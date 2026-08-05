"""CT-8D1 visible refresh projection and endpoint tests.

These tests never contact Odoo or an office database: the coordinator is
stubbed and the service dependency is replaced with a fixture-shaped stub.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlsplit

import pytest

from src.api import DASHBOARD_SESSION_COOKIE, app
from src.control_tower.refresh import RefreshAlreadyRunning
from src.control_tower.refresh_ui import refresh_ui_projection
from src.control_tower.router import service_dependency
from src.dashboard_auth import sign_dashboard_session


NOW = datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc)
TRUSTED_AT = "2026-08-05T01:00:00+00:00"
TRUSTED_RUN_ID = "00000000-0000-4000-8000-000000000101"


def _attempt(
    *,
    status,
    started_at=NOW - timedelta(minutes=5),
    model_counts=None,
    error_message=None,
    duration_seconds=None,
):
    return {
        "run_id": "00000000-0000-4000-8000-000000000102",
        "status": status,
        "started_at": started_at.isoformat(),
        "completed_at": NOW.isoformat() if status == "COMPLETED" else None,
        "finished_at": NOW.isoformat() if status in {"COMPLETED", "FAILED", "ABORTED"} else None,
        "duration_seconds": duration_seconds,
        "company_id": 3,
        "error_message": error_message,
        "model_counts": model_counts,
        "trigger": "manual",
        "requested_by": "admin",
    }


def _health(**overrides):
    health = {
        "status": "READY",
        "company_id": 3,
        "latest_trusted_run_id": TRUSTED_RUN_ID,
        "latest_trusted_completed_at": TRUSTED_AT,
        "latest_attempt": None,
        "latest_refresh_attempt_status": None,
        "latest_refresh_candidate_pending": False,
        "latest_refresh_attempt_stale": False,
        "latest_attempt_start_at": None,
        "latest_attempt_finish_at": None,
        "latest_attempt_duration_seconds": None,
        "latest_failure_message": None,
        "serving_older_trusted_snapshot": False,
        "freshness": "CURRENT",
        "freshness_classification": {"state": "CURRENT"},
    }
    health.update(overrides)
    return health


def _ui(health, coordinator=None, can_refresh=True):
    return refresh_ui_projection(health, coordinator or {"active_request": False}, can_refresh)


def test_reading_stage_uses_durable_started_at_and_no_fabricated_counts():
    ui = _ui(_health(
        latest_attempt=_attempt(status="RUNNING", duration_seconds=None),
        latest_refresh_attempt_status="RUNNING",
    ))
    assert ui["status"] == "READING"
    assert ui["stage_label"] == "Membaca perubahan dari Odoo"
    assert ui["active"] is True
    assert ui["outcome"] is None
    assert ui["counts"] is None
    assert ui["elapsed_seconds"] is not None
    assert ui["trusted"]["run_id"] == TRUSTED_RUN_ID


def test_checking_stage_exposes_durable_model_counts():
    ui = _ui(_health(
        latest_attempt=_attempt(
            status="READY_FOR_PUBLISH",
            model_counts={"sale.order": 10, "mrp.production": 4},
            duration_seconds=42.5,
        ),
        latest_refresh_attempt_status="READY_FOR_PUBLISH",
    ))
    assert ui["status"] == "CHECKING"
    assert ui["stage_label"] == "Memeriksa hasil"
    assert ui["counts"] == {"models_completed": 2, "records": 14}
    assert ui["elapsed_seconds"] == 42.5


def test_success_maps_completed_attempt_to_done():
    ui = _ui(_health(
        latest_attempt=_attempt(status="COMPLETED"),
        latest_refresh_attempt_status="COMPLETED",
    ))
    assert ui["status"] == "DONE"
    assert ui["outcome"] == "SUCCESS"
    assert ui["stage_label"] == "Selesai"
    assert ui["message"] == "Pembaruan selesai. Control Tower menampilkan snapshot terbaru yang berhasil."


def test_failure_keeps_trusted_snapshot_and_sanitized_diagnostic():
    ui = _ui(_health(
        latest_attempt=_attempt(
            status="FAILED",
            error_message="connection refused: postgresql://[redacted]",
        ),
        latest_refresh_attempt_status="FAILED",
        latest_failure_message="Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil.",
    ))
    assert ui["status"] == "FAILED"
    assert ui["outcome"] == "FAILED"
    assert ui["stage_label"] == "Gagal"
    assert ui["message"] == "Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil."
    assert ui["trusted"]["timestamp"] == TRUSTED_AT
    assert ui["latest_attempt"]["error_message"] == "connection refused: postgresql://[redacted]"


def test_stale_attempt_is_interrupted_not_success():
    ui = _ui(_health(
        latest_attempt=_attempt(status="RUNNING", started_at=NOW - timedelta(hours=2)),
        latest_refresh_attempt_status="RUNNING",
        latest_refresh_attempt_stale=True,
        latest_failure_message="Refresh attempt exceeded the stale threshold; administrator recovery is required.",
    ))
    assert ui["status"] == "STALE"
    assert ui["outcome"] == "INTERRUPTED"
    assert ui["active"] is False


def test_no_completed_snapshot_is_truthful():
    ui = _ui(_health(latest_trusted_run_id=None, latest_trusted_completed_at=None))
    assert ui["status"] == "NO_COMPLETED_EXTRACTION"
    assert ui["trusted"] is None
    assert "Belum ada snapshot" in ui["message"]


def test_idle_without_attempt_is_waiting():
    ui = _ui(_health())
    assert ui["status"] == "IDLE"
    assert ui["stage_label"] == "Menunggu pembaruan"
    assert ui["active"] is False


def test_can_refresh_flows_through_and_active_coordinator_wins():
    ui = _ui(
        _health(),
        coordinator={"active_request": True},
        can_refresh=False,
    )
    assert ui["active"] is True
    assert ui["can_refresh"] is False


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
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": parsed.path,
            "raw_path": parsed.path.encode(),
            "query_string": parsed.query.encode(),
            "headers": headers,
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "root_path": "",
        },
        receive,
        capture,
    )
    return status_holder.get("status"), bytes(body_holder)


class StubRefreshService:
    def __init__(self, health_payload):
        self._health = health_payload

    def health(self):
        return dict(self._health)

    def close(self):
        pass


class StubCoordinator:
    def __init__(self, *, raise_conflict=False, start_result=None):
        self.raise_conflict = raise_conflict
        self.start_result = start_result or {"job_id": "job-1", "status": "ACCEPTED", "company_id": 3}

    def status(self):
        return {"active_request": False, "job_id": None, "last_result": None}

    def start(self, **kwargs):
        if self.raise_conflict:
            raise RefreshAlreadyRunning("A Control Tower refresh request is already active.")
        return self.start_result


def _admin_session():
    return sign_dashboard_session(
        {"dashboard_authenticated": True, "dashboard_username": "admin", "dashboard_role": "admin"}
    )


def _user_session():
    return sign_dashboard_session(
        {"dashboard_authenticated": True, "dashboard_username": "reviewer"}
    )


def test_refresh_status_projection_endpoint(monkeypatch):
    service = StubRefreshService(_health(
        latest_attempt=_attempt(status="COMPLETED"),
        latest_refresh_attempt_status="COMPLETED",
    ))
    app.dependency_overrides[service_dependency] = lambda: service
    try:
        status, body = asyncio.run(_asgi_request(
            "GET", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _admin_session()}
        ))
        assert status == 200
        payload = json.loads(body)
        assert payload["latest_trusted_refresh_at"] == TRUSTED_AT
        assert payload["displayed_snapshot_run_id"] == TRUSTED_RUN_ID
        assert payload["refresh_ui"]["status"] == "DONE"
        assert payload["refresh_ui"]["can_refresh"] is True
    finally:
        app.dependency_overrides.pop(service_dependency, None)


def test_refresh_status_for_non_admin_has_no_refresh_right(monkeypatch):
    service = StubRefreshService(_health())
    app.dependency_overrides[service_dependency] = lambda: service
    try:
        status, body = asyncio.run(_asgi_request(
            "GET", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _user_session()}
        ))
        assert status == 200
        assert json.loads(body)["refresh_ui"]["can_refresh"] is False
    finally:
        app.dependency_overrides.pop(service_dependency, None)


def test_refresh_status_unauthenticated(monkeypatch):
    service = StubRefreshService(_health())
    app.dependency_overrides[service_dependency] = lambda: service
    try:
        status, _ = asyncio.run(_asgi_request("GET", "/api/control-tower/refresh"))
        assert status == 401
    finally:
        app.dependency_overrides.pop(service_dependency, None)


def test_admin_post_refresh_accepted(monkeypatch):
    import src.control_tower.router as router_module

    monkeypatch.setattr(router_module, "REFRESH_COORDINATOR", StubCoordinator())
    status, body = asyncio.run(_asgi_request(
        "POST", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _admin_session()}
    ))
    assert status == 202
    assert json.loads(body)["status"] == "ACCEPTED"


def test_non_admin_post_refresh_forbidden(monkeypatch):
    status, _ = asyncio.run(_asgi_request(
        "POST", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _user_session()}
    ))
    assert status == 403


def test_unauthenticated_post_refresh_rejected():
    status, _ = asyncio.run(_asgi_request("POST", "/api/control-tower/refresh"))
    assert status == 401


def test_duplicate_refresh_conflict(monkeypatch):
    import src.control_tower.router as router_module

    monkeypatch.setattr(router_module, "REFRESH_COORDINATOR", StubCoordinator(raise_conflict=True))
    status, body = asyncio.run(_asgi_request(
        "POST", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _admin_session()}
    ))
    assert status == 409
    assert "already active" in json.loads(body)["detail"].lower()


@pytest.mark.parametrize("field", ["latest_trusted_refresh_at", "displayed_snapshot_run_id", "refresh_ui"])
def test_refresh_endpoint_exposes_ui_projection_fields(monkeypatch, field):
    service = StubRefreshService(_health())
    app.dependency_overrides[service_dependency] = lambda: service
    try:
        status, body = asyncio.run(_asgi_request(
            "GET", "/api/control-tower/refresh", cookies={DASHBOARD_SESSION_COOKIE: _admin_session()}
        ))
        assert status == 200
        assert field in json.loads(body)
    finally:
        app.dependency_overrides.pop(service_dependency, None)
