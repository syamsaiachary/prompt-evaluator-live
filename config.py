# ─────────────────────────────────────────────
#  config.py  –  only file you need to edit
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()


def get_api_key() -> str:
    return os.environ.get("EVALUATOR_API_KEY") or os.getenv("API_KEY", "")


# ── Workers ────────────────────────────────────────────────────────────────────
# Model names use litellm's format: "gemini/<model-id>"
# Google enforces RPM per model independently — each gets its own 15 RPM quota.
# RPM and concurrency are managed inside worker_pool.py.

WORKER_1 = {
    "model":   "gemini/gemma-4-31b-it",
    "api_key": get_api_key(),
}

WORKER_2 = {
    "model":   "gemini/gemma-4-26b-a4b-it",
    "api_key": get_api_key(),
}

# ── CSV columns ────────────────────────────────────────────────────────────────
DOMAIN_COLUMN  = "Choose your domain below"
PROMPT_COLUMN  = "Submit your Prompt"

# ── Paths ──────────────────────────────────────────────────────────────────────
CSV_PATH       = "submissions.xlsx"
OUTPUT_PATH    = "output/evaluated_results.xlsx"
SCENARIO_DIR   = "scenarios"
CACHE_DIR      = ".eval_cache"

# ── Grade bands ────────────────────────────────────────────────────────────────
GRADE_BANDS = {
    "Excellent":          (40, 50),
    "Good":               (30, 39),
    "Needs Improvement":  (20, 29),
    "Poor":               (0,  19),
}

# ── Excel colours (openpyxl ARGB, no leading #) ────────────────────────────────
GRADE_COLOURS = {
    "Excellent":         "C6EFCE",
    "Good":              "FFEB9C",
    "Needs Improvement": "FCE4D6",
    "Poor":              "FFC7CE",
    "Flagged":           "E2E2E2",
}