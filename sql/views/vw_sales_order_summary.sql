-- =============================================================================
-- Sales Order Summary View
-- =============================================================================
-- Purpose: Order-level summary for sales analytics dashboard
-- Source: sale_order, sale_order_line, res_partner
-- Usage: Revenue analysis, order pipeline, sales performance
-- =============================================================================

CREATE OR REPLACE VIEW vw_sales_order_summary AS
SELECT 
    -- Order identifiers
    o.id AS order_id,
    o.name AS order_number,
    
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
        WHEN 'draft' THEN 'Quotation Draft'
        WHEN 'sent' THEN 'Quotation Sent'
        WHEN 'sale' THEN 'Sales Order'
        WHEN 'done' THEN 'Locked'
        WHEN 'cancel' THEN 'Cancelled'
        ELSE o.state
    END AS status_name,
    
    -- Customer information
    p.id AS customer_id,
    p.name AS customer_name,
    p.email AS customer_email,
    p.phone AS customer_phone,
    p.active AS customer_active,
    
    -- Delivery and invoice status (custom fields)
    o.x_studio_delivery_status AS delivery_status,
    o.x_studio_invoice_status AS invoice_status,
    
    -- Order amounts
    COALESCE(o.amount_total, 0) AS total_amount,
    
    -- Line aggregations
    COUNT(DISTINCT l.id) AS line_count,
    COALESCE(SUM(l.product_uom_qty), 0) AS total_quantity,
    COALESCE(SUM(l.price_subtotal), 0) AS sum_line_subtotals,
    
    -- Average metrics
    CASE 
        WHEN COUNT(DISTINCT l.id) > 0 THEN 
            COALESCE(SUM(l.price_subtotal), 0) / COUNT(DISTINCT l.id)
        ELSE 0 
    END AS avg_line_value,
    
    CASE 
        WHEN COUNT(DISTINCT l.id) > 0 THEN 
            COALESCE(SUM(l.product_uom_qty), 0) / COUNT(DISTINCT l.id)
        ELSE 0 
    END AS avg_quantity_per_line,
    
    -- Timestamps
    o.create_date AS created_at,
    o.write_date AS updated_at,
    
    -- Order type categorization
    CASE 
        WHEN o.state IN ('draft', 'sent') THEN 'Quotation'
        WHEN o.state IN ('sale', 'done') THEN 'Confirmed'
        WHEN o.state = 'cancel' THEN 'Cancelled'
        ELSE 'Other'
    END AS order_category

FROM sale_order o
LEFT JOIN sale_order_line l ON l.order_id = o.id
LEFT JOIN res_partner p ON p.id = o.partner_id
GROUP BY 
    o.id,
    o.name,
    o.date_order,
    o.state,
    o.amount_total,
    o.x_studio_delivery_status,
    o.x_studio_invoice_status,
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
CREATE INDEX IF NOT EXISTS idx_vw_sales_order_summary_date 
    ON vw_sales_order_summary (order_date);

-- Index on year-month for monthly reporting
CREATE INDEX IF NOT EXISTS idx_vw_sales_order_summary_ym 
    ON vw_sales_order_summary (order_year_month);

-- Index on status for pipeline analysis
CREATE INDEX IF NOT EXISTS idx_vw_sales_order_summary_status 
    ON vw_sales_order_summary (status_code);

-- Index on customer for customer analysis
CREATE INDEX IF NOT EXISTS idx_vw_sales_order_summary_customer 
    ON vw_sales_order_summary (customer_id);

COMMENT ON VIEW vw_sales_order_summary IS 
    'Sales order summary view with customer info, date parts, and aggregations for dashboard reporting';

COMMENT ON COLUMN vw_sales_order_summary.order_id IS 'Unique order identifier from Odoo';
COMMENT ON COLUMN vw_sales_order_summary.order_number IS 'Human-readable order number (SO-00001)';
COMMENT ON COLUMN vw_sales_order_summary.order_category IS 'Order categorization: Quotation, Confirmed, Cancelled';