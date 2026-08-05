"""CT-8E1 normal incremental coordinator, retry, bootstrap, and API tests.

These tests verify the durable normal path: run creation, cross-process
concurrency rejection, retry lineage, watermark bootstrap from the trusted
snapshot, and the router endpoints.  Real Odoo is never contacted.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine, text

from src.api import DASHBOARD_SESSION_COOKIE, app
from src.control_tower.refresh import (
    IncrementalRefreshCoordinator,
    RefreshAlreadyRunning,
    _latest_retryable_run,
    find_active_durable_run,
)
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.router import service_dependency
from src.control_tower.watermarks import bootstrap_watermarks_from_trusted_snapshot
from src.dashboard_auth import sign_dashboard_session
from tests.test_control_tower_change_detection_postgres import _upgrade_003
from tests.test_control_tower_fetch_apply_postgres import _upgrade_004, _upgrade_005
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


def _client(engine):
    return SimpleNamespace(engine=engine)


class _TestPg:
    """PostgresClient-compatible facade backed by the disposable test engine."""

    def __init__(self, engine):
        self.engine = engine

    def close(self):
        self.engine.dispose()


def _coordinator(engine):
    return IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))


@pytest.fixture
def engine():
    db = create_engine(POSTGRES_URL, pool_pre_ping=True)
    _bootstrap_phase7(db)
    _upgrade(db)
    _upgrade_003()
    _upgrade_004()
    _upgrade_005()
    try:
        yield db
    finally:
        with db.begin() as conn:
            for table in (
                "ct_fetch_apply_batch", "ct_fetch_apply_evidence",
                "ct_fetch_apply_run", "ct_change_manifest", "ct_change_detection_run",
                "ct_control_tower_watermark", "ct_parent_reconciliation_queue",
                "ct_parent_reconciliation_cursor", "ct_published_snapshot",
                "ct_native_record_snapshot", "ct_document_link",
                "ct_extraction_run", "alembic_version",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
        db.dispose()


def _run_row(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT run_id::text, company_id, status, stage, base_snapshot_run_id::text,
                       progress, requested_by, selected_domains, attempt, retry_of_run_id::text
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
    return dict(row)


def _enqueue_sets(engine, run_id, count, *, start_parent_id=7001):
    """Insert `count` pending reconciliation sets attributed to the run."""
    with engine.begin() as conn:
        for offset in range(count):
            conn.execute(
                text(
                    """
                    INSERT INTO ct_parent_reconciliation_queue
                        (company_id, parent_model, parent_id, child_model, reason,
                         source_run_id, generation, last_touched_at, created_at, updated_at)
                    VALUES (3, 'sale.order', :parent_id, 'sale.order.line', 'changed_child_set',
                            CAST(:run_id AS UUID), 1, :now, :now, :now)
                    ON CONFLICT (company_id, parent_model, parent_id, child_model) DO UPDATE SET
                        reason = EXCLUDED.reason, source_run_id = EXCLUDED.source_run_id,
                        generation = ct_parent_reconciliation_queue.generation + 1,
                        last_touched_at = EXCLUDED.last_touched_at,
                        updated_at = EXCLUDED.updated_at,
                        status = 'PENDING'
                    """
                ),
                {"parent_id": start_parent_id + offset, "run_id": run_id, "now": STAMP},
            )


def _queue_counts(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed
                FROM ct_parent_reconciliation_queue
                WHERE source_run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
    return int(row["total"]), int(row["completed"])


def _pointer(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")
        ).scalar()


def _wm_statuses(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT model, status FROM ct_control_tower_watermark WHERE company_id=3 ORDER BY model
        """)).mappings().all()
    return {row["model"]: row["status"] for row in rows}


def _approved_models():
    from src.control_tower.relation_extractor import MODEL_SPECS
    return [spec.model for spec in MODEL_SPECS]


def _seed_full_model_evidence(engine, *, models=None):
    """Insert minimal trusted snapshot evidence for every required model."""
    from src.control_tower.relation_extractor import MODEL_SPECS

    models = models or [spec.model for spec in MODEL_SPECS]
    with engine.begin() as conn:
        for index, model in enumerate(models):
            record_id = 700000 + index
            conn.execute(
                text(
                    """
                    INSERT INTO public.ct_native_record_snapshot
                        (extraction_run_id, model, record_id, document_number, state,
                         company_id, company_name, write_date, payload, extracted_at)
                    VALUES (CAST(:run_id AS UUID), :model, :record_id, :document_number,
                            'sale', 3, 'PT Nobi Putra Angkasa', :write_date,
                            CAST(:payload AS JSONB), :extracted_at)
                    ON CONFLICT (extraction_run_id, model, record_id) DO NOTHING
                    """
                ),
                {
                    "run_id": PHASE7_BASE_RUN_ID,
                    "model": model,
                    "record_id": record_id,
                    "document_number": f"{model}-evidence",
                    "write_date": datetime(2026, 1, 1, 9, 55),
                    "payload": json.dumps({"id": record_id, "name": f"{model}-evidence"}),
                    "extracted_at": STAMP,
                },
            )


def _make_active_durable_run(engine, status="REQUESTED"):
    svc = RefreshRunStateService(_client(engine))
    run = svc.create_run(company_id=3, selected_domains=["commercial"], requested_by="tester", now=STAMP)
    if status in {"FAILED_TRANSIENT", "INTERRUPTED"}:
        svc.transition(run["run_id"], "PREPARING", now=STAMP)
        if status == "FAILED_TRANSIENT":
            svc.transition(run["run_id"], "FAILED_TRANSIENT", failure_class="TRANSIENT", error_message="boom", now=STAMP)
        else:
            svc.transition(run["run_id"], "INTERRUPTED", failure_class="INTERRUPTED", error_message="interrupted", now=STAMP)
        return run["run_id"]
    if status != "REQUESTED":
        for target in ("PREPARING", "DETECTING_CHANGES", "FETCHING", "RECONCILING", "VALIDATING"):
            svc.transition(run["run_id"], target, now=STAMP)
            if target == status:
                break
    return run["run_id"]


# --- durable run detection and concurrency -----------------------------------

def test_find_active_durable_run_detects_across_rows(engine):
    run_id = _make_active_durable_run(engine, status="FETCHING")
    active = find_active_durable_run(engine, company_id=3)
    assert active is not None
    assert active["run_id"] == run_id


def test_find_active_durable_run_none_after_terminal(engine):
    run_id = _make_active_durable_run(engine, status="PREPARING")
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_extraction_run SET status='SUCCEEDED', stage='SUCCEEDED',
                completed_at=:now, finished_at=:now, published_at=:now
            WHERE run_id = CAST(:run_id AS UUID)
        """), {"run_id": run_id, "now": STAMP})
    assert find_active_durable_run(engine, company_id=3) is None


def test_coordinator_start_rejects_durable_active_run(engine, monkeypatch):
    existing = _make_active_durable_run(engine, status="DETECTING_CHANGES")
    coordinator = IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))
    monkeypatch.setattr(coordinator, "_start_thread", lambda **kwargs: None)
    with pytest.raises(RefreshAlreadyRunning):
        coordinator.start(requested_by="tester", company_id=3)
    assert coordinator.status()["run_id"] is None


def test_coordinator_start_creates_run_and_accepts(engine, monkeypatch):
    coordinator = IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))
    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(coordinator, "_start_thread", fake_start)
    result = coordinator.start(requested_by="admin", company_id=3, selected_domains=["commercial"])
    assert result["status"] == "ACCEPTED"
    assert captured["requested_by"] == "admin"
    row = _run_row(engine, result["run_id"])
    assert row["status"] == "REQUESTED"
    assert row["requested_by"] == "admin"


def _count_active_runs(engine):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT COUNT(*) FROM ct_extraction_run
            WHERE company_id = 3 AND status IN (
                'REQUESTED','PREPARING','DETECTING_CHANGES','FETCHING','RECONCILING',
                'VALIDATING','REFRESHING_DERIVED_DATA','PUBLISHING'
            )
        """)).scalar()


def test_atomic_single_active_run_creation_across_connections(engine, monkeypatch):
    """Two simultaneous start attempts must create exactly one active run."""
    barrier = Barrier(2)
    outcomes = {}

    def attempt(label):
        coordinator = IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))
        monkeypatch.setattr(coordinator, "_start_thread", lambda **kwargs: None)
        barrier.wait(timeout=30)
        try:
            result = coordinator.start(requested_by=f"user-{label}", company_id=3, selected_domains=["commercial"])
            outcomes[label] = ("ok", result["run_id"])
        except Exception as exc:
            outcomes[label] = ("error", type(exc).__name__)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, label) for label in ("a", "b")]
        for future in futures:
            future.result(timeout=60)

    results = list(outcomes.values())
    assert sum(1 for status, _ in results if status == "ok") == 1
    assert sum(1 for status, _ in results if status == "error") == 1
    assert any(name == "RefreshAlreadyRunning" for _, name in results if isinstance(name, str) and _ == "error")
    assert _count_active_runs(engine) == 1


def test_latest_retryable_run_requires_transient_or_interrupted(engine):
    transient = _make_active_durable_run(engine, status="FAILED_TRANSIENT")
    assert _latest_retryable_run(engine, company_id=3)["run_id"] == transient
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_extraction_run SET status='FAILED_PERMANENT', failure_class='PERMANENT'
            WHERE run_id = CAST(:run_id AS UUID)
        """), {"run_id": transient})
    interrupted = _make_active_durable_run(engine, status="INTERRUPTED")
    latest = _latest_retryable_run(engine, company_id=3)
    assert latest["run_id"] == interrupted


def test_retry_creates_linked_run_and_does_not_publish(engine, monkeypatch):
    transient = _make_active_durable_run(engine, status="FAILED_TRANSIENT")
    coordinator = IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))
    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(coordinator, "_start_thread", fake_start)
    result = coordinator.retry(requested_by="admin", company_id=3)
    assert result["status"] == "ACCEPTED"
    assert result["retry_of_run_id"] == transient
    retry_row = _run_row(engine, result["run_id"])
    assert retry_row["retry_of_run_id"] == transient
    assert retry_row["attempt"] == 2
    assert retry_row["base_snapshot_run_id"] == PHASE7_BASE_RUN_ID


def test_retry_rejects_when_no_eligible_run(engine, monkeypatch):
    coordinator = IncrementalRefreshCoordinator(postgres_factory=lambda: _TestPg(engine))
    with pytest.raises(Exception):
        coordinator.retry(requested_by="admin", company_id=3)


# --- watermark bootstrap -----------------------------------------------------

def test_bootstrap_watermarks_from_trusted_snapshot(engine):
    _seed_full_model_evidence(engine)
    result = bootstrap_watermarks_from_trusted_snapshot(engine, company_id=3)
    assert result["published_run_id"] == PHASE7_BASE_RUN_ID
    assert result["pointer_moved"] is False
    assert result["odoo_contacted"] is False
    assert result["models_missing_evidence"] == []
    statuses = _wm_statuses(engine)
    for model in _approved_models():
        assert statuses.get(model) == "READY"
    assert _pointer(engine) == PHASE7_BASE_RUN_ID


def test_bootstrap_is_idempotent(engine):
    _seed_full_model_evidence(engine)
    bootstrap_watermarks_from_trusted_snapshot(engine, company_id=3)
    first = bootstrap_watermarks_from_trusted_snapshot(engine, company_id=3)
    assert first["models_adopted"] == []
    assert set(first["models_already_ready"]) == set(_approved_models())


def test_bootstrap_missing_model_writes_nothing(engine):
    """All-or-nothing: one missing model must leave all watermarks unwritten."""
    _seed_full_model_evidence(engine)
    # Remove evidence for one required model only.
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM ct_native_record_snapshot WHERE extraction_run_id = CAST(:run_id AS UUID) AND model = 'sale.order.line'"),
            {"run_id": PHASE7_BASE_RUN_ID},
        )
    before = _wm_statuses(engine)
    with pytest.raises(ValueError, match="sale.order.line"):
        bootstrap_watermarks_from_trusted_snapshot(engine, company_id=3)
    after = _wm_statuses(engine)
    assert after == before
    assert _pointer(engine) == PHASE7_BASE_RUN_ID


def test_bootstrap_requires_published_pointer(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ct_published_snapshot WHERE company_id=3"))
    with pytest.raises(ValueError, match="published trusted snapshot"):
        bootstrap_watermarks_from_trusted_snapshot(engine, company_id=3)


# --- router endpoints --------------------------------------------------------

async def _asgi_request(method, path, cookies=None, body=b""):
    parsed = urlsplit(path)
    headers = []
    if cookies:
        headers.append((b"cookie", "; ".join(f"{key}={value}" for key, value in cookies.items()).encode()))

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        return message

    status_holder = {}
    body_holder = bytearray()

    async def capture(message):
        if message["type"] == "http.response.start":
            status_holder["status"] = message["status"]
        elif message["type"] == "http.response.body":
            body_holder.extend(message.get("body", b""))

    await app(
        {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": parsed.path,
            "raw_path": parsed.path.encode(), "query_string": parsed.query.encode(),
            "headers": headers, "server": ("testserver", 80),
            "client": ("testclient", 50000), "root_path": "",
        },
        receive, capture,
    )
    return status_holder.get("status"), bytes(body_holder)


class StubPG:
    def __init__(self, engine):
        self.engine = engine


class StubRefreshService:
    def __init__(self, engine):
        self.pg = StubPG(engine)

    def health(self):
        return {
            "status": "READY",
            "company_id": 3,
            "latest_trusted_run_id": PHASE7_BASE_RUN_ID,
            "latest_trusted_completed_at": STAMP.isoformat(),
            "latest_attempt": None,
            "latest_refresh_attempt_status": None,
            "latest_refresh_candidate_pending": False,
            "latest_refresh_attempt_stale": False,
            "latest_failure_message": None,
            "serving_older_trusted_snapshot": False,
            "freshness": "CURRENT",
            "freshness_classification": {"state": "CURRENT"},
        }

    def close(self):
        pass


class StubCoordinator:
    def __init__(self, *, retry_result=None, retry_error=None):
        self.retry_result = retry_result or {"run_id": "r-1", "status": "ACCEPTED", "company_id": 3}
        self.retry_error = retry_error

    def status(self):
        return {"active_request": False, "run_id": None, "last_result": None}

    def retry(self, **kwargs):
        if self.retry_error:
            raise self.retry_error
        return self.retry_result


def _admin_session():
    return sign_dashboard_session(
        {"dashboard_authenticated": True, "dashboard_username": "admin", "dashboard_role": "admin"}
    )


def _user_session():
    return sign_dashboard_session(
        {"dashboard_authenticated": True, "dashboard_username": "reviewer"}
    )


def test_bootstrap_endpoint_admin_only(engine):
    _seed_full_model_evidence(engine)
    app.dependency_overrides[service_dependency] = lambda: StubRefreshService(engine)
    try:
        status, _ = asyncio.run(_asgi_request(
            "POST", "/api/control-tower/refresh/bootstrap-watermarks",
            cookies={DASHBOARD_SESSION_COOKIE: _user_session()},
        ))
        assert status == 403
        status, body = asyncio.run(_asgi_request(
            "POST", "/api/control-tower/refresh/bootstrap-watermarks",
            cookies={DASHBOARD_SESSION_COOKIE: _admin_session()},
        ))
        assert status == 200
        payload = json.loads(body)
        assert payload["pointer_moved"] is False
        assert payload["published_run_id"] == PHASE7_BASE_RUN_ID
    finally:
        app.dependency_overrides.pop(service_dependency, None)


def test_retry_endpoint_admin_only_and_delegates(engine, monkeypatch):
    import src.control_tower.router as router_module

    app.dependency_overrides[service_dependency] = lambda: StubRefreshService(engine)
    try:
        status, _ = asyncio.run(_asgi_request(
            "POST", "/api/control-tower/refresh/retry",
            cookies={DASHBOARD_SESSION_COOKIE: _user_session()},
        ))
        assert status == 403

        monkeypatch.setattr(router_module, "REFRESH_COORDINATOR", StubCoordinator())
        status, body = asyncio.run(_asgi_request(
            "POST", "/api/control-tower/refresh/retry",
            cookies={DASHBOARD_SESSION_COOKIE: _admin_session()},
        ))
        assert status == 202
        assert json.loads(body)["status"] == "ACCEPTED"

        monkeypatch.setattr(
            router_module, "REFRESH_COORDINATOR",
            StubCoordinator(retry_error=RefreshAlreadyRunning("A Control Tower refresh request is already active.")),
        )
        status, body = asyncio.run(_asgi_request(
            "POST", "/api/control-tower/refresh/retry",
            cookies={DASHBOARD_SESSION_COOKIE: _admin_session()},
        ))
        assert status == 409
        assert "already active" in json.loads(body)["detail"].lower()
    finally:
        app.dependency_overrides.pop(service_dependency, None)
        monkeypatch.undo()


def test_status_endpoint_exposes_retry_flag(engine, monkeypatch):
    import src.control_tower.router as router_module

    class Health:
        def __init__(self, status_value):
            self.status_value = status_value

        def health(self):
            return {
                "status": "READY",
                "company_id": 3,
                "latest_trusted_run_id": PHASE7_BASE_RUN_ID,
                "latest_trusted_completed_at": STAMP.isoformat(),
                "latest_attempt": {"run_id": "r-1", "status": self.status_value},
                "latest_refresh_attempt_status": self.status_value,
                "latest_refresh_candidate_pending": False,
                "latest_refresh_attempt_stale": False,
                "latest_failure_message": None,
                "serving_older_trusted_snapshot": False,
                "freshness": "CURRENT",
                "freshness_classification": {"state": "CURRENT"},
            }

        def close(self):
            pass

    app.dependency_overrides[service_dependency] = lambda: Health("FAILED_TRANSIENT")
    monkeypatch.setattr(router_module, "REFRESH_COORDINATOR", StubCoordinator())
    try:
        status, body = asyncio.run(_asgi_request(
            "GET", "/api/control-tower/refresh",
            cookies={DASHBOARD_SESSION_COOKIE: _admin_session()},
        ))
        assert status == 200
        payload = json.loads(body)
        assert payload["retryable"] is True
        assert payload["can_retry"] is True
    finally:
        app.dependency_overrides.pop(service_dependency, None)
        monkeypatch.undo()
