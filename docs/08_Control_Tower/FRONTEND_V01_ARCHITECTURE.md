# Arsitektur Frontend Control Tower v0.1

## Batas Implementasi

Frontend memakai stack dashboard yang sudah ada: FastAPI, HTML, CSS, dan JavaScript
tanpa framework atau dependency baru. Satu halaman terlindungi,
`/dashboard/control-tower`, memilih empat view melalui parameter URL `view`:

- `overview` — ringkasan kesehatan proses;
- `validation` — matriks validasi SOP;
- `exceptions` — daftar kerja pengecualian;
- `journey` — hubungan dokumen berdasarkan model dan native ID.

Alur data tetap:

`respons API -> adapter normalisasi -> view model halaman -> renderer UI -> DOM`

`control-tower-adapter.js` menjadi satu-satunya tempat untuk label status,
bahasa bisnis, klasifikasi aktif/historis, severity, confidence, owner, dan tautan
Journey. Perhitungan rule tetap berada di PostgreSQL/API.

## Koreksi API Minimum

Inventaris dilakukan terhadap respons loopback terautentikasi pada 21 Juli 2026.
Perubahan berikut diperlukan sebelum frontend dapat memenuhi kontrak v0.1.

| Endpoint | Respons aktual | Kebutuhan yang belum tersedia | Tambahan minimum | Alasan adapter saja tidak cukup | Risiko regresi |
| --- | --- | --- | --- | --- | --- |
| aplikasi kanonis `src.api:app` | Router Control Tower hanya terpasang melalui `src.control_tower_app:app` | Runtime README/Docker harus menyediakan API yang sama | Pasang router yang sudah ada sekali pada app kanonis; wrapper hanya mengekspor app tersebut | Frontend pada runtime kanonis akan menerima 404 | Rendah; daftar route diuji |
| `GET /api/control-tower/exceptions` | Filter hanya rule, status, severity, dan owner | Filter proses, dokumen, dan tanggal harus tetap server-side | Tambah parameter terikat untuk `sop_section`, pencarian nomor dokumen, dan rentang `detected_at` | Memuat 605 baris lalu memfilter di browser melanggar batas efisiensi | Rendah; query tetap read-only dan terparameterisasi |
| `GET /api/control-tower/journey/{model}/{id}` | Root membawa `payload` mentah; relasi tidak membawa state parent/child | State setiap dokumen dan bukti langsung/turunan tanpa payload tak terbatas | Hapus `payload`, left join snapshot state, dan beri `relation_evidence` dari depth | Frontend tidak boleh menebak state atau menghapus data yang sudah terkirim lewat jaringan | Rendah; field lama yang sensitif sengaja dihapus, field relasi hanya ditambah |
| `GET /api/control-tower/io-health` | Hanya row page dan total 824 product-UoM | Ringkasan 118 root IO tanpa mengambil seluruh dataset | Tambah agregat `summary` | Distinct root tidak dapat dihitung dari satu page | Rendah; agregat read-only dari view yang sama |

Tidak ada perubahan pada klasifikasi bisnis, scope PO 2026, Payment, Distribusi JO,
ekstraksi, atau Odoo. Semua query tetap read-only.

## State dan Keamanan

- Middleware session dashboard tetap menjadi proteksi halaman.
- Dependency auth yang sudah ada tetap melindungi seluruh API Control Tower.
- Respons `401` dirender sebagai state sesi berakhir, bukan error teknis.
- UI menyediakan loading, empty, error, retry, stale, dan selected-filter state.
- Peringatan stale memakai ambang presentasi frontend 24 jam; ambang ini tidak
  mengubah klasifikasi bisnis atau status backend.
- Raw technical status dan rule ID hanya muncul sebagai referensi sekunder.
- `payload` snapshot Odoo tidak dikirim ke browser melalui Record Journey.

## Validasi

- `pytest` untuk route/auth, query filter, agregat IO, dan sanitasi Journey;
- `node:test` untuk adapter status, bahasa bisnis, klasifikasi, PO 2026,
  backorder historis, Payment, Distribusi JO, empty/error/session/stale state;
- smoke API loopback terautentikasi;
- browser smoke desktop dan viewport sempit dengan pemeriksaan console,
  interaksi filter, pagination, Journey, dan state error/sesi.
