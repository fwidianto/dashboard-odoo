"""Control Tower query contracts and PostgreSQL-only publication service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from src.clients.postgres_client import PostgresClient
from src.control_tower.relation_extractor import ControlTowerRelationExtractor
from src.control_tower.v03 import (
    CATEGORIES,
    CLOSE_REASONS,
    CLOSE_REASONS_REQUIRING_NOTE,
    ensure_v03_schema,
    new_batch_id,
    validate_close,
)
from src.utils.settings import get_settings

STATUS_PRESENTATION = {
    "VALIDATED": ("Sesuai", "compliant"),
    "MISMATCH": ("Masalah Aktif", "active"),
    "PARTIAL_MATCH": ("Perlu Ditinjau", "review"),
    "DATA_EXCEPTION": ("Bukti Sistem Belum Lengkap", "incomplete"),
    "DATA_LINKAGE_GAP": ("Hubungan Dokumen Belum Lengkap", "incomplete"),
    "DOCUMENT_LINK_GAP": ("Hubungan Dokumen Belum Lengkap", "incomplete"),
    "MANUAL_EVIDENCE_REQUIRED": ("Memerlukan Bukti Manual", "manual"),
    "HISTORICAL_EXPOSURE": ("Catatan Historis", "historical"),
    "DATE_SCOPE_UNKNOWN": ("Tanggal Dokumen Belum Tersedia", "incomplete"),
    "MAPPING_PENDING": ("Belum Dapat Diperiksa Otomatis", "pending"),
    "NOT_TESTED": ("Belum Dapat Diperiksa Otomatis", "pending"),
    "VALID_EXCEPTION": ("Catatan Historis", "historical"),
}

RULE_BUSINESS_CONTENT = {
    "SO-PO-001": {
        "title": "Referensi PO pelanggan pada Sales Order belum lengkap",
        "explanation": "Referensi PO pelanggan yang diperlukan belum tersedia pada Sales Order.",
        "expected": "Referensi PO pelanggan yang diwajibkan tersedia pada Sales Order.",
        "impact": "Verifikasi pesanan dan penelusuran dokumen pelanggan dapat tertunda.",
    },
    "SO-SOURCE-001": {
        "title": "Sumber pemenuhan Sales Order belum dapat dipastikan",
        "explanation": "Bukti sumber pemenuhan belum cukup pada tingkat baris Sales Order.",
        "expected": "Sumber pemenuhan setiap baris Sales Order didukung bukti yang dipublikasikan.",
        "impact": "Kebutuhan produksi atau pengadaan belum dapat dipastikan otomatis.",
    },
    "SO-CANCEL-001": {
        "title": "Sales Order dibatalkan, tetapi dokumen operasional masih terbuka",
        "explanation": "Dokumen lanjutan yang didukung graph masih terbuka setelah Sales Order dibatalkan.",
        "expected": "Tidak ada dokumen operasional terbuka setelah Sales Order dibatalkan; dokumen selesai atau terposting tetap menjadi histori.",
        "impact": "Pekerjaan produksi, gudang, pengadaan, atau penagihan perlu ditinjau.",
    },
    "PO-CANCEL-001": {
        "title": "Purchase Order dibatalkan, tetapi penerimaan masih terbuka",
        "explanation": "Penerimaan yang didukung relasi native masih terbuka untuk PO aktif-scope 2026 yang dibatalkan.",
        "expected": "Tidak ada penerimaan operasional terbuka untuk Purchase Order scope 2026 yang dibatalkan.",
        "impact": "Gudang dapat melihat pekerjaan penerimaan untuk pembelian yang sudah dibatalkan.",
    },
    "PO-DRAFT-001": {
        "title": "Purchase Order draft memiliki dokumen lanjutan",
        "explanation": "PO draft dan dokumen lanjutannya memerlukan peninjauan; histori Reset to Draft tidak disimpulkan otomatis.",
        "expected": "Dokumen lanjutan selaras dengan status Purchase Order yang sedang dikoreksi.",
        "impact": "Dokumen lanjutan dapat tidak selaras dengan PO yang sedang dikoreksi.",
    },
    "SO-IO-MO-001": {
        "title": "Hubungan Sales Order, Internal Order, dan produksi perlu ditinjau",
        "explanation": "Bukti pada tingkat baris belum cukup untuk menyimpulkan penanganan Manufacturing Order.",
        "expected": "Penanganan Manufacturing Order dapat ditentukan dari bukti baris Sales Order dan hubungan Internal Order yang lengkap.",
        "impact": "Rencana produksi dapat terbaca tanpa konteks sumber pemenuhan yang lengkap.",
    },
    "IO-PROD-001": {
        "title": "Bukti produksi untuk Internal Order belum lengkap",
        "explanation": "Bukti produksi pada pasangan produk dan satuan ukur yang sama belum lengkap.",
        "expected": "Bukti produksi tersedia pada pasangan produk dan satuan ukur yang sama.",
        "impact": "Kemajuan produksi belum dapat dinilai otomatis dengan keyakinan memadai.",
    },
    "IO-UTIL-001": {
        "title": "Bukti pemanfaatan Internal Order belum lengkap",
        "explanation": "Hubungan dokumen dan kuantitas belum cukup untuk menilai pemanfaatan Internal Order.",
        "expected": "Hubungan dokumen dan kuantitas cukup untuk menilai pemanfaatan Internal Order.",
        "impact": "Kebutuhan belum termanfaatkan atau alokasi ganda dapat tidak terlihat.",
    },
}

HEADER_FIELDS = {
    "sale.order": (
        ("name", "Nomor SO"),
        ("state", "Status"),
        ("partner_id", "Customer"),
        ("client_order_ref", "Customer Reference"),
        ("date_order", "Tanggal Order"),
        ("commitment_date", "Delivery Date"),
    ),
    "purchase.order": (
        ("name", "Nomor PO"),
        ("state", "Status"),
        ("date_order", "Tanggal Order"),
    ),
    "approval.request": (("name", "Internal Order"), ("request_status", "Status")),
    "mrp.production": (("name", "Manufacturing Order"), ("state", "Status"), ("origin", "Sumber")),
    "stock.picking": (("name", "Dokumen"), ("state", "Status"), ("origin", "Sumber")),
    "account.move": (
        ("name", "Invoice"),
        ("state", "Status"),
        ("payment_state", "Status pembayaran"),
        ("amount_total", "Total"),
        ("amount_residual", "Sisa"),
    ),
}

LINE_FIELDS = {
    "sale.order.line": (
        ("product_id", "Produk"),
        ("product_uom_qty", "Quantity"),
        ("product_uom", "UoM"),
        ("price_unit", "Unit Price"),
        ("qty_delivered", "Delivered"),
        ("qty_invoiced", "Invoiced"),
    ),
    "approval.product.line": (
        ("product_id", "Produk"),
        ("quantity", "Quantity"),
        ("product_uom_id", "UoM"),
    ),
    "purchase.order.line": (
        ("product_id", "Produk"),
        ("product_qty", "Quantity"),
        ("product_uom", "UoM"),
        ("qty_received", "Received"),
        ("qty_invoiced", "Invoiced"),
    ),
}

MODULE_LABELS = {
    "sale.order": "Sales",
    "sale.order.line": "Sales",
    "approval.request": "Approval / Internal Order",
    "approval.product.line": "Approval / Internal Order",
    "mrp.production": "Manufacturing",
    "purchase.order": "Purchase",
    "purchase.order.line": "Purchase",
    "stock.picking": "Receipt / Delivery",
    "stock.move": "Receipt / Delivery",
    "account.move": "Invoice",
    "account.move.line": "Invoice",
    "account.partial.reconcile": "Payment",
}

REFRESH_JOB_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ct_refresh_job (
    job_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    phase TEXT NOT NULL,
    message TEXT NOT NULL,
    changed_documents BIGINT NOT NULL DEFAULT 0,
    recalculated_checks BIGINT NOT NULL DEFAULT 0,
    result JSONB,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
)
"""
REFRESH_JOB_ACTIVE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ct_refresh_job_one_active
ON ct_refresh_job ((1)) WHERE status IN ('QUEUED', 'RUNNING')
"""


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def display_value(value: Any) -> Any:
    """Return a safe display scalar from a normalized snapshot value."""
    if value in (None, False, ""):
        return None
    if isinstance(value, dict):
        return value.get("name") or value.get("display_name") or value.get("id")
    if isinstance(value, list):
        values = [display_value(item) for item in value]
        return ", ".join(str(item) for item in values if item not in (None, "")) or None
    return json_safe(value)


def display_document_number(value: Any) -> str:
    """Normalize missing or Odoo-unassigned document numbers for investigation UI."""
    displayed = display_value(value)
    if displayed is None or str(displayed).strip() in {"", "/"}:
        return "Belum ditemukan"
    return str(displayed)


class ControlTowerService:
    """Query layer plus atomic PostgreSQL publication; Odoo stays read-only."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        self.pg = postgres_client or PostgresClient()
        self.odoo_base_url = get_settings().odoo.url.rstrip("/")

    def _rows(self, sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        with self.pg.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return [
                {key: json_safe(value) for key, value in row.items()}
                for row in result.mappings().all()
            ]

    def _row(self, sql: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    def health(self) -> dict[str, Any]:
        run = self._row("""
            SELECT run_id, started_at, completed_at, company_id, model_counts
            FROM vw_ct_current_run
        """)
        counts = self._row("""
            SELECT
                (SELECT COUNT(*) FROM vw_ct_native_record_snapshot_current) AS snapshot_count,
                (SELECT COUNT(*) FROM vw_ct_document_links) AS link_count,
                (SELECT COUNT(*) FROM mv_ct_rule_results) AS rule_result_count,
                (SELECT COUNT(*) FROM mv_ct_exception_worklist) AS exception_count
        """) or {}
        refresh = (run or {}).get("model_counts", {}).get("_refresh", {}) if run else {}
        if run:
            public_counts = dict(run.get("model_counts") or {})
            public_refresh = dict(public_counts.get("_refresh") or {})
            public_refresh.pop("source_fingerprint", None)
            public_refresh.pop("source_binding", None)
            public_counts["_refresh"] = public_refresh
            run = {**run, "model_counts": public_counts}
        return {
            "status": "READY" if run else "NO_COMPLETED_EXTRACTION",
            "latest_run": run,
            "last_successful_odoo_sync_at": refresh.get("last_successful_odoo_sync_at"),
            "changed_documents": refresh.get("changed_documents"),
            "recalculated_checks": len(refresh.get("recalculated_rule_ids") or []),
            "unrecalculated_rule_ids": refresh.get("unrecalculated_rule_ids") or [],
            **counts,
            "read_only": True,
            "payment_kpi_published": False,
            "runtime_materialized": True,
        }

    @staticmethod
    def _status(raw_status: str) -> dict[str, str]:
        label, category = STATUS_PRESENTATION.get(raw_status, (raw_status, "pending"))
        return {"code": raw_status, "label": label, "category": category}

    @staticmethod
    def _business_content(rule_id: str, fallback: str) -> dict[str, str]:
        return RULE_BUSINESS_CONTENT.get(
            rule_id,
            {
                "title": fallback,
                "explanation": "Kondisi ini memerlukan bukti tambahan sebelum kesimpulan operasional dibuat.",
                "expected": "Kondisi memenuhi pemeriksaan SOP dengan bukti sistem yang memadai.",
                "impact": "Dampak belum dapat dipastikan otomatis.",
            },
        )

    def _legacy_findings(self) -> dict[str, Any]:
        rows = self._rows("""
            WITH business_cases AS (
                SELECT DISTINCT ON (issue_id)
                    issue_id, rule_id, rule_name, validation_status, owner, sop_section,
                    document_model, document_id, document_number, detected_at
                FROM mv_ct_exception_worklist
                WHERE validation_status IN (
                    'MISMATCH', 'PARTIAL_MATCH', 'DATA_EXCEPTION',
                    'DATA_LINKAGE_GAP', 'DOCUMENT_LINK_GAP'
                )
                ORDER BY issue_id, detected_at DESC
            )
            SELECT
                rule_id, rule_name, validation_status, owner, sop_section,
                COUNT(*) AS case_count,
                MIN(issue_id) AS first_case_id,
                MIN(document_model) AS sample_document_model,
                MIN(document_id) AS sample_document_id,
                MIN(document_number) AS sample_document_number,
                MAX(detected_at) AS last_checked_at
            FROM business_cases
            GROUP BY rule_id, rule_name, validation_status, owner, sop_section
            ORDER BY
                CASE validation_status
                    WHEN 'MISMATCH' THEN 1
                    WHEN 'PARTIAL_MATCH' THEN 2
                    ELSE 3
                END,
                rule_id
        """)
        findings: list[dict[str, Any]] = []
        summary = {"active": 0, "review": 0, "incomplete": 0}
        for row in rows:
            status = self._status(row["validation_status"])
            case_count = int(row["case_count"])
            if status["category"] in summary:
                summary[status["category"]] += case_count
            business = self._business_content(row["rule_id"], row["rule_name"])
            findings.append(
                {
                    "finding_id": f'{row["rule_id"]}:{row["validation_status"]}',
                    "rule_id": row["rule_id"],
                    "status": status,
                    "title": business["title"],
                    "business_explanation": business["explanation"],
                    "impact": business["impact"],
                    "process": row["sop_section"],
                    "process_owner": row["owner"],
                    "case_count": case_count,
                    "single_case_id": row["first_case_id"] if case_count == 1 else None,
                    "primary_document": {
                        "model": row["sample_document_model"],
                        "id": row["sample_document_id"],
                        "number": display_document_number(row["sample_document_number"]),
                    },
                    "last_checked_at": row["last_checked_at"],
                }
            )
        secondary = self._row("""
            SELECT COUNT(*) AS historical
            FROM vw_ct_po_cancellation_scope
            WHERE operational_exposure = 'HISTORICAL_EXPOSURE'
        """) or {"historical": 0}
        return {"summary": summary, "findings": findings, "secondary": secondary}

    def cases(
        self,
        *,
        case_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        validation_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if case_id:
            conditions.append("issue_id = :case_id")
            params["case_id"] = case_id
        if rule_id:
            conditions.append("rule_id = :rule_id")
            params["rule_id"] = rule_id
        if validation_status:
            conditions.append("validation_status = :validation_status")
            params["validation_status"] = validation_status
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        grouped = f"""
            WITH grouped AS (
                SELECT
                    issue_id, MIN(rule_id) AS rule_id, MIN(rule_name) AS rule_name,
                    MIN(sop_section) AS sop_section, MIN(document_model) AS document_model,
                    MIN(document_id) AS document_id, MIN(document_number) AS document_number,
                    MIN(validation_status) AS validation_status, MIN(severity) AS severity,
                    MIN(confidence) AS confidence, MIN(owner) AS owner,
                    JSONB_AGG(DISTINCT expected_condition) AS expected_conditions,
                    JSONB_AGG(DISTINCT actual_condition) AS actual_conditions,
                    JSONB_AGG(DISTINCT evidence) AS evidence,
                    MAX(detected_at) AS last_checked_at, COUNT(*) AS raw_record_count
                FROM mv_ct_exception_worklist
                {where}
                GROUP BY issue_id
            )
        """
        rows = self._rows(
            grouped + """
                SELECT * FROM grouped
                ORDER BY
                    CASE validation_status WHEN 'MISMATCH' THEN 1 WHEN 'PARTIAL_MATCH' THEN 2 ELSE 3 END,
                    rule_id, document_number NULLS LAST, document_id
                LIMIT :limit OFFSET :offset
            """,
            params,
        )
        total = self._row(grouped + "SELECT COUNT(*) AS total FROM grouped", params) or {"total": 0}
        return {
            "rows": [self._case_contract(row) for row in rows],
            "total": int(total["total"]),
            "limit": limit,
            "offset": offset,
        }

    def _case_contract(self, row: dict[str, Any]) -> dict[str, Any]:
        business = self._business_content(row["rule_id"], row["rule_name"])
        return {
            "case_id": row["issue_id"],
            "business_status": self._status(row["validation_status"]),
            "technical_status": row["validation_status"],
            "business_title": business["title"],
            "business_explanation": business["explanation"],
            "actual_summary": business["explanation"],
            "expected_summary": business["expected"],
            "actual": row["actual_conditions"],
            "expected": row["expected_conditions"],
            "impact": business["impact"],
            "primary_document": {
                "model": row["document_model"],
                "id": row["document_id"],
                "number": display_document_number(row["document_number"]),
            },
            "process": row["sop_section"],
            "process_owner": row["owner"],
            "evidence": row["evidence"],
            "missing_evidence": row["validation_status"]
            in {"DATA_EXCEPTION", "DATA_LINKAGE_GAP", "DOCUMENT_LINK_GAP", "PARTIAL_MATCH"},
            "technical_rule_reference": row["rule_id"],
            "confidence": row["confidence"],
            "severity": row["severity"],
            "raw_record_count": int(row["raw_record_count"]),
            "first_seen_at": None,
            "age_label": "Belum tersedia",
            "last_checked_at": row["last_checked_at"],
        }

    def case_detail(self, case_id: str) -> Optional[dict[str, Any]]:
        result = self.cases(case_id=case_id, limit=1, offset=0)
        case = next((item for item in result["rows"] if item["case_id"] == case_id), None)
        if case is None:
            return None
        primary = case["primary_document"]
        journey = self.journey(primary["model"], int(primary["id"]))
        case["related_documents"] = self._document_chain(journey)
        case["snapshot_timestamp"] = (journey.get("root") or {}).get("extracted_at")
        case["related_data"] = self.related_data(primary["model"], int(primary["id"]))
        return case

    @staticmethod
    def _document_chain(journey: dict[str, Any]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        root = journey.get("root")
        if root:
            key = (root["model"], int(root["record_id"]))
            seen.add(key)
            documents.append(
                {
                    "model": root["model"],
                    "id": root["record_id"],
                    "number": display_document_number(root.get("document_number")),
                    "state": root.get("state"),
                    "relationship_type": "Dokumen utama",
                    "evidence_type": "Hubungan langsung",
                }
            )
        for link in journey.get("links", []):
            key = (link["child_model"], int(link["child_id"]))
            if key in seen:
                continue
            seen.add(key)
            documents.append(
                {
                    "model": link["child_model"],
                    "id": link["child_id"],
                    "number": display_document_number(link.get("child_number")),
                    "state": link.get("child_state"),
                    "relationship_type": link.get("link_type"),
                    "evidence_type": (
                        "Hubungan langsung" if link.get("depth") == 1 else "Hubungan turunan"
                    ),
                    "confidence": link.get("confidence"),
                }
            )
        return documents

    def related_data(self, root_model: str, root_id: int) -> dict[str, Any]:
        root = self._row(
            """
            SELECT model, record_id, document_number, state, write_date, extracted_at, payload
            FROM vw_ct_native_record_snapshot_current
            WHERE model = :root_model AND record_id = :root_id
        """,
            {"root_model": root_model, "root_id": root_id},
        )
        if root is None:
            return {"root": None, "header": [], "line_items": [], "document_groups": []}
        payload = root.pop("payload") or {}
        header = []
        for key, label in HEADER_FIELDS.get(
            root_model,
            (("name", "Dokumen"), ("state", "Status")),
        ):
            value = (
                display_document_number(payload.get(key))
                if key in {"name", "display_name"}
                else display_value(payload.get(key))
            )
            if value is not None:
                header.append({"key": key, "label": label, "value": value})
        journey = self.journey(root_model, root_id)
        relationship_by_key: dict[tuple[str, int], dict[str, Any]] = {}
        for link in journey.get("links", []):
            key = (link["child_model"], int(link["child_id"]))
            relationship_by_key.setdefault(
                key,
                {
                    "relationship_type": link.get("link_type"),
                    "evidence_type": (
                        "Hubungan langsung" if link.get("depth") == 1 else "Hubungan turunan"
                    ),
                    "confidence": link.get("confidence"),
                },
            )
        linked_keys = {
            (link["child_model"], int(link["child_id"])) for link in journey.get("links", [])
        } | {(link["parent_model"], int(link["parent_id"])) for link in journey.get("links", [])}
        linked_keys.discard((root_model, root_id))
        snapshots: list[dict[str, Any]] = []
        if linked_keys:
            values = [{"model": model, "record_id": record_id} for model, record_id in linked_keys]
            snapshots = self._rows(
                """
                SELECT model, record_id, document_number, state, write_date, payload
                FROM vw_ct_native_record_snapshot_current
                WHERE (model, record_id) IN (
                    SELECT item ->> 'model', (item ->> 'record_id')::bigint
                    FROM JSONB_ARRAY_ELEMENTS(CAST(:keys AS JSONB)) item
                )
            """,
                {"keys": json.dumps(values)},
            )
        line_items: list[dict[str, Any]] = []
        groups: dict[str, list[dict[str, Any]]] = {}
        for snapshot in snapshots:
            item_payload = snapshot.pop("payload") or {}
            if snapshot["model"] in LINE_FIELDS:
                values = [
                    {"key": key, "label": label, "value": display_value(item_payload.get(key))}
                    for key, label in LINE_FIELDS[snapshot["model"]]
                    if display_value(item_payload.get(key)) is not None
                ]
                line_items.append(
                    {"model": snapshot["model"], "id": snapshot["record_id"], "values": values}
                )
            group = MODULE_LABELS.get(snapshot["model"], snapshot["model"])
            relationship = relationship_by_key.get(
                (snapshot["model"], int(snapshot["record_id"])),
                {
                    "relationship_type": None,
                    "evidence_type": "Hubungan turunan",
                    "confidence": None,
                },
            )
            groups.setdefault(group, []).append(
                {
                    "model": snapshot["model"],
                    "id": snapshot["record_id"],
                    "number": display_document_number(snapshot.get("document_number")),
                    "status": snapshot.get("state"),
                    "date": snapshot.get("write_date"),
                    **relationship,
                    "record_journey_url": (
                        f'/control-tower?view=journey&model={snapshot["model"]}&id={snapshot["record_id"]}'
                    ),
                }
            )
        document_groups = [
            {"module": module, "documents": documents}
            for module, documents in sorted(groups.items())
        ]
        document_groups.append(
            {
                "module": "Payment",
                "documents": [],
                "availability": "Belum dipublikasikan",
            }
        )
        return {
            "root": root,
            "header": header,
            "line_items": line_items,
            "document_groups": document_groups,
        }

    def refresh(self) -> dict[str, Any]:
        extractor = ControlTowerRelationExtractor(postgres_client=self.pg)
        try:
            return extractor.run_incremental()
        finally:
            extractor.odoo.close()

    def ensure_refresh_job_schema(self) -> None:
        with self.pg.engine.begin() as conn:
            conn.execute(text(REFRESH_JOB_SCHEMA_SQL))
            ensure_v03_schema(conn)
            conn.execute(text(REFRESH_JOB_ACTIVE_INDEX_SQL))

    @staticmethod
    def _refresh_job_columns() -> str:
        return """
            job_id::text AS job_id, status, phase, phase_label, message,
            current_work, completed_work_units, total_work_units, percentage,
            processed_records, total_records, changed_documents, recalculated_checks,
            result, failed_phase, failed_work, last_successful_batch, error_message,
            retryable_phase, checkpoint, retry_of::text AS retry_of, final_summary,
            created_at, started_at, updated_at, completed_at
        """

    def _legacy_start_refresh_job(self, *, retry_of: Optional[str] = None) -> dict[str, Any]:
        self.ensure_refresh_job_schema()
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                UPDATE ct_refresh_job
                SET status = 'FAILED', phase = 'FAILED',
                    message = 'Pembaruan sebelumnya terhenti; snapshot terakhir tetap dipertahankan.',
                    error_code = 'STALE_WORKER', failed_phase = phase,
                    failed_work = current_work, retryable_phase = phase,
                    error_message = 'Worker pembaruan tidak lagi aktif.',
                    updated_at = NOW(), completed_at = NOW()
                WHERE status IN ('QUEUED', 'RUNNING')
                  AND updated_at < NOW() - INTERVAL '30 minutes'
            """))
            active = conn.execute(text(f"""
                SELECT {self._refresh_job_columns()}
                FROM ct_refresh_job
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at DESC
                LIMIT 1
            """)).mappings().one_or_none()
            if active:
                return {**json_safe(dict(active)), "already_running": True}

        job_id = str(uuid4())
        try:
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                    INSERT INTO ct_refresh_job (job_id, status, phase, message)
                    VALUES (CAST(:job_id AS UUID), 'QUEUED', 'QUEUED', 'Pembaruan dijadwalkan…')
                """),
                    {"job_id": job_id},
                )
        except IntegrityError:
            active = self._row("""
                SELECT job_id::text AS job_id, status, phase, message,
                       changed_documents, recalculated_checks, created_at, updated_at
                FROM ct_refresh_job
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at DESC
                LIMIT 1
            """)
            if active:
                return {**active, "already_running": True}
            raise
        return {
            "job_id": job_id,
            "status": "QUEUED",
            "phase": "QUEUED",
            "message": "Pembaruan dijadwalkan…",
            "changed_documents": 0,
            "recalculated_checks": 0,
            "already_running": False,
        }

    def _legacy_refresh_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._row(
            """
            SELECT job_id::text AS job_id, status, phase, message,
                   changed_documents, recalculated_checks, result,
                   created_at, started_at, updated_at, completed_at
            FROM ct_refresh_job
            WHERE job_id = CAST(:job_id AS UUID)
        """,
            {"job_id": job_id},
        )

    def _legacy_run_refresh_job(self, job_id: str) -> None:
        with self.pg.engine.begin() as conn:
            result = conn.execute(
                text("""
                UPDATE ct_refresh_job
                SET status = 'RUNNING', phase = 'CHECKING',
                    message = 'Memeriksa perubahan Odoo…',
                    started_at = NOW(), updated_at = NOW()
                WHERE job_id = CAST(:job_id AS UUID) AND status = 'QUEUED'
            """),
                {"job_id": job_id},
            )
            if result.rowcount != 1:
                return

        def progress(
            phase: str,
            message: str,
            changed_documents: int,
            recalculated_checks: int,
        ) -> None:
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                    UPDATE ct_refresh_job
                    SET phase = :phase, message = :message,
                        changed_documents = :changed_documents,
                        recalculated_checks = :recalculated_checks,
                        updated_at = NOW()
                    WHERE job_id = CAST(:job_id AS UUID) AND status = 'RUNNING'
                """),
                    {
                        "job_id": job_id,
                        "phase": phase,
                        "message": message,
                        "changed_documents": changed_documents,
                        "recalculated_checks": recalculated_checks,
                    },
                )

        extractor = ControlTowerRelationExtractor(
            postgres_client=self.pg,
            progress_callback=progress,
        )
        try:
            refresh_result = extractor.run_incremental()
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                    UPDATE ct_refresh_job
                    SET status = 'COMPLETED', phase = 'COMPLETED',
                        message = :message,
                        changed_documents = :changed_documents,
                        recalculated_checks = :recalculated_checks,
                        result = CAST(:result AS JSONB), error_code = NULL,
                        updated_at = NOW(), completed_at = NOW()
                    WHERE job_id = CAST(:job_id AS UUID)
                """),
                    {
                        "job_id": job_id,
                        "message": (
                            "Tidak ada perubahan sejak pembaruan terakhir."
                            if refresh_result["outcome"] == "NO_CHANGES"
                            else "Data berhasil diperbarui."
                        ),
                        "changed_documents": refresh_result["changed_documents"],
                        "recalculated_checks": len(refresh_result["recalculated_rule_ids"]),
                        "result": json.dumps(refresh_result),
                    },
                )
        except Exception:
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                    UPDATE ct_refresh_job
                    SET status = 'FAILED', phase = 'FAILED',
                        message = 'Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil.',
                        error_code = 'INCREMENTAL_REFRESH_FAILED',
                        updated_at = NOW(), completed_at = NOW()
                    WHERE job_id = CAST(:job_id AS UUID)
                """),
                    {"job_id": job_id},
                )
        finally:
            extractor.odoo.close()

    def start_refresh_job(self, *, retry_of: Optional[str] = None) -> dict[str, Any]:
        """Queue one refresh from the last published checkpoint."""
        self.ensure_refresh_job_schema()
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                UPDATE ct_refresh_job
                SET status = 'FAILED', failed_phase = phase, failed_work = current_work,
                    retryable_phase = phase, phase = 'FAILED',
                    message = 'Pembaruan sebelumnya terhenti; data terakhir tetap dipertahankan.',
                    error_message = 'Worker pembaruan tidak lagi aktif.',
                    error_code = 'STALE_WORKER', updated_at = NOW(), completed_at = NOW()
                WHERE status IN ('QUEUED', 'RUNNING')
                  AND updated_at < NOW() - INTERVAL '30 minutes'
            """))
            active = conn.execute(text(f"""
                SELECT {self._refresh_job_columns()}
                FROM ct_refresh_job
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at DESC LIMIT 1
            """)).mappings().one_or_none()
            if active:
                return {**json_safe(dict(active)), "already_running": True}

        job_id = str(uuid4())
        try:
            with self.pg.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO ct_refresh_job (
                        job_id, status, phase, phase_label, message, current_work,
                        retry_of, checkpoint
                    ) VALUES (
                        CAST(:job_id AS UUID), 'QUEUED', 'PREPARATION', 'Persiapan',
                        'Pembaruan dijadwalkan…', 'Menunggu worker refresh',
                        CAST(:retry_of AS UUID), CAST(:checkpoint AS JSONB)
                    )
                """), {
                    "job_id": job_id,
                    "retry_of": retry_of,
                    "checkpoint": json.dumps({"publication": "last_successful"}),
                })
        except IntegrityError:
            active = self._row(f"""
                SELECT {self._refresh_job_columns()}
                FROM ct_refresh_job
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at DESC LIMIT 1
            """)
            if active:
                return {**active, "already_running": True}
            raise
        queued = self.refresh_job(job_id) or {}
        return {**queued, "already_running": False}

    def refresh_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._row(f"""
            SELECT {self._refresh_job_columns()}
            FROM ct_refresh_job
            WHERE job_id = CAST(:job_id AS UUID)
        """, {"job_id": job_id})

    def retry_refresh_job(self, job_id: str) -> dict[str, Any]:
        failed = self.refresh_job(job_id)
        if failed is None:
            raise ValueError("Refresh job tidak ditemukan.")
        if failed["status"] != "FAILED":
            raise ValueError("Hanya refresh yang gagal yang dapat dicoba lagi.")
        return self.start_refresh_job(retry_of=job_id)

    def run_refresh_job(self, job_id: str) -> None:
        run_started_at = datetime.now(timezone.utc)
        with self.pg.engine.begin() as conn:
            claimed = conn.execute(text("""
                UPDATE ct_refresh_job
                SET status = 'RUNNING', phase = 'PREPARATION', phase_label = 'Persiapan',
                    message = 'Menyiapkan refresh Control Tower…',
                    current_work = 'Membuka checkpoint terakhir yang berhasil',
                    started_at = NOW(), updated_at = NOW()
                WHERE job_id = CAST(:job_id AS UUID) AND status = 'QUEUED'
            """), {"job_id": job_id})
            if claimed.rowcount != 1:
                return

        def progress(
            phase: str,
            message: str,
            changed_documents: int,
            recalculated_checks: int,
            phase_label: Optional[str],
            current_work: Optional[str],
            completed_work_units: Optional[int],
            total_work_units: Optional[int],
            processed_records: Optional[int],
            total_records: Optional[int],
        ) -> None:
            percentage = (
                round(completed_work_units * 100 / total_work_units, 2)
                if completed_work_units is not None and total_work_units
                else 0
            )
            with self.pg.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE ct_refresh_job SET
                        phase = :phase, phase_label = COALESCE(:phase_label, phase_label),
                        message = :message, current_work = :current_work,
                        completed_work_units = COALESCE(:completed_work_units, completed_work_units),
                        total_work_units = COALESCE(:total_work_units, total_work_units),
                        percentage = :percentage, processed_records = :processed_records,
                        total_records = :total_records,
                        last_successful_batch = CASE
                            WHEN :processed_records IS NOT NULL THEN :current_work
                            ELSE last_successful_batch END,
                        changed_documents = :changed_documents,
                        recalculated_checks = :recalculated_checks, updated_at = NOW()
                    WHERE job_id = CAST(:job_id AS UUID) AND status = 'RUNNING'
                """), {
                    "job_id": job_id, "phase": phase, "phase_label": phase_label,
                    "message": message, "current_work": current_work,
                    "completed_work_units": completed_work_units,
                    "total_work_units": total_work_units, "percentage": percentage,
                    "processed_records": processed_records, "total_records": total_records,
                    "changed_documents": changed_documents,
                    "recalculated_checks": recalculated_checks,
                })

        extractor = ControlTowerRelationExtractor(postgres_client=self.pg, progress_callback=progress)
        try:
            refresh_result = extractor.run_incremental()
            completed_at = datetime.now(timezone.utc)
            lifecycle = (refresh_result.get("v03") or {}).get("finding_lifecycle") or {}
            duration_seconds = round((completed_at - run_started_at).total_seconds(), 2)
            final_summary = {
                "documents_changed": refresh_result["changed_documents"],
                "new_findings": int(lifecycle.get("new", 0)),
                "auto_resolved_findings": int(lifecycle.get("auto_resolved", 0)),
                "duration_seconds": duration_seconds,
                "duration": f"{duration_seconds:g} detik",
                "completed_at": completed_at.isoformat(),
            }
            with self.pg.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE ct_refresh_job SET
                        status = 'COMPLETED', phase = 'FINALIZE',
                        phase_label = 'Finalisasi dan publish', message = :message,
                        current_work = 'Dataset Control Tower telah dipublikasikan',
                        completed_work_units = total_work_units, percentage = 100,
                        changed_documents = :changed_documents,
                        recalculated_checks = :recalculated_checks,
                        result = CAST(:result AS JSONB), final_summary = CAST(:final_summary AS JSONB),
                        error_code = NULL, error_message = NULL,
                        updated_at = NOW(), completed_at = :completed_at
                    WHERE job_id = CAST(:job_id AS UUID)
                """), {
                    "job_id": job_id,
                    "message": (
                        "Tidak ada perubahan sejak pembaruan terakhir."
                        if refresh_result["outcome"] == "NO_CHANGES"
                        else "Data berhasil diperbarui."
                    ),
                    "changed_documents": refresh_result["changed_documents"],
                    "recalculated_checks": len(refresh_result["recalculated_rule_ids"]),
                    "result": json.dumps(refresh_result),
                    "final_summary": json.dumps(final_summary),
                    "completed_at": completed_at,
                })
        except Exception:
            with self.pg.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE ct_refresh_job SET
                        status = 'FAILED', failed_phase = phase, failed_work = current_work,
                        retryable_phase = phase, phase = 'FAILED',
                        message = 'Pembaruan Odoo gagal. Control Tower tetap menampilkan data terakhir yang berhasil.',
                        error_message = 'Tahap ini tidak selesai; data yang sebelumnya terbit tetap aman.',
                        error_code = 'INCREMENTAL_REFRESH_FAILED',
                        updated_at = NOW(), completed_at = NOW()
                    WHERE job_id = CAST(:job_id AS UUID)
                """), {"job_id": job_id})
        finally:
            extractor.odoo.close()

    def validation_summary(self) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT *
            FROM mv_ct_sop_validation_summary
            ORDER BY
                CASE overall_status
                    WHEN 'MISMATCH' THEN 1
                    WHEN 'DATA_LINKAGE_GAP' THEN 2
                    WHEN 'PARTIAL_MATCH' THEN 3
                    WHEN 'MANUAL_EVIDENCE_REQUIRED' THEN 4
                    WHEN 'NOT_TESTED' THEN 5
                    ELSE 6
                END,
                rule_id
        """)

    def exceptions(
        self,
        *,
        rule_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        owner: Optional[str] = None,
        process: Optional[str] = None,
        document: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if rule_id:
            conditions.append("rule_id = :rule_id")
            params["rule_id"] = rule_id
        if status:
            conditions.append("validation_status = :status")
            params["status"] = status
        if severity:
            conditions.append("severity = :severity")
            params["severity"] = severity
        if owner:
            conditions.append("owner = :owner")
            params["owner"] = owner
        if process:
            conditions.append("sop_section = :process")
            params["process"] = process
        normalized_document = (document or "").strip()
        if normalized_document:
            conditions.append(
                "POSITION(LOWER(:document) IN LOWER(COALESCE(document_number, ''))) > 0"
            )
            params["document"] = normalized_document
        if date_from:
            conditions.append("detected_at::date >= :date_from")
            params["date_from"] = date_from
        if date_to:
            conditions.append("detected_at::date <= :date_to")
            params["date_to"] = date_to

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._rows(
            f"""
            SELECT *
            FROM mv_ct_exception_worklist
            {where}
            ORDER BY severity_priority, rule_id, document_number NULLS LAST, document_id
            LIMIT :limit OFFSET :offset
        """,
            params,
        )
        total = (
            self._row(
                f"""
            SELECT COUNT(*) AS total
            FROM mv_ct_exception_worklist
            {where}
        """,
                params,
            )
            or {"total": 0}
        )
        return {"rows": rows, "total": total["total"], "limit": limit, "offset": offset}

    def po_cancellation_scope(
        self,
        *,
        date_scope: Optional[str] = None,
        operational_exposure: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return active, historical, and date-review PO cancellation records.

        This remains a PostgreSQL-only read model. ``date_order`` scope is
        calculated in SQL from targeted enrichment, never from ``write_date``.
        """
        allowed_scopes = {
            "ACTIVE_2026_PLUS",
            "HISTORICAL_PRE_2026",
            "DATE_SCOPE_UNKNOWN",
        }
        allowed_exposures = {
            "ACTIVE_ISSUE",
            "HISTORICAL_EXPOSURE",
            "DATE_REVIEW_REQUIRED",
            "NO_OPEN_RECEIPT",
        }
        if date_scope and date_scope not in allowed_scopes:
            raise ValueError("Unsupported PO cancellation date scope.")
        if operational_exposure and operational_exposure not in allowed_exposures:
            raise ValueError("Unsupported PO cancellation exposure.")

        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if date_scope:
            conditions.append("date_scope = :date_scope")
            params["date_scope"] = date_scope
        if operational_exposure:
            conditions.append("operational_exposure = :operational_exposure")
            params["operational_exposure"] = operational_exposure
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = self._rows(
            f"""
            SELECT *
            FROM vw_ct_po_cancellation_scope
            {where}
            ORDER BY date_scope, operational_exposure, purchase_order_id
            LIMIT :limit OFFSET :offset
        """,
            params,
        )
        total = self._row(
            f"SELECT COUNT(*) AS total FROM vw_ct_po_cancellation_scope {where}", params
        ) or {"total": 0}
        summary = self._rows("""
            SELECT
                date_scope,
                COUNT(*) AS cancelled_po_roots,
                COUNT(*) FILTER (WHERE operational_exposure = 'ACTIVE_ISSUE') AS masalah_aktif_2026_plus,
                COUNT(*) FILTER (WHERE operational_exposure = 'HISTORICAL_EXPOSURE') AS catatan_historis,
                COUNT(*) FILTER (WHERE operational_exposure = 'DATE_REVIEW_REQUIRED') AS tanggal_po_belum_tersedia,
                COUNT(*) FILTER (WHERE open_backorder_count > 0) AS open_backorders
            FROM vw_ct_po_cancellation_scope
            GROUP BY date_scope
            ORDER BY date_scope
        """)
        return {
            "summary": summary,
            "rows": rows,
            "total": total["total"],
            "limit": limit,
            "offset": offset,
        }

    def journey(self, root_model: str, root_id: int) -> dict[str, Any]:
        root = self._row(
            """
            SELECT model, record_id, document_number, state, company_id, company_name,
                   write_date, extracted_at
            FROM vw_ct_native_record_snapshot_current
            WHERE model = :root_model AND record_id = :root_id
        """,
            {"root_model": root_model, "root_id": root_id},
        )
        if root is None:
            return {"root": None, "links": [], "validations": []}

        links = self._rows(
            """
            SELECT
                path.depth, path.root_model, path.root_id, path.root_number,
                path.parent_model, path.parent_id, path.parent_number,
                parent_snapshot.state AS parent_state,
                path.child_model, path.child_id, path.child_number,
                child_snapshot.state AS child_state,
                path.link_type, path.confidence, path.link_path,
                CASE
                    WHEN path.depth = 1 THEN 'DIRECT_RELATION'
                    ELSE 'DERIVED_PATH'
                END AS relation_evidence
            FROM mv_ct_document_paths AS path
            LEFT JOIN vw_ct_native_record_snapshot_current AS parent_snapshot
              ON parent_snapshot.model = path.parent_model
             AND parent_snapshot.record_id = path.parent_id
            LEFT JOIN vw_ct_native_record_snapshot_current AS child_snapshot
              ON child_snapshot.model = path.child_model
             AND child_snapshot.record_id = path.child_id
            WHERE path.root_model = :root_model AND path.root_id = :root_id
            ORDER BY path.depth, path.parent_model, path.parent_id,
                     path.child_model, path.child_id
        """,
            {"root_model": root_model, "root_id": root_id},
        )
        validations = self._rows(
            """
            SELECT *
            FROM mv_ct_rule_results
            WHERE document_model = :root_model AND document_id = :root_id
            ORDER BY rule_id
        """,
            {"root_model": root_model, "root_id": root_id},
        )
        return {"root": root, "links": links, "validations": validations}

    def io_health(
        self,
        *,
        production_status: Optional[str] = None,
        utilization_status: Optional[str] = None,
        confidence: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if production_status:
            conditions.append("production_status = :production_status")
            params["production_status"] = production_status
        if utilization_status:
            conditions.append("utilization_status = :utilization_status")
            params["utilization_status"] = utilization_status
        if confidence:
            conditions.append("confidence = :confidence")
            params["confidence"] = confidence
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._rows(
            f"""
            SELECT *
            FROM vw_ct_io_health
            {where}
            ORDER BY
                CASE WHEN production_status = 'DATA_EXCEPTION' OR utilization_status = 'DATA_EXCEPTION' THEN 1 ELSE 2 END,
                internal_order_number,
                product_name
            LIMIT :limit OFFSET :offset
        """,
            params,
        )
        total = self._row(f"SELECT COUNT(*) AS total FROM vw_ct_io_health {where}", params) or {
            "total": 0
        }
        summary = (
            self._row("""
            SELECT
                COUNT(DISTINCT internal_order_id) AS internal_order_roots,
                COUNT(*) AS product_uom_rows,
                COUNT(*) FILTER (WHERE production_status = 'DATA_EXCEPTION')
                    AS production_evidence_gaps,
                COUNT(*) FILTER (WHERE utilization_status = 'DATA_EXCEPTION')
                    AS utilization_evidence_gaps
            FROM vw_ct_io_health
        """)
            or {
                "internal_order_roots": 0,
                "product_uom_rows": 0,
                "production_evidence_gaps": 0,
                "utilization_evidence_gaps": 0,
            }
        )
        return {
            "rows": rows,
            "summary": summary,
            "total": total["total"],
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _document_type(model: str, payload: Optional[dict[str, Any]] = None) -> str:
        payload = payload or {}
        if model == "sale.order":
            return "SO"
        if model == "mrp.production":
            return "MO"
        if model == "purchase.order":
            return "PO"
        if model == "approval.request":
            category = str((payload.get("category_id") or {}).get("name") or "").upper()
            return {"RKB": "RKB", "PEMBELIAN": "ROP"}.get(category, "IO")
        if model == "stock.picking":
            return "Receipt/LPB atau Delivery"
        if model == "account.move":
            return "Invoice / Vendor Bill"
        if model == "account.payment":
            return "Payment"
        return model

    def _native_url(self, model: str, record_id: int) -> str:
        fragment = urlencode({"id": record_id, "model": model, "view_type": "form"})
        return f"{self.odoo_base_url}/web#{fragment}"

    @staticmethod
    def _detail_url(model: str, record_id: int, tab: str = "summary") -> str:
        return "/control-tower?" + urlencode(
            {"view": "document", "model": model, "id": record_id, "tab": tab}
        )

    def _public_document(self, document: dict[str, Any]) -> dict[str, Any]:
        model = str(document.get("model") or "")
        raw_id = document.get("id")
        record_id = int(raw_id) if raw_id is not None else None
        result = {
            "type": str(document.get("type") or self._document_type(model)),
            "number": display_document_number(document.get("number")),
            "status": document.get("status"),
            "problematic": bool(document.get("problematic", True)),
        }
        if record_id is not None and model:
            result["open_url"] = self._native_url(model, record_id)
            result["detail_url"] = self._detail_url(model, record_id)
        for key in ("quantity", "product", "uom"):
            if document.get(key) is not None:
                result[key] = json_safe(document[key])
        return result

    @staticmethod
    def _affected_summary(documents: list[dict[str, Any]]) -> str:
        counts: dict[str, int] = {}
        for document in documents:
            label = str(document.get("type") or "dokumen")
            counts[label] = counts.get(label, 0) + 1
        if not counts:
            return "0 dokumen"
        if len(counts) == 1:
            label, count = next(iter(counts.items()))
            return f"{count} {label}" if label != "dokumen" else f"{count} dokumen"
        return ", ".join(f"{count} {label}" for label, count in counts.items())

    def _finding_contract(self, row: dict[str, Any]) -> dict[str, Any]:
        impacted = [self._public_document(item) for item in (row.get("impacted_documents") or [])]
        evidence = row.get("current_evidence") or {}
        line_labels = {
            "product": "Produk",
            "quantity": "Kuantitas",
            "uom": "Satuan",
            "untaxed_value": "Nilai sebelum pajak",
            "company_currency_value": "Nilai dalam IDR",
            "expected_quantity": "Kuantitas dokumen utama",
            "actual_quantity": "Kuantitas terkait",
            "rounding": "Presisi satuan",
        }
        heading = {
            "Masalah Aktif": "Tindakan yang disarankan",
            "Perlu Ditinjau": "Yang perlu dikonfirmasi",
            "Data Belum Lengkap": "Data yang perlu dilengkapi",
        }[row["category"]]
        primary = self._public_document(
            {
                "model": row["primary_document_model"],
                "id": row["primary_document_id"],
                "type": row.get("primary_document_type"),
                "number": row["primary_document_number"],
                "status": row["primary_document_state"],
                "problematic": True,
            }
        )
        return {
            "finding_id": row["finding_key"],
            "category": row["category"],
            "title": row["business_title"],
            "primary_document": primary,
            "affected_summary": self._affected_summary(impacted),
            "impacted_documents": impacted,
            "impacted_lines": [
                {
                    "values": [
                        {"label": line_labels[key], "value": json_safe(value)}
                        for key, value in item.items()
                        if key in line_labels and value is not None
                    ]
                }
                for item in (row.get("impacted_lines") or [])
                if any(key in line_labels and value is not None for key, value in item.items())
            ],
            "facts": evidence.get("facts") or [],
            "recommendation_heading": heading,
            "recommendation": evidence.get("recommended_action"),
            "process_owner": row["process_owner"],
            "responsible_user": row.get("responsible_user"),
            "first_seen_at": row["first_seen_at"],
            "last_detected_at": row["last_detected_at"],
            "currently_detected": row["currently_detected"],
            "lifecycle_state": row["lifecycle_state"],
            "closed_reason": row.get("closed_reason"),
            "closed_note": row.get("closed_note"),
            "closed_by": row.get("closed_by"),
            "closed_at": row.get("closed_at"),
            "auto_resolved_at": row.get("auto_resolved_at"),
            "reopened_reason": row.get("reopened_reason"),
            "reopened_by": row.get("reopened_by"),
            "reopened_at": row.get("reopened_at"),
        }

    def findings(
        self,
        *,
        category: Optional[str] = None,
        process_node: Optional[str] = None,
        document: Optional[str] = None,
        archive: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        if category and category not in CATEGORIES:
            raise ValueError("Kategori temuan tidak valid.")
        conditions = ["finding.lifecycle_state <> 'ACTIVE'" if archive else "finding.lifecycle_state = 'ACTIVE'"]
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if category:
            conditions.append("finding.category = :category")
            params["category"] = category
        if process_node:
            conditions.append("finding.process_node = :process_node")
            params["process_node"] = process_node
        if document:
            conditions.append("LOWER(COALESCE(finding.primary_document_number, '')) LIKE :document")
            params["document"] = f"%{document.strip().lower()}%"
        where = " AND ".join(conditions)
        rows = self._rows(
            f"""
                SELECT finding.*, search.document_type AS primary_document_type
                FROM ct_finding finding
                LEFT JOIN ct_published_run published ON published.company_id = 3
                LEFT JOIN ct_document_search search
                  ON search.extraction_run_id = published.extraction_run_id
                 AND search.model = finding.primary_document_model
                 AND search.record_id = finding.primary_document_id
                WHERE {where}
                ORDER BY
                    CASE finding.category
                        WHEN 'Masalah Aktif' THEN 1
                        WHEN 'Perlu Ditinjau' THEN 2
                        ELSE 3
                    END,
                    finding.last_detected_at DESC, finding.primary_document_number
                LIMIT :limit OFFSET :offset
            """,
            params,
        )
        total = self._row(f"SELECT COUNT(*) AS total FROM ct_finding finding WHERE {where}", params) or {
            "total": 0
        }
        summary_rows = self._rows("""
            SELECT category, COUNT(*) AS count
            FROM ct_finding
            WHERE lifecycle_state = 'ACTIVE'
            GROUP BY category
        """)
        summary = {"active": 0, "review": 0, "incomplete": 0}
        category_key = {
            "Masalah Aktif": "active",
            "Perlu Ditinjau": "review",
            "Data Belum Lengkap": "incomplete",
        }
        for item in summary_rows:
            summary[category_key[item["category"]]] = int(item["count"])
        return {
            "summary": summary,
            "rows": [self._finding_contract(row) for row in rows],
            "total": int(total["total"]),
            "limit": limit,
            "offset": offset,
            "archive": archive,
            "close_reasons": list(CLOSE_REASONS),
            "reasons_requiring_note": list(CLOSE_REASONS_REQUIRING_NOTE),
        }

    def finding_detail(self, finding_key: str) -> Optional[dict[str, Any]]:
        row = self._row("""
            SELECT finding.*, search.document_type AS primary_document_type
            FROM ct_finding finding
            LEFT JOIN ct_published_run published ON published.company_id = 3
            LEFT JOIN ct_document_search search
              ON search.extraction_run_id = published.extraction_run_id
             AND search.model = finding.primary_document_model
             AND search.record_id = finding.primary_document_id
            WHERE finding.finding_key = :key
        """, {"key": finding_key})
        if row is None:
            return None
        history = self._rows("""
            SELECT event_type, actor, reason, note, event_at
            FROM ct_finding_event
            WHERE finding_key = :key
            ORDER BY event_at, event_id
        """, {"key": finding_key})
        return {**self._finding_contract(row), "history": history}

    def close_findings(
        self,
        finding_keys: list[str],
        *,
        reason: str,
        note: Optional[str],
        actor: str,
    ) -> dict[str, Any]:
        if not finding_keys:
            raise ValueError("Pilih minimal satu temuan.")
        normalized_reason, normalized_note = validate_close(reason, note)
        batch_id = new_batch_id()
        with self.pg.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    UPDATE ct_finding
                    SET lifecycle_state = 'MANUALLY_CLOSED', closed_reason = :reason,
                        closed_note = :note, closed_by = :actor, closed_at = NOW(),
                        updated_at = NOW()
                    WHERE finding_key IN :keys AND lifecycle_state = 'ACTIVE'
                    RETURNING finding_key, current_evidence
                """).bindparams(bindparam("keys", expanding=True)),
                {"keys": list(dict.fromkeys(finding_keys)), "reason": normalized_reason,
                 "note": normalized_note, "actor": actor},
            ).mappings().all()
            if rows:
                conn.execute(
                    text("""
                        INSERT INTO ct_finding_event (
                            finding_key, batch_id, event_type, actor, reason, note,
                            evidence_snapshot
                        ) VALUES (
                            :finding_key, CAST(:batch_id AS UUID), 'MANUALLY_CLOSED',
                            :actor, :reason, :note, CAST(:evidence AS JSONB)
                        )
                    """),
                    [
                        {
                            "finding_key": row["finding_key"], "batch_id": batch_id,
                            "actor": actor, "reason": normalized_reason, "note": normalized_note,
                            "evidence": json.dumps(row["current_evidence"] or {}),
                        }
                        for row in rows
                    ],
                )
        return {"affected": len(rows), "batch_id": batch_id, "reason": normalized_reason}

    def reopen_findings(
        self,
        finding_keys: list[str],
        *,
        reason: str,
        actor: str,
    ) -> dict[str, Any]:
        normalized_reason = reason.strip()
        if not finding_keys:
            raise ValueError("Pilih minimal satu temuan.")
        if not normalized_reason:
            raise ValueError("Alasan buka kembali wajib diisi.")
        batch_id = new_batch_id()
        with self.pg.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    UPDATE ct_finding
                    SET lifecycle_state = 'ACTIVE', reopened_reason = :reason,
                        reopened_by = :actor, reopened_at = NOW(), updated_at = NOW()
                    WHERE finding_key IN :keys AND lifecycle_state <> 'ACTIVE'
                    RETURNING finding_key, current_evidence
                """).bindparams(bindparam("keys", expanding=True)),
                {"keys": list(dict.fromkeys(finding_keys)), "reason": normalized_reason,
                 "actor": actor},
            ).mappings().all()
            if rows:
                conn.execute(
                    text("""
                        INSERT INTO ct_finding_event (
                            finding_key, batch_id, event_type, actor, reason,
                            evidence_snapshot
                        ) VALUES (
                            :finding_key, CAST(:batch_id AS UUID), 'REOPENED',
                            :actor, :reason, CAST(:evidence AS JSONB)
                        )
                    """),
                    [
                        {
                            "finding_key": row["finding_key"], "batch_id": batch_id,
                            "actor": actor, "reason": normalized_reason,
                            "evidence": json.dumps(row["current_evidence"] or {}),
                        }
                        for row in rows
                    ],
                )
        return {"affected": len(rows), "batch_id": batch_id, "reason": normalized_reason}

    def search_documents(self, query: str, *, limit: int = 100) -> dict[str, Any]:
        normalized = query.strip().lower()
        if not normalized:
            return {"query": query, "groups": [], "total": 0}
        rows = self._rows("""
            SELECT document_type, model, record_id, document_number, native_state,
                   business_date, secondary_text, active_finding_count
            FROM ct_document_search search
            JOIN ct_published_run published
              ON published.company_id = search.company_id
             AND published.extraction_run_id = search.extraction_run_id
            WHERE search.search_text LIKE :query
            ORDER BY
                (LOWER(COALESCE(document_number, '')) = :exact) DESC,
                (LOWER(COALESCE(document_number, '')) LIKE :prefix) DESC,
                active_finding_count DESC,
                business_date DESC NULLS LAST,
                document_number
            LIMIT :limit
        """, {"query": f"%{normalized}%", "exact": normalized,
                "prefix": f"{normalized}%", "limit": limit})
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(row["document_type"], []).append(
                {
                    "number": display_document_number(row["document_number"]),
                    "status": row["native_state"],
                    "secondary": row["secondary_text"],
                    "business_date": row["business_date"],
                    "active_findings": int(row["active_finding_count"]),
                    "open_url": self._native_url(row["model"], int(row["record_id"])),
                    "detail_url": self._detail_url(row["model"], int(row["record_id"])),
                }
            )
        return {
            "query": query,
            "groups": [{"type": key, "documents": value} for key, value in groups.items()],
            "total": len(rows),
        }

    def process_map(self) -> dict[str, Any]:
        counts = self._rows("""
            SELECT CASE process_node
                       WHEN 'Gross Profit' THEN 'Sales Order'
                       ELSE process_node
                   END AS process_node,
                   category, COUNT(*) AS count
            FROM ct_finding
            WHERE lifecycle_state = 'ACTIVE'
            GROUP BY 1, category
        """)
        by_node: dict[str, dict[str, int]] = {}
        for row in counts:
            by_node.setdefault(row["process_node"], {})[row["category"]] = int(row["count"])
        return {"counts": by_node, "source": "ct_finding", "categories": list(CATEGORIES)}

    def document_detail(
        self,
        model: str,
        record_id: int,
        *,
        include_all_lines: bool = False,
        include_tracking: bool = False,
    ) -> Optional[dict[str, Any]]:
        root = self._row("""
            SELECT snapshot.document_number, snapshot.state, snapshot.payload,
                   snapshot.write_date, published.published_at, search.document_type
            FROM ct_published_run published
            JOIN ct_native_record_snapshot snapshot
              ON snapshot.extraction_run_id = published.extraction_run_id
            LEFT JOIN ct_document_search search
              ON search.extraction_run_id = published.extraction_run_id
             AND search.model = snapshot.model AND search.record_id = snapshot.record_id
            WHERE published.company_id = 3
              AND snapshot.model = :model AND snapshot.record_id = :record_id
        """, {"model": model, "record_id": record_id})
        if root is None:
            return None
        payload = root.pop("payload") or {}
        fields = {
            "sale.order": (
                ("partner_id", "Pelanggan"), ("project_id", "Proyek"),
                ("date_order", "Tanggal Order"), ("commitment_date", "Tanggal Pengiriman"),
                ("currency_id", "Mata Uang"), ("amount_untaxed", "Nilai Sebelum Pajak"),
                ("client_order_ref", "Referensi Pelanggan"),
            ),
            "purchase.order": (
                ("partner_id", "Vendor"), ("date_order", "Tanggal Order"),
                ("date_approve", "Tanggal Konfirmasi"), ("currency_id", "Mata Uang"),
                ("amount_untaxed", "Nilai Sebelum Pajak"),
            ),
            "approval.request": (
                ("category_id", "Kategori"), ("request_owner_id", "Pemohon"),
                ("date_confirmed", "Tanggal Konfirmasi"), ("x_studio_date_of_need", "Tanggal Kebutuhan"),
                ("x_studio_project", "Proyek"), ("x_currency_id", "Mata Uang"),
                ("x_studio_total_rkb_amount", "Nilai RKB"),
            ),
            "mrp.production": (
                ("product_id", "Finished Goods"), ("product_qty", "Kuantitas Direncanakan"),
                ("qty_produced", "Kuantitas Diproduksi"), ("product_uom_id", "Satuan"),
                ("origin", "Sumber"), ("date_start", "Mulai"), ("date_finished", "Selesai"),
            ),
            "stock.picking": (
                ("partner_id", "Partner"), ("picking_type_id", "Tipe Operasi"),
                ("location_id", "Lokasi Sumber"), ("location_dest_id", "Lokasi Tujuan"),
                ("scheduled_date", "Tanggal Terjadwal"), ("date_done", "Tanggal Transfer"),
                ("origin", "Dokumen Sumber"),
            ),
            "account.move": (
                ("move_type", "Tipe"), ("partner_id", "Partner"),
                ("invoice_date", "Tanggal Invoice"), ("date", "Tanggal Akuntansi"),
                ("currency_id", "Mata Uang"), ("amount_untaxed", "Nilai Sebelum Pajak"),
                ("payment_state", "Status Pembayaran"), ("journal_id", "Jurnal"),
            ),
            "account.payment": (
                ("partner_id", "Partner"), ("date", "Tanggal Pembayaran"),
                ("amount", "Nilai"), ("currency_id", "Mata Uang"),
                ("payment_type", "Tipe Pembayaran"), ("journal_id", "Jurnal"),
            ),
        }.get(model, ())
        summary_fields = [
            {"label": label, "value": display_value(payload.get(key))}
            for key, label in fields
            if display_value(payload.get(key)) is not None
        ]
        primary_count = min(5, len(summary_fields))
        line_map = {
            "sale.order": ("sale.order.line", "order_id"),
            "purchase.order": ("purchase.order.line", "order_id"),
            "approval.request": ("approval.product.line", "approval_request_id"),
            "stock.picking": ("stock.move", "picking_id"),
            "account.move": ("account.move.line", "move_id"),
        }
        raw_lines: list[dict[str, Any]] = []
        problematic_ids = {
            int(item["primary_line_id"])
            for item in self._rows("""
                SELECT primary_line_id
                FROM ct_finding
                WHERE lifecycle_state = 'ACTIVE'
                  AND primary_document_model = :model
                  AND primary_document_id = :record_id
                  AND primary_line_id IS NOT NULL
            """, {"model": model, "record_id": record_id})
        }
        if model in line_map:
            line_model, relation_field = line_map[model]
            raw_lines = self._rows(f"""
                SELECT snapshot.record_id, snapshot.payload
                FROM ct_published_run published
                JOIN ct_native_record_snapshot snapshot
                  ON snapshot.extraction_run_id = published.extraction_run_id
                WHERE published.company_id = 3
                  AND snapshot.model = :line_model
                  AND NULLIF(snapshot.payload #>> '{{{relation_field},id}}', '')::bigint = :record_id
                ORDER BY snapshot.record_id
            """, {"line_model": line_model, "record_id": record_id})
        line_fields = {
            "sale.order.line": (
                ("product_id", "Produk"), ("name", "Deskripsi"),
                ("product_uom_qty", "Dipesan"), ("qty_delivered", "Dikirim"),
                ("qty_invoiced", "Ditagihkan"), ("product_uom", "Satuan"),
                ("price_subtotal", "Subtotal Sebelum Pajak"),
            ),
            "purchase.order.line": (
                ("product_id", "Produk"), ("name", "Deskripsi"),
                ("product_qty", "Dipesan"), ("qty_received", "Diterima"),
                ("qty_invoiced", "Ditagihkan"), ("product_uom", "Satuan"),
                ("price_subtotal", "Subtotal Sebelum Pajak"),
            ),
            "approval.product.line": (
                ("product_id", "Produk"), ("description", "Deskripsi"),
                ("quantity", "Kebutuhan"), ("product_uom_id", "Satuan"),
                ("x_studio_subtotal", "Nilai RKB"), ("x_studio_status", "Status"),
            ),
            "stock.move": (
                ("product_id", "Produk"), ("product_uom_qty", "Direncanakan"),
                ("quantity", "Selesai"), ("product_uom", "Satuan"),
            ),
            "account.move.line": (
                ("product_id", "Produk"), ("quantity", "Kuantitas"),
                ("product_uom_id", "Satuan"), ("price_subtotal", "Subtotal Sebelum Pajak"),
                ("account_id", "Akun"),
            ),
        }
        has_problem_lines = bool(problematic_ids)
        visible_lines = raw_lines if include_all_lines or not has_problem_lines else [
            item for item in raw_lines if int(item["record_id"]) in problematic_ids
        ]
        lines = []
        for item in visible_lines:
            line_payload = item["payload"] or {}
            lines.append(
                {
                    "problematic": int(item["record_id"]) in problematic_ids,
                    "values": [
                        {"label": label, "value": display_value(line_payload.get(key))}
                        for key, label in line_fields.get(line_map.get(model, ("", ""))[0], ())
                        if display_value(line_payload.get(key)) is not None
                    ],
                }
            )
        related = self._related_business_documents(model, record_id)
        finding_rows = self._rows("""
            SELECT finding.*, search.document_type AS primary_document_type
            FROM ct_finding finding
            LEFT JOIN ct_published_run published ON published.company_id = 3
            LEFT JOIN ct_document_search search
              ON search.extraction_run_id = published.extraction_run_id
             AND search.model = finding.primary_document_model
             AND search.record_id = finding.primary_document_id
            WHERE finding.lifecycle_state = 'ACTIVE'
              AND finding.primary_document_model = :model
              AND finding.primary_document_id = :record_id
            ORDER BY finding.category, finding.last_detected_at DESC
        """, {"model": model, "record_id": record_id})
        tabs = ["Ringkasan", "Line Item", "Dokumen Terkait", "Temuan Aktif", "Tracking"]
        gross_profit = None
        if model == "sale.order":
            tabs.append("Gross Profit")
            gross_profit = self.gross_profit(record_id)
        return {
            "document": {
                "type": root.get("document_type") or self._document_type(model, payload),
                "number": display_document_number(root["document_number"]),
                "status": root["state"],
                "open_url": self._native_url(model, record_id),
            },
            "tabs": tabs,
            "summary": {
                "primary": summary_fields[:primary_count],
                "additional": summary_fields[primary_count:],
            },
            "line_items": lines,
            "line_item_count": len(raw_lines),
            "problematic_line_count": len(problematic_ids),
            "showing_problematic_only": has_problem_lines and not include_all_lines,
            "related_groups": related,
            "findings": [self._finding_contract(row) for row in finding_rows],
            "tracking": self.tracking(model, record_id) if include_tracking else None,
            "gross_profit": gross_profit,
            "odoo_sync_at": root["published_at"],
        }

    def _related_business_documents(self, model: str, record_id: int) -> list[dict[str, Any]]:
        rows = self._rows("""
            WITH published AS (
                SELECT extraction_run_id FROM ct_published_run WHERE company_id = 3
            ), related_key AS (
                SELECT child_model AS model, child_id AS record_id, link_type
                FROM ct_document_link, published
                WHERE ct_document_link.extraction_run_id = published.extraction_run_id
                  AND confidence = 'HIGH' AND parent_model = :model AND parent_id = :record_id
                UNION
                SELECT parent_model, parent_id, link_type
                FROM ct_document_link, published
                WHERE ct_document_link.extraction_run_id = published.extraction_run_id
                  AND confidence = 'HIGH' AND child_model = :model AND child_id = :record_id
                UNION
                SELECT target_document_model, target_document_id, relationship_type
                FROM ct_line_lineage, published
                WHERE ct_line_lineage.extraction_run_id = published.extraction_run_id
                  AND source_document_model = :model AND source_document_id = :record_id
                UNION
                SELECT source_document_model, source_document_id, relationship_type
                FROM ct_line_lineage, published
                WHERE ct_line_lineage.extraction_run_id = published.extraction_run_id
                  AND target_document_model = :model AND target_document_id = :record_id
            )
            SELECT DISTINCT snapshot.model, snapshot.record_id, snapshot.document_number,
                   snapshot.state, snapshot.payload, search.document_type
            FROM related_key
            JOIN published ON TRUE
            JOIN ct_native_record_snapshot snapshot
              ON snapshot.extraction_run_id = published.extraction_run_id
             AND snapshot.model = related_key.model
              AND snapshot.record_id = related_key.record_id
            LEFT JOIN ct_document_search search
              ON search.extraction_run_id = published.extraction_run_id
             AND search.model = snapshot.model AND search.record_id = snapshot.record_id
            WHERE snapshot.model IN (
                'sale.order', 'approval.request', 'mrp.production', 'purchase.order',
                'stock.picking', 'account.move', 'account.payment'
            )
            ORDER BY snapshot.model, snapshot.document_number
        """, {"model": model, "record_id": record_id})
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            label = row.get("document_type") or self._document_type(row["model"], row.get("payload") or {})
            groups.setdefault(label, []).append(
                {
                    "number": display_document_number(row["document_number"]),
                    "status": row["state"],
                    "open_url": self._native_url(row["model"], int(row["record_id"])),
                    "detail_url": self._detail_url(row["model"], int(row["record_id"])),
                }
            )
        order = ["Sales", "SO", "IO", "Manufacturing", "MO", "RKB", "ROP", "Purchase", "PO", "Receipt/LPB", "Delivery", "Invoice", "Vendor Bill", "Payment"]
        return [
            {"module": label, "documents": groups[label]}
            for label in order
            if label in groups
        ] + [
            {"module": label, "documents": docs}
            for label, docs in groups.items()
            if label not in order
        ]

    def gross_profit(self, sale_order_id: int) -> Optional[dict[str, Any]]:
        summary = self._row("""
            SELECT gp.*
            FROM ct_published_run published
            JOIN ct_gp_summary gp ON gp.extraction_run_id = published.extraction_run_id
            WHERE published.company_id = 3 AND gp.sale_order_id = :sale_order_id
        """, {"sale_order_id": sale_order_id})
        if summary is None:
            return None
        lines = self._rows("""
            SELECT gp.quantity, gp.revenue_idr, gp.cogs_idr, gp.gross_profit_idr,
                   gp.allocation_status, sale_line.payload #>> '{product_id,name}' AS product,
                   invoice.document_number AS invoice_number,
                   invoice.state AS invoice_state
            FROM ct_published_run published
            JOIN ct_gp_line gp ON gp.extraction_run_id = published.extraction_run_id
            JOIN ct_native_record_snapshot sale_line
              ON sale_line.extraction_run_id = published.extraction_run_id
             AND sale_line.model = 'sale.order.line'
             AND sale_line.record_id = gp.sale_order_line_id
            JOIN ct_native_record_snapshot invoice_line
              ON invoice_line.extraction_run_id = published.extraction_run_id
             AND invoice_line.model = 'account.move.line'
             AND invoice_line.record_id = gp.invoice_line_id
            JOIN ct_native_record_snapshot invoice
              ON invoice.extraction_run_id = published.extraction_run_id
             AND invoice.model = 'account.move'
             AND invoice.record_id = NULLIF(invoice_line.payload #>> '{move_id,id}', '')::bigint
            WHERE published.company_id = 3 AND gp.sale_order_id = :sale_order_id
            ORDER BY product, invoice.document_number
        """, {"sale_order_id": sale_order_id})
        cards = {
            "planned_gp": summary["planned_gp_idr"],
            "planned_margin": summary["planned_margin"],
            "realized_gp": summary["realized_gp_idr"],
            "realized_margin": summary["realized_margin"],
        }
        return {
            "currency": "IDR",
            "cards": cards,
            "planned": {
                "revenue": summary["planned_revenue_idr"],
                "rkb": summary["planned_rkb_idr"],
                "gross_profit": summary["planned_gp_idr"],
                "margin": summary["planned_margin"],
                "status": summary["planned_status"],
            },
            "realized": {
                "revenue": summary["realized_revenue_idr"],
                "cogs": summary["realized_cogs_idr"],
                "gross_profit": summary["realized_gp_idr"],
                "margin": summary["realized_margin"],
                "status": summary["realized_status"],
            },
            "lines": [json_safe(row) for row in lines],
            "limitations": summary["limitations"] or [],
            "cogs_account": {"code": "51000010", "name": "Cost of Goods Sold (Material)"},
        }

    def tracking(self, model: str, record_id: int) -> dict[str, Any]:
        rows = self._rows("""
            WITH RECURSIVE published AS (
                SELECT extraction_run_id FROM ct_published_run WHERE company_id = 3
            ), edge AS (
                SELECT parent_model, parent_id, child_model, child_id, link_type
                FROM ct_document_link, published
                WHERE ct_document_link.extraction_run_id = published.extraction_run_id
                  AND confidence = 'HIGH'
                UNION
                SELECT source_document_model, source_document_id,
                       target_document_model, target_document_id, relationship_type
                FROM ct_line_lineage, published
                WHERE ct_line_lineage.extraction_run_id = published.extraction_run_id
                  AND source_document_model IS NOT NULL AND source_document_id IS NOT NULL
                  AND target_document_model IS NOT NULL AND target_document_id IS NOT NULL
            ), walk(model, record_id, depth, path) AS (
                SELECT CAST(:model AS TEXT), CAST(:record_id AS BIGINT), 0,
                       ARRAY[:model || ':' || CAST(:record_id AS TEXT)]::text[]
                UNION ALL
                SELECT neighbor.model, neighbor.record_id, walk.depth + 1,
                       walk.path || (neighbor.model || ':' || neighbor.record_id::text)
                FROM walk
                JOIN LATERAL (
                    SELECT edge.child_model AS model, edge.child_id AS record_id
                    FROM edge
                    WHERE edge.parent_model = walk.model AND edge.parent_id = walk.record_id
                    UNION
                    SELECT edge.parent_model, edge.parent_id
                    FROM edge
                    WHERE edge.child_model = walk.model AND edge.child_id = walk.record_id
                ) neighbor ON TRUE
                WHERE walk.depth < 6
                  AND NOT (neighbor.model || ':' || neighbor.record_id::text) = ANY(walk.path)
            ), business_node AS (
                SELECT DISTINCT ON (walk.model, walk.record_id)
                       walk.model, walk.record_id, walk.depth
                FROM walk
                WHERE walk.model IN (
                    'sale.order', 'approval.request', 'mrp.production', 'purchase.order',
                    'stock.picking', 'account.move', 'account.payment'
                )
                ORDER BY walk.model, walk.record_id, walk.depth
            )
            SELECT node.model, node.record_id, node.depth, snapshot.document_number,
                   snapshot.state, snapshot.payload, search.document_type,
                   search.business_date, search.secondary_text
            FROM business_node node
            JOIN published ON TRUE
            JOIN ct_native_record_snapshot snapshot
              ON snapshot.extraction_run_id = published.extraction_run_id
             AND snapshot.model = node.model AND snapshot.record_id = node.record_id
            LEFT JOIN ct_document_search search
              ON search.extraction_run_id = published.extraction_run_id
             AND search.model = node.model AND search.record_id = node.record_id
            ORDER BY search.business_date NULLS LAST, node.depth, snapshot.document_number
        """, {"model": model, "record_id": record_id})
        if not rows:
            return {"context": None, "timeline": [], "diagram": {"nodes": [], "edges": []}}
        nodes = [
            {
                "key": f"node-{index}",
                "type": row["document_type"] or self._document_type(row["model"], row.get("payload")),
                "number": display_document_number(row["document_number"]),
                "status": row["state"],
                "business_date": row["business_date"],
                "summary": row["secondary_text"],
                "depth": int(row["depth"]),
                "open_url": self._native_url(row["model"], int(row["record_id"])),
                "detail_url": self._detail_url(row["model"], int(row["record_id"]), "tracking"),
                "_model": row["model"],
                "_id": int(row["record_id"]),
            }
            for index, row in enumerate(rows)
        ]
        node_key = {(item["_model"], item["_id"]): item["key"] for item in nodes}
        raw_edges = self._rows("""
            WITH published AS (
                SELECT extraction_run_id FROM ct_published_run WHERE company_id = 3
            ), selected AS (
                SELECT model, record_id
                FROM jsonb_to_recordset(CAST(:nodes AS JSONB))
                     AS item(model TEXT, record_id BIGINT)
            ), edge AS (
                SELECT parent_model, parent_id, child_model, child_id, link_type
                FROM ct_document_link, published
                WHERE ct_document_link.extraction_run_id = published.extraction_run_id
                  AND confidence = 'HIGH'
                UNION
                SELECT source_document_model, source_document_id,
                       target_document_model, target_document_id, relationship_type
                FROM ct_line_lineage, published
                WHERE ct_line_lineage.extraction_run_id = published.extraction_run_id
            )
            SELECT edge.*
            FROM edge
            JOIN selected source
              ON source.model = edge.parent_model AND source.record_id = edge.parent_id
            JOIN selected target
              ON target.model = edge.child_model AND target.record_id = edge.child_id
        """, {"nodes": json.dumps([
            {"model": model_name, "record_id": record_key}
            for model_name, record_key in node_key
        ])})
        edges = []
        seen: set[tuple[str, str]] = set()
        for edge in raw_edges:
            source = node_key.get((edge["parent_model"], int(edge["parent_id"]))) if edge["parent_id"] is not None else None
            target = node_key.get((edge["child_model"], int(edge["child_id"]))) if edge["child_id"] is not None else None
            if source and target and source != target and (source, target) not in seen:
                seen.add((source, target))
                edges.append({"source": source, "target": target, "relationship": edge["link_type"]})
        context = next((item for item in nodes if item["type"] == "SO"), nodes[0])
        for item in nodes:
            item.pop("_model", None)
            item.pop("_id", None)
        return {
            "context": {key: context[key] for key in ("type", "number", "status", "detail_url")},
            "timeline": nodes,
            "diagram": {"nodes": nodes, "edges": edges},
            "modes": ["Timeline", "Diagram"],
        }

    def rkb_tracking(self, request_id: int) -> Optional[dict[str, Any]]:
        root = self._row("""
            SELECT snapshot.document_number, snapshot.state, snapshot.payload
            FROM ct_published_run published
            JOIN ct_native_record_snapshot snapshot
              ON snapshot.extraction_run_id = published.extraction_run_id
            WHERE published.company_id = 3 AND snapshot.model = 'approval.request'
              AND snapshot.record_id = :request_id
              AND UPPER(COALESCE(snapshot.payload #>> '{category_id,name}', '')) = 'RKB'
        """, {"request_id": request_id})
        if root is None:
            return None
        rows = self._rows("""
            WITH published AS (
                SELECT extraction_run_id FROM ct_published_run WHERE company_id = 3
            ), line AS (
                SELECT item.record_id, item.payload
                FROM published
                JOIN ct_native_record_snapshot item
                  ON item.extraction_run_id = published.extraction_run_id
                 AND item.model = 'approval.product.line'
                WHERE NULLIF(item.payload #>> '{approval_request_id,id}', '')::bigint = :request_id
            ), po_branch AS (
                SELECT
                    line.record_id AS line_id, pol.record_id AS po_line_id,
                    po.record_id AS po_id, po.document_number AS po_number, po.state AS po_state,
                    NULLIF(pol.payload ->> 'product_qty', '')::numeric AS po_quantity,
                    NULLIF(pol.payload ->> 'price_subtotal', '')::numeric AS po_value,
                    receipt.record_id AS receipt_id, receipt.document_number AS receipt_number,
                    receipt.state AS receipt_state,
                    NULLIF(move.payload ->> 'quantity', '')::numeric AS received_quantity
                FROM line
                JOIN published ON TRUE
                JOIN ct_native_record_snapshot pol
                  ON pol.extraction_run_id = published.extraction_run_id
                 AND pol.model = 'purchase.order.line'
                 AND pol.record_id = NULLIF(line.payload #>> '{purchase_order_line_id,id}', '')::bigint
                JOIN ct_native_record_snapshot po
                  ON po.extraction_run_id = published.extraction_run_id
                 AND po.model = 'purchase.order'
                 AND po.record_id = NULLIF(pol.payload #>> '{order_id,id}', '')::bigint
                LEFT JOIN ct_native_record_snapshot move
                  ON move.extraction_run_id = published.extraction_run_id
                 AND move.model = 'stock.move'
                 AND NULLIF(move.payload #>> '{purchase_line_id,id}', '')::bigint = pol.record_id
                 AND move.state = 'done'
                LEFT JOIN ct_native_record_snapshot receipt
                  ON receipt.extraction_run_id = published.extraction_run_id
                 AND receipt.model = 'stock.picking'
                 AND receipt.record_id = NULLIF(move.payload #>> '{picking_id,id}', '')::bigint
            )
            SELECT
                line.record_id, line.payload,
                COALESCE(jsonb_agg(jsonb_build_object(
                    'po_line_id', branch.po_line_id,
                    'po_number', branch.po_number, 'po_state', branch.po_state,
                    'po_quantity', branch.po_quantity, 'po_value', branch.po_value,
                    'receipt_number', branch.receipt_number,
                    'receipt_state', branch.receipt_state,
                    'received_quantity', branch.received_quantity,
                    'po_id', branch.po_id, 'receipt_id', branch.receipt_id
                ) ORDER BY branch.po_number, branch.receipt_number)
                FILTER (WHERE branch.po_id IS NOT NULL), '[]'::jsonb) AS branches
            FROM line
            LEFT JOIN po_branch branch ON branch.line_id = line.record_id
            GROUP BY line.record_id, line.payload
            ORDER BY line.record_id
        """, {"request_id": request_id})
        items = []
        total_rkb = Decimal("0")
        total_po = Decimal("0")
        for row in rows:
            payload = row["payload"] or {}
            required = Decimal(str(payload.get("quantity") or 0))
            rkb_value = Decimal(str(payload.get("x_studio_subtotal") or 0))
            total_rkb += rkb_value
            branches = []
            po_quantity = Decimal("0")
            received = Decimal("0")
            po_value = Decimal("0")
            counted_po_lines: set[int] = set()
            for branch in row["branches"] or []:
                branch_po_quantity = Decimal(str(branch.get("po_quantity") or 0))
                branch_received = Decimal(str(branch.get("received_quantity") or 0))
                branch_po_value = Decimal(str(branch.get("po_value") or 0))
                po_line_id = int(branch["po_line_id"])
                if po_line_id not in counted_po_lines:
                    counted_po_lines.add(po_line_id)
                    po_quantity += branch_po_quantity
                    po_value += branch_po_value
                received += branch_received
                branch_result = {
                    "po_number": branch.get("po_number"),
                    "po_status": branch.get("po_state"),
                    "po_quantity": branch_po_quantity,
                    "receipt_number": branch.get("receipt_number"),
                    "receipt_status": branch.get("receipt_state"),
                    "received_quantity": branch_received,
                    "progress_text": f"{branch_received:g} dari {branch_po_quantity:g} sudah diterima",
                }
                if branch.get("po_id"):
                    branch_result["po_open_url"] = self._native_url("purchase.order", int(branch["po_id"]))
                if branch.get("receipt_id"):
                    branch_result["receipt_open_url"] = self._native_url("stock.picking", int(branch["receipt_id"]))
                branches.append(branch_result)
            total_po += po_value
            for_need = min(po_quantity, required)
            extra_stock = max(po_quantity - required, Decimal("0"))
            items.append(
                {
                    "product": display_value(payload.get("product_id")) or payload.get("description"),
                    "uom": display_value(payload.get("product_uom_id")),
                    "summary": {
                        "required": required,
                        "opening_stock": None,
                        "opening_stock_availability": "Tidak dapat direkonstruksi dari data historis yang disinkronkan",
                        "processed_to_rop": None,
                        "rop_relation_availability": "Relasi RKB Line ke ROP Line tidak tersedia",
                        "ordered_for_rkb": for_need,
                        "additional_for_stock": extra_stock,
                        "total_po": po_quantity,
                        "received": received,
                        "current_shortage": max(required - received, Decimal("0")),
                    },
                    "material_status": "Sudah Diterima" if received >= required and required > 0 else "Belum Dialokasikan",
                    "allocation_availability": "Reservasi historis tidak tersedia pada kontrak sumber",
                    "branches": branches,
                    "financial": {"rkb_value": rkb_value, "po_value": po_value},
                }
            )
        difference = total_po - total_rkb
        return {
            "rkb": {
                "number": display_document_number(root["document_number"]),
                "status": root["state"],
                "work_reference": display_value(root["payload"].get("x_studio_nomor_jo"))
                or display_value(root["payload"].get("x_studio_nomor_io")),
                "open_url": self._native_url("approval.request", request_id),
            },
            "items": items,
            "financial": {
                "rkb_value": total_rkb,
                "po_value": total_po,
                "difference": difference,
                "difference_percentage": (difference / total_rkb) if total_rkb else None,
                "classification": None,
            },
            "limitations": [
                "Relasi native RKB Line ke ROP Line tidak tersedia pada Odoo.",
                "Stock Awal historis tidak diganti dengan stock saat ini.",
            ],
        }

    def exception_rules(self) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT exception_id::text AS exception_id, rule_code, selector, reason,
                   approver, created_by, valid_from, valid_until, active,
                   created_at, updated_at
            FROM ct_exception_rule
            ORDER BY active DESC, created_at DESC
        """)

    def product_cost_classifications(
        self,
        *,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        condition = ""
        params: dict[str, Any] = {"limit": limit}
        if search and search.strip():
            condition = """
                AND LOWER(CONCAT_WS(' ', product.payload ->> 'display_name',
                                         product.payload ->> 'default_code')) LIKE :search
            """
            params["search"] = f"%{search.strip().lower()}%"
        return self._rows(f"""
            SELECT classification.product_id,
                   COALESCE(product.payload ->> 'display_name', product.payload ->> 'name') AS product,
                   product.payload ->> 'default_code' AS product_code,
                   classification.classification, classification.source,
                   classification.updated_by, classification.updated_at
            FROM ct_product_cost_classification classification
            JOIN ct_published_run published ON published.company_id = classification.company_id
            LEFT JOIN ct_native_record_snapshot product
              ON product.extraction_run_id = published.extraction_run_id
             AND product.model = 'product.product'
             AND product.record_id = classification.product_id
            WHERE classification.company_id = 3 {condition}
            ORDER BY product, product_code
            LIMIT :limit
        """, params)

    def update_product_cost_classification(
        self,
        product_id: int,
        *,
        classification: str,
        actor: str,
    ) -> dict[str, Any]:
        allowed = {"Material", "Jasa Eksternal", "Belum Terkategori"}
        if classification not in allowed:
            raise ValueError("Klasifikasi biaya produk tidak valid.")
        with self.pg.engine.begin() as conn:
            exists = conn.execute(text("""
                SELECT 1
                FROM ct_published_run published
                JOIN ct_native_record_snapshot product
                  ON product.extraction_run_id = published.extraction_run_id
                 AND product.model = 'product.product'
                 AND product.record_id = :product_id
                WHERE published.company_id = 3
            """), {"product_id": product_id}).scalar_one_or_none()
            if not exists:
                raise ValueError("Produk tidak tersedia pada data yang dipublikasikan.")
            conn.execute(text("""
                INSERT INTO ct_product_cost_classification (
                    company_id, product_id, classification, source, updated_by, updated_at
                ) VALUES (3, :product_id, :classification, 'MANUAL', :actor, NOW())
                ON CONFLICT (company_id, product_id) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    source = 'MANUAL', updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """), {"product_id": product_id, "classification": classification, "actor": actor})
        return {"classification": classification, "source": "MANUAL"}

    def create_exception_rule(
        self,
        *,
        rule_code: str,
        selector: dict[str, Any],
        reason: str,
        approver: str,
        valid_from: date,
        valid_until: Optional[date],
        actor: str,
    ) -> dict[str, Any]:
        allowed = {
            "product_id", "product_category_id", "account_id", "journal_id",
            "operation_type_id", "vendor_id", "company_id",
        }
        if not selector or set(selector) - allowed:
            raise ValueError("Scope pengecualian harus memakai selector exact yang didukung.")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in selector.values()):
            raise ValueError("Nilai selector pengecualian harus ID exact.")
        if valid_until and valid_until < valid_from:
            raise ValueError("Tanggal akhir tidak boleh sebelum tanggal mulai.")
        if not reason.strip() or not approver.strip():
            raise ValueError("Alasan dan approver wajib diisi.")
        exception_id = str(uuid4())
        with self.pg.engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM ct_rule_config WHERE rule_code = :rule_code"),
                {"rule_code": rule_code},
            ).scalar_one_or_none()
            if not exists:
                raise ValueError("Rule tujuan tidak tersedia.")
            conn.execute(text("""
                INSERT INTO ct_exception_rule (
                    exception_id, rule_code, selector, reason, approver, created_by,
                    valid_from, valid_until, active
                ) VALUES (
                    CAST(:exception_id AS UUID), :rule_code, CAST(:selector AS JSONB),
                    :reason, :approver, :actor, :valid_from, :valid_until, TRUE
                )
            """), {"exception_id": exception_id, "rule_code": rule_code,
                    "selector": json.dumps(selector), "reason": reason.strip(),
                    "approver": approver.strip(), "actor": actor,
                    "valid_from": valid_from, "valid_until": valid_until})
            conn.execute(text("""
                INSERT INTO ct_exception_rule_event (
                    exception_id, event_type, actor, snapshot
                ) VALUES (
                    CAST(:exception_id AS UUID), 'CREATED', :actor, CAST(:snapshot AS JSONB)
                )
            """), {"exception_id": exception_id, "actor": actor,
                    "snapshot": json.dumps({"rule_code": rule_code, "selector": selector,
                                            "reason": reason.strip(), "approver": approver.strip(),
                                            "valid_from": str(valid_from),
                                            "valid_until": str(valid_until) if valid_until else None})})
        return {"exception_id": exception_id, "active": True}

    def deactivate_exception_rule(self, exception_id: str, *, actor: str) -> bool:
        with self.pg.engine.begin() as conn:
            row = conn.execute(text("""
                UPDATE ct_exception_rule
                SET active = FALSE, updated_at = NOW()
                WHERE exception_id = CAST(:exception_id AS UUID) AND active
                RETURNING rule_code, selector, reason, approver
            """), {"exception_id": exception_id}).mappings().one_or_none()
            if row is None:
                return False
            conn.execute(text("""
                INSERT INTO ct_exception_rule_event (
                    exception_id, event_type, actor, snapshot
                ) VALUES (
                    CAST(:exception_id AS UUID), 'DEACTIVATED', :actor, CAST(:snapshot AS JSONB)
                )
            """), {"exception_id": exception_id, "actor": actor,
                    "snapshot": json.dumps(dict(row), default=str)})
        return True

    def close(self) -> None:
        self.pg.close()
