-- =============================================================================
-- Purchase Order Summary View
-- =============================================================================
-- Purpose: Order-level summary for purchasing analytics dashboard
-- Source: purchase_order, purchase_order_line, res_partner
-- Usage: Spend analysis, vendor performance, procurement pipeline
-- =============================================================================

CREATE OR REPLACE VIEW vw_purchase_summary AS
SELECT 
    -- Order identifiers
    o.id AS order_id,
    o.name AS order_reference,
    
    -- Order dates with full granularity
    o.date_order AS order_date,
    EXTRACT(YEAR FROM o.date_order)::INTEGER AS order_year,
    EXTRACT(QUARTER FROM o.date_order)::INTEGER AS order_quarter,
    EXTRACT(MONTH FROM o.date_order)::INTEGER AS order_month,
    EXTRACT(WEEK FROM o.date_order)::INTEGER AS order_week,
    EXTRACT(DAY FROM o.date_order)::INTEGER AS order_day,
    TO_CHAR(o.date_order, 'YYYY-MM') AS order_year_month,
    TO_CHAR(o.date_order, 'YYYY-MM-DD') AS order_date_str,
    TO_CHAR(o.date_order, 'Day') AS order_day_name,
    
    -- Status codes and human-readable names
    o.state AS status_code,
    CASE o.state
        WHEN 'draft' THEN 'Draft'
        WHEN 'sent' THEN 'RFQ Sent'
        WHEN 'purchase' THEN 'Purchase Order'
        WHEN 'done' THEN 'Done'
        WHEN 'cancel' THEN 'Cancelled'
        ELSE o.state
    END AS status_name,
    
    -- Vendor information
    p.id AS vendor_id,
    p.name AS vendor_name,
    p.email AS vendor_email,
    p.phone AS vendor_phone,
    p.active AS vendor_active,
    
    -- Order amounts
    COALESCE(o.amount_total, 0) AS total_amount,
    
    -- Line aggregations
    COUNT(DISTINCT l.id) AS line_count,
    COALESCE(SUM(l.product_qty), 0) AS total_quantity,
    COALESCE(SUM(l.price_subtotal), 0) AS sum_line_subtotals,
    
    -- Average metrics
    CASE 
        WHEN COUNT(DISTINCT l.id) > 0 THEN 
            COALESCE(SUM(l.price_subtotal), 0) / COUNT(DISTINCT l.id)
        ELSE 0 
    END AS avg_line_value,
    
    CASE 
        WHEN COUNT(DISTINCT l.id) > 0 THEN 
            COALESCE(SUM(l.product_qty), 0) / COUNT(DISTINCT l.id)
        ELSE 0 
    END AS avg_quantity_per_line,
    
    -- Timestamps
    o.create_date AS created_at,
    o.write_date AS updated_at,
    
    -- Order category
    CASE 
        WHEN o.state = 'draft' THEN 'Draft'
        WHEN o.state IN ('sent', 'purchase') THEN 'Active'
        WHEN o.state = 'done' THEN 'Completed'
        WHEN o.state = 'cancel' THEN 'Cancelled'
        ELSE 'Other'
    END AS order_category,
    
    -- Days since creation
    EXTRACT(DAY FROM (CURRENT_DATE - o.date_order))::INTEGER AS days_since_order

FROM purchase_order o
LEFT JOIN purchase_order_line l ON l.order_id = o.id
LEFT JOIN res_partner p ON p.id = o.partner_id
GROUP BY 
    o.id,
    o.name,
    o.date_order,
    o.state,
    o.amount_total,
    o.create_date,
    o.write_date,
    p.id,
    p.name,
    p.email,
    p.phone,
    p.active;

-- =============================================================================
-- Indexes for performance optimization
-- =============================================================================

-- Index on date for time-based queries
CREATE INDEX IF NOT EXISTS idx_vw_purchase_summary_date 
    ON vw_purchase_summary (order_date);

-- Index on year-month for monthly reporting
CREATE INDEX IF NOT EXISTS idx_vw_purchase_summary_ym 
    ON vw_purchase_summary (order_year_month);

-- Index on status for pipeline analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_summary_status 
    ON vw_purchase_summary (status_code);

-- Index on vendor for vendor analysis
CREATE INDEX IF NOT EXISTS idx_vw_purchase_summary_vendor 
    ON vw_purchase_summary (vendor_id);

COMMENT ON VIEW vw_purchase_summary IS 
    'Purchase order summary view with vendor info, date parts, and aggregations for dashboard reporting';

COMMENT ON COLUMN vw_purchase_summary.order_id IS 'Unique purchase order identifier from Odoo';
COMMENT ON COLUMN vw_purchase_summary.order_reference IS 'Human-readable order reference (PO-00001)';
COMMENT ON COLUMN vw_purchase_summary.days_since_order IS 'Number of days since the order was created';