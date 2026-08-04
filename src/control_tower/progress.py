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
DETECTION_COUNT_FIELDS = (
    "detection_records_scanned", "detection_overlap_rows_rechecked",
    "detection_newer_rows_detected", "detection_duplicate_rows_removed",
    "detection_manifest_rows_persisted", "detection_manifest_row_count",
    "detection_parent_hints_identified",
    "detection_bucket_page_size",
    "detection_configured_overlap_rows",
    "detection_watermark_second_replay_rows",
    "detection_genuinely_newer_rows",
)
DETECTION_NUMBER_FIELDS = ("detection_elapsed_seconds",)
DETECTION_LIST_FIELDS = (
    "detection_selected_domains", "detection_models_planned",
    "detection_models_completed",
)
DETECTION_TEXT_FIELDS = (
    "detection_current_model", "detection_started_at", "detection_finished_at",
    "detection_contract_fingerprint", "detection_completion_fingerprint",
    "detection_completion_contract_version",
    "detection_cursor_algorithm_version",
)
DETECTION_MAP_FIELDS = (
    "detection_watermarks", "detection_overlap_lower_bounds",
    "detection_model_completed_at", "detection_model_row_counts",
    "detection_replay_start_seconds", "detection_scan_upper_exclusives",
)
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
        "change_detection_complete",
        *DETECTION_COUNT_FIELDS, *DETECTION_NUMBER_FIELDS,
        *DETECTION_LIST_FIELDS, *DETECTION_TEXT_FIELDS, *DETECTION_MAP_FIELDS,
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
    if "change_detection_complete" in payload:
        if not isinstance(payload["change_detection_complete"], bool):
            raise ValueError("Detection completion marker must be boolean.")
        result["change_detection_complete"] = payload["change_detection_complete"]
    for field in DETECTION_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in DETECTION_NUMBER_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or not math.isfinite(value):
            raise ValueError(f"Progress duration must be a non-negative number: {field}")
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
    for field in DETECTION_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Detection progress list must contain strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Detection progress list must contain unique strings: {field}")
        result[field] = list(value)
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
    for field in DETECTION_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Detection progress text field must be a string: {field}")
        if field in {"detection_contract_fingerprint", "detection_completion_fingerprint"}:
            if len(payload[field]) != 64 or any(char not in "0123456789abcdef" for char in payload[field].lower()):
                raise ValueError(f"Detection fingerprint must be a SHA-256 hex string: {field}")
        if field == "detection_completion_contract_version" and payload[field] != "ct-change-manifest-v1":
            raise ValueError("Unsupported detection completion contract version.")
        if field in {"detection_started_at", "detection_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in DETECTION_MAP_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise ValueError(f"Detection progress map must have string keys: {field}")
        if field in {"detection_replay_start_seconds", "detection_scan_upper_exclusives"}:
            normalized_seconds = {}
            for key, timestamp in value.items():
                if timestamp is None:
                    normalized_seconds[key] = None
                elif isinstance(timestamp, str):
                    normalized_seconds[key] = _normalize_copy_forward_timestamp(timestamp, field)
                else:
                    raise ValueError(f"Detection second map must contain ISO strings or null: {field}")
            result[field] = {key: normalized_seconds[key] for key in sorted(normalized_seconds)}
            continue
        if field == "detection_model_row_counts":
            normalized_counts = {}
            for key, count in value.items():
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("Detection model row counts must be non-negative integers.")
                normalized_counts[key] = count
            result[field] = {key: normalized_counts[key] for key in sorted(normalized_counts)}
        else:
            result[field] = {key: value[key] for key in sorted(value)}
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
    if "detection_models_completed" in result:
        planned = result.get("detection_models_planned")
        if planned is None and result["detection_models_completed"]:
            raise ValueError("Completed detection models require planned models.")
        if planned is not None and not set(result["detection_models_completed"]).issubset(planned):
            raise ValueError("Completed detection models must be a subset of planned models.")
    if {"detection_started_at", "detection_finished_at", "detection_elapsed_seconds"}.issubset(result):
        started = datetime.fromisoformat(result["detection_started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(result["detection_finished_at"].replace("Z", "+00:00"))
        elapsed = (finished - started).total_seconds()
        if elapsed < 0 or round(elapsed, 6) != result["detection_elapsed_seconds"]:
            raise ValueError("Detection elapsed seconds must equal finished minus started and be non-negative.")
    if result.get("change_detection_complete"):
        planned = result.get("detection_models_planned")
        completed = result.get("detection_models_completed")
        if not planned:
            raise ValueError("Completed detection requires planned models.")
        if completed != planned:
            raise ValueError("Completed detection models must exactly equal planned models.")
        required = {
            "detection_contract_fingerprint", "detection_completion_fingerprint",
            "detection_completion_contract_version", "detection_manifest_row_count",
            "detection_model_row_counts", "detection_manifest_rows_persisted",
            "detection_started_at", "detection_finished_at", "detection_elapsed_seconds",
            "detection_cursor_algorithm_version", "detection_bucket_page_size",
            "detection_replay_start_seconds", "detection_scan_upper_exclusives",
        }
        if not required.issubset(result):
            raise ValueError("Completed detection requires complete completion evidence.")
        model_counts = result["detection_model_row_counts"]
        if set(model_counts) != set(planned):
            raise ValueError("Detection model row counts must match planned models.")
        if sum(model_counts.values()) != result["detection_manifest_row_count"]:
            raise ValueError("Detection model row counts must equal the manifest row count.")
        if result["detection_manifest_rows_persisted"] != result["detection_manifest_row_count"]:
            raise ValueError("Persisted manifest rows must equal the completion row count.")
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
