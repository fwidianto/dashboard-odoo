"""Durable parent reconciliation queue contracts; no Odoo work is performed."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from src.control_tower.schema_guard import ensure_phase8_schema_ready


def completion_status(current_generation: int, claimed_generation: int) -> str:
    return "COMPLETED" if current_generation == claimed_generation else "PENDING"


def normalize_reconciliation_timestamp(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Reconciliation timestamps must be timezone-aware datetimes.")
    return value.astimezone(timezone.utc)


def _normalize_returned_timestamps(row: dict) -> dict:
    for field in (
        "last_checked_at",
        "last_touched_at",
        "created_at",
        "updated_at",
        "last_sweep_started_at",
        "last_sweep_completed_at",
    ):
        if row.get(field) is not None:
            row[field] = normalize_reconciliation_timestamp(row[field])
    return row


class ReconciliationQueueService:
    def __init__(self, postgres_client, *, schema_guard=ensure_phase8_schema_ready) -> None:
        self.pg = postgres_client
        schema_guard(postgres_client)

    def enqueue(self, *, company_id: int, parent_model: str, parent_id: int,
                child_model: str, reason: str, source_run_id: str | None = None,
                now: datetime | None = None) -> None:
        now = normalize_reconciliation_timestamp(now)
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ct_parent_reconciliation_queue
                    (company_id, parent_model, parent_id, child_model, reason,
                     source_run_id, generation, last_touched_at, created_at, updated_at)
                VALUES (:company_id, :parent_model, :parent_id, :child_model, :reason,
                        CAST(:source_run_id AS UUID), 1, :now, :now, :now)
                ON CONFLICT (company_id, parent_model, parent_id, child_model) DO UPDATE SET
                    reason = EXCLUDED.reason, source_run_id = EXCLUDED.source_run_id,
                    generation = ct_parent_reconciliation_queue.generation + 1,
                    last_touched_at = EXCLUDED.last_touched_at,
                    updated_at = EXCLUDED.updated_at,
                    status = CASE WHEN ct_parent_reconciliation_queue.status = 'RUNNING'
                                  THEN 'RUNNING' ELSE 'PENDING' END
            """), {"company_id": company_id, "parent_model": parent_model, "parent_id": parent_id, "child_model": child_model, "reason": reason, "source_run_id": source_run_id, "now": now})

    def claim(self, *, company_id: int, worker_id: str, limit: int = 100,
              now: datetime | None = None) -> list[dict]:
        now = normalize_reconciliation_timestamp(now)
        with self.pg.engine.begin() as conn:
            rows = conn.execute(text("""
                WITH picked AS (
                    SELECT company_id, parent_model, parent_id, child_model
                    FROM ct_parent_reconciliation_queue
                    WHERE company_id = :company_id AND status = 'PENDING'
                    ORDER BY last_touched_at, parent_model, parent_id, child_model
                    FOR UPDATE SKIP LOCKED LIMIT :limit
                )
                UPDATE ct_parent_reconciliation_queue q
                SET status = 'RUNNING', claimed_by = :worker_id,
                    claimed_generation = q.generation, attempts = q.attempts + 1,
                    updated_at = :now
                FROM picked p
                WHERE (q.company_id, q.parent_model, q.parent_id, q.child_model) =
                      (p.company_id, p.parent_model, p.parent_id, p.child_model)
                RETURNING q.*
            """), {"company_id": company_id, "worker_id": worker_id, "limit": limit, "now": now}).mappings().all()
        return [_normalize_returned_timestamps(dict(row)) for row in rows]

    def _finish(self, key: dict, *, success: bool, claimed_generation: int,
                now: datetime | None = None) -> str:
        now = normalize_reconciliation_timestamp(now)
        with self.pg.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE ct_parent_reconciliation_queue
                SET status = CASE WHEN generation = :claimed_generation
                                  THEN :success_status ELSE 'PENDING' END,
                    last_checked_at = CASE WHEN :success THEN :now ELSE last_checked_at END,
                    claimed_by = NULL, claimed_generation = NULL, updated_at = :now
                WHERE company_id = :company_id AND parent_model = :parent_model
                  AND parent_id = :parent_id AND child_model = :child_model
                  AND status = 'RUNNING' AND claimed_generation = :claimed_generation
                RETURNING status
            """), {**key, "claimed_generation": claimed_generation, "success_status": "COMPLETED" if success else "PENDING", "success": success, "now": now}).scalar()
        if row is None:
            raise ValueError("Stale or unclaimed reconciliation completion.")
        return row

    def complete(self, key: dict, *, claimed_generation: int, now: datetime | None = None) -> str:
        return self._finish(key, success=True, claimed_generation=claimed_generation, now=now)

    def fail(self, key: dict, *, claimed_generation: int, now: datetime | None = None) -> str:
        return self._finish(key, success=False, claimed_generation=claimed_generation, now=now)

    def advance_cursor(self, *, company_id: int, parent_model: str, child_model: str,
                       expected_version: int, last_parent_id: int | None,
                       now: datetime | None = None) -> dict:
        now = normalize_reconciliation_timestamp(now)
        with self.pg.engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE ct_parent_reconciliation_cursor
                SET last_parent_id = :last_parent_id, version = version + 1,
                    last_sweep_completed_at = :now, updated_at = :now
                WHERE company_id = :company_id AND parent_model = :parent_model
                  AND child_model = :child_model AND version = :expected_version
                RETURNING *
            """), {"company_id": company_id, "parent_model": parent_model, "child_model": child_model, "expected_version": expected_version, "last_parent_id": last_parent_id, "now": now})
            row = result.mappings().first()
        if row is None:
            raise ValueError("Stale reconciliation cursor version.")
        return _normalize_returned_timestamps(dict(row))
