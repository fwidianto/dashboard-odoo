from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.control_tower.change_detection import (
    ChangeDetectionError,
    DETECTION_BUCKET_PAGE_SIZE,
    DETECTION_CURSOR_ALGORITHM_VERSION,
    IncrementalChangeDetectionService,
    _capture_scan_upper_exclusive,
    _detection_fields,
    _locate_next_bucket,
    _scan_bucket_page,
    _validate_flat_domain,
    parse_odoo_write_date,
)
from src.control_tower.contracts import resolve_execution_entries
from src.control_tower.progress import ProgressContractError, parse_progress_json
from src.control_tower.watermarks import normalize_utc
from tests.control_tower_odoo_fake import FakeOdoo, UnfilteredOdoo


UTC = timezone.utc
STAMP = datetime(2026, 3, 13, 3, 29, 26, tzinfo=UTC)
WIRE = "2026-03-13 03:29:26"


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


def _row(record_id, second, *, order_id=0, true_ts=None, extra=None):
    row = {"id": record_id, "write_date": second, "company_id": [3, "Nobi"]}
    if order_id:
        row["order_id"] = [order_id, "SO"]
    if true_ts is not None:
        row["_true_write_date"] = true_ts
    if extra is not None:
        row.update(extra)
    return row


def _all_clauses(calls):
    clauses = []

    def walk(item):
        if isinstance(item, tuple) and len(item) == 3 and isinstance(item[0], str) and isinstance(item[1], str):
            clauses.append(item)
            return
        if isinstance(item, (list, tuple)):
            for part in item:
                walk(part)

    for call in calls:
        walk(call["domain"])
    return clauses


# --- Odoo transport parsing -------------------------------------------------

def test_parse_odoo_write_date_accepts_real_wire_format():
    value = parse_odoo_write_date("2026-03-13 03:29:26")
    assert value == datetime(2026, 3, 13, 3, 29, 26, tzinfo=UTC)
    assert value.tzinfo is not None and value.utcoffset() == timedelta(0)
    assert value.microsecond == 0
    assert parse_odoo_write_date("2026-03-13T03:29:26") == value


@pytest.mark.parametrize("bad", [
    "2026-03-13 03:29:26.500000",
    "2026-03-13 03:29:26+00:00",
    "2026-03-13 03:29",
    "13/03/2026 03:29:26",
    "2026-03-13 03:29:61",
    "2026-13-13 03:29:26",
    "",
    None,
    123,
])
def test_parse_odoo_write_date_rejects_unsupported_forms(bad):
    with pytest.raises(ChangeDetectionError, match="YYYY-MM-DD|valid date"):
        parse_odoo_write_date(bad)


def test_general_naive_datetime_remains_rejected():
    naive = datetime(2026, 3, 13, 3, 29, 26)
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(naive)
    with pytest.raises(ChangeDetectionError, match="YYYY-MM-DD"):
        parse_odoo_write_date(naive)


def test_aware_utc_accepted_by_internal_normalization():
    assert normalize_utc(datetime(2026, 3, 13, 3, 29, 26, tzinfo=UTC)) == STAMP
    assert normalize_utc(datetime(2026, 3, 13, 10, 29, 26, tzinfo=timezone(timedelta(hours=7)))) == STAMP


# --- Hidden precision regression -------------------------------------------

def test_hidden_precision_bucket_range_captures_every_record():
    rows = [
        _row(101, WIRE, order_id=88, true_ts=datetime(2026, 3, 13, 3, 29, 26, 500000, tzinfo=UTC)),
        _row(102, WIRE, order_id=88, true_ts=datetime(2026, 3, 13, 3, 29, 26, 750000, tzinfo=UTC)),
        _row(103, WIRE, order_id=88, true_ts=datetime(2026, 3, 13, 3, 29, 26, 999000, tzinfo=UTC)),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, _ = _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert [row["record_id"] for row in manifest] == [101, 102, 103]
    assert all(row["source_write_date"] == STAMP for row in manifest)
    assert result.manifest_rows == 3
    assert result.watermark_second_replay_rows == 3
    assert result.overlap_rechecked == 3
    clauses = _all_clauses(fake.calls)
    assert not any(clause[0] == "write_date" and clause[1] == "=" for clause in clauses)
    for call in fake.calls:
        bucket = [clause for clause in _all_clauses([call]) if clause[0] == "write_date" and clause[1] == ">="]
        upper = [clause for clause in _all_clauses([call]) if clause[0] == "write_date" and clause[1] == "<"]
        assert len(bucket) <= 1 and len(upper) <= 1


# --- Mandatory watermark-bucket replay --------------------------------------

def test_mandatory_watermark_second_replay_with_zero_overlap():
    rows = [
        _row(9, WIRE, order_id=88),
        _row(12, WIRE, order_id=88),
        _row(11, "2026-03-13 03:29:27", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, scan = _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert [row["record_id"] for row in manifest] == [9, 12, 11]
    assert [row["from_overlap"] for row in manifest] == [True, True, False]
    assert result.watermark_second_replay_rows == 2
    assert result.genuinely_newer_rows == 1
    assert result.overlap_rechecked == 2
    assert scan["replay_start_second"] == STAMP
    first_page = next(call for call in fake.calls if call["order"] == "id asc")
    id_clauses = [clause for clause in _all_clauses([first_page]) if clause[0] == "id"]
    assert id_clauses == [("id", ">", 0)]
    assert not any(clause[0] == "id" and clause[1] == ">" and clause[2] == 10 for clause in _all_clauses(fake.calls))


# --- Bucket pagination ------------------------------------------------------

def test_bucket_pagination_pages_without_duplicates_or_backward_ids():
    page_size = 2
    rows = [_row(record_id, "2026-03-13 03:29:27", order_id=88) for record_id in range(101, 107)]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, _ = _service()._detect_model(_entry(), 3, _watermark(), fake, bucket_page_size=page_size)
    ids = [row["record_id"] for row in manifest]
    assert ids == list(range(101, 107))
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    assert result.genuinely_newer_rows == 6
    pages = [call for call in fake.calls if call["order"] == "id asc"]
    assert len(pages) == 4
    for index, call in enumerate(pages):
        assert call["limit"] == page_size
        id_gt = [clause for clause in _all_clauses([call]) if clause[0] == "id"][0]
        assert id_gt == ("id", ">", (0 if index == 0 else 100 + index * page_size))


def test_conflicting_duplicate_content_fails_closed_before_next_page():
    rows = [
        _row(101, "2026-03-13 03:29:27", order_id=88),
        _row(102, "2026-03-13 03:29:27", order_id=89),
        _row(102, "2026-03-13 03:29:27", order_id=99),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    with pytest.raises(ChangeDetectionError, match="conflicting"):
        _service()._detect_model(_entry(), 3, _watermark(), fake, bucket_page_size=3)
    assert len([call for call in fake.calls if call["order"] == "id asc"]) == 1


def test_conflicting_duplicate_id_across_buckets_fails_closed():
    rows = [
        _row(12, "2026-03-13 03:29:27", order_id=88),
        _row(12, "2026-03-13 03:29:28", order_id=88),
    ]
    with pytest.raises(ChangeDetectionError, match="conflicting"):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo({"sale.order.line": rows}))


# --- Next populated second --------------------------------------------------

def test_next_populated_second_probe_skips_empty_seconds():
    rows = [
        _row(101, WIRE, order_id=88),
        _row(102, "2026-03-13 03:29:29", order_id=88),
        _row(103, "2026-03-13 03:29:30", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, _ = _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert [row["record_id"] for row in manifest] == [101, 102, 103]
    probes = [call for call in fake.calls if call["order"] == "write_date asc, id asc" and call["limit"] == 1]
    assert len(probes) == 3
    for probe in probes:
        assert probe["limit"] == 1
    probe_bounds = []
    for probe in probes:
        lower = [clause for clause in _all_clauses([probe]) if clause[0] == "write_date" and clause[1] == ">="][0]
        probe_bounds.append(datetime.fromisoformat(lower[2]))
    assert probe_bounds == [STAMP, STAMP + timedelta(seconds=1), STAMP + timedelta(seconds=4)]
    bucket_seconds = sorted({row["source_write_date"] for row in manifest})
    assert bucket_seconds == [STAMP, STAMP + timedelta(seconds=3), STAMP + timedelta(seconds=4)]


# --- Fixed upper boundary ---------------------------------------------------

def test_fixed_upper_boundary_is_captured_once_and_terminates_live_source():
    rows = [
        _row(101, WIRE, order_id=88),
        _row(102, "2026-03-13 03:29:27", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows}, live=True)
    result, manifest, scan = _service()._detect_model(_entry(), 3, _watermark(), fake)
    upper_calls = [call for call in fake.calls if call["order"] == "write_date desc, id desc"]
    assert len(upper_calls) == 1
    assert upper_calls[0]["limit"] == 1
    assert scan["scan_upper_exclusive"] == STAMP + timedelta(seconds=2)
    assert [row["record_id"] for row in manifest] == [101, 102]
    assert all(call["limit"] is not None for call in fake.calls)
    _, manifest_again, scan_again = _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert len(manifest_again) > 2
    assert scan_again["scan_upper_exclusive"] > scan["scan_upper_exclusive"]


# --- Overlap classification -------------------------------------------------

def test_overlap_replays_configured_and_watermark_buckets_and_distinguishes_newer():
    watermark = _watermark(overlap=5)
    rows = [
        _row(100, "2026-03-13 03:29:21", order_id=88),
        _row(101, "2026-03-13 03:29:25", order_id=88),
        _row(102, WIRE, order_id=88),
        _row(103, "2026-03-13 03:29:27", order_id=88),
        _row(100, "2026-03-13 03:29:21", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, scan = _service()._detect_model(_entry(), 3, watermark, fake)
    assert scan["replay_start_second"] == STAMP - timedelta(seconds=5)
    assert [row["record_id"] for row in manifest] == [100, 101, 102, 103]
    assert [row["from_overlap"] for row in manifest] == [True, True, True, False]
    assert result.configured_overlap_rows == 2
    assert result.watermark_second_replay_rows == 1
    assert result.genuinely_newer_rows == 1
    assert result.duplicates_removed == 1
    assert result.overlap_rechecked == 3
    assert len({row["record_id"] for row in manifest}) == 4


def test_rows_below_replay_start_are_excluded_by_domain():
    watermark = _watermark(overlap=5)
    older = _row(9, "2026-03-13 03:29:20", order_id=88)
    result, manifest, _ = _service()._detect_model(_entry(), 3, watermark, FakeOdoo({"sale.order.line": [older]}))
    assert manifest == []
    assert result.manifest_rows == 0


def test_out_of_window_rows_fail_closed_even_from_rogue_client():
    rows = [
        _row(9, "2026-03-13 03:29:20", order_id=88),
        _row(10, WIRE, order_id=88),
    ]
    with pytest.raises(ChangeDetectionError, match="bucket probe"):
        _service()._detect_model(_entry(), 3, _watermark(overlap=5), UnfilteredOdoo({"sale.order.line": rows}))


# --- Read-only behavior -----------------------------------------------------

def test_detection_only_uses_bounded_search_read_with_detection_fields():
    rows = [
        _row(101, WIRE, order_id=88),
        _row(102, "2026-03-13 03:29:27", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    _service()._detect_model(_entry(), 3, _watermark(), fake)
    assert fake.calls
    fields = _detection_fields(_entry())
    assert fields == ("id", "write_date", "company_id", "order_id")
    for call in fake.calls:
        assert tuple(call["fields"]) == fields
        assert call["limit"] is not None and call["limit"] >= 1
        assert call["order"] in {"write_date desc, id desc", "write_date asc, id asc", "id asc"}
    with pytest.raises(AssertionError, match="complete Odoo reads"):
        fake.read("sale.order.line", [1])


# --- Response shape validation ----------------------------------------------

@pytest.mark.parametrize("row", [
    _row(12, "2026-03-13 03:29:27", order_id=88, extra={"extra": 1}),
    {"id": 12, "write_date": "2026-03-13 03:29:27"},
])
def test_response_shape_rejects_extra_or_missing_required_fields(row):
    with pytest.raises(ChangeDetectionError):
        _service()._detect_model(_entry(), 3, _watermark(), UnfilteredOdoo({"sale.order.line": [row]}))


@pytest.mark.parametrize("relation", [
    [True, "SO"], [0, "SO"], [-1, "SO"], [88], [88, "SO", "extra"],
    {"id": 88}, "88", [88, False], [88, ""],
])
def test_malformed_many2one_values_fail_closed(relation):
    row = _row(12, "2026-03-13 03:29:27", extra={"order_id": relation})
    with pytest.raises(ChangeDetectionError):
        _service()._detect_model(_entry(), 3, _watermark(), FakeOdoo({"sale.order.line": [row]}))


@pytest.mark.parametrize("row, message", [
    (_row(0, "2026-03-13 03:29:27"), "id"),
    (_row(12, "2026-03-13 03:29:27", extra={"company_id": [4, "Other"]}), "company scope"),
])
def test_malformed_or_wrong_company_rows_fail_closed(row, message):
    with pytest.raises(ChangeDetectionError, match=message):
        _service()._detect_model(_entry(), 3, _watermark(), UnfilteredOdoo({"sale.order.line": [row]}))


# --- Parent hints -----------------------------------------------------------

def test_account_partial_reconcile_preserves_debit_and_credit_parent_hints():
    entry = next(entry for entry in resolve_execution_entries(["finance"]) if entry.model_key == "account.partial.reconcile")
    fields = _detection_fields(entry)
    assert fields == ("id", "write_date", "company_id", "credit_move_id", "debit_move_id")
    row = {
        "id": 12, "write_date": "2026-03-13 03:29:27", "company_id": [3, "Nobi"],
        "debit_move_id": [88, "Debit"], "credit_move_id": [89, "Credit"],
    }
    watermark = dict(_watermark(), model="account.partial.reconcile")
    _, rows, _ = _service()._detect_model(entry, 3, watermark, FakeOdoo({"account.partial.reconcile": [row]}))
    assert rows[0]["parent_hints"] == [
        {"parent_model": "account.move.line", "parent_record_id": 89, "field": "credit_move_id"},
        {"parent_model": "account.move.line", "parent_record_id": 88, "field": "debit_move_id"},
    ]


def test_stock_move_preserves_coexisting_picking_and_production_hints():
    entry = next(entry for entry in resolve_execution_entries(["warehouse"]) if entry.model_key == "stock.move")
    fields = _detection_fields(entry)
    assert "picking_id" in fields and "production_id" in fields
    row = {
        "id": 12, "write_date": "2026-03-13 03:29:27", "company_id": [3, "Nobi"],
        "picking_id": [88, "Picking"], "production_id": [89, "Production"],
    }
    watermark = dict(_watermark(), model="stock.move")
    _, rows, _ = _service()._detect_model(entry, 3, watermark, FakeOdoo({"stock.move": [row]}))
    assert {hint["field"] for hint in rows[0]["parent_hints"]} == {"picking_id", "production_id"}


# --- Progress contract ------------------------------------------------------

def test_shared_stock_move_resolves_once_and_progress_is_truthful():
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
        "detection_cursor_algorithm_version": DETECTION_CURSOR_ALGORITHM_VERSION,
        "detection_bucket_page_size": DETECTION_BUCKET_PAGE_SIZE,
        "detection_replay_start_seconds": {model: "2026-01-01T10:00:00+00:00" for model in models},
        "detection_scan_upper_exclusives": {model: "2026-01-01T10:00:02+00:00" for model in models},
        "detection_completion_fingerprint": "b" * 64,
        "detection_completion_contract_version": "ct-change-manifest-v1",
        "detection_manifest_row_count": 2,
        "detection_manifest_rows_persisted": 2,
        "detection_model_row_counts": {model: (2 if index == 0 else 0) for index, model in enumerate(models)},
    })
    assert payload["change_detection_complete"] is True
    assert payload["detection_models_completed"] == models


def test_completion_progress_requires_all_evidence():
    with pytest.raises(ProgressContractError):
        parse_progress_json({
            "change_detection_complete": True,
            "detection_models_planned": ["sale.order"],
            "detection_models_completed": ["sale.order"],
        })

# --- Odoo domain serialization (Odoo 18 flat-domain correction) ------------

def _contains_nested_domain(item):
    if isinstance(item, (list, tuple)) and len(item) == 3 and isinstance(item[0], str) and item[0] in ("&", "|"):
        return any(_contains_nested_domain(part) for part in item[1:])
    if isinstance(item, (list, tuple)):
        return any(_contains_nested_domain(part) for part in item)
    return False


def test_upper_bound_capture_domain_is_flat_and_bounded():
    entry = _entry()
    fields = _detection_fields(entry)
    fake = FakeOdoo({"sale.order.line": [_row(101, WIRE, order_id=88)]})
    cap = _capture_scan_upper_exclusive(fake, "sale.order.line", 3, STAMP, tuple(fields))
    assert cap == STAMP + timedelta(seconds=1)
    call = fake.calls[0]
    assert call["order"] == "write_date desc, id desc"
    assert call["limit"] == 1
    assert not _contains_nested_domain(call["domain"])


def test_locate_next_bucket_emits_flat_implicit_and_domain():
    entry = _entry()
    fields = _detection_fields(entry)
    fake = FakeOdoo({"sale.order.line": [_row(101, WIRE, order_id=88)]})
    upper = STAMP + timedelta(seconds=1)
    second = _locate_next_bucket(fake, "sale.order.line", 3, STAMP, upper, tuple(fields))
    assert second == STAMP
    call = fake.calls[0]
    assert call["order"] == "write_date asc, id asc"
    assert call["limit"] == 1
    assert call["domain"] == (
        ("company_id", "=", 3),
        ("write_date", ">=", STAMP.isoformat()),
        ("write_date", "<", upper.isoformat()),
    )
    assert not _contains_nested_domain(call["domain"])


def test_scan_bucket_page_emits_flat_implicit_and_domain():
    entry = _entry()
    fields = _detection_fields(entry)
    fake = FakeOdoo({"sale.order.line": [_row(101, WIRE, order_id=88)]})
    page = _scan_bucket_page(fake, "sale.order.line", 3, STAMP, 0, tuple(fields), 25)
    assert [row["id"] for row in page] == [101]
    call = fake.calls[0]
    assert call["order"] == "id asc"
    assert call["limit"] == 25
    assert call["domain"] == (
        ("company_id", "=", 3),
        ("write_date", ">=", STAMP.isoformat()),
        ("write_date", "<", (STAMP + timedelta(seconds=1)).isoformat()),
        ("id", ">", 0),
    )
    assert not _contains_nested_domain(call["domain"])


def test_detector_emits_no_nested_domains_equality_or_offset():
    rows = [
        _row(101, WIRE, order_id=88, true_ts=datetime(2026, 3, 13, 3, 29, 26, 123000, tzinfo=UTC)),
        _row(102, WIRE, order_id=88, true_ts=datetime(2026, 3, 13, 3, 29, 26, 456000, tzinfo=UTC)),
        _row(103, "2026-03-13 03:29:27", order_id=88),
    ]
    fake = FakeOdoo({"sale.order.line": rows})
    result, manifest, _ = _service()._detect_model(_entry(), 3, _watermark(), fake, bucket_page_size=2)
    assert result.manifest_rows == 3
    assert [row["record_id"] for row in manifest] == [101, 102, 103]
    for call in fake.calls:
        assert not _contains_nested_domain(call["domain"])
        assert call.get("offset") is None
        assert call["limit"] is not None
        assert not any(clause[0] == "write_date" and clause[1] == "=" for clause in _all_clauses([call]))


@pytest.mark.parametrize("bad", [
    ["&", ("company_id", "=", 3)],
    ["&", ("company_id", "=", 3), ["&", ("write_date", ">=", "x"), ("write_date", "<", "y")]],
    [("company_id", "=", 3), {"write_date": "x"}],
    ["company_id"],
    [("company_id", 3)],
    [("company_id", "=", [3])],
    [("company_id", "in", (3, 4))],
    ("company_id", "=", 3),
])
def test_local_domain_validation_rejects_unsupported_shapes(bad):
    with pytest.raises(ChangeDetectionError):
        _validate_flat_domain(bad, "sale.order")


def test_local_domain_validation_accepts_flat_shapes():
    _validate_flat_domain([], "sale.order")
    _validate_flat_domain([
        ("company_id", "=", 3),
        ("write_date", ">=", STAMP.isoformat()),
        ("write_date", "<", (STAMP + timedelta(seconds=1)).isoformat()),
        ("id", ">", 0),
    ], "sale.order")
    _validate_flat_domain(["&", ("company_id", "=", 3), ("write_date", ">=", STAMP.isoformat())], "sale.order")


def test_nested_domain_rejected_with_server_like_message():
    nested = ["&", ("company_id", "=", 3), ["&", ("write_date", ">=", "x"), ("write_date", "<", "y")]]
    with pytest.raises(ChangeDetectionError, match="Nested Odoo Boolean domain"):
        _validate_flat_domain(nested, "sale.order")


class StrictOdoo18(FakeOdoo):
    """Independent Odoo 18-faithful fake: nested domains raise the server error."""

    def _validate_domain(self, model, domain):
        if isinstance(domain, list) and domain and not (
            isinstance(domain[0], str) and domain[0] in ("&", "|")
        ):
            for leaf in domain:
                if isinstance(leaf, list) and len(leaf) == 3 and isinstance(leaf[0], str) and leaf[0] in ("&", "|"):
                    raise ValueError(f"Invalid field {model}.{leaf[0]} in leaf {tuple(leaf)!r}")
        return super()._validate_domain(model, domain)


def test_strict_odoo18_fake_rejects_old_nested_shape_and_corrected_detector_completes():
    previous_rejected_shape = [
        "&", ("company_id", "=", 3),
        ["&", ("write_date", ">=", STAMP.isoformat()),
              ("write_date", "<", (STAMP + timedelta(seconds=1)).isoformat())],
    ]
    strict = StrictOdoo18({"sale.order.line": [_row(101, WIRE, order_id=88)]})
    with pytest.raises(ValueError, match=r"Invalid field sale\.order\.line\.& in leaf"):
        strict.search_read("sale.order.line", previous_rejected_shape,
                           fields=["id", "write_date", "company_id"], order="id asc", limit=1)
    rows = [
        _row(101, WIRE, order_id=88),
        _row(102, "2026-03-13 03:29:27", order_id=88),
    ]
    result, manifest, scan = _service()._detect_model(
        _entry(), 3, _watermark(), StrictOdoo18({"sale.order.line": rows}))
    assert result.manifest_rows == 2
    assert [row["record_id"] for row in manifest] == [101, 102]
    assert scan["scan_upper_exclusive"] == STAMP + timedelta(seconds=2)
