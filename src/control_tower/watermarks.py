"""Control Tower watermark persistence with monotonic publication guards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import UUID

from sqlalchemy import text

from src.control_tower.refresh_state import require_no_change_run, require_published_run
from src.control_tower.schema_guard import ensure_phase8_schema_ready

VALID_WATERMARK_STATUSES = frozenset({"BOOTSTRAP_REQUIRED", "READY"})


def normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Watermark timestamps must be timezone-aware datetimes.")
    return value.astimezone(timezone.utc)


def validate_overlap(overlap_seconds: int) -> int:
    if isinstance(overlap_seconds, bool) or not isinstance(overlap_seconds, int) or overlap_seconds < 0:
        raise ValueError("Watermark overlap_seconds must be a non-negative integer.")
    return overlap_seconds


def validate_record_id(record_id: int) -> int:
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise ValueError("Watermark last_successful_id must be a positive integer.")
    return record_id


def validate_watermark_identity(company_id: int, model: str) -> tuple[int, str]:
    if isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0:
        raise ValueError("Watermark company_id must be a positive integer.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Watermark model identity must be a non-empty string.")
    return company_id, model


def _validate_run_id(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Watermark published_run_id must be a valid UUID.") from exc


def validate_watermark_row(row: Mapping[str, Any], *, company_id: int | None = None, model: str | None = None) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("Persisted watermark row must be an object.")
    row = dict(row)
    expected_company, expected_model = (validate_watermark_identity(company_id, model) if company_id is not None and model is not None else (None, None))
    required = {"company_id", "model", "last_successful_write_date", "last_successful_id", "overlap_seconds", "published_run_id", "status"}
    missing = required - row.keys()
    if missing:
        raise ValueError(f"Persisted watermark row is missing fields: {sorted(missing)}")
    if isinstance(row["company_id"], bool) or not isinstance(row["company_id"], int) or row["company_id"] <= 0:
        raise ValueError("Persisted watermark company_id is invalid.")
    if expected_company is not None and row["company_id"] != expected_company:
        raise ValueError("Persisted watermark company identity does not match the request.")
    if not isinstance(row["model"], str) or not row["model"].strip():
        raise ValueError("Persisted watermark model identity is invalid.")
    if expected_model is not None and row["model"] != expected_model:
        raise ValueError("Persisted watermark model identity does not match the request.")
    validate_overlap(row["overlap_seconds"])
    status = row["status"]
    if status not in VALID_WATERMARK_STATUSES:
        raise ValueError(f"Persisted watermark status is invalid: {status}")
    write_date = row["last_successful_write_date"]
    record_id = row["last_successful_id"]
    if (write_date is None) != (record_id is None):
        raise ValueError("Persisted watermark write_date and ID must be set together.")
    if write_date is not None:
        write_date = normalize_utc(write_date)
        validate_record_id(record_id)
    published_run_id = row["published_run_id"]
    if published_run_id is not None:
        published_run_id = _validate_run_id(published_run_id)
    if status == "BOOTSTRAP_REQUIRED" and (write_date is not None or published_run_id is not None):
        raise ValueError("Bootstrap watermark cannot contain a successful tuple.")
    if status == "READY" and (write_date is None or published_run_id is None):
        raise ValueError("Ready watermark must contain a complete successful tuple.")
    normalized = dict(row)
    normalized["last_successful_write_date"] = write_date
    normalized["last_successful_id"] = record_id
    normalized["published_run_id"] = published_run_id
    for field in ("checked_at", "created_at", "updated_at"):
        if field in normalized and normalized[field] is not None:
            normalized[field] = normalize_utc(normalized[field])
    return normalized


def compare_tuples(left: tuple[datetime, int], right: tuple[datetime, int]) -> int:
    return (left > right) - (left < right)


class ControlTowerWatermarkStore:
    def __init__(self, postgres_client, *, schema_guard=ensure_phase8_schema_ready) -> None:
        self.pg = postgres_client
        schema_guard(postgres_client)

    def get(self, company_id: int, model: str) -> Optional[dict[str, Any]]:
        validate_watermark_identity(company_id, model)
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("SELECT company_id, model, last_successful_write_date, last_successful_id, overlap_seconds, published_run_id, checked_at, status, created_at, updated_at FROM ct_control_tower_watermark WHERE company_id = :company_id AND model = :model"), {"company_id": company_id, "model": model}).mappings().first()
        return validate_watermark_row(dict(row), company_id=company_id, model=model) if row else None

    def _published_run(self, conn, company_id: int, run_id: str):
        run = conn.execute(text("SELECT status, published_at, base_snapshot_run_id FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) AND company_id = :company_id FOR UPDATE"), {"run_id": run_id, "company_id": company_id}).mappings().first()
        if not run:
            raise ValueError("Refresh run was not found for watermark operation.")
        require_published_run(run["status"], run["published_at"])
        pointer = conn.execute(text("SELECT run_id FROM ct_published_snapshot WHERE company_id = :company_id FOR UPDATE"), {"company_id": company_id}).scalar()
        if str(pointer) != str(run_id):
            raise ValueError("Watermark run is not the currently published snapshot.")
        return run, pointer

    def _no_change_run(self, conn, company_id: int, run_id: str):
        run = conn.execute(text("SELECT status, published_at, base_snapshot_run_id FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) AND company_id = :company_id FOR UPDATE"), {"run_id": run_id, "company_id": company_id}).mappings().first()
        if not run:
            raise ValueError("Refresh run was not found for no-change watermark operation.")
        require_no_change_run(run["status"], run["published_at"])
        pointer = conn.execute(text("SELECT run_id FROM ct_published_snapshot WHERE company_id = :company_id FOR UPDATE"), {"company_id": company_id}).scalar()
        if not run["base_snapshot_run_id"] or str(run["base_snapshot_run_id"]) != str(pointer):
            raise ValueError("No-change watermark requires the trusted base snapshot to remain current.")
        return run, pointer

    def advance_after_publication(self, *, company_id: int, model: str, run_id: str, write_date: datetime, record_id: int, overlap_seconds: int = 0, status: str = "READY", now: Optional[datetime] = None) -> None:
        validate_watermark_identity(company_id, model)
        write_date = normalize_utc(write_date)
        validate_record_id(record_id)
        overlap_seconds = validate_overlap(overlap_seconds)
        if status not in VALID_WATERMARK_STATUSES or status != "READY":
            raise ValueError("Published watermark advancement requires status READY.")
        checked_at = normalize_utc(now) if now else datetime.now(timezone.utc)
        with self.pg.engine.begin() as conn:
            self._published_run(conn, company_id, run_id)
            current = conn.execute(text("SELECT company_id, model, last_successful_write_date, last_successful_id, overlap_seconds, published_run_id, checked_at, status, created_at, updated_at FROM ct_control_tower_watermark WHERE company_id = :company_id AND model = :model FOR UPDATE"), {"company_id": company_id, "model": model}).mappings().first()
            if current:
                current = validate_watermark_row(dict(current), company_id=company_id, model=model)
            if current and current["last_successful_write_date"] is not None:
                old = (current["last_successful_write_date"], current["last_successful_id"])
                comparison = compare_tuples((write_date, record_id), old)
                if comparison < 0:
                    raise ValueError("Watermark advancement would move backward.")
            conn.execute(text("""
                INSERT INTO ct_control_tower_watermark
                    (company_id, model, last_successful_write_date, last_successful_id, overlap_seconds, published_run_id, checked_at, status, created_at, updated_at)
                VALUES (:company_id, :model, :write_date, :record_id, :overlap_seconds, CAST(:run_id AS UUID), :checked_at, :status, :checked_at, :checked_at)
                ON CONFLICT (company_id, model) DO UPDATE SET
                    last_successful_write_date = EXCLUDED.last_successful_write_date,
                    last_successful_id = EXCLUDED.last_successful_id,
                    overlap_seconds = EXCLUDED.overlap_seconds,
                    published_run_id = EXCLUDED.published_run_id,
                    checked_at = EXCLUDED.checked_at, status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
                WHERE (ct_control_tower_watermark.last_successful_write_date IS NULL
                    OR (EXCLUDED.last_successful_write_date, EXCLUDED.last_successful_id)
                       >= (ct_control_tower_watermark.last_successful_write_date, ct_control_tower_watermark.last_successful_id))
            """), {"company_id": company_id, "model": model, "write_date": write_date, "record_id": record_id, "overlap_seconds": overlap_seconds, "run_id": run_id, "checked_at": checked_at, "status": status})

    def record_no_change_checked_at(self, *, company_id: int, model: str, run_id: str, now: Optional[datetime] = None) -> None:
        validate_watermark_identity(company_id, model)
        checked_at = normalize_utc(now) if now else datetime.now(timezone.utc)
        with self.pg.engine.begin() as conn:
            self._no_change_run(conn, company_id, run_id)
            row = conn.execute(text("SELECT company_id, model, last_successful_write_date, last_successful_id, overlap_seconds, published_run_id, checked_at, status, created_at, updated_at FROM ct_control_tower_watermark WHERE company_id = :company_id AND model = :model FOR UPDATE"), {"company_id": company_id, "model": model}).mappings().first()
            if not row:
                raise ValueError("No watermark exists for the no-change check.")
            validate_watermark_row(dict(row), company_id=company_id, model=model)
            result = conn.execute(text("UPDATE ct_control_tower_watermark SET checked_at = :checked_at, updated_at = :checked_at WHERE company_id = :company_id AND model = :model"), {"company_id": company_id, "model": model, "checked_at": checked_at})
            if result.rowcount != 1:
                raise ValueError("No watermark exists for the no-change check.")

    def record_no_change(self, *, company_id: int, model: str, run_id: str, now: Optional[datetime] = None) -> None:
        self.record_no_change_checked_at(company_id=company_id, model=model, run_id=run_id, now=now)
