"""PostgreSQL set-based copy-forward for a candidate refresh snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
from typing import Any, Callable, Optional
from uuid import UUID

from sqlalchemy import text

from src.control_tower.progress import (
    ProgressContractError,
    parse_progress_json,
    serialize_progress,
)
from src.control_tower.refresh import REFRESH_LOCK_KEY, RefreshLifecycleError, sanitize_diagnostic
from src.control_tower.refresh_state import validate_transition
from src.control_tower.schema_guard import ensure_phase8_schema_ready


SNAPSHOT_TABLE_COLUMNS = (
    (
        "ct_native_record_snapshot",
        (
            "model",
            "record_id",
            "document_number",
            "state",
            "company_id",
            "company_name",
            "write_date",
            "payload",
            "extracted_at",
        ),
    ),
    (
        "ct_document_link",
        (
            "link_type",
            "parent_model",
            "parent_id",
            "parent_number",
            "child_model",
            "child_id",
            "child_number",
            "source_field",
            "confidence",
            "evidence",
            "extracted_at",
        ),
    ),
)


def _copy_insert_sql(table_name: str, columns: tuple[str, ...]) -> str:
    column_list = ", ".join(columns)
    return f"""
        INSERT INTO public.{table_name} (extraction_run_id, {column_list})
        SELECT CAST(:candidate_run_id AS UUID), {column_list}
        FROM public.{table_name}
        WHERE extraction_run_id = CAST(:source_run_id AS UUID)
        """


SNAPSHOT_TABLES = tuple(
    (table_name, _copy_insert_sql(table_name, columns))
    for table_name, columns in SNAPSHOT_TABLE_COLUMNS
)

SNAPSHOT_TABLE_NAMES = tuple(table_name for table_name, _ in SNAPSHOT_TABLES)
_COMPLETE_PROGRESS_STATUS = "COMPLETE"
_COPYING_PROGRESS_STATUS = "COPYING_BASE_SNAPSHOT"


def _projection(table_name: str) -> str:
    columns = dict(SNAPSHOT_TABLE_COLUMNS)[table_name]
    return ", ".join(columns)


def _validate_run_id(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise CopyForwardValidationError(f"{label} must be a UUID.")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise CopyForwardValidationError(f"{label} must be a UUID.") from exc


def _capture_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_seconds(started_at: datetime, finished_at: datetime) -> float:
    for timestamp in (started_at, finished_at):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Copy-forward timestamps must be timezone-aware.")
    elapsed = (
        finished_at.astimezone(timezone.utc)
        - started_at.astimezone(timezone.utc)
    ).total_seconds()
    return round(max(0.0, elapsed), 6)


def _jsonb_text(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        sort_keys=True,
        separators=(",", ":"),
    )


class CopyForwardError(RefreshLifecycleError):
    """Base error for a candidate that cannot safely copy forward."""


class CopyForwardValidationError(CopyForwardError):
    """Raised when the candidate or trusted source is not usable."""


class CopyForwardStaleError(CopyForwardError):
    """Raised when the candidate no longer targets the trusted snapshot."""


class CopyForwardPartialError(CopyForwardError):
    """Raised when candidate rows or metadata indicate an incomplete copy."""


def _utc(value: Optional[datetime]) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Copy-forward timestamps must be timezone-aware.")
    return timestamp.astimezone(timezone.utc)


class CandidateSnapshotCopyForwardService:
    """Copy the trusted raw snapshot into one candidate in one PostgreSQL transaction."""

    def __init__(
        self,
        postgres_client,
        *,
        schema_guard=ensure_phase8_schema_ready,
        copy_hook: Optional[Callable[[str, Any], None]] = None,
    ) -> None:
        self.pg = postgres_client
        self.copy_hook = copy_hook
        schema_guard(postgres_client)

    def copy_forward(
        self,
        candidate_run_id: str,
        *,
        company_id: int,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        candidate_id = _validate_run_id(candidate_run_id, "Candidate run ID")
        if isinstance(company_id, bool) or not isinstance(company_id, int):
            raise CopyForwardValidationError("Company ID must be an integer.")
        timestamp = _utc(now)
        failure_candidate_id: Optional[str] = None
        failure_boundary: Optional[dict[str, Any]] = None

        try:
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(CAST(:lock_key AS BIGINT))"
                    ),
                    {"lock_key": REFRESH_LOCK_KEY},
                )
                candidate = conn.execute(
                    text(
                        """
                        SELECT run_id::text AS run_id, status, stage, company_id,
                               base_snapshot_run_id::text AS base_snapshot_run_id,
                               progress, stage_timings, published_at,
                               completed_at, finished_at, duration_seconds
                        FROM public.ct_extraction_run
                        WHERE run_id = CAST(:run_id AS UUID)
                        FOR UPDATE
                        """
                    ),
                    {"run_id": candidate_id},
                ).mappings().first()
                if not candidate:
                    raise CopyForwardValidationError("Candidate refresh run was not found.")
                failure_candidate_id = candidate_id
                failure_boundary = {
                    "status": candidate["status"],
                    "stage": candidate["stage"],
                    "base_snapshot_run_id": candidate["base_snapshot_run_id"],
                    "progress": _jsonb_text(candidate["progress"]),
                    "stage_timings": _jsonb_text(candidate["stage_timings"]),
                    "published_at": candidate["published_at"],
                    "completed_at": candidate["completed_at"],
                    "finished_at": candidate["finished_at"],
                    "duration_seconds": candidate["duration_seconds"],
                }
                if candidate["company_id"] != company_id:
                    raise CopyForwardValidationError(
                        "Candidate refresh run belongs to a different company."
                    )

                status = candidate["status"]
                stage = candidate["stage"]
                if status not in {"PREPARING", "DETECTING_CHANGES"}:
                    raise CopyForwardValidationError(
                        f"Candidate refresh run has unsupported state: {status!r}."
                    )
                if stage != status:
                    raise CopyForwardValidationError(
                        f"Candidate refresh run stage is {stage!r}, not {status!r}."
                    )

                pointer = conn.execute(
                    text(
                        """
                        SELECT company_id, run_id::text AS run_id, published_at
                        FROM public.ct_published_snapshot
                        WHERE company_id = :company_id
                        FOR UPDATE
                        """
                    ),
                    {"company_id": company_id},
                ).mappings().first()
                if not pointer:
                    raise CopyForwardValidationError(
                        "No trusted published snapshot exists for the candidate company."
                    )

                if pointer["published_at"] is None:
                    raise CopyForwardValidationError(
                        "The trusted published pointer is missing publication metadata."
                    )
                source_id = _validate_run_id(pointer["run_id"], "Source run ID")
                if source_id == candidate_id:
                    raise CopyForwardValidationError(
                        "Candidate run cannot copy forward from itself."
                    )
                source = conn.execute(
                    text(
                        """
                        SELECT run_id::text AS run_id, company_id, status,
                               completed_at, published_at
                        FROM public.ct_extraction_run
                        WHERE run_id = CAST(:run_id AS UUID)
                        FOR SHARE
                        """
                    ),
                    {"run_id": source_id},
                ).mappings().first()
                if not source:
                    raise CopyForwardValidationError(
                        "The published snapshot points to a missing extraction run."
                    )
                if source["company_id"] != company_id:
                    raise CopyForwardValidationError(
                        "The trusted published snapshot belongs to a different company."
                    )
                if source["status"] not in {"COMPLETED", "SUCCEEDED"}:
                    raise CopyForwardValidationError(
                        "The trusted published snapshot is not a completed run."
                    )
                if source["completed_at"] is None:
                    raise CopyForwardValidationError(
                        "The trusted published snapshot is missing completion metadata."
                    )
                if source["published_at"] is None:
                    raise CopyForwardValidationError(
                        "The trusted published source is missing publication metadata."
                    )
                if source_id != _validate_run_id(source["run_id"], "Source run ID"):
                    raise CopyForwardStaleError(
                        "The trusted published pointer changed during validation."
                    )

                base_snapshot = (
                    _validate_run_id(
                        candidate["base_snapshot_run_id"], "Candidate base snapshot run ID"
                    )
                    if candidate["base_snapshot_run_id"] is not None
                    else None
                )
                if base_snapshot is not None and base_snapshot != source_id:
                    raise CopyForwardStaleError(
                        "Candidate base snapshot is stale; the trusted published snapshot changed."
                    )

                progress = self._load_progress(candidate["progress"])
                stage_timings = self._stage_timings(candidate["stage_timings"])
                self._lock_source_rows(conn, source_id)
                source_counts = self._source_counts(conn, source_id, int(company_id))
                candidate_counts = self._candidate_counts(conn, candidate_id)
                complete = self._is_complete_progress(
                    progress,
                    candidate_id=candidate_id,
                    source_id=source_id,
                    stage_timings=stage_timings,
                )

                if status == "DETECTING_CHANGES":
                    if any(
                        candidate[field] is not None
                        for field in ("published_at", "completed_at", "finished_at", "duration_seconds")
                    ):
                        raise CopyForwardPartialError(
                            "Candidate has advanced beyond copy-forward detection."
                        )
                    if base_snapshot is None or not complete:
                        raise CopyForwardPartialError(
                            "Candidate is in change detection with incomplete copy-forward data."
                        )
                    self._verify_copy_integrity(
                        conn,
                        source_id=source_id,
                        candidate_id=candidate_id,
                        source_counts=source_counts,
                    )
                    return self._result(
                        candidate_id,
                        source_id,
                        self._candidate_counts(conn, candidate_id),
                        idempotent=True,
                    )

                if complete or self._has_copy_metadata(progress, stage_timings):
                    raise CopyForwardPartialError(
                        "Candidate contains partial or inconsistent copy-forward state."
                    )
                if any(candidate_counts.values()):
                    raise CopyForwardPartialError(
                        "Candidate contains partial or inconsistent copy-forward rows."
                    )

                if source_counts["ct_native_record_snapshot"] and conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM public.ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                          AND company_id IS NOT NULL
                          AND company_id <> :company_id
                        LIMIT 1
                        """
                    ),
                    {"run_id": source_id, "company_id": company_id},
                ).scalar():
                    raise CopyForwardValidationError(
                        "Trusted snapshot contains rows from another company."
                    )

                self._claim_base_snapshot(
                    conn,
                    candidate_id=candidate_id,
                    source_id=source_id,
                )
                started_at = timestamp
                progress = dict(progress)
                progress.update(
                    {
                        "copy_forward_status": _COPYING_PROGRESS_STATUS,
                        "copy_forward_source_run_id": source_id,
                        "copy_forward_candidate_run_id": candidate_id,
                        "copy_forward_tables_planned": sorted(SNAPSHOT_TABLE_NAMES),
                        "copy_forward_tables_completed": [],
                        "copy_forward_rows": {},
                        "copy_forward_total_rows": 0,
                        "copy_forward_current_table": SNAPSHOT_TABLE_NAMES[0],
                        "copy_forward_started_at": started_at.isoformat(),
                        "copy_forward_table_completed_at": {},
                        "copy_forward_elapsed_seconds": 0.0,
                    }
                )
                self._update_progress(
                    conn,
                    candidate_id=candidate_id,
                    source_id=source_id,
                    progress=progress,
                    now=_capture_timestamp(),
                )

                copied_rows: dict[str, int] = {}
                completed_tables: list[str] = []
                completed_at_by_table: dict[str, str] = {}
                for table_name, insert_sql in SNAPSHOT_TABLES:
                    conn.execute(
                        text(insert_sql),
                        {
                            "source_run_id": source_id,
                            "candidate_run_id": candidate_id,
                        },
                    )
                    if self.copy_hook is not None:
                        self.copy_hook(table_name, conn)
                    self._assert_exact_table_equality(
                        conn,
                        table_name=table_name,
                        source_id=source_id,
                        candidate_id=candidate_id,
                    )
                    copied_rows[table_name] = self._candidate_counts(
                        conn, candidate_id
                    )[table_name]
                    completed_tables.append(table_name)
                    completed_at = _capture_timestamp()
                    completed_at_by_table[table_name] = completed_at.isoformat()
                    progress.update(
                        {
                            "copy_forward_tables_completed": completed_tables,
                            "copy_forward_rows": copied_rows,
                            "copy_forward_total_rows": sum(copied_rows.values()),
                            "copy_forward_current_table": table_name,
                            "copy_forward_table_completed_at": completed_at_by_table,
                            "copy_forward_elapsed_seconds": _elapsed_seconds(
                                started_at, completed_at
                            ),
                        }
                    )
                    self._update_progress(
                        conn,
                        candidate_id=candidate_id,
                        source_id=source_id,
                        progress=progress,
                        now=completed_at,
                    )

                self._verify_copy_integrity(
                    conn,
                    source_id=source_id,
                    candidate_id=candidate_id,
                    source_counts=source_counts,
                )
                finished_at = _capture_timestamp()
                progress.update(
                    {
                        "copy_forward_status": _COMPLETE_PROGRESS_STATUS,
                        "copy_forward_tables_completed": sorted(completed_tables),
                        "copy_forward_rows": copied_rows,
                        "copy_forward_total_rows": sum(copied_rows.values()),
                        "copy_forward_current_table": completed_tables[-1],
                        "copy_forward_finished_at": finished_at.isoformat(),
                        "copy_forward_table_completed_at": completed_at_by_table,
                        "copy_forward_elapsed_seconds": _elapsed_seconds(
                            started_at, finished_at
                        ),
                    }
                )
                stage_timings.update(
                    {
                        "copy_forward_seconds": progress["copy_forward_elapsed_seconds"],
                        "copy_forward_rows": copied_rows,
                        "copy_forward_source_run_id": source_id,
                        "copy_forward_started_at": progress["copy_forward_started_at"],
                        "copy_forward_finished_at": progress["copy_forward_finished_at"],
                        "copy_forward_table_completed_at": completed_at_by_table,
                    }
                )
                self._transition_to_detection(
                    conn,
                    candidate_id=candidate_id,
                    source_id=source_id,
                    progress=progress,
                    stage_timings=stage_timings,
                    now=finished_at,
                )
                return self._result(
                    candidate_id,
                    source_id,
                    copied_rows,
                    idempotent=False,
                )
        except Exception as exc:
            if failure_candidate_id is not None:
                try:
                    self._record_failure(
                        failure_candidate_id,
                        exc,
                        _capture_timestamp(),
                        expected_state=failure_boundary,
                    )
                except Exception as failure_recording_error:
                    logging.getLogger().error(
                        "Could not record copy-forward failure for candidate %s: %s; "
                        "the original exception is preserved.",
                        failure_candidate_id,
                        failure_recording_error,
                        exc_info=True,
                    )
            raise

    @staticmethod
    def _load_progress(value: Any) -> dict[str, Any]:
        try:
            return parse_progress_json(value)
        except ProgressContractError as exc:
            raise CopyForwardPartialError(
                f"Candidate progress is malformed or invalid: {exc}"
            ) from exc

    @staticmethod
    def _stage_timings(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise CopyForwardPartialError("Candidate stage timings are malformed.")
        return dict(value)

    @staticmethod
    def _has_copy_metadata(
        progress: dict[str, Any],
        stage_timings: dict[str, Any],
    ) -> bool:
        return any(
            key.startswith("copy_forward_")
            for key in (*progress, *stage_timings)
        )

    @staticmethod
    def _lock_source_rows(conn, source_id: str) -> None:
        for table_name in SNAPSHOT_TABLE_NAMES:
            conn.execute(
                text(
                    f"""
                    SELECT extraction_run_id
                    FROM public.{table_name}
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    FOR SHARE
                    """
                ),
                {"run_id": source_id},
            ).all()

    @staticmethod
    def _assert_exact_table_equality(
        conn,
        *,
        table_name: str,
        source_id: str,
        candidate_id: str,
    ) -> None:
        difference_sql = text(
            f"""
            SELECT {_projection(table_name)}
            FROM public.{table_name}
            WHERE extraction_run_id = CAST(:left_run_id AS UUID)
            EXCEPT ALL
            SELECT {_projection(table_name)}
            FROM public.{table_name}
            WHERE extraction_run_id = CAST(:right_run_id AS UUID)
            LIMIT 1
            """
        )
        for direction, left_run_id, right_run_id in (
            ("source-only", source_id, candidate_id),
            ("candidate-only", candidate_id, source_id),
        ):
            if (
                conn.execute(
                    difference_sql,
                    {"left_run_id": left_run_id, "right_run_id": right_run_id},
                ).first()
                is not None
            ):
                raise CopyForwardPartialError(
                    f"Exact copy-forward equality failed for {table_name} ({direction})."
                )

    @classmethod
    def _verify_copy_integrity(
        cls,
        conn,
        *,
        source_id: str,
        candidate_id: str,
        source_counts: dict[str, int],
    ) -> dict[str, int]:
        for table_name in SNAPSHOT_TABLE_NAMES:
            cls._assert_exact_table_equality(
                conn,
                table_name=table_name,
                source_id=source_id,
                candidate_id=candidate_id,
            )
        candidate_counts = cls._candidate_counts(conn, candidate_id)
        if candidate_counts != source_counts:
            raise CopyForwardPartialError(
                "Copy-forward row counts disagree after exact equality verification."
            )
        if cls._source_counts(conn, source_id, 0) != source_counts:
            raise CopyForwardPartialError(
                "Trusted source changed during copy-forward."
            )
        return candidate_counts

    @staticmethod
    def _claim_base_snapshot(conn, *, candidate_id: str, source_id: str) -> None:
        base = conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET base_snapshot_run_id = COALESCE(
                        base_snapshot_run_id, CAST(:source_id AS UUID)
                    )
                WHERE run_id = CAST(:candidate_id AS UUID)
                  AND (
                      base_snapshot_run_id IS NULL
                      OR base_snapshot_run_id = CAST(:source_id AS UUID)
                  )
                RETURNING base_snapshot_run_id::text
                """
            ),
            {"candidate_id": candidate_id, "source_id": source_id},
        ).scalar()
        if base is None or _validate_run_id(str(base), "Candidate base snapshot run ID") != source_id:
            raise CopyForwardStaleError(
                "Candidate base snapshot could not be assigned immutably."
            )

    @staticmethod
    def _source_counts(conn, source_id: str, company_id: int) -> dict[str, int]:
        return {
            "ct_native_record_snapshot": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM public.ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                        """
                    ),
                    {"run_id": source_id},
                ).scalar_one()
            ),
            "ct_document_link": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM public.ct_document_link
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                        """
                    ),
                    {"run_id": source_id},
                ).scalar_one()
            ),
        }

    @staticmethod
    def _candidate_counts(conn, candidate_id: str) -> dict[str, int]:
        return {
            table_name: int(
                conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM public.{table_name}
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                        """
                    ),
                    {"run_id": candidate_id},
                ).scalar_one()
            )
            for table_name in SNAPSHOT_TABLE_NAMES
        }

    @staticmethod
    def _aware_timestamp(value: Any) -> Optional[datetime]:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _is_complete_progress(
        progress: dict[str, Any],
        *,
        candidate_id: str,
        source_id: str,
        stage_timings: dict[str, Any],
    ) -> bool:
        planned = progress.get("copy_forward_tables_planned")
        completed = progress.get("copy_forward_tables_completed")
        rows = progress.get("copy_forward_rows", {})
        completed_at = progress.get("copy_forward_table_completed_at")
        if (
            not isinstance(planned, list)
            or not isinstance(completed, list)
            or not isinstance(rows, dict)
            or not isinstance(completed_at, dict)
        ):
            return False
        started_text = progress.get("copy_forward_started_at")
        finished_text = progress.get("copy_forward_finished_at")
        started = CandidateSnapshotCopyForwardService._aware_timestamp(started_text)
        finished = CandidateSnapshotCopyForwardService._aware_timestamp(finished_text)
        elapsed = progress.get("copy_forward_elapsed_seconds")
        if (
            started is None
            or finished is None
            or finished < started
            or isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or elapsed < 0
            or not math.isfinite(elapsed)
        ):
            return False
        if _elapsed_seconds(started, finished) != elapsed:
            return False
        table_timestamps = {
            table_name: CandidateSnapshotCopyForwardService._aware_timestamp(
                completed_at.get(table_name)
            )
            for table_name in SNAPSHOT_TABLE_NAMES
        }
        if (
            set(completed_at) != set(SNAPSHOT_TABLE_NAMES)
            or any(value is None for value in table_timestamps.values())
            or any(
                value < started or value > finished
                for value in table_timestamps.values()
                if value is not None
            )
        ):
            return False
        if (
            progress.get("copy_forward_status") != _COMPLETE_PROGRESS_STATUS
            or progress.get("copy_forward_source_run_id") != source_id
            or progress.get("copy_forward_candidate_run_id") != candidate_id
            or progress.get("copy_forward_current_table") != SNAPSHOT_TABLE_NAMES[-1]
            or planned != sorted(SNAPSHOT_TABLE_NAMES)
            or completed != sorted(SNAPSHOT_TABLE_NAMES)
            or set(rows) != set(SNAPSHOT_TABLE_NAMES)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in rows.values()
            )
            or isinstance(progress.get("copy_forward_total_rows"), bool)
            or not isinstance(progress.get("copy_forward_total_rows"), int)
            or progress["copy_forward_total_rows"] != sum(rows.values())
            or not isinstance(stage_timings, dict)
        ):
            return False
        return (
            stage_timings.get("copy_forward_seconds") == elapsed
            and stage_timings.get("copy_forward_rows") == rows
            and stage_timings.get("copy_forward_source_run_id") == source_id
            and stage_timings.get("copy_forward_started_at") == started_text
            and stage_timings.get("copy_forward_finished_at") == finished_text
            and stage_timings.get("copy_forward_table_completed_at") == completed_at
        )

    @staticmethod
    def _update_progress(
        conn,
        *,
        candidate_id: str,
        source_id: str,
        progress: dict[str, Any],
        now: datetime,
    ) -> None:
        result = conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET progress = CAST(:progress AS JSONB),
                    heartbeat_at = :now
                WHERE run_id = CAST(:candidate_id AS UUID)
                """
            ),
            {
                "candidate_id": candidate_id,
                "source_id": source_id,
                "progress": serialize_progress(progress),
                "now": now,
            },
        )
        if result.rowcount != 1:
            raise CopyForwardValidationError("Candidate progress update was not persisted.")

    @staticmethod
    def _transition_to_detection(
        conn,
        *,
        candidate_id: str,
        source_id: str,
        progress: dict[str, Any],
        stage_timings: Any,
        now: datetime,
    ) -> None:
        validate_transition("PREPARING", "DETECTING_CHANGES")
        timings = CandidateSnapshotCopyForwardService._stage_timings(stage_timings)
        conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET status = 'DETECTING_CHANGES',
                    stage = 'DETECTING_CHANGES',
                    stage_started_at = :now,
                    heartbeat_at = :now,
                    failure_class = NULL,
                    progress = CAST(:progress AS JSONB),
                    stage_timings = CAST(:stage_timings AS JSONB)
                WHERE run_id = CAST(:candidate_id AS UUID)
                """
            ),
            {
                "candidate_id": candidate_id,
                "source_id": source_id,
                "progress": serialize_progress(progress),
                "stage_timings": json.dumps(timings, sort_keys=True, separators=(",", ":")),
                "now": now,
            },
        )

    def _record_failure(
        self,
        candidate_id: str,
        error: Exception,
        now: datetime,
        *,
        expected_state: Optional[dict[str, Any]],
    ) -> bool:
        target = "FAILED_PERMANENT" if isinstance(error, CopyForwardError) else "FAILED_TRANSIENT"
        failure_class = "PERMANENT" if target == "FAILED_PERMANENT" else "TRANSIENT"
        with self.pg.engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(CAST(:lock_key AS BIGINT))"),
                {"lock_key": REFRESH_LOCK_KEY},
            )
            row = conn.execute(
                text(
                    """
                    SELECT status, stage, base_snapshot_run_id::text AS base_snapshot_run_id,
                           progress, stage_timings, published_at, completed_at,
                           finished_at, duration_seconds, started_at
                    FROM public.ct_extraction_run
                    WHERE run_id = CAST(:run_id AS UUID)
                    FOR UPDATE
                    """
                ),
                {"run_id": candidate_id},
            ).mappings().first()
            if not row:
                raise CopyForwardValidationError(
                    "Candidate disappeared before failure state recording."
                )
            if row["status"] in {
                "SUCCEEDED",
                "SUCCEEDED_NO_CHANGES",
                "FAILED_TRANSIENT",
                "FAILED_PERMANENT",
                "INTERRUPTED",
                "ABORTED",
                "COMPLETED",
                "FAILED",
            }:
                logging.getLogger().warning(
                    "Skipped copy-forward failure persistence for candidate %s; "
                    "authoritative state is already %s.",
                    candidate_id,
                    row["status"],
                )
                return False
            if (
                not expected_state
                or expected_state.get("status") != "PREPARING"
                or expected_state.get("stage") != "PREPARING"
                or any(
                    expected_state.get(field) is not None
                    for field in (
                        "published_at",
                        "completed_at",
                        "finished_at",
                        "duration_seconds",
                    )
                )
                or row["status"] != expected_state.get("status")
                or row["stage"] != expected_state.get("stage")
                or row["base_snapshot_run_id"] != expected_state.get(
                    "base_snapshot_run_id"
                )
                or _jsonb_text(row["progress"]) != expected_state.get("progress")
                or _jsonb_text(row["stage_timings"])
                != expected_state.get("stage_timings")
                or any(
                    row[field] is not None
                    for field in (
                        "published_at",
                        "completed_at",
                        "finished_at",
                        "duration_seconds",
                    )
                )
            ):
                logging.getLogger().warning(
                    "Skipped copy-forward failure persistence for candidate %s; "
                    "the run advanced or changed before failure recording.",
                    candidate_id,
                )
                return False
            validate_transition(str(row["status"]), target, failure_class)
            result = conn.execute(
                text(
                    """
                    UPDATE public.ct_extraction_run
                    SET status = :status,
                        stage = :status,
                        failure_class = :failure_class,
                        error_message = :error_message,
                        last_error_at = :now,
                        heartbeat_at = :now,
                        completed_at = COALESCE(completed_at, :now),
                        finished_at = COALESCE(finished_at, :now),
                        duration_seconds = COALESCE(
                            duration_seconds,
                            EXTRACT(EPOCH FROM (:now - started_at))
                        )
                    WHERE run_id = CAST(:run_id AS UUID)
                      AND status = :expected_status
                      AND stage = :expected_stage
                      AND base_snapshot_run_id IS NOT DISTINCT FROM
                          CAST(:expected_base_snapshot_run_id AS UUID)
                      AND progress IS NOT DISTINCT FROM CAST(:expected_progress AS JSONB)
                      AND stage_timings IS NOT DISTINCT FROM
                          CAST(:expected_stage_timings AS JSONB)
                      AND published_at IS NULL
                      AND completed_at IS NULL
                      AND finished_at IS NULL
                      AND duration_seconds IS NULL
                    """
                ),
                {
                    "run_id": candidate_id,
                    "status": target,
                    "failure_class": failure_class,
                    "error_message": sanitize_diagnostic(error),
                    "now": now,
                    "expected_status": expected_state["status"],
                    "expected_stage": expected_state["stage"],
                    "expected_base_snapshot_run_id": expected_state[
                        "base_snapshot_run_id"
                    ],
                    "expected_progress": expected_state["progress"],
                    "expected_stage_timings": expected_state["stage_timings"],
                },
            )
            if result.rowcount != 1:
                logging.getLogger().warning(
                    "Skipped copy-forward failure persistence for candidate %s; "
                    "the run changed during conditional update.",
                    candidate_id,
                )
                return False
            return True

    @staticmethod
    def _result(
        candidate_id: str,
        source_id: str,
        counts: dict[str, int],
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "run_id": candidate_id,
            "status": "DETECTING_CHANGES",
            "source_run_id": source_id,
            "base_snapshot_run_id": source_id,
            "tables": dict(counts),
            "total_rows": sum(counts.values()),
            "idempotent": idempotent,
        }
