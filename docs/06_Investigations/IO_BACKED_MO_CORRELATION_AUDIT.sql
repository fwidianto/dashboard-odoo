-- =============================================================================
-- Phase 2A.1 - IO-backed Manufacturing Correlation Audit
-- =============================================================================
-- Purpose:
--   Pre-change / post-change validation checks for Sales Order -> IO -> MO
--   correlation. These checks are correlation-only and must not be interpreted
--   as allocation of IO-backed MO quantity to an individual Sales Order.
--
-- Scope:
--   PT Nobi Putra Angkasa Sales Orders, matching the Sales Order dashboard view.
-- =============================================================================

WITH so_scope AS (
    SELECT
        id AS sales_order_id,
        name AS sales_order_number
    FROM sale_order
    WHERE company_id::text = 'Nobi Putra Angkasa, PT'
),
line_agg AS (
    SELECT
        sales_order_id,
        COALESCE(SUM(COALESCE(ordered_quantity, 0)), 0)::numeric AS ordered_qty,
        COALESCE(SUM(COALESCE(delivered_quantity, 0)), 0)::numeric AS delivered_qty,
        COALESCE(SUM(COALESCE(invoiced_quantity, 0)), 0)::numeric AS invoiced_qty
    FROM vw_sales_order_line_source_context
    GROUP BY sales_order_id
),
so_io_links AS (
    SELECT DISTINCT
        bridge.so_id AS sales_order_id,
        bridge.so_number AS sales_order_number,
        bridge.internal_order_id,
        COALESCE(NULLIF(BTRIM(ar.name::text), ''), bridge.internal_order_id::text) AS internal_order_number
    FROM vw_sale_order_internal_order_bridge bridge
    JOIN so_scope so
        ON so.sales_order_id = bridge.so_id
    LEFT JOIN approval_request ar
        ON ar.id = bridge.internal_order_id
    WHERE bridge.internal_order_id IS NOT NULL
),
io_linked_so_qty AS (
    SELECT
        links.internal_order_id,
        links.internal_order_number,
        COUNT(DISTINCT links.sales_order_id) AS linked_so_count,
        COALESCE(SUM(COALESCE(line.ordered_qty, 0)), 0)::numeric AS linked_so_ordered_qty,
        COALESCE(SUM(COALESCE(line.delivered_qty, 0)), 0)::numeric AS linked_so_delivered_qty,
        COALESCE(SUM(COALESCE(line.invoiced_qty, 0)), 0)::numeric AS linked_so_invoiced_qty
    FROM so_io_links links
    LEFT JOIN line_agg line
        ON line.sales_order_id = links.sales_order_id
    GROUP BY links.internal_order_id, links.internal_order_number
),
io_mo_rows AS (
    SELECT DISTINCT
        io.internal_order_id,
        io.internal_order_number,
        mo.manufacturing_order_id,
        COALESCE(mo.manufacturing_quantity, 0)::numeric AS manufacturing_quantity
    FROM (
        SELECT DISTINCT internal_order_id, internal_order_number
        FROM so_io_links
    ) io
    LEFT JOIN vw_mrp_order_context mo
        ON NULLIF(BTRIM(mo.internal_order_number), '') IS NOT NULL
       AND (
            BTRIM(mo.internal_order_number) = io.internal_order_number
            OR BTRIM(mo.internal_order_number) = io.internal_order_id::text
       )
       AND mo.manufacturing_source_type = 'IO_BASED_MO'
       AND mo.is_valid_for_metrics
),
io_mo_agg AS (
    SELECT
        internal_order_id,
        internal_order_number,
        COUNT(DISTINCT manufacturing_order_id) AS io_mo_count,
        COALESCE(SUM(manufacturing_quantity) FILTER (WHERE manufacturing_order_id IS NOT NULL), 0)::numeric AS io_mo_qty
    FROM io_mo_rows
    GROUP BY internal_order_id, internal_order_number
),
io_correlation AS (
    SELECT
        qty.internal_order_id,
        qty.internal_order_number,
        qty.linked_so_count,
        qty.linked_so_ordered_qty,
        qty.linked_so_delivered_qty,
        qty.linked_so_invoiced_qty,
        COALESCE(mo.io_mo_count, 0) AS io_mo_count,
        COALESCE(mo.io_mo_qty, 0)::numeric AS io_mo_qty
    FROM io_linked_so_qty qty
    LEFT JOIN io_mo_agg mo
        ON mo.internal_order_id = qty.internal_order_id
       AND mo.internal_order_number = qty.internal_order_number
),
direct_so_mo AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT manufacturing_order_id) AS direct_mo_count
    FROM vw_mrp_order_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
      AND manufacturing_source_type IN ('SO_BASED_MO', 'JO_BASED_MO')
    GROUP BY inferred_sales_order_id
)
SELECT 'sales_orders_linked_to_at_least_one_io' AS metric, COUNT(DISTINCT sales_order_id)::numeric AS value
FROM so_io_links
UNION ALL
SELECT 'linked_ios_with_at_least_one_io_based_mo' AS metric, COUNT(*)::numeric AS value
FROM io_correlation
WHERE io_mo_count > 0
UNION ALL
SELECT 'shared_ios_more_than_one_so' AS metric, COUNT(*)::numeric AS value
FROM io_correlation
WHERE linked_so_count > 1
UNION ALL
SELECT 'ios_io_mo_qty_gt_linked_so_ordered_qty' AS metric, COUNT(*)::numeric AS value
FROM io_correlation
WHERE io_mo_count > 0
  AND io_mo_qty > linked_so_ordered_qty
UNION ALL
SELECT 'ios_linked_so_ordered_qty_gt_io_mo_qty' AS metric, COUNT(*)::numeric AS value
FROM io_correlation
WHERE io_mo_count > 0
  AND linked_so_ordered_qty > io_mo_qty
UNION ALL
SELECT 'previously_missing_so_mo_relations_now_visible_from_io' AS metric, COUNT(DISTINCT links.sales_order_id)::numeric AS value
FROM so_io_links links
JOIN io_correlation corr
    ON corr.internal_order_id = links.internal_order_id
   AND corr.internal_order_number = links.internal_order_number
LEFT JOIN direct_so_mo direct_mo
    ON direct_mo.sales_order_id = links.sales_order_id
WHERE COALESCE(direct_mo.direct_mo_count, 0) = 0
  AND corr.io_mo_count > 0;

-- Optional detail sample for shared or imbalanced IOs.
-- SELECT *
-- FROM io_correlation
-- WHERE linked_so_count > 1
--    OR io_mo_qty <> linked_so_ordered_qty
-- ORDER BY linked_so_count DESC, internal_order_number
-- LIMIT 100;
