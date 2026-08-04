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
from src.control_tower.contracts import resolve_domain_selection
from src.control_tower.progress import parse_progress_json, serialize_progress
from src.control_tower.refresh import REFRESH_LOCK_KEY
from src.control_tower.refresh_state import validate_transition
from src.control_tower.relation_extractor import MODEL_SPECS
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


# Field type contract derived from the approved extractor LINK_SPECS plus the
# documented many2one relation fields the extractor already normalizes.
# Any MODEL_SPECS field not declared here is treated as a scalar.
_MANY2ONE_FIELDS: dict[str, tuple[str, ...]] = {
    "sale.order": ("partner_id", "company_id", "x_studio_io_1"),
    "sale.order.line": ("order_id", "product_id", "product_uom", "company_id"),
    "approval.request": ("category_id", "request_owner_id", "company_id"),
    "approval.product.line": ("approval_request_id", "product_id", "product_uom_id", "company_id"),
    "mrp.production": ("product_id", "product_uom_id", "company_id"),
    "purchase.order": ("company_id",),
    "purchase.order.line": ("order_id", "product_id", "product_uom", "company_id",
                            "x_studio_many2one_field_iJ0j0", "x_studio_many2one_field_ij0j0",
                            "x_studio_many2one_field_n6i7C", "x_studio_many2one_field_n6i7c",
                            "x_studio_jo"),
    "stock.picking": ("sale_id", "backorder_id", "partner_id", "picking_type_id", "company_id"),
    "stock.move": ("picking_id", "purchase_line_id", "sale_line_id",
                   "raw_material_production_id", "production_id", "product_id",
                   "product_uom", "location_id", "location_dest_id", "company_id"),
    "account.move": ("purchase_id", "reversed_entry_id", "company_id"),
    "account.move.line": ("move_id", "account_id", "partner_id", "product_id", "company_id"),
    "account.partial.reconcile": ("debit_move_id", "credit_move_id", "company_id"),
}
_MANY2MANY_FIELDS: dict[str, tuple[str, ...]] = {
    "mrp.production": ("move_raw_ids", "move_finished_ids"),
    "account.move.line": ("sale_line_ids",),
}


def _field_type(model: str, field: str) -> str:
    if field in _MANY2ONE_FIELDS.get(model, ()):
        return "many2one"
    if field in _MANY2MANY_FIELDS.get(model, ()):
        return "many2many"
    return "scalar"


def _normalize_field_value(value: Any, model: str, field: str) -> Any:
    field_type = _field_type(model, field)
    if value is False:
        return None
    if field_type == "many2one":
        if value is None:
            return None
        return {"id": _relation_id(value, f"{model}.{field}"), "name": _relation_name(value)}
    if field_type == "many2many":
        if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
            raise FetchApplyError(f"{model}.{field} must be a many2many integer list.")
        return list(value)
    return value


def _build_field_contract(model: str) -> tuple[str, ...]:
    spec = next(spec for spec in MODEL_SPECS if spec.model == model)
    required = {"id", "write_date"}
    if not required.issubset(spec.fields):
        raise FetchApplyError(f"Approved snapshot fields are incomplete for {model}.")
    return tuple(dict.fromkeys(spec.fields))

def _normalize_record(record: Mapping[str, Any], model: str, company_id: int) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise FetchApplyError(f"Odoo fetch response contained a non-object row for {model}.")
    fields = _build_field_contract(model)
    unexpected = set(record) - set(fields)
    if unexpected:
        raise FetchApplyError(f"Odoo fetch response contained unexpected fields for {model}: {sorted(unexpected)}")
    missing = set(fields) - set(record)
    if missing:
        raise FetchApplyError(f"Odoo fetch response omitted approved fields for {model}: {sorted(missing)}")
    normalized = {
        field: _normalize_field_value(record[field], model, field)
        for field in fields
    }
    record_id = _positive_id(normalized["id"], f"{model}.id")
    company = normalized.get("company_id")
    if company is None:
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
            self._ensure_no_contradictory_evidence(run_uuid, detection)
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
                       manifest_row_count, batch_size, contract_version, status,
                       started_at, finished_at, duration_seconds,
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
        with self.pg.engine.connect() as conn:
            header = conn.execute(text("""
                SELECT run_id::text, company_id, base_snapshot_run_id::text,
                       selected_domains, models, status, completion_fingerprint,
                       manifest_row_count, model_row_counts
                FROM ct_change_detection_run
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().first()
            manifest_total = conn.execute(text("""
                SELECT COUNT(*) FROM ct_change_manifest
                WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).scalar()
        if not header:
            raise FetchApplyError("Completed change detection header is missing.", requires_new_retry=True)
        if header["status"] != "COMPLETE":
            raise FetchApplyError("Change detection is not durably complete.", requires_new_retry=True)
        if int(header["company_id"]) != company_id or str(header["base_snapshot_run_id"]) != str(base_snapshot):
            raise FetchApplyError("Change detection evidence belongs to another company or base snapshot.")
        if int(header["manifest_row_count"]) != int(manifest_total):
            raise FetchApplyError("Change manifest row count does not match the completed detection header.")
        return {
            "manifest_completion_fingerprint": str(header["completion_fingerprint"]),
            "manifest_row_count": int(header["manifest_row_count"]),
            "models": list(header["models"]),
            "model_row_counts": dict(header["model_row_counts"] or {}),
        }

    def _ensure_no_contradictory_evidence(self, run_uuid: str, detection: dict[str, Any]) -> None:
        with self.pg.engine.connect() as conn:
            header = conn.execute(text("""
                SELECT status, manifest_completion_fingerprint, manifest_row_count
                FROM ct_fetch_apply_run WHERE run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().first()
        if header is None:
            return
        if header["status"] == "COMPLETE":
            raise FetchApplyError("Completed fetch/apply evidence exists without a completion progress marker.")
        if (
            header["manifest_completion_fingerprint"] != detection["manifest_completion_fingerprint"]
            or header["manifest_row_count"] != detection["manifest_row_count"]
        ):
            raise FetchApplyError(
                "Existing fetch/apply evidence contradicts the completed manifest.",
                requires_new_retry=True,
            )

    def _load_or_create_header(
        self, run_uuid: str, company_id: int, base_snapshot: Any,
        selected_domains: Any, detection: dict[str, Any], timestamp: datetime,
    ) -> dict[str, Any]:
        resolved_domains = sorted(str(domain.key) for domain in resolve_domain_selection(selected_domains))
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ct_fetch_apply_run
                    (run_id, company_id, base_snapshot_run_id, selected_domains,
                     models, manifest_completion_fingerprint, manifest_row_count,
                     batch_size, contract_version, status, started_at)
                VALUES (CAST(:run_id AS UUID), :company_id, CAST(:base AS UUID),
                        CAST(:domains AS JSONB), CAST(:models AS JSONB),
                        :manifest_fingerprint, :manifest_row_count, :batch_size,
                        :contract_version, 'RUNNING', :started_at)
                ON CONFLICT (run_id) DO NOTHING
            """), {
                "run_id": run_uuid, "company_id": company_id, "base": base_snapshot,
                "domains": json.dumps(resolved_domains),
                "models": json.dumps(detection["models"]),
                "manifest_fingerprint": detection["manifest_completion_fingerprint"],
                "manifest_row_count": detection["manifest_row_count"],
                "batch_size": self._batch_size,
                "contract_version": FETCH_APPLY_CONTRACT_VERSION,
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

    def _fetch_and_apply_batch(
        self, run_uuid: str, model: str, manifest_rows: list[dict[str, Any]],
        batch_number: int, batch_size: int, started: datetime, odoo_client,
    ) -> dict[str, int]:
        fields = list(_build_field_contract(model))
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
            normalized = _normalize_record(record, model, company_id)
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
                    "write_date": row["write_date"], "payload": row["payload"],
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
            conn.execute(text("""
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

    def _finalize(
        self, run_uuid: str, company_id: int, header: dict[str, Any],
        progress: dict[str, Any], timestamp: datetime,
        detection: dict[str, Any], *, idempotent: bool,
    ) -> dict[str, Any]:
        if not idempotent:
            self._fire("before_completion")
        self._validate_candidate_rows(run_uuid)
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
            conn.execute(text("""
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
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET progress = CAST(:progress AS JSONB), heartbeat_at = :now
                WHERE run_id = CAST(:run_uuid AS UUID)
            """), {
                "run_uuid": run_uuid, "progress": serialize_progress(progress),
                "now": timestamp,
            })
            validate_transition("FETCHING", "RECONCILING")
            conn.execute(text("""
                UPDATE ct_extraction_run
                SET status = 'RECONCILING', stage = 'RECONCILING',
                    stage_started_at = :now, heartbeat_at = :now
                WHERE run_id = CAST(:run_uuid AS UUID) AND status = 'FETCHING'
            """), {"run_uuid": run_uuid, "now": timestamp})
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
                SELECT model, record_id, payload_fingerprint, apply_status
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
                ORDER BY model, record_id
            """), {"run_id": run_uuid}).all()
        chunks = [FETCH_APPLY_CONTRACT_VERSION]
        for row in rows:
            chunks.append(json.dumps({
                "model": str(row[0]), "record_id": int(row[1]),
                "payload_fingerprint": row[2], "apply_status": str(row[3]),
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
            "evidence_fingerprint": self._evidence_fingerprint(header["run_id"]),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _validate_candidate_rows(self, run_uuid: str) -> None:
        with self.pg.engine.connect() as conn:
            evidence = conn.execute(text("""
                SELECT model, record_id, payload_fingerprint, apply_status
                FROM ct_fetch_apply_evidence
                WHERE run_id = CAST(:run_id AS UUID)
                  AND fetch_status = 'FETCHED'
            """), {"run_id": run_uuid}).mappings().all()
            snapshots = conn.execute(text("""
                SELECT model, record_id, payload
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            """), {"run_id": run_uuid}).mappings().all()
        snapshot_by_key = {(str(row["model"]), int(row["record_id"])): row["payload"] for row in snapshots}
        for row in evidence:
            key = (str(row["model"]), int(row["record_id"]))
            payload = snapshot_by_key.get(key)
            if payload is None:
                raise FetchApplyError(
                    f"Applied candidate row is missing for {row['model']}/{row['record_id']}.",
                    requires_new_retry=True,
                )
            if not isinstance(payload, dict):
                raise FetchApplyError(f"Candidate payload is malformed for {row['model']}/{row['record_id']}.")
            if isinstance(payload.get("write_date"), str):
                try:
                    payload = dict(payload)
                    payload["write_date"] = datetime.fromisoformat(payload["write_date"].replace("Z", "+00:00"))
                except ValueError:
                    raise FetchApplyError(
                        f"Candidate payload write_date is malformed for {row['model']}/{row['record_id']}."
                    )
            fingerprint = _jsonb_fingerprint(payload)
            if fingerprint != row["payload_fingerprint"]:
                raise FetchApplyError(
                    f"Candidate row no longer matches recorded application evidence for {row['model']}/{row['record_id']}.",
                    requires_new_retry=True,
                )

    def _validate_completed(
        self, run_uuid: str, company_id: int, base_snapshot: Any,
        header: dict[str, Any], *, idempotent: bool,
    ) -> dict[str, Any]:
        detection = self._detection_inputs(run_uuid, company_id, base_snapshot, header["selected_domains"])
        self._validate_candidate_rows(run_uuid)
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
        expected_models = sorted(header["models"])
        if sorted(model_counts) != expected_models:
            raise FetchApplyError("Completed fetch/apply model counts do not match the plan.")
        for model in expected_models:
            expected_count = int(detection["model_row_counts"].get(model, 0))
            if model_counts[model]["records_requested"] != expected_count:
                raise FetchApplyError(f"Completed fetch/apply evidence count changed for {model}.")
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
