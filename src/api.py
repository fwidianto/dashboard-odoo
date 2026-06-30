"""FastAPI integration for Odoo-PostgreSQL sync service.

This module provides a REST API for managing synchronization tasks.
Designed for production deployment with uvicorn.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.engine.sync_engine import SyncEngine
from src.engine.scheduler import SyncScheduler
from src.state.state_manager import StateManager
from src.clients.postgres_client import PostgresClient
from src.utils.logging import get_logger, setup_logging
from src.utils.settings import get_settings

# Initialize logging
setup_logging()
logger = get_logger("api")

# Create FastAPI app
app = FastAPI(
    title="Odoo-PostgreSQL Sync API",
    description="REST API for Odoo to PostgreSQL synchronization",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Global instances
_scheduler: Optional[SyncScheduler] = None


# Pydantic models for API
class SyncRequest(BaseModel):
    """Request model for sync operation."""

    full_sync: bool = Field(default=False, description="Perform full sync")
    models: Optional[list[str]] = Field(default=None, description="Specific models to sync")


class SyncResponse(BaseModel):
    """Response model for sync operation."""

    status: str
    message: str
    results: Optional[list[dict]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StatusResponse(BaseModel):
    """Response model for status check."""

    status: str
    models: list[dict]
    total_models: int
    synced_models: int
    scheduler_running: bool


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    odoo_connected: bool
    postgres_connected: bool
    scheduler_running: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SyncHistoryResponse(BaseModel):
    """Response model for sync history."""

    records: list[dict]
    total: int


class SyncAuditResponse(BaseModel):
    """Response model for sync audit."""

    records: list[dict]
    total: int


class ResetRequest(BaseModel):
    """Request model for reset operation."""

    models: list[str] = Field(..., description="Models to reset")


def _json_safe(value):
    """Convert database values into JSON-friendly primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _calculate_ratio(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None
    return numerator / denominator


def _build_internal_order_dashboard_summary(rows: list[dict]) -> dict:
    active_rows = [row for row in rows if row.get("traceability_status") != "CANCELLED_RECORD"]

    so_ordered = sum(float(row.get("total_so_ordered_qty") or 0) for row in active_rows)
    so_delivered = sum(float(row.get("total_so_delivered_qty") or 0) for row in active_rows)
    so_invoiced = sum(float(row.get("total_so_invoiced_qty") or 0) for row in active_rows)
    po_ordered = sum(float(row.get("total_po_ordered_qty") or 0) for row in active_rows)
    po_received = sum(float(row.get("total_po_received_qty") or 0) for row in active_rows)
    po_invoiced = sum(float(row.get("total_po_invoiced_qty") or 0) for row in active_rows)

    return {
        "active_internal_orders": len(active_rows),
        "internal_orders_with_mo": sum(1 for row in active_rows if row.get("linked_mo_count", 0) > 0),
        "internal_orders_with_so": sum(1 for row in active_rows if row.get("linked_so_count", 0) > 0),
        "internal_orders_delivered": sum(1 for row in active_rows if row.get("has_delivered_so")),
        "internal_orders_invoiced": sum(1 for row in active_rows if row.get("has_invoiced_so")),
        "delivery_progress_ratio": _calculate_ratio(so_delivered, so_ordered),
        "invoice_progress_ratio": _calculate_ratio(so_invoiced, so_ordered),
        "procurement_receipt_progress_ratio": _calculate_ratio(po_received, po_ordered),
        "procurement_billing_progress_ratio": _calculate_ratio(po_invoiced, po_ordered),
        "total_so_ordered_qty": so_ordered,
        "total_so_delivered_qty": so_delivered,
        "total_so_invoiced_qty": so_invoiced,
        "total_po_ordered_qty": po_ordered,
        "total_po_received_qty": po_received,
        "total_po_invoiced_qty": po_invoiced,
    }


def _build_internal_order_filter_options(rows: list[dict]) -> dict:
    def unique_values(key: str) -> list[str]:
        values = {
            str(row[key])
            for row in rows
            if row.get(key) is not None and str(row.get(key)).strip()
        }
        return sorted(values)

    return {
        "requesters": unique_values("requester"),
        "statuses": unique_values("status_summary"),
        "traceability_statuses": unique_values("traceability_status"),
    }


def _build_sales_order_dashboard_summary(rows: list[dict]) -> dict:
    active_rows = [row for row in rows if row.get("follow_up_status") != "CANCELLED_RECORD"]

    ordered_qty = sum(float(row.get("ordered_qty") or 0) for row in active_rows)
    delivered_qty = sum(float(row.get("delivered_qty") or 0) for row in active_rows)
    invoiced_qty = sum(float(row.get("invoiced_qty") or 0) for row in active_rows)
    ordered_amount = sum(float(row.get("ordered_amount") or 0) for row in active_rows)
    delivered_amount = sum(float(row.get("delivered_amount") or 0) for row in active_rows)
    invoiced_amount = sum(float(row.get("invoiced_amount") or 0) for row in active_rows)

    return {
        "active_sales_orders": len(active_rows),
        "delivered_sales_orders": sum(1 for row in active_rows if row.get("has_delivered_qty")),
        "invoiced_sales_orders": sum(1 for row in active_rows if row.get("has_invoiced_qty")),
        "delayed_delivery_sales_orders": sum(
            1 for row in active_rows if row.get("follow_up_status") == "DELAYED_DELIVERY"
        ),
        "waiting_invoice_sales_orders": sum(
            1 for row in active_rows if row.get("follow_up_status") == "WAITING_INVOICE"
        ),
        "quantity_delivery_progress_ratio": _calculate_ratio(delivered_qty, ordered_qty),
        "quantity_invoice_progress_ratio": _calculate_ratio(invoiced_qty, ordered_qty),
        "amount_delivery_progress_ratio": _calculate_ratio(delivered_amount, ordered_amount),
        "amount_invoice_progress_ratio": _calculate_ratio(invoiced_amount, ordered_amount),
        "sales_orders_from_internal_order": sum(
            1 for row in active_rows if row.get("source_type") == "FROM_INTERNAL_ORDER"
        ),
        "sales_orders_make_to_order": sum(
            1 for row in active_rows if row.get("source_type") == "MAKE_TO_ORDER"
        ),
        "sales_orders_from_stock": sum(
            1 for row in active_rows if row.get("source_type") == "FROM_STOCK"
        ),
        "unknown_source_sales_orders": sum(
            1 for row in active_rows if row.get("source_type") == "UNKNOWN_SOURCE"
        ),
        "total_ordered_qty": ordered_qty,
        "total_delivered_qty": delivered_qty,
        "total_invoiced_qty": invoiced_qty,
        "total_ordered_amount": ordered_amount,
        "total_delivered_amount": delivered_amount,
        "total_invoiced_amount": invoiced_amount,
    }


def _build_sales_order_filter_options(rows: list[dict]) -> dict:
    def unique_values(key: str) -> list[str]:
        values = {
            str(row[key])
            for row in rows
            if row.get(key) is not None and str(row.get(key)).strip()
        }
        return sorted(values)

    return {
        "customers": unique_values("customer_name"),
        "years": unique_values("order_year"),
        "product_types": unique_values("product_type_label"),
        "source_types": unique_values("source_type"),
        "sales_order_statuses": unique_values("sales_order_state"),
        "follow_up_statuses": unique_values("follow_up_status"),
    }


def _build_internal_order_rekap_warnings(summary_row: dict) -> list[str]:
    warnings: list[str] = []

    if not summary_row.get("has_sales_order_link"):
        warnings.append("Pre-SO Internal Order: no linked Sales Order found.")
    if int(summary_row.get("mixed_uom_count") or 0) > 0:
        warnings.append("Mixed UoM detected; quantity comparison may be unreliable.")
    if Decimal(str(summary_row.get("rkb_actual_unknown_class_amount") or 0)) != 0:
        warnings.append("Unknown product classification amount exists; review product classification.")
    if int(summary_row.get("po_without_rop_count") or 0) > 0:
        warnings.append("Some PO rows exist without linked ROP.")
    if int(summary_row.get("rop_without_po_count") or 0) > 0:
        warnings.append("Some ROP rows exist without linked PO.")

    return warnings


def get_sync_engine() -> SyncEngine:
    """Dependency to get sync engine instance."""
    engine = SyncEngine()
    engine.initialize()
    return engine


def get_scheduler() -> Optional[SyncScheduler]:
    """Get scheduler instance."""
    return _scheduler


# ============================================
# Health Endpoints
# ============================================

@app.get("/", include_in_schema=False)
async def dashboard_home():
    """Open the first dashboard page by default."""
    return FileResponse(STATIC_DIR / "dashboard" / "internal-orders.html")


@app.get("/dashboard/internal-orders", include_in_schema=False)
async def internal_order_dashboard_page():
    """Serve the Internal Order Traceability Dashboard page."""
    return FileResponse(STATIC_DIR / "dashboard" / "internal-orders.html")


@app.get("/dashboard/sales-orders", include_in_schema=False)
async def sales_order_dashboard_page():
    """Serve the Sales Order Traceability Dashboard page."""
    return FileResponse(STATIC_DIR / "dashboard" / "sales-orders.html")


@app.get("/dashboard/internal-order-rekap", include_in_schema=False)
async def internal_order_rekap_dashboard_page():
    """Serve the Internal Order Rekap Dashboard page."""
    return FileResponse(STATIC_DIR / "dashboard" / "internal-order-rekap.html")


@app.get("/api/dashboard/internal-orders", tags=["Dashboard"])
async def internal_order_dashboard_data():
    """
    Return V1 Internal Order traceability dashboard data.

    This endpoint is read-only and uses the validated dashboard view:
    vw_dashboard_internal_order_traceability.
    """
    sql = text("""
        SELECT
            internal_order_number,
            traceability_status,
            status_summary,
            requester,
            needed_date_from,
            needed_date_to,
            line_count,
            product_count,
            linked_mo_count,
            linked_so_count,
            linked_so_line_count,
            total_so_amount,
            total_so_ordered_qty,
            total_so_delivered_qty,
            total_so_invoiced_qty,
            so_delivery_progress_ratio,
            so_invoice_progress_ratio,
            has_delivered_so,
            has_invoiced_so,
            delivery_status_summary,
            invoice_status_summary,
            linked_po_line_count,
            total_po_ordered_qty,
            total_po_received_qty,
            total_po_invoiced_qty,
            po_receipt_progress_ratio,
            po_invoice_progress_ratio,
            purchase_status_summary,
            accounting_line_count,
            manufacturing_movement_count,
            finished_goods_store_count,
            delivery_movement_count
        FROM vw_dashboard_internal_order_traceability
        ORDER BY
            CASE traceability_status
                WHEN 'HAS_ACCOUNTING_LINK' THEN 1
                WHEN 'HAS_INVOICED_SO' THEN 2
                WHEN 'HAS_DELIVERED_SO' THEN 3
                WHEN 'HAS_LINKED_SO' THEN 4
                WHEN 'HAS_MO_NO_SO_YET' THEN 5
                WHEN 'NEW_OR_TO_SUBMIT_NO_MO' THEN 6
                WHEN 'OLD_OR_UNLINKED_NO_MO' THEN 7
                WHEN 'CANCELLED_RECORD' THEN 8
                ELSE 9
            END,
            internal_order_number
    """)

    pg = PostgresClient()
    try:
        with pg.engine.connect() as conn:
            result = conn.execute(sql)
            rows = [
                {key: _json_safe(value) for key, value in row._mapping.items()}
                for row in result.fetchall()
            ]

        return {
            "rows": rows,
            "summary": _build_internal_order_dashboard_summary(rows),
            "filters": _build_internal_order_filter_options(rows),
            "meta": {
                "source_view": "vw_dashboard_internal_order_traceability",
                "row_count": len(rows),
                "profitability_included": False,
                "stock_movement_counts_are_diagnostic": True,
            },
        }
    except Exception as e:
        logger.error("Internal Order dashboard query failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pg.close()


@app.get("/api/dashboard/sales-orders", tags=["Dashboard"])
async def sales_order_dashboard_data():
    """
    Return Phase 2A Sales Order traceability dashboard data.

    This endpoint is read-only and uses the dashboard view:
    vw_dashboard_sales_order_traceability.
    """
    sql = text("""
        SELECT
            sales_order_id,
            sales_order_number,
            company_id,
            customer_name,
            order_date,
            order_create_date,
            order_year,
            commitment_date,
            sales_order_state,
            normalized_status,
            is_cancelled,
            is_valid_for_metrics,
            delivery_status,
            invoice_status,
            product_type_raw,
            product_type_label,
            raw_internal_order_reference,
            source_type,
            source_link_status,
            from_internal_order_line_count,
            from_stock_line_count,
            make_to_order_line_count,
            mixed_source_line_count,
            unknown_source_line_count,
            sales_order_line_count,
            ordered_qty,
            delivered_qty,
            invoiced_qty,
            ordered_amount,
            delivered_amount,
            invoiced_amount,
            ordered_amount_idr,
            delivered_amount_idr,
            invoiced_amount_idr,
            currency_rate_used,
            currency_conversion_basis,
            qty_delivery_progress_ratio,
            qty_invoice_progress_ratio,
            amount_delivery_progress_ratio,
            amount_invoice_progress_ratio,
            is_fully_delivered_qty,
            is_fully_invoiced_qty,
            is_fully_delivered_amount,
            is_fully_invoiced_amount,
            has_delivered_qty,
            has_invoiced_qty,
            internal_order_count,
            manufacturing_order_count,
            job_order_mo_count,
            direct_mo_count,
            direct_mo_qty,
            direct_done_mo_qty,
            direct_in_progress_mo_qty,
            io_backed_mo_count,
            io_backed_mo_qty,
            io_backed_done_mo_qty,
            io_backed_in_progress_mo_qty,
            total_related_mo_count,
            total_related_mo_qty,
            total_done_mo_qty,
            total_in_progress_mo_qty,
            shared_io_count,
            shared_io_numbers,
            multi_io_so_count,
            has_multi_io_so,
            linked_so_qty_basis,
            io_qty_correlation_status,
            accounting_line_count,
            stock_movement_diagnostic_count,
            unknown_movement_diagnostic_count,
            follow_up_status,
            follow_up_status_priority,
            sales_order_lines,
            internal_orders,
            manufacturing_orders,
            io_manufacturing_correlations,
            '[]'::jsonb AS rkb_lines,
            '[]'::jsonb AS purchase_order_lines,
            diagnostics
        FROM vw_dashboard_sales_order_traceability
        ORDER BY
            follow_up_status_priority,
            commitment_date NULLS LAST,
            sales_order_number
    """)

    pg = PostgresClient()
    try:
        with pg.engine.connect() as conn:
            result = conn.execute(sql)
            rows = [
                {key: _json_safe(value) for key, value in row._mapping.items()}
                for row in result.fetchall()
            ]

        return {
            "rows": rows,
            "summary": _build_sales_order_dashboard_summary(rows),
            "filters": _build_sales_order_filter_options(rows),
            "meta": {
                "source_view": "vw_dashboard_sales_order_traceability",
                "row_count": len(rows),
                "phase": "2A.1",
                "profitability_included": False,
                "accounting_ar_included": False,
                "stock_movement_counts_are_diagnostic": True,
                "io_mo_quantity_is_correlation_only": True,
            },
        }
    except Exception as e:
        logger.error("Sales Order dashboard query failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pg.close()



@app.get("/api/dashboard/sales-orders/{sales_order_id}/details", tags=["Dashboard"])
async def sales_order_dashboard_detail(sales_order_id: int):
    """Return heavy expanded detail sections for one Sales Order row."""
    sql = text("""
        SELECT
            sales_order_id,
            rkb_lines,
            purchase_order_lines
        FROM vw_dashboard_sales_order_traceability
        WHERE sales_order_id = :sales_order_id
    """)

    pg = PostgresClient()
    try:
        with pg.engine.connect() as conn:
            row = conn.execute(sql, {"sales_order_id": sales_order_id}).mappings().first()

        if row is None:
            raise HTTPException(status_code=404, detail="Sales Order not found")

        return {key: _json_safe(value) for key, value in row.items()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sales Order dashboard detail query failed", sales_order_id=sales_order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pg.close()


@app.get("/api/dashboard/internal-order-rekap", tags=["Dashboard"])
async def internal_order_rekap_dashboard_data(
    internal_order_number: Optional[str] = Query(default=None)
):
    """
    Return Internal Order Rekap operational reconciliation data.

    This endpoint is read-only and uses:
    vw_internal_order_rekap_summary
    vw_internal_order_rekap_lines
    """
    if internal_order_number is None or not internal_order_number.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": "internal_order_number query parameter is required."},
        )

    normalized_internal_order_number = internal_order_number.strip()

    summary_sql = text("""
        SELECT
            internal_order_number,
            company_name,
            has_sales_order_link,
            product_count,
            rkb_actual_product_count,
            rop_product_count,
            po_product_count,
            rkb_actual_amount,
            rkb_actual_trackable_amount,
            rkb_actual_non_trackable_amount,
            rkb_actual_unknown_class_amount,
            rop_amount,
            rop_trackable_amount,
            rop_non_trackable_amount,
            rop_unknown_class_amount,
            po_amount,
            po_trackable_amount,
            po_non_trackable_amount,
            po_unknown_class_amount,
            not_yet_rop_amount,
            excess_rop_amount,
            po_received_qty,
            po_invoiced_qty,
            mixed_uom_count,
            rkb_only_count,
            rop_only_count,
            po_only_count,
            rkb_rop_po_count,
            po_without_rop_count,
            rop_without_po_count,
            received_ratio,
            invoiced_ratio,
            rop_progress_ratio,
            not_yet_rop_ratio,
            comparison_basis,
            summary_scope
        FROM vw_internal_order_rekap_summary
        WHERE internal_order_number = :internal_order_number
    """)

    breakdown_trackability_sql = text("""
        SELECT
            product_trackability_class,
            product_classification_reason,
            is_trackable_product,
            COUNT(*) AS product_count,
            SUM(rkb_actual_subtotal) AS rkb_actual_amount,
            SUM(rop_subtotal) AS rop_amount,
            SUM(po_subtotal) AS po_amount
        FROM vw_internal_order_rekap_lines
        WHERE internal_order_number = :internal_order_number
        GROUP BY
            product_trackability_class,
            product_classification_reason,
            is_trackable_product
        ORDER BY
            product_trackability_class,
            product_classification_reason,
            is_trackable_product
    """)

    breakdown_presence_sql = text("""
        SELECT
            product_presence_status,
            COUNT(*) AS product_count,
            SUM(rkb_actual_subtotal) AS rkb_actual_amount,
            SUM(rop_subtotal) AS rop_amount,
            SUM(po_subtotal) AS po_amount
        FROM vw_internal_order_rekap_lines
        WHERE internal_order_number = :internal_order_number
        GROUP BY product_presence_status
        ORDER BY product_presence_status
    """)

    lines_sql = text("""
        SELECT
            internal_order_number,
            company_name,
            has_sales_order_link,
            product_key,
            product_name,
            product_trackability_class,
            product_classification_reason,
            is_trackable_product,
            product_presence_status,
            uom_summary,
            rkb_actual_uom_summary,
            rop_uom_summary,
            po_uom_summary,
            mixed_uom_flag,
            rkb_actual_qty,
            rkb_actual_unit_price,
            rkb_actual_subtotal,
            rop_qty,
            rop_unit_price,
            rop_subtotal,
            po_qty,
            po_unit_price,
            po_subtotal,
            po_received_qty,
            po_invoiced_qty,
            not_yet_rop_qty,
            not_yet_rop_amount,
            excess_rop_qty,
            excess_rop_amount,
            po_without_rop_flag,
            rop_without_po_flag,
            comparison_scope
        FROM vw_internal_order_rekap_lines
        WHERE internal_order_number = :internal_order_number
        ORDER BY
            product_trackability_class,
            product_presence_status,
            COALESCE(rkb_actual_subtotal, 0) DESC,
            product_key
    """)

    pg = PostgresClient()
    try:
        with pg.engine.connect() as conn:
            summary_result = conn.execute(
                summary_sql,
                {"internal_order_number": normalized_internal_order_number},
            ).fetchone()
            if summary_result is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "Internal Order not found.",
                        "internal_order_number": normalized_internal_order_number,
                    },
                )

            summary = {
                key: _json_safe(value)
                for key, value in summary_result._mapping.items()
            }

            trackability_breakdowns = [
                {key: _json_safe(value) for key, value in row._mapping.items()}
                for row in conn.execute(
                    breakdown_trackability_sql,
                    {"internal_order_number": normalized_internal_order_number},
                ).fetchall()
            ]

            presence_breakdowns = [
                {key: _json_safe(value) for key, value in row._mapping.items()}
                for row in conn.execute(
                    breakdown_presence_sql,
                    {"internal_order_number": normalized_internal_order_number},
                ).fetchall()
            ]

            lines = [
                {key: _json_safe(value) for key, value in row._mapping.items()}
                for row in conn.execute(
                    lines_sql,
                    {"internal_order_number": normalized_internal_order_number},
                ).fetchall()
            ]

        metadata = {
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "comparison_basis": summary.get("comparison_basis"),
            "summary_scope": summary.get("summary_scope"),
            "line_count": len(lines),
            "warnings": _build_internal_order_rekap_warnings(summary),
        }

        return {
            "status": "success",
            "internal_order_number": normalized_internal_order_number,
            "summary": summary,
            "breakdowns": {
                "by_trackability_class": trackability_breakdowns,
                "by_product_presence_status": presence_breakdowns,
            },
            "lines": lines,
            "metadata": metadata,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Internal Order Rekap API query failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pg.close()


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Check health status of all services.
    
    Returns connection status for Odoo and PostgreSQL,
    and whether the scheduler is running.
    """
    try:
        from src.clients.odoo_client import OdooClient

        odoo = OdooClient()
        pg = PostgresClient()

        odoo_connected = odoo.test_connection()
        postgres_connected = pg.test_connection()

        odoo.close()
        pg.close()

        status = "healthy" if (odoo_connected and postgres_connected) else "degraded"

        return HealthResponse(
            status=status,
            odoo_connected=odoo_connected,
            postgres_connected=postgres_connected,
            scheduler_running=_scheduler.is_running if _scheduler else False,
        )
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/sync-status", response_model=StatusResponse, tags=["Health"])
async def get_sync_status():
    """
    Get current synchronization status for all models.
    
    Returns sync state for each configured model including:
    - Last sync date and ID
    - Record count
    - Status (pending, running, completed, failed)
    """
    try:
        engine = get_sync_engine()
        status = engine.get_sync_status()

        return StatusResponse(
            status="ok",
            models=status.get("models", []),
            total_models=status.get("total_models", 0),
            synced_models=status.get("synced_models", 0),
            scheduler_running=_scheduler.is_running if _scheduler else False,
        )
    except Exception as e:
        logger.error("Status check failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sync-history", response_model=SyncHistoryResponse, tags=["Health"])
async def get_sync_history(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
):
    """
    Get sync history records.
    
    Returns history of sync operations including:
    - Start and end times
    - Duration
    - Records processed (inserted, updated, deleted)
    - Error count and messages
    - Odoo/PostgreSQL counts before and after
    """
    try:
        pg = PostgresClient()
        records = pg.get_sync_history(model_name=model_name, limit=limit)
        pg.close()

        return SyncHistoryResponse(
            records=records,
            total=len(records),
        )
    except Exception as e:
        logger.error("History check failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sync-audit", response_model=SyncAuditResponse, tags=["Health"])
async def get_sync_audit(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
):
    """
    Get sync audit records comparing Odoo and PostgreSQL counts.
    
    Returns audit records showing:
    - Odoo record count
    - PostgreSQL record count
    - Difference between counts
    - Whether counts match (is_synced)
    - Audit timestamp
    """
    try:
        # This would query the sync_audit table
        # For now, return placeholder structure
        return SyncAuditResponse(
            records=[],
            total=0,
        )
    except Exception as e:
        logger.error("Audit check failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Sync Endpoints
# ============================================

@app.post("/sync", response_model=SyncResponse, tags=["Sync"])
async def trigger_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a synchronization operation.
    
    Can run synchronously (blocking) or be queued as a background task.
    Use full_sync=true for complete data synchronization.
    """
    try:
        logger.info("Sync triggered via API", full_sync=request.full_sync)

        engine = get_sync_engine()
        
        # Run sync
        results = engine.sync_all(
            full_sync=request.full_sync,
            model_names=request.models,
        )

        # Format results
        result_list = []
        for result in results:
            result_list.append({
                "model": result.model_name,
                "table": result.table_name,
                "success": result.success,
                "records_synced": result.records_synced,
                "records_inserted": result.records_inserted,
                "records_updated": result.records_updated,
                "records_deleted": result.records_deleted,
                "duration_seconds": result.duration_seconds,
                "errors": result.errors,
            })

        successful = sum(1 for r in results if r.success)
        status = "completed" if successful == len(results) else "partial"

        return SyncResponse(
            status=status,
            message=f"Synced {successful}/{len(results)} models successfully",
            results=result_list,
        )

    except Exception as e:
        logger.error("Sync failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/{model_name}", response_model=SyncResponse, tags=["Sync"])
async def sync_model(model_name: str, full_sync: bool = False):
    """
    Synchronize a specific model.
    
    Args:
        model_name: Odoo model technical name (e.g., 'res.partner').
        full_sync: Whether to perform full sync.
    """
    try:
        engine = get_sync_engine()
        
        # Find model config
        model_config = None
        for config in engine.config.models:
            if config.odoo_model == model_name:
                model_config = config
                break

        if not model_config:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_name}' not found in configuration",
            )

        result = engine.sync_model(model_config, full_sync=full_sync)

        return SyncResponse(
            status="completed" if result.success else "failed",
            message=f"Synced {result.records_synced} records",
            results=[{
                "model": result.model_name,
                "table": result.table_name,
                "success": result.success,
                "records_synced": result.records_synced,
                "records_inserted": result.records_inserted,
                "records_updated": result.records_updated,
                "records_deleted": result.records_deleted,
                "duration_seconds": result.duration_seconds,
                "errors": result.errors,
            }],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Model sync failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset", response_model=SyncResponse, tags=["Sync"])
async def reset_sync_state(request: ResetRequest):
    """
    Reset synchronization state for specified models.
    
    After reset, incremental sync will re-sync all records.
    """
    try:
        pg = PostgresClient()
        state_mgr = StateManager(pg)
        state_mgr.initialize()

        for model_name in request.models:
            state_mgr.reset_model_state(model_name)

        pg.close()

        return SyncResponse(
            status="completed",
            message=f"Reset sync state for {len(request.models)} models",
        )

    except Exception as e:
        logger.error("Reset failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models", tags=["Configuration"])
async def list_models():
    """
    List all configured models.
    
    Returns model configurations including Odoo model name,
    PostgreSQL table name, field mappings, and deletion strategy.
    """
    try:
        engine = get_sync_engine()
        
        models = []
        for config in engine.config.models:
            models.append({
                "odoo_model": config.odoo_model,
                "postgres_table": config.postgres_table,
                "description": config.description,
                "deletion_strategy": config.deletion_strategy,
                "batch_size": config.batch_size or engine.config.default_batch_size,
                "field_count": len(config.fields),
                "fields": [
                    {
                        "odoo_field": f.odoo_field,
                        "postgres_column": f.postgres_column,
                        "postgres_type": f.postgres_type,
                        "primary_key": f.primary_key,
                        "is_sync_date": f.is_sync_date,
                        "field_type": f.field_type,
                        "is_foreign_key": f.is_foreign_key,
                        "indexed": f.indexed,
                    }
                    for f in config.fields
                ],
            })

        return {"models": models, "total": len(models)}

    except Exception as e:
        logger.error("List models failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Scheduler Endpoints
# ============================================

@app.post("/scheduler/start", tags=["Scheduler"])
async def start_scheduler(interval_minutes: int = 15):
    """
    Start the synchronization scheduler.
    
    Args:
        interval_minutes: Incremental sync interval in minutes.
    """
    global _scheduler

    if _scheduler and _scheduler.is_running:
        return {"status": "already_running", "message": "Scheduler is already running"}

    _scheduler = SyncScheduler(incremental_interval_minutes=interval_minutes)
    _scheduler.start(run_immediately=True)

    return {"status": "started", "message": f"Scheduler started with {interval_minutes}min interval"}


@app.post("/scheduler/stop", tags=["Scheduler"])
async def stop_scheduler():
    """Stop the synchronization scheduler."""
    global _scheduler

    if not _scheduler or not _scheduler.is_running:
        return {"status": "not_running", "message": "Scheduler is not running"}

    _scheduler.stop()
    _scheduler = None

    return {"status": "stopped", "message": "Scheduler stopped"}


@app.get("/scheduler/status", tags=["Scheduler"])
async def scheduler_status():
    """Get scheduler status and next run times."""
    if not _scheduler:
        return {
            "running": False,
            "next_runs": [],
        }

    next_runs = _scheduler.get_next_run_times(5)
    return {
        "running": _scheduler.is_running,
        "next_runs": [
            {"datetime": run.isoformat(), "timestamp": run.timestamp()}
            for run in next_runs
        ],
    }


@app.get("/validate", tags=["Configuration"])
async def validate_configuration():
    """
    Validate the current configuration.
    
    Checks that all configured models and fields exist in Odoo.
    """
    try:
        engine = get_sync_engine()
        errors = engine.validate_configuration()

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    except Exception as e:
        logger.error("Validation failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
