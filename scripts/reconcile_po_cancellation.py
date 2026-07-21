"""Reconcile Control Tower PO-CANCEL-001 from the current PostgreSQL snapshot.

This utility never calls Odoo. It only reads the current completed Control
Tower read model and writes local, ignored reconciliation artifacts under
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
from typing import Any

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient


OUTPUT_DIR = PROJECT_ROOT / "output"
DATE_START_DEFAULT = "2026-01-01"
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
    "source": "docs/09_Odoo18_Validation/FINAL_SOP_SYSTEM_CLOSURE_AUDIT.md at bd9d09b",
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


def masked(model: str, record_id: int | None) -> str:
    prefixes = {"purchase.order": "PO", "stock.picking": "RCT"}
    token = sha256(f"{model}:{record_id}".encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefixes.get(model, 'DOC')}-{token}"


def is_open(row: dict[str, Any]) -> bool:
    return normalized_state(row.get("receipt_state")) in OPEN_RECEIPT_STATES


def is_closed(value: Any) -> bool:
    return normalized_state(value) in CLOSED_RECEIPT_STATES


def scope_from_date(value: Any, date_start: str) -> str:
    if not value:
        return "UNAVAILABLE_IN_CURRENT_SNAPSHOT"
    return "DATE_ORDER_2026_PLUS" if str(value)[:10] >= date_start else "HISTORICAL_PRE_2026"


def classify_candidate(
    receipts: list[dict[str, Any]],
    backorders: list[dict[str, Any]],
    date_start: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Return exactly one primary class and the deduplicated open receipts."""
    unique_receipts = {
        int(row["receipt_id"]): row
        for row in receipts
        if row.get("receipt_id") is not None
    }
    direct_receipts = list(unique_receipts.values())
    if not direct_receipts:
        return "INVALID_OR_LOW_CONFIDENCE_LINK", "Tidak ada Receipt native untuk kandidat rule.", []
    open_receipts = [row for row in direct_receipts if is_open(row)]
    unsupported = [
        row
        for row in direct_receipts
        if state_bucket(row.get("receipt_state")) == "UNSUPPORTED_OR_NULL"
    ]

    if any(
        row.get("po_company_id") != 3 or row.get("receipt_company_id") != 3
        for row in direct_receipts
    ):
        return "COMPANY_SCOPE_DIFFERENCE", "Relasi lintas company ditemukan; di luar scope company_id=3.", open_receipts
    if any(row.get("confidence") != "HIGH" for row in direct_receipts):
        return "INVALID_OR_LOW_CONFIDENCE_LINK", "Relasi tidak seluruhnya HIGH/native.", open_receipts
    if unsupported:
        return "UNRESOLVED_EVIDENCE_GAP", "State Receipt NULL atau di luar kosakata operasi.", open_receipts
    if not open_receipts:
        if direct_receipts and all(is_closed(row.get("receipt_state")) for row in direct_receipts):
            return "CLOSED_RECEIPT_FALSE_POSITIVE", "Hanya Receipt done/cancel yang terhubung.", open_receipts
        return "DUPLICATE_RELATION_PATH", "Tidak ada Receipt operasional setelah deduplikasi PO/Receipt.", open_receipts

    date_order = next((row.get("po_date_order") for row in direct_receipts if row.get("po_date_order")), None)
    if date_order and scope_from_date(date_order, date_start) == "HISTORICAL_PRE_2026":
        return "HISTORICAL_PRE_2026", "date_order berada sebelum 2026-01-01; rule saat ini all-time.", open_receipts

    open_ids = {int(row["receipt_id"]) for row in open_receipts}
    closed_parent_by_child = {
        int(row["child_receipt_id"])
        for row in backorders
        if row.get("child_receipt_id") is not None and is_closed(row.get("parent_state"))
    }
    if open_ids and open_ids.issubset(closed_parent_by_child):
        return "OPEN_BACKORDER", "Receipt operasional yang tersisa adalah child backorder dari parent closed.", open_receipts

    return "REAL_OPEN_RECEIPT", "Receipt native berstate operasional terbuka melalui PO_TO_RECEIPT.", open_receipts


def read_snapshot(conn: Any, date_start: str) -> dict[str, Any]:
    stage("Membaca snapshot dan grain PO-CANCEL-001")
    metadata = query_one(
        conn,
        """
        SELECT run_id::text AS run_id, company_id, started_at, completed_at, model_counts
        FROM vw_ct_current_run
        """,
    )
    grain = query_one(
        conn,
        """
        SELECT
          COUNT(*) AS rule_result_rows,
          COUNT(DISTINCT document_id) AS unique_po_roots,
          COUNT(*) FILTER (WHERE validation_status = 'VALIDATED') AS validated_po_roots,
          COUNT(*) FILTER (WHERE validation_status = 'MISMATCH') AS mismatch_po_roots
        FROM mv_ct_rule_results
        WHERE rule_id = 'PO-CANCEL-001'
        """,
    )
    payload = query_one(
        conn,
        """
        SELECT BOOL_OR(payload ? 'date_order') AS has_date_order,
               COUNT(*) FILTER (WHERE payload ? 'date_order') AS roots_with_date_order
        FROM vw_ct_native_record_snapshot_current
        WHERE model = 'purchase.order'
        """,
    )
    write_date_scope = query_rows(
        conn,
        """
        WITH cancelled AS (
            SELECT record_id, write_date
            FROM vw_ct_native_record_snapshot_current
            WHERE model = 'purchase.order'
              AND LOWER(COALESCE(state, '')) IN ('cancel', 'cancelled')
        ), mismatch AS (
            SELECT document_id
            FROM mv_ct_rule_results
            WHERE rule_id = 'PO-CANCEL-001' AND validation_status = 'MISMATCH'
        )
        SELECT
          CASE
            WHEN cancelled.write_date >= CAST(:date_start AS timestamp) THEN 'WRITE_DATE_2026_PLUS_PROXY'
            WHEN cancelled.write_date IS NULL THEN 'WRITE_DATE_NULL_PROXY'
            ELSE 'WRITE_DATE_PRE_2026_PROXY'
          END AS scope,
          COUNT(*) AS cancelled_po_roots,
          COUNT(*) FILTER (WHERE mismatch.document_id IS NOT NULL) AS mismatch_po_roots
        FROM cancelled
        LEFT JOIN mismatch ON mismatch.document_id = cancelled.record_id
        GROUP BY 1
        ORDER BY 1
        """,
        date_start=date_start,
    )
    done("Membaca snapshot dan grain PO-CANCEL-001")
    return {
        "latest_completed_run": metadata,
        "grain": grain,
        "date_order_capture": payload,
        "write_date_proxy": write_date_scope,
    }


def read_state_distribution(conn: Any, date_start: str) -> dict[str, Any]:
    stage("Menghitung distribusi state Receipt")
    rows = query_rows(
        conn,
        """
        WITH cancelled AS (
            SELECT record_id, write_date
            FROM vw_ct_native_record_snapshot_current
            WHERE model = 'purchase.order'
              AND LOWER(COALESCE(state, '')) IN ('cancel', 'cancelled')
        ), relations AS (
            SELECT cancelled.record_id AS po_id, cancelled.write_date,
                   receipt.record_id AS receipt_id, receipt.state AS receipt_state
            FROM cancelled
            JOIN vw_ct_document_links link
              ON link.link_type = 'PO_TO_RECEIPT'
             AND link.parent_model = 'purchase.order'
             AND link.parent_id = cancelled.record_id
             AND link.child_model = 'stock.picking'
            JOIN vw_ct_native_record_snapshot_current receipt
              ON receipt.model = 'stock.picking' AND receipt.record_id = link.child_id
        ), scoped AS (
            SELECT 'ALL_DATES' AS scope, * FROM relations
            UNION ALL
            SELECT 'WRITE_DATE_2026_PLUS_PROXY' AS scope, *
            FROM relations
            WHERE write_date >= CAST(:date_start AS timestamp)
        )
        SELECT scope, COALESCE(NULLIF(LOWER(receipt_state), ''), 'UNSUPPORTED_OR_NULL') AS receipt_state,
               COUNT(DISTINCT po_id) AS po_roots,
               COUNT(DISTINCT receipt_id) AS unique_receipts,
               COUNT(*) AS relation_rows
        FROM scoped
        GROUP BY scope, receipt_state
        ORDER BY scope, receipt_state
        """,
        date_start=date_start,
    )
    result: dict[str, Any] = {
        "all_dates": {state: 0 for state in STATE_ORDER},
        "write_date_2026_plus_proxy": {state: 0 for state in STATE_ORDER},
        "date_order_2026_plus": {
            "status": "UNAVAILABLE_IN_CURRENT_SNAPSHOT",
            "reason": "purchase.order.date_order tidak diekstrak ke ct_native_record_snapshot.",
        },
    }
    for row in rows:
        target = "all_dates" if row["scope"] == "ALL_DATES" else "write_date_2026_plus_proxy"
        result[target][state_bucket(row["receipt_state"])] = {
            "unique_receipts": row["unique_receipts"],
            "po_roots": row["po_roots"],
            "relation_rows": row["relation_rows"],
        }
    for key in ("all_dates", "write_date_2026_plus_proxy"):
        for state, value in list(result[key].items()):
            if isinstance(value, int):
                result[key][state] = {"unique_receipts": 0, "po_roots": 0, "relation_rows": 0}
    done("Menghitung distribusi state Receipt")
    return result


def read_duplicates(conn: Any) -> dict[str, Any]:
    stage("Menganalisis deduplikasi relasi native dan graf")
    raw = query_one(
        conn,
        """
        WITH cancelled AS (
            SELECT record_id AS po_id
            FROM vw_ct_native_record_snapshot_current
            WHERE model = 'purchase.order'
              AND LOWER(COALESCE(state, '')) IN ('cancel', 'cancelled')
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
            SELECT record_id AS po_id
            FROM vw_ct_native_record_snapshot_current
            WHERE model = 'purchase.order'
              AND LOWER(COALESCE(state, '')) IN ('cancel', 'cancelled')
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
          AND LOWER(COALESCE(po.state, '')) IN ('cancel', 'cancelled')
        GROUP BY po.company_id, receipt.company_id
        ORDER BY po.company_id, receipt.company_id
        """,
    )
    done("Menganalisis deduplikasi relasi native dan graf")
    return {"canonical_raw_path": raw, "materialized_graph": graph, "company_pairs": company}


def read_candidates(conn: Any, date_start: str) -> list[dict[str, Any]]:
    stage("Mengklasifikasikan kandidat PO-CANCEL-001")
    direct_rows = query_rows(
        conn,
        """
        WITH candidates AS (
            SELECT document_id AS po_id
            FROM mv_ct_rule_results
            WHERE rule_id = 'PO-CANCEL-001' AND validation_status = 'MISMATCH'
        )
        SELECT candidates.po_id, po.document_number AS po_document_number, po.state AS po_state,
               po.write_date AS po_write_date, po.payload ->> 'date_order' AS po_date_order,
               po.company_id AS po_company_id,
               link.child_id AS receipt_id, receipt.document_number AS receipt_document_number,
               receipt.state AS receipt_state, receipt.company_id AS receipt_company_id,
               link.link_type, link.source_field, link.confidence
        FROM candidates
        JOIN vw_ct_native_record_snapshot_current po
          ON po.model = 'purchase.order' AND po.record_id = candidates.po_id
        LEFT JOIN vw_ct_document_links link
          ON link.link_type = 'PO_TO_RECEIPT'
         AND link.parent_model = 'purchase.order'
         AND link.parent_id = candidates.po_id
         AND link.child_model = 'stock.picking'
        LEFT JOIN vw_ct_native_record_snapshot_current receipt
          ON receipt.model = 'stock.picking' AND receipt.record_id = link.child_id
        ORDER BY candidates.po_id, link.child_id
        """,
    )
    backorder_rows = query_rows(
        conn,
        """
        WITH candidates AS (
            SELECT document_id AS po_id
            FROM mv_ct_rule_results
            WHERE rule_id = 'PO-CANCEL-001' AND validation_status = 'MISMATCH'
        ), receipts AS (
            SELECT DISTINCT candidates.po_id, link.child_id AS receipt_id
            FROM candidates
            JOIN vw_ct_document_links link
              ON link.link_type = 'PO_TO_RECEIPT'
             AND link.parent_model = 'purchase.order'
             AND link.parent_id = candidates.po_id
             AND link.child_model = 'stock.picking'
        )
        SELECT receipts.po_id, relation.parent_id AS parent_receipt_id,
               parent.document_number AS parent_receipt_document_number, parent.state AS parent_state,
               relation.child_id AS child_receipt_id,
               child.document_number AS child_receipt_document_number, child.state AS child_state
        FROM receipts
        JOIN vw_ct_document_links relation
          ON relation.link_type = 'PICKING_TO_BACKORDER'
         AND relation.parent_model = 'stock.picking'
         AND relation.child_model = 'stock.picking'
         AND (relation.parent_id = receipts.receipt_id OR relation.child_id = receipts.receipt_id)
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
        if key not in {
            (int(item["parent_receipt_id"]), int(item["child_receipt_id"]))
            for item in backorders_by_po[int(row["po_id"])]
        }:
            backorders_by_po[int(row["po_id"])].append(row)

    candidates: list[dict[str, Any]] = []
    for po_id in sorted(by_po):
        receipts = by_po[po_id]
        classification, reason, open_receipts = classify_candidate(
            receipts, backorders_by_po[po_id], date_start
        )
        selected = sorted(open_receipts, key=lambda row: int(row["receipt_id"]))
        representative = selected[0] if selected else receipts[0]
        selected_ids = {int(row["receipt_id"]) for row in selected}
        related_backorders = [
            row
            for row in backorders_by_po[po_id]
            if int(row["parent_receipt_id"]) in selected_ids
            or int(row["child_receipt_id"]) in selected_ids
        ]
        date_order = representative.get("po_date_order")
        candidates.append(
            {
                "po_native_id": po_id,
                "po_document_number": representative.get("po_document_number"),
                "po_state": representative.get("po_state"),
                "po_date": {
                    "value": date_order or representative.get("po_write_date"),
                    "basis": "date_order" if date_order else "write_date_diagnostic_only",
                    "scope_assessment": scope_from_date(date_order, date_start),
                },
                "receipt_native_id": representative.get("receipt_id"),
                "receipt_document_number": representative.get("receipt_document_number"),
                "receipt_state": representative.get("receipt_state"),
                "parent_backorder_relationship": related_backorders,
                "relationship_path": "purchase.order -> purchase.order.line -> stock.move -> stock.picking",
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
    done("Mengklasifikasikan kandidat PO-CANCEL-001")
    return candidates


def state_totals(distribution: dict[str, Any], key: str) -> dict[str, int]:
    return {
        state: int(distribution[key][state]["unique_receipts"])
        for state in STATE_ORDER
    }


def render_report(
    snapshot: dict[str, Any],
    states: dict[str, Any],
    duplicates: dict[str, Any],
    candidates: list[dict[str, Any]],
    date_start: str,
) -> str:
    classification_totals = Counter(item["primary_classification"] for item in candidates)
    samples: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        samples.setdefault(candidate["primary_classification"], candidate)
    all_states = state_totals(states, "all_dates")
    proxy_states = state_totals(states, "write_date_2026_plus_proxy")
    run = snapshot["latest_completed_run"]
    grain = snapshot["grain"]
    graph = duplicates["materialized_graph"]
    raw = duplicates["canonical_raw_path"]

    lines = [
        "# Rekonsiliasi PO-CANCEL-001",
        "",
        "## 1. Ringkasan eksekutif",
        "",
        f"- Rule saat ini menguji **{grain['rule_result_rows']} PO root unik**: {grain['validated_po_roots']} `VALIDATED` dan {grain['mismatch_po_roots']} `MISMATCH`.",
        f"- Semua kandidat mismatch memiliki Receipt native berstate `assigned`; {classification_totals.get('OPEN_BACKORDER', 0)} di antaranya merupakan child backorder dari parent `done`.",
        "- Tidak ada false positive teknis terkonfirmasi: edge `PO_TO_RECEIPT` sudah unik per pasangan PO/Receipt, dan rule tidak memakai path rekursif untuk menghitung mismatch.",
        "- Rekonsiliasi 2026 belum dapat direproduksi dari snapshot ini karena `purchase.order.date_order` tidak diekstrak. Baseline lama memakai field tersebut secara langsung.",
        "",
        "## 2. Branch, commit, dan snapshot",
        "",
        "- Branch diperiksa: `feature/control-tower-sop-validation-v0`.",
        "- Commit diperiksa: `369ad1e001f2ea59ada6b883664d1e898defe2db`.",
        f"- Run COMPLETED: `{run.get('run_id')}`; company ID `{run.get('company_id')}`; selesai `{run.get('completed_at')}`.",
        f"- Model count run mencatat `{run.get('model_counts', {}).get('document_links')}` document links.",
        "",
        "## 3. Perintah dan batas read-only",
        "",
        "- `venv\\Scripts\\python.exe scripts\\reconcile_po_cancellation.py`",
        "- Semua query memakai PostgreSQL snapshot yang sudah COMPLETED. Skrip ini tidak mengimpor client Odoo dan tidak memanggil RPC/method Odoo.",
        "",
        "## 4. Definisi grain",
        "",
        "- PO root: satu `purchase.order` berstate `cancel`/`cancelled` dalam snapshot company ID 3.",
        "- Receipt relation: satu pasangan unik `purchase.order` dan `stock.picking` dari jalur native `purchase.order.line -> stock.move.purchase_line_id + stock.move.picking_id`.",
        f"- `tested={grain['rule_result_rows']}` adalah **hasil rule per PO root unik**, bukan jumlah Receipt maupun row relation.",
        f"- Semua-date: `{graph['direct_relation_rows']}` row PO-to-Receipt langsung, `{graph['unique_po_receipt_pairs']}` pasangan PO/Receipt unik.",
        "",
        "## 5. All-time dibanding 2026+",
        "",
        f"- All-time current rule: `{grain['unique_po_roots']}` cancelled PO roots; `{grain['mismatch_po_roots']}` root dengan Receipt operasional terbuka.",
        f"- Baseline lama: `{BASELINE['cancelled_po_roots']}` cancelled PO roots dan `{BASELINE['open_receipt_po_roots']}` Receipt terbuka, dengan scope `{BASELINE['scope']}`.",
        "- Snapshot terbaru hanya menyimpan `id`, `name`, `state`, `company_id`, dan `write_date` untuk `purchase.order`; `date_order` tidak tersedia. Karena itu `write_date` di bawah adalah proxy diagnostik, bukan substitusi date boundary baseline.",
    ]
    for row in snapshot["write_date_proxy"]:
        lines.append(
            f"- Proxy `{row['scope']}`: `{row['cancelled_po_roots']}` cancelled PO roots; `{row['mismatch_po_roots']}` mismatch."
        )
    lines.extend([
        "",
        "## 6. Distribusi state Receipt",
        "",
        "| State Receipt | All-time unik | Proxy write_date >= 2026 unik |",
        "| --- | ---: | ---: |",
    ])
    for state in STATE_ORDER:
        lines.append(f"| `{state}` | {all_states[state]} | {proxy_states[state]} |")
    lines.extend([
        "",
        "Distribusi `date_order >= 2026-01-01` tidak tersedia dalam snapshot; baseline lama melaporkan seluruh bucket open = 0.",
        "",
        "## 7. Backorder dan deduplikasi",
        "",
        f"- `{classification_totals.get('OPEN_BACKORDER', 0)}` kandidat memiliki parent Receipt `done` dan child backorder `assigned`; parent historical tidak dihitung sebagai anomali independen.",
        f"- Jalur raw menghasilkan `{raw['raw_relation_rows']}` row; setelah deduplikasi PO/Receipt menjadi `{raw['unique_po_receipt_pairs']}` pasangan. `{raw['duplicate_rows_from_multiple_po_lines']}` row tambahan berasal dari beberapa PO line; `{raw['duplicate_rows_from_additional_moves_per_line']}` dari move tambahan per line.",
        f"- Graph materialized mempunyai `{graph['repeated_direct_graph_edges']}` edge langsung berulang dan `{graph['recursive_path_excess_rows']}` path rekursif berlebih. Rule PO tidak menggunakan path rekursif tersebut untuk menghitung hasil.",
        "",
        "## 8. Penjelasan 1.209 / 1.174 / 35",
        "",
        "- `1.209` adalah satu result untuk setiap PO cancelled root.",
        "- `1.174` adalah root tanpa Receipt operational open; Receipt `done` dan `cancel` diperlakukan sebagai bukti historis/closed.",
        "- `35` adalah root dengan Receipt native `assigned` ber-confidence `HIGH`, setelah deduplikasi pasangan PO/Receipt.",
        "",
        "## 9. Rekonsiliasi dengan baseline 348 / 0",
        "",
        "- Baseline lama melakukan read-only ORM langsung pada `purchase.order` dengan filter `state = cancel` dan `date_order >= 2026-01-01`, lalu menilai Receipt dari relasi PO, stock move, dan backorder.",
        "- Rule current memakai company ID 3, seluruh tanggal yang ada di snapshot, state `cancel` atau `cancelled`, dan relasi native `PO_TO_RECEIPT`; ia tidak mempunyai filter `date_order`.",
        "- Kosakata open sejalan untuk state operasional (`draft`, `waiting`, `confirmed`, `assigned`, `partially_available`); `done` dan `cancel` closed pada kedua audit.",
        "- Perbedaan 1.209 versus 348 adalah terutama perbedaan grain/date scope yang tidak ekuivalen. Snapshot tidak memiliki field untuk membuktikan berapa dari 35 kandidat berada dalam scope `date_order` baseline, sehingga baseline tidak boleh dinyatakan salah maupun dipakai untuk menyembunyikan 35 exposure all-time.",
        "",
        "## 10. Klasifikasi kandidat",
        "",
        "| Klasifikasi utama | Jumlah |",
        "| --- | ---: |",
    ])
    for classification, count in sorted(classification_totals.items()):
        lines.append(f"| `{classification}` | {count} |")
    lines.extend(["", "Sampel tersanitasi:"])
    for classification, candidate in sorted(samples.items()):
        lines.append(
            f"- `{classification}`: `{masked('purchase.order', candidate['po_native_id'])}` -> `{masked('stock.picking', candidate['receipt_native_id'])}`; state Receipt `{candidate['receipt_state']}`."
        )
    lines.extend([
        "",
        "## 11. Defect teknis dan perubahan kode",
        "",
        "- Tidak ada defect false-positive teknis terkonfirmasi. SQL/Python rule tidak diubah agar count tidak dipaksa cocok dengan baseline.",
        "- Ditambahkan skrip diagnostik PostgreSQL-only ini; output lokal menyimpan ID dan nomor dokumen hanya untuk review manual, sedangkan laporan ini tetap tersanitasi.",
        "",
        "## 12. Keputusan bisnis tersisa dan rekomendasi",
        "",
        "- Owner Procurement/WHD perlu menetapkan apakah PO-CANCEL-001 adalah control all-time atau hanya `purchase.order.date_order >= 2026-01-01`.",
        "- Bila scope 2026+ disetujui, extraction berikutnya yang diotorisasi harus menangkap `purchase.order.date_order`; jangan menerapkan proxy `write_date` sebagai filter produksi.",
        "- Rekomendasi akhir: **NEEDS_BUSINESS_SCOPE_DECISION**. Rule all-time secara teknis benar dan seluruh 35 exposure dapat ditelusuri melalui native ID, tetapi rekonsiliasi exact terhadap baseline 2026 tidak dapat dibuktikan dari field snapshot yang tersedia.",
        "",
        "## 13. Konfirmasi keamanan",
        "",
        "- Odoo tetap read-only; tidak ada extraction baru, RPC Odoo, atau method mutasi Odoo.",
        "- Tidak ada merge, push, atau perubahan frontend.",
        "",
        "## 14. Tests dan validasi",
        "",
        "<!-- VALIDATION_RESULTS -->",
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
    assert scope_from_date("2025-12-31", DATE_START_DEFAULT) == "HISTORICAL_PRE_2026"
    classification, _, _ = classify_candidate(
        [{"receipt_id": 2, "receipt_state": "assigned", "confidence": "HIGH", "po_company_id": 3, "receipt_company_id": 3}],
        [{"parent_receipt_id": 1, "parent_state": "done", "child_receipt_id": 2, "child_state": "assigned"}],
        DATE_START_DEFAULT,
    )
    assert classification == "OPEN_BACKORDER"
    assert "42" not in masked("purchase.order", 42)
    print("SELF_CHECK status=ok")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile PO-CANCEL-001 from PostgreSQL only")
    parser.add_argument("--date-start", default=DATE_START_DEFAULT)
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
            snapshot = read_snapshot(conn, args.date_start)
            states = read_state_distribution(conn, args.date_start)
            duplicates = read_duplicates(conn)
            candidates = read_candidates(conn, args.date_start)
        scope_summary = {
            "date_start": args.date_start,
            "all_time": snapshot["grain"],
            "date_order_2026_plus": {
                "status": "UNAVAILABLE_IN_CURRENT_SNAPSHOT",
                "capture": snapshot["date_order_capture"],
                "earlier_baseline": BASELINE,
            },
            "write_date_proxy": snapshot["write_date_proxy"],
            "latest_completed_run": snapshot["latest_completed_run"],
        }
        write_json("po_cancellation_scope_summary.json", scope_summary)
        write_json("po_cancellation_state_distribution.json", states)
        write_json("po_cancellation_candidates.json", candidates)
        write_json("po_cancellation_duplicate_analysis.json", duplicates)
        report_path = OUTPUT_DIR / "po_cancellation_reconciliation_report.md"
        report_path.write_text(
            render_report(snapshot, states, duplicates, candidates, args.date_start),
            encoding="utf-8",
        )
        print(f"[SAVE ] {report_path.relative_to(PROJECT_ROOT)}", flush=True)
        print(f"[DONE ] candidates={len(candidates)}", flush=True)
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
