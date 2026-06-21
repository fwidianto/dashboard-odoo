-- =============================================================================
-- Purchase Order Lines View
-- =============================================================================
-- Purpose: Line-level detail for product procurement analysis
-- Source: purchase_order, purchase_order_line, res_partner, product_product, product_template
-- Usage: Product cost analysis, vendor pricing, purchase detail
-- =============================================================================

CREATE OR REPLACE VIEW vw_purchase_order_lines AS
SELECT 
    -- Order header info
    o.id AS order_id,
    o.name AS order_reference,
    o.date_order AS order_date,
    EXTRACT(YEAR FROM o.date_order)::INTEGER AS order_year,
    EXTRACT(MONTH FROM o.date_order)::INTEGER AS order_month,
    TO_CHAR(o.date_order, 'YYYY-MM') AS order_year_month,
    
    -- Order status
    o.state AS order_status_code,
    CASE o.state
        WHEN 'draft' THEN 'Draft'
        WHEN 'sent' THEN 'RFQ Sent'
        WHEN 'purchase' THEN 'Purchase Order'
        WHEN 'done' THEN 'Done'
        WHEN 'cancel' THEN 'Cancelled'
        ELSE o.state
    END AS order_status_name,
    
    -- Line identifiers
    l.id AS line_id,
    l.name AS line_description,
    
    -- Quantity and pricing
    COALESCE(l.product_qty, 0) AS quantity_ordered,
    COALESCE(l.price_unit, 0) AS unit_price,
    COALESCE(l.price_subtotal, 0) AS line_subtotal,
    
    -- Line value as percentage of order
    CASE 
        WHEN o.amount_total > 0 THEN 
            ROUND((COALESCE(l.price_subtotal, 0) / o.amount_total) * 100, 2)
        ELSE 0 
    END AS line_percentage_of_order,
    
    -- Product information
    pr.id AS product_id,
    pr.name AS product_name,
    pr.default_code AS product_code,
    pr.barcode AS product_barcode,
    pr.active AS product_active,
    COALESCE(pr.list_price, 0) AS product_sale_price,
    COALESCE(pr.standard_price, 0) AS product_cost_price,
    
    -- Product type (from template)
    pt.type AS product_type,
    CASE pt.type
        WHEN 'consu' THEN 'Consumable'
        WHEN 'service' THEN 'Service'
        WHEN 'product' THEN 'Storable Product'
        ELSE pt.type
    END AS product_type_name,
    
    -- Product category
    pt.categ_id AS category_id,
    
    -- Price variance (purchase price vs standard cost)
    CASE 
        WHEN COALESCE(pr.standard_price, 0) > 0 THEN 
            ROUND(((COALESCE(l.price_unit, 0) - COALESCE(pr.standard_price, 0)) / COALESCE(pr.standard_price, 0)) * 100, 2)
        ELSE 0
    END AS price_variance_percentage,
    
    COALESCE(l.price_unit, 0) - COALESCE(pr.standard_price, 0) AS price_variance_amount,
    
    -- Vendor information
    p.id AS vendor_id,
    p.name AS vendor_name,
    p.email AS vendor_email,
    
    -- Markup calculation (what we pay vendor vs what we sell for)
    CASE 
        WHEN COALESCE(l.product_qty, 0) * COALESCE(pr.list_price, 0) > 0 THEN 
            ROUND(((COALESCE(l.product_qty, 0) * COALESCE(pr.list_price, 0) - COALESCE(l.price_subtotal, 0)) / 
                  (COALESCE(l.product_qty, 0) * COALESCE(pr.list_price, 0))) * 100, 2)
        ELSE 0
    END AS expected_margin_percentage,
    
    -- Timestamps
    l.create_date AS line_created_at,
    o.create_date AS order_created_at

FROM purchase_order o
INNER JOIN purchase_order_line l ON l.order_id = o.id
LEFT JOIN res_partner p ON p.id = o.partner_id
LEFT JOIN product_product pr ON pr.id = l.product_id
LEFT JOIN product_template pt ON pt.id = pr.product_tmpl_id;

-- =============================================================================
-- Indexes for performance optimization
-- =============================================================================

-- Index on product for product cost analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_order_lines_product 
    ON vw_purchase_order_lines (product_id);

-- Index on order date for time analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_order_lines_date 
    ON vw_purchase_order_lines (order_date);

-- Index on year-month for monthly reporting
CREATE INDEX IF NOT EXISTS idx_vw_purchase_order_lines_ym 
    ON vw_purchase_order_lines (order_year_month);

-- Index on vendor for vendor analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_order_lines_vendor 
    ON vw_purchase_order_lines (vendor_id);

-- Index on product type for type analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_order_lines_type 
    ON vw_purchase_order_lines (product_type);

COMMENT ON VIEW vw_purchase_order_lines IS 
    'Purchase order line detail view with product and vendor info for analytics';

COMMENT ON COLUMN vw_purchase_order_lines.price_variance_percentage IS 
    'Percentage difference between purchase price and standard cost (positive = more expensive)';
COMMENT ON COLUMN vw_purchase_order_lines.expected_margin_percentage IS 
    'Expected margin if product is sold at list price';