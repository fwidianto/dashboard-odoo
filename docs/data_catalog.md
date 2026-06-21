# Data Catalog

**Generated:** 2026-06-21  
**Source:** Odoo PostgreSQL Synchronization Configuration (`config/models.yaml`)  
**Purpose:** Document all synchronized PostgreSQL tables for analytics layer development

---

## Overview

This data catalog documents all tables synchronized from Odoo to PostgreSQL. Each entry includes:
- Table name and source Odoo model
- Record count considerations
- Primary key information
- Important business fields
- Likely join relationships

---

## Data Model Summary

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  res.partner    │     │product.template │     │ product.product │
│  (Customers,    │◄────│  (Products)     │────►│  (Variants)     │
│   Vendors)      │     │                 │     │                 │
└────────┬────────┘     └────────┬────────┘     └─────────────────┘
         │                       │
         │      ┌────────────────┴────────────────┐
         │      │                                 │
         ▼      ▼                                 ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  sale.order     │     │ purchase.order  │     │ stock.quant     │
│  sale.order.line│     │ purchase.order.line│   │ stock.move      │
│  (Sales)        │     │ (Purchasing)     │     │ stock.move.line │
└─────────────────┘     └─────────────────┘     │ (Inventory)     │
                                                └────────┬────────┘
                                                         │
┌─────────────────┐     ┌─────────────────┐              │
│  mrp.production │     │account.move     │              │
│  (Manufacturing)│     │account.move.line│              ▼
│                 │     │account.payment  │     ┌─────────────────┐
└─────────────────┘     │  (Accounting)   │     │  (Approval)     │
                        └─────────────────┘     │approval.request │
                                               │approval.product │
                                               └─────────────────┘
```

---

## Core Tables

### 1. res_partner

| Property | Value |
|----------|-------|
| **Source Model** | `res.partner` |
| **PostgreSQL Table** | `res_partner` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Partners (customers, vendors, contacts) |
| **Record Count** | Growing - all active/inactive partners |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Partner name |
| `email` | TEXT | Email address |
| `phone` | TEXT | Phone number |
| `active` | BOOLEAN | Is active record |
| `company_id` | INTEGER | Company (FK to company) |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Join Relationships:**
- `sale.order.partner_id` → `res_partner.id` (Customer)
- `purchase.order.partner_id` → `res_partner.id` (Vendor)
- `account.move.partner_id` → `res_partner.id` (Partner)
- `account.payment.partner_id` → `res_partner.id` (Partner)

---

### 2. product_template

| Property | Value |
|----------|-------|
| **Source Model** | `product.template` |
| **PostgreSQL Table** | `product_template` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Product templates (master data) |
| **Record Count** | Growing - all product templates |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Product name |
| `list_price` | NUMERIC(20,4) | Sale price |
| `standard_price` | NUMERIC(20,4) | Cost price |
| `type` | VARCHAR(64) | Product type (consumable, service, storable) |
| `active` | BOOLEAN | Is active |
| `default_code` | TEXT | Internal reference |
| `barcode` | TEXT | Barcode |
| `categ_id` | INTEGER | Category (FK) |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Join Relationships:**
- `sale.order.line.product_id` → `product_product.id` → `product_template.id`
- `purchase.order.line.product_id` → `product_product.id` → `product_template.id`
- `stock.move.product_id` → `product_product.id` → `product_template.id`
- `stock.quant.product_id` → `product_product.id` → `product_template.id`
- `mrp.production.product_id` → `product_product.id` → `product_template.id`

---

### 3. product_product

| Property | Value |
|----------|-------|
| **Source Model** | `product.product` |
| **PostgreSQL Table** | `product_product` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Product variants (specific products) |
| **Record Count** | Growing - all product variants |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Variant name |
| `default_code` | TEXT | Internal reference |
| `barcode` | TEXT | Barcode |
| `list_price` | NUMERIC(20,4) | Sale price |
| `standard_price` | NUMERIC(20,4) | Cost price |
| `active` | BOOLEAN | Is active |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Join Relationships:**
- `sale.order.line.product_id` → `product_product.id`
- `purchase.order.line.product_id` → `product_product.id`
- `stock.move.product_id` → `product_product.id`
- `stock.quant.product_id` → `product_product.id`
- `mrp.production.product_id` → `product_product.id`

---

## Sales Tables

### 4. sale_order

| Property | Value |
|----------|-------|
| **Source Model** | `sale.order` |
| **PostgreSQL Table** | `sale_order` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Sales orders (quotations and orders) |
| **Record Count** | Growing - all sales documents |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Order number (SO-00001) |
| `partner_id` | INTEGER | Customer (FK → res_partner) |
| `date_order` | DATE | Order date |
| `state` | VARCHAR(64) | Status (draft, sent, sale, done, cancel) |
| `amount_total` | NUMERIC(20,4) | Total amount |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |
| `x_studio_delivery_status` | TEXT | Delivery status |
| `x_studio_invoice_status` | TEXT | Invoice status |

**Order States:**
- `draft` - Quotation draft
- `sent` - Quotation sent
- `sale` - Sales order
- `done` - Locked
- `cancel` - Cancelled

**Join Relationships:**
- `sale_order.id` ← `sale_order_line.order_id` (1:M)
- `sale_order.partner_id` → `res_partner.id` (Customer)

---

### 5. sale_order_line

| Property | Value |
|----------|-------|
| **Source Model** | `sale.order.line` |
| **PostgreSQL Table** | `sale_order_line` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Sales order line items |
| **Record Count** | Growing - all order lines |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `order_id` | INTEGER | Order (FK → sale_order) |
| `product_id` | INTEGER | Product (FK → product_product) |
| `name` | TEXT | Line description |
| `product_uom_qty` | NUMERIC(20,4) | Quantity ordered |
| `price_unit` | NUMERIC(20,4) | Unit price |
| `price_subtotal` | NUMERIC(20,4) | Line subtotal |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `sale_order_line.order_id` → `sale_order.id`
- `sale_order_line.product_id` → `product_product.id`

---

## Purchasing Tables

### 6. purchase_order

| Property | Value |
|----------|-------|
| **Source Model** | `purchase.order` |
| **PostgreSQL Table** | `purchase_order` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Purchase orders |
| **Record Count** | Growing - all purchase orders |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Order reference |
| `partner_id` | INTEGER | Vendor (FK → res_partner) |
| `date_order` | DATE | Order date |
| `state` | VARCHAR(64) | Status (draft, sent, purchase, done, cancel) |
| `amount_total` | NUMERIC(20,4) | Total amount |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Order States:**
- `draft` - Draft
- `sent` - RFQ sent
- `purchase` - Purchase order
- `done` - Done
- `cancel` - Cancelled

**Join Relationships:**
- `purchase_order.id` ← `purchase_order_line.order_id` (1:M)
- `purchase_order.partner_id` → `res_partner.id` (Vendor)

---

### 7. purchase_order_line

| Property | Value |
|----------|-------|
| **Source Model** | `purchase.order.line` |
| **PostgreSQL Table** | `purchase_order_line` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Purchase order line items |
| **Record Count** | Growing - all PO lines |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `order_id` | INTEGER | Order (FK → purchase_order) |
| `product_id` | INTEGER | Product (FK → product_product) |
| `name` | TEXT | Line description |
| `product_qty` | NUMERIC(20,4) | Quantity ordered |
| `price_unit` | NUMERIC(20,4) | Unit price |
| `price_subtotal` | NUMERIC(20,4) | Line subtotal |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `purchase_order_line.order_id` → `purchase_order.id`
- `purchase_order_line.product_id` → `product_product.id`

---

## Accounting Tables

### 8. account_move

| Property | Value |
|----------|-------|
| **Source Model** | `account.move` |
| **PostgreSQL Table** | `account_move` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Journal entries (invoices, bills, etc.) |
| **Record Count** | Growing - all journal entries |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Entry number |
| `date` | DATE | Entry date |
| `ref` | TEXT | Reference |
| `partner_id` | INTEGER | Partner (FK → res_partner) |
| `move_type` | VARCHAR(64) | Type (entry, out_invoice, in_invoice, etc.) |
| `state` | VARCHAR(64) | Status (draft, posted, cancelled) |
| `amount_total` | NUMERIC(20,4) | Total amount |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Move Types:**
- `entry` - Miscellaneous Entry
- `out_invoice` - Customer Invoice
- `in_invoice` - Vendor Bill
- `out_refund` - Customer Credit Note
- `in_refund` - Vendor Credit Note
- `out_receipt` - Sales Receipt
- `in_receipt` - Purchase Receipt

**Join Relationships:**
- `account_move.id` ← `account_move_line.move_id` (1:M)
- `account_move.partner_id` → `res_partner.id`

---

### 9. account_move_line

| Property | Value |
|----------|-------|
| **Source Model** | `account.move.line` |
| **PostgreSQL Table** | `account_move_line` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Journal entry lines |
| **Record Count** | Growing - all journal lines |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `move_id` | INTEGER | Journal entry (FK → account_move) |
| `account_id` | INTEGER | Account (FK) |
| `partner_id` | INTEGER | Partner (FK → res_partner) |
| `name` | TEXT | Line label |
| `debit` | NUMERIC(20,4) | Debit amount |
| `credit` | NUMERIC(20,4) | Credit amount |
| `balance` | NUMERIC(20,4) | Line balance |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `account_move_line.move_id` → `account_move.id`
- `account_move_line.partner_id` → `res_partner.id`

---

### 10. account_payment

| Property | Value |
|----------|-------|
| **Source Model** | `account.payment` |
| **PostgreSQL Table** | `account_payment` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Payments |
| **Record Count** | Growing - all payments |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Payment reference |
| `date` | DATE | Payment date |
| `partner_id` | INTEGER | Partner (FK → res_partner) |
| `amount` | NUMERIC(20,4) | Payment amount |
| `payment_type` | VARCHAR(64) | Type (inbound, outbound, transfer) |
| `state` | VARCHAR(64) | Status (draft, posted, sent, reconciled, cancelled) |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Join Relationships:**
- `account_payment.partner_id` → `res_partner.id`

---

## Inventory Tables

### 11. stock_move

| Property | Value |
|----------|-------|
| **Source Model** | `stock.move` |
| **PostgreSQL Table** | `stock_move` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Stock moves (transfers, receipts, deliveries) |
| **Record Count** | Growing - all stock movements |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Move description |
| `product_id` | INTEGER | Product (FK → product_product) |
| `product_uom_qty` | NUMERIC(20,4) | Quantity |
| `state` | VARCHAR(64) | Status (draft, waiting, confirmed, assigned, done, cancel) |
| `location_id` | INTEGER | Source location |
| `location_dest_id` | INTEGER | Destination location |
| `date` | TIMESTAMP | Move date |
| `create_date` | TIMESTAMP | Creation timestamp |

**Move States:**
- `draft` - Draft
- `waiting` - Waiting Another Move
- `confirmed` - Waiting Availability
- `assigned` - Ready to Transfer
- `done` - Transferred
- `cancel` - Cancelled

**Join Relationships:**
- `stock_move.product_id` → `product_product.id`
- `stock_move.id` ← `stock_move_line.move_id` (1:M)

---

### 12. stock_move_line

| Property | Value |
|----------|-------|
| **Source Model** | `stock.move.line` |
| **PostgreSQL Table** | `stock_move_line` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Stock move line items (detailed moves) |
| **Record Count** | Growing - all detailed moves |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `move_id` | INTEGER | Stock move (FK → stock_move) |
| `product_id` | INTEGER | Product (FK → product_product) |
| `lot_id` | INTEGER | Lot/Serial number |
| `location_id` | INTEGER | Source location |
| `location_dest_id` | INTEGER | Destination location |
| `qty_done` | NUMERIC(20,4) | Quantity done |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `stock_move_line.move_id` → `stock_move.id`
- `stock_move_line.product_id` → `product_product.id`

---

### 13. stock_quant

| Property | Value |
|----------|-------|
| **Source Model** | `stock.quant` |
| **PostgreSQL Table** | `stock_quant` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Stock quantities (current inventory) |
| **Record Count** | Grows with locations × products |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `product_id` | INTEGER | Product (FK → product_product) |
| `location_id` | INTEGER | Location (FK) |
| `lot_id` | INTEGER | Lot/Serial number |
| `quantity` | NUMERIC(20,4) | On-hand quantity |
| `reserved_quantity` | NUMERIC(20,4) | Reserved quantity |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `stock_quant.product_id` → `product_product.id`

---

## Manufacturing Tables

### 14. mrp_production

| Property | Value |
|----------|-------|
| **Source Model** | `mrp.production` |
| **PostgreSQL Table** | `mrp_production` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Manufacturing orders |
| **Record Count** | Growing - all MO records |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | MO reference (MO/00001) |
| `product_id` | INTEGER | Product to manufacture (FK → product_product) |
| `product_qty` | NUMERIC(20,4) | Quantity to produce |
| `state` | VARCHAR(64) | Status (draft, confirmed, progress, done, cancel) |
| `date_start` | TIMESTAMP | Planned start date |
| `date_finished` | TIMESTAMP | Finished date |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Production States:**
- `draft` - Draft
- `confirmed` - Confirmed
- `progress` - In Progress
- `done` - Done
- `cancel` - Cancelled

**Join Relationships:**
- `mrp_production.product_id` → `product_product.id`

---

## Approval Tables

### 15. approval_request

| Property | Value |
|----------|-------|
| **Source Model** | `approval.request` |
| **PostgreSQL Table** | `approval_request` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Purchase approval requests |
| **Record Count** | Growing - all approval requests |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `name` | TEXT | Request reference |
| `request_owner_id` | INTEGER | Requester (FK → res_partner) |
| `category_id` | INTEGER | Category (FK) |
| `amount` | NUMERIC(20,4) | Request amount |
| `state` | VARCHAR(64) | Status |
| `date` | DATE | Request date |
| `create_date` | TIMESTAMP | Creation timestamp |
| `write_date` | TIMESTAMP | Last update timestamp |

**Join Relationships:**
- `approval_request.request_owner_id` → `res_partner.id`

---

### 16. approval_product_line

| Property | Value |
|----------|-------|
| **Source Model** | `approval.product.line` |
| **PostgreSQL Table** | `approval_product_line` |
| **Primary Key** | `id` (INTEGER) |
| **Description** | Approval request line items |
| **Record Count** | Growing - all approval lines |

| Column | Type | Business Meaning |
|--------|------|------------------|
| `id` | INTEGER | Odoo record ID (PK) |
| `request_id` | INTEGER | Request (FK → approval_request) |
| `product_id` | INTEGER | Product (FK → product_product) |
| `quantity` | NUMERIC(20,4) | Quantity requested |
| `price_unit` | NUMERIC(20,4) | Unit price |
| `estimated_price` | NUMERIC(20,4) | Estimated total |
| `create_date` | TIMESTAMP | Creation timestamp |

**Join Relationships:**
- `approval_product_line.request_id` → `approval_request.id`
- `approval_product_line.product_id` → `product_product.id`

---

## Table Reference Summary

| Table Name | Odoo Model | Primary Key | Key Business Fields |
|------------|------------|-------------|---------------------|
| `res_partner` | res.partner | id | name, email, company_id |
| `product_template` | product.template | id | name, list_price, standard_price, categ_id |
| `product_product` | product.product | id | name, default_code, list_price |
| `sale_order` | sale.order | id | name, partner_id, date_order, state, amount_total |
| `sale_order_line` | sale.order.line | id | order_id, product_id, product_uom_qty, price_subtotal |
| `purchase_order` | purchase.order | id | name, partner_id, date_order, state, amount_total |
| `purchase_order_line` | purchase.order.line | id | order_id, product_id, product_qty, price_subtotal |
| `account_move` | account.move | id | name, date, move_type, state, amount_total |
| `account_move_line` | account.move.line | id | move_id, account_id, debit, credit, balance |
| `account_payment` | account.payment | id | name, date, partner_id, amount, payment_type |
| `stock_move` | stock.move | id | name, product_id, product_uom_qty, state, date |
| `stock_move_line` | stock.move.line | id | move_id, product_id, qty_done |
| `stock_quant` | stock.quant | id | product_id, location_id, quantity, reserved_quantity |
| `mrp_production` | mrp.production | id | name, product_id, product_qty, state, date_start |
| `approval_request` | approval.request | id | name, request_owner_id, amount, state |
| `approval_product_line` | approval.product.line | id | request_id, product_id, quantity, estimated_price |

---

## Analytics Considerations

### Slowly Changing Dimensions
- `res_partner`: Partner attributes may change (name, address)
- `product_template` / `product_product`: Prices and product info may change

### Date Dimensions
- `sale_order.date_order` - Order date
- `purchase_order.date_order` - PO date
- `account_move.date` - Invoice date
- `account_payment.date` - Payment date
- `stock_move.date` - Move date
- `mrp_production.date_start` / `date_finished` - Production dates

### Quantity Dimensions
- Sales: `sale_order_line.product_uom_qty`
- Purchases: `purchase_order_line.product_qty`
- Inventory: `stock_quant.quantity`, `stock_quant.reserved_quantity`
- Manufacturing: `mrp_production.product_qty`

### Amount Dimensions
- `sale_order.amount_total` - Total sales amount
- `purchase_order.amount_total` - Total purchase amount
- `account_move.amount_total` - Total invoice amount
- `account_payment.amount` - Payment amount
- `sale_order_line.price_subtotal` - Line amount
- `purchase_order_line.price_subtotal` - Line amount

---

## Next Steps

1. **Dimensional Modeling**: Design star schemas for each data mart
2. **View Creation**: Build denormalized SQL views for dashboard consumption
3. **Indexing Strategy**: Optimize views with appropriate indexes
4. **ETL Pipeline**: Consider materialized views or scheduled refresh