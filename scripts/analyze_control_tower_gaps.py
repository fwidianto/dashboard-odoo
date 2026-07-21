"""Targeted root-cause diagnostics for Control Tower v0.1.2.

Reads only the PostgreSQL Control Tower layer. It does not fetch or write Odoo.
Produces concise JSON reports under output/ for rule and process-owner review.
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
            "IO gap cause buckets",
            lambda: service._rows("""
                WITH gaps AS (
                    SELECT
                        'IO-PROD-001'::text AS rule_id,
                        internal_order_id,
                        COALESCE(
                            NULLIF(evidence ->> 'production_gap_reason', ''),
                            'UNCLASSIFIED'
                        ) AS cause
                    FROM vw_ct_io_health
                    WHERE production_status = 'DATA_EXCEPTION'

                    UNION ALL

                    SELECT
                        'IO-UTIL-001'::text AS rule_id,
                        internal_order_id,
                        COALESCE(
                            NULLIF(evidence ->> 'utilization_gap_reason', ''),
                            'UNCLASSIFIED'
                        ) AS cause
                    FROM vw_ct_io_health
                    WHERE utilization_status = 'DATA_EXCEPTION'
                )
                SELECT
                    rule_id,
                    cause,
                    COUNT(*) AS record_count,
                    COUNT(DISTINCT internal_order_id) AS internal_order_count
                FROM gaps
                GROUP BY rule_id, cause
                ORDER BY rule_id, record_count DESC, cause
            """),
        )

        io_gap_samples = stage(
            "IO gap samples",
            lambda: service._rows("""
                SELECT
                    internal_order_id,
                    internal_order_number,
                    product_id,
                    product_name,
                    uom_id,
                    uom_name,
                    production_status,
                    utilization_status,
                    confidence,
                    mo_count,
                    planned_qty,
                    produced_qty,
                    linked_so_count,
                    multi_io_so_count,
                    utilized_ordered_qty,
                    utilized_delivered_qty,
                    evidence
                FROM vw_ct_io_health
                WHERE production_status = 'DATA_EXCEPTION'
                   OR utilization_status = 'DATA_EXCEPTION'
                ORDER BY internal_order_number NULLS LAST, product_name, product_id
                LIMIT 250
            """),
        )

        io_status_distribution = stage(
            "IO status distribution",
            lambda: service._rows("""
                SELECT
                    production_status,
                    utilization_status,
                    confidence,
                    COUNT(*) AS record_count,
                    COUNT(DISTINCT internal_order_id) AS internal_order_count
                FROM vw_ct_io_health
                GROUP BY production_status, utilization_status, confidence
                ORDER BY record_count DESC, production_status, utilization_status, confidence
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

        source_gap_causes = stage(
            "SO source gap cause buckets",
            lambda: service._rows("""
                SELECT
                    COALESCE(
                        NULLIF(evidence ->> 'source_gap_reason', ''),
                        'UNCLASSIFIED'
                    ) AS cause,
                    actual_condition ->> 'source_type' AS source_type,
                    confidence,
                    COUNT(*) AS record_count,
                    COUNT(DISTINCT document_id) AS document_count
                FROM mv_ct_rule_results
                WHERE rule_id = 'SO-SOURCE-001'
                  AND validation_status = 'DATA_LINKAGE_GAP'
                GROUP BY 1, 2, 3
                ORDER BY record_count DESC, cause, source_type NULLS FIRST
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
                    COUNT(*) AS record_count,
                    COUNT(DISTINCT document_id) AS document_count
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
                    COUNT(*) FILTER (WHERE production_status = 'DATA_EXCEPTION')
                        AS production_data_exceptions,
                    COUNT(*) FILTER (WHERE utilization_status = 'DATA_EXCEPTION')
                        AS utilization_data_exceptions,
                    COUNT(*) FILTER (WHERE confidence = 'LOW') AS low_confidence_rows,
                    COUNT(*) FILTER (WHERE multi_io_so_count > 0) AS ambiguous_multi_io_rows,
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            NULLIF(evidence ->> 'non_matching_linked_so_line_count', '')::bigint,
                            0
                        ) > 0
                    ) AS mixed_source_context_rows
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

        save_json("ct_gap_cause_counts_v012.json", io_gap_causes)
        save_json("ct_io_gap_samples_v012.json", io_gap_samples)
        save_json("ct_io_status_distribution_v012.json", io_status_distribution)
        save_json("ct_operational_exception_samples_v012.json", operational_exceptions)
        save_json("ct_so_source_gap_cause_counts_v012.json", source_gap_causes)
        save_json("ct_exception_counts_v012.json", exception_counts)
        save_json("ct_io_scope_v012.json", io_scope)
        save_json("ct_relevant_link_quality_v012.json", link_quality)

        print("\n=== IO GAP CAUSE BUCKETS ===")
        if not io_gap_causes:
            print("No IO DATA_LINKAGE_GAP rows remain.")
        for row in io_gap_causes:
            print(
                f"{row['rule_id']:<12} {row['cause']:<44} "
                f"rows={row['record_count']:<5} io={row['internal_order_count']}"
            )

        print("\n=== IO SCOPE ===")
        for row in io_scope:
            for key, value in row.items():
                print(f"{key:<34}: {value}")

        print("\n=== EXCEPTION COUNTS ===")
        for row in exception_counts:
            print(
                f"{row['rule_id']:<16} {row['validation_status']:<18} "
                f"severity={row['severity']:<7} confidence={row['confidence']:<6} "
                f"rows={row['record_count']:<5} documents={row['document_count']}"
            )

        print("\n=== SO SOURCE GAP CAUSES ===")
        for row in source_gap_causes:
            print(
                f"{row['cause']:<38} source={str(row['source_type']):<18} "
                f"rows={row['record_count']:<5} documents={row['document_count']}"
            )

        print("\n[DONE ] Targeted v0.1.2 analysis saved under output\\")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
