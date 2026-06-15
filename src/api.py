"""FastAPI integration for Odoo-PostgreSQL sync service.

This module provides a REST API for managing synchronization tasks.
Designed for production deployment with uvicorn.
"""

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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