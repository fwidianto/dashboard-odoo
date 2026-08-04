from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.control_tower.change_detection import (
    ChangeDetectionError,
    IncrementalChangeDetectionService,
    _detection_fields,
    _incremental_domain,
)
from src.control_tower.contracts import resolve_execution_entries
from src.control_tower.progress import ProgressContractError, parse_progress_json


UTC = timezone.utc
STAMP = datetime(2026, 1, 1, 10, tzinfo=UTC)


class FakeOdoo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search_read(self, model, domain, *, fields, order):
        self.calls.append((model, domain, fields, order))
        return self.rows

    def read_batched(self, *args, **kwargs):
        raise AssertionError("Detection must not fall back to complete-record reads")

    def read(self, *args, **kwargs):
        raise AssertionError("Detection must not fetch complete records")


def _service():
    return IncrementalChangeDetectionService(
        SimpleNamespace(engine=None),
        schema_guard=lambda pg: None,
    )


def _watermark(*, overlap=0):
    return {
        "company_id": 3,
        "model": "sale.order.line",
        "last_successful_write_date": STAMP,
        "last_successful_id": 10,
        "overlap_seconds": overlap,
        "published_run_id": "00000000-0000-4000-8000-000000000100",
        "status": "READY",
    }


def _entry():
    return next(entry for entry in resolve_execution_entries(["commercial"]) if entry.model_key == "sale.order.line")


def test_exact_tuple_boundary_and_minimal_parent_fields():
    entry = _entry()
    domain = _incremental_domain(3, STAMP, 10, 0)
    fields = _detection_fields(entry)
    assert domain == [
        "&", ("company_id", "=", 3), "|",
        ("write_date", ">", STAMP.isoformat()),
        "&", ("write_date", "=", STAMP.isoformat()), ("id", ">", 10),
    ]
    assert fields == ("id", "write_date", "company_id", "order_id")
    fake = FakeOdoo([
        {"id": 12, "write_date": "2026-01-01T10:00:00+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
        {"id": 11, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": False},
    ])
    result, rows = _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert [row["record_id"] for row in rows] == [12, 11]
    assert result.newer_detected == 2
    assert fake.calls[0][2] == ["id", "write_date", "company_id", "order_id"]
    assert fake.calls[0][3] == "write_date asc, id asc"


def test_overlap_recheck_is_deterministic_and_duplicate_safe():
    fake = FakeOdoo([
        {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
        {"id": 10, "write_date": "2026-01-01T10:00:00+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
        {"id": 11, "write_date": "2026-01-01T09:59:59+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
        {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
    ])
    result, rows = _service()._detect_model(_entry(), 3, _watermark(overlap=5), fake)
    assert [row["record_id"] for row in rows] == [11, 10, 12]
    assert result.overlap_rechecked == 2
    assert result.newer_detected == 1
    assert result.duplicates_removed == 1
    assert rows[0]["from_overlap"] is True
    assert rows[-1]["from_overlap"] is False


def test_overlap_boundary_is_inclusive_and_older_rows_fail_closed():
    lower = STAMP - timedelta(seconds=5)
    exact = {"id": 9, "write_date": lower.isoformat(), "company_id": [3, "Nobi"], "order_id": False}
    result, rows = _service()._detect_model(_entry(), 3, _watermark(overlap=5), FakeOdoo([exact]))
    assert result.overlap_rechecked == 1
    assert rows[0]["from_overlap"] is True
    older = dict(exact, write_date=(lower - timedelta(microseconds=1)).isoformat())
    with pytest.raises(ChangeDetectionError, match="overlap boundary"):
        _service()._detect_model(_entry(), 3, _watermark(overlap=5), FakeOdoo([older]))


@pytest.mark.parametrize("row", [
    {"id": 10, "write_date": STAMP.isoformat(), "company_id": [3, "Nobi"], "order_id": False},
    {"id": 11, "write_date": (STAMP - timedelta(microseconds=1)).isoformat(), "company_id": [3, "Nobi"], "order_id": False},
])
def test_non_overlap_watermark_tuple_is_exclusive(row):
    with pytest.raises(ChangeDetectionError, match="incremental boundary"):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo([row]))


def test_equal_timestamp_higher_id_and_newer_timestamp_lower_id_are_newer():
    rows = [
        {"id": 11, "write_date": STAMP.isoformat(), "company_id": [3, "Nobi"], "order_id": False},
        {"id": 1, "write_date": (STAMP + timedelta(seconds=1)).isoformat(), "company_id": [3, "Nobi"], "order_id": False},
    ]
    result, output = _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo(rows))
    assert result.newer_detected == 2
    assert [row["record_id"] for row in output] == [11, 1]


@pytest.mark.parametrize("row", [
    {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": False, "extra": 1},
    {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "order_id": False},
])
def test_response_shape_rejects_extra_or_missing_required_fields(row):
    with pytest.raises(ChangeDetectionError):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo([row]))


@pytest.mark.parametrize("relation", [
    [True, "SO"], [0, "SO"], [-1, "SO"], [88], [88, "SO", "extra"],
    {"id": 88}, "88", [88, False], [88, ""],
])
def test_malformed_many2one_values_fail_closed(relation):
    row = {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": relation}
    with pytest.raises(ChangeDetectionError):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo([row]))


@pytest.mark.parametrize("row, message", [
    ({"id": 0, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": False}, "id"),
    ({"id": 12, "write_date": "2026-01-01T10:00:01", "company_id": [3, "Nobi"], "order_id": False}, "timezone-aware"),
    ({"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [4, "Other"], "order_id": False}, "company scope"),
])
def test_malformed_or_wrong_company_rows_fail_closed(row, message):
    with pytest.raises(ChangeDetectionError, match=message):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo([row]))


def test_conflicting_duplicate_id_fails_closed():
    rows = [
        {"id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
        {"id": 12, "write_date": "2026-01-01T10:00:02+00:00", "company_id": [3, "Nobi"], "order_id": [88, "SO"]},
    ]
    with pytest.raises(ChangeDetectionError, match="conflicting"):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo(rows))


def test_shared_stock_move_is_resolved_once_and_progress_is_truthful():
    entries = resolve_execution_entries(["warehouse"])
    models = [entry.model_key for entry in entries]
    assert models.count("stock.move") == 1
    payload = parse_progress_json({
        "change_detection_complete": True,
        "detection_selected_domains": ["warehouse"],
        "detection_models_planned": models,
        "detection_models_completed": models,
        "detection_started_at": "2026-01-01T10:00:00+00:00",
        "detection_finished_at": "2026-01-01T10:00:00+00:00",
        "detection_elapsed_seconds": 0,
        "detection_records_scanned": 2,
        "detection_contract_fingerprint": "a" * 64,
        "detection_completion_fingerprint": "b" * 64,
        "detection_completion_contract_version": "ct-change-manifest-v1",
        "detection_manifest_row_count": 2,
        "detection_manifest_rows_persisted": 2,
        "detection_model_row_counts": {model: (2 if index == 0 else 0) for index, model in enumerate(models)},
    })
    assert payload["change_detection_complete"] is True
    assert payload["detection_models_completed"] == models


def test_account_partial_reconcile_preserves_debit_and_credit_parent_hints():
    entry = next(entry for entry in resolve_execution_entries(["finance"]) if entry.model_key == "account.partial.reconcile")
    fields = _detection_fields(entry)
    assert fields == ("id", "write_date", "company_id", "credit_move_id", "debit_move_id")
    row = {
        "id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"],
        "debit_move_id": [88, "Debit"], "credit_move_id": [89, "Credit"],
    }
    watermark = dict(_watermark(), model="account.partial.reconcile")
    _, rows = _service()._detect_model(entry, 3, watermark, FakeOdoo([row]))
    assert rows[0]["parent_hints"] == [
        {"parent_model": "account.move.line", "parent_record_id": 89, "field": "credit_move_id"},
        {"parent_model": "account.move.line", "parent_record_id": 88, "field": "debit_move_id"},
    ]


def test_stock_move_preserves_coexisting_picking_and_production_hints():
    entry = next(entry for entry in resolve_execution_entries(["warehouse"]) if entry.model_key == "stock.move")
    fields = _detection_fields(entry)
    assert "picking_id" in fields and "production_id" in fields
    row = {
        "id": 12, "write_date": "2026-01-01T10:00:01+00:00", "company_id": [3, "Nobi"],
        "picking_id": [88, "Picking"], "production_id": [89, "Production"],
    }
    watermark = dict(_watermark(), model="stock.move")
    _, rows = _service()._detect_model(entry, 3, watermark, FakeOdoo([row]))
    assert {hint["field"] for hint in rows[0]["parent_hints"]} == {"picking_id", "production_id"}


def test_completion_progress_requires_all_evidence():
    with pytest.raises(ProgressContractError):
        parse_progress_json({
            "change_detection_complete": True,
            "detection_models_planned": ["sale.order"],
            "detection_models_completed": ["sale.order"],
        })
