# Canonical Process Status Model

Status: Phase 0 Draft v1

## 1. Tujuan

Status asli Odoo berbeda antarmodul. Dokumen ini menetapkan bahasa status lintas proses agar Sales, Manufacturing, Purchase, Inventory, dan Accounting dapat dibaca dalam satu Control Tower.

## 2. Canonical Status

| Status | Arti Business-Facing | Contoh |
| --- | --- | --- |
| `NOT_STARTED` | Tahap seharusnya terjadi tetapi record belum terbentuk | SO MTO belum memiliki MO |
| `WAITING` | Record tersedia tetapi menunggu approval, material, informasi, atau waktu | PO menunggu Confirm VP Operations |
| `IN_PROGRESS` | Aktivitas sedang berjalan | MO Confirmed dan produksi berjalan |
| `BLOCKED` | Proses tidak boleh dilanjutkan karena kendala atau control point | Receipt menunggu keputusan overreceipt |
| `PARTIAL` | Sebagian quantity atau dokumen sudah selesai | Receipt atau Delivery memiliki Backorder |
| `COMPLETED` | Tahap selesai sesuai data dan rule yang berlaku | Delivery Done dengan quantity sesuai |
| `EXCEPTION` | Data atau flow tidak sesuai rule dan memerlukan review | PO berubah tetapi Receipt tidak berubah |
| `NOT_APPLICABLE` | Tahap tidak diperlukan pada cabang flow tersebut | PO untuk SO yang dipenuhi penuh dari Stock |
| `CANCELLED` | Dokumen atau flow dibatalkan secara sah | SO Cancelled dan turunannya sudah diselaraskan |
| `UNKNOWN` | Data belum cukup untuk menentukan status dengan aman | Source fulfilment tidak dapat diklasifikasikan |

## 3. Status Precedence

Jika satu record memenuhi lebih dari satu kondisi, gunakan prioritas berikut:

```text
EXCEPTION
→ BLOCKED
→ CANCELLED
→ PARTIAL
→ IN_PROGRESS
→ WAITING
→ NOT_STARTED
→ COMPLETED
→ NOT_APPLICABLE
→ UNKNOWN
```

Catatan:

- `EXCEPTION` tidak menghapus status operasional asli; detail harus tetap menunjukkan bahwa record mungkin juga `IN_PROGRESS` atau `PARTIAL`.
- `CANCELLED` hanya dianggap sehat jika tidak ada dokumen turunan aktif yang seharusnya ikut dihentikan.
- `COMPLETED` harus memenuhi exit condition dan tidak memiliki anomaly Critical/High terbuka.

## 4. Stage Evaluation Contract

Setiap tahap proses harus memiliki fungsi logis berikut:

```text
is_applicable(record)
is_started(record)
is_waiting(record)
is_in_progress(record)
is_partial(record)
is_completed(record)
is_cancelled(record)
has_blocker(record)
has_exception(record)
```

Output minimum:

```text
root_type
root_id
node_id
native_status
canonical_status
status_reason
owner
age_days
open_exception_count
highest_severity
last_activity_at
source_updated_at
rule_version
```

## 5. Contoh Penentuan Status

### Sales Order

- Draft quotation/SO: `WAITING`.
- SO Confirmed dengan source sudah jelas: `COMPLETED` untuk node Sales Order.
- SO Cancelled dan turunan telah diselaraskan: `CANCELLED`.
- SO Cancelled tetapi MO/Delivery aktif: `EXCEPTION`.

### Manufacturing

- MTO seharusnya membuat MO tetapi MO belum ada: `NOT_STARTED`.
- MO Draft: `WAITING`.
- MO Confirmed: `IN_PROGRESS`.
- Produksi sebagian dan ada Backorder: `PARTIAL`.
- MO Done tetapi FG belum ke Stock: `EXCEPTION` pada node Finish Good.

### Purchase Order

- RFQ Draft: `WAITING`.
- PO menunggu review atau Confirm: `WAITING`.
- PO Confirmed dan masih menunggu Receipt: `IN_PROGRESS`.
- Receipt sebagian: `PARTIAL`.
- PO Cancelled tetapi Receipt aktif: `EXCEPTION`.

### Delivery

- Delivery Waiting/Confirmed dan stock belum available: `WAITING`.
- Delivery Ready: `IN_PROGRESS`.
- Delivery sebagian dengan Backorder: `PARTIAL`.
- Delivery Done sesuai actual shipment: `COMPLETED`.
- Delivery Done tanpa bukti penerimaan atau quantity mismatch: `EXCEPTION`.

### Invoice

- Delivery/milestone terpenuhi tetapi belum invoiceable menurut agreement: `WAITING` atau `NOT_APPLICABLE` sesuai rule.
- Invoice Draft: `WAITING`.
- Invoice Posted tetapi belum lunas: node Invoice `COMPLETED`; node Payment `IN_PROGRESS`.
- Invoice dibatalkan secara sah: `CANCELLED`.

## 6. Aging

Aging dihitung dari timestamp business event terakhir yang relevan, bukan selalu `create_date`.

Contoh:

- approval: tanggal submit;
- PO arrival: Expected Arrival;
- Receipt: tanggal barang seharusnya diterima;
- Delivery: commitment/delivery date;
- invoice: tanggal invoiceable milestone;
- anomaly: tanggal issue ditemukan.

Threshold aging belum dibekukan. Sistem wajib menyimpan threshold pada Rule Registry, bukan hard-code di UI.

## 7. Aggregate Node Status

Untuk ringkasan node:

- tampilkan total per canonical status;
- tampilkan highest severity;
- tampilkan oldest age;
- jangan mengubah banyak record menjadi satu status tunggal tanpa distribusi;
- node dianggap `Healthy` hanya jika tidak ada exception Critical/High dan backlog berada dalam threshold.

## 8. Test Requirement

Setiap status harus memiliki minimal:

1. valid normal case;
2. invalid case;
3. partial case;
4. cancelled case;
5. accepted exception;
6. missing-data case.
