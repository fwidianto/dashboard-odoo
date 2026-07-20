# Confirmed SOP Decisions — 20 July 2026

Status: confirmed working baseline for SOP Draft v2 and future dashboard/data-contract changes.

The detailed authority is `SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`.

## Confirmed Decisions

1. Distribusi JO is outside Odoo and may happen before SO Confirm.
2. SO confirmed (`sale`) is the operational approval evidence.
3. Customer Reference and Customer PO Date are mandatory for confirmed SOs from 2026 onward.
4. Fulfilment source is determined per SO line; mixed source must be represented as `MIXED_SOURCE`.
5. IO-backed SO may create an MO that is automatically cancelled; classify it as `MO_SUPPRESSED_BY_IO`.
6. ROP to RFQ/PO is a custom user-triggered Server Action.
7. PO confirmed is the official operational approval evidence.
8. Reset to Draft is correction, not cancellation, and may leave downstream open.
9. Reset/Unlock requires reason, approval, affected-document review, and closing Log Note.
10. Cancellation is successful only when final state becomes `cancel`.
11. Completed downstream documents remain historical evidence; open/partial/reserved/backorder records require resolution or approved exception.
12. `CANCELLED_PO_WITH_OPEN_RECEIPT` is an anomaly; none was found among 348 cancelled POs from 2026 onward.
13. Cancelling Receipt does not cancel PO; cancelling Delivery does not cancel SO.
14. IO administrative state is not operational production progress.
15. IO Production and Utilization statuses are provisional and retain `DATA_EXCEPTION` where allocation/product/UoM evidence is unsafe.
16. Production is hybrid Odoo/manual; MO Done is not proof of every physical/QC step.
17. Native IDs and relation tables outrank display/document text.
18. Automation-derived helper fields are secondary evidence.
19. Payment truth uses invoice residual and reconciliation, not copied SO fields.
20. Accounting labels, adjustment treatment, DP, overpayment, and management payment date remain open.

## Approved Exception Vocabulary

- `MO_SUPPRESSED_BY_IO`
- `MIXED_SOURCE`
- `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM`
- `RESET_TO_DRAFT_WITH_OPEN_RECEIPT`
- `RESET_TO_DRAFT_WITH_DRAFT_VENDOR_BILL`
- `CANCEL_BLOCKED_OR_FAILED`
- `ACTION_APPLIED_WITH_RPC_ERROR`
- `CANCELED_PARENT_WITH_OPEN_DOWNSTREAM`
- `CANCELED_PARENT_WITH_DONE_DOWNSTREAM`
- `CANCELED_PARENT_WITH_RESERVED_STOCK`
- `CANCELED_PARENT_WITH_PARTIAL_BACKORDER`
- `CANCELLED_PO_WITH_OPEN_RECEIPT`
- `CANCELLED_SO_WITH_ACTIVE_DOWNSTREAM`
- `IO_PRODUCTION_DATA_EXCEPTION`
- `IO_UTILIZATION_DATA_EXCEPTION`
- `AUTOMATION_EFFECT_UNCONFIRMED`

## Dashboard Implementation Gate

These decisions are authoritative for documentation and data-contract planning, but they do not authorize immediate SQL/API/UI implementation. Implementation starts after SOP Draft v2 and remaining owner decisions are approved.
