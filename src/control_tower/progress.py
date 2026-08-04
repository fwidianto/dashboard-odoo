"""Truthful, nullable progress payload validation and deterministic persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any, Mapping

COUNT_FIELDS = ("domains_planned", "domains_completed", "models_planned", "models_completed", "records_detected", "records_fetched", "inserted", "updated", "unchanged", "removed", "parents_reconciled", "views_refreshed", "checks_recalculated", "findings_opened", "findings_resolved")
LIST_FIELDS = ("domains", "completed_domains", "models", "completed_models")
TEXT_FIELDS = ("current_domain", "current_model", "stage_message")
COPY_FORWARD_COUNT_FIELDS = ("copy_forward_total_rows",)
COPY_FORWARD_NUMBER_FIELDS = ("copy_forward_elapsed_seconds",)
COPY_FORWARD_LIST_FIELDS = ("copy_forward_tables_planned", "copy_forward_tables_completed")
COPY_FORWARD_TEXT_FIELDS = (
    "copy_forward_status",
    "copy_forward_source_run_id",
    "copy_forward_candidate_run_id",
    "copy_forward_current_table",
    "copy_forward_started_at",
    "copy_forward_finished_at",
)
COPY_FORWARD_MAP_FIELDS = ("copy_forward_rows",)
COPY_FORWARD_TIMESTAMP_MAP_FIELDS = ("copy_forward_table_completed_at",)
COPY_FORWARD_STATUS_VALUES = frozenset({"COPYING_BASE_SNAPSHOT", "COMPLETE"})
KNOWN_FIELDS = frozenset(
    (
        *COUNT_FIELDS,
        *LIST_FIELDS,
        *TEXT_FIELDS,
        *COPY_FORWARD_COUNT_FIELDS,
        *COPY_FORWARD_NUMBER_FIELDS,
        *COPY_FORWARD_LIST_FIELDS,
        *COPY_FORWARD_TEXT_FIELDS,
        *COPY_FORWARD_MAP_FIELDS,
        *COPY_FORWARD_TIMESTAMP_MAP_FIELDS,
    )
)


class ProgressContractError(ValueError):
    """Raised when a progress payload cannot be trusted."""


def _normalize_copy_forward_timestamp(value: str, field: str) -> str:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Progress timestamp must be ISO-8601: {field}") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"Progress timestamp must be timezone-aware: {field}")
    return timestamp.astimezone(timezone.utc).isoformat()


def validate_progress_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("Refresh progress must be a JSON object.")
    unknown = set(payload) - KNOWN_FIELDS
    if unknown:
        raise ValueError(f"Unknown refresh progress fields: {sorted(unknown)}")
    result: dict[str, Any] = {}
    for field in COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in COPY_FORWARD_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in COPY_FORWARD_NUMBER_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            or not math.isfinite(value)
        ):
            raise ValueError(f"Progress duration must be a non-negative number: {field}")
        result[field] = value
    for field in LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Progress list must contain strings: {field}")
        result[field] = sorted(set(value))
    for field in COPY_FORWARD_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Progress list must contain strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Progress list must contain unique strings: {field}")
        result[field] = sorted(value)
    for completed, planned in (("completed_domains", "domains"), ("completed_models", "models")):
        if completed not in result:
            continue
        if planned not in result:
            if result[completed]:
                raise ValueError(f"Completed progress requires planned progress: {completed}")
            continue
        if not set(result[completed]).issubset(result[planned]):
            raise ValueError(f"Completed progress must be a subset of planned progress: {completed}")
    for completed, planned in (("domains_completed", "domains_planned"), ("models_completed", "models_planned")):
        if completed not in result:
            continue
        if planned not in result:
            if result[completed] > 0:
                raise ValueError(f"Completed progress requires planned progress: {completed}")
            continue
        if result[completed] > result[planned]:
            raise ValueError(f"Completed progress cannot exceed planned progress: {completed}")
    for field in TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Progress text field must be a string: {field}")
        result[field] = payload[field]
    for field in COPY_FORWARD_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Progress text field must be a string: {field}")
        if field == "copy_forward_status" and payload[field] not in COPY_FORWARD_STATUS_VALUES:
            raise ValueError(f"Unsupported copy-forward progress status: {payload[field]}")
        if field in {"copy_forward_started_at", "copy_forward_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in COPY_FORWARD_MAP_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, Mapping):
            raise ValueError(f"Progress row map must be an object: {field}")
        normalized: dict[str, int] = {}
        for key, row_count in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Progress row map keys must be strings: {field}")
            if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
                raise ValueError(f"Progress row map values must be non-negative integers: {field}")
            normalized[key] = row_count
        result[field] = {key: normalized[key] for key in sorted(normalized)}
    for field in COPY_FORWARD_TIMESTAMP_MAP_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, Mapping):
            raise ValueError(f"Progress timestamp map must be an object: {field}")
        normalized_timestamps: dict[str, str] = {}
        for key, timestamp in value.items():
            if not isinstance(key, str) or not isinstance(timestamp, str):
                raise ValueError(
                    f"Progress timestamp map must contain string keys and values: {field}"
                )
            normalized_timestamps[key] = _normalize_copy_forward_timestamp(
                timestamp, field
            )
        result[field] = {
            key: normalized_timestamps[key] for key in sorted(normalized_timestamps)
        }
    if "copy_forward_rows" in result and "copy_forward_total_rows" in result:
        if result["copy_forward_total_rows"] != sum(result["copy_forward_rows"].values()):
            raise ValueError("Copy-forward total rows must equal per-table row totals.")

    if {
        "copy_forward_started_at",
        "copy_forward_finished_at",
        "copy_forward_elapsed_seconds",
    }.issubset(result):
        started = datetime.fromisoformat(
            result["copy_forward_started_at"].replace("Z", "+00:00")
        )
        finished = datetime.fromisoformat(
            result["copy_forward_finished_at"].replace("Z", "+00:00")
        )
        elapsed = (finished - started).total_seconds()
        if elapsed < 0:
            raise ValueError("Copy-forward finish timestamp must not precede its start.")
        if round(elapsed, 6) != result["copy_forward_elapsed_seconds"]:
            raise ValueError(
                "Copy-forward elapsed seconds must equal finished minus started."
            )

    if "copy_forward_tables_completed" in result:
        planned = result.get("copy_forward_tables_planned")
        if planned is None and result["copy_forward_tables_completed"]:
            raise ValueError("Completed copy-forward tables require planned tables.")
        if planned is not None and not set(result["copy_forward_tables_completed"]).issubset(planned):
            raise ValueError("Completed copy-forward tables must be a subset of planned tables.")
    return result


def parse_progress_json(value: Any) -> dict[str, Any]:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProgressContractError("Persisted refresh progress is malformed JSON.") from exc
    try:
        return validate_progress_payload(value)
    except (TypeError, ValueError) as exc:
        raise ProgressContractError(f"Persisted refresh progress is invalid: {exc}") from exc


def serialize_progress(payload: Mapping[str, Any] | None) -> str:
    return json.dumps(validate_progress_payload(payload), sort_keys=True, separators=(",", ":"))
