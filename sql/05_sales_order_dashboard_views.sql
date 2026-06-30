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
        COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0), 1)::numeric AS currency_rate_used,
        CASE
            WHEN COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0)) IS NULL
                THEN 'IDR_FALLBACK_RATE_1'
            ELSE 'SALE_ORDER_CURRENCY_RATE_MULTIPLIED_TO_IDR'
        END AS currency_conversion_basis,
        (COALESCE(line.ordered_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS ordered_amount,
        (COALESCE(line.delivered_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS delivered_amount,
        (COALESCE(line.invoiced_quantity, 0) * COALESCE(sol.price_unit, 0))::numeric AS invoiced_amount,
        (COALESCE(sol.price_unit, 0) * COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0), 1))::numeric AS unit_price_idr,
        (COALESCE(line.ordered_quantity, 0) * COALESCE(sol.price_unit, 0) * COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0), 1))::numeric AS ordered_amount_idr,
        (COALESCE(line.delivered_quantity, 0) * COALESCE(sol.price_unit, 0) * COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0), 1))::numeric AS delivered_amount_idr,
        (COALESCE(line.invoiced_quantity, 0) * COALESCE(sol.price_unit, 0) * COALESCE(NULLIF(so_line.currency_rate, 0), NULLIF(sol.x_studio_currency_rate, 0), 1))::numeric AS invoiced_amount_idr,
        CASE
            WHEN line.product_name IS NULL OR BTRIM(line.product_name::text) = '' THEN FALSE
            WHEN BTRIM(line.product_name::text) = '-' THEN FALSE
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%down payment%' THEN FALSE
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%downpayment%' THEN FALSE
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%advance payment%' THEN FALSE
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%uang muka%' THEN FALSE
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) ~ '(^|[^a-z0-9])dp([^a-z0-9]|$)' THEN FALSE
            ELSE TRUE
        END AS is_countable_sales_line,
        CASE
            WHEN line.product_name IS NULL OR BTRIM(line.product_name::text) = '' THEN 'Excluded - No Product'
            WHEN BTRIM(line.product_name::text) = '-' THEN 'Excluded - Placeholder'
            WHEN LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%down payment%'
              OR LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%downpayment%'
              OR LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%advance payment%'
              OR LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) LIKE '%uang muka%'
              OR LOWER(COALESCE(line.product_name::text, '') || ' ' || COALESCE(line.line_description::text, '')) ~ '(^|[^a-z0-9])dp([^a-z0-9]|$)' THEN 'Excluded - Down Payment'
            ELSE 'Counted'
        END AS progress_basis,
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
    LEFT JOIN sale_order so_line
        ON so_line.id = line.sales_order_id
),
line_agg AS (
    SELECT
        sales_order_id,
        sales_order_number,
        COUNT(*) AS sales_order_line_count,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN ordered_qty ELSE 0 END), 0)::numeric AS ordered_qty,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN delivered_qty ELSE 0 END), 0)::numeric AS delivered_qty,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN invoiced_qty ELSE 0 END), 0)::numeric AS invoiced_qty,
        COALESCE(SUM(CASE WHEN is_countable_sales_line AND line_source_type = 'FROM_INTERNAL_ORDER' THEN delivered_qty ELSE 0 END), 0)::numeric AS delivered_qty_from_internal_order,
        COALESCE(SUM(CASE WHEN is_countable_sales_line AND line_source_type = 'FROM_STOCK' THEN delivered_qty ELSE 0 END), 0)::numeric AS delivered_qty_from_stock,
        COALESCE(SUM(CASE WHEN is_countable_sales_line AND line_source_type = 'MAKE_TO_ORDER' THEN delivered_qty ELSE 0 END), 0)::numeric AS delivered_qty_make_to_order,
        COALESCE(SUM(CASE WHEN is_countable_sales_line AND line_source_type = 'MIXED_SOURCE' THEN delivered_qty ELSE 0 END), 0)::numeric AS delivered_qty_mixed_source,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN ordered_amount ELSE 0 END), 0)::numeric AS ordered_amount,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN delivered_amount ELSE 0 END), 0)::numeric AS delivered_amount,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN invoiced_amount ELSE 0 END), 0)::numeric AS invoiced_amount,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN ordered_amount_idr ELSE 0 END), 0)::numeric AS ordered_amount_idr,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN delivered_amount_idr ELSE 0 END), 0)::numeric AS delivered_amount_idr,
        COALESCE(SUM(CASE WHEN is_countable_sales_line THEN invoiced_amount_idr ELSE 0 END), 0)::numeric AS invoiced_amount_idr,
        COALESCE(MAX(currency_rate_used), 1)::numeric AS currency_rate_used,
        COALESCE(MAX(currency_conversion_basis), 'IDR_FALLBACK_RATE_1') AS currency_conversion_basis,
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
                'unit_price_idr', unit_price_idr,
                'ordered_amount', ordered_amount,
                'delivered_amount', delivered_amount,
                'invoiced_amount', invoiced_amount,
                'ordered_amount_idr', ordered_amount_idr,
                'delivered_amount_idr', delivered_amount_idr,
                'invoiced_amount_idr', invoiced_amount_idr,
                'currency_rate_used', currency_rate_used,
                'currency_conversion_basis', currency_conversion_basis,
                'is_countable_sales_line', is_countable_sales_line,
                'progress_basis', progress_basis,
                'qty_delivery_progress_ratio', CASE WHEN is_countable_sales_line AND ordered_qty > 0 THEN LEAST(delivered_qty / NULLIF(ordered_qty, 0), 1.0::numeric) END,
                'qty_invoice_progress_ratio', CASE WHEN is_countable_sales_line AND ordered_qty > 0 THEN LEAST(invoiced_qty / NULLIF(ordered_qty, 0), 1.0::numeric) END,
                'amount_delivery_progress_ratio', CASE WHEN is_countable_sales_line AND ordered_amount_idr > 0 THEN LEAST(delivered_amount_idr / NULLIF(ordered_amount_idr, 0), 1.0::numeric) END,
                'amount_invoice_progress_ratio', CASE WHEN is_countable_sales_line AND ordered_amount_idr > 0 THEN LEAST(invoiced_amount_idr / NULLIF(ordered_amount_idr, 0), 1.0::numeric) END,
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
        COUNT(DISTINCT bridge.internal_order_id) AS internal_order_count
    FROM vw_sale_order_internal_order_bridge bridge
    WHERE bridge.internal_order_id IS NOT NULL
    GROUP BY bridge.so_id
),
so_io_links AS (
    SELECT DISTINCT
        bridge.so_id AS sales_order_id,
        bridge.internal_order_id,
        COALESCE(NULLIF(BTRIM(ar.name::text), ''), bridge.internal_order_id::text) AS internal_order_number
    FROM vw_sale_order_internal_order_bridge bridge
    JOIN sale_order so_scope
        ON so_scope.id = bridge.so_id
       AND so_scope.company_id::text = 'Nobi Putra Angkasa, PT'
    LEFT JOIN approval_request ar
        ON ar.id = bridge.internal_order_id
    WHERE bridge.internal_order_id IS NOT NULL
),
so_io_link_counts AS (
    SELECT
        sales_order_id,
        COUNT(DISTINCT internal_order_id) AS linked_io_count
    FROM so_io_links
    GROUP BY sales_order_id
),
io_linked_so_qty AS (
    SELECT
        internal_order_id,
        internal_order_number,
        COUNT(DISTINCT sales_order_id) AS linked_so_count,
        COUNT(DISTINCT sales_order_id) FILTER (WHERE linked_io_count > 1) AS multi_io_so_count,
        BOOL_OR(linked_io_count > 1) AS has_multi_io_so,
        'FULL_SO_QTY_UNALLOCATED'::text AS linked_so_qty_basis,
        COALESCE(SUM(ordered_qty), 0)::numeric AS linked_so_ordered_qty,
        COALESCE(SUM(delivered_qty), 0)::numeric AS linked_so_delivered_qty,
        COALESCE(SUM(invoiced_qty), 0)::numeric AS linked_so_invoiced_qty
    FROM (
        SELECT DISTINCT
            links.internal_order_id,
            links.internal_order_number,
            links.sales_order_id,
            COALESCE(counts.linked_io_count, 1) AS linked_io_count,
            COALESCE(line.ordered_qty, 0)::numeric AS ordered_qty,
            COALESCE(line.delivered_qty, 0)::numeric AS delivered_qty,
            COALESCE(line.invoiced_qty, 0)::numeric AS invoiced_qty
        FROM so_io_links links
        LEFT JOIN so_io_link_counts counts
            ON counts.sales_order_id = links.sales_order_id
        LEFT JOIN line_agg line
            ON line.sales_order_id = links.sales_order_id
    ) linked_so
    GROUP BY internal_order_id, internal_order_number
),
io_multi_io_so_links AS (
    SELECT DISTINCT
        links.internal_order_id,
        links.internal_order_number,
        links.sales_order_id AS multi_io_sales_order_id
    FROM so_io_links links
    JOIN so_io_link_counts counts
        ON counts.sales_order_id = links.sales_order_id
    WHERE counts.linked_io_count > 1
),
so_multi_io_context AS (
    SELECT
        dashboard_links.sales_order_id,
        COUNT(DISTINCT multi_links.multi_io_sales_order_id) AS multi_io_so_count,
        (COUNT(DISTINCT multi_links.multi_io_sales_order_id) > 0) AS has_multi_io_so
    FROM so_io_links dashboard_links
    JOIN io_multi_io_so_links multi_links
        ON multi_links.internal_order_id = dashboard_links.internal_order_id
       AND multi_links.internal_order_number = dashboard_links.internal_order_number
    GROUP BY dashboard_links.sales_order_id
),
io_mo_rows AS (
    -- IO-backed MO quantity is correlation-only. It is not allocated to any
    -- individual Sales Order because one IO may serve multiple SOs.
    SELECT DISTINCT
        io.internal_order_id,
        io.internal_order_number,
        mo.manufacturing_order_id,
        mo.manufacturing_order_number,
        mo.manufacturing_order_state,
        mo.manufactured_product_name,
        COALESCE(mo.manufacturing_quantity, 0)::numeric AS manufacturing_quantity,
        COALESCE(mo.cost_of_analysis, 0)::numeric AS cost_of_analysis,
        mo.actual_cost_per_unit,
        mo.manufacturing_origin,
        mo.normalized_jo_number,
        mo.manufacturing_source_type
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
       AND LOWER(COALESCE(mo.manufacturing_order_state, '')) NOT IN ('cancel', 'cancelled')
),
io_mo_agg AS (
    SELECT
        internal_order_id,
        internal_order_number,
        COUNT(DISTINCT manufacturing_order_id) AS io_mo_count,
        COALESCE(SUM(manufacturing_quantity) FILTER (WHERE manufacturing_order_id IS NOT NULL), 0)::numeric AS io_mo_qty,
        COALESCE(SUM(manufacturing_quantity) FILTER (
            WHERE manufacturing_order_id IS NOT NULL
              AND LOWER(COALESCE(manufacturing_order_state, '')) = 'done'
        ), 0)::numeric AS io_done_mo_qty,
        COALESCE(SUM(manufacturing_quantity) FILTER (
            WHERE manufacturing_order_id IS NOT NULL
              AND LOWER(COALESCE(manufacturing_order_state, '')) NOT IN ('done', 'cancel', 'cancelled')
        ), 0)::numeric AS io_in_progress_mo_qty,
        COALESCE(SUM(cost_of_analysis) FILTER (WHERE manufacturing_order_id IS NOT NULL), 0)::numeric AS io_actual_cost_full,
        COALESCE(SUM(cost_of_analysis) FILTER (WHERE manufacturing_order_id IS NOT NULL), 0)::numeric
            / NULLIF(COALESCE(SUM(manufacturing_quantity) FILTER (WHERE manufacturing_order_id IS NOT NULL), 0)::numeric, 0)
            AS io_actual_cost_per_unit,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'manufacturing_order_id', manufacturing_order_id,
                'manufacturing_order_number', manufacturing_order_number,
                'manufacturing_order_state', manufacturing_order_state,
                'manufactured_product_name', manufactured_product_name,
                'manufacturing_quantity', manufacturing_quantity,
                'cost_of_analysis', cost_of_analysis,
                'actual_cost', cost_of_analysis,
                'actual_cost_per_unit', actual_cost_per_unit,
                'cost_basis', 'MRP_COST_OF_ANALYSIS',
                'origin', manufacturing_origin,
                'job_order_number', normalized_jo_number,
                'manufacturing_source_type', manufacturing_source_type
            )
            ORDER BY manufacturing_order_number
        ) FILTER (WHERE manufacturing_order_id IS NOT NULL) AS io_manufacturing_orders
    FROM io_mo_rows
    GROUP BY internal_order_id, internal_order_number
),
io_correlation_by_internal_order AS (
    SELECT
        qty.internal_order_id,
        qty.internal_order_number,
        COALESCE(mo.io_mo_count, 0) AS io_mo_count,
        COALESCE(mo.io_mo_qty, 0)::numeric AS io_mo_qty,
        COALESCE(mo.io_done_mo_qty, 0)::numeric AS io_done_mo_qty,
        COALESCE(mo.io_in_progress_mo_qty, 0)::numeric AS io_in_progress_mo_qty,
        COALESCE(mo.io_actual_cost_full, 0)::numeric AS io_actual_cost_full,
        mo.io_actual_cost_per_unit,
        COALESCE(qty.linked_so_count, 0) AS linked_so_count,
        COALESCE(qty.multi_io_so_count, 0) AS multi_io_so_count,
        COALESCE(qty.has_multi_io_so, FALSE) AS has_multi_io_so,
        qty.linked_so_qty_basis,
        COALESCE(qty.linked_so_ordered_qty, 0)::numeric AS linked_so_ordered_qty,
        COALESCE(qty.linked_so_delivered_qty, 0)::numeric AS linked_so_delivered_qty,
        COALESCE(qty.linked_so_invoiced_qty, 0)::numeric AS linked_so_invoiced_qty,
        CASE
            WHEN COALESCE(mo.io_mo_count, 0) = 0 THEN 'NO_IO_MO_FOUND'
            WHEN COALESCE(qty.has_multi_io_so, FALSE) THEN 'IO_QTY_UNALLOCATED_MULTI_IO_SO'
            WHEN qty.linked_so_ordered_qty IS NULL THEN 'IO_QTY_UNCLEAR'
            WHEN COALESCE(mo.io_mo_qty, 0) > COALESCE(qty.linked_so_ordered_qty, 0) THEN 'IO_QTY_SURPLUS_VS_LINKED_SO'
            WHEN COALESCE(qty.linked_so_ordered_qty, 0) > COALESCE(mo.io_mo_qty, 0) THEN 'LINKED_SO_QTY_EXCEEDS_IO_QTY'
            WHEN COALESCE(mo.io_mo_qty, 0) = COALESCE(qty.linked_so_ordered_qty, 0) THEN 'IO_QTY_BALANCED_WITH_LINKED_SO'
            ELSE 'IO_QTY_UNCLEAR'
        END AS io_qty_correlation_status,
        COALESCE(mo.io_manufacturing_orders, '[]'::jsonb) AS io_manufacturing_orders
    FROM io_linked_so_qty qty
    LEFT JOIN io_mo_agg mo
        ON mo.internal_order_id = qty.internal_order_id
       AND mo.internal_order_number = qty.internal_order_number
),
so_io_correlation_agg AS (
    SELECT
        links.sales_order_id,
        COUNT(DISTINCT corr.internal_order_id) FILTER (WHERE corr.linked_so_count > 1) AS shared_io_count,
        STRING_AGG(DISTINCT corr.internal_order_number, ', ' ORDER BY corr.internal_order_number)
            FILTER (WHERE corr.linked_so_count > 1) AS shared_io_numbers,
        COALESCE(MAX(multi_context.multi_io_so_count), 0) AS multi_io_so_count,
        COALESCE(BOOL_OR(multi_context.has_multi_io_so), FALSE) AS has_multi_io_so,
        'FULL_SO_QTY_UNALLOCATED'::text AS linked_so_qty_basis,
        COALESCE(SUM(corr.io_mo_count), 0)::integer AS io_backed_mo_count,
        COALESCE(SUM(corr.io_mo_qty), 0)::numeric AS io_backed_mo_qty,
        COALESCE(SUM(corr.io_done_mo_qty), 0)::numeric AS io_backed_done_mo_qty,
        COALESCE(SUM(corr.io_in_progress_mo_qty), 0)::numeric AS io_backed_in_progress_mo_qty,
        COALESCE(SUM(corr.io_actual_cost_full), 0)::numeric AS io_backed_actual_cost_full,
        COALESCE(SUM(corr.io_actual_cost_full), 0)::numeric / NULLIF(COALESCE(SUM(corr.io_mo_qty), 0)::numeric, 0) AS io_backed_actual_cost_per_unit,
        CASE
            WHEN COUNT(corr.internal_order_id) = 0 THEN 'NO_IO_MO_FOUND'
            WHEN BOOL_OR(corr.io_qty_correlation_status = 'IO_QTY_UNALLOCATED_MULTI_IO_SO') THEN 'IO_QTY_UNALLOCATED_MULTI_IO_SO'
            WHEN BOOL_OR(corr.io_qty_correlation_status = 'LINKED_SO_QTY_EXCEEDS_IO_QTY') THEN 'LINKED_SO_QTY_EXCEEDS_IO_QTY'
            WHEN BOOL_OR(corr.io_qty_correlation_status = 'IO_QTY_SURPLUS_VS_LINKED_SO') THEN 'IO_QTY_SURPLUS_VS_LINKED_SO'
            WHEN BOOL_OR(corr.io_qty_correlation_status = 'IO_QTY_UNCLEAR') THEN 'IO_QTY_UNCLEAR'
            WHEN BOOL_AND(corr.io_qty_correlation_status = 'NO_IO_MO_FOUND') THEN 'NO_IO_MO_FOUND'
            WHEN BOOL_AND(corr.io_qty_correlation_status = 'IO_QTY_BALANCED_WITH_LINKED_SO') THEN 'IO_QTY_BALANCED_WITH_LINKED_SO'
            ELSE 'IO_QTY_UNCLEAR'
        END AS io_qty_correlation_status,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'internal_order_id', corr.internal_order_id,
                'internal_order_number', corr.internal_order_number,
                'io_mo_count', corr.io_mo_count,
                'io_mo_qty', corr.io_mo_qty,
                'io_done_mo_qty', corr.io_done_mo_qty,
                'io_in_progress_mo_qty', corr.io_in_progress_mo_qty,
                'io_actual_cost_full', corr.io_actual_cost_full,
                'io_actual_cost', corr.io_actual_cost_full,
                'io_actual_cost_per_unit', corr.io_actual_cost_per_unit,
                'actual_cost_is_correlation_only', TRUE,
                'linked_so_count', corr.linked_so_count,
                'multi_io_so_count', corr.multi_io_so_count,
                'has_multi_io_so', corr.has_multi_io_so,
                'linked_so_qty_basis', corr.linked_so_qty_basis,
                'linked_so_ordered_qty', corr.linked_so_ordered_qty,
                'linked_so_delivered_qty', corr.linked_so_delivered_qty,
                'linked_so_invoiced_qty', corr.linked_so_invoiced_qty,
                'io_qty_correlation_status', corr.io_qty_correlation_status,
                'io_manufacturing_orders', corr.io_manufacturing_orders
            )
            ORDER BY corr.internal_order_number
        ) FILTER (WHERE corr.internal_order_id IS NOT NULL) AS io_manufacturing_correlations
    FROM so_io_links links
    LEFT JOIN so_multi_io_context multi_context
        ON multi_context.sales_order_id = links.sales_order_id
    LEFT JOIN io_correlation_by_internal_order corr
        ON corr.internal_order_id = links.internal_order_id
       AND corr.internal_order_number = links.internal_order_number
    GROUP BY links.sales_order_id
),
mo_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT manufacturing_order_id) AS direct_mo_count,
        COALESCE(SUM(COALESCE(manufacturing_quantity, 0)), 0)::numeric AS direct_mo_qty,
        COALESCE(SUM(COALESCE(manufacturing_quantity, 0)) FILTER (
            WHERE LOWER(COALESCE(manufacturing_order_state, '')) = 'done'
        ), 0)::numeric AS direct_done_mo_qty,
        COALESCE(SUM(COALESCE(manufacturing_quantity, 0)) FILTER (
            WHERE LOWER(COALESCE(manufacturing_order_state, '')) NOT IN ('done', 'cancel', 'cancelled')
        ), 0)::numeric AS direct_in_progress_mo_qty,
        COALESCE(SUM(COALESCE(cost_of_analysis, 0)), 0)::numeric AS direct_actual_cost_full,
        COALESCE(SUM(COALESCE(cost_of_analysis, 0)), 0)::numeric / NULLIF(COALESCE(SUM(COALESCE(manufacturing_quantity, 0)), 0)::numeric, 0) AS direct_actual_cost_per_unit,
        COUNT(DISTINCT manufacturing_order_id) FILTER (WHERE manufacturing_source_type = 'JO_BASED_MO') AS job_order_mo_count,
        JSONB_AGG(
            DISTINCT JSONB_BUILD_OBJECT(
                'manufacturing_order_id', manufacturing_order_id,
                'manufacturing_order_number', manufacturing_order_number,
                'manufacturing_order_state', manufacturing_order_state,
                'manufactured_product_name', manufactured_product_name,
                'manufacturing_quantity', manufacturing_quantity,
                'cost_of_analysis', cost_of_analysis,
                'actual_cost', cost_of_analysis,
                'actual_cost_per_unit', actual_cost_per_unit,
                'cost_basis', 'MRP_COST_OF_ANALYSIS',
                'origin', manufacturing_origin,
                'internal_order_number', internal_order_number,
                'job_order_number', normalized_jo_number,
                'manufacturing_source_type', manufacturing_source_type
            )
        ) FILTER (WHERE manufacturing_order_id IS NOT NULL) AS manufacturing_orders
    FROM vw_mrp_order_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
      AND manufacturing_source_type IN ('SO_BASED_MO', 'JO_BASED_MO')
      AND LOWER(COALESCE(manufacturing_order_state, '')) NOT IN ('cancel', 'cancelled')
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
        so.create_date AS order_create_date,
        EXTRACT(YEAR FROM so.create_date)::integer AS order_year,
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
),
rkb_related_rows AS (
    SELECT DISTINCT ON (sales_order_id, rkb_line_id)
        sales_order_id,
        rkb_line_id,
        rkb_link_basis,
        COALESCE(planned_subtotal, 0)::numeric AS planned_subtotal
    FROM (
        SELECT
            so.sales_order_id,
            rkb.rkb_line_id,
            'DIRECT_SO_OR_JO_RKB'::text AS rkb_link_basis,
            rkb.planned_subtotal
        FROM so_base so
        JOIN vw_rkb_planning_lines rkb
            ON rkb.is_valid_for_metrics
           AND rkb.job_order_number IS NOT NULL
           AND rkb.job_order_number = so.sales_order_number
        UNION ALL
        SELECT
            links.sales_order_id,
            rkb.rkb_line_id,
            'IO_CORRELATED_RKB_UNALLOCATED'::text AS rkb_link_basis,
            rkb.planned_subtotal
        FROM so_io_links links
        JOIN vw_rkb_planning_lines rkb
            ON rkb.is_valid_for_metrics
           AND rkb.internal_order_number IS NOT NULL
           AND (
                rkb.internal_order_number = links.internal_order_number
                OR rkb.internal_order_number = links.internal_order_id::text
           )
    ) rkb_links
    ORDER BY sales_order_id, rkb_line_id,
        CASE rkb_link_basis WHEN 'DIRECT_SO_OR_JO_RKB' THEN 1 ELSE 2 END
),
rkb_cost_agg AS (
    SELECT
        sales_order_id,
        COALESCE(SUM(planned_subtotal), 0)::numeric AS rkb_planned_cost,
        COALESCE(SUM(planned_subtotal) FILTER (WHERE rkb_link_basis = 'DIRECT_SO_OR_JO_RKB'), 0)::numeric AS direct_rkb_planned_cost,
        COALESCE(SUM(planned_subtotal) FILTER (WHERE rkb_link_basis = 'IO_CORRELATED_RKB_UNALLOCATED'), 0)::numeric AS io_correlated_rkb_planned_cost,
        BOOL_OR(rkb_link_basis = 'DIRECT_SO_OR_JO_RKB') AS has_direct_rkb,
        BOOL_OR(rkb_link_basis = 'IO_CORRELATED_RKB_UNALLOCATED') AS has_io_rkb
    FROM rkb_related_rows
    GROUP BY sales_order_id
),
actual_cost_inputs AS (
    SELECT
        so.sales_order_id,
        COALESCE(source.sales_order_source_type, 'UNKNOWN_SOURCE') AS source_type,
        COALESCE(line.delivered_qty, 0)::numeric AS delivered_qty,
        COALESCE(line.delivered_qty_from_internal_order, 0)::numeric AS delivered_qty_from_internal_order,
        COALESCE(line.delivered_qty_make_to_order, 0)::numeric AS delivered_qty_make_to_order,
        COALESCE(line.delivered_qty_mixed_source, 0)::numeric AS delivered_qty_mixed_source,
        COALESCE(line.ordered_amount_idr, 0)::numeric AS sales_amount_idr,
        COALESCE(rkb.has_io_rkb, FALSE) AS has_io_rkb,
        COALESCE(mo.direct_actual_cost_full, 0)::numeric AS direct_actual_cost_full,
        mo.direct_actual_cost_per_unit,
        COALESCE(io_corr.io_backed_actual_cost_full, 0)::numeric AS io_backed_actual_cost_full,
        io_corr.io_backed_actual_cost_per_unit
    FROM so_base so
    LEFT JOIN line_agg line
        ON line.sales_order_id = so.sales_order_id
    LEFT JOIN source_summary source
        ON source.sales_order_id = so.sales_order_id
    LEFT JOIN mo_agg mo
        ON mo.sales_order_id = so.sales_order_id
    LEFT JOIN so_io_correlation_agg io_corr
        ON io_corr.sales_order_id = so.sales_order_id
    LEFT JOIN rkb_cost_agg rkb
        ON rkb.sales_order_id = so.sales_order_id
),
actual_cost_calc_raw AS (
    SELECT
        sales_order_id,
        source_type,
        sales_amount_idr,
        has_io_rkb,
        direct_actual_cost_full,
        direct_actual_cost_per_unit,
        io_backed_actual_cost_full,
        io_backed_actual_cost_per_unit,
        delivered_qty,
        delivered_qty_mixed_source,
        CASE
            WHEN source_type = 'MAKE_TO_ORDER' THEN delivered_qty
            ELSE delivered_qty_make_to_order
        END AS direct_allocated_delivered_qty,
        CASE
            WHEN source_type = 'FROM_INTERNAL_ORDER' THEN delivered_qty
            WHEN source_type = 'MIXED_SOURCE' THEN delivered_qty_from_internal_order
            ELSE 0::numeric
        END AS io_allocated_delivered_qty
    FROM actual_cost_inputs
),
actual_cost_calc AS (
    SELECT
        sales_order_id,
        direct_actual_cost_full,
        direct_actual_cost_per_unit,
        CASE
            WHEN direct_actual_cost_full = 0 THEN 0::numeric
            WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
            ELSE direct_actual_cost_full
        END AS direct_actual_cost,
        CASE
            WHEN direct_actual_cost_full = 0 THEN 'NO_DIRECT_MO_COST'
            WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN 'DIRECT_MO_COST_PER_DELIVERED_QTY'
            ELSE 'DIRECT_MO_COST_FULL'
        END AS direct_actual_cost_basis,
        io_backed_actual_cost_full,
        io_backed_actual_cost_per_unit,
        CASE
            WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
            WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
            WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
            ELSE 0::numeric
        END AS io_backed_actual_cost_allocated,
        CASE
            WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN
                CASE WHEN source_type = 'FROM_STOCK' THEN 'FROM_STOCK_COST_NOT_TRACEABLE' ELSE 'NO_IO_ACTUAL_COST' END
            WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN 'IO_COST_PER_DELIVERED_QTY'
            WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN 'MIXED_SOURCE_IO_COST_PER_DELIVERED_QTY'
            ELSE 'IO_COST_CORRELATION_ONLY_UNALLOCATED'
        END AS io_backed_actual_cost_basis,
        direct_actual_cost_full + io_backed_actual_cost_full AS total_related_actual_cost_full,
        (
            CASE
                WHEN direct_actual_cost_full = 0 THEN 0::numeric
                WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
                ELSE direct_actual_cost_full
            END
            +
            CASE
                WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
                WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                ELSE 0::numeric
            END
        ) AS actual_cost_quantity_based,
        (
            CASE
                WHEN direct_actual_cost_full = 0 THEN 0::numeric
                WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
                ELSE direct_actual_cost_full
            END
            +
            CASE
                WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
                WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                ELSE 0::numeric
            END
        ) AS actual_cost,
        CASE
            WHEN delivered_qty > 0 THEN (
                (
                    CASE
                        WHEN direct_actual_cost_full = 0 THEN 0::numeric
                        WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
                        ELSE direct_actual_cost_full
                    END
                    +
                    CASE
                        WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
                        WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                        WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                        ELSE 0::numeric
                    END
                ) / NULLIF(delivered_qty, 0)
            )
        END AS actual_cost_per_unit,
        CASE
            WHEN source_type = 'MIXED_SOURCE' AND delivered_qty_mixed_source > 0 THEN 'MIXED_SOURCE_ACTUAL_COST_NEEDS_REVIEW'
            WHEN (
                CASE
                    WHEN direct_actual_cost_full = 0 THEN 0::numeric
                    WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
                    ELSE direct_actual_cost_full
                END
            ) > 0
             AND (
                CASE
                    WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
                    WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                    WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                    ELSE 0::numeric
                END
            ) > 0 THEN 'DIRECT_AND_IO_QTY_BASED'
            WHEN (
                CASE
                    WHEN direct_actual_cost_full = 0 THEN 0::numeric
                    WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN direct_allocated_delivered_qty * direct_actual_cost_per_unit
                    ELSE direct_actual_cost_full
                END
            ) > 0 THEN
                CASE
                    WHEN direct_actual_cost_full = 0 THEN 'NO_DIRECT_MO_COST'
                    WHEN direct_allocated_delivered_qty > 0 AND direct_actual_cost_per_unit IS NOT NULL THEN 'DIRECT_MO_COST_PER_DELIVERED_QTY'
                    ELSE 'DIRECT_MO_COST_FULL'
                END
            WHEN (
                CASE
                    WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN 0::numeric
                    WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                    WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN io_allocated_delivered_qty * io_backed_actual_cost_per_unit
                    ELSE 0::numeric
                END
            ) > 0 THEN
                CASE
                    WHEN io_backed_actual_cost_full = 0 OR io_backed_actual_cost_per_unit IS NULL THEN
                        CASE WHEN source_type = 'FROM_STOCK' THEN 'FROM_STOCK_COST_NOT_TRACEABLE' ELSE 'NO_IO_ACTUAL_COST' END
                    WHEN source_type = 'FROM_INTERNAL_ORDER' AND io_allocated_delivered_qty > 0 THEN 'IO_COST_PER_DELIVERED_QTY'
                    WHEN source_type = 'MIXED_SOURCE' AND io_allocated_delivered_qty > 0 THEN 'MIXED_SOURCE_IO_COST_PER_DELIVERED_QTY'
                    ELSE 'IO_COST_CORRELATION_ONLY_UNALLOCATED'
                END
            WHEN source_type = 'FROM_STOCK' THEN 'FROM_STOCK_COST_NOT_TRACEABLE'
            ELSE 'NO_ACTUAL_COST'
        END AS actual_cost_basis,
        NULLIF(CONCAT_WS('|',
            CASE WHEN sales_amount_idr = 0 THEN 'NO_SALES_AMOUNT_BASIS' END,
            CASE WHEN has_io_rkb THEN 'RKB_COST_IO_CORRELATED_UNALLOCATED' END,
            CASE WHEN source_type = 'MIXED_SOURCE' AND delivered_qty_mixed_source > 0 THEN 'MIXED_SOURCE_ACTUAL_COST_NEEDS_REVIEW' END,
            CASE WHEN source_type = 'FROM_STOCK' AND io_backed_actual_cost_full = 0 AND direct_actual_cost_full = 0 THEN 'ACTUAL_COST_INCOMPLETE' END,
            CASE WHEN source_type = 'UNKNOWN_SOURCE' THEN 'ACTUAL_COST_INCOMPLETE' END
        ), '') AS contribution_basis_warning
    FROM actual_cost_calc_raw
)
SELECT
    so.sales_order_id,
    so.sales_order_number,
    so.company_id,
    so.customer_name,
    so.order_date,
    so.order_create_date,
    so.order_year,
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
    COALESCE(line.ordered_amount_idr, 0) AS ordered_amount_idr,
    COALESCE(line.ordered_amount_idr, 0) AS sales_amount_idr,
    COALESCE(rkb.rkb_planned_cost, 0) AS rkb_planned_cost,
    COALESCE(rkb.direct_rkb_planned_cost, 0) AS direct_rkb_planned_cost,
    COALESCE(rkb.io_correlated_rkb_planned_cost, 0) AS io_correlated_rkb_planned_cost,
    CASE
        WHEN COALESCE(rkb.has_direct_rkb, FALSE) AND COALESCE(rkb.has_io_rkb, FALSE) THEN 'DIRECT_AND_IO_CORRELATED_RKB'
        WHEN COALESCE(rkb.has_direct_rkb, FALSE) THEN 'DIRECT_SO_OR_JO_RKB'
        WHEN COALESCE(rkb.has_io_rkb, FALSE) THEN 'IO_CORRELATED_RKB_UNALLOCATED'
        ELSE 'NO_RKB_FOUND'
    END AS rkb_cost_basis,
    COALESCE(line.delivered_amount_idr, 0) AS delivered_amount_idr,
    COALESCE(line.invoiced_amount_idr, 0) AS invoiced_amount_idr,
    COALESCE(line.currency_rate_used, 1) AS currency_rate_used,
    COALESCE(line.currency_conversion_basis, 'IDR_FALLBACK_RATE_1') AS currency_conversion_basis,
    CASE WHEN COALESCE(line.ordered_qty, 0) > 0 THEN LEAST(COALESCE(line.delivered_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0), 1.0::numeric) END AS qty_delivery_progress_ratio,
    CASE WHEN COALESCE(line.ordered_qty, 0) > 0 THEN LEAST(COALESCE(line.invoiced_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0), 1.0::numeric) END AS qty_invoice_progress_ratio,
    CASE WHEN COALESCE(line.ordered_amount_idr, 0) > 0 THEN LEAST(COALESCE(line.delivered_amount_idr, 0) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0), 1.0::numeric) END AS amount_delivery_progress_ratio,
    CASE WHEN COALESCE(line.ordered_amount_idr, 0) > 0 THEN LEAST(COALESCE(line.invoiced_amount_idr, 0) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0), 1.0::numeric) END AS amount_invoice_progress_ratio,
    (COALESCE(line.delivered_qty, 0) >= COALESCE(line.ordered_qty, 0) AND COALESCE(line.ordered_qty, 0) > 0) AS is_fully_delivered_qty,
    (COALESCE(line.invoiced_qty, 0) >= COALESCE(line.ordered_qty, 0) AND COALESCE(line.ordered_qty, 0) > 0) AS is_fully_invoiced_qty,
    (COALESCE(line.delivered_amount, 0) >= COALESCE(line.ordered_amount, 0) AND COALESCE(line.ordered_amount, 0) > 0) AS is_fully_delivered_amount,
    (COALESCE(line.invoiced_amount, 0) >= COALESCE(line.ordered_amount, 0) AND COALESCE(line.ordered_amount, 0) > 0) AS is_fully_invoiced_amount,
    (COALESCE(line.delivered_qty, 0) > 0) AS has_delivered_qty,
    (COALESCE(line.invoiced_qty, 0) > 0) AS has_invoiced_qty,
    COALESCE(io.internal_order_count, 0) AS internal_order_count,
    COALESCE(mo.direct_mo_count, 0) AS manufacturing_order_count,
    COALESCE(mo.job_order_mo_count, 0) AS job_order_mo_count,
    COALESCE(mo.direct_mo_count, 0) AS direct_mo_count,
    COALESCE(mo.direct_mo_qty, 0) AS direct_mo_qty,
    COALESCE(mo.direct_done_mo_qty, 0) AS direct_done_mo_qty,
    COALESCE(mo.direct_in_progress_mo_qty, 0) AS direct_in_progress_mo_qty,
    COALESCE(ac.direct_actual_cost, 0) AS direct_actual_cost,
    ac.direct_actual_cost_per_unit,
    ac.direct_actual_cost_basis,
    COALESCE(io_corr.io_backed_mo_count, 0) AS io_backed_mo_count,
    COALESCE(io_corr.io_backed_mo_qty, 0) AS io_backed_mo_qty,
    COALESCE(io_corr.io_backed_done_mo_qty, 0) AS io_backed_done_mo_qty,
    COALESCE(io_corr.io_backed_in_progress_mo_qty, 0) AS io_backed_in_progress_mo_qty,
    COALESCE(io_corr.io_backed_actual_cost_full, 0) AS io_backed_actual_cost,
    COALESCE(io_corr.io_backed_actual_cost_full, 0) AS io_backed_actual_cost_full,
    COALESCE(ac.io_backed_actual_cost_allocated, 0) AS io_backed_actual_cost_allocated,
    ac.io_backed_actual_cost_per_unit,
    ac.io_backed_actual_cost_basis,
    TRUE AS io_backed_actual_cost_is_correlation_only,
    COALESCE(ac.total_related_actual_cost_full, 0) AS total_related_actual_cost,
    COALESCE(ac.total_related_actual_cost_full, 0) AS total_related_actual_cost_full,
    COALESCE(ac.actual_cost, 0) AS actual_cost,
    COALESCE(ac.actual_cost_quantity_based, 0) AS actual_cost_quantity_based,
    ac.actual_cost_per_unit,
    ac.actual_cost_basis,
    COALESCE(line.ordered_amount_idr, 0) - COALESCE(rkb.rkb_planned_cost, 0) AS rkb_kontribusi_amount,
    (COALESCE(line.ordered_amount_idr, 0) - COALESCE(rkb.rkb_planned_cost, 0)) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0) AS rkb_kontribusi_percent,
    COALESCE(line.ordered_amount_idr, 0) - COALESCE(ac.actual_cost_quantity_based, 0) AS kontribusi_aktual_amount,
    (COALESCE(line.ordered_amount_idr, 0) - COALESCE(ac.actual_cost_quantity_based, 0)) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0) AS kontribusi_aktual_percent,
    ac.contribution_basis_warning,
    COALESCE(mo.direct_mo_count, 0) + COALESCE(io_corr.io_backed_mo_count, 0) AS total_related_mo_count,
    COALESCE(mo.direct_mo_qty, 0) + COALESCE(io_corr.io_backed_mo_qty, 0) AS total_related_mo_qty,
    COALESCE(mo.direct_done_mo_qty, 0) + COALESCE(io_corr.io_backed_done_mo_qty, 0) AS total_done_mo_qty,
    COALESCE(mo.direct_in_progress_mo_qty, 0) + COALESCE(io_corr.io_backed_in_progress_mo_qty, 0) AS total_in_progress_mo_qty,
    COALESCE(io_corr.shared_io_count, 0) AS shared_io_count,
    io_corr.shared_io_numbers,
    COALESCE(io_corr.multi_io_so_count, 0) AS multi_io_so_count,
    COALESCE(io_corr.has_multi_io_so, FALSE) AS has_multi_io_so,
    COALESCE(io_corr.linked_so_qty_basis, 'FULL_SO_QTY_UNALLOCATED') AS linked_so_qty_basis,
    COALESCE(io_corr.io_qty_correlation_status, 'NO_IO_MO_FOUND') AS io_qty_correlation_status,
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
          AND COALESCE(mo.direct_mo_count, 0) = 0 THEN 'WAITING_PRODUCTION'
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
          AND COALESCE(mo.direct_mo_count, 0) = 0 THEN 4
        WHEN COALESCE(line.delivered_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 5
        WHEN COALESCE(line.delivered_qty, 0) > 0
          AND COALESCE(line.invoiced_qty, 0) < COALESCE(line.ordered_qty, 0)
          AND COALESCE(line.ordered_qty, 0) > 0 THEN 6
        ELSE 7
    END AS follow_up_status_priority,
    COALESCE(line.sales_order_lines, '[]'::jsonb) AS sales_order_lines,
    COALESCE(mo.manufacturing_orders, '[]'::jsonb) AS manufacturing_orders,
    COALESCE(io_corr.io_manufacturing_correlations, '[]'::jsonb) AS io_manufacturing_correlations,
    JSONB_BUILD_OBJECT(
        'company_id', so.company_id,
        'product_type_raw', so.product_type_raw,
        'product_type_label', so.product_type_label,
        'delivery_status', so.delivery_status,
        'invoice_status', so.invoice_status,
        'source_link_status', COALESCE(source.sales_order_source_link_status, 'UNKNOWN_NO_MATCHED_LINES'),
        'io_mo_quantity_is_correlation_only', TRUE,
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
LEFT JOIN so_io_correlation_agg io_corr
    ON io_corr.sales_order_id = so.sales_order_id
LEFT JOIN actual_cost_calc ac
    ON ac.sales_order_id = so.sales_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.sales_order_id = so.sales_order_id
LEFT JOIN rkb_cost_agg rkb
    ON rkb.sales_order_id = so.sales_order_id;

COMMENT ON VIEW vw_dashboard_sales_order_traceability IS
    'Phase 2A dashboard-ready Sales Order traceability view for PT Nobi Putra Angkasa only. Quantity and amount progress use countable SO lines and are capped at 100 percent. IO-backed MO quantity is correlation-only and not allocated to individual SOs. Delay uses sale_order.commitment_date. Sales amounts use sale_order.currency_rate as an IDR multiplier with rate-1 fallback. Actual cost is quantity-based from delivered quantity when possible; full IO or MO cost remains audit/correlation only. Contribution metrics are operational and not accounting COGS or gross profit. Accounting/AR is out of scope; accounting count is diagnostic only.';


