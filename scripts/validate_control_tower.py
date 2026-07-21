"""Database regression checks untuk Control Tower Health v0.1.

Script ini hanya membaca PostgreSQL dan keluar non-zero bila invariant utama
rusak. Jalankan setelah ``run_control_tower_refresh.py``.
"""

from __future__ import annotations

from pathlib import Path
import sys
from time import perf_counter

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient


CHECKS = (
    ("latest_completed_run_exists", "SELECT COUNT(*) = 1 AS passed FROM vw_ct_current_run"),
    ("current_snapshot_not_empty", "SELECT COUNT(*) > 0 AS passed FROM vw_ct_native_record_snapshot_current"),
    (
        "so_to_io_direction_is_correct",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM vw_ct_document_links
        WHERE link_type = 'SO_TO_IO'
          AND (parent_model <> 'sale.order' OR child_model <> 'approval.request')
        """,
    ),
    (
        "high_confidence_links_are_not_dangling",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM vw_ct_document_links link
        LEFT JOIN vw_ct_native_record_snapshot_current parent
          ON parent.model = link.parent_model AND parent.record_id = link.parent_id
        LEFT JOIN vw_ct_native_record_snapshot_current child
          ON child.model = link.child_model AND child.record_id = link.child_id
        WHERE link.confidence = 'HIGH'
          AND (parent.record_id IS NULL OR child.record_id IS NULL)
        """,
    ),
    (
        "materialized_document_paths_not_empty",
        "SELECT COUNT(*) > 0 AS passed FROM mv_ct_document_paths",
    ),
    (
        "materialized_rule_results_not_empty",
        "SELECT COUNT(*) > 0 AS passed FROM mv_ct_rule_results",
    ),
    (
        "io_health_not_empty",
        "SELECT COUNT(*) > 0 AS passed FROM vw_ct_io_health",
    ),
    (
        "io_lineage_version_is_current",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM vw_ct_io_health
        WHERE COALESCE(evidence ->> 'lineage_version', '') <> 'v0.1.2'
        """,
    ),
    (
        "io_production_gap_has_line_local_reason",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM mv_ct_rule_results
        WHERE rule_id = 'IO-PROD-001'
          AND validation_status = 'DATA_LINKAGE_GAP'
          AND COALESCE(NULLIF(evidence ->> 'mo_product_uom_mismatch_count', '')::bigint, 0) = 0
          AND actual_condition ->> 'product_id' IS NOT NULL
          AND actual_condition ->> 'uom_id' IS NOT NULL
        """,
    ),
    (
        "io_utilization_gap_has_line_level_ambiguity",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM mv_ct_rule_results
        WHERE rule_id = 'IO-UTIL-001'
          AND validation_status = 'DATA_LINKAGE_GAP'
          AND COALESCE(NULLIF(evidence ->> 'ambiguous_so_line_count', '')::bigint, 0) = 0
          AND actual_condition ->> 'product_id' IS NOT NULL
          AND actual_condition ->> 'uom_id' IS NOT NULL
        """,
    ),
    (
        "mixed_source_lines_are_not_io_mismatches",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM vw_ct_io_health
        WHERE COALESCE(NULLIF(evidence ->> 'so_product_uom_mismatch_count', '')::bigint, 0) <> 0
        """,
    ),
    (
        "validation_status_vocabulary_is_controlled",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM mv_ct_rule_results
        WHERE validation_status NOT IN (
            'VALIDATED', 'PARTIAL_MATCH', 'MISMATCH',
            'MANUAL_EVIDENCE_REQUIRED', 'DATA_LINKAGE_GAP',
            'VALID_EXCEPTION', 'NOT_TESTED'
        )
        """,
    ),
    (
        "so_cancel_excludes_technical_descendants",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM mv_ct_rule_results result
        CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS(
            COALESCE(result.actual_condition -> 'open_documents', '[]'::jsonb)
        ) document
        WHERE result.rule_id = 'SO-CANCEL-001'
          AND document ->> 'model' NOT IN (
              'mrp.production', 'stock.picking', 'purchase.order', 'account.move'
          )
        """,
    ),
    (
        "active_io_mo_is_review_signal_not_mismatch",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM mv_ct_rule_results
        WHERE rule_id = 'SO-IO-MO-001'
          AND validation_status = 'MISMATCH'
        """,
    ),
    (
        "exception_worklist_excludes_validated",
        "SELECT COUNT(*) = 0 AS passed FROM mv_ct_exception_worklist WHERE validation_status = 'VALIDATED'",
    ),
    (
        "payment_rule_not_published_as_record_result",
        "SELECT COUNT(*) = 0 AS passed FROM mv_ct_rule_results WHERE rule_id = 'PAY-001'",
    ),
)


def main() -> int:
    pg = PostgresClient()
    failures: list[str] = []
    try:
        with pg.engine.connect() as conn:
            for name, sql in CHECKS:
                started = perf_counter()
                passed = bool(conn.execute(text(sql)).scalar())
                duration = perf_counter() - started
                print(f"{'PASS' if passed else 'FAIL'} - {name} ({duration:.2f}s)", flush=True)
                if not passed:
                    failures.append(name)
    finally:
        pg.close()

    if failures:
        print("Failed checks: " + ", ".join(failures))
        return 1
    print("All Control Tower v0.1.2 database checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
