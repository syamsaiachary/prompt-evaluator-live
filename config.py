# ─────────────────────────────────────────────
#  config.py  –  only file you need to edit
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()


def get_api_key() -> str:
    return os.environ.get("EVALUATOR_API_KEY") or os.getenv("API_KEY", "")


# ── Workers ────────────────────────────────────────────────────────────────────
# Google enforces RPM per MODEL, not per account.
# Each model below gets its own independent 15 RPM quota.
# worker_pool.py runs each at 14 RPM → 28 RPM combined → ~9 min for 250 rows.
#
# If you have TWO Google accounts with separate API keys you can set
# WORKER_1_API_KEY and WORKER_2_API_KEY differently for true isolation.
# With a single account, both keys must be identical — but that's fine
# because the per-model quotas are still separate.

WORKER_1 = {
    "provider":        "gemini",
    "model":           "gemma-4-31b-it",
    "api_key":         get_api_key(),
    # semaphore_limit is now managed inside worker_pool.py (_CONCURRENCY = 4).
    # This field is kept for backwards compatibility but ignored by the pool.
    "semaphore_limit": 7,
}

WORKER_2 = {
    "provider":        "gemini",
    "model":           "gemma-4-26b-a4b-it",
    "api_key":         get_api_key(),
    "semaphore_limit": 7,
}

# RPM_LIMIT is now set inside worker_pool.py (RPM_PER_MODEL = 14).
# Kept here for reference / legacy imports that may read it.
RPM_LIMIT = 14

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