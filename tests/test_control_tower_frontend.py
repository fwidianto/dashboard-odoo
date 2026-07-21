from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.api import PROTECTED_PAGE_PATHS, app, safe_next_path
from src.control_tower.router import exception_worklist
from src.control_tower.service import ControlTowerService
from src.control_tower_app import app as compatibility_app


def service_double() -> ControlTowerService:
    return object.__new__(ControlTowerService)


def test_canonical_app_exposes_protected_control_tower() -> None:
    openapi_paths = app.openapi()["paths"]

    assert compatibility_app is app
    assert "/dashboard/control-tower" in PROTECTED_PAGE_PATHS
    assert safe_next_path("/dashboard/control-tower") == "/dashboard/control-tower"
    assert "/api/control-tower/health" in openapi_paths
    assert "/api/control-tower/journey/{root_model}/{root_id}" in openapi_paths


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
