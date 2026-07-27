# Control Tower — Visual Elegance Standard

## Purpose

Menjaga Process Map tetap clean, informatif, dan terasa matang tanpa berubah menjadi wiring diagram.

## Hierarchy yang dibekukan

### Main spine

Estimasi / RKB Kasar → Quotation → Sales Order → Fulfilment → Delivery → Invoice → Payment

### Fulfilment

Fulfilment hanya memiliki dua sumber:

1. Manufacturing Order
2. From Stock / Internal Order

### Kebutuhan Material

Kebutuhan Material bukan pilihan Fulfilment. Ia merupakan supporting flow yang turun dari Sales Order:

Sales Order → RKB Pekerjaan → Cek Stock → ROP → Purchase Order → Receipt & QC

## Elegance rules

- Main connector: sekitar 1.25 px.
- Focus connector: sekitar 1.8 px.
- Supporting connector: sekitar 1 px, lebih redup atau dashed.
- Motion overlay: sekitar 2.1 px, tidak lebih tebal daripada dua kali static line.
- Arrowhead: kecil, 6 px, tidak lebih dominan daripada node.
- Maksimal satu active animated journey pada satu waktu.
- Default state tenang; supporting branches hanya muncul saat diperlukan.
- Tidak ada glow kuat, oversized arrow, atau garis tebal yang terasa seperti diagram presentasi.
- Node tetap menjadi fokus utama; garis hanya membantu mata berpindah.
- Main flow, fulfilment source, dan material-support flow harus terbaca sebagai tiga level visual berbeda.
- Pada 1024 px, pertahankan ukuran node dan gunakan horizontal scrolling daripada mengecilkan seluruh map.

## Acceptance

Desain lolos bila:

1. alur utama dipahami dalam lima detik;
2. Fulfilment tidak disalahartikan sebagai material procurement;
3. Kebutuhan Material jelas berasal dari Sales Order;
4. arrow dan motion terlihat tetapi tidak menarik perhatian berlebihan;
5. default view tidak terasa ramai;
6. focused state hanya menonjolkan satu journey.
