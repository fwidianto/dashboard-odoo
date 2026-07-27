from decimal import Decimal

import pytest

from src.control_tower.relation_extractor import CONTRACT_VERSION, LINK_SPECS, MODEL_SPECS
from src.control_tower.v03 import (
    CLOSE_REASONS,
    RULE_CONFIGS,
    V03_SCHEMA_SQL,
    quantities_equal,
    validate_close,
)


def test_v03_contract_covers_proven_line_relations_and_reference_data() -> None:
    models = {spec.model: spec for spec in MODEL_SPECS}
    assert {
        "sale.order.line",
        "purchase.order.line",
        "account.move.line",
        "stock.move",
        "stock.move.line",
        "stock.valuation.layer",
        "approval.product.line",
        "uom.uom",
        "res.currency.rate",
        "account.account",
    } <= models.keys()
    assert "sale_line_ids" in models["account.move.line"].required_fields
    assert "purchase_line_id" in models["account.move.line"].required_fields
    assert "cogs_origin_id" in models["account.move.line"].required_fields
    assert "write_date" in models["stock.valuation.layer"].required_fields
    assert CONTRACT_VERSION.endswith("odoo18-2026")

    links = {(item.field_owner_model, item.source_field) for item in LINK_SPECS}
    assert ("account.move.line", "sale_line_ids") in links
    assert ("account.move.line", "purchase_line_id") in links
    assert ("account.move.line", "cogs_origin_id") in links
    assert ("stock.move", "sale_line_id") in links
    assert ("stock.move", "purchase_line_id") in links
    assert ("approval.product.line", "purchase_order_line_id") in links


def test_v03_schema_preserves_many_to_many_and_finding_history() -> None:
    assert "ct_line_lineage" in V03_SCHEMA_SQL
    assert "ct_finding_detection" in V03_SCHEMA_SQL
    assert "ct_finding_event" in V03_SCHEMA_SQL
    assert "ct_exception_rule" in V03_SCHEMA_SQL
    assert "ct_published_run" in V03_SCHEMA_SQL
    assert "primary_line_id" in V03_SCHEMA_SQL
    assert "MANUALLY_CLOSED" in V03_SCHEMA_SQL
    assert "AUTO_RESOLVED" in V03_SCHEMA_SQL
    assert "completed_work_units" in V03_SCHEMA_SQL
    assert "retryable_phase" in V03_SCHEMA_SQL
    assert "final_summary" in V03_SCHEMA_SQL
    assert len({rule["rule_code"] for rule in RULE_CONFIGS}) == len(RULE_CONFIGS)


def test_uom_comparison_uses_rounding_precision() -> None:
    assert quantities_equal(Decimal("10.001"), Decimal("10.004"), Decimal("0.01"))
    assert not quantities_equal(Decimal("10.001"), Decimal("10.006"), Decimal("0.01"))
    with pytest.raises(ValueError, match="positive"):
        quantities_equal(Decimal("1"), Decimal("1"), Decimal("0"))


def test_close_validation_requires_auditable_reason_and_notes() -> None:
    assert validate_close(CLOSE_REASONS[0], None) == (CLOSE_REASONS[0], None)
    with pytest.raises(ValueError, match="Catatan wajib"):
        validate_close("Pengecualian bisnis yang sah", "")
    with pytest.raises(ValueError, match="tidak valid"):
        validate_close("bebas", "catatan")
    assert validate_close("Alasan lain", "  bukti keputusan  ") == (
        "Alasan lain",
        "bukti keputusan",
    )
