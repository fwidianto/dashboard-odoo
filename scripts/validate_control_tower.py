"""Database regression checks untuk Control Tower Health v0.1.

Script ini hanya membaca PostgreSQL dan keluar non-zero bila invariant utama
rusak. Jalankan setelah ``run_control_tower_refresh.py``.
"""

from __future__ import annotations

from pathlib import Path
import sys

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
        "validation_status_vocabulary_is_controlled",
        """
        SELECT COUNT(*) = 0 AS passed
        FROM vw_ct_rule_results
        WHERE validation_status NOT IN (
            'VALIDATED', 'PARTIAL_MATCH', 'MISMATCH',
            'MANUAL_EVIDENCE_REQUIRED', 'DATA_LINKAGE_GAP',
            'VALID_EXCEPTION', 'NOT_TESTED'
        )
        """,
    ),
    (
        "exception_worklist_excludes_validated",
        "SELECT COUNT(*) = 0 AS passed FROM vw_ct_exception_worklist WHERE validation_status = 'VALIDATED'",
    ),
    (
        "payment_rule_not_published_as_record_result",
        "SELECT COUNT(*) = 0 AS passed FROM vw_ct_rule_results WHERE rule_id = 'PAY-001'",
    ),
)


def main() -> int:
    pg = PostgresClient()
    failures: list[str] = []
    try:
        with pg.engine.connect() as conn:
            for name, sql in CHECKS:
                passed = bool(conn.execute(text(sql)).scalar())
                print(f"{'PASS' if passed else 'FAIL'} - {name}")
                if not passed:
                    failures.append(name)
    finally:
        pg.close()

    if failures:
        print("Failed checks: " + ", ".join(failures))
        return 1
    print("All Control Tower v0.1 database checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
