# ─────────────────────────────────────────────
#  config.py  –  only file you need to edit
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()  # This looks for a .env file in the current directory
def get_api_key() -> str:
    """
    Returns the active API key.
    Priority: environment variable set by app.py (user-supplied)
              → fallback to .env file
    """
    return os.environ.get("EVALUATOR_API_KEY") or os.getenv("API_KEY", "")


# Worker 1 — processes first half of CSV
WORKER_1 = {
    "provider": "gemini",
    "model": "gemma-4-31b-it",
    "api_key": get_api_key(),
    # semaphore_limit = how many LLM calls can be in-flight at once.
    # With LLM calls taking ~15-20s and a rate slot every 5s (RPM=12),
    # you need ceil(20/5) = 4 slots to keep the pipeline full.
    # Fewer than that and the rate limiter idles waiting for the semaphore.
    "semaphore_limit": 5,
}

# Worker 2 — processes second half of CSV
WORKER_2 = {
    "provider": "gemini",
    "model": "gemma-4-26b-a4b-it",
    "api_key": get_api_key(),
    "semaphore_limit": 5,
}

# Effective requests per minute per worker sent to the API.
# 12 RPM = 5s gap. Stays 20% below the free-tier 15 RPM ceiling,
# giving headroom for retry re-entries without clipping quota.
RPM_LIMIT = 13

# CSV column names (must match exactly)
DOMAIN_COLUMN  = "Choose your domain below"
PROMPT_COLUMN  = "Submit your Prompt"

# File paths
CSV_PATH       = "submissions.xlsx"
OUTPUT_PATH    = "output/evaluated_results.xlsx"
SCENARIO_DIR   = "scenarios"
CACHE_DIR      = ".eval_cache"

# Scoring thresholds for grade bands
GRADE_BANDS = {
    "Excellent":          (40, 50),
    "Good":               (30, 39),
    "Needs Improvement":  (20, 29),
    "Poor":               (0,  19),
}

# Colour hex values for Excel rows (openpyxl ARGB format)
GRADE_COLOURS = {
    "Excellent":         "C6EFCE",   # soft mint green
    "Good":              "FFEB9C",   # pale buttery yellow
    "Needs Improvement": "FCE4D6",   # light peach/apricot
    "Poor":              "FFC7CE",   # soft pink (not harsh red)
    "Flagged":           "E2E2E2",   # light grey (slightly darker than D9D9D9 for contrast)
}