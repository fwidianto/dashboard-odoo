-- =============================================================================
-- Data Truth Layer - 04 Dashboard Traceability Views
-- =============================================================================
-- Purpose:
--   Dashboard-ready traceability views built only from Data Truth Layer views.
--
-- Scope:
--   Traceability and status reporting only.
--   No final profitability calculation.
--   No raw Odoo tables are overwritten.
-- =============================================================================

DROP VIEW IF EXISTS vw_dashboard_internal_order_traceability CASCADE;

CREATE OR REPLACE VIEW vw_dashboard_internal_order_traceability AS
WITH io_base AS (
    SELECT
        internal_order_id,
        internal_order_number,
        COUNT(DISTINCT internal_order_line_id) AS line_count,
        COUNT(DISTINCT internal_order_line_id) FILTER (WHERE internal_order_is_valid_for_metrics) AS active_line_count,
        COUNT(DISTINCT internal_order_line_id) FILTER (WHERE internal_order_is_cancelled) AS cancelled_line_count,
        STRING_AGG(DISTINCT internal_order_status, ', ' ORDER BY internal_order_status) AS status_summary,
        STRING_AGG(DISTINCT requester_name, ', ' ORDER BY requester_name) FILTER (
            WHERE requester_name IS NOT NULL AND BTRIM(requester_name) <> ''
        ) AS requester,
        MIN(planned_or_needed_date) AS needed_date_from,
        MAX(planned_or_needed_date) AS needed_date_to,
        COUNT(DISTINCT internal_order_product_name) FILTER (
            WHERE internal_order_product_name IS NOT NULL AND BTRIM(internal_order_product_name) <> ''
        ) AS product_count,
        BOOL_OR(internal_order_is_valid_for_metrics) AS has_active_line,
        BOOL_AND(internal_order_is_cancelled) AS all_lines_cancelled
    FROM vw_manufacturing_flow_context
    WHERE internal_order_number IS NOT NULL
    GROUP BY internal_order_id, internal_order_number
),
flow_agg AS (
    SELECT
        internal_order_id,
        internal_order_number,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE manufacturing_is_valid_for_metrics) AS linked_mo_count,
        COALESCE(SUM(manufacturing_movement_count) FILTER (WHERE manufacturing_is_valid_for_metrics), 0) AS manufacturing_movement_count,
        COALESCE(SUM(finished_goods_store_movement_count) FILTER (WHERE manufacturing_is_valid_for_metrics), 0) AS finished_goods_store_count,
        COALESCE(SUM(delivery_movement_count) FILTER (WHERE manufacturing_is_valid_for_metrics), 0) AS delivery_movement_count,
        BOOL_OR(has_manufacturing_order AND manufacturing_is_valid_for_metrics) AS has_mo,
        BOOL_OR(has_finished_goods_store_movement AND manufacturing_is_valid_for_metrics) AS has_finished_goods_store,
        BOOL_OR(has_delivery_movement AND manufacturing_is_valid_for_metrics) AS has_delivery
    FROM vw_manufacturing_flow_context
    WHERE internal_order_number IS NOT NULL
    GROUP BY internal_order_id, internal_order_number
),
sales_order_agg AS (
    SELECT
        bridge.internal_order_id AS internal_order_id,
        COUNT(DISTINCT bridge.so_id) FILTER (WHERE sor.is_valid_for_metrics) AS linked_so_count,
        COUNT(DISTINCT sor.sales_order_line_id) FILTER (WHERE sor.is_valid_for_metrics) AS linked_so_line_count,
        COALESCE(SUM(sor.line_subtotal) FILTER (WHERE sor.is_valid_for_metrics), 0) AS total_so_amount,
        COALESCE(SUM(sor.ordered_quantity) FILTER (WHERE sor.is_valid_for_metrics), 0) AS total_ordered_qty,
        COALESCE(SUM(sor.delivered_quantity) FILTER (WHERE sor.is_valid_for_metrics), 0) AS total_delivered_qty,
        COALESCE(SUM(sor.invoiced_quantity) FILTER (WHERE sor.is_valid_for_metrics), 0) AS total_invoiced_qty,
        STRING_AGG(DISTINCT sor.delivery_status, ', ' ORDER BY sor.delivery_status) FILTER (
            WHERE sor.is_valid_for_metrics
              AND sor.delivery_status IS NOT NULL
              AND BTRIM(sor.delivery_status) <> ''
        ) AS delivery_status_summary,
        STRING_AGG(DISTINCT sor.invoice_status, ', ' ORDER BY sor.invoice_status) FILTER (
            WHERE sor.is_valid_for_metrics
              AND sor.invoice_status IS NOT NULL
              AND BTRIM(sor.invoice_status) <> ''
        ) AS invoice_status_summary
    FROM vw_sale_order_internal_order_bridge bridge
    JOIN vw_sales_order_revenue sor
        ON sor.sales_order_id = bridge.so_id
    GROUP BY bridge.internal_order_id
),
procurement_agg AS (
    SELECT
        io.internal_order_id,
        COUNT(DISTINCT procurement.procurement_line_id) FILTER (WHERE procurement.is_valid_for_metrics) AS linked_po_line_count,
        COALESCE(SUM(procurement.ordered_quantity) FILTER (WHERE procurement.is_valid_for_metrics), 0) AS total_po_ordered_qty,
        COALESCE(SUM(procurement.received_quantity) FILTER (WHERE procurement.is_valid_for_metrics), 0) AS total_po_received_qty,
        COALESCE(SUM(procurement.invoiced_quantity) FILTER (WHERE procurement.is_valid_for_metrics), 0) AS total_po_invoiced_qty,
        STRING_AGG(DISTINCT procurement.purchase_line_state, ', ' ORDER BY procurement.purchase_line_state) FILTER (
            WHERE procurement.is_valid_for_metrics
              AND procurement.purchase_line_state IS NOT NULL
              AND BTRIM(procurement.purchase_line_state) <> ''
        ) AS purchase_status_summary
    FROM io_base io
    JOIN vw_procurement_lines procurement
        ON procurement.internal_order_number = io.internal_order_number
    GROUP BY io.internal_order_id
),
accounting_agg AS (
    SELECT
        bridge.internal_order_id AS internal_order_id,
        COUNT(DISTINCT accounting.accounting_line_id) FILTER (WHERE accounting.is_valid_for_metrics) AS accounting_line_count
    FROM vw_sale_order_internal_order_bridge bridge
    JOIN vw_sales_order_revenue sor
        ON sor.sales_order_id = bridge.so_id
    JOIN vw_accounting_sales_lines accounting
        ON accounting.inferred_sales_order_id = bridge.so_id
    GROUP BY bridge.internal_order_id
)
SELECT
    io.internal_order_id,
    io.internal_order_number,
    io.line_count,
    io.status_summary,
    io.requester,
    io.needed_date_from,
    io.needed_date_to,
    io.product_count,
    COALESCE(flow.linked_mo_count, 0) AS linked_mo_count,
    COALESCE(flow.manufacturing_movement_count, 0) AS manufacturing_movement_count,
    COALESCE(flow.finished_goods_store_count, 0) AS finished_goods_store_count,
    COALESCE(flow.delivery_movement_count, 0) AS delivery_movement_count,
    COALESCE(sales_order.linked_so_count, 0) AS linked_so_count,
    COALESCE(sales_order.linked_so_count, 0) AS later_so_count,
    COALESCE(sales_order.linked_so_line_count, 0) AS linked_so_line_count,
    COALESCE(sales_order.total_so_amount, 0) AS total_so_amount,
    COALESCE(sales_order.total_ordered_qty, 0) AS total_so_ordered_qty,
    COALESCE(sales_order.total_ordered_qty, 0) AS total_ordered_qty,
    COALESCE(sales_order.total_delivered_qty, 0) AS total_so_delivered_qty,
    COALESCE(sales_order.total_delivered_qty, 0) AS total_delivered_qty,
    COALESCE(sales_order.total_invoiced_qty, 0) AS total_so_invoiced_qty,
    COALESCE(sales_order.total_invoiced_qty, 0) AS total_invoiced_qty,
    CASE
        WHEN COALESCE(sales_order.total_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(sales_order.total_delivered_qty, 0) / NULLIF(sales_order.total_ordered_qty, 0)
    END AS so_delivery_progress_ratio,
    CASE
        WHEN COALESCE(sales_order.total_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(sales_order.total_delivered_qty, 0) / NULLIF(sales_order.total_ordered_qty, 0)
    END AS delivery_progress_ratio,
    CASE
        WHEN COALESCE(sales_order.total_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(sales_order.total_invoiced_qty, 0) / NULLIF(sales_order.total_ordered_qty, 0)
    END AS so_invoice_progress_ratio,
    CASE
        WHEN COALESCE(sales_order.total_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(sales_order.total_invoiced_qty, 0) / NULLIF(sales_order.total_ordered_qty, 0)
    END AS invoice_progress_ratio,
    (COALESCE(sales_order.total_delivered_qty, 0) > 0) AS has_delivered_so,
    (COALESCE(sales_order.total_delivered_qty, 0) > 0) AS has_delivery_from_so_line,
    (COALESCE(sales_order.total_invoiced_qty, 0) > 0) AS has_invoiced_so,
    (COALESCE(sales_order.total_invoiced_qty, 0) > 0) AS has_invoice_from_so_line,
    sales_order.delivery_status_summary,
    sales_order.invoice_status_summary,
    COALESCE(procurement.linked_po_line_count, 0) AS linked_po_line_count,
    COALESCE(procurement.total_po_ordered_qty, 0) AS total_po_ordered_qty,
    COALESCE(procurement.total_po_received_qty, 0) AS total_po_received_qty,
    COALESCE(procurement.total_po_invoiced_qty, 0) AS total_po_invoiced_qty,
    CASE
        WHEN COALESCE(procurement.total_po_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(procurement.total_po_received_qty, 0) / NULLIF(procurement.total_po_ordered_qty, 0)
    END AS po_receipt_progress_ratio,
    CASE
        WHEN COALESCE(procurement.total_po_ordered_qty, 0) = 0 THEN NULL
        ELSE COALESCE(procurement.total_po_invoiced_qty, 0) / NULLIF(procurement.total_po_ordered_qty, 0)
    END AS po_invoice_progress_ratio,
    procurement.purchase_status_summary,
    COALESCE(accounting.accounting_line_count, 0) AS accounting_line_count,
    CASE
        WHEN io.all_lines_cancelled THEN 'CANCELLED_RECORD'
        WHEN COALESCE(accounting.accounting_line_count, 0) > 0 THEN 'HAS_ACCOUNTING_LINK'
        WHEN COALESCE(sales_order.total_invoiced_qty, 0) > 0 THEN 'HAS_INVOICED_SO'
        WHEN COALESCE(sales_order.total_delivered_qty, 0) > 0 THEN 'HAS_DELIVERED_SO'
        WHEN COALESCE(sales_order.linked_so_count, 0) > 0 THEN 'HAS_LINKED_SO'
        WHEN COALESCE(flow.has_mo, FALSE) THEN 'HAS_MO_NO_SO_YET'
        WHEN NOT COALESCE(flow.has_mo, FALSE)
          AND (
              io.status_summary ILIKE '%new%'
              OR io.status_summary ILIKE '%to submit%'
              OR io.status_summary ILIKE '%draft%'
          )
            THEN 'NEW_OR_TO_SUBMIT_NO_MO'
        WHEN NOT COALESCE(flow.has_mo, FALSE) THEN 'OLD_OR_UNLINKED_NO_MO'
        ELSE 'READY_FOR_MANUFACTURING_TRACE'
    END AS traceability_status
FROM io_base io
LEFT JOIN flow_agg flow
    ON flow.internal_order_id = io.internal_order_id
LEFT JOIN sales_order_agg sales_order
    ON sales_order.internal_order_id = io.internal_order_id
LEFT JOIN procurement_agg procurement
    ON procurement.internal_order_id = io.internal_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.internal_order_id = io.internal_order_id;

COMMENT ON VIEW vw_dashboard_internal_order_traceability IS
    'Dashboard-ready Internal Order traceability view at one row per Internal Order number. V1 delivery/invoicing readiness is measured from linked SO lines, procurement receipt/billing progress is measured from PO lines, and stock movement counts are optional diagnostics. Internal Order to SO uses parsed sale_order.x_studio_io_1 many-to-many bridge, not MO-to-SO inference. INTERNAL_ORDER_WITHOUT_MO is status/follow-up, not invalid data. No profitability calculation.';
