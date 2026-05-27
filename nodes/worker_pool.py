# ─────────────────────────────────────────────────────────────────────────────
#  nodes/worker_pool.py  –  Dual-model async worker pool
#
#  DESIGN
#  ──────
#  Google gives each MODEL its own 15 RPM quota — completely independent of
#  other models on the same account.  Two models = two separate 15-RPM budgets
#  = 30 RPM combined ceiling.
#
#  We stay at 14 RPM per model (7% headroom) to absorb retry re-entries.
#  Gap between dispatches = 60 / 14 ≈ 4.3 s per model.
#
#  Average LLM latency ≈ 15 s.
#  To keep the pipeline saturated we need:  ceil(15s / 4.3s) = 4 in-flight
#  calls per model at any time.  That's exactly what the semaphore(4) does.
#
#  Timeline per model (simplified):
#    t=0.0   dispatch req-1   (slot 1 of 4 taken)
#    t=4.3   dispatch req-2   (slot 2 of 4 taken)
#    t=8.6   dispatch req-3   (slot 3 of 4 taken)
#    t=12.9  dispatch req-4   (slot 4 of 4 taken)
#    t=15.0  req-1 returns → slot freed → req-5 can enter sem immediately
#    t=17.2  dispatch req-5   (gap enforced by rate limiter, not sem)
#    → fully saturated, no idle gaps
#
#  Both models run in parallel → combined ~28 RPM effective throughput.
#  250 rows ÷ 28 ≈ 9 minutes (vs ~30 min with the old 5-semaphore design).
#
#  RETRY STRATEGY
#  ──────────────
#  • 429 (per-minute limit):  sleep the retry-after hint, then re-enter
#    THIS model's own rate limiter queue.  The limiter space them correctly.
#  • 429 (daily quota):       fatal — surface a clear message, stop retrying.
#  • 500 / 503 / timeout:     exponential backoff, re-enter rate limiter.
#  • All retries re-acquire a rate slot from the top so they're counted
#    against the model's budget just like a fresh request.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts.evaluator_system_prompt import SYSTEM_PROMPT
from config import CACHE_DIR

# ── Tunables ──────────────────────────────────────────────────────────────────
RPM_PER_MODEL   = 14        # stay 1 below Google's 15 RPM hard ceiling
_GAP            = 60.0 / RPM_PER_MODEL   # ~4.29 s between dispatches per model
_JITTER         = 0.25      # ±random seconds added after each sleep to
                             # prevent two models firing at the same millisecond
_CONCURRENCY    = 10         # in-flight calls per model  (ceil(15s latency / 4.3s gap))
_LLM_TIMEOUT    = 90        # seconds before a hung call is hard-cancelled
_MAX_ATTEMPTS   = 4         # total tries per row (1 original + 3 retries)


# ── Daily-quota detection ─────────────────────────────────────────────────────
_DAILY_SIGNALS = [
    "resource_exhausted", "daily", "per day",
    "quota exceeded", "free tier", "billing", "project quota",
]

def _is_daily_quota(err: str) -> bool:
    lower = err.lower()
    return any(sig in lower for sig in _DAILY_SIGNALS)


# ── Empty / flagged score skeleton ────────────────────────────────────────────
def _empty_scores(feedback: str = "") -> dict:
    base = {
        "task":      {"score": None, "feedback": feedback},
        "context":   {"score": None, "feedback": feedback},
        "persona":   {"score": None, "feedback": feedback},
        "output":    {"score": None, "feedback": feedback},
        "examples":  {"score": None, "feedback": feedback},
        "about_you": {"score": None, "feedback": feedback},
        "tg":        {"score": None, "feedback": feedback},
        "total":     None,
        "grade":     "Flagged",
    }
    # task feedback is the canonical "reason" field used by the UI
    base["task"]["feedback"] = feedback
    return base


# ── JSON parser ───────────────────────────────────────────────────────────────
def _parse_json(content) -> dict:
    if isinstance(content, list):
        text = next(
            (p["text"] for p in content if isinstance(p, dict) and "text" in p),
            "".join(str(p) for p in content),
        )
    else:
        text = str(content)

    text  = re.sub(r"```(?:json)?|```", "", text).strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]

    try:
        return json.loads(text)
    except Exception as e:
        return _empty_scores(f"LLM returned invalid JSON: {text[:80]}…  ({e})")


# ── WorkItem ──────────────────────────────────────────────────────────────────
@dataclass
class WorkItem:
    index:    int
    row:      dict
    messages: list
    future:   asyncio.Future          # caller awaits this to get scores
    attempt:  int = 0


# ── ModelWorker ───────────────────────────────────────────────────────────────
class ModelWorker:
    """
    Owns one model's queue, rate limiter, and concurrency semaphore.
    Runs as a background async task for the lifetime of one evaluation run.
    """

    def __init__(self, name: str, model: str, api_key: str):
        self.name    = name
        self.model   = model
        self.api_key = api_key

        self._queue: asyncio.Queue[WorkItem | None] = asyncio.Queue()
        self._sem   = asyncio.Semaphore(_CONCURRENCY)
        self._lock  = asyncio.Lock()      # serialises rate-slot acquisition
        self._last  = 0.0                 # monotonic time of last dispatch

        self._llm   = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.1,
            max_retries=0,          # we handle all retries ourselves
            timeout=_LLM_TIMEOUT,
        )

    # ── public API ────────────────────────────────────────────────────────────

    def submit(self, item: WorkItem) -> None:
        """Put a work item onto this worker's queue (thread-safe)."""
        self._queue.put_nowait(item)

    async def run(self) -> None:
        """
        Dispatcher loop.  Runs until it receives a None sentinel.
        For each item it:
          1. acquires a rate slot (blocks here to enforce 14 RPM spacing)
          2. spawns an async task for the actual LLM call (so the next item
             can start acquiring its rate slot immediately — that's how we get
             4 calls in-flight: item-1 is at step 1→2 while item-2 is at
             step 1→2 with a 4.3 s delay, etc.)
        """
        tasks: list[asyncio.Task] = []

        while True:
            item = await self._queue.get()
            if item is None:            # sentinel → drain and exit
                break

            await self._acquire_slot()  # blocks here; next item queues behind
            t = asyncio.create_task(self._call(item))
            tasks.append(t)

        # Wait for all in-flight calls to finish before returning
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── internals ─────────────────────────────────────────────────────────────

    async def _acquire_slot(self) -> None:
        """Token-bucket: enforce _GAP seconds between dispatches."""
        async with self._lock:
            now  = time.monotonic()
            wait = (self._last + _GAP) - now
            if wait > 0:
                await asyncio.sleep(wait)
            await asyncio.sleep(random.uniform(0, _JITTER))
            self._last = time.monotonic()

    async def _call(self, item: WorkItem) -> None:
        """
        Make one LLM call.  On failure, either re-queues the item (retriable
        errors) or resolves the future with an error score (fatal errors).
        The semaphore caps how many _call coroutines run simultaneously.
        """
        async with self._sem:
            try:
                response = await asyncio.wait_for(
                    self._llm.ainvoke(item.messages),
                    timeout=_LLM_TIMEOUT,
                )
                scores = _parse_json(response.content)
                self._resolve(item, scores)

            except asyncio.TimeoutError:
                self._handle_error(item, "TimeoutError", retriable=True, wait=5)

            except Exception as e:
                err = str(e)
                is_429 = "429" in err

                if is_429 and _is_daily_quota(err):
                    print(
                        f"[{self.name}] Row {item.index:04d} | "
                        f"DAILY QUOTA EXHAUSTED — switch API key and re-run."
                    )
                    self._resolve(item, _empty_scores(
                        "Daily API quota exhausted. Switch API key and re-run."
                    ))
                    return

                retriable = (
                    is_429
                    or any(c in err for c in ("500", "503", "504"))
                    or any(k in err for k in (
                        "DEADLINE_EXCEEDED", "INTERNAL", "UNAVAILABLE",
                        "TimeoutError", "ReadTimeout", "ConnectTimeout",
                    ))
                )

                if retriable:
                    if is_429:
                        m    = re.search(r'retry in (\d+(?:\.\d+)?)s', err, re.IGNORECASE)
                        wait = min(float(m.group(1)) if m else 60.0, 120.0)
                    else:
                        wait = min(8 * (2 ** item.attempt), 60)   # 8, 16, 32, 60
                    self._handle_error(item, type(e).__name__, retriable=True, wait=wait)
                else:
                    print(
                        f"[{self.name}] Row {item.index:04d} | "
                        f"Non-retriable error: {e}"
                    )
                    self._resolve(item, _empty_scores(f"Evaluation error: {e}"))

    def _handle_error(
        self, item: WorkItem, reason: str, retriable: bool, wait: float
    ) -> None:
        item.attempt += 1
        if retriable and item.attempt < _MAX_ATTEMPTS:
            print(
                f"[{self.name}] Row {item.index:04d} | "
                f"{reason} — retrying in {wait:.0f}s "
                f"(attempt {item.attempt}/{_MAX_ATTEMPTS - 1})"
            )
            # Schedule the re-queue after the backoff sleep.
            # asyncio.create_task so we don't block _call's semaphore slot.
            asyncio.create_task(self._requeue_after(item, wait))
        else:
            print(
                f"[{self.name}] Row {item.index:04d} | "
                f"Failed after {item.attempt} attempt(s): {reason}"
            )
            self._resolve(item, _empty_scores(f"Evaluation error after retries: {reason}"))

    async def _requeue_after(self, item: WorkItem, wait: float) -> None:
        await asyncio.sleep(wait)
        # Re-enter the same worker's queue — the dispatcher loop will
        # re-acquire a rate slot before firing, preventing retry bursts.
        self._queue.put_nowait(item)

    def _resolve(self, item: WorkItem, scores: dict) -> None:
        """Resolve the caller's future (safe to call from any task)."""
        if not item.future.done():
            item.future.get_loop().call_soon_threadsafe(
                item.future.set_result, scores
            )


# ── Pool — holds both workers ─────────────────────────────────────────────────
class EvaluatorPool:
    """
    Manages two ModelWorker instances and their background dispatcher tasks.
    Use as an async context manager:

        async with EvaluatorPool() as pool:
            scores = await pool.evaluate(index, row, messages, worker="worker1")
    """

    def __init__(self, worker1_cfg: dict, worker2_cfg: dict):
        self._w1 = ModelWorker("worker1", worker1_cfg["model"], worker1_cfg["api_key"])
        self._w2 = ModelWorker("worker2", worker2_cfg["model"], worker2_cfg["api_key"])
        self._tasks: list[asyncio.Task] = []

    async def __aenter__(self):
        loop = asyncio.get_running_loop()
        self._tasks = [
            loop.create_task(self._w1.run(), name="worker1-dispatcher"),
            loop.create_task(self._w2.run(), name="worker2-dispatcher"),
        ]
        return self

    async def __aexit__(self, *_):
        # Send sentinel to stop both dispatcher loops
        self._w1._queue.put_nowait(None)
        self._w2._queue.put_nowait(None)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def evaluate(
        self,
        index:    int,
        row:      dict,
        messages: list,
        worker:   str,
    ) -> dict:
        """
        Submit a row to the specified worker and await its result.
        The future is resolved by the worker's background dispatcher task.
        """
        loop   = asyncio.get_running_loop()
        future = loop.create_future()
        item   = WorkItem(index=index, row=row, messages=messages, future=future)

        target = self._w1 if worker == "worker1" else self._w2
        target.submit(item)

        return await future


# ── Module-level singleton ────────────────────────────────────────────────────
# evaluate.py imports this and calls pool.evaluate(…).
# graph.py / main.py wraps the whole run in `async with get_pool():`.

_pool: EvaluatorPool | None = None


def init_pool(worker1_cfg: dict, worker2_cfg: dict) -> EvaluatorPool:
    global _pool
    _pool = EvaluatorPool(worker1_cfg, worker2_cfg)
    return _pool


def get_pool() -> EvaluatorPool:
    if _pool is None:
        raise RuntimeError("Call init_pool() before get_pool()")
    return _pool