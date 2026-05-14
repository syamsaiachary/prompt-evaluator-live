# ─────────────────────────────────────────────
#  nodes/generate_excel_node.py  –  Node 5
#  Calls the generate_excel tool to write the final .xlsx
# ─────────────────────────────────────────────
from __future__ import annotations
from state import OverallState
from tools.excel_generator import generate_excel
from config import OUTPUT_PATH


def generate_excel_node(state: OverallState) -> dict:
    print(f"[generate_excel] Writing {len(state['results'])} rows to Excel...")

    path = generate_excel.invoke({
        "results":       state["results"],
        "original_rows": state["rows"],
    })

    print(f"[generate_excel] ✅ Saved → {path}")
    return {}
