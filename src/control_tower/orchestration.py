"""Phase 8C-1 durable refresh orchestration through precision-safe detection.

The orchestrator connects the approved refresh-run state machine, trusted
snapshot copy-forward, and precision-safe incremental change detection into
one coherent backend command that can start or resume a refresh run through
detection completion.

It reuses the approved services and never duplicates their SQL, Odoo domains,
bucket cursors, parsing, fingerprints, parent hints, or watermark logic.

Boundary contract (Phase 8C-1):

- detected manifest with one or more rows -> DETECTING_CHANGES -> FETCHING
- zero-row manifest (no changes)         -> DETECTING_CHANGES -> VALIDATING
- runs already at FETCHING/VALIDATING    -> idempotent orchestration result
- partial or inconsistent detection      -> fail closed; require a new linked run

The orchestrator deliberately does not hold an outer advisory lock: the
approved copy-forward and detection services own the global refresh lock
inside their own transactions, which avoids nested-lock deadlock and
lock-order inversion.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping, Optional
from uuid import UUID

from sqlalchemy import text

from src.control_tower.change_detection import (
    DETECTION_BUCKET_PAGE_SIZE,
    IncrementalChangeDetectionService,
)
from src.control_tower.contracts import resolve_domain_selection
from src.control_tower.copy_forward import (
    CandidateSnapshotCopyForwardService,
    CopyForwardError,
    CopyForwardPartialError,
)
from src.control_tower.fetch_apply import FetchApplyError, FetchApplyService
from src.control_tower.progress import parse_progress_json
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.schema_guard import ensure_phase8_detection_schema_ready


_ORCHESTRATION_BOUNDARY_STATES = frozenset({"FETCHING", "VALIDATING", "RECONCILING"})
_DURABLE_NON_BOUNDARY_STATES = frozenset(
    {"REQUESTED", "PREPARING", "DETECTING_CHANGES", "RECONCILING", "REFRESHING_DERIVED_DATA", "PUBLISHING"}
)
_FAILED_OR_TERMINAL_STATES = frozenset(
    {
        "FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED",
        "SUCCEEDED", "SUCCEEDED_NO_CHANGES", "COMPLETED", "FAILED",
    }
)


class OrchestrationError(ValueError):
    """Raised when the refresh pipeline cannot safely proceed."""

    def __init__(self, message: str, *, requires_new_retry: bool = False) -> None:
        super().__init__(message)
        self.requires_new_retry = requires_new_retry


class _NoCallOdoo:
    """Client that raises if any Odoo attribute is touched."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"idempotent orchestration must not call Odoo: {name}")


def _utc(value: Optional[datetime]) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise OrchestrationError("Orchestration timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


class RefreshPipelineOrchestrator:
    """Start or resume one refresh run through detection completion."""

    def __init__(
        self,
        postgres_client,
        *,
        schema_guard=ensure_phase8_detection_schema_ready,
        hooks: Optional[Mapping[str, Callable[[str], None]]] = None,
    ) -> None:
        self.pg = postgres_client
        schema_guard(postgres_client)
        self._hooks = dict(hooks or {})
        self._state = RefreshRunStateService(postgres_client)
        self._copy_forward = CandidateSnapshotCopyForwardService(postgres_client)
        self._detection = IncrementalChangeDetectionService(
            postgres_client, schema_guard=schema_guard
        )
        self._fetch_apply = FetchApplyService(postgres_client, hooks=self._hooks)

    def _fire(self, name: str) -> None:
        hook = self._hooks.get(name)
        if hook is not None:
            hook(name)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        try:
            return str(UUID(str(run_id)))
        except (TypeError, ValueError) as exc:
            raise OrchestrationError("Refresh run ID must be a valid UUID.") from exc

    @staticmethod
    def _validate_company(company_id: int) -> None:
        if isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0:
            raise OrchestrationError("Company ID must be a positive integer.")

    @staticmethod
    def _validate_page_size(bucket_page_size: int) -> None:
        if isinstance(bucket_page_size, bool) or not isinstance(bucket_page_size, int) or bucket_page_size <= 0:
            raise OrchestrationError("Bucket page size must be a positive integer.")

    def orchestrate(
        self,
        *,
        run_id: str,
        company_id: int,
        selected_domains: list[str] | tuple[str, ...] | None,
        odoo_client,
        now: Optional[datetime] = None,
        bucket_page_size: int = DETECTION_BUCKET_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Start or resume one run through detection completion."""
        timestamp = _utc(now)
        run_uuid = self._validate_run_id(run_id)
        self._validate_company(company_id)
        self._validate_page_size(bucket_page_size)
        try:
            resolved = [domain.key for domain in resolve_domain_selection(selected_domains)]
        except ValueError as exc:
            raise OrchestrationError(f"Invalid selected domains: {exc}") from exc
        self._fire("before_prepare")
        run = self._read_run(run_uuid)
        self._validate_run_inputs(run, company_id, resolved)
        if run["status"] in _ORCHESTRATION_BOUNDARY_STATES:
            if run["status"] == "FETCHING":
                return self._ensure_fetch_apply(run, company_id, resolved, odoo_client, timestamp)
            return self._idempotent_boundary_result(run, resolved)
        if run["status"] in _FAILED_OR_TERMINAL_STATES:
            raise OrchestrationError(
                f"Refresh run is {run['status']} and cannot be orchestrated as a clean run.",
                requires_new_retry=True,
            )
        if run["status"] not in _DURABLE_NON_BOUNDARY_STATES:
            raise OrchestrationError(f"Refresh run is in an unsupported state: {run['status']}")
        progress = parse_progress_json(run["progress"])
        self._persist_start_header(run_uuid, resolved, timestamp)
        if run["status"] == "REQUESTED":
            try:
                self._state.transition(run_uuid, "PREPARING", now=timestamp)
            except ValueError as exc:
                raise OrchestrationError(f"Refresh run could not be prepared: {exc}") from exc
            run = self._read_run(run_uuid)
            progress = parse_progress_json(run["progress"])
        self._fire("before_copy_forward")
        run, progress = self._ensure_copy_forward(run, progress, company_id, timestamp)
        self._fire("after_copy_forward")
        self._fire("before_detection")
        run, progress, detection = self._ensure_detection(
            run, progress, company_id, resolved, odoo_client, bucket_page_size, timestamp
        )
        self._fire("after_detection")
        if run["status"] == "FETCHING":
            return self._ensure_fetch_apply(run, company_id, resolved, odoo_client, timestamp)
        boundary = self._finalize_boundary(run, progress, resolved, timestamp, detection)
        if boundary["current_state"] == "FETCHING":
            run = self._read_run(run_uuid)
            if run is None:
                raise OrchestrationError("Refresh run disappeared at the fetching boundary.")
            return self._ensure_fetch_apply(run, company_id, resolved, odoo_client, timestamp)
        return boundary

    def _read_run(self, run_uuid: str) -> Optional[dict[str, Any]]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT run_id::text, company_id, status, stage,
                           base_snapshot_run_id::text, selected_domains, progress
                    FROM ct_extraction_run
                    WHERE run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": run_uuid},
            ).mappings().first()
        return dict(row) if row else None

    def _validate_run_inputs(self, run: Optional[dict[str, Any]], company_id: int, resolved: list[str]) -> None:
        if run is None:
            raise OrchestrationError("Refresh run was not found.")
        if int(run["company_id"]) != company_id:
            raise OrchestrationError("Refresh run belongs to a different company.")
        stored = list(run["selected_domains"] or [])
        if stored != resolved:
            raise OrchestrationError(
                "Refresh run selected domains do not match the request; domain selection is immutable."
            )
        if run["status"] in _ORCHESTRATION_BOUNDARY_STATES or run["status"] == "DETECTING_CHANGES":
            self._validate_base_against_pointer(run, company_id)

    def _validate_base_against_pointer(self, run: dict[str, Any], company_id: int) -> None:
        with self.pg.engine.connect() as conn:
            pointer = conn.execute(
                text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id = :company_id"),
                {"company_id": company_id},
            ).scalar()
        if not run["base_snapshot_run_id"] or str(run["base_snapshot_run_id"]) != str(pointer):
            raise OrchestrationError(
                "Candidate base snapshot is stale or the published pointer changed."
            )

    def _persist_start_header(self, run_uuid: str, resolved: list[str], timestamp: datetime) -> None:
        with self.pg.engine.connect() as conn:
            existing = conn.execute(
                text("SELECT progress FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"),
                {"run_id": run_uuid},
            ).scalar()
        progress = parse_progress_json(existing)
        if progress.get("orchestration_started_at"):
            return
        header = {
            "orchestration_selected_domains": sorted(resolved),
            "orchestration_started_at": timestamp.isoformat(),
        }
        with self.pg.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ct_extraction_run
                    SET progress = progress || CAST(:header AS JSONB), heartbeat_at = :now
                    WHERE run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": run_uuid, "header": json.dumps(header, sort_keys=True), "now": timestamp},
            )

    def _ensure_copy_forward(
        self,
        run: dict[str, Any],
        progress: dict[str, Any],
        company_id: int,
        timestamp: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        status = run["status"]
        try:
            self._invoke_copy_forward(status, run, progress, company_id, timestamp)
        except OrchestrationError:
            raise
        except CopyForwardPartialError as exc:
            raise OrchestrationError(
                f"Copy-forward is partial or inconsistent; a linked retry is required: {exc}",
                requires_new_retry=True,
            ) from exc
        except CopyForwardError as exc:
            raise OrchestrationError(f"Copy-forward failed closed: {exc}") from exc
        except Exception as exc:
            raise OrchestrationError(f"Copy-forward failed durably: {exc}") from exc
        if status == "PREPARING":
            refreshed = self._read_run(run["run_id"])
            if refreshed is None:
                raise OrchestrationError("Refresh run disappeared during copy-forward.")
            return refreshed, parse_progress_json(refreshed["progress"])
        return run, progress

    def _invoke_copy_forward(
        self,
        status: str,
        run: dict[str, Any],
        progress: dict[str, Any],
        company_id: int,
        timestamp: datetime,
    ) -> None:
        if status == "PREPARING":
            self._copy_forward.copy_forward(run["run_id"], company_id=company_id, now=timestamp)
            return
        if status == "DETECTING_CHANGES" and not progress.get("change_detection_complete"):
            self._copy_forward.copy_forward(run["run_id"], company_id=company_id, now=timestamp)
            return
        if status == "DETECTING_CHANGES" and progress.get("change_detection_complete"):
            if progress.get("copy_forward_status") != "COMPLETE":
                raise OrchestrationError(
                    "Completed detection without durable copy-forward evidence.",
                    requires_new_retry=True,
                )
            return
        raise OrchestrationError(f"Unsupported run state for copy-forward: {status}")

    def _detection_header_status(self, run_uuid: str) -> Optional[str]:
        with self.pg.engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT status FROM ct_change_detection_run WHERE run_id = CAST(:run_id AS UUID)"
                ),
                {"run_id": run_uuid},
            ).scalar()

    def _ensure_detection(
        self,
        run: dict[str, Any],
        progress: dict[str, Any],
        company_id: int,
        resolved: list[str],
        odoo_client,
        bucket_page_size: int,
        timestamp: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if progress.get("change_detection_complete"):
            if self._detection_header_status(run["run_id"]) != "COMPLETE":
                raise OrchestrationError(
                    "Detection progress and manifest evidence are inconsistent.",
                    requires_new_retry=True,
                )
            client = _NoCallOdoo()
            idempotent = True
        else:
            client = odoo_client
            idempotent = False
        try:
            detection = self._detection.detect(
                run_id=run["run_id"],
                company_id=company_id,
                selected_domains=resolved,
                odoo_client=client,
                bucket_page_size=bucket_page_size,
                now=timestamp,
            )
        except OrchestrationError:
            raise
        except Exception as exc:
            raise OrchestrationError(
                f"Change detection failed durably; evidence is preserved and a linked retry is required: {exc}",
                requires_new_retry=True,
            ) from exc
        refreshed = self._read_run(run["run_id"])
        if refreshed is None:
            raise OrchestrationError("Refresh run disappeared during detection.")
        return refreshed, parse_progress_json(refreshed["progress"]), {
            "idempotent": idempotent,
            "manifest_rows": int(detection.get("manifest_rows", 0)),
        }

    def _ensure_fetch_apply(
        self,
        run: dict[str, Any],
        company_id: int,
        resolved: list[str],
        odoo_client,
        timestamp: datetime,
    ) -> dict[str, Any]:
        if run["status"] == "RECONCILING":
            progress = parse_progress_json(run["progress"])
            if not progress.get("fetch_apply_complete"):
                raise OrchestrationError(
                    "Refresh run is at RECONCILING without complete fetch/apply evidence.",
                    requires_new_retry=True,
                )
            summary = self._fetch_apply.run(
                run_id=run["run_id"], company_id=company_id,
                odoo_client=_NoCallOdoo(), now=timestamp,
            )
            return self._merge_fetch_summary(summary, resolved, run)
        try:
            summary = self._fetch_apply.run(
                run_id=run["run_id"], company_id=company_id,
                odoo_client=odoo_client, now=timestamp,
            )
        except FetchApplyError as exc:
            raise OrchestrationError(
                f"Fetch/apply failed closed: {exc}",
                requires_new_retry=bool(exc.requires_new_retry),
            ) from exc
        except Exception as exc:
            raise OrchestrationError(
                f"Fetch/apply failed durably; evidence is preserved and a linked retry is required: {exc}",
                requires_new_retry=True,
            ) from exc
        return self._merge_fetch_summary(summary, resolved, run)

    def _merge_fetch_summary(self, summary: dict[str, Any], resolved: list[str], run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": summary["run_id"],
            "company_id": int(summary["company_id"]),
            "selected_domains": sorted(resolved),
            "current_state": summary["current_state"],
            "last_completed_stage": summary["last_completed_stage"],
            "next_required_stage": summary["next_required_stage"],
            "copy_forward_status": "COMPLETE",
            "detection_status": "COMPLETE",
            "manifest_rows": int(summary.get("records_requested", 0)),
            "models_completed": list(summary.get("models_completed", [])),
            "no_changes": False,
            "records_fetched": int(summary.get("records_fetched", 0)),
            "records_missing_at_fetch": int(summary.get("records_missing_at_fetch", 0)),
            "source_drift": int(summary.get("source_drift", 0)),
            "inserted": int(summary.get("inserted", 0)),
            "updated": int(summary.get("updated", 0)),
            "unchanged": int(summary.get("unchanged", 0)),
            "applied_total": int(summary.get("applied_total", 0)),
            "idempotent": bool(summary.get("idempotent", False)),
            "requires_new_retry": False,
            "base_snapshot_run_id": str(run["base_snapshot_run_id"]) if run["base_snapshot_run_id"] else None,
            "candidate_run_id": summary["run_id"],
        }

    def _finalize_boundary(
        self,
        run: dict[str, Any],
        progress: dict[str, Any],
        resolved: list[str],
        timestamp: datetime,
        detection: dict[str, Any],
    ) -> dict[str, Any]:
        if run["status"] in _ORCHESTRATION_BOUNDARY_STATES:
            return self._idempotent_boundary_result(run, resolved)
        if run["status"] != "DETECTING_CHANGES":
            raise OrchestrationError(f"Unexpected orchestration state before boundary: {run['status']}")
        if not progress.get("change_detection_complete"):
            raise OrchestrationError(
                "Detection evidence is not complete at the boundary.",
                requires_new_retry=True,
            )
        manifest_rows = int(progress.get("detection_manifest_row_count", 0))
        target = "FETCHING" if manifest_rows > 0 else "VALIDATING"
        self._fire("before_finalize")
        merged = self._merge_boundary_progress(progress, resolved, target, manifest_rows, timestamp)
        try:
            self._state.transition(run["run_id"], target, progress=merged, now=timestamp)
        except ValueError as exc:
            raise OrchestrationError(
                f"Stale state transition rejected before {target}: {exc}",
                requires_new_retry=True,
            ) from exc
        self._fire("after_finalize")
        completed = self._read_run(run["run_id"])
        if completed is None:
            raise OrchestrationError("Refresh run disappeared during boundary transition.")
        return self._result(
            completed,
            resolved,
            next_required_stage=target,
            last_completed_stage="DETECTING_CHANGES",
            manifest_rows=manifest_rows,
            idempotent=bool(detection.get("idempotent", False)),
            no_changes=manifest_rows == 0,
        )

    def _merge_boundary_progress(
        self,
        progress: dict[str, Any],
        resolved: list[str],
        target: str,
        manifest_rows: int,
        timestamp: datetime,
    ) -> dict[str, Any]:
        merged = dict(progress)
        started = merged.get("orchestration_started_at") or timestamp.isoformat()
        merged.update(
            {
                "orchestration_selected_domains": sorted(resolved),
                "orchestration_started_at": started,
                "orchestration_current_stage": target,
                "orchestration_last_completed_stage": "DETECTING_CHANGES",
                "orchestration_next_required_stage": target,
                "orchestration_copy_forward_status": progress.get("copy_forward_status", "NOT_STARTED"),
                "orchestration_detection_status": "COMPLETE",
                "orchestration_manifest_rows": manifest_rows,
                "orchestration_models_planned": list(progress.get("detection_models_planned", [])),
                "orchestration_models_completed": list(progress.get("detection_models_completed", [])),
                "orchestration_no_changes": manifest_rows == 0,
                "orchestration_finished_at": timestamp.isoformat(),
                "orchestration_elapsed_seconds": round(
                    max(0.0, (timestamp - datetime.fromisoformat(started)).total_seconds()), 6
                ),
            }
        )
        return merged

    def _idempotent_boundary_result(self, run: dict[str, Any], resolved: list[str]) -> dict[str, Any]:
        progress = parse_progress_json(run["progress"])
        if not progress.get("change_detection_complete"):
            raise OrchestrationError(
                f"Run is at {run['status']} without complete detection evidence.",
                requires_new_retry=True,
            )
        if progress.get("copy_forward_status") != "COMPLETE":
            raise OrchestrationError(
                f"Run is at {run['status']} without complete copy-forward evidence.",
                requires_new_retry=True,
            )
        manifest_rows = int(progress.get("detection_manifest_row_count", 0))
        return self._result(
            run,
            resolved,
            next_required_stage=run["status"],
            last_completed_stage=progress.get("orchestration_last_completed_stage") or "DETECTING_CHANGES",
            manifest_rows=manifest_rows,
            idempotent=True,
            no_changes=manifest_rows == 0,
        )

    def _result(
        self,
        run: dict[str, Any],
        resolved: list[str],
        *,
        next_required_stage: str,
        last_completed_stage: Optional[str],
        manifest_rows: int,
        idempotent: bool,
        no_changes: bool,
    ) -> dict[str, Any]:
        progress = parse_progress_json(run["progress"])
        return {
            "run_id": str(run["run_id"]),
            "company_id": int(run["company_id"]),
            "selected_domains": sorted(resolved),
            "current_state": run["status"],
            "last_completed_stage": last_completed_stage,
            "next_required_stage": next_required_stage,
            "copy_forward_status": progress.get("copy_forward_status"),
            "detection_status": progress.get("orchestration_detection_status", "COMPLETE"),
            "manifest_rows": manifest_rows,
            "models_completed": list(progress.get("detection_models_completed", [])),
            "no_changes": bool(no_changes),
            "idempotent": bool(idempotent),
            "requires_new_retry": False,
            "base_snapshot_run_id": str(run["base_snapshot_run_id"]) if run["base_snapshot_run_id"] else None,
            "candidate_run_id": str(run["run_id"]),
        }
