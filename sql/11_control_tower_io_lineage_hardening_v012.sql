-- =============================================================================
-- Control Tower Health v0.1.2 - Internal Order line-level lineage hardening
-- =============================================================================
-- Temuan live v0.1.1:
--   - satu unmatched MO pada sebuah IO membuat seluruh product/UoM row menjadi
--     DATA_EXCEPTION;
--   - seluruh SO line pada SO yang terhubung ke IO dianggap harus cocok dengan
--     IO tersebut, padahal mixed-source adalah proses yang valid;
--   - multi-IO dideteksi pada level SO, bukan pada level line/product/UoM.
--
-- Perbaikan:
--   1. production gap hanya berlaku pada requested product/UoM yang tidak punya
--      exact MO match ketika IO tersebut memang memiliki unmatched MO;
--   2. SO line hanya dialokasikan ke IO dengan exact product/UoM match;
--   3. ambiguity hanya terjadi jika satu SO line cocok ke lebih dari satu IO;
--   4. SO line lain pada mixed-source SO tidak dianggap mismatch;
--   5. materialized rule/summary/worklist direfresh tanpa fetch ulang Odoo.
--
-- Tetap read-only terhadap Odoo. Seluruh perubahan hanya pada PostgreSQL dashboard.
-- =============================================================================

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
      AND UPPER(BTRIM(COALESCE(line.payload ->> 'x_studio_category', ''))) = 'MANUFACTURE'
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
io_mo_classified AS (
    SELECT
        raw.*,
        EXISTS (
            SELECT 1
            FROM io_requested req
            WHERE req.internal_order_id = raw.internal_order_id
              AND req.product_id IS NOT DISTINCT FROM raw.product_id
              AND req.uom_id IS NOT DISTINCT FROM raw.uom_id
        ) AS exact_request_match
    FROM io_mo_raw raw
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
    FROM io_mo_classified
    WHERE exact_request_match
    GROUP BY internal_order_id, product_id, uom_id
),
io_mo_quality AS (
    SELECT
        internal_order_id,
        COUNT(DISTINCT manufacturing_order_id) AS total_mo_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (
            WHERE NOT exact_request_match
        ) AS unmatched_mo_count,
        CASE WHEN BOOL_OR(confidence = 'MEDIUM') THEN 'MEDIUM' ELSE 'HIGH' END AS link_confidence
    FROM io_mo_classified
    GROUP BY internal_order_id
),
so_line_raw AS (
    SELECT
        so_io.child_id AS internal_order_id,
        so_io.parent_id AS sales_order_id,
        line.record_id AS sales_order_line_id,
        NULLIF(line.payload #>> '{product_id,id}', '')::bigint AS product_id,
        NULLIF(line.payload #>> '{product_uom,id}', '')::bigint AS uom_id,
        COALESCE(NULLIF(line.payload ->> 'product_uom_qty', '')::numeric, 0) AS ordered_qty,
        COALESCE(NULLIF(line.payload ->> 'qty_delivered', '')::numeric, 0) AS delivered_qty
    FROM vw_ct_document_links so_io
    JOIN vw_ct_document_links so_line
      ON so_line.link_type = 'SO_TO_LINE'
     AND so_line.parent_model = 'sale.order'
     AND so_line.parent_id = so_io.parent_id
    JOIN vw_ct_native_record_snapshot_current line
      ON line.model = 'sale.order.line'
     AND line.record_id = so_line.child_id
    WHERE so_io.link_type = 'SO_TO_IO'
      AND so_io.parent_model = 'sale.order'
      AND so_io.child_model = 'approval.request'
),
so_line_candidate AS (
    SELECT raw.*
    FROM so_line_raw raw
    JOIN io_requested req
      ON req.internal_order_id = raw.internal_order_id
     AND req.product_id IS NOT DISTINCT FROM raw.product_id
     AND req.uom_id IS NOT DISTINCT FROM raw.uom_id
),
so_line_candidate_count AS (
    SELECT
        sales_order_line_id,
        COUNT(DISTINCT internal_order_id) AS candidate_io_count
    FROM so_line_candidate
    GROUP BY sales_order_line_id
),
so_usage AS (
    SELECT
        candidate.internal_order_id,
        candidate.product_id,
        candidate.uom_id,
        COUNT(DISTINCT candidate.sales_order_id) AS linked_so_count,
        COUNT(DISTINCT candidate.sales_order_line_id) AS matched_so_line_count,
        COUNT(DISTINCT candidate.sales_order_line_id) FILTER (
            WHERE counts.candidate_io_count = 1
        ) AS unique_allocated_so_line_count,
        COUNT(DISTINCT candidate.sales_order_line_id) FILTER (
            WHERE counts.candidate_io_count > 1
        ) AS ambiguous_so_line_count,
        SUM(candidate.ordered_qty) FILTER (
            WHERE counts.candidate_io_count = 1
        )::numeric AS utilized_ordered_qty,
        SUM(candidate.delivered_qty) FILTER (
            WHERE counts.candidate_io_count = 1
        )::numeric AS utilized_delivered_qty
    FROM so_line_candidate candidate
    JOIN so_line_candidate_count counts
      ON counts.sales_order_line_id = candidate.sales_order_line_id
    GROUP BY candidate.internal_order_id, candidate.product_id, candidate.uom_id
),
so_nonmatching AS (
    SELECT
        raw.internal_order_id,
        COUNT(DISTINCT raw.sales_order_line_id) FILTER (
            WHERE NOT EXISTS (
                SELECT 1
                FROM io_requested req
                WHERE req.internal_order_id = raw.internal_order_id
                  AND req.product_id IS NOT DISTINCT FROM raw.product_id
                  AND req.uom_id IS NOT DISTINCT FROM raw.uom_id
            )
        ) AS non_matching_linked_so_line_count
    FROM so_line_raw raw
    GROUP BY raw.internal_order_id
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
    COALESCE(usage.ambiguous_so_line_count, 0) AS multi_io_so_count,
    COALESCE(usage.utilized_ordered_qty, 0)::numeric AS utilized_ordered_qty,
    COALESCE(usage.utilized_delivered_qty, 0)::numeric AS utilized_delivered_qty,
    CASE
        WHEN req.product_id IS NULL OR req.uom_id IS NULL THEN 'DATA_EXCEPTION'
        WHEN COALESCE(mo.mo_count, 0) = 0
         AND COALESCE(mo_quality.unmatched_mo_count, 0) > 0 THEN 'DATA_EXCEPTION'
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
        WHEN COALESCE(usage.ambiguous_so_line_count, 0) > 0 THEN 'DATA_EXCEPTION'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) = 0 THEN 'NOT_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) < req.requested_qty THEN 'PARTIALLY_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) = req.requested_qty THEN 'FULLY_UTILIZED'
        WHEN COALESCE(usage.utilized_ordered_qty, 0) > req.requested_qty THEN 'OVER_UTILIZED'
        ELSE 'DATA_EXCEPTION'
    END AS utilization_status,
    CASE
        WHEN req.product_id IS NULL OR req.uom_id IS NULL THEN 'LOW'
        WHEN COALESCE(mo.mo_count, 0) = 0
         AND COALESCE(mo_quality.unmatched_mo_count, 0) > 0 THEN 'LOW'
        WHEN COALESCE(usage.ambiguous_so_line_count, 0) > 0 THEN 'LOW'
        WHEN COALESCE(mo.link_confidence, mo_quality.link_confidence, 'HIGH') = 'MEDIUM' THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS confidence,
    JSONB_BUILD_OBJECT(
        'mo_product_uom_mismatch_count', COALESCE(mo_quality.unmatched_mo_count, 0),
        'so_product_uom_mismatch_count', 0,
        'multi_io_so_count', COALESCE(usage.ambiguous_so_line_count, 0),
        'production_gap_reason', CASE
            WHEN req.product_id IS NULL OR req.uom_id IS NULL
                THEN 'MISSING_REQUEST_PRODUCT_OR_UOM'
            WHEN COALESCE(mo.mo_count, 0) = 0
             AND COALESCE(mo_quality.unmatched_mo_count, 0) > 0
                THEN 'NO_EXACT_MO_MATCH_WITH_UNMATCHED_IO_MO'
            ELSE NULL
        END,
        'utilization_gap_reason', CASE
            WHEN req.product_id IS NULL OR req.uom_id IS NULL
                THEN 'MISSING_REQUEST_PRODUCT_OR_UOM'
            WHEN COALESCE(usage.ambiguous_so_line_count, 0) > 0
                THEN 'AMBIGUOUS_SO_LINE_MATCHES_MULTIPLE_IO'
            ELSE NULL
        END,
        'total_io_mo_count', COALESCE(mo_quality.total_mo_count, 0),
        'matched_so_line_count', COALESCE(usage.matched_so_line_count, 0),
        'unique_allocated_so_line_count', COALESCE(usage.unique_allocated_so_line_count, 0),
        'ambiguous_so_line_count', COALESCE(usage.ambiguous_so_line_count, 0),
        'non_matching_linked_so_line_count', COALESCE(nonmatching.non_matching_linked_so_line_count, 0),
        'quantity_basis', 'EXACT_PRODUCT_AND_UOM_ONLY',
        'allocation_basis', 'UNIQUE_EXACT_PRODUCT_UOM_MATCH_PER_SO_LINE',
        'lineage_version', 'v0.1.2'
    ) AS evidence
FROM io_requested req
LEFT JOIN io_mo mo
  ON mo.internal_order_id = req.internal_order_id
 AND mo.product_id IS NOT DISTINCT FROM req.product_id
 AND mo.uom_id IS NOT DISTINCT FROM req.uom_id
LEFT JOIN io_mo_quality mo_quality
  ON mo_quality.internal_order_id = req.internal_order_id
LEFT JOIN so_usage usage
  ON usage.internal_order_id = req.internal_order_id
 AND usage.product_id IS NOT DISTINCT FROM req.product_id
 AND usage.uom_id IS NOT DISTINCT FROM req.uom_id
LEFT JOIN so_nonmatching nonmatching
  ON nonmatching.internal_order_id = req.internal_order_id;

CREATE OR REPLACE VIEW vw_ct_io_lineage_diagnostics AS
SELECT
    internal_order_id,
    internal_order_number,
    product_id,
    product_name,
    uom_id,
    uom_name,
    production_status,
    utilization_status,
    confidence,
    COALESCE(NULLIF(evidence ->> 'mo_product_uom_mismatch_count', '')::bigint, 0)
        AS unmatched_io_mo_count,
    COALESCE(NULLIF(evidence ->> 'ambiguous_so_line_count', '')::bigint, 0)
        AS ambiguous_so_line_count,
    COALESCE(NULLIF(evidence ->> 'non_matching_linked_so_line_count', '')::bigint, 0)
        AS non_matching_linked_so_line_count,
    evidence
FROM vw_ct_io_health;

REFRESH MATERIALIZED VIEW mv_ct_rule_results;
REFRESH MATERIALIZED VIEW mv_ct_sop_validation_summary;
REFRESH MATERIALIZED VIEW mv_ct_exception_worklist;

COMMENT ON VIEW vw_ct_io_health IS
    'IO product/UoM health with line-local MO gaps and unique exact SO-line allocation (v0.1.2).';
COMMENT ON VIEW vw_ct_io_lineage_diagnostics IS
    'Diagnostic read model for unmatched IO MOs, ambiguous SO-line allocation, and mixed-source lines.';
