# ─────────────────────────────────────────────
#  config.py  –  only file you need to edit
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()  # This looks for a .env file in the current directory
api_key = os.getenv("API_KEY")

# Worker 1 — processes first half of CSV
WORKER_1 = {
    "provider": "gemini",
    "model": "gemma-4-31b-it",
    "api_key": api_key,   
    "semaphore_limit": 8,                
}

# Worker 2 — processes second half of CSV
WORKER_2 = {
    "provider": "gemini",
    "model": "gemma-4-26b-a4b-it",
    "api_key": api_key,  
    "semaphore_limit": 8,
}

# Global LLM rate limit (requests per minute)
RPM_LIMIT = 15

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