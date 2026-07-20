# Odoo Protocol Control Tower Concept

Status: Concept Draft v1  
Purpose: Menghubungkan Odoo Protocol, dashboard traceability, anomaly ticketing, dan AI-assisted SOP improvement menjadi satu loop operasional aktif.

---

## 1. Product Vision

Aplikasi tidak hanya menampilkan dashboard terpisah. Aplikasi menjadi **process control tower** yang memperlihatkan perjalanan transaksi dari awal sampai akhir dan memeriksa apakah kondisi aktual Odoo konsisten dengan Odoo Protocol.

```text
Quotation / Customer Order
→ Sales Order
→ Approval
→ Fulfilment Decision
→ Manufacturing / Internal Order
→ RKB / ROP
→ RFQ / Purchase Order
→ Receipt
→ Material Transfer / Production
→ Finish Good
→ Delivery
→ Invoice
→ Payment
```

Setiap node dapat diklik untuk melihat:

- record yang sedang berada pada tahap tersebut;
- jumlah record normal, waiting, blocked, dan anomaly;
- aging;
- process owner;
- dokumen upstream dan downstream;
- SOP dan control point yang berlaku;
- ticket aktif;
- tindakan yang disarankan.

---

## 2. Core Principle

```text
Odoo Protocol
→ mendefinisikan flow, rule, owner, evidence, dan exception

Odoo Data
→ menunjukkan kejadian aktual

Dashboard Rule Engine
→ membandingkan aktual dengan Protocol

Exception / Ticket
→ mencatat ketidaksesuaian dan penyelesaian

AI SOP Proposal
→ mengusulkan pembaruan berdasarkan ticket tervalidasi

Human Approval
→ menentukan apakah SOP diubah

SOP Version Baru
→ memperbarui rule dashboard
```

Tidak ada perubahan SOP atau business rule yang diterbitkan otomatis tanpa approval manusia.

---

## 3. Existing Foundation

Project saat ini sudah memiliki fondasi traceability:

- Internal Order Traceability;
- Manufacturing Traceability;
- Sales Order Traceability;
- Delivery Progress;
- Invoice Progress;
- Procurement Receipt Progress;
- Procurement Billing Progress;
- dashboard pages dan JSON APIs.

Control Tower tidak mengganti dashboard tersebut. Control Tower menjadi lapisan navigasi dan governance yang menyatukan semuanya.

---

# 4. Application Views

## 4.1 End-to-End Process Map

Halaman utama menampilkan node proses secara horizontal atau loop.

Contoh node:

| Node | Isi Utama |
| --- | --- |
| Quotation | Draft quotation / Sales Order belum Confirm |
| Sales Order | SO Confirmed aktif |
| Approval | Dokumen menunggu approval / review |
| Fulfilment | Stock, Nomor IO, Make-to-Order, atau Mixed Source |
| Manufacturing | MO Draft, Confirmed, In Progress, Backorder, Done |
| Purchase Request | RKB / ROP dan approval status |
| Purchase Order | RFQ / PO status dan Expected Arrival |
| Receipt | Waiting, Partial, Done, Reject / Return |
| Production | Bon, WIP, consumption, output, Child / Parent MO |
| Finish Good | Post Production dan transfer ke Stock |
| Delivery | Waiting, Ready, Partial, Done |
| Invoice | Not Invoiced, Partial, Fully Invoiced |
| Payment | Unpaid, Partial, Paid jika data tersedia |

Setiap node menampilkan:

- total record;
- waiting count;
- exception count;
- oldest aging;
- Critical / High badge;
- owner utama.

## 4.2 Stage Worklist

Ketika node diklik, aplikasi membuka tabel record yang berada pada tahap tersebut.

Contoh klik `Purchase Order`:

- RFQ menunggu Procurement;
- PO menunggu Log Note review;
- PO menunggu Confirm VP Operations;
- PO Expected Arrival lewat;
- PO berubah tetapi Receipt belum sinkron;
- PO Cancelled tetapi Receipt masih aktif.

Filter minimum:

- company;
- date range;
- process owner;
- status;
- severity;
- aging;
- customer / vendor;
- SO / JO / IO;
- Product Type;
- site / warehouse.

## 4.3 Order Journey Detail

User dapat membuka satu root transaction, umumnya SO atau Nomor IO, lalu melihat perjalanan lengkapnya.

```text
SO-XXXX
├── Customer / Project / Commercial Terms
├── Source Decision
├── MO / Child MO
├── RKB / ROP
├── RFQ / PO
├── Receipt
├── Bon / Consumption / Output
├── Transfer FG
├── Delivery
├── Invoice
├── Payment
├── Active Anomaly
└── Related SOP Rules
```

Setiap dokumen memperlihatkan:

- status aktual;
- quantity reconciliation;
- dates dan aging;
- owner;
- Log Note indicator;
- anomaly;
- link ke detail dashboard lama;
- link / reference ke SOP.

## 4.4 Exception Worklist

Satu halaman lintas proses untuk:

- anomaly dari dashboard;
- ticket laporan user;
- request Lock / Unlock;
- correction request;
- improvement request;
- SOP change candidate.

## 4.5 SOP Rule Explorer

User dapat membuka node SOP dan melihat:

- rule aktif;
- data source;
- field source;
- exception logic;
- severity;
- process owner;
- evidence requirement;
- dashboard implementation status;
- test case;
- SOP version.

---

# 5. Canonical Process State

Odoo memiliki status yang berbeda pada setiap model. UI membutuhkan status proses yang seragam.

| Canonical State | Makna |
| --- | --- |
| `NOT_STARTED` | Tahap belum diperlukan atau belum dimulai. |
| `WAITING` | Menunggu user, approval, material, customer, supplier, atau informasi. |
| `IN_PROGRESS` | Aktivitas sedang berjalan. |
| `BLOCKED` | Tidak dapat dilanjutkan karena dependency atau masalah. |
| `PARTIAL` | Sebagian selesai dan masih memiliki sisa. |
| `COMPLETED` | Tahap selesai sesuai rule. |
| `EXCEPTION` | Data atau flow tidak konsisten dengan Protocol. |
| `NOT_APPLICABLE` | Tahap tidak berlaku untuk flow transaksi tersebut. |
| `CANCELLED` | Flow atau dokumen dibatalkan secara valid. |

Status canonical tidak menggantikan status Odoo. Status ini merupakan interpretasi business-facing dari data Odoo dan SOP.

---

# 6. Flow Instance Model

## 6.1 Root Entity

Aplikasi membutuhkan `flow_instance_id` untuk menghubungkan record lintas model.

Prioritas root:

1. Sales Order untuk customer order;
2. Nomor IO untuk internal production / make-to-stock;
3. standalone process key untuk conversion, general procurement, service, atau flow tanpa SO / IO.

## 6.2 Minimum Flow Instance Fields

```text
flow_instance_id
root_type
root_document_id
root_document_number
company_id
customer_id
project
product_type
source_type
current_stage
canonical_status
overall_health
process_owner
oldest_open_date
last_activity_date
active_exception_count
critical_exception_count
sop_version
```

## 6.3 Flow Node Fact

Satu flow instance memiliki banyak node.

```text
flow_instance_id
node_id
node_name
applicable
canonical_status
record_count
primary_document
primary_document_id
owner
planned_date
actual_date
aging_days
exception_count
highest_severity
rule_version
```

---

# 7. SOP Rule Registry

Agar SOP dan dashboard memiliki korelasi valid, business rule tidak boleh hanya berada pada paragraf Word.

Setiap control point perlu memiliki machine-readable record.

## Minimum Rule Contract

```text
rule_id
rule_name
sop_section
sop_version
process_node
business_rule
source_models
source_fields
condition_logic
excluded_states
exception_logic
severity
aging_threshold
process_owner
evidence_requirement
suggested_action
test_case_valid
test_case_invalid
test_case_exception
implementation_status
implemented_query_or_view
```

Contoh:

```text
rule_id: PO-REC-001
process_node: PURCHASE_ORDER
business_rule: PO Quantity berubah tetapi Receipt harus ikut direview
source_models: purchase_order_line, stock_move
severity: HIGH
process_owner: Procurement / WHD
related_sop: Purchase Order - Perubahan Setelah Confirm
```

---

# 8. Consistency Engine

Consistency Engine melakukan tiga jenis evaluasi.

## 8.1 Stage Derivation

Menentukan record sedang berada pada tahap mana.

Contoh:

```text
SO Confirmed
+ MO belum Done
= Manufacturing / In Progress

ROP Approved
+ RFQ belum terbentuk
= Purchase Request / Waiting Procurement

Delivery Done
+ qty_invoiced < qty_delivered
= Invoice / Waiting
```

## 8.2 Protocol Compliance

Mengecek rule SOP.

Contoh:

- Parent MO Done sebelum Child MO Done;
- JO dan IO terisi bersamaan;
- PO Cancelled tetapi Receipt aktif;
- Delivery Done tanpa evidence;
- Unlock / correction tanpa Log Note;
- movement baru ke legacy `/FG`.

## 8.3 Cross-Document Reconciliation

Membandingkan:

- ordered quantity;
- planned production;
- purchased quantity;
- received quantity;
- consumed quantity;
- produced quantity;
- delivered quantity;
- invoiced quantity;
- paid amount jika tersedia.

---

# 9. Ticket and Improvement Loop

```text
Dashboard menemukan exception
atau user melaporkan masalah
→ Ticket dibuat
→ Link ke flow instance dan rule_id
→ Triage
→ Process owner memperbaiki
→ Verifikasi manusia
→ Ticket Closed
→ AI menilai SOP impact
→ AI membuat SOP Change Proposal
→ Process Owner Review
→ VP Operations Approval
→ SOP version baru
→ Rule Registry diperbarui
→ Consistency Engine memakai rule baru
```

Ticket minimum harus menyimpan:

- flow instance;
- document;
- rule ID;
- issue category;
- severity;
- root cause;
- action;
- evidence;
- resolution;
- SOP impact;
- verification;
- close date.

---

# 10. Suggested Routes

```text
/dashboard/control-tower
/dashboard/control-tower/stage/{node_id}
/dashboard/control-tower/flow/{flow_instance_id}
/dashboard/control-tower/exceptions
/dashboard/control-tower/sop-rules
/dashboard/control-tower/sop-proposals
```

API:

```text
/api/control-tower/summary
/api/control-tower/stages/{node_id}
/api/control-tower/flows/{flow_instance_id}
/api/control-tower/exceptions
/api/control-tower/rules
/api/control-tower/proposals
```

Existing dashboard routes remain available as specialist drill-down pages.

---

# 11. Read / Write Boundary

## Phase awal

- Odoo tetap read-only untuk dashboard;
- PostgreSQL analytics menyimpan derived states dan rule results;
- ticket dan review dapat disimpan pada separate governance schema;
- Log Note tetap dicatat pada Odoo oleh user;
- dashboard dapat menampilkan indicator dan reference, tanpa menulis ke transaksi Odoo.

## Future integration

Setelah governance dan access disetujui:

- membuat ticket dari dashboard;
- link ticket ke Odoo document;
- membaca atau menghubungkan Log Note;
- workflow approval SOP proposal;
- optional Odoo Helpdesk integration.

---

# 12. Proposed Data Layers

```text
Odoo PostgreSQL / Synced PostgreSQL
        ↓
Data Truth Layer
        ↓
Traceability Views
        ↓
Flow State Engine
        ↓
SOP Rule Registry + Consistency Engine
        ↓
Exception / Ticket Store
        ↓
Control Tower API
        ↓
Interactive Process Map and Worklists
```

---

# 13. Implementation Phases

## Phase 0 — Contract Freeze

- freeze process nodes;
- assign node owners;
- create initial SOP Rule Registry;
- define root flow keys;
- define canonical statuses;
- map existing views and APIs to nodes.

## Phase 1 — Read-Only Control Tower

- process map;
- clickable nodes;
- stage worklists;
- order journey detail;
- use existing traceability data;
- no ticket write yet.

## Phase 2 — Exception Engine

- implement Priority 1 rules;
- exception worklist;
- owner and severity;
- SOP link;
- rule test cases.

## Phase 3 — Ticket Workflow

- create / assign / review / verify / close;
- link Log Note and evidence;
- SLA and aging;
- Data Health Owner worklist.

## Phase 4 — AI SOP Proposal

- summarize closed tickets;
- cluster recurring root causes;
- generate SOP Change Proposal;
- process owner review;
- VP Operations approval;
- versioned publication.

## Phase 5 — Active Governance

- scheduled rule evaluation;
- notification;
- recurring management review;
- SOP-rule version synchronization;
- audit history.

---

# 14. MVP Scope

The first practical MVP should contain:

1. end-to-end process map;
2. clickable `Sales Order`, `Manufacturing`, `Procurement`, `Receipt`, `Delivery`, and `Invoice` nodes;
3. stage-specific record lists;
4. one order journey detail page;
5. canonical status and aging;
6. Priority 1 exception badges;
7. related SOP section on every node / exception;
8. links to current Sales Order and Internal Order dashboards.

Payment can remain `NOT AVAILABLE` until reliable payment and reconciliation data is mapped.

---

# 15. Definition of Success

The Control Tower is successful when:

- a user can identify where every active transaction currently sits;
- a user can click a stage and see the records requiring action;
- one SO / IO can be traced from origin to Invoice / Payment;
- every exception references a rule and SOP section;
- every rule has data sources and test cases;
- changes to SOP create a controlled change to dashboard rules;
- recurring resolved tickets can become AI-generated SOP proposals;
- no SOP update becomes effective without human approval.
