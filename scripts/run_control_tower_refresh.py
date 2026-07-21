"""Refresh read-only Control Tower Health v0.1.

Contoh:
    python scripts/run_control_tower_refresh.py
    python scripts/run_control_tower_refresh.py --extract-only
    python scripts/run_control_tower_refresh.py --sql-only
    python scripts/run_control_tower_refresh.py --io-hardening-only
    python scripts/run_control_tower_refresh.py --po-scope-only
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient
from src.control_tower.relation_extractor import ControlTowerRelationExtractor


BASE_SQL_PATHS = (
    PROJECT_ROOT / "sql" / "09_control_tower_sop_validation_v0.sql",
    PROJECT_ROOT / "sql" / "10_control_tower_runtime_hardening_v01.sql",
)
IO_HARDENING_SQL_PATH = (
    PROJECT_ROOT / "sql" / "11_control_tower_io_lineage_hardening_v012.sql"
)
PO_SCOPE_SQL_PATH = PROJECT_ROOT / "sql" / "12_control_tower_po_2026_scope.sql"
SQL_PATHS = (*BASE_SQL_PATHS, IO_HARDENING_SQL_PATH, PO_SCOPE_SQL_PATH)


def apply_sql(pg: PostgresClient, sql_path: Path) -> None:
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")

    print(f"[START] Applying SQL: {sql_path.name}", flush=True)
    started = perf_counter()
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

    duration = perf_counter() - started
    print(f"[DONE ] Applied SQL: {sql_path.name} ({duration:.2f} seconds)", flush=True)


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
    mode.add_argument(
        "--io-hardening-only",
        action="store_true",
        help="Apply only v0.1.2 IO lineage SQL to the existing completed snapshot.",
    )
    mode.add_argument(
        "--po-scope-only",
        action="store_true",
        help="Apply only the PO 2026+ scope SQL to the existing completed snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pg = PostgresClient()
    extractor: ControlTowerRelationExtractor | None = None
    try:
        if args.po_scope_only:
            print("[INFO ] Reusing latest COMPLETED extraction; Odoo will not be fetched.", flush=True)
            apply_sql(pg, PO_SCOPE_SQL_PATH)
            print("Control Tower PO scope refresh completed. Odoo was not contacted.")
            return 0

        extractor = ControlTowerRelationExtractor(
            postgres_client=pg,
            company_id=args.company_id,
            batch_size=args.batch_size,
        )
        if not args.sql_only and not args.io_hardening_only:
            result = extractor.run()
            print(json.dumps(result, indent=2, default=str))
        else:
            extractor.ensure_schema()
            print("[INFO ] Reusing latest COMPLETED extraction; Odoo will not be fetched.", flush=True)

        if args.io_hardening_only:
            apply_sql(pg, IO_HARDENING_SQL_PATH)
        elif not args.extract_only:
            for sql_path in SQL_PATHS:
                apply_sql(pg, sql_path)

        print("Control Tower refresh completed. Odoo remained read-only.")
        return 0
    finally:
        if extractor is not None:
            extractor.close()
        else:
            pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
