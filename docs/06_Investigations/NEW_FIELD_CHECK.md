# New Field Check

Check date: 2026-06-23

## Summary

Both requested new fields exist in the current PostgreSQL extract.

| Field | Found | Data type | Notes |
| --- | --- | --- | --- |
| `approval_product_line.x_studio_category` | Yes | `text` | Used for RKB/ROP classification. |
| `stock_move_line.picking_type_id` | Yes | `text` | Already extracted as display labels, not numeric IDs. |

No other extracted table currently contains a `picking_type_id` column.

## Approval Category Values

Current top values from `approval_product_line.x_studio_category`:

| Value | Count |
| --- | ---: |
| `RKB` | 27,433 |
| `PEMBELIAN` | 14,392 |
| `MANUFACTURE` | 1,024 |
| `INTERNAL USE` | 50 |
| null | 24 |

Important: no literal `ROP` value was found in the current extract. The business confirmed that `PEMBELIAN` and `ROP` mean the same thing, so `PEMBELIAN` is classified as `ROP_PROCUREMENT_REQUEST`.

## Picking Type Values

`stock_move_line.picking_type_id` is a text display label. Examples:

| Value | Count |
| --- | ---: |
| `NPA - Karawang: Manufacturing` | 67,373 |
| `NPA - Karawang: Pick Components KRW` | 45,894 |
| `NPA - JKT - FF5: Manufacturing` | 37,207 |
| null | 23,233 |
| `NPA - JKT - FF5: Pick Components FF5 (jgn ubah²)` | 13,072 |
| `NPA - Karawang: Receipts` | 9,376 |
| `NPA - JKT - FF5: Receipts` | 8,326 |
| `NPA - Karawang: Delivery Orders` | 7,959 |
| `NPA - Karawang: Store Finished Product` | 7,574 |
| `NPA - Karawang: Internal Transfers` | 3,150 |

Because this field is a text label, the Data Truth Layer can classify movement type by keywords. A stock picking type master table would still be useful later for stable IDs, warehouse, operation type, and localization-safe classification.
