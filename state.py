# ─────────────────────────────────────────────
#  state.py  –  shared LangGraph state schemas
# ─────────────────────────────────────────────
from __future__ import annotations
import operator
from typing import Annotated, Any
from typing_extensions import TypedDict


class OverallState(TypedDict):
    """State that flows through the main graph."""
    rows:    list[dict]                          # all CSV rows as dicts
    half1:   list[dict]                          # rows for Worker 1
    half2:   list[dict]                          # rows for Worker 2
    results: Annotated[list[dict], operator.add] # fan-in collector


class WorkerState(TypedDict):
    """State for each individual evaluate node invocation."""
    row:     dict   # single CSV row
    worker:  str    # "worker1" or "worker2"
    index:   int    # original row index (to preserve order in output)
