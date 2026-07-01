# Material Search Future Plan

**Date:** 2026-07-01  
**Status:** Future phase agreed  
**Purpose:** Universal search for material correlation across SO, IO, RKB, ROP, PO, and receipt.

---

## 1. Why this should be separate

The Order Material Tracking page should answer:

```text
For this order, where are the related materials?
```

The Material Search page should answer:

```text
For this material/item/document, where does it appear across SO, IO, RKB, ROP, PO, and receipt?
```

These are related but different use cases.

Keeping them separate avoids making one page too noisy.

---

## 2. Page Concept

Proposed page:

```text
/dashboard/material-search
```

Purpose:

```text
Search all material relationships from product, SO, IO, ROP, PO, supplier, or customer.
```

---

## 3. Search Inputs

The page should support search by:

```text
- Product Name
- Product Code
- Internal Order Number
- Sales Order Number
- RKB Number
- ROP Number / Approval Number
- Purchase Order Number
- Supplier
- Customer
```

---

## 4. Main Table Fields

Suggested fields:

```text
- Product Code
- Product Name
- Internal Order Number
- Sales Order Number
- RKB Number
- ROP Number / Approval Number
- PO Number
- Supplier
- Customer
- RKB Qty
- ROP Qty
- PO Qty
- Received Qty
- Current Status
- Follow-Up Action
```

---

## 5. Questions this page should answer

```text
Barang ini ada di mana?
Ada RKB-nya?
Ada ROP-nya?
Sudah PO?
PO nomor berapa?
Supplier-nya siapa?
Sudah datang?
Untuk SO/IO mana?
Apa yang harus difollow-up?
```

---

## 6. Scope Boundary

Included:

```text
- Material correlation
- Document relationship search
- Procurement status
- Receipt status
- SO/IO relationship context
```

Not included in first version:

```text
- Full inventory valuation
- Accounting COGS
- AR/payment
- Profitability
- Supplier performance scoring
- Forecasting
```

---

## 7. Future Innovation Ideas

### 7.1 Universal search bar

One search box that accepts:

```text
SO number, IO number, PO number, ROP number, product code, or product name
```

The system detects the type and returns related records.

---

### 7.2 Material journey timeline

Show a visual timeline:

```text
RKB → ROP → PO → Receipt → Production → Finished Good → Delivery
```

---

### 7.3 Follow-up action engine

Add a field:

```text
next_action
```

Examples:

```text
Create ROP
Create PO
Follow up supplier
Receive remaining qty
Start production
Check delivery
Needs manual review
```

---

### 7.4 Executive / Operations / Audit modes

Potential display modes:

```text
Executive Mode = summary and exceptions only
Operations Mode = full material tracking table
Audit Mode = technical relationship diagnostics
```

---

## 8. Progress Checklist

- [ ] Confirm Order Material Tracking page is stable first
- [ ] Define material search data grain
- [ ] Define product key matching rules
- [ ] Define SO / IO / ROP / PO relationship rules
- [ ] Build SQL view for material search
- [ ] Build API endpoint
- [ ] Build frontend page
- [ ] Add universal search input
- [ ] Add filters
- [ ] Test with real product examples
- [ ] Polish UI
