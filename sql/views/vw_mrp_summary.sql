-- =============================================================================
-- Manufacturing Summary View
-- =============================================================================
-- Purpose: Manufacturing order summary for production analytics
-- Source: mrp_production, product_product, product_template
-- Usage: Production planning, capacity analysis, manufacturing efficiency
-- =============================================================================

CREATE OR REPLACE VIEW vw_mrp_summary AS
SELECT 
    -- Production order identifiers
    m.id AS production_id,
    m.name AS production_reference,
    
    -- Start and finish dates with full granularity
    m.date_start AS planned_start_date,
    m.date_finished AS finished_date,
    EXTRACT(YEAR FROM m.date_start)::INTEGER AS planned_year,
    EXTRACT(QUARTER FROM m.date_start)::INTEGER AS planned_quarter,
    EXTRACT(MONTH FROM m.date_start)::INTEGER AS planned_month,
    EXTRACT(WEEK FROM m.date_start)::INTEGER AS planned_week,
    TO_CHAR(m.date_start, 'YYYY-MM') AS planned_year_month,
    
    -- Status codes and human-readable names
    m.state AS status_code,
    CASE m.state
        WHEN 'draft' THEN 'Draft'
        WHEN 'confirmed' THEN 'Confirmed'
        WHEN 'progress' THEN 'In Progress'
        WHEN 'done' THEN 'Done'
        WHEN 'cancel' THEN 'Cancelled'
        ELSE m.state
    END AS status_name,
    
    -- Product information
    pr.id AS product_id,
    pr.name AS product_name,
    pr.default_code AS product_code,
    pr.barcode AS product_barcode,
    pr.active AS product_active,
    COALESCE(pr.list_price, 0) AS product_list_price,
    COALESCE(pr.standard_price, 0) AS product_standard_cost,
    
    -- Product type (from template)
    pt.type AS product_type,
    CASE pt.type
        WHEN 'consu' THEN 'Consumable'
        WHEN 'service' THEN 'Service'
        WHEN 'product' THEN 'Storable Product'
        ELSE pt.type
    END AS product_type_name,
    
    -- Production quantities
    COALESCE(m.product_qty, 0) AS quantity_to_produce,
    
    -- Product value
    COALESCE(m.product_qty, 0) * COALESCE(pr.standard_price, 0) AS total_production_value,
    
    -- Duration calculation (in hours)
    CASE 
        WHEN m.date_start IS NOT NULL AND m.date_finished IS NOT NULL THEN 
            EXTRACT(EPOCH FROM (m.date_finished - m.date_start)) / 3600
        ELSE NULL
    END AS production_duration_hours,
    
    -- Cycle time per unit (hours)
    CASE 
        WHEN m.date_start IS NOT NULL AND m.date_finished IS NOT NULL 
             AND COALESCE(m.product_qty, 0) > 0 THEN 
            (EXTRACT(EPOCH FROM (m.date_finished - m.date_start)) / 3600) / m.product_qty
        ELSE NULL
    END AS cycle_time_hours_per_unit,
    
    -- Timestamps
    m.create_date AS created_at,
    m.write_date AS updated_at,
    
    -- Production category
    CASE 
        WHEN m.state = 'draft' THEN 'Planned'
        WHEN m.state IN ('confirmed', 'progress') THEN 'Active'
        WHEN m.state = 'done' THEN 'Completed'
        WHEN m.state = 'cancel' THEN 'Cancelled'
        ELSE 'Other'
    END AS production_category,
    
    -- Days since creation
    CASE 
        WHEN m.date_start IS NOT NULL THEN 
            EXTRACT(DAY FROM (CURRENT_DATE - m.date_start))::INTEGER
        ELSE NULL
    END AS days_since_planned_start,
    
    -- Is overdue?
    CASE 
        WHEN m.date_start IS NOT NULL 
             AND m.state IN ('draft', 'confirmed', 'progress')
             AND m.date_start < CURRENT_TIMESTAMP THEN 
            true
        ELSE false
    END AS is_overdue,
    
    -- Is on time? (finished before or on planned date)
    CASE 
        WHEN m.date_finished IS NOT NULL AND m.date_start IS NOT NULL THEN 
            m.date_finished <= m.date_start
        ELSE NULL
    END AS finished_on_time

FROM mrp_production m
LEFT JOIN product_product pr ON pr.id = m.product_id
LEFT JOIN product_template pt ON pt.id = pr.product_tmpl_id;

-- =============================================================================
-- Indexes for performance optimization
-- =============================================================================

-- Index on planned date for scheduling
CREATE INDEX IF NOT EXISTS idx_vw_mrp_summary_date 
    ON vw_mrp_summary (planned_start_date);

-- Index on year-month for monthly reporting
CREATE INDEX IF NOT EXISTS idx_vw_mrp_summary_ym 
    ON vw_mrp_summary (planned_year_month);

-- Index on status for pipeline analysis
CREATE INDEX IF NOT EXISTS idx_vw_mrp_summary_status 
    ON vw_mrp_summary (status_code);

-- Index on product for product analysis
CREATE INDEX IF NOT EXISTS idx_vw_mrp_summary_product 
    ON vw_mrp_summary (product_id);

-- Index for overdue production orders
CREATE INDEX IF NOT EXISTS idx_vw_mrp_summary_overdue 
    ON vw_mrp_summary (is_overdue) WHERE is_overdue = true;

COMMENT ON VIEW vw_mrp_summary IS 
    'Manufacturing order summary view with product info, date parts, and efficiency metrics';

COMMENT ON COLUMN vw_mrp_summary.production_id IS 'Unique manufacturing order identifier from Odoo';
COMMENT ON COLUMN vw_mrp_summary.production_reference IS 'Human-readable MO reference (MO/00001)';
COMMENT ON COLUMN vw_mrp_summary.production_duration_hours IS 'Total time from start to finish in hours';
COMMENT ON COLUMN vw_mrp_summary.cycle_time_hours_per_unit IS 'Average hours per unit produced';