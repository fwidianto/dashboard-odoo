-- =============================================================================
-- Inventory Summary View
-- =============================================================================
-- Purpose: Current inventory levels and stock movement summary
-- Source: stock_quant, stock_move, product_product, product_template
-- Usage: Inventory monitoring, stock analysis, reorder planning
-- =============================================================================

-- Part 1: Current Inventory Levels (from stock_quant)
CREATE OR REPLACE VIEW vw_inventory_summary AS
WITH current_inventory AS (
    SELECT 
        sq.product_id,
        sq.location_id,
        COALESCE(SUM(sq.quantity), 0) AS on_hand_quantity,
        COALESCE(SUM(sq.reserved_quantity), 0) AS reserved_quantity
    FROM stock_quant sq
    GROUP BY sq.product_id, sq.location_id
),
inventory_values AS (
    SELECT 
        ci.product_id,
        ci.location_id,
        ci.on_hand_quantity,
        ci.reserved_quantity,
        ci.on_hand_quantity - ci.reserved_quantity AS available_quantity,
        COALESCE(pr.standard_price, 0) AS unit_cost,
        (ci.on_hand_quantity - ci.reserved_quantity) * COALESCE(pr.standard_price, 0) AS available_value,
        ci.on_hand_quantity * COALESCE(pr.standard_price, 0) AS on_hand_value
    FROM current_inventory ci
    LEFT JOIN product_product pr ON pr.id = ci.product_id
)
SELECT 
    -- Product identifiers
    pr.id AS product_id,
    pr.name AS product_name,
    pr.default_code AS product_code,
    pr.barcode AS product_barcode,
    pr.active AS product_active,
    
    -- Product type (from template)
    pt.type AS product_type,
    CASE pt.type
        WHEN 'consu' THEN 'Consumable'
        WHEN 'service' THEN 'Service'
        WHEN 'product' THEN 'Storable Product'
        ELSE pt.type
    END AS product_type_name,
    
    -- Product pricing
    COALESCE(pr.list_price, 0) AS list_price,
    COALESCE(pr.standard_price, 0) AS standard_cost,
    
    -- Location
    iv.location_id,
    'Location' || iv.location_id::TEXT AS location_name,
    
    -- Inventory quantities
    iv.on_hand_quantity,
    iv.reserved_quantity,
    iv.available_quantity,
    
    -- Inventory values
    iv.unit_cost,
    iv.available_value,
    iv.on_hand_value,
    
    -- Stock status classification
    CASE 
        WHEN iv.available_quantity <= 0 THEN 'Out of Stock'
        WHEN iv.available_quantity < 10 THEN 'Low Stock'
        WHEN iv.available_quantity < 50 THEN 'Normal Stock'
        ELSE 'High Stock'
    END AS stock_status,
    
    -- Turnover indicator (days of stock - simplified)
    CASE 
        WHEN COALESCE(pr.standard_price, 0) > 0 THEN 
            ROUND(iv.available_quantity / NULLIF(
                (SELECT COALESCE(SUM(ABS(product_uom_qty)), 0) / 30 
                 FROM stock_move 
                 WHERE product_id = pr.id 
                   AND state = 'done'
                   AND date >= CURRENT_DATE - INTERVAL '30 days'
                ), 0), 2)
        ELSE NULL
    END AS estimated_days_of_stock

FROM inventory_values iv
INNER JOIN product_product pr ON pr.id = iv.product_id
LEFT JOIN product_template pt ON pt.id = pr.product_tmpl_id
WHERE pr.active = true;

-- =============================================================================
-- Indexes for performance optimization
-- =============================================================================

-- Index on product for product analysis
CREATE INDEX IF NOT EXISTS idx_vw_inventory_summary_product 
    ON vw_inventory_summary (product_id);

-- Index on product type
CREATE INDEX IF NOT EXISTS idx_vw_inventory_summary_type 
    ON vw_inventory_summary (product_type);

-- Index on stock status for alerts
CREATE INDEX IF NOT EXISTS idx_vw_inventory_summary_status 
    ON vw_inventory_summary (stock_status);

-- Index on location
CREATE INDEX IF NOT EXISTS idx_vw_inventory_summary_location 
    ON vw_inventory_summary (location_id);

-- Partial index for low/out of stock items
CREATE INDEX IF NOT EXISTS idx_vw_inventory_summary_low_stock 
    ON vw_inventory_summary (product_id, available_quantity) 
    WHERE stock_status IN ('Low Stock', 'Out of Stock');

COMMENT ON VIEW vw_inventory_summary IS 
    'Current inventory levels by product and location with value calculations';

COMMENT ON COLUMN vw_inventory_summary.on_hand_quantity IS 
    'Total quantity on hand including reserved';
COMMENT ON COLUMN vw_inventory_summary.reserved_quantity IS 
    'Quantity reserved for outbound moves';
COMMENT ON COLUMN vw_inventory_summary.available_quantity IS 
    'Quantity available for new orders (on_hand - reserved)';
COMMENT ON COLUMN vw_inventory_summary.stock_status IS 
    'Stock level classification: Out of Stock, Low Stock, Normal Stock, High Stock';
COMMENT ON COLUMN vw_inventory_summary.estimated_days_of_stock IS 
    'Estimated days until stock runs out based on last 30 days consumption';

-- =============================================================================
-- Additional View: Inventory Movement Summary (by product over time)
-- =============================================================================

CREATE OR REPLACE VIEW vw_inventory_movements AS
SELECT 
    -- Product info
    pr.id AS product_id,
    pr.name AS product_name,
    pr.default_code AS product_code,
    
    -- Date info
    DATE(sm.date) AS move_date,
    EXTRACT(YEAR FROM sm.date)::INTEGER AS move_year,
    EXTRACT(MONTH FROM sm.date)::INTEGER AS move_month,
    TO_CHAR(sm.date, 'YYYY-MM') AS move_year_month,
    
    -- Move types
    sm.state AS move_status,
    CASE 
        WHEN sm.location_dest_id != sm.location_id THEN 'Transfer'
        ELSE 'Adjustment'
    END AS move_type,
    
    -- Quantities (signed: positive for incoming, negative for outgoing)
    CASE 
        WHEN sm.location_dest_id != sm.location_id AND sm.product_uom_qty > 0 THEN sm.product_uom_qty
        ELSE 0
    END AS quantity_in,
    CASE 
        WHEN sm.location_dest_id = sm.location_id AND sm.product_uom_qty > 0 THEN sm.product_uom_qty
        ELSE 0
    END AS quantity_out,
    sm.product_uom_qty AS absolute_quantity,
    
    -- Timestamps
    sm.create_date AS created_at

FROM stock_move sm
INNER JOIN product_product pr ON pr.id = sm.product_id
WHERE sm.state = 'done';

-- Indexes for movement analysis
CREATE INDEX IF NOT EXISTS idx_vw_inventory_movements_product 
    ON vw_inventory_movements (product_id);

CREATE INDEX IF NOT EXISTS idx_vw_inventory_movements_date 
    ON vw_inventory_movements (move_date);

CREATE INDEX IF NOT EXISTS idx_vw_inventory_movements_ym 
    ON vw_inventory_movements (move_year_month);

COMMENT ON VIEW vw_inventory_movements IS 
    'Stock movements by product and date for inventory trend analysis';