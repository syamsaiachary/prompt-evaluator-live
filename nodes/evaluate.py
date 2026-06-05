# ─────────────────────────────────────────────
#  nodes/evaluate.py  –  Node 3
# ─────────────────────────────────────────────
from __future__ import annotations

import json
import os
import re

from state import WorkerState
from config import DOMAIN_COLUMN, PROMPT_COLUMN, CACHE_DIR
from nodes.worker_pool import get_pool

# ── Pre-check ─────────────────────────────────────────────────────────────────
_URL_PATTERN = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|example\.com|\.test\b|\.local\b)[^\s]+",
    re.IGNORECASE,
)
_MIN_PROMPT_LENGTH = 20


def _empty_scores(feedback: str = "") -> dict:
    base = {k: {"score": None, "feedback": ""} for k in
            ["task", "context", "persona", "output", "examples", "about_you", "tg"]}
    base["total"] = None
    base["grade"] = "Flagged"
    base["task"]["feedback"] = feedback
    return base


def _pre_check(text: str) -> dict | None:
    stripped = text.strip()
    if len(stripped) < _MIN_PROMPT_LENGTH:
        return _empty_scores("NA")
    if _URL_PATTERN.search(stripped):
        scores = _empty_scores("External link not supported")
        for k in ["context", "persona", "output", "examples", "about_you", "tg"]:
            scores[k]["feedback"] = "External link not supported"
        return scores
    return None


# Feedback strings that must NOT be cached — row should be retried next run
_NO_CACHE_SIGNALS = [
    "error",
    "quota exhausted",
    "switch api key",
    "after retries",
    "timed out",
]

def _should_cache(scores: dict) -> bool:
    """Return False for any result that was caused by an API/infra failure."""
    if scores.get("total") is not None:
        return True  # scored successfully — always cache
    feedback = str(scores.get("task", {}).get("feedback", "")).lower()
    return not any(sig in feedback for sig in _NO_CACHE_SIGNALS)


# ── Main node ─────────────────────────────────────────────────────────────────
async def evaluate_node(state: WorkerState) -> dict:
    worker = state["worker"]
    index  = state["index"]
    row    = state["row"]

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"row_{index:04d}.json")

    # 1. Cache hit
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            print(f"[evaluate] Row {index:04d} | {worker} | Cache HIT")
            return {"results": [{"index": index, "scores": cached}]}
        except Exception as e:
            print(f"[evaluate] Row {index:04d} | Cache read failed: {e}")

    domain           = str(row.get(DOMAIN_COLUMN, "")).strip()
    submitted_prompt = str(row.get(PROMPT_COLUMN, "")).strip()

    # 2. Pre-check
    flagged = _pre_check(submitted_prompt)
    if flagged:
        print(f"[evaluate] Row {index:04d} | {worker} | FLAGGED → {flagged['task']['feedback']}")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(flagged, f, indent=4)
        except Exception:
            pass
        return {"results": [{"index": index, "scores": flagged}]}

    # 3. Delegate to pool
    pool   = get_pool()
    scores = await pool.evaluate(
        index=index,
        domain=domain,
        submitted_prompt=submitted_prompt,
        worker=worker,
    )

    print(
        f"[evaluate] Row {index:04d} | {worker} | "
        f"domain={domain} | total={scores.get('total', '?')}/50"
    )

    # 4. Cache only results that are not API/infra failures
    if _should_cache(scores):
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(scores, f, indent=4)
        except Exception as e:
            print(f"[evaluate] Row {index:04d} | Cache write failed: {e}")
    else:
        print(f"[evaluate] Row {index:04d} | Not cached — will retry on next run")

    return {"results": [{"index": index, "scores": scores}]}