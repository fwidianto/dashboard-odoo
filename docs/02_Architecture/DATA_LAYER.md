# Data Layer Definition

## Principle

A table may appear in multiple layers.

Layers are not physical database tables.
Layers are business perspectives used to answer specific questions.

The same Odoo table can support different layers depending on:
- transaction type
- document source
- movement direction
- related document
- business question

---

## Revenue Layer

Purpose:
Measure confirmed or invoiced customer revenue.

Main question:
How much revenue did we generate?

Possible tables:
- sale_order_line
- account_move
- account_move_line

Usage logic:
- sale_order_line = ordered revenue
- account_move = invoiced revenue
- account_move_line = detailed invoice revenue

---

## Procurement Layer

Purpose:
Measure purchased materials and supplier cost.

Main question:
How much material cost was purchased or received?

Possible tables:
- purchase_order_line
- stock_move
- account_move
- account_move_line

Usage logic:
- purchase_order_line = ordered purchase cost
- stock_move = received material movement
- account_move = vendor bill
- account_move_line = detailed vendor bill cost

---

## Production Layer

Purpose:
Measure actual manufacturing execution and material consumption.

Main question:
What materials were consumed to produce finished goods?

Possible tables:
- mrp_production
- stock_move
- stock_move_line

Usage logic:
- mrp_production = manufacturing order header
- stock_move = raw material consumption and finished good production
- stock_move_line = detailed movement execution

---

## Inventory Layer

Purpose:
Measure current and historical stock position.

Main question:
What stock do we have, where is it, and how did it move?

Possible tables:
- stock_quant
- stock_move
- stock_move_line

Usage logic:
- stock_quant = current stock balance
- stock_move = planned or completed movement
- stock_move_line = actual detailed movement

---

## Delivery Layer

Purpose:
Measure delivery of finished goods to customer.

Main question:
What has been delivered to customer?

Possible tables:
- stock_picking
- stock_move
- stock_move_line
- sale_order_line

Usage logic:
- stock_picking = delivery document
- stock_move = delivered products
- sale_order_line = sales reference

---

## Profitability Layer

Purpose:
Compare revenue, planned cost, and actual cost.

Main question:
Is the SO, IO, or MO profitable?

Possible sources:
- sale_order_line
- approval_product_line
- mrp_production
- stock_move
- purchase_order_line
- account_move_line

Usage logic:
- sale_order_line = revenue baseline
- approval_product_line = RKB planned material cost
- mrp_production = production reference
- stock_move = actual material consumption
- purchase_order_line = purchase cost reference
- account_move_line = financial actual