-- =============================================================================
-- Phase 1 - Job Order Cost Rekap Views
-- =============================================================================
-- Purpose:
--   Additive SQL skeleton/first implementation for the future Excel-style
--   Job Order / Project Cost Rekap report.
--
-- Phase 1 basis:
--   RKB PPIC is a future manual Excel upload/staging source and is not
--   currently available in PostgreSQL. Phase 1 uses Odoo RKB Actual as the
--   comparison baseline.
--
-- Scope:
--   Operational SO/JO-first RKB -> ROP -> PO reconciliation only.
--   Internal Order is linked secondary context where available.
--
-- Explicitly out of scope:
--   Profitability, margin, COGS, estimator variance, stock valuation,
--   accounting-based profit, frontend, and API endpoints.
-- =============================================================================

DROP VIEW IF EXISTS vw_job_order_rekap_summary CASCADE;
DROP VIEW IF EXISTS vw_job_order_po_amount_compare CASCADE;
DROP VIEW IF EXISTS vw_job_order_excess_rop CASCADE;
DROP VIEW IF EXISTS vw_job_order_not_yet_rop CASCADE;
DROP VIEW IF EXISTS vw_job_order_rekap_lines CASCADE;
DROP VIEW IF EXISTS vw_job_order_product_universe CASCADE;
DROP VIEW IF EXISTS vw_job_order_po_agg CASCADE;
DROP VIEW IF EXISTS vw_job_order_rop_agg CASCADE;
DROP VIEW IF EXISTS vw_job_order_odoo_rkb_actual_agg CASCADE;
DROP VIEW IF EXISTS vw_job_order_report_scope CASCADE;

CREATE OR REPLACE VIEW vw_job_order_report_scope AS
WITH io_agg AS (
    SELECT
        bridge.so_id AS sales_order_id,
        STRING_AGG(DISTINCT bridge.internal_order_id::text, ', ' ORDER BY bridge.internal_order_id::text) AS internal_order_id_summary,
        STRING_AGG(DISTINCT ar.name::text, ', ' ORDER BY ar.name::text) FILTER (WHERE ar.name IS NOT NULL) AS internal_order_number_summary,
        COUNT(DISTINCT bridge.internal_order_id) AS internal_order_count
    FROM vw_sale_order_internal_order_bridge bridge
    LEFT JOIN approval_request ar
        ON ar.id = bridge.internal_order_id
    GROUP BY bridge.so_id
)
SELECT
    so.sales_order_number AS report_key,
    CASE
        WHEN so.source_type = 'MAKE_TO_ORDER' THEN 'JOB_ORDER'
        ELSE 'SALES_ORDER'
    END AS report_reference_type,
    so.sales_order_id,
    so.sales_order_number,
    io.internal_order_id_summary,
    io.internal_order_number_summary,
    COALESCE(io.internal_order_count, 0) AS internal_order_count,
    CASE
        WHEN so.source_type = 'MAKE_TO_ORDER' THEN so.sales_order_number
        WHEN so.sales_order_number ~ '^[0-9]{7}$' THEN so.sales_order_number
        ELSE NULL
    END AS job_order_number,
    so.company_id AS company_name,
    so.customer_name,
    so.source_type,
    so.product_type_label,
    so.is_valid_for_metrics,
    'SO_JO_FIRST' AS report_entry_point,
    'IO_LINKED_SECONDARY_CONTEXT' AS internal_order_role
FROM vw_dashboard_sales_order_traceability so
LEFT JOIN io_agg io
    ON io.sales_order_id = so.sales_order_id
WHERE so.is_valid_for_metrics;

COMMENT ON VIEW vw_job_order_report_scope IS
    'Phase 1 SO/JO-first Job Order Cost Rekap report scope. Internal Order is retained as linked secondary context.';

CREATE OR REPLACE VIEW vw_job_order_odoo_rkb_actual_agg AS
WITH mapped AS (
    SELECT
        COALESCE(so_jo.name::text, bridge.so_number::text, rkb.job_order_number::text) AS report_key,
        rkb.product_name::text AS product_key,
        rkb.product_name::text AS product_name,
        rkb.unit_of_measure::text AS unit_of_measure,
        rkb.planned_quantity::numeric AS quantity,
        rkb.planned_unit_price::numeric AS unit_price,
        rkb.planned_subtotal::numeric AS subtotal,
        rkb.date_of_need,
        rkb.approval_line_id
    FROM vw_rkb_planning_lines rkb
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = rkb.job_order_number::text
    -- TODO: confirm whether any non-MANUFACTURE RKB rows can safely use approval_request_numeric_id as IO.
    -- For now, IO mapping only uses explicit RKB internal_order_number to avoid treating
    -- the RKB approval request itself as an Internal Order.
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') IS NOT NULL
       AND bridge.internal_order_id::text = rkb.internal_order_number::text
    WHERE rkb.is_valid_for_metrics
      AND NULLIF(BTRIM(COALESCE(rkb.product_name::text, '')), '') IS NOT NULL
)
SELECT
    report_key,
    product_key,
    MAX(product_name) AS product_name,
    STRING_AGG(DISTINCT unit_of_measure, ', ' ORDER BY unit_of_measure) FILTER (WHERE NULLIF(BTRIM(unit_of_measure), '') IS NOT NULL) AS rkb_actual_uom_summary,
    COALESCE(SUM(quantity), 0)::numeric AS rkb_actual_qty,
    COALESCE(SUM(subtotal), 0)::numeric / NULLIF(COALESCE(SUM(quantity), 0), 0) AS rkb_actual_unit_price,
    COALESCE(SUM(subtotal), 0)::numeric AS rkb_actual_subtotal,
    COUNT(DISTINCT approval_line_id) AS rkb_actual_line_count,
    MIN(date_of_need) AS rkb_actual_date_min,
    MAX(date_of_need) AS rkb_actual_date_max,
    'ODOO_RKB_ACTUAL_BASELINE' AS comparison_basis,
    'vw_rkb_planning_lines' AS source_view
FROM mapped
WHERE NULLIF(BTRIM(COALESCE(report_key, '')), '') IS NOT NULL
GROUP BY report_key, product_key;

COMMENT ON VIEW vw_job_order_odoo_rkb_actual_agg IS
    'Aggregates current/latest Odoo RKB approval lines as the Phase 1 ODOO_RKB_ACTUAL_BASELINE. This is not stock consumption, COGS, or profitability.';

CREATE OR REPLACE VIEW vw_job_order_rop_agg AS
WITH mapped AS (
    SELECT
        COALESCE(so_jo.name::text, bridge.so_number::text, apl.job_order_number::text) AS report_key,
        apl.product_name::text AS product_key,
        apl.product_name::text AS product_name,
        apl.unit_of_measure::text AS unit_of_measure,
        apl.planned_quantity::numeric AS quantity,
        apl.planned_unit_price::numeric AS unit_price,
        apl.planned_subtotal::numeric AS subtotal,
        apl.date_of_need,
        apl.approval_line_id
    FROM vw_approval_product_line_context apl
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = apl.job_order_number::text
    -- TODO: confirm whether any ROP/PEMBELIAN rows can safely use approval_request_numeric_id as IO.
    -- For now, IO mapping only uses explicit ROP/PEMBELIAN internal_order_number to avoid
    -- treating the procurement approval request itself as an Internal Order.
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON NULLIF(BTRIM(COALESCE(apl.internal_order_number::text, '')), '') IS NOT NULL
       AND bridge.internal_order_id::text = apl.internal_order_number::text
    WHERE apl.approval_business_type = 'ROP_PROCUREMENT_REQUEST'
      AND apl.is_valid_for_metrics
      AND NULLIF(BTRIM(COALESCE(apl.product_name::text, '')), '') IS NOT NULL
)
SELECT
    report_key,
    product_key,
    MAX(product_name) AS product_name,
    STRING_AGG(DISTINCT unit_of_measure, ', ' ORDER BY unit_of_measure) FILTER (WHERE NULLIF(BTRIM(unit_of_measure), '') IS NOT NULL) AS rop_uom_summary,
    COALESCE(SUM(quantity), 0)::numeric AS rop_qty,
    COALESCE(SUM(subtotal), 0)::numeric / NULLIF(COALESCE(SUM(quantity), 0), 0) AS rop_unit_price,
    COALESCE(SUM(subtotal), 0)::numeric AS rop_subtotal,
    COUNT(DISTINCT approval_line_id) AS rop_line_count,
    MIN(date_of_need) AS rop_date_of_need_min,
    MAX(date_of_need) AS rop_date_of_need_max,
    'ROP_PEMBELIAN_FROM_APPROVAL_LINES' AS source_basis
FROM mapped
WHERE NULLIF(BTRIM(COALESCE(report_key, '')), '') IS NOT NULL
GROUP BY report_key, product_key;

COMMENT ON VIEW vw_job_order_rop_agg IS
    'Aggregates ROP and PEMBELIAN approval lines as procurement requests. ROP and PEMBELIAN have the same business meaning.';

CREATE OR REPLACE VIEW vw_job_order_po_agg AS
WITH mapped AS (
    SELECT
        COALESCE(so_jo.name::text, bridge.so_number::text, po.job_order_number::text) AS report_key,
        po.product_name::text AS product_key,
        po.product_name::text AS product_name,
        po.unit_of_measure::text AS unit_of_measure,
        po.ordered_quantity::numeric AS ordered_quantity,
        po.received_quantity::numeric AS received_quantity,
        po.invoiced_quantity::numeric AS invoiced_quantity,
        po.unit_price::numeric AS unit_price,
        po.line_subtotal::numeric AS line_subtotal,
        po.purchase_planned_date,
        po.purchase_line_state,
        po.procurement_line_id
    FROM vw_procurement_lines po
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = po.job_order_number::text
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON bridge.internal_order_id::text = po.internal_order_number::text
    WHERE po.is_valid_for_metrics
      AND NULLIF(BTRIM(COALESCE(po.product_name::text, '')), '') IS NOT NULL
)
SELECT
    report_key,
    product_key,
    MAX(product_name) AS product_name,
    STRING_AGG(DISTINCT unit_of_measure, ', ' ORDER BY unit_of_measure) FILTER (WHERE NULLIF(BTRIM(unit_of_measure), '') IS NOT NULL) AS po_uom_summary,
    COALESCE(SUM(ordered_quantity), 0)::numeric AS po_qty,
    COALESCE(SUM(received_quantity), 0)::numeric AS po_received_qty,
    COALESCE(SUM(invoiced_quantity), 0)::numeric AS po_billed_qty,
    COALESCE(SUM(line_subtotal), 0)::numeric / NULLIF(COALESCE(SUM(ordered_quantity), 0), 0) AS po_unit_price,
    COALESCE(SUM(line_subtotal), 0)::numeric AS po_subtotal,
    COUNT(DISTINCT procurement_line_id) AS po_line_count,
    MIN(purchase_planned_date) AS po_expected_arrival_min,
    MAX(purchase_planned_date) AS po_expected_arrival_max,
    STRING_AGG(DISTINCT purchase_line_state, ', ' ORDER BY purchase_line_state) FILTER (WHERE NULLIF(BTRIM(purchase_line_state), '') IS NOT NULL) AS po_status_summary,
    'vw_procurement_lines' AS source_view
FROM mapped
WHERE NULLIF(BTRIM(COALESCE(report_key, '')), '') IS NOT NULL
GROUP BY report_key, product_key;

COMMENT ON VIEW vw_job_order_po_agg IS
    'Aggregates PO execution for Job Order Cost Rekap Phase 1. This is procurement comparison only, not stock valuation or accounting profit.';

CREATE OR REPLACE VIEW vw_job_order_product_universe AS
WITH product_sources AS (
    SELECT
        so.sales_order_number AS report_key,
        rev.product_name::text AS product_key,
        rev.product_name::text AS product_name,
        NULL::text AS uom_summary,
        TRUE AS appears_in_so,
        FALSE AS appears_in_rkb_actual,
        FALSE AS appears_in_rop,
        FALSE AS appears_in_po
    FROM vw_job_order_report_scope so
    JOIN vw_sales_order_revenue rev
        ON rev.sales_order_id = so.sales_order_id
    WHERE NULLIF(BTRIM(COALESCE(rev.product_name::text, '')), '') IS NOT NULL

    UNION ALL

    SELECT report_key, product_key, product_name, rkb_actual_uom_summary, FALSE, TRUE, FALSE, FALSE
    FROM vw_job_order_odoo_rkb_actual_agg

    UNION ALL

    SELECT report_key, product_key, product_name, rop_uom_summary, FALSE, FALSE, TRUE, FALSE
    FROM vw_job_order_rop_agg

    UNION ALL

    SELECT report_key, product_key, product_name, po_uom_summary, FALSE, FALSE, FALSE, TRUE
    FROM vw_job_order_po_agg
)
SELECT
    report_key,
    product_key,
    MAX(product_name) AS product_name,
    BOOL_OR(appears_in_so) AS appears_in_so,
    FALSE AS appears_in_rkb_ppic,
    BOOL_OR(appears_in_rkb_actual) AS appears_in_rkb_actual,
    BOOL_OR(appears_in_rop) AS appears_in_rop,
    BOOL_OR(appears_in_po) AS appears_in_po,
    STRING_AGG(DISTINCT uom_summary, ', ' ORDER BY uom_summary) FILTER (WHERE NULLIF(BTRIM(uom_summary), '') IS NOT NULL) AS uom_summary,
    CASE
        WHEN BOOL_OR(appears_in_rkb_actual) AND BOOL_OR(appears_in_rop) AND BOOL_OR(appears_in_po) THEN 'COMPLETE_THROUGH_PO'
        WHEN BOOL_OR(appears_in_rkb_actual) AND NOT BOOL_OR(appears_in_rop) THEN 'ODOO_RKB_ACTUAL_NOT_ROP'
        WHEN BOOL_OR(appears_in_rop) AND NOT BOOL_OR(appears_in_po) THEN 'ROP_NOT_PO'
        WHEN BOOL_OR(appears_in_po) AND NOT BOOL_OR(appears_in_rkb_actual) THEN 'PO_WITHOUT_ODOO_RKB_ACTUAL'
        WHEN BOOL_OR(appears_in_so) AND NOT BOOL_OR(appears_in_rkb_actual) AND NOT BOOL_OR(appears_in_rop) AND NOT BOOL_OR(appears_in_po) THEN 'SO_ONLY'
        ELSE 'PARTIAL_REVIEW'
    END AS product_presence_status
FROM product_sources
WHERE NULLIF(BTRIM(COALESCE(report_key, '')), '') IS NOT NULL
  AND NULLIF(BTRIM(COALESCE(product_key, '')), '') IS NOT NULL
GROUP BY report_key, product_key;

COMMENT ON VIEW vw_job_order_product_universe IS
    'Product universe for Phase 1 Job Order Cost Rekap across SO lines, Odoo RKB Actual, ROP/PEMBELIAN, and PO. RKB PPIC is reserved for future upload.';

CREATE OR REPLACE VIEW vw_job_order_rekap_lines AS
SELECT
    universe.report_key,
    scope.report_reference_type,
    scope.sales_order_id,
    scope.sales_order_number,
    scope.internal_order_id_summary,
    scope.internal_order_number_summary,
    scope.job_order_number,
    scope.company_name,
    scope.customer_name,
    universe.product_key,
    universe.product_name,
    universe.uom_summary,
    universe.product_presence_status,
    NULL::numeric AS rkb_ppic_qty,
    NULL::numeric AS rkb_ppic_unit_price,
    NULL::numeric AS rkb_ppic_subtotal,
    NULL::numeric AS rkb_ppic_rop_plan_qty,
    'FUTURE_MANUAL_EXCEL_UPLOAD_NOT_IN_POSTGRES' AS rkb_ppic_source_status,
    COALESCE(rkb.rkb_actual_qty, 0)::numeric AS rkb_actual_qty,
    rkb.rkb_actual_uom_summary,
    rkb.rkb_actual_unit_price,
    COALESCE(rkb.rkb_actual_subtotal, 0)::numeric AS rkb_actual_subtotal,
    COALESCE(rkb.rkb_actual_line_count, 0) AS rkb_actual_line_count,
    rkb.rkb_actual_date_min,
    rkb.rkb_actual_date_max,
    COALESCE(rop.rop_qty, 0)::numeric AS rop_qty,
    rop.rop_uom_summary,
    rop.rop_unit_price,
    COALESCE(rop.rop_subtotal, 0)::numeric AS rop_subtotal,
    COALESCE(rop.rop_line_count, 0) AS rop_line_count,
    rop.rop_date_of_need_min,
    rop.rop_date_of_need_max,
    COALESCE(po.po_qty, 0)::numeric AS po_qty,
    COALESCE(po.po_received_qty, 0)::numeric AS po_received_qty,
    COALESCE(po.po_billed_qty, 0)::numeric AS po_billed_qty,
    po.po_uom_summary,
    po.po_unit_price,
    COALESCE(po.po_subtotal, 0)::numeric AS po_subtotal,
    COALESCE(po.po_line_count, 0) AS po_line_count,
    po.po_expected_arrival_min,
    po.po_expected_arrival_max,
    po.po_status_summary,
    GREATEST(COALESCE(rkb.rkb_actual_qty, 0) - COALESCE(rop.rop_qty, 0), 0)::numeric AS not_yet_rop_qty,
    (GREATEST(COALESCE(rkb.rkb_actual_qty, 0) - COALESCE(rop.rop_qty, 0), 0) * COALESCE(rkb.rkb_actual_unit_price, 0))::numeric AS not_yet_rop_amount,
    GREATEST(COALESCE(rop.rop_qty, 0) - COALESCE(rkb.rkb_actual_qty, 0), 0)::numeric AS excess_rop_qty,
    (GREATEST(COALESCE(rop.rop_qty, 0) - COALESCE(rkb.rkb_actual_qty, 0), 0) * COALESCE(rop.rop_unit_price, 0))::numeric AS excess_rop_amount,
    GREATEST(COALESCE(po.po_qty, 0) - COALESCE(rop.rop_qty, 0), 0)::numeric AS po_excess_qty,
    (GREATEST(COALESCE(po.po_qty, 0) - COALESCE(rop.rop_qty, 0), 0) * COALESCE(po.po_unit_price, 0))::numeric AS po_excess_amount,
    COALESCE(po.po_received_qty, 0) / NULLIF(COALESCE(po.po_qty, 0), 0) AS received_ratio,
    COALESCE(po.po_billed_qty, 0) / NULLIF(COALESCE(po.po_qty, 0), 0) AS billed_ratio,
    'ODOO_RKB_ACTUAL_BASELINE' AS comparison_basis,
    'OPERATIONAL_RECONCILIATION_NOT_PROFITABILITY' AS metric_scope
FROM vw_job_order_product_universe universe
LEFT JOIN vw_job_order_report_scope scope
    ON scope.report_key = universe.report_key
LEFT JOIN vw_job_order_odoo_rkb_actual_agg rkb
    ON rkb.report_key = universe.report_key
   AND rkb.product_key = universe.product_key
LEFT JOIN vw_job_order_rop_agg rop
    ON rop.report_key = universe.report_key
   AND rop.product_key = universe.product_key
LEFT JOIN vw_job_order_po_agg po
    ON po.report_key = universe.report_key
   AND po.product_key = universe.product_key;

COMMENT ON VIEW vw_job_order_rekap_lines IS
    'Phase 1 Rekap lines at report_key + product_key grain. Uses Odoo RKB Actual as baseline; RKB PPIC is reserved for future upload/import.';

CREATE OR REPLACE VIEW vw_job_order_not_yet_rop AS
SELECT *
FROM vw_job_order_rekap_lines
WHERE not_yet_rop_qty > 0;

COMMENT ON VIEW vw_job_order_not_yet_rop IS
    'Products where Odoo RKB Actual baseline quantity exceeds ROP/PEMBELIAN quantity. Operational follow-up only.';

CREATE OR REPLACE VIEW vw_job_order_excess_rop AS
SELECT *
FROM vw_job_order_rekap_lines
WHERE excess_rop_qty > 0;

COMMENT ON VIEW vw_job_order_excess_rop IS
    'Products where ROP/PEMBELIAN quantity exceeds Odoo RKB Actual baseline quantity. Operational follow-up only.';

CREATE OR REPLACE VIEW vw_job_order_po_amount_compare AS
SELECT
    report_key,
    report_reference_type,
    sales_order_id,
    sales_order_number,
    internal_order_id_summary,
    internal_order_number_summary,
    job_order_number,
    company_name,
    customer_name,
    product_key,
    product_name,
    LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0))::numeric AS common_qty,
    rop_unit_price,
    po_unit_price,
    (LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0)) * COALESCE(rop_unit_price, 0))::numeric AS rop_value_for_common_qty,
    (LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0)) * COALESCE(po_unit_price, 0))::numeric AS po_value_for_common_qty,
    (
        LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0)) * COALESCE(rop_unit_price, 0)
        - LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0)) * COALESCE(po_unit_price, 0)
    )::numeric AS po_saving_amount,
    po_excess_qty,
    po_excess_amount,
    'PROCUREMENT_PRICE_COMPARISON_NOT_ACCOUNTING_PROFIT' AS comparison_scope
FROM vw_job_order_rekap_lines
WHERE COALESCE(rop_qty, 0) > 0
   OR COALESCE(po_qty, 0) > 0;

COMMENT ON VIEW vw_job_order_po_amount_compare IS
    'ROP vs PO operational amount comparison. Positive saving means PO unit price is lower than ROP unit price for common quantity; this is not accounting profit.';

CREATE OR REPLACE VIEW vw_job_order_rekap_summary AS
SELECT
    report_key,
    MAX(report_reference_type) AS report_reference_type,
    MAX(sales_order_id) AS sales_order_id,
    MAX(sales_order_number) AS sales_order_number,
    MAX(internal_order_id_summary) AS internal_order_id_summary,
    MAX(internal_order_number_summary) AS internal_order_number_summary,
    MAX(job_order_number) AS job_order_number,
    MAX(company_name) AS company_name,
    MAX(customer_name) AS customer_name,
    COUNT(*) AS rekap_line_count,
    COUNT(DISTINCT product_key) AS product_count,
    SUM(rkb_actual_qty)::numeric AS rkb_actual_qty,
    SUM(rkb_actual_subtotal)::numeric AS rkb_actual_amount,
    SUM(rop_qty)::numeric AS rop_qty,
    SUM(rop_subtotal)::numeric AS rop_amount,
    SUM(not_yet_rop_qty)::numeric AS not_yet_rop_qty,
    SUM(not_yet_rop_amount)::numeric AS not_yet_rop_amount,
    SUM(excess_rop_qty)::numeric AS excess_rop_qty,
    SUM(excess_rop_amount)::numeric AS excess_rop_amount,
    SUM(po_qty)::numeric AS po_qty,
    SUM(po_subtotal)::numeric AS po_amount,
    SUM(po_received_qty)::numeric AS po_received_qty,
    SUM(po_billed_qty)::numeric AS po_billed_qty,
    SUM(po_excess_qty)::numeric AS po_excess_qty,
    SUM(po_excess_amount)::numeric AS po_excess_amount,
    SUM(po_received_qty) / NULLIF(SUM(po_qty), 0) AS received_ratio,
    SUM(po_billed_qty) / NULLIF(SUM(po_qty), 0) AS billed_ratio,
    SUM(rop_qty) / NULLIF(SUM(rkb_actual_qty), 0) AS rop_progress_ratio,
    SUM(not_yet_rop_qty) / NULLIF(SUM(rkb_actual_qty), 0) AS not_yet_rop_ratio,
    'ODOO_RKB_ACTUAL_BASELINE' AS comparison_basis,
    'REKAP_2_STYLE_OPERATIONAL_SUMMARY_NOT_PROFITABILITY' AS summary_scope
FROM vw_job_order_rekap_lines
GROUP BY report_key;

COMMENT ON VIEW vw_job_order_rekap_summary IS
    'Phase 1 Rekap 2-style summary by report_key. Uses Odoo RKB Actual baseline and excludes profitability, COGS, valuation, and accounting profit.';

-- =============================================================================
-- Validation queries for Phase 1 review
-- =============================================================================
-- Duplicate grain check: expected 0 rows.
-- SELECT report_key, product_key, COUNT(*) AS row_count
-- FROM vw_job_order_rekap_lines
-- GROUP BY report_key, product_key
-- HAVING COUNT(*) > 1;
--
-- Unmapped RKB Actual check: review rows with no report_key.
-- WITH mapped AS (
--     SELECT
--         rkb.approval_line_id,
--         COALESCE(so_jo.name::text, bridge.so_number::text, rkb.job_order_number::text) AS report_key
--     FROM vw_rkb_planning_lines rkb
--     LEFT JOIN sale_order so_jo
--         ON so_jo.name::text = rkb.job_order_number::text
--     LEFT JOIN vw_sale_order_internal_order_bridge bridge
--         ON NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') IS NOT NULL
--        AND bridge.internal_order_id::text = rkb.internal_order_number::text
--     WHERE rkb.is_valid_for_metrics
-- )
-- SELECT * FROM mapped WHERE report_key IS NULL;
--
-- Unmapped ROP/PEMBELIAN check: review rows with no report_key.
-- WITH mapped AS (
--     SELECT
--         apl.approval_line_id,
--         COALESCE(so_jo.name::text, bridge.so_number::text, apl.job_order_number::text) AS report_key
--     FROM vw_approval_product_line_context apl
--     LEFT JOIN sale_order so_jo
--         ON so_jo.name::text = apl.job_order_number::text
--     LEFT JOIN vw_sale_order_internal_order_bridge bridge
--         ON NULLIF(BTRIM(COALESCE(apl.internal_order_number::text, '')), '') IS NOT NULL
--        AND bridge.internal_order_id::text = apl.internal_order_number::text
--     WHERE apl.approval_business_type = 'ROP_PROCUREMENT_REQUEST'
--       AND apl.is_valid_for_metrics
-- )
-- SELECT * FROM mapped WHERE report_key IS NULL;
--
-- Unmapped PO check: review rows with no report_key.
-- WITH mapped AS (
--     SELECT
--         po.procurement_line_id,
--         COALESCE(so_jo.name::text, bridge.so_number::text, po.job_order_number::text) AS report_key
--     FROM vw_procurement_lines po
--     LEFT JOIN sale_order so_jo
--         ON so_jo.name::text = po.job_order_number::text
--     LEFT JOIN vw_sale_order_internal_order_bridge bridge
--         ON NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') IS NOT NULL
--        AND bridge.internal_order_id::text = po.internal_order_number::text
--     WHERE po.is_valid_for_metrics
-- )
-- SELECT * FROM mapped WHERE report_key IS NULL;
--
-- Mixed UoM check.
-- SELECT report_key, product_key, uom_summary
-- FROM vw_job_order_rekap_lines
-- WHERE uom_summary ILIKE '%,%';
--
-- PO without ROP check.
-- SELECT *
-- FROM vw_job_order_rekap_lines
-- WHERE po_qty > 0
--   AND COALESCE(rop_qty, 0) = 0;
--
-- ROP without PO check.
-- SELECT *
-- FROM vw_job_order_rekap_lines
-- WHERE rop_qty > 0
--   AND COALESCE(po_qty, 0) = 0;
--
-- Cancelled record exclusion check: expected 0 rows.
-- SELECT *
-- FROM vw_job_order_report_scope
-- WHERE NOT is_valid_for_metrics;