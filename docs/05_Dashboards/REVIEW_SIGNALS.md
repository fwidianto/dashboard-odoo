# Review Signals

Last updated: 2026-07-03  
Status: Phase 1 validation baseline  
Applies to:
- Sales Order Traceability Dashboard
- Order Material Tracking / Material & Procurement Dashboard

---

## Purpose

Review Signals are operational review indicators that group dashboard rows into simple follow-up categories.

The purpose is to help users move from reading raw ERP rows to quickly identifying which rows appear healthy, which rows should be monitored, and which rows need operational or procurement follow-up.

Review Signals are not final accounting conclusions, profitability conclusions, or audit results. They are dashboard-level review helpers based on the fields exposed in the current dashboard payload.

---

## Dashboard pages using Review Signals

### Sales Order Traceability

The Sales Order page assigns Review Signals in the frontend after loading rows from:

```text
/api/dashboard/sales-orders
```

The source API reads from:

```text
vw_dashboard_sales_order_traceability
```

### Order Material Tracking

The Order Material Tracking page assigns Review Signals in the frontend after loading rows from:

```text
/api/dashboard/internal-order-rekap
```

The source API reads from internal order / sales order material tracking views including:

```text
vw_internal_order_rekap_summary
vw_internal_order_rekap_lines
```

---

## Review Signal categories

| Signal | Meaning |
| --- | --- |
| Healthy | No immediate follow-up detected based on the exposed dashboard fields. |
| Watchlist | Normal in-progress or context row that should be monitored until complete. |
| Needs Review | A mismatch, unknown source, delayed delivery, unclear classification, or variance needs review. |
| Supplier Follow-up | Procurement or receipt progress needs follow-up, such as ROP without PO or PO not received. |
| Operational Follow-up | Fulfillment, manufacturing, sales-order linkage, source path, or non-product context needs operational attention. |

---

## Sales Order Review Signal rules

Sales Order Review Signals are derived from `follow_up_status`, `source_type`, and cancellation status.

Current priority:

1. Excluded / cancelled rows
2. Healthy
3. Needs Review
4. Operational Follow-up
5. Watchlist

Current rule mapping:

| Condition | Review Signal | Review Note |
| --- | --- | --- |
| Cancelled row | Excluded | Cancelled Sales Order is excluded from active review counts. |
| `follow_up_status = COMPLETED` | Healthy | Delivery and invoice review complete. |
| `follow_up_status = DELAYED_DELIVERY` | Needs Review | Delivery is delayed and needs review. |
| `follow_up_status = UNKNOWN_SOURCE` or `source_type = UNKNOWN_SOURCE` | Needs Review | Source relationship needs checking. |
| `follow_up_status = WAITING_PRODUCTION` | Operational Follow-up | Manufacturing follow-up is required. |
| `follow_up_status = WAITING_DELIVERY` | Operational Follow-up | Delivery/fulfillment follow-up is required. |
| `follow_up_status = WAITING_INVOICE` | Watchlist | Invoice pending after fulfillment progress. |
| Any other active row | Watchlist | In progress; monitor until complete. |

### Sales Order detection cards

| Detection | Current basis |
| --- | --- |
| Delayed delivery | Rows where `follow_up_status = DELAYED_DELIVERY`. |
| Waiting invoice | Rows where `follow_up_status = WAITING_INVOICE`. |
| Source relationship check | Rows where `follow_up_status = UNKNOWN_SOURCE` or `source_type = UNKNOWN_SOURCE`. |
| Operational follow-up | Rows mapped to Operational Follow-up. |
| Supplier follow-up | Not included in Sales Order Phase 1 because no reliable procurement follow-up field is exposed on the Sales Order payload. |
| Contribution watchlist | Not included in Phase 1 because contribution fields are review context, not approved accounting profit rules. |

---

## Order Material Tracking Review Signal rules

Order Material Tracking Review Signals are derived from material chain status, procurement flags, receipt progress, source path, product trackability, and sales-order linkage.

Current priority:

1. Needs Review
2. Supplier Follow-up
3. Operational Follow-up
4. Healthy
5. Watchlist

Current rule mapping:

| Condition | Review Signal | Review Note |
| --- | --- | --- |
| `po_without_rop_flag = true` | Needs Review | PO exists without linked ROP; check procurement chain. |
| `mixed_uom_flag = true` | Needs Review | Mixed UoM detected; quantity comparison may need review. |
| `product_trackability_class = UNKNOWN_PRODUCT_CLASS` | Needs Review | Product classification is unclear. |
| Material status is `Needs Review` | Needs Review | Material chain status needs checking. |
| `excess_rop_amount` exists | Needs Review | ROP amount differs from RKB reference; review variance. |
| `po_excess_amount` exists | Needs Review | PO amount differs from ROP reference; review variance. |
| `rop_without_po_flag = true` | Supplier Follow-up | ROP exists but no PO is linked yet. |
| PO exists but received quantity is zero | Supplier Follow-up | PO created but material has not been received. |
| PO partially received | Supplier Follow-up | PO partially received; supplier follow-up may be needed. |
| No linked Sales Order | Operational Follow-up | Pre-SO Internal Order; monitor until sales order linkage is available. |
| `material_chain_source = UNKNOWN_SOURCE` | Operational Follow-up | Material source path is unclear. |
| Non-trackable product/service row | Operational Follow-up | Non-product/service row; review operational meaning if needed. |
| `material_chain_source = FROM_STOCK` | Healthy | Material is covered from stock. |
| PO fully received with no mismatch flag | Healthy | PO material received; no immediate material follow-up. |
| Any other row | Watchlist | Material chain is in progress; monitor until complete. |

### Order Material Tracking detection cards

| Detection | Current basis |
| --- | --- |
| ROP without PO | Rows where `rop_without_po_flag = true`. |
| PO not received | Rows with PO quantity/value and zero received quantity. |
| Partially received | Rows with received quantity greater than zero but less than PO quantity. |
| PO without ROP | Rows where `po_without_rop_flag = true`. |
| Mixed UoM | Rows where `mixed_uom_flag = true`. |
| Non-product/service rows | Rows where `product_trackability_class` is not `TRACKABLE_PRODUCT`. |
| Excess ROP amount | Rows with non-zero `excess_rop_amount`. |
| PO excess amount | Rows with non-zero `po_excess_amount`. |

---

## Fields used

### Sales Order

- `is_cancelled`
- `follow_up_status`
- `source_type`
- `sales_order_state`
- `order_year`
- `customer_name`
- `product_type_label`
- `commitment_date`
- `has_delivered_qty`
- `has_invoiced_qty`

### Order Material Tracking

- `po_without_rop_flag`
- `rop_without_po_flag`
- `mixed_uom_flag`
- `product_trackability_class`
- `product_presence_status`
- `material_chain_source`
- `has_sales_order_link`
- `rkb_actual_qty`
- `rkb_actual_subtotal`
- `rop_qty`
- `rop_subtotal`
- `po_qty`
- `po_subtotal`
- `po_received_qty`
- `po_invoiced_qty`
- `excess_rop_amount`
- `po_excess_amount`

---

## Filter behavior

### Sales Order Traceability

Review Signal counts are calculated from the same filtered row population used by the table.

Current filters include:

- Sales Order search
- Year
- Customer
- Product type
- Delivery date range
- Source type
- Sales Order status
- Follow-up status
- Review Signal card filter
- Quick filters such as Delivered SO and Invoiced SO

### Order Material Tracking

Review Signal counts are calculated from the current filtered row population, but intentionally exclude the selected Review Signal filter itself. This keeps the full signal mix visible while a user is filtering into one Review Signal category.

Current filters include:

- Perspective and selected Internal Order / Sales Order
- Tab filter
- KPI card filter
- Item type
- Material status
- Sales Order status
- Presence state
- Flag filters
- Review Signal card filter

---

## Export behavior

### Sales Order Traceability

The export column definitions include:

- `review_signal`
- `review_note`

`review_signal` is visible by default. `review_note` is available but hidden by default.

### Order Material Tracking

The export column definitions include:

- `review_signal`
- `review_note`

`review_signal` is visible by default. `review_note` is available but hidden by default.

---

## Known limitations

- Sales Order Phase 1 does not include reliable procurement follow-up fields, so Supplier Follow-up is intentionally not detected from the Sales Order payload.
- Contribution/profitability watchlist is not included until approved accounting/profit rules are available.
- Review Signals are operational review indicators, not final accounting conclusions.
- Counts depend on the currently filtered dashboard rows.
- Sales Order Review Signals currently count the selected Review Signal filter itself; Order Material Tracking intentionally excludes the selected Review Signal filter when showing the signal mix. This behavior should be reviewed for consistency.
- Healthy means no immediate issue was detected from the exposed fields. It does not guarantee final completion outside the dashboard scope.
- Watchlist may include normal in-progress rows, context rows, or rows that are not yet complete but not clearly problematic.

---

## Phase 2 ideas

- Decide whether Sales Order and Order Material Tracking should use the same Review Signal count behavior when a Review Signal card is selected.
- Add optional backend-side rule tests with small sample fixtures.
- Add trend charts only after the Review Signal logic is stable.
- Add aging analysis for supplier follow-up, invoice follow-up, and delayed delivery if reliable date fields are available.
- Add public-safe screenshots to the portfolio after validation.
