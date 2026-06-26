# Job Order Cost Rekap Excel SQL Comparison

Workbook used: `private_reference/Ceking Project Indokordsa.xlsx`

## 1. Executive Correction

This workbook is an Internal Order case, not a Sales Order / Job Order case.

- Internal Order: `426IO026`
- The related Sales Order does not exist yet for this case
- The previous comparison against SO/JO report keys `4260306` through `4260317` was only a product-overlap clue, not the correct business anchor
- The large gap seen before is expected because the comparison grain was wrong
- This workbook now belongs to [INTERNAL_ORDER_COST_REKAP_DESIGN.md](INTERNAL_ORDER_COST_REKAP_DESIGN.md)
- SO/JO Rekap remains the separate report mode for cases where a Sales Order already exists

## 2. Correct Comparison Grain

- Excel workbook anchor: `426IO026`
- Correct SQL anchor: `internal_order_number = '426IO026'`
- Current SO/JO Rekap views are secondary reference only for this workbook
- Do not force this workbook into the SO/JO report-key family

Rekap sheet consistency check:
- `Rekap` has 473 unique product codes
- 410 of those product codes match the union of current IO-first SQL rows
- 63 workbook codes are not present in the current IO-first SQL rows
- 4 SQL codes are not present in the workbook `Rekap` sheet
- This confirms `Rekap` is a combined IO-level summary layer, not a single SO/JO report-key extract

## 3. IO-first RKB Actual Comparison

SQL query used:
- `vw_rkb_planning_lines` filtered to `internal_order_number = '426IO026'` or `approval_request_id ILIKE '%426IO026%'`

| Metric | Excel `RKB Actual` | SQL `vw_rkb_planning_lines` | Notes |
|---|---:|---:|---|
| Row count | 422 | 426 | SQL has 4 extra rows |
| Unique product codes | 409 | 413 | 409 matched |
| Matched product count | 409 | 409 | Exact code match on every workbook code |
| Excel-only product count | 0 | - | No workbook-only RKB codes |
| SQL-only product count | - | 4 | Sample codes: `38145`, `38147`, `39497`, `42961` |
| Subtotal total | 7,405,532,616.61 | 7,476,666,216.61 | Difference: `+71,133,600.00` |

Notes:
- RKB is the cleanest IO-first match in this case
- Remaining delta is small compared with the earlier wrong-grain gap
- Matched-row subtotal delta is `+91,232,195.94`

## 4. IO-first ROP / PEMBELIAN Comparison

SQL query used:
- `vw_approval_product_line_context` filtered to `approval_business_type = 'ROP_PROCUREMENT_REQUEST'` and `internal_order_number = '426IO026'`

| Metric | Excel `ROP` | SQL `vw_approval_product_line_context` | Notes |
|---|---:|---:|---|
| Row count | 205 | 200 | Excel has 8 extra codes, SQL has 3 extra codes |
| Unique product codes | 183 | 178 | 175 matched |
| Matched product count | 175 | 175 | Good but not perfect code alignment |
| Excel-only product count | 8 | - | Sample codes: `20495`, `20496`, `20555`, `20576`, `20617`, `21416`, `21505`, `21601` |
| SQL-only product count | - | 3 | Sample codes: `38147`, `39497`, `42961` |
| Subtotal total | 6,337,964,369.15 | 6,428,714,005.63 | Difference: `+90,749,636.48` |

Notes:
- ROP is mostly aligned at the product-code level
- The remaining gap is likely a mix of manual workbook lines and slightly different procurement-request linkage
- Matched-row subtotal delta is `+73,465,636.48`

## 5. IO-first PO Comparison

SQL query used:
- `vw_procurement_lines` filtered to `internal_order_number = '426IO026'` or `job_order_number = '426IO026'`

| Metric | Excel `PO` | SQL `vw_procurement_lines` | Notes |
|---|---:|---:|---|
| Row count | 243 | 274 | SQL has more PO lines than the workbook |
| Unique product codes | 172 | 172 | 166 matched |
| Matched product count | 166 | 166 | Code-level overlap is partial |
| Excel-only product count | 6 | - | Sample codes: `25494`, `43891`, `43892`, `43893`, `43894`, `43895` |
| SQL-only product count | - | 6 | Sample codes: `38145`, `38147`, `39497`, `42961`, `43959`, `43963` |
| Subtotal total | 6,211,393,199.27 | 6,314,732,548.20 | Difference: `+103,339,348.93` |

Notes:
- PO is the weakest of the three IO-first comparisons
- This may mean PO is missing from the workbook, differently linked in SQL, or still being handled through an alternate procurement flow
- Matched-row subtotal delta is `-127,716,687.15`

## 6. Sales Order Link Check

Bridge query result:
- `vw_sale_order_internal_order_bridge` returned 0 rows for `426IO026`

Conclusion:
- `426IO026` is currently a pre-SO Internal Order case
- There is no linked Sales Order in the current bridge view

## 7. Implication for Data Model

We need two report modes:

A. Sales Order / Job Order Rekap
- anchored by SO/JO `report_key`
- used only when the Sales Order exists

B. Internal Order Rekap
- anchored by `internal_order_number`
- used for cases like `426IO026`

This workbook belongs to mode B.
Do not force it into mode A.

## 8. Recommendation

- Keep the current SO/JO-first views unchanged
- Create a separate IO-first Rekap design for pre-SO cases
- Before building UI, validate IO-first RKB / ROP / PO mapping for `426IO026`
- Treat the earlier large gap as a grain-selection issue, not a sign that the workbook and SQL are directly comparable at the SO/JO level

Additional note for `426IO026`:
- the earlier ~`7.477B` SQL RKB figure was trackable-only
- the full Odoo RKB Actual total is `9.078B`
- future comparisons should state explicitly whether they use the full total or a trackable-only subset
