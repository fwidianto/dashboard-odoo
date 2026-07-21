"""FastAPI router untuk Control Tower SOP Validation v0.1."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.control_tower.service import ControlTowerService

router = APIRouter(prefix="/api/control-tower", tags=["Control Tower"])


def require_dashboard_auth(request: Request) -> None:
    from src.api import is_authenticated

    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
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
    process: Optional[str] = Query(default=None),
    document: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to.")
    return service.exceptions(
        rule_id=rule_id,
        status=validation_status,
        severity=severity,
        owner=owner,
        process=process,
        document=document,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


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
        raise HTTPException(
            status_code=404, detail="Record not found in latest completed extraction."
        )
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
