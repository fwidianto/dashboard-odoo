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
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, Optional
from uuid import uuid4
from urllib.parse import urlsplit

from sqlalchemy import bindparam, text

from src.clients.odoo_client import OdooClient
from src.clients.postgres_client import PostgresClient
from src.control_tower.v03 import (
    SCOPE_YEAR,
    ensure_v03_schema,
    publish_pointer,
    rebuild_document_search,
    rebuild_finding_detections,
    rebuild_gross_profit,
    rebuild_line_lineage,
    reconcile_findings,
)
from src.utils.logging import get_logger


REFRESH_LOCK_KEY = 3202603
CONTRACT_VERSION = "control-tower-v0.3-odoo18-2026"
MATERIALIZED_VIEWS = (
    "mv_ct_document_paths",
    "mv_ct_rule_results",
    "mv_ct_sop_validation_summary",
    "mv_ct_exception_worklist",
)
RULES_BY_MODEL: dict[str, frozenset[str]] = {
    "sale.order": frozenset({"SO-PO-001", "SO-SOURCE-001", "SO-CANCEL-001", "SO-IO-MO-001"}),
    "sale.order.line": frozenset({"SO-SOURCE-001", "SO-IO-MO-001", "IO-UTIL-001"}),
    "approval.request": frozenset({"SO-SOURCE-001", "SO-IO-MO-001", "IO-PROD-001", "IO-UTIL-001"}),
    "approval.product.line": frozenset({"SO-SOURCE-001", "IO-PROD-001", "IO-UTIL-001"}),
    "mrp.production": frozenset({"SO-SOURCE-001", "SO-CANCEL-001", "SO-IO-MO-001", "IO-PROD-001"}),
    "purchase.order": frozenset({"SO-CANCEL-001", "PO-CANCEL-001", "PO-DRAFT-001"}),
    "purchase.order.line": frozenset({"SO-SOURCE-001", "PO-CANCEL-001", "PO-DRAFT-001"}),
    "stock.picking": frozenset({"SO-SOURCE-001", "SO-CANCEL-001", "PO-CANCEL-001", "PO-DRAFT-001"}),
    "stock.move": frozenset({"SO-SOURCE-001", "SO-CANCEL-001", "PO-CANCEL-001", "PO-DRAFT-001"}),
    "account.move": frozenset({"SO-CANCEL-001", "PO-DRAFT-001"}),
    "account.move.line": frozenset({"SO-CANCEL-001"}),
    "account.partial.reconcile": frozenset(),
}


class RefreshInProgress(RuntimeError):
    """Raised when another Control Tower refresh owns the PostgreSQL lock."""


class IncrementalRefreshError(RuntimeError):
    """Sanitized incremental-refresh failure safe for the API boundary."""


class DataContractError(RuntimeError):
    """Raised when a required, explicitly whitelisted Odoo field is unavailable."""


@dataclass(frozen=True)
class ModelSpec:
    model: str
    fields: tuple[str, ...]
    number_fields: tuple[str, ...] = ("name", "display_name")
    business_name: str = ""
    business_date_fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ("id", "write_date")
    company_scope: str = "auto"
    sync_strategy: str = "full_backfill_then_write_date"


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
            "commitment_date", "project_id", "currency_id", "currency_rate",
            "amount_untaxed", "order_line", "invoice_ids", "picking_ids",
            "mrp_production_ids", "procurement_group_id", "write_date",
        ),
        business_name="Sales Order",
        business_date_fields=("date_order",),
        required_fields=(
            "id", "name", "state", "company_id", "partner_id", "date_order",
            "currency_id", "amount_untaxed", "order_line", "write_date",
        ),
    ),
    ModelSpec(
        "sale.order.line",
        (
            "id", "order_id", "product_id", "name", "product_uom", "product_uom_qty",
            "qty_delivered", "qty_invoiced", "price_unit", "discount", "price_subtotal",
            "is_downpayment", "currency_id", "invoice_lines", "move_ids", "write_date",
            "company_id",
        ),
        business_name="Sales Order Line",
        required_fields=(
            "id", "order_id", "product_uom_qty", "price_unit", "price_subtotal",
            "is_downpayment", "invoice_lines", "move_ids", "write_date",
        ),
    ),
    ModelSpec(
        "approval.request",
        (
            "id", "name", "display_name", "request_status", "state", "category_id",
            "request_owner_id", "date", "date_confirmed", "date_start", "date_end",
            "product_line_ids", "amount", "x_currency_id", "x_studio_date_of_need",
            "x_studio_tanggal_kebutuhan", "x_studio_delivery_date",
            "x_studio_many2one_field_nbFpo", "x_studio_nomor_io", "x_studio_nomor_jo",
            "x_studio_many2many_field_0YSbP", "x_studio_many2one_field_cbw77",
            "x_studio_project", "x_studio_total_rkb_amount", "x_studio_receipt_location",
            "company_id", "write_date",
        ),
        business_name="RKB / Approval Procurement",
        business_date_fields=("date_confirmed",),
        required_fields=(
            "id", "name", "request_status", "category_id", "product_line_ids",
            "date_confirmed", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "approval.product.line",
        (
            "id", "approval_request_id", "product_id", "description", "product_uom_id",
            "quantity", "x_studio_quantity", "x_studio_category", "x_studio_status",
            "x_studio_nomor_io", "x_studio_nomor_io_1", "x_studio_nomor_jo",
            "x_studio_date_of_need", "x_studio_unit_price", "x_studio_subtotal",
            "x_studio_rkb_quantity", "x_studio_total_rop", "x_studio_po_quantity",
            "x_studio_stock", "x_studio_request_of_approval", "x_studio_project",
            "x_currency_id", "purchase_order_line_id", "company_id", "write_date",
        ),
        business_name="RKB / Approval Procurement Line",
        required_fields=(
            "id", "approval_request_id", "description", "quantity", "product_uom_id",
            "purchase_order_line_id", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "mrp.production",
        (
            "id", "name", "state", "origin", "product_id", "product_uom_id",
            "product_qty", "qty_produced", "x_studio_nomor_io", "x_studio_nomor_jo",
            "x_studio_io_from_sales_order_1", "sale_line_id", "procurement_group_id",
            "move_raw_ids", "move_finished_ids", "date_start", "date_finished",
            "company_id", "write_date",
        ),
        business_name="Manufacturing Order",
        business_date_fields=("date_start", "date_finished"),
        required_fields=(
            "id", "name", "state", "product_id", "product_uom_id", "product_qty",
            "move_raw_ids", "move_finished_ids", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "purchase.order",
        (
            "id", "name", "state", "partner_id", "date_order", "date_approve",
            "currency_id", "amount_untaxed", "order_line", "picking_ids", "invoice_ids",
            "company_id", "write_date",
        ),
        business_name="Purchase Order",
        business_date_fields=("date_order",),
        required_fields=(
            "id", "name", "state", "partner_id", "date_order", "currency_id",
            "order_line", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "purchase.order.line",
        (
            "id", "order_id", "state", "product_id", "name", "product_uom", "product_qty",
            "qty_received", "qty_invoiced", "price_unit", "price_subtotal", "currency_id",
            "invoice_lines", "move_ids", "x_studio_many2one_field_iJ0j0",
            "x_studio_many2one_field_n6i7C", "x_studio_jo", "x_studio_quantity_rop",
            "company_id", "write_date",
        ),
        business_name="Purchase Order Line",
        required_fields=(
            "id", "order_id", "product_qty", "price_unit", "price_subtotal",
            "invoice_lines", "move_ids", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.picking",
        (
            "id", "name", "state", "sale_id", "backorder_id", "origin", "partner_id",
            "picking_type_id", "purchase_id", "scheduled_date", "date_done", "location_id",
            "location_dest_id", "move_ids", "return_id", "company_id", "write_date",
        ),
        business_name="Receipt / Delivery",
        business_date_fields=("date_done", "scheduled_date"),
        required_fields=(
            "id", "name", "state", "picking_type_id", "location_id", "location_dest_id",
            "move_ids", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.move",
        (
            "id", "name", "state", "picking_id", "purchase_line_id", "sale_line_id",
            "origin_returned_move_id", "created_production_id", "raw_material_production_id",
            "production_id", "product_id", "product_uom", "product_uom_qty", "quantity",
            "location_id", "location_dest_id", "picking_type_id", "date", "move_line_ids",
            "stock_valuation_layer_ids", "account_move_ids", "company_id", "write_date",
        ),
        business_name="Stock Move",
        business_date_fields=("date",),
        required_fields=(
            "id", "state", "product_id", "product_uom", "product_uom_qty", "quantity",
            "location_id", "location_dest_id", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.move.line",
        (
            "id", "move_id", "picking_id", "product_id", "product_uom_id", "quantity",
            "location_id", "location_dest_id", "lot_id", "state", "date", "company_id",
            "write_date",
        ),
        number_fields=(),
        business_name="Stock Move Line",
        business_date_fields=("date",),
        required_fields=(
            "id", "move_id", "product_uom_id", "quantity", "location_id",
            "location_dest_id", "date", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.move",
        (
            "id", "name", "state", "move_type", "date", "invoice_date", "payment_state",
            "partner_id", "currency_id", "company_currency_id", "amount_untaxed",
            "amount_untaxed_signed", "amount_total", "amount_total_signed", "amount_residual",
            "invoice_origin", "purchase_id", "reversed_entry_id", "reversal_move_ids",
            "journal_id", "line_ids", "invoice_line_ids", "company_id", "write_date",
        ),
        business_name="Invoice / Vendor Bill / Journal Entry",
        business_date_fields=("invoice_date", "date"),
        required_fields=(
            "id", "state", "move_type", "date", "currency_id", "journal_id",
            "line_ids", "invoice_line_ids", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.move.line",
        (
            "id", "move_id", "account_id", "partner_id", "product_id", "name",
            "display_type", "parent_state", "quantity", "product_uom_id", "price_unit",
            "discount", "price_subtotal", "debit", "credit", "balance", "amount_currency",
            "currency_id", "sale_line_ids", "purchase_line_id", "cogs_origin_id",
            "stock_valuation_layer_ids", "x_studio_sales_order", "amount_residual",
            "reconciled", "matching_number", "company_id", "write_date",
        ),
        number_fields=(),
        business_name="Invoice / Journal Line",
        required_fields=(
            "id", "move_id", "account_id", "display_type", "parent_state", "quantity",
            "price_subtotal", "balance", "currency_id", "sale_line_ids", "purchase_line_id",
            "cogs_origin_id", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "stock.valuation.layer",
        (
            "id", "stock_move_id", "account_move_id", "account_move_line_id", "product_id",
            "quantity", "unit_cost", "value", "remaining_qty", "remaining_value",
            "company_id", "create_date", "write_date",
        ),
        number_fields=(),
        business_name="Stock Valuation Layer",
        business_date_fields=("create_date",),
        required_fields=(
            "id", "product_id", "quantity", "value", "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.payment",
        (
            "id", "name", "state", "date", "partner_id", "amount", "currency_id",
            "payment_type", "partner_type", "journal_id", "move_id", "reconciled_invoice_ids",
            "reconciled_bill_ids", "company_id", "write_date",
        ),
        business_name="Payment",
        business_date_fields=("date",),
        required_fields=(
            "id", "state", "date", "payment_type", "partner_type", "journal_id",
            "company_id", "write_date",
        ),
    ),
    ModelSpec(
        "account.partial.reconcile",
        (
            "id", "debit_move_id", "credit_move_id", "amount", "max_date",
            "company_id", "write_date",
        ),
        number_fields=(),
        business_name="Payment Reconciliation",
    ),
    ModelSpec(
        "product.product",
        (
            "id", "name", "display_name", "product_tmpl_id", "default_code", "barcode",
            "categ_id", "type", "is_storable", "uom_id", "uom_po_id", "company_id",
            "write_date",
        ),
        business_name="Product",
        required_fields=(
            "id", "name", "product_tmpl_id", "categ_id", "type", "uom_id", "uom_po_id",
            "write_date",
        ),
    ),
    ModelSpec(
        "product.template",
        (
            "id", "name", "type", "is_storable", "categ_id", "uom_id", "uom_po_id",
            "company_id", "write_date",
        ),
        business_name="Product Template",
        required_fields=("id", "name", "type", "categ_id", "uom_id", "uom_po_id", "write_date"),
    ),
    ModelSpec(
        "product.category",
        (
            "id", "name", "complete_name", "parent_id", "property_account_expense_categ_id",
            "property_account_income_categ_id", "write_date",
        ),
        business_name="Product Category",
        company_scope="global",
        required_fields=("id", "name", "write_date"),
    ),
    ModelSpec(
        "uom.uom",
        ("id", "name", "category_id", "factor", "factor_inv", "rounding", "uom_type", "active", "write_date"),
        business_name="Unit of Measure",
        company_scope="global",
        required_fields=(
            "id", "name", "category_id", "factor", "factor_inv", "rounding", "uom_type",
            "write_date",
        ),
    ),
    ModelSpec(
        "uom.category",
        ("id", "name", "write_date"),
        business_name="Unit of Measure Category",
        company_scope="global",
    ),
    ModelSpec(
        "res.currency",
        ("id", "name", "symbol", "rounding", "decimal_places", "active", "write_date"),
        business_name="Currency",
        company_scope="global",
    ),
    ModelSpec(
        "res.currency.rate",
        (
            "id", "name", "rate", "company_rate", "inverse_company_rate", "currency_id",
            "company_id", "write_date",
        ),
        number_fields=(),
        business_name="Exchange Rate",
        business_date_fields=("name",),
        required_fields=("id", "name", "rate", "currency_id", "write_date"),
    ),
    ModelSpec(
        "res.company",
        ("id", "name", "currency_id", "partner_id", "write_date"),
        business_name="Company",
        company_scope="self",
    ),
    ModelSpec(
        "res.partner",
        ("id", "name", "display_name", "commercial_company_name", "company_id", "write_date"),
        business_name="Customer / Vendor",
    ),
    ModelSpec(
        "account.account",
        ("id", "code", "name", "account_type", "deprecated", "company_ids", "write_date"),
        business_name="Account",
        company_scope="many",
        required_fields=("id", "code", "name", "account_type", "company_ids", "write_date"),
    ),
    ModelSpec(
        "account.journal",
        ("id", "name", "code", "type", "company_id", "currency_id", "active", "write_date"),
        business_name="Journal",
        required_fields=("id", "name", "code", "type", "company_id", "write_date"),
    ),
    ModelSpec(
        "stock.picking.type",
        (
            "id", "name", "display_name", "code", "sequence_code", "warehouse_id",
            "default_location_src_id", "default_location_dest_id", "company_id", "active",
            "write_date",
        ),
        business_name="Operation Type",
        required_fields=("id", "name", "code", "company_id", "write_date"),
    ),
    ModelSpec(
        "stock.location",
        ("id", "name", "complete_name", "usage", "location_id", "company_id", "active", "write_date"),
        business_name="Stock Location",
        required_fields=("id", "name", "usage", "write_date"),
    ),
)


LINK_SPECS: tuple[LinkSpec, ...] = (
    # Field berada pada SO, tetapi arah graph yang dibutuhkan adalah SO -> IO.
    LinkSpec("sale.order", "x_studio_io_1", "approval.request", "SO_TO_IO", "many2many", "HIGH", True),
    LinkSpec("sale.order.line", "order_id", "sale.order", "SO_TO_LINE"),
    LinkSpec("approval.product.line", "approval_request_id", "approval.request", "APPROVAL_TO_LINE"),
    LinkSpec("purchase.order.line", "order_id", "purchase.order", "PO_TO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_iJ0j0", "approval.request", "IO_TO_PO_LINE"),
    LinkSpec("purchase.order.line", "x_studio_many2one_field_n6i7C", "approval.request", "ROP_TO_PO_LINE"),
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
    LinkSpec("stock.move", "origin_returned_move_id", "stock.move", "MOVE_TO_RETURN"),
    LinkSpec("stock.move", "created_production_id", "mrp.production", "MOVE_TO_CREATED_MO", field_owner_is_parent=True),
    LinkSpec("stock.move", "raw_material_production_id", "mrp.production", "MO_TO_COMPONENT_MOVE"),
    LinkSpec("stock.move", "production_id", "mrp.production", "MO_TO_FINISHED_MOVE"),
    LinkSpec("stock.move.line", "move_id", "stock.move", "MOVE_TO_DETAIL_LINE"),
    LinkSpec("mrp.production", "sale_line_id", "sale.order.line", "SO_LINE_TO_MO"),
    LinkSpec("approval.product.line", "x_studio_nomor_io", "approval.request", "IO_TO_APPROVAL_LINE"),
    LinkSpec("approval.product.line", "x_studio_nomor_jo", "sale.order", "SO_TO_APPROVAL_LINE"),
    LinkSpec("approval.product.line", "purchase_order_line_id", "purchase.order.line", "PO_LINE_TO_APPROVAL_LINE", field_owner_is_parent=True),
    LinkSpec("stock.valuation.layer", "stock_move_id", "stock.move", "MOVE_TO_VALUATION"),
    LinkSpec("stock.valuation.layer", "account_move_id", "account.move", "JOURNAL_TO_VALUATION"),
    LinkSpec("stock.valuation.layer", "account_move_line_id", "account.move.line", "ACCOUNT_LINE_TO_VALUATION"),
    LinkSpec("account.move", "purchase_id", "purchase.order", "PO_TO_VENDOR_BILL"),
    LinkSpec("account.move", "reversed_entry_id", "account.move", "MOVE_TO_REVERSAL"),
    LinkSpec("account.move.line", "move_id", "account.move", "MOVE_TO_LINE"),
    LinkSpec("account.move.line", "sale_line_ids", "sale.order.line", "SO_LINE_TO_ACCOUNT_LINE", "many2many"),
    LinkSpec("account.move.line", "purchase_line_id", "purchase.order.line", "PO_LINE_TO_ACCOUNT_LINE"),
    LinkSpec("account.move.line", "cogs_origin_id", "account.move.line", "INVOICE_LINE_TO_COGS_LINE"),
    LinkSpec("account.payment", "move_id", "account.move", "JOURNAL_TO_PAYMENT"),
    LinkSpec("account.payment", "reconciled_invoice_ids", "account.move", "INVOICE_TO_PAYMENT", "many2many"),
    LinkSpec("account.payment", "reconciled_bill_ids", "account.move", "BILL_TO_PAYMENT", "many2many"),
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
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_incremental
    ON ct_native_record_snapshot (company_id, model, write_date DESC, record_id);
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_payload
    ON ct_native_record_snapshot USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_so_business_date
    ON ct_native_record_snapshot (extraction_run_id, ((payload ->> 'date_order')), record_id)
    WHERE model = 'sale.order';
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_po_business_date
    ON ct_native_record_snapshot (extraction_run_id, ((payload ->> 'date_order')), record_id)
    WHERE model = 'purchase.order';
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_account_business_date
    ON ct_native_record_snapshot (
        extraction_run_id,
        (COALESCE(payload ->> 'invoice_date', payload ->> 'date')),
        record_id
    ) WHERE model = 'account.move';
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_approval_business_date
    ON ct_native_record_snapshot (extraction_run_id, ((payload ->> 'date_confirmed')), record_id)
    WHERE model = 'approval.request';
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_aml_move
    ON ct_native_record_snapshot (
        extraction_run_id,
        ((NULLIF(payload #>> '{move_id,id}', '')::bigint)),
        record_id
    ) WHERE model = 'account.move.line';
CREATE INDEX IF NOT EXISTS idx_ct_snapshot_aml_cogs
    ON ct_native_record_snapshot (
        extraction_run_id,
        ((NULLIF(payload #>> '{account_id,id}', '')::bigint)),
        ((NULLIF(payload #>> '{cogs_origin_id,id}', '')::bigint)),
        record_id
    ) WHERE model = 'account.move.line'
      AND payload #>> '{cogs_origin_id,id}' IS NOT NULL;

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
    owner_model TEXT,
    owner_record_id BIGINT,
    extracted_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        extraction_run_id, link_type, parent_model, parent_id,
        child_model, child_id, source_field
    )
);

ALTER TABLE ct_document_link
    ADD COLUMN IF NOT EXISTS owner_model TEXT;
ALTER TABLE ct_document_link
    ADD COLUMN IF NOT EXISTS owner_record_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_ct_link_run_parent
    ON ct_document_link (extraction_run_id, parent_model, parent_id);
CREATE INDEX IF NOT EXISTS idx_ct_link_run_child
    ON ct_document_link (extraction_run_id, child_model, child_id);
CREATE INDEX IF NOT EXISTS idx_ct_link_run_owner
    ON ct_document_link (extraction_run_id, owner_model, owner_record_id)
    WHERE owner_model IS NOT NULL AND owner_record_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ct_link_run_source_owner
    ON ct_document_link (extraction_run_id, source_field, owner_model, owner_record_id);

CREATE TABLE IF NOT EXISTS ct_data_contract_field (
    contract_version TEXT NOT NULL,
    model TEXT NOT NULL,
    model_business_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_business_name TEXT,
    actual_type TEXT,
    required BOOLEAN NOT NULL,
    available BOOLEAN NOT NULL,
    relationship_target TEXT,
    is_business_date BOOLEAN NOT NULL DEFAULT FALSE,
    is_write_watermark BOOLEAN NOT NULL DEFAULT FALSE,
    sync_strategy TEXT NOT NULL,
    destination TEXT NOT NULL DEFAULT 'ct_native_record_snapshot.payload',
    validation_error TEXT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (contract_version, model, field_name)
);

CREATE INDEX IF NOT EXISTS idx_ct_contract_failures
    ON ct_data_contract_field (contract_version, model, required, available);

CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment_execution (
    execution_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    company_id BIGINT NOT NULL,
    expected_count BIGINT NOT NULL,
    returned_count BIGINT,
    null_date_order_count BIGINT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT
);

CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment (
    run_id UUID NOT NULL,
    purchase_order_id BIGINT NOT NULL,
    company_id BIGINT NOT NULL,
    source_state TEXT NOT NULL,
    date_order TIMESTAMP WITHOUT TIME ZONE,
    source_write_date TIMESTAMP WITHOUT TIME ZONE,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enrichment_status TEXT NOT NULL CHECK (enrichment_status = 'COMPLETED'),
    enrichment_execution_id UUID NOT NULL
        REFERENCES ct_purchase_order_date_enrichment_execution (execution_id),
    PRIMARY KEY (run_id, purchase_order_id)
);
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
    evidence, owner_model, owner_record_id, extracted_at
) VALUES (
    CAST(:run_id AS UUID), :link_type, :parent_model, :parent_id, :parent_number,
    :child_model, :child_id, :child_number, :source_field, :confidence,
    CAST(:evidence AS JSONB), :owner_model, :owner_record_id, :extracted_at
)
ON CONFLICT (
    extraction_run_id, link_type, parent_model, parent_id,
    child_model, child_id, source_field
) DO UPDATE SET
    parent_number = EXCLUDED.parent_number,
    child_number = EXCLUDED.child_number,
    confidence = EXCLUDED.confidence,
    evidence = EXCLUDED.evidence,
    owner_model = EXCLUDED.owner_model,
    owner_record_id = EXCLUDED.owner_record_id,
    extracted_at = EXCLUDED.extracted_at
""")


UPSERT_STAGED_SNAPSHOT_SQL = text("""
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
WHERE ct_native_record_snapshot.document_number IS DISTINCT FROM EXCLUDED.document_number
   OR ct_native_record_snapshot.state IS DISTINCT FROM EXCLUDED.state
   OR ct_native_record_snapshot.company_id IS DISTINCT FROM EXCLUDED.company_id
   OR ct_native_record_snapshot.company_name IS DISTINCT FROM EXCLUDED.company_name
   OR ct_native_record_snapshot.write_date IS DISTINCT FROM EXCLUDED.write_date
   OR ct_native_record_snapshot.payload IS DISTINCT FROM EXCLUDED.payload
RETURNING record_id
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
        progress_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self.odoo = odoo_client or OdooClient()
        self.pg = postgres_client or PostgresClient()
        self.company_id = company_id
        self.batch_size = batch_size
        self.progress_callback = progress_callback
        self.logger = get_logger("control_tower_relation_extractor")
        self._metadata_cache: dict[str, dict[str, dict]] = {}

    def _progress(
        self,
        phase: str,
        message: str,
        changed_documents: int = 0,
        recalculated_checks: int = 0,
        phase_label: Optional[str] = None,
        current_work: Optional[str] = None,
        completed_work_units: Optional[int] = None,
        total_work_units: Optional[int] = None,
        processed_records: Optional[int] = None,
        total_records: Optional[int] = None,
    ) -> None:
        if self.progress_callback:
            self.progress_callback(
                phase,
                message,
                changed_documents,
                recalculated_checks,
                phase_label,
                current_work,
                completed_work_units,
                total_work_units,
                processed_records,
                total_records,
            )

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
        with self.pg.engine.begin() as conn:
            ensure_v03_schema(conn)

    def _available_fields(self, spec: ModelSpec) -> tuple[list[str], dict[str, dict]]:
        metadata_cache = getattr(self, "_metadata_cache", {})
        metadata = metadata_cache.get(spec.model)
        if metadata is None:
            metadata = self.odoo.get_model_fields(spec.model)
            metadata_cache[spec.model] = metadata
            self._metadata_cache = metadata_cache
        available = [field for field in spec.fields if field in metadata]
        if "id" not in available:
            raise RuntimeError(f"Model {spec.model} tidak mengekspos field id")
        return available, metadata

    def audit_data_contract(self) -> dict[str, Any]:
        """Validate and persist the explicit whitelist without reading business records."""
        rows: list[dict[str, Any]] = []
        failures: list[str] = []
        verified_at = datetime.now(timezone.utc)
        for spec in MODEL_SPECS:
            metadata = self.odoo.get_model_fields(spec.model)
            self._metadata_cache[spec.model] = metadata
            for field in spec.fields:
                field_def = metadata.get(field) or {}
                required = field in spec.required_fields
                available = field in metadata
                if required and not available:
                    failures.append(f"{spec.model}.{field}")
                rows.append(
                    {
                        "contract_version": CONTRACT_VERSION,
                        "model": spec.model,
                        "model_business_name": spec.business_name or spec.model,
                        "field_name": field,
                        "field_business_name": field_def.get("string"),
                        "actual_type": field_def.get("type"),
                        "required": required,
                        "available": available,
                        "relationship_target": field_def.get("relation"),
                        "is_business_date": field in spec.business_date_fields,
                        "is_write_watermark": field == "write_date",
                        "sync_strategy": spec.sync_strategy,
                        "validation_error": "required field unavailable" if required and not available else None,
                        "verified_at": verified_at,
                    }
                )
        with self.pg.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ct_data_contract_field (
                        contract_version, model, model_business_name, field_name,
                        field_business_name, actual_type, required, available,
                        relationship_target, is_business_date, is_write_watermark,
                        sync_strategy, validation_error, verified_at
                    ) VALUES (
                        :contract_version, :model, :model_business_name, :field_name,
                        :field_business_name, :actual_type, :required, :available,
                        :relationship_target, :is_business_date, :is_write_watermark,
                        :sync_strategy, :validation_error, :verified_at
                    )
                    ON CONFLICT (contract_version, model, field_name) DO UPDATE SET
                        model_business_name = EXCLUDED.model_business_name,
                        field_business_name = EXCLUDED.field_business_name,
                        actual_type = EXCLUDED.actual_type,
                        required = EXCLUDED.required,
                        available = EXCLUDED.available,
                        relationship_target = EXCLUDED.relationship_target,
                        is_business_date = EXCLUDED.is_business_date,
                        is_write_watermark = EXCLUDED.is_write_watermark,
                        sync_strategy = EXCLUDED.sync_strategy,
                        validation_error = EXCLUDED.validation_error,
                        verified_at = EXCLUDED.verified_at
                """),
                rows,
            )
        if failures:
            raise DataContractError(
                "Field wajib Odoo tidak tersedia: " + ", ".join(sorted(failures))
            )
        return {
            "contract_version": CONTRACT_VERSION,
            "models": len(MODEL_SPECS),
            "fields": len(rows),
            "failures": [],
            "verified_at": verified_at.isoformat(),
        }

    def _domain(
        self,
        metadata: Mapping[str, Mapping[str, Any]],
        spec: Optional[ModelSpec] = None,
    ) -> list:
        scope = spec.company_scope if spec else "auto"
        if scope == "global":
            return []
        if scope == "self":
            return [("id", "=", self.company_id)]
        if scope == "many" and "company_ids" in metadata:
            return [("company_ids", "in", [self.company_id])]
        if "company_id" not in metadata:
            return []
        if metadata["company_id"].get("required"):
            return [("company_id", "=", self.company_id)]
        return ["|", ("company_id", "=", False), ("company_id", "=", self.company_id)]

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
        domain = self._domain(metadata, spec)
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
                conn.execute(
                    INSERT_SNAPSHOT_SQL,
                    [
                        {
                            "run_id": run_id,
                            **{key: row[key] for key in (
                                "model", "record_id", "document_number", "state",
                                "company_id", "company_name", "write_date",
                            )},
                            "payload": json.dumps(row["payload"], default=str),
                            "extracted_at": extracted_at,
                        }
                        for row in rows
                    ],
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

    @staticmethod
    def _link_owner(row: Mapping[str, Any]) -> tuple[Optional[str], Optional[int]]:
        """Return the record whose fields produced a link.

        Normalizing this identity keeps selective refreshes on indexed columns;
        the JSON evidence remains available for audit and display.
        """
        evidence = row.get("evidence") or {}
        if evidence.get("field_owner_model") and evidence.get("field_owner_record_id") is not None:
            return str(evidence["field_owner_model"]), int(evidence["field_owner_record_id"])
        if evidence.get("via_stock_move_id") is not None:
            return "stock.move", int(evidence["via_stock_move_id"])
        if evidence.get("via_account_move_line_id") is not None:
            return "account.move.line", int(evidence["via_account_move_line_id"])
        if evidence.get("relation_kind") == "exact_text_reference":
            return str(row["child_model"]), int(row["child_id"])
        return None, None

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
            pending: list[dict[str, Any]] = []
            for row in unique.values():
                owner_model, owner_record_id = self._link_owner(row)
                pending.append(
                    {
                        "run_id": run_id,
                        **{key: row[key] for key in (
                            "link_type", "parent_model", "parent_id", "parent_number",
                            "child_model", "child_id", "child_number", "source_field", "confidence",
                        )},
                        "evidence": json.dumps(row["evidence"], default=str),
                        "owner_model": owner_model,
                        "owner_record_id": owner_record_id,
                        "extracted_at": extracted_at,
                    }
                )
                if len(pending) >= self.batch_size:
                    conn.execute(INSERT_LINK_SQL, pending)
                    pending.clear()
            if pending:
                conn.execute(INSERT_LINK_SQL, pending)
        return len(unique)

    def _current_completed_run(self) -> dict[str, Any]:
        with self.pg.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT run_id::text AS run_id, started_at, completed_at, model_counts
                    FROM ct_extraction_run
                    WHERE status = 'COMPLETED' AND company_id = :company_id
                    ORDER BY completed_at DESC
                    LIMIT 1
                """),
                {"company_id": self.company_id},
            ).mappings().one_or_none()
        if row is None:
            raise IncrementalRefreshError(
                "Snapshot lengkap belum tersedia; jalankan ekstraksi awal sebelum refresh incremental."
            )

        result = dict(row)
        refresh_meta = (result.get("model_counts") or {}).get("_refresh", {})
        raw_watermark = refresh_meta.get("source_watermark")
        if raw_watermark:
            watermark = datetime.fromisoformat(str(raw_watermark).replace("Z", "+00:00"))
        else:
            watermark = result["started_at"]
        if watermark.tzinfo is None:
            watermark = watermark.replace(tzinfo=timezone.utc)
        result["source_watermark"] = watermark.astimezone(timezone.utc)
        result["source_fingerprint"] = refresh_meta.get("source_fingerprint")
        return result

    def _source_fingerprint(self) -> str:
        parsed = urlsplit(self.odoo.url)
        safe_origin = f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}"
        if parsed.port:
            safe_origin += f":{parsed.port}"
        safe_origin += parsed.path.rstrip("/")
        return hashlib.sha256(f"{safe_origin}|{self.odoo.db}".encode("utf-8")).hexdigest()

    def _verify_source_compatibility(self, base: Mapping[str, Any]) -> tuple[str, str]:
        """Bind a legacy snapshot to its Odoo source without persisting source details."""
        fingerprint = self._source_fingerprint()
        stored = base.get("source_fingerprint")
        if stored:
            if stored != fingerprint:
                raise IncrementalRefreshError(
                    "Sumber Odoo tidak sama dengan sumber snapshot terakhir yang berhasil."
                )
            return fingerprint, "stored_fingerprint"

        root_models = (
            "sale.order",
            "approval.request",
            "mrp.production",
            "purchase.order",
            "stock.picking",
            "account.move",
        )
        with self.pg.engine.connect() as conn:
            anchors = conn.execute(
                text("""
                    WITH ranked AS (
                        SELECT
                            model, record_id, document_number,
                            ROW_NUMBER() OVER (PARTITION BY model ORDER BY record_id DESC) AS rank
                        FROM ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                          AND model IN :root_models
                          AND document_number IS NOT NULL
                    )
                    SELECT model, record_id, document_number
                    FROM ranked
                    WHERE rank <= 2
                    ORDER BY model, record_id
                """).bindparams(bindparam("root_models", expanding=True)),
                {"run_id": base["run_id"], "root_models": root_models},
            ).mappings().all()
        if len(anchors) < 6 or len({row["model"] for row in anchors}) < 3:
            raise IncrementalRefreshError(
                "Snapshot lama tidak memiliki anchor yang cukup untuk memverifikasi sumber Odoo."
            )

        specs = {spec.model: spec for spec in MODEL_SPECS}
        matches = 0
        matched_models: set[str] = set()
        for model in sorted({row["model"] for row in anchors}):
            model_anchors = [row for row in anchors if row["model"] == model]
            spec = specs[model]
            fields = ["id", *spec.number_fields]
            source_rows = self.odoo.search_read(
                model,
                [("id", "in", [int(row["record_id"]) for row in model_anchors])],
                fields=list(dict.fromkeys(fields)),
                limit=len(model_anchors),
                order="id",
            )
            source_numbers = {
                int(row["id"]): next(
                    (str(row.get(field)) for field in spec.number_fields if row.get(field)),
                    None,
                )
                for row in source_rows
            }
            model_matches = sum(
                1
                for anchor in model_anchors
                if source_numbers.get(int(anchor["record_id"])) == str(anchor["document_number"])
            )
            matches += model_matches
            if model_matches:
                matched_models.add(model)

        if matches / len(anchors) < 0.75 or len(matched_models) < 3:
            raise IncrementalRefreshError(
                "Anchor snapshot tidak cocok dengan sumber Odoo yang dikonfigurasi."
            )
        return fingerprint, "legacy_anchor_match"

    def _start_incremental_run(
        self,
        run_id: str,
        base_run_id: str,
        started_at: datetime,
    ) -> None:
        with self.pg.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ct_extraction_run (
                        run_id, started_at, status, company_id, model_counts
                    ) VALUES (
                        CAST(:run_id AS UUID), :started_at, 'RUNNING', :company_id,
                        CAST(:model_counts AS JSONB)
                    )
                """),
                {
                    "run_id": run_id,
                    "started_at": started_at,
                    "company_id": self.company_id,
                    "model_counts": json.dumps(
                        {"_refresh": {"sync_mode": "incremental", "base_run_id": base_run_id}}
                    ),
                },
            )
            conn.execute(
                text("""
                    INSERT INTO ct_native_record_snapshot (
                        extraction_run_id, model, record_id, document_number, state,
                        company_id, company_name, write_date, payload, extracted_at
                    )
                    SELECT
                        CAST(:run_id AS UUID), model, record_id, document_number, state,
                        company_id, company_name, write_date, payload, extracted_at
                    FROM ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:base_run_id AS UUID)
                """),
                {"run_id": run_id, "base_run_id": base_run_id},
            )

    def _extract_model_incremental(
        self,
        spec: ModelSpec,
        run_id: str,
        extracted_at: datetime,
        watermark: datetime,
    ) -> list[int]:
        available_fields, metadata = self._available_fields(spec)
        if "write_date" not in metadata:
            raise IncrementalRefreshError(
                f"Model {spec.model} tidak menyediakan write_date untuk refresh incremental."
            )
        domain = [
            *self._domain(metadata, spec),
            ("write_date", ">=", watermark.strftime("%Y-%m-%d %H:%M:%S")),
        ]
        changed_ids: list[int] = []
        for batch in self.odoo.read_batched(
            spec.model,
            domain,
            fields=available_fields,
            batch_size=self.batch_size,
            order="write_date,id",
        ):
            rows = [self._normalize_record(spec, record, metadata) for record in batch]
            with self.pg.engine.begin() as conn:
                for row in rows:
                    result = conn.execute(
                        UPSERT_STAGED_SNAPSHOT_SQL,
                        {
                            "run_id": run_id,
                            **{
                                key: row[key]
                                for key in (
                                    "model",
                                    "record_id",
                                    "document_number",
                                    "state",
                                    "company_id",
                                    "company_name",
                                    "write_date",
                                )
                            },
                            "payload": json.dumps(row["payload"], default=str),
                            "extracted_at": extracted_at,
                        },
                    )
                    updated_id = result.scalar_one_or_none()
                    if updated_id is not None:
                        changed_ids.append(int(updated_id))
        return changed_ids

    def _copy_links(self, run_id: str, base_run_id: str) -> int:
        with self.pg.engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO ct_document_link (
                        extraction_run_id, link_type, parent_model, parent_id, parent_number,
                        child_model, child_id, child_number, source_field, confidence,
                        evidence, owner_model, owner_record_id, extracted_at
                    )
                    SELECT
                        CAST(:run_id AS UUID), link_type, parent_model, parent_id, parent_number,
                        child_model, child_id, child_number, source_field, confidence,
                        evidence,
                        COALESCE(
                            owner_model,
                            CASE
                                WHEN evidence ? 'field_owner_model'
                                    THEN evidence ->> 'field_owner_model'
                                WHEN evidence ? 'via_stock_move_id' THEN 'stock.move'
                                WHEN evidence ? 'via_account_move_line_id' THEN 'account.move.line'
                                WHEN evidence ->> 'relation_kind' = 'exact_text_reference'
                                    THEN child_model
                            END
                        ),
                        COALESCE(
                            owner_record_id,
                            CASE
                                WHEN evidence ? 'field_owner_record_id'
                                    THEN NULLIF(evidence ->> 'field_owner_record_id', '')::bigint
                                WHEN evidence ? 'via_stock_move_id'
                                    THEN NULLIF(evidence ->> 'via_stock_move_id', '')::bigint
                                WHEN evidence ? 'via_account_move_line_id'
                                    THEN NULLIF(evidence ->> 'via_account_move_line_id', '')::bigint
                                WHEN evidence ->> 'relation_kind' = 'exact_text_reference'
                                    THEN child_id
                            END
                        ),
                        extracted_at
                    FROM ct_document_link
                    WHERE extraction_run_id = CAST(:base_run_id AS UUID)
                """),
                {"run_id": run_id, "base_run_id": base_run_id},
            )
        return max(result.rowcount or 0, 0)

    def _snapshot_rows_for_keys(
        self,
        run_id: str,
        keys: Iterable[tuple[str, int]],
    ) -> list[dict[str, Any]]:
        serialized = [
            {"model": model, "record_id": record_id}
            for model, record_id in sorted(set(keys))
        ]
        if not serialized:
            return []
        with self.pg.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT model, record_id, document_number, state, company_id,
                           company_name, write_date, payload
                    FROM ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND (model, record_id) IN (
                          SELECT item ->> 'model', (item ->> 'record_id')::bigint
                          FROM JSONB_ARRAY_ELEMENTS(CAST(:keys AS JSONB)) item
                      )
                """),
                {"run_id": run_id, "keys": json.dumps(serialized)},
            ).mappings().all()
        return [dict(row) for row in rows]

    def _dependent_owner_keys(
        self,
        run_id: str,
        base_run_id: str,
        changed_records: Mapping[str, list[int]],
    ) -> set[tuple[str, int]]:
        changed_keys = {
            (model, record_id)
            for model, record_ids in changed_records.items()
            for record_id in record_ids
        }
        owners = set(changed_keys)
        with self.pg.engine.connect() as conn:
            purchase_line_ids = changed_records.get("purchase.order.line", [])
            if purchase_line_ids:
                rows = conn.execute(
                    text("""
                        SELECT record_id
                        FROM ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                          AND model = 'stock.move'
                          AND payload #>> '{purchase_line_id,id}' IN :ids
                    """).bindparams(bindparam("ids", expanding=True)),
                    {"run_id": run_id, "ids": tuple(map(str, purchase_line_ids))},
                ).scalars().all()
                owners.update(("stock.move", int(record_id)) for record_id in rows)

            sale_line_ids = changed_records.get("sale.order.line", [])
            if sale_line_ids:
                rows = conn.execute(
                    text("""
                        SELECT record_id
                        FROM ct_native_record_snapshot snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                          AND model = 'account.move.line'
                          AND EXISTS (
                              SELECT 1
                              FROM JSONB_ARRAY_ELEMENTS_TEXT(
                                  COALESCE(snapshot.payload -> 'sale_line_ids', '[]'::jsonb)
                              ) AS element(value)
                              WHERE element.value IN :ids
                          )
                    """).bindparams(bindparam("ids", expanding=True)),
                    {"run_id": run_id, "ids": tuple(map(str, sale_line_ids))},
                ).scalars().all()
                owners.update(("account.move.line", int(record_id)) for record_id in rows)

        base_rows = self._snapshot_rows_for_keys(base_run_id, changed_keys)
        current_rows = self._snapshot_rows_for_keys(run_id, changed_keys)
        base_numbers = {
            (row["model"], row["record_id"]): row.get("document_number") for row in base_rows
        }
        changed_names: dict[str, set[str]] = {}
        for row in current_rows:
            key = (row["model"], row["record_id"])
            before = base_numbers.get(key)
            after = row.get("document_number")
            if before != after:
                changed_names.setdefault(row["model"], set()).update(
                    str(value) for value in (before, after) if value
                )

        inferred_dependents = {
            "sale.order": (
                ("mrp.production", "origin"),
                ("mrp.production", "x_studio_nomor_jo"),
                ("purchase.order.line", "x_studio_jo"),
                ("account.move.line", "x_studio_sales_order"),
            ),
            "approval.request": (("mrp.production", "x_studio_nomor_io"),),
            "purchase.order": (("account.move", "invoice_origin"),),
        }
        with self.pg.engine.connect() as conn:
            for parent_model, names in changed_names.items():
                for child_model, field in inferred_dependents.get(parent_model, ()):
                    rows = conn.execute(
                        text(f"""
                            SELECT record_id
                            FROM ct_native_record_snapshot
                            WHERE extraction_run_id = CAST(:run_id AS UUID)
                              AND model = :child_model
                              AND payload ->> '{field}' IN :names
                        """).bindparams(bindparam("names", expanding=True)),
                        {"run_id": run_id, "child_model": child_model, "names": tuple(names)},
                    ).scalars().all()
                    owners.update((child_model, int(record_id)) for record_id in rows)
        return owners

    def _dependency_keys_for_owners(
        self,
        run_id: str,
        owner_rows: Iterable[Mapping[str, Any]],
    ) -> set[tuple[str, int]]:
        owner_rows = list(owner_rows)
        dependencies: set[tuple[str, int]] = set()
        specs_by_owner: dict[str, list[LinkSpec]] = {}
        for spec in LINK_SPECS:
            specs_by_owner.setdefault(spec.field_owner_model, []).append(spec)
        for owner in owner_rows:
            for spec in specs_by_owner.get(owner["model"], []):
                dependencies.update(
                    (spec.related_model, related_id)
                    for related_id in _relation_ids(
                        owner["payload"].get(spec.source_field), spec.cardinality
                    )
                )
            if owner["model"] == "stock.move":
                for field, model in (
                    ("picking_id", "stock.picking"),
                    ("purchase_line_id", "purchase.order.line"),
                ):
                    record_id = _relation_id(owner["payload"].get(field))
                    if record_id:
                        dependencies.add((model, record_id))
            if owner["model"] == "account.move.line":
                move_id = _relation_id(owner["payload"].get("move_id"))
                if move_id:
                    dependencies.add(("account.move", move_id))
                dependencies.update(
                    ("sale.order.line", record_id)
                    for record_id in _relation_ids(
                        owner["payload"].get("sale_line_ids"), "many2many"
                    )
                )

        first_level = self._snapshot_rows_for_keys(run_id, dependencies)
        for row in first_level:
            if row["model"] == "purchase.order.line":
                parent_id = _relation_id(row["payload"].get("order_id"))
                if parent_id:
                    dependencies.add(("purchase.order", parent_id))
            if row["model"] == "sale.order.line":
                parent_id = _relation_id(row["payload"].get("order_id"))
                if parent_id:
                    dependencies.add(("sale.order", parent_id))

        inferred_parents: dict[str, set[str]] = {}
        for owner in owner_rows:
            payload = owner["payload"]
            references: tuple[tuple[str, Any], ...] = ()
            if owner["model"] == "mrp.production":
                references = (
                    ("sale.order", payload.get("origin")),
                    ("approval.request", payload.get("x_studio_nomor_io")),
                    ("sale.order", payload.get("x_studio_nomor_jo")),
                )
            elif owner["model"] == "purchase.order.line":
                references = (("sale.order", payload.get("x_studio_jo")),)
            elif owner["model"] == "account.move":
                references = (("purchase.order", payload.get("invoice_origin")),)
            elif owner["model"] == "account.move.line":
                references = (("sale.order", payload.get("x_studio_sales_order")),)
            for model, value in references:
                if isinstance(value, str) and value.strip():
                    inferred_parents.setdefault(model, set()).add(value.strip())
        with self.pg.engine.connect() as conn:
            for model, names in inferred_parents.items():
                rows = conn.execute(
                    text("""
                        SELECT record_id
                        FROM ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                          AND model = :model
                          AND document_number IN :names
                    """).bindparams(bindparam("names", expanding=True)),
                    {"run_id": run_id, "model": model, "names": tuple(names)},
                ).scalars().all()
                dependencies.update((model, int(record_id)) for record_id in rows)
        return dependencies

    def _delete_affected_links(
        self,
        run_id: str,
        owner_keys: Iterable[tuple[str, int]],
    ) -> None:
        serialized = [
            {"model": model, "record_id": record_id}
            for model, record_id in sorted(set(owner_keys))
        ]
        if not serialized:
            return
        with self.pg.engine.begin() as conn:
            conn.execute(
                text("""
                    CREATE TEMP TABLE ct_affected_link_owner_key
                    ON COMMIT DROP AS
                    SELECT
                        item ->> 'model' AS model,
                        (item ->> 'record_id')::bigint AS record_id
                    FROM JSONB_ARRAY_ELEMENTS(CAST(:keys AS JSONB)) item
                """),
                {"keys": json.dumps(serialized)},
            )
            conn.execute(text("""
                CREATE UNIQUE INDEX ON ct_affected_link_owner_key (model, record_id)
            """))
            conn.execute(text("ANALYZE ct_affected_link_owner_key"))
            conn.execute(text("""
                DELETE FROM ct_document_link link
                USING ct_affected_link_owner_key owner
                WHERE link.extraction_run_id = CAST(:run_id AS UUID)
                  AND link.owner_model = owner.model
                  AND link.owner_record_id = owner.record_id
            """), {"run_id": run_id})

    def _update_changed_link_numbers(
        self,
        run_id: str,
        changed_keys: Iterable[tuple[str, int]],
    ) -> None:
        serialized = [
            {"model": model, "record_id": record_id}
            for model, record_id in sorted(set(changed_keys))
        ]
        if not serialized:
            return
        with self.pg.engine.begin() as conn:
            conn.execute(text("""
                CREATE TEMP TABLE ct_changed_link_number_key
                ON COMMIT DROP AS
                SELECT
                    item ->> 'model' AS model,
                    (item ->> 'record_id')::bigint AS record_id
                FROM JSONB_ARRAY_ELEMENTS(CAST(:keys AS JSONB)) item
            """), {"keys": json.dumps(serialized)})
            conn.execute(text("""
                CREATE UNIQUE INDEX ON ct_changed_link_number_key (model, record_id)
            """))
            conn.execute(text("ANALYZE ct_changed_link_number_key"))
            for side in ("parent", "child"):
                conn.execute(
                    text(f"""
                        UPDATE ct_document_link link
                        SET {side}_number = snapshot.document_number
                        FROM ct_native_record_snapshot snapshot
                        JOIN ct_changed_link_number_key changed
                          ON changed.model = snapshot.model
                         AND changed.record_id = snapshot.record_id
                        WHERE link.extraction_run_id = CAST(:run_id AS UUID)
                          AND snapshot.extraction_run_id = link.extraction_run_id
                          AND snapshot.model = link.{side}_model
                          AND snapshot.record_id = link.{side}_id
                    """),
                    {"run_id": run_id},
                )

    def _refresh_links_selective(
        self,
        run_id: str,
        base_run_id: str,
        changed_records: Mapping[str, list[int]],
        extracted_at: datetime,
    ) -> int:
        self._copy_links(run_id, base_run_id)
        owner_keys = self._dependent_owner_keys(run_id, base_run_id, changed_records)
        owner_rows = self._snapshot_rows_for_keys(run_id, owner_keys)
        dependency_keys = self._dependency_keys_for_owners(run_id, owner_rows)
        indexed_rows = self._snapshot_rows_for_keys(
            run_id,
            owner_keys | dependency_keys,
        )
        index = self._index_snapshots(indexed_rows)
        self._delete_affected_links(run_id, owner_keys)
        changed_keys = {
            (model, record_id)
            for model, record_ids in changed_records.items()
            for record_id in record_ids
        }
        self._update_changed_link_numbers(run_id, changed_keys)
        links = [
            *self._iter_direct_links(owner_rows, index),
            *self._iter_derived_links(owner_rows, index),
            *self._iter_inferred_links(owner_rows, self._name_index(indexed_rows)),
        ]
        self._insert_links(links, run_id, extracted_at)
        with self.pg.engine.connect() as conn:
            return int(
                conn.execute(
                    text("""
                        SELECT COUNT(*) FROM ct_document_link
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """),
                    {"run_id": run_id},
                ).scalar_one()
            )

    def _model_counts_for_run(self, run_id: str) -> dict[str, int]:
        with self.pg.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT model, COUNT(*) AS count
                    FROM ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    GROUP BY model
                """),
                {"run_id": run_id},
            ).mappings().all()
        return {str(row["model"]): int(row["count"]) for row in rows}

    def _publish_po_enrichment(
        self,
        conn: Any,
        *,
        run_id: str,
        base_run_id: str,
        completed_at: datetime,
    ) -> None:
        execution_id = str(uuid4())
        expected_count = int(
            conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND model = 'purchase.order'
                      AND LOWER(COALESCE(state, '')) IN ('cancel', 'cancelled')
                """),
                {"run_id": run_id},
            ).scalar_one()
        )
        conn.execute(
            text("""
                INSERT INTO ct_purchase_order_date_enrichment_execution (
                    execution_id, run_id, company_id, expected_count, returned_count,
                    null_date_order_count, status, started_at, completed_at
                ) VALUES (
                    CAST(:execution_id AS UUID), CAST(:run_id AS UUID), :company_id,
                    :expected_count, :expected_count, 0, 'RUNNING', :completed_at, NULL
                )
            """),
            {
                "execution_id": execution_id,
                "run_id": run_id,
                "company_id": self.company_id,
                "expected_count": expected_count,
                "completed_at": completed_at,
            },
        )
        conn.execute(
            text("""
                INSERT INTO ct_purchase_order_date_enrichment (
                    run_id, purchase_order_id, company_id, source_state, date_order,
                    source_write_date, extracted_at, enrichment_status,
                    enrichment_execution_id
                )
                SELECT
                    CAST(:run_id AS UUID), snapshot.record_id, :company_id,
                    LOWER(COALESCE(snapshot.state, '')),
                    COALESCE(
                        NULLIF(snapshot.payload ->> 'date_order', '')::timestamp,
                        previous.date_order
                    ),
                    snapshot.write_date, :completed_at, 'COMPLETED',
                    CAST(:execution_id AS UUID)
                FROM ct_native_record_snapshot snapshot
                LEFT JOIN ct_purchase_order_date_enrichment previous
                  ON previous.run_id = CAST(:base_run_id AS UUID)
                 AND previous.purchase_order_id = snapshot.record_id
                WHERE snapshot.extraction_run_id = CAST(:run_id AS UUID)
                  AND snapshot.model = 'purchase.order'
                  AND LOWER(COALESCE(snapshot.state, '')) IN ('cancel', 'cancelled')
            """),
            {
                "execution_id": execution_id,
                "run_id": run_id,
                "base_run_id": base_run_id,
                "company_id": self.company_id,
                "completed_at": completed_at,
            },
        )
        null_count = int(
            conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM ct_purchase_order_date_enrichment
                    WHERE run_id = CAST(:run_id AS UUID) AND date_order IS NULL
                """),
                {"run_id": run_id},
            ).scalar_one()
        )
        conn.execute(
            text("""
                UPDATE ct_purchase_order_date_enrichment_execution
                SET status = 'COMPLETED', null_date_order_count = :null_count,
                    completed_at = :completed_at
                WHERE execution_id = CAST(:execution_id AS UUID)
            """),
            {
                "execution_id": execution_id,
                "null_count": null_count,
                "completed_at": completed_at,
            },
        )

    def _publish_incremental_run(
        self,
        *,
        run_id: str,
        base_run_id: str,
        started_at: datetime,
        model_counts: dict[str, int],
        changed_models: dict[str, int],
        link_count: int,
        recalculated_rules: list[str],
        unrecalculated_rules: list[str],
        source_fingerprint: str,
        source_binding: str,
    ) -> datetime:
        completed_at = datetime.now(timezone.utc)
        changed_documents = sum(changed_models.values())
        refresh_meta = {
            "sync_mode": "incremental",
            "base_run_id": base_run_id,
            "source_watermark": started_at.isoformat(),
            "last_successful_odoo_sync_at": completed_at.isoformat(),
            "changed_documents": changed_documents,
            "changed_models": changed_models,
            "recalculated_rule_ids": recalculated_rules,
            "unrecalculated_rule_ids": unrecalculated_rules,
            "source_fingerprint": source_fingerprint,
            "source_binding": source_binding,
        }
        published_counts: dict[str, Any] = {
            **model_counts,
            "document_links": link_count,
            "_refresh": refresh_meta,
        }
        with self.pg.engine.begin() as conn:
            self._progress(
                "LINEAGE",
                "Membentuk relasi line-to-line…",
                changed_documents,
                len(recalculated_rules),
                "Pembentukan relasi line-to-line",
                "Relasi line Odoo",
                len(MODEL_SPECS) + 3,
                len(MODEL_SPECS) + 7,
            )
            v03_summary = self._build_v03_candidate(conn, run_id=run_id)
            refresh_meta["v03"] = v03_summary
            self._publish_po_enrichment(
                conn,
                run_id=run_id,
                base_run_id=base_run_id,
                completed_at=completed_at,
            )
            conn.execute(
                text("""
                    UPDATE ct_extraction_run
                    SET completed_at = :completed_at,
                        status = 'COMPLETED',
                        model_counts = CAST(:model_counts AS JSONB),
                        error_message = NULL
                    WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
                """),
                {
                    "completed_at": completed_at,
                    "model_counts": json.dumps(published_counts),
                    "run_id": run_id,
                },
            )
            if changed_documents:
                for view_name in MATERIALIZED_VIEWS:
                    conn.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
            publish_pointer(
                conn,
                company_id=self.company_id,
                run_id=run_id,
                contract_version=CONTRACT_VERSION,
                scope_year=SCOPE_YEAR,
                published_at=completed_at,
            )
            self._last_v03_summary = v03_summary
        return completed_at

    def _build_v03_candidate(self, conn: Any, *, run_id: str) -> dict[str, Any]:
        conn.execute(text("SET LOCAL work_mem = '64MB'"))
        lineage = rebuild_line_lineage(conn, run_id=run_id)
        self._progress(
            "RULES",
            "Menjalankan pemeriksaan terdampak…",
            phase_label="Rerun pemeriksaan terdampak",
            current_work="Gross Profit dan aturan bisnis",
            completed_work_units=len(MODEL_SPECS) + 4,
            total_work_units=len(MODEL_SPECS) + 7,
        )
        gross_profit = rebuild_gross_profit(
            conn,
            run_id=run_id,
            company_id=self.company_id,
        )
        detections = rebuild_finding_detections(
            conn,
            run_id=run_id,
            company_id=self.company_id,
            scope_year=SCOPE_YEAR,
        )
        lifecycle = reconcile_findings(conn, run_id=run_id)
        self._progress(
            "READ_MODELS",
            "Memperbarui ringkasan, pencarian, tracking, dan Peta Proses…",
            phase_label="Update ringkasan, pencarian, tracking, dan Process Map",
            current_work="Model baca Control Tower",
            completed_work_units=len(MODEL_SPECS) + 5,
            total_work_units=len(MODEL_SPECS) + 7,
        )
        search_count = rebuild_document_search(
            conn,
            run_id=run_id,
            company_id=self.company_id,
        )
        return {
            "lineage": lineage,
            "search_documents": search_count,
            "gross_profit": gross_profit,
            "detections": detections,
            "finding_lifecycle": lifecycle,
        }

    def _mark_incremental_failed(self, run_id: str) -> None:
        with self.pg.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE ct_extraction_run
                    SET completed_at = NOW(), status = 'FAILED',
                        error_message = 'INCREMENTAL_REFRESH_FAILED'
                    WHERE run_id = CAST(:run_id AS UUID) AND status = 'RUNNING'
                """),
                {"run_id": run_id},
            )

    def _run_incremental_locked(self) -> dict[str, Any]:
        total_units = len(MODEL_SPECS) + 7
        self._progress(
            "SCHEMA_CHECK",
            "Memeriksa koneksi dan skema…",
            phase_label="Pemeriksaan koneksi dan skema",
            current_work="Kontrak sumber dan watermark",
            completed_work_units=1,
            total_work_units=total_units,
        )
        base = self._current_completed_run()
        source_fingerprint, source_binding = self._verify_source_compatibility(base)
        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        changed_records: dict[str, list[int]] = {}
        try:
            self._start_incremental_run(run_id, base["run_id"], started_at)
            for model_index, spec in enumerate(MODEL_SPECS, start=1):
                self._progress(
                    "ODOO_SYNC",
                    f"Mengambil perubahan terbaru ({spec.model})…",
                    sum(len(ids) for ids in changed_records.values()),
                    phase_label="Sinkronisasi Odoo",
                    current_work=spec.business_name or spec.model,
                    completed_work_units=model_index,
                    total_work_units=total_units,
                )
                changed_ids = self._extract_model_incremental(
                    spec,
                    run_id,
                    started_at,
                    base["source_watermark"],
                )
                if changed_ids:
                    changed_records[spec.model] = changed_ids
                self._progress(
                    "ODOO_SYNC",
                    f"Sinkronisasi {spec.model} selesai.",
                    sum(len(ids) for ids in changed_records.values()),
                    phase_label="Sinkronisasi Odoo",
                    current_work=spec.business_name or spec.model,
                    completed_work_units=1 + model_index,
                    total_work_units=total_units,
                    processed_records=len(changed_ids),
                    total_records=len(changed_ids),
                )

            changed_models = {
                model: len(record_ids) for model, record_ids in changed_records.items()
            }
            changed_count = sum(changed_models.values())
            self._progress(
                "POSTGRES_UPDATE",
                f"Memperbarui {changed_count} dokumen…",
                changed_count,
                phase_label="Update PostgreSQL",
                current_work="Snapshot kandidat dan hubungan dokumen",
                completed_work_units=len(MODEL_SPECS) + 2,
                total_work_units=total_units,
                processed_records=changed_count,
                total_records=changed_count,
            )
            if changed_records:
                link_count = self._refresh_links_selective(
                    run_id,
                    base["run_id"],
                    changed_records,
                    started_at,
                )
            else:
                link_count = self._copy_links(run_id, base["run_id"])

            affected_rules = sorted(
                set().union(*(RULES_BY_MODEL[model] for model in changed_models))
                if changed_models
                else set()
            )
            unrecalculated_rules = (
                ["SO-SOURCE-001"] if "SO-SOURCE-001" in affected_rules else []
            )
            recalculated_rules = [
                rule for rule in affected_rules if rule not in unrecalculated_rules
            ]
            self._progress(
                "RULES",
                f"Menyiapkan {len(recalculated_rules)} pemeriksaan terdampak…",
                changed_count,
                len(recalculated_rules),
                "Rerun pemeriksaan terdampak",
                "Kelompok aturan terdampak",
                len(MODEL_SPECS) + 4,
                total_units,
                len(recalculated_rules),
                len(recalculated_rules),
            )
            model_counts = self._model_counts_for_run(run_id)
            completed_at = self._publish_incremental_run(
                run_id=run_id,
                base_run_id=base["run_id"],
                started_at=started_at,
                model_counts=model_counts,
                changed_models=changed_models,
                link_count=link_count,
                recalculated_rules=recalculated_rules,
                unrecalculated_rules=unrecalculated_rules,
                source_fingerprint=source_fingerprint,
                source_binding=source_binding,
            )
            self._progress(
                "FINALIZE",
                (
                    "Tidak ada perubahan sejak pembaruan terakhir."
                    if not changed_models
                    else "Data berhasil diperbarui."
                ),
                changed_count,
                len(recalculated_rules),
                "Finalisasi dan publish",
                "Dataset Control Tower telah dipublikasikan",
                total_units,
                total_units,
            )
            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "outcome": (
                    "NO_CHANGES"
                    if not changed_models
                    else "UPDATED_WITH_LIMITATIONS"
                    if unrecalculated_rules
                    else "UPDATED"
                ),
                "company_id": self.company_id,
                "changed_documents": sum(changed_models.values()),
                "changed_models": changed_models,
                "recalculated_rule_ids": recalculated_rules,
                "unrecalculated_rule_ids": unrecalculated_rules,
                "last_successful_odoo_sync_at": completed_at.isoformat(),
                "snapshot_timestamp": completed_at.isoformat(),
                "source_watermark": started_at.isoformat(),
                "v03": getattr(self, "_last_v03_summary", {}),
                "read_only": True,
            }
        except Exception as exc:
            self._mark_incremental_failed(run_id)
            self.logger.error(
                "Control Tower incremental refresh failed",
                error_type=type(exc).__name__,
            )
            if isinstance(exc, IncrementalRefreshError):
                raise
            raise IncrementalRefreshError(
                "Pembaruan Odoo gagal; snapshot terakhir tetap dipertahankan."
            ) from exc

    def run_incremental(self) -> dict[str, Any]:
        """Fetch only Odoo changes and atomically publish a complete candidate snapshot."""
        self._progress(
            "PREPARATION",
            "Menyiapkan refresh Control Tower…",
            phase_label="Persiapan",
            current_work="Membuka checkpoint terakhir yang berhasil",
            completed_work_units=0,
            total_work_units=len(MODEL_SPECS) + 7,
        )
        self.ensure_schema()
        self.audit_data_contract()
        with self.pg.engine.connect() as lock_conn:
            acquired = bool(
                lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": REFRESH_LOCK_KEY},
                ).scalar_one()
            )
            lock_conn.commit()
            if not acquired:
                raise RefreshInProgress("Pembaruan Control Tower sedang berjalan.")
            try:
                return self._run_incremental_locked()
            finally:
                lock_conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": REFRESH_LOCK_KEY},
                )
                lock_conn.commit()

    def run(self) -> dict[str, Any]:
        """Jalankan extraction lengkap dan publish hanya ketika run COMPLETED."""
        self.ensure_schema()
        self.audit_data_contract()
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
            refresh_meta = {
                "sync_mode": "full_backfill",
                "source_watermark": started_at.isoformat(),
                "last_successful_odoo_sync_at": completed_at.isoformat(),
                "changed_documents": sum(model_counts.values()),
                "source_fingerprint": self._source_fingerprint(),
                "source_binding": "full_backfill",
            }
            with self.pg.engine.begin() as conn:
                v03_summary = self._build_v03_candidate(conn, run_id=run_id)
                self._publish_po_enrichment(
                    conn,
                    run_id=run_id,
                    base_run_id=run_id,
                    completed_at=completed_at,
                )
                published_counts = {
                    **model_counts,
                    "document_links": link_count,
                    "_refresh": {**refresh_meta, "v03": v03_summary},
                }
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
                        "model_counts": json.dumps(published_counts),
                        "run_id": run_id,
                    },
                )
                for view_name in MATERIALIZED_VIEWS:
                    if conn.execute(
                        text("SELECT to_regclass(:view_name)"),
                        {"view_name": view_name},
                    ).scalar_one() is not None:
                        conn.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
                publish_pointer(
                    conn,
                    company_id=self.company_id,
                    run_id=run_id,
                    contract_version=CONTRACT_VERSION,
                    scope_year=SCOPE_YEAR,
                    published_at=completed_at,
                )

            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "company_id": self.company_id,
                "model_counts": model_counts,
                "document_links": link_count,
                "v03": v03_summary,
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
