# ─────────────────────────────────────────────────────────────────────────────
#  nodes/worker_pool.py  –  Dual-model async worker pool (litellm backend)
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from prompts.evaluator_system_prompt import SYSTEM_PROMPT
from tools.scenario_loader import get_scenario_context
from config import CACHE_DIR

# Suppress litellm's startup banner and success noise
litellm.suppress_debug_info = True
litellm.set_verbose         = False

# ── Tunables ──────────────────────────────────────────────────────────────────
RPM_PER_MODEL = 14
_GAP          = 60.0 / RPM_PER_MODEL   # ~4.29 s between dispatches per model
_JITTER       = 0.25
_CONCURRENCY  = 10
# API_TIMEOUT applies only to the actual HTTP call — not queue/semaphore wait.
# Previously asyncio.wait_for() wrapped the entire _call including sem acquisition,
# so rows queued behind others were timing out before the API was even reached.
_API_TIMEOUT  = 90
_MAX_ATTEMPTS = 4

# ── Daily-quota detection ─────────────────────────────────────────────────────
_DAILY_SIGNALS = [
    "resource_exhausted", "daily", "per day",
    "quota exceeded", "free tier", "billing", "project quota",
]

def _is_daily_quota(err: str) -> bool:
    return any(sig in err.lower() for sig in _DAILY_SIGNALS)


# ── Score helpers ─────────────────────────────────────────────────────────────
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
    base["task"]["feedback"] = feedback
    return base


def _parse_json(content: Any) -> dict:
    text  = str(content)
    text  = re.sub(r"```(?:json)?|```", "", text).strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        return _empty_scores(f"LLM returned invalid JSON: {text[:80]}… ({e})")


# ── WorkItem ──────────────────────────────────────────────────────────────────
@dataclass
class WorkItem:
    index:            int
    domain:           str
    submitted_prompt: str
    future:           asyncio.Future
    attempt:          int = 0


# ── ModelWorker ───────────────────────────────────────────────────────────────
class ModelWorker:
    def __init__(self, name: str, model: str, api_key: str):
        self.name    = name
        self.model   = model
        self.api_key = api_key

        self._queue: asyncio.Queue[WorkItem | None] = asyncio.Queue()
        self._sem   = asyncio.Semaphore(_CONCURRENCY)
        self._lock  = asyncio.Lock()
        self._last  = 0.0

    def submit(self, item: WorkItem) -> None:
        self._queue.put_nowait(item)

    async def run(self) -> None:
        tasks: list[asyncio.Task] = []
        while True:
            item = await self._queue.get()
            if item is None:
                break
            await self._acquire_slot()
            tasks.append(asyncio.create_task(self._call(item)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _acquire_slot(self) -> None:
        async with self._lock:
            now  = time.monotonic()
            wait = (self._last + _GAP) - now
            if wait > 0:
                await asyncio.sleep(wait)
            await asyncio.sleep(random.uniform(0, _JITTER))
            self._last = time.monotonic()

    async def _call(self, item: WorkItem) -> None:
        # Semaphore acquired here — waiting here does NOT count against timeout
        async with self._sem:
            await self._call_api(item)

    async def _call_api(self, item: WorkItem) -> None:
        # Timeout starts HERE — only after semaphore is acquired and we're
        # actually about to hit the API. Queue and semaphore wait time is excluded.
        try:
            scenario_context = get_scenario_context.invoke(
                {"scenario_type": item.domain}
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"scenario_type: {item.domain}\n\n"
                    f"Scenario Context:\n{scenario_context}\n\n"
                    f"Submitted Prompt:\n{item.submitted_prompt}"
                )},
            ]

            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    api_key=self.api_key,
                    timeout=_API_TIMEOUT,
                ),
                timeout=_API_TIMEOUT + 5,  # outer guard if litellm's own timeout stalls
            )

            scores = _parse_json(response.choices[0].message.content)
            self._resolve(item, scores)

        except asyncio.TimeoutError:
            self._handle_error(item, "Timeout", retriable=True, wait=5)

        except Exception as e:
            err    = str(e)
            is_429 = "429" in err or isinstance(e, litellm.RateLimitError)

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
                    "ReadTimeout", "ConnectTimeout",
                ))
                or isinstance(e, (
                    litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIConnectionError,
                    litellm.Timeout,
                ))
            )

            if retriable:
                if is_429:
                    m    = re.search(r'retry in (\d+(?:\.\d+)?)s', err, re.IGNORECASE)
                    wait = min(float(m.group(1)) if m else 60.0, 120.0)
                else:
                    wait = min(8 * (2 ** item.attempt), 60)
                self._handle_error(item, type(e).__name__, retriable=True, wait=wait)
            else:
                print(f"[{self.name}] Row {item.index:04d} | Non-retriable: {e}")
                self._resolve(item, _empty_scores(f"Evaluation error: {e}"))

    def _handle_error(
        self, item: WorkItem, reason: str, retriable: bool, wait: float
    ) -> None:
        item.attempt += 1
        if retriable and item.attempt < _MAX_ATTEMPTS:
            print(
                f"[{self.name}] Row {item.index:04d} | "
                f"{reason} — retry in {wait:.0f}s "
                f"(attempt {item.attempt}/{_MAX_ATTEMPTS - 1})"
            )
            asyncio.create_task(self._requeue_after(item, wait))
        else:
            print(
                f"[{self.name}] Row {item.index:04d} | "
                f"Failed after {item.attempt} attempt(s): {reason}"
            )
            self._resolve(item, _empty_scores(
                f"Evaluation error after retries: {reason}"
            ))

    async def _requeue_after(self, item: WorkItem, wait: float) -> None:
        await asyncio.sleep(wait)
        self._queue.put_nowait(item)

    def _resolve(self, item: WorkItem, scores: dict) -> None:
        if not item.future.done():
            item.future.set_result(scores)


# ── EvaluatorPool ─────────────────────────────────────────────────────────────
class EvaluatorPool:
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
        self._w1._queue.put_nowait(None)
        self._w2._queue.put_nowait(None)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def evaluate(
        self,
        index:            int,
        domain:           str,
        submitted_prompt: str,
        worker:           str,
    ) -> dict:
        loop   = asyncio.get_running_loop()
        future = loop.create_future()
        item   = WorkItem(
            index=index,
            domain=domain,
            submitted_prompt=submitted_prompt,
            future=future,
        )
        target = self._w1 if worker == "worker1" else self._w2
        target.submit(item)
        return await future


# ── Module-level singleton ────────────────────────────────────────────────────
_pool: EvaluatorPool | None = None


def init_pool(worker1_cfg: dict, worker2_cfg: dict) -> EvaluatorPool:
    global _pool
    _pool = EvaluatorPool(worker1_cfg, worker2_cfg)
    return _pool


def get_pool() -> EvaluatorPool:
    if _pool is None:
        raise RuntimeError("Call init_pool() before get_pool()")
    return _pool