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
ORCHESTRATION_COUNT_FIELDS = ("orchestration_manifest_rows",)
ORCHESTRATION_NUMBER_FIELDS = ("orchestration_elapsed_seconds",)
ORCHESTRATION_LIST_FIELDS = (
    "orchestration_selected_domains",
    "orchestration_models_planned",
    "orchestration_models_completed",
)
ORCHESTRATION_TEXT_FIELDS = (
    "orchestration_started_at",
    "orchestration_finished_at",
    "orchestration_current_stage",
    "orchestration_last_completed_stage",
    "orchestration_next_required_stage",
    "orchestration_copy_forward_status",
    "orchestration_detection_status",
)
ORCHESTRATION_BOOL_FIELDS = ("orchestration_no_changes",)
FETCH_APPLY_COUNT_FIELDS = (
    "fetch_apply_records_requested",
    "fetch_apply_records_fetched",
    "fetch_apply_records_missing_at_fetch",
    "fetch_apply_records_source_drift",
    "fetch_apply_inserted",
    "fetch_apply_updated",
    "fetch_apply_unchanged",
    "fetch_apply_applied_total",
    "fetch_apply_batches_completed",
)
FETCH_APPLY_NUMBER_FIELDS = ("fetch_apply_elapsed_seconds",)
FETCH_APPLY_LIST_FIELDS = (
    "fetch_apply_models_planned",
    "fetch_apply_models_completed",
)
FETCH_APPLY_TEXT_FIELDS = (
    "fetch_apply_current_model",
    "fetch_apply_started_at",
    "fetch_apply_finished_at",
    "fetch_apply_completion_fingerprint",
    "fetch_apply_contract_version",
)
FETCH_APPLY_BOOL_FIELDS = ("fetch_apply_complete",)
RECONCILIATION_COUNT_FIELDS = (
    "reconciliation_sets_enqueued",
    "reconciliation_sets_completed",
    "reconciliation_records_read",
    "reconciliation_records_removed",
)
RECONCILIATION_NUMBER_FIELDS = ("reconciliation_elapsed_seconds",)
RECONCILIATION_LIST_FIELDS = ("reconciliation_sets_planned", "reconciliation_sets_completed_list")
RECONCILIATION_TEXT_FIELDS = (
    "reconciliation_current_parent",
    "reconciliation_started_at",
    "reconciliation_finished_at",
)
RECONCILIATION_BOOL_FIELDS = ("reconciliation_complete",)
VALIDATION_COUNT_FIELDS = ("validation_issues",)
VALIDATION_NUMBER_FIELDS = ("validation_elapsed_seconds",)
VALIDATION_TEXT_FIELDS = ("validation_started_at", "validation_finished_at")
VALIDATION_BOOL_FIELDS = ("validation_complete",)
DERIVED_COUNT_FIELDS = ("derived_sql_files_applied",)
DERIVED_NUMBER_FIELDS = ("derived_sql_elapsed_seconds",)
DERIVED_TEXT_FIELDS = ("derived_started_at", "derived_finished_at")
DERIVED_BOOL_FIELDS = ("derived_refresh_complete",)
PUBLICATION_COUNT_FIELDS = ("watermarks_advanced",)
PUBLICATION_NUMBER_FIELDS = ("publication_elapsed_seconds",)
PUBLICATION_TEXT_FIELDS = ("publication_started_at", "publication_finished_at")
PUBLICATION_BOOL_FIELDS = ("publication_complete",)
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
        *ORCHESTRATION_COUNT_FIELDS, *ORCHESTRATION_NUMBER_FIELDS,
        *ORCHESTRATION_LIST_FIELDS, *ORCHESTRATION_TEXT_FIELDS,
        *ORCHESTRATION_BOOL_FIELDS,
        *FETCH_APPLY_COUNT_FIELDS, *FETCH_APPLY_NUMBER_FIELDS,
        *FETCH_APPLY_LIST_FIELDS, *FETCH_APPLY_TEXT_FIELDS,
        *FETCH_APPLY_BOOL_FIELDS,
        *RECONCILIATION_COUNT_FIELDS, *RECONCILIATION_NUMBER_FIELDS,
        *RECONCILIATION_LIST_FIELDS, *RECONCILIATION_TEXT_FIELDS,
        *RECONCILIATION_BOOL_FIELDS,
        *VALIDATION_COUNT_FIELDS, *VALIDATION_NUMBER_FIELDS,
        *VALIDATION_TEXT_FIELDS, *VALIDATION_BOOL_FIELDS,
        *DERIVED_COUNT_FIELDS, *DERIVED_NUMBER_FIELDS,
        *DERIVED_TEXT_FIELDS, *DERIVED_BOOL_FIELDS,
        *PUBLICATION_COUNT_FIELDS, *PUBLICATION_NUMBER_FIELDS,
        *PUBLICATION_TEXT_FIELDS, *PUBLICATION_BOOL_FIELDS,
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
    for field in ORCHESTRATION_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in FETCH_APPLY_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in RECONCILIATION_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in VALIDATION_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in DERIVED_COUNT_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Progress count must be a non-negative integer: {field}")
        result[field] = value
    for field in PUBLICATION_COUNT_FIELDS:
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
    for field in ORCHESTRATION_NUMBER_FIELDS:
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
    for field in FETCH_APPLY_NUMBER_FIELDS:
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
    for field in RECONCILIATION_NUMBER_FIELDS:
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
    for field in VALIDATION_NUMBER_FIELDS:
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
    for field in DERIVED_NUMBER_FIELDS:
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
    for field in PUBLICATION_NUMBER_FIELDS:
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
    for field in ORCHESTRATION_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Orchestration progress list must contain strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Orchestration progress list must contain unique strings: {field}")
        result[field] = list(value)
    for field in FETCH_APPLY_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Fetch/apply progress list must contain strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Fetch/apply progress list must contain unique strings: {field}")
        result[field] = list(value)
    for field in RECONCILIATION_LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Reconciliation progress list must contain strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Reconciliation progress list must contain unique strings: {field}")
        result[field] = list(value)
    if "fetch_apply_models_completed" in result:
        planned = result.get("fetch_apply_models_planned")
        if planned is None and result["fetch_apply_models_completed"]:
            raise ValueError("Completed fetch/apply models require planned models.")
        if planned is not None and not set(result["fetch_apply_models_completed"]).issubset(planned):
            raise ValueError("Completed fetch/apply models must be a subset of planned models.")
    if "orchestration_models_completed" in result:
        planned = result.get("orchestration_models_planned")
        if planned is None and result["orchestration_models_completed"]:
            raise ValueError("Completed orchestration models require planned models.")
        if planned is not None and not set(result["orchestration_models_completed"]).issubset(planned):
            raise ValueError("Completed orchestration models must be a subset of planned models.")
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
    for field in ORCHESTRATION_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Orchestration progress text field must be a string: {field}")
        if field in {"orchestration_started_at", "orchestration_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in ORCHESTRATION_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Orchestration progress marker must be boolean: {field}")
        result[field] = payload[field]
    for field in FETCH_APPLY_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Fetch/apply progress text field must be a string: {field}")
        if field == "fetch_apply_completion_fingerprint" and (
            len(payload[field]) != 64 or any(char not in "0123456789abcdef" for char in payload[field].lower())
        ):
            raise ValueError("Fetch/apply completion fingerprint must be a SHA-256 hex string.")
        if field in {"fetch_apply_started_at", "fetch_apply_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in FETCH_APPLY_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Fetch/apply progress marker must be boolean: {field}")
        result[field] = payload[field]
    for field in RECONCILIATION_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Reconciliation progress text field must be a string: {field}")
        if field in {"reconciliation_started_at", "reconciliation_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in RECONCILIATION_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Reconciliation progress marker must be boolean: {field}")
        result[field] = payload[field]
    for field in VALIDATION_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Validation progress text field must be a string: {field}")
        if field in {"validation_started_at", "validation_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in VALIDATION_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Validation progress marker must be boolean: {field}")
        result[field] = payload[field]
    for field in DERIVED_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Derived progress text field must be a string: {field}")
        if field in {"derived_started_at", "derived_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in DERIVED_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Derived progress marker must be boolean: {field}")
        result[field] = payload[field]
    for field in PUBLICATION_TEXT_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        if not isinstance(payload[field], str):
            raise ValueError(f"Publication progress text field must be a string: {field}")
        if field in {"publication_started_at", "publication_finished_at"}:
            result[field] = _normalize_copy_forward_timestamp(payload[field], field)
        else:
            result[field] = payload[field]
    for field in PUBLICATION_BOOL_FIELDS:
        if field not in payload:
            continue
        if not isinstance(payload[field], bool):
            raise ValueError(f"Publication progress marker must be boolean: {field}")
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
    if {"orchestration_started_at", "orchestration_finished_at", "orchestration_elapsed_seconds"}.issubset(result):
        started = datetime.fromisoformat(result["orchestration_started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(result["orchestration_finished_at"].replace("Z", "+00:00"))
        elapsed = (finished - started).total_seconds()
        if elapsed < 0 or round(elapsed, 6) != result["orchestration_elapsed_seconds"]:
            raise ValueError("Orchestration elapsed seconds must equal finished minus started and be non-negative.")
    if {"fetch_apply_started_at", "fetch_apply_finished_at", "fetch_apply_elapsed_seconds"}.issubset(result):
        started = datetime.fromisoformat(result["fetch_apply_started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(result["fetch_apply_finished_at"].replace("Z", "+00:00"))
        elapsed = (finished - started).total_seconds()
        if elapsed < 0 or round(elapsed, 6) != result["fetch_apply_elapsed_seconds"]:
            raise ValueError("Fetch/apply elapsed seconds must equal finished minus started and be non-negative.")
    if result.get("fetch_apply_complete"):
        planned = result.get("fetch_apply_models_planned")
        completed = result.get("fetch_apply_models_completed")
        if not planned:
            raise ValueError("Completed fetch/apply requires planned models.")
        if completed != planned:
            raise ValueError("Completed fetch/apply models must exactly equal planned models.")
        required = {
            "fetch_apply_started_at", "fetch_apply_finished_at",
            "fetch_apply_elapsed_seconds", "fetch_apply_completion_fingerprint",
            "fetch_apply_contract_version", "fetch_apply_records_requested",
            "fetch_apply_records_fetched", "fetch_apply_records_missing_at_fetch",
            "fetch_apply_records_source_drift", "fetch_apply_inserted",
            "fetch_apply_updated", "fetch_apply_unchanged",
            "fetch_apply_applied_total", "fetch_apply_batches_completed",
        }
        if not required.issubset(result):
            raise ValueError("Completed fetch/apply requires complete completion evidence.")
        if (
            result["fetch_apply_applied_total"]
            != result["fetch_apply_inserted"] + result["fetch_apply_updated"] + result["fetch_apply_unchanged"]
        ):
            raise ValueError("Fetch/apply applied total must equal applied classifications.")
        if (
            result["fetch_apply_records_fetched"]
            + result["fetch_apply_records_missing_at_fetch"]
            != result["fetch_apply_records_requested"]
        ):
            raise ValueError("Fetch/apply fetched plus missing must equal requested.")
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
    if result.get("reconciliation_complete"):
        if not result.get("reconciliation_started_at") or not result.get("reconciliation_finished_at"):
            raise ValueError("Completed reconciliation requires start and finish timestamps.")
        if result.get("reconciliation_sets_enqueued", 0) < result.get("reconciliation_sets_completed", 0):
            raise ValueError("Completed reconciliation sets cannot exceed enqueued sets.")
        for completed_field, planned_field in (
            ("reconciliation_sets_completed_list", "reconciliation_sets_planned"),
        ):
            if completed_field in result:
                if planned_field not in result:
                    raise ValueError(f"Completed reconciliation requires planned sets: {completed_field}")
                if not set(result[completed_field]).issubset(result[planned_field]):
                    raise ValueError(f"Completed reconciliation sets must be a subset of planned sets.")
    if result.get("validation_complete"):
        if not result.get("validation_started_at") or not result.get("validation_finished_at"):
            raise ValueError("Completed validation requires start and finish timestamps.")
    if result.get("derived_refresh_complete"):
        if not result.get("derived_started_at") or not result.get("derived_finished_at"):
            raise ValueError("Completed derived refresh requires start and finish timestamps.")
    if result.get("publication_complete"):
        if not result.get("publication_started_at") or not result.get("publication_finished_at"):
            raise ValueError("Completed publication requires start and finish timestamps.")
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
