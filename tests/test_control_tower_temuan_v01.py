from hashlib import md5
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.control_tower.router import require_dashboard_auth
from src.control_tower.service import ControlTowerService


ROOT = Path(__file__).parents[1]
RULE_SQL = (ROOT / "sql/09_control_tower_sop_validation_v0.sql").read_text(encoding="utf-8")
PROJECTION_SQL = (ROOT / "sql/13_control_tower_temuan_v01.sql").read_text(encoding="utf-8")


def missing_fields(client_ref, po_date):
    return [
        field
        for field, value in (
            ("Customer Reference", client_ref),
            ("Customer PO Date", po_date),
        )
        if value is None or not str(value).strip()
    ]


def finding_id(document_id, company_id):
    return md5(
        f"DH2-SALES-001|sale.order|{document_id}|{company_id}".encode()
    ).hexdigest()


def test_rule_positive_and_negative_field_fixtures():
    assert missing_fields(None, "2026-01-02") == ["Customer Reference"]
    assert missing_fields("REF-1", None) == ["Customer PO Date"]
    assert missing_fields(" ", "") == ["Customer Reference", "Customer PO Date"]
    assert missing_fields("REF-1", "2026-01-02") == []


def test_rule_scope_is_strict_and_does_not_use_write_date():
    assert "LOWER(COALESCE(state, '')) = 'sale'" in RULE_SQL
    assert "date_order" in RULE_SQL
    assert "TIMESTAMP '2026-01-01'" in RULE_SQL
    assert "COALESCE(NULLIF(payload ->> 'date_order', '')::timestamp, write_date)" not in RULE_SQL


def test_persistence_contract_and_deterministic_business_key():
    assert "CREATE TABLE IF NOT EXISTS ct_finding" in PROJECTION_SQL
    assert "Cannot replace incompatible populated ct_finding table." in PROJECTION_SQL
    assert "UNIQUE (rule_code, affected_model, affected_document_id, company_id)" in PROJECTION_SQL
    assert finding_id(42, 7) == finding_id(42, 7)
    assert finding_id(42, 7) != finding_id(42, 8)
    assert "current_status IN ('OPEN', 'RESOLVED')" in PROJECTION_SQL
    assert "first_detected_time" in PROJECTION_SQL
    assert "last_detected_time" in PROJECTION_SQL


def test_projection_is_idempotent_and_resolves_only_current_company():
    assert "ON CONFLICT (rule_code, affected_model, affected_document_id, company_id)" in PROJECTION_SQL
    assert "first_detected_time = EXCLUDED" not in PROJECTION_SQL
    assert "current_status = 'OPEN'" in PROJECTION_SQL
    assert "current_status = 'RESOLVED'" in PROJECTION_SQL
    assert "finding.company_id = (SELECT company_id FROM vw_ct_current_run)" in PROJECTION_SQL


def test_findings_service_exposes_contract_and_deterministic_order():
    service = ControlTowerService.__new__(ControlTowerService)
    service._rows = Mock(side_effect=[
        [{
            "finding_id": "abc",
            "category": "DATA_BELUM_LENGKAP",
            "rule_code": "DH2-SALES-001",
            "affected_model": "sale.order",
            "affected_document_id": 42,
            "native_document_reference": "SO001",
            "company_id": 7,
            "title": "Data Sales Order belum lengkap",
            "summary": "Lengkapi Customer Reference pada SO SO001.",
            "evidence_payload": {"missing_fields": ["Customer Reference"]},
            "first_detected_time": "2026-01-02T00:00:00+00:00",
            "last_detected_time": "2026-01-03T00:00:00+00:00",
            "current_status": "OPEN",
            "destination_url": "/dashboard/sales-orders?sales_order_id=42",
        }],
        [{"total": 1}],
    ])
    result = service.findings()
    assert result["rows"][0]["destination_url"].endswith("sales_order_id=42")
    assert result["rows"][0]["current_status"] == "OPEN"
    assert result["total"] == 1
    assert "ORDER BY finding.rule_code, finding.affected_model" in service._rows.call_args_list[0].args[0]


def test_findings_service_applies_bound_business_filters_to_rows_and_total():
    service = ControlTowerService.__new__(ControlTowerService)
    service._rows = Mock(side_effect=[[], [{"total": 0}]])
    result = service.findings(affected_model="sale.order", category="DATA_BELUM_LENGKAP", rule_code="DH2-SALES-001")
    assert result["total"] == 0
    sql, params = service._rows.call_args_list[0].args
    assert "finding.affected_model = :affected_model" in sql
    assert "finding.category = :category" in sql
    assert "finding.rule_code = :rule_code" in sql
    assert params["affected_model"] == "sale.order"
    assert params["category"] == "DATA_BELUM_LENGKAP"
    assert params["rule_code"] == "DH2-SALES-001"

def test_findings_api_requires_authentication():
    with pytest.raises(Exception) as error:
        require_dashboard_auth(type("Request", (), {"cookies": {}})())
    assert getattr(error.value, "status_code", None) == 401
