"""Phase 8E-1 continuation: complete an incremental refresh through terminal states.

The normal Refresh Data path creates a durable run and runs the existing
orchestrator through copy-forward, detection, and fetch/apply.  This module
continues a run that has reached ``RECONCILING`` (changed data) or
``VALIDATING`` (no changes) through reconciliation, candidate validation,
derived Control Tower data refresh, atomic publication, and watermark
advancement.

It reuses the approved state machine, copy-forward, detection, fetch/apply,
reconciliation queue, watermark store, and publication SQL.  It never fetches
the full approved dataset and never calls ``ControlTowerRelationExtractor.run``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from sqlalchemy import text

from src.control_tower.contracts import resolve_domain_selection
from src.control_tower.progress import parse_progress_json, serialize_progress
from src.control_tower.reconciliation import ReconciliationExecutionService
from src.control_tower.refresh import SQL_PATHS, sanitize_diagnostic
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.schema_guard import ensure_phase8_schema_ready
from src.control_tower.watermarks import (
    ControlTowerWatermarkStore,
    watermark_displayed_second,
)


class RefreshContinuationError(ValueError):
    """Raised when an incremental run cannot safely complete."""

    def __init__(self, message: str, *, requires_new_retry: bool = False) -> None:
        super().__init__(message)
        self.requires_new_retry = requires_new_retry


def _utc(value: Optional[datetime]) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise RefreshContinuationError("Continuation timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _elapsed(started_at: datetime, finished_at: datetime) -> float:
    return round(max(0.0, (finished_at - started_at).total_seconds()), 6)


class RefreshContinuationService:
    """Complete one incremental refresh run to a truthful terminal state."""

    def __init__(
        self,
        postgres_client,
        *,
        schema_guard=ensure_phase8_schema_ready,
        sql_paths: tuple[Path, ...] = SQL_PATHS,
    ) -> None:
        self.pg = postgres_client
        schema_guard(postgres_client)
        self._state = RefreshRunStateService(postgres_client)
        self._reconciliation = ReconciliationExecutionService(postgres_client)
        self._watermarks = ControlTowerWatermarkStore(postgres_client)
        self._sql_paths = sql_paths

    # -- public entry ---------------------------------------------------------

    def complete(
        self,
        *,
        run_id: str,
        company_id: int,
        odoo_client,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Continue a run at RECONCILING or VALIDATING to a terminal state."""
        timestamp = _utc(now)
        run = self._read_run(run_id)
        if run is None:
            raise RefreshContinuationError("Refresh run was not found.")
        if int(run["company_id"]) != company_id:
            raise RefreshContinuationError("Refresh run belongs to a different company.")

        if run["status"] in {"SUCCEEDED", "SUCCEEDED_NO_CHANGES", "COMPLETED"}:
            return self._terminal_result(run)
        if run["status"] in {"FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED", "FAILED"}:
            raise RefreshContinuationError(
                f"Refresh run is {run['status']} and cannot be completed as a clean run.",
                requires_new_retry=run["status"] in {"FAILED_TRANSIENT", "INTERRUPTED"},
            )

        if run["status"] == "RECONCILING":
            run = self._complete_reconciliation(run, company_id, odoo_client, timestamp)

        if run["status"] == "VALIDATING":
            return self._complete_validation(run, company_id, odoo_client, timestamp)

        if run["status"] in {"SUCCEEDED", "SUCCEEDED_NO_CHANGES", "COMPLETED"}:
            return self._terminal_result(run)

        raise RefreshContinuationError(
            f"Refresh run is in an unsupported continuation state: {run['status']}"
        )

    # -- stage completion -----------------------------------------------------

    def _complete_reconciliation(
        self,
        run: dict[str, Any],
        company_id: int,
        odoo_client,
        timestamp: datetime,
    ) -> dict[str, Any]:
        progress = parse_progress_json(run["progress"])
        if progress.get("reconciliation_complete"):
            run = self._transition_to_validating(run, company_id, timestamp)
            if run is None:
                raise RefreshContinuationError("Refresh run disappeared during reconciliation.")
            return run

        started = timestamp
        progress = dict(progress)
        progress.update({
            "reconciliation_started_at": started.isoformat(),
            "reconciliation_sets_planned": list(progress.get("reconciliation_sets_planned") or []),
            "reconciliation_sets_completed_list": list(progress.get("reconciliation_sets_completed_list") or []),
        })
        self._write_progress(run["run_id"], progress)

        enqueued = self._reconciliation.enqueue_from_manifest(
            run_id=run["run_id"], company_id=company_id,
        )
        planned = list(progress.get("reconciliation_sets_planned") or [])
        progress["reconciliation_sets_enqueued"] = enqueued

        try:
            summary = self._reconciliation.execute(
                run_id=run["run_id"], company_id=company_id, odoo_client=odoo_client,
                worker_id=f"run-{run['run_id']}", now=timestamp,
            )
        except Exception as exc:
            if isinstance(exc, RefreshContinuationError):
                raise
            raise RefreshContinuationError(
                f"Reconciliation failed closed; evidence is preserved and a linked retry is required: {exc}",
                requires_new_retry=True,
            ) from exc
        finished = _utc(timestamp)
        progress.update({
            "reconciliation_sets_enqueued": enqueued,
            "reconciliation_sets_completed": summary["sets_completed"],
            "reconciliation_records_read": summary["records_read"],
            "reconciliation_records_removed": summary["records_removed"],
            "reconciliation_finished_at": finished.isoformat(),
            "reconciliation_elapsed_seconds": _elapsed(started, finished),
            "reconciliation_complete": True,
        })
        self._write_progress(run["run_id"], progress)

        run = self._transition_to_validating(run, company_id, timestamp)
        if run is None:
            raise RefreshContinuationError("Refresh run disappeared after reconciliation.")
        return run

    def _transition_to_validating(
        self, run: dict[str, Any], company_id: int, timestamp: datetime,
    ) -> Optional[dict[str, Any]]:
        current = self._read_run(run["run_id"])
        if current is None:
            raise RefreshContinuationError("Refresh run disappeared before the VALIDATING transition.")
        progress = parse_progress_json(current["progress"])
        progress.update({
            "orchestration_current_stage": "VALIDATING",
            "orchestration_last_completed_stage": "RECONCILING",
            "orchestration_next_required_stage": "VALIDATING",
        })
        try:
            self._state.transition(
                run["run_id"], "VALIDATING", progress=progress, now=timestamp,
            )
        except ValueError as exc:
            refreshed = self._read_run(run["run_id"])
            if refreshed and refreshed["status"] in {"SUCCEEDED", "SUCCEEDED_NO_CHANGES", "COMPLETED"}:
                return refreshed
            raise RefreshContinuationError(
                f"Stale state transition rejected before VALIDATING: {exc}",
                requires_new_retry=True,
            ) from exc
        return self._read_run(run["run_id"])

    def _complete_validation(
        self,
        run: dict[str, Any],
        company_id: int,
        odoo_client,
        timestamp: datetime,
    ) -> dict[str, Any]:
        progress = parse_progress_json(run["progress"])
        no_changes = bool(
            progress.get("orchestration_no_changes")
            or progress.get("detection_manifest_row_count", 0) == 0
        )
        if progress.get("validation_complete"):
            return self._finalize_validated(run, company_id, timestamp, no_changes=no_changes)

        started = timestamp
        progress = dict(progress)
        progress.update({
            "validation_started_at": started.isoformat(),
        })
        self._write_progress(run["run_id"], progress)

        self._validate_candidate(run, company_id, no_changes=no_changes)
        finished = _utc(timestamp)
        progress.update({
            "validation_finished_at": finished.isoformat(),
            "validation_elapsed_seconds": _elapsed(started, finished),
            "validation_complete": True,
        })
        self._write_progress(run["run_id"], progress)
        return self._finalize_validated(run, company_id, timestamp, no_changes=no_changes)

    def _finalize_validated(
        self, run: dict[str, Any], company_id: int, timestamp: datetime, *, no_changes: bool,
    ) -> dict[str, Any]:
        if no_changes:
            return self._finalize_no_changes(run, company_id, timestamp)
        return self._publish_changed(run, company_id, timestamp)

    # -- no-change path -------------------------------------------------------

    def _finalize_no_changes(
        self, run: dict[str, Any], company_id: int, timestamp: datetime,
    ) -> dict[str, Any]:
        run_id = run["run_id"]
        refreshed = self._read_run(run_id)
        if refreshed and refreshed["status"] == "SUCCEEDED_NO_CHANGES":
            return self._terminal_result(refreshed)
        try:
            self._state.transition(run_id, "PUBLISHING", now=timestamp)
        except ValueError as exc:
            refreshed = self._read_run(run_id)
            if refreshed and refreshed["status"] == "SUCCEEDED_NO_CHANGES":
                return self._terminal_result(refreshed)
            raise RefreshContinuationError(
                f"Stale state transition rejected before no-change finalization: {exc}",
                requires_new_retry=True,
            ) from exc
        self._state.finalize_no_change(run_id, now=timestamp)
        self._record_no_change_watermarks(run_id, company_id, timestamp)
        return self._terminal_result(self._read_run(run_id))

    def _record_no_change_watermarks(self, run_id: str, company_id: int, timestamp: datetime) -> None:
        models = self._run_models(run_id)
        for model in models:
            self._watermarks.record_no_change_checked_at(
                company_id=company_id, model=model, run_id=run_id, now=timestamp,
            )

    def _run_models(self, run_id: str) -> list[str]:
        with self.pg.engine.connect() as conn:
            selected = conn.execute(
                text("SELECT selected_domains FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"),
                {"run_id": run_id},
            ).scalar()
        resolved = resolve_domain_selection(selected or ("all",))
        from src.control_tower.contracts import resolve_model_keys
        return list(resolve_model_keys([domain.key for domain in resolved]))

    # -- changed publication path ---------------------------------------------

    def _publish_changed(self, run: dict[str, Any], company_id: int, timestamp: datetime) -> dict[str, Any]:
        run_id = run["run_id"]
        refreshed = self._read_run(run_id)
        if refreshed and refreshed["status"] == "SUCCEEDED":
            return self._terminal_result(refreshed)

        started = timestamp
        progress = parse_progress_json(refreshed["progress"] if refreshed else run["progress"])
        progress = dict(progress)
        progress.update({
            "derived_started_at": started.isoformat(),
            "orchestration_current_stage": "REFRESHING_DERIVED_DATA",
            "orchestration_last_completed_stage": "VALIDATING",
            "orchestration_next_required_stage": "REFRESHING_DERIVED_DATA",
        })
        try:
            self._state.transition(run_id, "REFRESHING_DERIVED_DATA", progress=progress, now=started)
        except ValueError as exc:
            refreshed = self._read_run(run_id)
            if refreshed and refreshed["status"] == "SUCCEEDED":
                return self._terminal_result(refreshed)
            raise RefreshContinuationError(
                f"Stale state transition rejected before derived refresh: {exc}",
                requires_new_retry=True,
            ) from exc

        derived_finished = _utc(started)
        progress = dict(progress)
        progress.update({
            "derived_finished_at": derived_finished.isoformat(),
            "derived_refresh_complete": True,
            "orchestration_current_stage": "PUBLISHING",
            "orchestration_last_completed_stage": "REFRESHING_DERIVED_DATA",
            "orchestration_next_required_stage": "PUBLISHING",
        })
        try:
            self._state.transition(run_id, "PUBLISHING", progress=progress, now=derived_finished)
        except ValueError as exc:
            refreshed = self._read_run(run_id)
            if refreshed and refreshed["status"] == "SUCCEEDED":
                return self._terminal_result(refreshed)
            raise RefreshContinuationError(
                f"Stale state transition rejected before publication: {exc}",
                requires_new_retry=True,
            ) from exc

        publication_started = derived_finished
        try:
            self._publish_and_advance(run_id, company_id, publication_started)
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise RefreshContinuationError(
                f"Publication failed closed; trusted snapshot and watermarks are unchanged: {sanitize_diagnostic(exc)}",
                requires_new_retry=True,
            ) from exc

        final = self._read_run(run_id)
        if final is None or final["status"] != "SUCCEEDED":
            raise RefreshContinuationError("Publication completed without a truthful SUCCEEDED run.")
        return self._terminal_result(final)

    def _publish_and_advance(self, run_id: str, company_id: int, timestamp: datetime) -> None:
        """Atomically update the trusted pointer, run SQL, finalize, and advance watermarks."""
        completed_at = _utc(timestamp)
        with self.pg.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT company_id, status, base_snapshot_run_id::text AS base_snapshot_run_id,
                       started_at, model_counts, requested_by
                FROM ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                FOR UPDATE
            """), {"run_id": run_id}).mappings().first()
            if not row or int(row["company_id"]) != company_id:
                raise RefreshContinuationError("Refresh candidate was not found for this company.")
            if str(row["status"]) != "PUBLISHING":
                raise RefreshContinuationError(
                    f"Refresh candidate is {row['status']}, not PUBLISHING."
                )

            pointer = conn.execute(text("""
                SELECT run_id::text AS run_id, published_at
                FROM ct_published_snapshot
                WHERE company_id = :company_id
                FOR UPDATE
            """), {"company_id": company_id}).mappings().first()
            if not pointer:
                raise RefreshContinuationError("No trusted published snapshot exists for publication.")
            if not row["base_snapshot_run_id"] or str(row["base_snapshot_run_id"]) != str(pointer["run_id"]):
                raise RefreshContinuationError(
                    "Candidate base snapshot is stale; the trusted published snapshot changed."
                )

            previous_run_id = pointer["run_id"]
            model_counts = self._candidate_model_counts(conn, run_id)
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET status = 'SUCCEEDED', stage = 'SUCCEEDED',
                    completed_at = :completed_at, finished_at = :completed_at,
                    published_at = :completed_at,
                    duration_seconds = EXTRACT(EPOCH FROM (:completed_at - started_at)),
                    model_counts = CAST(:model_counts AS JSONB),
                    failure_class = NULL,
                    error_message = NULL
                WHERE run_id = CAST(:run_id AS UUID)
            """), {
                "run_id": run_id, "completed_at": completed_at,
                "model_counts": _json_text(model_counts),
            })
            conn.execute(text("""
                INSERT INTO ct_published_snapshot
                    (company_id, run_id, published_at, previous_run_id, trigger, requested_by)
                VALUES (:company_id, CAST(:run_id AS UUID), :published_at,
                        CAST(:previous_run_id AS UUID), 'incremental', :requested_by)
                ON CONFLICT (company_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    published_at = EXCLUDED.published_at,
                    previous_run_id = EXCLUDED.previous_run_id,
                    trigger = EXCLUDED.trigger,
                    requested_by = EXCLUDED.requested_by
            """), {
                "company_id": company_id, "run_id": run_id,
                "published_at": completed_at, "previous_run_id": previous_run_id,
                "requested_by": row["requested_by"] or "incremental",
            })

            for sql_path in self._sql_paths:
                if not sql_path.exists():
                    raise FileNotFoundError(f"SQL file not found: {sql_path}")
                conn.exec_driver_sql(sql_path.read_text(encoding="utf-8"))

            self._advance_watermarks_in_transaction(conn, run_id, company_id, completed_at)

    def _advance_watermarks_in_transaction(self, conn, run_id: str, company_id: int, now: datetime) -> None:
        models = self._run_models(run_id)
        for model in models:
            evidence = conn.execute(text("""
                SELECT MAX(fetched_write_date) AS max_write_date,
                       MAX(record_id) FILTER (
                           WHERE fetched_write_date = (
                               SELECT MAX(fetched_write_date) FROM ct_fetch_apply_evidence
                               WHERE run_id = CAST(:run_id AS UUID) AND model = :model
                           )
                       ) AS max_id
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID) AND model = :model
            """), {"run_id": run_id, "model": model}).mappings().first()
            if evidence is None or evidence["max_write_date"] is None:
                continue
            write_date = watermark_displayed_second(evidence["max_write_date"])
            record_id = int(evidence["max_id"])
            self._watermarks.advance_after_publication(
                company_id=company_id, model=model, run_id=run_id,
                write_date=write_date, record_id=record_id, now=now, connection=conn,
            )

    def _candidate_model_counts(self, conn, run_id: str) -> dict[str, int]:
        rows = conn.execute(text("""
            SELECT model, COUNT(*) AS total
            FROM ct_native_record_snapshot
            WHERE extraction_run_id = CAST(:run_id AS UUID)
            GROUP BY model
        """), {"run_id": run_id}).mappings().all()
        return {str(row["model"]): int(row["total"]) for row in rows}

    # -- candidate validation ---------------------------------------------------

    def _validate_candidate(self, run: dict[str, Any], company_id: int, *, no_changes: bool) -> None:
        progress = parse_progress_json(run["progress"])
        if not progress.get("copy_forward_status") == "COMPLETE":
            raise RefreshContinuationError(
                "Candidate copy-forward is not durably complete.",
                requires_new_retry=True,
            )
        if not progress.get("change_detection_complete"):
            raise RefreshContinuationError(
                "Candidate change detection is not durably complete.",
                requires_new_retry=True,
            )
        if no_changes:
            if int(progress.get("detection_manifest_row_count", 0)) != 0:
                raise RefreshContinuationError(
                    "Candidate no-change evidence contradicts the manifest row count.",
                    requires_new_retry=True,
                )
            self._validate_pointer_unchanged(run, company_id)
            return
        if not progress.get("fetch_apply_complete"):
            raise RefreshContinuationError(
                "Candidate fetch/apply is not durably complete.",
                requires_new_retry=True,
            )
        if not progress.get("reconciliation_complete"):
            raise RefreshContinuationError(
                "Candidate reconciliation is not durably complete.",
                requires_new_retry=True,
            )
        self._validate_pointer_unchanged(run, company_id)
        self._validate_no_cross_company(run, company_id)

    def _validate_pointer_unchanged(self, run: dict[str, Any], company_id: int) -> None:
        with self.pg.engine.connect() as conn:
            pointer = conn.execute(text("""
                SELECT run_id::text FROM ct_published_snapshot WHERE company_id = :company_id
            """), {"company_id": company_id}).scalar()
        if not run["base_snapshot_run_id"] or str(run["base_snapshot_run_id"]) != str(pointer):
            raise RefreshContinuationError(
                "Candidate base snapshot is stale or the published pointer changed.",
                requires_new_retry=True,
            )

    def _validate_no_cross_company(self, run: dict[str, Any], company_id: int) -> None:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT 1
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                  AND company_id IS NOT NULL
                  AND company_id <> :company_id
                LIMIT 1
            """), {"run_id": run["run_id"], "company_id": company_id}).scalar()
        if row:
            raise RefreshContinuationError(
                "Candidate contains rows from another company; publication is blocked."
            )

    # -- helpers ---------------------------------------------------------------

    def _read_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT run_id::text, company_id, status, stage,
                       base_snapshot_run_id::text, selected_domains, progress,
                       published_at, completed_at, finished_at, duration_seconds,
                       started_at, model_counts, error_message
                FROM ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_id}).mappings().first()
        return dict(row) if row else None

    def _write_progress(self, run_id: str, progress: dict[str, Any]) -> None:
        with self.pg.engine.begin() as conn:
            updated = conn.execute(text("""
                UPDATE ct_extraction_run
                SET progress = CAST(:progress AS JSONB), heartbeat_at = :now
                WHERE run_id = CAST(:run_id AS UUID)
            """), {
                "run_id": run_id,
                "progress": serialize_progress(progress),
                "now": datetime.now(timezone.utc),
            })
            if updated.rowcount != 1:
                raise RefreshContinuationError("Refresh run progress could not be persisted.")

    def _mark_failed(self, run_id: str, error: Any) -> None:
        try:
            self._state.transition(
                run_id, "FAILED_TRANSIENT",
                failure_class="TRANSIENT",
                error_message=sanitize_diagnostic(error),
            )
        except ValueError:
            try:
                self._state.transition(
                    run_id, "FAILED_PERMANENT",
                    failure_class="PERMANENT",
                    error_message=sanitize_diagnostic(error),
                )
            except ValueError:
                pass

    def _terminal_result(self, run: dict[str, Any]) -> dict[str, Any]:
        progress = parse_progress_json(run["progress"])
        status = run["status"] if run["status"] != "COMPLETED" else "SUCCEEDED"
        return {
            "run_id": str(run["run_id"]),
            "company_id": int(run["company_id"]),
            "current_state": status,
            "status": status,
            "no_changes": status == "SUCCEEDED_NO_CHANGES",
            "published_at": run["published_at"],
            "completed_at": run["completed_at"] or run["finished_at"],
            "finished_at": run["finished_at"],
            "duration_seconds": run["duration_seconds"],
            "base_snapshot_run_id": run["base_snapshot_run_id"],
            "trusted_run_id": str(run["run_id"]),
            "manifest_rows": int(progress.get("detection_manifest_row_count", 0)),
            "records_fetched": int(progress.get("fetch_apply_records_fetched", 0)),
            "inserted": int(progress.get("fetch_apply_inserted", 0)),
            "updated": int(progress.get("fetch_apply_updated", 0)),
            "unchanged": int(progress.get("fetch_apply_unchanged", 0)),
            "models_completed": list(progress.get("detection_models_completed", [])),
        }


def _json_text(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
