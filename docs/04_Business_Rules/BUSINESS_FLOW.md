# Business Flow - Manufacturing Profitability System

## Objective

The primary objective of this system is to measure and monitor profitability throughout the manufacturing process, from customer demand to final invoice collection.

The system must answer:

* Is a Sales Order profitable?
* Is a Manufacturing Order profitable?
* How accurate was the estimator's budget?
* How accurate was PPIC's material planning?
* Where did cost overruns occur?
* Which customers, products, and projects generate the highest profit?

---

# Glossary

| Term | Meaning |
| --- | --- |
| SO | Sales Order. Customer demand and revenue document. |
| JO | Job Order. Factory terminology for an SO that requires new production. Every JO is an SO, but not every SO is a JO. |
| IO | Internal Order. Internal make-to-stock demand used to produce finished goods before a customer SO exists. |
| RKB | PPIC material planning for comparison. It does not directly trigger purchasing. |
| ROP / PEMBELIAN | Procurement request / Request of Purchase. |

Important clarification:

* JO is not a separate demand type from SO.
* JO means the Sales Order requires production or represents production demand.
* If an SO consumes finished goods already produced from Internal Order, it is not treated as JO.
* Keep IO separate from JO.

---

# 1. Business Entities

## Sales Order (SO)

Sales Order represents confirmed customer demand.

A Sales Order may:

* Consume existing finished goods inventory
* Trigger a Manufacturing Order
* Be linked to a previous Internal Order

Sales Order source types for V1:

| SO source type | Business meaning |
| --- | --- |
| FROM_INTERNAL_ORDER | SO links to an IO and uses finished goods already produced from that IO. No new MO should be needed for this SO. |
| MAKE_TO_ORDER / JO | SO requires new production and creates or links to MO. Factory users call this JO. |
| FROM_STOCK | SO is delivered from available stock without IO/MO. |

Sales Order is the primary revenue source.

Key Table:

* sale_order
* sale_order_line

---

## Internal Order (IO)

Internal Order is demand created internally by the company.

Purpose:

* Build stock before customer order arrives
* Prepare inventory for expected demand
* Produce strategic finished goods

Internal Orders generate Manufacturing Orders before customer Sales Orders exist.

For dashboard v1, Internal Order is not a separate missing master table.
Internal Order exists inside the approval module:

* `approval_product_line`
* `x_studio_category = MANUFACTURE`

For MANUFACTURE approval lines, `approval_request_id` displays the Internal Order number.
The primary bridge to Manufacturing Order is:

* `approval_product_line.approval_request_id = mrp_production.x_studio_nomor_io`

`approval_product_line.x_studio_nomor_io` is secondary context and should not be the primary Internal Order bridge for v1.

Later Sales Orders produced from Internal Order stock are linked by the Sales Order IO field:

* `sale_order.x_studio_io_1`

This field is stored as set/list text, for example `{1081}` or `{1361,1578}`.
It must be parsed into individual numeric approval request IDs.

One Sales Order may reference multiple Internal Orders.
One Internal Order may be referenced by multiple Sales Orders.

Do not infer the Internal Order to Sales Order relationship directly from MO.

Once a customer order arrives:

* Sales Order references Internal Order
* Existing finished goods inventory is delivered
* No new Manufacturing Order is required

---

## Manufacturing Order (MO)

Manufacturing Order represents production execution.

Key Table:

* mrp_production

Purpose:

* Convert raw materials into finished goods

Manufacturing Orders may originate from:

1. Sales Orders that require production, also called JO by factory users
2. Internal Orders

JO fields in Odoo should be interpreted as Sales Order / job-order references where valid, not as a separate entity competing with SO.

---

# 2. Manufacturing Scenarios

## Scenario A - Make To Order

Customer PO
→ Sales Order
→ Manufacturing Order
→ Finished Goods
→ Delivery
→ Invoice
→ Accounts Receivable

Flow:

SO
→ MO
→ DO
→ Invoice
→ AR

---

## Scenario B - Make To Stock

Internal Order
→ Manufacturing Order
→ Finished Goods Inventory

Later:

Customer PO
→ Sales Order
→ Delivery
→ Invoice
→ AR

Flow:

IO
→ MO
→ Finished Goods Stock

Then

SO
→ DO
→ Invoice
→ AR

No new MO is generated.

---

## Scenario C - Existing Finished Goods Available

Customer PO
→ Sales Order

If stock is available:

SO
→ Delivery
→ Invoice
→ AR

No MO is created.

---

# 3. Cost Planning Flow

## Estimator Stage

Before production begins:

Estimator prepares projected cost.

Estimator Output:

* Material Cost
* Labor Cost
* Overhead Cost
* Expected Total Cost
* Expected Profit

Source:
Excel file outside Odoo

Estimator provides baseline profitability expectation.

---

## Commercial Flow

Estimator
→ Marketing
→ Customer
→ Customer PO
→ BOQ
→ PPIC

---

# 4. PPIC Planning Flow

PPIC translates commercial requirements into manufacturing requirements.

Responsibilities:

* Determine required materials
* Check inventory availability
* Forecast shortages
* Plan production

Output:

RKB (Rencana Kebutuhan Material)

Stored in:

approval_product_line

Approval categories:

| Category | Business role |
| --- | --- |
| RKB | Material planning / PPIC comparison |
| PEMBELIAN | ROP / Request of Purchase |
| ROP | Same business meaning as PEMBELIAN |
| MANUFACTURE | Internal Order |
| INTERNAL USE | Out of current dashboard scope |

(Custom module)

---

# 5. RKB Purpose

RKB is the detailed material requirement list for PPIC planning and comparison.

It serves as:

* Production planning document
* Cost comparison document

RKB is significantly more detailed than Estimator data.

Because RKB contains actual material requirements, it can be matched directly against Manufacturing Orders.

RKB does not directly trigger purchasing. Procurement request flow comes from ROP/PEMBELIAN approval lines.

---

# 6. Procurement & Inventory Flow

Important v1 rule:

* RKB is planning/comparison only and does not directly trigger purchasing.
* ROP / PEMBELIAN is the approval-based Request of Purchase flow.
* MANUFACTURE approval lines represent Internal Order flow into Manufacturing Order.

RKB
→ Check Inventory

If material available:

Inventory
→ Manufacturing Order

If material unavailable:

Purchase Request
→ Purchase Order
→ Goods Receipt
→ Inventory
→ Manufacturing Order

---

# 7. Profitability Framework

## Level 1 - Estimator Profitability

Expected Profit

Revenue
minus
Estimator Cost

Purpose:

Measure quotation quality.

---

## Level 2 - PPIC Profitability

Expected Profit

Revenue
minus
RKB Cost

Purpose:

Measure planning accuracy.

---

## Level 3 - Manufacturing Profitability

Actual Profit

Revenue
minus
Actual MO Consumption
minus
Labor
minus
Overhead

Purpose:

Measure production efficiency.

---

## Level 4 - Final Sales Order Profitability

Revenue
minus
All Actual Costs

Purpose:

Determine true business profitability.

---

# 8. Dashboard Hierarchy

Level 1

Sales Order Dashboard

* Sales value
* Gross profit
* Margin %
* Customer profitability

---

Level 2

Internal Order Dashboard

* Stock build value
* Inventory turnover
* Conversion to Sales Order

---

Level 3

Manufacturing Dashboard

* MO cost
* Material variance
* Production efficiency
* Cost overrun

---

Level 4

Estimator vs Actual Dashboard

Estimator Cost
vs
RKB Cost
vs
Actual Cost

Variance analysis

---

Level 5

Executive Profitability Dashboard

Customer Profitability
Product Profitability
Project Profitability
Salesperson Profitability
Monthly Profit Trend
