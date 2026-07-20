# Data Readiness Matrix — Odoo Protocol Control Tower

Status: Phase 0 Draft v2 — process validation focus

## 1. Readiness Scale

- `READY`: dapat digunakan untuk MVP setelah business rule dan sample record disetujui.
- `PARTIAL`: data ada tetapi linkage, evidence, atau business rule belum lengkap.
- `MISSING`: source of truth belum tersedia atau belum disinkron.
- `MANUAL`: proses/bukti berada di luar Odoo dan memerlukan human verification.
- `HYBRID`: sebagian status tersedia di Odoo, tetapi kondisi aktual masih memerlukan bukti manual.
- `INVESTIGATION`: beberapa kandidat source tersedia tetapi belum ditentukan mana yang valid.

## 2. Stage Readiness

| Node | Tahap | Data Utama | Existing Asset | Readiness | Gap Utama | Treatment Saat Validasi |
| --- | --- | --- | --- | --- | --- | --- |
| CT-00 | Customer PO / Confirmed Quotation | customer PO, confirmed quotation, attachment/reference | Belum dipetakan pada traceability V1 | Manual / Missing Mapping | Link ke SO dan evidence minimum | Tampilkan sebagai milestone bisnis; jangan tampilkan angka nol sebagai data valid |
| CT-01 | Sales Order & Approval | `sale_order`, `sale_order_line`, state, Log Note | Sales Order Traceability view, API, dashboard | Ready / Partial | Bukti basis customer PO, approval/confirm event, mandatory-field final rules | Live setelah direkonsiliasi ke sample SO |
| CT-02 | Distribusi JO / Operational Handover | penerima informasi, waktu distribusi, referensi SO/quotation | Belum ada object formal pada dashboard | Manual / Future Odoo | Bukti distribusi saat ini dan rancangan Log Note/Activity/Follower | Milestone manual dengan status `Mapping Pending`; tidak dianggap gagal otomatis |
| CT-03 | Fulfilment Decision | SO source summary, IO bridge, MO context | Source classification dan traceability views | Ready / Partial | Mixed-source edge cases dan unknown-source review | Live source badges setelah sample validation |
| CT-04 | Internal Order | `approval_request`, `approval_product_line`, MO bridge | Internal Order Traceability dashboard/API | Ready | Status naming dan ownership refinement | Live dan link ke existing IO dashboard |
| CT-05 | Manufacturing Planning | `mrp_production`, `stock_move` | Manufacturing traceability context | Ready / Partial | Parent/child link, component completeness, actual planning practice | Live summary; compare against PPIC sample |
| CT-06 | RKB / ROP | approval request/product line | Data procurement request tersedia | Partial | RKB–ROP relation, approval timestamps, cancellation sync | Worklist berdasarkan status yang telah divalidasi |
| CT-07 | RFQ / Purchase Order | `purchase_order`, `purchase_order_line`, Log Note | Procurement receipt/billing tracking | Ready / Partial | Review Log Note, RFQ grouping, quantity change history | Live PO worklist; approval shown inside node |
| CT-08 | Receipt & Inspection | picking/move/move line, evidence | Receipt progress tersedia | Ready / Partial / Manual | Inspection evidence, BAP, overreceipt decision | ERP status live; evidence diberi confidence/manual flag |
| CT-09 | Material Transfer / WIP | stock picking/move/location | Stock movement diagnostics tersedia | Partial | Bon identifier, operation type, site mapping, aging | Diagnostic only until location/movement mapping validated |
| CT-10 | Production / Finish Good | MO component/finished moves + production document | Manufacturing traceability tersedia | Hybrid | Tidak semua user/proses Produksi memakai Odoo; actual production/QC evidence eksternal | Tampilkan ERP Status dan Operational Status terpisah; jangan menyimpulkan fisik hanya dari Odoo |
| CT-11 | Delivery | delivered qty, picking, signed evidence | Delivery Progress Tracking dan SO dashboard | Ready / Partial Evidence | Signed document dan actual shipment comparison | Live ERP progress dengan evidence confidence |
| CT-12 | Invoice | SO line invoiced qty, account move/line | Invoice Progress Tracking dan accounting linkage | Ready / Partial | DP/final invoice mapping dan definisi settlement | Live traceability; belum menyimpulkan pembayaran |
| CT-13 | Payment / Collection | payment record, residual receivable, reconciliation | Belum termasuk V1 | Investigation | Konsistensi payment record vs AR reconciliation, partial payment, reversals | Node visible sebagai `Validation Pending`; tidak memilih satu source secara prematur |
| Overlay | Approval | status dokumen, approval record, Log Note | Tersedia berbeda per dokumen | Partial / Manual | Event dan authority per SO, ROP, PO, Unlock | Ditampilkan pada node dokumen terkait, bukan satu node umum |
| Overlay | Log Note | mail message / chatter | Business use confirmed | Partial / Manual | Message model sync, prefix parsing, mentions, attachments | Link/reference dahulu; parsing setelah format dan access divalidasi |
| Overlay | SOP Rule | Markdown/registry | SOP mapping documents tersedia | Ready as documentation | Machine-readable registry dan published version | Rule ID dan SOP reference wajib pada exception |
| Future | Formal Ticketing | helpdesk/custom model/register | Belum dipilih | Deferred | Tool, owner, SLA, evidence | Tidak dikerjakan pada fase validasi proses |

## 3. Existing Assets to Reuse

Project saat ini sudah memiliki:

- Internal Order Traceability;
- Manufacturing Traceability;
- Sales Order Traceability;
- Delivery Progress Tracking;
- Invoice Progress Tracking;
- Procurement Receipt Tracking;
- Procurement Billing Tracking;
- JSON APIs dan existing dashboard pages.

Control Tower menyusun dan memvalidasi ulang asset tersebut terhadap SOP. Control Tower tidak menggantikan dashboard existing.

## 4. Data Confidence dan Coverage Mode

Setiap tahap atau rule harus menampilkan keduanya.

### Data Confidence

| Confidence | Meaning |
| --- | --- |
| `HIGH` | Direct field/link dan business rule telah dikonfirmasi |
| `MEDIUM` | Derived linkage dengan asumsi yang terdokumentasi |
| `LOW` | Inference memerlukan human review |
| `MANUAL` | Tidak dapat diputuskan dari ERP data saja |

### Coverage Mode

| Mode | Meaning |
| --- | --- |
| `ODOO` | Proses dan status utama dapat dibuktikan dari Odoo |
| `HYBRID` | Odoo memberi sebagian bukti; kondisi aktual membutuhkan evidence eksternal |
| `MANUAL` | Tahap berjalan di luar Odoo |
| `PENDING_MAPPING` | Business stage dikonfirmasi tetapi source data belum dipetakan |

Low/manual-confidence records tidak boleh ditampilkan sebagai confirmed error. Gunakan `Needs Review`.

## 5. Prioritas Kerja Saat Ini

### Priority A — Klarifikasi dan Validasi Proses

1. customer PO / confirmed quotation sebagai business start;
2. Sales Order approval/Confirm dan bukti handover Distribusi JO;
3. cabang Stock, IO, JO/MO, dan Mixed Source;
4. ownership, entry condition, dan exit condition per tahap;
5. bagian Produksi yang Odoo, hybrid, dan manual;
6. alur invoice DP/final invoice;
7. payment record versus receivable reconciliation.

### Priority B — Validasi SOP terhadap Data Dashboard

1. pilih sample transaksi nyata untuk setiap cabang;
2. telusuri setiap dokumen upstream/downstream;
3. cocokkan status Odoo, kondisi aktual, dan SOP;
4. dokumentasikan field/model dan confidence;
5. identifikasi false positive, missing link, atau SOP gap;
6. approve mapping bersama process owner.

### Priority C — Read Model Control Tower

1. stable Sales Order dan Internal Order root;
2. standard stage-status output;
3. document link graph;
4. data confidence dan coverage mode;
5. related SOP/Rule ID;
6. company filter PT Nobi Putra Angkasa;
7. source refresh timestamp.

Formal ticketing dan AI proposal tetap ditunda sampai Priority A dan B cukup stabil.

## 6. Sample Validation Minimum

Setiap flow perlu minimal:

- satu Trading dari Stock normal;
- satu SO dari Internal Order;
- satu Make-to-Order / JO;
- satu Mixed Source;
- satu partial/backorder;
- satu cancellation/change case;
- satu anomaly yang sudah diketahui;
- satu production case yang memerlukan evidence manual;
- satu invoice dengan DP/pelunasan bila tersedia;
- satu payment penuh dan satu partial payment untuk investigasi Accounting.

## 7. Data Validation Gate

Tahap tidak dapat ditandai production-ready sampai:

- proses aktual dikonfirmasi oleh owner;
- model dan field source terdokumentasi;
- company dan state filters eksplisit;
- null, duplicate, cancellation, dan partial behavior diuji;
- entry/exit logic disetujui;
- coverage mode dan confidence ditentukan;
- valid, invalid, partial, cancelled, manual, dan accepted-exception case diuji sesuai relevansi;
- hasil dashboard direkonsiliasi ke sample Odoo dan evidence operasional.