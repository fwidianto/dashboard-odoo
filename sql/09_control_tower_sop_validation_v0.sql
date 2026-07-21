-- =============================================================================
-- Control Tower Health v0.1 - SOP Validation Read Model
-- =============================================================================
-- Tujuan:
--   1. memakai snapshot dan relasi native ID dari extractor read-only;
--   2. menguji rule SOP yang sudah cukup kuat;
--   3. mempertahankan DATA_LINKAGE_GAP / DATA_EXCEPTION jika bukti belum aman;
--   4. menyediakan summary, exception worklist, dan record journey untuk API.
--
-- Batasan:
--   - tidak ada write-back ke Odoo;
--   - Payment KPI final belum dipublikasikan;
--   - Distribusi JO tetap manual evidence;
--   - draft PO dengan downstream open adalah review signal, bukan bukti pasti reset.
-- =============================================================================

-- Keep dependent materialized views intact. These base views are replaced in
-- place below; dropping them with CASCADE made a partial SQL reapply unusable.

CREATE OR REPLACE VIEW vw_ct_current_run AS
SELECT
    run_id,
    started_at,
    completed_at,
    company_id,
    model_counts
FROM ct_extraction_run
WHERE status = 'COMPLETED'
ORDER BY completed_at DESC, started_at DESC
LIMIT 1;

CREATE OR REPLACE VIEW vw_ct_native_record_snapshot_current AS
SELECT snapshot.*
FROM ct_native_record_snapshot snapshot
JOIN vw_ct_current_run current_run
  ON current_run.run_id = snapshot.extraction_run_id;

CREATE OR REPLACE VIEW vw_ct_document_links AS
SELECT link.*
FROM ct_document_link link
JOIN vw_ct_current_run current_run
  ON current_run.run_id = link.extraction_run_id;

COMMENT ON VIEW vw_ct_document_links IS
    'Current completed native-ID document graph. HIGH means native relation; MEDIUM means exact text reference requiring review.';

CREATE OR REPLACE VIEW vw_ct_document_paths AS
WITH RECURSIVE walk AS (
    SELECT
        link.parent_model AS root_model,
        link.parent_id AS root_id,
        link.parent_number AS root_number,
        link.parent_model,
        link.parent_id,
        link.parent_number,
        link.child_model,
        link.child_id,
        link.child_number,
        link.link_type,
        link.confidence,
        1 AS depth,
        ARRAY[
            link.parent_model || ':' || link.parent_id::text,
            link.child_model || ':' || link.child_id::text
        ]::text[] AS visited,
        ARRAY[link.link_type]::text[] AS link_path
    FROM vw_ct_document_links link

    UNION ALL

    SELECT
        walk.root_model,
        walk.root_id,
        walk.root_number,
        next_link.parent_model,
        next_link.parent_id,
        next_link.parent_number,
        next_link.child_model,
        next_link.child_id,
        next_link.child_number,
        next_link.link_type,
        CASE
            WHEN walk.confidence = 'MEDIUM' OR next_link.confidence = 'MEDIUM' THEN 'MEDIUM'
            ELSE 'HIGH'
        END AS confidence,
        walk.depth + 1,
        walk.visited || (next_link.child_model || ':' || next_link.child_id::text),
        walk.link_path || next_link.link_type
    FROM walk
    JOIN vw_ct_document_links next_link
      ON next_link.parent_model = walk.child_model
     AND next_link.parent_id = walk.child_id
    WHERE walk.depth < 5
      AND NOT (
          next_link.child_model || ':' || next_link.child_id::text = ANY(walk.visited)
      )
)
SELECT * FROM walk;

-- -----------------------------------------------------------------------------
-- Internal Order Health: conservative exact product/UoM matching only.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_ct_io_health AS
WITH io_line AS (
    SELECT
        link.parent_id AS internal_order_id,
        link.parent_number AS internal_order_number,
        line.record_id AS approval_line_id,
        NULLIF(line.payload #>> '{product_id,id}', '')::bigint AS product_id,
        line.payload #>> '{product_id,name}' AS product_name,
        NULLIF(line.payload #>> '{product_uom_id,id}', '')::bigint AS uom_id,
        line.payload #>> '{product_uom_id,name}' AS uom_name,
        COALESCE(NULLIF(line.payload ->> 'quantity', '')::numeric, 0) AS requested_qty
    FROM vw_ct_document_links link
    JOIN vw_ct_native_record_snapshot_current line
      ON line.model = 'approval.product.line'
     AND line.record_id = link.child_id
    WHERE link.link_type = 'APPROVAL_TO_LINE'
      AND UPPER(COALESCE(line.payload ->> 'x_studio_category', '')) = 'MANUFACTURE'
),
io_requested AS (
    SELECT
        internal_order_id,
        internal_order_number,
        product_id,
        MAX(product_name) AS product_name,
        uom_id,
        MAX(uom_name) AS uom_name,
        SUM(requested_qty)::numeric AS requested_qty,
        COUNT(*) AS approval_line_count
    FROM io_line
    GROUP BY internal_order_id, internal_order_number, product_id, uom_id
),
io_mo_raw AS (
    SELECT
        link.parent_id AS internal_order_id,
        mo.record_id AS manufacturing_order_id,
        mo.state AS manufacturing_state,
        NULLIF(mo.payload #>> '{product_id,id}', '')::bigint AS product_id,
        NULLIF(mo.payload #>> '{product_uom_id,id}', '')::bigint AS uom_id,
        COALESCE(NULLIF(mo.payload ->> 'product_qty', '')::numeric, 0) AS planned_qty,
        COALESCE(NULLIF(mo.payload ->> 'qty_produced', '')::numeric, 0) AS produced_qty,
        link.confidence
    FROM vw_ct_document_links link
    JOIN vw_ct_native_record_snapshot_current mo
      ON mo.model = 'mrp.production'
     AND mo.record_id = link.child_id
    WHERE link.link_type = 'IO_TO_MO_REFERENCE'
),
io_mo AS (
    SELECT
        internal_order_id,
        product_id,
        uom_id,
        COUNT(DISTINCT manufacturing_order_id) AS mo_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (
            WHERE LOWER(COALESCE(manufacturing_state, '')) IN ('cancel', 'cancelled')
        ) AS cancelled_mo_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (
            WHERE LOWER(COALESCE(manufacturing_state, '')) NOT IN ('cancel', 'cancelled', 'done')
        ) AS active_mo_count,
        SUM(planned_qty) FILTER (
            WHERE LOWER(COALESCE(manufacturing_state, '')) NOT IN ('cancel', 'cancelled')
        )::numeric AS planned_qty,
        SUM(produced_qty) FILTER (
            WHERE LOWER(COALESCE(manufacturing_state, '')) NOT IN ('cancel', 'cancelled')
        )::numeric AS produced_qty,
        CASE WHEN BOOL_OR(confidence = 'MEDIUM') THEN 'MEDIUM' ELSE 'HIGH' END AS link_confidence
    FROM io_mo_raw
    GROUP BY internal_order_id, product_id, uom_id
),
mo_mismatch AS (
    SELECT
        mo.internal_order_id,
        COUNT(*) AS mismatch_count
    FROM io_mo_raw mo
    WHERE NOT EXISTS (
        SELECT 1
        FROM io_requested req
        WHERE req.internal_order_id = mo.internal_order_id
          AND req.product_id IS NOT DISTINCT FROM mo.product_id
          AND req.uom_id IS NOT DISTINCT FROM mo.uom_id
    )
    GROUP BY mo.internal_order_id
),
so_io_count AS (
    SELECT parent_id AS sales_order_id, COUNT(DISTINCT child_id) AS io_count
    FROM vw_ct_document_links
    WHERE link_type = 'SO_TO_IO'
    GROUP BY parent_id
),
so_line_usage_raw AS (
    SELECT
        so_io.child_id AS internal_order_id,
        so_io.parent_id AS sales_order_id,
        COALESCE(counts.io_count, 0) AS io_count,
        line.record_id AS sales_order_line_id,
        NULLIF(line.payload #>> '{product_id,id}', '')::bigint AS product_id,
        NULLIF(line.payload #>> '{product_uom,id}', '')::bigint AS uom_id,
        COALESCE(NULLIF(line.payload ->> 'product_uom_qty', '')::numeric, 0) AS ordered_qty,
        COALESCE(NULLIF(line.payload ->> 'qty_delivered', '')::numeric, 0) AS delivered_qty
    FROM vw_ct_document_links so_io
    JOIN so_io_count counts
      ON counts.sales_order_id = so_io.parent_id
    JOIN vw_ct_document_links so_line
      ON so_line.link_type = 'SO_TO_LINE'
     AND so_line.parent_model = 'sale.order'
     AND so_line.parent_id = so_io.parent_id
    JOIN vw_ct_native_record_snapshot_current line
      ON line.model = 'sale.order.line'
     AND line.record_id = so_line.child_id
    WHERE so_io.link_type = 'SO_TO_IO'
),
so_usage AS (
    SELECT
        internal_order_id,
        product_id,
        uom_id,
        COUNT(DISTINCT sales_order_id) AS linked_so_count,
        COUNT(DISTINCT sales_order_id) FILTER (WHERE io_count > 1) AS multi_io_so_count,
        SUM(ordered_qty)::numeric AS utilized_ordered_qty,
        SUM(delivered_qty)::numeric AS utilized_delivered_qty
    FROM so_line_usage_raw
    GROUP BY internal_order_id, product_id, uom_id
),
usage_mismatch AS (
    SELECT
        usage.internal_order_id,
        COUNT(*) AS mismatch_count
    FROM so_line_usage_raw usage
    WHERE NOT EXISTS (
        SELECT 1
        FROM io_requested req
        WHERE req.internal_order_id = usage.internal_order_id
          AND req.product_id IS NOT DISTINCT FROM usage.product_id
          AND req.uom_id IS NOT DISTINCT FROM usage.uom_id
    )
    GROUP BY usage.internal_order_id
)
SELECT
    req.internal_order_id,
    req.internal_order_number,
    req.product_id,
    req.product_name,
    req.uom_id,
    req.uom_name,
    req.approval_line_count,
    req.requested_qty,
    COALESCE(mo.mo_count, 0) AS mo_count,
    COALESCE(mo.cancelled_mo_count, 0) AS cancelled_mo_count,
    COALESCE(mo.active_mo_count, 0) AS active_mo_count,
    COALESCE(mo.planned_qty, 0)::numeric AS planned_qty,
    COALESCE(mo.produced_qty, 0)::numeric AS produced_qty,
    COALESCE(usage.linked_so_count, 0) AS linked_so_count,
    COALESCE(usage.multi_io_so_count, 0) AS multi_io_so_count,
    COALESCE(usage.utilized_ordered_qty, 0)::numeric AS utilized_ordered_qty,
    COALESCE(usage.utilized_delivered_qty, 0)::numeric AS utilized_delivered_qty,
    CASE
        WHEN req.product_id IS NULL OR req.uom_id IS NULL THEN 'DATA_EXCEPTION'
        WHEN COALESCE(mismatch.mismatch_count, 0) > 0 THEN 'DATA_EXCEPTION'
        WHEN COALESCE(mo.mo_count, 0) = 0 THEN 'NOT_STARTED'
        WHEN COALESCE(mo.mo_count, 0) = COALESCE(mo.cancelled_mo_count, 0)
         AND COALESCE(mo.produced_qty, 0) = 0 THEN 'CANCELLED'
        WHEN COALESCE(mo.produced_qty, 0) = 0 THEN 'IN_PROGRESS'
        WHEN COALESCE(mo.produced_qty, 0) < req.requested_qty THEN 'PARTIALLY_PRODUCED'
        WHEN COALESCE(mo.produced_qty, 0) = req.requested_qty THEN 'FULLY_PRODUCED'
        WHEN COALESCE(mo.produced_qty, 0) > req.requested_qty THEN 'OVER_PRODUCED'
        ELSE 'DATA_EXCEPTION'
    END AS production_status,
    CASE
        WHEN req.product_id IS NULL OR req.uom_id IS NULL THEN 'DATA_EXCEPTION'
        WHEN COALESCE(usage_mismatch.mismatch_count, 0) > 0 THEN 'DATA_EXCEPTION'
        WHEN COALESCE(usage.multi_io_so_count, 0) > 0 THEN 'DATA_EXCEPTION'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) = 0 THEN 'NOT_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) < req.requested_qty THEN 'PARTIALLY_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) = req.requested_qty THEN 'FULLY_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) > req.requested_qty THEN 'OVER_UTILIZED'
        ELSE 'DATA_EXCEPTION'
    END AS utilization_status,
    CASE
        WHEN req.product_id IS NULL OR req.uom_id IS NULL THEN 'LOW'
        WHEN COALESCE(mismatch.mismatch_count, 0) > 0
          OR COALESCE(usage_mismatch.mismatch_count, 0) > 0
          OR COALESCE(usage.multi_io_so_count, 0) > 0 THEN 'LOW'
        WHEN COALESCE(mo.link_confidence, 'HIGH') = 'MEDIUM' THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS confidence,
    JSONB_BUILD_OBJECT(
        'mo_product_uom_mismatch_count', COALESCE(mismatch.mismatch_count, 0),
        'so_product_uom_mismatch_count', COALESCE(usage_mismatch.mismatch_count, 0),
        'multi_io_so_count', COALESCE(usage.multi_io_so_count, 0),
        'quantity_basis', 'EXACT_PRODUCT_AND_UOM_ONLY'
    ) AS evidence
FROM io_requested req
LEFT JOIN io_mo mo
  ON mo.internal_order_id = req.internal_order_id
 AND mo.product_id IS NOT DISTINCT FROM req.product_id
 AND mo.uom_id IS NOT DISTINCT FROM req.uom_id
LEFT JOIN so_usage usage
  ON usage.internal_order_id = req.internal_order_id
 AND usage.product_id IS NOT DISTINCT FROM req.product_id
 AND usage.uom_id IS NOT DISTINCT FROM req.uom_id
LEFT JOIN mo_mismatch mismatch
  ON mismatch.internal_order_id = req.internal_order_id
LEFT JOIN usage_mismatch
  ON usage_mismatch.internal_order_id = req.internal_order_id;

CREATE OR REPLACE VIEW vw_ct_rule_catalog AS
SELECT * FROM (VALUES
    ('SO-PO-001', 'Kelengkapan Customer PO pada SO Confirmed', 'SOP 3.1', 'Marketing / Admin Sales', 'HIGH', 'DETERMINISTIC'),
    ('SO-SOURCE-001', 'Klasifikasi fulfilment per SO', 'SOP 3.1-3.2', 'Marketing / PPIC', 'HIGH', 'DETERMINISTIC_WITH_LINKAGE'),
    ('SO-CANCEL-001', 'SO Cancelled tanpa downstream operasional terbuka', 'Control Point Cancellation', 'Multi-owner', 'HIGH', 'DETERMINISTIC'),
    ('PO-CANCEL-001', 'PO Cancelled tanpa Receipt terbuka', 'SOP 3.4-3.5', 'Procurement / WHD', 'HIGH', 'DETERMINISTIC'),
    ('PO-DRAFT-001', 'Draft PO dengan downstream terbuka perlu review koreksi', 'SOP Reset to Draft', 'Procurement / WHD', 'MEDIUM', 'REVIEW_SIGNAL'),
    ('SO-IO-MO-001', 'MO suppression pada SO berbasis IO', 'SOP 3.1-3.2', 'Marketing / PPIC', 'MEDIUM', 'AUTOMATION_EVIDENCE'),
    ('IO-PROD-001', 'Status produksi Internal Order', 'SOP Internal Order', 'PPIC', 'HIGH', 'PROVISIONAL_QUANTITY_CONTRACT'),
    ('IO-UTIL-001', 'Status pemanfaatan Internal Order', 'SOP Internal Order', 'PPIC / Marketing', 'HIGH', 'PROVISIONAL_QUANTITY_CONTRACT'),
    ('JO-DIST-001', 'Bukti Distribusi JO', 'SOP Distribusi JO', 'Marketing / Operations', 'MEDIUM', 'MANUAL_EVIDENCE_ONLY'),
    ('PAY-001', 'Status Payment dan Reconciliation', 'Accounting SOP Pending', 'Accounting', 'HIGH', 'OWNER_DECISION_REQUIRED')
) AS rules(rule_id, rule_name, sop_section, owner, default_severity, implementation_class);

CREATE OR REPLACE VIEW vw_ct_rule_results AS
WITH confirmed_so AS (
    SELECT *
    FROM vw_ct_native_record_snapshot_current
    WHERE model = 'sale.order'
      AND LOWER(COALESCE(state, '')) = 'sale'
      AND COALESCE(NULLIF(payload ->> 'date_order', '')::timestamp, write_date) >= TIMESTAMP '2026-01-01'
),
source_context AS (
    SELECT
        so.record_id AS sales_order_id,
        so.document_number,
        dashboard.source_type
    FROM vw_ct_native_record_snapshot_current so
    LEFT JOIN vw_dashboard_sales_order_traceability dashboard
      ON dashboard.sales_order_id = so.record_id
    WHERE so.model = 'sale.order'
      AND LOWER(COALESCE(so.state, '')) NOT IN ('cancel', 'cancelled')
),
descendants AS (
    SELECT
        path.root_model,
        path.root_id,
        path.child_model,
        path.child_id,
        child.state AS child_state,
        child.document_number AS child_number,
        JSONB_AGG(DISTINCT TO_JSONB(path.link_path)) AS link_paths
    FROM vw_ct_document_paths path
    JOIN vw_ct_native_record_snapshot_current child
      ON child.model = path.child_model
     AND child.record_id = path.child_id
    GROUP BY
        path.root_model,
        path.root_id,
        path.child_model,
        path.child_id,
        child.state,
        child.document_number
),
open_descendant AS (
    SELECT
        root_model,
        root_id,
        COUNT(*) FILTER (
            WHERE LOWER(COALESCE(child_state, '')) NOT IN ('done', 'cancel', 'cancelled', 'posted')
        ) AS open_count,
        COUNT(*) FILTER (
            WHERE LOWER(COALESCE(child_state, '')) IN ('done', 'posted')
        ) AS historical_count,
        JSONB_AGG(
            DISTINCT JSONB_BUILD_OBJECT(
                'model', child_model,
                'id', child_id,
                'number', child_number,
                'state', child_state,
                'link_paths', link_paths
            )
        ) FILTER (
            WHERE LOWER(COALESCE(child_state, '')) NOT IN ('done', 'cancel', 'cancelled', 'posted')
        ) AS open_documents
    FROM descendants
    GROUP BY root_model, root_id
),
po_receipt AS (
    SELECT
        link.parent_id AS purchase_order_id,
        COUNT(*) FILTER (
            WHERE LOWER(COALESCE(receipt.state, '')) NOT IN ('done', 'cancel', 'cancelled')
        ) AS open_receipt_count,
        JSONB_AGG(
            JSONB_BUILD_OBJECT('id', receipt.record_id, 'number', receipt.document_number, 'state', receipt.state)
        ) FILTER (
            WHERE LOWER(COALESCE(receipt.state, '')) NOT IN ('done', 'cancel', 'cancelled')
        ) AS open_receipts
    FROM vw_ct_document_links link
    JOIN vw_ct_native_record_snapshot_current receipt
      ON receipt.model = 'stock.picking'
     AND receipt.record_id = link.child_id
    WHERE link.link_type = 'PO_TO_RECEIPT'
    GROUP BY link.parent_id
),
suppression_candidate AS (
    SELECT DISTINCT
        so.record_id AS sales_order_id,
        so.document_number AS sales_order_number,
        mo.record_id AS manufacturing_order_id,
        mo.document_number AS manufacturing_order_number,
        mo.state AS manufacturing_state,
        mo.payload ->> 'x_studio_io_from_sales_order_1' AS suppression_field
    FROM vw_ct_native_record_snapshot_current so
    JOIN vw_ct_document_links so_io
      ON so_io.link_type = 'SO_TO_IO'
     AND so_io.parent_model = 'sale.order'
     AND so_io.parent_id = so.record_id
    JOIN vw_ct_document_links so_mo
      ON so_mo.link_type = 'SO_TO_MO_ORIGIN'
     AND so_mo.parent_model = 'sale.order'
     AND so_mo.parent_id = so.record_id
    JOIN vw_ct_native_record_snapshot_current mo
      ON mo.model = 'mrp.production'
     AND mo.record_id = so_mo.child_id
    WHERE so.model = 'sale.order'
)
SELECT
    'SO-PO-001'::text AS rule_id,
    'SOP 3.1'::text AS sop_section,
    'sale.order'::text AS document_model,
    so.record_id AS document_id,
    so.document_number,
    JSONB_BUILD_OBJECT(
        'client_order_ref_required', TRUE,
        'customer_po_date_required', TRUE,
        'effective_from', '2026-01-01'
    ) AS expected_condition,
    JSONB_BUILD_OBJECT(
        'client_order_ref', so.payload ->> 'client_order_ref',
        'customer_po_date', so.payload ->> 'x_studio_tanggal_po_cust',
        'state', so.state
    ) AS actual_condition,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(so.payload ->> 'client_order_ref', '')), '') IS NOT NULL
         AND NULLIF(BTRIM(COALESCE(so.payload ->> 'x_studio_tanggal_po_cust', '')), '') IS NOT NULL
            THEN 'VALIDATED'
        ELSE 'MISMATCH'
    END AS validation_status,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(so.payload ->> 'client_order_ref', '')), '') IS NOT NULL
         AND NULLIF(BTRIM(COALESCE(so.payload ->> 'x_studio_tanggal_po_cust', '')), '') IS NOT NULL
            THEN 'LOW'
        ELSE 'MEDIUM'
    END AS severity,
    'HIGH'::text AS confidence,
    'Marketing / Admin Sales'::text AS owner,
    JSONB_BUILD_OBJECT('source', 'native sale.order fields') AS evidence,
    NOW() AS detected_at
FROM confirmed_so so

UNION ALL

SELECT
    'SO-SOURCE-001',
    'SOP 3.1-3.2',
    'sale.order',
    source.sales_order_id,
    source.document_number,
    JSONB_BUILD_OBJECT('allowed', JSONB_BUILD_ARRAY('FROM_STOCK', 'FROM_INTERNAL_ORDER', 'MAKE_TO_ORDER', 'MIXED_SOURCE')),
    JSONB_BUILD_OBJECT('source_type', source.source_type),
    CASE
        WHEN source.source_type IN ('FROM_STOCK', 'FROM_INTERNAL_ORDER', 'MAKE_TO_ORDER', 'MIXED_SOURCE') THEN 'VALIDATED'
        ELSE 'DATA_LINKAGE_GAP'
    END,
    CASE WHEN source.source_type IN ('FROM_STOCK', 'FROM_INTERNAL_ORDER', 'MAKE_TO_ORDER', 'MIXED_SOURCE') THEN 'LOW' ELSE 'HIGH' END,
    CASE WHEN source.source_type IS NULL THEN 'LOW' ELSE 'MEDIUM' END,
    'Marketing / PPIC',
    JSONB_BUILD_OBJECT(
        'dashboard_view', 'vw_dashboard_sales_order_traceability',
        'source_gap_reason', CASE
            WHEN source.source_type IS NULL THEN 'NULL_SOURCE_DATA'
            WHEN source.source_type NOT IN (
                'FROM_STOCK', 'FROM_INTERNAL_ORDER', 'MAKE_TO_ORDER', 'MIXED_SOURCE'
            ) THEN 'UNSUPPORTED_SOURCE_CLASSIFICATION'
            ELSE NULL
        END
    ),
    NOW()
FROM source_context source

UNION ALL

SELECT
    'SO-CANCEL-001',
    'Control Point Cancellation',
    'sale.order',
    so.record_id,
    so.document_number,
    JSONB_BUILD_OBJECT('open_downstream_count', 0, 'done_posted_records_retained_as_history', TRUE),
    JSONB_BUILD_OBJECT(
        'open_downstream_count', COALESCE(downstream.open_count, 0),
        'historical_downstream_count', COALESCE(downstream.historical_count, 0),
        'open_documents', COALESCE(downstream.open_documents, '[]'::jsonb)
    ),
    CASE WHEN COALESCE(downstream.open_count, 0) = 0 THEN 'VALIDATED' ELSE 'MISMATCH' END,
    CASE WHEN COALESCE(downstream.open_count, 0) = 0 THEN 'LOW' ELSE 'HIGH' END,
    'HIGH',
    'Multi-owner',
    JSONB_BUILD_OBJECT('basis', 'native/reviewable descendant graph'),
    NOW()
FROM vw_ct_native_record_snapshot_current so
LEFT JOIN open_descendant downstream
  ON downstream.root_model = 'sale.order'
 AND downstream.root_id = so.record_id
WHERE so.model = 'sale.order'
  AND LOWER(COALESCE(so.state, '')) IN ('cancel', 'cancelled')

UNION ALL

SELECT
    'PO-CANCEL-001',
    'SOP 3.4-3.5',
    'purchase.order',
    po.record_id,
    po.document_number,
    JSONB_BUILD_OBJECT('open_receipt_count', 0),
    JSONB_BUILD_OBJECT(
        'open_receipt_count', COALESCE(receipt.open_receipt_count, 0),
        'open_receipts', COALESCE(receipt.open_receipts, '[]'::jsonb)
    ),
    CASE WHEN COALESCE(receipt.open_receipt_count, 0) = 0 THEN 'VALIDATED' ELSE 'MISMATCH' END,
    CASE WHEN COALESCE(receipt.open_receipt_count, 0) = 0 THEN 'LOW' ELSE 'HIGH' END,
    'HIGH',
    'Procurement / WHD',
    JSONB_BUILD_OBJECT('basis', 'PO_TO_RECEIPT native derived relation'),
    NOW()
FROM vw_ct_native_record_snapshot_current po
LEFT JOIN po_receipt receipt
  ON receipt.purchase_order_id = po.record_id
WHERE po.model = 'purchase.order'
  AND LOWER(COALESCE(po.state, '')) IN ('cancel', 'cancelled')

UNION ALL

SELECT
    'PO-DRAFT-001',
    'SOP Reset to Draft',
    'purchase.order',
    po.record_id,
    po.document_number,
    JSONB_BUILD_OBJECT('review_required_if_open_receipt', TRUE),
    JSONB_BUILD_OBJECT(
        'current_state', po.state,
        'open_receipt_count', COALESCE(receipt.open_receipt_count, 0),
        'open_receipts', COALESCE(receipt.open_receipts, '[]'::jsonb),
        'warning', 'Current Draft state alone does not prove a historical Reset to Draft'
    ),
    'PARTIAL_MATCH',
    'MEDIUM',
    'MEDIUM',
    'Procurement / WHD',
    JSONB_BUILD_OBJECT('requires_chatter_or_state_history', TRUE),
    NOW()
FROM vw_ct_native_record_snapshot_current po
JOIN po_receipt receipt
  ON receipt.purchase_order_id = po.record_id
 AND receipt.open_receipt_count > 0
WHERE po.model = 'purchase.order'
  AND LOWER(COALESCE(po.state, '')) = 'draft'

UNION ALL

SELECT
    'SO-IO-MO-001',
    'SOP 3.1-3.2',
    'mrp.production',
    candidate.manufacturing_order_id,
    candidate.manufacturing_order_number,
    JSONB_BUILD_OBJECT('expected_classification', 'MO_SUPPRESSED_BY_IO'),
    JSONB_BUILD_OBJECT(
        'sales_order_id', candidate.sales_order_id,
        'sales_order_number', candidate.sales_order_number,
        'manufacturing_state', candidate.manufacturing_state,
        'suppression_field', candidate.suppression_field
    ),
    CASE
        WHEN LOWER(COALESCE(candidate.manufacturing_state, '')) IN ('cancel', 'cancelled')
         AND NULLIF(BTRIM(COALESCE(candidate.suppression_field, '')), '') IS NOT NULL
            THEN 'VALIDATED'
        WHEN LOWER(COALESCE(candidate.manufacturing_state, '')) IN ('cancel', 'cancelled')
            THEN 'PARTIAL_MATCH'
        ELSE 'MISMATCH'
    END,
    CASE
        WHEN LOWER(COALESCE(candidate.manufacturing_state, '')) IN ('cancel', 'cancelled') THEN 'LOW'
        ELSE 'MEDIUM'
    END,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(candidate.suppression_field, '')), '') IS NOT NULL THEN 'HIGH'
        ELSE 'MEDIUM'
    END,
    'Marketing / PPIC',
    JSONB_BUILD_OBJECT('relations', JSONB_BUILD_ARRAY('SO_TO_IO', 'SO_TO_MO_ORIGIN')),
    NOW()
FROM suppression_candidate candidate

UNION ALL

SELECT
    'IO-PROD-001',
    'SOP Internal Order',
    'approval.request',
    io.internal_order_id,
    io.internal_order_number,
    JSONB_BUILD_OBJECT('status_set', JSONB_BUILD_ARRAY('NOT_STARTED', 'IN_PROGRESS', 'PARTIALLY_PRODUCED', 'FULLY_PRODUCED', 'OVER_PRODUCED', 'CANCELLED', 'DATA_EXCEPTION')),
    JSONB_BUILD_OBJECT(
        'production_status', io.production_status,
        'requested_qty', io.requested_qty,
        'planned_qty', io.planned_qty,
        'produced_qty', io.produced_qty,
        'product_id', io.product_id,
        'uom_id', io.uom_id
    ),
    CASE WHEN io.production_status = 'DATA_EXCEPTION' THEN 'DATA_LINKAGE_GAP' ELSE 'VALIDATED' END,
    CASE WHEN io.production_status = 'DATA_EXCEPTION' THEN 'HIGH' ELSE 'LOW' END,
    io.confidence,
    'PPIC',
    CASE
        WHEN io.production_status = 'DATA_EXCEPTION' THEN io.evidence || JSONB_BUILD_OBJECT(
            'data_linkage_gap_reason', io.evidence ->> 'production_gap_reason'
        )
        ELSE io.evidence
    END,
    NOW()
FROM vw_ct_io_health io

UNION ALL

SELECT
    'IO-UTIL-001',
    'SOP Internal Order',
    'approval.request',
    io.internal_order_id,
    io.internal_order_number,
    JSONB_BUILD_OBJECT('status_set', JSONB_BUILD_ARRAY('NOT_UTILIZED', 'PARTIALLY_UTILIZED', 'FULLY_UTILIZED', 'OVER_UTILIZED', 'DATA_EXCEPTION')),
    JSONB_BUILD_OBJECT(
        'utilization_status', io.utilization_status,
        'requested_qty', io.requested_qty,
        'utilized_ordered_qty', io.utilized_ordered_qty,
        'utilized_delivered_qty', io.utilized_delivered_qty,
        'multi_io_so_count', io.multi_io_so_count
    ),
    CASE WHEN io.utilization_status = 'DATA_EXCEPTION' THEN 'DATA_LINKAGE_GAP' ELSE 'VALIDATED' END,
    CASE WHEN io.utilization_status = 'DATA_EXCEPTION' THEN 'HIGH' ELSE 'LOW' END,
    io.confidence,
    'PPIC / Marketing',
    CASE
        WHEN io.utilization_status = 'DATA_EXCEPTION' THEN io.evidence || JSONB_BUILD_OBJECT(
            'data_linkage_gap_reason', io.evidence ->> 'utilization_gap_reason'
        )
        ELSE io.evidence
    END,
    NOW()
FROM vw_ct_io_health io;

CREATE OR REPLACE VIEW vw_ct_sop_validation_summary AS
WITH aggregate AS (
    SELECT
        result.rule_id,
        COUNT(*) AS tested_records,
        COUNT(*) FILTER (WHERE validation_status = 'VALIDATED') AS validated_records,
        COUNT(*) FILTER (WHERE validation_status = 'PARTIAL_MATCH') AS partial_match_records,
        COUNT(*) FILTER (WHERE validation_status = 'MISMATCH') AS mismatch_records,
        COUNT(*) FILTER (WHERE validation_status = 'MANUAL_EVIDENCE_REQUIRED') AS manual_records,
        COUNT(*) FILTER (WHERE validation_status = 'DATA_LINKAGE_GAP') AS linkage_gap_records,
        COUNT(*) FILTER (WHERE validation_status = 'VALID_EXCEPTION') AS valid_exception_records,
        COUNT(*) FILTER (WHERE validation_status = 'NOT_TESTED') AS not_tested_records
    FROM vw_ct_rule_results result
    GROUP BY result.rule_id
)
SELECT
    catalog.rule_id,
    catalog.rule_name,
    catalog.sop_section,
    catalog.owner,
    catalog.default_severity,
    catalog.implementation_class,
    COALESCE(aggregate.tested_records, 0) AS tested_records,
    COALESCE(aggregate.validated_records, 0) AS validated_records,
    COALESCE(aggregate.partial_match_records, 0) AS partial_match_records,
    COALESCE(aggregate.mismatch_records, 0) AS mismatch_records,
    COALESCE(aggregate.manual_records, 0) AS manual_records,
    COALESCE(aggregate.linkage_gap_records, 0) AS linkage_gap_records,
    COALESCE(aggregate.valid_exception_records, 0) AS valid_exception_records,
    COALESCE(aggregate.not_tested_records, 0) AS not_tested_records,
    CASE
        WHEN aggregate.rule_id IS NULL AND catalog.implementation_class = 'MANUAL_EVIDENCE_ONLY' THEN 'MANUAL_EVIDENCE_REQUIRED'
        WHEN aggregate.rule_id IS NULL THEN 'NOT_TESTED'
        WHEN COALESCE(aggregate.mismatch_records, 0) > 0 THEN 'MISMATCH'
        WHEN COALESCE(aggregate.linkage_gap_records, 0) > 0 THEN 'DATA_LINKAGE_GAP'
        WHEN COALESCE(aggregate.partial_match_records, 0) > 0 THEN 'PARTIAL_MATCH'
        ELSE 'VALIDATED'
    END AS overall_status,
    CASE
        WHEN COALESCE(aggregate.tested_records, 0) = 0 THEN NULL
        ELSE ROUND(
            100.0 * COALESCE(aggregate.validated_records, 0)
            / NULLIF(aggregate.tested_records, 0),
            2
        )
    END AS validation_rate_percent
FROM vw_ct_rule_catalog catalog
LEFT JOIN aggregate
  ON aggregate.rule_id = catalog.rule_id;

CREATE OR REPLACE VIEW vw_ct_exception_worklist AS
SELECT
    MD5(result.rule_id || '|' || result.document_model || '|' || result.document_id::text) AS issue_id,
    result.rule_id,
    catalog.rule_name,
    result.sop_section,
    result.document_model,
    result.document_id,
    result.document_number,
    result.validation_status,
    result.severity,
    result.confidence,
    result.owner,
    result.expected_condition,
    result.actual_condition,
    result.evidence,
    result.detected_at,
    CASE result.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END AS severity_priority
FROM vw_ct_rule_results result
LEFT JOIN vw_ct_rule_catalog catalog
  ON catalog.rule_id = result.rule_id
WHERE result.validation_status IN (
    'PARTIAL_MATCH',
    'MISMATCH',
    'MANUAL_EVIDENCE_REQUIRED',
    'DATA_LINKAGE_GAP',
    'NOT_TESTED'
);

COMMENT ON VIEW vw_ct_rule_results IS
    'Record-level SOP validation. Mismatch describes inconsistency; it does not by itself prove user fault or SOP fault.';
COMMENT ON VIEW vw_ct_exception_worklist IS
    'Read-only investigation queue. Human review decides data error, SOP gap, dashboard gap, or valid exception.';
