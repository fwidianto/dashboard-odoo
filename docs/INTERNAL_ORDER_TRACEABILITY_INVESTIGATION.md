# Internal Order Traceability Investigation

Investigation date: 2026-06-24

## Purpose

Fix the Internal Order to Sales Order bridge for the manufacturing dashboard.

The issue was that `sale_order.x_studio_io_1` stores numeric approval request IDs in a many-to-many/set-like field, while `approval_product_line.approval_request_id` had been extracted as display text.

## Odoo Metadata Findings

### `sale.order.x_studio_io_1`

Odoo `fields_get` result:

| Property | Value |
| --- | --- |
| Field | `x_studio_io_1` |
| Type | `many2many` |
| Relation model | `approval.request` |
| Stored | `True` |
| Display label | `IO` |

Sample Odoo values:

| SO | Raw value |
| --- | --- |
| `3260261` | `[2277]` |
| `3260319` | `[2277]` |
| `3260218` | `[2831]` |

In PostgreSQL this field appears as set/list text such as `{1081}` or `{1361,1578}`.

### `approval.product.line.approval_request_id`

Odoo `fields_get` result:

| Property | Value |
| --- | --- |
| Field | `approval_request_id` |
| Type | `many2one` |
| Relation model | `approval.request` |
| Required | `True` |
| Display label | `Approval Request` |

Sample Odoo values:

| Approval product line | Raw Odoo value |
| --- | --- |
| `3` | `[14, '225IO001']` |
| `4` | `[15, '225IO002']` |
| `5` | `[16, '125IO003']` |

The extractor stores many2one display names by default, so PostgreSQL previously had only values like `125IO003` and not the numeric `approval.request.id`.

### `approval.request`

Odoo model exists and was synced.

Important fields confirmed:

| Field | Purpose |
| --- | --- |
| `id` | Numeric approval request ID used by `sale_order.x_studio_io_1` |
| `name` | Request/display number |
| `display_name` | Display label |
| `request_status` | Approval status |
| `category_id` | Approval category |
| `request_owner_id` | Requester/owner |
| `create_date` | Created timestamp |
| `write_date` | Updated timestamp |
| `date_confirmed` | Confirmation date |
| `company_id` | Company |

## Extractor Behavior

Current extractor behavior:

- `many2one` fields are stored as display names by default.
- `many2many` fields are stored as set/list text in PostgreSQL.
- Nested paths are supported through `PathResolver`.

Fix applied:

- Added `approval_request_id.id` to `approval.product.line` config.
- Stored it as `approval_request_numeric_id`.
- Optimized `PathResolver` so nested `.id` on Odoo many2one values like `[14, '225IO001']` returns `14` directly without an extra Odoo read.
- Synced `approval.request`.

## Sync Result

Targeted full sync was run for:

| Model | Records synced |
| --- | ---: |
| `approval.product.line` | 42,902 |
| `approval.request` | 2,947 |

New/updated PostgreSQL objects:

| Object | Purpose |
| --- | --- |
| `approval_product_line.approval_request_numeric_id` | Numeric `approval.request.id` behind display field `approval_request_id` |
| `approval_request` | Approval request header table |

## Data Truth Layer Update

Updated mapping:

```text
sale_order.x_studio_io_1 parsed numeric ID
-> approval_product_line.approval_request_numeric_id
-> approval_product_line.approval_request_id display number
```

Updated views:

- `vw_approval_product_line_context`
- `vw_internal_order_context`
- `vw_manufacturing_flow_context`
- `vw_sale_order_internal_order_bridge`
- `vw_dashboard_internal_order_traceability`

Important rule:

Do not infer Internal Order to Sales Order directly from MO.

## Recalculated Results

| Metric | Count |
| --- | ---: |
| `sale_order_internal_order_bridge_rows` | 222 |
| Sales Orders with parsed IO bridge | 211 |
| Distinct parsed Internal Order IDs from SO | 88 |
| Dashboard Internal Orders | 116 |
| Internal Orders with later SO | 88 |
| Internal Orders without later SO | 28 |
| Dashboard `later_so_count` total | 222 |
| Dashboard `accounting_line_count` total | 3,449 |
| `active_so_line_from_internal_order` | 1,026 |

Dashboard traceability status after fix:

| Status | Internal Order count |
| --- | ---: |
| `CANCELLED_RECORD` | 1 |
| `HAS_ACCOUNTING_LINK` | 82 |
| `HAS_MO_NO_FINISHED_GOODS` | 24 |
| `NEW_OR_TO_SUBMIT_NO_MO` | 9 |

Sample successful matches:

| Numeric ID | Internal Order number | Later SO count | Accounting line count |
| ---: | --- | ---: | ---: |
| 14 | `225IO001` | 21 | 114 |
| 15 | `225IO002` | 1 | 15 |
| 16 | `125IO003` | 1 | 46 |
| 25 | `224IO038` | 3 | 38 |
| 74 | `124IO007` | 1 | 119 |

## Remaining Notes

- The SO-to-IO bridge is now many-to-many and working.
- One SO may reference multiple Internal Orders.
- One Internal Order may be referenced by multiple SOs.
- Profitability has not been calculated.
- Frontend has not been built.
- Finished-goods and delivery movement linkage still needs separate review.
