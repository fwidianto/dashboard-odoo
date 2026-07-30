"""Explicit administrator recovery for stale Control Tower candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient
from src.control_tower.refresh import recover_stale_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Abort one stale Control Tower candidate.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--requested-by", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    parser.add_argument(
        "--confirm",
        choices=("ABORT",),
        required=True,
        help="Explicit administrator intent. Use --confirm ABORT.",
    )
    args = parser.parse_args()

    pg = PostgresClient()
    try:
        result = recover_stale_run(
            pg,
            run_id=args.run_id,
            requested_by=args.requested_by[:80],
            reason=args.reason,
            max_age_minutes=args.max_age_minutes,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
