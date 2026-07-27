"""FastAPI router untuk Control Tower SOP Validation v0.1."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.control_tower.relation_extractor import IncrementalRefreshError, RefreshInProgress
from src.control_tower.service import ControlTowerService

router = APIRouter(prefix="/api/control-tower", tags=["Control Tower"])
refresh_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="control-tower-refresh")


def _run_refresh_job(job_id: str) -> None:
    service = ControlTowerService()
    try:
        service.run_refresh_job(job_id)
    finally:
        service.close()


def require_dashboard_auth(request: Request) -> None:
    from src.api import is_authenticated

    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )


def dashboard_actor(request: Request) -> str:
    from src.api import DASHBOARD_SESSION_COOKIE, read_dashboard_session

    session = read_dashboard_session(request.cookies.get(DASHBOARD_SESSION_COOKIE))
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    actor = str(session.get("dashboard_username") or "dashboard-user").strip()
    return actor or "dashboard-user"


class FindingCloseRequest(BaseModel):
    finding_ids: list[str] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=200)
    note: Optional[str] = Field(default=None, max_length=2000)


class FindingReopenRequest(BaseModel):
    finding_ids: list[str] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)


class ExceptionRuleRequest(BaseModel):
    rule_code: str = Field(min_length=1, max_length=100)
    selector: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)
    approver: str = Field(min_length=1, max_length=200)
    valid_from: date
    valid_until: Optional[date] = None


class ProductCostClassificationRequest(BaseModel):
    classification: str = Field(min_length=1, max_length=100)


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


@router.get("/findings", dependencies=[Depends(require_dashboard_auth)])
def finding_summaries(
    category: Optional[str] = Query(default=None),
    process_node: Optional[str] = Query(default=None, max_length=100),
    document: Optional[str] = Query(default=None, max_length=100),
    archive: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.findings(
            category=category,
            process_node=process_node,
            document=document,
            archive=archive,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/findings/bulk-close")
def bulk_close_findings(
    body: FindingCloseRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.close_findings(
            body.finding_ids,
            reason=body.reason,
            note=body.note,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/findings/bulk-reopen")
def bulk_reopen_findings(
    body: FindingReopenRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.reopen_findings(body.finding_ids, reason=body.reason, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/findings/{finding_id}", dependencies=[Depends(require_dashboard_auth)])
def finding_detail(
    finding_id: str,
    service: ControlTowerService = Depends(service_dependency),
):
    if len(finding_id) != 32 or any(character not in "0123456789abcdef" for character in finding_id):
        raise HTTPException(status_code=422, detail="Invalid finding identifier.")
    result = service.finding_detail(finding_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    return result


@router.post("/findings/{finding_id}/close")
def close_finding(
    finding_id: str,
    body: FindingCloseRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    if body.finding_ids != [finding_id]:
        raise HTTPException(status_code=422, detail="Finding identifier mismatch.")
    try:
        return service.close_findings([finding_id], reason=body.reason, note=body.note, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/findings/{finding_id}/reopen")
def reopen_finding(
    finding_id: str,
    body: FindingReopenRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    if body.finding_ids != [finding_id]:
        raise HTTPException(status_code=422, detail="Finding identifier mismatch.")
    try:
        return service.reopen_findings([finding_id], reason=body.reason, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/search", dependencies=[Depends(require_dashboard_auth)])
def global_document_search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    service: ControlTowerService = Depends(service_dependency),
):
    return service.search_documents(q, limit=limit)


@router.get("/documents/{model}/{record_id}", dependencies=[Depends(require_dashboard_auth)])
def document_detail(
    model: str,
    record_id: int,
    include_all_lines: bool = Query(default=False),
    include_tracking: bool = Query(default=False),
    service: ControlTowerService = Depends(service_dependency),
):
    result = service.document_detail(
        model,
        record_id,
        include_all_lines=include_all_lines,
        include_tracking=include_tracking,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found in the published dataset.")
    return result


@router.get("/documents/sale.order/{record_id}/gross-profit", dependencies=[Depends(require_dashboard_auth)])
def sales_order_gross_profit(
    record_id: int,
    service: ControlTowerService = Depends(service_dependency),
):
    result = service.gross_profit(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Gross Profit is not available for this Sales Order.")
    return result


@router.get("/tracking/{model}/{record_id}", dependencies=[Depends(require_dashboard_auth)])
def integrated_tracking(
    model: str,
    record_id: int,
    service: ControlTowerService = Depends(service_dependency),
):
    return service.tracking(model, record_id)


@router.get("/rkb-tracking/{request_id}", dependencies=[Depends(require_dashboard_auth)])
def rkb_tracking(
    request_id: int,
    service: ControlTowerService = Depends(service_dependency),
):
    result = service.rkb_tracking(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="RKB not found in the published dataset.")
    return result


@router.get("/process-map", dependencies=[Depends(require_dashboard_auth)])
def process_map(service: ControlTowerService = Depends(service_dependency)):
    return service.process_map()


@router.get("/exception-rules", dependencies=[Depends(require_dashboard_auth)])
def reusable_exception_rules(service: ControlTowerService = Depends(service_dependency)):
    return {"rows": service.exception_rules()}


@router.post("/exception-rules", status_code=status.HTTP_201_CREATED)
def create_reusable_exception_rule(
    body: ExceptionRuleRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.create_exception_rule(
            rule_code=body.rule_code,
            selector=body.selector,
            reason=body.reason,
            approver=body.approver,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/exception-rules/{exception_id}")
def deactivate_reusable_exception_rule(
    exception_id: str,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        UUID(exception_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid exception identifier.") from exc
    if not service.deactivate_exception_rule(exception_id, actor=actor):
        raise HTTPException(status_code=404, detail="Active exception rule not found.")
    return {"active": False}


@router.get("/product-cost-classifications", dependencies=[Depends(require_dashboard_auth)])
def product_cost_classifications(
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    service: ControlTowerService = Depends(service_dependency),
):
    return {"rows": service.product_cost_classifications(search=q, limit=limit)}


@router.put("/product-cost-classifications/{product_id}")
def update_product_cost_classification(
    product_id: int,
    body: ProductCostClassificationRequest,
    actor: str = Depends(dashboard_actor),
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        return service.update_product_cost_classification(
            product_id,
            classification=body.classification,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cases", dependencies=[Depends(require_dashboard_auth)])
def finding_cases(
    rule_id: Optional[str] = Query(default=None, max_length=64),
    validation_status: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ControlTowerService = Depends(service_dependency),
):
    return service.cases(
        rule_id=rule_id,
        validation_status=validation_status,
        limit=limit,
        offset=offset,
    )


@router.get("/cases/{case_id}", dependencies=[Depends(require_dashboard_auth)])
def finding_case_detail(
    case_id: str,
    service: ControlTowerService = Depends(service_dependency),
):
    if len(case_id) != 32 or any(character not in "0123456789abcdef" for character in case_id):
        raise HTTPException(status_code=422, detail="Invalid case identifier.")
    result = service.case_detail(case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found in latest completed snapshot.")
    return result


@router.get("/related-data/{root_model}/{root_id}", dependencies=[Depends(require_dashboard_auth)])
def related_data(
    root_model: str,
    root_id: int,
    service: ControlTowerService = Depends(service_dependency),
):
    result = service.related_data(root_model, root_id)
    if result["root"] is None:
        raise HTTPException(
            status_code=404, detail="Record not found in latest completed snapshot."
        )
    return result


@router.post(
    "/refresh",
    dependencies=[Depends(require_dashboard_auth)],
    status_code=status.HTTP_202_ACCEPTED,
)
def incremental_refresh(service: ControlTowerService = Depends(service_dependency)):
    try:
        job = service.start_refresh_job()
        if not job["already_running"]:
            refresh_executor.submit(_run_refresh_job, job["job_id"])
        return {**job, "poll_url": f'/api/control-tower/refresh/{job["job_id"]}'}
    except RefreshInProgress as exc:
        raise HTTPException(status_code=409, detail="Pembaruan Odoo sedang berjalan.") from exc
    except IncrementalRefreshError as exc:
        raise HTTPException(
            status_code=503,
            detail="Pembaruan Odoo gagal. Control Tower tetap menampilkan data terakhir yang berhasil.",
        ) from exc


@router.get("/refresh/{job_id}", dependencies=[Depends(require_dashboard_auth)])
def incremental_refresh_status(
    job_id: str,
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid refresh job identifier.") from exc
    job = service.refresh_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Refresh job not found.")
    return job


@router.post(
    "/refresh/{job_id}/retry",
    dependencies=[Depends(require_dashboard_auth)],
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_incremental_refresh(
    job_id: str,
    service: ControlTowerService = Depends(service_dependency),
):
    try:
        UUID(job_id)
        job = service.retry_refresh_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not job["already_running"]:
        refresh_executor.submit(_run_refresh_job, job["job_id"])
    return {**job, "poll_url": f'/api/control-tower/refresh/{job["job_id"]}'}


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
