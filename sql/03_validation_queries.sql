-- =============================================================================
-- Data Truth Layer - 03 Validation Queries
-- =============================================================================
-- Purpose:
--   Validate active traceability coverage and cancelled-record exclusions after:
--   1. sql/01_base_views.sql
--   2. sql/02_traceability_views.sql
--
-- Scope:
--   Counts only. No final profitability calculation.
-- =============================================================================

SELECT 'total_so_active' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics

UNION ALL
SELECT 'total_so_cancelled' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_cancelled

UNION ALL
SELECT 'total_so_lines_active' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics

UNION ALL
SELECT 'total_so_lines_cancelled' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_cancelled

UNION ALL
SELECT 'active_so_with_mo' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_mo

UNION ALL
SELECT 'active_so_without_mo' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND NOT has_mo

UNION ALL
SELECT 'active_so_with_stock_movement' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_stock_movement

UNION ALL
SELECT 'active_so_with_accounting_line' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND has_accounting_line

UNION ALL
SELECT 'active_so_mixed_source' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND sales_order_source_type = 'MIXED_SOURCE'

UNION ALL
SELECT 'active_so_unknown_source' AS metric, COUNT(*)::numeric AS value
FROM vw_so_traceability
WHERE is_valid_for_metrics AND sales_order_source_type = 'UNKNOWN_SOURCE'

UNION ALL
SELECT 'active_so_line_from_internal_order' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'FROM_INTERNAL_ORDER'

UNION ALL
SELECT 'active_so_line_from_stock' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'FROM_STOCK'

UNION ALL
SELECT 'active_so_line_make_to_order' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'MAKE_TO_ORDER'

UNION ALL
SELECT 'active_so_line_mixed_source' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'MIXED_SOURCE'

UNION ALL
SELECT 'active_so_line_unknown_source' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'UNKNOWN_SOURCE'

UNION ALL
SELECT 'active_so_line_needs_movement_classification' AS metric, COUNT(*)::numeric AS value
FROM vw_sales_order_line_source_context
WHERE is_valid_for_metrics AND line_source_type = 'NEEDS_MOVEMENT_CLASSIFICATION'

UNION ALL
SELECT 'active_mo_count' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics

UNION ALL
SELECT 'cancelled_mo_count' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_cancelled

UNION ALL
SELECT 'active_mo_with_io' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics AND has_internal_order

UNION ALL
SELECT 'active_mo_without_so' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics AND NOT has_sales_order

UNION ALL
SELECT 'active_mo_invalid_both_so_and_io' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics AND invalid_both_so_and_io

UNION ALL
SELECT 'active_mo_invalid_both_io_and_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics AND invalid_both_io_and_jo

UNION ALL
SELECT 'active_mo_invalid_jo_format' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics AND invalid_jo_format

UNION ALL
SELECT 'active_rkb_count' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_rkb_planning

UNION ALL
SELECT 'cancelled_rkb_count' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_cancelled

UNION ALL
SELECT 'active_rkb_lines_with_io_or_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_rkb_planning AND (has_internal_order OR has_job_order)

UNION ALL
SELECT 'active_rop_count' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_procurement_request

UNION ALL
SELECT 'active_rop_lines_with_io_or_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_procurement_request AND (has_internal_order OR has_job_order)

UNION ALL
SELECT 'unknown_approval_category_count' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics AND approval_business_type = 'UNKNOWN_APPROVAL_CATEGORY'

UNION ALL
SELECT 'other_approval_category_count' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics AND approval_business_type = 'OTHER_APPROVAL_CATEGORY'

UNION ALL
SELECT 'approval_category_' || LOWER(COALESCE(approval_business_type, 'unknown')) AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics
GROUP BY approval_business_type

UNION ALL
SELECT 'active_rkb_invalid_both_io_and_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics AND rkb_source_type = 'INVALID_BOTH_IO_AND_JO'

UNION ALL
SELECT 'active_rkb_invalid_jo_format' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics AND rkb_source_type = 'INVALID_JO_FORMAT'

UNION ALL
SELECT 'active_rkb_unlinked' AS metric, COUNT(*)::numeric AS value
FROM vw_rkb_planning_lines
WHERE is_valid_for_metrics AND rkb_source_type = 'UNLINKED_RKB'

UNION ALL
SELECT 'active_po_count' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_valid_for_metrics

UNION ALL
SELECT 'cancelled_po_count' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_cancelled

UNION ALL
SELECT 'active_po_lines_with_io_or_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_valid_for_metrics AND (has_internal_order OR has_job_order)

UNION ALL
SELECT 'active_po_invalid_both_io_and_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_valid_for_metrics AND purchase_source_type = 'INVALID_BOTH_IO_AND_JO'

UNION ALL
SELECT 'active_po_invalid_jo_format' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_valid_for_metrics AND purchase_source_type = 'INVALID_JO_FORMAT'

UNION ALL
SELECT 'active_po_unlinked' AS metric, COUNT(*)::numeric AS value
FROM vw_procurement_lines
WHERE is_valid_for_metrics AND purchase_source_type = 'UNLINKED_PO'

UNION ALL
SELECT 'active_stock_move_line_count' AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics

UNION ALL
SELECT 'stock_movement_type_' || LOWER(movement_business_type) AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics
GROUP BY movement_business_type

UNION ALL
SELECT 'stock_picking_type_' || COALESCE(NULLIF(BTRIM(picking_type_raw), ''), 'NULL') AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics
GROUP BY COALESCE(NULLIF(BTRIM(picking_type_raw), ''), 'NULL')

UNION ALL
SELECT 'cancelled_stock_move_line_count' AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_cancelled

UNION ALL
SELECT 'active_accounting_line_count' AS metric, COUNT(*)::numeric AS value
FROM vw_accounting_sales_lines
WHERE is_valid_for_metrics

UNION ALL
SELECT 'active_accounting_lines_linked_to_so' AS metric, COUNT(*)::numeric AS value
FROM vw_accounting_sales_lines
WHERE is_valid_for_metrics AND has_sales_order

UNION ALL
SELECT 'accounting_lines_x_studio_sales_order_new' AS metric, COUNT(*)::numeric AS value
FROM account_move_line
WHERE BTRIM(COALESCE(x_studio_sales_order::text, '')) = 'New'

UNION ALL
SELECT 'active_accounting_lines_unmatched_non_new_so_number' AS metric, COUNT(*)::numeric AS value
FROM vw_accounting_sales_lines
WHERE is_valid_for_metrics
  AND normalized_sales_order_number IS NOT NULL
  AND NOT has_sales_order

UNION ALL
SELECT 'cancelled_accounting_line_count' AS metric, COUNT(*)::numeric AS value
FROM vw_accounting_sales_lines
WHERE is_cancelled

ORDER BY metric;
