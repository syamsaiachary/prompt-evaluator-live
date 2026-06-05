# ─────────────────────────────────────────────────────────────────────────────
#  nodes/worker_pool.py  –  Dual-model async worker pool (litellm backend)
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

import litellm

from prompts.evaluator_system_prompt import SYSTEM_PROMPT
from tools.scenario_loader import get_scenario_context
from config import CACHE_DIR

# Silence litellm's verbose success logs — errors still surface
litellm.success_callback = []
litellm.set_verbose      = False

# ── Tunables ──────────────────────────────────────────────────────────────────
RPM_PER_MODEL  = 14
_GAP           = 60.0 / RPM_PER_MODEL   # ~4.29 s between dispatches per model
_JITTER        = 0.25
_CONCURRENCY   = 10
_LLM_TIMEOUT   = 120
_MAX_ATTEMPTS  = 4

_RATE_BACKOFF   = [15, 30, 60]    # seconds for 429 retries
_SERVER_BACKOFF = [20, 45, 90]    # seconds for 5xx / timeout retries


# ── Daily-quota detection ─────────────────────────────────────────────────────
_DAILY_SIGNALS = [
    "resource_exhausted", "daily", "per day",
    "quota exceeded", "free tier", "billing", "project quota",
]

def _is_daily_quota(err: str) -> bool:
    return any(sig in err.lower() for sig in _DAILY_SIGNALS)


# ── Score helpers ─────────────────────────────────────────────────────────────
def _empty_scores(feedback: str = "") -> dict:
    base = {k: {"score": None, "feedback": ""} for k in
            ["task", "context", "persona", "output", "examples", "about_you", "tg"]}
    base["total"] = None
    base["grade"] = "Flagged"
    base["task"]["feedback"] = feedback
    return base


def _parse_json(content: Any) -> dict:
    text = str(content)
    text = re.sub(r"```(?:json)?|```", "", text).strip()
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
    cancelled:        asyncio.Event = field(default_factory=asyncio.Event)
    attempt:          int  = 0
    is_fallback:      bool = False


# ── ModelWorker ───────────────────────────────────────────────────────────────
class ModelWorker:
    def __init__(self, name: str, model: str, api_key: str):
        self.name    = name
        self.model   = model          # litellm format: "gemini/gemma-4-31b-it"
        self.api_key = api_key

        self._queue: asyncio.Queue[WorkItem | None] = asyncio.Queue()
        self._sem   = asyncio.Semaphore(_CONCURRENCY)
        self._lock  = asyncio.Lock()
        self._last  = 0.0
        self._fallback_worker: "ModelWorker | None" = None

    def set_fallback(self, worker: "ModelWorker") -> None:
        self._fallback_worker = worker

    def submit(self, item: WorkItem) -> None:
        self._queue.put_nowait(item)

    async def run(self) -> None:
        tasks: list[asyncio.Task] = []
        while True:
            item = await self._queue.get()
            if item is None:
                break
            if item.cancelled.is_set():
                print(f"[{self.name}] Row {item.index:04d} | Skipping cancelled item")
                continue
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
        if item.cancelled.is_set():
            return

        async with self._sem:
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
                        timeout=_LLM_TIMEOUT,
                    ),
                    timeout=_LLM_TIMEOUT + 5,  # outer guard in case litellm's own timeout stalls
                )

                content = response.choices[0].message.content
                scores  = _parse_json(content)

                if not item.cancelled.is_set():
                    self._resolve(item, scores)

            except asyncio.TimeoutError:
                self._handle_error(item, "TimeoutError", is_rate_limit=False)

            except litellm.RateLimitError as e:
                err = str(e)
                if _is_daily_quota(err):
                    print(
                        f"[{self.name}] Row {item.index:04d} | "
                        f"DAILY QUOTA EXHAUSTED — switch API key and re-run."
                    )
                    self._resolve(item, _empty_scores(
                        "Daily API quota exhausted. Switch API key and re-run."
                    ))
                    return
                m    = re.search(r'retry in (\d+(?:\.\d+)?)s', err, re.IGNORECASE)
                wait = min(float(m.group(1)) if m else 60.0, 120.0)
                self._handle_error(item, "RateLimitError",
                                   is_rate_limit=True, wait_override=wait)

            except (litellm.ServiceUnavailableError,
                    litellm.InternalServerError,
                    litellm.APIConnectionError,
                    litellm.Timeout) as e:
                self._handle_error(item, type(e).__name__, is_rate_limit=False)

            except Exception as e:
                # Catch-all for any other litellm or network error
                err = str(e)
                is_retriable = any(c in err for c in ("502", "503", "504")) or \
                               any(k in err for k in (
                                   "DEADLINE_EXCEEDED", "UNAVAILABLE",
                                   "ReadTimeout", "ConnectTimeout",
                               ))
                if is_retriable:
                    self._handle_error(item, type(e).__name__, is_rate_limit=False)
                else:
                    print(f"[{self.name}] Row {item.index:04d} | Non-retriable: {e}")
                    self._resolve(item, _empty_scores(f"Evaluation error: {e}"))

    def _handle_error(
        self,
        item: WorkItem,
        reason: str,
        is_rate_limit: bool,
        wait_override: float | None = None,
    ) -> None:
        item.attempt += 1

        if item.attempt < _MAX_ATTEMPTS:
            if wait_override is not None:
                wait = wait_override
            elif is_rate_limit:
                wait = _RATE_BACKOFF[min(item.attempt - 1, len(_RATE_BACKOFF) - 1)]
            else:
                wait = _SERVER_BACKOFF[min(item.attempt - 1, len(_SERVER_BACKOFF) - 1)]

            print(
                f"[{self.name}] Row {item.index:04d} | "
                f"{reason} — retry in {wait:.0f}s "
                f"(attempt {item.attempt}/{_MAX_ATTEMPTS - 1})"
            )
            asyncio.create_task(self._requeue_after(item, wait))

        else:
            if self._fallback_worker and not item.is_fallback:
                print(
                    f"[{self.name}] Row {item.index:04d} | "
                    f"All {_MAX_ATTEMPTS} attempts failed ({reason}). "
                    f"Handing off to {self._fallback_worker.name}."
                )
                item.attempt     = 0
                item.is_fallback = True
                asyncio.create_task(self._requeue_after(
                    item, 15, target=self._fallback_worker
                ))
            else:
                print(
                    f"[{self.name}] Row {item.index:04d} | "
                    f"Failed after {item.attempt} attempt(s) "
                    f"{'(fallback also failed) ' if item.is_fallback else ''}: {reason}"
                )
                self._resolve(item, _empty_scores(
                    f"Evaluation error after retries: {reason}"
                ))

    async def _requeue_after(
        self,
        item: WorkItem,
        wait: float,
        target: "ModelWorker | None" = None,
    ) -> None:
        await asyncio.sleep(wait)
        if not item.cancelled.is_set():
            (target or self)._queue.put_nowait(item)

    def _resolve(self, item: WorkItem, scores: dict) -> None:
        if not item.future.done():
            item.future.set_result(scores)


# ── EvaluatorPool ─────────────────────────────────────────────────────────────
class EvaluatorPool:
    def __init__(self, worker1_cfg: dict, worker2_cfg: dict):
        self._w1 = ModelWorker("worker1", worker1_cfg["model"], worker1_cfg["api_key"])
        self._w2 = ModelWorker("worker2", worker2_cfg["model"], worker2_cfg["api_key"])
        self._w1.set_fallback(self._w2)
        self._w2.set_fallback(self._w1)
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

        try:
            return await future
        except asyncio.CancelledError:
            item.cancelled.set()
            raise


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