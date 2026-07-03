# Order Material Tracking Business Rules

Last updated: 2026-07-03

## Purpose

This document captures the business interpretation for Order Material Tracking before the Review Signals rules are revised again.

The goal is to avoid treating normal business behavior as an exception. Review Signals should support management review, purchasing follow-up, and operational interpretation, not create false alarms.

## Core Material Flow

Order Material Tracking compares and reconciles the material/procurement chain around:

```text
RKB -> ROP -> PO -> Receipt
```

Business meaning:

| Term | Meaning |
| --- | --- |
| RKB | PPIC/material planning reference. It is useful for cost/kontribusi comparison, but it does not directly force purchasing quantity. |
| ROP / PEMBELIAN | Procurement request / request of purchase. This is the purchasing trigger that PO should normally follow. |
| PO | Purchase order to supplier. PO should follow ROP quantity, but may be higher because of supplier minimum order quantity (MOQ). |
| Receipt | Material received against PO. Receipt progress is useful for supplier/material follow-up. |

## RKB vs ROP Rule

ROP does not need to exactly follow RKB.

Do not classify a row as an exception only because:

- ROP quantity differs from RKB quantity.
- ROP amount differs from RKB amount.
- RKB exists but ROP does not exist yet.

RKB-only rows should normally be treated as watchlist/context for gross profit or kontribusi comparison, not as purchasing errors.

Recommended note:

```text
RKB only; monitor for contribution comparison and later procurement progress if purchasing is required.
```

## ROP vs PO Quantity Rule

PO should follow ROP quantity, but PO may be higher than ROP because of Minimum Order Quantity (MOQ) or supplier packaging rules.

| Condition | Business Interpretation | Recommended Signal |
| --- | --- | --- |
| PO Qty = ROP Qty | Normal purchasing match. | Healthy or Watchlist depending receipt status. |
| PO Qty > ROP Qty | Normal/acceptable when caused by MOQ or supplier packaging. Keep as notice, not exception. | Watchlist / Notice |
| PO Qty < ROP Qty | Purchasing may not fully cover the requested quantity. | Supplier Follow-up |

Recommended notes:

```text
PO Qty is above ROP, possibly due to MOQ or supplier packaging.
PO Qty is less than ROP; follow up with Purchasing.
```

## ROP Without PO

If ROP exists but PO is not created yet, this should be treated as a purchasing follow-up item.

Recommended signal:

```text
Supplier Follow-up
```

Recommended note:

```text
ROP exists but PO is not created yet; follow up with Purchasing.
```

## PO Without ROP

PO without ROP is not automatically an error.

Possible normal reasons:

- Discount line.
- Service / jasa line.
- Additional charge.
- Manual or urgent purchase.
- Non-RKB / non-ROP item that still belongs to the transaction.

Recommended treatment:

- Do not classify as Needs Review by default.
- Treat as Watchlist or Operational Follow-up depending item type.
- Use a neutral note so the user can understand why it appears.

Recommended note:

```text
PO exists without ROP; may be service, discount, manual purchase, or non-RKB item.
```

## From Stock Rule

A row planned from stock should not automatically be marked Healthy.

Reason:

The dashboard does not yet have reliable available-stock correlation per project/order. "From Stock" means the current plan/source path points to stock, not that stock availability is fully validated for this project.

Recommended signal:

```text
Watchlist
```

Recommended note:

```text
Planned from stock; stock availability is not yet project-correlated.
```

## Mixed UoM Rule

Mixed UoM should not automatically be Needs Review in Phase 1.

Company rule expects users to use the same UoM, so UoM inconsistency can be shown as a prevention notice. It should not override stronger business conditions such as Supplier Follow-up.

Recommended signal:

```text
Watchlist / Notice
```

Recommended note:

```text
UoM inconsistency detected; company rule expects same UoM.
```

## Product Classification Rules

Product classification should be separated from Review Signal severity.

Recommended business classes:

| Class | Meaning | Review Treatment |
| --- | --- | --- |
| Product Item | Real material/product item that can be followed through RKB, ROP, PO, and Receipt. | Eligible for material-readiness and supplier follow-up rules. |
| Non-Product / Service Item | Service or operational cost item, often represented in RKB as an "Others" product line. | Not a material error. Use operational/context note if needed. |
| Transactional Line | Discount, additional charge, admin charge, rounding, price adjustment, or similar transaction adjustment. | Exclude from material readiness exceptions. |
| Unknown / Unclassified | Row cannot yet be confidently classified. | Watchlist only; check only if it affects material review. |

Important:

- Unknown product classification should not automatically be Needs Review.
- Discount and additional-charge style rows should be classified as Transactional Line when possible, not as material errors.
- Non-product/service rows are not automatically errors.

Recommended notes:

```text
Transactional line; excluded from material readiness review.
Non-product/service row; review operational meaning only if needed.
Item type is not classified yet; check only if it affects material review.
```

## Unknown Source Rule

Unknown Source should not automatically be Needs Review.

A row with unknown source may be:

- A transactional line.
- A service/non-product row.
- A reconciliation row preserved by the query.
- A real data-linking issue.

Recommended treatment:

- If it is a transaction/service/non-material row, do not treat it as material exception.
- If it is a product item and source path is unclear, use Watchlist first.
- Only elevate later if real examples prove it is a broken relationship.

Recommended note:

```text
Source path is unclear; verify only if this is a real material item.
```

## Zero Quantity / Zero Amount Rows

If all material quantities are zero, do not automatically classify as Needs Review.

Interpretation depends on amount and item type:

| Case | Treatment |
| --- | --- |
| Qty = 0 and amount = 0 | Likely empty/non-material row; exclude from material review if possible. |
| Qty = 0 but amount exists | Classify based on item type: transactional line, service/non-product item, or unknown. |
| Qty exists but chain is incomplete | Apply normal RKB/ROP/PO/receipt rules. |

Recommended note for empty rows:

```text
Empty quantity/amount row; excluded from material review.
```

## Revised Review Signal Direction

Recommended Phase 1 target after this clarification:

| Signal | Meaning |
| --- | --- |
| Healthy | Use sparingly. Only when material coverage is reasonably clear, such as PO received. Do not mark From Stock as Healthy until stock availability can be project-correlated. |
| Watchlist | Normal in-progress or context rows: RKB only, PO above ROP due to MOQ, From Stock plan, PO without ROP when it may be service/discount/manual item, Mixed UoM notice. |
| Supplier Follow-up | Purchasing action likely needed: ROP without PO, PO Qty less than ROP, PO not received, partially received PO. |
| Operational Follow-up | Process/context review: Pre-SO Internal Order, non-product/service operational row, unclear source for real material item. |
| Needs Review | Keep very limited. Use only for truly broken material relationships after actual examples are validated. Do not use for normal quantity/amount differences. |

## Rules to Avoid

Do not classify these as Needs Review by default:

- ROP amount differs from RKB amount.
- ROP quantity differs from RKB quantity.
- PO amount differs from ROP amount.
- PO quantity is higher than ROP quantity.
- PO without ROP.
- Mixed UoM.
- From Stock.
- Unknown product classification.
- Discount/additional-charge/transactional rows.

## Development Notes

Before revising `deriveReviewSignal(row)` for Order Material Tracking:

1. Inspect examples for unknown product classification, unknown source path, and zero-quantity rows.
2. Separate item classification from review signal severity.
3. Add or map Transactional Line where discount/additional-charge rows can be identified safely.
4. Keep rules explainable in the dashboard UI and documentation.
5. Do not change SQL unless the frontend/API fields are insufficient and the reason is documented first.
