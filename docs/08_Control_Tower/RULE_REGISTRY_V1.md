# Rule Registry v1 — SOP and Dashboard Contract

Status: Phase 0 Draft v2 — validation-first  
Scope: PT Nobi Putra Angkasa  
Purpose: Menjadi kontrak antara business rule SOP, proses aktual, data source, dashboard exception, owner, dan tindakan.

## 1. Rule Status

- `READY`: data dan logic dasar tersedia; tetap perlu sample reconciliation sebelum production use.
- `PARTIAL`: sebagian data tersedia, exception logic atau evidence belum lengkap.
- `MANUAL_VALIDATION`: kondisi hanya dapat diverifikasi dari user/dokumen eksternal.
- `MISSING_DATA`: source of truth belum tersedia.
- `INVESTIGATION`: beberapa kandidat source tersedia tetapi konsistensinya belum dibuktikan.
- `NEEDS_BUSINESS_DECISION`: memerlukan keputusan process owner/VP Operations.
- `NOT_IMPLEMENTED`: rule terdefinisi tetapi belum dibuat pada SQL/API.
- `DEFERRED`: bukan scope validasi/implementasi sekarang.

## 2. Initial Rule Registry

| Rule ID | Node | Business Rule / Exception | Source | Exception Logic / Validation | Severity | Owner | SOP Ref | Readiness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `QTN-001` | CT-00 | SO harus memiliki dasar Customer PO dan confirmed quotation | Customer PO, quotation, attachment/reference, SO | Validasi sample bahwa dasar order dapat ditelusuri; belum menjadi automated exception | High | Marketing / Admin Sales | SOP 3.1 / business start | Manual Validation |
| `SO-001` | CT-01 | Customer Reference wajib tersedia sesuai kebutuhan order | `sale_order` | Kosong pada SO aktif tanpa accepted exception | Medium | Marketing | SOP 3.1 | Ready |
| `SO-002` | CT-01 | Delivery Date atau Delivery Time wajib tersedia | `sale_order` | Keduanya kosong pada SO aktif | Medium | Marketing | SOP 3.1 | Ready |
| `SO-003` | CT-03 | SO Confirmed harus memiliki klasifikasi fulfilment | SO source views | Source `UNKNOWN_SOURCE` | High | Marketing / PPIC | SOP 3.1–3.2 | Ready |
| `SO-004` | CT-03 | JO dan IO tidak boleh terisi bersamaan kecuali exception sah | SO/MO context | Kedua referensi terisi dan tidak ada approved exception | High | Marketing / PPIC | SOP 3.2 | Ready |
| `SO-005` | CT-01 | SO Cancelled tidak boleh memiliki dokumen turunan aktif | SO, MO, Delivery, Invoice | SO Cancelled dan salah satu turunan tetap aktif | High | Multi-owner | Control Point 5.1 | Partial |
| `SO-006` | CT-01 | Perubahan quantity SO wajib direkonsiliasi ke MO/Delivery | SO lines, MO, Delivery | Quantity downstream berbeda setelah perubahan tanpa Log Note/exception | High | Marketing / PPIC / WHD | Control Point 5.1 | Partial |
| `APR-001` | Node dokumen terkait | Approval tidak boleh tertahan melewati threshold | status dokumen, approval records, Log Note | Waiting lebih lama dari SLA per jenis dokumen | Medium/High | Approver terkait | SOP node terkait | Needs Business Decision |
| `APR-002` | Semua node terkait | Unlock wajib memiliki request dan approval pada Log Note | dokumen + message/log | Unlock terjadi tanpa `[UNLOCK REQUEST]` dan keputusan | High | Owner dokumen / Approver | Governance 5.13 | Partial |
| `DIST-001` | CT-02 | Distribusi JO dilakukan setelah SO approved/confirmed | SO status + evidence distribusi | SO belum approved tetapi sudah didistribusikan, atau SO approved namun handover belum dapat dibuktikan | High | Marketing / Admin Sales | SOP Sales Order / Distribusi JO | Manual Validation / Future Odoo |
| `DIST-002` | CT-02 | Distribusi JO harus mengacu pada SO/quotation yang benar dan penerima terkait | evidence distribusi, SO, recipient list | Referensi order atau penerima tidak sesuai | Medium/High | Marketing / Admin Sales | SOP Sales Order / Distribusi JO | Manual Validation |
| `IO-001` | CT-04 | SO dengan Nomor IO harus terhubung ke IO yang valid | SO–IO bridge | Referensi ada tetapi bridge tidak terbentuk | High | Marketing / PPIC | SOP 3.1–3.2 | Ready |
| `MO-001` | CT-05 | MTO/JO harus memiliki MO | SO source + MO context | Source MTO tetapi MO tidak ditemukan | High | PPIC | SOP 3.2 | Ready |
| `MO-002` | CT-05 | MO Confirmed tanpa component hanya boleh sementara | MO + component move | Tidak ada component melewati threshold atau sebelum MAD | Medium/High | PPIC | SOP 3.2 | Partial |
| `MO-003` | CT-10 | Parent MO tidak boleh selesai sebelum Child MO | Parent/Child MO | Parent Done saat Child belum Done/Cancelled sah | High | PPIC | Case 4.2 | Ready/Partial |
| `MO-004` | CT-10 | Child output harus cukup untuk Parent consumption | Parent/Child MO + moves | Output Child lebih kecil dari consumption Parent tanpa exception | High | PPIC | Case 4.2 | Partial |
| `MO-005` | CT-09 | MO Cancelled tidak boleh meninggalkan material di WIP tanpa disposition | MO + stock moves | MO Cancelled dan saldo/movement terkait masih di WIP | High | PPIC / WHD | Control Point 5.2 | Partial |
| `MO-006` | CT-10 | Consumption harus sesuai movement Pre-Production → Virtual Production | component moves | Actual consumption tidak dapat direkonsiliasi | High | PPIC | SOP 3.6 | Partial |
| `MO-007` | CT-10 | Output harus sesuai movement Virtual Production → Post-Production | finished moves | Produced quantity tidak dapat direkonsiliasi | High | PPIC | SOP 3.6 | Partial |
| `MO-008` | CT-10 | MO Done harus diikuti transfer FG dari Post-Production ke Stock | MO + output transfer | MO Done, FG tertahan di Post-Production melewati threshold | High | PPIC / WHD | SOP 3.6 | Partial |
| `MO-009` | CT-10 | Empty Panel FF5 harus memiliki transfer KRW → FF5 yang lengkap | child/parent MO + cross-site move | Consumption FF5 lebih besar dari transfer valid | High | PPIC / WHD | Case 4.7 | Partial |
| `PROD-001` | CT-10 | Status Odoo tidak boleh menjadi satu-satunya bukti produksi fisik/QC selesai selama coverage masih hybrid | MO + production document/manual evidence | ERP menunjukkan selesai tetapi bukti operasional belum tersedia/terverifikasi | High | PPIC / Produksi | SOP 3.6 | Manual Validation / Partial |
| `ROP-001` | CT-06 | ROP Approved harus membentuk RFQ | ROP + RFQ | Approved tanpa RFQ melewati threshold | High | Procurement | SOP 3.3 | Partial |
| `ROP-002` | CT-06 | ROP Cancelled tidak boleh memiliki RFQ/PO aktif | ROP, RFQ, PO | ROP Cancelled dengan downstream aktif | High | Procurement | Control Point 5.3 | Partial |
| `PO-001` | CT-07 | PO Confirmed harus memiliki Receipt | PO + Receipt | Confirmed tanpa Receipt | High | Procurement | SOP 3.4 | Ready/Partial |
| `PO-002` | CT-07 | Perubahan quantity PO harus direkonsiliasi ke Receipt | PO line + receipt move | Quantity PO dan Receipt berbeda setelah perubahan tanpa keputusan | High | Procurement / WHD | Control Point 5.4 | Partial |
| `PO-003` | CT-07 | PO Cancelled tidak boleh memiliki Receipt aktif | PO + Receipt | Cancelled dengan Receipt non-cancelled | High | Procurement / WHD | Control Point 5.4 | Ready/Partial |
| `PO-004` | CT-07 | PO hanya boleh diubah oleh Procurement | audit/write user bila tersedia | Perubahan oleh role lain | High | Procurement / VP Operations | SOP 3.4 | Missing Data / Access Audit |
| `PO-005` | CT-07 | Review Assistant VP pada Log Note wajib sebelum Confirm | PO + Log Note | PO Confirmed tanpa review note valid | High | Assistant VP / VP Operations | SOP 3.4 | Partial |
| `RCV-001` | CT-08 | Receipt quantity harus sesuai barang aktual dan Backorder | receipt moves | Partial tanpa Backorder atau explanation | High | WHD | SOP 3.5 | Partial |
| `RCV-002` | CT-08 | Receipt harus masuk ke lokasi sesuai Deliver To | PO + Receipt location | Destination tidak sesuai mapping | High | WHD | SOP 3.5 | Partial |
| `RCV-003` | CT-08 | Receipt tidak boleh Done tanpa bukti pemeriksaan | Receipt + evidence | Done tanpa attachment/reference/checklist | High | WHD / Requester | SOP 3.5 | Manual Validation / Partial |
| `RCV-004` | CT-08 | Service Receipt harus memiliki BAP atau bukti kontrak | Receipt + evidence | Service Done tanpa BAP/reference | High | Requester / WHD | Case 4.4 | Manual Validation / Partial |
| `STK-001` | CT-09/10 | Lokasi legacy KRW/FG dan FF5/FG tidak boleh digunakan | stock quant/move/location | Current balance non-zero atau movement baru setelah cut-off | High | WHD / Data Health Owner | Location Governance | Partial; Cut-off Missing |
| `STK-002` | CT-09 | Bon berbeda dari actual consumption | transfer + component move | Bon otomatis dianggap consumed atau tidak dapat dibedakan | High | PPIC / WHD | SOP 3.6 | Partial |
| `DEL-001` | CT-11 | Delivery parsial wajib menggunakan Backorder | SO line + Delivery | Delivered < demand dan tidak ada backorder/decision | High | WHD | SOP 3.7 | Ready/Partial |
| `DEL-002` | CT-11 | Delivery Done harus sesuai actual shipment | Delivery + SO line + evidence | Quantity/status tidak sesuai bukti aktual | Critical/High | WHD | SOP 3.7 | Partial |
| `DEL-003` | CT-11 | DO Manual harus direkonsiliasi ke Delivery normal | Internal Transfer + Delivery | DO Manual terbuka/tidak matched setelah MO selesai | Critical/High | WHD | Case 4.1 | Partial |
| `INV-001` | CT-12 | Invoice progress harus sesuai quantity/milestone yang dapat ditagih | SO line + invoice | Invoiceable tersisa melewati threshold tanpa reason | Medium/High | Accounting | Case 4.5 | Partial |
| `INV-002` | CT-12 | DP harus sesuai kontrak dan Payment Terms | Invoice + SO + contract evidence | Nilai/percentage tidak sesuai approved basis | High | Accounting | Case 4.5 | Needs Business Decision/Evidence |
| `INV-003` | CT-12 | DP harus diperhitungkan pada pelunasan | Invoice chain | DP belum direkonsiliasi ke final invoice | High | Accounting | Case 4.5 | Partial/Missing Mapping |
| `PAY-001` | CT-13 | Status collection harus konsisten antara payment record dan receivable reconciliation | invoice, payment record, residual, reconciliation | Kedua indikator berbeda atau belum dapat dijelaskan | High | Accounting | Accounting SOP Pending | Investigation |
| `PAY-002` | CT-13 | Partial payment tidak boleh ditampilkan sebagai fully paid | payment + invoice residual + reconciliation | Payment ada tetapi residual/reconciliation menunjukkan outstanding | High | Accounting | Accounting SOP Pending | Investigation |
| `GOV-001` | Semua | Koreksi, Cancel, Lock/Unlock wajib memiliki Log Note | dokumen + Log Note | Action terjadi tanpa request, reason, approval, completion note | Medium/High | Owner / Approver | Governance 5.13 | Partial |
| `GOV-002` | Semua | Critical/High anomaly nantinya wajib memiliki ticket pusat | anomaly + ticket | Future rule setelah ticketing dipilih | High | Data Health Owner | Governance 5.13 | Deferred |
| `GOV-003` | Semua | Closed ticket nantinya wajib memiliki evidence dan verifier manusia | ticket | Future rule setelah ticketing tersedia | High | Coordinator / Process Owner | AI SOP Governance | Deferred |

## 3. Rule Execution Output

Setiap rule menghasilkan record standar:

```text
rule_id
rule_version
sop_version
validation_version
root_type
root_id
node_id
document_model
document_id
document_number
native_status
operational_status
coverage_mode
is_exception
severity
confidence
status_reason
process_owner
approver
evidence_required
suggested_action
validation_status
detected_at
source_updated_at
```

Rule berstatus `MANUAL_VALIDATION`, `INVESTIGATION`, atau `MISSING_DATA` tidak boleh menghasilkan label confirmed error tanpa human review.

## 4. Required Test Cases

Setiap rule wajib memiliki sesuai relevansi:

- `VALID_NORMAL`;
- `INVALID_EXCEPTION`;
- `VALID_ACCEPTED_EXCEPTION`;
- `CANCELLED`;
- `PARTIAL`;
- `MISSING_DATA`;
- `MANUAL_EVIDENCE`;
- `SOURCE_CONFLICT`;
- `BOUNDARY_DATE` untuk aging/cut-off.

## 5. Current Validation Method

```text
Pilih sample transaksi
→ Baca SOP expected flow
→ Cek Odoo record dan related documents
→ Cek evidence operasional/manual
→ Bandingkan dengan existing dashboard output
→ Klasifikasikan mismatch:
   Data Error / Linkage Gap / Dashboard Rule Gap / SOP Gap / Valid Exception
→ Process Owner review
→ Rule mapping approved or revised
```

## 6. Change Control

Perubahan rule tidak boleh dilakukan hanya karena query menghasilkan terlalu banyak exception.

```text
Mismatch / False Positive
→ Review data, evidence, dan SOP
→ Tentukan apakah data, dashboard rule, atau SOP yang perlu berubah
→ Human approval
→ Update rule_version dan/atau sop_version
→ Regression test
→ Publish
```

Formal ticketing menjadi bagian loop setelah proses dan mapping rule tervalidasi.