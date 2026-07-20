# Process Node Register — Odoo Protocol Control Tower

Status: Phase 0 Draft v1  
Business authority: Odoo Protocol  
Technical implementation: Dashboard Odoo

## 1. Tujuan

Dokumen ini membekukan definisi awal setiap **tahap proses** yang akan tampil pada aplikasi Control Tower. Satu tahap proses menjadi pintu masuk untuk melihat transaksi aktif, status, aging, anomaly, owner, dan referensi SOP.

## 2. Root Flow Instance

Untuk implementasi awal, perjalanan end-to-end menggunakan dua root:

1. **Customer Flow Root**: `sale_order.id` / Nomor SO.
2. **Internal Production Root**: `approval_request.id` / Nomor IO.

Quotation masih diperlakukan sebagai tahap sebelum root sampai data quotation dan customer PO berhasil dipetakan secara konsisten.

## 3. Canonical Process Nodes

| Node ID | Tahap Proses | Jenis | Primary Owner | Entry Condition | Exit Condition | Sumber Utama | Readiness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CT-00` | Quotation / Customer Order | Document | Marketing | Draft quotation atau customer PO diterima | Sales Order dibuat | Quotation / dokumen customer | Missing / Provisional |
| `CT-01` | Sales Order | Document | Marketing / Admin Sales | SO dibuat | SO Confirmed atau Cancelled | `sale_order`, `sale_order_line` | Ready |
| `CT-02` | Approval / Operational Review | Control | Assistant VP / VP Operations | Dokumen membutuhkan review atau approval | Approved, Rejected, atau Returned | Approval record, status dokumen, Log Note | Partial |
| `CT-03` | Fulfilment Decision | Decision | Marketing / PPIC | SO Confirmed | Source ditentukan: Stock, IO, JO/MO, Mixed | SO source views, IO bridge, MO context | Ready / Partial |
| `CT-04` | Internal Order / Stock Fulfilment | Document / Process | PPIC | SO menggunakan IO atau kebutuhan stock internal dibuat | Stock hasil IO tersedia untuk fulfilment | `approval_request`, `approval_product_line`, MO bridge | Ready |
| `CT-05` | Manufacturing Planning | Document / Process | PPIC | MO dibuat atau kebutuhan produksi teridentifikasi | MO Confirmed dan material plan tersedia | `mrp_production`, `stock_move` | Ready / Partial |
| `CT-06` | RKB / ROP Purchase Request | Document / Approval | PPIC / Requester | Kebutuhan material atau jasa diajukan | ROP Approved, Cancelled, atau ditolak | `approval_request`, `approval_product_line` | Partial |
| `CT-07` | RFQ / Purchase Order | Document / Process | Procurement | RFQ terbentuk dari ROP | PO selesai, dibatalkan, atau seluruh penerimaan selesai | `purchase_order`, `purchase_order_line` | Ready / Partial |
| `CT-08` | Receipt & Inspection | Document / Control | WHD / Gudang | Receipt terbentuk | Receipt Done, Backorder, Return, atau Cancelled | `stock_picking`, `stock_move`, `stock_move_line` | Ready / Partial |
| `CT-09` | Material Transfer / Pre-Production | Process | PPIC / WHD | Material dibon dari Stock | Material tersedia di Pre-Production/WIP | stock picking / move | Partial |
| `CT-10` | Production / Finish Good | Process | PPIC / Produksi / WHD | Material tersedia dan produksi berjalan | Output masuk Post-Production lalu Stock | MO, component moves, finished moves | Partial |
| `CT-11` | Delivery | Document / Process | Marketing / WHD | Delivery terbentuk dari SO | Customer menerima, Delivery Done, atau Backorder | SO lines, delivery picking | Ready |
| `CT-12` | Invoice | Document / Process | Accounting | Invoiceable condition terpenuhi | Invoice Posted, Paid, Cancelled, atau Credit Note | `account_move`, `account_move_line`, SO invoice progress | Ready / Partial |
| `CT-13` | Payment / Collection | Document / Process | Accounting | Invoice Posted dan memiliki receivable | Payment reconciled atau outstanding | payment / receivable reconciliation | Missing |

## 4. Cabang Flow yang Sah

### 4.1 Trading dari Stock

```text
CT-01 Sales Order
→ CT-03 Fulfilment Decision = FROM_STOCK
→ CT-11 Delivery
→ CT-12 Invoice
→ CT-13 Payment
```

### 4.2 Sales Order dari Internal Order

```text
CT-01 Sales Order
→ CT-03 Fulfilment Decision = FROM_INTERNAL_ORDER
→ CT-04 Internal Order
→ CT-05 Manufacturing Planning
→ CT-09 Material Transfer
→ CT-10 Production / Finish Good
→ CT-11 Delivery
→ CT-12 Invoice
→ CT-13 Payment
```

### 4.3 Make-to-Order / JO

```text
CT-01 Sales Order
→ CT-03 Fulfilment Decision = MAKE_TO_ORDER
→ CT-05 Manufacturing Planning
→ CT-06 RKB / ROP
→ CT-07 RFQ / PO
→ CT-08 Receipt
→ CT-09 Material Transfer
→ CT-10 Production / Finish Good
→ CT-11 Delivery
→ CT-12 Invoice
→ CT-13 Payment
```

### 4.4 Mixed Source

Satu SO dapat memiliki line dari Stock, IO, dan MO. Status node dihitung per line terlebih dahulu lalu diringkas pada level SO. SO diberi label `MIXED_SOURCE` dan detail line wajib tersedia pada drill-down.

## 5. Node yang Bersifat Cross-Cutting

Approval, anomaly, ticket, Log Note, dan SOP reference bukan alur terpisah. Elemen ini menjadi overlay pada setiap tahap proses:

- jumlah record menunggu approval;
- jumlah anomaly aktif;
- ticket terbuka;
- Log Note request terakhir;
- Rule ID dan SOP section terkait;
- owner dan target tindak lanjut.

## 6. Aturan Klik Node

Saat user mengklik satu tahap proses, aplikasi minimal menampilkan:

1. jumlah record aktif;
2. canonical status;
3. aging;
4. record blocked atau partial;
5. anomaly dan severity;
6. process owner;
7. dokumen upstream dan downstream;
8. link ke detail record atau dashboard existing;
9. SOP section dan rule yang berlaku.

## 7. Keputusan Sementara yang Dipakai

- Nama business-facing adalah **Tahap Proses**; dokumentasi teknis boleh memakai `Process Node`.
- Sales Order menjadi root utama customer order journey.
- Nomor IO menjadi root untuk internal production journey.
- Payment belum ditampilkan sebagai data valid sebelum mapping reconciliation disetujui.
- Approval diperlakukan sebagai control overlay dan tahap tampilan, bukan selalu satu model tunggal.
- Status asli Odoo tetap disimpan; canonical status hanya interpretasi lintas modul.

## 8. Open Decisions

1. Apakah quotation Odoo aktif digunakan dan dapat menjadi root sebelum SO?
2. Approval apa saja yang wajib muncul sebagai tahap tersendiri: SO, ROP, PO, Unlock, atau seluruhnya?
3. Apakah Payment memakai status invoice, payment record, atau reconciliation account receivable sebagai source of truth?
4. Apakah customer flow perlu dimulai dari Distribusi JO sebelum Sales Order?
5. Apakah satu layar proses menampilkan company lain atau hanya PT Nobi Putra Angkasa?
