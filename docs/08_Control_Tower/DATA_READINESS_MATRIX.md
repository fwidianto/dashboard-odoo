# Data Readiness Matrix — Odoo Protocol Control Tower

Status: Phase 0 Draft v1

## 1. Readiness Scale

- `READY`: dapat digunakan untuk MVP dengan rule yang sudah disepakati.
- `PARTIAL`: data ada tetapi linkage, evidence, atau business rule belum lengkap.
- `MISSING`: source of truth belum tersedia atau belum disinkron.
- `MANUAL`: memerlukan supporting document atau human verification.

## 2. Stage Readiness

| Node | Tahap | Data Utama | Existing Asset | Readiness | Gap Utama | MVP Treatment |
| --- | --- | --- | --- | --- | --- | --- |
| CT-00 | Quotation / Customer Order | quotation, customer PO | Belum dipetakan pada traceability V1 | Missing / Manual | Model aktif, document attachment, linkage ke SO | Tampilkan `Not Available` dan mulai dari SO |
| CT-01 | Sales Order | `sale_order`, `sale_order_line` | Sales Order Traceability view, API, dashboard | Ready | Mandatory-field final rules dan delay threshold | Live node dan clickable worklist |
| CT-02 | Approval / Review | approval records, Log Note | ROP approval tersedia sebagian; PO review menggunakan Log Note | Partial / Manual | Approval types, timestamps, message parsing, SLA | Tampilkan review/approval yang sudah bisa dipastikan; sisanya provisional |
| CT-03 | Fulfilment Decision | SO source summary, IO bridge, MO context | Source classification dan traceability views | Ready / Partial | Mixed-source edge cases dan unknown-source review | Live source badges dan exception list |
| CT-04 | Internal Order | `approval_request`, `approval_product_line`, MO bridge | Internal Order Traceability dashboard/API | Ready | Status naming dan ownership refinement | Live node dan link ke existing IO dashboard |
| CT-05 | Manufacturing Planning | `mrp_production`, `stock_move` | Manufacturing traceability context | Ready / Partial | Parent/child link, component completeness aging | Live summary; detailed anomaly bertahap |
| CT-06 | RKB / ROP | approval request/product line | Data procurement request tersedia | Partial | RKB–ROP relation, approval timestamps, cancellation sync | Worklist awal berbasis status yang tervalidasi |
| CT-07 | RFQ / Purchase Order | `purchase_order`, `purchase_order_line` | Procurement receipt/billing tracking | Ready / Partial | Log Note review, exact RFQ grouping, SLA | Live PO worklist; anomaly quantity/cancel bertahap |
| CT-08 | Receipt & Inspection | picking/move/move line | Receipt progress tersedia | Ready / Partial / Manual | Inspection evidence, BAP, overreceipt decision | Live receipt status; evidence gap manual flag |
| CT-09 | Material Transfer / WIP | stock picking/move/location | Stock movement diagnostics tersedia | Partial | Bon identifier, operation type, site mapping, aging | Diagnostic node; no auto-judgment without mapping |
| CT-10 | Production / Finish Good | MO component/finished moves | Manufacturing traceability tersedia | Partial | Virtual Production reconciliation, FG transfer, child MO mapping | Live progress with confidence indicator |
| CT-11 | Delivery | SO line delivered qty, picking | Delivery Progress Tracking dan SO dashboard | Ready | Signed evidence dan actual shipment comparison | Live node dan clickable SO/Delivery detail |
| CT-12 | Invoice | SO line invoiced qty, account move/line | Invoice Progress Tracking dan accounting linkage | Ready / Partial | Accounting classification, DP/final invoice mapping | Live invoice progress; label traceability-only |
| CT-13 | Payment | payment/reconciliation/receivable | Belum termasuk V1 | Missing | Source of truth, partial payments, reconciliation, aging | Node visible tetapi `Data Mapping Pending` |
| Overlay | Log Note | mail message / chatter | Business use confirmed | Partial / Manual | Message model sync, prefix parsing, mentions, attachments | Start with link/reference; parsing later |
| Overlay | Ticket | anomaly register/helpdesk | Belum ada formal module | Missing | Tool choice, ID, owner, SLA, evidence | Start with external register or new table |
| Overlay | SOP Rule | Markdown/registry | SOP mapping documents tersedia | Ready as documentation | Machine-readable registry dan published version | Use Rule ID and link from each exception |

## 3. Existing Assets to Reuse

The current project already contains:

- Internal Order Traceability;
- Manufacturing Traceability;
- Sales Order Traceability;
- Delivery Progress Tracking;
- Invoice Progress Tracking;
- Procurement Receipt Tracking;
- Procurement Billing Tracking;
- JSON APIs and existing dashboard pages.

Control Tower should compose these assets rather than replace them.

## 4. Data Confidence

Every stage or rule must expose one of:

| Confidence | Meaning |
| --- | --- |
| `HIGH` | Direct field/link and business rule confirmed |
| `MEDIUM` | Derived linkage with known assumptions |
| `LOW` | Inference requires human review |
| `MANUAL` | Cannot be decided from ERP data alone |

Low/manual-confidence records must not be presented as confirmed errors. They are `Needs Review`.

## 5. Priority Data Work

### Priority A — Required for MVP

1. stable Sales Order root identifier;
2. canonical source classification;
3. MO, Delivery, and Invoice linkage to SO;
4. owner mapping;
5. standard stage-status output;
6. related SOP/Rule ID;
7. company filter PT Nobi Putra Angkasa;
8. source refresh timestamp.

### Priority B — Required for active consistency checking

1. ROP/RFQ/PO/Receipt relationship;
2. PO change versus Receipt quantity;
3. parent/child MO mapping;
4. Pre-Production, Virtual Production, Post-Production, Stock movement reconciliation;
5. cancellation mismatch;
6. Log Note availability;
7. anomaly/ticket storage.

### Priority C — Required for complete quotation-to-cash loop

1. quotation/customer PO mapping;
2. approval event history;
3. invoice DP/final invoice logic;
4. payment and AR reconciliation;
5. supporting-document evidence model.

## 6. Data Validation Gate

A node cannot be marked production-ready until:

- model and field source are documented;
- company and state filters are explicit;
- null and duplicate behavior are tested;
- business owner confirms entry/exit logic;
- at least one valid, invalid, partial, cancelled, and accepted-exception case is tested;
- dashboard result is reconciled to sample Odoo records.
