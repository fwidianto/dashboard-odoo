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

# 1. Business Entities

## Sales Order (SO)

Sales Order represents confirmed customer demand.

A Sales Order may:

* Consume existing finished goods inventory
* Trigger a Manufacturing Order
* Be linked to a previous Internal Order

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

1. Sales Orders
2. Internal Orders

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

Category:

RKB

(Custom module)

---

# 5. RKB Purpose

RKB is the detailed material requirement list.

It serves as:

* Production planning document
* Procurement planning document
* Cost comparison document

RKB is significantly more detailed than Estimator data.

Because RKB contains actual material requirements, it can be matched directly against Manufacturing Orders.

---

# 6. Procurement & Inventory Flow

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
