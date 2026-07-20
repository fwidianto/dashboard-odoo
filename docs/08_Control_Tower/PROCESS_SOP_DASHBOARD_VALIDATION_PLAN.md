# Process–SOP–Dashboard Validation Plan

Status: Phase 0 Execution Draft v1  
Scope: PT Nobi Putra Angkasa  
Current priority: Clarify actual process and validate Odoo Protocol against Dashboard Odoo before building the active Control Tower.

## 1. Objective

Prove, stage by stage, whether these four layers are consistent:

```text
Actual operating process
↕
Odoo Protocol / SOP
↕
Odoo source data
↕
Dashboard logic and output
```

A mapping is not considered valid only because the SQL runs or the SOP sounds correct. It must be reconciled to real transactions and confirmed by the relevant process owner.

## 2. Validation Outputs

Each validated stage must produce:

1. confirmed business definition;
2. process owner and approver;
3. entry and exit conditions;
4. Odoo, Hybrid, Manual, or Pending coverage mode;
5. source models and fields;
6. upstream/downstream document links;
7. native-to-canonical status mapping;
8. evidence requirements;
9. related SOP section and Rule ID;
10. valid, invalid, partial, cancelled, and exception sample results;
11. reviewer decision and sign-off status.

## 3. Validation Matrix Template

| Validation ID | Root SO/IO | Node | Expected by SOP | Actual Process | Odoo Evidence | Dashboard Result | Confidence | Result | Gap Type | Owner | Reviewer | Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `VAL-0001` |  |  |  |  |  |  |  |  |  |  |  |  |

### Result Values

- `MATCH`;
- `PARTIAL_MATCH`;
- `MISMATCH`;
- `MANUAL_ONLY`;
- `MAPPING_PENDING`;
- `VALID_EXCEPTION`;
- `NOT_APPLICABLE`.

### Gap Type

- `PROCESS_NOT_IN_SOP`;
- `SOP_NOT_FOLLOWED`;
- `SOURCE_DATA_MISSING`;
- `DOCUMENT_LINK_GAP`;
- `DASHBOARD_LOGIC_GAP`;
- `STATUS_MAPPING_GAP`;
- `MANUAL_EVIDENCE_GAP`;
- `ACCESS_OR_AUDIT_GAP`;
- `VALID_BUSINESS_EXCEPTION`;
- `NEEDS_OWNER_DECISION`.

## 4. Sample Transaction Pack

Select actual transactions that cover:

| Sample ID | Scenario | Minimum Evidence |
| --- | --- | --- |
| `SMP-01` | Trading from Stock — normal | Customer PO, SO, Delivery, Invoice |
| `SMP-02` | SO fulfilled from Internal Order | Customer PO, SO, IO, MO, stock output, Delivery, Invoice |
| `SMP-03` | Make-to-Order / JO | SO, MO, RKB/ROP, RFQ/PO, Receipt, production, Delivery, Invoice |
| `SMP-04` | Mixed Source | SO lines classified Stock/IO/MO and downstream quantities |
| `SMP-05` | Partial Receipt / Delivery / Production | actual quantity and Backorder evidence |
| `SMP-06` | Change after Confirm | Log Note, Unlock request, revised document, downstream reconciliation |
| `SMP-07` | Cancellation | parent and downstream cancellation/status consistency |
| `SMP-08` | Known anomaly | actual issue, correction, evidence, expected dashboard flag |
| `SMP-09` | Hybrid production | Odoo MO/moves plus manual production/QC document |
| `SMP-10` | DP and final invoice | SO/payment terms, DP invoice, final invoice, deduction/reconciliation |
| `SMP-11` | Full payment | payment record, invoice residual, AR reconciliation |
| `SMP-12` | Partial payment | payment record, remaining residual, AR reconciliation |

Use more than one sample when a scenario has materially different behavior.

## 5. Stage Validation Questions

### CT-00 — Customer PO / Confirmed Quotation

- Where is the customer PO stored or referenced?
- What proves the quotation is confirmed by the customer?
- Can the evidence be linked consistently to the SO?
- Is Customer Reference sufficient, or is attachment/reference also required?

### CT-01 — Sales Order & Approval

- Who prepares, reviews, approves, and confirms the SO?
- Which state/event proves approval?
- Are mandatory fields consistent with the SOP?
- What changes after Confirm require Log Note and downstream review?

### CT-02 — Distribusi JO / Operational Handover

- Who sends the information and to whom?
- Exactly when is it sent relative to SO approval/Confirm?
- What information is distributed?
- What evidence exists today: email, WhatsApp, document, or other?
- Can future Odoo Log Note, Activity, Followers, or another mechanism represent it without losing usability?

### CT-03 — Fulfilment Decision

- How is Stock, IO, JO/MO, or Mixed determined?
- Is the decision line-level or header-level?
- Which fields and documents provide evidence?
- What legitimate Unknown Source cases exist?

### CT-04 — Internal Order

- How is SO linked to Nomor IO?
- When is IO considered complete enough to fulfil an SO?
- Can one IO supply multiple SOs?
- How is produced stock reserved/used?

### CT-05 — Manufacturing Planning

- When is MO created and Confirmed?
- Which components may remain incomplete?
- How are Parent/Child MO linked?
- Which scheduling fields are reliable?

### CT-06 — RKB / ROP

- How are RKB and ROP related?
- Which approval events are visible?
- How are MOQ stock lines separated?
- What happens on change/cancellation?

### CT-07 — RFQ / Purchase Order

- How does ROP produce RFQ/PO?
- What proves Assistant VP review in Log Note?
- What proves VP Operations Confirm?
- How are PO changes propagated or reconciled to Receipt?

### CT-08 — Receipt & Inspection

- What does Odoo prove and what requires physical/manual evidence?
- How are partials, Backorder, overreceipt, and rejection represented?
- How is Service Receipt evidence linked?

### CT-09 — Material Transfer / Pre-Production

- Which Operation Types identify Bon?
- Are source/destination locations valid per site?
- How is Bon distinguished from consumption?
- What movement is manual or missing?

### CT-10 — Production / Finish Good

- Which Produksi users/actions occur in Odoo?
- Which steps remain outside Odoo?
- What production/QC document proves actual consumption and output?
- Does Mark As Done match physical completion?
- How is output moved Post-Production → Stock?

### CT-11 — Delivery

- What proves readiness, departure, customer receipt, and completion?
- When exactly is Validate performed?
- How are partial delivery and DO Manual reconciled?

### CT-12 — Invoice

- What triggers DP and final invoice?
- What quantity/milestone is invoiceable?
- How is DP deducted/reconciled?
- What status is traceability-only versus accounting conclusion?

### CT-13 — Payment / Collection

- What does `account.payment` or equivalent payment record show?
- What does invoice residual show?
- What does receivable reconciliation show?
- How do partial payment, reversal, credit note, write-off, and timing differences behave?
- Which combination accurately defines fully paid and outstanding?

## 6. Validation Procedure

For every sample:

```text
1. Open the source SO/IO and supporting document.
2. Follow every related Odoo document.
3. Record native status, quantity, dates, owner, and links.
4. Check physical/manual evidence where Odoo coverage is incomplete.
5. Read the current SOP expected condition.
6. Open the existing dashboard/API output.
7. Compare expected, actual, Odoo, and dashboard.
8. Classify result and gap type.
9. Let the process owner confirm the actual process.
10. Approve, revise, or defer the mapping.
```

No dashboard rule becomes a production control before this procedure is completed for representative cases.

## 7. Sign-Off Model

| Layer | Reviewer |
| --- | --- |
| Actual process | Process Owner |
| Cross-functional sequence | Assistant VP / Staff VP Operations |
| Business authority / exception | VP Operations |
| Odoo model/field/link | Odoo/Data Technical Owner |
| Dashboard rule/query | Dashboard Technical Owner |
| Accounting settlement/payment | Accounting Owner |

A stage receives `VALIDATED` only after business and technical evidence agree.

## 8. Validation Status

- `NOT_STARTED`;
- `SAMPLE_SELECTED`;
- `BUSINESS_REVIEW`;
- `DATA_RECONCILIATION`;
- `DASHBOARD_RECONCILIATION`;
- `REVISION_REQUIRED`;
- `READY_FOR_SIGNOFF`;
- `VALIDATED`;
- `DEFERRED`.

## 9. Immediate Execution Order

1. Validate `SMP-01` Trading from Stock from CT-00 to CT-13 available data.
2. Validate `SMP-03` Make-to-Order / JO because it covers the most stages.
3. Validate `SMP-02` Internal Order flow.
4. Validate `SMP-04` Mixed Source.
5. Validate partial/change/cancellation samples.
6. Validate Hybrid Production with PPIC, Produksi, and WHD.
7. Validate Invoice/Payment with Accounting.
8. Freeze approved Node Register and Rule Registry version.
9. Only then prepare SQL/API implementation prompt for Codex.

## 10. Current Exclusions

During this validation phase, do not:

- build formal ticketing;
- automate SOP updates;
- write back to Odoo;
- hard-code SLA without owner decision;
- treat manual stages as zero;
- treat Odoo status as proof of physical completion when coverage is hybrid;
- choose payment source of truth before sample reconciliation.