"""FastAPI router for the read-only Control Tower office pilot."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from src.control_tower.refresh import (
    DURABLE_ACTIVE_STATES,
    REFRESH_COORDINATOR,
    RefreshAlreadyRunning,
    RefreshLifecycleError,
    find_active_durable_run,
    recover_stale_run,
    sanitize_diagnostic,
)
from src.control_tower.refresh_ui import refresh_ui_projection
from src.control_tower.service import (
    COMPANY_ID,
    ControlTowerDatabaseUnavailable,
    ControlTowerService,
)
from src.dashboard_auth import is_admin, is_authenticated, session_payload


router = APIRouter(prefix="/api/control-tower", tags=["Control Tower"])


def require_dashboard_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )


def require_dashboard_admin(request: Request) -> None:
    require_dashboard_auth(request)
    if not is_admin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission required for refresh.",
        )


def service_dependency():
    service = ControlTowerService()
    try:
        yield service
    finally:
        service.close()


@router.get("/health", dependencies=[Depends(require_dashboard_auth)])
def control_tower_health(service: ControlTowerService = Depends(service_dependency)):
    return service.health()


@router.get("/refresh", dependencies=[Depends(require_dashboard_auth)])
def control_tower_refresh_status(
    request: Request,
    service: ControlTowerService = Depends(service_dependency),
):
    health = service.health()
    coordinator = REFRESH_COORDINATOR.status()
    attempt_status = health.get("latest_refresh_attempt_status")
    candidate_pending = attempt_status in {"READY_FOR_PUBLISH", "PUBLISHING"}
    stale_attempt = bool(health.get("latest_refresh_attempt_stale"))
    active = (
        coordinator["active_request"]
        or (attempt_status in DURABLE_ACTIVE_STATES | {"RUNNING", "READY_FOR_PUBLISH"} and not stale_attempt)
    )
    can_refresh = is_admin(request) and not active and not stale_attempt and not candidate_pending
    latest_attempt = health.get("latest_attempt") or {}
    can_recover_stale = (
        is_admin(request)
        and bool(stale_attempt)
        and not coordinator["active_request"]
        and bool(latest_attempt.get("run_id"))
    )
    retryable_status = attempt_status in {"FAILED_TRANSIENT", "INTERRUPTED"}
    can_retry = (
        is_admin(request)
        and bool(retryable_status)
        and not coordinator["active_request"]
        and bool(latest_attempt.get("run_id"))
    )
    return {
        "company_id": COMPANY_ID,
        "active": active,
        "can_refresh": can_refresh,
        "can_recover_stale": can_recover_stale,
        "can_retry": can_retry,
        "candidate_pending": candidate_pending,
        "stale_attempt": stale_attempt,
        "retryable": bool(retryable_status),
        "coordinator": coordinator,
        "latest_attempt": health.get("latest_attempt"),
        "latest_trusted_run_id": health.get("latest_trusted_run_id"),
        "latest_trusted_refresh_at": health.get("latest_trusted_completed_at"),
        "displayed_snapshot_run_id": health.get("latest_trusted_run_id"),
        "serving_older_trusted_snapshot": health.get("serving_older_trusted_snapshot"),
        "freshness": health.get("freshness"),
        "freshness_classification": health.get("freshness_classification"),
        "refresh_ui": refresh_ui_projection(health, coordinator, can_refresh, can_recover_stale, can_retry),
    }


@router.post("/refresh/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_control_tower_refresh(
    request: Request,
    _: None = Depends(require_dashboard_admin),
):
    payload = session_payload(request) or {}
    requested_by = str(payload.get("dashboard_username") or "administrator")[:80]
    try:
        return REFRESH_COORDINATOR.retry(
            requested_by=requested_by,
            company_id=COMPANY_ID,
        )
    except RefreshAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RefreshLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=sanitize_diagnostic(str(exc)),
        ) from exc


@router.post("/refresh/bootstrap-watermarks", status_code=status.HTTP_200_OK)
def bootstrap_control_tower_watermarks(
    _: None = Depends(require_dashboard_admin),
    service: ControlTowerService = Depends(service_dependency),
):
    from src.control_tower.watermarks import bootstrap_watermarks_from_trusted_snapshot

    try:
        result = bootstrap_watermarks_from_trusted_snapshot(service.pg, company_id=COMPANY_ID)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=sanitize_diagnostic(str(exc)),
        ) from exc
    return result


@router.post("/refresh/recover", status_code=status.HTTP_200_OK)
def recover_stale_control_tower_refresh(
    request: Request,
    _: None = Depends(require_dashboard_admin),
    service: ControlTowerService = Depends(service_dependency),
):
    coordinator = REFRESH_COORDINATOR.status()
    if coordinator["active_request"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Control Tower refresh is already running.",
        )

    health = service.health()
    latest_attempt = health.get("latest_attempt") or {}
    stale_attempt = bool(health.get("latest_refresh_attempt_stale"))
    if not stale_attempt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No stale refresh attempt is available to close.",
        )
    run_id = latest_attempt.get("run_id")
    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The latest refresh attempt has no usable run identifier.",
        )
    payload = session_payload(request) or {}
    requested_by = str(payload.get("dashboard_username") or "administrator")[:80]
    try:
        result = recover_stale_run(
            service.pg,
            run_id=run_id,
            requested_by=requested_by,
            reason="Administrator closed stale refresh from Control Tower",
            company_id=COMPANY_ID,
        )
    except RefreshLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=sanitize_diagnostic(str(exc)),
        ) from exc

    return {
        "status": "RECOVERED",
        "run_id": run_id,
        "attempt_status": result.get("status"),
        "trusted_run_id": health.get("latest_trusted_run_id"),
    }


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
def trigger_control_tower_refresh(
    request: Request,
    _: None = Depends(require_dashboard_admin),
):
    payload = session_payload(request) or {}
    requested_by = str(payload.get("dashboard_username") or "administrator")[:80]
    try:
        return REFRESH_COORDINATOR.start(
            requested_by=requested_by,
            company_id=COMPANY_ID,
        )
    except RefreshAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/sop-validation", dependencies=[Depends(require_dashboard_auth)])
def sop_validation_summary(service: ControlTowerService = Depends(service_dependency)):
    return {
        "rows": service.validation_summary(),
        "meta": {
            "version": "v0.1.3",
            "meaning": "Data menguji konsistensi SOP; mismatch tidak otomatis membuktikan kesalahan user atau SOP.",
            "po_cancellation_scope": "Masalah Aktif 2026+ memakai purchase.order.date_order. Catatan Historis dan Tanggal PO Belum Tersedia tersedia terpisah.",
        },
    }


@router.get("/exceptions", dependencies=[Depends(require_dashboard_auth)])
def exception_worklist(
    rule_id: Optional[str] = Query(default=None),
    validation_status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    owner: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    return service.exceptions(
        rule_id=rule_id,
        status=validation_status,
        severity=severity,
        owner=owner,
        limit=limit,
        offset=offset,
    )


@router.get("/findings", dependencies=[Depends(require_dashboard_auth)])
def findings(
    affected_model: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    rule_code: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    return service.findings(
        affected_model=affected_model,
        category=category,
        rule_code=rule_code,
        limit=limit,
        offset=offset,
    )


@router.get("/evidence", dependencies=[Depends(require_dashboard_auth)])
def evidence(
    presentation_category: str = Query(default="MASALAH_AKTIF"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.evidence(
            presentation_category=presentation_category,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/temuan", dependencies=[Depends(require_dashboard_auth)])
def temuan(
    presentation_category: Optional[str] = Query(default=None),
    process_key: Optional[str] = Query(default=None),
    rule_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    sort: str = Query(default="attention"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.temuan(
            presentation_category=presentation_category,
            process_key=process_key,
            rule_id=rule_id,
            severity=severity,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/po-cancellation-scope", dependencies=[Depends(require_dashboard_auth)])
def po_cancellation_scope(
    date_scope: Optional[str] = Query(default=None),
    operational_exposure: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        result = service.po_cancellation_scope(
            date_scope=date_scope,
            operational_exposure=operational_exposure,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **result,
        "meta": {
            "meaning": "PO Sudah Dibatalkan, tetapi Penerimaan Barang Masih Terbuka. Hanya Masalah Aktif 2026+ masuk antrean operasional; Catatan Historis tetap tersedia untuk audit.",
            "date_scope_field": "purchase.order.date_order",
            "date_scope_boundary": "2026-01-01",
        },
    }


@router.get("/journey/{root_model}/{root_id}", dependencies=[Depends(require_dashboard_auth)])
def record_journey(
    root_model: str,
    root_id: int,
    service: ControlTowerService = Depends(service_dependency),
):
    result = service.journey(root_model, root_id)
    if result["root"] is None:
        raise HTTPException(status_code=404, detail="Record not found in latest completed extraction.")
    return result


@router.get("/io-health", dependencies=[Depends(require_dashboard_auth)])
def internal_order_health(
    production_status: Optional[str] = Query(default=None),
    utilization_status: Optional[str] = Query(default=None),
    confidence: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    return service.io_health(
        production_status=production_status,
        utilization_status=utilization_status,
        confidence=confidence,
        limit=limit,
        offset=offset,
    )
