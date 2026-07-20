# Process Node Register — Odoo Protocol Control Tower

Status: Phase 0 Draft v2 — clarified with VP Operations review follow-up  
Business authority: Odoo Protocol  
Technical implementation: Dashboard Odoo

## 1. Tujuan

Dokumen ini membekukan definisi awal setiap **tahap proses** yang akan tampil pada aplikasi Control Tower. Satu tahap proses menjadi pintu masuk untuk melihat transaksi aktif, status, aging, anomaly, owner, dan referensi SOP.

Fokus saat ini adalah memvalidasi keterkaitan proses aktual, SOP, dan data dashboard. Ticketing dan AI-assisted SOP update tetap menjadi arah berikutnya, tetapi bukan scope implementasi sekarang.

## 2. Root Flow Instance

Perjalanan bisnis dimulai dari **Customer PO / Confirmed Quotation**. Namun root teknis awal tetap:

1. **Customer Flow Root**: `sale_order.id` / Nomor SO.
2. **Internal Production Root**: `approval_request.id` / Nomor IO.

Semua Quotation yang masuk ke flow operasional dianggap:

- telah dikonfirmasi customer; dan
- memiliki PO customer sebagai dasar order.

Karena customer PO / confirmed quotation belum dipetakan secara konsisten sebagai object data dashboard, tahap tersebut ditampilkan sebagai milestone bisnis/manual sebelum Sales Order.

## 3. Canonical Process Nodes

| Node ID | Tahap Proses | Jenis | Primary Owner | Entry Condition | Exit Condition | Sumber Utama | Readiness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CT-00` | Customer PO / Confirmed Quotation | Document / Milestone | Marketing | Quotation telah dikonfirmasi customer dan PO customer tersedia | Sales Order dibuat berdasarkan dokumen tersebut | Customer PO, confirmed quotation, attachment/reference | Manual / Mapping Pending |
| `CT-01` | Sales Order & Approval | Document / Control | Marketing / Admin Sales; approver sesuai kewenangan | Dasar customer order tersedia dan SO dibuat | SO telah direview, approved/confirmed, atau Cancelled | `sale_order`, `sale_order_line`, status, Log Note | Ready / Partial |
| `CT-02` | Distribusi JO / Operational Handover | Communication / Handover | Marketing / Admin Sales | SO sudah approved/confirmed | Informasi order telah disebarkan kepada bagian terkait dan pekerjaan dapat ditindaklanjuti | Saat ini komunikasi operasional; future Odoo Log Note/Activity/Follower perlu divalidasi | Manual / Future Odoo |
| `CT-03` | Fulfilment Decision | Decision | Marketing / PPIC | SO Confirmed dan Distribusi JO telah dilakukan atau informasi order telah diterima bagian terkait | Source ditentukan: Stock, IO, JO/MO, atau Mixed | SO source views, IO bridge, MO context | Ready / Partial |
| `CT-04` | Internal Order / Stock Fulfilment | Document / Process | PPIC | SO menggunakan IO atau kebutuhan stock internal dibuat | Stock hasil IO tersedia untuk fulfilment | `approval_request`, `approval_product_line`, MO bridge | Ready |
| `CT-05` | Manufacturing Planning | Document / Process | PPIC | MO dibuat atau kebutuhan produksi teridentifikasi | MO Confirmed dan material plan tersedia | `mrp_production`, `stock_move` | Ready / Partial |
| `CT-06` | RKB / ROP Purchase Request | Document / Approval | PPIC / Requester; approver ROP | Kebutuhan material atau jasa diajukan | ROP Approved, Cancelled, atau ditolak | `approval_request`, `approval_product_line` | Partial |
| `CT-07` | RFQ / Purchase Order | Document / Process / Approval | Procurement; Assistant VP / VP Operations untuk review/approval | RFQ terbentuk dari ROP | PO selesai, dibatalkan, atau seluruh penerimaan selesai | `purchase_order`, `purchase_order_line`, Log Note | Ready / Partial |
| `CT-08` | Receipt & Inspection | Document / Control | WHD / Gudang | Receipt terbentuk | Receipt Done, Backorder, Return, atau Cancelled | `stock_picking`, `stock_move`, `stock_move_line` | Ready / Partial / Manual Evidence |
| `CT-09` | Material Transfer / Pre-Production | Process | PPIC / WHD | Material dibon dari Stock | Material tersedia di Pre-Production/WIP | stock picking / move | Partial |
| `CT-10` | Production / Finish Good | Hybrid Process | PPIC / Produksi / WHD | Material tersedia dan produksi berjalan | Output masuk Post-Production lalu Stock | MO, component moves, finished moves, production document/manual evidence | Partial / Hybrid Odoo-Manual |
| `CT-11` | Delivery | Document / Process | Marketing / WHD | Delivery terbentuk dari SO | Customer menerima, Delivery Done, atau Backorder | SO lines, delivery picking, signed delivery evidence | Ready / Partial Evidence |
| `CT-12` | Invoice | Document / Process | Accounting | Invoiceable condition terpenuhi | Invoice Posted, Cancelled, Credit Note, atau fully settled sesuai hasil validasi Accounting | `account_move`, `account_move_line`, SO invoice progress | Ready / Partial |
| `CT-13` | Payment / Collection | Document / Process | Accounting | Invoice Posted dan memiliki receivable | Payment dan saldo receivable telah konsisten serta outstanding dapat dijelaskan | payment record dan receivable reconciliation — keduanya wajib dibandingkan | Investigation Pending |

## 4. Posisi Approval dalam Control Tower

Approval **tidak dijadikan satu tahap umum yang menampung semua approval**. Approval tampil pada tahap dokumen yang relevan:

- approval / Confirm Sales Order pada `CT-01`;
- approval ROP pada `CT-06`;
- review Log Note dan Confirm Purchase Order pada `CT-07`;
- request dan approval `Lock` / `Unlock` sebagai overlay pada dokumen yang dikoreksi;
- approval exception sebagai overlay pada anomaly terkait.

Dengan model ini, user dapat melihat dokumen sedang tertahan pada approval apa tanpa memisahkannya dari konteks proses aslinya.

## 5. Cabang Flow yang Sah

Semua customer flow diawali dengan:

```text
CT-00 Customer PO / Confirmed Quotation
→ CT-01 Sales Order & Approval
→ CT-02 Distribusi JO / Operational Handover
→ CT-03 Fulfilment Decision
```

### 5.1 Trading dari Stock

```text
CT-03 Fulfilment Decision = FROM_STOCK
→ CT-11 Delivery
→ CT-12 Invoice
→ CT-13 Payment
```

### 5.2 Sales Order dari Internal Order

```text
CT-03 Fulfilment Decision = FROM_INTERNAL_ORDER
→ CT-04 Internal Order
→ CT-05 Manufacturing Planning
→ CT-09 Material Transfer
→ CT-10 Production / Finish Good
→ CT-11 Delivery
→ CT-12 Invoice
→ CT-13 Payment
```

### 5.3 Make-to-Order / JO

```text
CT-03 Fulfilment Decision = MAKE_TO_ORDER
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

### 5.4 Mixed Source

Satu SO dapat memiliki line dari Stock, IO, dan MO. Status node dihitung per line terlebih dahulu lalu diringkas pada level SO. SO diberi label `MIXED_SOURCE` dan detail line wajib tersedia pada drill-down.

## 6. Odoo Coverage versus Proses Aktual

Belum seluruh user dan kegiatan operasional berjalan di Odoo. Produksi adalah contoh utama.

Dashboard wajib membedakan:

- **ERP Status**: status yang dapat dibuktikan dari Odoo;
- **Operational Status**: kondisi aktual berdasarkan user atau dokumen eksternal;
- **Data Confidence**: High, Medium, Low, atau Manual;
- **Coverage Mode**: Odoo, Hybrid, atau Manual.

Status Odoo tidak boleh langsung dianggap membuktikan pekerjaan fisik selesai apabila proses tersebut masih memakai dokumen atau komunikasi di luar Odoo.

## 7. Elemen Cross-Cutting

Elemen berikut menjadi overlay pada tahap proses, bukan alur terpisah:

- approval yang relevan dengan dokumen;
- anomaly aktif;
- request `Lock` / `Unlock`;
- Log Note terakhir;
- Rule ID dan SOP section terkait;
- owner dan target tindak lanjut;
- data confidence dan coverage mode.

Formal ticketing ditunda sampai validasi proses dan rule SOP-dashboard selesai.

## 8. Aturan Klik Tahap Proses

Saat user mengklik satu tahap proses, aplikasi minimal menampilkan:

1. jumlah record aktif;
2. native status dan canonical status;
3. operational/manual status bila tersedia;
4. aging;
5. record blocked atau partial;
6. anomaly dan severity;
7. process owner dan approver terkait;
8. dokumen upstream dan downstream;
9. link ke detail record atau dashboard existing;
10. SOP section dan Rule ID;
11. data confidence, coverage mode, dan source timestamp.

## 9. Keputusan yang Sudah Dipakai

- Business journey dimulai dari Customer PO / Confirmed Quotation.
- Semua Quotation dalam scope dianggap sudah dikonfirmasi customer dan memiliki PO customer.
- Sales Order tetap menjadi root teknis awal customer journey.
- Distribusi JO adalah tahap handover setelah SO approved/confirmed.
- Distribusi JO masih manual/non-Odoo, tetapi diarahkan agar ke depan tercatat di Odoo.
- Approval menempel pada tahap dokumen terkait, bukan satu node approval umum.
- Nomor IO menjadi root untuk internal production journey.
- Produksi diperlakukan sebagai proses hybrid Odoo-manual sampai coverage aktual tervalidasi.
- Payment belum boleh disimpulkan hanya dari satu indikator; payment record dan receivable reconciliation harus diuji konsistensinya.
- Formal ticketing ditunda; fokus saat ini adalah validasi proses, SOP, source data, dan dashboard.
- Status asli Odoo tetap disimpan; canonical status hanya interpretasi business-facing.

## 10. Open Validation Items

1. Bukti minimum bahwa Customer PO / confirmed quotation telah menjadi dasar SO.
2. Bentuk bukti Distribusi JO saat ini dan rancangan pencatatannya di Odoo ke depan.
3. Bagian proses Produksi mana yang sudah dilakukan di Odoo dan mana yang masih manual.
4. Validasi Accounting terhadap payment record, partial payment, residual receivable, dan reconciliation.
5. Apakah satu layar hanya menampilkan PT Nobi Putra Angkasa atau disiapkan multi-company sejak awal.