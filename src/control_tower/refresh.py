"""Safe Control Tower refresh lifecycle helpers.

The lifecycle keeps extraction candidates separate from the published pointer.
Odoo access remains delegated to the existing read-only relation extractor.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock, Thread
from time import perf_counter
from typing import Any, Iterator, Optional, Sequence
from uuid import uuid4

from sqlalchemy import text

from src.clients.postgres_client import PostgresClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_PATHS = (
    PROJECT_ROOT / "sql" / "09_control_tower_sop_validation_v0.sql",
    PROJECT_ROOT / "sql" / "10_control_tower_runtime_hardening_v01.sql",
    PROJECT_ROOT / "sql" / "11_control_tower_io_lineage_hardening_v012.sql",
    PROJECT_ROOT / "sql" / "12_control_tower_po_2026_scope.sql",
    PROJECT_ROOT / "sql" / "13_control_tower_temuan_v01.sql",
)
REFRESH_LOCK_KEY = 8247135091
DEFAULT_STALE_RUN_MINUTES = 30
BENCHMARK_THRESHOLD_SECONDS = 30 * 60


class RefreshAlreadyRunning(RuntimeError):
    """Raised when another refresh owns the PostgreSQL advisory lock."""


class RefreshLifecycleError(RuntimeError):
    """Raised when a candidate cannot safely transition state."""


def sanitize_diagnostic(value: Any, limit: int = 300) -> str:
    """Keep diagnostics useful without returning credentials or long payloads."""
    message = str(value or "").replace("\x00", " ").strip()
    message = re.sub(r"(?i)(password|passwd|api[_ -]?key|token|secret)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", message)
    message = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[redacted]", message)
    return message[:limit] or "Refresh failed without a diagnostic message."


def ensure_refresh_schema(pg: PostgresClient) -> None:
    """Add lifecycle metadata idempotently; never removes extracted evidence."""
    statements = (
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS duration_seconds DOUBLE PRECISION",
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS trigger TEXT",
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS requested_by TEXT",
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS stage_timings JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE ct_extraction_run ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
        "CREATE TABLE IF NOT EXISTS ct_published_snapshot ("
        "company_id BIGINT PRIMARY KEY, run_id UUID NOT NULL, published_at TIMESTAMPTZ NOT NULL, "
        "previous_run_id UUID, trigger TEXT, requested_by TEXT"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_ct_extraction_run_status_started "
        "ON ct_extraction_run (company_id, status, started_at DESC)",
    )
    with pg.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text("""
            INSERT INTO ct_published_snapshot (company_id, run_id, published_at, trigger, requested_by)
            SELECT latest.company_id, latest.run_id, COALESCE(latest.completed_at, NOW()), 'legacy', 'migration'
            FROM (
                SELECT DISTINCT ON (company_id)
                    company_id, run_id, completed_at
                FROM ct_extraction_run
                WHERE status = 'COMPLETED'
                ORDER BY company_id, completed_at DESC NULLS LAST, started_at DESC
            ) latest
            ON CONFLICT (company_id) DO NOTHING
        """))


@contextmanager
def advisory_refresh_lock(pg: PostgresClient) -> Iterator[None]:
    """Hold one database-wide lock for extraction, SQL, and finding publication."""
    connection = pg.engine.connect()
    locked = False
    try:
        locked = bool(connection.execute(
            text("SELECT pg_try_advisory_lock(CAST(:lock_key AS BIGINT))"),
            {"lock_key": REFRESH_LOCK_KEY},
        ).scalar())
        if not locked:
            raise RefreshAlreadyRunning("A Control Tower refresh is already running.")
        yield
    finally:
        if locked:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(CAST(:lock_key AS BIGINT))"),
                    {"lock_key": REFRESH_LOCK_KEY},
                )
                connection.commit()
            finally:
                connection.close()
        else:
            connection.close()


def _run_row(pg: PostgresClient, run_id: str) -> Optional[dict[str, Any]]:
    with pg.engine.connect() as conn:
        row = conn.execute(text("""
            SELECT run_id::text, status, started_at, completed_at, finished_at,
                   company_id, model_counts, error_message, duration_seconds,
                   trigger, requested_by, stage_timings, published_at
            FROM ct_extraction_run
            WHERE run_id = CAST(:run_id AS UUID)
        """), {"run_id": run_id}).mappings().first()
    return dict(row) if row else None


def mark_run_failed(
    pg: PostgresClient,
    run_id: str,
    error: Any,
    *,
    status: str = "FAILED",
    finished_at: Optional[datetime] = None,
) -> None:
    """Finalize a failed or interrupted candidate without changing the pointer."""
    finished = finished_at or datetime.now(timezone.utc)
    with pg.engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_extraction_run
            SET status = :status,
                finished_at = :finished_at,
                duration_seconds = EXTRACT(EPOCH FROM (:finished_at - started_at)),
                error_message = :error_message
            WHERE run_id = CAST(:run_id AS UUID)
              AND status <> 'COMPLETED'
        """), {
            "run_id": run_id,
            "status": status,
            "finished_at": finished,
            "error_message": sanitize_diagnostic(error),
        })


def publish_candidate(
    pg: PostgresClient,
    run_id: str,
    *,
    sql_paths: Sequence[Path] = SQL_PATHS,
    trigger: str = "manual",
    requested_by: Optional[str] = None,
) -> dict[str, Any]:
    """Promote one complete candidate and rebuild all dependent read models atomically."""
    ensure_refresh_schema(pg)
    started = perf_counter()
    try:
        with pg.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT company_id, status, finished_at, model_counts
                FROM ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                FOR UPDATE
            """), {"run_id": run_id}).mappings().first()
            if not row:
                raise RefreshLifecycleError("Refresh candidate was not found.")

            company_id = row["company_id"]
            status = row["status"]
            model_counts = row["model_counts"]
            if status != "READY_FOR_PUBLISH":
                raise RefreshLifecycleError(
                    f"Refresh candidate is {status}, not READY_FOR_PUBLISH."
                )

            previous = conn.execute(text("""
                SELECT run_id
                FROM ct_published_snapshot
                WHERE company_id = :company_id
                FOR UPDATE
            """), {"company_id": company_id}).first()
            previous_run_id = previous[0] if previous else None

            completed_at = datetime.now(timezone.utc)
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET status = 'COMPLETED', completed_at = :completed_at,
                    published_at = :completed_at, trigger = :trigger,
                    requested_by = :requested_by
                WHERE run_id = CAST(:run_id AS UUID)
            """), {
                "run_id": run_id,
                "completed_at": completed_at,
                "trigger": trigger,
                "requested_by": requested_by,
            })
            conn.execute(text("""
                INSERT INTO ct_published_snapshot
                    (company_id, run_id, published_at, previous_run_id, trigger, requested_by)
                VALUES (:company_id, CAST(:run_id AS UUID), :published_at,
                        CAST(:previous_run_id AS UUID), :trigger, :requested_by)
                ON CONFLICT (company_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    published_at = EXCLUDED.published_at,
                    previous_run_id = EXCLUDED.previous_run_id,
                    trigger = EXCLUDED.trigger,
                    requested_by = EXCLUDED.requested_by
            """), {
                "company_id": company_id,
                "run_id": run_id,
                "published_at": completed_at,
                "previous_run_id": previous_run_id,
                "trigger": trigger,
                "requested_by": requested_by,
            })

            for sql_path in sql_paths:
                if not sql_path.exists():
                    raise FileNotFoundError(f"SQL file not found: {sql_path}")
                conn.exec_driver_sql(sql_path.read_text(encoding="utf-8"))

            stage_timings = dict(model_counts or {}) if isinstance(model_counts, dict) else {}
            stage_timings["sql_and_publication_seconds"] = round(perf_counter() - started, 3)
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
                    stage_timings = CAST(:stage_timings AS JSONB)
                WHERE run_id = CAST(:run_id AS UUID)
            """), {
                "run_id": run_id,
                "stage_timings": json.dumps(stage_timings, default=str),
            })
    except BaseException as exc:
        try:
            mark_run_failed(pg, run_id, exc)
        except Exception:
            pass
        raise

    return _run_row(pg, run_id) or {"run_id": run_id, "status": "COMPLETED"}


def run_refresh_pipeline(
    *,
    company_id: int = 3,
    batch_size: int = 500,
    trigger: str = "manual",
    requested_by: Optional[str] = None,
    sql_paths: Sequence[Path] = SQL_PATHS,
) -> dict[str, Any]:
    """Run full extraction and publish only after SQL/finding rebuild succeeds."""
    from src.control_tower.relation_extractor import ControlTowerRelationExtractor

    pg = PostgresClient()
    extractor: Optional[ControlTowerRelationExtractor] = None
    started = perf_counter()
    try:
        with advisory_refresh_lock(pg):
            extractor = ControlTowerRelationExtractor(
                postgres_client=pg,
                company_id=company_id,
                batch_size=batch_size,
            )
            candidate = extractor.run(
                lock_held=True,
                trigger=trigger,
                requested_by=requested_by,
            )
            result = publish_candidate(
                pg,
                candidate["run_id"],
                sql_paths=sql_paths,
                trigger=trigger,
                requested_by=requested_by,
            )
            result["total_duration_seconds"] = round(perf_counter() - started, 3)
            return result
    finally:
        if extractor is not None:
            extractor.close()
        else:
            pg.close()


def benchmark_classification(
    *,
    outcome: str,
    duration_seconds: Optional[float],
    threshold_seconds: float = BENCHMARK_THRESHOLD_SECONDS,
) -> str:
    """Classify a benchmark without claiming host evidence that was not run."""
    if outcome != "COMPLETED":
        return "FAILED"
    if duration_seconds is None:
        return "PENDING_HOST"
    return "PASS" if duration_seconds <= threshold_seconds else "FAIL"


def recover_stale_run(
    pg: PostgresClient,
    *,
    run_id: str,
    requested_by: str,
    reason: str,
    company_id: int = 3,
    max_age_minutes: int = DEFAULT_STALE_RUN_MINUTES,
) -> dict[str, Any]:
    """Explicitly transition one stale candidate to ABORTED; never delete data."""
    ensure_refresh_schema(pg)
    with pg.engine.begin() as conn:
        row = conn.execute(text("""
            SELECT run_id::text, status, started_at, company_id
            FROM ct_extraction_run
            WHERE run_id = CAST(:run_id AS UUID)
            FOR UPDATE
        """), {"run_id": run_id}).mappings().first()
        if not row:
            raise RefreshLifecycleError("Requested refresh run was not found.")
        if int(row["company_id"] or 0) != company_id:
            raise RefreshLifecycleError("Requested refresh run is outside company 3 scope.")
        if row["status"] not in {"RUNNING", "READY_FOR_PUBLISH"}:
            raise RefreshLifecycleError(f"Refresh run is {row['status']} and cannot be recovered.")
        age_seconds = (datetime.now(timezone.utc) - row["started_at"]).total_seconds()
        if age_seconds < max_age_minutes * 60:
            raise RefreshLifecycleError("Refresh run is not older than the configured stale threshold.")
        finished_at = datetime.now(timezone.utc)
        audit_message = f"ABORTED_BY_ADMIN: {sanitize_diagnostic(reason, 180)}"
        conn.execute(text("""
            UPDATE ct_extraction_run
            SET status = 'ABORTED', finished_at = :finished_at,
                duration_seconds = EXTRACT(EPOCH FROM (:finished_at - started_at)),
                error_message = :error_message,
                trigger = 'recovery', requested_by = :requested_by,
                stage_timings = stage_timings || CAST(:audit AS JSONB)
            WHERE run_id = CAST(:run_id AS UUID)
        """), {
            "run_id": run_id,
            "finished_at": finished_at,
            "error_message": audit_message,
            "requested_by": requested_by,
            "audit": json.dumps({"recovery_reason": sanitize_diagnostic(reason, 180)}),
        })
    return _run_row(pg, run_id) or {"run_id": run_id, "status": "ABORTED"}


class RefreshCoordinator:
    """One-process request guard around the database-wide refresh lock."""

    def __init__(self) -> None:
        self._state_lock = Lock()
        self._thread: Optional[Thread] = None
        self._job_id: Optional[str] = None
        self._last_result: Optional[dict[str, Any]] = None

    def start(self, *, requested_by: str, company_id: int = 3, batch_size: int = 500) -> dict[str, Any]:
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                raise RefreshAlreadyRunning("A Control Tower refresh request is already active.")
            job_id = str(uuid4())
            self._job_id = job_id
            self._last_result = None
            self._thread = Thread(
                target=self._run,
                kwargs={
                    "job_id": job_id,
                    "requested_by": requested_by,
                    "company_id": company_id,
                    "batch_size": batch_size,
                },
                name="control-tower-refresh",
                daemon=True,
            )
            self._thread.start()
            return {"job_id": job_id, "status": "ACCEPTED", "company_id": company_id}

    def _run(self, *, job_id: str, requested_by: str, company_id: int, batch_size: int) -> None:
        try:
            result = run_refresh_pipeline(
                company_id=company_id,
                batch_size=batch_size,
                trigger="manual",
                requested_by=requested_by,
            )
        except Exception as exc:
            result = {"job_id": job_id, "status": "FAILED", "error_message": sanitize_diagnostic(exc)}
        result["job_id"] = job_id
        with self._state_lock:
            self._last_result = result

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            active = bool(self._thread and self._thread.is_alive())
            return {
                "active_request": active,
                "job_id": self._job_id,
                "last_result": self._last_result,
            }


REFRESH_COORDINATOR = RefreshCoordinator()
