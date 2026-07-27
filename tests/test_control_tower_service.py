from uuid import UUID
from unittest.mock import MagicMock

from src.control_tower.service import (
    ControlTowerService,
    display_document_number,
    json_safe,
)


def test_json_safe_serializes_uuid() -> None:
    value = UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")

    assert json_safe(value) == "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"


def test_json_safe_serializes_nested_uuid() -> None:
    value = {"latest_run": {"run_id": UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")}}

    assert json_safe(value) == {
        "latest_run": {"run_id": "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"}
    }


def test_unassigned_odoo_document_number_is_not_presented_as_a_real_reference() -> None:
    assert display_document_number("/") == "Belum ditemukan"
    assert display_document_number(None) == "Belum ditemukan"
    assert display_document_number("SO2600123") == "SO2600123"


def test_case_contract_keeps_raw_evidence_secondary_to_business_summaries() -> None:
    service = object.__new__(ControlTowerService)
    row = {
        "issue_id": "case-1",
        "rule_id": "SO-CANCEL-001",
        "rule_name": "technical name",
        "validation_status": "MISMATCH",
        "actual_conditions": [{"open_documents_count": 2}],
        "expected_conditions": [{"open_downstream_count": 0}],
        "document_model": "sale.order",
        "document_id": 12,
        "document_number": "/",
        "sop_section": "Cancellation",
        "owner": "Marketing / Warehouse",
        "evidence": [{"source": "graph"}],
        "confidence": "HIGH",
        "severity": "HIGH",
        "raw_record_count": 2,
        "last_checked_at": "2026-07-22T00:00:00+00:00",
    }

    result = service._case_contract(row)

    assert result["primary_document"]["number"] == "Belum ditemukan"
    assert result["actual_summary"].startswith("Dokumen lanjutan")
    assert result["expected_summary"].startswith("Tidak ada dokumen operasional")
    assert result["actual"] == [{"open_documents_count": 2}]


def test_health_does_not_expose_internal_source_binding_metadata() -> None:
    service = object.__new__(ControlTowerService)
    service._row = MagicMock(
        side_effect=[
            {
                "run_id": "run-1",
                "completed_at": "2026-07-22T00:00:00+00:00",
                "model_counts": {
                    "sale.order": 10,
                    "_refresh": {
                        "source_fingerprint": "internal-hash",
                        "source_binding": "stored_fingerprint",
                        "changed_documents": 2,
                    },
                },
            },
            {"snapshot_count": 10},
        ]
    )

    result = service.health()

    public_refresh = result["latest_run"]["model_counts"]["_refresh"]
    assert public_refresh == {"changed_documents": 2}
    assert result["changed_documents"] == 2
