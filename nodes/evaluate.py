# ─────────────────────────────────────────────
#  nodes/evaluate.py  –  Node 3 (runs N times in parallel)
#  Each invocation evaluates ONE submitted prompt.
#  Flow: pre-check → fetch scenario context → LLM scores → JSON
# ─────────────────────────────────────────────
from __future__ import annotations
import asyncio
from collections import deque
import json
import os
from typing import Union
import re
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import WorkerState
from tools.scenario_loader import get_scenario_context
from prompts.evaluator_system_prompt import SYSTEM_PROMPT
from config import WORKER_1, WORKER_2, DOMAIN_COLUMN, PROMPT_COLUMN, RPM_LIMIT, CACHE_DIR


# ── Lazy asyncio primitives ───────────────────────────────────
# Recreated whenever a new event loop is detected (e.g. new subprocess).
_primitives: dict = {}

def _get_primitives() -> dict:
    """
    Always returns primitives bound to the *current* running loop.
    Safe across multiple asyncio.run() calls (CLI reruns, subprocess launches).
    """
    global _primitives
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError("_get_primitives() must be called inside a running event loop")

    if _primitives.get("loop") is not loop:
        _primitives = {
            "loop":         loop,
            "sem_w1":       asyncio.Semaphore(WORKER_1["semaphore_limit"]),
            "sem_w2":       asyncio.Semaphore(WORKER_2["semaphore_limit"]),
            "rate_lock_w1": asyncio.Lock(),
            "rate_lock_w2": asyncio.Lock(),
        }
    return _primitives


# ── Strict token-bucket rate limiter ─────────────────────────
#
# Strategy: enforce a MINIMUM GAP between consecutive requests per worker.
#   RPM_LIMIT = 15  →  min_gap = 60 / 15 = 4.0 s per worker
#
# The lock serialises entry so at most one coroutine at a time computes
# its wait and records its dispatch time. This makes it *impossible* for
# two requests to fire closer together than min_gap — no burst can occur.
#
# Why not a sliding window?
#   A sliding window lets N coroutines all "book" slots at t=0, fire them
#   simultaneously, then all wait ~60 s and repeat — recreating the burst.
#   A token bucket with per-request spacing eliminates that entirely.
#
_last_call_w1: float = 0.0   # time.monotonic() of last w1 dispatch
_last_call_w2: float = 0.0   # time.monotonic() of last w2 dispatch

_MIN_GAP = 60.0 / RPM_LIMIT  # seconds between requests (e.g. 4.0 s for RPM=15)


async def _acquire_rpm_slot(worker: str) -> None:
    """
    Block until it is safe to fire the next request for `worker`.
    Guarantees requests are spaced at least _MIN_GAP seconds apart.
    """
    global _last_call_w1, _last_call_w2

    p     = _get_primitives()
    is_w1 = worker == "worker1"
    lock  = p["rate_lock_w1"] if is_w1 else p["rate_lock_w2"]

    # The lock is held for the entire wait+record cycle.
    # This serialises all coroutines for this worker — they queue up here
    # and each one exits exactly _MIN_GAP after the previous one.
    async with lock:
        now  = time.monotonic()
        last = _last_call_w1 if is_w1 else _last_call_w2
        wait = (last + _MIN_GAP) - now

        if wait > 0:
            await asyncio.sleep(wait)

        # Record dispatch time *after* sleeping so the next waiter
        # measures from when this request actually fires.
        if is_w1:
            _last_call_w1 = time.monotonic()
        else:
            _last_call_w2 = time.monotonic()


# ── URL / short-prompt pre-check ─────────────────────────────
_URL_PATTERN = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|example\.com|\.test\b|\.local\b)[^\s]+",
    re.IGNORECASE,
)
_MIN_PROMPT_LENGTH = 20


def _empty_scores() -> dict:
    return {
        "task":      {"score": None, "feedback": ""},
        "context":   {"score": None, "feedback": ""},
        "persona":   {"score": None, "feedback": ""},
        "output":    {"score": None, "feedback": ""},
        "examples":  {"score": None, "feedback": ""},
        "about_you": {"score": None, "feedback": ""},
        "tg":        {"score": None, "feedback": ""},
        "total":     None,
        "grade":     "Flagged",
    }


def _pre_check(text: str) -> dict | None:
    """
    Returns a flagged result dict if the submission should be skipped,
    or None if it should proceed to LLM evaluation.
    """
    stripped = text.strip()

    if len(stripped) < _MIN_PROMPT_LENGTH:
        scores = _empty_scores()
        scores["task"]["feedback"] = "NA"
        return scores

    if _URL_PATTERN.search(stripped):
        scores = _empty_scores()
        for key in ["task", "context", "persona", "output", "examples", "about_you", "tg"]:
            scores[key]["feedback"] = "External link not supported"
        return scores

    return None


# ── LLM helpers ──────────────────────────────────────────────
def _get_llm(worker: str) -> ChatGoogleGenerativeAI:
    cfg = WORKER_1 if worker == "worker1" else WORKER_2
    return ChatGoogleGenerativeAI(
        model=cfg["model"],
        google_api_key=cfg["api_key"],
        temperature=0,
        max_retries=0,
        timeout=60,
    )


def _parse_json(response_content: Union[str, list]) -> dict:
    if isinstance(response_content, list):
        for part in response_content:
            if isinstance(part, dict) and "text" in part:
                text = part["text"]
                break
        else:
            text = "".join(str(p) for p in response_content)
    else:
        text = response_content

    text  = re.sub(r"```(?:json)?|```", "", text).strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        json_str = text[start : end + 1]
    else:
        json_str = text

    try:
        return json.loads(json_str)
    except Exception as e:
        print(f"[parse_json] Failed to parse JSON: {e}")
        scores = _empty_scores()
        scores["task"]["feedback"] = f"LLM returned invalid JSON: {json_str[:50]}..."
        return scores


# ── Main evaluate node ────────────────────────────────────────
async def evaluate_node(state: WorkerState) -> dict:
    worker = state["worker"]
    index  = state["index"]
    row    = state["row"]

    p         = _get_primitives()
    semaphore = p["sem_w1"] if worker == "worker1" else p["sem_w2"]

    # ── Cache check ──────────────────────────────────────────
    cache_file = os.path.join(CACHE_DIR, f"row_{index:04d}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_scores = json.load(f)
            return {"results": [{"index": index, "scores": cached_scores}]}
        except Exception as e:
            print(f"[evaluate] Row {index:04d} | Cache read failed: {e}")

    domain           = str(row.get(DOMAIN_COLUMN, "")).strip()
    submitted_prompt = str(row.get(PROMPT_COLUMN, "")).strip()

    # ── Pre-check: skip flagged rows without touching the API ─
    flagged = _pre_check(submitted_prompt)
    if flagged:
        flag_reason = flagged["task"]["feedback"]
        print(f"[evaluate] Row {index:04d} | {worker} | FLAGGED → {flag_reason}")
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(flagged, f, indent=4)
        except Exception:
            pass
        return {"results": [{"index": index, "scores": flagged}]}

    # ── Gate 1: rate limiter (token bucket, strict spacing) ───
    # Acquired OUTSIDE the semaphore so coroutines queue here
    # rather than holding a semaphore slot while waiting.
    await _acquire_rpm_slot(worker)

    scenario_context = get_scenario_context.invoke({"scenario_type": domain})

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"scenario_type: {domain}\n\n"
            f"Scenario Context:\n{scenario_context}\n\n"
            f"Submitted Prompt:\n{submitted_prompt}"
        )),
    ]

    llm = _get_llm(worker)
    scores: dict | None = None

    for attempt in range(4):
        try:
            # ── Gate 2: concurrency limiter — wraps only the LLM call ────────
            async with semaphore:
                final_response = await llm.ainvoke(messages)

            # ── Success path (outside semaphore so slot is freed first) ───────
            scores = _parse_json(final_response.content)

            print(
                f"[evaluate] Row {index:04d} | {worker} | "
                f"domain={domain} | total={scores.get('total', '?')}/50"
            )

            os.makedirs(CACHE_DIR, exist_ok=True)
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(scores, f, indent=4)
            except Exception as e:
                print(f"[evaluate] Row {index:04d} | Failed writing cache: {e}")

            break  # done — exit retry loop

        except Exception as e:
            err = str(e)
            is_429     = "429" in err
            is_retriable = (
                is_429
                or "500" in err
                or "503" in err
                or "504" in err
                or "DEADLINE_EXCEEDED" in err
                or "INTERNAL" in err
                or "UNAVAILABLE" in err
                or "TimeoutError" in type(e).__name__
                or "ReadTimeout" in type(e).__name__
                or "ConnectTimeout" in type(e).__name__
                or isinstance(e, asyncio.CancelledError)
            )
            if is_retriable and attempt < 3:
                if is_429:
                    # Step 1 — honour the server's mandatory cooldown.
                    m = re.search(r'retry in (\d+(?:\.\d+)?)s', err, re.IGNORECASE)
                    wait = float(m.group(1)) if m else 60.0
                    print(
                        f"[evaluate] Row {index:04d} | 429 — cooling down {wait:.0f}s "
                        f"then re-queuing in rate limiter (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait)
                    # Step 2 — re-enter the rate-limiter queue so this retry is
                    # counted against the 15 RPM budget just like a fresh call.
                    # Without this, all retries fire simultaneously after their
                    # individual sleeps, causing a fresh burst of 429s.
                    await _acquire_rpm_slot(worker)
                else:
                    # 500 / 503 / timeout → short backoff, then re-queue.
                    wait = min(10 * (attempt + 1), 30)
                    print(
                        f"[evaluate] Row {index:04d} | {type(e).__name__} — "
                        f"retrying in {wait}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait)
                    await _acquire_rpm_slot(worker)
                continue
            else:
                # All retries exhausted or non-retriable error.
                # Do NOT cache this result — it was an API/network failure,
                # not a deterministic outcome. The next run should retry it
                # properly rather than treating the error as a real score.
                print(
                    f"[evaluate] Row {index:04d} | ERROR after {attempt + 1} attempt(s) "
                    f"— flagging row (not cached, will retry next run). Reason: {e}"
                )
                scores = _empty_scores()
                scores["task"]["feedback"] = f"Evaluation error: {e}"
                # ↑ No cache write here — intentional so a retry run re-evaluates
                break

    return {"results": [{"index": index, "scores": scores}]}