# ─────────────────────────────────────────────
#  nodes/router.py  –  Node 2
#  router_node returns a normal state update (dict)
#  route_rows returns the Send fan-out list for parallel execution
# ─────────────────────────────────────────────
from __future__ import annotations
from langgraph.types import Send
from state import OverallState


def router_node(state: OverallState) -> dict:
    """
    LangGraph node functions in a StateGraph must return a dict-like
    state update, not a list[Send].
    """
    total_rows = len(state.get("rows", []))
    print(f"[router] Preparing dispatch for {total_rows} rows")
    return {}


def route_rows(state: OverallState) -> list[Send]:
    """
    Conditional edge router that fans out all rows in parallel.
    Worker 1 gets first half, Worker 2 gets second half.
    """
    sends: list[Send] = []

    # First half → worker1
    for i, row in enumerate(state["half1"]):
        sends.append(
            Send(
                "evaluate",
                {
                    "row": row,
                    "worker": "worker1",
                    "index": i,
                },
            )
        )

    # Second half → worker2
    offset = len(state["half1"])
    for i, row in enumerate(state["half2"]):
        sends.append(
            Send(
                "evaluate",
                {
                    "row": row,
                    "worker": "worker2",
                    "index": offset + i,
                },
            )
        )

    print(f"[router] Dispatched {len(sends)} parallel evaluate tasks")
    return sends