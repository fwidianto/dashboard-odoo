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
        COALESCE(SUM(ordered_qty), 0)::numeric AS ordered_qty,
        COALESCE(SUM(delivered_qty), 0)::numeric AS delivered_qty,
        COALESCE(SUM(invoiced_qty), 0)::numeric AS invoiced_qty,
        COALESCE(SUM(ordered_amount), 0)::numeric AS ordered_amount,
        COALESCE(SUM(delivered_amount), 0)::numeric AS delivered_amount,
        COALESCE(SUM(invoiced_amount), 0)::numeric AS invoiced_amount,
        COALESCE(SUM(ordered_amount_idr), 0)::numeric AS ordered_amount_idr,
        COALESCE(SUM(delivered_amount_idr), 0)::numeric AS delivered_amount_idr,
        COALESCE(SUM(invoiced_amount_idr), 0)::numeric AS invoiced_amount_idr,
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
                'qty_delivery_progress_ratio', delivered_qty / NULLIF(ordered_qty, 0),
                'qty_invoice_progress_ratio', invoiced_qty / NULLIF(ordered_qty, 0),
                'amount_delivery_progress_ratio', delivered_amount_idr / NULLIF(ordered_amount_idr, 0),
                'amount_invoice_progress_ratio', invoiced_amount_idr / NULLIF(ordered_amount_idr, 0),
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
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'manufacturing_order_id', manufacturing_order_id,
                'manufacturing_order_number', manufacturing_order_number,
                'manufacturing_order_state', manufacturing_order_state,
                'manufactured_product_name', manufactured_product_name,
                'manufacturing_quantity', manufacturing_quantity,
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
so_io_keys AS (
    SELECT DISTINCT sales_order_id, internal_order_number AS io_key
    FROM so_io_links
    WHERE internal_order_number IS NOT NULL
    UNION
    SELECT DISTINCT sales_order_id, internal_order_id::text AS io_key
    FROM so_io_links
    WHERE internal_order_id IS NOT NULL
),
so_number_keys AS (
    SELECT DISTINCT sales_order_id, sales_order_number AS jo_key
    FROM so_base
    WHERE sales_order_number IS NOT NULL
),
rkb_source_rows AS MATERIALIZED (
    SELECT
        rkb_line_id,
        approval_request_display_name,
        product_name,
        rkb_line_description,
        planned_quantity,
        unit_of_measure,
        planned_unit_price,
        planned_subtotal,
        approval_status,
        requester_name,
        date_of_need,
        internal_order_number,
        job_order_number
    FROM vw_rkb_planning_lines
    WHERE is_valid_for_metrics
      AND (internal_order_number IS NOT NULL OR job_order_number IS NOT NULL)
),
po_source_rows AS MATERIALIZED (
    SELECT
        procurement_line_id,
        purchase_order_reference,
        vendor_name,
        product_name,
        procurement_line_description,
        ordered_quantity,
        received_quantity,
        invoiced_quantity,
        unit_of_measure,
        currency_name,
        unit_price,
        line_subtotal,
        inverse_currency_rate,
        purchase_line_state,
        purchase_planned_date,
        internal_order_number,
        job_order_number
    FROM vw_procurement_lines
    WHERE is_valid_for_metrics
      AND (internal_order_number IS NOT NULL OR job_order_number IS NOT NULL)

),
rkb_related_rows AS (
    SELECT DISTINCT ON (sales_order_id, rkb_line_id)
        sales_order_id,
        rkb_line_id,
        approval_request_display_name,
        rkb_link_basis,
        product_name,
        rkb_line_description,
        planned_quantity,
        unit_of_measure,
        planned_unit_price,
        planned_subtotal,
        approval_status,
        requester_name,
        date_of_need,
        internal_order_number,
        job_order_number
    FROM (
        SELECT
            links.sales_order_id,
            rkb.rkb_line_id,
            rkb.approval_request_display_name,
            'IO_BASED_RKB'::text AS rkb_link_basis,
            rkb.product_name,
            rkb.rkb_line_description,
            rkb.planned_quantity,
            rkb.unit_of_measure,
            rkb.planned_unit_price,
            rkb.planned_subtotal,
            rkb.approval_status,
            rkb.requester_name,
            rkb.date_of_need,
            rkb.internal_order_number,
            rkb.job_order_number
        FROM so_io_keys links
        JOIN rkb_source_rows rkb
            ON rkb.internal_order_number = links.io_key
        UNION ALL
        SELECT
            so.sales_order_id,
            rkb.rkb_line_id,
            rkb.approval_request_display_name,
            'JO_SO_BASED_RKB'::text AS rkb_link_basis,
            rkb.product_name,
            rkb.rkb_line_description,
            rkb.planned_quantity,
            rkb.unit_of_measure,
            rkb.planned_unit_price,
            rkb.planned_subtotal,
            rkb.approval_status,
            rkb.requester_name,
            rkb.date_of_need,
            rkb.internal_order_number,
            rkb.job_order_number
        FROM so_number_keys so
        JOIN rkb_source_rows rkb
            ON rkb.job_order_number = so.jo_key
    ) rkb_links
    ORDER BY sales_order_id, rkb_line_id,
        CASE rkb_link_basis WHEN 'JO_SO_BASED_RKB' THEN 1 ELSE 2 END
),
rkb_agg AS (
    SELECT
        sales_order_id,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'rkb_line_id', rkb_line_id,
                'rkb_reference', approval_request_display_name,
                'rkb_link_basis', rkb_link_basis,
                'product_name', product_name,
                'description', rkb_line_description,
                'quantity', planned_quantity,
                'unit_of_measure', unit_of_measure,
                'unit_price', planned_unit_price,
                'amount', planned_subtotal,
                'status', approval_status,
                'requester', requester_name,
                'needed_date', date_of_need,
                'internal_order_number', internal_order_number,
                'job_order_number', job_order_number
            )
            ORDER BY approval_request_display_name, rkb_line_id
        ) AS rkb_lines
    FROM rkb_related_rows
    GROUP BY sales_order_id
),
po_related_rows AS (
    SELECT DISTINCT ON (sales_order_id, procurement_line_id)
        sales_order_id,
        procurement_line_id,
        purchase_order_reference,
        po_link_basis,
        vendor_name,
        product_name,
        procurement_line_description,
        ordered_quantity,
        received_quantity,
        invoiced_quantity,
        unit_of_measure,
        currency_name,
        unit_price,
        line_subtotal,
        inverse_currency_rate,
        po_unit_price_idr,
        po_amount_idr,
        currency_conversion_basis,
        purchase_line_state,
        purchase_planned_date,
        internal_order_number,
        job_order_number
    FROM (
        SELECT
            links.sales_order_id,
            po.procurement_line_id,
            po.purchase_order_reference,
            'IO_BASED_PO'::text AS po_link_basis,
            po.vendor_name,
            po.product_name,
            po.procurement_line_description,
            po.ordered_quantity,
            po.received_quantity,
            po.invoiced_quantity,
            po.unit_of_measure,
            po.currency_name,
            po.unit_price,
            po.line_subtotal,
            po.inverse_currency_rate,
            (COALESCE(po.unit_price, 0) * COALESCE(NULLIF(po.inverse_currency_rate, 0), 1))::numeric AS po_unit_price_idr,
            (COALESCE(po.line_subtotal, 0) * COALESCE(NULLIF(po.inverse_currency_rate, 0), 1))::numeric AS po_amount_idr,
            CASE
                WHEN NULLIF(po.inverse_currency_rate, 0) IS NULL THEN 'IDR_FALLBACK_RATE_1'
                ELSE 'PO_INVERSE_CURRENCY_RATE_MULTIPLIED_TO_IDR'
            END AS currency_conversion_basis,
            po.purchase_line_state,
            po.purchase_planned_date,
            po.internal_order_number,
            po.job_order_number
        FROM so_io_keys links
        JOIN po_source_rows po
            ON po.internal_order_number = links.io_key
        UNION ALL
        SELECT
            so.sales_order_id,
            po.procurement_line_id,
            po.purchase_order_reference,
            'JO_SO_BASED_PO'::text AS po_link_basis,
            po.vendor_name,
            po.product_name,
            po.procurement_line_description,
            po.ordered_quantity,
            po.received_quantity,
            po.invoiced_quantity,
            po.unit_of_measure,
            po.currency_name,
            po.unit_price,
            po.line_subtotal,
            po.inverse_currency_rate,
            (COALESCE(po.unit_price, 0) * COALESCE(NULLIF(po.inverse_currency_rate, 0), 1))::numeric AS po_unit_price_idr,
            (COALESCE(po.line_subtotal, 0) * COALESCE(NULLIF(po.inverse_currency_rate, 0), 1))::numeric AS po_amount_idr,
            CASE
                WHEN NULLIF(po.inverse_currency_rate, 0) IS NULL THEN 'IDR_FALLBACK_RATE_1'
                ELSE 'PO_INVERSE_CURRENCY_RATE_MULTIPLIED_TO_IDR'
            END AS currency_conversion_basis,
            po.purchase_line_state,
            po.purchase_planned_date,
            po.internal_order_number,
            po.job_order_number
        FROM so_number_keys so
        JOIN po_source_rows po
            ON po.job_order_number = so.jo_key
    ) po_links
    ORDER BY sales_order_id, procurement_line_id,
        CASE po_link_basis WHEN 'JO_SO_BASED_PO' THEN 1 ELSE 2 END
),
po_agg AS (
    SELECT
        sales_order_id,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'procurement_line_id', procurement_line_id,
                'po_reference', purchase_order_reference,
                'po_link_basis', po_link_basis,
                'vendor_name', vendor_name,
                'product_name', product_name,
                'description', procurement_line_description,
                'ordered_quantity', ordered_quantity,
                'received_quantity', received_quantity,
                'billed_quantity', invoiced_quantity,
                'unit_of_measure', unit_of_measure,
                'currency', currency_name,
                'unit_price_original', unit_price,
                'amount_original', line_subtotal,
                'currency_rate_used', COALESCE(NULLIF(inverse_currency_rate, 0), 1),
                'currency_conversion_basis', currency_conversion_basis,
                'po_unit_price_idr', po_unit_price_idr,
                'po_amount_idr', po_amount_idr,
                'status', purchase_line_state,
                'expected_arrival', purchase_planned_date,
                'internal_order_number', internal_order_number,
                'job_order_number', job_order_number
            )
            ORDER BY purchase_order_reference, procurement_line_id
        ) AS purchase_order_lines
    FROM po_related_rows
    GROUP BY sales_order_id
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
    COALESCE(line.delivered_amount_idr, 0) AS delivered_amount_idr,
    COALESCE(line.invoiced_amount_idr, 0) AS invoiced_amount_idr,
    COALESCE(line.currency_rate_used, 1) AS currency_rate_used,
    COALESCE(line.currency_conversion_basis, 'IDR_FALLBACK_RATE_1') AS currency_conversion_basis,
    COALESCE(line.delivered_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0) AS qty_delivery_progress_ratio,
    COALESCE(line.invoiced_qty, 0) / NULLIF(COALESCE(line.ordered_qty, 0), 0) AS qty_invoice_progress_ratio,
    COALESCE(line.delivered_amount_idr, 0) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0) AS amount_delivery_progress_ratio,
    COALESCE(line.invoiced_amount_idr, 0) / NULLIF(COALESCE(line.ordered_amount_idr, 0), 0) AS amount_invoice_progress_ratio,
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
    COALESCE(io_corr.io_backed_mo_count, 0) AS io_backed_mo_count,
    COALESCE(io_corr.io_backed_mo_qty, 0) AS io_backed_mo_qty,
    COALESCE(io_corr.io_backed_done_mo_qty, 0) AS io_backed_done_mo_qty,
    COALESCE(io_corr.io_backed_in_progress_mo_qty, 0) AS io_backed_in_progress_mo_qty,
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
    COALESCE(io.internal_orders, '[]'::jsonb) AS internal_orders,
    COALESCE(mo.manufacturing_orders, '[]'::jsonb) AS manufacturing_orders,
    COALESCE(io_corr.io_manufacturing_correlations, '[]'::jsonb) AS io_manufacturing_correlations,
    COALESCE(rkb.rkb_lines, '[]'::jsonb) AS rkb_lines,
    COALESCE(po.purchase_order_lines, '[]'::jsonb) AS purchase_order_lines,
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
LEFT JOIN rkb_agg rkb
    ON rkb.sales_order_id = so.sales_order_id
LEFT JOIN po_agg po
    ON po.sales_order_id = so.sales_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.sales_order_id = so.sales_order_id;

COMMENT ON VIEW vw_dashboard_sales_order_traceability IS
    'Phase 2A dashboard-ready Sales Order traceability view for PT Nobi Putra Angkasa only. Quantity progress uses SO line quantities; amount progress uses IDR-converted qty * price_unit. IO-backed MO quantity is correlation-only and not allocated to individual SOs. Delay uses sale_order.commitment_date. Sales amounts use sale_order.currency_rate as an IDR multiplier with rate-1 fallback; PO detail uses purchase_order_line.x_studio_currency_rate_inverse as an IDR multiplier with rate-1 fallback. Accounting/AR and profitability are out of scope; accounting count is diagnostic only.';


