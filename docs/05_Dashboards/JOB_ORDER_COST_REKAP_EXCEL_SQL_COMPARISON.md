# Job Order Cost Rekap Excel SQL Comparison

Workbook used: `private_reference/Ceking Project Indokordsa.xlsx`

## Report Key Detection

The workbook does not resolve to one clean SQL `report_key`.

Confirmed workbook context values:
- Internal Order: `426IO026`
- Job Order / SO reference visible in the workbook: `20830`
- Approval Request IDs visible in the workbook: `100602271`, `100602273`

SQL-side match:
- Representative SQL report key exists: `4260314`
- Best matching SQL family by item-code overlap: `4260306` through `4260317`
- Comparison below uses the aggregated SQL family because the workbook is a project-level rollup, not a single report-key extract

Why this matters:
- `vw_job_order_rekap_summary` is keyed per report key
- the workbook combines multiple report keys under the same IO context
- the same product code can appear under several SQL report keys, so a strict one-to-one comparison is not valid yet

## Summary Comparison

Excel summary values are from `Rekap 2`.
SQL values are the aggregate of report keys `4260306`-`4260317` from `vw_job_order_rekap_summary`.

| Field | Excel | SQL family | Diff | Diff % | Notes |
|---|---:|---:|---:|---:|---|
| RKB Actual total | 8,866,942,305.61 | 6,772,018,085.43 | -2,094,924,220.18 | -23.63% | Direct phase-1 compare |
| ROP amount | 6,337,964,369.15 | 6,265,492,137.88 | -72,472,231.27 | -1.14% | Closest operational match |
| PO amount total | 6,227,809,824.12 | 3,489,204,336.00 | -2,738,605,488.12 | -43.97% | SQL PO is materially lower |
| Not Yet ROP amount | 242,374,833.33 | 1,244,045,034.36 | +1,001,670,201.03 | +413.27% | Large gap; likely scope/mapping gap |
| Excess amount | 157,704,866.21 | 742,051,765.81 | +584,346,899.60 | +370.53% | Large gap; likely scope/mapping gap |
| Received Qty | 0.008732 | 0.000000 | -0.008732 | -100.00% | UoM/product grain may differ |

Excel-only or manual fields with no direct phase-1 SQL equivalent yet:
- Total Job Order / SO value: `13,401,200,000`
- Budget Estimator: `8,997,813,000`
- RKB PPIC Budget: `7,284,965,499.90`
- Saving: `501,184,305.62`
- Amount sesuai qty ROP: `5,836,350,063.53`

SQL summary row existence check:
- `vw_job_order_rekap_summary` has a row for representative report key `4260314`
- that single row is only a slice of the workbook, so it is not the right rollup for the full Excel report

## Item-Level Comparison Samples

Across the workbook `Rekap` sheet:
- item rows start at row 5
- 473 unique product codes were parsed
- 235 product codes match the current SQL family exactly
- 238 product codes do not match this SQL family
- 178 matched product codes appear in multiple SQL report keys, which confirms the workbook is a rolled-up project view

| Excel product / reference | SQL match | Status | Excel RKB Actual subtotal | SQL RKB Actual subtotal | Excel ROP subtotal | SQL ROP subtotal | Excel PO subtotal | SQL PO subtotal | Notes |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `43809` / `[43809] ACB 3P 100KA ...` | `4260314` / `4260317` | MATCHED_EXACT | 390,074,158 | 390,074,158 | 390,074,158 | 390,074,158 | 390,074,158 | 0 | Product matches exactly; PO is not populated in current SQL family |
| `43816` / `[43816] ACB 3P 100KA ...` | `4260310` / `4260312` | MATCHED_EXACT | 303,896,708 | 303,896,708 | 303,896,708 | 303,896,708 | 310,706,780 | 0 | Exact product match; PO gap remains |
| `43804` / `[43804] ACB 3P 66KA ...` | `4260306` / `4260316` | MATCHED_EXACT | 580,114,016 | 580,114,016 | 580,114,016 | 580,114,016 | 580,114,016 | 0 | Excel PO is manual/planned; SQL PO not present here |
| `43802` / `[43802] ACB 3P 66KA ...` | `4260312` | MATCHED_EXACT | 91,931,938 | 91,931,938 | 91,931,938 | 91,931,938 | 91,931,938 | 0 | Exact product match; PO not yet linked in SQL family |
| `43803` / `[43803] ACB 3P 66KA ...` | `4260311` / `4260312` | MATCHED_EXACT | 130,030,660 | 130,030,660 | 130,030,660 | 130,030,660 | 143,033,752 | 0 | RKB/ROP align; PO subtotal is workbook-only for this product |

Practical read on the item comparison:
- RKB Actual and ROP are mostly aligned on the exact product rows shown above
- PO is the main mismatch area in the current SQL family
- many workbook rows likely carry manual or cross-reference values that are not yet surfaced through `vw_procurement_lines`

## Conclusion

The Excel workbook is not a clean one-report-key snapshot in the current SQL grain.

Current state:
- SQL is good enough to match many RKB Actual and ROP item rows exactly
- SQL PO coverage is still incomplete relative to the workbook
- workbook-level summary totals do not match a single SQL report key
- the safest interpretation is that the workbook is a higher-level IO/project rollup built from multiple SQL report keys

Recommendation:
- keep the current conservative SQL mapping
- do not force a one-key comparison yet
- use the workbook as a reference for future IO-level rollup and PO mapping review
