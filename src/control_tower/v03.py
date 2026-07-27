"""Odoo Control Tower v0.3 truth, finding, and publication layer.

Everything in this module writes only to the local PostgreSQL database. Odoo
access stays in :mod:`relation_extractor`, behind its read-only allowlist.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import text


SCOPE_YEAR = 2026
COGS_ACCOUNT_CODE = "51000010"
COGS_ACCOUNT_NAME = "Cost of Goods Sold (Material)"

CATEGORIES = ("Masalah Aktif", "Perlu Ditinjau", "Data Belum Lengkap")
CLOSE_REASONS = (
    "Dokumen terlalu lama untuk diperbaiki",
    "Sudah tidak relevan",
    "Pengecualian bisnis yang sah",
    "Sudah dikoreksi di luar sistem",
    "Duplikat temuan",
    "Alasan lain",
)
CLOSE_REASONS_REQUIRING_NOTE = (
    "Pengecualian bisnis yang sah",
    "Sudah dikoreksi di luar sistem",
    "Alasan lain",
)


V03_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ct_published_run (
    company_id BIGINT PRIMARY KEY,
    extraction_run_id UUID NOT NULL UNIQUE,
    contract_version TEXT NOT NULL,
    scope_year INTEGER NOT NULL,
    published_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ct_line_lineage (
    extraction_run_id UUID NOT NULL,
    relationship_type TEXT NOT NULL,
    source_model TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    target_model TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    source_document_model TEXT,
    source_document_id BIGINT,
    target_document_model TEXT,
    target_document_id BIGINT,
    product_id BIGINT,
    source_quantity NUMERIC,
    target_quantity NUMERIC,
    source_uom_id BIGINT,
    target_uom_id BIGINT,
    source_quantity_reference NUMERIC,
    target_quantity_reference NUMERIC,
    uom_rounding NUMERIC,
    quantity_difference NUMERIC,
    company_currency_value NUMERIC,
    lineage_status TEXT NOT NULL CHECK (
        lineage_status IN ('PROVEN', 'PROVEN_UNALLOCATED', 'INCOMPLETE')
    ),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (
        extraction_run_id, relationship_type, source_model, source_id,
        target_model, target_id
    )
);

CREATE INDEX IF NOT EXISTS idx_ct_lineage_source
    ON ct_line_lineage (extraction_run_id, source_model, source_id);
CREATE INDEX IF NOT EXISTS idx_ct_lineage_target
    ON ct_line_lineage (extraction_run_id, target_model, target_id);
CREATE INDEX IF NOT EXISTS idx_ct_lineage_documents
    ON ct_line_lineage (
        extraction_run_id, source_document_model, source_document_id,
        target_document_model, target_document_id
    );
CREATE INDEX IF NOT EXISTS idx_ct_lineage_product
    ON ct_line_lineage (extraction_run_id, product_id, relationship_type);

CREATE TABLE IF NOT EXISTS ct_finding_detection (
    extraction_run_id UUID NOT NULL,
    finding_key TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    business_title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('Masalah Aktif', 'Perlu Ditinjau', 'Data Belum Lengkap')
    ),
    primary_document_model TEXT NOT NULL,
    primary_document_id BIGINT NOT NULL,
    primary_document_number TEXT,
    primary_document_state TEXT,
    primary_line_model TEXT,
    primary_line_id BIGINT,
    impacted_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
    impacted_lines JSONB NOT NULL DEFAULT '[]'::jsonb,
    facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_action TEXT,
    process_owner TEXT NOT NULL,
    responsible_user TEXT,
    process_node TEXT NOT NULL,
    business_date DATE,
    selectors JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (extraction_run_id, finding_key)
);

CREATE INDEX IF NOT EXISTS idx_ct_detection_category
    ON ct_finding_detection (extraction_run_id, category, process_node, business_date);
CREATE INDEX IF NOT EXISTS idx_ct_detection_document
    ON ct_finding_detection (
        extraction_run_id, primary_document_model, primary_document_id, primary_line_id
    );

CREATE TABLE IF NOT EXISTS ct_finding (
    finding_key TEXT PRIMARY KEY,
    rule_code TEXT NOT NULL,
    business_title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('Masalah Aktif', 'Perlu Ditinjau', 'Data Belum Lengkap')
    ),
    primary_document_model TEXT NOT NULL,
    primary_document_id BIGINT NOT NULL,
    primary_document_number TEXT,
    primary_document_state TEXT,
    primary_line_model TEXT,
    primary_line_id BIGINT,
    impacted_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
    impacted_lines JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_detected_at TIMESTAMPTZ NOT NULL,
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN ('ACTIVE', 'MANUALLY_CLOSED', 'AUTO_RESOLVED')
    ),
    closed_reason TEXT,
    closed_note TEXT,
    closed_by TEXT,
    closed_at TIMESTAMPTZ,
    reopened_reason TEXT,
    reopened_by TEXT,
    reopened_at TIMESTAMPTZ,
    auto_resolved_at TIMESTAMPTZ,
    current_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    process_owner TEXT NOT NULL,
    responsible_user TEXT,
    process_node TEXT NOT NULL,
    business_date DATE,
    last_detection_run_id UUID NOT NULL,
    currently_detected BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ct_finding_active
    ON ct_finding (category, process_node, business_date DESC)
    WHERE lifecycle_state = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_ct_finding_archive
    ON ct_finding (lifecycle_state, closed_at DESC, auto_resolved_at DESC)
    WHERE lifecycle_state <> 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_ct_finding_document
    ON ct_finding (primary_document_model, primary_document_id, primary_line_id);

CREATE TABLE IF NOT EXISTS ct_finding_event (
    event_id BIGSERIAL PRIMARY KEY,
    finding_key TEXT NOT NULL REFERENCES ct_finding (finding_key),
    batch_id UUID,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('DETECTED', 'UPDATED', 'MANUALLY_CLOSED', 'REOPENED', 'AUTO_RESOLVED')
    ),
    actor TEXT NOT NULL,
    reason TEXT,
    note TEXT,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evidence_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ct_finding_event_history
    ON ct_finding_event (finding_key, event_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS idx_ct_finding_event_batch
    ON ct_finding_event (batch_id, event_at) WHERE batch_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ct_exception_rule (
    exception_id UUID PRIMARY KEY,
    rule_code TEXT NOT NULL,
    selector JSONB NOT NULL,
    reason TEXT NOT NULL,
    approver TEXT NOT NULL,
    created_by TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (jsonb_typeof(selector) = 'object'),
    CHECK (selector <> '{}'::jsonb),
    CHECK (valid_until IS NULL OR valid_until >= valid_from)
);

CREATE INDEX IF NOT EXISTS idx_ct_exception_rule_active
    ON ct_exception_rule (rule_code, valid_from, valid_until)
    WHERE active;

CREATE TABLE IF NOT EXISTS ct_exception_rule_event (
    event_id BIGSERIAL PRIMARY KEY,
    exception_id UUID NOT NULL REFERENCES ct_exception_rule (exception_id),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS ct_rule_config (
    rule_code TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    business_condition TEXT NOT NULL,
    severity_mapping JSONB NOT NULL,
    evidence_shown JSONB NOT NULL,
    process_owner TEXT NOT NULL,
    effective_date DATE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ct_product_cost_classification (
    company_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    classification TEXT NOT NULL CHECK (
        classification IN ('Material', 'Jasa Eksternal', 'Belum Terkategori')
    ),
    source TEXT NOT NULL CHECK (source IN ('AUTO', 'MANUAL')),
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, product_id)
);

CREATE TABLE IF NOT EXISTS ct_document_search (
    extraction_run_id UUID NOT NULL,
    company_id BIGINT NOT NULL,
    document_type TEXT NOT NULL,
    model TEXT NOT NULL,
    record_id BIGINT NOT NULL,
    document_number TEXT,
    native_state TEXT,
    business_date DATE,
    secondary_text TEXT,
    search_text TEXT NOT NULL,
    active_finding_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (extraction_run_id, model, record_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_document_search_number
    ON ct_document_search (
        extraction_run_id, document_type, LOWER(document_number), business_date DESC
    );
CREATE INDEX IF NOT EXISTS idx_ct_document_search_text
    ON ct_document_search USING GIN (to_tsvector('simple', search_text));

CREATE TABLE IF NOT EXISTS ct_gp_summary (
    extraction_run_id UUID NOT NULL,
    sale_order_id BIGINT NOT NULL,
    sale_order_number TEXT,
    planned_revenue_idr NUMERIC,
    planned_rkb_idr NUMERIC,
    planned_gp_idr NUMERIC,
    planned_margin NUMERIC,
    realized_revenue_idr NUMERIC,
    realized_cogs_idr NUMERIC,
    realized_gp_idr NUMERIC,
    realized_margin NUMERIC,
    planned_status TEXT NOT NULL,
    realized_status TEXT NOT NULL,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    calculated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (extraction_run_id, sale_order_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_gp_summary_status
    ON ct_gp_summary (extraction_run_id, planned_status, realized_status);

CREATE TABLE IF NOT EXISTS ct_gp_line (
    extraction_run_id UUID NOT NULL,
    sale_order_id BIGINT NOT NULL,
    sale_order_line_id BIGINT NOT NULL,
    invoice_line_id BIGINT NOT NULL,
    product_id BIGINT,
    quantity NUMERIC,
    revenue_idr NUMERIC NOT NULL,
    cogs_idr NUMERIC,
    gross_profit_idr NUMERIC,
    allocation_status TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (
        extraction_run_id, sale_order_line_id, invoice_line_id
    )
);

CREATE INDEX IF NOT EXISTS idx_ct_gp_line_so
    ON ct_gp_line (extraction_run_id, sale_order_id, product_id);

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
);

ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS phase_label TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS current_work TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS completed_work_units BIGINT NOT NULL DEFAULT 0;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS total_work_units BIGINT NOT NULL DEFAULT 0;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS percentage NUMERIC(5,2) NOT NULL DEFAULT 0;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS processed_records BIGINT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS total_records BIGINT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS failed_phase TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS failed_work TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS last_successful_batch TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS retryable_phase TEXT;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS checkpoint JSONB;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS retry_of UUID;
ALTER TABLE ct_refresh_job ADD COLUMN IF NOT EXISTS final_summary JSONB;
"""


V03_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS ct_gp_line;
DROP TABLE IF EXISTS ct_gp_summary;
DROP TABLE IF EXISTS ct_document_search;
DROP TABLE IF EXISTS ct_product_cost_classification;
DROP TABLE IF EXISTS ct_rule_config;
DROP TABLE IF EXISTS ct_exception_rule_event;
DROP TABLE IF EXISTS ct_exception_rule;
DROP TABLE IF EXISTS ct_finding_event;
DROP TABLE IF EXISTS ct_finding;
DROP TABLE IF EXISTS ct_finding_detection;
DROP TABLE IF EXISTS ct_line_lineage;
DROP TABLE IF EXISTS ct_published_run;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS phase_label;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS current_work;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS completed_work_units;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS total_work_units;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS percentage;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS processed_records;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS total_records;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS failed_phase;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS failed_work;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS last_successful_batch;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS error_message;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS retryable_phase;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS checkpoint;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS retry_of;
ALTER TABLE IF EXISTS ct_refresh_job DROP COLUMN IF EXISTS final_summary;
"""


RULE_CONFIGS: tuple[Mapping[str, Any], ...] = (
    {
        "rule_code": "INV_ITEM_WITHOUT_SOL",
        "business_name": "Item invoice tanpa Sales Order Line",
        "business_condition": "Baris item invoice pelanggan tidak memiliki relasi native ke Sales Order Line.",
        "severity_mapping": {"impact_proven": "Masalah Aktif", "no_impact": "Perlu Ditinjau", "missing_relation_data": "Data Belum Lengkap"},
        "evidence_shown": ["Invoice", "Customer", "Product", "Quantity", "Untaxed value", "Delivery or COGS"],
        "process_owner": "Finance",
    },
    {
        "rule_code": "DELIVERY_WITHOUT_SOL",
        "business_name": "Delivery tanpa Sales Order Line",
        "business_condition": "Stock-out ke customer tidak memiliki relasi native ke Sales Order Line.",
        "severity_mapping": {"done": "Masalah Aktif"},
        "evidence_shown": ["Delivery", "Product", "Quantity", "Customer", "Operation type"],
        "process_owner": "Warehouse",
    },
    {
        "rule_code": "RECEIPT_WITHOUT_POL",
        "business_name": "Receipt tanpa Purchase Order Line",
        "business_condition": "Penerimaan dari supplier tidak memiliki relasi native ke Purchase Order Line.",
        "severity_mapping": {"done": "Masalah Aktif", "not_done": "Perlu Ditinjau"},
        "evidence_shown": ["Receipt", "Vendor", "Product", "Quantity", "Operation type"],
        "process_owner": "Warehouse",
    },
    {
        "rule_code": "VENDOR_BILL_WITHOUT_POL",
        "business_name": "Vendor Bill tanpa Purchase Order Line",
        "business_condition": "Baris produk Vendor Bill Posted tidak memiliki relasi native ke Purchase Order Line.",
        "severity_mapping": {"posted": "Masalah Aktif"},
        "evidence_shown": ["Vendor Bill", "Vendor", "Product", "Quantity", "Untaxed value"],
        "process_owner": "Finance",
    },
    {
        "rule_code": "PO_WITHOUT_ROP",
        "business_name": "Purchase Order tanpa Approval Procurement",
        "business_condition": "Purchase Order tidak memiliki basis Approval Procurement native pada barisnya.",
        "severity_mapping": {"confirmed": "Masalah Aktif", "draft": "Perlu Ditinjau"},
        "evidence_shown": ["Purchase Order", "Vendor", "Status", "Baris pembelian"],
        "process_owner": "Procurement",
    },
    {
        "rule_code": "CANCELLED_PARENT_ACTIVE_CHILD",
        "business_name": "Dokumen induk dibatalkan dengan dokumen lanjutan aktif",
        "business_condition": "Dokumen induk cancelled masih memiliki dokumen turunan terbuka melalui relasi native.",
        "severity_mapping": {"empty_child": "Masalah Aktif", "active_content": "Perlu Ditinjau"},
        "evidence_shown": ["Parent", "Open child", "Product", "Quantity", "Native status"],
        "process_owner": "PPIC",
    },
    {
        "rule_code": "QUANTITY_MISMATCH",
        "business_name": "Kuantitas dokumen terkait tidak sama",
        "business_condition": "Kuantitas line terkait berbeda setelah konversi dan pembulatan UoM Odoo.",
        "severity_mapping": {"outside_rounding": "Perlu Ditinjau", "uom_missing": "Data Belum Lengkap"},
        "evidence_shown": ["Source line", "Related line", "Quantity", "UoM", "Rounding"],
        "process_owner": "PPIC",
    },
    {
        "rule_code": "PLANNED_GP_NEGATIVE",
        "business_name": "Gross Profit rencana negatif",
        "business_condition": "Nilai Sales Order sebelum pajak dikurangi total RKB menghasilkan Gross Profit negatif.",
        "severity_mapping": {"quotation": "Perlu Ditinjau", "confirmed": "Masalah Aktif"},
        "evidence_shown": ["Sales Order", "Revenue IDR", "RKB IDR", "Gross Profit", "Margin"],
        "process_owner": "Commercial",
    },
    {
        "rule_code": "REALIZED_GP_NEGATIVE",
        "business_name": "Gross Profit realisasi negatif",
        "business_condition": "Revenue item Posted dikurangi COGS account 51000010 menghasilkan Gross Profit negatif.",
        "severity_mapping": {"negative": "Masalah Aktif"},
        "evidence_shown": ["Posted revenue", "COGS", "Gross Profit", "Margin", "Reconciliation"],
        "process_owner": "Finance",
    },
    {
        "rule_code": "RKB_LINEAGE_MISSING",
        "business_name": "Hubungan RKB ke Approval Procurement belum tersedia",
        "business_condition": "Baris RKB membutuhkan pengadaan, tetapi relasi native ke baris Approval Procurement tidak tersedia.",
        "severity_mapping": {"missing": "Data Belum Lengkap"},
        "evidence_shown": ["RKB", "Item", "Required quantity", "Approval Procurement relation"],
        "process_owner": "Procurement",
    },
    {
        "rule_code": "COGS_LINEAGE_MISSING",
        "business_name": "Alokasi COGS ke invoice line belum tersedia",
        "business_condition": "Baris COGS Posted tidak memiliki relasi cogs_origin_id ke baris invoice.",
        "severity_mapping": {"missing": "Data Belum Lengkap"},
        "evidence_shown": ["Journal entry", "COGS", "Product", "Invoice line relation"],
        "process_owner": "Finance",
    },
)


def round_to_uom(value: Decimal, rounding: Decimal) -> Decimal:
    """Round with Odoo's half-up business precision for deterministic comparisons."""
    if rounding <= 0:
        raise ValueError("UoM rounding must be positive")
    return (value / rounding).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * rounding


def quantities_equal(left: Decimal, right: Decimal, rounding: Decimal) -> bool:
    return round_to_uom(left, rounding) == round_to_uom(right, rounding)


def validate_close(reason: str, note: str | None) -> tuple[str, str | None]:
    normalized_reason = reason.strip()
    normalized_note = (note or "").strip() or None
    if normalized_reason not in CLOSE_REASONS:
        raise ValueError("Alasan penutupan tidak valid.")
    if normalized_reason in CLOSE_REASONS_REQUIRING_NOTE and not normalized_note:
        raise ValueError("Catatan wajib diisi untuk alasan penutupan ini.")
    return normalized_reason, normalized_note


def ensure_v03_schema(conn: Any) -> None:
    conn.exec_driver_sql(V03_SCHEMA_SQL)
    effective_date = date(SCOPE_YEAR, 1, 1)
    for rule in RULE_CONFIGS:
        conn.execute(
            text("""
                INSERT INTO ct_rule_config (
                    rule_code, business_name, business_condition, severity_mapping,
                    evidence_shown, process_owner, effective_date, enabled, updated_at
                ) VALUES (
                    :rule_code, :business_name, :business_condition,
                    CAST(:severity_mapping AS JSONB), CAST(:evidence_shown AS JSONB),
                    :process_owner, :effective_date, TRUE, NOW()
                )
                ON CONFLICT (rule_code) DO UPDATE SET
                    business_name = EXCLUDED.business_name,
                    business_condition = EXCLUDED.business_condition,
                    severity_mapping = EXCLUDED.severity_mapping,
                    evidence_shown = EXCLUDED.evidence_shown,
                    process_owner = EXCLUDED.process_owner,
                    effective_date = EXCLUDED.effective_date,
                    updated_at = NOW()
            """),
            {
                **rule,
                "severity_mapping": json.dumps(rule["severity_mapping"]),
                "evidence_shown": json.dumps(rule["evidence_shown"]),
                "effective_date": effective_date,
            },
        )


def rebuild_line_lineage(conn: Any, *, run_id: str) -> dict[str, int]:
    """Build only native, line-level relationships for one unpublished run."""
    params = {"run_id": run_id}
    conn.execute(
        text("DELETE FROM ct_line_lineage WHERE extraction_run_id = CAST(:run_id AS UUID)"),
        params,
    )

    # Invoice line -> Sales Order line. A many-to-many relation is retained as
    # many rows; quantities are deliberately not allocated when there is more
    # than one related Sales Order line.
    conn.execute(
        text("""
            WITH invoice_line AS (
                SELECT
                    aml.record_id,
                    aml.payload,
                    move.record_id AS move_id,
                    move.payload ->> 'move_type' AS move_type,
                    COUNT(*) OVER (PARTITION BY aml.record_id) AS relation_count,
                    relation.sale_line_id
                FROM ct_native_record_snapshot aml
                JOIN ct_native_record_snapshot move
                  ON move.extraction_run_id = aml.extraction_run_id
                 AND move.model = 'account.move'
                 AND move.record_id = NULLIF(aml.payload #>> '{move_id,id}', '')::bigint
                CROSS JOIN LATERAL (
                    SELECT value::bigint AS sale_line_id
                    FROM jsonb_array_elements_text(
                        COALESCE(aml.payload -> 'sale_line_ids', '[]'::jsonb)
                    ) value
                ) relation
                WHERE aml.extraction_run_id = CAST(:run_id AS UUID)
                  AND aml.model = 'account.move.line'
                  AND move.payload ->> 'move_type' IN ('out_invoice', 'out_refund')
                  AND COALESCE(aml.payload ->> 'display_type', 'product') = 'product'
            ), resolved AS (
                SELECT
                    source.*,
                    sol.payload AS sol_payload,
                    NULLIF(source.payload #>> '{product_id,id}', '')::bigint AS source_product_id,
                    NULLIF(sol.payload #>> '{product_id,id}', '')::bigint AS target_product_id,
                    NULLIF(source.payload #>> '{product_uom_id,id}', '')::bigint AS source_uom_id,
                    NULLIF(sol.payload #>> '{product_uom,id}', '')::bigint AS target_uom_id,
                    NULLIF(source.payload ->> 'quantity', '')::numeric AS source_quantity,
                    NULLIF(sol.payload ->> 'product_uom_qty', '')::numeric AS target_quantity,
                    NULLIF(sol.payload #>> '{order_id,id}', '')::bigint AS sale_order_id
                FROM invoice_line source
                JOIN ct_native_record_snapshot sol
                  ON sol.extraction_run_id = CAST(:run_id AS UUID)
                 AND sol.model = 'sale.order.line'
                 AND sol.record_id = source.sale_line_id
            ), converted AS (
                SELECT
                    resolved.*,
                    NULLIF(source_uom.payload ->> 'factor', '')::numeric AS source_factor,
                    NULLIF(target_uom.payload ->> 'factor', '')::numeric AS target_factor,
                    NULLIF(target_uom.payload ->> 'rounding', '')::numeric AS target_rounding,
                    source_uom.payload #>> '{category_id,id}' AS source_category,
                    target_uom.payload #>> '{category_id,id}' AS target_category
                FROM resolved
                LEFT JOIN ct_native_record_snapshot source_uom
                  ON source_uom.extraction_run_id = CAST(:run_id AS UUID)
                 AND source_uom.model = 'uom.uom'
                 AND source_uom.record_id = resolved.source_uom_id
                LEFT JOIN ct_native_record_snapshot target_uom
                  ON target_uom.extraction_run_id = CAST(:run_id AS UUID)
                 AND target_uom.model = 'uom.uom'
                 AND target_uom.record_id = resolved.target_uom_id
            )
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id, source_quantity,
                target_quantity, source_uom_id, target_uom_id, source_quantity_reference,
                target_quantity_reference, uom_rounding, quantity_difference,
                lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), 'INVOICE_LINE_TO_SO_LINE', 'account.move.line', record_id,
                'sale.order.line', sale_line_id, 'account.move', move_id,
                'sale.order', sale_order_id, source_product_id, source_quantity,
                target_quantity, source_uom_id, target_uom_id,
                CASE WHEN source_factor <> 0 THEN source_quantity / source_factor END,
                CASE WHEN target_factor <> 0 THEN target_quantity / target_factor END,
                CASE WHEN target_factor <> 0 THEN target_rounding / target_factor END,
                CASE
                    WHEN source_factor <> 0 AND target_factor <> 0
                    THEN (source_quantity / source_factor) - (target_quantity / target_factor)
                END,
                CASE
                    WHEN source_product_id IS DISTINCT FROM target_product_id
                      OR source_factor IS NULL OR target_factor IS NULL
                      OR source_factor = 0 OR target_factor = 0
                      OR source_category IS DISTINCT FROM target_category
                    THEN 'INCOMPLETE'
                    WHEN relation_count > 1 THEN 'PROVEN_UNALLOCATED'
                    ELSE 'PROVEN'
                END,
                jsonb_build_object(
                    'native_field', 'account.move.line.sale_line_ids',
                    'relation_count', relation_count,
                    'move_type', move_type
                )
            FROM converted
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    return _continue_line_lineage(conn, params)


def _insert_procurement_and_cost_detections(conn: Any, params: Mapping[str, Any]) -> None:
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), candidates AS (
                SELECT line, move, product
                FROM snapshot line
                JOIN snapshot move
                  ON move.model = 'account.move'
                 AND move.record_id = NULLIF(line.payload #>> '{move_id,id}', '')::bigint
                 AND move.state = 'posted'
                 AND move.payload ->> 'move_type' IN ('in_invoice', 'in_refund')
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(line.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' IN ('consu', 'service')
                WHERE line.model = 'account.move.line'
                  AND COALESCE(line.payload ->> 'display_type', 'product') = 'product'
                  AND line.payload #>> '{purchase_line_id,id}' IS NULL
                  AND COALESCE(
                        NULLIF(move.payload ->> 'invoice_date', '')::date,
                        NULLIF(move.payload ->> 'date', '')::date
                      ) >= :scope_start
                  AND COALESCE(
                        NULLIF(move.payload ->> 'invoice_date', '')::date,
                        NULLIF(move.payload ->> 'date', '')::date
                      ) < :scope_end
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID),
                MD5(CONCAT_WS('|', 'VENDOR_BILL_WITHOUT_POL', 'account.move', (move).record_id,
                              'account.move.line', (line).record_id, 'missing_purchase_line')),
                'VENDOR_BILL_WITHOUT_POL', 'Vendor Bill tanpa Purchase Order Line',
                'Masalah Aktif', 'account.move', (move).record_id, (move).document_number,
                (move).state, 'account.move.line', (line).record_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move', 'id', (move).record_id, 'number', (move).document_number,
                    'status', (move).state, 'type', 'Vendor Bill', 'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move.line', 'id', (line).record_id,
                    'product', (line).payload #>> '{product_id,name}',
                    'quantity', (line).payload ->> 'quantity',
                    'uom', (line).payload #>> '{product_uom_id,name}',
                    'untaxed_value', (line).payload ->> 'price_subtotal'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Vendor Bill', 'value', (move).document_number),
                    jsonb_build_object('label', 'Vendor', 'value', (move).payload #>> '{partner_id,name}'),
                    jsonb_build_object('label', 'Product', 'value', (line).payload #>> '{product_id,name}')
                ),
                'Periksa dasar procurement atau gunakan pengecualian yang sudah disetujui.',
                'Finance', 'Vendor Bill',
                COALESCE(NULLIF((move).payload ->> 'invoice_date', '')::date,
                         NULLIF((move).payload ->> 'date', '')::date),
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', (product).record_id,
                    'product_category_id', NULLIF((product).payload #>> '{categ_id,id}', '')::bigint,
                    'account_id', NULLIF((line).payload #>> '{account_id,id}', '')::bigint,
                    'journal_id', NULLIF((move).payload #>> '{journal_id,id}', '')::bigint,
                    'vendor_id', NULLIF((move).payload #>> '{partner_id,id}', '')::bigint,
                    'company_id', :company_id
                )), :detected_at
            FROM candidates
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), candidate AS (
                SELECT po.* FROM snapshot po
                WHERE po.model = 'purchase.order'
                  AND po.state NOT IN ('cancel', 'cancelled')
                  AND NULLIF(po.payload ->> 'date_order', '')::date >= :scope_start
                  AND NULLIF(po.payload ->> 'date_order', '')::date < :scope_end
                  AND NOT EXISTS (
                      SELECT 1 FROM snapshot pol
                      JOIN snapshot approval
                        ON approval.model = 'approval.request'
                       AND approval.record_id = NULLIF(
                           pol.payload #>> '{x_studio_many2one_field_n6i7C,id}', ''
                       )::bigint
                       AND UPPER(COALESCE(approval.payload #>> '{category_id,name}', '')) = 'PEMBELIAN'
                      WHERE pol.model = 'purchase.order.line'
                        AND NULLIF(pol.payload #>> '{order_id,id}', '')::bigint = po.record_id
                  )
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, impacted_documents, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', 'PO_WITHOUT_ROP',
                    'purchase.order', record_id, '', '', 'missing_approval_procurement')),
                'PO_WITHOUT_ROP', 'Purchase Order tanpa Approval Procurement',
                CASE WHEN state IN ('purchase', 'done') THEN 'Masalah Aktif' ELSE 'Perlu Ditinjau' END,
                'purchase.order', record_id, document_number, state,
                jsonb_build_array(jsonb_build_object(
                    'model', 'purchase.order', 'id', record_id, 'number', document_number,
                    'status', state, 'problematic', TRUE
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Purchase Order', 'value', document_number),
                    jsonb_build_object('label', 'Vendor', 'value', payload #>> '{partner_id,name}'),
                    jsonb_build_object('label', 'Approval Procurement', 'value', 'Belum terhubung')
                ),
                CASE WHEN state IN ('purchase', 'done')
                    THEN 'Periksa dasar persetujuan untuk Purchase Order yang sudah dikonfirmasi.'
                    ELSE 'Konfirmasi Approval Procurement sebelum RFQ dikonfirmasi.' END,
                'Procurement', 'Purchase Order', NULLIF(payload ->> 'date_order', '')::date,
                jsonb_strip_nulls(jsonb_build_object(
                    'vendor_id', NULLIF(payload #>> '{partner_id,id}', '')::bigint,
                    'company_id', :company_id
                )), :detected_at
            FROM candidate
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', 'RKB_LINEAGE_MISSING',
                    'approval.request', header.record_id, 'approval.product.line', line.record_id,
                    'missing_rkb_rop_line')),
                'RKB_LINEAGE_MISSING', 'Hubungan RKB ke Approval Procurement belum tersedia',
                'Data Belum Lengkap', 'approval.request', header.record_id,
                header.document_number, header.state, 'approval.product.line', line.record_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'approval.request', 'id', header.record_id,
                    'number', header.document_number, 'status', header.state,
                    'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'approval.product.line', 'id', line.record_id,
                    'product', line.payload #>> '{product_id,name}',
                    'quantity', line.payload ->> 'quantity',
                    'uom', line.payload #>> '{product_uom_id,name}'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'RKB', 'value', header.document_number),
                    jsonb_build_object('label', 'Item', 'value', line.payload #>> '{product_id,name}'),
                    jsonb_build_object('label', 'Hubungan Approval Procurement', 'value', 'Tidak tersedia')
                ),
                'Lengkapi relasi native RKB Line ke Approval Procurement Line.',
                'Procurement', 'RKB Pekerjaan',
                NULLIF(header.payload ->> 'date_confirmed', '')::date,
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', NULLIF(line.payload #>> '{product_id,id}', '')::bigint,
                    'product_category_id', NULLIF(product.payload #>> '{categ_id,id}', '')::bigint,
                    'company_id', :company_id
                )), :detected_at
            FROM snapshot line
            JOIN snapshot header
              ON header.model = 'approval.request'
             AND header.record_id = NULLIF(line.payload #>> '{approval_request_id,id}', '')::bigint
             AND UPPER(COALESCE(header.payload #>> '{category_id,name}', '')) = 'RKB'
             AND NULLIF(header.payload ->> 'date_confirmed', '')::date >= :scope_start
             AND NULLIF(header.payload ->> 'date_confirmed', '')::date < :scope_end
            LEFT JOIN snapshot product
              ON product.model = 'product.product'
             AND product.record_id = NULLIF(line.payload #>> '{product_id,id}', '')::bigint
            WHERE line.model = 'approval.product.line'
              AND (COALESCE((line.payload ->> 'x_studio_request_of_approval')::boolean, FALSE)
                   OR COALESCE(NULLIF(line.payload ->> 'x_studio_total_rop', '')::numeric, 0) > 0)
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', 'COGS_LINEAGE_MISSING',
                    'account.move', journal.record_id, 'account.move.line', cogs.record_id,
                    'missing_cogs_origin')),
                'COGS_LINEAGE_MISSING', 'Alokasi COGS ke invoice line belum tersedia',
                'Data Belum Lengkap', 'account.move', journal.record_id,
                journal.document_number, journal.state, 'account.move.line', cogs.record_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move', 'id', journal.record_id,
                    'number', journal.document_number, 'status', journal.state,
                    'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move.line', 'id', cogs.record_id,
                    'product', cogs.payload #>> '{product_id,name}',
                    'company_currency_value', cogs.payload ->> 'balance'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Journal entry', 'value', journal.document_number),
                    jsonb_build_object('label', 'COGS', 'value', cogs.payload ->> 'balance'),
                    jsonb_build_object('label', 'Invoice line relation', 'value', 'Tidak tersedia')
                ),
                'Lengkapi relasi cogs_origin_id; nilai ini tidak dialokasikan secara proporsional.',
                'Finance', 'Gross Profit', NULLIF(journal.payload ->> 'date', '')::date,
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', NULLIF(cogs.payload #>> '{product_id,id}', '')::bigint,
                    'account_id', :cogs_account_id,
                    'journal_id', NULLIF(journal.payload #>> '{journal_id,id}', '')::bigint,
                    'company_id', :company_id
                )), :detected_at
            FROM snapshot cogs
            JOIN snapshot journal
              ON journal.model = 'account.move'
             AND journal.record_id = NULLIF(cogs.payload #>> '{move_id,id}', '')::bigint
             AND journal.state = 'posted'
             AND NULLIF(journal.payload ->> 'date', '')::date >= :scope_start
             AND NULLIF(journal.payload ->> 'date', '')::date < :scope_end
            WHERE cogs.model = 'account.move.line'
              AND NULLIF(cogs.payload #>> '{account_id,id}', '')::bigint = :cogs_account_id
              AND cogs.payload #>> '{cogs_origin_id,id}' IS NULL
            ON CONFLICT DO NOTHING
        """),
        params,
    )

def _continue_line_lineage(conn: Any, params: Mapping[str, Any]) -> dict[str, int]:
    # Stock move -> Sales/Purchase line uses native many2one fields. The two
    # targets share the same conversion formula, so one UNION keeps it boring.
    conn.execute(
        text("""
            WITH relation AS (
                SELECT
                    move.record_id AS move_id,
                    move.payload,
                    'SO_MOVE_TO_LINE'::text AS relationship_type,
                    'sale.order.line'::text AS target_model,
                    NULLIF(move.payload #>> '{sale_line_id,id}', '')::bigint AS target_id,
                    'sale.order'::text AS target_document_model,
                    'product_uom_qty'::text AS target_quantity_field,
                    'product_uom'::text AS target_uom_field,
                    'order_id'::text AS target_document_field
                FROM ct_native_record_snapshot move
                WHERE move.extraction_run_id = CAST(:run_id AS UUID)
                  AND move.model = 'stock.move'
                  AND move.payload #>> '{sale_line_id,id}' IS NOT NULL
                UNION ALL
                SELECT
                    move.record_id, move.payload, 'PO_MOVE_TO_LINE', 'purchase.order.line',
                    NULLIF(move.payload #>> '{purchase_line_id,id}', '')::bigint,
                    'purchase.order', 'product_qty', 'product_uom', 'order_id'
                FROM ct_native_record_snapshot move
                WHERE move.extraction_run_id = CAST(:run_id AS UUID)
                  AND move.model = 'stock.move'
                  AND move.payload #>> '{purchase_line_id,id}' IS NOT NULL
            ), resolved AS (
                SELECT
                    relation.*,
                    target.payload AS target_payload,
                    NULLIF(relation.payload #>> '{picking_id,id}', '')::bigint AS picking_id,
                    NULLIF(relation.payload #>> '{product_id,id}', '')::bigint AS source_product_id,
                    NULLIF(target.payload #>> '{product_id,id}', '')::bigint AS target_product_id,
                    NULLIF(relation.payload #>> '{product_uom,id}', '')::bigint AS source_uom_id,
                    CASE
                        WHEN target_uom_field = 'product_uom'
                        THEN NULLIF(target.payload #>> '{product_uom,id}', '')::bigint
                    END AS target_uom_id,
                    NULLIF(relation.payload ->> 'quantity', '')::numeric AS source_quantity,
                    CASE
                        WHEN target_quantity_field = 'product_uom_qty'
                        THEN NULLIF(target.payload ->> 'product_uom_qty', '')::numeric
                        ELSE NULLIF(target.payload ->> 'product_qty', '')::numeric
                    END AS target_quantity,
                    NULLIF(target.payload #>> '{order_id,id}', '')::bigint AS target_document_id
                FROM relation
                JOIN ct_native_record_snapshot target
                  ON target.extraction_run_id = CAST(:run_id AS UUID)
                 AND target.model = relation.target_model
                 AND target.record_id = relation.target_id
            ), converted AS (
                SELECT
                    resolved.*,
                    NULLIF(source_uom.payload ->> 'factor', '')::numeric AS source_factor,
                    NULLIF(target_uom.payload ->> 'factor', '')::numeric AS target_factor,
                    NULLIF(target_uom.payload ->> 'rounding', '')::numeric AS target_rounding,
                    source_uom.payload #>> '{category_id,id}' AS source_category,
                    target_uom.payload #>> '{category_id,id}' AS target_category
                FROM resolved
                LEFT JOIN ct_native_record_snapshot source_uom
                  ON source_uom.extraction_run_id = CAST(:run_id AS UUID)
                 AND source_uom.model = 'uom.uom'
                 AND source_uom.record_id = resolved.source_uom_id
                LEFT JOIN ct_native_record_snapshot target_uom
                  ON target_uom.extraction_run_id = CAST(:run_id AS UUID)
                 AND target_uom.model = 'uom.uom'
                 AND target_uom.record_id = resolved.target_uom_id
            )
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id, source_quantity,
                target_quantity, source_uom_id, target_uom_id, source_quantity_reference,
                target_quantity_reference, uom_rounding, quantity_difference,
                lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), relationship_type, 'stock.move', move_id,
                target_model, target_id, 'stock.picking', picking_id,
                target_document_model, target_document_id, source_product_id,
                source_quantity, target_quantity, source_uom_id, target_uom_id,
                CASE WHEN source_factor <> 0 THEN source_quantity / source_factor END,
                CASE WHEN target_factor <> 0 THEN target_quantity / target_factor END,
                CASE WHEN target_factor <> 0 THEN target_rounding / target_factor END,
                CASE
                    WHEN source_factor <> 0 AND target_factor <> 0
                    THEN (source_quantity / source_factor) - (target_quantity / target_factor)
                END,
                CASE
                    WHEN source_product_id IS DISTINCT FROM target_product_id
                      OR source_factor IS NULL OR target_factor IS NULL
                      OR source_factor = 0 OR target_factor = 0
                      OR source_category IS DISTINCT FROM target_category
                    THEN 'INCOMPLETE'
                    ELSE 'PROVEN'
                END,
                jsonb_build_object(
                    'native_field', CASE relationship_type
                        WHEN 'SO_MOVE_TO_LINE' THEN 'stock.move.sale_line_id'
                        ELSE 'stock.move.purchase_line_id'
                    END,
                    'move_state', payload ->> 'state'
                )
            FROM converted
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    # Vendor Bill line -> Purchase Order line.
    conn.execute(
        text("""
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id, source_quantity,
                target_quantity, source_uom_id, target_uom_id, lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), 'BILL_LINE_TO_PO_LINE', 'account.move.line', aml.record_id,
                'purchase.order.line', pol.record_id, 'account.move',
                NULLIF(aml.payload #>> '{move_id,id}', '')::bigint, 'purchase.order',
                NULLIF(pol.payload #>> '{order_id,id}', '')::bigint,
                NULLIF(aml.payload #>> '{product_id,id}', '')::bigint,
                NULLIF(aml.payload ->> 'quantity', '')::numeric,
                NULLIF(pol.payload ->> 'product_qty', '')::numeric,
                NULLIF(aml.payload #>> '{product_uom_id,id}', '')::bigint,
                NULLIF(pol.payload #>> '{product_uom,id}', '')::bigint,
                CASE
                    WHEN aml.payload #>> '{product_id,id}' IS DISTINCT FROM pol.payload #>> '{product_id,id}'
                    THEN 'INCOMPLETE' ELSE 'PROVEN'
                END,
                jsonb_build_object('native_field', 'account.move.line.purchase_line_id')
            FROM ct_native_record_snapshot aml
            JOIN ct_native_record_snapshot move
              ON move.extraction_run_id = aml.extraction_run_id
             AND move.model = 'account.move'
             AND move.record_id = NULLIF(aml.payload #>> '{move_id,id}', '')::bigint
             AND move.payload ->> 'move_type' IN ('in_invoice', 'in_refund')
            JOIN ct_native_record_snapshot pol
              ON pol.extraction_run_id = aml.extraction_run_id
             AND pol.model = 'purchase.order.line'
             AND pol.record_id = NULLIF(aml.payload #>> '{purchase_line_id,id}', '')::bigint
            WHERE aml.extraction_run_id = CAST(:run_id AS UUID)
              AND aml.model = 'account.move.line'
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    # Approval Procurement line -> PO line. The absent RKB -> Approval
    # Procurement relation is intentionally not reconstructed here.
    conn.execute(
        text("""
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id, source_quantity,
                target_quantity, source_uom_id, target_uom_id, lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), 'APPROVAL_LINE_TO_PO_LINE',
                'approval.product.line', line.record_id, 'purchase.order.line', pol.record_id,
                'approval.request', NULLIF(line.payload #>> '{approval_request_id,id}', '')::bigint,
                'purchase.order', NULLIF(pol.payload #>> '{order_id,id}', '')::bigint,
                NULLIF(line.payload #>> '{product_id,id}', '')::bigint,
                NULLIF(line.payload ->> 'quantity', '')::numeric,
                NULLIF(pol.payload ->> 'product_qty', '')::numeric,
                NULLIF(line.payload #>> '{product_uom_id,id}', '')::bigint,
                NULLIF(pol.payload #>> '{product_uom,id}', '')::bigint,
                CASE
                    WHEN line.payload #>> '{product_id,id}' IS DISTINCT FROM pol.payload #>> '{product_id,id}'
                    THEN 'INCOMPLETE' ELSE 'PROVEN'
                END,
                jsonb_build_object('native_field', 'approval.product.line.purchase_order_line_id')
            FROM ct_native_record_snapshot line
            JOIN ct_native_record_snapshot pol
              ON pol.extraction_run_id = line.extraction_run_id
             AND pol.model = 'purchase.order.line'
             AND pol.record_id = NULLIF(line.payload #>> '{purchase_order_line_id,id}', '')::bigint
            WHERE line.extraction_run_id = CAST(:run_id AS UUID)
              AND line.model = 'approval.product.line'
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    # COGS line -> invoice line and valuation -> stock/account lines retain the
    # monetary evidence used by realized GP without proportional allocation.
    conn.execute(
        text("""
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id,
                company_currency_value, lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), 'COGS_LINE_TO_INVOICE_LINE', 'account.move.line', cogs.record_id,
                'account.move.line', invoice_line.record_id, 'account.move',
                NULLIF(cogs.payload #>> '{move_id,id}', '')::bigint, 'account.move',
                NULLIF(invoice_line.payload #>> '{move_id,id}', '')::bigint,
                NULLIF(cogs.payload #>> '{product_id,id}', '')::bigint,
                NULLIF(cogs.payload ->> 'balance', '')::numeric, 'PROVEN',
                jsonb_build_object('native_field', 'account.move.line.cogs_origin_id')
            FROM ct_native_record_snapshot cogs
            JOIN ct_native_record_snapshot invoice_line
              ON invoice_line.extraction_run_id = cogs.extraction_run_id
             AND invoice_line.model = 'account.move.line'
             AND invoice_line.record_id = NULLIF(cogs.payload #>> '{cogs_origin_id,id}', '')::bigint
            WHERE cogs.extraction_run_id = CAST(:run_id AS UUID)
              AND cogs.model = 'account.move.line'
            ON CONFLICT DO NOTHING
        """),
        params,
    )
    conn.execute(
        text("""
            INSERT INTO ct_line_lineage (
                extraction_run_id, relationship_type, source_model, source_id,
                target_model, target_id, source_document_model, source_document_id,
                target_document_model, target_document_id, product_id,
                source_quantity, company_currency_value, lineage_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), relation.relationship_type,
                'stock.valuation.layer', valuation.record_id, relation.target_model,
                relation.target_id, 'account.move',
                NULLIF(valuation.payload #>> '{account_move_id,id}', '')::bigint,
                relation.target_document_model, relation.target_document_id,
                NULLIF(valuation.payload #>> '{product_id,id}', '')::bigint,
                NULLIF(valuation.payload ->> 'quantity', '')::numeric,
                NULLIF(valuation.payload ->> 'value', '')::numeric,
                'PROVEN', jsonb_build_object('native_field', relation.native_field)
            FROM ct_native_record_snapshot valuation
            CROSS JOIN LATERAL (
                VALUES
                    ('VALUATION_TO_STOCK_MOVE'::text, 'stock.move'::text,
                     NULLIF(valuation.payload #>> '{stock_move_id,id}', '')::bigint,
                     'stock.picking'::text, NULL::bigint, 'stock.valuation.layer.stock_move_id'::text),
                    ('VALUATION_TO_ACCOUNT_LINE'::text, 'account.move.line'::text,
                     NULLIF(valuation.payload #>> '{account_move_line_id,id}', '')::bigint,
                     'account.move'::text, NULL::bigint, 'stock.valuation.layer.account_move_line_id'::text)
            ) relation(
                relationship_type, target_model, target_id,
                target_document_model, target_document_id, native_field
            )
            WHERE valuation.extraction_run_id = CAST(:run_id AS UUID)
              AND valuation.model = 'stock.valuation.layer'
              AND relation.target_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    rows = conn.execute(
        text("""
            SELECT lineage_status, COUNT(*) AS count
            FROM ct_line_lineage
            WHERE extraction_run_id = CAST(:run_id AS UUID)
            GROUP BY lineage_status
        """),
        params,
    ).mappings().all()
    return {str(row["lineage_status"]): int(row["count"]) for row in rows}


def rebuild_document_search(
    conn: Any,
    *,
    run_id: str,
    company_id: int,
) -> int:
    """Index every synchronized business document, not only documents with findings."""
    params = {"run_id": run_id, "company_id": company_id}
    conn.execute(
        text("DELETE FROM ct_document_search WHERE extraction_run_id = CAST(:run_id AS UUID)"),
        params,
    )
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT *
                FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), line_context AS (
                SELECT parent_model, parent_id,
                       STRING_AGG(DISTINCT context, ' ') FILTER (WHERE context <> '') AS context
                FROM (
                    SELECT
                        'sale.order'::text AS parent_model,
                        NULLIF(line.payload #>> '{order_id,id}', '')::bigint AS parent_id,
                        CONCAT_WS(' ', line.payload #>> '{product_id,name}', line.payload ->> 'name') AS context
                    FROM snapshot line WHERE line.model = 'sale.order.line'
                    UNION ALL
                    SELECT
                        'purchase.order', NULLIF(line.payload #>> '{order_id,id}', '')::bigint,
                        CONCAT_WS(' ', line.payload #>> '{product_id,name}', line.payload ->> 'name')
                    FROM snapshot line WHERE line.model = 'purchase.order.line'
                    UNION ALL
                    SELECT
                        'approval.request', NULLIF(line.payload #>> '{approval_request_id,id}', '')::bigint,
                        CONCAT_WS(' ', line.payload #>> '{product_id,name}', line.payload ->> 'description')
                    FROM snapshot line WHERE line.model = 'approval.product.line'
                    UNION ALL
                    SELECT
                        'stock.picking', NULLIF(line.payload #>> '{picking_id,id}', '')::bigint,
                        CONCAT_WS(' ', line.payload #>> '{product_id,name}', line.payload ->> 'name')
                    FROM snapshot line WHERE line.model = 'stock.move'
                    UNION ALL
                    SELECT
                        'account.move', NULLIF(line.payload #>> '{move_id,id}', '')::bigint,
                        CONCAT_WS(' ', line.payload #>> '{product_id,name}', line.payload ->> 'name')
                    FROM snapshot line WHERE line.model = 'account.move.line'
                ) lines
                WHERE parent_id IS NOT NULL
                GROUP BY parent_model, parent_id
            ), documents AS (
                SELECT
                    item.*,
                    picking_type.payload ->> 'code' AS picking_code,
                    COALESCE(line_context.context, '') AS line_context,
                    CASE
                        WHEN item.model = 'sale.order' THEN 'SO'
                        WHEN item.model = 'mrp.production' THEN 'MO'
                        WHEN item.model = 'purchase.order' THEN 'PO'
                        WHEN item.model = 'approval.request'
                             AND UPPER(COALESCE(item.payload #>> '{category_id,name}', '')) = 'RKB'
                            THEN 'RKB'
                        WHEN item.model = 'approval.request'
                             AND UPPER(COALESCE(item.payload #>> '{category_id,name}', '')) = 'PEMBELIAN'
                            THEN 'ROP'
                        WHEN item.model = 'approval.request' THEN 'IO'
                        WHEN item.model = 'stock.picking'
                             AND picking_type.payload ->> 'code' = 'incoming' THEN 'Receipt/LPB'
                        WHEN item.model = 'stock.picking'
                             AND picking_type.payload ->> 'code' = 'outgoing' THEN 'Delivery'
                        WHEN item.model = 'stock.picking' THEN 'Transfer'
                        WHEN item.model = 'account.move'
                             AND item.payload ->> 'move_type' IN ('out_invoice', 'out_refund') THEN 'Invoice'
                        WHEN item.model = 'account.move'
                             AND item.payload ->> 'move_type' IN ('in_invoice', 'in_refund') THEN 'Vendor Bill'
                        WHEN item.model = 'account.payment' THEN 'Payment'
                    END AS document_type,
                    CASE
                        WHEN item.model = 'sale.order'
                            THEN NULLIF(item.payload ->> 'date_order', '')::date
                        WHEN item.model = 'mrp.production'
                            THEN COALESCE(
                                NULLIF(item.payload ->> 'date_finished', '')::date,
                                NULLIF(item.payload ->> 'date_start', '')::date
                            )
                        WHEN item.model = 'purchase.order'
                            THEN NULLIF(item.payload ->> 'date_order', '')::date
                        WHEN item.model = 'approval.request'
                            THEN NULLIF(item.payload ->> 'date_confirmed', '')::date
                        WHEN item.model = 'stock.picking'
                            THEN COALESCE(
                                NULLIF(item.payload ->> 'date_done', '')::date,
                                NULLIF(item.payload ->> 'scheduled_date', '')::date
                            )
                        WHEN item.model = 'account.move'
                            THEN COALESCE(
                                NULLIF(item.payload ->> 'invoice_date', '')::date,
                                NULLIF(item.payload ->> 'date', '')::date
                            )
                        WHEN item.model = 'account.payment'
                            THEN NULLIF(item.payload ->> 'date', '')::date
                    END AS business_date,
                    CASE
                        WHEN item.model = 'sale.order' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{partner_id,name}', item.payload #>> '{project_id,name}'
                        )
                        WHEN item.model = 'purchase.order' THEN item.payload #>> '{partner_id,name}'
                        WHEN item.model = 'mrp.production' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{product_id,name}', item.payload ->> 'origin'
                        )
                        WHEN item.model = 'approval.request' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{request_owner_id,name}', item.payload ->> 'x_studio_project',
                            item.payload #>> '{x_studio_nomor_jo,name}', item.payload #>> '{x_studio_nomor_io,name}'
                        )
                        WHEN item.model = 'stock.picking' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{partner_id,name}', item.payload ->> 'origin'
                        )
                        WHEN item.model = 'account.move' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{partner_id,name}', item.payload ->> 'invoice_origin'
                        )
                        WHEN item.model = 'account.payment' THEN CONCAT_WS(
                            ' / ', item.payload #>> '{partner_id,name}', item.payload #>> '{journal_id,name}'
                        )
                    END AS secondary_text
                FROM snapshot item
                LEFT JOIN snapshot picking_type
                  ON picking_type.model = 'stock.picking.type'
                 AND picking_type.record_id = NULLIF(item.payload #>> '{picking_type_id,id}', '')::bigint
                LEFT JOIN line_context
                  ON line_context.parent_model = item.model
                 AND line_context.parent_id = item.record_id
                WHERE item.model IN (
                    'sale.order', 'mrp.production', 'purchase.order', 'approval.request',
                    'stock.picking', 'account.move', 'account.payment'
                )
            )
            INSERT INTO ct_document_search (
                extraction_run_id, company_id, document_type, model, record_id,
                document_number, native_state, business_date, secondary_text,
                search_text, active_finding_count
            )
            SELECT
                CAST(:run_id AS UUID), :company_id, document_type, model, record_id,
                document_number, state, business_date, NULLIF(secondary_text, ''),
                LOWER(CONCAT_WS(' ', document_number, secondary_text, line_context)),
                (
                    SELECT COUNT(*)
                    FROM ct_finding finding
                    WHERE finding.lifecycle_state = 'ACTIVE'
                      AND finding.primary_document_model = documents.model
                      AND finding.primary_document_id = documents.record_id
                )
            FROM documents
            WHERE document_type IS NOT NULL
              AND (company_id = :company_id OR company_id IS NULL)
            ON CONFLICT (extraction_run_id, model, record_id) DO UPDATE SET
                company_id = EXCLUDED.company_id,
                document_type = EXCLUDED.document_type,
                document_number = EXCLUDED.document_number,
                native_state = EXCLUDED.native_state,
                business_date = EXCLUDED.business_date,
                secondary_text = EXCLUDED.secondary_text,
                search_text = EXCLUDED.search_text,
                active_finding_count = EXCLUDED.active_finding_count
        """),
        params,
    )
    return int(
        conn.execute(
            text("""
                SELECT COUNT(*) FROM ct_document_search
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            """),
            params,
        ).scalar_one()
    )


def _validated_cogs_account_id(conn: Any, *, run_id: str) -> int:
    rows = conn.execute(
        text("""
            SELECT record_id, payload ->> 'name' AS name
            FROM ct_native_record_snapshot
            WHERE extraction_run_id = CAST(:run_id AS UUID)
              AND model = 'account.account'
              AND payload ->> 'code' = :code
              AND COALESCE((payload ->> 'deprecated')::boolean, FALSE) = FALSE
        """),
        {"run_id": run_id, "code": COGS_ACCOUNT_CODE},
    ).mappings().all()
    if len(rows) != 1 or str(rows[0]["name"]) != COGS_ACCOUNT_NAME:
        raise ValueError(
            f"Akun COGS {COGS_ACCOUNT_CODE} tidak dapat divalidasi secara unik."
        )
    return int(rows[0]["record_id"])


def rebuild_gross_profit(
    conn: Any,
    *,
    run_id: str,
    company_id: int,
) -> dict[str, int]:
    """Reconcile SO-level GP; line GP exists only for direct, unique lineage."""
    cogs_account_id = _validated_cogs_account_id(conn, run_id=run_id)
    params = {
        "run_id": run_id,
        "company_id": company_id,
        "cogs_account_id": cogs_account_id,
    }
    conn.execute(
        text("""
            INSERT INTO ct_product_cost_classification (
                company_id, product_id, classification, source, updated_at
            )
            SELECT :company_id, product.record_id,
                   CASE product.payload ->> 'type'
                       WHEN 'service' THEN 'Jasa Eksternal'
                       WHEN 'consu' THEN 'Material'
                       ELSE 'Belum Terkategori'
                   END,
                   'AUTO', NOW()
            FROM ct_native_record_snapshot product
            WHERE product.extraction_run_id = CAST(:run_id AS UUID)
              AND product.model = 'product.product'
            ON CONFLICT (company_id, product_id) DO UPDATE SET
                classification = EXCLUDED.classification,
                updated_at = EXCLUDED.updated_at
            WHERE ct_product_cost_classification.source = 'AUTO'
        """),
        params,
    )
    conn.execute(
        text("DELETE FROM ct_gp_line WHERE extraction_run_id = CAST(:run_id AS UUID)"),
        params,
    )
    conn.execute(
        text("DELETE FROM ct_gp_summary WHERE extraction_run_id = CAST(:run_id AS UUID)"),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), invoice_relation AS (
                SELECT
                    invoice_line.record_id AS invoice_line_id,
                    invoice_line.payload,
                    move.record_id AS invoice_id,
                    move.payload ->> 'move_type' AS move_type,
                    sale_line.record_id AS sale_line_id,
                    NULLIF(sale_line.payload #>> '{order_id,id}', '')::bigint AS sale_order_id,
                    COUNT(*) OVER (PARTITION BY invoice_line.record_id) AS relation_count
                FROM snapshot invoice_line
                JOIN snapshot move
                  ON move.model = 'account.move'
                 AND move.record_id = NULLIF(invoice_line.payload #>> '{move_id,id}', '')::bigint
                 AND move.state = 'posted'
                 AND move.payload ->> 'move_type' IN ('out_invoice', 'out_refund')
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    COALESCE(invoice_line.payload -> 'sale_line_ids', '[]'::jsonb)
                ) relation(sale_line_id)
                JOIN snapshot sale_line
                  ON sale_line.model = 'sale.order.line'
                 AND sale_line.record_id = relation.sale_line_id::bigint
                 AND COALESCE((sale_line.payload ->> 'is_downpayment')::boolean, FALSE) = FALSE
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(invoice_line.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' = 'consu'
                WHERE invoice_line.model = 'account.move.line'
                  AND COALESCE(invoice_line.payload ->> 'display_type', 'product') = 'product'
            ), unique_line AS (
                SELECT *
                FROM invoice_relation
                WHERE relation_count = 1
            ), cogs AS (
                SELECT
                    NULLIF(cogs.payload #>> '{cogs_origin_id,id}', '')::bigint AS invoice_line_id,
                    SUM(NULLIF(cogs.payload ->> 'balance', '')::numeric) AS cogs_idr,
                    JSONB_AGG(cogs.record_id ORDER BY cogs.record_id) AS cogs_line_ids
                FROM snapshot cogs
                JOIN snapshot journal_move
                  ON journal_move.model = 'account.move'
                 AND journal_move.record_id = NULLIF(cogs.payload #>> '{move_id,id}', '')::bigint
                 AND journal_move.state = 'posted'
                WHERE cogs.model = 'account.move.line'
                  AND NULLIF(cogs.payload #>> '{account_id,id}', '')::bigint = :cogs_account_id
                  AND cogs.payload #>> '{cogs_origin_id,id}' IS NOT NULL
                GROUP BY NULLIF(cogs.payload #>> '{cogs_origin_id,id}', '')::bigint
            )
            INSERT INTO ct_gp_line (
                extraction_run_id, sale_order_id, sale_order_line_id, invoice_line_id,
                product_id, quantity, revenue_idr, cogs_idr, gross_profit_idr,
                allocation_status, evidence
            )
            SELECT
                CAST(:run_id AS UUID), line.sale_order_id, line.sale_line_id,
                line.invoice_line_id, NULLIF(line.payload #>> '{product_id,id}', '')::bigint,
                NULLIF(line.payload ->> 'quantity', '')::numeric,
                -NULLIF(line.payload ->> 'balance', '')::numeric,
                cogs.cogs_idr,
                CASE
                    WHEN cogs.invoice_line_id IS NOT NULL
                    THEN -NULLIF(line.payload ->> 'balance', '')::numeric - cogs.cogs_idr
                END,
                CASE WHEN cogs.invoice_line_id IS NULL THEN 'MISSING_COGS' ELSE 'PROVEN' END,
                jsonb_build_object(
                    'invoice_id', line.invoice_id,
                    'invoice_move_type', line.move_type,
                    'cogs_line_ids', COALESCE(cogs.cogs_line_ids, '[]'::jsonb),
                    'revenue_source', 'account.move.line.balance',
                    'cogs_source', 'account.move.line.cogs_origin_id'
                )
            FROM unique_line line
            LEFT JOIN cogs ON cogs.invoice_line_id = line.invoice_line_id
            ON CONFLICT (extraction_run_id, sale_order_line_id, invoice_line_id) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                revenue_idr = EXCLUDED.revenue_idr,
                cogs_idr = EXCLUDED.cogs_idr,
                gross_profit_idr = EXCLUDED.gross_profit_idr,
                allocation_status = EXCLUDED.allocation_status,
                evidence = EXCLUDED.evidence
        """),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), company AS (
                SELECT NULLIF(payload #>> '{currency_id,id}', '')::bigint AS currency_id
                FROM snapshot WHERE model = 'res.company' AND record_id = :company_id
            ), so_base AS (
                SELECT
                    so.record_id AS sale_order_id,
                    so.document_number,
                    so.state,
                    NULLIF(so.payload ->> 'date_order', '')::date AS business_date,
                    NULLIF(so.payload #>> '{currency_id,id}', '')::bigint AS currency_id,
                    NULLIF(so.payload ->> 'amount_untaxed', '')::numeric AS amount_untaxed
                FROM snapshot so
                WHERE so.model = 'sale.order'
            ), so_converted AS (
                SELECT
                    so.*,
                    CASE
                        WHEN so.currency_id = company.currency_id THEN so.amount_untaxed
                        WHEN rate.company_rate > 0 THEN so.amount_untaxed / rate.company_rate
                    END AS planned_revenue_idr
                FROM so_base so
                CROSS JOIN company
                LEFT JOIN LATERAL (
                    SELECT NULLIF(rate.payload ->> 'company_rate', '')::numeric AS company_rate
                    FROM snapshot rate
                    WHERE rate.model = 'res.currency.rate'
                      AND NULLIF(rate.payload #>> '{currency_id,id}', '')::bigint = so.currency_id
                      AND (rate.payload #>> '{company_id,id}' IS NULL
                           OR NULLIF(rate.payload #>> '{company_id,id}', '')::bigint = :company_id)
                      AND NULLIF(rate.payload ->> 'name', '')::date <= so.business_date
                    ORDER BY NULLIF(rate.payload ->> 'name', '')::date DESC
                    LIMIT 1
                ) rate ON TRUE
            ), rkb_line AS (
                SELECT
                    NULLIF(line.payload #>> '{x_studio_nomor_jo,id}', '')::bigint AS sale_order_id,
                    NULLIF(line.payload ->> 'x_studio_subtotal', '')::numeric AS subtotal,
                    COALESCE(
                        NULLIF(line.payload #>> '{x_currency_id,id}', '')::bigint,
                        NULLIF(header.payload #>> '{x_currency_id,id}', '')::bigint
                    ) AS currency_id,
                    NULLIF(header.payload ->> 'date_confirmed', '')::date AS business_date
                FROM snapshot line
                JOIN snapshot header
                  ON header.model = 'approval.request'
                 AND header.record_id = NULLIF(line.payload #>> '{approval_request_id,id}', '')::bigint
                 AND UPPER(COALESCE(header.payload #>> '{category_id,name}', '')) = 'RKB'
                WHERE line.model = 'approval.product.line'
                  AND line.payload #>> '{x_studio_nomor_jo,id}' IS NOT NULL
            ), rkb_converted AS (
                SELECT
                    line.sale_order_id,
                    CASE
                        WHEN line.currency_id = company.currency_id THEN line.subtotal
                        WHEN rate.company_rate > 0 THEN line.subtotal / rate.company_rate
                    END AS subtotal_idr,
                    line.subtotal IS NOT NULL
                      AND line.business_date IS NOT NULL
                      AND (line.currency_id = company.currency_id OR rate.company_rate > 0) AS complete
                FROM rkb_line line
                CROSS JOIN company
                LEFT JOIN LATERAL (
                    SELECT NULLIF(rate.payload ->> 'company_rate', '')::numeric AS company_rate
                    FROM snapshot rate
                    WHERE rate.model = 'res.currency.rate'
                      AND NULLIF(rate.payload #>> '{currency_id,id}', '')::bigint = line.currency_id
                      AND (rate.payload #>> '{company_id,id}' IS NULL
                           OR NULLIF(rate.payload #>> '{company_id,id}', '')::bigint = :company_id)
                      AND NULLIF(rate.payload ->> 'name', '')::date <= line.business_date
                    ORDER BY NULLIF(rate.payload ->> 'name', '')::date DESC
                    LIMIT 1
                ) rate ON TRUE
            ), rkb AS (
                SELECT
                    sale_order_id, SUM(subtotal_idr) AS rkb_idr,
                    COUNT(*) AS line_count, BOOL_AND(complete) AS complete
                FROM rkb_converted GROUP BY sale_order_id
            ), revenue_relation AS (
                SELECT
                    invoice_line.record_id AS invoice_line_id,
                    -NULLIF(invoice_line.payload ->> 'balance', '')::numeric AS revenue_idr,
                    ARRAY_AGG(DISTINCT NULLIF(sol.payload #>> '{order_id,id}', '')::bigint) AS sale_orders
                FROM snapshot invoice_line
                JOIN snapshot move
                  ON move.model = 'account.move'
                 AND move.record_id = NULLIF(invoice_line.payload #>> '{move_id,id}', '')::bigint
                 AND move.state = 'posted'
                 AND move.payload ->> 'move_type' IN ('out_invoice', 'out_refund')
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    COALESCE(invoice_line.payload -> 'sale_line_ids', '[]'::jsonb)
                ) relation(sale_line_id)
                JOIN snapshot sol
                  ON sol.model = 'sale.order.line'
                 AND sol.record_id = relation.sale_line_id::bigint
                 AND COALESCE((sol.payload ->> 'is_downpayment')::boolean, FALSE) = FALSE
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(invoice_line.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' = 'consu'
                WHERE invoice_line.model = 'account.move.line'
                  AND COALESCE(invoice_line.payload ->> 'display_type', 'product') = 'product'
                GROUP BY invoice_line.record_id, invoice_line.payload
            ), revenue AS (
                SELECT sale_orders[1] AS sale_order_id, SUM(revenue_idr) AS revenue_idr,
                       COUNT(*) AS invoice_line_count
                FROM revenue_relation
                WHERE CARDINALITY(sale_orders) = 1
                GROUP BY sale_orders[1]
            ), ambiguous_revenue AS (
                SELECT sale_order_id, COUNT(*) AS invoice_line_count
                FROM revenue_relation relation
                CROSS JOIN LATERAL unnest(relation.sale_orders) sale_order_id
                WHERE CARDINALITY(relation.sale_orders) > 1
                GROUP BY sale_order_id
            ), cogs AS (
                SELECT
                    relation.sale_orders[1] AS sale_order_id,
                    SUM(NULLIF(cogs.payload ->> 'balance', '')::numeric) AS cogs_idr,
                    COUNT(*) AS cogs_line_count
                FROM snapshot cogs
                JOIN snapshot journal_move
                  ON journal_move.model = 'account.move'
                 AND journal_move.record_id = NULLIF(cogs.payload #>> '{move_id,id}', '')::bigint
                 AND journal_move.state = 'posted'
                JOIN revenue_relation relation
                  ON relation.invoice_line_id = NULLIF(cogs.payload #>> '{cogs_origin_id,id}', '')::bigint
                 AND CARDINALITY(relation.sale_orders) = 1
                WHERE cogs.model = 'account.move.line'
                  AND NULLIF(cogs.payload #>> '{account_id,id}', '')::bigint = :cogs_account_id
                GROUP BY relation.sale_orders[1]
            )
            INSERT INTO ct_gp_summary (
                extraction_run_id, sale_order_id, sale_order_number,
                planned_revenue_idr, planned_rkb_idr, planned_gp_idr, planned_margin,
                realized_revenue_idr, realized_cogs_idr, realized_gp_idr, realized_margin,
                planned_status, realized_status, limitations, calculated_at
            )
            SELECT
                CAST(:run_id AS UUID), so.sale_order_id, so.document_number,
                so.planned_revenue_idr, rkb.rkb_idr,
                CASE WHEN so.planned_revenue_idr IS NOT NULL AND rkb.complete
                     THEN so.planned_revenue_idr - rkb.rkb_idr END,
                CASE WHEN so.planned_revenue_idr <> 0 AND rkb.complete
                     THEN (so.planned_revenue_idr - rkb.rkb_idr) / so.planned_revenue_idr END,
                CASE WHEN ambiguous.sale_order_id IS NULL THEN revenue.revenue_idr END,
                CASE WHEN ambiguous.sale_order_id IS NULL THEN cogs.cogs_idr END,
                CASE WHEN ambiguous.sale_order_id IS NULL
                           AND revenue.revenue_idr IS NOT NULL AND cogs.cogs_idr IS NOT NULL
                      THEN revenue.revenue_idr - cogs.cogs_idr END,
                CASE WHEN ambiguous.sale_order_id IS NULL
                           AND revenue.revenue_idr <> 0 AND cogs.cogs_idr IS NOT NULL
                      THEN (revenue.revenue_idr - cogs.cogs_idr) / revenue.revenue_idr END,
                CASE
                    WHEN so.planned_revenue_idr IS NULL THEN 'INCOMPLETE_CURRENCY'
                    WHEN rkb.sale_order_id IS NULL THEN 'INCOMPLETE_RKB_RELATION'
                    WHEN NOT rkb.complete THEN 'INCOMPLETE_RKB_VALUE'
                    ELSE 'COMPLETE'
                END,
                CASE
                    WHEN ambiguous.sale_order_id IS NOT NULL THEN 'INCOMPLETE_REVENUE_ALLOCATION'
                    WHEN revenue.sale_order_id IS NULL THEN 'NOT_REALIZED'
                    WHEN cogs.sale_order_id IS NULL THEN 'INCOMPLETE_COGS_RELATION'
                    ELSE 'COMPLETE'
                END,
                to_jsonb(array_remove(ARRAY[
                    CASE WHEN so.planned_revenue_idr IS NULL THEN 'Kurs SO pada tanggal bisnis tidak tersedia.' END,
                    CASE WHEN rkb.sale_order_id IS NULL THEN 'Relasi RKB langsung ke SO tidak tersedia.' END,
                    CASE WHEN rkb.sale_order_id IS NOT NULL AND NOT rkb.complete
                         THEN 'Nilai, tanggal bisnis, atau kurs RKB belum lengkap.' END,
                    CASE WHEN revenue.sale_order_id IS NOT NULL AND cogs.sale_order_id IS NULL
                          THEN 'COGS belum dapat direkonsiliasi ke invoice line.' END,
                    CASE WHEN ambiguous.sale_order_id IS NOT NULL
                          THEN 'Invoice line terkait ke lebih dari satu Sales Order dan tidak dialokasikan.' END
                ]::text[], NULL)),
                NOW()
            FROM so_converted so
            LEFT JOIN rkb ON rkb.sale_order_id = so.sale_order_id
            LEFT JOIN revenue ON revenue.sale_order_id = so.sale_order_id
            LEFT JOIN cogs ON cogs.sale_order_id = so.sale_order_id
            LEFT JOIN ambiguous_revenue ambiguous ON ambiguous.sale_order_id = so.sale_order_id
            ON CONFLICT (extraction_run_id, sale_order_id) DO UPDATE SET
                sale_order_number = EXCLUDED.sale_order_number,
                planned_revenue_idr = EXCLUDED.planned_revenue_idr,
                planned_rkb_idr = EXCLUDED.planned_rkb_idr,
                planned_gp_idr = EXCLUDED.planned_gp_idr,
                planned_margin = EXCLUDED.planned_margin,
                realized_revenue_idr = EXCLUDED.realized_revenue_idr,
                realized_cogs_idr = EXCLUDED.realized_cogs_idr,
                realized_gp_idr = EXCLUDED.realized_gp_idr,
                realized_margin = EXCLUDED.realized_margin,
                planned_status = EXCLUDED.planned_status,
                realized_status = EXCLUDED.realized_status,
                limitations = EXCLUDED.limitations,
                calculated_at = EXCLUDED.calculated_at
        """),
        params,
    )

    return {
        "summaries": int(
            conn.execute(
                text("SELECT COUNT(*) FROM ct_gp_summary WHERE extraction_run_id = CAST(:run_id AS UUID)"),
                params,
            ).scalar_one()
        ),
        "proven_lines": int(
            conn.execute(
                text("""
                    SELECT COUNT(*) FROM ct_gp_line
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND allocation_status = 'PROVEN'
                """),
                params,
            ).scalar_one()
        ),
        "incomplete_lines": int(
            conn.execute(
                text("""
                    SELECT COUNT(*) FROM ct_gp_line
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND allocation_status <> 'PROVEN'
                """),
                params,
            ).scalar_one()
        ),
    }


def rebuild_finding_detections(
    conn: Any,
    *,
    run_id: str,
    company_id: int,
    scope_year: int = SCOPE_YEAR,
) -> dict[str, int]:
    """Evaluate the frozen v0.3 rules against one complete candidate run."""
    cogs_account_id = _validated_cogs_account_id(conn, run_id=run_id)
    params = {
        "run_id": run_id,
        "company_id": company_id,
        "scope_start": date(scope_year, 1, 1),
        "scope_end": date(scope_year + 1, 1, 1),
        "detected_at": datetime.now(timezone.utc),
        "cogs_account_id": cogs_account_id,
    }
    conn.execute(
        text("DELETE FROM ct_finding_detection WHERE extraction_run_id = CAST(:run_id AS UUID)"),
        params,
    )

    # Posted customer item invoice line without a native Sales Order line.
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), candidate AS (
                SELECT
                    line.record_id AS line_id,
                    line.payload AS line_payload,
                    move.record_id AS move_id,
                    move.document_number,
                    move.state,
                    move.payload AS move_payload,
                    product.record_id AS product_id,
                    product.payload #>> '{categ_id,id}' AS product_category_id,
                    EXISTS (
                        SELECT 1 FROM snapshot cogs
                        JOIN snapshot journal_move
                          ON journal_move.model = 'account.move'
                         AND journal_move.record_id = NULLIF(cogs.payload #>> '{move_id,id}', '')::bigint
                         AND journal_move.state = 'posted'
                        WHERE cogs.model = 'account.move.line'
                          AND NULLIF(cogs.payload #>> '{cogs_origin_id,id}', '')::bigint = line.record_id
                          AND NULLIF(cogs.payload #>> '{account_id,id}', '')::bigint = :cogs_account_id
                    ) AS impact_proven
                FROM snapshot line
                JOIN snapshot move
                  ON move.model = 'account.move'
                 AND move.record_id = NULLIF(line.payload #>> '{move_id,id}', '')::bigint
                 AND move.state = 'posted'
                 AND move.payload ->> 'move_type' IN ('out_invoice', 'out_refund')
                 AND COALESCE(
                    NULLIF(move.payload ->> 'invoice_date', '')::date,
                    NULLIF(move.payload ->> 'date', '')::date
                 ) >= :scope_start
                 AND COALESCE(
                    NULLIF(move.payload ->> 'invoice_date', '')::date,
                    NULLIF(move.payload ->> 'date', '')::date
                 ) < :scope_end
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(line.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' = 'consu'
                WHERE line.model = 'account.move.line'
                  AND COALESCE(line.payload ->> 'display_type', 'product') = 'product'
                  AND jsonb_array_length(COALESCE(line.payload -> 'sale_line_ids', '[]'::jsonb)) = 0
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID),
                MD5(CONCAT_WS('|', 'INV_ITEM_WITHOUT_SOL', 'account.move', move_id,
                              'account.move.line', line_id, 'missing_sale_line')),
                'INV_ITEM_WITHOUT_SOL', 'Item invoice tanpa Sales Order Line',
                CASE WHEN impact_proven THEN 'Masalah Aktif' ELSE 'Perlu Ditinjau' END,
                'account.move', move_id, document_number, state,
                'account.move.line', line_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move', 'id', move_id, 'number', document_number,
                    'status', state, 'type', 'Invoice', 'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'account.move.line', 'id', line_id,
                    'product', line_payload #>> '{product_id,name}',
                    'quantity', line_payload ->> 'quantity',
                    'uom', line_payload #>> '{product_uom_id,name}',
                    'untaxed_value', line_payload ->> 'price_subtotal'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Invoice', 'value', document_number),
                    jsonb_build_object('label', 'Customer', 'value', move_payload #>> '{partner_id,name}'),
                    jsonb_build_object('label', 'Product', 'value', line_payload #>> '{product_id,name}'),
                    jsonb_build_object('label', 'Dampak inventory/COGS', 'value', impact_proven)
                ),
                CASE WHEN impact_proven
                     THEN 'Periksa sumber pesanan dan koreksi hubungan dokumen bersama Finance dan Warehouse.'
                     ELSE 'Konfirmasi apakah item ini merupakan transaksi sah tanpa Sales Order.' END,
                'Finance', 'Invoice',
                COALESCE(
                    NULLIF(move_payload ->> 'invoice_date', '')::date,
                    NULLIF(move_payload ->> 'date', '')::date
                ),
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', product_id,
                    'product_category_id', NULLIF(product_category_id, '')::bigint,
                    'journal_id', NULLIF(move_payload #>> '{journal_id,id}', '')::bigint,
                    'company_id', :company_id
                )),
                :detected_at
            FROM candidate
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    # Customer stock-out and supplier receipt are classified from operation
    # code plus source/destination usage, never from names or origin text.
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), candidate AS (
                SELECT
                    move.record_id AS line_id,
                    move.payload AS line_payload,
                    picking.record_id AS picking_id,
                    picking.document_number,
                    move.state,
                    picking.payload AS picking_payload,
                    product.record_id AS product_id,
                    product.payload #>> '{categ_id,id}' AS product_category_id,
                    picking_type.record_id AS operation_type_id,
                    picking_type.payload ->> 'code' AS operation_code,
                    source_location.payload ->> 'usage' AS source_usage,
                    destination_location.payload ->> 'usage' AS destination_usage,
                    COALESCE(
                        NULLIF(picking.payload ->> 'date_done', '')::date,
                        NULLIF(move.payload ->> 'date', '')::date,
                        NULLIF(picking.payload ->> 'scheduled_date', '')::date
                    ) AS business_date
                FROM snapshot move
                JOIN snapshot picking
                  ON picking.model = 'stock.picking'
                 AND picking.record_id = NULLIF(move.payload #>> '{picking_id,id}', '')::bigint
                JOIN snapshot picking_type
                  ON picking_type.model = 'stock.picking.type'
                 AND picking_type.record_id = NULLIF(move.payload #>> '{picking_type_id,id}', '')::bigint
                JOIN snapshot source_location
                  ON source_location.model = 'stock.location'
                 AND source_location.record_id = NULLIF(move.payload #>> '{location_id,id}', '')::bigint
                JOIN snapshot destination_location
                  ON destination_location.model = 'stock.location'
                 AND destination_location.record_id = NULLIF(move.payload #>> '{location_dest_id,id}', '')::bigint
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(move.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' = 'consu'
                WHERE move.model = 'stock.move'
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID),
                MD5(CONCAT_WS('|', 'DELIVERY_WITHOUT_SOL', 'stock.picking', picking_id,
                              'stock.move', line_id, 'customer_stock_out')),
                'DELIVERY_WITHOUT_SOL', 'Delivery tanpa Sales Order Line', 'Masalah Aktif',
                'stock.picking', picking_id, document_number, state,
                'stock.move', line_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'stock.picking', 'id', picking_id, 'number', document_number,
                    'status', state, 'type', 'Delivery', 'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'stock.move', 'id', line_id,
                    'product', line_payload #>> '{product_id,name}',
                    'quantity', line_payload ->> 'quantity',
                    'uom', line_payload #>> '{product_uom,name}'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Delivery', 'value', document_number),
                    jsonb_build_object('label', 'Customer', 'value', picking_payload #>> '{partner_id,name}'),
                    jsonb_build_object('label', 'Product', 'value', line_payload #>> '{product_id,name}'),
                    jsonb_build_object('label', 'Operation type', 'value', picking_payload #>> '{picking_type_id,name}')
                ),
                'Periksa sumber pesanan dan koreksi hubungan Sales Order Line sebelum transaksi lanjutan.',
                'Warehouse', 'Delivery', business_date,
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', product_id,
                    'product_category_id', NULLIF(product_category_id, '')::bigint,
                    'operation_type_id', operation_type_id,
                    'company_id', :company_id
                )),
                :detected_at
            FROM candidate
            WHERE operation_code = 'outgoing'
              AND destination_usage = 'customer'
              AND source_usage <> 'customer'
              AND state = 'done'
              AND line_payload #>> '{sale_line_id,id}' IS NULL
              AND business_date >= :scope_start AND business_date < :scope_end
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), candidate AS (
                SELECT
                    move.record_id AS line_id,
                    move.payload AS line_payload,
                    picking.record_id AS picking_id,
                    picking.document_number,
                    move.state,
                    picking.payload AS picking_payload,
                    product.record_id AS product_id,
                    product.payload #>> '{categ_id,id}' AS product_category_id,
                    picking_type.record_id AS operation_type_id,
                    picking_type.payload ->> 'code' AS operation_code,
                    source_location.payload ->> 'usage' AS source_usage,
                    destination_location.payload ->> 'usage' AS destination_usage,
                    COALESCE(
                        NULLIF(picking.payload ->> 'date_done', '')::date,
                        NULLIF(move.payload ->> 'date', '')::date,
                        NULLIF(picking.payload ->> 'scheduled_date', '')::date
                    ) AS business_date
                FROM snapshot move
                JOIN snapshot picking
                  ON picking.model = 'stock.picking'
                 AND picking.record_id = NULLIF(move.payload #>> '{picking_id,id}', '')::bigint
                JOIN snapshot picking_type
                  ON picking_type.model = 'stock.picking.type'
                 AND picking_type.record_id = NULLIF(move.payload #>> '{picking_type_id,id}', '')::bigint
                JOIN snapshot source_location
                  ON source_location.model = 'stock.location'
                 AND source_location.record_id = NULLIF(move.payload #>> '{location_id,id}', '')::bigint
                JOIN snapshot destination_location
                  ON destination_location.model = 'stock.location'
                 AND destination_location.record_id = NULLIF(move.payload #>> '{location_dest_id,id}', '')::bigint
                JOIN snapshot product
                  ON product.model = 'product.product'
                 AND product.record_id = NULLIF(move.payload #>> '{product_id,id}', '')::bigint
                 AND product.payload ->> 'type' = 'consu'
                WHERE move.model = 'stock.move'
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID),
                MD5(CONCAT_WS('|', 'RECEIPT_WITHOUT_POL', 'stock.picking', picking_id,
                              'stock.move', line_id, 'supplier_receipt')),
                'RECEIPT_WITHOUT_POL', 'Receipt tanpa Purchase Order Line',
                CASE WHEN state = 'done' THEN 'Masalah Aktif' ELSE 'Perlu Ditinjau' END,
                'stock.picking', picking_id, document_number, state,
                'stock.move', line_id,
                jsonb_build_array(jsonb_build_object(
                    'model', 'stock.picking', 'id', picking_id, 'number', document_number,
                    'status', state, 'type', 'Receipt/LPB', 'problematic', TRUE
                )),
                jsonb_build_array(jsonb_build_object(
                    'model', 'stock.move', 'id', line_id,
                    'product', line_payload #>> '{product_id,name}',
                    'quantity', COALESCE(line_payload ->> 'quantity', line_payload ->> 'product_uom_qty'),
                    'uom', line_payload #>> '{product_uom,name}'
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Receipt', 'value', document_number),
                    jsonb_build_object('label', 'Vendor', 'value', picking_payload #>> '{partner_id,name}'),
                    jsonb_build_object('label', 'Product', 'value', line_payload #>> '{product_id,name}'),
                    jsonb_build_object('label', 'Operation type', 'value', picking_payload #>> '{picking_type_id,name}')
                ),
                CASE WHEN state = 'done'
                     THEN 'Periksa dasar pembelian dan koreksi hubungan Purchase Order Line.'
                     ELSE 'Konfirmasi dasar penerimaan sebelum Receipt diselesaikan.' END,
                'Warehouse', 'Receipt & QC', business_date,
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', product_id,
                    'product_category_id', NULLIF(product_category_id, '')::bigint,
                    'operation_type_id', operation_type_id,
                    'company_id', :company_id
                )),
                :detected_at
            FROM candidate
            WHERE operation_code = 'incoming'
              AND source_usage = 'supplier'
              AND destination_usage = 'internal'
              AND line_payload #>> '{purchase_line_id,id}' IS NULL
              AND business_date >= :scope_start AND business_date < :scope_end
            ON CONFLICT DO NOTHING
        """),
        params,
    )

    _insert_procurement_and_cost_detections(conn, params)
    _insert_cancelled_parent_detections(conn, params)
    _insert_quantity_detections(conn, params)
    _insert_gp_detections(conn, params)

    # Disabled rules and exact reusable exceptions apply to the candidate.
    # Closing an individual finding never creates one of these rules.
    conn.execute(
        text("""
            DELETE FROM ct_finding_detection detection
            WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
              AND NOT EXISTS (
                  SELECT 1 FROM ct_rule_config config
                  WHERE config.rule_code = detection.rule_code AND config.enabled
              )
        """),
        params,
    )
    conn.execute(
        text("""
            DELETE FROM ct_finding_detection detection
            USING ct_exception_rule exception
            WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
              AND exception.active
              AND exception.rule_code = detection.rule_code
              AND detection.selectors @> exception.selector
              AND detection.business_date >= exception.valid_from
              AND (exception.valid_until IS NULL OR detection.business_date <= exception.valid_until)
        """),
        params,
    )
    rows = conn.execute(
        text("""
            SELECT category, COUNT(*) AS count
            FROM ct_finding_detection
            WHERE extraction_run_id = CAST(:run_id AS UUID)
            GROUP BY category
        """),
        params,
    ).mappings().all()
    return {str(row["category"]): int(row["count"]) for row in rows}


def _insert_cancelled_parent_detections(conn: Any, params: Mapping[str, Any]) -> None:
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), open_child AS (
                SELECT
                    parent.record_id AS parent_id,
                    parent.model AS parent_model,
                    parent.document_number AS parent_number,
                    parent.state AS parent_state,
                    parent.payload AS parent_payload,
                    child.model AS child_model,
                    child.record_id AS child_id,
                    child.document_number AS child_number,
                    child.state AS child_state,
                    COALESCE(
                        CASE child.model
                            WHEN 'mrp.production' THEN NULLIF(child.payload ->> 'product_qty', '')::numeric
                            WHEN 'account.move' THEN NULLIF(child.payload ->> 'amount_untaxed', '')::numeric
                        END,
                        CASE WHEN child.model = 'purchase.order' THEN (
                            SELECT SUM(NULLIF(line.payload ->> 'product_qty', '')::numeric)
                            FROM snapshot line
                            WHERE line.model = 'purchase.order.line'
                              AND NULLIF(line.payload #>> '{order_id,id}', '')::bigint = child.record_id
                        ) END,
                        CASE WHEN child.model = 'stock.picking' THEN (
                            SELECT SUM(NULLIF(move.payload ->> 'product_uom_qty', '')::numeric)
                            FROM snapshot move
                            WHERE move.model = 'stock.move'
                              AND NULLIF(move.payload #>> '{picking_id,id}', '')::bigint = child.record_id
                        ) END,
                        CASE WHEN child.model = 'approval.request' THEN (
                            SELECT SUM(NULLIF(line.payload ->> 'quantity', '')::numeric)
                            FROM snapshot line
                            WHERE line.model = 'approval.product.line'
                              AND NULLIF(line.payload #>> '{approval_request_id,id}', '')::bigint = child.record_id
                        ) END,
                        0
                    ) AS child_quantity,
                    CASE parent.model
                        WHEN 'sale.order' THEN NULLIF(parent.payload ->> 'date_order', '')::date
                        WHEN 'purchase.order' THEN NULLIF(parent.payload ->> 'date_order', '')::date
                    END AS business_date
                FROM ct_document_link link
                JOIN snapshot parent
                  ON parent.model = link.parent_model AND parent.record_id = link.parent_id
                JOIN snapshot child
                  ON child.model = link.child_model AND child.record_id = link.child_id
                WHERE link.extraction_run_id = CAST(:run_id AS UUID)
                  AND link.confidence = 'HIGH'
                  AND parent.model IN ('sale.order', 'purchase.order')
                  AND parent.state IN ('cancel', 'cancelled')
                  AND child.model IN (
                      'approval.request', 'mrp.production', 'purchase.order',
                      'stock.picking', 'account.move'
                  )
                  AND COALESCE(child.state, '') NOT IN (
                      'done', 'cancel', 'cancelled', 'posted'
                  )
            ), grouped AS (
                SELECT
                    parent_id, parent_model, MIN(parent_number) AS parent_number,
                    MIN(parent_state) AS parent_state, MIN(business_date) AS business_date,
                    BOOL_OR(child_quantity = 0) AS has_empty_child,
                    COUNT(*) AS child_count,
                    jsonb_agg(jsonb_build_object(
                        'model', child_model, 'id', child_id, 'number', child_number,
                        'status', child_state, 'quantity', child_quantity, 'problematic', TRUE
                    ) ORDER BY child_model, child_number) AS impacted_documents
                FROM open_child
                WHERE business_date >= :scope_start AND business_date < :scope_end
                GROUP BY parent_id, parent_model
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, impacted_documents, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', 'CANCELLED_PARENT_ACTIVE_CHILD',
                    parent_model, parent_id, '', '', 'open_child')),
                'CANCELLED_PARENT_ACTIVE_CHILD',
                'Dokumen induk dibatalkan dengan dokumen lanjutan aktif',
                CASE WHEN has_empty_child THEN 'Masalah Aktif' ELSE 'Perlu Ditinjau' END,
                parent_model, parent_id, parent_number, parent_state,
                impacted_documents,
                jsonb_build_array(
                    jsonb_build_object('label', 'Dokumen induk', 'value', parent_number),
                    jsonb_build_object('label', 'Dokumen lanjutan terbuka', 'value', child_count),
                    jsonb_build_object('label', 'Ada child kosong', 'value', has_empty_child)
                ),
                CASE WHEN has_empty_child
                    THEN 'Periksa dokumen turunan kosong yang tetap terbuka setelah parent dibatalkan.'
                    ELSE 'Konfirmasi apakah item dan kuantitas pada dokumen turunan masih diperlukan.' END,
                CASE WHEN parent_model = 'sale.order' THEN 'PPIC' ELSE 'Procurement' END,
                CASE WHEN parent_model = 'sale.order' THEN 'Sales Order' ELSE 'Purchase Order' END,
                business_date, jsonb_build_object('company_id', :company_id), :detected_at
            FROM grouped
            ON CONFLICT DO NOTHING
        """),
        params,
    )


def _insert_quantity_detections(conn: Any, params: Mapping[str, Any]) -> None:
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), eligible AS (
                SELECT lineage.*
                FROM ct_line_lineage lineage
                JOIN snapshot source
                  ON source.model = lineage.source_model AND source.record_id = lineage.source_id
                LEFT JOIN snapshot source_document
                  ON source_document.model = lineage.source_document_model
                 AND source_document.record_id = lineage.source_document_id
                WHERE lineage.extraction_run_id = CAST(:run_id AS UUID)
                  AND lineage.relationship_type IN (
                      'INVOICE_LINE_TO_SO_LINE', 'SO_MOVE_TO_LINE', 'PO_MOVE_TO_LINE'
                  )
                  AND (
                      (lineage.relationship_type = 'INVOICE_LINE_TO_SO_LINE'
                       AND source_document.state = 'posted')
                      OR (lineage.relationship_type IN ('SO_MOVE_TO_LINE', 'PO_MOVE_TO_LINE')
                          AND source.state = 'done')
                  )
            ), grouped AS (
                SELECT
                    relationship_type, target_model, target_id,
                    target_document_model, target_document_id, MIN(product_id) AS product_id,
                    SUM(source_quantity_reference) AS actual_quantity,
                    MAX(target_quantity_reference) AS expected_quantity,
                    MAX(uom_rounding) AS rounding,
                    BOOL_OR(lineage_status <> 'PROVEN') AS incomplete,
                    jsonb_agg(jsonb_build_object(
                        'model', source_model, 'id', source_id,
                        'document_model', source_document_model,
                        'document_id', source_document_id,
                        'quantity', source_quantity, 'uom_id', source_uom_id
                    ) ORDER BY source_id) AS impacted_lines
                FROM eligible
                GROUP BY relationship_type, target_model, target_id,
                         target_document_model, target_document_id
            ), candidate AS (
                SELECT grouped.*, document.document_number, document.state,
                       document.payload AS document_payload,
                       target.payload AS target_payload,
                       CASE
                           WHEN incomplete OR rounding IS NULL OR rounding <= 0
                                OR actual_quantity IS NULL OR expected_quantity IS NULL
                               THEN 'Data Belum Lengkap'
                           ELSE 'Perlu Ditinjau'
                       END AS category
                FROM grouped
                JOIN snapshot document
                  ON document.model = grouped.target_document_model
                 AND document.record_id = grouped.target_document_id
                JOIN snapshot target
                  ON target.model = grouped.target_model AND target.record_id = grouped.target_id
                WHERE incomplete OR rounding IS NULL OR rounding <= 0
                   OR actual_quantity IS NULL OR expected_quantity IS NULL
                   OR ROUND((actual_quantity - expected_quantity) / rounding) <> 0
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, primary_line_model, primary_line_id,
                impacted_documents, impacted_lines, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', 'QUANTITY_MISMATCH',
                    target_document_model, target_document_id, target_model, target_id,
                    relationship_type)),
                'QUANTITY_MISMATCH', 'Kuantitas dokumen terkait tidak sama', category,
                target_document_model, target_document_id, document_number, state,
                target_model, target_id,
                jsonb_build_array(jsonb_build_object(
                    'model', target_document_model, 'id', target_document_id,
                    'number', document_number, 'status', state, 'problematic', TRUE
                )), impacted_lines,
                jsonb_build_array(
                    jsonb_build_object('label', 'Kuantitas dokumen utama', 'value', expected_quantity),
                    jsonb_build_object('label', 'Kuantitas terkait', 'value', actual_quantity),
                    jsonb_build_object('label', 'Presisi UoM', 'value', rounding)
                ),
                CASE WHEN category = 'Data Belum Lengkap'
                    THEN 'Lengkapi produk, UoM, atau relasi line sebelum kuantitas disimpulkan.'
                    ELSE 'Konfirmasi perbedaan kuantitas di luar presisi UoM.' END,
                CASE relationship_type WHEN 'INVOICE_LINE_TO_SO_LINE' THEN 'Finance' ELSE 'Warehouse' END,
                CASE relationship_type
                    WHEN 'INVOICE_LINE_TO_SO_LINE' THEN 'Invoice'
                    WHEN 'SO_MOVE_TO_LINE' THEN 'Delivery'
                    ELSE 'Receipt & QC'
                END,
                CASE target_document_model
                    WHEN 'sale.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                    WHEN 'purchase.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                END,
                jsonb_strip_nulls(jsonb_build_object(
                    'product_id', product_id, 'company_id', :company_id
                )), :detected_at
            FROM candidate
            WHERE CASE target_document_model
                    WHEN 'sale.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                    WHEN 'purchase.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                  END >= :scope_start
              AND CASE target_document_model
                    WHEN 'sale.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                    WHEN 'purchase.order' THEN NULLIF(document_payload ->> 'date_order', '')::date
                  END < :scope_end
            ON CONFLICT DO NOTHING
        """),
        params,
    )


def _insert_gp_detections(conn: Any, params: Mapping[str, Any]) -> None:
    conn.execute(
        text("""
            WITH snapshot AS NOT MATERIALIZED (
                SELECT * FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
            ), negative AS (
                SELECT summary.*, so.state, so.payload,
                       'PLANNED_GP_NEGATIVE'::text AS rule_code,
                       'Gross Profit rencana negatif'::text AS title,
                       CASE WHEN so.state IN ('draft', 'sent')
                            THEN 'Perlu Ditinjau' ELSE 'Masalah Aktif' END AS category,
                       summary.planned_revenue_idr AS revenue,
                       summary.planned_rkb_idr AS cost,
                       summary.planned_gp_idr AS gp,
                       summary.planned_margin AS margin,
                       'planned'::text AS variant
                FROM ct_gp_summary summary
                JOIN snapshot so ON so.model = 'sale.order' AND so.record_id = summary.sale_order_id
                WHERE summary.extraction_run_id = CAST(:run_id AS UUID)
                  AND so.state NOT IN ('cancel', 'cancelled')
                  AND summary.planned_status = 'COMPLETE' AND summary.planned_gp_idr < 0
                UNION ALL
                SELECT summary.*, so.state, so.payload,
                       'REALIZED_GP_NEGATIVE', 'Gross Profit realisasi negatif',
                       'Masalah Aktif', summary.realized_revenue_idr,
                       summary.realized_cogs_idr, summary.realized_gp_idr,
                       summary.realized_margin, 'realized'
                FROM ct_gp_summary summary
                JOIN snapshot so ON so.model = 'sale.order' AND so.record_id = summary.sale_order_id
                WHERE summary.extraction_run_id = CAST(:run_id AS UUID)
                  AND summary.realized_status = 'COMPLETE' AND summary.realized_gp_idr < 0
            )
            INSERT INTO ct_finding_detection (
                extraction_run_id, finding_key, rule_code, business_title, category,
                primary_document_model, primary_document_id, primary_document_number,
                primary_document_state, impacted_documents, facts, recommended_action,
                process_owner, process_node, business_date, selectors, detected_at
            )
            SELECT
                CAST(:run_id AS UUID), MD5(CONCAT_WS('|', rule_code, 'sale.order',
                    sale_order_id, '', '', variant)), rule_code, title, category,
                'sale.order', sale_order_id, sale_order_number, state,
                jsonb_build_array(jsonb_build_object(
                    'model', 'sale.order', 'id', sale_order_id,
                    'number', sale_order_number, 'status', state, 'problematic', TRUE
                )),
                jsonb_build_array(
                    jsonb_build_object('label', 'Revenue IDR', 'value', revenue),
                    jsonb_build_object('label', CASE variant WHEN 'planned' THEN 'RKB IDR' ELSE 'COGS IDR' END, 'value', cost),
                    jsonb_build_object('label', 'Gross Profit IDR', 'value', gp),
                    jsonb_build_object('label', 'Margin', 'value', margin)
                ),
                CASE variant WHEN 'planned'
                    THEN 'Tinjau nilai penjualan dan total RKB sebelum proses dilanjutkan.'
                    ELSE 'Rekonsiliasi Posted revenue dan COGS bersama Finance.' END,
                CASE variant WHEN 'planned' THEN 'Commercial' ELSE 'Finance' END,
                'Gross Profit', NULLIF(payload ->> 'date_order', '')::date,
                jsonb_build_object('company_id', :company_id), :detected_at
            FROM negative
            WHERE NULLIF(payload ->> 'date_order', '')::date >= :scope_start
              AND NULLIF(payload ->> 'date_order', '')::date < :scope_end
            ON CONFLICT DO NOTHING
        """),
        params,
    )


def reconcile_findings(conn: Any, *, run_id: str) -> dict[str, int]:
    """Merge candidate detections while preserving manual archive decisions."""
    params = {"run_id": run_id}
    new_count = int(
        conn.execute(
            text("""
                WITH inserted AS (
                    INSERT INTO ct_finding (
                        finding_key, rule_code, business_title, category,
                        primary_document_model, primary_document_id,
                        primary_document_number, primary_document_state,
                        primary_line_model, primary_line_id, impacted_documents,
                        impacted_lines, first_seen_at, last_seen_at, last_detected_at,
                        lifecycle_state, current_evidence, process_owner,
                        responsible_user, process_node, business_date,
                        last_detection_run_id, currently_detected, updated_at
                    )
                    SELECT
                        detection.finding_key, detection.rule_code, detection.business_title,
                        detection.category, detection.primary_document_model,
                        detection.primary_document_id, detection.primary_document_number,
                        detection.primary_document_state, detection.primary_line_model,
                        detection.primary_line_id, detection.impacted_documents,
                        detection.impacted_lines, detection.detected_at,
                        detection.detected_at, detection.detected_at, 'ACTIVE',
                        jsonb_build_object(
                            'facts', detection.facts,
                            'recommended_action', detection.recommended_action,
                            'selectors', detection.selectors
                        ),
                        detection.process_owner, detection.responsible_user,
                        detection.process_node, detection.business_date,
                        detection.extraction_run_id, TRUE, detection.detected_at
                    FROM ct_finding_detection detection
                    WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
                    ON CONFLICT (finding_key) DO NOTHING
                    RETURNING finding_key, current_evidence
                ), events AS (
                    INSERT INTO ct_finding_event (
                        finding_key, event_type, actor, reason, evidence_snapshot
                    )
                    SELECT finding_key, 'DETECTED', 'system', 'Terdeteksi pada refresh',
                           current_evidence
                    FROM inserted
                    RETURNING event_id
                )
                SELECT COUNT(*) FROM inserted
            """),
            params,
        ).scalar_one()
    )

    # Evidence/count changes update the same stable finding and receive an
    # audit event. A manually closed finding stays archived.
    updated_count = int(
        conn.execute(
            text("""
                WITH changed AS (
                    SELECT finding.finding_key, detection.facts,
                           detection.recommended_action, detection.selectors
                    FROM ct_finding finding
                    JOIN ct_finding_detection detection
                      ON detection.finding_key = finding.finding_key
                     AND detection.extraction_run_id = CAST(:run_id AS UUID)
                    WHERE finding.lifecycle_state <> 'AUTO_RESOLVED'
                      AND (
                          finding.category IS DISTINCT FROM detection.category
                          OR finding.impacted_documents IS DISTINCT FROM detection.impacted_documents
                          OR finding.impacted_lines IS DISTINCT FROM detection.impacted_lines
                          OR finding.current_evidence IS DISTINCT FROM jsonb_build_object(
                              'facts', detection.facts,
                              'recommended_action', detection.recommended_action,
                              'selectors', detection.selectors
                          )
                      )
                ), event_rows AS (
                    INSERT INTO ct_finding_event (
                        finding_key, event_type, actor, reason, evidence_snapshot
                    )
                    SELECT finding_key, 'UPDATED', 'system',
                           'Bukti atau jumlah baris terdampak berubah',
                           jsonb_build_object(
                               'facts', facts,
                               'recommended_action', recommended_action,
                               'selectors', selectors
                           )
                    FROM changed
                    RETURNING event_id
                )
                SELECT COUNT(*) FROM changed
            """),
            params,
        ).scalar_one()
    )

    reactivated_count = int(
        conn.execute(
            text("""
                WITH reactivated AS (
                    UPDATE ct_finding finding
                    SET lifecycle_state = 'ACTIVE', closed_reason = NULL,
                        auto_resolved_at = NULL, currently_detected = TRUE,
                        updated_at = detection.detected_at
                    FROM ct_finding_detection detection
                    WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
                      AND detection.finding_key = finding.finding_key
                      AND finding.lifecycle_state = 'AUTO_RESOLVED'
                    RETURNING finding.finding_key, finding.current_evidence
                ), events AS (
                    INSERT INTO ct_finding_event (
                        finding_key, event_type, actor, reason, evidence_snapshot
                    )
                    SELECT finding_key, 'REOPENED', 'system',
                           'Kondisi terdeteksi kembali setelah selesai otomatis',
                           current_evidence
                    FROM reactivated
                    RETURNING event_id
                )
                SELECT COUNT(*) FROM reactivated
            """),
            params,
        ).scalar_one()
    )

    conn.execute(
        text("""
            UPDATE ct_finding finding
            SET rule_code = detection.rule_code,
                business_title = detection.business_title,
                category = detection.category,
                primary_document_number = detection.primary_document_number,
                primary_document_state = detection.primary_document_state,
                impacted_documents = detection.impacted_documents,
                impacted_lines = detection.impacted_lines,
                last_seen_at = detection.detected_at,
                last_detected_at = detection.detected_at,
                current_evidence = jsonb_build_object(
                    'facts', detection.facts,
                    'recommended_action', detection.recommended_action,
                    'selectors', detection.selectors
                ),
                process_owner = detection.process_owner,
                responsible_user = detection.responsible_user,
                process_node = detection.process_node,
                business_date = detection.business_date,
                last_detection_run_id = detection.extraction_run_id,
                currently_detected = TRUE,
                updated_at = detection.detected_at
            FROM ct_finding_detection detection
            WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
              AND detection.finding_key = finding.finding_key
        """),
        params,
    )

    auto_resolved_count = int(
        conn.execute(
            text("""
                WITH resolved AS (
                    UPDATE ct_finding finding
                    SET lifecycle_state = 'AUTO_RESOLVED',
                        closed_reason = 'Selesai Otomatis',
                        auto_resolved_at = NOW(), currently_detected = FALSE,
                        updated_at = NOW()
                    WHERE finding.lifecycle_state = 'ACTIVE'
                      AND NOT EXISTS (
                          SELECT 1 FROM ct_finding_detection detection
                          WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
                            AND detection.finding_key = finding.finding_key
                      )
                    RETURNING finding.finding_key, finding.current_evidence
                ), events AS (
                    INSERT INTO ct_finding_event (
                        finding_key, event_type, actor, reason, evidence_snapshot
                    )
                    SELECT finding_key, 'AUTO_RESOLVED', 'system',
                           'Kondisi tidak lagi ditemukan pada refresh berhasil',
                           current_evidence
                    FROM resolved
                    RETURNING event_id
                )
                SELECT COUNT(*) FROM resolved
            """),
            params,
        ).scalar_one()
    )
    conn.execute(
        text("""
            UPDATE ct_finding finding
            SET currently_detected = FALSE, updated_at = NOW()
            WHERE finding.lifecycle_state = 'MANUALLY_CLOSED'
              AND NOT EXISTS (
                  SELECT 1 FROM ct_finding_detection detection
                  WHERE detection.extraction_run_id = CAST(:run_id AS UUID)
                    AND detection.finding_key = finding.finding_key
              )
        """),
        params,
    )

    conn.execute(
        text("""
            UPDATE ct_document_search document
            SET active_finding_count = (
                SELECT COUNT(*)
                FROM ct_finding finding
                WHERE finding.lifecycle_state = 'ACTIVE'
                  AND finding.primary_document_model = document.model
                  AND finding.primary_document_id = document.record_id
            )
            WHERE document.extraction_run_id = CAST(:run_id AS UUID)
        """),
        params,
    )
    return {
        "new": new_count,
        "updated": updated_count,
        "reactivated": reactivated_count,
        "auto_resolved": auto_resolved_count,
    }


def publish_pointer(
    conn: Any,
    *,
    company_id: int,
    run_id: str,
    contract_version: str,
    scope_year: int,
    published_at: datetime | None = None,
) -> None:
    conn.execute(
        text("""
            INSERT INTO ct_published_run (
                company_id, extraction_run_id, contract_version, scope_year, published_at
            ) VALUES (
                :company_id, CAST(:run_id AS UUID), :contract_version, :scope_year, :published_at
            )
            ON CONFLICT (company_id) DO UPDATE SET
                extraction_run_id = EXCLUDED.extraction_run_id,
                contract_version = EXCLUDED.contract_version,
                scope_year = EXCLUDED.scope_year,
                published_at = EXCLUDED.published_at
        """),
        {
            "company_id": company_id,
            "run_id": run_id,
            "contract_version": contract_version,
            "scope_year": scope_year,
            "published_at": published_at or datetime.now(timezone.utc),
        },
    )


def new_batch_id() -> str:
    return str(uuid4())
