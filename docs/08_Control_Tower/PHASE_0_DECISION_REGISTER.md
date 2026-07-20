# Phase 0 Decision Register — Control Tower

Status: Open for Business Review

## Confirmed Working Decisions

| ID | Decision | Status |
| --- | --- | --- |
| `CTD-001` | Business-facing term is **Tahap Proses**; technical term may remain `Process Node`. | Working Confirmed |
| `CTD-002` | Odoo Protocol defines expected process; Dashboard Odoo checks actual data. | Confirmed Concept |
| `CTD-003` | Dashboard exceptions may create tickets; closed tickets may trigger AI SOP Change Proposals. | Confirmed Concept |
| `CTD-004` | Human process owners and VP Operations retain approval authority. | Confirmed |
| `CTD-005` | Sales Order is the initial root for customer order journey. | Provisional |
| `CTD-006` | Internal Order is a separate root for internal production journey. | Provisional |
| `CTD-007` | MVP is read-only and does not write back to Odoo. | Proposed |
| `CTD-008` | Missing data is shown as `Data Mapping Pending`, not as zero. | Proposed |
| `CTD-009` | PT Nobi Putra Angkasa is the initial company scope. | Existing Project Rule |

## Questions Requiring User / VP / Process Owner Decision

| ID | Question | Why It Matters | Proposed Default | Decision Owner |
| --- | --- | --- | --- | --- |
| `CTQ-001` | Apakah Quotation aktif digunakan secara konsisten di Odoo, atau customer PO langsung menjadi dasar SO? | Menentukan tahap pertama dan root journey | Mulai dari SO; Quotation tampil pending | Marketing / VP Operations |
| `CTQ-002` | Apakah Distribusi JO perlu tampil sebagai tahap proses sebelum SO? | Proses internal penting tetapi mungkin tidak memiliki object data formal | Tampilkan sebagai milestone manual bila perlu | Marketing / VP Operations |
| `CTQ-003` | Approval mana yang tampil sebagai tahap: seluruh approval atau hanya ROP/PO/Unlock? | Approval adalah cross-cutting dan dapat membuat UI terlalu kompleks | Satu node Approval dengan filter jenis | VP Operations |
| `CTQ-004` | Apakah satu SO boleh memiliki beberapa root journey karena mixed source? | Menentukan grain data dan perhitungan status | Satu SO root; status dihitung line-first | Marketing / PPIC |
| `CTQ-005` | Source of truth Payment adalah payment record, bank reconciliation, atau saldo receivable invoice? | Menentukan kapan proses dianggap Paid | Gunakan reconciliation AR setelah Accounting review | Accounting |
| `CTQ-006` | Apakah invoice DP dan pelunasan ditampilkan sebagai dua tahap atau sub-status pada Invoice? | Mempengaruhi process map dan journey | Satu node Invoice dengan sub-type DP/Final | Accounting / VP Operations |
| `CTQ-007` | Siapa Data Health Owner dan backup formal? | Diperlukan untuk assignment, verification, dan closure | Staff/Assistant VP Operations yang ditunjuk | VP Operations |
| `CTQ-008` | Tool ticket awal: Odoo Helpdesk, custom Odoo model, atau external register? | Menentukan integrasi aktif | External register/MVP table dahulu | VP Operations / Technical Owner |
| `CTQ-009` | Apakah user dapat membuka record Odoo langsung dari dashboard? | Membutuhkan URL pattern, access, dan security | Ya, read-through deep link berdasarkan hak user | Odoo Admin |
| `CTQ-010` | Berapa SLA/aging threshold per tahap dan severity? | Menentukan WAITING versus BLOCKED/EXCEPTION | Belum hard-code; simpan configurable | Process Owners / VP Operations |
| `CTQ-011` | Apakah dashboard hanya untuk PT Nobi Putra Angkasa atau dirancang multi-company sejak awal? | Mempengaruhi architecture dan filter | Data layer scoped ke NPA; desain tetap extensible | VP Operations |
| `CTQ-012` | Apakah Log Note akan disinkron dan dianalisis, atau hanya ditautkan ke Odoo? | Menentukan evidence untuk approval/Unlock | Link dahulu; parsing setelah format dibakukan | VP Operations / Odoo Admin |

## Review Method

Jawaban dapat diberikan bertahap. Setiap keputusan harus memperbarui:

1. Process Node Register;
2. Rule Registry;
3. data contract/config;
4. SOP section terkait;
5. MVP acceptance criteria bila berdampak.
