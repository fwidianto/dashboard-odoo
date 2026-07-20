# Phase 0 Decision Register — Control Tower

Status: Business Process Validation in Progress

## Confirmed / Working Decisions

| ID | Decision | Status |
| --- | --- | --- |
| `CTD-001` | Business-facing term is **Tahap Proses**; technical term may remain `Process Node`. | Working Confirmed |
| `CTD-002` | Odoo Protocol defines expected process; Dashboard Odoo checks actual data. | Confirmed Concept |
| `CTD-003` | Dashboard exceptions may later create tickets; closed tickets may trigger AI SOP Change Proposals. | Confirmed Future Concept |
| `CTD-004` | Human process owners and VP Operations retain approval authority. | Confirmed |
| `CTD-005` | Business journey begins from Customer PO / Confirmed Quotation, while Sales Order remains the initial technical root. | Confirmed Working Decision |
| `CTD-006` | Every Quotation in operational scope is considered customer-confirmed and supported by a customer PO. | Confirmed Working Decision |
| `CTD-007` | Distribusi JO occurs after SO approval/confirmation as operational information handover to related functions. | Confirmed Working Decision |
| `CTD-008` | Distribusi JO is not yet consistently in Odoo; future direction is to record the handover in Odoo. | Confirmed Direction |
| `CTD-009` | Approvals are shown within the relevant document stage rather than collected into one generic Approval stage. | Working Interpretation for Validation |
| `CTD-010` | Production is treated as Hybrid Odoo-Manual because not all users/processes currently use Odoo. | Confirmed Current Condition |
| `CTD-011` | Payment validity must compare payment records and receivable reconciliation before selecting a source of truth. | Confirmed Investigation Approach |
| `CTD-012` | Formal ticketing is deferred. Current focus is process clarification and SOP-dashboard consistency validation. | Confirmed Current Scope |
| `CTD-013` | MVP/read model remains read-only and does not write back to Odoo. | Proposed Technical Guardrail |
| `CTD-014` | Missing data is shown as `Data Mapping Pending`, `Manual`, or `Validation Pending`, not as zero. | Proposed Technical Guardrail |
| `CTD-015` | PT Nobi Putra Angkasa is the initial company scope. | Existing Project Rule |
| `CTD-016` | Internal Order remains a separate root for internal production journey. | Provisional |
| `CTD-017` | Mixed-source SO uses one SO root; status is calculated line-first and rolled up. | Provisional |

## Clarification of Approval Placement

The previous question about “which approvals appear as a stage” is resolved with this working model:

| Approval / Review | Where It Appears |
| --- | --- |
| Sales Order approval / Confirm | `CT-01 Sales Order & Approval` |
| ROP approval | `CT-06 RKB / ROP` |
| PO review Log Note and Confirm | `CT-07 RFQ / Purchase Order` |
| Lock / Unlock request and approval | Overlay on the affected document node |
| Exception approval | Overlay on the affected anomaly/document |

This avoids a generic Approval node that removes approval from its document context. This interpretation still needs confirmation during process-owner validation.

## Questions Requiring Validation

| ID | Question | Why It Matters | Proposed Validation | Decision Owner |
| --- | --- | --- | --- | --- |
| `CTV-001` | What is the minimum evidence that a customer PO and confirmed quotation are the basis of an SO? | CT-00 cannot be data-valid without a traceable reference | Inspect attachments, Customer Reference, source document, or agreed field on sample SOs | Marketing / Admin Sales |
| `CTV-002` | How is Distribusi JO currently performed and evidenced? | Determines current manual status and future Odoo design | Review current recipient list, message format, timing, and whether Log Note/Activity can represent it | Marketing / VP Operations |
| `CTV-003` | Which Production activities are recorded in Odoo and which remain manual? | Prevents dashboard from equating ERP status with physical completion | Walk through one real MO from planning, Bon, production document, QC, output, and stock transfer | PPIC / Produksi / WHD |
| `CTV-004` | Is the approval placement above correct for actual authority and timing? | Controls stage status and owner of next action | Validate SO, ROP, PO, and Unlock examples | VP Operations / Process Owners |
| `CTV-005` | How are full payment, partial payment, credit note, reversal, and outstanding AR represented? | Determines CT-13 source of truth | Reconcile payment records, invoice residual, and AR reconciliation on sample invoices | Accounting |
| `CTV-006` | Should Invoice DP and Final Invoice remain sub-types under one Invoice node? | Affects process map and journey detail | Validate with Accounting using DP and settlement samples | Accounting / VP Operations |
| `CTV-007` | Who formally validates dashboard-to-SOP mapping and signs off each node? | Needed before rules become production controls | Use process owner plus VP Operations for final business approval | VP Operations |
| `CTV-008` | Can dashboard users open the Odoo record directly? | Requires URL, access, and security validation | Test read-through deep links by user role | Odoo Admin |
| `CTV-009` | What aging/SLA threshold applies per stage? | Needed for WAITING versus BLOCKED/EXCEPTION | Defer hard-code until sample aging and owner review | Process Owners / VP Operations |
| `CTV-010` | Should Control Tower remain NPA-only or be multi-company-ready? | Affects data architecture and filters | Keep NPA data scope; design extensible | VP Operations |
| `CTV-011` | Should Log Note be parsed or initially only linked? | Affects approval and handover evidence | Link first; parse only after format and access are standardized | VP Operations / Odoo Admin |

## Deferred Questions

| ID | Topic | Reason for Deferral |
| --- | --- | --- |
| `CTF-001` | Ticket tool: Helpdesk, custom model, or external register | Process and SOP-dashboard mapping must be validated first |
| `CTF-002` | AI-generated SOP update automation | Depends on validated tickets, resolution records, and version governance |
| `CTF-003` | Write-back from dashboard to Odoo | Current architecture remains read-only |

## Current Validation Order

1. Customer PO / confirmed quotation → Sales Order.
2. SO approval/Confirm → Distribusi JO.
3. Fulfilment branch: Stock, IO, JO/MO, Mixed.
4. Manufacturing, procurement, Receipt, and WIP links.
5. Production Odoo/manual coverage.
6. Delivery → Invoice.
7. Payment and receivable reconciliation.
8. Rule-by-rule SOP-dashboard consistency review.

## Review Method

Every validated decision must update:

1. Process Node Register;
2. Rule Registry;
3. Data Readiness Matrix;
4. machine-readable config/data contract;
5. SOP section related to the process;
6. test cases and sample record evidence;
7. MVP acceptance criteria when affected.