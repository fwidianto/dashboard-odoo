"""Durable parent reconciliation queue contracts and bounded execution service.

The queue contracts define durable claims; the execution service performs the
smallest supported parent/child set reconciliation for changed sets.  No
speculative global deletion crawler, periodic orphan sweep, or generic event
system is built here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

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


class ReconciliationExecutionError(ValueError):
    """Raised when a parent set cannot be reconciled truthfully."""

    def __init__(self, message: str, *, requires_new_retry: bool = False) -> None:
        super().__init__(message)
        self.requires_new_retry = requires_new_retry


class ReconciliationExecutionService:
    """Execute the smallest supported parent/child set reconciliation.

    Only ``PARENT_CURRENT_CHILD_SET`` strategy sets registered in the domain
    contract are reconciled.  The current complete child set is read from Odoo
    with approved fields and read-only access, candidate rows become an exact
    representation of that evidence, and removed/unlinked children are removed
    only when the native relation proves the unlink.
    """

    def __init__(self, postgres_client, *, batch_size: int = 500) -> None:
        self.pg = postgres_client
        self._queue = ReconciliationQueueService(postgres_client)
        self._batch_size = batch_size
        self._metadata_cache: dict[str, dict] = {}

    # -- manifest-driven enqueue ---------------------------------------------

    def enqueue_from_manifest(self, *, run_id: str, company_id: int) -> int:
        """Enqueue affected parent/child sets from the completed change manifest."""
        from src.control_tower.contracts import DOMAIN_REGISTRY

        supported: set[tuple[str, str, str]] = set()
        for domain in DOMAIN_REGISTRY:
            for relation in domain.parent_children:
                if relation.strategy == "PARENT_CURRENT_CHILD_SET":
                    supported.add((relation.parent_model, relation.child_model))

        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model, parent_model, parent_record_id, parent_hints
                FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID)
                  AND company_id = :company_id
                  AND status <> 'DETECTED'
            """), {"run_id": run_id, "company_id": company_id}).mappings().all()

        hints: set[tuple[str, int, str]] = set()
        for row in rows:
            child_model = row["model"]
            parent_model = row["parent_model"]
            parent_id = row["parent_record_id"]
            if parent_model and parent_id:
                if (parent_model, child_model) in supported:
                    hints.add((parent_model, int(parent_id), child_model))
            for hint in row["parent_hints"] or []:
                if not isinstance(hint, dict):
                    continue
                hinted_model = hint.get("parent_model")
                hinted_id = hint.get("parent_record_id")
                if hinted_model and hinted_id and (hinted_model, child_model) in supported:
                    hints.add((hinted_model, int(hinted_id), child_model))

        for parent_model, parent_id, child_model in sorted(hints):
            self._queue.enqueue(
                company_id=company_id,
                parent_model=parent_model,
                parent_id=parent_id,
                child_model=child_model,
                reason="changed_child_set",
                source_run_id=run_id,
            )
        return len(hints)

    # -- execution -----------------------------------------------------------

    def execute(
        self,
        *,
        run_id: str,
        company_id: int,
        odoo_client,
        worker_id: str = "incremental-refresh",
        now: datetime | None = None,
        limit: int = 100,
    ) -> dict:
        """Claim and process reconciliation sets; returns durable totals."""
        from src.control_tower.fetch_apply import (
            _build_field_contract,
            _normalize_record,
            _validated_field_metadata,
        )

        now = normalize_reconciliation_timestamp(now)
        claimed = self._queue.claim(
            company_id=company_id, worker_id=worker_id, limit=limit, now=now,
        )
        if not claimed:
            return {
                "sets_claimed": 0, "sets_completed": 0, "records_read": 0,
                "records_removed": 0, "next_required_stage": "VALIDATING",
            }

        totals = {"sets_claimed": 0, "sets_completed": 0, "records_read": 0, "records_removed": 0}
        for item in claimed:
            totals["sets_claimed"] += 1
            key = {
                "company_id": company_id,
                "parent_model": item["parent_model"],
                "parent_id": int(item["parent_id"]),
                "child_model": item["child_model"],
            }
            claimed_generation = int(item["claimed_generation"])
            try:
                read_count, removed_count = self._reconcile_set(
                    run_id=run_id, company_id=company_id, odoo_client=odoo_client,
                    parent_model=key["parent_model"], parent_id=key["parent_id"],
                    child_model=key["child_model"], now=now,
                )
                self._queue.complete(key, claimed_generation=claimed_generation, now=now)
                totals["sets_completed"] += 1
                totals["records_read"] += read_count
                totals["records_removed"] += removed_count
            except ReconciliationExecutionError:
                raise
            except Exception as exc:
                try:
                    self._queue.fail(key, claimed_generation=claimed_generation, now=now)
                except Exception:
                    pass
                raise ReconciliationExecutionError(
                    f"Reconciliation failed durably; evidence is preserved and a linked retry is required: {exc}",
                    requires_new_retry=True,
                ) from exc

        remaining = self.pending_count(run_id, company_id)
        totals["next_required_stage"] = "VALIDATING" if remaining == 0 else "RECONCILING"
        return totals

    def pending_count(self, run_id: str, company_id: int) -> int:
        with self.pg.engine.connect() as conn:
            return int(conn.execute(text("""
                SELECT COUNT(*) FROM ct_parent_reconciliation_queue
                WHERE company_id = :company_id
                  AND source_run_id = CAST(:run_id AS UUID)
                  AND status <> 'COMPLETED'
            """), {"company_id": company_id, "run_id": run_id}).scalar())

    def _field_metadata(self, model: str, odoo_client) -> dict:
        if model not in self._metadata_cache:
            from src.control_tower.fetch_apply import _validated_field_metadata

            metadata = odoo_client.get_model_fields(model)
            if not isinstance(metadata, dict):
                raise ReconciliationExecutionError(f"Odoo model metadata is malformed for {model}.")
            self._metadata_cache[model] = _validated_field_metadata(model, metadata)
        return self._metadata_cache[model]

    def _parent_field(self, parent_model: str, child_model: str) -> str:
        from src.control_tower.contracts import DOMAIN_REGISTRY

        for domain in DOMAIN_REGISTRY:
            for relation in domain.parent_children:
                if (
                    relation.strategy == "PARENT_CURRENT_CHILD_SET"
                    and relation.parent_model == parent_model
                    and relation.child_model == child_model
                ):
                    return relation.parent_field
        raise ReconciliationExecutionError(
            f"Unsupported parent/child reconciliation set: {parent_model} -> {child_model}"
        )

    def _reconcile_set(
        self, *, run_id, company_id, odoo_client, parent_model, parent_id, child_model, now,
    ) -> tuple[int, int]:
        from src.control_tower.fetch_apply import (
            _build_field_contract,
            _normalize_record,
        )

        parent_field = self._parent_field(parent_model, child_model)
        fields = list(_build_field_contract(child_model))
        metadata = self._field_metadata(child_model, odoo_client)
        domain = [("company_id", "=", company_id), (parent_field, "=", parent_id)]
        records = odoo_client.search_read(
            child_model, domain, fields=fields, order="id asc", limit=self._batch_size,
        )
        if not isinstance(records, list):
            raise ReconciliationExecutionError(
                f"Odoo search_read returned a non-list for {child_model}."
            )
        if len(records) > self._batch_size:
            raise ReconciliationExecutionError(
                f"Odoo reconciliation exceeded the batch limit for {child_model}."
            )

        current_ids: set[int] = set()
        apply_rows: list[dict] = []
        for record in records:
            normalized = _normalize_record(record, child_model, company_id, metadata)
            record_id = int(normalized["record_id"])
            if record_id in current_ids:
                raise ReconciliationExecutionError(
                    f"Odoo reconciliation returned a duplicate row for {child_model}/{record_id}."
                )
            current_ids.add(record_id)
            apply_rows.append({
                "run_id": run_id,
                "model": child_model,
                "record_id": record_id,
                "document_number": normalized["document_number"],
                "state": normalized["state"],
                "company_id": normalized["company_id"],
                "company_name": normalized["company_name"],
                "write_date": normalized["write_date"],
                "payload": json.dumps(
                    normalized["payload"], sort_keys=True, separators=(",", ":"), default=str
                ),
                "extracted_at": now,
            })

        self._upsert_candidate_rows(apply_rows)
        removed = self._remove_unlinked_children(
            run_id=run_id, company_id=company_id, child_model=child_model,
            parent_field=parent_field, parent_id=parent_id, current_ids=current_ids,
            odoo_client=odoo_client, fields=fields, metadata=metadata,
        )
        return len(apply_rows), removed

    def _upsert_candidate_rows(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self.pg.engine.begin() as conn:
            for row in rows:
                conn.execute(text("""
                    INSERT INTO ct_native_record_snapshot
                        (extraction_run_id, model, record_id, document_number, state,
                         company_id, company_name, write_date, payload, extracted_at)
                    VALUES (CAST(:run_id AS UUID), :model, :record_id, :document_number,
                            :state, :company_id, :company_name, :write_date,
                            CAST(:payload AS JSONB), :extracted_at)
                    ON CONFLICT (extraction_run_id, model, record_id) DO UPDATE SET
                        document_number = EXCLUDED.document_number,
                        state = EXCLUDED.state,
                        company_id = EXCLUDED.company_id,
                        company_name = EXCLUDED.company_name,
                        write_date = EXCLUDED.write_date,
                        payload = EXCLUDED.payload,
                        extracted_at = EXCLUDED.extracted_at
                """), {
                    "run_id": row["run_id"], "model": row["model"],
                    "record_id": row["record_id"], "document_number": row["document_number"],
                    "state": row["state"], "company_id": row["company_id"],
                    "company_name": row["company_name"], "write_date": row["write_date"],
                    "payload": row["payload"], "extracted_at": row["extracted_at"],
                })

    def _remove_unlinked_children(
        self, *, run_id, company_id, child_model, parent_field, parent_id,
        current_ids, odoo_client, fields, metadata,
    ) -> int:
        """Remove candidate children only when the native relation proves unlink.

        A candidate child still linked to this parent in Odoo must remain.
        A child whose Odoo relation no longer points to this parent (moved or
        deleted) is removed from the candidate.  Ambiguity fails closed.
        """
        from src.control_tower.fetch_apply import _normalize_record

        with self.pg.engine.connect() as conn:
            candidate_rows = conn.execute(text("""
                SELECT record_id, payload
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                  AND model = :child_model
                  AND payload -> :parent_field ->> 'id' = CAST(:parent_id AS TEXT)
            """), {
                "run_id": run_id, "child_model": child_model,
                "parent_field": parent_field, "parent_id": parent_id,
            }).mappings().all()

        removed = 0
        for row in candidate_rows:
            record_id = int(row["record_id"])
            if record_id in current_ids:
                continue
            probe = odoo_client.search_read(
                child_model, [("id", "=", record_id), ("company_id", "=", company_id)],
                fields=fields, order="id asc", limit=1,
            )
            if not isinstance(probe, list) or len(probe) > 1:
                raise ReconciliationExecutionError(
                    f"Odoo unlink probe returned an invalid result for {child_model}/{record_id}.",
                    requires_new_retry=True,
                )
            if not probe:
                removed += self._delete_candidate(run_id, child_model, record_id)
                continue
            normalized = _normalize_record(probe[0], child_model, company_id, metadata)
            linked_parent = None
            value = normalized["payload"].get(parent_field)
            if isinstance(value, dict) and isinstance(value.get("id"), int):
                linked_parent = value["id"]
            elif value is not None:
                raise ReconciliationExecutionError(
                    f"Unsupported relation representation for {child_model}.{parent_field}.",
                    requires_new_retry=True,
                )
            if linked_parent is None or linked_parent != parent_id:
                removed += self._delete_candidate(run_id, child_model, record_id)
                continue
            raise ReconciliationExecutionError(
                f"Odoo child still points to this parent despite the set probe: {child_model}/{record_id}.",
                requires_new_retry=True,
            )
        return removed

    def _delete_candidate(self, run_id: str, model: str, record_id: int) -> int:
        with self.pg.engine.begin() as conn:
            result = conn.execute(text("""
                DELETE FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                  AND model = :model AND record_id = :record_id
            """), {"run_id": run_id, "model": model, "record_id": record_id})
        return int(result.rowcount)
