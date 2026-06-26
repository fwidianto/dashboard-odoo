# Job Order Cost Rekap Validation

## Validation Date

2026-06-26

## SQL Files Executed

Executed locally against the PostgreSQL database configured by `.env`:

1. `sql/01_base_views.sql`
2. `sql/04_dashboard_traceability_views.sql`
3. `sql/05_sales_order_dashboard_views.sql`
4. `sql/06_job_order_cost_rekap_views.sql`

Execution method:

```text
Python + psycopg2 using POSTGRES_* settings from .env
```

`psql` was not available on PATH, so the project virtualenv database driver was used instead.

## SQL Execution Result

Status: passed.

No SQL execution errors were encountered, and no SQL fixes were required.

## Validation Results

| Check | Result |
| --- | ---: |
| `vw_job_order_rekap_lines` row count | 29,464 |
| `vw_job_order_rekap_summary` row count | 1,100 |
| Duplicate `report_key + product_key` rows | 0 |
| Unmapped RKB Actual rows | 5,606 |
| Unmapped ROP / PEMBELIAN rows | 6,473 |
| Unmapped PO rows | 10,688 |
| Mixed UoM rows | 124 |
| PO without ROP rows | 1,934 |
| ROP without PO rows | 1,402 |
| Cancelled rows in report scope | 0 |

## SQL Errors Fixed

None.

## Notes

- Duplicate grain check passed with 0 duplicate `report_key + product_key` groups.
- Cancelled record exclusion passed with 0 invalid scope rows.
- Unmapped RKB Actual, ROP/PEMBELIAN, and PO counts are expected review items because Phase 1 intentionally maps SO/JO-first and only uses Internal Order as linked secondary context.
- Mixed UoM rows require business/data review before quantity comparisons are treated as final.
- PO without ROP and ROP without PO rows are operational follow-up buckets, not SQL failures.

## Remaining Risks / TODOs

- Confirm whether SO number and JO number are always the same in the target report.
- Confirm product key strategy across SO, RKB Actual, ROP/PEMBELIAN, and PO.
- Review unmapped RKB Actual, ROP/PEMBELIAN, and PO rows to determine whether additional safe mapping rules are needed.
- Review mixed UoM rows before using quantity comparisons for production reporting.
- Validate output against at least one known manually prepared Excel report.
- Add future RKB PPIC upload/staging only after the manual PPIC file structure is confirmed.
