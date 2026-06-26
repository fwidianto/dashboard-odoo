# Dashboard Business Review

## 1. Review Scope

This review treats the V1 Data Truth Layer and business mappings as correct.

Reviewed dashboard:

```text
Internal Order Traceability Dashboard
```

Review perspectives:

- VP Operations
- PPIC Manager
- Procurement Manager

Out of scope:

- SQL changes
- API changes
- New business relationships
- Profitability

## 2. Dashboard Strengths

- Gives one place to see Internal Order progress from IO to MO, SO, delivery, invoice, procurement, and accounting linkage.
- Uses operationally understandable statuses such as `HAS_MO_NO_SO_YET`, `HAS_DELIVERED_SO`, and `HAS_ACCOUNTING_LINK`.
- KPI cards quickly show whether IOs are moving through manufacturing, sales, delivery, invoicing, and procurement.
- Filters by date, IO number, requester, status, and traceability status support daily follow-up work.
- Expandable diagnostics keep proof fields available without forcing every user to read raw traceability details.

## 3. Dashboard Weaknesses

- The current main table has too many quantity columns for executive scanning.
- Procurement quantities beside sales quantities can confuse users if the page is read as one linear workflow.
- Accounting line count is useful as proof of linkage, but it can be mistaken for paid, posted revenue, or AR collection.
- Product Count is useful for complexity, but not enough for product-level decisions without drill-down.
- Delivery and invoice percentages are more useful than raw ordered/delivered/invoiced quantities for the main table.

## 4. Recommended KPI Cards

### Keep Prominent

| KPI Card | Main Audience | Why Useful |
| --- | --- | --- |
| Active IO | VP Operations, PPIC | Shows active workload. |
| With MO | VP Operations, PPIC | Shows manufacturing conversion. |
| With SO | VP Operations, Sales/Ops | Shows whether produced/internal stock has later demand. |
| Delivered | VP Operations | Shows customer fulfillment progress. |
| Invoiced | VP Operations, Finance | Shows commercial completion after delivery. |
| Delivery Progress % | VP Operations | Best high-level fulfillment health metric. |
| Invoice Progress % | VP Operations, Finance | Best high-level billing health metric. |
| PO Receipt % | Procurement | Shows supplier receipt completion. |
| PO Billing % | Procurement, Finance | Shows vendor billing completion. |

### Consider Renaming

| Current KPI | Recommended Label | Reason |
| --- | --- | --- |
| Delivered | IOs Delivered | Makes clear this is a count of IOs with delivered SO quantity. |
| Invoiced | IOs Invoiced | Makes clear this is a count of IOs with invoiced SO quantity. |
| PO Receipt | Procurement Receipt % | Avoids sounding like number of receipts. |
| PO Billing | Procurement Billing % | Avoids sounding like number of bills. |

### Keep Out of KPI Cards

| Metric | Reason |
| --- | --- |
| Accounting Line Count | Too technical for a top card; better as status or diagnostic. |
| Product Count | Useful per row, not as top management KPI. |
| Stock Movement Counts | Optional diagnostics only. |

## 5. Recommended Main-Table Columns

Recommended main table should support fast follow-up, not full audit proof.

| Column | Keep? | Reason |
| --- | --- | --- |
| Internal Order Number | Yes | Primary identifier. |
| Traceability Status | Yes | Main action/status signal. |
| Status | Yes | Shows source approval/workflow status. |
| Requester | Yes | Helps assign follow-up. |
| Need Date | Yes | Helps prioritize. |
| Product Count | Yes | Indicates complexity. |
| MO Count | Yes | PPIC/manufacturing progress. |
| SO Count | Yes | Shows later customer linkage. |
| Delivery % | Yes | Better than raw delivered quantity for scanning. |
| Invoice % | Yes | Better than raw invoiced quantity for scanning. |
| Receipt % | Yes | Procurement progress. |
| Billing % | Yes | Procurement billing progress. |

## 6. Diagnostic-Only Columns

Move these into row expansion or detail drawer by default.

| Column | Why Diagnostic Only |
| --- | --- |
| SO Ordered Qty | Useful proof, but makes the main table wide. |
| SO Delivered Qty | Use Delivery % in main table; keep raw qty in detail. |
| SO Invoiced Qty | Use Invoice % in main table; keep raw qty in detail. |
| PO Ordered Qty | Use Receipt/Billing % in main table; keep raw qty in detail. |
| PO Received Qty | Useful for procurement drill-down, not top-level scan. |
| PO Invoiced Qty | Useful for procurement/finance drill-down. |
| Accounting Lines | Technical proof field; show in detail and/or status tooltip. |
| SO Line Count | Explains aggregation only. |
| SO Amount | Revenue traceability only; can be misread as profitability. |
| Delivery Status Summary | Useful Odoo context, but verbose. |
| Invoice Status Summary | Useful Odoo context, but verbose. |
| Linked PO Line Count | Explains procurement aggregation only. |
| Purchase Status Summary | Useful PO context, but verbose. |
| IO Line Count | Explains source aggregation only. |
| Manufacturing Movement Count | Optional operational diagnostic. |
| Finished Goods Store Count | Optional operational diagnostic. |
| Delivery Movement Count | Optional operational diagnostic. |

## 7. Columns To Remove From Default View

No field should be deleted from the system yet. For V1 usability, remove these from the default visible table and keep them only in diagnostics:

- Raw SO quantities
- Raw PO quantities
- Accounting line count
- Stock movement counts
- Source line counts
- Odoo status summaries other than the main `Status` and `Traceability Status`

## 8. Suggested Dashboard Layout

Recommended layout order:

1. KPI cards grouped by business area:
   - Operations: Active IO, With MO, With SO
   - Sales fulfillment: IOs Delivered, IOs Invoiced, Delivery Progress %, Invoice Progress %
   - Procurement: Procurement Receipt %, Procurement Billing %
2. Follow-up status strip:
   - Accounting linked
   - Invoiced SO
   - Delivered SO
   - Linked SO
   - MO no SO yet
   - New/no MO
   - Review/no MO
3. Filters:
   - Date range
   - IO number
   - Requester
   - Status
   - Traceability status
4. Main table:
   - IO identity and ownership
   - lifecycle counts
   - progress percentages
   - traceability status
5. Expandable diagnostics:
   - raw quantities
   - accounting line count
   - PO/SO line counts
   - stock movement diagnostics

## 9. Follow-Up Actions Users Can Take

| Dashboard Signal | Suggested User Action |
| --- | --- |
| `NEW_OR_TO_SUBMIT_NO_MO` | PPIC checks whether the IO should be submitted, cancelled, or ignored as old work. |
| `OLD_OR_UNLINKED_NO_MO` | PPIC/Operations reviews whether MO is missing or the IO is abandoned/migration data. |
| `HAS_MO_NO_SO_YET` | Operations/Sales checks whether produced stock is awaiting customer SO. |
| `HAS_LINKED_SO` with 0 delivery | Operations checks delivery schedule or fulfillment blocker. |
| Delivered but not invoiced | Finance/Sales Admin checks invoice creation. |
| PO receipt below 100% | Procurement follows up supplier receipt. |
| PO billing below 100% | Procurement/Finance checks vendor bill status. |
| Accounting linked | Treat as traceability complete for V1; profitability review comes later. |

## 10. Business-User Feedback Summary

### VP Operations

The dashboard is useful as a high-level flow monitor. The VP view should emphasize workload, conversion to MO/SO, delivery completion, invoice completion, and follow-up statuses. Raw SO/PO quantities should be secondary.

### PPIC Manager

The dashboard is useful for checking whether Internal Orders became MOs and whether produced stock later connects to SO. PPIC needs IO number, status, requester, need date, product count, MO count, SO count, and follow-up status. Stock movement diagnostics can stay expandable.

### Procurement Manager

The dashboard is useful only if procurement metrics are clearly labeled as procurement progress, not sales progress. Procurement needs receipt and billing percentages in the main view, with raw PO quantities and PO line counts in diagnostics.

## 11. Implemented UI Simplification

The Internal Order Traceability Dashboard main table was simplified for quick operational review.

Kept in the default main table:

- IO Number
- Status
- Product Count
- MO Count
- SO Count
- Delivery %
- Invoice %
- Receipt %
- Billing %
- Traceability Status

Moved into expandable diagnostics:

- Requester
- Need Date
- Accounting Lines
- Raw SO ordered/delivered/invoiced quantities
- Raw PO ordered/received/invoiced quantities
- SO/PO/IO line counts
- Odoo delivery, invoice, and purchase status summaries
- Stock movement diagnostics

KPI cards and filters were intentionally left unchanged.

## 12. Recommendation

Keep the simplified V1 dashboard and review it with business users before wider rollout.

Next UX review:

```text
Confirm whether the simplified main table is enough for daily operations.
Confirm whether diagnostics contain enough proof fields for follow-up.
Only after acceptance, decide the first drill-down.
```

Do not start profitability until business users accept the simplified traceability page.
