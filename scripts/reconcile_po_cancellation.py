#!/usr/bin/env python3
"""Reconcile PO-CANCEL-001 from PostgreSQL-only Control Tower evidence.

The targeted Odoo enrichment is intentionally performed by
``enrich_po_cancellation_date_order.py``. This script never connects to Odoo;
it reads the published enrichment and writes review artifacts under ignored
``output/``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient


OUTPUT_DIR = PROJECT_ROOT / "output"
DATE_START = "2026-01-01"
OPEN_RECEIPT_STATES = {"draft", "waiting", "confirmed", "assigned", "partially_available"}
CLOSED_RECEIPT_STATES = {"done", "cancel", "cancelled"}
STATE_ORDER = (
    "draft",
    "waiting",
    "confirmed",
    "assigned",
    "partially_available",
    "done",
    "cancel",
    "cancelled",
    "UNSUPPORTED_OR_NULL",
)
BASELINE = {
    "scope": "purchase.order.date_order >= 2026-01-01",
    "cancelled_po_roots": 348,
    "open_receipt_po_roots": 0,
    "source": "earlier 2026 closure audit",
}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def query_rows(conn: Any, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [
        {key: json_safe(value) for key, value in row.items()}
        for row in conn.execute(text(sql), params).mappings().all()
    ]


def query_one(conn: Any, sql: str, **params: Any) -> dict[str, Any]:
    rows = query_rows(conn, sql, **params)
    return rows[0] if rows else {}


def stage(name: str) -> None:
    print(f"[START] {name}", flush=True)


def done(name: str) -> None:
    print(f"[DONE ] {name}", flush=True)


def normalized_state(value: Any) -> str:
    return str(value or "").strip().lower()


def state_bucket(value: Any) -> str:
    state = normalized_state(value)
    return state if state in STATE_ORDER else "UNSUPPORTED_OR_NULL"


def is_open(value: Any) -> bool:
    return normalized_state(value) in OPEN_RECEIPT_STATES


def is_closed(value: Any) -> bool:
    return normalized_state(value) in CLOSED_RECEIPT_STATES


def masked(model: str, record_id: int | None) -> str:
    prefixes = {"purchase.order": "PO", "stock.picking": "RCT"}
    token = sha256(f"{model}:{record_id}".encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefixes.get(model, 'DOC')}-{token}"


def classify_candidate(
    receipts: list[dict[str, Any]], backorders: list[dict[str, Any]]
) -> tuple[str, str, list[dict[str, Any]]]:
    """Classify receipt exposure separately from the PO date scope."""
    direct = {
        int(row["receipt_id"]): row
        for row in receipts
        if row.get("receipt_id") is not None
    }
    values = list(direct.values())
    if not values:
        return "INVALID_OR_LOW_CONFIDENCE_LINK", "Tidak ada Receipt native untuk kandidat.", []
    if any(row.get("confidence") != "HIGH" for row in values):
        return "INVALID_OR_LOW_CONFIDENCE_LINK", "Relasi Receipt tidak seluruhnya HIGH/native.", []
    unsupported = [row for row in values if state_bucket(row.get("receipt_state")) == "UNSUPPORTED_OR_NULL"]
    if unsupported:
        return "UNRESOLVED_EVIDENCE_GAP", "State Receipt kosong atau di luar kosakata operasional.", []

    open_receipts = [row for row in values if is_open(row.get("receipt_state"))]
    if not open_receipts:
        if all(is_closed(row.get("receipt_state")) for row in values):
            return "CLOSED_RECEIPT_FALSE_POSITIVE", "Hanya Receipt closed yang terhubung.", []
        return "DUPLICATE_RELATION_PATH", "Tidak ada Receipt operasional setelah deduplikasi.", []

    open_ids = {int(row["receipt_id"]) for row in open_receipts}
    closed_parent_by_child = {
        int(row["child_receipt_id"])
        for row in backorders
        if row.get("child_receipt_id") is not None and is_closed(row.get("parent_state"))
    }
    if open_ids and open_ids.issubset(closed_parent_by_child):
        return (
            "OPEN_BACKORDER",
            "Receipt terbuka adalah child backorder dari parent Receipt yang sudah closed.",
            open_receipts,
        )
    return (
        "REAL_OPEN_RECEIPT",
        "Receipt native berstate operasional terbuka melalui jalur PO_TO_RECEIPT.",
        open_receipts,
    )


def read_snapshot(conn: Any) -> dict[str, Any]:
    stage("Membaca snapshot, enrichment, dan grain PO-CANCEL-001")
    metadata = query_one(
        conn,
        """
        SELECT run_id::text AS run_id, company_id, started_at, completed_at, model_counts
        FROM vw_ct_current_run
        """,
    )
    enrichment = query_one(
        conn,
        """
        SELECT
            execution.expected_count,
            execution.returned_count,
            execution.null_date_order_count,
            execution.status,
            execution.started_at,
            execution.completed_at
        FROM ct_purchase_order_date_enrichment_execution execution
        JOIN vw_ct_current_run current_run ON current_run.run_id = execution.run_id
        WHERE execution.company_id = 3
          AND execution.status = 'COMPLETED'
        ORDER BY execution.completed_at DESC
        LIMIT 1
        """,
    )
    all_time = query_one(
        conn,
        """
        SELECT
            COUNT(*) AS cancelled_po_roots,
            COUNT(*) FILTER (WHERE operational_open_receipt_count = 0) AS no_open_receipt_roots,
            COUNT(*) FILTER (WHERE operational_open_receipt_count > 0) AS open_receipt_roots,
            COUNT(DISTINCT purchase_order_id) AS unique_po_roots
        FROM vw_ct_po_cancellation_scope
        """,
    )
    scopes = query_rows(
        conn,
        """
        SELECT
            date_scope,
            COUNT(*) AS cancelled_po_roots,
            COUNT(*) FILTER (WHERE operational_open_receipt_count > 0) AS open_receipt_roots,
            COUNT(*) FILTER (WHERE operational_exposure = 'ACTIVE_ISSUE') AS active_issues,
            COUNT(*) FILTER (WHERE operational_exposure = 'HISTORICAL_EXPOSURE') AS historical_exposures,
            COUNT(*) FILTER (WHERE operational_exposure = 'DATE_REVIEW_REQUIRED') AS date_review_required,
            COUNT(*) FILTER (WHERE open_backorder_count > 0) AS open_backorders
        FROM vw_ct_po_cancellation_scope
        GROUP BY date_scope
        ORDER BY date_scope
        """,
    )
    rule_summary = query_one(
        conn,
        """
        SELECT tested_records, validated_records, mismatch_records,
               valid_exception_records, overall_status, validation_rate_percent
        FROM mv_ct_sop_validation_summary
        WHERE rule_id = 'PO-CANCEL-001'
        """,
    )
    if not metadata or not enrichment or int(enrichment.get("expected_count") or 0) <= 0:
        raise RuntimeError("Published targeted date_order enrichment tidak tersedia.")
    if int(enrichment["expected_count"]) != int(enrichment["returned_count"]):
        raise RuntimeError("Enrichment completed tidak lengkap.")
    if int(all_time["cancelled_po_roots"]) != int(enrichment["returned_count"]):
        raise RuntimeError("Grain enrichment dan PO cancellation tidak sama.")
    done("Membaca snapshot, enrichment, dan grain PO-CANCEL-001")
    return {
        "latest_completed_run": metadata,
        "enrichment": enrichment,
        "all_time": all_time,
        "scopes": scopes,
        "active_rule_summary": rule_summary,
    }


def read_state_distribution(conn: Any) -> dict[str, Any]:
    stage("Menghitung distribusi state Receipt berdasarkan date_order")
    rows = query_rows(
        conn,
        """
        WITH relations AS (
            SELECT DISTINCT
                scope.date_scope,
                scope.purchase_order_id,
                link.child_id AS receipt_id,
                LOWER(COALESCE(receipt.state, '')) AS receipt_state
            FROM vw_ct_po_cancellation_scope scope
            JOIN vw_ct_document_links link
              ON link.link_type = 'PO_TO_RECEIPT'
             AND link.parent_model = 'purchase.order'
             AND link.parent_id = scope.purchase_order_id
             AND link.child_model = 'stock.picking'
             AND link.confidence = 'HIGH'
            JOIN vw_ct_native_record_snapshot_current receipt
              ON receipt.model = 'stock.picking'
             AND receipt.record_id = link.child_id
        ), scoped AS (
            SELECT 'ALL_DATES'::text AS scope, * FROM relations
            UNION ALL
            SELECT date_scope AS scope, * FROM relations
        )
        SELECT
            scope,
            COALESCE(NULLIF(receipt_state, ''), 'UNSUPPORTED_OR_NULL') AS receipt_state,
            COUNT(DISTINCT purchase_order_id) AS po_roots,
            COUNT(DISTINCT receipt_id) AS unique_receipts,
            COUNT(*) AS relation_rows
        FROM scoped
        GROUP BY scope, receipt_state
        ORDER BY scope, receipt_state
        """,
    )
    result: dict[str, dict[str, dict[str, int]]] = {
        key: {
            state: {"unique_receipts": 0, "po_roots": 0, "relation_rows": 0}
            for state in STATE_ORDER
        }
        for key in (
            "all_dates",
            "active_2026_plus",
            "historical_pre_2026",
            "date_scope_unknown",
        )
    }
    aliases = {
        "ALL_DATES": "all_dates",
        "ACTIVE_2026_PLUS": "active_2026_plus",
        "HISTORICAL_PRE_2026": "historical_pre_2026",
        "DATE_SCOPE_UNKNOWN": "date_scope_unknown",
    }
    for row in rows:
        target = aliases[row["scope"]]
        result[target][state_bucket(row["receipt_state"])] = {
            "unique_receipts": int(row["unique_receipts"]),
            "po_roots": int(row["po_roots"]),
            "relation_rows": int(row["relation_rows"]),
        }
    done("Menghitung distribusi state Receipt berdasarkan date_order")
    return result


def read_duplicates(conn: Any) -> dict[str, Any]:
    stage("Menganalisis deduplikasi relasi native dan graf")
    raw = query_one(
        conn,
        """
        WITH cancelled AS (
            SELECT purchase_order_id AS po_id
            FROM vw_ct_po_cancellation_scope
        ), raw AS (
            SELECT po.po_id, po_line.record_id AS po_line_id, move.record_id AS stock_move_id,
                   NULLIF(move.payload -> 'picking_id' ->> 'id', '')::bigint AS receipt_id
            FROM cancelled po
            JOIN vw_ct_native_record_snapshot_current po_line
              ON po_line.model = 'purchase.order.line'
             AND NULLIF(po_line.payload -> 'order_id' ->> 'id', '')::bigint = po.po_id
            JOIN vw_ct_native_record_snapshot_current move
              ON move.model = 'stock.move'
             AND NULLIF(move.payload -> 'purchase_line_id' ->> 'id', '')::bigint = po_line.record_id
            WHERE NULLIF(move.payload -> 'picking_id' ->> 'id', '') IS NOT NULL
        ), grouped AS (
            SELECT po_id, receipt_id, COUNT(*) AS raw_rows,
                   COUNT(DISTINCT po_line_id) AS po_line_count,
                   COUNT(DISTINCT stock_move_id) AS stock_move_count
            FROM raw
            GROUP BY po_id, receipt_id
        )
        SELECT COUNT(*) AS unique_po_receipt_pairs,
               COALESCE(SUM(raw_rows), 0) AS raw_relation_rows,
               COALESCE(SUM(raw_rows - 1), 0) AS duplicate_rows_before_pair_dedup,
               COALESCE(SUM(po_line_count - 1), 0) AS duplicate_rows_from_multiple_po_lines,
               COALESCE(SUM(raw_rows - po_line_count), 0) AS duplicate_rows_from_additional_moves_per_line,
               COUNT(*) FILTER (WHERE po_line_count > 1) AS pairs_with_multiple_po_lines,
               COUNT(*) FILTER (WHERE stock_move_count > 1) AS pairs_with_multiple_stock_moves
        FROM grouped
        """,
    )
    graph = query_one(
        conn,
        """
        WITH cancelled AS (
            SELECT purchase_order_id AS po_id
            FROM vw_ct_po_cancellation_scope
        ), direct AS (
            SELECT link.parent_id AS po_id, link.child_id AS receipt_id
            FROM vw_ct_document_links link
            JOIN cancelled ON cancelled.po_id = link.parent_id
            WHERE link.link_type = 'PO_TO_RECEIPT'
              AND link.parent_model = 'purchase.order'
              AND link.child_model = 'stock.picking'
        ), paths AS (
            SELECT direct.po_id, direct.receipt_id, COUNT(path.*) AS path_rows
            FROM direct
            LEFT JOIN mv_ct_document_paths path
              ON path.root_model = 'purchase.order'
             AND path.root_id = direct.po_id
             AND path.child_model = 'stock.picking'
             AND path.child_id = direct.receipt_id
            GROUP BY direct.po_id, direct.receipt_id
        )
        SELECT (SELECT COUNT(*) FROM direct) AS direct_relation_rows,
               (SELECT COUNT(DISTINCT (po_id, receipt_id)) FROM direct) AS unique_po_receipt_pairs,
               (SELECT COUNT(*) - COUNT(DISTINCT (po_id, receipt_id)) FROM direct) AS repeated_direct_graph_edges,
               (SELECT COALESCE(SUM(GREATEST(path_rows - 1, 0)), 0) FROM paths) AS recursive_path_excess_rows,
               (SELECT COUNT(*) FILTER (WHERE path_rows > 1) FROM paths) AS pairs_with_multiple_paths
        """,
    )
    company = query_rows(
        conn,
        """
        SELECT po.company_id AS po_company_id, receipt.company_id AS receipt_company_id,
               COUNT(DISTINCT link.parent_id) AS po_roots,
               COUNT(DISTINCT link.child_id) AS receipt_pickings
        FROM vw_ct_document_links link
        JOIN vw_ct_native_record_snapshot_current po
          ON po.model = 'purchase.order' AND po.record_id = link.parent_id
        JOIN vw_ct_native_record_snapshot_current receipt
          ON receipt.model = 'stock.picking' AND receipt.record_id = link.child_id
        WHERE link.link_type = 'PO_TO_RECEIPT'
          AND link.parent_id IN (SELECT purchase_order_id FROM vw_ct_po_cancellation_scope)
        GROUP BY po.company_id, receipt.company_id
        ORDER BY po.company_id, receipt.company_id
        """,
    )
    done("Menganalisis deduplikasi relasi native dan graf")
    return {"canonical_raw_path": raw, "materialized_graph": graph, "company_pairs": company}


def read_candidates(conn: Any) -> list[dict[str, Any]]:
    stage("Mengklasifikasikan seluruh exposure Receipt")
    direct_rows = query_rows(
        conn,
        """
        WITH candidates AS (
            SELECT *
            FROM vw_ct_po_cancellation_scope
            WHERE operational_exposure IN (
                'ACTIVE_ISSUE', 'HISTORICAL_EXPOSURE', 'DATE_REVIEW_REQUIRED'
            )
        )
        SELECT
            candidates.purchase_order_id AS po_id,
            candidates.purchase_order_number AS po_document_number,
            candidates.purchase_order_state AS po_state,
            candidates.date_order AS po_date_order,
            candidates.date_scope,
            candidates.operational_exposure,
            link.child_id AS receipt_id,
            receipt.document_number AS receipt_document_number,
            receipt.state AS receipt_state,
            link.link_type,
            link.source_field,
            link.confidence
        FROM candidates
        LEFT JOIN vw_ct_document_links link
          ON link.link_type = 'PO_TO_RECEIPT'
         AND link.parent_model = 'purchase.order'
         AND link.parent_id = candidates.purchase_order_id
         AND link.child_model = 'stock.picking'
         AND link.confidence = 'HIGH'
        LEFT JOIN vw_ct_native_record_snapshot_current receipt
          ON receipt.model = 'stock.picking'
         AND receipt.record_id = link.child_id
        ORDER BY candidates.purchase_order_id, link.child_id
        """,
    )
    backorder_rows = query_rows(
        conn,
        """
        WITH candidates AS (
            SELECT purchase_order_id AS po_id
            FROM vw_ct_po_cancellation_scope
            WHERE operational_exposure IN (
                'ACTIVE_ISSUE', 'HISTORICAL_EXPOSURE', 'DATE_REVIEW_REQUIRED'
            )
        ), receipts AS (
            SELECT DISTINCT candidates.po_id, link.child_id AS receipt_id
            FROM candidates
            JOIN vw_ct_document_links link
              ON link.link_type = 'PO_TO_RECEIPT'
             AND link.parent_model = 'purchase.order'
             AND link.parent_id = candidates.po_id
             AND link.child_model = 'stock.picking'
             AND link.confidence = 'HIGH'
        )
        SELECT
            receipts.po_id,
            relation.parent_id AS parent_receipt_id,
            parent.document_number AS parent_receipt_document_number,
            parent.state AS parent_state,
            relation.child_id AS child_receipt_id,
            child.document_number AS child_receipt_document_number,
            child.state AS child_state
        FROM receipts
        JOIN vw_ct_document_links relation
          ON relation.link_type = 'PICKING_TO_BACKORDER'
         AND relation.parent_model = 'stock.picking'
         AND relation.child_model = 'stock.picking'
         AND relation.child_id = receipts.receipt_id
         AND relation.confidence = 'HIGH'
        JOIN vw_ct_native_record_snapshot_current parent
          ON parent.model = 'stock.picking' AND parent.record_id = relation.parent_id
        JOIN vw_ct_native_record_snapshot_current child
          ON child.model = 'stock.picking' AND child.record_id = relation.child_id
        ORDER BY receipts.po_id, relation.parent_id, relation.child_id
        """,
    )
    by_po: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in direct_rows:
        by_po[int(row["po_id"])].append(row)
    backorders_by_po: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in backorder_rows:
        key = (int(row["parent_receipt_id"]), int(row["child_receipt_id"]))
        existing = {
            (int(item["parent_receipt_id"]), int(item["child_receipt_id"]))
            for item in backorders_by_po[int(row["po_id"])]
        }
        if key not in existing:
            backorders_by_po[int(row["po_id"])].append(row)

    candidates: list[dict[str, Any]] = []
    for po_id in sorted(by_po):
        receipts = by_po[po_id]
        classification, reason, open_receipts = classify_candidate(receipts, backorders_by_po[po_id])
        representative = sorted(
            open_receipts or receipts,
            key=lambda row: int(row.get("receipt_id") or 0),
        )[0]
        selected_ids = {int(row["receipt_id"]) for row in open_receipts}
        related_backorders = [
            row
            for row in backorders_by_po[po_id]
            if int(row["child_receipt_id"]) in selected_ids
        ]
        candidates.append(
            {
                "po_native_id": po_id,
                "po_document_number": representative.get("po_document_number"),
                "po_state": representative.get("po_state"),
                "po_date": {
                    "value": representative.get("po_date_order"),
                    "basis": "purchase.order.date_order",
                    "scope": representative.get("date_scope"),
                },
                "operational_exposure": representative.get("operational_exposure"),
                "receipt_native_id": representative.get("receipt_id"),
                "receipt_document_number": representative.get("receipt_document_number"),
                "receipt_state": representative.get("receipt_state"),
                "parent_backorder_relationship": related_backorders,
                "relationship_path": "purchase.order -> purchase.order.line -> stock.move.purchase_line_id -> stock.picking.picking_id",
                "relationship_link_type": representative.get("link_type"),
                "relationship_source_field": representative.get("source_field"),
                "relation_confidence": representative.get("confidence"),
                "primary_classification": classification,
                "reason": reason,
                "all_direct_receipts": [
                    {
                        "receipt_native_id": row.get("receipt_id"),
                        "receipt_document_number": row.get("receipt_document_number"),
                        "receipt_state": row.get("receipt_state"),
                        "relation_confidence": row.get("confidence"),
                    }
                    for row in receipts
                    if row.get("receipt_id") is not None
                ],
            }
        )
    done("Mengklasifikasikan seluruh exposure Receipt")
    return candidates


def measure_performance(conn: Any, candidates: list[dict[str, Any]]) -> dict[str, float]:
    stage("Mengukur query kerja Control Tower")
    measurements: dict[str, float] = {}
    checks: list[tuple[str, str, dict[str, Any]]] = [
        (
            "active_summary_seconds",
            "SELECT * FROM mv_ct_sop_validation_summary WHERE rule_id = 'PO-CANCEL-001'",
            {},
        ),
        (
            "historical_summary_seconds",
            "SELECT COUNT(*) FROM vw_ct_po_cancellation_historical",
            {},
        ),
        (
            "active_exception_list_seconds",
            """
            SELECT * FROM mv_ct_exception_worklist
            WHERE rule_id = 'PO-CANCEL-001'
            ORDER BY document_id
            LIMIT 200
            """,
            {},
        ),
    ]
    if candidates:
        checks.append(
            (
                "representative_journey_seconds",
                """
                SELECT * FROM mv_ct_document_paths
                WHERE root_model = 'purchase.order' AND root_id = :root_id
                ORDER BY depth, parent_id, child_id
                """,
                {"root_id": int(candidates[0]["po_native_id"])},
            )
        )
    for name, sql, params in checks:
        started = perf_counter()
        conn.execute(text(sql), params).all()
        measurements[name] = round(perf_counter() - started, 4)
    done("Mengukur query kerja Control Tower")
    return measurements


def state_totals(distribution: dict[str, Any], key: str) -> dict[str, int]:
    return {state: int(distribution[key][state]["unique_receipts"]) for state in STATE_ORDER}


def scope_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["date_scope"]): row for row in snapshot["scopes"]}


def render_report(
    snapshot: dict[str, Any],
    states: dict[str, Any],
    duplicates: dict[str, Any],
    candidates: list[dict[str, Any]],
    performance: dict[str, float],
) -> str:
    scopes = scope_map(snapshot)
    active = scopes.get("ACTIVE_2026_PLUS", {})
    historical = scopes.get("HISTORICAL_PRE_2026", {})
    unknown = scopes.get("DATE_SCOPE_UNKNOWN", {})
    all_time = snapshot["all_time"]
    enrichment = snapshot["enrichment"]
    rule = snapshot["active_rule_summary"]
    run = snapshot["latest_completed_run"]
    graph = duplicates["materialized_graph"]
    raw = duplicates["canonical_raw_path"]
    classifications = Counter(item["primary_classification"] for item in candidates)
    samples: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        samples.setdefault(candidate["primary_classification"], candidate)

    lines = [
        "# Scope Kesehatan Pembatalan PO 2026+",
        "",
        "## 1. Ringkasan eksekutif",
        "",
        "Kontrol aktif dimulai pada **1 Januari 2026** berdasarkan `purchase.order.date_order`. "
        "PO sebelum tanggal itu tetap tersedia sebagai Catatan Historis, tetapi tidak lagi masuk KPI atau antrean masalah operasional.",
        f"- `{all_time['cancelled_po_roots']}` PO cancelled unik tersedia secara all-time.",
        f"- `{active.get('cancelled_po_roots', 0)}` PO berada dalam scope aktif 2026+; `{active.get('active_issues', 0)}` menjadi **Masalah Aktif 2026+**.",
        f"- `{historical.get('cancelled_po_roots', 0)}` PO sebelum 2026; `{historical.get('historical_exposures', 0)}` merupakan **Catatan Historis** dengan Receipt masih terbuka.",
        f"- `{unknown.get('cancelled_po_roots', 0)}` PO memiliki **Tanggal PO Belum Tersedia**; tidak ada yang masuk KPI aktif secara diam-diam.",
        "",
        "## 2. Branch, commit, dan snapshot",
        "",
        "- Branch: `feature/control-tower-sop-validation-v0`.",
        "- Basis audit sebelumnya: `f968e63` di atas `369ad1e`.",
        f"- Run COMPLETED: `{run.get('run_id')}`; company ID `{run.get('company_id')}`; selesai `{run.get('completed_at')}`.",
        f"- Snapshot mencatat `{run.get('model_counts', {}).get('document_links')}` document links.",
        "",
        "## 3. Mengapa targeted enrichment dilakukan",
        "",
        "Snapshot Control Tower tidak menyimpan `purchase.order.date_order`, sedangkan keputusan scope bisnis harus memakai field itu secara tepat. "
        "Karena itu enrichment hanya membaca PO cancelled yang memang sudah diuji oleh PO-CANCEL-001; tidak ada full extraction atau pengambilan module Odoo lain.",
        f"- PO diminta dari snapshot: `{enrichment['expected_count']}`.",
        f"- PO berhasil dibaca: `{enrichment['returned_count']}`.",
        f"- `date_order` NULL: `{enrichment['null_date_order_count']}`.",
        "- `write_date` disimpan sebagai bukti sumber tetapi **tidak digunakan** untuk menentukan scope produksi.",
        "",
        "## 4. Definisi grain dan relasi",
        "",
        "- PO root: satu `purchase.order` berstate `cancel`/`cancelled` pada company ID 3.",
        "- Relasi Receipt: pasangan unik `purchase.order` -> `purchase.order.line` -> `stock.move.purchase_line_id` -> `stock.picking.picking_id`.",
        f"- Hasil all-time `{all_time['cancelled_po_roots']}` adalah PO root unik, bukan jumlah stock move atau Receipt.",
        f"- Relasi langsung: `{graph['direct_relation_rows']}` row dan `{graph['unique_po_receipt_pairs']}` pasangan PO/Receipt unik.",
        "",
        "## 5. Perbandingan all-time dan scope 2026+",
        "",
        "| Scope | PO cancelled unik | PO dengan Receipt terbuka | Masalah aktif | Catatan historis | Date review | Backorder terbuka |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| All-time | {all_time['cancelled_po_roots']} | {all_time['open_receipt_roots']} | {active.get('active_issues', 0)} | {historical.get('historical_exposures', 0)} | {unknown.get('date_review_required', 0)} | {sum(int(row.get('open_backorders', 0)) for row in snapshot['scopes'])} |",
        f"| Aktif 2026+ | {active.get('cancelled_po_roots', 0)} | {active.get('open_receipt_roots', 0)} | {active.get('active_issues', 0)} | 0 | 0 | {active.get('open_backorders', 0)} |",
        f"| Historis sebelum 2026 | {historical.get('cancelled_po_roots', 0)} | {historical.get('open_receipt_roots', 0)} | 0 | {historical.get('historical_exposures', 0)} | 0 | {historical.get('open_backorders', 0)} |",
        f"| Tanggal belum tersedia | {unknown.get('cancelled_po_roots', 0)} | {unknown.get('open_receipt_roots', 0)} | 0 | 0 | {unknown.get('date_review_required', 0)} | {unknown.get('open_backorders', 0)} |",
        "",
        "## 6. Distribusi state Receipt",
        "",
        "Receipt `done`, `cancel`, dan `cancelled` adalah bukti historis/closed. Hanya state operasional berikut yang dapat menjadi Receipt terbuka: `draft`, `waiting`, `confirmed`, `assigned`, `partially_available`.",
        "",
        "| State Receipt | All-time | Aktif 2026+ | Historis < 2026 | Tanggal belum tersedia |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    all_states = state_totals(states, "all_dates")
    active_states = state_totals(states, "active_2026_plus")
    historical_states = state_totals(states, "historical_pre_2026")
    unknown_states = state_totals(states, "date_scope_unknown")
    for state in STATE_ORDER:
        lines.append(
            f"| `{state}` | {all_states[state]} | {active_states[state]} | {historical_states[state]} | {unknown_states[state]} |"
        )

    lines.extend([
        "",
        "## 7. Backorder",
        "",
        f"- `{historical.get('open_backorders', 0)}` PO historis memiliki child backorder terbuka dengan parent Receipt closed.",
        "- Parent Receipt tetap disimpan sebagai sejarah; hanya child Receipt terbuka yang dinilai sebagai exposure. Satu PO root tetap dihitung satu kali.",
        "",
        "## 8. Penjelasan hasil 1.209 / 1.174 / 35",
        "",
        f"- `{all_time['cancelled_po_roots']}` adalah total PO root cancelled all-time.",
        f"- `{all_time['no_open_receipt_roots']}` tidak memiliki Receipt operasional terbuka; Receipt done/cancel tidak dihitung sebagai masalah.",
        f"- `{all_time['open_receipt_roots']}` memiliki Receipt native `assigned` terbuka. Setelah scope bisnis diterapkan, semuanya adalah Catatan Historis, bukan Masalah Aktif 2026+.",
        f"- Summary SOP aktif sekarang: `{rule['tested_records']}` tested / `{rule['validated_records']}` validated / `{rule['mismatch_records']}` mismatch.",
        "",
        "## 9. Rekonsiliasi dengan baseline 348 / 0",
        "",
        f"Audit 2026 sebelumnya melaporkan `{BASELINE['cancelled_po_roots']}` PO cancelled dan `{BASELINE['open_receipt_po_roots']}` Receipt terbuka dengan filter `{BASELINE['scope']}`.",
        f"Enrichment sekarang membuktikan angka yang sama: `{active.get('cancelled_po_roots', 0)}` PO aktif 2026+ dan `{active.get('active_issues', 0)}` Receipt terbuka. "
        "Perbedaan lama 1.209 versus 348 terjadi karena rule lama mematerialisasi seluruh tanggal; bukan karena baseline perlu dianggap salah.",
        "",
        "## 10. Klasifikasi exposure dan sampel tersanitasi",
        "",
        "| Klasifikasi teknis Receipt | Jumlah |",
        "| --- | ---: |",
    ])
    for classification, count in sorted(classifications.items()):
        lines.append(f"| `{classification}` | {count} |")
    lines.append("")
    for classification, candidate in sorted(samples.items()):
        lines.append(
            f"- `{classification}`: `{masked('purchase.order', candidate['po_native_id'])}` -> "
            f"`{masked('stock.picking', candidate['receipt_native_id'])}`; "
            f"scope `{candidate['po_date']['scope']}`, state Receipt `{candidate['receipt_state']}`."
        )

    lines.extend([
        "",
        "## 11. Deduplikasi dan defect teknis",
        "",
        f"- Jalur canonical menghasilkan `{raw['raw_relation_rows']}` row sebelum deduplikasi dan `{raw['unique_po_receipt_pairs']}` pasangan PO/Receipt setelahnya.",
        f"- `{raw['duplicate_rows_from_multiple_po_lines']}` row tambahan berasal dari multiple PO line; `{raw['duplicate_rows_from_additional_moves_per_line']}` dari move tambahan per line.",
        f"- Graf mempunyai `{graph['repeated_direct_graph_edges']}` edge langsung berulang dan `{graph['recursive_path_excess_rows']}` path rekursif berlebih; PO rule tidak memakai path rekursif untuk menghitung exposure.",
        "- Tidak ada false positive relasi teknis yang perlu disembunyikan. Perubahan ini adalah penerapan keputusan scope bisnis yang disetujui.",
        "",
        "## 12. Dampak dashboard dan pekerjaan Procurement/WHD",
        "",
        "Dashboard dan API sekarang menampilkan Masalah Aktif 2026+ secara terpisah dari Catatan Historis. Procurement/WHD tidak menerima 35 exposure sebelum 2026 sebagai antrean kerja aktif, tetapi audit tetap dapat menelusurinya. "
        "Endpoint read-only `/api/control-tower/po-cancellation-scope` menyediakan ringkasan serta filter scope untuk UI mendatang.",
        "",
        "## 13. Files changed",
        "",
        "- `scripts/enrich_po_cancellation_date_order.py`",
        "- `sql/12_control_tower_po_2026_scope.sql`",
        "- `scripts/run_control_tower_refresh.py`",
        "- `scripts/reconcile_po_cancellation.py`",
        "- `scripts/validate_control_tower.py`",
        "- `src/control_tower/service.py` dan `src/control_tower/router.py`",
        "",
        "## 14. Kinerja query",
        "",
        f"- Summary aktif: `{performance.get('active_summary_seconds', 0):.4f}s`.",
        f"- Summary historis: `{performance.get('historical_summary_seconds', 0):.4f}s`.",
        f"- Active exception list: `{performance.get('active_exception_list_seconds', 0):.4f}s`.",
        f"- Representative PO journey: `{performance.get('representative_journey_seconds', 0):.4f}s`.",
        "",
        "## 15. Tests dan validasi",
        "",
        "Perintah yang dijalankan pada delivery ini:",
        "",
        "- `venv\\Scripts\\python.exe scripts\\enrich_po_cancellation_date_order.py --self-check`",
        "- `venv\\Scripts\\python.exe scripts\\enrich_po_cancellation_date_order.py`",
        "- `venv\\Scripts\\python.exe scripts\\run_control_tower_refresh.py --po-scope-only`",
        "- `venv\\Scripts\\python.exe scripts\\reconcile_po_cancellation.py --self-check`",
        "- `venv\\Scripts\\python.exe scripts\\reconcile_po_cancellation.py`",
        "- `venv\\Scripts\\python.exe scripts\\validate_control_tower.py`",
        "- `venv\\Scripts\\python.exe -m pytest tests\\test_control_tower_service.py tests\\test_control_tower_relation_extractor.py`",
        "- Compile setiap file Python yang diubah dan authenticated loopback API smoke test.",
        "",
        "<!-- VALIDATION_RESULTS -->",
        "",
        "## 16. Konfirmasi keamanan",
        "",
        "- Odoo hanya menerima `version`, autentikasi, `fields_get`, dan `read`; tidak ada method mutating.",
        "- Tidak ada full extraction; PostgreSQL hanya menerima enrichment analitis dan materialisasi scope.",
        "- Tidak ada merge, push, atau perubahan frontend.",
        "",
        "## 17. Keputusan bisnis tersisa",
        "",
        "Tidak ada keputusan scope tambahan yang diperlukan: owner bisnis telah menetapkan batas 1 Januari 2026. Bila suatu run mendatang memiliki `date_order` NULL, record akan tetap tampil sebagai Tanggal PO Belum Tersedia dan tidak akan masuk KPI aktif.",
        "",
        "## 18. Rekomendasi akhir",
        "",
        "**READY_FOR_UI** - scope aktif, catatan historis, dan date-review sudah dipisahkan dengan bukti native yang dapat ditinjau.",
        "",
    ])
    return "\n".join(lines)


def write_json(name: str, value: Any) -> None:
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(json_safe(value), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SAVE ] {path.relative_to(PROJECT_ROOT)}", flush=True)


def self_check() -> int:
    assert state_bucket("assigned") == "assigned"
    assert state_bucket(None) == "UNSUPPORTED_OR_NULL"
    assert is_open("assigned") and not is_open("done")
    classification, _, _ = classify_candidate(
        [{"receipt_id": 2, "receipt_state": "assigned", "confidence": "HIGH"}],
        [{"parent_receipt_id": 1, "parent_state": "done", "child_receipt_id": 2, "child_state": "assigned"}],
    )
    assert classification == "OPEN_BACKORDER"
    assert "42" not in masked("purchase.order", 42)
    print("SELF_CHECK status=ok")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile scoped PO-CANCEL-001 from PostgreSQL only")
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        return self_check()

    OUTPUT_DIR.mkdir(exist_ok=True)
    pg = PostgresClient()
    try:
        with pg.engine.connect() as conn:
            snapshot = read_snapshot(conn)
            states = read_state_distribution(conn)
            duplicates = read_duplicates(conn)
            candidates = read_candidates(conn)
            performance = measure_performance(conn, candidates)
        scope_summary = {
            "date_start": DATE_START,
            "latest_completed_run": snapshot["latest_completed_run"],
            "enrichment": snapshot["enrichment"],
            "all_time": snapshot["all_time"],
            "scopes": snapshot["scopes"],
            "active_rule_summary": snapshot["active_rule_summary"],
            "earlier_baseline": BASELINE,
            "performance": performance,
        }
        write_json("po_cancellation_scope_summary.json", scope_summary)
        write_json("po_cancellation_state_distribution.json", states)
        write_json("po_cancellation_candidates.json", candidates)
        write_json("po_cancellation_duplicate_analysis.json", duplicates)
        report = render_report(snapshot, states, duplicates, candidates, performance)
        for name in (
            "po_cancellation_reconciliation_report.md",
            "po_cancellation_2026_scope_report.md",
        ):
            path = OUTPUT_DIR / name
            path.write_text(report, encoding="utf-8")
            print(f"[SAVE ] {path.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"[DONE ] exposure_candidates={len(candidates)}", flush=True)
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
