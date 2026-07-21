# Implementasi Control Tower Health v0.1 — Validasi SOP

**Status:** feature implementation, read-only, belum digabung ke `main`  
**Branch:** `feature/control-tower-sop-validation-v0`  
**Scope awal:** PT Nobi Putra Angkasa (`res.company.id = 3`, dapat dioverride)  
**Bahasa output user:** Bahasa Indonesia pada tahap UI; API mempertahankan kode status stabil.

## 1. Tujuan

Control Tower Health v0.1 mengubah SOP yang sudah dirangkum menjadi hipotesis yang dapat diuji terhadap data Odoo aktual.

```text
SOP Rule
→ Native Odoo Evidence
→ Document Link Graph
→ Record-Level Validation
→ SOP Validation Summary
→ Exception Worklist
→ Human Review
```

Hasil `MISMATCH` tidak otomatis berarti user salah atau SOP salah. Hasil tersebut berarti terdapat ketidaksesuaian yang perlu diklasifikasikan sebagai:

- data Odoo salah/tidak lengkap;
- linkage dashboard salah;
- rule dashboard kurang konteks;
- SOP tidak sesuai proses aktual;
- proses tidak mengikuti SOP; atau
- valid exception yang perlu approval.

## 2. Guardrail

- Odoo hanya dibaca melalui `search`, `read`, `search_read`, `search_count`, dan `fields_get`.
- Tidak ada `create`, `write`, `unlink`, raw SQL ke Odoo, atau write-back dashboard.
- Snapshot dan rule result hanya ditulis ke PostgreSQL lokal dashboard.
- Run yang gagal tidak menjadi sumber view aktif; view hanya memakai extraction run terbaru yang `COMPLETED`.
- Relasi native diberi confidence `HIGH`.
- Exact text reference diberi confidence `MEDIUM` dan tetap membutuhkan review.
- Payment KPI final tidak diterbitkan sebelum keputusan Accounting.
- Distribusi JO tetap `MANUAL_EVIDENCE_REQUIRED` dan tidak diinferensikan dari state Odoo.

## 3. Komponen

### 3.1 Native Relation Extractor

File:

```text
src/control_tower/relation_extractor.py
```

Output PostgreSQL:

| Table | Fungsi |
| --- | --- |
| `ct_extraction_run` | Audit setiap extraction run dan status publish. |
| `ct_native_record_snapshot` | Snapshot JSONB yang mempertahankan native ID. |
| `ct_document_link` | Parent/child graph dengan link type, confidence, dan evidence. |

Model awal:

- Sales Order dan Sales Order Line;
- Approval Request dan Approval Product Line;
- Manufacturing Order;
- Purchase Order dan Purchase Order Line;
- Stock Picking dan Stock Move;
- Account Move, Account Move Line, dan Partial Reconciliation.

Relasi penting:

- `SO_TO_IO` langsung dari many-to-many SO;
- `SO_TO_LINE`;
- `IO_TO_MO_REFERENCE`;
- `SO_TO_MO_ORIGIN` sebagai exact text secondary evidence;
- `PO_TO_LINE`;
- `PO_TO_RECEIPT` dari native PO Line → Stock Move → Picking;
- `SO_TO_DELIVERY`;
- `MO_TO_COMPONENT_MOVE` dan `MO_TO_FINISHED_MOVE`;
- `SO_TO_INVOICE` dari SO Line → Account Move Line → Account Move;
- payment/reconciliation graph untuk traceability saja.

### 3.2 SQL Read Model

File:

```text
sql/09_control_tower_sop_validation_v0.sql
```

Views:

| View | Fungsi |
| --- | --- |
| `vw_ct_current_run` | Extraction run terbaru yang selesai. |
| `vw_ct_native_record_snapshot_current` | Snapshot aktif. |
| `vw_ct_document_links` | Direct/derived link aktif. |
| `vw_ct_document_paths` | Recursive journey sampai kedalaman 5. |
| `vw_ct_io_health` | Production dan utilization IO secara konservatif. |
| `vw_ct_rule_catalog` | Registry rule v0.1. |
| `vw_ct_rule_results` | Expected versus actual per record. |
| `vw_ct_sop_validation_summary` | Agregasi validasi per SOP rule. |
| `vw_ct_exception_worklist` | Investigation queue read-only. |

## 4. Rule v0.1

| Rule | Arti | Treatment |
| --- | --- | --- |
| `SO-PO-001` | Customer Reference dan Customer PO Date pada SO Confirmed 2026+ | Deterministic |
| `SO-SOURCE-001` | Source fulfilment harus dapat diklasifikasikan | Linkage-aware |
| `SO-CANCEL-001` | SO Cancelled tidak memiliki downstream operasional terbuka | Deterministic graph |
| `PO-CANCEL-001` | PO Cancelled tidak memiliki Receipt terbuka | Deterministic graph |
| `PO-DRAFT-001` | Draft PO dengan Receipt terbuka perlu review | `PARTIAL_MATCH`, bukan tuduhan reset |
| `SO-IO-MO-001` | Kandidat `MO_SUPPRESSED_BY_IO` | Automation evidence |
| `IO-PROD-001` | Production status IO | Provisional exact product/UoM |
| `IO-UTIL-001` | Utilization status IO | Provisional; multi-IO tidak diinferensikan |
| `JO-DIST-001` | Evidence Distribusi JO | Manual evidence only |
| `PAY-001` | Payment/reconciliation | Owner decision required; tanpa record result final |

Status validasi:

```text
VALIDATED
PARTIAL_MATCH
MISMATCH
MANUAL_EVIDENCE_REQUIRED
DATA_LINKAGE_GAP
VALID_EXCEPTION
NOT_TESTED
```

## 5. Menjalankan Refresh

Gunakan environment Odoo/PostgreSQL yang sama dengan dashboard.

```bash
python scripts/run_control_tower_refresh.py
```

Pilihan:

```bash
python scripts/run_control_tower_refresh.py --company-id 3
python scripts/run_control_tower_refresh.py --extract-only
python scripts/run_control_tower_refresh.py --sql-only
```

Validasi database setelah refresh:

```bash
python scripts/validate_control_tower.py
```

Menjalankan API dengan router Control Tower:

```bash
python -m uvicorn src.control_tower_app:app --host 127.0.0.1 --port 8000
```

## 6. Endpoint

Semua endpoint mengikuti session authentication dashboard yang ada.

```text
GET /api/control-tower/health
GET /api/control-tower/sop-validation
GET /api/control-tower/exceptions
GET /api/control-tower/journey/{root_model}/{root_id}
GET /api/control-tower/io-health
```

Contoh filter worklist:

```text
/api/control-tower/exceptions?severity=HIGH
/api/control-tower/exceptions?rule_id=PO-CANCEL-001
/api/control-tower/exceptions?validation_status=DATA_LINKAGE_GAP
```

## 7. Acceptance Criteria v0.1

1. Tidak memakai display name sebagai primary join pada graph baru.
2. SO–IO many-to-many tersimpan satu row per native relation.
3. Setiap rule result memiliki expected dan actual condition.
4. Mismatch dapat ditelusuri ke record dan document path.
5. Manual evidence tidak ditampilkan sebagai confirmed error.
6. Multi-IO dan product/UoM conflict menghasilkan `DATA_LINKAGE_GAP`/`DATA_EXCEPTION`, bukan alokasi buatan.
7. Run gagal tidak mengganti current published snapshot.
8. Payment KPI tidak dipublikasikan.
9. Tidak ada write-back ke Odoo.

## 8. Batas Validasi Saat Ini

Implementasi sudah ditulis dan unit test pure-Python tersedia. Namun branch ini belum boleh dianggap tervalidasi terhadap database aktual sebelum:

1. refresh dijalankan pada PostgreSQL yang berisi hasil sync terbaru;
2. SQL migration berhasil;
3. `validate_control_tower.py` lulus;
4. angka summary direkonsiliasi terhadap closure audit;
5. sampel record dibuka di Odoo dan dibandingkan dengan API journey;
6. process owner menilai mismatch/exception hasil pertama.

Frontend Process Map belum dibuat. Tahap berikutnya hanya dilakukan setelah graph dan rule result lolos rekonsiliasi data.
