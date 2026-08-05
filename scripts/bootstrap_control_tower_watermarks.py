"""Explicit administrator adoption of Phase 3 watermarks from the trusted snapshot.

This is a maintenance/bootstrap/recovery operation only.  It is never an
automatic ordinary-refresh fallback.  It reads the currently published trusted
snapshot, derives each approved model's canonical successful watermark tuple
from trusted snapshot evidence, writes all required watermarks atomically, and
does not move the published pointer or contact Odoo.
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
from src.control_tower.watermarks import bootstrap_watermarks_from_trusted_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Adopt Phase 3 watermarks from the published trusted snapshot"
    )
    parser.add_argument(
        "--company-id",
        type=int,
        default=int(os.getenv("CT_COMPANY_ID", "3")),
        help="Native res.company ID. The office pilot is fixed to company 3.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.company_id != 3:
        raise SystemExit("Control Tower Office Pilot is restricted to company_id=3.")

    pg = PostgresClient()
    try:
        result = bootstrap_watermarks_from_trusted_snapshot(pg, company_id=args.company_id)
    finally:
        pg.close()

    print(json.dumps(result, indent=2, default=str))
    if result.get("pointer_moved") is not False or result.get("odoo_contacted") is not False:
        print("FATAL: watermark adoption must not move the pointer or contact Odoo.")
        return 1
    if result.get("models_missing_evidence"):
        print(
            "WARNING: the trusted snapshot lacks approved model evidence for: "
            + ", ".join(result["models_missing_evidence"])
        )
    print("Watermark adoption completed. Odoo was not contacted and the trusted pointer is unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
