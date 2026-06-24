-- =============================================================================
-- Data Truth Layer - 01 Base Views
-- =============================================================================
-- Purpose:
--   Normalize raw Odoo extract tables into business-named traceability views.
--
-- Scope:
--   Traceability and source classification only.
--   No final profitability calculation.
--
-- Confirmed extracted field availability:
--   - sale_order.x_studio_io_1 is currently extracted.
--   - sale_order_line.x_studio_io_1 is NOT currently extracted.
--   - purchase_order_line.x_studio_many2one_field_ij0j0 is the extracted IO field.
--
-- Inferred links:
--   - sale_order.name = sale_order_line.order_id
--   - sale_order.name = mrp_production.origin
--   - stock_move_line.reference = mrp_production.name
--   - stock_move_line.x_studio_source_document = sale_order.name
--   - stock_move_line.x_studio_sale_line = sale_order_line.id::text, where available
--   - normalized account_move_line.x_studio_sales_order = sale_order.name::text
-- =============================================================================

DROP VIEW IF EXISTS vw_data_quality_exceptions CASCADE;
DROP VIEW IF EXISTS vw_manufacturing_flow_context CASCADE;
DROP VIEW IF EXISTS vw_internal_order_context CASCADE;
DROP VIEW IF EXISTS vw_so_traceability CASCADE;
DROP VIEW IF EXISTS vw_sales_order_source_summary CASCADE;
DROP VIEW IF EXISTS vw_sales_order_line_source_context CASCADE;
DROP VIEW IF EXISTS vw_sale_order_internal_order_bridge CASCADE;
DROP VIEW IF EXISTS vw_accounting_sales_lines CASCADE;
DROP VIEW IF EXISTS vw_procurement_lines CASCADE;
DROP VIEW IF EXISTS vw_rkb_planning_lines CASCADE;
DROP VIEW IF EXISTS vw_approval_product_line_context CASCADE;
DROP VIEW IF EXISTS vw_stock_movement_context CASCADE;
DROP VIEW IF EXISTS vw_mrp_order_context CASCADE;
DROP VIEW IF EXISTS vw_sales_order_revenue CASCADE;

CREATE OR REPLACE VIEW vw_sales_order_revenue AS
SELECT
    so.id AS sales_order_id,
    so.name AS sales_order_number,
    so.date_order AS order_date,
    so.commitment_date,
    so.partner_id AS customer_name,
    so.x_studio_sales_name AS salesperson_name,
    so.state AS sales_order_state,
    UPPER(COALESCE(so.state, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(so.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(so.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    so.delivery_status,
    so.invoice_status,
    so.currency_id AS currency_name,
    so.currency_rate,
    so.company_id AS company_name,
    so.amount_untaxed AS sales_order_untaxed_amount,
    so.x_studio_product_type AS product_type,
    so.x_studio_prodcut_type AS product_type_alt,
    sol.id AS sales_order_line_id,
    sol.order_id AS sales_order_line_order_number,
    sol.product_id AS product_name,
    sol.name AS line_description,
    sol.product_uom_qty AS ordered_quantity,
    sol.qty_delivered AS delivered_quantity,
    sol.qty_invoiced AS invoiced_quantity,
    sol.price_unit AS unit_price,
    sol.price_subtotal AS line_subtotal,
    sol.x_studio_currency_rate AS line_currency_rate,
    CASE
        WHEN NULLIF(BTRIM(so.x_studio_io_1), '') IS NULL THEN NULL
        WHEN BTRIM(so.x_studio_io_1) IN ('{}', '[]', 'False', 'false', 'None', 'none') THEN NULL
        ELSE so.x_studio_io_1
    END AS sales_order_io_number,
    NULL::text AS sales_order_line_io_number,
    (
        NULLIF(BTRIM(so.x_studio_io_1), '') IS NOT NULL
        AND BTRIM(so.x_studio_io_1) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none')
    ) AS has_confirmed_sales_order_io,
    FALSE AS missing_sales_order_io_field,
    TRUE AS missing_sales_order_line_io_field,
    (sol.id IS NOT NULL) AS has_sales_order_line,
    (sol.id IS NULL) AS missing_sales_order_line,
    CASE
        WHEN sol.id IS NOT NULL THEN 'SO_LINE_INFERRED_BY_ORDER_NAME'
        ELSE 'SO_LINE_MISSING'
    END AS sales_order_line_link_status,
    CASE
        WHEN sol.id IS NOT NULL THEN 'HIGH'
        ELSE 'NONE'
    END AS sales_order_line_match_confidence
FROM sale_order so
LEFT JOIN sale_order_line sol
    ON sol.order_id = so.name;

COMMENT ON VIEW vw_sales_order_revenue IS
    'Base SO revenue and line view. SO line link is inferred by sale_order.name = sale_order_line.order_id. sale_order.x_studio_io_1 is used as confirmed SO IO; sale_order_line.x_studio_io_1 is not currently extracted.';

CREATE OR REPLACE VIEW vw_mrp_order_context AS
SELECT
    mo.id AS manufacturing_order_id,
    mo.name AS manufacturing_order_number,
    mo.product_id AS manufactured_product_name,
    mo.product_qty AS manufacturing_quantity,
    mo.state AS manufacturing_order_state,
    UPPER(COALESCE(mo.state, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(mo.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(mo.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    mo.date_start AS manufacturing_start_date,
    mo.date_finished AS manufacturing_finished_date,
    mo.x_studio_master_production_schedule_start AS mps_start_date,
    mo.x_studio_master_production_schedule_finish AS mps_finish_date,
    mo.origin AS manufacturing_origin,
    mo.x_studio_nomor_io AS internal_order_number,
    mo.x_studio_nomor_jo AS raw_job_order_number,
    CASE
        WHEN BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(mo.x_studio_nomor_jo)
        ELSE NULL
    END AS normalized_jo_number,
    CASE
        WHEN BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(mo.x_studio_nomor_jo)
        ELSE NULL
    END AS job_order_number,
    mo.company_id AS company_name,
    so.id AS inferred_sales_order_id,
    so.name AS inferred_sales_order_number,
    (so.id IS NOT NULL) AS has_sales_order,
    (NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL) AS has_internal_order,
    (BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$') AS has_valid_jo,
    (BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$') AS has_job_order,
    (
        NULLIF(BTRIM(COALESCE(mo.x_studio_nomor_jo, '')), '') IS NOT NULL
        AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
        AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
    ) AS invalid_jo_format,
    (so.id IS NOT NULL AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL) AS invalid_both_so_and_io,
    (
        NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
        AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
    ) AS invalid_both_io_and_jo,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(mo.x_studio_nomor_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID_JO_FORMAT'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN so.id IS NOT NULL
          AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
            THEN 'INVALID_BOTH_SO_AND_IO'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
          AND so.id IS NULL
            THEN 'IO_BASED_MO'
        WHEN so.id IS NOT NULL
          AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NULL
            THEN 'SO_BASED_MO'
        WHEN BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
          AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NULL
            THEN 'JO_BASED_MO'
        ELSE 'UNKNOWN_OR_MANUAL_MO'
    END AS manufacturing_source_type,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(mo.x_studio_nomor_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID_JO_FORMAT'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN so.id IS NOT NULL
          AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
            THEN 'INVALID_BOTH_SO_AND_IO'
        WHEN so.id IS NOT NULL THEN 'SO_TO_MO_INFERRED_BY_ORIGIN'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL THEN 'MO_CONFIRMED_BY_IO_FIELD'
        WHEN BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$' THEN 'MO_CONFIRMED_BY_JO_FIELD'
        ELSE 'MO_SOURCE_UNKNOWN'
    END AS manufacturing_source_link_status,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(mo.x_studio_nomor_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
          AND BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID'
        WHEN so.id IS NOT NULL
          AND NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL
            THEN 'INVALID'
        WHEN so.id IS NOT NULL THEN 'HIGH'
        WHEN NULLIF(BTRIM(mo.x_studio_nomor_io), '') IS NOT NULL THEN 'HIGH'
        WHEN BTRIM(COALESCE(mo.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$' THEN 'HIGH'
        ELSE 'UNKNOWN'
    END AS manufacturing_source_confidence
FROM mrp_production mo
LEFT JOIN sale_order so
    ON so.name = mo.origin;

COMMENT ON VIEW vw_mrp_order_context IS
    'MO source classification view. Normally one source reference should exist: SO, IO, or JO.';

CREATE OR REPLACE VIEW vw_stock_movement_context AS
SELECT
    sml.id AS stock_move_line_id,
    sml.reference AS stock_reference,
    sml.date_x AS movement_date,
    sml.x_studio_source_document AS source_document_number,
    sml.product_id AS product_name,
    sml.product_category_name,
    sml.x_studio_sale_line AS sales_order_line_reference,
    sml.x_studio_demand AS demanded_quantity,
    sml.quantity AS moved_quantity,
    sml.product_uom_id AS unit_of_measure,
    sml.location_id AS source_location_id,
    sml.location_dest_id AS destination_location_id,
    sml.state AS stock_movement_state,
    UPPER(COALESCE(sml.state, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(sml.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(sml.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    sml.picking_type_id AS picking_type_raw,
    CASE
        WHEN sml.picking_type_id ILIKE '%%Store Finished Product%%'
          OR sml.picking_type_id ILIKE '%%Finished Goods%%'
          OR sml.picking_type_id ILIKE '%%Finished Product%%'
            THEN 'FINISHED_GOODS_STORE'
        WHEN sml.picking_type_id ILIKE '%%OUT%%'
          OR sml.picking_type_id ILIKE '%%Delivery%%'
          OR sml.picking_type_id ILIKE '%%Customer%%'
          OR sml.picking_type_id ILIKE '%%Keluar%%'
            THEN 'DELIVERY'
        WHEN sml.picking_type_id ILIKE '%%Receipt%%'
          OR sml.picking_type_id ILIKE '%%Vendor%%'
          OR sml.picking_type_id ILIKE '%%Terima%%'
            THEN 'RECEIPT'
        WHEN sml.picking_type_id ILIKE '%%Internal%%'
          OR sml.picking_type_id ILIKE '%%INT%%'
          OR sml.picking_type_id ILIKE '%%Transfer%%'
            THEN 'INTERNAL_TRANSFER'
        WHEN sml.picking_type_id ILIKE '%%Manufacturing%%'
          OR sml.picking_type_id ILIKE '%%Production%%'
          OR sml.picking_type_id ILIKE '%%Pick Components%%'
          OR sml.picking_type_id ILIKE '%%MO%%'
          OR sml.picking_type_id ILIKE '%%MRP%%'
            THEN 'MANUFACTURING'
        ELSE 'UNKNOWN_MOVEMENT_TYPE'
    END AS movement_business_type,
    (
        sml.picking_type_id ILIKE '%%OUT%%'
        OR sml.picking_type_id ILIKE '%%Delivery%%'
        OR sml.picking_type_id ILIKE '%%Customer%%'
        OR sml.picking_type_id ILIKE '%%Keluar%%'
    ) AS is_delivery_movement,
    (
        sml.picking_type_id ILIKE '%%Store Finished Product%%'
        OR sml.picking_type_id ILIKE '%%Finished Goods%%'
        OR sml.picking_type_id ILIKE '%%Finished Product%%'
    ) AS is_finished_goods_store_movement,
    (
        sml.picking_type_id ILIKE '%%Receipt%%'
        OR sml.picking_type_id ILIKE '%%Vendor%%'
        OR sml.picking_type_id ILIKE '%%Terima%%'
    ) AS is_receipt_movement,
    (
        sml.picking_type_id ILIKE '%%Internal%%'
        OR sml.picking_type_id ILIKE '%%INT%%'
        OR sml.picking_type_id ILIKE '%%Transfer%%'
    ) AS is_internal_transfer,
    (
        sml.picking_type_id ILIKE '%%Manufacturing%%'
        OR sml.picking_type_id ILIKE '%%Production%%'
        OR sml.picking_type_id ILIKE '%%Pick Components%%'
        OR sml.picking_type_id ILIKE '%%MO%%'
        OR sml.picking_type_id ILIKE '%%MRP%%'
    ) AS is_manufacturing_movement,
    (
        sml.picking_type_id IS NULL
        OR NOT (
            sml.picking_type_id ILIKE '%%OUT%%'
            OR sml.picking_type_id ILIKE '%%Store Finished Product%%'
            OR sml.picking_type_id ILIKE '%%Finished Goods%%'
            OR sml.picking_type_id ILIKE '%%Finished Product%%'
            OR sml.picking_type_id ILIKE '%%Delivery%%'
            OR sml.picking_type_id ILIKE '%%Customer%%'
            OR sml.picking_type_id ILIKE '%%Keluar%%'
            OR sml.picking_type_id ILIKE '%%Receipt%%'
            OR sml.picking_type_id ILIKE '%%Vendor%%'
            OR sml.picking_type_id ILIKE '%%Terima%%'
            OR sml.picking_type_id ILIKE '%%Internal%%'
            OR sml.picking_type_id ILIKE '%%INT%%'
            OR sml.picking_type_id ILIKE '%%Transfer%%'
            OR sml.picking_type_id ILIKE '%%Manufacturing%%'
            OR sml.picking_type_id ILIKE '%%Production%%'
            OR sml.picking_type_id ILIKE '%%Pick Components%%'
            OR sml.picking_type_id ILIKE '%%MO%%'
            OR sml.picking_type_id ILIKE '%%MRP%%'
        )
    ) AS is_unknown_movement_type,
    sml.picking_partner_id AS picking_partner_name,
    sml.source AS movement_source,
    sml.company_id AS company_name,
    mo.manufacturing_order_id AS inferred_manufacturing_order_id,
    mo.manufacturing_order_number AS inferred_manufacturing_order_number,
    mo.internal_order_number AS inferred_internal_order_number,
    mo.job_order_number AS inferred_job_order_number,
    direct_so.id AS direct_source_sales_order_id,
    direct_so.name AS direct_source_sales_order_number,
    sol.id AS inferred_sales_order_line_id,
    COALESCE(direct_so.id, line_so.id, mo.inferred_sales_order_id) AS inferred_sales_order_id,
    COALESCE(direct_so.name, line_so.name, mo.inferred_sales_order_number) AS inferred_sales_order_number,
    (mo.manufacturing_order_id IS NOT NULL) AS has_manufacturing_order,
    (COALESCE(direct_so.id, line_so.id, mo.inferred_sales_order_id) IS NOT NULL) AS has_sales_order,
    (sol.id IS NOT NULL) AS has_sales_order_line,
    CASE
        WHEN mo.manufacturing_order_id IS NOT NULL AND sol.id IS NOT NULL THEN 'STOCK_TO_MO_AND_SO_LINE_INFERRED'
        WHEN mo.manufacturing_order_id IS NOT NULL AND direct_so.id IS NOT NULL THEN 'STOCK_TO_MO_AND_SO_INFERRED'
        WHEN mo.manufacturing_order_id IS NOT NULL THEN 'STOCK_TO_MO_INFERRED_BY_REFERENCE'
        WHEN sol.id IS NOT NULL THEN 'STOCK_TO_SO_LINE_INFERRED_BY_SALE_LINE'
        WHEN direct_so.id IS NOT NULL THEN 'STOCK_TO_SO_INFERRED_BY_SOURCE_DOCUMENT'
        ELSE 'STOCK_WITHOUT_SO_OR_MO_MATCH'
    END AS stock_link_status,
    CASE
        WHEN mo.manufacturing_order_id IS NOT NULL AND sol.id IS NOT NULL THEN 'HIGH'
        WHEN mo.manufacturing_order_id IS NOT NULL THEN 'HIGH'
        WHEN sol.id IS NOT NULL THEN 'MEDIUM'
        WHEN direct_so.id IS NOT NULL THEN 'MEDIUM'
        ELSE 'UNKNOWN'
    END AS stock_match_confidence
FROM stock_move_line sml
LEFT JOIN vw_mrp_order_context mo
    ON mo.manufacturing_order_number = sml.reference
LEFT JOIN sale_order direct_so
    ON direct_so.name = sml.x_studio_source_document
LEFT JOIN sale_order_line sol
    ON sml.x_studio_sale_line = sol.id::text
LEFT JOIN sale_order line_so
    ON line_so.name = sol.order_id;

COMMENT ON VIEW vw_stock_movement_context IS
    'Stock movement traceability view. Uses MO reference, SO source document, and SO line custom reference where available.';

CREATE OR REPLACE VIEW vw_approval_product_line_context AS
SELECT
    apl.id AS approval_line_id,
    apl.id AS rkb_line_id,
    apl.approval_request_id,
    apl.approval_request_id AS approval_request_display_name,
    apl.approval_request_numeric_id,
    apl.product_id AS product_name,
    apl.description AS approval_line_description,
    apl.description AS rkb_line_description,
    apl.quantity AS planned_quantity,
    apl.product_uom_id AS unit_of_measure,
    apl.x_studio_unit_price AS planned_unit_price,
    apl.x_studio_subtotal AS planned_subtotal,
    apl.x_studio_date_of_need AS date_of_need,
    apl.x_studio_nomor_io AS approval_line_internal_order_number,
    CASE
        WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
          AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
            THEN BTRIM(apl.approval_request_id::text)
        WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
            THEN BTRIM(apl.x_studio_nomor_io)
        ELSE NULL
    END AS internal_order_number,
    CASE
        WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
            THEN apl.approval_request_numeric_id
        ELSE NULL
    END AS internal_order_id,
    CASE
        WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
          AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
            THEN BTRIM(apl.approval_request_id::text)
        ELSE NULL
    END AS primary_internal_order_number,
    apl.x_studio_nomor_jo AS raw_job_order_number,
    CASE
        WHEN BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(apl.x_studio_nomor_jo)
        ELSE NULL
    END AS normalized_jo_number,
    CASE
        WHEN BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(apl.x_studio_nomor_jo)
        ELSE NULL
    END AS job_order_number,
    apl.x_studio_status AS approval_status,
    UPPER(COALESCE(apl.x_studio_status, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(apl.x_studio_status, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(apl.x_studio_status, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    apl.x_studio_category AS approval_category_raw,
    CASE
        WHEN apl.x_studio_category IS NULL THEN NULL
        WHEN BTRIM(apl.x_studio_category::text) IN ('', '{}', 'New', 'new') THEN NULL
        ELSE UPPER(BTRIM(apl.x_studio_category::text))
    END AS approval_category_normalized,
    CASE
        WHEN apl.x_studio_category IS NULL
          OR BTRIM(apl.x_studio_category::text) IN ('', '{}', 'New', 'new')
            THEN 'UNKNOWN_APPROVAL_CATEGORY'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'RKB' THEN 'RKB_PLANNING'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) IN ('ROP', 'PEMBELIAN') THEN 'ROP_PROCUREMENT_REQUEST'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'MANUFACTURE' THEN 'INTERNAL_ORDER'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'INTERNAL USE' THEN 'OUT_OF_SCOPE_INTERNAL_USE'
        ELSE 'OTHER_APPROVAL_CATEGORY'
    END AS approval_business_type,
    (UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'RKB') AS is_rkb,
    (UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) IN ('ROP', 'PEMBELIAN')) AS is_rop,
    (UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE') AS is_internal_order,
    (UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'INTERNAL USE') AS is_out_of_scope,
    (
        LOWER(COALESCE(apl.x_studio_status, '')) NOT IN ('cancel', 'cancelled')
        AND UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'RKB'
    ) AS is_valid_for_rkb_planning,
    (
        LOWER(COALESCE(apl.x_studio_status, '')) NOT IN ('cancel', 'cancelled')
        AND UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) IN ('ROP', 'PEMBELIAN')
    ) AS is_valid_for_procurement_request,
    (
        LOWER(COALESCE(apl.x_studio_status, '')) NOT IN ('cancel', 'cancelled')
        AND UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
    ) AS is_valid_for_internal_order_flow,
    apl.x_studio_reqestor AS requester_name,
    apl.company_id AS company_name,
    (
        CASE
            WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
              AND apl.approval_request_numeric_id IS NOT NULL
                THEN apl.approval_request_numeric_id::text
            WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
              AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                THEN BTRIM(apl.approval_request_id::text)
            WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                THEN BTRIM(apl.x_studio_nomor_io)
            ELSE NULL
        END
    ) IS NOT NULL AS has_internal_order,
    (BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$') AS has_valid_jo,
    (BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$') AS has_job_order,
    (
        NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_jo, '')), '') IS NOT NULL
        AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
        AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
    ) AS invalid_jo_format,
    (
        (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NOT NULL
        AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
    ) AS invalid_both_io_and_jo,
    (
        (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NULL
        AND (
            NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_jo, '')), '') IS NULL
            OR BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
        )
    ) AS missing_internal_order_and_job_order,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID_JO_FORMAT'
        WHEN (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NOT NULL
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NOT NULL THEN 'IO_BASED_APPROVAL'
        WHEN BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$' THEN 'JO_BASED_APPROVAL'
        ELSE 'UNLINKED_APPROVAL'
    END AS approval_source_type,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID_JO_FORMAT'
        WHEN (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NOT NULL
          AND BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN (
            CASE
                WHEN UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'MANUFACTURE'
                  AND NULLIF(BTRIM(COALESCE(apl.approval_request_id::text, '')), '') IS NOT NULL
                    THEN BTRIM(apl.approval_request_id::text)
                WHEN NULLIF(BTRIM(COALESCE(apl.x_studio_nomor_io, '')), '') IS NOT NULL
                    THEN BTRIM(apl.x_studio_nomor_io)
                ELSE NULL
            END
        ) IS NOT NULL THEN 'IO_BASED_RKB'
        WHEN BTRIM(COALESCE(apl.x_studio_nomor_jo, '')) ~ '^[0-9]{7}$' THEN 'JO_BASED_RKB'
        ELSE 'UNLINKED_RKB'
    END AS rkb_source_type,
    (UPPER(BTRIM(COALESCE(apl.x_studio_category::text, ''))) = 'RKB') AS is_rkb_candidate,
    FALSE AS missing_rkb_category_confirmation,
    CASE
        WHEN apl.x_studio_category IS NULL
          OR BTRIM(apl.x_studio_category::text) IN ('', '{}', 'New', 'new')
            THEN 'UNKNOWN_APPROVAL_CATEGORY'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'RKB' THEN 'RKB_CONFIRMED_BY_CATEGORY'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) IN ('ROP', 'PEMBELIAN') THEN 'ROP_CONFIRMED_BY_CATEGORY'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'MANUFACTURE' THEN 'INTERNAL_ORDER_CONFIRMED_BY_CATEGORY'
        WHEN UPPER(BTRIM(apl.x_studio_category::text)) = 'INTERNAL USE' THEN 'OUT_OF_SCOPE_INTERNAL_USE'
        ELSE 'OTHER_APPROVAL_CATEGORY'
    END AS rkb_category_status
FROM approval_product_line apl;

COMMENT ON VIEW vw_approval_product_line_context IS
    'Approval product line context. Category maps RKB to planning, PEMBELIAN/ROP to procurement request, MANUFACTURE to Internal Order, and INTERNAL USE to out of scope.';

CREATE OR REPLACE VIEW vw_rkb_planning_lines AS
SELECT *
FROM vw_approval_product_line_context
WHERE is_rkb;

COMMENT ON VIEW vw_rkb_planning_lines IS
    'Compatibility view for RKB-only planning lines. Full approval category context is in vw_approval_product_line_context.';

CREATE OR REPLACE VIEW vw_internal_order_context AS
SELECT
    apl.approval_line_id AS internal_order_line_id,
    apl.approval_request_id,
    apl.approval_category_raw,
    apl.approval_category_normalized,
    apl.approval_business_type,
    apl.approval_request_display_name,
    apl.approval_request_numeric_id,
    apl.primary_internal_order_number,
    apl.internal_order_number,
    apl.internal_order_id,
    apl.approval_line_internal_order_number,
    apl.raw_job_order_number,
    apl.normalized_jo_number,
    apl.job_order_number,
    apl.product_name,
    apl.approval_line_description,
    apl.planned_quantity,
    apl.unit_of_measure,
    apl.planned_unit_price,
    apl.planned_subtotal,
    apl.approval_status,
    apl.normalized_status,
    apl.is_cancelled,
    apl.is_valid_for_metrics,
    apl.requester_name,
    apl.date_of_need AS planned_or_needed_date,
    apl.company_name,
    apl.has_internal_order,
    apl.has_valid_jo,
    apl.has_job_order,
    apl.invalid_jo_format,
    apl.invalid_both_io_and_jo,
    apl.missing_internal_order_and_job_order,
    apl.is_valid_for_internal_order_flow,
    COUNT(DISTINCT mo.manufacturing_order_id) FILTER (WHERE mo.is_valid_for_metrics) AS linked_manufacturing_order_count,
    COUNT(DISTINCT mo.manufacturing_order_id) FILTER (WHERE mo.is_cancelled) AS cancelled_linked_manufacturing_order_count,
    BOOL_OR(mo.manufacturing_order_id IS NOT NULL AND mo.is_valid_for_metrics) AS has_linked_manufacturing_order,
    CASE
        WHEN NOT apl.is_valid_for_internal_order_flow THEN 'NOT_ACTIVE_INTERNAL_ORDER_FLOW'
        WHEN apl.invalid_jo_format THEN 'INVALID_JO_FORMAT'
        WHEN apl.invalid_both_io_and_jo THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN NOT apl.has_internal_order AND NOT apl.has_valid_jo THEN 'MISSING_IO_AND_JO'
        WHEN COUNT(DISTINCT mo.manufacturing_order_id) FILTER (WHERE mo.is_valid_for_metrics) > 0 THEN 'INTERNAL_ORDER_TO_MO_LINKED'
        ELSE 'INTERNAL_ORDER_WITHOUT_MO_LINK'
    END AS internal_order_link_status,
    CASE
        WHEN apl.invalid_jo_format OR apl.invalid_both_io_and_jo THEN 'INVALID'
        WHEN COUNT(DISTINCT mo.manufacturing_order_id) FILTER (WHERE mo.is_valid_for_metrics) > 0 THEN 'INFERRED'
        WHEN apl.has_internal_order OR apl.has_valid_jo THEN 'POSSIBLE'
        ELSE 'UNKNOWN'
    END AS internal_order_match_confidence
FROM vw_approval_product_line_context apl
LEFT JOIN vw_mrp_order_context mo
    ON (
        apl.has_internal_order
        AND NULLIF(BTRIM(mo.internal_order_number), '') IS NOT NULL
        AND apl.internal_order_number = mo.internal_order_number
    )
    OR (
        apl.has_valid_jo
        AND mo.has_valid_jo
        AND apl.job_order_number = mo.job_order_number
    )
WHERE apl.is_internal_order
GROUP BY
    apl.approval_line_id,
    apl.approval_request_id,
    apl.approval_category_raw,
    apl.approval_category_normalized,
    apl.approval_business_type,
    apl.approval_request_display_name,
    apl.approval_request_numeric_id,
    apl.primary_internal_order_number,
    apl.internal_order_number,
    apl.internal_order_id,
    apl.approval_line_internal_order_number,
    apl.raw_job_order_number,
    apl.normalized_jo_number,
    apl.job_order_number,
    apl.product_name,
    apl.approval_line_description,
    apl.planned_quantity,
    apl.unit_of_measure,
    apl.planned_unit_price,
    apl.planned_subtotal,
    apl.approval_status,
    apl.normalized_status,
    apl.is_cancelled,
    apl.is_valid_for_metrics,
    apl.requester_name,
    apl.date_of_need,
    apl.company_name,
    apl.has_internal_order,
    apl.has_valid_jo,
    apl.has_job_order,
    apl.invalid_jo_format,
    apl.invalid_both_io_and_jo,
    apl.missing_internal_order_and_job_order,
    apl.is_valid_for_internal_order_flow;

COMMENT ON VIEW vw_internal_order_context IS
    'Internal Order context for v1. Internal Order is approval_product_line category MANUFACTURE. approval_request_id is the primary IO number and links to mrp_production.x_studio_nomor_io; valid JO is secondary.';

CREATE OR REPLACE VIEW vw_procurement_lines AS
SELECT
    pol.id AS procurement_line_id,
    pol.order_id AS purchase_order_reference,
    pol.partner_id AS vendor_name,
    pol.date_approve AS purchase_approval_date,
    pol.date_planned AS purchase_planned_date,
    pol.state AS purchase_line_state,
    UPPER(COALESCE(pol.state, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(pol.state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(pol.state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    pol.product_id AS product_name,
    pol.name AS procurement_line_description,
    pol.product_qty AS ordered_quantity,
    pol.product_uom AS unit_of_measure,
    pol.qty_received AS received_quantity,
    pol.qty_invoiced AS invoiced_quantity,
    pol.currency_id AS currency_name,
    pol.x_studio_currency_rate_inverse AS inverse_currency_rate,
    pol.price_unit AS unit_price,
    pol.price_subtotal AS line_subtotal,
    pol.x_studio_group_po AS purchase_group,
    pol.x_studio_many2one_field_ij0j0 AS internal_order_number,
    pol.x_studio_jo AS raw_job_order_number,
    CASE
        WHEN BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(pol.x_studio_jo)
        ELSE NULL
    END AS normalized_jo_number,
    CASE
        WHEN BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$'
            THEN BTRIM(pol.x_studio_jo)
        ELSE NULL
    END AS job_order_number,
    pol.x_studio_payment_terms AS payment_terms,
    pol.purchaser AS purchaser_name,
    pol.company_id AS company_name,
    pol.taxes_id AS taxes_name,
    (NULLIF(BTRIM(pol.x_studio_many2one_field_ij0j0), '') IS NOT NULL) AS has_internal_order,
    (BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$') AS has_valid_jo,
    (BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$') AS has_job_order,
    (
        NULLIF(BTRIM(COALESCE(pol.x_studio_jo, '')), '') IS NOT NULL
        AND BTRIM(COALESCE(pol.x_studio_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
        AND BTRIM(COALESCE(pol.x_studio_jo, '')) !~ '^[0-9]{7}$'
    ) AS invalid_jo_format,
    (
        NULLIF(BTRIM(pol.x_studio_many2one_field_ij0j0), '') IS NOT NULL
        AND BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$'
    ) AS invalid_both_io_and_jo,
    (
        NULLIF(BTRIM(pol.x_studio_many2one_field_ij0j0), '') IS NULL
        AND (
            NULLIF(BTRIM(COALESCE(pol.x_studio_jo, '')), '') IS NULL
            OR BTRIM(COALESCE(pol.x_studio_jo, '')) IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
        )
    ) AS missing_internal_order_and_job_order,
    CASE
        WHEN NULLIF(BTRIM(COALESCE(pol.x_studio_jo, '')), '') IS NOT NULL
          AND BTRIM(COALESCE(pol.x_studio_jo, '')) NOT IN ('{}', '[]', 'False', 'false', 'None', 'none', 'New', 'new')
          AND BTRIM(COALESCE(pol.x_studio_jo, '')) !~ '^[0-9]{7}$'
            THEN 'INVALID_JO_FORMAT'
        WHEN NULLIF(BTRIM(pol.x_studio_many2one_field_ij0j0), '') IS NOT NULL
          AND BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$'
            THEN 'INVALID_BOTH_IO_AND_JO'
        WHEN NULLIF(BTRIM(pol.x_studio_many2one_field_ij0j0), '') IS NOT NULL THEN 'IO_BASED_PO'
        WHEN BTRIM(COALESCE(pol.x_studio_jo, '')) ~ '^[0-9]{7}$' THEN 'JO_BASED_PO'
        ELSE 'UNLINKED_PO'
    END AS purchase_source_type,
    'PO_IO_JO_CLASSIFIED_FROM_CUSTOM_FIELDS' AS procurement_link_status
FROM purchase_order_line pol;

COMMENT ON VIEW vw_procurement_lines IS
    'Purchase Order line classification. IO field is purchase_order_line.x_studio_many2one_field_ij0j0.';

CREATE OR REPLACE VIEW vw_accounting_sales_lines AS
SELECT
    aml.id AS accounting_line_id,
    aml.move_id AS accounting_move_id,
    aml.move_name AS accounting_move_name,
    aml.date_x AS accounting_date,
    aml.account_id AS account_name,
    aml.partner_id AS partner_id,
    aml.product_id AS product_name,
    aml.product_category_id AS product_category_name,
    aml.name AS accounting_line_description,
    aml.quantity AS accounting_quantity,
    aml.debit,
    aml.credit,
    aml.balance,
    aml.parent_state AS accounting_parent_state,
    UPPER(COALESCE(aml.parent_state, 'UNKNOWN')) AS normalized_status,
    (LOWER(COALESCE(aml.parent_state, '')) IN ('cancel', 'cancelled')) AS is_cancelled,
    (LOWER(COALESCE(aml.parent_state, '')) NOT IN ('cancel', 'cancelled')) AS is_valid_for_metrics,
    aml.x_studio_sales_order AS sales_order_reference,
    CASE
        WHEN aml.x_studio_sales_order IS NULL THEN NULL
        WHEN BTRIM(aml.x_studio_sales_order::text) IN ('', '{}', 'New') THEN NULL
        ELSE BTRIM(aml.x_studio_sales_order::text)
    END AS normalized_sales_order_number,
    aml.company_id AS company_name,
    so.id AS inferred_sales_order_id,
    so.name AS inferred_sales_order_number,
    (so.id IS NOT NULL) AS has_sales_order,
    CASE
        WHEN so.id IS NOT NULL THEN 'ACCOUNTING_TO_SO_INFERRED_BY_SO_NUMBER'
        WHEN aml.x_studio_sales_order IS NULL
          OR BTRIM(aml.x_studio_sales_order::text) IN ('', '{}', 'New') THEN 'ACCOUNTING_WITHOUT_SO_REFERENCE'
        ELSE 'ACCOUNTING_SO_NUMBER_PRESENT_BUT_NO_MATCH'
    END AS accounting_link_status,
    CASE
        WHEN so.id IS NOT NULL THEN 'HIGH'
        WHEN aml.x_studio_sales_order IS NULL
          OR BTRIM(aml.x_studio_sales_order::text) IN ('', '{}', 'New') THEN 'NONE'
        ELSE 'LOW'
    END AS accounting_match_confidence
FROM account_move_line aml
LEFT JOIN sale_order so
    ON (
        CASE
            WHEN aml.x_studio_sales_order IS NULL THEN NULL
            WHEN BTRIM(aml.x_studio_sales_order::text) IN ('', '{}', 'New') THEN NULL
            ELSE BTRIM(aml.x_studio_sales_order::text)
        END
    ) = so.name::text;

COMMENT ON VIEW vw_accounting_sales_lines IS
    'Accounting traceability view. SO link is inferred by normalized account_move_line.x_studio_sales_order = sale_order.name::text. New is treated as null.';

CREATE OR REPLACE VIEW vw_sale_order_internal_order_bridge AS
SELECT
    so.id AS so_id,
    so.name AS so_number,
    io_token.internal_order_id,
    so.x_studio_io_1 AS raw_x_studio_io_1
FROM sale_order so
CROSS JOIN LATERAL (
    SELECT (match_token[1])::bigint AS internal_order_id
    FROM regexp_matches(COALESCE(so.x_studio_io_1::text, ''), '([0-9]+)', 'g') AS match_token
) io_token
WHERE so.x_studio_io_1 IS NOT NULL
  AND BTRIM(so.x_studio_io_1::text) NOT IN ('', '{}', '[]', 'New', 'new', 'False', 'false', 'None', 'none');

COMMENT ON VIEW vw_sale_order_internal_order_bridge IS
    'Many-to-many bridge parsed from sale_order.x_studio_io_1 set/list text such as {1081} or {1361,1578}. internal_order_id is approval_request_id / Internal Order reference.';

CREATE OR REPLACE VIEW vw_manufacturing_flow_context AS
WITH stock_agg AS (
    SELECT
        inferred_manufacturing_order_id AS manufacturing_order_id,
        COUNT(DISTINCT stock_move_line_id) AS stock_movement_count,
        COUNT(DISTINCT stock_move_line_id) FILTER (WHERE is_manufacturing_movement) AS manufacturing_movement_count,
        COUNT(DISTINCT stock_move_line_id) FILTER (WHERE is_finished_goods_store_movement) AS finished_goods_store_movement_count,
        COUNT(DISTINCT stock_move_line_id) FILTER (WHERE is_delivery_movement) AS delivery_movement_count,
        COUNT(DISTINCT stock_move_line_id) FILTER (WHERE is_unknown_movement_type) AS unknown_movement_type_count,
        COALESCE(SUM(moved_quantity), 0) AS moved_quantity_total
    FROM vw_stock_movement_context
    WHERE inferred_manufacturing_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_manufacturing_order_id
),
accounting_agg AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        COUNT(DISTINCT accounting_line_id) AS accounting_line_count,
        COUNT(DISTINCT accounting_move_id) AS accounting_move_count
    FROM vw_accounting_sales_lines
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id
)
SELECT
    io.internal_order_line_id,
    io.approval_request_id,
    io.approval_request_display_name,
    io.approval_request_numeric_id,
    io.primary_internal_order_number,
    io.internal_order_number,
    io.internal_order_id,
    io.approval_line_internal_order_number,
    io.raw_job_order_number,
    io.normalized_jo_number,
    io.job_order_number,
    io.product_name AS internal_order_product_name,
    io.planned_quantity AS internal_order_quantity,
    io.approval_status AS internal_order_status,
    io.normalized_status AS internal_order_normalized_status,
    io.is_cancelled AS internal_order_is_cancelled,
    io.is_valid_for_metrics AS internal_order_is_valid_for_metrics,
    io.requester_name,
    io.planned_or_needed_date,
    io.company_name,
    mo.manufacturing_order_id,
    mo.manufacturing_order_number,
    mo.manufactured_product_name,
    mo.manufacturing_quantity,
    mo.manufacturing_order_state,
    mo.normalized_status AS manufacturing_normalized_status,
    mo.is_cancelled AS manufacturing_is_cancelled,
    mo.is_valid_for_metrics AS manufacturing_is_valid_for_metrics,
    mo.manufacturing_source_type,
    mo.manufacturing_source_link_status,
    mo.inferred_sales_order_id,
    mo.inferred_sales_order_number,
    (mo.inferred_sales_order_id IS NOT NULL) AS has_later_sales_order,
    COALESCE(stock.stock_movement_count, 0) AS stock_movement_count,
    COALESCE(stock.manufacturing_movement_count, 0) AS manufacturing_movement_count,
    COALESCE(stock.finished_goods_store_movement_count, 0) AS finished_goods_store_movement_count,
    COALESCE(stock.delivery_movement_count, 0) AS delivery_movement_count,
    COALESCE(stock.unknown_movement_type_count, 0) AS unknown_movement_type_count,
    COALESCE(stock.moved_quantity_total, 0) AS moved_quantity_total,
    COALESCE(accounting.accounting_line_count, 0) AS accounting_line_count,
    COALESCE(accounting.accounting_move_count, 0) AS accounting_move_count,
    (mo.manufacturing_order_id IS NOT NULL AND mo.is_valid_for_metrics) AS has_manufacturing_order,
    (COALESCE(stock.stock_movement_count, 0) > 0) AS has_stock_movement,
    (COALESCE(stock.finished_goods_store_movement_count, 0) > 0) AS has_finished_goods_store_movement,
    (COALESCE(stock.delivery_movement_count, 0) > 0) AS has_delivery_movement,
    (COALESCE(accounting.accounting_line_count, 0) > 0) AS has_accounting_line,
    CASE
        WHEN io.is_cancelled OR COALESCE(mo.is_cancelled, FALSE) THEN 'CANCELLED_RECORD'
        WHEN mo.manufacturing_order_id IS NULL THEN 'INTERNAL_ORDER_WITHOUT_MO_LINK'
        WHEN mo.inferred_sales_order_id IS NULL THEN 'IO_TO_MO_NO_SO_LINK_YET'
        WHEN COALESCE(stock.stock_movement_count, 0) = 0 THEN 'IO_TO_MO_SO_WITHOUT_STOCK_MOVEMENT'
        WHEN COALESCE(accounting.accounting_line_count, 0) = 0 THEN 'IO_TO_MO_SO_STOCK_WITHOUT_ACCOUNTING'
        ELSE 'IO_MO_SO_STOCK_ACCOUNTING_TRACE'
    END AS manufacturing_flow_status,
    CASE
        WHEN io.invalid_jo_format OR io.invalid_both_io_and_jo THEN 'INVALID'
        WHEN mo.manufacturing_order_id IS NOT NULL AND mo.inferred_sales_order_id IS NOT NULL THEN 'INFERRED'
        WHEN mo.manufacturing_order_id IS NOT NULL THEN 'PARTIAL'
        ELSE 'UNKNOWN'
    END AS manufacturing_flow_confidence
FROM vw_internal_order_context io
LEFT JOIN vw_mrp_order_context mo
    ON (
        io.has_internal_order
        AND NULLIF(BTRIM(mo.internal_order_number), '') IS NOT NULL
        AND io.internal_order_number = mo.internal_order_number
    )
    OR (
        io.has_valid_jo
        AND mo.has_valid_jo
        AND io.job_order_number = mo.job_order_number
    )
LEFT JOIN stock_agg stock
    ON stock.manufacturing_order_id = mo.manufacturing_order_id
LEFT JOIN accounting_agg accounting
    ON accounting.sales_order_id = mo.inferred_sales_order_id;

COMMENT ON VIEW vw_manufacturing_flow_context IS
    'Manufacturing flow context from Internal Order approval lines (MANUFACTURE) to MO, stock movement, later SO, and accounting. approval_request_id is the primary IO bridge to MO. SO link is not forced when unavailable.';

CREATE OR REPLACE VIEW vw_sales_order_line_source_context AS
WITH mo_by_so_product AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        manufactured_product_name AS product_name,
        COUNT(DISTINCT manufacturing_order_id) AS matching_mo_count
    FROM vw_mrp_order_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
    GROUP BY inferred_sales_order_id, manufactured_product_name
),
delivery_by_line AS (
    SELECT
        inferred_sales_order_line_id AS sales_order_line_id,
        COUNT(DISTINCT stock_move_line_id) AS matching_stock_movement_count
    FROM vw_stock_movement_context
    WHERE inferred_sales_order_line_id IS NOT NULL
      AND is_valid_for_metrics
      AND is_delivery_movement
    GROUP BY inferred_sales_order_line_id
),
delivery_by_so_product AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        product_name,
        COUNT(DISTINCT stock_move_line_id) AS matching_stock_movement_count
    FROM vw_stock_movement_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
      AND is_delivery_movement
    GROUP BY inferred_sales_order_id, product_name
),
unknown_movement_by_line AS (
    SELECT
        inferred_sales_order_line_id AS sales_order_line_id,
        COUNT(DISTINCT stock_move_line_id) AS unknown_movement_count
    FROM vw_stock_movement_context
    WHERE inferred_sales_order_line_id IS NOT NULL
      AND is_valid_for_metrics
      AND is_unknown_movement_type
    GROUP BY inferred_sales_order_line_id
),
unknown_movement_by_so_product AS (
    SELECT
        inferred_sales_order_id AS sales_order_id,
        product_name,
        COUNT(DISTINCT stock_move_line_id) AS unknown_movement_count
    FROM vw_stock_movement_context
    WHERE inferred_sales_order_id IS NOT NULL
      AND is_valid_for_metrics
      AND is_unknown_movement_type
    GROUP BY inferred_sales_order_id, product_name
),
so_internal_order_bridge AS (
    SELECT
        so_id AS sales_order_id,
        COUNT(DISTINCT internal_order_id) AS internal_order_reference_count
    FROM vw_sale_order_internal_order_bridge
    GROUP BY so_id
)
SELECT
    sor.sales_order_id,
    sor.sales_order_number,
    sor.sales_order_line_id,
    sor.product_name,
    sor.line_description,
    sor.ordered_quantity,
    sor.delivered_quantity,
    sor.invoiced_quantity,
    sor.line_subtotal,
    sor.sales_order_state,
    sor.normalized_status,
    sor.is_cancelled,
    sor.is_valid_for_metrics,
    sor.delivery_status,
    sor.invoice_status,
    sor.sales_order_io_number,
    sor.sales_order_line_io_number,
    (COALESCE(so_internal_order_bridge.internal_order_reference_count, 0) > 0) AS has_internal_order,
    COALESCE(so_internal_order_bridge.internal_order_reference_count, 0) AS internal_order_reference_count,
    COALESCE(mo_by_so_product.matching_mo_count, 0) AS matching_mo_count,
    COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) AS matching_stock_movement_count,
    COALESCE(unknown_movement_by_line.unknown_movement_count, unknown_movement_by_so_product.unknown_movement_count, 0) AS unknown_movement_count,
    (COALESCE(mo_by_so_product.matching_mo_count, 0) > 0) AS has_mo,
    (COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0) AS has_stock_movement,
    (COALESCE(unknown_movement_by_line.unknown_movement_count, unknown_movement_by_so_product.unknown_movement_count, 0) > 0) AS needs_movement_classification,
    CASE
        WHEN NOT sor.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(so_internal_order_bridge.internal_order_reference_count, 0) > 0 THEN 'FROM_INTERNAL_ORDER'
        WHEN COALESCE(mo_by_so_product.matching_mo_count, 0) > 0
          AND COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0
            THEN 'MIXED_SOURCE'
        WHEN COALESCE(mo_by_so_product.matching_mo_count, 0) > 0 THEN 'MAKE_TO_ORDER'
        WHEN COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0 THEN 'FROM_STOCK'
        WHEN COALESCE(unknown_movement_by_line.unknown_movement_count, unknown_movement_by_so_product.unknown_movement_count, 0) > 0 THEN 'NEEDS_MOVEMENT_CLASSIFICATION'
        ELSE 'UNKNOWN_SOURCE'
    END AS line_source_type,
    CASE
        WHEN NOT sor.is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN COALESCE(so_internal_order_bridge.internal_order_reference_count, 0) > 0 THEN 'CONFIRMED_IO_BRIDGE'
        WHEN COALESCE(mo_by_so_product.matching_mo_count, 0) > 0
          AND COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0
            THEN 'POSSIBLE_PARTIAL_STOCK_AND_MO'
        WHEN COALESCE(mo_by_so_product.matching_mo_count, 0) > 0 THEN 'INFERRED_BY_SO_ORIGIN_AND_PRODUCT'
        WHEN COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0 THEN 'INFERRED_BY_DELIVERY_MOVEMENT'
        WHEN COALESCE(unknown_movement_by_line.unknown_movement_count, unknown_movement_by_so_product.unknown_movement_count, 0) > 0 THEN 'NEEDS_PICKING_TYPE_CLASSIFICATION'
        ELSE 'UNKNOWN_MISSING_IO_FIELD_STOCK_MOVE_OR_MO_LINK'
    END AS line_source_link_status,
    CASE
        WHEN NOT sor.is_valid_for_metrics THEN 'CANCELLED'
        WHEN COALESCE(so_internal_order_bridge.internal_order_reference_count, 0) > 0 THEN 'CONFIRMED'
        WHEN COALESCE(mo_by_so_product.matching_mo_count, 0) > 0
          OR COALESCE(delivery_by_line.matching_stock_movement_count, delivery_by_so_product.matching_stock_movement_count, 0) > 0
            THEN 'INFERRED'
        WHEN COALESCE(unknown_movement_by_line.unknown_movement_count, unknown_movement_by_so_product.unknown_movement_count, 0) > 0 THEN 'UNKNOWN'
        ELSE 'UNKNOWN'
    END AS line_source_confidence,
    sor.missing_sales_order_io_field,
    sor.missing_sales_order_line_io_field
FROM vw_sales_order_revenue sor
LEFT JOIN mo_by_so_product
    ON mo_by_so_product.sales_order_id = sor.sales_order_id
   AND mo_by_so_product.product_name = sor.product_name
LEFT JOIN delivery_by_line
    ON delivery_by_line.sales_order_line_id = sor.sales_order_line_id
LEFT JOIN delivery_by_so_product
    ON delivery_by_so_product.sales_order_id = sor.sales_order_id
   AND delivery_by_so_product.product_name = sor.product_name
LEFT JOIN unknown_movement_by_line
    ON unknown_movement_by_line.sales_order_line_id = sor.sales_order_line_id
LEFT JOIN unknown_movement_by_so_product
    ON unknown_movement_by_so_product.sales_order_id = sor.sales_order_id
   AND unknown_movement_by_so_product.product_name = sor.product_name
LEFT JOIN so_internal_order_bridge
    ON so_internal_order_bridge.sales_order_id = sor.sales_order_id
WHERE sor.sales_order_line_id IS NOT NULL;

COMMENT ON VIEW vw_sales_order_line_source_context IS
    'SO line-level fulfillment/source classification. IO rule cannot be confirmed until x_studio_io_1 is extracted on SO or SO line.';

CREATE OR REPLACE VIEW vw_sales_order_source_summary AS
WITH so_base AS (
    SELECT
        id AS sales_order_id,
        name AS sales_order_number,
        UPPER(COALESCE(state, 'unknown')) AS normalized_status,
        (LOWER(COALESCE(state, '')) = 'cancel') AS is_cancelled,
        (LOWER(COALESCE(state, '')) <> 'cancel') AS is_valid_for_metrics
    FROM sale_order
),
line_counts AS (
    SELECT
        sales_order_id,
        sales_order_number,
        COUNT(*) AS sales_order_line_count,
        COUNT(DISTINCT line_source_type) AS distinct_line_source_type_count,
        COUNT(*) FILTER (WHERE line_source_type = 'FROM_INTERNAL_ORDER') AS from_internal_order_line_count,
        COUNT(*) FILTER (WHERE line_source_type = 'FROM_STOCK') AS from_stock_line_count,
        COUNT(*) FILTER (WHERE line_source_type = 'MAKE_TO_ORDER') AS make_to_order_line_count,
        COUNT(*) FILTER (WHERE line_source_type = 'MIXED_SOURCE') AS mixed_source_line_count,
        COUNT(*) FILTER (WHERE line_source_type = 'NEEDS_MOVEMENT_CLASSIFICATION') AS needs_movement_classification_line_count,
        COUNT(*) FILTER (WHERE line_source_type = 'UNKNOWN_SOURCE') AS unknown_source_line_count,
        BOOL_OR(has_internal_order) AS has_internal_order,
        BOOL_OR(has_mo) AS has_mo,
        BOOL_OR(has_stock_movement) AS has_stock_movement
    FROM vw_sales_order_line_source_context
    WHERE is_valid_for_metrics
    GROUP BY sales_order_id, sales_order_number
),
only_source AS (
    SELECT
        sales_order_id,
        MIN(line_source_type) AS only_source_type
    FROM vw_sales_order_line_source_context
    WHERE is_valid_for_metrics
    GROUP BY sales_order_id
),
classified AS (
    SELECT
        so.sales_order_id,
        so.sales_order_number,
        so.normalized_status,
        so.is_cancelled,
        so.is_valid_for_metrics,
        COALESCE(lc.sales_order_line_count, 0) AS sales_order_line_count,
        COALESCE(lc.distinct_line_source_type_count, 0) AS distinct_line_source_type_count,
        COALESCE(lc.from_internal_order_line_count, 0) AS from_internal_order_line_count,
        COALESCE(lc.from_stock_line_count, 0) AS from_stock_line_count,
        COALESCE(lc.make_to_order_line_count, 0) AS make_to_order_line_count,
        COALESCE(lc.mixed_source_line_count, 0) AS mixed_source_line_count,
        COALESCE(lc.needs_movement_classification_line_count, 0) AS needs_movement_classification_line_count,
        COALESCE(lc.unknown_source_line_count, 0) AS unknown_source_line_count,
        COALESCE(lc.has_internal_order, FALSE) AS has_internal_order,
        COALESCE(lc.has_mo, FALSE) AS has_mo,
        COALESCE(lc.has_stock_movement, FALSE) AS has_stock_movement,
        os.only_source_type
    FROM so_base so
    LEFT JOIN line_counts lc
        ON lc.sales_order_id = so.sales_order_id
    LEFT JOIN only_source os
        ON os.sales_order_id = so.sales_order_id
)
SELECT
    sales_order_id,
    sales_order_number,
    normalized_status,
    is_cancelled,
    is_valid_for_metrics,
    sales_order_line_count,
    from_internal_order_line_count,
    from_stock_line_count,
    make_to_order_line_count,
    mixed_source_line_count,
    needs_movement_classification_line_count,
    unknown_source_line_count,
    has_internal_order,
    has_mo,
    has_stock_movement,
    CASE
        WHEN NOT is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN sales_order_line_count = 0 THEN 'UNKNOWN_SOURCE'
        WHEN distinct_line_source_type_count = 1 THEN only_source_type
        ELSE 'MIXED_SOURCE'
    END AS sales_order_source_type,
    CASE
        WHEN NOT is_valid_for_metrics THEN 'CANCELLED_RECORD'
        WHEN sales_order_line_count = 0 THEN 'UNKNOWN_NO_ACTIVE_LINES'
        WHEN distinct_line_source_type_count = 1 THEN 'ALL_ACTIVE_LINES_SAME_SOURCE'
        ELSE 'MULTIPLE_ACTIVE_LINE_SOURCE_TYPES'
    END AS sales_order_source_link_status
FROM classified;

COMMENT ON VIEW vw_sales_order_source_summary IS
    'SO header source classification derived from SO line-level source classification. Mixed fulfillment is preserved as MIXED_SOURCE.';

