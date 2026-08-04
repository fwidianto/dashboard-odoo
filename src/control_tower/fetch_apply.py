"""Phase 8C-2 bounded full-record fetch and deterministic candidate apply.

The service consumes a completed change manifest, fetches approved full
payloads for the detected records using read-only Odoo ``search_read`` calls,
normalizes and validates each payload against the approved extractor
contract, persists durable fetch/apply evidence, applies deterministic
inserts/updates/unchanged results to the copied candidate snapshot, and
transitions the run from ``FETCHING`` to ``RECONCILING``.

It reuses the approved stage contracts and never duplicates detection,
copy-forward, extractor, or orchestrator logic.  No reconciliation,
publication, watermark movement, finding regeneration, or worker is created.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Mapping, Optional
from uuid import UUID

from sqlalchemy import text

from src.control_tower.change_detection import parse_odoo_write_date
from src.control_tower.change_detection import IncrementalChangeDetectionService
from src.control_tower.contracts import resolve_domain_selection
from src.control_tower.progress import parse_progress_json, serialize_progress
from src.control_tower.refresh import REFRESH_LOCK_KEY
from src.control_tower.refresh_state import validate_transition
from src.control_tower.relation_extractor import LINK_SPECS, MODEL_SPECS, normalize_value
from src.control_tower.schema_guard import ensure_phase8_fetch_schema_ready

FETCH_APPLY_CONTRACT_VERSION = "ct-fetch-apply-v1"
FETCH_APPLY_BATCH_SIZE = 500
FETCH_STATUS_FETCHED = "FETCHED"
FETCH_STATUS_MISSING = "MISSING_AT_FETCH"
APPLY_INSERTED = "INSERTED"
APPLY_UPDATED = "UPDATED"
APPLY_UNCHANGED = "UNCHANGED"


class FetchApplyError(ValueError):
    """Raised when fetch/apply cannot safely proceed."""

    def __init__(self, message: str, *, requires_new_retry: bool = False) -> None:
        super().__init__(message)
        self.requires_new_retry = requires_new_retry


def _utc(value: Optional[datetime]) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise FetchApplyError("Fetch/apply timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _positive_id(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FetchApplyError(f"{label} must be a positive integer.")
    return value


def _relation_id(value: Any, label: str) -> int:
    if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int) and value[0] > 0:
        return value[0]
    raise FetchApplyError(f"{label} must be a many2one pair.")


def _relation_name(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return str(value[1]) if value[1] not in (None, False, "") else None
    return None


def _jsonb_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _document_number(normalized: Mapping[str, Any], model: str) -> Optional[str]:
    for field in ("name", "display_name"):
        value = normalized.get(field)
        if value not in (None, False, ""):
            return str(value)
    return None


def _state_value(normalized: Mapping[str, Any]) -> Optional[str]:
    for field in ("state", "request_status", "x_studio_status"):
        value = normalized.get(field)
        if value not in (None, False, ""):
            return str(value)
    return None


def _code_side_field_contract_fingerprint(models: list[str], batch_size: int) -> str:
    """Deterministic fingerprint of the code-side payload allowlist contract.

    Covers ordered resolved models, approved ordered field names from
    MODEL_SPECS, and the batch size.  No Odoo access is required.
    """
    value = {
        "version": FETCH_APPLY_CONTRACT_VERSION,
        "models": [
            {"model": model, "fields": list(_build_field_contract(model))}
            for model in models
        ],
        "batch_size": batch_size,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _relation_target(model: str, field: str) -> Optional[str]:
    for spec in LINK_SPECS:
        if spec.field_owner_model == model and spec.source_field == field:
            return spec.related_model
    return None


def _validated_field_metadata(
    model: str, metadata: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate that every approved field has a trusted metadata definition.

    Returns a canonical per-field metadata map.  Missing definitions, blank
    field types, and relational fields without a relation target are rejected.
    Display names are never treated as schema evidence.
    """
    if not isinstance(metadata, Mapping):
        raise FetchApplyError(f"Odoo model metadata is malformed for {model}.")
    validated: dict[str, dict[str, Any]] = {}
    for field in _build_field_contract(model):
        field_def = metadata.get(field)
        if not isinstance(field_def, Mapping):
            raise FetchApplyError(
                f"Odoo model metadata is missing a definition for approved field {model}.{field}."
            )
        field_def = dict(field_def)
        field_type = field_def.get("type")
        if not isinstance(field_type, str) or not field_type.strip():
            raise FetchApplyError(
                f"Odoo model metadata has a blank or malformed field type for {model}.{field}."
            )
        field_type = field_type.strip()
        relation = field_def.get("relation")
        if field_type in {"many2one", "many2many", "one2many"}:
            if not isinstance(relation, str) or not relation.strip():
                raise FetchApplyError(
                    f"Relational field {model}.{field} lacks a trusted relation target."
                )
            validated[field] = {
                "type": field_type,
                "relation": relation.strip(),
            }
        else:
            validated[field] = {"type": field_type, "relation": None}
    return validated


def _full_field_contract_fingerprint(
    models: list[str], batch_size: int,
    metadata_by_model: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> str:
    """Deterministic fingerprint including trusted metadata normalization inputs.

    Binds, for every approved field, the exact field name, exact field type,
    and the exact metadata relation target (not LINK_SPECS truthiness).
    """
    value = {
        "version": FETCH_APPLY_CONTRACT_VERSION,
        "models": [],
        "batch_size": batch_size,
    }
    for model in models:
        validated = _validated_field_metadata(
            model, dict(metadata_by_model.get(model) or {})
        )
        fields = []
        for field in _build_field_contract(model):
            field_def = validated[field]
            fields.append({
                "field": field,
                "type": field_def["type"],
                "relation_target": field_def["relation"],
            })
        value["models"].append({"model": model, "fields": fields})
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
def _build_field_contract(model: str) -> tuple[str, ...]:
    spec = next(spec for spec in MODEL_SPECS if spec.model == model)
    required = {"id", "write_date"}
    if not required.issubset(spec.fields):
        raise FetchApplyError(f"Approved snapshot fields are incomplete for {model}.")
    return tuple(dict.fromkeys(spec.fields))


def _normalize_record(
    record: Mapping[str, Any], model: str, company_id: int,
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize one full payload using the shared extractor contract.

    Field types come from trusted Odoo model metadata (``get_model_fields``)
    and normalization reuses ``normalize_value`` so payloads match existing
    snapshots exactly.  Display names remain non-authoritative.
    """
    if not isinstance(record, Mapping):
        raise FetchApplyError(f"Odoo fetch response contained a non-object row for {model}.")
    fields = _build_field_contract(model)
    unexpected = set(record) - set(fields)
    if unexpected:
        raise FetchApplyError(f"Odoo fetch response contained unexpected fields for {model}: {sorted(unexpected)}")
    missing = set(fields) - set(record)
    if missing:
        raise FetchApplyError(f"Odoo fetch response omitted approved fields for {model}: {sorted(missing)}")
    normalized: dict[str, Any] = {}
    for field in fields:
        field_def = dict(metadata.get(field) or {})
        field_type = field_def.get("type") if isinstance(field_def, Mapping) else None
        value = record[field]
        if field_type == "many2one":
            if value is False:
                value = None
            if value is not None:
                pair = value if isinstance(value, (list, tuple)) else None
                if not pair or len(pair) != 2 or isinstance(pair[0], bool) or not isinstance(pair[0], int) or pair[0] <= 0:
                    raise FetchApplyError(f"{model}.{field} must be a valid many2one pair.")
            normalized[field] = normalize_value(value, field_def)
        elif field_type in {"many2many", "one2many"}:
            if value is False:
                normalized[field] = []
            elif not isinstance(value, list) or not all(
                isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
            ):
                raise FetchApplyError(f"{model}.{field} must be a positive integer list.")
            else:
                normalized[field] = normalize_value(value, field_def)
        else:
            normalized[field] = normalize_value(value, field_def)
    record_id = _positive_id(normalized["id"], f"{model}.id")
    company = normalized.get("company_id")
    if not isinstance(company, Mapping) or not isinstance(company.get("id"), int):
        raise FetchApplyError(f"Odoo fetch response is missing company scope for {model}/{record_id}.")
    if company["id"] != company_id:
        raise FetchApplyError(
            f"Odoo fetch response crossed company scope for {model}/{record_id}."
        )
    try:
        write_date = parse_odoo_write_date(record["write_date"])
    except Exception as exc:
        raise FetchApplyError(f"Odoo fetch write_date is malformed for {model}/{record_id}: {exc}") from exc
    normalized["write_date"] = write_date
    return {
        "model": model,
        "record_id": record_id,
        "document_number": _document_number(normalized, model),
        "state": _state_value(normalized),
        "company_id": company["id"],
        "company_name": company.get("name"),
        "write_date": write_date,
        "payload": normalized,
    }

def _canonical_payload(row: Mapping[str, Any]) -> str:
    payload = dict(row["payload"])
    payload["write_date"] = payload["write_date"].isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


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
            raise FetchApplyError("A Control Tower refresh is already running.")
        yield
    finally:
        if locked:
            connection.execute(
                text("SELECT pg_advisory_unlock(CAST(:lock_key AS BIGINT))"),
                {"lock_key": REFRESH_LOCK_KEY},
            )
            connection.commit()
        connection.close()


class FetchApplyService:
    """Fetch full detected records and apply deterministic candidate deltas."""

    def __init__(
        self,
        postgres_client,
        *,
        schema_guard=ensure_phase8_fetch_schema_ready,
        hooks: Optional[Mapping[str, Callable[[str], None]]] = None,
        batch_size: int = FETCH_APPLY_BATCH_SIZE,
    ) -> None:
        self.pg = postgres_client
        self._hooks = dict(hooks or {})
        self._batch_size = batch_size
        self._detection = IncrementalChangeDetectionService(postgres_client, schema_guard=ensure_phase8_fetch_schema_ready)
        self._metadata_cache: dict[str, Mapping[str, Mapping[str, Any]]] = {}
        schema_guard(postgres_client)

    def _fire(self, name: str) -> None:
        hook = self._hooks.get(name)
        if hook is not None:
            hook(name)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        try:
            return str(UUID(str(run_id)))
        except (TypeError, ValueError) as exc:
            raise FetchApplyError("Refresh run ID must be a valid UUID.") from exc

    def run(self, *, run_id: str, company_id: int, odoo_client, now: Optional[datetime] = None) -> dict[str, Any]:
        """Fetch and apply detected records, then transition to RECONCILING."""
        run_uuid = self._validate_run_id(run_id)
        _positive_id(company_id, "Company ID")
        if isinstance(self._batch_size, bool) or not isinstance(self._batch_size, int) or self._batch_size <= 0:
            raise FetchApplyError("Fetch batch size must be a positive integer.")
        timestamp = _utc(now)
        with _refresh_lock(self.pg):
            with self.pg.engine.begin() as conn:
                run = conn.execute(text("""
                    SELECT run_id::text, company_id, status, stage,
                           base_snapshot_run_id::text, selected_domains, progress
                    FROM ct_extraction_run
                    WHERE run_id = CAST(:run_id AS UUID)
                    FOR UPDATE
                """), {"run_id": run_uuid}).mappings().first()
                if not run or int(run["company_id"]) != company_id:
                    raise FetchApplyError("Refresh run was not found for this company.")
                if run["status"] not in {"FETCHING", "RECONCILING"}:
                    raise FetchApplyError(f"Refresh run is {run['status']}, not FETCHING.")
                if run["stage"] != run["status"]:
                    raise FetchApplyError(f"Refresh run stage is {run['stage']}, not {run['status']}.")
                progress = parse_progress_json(run["progress"])
                if not progress.get("fetch_apply_complete") and run["status"] != "FETCHING":
                    raise FetchApplyError(
                        f"Refresh run is {run['status']} without complete fetch/apply evidence."
                    )
            self._validate_pointer(run_uuid, company_id, run["base_snapshot_run_id"])
            if progress.get("fetch_apply_complete"):
                header = self._header(run_uuid)
                if header is None or header["status"] != "COMPLETE":
                    raise FetchApplyError(
                        "Fetch/apply progress claims completion without a durable complete header.",
                        requires_new_retry=True,
                    )
                return self._validate_completed(run_uuid, company_id, run["base_snapshot_run_id"], header, idempotent=True)

            self._validate_pointer(run_uuid, company_id, run["base_snapshot_run_id"])
            detection = self._detection_inputs(run_uuid, company_id, run["base_snapshot_run_id"], run["selected_domains"])
            if detection["manifest_row_count"] == 0:
                raise FetchApplyError("FETCHING requires a non-empty completed manifest.")
            self._ensure_no_contradictory_evidence(
                run_uuid, company_id, run["base_snapshot_run_id"], run["selected_domains"], detection,
            )
            header = self._load_or_create_header(
                run_uuid, company_id, run["base_snapshot_run_id"],
                run["selected_domains"], detection, timestamp,
            )
            progress = self._ensure_fetch_apply(header, progress, timestamp, odoo_client)
            return self._finalize(run_uuid, company_id, header, progress, timestamp, detection, idempotent=False)

    def _header(self, run_uuid: str) -> Optional[dict[str, Any]]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT run_id::text, company_id, base_snapshot_run_id::text,
                       selected_domains, models, manifest_completion_fingerprint,
                       manifest_row_count, batch_size, contract_version,
                       field_contract_version, field_contract_fingerprint,
                       field_contract_allowlist_fingerprint,
                       status, started_at, finished_at, duration_seconds,
                       completion_fingerprint, model_fetch_counts
                FROM ct_fetch_apply_run
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().first()
        return dict(row) if row else None

    def _validate_pointer(self, run_uuid: str, company_id: int, base_snapshot: Any) -> None:
        with self.pg.engine.connect() as conn:
            pointer = conn.execute(text("""
                SELECT run_id::text FROM ct_published_snapshot
                WHERE company_id = :company_id
            """), {"company_id": company_id}).scalar()
        if not base_snapshot or str(base_snapshot) != str(pointer):
            raise FetchApplyError(
                "Candidate base snapshot is stale or the published pointer changed."
            )

    def _detection_inputs(self, run_uuid: str, company_id: int, base_snapshot: Any, selected_domains: Any) -> dict[str, Any]:
        try:
            return self._detection.validate_completed_manifest(
                run_id=run_uuid, company_id=company_id, selected_domains=selected_domains,
                lock_held=True,
            )
        except Exception as exc:
            raise FetchApplyError(
                f"Completed change detection validation failed: {exc}",
                requires_new_retry=True,
            ) from exc

    def _validate_header_immutables(
        self, header: dict[str, Any], company_id: int, base_snapshot: Any,
        run_selected_domains: Any, detection: dict[str, Any],
        *, expect_complete: Optional[bool] = None,
    ) -> None:
        expected_domains = sorted(str(domain.key) for domain in resolve_domain_selection(run_selected_domains))
        code_side = _code_side_field_contract_fingerprint(
            list(detection["models"]), int(header["batch_size"]),
        )
        if (
            int(header["company_id"]) != company_id
            or str(header["base_snapshot_run_id"]) != str(base_snapshot)
            or list(header["selected_domains"]) != expected_domains
            or list(header["models"]) != list(detection["models"])
            or header["manifest_completion_fingerprint"] != detection["manifest_completion_fingerprint"]
            or int(header["manifest_row_count"]) != int(detection["manifest_row_count"])
            or int(header["batch_size"]) != self._batch_size
            or header["contract_version"] != FETCH_APPLY_CONTRACT_VERSION
            or header.get("field_contract_version") != FETCH_APPLY_CONTRACT_VERSION
            or header.get("field_contract_allowlist_fingerprint") != code_side
            or (header["status"] == "COMPLETE" and not header.get("field_contract_fingerprint"))
        ):
            raise FetchApplyError(
                "Fetch/apply header immutable inputs contradict the run, manifest, or field contract.",
                requires_new_retry=True,
            )
        if expect_complete is not None and (header["status"] == "COMPLETE") != expect_complete:
            raise FetchApplyError(
                "Fetch/apply header status contradicts the expected lifecycle state.",
                requires_new_retry=True,
            )

    def _ensure_no_contradictory_evidence(
        self, run_uuid: str, company_id: int, base_snapshot: Any,
        run_selected_domains: Any, detection: dict[str, Any],
    ) -> None:
        with self.pg.engine.connect() as conn:
            header = conn.execute(text("""
                SELECT run_id::text, company_id, base_snapshot_run_id::text,
                       selected_domains, models, manifest_completion_fingerprint,
                       manifest_row_count, batch_size, contract_version,
                       field_contract_version, field_contract_fingerprint,
                       field_contract_allowlist_fingerprint, status
                FROM ct_fetch_apply_run WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().first()
        if header is None:
            return
        self._validate_header_immutables(
            header, company_id, base_snapshot, run_selected_domains, detection,
            expect_complete=False,
        )

    def _load_or_create_header(
        self, run_uuid: str, company_id: int, base_snapshot: Any,
        selected_domains: Any, detection: dict[str, Any], timestamp: datetime,
    ) -> dict[str, Any]:
        resolved_domains = sorted(str(domain.key) for domain in resolve_domain_selection(selected_domains))
        code_side = _code_side_field_contract_fingerprint(
            list(detection["models"]), self._batch_size,
        )
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ct_fetch_apply_run
                    (run_id, company_id, base_snapshot_run_id, selected_domains,
                     models, manifest_completion_fingerprint, manifest_row_count,
                     batch_size, contract_version, field_contract_version,
                     field_contract_fingerprint, field_contract_allowlist_fingerprint,
                     status, started_at)
                VALUES (CAST(:run_id AS UUID), :company_id, CAST(:base AS UUID),
                        CAST(:domains AS JSONB), CAST(:models AS JSONB),
                        :manifest_fingerprint, :manifest_row_count, :batch_size,
                        :contract_version, :field_contract_version,
                        :field_contract_fingerprint, :field_contract_allowlist_fingerprint,
                        'RUNNING', :started_at)
                ON CONFLICT (run_id) DO NOTHING
            """), {
                "run_id": run_uuid, "company_id": company_id, "base": base_snapshot,
                "domains": json.dumps(resolved_domains),
                "models": json.dumps(detection["models"]),
                "manifest_fingerprint": detection["manifest_completion_fingerprint"],
                "manifest_row_count": detection["manifest_row_count"],
                "batch_size": self._batch_size,
                "contract_version": FETCH_APPLY_CONTRACT_VERSION,
                "field_contract_version": FETCH_APPLY_CONTRACT_VERSION,
                "field_contract_fingerprint": None,
                "field_contract_allowlist_fingerprint": code_side,
                "started_at": timestamp,
            })
        header = self._header(run_uuid)
        if header is None:
            raise FetchApplyError("Fetch/apply header could not be persisted.")
        return header

    def _completed_batches(self, run_uuid: str) -> set[tuple[str, int]]:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model, batch_number FROM ct_fetch_apply_batch
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).all()
        return {(str(row[0]), int(row[1])) for row in rows}

    def _existing_totals(self, run_uuid: str) -> dict[str, int]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT COALESCE(SUM(records_requested), 0) AS records_requested,
                       COALESCE(SUM(records_fetched), 0) AS records_fetched,
                       COALESCE(SUM(records_missing), 0) AS records_missing,
                       COALESCE(SUM(source_drift), 0) AS source_drift,
                       COALESCE(SUM(inserted), 0) AS inserted,
                       COALESCE(SUM(updated), 0) AS updated,
                       COALESCE(SUM(unchanged), 0) AS unchanged,
                       COUNT(*) AS batches_completed
                FROM ct_fetch_apply_batch
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().one()
        return {
            "records_requested": int(row["records_requested"]),
            "records_fetched": int(row["records_fetched"]),
            "records_missing": int(row["records_missing"]),
            "source_drift": int(row["source_drift"]),
            "inserted": int(row["inserted"]),
            "updated": int(row["updated"]),
            "unchanged": int(row["unchanged"]),
            "batches_completed": int(row["batches_completed"]),
        }

    def _ensure_fetch_apply(
        self, header: dict[str, Any], progress: dict[str, Any],
        timestamp: datetime, odoo_client,
    ) -> dict[str, Any]:
        run_uuid = header["run_id"]
        models = list(header["models"])
        completed_batches = self._completed_batches(run_uuid)
        all_batches_complete = True
        for model in models:
            batches = self._manifest_batches(run_uuid, model)
            expected = set(range(1, len(batches) + 1))
            if not expected.issubset({number for (model_key, number) in completed_batches if model_key == model}):
                all_batches_complete = False
        if not all_batches_complete:
            metadata_by_model = {
                model: self._field_metadata(model, odoo_client) for model in models
            }
            full_fingerprint = _full_field_contract_fingerprint(
                models, int(header["batch_size"]), metadata_by_model,
            )
            if header.get("field_contract_fingerprint") is None:
                with self.pg.engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE ct_fetch_apply_run
                        SET field_contract_fingerprint = :fingerprint
                        WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
                    """), {"run_id": run_uuid, "fingerprint": full_fingerprint})
            elif header["field_contract_fingerprint"] != full_fingerprint:
                raise FetchApplyError(
                    "Current field metadata no longer matches the persisted fetch/apply contract.",
                    requires_new_retry=True,
                )
        elif header.get("field_contract_fingerprint") is None:
            raise FetchApplyError(
                "Completed fetch/apply evidence lacks a durable field-contract fingerprint.",
                requires_new_retry=True,
            )
        totals = self._existing_totals(run_uuid)
        started_value = progress.get("fetch_apply_started_at")
        if isinstance(started_value, str):
            started = datetime.fromisoformat(started_value.replace("Z", "+00:00"))
        else:
            started = _utc(started_value or timestamp)
        progress = dict(progress)
        progress.update({
            "fetch_apply_models_planned": models,
            "fetch_apply_started_at": started.isoformat(),
            "fetch_apply_contract_version": FETCH_APPLY_CONTRACT_VERSION,
        })
        progress = parse_progress_json(progress)
        self._write_progress(run_uuid, progress)

        for model in models:
            batches = self._manifest_batches(run_uuid, model)
            expected_batches = set(range(1, len(batches) + 1))
            for batch_number in range(1, len(batches) + 1):
                if (model, batch_number) in completed_batches:
                    continue
                if batch_number == 1:
                    self._fire("before_first_fetch")
                self._fire("before_fetch")
                batch_result = self._fetch_and_apply_batch(
                    run_uuid, model, batches[batch_number - 1], batch_number,
                    header["batch_size"], started, odoo_client,
                )
                self._fire("after_fetch")
                for key in (
                    "records_requested", "records_fetched", "records_missing",
                    "source_drift", "inserted", "updated", "unchanged",
                ):
                    totals[key] += batch_result[key]
                totals["batches_completed"] += 1
                completed_batches.add((model, batch_number))
                self._write_progress(run_uuid, self._merged_progress(progress, model, totals, started))
                self._fire("after_apply")
            if not expected_batches.issubset({number for (model_key, number) in completed_batches if model_key == model}):
                raise FetchApplyError(f"Fetch/apply did not complete every batch for {model}.")
            progress = self._merged_progress(progress, model, totals, started)
            self._write_progress(run_uuid, progress)

        return parse_progress_json(progress)

    def _manifest_batches(self, run_uuid: str, model: str) -> list[list[dict[str, Any]]]:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model, record_id, source_write_date, detection_sequence, status
                FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID) AND model = :model
                ORDER BY detection_sequence
            """), {"run_id": run_uuid, "model": model}).mappings().all()
        batch_size = self._batch_size
        return [
            [dict(row) for row in rows[index:index + batch_size]]
            for index in range(0, len(rows), batch_size)
        ]

    def _merged_progress(self, progress: dict[str, Any], model: str, totals: dict[str, int], started: datetime) -> dict[str, Any]:
        merged = dict(progress)
        completed = list(progress.get("fetch_apply_models_completed", []))
        if model not in completed:
            completed.append(model)
        merged.update({
            "fetch_apply_models_completed": completed,
            "fetch_apply_current_model": model,
            "fetch_apply_records_requested": totals["records_requested"],
            "fetch_apply_records_fetched": totals["records_fetched"],
            "fetch_apply_records_missing_at_fetch": totals["records_missing"],
            "fetch_apply_records_source_drift": totals["source_drift"],
            "fetch_apply_inserted": totals["inserted"],
            "fetch_apply_updated": totals["updated"],
            "fetch_apply_unchanged": totals["unchanged"],
            "fetch_apply_applied_total": totals["inserted"] + totals["updated"] + totals["unchanged"],
            "fetch_apply_batches_completed": totals["batches_completed"],
            "fetch_apply_elapsed_seconds": round(max(0.0, (datetime.now(timezone.utc) - started).total_seconds()), 6),
        })
        return parse_progress_json(merged)

    def _field_metadata(self, model: str, odoo_client) -> Mapping[str, Mapping[str, Any]]:
        if model not in self._metadata_cache:
            metadata = odoo_client.get_model_fields(model)
            if not isinstance(metadata, Mapping):
                raise FetchApplyError(f"Odoo model metadata is malformed for {model}.")
            self._metadata_cache[model] = _validated_field_metadata(model, metadata)
        return self._metadata_cache[model]
        return self._metadata_cache[model]

    def _fetch_and_apply_batch(
        self, run_uuid: str, model: str, manifest_rows: list[dict[str, Any]],
        batch_number: int, batch_size: int, started: datetime, odoo_client,
    ) -> dict[str, int]:
        fields = list(_build_field_contract(model))
        metadata = self._field_metadata(model, odoo_client)
        requested_ids = [int(row["record_id"]) for row in manifest_rows]
        company_id = self._company_id_for_run(run_uuid)
        domain = [("company_id", "=", company_id), ("id", "in", requested_ids)]
        records = odoo_client.search_read(
            model, domain, fields=fields, order="id asc", limit=batch_size,
        )
        if not isinstance(records, list):
            raise FetchApplyError(f"Odoo search_read returned a non-list for {model} batch {batch_number}.")
        if len(records) > batch_size:
            raise FetchApplyError(f"Odoo fetch exceeded the batch limit for {model} batch {batch_number}.")
        by_id: dict[int, dict[str, Any]] = {}
        for record in records:
            normalized = _normalize_record(record, model, company_id, metadata)
            record_id = normalized["record_id"]
            if record_id in by_id:
                raise FetchApplyError(f"Odoo fetch returned a duplicate conflicting row for {model}/{record_id}.")
            if record_id not in requested_ids:
                raise FetchApplyError(f"Odoo fetch returned an unrequested record for {model}/{record_id}.")
            by_id[record_id] = normalized
        fetched_ids = set(by_id)

        candidate_rows = self._candidate_payloads(run_uuid, model, requested_ids)
        evidence_rows: list[dict[str, Any]] = []
        apply_rows: list[dict[str, Any]] = []
        drift = 0
        inserted = updated = unchanged = 0
        detection_by_id = {int(row["record_id"]): row for row in manifest_rows}
        for manifest_row in manifest_rows:
            record_id = int(manifest_row["record_id"])
            detection_sequence = int(manifest_row["detection_sequence"])
            detection_written = manifest_row["source_write_date"]
            if record_id in by_id:
                normalized = by_id[record_id]
                fetched_written = normalized["write_date"]
                if fetched_written < detection_written:
                    raise FetchApplyError(
                        f"Fetched write_date is older than detection evidence for {model}/{record_id}."
                    )
                is_drift = fetched_written > detection_written
                if is_drift:
                    drift += 1
                fingerprint = _jsonb_fingerprint(normalized["payload"])
                existing = candidate_rows.get(record_id)
                if existing is None:
                    classification = APPLY_INSERTED
                    inserted += 1
                elif existing["fingerprint"] == fingerprint:
                    classification = APPLY_UNCHANGED
                    unchanged += 1
                else:
                    classification = APPLY_UPDATED
                    updated += 1
                apply_rows.append({
                    "run_id": run_uuid, "model": model, "record_id": record_id,
                    "document_number": normalized["document_number"],
                    "state": normalized["state"],
                    "company_id": normalized["company_id"],
                    "company_name": normalized["company_name"],
                    "write_date": normalized["write_date"],
                    "payload": _canonical_payload(normalized),
                    "extracted_at": datetime.now(timezone.utc),
                })
                evidence_rows.append({
                    "run_id": run_uuid, "company_id": company_id,
                    "model": model, "record_id": record_id,
                    "detection_sequence": detection_sequence,
                    "batch_number": batch_number,
                    "detection_source_write_date": detection_written,
                    "fetched_write_date": fetched_written,
                    "fetch_status": FETCH_STATUS_FETCHED,
                    "apply_status": classification,
                    "source_drift": is_drift,
                    "payload_fingerprint": fingerprint,
                    "fetched_at": datetime.now(timezone.utc),
                    "applied_at": datetime.now(timezone.utc),
                    "error_evidence": None,
                })
            else:
                evidence_rows.append({
                    "run_id": run_uuid, "company_id": company_id,
                    "model": model, "record_id": record_id,
                    "detection_sequence": detection_sequence,
                    "batch_number": batch_number,
                    "detection_source_write_date": detection_written,
                    "fetched_write_date": None,
                    "fetch_status": FETCH_STATUS_MISSING,
                    "apply_status": FETCH_STATUS_MISSING,
                    "source_drift": False,
                    "payload_fingerprint": None,
                    "fetched_at": datetime.now(timezone.utc),
                    "applied_at": None,
                    "error_evidence": None,
                })

        missing_count = len(requested_ids) - len(fetched_ids)
        self._persist_batch(
            run_uuid, model, batch_number, evidence_rows, apply_rows,
            {
                "records_requested": len(requested_ids),
                "records_fetched": len(fetched_ids),
                "records_missing": missing_count,
                "inserted": inserted,
                "updated": updated,
                "unchanged": unchanged,
                "source_drift": drift,
            },
        )
        return {
            "records_requested": len(requested_ids),
            "records_fetched": len(fetched_ids),
            "records_missing": missing_count,
            "source_drift": drift,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
        }

    def _company_id_for_run(self, run_uuid: str) -> int:
        with self.pg.engine.connect() as conn:
            value = conn.execute(text("""
                SELECT company_id FROM ct_fetch_apply_run WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).scalar()
        if value is None:
            raise FetchApplyError("Fetch/apply header is missing.")
        return int(value)

    def _candidate_payloads(self, run_uuid: str, model: str, record_ids: list[int]) -> dict[int, dict[str, Any]]:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT record_id, payload
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                  AND model = :model
                  AND record_id = ANY(:record_ids)
            """), {"run_id": run_uuid, "model": model, "record_ids": record_ids}).mappings().all()
        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            payload = row["payload"]
            if not isinstance(payload, dict):
                raise FetchApplyError(f"Candidate payload is malformed for {model}/{row['record_id']}.")
            if isinstance(payload.get("write_date"), str):
                try:
                    payload = dict(payload)
                    payload["write_date"] = datetime.fromisoformat(payload["write_date"].replace("Z", "+00:00"))
                except ValueError:
                    raise FetchApplyError(f"Candidate payload write_date is malformed for {model}/{row['record_id']}.")
            result[int(row["record_id"])] = {"fingerprint": _jsonb_fingerprint(payload)}
        return result

    def _persist_batch(
        self, run_uuid: str, model: str, batch_number: int,
        evidence_rows: list[dict[str, Any]], apply_rows: list[dict[str, Any]],
        counts: dict[str, int],
    ) -> None:
        with self.pg.engine.begin() as conn:
            for row in evidence_rows:
                conn.execute(text("""
                    INSERT INTO ct_fetch_apply_evidence
                        (run_id, company_id, model, record_id, detection_sequence,
                         batch_number, detection_source_write_date, fetched_write_date,
                         fetch_status, apply_status, source_drift, payload_fingerprint,
                         fetched_at, applied_at, error_evidence)
                    VALUES (CAST(:run_id AS UUID), :company_id, :model, :record_id,
                            :detection_sequence, :batch_number,
                            :detection_source_write_date, :fetched_write_date,
                            :fetch_status, :apply_status, :source_drift,
                            :payload_fingerprint, :fetched_at, :applied_at, :error_evidence)
                """), {
                    "run_id": row["run_id"], "company_id": row["company_id"],
                    "model": row["model"], "record_id": row["record_id"],
                    "detection_sequence": row["detection_sequence"],
                    "batch_number": row["batch_number"],
                    "detection_source_write_date": row["detection_source_write_date"],
                    "fetched_write_date": row["fetched_write_date"],
                    "fetch_status": row["fetch_status"], "apply_status": row["apply_status"],
                    "source_drift": row["source_drift"],
                    "payload_fingerprint": row["payload_fingerprint"],
                    "fetched_at": row["fetched_at"], "applied_at": row["applied_at"],
                    "error_evidence": row["error_evidence"],
                })
            for row in apply_rows:
                conn.execute(text("""
                    INSERT INTO ct_native_record_snapshot
                        (extraction_run_id, model, record_id, document_number, state,
                         company_id, company_name, write_date, payload, extracted_at)
                    VALUES (CAST(:run_id AS UUID), :model, :record_id, :document_number,
                            :state, :company_id, :company_name, :write_date,
                            CAST(:payload AS JSONB), :extracted_at)
                    ON CONFLICT (extraction_run_id, model, record_id) DO UPDATE SET
                        document_number = EXCLUDED.document_number,
                        state = EXCLUDED.state,
                        company_id = EXCLUDED.company_id,
                        company_name = EXCLUDED.company_name,
                        write_date = EXCLUDED.write_date,
                        payload = EXCLUDED.payload,
                        extracted_at = EXCLUDED.extracted_at
                    WHERE ct_native_record_snapshot.payload IS DISTINCT FROM EXCLUDED.payload
                """), {
                    "run_id": row["run_id"], "model": row["model"],
                    "record_id": row["record_id"],
                    "document_number": row["document_number"], "state": row["state"],
                    "company_id": row["company_id"], "company_name": row["company_name"],
                    "write_date": row["write_date"].replace(tzinfo=None) if isinstance(row["write_date"], datetime) else row["write_date"],
                    "payload": row["payload"],
                    "extracted_at": row["extracted_at"],
                })
            for row in evidence_rows:
                conn.execute(text("""
                    UPDATE ct_change_manifest
                    SET status = :status
                    WHERE run_id = CAST(:run_id AS UUID) AND model = :model AND record_id = :record_id
                """), {
                    "run_id": run_uuid, "model": row["model"], "record_id": row["record_id"],
                    "status": "APPLIED" if row["fetch_status"] == FETCH_STATUS_FETCHED else "MISSING_AT_FETCH",
                })
            conn.execute(text("""
                INSERT INTO ct_fetch_apply_batch
                    (run_id, model, batch_number, records_requested, records_fetched,
                     records_missing, inserted, updated, unchanged, source_drift, completed_at)
                VALUES (CAST(:run_id AS UUID), :model, :batch_number, :records_requested,
                        :records_fetched, :records_missing, :inserted, :updated,
                        :unchanged, :source_drift, :completed_at)
            """), {
                "run_id": run_uuid, "model": model, "batch_number": batch_number,
                "records_requested": counts["records_requested"],
                "records_fetched": counts["records_fetched"],
                "records_missing": counts["records_missing"],
                "inserted": counts["inserted"], "updated": counts["updated"],
                "unchanged": counts["unchanged"], "source_drift": counts["source_drift"],
                "completed_at": datetime.now(timezone.utc),
            })

    def _write_progress(self, run_uuid: str, progress: dict[str, Any]) -> None:
        with self.pg.engine.begin() as conn:
            updated = conn.execute(text("""
                UPDATE ct_extraction_run
                SET progress = progress || CAST(:progress AS JSONB), heartbeat_at = :now
                WHERE run_id = CAST(:run_uuid AS UUID)
                  AND status = 'FETCHING'
                  AND COALESCE((progress->>'fetch_apply_complete')::boolean, FALSE) = FALSE
            """), {
                "run_uuid": run_uuid,
                "progress": serialize_progress(progress),
                "now": datetime.now(timezone.utc),
            })
            if updated.rowcount != 1:
                raise FetchApplyError(
                    "Fetch/apply progress write was rejected by a stale run state.",
                    requires_new_retry=True,
                )

    def _finalize(
        self, run_uuid: str, company_id: int, header: dict[str, Any],
        progress: dict[str, Any], timestamp: datetime,
        detection: dict[str, Any], *, idempotent: bool,
    ) -> dict[str, Any]:
        if not idempotent:
            self._fire("before_completion")
        self._validate_candidate_rows(run_uuid, str(header["base_snapshot_run_id"]))
        self._validate_evidence_reconciliation(run_uuid, detection)
        totals = self._evidence_totals(run_uuid)
        model_counts = self._model_counts(run_uuid, header["models"])
        completion_fingerprint = self._completion_fingerprint(
            company_id, header, detection, model_counts,
        )
        expected_models = sorted(header["models"])
        if sorted(model_counts) != expected_models:
            raise FetchApplyError("Fetch/apply model counts do not match the plan.")
        for model in expected_models:
            expected_count = int(detection["model_row_counts"].get(model, 0))
            if model_counts[model]["records_requested"] != expected_count:
                raise FetchApplyError(f"Fetch/apply evidence count changed for {model}.")
        progress = dict(progress)
        progress.update({
            "fetch_apply_complete": True,
            "fetch_apply_models_completed": list(header["models"]),
            "fetch_apply_finished_at": timestamp.isoformat(),
            "fetch_apply_elapsed_seconds": round(
                max(0.0, (timestamp - datetime.fromisoformat(progress["fetch_apply_started_at"].replace("Z", "+00:00"))).total_seconds()), 6
            ),
            "fetch_apply_completion_fingerprint": completion_fingerprint,
            "orchestration_current_stage": "RECONCILING",
            "orchestration_last_completed_stage": "FETCHING",
            "orchestration_next_required_stage": "RECONCILING",
            "orchestration_finished_at": timestamp.isoformat(),
        })
        progress = parse_progress_json(progress)
        with self.pg.engine.begin() as conn:
            current = conn.execute(text("""
                SELECT status FROM ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                FOR UPDATE
            """), {"run_id": run_uuid}).scalar()
            if str(current) != "FETCHING":
                raise FetchApplyError(
                    f"Stale refresh run state {current!r} cannot finalize fetch/apply.",
                    requires_new_retry=True,
                )
            header_updated = conn.execute(text("""
                UPDATE ct_fetch_apply_run
                SET status = 'COMPLETE', finished_at = :finished_at,
                    duration_seconds = :duration_seconds,
                    completion_fingerprint = :completion_fingerprint,
                    model_fetch_counts = CAST(:model_counts AS JSONB)
                WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
            """), {
                "run_id": run_uuid, "finished_at": timestamp,
                "duration_seconds": max(0.0, (timestamp - _utc(header["started_at"])).total_seconds()),
                "completion_fingerprint": completion_fingerprint,
                "model_counts": json.dumps(model_counts, sort_keys=True),
            })
            if header_updated.rowcount != 1:
                raise FetchApplyError(
                    "Fetch/apply header completion was superseded by another writer.",
                    requires_new_retry=True,
                )
            progress_updated = conn.execute(text("""
                UPDATE ct_extraction_run
                SET progress = CAST(:progress AS JSONB), heartbeat_at = :now
                WHERE run_id = CAST(:run_uuid AS UUID)
            """), {
                "run_uuid": run_uuid, "progress": serialize_progress(progress),
                "now": timestamp,
            })
            if progress_updated.rowcount != 1:
                raise FetchApplyError("Fetch/apply final progress could not be persisted.")
            validate_transition("FETCHING", "RECONCILING")
            transition_updated = conn.execute(text("""
                UPDATE ct_extraction_run
                SET status = 'RECONCILING', stage = 'RECONCILING',
                    stage_started_at = :now, heartbeat_at = :now
                WHERE run_id = CAST(:run_uuid AS UUID) AND status = 'FETCHING'
            """), {"run_uuid": run_uuid, "now": timestamp})
            if transition_updated.rowcount != 1:
                raise FetchApplyError(
                    "Fetch/apply stale transition affected zero rows; finalization rolled back.",
                    requires_new_retry=True,
                )
        if not idempotent:
            self._fire("after_transition")
        return self._summary(run_uuid, company_id, totals, model_counts, idempotent=idempotent)

    def _evidence_totals(self, run_uuid: str) -> dict[str, int]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE fetch_status = 'FETCHED') AS fetched,
                       COUNT(*) FILTER (WHERE fetch_status = 'MISSING_AT_FETCH') AS missing,
                       COUNT(*) FILTER (WHERE source_drift) AS drift,
                       COUNT(*) FILTER (WHERE apply_status = 'INSERTED') AS inserted,
                       COUNT(*) FILTER (WHERE apply_status = 'UPDATED') AS updated,
                       COUNT(*) FILTER (WHERE apply_status = 'UNCHANGED') AS unchanged
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().one()
        return {
            "records_requested": int(row["total"]),
            "records_fetched": int(row["fetched"]),
            "records_missing": int(row["missing"]),
            "source_drift": int(row["drift"]),
            "inserted": int(row["inserted"]),
            "updated": int(row["updated"]),
            "unchanged": int(row["unchanged"]),
        }

    def _model_counts(self, run_uuid: str, models: list[str]) -> dict[str, dict[str, int]]:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE fetch_status = 'FETCHED') AS fetched,
                       COUNT(*) FILTER (WHERE fetch_status = 'MISSING_AT_FETCH') AS missing
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID) AND model = ANY(:models)
                GROUP BY model
            """), {"run_id": run_uuid, "models": models}).mappings().all()
        return {
            str(row["model"]): {
                "records_requested": int(row["total"]),
                "records_fetched": int(row["fetched"]),
                "records_missing": int(row["missing"]),
            }
            for row in rows
        }

    def _evidence_fingerprint(self, run_uuid: str) -> str:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model, record_id, detection_sequence, detection_source_write_date,
                       fetched_write_date, fetch_status, apply_status, source_drift,
                       payload_fingerprint, batch_number, fetched_at, applied_at,
                       error_evidence
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, detection_sequence, record_id
            """), {"run_id": run_uuid}).all()
        chunks = [FETCH_APPLY_CONTRACT_VERSION]
        for row in rows:
            chunks.append(json.dumps({
                "model": str(row[0]), "record_id": int(row[1]),
                "detection_sequence": int(row[2]),
                "detection_source_write_date": (
                    row[3].astimezone(timezone.utc).isoformat() if row[3] is not None else None
                ),
                "fetched_write_date": (
                    row[4].astimezone(timezone.utc).isoformat() if row[4] is not None else None
                ),
                "fetch_status": str(row[5]),
                "apply_status": str(row[6]),
                "source_drift": bool(row[7]),
                "payload_fingerprint": row[8],
                "batch_number": int(row[9]),
                "fetched_at": (
                    row[10].astimezone(timezone.utc).isoformat() if row[10] is not None else None
                ),
                "applied_at": (
                    row[11].astimezone(timezone.utc).isoformat() if row[11] is not None else None
                ),
                "error_evidence": row[12],
            }, sort_keys=True, separators=(",", ":")))
        return hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest()
    @staticmethod
    def _manifest_fingerprint(detection: dict[str, Any]) -> str:
        chunks = [FETCH_APPLY_CONTRACT_VERSION]
        for row in sorted(detection.get("manifest_rows", []), key=lambda r: (r["model"], r["detection_sequence"], r["record_id"])):
            chunks.append(json.dumps({
                "model": row["model"], "record_id": int(row["record_id"]),
                "detection_sequence": int(row["detection_sequence"]),
                "source_write_date": str(row["source_write_date"]),
                "parent_model": row.get("parent_model"),
                "parent_record_id": int(row["parent_record_id"]) if row.get("parent_record_id") else None,
                "parent_hints": sorted(row.get("parent_hints") or [], key=lambda hint: (hint.get("parent_model"), hint.get("field"), hint.get("parent_record_id"))),
            }, sort_keys=True, separators=(",", ":")))
        return hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest()

    def _batch_fingerprint(self, run_uuid: str) -> str:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT model, batch_number, records_requested, records_fetched,
                       records_missing, inserted, updated, unchanged, source_drift,
                       completed_at
                FROM ct_fetch_apply_batch
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, batch_number
            """), {"run_id": run_uuid}).all()
        chunks = [FETCH_APPLY_CONTRACT_VERSION]
        for row in rows:
            chunks.append(json.dumps({
                "model": str(row[0]), "batch_number": int(row[1]),
                "records_requested": int(row[2]), "records_fetched": int(row[3]),
                "records_missing": int(row[4]), "inserted": int(row[5]),
                "updated": int(row[6]), "unchanged": int(row[7]),
                "source_drift": int(row[8]),
                "completed_at": (
                    row[9].astimezone(timezone.utc).isoformat() if row[9] is not None else None
                ),
            }, sort_keys=True, separators=(",", ":")))
        return hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest()
    def _completion_fingerprint(
        self, company_id: int, header: dict[str, Any],
        detection: dict[str, Any], model_counts: dict[str, dict[str, int]],
    ) -> str:
        value = {
            "version": FETCH_APPLY_CONTRACT_VERSION,
            "company_id": company_id,
            "selected_domains": list(header["selected_domains"]),
            "models": list(header["models"]),
            "manifest_completion_fingerprint": header["manifest_completion_fingerprint"],
            "manifest_row_count": header["manifest_row_count"],
            "batch_size": header["batch_size"],
            "base_snapshot_run_id": str(header["base_snapshot_run_id"]),
            "model_counts": model_counts,
            "manifest_fingerprint": self._manifest_fingerprint(detection),
            "evidence_fingerprint": self._evidence_fingerprint(header["run_id"]),
            "batch_fingerprint": self._batch_fingerprint(header["run_id"]),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _validate_evidence_reconciliation(self, run_uuid: str, detection: dict[str, Any]) -> None:
        with self.pg.engine.connect() as conn:
            evidence = conn.execute(text("""
                SELECT model, record_id, detection_sequence, detection_source_write_date,
                       fetched_write_date, batch_number, fetch_status, apply_status,
                       source_drift
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, detection_sequence
            """), {"run_id": run_uuid}).mappings().all()
            batches = conn.execute(text("""
                SELECT model, batch_number, records_requested, records_fetched,
                       records_missing, inserted, updated, unchanged, source_drift
                FROM ct_fetch_apply_batch
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, batch_number
            """), {"run_id": run_uuid}).mappings().all()
            manifest = conn.execute(text("""
                SELECT model, record_id, status
                FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, detection_sequence
            """), {"run_id": run_uuid}).mappings().all()
        manifest_rows = list(detection.get("manifest_rows") or [])
        if len(evidence) != len(manifest_rows):
            raise FetchApplyError(
                f"Fetch/apply evidence count {len(evidence)} does not match manifest count {len(manifest_rows)}.",
                requires_new_retry=True,
            )
        manifest_by_key = {
            (str(row["model"]), int(row["record_id"])): row for row in manifest_rows
        }
        manifest_status_by_key = {
            (str(row["model"]), int(row["record_id"])): str(row["status"]) for row in manifest
        }
        evidence_by_key: dict[tuple[str, int], dict[str, Any]] = {}
        for row in evidence:
            key = (str(row["model"]), int(row["record_id"]))
            if key in evidence_by_key:
                raise FetchApplyError(f"Duplicate fetch/apply evidence for {key[0]}/{key[1]}.")
            evidence_by_key[key] = row
            manifest = manifest_by_key.get(key)
            if manifest is None:
                raise FetchApplyError(
                    f"Fetch/apply evidence exists for an unknown manifest row {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            if int(row["detection_sequence"]) != int(manifest["detection_sequence"]):
                raise FetchApplyError(
                    f"Fetch/apply detection sequence changed for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            if str(row["detection_source_write_date"]) != str(manifest["source_write_date"]):
                raise FetchApplyError(
                    f"Fetch/apply detection source timestamp changed for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            is_drift = row["fetched_write_date"] is not None and row["fetched_write_date"] > row["detection_source_write_date"]
            if bool(row["source_drift"]) != is_drift:
                raise FetchApplyError(
                    f"Fetch/apply source-drift flag is inconsistent for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            expected_status = "APPLIED" if row["fetch_status"] == FETCH_STATUS_FETCHED else "MISSING_AT_FETCH"
            actual_status = manifest_status_by_key.get(key)
            if actual_status != expected_status:
                raise FetchApplyError(
                    f"Manifest lifecycle status {actual_status!r} contradicts fetch/apply evidence for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
        for key, manifest in manifest_by_key.items():
            if key not in evidence_by_key:
                raise FetchApplyError(
                    f"Manifest row has no fetch/apply evidence: {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
        manifest_statuses = set(manifest_status_by_key.values())
        if not manifest_statuses.issubset({"APPLIED", "MISSING_AT_FETCH"}):
            raise FetchApplyError(
                f"Manifest contains unresolved lifecycle statuses at the boundary: {sorted(manifest_statuses)}.",
                requires_new_retry=True,
            )
        batch_by_key: dict[tuple[str, int], dict[str, Any]] = {}
        for row in batches:
            key = (str(row["model"]), int(row["batch_number"]))
            batch_by_key[key] = row
        evidence_by_batch: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for row in evidence:
            key = (str(row["model"]), int(row["batch_number"]))
            evidence_by_batch.setdefault(key, []).append(row)
        model_batch_numbers: dict[str, list[int]] = {}
        for (model, number) in batch_by_key:
            model_batch_numbers.setdefault(model, []).append(number)
        for model, numbers in model_batch_numbers.items():
            if sorted(numbers) != list(range(1, max(numbers) + 1)):
                raise FetchApplyError(f"Fetch/apply batch numbers are not contiguous for {model}.")
        for key, rows in evidence_by_batch.items():
            batch = batch_by_key.get(key)
            if batch is None:
                raise FetchApplyError(f"Evidence batch has no batch row: {key[0]}/{key[1]}.")
            if len(rows) != int(batch["records_requested"]):
                raise FetchApplyError(
                    f"Batch {key[0]}/{key[1]} evidence count does not match its requested count.",
                    requires_new_retry=True,
                )
            fetched = sum(1 for row in rows if row["fetch_status"] == FETCH_STATUS_FETCHED)
            missing = sum(1 for row in rows if row["fetch_status"] == FETCH_STATUS_MISSING)
            if fetched != int(batch["records_fetched"]) or missing != int(batch["records_missing"]):
                raise FetchApplyError(f"Batch {key[0]}/{key[1]} fetch counts do not reconcile.")
            inserted = sum(1 for row in rows if row["apply_status"] == APPLY_INSERTED)
            updated = sum(1 for row in rows if row["apply_status"] == APPLY_UPDATED)
            unchanged = sum(1 for row in rows if row["apply_status"] == APPLY_UNCHANGED)
            if (
                inserted != int(batch["inserted"])
                or updated != int(batch["updated"])
                or unchanged != int(batch["unchanged"])
            ):
                raise FetchApplyError(f"Batch {key[0]}/{key[1]} apply counts do not reconcile.")
            drift_count = sum(1 for row in rows if row["source_drift"])
            if drift_count != int(batch["source_drift"]):
                raise FetchApplyError(f"Batch {key[0]}/{key[1]} source-drift count does not reconcile.")
            if int(batch["source_drift"]) > fetched:
                raise FetchApplyError(f"Batch {key[0]}/{key[1]} source-drift count exceeds fetched count.")
        for key, batch in batch_by_key.items():
            if key not in evidence_by_batch:
                raise FetchApplyError(f"Batch row has no evidence: {key[0]}/{key[1]}.")
        batch_size = self._batch_size
        for model in sorted({str(row["model"]) for row in manifest_rows}):
            model_rows = sorted(
                [row for row in manifest_rows if str(row["model"]) == model],
                key=lambda r: (int(r["detection_sequence"]), int(r["record_id"])),
            )
            for index, manifest in enumerate(model_rows):
                expected_batch = index // batch_size + 1
                evidence_row = evidence_by_key[(str(manifest["model"]), int(manifest["record_id"]))]
                if int(evidence_row["batch_number"]) != expected_batch:
                    raise FetchApplyError(
                        f"Fetch/apply batch membership changed for {model}/{manifest['record_id']}: "
                        f"expected {expected_batch}, found {evidence_row['batch_number']}.",
                        requires_new_retry=True,
                    )
    def _validate_candidate_rows(self, run_uuid: str, base_snapshot_run_id: str) -> None:
        with self.pg.engine.connect() as conn:
            evidence = conn.execute(text("""
                SELECT model, record_id, payload_fingerprint, apply_status, fetch_status
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().all()
            snapshots = conn.execute(text("""
                SELECT model, record_id, document_number, state, company_id,
                       company_name, write_date, payload, extracted_at,
                       extraction_run_id::text
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().all()
            base_rows = conn.execute(text("""
                SELECT model, record_id, document_number, state, company_id,
                       company_name, write_date, payload, extracted_at
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:base AS UUID)
            """), {"base": base_snapshot_run_id}).mappings().all()
        snapshot_by_key = {
            (str(row["model"]), int(row["record_id"])): dict(row) for row in snapshots
        }
        base_by_key = {
            (str(row["model"]), int(row["record_id"])): dict(row) for row in base_rows
        }

        def _business_row_equal(candidate: Mapping[str, Any], base: Mapping[str, Any], key) -> None:
            for column in ("document_number", "state", "company_id", "company_name", "write_date", "payload", "extracted_at"):
                if candidate.get(column) != base.get(column):
                    raise FetchApplyError(
                        f"Missing-at-fetch candidate row is not an exact copy of the base for {key[0]}/{key[1]} ({column}).",
                        requires_new_retry=True,
                    )

        for row in evidence:
            key = (str(row["model"]), int(row["record_id"]))
            if row["fetch_status"] == FETCH_STATUS_MISSING:
                in_base = key in base_by_key
                in_candidate = key in snapshot_by_key
                if in_base != in_candidate:
                    raise FetchApplyError(
                        f"Missing-at-fetch baseline policy violated for {key[0]}/{key[1]}.",
                        requires_new_retry=True,
                    )
                if in_base:
                    _business_row_equal(snapshot_by_key[key], base_by_key[key], key)
                continue
            candidate = snapshot_by_key.get(key)
            if candidate is None:
                raise FetchApplyError(
                    f"Applied candidate row is missing for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            payload = candidate["payload"]
            if not isinstance(payload, dict):
                raise FetchApplyError(f"Candidate payload is malformed for {key[0]}/{key[1]}.")
            if isinstance(payload.get("write_date"), str):
                try:
                    payload = dict(payload)
                    payload["write_date"] = datetime.fromisoformat(payload["write_date"].replace("Z", "+00:00"))
                except ValueError:
                    raise FetchApplyError(
                        f"Candidate payload write_date is malformed for {key[0]}/{key[1]}."
                    )
            fingerprint = _jsonb_fingerprint(payload)
            if fingerprint != row["payload_fingerprint"]:
                raise FetchApplyError(
                    f"Candidate row no longer matches recorded application evidence for {key[0]}/{key[1]}.",
                    requires_new_retry=True,
                )
            if str(candidate["model"]) != key[0] or int(candidate["record_id"]) != key[1]:
                raise FetchApplyError(f"Candidate identity changed for {key[0]}/{key[1]}.")
            if str(candidate["extraction_run_id"]) != run_uuid:
                raise FetchApplyError(f"Candidate run identity changed for {key[0]}/{key[1]}.")
            normalized = payload
            expected_document_number = _document_number(normalized, key[0])
            expected_state = _state_value(normalized)
            if str(candidate.get("document_number") or "") != str(expected_document_number or ""):
                raise FetchApplyError(f"Candidate document number changed for {key[0]}/{key[1]}.")
            if str(candidate.get("state") or "") != str(expected_state or ""):
                raise FetchApplyError(f"Candidate state changed for {key[0]}/{key[1]}.")
            company = normalized.get("company_id")
            expected_company_id = None
            expected_company_name = None
            if isinstance(company, Mapping) and isinstance(company.get("id"), int):
                expected_company_id = company["id"]
                expected_company_name = company.get("name")
            if int(candidate.get("company_id") or 0) != int(expected_company_id or 0):
                raise FetchApplyError(f"Candidate company changed for {key[0]}/{key[1]}.")
            if str(candidate.get("company_name") or "") != str(expected_company_name or ""):
                raise FetchApplyError(f"Candidate company name changed for {key[0]}/{key[1]}.")
            expected_write = normalized.get("write_date")
            if isinstance(expected_write, datetime) and not expected_write.tzinfo:
                expected_write = expected_write.replace(tzinfo=timezone.utc)
            candidate_write = candidate.get("write_date")
            if isinstance(candidate_write, datetime) and candidate_write.tzinfo is None:
                candidate_write = candidate_write.replace(tzinfo=timezone.utc)
            if isinstance(expected_write, datetime) and isinstance(candidate_write, datetime):
                if candidate_write.astimezone(timezone.utc) != expected_write.astimezone(timezone.utc):
                    raise FetchApplyError(f"Candidate write_date changed for {key[0]}/{key[1]}.")
            elif candidate_write != expected_write:
                raise FetchApplyError(f"Candidate write_date changed for {key[0]}/{key[1]}.")
    def _validate_progress_consistency(self, run_uuid: str, header: dict[str, Any], totals: dict[str, int]) -> None:
        with self.pg.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT progress FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).scalar()
        progress = parse_progress_json(row)
        if not progress.get("fetch_apply_complete"):
            raise FetchApplyError("Completed fetch/apply progress is missing its completion marker.", requires_new_retry=True)
        if progress.get("fetch_apply_completion_fingerprint") != header["completion_fingerprint"]:
            raise FetchApplyError("Completed fetch/apply progress completion fingerprint contradicts durable evidence.", requires_new_retry=True)
        if sorted(progress.get("fetch_apply_models_planned") or []) != sorted(header["models"]):
            raise FetchApplyError("Completed fetch/apply progress model plan contradicts the header.", requires_new_retry=True)
        if sorted(progress.get("fetch_apply_models_completed") or []) != sorted(header["models"]):
            raise FetchApplyError("Completed fetch/apply progress model completion contradicts the header.", requires_new_retry=True)
        if int(progress.get("fetch_apply_records_requested", 0)) != totals["records_requested"]:
            raise FetchApplyError("Completed fetch/apply progress requested count contradicts durable evidence.")
        if int(progress.get("fetch_apply_records_fetched", 0)) != totals["records_fetched"]:
            raise FetchApplyError("Completed fetch/apply progress fetched count contradicts durable evidence.")
        if int(progress.get("fetch_apply_records_missing_at_fetch", 0)) != totals["records_missing"]:
            raise FetchApplyError("Completed fetch/apply progress missing count contradicts durable evidence.")
        if int(progress.get("fetch_apply_records_source_drift", 0)) != totals["source_drift"]:
            raise FetchApplyError("Completed fetch/apply progress drift count contradicts durable evidence.")
        if int(progress.get("fetch_apply_inserted", 0)) != totals["inserted"]:
            raise FetchApplyError("Completed fetch/apply progress inserted count contradicts durable evidence.")
        if int(progress.get("fetch_apply_updated", 0)) != totals["updated"]:
            raise FetchApplyError("Completed fetch/apply progress updated count contradicts durable evidence.")
        if int(progress.get("fetch_apply_unchanged", 0)) != totals["unchanged"]:
            raise FetchApplyError("Completed fetch/apply progress unchanged count contradicts durable evidence.")
        started = progress.get("fetch_apply_started_at")
        finished = progress.get("fetch_apply_finished_at")
        elapsed = progress.get("fetch_apply_elapsed_seconds")
        if not started or not finished or elapsed is None:
            raise FetchApplyError("Completed fetch/apply progress timestamps are incomplete.")
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        finished_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        if finished_dt < started_dt or round((finished_dt - started_dt).total_seconds(), 6) != float(elapsed):
            raise FetchApplyError("Completed fetch/apply progress elapsed time is inconsistent with its timestamps.")

    def _validate_completed(
        self, run_uuid: str, company_id: int, base_snapshot: Any,
        header: dict[str, Any], *, idempotent: bool,
    ) -> dict[str, Any]:
        with self.pg.engine.connect() as conn:
            run = conn.execute(text("""
                SELECT status, stage, selected_domains FROM ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().first()
        if not run:
            raise FetchApplyError("Refresh run was not found.", requires_new_retry=True)
        if str(run["status"]) != "RECONCILING" or str(run["stage"]) != "RECONCILING":
            raise FetchApplyError(
                f"Completed fetch/apply evidence exists while the run is {run['status']}/{run['stage']}; "
                "a RECONCILING summary would be a false success.",
                requires_new_retry=True,
            )
        detection = self._detection_inputs(run_uuid, company_id, base_snapshot, run["selected_domains"])
        self._validate_header_immutables(
            header, company_id, base_snapshot, run["selected_domains"], detection,
            expect_complete=True,
        )
        self._validate_candidate_rows(run_uuid, str(header["base_snapshot_run_id"]))
        self._validate_evidence_reconciliation(run_uuid, detection)
        if (
            header["manifest_completion_fingerprint"] != detection["manifest_completion_fingerprint"]
            or header["manifest_row_count"] != detection["manifest_row_count"]
        ):
            raise FetchApplyError("Completed fetch/apply header contradicts the manifest.", requires_new_retry=True)
        totals = self._evidence_totals(run_uuid)
        if totals["records_requested"] != header["manifest_row_count"]:
            raise FetchApplyError("Completed fetch/apply evidence row count changed.")
        model_counts = self._model_counts(run_uuid, header["models"])
        expected = self._completion_fingerprint(company_id, header, detection, model_counts)
        if expected != header["completion_fingerprint"]:
            raise FetchApplyError("Completed fetch/apply completion fingerprint changed.")
        if header["model_fetch_counts"] != model_counts:
            raise FetchApplyError("Completed fetch/apply header model counts contradict durable evidence.")
        expected_models = sorted(header["models"])
        if sorted(model_counts) != expected_models:
            raise FetchApplyError("Completed fetch/apply model counts do not match the plan.")
        for model in expected_models:
            expected_count = int(detection["model_row_counts"].get(model, 0))
            if model_counts[model]["records_requested"] != expected_count:
                raise FetchApplyError(f"Completed fetch/apply evidence count changed for {model}.")
        self._validate_progress_consistency(run_uuid, header, totals)
        return self._summary(run_uuid, company_id, totals, model_counts, idempotent=idempotent)
    def _summary(
        self, run_uuid: str, company_id: int, totals: dict[str, int],
        model_counts: dict[str, dict[str, int]], *, idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "run_id": run_uuid,
            "company_id": company_id,
            "current_state": "RECONCILING",
            "last_completed_stage": "FETCHING",
            "next_required_stage": "RECONCILING",
            "records_requested": totals["records_requested"],
            "records_fetched": totals["records_fetched"],
            "records_missing_at_fetch": totals["records_missing"],
            "source_drift": totals["source_drift"],
            "inserted": totals["inserted"],
            "updated": totals["updated"],
            "unchanged": totals["unchanged"],
            "applied_total": totals["inserted"] + totals["updated"] + totals["unchanged"],
            "models_completed": list(model_counts),
            "idempotent": bool(idempotent),
            "requires_new_retry": False,
        }
