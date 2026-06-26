-- ============================================================================= -- Phase 1 - Internal Order Cost Rekap Views -- ============================================================================= -- Purpose: --   Additive SQL layer for pre-Sales-Order Internal Order cases. -- -- Phase 1 basis: --   RKB Actual, ROP / PEMBELIAN, and PO are compared directly at the --   internal_order_number grain. RKB PPIC remains a future/manual Excel --   staging source and is not imported here. -- -- Scope: --   Internal Order-first reconciliation only. --   Sales Order / Job Order views remain unchanged and separate. -- -- Explicitly out of scope: --   Profitability, margin, COGS, accounting profit, AR/payment, UI/API, --   and RKB PPIC upload/import workflow. -- =============================================================================  DROP VIEW IF EXISTS vw_internal_order_rekap_summary CASCADE; DROP VIEW IF EXISTS vw_internal_order_rekap_lines CASCADE; DROP VIEW IF EXISTS vw_internal_order_product_universe CASCADE; DROP VIEW IF EXISTS vw_internal_order_po_agg CASCADE; DROP VIEW IF EXISTS vw_internal_order_rop_agg CASCADE; DROP VIEW IF EXISTS vw_internal_order_rkb_actual_agg CASCADE; DROP VIEW IF EXISTS vw_internal_order_rekap_scope CASCADE;  CREATE VIEW vw_internal_order_rekap_scope AS WITH source_rows AS (     SELECT         NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') AS internal_order_number,         rkb.company_name::text AS company_name,         rkb.approval_line_id::text AS source_row_id,         'RKB_ACTUAL'::text AS source_type     FROM vw_rkb_planning_lines rkb     WHERE rkb.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(rkb.approval_status::text, '') ILIKE '%cancel%'          OR COALESCE(rkb.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(rkb.approval_status::text, '') ILIKE '%reject%'          OR COALESCE(rkb.normalized_status::text, '') ILIKE '%reject%'       )      UNION ALL      SELECT         NULLIF(BTRIM(COALESCE(rop.internal_order_number::text, '')), '') AS internal_order_number,         rop.company_name::text AS company_name,         rop.approval_line_id::text AS source_row_id,         'ROP'::text AS source_type     FROM vw_approval_product_line_context rop     WHERE rop.approval_business_type = 'ROP_PROCUREMENT_REQUEST'       AND rop.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(rop.internal_order_number::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(rop.approval_status::text, '') ILIKE '%cancel%'          OR COALESCE(rop.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(rop.approval_status::text, '') ILIKE '%reject%'          OR COALESCE(rop.normalized_status::text, '') ILIKE '%reject%'       )      UNION ALL      SELECT         NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') AS internal_order_number,         po.company_name::text AS company_name,         po.procurement_line_id::text AS source_row_id,         'PO'::text AS source_type     FROM vw_procurement_lines po     WHERE po.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(po.purchase_line_state::text, '') ILIKE '%cancel%'          OR COALESCE(po.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(po.purchase_line_state::text, '') ILIKE '%reject%'          OR COALESCE(po.normalized_status::text, '') ILIKE '%reject%'       ) ), bridge_flags AS (     SELECT DISTINCT         NULLIF(BTRIM(COALESCE(bridge.raw_x_studio_io_1::text, bridge.internal_order_id::text, '')), '') AS internal_order_number,         TRUE AS has_sales_order_link     FROM vw_sale_order_internal_order_bridge bridge     WHERE NULLIF(BTRIM(COALESCE(bridge.raw_x_studio_io_1::text, bridge.internal_order_id::text, '')), '') IS NOT NULL ) SELECT     src.internal_order_number,     STRING_AGG(DISTINCT src.company_name, ', ' ORDER BY src.company_name)         FILTER (WHERE NULLIF(BTRIM(COALESCE(src.company_name, '')), '') IS NOT NULL) AS company_name,     COUNT(*) AS source_row_count,     COUNT(*) FILTER (WHERE src.source_type = 'RKB_ACTUAL') AS rkb_actual_row_count,     COUNT(*) FILTER (WHERE src.source_type = 'ROP') AS rop_row_count,     COUNT(*) FILTER (WHERE src.source_type = 'PO') AS po_row_count,     COUNT(DISTINCT src.source_row_id) FILTER (WHERE src.source_type = 'RKB_ACTUAL') AS rkb_actual_count,     COUNT(DISTINCT src.source_row_id) FILTER (WHERE src.source_type = 'ROP') AS rop_count,     COUNT(DISTINCT src.source_row_id) FILTER (WHERE src.source_type = 'PO') AS po_count,     CASE WHEN COUNT(*) FILTER (WHERE src.source_type = 'RKB_ACTUAL') > 0 THEN TRUE ELSE FALSE END AS has_rkb_actual,     CASE WHEN COUNT(*) FILTER (WHERE src.source_type = 'ROP') > 0 THEN TRUE ELSE FALSE END AS has_rop,     CASE WHEN COUNT(*) FILTER (WHERE src.source_type = 'PO') > 0 THEN TRUE ELSE FALSE END AS has_po,     COALESCE(BOOL_OR(bridge_flags.has_sales_order_link), FALSE) AS has_sales_order_link FROM source_rows src LEFT JOIN bridge_flags     ON bridge_flags.internal_order_number = src.internal_order_number GROUP BY src.internal_order_number;  COMMENT ON VIEW vw_internal_order_rekap_scope IS     'Phase 1 Internal Order scope. One row per internal_order_number with RKB / ROP / PO source presence and Sales Order bridge flag.';  CREATE VIEW vw_internal_order_rkb_actual_agg AS WITH source_rows AS (     SELECT         NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') AS internal_order_number,         COALESCE(             NULLIF(BTRIM((regexp_match(COALESCE(rkb.product_name::text, ''), '^\[([^\]]+)\]'))[1]), ''),             NULLIF(LOWER(REGEXP_REPLACE(BTRIM(COALESCE(rkb.product_name::text, '')), '[[:space:]]+', ' ', 'g')), '')         ) AS product_key,         NULLIF(BTRIM(COALESCE(rkb.product_name::text, '')), '') AS product_name,         NULLIF(BTRIM(COALESCE(rkb.unit_of_measure::text, '')), '') AS unit_of_measure,         COALESCE(rkb.planned_quantity, 0)::numeric AS qty,         COALESCE(rkb.planned_subtotal, 0)::numeric AS subtotal,         rkb.date_of_need,         rkb.approval_line_id,         NULLIF(BTRIM(COALESCE(rkb.approval_request_id::text, '')), '') AS approval_request_id,         NULLIF(BTRIM(COALESCE(rkb.approval_request_numeric_id::text, '')), '') AS approval_request_numeric_id,         NULLIF(BTRIM(COALESCE(rkb.approval_status::text, '')), '') AS approval_status,         NULLIF(BTRIM(COALESCE(rkb.normalized_status::text, '')), '') AS normalized_status     FROM vw_rkb_planning_lines rkb     WHERE rkb.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') IS NOT NULL       AND NULLIF(BTRIM(COALESCE(rkb.product_name::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(rkb.approval_status::text, '') ILIKE '%cancel%'          OR COALESCE(rkb.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(rkb.approval_status::text, '') ILIKE '%reject%'          OR COALESCE(rkb.normalized_status::text, '') ILIKE '%reject%'       ) ) SELECT     source_rows.internal_order_number,     source_rows.product_key,     MAX(source_rows.product_name) AS product_name,     STRING_AGG(DISTINCT source_rows.unit_of_measure, ', ' ORDER BY source_rows.unit_of_measure)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '') IS NOT NULL) AS rkb_actual_uom_summary,     COUNT(DISTINCT NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '')) AS rkb_actual_uom_count,     COALESCE(SUM(source_rows.qty), 0)::numeric AS rkb_actual_qty,     CASE WHEN COALESCE(SUM(source_rows.qty), 0) <> 0          THEN COALESCE(SUM(source_rows.subtotal), 0)::numeric / NULLIF(COALESCE(SUM(source_rows.qty), 0), 0)          ELSE NULL     END AS rkb_actual_unit_price,     COALESCE(SUM(source_rows.subtotal), 0)::numeric AS rkb_actual_subtotal,     COUNT(DISTINCT source_rows.approval_line_id) AS rkb_actual_line_count,     STRING_AGG(DISTINCT source_rows.approval_status, ', ' ORDER BY source_rows.approval_status)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_status, '')), '') IS NOT NULL) AS rkb_actual_status_summary,     STRING_AGG(DISTINCT source_rows.normalized_status, ', ' ORDER BY source_rows.normalized_status)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.normalized_status, '')), '') IS NOT NULL) AS rkb_actual_normalized_status_summary,     STRING_AGG(DISTINCT source_rows.approval_request_id, ', ' ORDER BY source_rows.approval_request_id)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_request_id, '')), '') IS NOT NULL) AS rkb_actual_request_summary,     STRING_AGG(DISTINCT source_rows.approval_request_numeric_id, ', ' ORDER BY source_rows.approval_request_numeric_id)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_request_numeric_id, '')), '') IS NOT NULL) AS rkb_actual_request_numeric_summary,     MIN(source_rows.date_of_need) AS rkb_actual_date_of_need_min,     MAX(source_rows.date_of_need) AS rkb_actual_date_of_need_max FROM source_rows GROUP BY source_rows.internal_order_number, source_rows.product_key;  COMMENT ON VIEW vw_internal_order_rkb_actual_agg IS     'Aggregates current/latest Odoo RKB Actual lines by internal_order_number + product_key. Baseline only, not profitability or stock valuation.';  CREATE VIEW vw_internal_order_rop_agg AS WITH source_rows AS (     SELECT         NULLIF(BTRIM(COALESCE(rop.internal_order_number::text, '')), '') AS internal_order_number,         COALESCE(             NULLIF(BTRIM((regexp_match(COALESCE(rop.product_name::text, ''), '^\[([^\]]+)\]'))[1]), ''),             NULLIF(LOWER(REGEXP_REPLACE(BTRIM(COALESCE(rop.product_name::text, '')), '[[:space:]]+', ' ', 'g')), '')         ) AS product_key,         NULLIF(BTRIM(COALESCE(rop.product_name::text, '')), '') AS product_name,         NULLIF(BTRIM(COALESCE(rop.unit_of_measure::text, '')), '') AS unit_of_measure,         COALESCE(rop.planned_quantity, 0)::numeric AS qty,         COALESCE(rop.planned_subtotal, 0)::numeric AS subtotal,         rop.date_of_need,         rop.approval_line_id,         NULLIF(BTRIM(COALESCE(rop.approval_request_id::text, '')), '') AS approval_request_id,         NULLIF(BTRIM(COALESCE(rop.approval_request_numeric_id::text, '')), '') AS approval_request_numeric_id,         NULLIF(BTRIM(COALESCE(rop.approval_status::text, '')), '') AS approval_status,         NULLIF(BTRIM(COALESCE(rop.normalized_status::text, '')), '') AS normalized_status,         NULLIF(BTRIM(COALESCE(rop.approval_category_raw::text, '')), '') AS approval_category_raw,         NULLIF(BTRIM(COALESCE(rop.approval_business_type::text, '')), '') AS approval_business_type     FROM vw_approval_product_line_context rop     WHERE rop.approval_business_type = 'ROP_PROCUREMENT_REQUEST'       AND rop.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(rop.internal_order_number::text, '')), '') IS NOT NULL       AND NULLIF(BTRIM(COALESCE(rop.product_name::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(rop.approval_status::text, '') ILIKE '%cancel%'          OR COALESCE(rop.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(rop.approval_status::text, '') ILIKE '%reject%'          OR COALESCE(rop.normalized_status::text, '') ILIKE '%reject%'       ) ) SELECT     source_rows.internal_order_number,     source_rows.product_key,     MAX(source_rows.product_name) AS product_name,     STRING_AGG(DISTINCT source_rows.unit_of_measure, ', ' ORDER BY source_rows.unit_of_measure)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '') IS NOT NULL) AS rop_uom_summary,     COUNT(DISTINCT NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '')) AS rop_uom_count,     COALESCE(SUM(source_rows.qty), 0)::numeric AS rop_qty,     CASE WHEN COALESCE(SUM(source_rows.qty), 0) <> 0          THEN COALESCE(SUM(source_rows.subtotal), 0)::numeric / NULLIF(COALESCE(SUM(source_rows.qty), 0), 0)          ELSE NULL     END AS rop_unit_price,     COALESCE(SUM(source_rows.subtotal), 0)::numeric AS rop_subtotal,     COUNT(DISTINCT source_rows.approval_line_id) AS rop_line_count,     MIN(source_rows.date_of_need) AS rop_date_of_need_min,     MAX(source_rows.date_of_need) AS rop_date_of_need_max,     STRING_AGG(DISTINCT source_rows.approval_status, ', ' ORDER BY source_rows.approval_status)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_status, '')), '') IS NOT NULL) AS rop_status_summary,     STRING_AGG(DISTINCT source_rows.normalized_status, ', ' ORDER BY source_rows.normalized_status)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.normalized_status, '')), '') IS NOT NULL) AS rop_normalized_status_summary,     STRING_AGG(DISTINCT source_rows.approval_category_raw, ', ' ORDER BY source_rows.approval_category_raw)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_category_raw, '')), '') IS NOT NULL) AS rop_category_summary,     STRING_AGG(DISTINCT source_rows.approval_request_id, ', ' ORDER BY source_rows.approval_request_id)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_request_id, '')), '') IS NOT NULL) AS rop_request_summary,     STRING_AGG(DISTINCT source_rows.approval_request_numeric_id, ', ' ORDER BY source_rows.approval_request_numeric_id)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.approval_request_numeric_id, '')), '') IS NOT NULL) AS rop_request_numeric_summary FROM source_rows GROUP BY source_rows.internal_order_number, source_rows.product_key;  COMMENT ON VIEW vw_internal_order_rop_agg IS     'Aggregates ROP / PEMBELIAN approval lines by internal_order_number + product_key. ROP and PEMBELIAN have the same business meaning.';  CREATE VIEW vw_internal_order_po_agg AS WITH source_rows AS (     SELECT         NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') AS internal_order_number,         COALESCE(             NULLIF(BTRIM((regexp_match(COALESCE(po.product_name::text, ''), '^\[([^\]]+)\]'))[1]), ''),             NULLIF(LOWER(REGEXP_REPLACE(BTRIM(COALESCE(po.product_name::text, '')), '[[:space:]]+', ' ', 'g')), '')         ) AS product_key,         NULLIF(BTRIM(COALESCE(po.product_name::text, '')), '') AS product_name,         NULLIF(BTRIM(COALESCE(po.unit_of_measure::text, '')), '') AS unit_of_measure,         COALESCE(po.ordered_quantity, 0)::numeric AS ordered_quantity,         COALESCE(po.received_quantity, 0)::numeric AS received_quantity,         COALESCE(po.invoiced_quantity, 0)::numeric AS invoiced_quantity,         COALESCE(po.unit_price, 0)::numeric AS unit_price,         COALESCE(po.line_subtotal, 0)::numeric AS line_subtotal,         po.purchase_planned_date,         NULLIF(BTRIM(COALESCE(po.purchase_line_state::text, '')), '') AS purchase_line_state,         po.procurement_line_id,         NULLIF(BTRIM(COALESCE(po.purchase_order_reference::text, '')), '') AS purchase_order_reference     FROM vw_procurement_lines po     WHERE po.is_valid_for_metrics       AND NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') IS NOT NULL       AND NULLIF(BTRIM(COALESCE(po.product_name::text, '')), '') IS NOT NULL       AND NOT (             COALESCE(po.purchase_line_state::text, '') ILIKE '%cancel%'          OR COALESCE(po.normalized_status::text, '') ILIKE '%cancel%'          OR COALESCE(po.purchase_line_state::text, '') ILIKE '%reject%'          OR COALESCE(po.normalized_status::text, '') ILIKE '%reject%'       ) ) SELECT     source_rows.internal_order_number,     source_rows.product_key,     MAX(source_rows.product_name) AS product_name,     STRING_AGG(DISTINCT source_rows.unit_of_measure, ', ' ORDER BY source_rows.unit_of_measure)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '') IS NOT NULL) AS po_uom_summary,     COUNT(DISTINCT NULLIF(BTRIM(COALESCE(source_rows.unit_of_measure, '')), '')) AS po_uom_count,     COALESCE(SUM(source_rows.ordered_quantity), 0)::numeric AS po_qty,     COALESCE(SUM(source_rows.received_quantity), 0)::numeric AS po_received_qty,     COALESCE(SUM(source_rows.invoiced_quantity), 0)::numeric AS po_invoiced_qty,     CASE WHEN COALESCE(SUM(source_rows.ordered_quantity), 0) <> 0          THEN COALESCE(SUM(source_rows.line_subtotal), 0)::numeric / NULLIF(COALESCE(SUM(source_rows.ordered_quantity), 0), 0)          ELSE NULL     END AS po_unit_price,     COALESCE(SUM(source_rows.line_subtotal), 0)::numeric AS po_subtotal,     COUNT(DISTINCT source_rows.procurement_line_id) AS po_line_count,     MIN(source_rows.purchase_planned_date) AS po_expected_arrival_min,     MAX(source_rows.purchase_planned_date) AS po_expected_arrival_max,     STRING_AGG(DISTINCT source_rows.purchase_line_state, ', ' ORDER BY source_rows.purchase_line_state)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.purchase_line_state, '')), '') IS NOT NULL) AS po_status_summary,     STRING_AGG(DISTINCT source_rows.purchase_order_reference, ', ' ORDER BY source_rows.purchase_order_reference)         FILTER (WHERE NULLIF(BTRIM(COALESCE(source_rows.purchase_order_reference, '')), '') IS NOT NULL) AS po_order_reference_summary FROM source_rows GROUP BY source_rows.internal_order_number, source_rows.product_key;  COMMENT ON VIEW vw_internal_order_po_agg IS     'Aggregates PO execution by internal_order_number + product_key. This is procurement comparison only, not stock valuation or accounting profit.';  CREATE VIEW vw_internal_order_product_universe AS
WITH source_rows AS (
    SELECT
        rkb.internal_order_number,
        rkb.product_key,
        rkb.product_name,
        rkb.rkb_actual_uom_summary AS source_uom_summary,
        rkb.rkb_actual_uom_count AS source_uom_count,
        TRUE AS appears_in_rkb_actual,
        FALSE AS appears_in_rop,
        FALSE AS appears_in_po
    FROM vw_internal_order_rkb_actual_agg rkb

    UNION ALL

    SELECT
        rop.internal_order_number,
        rop.product_key,
        rop.product_name,
        rop.rop_uom_summary AS source_uom_summary,
        rop.rop_uom_count AS source_uom_count,
        FALSE AS appears_in_rkb_actual,
        TRUE AS appears_in_rop,
        FALSE AS appears_in_po
    FROM vw_internal_order_rop_agg rop

    UNION ALL

    SELECT
        po.internal_order_number,
        po.product_key,
        po.product_name,
        po.po_uom_summary AS source_uom_summary,
        po.po_uom_count AS source_uom_count,
        FALSE AS appears_in_rkb_actual,
        FALSE AS appears_in_rop,
        TRUE AS appears_in_po
    FROM vw_internal_order_po_agg po
), classified AS (
    SELECT
        source_rows.*,
        CASE
            WHEN COALESCE(source_rows.product_key, '') ILIKE '!!%%' OR COALESCE(source_rows.product_name, '') ILIKE '!!%%' THEN 'NON_TRACKABLE_OTHERS'
            WHEN COALESCE(source_rows.product_key, '') ILIKE '%%others%%' OR COALESCE(source_rows.product_name, '') ILIKE '%%others%%' THEN 'NON_TRACKABLE_OTHERS'
            WHEN COALESCE(source_rows.product_key, '') ILIKE '%%sisa budget%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%sisa budget%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%estimator%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%estimator%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%jasa%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%jasa%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%machining%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%machining%%' THEN 'BUDGET_SERVICE_ADJUSTMENT'
            WHEN COALESCE(source_rows.product_key, '') ~ '^\[[0-9]{5}\]' OR COALESCE(source_rows.product_name, '') ~ '^\[[0-9]{5}\]' THEN 'TRACKABLE_PRODUCT'
            ELSE 'UNKNOWN_PRODUCT_CLASS'
        END AS product_trackability_class,
        CASE
            WHEN COALESCE(source_rows.product_key, '') ILIKE '!!%%' OR COALESCE(source_rows.product_name, '') ILIKE '!!%%' THEN 'DOUBLE_BANG_OTHERS'
            WHEN COALESCE(source_rows.product_key, '') ILIKE '%%others%%' OR COALESCE(source_rows.product_name, '') ILIKE '%%others%%' THEN 'CONTAINS_OTHERS'
            WHEN COALESCE(source_rows.product_key, '') ILIKE '%%sisa budget%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%sisa budget%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%estimator%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%estimator%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%jasa%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%jasa%%'
              OR COALESCE(source_rows.product_key, '') ILIKE '%%machining%%'
              OR COALESCE(source_rows.product_name, '') ILIKE '%%machining%%' THEN 'BUDGET_SERVICE_TEXT'
            WHEN COALESCE(source_rows.product_key, '') ~ '^\[[0-9]{5}\]' OR COALESCE(source_rows.product_name, '') ~ '^\[[0-9]{5}\]' THEN 'BRACKETED_PRODUCT_CODE'
            ELSE 'UNKNOWN_FALLBACK'
        END AS product_classification_reason,
        CASE
            WHEN COALESCE(source_rows.product_key, '') ~ '^\[[0-9]{5}\]' OR COALESCE(source_rows.product_name, '') ~ '^\[[0-9]{5}\]' THEN TRUE
            ELSE FALSE
        END AS is_trackable_product
    FROM source_rows
)
SELECT
    classified.internal_order_number,
    classified.product_key,
    MAX(classified.product_name) AS product_name,
    BOOL_OR(classified.appears_in_rkb_actual) AS appears_in_rkb_actual,
    BOOL_OR(classified.appears_in_rop) AS appears_in_rop,
    BOOL_OR(classified.appears_in_po) AS appears_in_po,
    STRING_AGG(DISTINCT classified.source_uom_summary, ' ; ' ORDER BY classified.source_uom_summary)
        FILTER (WHERE NULLIF(BTRIM(COALESCE(classified.source_uom_summary, '')), '') IS NOT NULL) AS uom_summary,
    CASE
        WHEN BOOL_OR(classified.appears_in_rkb_actual) AND BOOL_OR(classified.appears_in_rop) AND BOOL_OR(classified.appears_in_po) THEN 'RKB_ROP_PO'
        WHEN BOOL_OR(classified.appears_in_rkb_actual) AND BOOL_OR(classified.appears_in_rop) AND NOT BOOL_OR(classified.appears_in_po) THEN 'RKB_ROP'
        WHEN BOOL_OR(classified.appears_in_rkb_actual) AND NOT BOOL_OR(classified.appears_in_rop) AND BOOL_OR(classified.appears_in_po) THEN 'RKB_PO'
        WHEN NOT BOOL_OR(classified.appears_in_rkb_actual) AND BOOL_OR(classified.appears_in_rop) AND BOOL_OR(classified.appears_in_po) THEN 'ROP_PO'
        WHEN BOOL_OR(classified.appears_in_rkb_actual) AND NOT BOOL_OR(classified.appears_in_rop) AND NOT BOOL_OR(classified.appears_in_po) THEN 'RKB_ONLY'
        WHEN NOT BOOL_OR(classified.appears_in_rkb_actual) AND BOOL_OR(classified.appears_in_rop) AND NOT BOOL_OR(classified.appears_in_po) THEN 'ROP_ONLY'
        WHEN NOT BOOL_OR(classified.appears_in_rkb_actual) AND NOT BOOL_OR(classified.appears_in_rop) AND BOOL_OR(classified.appears_in_po) THEN 'PO_ONLY'
    END AS product_presence_status,
    (
        MAX(COALESCE(classified.source_uom_count, 0)) > 1
        OR COUNT(DISTINCT NULLIF(BTRIM(COALESCE(classified.source_uom_summary, '')), '')) > 1
    ) AS mixed_uom_flag,
    MAX(classified.product_trackability_class) AS product_trackability_class,
    BOOL_OR(classified.is_trackable_product) AS is_trackable_product,
    MAX(classified.product_classification_reason) AS product_classification_reason
FROM classified
WHERE NULLIF(BTRIM(COALESCE(classified.internal_order_number, '')), '') IS NOT NULL
  AND NULLIF(BTRIM(COALESCE(classified.product_key, '')), '') IS NOT NULL
GROUP BY classified.internal_order_number, classified.product_key;

COMMENT ON VIEW vw_internal_order_product_universe IS     'Conservative product universe for Internal Order Rekap. Exact bracketed product code is preferred; normalized product name is the fallback.';  CREATE VIEW vw_internal_order_rekap_lines AS
SELECT
    universe.internal_order_number,
    scope.company_name,
    scope.has_sales_order_link,
    universe.product_key,
    universe.product_name,
    universe.uom_summary,
    rkb.rkb_actual_uom_summary,
    rop.rop_uom_summary,
    po.po_uom_summary,
    universe.product_presence_status,
    universe.mixed_uom_flag,
    universe.product_trackability_class,
    universe.is_trackable_product,
    universe.product_classification_reason,
    COALESCE(rkb.rkb_actual_qty, 0)::numeric AS rkb_actual_qty,
    rkb.rkb_actual_unit_price,
    COALESCE(rkb.rkb_actual_subtotal, 0)::numeric AS rkb_actual_subtotal,
    COALESCE(rkb.rkb_actual_line_count, 0) AS rkb_actual_line_count,
    rkb.rkb_actual_status_summary,
    rkb.rkb_actual_normalized_status_summary,
    rkb.rkb_actual_request_summary,
    rkb.rkb_actual_request_numeric_summary,
    rkb.rkb_actual_date_of_need_min,
    rkb.rkb_actual_date_of_need_max,
    COALESCE(rop.rop_qty, 0)::numeric AS rop_qty,
    rop.rop_unit_price,
    COALESCE(rop.rop_subtotal, 0)::numeric AS rop_subtotal,
    COALESCE(rop.rop_line_count, 0) AS rop_line_count,
    rop.rop_status_summary,
    rop.rop_normalized_status_summary,
    rop.rop_category_summary,
    rop.rop_request_summary,
    rop.rop_request_numeric_summary,
    rop.rop_date_of_need_min,
    rop.rop_date_of_need_max,
    COALESCE(po.po_qty, 0)::numeric AS po_qty,
    COALESCE(po.po_received_qty, 0)::numeric AS po_received_qty,
    COALESCE(po.po_invoiced_qty, 0)::numeric AS po_invoiced_qty,
    po.po_unit_price,
    COALESCE(po.po_subtotal, 0)::numeric AS po_subtotal,
    COALESCE(po.po_line_count, 0) AS po_line_count,
    po.po_expected_arrival_min,
    po.po_expected_arrival_max,
    po.po_status_summary,
    GREATEST(COALESCE(rkb.rkb_actual_qty, 0) - COALESCE(rop.rop_qty, 0), 0)::numeric AS not_yet_rop_qty,
    CASE
        WHEN rkb.rkb_actual_unit_price IS NOT NULL
        THEN (GREATEST(COALESCE(rkb.rkb_actual_qty, 0) - COALESCE(rop.rop_qty, 0), 0) * rkb.rkb_actual_unit_price)::numeric
        ELSE NULL
    END AS not_yet_rop_amount,
    GREATEST(COALESCE(rop.rop_qty, 0) - COALESCE(rkb.rkb_actual_qty, 0), 0)::numeric AS excess_rop_qty,
    CASE
        WHEN rop.rop_unit_price IS NOT NULL
        THEN (GREATEST(COALESCE(rop.rop_qty, 0) - COALESCE(rkb.rkb_actual_qty, 0), 0) * rop.rop_unit_price)::numeric
        ELSE NULL
    END AS excess_rop_amount,
    (COALESCE(po.po_qty, 0) > 0 AND COALESCE(rop.rop_qty, 0) = 0) AS po_without_rop_flag,
    (COALESCE(rop.rop_qty, 0) > 0 AND COALESCE(po.po_qty, 0) = 0) AS rop_without_po_flag,
    'IO_REKAP_LINES'::text AS comparison_scope
FROM vw_internal_order_product_universe universe
LEFT JOIN vw_internal_order_rekap_scope scope
    ON scope.internal_order_number = universe.internal_order_number
LEFT JOIN vw_internal_order_rkb_actual_agg rkb
    ON rkb.internal_order_number = universe.internal_order_number
   AND rkb.product_key = universe.product_key
LEFT JOIN vw_internal_order_rop_agg rop
    ON rop.internal_order_number = universe.internal_order_number
   AND rop.product_key = universe.product_key
LEFT JOIN vw_internal_order_po_agg po
    ON po.internal_order_number = universe.internal_order_number
   AND po.product_key = universe.product_key;

COMMENT ON VIEW vw_internal_order_rekap_lines IS     'Phase 1 Internal Order Rekap lines at internal_order_number + product_key grain. Quantity comparison remains UoM-sensitive and non-converted.';  CREATE VIEW vw_internal_order_rekap_summary AS
SELECT
    lines.internal_order_number,
    MAX(lines.company_name) AS company_name,
    COALESCE(BOOL_OR(lines.has_sales_order_link), FALSE) AS has_sales_order_link,
    COUNT(*) AS product_count,
    COUNT(*) FILTER (WHERE COALESCE(lines.rkb_actual_qty, 0) > 0) AS rkb_actual_product_count,
    COUNT(*) FILTER (WHERE COALESCE(lines.rop_qty, 0) > 0) AS rop_product_count,
    COUNT(*) FILTER (WHERE COALESCE(lines.po_qty, 0) > 0) AS po_product_count,
    SUM(lines.rkb_actual_subtotal)::numeric AS rkb_actual_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'TRACKABLE_PRODUCT' THEN lines.rkb_actual_subtotal ELSE 0 END)::numeric AS rkb_actual_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'NON_TRACKABLE_OTHERS' THEN lines.rkb_actual_subtotal ELSE 0 END)::numeric AS rkb_actual_non_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'UNKNOWN_PRODUCT_CLASS' THEN lines.rkb_actual_subtotal ELSE 0 END)::numeric AS rkb_actual_unknown_class_amount,
    COUNT(*) FILTER (WHERE COALESCE(lines.rkb_actual_qty, 0) > 0 AND lines.product_trackability_class = 'TRACKABLE_PRODUCT') AS rkb_actual_trackable_product_count,
    COUNT(*) FILTER (WHERE COALESCE(lines.rkb_actual_qty, 0) > 0 AND lines.product_trackability_class = 'NON_TRACKABLE_OTHERS') AS rkb_actual_non_trackable_product_count,
    SUM(lines.rop_subtotal)::numeric AS rop_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'TRACKABLE_PRODUCT' THEN lines.rop_subtotal ELSE 0 END)::numeric AS rop_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'NON_TRACKABLE_OTHERS' THEN lines.rop_subtotal ELSE 0 END)::numeric AS rop_non_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'UNKNOWN_PRODUCT_CLASS' THEN lines.rop_subtotal ELSE 0 END)::numeric AS rop_unknown_class_amount,
    SUM(lines.po_subtotal)::numeric AS po_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'TRACKABLE_PRODUCT' THEN lines.po_subtotal ELSE 0 END)::numeric AS po_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'NON_TRACKABLE_OTHERS' THEN lines.po_subtotal ELSE 0 END)::numeric AS po_non_trackable_amount,
    SUM(CASE WHEN lines.product_trackability_class = 'UNKNOWN_PRODUCT_CLASS' THEN lines.po_subtotal ELSE 0 END)::numeric AS po_unknown_class_amount,
    SUM(lines.not_yet_rop_amount)::numeric AS not_yet_rop_amount,
    SUM(lines.excess_rop_amount)::numeric AS excess_rop_amount,
    SUM(lines.po_received_qty)::numeric AS po_received_qty,
    SUM(lines.po_invoiced_qty)::numeric AS po_invoiced_qty,
    SUM(CASE WHEN lines.mixed_uom_flag THEN 1 ELSE 0 END) AS mixed_uom_count,
    SUM(CASE WHEN lines.product_presence_status = 'RKB_ONLY' THEN 1 ELSE 0 END) AS rkb_only_count,
    SUM(CASE WHEN lines.product_presence_status = 'ROP_ONLY' THEN 1 ELSE 0 END) AS rop_only_count,
    SUM(CASE WHEN lines.product_presence_status = 'PO_ONLY' THEN 1 ELSE 0 END) AS po_only_count,
    SUM(CASE WHEN lines.product_presence_status = 'RKB_ROP_PO' THEN 1 ELSE 0 END) AS rkb_rop_po_count,
    SUM(CASE WHEN lines.po_without_rop_flag THEN 1 ELSE 0 END) AS po_without_rop_count,
    SUM(CASE WHEN lines.rop_without_po_flag THEN 1 ELSE 0 END) AS rop_without_po_count,
    SUM(lines.po_received_qty) / NULLIF(SUM(lines.po_qty), 0) AS received_ratio,
    SUM(lines.po_invoiced_qty) / NULLIF(SUM(lines.po_qty), 0) AS invoiced_ratio,
    SUM(lines.rop_qty) / NULLIF(SUM(lines.rkb_actual_qty), 0) AS rop_progress_ratio,
    SUM(lines.not_yet_rop_qty) / NULLIF(SUM(lines.rkb_actual_qty), 0) AS not_yet_rop_ratio,
    'ODOO_RKB_ACTUAL_BASELINE'::text AS comparison_basis,
    'INTERNAL_ORDER_REKAP_OPERATIONAL_SUMMARY'::text AS summary_scope
FROM vw_internal_order_rekap_lines lines
GROUP BY lines.internal_order_number;

-- Validation queries for Phase 1 review -- ============================================================================= -- 1) Count Internal Order summary rows. -- SELECT COUNT(*) FROM vw_internal_order_rekap_summary; -- -- 2) Check validation case exists. -- SELECT * FROM vw_internal_order_rekap_summary WHERE internal_order_number = '426IO026'; -- -- 3) Line detail for validation case. -- SELECT * FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' ORDER BY product_key LIMIT 50; -- -- 4) Mixed UoM count for validation case. -- SELECT COUNT(*) FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' AND mixed_uom_flag = true; -- -- 5) Product presence distribution for validation case. -- SELECT product_presence_status, COUNT(*) FROM vw_internal_order_rekap_lines WHERE internal_order_number = '426IO026' GROUP BY product_presence_status ORDER BY product_presence_status; -- -- 6) Sales Order bridge check. -- SELECT * FROM vw_internal_order_rekap_summary WHERE internal_order_number = '426IO026'; -- -- 7) Top IOs by amount. -- SELECT internal_order_number, product_count, rkb_actual_amount, rop_amount, po_amount, not_yet_rop_amount, excess_rop_amount -- FROM vw_internal_order_rekap_summary -- ORDER BY COALESCE(rkb_actual_amount, 0) DESC -- LIMIT 20;
