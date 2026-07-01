# Dashboard Progress Tracker

**Date:** 2026-07-01  
**Current project phase:** Phase 2A.3 - Order Material Tracking / Interactive Table Controls  
**Current stable base:** Sales Order dashboard and Internal Order dashboard  
**Next focus:** Table readability polish, then decide whether to add Sales Order Perspective before Material Search

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

### Internal Order Rekap / Order Material Tracking

- [x] `sql/07_internal_order_cost_rekap_views.sql` found
- [x] `vw_internal_order_rekap_summary` confirmed as required by API
- [x] `vw_internal_order_rekap_lines` confirmed as required by API
- [x] Internal Order Rekap UI cleanup completed
- [x] Compact number formatting added to KPI cards
- [x] Trackable RKB Actual relabeled as Product Item RKB in UI
- [x] Non-Trackable RKB relabeled as Non-Product / Service Item RKB in UI
- [x] Trackable Product relabeled as Product Item in UI
- [x] Visible underscore-heavy enum labels cleaned up
- [x] Mixed UOM Count hidden from main KPI cards
- [x] Not Yet ROP Amount hidden from main KPI cards
- [x] KPI card filters implemented
- [x] Active filter indicator added
- [x] Clear filter behavior added
- [x] Document relationship fields are working
- [x] IO Reference Amount implemented from approval product lines where `approval_business_type = INTERNAL_ORDER` and `approval_category_raw = MANUFACTURE`
- [x] RKB Kontribusi implemented as IO Reference Amount minus RKB Actual Amount
- [x] RKB Kontribusi % implemented as RKB Kontribusi divided by IO Reference Amount
- [x] Interactive table controls implemented
- [x] Sortable table headers added
- [x] Combined filters added
- [x] Clear All Filters and Clear Sort added
- [x] Document reference rendering updated to inline comma-separated values

---

## 2. Current Decisions

### Decision 1 - Page direction

The current Internal Order Rekap should continue evolving into:

```text
Order Material Tracking
```

It should stay conservative and business-friendly.

### Decision 2 - Hide confusing cards

Hide from main UI:

```text
- Mixed UOM Count
- Not Yet ROP Amount
```

Reason:

```text
They are diagnostic/matching concepts and may confuse users.
```

### Decision 3 - Material Search stays separate

Keep a separate future page:

```text
Material Search
```

Purpose:

```text
Universal search by product, SO, IO, RKB, ROP, PO, supplier, or customer.
```

---

## 3. Next Work Plan

### Step 1 - Table readability and VP demo polish

- [ ] Refine column density and visual hierarchy for the current Internal Order Rekap table
- [ ] Keep the page readable on first load without changing the data model
- [ ] Decide whether the next visible step is a Sales Order Perspective toggle

### Step 2 - Perspective planning

- [ ] Define Internal Order Perspective more clearly
- [ ] Decide whether to add Sales Order Perspective next
- [ ] Keep the first screen from becoming crowded

### Step 3 - Material Search later

- [ ] Do not start Material Search yet
- [ ] Keep it as a separate page when the chain view is stable enough
- [ ] Use it later for universal lookup by product, SO, IO, RKB, ROP, PO, supplier, or customer

### Step 4 - VP readiness

- [ ] Add simple login page
- [ ] Protect dashboard routes
- [ ] Run locally from PC
- [ ] Test access from same Wi-Fi / hotspot
- [ ] Prepare temporary tunnel only if needed
- [ ] Tag first review version as `v0.1-vp-review`

---

## 4. Phase Checklist

### Phase 1 - Stabilize current page

- [x] Confirm `vw_internal_order_rekap_summary` loads
- [x] Confirm `vw_internal_order_rekap_lines` loads
- [x] Confirm current Internal Order Rekap API loads
- [x] Confirm selected IO example works, such as `426IO026`

### Phase 2 - UI label cleanup

- [x] Rename Trackable RKB Actual to Product Item RKB
- [x] Rename Non-Trackable RKB to Non-Product / Service Item RKB
- [x] Rename Trackable Product to Product Item
- [x] Remove underscores from visible labels
- [x] Hide Mixed UOM Count from main cards
- [x] Hide Not Yet ROP Amount from main cards

### Phase 3 - Card filtering

- [x] Make summary cards clickable
- [x] Add active filter indicator
- [x] Add clear filter button
- [x] Ensure behavior matches Sales Order dashboard card filters

### Phase 4 - Table relationship fields

- [x] Show Internal Order Number
- [ ] Show actual linked Sales Order Number
- [x] Show Sales Order Status as Linked / Pre-SO
- [x] Show RKB Number
- [x] Show ROP Number / Approval Number
- [x] Show Related PO Number
- [x] Show Product Name
- [x] Show RKB / ROP / PO / Receipt quantities
- [x] Show current material status

### Phase 5 - Interactive table controls

- [x] Add sortable table headers
- [x] Add combined filters
- [x] Add clear all filters
- [x] Add clear sort
- [x] Keep document references inline and comma-separated

### Phase 6 - VP readiness

- [x] Compact numbers on cards
- [x] Clear labels
- [x] No confusing diagnostics on main screen
- [x] No accounting profit claims
- [x] No raw technical enum labels
- [ ] Ready for VP review demo

---

## 5. Risks / Notes

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

### Latest implementation notes

- Document chain columns now work in the Internal Order Rekap table.
- IO Reference Amount source is verified for `426IO026`.
- For `426IO026`, the verified source totals are approximately:
  - `INTERNAL_ORDER / MANUFACTURE`: 13 rows = `13,401,200,001`
  - `RKB_PLANNING / RKB`: 431 rows = `9,078,900,723.61`
  - `ROP_PROCUREMENT_REQUEST / PEMBELIAN`: 213 rows = `6,428,714,005.63`
- For `426IO026`, expected RKB Kontribusi is approximately `4,322,299,277.39` or `32.25%`.

---

## 6. Success Criteria

The current phase is successful if:

```text
1. Order Material Tracking remains clearer than the old Internal Order Rekap.
2. Cards are readable with compact numbers.
3. Confusing diagnostics are hidden from the main cards.
4. Labels are business-friendly.
5. Cards and filters can narrow the table together.
6. Table shows IO, SO status, RKB, ROP, and PO relationship fields.
7. Page is ready for a VP-facing review without a long explanation.
```
