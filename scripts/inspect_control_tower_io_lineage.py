"""Inspect one Internal Order against linked Manufacturing Orders.

This diagnostic reads only the completed PostgreSQL Control Tower snapshot. It does not
fetch from or write to Odoo. The output makes product/UoM mismatches explicit without
inventing quantity allocations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.control_tower.service import ControlTowerService, json_safe


OUTPUT_DIR = PROJECT_ROOT / "output"


def build_match_matrix(
    io_lines: list[dict[str, Any]],
    manufacturing_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return exact product/UoM matches and unmatched records.

    A match is accepted only when both native product IDs and native UoM IDs are present
    and equal. Quantities are reported but never allocated by this diagnostic.
    """

    line_matches: list[dict[str, Any]] = []
    matched_mo_ids: set[int] = set()

    for line in io_lines:
        product_id = line.get("product_id")
        uom_id = line.get("uom_id")
        exact_matches = [
            mo
            for mo in manufacturing_orders
            if product_id is not None
            and uom_id is not None
            and mo.get("product_id") == product_id
            and mo.get("uom_id") == uom_id
        ]
        matched_mo_ids.update(
            mo["manufacturing_order_id"]
            for mo in exact_matches
            if mo.get("manufacturing_order_id") is not None
        )
        line_matches.append(
            {
                "approval_line_id": line.get("approval_line_id"),
                "product_id": product_id,
                "product_name": line.get("product_name"),
                "uom_id": uom_id,
                "uom_name": line.get("uom_name"),
                "requested_qty": line.get("requested_qty"),
                "exact_match_count": len(exact_matches),
                "exact_matches": exact_matches,
            }
        )

    unmatched_io_lines = [row for row in line_matches if row["exact_match_count"] == 0]
    unmatched_manufacturing_orders = [
        mo
        for mo in manufacturing_orders
        if mo.get("manufacturing_order_id") not in matched_mo_ids
    ]

    return {
        "matching_basis": "EXACT_NATIVE_PRODUCT_ID_AND_UOM_ID",
        "quantity_allocation_performed": False,
        "io_line_count": len(io_lines),
        "manufacturing_order_count": len(manufacturing_orders),
        "matched_io_line_count": len(line_matches) - len(unmatched_io_lines),
        "unmatched_io_line_count": len(unmatched_io_lines),
        "unmatched_manufacturing_order_count": len(unmatched_manufacturing_orders),
        "line_matches": line_matches,
        "unmatched_io_lines": unmatched_io_lines,
        "unmatched_manufacturing_orders": unmatched_manufacturing_orders,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect one Internal Order and its linked MOs using the completed "
            "PostgreSQL Control Tower snapshot."
        )
    )
    parser.add_argument(
        "--io",
        required=True,
        dest="io_number",
        help="Internal Order number, for example 125IO015.",
    )
    return parser.parse_args()


def output_filename(io_number: str) -> str:
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "_", io_number.strip())
    return f"ct_io_lineage_{safe_number}.json"


def main() -> int:
    args = parse_args()
    io_number = args.io_number.strip()
    service = ControlTowerService()

    try:
        io_candidates = service._rows(
            """
            SELECT DISTINCT
                link.parent_id AS internal_order_id,
                link.parent_number AS internal_order_number,
                root.state AS internal_order_state
            FROM vw_ct_document_links link
            LEFT JOIN vw_ct_native_record_snapshot_current root
              ON root.model = 'approval.request'
             AND root.record_id = link.parent_id
            WHERE link.link_type = 'APPROVAL_TO_LINE'
              AND UPPER(BTRIM(link.parent_number)) = UPPER(BTRIM(:io_number))
            ORDER BY link.parent_id
            """,
            {"io_number": io_number},
        )

        if not io_candidates:
            print(f"[ERROR] Internal Order {io_number!r} was not found in the current snapshot.")
            return 2
        if len(io_candidates) > 1:
            print(
                f"[ERROR] Internal Order number {io_number!r} resolves to multiple native IDs: "
                f"{[row['internal_order_id'] for row in io_candidates]}"
            )
            return 3

        io_header = io_candidates[0]
        io_id = io_header["internal_order_id"]

        io_lines = service._rows(
            """
            SELECT
                link.child_id AS approval_line_id,
                NULLIF(line.payload #>> '{product_id,id}', '')::bigint AS product_id,
                line.payload #>> '{product_id,name}' AS product_name,
                NULLIF(line.payload #>> '{product_uom_id,id}', '')::bigint AS uom_id,
                line.payload #>> '{product_uom_id,name}' AS uom_name,
                COALESCE(NULLIF(line.payload ->> 'quantity', '')::numeric, 0)
                    AS requested_qty,
                line.payload ->> 'x_studio_category' AS category_raw
            FROM vw_ct_document_links link
            JOIN vw_ct_native_record_snapshot_current line
              ON line.model = 'approval.product.line'
             AND line.record_id = link.child_id
            WHERE link.link_type = 'APPROVAL_TO_LINE'
              AND link.parent_id = :io_id
              AND UPPER(BTRIM(COALESCE(line.payload ->> 'x_studio_category', '')))
                    = 'MANUFACTURE'
            ORDER BY link.child_id
            """,
            {"io_id": io_id},
        )

        manufacturing_orders = service._rows(
            """
            SELECT
                link.child_id AS manufacturing_order_id,
                link.child_number AS manufacturing_order_number,
                mo.state AS manufacturing_order_state,
                NULLIF(mo.payload #>> '{product_id,id}', '')::bigint AS product_id,
                mo.payload #>> '{product_id,name}' AS product_name,
                NULLIF(mo.payload #>> '{product_uom_id,id}', '')::bigint AS uom_id,
                mo.payload #>> '{product_uom_id,name}' AS uom_name,
                COALESCE(NULLIF(mo.payload ->> 'product_qty', '')::numeric, 0)
                    AS planned_qty,
                COALESCE(NULLIF(mo.payload ->> 'qty_produced', '')::numeric, 0)
                    AS produced_qty,
                mo.payload ->> 'origin' AS origin,
                mo.payload ->> 'x_studio_nomor_io' AS io_reference_raw,
                mo.payload ->> 'x_studio_nomor_jo' AS jo_reference_raw,
                link.confidence AS link_confidence
            FROM vw_ct_document_links link
            JOIN vw_ct_native_record_snapshot_current mo
              ON mo.model = 'mrp.production'
             AND mo.record_id = link.child_id
            WHERE link.link_type = 'IO_TO_MO_REFERENCE'
              AND link.parent_id = :io_id
            ORDER BY link.child_number NULLS LAST, link.child_id
            """,
            {"io_id": io_id},
        )

        health_rows = service._rows(
            """
            SELECT
                internal_order_id,
                internal_order_number,
                product_id,
                product_name,
                uom_id,
                uom_name,
                requested_qty,
                mo_count,
                planned_qty,
                produced_qty,
                production_status,
                utilization_status,
                confidence,
                evidence
            FROM vw_ct_io_health
            WHERE internal_order_id = :io_id
            ORDER BY product_name NULLS LAST, product_id, uom_id
            """,
            {"io_id": io_id},
        )

        matching = build_match_matrix(io_lines, manufacturing_orders)
        report = {
            "scope": {
                "source": "COMPLETED_POSTGRESQL_CONTROL_TOWER_SNAPSHOT",
                "odoo_fetch_performed": False,
                "odoo_write_back_performed": False,
                "company_scope": "PT Nobi Putra Angkasa",
            },
            "internal_order": io_header,
            "io_lines": io_lines,
            "manufacturing_orders": manufacturing_orders,
            "exact_product_uom_matching": matching,
            "current_io_health_rows": health_rows,
        }

        OUTPUT_DIR.mkdir(exist_ok=True)
        path = OUTPUT_DIR / output_filename(io_number)
        path.write_text(
            json.dumps(json_safe(report), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        print(f"\n=== INTERNAL ORDER {io_number} ===")
        print(f"Native ID                    : {io_id}")
        print(f"State                        : {io_header.get('internal_order_state')}")
        print(f"IO manufacture lines         : {matching['io_line_count']}")
        print(f"Linked manufacturing orders  : {matching['manufacturing_order_count']}")
        print(f"Unmatched IO lines           : {matching['unmatched_io_line_count']}")
        print(
            "Unmatched manufacturing MOs  : "
            f"{matching['unmatched_manufacturing_order_count']}"
        )
        print("Quantity allocation performed: NO")

        print("\n=== UNMATCHED IO LINES ===")
        if not matching["unmatched_io_lines"]:
            print("None")
        for row in matching["unmatched_io_lines"]:
            print(
                f"line={row['approval_line_id']} product={row['product_name']} "
                f"[id={row['product_id']}] uom={row['uom_name']} [id={row['uom_id']}] "
                f"qty={row['requested_qty']}"
            )

        print("\n=== UNMATCHED MANUFACTURING ORDERS ===")
        if not matching["unmatched_manufacturing_orders"]:
            print("None")
        for row in matching["unmatched_manufacturing_orders"]:
            print(
                f"mo={row['manufacturing_order_number']} "
                f"[id={row['manufacturing_order_id']}] product={row['product_name']} "
                f"[id={row['product_id']}] uom={row['uom_name']} [id={row['uom_id']}] "
                f"planned={row['planned_qty']} produced={row['produced_qty']} "
                f"state={row['manufacturing_order_state']}"
            )

        print(f"\n[SAVE] {path}")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
