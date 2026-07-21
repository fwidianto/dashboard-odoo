"""Export reconciliation diagnostics from the latest Control Tower snapshot.

This script does not fetch Odoo and does not write to Odoo. It only reads the
PostgreSQL read model and writes JSON files under ``output/``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Callable, TypeVar

from sqlalchemy import text


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
    path = OUTPUT_DIR / filename
    path.write_text(
        json.dumps(json_safe(value), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"[SAVE ] {path}", flush=True)


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    service = ControlTowerService()
    try:
        health = stage("Control Tower health", service.health)
        summary = stage("SOP validation summary", service.validation_summary)
        io_health = stage("Internal Order health", lambda: service.io_health(limit=5000))

        exception_rules = (
            "PO-CANCEL-001",
            "SO-CANCEL-001",
            "SO-SOURCE-001",
            "SO-IO-MO-001",
            "IO-PROD-001",
            "IO-UTIL-001",
        )
        exception_samples: dict[str, Any] = {}
        for rule_id in exception_rules:
            exception_samples[rule_id] = stage(
                f"Exception sample {rule_id}",
                lambda rule_id=rule_id: service.exceptions(rule_id=rule_id, limit=100),
            )

        category_rows = stage(
            "Approval category diagnostics",
            lambda: service._rows("""
                SELECT raw_category, normalized_category, record_count
                FROM vw_ct_io_category_diagnostics
                ORDER BY record_count DESC
            """),
        )

        link_counts = stage(
            "Document link distribution",
            lambda: service._rows("""
                SELECT link_type, confidence, COUNT(*) AS link_count
                FROM vw_ct_document_links
                GROUP BY link_type, confidence
                ORDER BY link_count DESC, link_type, confidence
            """),
        )

        status_counts = stage(
            "IO status distribution",
            lambda: service._rows("""
                SELECT
                    production_status,
                    utilization_status,
                    confidence,
                    COUNT(*) AS record_count
                FROM vw_ct_io_health
                GROUP BY production_status, utilization_status, confidence
                ORDER BY record_count DESC
            """),
        )

        save_json("ct_health_v011.json", health)
        save_json("ct_validation_summary_v011.json", summary)
        save_json("ct_io_health_v011.json", io_health)
        save_json("ct_exception_samples_v011.json", exception_samples)
        save_json("ct_io_category_diagnostics_v011.json", category_rows)
        save_json("ct_document_link_counts_v011.json", link_counts)
        save_json("ct_io_status_counts_v011.json", status_counts)

        print("\n=== CONTROL TOWER v0.1.2 ===")
        print(f"Status         : {health.get('status')}")
        print(f"Snapshots      : {health.get('snapshot_count')}")
        print(f"Document links : {health.get('link_count')}")
        print(f"Rule results   : {health.get('rule_result_count')}")
        print(f"Exceptions     : {health.get('exception_count')}")

        print("\n=== SOP VALIDATION SUMMARY ===")
        for row in summary:
            print(
                f"{row['rule_id']:<16} {row['overall_status']:<25} "
                f"tested={row['tested_records']:<6} "
                f"valid={row['validated_records']:<6} "
                f"mismatch={row['mismatch_records']:<6} "
                f"gap={row['linkage_gap_records']:<6} "
                f"partial={row['partial_match_records']:<6}"
            )

        print("\n=== IO CATEGORY DIAGNOSTICS ===")
        for row in category_rows[:15]:
            print(
                f"normalized={str(row.get('normalized_category')):<24} "
                f"count={row.get('record_count')}"
            )

        print("\n[DONE ] Diagnostics saved under output\\")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
