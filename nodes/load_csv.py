import pandas as pd
from state import OverallState
import config


def _safe_row(row: dict) -> dict:
    """Convert any pandas Timestamps (and NaN) to safe Python primitives."""
    result = {}
    for k, v in row.items():
        if isinstance(v, pd.Timestamp):
            result[k] = v.isoformat()          # → "2025-07-29T14:22:35"
        elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
            result[k] = None                   # NaN → None
        else:
            result[k] = v
    return result


def load_csv_node(state: OverallState) -> dict:
    path = state.get("csv_path") or config.CSV_PATH

    if path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    # Strip whitespace from column names to avoid matching issues
    df.columns = df.columns.str.strip()

    # ── Convert every row to safe primitives ──────────────────────────────
    rows = [_safe_row(row) for row in df.to_dict(orient="records")]

    mid = len(rows) // 2
    half1 = rows[:mid]
    half2 = rows[mid:]

    print(f"[load_csv] Loaded {len(rows)} rows → "
          f"Worker 1: {len(half1)} rows | Worker 2: {len(half2)} rows")

    return {
        "rows": rows,
        "half1": half1,
        "half2": half2,
    }