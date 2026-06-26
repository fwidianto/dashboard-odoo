-- =============================================================================
-- Phase 2A - Sales Order Dashboard Views
-- =============================================================================
-- Purpose:
--   Dashboard-ready Sales Order traceability view.
--   Phase 2A is scoped to PT Nobi Putra Angkasa only.
--
-- Scope:
--   Traceability, delivery progress, invoice progress, source classification,
--   and operational follow-up only.
--
-- Explicitly out of scope:
--   Profitability, AR/payment state, COGS, margin, estimator cost, and
--   accounting-based status.
--
-- Company scope:
--   The current extracted sale_order.company_id column stores the Odoo display
--   value, not a numeric company ID. The view still filters on company_id at
--   SQL level using the extracted company_id value for PT Nobi Putra Angkasa.
-- =============================================================================

DROP VIEW IF EXISTS vw_dashboard_sales_order_traceability CASCADE;

CREATE OR REPLACE VIEW vw_dashboard_sales_order_traceability AS
WITH line_base AS (
    SELECT
        line.sales_order_id,
        line.sales_order_number,
        line.sales_order_line_id,
        line.product_name,
        line.line_description,
        COALESCE(line.ordered_quantity, 0)::numeric AS ordered_qty,
        COALESCE(line.delivered_quantity, 0)::numeric AS delivered_qty,
        COALESCE(line.invoiced_quantity, 0)::numeric AS invoiced_qty,
        COALESCE(sol.price_unit, 0)::numeric AS unit_price,
        (COALESCE(line.ordered_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS ordered_amount,
        (COALESCE(line.delivered_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS delivered_amount,
        (COALESCE(line.invoiced_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS invoiced_amount,
        line.line_source_type,
        line.line_source_link_status,
        line.line_source_confidence,
        line.internal_order_reference_count,
        line.matching_mo_count,
        line.matching_stock_movement_count,
        line.unknown_movement_count
    FROM vw_sales_order_line_source_context line
    LEFT JOIN sale_order_line sol
        ON sol.id = line.sales_order_line_id
),
line_agg AS (
    SELECT
        sales_order_id,
        sales_order_number,
        COUNT(*) AS sales_order_line_count,
        COALESCE(SUM(ordered_qty), 0)::numeric AS ordered_qty,
        COALESCE(SUM(delivered_qty), 0)::numeric AS delivered_qty,
        COALESCE(SUM(invoiced_qty), 0)::numeric AS invoiced_qty,
        COALESCE(SUM(ordered_amount), 0)::numeric AS ordered_amount,
        COALESCE(SUM(delivered_amount), 0)::numeric AS delivered_amount,
        COALESCE(SUM(invoiced_amount), 0)::numeric AS invoiced_amount,
        COALESCE(SUM(internal_order_reference_count), 0)::integer AS line_internal_order_reference_count,
        COALESCE(SUM(matching_mo_count), 0)::integer AS line_matching_mo_count,
        COALESCE(SUM(matching_stock_movement_count), 0)::integer AS line_stock_movement_count,
        COALESCE(SUM(unknown_movement_count), 0)::integer AS line_unknown_movement_count,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'sales_order_line_id', sales_order_line_id,
                'product_name', product_name,
                'line_description', line_description,
                'ordered_qty', ordered_qty,
                'delivered_qty', delivered_qty,
                'invoiced_qty', invoiced_qty,
                'unit_price', unit_price,
                'ordered_amount', ordered_amount,
                'delivered_amount', delivered_amount,
                'invoiced_amount', invoiced_amount,
                'qty_delivery_progress_ratio', delivered_qty / NULLIF(ordered_qty, 0),
                'qty_invoice_progress_ratio', invoiced_qty / NULLIF(ordered_qty, 0),
                'amount_delivery_progress_ratio', delivered_amount / NULLIF(ordered_amount, 0),
                'amount_invoice_progress_ratio', invoiced_amount / NULLIF(ordered_amount, 0),
                'line_source_type', line_source_type,
                'line_source_link_status', line_source_link_status,
                'line_source_confidence', line_source_confidence
            )
            ORDER BY sales_order_line_id
        ) AS sales_order_lines
    FROM line_base
    GROUP BY sales_order_id, sales_order_number
),
io_agg AS (
    SELECT
        bridge.so_id AS sales_order_id,
        COUNT(DISTINCT bridge.internal_order_id) AS internal_order_count,
        JSONB_AGG(
            DISTINCT JSONB_BUILD_OBJECT(
                'internal_order_id', bridge.internal_order_id,
                'internal_order_number', ar.name,
                'raw_x_studio_io_1', bridge.raw_x_studio_io_1
            )
        ) FILTER (WHERE bridge.internal_order_id IS NOT NULL) AS internal_orders
    FROM vw_sale_order_internal_order_bridge bridge
    LEFT JOIN approval_request ar
        ON ar.id = bridge.internal_order_id
    GROUP BY bridge.so_id
),
mo_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT manufacturing_order_id) AS manufacturing_order_count,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE manufacturing_source_type = 'JO_BASED_MO') AS job_order_mo_count,
        JSONB_AGG(
            DISTINCT JSONB_BUILD_OBJECT(
                'manufacturing_order_id', manufacturing_order_id,
                'manufacturing_order_number', manufacturing_order_number,
                'manufacturing_order_state', manufacturing_order_state,
                'manufactured_product_name', manufactured_product_name,
                'manufacturing_quantity', manufacturing_quantity,
                'origin', manufacturing_origin,
                'internal_order_number', internal_order_number,
                'job_order_number', normalized_jo_number,
                'manufacturing_source_type', manufacturing_source_type
            )
        ) FILTER (WHERE manufacturing_order_id IS NOT NULL) AS manufacturing_orders
    FROM vw_mrp_order_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
),
accounting_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT accounting_line_id) AS accounting_line_count
    FROM vw_accounting_sales_lines
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
),
source_summary AS (
    SELECT
        sales_order_id,
        sales_order_source_type,
        sales_order_source_link_status,
        from_internal_order_line_count,
        from_stock_line_count,
        make_to_order_line_count,
        mixed_source_line_count,
        unknown_source_line_count
    FROM vw_sales_order_source_summary
),
so_base AS (
    SELECT
        so.id AS sales_order_id,
        so.name AS sales_order_number,
        so.company_id AS company_id,
        so.partner_id AS customer_name,
        so.date_order AS order_date,
        so.commitment_date,
        so.state AS sales_order_state,
        UPPER(COALESCE(so.state, 'UNKNOWN')) AS normalized_status,
        (LOWER(COALESCE(so.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
        (LOWER(COALESCE(so.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
        so.delivery_status,
        so.invoice_status,
        so.x_studio_product_type AS product_type_raw,
        CASE
            WHEN so.x_studio_product_type IS NULL THEN 'Unknown Product Type'
            WHEN TRIM(so.x_studio_product_type::text) IN ('', '{}', 'New') THEN 'Unknown Product Type'
            WHEN TRIM(so.x_studio_product_type::text) = '1' THEN 'Cable Tray'
            WHEN TRIM(so.x_studio_product_type::text) = '2' THEN 'Empty Panel'
            WHEN TRIM(so.x_studio_product_type::text) = '3' THEN 'Pole/Structure'
            WHEN TRIM(so.x_studio_product_type::text) = '4' THEN 'Electrical Panel'
            WHEN TRIM(so.x_studio_product_type::text) = '5' THEN 'Lamp'
            WHEN TRIM(so.x_studio_product_type::text) = '6' THEN 'Scaffolding'
            WHEN TRIM(so.x_studio_product_type::text) = 'Electrical Service' THEN 'Electrical Service'
            ELSE 'Other Product Type'
        END AS product_type_label,
        so.x_studio_io_1 AS raw_internal_order_reference
    FROM sale_order so
    WHERE so.company_id::text = 'Nobi Putra Angkasa, PT'
)
SELECT
    so.sales_order_id,
    so.sales_order_number,
    so.company_id,
    so.customer_name,
    so.order_date,
    so.commitment_date,
    so.sales_order_state,
    so.normalized_status,
    so.is_cancelled,
    so.is_valid_for_metrics,
    so.delivery_status,
    so.invoice_status,
    so.product_type_raw,
    so.product_type_label,
    so.raw_internal_order_reference,
    COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') AS source_type,
    COALESCE(source.sales_order_source_link_status, 'UNKNOWN_NO_MATCHED_LINES') AS source_link_status,
    COALESCE(source.from_internal_order_line_count, 0) AS from_internal_order_line_count,
    COALESCE(source.from_stock_line_count, 0) AS from_stock_line_count,
    COALESCE(source.make_to_order_line_count, 0) AS make_to_order_line_count,
    COALESCE(source.mixed_source_line_count, 0) AS mixed_source_line_count,
    COALESCE(source.unknown_source_line_count, 0) AS unknown_source_line_count,
    COALESCE(line.sales_order_line_count, 0) AS sales_order_line_count,
    COALESCE(line.ordered_qty, 0) AS ordered_qty,
    COALESCE(line.delivered_qty, 0) AS delivered_qty,
    COALESCE(line.invoiced_qty, 0) AS invoiced_qty,
    COALESCE(line.ordered_amount, 0) AS ordered_amount,
    COALESCE(line.delivered_amount, 0) AS delivered_amount,
    COALESCE(line.invoiced_amount, 0) AS invoiced_amount,
    COALESCE(line.delivered_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0) AS qty_delivery_progress_ratio,
    COALESCE(line.invoiced_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0) AS qty_invoice_progress_ratio,
    COALESCE(line.delivered_amount, 0) / NULLIF(COALESCE(line.ordered_amount, 0), 0) AS amount_delivery_progress_ratio,
    COALESCE(line.invoiced_amount, 0) / NULLIF(COALESCE(line.ordered_amount, 0), 0) AS amount_invoice_progress_ratio,
    (COALESCE(line.delivered_qty, 0) >= COALESCE(line.ordered_qty, 0) AND COALESCE(line.ordered_qty, 0) > 0) AS is_fully_delivered_qty,
    (COALESCE(line.invoiced_qty, 0) >= COALESCE(line.ordered_qty, 0) AND COALESCE(line.ordered_qty, 0) > 0) AS is_fully_invoiced_qty,
    (COALESCE(line.delivered_amount, 0) >= COALESCE(line.ordered_amount, 0) AND COALESCE(line.ordered_amount, 0) > 0) AS is_fully_delivered_amount,
    (COALESCE(line.invoiced_amount, 0) >= COALESCE(line.ordered_amount, 0) AND COALESCE(line.ordered_amount, 0) > 0) AS is_fully_invoiced_amount,
    (COALESCE(line.delivered_qty, 0) > 0) AS has_delivered_qty,
    (COALESCE(line.invoiced_qty, 0) > 0) AS has_invoiced_qty,
    COALESCE(io.internal_order_count, 0) AS internal_order_count,
    COALESCE(mo.manufacturing_order_count, 0) AS manufacturing_order_count,
    COALESCE(mo.job_order_mo_count, 0) AS job_order_mo_count,
    COALESCE(accounting.accounting_line_count, 0) AS accounting_line_count,
    COALESCE(line.line_stock_movement_count, 0) AS stock_movement_diagnostic_count,
    COALESCE(line.line_unknown_movement_count, 0) AS unknown_movement_diagnostic_count,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'UNKNOWN_SOURCE' THEN 'UNKNOWN_SOURCE'
        WHEN so.commitment_date::date < CURRENT_DATE
          AND COALESCE(line.delivered_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 'DELAYED_DELIVERY'
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'MAKE_TO_ORDER'
          AND COALESCE(mo.manufacturing_order_count, 0) = 0 THEN 'WAITING_PRODUCTION'
        WHEN COALESCE(line.delivered_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 'WAITING_DELIVERY'
        WHEN COALESCE(line.delivered_qty, 0) > 0
          AND COALESCE(line.invoiced_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 'WAITING_INVOICE'
        ELSE 'COMPLETED'
    END AS follow_up_status,
    CASE
        WHEN NOT so.is_valid_for_metrics THEN 1
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'UNKNOWN_SOURCE' THEN 2
        WHEN so.commitment_date::date < CURRENT_DATE
          AND COALESCE(line.delivered_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 3
        WHEN COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') = 'MAKE_TO_ORDER'
          AND COALESCE(mo.manufacturing_order_count, 0) = 0 THEN 4
        WHEN COALESCE(line.delivered_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 5
        WHEN COALESCE(line.delivered_qty, 0) > 0
          AND COALESCE(line.invoiced_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 6
        ELSE 7
    END AS follow_up_status_priority,
    COALESCE(line.sales_order_lines, '[]'::jsonb) AS sales_order_lines,
    COALESCE(io.internal_orders, '[]'::jsonb) AS internal_orders,
    COALESCE(mo.manufacturing_orders, '[]'::jsonb) AS manufacturing_orders,
    JSONB_BUILD_OBJECT(
        'company_id', so.company_id,
        'product_type_raw', so.product_type_raw,
        'product_type_label', so.product_type_label,
        'delivery_status', so.delivery_status,
        'invoice_status', so.invoice_status,
        'source_link_status', COALESCE(source.sales_order_source_link_status, 'UNKNOWN_NO_MATCHED_LINES'),
        'stock_movement_diagnostic_count', COALESCE(line.line_stock_movement_count, 0),
        'unknown_movement_diagnostic_count', COALESCE(line.line_unknown_movement_count, 0),
        'accounting_line_count_out_of_scope', COALESCE(accounting.accounting_line_count, 0)
    ) AS diagnostics
FROM so_base so
LEFT JOIN line_agg line
    ON line.sales_order_id = so.sales_order_id
LEFT JOIN source_summary source
    ON source.sales_order_id = so.sales_order_id
LEFT JOIN io_agg io
    ON io.sales_order_id = so.sales_order_id
LEFT JOIN mo_agg mo
    ON mo.sales_order_id = so.sales_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.sales_order_id = so.sales_order_id;

COMMENT ON VIEW vw_dashboard_sales_order_traceability IS
    'Phase 2A dashboard-ready Sales Order traceability view for PT Nobi Putra Angkasa only. Quantity progress uses SO line quantities; amount progress uses qty * price_unit. Delay uses sale_order.commitment_date. Accounting/AR and profitability are out of scope; accounting count is diagnostic only.';
