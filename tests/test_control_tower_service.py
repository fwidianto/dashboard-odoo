from uuid import UUID

from src.control_tower.service import (
    ControlTowerService,
    json_safe,
    presentation_category_for_status,
    process_key_for,
    supported_destination,
)


def test_json_safe_serializes_uuid() -> None:
    value = UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")

    assert json_safe(value) == "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"


def test_json_safe_serializes_nested_uuid() -> None:
    value = {"latest_run": {"run_id": UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")}}

    assert json_safe(value) == {
        "latest_run": {"run_id": "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"}
    }


def test_presentation_category_mapping_excludes_healthy_and_not_tested() -> None:
    assert presentation_category_for_status("MISMATCH") == "MASALAH_AKTIF"
    assert presentation_category_for_status("DATA_LINKAGE_GAP") == "PERLU_DITINJAU"
    assert presentation_category_for_status("PARTIAL_MATCH") == "PERLU_DITINJAU"
    assert presentation_category_for_status("MANUAL_EVIDENCE_REQUIRED") == "PERLU_DITINJAU"
    assert presentation_category_for_status("DATA_EXCEPTION") == "PERLU_DITINJAU"
    assert presentation_category_for_status("VALIDATED") is None
    assert presentation_category_for_status("NOT_TESTED") is None


def test_process_mapping_requires_supported_rule_and_model_pair() -> None:
    assert process_key_for("SO-SOURCE-001", "sale.order") == "sales-order"
    assert process_key_for("IO-PROD-001", "approval.request") == "internal-order"
    assert process_key_for("PO-CANCEL-001", "purchase.order") == "material-purchase-order"
    assert process_key_for("JO-DIST-001", "job.order") is None


def test_supported_destinations_keep_unsupported_models_empty() -> None:
    assert supported_destination(
        affected_model="sale.order", document_id=42, document_number="SO0042"
    ) == ("/dashboard/sales-orders?sales_order_id=42", "Sales Order Traceability")
    assert supported_destination(
        affected_model="approval.request", document_id=116, document_number="125IO015"
    ) == (
        "/dashboard/internal-order-rekap?internal_order_number=125IO015",
        "Order Material Tracking",
    )
    assert supported_destination(
        affected_model="purchase.order", document_id=7, document_number="PO0007"
    ) == (None, None)
    assert supported_destination(
        affected_model="mrp.production", document_id=8, document_number="MO0008"
    ) == (None, None)


class _FakeEvidenceService(ControlTowerService):
    def __init__(self) -> None:
        self.calls = []

    def _row(self, sql, params=None):
        self.calls.append((sql, params))
        if "COUNT(*) FILTER" in sql:
            return {"masalah_aktif": 4, "perlu_ditinjau": 5, "data_belum_lengkap": 0}
        return {"total": 3}

    def _rows(self, sql, params=None):
        self.calls.append((sql, params))
        if "GROUP BY" in sql:
            return [{
                "rule_id": "SO-CANCEL-001",
                "document_model": "sale.order",
                "validation_status": "MISMATCH",
                "total": 3,
            }]
        return [{
            "evidence_key": "evidence-1",
            "issue_id": "issue-1",
            "source_kind": "mv_ct_exception_worklist",
            "rule_id": "SO-CANCEL-001",
            "source_rule_id": "SO-CANCEL-001",
            "affected_model": "sale.order",
            "affected_document_id": 42,
            "native_document_reference": "SO0042",
            "validation_status": "MISMATCH",
            "severity": "HIGH",
            "confidence": "HIGH",
            "actual_condition": {},
            "evidence": {},
        }]

    def validation_summary(self):
        return [{"rule_id": "SO-CANCEL-001", "overall_status": "MISMATCH"}]


class _FakeTemuanDestinationService(ControlTowerService):
    rows = [
        {
            "evidence_key": "mo-1",
            "source_kind": "mv_ct_exception_worklist",
            "presentation_category": "MASALAH_AKTIF",
            "rule_id": "SO-IO-MO-001",
            "source_rule_id": "SO-IO-MO-001",
            "affected_model": "mrp.production",
            "document_id": 8,
            "document_number": "MO0008",
            "validation_status": "MISMATCH",
            "severity": "HIGH",
            "confidence": "HIGH",
        },
        {
            "evidence_key": "po-1",
            "source_kind": "mv_ct_exception_worklist",
            "presentation_category": "MASALAH_AKTIF",
            "rule_id": "PO-CANCEL-001",
            "source_rule_id": "PO-CANCEL-001",
            "affected_model": "purchase.order",
            "document_id": 7,
            "document_number": "PO0007",
            "validation_status": "MISMATCH",
            "severity": "HIGH",
            "confidence": "HIGH",
        },
    ]

    def _rows(self, sql, params=None):
        if "GROUP BY presentation_category" in sql or "SELECT DISTINCT" in sql:
            return []
        if "FROM evidence" in sql:
            return list(self.rows)
        return []

    def _row(self, sql, params=None):
        if "COUNT(*) AS total" in sql:
            return {"total": len(self.rows)}
        return {}

    def validation_summary(self):
        return []


def test_unsupported_temuan_destinations_explain_without_urls() -> None:
    result = _FakeTemuanDestinationService().temuan(
        presentation_category="MASALAH_AKTIF"
    )

    assert {row["affected_model"] for row in result["rows"]} == {
        "mrp.production",
        "purchase.order",
    }
    for row in result["rows"]:
        assert row["destination_url"] is None
        assert row["destination_label"] is None
        assert row["destination_supported"] is False
        assert row["unsupported_destination_reason"] == (
            "No exact compatible investigation page is available for this document."
        )


def test_evidence_uses_authoritative_total_and_offset() -> None:
    service = _FakeEvidenceService()

    result = service.evidence(
        presentation_category="MASALAH_AKTIF", limit=2, offset=4
    )

    assert result["total"] == 3
    assert result["limit"] == 2
    assert result["offset"] == 4
    assert result["category_counts"] == {
        "MASALAH_AKTIF": 4,
        "PERLU_DITINJAU": 5,
        "DATA_BELUM_LENGKAP": 0,
    }
    assert result["rows"][0]["presentation_category"] == "MASALAH_AKTIF"
    assert result["rows"][0]["process_key"] == "sales-order"
    assert result["rows"][0]["destination_url"] == "/dashboard/sales-orders?sales_order_id=42"
    assert result["process_counts"][0]["count"] == 3
    assert result["rule_results"][0]["overall_status"] == "MISMATCH"
    assert any(params == {"limit": 2, "offset": 4} for _, params in service.calls)
