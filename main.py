# ─────────────────────────────────────────────
#  main.py  –  Entry point
#  Usage:  python main.py
#          python main.py --csv path/to/file.xlsx
# ─────────────────────────────────────────────
from __future__ import annotations
import asyncio
import argparse
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from graph import build_graph
from config import CSV_PATH

async def run(csv_path: str) -> None:
    import config
    config.CSV_PATH = csv_path
    
    os.makedirs(config.CACHE_DIR, exist_ok=True)

    start = time.perf_counter()
    print("=" * 60)
    print("  Prompt Evaluator  –  Starting")
    print("=" * 60)

    graph = build_graph()
    await graph.ainvoke({"half1": [], "half2": [], "results": [], "rows": []})

    elapsed = time.perf_counter() - start
    mins, secs = divmod(int(elapsed), 60)
    print("=" * 60)
    print(f"  ✅ Done in {mins}m {secs}s")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt Evaluator")
    parser.add_argument(
        "--csv", default=CSV_PATH,
        help="Path to submissions CSV/Excel (default: submissions.csv)"
    )
    args = parser.parse_args()
    asyncio.run(run(args.csv))


if __name__ == "__main__":
    main()