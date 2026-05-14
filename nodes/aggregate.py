# ─────────────────────────────────────────────
#  nodes/aggregate.py  –  Node 4
#  Fan-in: all individual results are already collected
#  into state["results"] by LangGraph's Annotated reducer.
#  This node just logs and passes through.
# ─────────────────────────────────────────────
from __future__ import annotations
from state import OverallState


def aggregate_node(state: OverallState) -> dict:
    total = len(state.get("results", []))
    print(f"[aggregate] Collected {total} evaluated results")
    return {}
