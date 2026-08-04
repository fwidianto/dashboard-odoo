"""Read-only incremental change detection for the Control Tower boundary."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import text

from src.control_tower.contracts import ModelExecutionContract, resolve_domain_selection, resolve_execution_entries
from src.control_tower.progress import parse_progress_json, serialize_progress
from src.control_tower.refresh import REFRESH_LOCK_KEY
from src.control_tower.schema_guard import ensure_phase8_detection_schema_ready
from src.control_tower.watermarks import normalize_utc, validate_watermark_row
from src.control_tower.relation_extractor import MODEL_SPECS

DETECTION_STATUS = "DETECTED"
MANIFEST_COMPLETE = "COMPLETE"
MANIFEST_RUNNING = "RUNNING"
COMPLETION_CONTRACT_VERSION = "ct-change-manifest-v1"


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
            "write_date": row["last_successful_write_date"].isoformat(),
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
) -> str:
    value = {
        "version": "ct-detection-contract-v1",
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


def _incremental_domain(company_id: int, write_date: datetime, record_id: int, overlap_seconds: int) -> list[Any]:
    date_value = write_date.isoformat()
    company = ("company_id", "=", company_id)
    if overlap_seconds:
        return ["&", company, ("write_date", ">=", (write_date - timedelta(seconds=overlap_seconds)).isoformat())]
    return [
        "&", company, "|",
        ("write_date", ">", date_value),
        "&", ("write_date", "=", date_value), ("id", ">", record_id),
    ]


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
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            run_uuid = str(UUID(str(run_id)))
        except (TypeError, ValueError) as exc:
            raise ChangeDetectionError("Refresh run ID must be a UUID.") from exc
        if isinstance(company_id, bool) or not isinstance(company_id, int) or company_id <= 0:
            raise ChangeDetectionError("Company ID must be a positive integer.")
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
                if inputs["contract_fingerprint"] != contract_fingerprint:
                    raise ChangeDetectionError("Completed change manifest contract inputs changed.")
                return self._idempotent_result(
                    run_uuid, inputs, company_id, models, entries, resolved_domains, contract_fingerprint,
                )
            if inputs["manifest_status"] == MANIFEST_RUNNING:
                raise ChangeDetectionError("A partial change manifest cannot be silently reused.")
            self._start_manifest(
                run_uuid, company_id, inputs["base_snapshot_run_id"], resolved_domains,
                models, registry_fingerprint, contract_fingerprint, watermark_inputs, timestamp,
            )
            progress = self._initial_progress(
                resolved_domains, models, timestamp, watermarks,
                inputs["candidate_progress"], contract_fingerprint,
            )
            self._write_progress(run_uuid, progress)

            results: list[DetectionModelResult] = []
            for entry in entries:
                result, rows = self._detect_model(
                    entry, company_id, watermarks[entry.model_key], odoo_client,
                )
                progress = self._progress_after_model(progress, entry.model_key, result, timestamp)
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
                progress.update({
                    "detection_current_model": None,
                    "detection_finished_at": finished.isoformat(),
                    "detection_elapsed_seconds": elapsed,
                    "detection_manifest_row_count": evidence["row_count"],
                    "detection_model_row_counts": evidence["model_row_counts"],
                    "detection_completion_fingerprint": evidence["fingerprint"],
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
                        manifest_row_count = :manifest_row_count,
                        model_row_counts = CAST(:model_row_counts AS JSONB)
                    WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
                """), {
                    "run_id": run_uuid, "finished_at": finished, "duration_seconds": elapsed,
                    "completion_contract_version": COMPLETION_CONTRACT_VERSION,
                    "completion_fingerprint": evidence["fingerprint"],
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

    def _initial_progress(self, domains, models, started, watermarks, base_progress, contract_fingerprint):
        payload = dict(base_progress or {})
        payload.update({
            "detection_selected_domains": sorted(str(item) for item in (domains or ["all"])),
            "detection_models_planned": list(models),
            "detection_models_completed": [],
            "detection_records_scanned": 0, "detection_overlap_rows_rechecked": 0,
            "detection_newer_rows_detected": 0, "detection_duplicate_rows_removed": 0,
            "detection_manifest_rows_persisted": 0, "detection_parent_hints_identified": 0,
            "detection_started_at": started.isoformat(),
            "detection_contract_fingerprint": contract_fingerprint,
            "detection_watermarks": {
                model: {
                    "write_date": row["last_successful_write_date"].isoformat(),
                    "id": row["last_successful_id"],
                    "overlap_seconds": row["overlap_seconds"],
                } for model, row in watermarks.items()
            },
            "detection_overlap_lower_bounds": {
                model: (row["last_successful_write_date"] - timedelta(seconds=row["overlap_seconds"])).isoformat()
                if row["overlap_seconds"] else row["last_successful_write_date"].isoformat()
                for model, row in watermarks.items()
            },
        })
        return parse_progress_json(payload)

    def _detect_model(self, entry, company_id, watermark, odoo_client):
        fields = _detection_fields(entry)
        domain = _incremental_domain(company_id, watermark["last_successful_write_date"], watermark["last_successful_id"], watermark["overlap_seconds"])
        overlap_lower_bound = watermark["last_successful_write_date"] - timedelta(seconds=watermark["overlap_seconds"])
        required_fields = {"id", "write_date", "company_id"}
        records = odoo_client.search_read(entry.model_key, domain, fields=list(fields), order="write_date asc, id asc")
        if not isinstance(records, list):
            raise ChangeDetectionError(f"Odoo search_read returned a non-list for {entry.model_key}.")
        unique = {}
        duplicates = 0
        for record in records:
            if not isinstance(record, Mapping):
                raise ChangeDetectionError("Odoo detection response contained a non-object row.")
            unexpected = set(record) - set(fields)
            if unexpected:
                raise ChangeDetectionError(f"Odoo detection response contained unexpected fields: {sorted(unexpected)}")
            missing = required_fields - set(record)
            if missing:
                raise ChangeDetectionError(f"Odoo detection response omitted required fields: {sorted(missing)}")
            record_id = _positive_id(record.get("id"), f"{entry.model_key}.id")
            source_date = _utc(record.get("write_date"))
            company = _relation_id(record.get("company_id"), f"{entry.model_key}.company_id")
            if company != company_id:
                raise ChangeDetectionError(f"Odoo detection response crossed company scope for {entry.model_key}.")
            parent_hints = []
            for relation in sorted((rel for rel in entry.parent_children if rel.child_model == entry.model_key), key=lambda rel: (rel.parent_model, rel.parent_field)):
                parent_id = _relation_id(record.get(relation.parent_field), f"{entry.model_key}.{relation.parent_field}")
                if parent_id is not None:
                    parent_hints.append({"parent_model": relation.parent_model, "parent_record_id": parent_id, "field": relation.parent_field})
            previous = unique.get(record_id)
            if previous:
                if previous["source_write_date"] != source_date or previous["parent_hints"] != parent_hints:
                    raise ChangeDetectionError(f"Duplicate Odoo ID has conflicting detection metadata: {entry.model_key}/{record_id}.")
                duplicates += 1
                continue
            unique[record_id] = {
                "source_write_date": source_date, "parent_hints": parent_hints,
                "from_overlap": (source_date, record_id) <= (watermark["last_successful_write_date"], watermark["last_successful_id"]),
            }
        ordered = sorted(unique.items(), key=lambda item: (item[1]["source_write_date"], item[0]))
        rows = []
        overlap = newer = parents = 0
        for sequence, (record_id, value) in enumerate(ordered, start=1):
            tuple_value = (value["source_write_date"], record_id)
            watermark_tuple = (watermark["last_successful_write_date"], watermark["last_successful_id"])
            if watermark["overlap_seconds"]:
                if value["source_write_date"] < overlap_lower_bound:
                    raise ChangeDetectionError(f"Odoo returned a row below the overlap boundary for {entry.model_key}/{record_id}.")
            elif tuple_value <= watermark_tuple:
                raise ChangeDetectionError(f"Odoo returned a row outside the incremental boundary for {entry.model_key}/{record_id}.")
            hints = value["parent_hints"]
            if value["from_overlap"]:
                overlap += 1
            else:
                newer += 1
            parents += len(hints)
            first = hints[0] if hints else {}
            rows.append({
                "record_id": record_id, "source_write_date": value["source_write_date"],
                "parent_model": first.get("parent_model"), "parent_record_id": first.get("parent_record_id"),
                "parent_hints": hints, "from_overlap": value["from_overlap"],
                "detection_sequence": sequence,
            })
        result = DetectionModelResult(entry.model_key, len(records), overlap, newer, duplicates, len(rows), parents)
        return result, rows

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
    def _progress_after_model(progress, model, result, timestamp):
        progress = dict(progress)
        completed = list(progress.get("detection_models_completed", []))
        if model not in completed:
            completed.append(model)
        progress.update({
            "detection_current_model": model,
            "detection_models_completed": completed,
            "detection_records_scanned": progress.get("detection_records_scanned", 0) + result.scanned,
            "detection_overlap_rows_rechecked": progress.get("detection_overlap_rows_rechecked", 0) + result.overlap_rechecked,
            "detection_newer_rows_detected": progress.get("detection_newer_rows_detected", 0) + result.newer_detected,
            "detection_duplicate_rows_removed": progress.get("detection_duplicate_rows_removed", 0) + result.duplicates_removed,
            "detection_manifest_rows_persisted": progress.get("detection_manifest_rows_persisted", 0) + result.manifest_rows,
            "detection_parent_hints_identified": progress.get("detection_parent_hints_identified", 0) + result.parent_hints,
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

    def _idempotent_result(self, run_id, inputs, company_id, models, entries, domains, contract_fingerprint):
        progress = inputs["candidate_progress"]
        if not progress.get("change_detection_complete"):
            raise ChangeDetectionError("Completed manifest lacks a trusted completion progress marker.")
        if progress.get("detection_models_planned") != list(models) or progress.get("detection_models_completed") != list(models):
            raise ChangeDetectionError("Completed manifest progress does not contain every planned model.")
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
