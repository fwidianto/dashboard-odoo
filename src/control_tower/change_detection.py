"""Read-only incremental change detection for the Control Tower boundary.

Phase 8B-2B2R cursor contract
-----------------------------
Odoo 18 XML-RPC exposes ``write_date`` as a timezone-naive wall-clock string
``YYYY-MM-DD HH:MM:SS`` that represents UTC.  The Odoo database keeps hidden
microsecond precision, so a cross-run equality on ``write_date`` never matches.
Detection therefore scans whole displayed seconds with range buckets:

``write_date >= second_start AND write_date < second_start + 1 second``

The persisted watermark is canonical timezone-aware UTC with an effective
cursor precision of one second.  ``replay_start_second`` is
``watermark_second - configured_overlap_seconds``.  Every run replays the
complete watermark second, even when the configured overlap is zero; the
persisted watermark ID is auxiliary evidence only and must never exclude
lower-ID records that were updated later within the same displayed second.
The record-ID cursor is strictly an intra-run, intra-bucket pagination cursor.

At the beginning of each model scan a read-only probe captures a fixed upper
boundary (``scan_upper_exclusive = displayed_second + 1 second``) so a run
never chases an indefinitely moving source.  Rows at or after that boundary
are left for a later run.

The manifest ``from_overlap`` marker is true for both configured overlap
replay (displayed second below the watermark second) and mandatory precision
replay (displayed second equal to the watermark second); progress reports the
two classes separately from genuinely newer rows.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import text

from src.control_tower.contracts import ModelExecutionContract, resolve_domain_selection, resolve_execution_entries
from src.control_tower.progress import parse_progress_json, serialize_progress
from src.control_tower.refresh import REFRESH_LOCK_KEY
from src.control_tower.schema_guard import ensure_phase8_detection_schema_ready
from src.control_tower.watermarks import normalize_utc, validate_watermark_row, watermark_displayed_second
from src.control_tower.relation_extractor import MODEL_SPECS

DETECTION_STATUS = "DETECTED"
MANIFEST_COMPLETE = "COMPLETE"
MANIFEST_RUNNING = "RUNNING"
COMPLETION_CONTRACT_VERSION = "ct-change-manifest-v1"
DETECTION_CONTRACT_VERSION = "ct-detection-contract-v2"
DETECTION_CURSOR_ALGORITHM_VERSION = "ct-second-bucket-v1"
DETECTION_BUCKET_PAGE_SIZE = 500
_ODOO_WRITE_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$")


class ChangeDetectionError(ValueError):
    """Base error for fail-closed change detection."""


class BootstrapRequired(ChangeDetectionError):
    """Raised when a selected model has no successfully published watermark."""


@dataclass(frozen=True)
class DetectionModelResult:
    model: str
    scanned: int
    overlap_rechecked: int
    newer_detected: int
    duplicates_removed: int
    manifest_rows: int
    parent_hints: int
    configured_overlap_rows: int = 0
    watermark_second_replay_rows: int = 0
    genuinely_newer_rows: int = 0


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ChangeDetectionError("Odoo write_date is malformed.") from exc
    try:
        return normalize_utc(value)
    except ValueError as exc:
        raise ChangeDetectionError("Odoo write_date must be timezone-aware.") from exc


def parse_odoo_write_date(value: Any) -> datetime:
    """Parse an Odoo XML-RPC ``write_date`` string into aware UTC.

    Odoo 18 XML-RPC returns ``write_date`` as a timezone-naive wall-clock
    string ``YYYY-MM-DD HH:MM:SS`` (UTC).  This transport-boundary parser is
    the only place naive wall-clock values are accepted; general internal
    normalization stays strict and continues to require aware datetimes.
    Hidden database microseconds are intentionally not represented: the
    result is truncated to the displayed second.
    """
    if not isinstance(value, str):
        raise ChangeDetectionError("Odoo write_date must match YYYY-MM-DD HH:MM:SS.")
    match = _ODOO_WRITE_DATE_RE.fullmatch(value)
    if match is None:
        raise ChangeDetectionError("Odoo write_date must match YYYY-MM-DD HH:MM:SS.")
    try:
        parsed = datetime(*(int(part) for part in match.groups()), tzinfo=timezone.utc)
    except ValueError as exc:
        raise ChangeDetectionError(f"Odoo write_date is not a valid date: {value!r}") from exc
    return parsed


_ALLOWED_DOMAIN_OPERATORS = frozenset({"=", "!=", ">", ">=", "<", "<="})
_DOMAIN_PREFIX_OPERATORS = frozenset({"&", "|"})


def _validate_flat_domain_leaf(leaf: Any, model: str) -> None:
    """Validate one Odoo domain leaf without nested Boolean structures."""
    if not isinstance(leaf, (tuple, list)) or len(leaf) != 3:
        raise ChangeDetectionError(f"Malformed Odoo domain leaf for {model}: {leaf!r}")
    field, operator, value = leaf
    if isinstance(field, str) and field in _DOMAIN_PREFIX_OPERATORS:
        raise ChangeDetectionError(
            f"Nested Odoo Boolean domain is unsupported: "
            f"Invalid field {model}.{field} in leaf {leaf!r}"
        )
    if not isinstance(field, str) or not isinstance(operator, str):
        raise ChangeDetectionError(f"Malformed Odoo domain leaf for {model}: {leaf!r}")
    if operator not in _ALLOWED_DOMAIN_OPERATORS:
        raise ChangeDetectionError(f"Unsupported Odoo domain operator for {model}: {leaf!r}")
    if isinstance(value, (dict, list, tuple)):
        raise ChangeDetectionError(f"Unsupported Odoo domain leaf value for {model}: {leaf!r}")


def _validate_flat_domain(domain: Any, model: str) -> None:
    """Reject nested Odoo Boolean-domain structures before any server call.

    Real Odoo 18 treats nested sublists as leaves and raises
    ``Invalid field <model>.& in leaf``.  Detection domains are conjunctive, so
    flat implicit-AND lists are the only supported shape, with a flat prefix
    form allowed only where an explicit ``&`` is genuinely needed.
    """
    if not isinstance(domain, list):
        raise ChangeDetectionError(f"Odoo domain must be a flat list for {model}.")
    if not domain:
        return
    if isinstance(domain[0], str) and domain[0] in _DOMAIN_PREFIX_OPERATORS:
        if len(domain) < 3:
            raise ChangeDetectionError(f"Malformed flat prefix Odoo domain for {model}: {domain!r}")
        for operand in domain[1:]:
            _validate_flat_domain_leaf(operand, model)
        return
    for leaf in domain:
        if isinstance(leaf, (dict, str)):
            raise ChangeDetectionError(f"Invalid Odoo domain leaf for {model}: {leaf!r}")
        _validate_flat_domain_leaf(leaf, model)


def _positive_id(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ChangeDetectionError(f"{label} must be a positive integer.")
    return value


def _relation_id(value: Any, label: str) -> int | None:
    if value in (None, False):
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ChangeDetectionError(f"{label} must be an Odoo many2one pair or null.")
    record_id, display_value = value
    if not isinstance(display_value, str) or not display_value:
        raise ChangeDetectionError(f"{label} has an invalid display value.")
    return _positive_id(record_id, label)


def _registry_fingerprint(entries: tuple[ModelExecutionContract, ...]) -> str:
    specs = {spec.model: spec for spec in MODEL_SPECS}
    value = []
    for entry in entries:
        value.append({
            "model": entry.model_key,
            "domains": list(entry.domain_keys),
            "fields": list(specs[entry.model_key].fields),
            "parents": [
                {"parent_model": rel.parent_model, "field": rel.parent_field}
                for rel in entry.parent_children
                if rel.child_model == entry.model_key
            ],
        })
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _watermark_inputs(watermarks: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        model: {
            "write_date": watermark_displayed_second(row["last_successful_write_date"]).isoformat(),
            "id": row["last_successful_id"],
            "overlap_seconds": row["overlap_seconds"],
            "published_run_id": row["published_run_id"],
        }
        for model, row in sorted(watermarks.items())
    }


def _contract_fingerprint(
    company_id: int,
    base_snapshot_run_id: str,
    domains: tuple[str, ...],
    entries: tuple[ModelExecutionContract, ...],
    watermark_inputs: Mapping[str, Mapping[str, Any]],
    scan_upper_exclusives: Mapping[str, Any] | None = None,
    bucket_page_size: int = DETECTION_BUCKET_PAGE_SIZE,
) -> str:
    value = {
        "version": DETECTION_CONTRACT_VERSION,
        "cursor_algorithm_version": DETECTION_CURSOR_ALGORITHM_VERSION,
        "bucket_page_size": bucket_page_size,
        "company_id": company_id,
        "base_snapshot_run_id": str(base_snapshot_run_id),
        "selected_domains": list(domains),
        "entries": [
            {
                "model": entry.model_key,
                "domains": list(entry.domain_keys),
                "fields": list(_detection_fields(entry)),
                "parents": [
                    {"parent_model": rel.parent_model, "child_model": rel.child_model, "field": rel.parent_field}
                    for rel in sorted(entry.parent_children, key=lambda rel: (rel.parent_model, rel.child_model, rel.parent_field))
                ],
            }
            for entry in entries
        ],
        "watermarks": watermark_inputs,
        "replay_start_seconds": {
            model: (
                datetime.fromisoformat(row["write_date"].replace("Z", "+00:00"))
                - timedelta(seconds=row["overlap_seconds"])
            ).isoformat()
            for model, row in watermark_inputs.items()
        },
        "scan_upper_exclusives": scan_upper_exclusives,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _canonical_manifest_row(row: Mapping[str, Any]) -> dict[str, Any]:
    hints = sorted(
        row["parent_hints"] or [],
        key=lambda hint: (hint["parent_model"], hint["field"], hint["parent_record_id"]),
    )
    return {
        "company_id": row["company_id"],
        "business_domains": list(row["business_domains"]),
        "model": row["model"],
        "record_id": row["record_id"],
        "source_write_date": _utc(row["source_write_date"]).isoformat(),
        "parent_model": row["parent_model"],
        "parent_record_id": row["parent_record_id"],
        "parent_hints": hints,
        "from_overlap": row["from_overlap"],
        "detection_sequence": row["detection_sequence"],
        "detected_at": _utc(row["detected_at"]).isoformat(),
        "status": row["status"],
    }


def _manifest_evidence(rows: list[Mapping[str, Any]], models: tuple[str, ...]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["model"], row["detection_sequence"], row["record_id"]))
    model_counts = {model: 0 for model in models}
    chunks = [COMPLETION_CONTRACT_VERSION]
    for row in ordered:
        if row["model"] not in model_counts:
            raise ChangeDetectionError("Manifest contains an unexpected model.")
        if row["company_id"] <= 0 or row["status"] != DETECTION_STATUS:
            raise ChangeDetectionError("Manifest contains invalid completion evidence.")
        model_counts[row["model"]] += 1
        chunks.append(json.dumps(_canonical_manifest_row(row), sort_keys=True, separators=(",", ":")))
    for model in models:
        sequences = [row["detection_sequence"] for row in ordered if row["model"] == model]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ChangeDetectionError(f"Manifest sequence is incomplete for {model}.")
    return {
        "fingerprint": hashlib.sha256("\n".join(chunks).encode()).hexdigest(),
        "row_count": len(ordered),
        "model_row_counts": model_counts,
    }


def _detection_fields(entry: ModelExecutionContract) -> tuple[str, ...]:
    spec = next(spec for spec in MODEL_SPECS if spec.model == entry.model_key)
    required = {"id", "write_date", "company_id"}
    if not required.issubset(spec.fields):
        raise ChangeDetectionError(
            f"Detection base fields are not approved for {entry.model_key}: {sorted(required - set(spec.fields))}"
        )
    fields = ["id", "write_date"]
    if "company_id" in spec.fields:
        fields.append("company_id")
    for relation in sorted(
        (rel for rel in entry.parent_children if rel.child_model == entry.model_key),
        key=lambda rel: (rel.parent_model, rel.parent_field),
    ):
        if relation.parent_field not in spec.fields:
            raise ChangeDetectionError(
                f"Detection field {entry.model_key}.{relation.parent_field} is not approved by MODEL_SPECS."
            )
        fields.append(relation.parent_field)
    return tuple(dict.fromkeys(fields))


def _parse_detection_row(
    record: Mapping[str, Any],
    model: str,
    fields: tuple[str, ...],
    company_id: int,
    parent_field_map: Mapping[str, str],
) -> tuple[int, datetime, list[dict[str, Any]]]:
    if not isinstance(record, Mapping):
        raise ChangeDetectionError("Odoo detection response contained a non-object row.")
    unexpected = set(record) - set(fields)
    if unexpected:
        raise ChangeDetectionError(f"Odoo detection response contained unexpected fields: {sorted(unexpected)}")
    missing = {"id", "write_date", "company_id"} - set(record)
    if missing:
        raise ChangeDetectionError(f"Odoo detection response omitted required fields: {sorted(missing)}")
    record_id = _positive_id(record.get("id"), f"{model}.id")
    source_date = parse_odoo_write_date(record.get("write_date"))
    company = _relation_id(record.get("company_id"), f"{model}.company_id")
    if company != company_id:
        raise ChangeDetectionError(f"Odoo detection response crossed company scope for {model}.")
    hints: list[dict[str, Any]] = []
    for field, parent_model in sorted(parent_field_map.items()):
        parent_id = _relation_id(record.get(field), f"{model}.{field}")
        if parent_id is not None:
            hints.append({"parent_model": parent_model, "parent_record_id": parent_id, "field": field})
    return record_id, source_date, hints


def _capture_scan_upper_exclusive(
    odoo_client, model: str, company_id: int, replay_start_second: datetime, fields: tuple[str, ...],
) -> datetime | None:
    """Capture the fixed scan upper boundary for one model with a limit=1 probe.

    The boundary is exclusive: no row with ``write_date >= scan_upper_exclusive``
    is ever included in the current run.  If no row exists at or after
    ``replay_start_second`` the model has no candidates and no boundary is invented.
    """
    domain = [
        "&", ("company_id", "=", company_id),
        ("write_date", ">=", replay_start_second.isoformat()),
    ]
    _validate_flat_domain(domain, model)
    records = odoo_client.search_read(model, domain, fields=list(fields), order="write_date desc, id desc", limit=1)
    if not isinstance(records, list):
        raise ChangeDetectionError(f"Odoo search_read returned a non-list for {model}.")
    if not records:
        return None
    if len(records) > 1:
        raise ChangeDetectionError(f"Odoo upper-bound probe returned more than one row for {model}.")
    record_id, source_date, _ = _parse_detection_row(records[0], model, fields, company_id, {})
    if source_date < replay_start_second:
        raise ChangeDetectionError(f"Odoo upper-bound probe returned a row below the replay start for {model}/{record_id}.")
    return source_date + timedelta(seconds=1)


def _locate_next_bucket(
    odoo_client, model: str, company_id: int, probe_second: datetime, scan_upper_exclusive: datetime, fields: tuple[str, ...],
) -> datetime | None:
    """Probe the next populated displayed second with one limit=1 read.

    Empty seconds are skipped by a single probe; there is no per-second empty
    loop iteration.  The returned displayed second is validated to stay inside
    the approved scan window.
    """
    domain = [
        ("company_id", "=", company_id),
        ("write_date", ">=", probe_second.isoformat()),
        ("write_date", "<", scan_upper_exclusive.isoformat()),
    ]
    _validate_flat_domain(domain, model)
    records = odoo_client.search_read(model, domain, fields=list(fields), order="write_date asc, id asc", limit=1)
    if not isinstance(records, list):
        raise ChangeDetectionError(f"Odoo search_read returned a non-list for {model}.")
    if not records:
        return None
    if len(records) > 1:
        raise ChangeDetectionError(f"Odoo bucket probe returned more than one row for {model}.")
    record_id, source_date, _ = _parse_detection_row(records[0], model, fields, company_id, {})
    if source_date < probe_second or source_date >= scan_upper_exclusive:
        raise ChangeDetectionError(f"Odoo bucket probe left the approved scan window for {model}/{record_id}.")
    return source_date


def _scan_bucket_page(
    odoo_client, model: str, company_id: int, bucket_second: datetime, cursor: int, fields: tuple[str, ...], page_size: int,
) -> list[Any]:
    """Read one bounded page inside a single displayed second.

    The record-ID cursor is an intra-run, intra-bucket pagination cursor only;
    it starts at zero for the first page and never derives from the persisted
    watermark ID.  Equality on ``write_date`` is never generated.
    """
    domain = [
        ("company_id", "=", company_id),
        ("write_date", ">=", bucket_second.isoformat()),
        ("write_date", "<", (bucket_second + timedelta(seconds=1)).isoformat()),
        ("id", ">", cursor),
    ]
    _validate_flat_domain(domain, model)
    records = odoo_client.search_read(model, domain, fields=list(fields), order="id asc", limit=page_size)
    if not isinstance(records, list):
        raise ChangeDetectionError(f"Odoo search_read returned a non-list for {model}.")
    if len(records) > page_size:
        raise ChangeDetectionError(f"Odoo bucket page exceeded the configured page size for {model}.")
    return records


@contextmanager
def _refresh_lock(pg):
    connection = pg.engine.connect()
    locked = False
    try:
        locked = bool(connection.execute(
            text("SELECT pg_try_advisory_lock(CAST(:lock_key AS BIGINT))"),
            {"lock_key": REFRESH_LOCK_KEY},
        ).scalar())
        if not locked:
            raise ChangeDetectionError("A Control Tower refresh is already running.")
        yield
    finally:
        if locked:
            connection.execute(
                text("SELECT pg_advisory_unlock(CAST(:lock_key AS BIGINT))"),
                {"lock_key": REFRESH_LOCK_KEY},
            )
            connection.commit()
        connection.close()


class IncrementalChangeDetectionService:
    """Detect changed IDs and relation hints; never fetches complete records."""

    def __init__(self, postgres_client, *, schema_guard=ensure_phase8_detection_schema_ready):
        self.pg = postgres_client
        schema_guard(postgres_client)

    def detect(
        self,
        *,
        run_id: str,
        company_id: int,
        selected_domains: list[str] | tuple[str, ...] | None,
        odoo_client,
        bucket_page_size: int = DETECTION_BUCKET_PAGE_SIZE,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            run_uuid = str(UUID(str(run_id)))
        except (TypeError, ValueError) as exc:
            raise ChangeDetectionError("Refresh run ID must be a UUID.") from exc
        if isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0:
            raise ChangeDetectionError("Company ID must be a positive integer.")
        if isinstance(bucket_page_size, bool) or not isinstance(bucket_page_size, int) or bucket_page_size <= 0:
            raise ChangeDetectionError("Bucket page size must be a positive integer.")
        timestamp = normalize_utc(now or datetime.now(timezone.utc))
        resolved_domains = tuple(domain.key for domain in resolve_domain_selection(selected_domains))
        entries = resolve_execution_entries(resolved_domains)
        models = tuple(entry.model_key for entry in entries)
        registry_fingerprint = _registry_fingerprint(entries)

        with _refresh_lock(self.pg):
            inputs = self._lock_candidate_and_load_inputs(
                run_uuid, company_id, resolved_domains, models, registry_fingerprint,
            )
            watermarks = self._load_watermarks(company_id, models)
            if any(row["status"] != "READY" for row in watermarks.values()):
                missing = sorted(model for model, row in watermarks.items() if row["status"] != "READY")
                raise BootstrapRequired(f"BOOTSTRAP_REQUIRED for model(s): {missing}")
            watermark_inputs = _watermark_inputs(watermarks)
            contract_fingerprint = _contract_fingerprint(
                company_id, inputs["base_snapshot_run_id"], resolved_domains, entries, watermark_inputs,
            )
            if inputs["manifest_status"] == MANIFEST_COMPLETE:
                if inputs["watermark_inputs"] != watermark_inputs:
                    raise ChangeDetectionError("Completed change manifest is stale because watermark inputs changed.")
                final_fingerprint = _contract_fingerprint(
                    company_id, inputs["base_snapshot_run_id"], resolved_domains, entries,
                    watermark_inputs,
                    inputs["candidate_progress"].get("detection_scan_upper_exclusives") or {},
                    bucket_page_size,
                )
                if inputs["contract_fingerprint"] != final_fingerprint:
                    raise ChangeDetectionError("Completed change manifest contract inputs changed.")
                return self._idempotent_result(
                    run_uuid, inputs, company_id, models, entries, resolved_domains,
                    final_fingerprint, watermarks, bucket_page_size,
                )
            if inputs["manifest_status"] == MANIFEST_RUNNING:
                raise ChangeDetectionError("A partial change manifest cannot be silently reused.")
            self._start_manifest(
                run_uuid, company_id, inputs["base_snapshot_run_id"], resolved_domains,
                models, registry_fingerprint, contract_fingerprint, watermark_inputs, timestamp,
            )
            progress = self._initial_progress(
                resolved_domains, models, timestamp, watermarks,
                inputs["candidate_progress"], contract_fingerprint, bucket_page_size,
            )
            self._write_progress(run_uuid, progress)

            results: list[DetectionModelResult] = []
            scan_upper_exclusives: dict[str, Any] = {}
            for entry in entries:
                result, rows, scan = self._detect_model(
                    entry, company_id, watermarks[entry.model_key], odoo_client, bucket_page_size,
                )
                scan_upper_exclusives[entry.model_key] = (
                    scan["scan_upper_exclusive"].isoformat()
                    if scan["scan_upper_exclusive"] is not None else None
                )
                progress = self._progress_after_model(
                    progress, entry.model_key, result, scan, timestamp,
                )
                self._persist_model(run_uuid, company_id, entry, rows, result, progress, timestamp)
                results.append(result)
            with self.pg.engine.begin() as conn:
                manifest_rows = conn.execute(text("""
                    SELECT company_id, business_domains, model, record_id, source_write_date,
                           parent_model, parent_record_id, parent_hints, from_overlap,
                           detection_sequence, detected_at, status
                    FROM ct_change_manifest
                    WHERE run_id = CAST(:run_id AS UUID)
                    ORDER BY model, detection_sequence, record_id
                    FOR UPDATE
                """), {"run_id": run_uuid}).mappings().all()
                evidence = _manifest_evidence([dict(row) for row in manifest_rows], models)
                expected_counts = {result.model: result.manifest_rows for result in results}
                if evidence["model_row_counts"] != expected_counts:
                    raise ChangeDetectionError("Manifest model counts do not match completed model results.")
                finished = normalize_utc(now or datetime.now(timezone.utc))
                elapsed = round(max(0.0, (finished - timestamp).total_seconds()), 6)
                final_fingerprint = _contract_fingerprint(
                    company_id, inputs["base_snapshot_run_id"], resolved_domains, entries,
                    watermark_inputs, scan_upper_exclusives, bucket_page_size,
                )
                progress.update({
                    "detection_current_model": None,
                    "detection_finished_at": finished.isoformat(),
                    "detection_elapsed_seconds": elapsed,
                    "detection_manifest_row_count": evidence["row_count"],
                    "detection_model_row_counts": evidence["model_row_counts"],
                    "detection_completion_fingerprint": evidence["fingerprint"],
                    "detection_contract_fingerprint": final_fingerprint,
                    "detection_completion_contract_version": COMPLETION_CONTRACT_VERSION,
                    "change_detection_complete": True,
                })
                progress = parse_progress_json(progress)
                updated = conn.execute(text("""
                    UPDATE ct_change_detection_run
                    SET status = 'COMPLETE', finished_at = :finished_at,
                        duration_seconds = :duration_seconds,
                        completion_contract_version = :completion_contract_version,
                        completion_fingerprint = :completion_fingerprint,
                        contract_fingerprint = :contract_fingerprint,
                        manifest_row_count = :manifest_row_count,
                        model_row_counts = CAST(:model_row_counts AS JSONB)
                    WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
                """), {
                    "run_id": run_uuid, "finished_at": finished, "duration_seconds": elapsed,
                    "completion_contract_version": COMPLETION_CONTRACT_VERSION,
                    "completion_fingerprint": evidence["fingerprint"],
                    "contract_fingerprint": final_fingerprint,
                    "manifest_row_count": evidence["row_count"],
                    "model_row_counts": json.dumps(evidence["model_row_counts"], sort_keys=True),
                })
                if updated.rowcount != 1:
                    raise ChangeDetectionError("Detection completion was superseded by another writer.")
                self._update_run_progress(conn, run_uuid, progress)
            return {
                "run_id": run_uuid, "company_id": company_id, "status": MANIFEST_COMPLETE,
                "models": list(models), "manifest_rows": sum(item.manifest_rows for item in results),
                "results": [item.__dict__ for item in results],
            }

    def _lock_candidate_and_load_inputs(self, run_id, company_id, domains, models, fingerprint):
        with self.pg.engine.begin() as conn:
            run = conn.execute(text("""
                SELECT run_id::text, company_id, status, stage, base_snapshot_run_id::text,
                       selected_domains, progress
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE
            """), {"run_id": run_id}).mappings().first()
            if not run or run["company_id"] != company_id:
                raise ChangeDetectionError("Candidate refresh run was not found for this company.")
            if run["status"] != "DETECTING_CHANGES" or run["stage"] != "DETECTING_CHANGES":
                raise ChangeDetectionError("Candidate is not at the approved detection boundary.")
            candidate_progress = parse_progress_json(run["progress"])
            if (
                candidate_progress.get("copy_forward_status") != "COMPLETE"
                or candidate_progress.get("copy_forward_candidate_run_id") != run_id
                or candidate_progress.get("copy_forward_source_run_id") != run["base_snapshot_run_id"]
            ):
                raise ChangeDetectionError("Candidate copy-forward is not durably complete.")
            if not run["base_snapshot_run_id"]:
                raise ChangeDetectionError("Candidate has no immutable base snapshot.")
            candidate_domains = run["selected_domains"] or []
            if candidate_domains != list(domains):
                raise ChangeDetectionError("Candidate selected domains do not match the detection request.")
            pointer = conn.execute(text("""
                SELECT run_id::text FROM ct_published_snapshot
                WHERE company_id = :company_id FOR UPDATE
            """), {"company_id": company_id}).scalar()
            if str(pointer) != str(run["base_snapshot_run_id"]):
                raise ChangeDetectionError("Candidate base snapshot is stale.")
            source = conn.execute(text("""
                SELECT run_id::text, company_id, status, published_at
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE
            """), {"run_id": run["base_snapshot_run_id"]}).mappings().first()
            if not source or source["company_id"] != company_id or source["status"] not in {"SUCCEEDED", "COMPLETED"} or source["published_at"] is None:
                raise ChangeDetectionError("Candidate base snapshot is not a trusted published run.")
            header = conn.execute(text("""
                SELECT status, company_id, base_snapshot_run_id::text, selected_domains, models,
                       registry_fingerprint, contract_fingerprint, watermark_inputs,
                       completion_contract_version, completion_fingerprint,
                       manifest_row_count, model_row_counts
                FROM ct_change_detection_run WHERE run_id = CAST(:run_id AS UUID) FOR UPDATE
            """), {"run_id": run_id}).mappings().first()
            expected_domains = sorted(str(item) for item in (domains or ["all"]))
            if header:
                if header["company_id"] != company_id or str(header["base_snapshot_run_id"]) != str(run["base_snapshot_run_id"]):
                    raise ChangeDetectionError("Existing detection manifest belongs to another company or base snapshot.")
                if header["selected_domains"] != expected_domains or header["models"] != list(models) or header["registry_fingerprint"] != fingerprint:
                    raise ChangeDetectionError("Existing detection manifest inputs are stale or changed.")
                return {
                    "manifest_status": header["status"],
                    "base_snapshot_run_id": str(run["base_snapshot_run_id"]),
                    "watermark_inputs": header["watermark_inputs"] or {},
                    "contract_fingerprint": header["contract_fingerprint"],
                    "completion_contract_version": header["completion_contract_version"],
                    "completion_fingerprint": header["completion_fingerprint"],
                    "manifest_row_count": header["manifest_row_count"],
                    "model_row_counts": header["model_row_counts"] or {},
                    "candidate_progress": candidate_progress,
                }
            return {
                "manifest_status": None,
                "base_snapshot_run_id": str(run["base_snapshot_run_id"]),
                "watermark_inputs": {},
                "contract_fingerprint": None,
                "completion_contract_version": None,
                "completion_fingerprint": None,
                "manifest_row_count": None,
                "model_row_counts": {},
                "candidate_progress": candidate_progress,
            }

    def _load_watermarks(self, company_id, models):
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT company_id, model, last_successful_write_date, last_successful_id,
                       overlap_seconds, published_run_id, status
                FROM ct_control_tower_watermark
                WHERE company_id = :company_id AND model = ANY(:models)
            """), {"company_id": company_id, "models": list(models)}).mappings().all()
        by_model = {row["model"]: validate_watermark_row(dict(row), company_id=company_id, model=row["model"]) for row in rows}
        for model in models:
            if model not in by_model:
                by_model[model] = {
                    "company_id": company_id, "model": model, "status": "BOOTSTRAP_REQUIRED",
                    "last_successful_write_date": None, "last_successful_id": None,
                    "overlap_seconds": 0, "published_run_id": None,
                }
        return by_model

    def _start_manifest(self, run_id, company_id, base_snapshot, domains, models, registry_fingerprint, contract_fingerprint, watermarks, started):
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ct_change_detection_run
                     (run_id, company_id, base_snapshot_run_id, selected_domains, models,
                      registry_fingerprint, contract_fingerprint, watermark_inputs, status, started_at)
                VALUES (CAST(:run_id AS UUID), :company_id, CAST(:base AS UUID),
                        CAST(:domains AS JSONB), CAST(:models AS JSONB), :fingerprint,
                        :contract_fingerprint, CAST(:watermarks AS JSONB), 'RUNNING', :started_at)
            """), {
                "run_id": run_id, "company_id": company_id, "base": base_snapshot,
                "domains": json.dumps(sorted(str(item) for item in (domains or ["all"]))),
                "models": json.dumps(list(models)), "fingerprint": registry_fingerprint,
                "contract_fingerprint": contract_fingerprint,
                "watermarks": json.dumps(watermarks, sort_keys=True), "started_at": started,
            })

    def _initial_progress(self, domains, models, started, watermarks, base_progress, contract_fingerprint, bucket_page_size):
        payload = dict(base_progress or {})
        payload.update({
            "detection_selected_domains": sorted(str(item) for item in (domains or ["all"])),
            "detection_models_planned": list(models),
            "detection_models_completed": [],
            "detection_records_scanned": 0, "detection_overlap_rows_rechecked": 0,
            "detection_newer_rows_detected": 0, "detection_duplicate_rows_removed": 0,
            "detection_manifest_rows_persisted": 0, "detection_parent_hints_identified": 0,
            "detection_configured_overlap_rows": 0,
            "detection_watermark_second_replay_rows": 0,
            "detection_genuinely_newer_rows": 0,
            "detection_started_at": started.isoformat(),
            "detection_contract_fingerprint": contract_fingerprint,
            "detection_cursor_algorithm_version": DETECTION_CURSOR_ALGORITHM_VERSION,
            "detection_bucket_page_size": bucket_page_size,
            "detection_watermarks": {
                model: {
                    "write_date": watermark_displayed_second(row["last_successful_write_date"]).isoformat(),
                    "id": row["last_successful_id"],
                    "overlap_seconds": row["overlap_seconds"],
                } for model, row in watermarks.items()
            },
            "detection_overlap_lower_bounds": {
                model: (watermark_displayed_second(row["last_successful_write_date"]) - timedelta(seconds=row["overlap_seconds"])).isoformat()
                for model, row in watermarks.items()
            },
            "detection_replay_start_seconds": {
                model: (watermark_displayed_second(row["last_successful_write_date"]) - timedelta(seconds=row["overlap_seconds"])).isoformat()
                for model, row in watermarks.items()
            },
            "detection_scan_upper_exclusives": {},
        })
        return parse_progress_json(payload)

    def _detect_model(self, entry, company_id, watermark, odoo_client, bucket_page_size=DETECTION_BUCKET_PAGE_SIZE):
        fields = _detection_fields(entry)
        watermark_second = watermark_displayed_second(watermark["last_successful_write_date"])
        replay_start_second = watermark_second - timedelta(seconds=watermark["overlap_seconds"])
        parent_field_map = {
            rel.parent_field: rel.parent_model
            for rel in entry.parent_children
            if rel.child_model == entry.model_key
        }
        scan_upper_exclusive = _capture_scan_upper_exclusive(
            odoo_client, entry.model_key, company_id, replay_start_second, fields,
        )
        unique: dict[int, dict[str, Any]] = {}
        duplicates = scanned = configured = watermark_replay = newer = parents = 0
        if scan_upper_exclusive is not None:
            probe_second = replay_start_second
            while probe_second < scan_upper_exclusive:
                bucket_second = _locate_next_bucket(
                    odoo_client, entry.model_key, company_id, probe_second, scan_upper_exclusive, fields,
                )
                if bucket_second is None:
                    break
                if bucket_second < replay_start_second or bucket_second >= scan_upper_exclusive:
                    raise ChangeDetectionError(
                        f"Odoo bucket probe left the approved scan window for {entry.model_key}."
                    )
                cursor = 0
                while True:
                    page = _scan_bucket_page(
                        odoo_client, entry.model_key, company_id, bucket_second, cursor, fields, bucket_page_size,
                    )
                    if not page:
                        break
                    page_ids: list[int] = []
                    for record in page:
                        record_id, source_date, hints = _parse_detection_row(
                            record, entry.model_key, fields, company_id, parent_field_map,
                        )
                        page_ids.append(record_id)
                        scanned += 1
                        if source_date != bucket_second:
                            raise ChangeDetectionError(
                                f"Odoo returned a row outside its second bucket for {entry.model_key}/{record_id}."
                            )
                        previous = unique.get(record_id)
                        if previous:
                            if previous["source_write_date"] != source_date or previous["parent_hints"] != hints:
                                raise ChangeDetectionError(
                                    f"Duplicate Odoo ID has conflicting detection metadata: {entry.model_key}/{record_id}."
                                )
                            duplicates += 1
                            continue
                        unique[record_id] = {
                            "source_write_date": source_date, "parent_hints": hints,
                        }
                    cursor = page_ids[-1]
                    if len(page) < bucket_page_size:
                        break
                probe_second = bucket_second + timedelta(seconds=1)
        ordered = sorted(unique.items(), key=lambda item: (item[1]["source_write_date"], item[0]))
        rows = []
        overlap = 0
        for sequence, (record_id, value) in enumerate(ordered, start=1):
            if value["source_write_date"] < watermark_second:
                configured += 1
                overlap += 1
            elif value["source_write_date"] == watermark_second:
                watermark_replay += 1
                overlap += 1
            else:
                newer += 1
            hints = value["parent_hints"]
            parents += len(hints)
            first = hints[0] if hints else {}
            rows.append({
                "record_id": record_id, "source_write_date": value["source_write_date"],
                "parent_model": first.get("parent_model"), "parent_record_id": first.get("parent_record_id"),
                "parent_hints": hints, "from_overlap": value["source_write_date"] <= watermark_second,
                "detection_sequence": sequence,
            })
        result = DetectionModelResult(
            entry.model_key, scanned, overlap, newer, duplicates, len(rows), parents,
            configured_overlap_rows=configured,
            watermark_second_replay_rows=watermark_replay,
            genuinely_newer_rows=newer,
        )
        return result, rows, {
            "replay_start_second": replay_start_second,
            "scan_upper_exclusive": scan_upper_exclusive,
        }

    def _persist_model(self, run_id, company_id, entry, rows, result, progress, timestamp):
        with self.pg.engine.begin() as conn:
            for row in rows:
                conn.execute(text("""
                    INSERT INTO ct_change_manifest
                        (run_id, company_id, business_domains, model, record_id,
                         source_write_date, parent_model, parent_record_id, parent_hints,
                         from_overlap, detection_sequence, detected_at, status)
                    VALUES (CAST(:run_id AS UUID), :company_id, CAST(:domains AS JSONB), :model,
                            :record_id, :source_write_date, :parent_model, :parent_record_id,
                            CAST(:parent_hints AS JSONB), :from_overlap, :sequence, :detected_at, :status)
                """), {
                    "run_id": run_id, "company_id": company_id, "domains": json.dumps(list(entry.domain_keys)),
                    "model": entry.model_key, **row, "sequence": row["detection_sequence"], "parent_hints": json.dumps(row["parent_hints"]),
                    "status": DETECTION_STATUS, "detected_at": timestamp,
                })
            self._update_run_progress(conn, run_id, progress)

    @staticmethod
    def _progress_after_model(progress, model, result, scan, timestamp):
        progress = dict(progress)
        completed = list(progress.get("detection_models_completed", []))
        if model not in completed:
            completed.append(model)
        scan_upper_exclusives = dict(progress.get("detection_scan_upper_exclusives", {}))
        scan_upper_exclusives[model] = (
            scan["scan_upper_exclusive"].isoformat() if scan["scan_upper_exclusive"] is not None else None
        )
        replay_start_seconds = dict(progress.get("detection_replay_start_seconds", {}))
        replay_start_seconds[model] = scan["replay_start_second"].isoformat()
        progress.update({
            "detection_current_model": model,
            "detection_models_completed": completed,
            "detection_records_scanned": progress.get("detection_records_scanned", 0) + result.scanned,
            "detection_overlap_rows_rechecked": progress.get("detection_overlap_rows_rechecked", 0) + result.overlap_rechecked,
            "detection_newer_rows_detected": progress.get("detection_newer_rows_detected", 0) + result.newer_detected,
            "detection_duplicate_rows_removed": progress.get("detection_duplicate_rows_removed", 0) + result.duplicates_removed,
            "detection_manifest_rows_persisted": progress.get("detection_manifest_rows_persisted", 0) + result.manifest_rows,
            "detection_parent_hints_identified": progress.get("detection_parent_hints_identified", 0) + result.parent_hints,
            "detection_configured_overlap_rows": progress.get("detection_configured_overlap_rows", 0) + result.configured_overlap_rows,
            "detection_watermark_second_replay_rows": progress.get("detection_watermark_second_replay_rows", 0) + result.watermark_second_replay_rows,
            "detection_genuinely_newer_rows": progress.get("detection_genuinely_newer_rows", 0) + result.genuinely_newer_rows,
            "detection_scan_upper_exclusives": scan_upper_exclusives,
            "detection_replay_start_seconds": replay_start_seconds,
            "detection_model_completed_at": {**progress.get("detection_model_completed_at", {}), model: timestamp.isoformat()},
        })
        return parse_progress_json(progress)

    def _write_progress(self, run_id, progress):
        with self.pg.engine.begin() as conn:
            self._update_run_progress(conn, run_id, progress)

    @staticmethod
    def _update_run_progress(conn, run_id, progress):
        updated = conn.execute(text("""
            UPDATE ct_extraction_run SET progress = CAST(:progress AS JSONB),
                heartbeat_at = :now
            WHERE run_id = CAST(:run_id AS UUID) AND status = 'DETECTING_CHANGES'
              AND COALESCE((progress->>'change_detection_complete')::boolean, FALSE) = FALSE
        """), {"run_id": run_id, "progress": serialize_progress(progress), "now": datetime.now(timezone.utc)})
        if updated.rowcount != 1:
            raise ChangeDetectionError("Detection progress is no longer writable after authoritative completion.")

    def _idempotent_result(self, run_id, inputs, company_id, models, entries, domains, contract_fingerprint, watermarks, bucket_page_size):
        progress = inputs["candidate_progress"]
        if not progress.get("change_detection_complete"):
            raise ChangeDetectionError("Completed manifest lacks a trusted completion progress marker.")
        if progress.get("detection_models_planned") != list(models) or progress.get("detection_models_completed") != list(models):
            raise ChangeDetectionError("Completed manifest progress does not contain every planned model.")
        if progress.get("detection_cursor_algorithm_version") != DETECTION_CURSOR_ALGORITHM_VERSION:
            raise ChangeDetectionError("Completed manifest cursor algorithm version changed.")
        if progress.get("detection_bucket_page_size") != bucket_page_size:
            raise ChangeDetectionError("Completed manifest bucket page size changed.")
        expected_replay_starts = {
            model: (watermark_displayed_second(row["last_successful_write_date"]) - timedelta(seconds=row["overlap_seconds"])).isoformat()
            for model, row in sorted(watermarks.items())
        }
        if progress.get("detection_replay_start_seconds") != expected_replay_starts:
            raise ChangeDetectionError("Completed manifest replay start changed.")
        if progress.get("detection_contract_fingerprint") != contract_fingerprint:
            raise ChangeDetectionError("Completed manifest progress contract fingerprint does not match.")
        if inputs["contract_fingerprint"] != contract_fingerprint:
            raise ChangeDetectionError("Completed manifest header contract fingerprint does not match.")
        if inputs["completion_contract_version"] != COMPLETION_CONTRACT_VERSION:
            raise ChangeDetectionError("Completed manifest evidence version is missing or unsupported.")
        with self.pg.engine.begin() as conn:
            manifest_rows = conn.execute(text("""
                SELECT company_id, business_domains, model, record_id, source_write_date,
                       parent_model, parent_record_id, parent_hints, from_overlap,
                       detection_sequence, detected_at, status
                FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, detection_sequence, record_id
                FOR UPDATE
            """), {"run_id": run_id}).mappings().all()
            evidence = _manifest_evidence([dict(row) for row in manifest_rows], models)
            expected_domains = {entry.model_key: list(entry.domain_keys) for entry in entries}
            for row in manifest_rows:
                if row["company_id"] != company_id or row["business_domains"] != expected_domains[row["model"]]:
                    raise ChangeDetectionError("Completed manifest company or domain metadata changed.")
            if evidence["row_count"] != inputs["manifest_row_count"]:
                raise ChangeDetectionError("Completed manifest row count changed.")
            if evidence["model_row_counts"] != (inputs["model_row_counts"] or {}):
                raise ChangeDetectionError("Completed manifest model row counts changed.")
            if evidence["fingerprint"] != inputs["completion_fingerprint"]:
                raise ChangeDetectionError("Completed manifest fingerprint changed.")
            if evidence["fingerprint"] != progress.get("detection_completion_fingerprint"):
                raise ChangeDetectionError("Completed manifest progress fingerprint changed.")
            if progress.get("detection_manifest_row_count") != evidence["row_count"]:
                raise ChangeDetectionError("Completed manifest progress row count changed.")
            if progress.get("detection_model_row_counts") != evidence["model_row_counts"]:
                raise ChangeDetectionError("Completed manifest progress model counts changed.")
        return {
            "run_id": run_id, "company_id": company_id, "status": MANIFEST_COMPLETE,
            "idempotent": True, "manifest_rows": evidence["row_count"],
            "models": list(models),
        }
