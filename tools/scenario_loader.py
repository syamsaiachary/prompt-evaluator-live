# ─────────────────────────────────────────────
#  tools/scenario_loader.py
#  Tool: get_scenario_context
#  Reads scenario PDFs once at startup, caches in memory.
#  The LLM calls this tool to fetch scenario context.
# ─────────────────────────────────────────────
from __future__ import annotations
import os
import pdfplumber
from langchain_core.tools import tool
from config import SCENARIO_DIR

# ── Cache: loaded once at import time ─────────
_SCENARIO_CACHE: dict[str, str] = {}


def _load_pdfs() -> None:
    """Parse all PDFs in the scenarios/ folder into the in-memory cache."""
    mapping = {
        "technical":     "technical.pdf",
        "non_technical": "non_technical.pdf",
        "non technical": "non_technical.pdf",   # handle space variant
    }
    for key, filename in mapping.items():
        path = os.path.join(SCENARIO_DIR, filename)
        if os.path.exists(path):
            with pdfplumber.open(path) as pdf:
                text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
            _SCENARIO_CACHE[key] = text
        else:
            _SCENARIO_CACHE[key] = f"[Scenario PDF not found: {path}]"


# Load on import so every worker shares the same cache
_load_pdfs()


# ── LangChain Tool Definition ──────────────────
@tool
def get_scenario_context(scenario_type: str) -> str:
    """
    Fetches the full scenario description for the given domain type.

    Args:
        scenario_type: Either 'technical' or 'non_technical'.

    Returns:
        The scenario text that the submitted prompt should address.
    """
    key = scenario_type.lower().strip().replace(" ", "_")
    return _SCENARIO_CACHE.get(key, f"[Unknown scenario type: {scenario_type}]")
