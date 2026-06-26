# Manufacturing Profitability Flow Implementation Gap

Audit date: 2026-06-23

This gap analysis uses `docs/BUSINESS_FLOW.md` as the available business source of truth. The requested files `docs/BUSINESS_RULES.md`, `docs/KPI_DEFINITIONS.md`, `docs/TABLE_MAPPING.md`, and `docs/DASHBOARD_REQUIREMENTS.md` were not found.

## Executive Answer

The current extracted tables are enough for a first traceability prototype, but not enough for a business-correct manufacturing profitability dashboard.

The strongest current paths are:
- SO header/line: `sale_order` + `sale_order_line`
- SO to MO: `sale_order.name` -> `mrp_production.origin`
- MO to stock movements: `mrp_production.name` -> `stock_move_line.reference`
- RKB/PPIC candidate lines: `approval_product_line`
- Procurement candidate lines: `purchase_order_line`
- Accounting candidate lines: `account_move_line.x_studio_sales_order` -> `sale_order.id::text`

The biggest gaps are:
- No Internal Order master table.
- No explicit IO to later SO link.
- No `account_move` invoice header.
- No `stock_picking` Delivery Order header.
- No `stock_move` stock move bridge.
- No `stock_location` master.
- Product master tables exist but are empty.
- No reliable approval category table/field to filter category = RKB.
- Estimator cost is outside Odoo and not loaded.
- Actual material cost value is not available from extracted stock movement lines alone.

## Question-by-Question Gap

### Can we implement SO -> MO -> DO -> Invoice -> AR?

Answer: partially, not completely.

What is possible now:
- SO can be represented from `sale_order`.
- SO lines can be represented from `sale_order_line`.
- MO can often be linked by `mrp_production.origin = sale_order.name`.
- Stock movement quantities can often be linked by `stock_move_line.reference = mrp_production.name` or `stock_move_line.x_studio_source_document = sale_order.name`.
- Accounting lines may be linked by `account_move_line.x_studio_sales_order = sale_order.id::text`.

What is missing:
- DO header is missing because `stock_picking` is not extracted.
- Stock move bridge is missing because `stock_move` is not extracted.
- Invoice header is missing because `account_move` is not extracted.
- AR aging/payment status is weak because invoice headers, due dates, payment state, and reconciliation are missing.

Conclusion: implementable only as a weak trace view. Not ready for reliable operational dashboard or financial AR dashboard.

### Can we implement IO -> MO -> SO -> DO -> Invoice -> AR?

Answer: no, not end to end.

What is possible now:
- IO-like values exist on `mrp_production.x_studio_nomor_io`.
- IO-like values exist on `approval_product_line.x_studio_nomor_io`.
- IO-like values appear in `purchase_order_line.x_studio_many2one_field_ij0j0`.

What is missing:
- No Internal Order master table.
- No direct IO field was found on `sale_order` or `sale_order_line`.
- No confirmed custom IO-to-SO link.
- DO, invoice header, and AR gaps are the same as Flow A.

Conclusion: IO -> MO can be partially shown. IO -> later SO is unclear and cannot be implemented correctly from current extracted fields.

### Can we identify whether SO created MO or used existing stock?

Answer: only by weak inference.

Possible inference:
- If `sale_order.name` matches `mrp_production.origin`, the SO likely triggered or is linked to an MO.
- If no MO origin exists but delivery movement exists in `stock_move_line`, the SO may have used available stock.

Why this is weak:
- `mrp_production.origin` is not guaranteed to be only SO.
- `stock_picking`, `stock_move`, procurement group, route, and stock rule data are missing.
- No explicit business field was found to mark SO as make-to-order vs make-to-stock.

Conclusion: not reliable enough for final dashboard logic.

### Can we link SO to MO?

Answer: partially yes.

Candidate link:
- `sale_order.name` -> `mrp_production.origin`

Evidence:
- 9,029 matching MO rows were found.

Limits:
- `origin` can contain non-SO values, including MO-like and IO-like values.
- Some SOs may not have MOs because they use existing stock.
- Some MOs may be created from IO before SO exists.

Conclusion: usable for a first SO-to-MO trace view with clear "source inferred from origin" labeling.

### Can we link IO to MO?

Answer: partially yes.

Candidate link:
- `mrp_production.x_studio_nomor_io`

Evidence:
- 1,260 MOs have non-null `x_studio_nomor_io`.

Limits:
- No IO master table exists.
- Need confirm IO number format and whether null means non-IO or missing data.

Conclusion: usable for IO-to-MO trace where `x_studio_nomor_io` exists.

### Can we link IO to later SO?

Answer: no.

Reason:
- No direct IO field was found on `sale_order` or `sale_order_line`.
- No IO master table was found with a later SO reference.
- No reliable bridge table was found.

Conclusion: this is a critical missing relationship for Flow B.

### Can we identify RKB per SO/MO/IO?

Answer: partially for MO/IO, unclear for SO.

Possible links:
- RKB candidate to IO: `approval_product_line.x_studio_nomor_io`
- RKB candidate to MO/JO: `approval_product_line.x_studio_nomor_jo` and `mrp_production.x_studio_nomor_jo`

Unclear:
- The required category = RKB field is not available because `approval_request` is missing and `approval_product_line` has no category column.
- SO-level RKB requires SO -> MO or SO -> IO. SO -> MO is partial; SO -> IO is missing.

Conclusion: RKB can be analyzed as candidate planning lines by IO/JO only after category filtering is fixed.

### Can we compare Estimator vs RKB?

Answer: no, not with current database only.

Reason:
- Estimator cost is expected to exist outside Odoo, usually Excel.
- No estimator table was found in the extracted database.
- RKB lines exist as candidates, but category = RKB cannot be confirmed from current extracted fields.

Conclusion: need import/load estimator data and extract approval category/header before this comparison is business-correct.

### Can we compare RKB vs actual material consumption?

Answer: partially for quantity, no for cost value.

What is possible:
- RKB candidate planned quantity/cost exists in `approval_product_line`.
- Actual movement quantities exist in `stock_move_line`.
- MO movements can be linked by `stock_move_line.reference = mrp_production.name`.

What is missing:
- `stock_move` is missing.
- `stock_location` is missing, so raw material consumption vs finished goods movement is hard to classify.
- Stock valuation/unit cost fields are missing.
- Product master tables are empty.

Conclusion: quantity comparison may be prototyped after movement classification is solved. Cost comparison is not reliable yet.

### Can we calculate profitability by SO?

Answer: partially for a prototype, not business-correct final profitability.

Available:
- Revenue from `sale_order_line.price_subtotal` or `sale_order.amount_untaxed`.
- Accounting line totals from `account_move_line` if `x_studio_sales_order` is validated as SO ID.
- RKB candidate cost can be bridged through SO -> MO -> IO/JO for some records.

Missing:
- Estimator cost table/import.
- Reliable actual material cost.
- Invoice header and AR status.
- Product master and location master.
- IO-to-later-SO link for make-to-stock/Internal Order flow.

Conclusion: SO profitability can be prototyped with large caveats, but final profitability is not ready.

### Can we calculate profitability by MO?

Answer: partially.

Available:
- MO header and product quantity from `mrp_production`.
- Candidate RKB cost by IO/JO from `approval_product_line`.
- Candidate procurement cost by IO/JO from `purchase_order_line`.
- Actual movement quantity by `stock_move_line.reference`.

Missing:
- Actual material valuation.
- Stock move and location classification.
- Work order/labor/overhead costing, if required.
- Finished goods valuation and WIP accounting.

Conclusion: MO cost planning and movement quantity dashboards are possible. MO profitability in financial value is not complete.

## Missing Tables or Fields

Highest priority missing tables:
- `account_move`
- `stock_picking`
- `stock_move`
- `stock_location`
- `approval_request`
- `purchase_order`
- Internal Order master table, if it exists in Odoo

Highest priority missing fields or mappings:
- SO field that references IO, if it exists.
- IO master key, IO status, IO date, IO owner/requester, and IO later SO reference.
- Approval request category field to identify category = RKB.
- Product master population for `product_product` and `product_template`.
- Stock valuation or unit cost fields for actual material consumption.
- Invoice/payment reconciliation fields for AR.
- Confirmed mapping for `purchase_order_line.x_studio_many2one_field_ij0j0`.
- Confirmed mapping for `mrp_production.x_studio_nomor_jo`.

## Current Implementability Matrix

| Capability | Status | Reason |
| --- | --- | --- |
| SO revenue | Partial / good | Sales headers and lines exist. |
| SO delivery status | Partial | `sale_order.delivery_status` exists, but DO header missing. |
| SO invoice status | Partial | `sale_order.invoice_status` exists, but invoice header missing. |
| SO -> MO | Partial / usable | `mrp_production.origin` often matches SO number. |
| IO -> MO | Partial / usable when IO exists | MO has `x_studio_nomor_io`; no IO master. |
| IO -> SO | Not ready | No direct extracted link found. |
| MO -> actual movement quantity | Partial / usable | `stock_move_line.reference` often matches MO name. |
| RKB planning | Partial | `approval_product_line` exists, but category = RKB cannot be confirmed. |
| Estimator vs RKB | Not ready | Estimator source not loaded; RKB category missing. |
| RKB vs actual quantity | Partial | Possible after movement classification. |
| RKB vs actual cost | Not ready | Actual valuation missing. |
| SO profitability | Prototype only | Revenue exists, costs incomplete. |
| MO profitability | Prototype only | Planning and movement exist, actual cost incomplete. |
| AR | Not ready | Missing invoice header/payment reconciliation. |

