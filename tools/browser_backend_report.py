#!/usr/bin/env python3
"""Print aggregate Camoufox/Cloakbrowser reliability statistics."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import DB_PATH  # noqa: E402
from db.database import DatabaseClient  # noqa: E402


def main():
    """Read browser audit events and print a compact tabular report."""
    with DatabaseClient(DB_PATH) as database:
        database.init_db_papers()
        rows = database.get_browser_backend_summary()
    if not rows:
        print("No browser backend events recorded.")
        return
    print("phase\tpublisher\tbackend\toperation\tattempts\tsuccess\tfallback\tavg_ms")
    for row in rows:
        print(
            f"{row['phase']}\t{row['publisher'] or '-'}\t{row['backend']}\t"
            f"{row['operation']}\t{row['attempts']}\t{row['successes']}\t"
            f"{row['fallback_attempts']}\t{row['average_duration_ms'] or '-'}"
        )


if __name__ == "__main__":
    main()
