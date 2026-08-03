"""Durable refresh-run state transitions without a worker implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text

from src.control_tower.progress import serialize_progress
from src.control_tower.refresh import sanitize_diagnostic
from src.control_tower.schema_guard import ensure_phase8_schema_ready

REFRESH_STATES = ("REQUESTED", "PREPARING", "DETECTING_CHANGES", "FETCHING", "RECONCILING", "VALIDATING", "REFRESHING_DERIVED_DATA", "PUBLISHING", "SUCCEEDED", "SUCCEEDED_NO_CHANGES", "FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED")
TERMINAL_STATES = frozenset({"SUCCEEDED", "SUCCEEDED_NO_CHANGES", "FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED", "COMPLETED", "FAILED"})
LEGACY_STATUS_PROJECTION = {"RUNNING": "FETCHING", "READY_FOR_PUBLISH": "PUBLISHING", "COMPLETED": "SUCCEEDED", "FAILED": "FAILED_PERMANENT", "ABORTED": "ABORTED"}
FAILURE_CLASSES = frozenset({"TRANSIENT", "PERMANENT", "INTERRUPTED", "ABORTED"})
_FAILURE_FOR_STATE = {"FAILED_TRANSIENT": "TRANSIENT", "FAILED_PERMANENT": "PERMANENT", "INTERRUPTED": "INTERRUPTED", "ABORTED": "ABORTED"}
_TRANSITIONS = {
    "REQUESTED": {"PREPARING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "PREPARING": {"DETECTING_CHANGES", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "DETECTING_CHANGES": {"FETCHING", "RECONCILING", "VALIDATING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "FETCHING": {"RECONCILING", "VALIDATING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "RECONCILING": {"VALIDATING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "VALIDATING": {"REFRESHING_DERIVED_DATA", "PUBLISHING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "REFRESHING_DERIVED_DATA": {"PUBLISHING", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
    "PUBLISHING": {"SUCCEEDED", "SUCCEEDED_NO_CHANGES", "INTERRUPTED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "ABORTED"},
}


def validate_failure_class(target: str, failure_class: Optional[str]) -> None:
    if failure_class is not None and failure_class not in FAILURE_CLASSES:
        raise ValueError(f"Unsupported refresh failure class: {failure_class}")
    expected = _FAILURE_FOR_STATE.get(target)
    if expected and failure_class != expected:
        raise ValueError(f"{target} requires failure class {expected}.")
    if failure_class is not None and not expected:
        raise ValueError(f"Failure class is not allowed for refresh state: {target}")


def validate_transition(current: str, target: str, failure_class: Optional[str] = None) -> None:
    if target not in REFRESH_STATES:
        raise ValueError(f"Unknown refresh state: {target}")
    if current in TERMINAL_STATES:
        raise ValueError(f"Terminal refresh run cannot transition: {current} -> {target}")
    validate_failure_class(target, failure_class)
    projected = LEGACY_STATUS_PROJECTION.get(current, current)
    if projected == target:
        return
    if target not in _TRANSITIONS.get(projected, set()):
        raise ValueError(f"Invalid refresh transition: {current} -> {target}")


def validate_retry_source_status(status: str) -> None:
    if status not in {"FAILED_TRANSIENT", "INTERRUPTED"}:
        raise ValueError("Only transient-failed or interrupted runs can be retried.")


def require_published_run(status: str, published_at: Any) -> None:
    if status not in {"SUCCEEDED", "COMPLETED"} or published_at is None:
        raise ValueError("Watermarks require a successfully published refresh run.")


def require_no_change_run(status: str, published_at: Any) -> None:
    if status != "SUCCEEDED_NO_CHANGES" or published_at is None:
        raise ValueError("No-change operations require a finalized no-change refresh run.")


def _utc(value: Optional[datetime]) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Refresh timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


class RefreshRunStateService:
    """Small PostgreSQL-backed state service; no worker loop or API coupling."""
    def __init__(self, postgres_client, *, schema_guard=ensure_phase8_schema_ready) -> None:
        self.pg = postgres_client
        schema_guard(postgres_client)

    def create_run(self, *, company_id: int, selected_domains: list[str], requested_by: Optional[str] = None, retry_of_run_id: Optional[str] = None, now: Optional[datetime] = None, attempt: int = 1) -> dict[str, Any]:
        from src.control_tower.contracts import resolve_domain_selection
        run_id = str(uuid4())
        timestamp = _utc(now)
        domains = [domain.key for domain in resolve_domain_selection(selected_domains)]
        with self.pg.engine.begin() as conn:
            pointer = conn.execute(text("SELECT run_id FROM ct_published_snapshot WHERE company_id = :company_id FOR UPDATE"), {"company_id": company_id}).scalar()
            conn.execute(text("""
                INSERT INTO ct_extraction_run
                    (run_id, started_at, requested_at, status, stage, company_id, requested_by,
                     retry_of_run_id, base_snapshot_run_id, attempt, selected_domains, progress)
                VALUES (CAST(:run_id AS UUID), :started_at, :requested_at, 'REQUESTED', 'REQUESTED',
                        :company_id, :requested_by, CAST(:retry_of AS UUID), CAST(:base AS UUID),
                        :attempt, CAST(:domains AS JSONB), '{}'::jsonb)
            """), {"run_id": run_id, "started_at": timestamp, "requested_at": timestamp, "company_id": company_id, "requested_by": requested_by, "retry_of": retry_of_run_id, "base": str(pointer) if pointer else None, "attempt": attempt, "domains": json.dumps(domains)})
        return {"run_id": run_id, "status": "REQUESTED", "company_id": company_id, "attempt": attempt}

    def transition(self, run_id: str, target: str, *, failure_class: Optional[str] = None, error_message: Optional[str] = None, progress: Optional[dict[str, Any]] = None, now: Optional[datetime] = None) -> None:
        timestamp = _utc(now)
        serialized_progress = serialize_progress(progress) if progress is not None else None
        with self.pg.engine.begin() as conn:
            row = conn.execute(text("SELECT status, stage FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE"), {"run_id": run_id}).mappings().first()
            if not row:
                raise ValueError("Refresh run was not found.")
            validate_transition(row["status"], target, failure_class)
            conn.execute(text("""
                UPDATE ct_extraction_run SET status = :status, stage = :stage,
                    stage_started_at = CASE WHEN stage IS DISTINCT FROM :stage THEN :now ELSE stage_started_at END,
                    heartbeat_at = :now, failure_class = :failure_class,
                    error_message = COALESCE(:error_message, error_message),
                    last_error_at = CASE WHEN :error_message IS NULL THEN last_error_at ELSE :now END,
                    progress = COALESCE(CAST(:progress AS JSONB), progress),
                    completed_at = CASE WHEN :terminal THEN COALESCE(completed_at, :now) ELSE completed_at END,
                    finished_at = CASE WHEN :terminal THEN COALESCE(finished_at, :now) ELSE finished_at END,
                    duration_seconds = CASE
                        WHEN :terminal THEN COALESCE(duration_seconds, EXTRACT(EPOCH FROM (:now - started_at)))
                        ELSE duration_seconds
                    END
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_id, "status": target, "stage": target, "now": timestamp, "failure_class": failure_class, "error_message": sanitize_diagnostic(error_message) if error_message else None, "progress": serialized_progress, "terminal": target in TERMINAL_STATES})

    def finalize_no_change(self, run_id: str, *, now: Optional[datetime] = None) -> None:
        timestamp = _utc(now)
        with self.pg.engine.begin() as conn:
            run = conn.execute(text("SELECT company_id, status, base_snapshot_run_id, started_at FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE"), {"run_id": run_id}).mappings().first()
            if not run:
                raise ValueError("Refresh run was not found.")
            validate_transition(run["status"], "SUCCEEDED_NO_CHANGES")
            pointer = conn.execute(text("SELECT run_id FROM ct_published_snapshot WHERE company_id = :company_id FOR UPDATE"), {"company_id": run["company_id"]}).scalar()
            if not run["base_snapshot_run_id"] or str(run["base_snapshot_run_id"]) != str(pointer):
                raise ValueError("No-change finalization requires the trusted snapshot to remain unchanged.")
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET status = 'SUCCEEDED_NO_CHANGES',
                    stage = 'SUCCEEDED_NO_CHANGES',
                    published_at = :now,
                    completed_at = :now,
                    finished_at = :now,
                    duration_seconds = EXTRACT(EPOCH FROM (:now - started_at)),
                    heartbeat_at = :now,
                    stage_started_at = :now,
                    failure_class = NULL
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_id, "now": timestamp})

    def heartbeat(self, run_id: str, *, now: Optional[datetime] = None) -> None:
        with self.pg.engine.begin() as conn:
            result = conn.execute(text("UPDATE ct_extraction_run SET heartbeat_at = :now WHERE run_id = CAST(:run_id AS UUID) AND status NOT IN ('SUCCEEDED','SUCCEEDED_NO_CHANGES','FAILED_TRANSIENT','FAILED_PERMANENT','INTERRUPTED','ABORTED','COMPLETED','FAILED')"), {"run_id": run_id, "now": _utc(now)})
            if result.rowcount != 1:
                raise ValueError("Heartbeat rejected for missing or terminal refresh run.")

    def create_retry(self, run_id: str, *, requested_by: Optional[str] = None, now: Optional[datetime] = None) -> dict[str, Any]:
        new_id = str(uuid4())
        timestamp = _utc(now)
        with self.pg.engine.begin() as conn:
            source = conn.execute(text("SELECT run_id, company_id, status, attempt, selected_domains, base_snapshot_run_id FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE"), {"run_id": run_id}).mappings().first()
            if not source:
                raise ValueError("Refresh run was not found.")
            validate_retry_source_status(source["status"])
            if isinstance(source["attempt"], bool) or not isinstance(source["attempt"], int) or source["attempt"] < 1:
                raise ValueError("Retry source has an invalid attempt number.")
            if not isinstance(source["selected_domains"], list) or not all(isinstance(domain, str) for domain in source["selected_domains"]):
                raise ValueError("Retry source has malformed selected domains.")
            if str(source["run_id"]) == new_id:
                raise ValueError("A retry cannot reference itself.")
            lineage = conn.execute(text("""
                WITH RECURSIVE chain(run_id, retry_of_run_id, path, has_cycle) AS (
                    SELECT run_id, retry_of_run_id, ARRAY[run_id], FALSE
                    FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
                    UNION ALL
                    SELECT parent.run_id, parent.retry_of_run_id,
                           chain.path || parent.run_id,
                           parent.run_id = ANY(chain.path)
                    FROM ct_extraction_run parent JOIN chain
                      ON parent.run_id = chain.retry_of_run_id
                    WHERE NOT chain.has_cycle
                ) SELECT COALESCE(bool_or(has_cycle), FALSE) FROM chain
            """), {"run_id": run_id}).scalar()
            missing_parent = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM ct_extraction_run child
                    LEFT JOIN ct_extraction_run parent
                      ON parent.run_id = child.retry_of_run_id
                    WHERE child.run_id = CAST(:run_id AS UUID)
                      AND child.retry_of_run_id IS NOT NULL
                      AND parent.run_id IS NULL
                )
            """), {"run_id": run_id}).scalar()
            if lineage or missing_parent:
                raise ValueError("Retry lineage contains a cycle or malformed parent reference.")
            conn.execute(text("""
                INSERT INTO ct_extraction_run
                    (run_id, started_at, requested_at, status, stage, company_id, requested_by,
                     retry_of_run_id, base_snapshot_run_id, attempt, selected_domains, progress)
                VALUES (CAST(:new_id AS UUID), :now, :now, 'REQUESTED', 'REQUESTED', :company_id, :requested_by,
                        CAST(:source AS UUID), CAST(:base AS UUID), :attempt, CAST(:domains AS JSONB), '{}'::jsonb)
            """), {"new_id": new_id, "now": timestamp, "company_id": source["company_id"], "requested_by": requested_by, "source": run_id, "base": str(source["base_snapshot_run_id"]) if source["base_snapshot_run_id"] else None, "attempt": source["attempt"] + 1, "domains": json.dumps(source["selected_domains"] or [])})
        return {"run_id": new_id, "status": "REQUESTED", "company_id": source["company_id"], "attempt": source["attempt"] + 1, "retry_of_run_id": run_id}
