# ─────────────────────────────────────────────
#  config.py  –  only file you need to edit
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str) -> str:
    return os.environ.get(key) or os.getenv(key, "")


# ── Workers ────────────────────────────────────────────────────────────────────
# model  → litellm model string:  "<provider>/<model-id>"
#   Gemini examples : "gemini/gemma-4-31b-it"
#                     "gemini/gemini-2.0-flash"
#   Groq examples   : "groq/llama-3.3-70b-versatile"
#                     "groq/gemma2-9b-it"
#   OpenAI examples : "openai/gpt-4o-mini"
#
# api_key → matching key for that provider
#   Gemini : GEMINI_API_KEY  (or GOOGLE_API_KEY)
#   Groq   : GROQ_API_KEY
#   OpenAI : OPENAI_API_KEY

WORKER_1 = {
    "model":   "gemini/gemma-4-31b-it",
    "api_key": _env("EVALUATOR_API_KEY") or _env("GEMINI_API_KEY") or _env("API_KEY"),
}

WORKER_2 = {
    "model":   "gemini/gemma-4-26b-a4b-it",
    "api_key": _env("EVALUATOR_API_KEY") or _env("GEMINI_API_KEY") or _env("API_KEY"),
}

# ── To use Groq instead, just swap the two blocks above to e.g.: ──────────────
# WORKER_1 = {
#     "model":   "groq/llama-3.3-70b-versatile",
#     "api_key": _env("EVALUATOR_API_KEY") or _env("GROQ_API_KEY"),
# }
# WORKER_2 = {
#     "model":   "groq/llama-3.1-8b-instant",
#     "api_key": _env("EVALUATOR_API_KEY") or _env("GROQ_API_KEY"),
# }

# ── CSV columns ────────────────────────────────────────────────────────────────
DOMAIN_COLUMN = "Choose your domain below"
PROMPT_COLUMN = "Submit your Prompt"

# ── Paths ──────────────────────────────────────────────────────────────────────
CSV_PATH     = "submissions.xlsx"
OUTPUT_PATH  = "output/evaluated_results.xlsx"
SCENARIO_DIR = "scenarios"
CACHE_DIR    = ".eval_cache"

# ── Grade bands ────────────────────────────────────────────────────────────────
GRADE_BANDS = {
    "Excellent":         (40, 50),
    "Good":              (30, 39),
    "Needs Improvement": (20, 29),
    "Poor":              (0,  19),
}

# ── Excel colours (openpyxl ARGB, no leading #) ────────────────────────────────
GRADE_COLOURS = {
    "Excellent":         "C6EFCE",
    "Good":              "FFEB9C",
    "Needs Improvement": "FCE4D6",
    "Poor":              "FFC7CE",
    "Flagged":           "E2E2E2",
}