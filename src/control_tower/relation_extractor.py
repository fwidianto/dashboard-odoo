"""Ekstraktor relasi native Odoo untuk Control Tower Health v0.1.

Modul ini sengaja dipisahkan dari pipeline sync dashboard lama yang menyimpan
banyak field relasional sebagai display name. Ekstraktor membaca model terpilih
melalui ``OdooClient`` read-only dan menyimpan:

* snapshot JSONB per record dengan native ID yang dipertahankan; dan
* graph parent/child dokumen berbasis native ID.

Tidak ada method yang menulis ke Odoo. Semua write hanya menuju PostgreSQL
lokal milik dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Mapping, Optional
from uuid import uuid4

from sqlalchemy import text

from src.clients.odoo_client import OdooClient
from src.clients.postgres_client import PostgresClient
from src.utils.logging import get_logger


@dataclass(frozen=True)
class ModelSpec:
    model: str
    fields: tuple[str, ...]
    number_fields: tuple[str, ...] = ("name", "display_name")


@dataclass(frozen=True)
class LinkSpec:
    """Definisi relasi yang dibaca dari satu field Odoo.

    Secara default field berada pada child dan menunjuk parent, contohnya
    ``sale.order.line.order_id -> sale.order``. Untuk field pada parent yang
    menunjuk child, gunakan ``field_owner_is_parent=True``. Contoh utamanya
    ``sale.order.x_studio_io_1 -> approval.request``.
    """

    field_owner_model: str
    source_field: str
    related_model: str
    link_type: str
    cardinality: str = "many2one"
    confidence: str = "HIGH"
    field_owner_is_parent: bool = False


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        "sale.order",
        (
            "id", "name", "state", "company_id", "partner_id", "client_order_ref",
            "x_studio_tanggal_po_cust", "x_studio_io_1", "date_order",
            "commitment_date", "write_date",
        ),
    ),
    ModelSpec(
        "sale.order.line",
        (
            "id", "order_id", "product_id", "product_uom", "product_uom_qty",
            "qty_delivered", "qty_invoiced", "price_unit", "write_date", "company_id",
        ),
    ),
    ModelSpec(
        "approval.request",
        (
            "id", "name", "display_name", "request_status", "state", "category_id",
            "request_owner_id", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "approval.product.line",
        (
            "id", "approval_request_id", "product_id", "product_uom_id", "quantity",
            "x_studio_category", "x_studio_status", "x_studio_nomor_io",
            "x_studio_nomor_jo", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "mrp.production",
        (
            "id", "name", "state", "origin", "product_id", "product_uom_id",
            "product_qty", "qty_produced", "x_studio_nomor_io", "x_studio_nomor_jo",
            "x_studio_io_from_sales_order_1", "move_raw_ids", "move_finished_ids",
            "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "purchase.order",
        ("id", "name", "state", "company_id", "write_date"),
    ),
    ModelSpec(
        "purchase.order.line",
        (
            "id", "order_id", "state", "product_id", "product_uom", "product_qty",
            "qty_received", "qty_invoiced", "x_studio_many2one_field_iJ0j0",
            "x_studio_many2one_field_ij0j0", "x_studio_many2one_field_n6i7C",
            "x_studio_many2one_field_n6i7c", "x_studio_jo", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.picking",
        (
            "id", "name", "state", "sale_id", "backorder_id", "origin", "partner_id",
            "picking_type_id", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.move",
        (
            "id", "name", "state", "picking_id", "purchase_line_id", "sale_line_id",
            "raw_material_production_id", "production_id", "product_id", "product_uom",
            "product_uom_qty", "quantity", "location_id", "location_dest_id",
            "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.move",
        (
            "id", "name", "state", "move_type", "payment_state", "amount_total",
            "amount_residual", "invoice_origin", "purchase_id", "reversed_entry_id",
            "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.move.line",
        (
            "id", "move_id", "account_id", "partner_id", "product_id", "sale_line_ids",
            "x_studio_sales_order", "amount_residual", "reconciled", "matching_number",
            "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.partial.reconcile",
        (
            "id", "debit_move_id", "credit_move_id", "amount", "max_date",
            "company_id", "write_date",
        ),
    ),
)


LINK_SPECS: tuple[LinkSpec, ...] = (
    # Field berada pada SO, tetapi arah graph yang dibutuhkan adalah SO -> IO.
    LinkSpec("sale.order", "x_studio_io_1", "approval.request", "SO_TO_IO", "many2many", "HIGH", True),
    LinkSpec("sale.order.line", "order_id", "sale.order", "SO_TO_LINE"),
    LinkSpec("approval.product.line", "approval_request_id", "approval.request", "APPROVAL_TO_LINE"),
    LinkSpec("purchase.order.line", "order_id", "purchase.order", "PO_TO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_iJ0j0", "approval.request", "IO_TO_PO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_ij0j0", "approval.request", "IO_TO_PO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_n6i7C", "approval.request", "ROP_TO_PO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_n6i7c", "approval.request", "ROP_TO_PO_LINE"),
    # Custom fields berikut dapat berupa many2one pada Odoo. Bila ternyata char,
    # direct link dilewati dan exact-text secondary link tetap tersedia.
    LinkSpec("mrp.production", "x_studio_nomor_io", "approval.request", "IO_TO_MO_REFERENCE"),
    LinkSpec("mrp.production", "x_studio_nomor_jo", "sale.order", "SO_TO_MO_JO_REFERENCE"),
    LinkSpec("purchase.order.line", "x_studio_jo", "sale.order", "SO_TO_PO_LINE_JO_REFERENCE"),
    LinkSpec("account.move.line", "x_studio_sales_order", "sale.order", "SO_TO_ACCOUNT_LINE_REFERENCE"),
    LinkSpec("stock.picking", "sale_id", "sale.order", "SO_TO_DELIVERY"),
    LinkSpec("stock.picking", "backorder_id", "stock.picking", "PICKING_TO_BACKORDER"),
    LinkSpec("stock.move", "picking_id", "stock.picking", "PICKING_TO_MOVE"),
    LinkSpec("stock.move", "purchase_line_id", "purchase.order.line", "PO_LINE_TO_MOVE"),
    LinkSpec("stock.move", "sale_line_id", "sale.order.line", "SO_LINE_TO_MOVE"),
    LinkSpec("stock.move", "raw_material_production_id", "mrp.production", "MO_TO_COMPONENT_MOVE"),
    LinkSpec("stock.move", "production_id", "mrp.production", "MO_TO_FINISHED_MOVE"),
    LinkSpec("account.move", "purchase_id", "purchase.order", "PO_TO_VENDOR_BILL"),
    LinkSpec("account.move", "reversed_entry_id", "account.move", "MOVE_TO_REVERSAL"),
    LinkSpec("account.move.line", "move_id", "account.move", "MOVE_TO_LINE"),
    LinkSpec("account.move.line", "sale_line_ids", "sale.order.line", "SO_LINE_TO_ACCOUNT_LINE", "many2many"),
    LinkSpec("account.partial.reconcile", "debit_move_id", "account.move.line", "AML_TO_PARTIAL_RECONCILE_DEBIT"),
    LinkSpec("account.partial.reconcile", "credit_move_id", "account.move.line", "AML_TO_PARTIAL_RECONCILE_CREDIT"),
)


CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ct_extraction_run (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    company_id BIGINT,
    model_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS ct_native_record_snapshot (
    extraction_run_id UUID NOT NULL,
    model TEXT NOT NULL,
    record_id BIGINT NOT NULL,
    document_number TEXT,
    state TEXT,
    company_id BIGINT,
    company_name TEXT,
    write_date TIMESTAMP,
    payload JSONB NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (extraction_run_id, model, record_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_snapshot_run_model
    ON ct_native_record_snapshot (extraction_run_id, model);
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_company
    ON ct_native_record_snapshot (company_id, model);
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_payload
    ON ct_native_record_snapshot USING GIN (payload);

CREATE TABLE IF NOT EXISTS ct_document_link (
    extraction_run_id UUID NOT NULL,
    link_type TEXT NOT NULL,
    parent_model TEXT NOT NULL,
    parent_id BIGINT NOT NULL,
    parent_number TEXT,
    child_model TEXT NOT NULL,
    child_id BIGINT NOT NULL,
    child_number TEXT,
    source_field TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    extracted_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        extraction_run_id, link_type, parent_model, parent_id,
        child_model, child_id, source_field
    )
);

CREATE INDEX IF NOT EXISTS idx_ct_link_run_parent
    ON ct_document_link (extraction_run_id, parent_model, parent_id);
CREATE INDEX IF NOT EXISTS idx_ct_link_run_child
    ON ct_document_link (extraction_run_id, child_model, child_id);
"""


INSERT_SNAPSHOT_SQL = text("""
INSERT INTO ct_native_record_snapshot (
    extraction_run_id, model, record_id, document_number, state, company_id,
    company_name, write_date, payload, extracted_at
) VALUES (
    CAST(:run_id AS UUID), :model, :record_id, :document_number, :state,
    :company_id, :company_name, :write_date, CAST(:payload AS JSONB), :extracted_at
)
ON CONFLICT (extraction_run_id, model, record_id) DO UPDATE SET
    document_number = EXCLUDED.document_number,
    state = EXCLUDED.state,
    company_id = EXCLUDED.company_id,
    company_name = EXCLUDED.company_name,
    write_date = EXCLUDED.write_date,
    payload = EXCLUDED.payload,
    extracted_at = EXCLUDED.extracted_at
""")


INSERT_LINK_SQL = text("""
INSERT INTO ct_document_link (
    extraction_run_id, link_type, parent_model, parent_id, parent_number,
    child_model, child_id, child_number, source_field, confidence,
    evidence, extracted_at
) VALUES (
    CAST(:run_id AS UUID), :link_type, :parent_model, :parent_id, :parent_number,
    :child_model, :child_id, :child_number, :source_field, :confidence,
    CAST(:evidence AS JSONB), :extracted_at
)
ON CONFLICT (
    extraction_run_id, link_type, parent_model, parent_id,
    child_model, child_id, source_field
) DO UPDATE SET
    parent_number = EXCLUDED.parent_number,
    child_number = EXCLUDED.child_number,
    confidence = EXCLUDED.confidence,
    evidence = EXCLUDED.evidence,
    extracted_at = EXCLUDED.extracted_at
""")


def _relation_id(value: Any) -> Optional[int]:
    if isinstance(value, Mapping):
        raw_id = value.get("id")
        return int(raw_id) if isinstance(raw_id, int) or str(raw_id).isdigit() else None
    if isinstance(value, (list, tuple)) and value:
        raw_id = value[0]
        return int(raw_id) if isinstance(raw_id, int) or str(raw_id).isdigit() else None
    if isinstance(value, int):
        return value
    return None


def _relation_name(value: Any) -> Optional[str]:
    if isinstance(value, Mapping):
        raw_name = value.get("name") or value.get("display_name")
        return str(raw_name) if raw_name not in (None, False, "") else None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[1]) if value[1] not in (None, False, "") else None
    return None


def _relation_ids(value: Any, cardinality: str) -> list[int]:
    if cardinality == "many2many":
        if not isinstance(value, (list, tuple)):
            return []
        return [int(item) for item in value if isinstance(item, int) or str(item).isdigit()]
    relation_id = _relation_id(value)
    return [relation_id] if relation_id is not None else []


def normalize_value(value: Any, field_def: Mapping[str, Any]) -> Any:
    """Normalisasi field Odoo sambil mempertahankan native ID."""
    field_type = field_def.get("type")

    if value is False:
        return None
    if field_type == "many2one":
        relation_id = _relation_id(value)
        if relation_id is None:
            return None
        return {"id": relation_id, "name": _relation_name(value)}
    if field_type in {"many2many", "one2many"}:
        if not isinstance(value, (list, tuple)):
            return []
        return [int(item) for item in value if isinstance(item, int) or str(item).isdigit()]
    return value


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    for candidate in (value, value.replace("T", " ")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


class ControlTowerRelationExtractor:
    """Extract native IDs dan document links dari Odoo ke PostgreSQL."""

    def __init__(
        self,
        odoo_client: Optional[OdooClient] = None,
        postgres_client: Optional[PostgresClient] = None,
        company_id: int = 3,
        batch_size: int = 500,
    ) -> None:
        self.odoo = odoo_client or OdooClient()
        self.pg = postgres_client or PostgresClient()
        self.company_id = company_id
        self.batch_size = batch_size
        self.logger = get_logger("control_tower_relation_extractor")

    def ensure_schema(self) -> None:
        # psycopg accepts multiple DDL statements in one cursor execution.
        raw = self.pg.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute(CREATE_SCHEMA_SQL)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    def _available_fields(self, spec: ModelSpec) -> tuple[list[str], dict[str, dict]]:
        metadata = self.odoo.get_model_fields(spec.model)
        available = [field for field in spec.fields if field in metadata]
        if "id" not in available:
            raise RuntimeError(f"Model {spec.model} tidak mengekspos field id")
        return available, metadata

    def _domain(self, metadata: Mapping[str, Mapping[str, Any]]) -> list:
        return [("company_id", "=", self.company_id)] if "company_id" in metadata else []

    @staticmethod
    def _document_number(normalized: Mapping[str, Any], spec: ModelSpec) -> Optional[str]:
        for field in spec.number_fields:
            value = normalized.get(field)
            if value not in (None, False, ""):
                return str(value)
        return None

    def _normalize_record(
        self,
        spec: ModelSpec,
        record: Mapping[str, Any],
        metadata: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        normalized = {
            field: normalize_value(value, metadata.get(field, {}))
            for field, value in record.items()
        }
        company = normalized.get("company_id")
        return {
            "model": spec.model,
            "record_id": int(normalized["id"]),
            "document_number": self._document_number(normalized, spec),
            "state": normalized.get("state") or normalized.get("request_status") or normalized.get("x_studio_status"),
            "company_id": _relation_id(company),
            "company_name": _relation_name(company),
            "write_date": _parse_datetime(normalized.get("write_date")),
            "payload": normalized,
        }

    def _extract_model(self, spec: ModelSpec, run_id: str, extracted_at: datetime) -> list[dict[str, Any]]:
        available_fields, metadata = self._available_fields(spec)
        domain = self._domain(metadata)
        snapshots: list[dict[str, Any]] = []

        for batch in self.odoo.read_batched(
            spec.model,
            domain,
            fields=available_fields,
            batch_size=self.batch_size,
            order="id",
        ):
            rows = [self._normalize_record(spec, record, metadata) for record in batch]
            with self.pg.engine.begin() as conn:
                for row in rows:
                    conn.execute(
                        INSERT_SNAPSHOT_SQL,
                        {
                            "run_id": run_id,
                            **{key: row[key] for key in (
                                "model", "record_id", "document_number", "state",
                                "company_id", "company_name", "write_date",
                            )},
                            "payload": json.dumps(row["payload"], default=str),
                            "extracted_at": extracted_at,
                        },
                    )
            snapshots.extend(rows)

        return snapshots

    @staticmethod
    def _index_snapshots(snapshots: Iterable[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        return {(row["model"], row["record_id"]): row for row in snapshots}

    @staticmethod
    def _name_index(snapshots: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in snapshots:
            number = row.get("document_number")
            if number:
                index[(row["model"], str(number).strip())] = row
        return index

    def _iter_direct_links(
        self,
        snapshots: Iterable[dict[str, Any]],
        snapshot_index: Mapping[tuple[str, int], dict[str, Any]],
    ) -> Iterable[dict[str, Any]]:
        specs_by_owner: dict[str, list[LinkSpec]] = {}
        for spec in LINK_SPECS:
            specs_by_owner.setdefault(spec.field_owner_model, []).append(spec)

        for owner in snapshots:
            payload = owner["payload"]
            for spec in specs_by_owner.get(owner["model"], []):
                value = payload.get(spec.source_field)
                for related_id in _relation_ids(value, spec.cardinality):
                    related = snapshot_index.get((spec.related_model, related_id))

                    if spec.field_owner_is_parent:
                        parent, child = owner, related
                        parent_model, parent_id = owner["model"], owner["record_id"]
                        child_model, child_id = spec.related_model, related_id
                    else:
                        parent, child = related, owner
                        parent_model, parent_id = spec.related_model, related_id
                        child_model, child_id = owner["model"], owner["record_id"]

                    yield {
                        "link_type": spec.link_type,
                        "parent_model": parent_model,
                        "parent_id": parent_id,
                        "parent_number": parent.get("document_number") if parent else _relation_name(value),
                        "child_model": child_model,
                        "child_id": child_id,
                        "child_number": child.get("document_number") if child else None,
                        "source_field": spec.source_field,
                        "confidence": spec.confidence,
                        "evidence": {
                            "relation_kind": spec.cardinality,
                            "field_owner_model": owner["model"],
                            "field_owner_record_id": owner["record_id"],
                            "field_owner_is_parent": spec.field_owner_is_parent,
                        },
                    }

    def _iter_derived_links(
        self,
        snapshots: Iterable[dict[str, Any]],
        snapshot_index: Mapping[tuple[str, int], dict[str, Any]],
    ) -> Iterable[dict[str, Any]]:
        """Bangun relasi native turunan dari kombinasi beberapa foreign key."""
        for move in (row for row in snapshots if row["model"] == "stock.move"):
            payload = move["payload"]
            picking_id = _relation_id(payload.get("picking_id"))
            po_line_id = _relation_id(payload.get("purchase_line_id"))
            if picking_id and po_line_id:
                po_line = snapshot_index.get(("purchase.order.line", po_line_id))
                po_id = _relation_id(po_line["payload"].get("order_id")) if po_line else None
                picking = snapshot_index.get(("stock.picking", picking_id))
                po = snapshot_index.get(("purchase.order", po_id)) if po_id else None
                if po_id:
                    yield {
                        "link_type": "PO_TO_RECEIPT",
                        "parent_model": "purchase.order",
                        "parent_id": po_id,
                        "parent_number": po.get("document_number") if po else None,
                        "child_model": "stock.picking",
                        "child_id": picking_id,
                        "child_number": picking.get("document_number") if picking else None,
                        "source_field": "stock.move.purchase_line_id+picking_id",
                        "confidence": "HIGH",
                        "evidence": {"via_stock_move_id": move["record_id"], "native_relation": True},
                    }

        # SO -> Invoice dari native SO line -> account move line -> account move.
        for aml in (row for row in snapshots if row["model"] == "account.move.line"):
            move_id = _relation_id(aml["payload"].get("move_id"))
            if not move_id:
                continue
            account_move = snapshot_index.get(("account.move", move_id))
            for so_line_id in _relation_ids(aml["payload"].get("sale_line_ids"), "many2many"):
                so_line = snapshot_index.get(("sale.order.line", so_line_id))
                so_id = _relation_id(so_line["payload"].get("order_id")) if so_line else None
                so = snapshot_index.get(("sale.order", so_id)) if so_id else None
                if so_id:
                    yield {
                        "link_type": "SO_TO_INVOICE",
                        "parent_model": "sale.order",
                        "parent_id": so_id,
                        "parent_number": so.get("document_number") if so else None,
                        "child_model": "account.move",
                        "child_id": move_id,
                        "child_number": account_move.get("document_number") if account_move else None,
                        "source_field": "account.move.line.sale_line_ids+move_id",
                        "confidence": "HIGH",
                        "evidence": {"via_account_move_line_id": aml["record_id"], "native_relation": True},
                    }

    def _iter_inferred_links(
        self,
        snapshots: Iterable[dict[str, Any]],
        name_index: Mapping[tuple[str, str], dict[str, Any]],
    ) -> Iterable[dict[str, Any]]:
        """Relasi text-reference sekunder, selalu MEDIUM dan harus dapat direview."""
        for child in snapshots:
            payload = child["payload"]

            if child["model"] == "mrp.production":
                origin = str(payload.get("origin") or "").strip()
                parent = name_index.get(("sale.order", origin))
                if parent:
                    yield self._inferred_row(parent, child, "SO_TO_MO_ORIGIN", "origin")

                io_value = payload.get("x_studio_nomor_io")
                if isinstance(io_value, str) and io_value.strip():
                    parent = name_index.get(("approval.request", io_value.strip()))
                    if parent:
                        yield self._inferred_row(parent, child, "IO_TO_MO_REFERENCE", "x_studio_nomor_io")

                jo_value = payload.get("x_studio_nomor_jo")
                if isinstance(jo_value, str) and jo_value.strip():
                    parent = name_index.get(("sale.order", jo_value.strip()))
                    if parent:
                        yield self._inferred_row(parent, child, "SO_TO_MO_JO_REFERENCE", "x_studio_nomor_jo")

            if child["model"] == "purchase.order.line":
                jo_value = payload.get("x_studio_jo")
                if isinstance(jo_value, str) and jo_value.strip():
                    parent = name_index.get(("sale.order", jo_value.strip()))
                    if parent:
                        yield self._inferred_row(parent, child, "SO_TO_PO_LINE_JO_REFERENCE", "x_studio_jo")

            if child["model"] == "account.move":
                origin = str(payload.get("invoice_origin") or "").strip()
                parent = name_index.get(("purchase.order", origin))
                if parent:
                    yield self._inferred_row(parent, child, "PO_TO_VENDOR_BILL_ORIGIN", "invoice_origin")

            if child["model"] == "account.move.line":
                so_ref = str(payload.get("x_studio_sales_order") or "").strip()
                parent = name_index.get(("sale.order", so_ref))
                if parent:
                    yield self._inferred_row(parent, child, "SO_TO_ACCOUNT_LINE_REFERENCE", "x_studio_sales_order")

    @staticmethod
    def _inferred_row(
        parent: Mapping[str, Any],
        child: Mapping[str, Any],
        link_type: str,
        source_field: str,
    ) -> dict[str, Any]:
        return {
            "link_type": link_type,
            "parent_model": parent["model"],
            "parent_id": parent["record_id"],
            "parent_number": parent.get("document_number"),
            "child_model": child["model"],
            "child_id": child["record_id"],
            "child_number": child.get("document_number"),
            "source_field": source_field,
            "confidence": "MEDIUM",
            "evidence": {"relation_kind": "exact_text_reference", "requires_human_review": True},
        }

    def _insert_links(
        self,
        links: Iterable[dict[str, Any]],
        run_id: str,
        extracted_at: datetime,
    ) -> int:
        # Deduplicate karena satu PO/Receipt atau SO/Invoice dapat terhubung melalui
        # beberapa line/move. Evidence pertama tetap cukup untuk drill-through.
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in links:
            key = (
                row["link_type"], row["parent_model"], row["parent_id"],
                row["child_model"], row["child_id"], row["source_field"],
            )
            unique.setdefault(key, row)

        with self.pg.engine.begin() as conn:
            for row in unique.values():
                conn.execute(
                    INSERT_LINK_SQL,
                    {
                        "run_id": run_id,
                        **{key: row[key] for key in (
                            "link_type", "parent_model", "parent_id", "parent_number",
                            "child_model", "child_id", "child_number", "source_field", "confidence",
                        )},
                        "evidence": json.dumps(row["evidence"], default=str),
                        "extracted_at": extracted_at,
                    },
                )
        return len(unique)

    def run(self) -> dict[str, Any]:
        """Jalankan extraction lengkap dan publish hanya ketika run COMPLETED."""
        self.ensure_schema()
        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        model_counts: dict[str, int] = {}

        with self.pg.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ct_extraction_run (run_id, started_at, status, company_id)
                    VALUES (CAST(:run_id AS UUID), :started_at, 'RUNNING', :company_id)
                """),
                {"run_id": run_id, "started_at": started_at, "company_id": self.company_id},
            )

        try:
            all_snapshots: list[dict[str, Any]] = []
            for spec in MODEL_SPECS:
                rows = self._extract_model(spec, run_id, started_at)
                all_snapshots.extend(rows)
                model_counts[spec.model] = len(rows)
                self.logger.info("Control Tower model extracted", model=spec.model, rows=len(rows))

            snapshot_index = self._index_snapshots(all_snapshots)
            name_index = self._name_index(all_snapshots)
            links = [
                *self._iter_direct_links(all_snapshots, snapshot_index),
                *self._iter_derived_links(all_snapshots, snapshot_index),
                *self._iter_inferred_links(all_snapshots, name_index),
            ]
            link_count = self._insert_links(links, run_id, started_at)

            completed_at = datetime.now(timezone.utc)
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE ct_extraction_run
                        SET completed_at = :completed_at,
                            status = 'COMPLETED',
                            model_counts = CAST(:model_counts AS JSONB)
                        WHERE run_id = CAST(:run_id AS UUID)
                    """),
                    {
                        "completed_at": completed_at,
                        "model_counts": json.dumps({**model_counts, "document_links": link_count}),
                        "run_id": run_id,
                    },
                )

            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "company_id": self.company_id,
                "model_counts": model_counts,
                "document_links": link_count,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            with self.pg.engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE ct_extraction_run
                        SET completed_at = :completed_at,
                            status = 'FAILED',
                            model_counts = CAST(:model_counts AS JSONB),
                            error_message = :error_message
                        WHERE run_id = CAST(:run_id AS UUID)
                    """),
                    {
                        "completed_at": completed_at,
                        "model_counts": json.dumps(model_counts),
                        "error_message": str(exc),
                        "run_id": run_id,
                    },
                )
            raise

    def close(self) -> None:
        self.odoo.close()
        self.pg.close()
