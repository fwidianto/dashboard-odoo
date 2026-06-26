# Odoo Extracted Table Audit

Audit date: 2026-06-23

## Documentation Inputs

Read before audit:
- `docs/BUSINESS_FLOW.md`: exists and used as the business source of truth.

Requested but not found:
- `docs/BUSINESS_RULES.md`
- `docs/KPI_DEFINITIONS.md`
- `docs/TABLE_MAPPING.md`
- `docs/DASHBOARD_REQUIREMENTS.md`

The conclusions below use `docs/BUSINESS_FLOW.md` and the current PostgreSQL database structure. Missing or weak relationships are marked as unclear.

## Relationship Check Summary

Observed join counts from the current extracted database:

| Relationship check | Matching rows | Interpretation |
| --- | ---: | --- |
| `sale_order_line.order_id = sale_order.name` | 12,244 | Strong candidate for SO line to SO header. Almost all 12,247 SO lines match. |
| `mrp_production.origin = sale_order.name` | 9,029 | Strong candidate for SO-triggered MO, but not all MOs come from SO. |
| `mrp_production.x_studio_nomor_io IS NOT NULL` | 1,260 | IO exists as an MO field, but no IO master table was found. |
| `mrp_production.x_studio_nomor_jo IS NOT NULL` | 8,273 | JO is widely present on MO. Business meaning needs confirmation. |
| `stock_move_line.reference = mrp_production.name` | 114,007 | Strong candidate for MO-related stock movements. |
| `stock_move_line.x_studio_source_document = sale_order.name` | 22,220 | Candidate for SO-related delivery/movement trace. Needs picking context. |
| `account_move_line.x_studio_sales_order = sale_order.id::text` | 31,152 | Stronger than SO name for accounting-to-SO link. Needs field validation. |
| `account_move_line.x_studio_sales_order = sale_order.name` | 3 | SO name is not the likely accounting key. |

Join counts involving IO and JO can multiply because IO/JO values are repeated across multiple rows. They indicate possible keys, not confirmed one-to-one relationships.

## Sales / Revenue

### `sale_order`

| Item | Detail |
| --- | --- |
| Row count | 1,201 |
| Important columns | `id`, `name`, `date_order`, `commitment_date`, `partner_id`, `amount_untaxed`, `state`, `delivery_status`, `invoice_status`, `currency_id`, `currency_rate`, `company_id`, `x_studio_sales_name`, `x_studio_product_type`, `x_studio_prodcut_type`, `x_studio_delivery_time`, `x_studio_tanggal_po_cust` |
| Business meaning | Sales Order header. Represents customer demand, sales status, delivery status, invoice status, customer, currency, and untaxed amount. |
| Possible relationships | `sale_order.name` appears to match `sale_order_line.order_id`, `mrp_production.origin`, and `stock_move_line.x_studio_source_document`. `sale_order.id::text` appears to match `account_move_line.x_studio_sales_order`. |
| Business layer | Sales / Revenue |
| Dashboard usefulness | Useful for SO list, revenue status, delivery status, invoice status, customer slicing, and SO-level profitability header. |
| Missing or unclear fields | No explicit Internal Order link found. No explicit MO link field. No invoice header relationship except possible accounting custom field. Product type has two similarly named fields: `x_studio_product_type` and `x_studio_prodcut_type`; meaning should be cleaned or confirmed. |

Enough for dashboard use: partially yes. Good for SO header and status. Not enough alone for end-to-end profitability.

### `sale_order_line`

| Item | Detail |
| --- | --- |
| Row count | 12,247 |
| Important columns | `id`, `order_id`, `order_partner_id`, `product_id`, `product_uom_qty`, `qty_delivered`, `qty_invoiced`, `price_unit`, `price_subtotal`, `currency_id`, `x_studio_currency_rate`, `company_id`, `name` |
| Business meaning | Sales Order line detail. Represents ordered product, quantity, delivered quantity, invoiced quantity, unit price, and line subtotal. |
| Possible relationships | `order_id` strongly appears to be SO display number and matches `sale_order.name` for 12,244 rows. `product_id` is currently extracted as display text for many rows. |
| Business layer | Sales / Revenue |
| Dashboard usefulness | Useful for line-level revenue, order quantity, delivered quantity, invoiced quantity, and product-level analysis. |
| Missing or unclear fields | No explicit IO field. No explicit MO link. If `order_id` is display name, the original numeric Odoo FK is not available. Product master tables are empty, so product enrichment is weak. |

Enough for dashboard use: yes for basic sales line revenue; partial for manufacturing profitability.

### `account_move`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Invoice, bill, credit note, and journal entry header in Odoo. Needed for invoice date, move type, state, payment state, due date, and invoice-level partner/currency context. |
| Possible relationships | Would normally link to `account_move_line.move_id`. |
| Business layer | Sales / Revenue / AR |
| Dashboard usefulness | Required for reliable Invoice and AR flow. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no. Invoice and AR reporting will be incomplete without this table.

### `account_move_line`

| Item | Detail |
| --- | --- |
| Row count | 420,034 |
| Important columns | `id`, `move_id`, `move_name`, `account_id`, `partner_id`, `product_id`, `product_category_id`, `quantity`, `debit`, `credit`, `balance`, `date_x`, `parent_state`, `x_studio_sales_order`, `company_id` |
| Business meaning | Accounting journal line detail. Can contain invoice lines, receivable lines, revenue lines, expense/COGS lines, and other accounting entries. |
| Possible relationships | `move_id` should link to missing `account_move`. `x_studio_sales_order` matches `sale_order.id::text` much more strongly than `sale_order.name`. Product/category fields can support accounting analysis if display values are reliable. |
| Business layer | Sales / Revenue / AR / Actual accounting |
| Dashboard usefulness | Useful for accounting totals and possible SO-level revenue/AR if `x_studio_sales_order` is validated. |
| Missing or unclear fields | Missing `account_move` header prevents reliable invoice type, invoice status, payment state, due dates, and AR aging. Need validate whether `x_studio_sales_order` is the SO numeric ID. |

Enough for dashboard use: partial. Useful as accounting detail, not enough for clean invoice/AR flow alone.

### `account_payment`

| Item | Detail |
| --- | --- |
| Row count | 7,689 |
| Important columns | `id`, `name`, `number`, `date_x`, `partner_id`, `state`, `memo`, `journal_id`, `amount_company_currency_signed`, `company_id` |
| Business meaning | Payment records. Can support cash collection analysis. |
| Possible relationships | No reliable extracted link to SO or invoice was found. Likely relates to invoices through Odoo reconciliation tables or `account_move`, which are not extracted. |
| Business layer | AR / Cash collection |
| Dashboard usefulness | Useful for payment totals by partner/date, but weak for SO-level AR. |
| Missing or unclear fields | Missing invoice/payment reconciliation relationship. Missing `account_move` header. |

Enough for dashboard use: partial for payment summary; no for SO-level AR.

## Internal Order

### Internal Order table

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Internal demand that can trigger MO before SO exists, based on the business flow. |
| Possible relationships | IO appears as custom fields on `mrp_production`, `approval_product_line`, and `purchase_order_line`. |
| Business layer | Internal Order / Planning |
| Dashboard usefulness | Required for Flow B and IO profitability. |
| Missing or unclear fields | No IO master table was found. No IO status, owner, date, customer expectation, or explicit later SO link was found. |

Enough for dashboard use: no. Current data only has IO references, not an IO entity.

### Internal Order fields found

| Table | Field | Meaning |
| --- | --- | --- |
| `mrp_production` | `x_studio_nomor_io` | Candidate IO number on MO. |
| `approval_product_line` | `x_studio_nomor_io` | Candidate IO number on RKB/planning line. |
| `purchase_order_line` | `x_studio_many2one_field_ij0j0` | Candidate IO field on procurement line. Field name is unclear and should be mapped. |

No direct IO field was found in `sale_order` or `sale_order_line`. This means IO to later SO is currently unclear.

## Manufacturing

### `mrp_production`

| Item | Detail |
| --- | --- |
| Row count | 10,793 |
| Important columns | `id`, `name`, `product_id`, `product_qty`, `state`, `date_start`, `date_finished`, `origin`, `x_studio_nomor_io`, `x_studio_nomor_jo`, `x_studio_master_production_schedule_start`, `x_studio_master_production_schedule_finish`, `company_id` |
| Business meaning | Manufacturing Order header. Represents planned/actual production order, product, quantity, status, dates, source document, IO, and JO. |
| Possible relationships | `origin` matches `sale_order.name` for many MOs. `name` matches `stock_move_line.reference` for many stock movements. `x_studio_nomor_io` can link to RKB/procurement IO fields. `x_studio_nomor_jo` can link to RKB/procurement JO fields. |
| Business layer | Manufacturing |
| Dashboard usefulness | Core table for MO dashboard, production tracking, SO-to-MO trace, and IO-to-MO trace. |
| Missing or unclear fields | No explicit SO FK. `origin` can also contain MO names or IO-like values, so it is not always an SO. No BOM, routing, work order, or cost fields. Actual material value cannot be calculated from this table alone. |

Enough for dashboard use: yes for production status and traceability; partial for profitability.

### `stock_move`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Odoo stock move header/detail that usually connects demand, picking, production, raw material consumption, finished goods production, and valuation logic. |
| Possible relationships | Would normally bridge `stock_move_line`, `mrp_production`, `stock_picking`, sale lines, and procurement. |
| Business layer | Manufacturing / Inventory / Delivery |
| Dashboard usefulness | Important for reliable material consumption, delivery, and actual cost analysis. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no. This is one of the biggest gaps for actual manufacturing cost.

### `stock_move_line`

| Item | Detail |
| --- | --- |
| Row count | 224,919 |
| Important columns | `id`, `reference`, `date_x`, `x_studio_source_document`, `product_id`, `product_category_name`, `x_studio_sale_line`, `x_studio_demand`, `quantity`, `product_uom_id`, `location_id`, `location_dest_id`, `state`, `picking_partner_id`, `company_id`, `source` |
| Business meaning | Executed stock movement line. Can show actual product movements, source/destination location IDs, quantities, and references. |
| Possible relationships | `reference` matches `mrp_production.name` for MO movements. `x_studio_source_document` matches `sale_order.name` for SO movements. `x_studio_sale_line` may link to sale line, but the key format needs validation. |
| Business layer | Manufacturing / Inventory / Delivery |
| Dashboard usefulness | Useful for actual movement quantities, delivery movement trace, and possible material consumption quantity analysis. |
| Missing or unclear fields | Missing `stock_move`, `stock_picking`, and `stock_location` make it hard to classify raw consumption vs finished goods vs delivery. No unit cost or valuation fields. Location IDs lack names. |

Enough for dashboard use: partial. Good for quantities and trace; insufficient for actual cost value without valuation data.

## RKB / PPIC Planning

### `approval_product_line`

| Item | Detail |
| --- | --- |
| Row count | 42,885 |
| Important columns | `id`, `approval_request_id`, `product_id`, `description`, `quantity`, `product_uom_id`, `x_studio_unit_price`, `x_studio_subtotal`, `x_studio_date_of_need`, `x_studio_nomor_io`, `x_studio_nomor_jo`, `x_studio_status`, `x_studio_related_field_ier4u`, `x_studio_reqestor`, `company_id` |
| Business meaning | Approval product/request lines. Based on `BUSINESS_FLOW.md`, RKB from `approval_product_line` with category RKB represents PPIC material planning. |
| Possible relationships | `x_studio_nomor_io` can relate to MO IO and purchase line IO. `x_studio_nomor_jo` can relate to MO JO and purchase line JO. `approval_request_id` should link to missing `approval_request`. |
| Business layer | RKB / PPIC Planning |
| Dashboard usefulness | Useful candidate for planned material quantities and RKB planned cost using `quantity`, `x_studio_unit_price`, and `x_studio_subtotal`. |
| Missing or unclear fields | No `category` field was found in this table. `approval_request` is missing, so the required category = RKB rule cannot be applied reliably. Need confirm whether all extracted rows are RKB or extract the approval category/header. |

Enough for dashboard use: partial. RKB cost can be prototyped only after category identification is solved.

### `approval_request`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Approval request header. Likely contains request category, requester, status, dates, and approval metadata. |
| Possible relationships | Would link to `approval_product_line.approval_request_id`. |
| Business layer | RKB / PPIC Planning |
| Dashboard usefulness | Needed to identify category = RKB and separate PPIC planning from other approval lines. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no. Required for business-correct RKB filtering.

## Procurement

### `purchase_order`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Purchase Order header. Needed for vendor, PO state, order date, approval date, currency, and receipt/billing context. |
| Possible relationships | Would normally link to `purchase_order_line.order_id`. |
| Business layer | Procurement |
| Dashboard usefulness | Required for reliable procurement status and vendor-level purchase analysis. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no.

### `purchase_order_line`

| Item | Detail |
| --- | --- |
| Row count | 20,936 |
| Important columns | `id`, `order_id`, `partner_id`, `date_approve`, `date_planned`, `state`, `product_id`, `product_qty`, `product_uom`, `qty_received`, `qty_invoiced`, `currency_id`, `x_studio_currency_rate_inverse`, `price_unit`, `price_subtotal`, `x_studio_group_po`, `x_studio_many2one_field_ij0j0`, `x_studio_jo`, `x_studio_payment_terms`, `purchaser`, `company_id`, `taxes_id` |
| Business meaning | Purchase Order line detail. Represents procured materials/services, quantities, price, receipt/invoice progress, vendor, IO/JO-like references, and planned dates. |
| Possible relationships | `x_studio_many2one_field_ij0j0` appears to be an IO-like key. `x_studio_jo` appears to be a JO key. `order_id` should link to missing `purchase_order`, but extracted values may be mixed ID/display values and need validation. |
| Business layer | Procurement |
| Dashboard usefulness | Useful for procurement cost by product, IO, JO, vendor, and status at line level. |
| Missing or unclear fields | Missing purchase header. The IO field name is not business-readable. No direct receipt valuation link. PO-to-RKB relation is unclear. |

Enough for dashboard use: partial.

## Inventory / Delivery

### `stock_quant`

| Item | Detail |
| --- | --- |
| Row count | 27,554 |
| Important columns | `id`, `location_id`, `product_id`, `inventory_quantity_auto_apply`, `reserved_quantity`, `product_uom_id`, `company_id` |
| Business meaning | Current inventory quantity snapshot by product and location. |
| Possible relationships | Product and location IDs should link to product and location masters, but product masters are empty and `stock_location` is missing. |
| Business layer | Inventory |
| Dashboard usefulness | Useful for current stock/reserved quantity. Can support finished goods availability only after location/product classification is fixed. |
| Missing or unclear fields | No location names/usages. No stock valuation. Product master data unavailable. |

Enough for dashboard use: partial for quantity, weak for finished goods decisioning.

### `stock_picking`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Delivery Order, receipt, transfer, and picking header. |
| Possible relationships | Would normally connect stock movements to SO, PO, delivery status, partner, scheduled date, and completion date. |
| Business layer | Inventory / Delivery |
| Dashboard usefulness | Required for reliable DO flow and delivery performance. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no. Delivery Order cannot be implemented cleanly without it.

### `stock_location`

| Item | Detail |
| --- | --- |
| Row count | Missing table |
| Important columns | Not available |
| Business meaning | Inventory location master with location name, usage, parent location, warehouse, customer/vendor/production/internal classification. |
| Possible relationships | Would link to `stock_move_line.location_id`, `stock_move_line.location_dest_id`, and `stock_quant.location_id`. |
| Business layer | Inventory / Delivery / Manufacturing |
| Dashboard usefulness | Required to classify raw material, WIP, finished goods, production, customer delivery, vendor receipt, and internal movements. |
| Missing or unclear fields | Entire table is not extracted. |

Enough for dashboard use: no.

### `product_product`

| Item | Detail |
| --- | --- |
| Row count | 0 |
| Important columns | `id`, `name`, `default_code`, `barcode`, `list_price`, `standard_price`, `active`, `create_date`, `write_date` |
| Business meaning | Product variant master. |
| Possible relationships | Should enrich product fields in sales, MO, RKB, purchase, stock, and accounting tables. |
| Business layer | Product master / Inventory |
| Dashboard usefulness | Currently not useful because it is empty. |
| Missing or unclear fields | No rows extracted. Need resync or mapping fix. |

Enough for dashboard use: no until populated.

### `product_template`

| Item | Detail |
| --- | --- |
| Row count | 0 |
| Important columns | `id`, `name`, `default_code`, `barcode`, `categ_id`, `type`, `list_price`, `standard_price`, `active`, `company_id`, `create_date`, `write_date` |
| Business meaning | Product template master with category/type and standard/list price. |
| Possible relationships | Should enrich product category/type and costing across all operational tables. |
| Business layer | Product master / Inventory / Costing |
| Dashboard usefulness | Currently not useful because it is empty. |
| Missing or unclear fields | No rows extracted. Product category and standard cost cannot be reliably used. |

Enough for dashboard use: no until populated.

## Overall Table Coverage

Tables found and useful:
- `sale_order`
- `sale_order_line`
- `account_move_line`
- `account_payment`
- `mrp_production`
- `stock_move_line`
- `approval_product_line`
- `purchase_order_line`
- `stock_quant`

Tables found but currently empty:
- `product_product`
- `product_template`

Important missing tables:
- `account_move`
- `stock_move`
- `stock_picking`
- `stock_location`
- `approval_request`
- `purchase_order`
- Internal Order master table, if one exists in Odoo

