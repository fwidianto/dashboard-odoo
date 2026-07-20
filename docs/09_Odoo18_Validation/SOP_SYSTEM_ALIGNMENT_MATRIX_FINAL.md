# SOP–System Alignment Matrix Final

**Project:** Odoo Protocol – PT Nobi Putra Angkasa  
**System:** Odoo 18  
**Status:** Final alignment baseline for SOP Draft v2  
**Date:** 20 July 2026  
**Document owner:** Operations / Odoo Process Owner  

---

## 1. Purpose

This document reconciles the agreed operational SOP with:

1. the restored Odoo 18 database structure and transaction evidence;
2. active Automated Actions, Server Actions, Studio rules, and Scheduled Actions;
3. runtime API tests performed on the Odoo staging environment;
4. final business clarifications provided by Operations.

This document is the approved working baseline for preparing **SOP Odoo Draft v2** and, after stakeholder approval, revising the Odoo analytics extraction, SQL, API, and Control Tower dashboard.

This document does **not** yet authorize dashboard implementation or production configuration changes.

---

## 2. Evidence Base

The alignment uses the following completed technical reviews:

- Database Restore and Schema Report;
- Odoo 18 Field and Model Mapping;
- Transaction Journey Validation;
- SOP and Dashboard Gap Register;
- Payment and Reconciliation Investigation;
- Distribusi JO and Hybrid Process Findings;
- Odoo 18 Automation and Server Action Map;
- Full Runtime Cancellation and Outstanding Matrix;
- Final SOP System Closure Audit;
- existing Odoo Flow & Tutorial baseline;
- business decisions confirmed during the Odoo Protocol discussion.

Technical scope includes 1,236 Sales Orders, 6,087 Purchase Orders, 11,330 Manufacturing Orders, 39,490 stock pickings, 304,916 stock moves, 3,032 approval requests, and Odoo accounting and reconciliation records. Runtime validation used the Odoo 18 staging API and did not modify production.

---

## 3. Status Legend

| Status | Meaning |
|---|---|
| `ALIGNED` | SOP and actual Odoo behavior are consistent. |
| `SOP_UPDATE` | Business rule is agreed, but the SOP wording or control point must be revised. |
| `MANUAL_OUTSIDE_ODOO` | Process exists operationally but is not represented as a reliable Odoo event. |
| `CUSTOM_BEHAVIOR` | Behavior comes from Studio, Automated Action, or Server Action rather than standard Odoo alone. |
| `DATA_HEALTH_CONTROL` | SOP is valid, but compliance must be monitored through exception checks. |
| `TO_BE` | Future process or system behavior that is not yet fully implemented. |
| `PENDING_OWNER_DECISION` | Final wording or rule still requires confirmation from the responsible function. |

---

## 4. Executive Alignment Conclusions

1. The core Sales, Manufacturing, Procurement, Receipt, Delivery, and Accounting relationships are present in Odoo 18 and are sufficiently traceable for a future Control Tower.
2. Distribusi JO is an external operational handover. It is not an Odoo stage and may occur while the SO is still Draft.
3. A Sales Order supported by an Internal Order can create an MO that is immediately cancelled by an active automation. This is valid **MO suppression**, not an ordinary production cancellation.
4. ROP to RFQ/PO is a custom, user-triggered server action, not a fully automatic standard Odoo transition.
5. Reset to Draft is a correction action, not a cancellation. A PO may return to Draft while Receipt, Stock Move, and Draft Vendor Bill remain active.
6. PO Confirmed is accepted as the official operational approval state.
7. No 2026 cancelled PO was found with an open Receipt. Therefore, `Cancelled PO with Open Receipt` remains a valid anomaly definition, but it is not a normal 2026 process pattern.
8. All 357 confirmed SOs from 2026 onward contained both Customer Reference and Customer PO Date. These fields can be established as mandatory controls for 2026 onward.
9. Internal Order status should be derived from production and utilization quantities, not from the current approval-request status alone. The current data still contains substantial allocation and UoM exceptions.
10. Payment status can be derived technically from invoice residual and reconciliation, but final business labels and exception treatment remain pending Accounting confirmation.

---

# 5. Final SOP–System Alignment Matrix

## A. Sales and Customer Order

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| S-01 | Customer confirmation before operational processing | Sales creates an SO after receiving Customer PO, confirmed quotation, Draft PO, or equivalent confirmed commercial evidence. | Odoo contains Customer Reference and Customer PO Date fields. All 357 confirmed SOs from 2026 onward contain both fields. | `ALIGNED` and `DATA_HEALTH_CONTROL`. Make both fields mandatory for confirmed SOs from 2026 onward. Earlier migration-period records are not used as the main compliance baseline. |
| S-02 | Distribusi JO | Marketing performs Distribusi JO outside Odoo. It may occur before SO Confirm when Operations/PPIC must start preparation, including while waiting for IO production or other operational/technical considerations. | No dedicated Odoo field, activity, status, automation, email, or chatter contract proves Distribusi JO completion. | `MANUAL_OUTSIDE_ODOO`. Remove Distribusi JO as an Odoo stage. SOP should identify it as an external handover and should not derive its completion from SO state. |
| S-03 | SO approval | VP Operations confirms the SO in Odoo. Physical document approval/signature may remain outside the system. | No separate automation confirms SO. Odoo state transition remains the strongest system evidence. | `ALIGNED`. `sale`/confirmed state is the system approval evidence for operational use. |
| S-04 | Timing of SO Confirm | SO does not always need to be confirmed immediately after Distribusi JO. It may remain Draft while waiting for IO readiness, commercial/technical clarification, or other management considerations. | Distribusi JO is external and no system dependency requires it to follow SO Confirm. | `SOP_UPDATE`. Separate business handover timing from the system confirmation event. |
| S-05 | SO numbering and Product Type | Product Type must be selected correctly because it affects SO classification and numbering. | Active automation rewrites SO numbering using Product Type context. | `CUSTOM_BEHAVIOR`. SOP must state that Product Type affects numbering and must be validated before confirmation. |
| S-06 | Fulfilment from Stock | SO lines may be fulfilled directly from available stock without a new MO. | SO-to-Delivery and line-level stock evidence are directly traceable. | `ALIGNED`. |
| S-07 | Fulfilment from Internal Order | A Sales Order may use FG produced under an Internal Order. The related new SO-based MO is automatically cancelled. | Active MO automation sets new MO to `cancel` when the IO-from-SO condition is present. | `CUSTOM_BEHAVIOR`. Label this as `MO_SUPPRESSED_BY_IO`, not ordinary cancellation or production failure. |
| S-08 | Mixed fulfilment | One SO may combine Stock, Internal Order, and new Manufacturing sources at line level. | Active SOs were found with both IO and direct-MO evidence. Header-level IO precedence can misclassify lines. | `SOP_UPDATE`. Define source per SO line. Header status becomes `MIXED_SOURCE` when more than one fulfilment source exists. |
| S-09 | SO cancellation | Cancel is successful only when the SO state actually changes to `cancel`. Completed downstream documents remain historical evidence; open downstream documents require review. | Runtime cancel attempt on an SO with mixed done/open downstream was blocked or failed and the SO remained `sale`. | `SOP_UPDATE`. Do not force state changes. Introduce `CANCEL_BLOCKED_OR_FAILED` and `CANCELED_SO_WITH_ACTIVE_DOWNSTREAM` exception controls. |
| S-10 | SO reset to Draft | Reset to Draft is a correction process requiring approval, reason, downstream review, and closure note. | Exact UI/API reset action was not proven in the audit. | `PENDING_OWNER_DECISION` for exact technical action. Operational control is still required in SOP. |

## B. Internal Order and Manufacturing

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| M-01 | Internal Order as production source | IO represents production for stock or future utilization and can be linked directly to SO and MO. | Direct SO–IO many-to-many relation and IO–MO many-to-one relation are present. | `ALIGNED`. Native relation IDs are the source of truth. |
| M-02 | Current IO approval status | Existing IO request status is not maintained as the operational production-progress status. | Several IOs remained `new` despite downstream MO or Delivery activity. | `SOP_UPDATE`. Do not use approval-request status alone as operational IO progress. |
| M-03 | Derived IO Production Status | Compare requested IO quantity against active MO planned quantity, completed MO quantity, and actual produced quantity. | 39 IOs were classified: 3 Not Started, 2 In Progress, 3 Partially Produced, 4 Fully Produced, 1 Over Produced, and 26 Data Exception. | `TO_BE`. Proposed statuses: `NOT_STARTED`, `IN_PROGRESS`, `PARTIALLY_PRODUCED`, `FULLY_PRODUCED`, `OVER_PRODUCED`, `CANCELLED`, `DATA_EXCEPTION`. Publish only after product and UoM matching rules are approved. |
| M-04 | Derived IO Utilization Status | Compare produced IO quantity against quantity directly allocated to SOs. | 39 IOs were classified: 12 Not Utilized, 2 Partially Utilized, 5 Fully Utilized, and 20 Data Exception. Multi-IO SO allocation is unresolved. | `TO_BE`. Proposed statuses: `NOT_UTILIZED`, `PARTIALLY_UTILIZED`, `FULLY_UTILIZED`, `OVER_UTILIZED`, `DATA_EXCEPTION`. Do not allocate multi-IO SO quantities by inference. |
| M-05 | MO creation and confirmation | PPIC completes JO/IO, schedule, responsible person, components, and operation type before confirming the MO. | Direct MO fields and state transitions exist. Confirmation-date helper is populated by automation. | `ALIGNED`, with confirmation date treated as supporting evidence rather than sole truth. |
| M-06 | Parent and Child MO | In future, Child MO should be generated from the confirmed Parent MO and remain traceable to it. | Current database exposes backorder sequences but no reliable persistent Parent-MO FK. | `TO_BE`. SOP must separate current behavior from future controlled Parent–Child generation. Dashboard must not claim exact genealogy until a persistent relation exists. |
| M-07 | Bon / component staging | Bon transfers components from Stock to Pre-Production/WIP. It is not consumption. | Stock moves and locations support the staging flow. | `ALIGNED`. Keep Bon and consumption as separate control points. |
| M-08 | Component consumption | Actual consumption is recorded from Pre-Production to Virtual Production when production is completed. | `raw_material_production_id` directly links component moves to MO. | `ALIGNED`. |
| M-09 | Finished output | MO output is created from Virtual Production to Post-Production, then transferred to Stock. | `production_id`, stock moves, and locations support this flow. | `ALIGNED`. |
| M-10 | Hybrid shop-floor process | Odoo records MO, component movement, consumption, and output. Physical production documents and some execution evidence remain manual. | 11,330 MOs and extensive stock-move evidence exist, while workorders are empty. | `ALIGNED` as `HYBRID_ODOO_MANUAL`. MO Done proves completion in Odoo, not every physical shop-floor step. |
| M-11 | Quality Control | QC may be carried out physically or through external/manual records. Odoo Quality is not consistently used as the evidence source. | No meaningful QC picking/workorder evidence was available in the audited database. | `MANUAL_OUTSIDE_ODOO`. SOP must define the required physical/manual evidence and owner. |
| M-12 | MO cancellation | Cancellation can cascade to related production/transfer evidence, but result must be checked. IO-based MO suppression must be distinguished from user cancellation. | Runtime MO cancel changed the MO to `cancel` and two related records also cancelled. | `SOP_UPDATE`. Add post-cancel verification and separate `MO_SUPPRESSED_BY_IO` from ordinary `MO_CANCELLED`. |

## C. RKB, ROP, Procurement, and Purchase Order

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| P-01 | RKB and ROP distinction | RKB is planning/request detail. ROP/PEMBELIAN is the approval-based purchase-request path. | Approval categories, request lines, and direct ROP-to-PO line links are present. | `ALIGNED`. |
| P-02 | ROP approval flow | ROP is reviewed and approved by Assistant VP and VP Operations according to the applicable approval path. | Approval actors and request states exist. Several totals and margins are automation-derived. | `ALIGNED`, but derived helper values must not replace the approval header state. |
| P-03 | ROP to RFQ/PO | After ROP approval, an authorized user runs the custom action that creates RFQ/PO records. | A bound Approval Request Server Action creates `purchase.order` and lines with ROP/JO links. It is user-triggered, not automatic. | `CUSTOM_BEHAVIOR`. SOP must explicitly identify the responsible user and button/action. |
| P-04 | PO approval | A PO is officially approved when it is Confirmed in Odoo. | PO state transition and approver/sign helper fields exist. | `ALIGNED`. The approver/sign field is supporting metadata; the confirmed state is the official operational evidence. |
| P-05 | PO naming/grouping | Procurement must validate PO group because the displayed reference may be rewritten. | Active automation rewrites PO name using PO Group. | `CUSTOM_BEHAVIOR`. Technical traceability must use IDs and line relations, not document-number text alone. |
| P-06 | Reset PO to Draft | Reset is a correction action, not cancellation. It requires approval, Log Note reason, downstream review, and closure. | Runtime S03: PO changed `purchase` to `draft`; Draft Vendor Bill, assigned Receipt, and two assigned Stock Moves remained active; no relation was deleted or unlinked. | `SOP_UPDATE`. Introduce `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM`. Correction is not complete until all downstream exposure is reviewed and resolved. |
| P-07 | Meaning of `_delete_entries()` | The custom reset action calls `_delete_entries()`, but its exact method scope is not available through the database/API. | Runtime evidence shows it did not cancel or delete the monitored Receipt, Bill, Stock Moves, or PO lines in the tested PO. | `PENDING_OWNER_DECISION` only for technical scope. SOP can already state that downstream is not guaranteed to be cleared. |
| P-08 | PO cancellation | PO Cancel is considered successful only when state becomes `cancel`. Open Receipt, partial receipt, completed receipt, backorder, and Vendor Bill exposure must be reviewed. | Runtime direct PO cancel with an assigned Receipt was blocked or failed. In 2026, 348 cancelled POs had zero open Receipt anomalies. | `SOP_UPDATE` and `DATA_HEALTH_CONTROL`. `CANCELLED_PO_WITH_OPEN_RECEIPT` is an anomaly. Do not assume Cancel always cascades automatically. |
| P-09 | Reported cancelled PO with open supplier DO/Receipt | Such a condition should not remain unresolved. | No such 2026 anomaly was found. The reported case may be older, migrated, reopened, or produced through another action path. | `DATA_HEALTH_CONTROL`. Investigate by exact PO and Receipt reference when available; do not generalize it as normal behavior. |
| P-10 | PO line and approval helper values | ROP quantity, PO quantity, budget, variance, unit price, line number, and last purchase price may be automation-derived. | Multiple active broad-trigger automations calculate or copy these fields. | `CUSTOM_BEHAVIOR`. Dashboard must label helpers as derived and retain underlying quantities and IDs. |

## D. Receipt, Warehouse, and Delivery

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| W-01 | Receipt processing | WHD validates Receipt only after physical receipt and required QC/evidence are complete. | PO–Receipt and Stock Move relations are direct. | `ALIGNED`. |
| W-02 | Partial Receipt and Backorder | Partial receipt must preserve the remaining open quantity through Backorder or equivalent active transfer. | `stock.picking.backorder_id` directly proves the chain. | `ALIGNED`. Control Tower should display the open child document. |
| W-03 | Cancel open Receipt | Cancelling a Receipt cancels its stock movement, but does not automatically cancel the PO. | Runtime test changed assigned Receipt to `cancel`; eight related records cancelled and one parent relation remained open. | `SOP_UPDATE`. Procurement/WHD must decide whether to create a replacement Receipt or cancel/correct the PO. |
| W-04 | Delivery processing | WHD validates Delivery after customer receipt/signature and actual delivered quantity. | SO–Delivery and Stock Move relations are direct. | `ALIGNED`. |
| W-05 | Cancel open Delivery | Cancelling a Delivery cancels its related stock movements, but does not automatically cancel the SO. | Runtime test changed Delivery to `cancel`; two related records cancelled and one parent relation remained open. | `SOP_UPDATE`. WHD/Operations must decide whether to recreate Delivery or cancel/correct the SO. |
| W-06 | Done Receipt or Delivery | Completed physical movement remains historical evidence and must not be erased merely because the parent is cancelled. | Historical journeys contain done downstream records attached to cancelled parents. | `ALIGNED`. Use `CANCELED_PARENT_WITH_DONE_DOWNSTREAM` as an exception requiring explanation, not deletion. |
| W-07 | Manual DO / Internal Transfer exception | A manually created transfer used as an operational exception must later be reconciled to the standard source document and flow. | Manual transfers can exist outside the native SO/PO path. | `SOP_UPDATE`. Require source reference, reason, owner, and closure verification. |

## E. Invoice, Payment, and Accounting

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| A-01 | Invoice relationship | Customer invoices must be traced from SO lines to accounting entries, not by description text. | Direct SO-line–invoice relation and accounting move-line links exist. | `ALIGNED`. |
| A-02 | Draft invoice cancellation | Final state must be checked even if API/UI reports an error. | Runtime S11 returned RPC error, but invoice state changed from `draft` to `cancel`. | `SOP_UPDATE`. Use `ACTION_APPLIED_WITH_RPC_ERROR`; do not repeat an action before verifying the final state. |
| A-03 | Payment source of truth | Payment status must use posted invoice state, amount residual, receivable journal items, reconciliation edges, payment entries, and adjustment evidence. | Header payment state was consistent with residuals in the audit, while settlement sources varied. Disabled helper automation had written sales-level paid copies. | `SOP_UPDATE`. `sale_order.x_studio_paid` and similar copy fields are not accounting truth. |
| A-04 | Proposed payment labels | Candidate labels include Unpaid, Partially Paid, Fully Paid, Payment Registered but Not Reconciled, Settled by Adjustment/Credit Note, Overpaid, and Cancelled/Reversed. | Technical classification is possible, but exception policy and business terminology are not yet approved. | `PENDING_OWNER_DECISION`. Accounting question list has been saved for later validation. |
| A-05 | Posted accounting documents | Posted invoices, posted Vendor Bills, Payment, and Reconciliation must not be changed during general operational testing. | Runtime audit kept posted accounting documents read-only. | `ALIGNED`. Accounting correction requires Accounting authority and a dedicated procedure. |

## F. Governance, Audit Trail, and Dashboard Contract

| ID | Process / Rule | Agreed SOP | Technical and Runtime Evidence | Final Alignment / Required Action |
|---|---|---|---|---|
| G-01 | Log Note for changes | Material changes, Unlock/Reset, corrections, and unusual cancellation should be recorded in Log Note with reason, approval, impact, and completion. | Chatter exists but is not consistently structured. No automation enforces the required note. | `SOP_UPDATE`. Apply as a mandatory operational control, with gradual enforcement and review. |
| G-02 | Correction closure | A correction is complete only after downstream verification and a closing Log Note. | Reset PO can leave Receipt, Stock Move, and Draft Bill active. | `SOP_UPDATE`. Introduce before/after checklist and closure owner. |
| G-03 | Native relation priority | Native IDs, foreign keys, and relation tables outrank display names and document-number matching. | Odoo stores many2one as IDs and SO–IO in a many-to-many relation table. Current dashboard extraction can lose these relations. | `SOP_UPDATE` for technical appendix and future data contract. |
| G-04 | Company scope | Analytics must use stable company ID, not company display-name text. | Native company field is numeric; current SQL uses a hard-coded display name. | `DATA_HEALTH_CONTROL`. Correct during dashboard implementation. |
| G-05 | Automation-derived evidence | Derived helper fields are useful for review but are not independent transaction evidence. | Numerous active automations calculate approval totals, margins, ROP/PO quantities, stock/WIP helpers, names, and approver copies. | `CUSTOM_BEHAVIOR`. Dashboard must show the underlying transaction basis. |
| G-06 | Overlapping automations | Potential trigger overlaps must be monitored, but are not confirmed defects without runtime evidence. | 22 approval combinations and 25 total potential conflict patterns were found. | `DATA_HEALTH_CONTROL`. Do not label as errors automatically. Add technical monitoring if performance or inconsistency appears. |
| G-07 | Cancellation exception worklist | Cancelled/reset parents with open, partial, reserved, posted, or done downstream must remain visible. | Runtime and historical evidence support multiple downstream outcomes. | `SOP_UPDATE`. Define exception statuses listed in Section 7. |
| G-08 | Control Tower role | Dashboard is a process-control and exception-review tool, not a substitute for the responsible owner. | Odoo contains sufficient direct relationships, but several business events remain manual or pending. | `ALIGNED`. |

---

## 6. Final Operational Rules to Insert into SOP Draft v2

### 6.1 Reset to Draft / Unlock

1. Reset to Draft is used only for correction and is not equivalent to Cancel.
2. The requester must state the reason, expected change, affected documents, and approval in Log Note.
3. Before Reset, identify all Receipt, Delivery, Stock Move, MO, Invoice, Vendor Bill, Backorder, reservation, and related documents.
4. After Reset, inspect the same downstream documents again.
5. Open downstream records must be cancelled, corrected, retained with an approved exception, or otherwise formally resolved.
6. Add a closing Log Note describing the final correction and remaining exposure.
7. The correction is not complete merely because the parent document is Draft.

### 6.2 Cancellation

1. Cancellation is successful only if the final document state is `cancel`.
2. An error message does not automatically mean the action failed; verify the final state before repeating the action.
3. Completed (`done`/posted) downstream records remain historical evidence.
4. Open, partial, reserved, assigned, waiting, or backorder records require explicit review and resolution.
5. Never force a state by direct database update.
6. Parent cancellation with active downstream must enter the Exception Worklist.

### 6.3 Internal Order Status

Until the matching and allocation rules are approved:

- continue to show the original Approval Request state for administrative reference;
- calculate provisional Production and Utilization statuses separately;
- retain `DATA_EXCEPTION` for mixed products, incompatible UoM, one SO linked to multiple IOs, or missing direct links;
- do not manually allocate quantities by assumption.

### 6.4 Distribusi JO

1. Distribusi JO is performed outside Odoo.
2. It may take place before SO Confirm.
3. The SO can remain Draft while Operations waits for IO production, technical clarification, or another approved consideration.
4. The dashboard must not infer Distribusi JO completion from SO, MO, follower, activity, or chatter state.

### 6.5 Accounting

1. Payment status must not rely on copied Sales Order fields.
2. Invoice residual and reconciliation are the principal technical evidence.
3. Final labels, treatment of adjustment journals, Down Payment, overpayment, and reconciliation timing remain pending Accounting approval.

---

## 7. Approved Data Health and Control Tower Exception Definitions

| Exception Code | Definition |
|---|---|
| `MO_SUPPRESSED_BY_IO` | MO automatically cancelled because the SO is supplied through an Internal Order. Valid suppression, not production failure. |
| `MIXED_SOURCE` | One SO contains more than one fulfilment source across its lines. |
| `RESET_TO_DRAFT_WITH_OPEN_DOWNSTREAM` | SO/PO returns to Draft while operational or accounting downstream remains active. |
| `RESET_TO_DRAFT_WITH_OPEN_RECEIPT` | PO is Draft after prior confirmation and a Receipt remains open. |
| `RESET_TO_DRAFT_WITH_DRAFT_VENDOR_BILL` | PO is Draft after prior confirmation and a Draft Vendor Bill remains active. |
| `CANCEL_BLOCKED_OR_FAILED` | Cancel action returned an error and the target state did not change. |
| `ACTION_APPLIED_WITH_RPC_ERROR` | Action returned an error but the requested state change occurred. |
| `CANCELED_PARENT_WITH_OPEN_DOWNSTREAM` | Cancelled/reset parent retains operationally open downstream records. |
| `CANCELED_PARENT_WITH_DONE_DOWNSTREAM` | Cancelled/reset parent retains completed stock, manufacturing, or posted-accounting evidence. |
| `CANCELED_PARENT_WITH_RESERVED_STOCK` | Cancelled/reset parent leaves assigned or reserved stock movement. |
| `CANCELED_PARENT_WITH_PARTIAL_BACKORDER` | Cancelled/reset parent leaves partial quantity or open backorder. |
| `CANCELLED_PO_WITH_OPEN_RECEIPT` | PO state is Cancel, but incoming Receipt remains neither Cancel nor Done. |
| `CANCELLED_SO_WITH_ACTIVE_DOWNSTREAM` | Cancelled SO retains open MO, Delivery, PO, Invoice, or Backorder. |
| `IO_PRODUCTION_DATA_EXCEPTION` | IO production status cannot be calculated safely because product, UoM, lifecycle, or linkage evidence is inconsistent. |
| `IO_UTILIZATION_DATA_EXCEPTION` | IO utilization cannot be allocated safely, including multi-IO SO cases. |
| `AUTOMATION_EFFECT_UNCONFIRMED` | Trigger conditions align, but execution history or exact field effect cannot be proven. |

---

## 8. Decisions Still Open

| Decision | Required Owner | Current Position |
|---|---|---|
| Final payment and reconciliation labels | Accounting | Question list prepared; technical basis confirmed. |
| Allowed journal adjustments and credit-note treatment | Accounting | Pending. |
| Down Payment allocation rule | Accounting | Pending. |
| Payment date used by management dashboard | Accounting | Pending. |
| IO product and UoM matching rule | PPIC / Production / Data Owner | Provisional calculation only. |
| Allocation when one SO uses multiple IOs | PPIC / Operations | Keep `DATA_EXCEPTION`; do not infer. |
| Persistent Parent–Child MO relationship | PPIC / Odoo Technical Owner | Future development after Parent MO Confirm. |
| Exact `_delete_entries()` method scope | Odoo Technical Owner | Not required to establish current operational control, but useful for future debugging. |
| Formal enforcement of structured Log Note | VP Operations / Process Owners | Target control agreed; enforcement method pending. |

---

## 9. Implementation Sequence After Approval

1. Publish this alignment matrix as the baseline for SOP Draft v2.
2. Rewrite the SOP and tutorial to reflect the final operational rules.
3. Review the Draft v2 with VP Operations and process owners.
4. Resolve Accounting and IO allocation decisions.
5. Approve the canonical Control Tower stages, statuses, and exception vocabulary.
6. Revise the analytics extraction contract:
   - preserve native IDs;
   - extract SO–IO many-to-many relations;
   - add stock picking/move and accounting reconciliation sources;
   - use stable company ID;
   - surface missing-field validation.
7. Revise SQL and APIs.
8. Implement dashboard/Control Tower UI and Exception Worklist.
9. Validate against fresh production-safe snapshots before release.

---

## 10. Sign-off

| Role | Decision | Name / Date |
|---|---|---|
| VP Operations | Approve operational baseline |  |
| Operations / Odoo Process Owner | Confirm SOP wording and ownership |  |
| Sales / Marketing | Confirm Customer PO and Distribusi JO rules |  |
| PPIC / Production | Confirm IO, MO, Parent–Child, and quantity rules |  |
| Procurement / WHD | Confirm PO, Receipt, Reset, and Cancellation controls |  |
| Accounting | Confirm payment/reconciliation rules |  |
| Data / Dashboard Owner | Confirm technical data contract |  |

---

**Document control:** This matrix supersedes earlier working assumptions where they conflict with the decisions and runtime evidence stated above. It is the direct input for SOP Odoo Draft v2, not the final end-user tutorial itself.
