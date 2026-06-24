-- =============================================================================
-- Data Truth Layer - 02 Traceability Views
-- =============================================================================
-- Purpose:
--   Build SO-level traceability and exception reporting from base views.
--
-- Scope:
--   Traceability, source classification, and data-quality flags only.
--   No final profitability calculation.
-- =============================================================================

CREATE OR REPLACE VIEW vw_so_traceability AS
WITH so_base AS (
    SELECT
        so.id AS sales_order_id,
        so.name AS sales_order_number,
        so.date_order AS order_date,
        so.partner_id AS customer_name,
        so.state AS sales_order_state,
        UPPER(COALESCE(so.state, 'UNKNOWN')) AS normalized_status,
        (LOWER(COALESCE(so.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
        (LOWER(COALESCE(so.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
        so.delivery_status,
        so.invoice_status,
        so.amount_untaxed AS sales_order_untaxed_amount,
        so.currency_id AS currency_name,
        so.company_id AS company_name,
        COUNT(sol.id) AS sales_order_line_count,
        COALESCE(SUM(sol.price_subtotal), 0) AS sales_order_line_subtotal_total,
        COALESCE(SUM(sol.product_uom_qty), 0) AS ordered_quantity_total,
        COALESCE(SUM(sol.qty_delivered), 0) AS delivered_quantity_total,
        COALESCE(SUM(sol.qty_invoiced), 0) AS invoiced_quantity_total
    FROM sale_order so
    LEFT JOIN sale_order_line sol
        ON sol.order_id = so.name
    GROUP BY
        so.id,
        so.name,
        so.date_order,
        so.partner_id,
        so.state,
        so.delivery_status,
        so.invoice_status,
        so.amount_untaxed,
        so.currency_id,
        so.company_id
),
mo_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT manufacturing_order_id) AS manufacturing_order_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE has_internal_order) AS manufacturing_order_with_io_count,
        COUNT(DISTINCT internal_order_number) FILTER (WHERE has_internal_order) AS internal_order_count,
        COUNT(DISTINCT job_order_number) FILTER (WHERE has_job_order) AS job_order_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE invalid_both_so_and_io) AS invalid_mo_both_so_and_io_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE invalid_both_io_and_jo) AS invalid_mo_both_io_and_jo_count
    FROM vw_mrp_order_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
),
stock_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT stock_move_line_id) AS stock_movement_count,
        COUNT(DISTINCT inferred_manufacturing_order_number) FILTER (
            WHERE inferred_manufacturing_order_number IS NOT NULL
        ) AS stock_movement_mo_count,
        COALESCE(SUM(moved_quantity), 0) AS moved_quantity_total
    FROM vw_stock_movement_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
),
accounting_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT accounting_line_id) AS accounting_line_count,
        COUNT(DISTINCT accounting_move_id) AS accounting_move_count,
        COALESCE(SUM(debit), 0) AS accounting_debit_total,
        COALESCE(SUM(credit), 0) AS accounting_credit_total,
        COALESCE(SUM(balance), 0) AS accounting_balance_total
    FROM vw_accounting_sales_lines
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
),
rkb_agg AS (
    SELECT
        mo.inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT rkb.rkb_line_id) AS rkb_line_count,
        COUNT(DISTINCT rkb.rkb_line_id) FILTER (WHERE rkb.rkb_source_type = 'IO_BASED_RKB') AS io_based_rkb_line_count,
        COUNT(DISTINCT rkb.rkb_line_id) FILTER (WHERE rkb.rkb_source_type = 'JO_BASED_RKB') AS jo_based_rkb_line_count,
        COUNT(DISTINCT rkb.rkb_line_id) FILTER (WHERE rkb.rkb_source_type = 'INVALID_BOTH_IO_AND_JO') AS invalid_rkb_line_count
    FROM vw_mrp_order_context mo
    JOIN vw_rkb_planning_lines rkb
        ON (
            NULLIF(BTRIM(mo.internal_order_number), '') IS NOT NULL
            AND mo.internal_order_number = rkb.internal_order_number
        )
        OR (
            NULLIF(BTRIM(mo.job_order_number), '') IS NOT NULL
            AND mo.job_order_number = rkb.job_order_number
        )
    WHERE mo.inferred_sales_order_id IS NOT NULL
      AND mo.is_valid_for_metrics
      AND rkb.is_valid_for_metrics
      AND rkb.is_valid_for_rkb_planning
    GROUP BY mo.inferred_sales_order_id
),
procurement_agg AS (
    SELECT
        mo.inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT p.procurement_line_id) AS procurement_line_count,
        COUNT(DISTINCT p.procurement_line_id) FILTER (WHERE p.purchase_source_type = 'IO_BASED_PO') AS io_based_po_line_count,
        COUNT(DISTINCT p.procurement_line_id) FILTER (WHERE p.purchase_source_type = 'JO_BASED_PO') AS jo_based_po_line_count,
        COUNT(DISTINCT p.procurement_line_id) FILTER (WHERE p.purchase_source_type = 'INVALID_BOTH_IO_AND_JO') AS invalid_po_line_count
    FROM vw_mrp_order_context mo
    JOIN vw_procurement_lines p
        ON (
            NULLIF(BTRIM(mo.internal_order_number), '') IS NOT NULL
            AND mo.internal_order_number = p.internal_order_number
        )
        OR (
            NULLIF(BTRIM(mo.job_order_number), '') IS NOT NULL
            AND mo.job_order_number = p.job_order_number
        )
    WHERE mo.inferred_sales_order_id IS NOT NULL
      AND mo.is_valid_for_metrics
      AND p.is_valid_for_metrics
    GROUP BY mo.inferred_sales_order_id
)
SELECT
    so.sales_order_id,
    so.sales_order_number,
    so.order_date,
    so.customer_name,
    so.sales_order_state,
    so.normalized_status,
    so.is_cancelled,
    so.is_valid_for_metrics,
    so.delivery_status,
    so.invoice_status,
    so.sales_order_untaxed_amount,
    so.currency_name,
    so.company_name,
    so.sales_order_line_count,
    so.sales_order_line_subtotal_total,
    so.ordered_quantity_total,
    so.delivered_quantity_total,
    so.invoiced_quantity_total,
    COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') AS sales_order_source_type,
    COALESCE(source.sales_order_source_link_status, 'UNKNOWN_NO_MATCHED_LINES') AS sales_order_source_link_status,
    COALESCE(source.from_internal_order_line_count, 0) AS from_internal_order_line_count,
    COALESCE(source.from_stock_line_count, 0) AS from_stock_line_count,
    COALESCE(source.make_to_order_line_count, 0) AS make_to_order_line_count,
    COALESCE(source.mixed_source_line_count, 0) AS mixed_source_line_count,
    COALESCE(source.unknown_source_line_count, 0) AS unknown_source_line_count,
    COALESCE(mo.manufacturing_order_count, 0) AS manufacturing_order_count,
    COALESCE(mo.manufacturing_order_with_io_count, 0) AS manufacturing_order_with_io_count,
    COALESCE(mo.internal_order_count, 0) AS internal_order_count,
    COALESCE(mo.job_order_count, 0) AS job_order_count,
    COALESCE(stock.stock_movement_count, 0) AS stock_movement_count,
    COALESCE(stock.stock_movement_mo_count, 0) AS stock_movement_mo_count,
    COALESCE(stock.moved_quantity_total, 0) AS moved_quantity_total,
    COALESCE(accounting.accounting_line_count, 0) AS accounting_line_count,
    COALESCE(accounting.accounting_move_count, 0) AS accounting_move_count,
    COALESCE(accounting.accounting_debit_total, 0) AS accounting_debit_total,
    COALESCE(accounting.accounting_credit_total, 0) AS accounting_credit_total,
    COALESCE(accounting.accounting_balance_total, 0) AS accounting_balance_total,
    COALESCE(rkb.rkb_line_count, 0) AS rkb_line_count,
    COALESCE(rkb.io_based_rkb_line_count, 0) AS io_based_rkb_line_count,
    COALESCE(rkb.jo_based_rkb_line_count, 0) AS jo_based_rkb_line_count,
    COALESCE(procurement.procurement_line_count, 0) AS procurement_line_count,
    COALESCE(procurement.io_based_po_line_count, 0) AS io_based_po_line_count,
    COALESCE(procurement.jo_based_po_line_count, 0) AS jo_based_po_line_count,
    (so.is_valid_for_metrics AND COALESCE(mo.manufacturing_order_count, 0) > 0) AS has_mo,
    (so.is_valid_for_metrics AND COALESCE(stock.stock_movement_count, 0) > 0) AS has_stock_movement,
    (so.is_valid_for_metrics AND COALESCE(accounting.accounting_line_count, 0) > 0) AS has_accounting_line,
    (so.is_valid_for_metrics AND COALESCE(rkb.rkb_line_count, 0) > 0) AS has_rkb_line,
    (so.is_valid_for_metrics AND COALESCE(procurement.procurement_line_count, 0) > 0) AS has_procurement_line,
    (so.is_valid_for_metrics AND COALESCE(mo.internal_order_count, 0) > 0) AS has_internal_order,
    (so.is_valid_for_metrics AND so.sales_order_line_count = 0) AS missing_sales_order_lines,
    (so.is_valid_for_metrics AND COALESCE(mo.manufacturing_order_count, 0) = 0) AS missing_mo,
    (so.is_valid_for_metrics AND COALESCE(stock.stock_movement_count, 0) = 0) AS missing_stock_movement,
    (so.is_valid_for_metrics AND COALESCE(accounting.accounting_line_count, 0) = 0) AS missing_accounting_line,
    (so.is_valid_for_metrics AND COALESCE(rkb.rkb_line_count, 0) = 0) AS missing_rkb_line,
    (so.is_valid_for_metrics AND COALESCE(procurement.procurement_line_count, 0) = 0) AS missing_procurement_line,
    (so.is_valid_for_metrics AND COALESCE(mo.internal_order_count, 0) = 0) AS missing_internal_order,
    (so.is_valid_for_metrics AND COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'MIXED_SOURCE') AS has_mixed_source_lines,
    (so.is_valid_for_metrics AND (COALESCE(source.unknown_source_line_count, 0) > 0 OR source.sales_order_id IS NULL)) AS has_unknown_source_lines,
    (so.is_valid_for_metrics AND COALESCE(mo.invalid_mo_both_so_and_io_count, 0) > 0) AS has_invalid_mo_both_so_and_io,
    (so.is_valid_for_metrics AND COALESCE(mo.invalid_mo_both_io_and_jo_count, 0) > 0) AS has_invalid_mo_both_io_and_jo,
    (
        so.is_valid_for_metrics
        AND COALESCE(rkb.io_based_rkb_line_count, 0) > 0
        AND COALESCE(rkb.jo_based_rkb_line_count, 0) > 0
    ) AS has_possible_double_rkb,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(mo.manufacturing_order_count, 0) > 0 THEN 'SO_TO_MO_INFERRED_BY_ORIGIN'
        ELSE 'SO_WITHOUT_MO_MATCH'
    END AS sales_order_to_mo_link_status,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(stock.stock_movement_count, 0) > 0 THEN 'SO_TO_STOCK_MOVEMENT_INFERRED'
        ELSE 'SO_WITHOUT_STOCK_MOVEMENT_MATCH'
    END AS sales_order_to_stock_link_status,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(accounting.accounting_line_count, 0) > 0 THEN 'SO_TO_ACCOUNTING_INFERRED_BY_SO_NUMBER'
        ELSE 'SO_WITHOUT_ACCOUNTING_MATCH'
    END AS sales_order_to_accounting_link_status,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(mo.manufacturing_order_count, 0) > 0
          AND COALESCE(stock.stock_movement_count, 0) > 0
          AND COALESCE(accounting.accounting_line_count, 0) > 0
            THEN 'SO_MO_STOCK_ACCOUNTING_TRACE'
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'MIXED_SOURCE' THEN 'MIXED_LINE_SOURCE_TRACE'
        WHEN COALESCE(mo.manufacturing_order_count, 0) = 0
          AND COALESCE(stock.stock_movement_count, 0) > 0
            THEN 'POSSIBLE_EXISTING_STOCK_OR_MISSING_MO_LINK'
        WHEN COALESCE(mo.manufacturing_order_count, 0) > 0
            THEN 'SO_MO_TRACE_ONLY'
        ELSE 'SALES_ORDER_ONLY_OR_MISSING_LINKS'
    END AS traceability_status,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED'
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'UNKNOWN_SOURCE' THEN 'UNKNOWN'
        WHEN COALESCE(mo.manufacturing_order_count, 0) > 0
          OR COALESCE(stock.stock_movement_count, 0) > 0
          OR COALESCE(accounting.accounting_line_count, 0) > 0
            THEN 'INFERRED'
        ELSE 'UNKNOWN'
    END AS traceability_match_confidence
FROM so_base so
LEFT JOIN vw_sales_order_source_summary source
    ON source.sales_order_id = so.sales_order_id
LEFT JOIN mo_agg mo
    ON mo.sales_order_id = so.sales_order_id
LEFT JOIN stock_agg stock
    ON stock.sales_order_id = so.sales_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.sales_order_id = so.sales_order_id
LEFT JOIN rkb_agg rkb
    ON rkb.sales_order_id = so.sales_order_id
LEFT JOIN procurement_agg procurement
    ON procurement.sales_order_id = so.sales_order_id;

COMMENT ON VIEW vw_so_traceability IS
    'SO-level traceability derived from line-level source classification. Supports MIXED_SOURCE SOs. No final profitability calculation.';

CREATE OR REPLACE VIEW vw_data_quality_exceptions AS
SELECT
    'PURCHASE_ORDER_LINE' AS record_type,
    procurement_line_id::text AS record_id,
    purchase_order_reference AS business_reference,
    purchase_source_type AS exception_type,
    CASE
        WHEN purchase_source_type = 'INVALID_BOTH_IO_AND_JO' THEN 'PO line has both IO and JO.'
        WHEN purchase_source_type = 'INVALID_JO_FORMAT' THEN 'PO line has JO value that is not exactly 7 digits. Placeholder New is treated as no JO.'
        ELSE 'PO line has neither IO nor JO.'
    END AS exception_message,
    'INVALID' AS exception_status,
    'HIGH' AS severity
FROM vw_procurement_lines
WHERE purchase_source_type IN ('INVALID_BOTH_IO_AND_JO', 'INVALID_JO_FORMAT')
   OR (is_valid_for_metrics AND purchase_source_type = 'UNLINKED_PO')

UNION ALL
SELECT
    'RKB_LINE' AS record_type,
    rkb_line_id::text AS record_id,
    approval_request_id AS business_reference,
    rkb_source_type AS exception_type,
    CASE
        WHEN rkb_source_type = 'INVALID_BOTH_IO_AND_JO' THEN 'RKB line has both IO and JO.'
        WHEN rkb_source_type = 'INVALID_JO_FORMAT' THEN 'RKB line has JO value that is not exactly 7 digits. Placeholder New is treated as no JO.'
        ELSE 'RKB line has neither IO nor JO.'
    END AS exception_message,
    'INVALID' AS exception_status,
    'HIGH' AS severity
FROM vw_rkb_planning_lines
WHERE rkb_source_type IN ('INVALID_BOTH_IO_AND_JO', 'INVALID_JO_FORMAT')
   OR (is_valid_for_metrics AND rkb_source_type = 'UNLINKED_RKB')

UNION ALL
SELECT
    'APPROVAL_PRODUCT_LINE' AS record_type,
    approval_line_id::text AS record_id,
    approval_request_id AS business_reference,
    approval_business_type AS exception_type,
    CASE
        WHEN approval_business_type = 'UNKNOWN_APPROVAL_CATEGORY' THEN 'Approval product line has missing/empty approval category.'
        ELSE 'Approval product line has approval category outside confirmed RKB/ROP/MANUFACTURE/INTERNAL USE categories.'
    END AS exception_message,
    'UNKNOWN' AS exception_status,
    'MEDIUM' AS severity
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics
  AND approval_business_type IN ('UNKNOWN_APPROVAL_CATEGORY', 'OTHER_APPROVAL_CATEGORY')

UNION ALL
SELECT
    'APPROVAL_PRODUCT_LINE' AS record_type,
    approval_line_id::text AS record_id,
    approval_request_id AS business_reference,
    'CANCELLED_APPROVAL_LINKED_TO_FLOW' AS exception_type,
    'Cancelled approval product line is still linked to IO/JO flow.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_approval_product_line_context
WHERE is_cancelled
  AND (has_internal_order OR has_job_order)

UNION ALL
SELECT
    'APPROVAL_PRODUCT_LINE' AS record_type,
    approval_line_id::text AS record_id,
    approval_request_id AS business_reference,
    'ROP_WITHOUT_APPROVED_STATUS' AS exception_type,
    'ROP/PEMBELIAN procurement request is not approved yet.' AS exception_message,
    'POSSIBLE' AS exception_status,
    'MEDIUM' AS severity
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics
  AND is_rop
  AND LOWER(COALESCE(approval_status, '')) <> 'approved'

UNION ALL
SELECT
    'INTERNAL_ORDER_LINE' AS record_type,
    internal_order_line_id::text AS record_id,
    approval_request_id AS business_reference,
    internal_order_link_status AS exception_type,
    CASE
        WHEN internal_order_link_status = 'MISSING_IO_AND_JO' THEN 'Internal Order approval line has neither IO nor valid JO, so it cannot be linked to MO.'
        WHEN internal_order_link_status = 'INVALID_JO_FORMAT' THEN 'Internal Order approval line has invalid JO format.'
        WHEN internal_order_link_status = 'INVALID_BOTH_IO_AND_JO' THEN 'Internal Order approval line has both IO and JO.'
        ELSE 'Internal Order approval line needs follow-up.'
    END AS exception_message,
    CASE
        WHEN internal_order_link_status IN ('INVALID_JO_FORMAT', 'INVALID_BOTH_IO_AND_JO') THEN 'INVALID'
        ELSE 'UNKNOWN'
    END AS exception_status,
    'MEDIUM' AS severity
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow
  AND internal_order_link_status IN (
      'MISSING_IO_AND_JO',
      'INVALID_JO_FORMAT',
      'INVALID_BOTH_IO_AND_JO'
  )

UNION ALL
SELECT
    'MANUFACTURING_ORDER' AS record_type,
    manufacturing_order_id::text AS record_id,
    manufacturing_order_number AS business_reference,
    manufacturing_source_type AS exception_type,
    CASE
        WHEN invalid_both_so_and_io THEN 'MO has both SO source and IO source.'
        WHEN invalid_jo_format THEN 'MO has JO value that is not exactly 7 digits. Placeholder New is treated as no JO.'
        ELSE 'MO has both IO and JO.'
    END AS exception_message,
    'INVALID' AS exception_status,
    'HIGH' AS severity
FROM vw_mrp_order_context
WHERE invalid_both_so_and_io OR invalid_both_io_and_jo OR invalid_jo_format

UNION ALL
SELECT
    'SALES_ORDER' AS record_type,
    sales_order_id::text AS record_id,
    sales_order_number AS business_reference,
    'SO_LINKED_TO_IO_AND_TRIGGERS_MO' AS exception_type,
    'SO is linked to IO but also appears to trigger a new MO. Current SO IO fields are not extracted, so this is detected through inferred MO IO only.' AS exception_message,
    'POSSIBLE' AS exception_status,
    'MEDIUM' AS severity
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_internal_order AND has_mo

UNION ALL
SELECT
    'SALES_ORDER' AS record_type,
    sales_order_id::text AS record_id,
    sales_order_number AS business_reference,
    'SO_MIXED_SOURCE_TYPES' AS exception_type,
    'SO has multiple source types across lines.' AS exception_message,
    'POSSIBLE' AS exception_status,
    'MEDIUM' AS severity
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_mixed_source_lines

UNION ALL
SELECT
    'SALES_ORDER_LINE' AS record_type,
    sales_order_line_id::text AS record_id,
    sales_order_number AS business_reference,
    'UNKNOWN_SOURCE' AS exception_type,
    'SO line source cannot be determined from extracted IO, MO, or stock movement fields.' AS exception_message,
    'UNKNOWN' AS exception_status,
    'MEDIUM' AS severity
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'UNKNOWN_SOURCE'

UNION ALL
SELECT
    'SALES_ORDER' AS record_type,
    sales_order_id::text AS record_id,
    sales_order_number AS business_reference,
    'POSSIBLE_DOUBLE_RKB' AS exception_type,
    'SO has both IO-based and JO-based RKB through related MO keys. This may indicate double planning or double costing.' AS exception_message,
    'POSSIBLE' AS exception_status,
    'HIGH' AS severity
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_possible_double_rkb

UNION ALL
SELECT
    'SALES_ORDER' AS record_type,
    sales_order_id::text AS record_id,
    sales_order_number AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Sales Order is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_so_traceability
WHERE is_cancelled

UNION ALL
SELECT
    'MANUFACTURING_ORDER' AS record_type,
    manufacturing_order_id::text AS record_id,
    manufacturing_order_number AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Manufacturing Order is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_mrp_order_context
WHERE is_cancelled

UNION ALL
SELECT
    'RKB_LINE' AS record_type,
    rkb_line_id::text AS record_id,
    approval_request_id AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'RKB line is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_rkb_planning_lines
WHERE is_cancelled

UNION ALL
SELECT
    'INTERNAL_ORDER_LINE' AS record_type,
    internal_order_line_id::text AS record_id,
    approval_request_id AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Internal Order approval line is cancelled and excluded from active manufacturing flow metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_internal_order_context
WHERE is_cancelled

UNION ALL
SELECT
    'PURCHASE_ORDER_LINE' AS record_type,
    procurement_line_id::text AS record_id,
    purchase_order_reference AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Purchase Order line is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_procurement_lines
WHERE is_cancelled

UNION ALL
SELECT
    'STOCK_MOVE_LINE' AS record_type,
    stock_move_line_id::text AS record_id,
    stock_reference AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Stock move line is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_stock_movement_context
WHERE is_cancelled

UNION ALL
SELECT
    'ACCOUNTING_LINE' AS record_type,
    accounting_line_id::text AS record_id,
    accounting_move_name AS business_reference,
    'CANCELLED_RECORD' AS exception_type,
    'Accounting line is cancelled and excluded from active traceability metrics.' AS exception_message,
    'CANCELLED_RECORD' AS exception_status,
    'INFO' AS severity
FROM vw_accounting_sales_lines
WHERE is_cancelled;

COMMENT ON VIEW vw_data_quality_exceptions IS
    'Business correction queue for invalid, possible, and unknown traceability records.';
