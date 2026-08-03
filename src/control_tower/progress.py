"""Truthful, nullable progress payload validation and deterministic persistence."""

from __future__ import annotations

import json
from typing import Any, Mapping

COUNT_FIELDS = ("domains_planned", "domains_completed", "models_planned", "models_completed", "records_detected", "records_fetched", "inserted", "updated", "unchanged", "removed", "parents_reconciled", "views_refreshed", "checks_recalculated", "findings_opened", "findings_resolved")
LIST_FIELDS = ("domains", "completed_domains", "models", "completed_models")
TEXT_FIELDS = ("current_domain", "current_model", "stage_message")
KNOWN_FIELDS = frozenset((*COUNT_FIELDS, *LIST_FIELDS, *TEXT_FIELDS))


class ProgressContractError(ValueError):
    """Raised when a progress payload cannot be trusted."""


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
    for field in LIST_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Progress list must contain strings: {field}")
        result[field] = sorted(set(value))
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
