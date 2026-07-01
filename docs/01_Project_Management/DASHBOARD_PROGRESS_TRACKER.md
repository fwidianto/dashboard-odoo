# Dashboard Progress Tracker

**Date:** 2026-07-01  
**Current project phase:** Phase 2A.2 planning  
**Current stable base:** Sales Order dashboard and Internal Order dashboard  
**Next focus:** Order Material Tracking based on Internal Order Rekap

---

## 1. Completed / Stabilized

### Sales Order Dashboard

- [x] Sales Order dashboard stabilized
- [x] Year filter added
- [x] Source labels improved
- [x] Amount progress capped
- [x] Down payment / placeholder lines excluded from progress where detectable
- [x] Detail expansion performance improved with lazy loading
- [x] RKB Planned Cost added
- [x] Actual Cost added from Cost of Analysis
- [x] Actual Cost corrected to quantity-based logic
- [x] IO RKB Planned Cost corrected as cost pool allocation
- [x] Contribution metrics labeled as operational Kontribusi, not accounting gross profit

### Internal Order Dashboard

- [x] Internal Order dashboard view applied
- [x] Internal Order dashboard API fixed
- [x] Internal Order dashboard loads

### Internal Order Rekap

- [x] `sql/07_internal_order_cost_rekap_views.sql` found
- [x] `vw_internal_order_rekap_summary` confirmed as required by API
- [x] `vw_internal_order_rekap_lines` confirmed as required by API
- [ ] Internal Order Rekap UI cleanup pending

---

## 2. Current Decisions

### Decision 1 — Page direction

The current Internal Order Rekap should evolve into:

```text
Order Material Tracking
```

It should support both:

```text
- Internal Order Perspective
- Sales Order Perspective
```

### Decision 2 — Hide confusing cards

Hide from main UI:

```text
- Mixed UOM Count
- Not Yet ROP Amount
```

Reason:

```text
They are diagnostic/matching concepts and may confuse users.
```

### Decision 3 — Material Search is separate

Create a separate future page:

```text
Material Search
```

Purpose:

```text
Universal search by product, SO, IO, RKB, ROP, PO, supplier, or customer.
```

---

## 3. Next Work Plan

### Step 1 — Internal Order Rekap UI cleanup

- [ ] Use compact number format on cards
- [ ] Rename Trackable RKB Actual to Product Item RKB
- [ ] Rename Non-Trackable RKB to Non-Product / Service Item RKB
- [ ] Rename Trackable Product to Product Item
- [ ] Remove underscores from displayed statuses
- [ ] Hide Mixed UOM Count
- [ ] Hide Not Yet ROP Amount

### Step 2 — Card filter behavior

- [ ] Make every summary card clickable
- [ ] Add filter state
- [ ] Add clear filter behavior
- [ ] Match Sales Order dashboard interaction style

### Step 3 — Add document relationship fields

- [ ] Show RKB Number
- [ ] Show ROP Number / Approval Number
- [ ] Show PO Related Number
- [ ] Show Sales Order Number
- [ ] Show Internal Order Number
- [ ] Show Product Name clearly

### Step 4 — Order perspective design

- [ ] Define Internal Order Perspective
- [ ] Define Sales Order Perspective
- [ ] Decide whether this is implemented as tabs, toggle, or filter
- [ ] Keep page readable and not crowded

### Step 5 — VP demo preparation

- [ ] Add simple login page
- [ ] Protect dashboard routes
- [ ] Run locally from PC
- [ ] Test access from same Wi-Fi / hotspot
- [ ] Prepare temporary tunnel only if needed
- [ ] Tag first review version as `v0.1-vp-review`

---

## 4. Risks / Notes

### RKB vs ROP matching

Current RKB/ROP comparison is based on Odoo RKB/ROP correlation by IO and product key.

Important limitation:

```text
Not every RKB item must become ROP.
```

Therefore, avoid strong labels like:

```text
Not Yet ROP
Procurement Shortage
```

Use safer language:

```text
RKB Without ROP Match
Matching Gap
Needs Review
```

But for now, hide the confusing card from main UI.

---

## 5. Tomorrow Success Criteria

Tomorrow is successful if:

```text
1. Order Material Tracking is clearer than current Internal Order Rekap.
2. Cards are readable with compact numbers.
3. Confusing diagnostics are hidden.
4. Labels are business-friendly.
5. Cards can filter table rows.
6. Table shows IO, SO, RKB, ROP, and PO relationship fields.
7. Page can be shown to VP without needing long explanation.
```
