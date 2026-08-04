"""Phase 8C-1 orchestration tests: mocked Odoo + disposable PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from src.control_tower.copy_forward import CandidateSnapshotCopyForwardService
from src.control_tower.orchestration import OrchestrationError, RefreshPipelineOrchestrator
from src.control_tower.progress import parse_progress_json
from src.control_tower.refresh_state import RefreshRunStateService
from tests.control_tower_odoo_fake import FakeOdoo
from tests.test_control_tower_change_detection_postgres import _upgrade_003
from tests.test_control_tower_refresh_contracts_postgres import (
    PHASE7_BASE_RUN_ID,
    _bootstrap_phase7,
    _upgrade,
)


POSTGRES_URL = os.getenv("CT_TEST_POSTGRES_URL")
ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set CT_TEST_POSTGRES_URL to a disposable PostgreSQL URL.",
)

STAMP = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
WIRE = "2026-01-01 10:00:00"
COMMERCIAL_MODELS = ["sale.order", "sale.order.line"]
ALL_MODELS = [
    "sale.order", "sale.order.line", "approval.request", "approval.product.line",
    "mrp.production", "purchase.order", "purchase.order.line", "stock.picking",
    "stock.move", "account.move", "account.move.line", "account.partial.reconcile",
]
ALL_DOMAINS = ["commercial", "internal_order", "manufacturing", "procurement", "warehouse", "finance"]


def _client(engine):
    return SimpleNamespace(engine=engine)


@pytest.fixture
def engine():
    db = create_engine(POSTGRES_URL, pool_pre_ping=True)
    _bootstrap_phase7(db)
    _upgrade(db)
    _upgrade_003()
    try:
        yield db
    finally:
        with db.begin() as conn:
            for table in (
                "ct_change_manifest", "ct_change_detection_run",
                "ct_control_tower_watermark", "ct_parent_reconciliation_queue",
                "ct_parent_reconciliation_cursor", "ct_published_snapshot",
                "ct_native_record_snapshot", "ct_document_link",
                "ct_extraction_run", "alembic_version",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
        db.dispose()


def _orchestrator(engine, *, hooks=None):
    return RefreshPipelineOrchestrator(_client(engine), hooks=hooks)


def _create_run(engine, domains, *, company_id=3, start_preparing=False):
    svc = RefreshRunStateService(_client(engine))
    run = svc.create_run(company_id=company_id, selected_domains=domains, now=STAMP)
    if start_preparing:
        svc.transition(run["run_id"], "PREPARING", now=STAMP)
    return run["run_id"]


def _seed_watermarks(engine, models):
    with engine.begin() as conn:
        for model in models:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_control_tower_watermark
                        (company_id, model, last_successful_write_date, last_successful_id,
                         overlap_seconds, published_run_id, status)
                    VALUES (3, :model, :stamp, 1, 0, CAST(:run AS UUID), 'READY')
                    """
                ),
                {"model": model, "stamp": STAMP, "run": PHASE7_BASE_RUN_ID},
            )


def _rows(detected=True, models=None):
    rows = {model: [] for model in (models or COMMERCIAL_MODELS)}
    if detected:
        rows["sale.order"] = [{"id": 1, "write_date": WIRE, "company_id": [3, "Nobi"]}]
        rows["sale.order.line"] = [
            {"id": 11, "write_date": WIRE, "company_id": [3, "Nobi"], "order_id": [1, "SO"]},
            {"id": 12, "write_date": WIRE, "company_id": [3, "Nobi"], "order_id": [1, "SO"]},
        ]
    return rows


def _all_domain_rows():
    rows = _rows(detected=False, models=ALL_MODELS)
    rows["sale.order"] = [{"id": 1, "write_date": WIRE, "company_id": [3, "Nobi"]}]
    rows["sale.order.line"] = [
        {"id": 11, "write_date": WIRE, "company_id": [3, "Nobi"], "order_id": [1, "SO"]},
        {"id": 12, "write_date": WIRE, "company_id": [3, "Nobi"], "order_id": [1, "SO"]},
    ]
    rows["stock.picking"] = [
        {"id": 31, "write_date": WIRE, "company_id": [3, "Nobi"]},
        {"id": 32, "write_date": WIRE, "company_id": [3, "Nobi"]},
    ]
    rows["account.partial.reconcile"] = [
        {"id": 41, "write_date": WIRE, "company_id": [3, "Nobi"],
         "debit_move_id": [51, "Line"], "credit_move_id": [52, "Line"]},
    ]
    return rows


def _run_row(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT run_id::text, company_id, status, stage,
                       base_snapshot_run_id::text, progress
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
    return dict(row)


def _progress(engine, run_id):
    return parse_progress_json(_run_row(engine, run_id)["progress"])


def _manifest(engine, run_id):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT model, record_id FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID) ORDER BY model, detection_sequence
                """
            ),
            {"run_id": run_id},
        ).all()
    return [(row[0], row[1]) for row in rows]


def _snapshot_count(engine, run_id):
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT COUNT(*) FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).scalar()


def _wm_snapshot(engine):
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                text(
                    """
                    SELECT model, last_successful_write_date::text, last_successful_id,
                           overlap_seconds, status
                    FROM ct_control_tower_watermark WHERE company_id=3 ORDER BY model
                    """
                )
            ).all()
        ]


def _pointer(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")
        ).scalar()


class NoCallOdoo:
    def __getattr__(self, name):
        raise AssertionError(f"idempotent orchestration must not call Odoo: {name}")


def _boom(name):
    raise RuntimeError("injected " + name)


def _move_pointer(engine):
    other = _create_run(engine, ["commercial"])
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_extraction_run
                SET status='COMPLETED', completed_at=:now, finished_at=:now, published_at=:now
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": other, "now": STAMP},
        )
        conn.execute(
            text(
                """
                UPDATE ct_published_snapshot SET run_id = CAST(:run_id AS UUID)
                WHERE company_id=3
                """
            ),
            {"run_id": other},
        )
    return other


# --- detected-row path ------------------------------------------------------

def test_full_orchestration_detected_rows_ends_at_fetching(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    before_wm = _wm_snapshot(engine)
    before_pointer = _pointer(engine)
    fake = FakeOdoo(_rows())
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"], odoo_client=fake, now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["next_required_stage"] == "FETCHING"
    assert result["last_completed_stage"] == "DETECTING_CHANGES"
    assert result["manifest_rows"] == 3
    assert result["models_completed"] == ["sale.order", "sale.order.line"]
    assert result["no_changes"] is False
    assert result["idempotent"] is False
    assert result["copy_forward_status"] == "COMPLETE"
    assert result["detection_status"] == "COMPLETE"
    assert result["base_snapshot_run_id"] == PHASE7_BASE_RUN_ID
    assert result["candidate_run_id"] == run
    assert _run_row(engine, run)["status"] == "FETCHING"
    progress = _progress(engine, run)
    assert progress["change_detection_complete"] is True
    assert progress["detection_manifest_row_count"] == 3
    assert progress["orchestration_no_changes"] is False
    assert progress["orchestration_next_required_stage"] == "FETCHING"
    assert progress["orchestration_elapsed_seconds"] >= 0
    assert _wm_snapshot(engine) == before_wm
    assert _pointer(engine) == before_pointer
    assert _snapshot_count(engine, run) == _snapshot_count(engine, PHASE7_BASE_RUN_ID)


# --- zero-row / no-change path ----------------------------------------------

def test_full_orchestration_zero_rows_ends_at_validating(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows(detected=False))
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"], odoo_client=fake, now=STAMP,
    )
    assert result["current_state"] == "VALIDATING"
    assert result["next_required_stage"] == "VALIDATING"
    assert result["manifest_rows"] == 0
    assert result["no_changes"] is True
    assert _run_row(engine, run)["status"] == "VALIDATING"
    progress = _progress(engine, run)
    assert progress["change_detection_complete"] is True
    assert progress["orchestration_no_changes"] is True
    assert progress["detection_manifest_row_count"] == 0


# --- idempotency and reuse --------------------------------------------------

def test_copy_forward_reuse_is_idempotent(engine):
    run = _create_run(engine, ["commercial"], start_preparing=True)
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    assert _snapshot_count(engine, run) == 1
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert result["manifest_rows"] == 3
    assert _snapshot_count(engine, run) == 1
    assert result["copy_forward_status"] == "COMPLETE"


def test_completed_orchestration_reuse_makes_no_odoo_calls(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    first = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    progress_before = _progress(engine, run)
    manifest_before = _manifest(engine, run)
    second = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert second["idempotent"] is True
    assert second["current_state"] == "FETCHING"
    assert second["manifest_rows"] == first["manifest_rows"] == 3
    assert _progress(engine, run) == progress_before
    assert _manifest(engine, run) == manifest_before


def test_already_at_validating_returns_idempotent(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    first = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows(detected=False)), now=STAMP,
    )
    assert first["current_state"] == "VALIDATING"
    second = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert second["idempotent"] is True
    assert second["current_state"] == "VALIDATING"
    assert second["no_changes"] is True


# --- shared-model domain selection ------------------------------------------

def test_shared_model_domain_selection_executes_each_model_once(engine):
    run = _create_run(engine, ALL_DOMAINS)
    _seed_watermarks(engine, ALL_MODELS)
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=ALL_DOMAINS,
        odoo_client=FakeOdoo(_all_domain_rows()), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert len(result["models_completed"]) == 12
    assert len(set(result["models_completed"])) == 12
    assert result["manifest_rows"] == 6
    progress = _progress(engine, run)
    assert progress["detection_models_planned"] == progress["detection_models_completed"]
    assert progress["detection_models_completed"] == result["models_completed"]


# --- read-only enforcement --------------------------------------------------

def test_odoo_read_only_enforcement_no_full_fetch_no_publication(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows())
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"], odoo_client=fake, now=STAMP,
    )
    assert fake.calls
    assert all(call.get("limit") is not None and call.get("fields") is not None for call in fake.calls)
    assert all("offset" not in call for call in fake.calls)
    with pytest.raises(AssertionError, match="complete Odoo reads"):
        fake.read("sale.order", [1])
    assert _pointer(engine) == PHASE7_BASE_RUN_ID
    assert _snapshot_count(engine, run) == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_change_detection_run")).scalar() == 1


# --- fail-closed input guards ------------------------------------------------

def test_wrong_company_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    with pytest.raises(OrchestrationError, match="different company"):
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=4, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )


def test_changed_domains_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    with pytest.raises(OrchestrationError, match="domains"):
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["warehouse"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )


def test_stale_pointer_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    _move_pointer(engine)
    with pytest.raises(OrchestrationError, match="stale"):
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=NoCallOdoo(), now=STAMP,
        )


def test_stale_base_snapshot_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    _move_pointer(engine)
    with pytest.raises(OrchestrationError, match="stale"):
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=NoCallOdoo(), now=STAMP,
        )


# --- partial detection and retry lineage ------------------------------------

def test_partial_detection_fails_closed_and_requires_linked_retry(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    failing = FakeOdoo(_rows(), fail_model="sale.order.line")
    with pytest.raises(OrchestrationError) as excinfo:
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=failing, now=STAMP,
        )
    assert excinfo.value.requires_new_retry is True
    row = _run_row(engine, run)
    assert row["status"] == "DETECTING_CHANGES"
    assert any(model == "sale.order" for model, _ in _manifest(engine, run))
    with engine.connect() as conn:
        header_status = conn.execute(
            text("SELECT status FROM ct_change_detection_run WHERE run_id=CAST(:run_id AS UUID)"),
            {"run_id": run},
        ).scalar()
    assert header_status == "RUNNING"
    with pytest.raises(OrchestrationError):
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    original_manifest = _manifest(engine, run)
    svc = RefreshRunStateService(_client(engine))
    svc.transition(run, "FAILED_TRANSIENT", failure_class="TRANSIENT", error_message="partial", now=STAMP)
    retry = svc.create_retry(run, now=STAMP)
    assert retry["retry_of_run_id"] == run
    assert retry["attempt"] == 2
    assert retry["run_id"] != run
    result = _orchestrator(engine).orchestrate(
        run_id=retry["run_id"], company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["manifest_rows"] == 3
    assert _manifest(engine, run) == original_manifest
    retry_manifest = _manifest(engine, retry["run_id"])
    assert len(retry_manifest) == 3
    assert all(model == "sale.order" or model == "sale.order.line" for model, _ in retry_manifest)


def test_failed_run_requires_linked_retry(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    svc = RefreshRunStateService(_client(engine))
    svc.transition(run, "FAILED_TRANSIENT", failure_class="TRANSIENT", error_message="boom", now=STAMP)
    with pytest.raises(OrchestrationError) as excinfo:
        _orchestrator(engine).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=NoCallOdoo(), now=STAMP,
        )
    assert excinfo.value.requires_new_retry is True


# --- concurrency and stale transitions --------------------------------------

def test_same_run_concurrency_preserves_evidence(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    barrier = Barrier(2)
    orch = _orchestrator(engine, hooks={"before_detection": lambda _: barrier.wait(timeout=30)})
    before_wm = _wm_snapshot(engine)
    before_pointer = _pointer(engine)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                orch.orchestrate,
                run_id=run, company_id=3, selected_domains=["commercial"],
                odoo_client=FakeOdoo(_rows()), now=STAMP,
            )
            for _ in range(2)
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("ok", future.result()))
            except Exception as exc:
                outcomes.append(("error", exc))
    assert any(outcome[0] == "ok" for outcome in outcomes)
    assert _run_row(engine, run)["status"] == "FETCHING"
    assert len(_manifest(engine, run)) == 3
    assert _wm_snapshot(engine) == before_wm
    assert _pointer(engine) == before_pointer


def test_stale_state_transition_protection(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    svc = RefreshRunStateService(_client(engine))
    with pytest.raises(ValueError, match="Invalid refresh transition"):
        svc.transition(run, "DETECTING_CHANGES", now=STAMP)
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["idempotent"] is True


# --- failure injection -------------------------------------------------------

def test_failure_before_copy_forward_resumes(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(RuntimeError, match="injected before_copy_forward"):
        _orchestrator(engine, hooks={"before_copy_forward": _boom}).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _run_row(engine, run)["status"] == "PREPARING"
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert _progress(engine, run)["orchestration_started_at"]


def test_failure_after_copy_forward_resumes_at_detection(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(RuntimeError, match="injected after_copy_forward"):
        _orchestrator(engine, hooks={"after_copy_forward": _boom}).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _run_row(engine, run)["status"] == "DETECTING_CHANGES"
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert _snapshot_count(engine, run) == 1


def test_failure_after_detection_resumes_without_odoo(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(RuntimeError, match="injected after_detection"):
        _orchestrator(engine, hooks={"after_detection": _boom}).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    row = _run_row(engine, run)
    assert row["status"] == "DETECTING_CHANGES"
    assert _progress(engine, run)["change_detection_complete"] is True
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["idempotent"] is True


def test_failure_during_finalize_resumes_at_boundary(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(RuntimeError, match="injected before_finalize"):
        _orchestrator(engine, hooks={"before_finalize": _boom}).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _run_row(engine, run)["status"] == "DETECTING_CHANGES"
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["idempotent"] is True


def test_failure_after_finalize_returns_idempotent(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(RuntimeError, match="injected after_finalize"):
        _orchestrator(engine, hooks={"after_finalize": _boom}).orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _run_row(engine, run)["status"] == "FETCHING"
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=NoCallOdoo(), now=STAMP,
    )
    assert result["current_state"] == "FETCHING"
    assert result["idempotent"] is True


# --- progress and immutability evidence -------------------------------------

def test_orchestration_progress_preserves_stage_evidence(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    progress = _progress(engine, run)
    assert progress["copy_forward_status"] == "COMPLETE"
    assert progress["copy_forward_finished_at"]
    assert progress["detection_contract_fingerprint"]
    assert progress["detection_completion_fingerprint"]
    assert progress["detection_scan_upper_exclusives"]
    assert progress["detection_model_row_counts"]
    assert progress["orchestration_selected_domains"] == sorted(["commercial"])
    assert progress["orchestration_current_stage"] == "FETCHING"
    assert progress["orchestration_last_completed_stage"] == "DETECTING_CHANGES"
    assert progress["orchestration_next_required_stage"] == "FETCHING"
    assert progress["orchestration_copy_forward_status"] == "COMPLETE"
    assert progress["orchestration_detection_status"] == "COMPLETE"
    assert progress["orchestration_manifest_rows"] == 3
    assert progress["orchestration_models_planned"] == ["sale.order", "sale.order.line"]
    assert progress["orchestration_models_completed"] == ["sale.order", "sale.order.line"]
    assert progress["orchestration_finished_at"]
    assert progress["orchestration_elapsed_seconds"] >= 0
    with engine.connect() as conn:
        header = conn.execute(
            text(
                """
                SELECT contract_fingerprint, completion_fingerprint, manifest_row_count
                FROM ct_change_detection_run WHERE run_id=CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run},
        ).mappings().first()
    assert header["contract_fingerprint"] == progress["detection_contract_fingerprint"]
    assert header["completion_fingerprint"] == progress["detection_completion_fingerprint"]
    assert header["manifest_row_count"] == 3


def test_immutability_snapshot_pointer_watermark(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    source_count = _snapshot_count(engine, PHASE7_BASE_RUN_ID)
    before_wm = _wm_snapshot(engine)
    before_pointer = _pointer(engine)
    _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert _snapshot_count(engine, PHASE7_BASE_RUN_ID) == source_count
    assert _snapshot_count(engine, run) == source_count
    assert _wm_snapshot(engine) == before_wm
    assert _pointer(engine) == before_pointer


def test_result_contract_is_complete(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    result = _orchestrator(engine).orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    expected = {
        "run_id", "company_id", "selected_domains", "current_state",
        "last_completed_stage", "next_required_stage", "copy_forward_status",
        "detection_status", "manifest_rows", "models_completed", "no_changes",
        "idempotent", "requires_new_retry", "base_snapshot_run_id", "candidate_run_id",
    }
    assert set(result) == expected
