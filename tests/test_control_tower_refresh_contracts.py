from datetime import datetime, timedelta, timezone
import json

import pytest

from src.control_tower.contracts import (
    DOMAIN_REGISTRY, MODEL_SPEC_KEYS, resolve_domain_selection,
    resolve_execution_entries, resolve_model_keys, validate_domain_registry,
)
from src.control_tower.progress import ProgressContractError, parse_progress_json, serialize_progress, validate_progress_payload
from src.control_tower.reconciliation import completion_status, normalize_reconciliation_timestamp
from src.control_tower.refresh_state import (
    TERMINAL_STATES,
    require_no_change_run,
    require_published_run,
    validate_failure_class,
    validate_retry_source_status,
    validate_transition,
)
from src.control_tower.schema_guard import Phase8SchemaNotReady, ensure_phase8_schema_ready
from src.control_tower.watermarks import (
    compare_tuples,
    normalize_utc,
    validate_overlap,
    validate_watermark_row,
)


def test_registry_references_only_approved_model_specs():
    validate_domain_registry()
    registered = {model for domain in DOMAIN_REGISTRY for model in domain.model_keys}
    assert registered <= MODEL_SPEC_KEYS
    assert "product.template" not in registered
    assert "account.payment" not in registered


def test_domain_selection_deduplicates_shared_models_and_resolves_dependencies():
    domains = resolve_domain_selection(["commercial", "warehouse"])
    assert [domain.key for domain in domains] == ["commercial", "internal_order", "manufacturing", "procurement", "warehouse"]
    models = resolve_model_keys(["commercial", "warehouse"])
    assert models.count("stock.move") == 1


def test_shared_model_entry_merges_domain_and_reconciliation_metadata():
    entry = next(item for item in resolve_execution_entries(["manufacturing", "warehouse"]) if item.model_key == "stock.move")
    assert entry.domain_keys == ("manufacturing", "warehouse")
    assert {relation.parent_model for relation in entry.parent_children} == {"mrp.production", "stock.picking"}
    assert entry.downstream_stages == ("RECONCILING", "VALIDATING", "REFRESHING_DERIVED_DATA")


def test_all_resolves_only_registered_control_tower_domains():
    assert resolve_domain_selection(["all"]) == DOMAIN_REGISTRY
    assert "product.template" not in resolve_model_keys(["all"])


def test_unknown_domain_and_mixed_all_fail_closed():
    with pytest.raises(ValueError, match="Unknown Control Tower domain"):
        resolve_domain_selection(["legacy_sync"])
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_domain_selection(["all", "commercial"])


@pytest.mark.parametrize("current,target", [
    ("REQUESTED", "PREPARING"), ("PREPARING", "DETECTING_CHANGES"),
    ("DETECTING_CHANGES", "VALIDATING"), ("VALIDATING", "PUBLISHING"),
    ("PUBLISHING", "SUCCEEDED_NO_CHANGES"), ("PUBLISHING", "SUCCEEDED"),
    ("READY_FOR_PUBLISH", "PUBLISHING"),
])
def test_valid_refresh_transitions(current, target):
    validate_transition(current, target)


def test_no_change_cannot_skip_validation_and_publication():
    with pytest.raises(ValueError, match="Invalid refresh transition"):
        validate_transition("DETECTING_CHANGES", "SUCCEEDED_NO_CHANGES")


def test_terminal_and_failure_states_cannot_restart_or_publish():
    assert "SUCCEEDED" in TERMINAL_STATES
    for current in ("SUCCEEDED", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED"):
        with pytest.raises(ValueError):
            validate_transition(current, "PUBLISHING")


def test_failure_class_is_explicit():
    validate_failure_class("FAILED_TRANSIENT", "TRANSIENT")
    with pytest.raises(ValueError, match="failure class"):
        validate_failure_class("FAILED_PERMANENT", "TRANSIENT")
    with pytest.raises(ValueError, match="Unsupported"):
        validate_failure_class("FAILED_TRANSIENT", "UNKNOWN")
    for active_state in ("REQUESTED", "PUBLISHING", "SUCCEEDED", "SUCCEEDED_NO_CHANGES"):
        with pytest.raises(ValueError, match="not allowed"):
            validate_failure_class(active_state, "TRANSIENT")
    validate_failure_class("ABORTED", "ABORTED")


def test_retry_is_limited_to_retry_safe_states():
    validate_retry_source_status("FAILED_TRANSIENT")
    validate_retry_source_status("INTERRUPTED")
    with pytest.raises(ValueError, match="Only transient"):
        validate_retry_source_status("FAILED_PERMANENT")


def test_progress_is_nullable_deterministic_and_subset_safe():
    payload = validate_progress_payload({"domains": ["warehouse", "commercial", "warehouse"], "completed_domains": ["commercial"], "models_planned": 2, "models_completed": 1, "records_detected": None})
    assert payload["domains"] == ["commercial", "warehouse"]
    assert "records_detected" not in payload
    assert serialize_progress(payload) == serialize_progress(json.loads(serialize_progress(payload)))
    with pytest.raises(ValueError, match="subset"):
        validate_progress_payload({"models": ["sale.order"], "completed_models": ["stock.move"]})
    with pytest.raises(ValueError, match="exceed"):
        validate_progress_payload({"domains_planned": 1, "domains_completed": 2})
    with pytest.raises(ValueError, match="requires planned"):
        validate_progress_payload({"completed_domains": ["commercial"]})
    with pytest.raises(ValueError, match="requires planned"):
        validate_progress_payload({"completed_models": ["stock.move"]})
    with pytest.raises(ValueError, match="subset"):
        validate_progress_payload({"domains": ["warehouse"], "completed_domains": ["commercial"]})
    with pytest.raises(ValueError, match="subset"):
        validate_progress_payload({"models": ["sale.order"], "completed_models": ["stock.move"]})
    assert validate_progress_payload({"completed_domains": [], "completed_models": []}) == {
        "completed_domains": [],
        "completed_models": [],
    }
    assert validate_progress_payload({"domains_completed": 0, "models_completed": 0}) == {
        "domains_completed": 0,
        "models_completed": 0,
    }


def test_progress_malformed_json_fails_closed():
    with pytest.raises(ProgressContractError, match="malformed JSON"):
        parse_progress_json("{")
    with pytest.raises(ProgressContractError, match="invalid"):
        parse_progress_json("[]")


def test_queue_generation_keeps_newer_touches_pending():
    assert completion_status(4, 4) == "COMPLETED"
    assert completion_status(5, 4) == "PENDING"


def test_watermark_tuple_and_timestamp_contracts():
    aware = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=7)))
    assert normalize_utc(aware).hour == 17
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="non-negative"):
        validate_overlap(-1)
    assert compare_tuples((normalize_utc(aware), 2), (normalize_utc(aware), 1)) == 1


def test_persisted_watermark_validation_is_fail_closed():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = {
        "company_id": 3,
        "model": "stock.move",
        "last_successful_write_date": aware,
        "last_successful_id": 7,
        "overlap_seconds": 0,
        "published_run_id": "00000000-0000-4000-8000-000000000007",
        "checked_at": aware,
        "status": "READY",
        "created_at": aware,
        "updated_at": aware,
    }
    normalized = validate_watermark_row(base, company_id=3, model="stock.move")
    assert normalized["last_successful_write_date"] == aware
    for field, value in (
        ("company_id", 4),
        ("model", "sale.order"),
        ("overlap_seconds", -1),
        ("last_successful_write_date", None),
        ("last_successful_id", 0),
        ("published_run_id", "not-a-uuid"),
        ("status", "BROKEN"),
    ):
        invalid = dict(base)
        invalid[field] = value
        with pytest.raises(ValueError):
            validate_watermark_row(invalid, company_id=3, model="stock.move")
    bootstrap = dict(base)
    bootstrap.update(status="BOOTSTRAP_REQUIRED", last_successful_write_date=None,
                     last_successful_id=None, published_run_id=None)
    assert validate_watermark_row(bootstrap)["status"] == "BOOTSTRAP_REQUIRED"


def test_no_change_publication_is_separate_from_normal_publication():
    require_published_run("SUCCEEDED", datetime.now(timezone.utc))
    require_no_change_run("SUCCEEDED_NO_CHANGES", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="successfully"):
        require_published_run("SUCCEEDED_NO_CHANGES", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="no-change"):
        require_no_change_run("SUCCEEDED", datetime.now(timezone.utc))


def test_reconciliation_timestamps_are_aware_and_utc():
    local = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=7)))
    assert normalize_reconciliation_timestamp(local).hour == 5
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_reconciliation_timestamp(datetime(2026, 1, 1, 12))


def test_migration_declares_phase7_prerequisite_and_reversible_objects():
    migration = open("migrations/versions/002_control_tower_refresh_contracts.py", encoding="utf-8").read()
    assert "Phase 8 migration requires a valid Phase 7 prerequisite column" in migration
    assert "finished_at" in migration and "published_at" in migration
    assert "ct_published_snapshot" in migration
    assert "fk_ct_run_retry_of" in migration
    assert "ck_ct_watermark_overlap_nonnegative" in migration
    assert "CREATE TABLE public.ct_control_tower_watermark" in migration
    assert "DROP TABLE public.ct_control_tower_watermark" in migration
    assert "ADD COLUMN IF NOT EXISTS" not in migration
    assert "CREATE TABLE IF NOT EXISTS" not in migration
    assert "CREATE INDEX IF NOT EXISTS" not in migration
    assert "DROP TABLE IF EXISTS ct_published_snapshot" not in migration


def test_watermark_requires_published_run():
    require_published_run("SUCCEEDED", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="successfully published"):
        require_published_run("FETCHING", None)


def test_phase8_schema_guard_is_deferred_and_clear():
    class Result:
        def __init__(self, scalar=None, row=None):
            self._scalar = scalar
            self._row = row

        def scalar(self):
            return self._scalar

        def mappings(self):
            return self

        def one(self):
            return self._row

    class Connection:
        def __init__(self, revision, row):
            self.revision = revision
            self.row = row

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_args, **_kwargs):
            if self.revision is not None:
                revision, self.revision = self.revision, None
                return Result(scalar=revision)
            return Result(row=self.row)

    class Engine:
        def __init__(self, connection):
            self.connection = connection

        def connect(self):
            return self.connection

    class Client:
        def __init__(self, connection):
            self.engine = Engine(connection)

    ready = {key: True for key in ("watermark", "queue", "cursor", "base_snapshot", "failure_class")}
    ensure_phase8_schema_ready(Client(Connection("002", ready)))
    with pytest.raises(Phase8SchemaNotReady, match="revision 002"):
        ensure_phase8_schema_ready(Client(Connection("001", ready)))
    with pytest.raises(Phase8SchemaNotReady, match="revision 002"):
        ensure_phase8_schema_ready(Client(Connection("002", {**ready, "queue": False})))
