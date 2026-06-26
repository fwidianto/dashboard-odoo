# Sales Order Dashboard Concept

## 1. Business Purpose

Sales Order is the primary business entity for the next dashboard concept.

The Sales Order Traceability Dashboard should answer:

- Which Sales Orders exist?
- What is the source of fulfillment?
- Which SOs came from Internal Order stock?
- Which SOs require new production / JO?
- Which SOs are fulfilled from stock?
- Which SOs are delivered?
- Which SOs are invoiced?
- Which SOs have accounting linkage?

This dashboard is traceability-only. It must not calculate profitability.

## 2. SO Source Classification

| Source Type | Business Meaning |
| --- | --- |
| `FROM_STOCK` | SO is fulfilled from available stock without IO/MO evidence. |
| `FROM_INTERNAL_ORDER` | SO is linked to Internal Order through `sale_order.x_studio_io_1`; no new MO should be needed for this SO. |
| `MAKE_TO_ORDER (JO)` | SO requires new production. JO means Job Order, which is factory terminology for a production-required SO. |

At SO level, if different lines have different source types, show:

```text
MIXED_SOURCE
```

## 3. KPI Cards

Recommended top KPI cards:

| KPI Card | Business Meaning |
| --- | --- |
| Active Sales Orders | Count of active SOs. |
| SO From Stock | SOs classified as `FROM_STOCK`. |
| SO From Internal Order | SOs classified as `FROM_INTERNAL_ORDER`. |
| SO Make To Order / JO | SOs classified as `MAKE_TO_ORDER (JO)`. |
| Mixed Source SO | SOs with multiple source types across lines. |
| Delivered SO | SOs with delivered quantity. |
| Invoiced SO | SOs with invoiced quantity. |
| Delivery Progress % | Total delivered quantity / total ordered quantity. |
| Invoice Progress % | Total invoiced quantity / total ordered quantity. |
| Accounting Linked SO | SOs with accounting line linkage. |

## 4. Filters

Recommended filters:

| Filter | Purpose |
| --- | --- |
| Date Range | Filter by SO date/order date. |
| Sales Order Number | Search specific SO. |
| Customer | Find SO by partner/customer. |
| Source Type | Filter `FROM_STOCK`, `FROM_INTERNAL_ORDER`, `MAKE_TO_ORDER (JO)`, `MIXED_SOURCE`, or unknown. |
| Delivery Status | Focus on not delivered, partially delivered, delivered. |
| Invoice Status | Focus on not invoiced, partially invoiced, invoiced. |
| Internal Order Number | Find SOs linked to a specific IO. |
| MO / JO Reference | Find production-required SOs. |
| Traceability Status | Filter follow-up statuses. |

## 5. Main Table Columns

Recommended default columns:

| Column | Business Meaning |
| --- | --- |
| SO Number | Primary business document. |
| Customer | Customer/partner. |
| SO Date | Order date. |
| Source Type | `FROM_STOCK`, `FROM_INTERNAL_ORDER`, `MAKE_TO_ORDER (JO)`, `MIXED_SOURCE`, or unknown. |
| IO Count | Number of linked Internal Orders, if any. |
| MO Count | Number of linked Manufacturing Orders, if any. |
| Ordered Qty | Total SO ordered quantity. |
| Delivered Qty | Total delivered quantity. |
| Invoiced Qty | Total invoiced quantity. |
| Delivery % | Delivery progress. |
| Invoice % | Invoice progress. |
| Accounting Lines | Accounting linkage count or yes/no flag. |
| Traceability Status | Main follow-up status. |

For executive usability, raw quantities can later move into diagnostics if the table becomes too wide. Percentages and source type should stay prominent.

## 6. Drill-Down Sections

Each SO row should open a detail view with:

### SO Lines

- Product
- Ordered quantity
- Delivered quantity
- Invoiced quantity
- Line source classification
- Line status/follow-up note

### Internal Order Links

Show only when SO source includes `FROM_INTERNAL_ORDER`.

- Internal Order number
- IO status
- IO requester
- IO needed date
- Linked MO count
- Link back to Internal Order Traceability Dashboard

### Manufacturing / JO

Show when SO source includes `MAKE_TO_ORDER (JO)`.

- MO number
- MO status
- Product
- Planned/produced quantity
- JO / production SO reference

### Delivery

- SO delivery status
- Delivered quantity
- Remaining delivery quantity
- Optional delivery movement diagnostics only

### Invoice

- SO invoice status
- Invoiced quantity
- Remaining invoice quantity

### Accounting

- Accounting line count
- Accounting linkage status
- Do not classify revenue, AR, COGS, or margin yet

## 7. Relationship To Internal Order Dashboard

The Internal Order Dashboard remains useful for production planning and IO lifecycle review.

The Sales Order Dashboard should become the main business dashboard because SO is the customer-facing demand and revenue document.

Navigation relationship:

| From | To | Purpose |
| --- | --- | --- |
| Sales Order Dashboard | Internal Order Dashboard | Review IO-backed SO supply history. |
| Internal Order Dashboard | Sales Order Dashboard | See which customer SO later consumed IO-produced stock. |

The Sales Order Dashboard should not replace the Internal Order Dashboard. It should sit above it as the business-facing entry point.

## 8. Navigation Flow

User navigation should support:

```text
Sales Order
-> Internal Order
-> Manufacturing Order
-> Delivery
-> Invoice
-> Accounting
```

Expected examples:

- `FROM_INTERNAL_ORDER`: SO -> IO -> MO -> Delivery -> Invoice -> Accounting
- `MAKE_TO_ORDER (JO)`: SO / JO -> MO -> Delivery -> Invoice -> Accounting
- `FROM_STOCK`: SO -> Delivery -> Invoice -> Accounting

## 9. Suggested Traceability Status

Recommended SO-level statuses:

| Status | Meaning |
| --- | --- |
| `HAS_ACCOUNTING_LINK` | SO has accounting line linkage. |
| `HAS_INVOICED_QTY` | SO has invoiced quantity. |
| `HAS_DELIVERED_QTY` | SO has delivered quantity. |
| `HAS_MO_NOT_DELIVERED` | SO has production link but no delivery yet. |
| `HAS_IO_NOT_DELIVERED` | SO is linked to IO but no delivery yet. |
| `FROM_STOCK_NOT_DELIVERED` | SO appears stock-sourced but not delivered. |
| `UNKNOWN_SOURCE` | Source classification is unclear. |
| `CANCELLED_RECORD` | Cancelled SO; exclude from active KPI cards. |

## 10. Implementation Note

Do not implement this dashboard yet.

Before implementation, confirm whether an SO-level dashboard view already exists or whether a new view is needed from existing traceability views. Do not change the Data Truth Layer until implementation is explicitly requested.
