import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request, Response

from src.api import (
    CONTROL_TOWER_COMPATIBILITY_PATH,
    CONTROL_TOWER_PATH,
    DASHBOARD_SESSION_COOKIE,
    DEFAULT_DASHBOARD_PATH,
    PROTECTED_PAGE_PATHS,
    app,
    control_tower_compatibility_redirect,
    control_tower_page,
    dashboard_auth_middleware,
    safe_control_tower_path,
    safe_next_path,
    sign_dashboard_session,
)
from src.control_tower.router import exception_worklist, require_dashboard_auth
from src.control_tower.service import ControlTowerService
from src.control_tower_app import app as compatibility_app


def service_double() -> ControlTowerService:
    return object.__new__(ControlTowerService)


def test_canonical_app_exposes_protected_control_tower() -> None:
    openapi_paths = app.openapi()["paths"]

    assert compatibility_app is app
    assert CONTROL_TOWER_PATH in PROTECTED_PAGE_PATHS
    assert CONTROL_TOWER_COMPATIBILITY_PATH in PROTECTED_PAGE_PATHS
    assert safe_next_path(CONTROL_TOWER_COMPATIBILITY_PATH) == CONTROL_TOWER_PATH
    assert "/api/control-tower/health" in openapi_paths
    assert "/api/control-tower/journey/{root_model}/{root_id}" in openapi_paths


def test_control_tower_safe_return_url_preserves_supported_state_only() -> None:
    requested = (
        "/dashboard/control-tower?view=exceptions&classification=historical"
        "&document=PO-TEST&unsupported=drop-me"
    )

    assert safe_control_tower_path(requested) == (
        "/control-tower?view=exceptions&classification=historical&document=PO-TEST"
    )
    assert safe_next_path(requested) == (
        "/control-tower?view=exceptions&classification=historical&document=PO-TEST"
    )
    assert safe_next_path("https://example.com/control-tower") == DEFAULT_DASHBOARD_PATH
    assert safe_next_path("//example.com/control-tower") == DEFAULT_DASHBOARD_PATH


def test_control_tower_routes_reuse_signed_session_and_redirect_compatibility() -> None:
    def request(path: str, query: str = "", cookie: str = "") -> Request:
        headers = [(b"cookie", cookie.encode("ascii"))] if cookie else []
        return Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": query.encode("ascii"),
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("127.0.0.1", 8000),
            }
        )

    async def downstream(_: Request) -> Response:
        return Response(status_code=204)

    query = "view=exceptions&classification=historical"
    unauthenticated = asyncio.run(
        dashboard_auth_middleware(request(CONTROL_TOWER_PATH, query), downstream)
    )
    assert unauthenticated.status_code == 307
    assert unauthenticated.headers["location"].startswith("/login?")
    assert "%2Fcontrol-tower" in unauthenticated.headers["location"]

    token = sign_dashboard_session({"dashboard_authenticated": True, "dashboard_username": "test"})
    authenticated = asyncio.run(
        dashboard_auth_middleware(
            request(CONTROL_TOWER_PATH, query, f"{DASHBOARD_SESSION_COOKIE}={token}"),
            downstream,
        )
    )
    standalone = asyncio.run(control_tower_page())
    compatibility = asyncio.run(
        control_tower_compatibility_redirect(
            request(
                CONTROL_TOWER_COMPATIBILITY_PATH,
                "view=exceptions&classification=historical&unsupported=x",
                f"{DASHBOARD_SESSION_COOKIE}={token}",
            )
        )
    )

    assert authenticated.status_code == 204
    assert Path(standalone.path).name == "index.html"
    assert compatibility.status_code == 307
    assert compatibility.headers["location"] == (
        "/control-tower?view=exceptions&classification=historical"
    )

    with pytest.raises(HTTPException) as exc_info:
        require_dashboard_auth(request("/api/control-tower/health"))
    assert exc_info.value.status_code == 401


def test_control_tower_assets_are_standalone() -> None:
    asset_root = Path("src/static/control-tower")

    assert (asset_root / "index.html").is_file()
    assert (asset_root / "control-tower.css").is_file()
    assert (asset_root / "control-tower-adapter.js").is_file()
    assert (asset_root / "control-tower.js").is_file()
    assert not Path("src/static/dashboard/control-tower-adapter.js").exists()


def test_exception_query_keeps_filters_server_side() -> None:
    service = service_double()
    service._rows = MagicMock(return_value=[])
    service._row = MagicMock(return_value={"total": 0})

    result = service.exceptions(
        rule_id="SO-CANCEL-001",
        status="MISMATCH",
        severity="HIGH",
        owner="Multi-owner",
        process="Control Point Cancellation",
        document="  SO/%_  ",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 21),
        limit=25,
        offset=50,
    )

    query, params = service._rows.call_args.args
    assert "sop_section = :process" in query
    assert "POSITION(LOWER(:document)" in query
    assert "detected_at::date >= :date_from" in query
    assert "detected_at::date <= :date_to" in query
    assert params["document"] == "SO/%_"
    assert params["limit"] == 25
    assert params["offset"] == 50
    assert result == {"rows": [], "total": 0, "limit": 25, "offset": 50}


def test_exception_route_rejects_reversed_date_range() -> None:
    service = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        exception_worklist(
            date_from=date(2026, 7, 21),
            date_to=date(2026, 1, 1),
            service=service,
        )

    assert exc_info.value.status_code == 422
    service.exceptions.assert_not_called()


def test_journey_omits_raw_payload_and_adds_linked_states() -> None:
    service = service_double()
    service._row = MagicMock(
        return_value={
            "model": "purchase.order",
            "record_id": 1,
            "document_number": "PO-TEST",
            "state": "cancel",
        }
    )
    service._rows = MagicMock(side_effect=[[], []])

    result = service.journey("purchase.order", 1)

    root_query = service._row.call_args.args[0]
    link_query = service._rows.call_args_list[0].args[0]
    assert "payload" not in root_query.lower()
    assert "parent_snapshot.state AS parent_state" in link_query
    assert "child_snapshot.state AS child_state" in link_query
    assert "DIRECT_RELATION" in link_query
    assert "DERIVED_PATH" in link_query
    assert result["root"]["document_number"] == "PO-TEST"


def test_io_health_returns_server_aggregate() -> None:
    service = service_double()
    service._rows = MagicMock(return_value=[])
    service._row = MagicMock(
        side_effect=[
            {"total": 824},
            {
                "internal_order_roots": 118,
                "product_uom_rows": 824,
                "production_evidence_gaps": 284,
                "utilization_evidence_gaps": 13,
            },
        ]
    )

    result = service.io_health(limit=1)

    assert result["total"] == 824
    assert result["summary"]["internal_order_roots"] == 118
    assert result["summary"]["product_uom_rows"] == 824
    assert "COUNT(DISTINCT internal_order_id)" in service._row.call_args_list[1].args[0]
