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
SELECT 'sale_order_internal_order_bridge_rows' AS metric, COUNT(*)::numeric AS value
FROM vw_sale_order_internal_order_bridge

UNION ALL
SELECT 'sale_orders_with_internal_order_bridge' AS metric, COUNT(DISTINCT so_id)::numeric AS value
FROM vw_sale_order_internal_order_bridge

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
SELECT 'active_mo_linked_to_internal_order' AS metric, COUNT(DISTINCT manufacturing_order_id)::numeric AS value
FROM vw_manufacturing_flow_context
WHERE manufacturing_is_valid_for_metrics
  AND internal_order_is_valid_for_metrics
  AND manufacturing_order_id IS NOT NULL

UNION ALL
SELECT 'active_mo_not_linked_to_internal_order_or_so' AS metric, COUNT(*)::numeric AS value
FROM vw_mrp_order_context
WHERE is_valid_for_metrics
  AND NOT has_internal_order
  AND NOT has_sales_order
  AND NOT has_valid_jo

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
SELECT 'active_approval_lines_by_category_' || LOWER(approval_business_type) AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics
GROUP BY approval_business_type

UNION ALL
SELECT 'active_internal_order_lines' AS metric, COUNT(*)::numeric AS value
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow

UNION ALL
SELECT 'active_internal_order_lines_with_io_number' AS metric, COUNT(*)::numeric AS value
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow AND has_internal_order

UNION ALL
SELECT 'active_internal_order_lines_with_valid_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow AND has_valid_jo

UNION ALL
SELECT 'active_internal_order_lines_linked_to_mo' AS metric, COUNT(*)::numeric AS value
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow AND has_linked_manufacturing_order

UNION ALL
SELECT 'active_internal_order_lines_not_linked_to_mo' AS metric, COUNT(*)::numeric AS value
FROM vw_internal_order_context
WHERE is_valid_for_internal_order_flow AND NOT has_linked_manufacturing_order

UNION ALL
SELECT 'internal_orders_with_later_so' AS metric, COUNT(*)::numeric AS value
FROM vw_dashboard_internal_order_traceability
WHERE linked_so_count > 0

UNION ALL
SELECT 'internal_orders_without_later_so' AS metric, COUNT(*)::numeric AS value
FROM vw_dashboard_internal_order_traceability
WHERE linked_so_count = 0

UNION ALL
SELECT 'dashboard_linked_so_count' AS metric, COALESCE(SUM(linked_so_count), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_linked_so_line_count' AS metric, COALESCE(SUM(linked_so_line_count), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_so_amount' AS metric, COALESCE(SUM(total_so_amount), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_so_ordered_qty' AS metric, COALESCE(SUM(total_so_ordered_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_so_delivered_qty' AS metric, COALESCE(SUM(total_so_delivered_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_so_invoiced_qty' AS metric, COALESCE(SUM(total_so_invoiced_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_internal_orders_with_so_line_delivery' AS metric, COUNT(*)::numeric AS value
FROM vw_dashboard_internal_order_traceability
WHERE has_delivered_so

UNION ALL
SELECT 'dashboard_internal_orders_with_so_line_invoice' AS metric, COUNT(*)::numeric AS value
FROM vw_dashboard_internal_order_traceability
WHERE has_invoiced_so

UNION ALL
SELECT 'dashboard_linked_po_line_count' AS metric, COALESCE(SUM(linked_po_line_count), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_po_ordered_qty' AS metric, COALESCE(SUM(total_po_ordered_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_po_received_qty' AS metric, COALESCE(SUM(total_po_received_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'dashboard_total_po_invoiced_qty' AS metric, COALESCE(SUM(total_po_invoiced_qty), 0)::numeric AS value
FROM vw_dashboard_internal_order_traceability

UNION ALL
SELECT 'active_out_of_scope_internal_use_count' AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics AND is_out_of_scope

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
FROM vw_approval_product_line_context
WHERE is_valid_for_procurement_request

UNION ALL
SELECT 'active_rop_lines_with_io_or_jo' AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
WHERE is_valid_for_procurement_request AND (has_internal_order OR has_job_order)

UNION ALL
SELECT 'unknown_approval_category_count' AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics AND approval_business_type = 'UNKNOWN_APPROVAL_CATEGORY'

UNION ALL
SELECT 'other_approval_category_count' AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
WHERE is_valid_for_metrics AND approval_business_type = 'OTHER_APPROVAL_CATEGORY'

UNION ALL
SELECT 'approval_category_' || LOWER(COALESCE(approval_business_type, 'unknown')) AS metric, COUNT(*)::numeric AS value
FROM vw_approval_product_line_context
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
SELECT 'manufacturing_movement_count' AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics AND is_manufacturing_movement

UNION ALL
SELECT 'finished_goods_store_movement_count' AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics AND is_finished_goods_store_movement

UNION ALL
SELECT 'delivery_movement_count' AS metric, COUNT(*)::numeric AS value
FROM vw_stock_movement_context
WHERE is_valid_for_metrics AND is_delivery_movement

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
