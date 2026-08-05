"""Stable user-facing refresh projection for the Control Tower UI.

The frontend must not infer raw database lifecycle meaning independently.
This module maps durable refresh evidence into plain Indonesian business
labels without inventing progress that the database cannot support.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional


FAILURE_MESSAGE = (
    "Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil."
)

RECOVERED_STAGE_LABEL = "Pembaruan lama ditutup"
RECOVERED_MESSAGE = (
    "Percobaan pembaruan lama telah ditutup. "
    "Snapshot terpercaya tetap digunakan. "
    "Anda dapat memulai Refresh Data kembali."
)

NO_CHANGE_STAGE_LABEL = "Tidak ada perubahan"
NO_CHANGE_MESSAGE = (
    "Tidak ada perubahan terdeteksi di Odoo. "
    "Snapshot terpercaya tetap digunakan."
)

_ACTIVE_STATES = frozenset({
    "REQUESTED", "PREPARING", "DETECTING_CHANGES", "FETCHING", "RECONCILING",
    "VALIDATING", "REFRESHING_DERIVED_DATA", "PUBLISHING", "RUNNING",
    "READY_FOR_PUBLISH",
})
_FAILED_STATES = frozenset({
    "FAILED", "FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "ABORTED",
})

_STAGE_LABEL_BY_STATE = {
    "REQUESTED": "Menyiapkan pembaruan",
    "PREPARING": "Menyiapkan pembaruan",
    "DETECTING_CHANGES": "Memeriksa perubahan",
    "FETCHING": "Membaca perubahan dari Odoo",
    "RECONCILING": "Menyesuaikan data terkait",
    "VALIDATING": "Memvalidasi hasil",
    "REFRESHING_DERIVED_DATA": "Memperbarui data turunan",
    "PUBLISHING": "Menerbitkan hasil",
    "RUNNING": "Membaca perubahan dari Odoo",
    "READY_FOR_PUBLISH": "Memeriksa hasil",
}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def refresh_elapsed_seconds(attempt: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Elapsed time from durable evidence only; never an in-memory claim."""
    if not attempt:
        return None
    duration = attempt.get("duration_seconds")
    if duration is not None:
        try:
            return round(float(duration), 1)
        except (TypeError, ValueError):
            return None
    started = _parse_timestamp(attempt.get("started_at"))
    if started is None:
        return None
    return round(max(0.0, (datetime.now(timezone.utc) - started).total_seconds()), 1)


def refresh_ui_projection(
    health: Mapping[str, Any],
    coordinator: Mapping[str, Any],
    can_refresh: bool,
    can_recover_stale: bool = False,
    can_retry: bool = False,
) -> dict[str, Any]:
    """Map durable refresh evidence to one stable user-facing payload."""
    attempt = health.get("latest_attempt") or {}
    status = health.get("latest_refresh_attempt_status")
    stale = bool(health.get("latest_refresh_attempt_stale"))
    candidate_pending = bool(health.get("latest_refresh_candidate_pending"))
    active = bool(coordinator.get("active_request")) or (
        status in _ACTIVE_STATES and not stale
    )
    trusted_at = health.get("latest_trusted_completed_at")
    trusted_run_id = health.get("latest_trusted_run_id")
    failure_message = health.get("latest_failure_message")
    recovered = (
        status == "ABORTED"
        and attempt.get("trigger") == "recovery"
    )

    counts = None
    model_counts = attempt.get("model_counts")
    if isinstance(model_counts, Mapping) and model_counts:
        counts = {
            "models_completed": len(model_counts),
            "records": sum(int(value or 0) for value in model_counts.values()),
        }

    stage = "IDLE"
    stage_label = "Menunggu pembaruan"
    outcome = None
    message = None
    if active:
        if status == "READY_FOR_PUBLISH" or status == "PUBLISHING":
            stage = "CHECKING"
            stage_label = "Memeriksa hasil"
        else:
            stage = "READING"
            stage_label = _STAGE_LABEL_BY_STATE.get(status, "Membaca perubahan dari Odoo")
        message = "Pembaruan sedang berjalan. Control Tower tetap menampilkan snapshot terpercaya."
    elif stale:
        stage = "STALE"
        stage_label = "Pembaruan terhenti"
        outcome = "INTERRUPTED"
        message = failure_message or (
            "Pembaruan terhenti karena melewati batas waktu. "
            "Snapshot terpercaya tetap ditampilkan."
        )
    elif recovered:
        stage = "RECOVERED"
        stage_label = RECOVERED_STAGE_LABEL
        outcome = "RECOVERED"
        message = RECOVERED_MESSAGE
    elif status in {"COMPLETED", "SUCCEEDED"}:
        stage = "DONE"
        stage_label = "Selesai"
        outcome = "SUCCESS"
        message = "Pembaruan selesai. Control Tower menampilkan snapshot terbaru yang berhasil."
    elif status == "SUCCEEDED_NO_CHANGES":
        stage = "DONE"
        stage_label = NO_CHANGE_STAGE_LABEL
        outcome = "NO_CHANGES"
        message = NO_CHANGE_MESSAGE
    elif status in _FAILED_STATES:
        stage = "FAILED"
        stage_label = "Gagal"
        outcome = "FAILED"
        message = failure_message or FAILURE_MESSAGE
    elif not trusted_at:
        stage = "NO_COMPLETED_EXTRACTION"
        stage_label = "Belum ada snapshot"
        message = "Belum ada snapshot terpercaya. Jalankan pembaruan data untuk memulai."

    return {
        "status": stage,
        "outcome": outcome,
        "stage_label": stage_label,
        "message": message,
        "active": active,
        "can_refresh": bool(can_refresh),
        "can_recover_stale": bool(can_recover_stale),
        "can_retry": bool(can_retry),
        "stale_attempt": stale,
        "candidate_pending": candidate_pending,
        "elapsed_seconds": (
            refresh_elapsed_seconds(attempt) if attempt else None
        ),
        "counts": counts,
        "trusted": (
            {"timestamp": trusted_at, "run_id": trusted_run_id}
            if trusted_at
            else None
        ),
        "latest_attempt": (
            {
                "status": status,
                "started_at": attempt.get("started_at"),
                "finished_at": attempt.get("finished_at")
                or attempt.get("completed_at"),
                "error_message": attempt.get("error_message"),
                "trigger": attempt.get("trigger"),
                "run_id": attempt.get("run_id"),
            }
            if attempt
            else None
        ),
    }
