# ─────────────────────────────────────────────
#  nodes/evaluate.py  –  Node 3 (runs N times in parallel via LangGraph fan-out)
#
#  This file is now a thin wrapper.  All the rate-limiting, concurrency,
#  and retry logic lives in worker_pool.py (ModelWorker / EvaluatorPool).
#
#  Responsibilities here:
#   1. Cache check (skip API call entirely if already evaluated)
#   2. Pre-check (flag short prompts / URLs without touching the API)
#   3. Build the message list
#   4. Delegate to the pool and await the result
#   5. Write to cache on success
# ─────────────────────────────────────────────
from __future__ import annotations

import json
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage

from state import WorkerState
from tools.scenario_loader import get_scenario_context
from prompts.evaluator_system_prompt import SYSTEM_PROMPT
from config import DOMAIN_COLUMN, PROMPT_COLUMN, CACHE_DIR
from nodes.worker_pool import get_pool


# ── Pre-check constants ───────────────────────────────────────────────────────
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
    """Returns a flagged score dict if the row should be skipped, else None."""
    stripped = text.strip()

    if len(stripped) < _MIN_PROMPT_LENGTH:
        return _empty_scores("NA")

    if _URL_PATTERN.search(stripped):
        scores = _empty_scores("External link not supported")
        for key in ["context", "persona", "output", "examples", "about_you", "tg"]:
            scores[key]["feedback"] = "External link not supported"
        return scores

    return None


# ── Main evaluate node ────────────────────────────────────────────────────────
async def evaluate_node(state: WorkerState) -> dict:
    worker = state["worker"]
    index  = state["index"]
    row    = state["row"]

    # ── 1. Cache check ────────────────────────────────────────────────────────
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"row_{index:04d}.json")

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

    # ── 2. Pre-check: no API call needed ─────────────────────────────────────
    flagged = _pre_check(submitted_prompt)
    if flagged:
        print(f"[evaluate] Row {index:04d} | {worker} | FLAGGED → {flagged['task']['feedback']}")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(flagged, f, indent=4)
        except Exception:
            pass
        return {"results": [{"index": index, "scores": flagged}]}

    # ── 3. Build messages ─────────────────────────────────────────────────────
    scenario_context = get_scenario_context.invoke({"scenario_type": domain})
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"scenario_type: {domain}\n\n"
            f"Scenario Context:\n{scenario_context}\n\n"
            f"Submitted Prompt:\n{submitted_prompt}"
        )),
    ]

    # ── 4. Delegate to pool ───────────────────────────────────────────────────
    pool   = get_pool()
    scores = await pool.evaluate(
        index=index,
        row=row,
        messages=messages,
        worker=worker,
    )

    print(
        f"[evaluate] Row {index:04d} | {worker} | "
        f"domain={domain} | total={scores.get('total', '?')}/50"
    )

    # ── 5. Write cache (only on non-error results) ────────────────────────────
    is_error = (
        scores.get("grade") == "Flagged"
        and "error" in str(scores.get("task", {}).get("feedback", "")).lower()
    )
    if not is_error:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(scores, f, indent=4)
        except Exception as e:
            print(f"[evaluate] Row {index:04d} | Cache write failed: {e}")

    return {"results": [{"index": index, "scores": scores}]}