# Sales Order Review Signals

## Purpose

Review Signals add a compact operational review layer to the Sales Order Traceability dashboard. The signals summarize which filtered Sales Orders look complete, which should be monitored, and which need business review based only on fields already exposed by the Sales Order dashboard API.

This is a frontend Phase 1 feature. It does not change SQL, backend calculations, or the source dashboard data contract.

## Page Scope

Implemented page:

```text
/dashboard/sales-orders
src/static/dashboard/sales-orders.html
src/static/dashboard/sales-orders.js
src/static/dashboard/sales-orders.css
```

The Review Signals section appears after the main KPI grid and before the filter panel. Counts and mix bars are recalculated from the currently filtered rows.

## Fields Used

The Phase 1 mapping uses existing Sales Order dashboard row fields only:

| Field | Use |
| --- | --- |
| `follow_up_status` | Primary signal source. |
| `source_type` | Source relationship check when source is unknown. |
| `is_cancelled` | Excludes cancelled rows from active review signal counts. |
| Existing contribution fields | Displayed elsewhere as context only; not used as a Review Signal rule in Phase 1. |

No payment, outstanding payment, AR, or supplier procurement status is inferred.

## Rule Mapping

| Review Signal | Rule | Review Note |
| --- | --- | --- |
| Healthy | `follow_up_status = COMPLETED` | Delivery and invoice review complete. |
| Needs Review | `follow_up_status = DELAYED_DELIVERY` | Delivery is delayed and needs review. |
| Needs Review | `follow_up_status = UNKNOWN_SOURCE` or `source_type = UNKNOWN_SOURCE` | Source relationship needs checking. |
| Operational Follow-up | `follow_up_status = WAITING_PRODUCTION` | Manufacturing follow-up is required. |
| Operational Follow-up | `follow_up_status = WAITING_DELIVERY` | Delivery/fulfillment follow-up is required. |
| Watchlist | `follow_up_status = WAITING_INVOICE` | Invoice pending after fulfillment progress. |
| Watchlist | Active row with no stronger Phase 1 signal | In progress; monitor until complete. |
| Excluded | Cancelled Sales Order | Cancelled Sales Order is excluded from active review counts. |

## Known Exclusions

- Supplier Follow-up count remains zero in Phase 1. The current Sales Order dashboard payload does not expose a reliable procurement follow-up field that can support this signal without inference.
- Payment and outstanding payment logic are not implemented because the current API metadata says `accounting_ar_included` is false.
- Contribution watchlist logic is not implemented in Phase 1. Existing contribution fields are useful review context, but the API metadata marks them as not approved accounting profit rules.
- No SQL files, dashboard views, or core business calculations are changed.

## Phase 2 Suggestions

- Add Supplier Follow-up only after a reliable procurement field or joined procurement review payload is available.
- Add payment/AR review only after the dashboard API explicitly includes accounting receivable fields and metadata.
- Define approved contribution watchlist thresholds with Finance/Operations before deriving contribution-based signals.
- Consider adding a Review Signal filter once the signal taxonomy is stable and accepted by users.
