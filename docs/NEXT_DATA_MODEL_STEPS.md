# Next Data Model Steps

Audit date: 2026-06-23

This document recommends the safest data-model path before building frontend dashboard pages. It does not create SQL views or change application logic.

## Recommended SQL Views to Create First

Create these only after the missing/unclear mappings are confirmed.

### 1. `vw_sales_order_revenue`

Purpose:
- Normalize SO header and line revenue into one clean sales dataset.

Source tables:
- `sale_order`
- `sale_order_line`

Core fields:
- SO ID and SO number
- customer
- order date
- product
- ordered quantity
- delivered quantity
- invoiced quantity
- line subtotal
- SO state
- delivery status
- invoice status

Key rule:
- Use `sale_order_line.order_id = sale_order.name` unless later extraction restores the original numeric FK.

### 2. `vw_mrp_order_context`

Purpose:
- Create one production order context table with SO, IO, and JO candidate keys.

Source tables:
- `mrp_production`
- optionally `sale_order`

Core fields:
- MO name
- MO product
- MO quantity
- MO state
- start and finish dates
- `origin`
- inferred SO number when `origin` matches `sale_order.name`
- IO number
- JO number

Key rule:
- Treat SO link from `origin` as inferred, not guaranteed.

### 3. `vw_stock_movement_context`

Purpose:
- Normalize stock movements for MO/SO traceability.

Source tables:
- `stock_move_line`
- `mrp_production`
- `sale_order`
- later `stock_move`, `stock_picking`, and `stock_location` when extracted

Core fields:
- movement date
- reference
- source document
- inferred MO
- inferred SO
- product
- quantity
- source location
- destination location
- movement state

Key rule:
- Do not classify raw consumption, finished goods, delivery, receipt, or internal transfer until `stock_location` and preferably `stock_move` are available.

### 4. `vw_rkb_planning_lines`

Purpose:
- Normalize RKB/PPIC planning lines.

Source tables:
- `approval_product_line`
- later `approval_request`

Core fields:
- approval request
- product
- description
- planned quantity
- unit price
- subtotal
- date of need
- IO number
- JO number
- status
- requester
- category

Key rule:
- Do not finalize RKB filtering until category = RKB is available from `approval_request` or a confirmed field.

### 5. `vw_procurement_lines`

Purpose:
- Normalize purchase order lines and connect procurement to IO/JO.

Source tables:
- `purchase_order_line`
- later `purchase_order`

Core fields:
- PO number/header
- vendor
- product
- quantity ordered
- quantity received
- quantity invoiced
- price unit
- subtotal
- state
- planned date
- IO candidate
- JO candidate

Key rule:
- Confirm `x_studio_many2one_field_ij0j0` before naming it IO in final dashboards.

### 6. `vw_accounting_sales_lines`

Purpose:
- Normalize accounting lines that relate to SO, revenue, invoice, AR, and COGS.

Source tables:
- `account_move_line`
- later `account_move`

Core fields:
- move ID
- move name
- account
- partner
- product
- date
- debit
- credit
- balance
- parent state
- SO candidate key

Key rule:
- Current evidence suggests `account_move_line.x_studio_sales_order = sale_order.id::text`, not SO name. Validate this before use.

### 7. `vw_so_traceability`

Purpose:
- Combine SO, MO, movement, RKB, procurement, and accounting relationship status.

Source views:
- `vw_sales_order_revenue`
- `vw_mrp_order_context`
- `vw_stock_movement_context`
- `vw_rkb_planning_lines`
- `vw_procurement_lines`
- `vw_accounting_sales_lines`

Core fields:
- SO number
- SO ID
- has MO
- inferred MO count
- has delivery movement
- has invoice/accounting line
- has RKB candidate
- has procurement candidate
- missing link flags

Key rule:
- This should be a traceability and data-quality view first, not a profitability view.

### 8. `vw_profitability_by_so`

Purpose:
- Calculate SO profitability only after traceability is validated.

Inputs:
- Revenue
- Estimator cost
- RKB planned cost
- procurement/actual material cost
- accounting actuals

Key rule:
- Do not create this as a final dashboard metric until estimator data, RKB category, actual cost valuation, and SO-to-IO link are solved.

### 9. `vw_profitability_by_mo`

Purpose:
- Calculate MO profitability or cost variance only after MO costing is validated.

Inputs:
- MO context
- RKB planned cost
- actual consumption quantity and value
- procurement cost
- linked SO revenue, where available

Key rule:
- MO profitability should show "unlinked revenue" or "no SO yet" for IO-created MOs.

## Safest Implementation Order

1. Freeze business keys and naming

Confirm these fields with Odoo/business users:
- SO number: `sale_order.name`
- SO numeric ID: `sale_order.id`
- MO number: `mrp_production.name`
- IO number: `x_studio_nomor_io`
- JO number: `x_studio_nomor_jo`
- Purchase IO field: `purchase_order_line.x_studio_many2one_field_ij0j0`
- Accounting SO field: `account_move_line.x_studio_sales_order`

2. Fix missing extraction coverage

Extract or repair these before final profitability:
- `account_move`
- `stock_picking`
- `stock_move`
- `stock_location`
- `approval_request`
- `purchase_order`
- Internal Order master table, if one exists
- Product master rows for `product_product` and `product_template`

3. Validate row match rates

Before creating dashboard metrics, measure:
- SO lines matching SO headers
- MOs matching SOs by origin
- MOs with IO
- MOs with JO
- RKB lines matching IO/JO
- PO lines matching IO/JO
- Stock movements matching MO/SO
- Accounting lines matching SO ID

4. Create traceability views first

Build views that show what is linked and what is missing. Avoid profit calculations until traceability is visible and trusted.

5. Load estimator data

Create a controlled import for estimator Excel data with clear keys:
- SO number, if estimator is SO-based
- IO number, if estimator starts before SO
- MO number or JO number, if estimator is production-based
- product/material lines
- estimated quantity
- estimated unit cost
- estimated subtotal

6. Add cost views

Only after estimator, RKB category, stock valuation, and movement classification are available:
- planned cost by IO/MO/SO
- actual material cost by MO/SO
- variance by material/product

7. Build frontend pages

Start with data-confidence pages before executive profitability pages.

## Dashboard Page to Build First

Build a "Manufacturing Traceability Audit" page first.

Why:
- It exposes whether SO, IO, MO, RKB, stock movement, invoice, and AR links are present.
- It prevents misleading profitability numbers.
- It directly answers the biggest risk in the data model: whether Flow A and Flow B can be followed reliably.

Suggested first-page sections:
- SO list with link status: has MO, has movement, has accounting, has RKB candidate, has IO candidate.
- MO list with origin type: SO-origin, IO-origin, unknown origin.
- Missing link counters.
- Sample unmatched records for each relationship.

Second page:
- Sales Order profitability prototype, clearly labeled as prototype and limited to revenue + RKB/procurement/accounting where links are validated.

Third page:
- MO cost variance prototype, using RKB planned quantity/cost vs actual movement quantity first.

## Risks Before Building Frontend

### Business correctness risks

- IO to later SO is not currently available.
- SO-created MO vs existing-stock delivery can only be inferred weakly.
- RKB category = RKB cannot be applied because approval category/header is missing.
- Estimator cost is outside Odoo and not yet imported.

### Data completeness risks

- Product master tables exist but have zero rows.
- Delivery Order header table is missing.
- Invoice header table is missing.
- Stock location master is missing.
- Stock move table is missing.
- Purchase Order header table is missing.

### Profitability risks

- Revenue is available, but actual cost is incomplete.
- Stock movement quantity exists, but movement value/unit cost is missing.
- Accounting lines exist, but invoice context and payment context are incomplete.
- MO profitability can be misleading if IO-created MOs are later sold through SO without an explicit IO-to-SO link.

### Technical risks

- Some extracted many2one fields now contain display names while others still contain numeric IDs.
- Several relationships depend on custom Odoo fields with unclear names.
- Join counts can multiply when IO/JO is repeated, so relationship checks must use distinct business keys and grain-aware aggregation.

## Recommended Next Action

Before any frontend dashboard work, add the missing extraction models/tables for:
1. `approval_request`
2. `stock_picking`
3. `stock_move`
4. `stock_location`
5. `account_move`
6. `purchase_order`
7. Internal Order master table or confirmed IO source model
8. product master population for `product_product` and `product_template`

After that, create traceability SQL views and validate match rates with the business team. Profitability views should come after traceability is confirmed.

