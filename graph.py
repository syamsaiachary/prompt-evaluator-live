# ─────────────────────────────────────────────
#  graph.py  –  LangGraph graph definition
# ─────────────────────────────────────────────
from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from state import OverallState
from nodes.load_csv import load_csv_node
from nodes.router import router_node, route_rows
from nodes.evaluate import evaluate_node
from nodes.aggregate import aggregate_node
from nodes.generate_excel_node import generate_excel_node


def build_graph():
    """
    Build and compile the evaluation graph.

    Flow:
      START
        → load_csv
        → router
        → evaluate × N (parallel fan-out via route_rows)
        → aggregate
        → generate_excel
        → END
    """
    builder = StateGraph(OverallState)

    # Nodes
    builder.add_node("load_csv", load_csv_node)
    builder.add_node("router", router_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("generate_excel", generate_excel_node)

    # Edges
    builder.add_edge(START, "load_csv")
    builder.add_edge("load_csv", "router")

    # IMPORTANT:
    # router_node is the node
    # route_rows is the conditional routing function that returns list[Send]
    builder.add_conditional_edges("router", route_rows, ["evaluate"])

    builder.add_edge("evaluate", "aggregate")
    builder.add_edge("aggregate", "generate_excel")
    builder.add_edge("generate_excel", END)

    return builder.compile()