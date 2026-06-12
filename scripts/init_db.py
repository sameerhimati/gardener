"""Create the ClickHouse tables. Run from repo root: .venv/bin/python scripts/init_db.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.core import ch  # noqa: E402

if __name__ == "__main__":
    if not ch.configured():
        print("CLICKHOUSE_URL not set — nothing to do (JSONL fallback active). result=False")
        sys.exit(0)
    result = ch.init_schema()
    print(f"ClickHouse schema initialized (events, lint_findings). result={result}")
