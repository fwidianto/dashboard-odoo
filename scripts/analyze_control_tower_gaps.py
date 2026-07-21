"""Targeted root-cause diagnostics for Control Tower v0.1.1.

Reads only the PostgreSQL Control Tower layer. It does not fetch or write Odoo.
Produces concise JSON reports under output/ for the next rule-hardening pass.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Callable, TypeVar


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.control_tower.service import ControlTowerService, json_safe


T = TypeVar("T")
OUTPUT_DIR = PROJECT_ROOT / "output"


def stage(name: str, function: Callable[[], T]) -> T:
    print(f"[START] {name}", flush=True)
    started = perf_counter()
    result = function()
    print(f"[DONE ] {name} ({perf_counter() - started:.2f}s)", flush=True)
    return result


def save_json(filename: str, value: Any) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(
        json.dumps(json_safe(value), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"[SAVE ] {path}", flush=True)


def main() -> int:
    service = ControlTowerService()
    try:
        io_gap_causes = stage(
            "IO gap cause distribution",
            lambda: service._rows("""
                SELECT
                    rule_id,
                    COALESCE(NULLIF(evidence ->> 'mo_product_uom_mismatch_count', '')::bigint, 0)
                        AS mo_product_uom_mismatch_count,
                    COALESCE(NULLIF(evidence ->> 'so_product_uom_mismatch_count', '')::bigint, 0)
                        AS so_product_uom_mismatch_count,
                    COALESCE(NULLIF(evidence ->> 'multi_io_so_count', '')::bigint, 0)
                        AS multi_io_so_count,
                    COUNT(*) AS record_count
                FROM mv_ct_rule_results
                WHERE rule_id IN ('IO-PROD-001', 'IO-UTIL-001')
                  AND validation_status = 'DATA_LINKAGE_GAP'
                GROUP BY
                    rule_id,
                    COALESCE(NULLIF(evidence ->> 'mo_product_uom_mismatch_count', '')::bigint, 0),
                    COALESCE(NULLIF(evidence ->> 'so_product_uom_mismatch_count', '')::bigint, 0),
                    COALESCE(NULLIF(evidence ->> 'multi_io_so_count', '')::bigint, 0)
                ORDER BY rule_id, record_count DESC
            """),
        )

        io_gap_samples = stage(
            "IO gap samples",
            lambda: service._rows("""
                SELECT
                    rule_id,
                    document_id,
                    document_number,
                    confidence,
                    actual_condition,
                    evidence
                FROM mv_ct_rule_results
                WHERE rule_id IN ('IO-PROD-001', 'IO-UTIL-001')
                  AND validation_status = 'DATA_LINKAGE_GAP'
                ORDER BY rule_id, document_number NULLS LAST, document_id
                LIMIT 200
            """),
        )

        operational_exceptions = stage(
            "Operational exception samples",
            lambda: service._rows("""
                SELECT
                    rule_id,
                    document_model,
                    document_id,
                    document_number,
                    validation_status,
                    severity,
                    confidence,
                    actual_condition,
                    evidence
                FROM mv_ct_exception_worklist
                WHERE rule_id IN (
                    'PO-CANCEL-001',
                    'SO-CANCEL-001',
                    'SO-SOURCE-001',
                    'SO-IO-MO-001'
                )
                ORDER BY
                    CASE rule_id
                        WHEN 'PO-CANCEL-001' THEN 1
                        WHEN 'SO-CANCEL-001' THEN 2
                        WHEN 'SO-SOURCE-001' THEN 3
                        ELSE 4
                    END,
                    document_number NULLS LAST,
                    document_id
                LIMIT 500
            """),
        )

        exception_counts = stage(
            "Exception counts by rule and state",
            lambda: service._rows("""
                SELECT
                    rule_id,
                    validation_status,
                    severity,
                    confidence,
                    COUNT(*) AS record_count
                FROM mv_ct_exception_worklist
                GROUP BY rule_id, validation_status, severity, confidence
                ORDER BY rule_id, validation_status, severity, confidence
            """),
        )

        io_scope = stage(
            "Internal Order scope summary",
            lambda: service._rows("""
                SELECT
                    COUNT(*) AS io_health_rows,
                    COUNT(DISTINCT internal_order_id) AS distinct_internal_orders,
                    COUNT(DISTINCT product_id) AS distinct_products,
                    COUNT(*) FILTER (WHERE production_status = 'DATA_EXCEPTION') AS production_data_exceptions,
                    COUNT(*) FILTER (WHERE utilization_status = 'DATA_EXCEPTION') AS utilization_data_exceptions,
                    COUNT(*) FILTER (WHERE confidence = 'LOW') AS low_confidence_rows,
                    COUNT(*) FILTER (WHERE multi_io_so_count > 0) AS multi_io_rows
                FROM vw_ct_io_health
            """),
        )

        link_quality = stage(
            "Relevant link quality",
            lambda: service._rows("""
                SELECT link_type, confidence, COUNT(*) AS link_count
                FROM vw_ct_document_links
                WHERE link_type IN (
                    'SO_TO_IO',
                    'IO_TO_MO_REFERENCE',
                    'SO_TO_MO_ORIGIN',
                    'PO_TO_RECEIPT',
                    'SO_TO_DELIVERY',
                    'SO_TO_INVOICE'
                )
                GROUP BY link_type, confidence
                ORDER BY link_type, confidence
            """),
        )

        save_json("ct_gap_cause_counts_v011.json", io_gap_causes)
        save_json("ct_io_gap_samples_v011.json", io_gap_samples)
        save_json("ct_operational_exception_samples_v011.json", operational_exceptions)
        save_json("ct_exception_counts_v011.json", exception_counts)
        save_json("ct_io_scope_v011.json", io_scope)
        save_json("ct_relevant_link_quality_v011.json", link_quality)

        print("\n=== IO GAP CAUSE DISTRIBUTION ===")
        for row in io_gap_causes:
            print(
                f"{row['rule_id']:<12} rows={row['record_count']:<5} "
                f"mo_mismatch={row['mo_product_uom_mismatch_count']:<3} "
                f"so_mismatch={row['so_product_uom_mismatch_count']:<3} "
                f"multi_io={row['multi_io_so_count']:<3}"
            )

        print("\n=== IO SCOPE ===")
        for row in io_scope:
            for key, value in row.items():
                print(f"{key:<32}: {value}")

        print("\n=== EXCEPTION COUNTS ===")
        for row in exception_counts:
            print(
                f"{row['rule_id']:<16} {row['validation_status']:<18} "
                f"severity={row['severity']:<7} confidence={row['confidence']:<6} "
                f"count={row['record_count']}"
            )

        print("\n[DONE ] Targeted gap analysis saved under output\\")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
