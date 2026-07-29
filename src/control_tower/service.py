"""Read-only query service untuk Control Tower SOP Validation v0.1."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import text

from src.clients.postgres_client import PostgresClient


PRESENTATION_CATEGORIES = {
    "MASALAH_AKTIF",
    "PERLU_DITINJAU",
    "DATA_BELUM_LENGKAP",
}
REVIEW_STATUSES = {
    "DATA_LINKAGE_GAP",
    "PARTIAL_MATCH",
    "MANUAL_EVIDENCE_REQUIRED",
    "DATA_EXCEPTION",
}
PROCESS_RULE_MAP = {
    ("SO-PO-001", "sale.order"): "sales-order",
    ("DH2-SALES-001", "sale.order"): "sales-order",
    ("SO-SOURCE-001", "sale.order"): "sales-order",
    ("SO-CANCEL-001", "sale.order"): "sales-order",
    ("IO-PROD-001", "approval.request"): "internal-order",
    ("IO-UTIL-001", "approval.request"): "internal-order",
    ("SO-IO-MO-001", "mrp.production"): "manufacturing-order",
    ("PO-CANCEL-001", "purchase.order"): "material-purchase-order",
    ("PO-DRAFT-001", "purchase.order"): "material-purchase-order",
}


def presentation_category_for_status(status: Optional[str]) -> Optional[str]:
    if status == "MISMATCH":
        return "MASALAH_AKTIF"
    if status in REVIEW_STATUSES:
        return "PERLU_DITINJAU"
    return None


def process_key_for(rule_id: Optional[str], document_model: Optional[str]) -> Optional[str]:
    return PROCESS_RULE_MAP.get((rule_id or "", document_model or ""))


def supported_destination(
    *,
    affected_model: Optional[str],
    document_id: Optional[int],
    document_number: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if affected_model == "sale.order" and document_id is not None:
        return f"/dashboard/sales-orders?sales_order_id={document_id}", "Sales Order Traceability"
    if affected_model == "approval.request" and document_number:
        return (
            "/dashboard/internal-order-rekap?internal_order_number="
            + quote(str(document_number), safe=""),
            "Order Material Tracking",
        )
    return None, None


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


class ControlTowerService:
    """Thin query layer. Tidak ada mutation atau write-back."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        self.pg = postgres_client or PostgresClient()

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
        return {
            "status": "READY" if run else "NO_COMPLETED_EXTRACTION",
            "latest_run": run,
            **counts,
            "read_only": True,
            "payment_kpi_published": False,
            "runtime_materialized": True,
        }

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

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._rows(f"""
            SELECT *
            FROM mv_ct_exception_worklist
            {where}
            ORDER BY severity_priority, rule_id, document_number NULLS LAST, document_id
            LIMIT :limit OFFSET :offset
        """, params)
        total = self._row(f"""
            SELECT COUNT(*) AS total
            FROM mv_ct_exception_worklist
            {where}
        """, params) or {"total": 0}
        return {"rows": rows, "total": total["total"], "limit": limit, "offset": offset}

    def findings(
        self,
        *,
        affected_model: Optional[str] = None,
        category: Optional[str] = None,
        rule_code: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return current-company OPEN Temuan findings only."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        conditions = [
            "finding.current_status = 'OPEN'",
            "finding.company_id = current_run.company_id",
        ]
        for key, value in (
            ("affected_model", affected_model),
            ("category", category),
            ("rule_code", rule_code),
        ):
            if value:
                conditions.append(f"finding.{key} = :{key}")
                params[key] = value
        where = "WHERE " + " AND ".join(conditions)
        rows = self._rows(f"""
            SELECT
                finding.finding_id,
                finding.category,
                finding.rule_code,
                finding.affected_model,
                finding.affected_document_id,
                finding.native_document_reference,
                finding.company_id,
                finding.title,
                finding.summary,
                finding.evidence_payload,
                finding.first_detected_time,
                finding.last_detected_time,
                finding.current_status,
                finding.destination_url
            FROM ct_finding finding
            CROSS JOIN vw_ct_current_run current_run
            {where}
            ORDER BY finding.rule_code, finding.affected_model,
                     finding.affected_document_id, finding.finding_id
            LIMIT :limit OFFSET :offset
        """, params)
        total = self._row(f"""
            SELECT COUNT(*) AS total
            FROM ct_finding finding
            CROSS JOIN vw_ct_current_run current_run
            {where}
        """, params) or {"total": 0}
        return {"rows": rows, "total": total["total"], "limit": limit, "offset": offset}

    def evidence(
        self,
        *,
        presentation_category: str = "MASALAH_AKTIF",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return the current snapshot evidence grouped for the three-panel UI."""
        if presentation_category not in PRESENTATION_CATEGORIES:
            raise ValueError("Unsupported Control Tower presentation category.")

        counts = self._row("""
            SELECT
                COUNT(*) FILTER (WHERE validation_status = 'MISMATCH') AS masalah_aktif,
                COUNT(*) FILTER (
                    WHERE validation_status IN (
                        'DATA_LINKAGE_GAP', 'PARTIAL_MATCH',
                        'MANUAL_EVIDENCE_REQUIRED', 'DATA_EXCEPTION'
                    )
                ) AS perlu_ditinjau,
                (
                    SELECT COUNT(*)
                    FROM ct_finding finding
                    CROSS JOIN vw_ct_current_run current_run
                    WHERE finding.current_status = 'OPEN'
                      AND finding.company_id = current_run.company_id
                ) AS data_belum_lengkap
            FROM mv_ct_exception_worklist
        """) or {}
        category_counts = {
            "MASALAH_AKTIF": int(counts.get("masalah_aktif") or 0),
            "PERLU_DITINJAU": int(counts.get("perlu_ditinjau") or 0),
            "DATA_BELUM_LENGKAP": int(counts.get("data_belum_lengkap") or 0),
        }

        if presentation_category == "DATA_BELUM_LENGKAP":
            rows = self._rows("""
                SELECT
                    finding.finding_id AS evidence_key,
                    finding.finding_id,
                    'ct_finding'::text AS source_kind,
                    finding.category,
                    'DATA_BELUM_LENGKAP'::text AS presentation_category,
                    finding.rule_code,
                    COALESCE(
                        NULLIF(finding.evidence_payload ->> 'source_check', ''),
                        finding.rule_code
                    ) AS source_rule_id,
                    finding.affected_model AS document_model,
                    finding.affected_model AS affected_model,
                    finding.affected_document_id AS document_id,
                    finding.affected_document_id,
                    finding.native_document_reference AS document_number,
                    finding.native_document_reference,
                    finding.title,
                    finding.summary,
                    finding.evidence_payload,
                    source_result.expected_condition,
                    source_result.actual_condition,
                    source_result.evidence,
                    source_result.validation_status,
                    source_result.severity,
                    source_result.confidence,
                    finding.first_detected_time,
                    finding.last_detected_time,
                    finding.current_status,
                    finding.destination_url
                FROM ct_finding finding
                CROSS JOIN vw_ct_current_run current_run
                LEFT JOIN mv_ct_rule_results source_result
                  ON source_result.rule_id = COALESCE(
                         NULLIF(finding.evidence_payload ->> 'source_check', ''),
                         finding.rule_code
                     )
                 AND source_result.document_model = finding.affected_model
                 AND source_result.document_id = finding.affected_document_id
                WHERE finding.current_status = 'OPEN'
                  AND finding.company_id = current_run.company_id
                ORDER BY finding.rule_code, finding.affected_model,
                         finding.affected_document_id, finding.finding_id
                LIMIT :limit OFFSET :offset
            """, {"limit": limit, "offset": offset})
            total = self._row("""
                SELECT COUNT(*) AS total
                FROM ct_finding finding
                CROSS JOIN vw_ct_current_run current_run
                WHERE finding.current_status = 'OPEN'
                  AND finding.company_id = current_run.company_id
            """) or {"total": 0}
            grouped = self._rows("""
                SELECT finding.rule_code, finding.affected_model AS document_model,
                       COUNT(*) AS total
                FROM ct_finding finding
                CROSS JOIN vw_ct_current_run current_run
                WHERE finding.current_status = 'OPEN'
                  AND finding.company_id = current_run.company_id
                GROUP BY finding.rule_code, finding.affected_model
            """)
        else:
            status_where = (
                "validation_status = 'MISMATCH'"
                if presentation_category == "MASALAH_AKTIF"
                else "validation_status IN ("
                "'DATA_LINKAGE_GAP', 'PARTIAL_MATCH', "
                "'MANUAL_EVIDENCE_REQUIRED', 'DATA_EXCEPTION')"
            )
            rows = self._rows(f"""
                SELECT
                    MD5(CONCAT_WS('|', issue_id, rule_id, document_model,
                                  document_id::text, actual_condition::text,
                                  evidence::text)) AS evidence_key,
                    issue_id,
                    'mv_ct_exception_worklist'::text AS source_kind,
                    NULL::text AS category,
                    '{presentation_category}'::text AS presentation_category,
                    rule_id,
                    rule_id AS source_rule_id,
                    document_model,
                    document_model AS affected_model,
                    document_id,
                    document_id AS affected_document_id,
                    document_number,
                    document_number AS native_document_reference,
                    rule_name AS title,
                    NULL::text AS summary,
                    expected_condition,
                    actual_condition,
                    evidence,
                    validation_status,
                    severity,
                    confidence,
                    owner,
                    detected_at,
                    NULL::timestamptz AS first_detected_time,
                    NULL::timestamptz AS last_detected_time,
                    NULL::text AS current_status,
                    NULL::text AS destination_url
                FROM mv_ct_exception_worklist
                WHERE {status_where}
                ORDER BY severity_priority, rule_id, document_number NULLS LAST, document_id,
                         evidence_key
                LIMIT :limit OFFSET :offset
            """, {"limit": limit, "offset": offset})
            total = self._row(f"""
                SELECT COUNT(*) AS total
                FROM mv_ct_exception_worklist
                WHERE {status_where}
            """) or {"total": 0}
            grouped = self._rows(f"""
                SELECT rule_id, document_model, validation_status, COUNT(*) AS total
                FROM mv_ct_exception_worklist
                WHERE {status_where}
                GROUP BY rule_id, document_model, validation_status
            """)

        process_totals: dict[str, dict[str, Any]] = {}
        for group in grouped:
            process_key = process_key_for(group.get("rule_id"), group.get("document_model"))
            if not process_key:
                continue
            entry = process_totals.setdefault(
                process_key,
                {"process_key": process_key, "count": 0, "rules": []},
            )
            entry["count"] += int(group.get("total") or 0)
            rule_entry = {
                "rule_id": group.get("rule_id"),
                "document_model": group.get("document_model"),
                "validation_status": group.get("validation_status")
                or ("OPEN" if presentation_category == "DATA_BELUM_LENGKAP" else None),
                "count": int(group.get("total") or 0),
            }
            if rule_entry not in entry["rules"]:
                entry["rules"].append(rule_entry)

        available_tracking_numbers: set[str] = set()
        tracking_candidates = {
            str(row.get("native_document_reference"))
            for row in rows
            if row.get("source_kind") == "mv_ct_exception_worklist"
            and row.get("affected_model") == "approval.request"
            and row.get("native_document_reference")
        }
        if tracking_candidates:
            tracking_params = {
                f"tracking_number_{index}": number
                for index, number in enumerate(sorted(tracking_candidates))
            }
            tracking_placeholders = ", ".join(f":{key}" for key in tracking_params)
            available_tracking_numbers = {
                str(item["internal_order_number"])
                for item in self._rows(
                    f"""
                        SELECT internal_order_number
                        FROM vw_internal_order_rekap_summary
                        WHERE internal_order_number IN ({tracking_placeholders})
                    """,
                    tracking_params,
                )
                if item.get("internal_order_number")
            }

        for row in rows:
            model = row.get("affected_model") or row.get("document_model")
            row["presentation_category"] = presentation_category
            row["process_key"] = process_key_for(
                row.get("source_rule_id") or row.get("rule_id"), model
            )
            if row.get("source_kind") == "mv_ct_exception_worklist":
                row["destination_url"], row["destination_label"] = supported_destination(
                    affected_model=model,
                    document_id=row.get("affected_document_id"),
                    document_number=row.get("native_document_reference"),
                )
                if (
                    model == "approval.request"
                    and str(row.get("native_document_reference")) not in available_tracking_numbers
                ):
                    row["destination_url"] = None
                    row["destination_label"] = None
                status = row.get("validation_status") or "UNKNOWN"
                row["evidence_wording"] = (
                    f"Hasil validasi {status}; bukti sumber perlu dikonfirmasi oleh pemilik proses."
                    if status == "MISMATCH"
                    else f"Hasil validasi {status} adalah sinyal review, bukan konfirmasi kesalahan."
                )
            else:
                row["destination_label"] = (
                    "Sales Order Traceability" if row.get("destination_url") else None
                )
                row["evidence_wording"] = row.get("summary") or (
                    "Finding lifecycle OPEN dari pemeriksaan SO-PO-001."
                )

        return {
            "rows": rows,
            "total": int(total.get("total") or 0),
            "limit": limit,
            "offset": offset,
            "presentation_category": presentation_category,
            "category_counts": category_counts,
            "process_counts": list(process_totals.values()),
            "rule_results": self.validation_summary(),
            "meta": {
                "source_views": [
                    "mv_ct_sop_validation_summary",
                    "mv_ct_exception_worklist",
                    "ct_finding",
                ],
                "healthy_and_not_tested_excluded": True,
                "review_signal_meaning": "Review signals are not confirmed user or SOP errors.",
            },
        }

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

        rows = self._rows(f"""
            SELECT *
            FROM vw_ct_po_cancellation_scope
            {where}
            ORDER BY date_scope, operational_exposure, purchase_order_id
            LIMIT :limit OFFSET :offset
        """, params)
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
        root = self._row("""
            SELECT model, record_id, document_number, state, company_id, company_name,
                   write_date, payload, extracted_at
            FROM vw_ct_native_record_snapshot_current
            WHERE model = :root_model AND record_id = :root_id
        """, {"root_model": root_model, "root_id": root_id})
        if root is None:
            return {"root": None, "links": [], "validations": []}

        links = self._rows("""
            SELECT
                depth, root_model, root_id, root_number,
                parent_model, parent_id, parent_number,
                child_model, child_id, child_number,
                link_type, confidence, link_path
            FROM mv_ct_document_paths
            WHERE root_model = :root_model AND root_id = :root_id
            ORDER BY depth, parent_model, parent_id, child_model, child_id
        """, {"root_model": root_model, "root_id": root_id})
        validations = self._rows("""
            SELECT *
            FROM mv_ct_rule_results
            WHERE document_model = :root_model AND document_id = :root_id
            ORDER BY rule_id
        """, {"root_model": root_model, "root_id": root_id})
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
        rows = self._rows(f"""
            SELECT *
            FROM vw_ct_io_health
            {where}
            ORDER BY
                CASE WHEN production_status = 'DATA_EXCEPTION' OR utilization_status = 'DATA_EXCEPTION' THEN 1 ELSE 2 END,
                internal_order_number,
                product_name
            LIMIT :limit OFFSET :offset
        """, params)
        total = self._row(f"SELECT COUNT(*) AS total FROM vw_ct_io_health {where}", params) or {"total": 0}
        return {"rows": rows, "total": total["total"], "limit": limit, "offset": offset}

    def close(self) -> None:
        self.pg.close()
