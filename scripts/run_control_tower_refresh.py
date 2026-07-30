"""Safe Control Tower refresh and read-model maintenance commands."""

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
from src.control_tower.refresh import (
    SQL_PATHS,
    ensure_refresh_schema,
    run_refresh_pipeline,
)
from src.control_tower.relation_extractor import ControlTowerRelationExtractor


IO_HARDENING_SQL_PATH = PROJECT_ROOT / "sql" / "11_control_tower_io_lineage_hardening_v012.sql"
PO_SCOPE_SQL_PATH = PROJECT_ROOT / "sql" / "12_control_tower_po_2026_scope.sql"
TEMUAN_SQL_PATH = PROJECT_ROOT / "sql" / "13_control_tower_temuan_v01.sql"


def apply_sql_bundle(pg: PostgresClient, sql_paths: tuple[Path, ...]) -> dict[str, float]:
    """Apply maintenance SQL in one transaction without changing the snapshot pointer."""
    timings: dict[str, float] = {}
    with pg.engine.begin() as conn:
        for sql_path in sql_paths:
            if not sql_path.exists():
                raise FileNotFoundError(f"SQL file not found: {sql_path}")
            started = perf_counter()
            conn.exec_driver_sql(sql_path.read_text(encoding="utf-8"))
            timings[sql_path.name] = round(perf_counter() - started, 3)
            print(f"[DONE ] Applied SQL: {sql_path.name} ({timings[sql_path.name]:.2f} seconds)", flush=True)
    return timings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe Control Tower refresh")
    parser.add_argument(
        "--company-id",
        type=int,
        default=int(os.getenv("CT_COMPANY_ID", "3")),
        help="Native res.company ID. The office pilot is fixed to company 3.",
    )
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("CT_BATCH_SIZE", "500")))
    parser.add_argument(
        "--requested-by",
        default=os.getenv("CT_REFRESH_REQUESTED_BY", "cli"),
        help="Audit actor label; never place credentials here.",
    )
    parser.add_argument(
        "--trigger",
        choices=("manual", "scheduled", "recovery"),
        default=os.getenv("CT_REFRESH_TRIGGER", "manual"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--extract-only",
        action="store_true",
        help="Extract a candidate and leave it READY_FOR_PUBLISH; do not rebuild or promote read models.",
    )
    mode.add_argument(
        "--sql-only",
        action="store_true",
        help="Rebuild read models from the existing trusted pointer; no Odoo extraction or promotion.",
    )
    mode.add_argument(
        "--io-hardening-only",
        action="store_true",
        help="Apply only IO lineage SQL to the existing trusted pointer; no Odoo extraction.",
    )
    mode.add_argument(
        "--po-scope-only",
        action="store_true",
        help="Apply only PO scope SQL to the existing trusted pointer; no Odoo extraction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.company_id != 3:
        raise SystemExit("Control Tower Office Pilot is restricted to company_id=3.")

    if not args.extract_only and not args.sql_only and not args.io_hardening_only and not args.po_scope_only:
        result = run_refresh_pipeline(
            company_id=args.company_id,
            batch_size=args.batch_size,
            trigger=args.trigger,
            requested_by=args.requested_by,
        )
        print(json.dumps(result, indent=2, default=str))
        print("Control Tower refresh completed and published atomically. Odoo remained read-only.")
        return 0

    pg = PostgresClient()
    extractor: ControlTowerRelationExtractor | None = None
    try:
        extractor = ControlTowerRelationExtractor(
            postgres_client=pg,
            company_id=args.company_id,
            batch_size=args.batch_size,
        )
        extractor.ensure_schema()
        ensure_refresh_schema(pg)

        if args.extract_only:
            result = extractor.run(
                trigger=args.trigger,
                requested_by=args.requested_by,
            )
            print(json.dumps(result, indent=2, default=str))
            print("Candidate extraction completed. It was not promoted.")
            return 0

        if args.io_hardening_only:
            paths = (IO_HARDENING_SQL_PATH,)
        elif args.po_scope_only:
            paths = (PO_SCOPE_SQL_PATH,)
        else:
            paths = SQL_PATHS

        print("[INFO ] Reusing the existing trusted snapshot; Odoo was not contacted.", flush=True)
        timings = apply_sql_bundle(pg, tuple(paths))
        print(json.dumps({"status": "SQL_ONLY", "stage_timings": timings}, indent=2))
        print("Control Tower SQL maintenance completed without candidate promotion.")
        return 0
    finally:
        if extractor is not None:
            extractor.close()
        else:
            pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
