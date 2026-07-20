"""Refresh read-only Control Tower Health v0.1.

Contoh:
    python scripts/run_control_tower_refresh.py
    python scripts/run_control_tower_refresh.py --extract-only
    python scripts/run_control_tower_refresh.py --sql-only
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient
from src.control_tower.relation_extractor import ControlTowerRelationExtractor


SQL_PATH = PROJECT_ROOT / "sql" / "09_control_tower_sop_validation_v0.sql"


def apply_sql(pg: PostgresClient, sql_path: Path = SQL_PATH) -> None:
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    sql = sql_path.read_text(encoding="utf-8")
    raw = pg.engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Control Tower Health v0.1")
    parser.add_argument(
        "--company-id",
        type=int,
        default=int(os.getenv("CT_COMPANY_ID", "3")),
        help="Native res.company ID. Default: CT_COMPANY_ID or 3.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("CT_BATCH_SIZE", "500")),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--extract-only", action="store_true")
    mode.add_argument("--sql-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pg = PostgresClient()
    extractor = ControlTowerRelationExtractor(
        postgres_client=pg,
        company_id=args.company_id,
        batch_size=args.batch_size,
    )
    try:
        if not args.sql_only:
            result = extractor.run()
            print(json.dumps(result, indent=2, default=str))
        else:
            extractor.ensure_schema()

        if not args.extract_only:
            apply_sql(pg)
            print(f"Applied SQL read model: {SQL_PATH}")

        print("Control Tower refresh completed. Odoo remained read-only.")
        return 0
    finally:
        extractor.close()


if __name__ == "__main__":
    raise SystemExit(main())
