"""Freshness classification for the trusted Control Tower snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


CURRENT_MAX_AGE_SECONDS = 24 * 60 * 60
STALE_MAX_AGE_SECONDS = 48 * 60 * 60
REFRESH_ATTEMPT_STALE_SECONDS = 30 * 60


def refresh_attempt_is_stale(
    started_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    threshold_seconds: int = REFRESH_ATTEMPT_STALE_SECONDS,
) -> bool:
    """Identify an abandoned attempt without changing its database row."""
    if started_at is None:
        return False
    if isinstance(started_at, str):
        try:
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return (reference - started_at).total_seconds() > threshold_seconds


def freshness_classification(
    completed_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    """Return a truthful age/state payload without using browser load time."""
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if completed_at is None:
        return {
            "state": "CRITICALLY_STALE",
            "data_age_seconds": None,
            "data_age_hours": None,
            "reason": "No trusted completed snapshot is available.",
        }
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (reference - completed_at).total_seconds())
    if age_seconds <= CURRENT_MAX_AGE_SECONDS:
        state = "CURRENT"
    elif age_seconds <= STALE_MAX_AGE_SECONDS:
        state = "STALE"
    else:
        state = "CRITICALLY_STALE"
    return {
        "state": state,
        "data_age_seconds": round(age_seconds, 3),
        "data_age_hours": round(age_seconds / 3600, 3),
        "reason": f"Trusted snapshot completed {completed_at.isoformat()}.",
    }
