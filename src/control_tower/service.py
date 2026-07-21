"""Read-only query service untuk Control Tower SOP Validation v0.1."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text

from src.clients.postgres_client import PostgresClient


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

    def close(self) -> None:
        self.pg.close()
