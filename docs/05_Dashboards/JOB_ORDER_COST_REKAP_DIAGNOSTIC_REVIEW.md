# Job Order Cost Rekap Diagnostic Review

## Executive Summary

What passed:

- SQL execution already passed in the prior validation run.
- `vw_job_order_rekap_lines` produced 29,464 rows and `vw_job_order_rekap_summary` produced 1,100 rows.
- Duplicate `report_key + product_key` validation passed with 0 duplicates.
- Cancelled record exclusion passed with 0 cancelled rows in report scope.

What needs review:

- Unmapped source rows remain material: 5606 RKB Actual rows, 6473 ROP / PEMBELIAN rows, and 10688 PO rows.
- There are 124 mixed-UoM rows where quantity comparison is not reliable yet.
- There are 1934 PO-without-ROP rows and 1402 ROP-without-PO rows that should be reviewed as process or mapping gaps.

Nothing blocks preserving the current conservative Phase 1 SQL. Before expanding mapping rules, the next phase should compare these results against one known manually prepared Excel report and review the unmapped samples with business users.

## Unmapped RKB Actual Sample

Count: 5606

| approval_line_id | approval_request_id | approval_request_numeric_id | product_name | planned_quantity | unit_of_measure | planned_subtotal | internal_order_number | job_order_number | approval_status | company_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10398 | RKB - 225IO021 | 732 | [21264] Stud Bolt FHS M6x15 ->[13945] | 4124.01 | Pcs | 7168065.501300001 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10399 | RKB - 225IO021 | 732 | [21265] Stud Bolt FHS M6x20 ->[13946] | 352.01 | Pcs | 572259.1369 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10400 | RKB - 225IO021 | 732 | [20827] Plat SPCC t2.0x1219x2438 ->[10046] | 136.34 | Lbr | 78948711.82060002 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10401 | RKB - 225IO021 | 732 | [22517] Plat SPCC t1.5x1219x2438 ->[1P00038] | 2.46 | Lbr | 1083835.6559999997 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10402 | RKB - 225IO021 | 732 | [20907] Plat SPCC t3.0x1219x2438 ->[10375] | 7.41 | Lbr | 6518008.2084 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10403 | RKB - 225IO021 | 732 | [21356] Plat SPHC t5.0x1200x2400 ->[15112] | 30.4 | Lbr | 39636962.48 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10404 | RKB - 225IO021 | 732 | [22667] MS463-1-3BG3 Push Swinghandle 133mm Padlock ->[1P00203] | 12 | Set | 1691832.5999999999 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10405 | RKB - 225IO021 | 732 | [22712] Sect. A1039 AA6063-T5 MF L=6000 ->[1P00250] | 2.6 | Btg | 116721.904 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10406 | RKB - 225IO021 | 732 | [34330] Rod Adapter   ->[1P00514] | 80.01 | Pcs | 297197.145 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10407 | RKB - 225IO021 | 732 | [22888] Round Rod EG dia 8 with double roller L=1200 ->[1P00437] | 22 | Pcs | 770000 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10408 | RKB - 225IO021 | 732 | [22604] PI5331-10-B Dual Roller Catch ->[1P00138] | 42 | Pcs | 661500 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10409 | RKB - 225IO021 | 732 | [21306] 208-9021 Rod Latch RH/LH with circlip rod fixing ->[14495] | 38 | Pcs | 1958602.46 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10410 | RKB - 225IO021 | 732 | [34328] Flat Rod PA Rod Guide ->[1P00512] | 42 | Pcs | 249900 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10411 | RKB - 225IO021 | 732 | [34327] Rod Guide A-26   ->[1P00510] | 124.01 | Pcs | 322794.3097 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10412 | RKB - 225IO021 | 732 | [22686] Engsel Countersink c/wHousing,Pen,Spie HL082 ->[1P00224] | 64.01 | Set | 1111653.3487 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10413 | RKB - 225IO021 | 732 | [21702] Key 1/4turn black DB cam 18 CL21853218C3 ->[18099] | 77 | Set | 1305150 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10414 | RKB - 225IO021 | 732 | [29948] Hinge black delrin pin PI5103B12C3  ->[1P00500] | 29 | Pcs | 282750 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10415 | RKB - 225IO021 | 732 | [21703] Key DB ZP w/logo Nobi 5mm CL5KeyZ ->[18100] | 7 | Pcs | 44800 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10416 | RKB - 225IO021 | 732 | [38089] Sticker Panel EV Charging | 3 | Set | 7500000 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |
| 10417 | RKB - 225IO021 | 732 | [21003] Roller Pengunci (Kuningan) ->[11306] | 42 | Pcs | 266826 | 225IO021 |  | pending | Nobi Putra Angkasa, PT |

Likely explanation categories:

- IO-only records: sample rows have `internal_order_number` such as `225IO021` but no `job_order_number`.
- Missing SO/JO reference: blank `job_order_number` prevents SO / JO-first mapping.
- Safe mapping may be possible later only if the IO value is proven to link to SO through `vw_sale_order_internal_order_bridge`.
- Some rows may be acceptable historical planning records not tied to the current SO / JO report scope.

## Unmapped ROP / PEMBELIAN Sample

Count: 6473

| approval_line_id | approval_request_id | approval_request_numeric_id | product_name | planned_quantity | unit_of_measure | planned_subtotal | internal_order_number | job_order_number | approval_status | approval_category_raw | company_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 130100002 | 18 | [20397] Plastik Cor t0.8 x 1000 mm ->[18675] | 30 | Roll | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 17 | 130100002 | 18 | [20147] Sarung Tangan Katun 5B   ->[10025] | 2400 | Set | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 18 | 130100002 | 18 | [20164] Masker Kain   ->[11152] | 100 | Lsn | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 19 | 130100002 | 18 | [20165] Lakban Kertas 1"   ->[11153] | 192 | Roll | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 20 | 130100002 | 18 | [20274] Lakban Plastik Bening 2"   ->[14961] | 96 | Roll | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 21 | 130100002 | 18 | [20197] Kain Majun   ->[11726] | 150 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 22 | 130100002 | 18 | [20139] Batu Gerinda Resibon 4" Steel ->[10014] | 300 | Pcs | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 23 | 130100002 | 18 | [20141] Batu Gerinda Flexible 4" (WA) ->[10017] | 300 | Pcs | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 24 | 130100002 | 18 | [20269] Cutting Wheel 4"   ->[14843] | 200 | Pcs | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 25 | 130100002 | 18 | [20320] Fiber Disc for sanding 4" Cubitron II 3M ->[16501] | 300 | Pcs | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 26 | 130100002 | 18 | [20142] Cutting Wheel 16"   ->[10019] | 25 | Pcs | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 27 | 130100002 | 18 | [20242] Plastik stretch film 500mm x 240m x 20um ->[13095] | 120 | Roll | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 28 | 130100002 | 18 | [20168] Kawat Ikat dia.1,6 Galvanize ->[11173] | 200 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 68 | 140100003 | 30 | [34433] Sealing Foam A  ->[1P00595] | 150 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 69 | 140100003 | 30 | [29445] Sealing Foam Glue B   ->[1P00596] | 60 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 75 | 140100004 | 32 | [20149] Gas Argon HP   ->[10371] | 50 | Btl | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 76 | 140100004 | 32 | [20133] Gas Oxygen (O2) Med Lab   ->[10003] | 10 | Cradle | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 95 | 150100006 | 38 | [20246] Paku 5 cm   ->[13351] | 90 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 96 | 150100006 | 38 | [20256] Paku 10 cm   ->[14037] | 60 | Kg | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |
| 98 | 150100007 | 44 | [22517] Plat SPCC t1.5x1219x2438 ->[1P00038] | 300 | Lbr | 0 |  |  | approved | PEMBELIAN | Nobi Putra Angkasa, PT |

Likely explanation categories:

- Missing JO/SO and IO references: sample PEMBELIAN rows have blank `internal_order_number` and blank `job_order_number`.
- General procurement/consumable purchases: early samples include gloves, masks, gas, tape, and similar items that may not belong to a Job Order report.
- Process gaps: procurement requests may have been created without project references.
- Mapping should not use `approval_request_numeric_id` as an IO unless future investigation proves it is a real Internal Order reference for these rows.

## Unmapped PO Sample

Count: 10688

| procurement_line_id | product_name | ordered_quantity | received_quantity | invoiced_quantity | unit_of_measure | line_subtotal | internal_order_number | job_order_number | purchase_line_state | company_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | Sewa Mobil Bulanan | 6 | 6 | 6 | Bulan | 23400000 |  |  | purchase | Nobi Elektrika Sejahtera, PT |
| 52 | Sewa Mobil Bulanan | 6 | 0 | 0 | Bulan | 21600000 |  |  | purchase | Nobi Elektrika Sejahtera, PT |
| 6379 | Jasa | 2 | 0 | 0 | Unit. | 516363800 |  |  | draft | Nobi Putra Angkasa, PT |
| 6402 | [20133] Gas Oxygen (O2) Med Lab   ->[10003] | 8 | 0 | 0 | Cradle | 7176000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6403 | [30002] Gas Argon HP 96 M3 99,99% 150 Bar ->[1G00140] | 2 | 2 | 2 | Cradle | 6720000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6404 | [22715] Cage Nut M6 SS 304   ->[1P00253] | 1300 | 1300 | 1300 | Pcs | 2730000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6407 | [25239]  Kabel NYAF 4mm2  hitam LSZH-Cable ->[1S01812] | 100 | 0 | 0 | Mtr | 1130000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6408 | [29188] Kubota V1505 Coupled w/ Stamford P1044F Assembled ->[1E00556] | 0 | 0 | 0 | Pcs | 0 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6409 | [20823] Plat SPCC t2.5x1219x2438 ->[10035] | 1 | 1 | 0 | Lbr | 787500 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6410 | [20132] Gas Oxygen (O2) Industri   ->[10002] | 5 | 5 | 5 | Btl | 225000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6411 | [20132] Gas Oxygen (O2) Industri   ->[10002] | 5 | 0 | 0 | Btl | 225000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6413 | [29933] Bolt+Nut+Fw+Sw Hex M12x220 SS316 Full Drat ->[1C00557] | 50 | 50 | 0 | Set | 5265315 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6414 | [29394] PowderCoat 1238458PX20 RAL7032 Grey207sCTX JOTUN ->[1P00396] | 1000 | 1000 | 1000 | Kg | 42000000 | 224IO038 |  | purchase | Nobi Putra Angkasa, PT |
| 6415 | [20130] GAS MIXED 20 (TBG) (20% CO2 + 80% ARGON) ->[1G00136] | 31 | 31 | 6 | Btl | 5425000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6416 | [20133] Gas Oxygen (O2) Med Lab   ->[10003] | 7 | 7 | 7 | Cradle | 6279000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6423 | [20028] Belt grinding grade #80 120 x 8996 mm Deerfos ->[1G00019] | 30 | 30 | 30 | Roll | 16050000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6431 | [29953] Socket Outlet Spine 16A 200-250VAC 50-60Hz ->[1P00620] | 300 | 300 | 300 | Pcs | 41550000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6439 | [20331] Gas Nitrogen HP puritas = 99.990% ->[16700] | 2 | 2 | 2 | Cradle | 2240000 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6442 | [21503] Plat SPHC t2.3 x 1219 x 3000 ->[16434] | 50 | 50 | 50 | Lbr | 37207250 |  |  | purchase | Nobi Putra Angkasa, PT |
| 6443 | [21588] Plat SPHC t2.3 x 1200 x 3020 ->[17261] | 30 | 30 | 30 | Lbr | 22459470 |  |  | purchase | Nobi Putra Angkasa, PT |

Likely explanation categories:

- Missing JO/SO and IO references: many sample PO lines have blank `internal_order_number` and `job_order_number`.
- Historical or non-target company data: samples include `Nobi Elektrika Sejahtera, PT`, outside current Sales Order dashboard scope.
- General procurement or services: examples include vehicle rental, services, gases, and common materials.
- IO-only records: some PO rows contain an IO number but may not match the SO-to-IO bridge used by the conservative report scope.

## Mixed UoM Sample

Count: 124

| report_key | product_key | product_name | uom_summary | rkb_actual_uom_summary | rop_uom_summary | po_uom_summary | rkb_actual_qty | rop_qty | po_qty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1250099 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lot, Pcs | Lot, Pcs |  |  | 402 | 0 | 0 |
| 1250132 | [38595] Cutting Sticker Channel Support | [38595] Cutting Sticker Channel Support | Lot, Pcs |  | Lot | Pcs | 0 | 1 | 190 |
| 1250160 | [!! - 520005] !! - Subcont, Galvanis, Painting, DLL 520005 | [!! - 520005] !! - Subcont, Galvanis, Painting, DLL 520005 | Lot, Unit., Unit. |  | Unit. | Lot, Unit. | 0 | 26 | 28 |
| 1250319 | [39436] Bolt+Nut+Fw+Sw RHSN M6x20 SS316 (neck 3mm) | [39436] Bolt+Nut+Fw+Sw RHSN M6x20 SS316 (neck 3mm) | Set, Unit | Unit | Set | Set | 120 | 200 | 200 |
| 1260077 | [21190] Plat SS 304-2B t1.5x1219x3000 ->[13189] | [21190] Plat SS 304-2B t1.5x1219x3000 ->[13189] | Lbr, Unit. | Unit. | Unit. | Lbr | 55.72 | 70 | 60 |
| 1260098 | [42518] Hanger Rod (Electro Galvanize) M10 Grade 8.8 2m Std Length c/w Double Nut, Flat and Spring Washer EG ->[HR-M10-2M] | [42518] Hanger Rod (Electro Galvanize) M10 Grade 8.8 2m Std Length c/w Double Nut, Flat and Spring Washer EG ->[HR-M10-2M] | Set, Unit. | Set | Set | Unit. | 5 | 5 | 5 |
| 1260163 | [21190] Plat SS 304-2B t1.5x1219x3000 ->[13189] | [21190] Plat SS 304-2B t1.5x1219x3000 ->[13189] | Lbr, Unit. | Unit. | Unit. | Lbr | 75.55 | 80 | 80 |
| 1260287 | [20984] Plat AA5052-H32 t2.0x1219x3000 ->[11241] | [20984] Plat AA5052-H32 t2.0x1219x3000 ->[11241] | Kg, Lbr |  | Lbr | Kg | 0 | 100 | 2000 |
| 1260287 | [21339] Plat AA5052-H32 t1.5x1219x3000 ->[14920] | [21339] Plat AA5052-H32 t1.5x1219x3000 ->[14920] | Kg, Lbr | Lbr | Lbr | Kg | 3.29 | 134 | 2000 |
| 1260287 | [40778] Plat AA5052-H32 t2,3x1219x3000 | [40778] Plat AA5052-H32 t2,3x1219x3000 | Kg, Lbr | Lbr | Lbr | Kg | 356.6 | 351 | 3000 |
| 2250054 | Jasa Transport [PRC] | Jasa Transport [PRC] | Lot, Unit. |  |  | Lot, Unit. | 0 | 0 | 2 |
| 2250093 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 18.51 | 0 | 0 |
| 2250157 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 222.34 | 0 | 0 |
| 2250168 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 47.88 | 0 | 0 |
| 2250169 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 29.35 | 0 | 0 |
| 2250171 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 102.824 | 0 | 0 |
| 2250178 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 580.5 | 0 | 0 |
| 2250178 | [21083] Rivet AL M3.2x8 mm   ->[11721] | [21083] Rivet AL M3.2x8 mm   ->[11721] | Dus 1000, Pcs | Pcs |  | Dus 1000 | 5081.45 | 0 | 4 |
| 2250178 | [21257] Plat AA1100 H-14 t1.4x1219x2438 ->[13853] | [21257] Plat AA1100 H-14 t1.4x1219x2438 ->[13853] | Lbr, Unit. | Unit. |  | Lbr | 58.17 | 0 | 50 |
| 2250180 | !! - OTHERS (RKB) | !! - OTHERS (RKB) | Lbr, Lot | Lbr, Lot |  |  | 2.89 | 0 | 0 |

These rows should not be trusted for quantity comparison yet because the same `report_key + product_key` combines different UoMs such as `Lot`, `Pcs`, `Unit`, `Lbr`, `Kg`, or package units. Quantity formulas can compare like-for-like units only after UoM normalization or business-approved conversion rules exist.

## PO without ROP Sample

Count: 1934

| report_key | product_key | product_name | po_qty | po_subtotal | po_status_summary | rkb_actual_qty | rop_qty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1240144 | Jasa Transport [PRC] | Jasa Transport [PRC] | 1 | 15000000 | purchase | 0 | 0 |
| 1240163 | [20495] Bolt+Nut+Fw+Sw Hex M8x30 HDG ->[1C00066] | [20495] Bolt+Nut+Fw+Sw Hex M8x30 HDG ->[1C00066] | 1484 | 2597000 | purchase | 0 | 0 |
| 1240166 | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | 7000 | 26705000 | purchase | 0 | 0 |
| 1240166 | [20576] Bolt+Nut+Fw+Sw JP M6x20 SS316 ->[1C00170] | [20576] Bolt+Nut+Fw+Sw JP M6x20 SS316 ->[1C00170] | 12000 | 48000000 | purchase | 0 | 0 |
| 1240166 | [20651] Bolt+Nut+Fw+Sw Hex M8x70 SS316 ->[1C00251] | [20651] Bolt+Nut+Fw+Sw Hex M8x70 SS316 ->[1C00251] | 200 | 1990000 | purchase | 0 | 0 |
| 1240166 | [29426] Ring Plastik M6 lokal OD=12,16 ID=6,54 t=1,6mm ->[1C00546] | [29426] Ring Plastik M6 lokal OD=12,16 ID=6,54 t=1,6mm ->[1C00546] | 23500 | 11750000 | purchase | 0 | 0 |
| 1240173 | [21401] Vinyl wire V-22 Yellow   ->[15435] | [21401] Vinyl wire V-22 Yellow   ->[15435] | 200 | 132000 | purchase | 0 | 0 |
| 1240173 | [23975] Cable skun Ring 22 - 12   ->[1S00276] | [23975] Cable skun Ring 22 - 12   ->[1S00276] | 100 | 820000 | purchase | 0 | 0 |
| 1240173 | [24682] Kabel NYAF kuning-hijau diameter 35mm ->[1S01179] | [24682] Kabel NYAF kuning-hijau diameter 35mm ->[1S01179] | 20 | 1830000 | purchase | 0 | 0 |
| 1240173 | [26492] Kabel NYAF Kuning-Hijau diameter 6 mm ->[15894] | [26492] Kabel NYAF Kuning-Hijau diameter 6 mm ->[15894] | 20 | 350000 | purchase | 0 | 0 |
| 1240173 | [28972] Cable skun ring M6 untuk kabel 5,5 mm ->[15150] | [28972] Cable skun ring M6 untuk kabel 5,5 mm ->[15150] | 200 | 150000 | purchase | 0 | 0 |
| 1250079 | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | 800 | 2867024 | purchase | 0 | 0 |
| 1250079 | [20576] Bolt+Nut+Fw+Sw JP M6x20 SS316 ->[1C00170] | [20576] Bolt+Nut+Fw+Sw JP M6x20 SS316 ->[1C00170] | 1200 | 6042168 | purchase | 0 | 0 |
| 1250082 | [20728] Bolt+Nut+Fw+Sw RHSN M10x25 SS316 (neck 3.0mm) ->[1C00357] | [20728] Bolt+Nut+Fw+Sw RHSN M10x25 SS316 (neck 3.0mm) ->[1C00357] | 400 | 5873872 | purchase | 0 | 0 |
| 1250094 | [20728] Bolt+Nut+Fw+Sw RHSN M10x25 SS316 (neck 3.0mm) ->[1C00357] | [20728] Bolt+Nut+Fw+Sw RHSN M10x25 SS316 (neck 3.0mm) ->[1C00357] | 1500 | 22027020 | purchase | 0 | 0 |
| 1250099 | [!! - 520005] !! - Subcont, Galvanis, Painting, DLL 520005 | [!! - 520005] !! - Subcont, Galvanis, Painting, DLL 520005 | 4 | 132596531.68 | purchase | 0 | 0 |
| 1250099 | Jasa Transport [PRC] | Jasa Transport [PRC] | 2 | 30900000 | purchase | 0 | 0 |
| 1250105 | [21416] Coil SPHC t2.0 x 1200 x Coil ->[15560] | [21416] Coil SPHC t2.0 x 1200 x Coil ->[15560] | 44860 | 494972926.6 | purchase | 0 | 0 |
| 1250105 | [21505] Coil SPHC t1.5 x 1200 x coil ->[16475] | [21505] Coil SPHC t1.5 x 1200 x coil ->[16475] | 28430 | 316723391 | purchase | 0 | 0 |
| 1250123 | [20682] Plat SS 316L -2B t2.0x1219x6000 ->[1C00293] | [20682] Plat SS 316L -2B t2.0x1219x6000 ->[1C00293] | 117 | 859482000 | purchase | 0 | 0 |

Possible causes:

- PO was created directly without a linked ROP/PEMBELIAN approval line.
- ROP exists but product text/key differs from the PO product text/key.
- ROP exists under a different SO/JO/IO reference than the PO.
- Historical data may predate consistent ROP reference discipline.
- Some PO rows may represent service/subcontract/transport purchases that are intentionally outside material ROP flow.

## ROP without PO Sample

Count: 1402

| report_key | product_key | product_name | rop_qty | rop_subtotal | rop_date_of_need_min | rop_date_of_need_max | po_qty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1250018 | [20496] Bolt+Nut+Fw+Sw RHSN M10x25 HDG ->[1C00067] | [20496] Bolt+Nut+Fw+Sw RHSN M10x25 HDG ->[1C00067] | 500 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [20801] Coupling Nut M10 EG ->[CN-M10] | [20801] Coupling Nut M10 EG ->[CN-M10] | 960 | 0 | 2025-01-24 | 2025-01-29 | 0 |
| 1250018 | [20842] Spring Nut M8 EG   ->[10131] | [20842] Spring Nut M8 EG   ->[10131] | 1250 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [20918] Hanger Rod M10x1000L EG Strength grade 4.6 ->[10407] | [20918] Hanger Rod M10x1000L EG Strength grade 4.6 ->[10407] | 1915 | 0 | 2025-01-24 | 2025-01-29 | 0 |
| 1250018 | [21512] Nut M8 EG Strength grade 8.8 ; 8PQ9500-0AA07 ->[16556] | [21512] Nut M8 EG Strength grade 8.8 ; 8PQ9500-0AA07 ->[16556] | 3000 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [21514] Nut M10 EG Strength grade 8.8 ; 8PQ9500-0AA05 ->[16559] | [21514] Nut M10 EG Strength grade 8.8 ; 8PQ9500-0AA05 ->[16559] | 4500 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [22959] Hanger Rod M08x1000 EG   ->[10252] | [22959] Hanger Rod M08x1000 EG   ->[10252] | 575 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [26676] Flat Washer M8 EG Strength grade 8.8 ->[16554] ; 8PQ9500-0AA70 | [26676] Flat Washer M8 EG Strength grade 8.8 ->[16554] ; 8PQ9500-0AA70 | 2700 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [26677] Spring Washer M8 EG Strength grade 8.8 ->[16555] | [26677] Spring Washer M8 EG Strength grade 8.8 ->[16555] | 2700 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [26719] Bolt Hex M8 x 30 Strength grade 8.8 ->[16644] | [26719] Bolt Hex M8 x 30 Strength grade 8.8 ->[16644] | 1250 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | [32078] Whip Cable Clamp, M10 Nut, Diameter Cable 25mm / 1 inch ->[1C00520] | [32078] Whip Cable Clamp, M10 Nut, Diameter Cable 25mm / 1 inch ->[1C00520] | 1470 | 0 | 2025-01-24 | 2025-01-24 | 0 |
| 1250018 | [34206] Coupling Nut M8 EG  ->[CN-M8] | [34206] Coupling Nut M8 EG  ->[CN-M8] | 290 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250018 | Whip Cable Pipe (Nut M10) pipe 1 Inch/25mm x€-EG | Whip Cable Pipe (Nut M10) pipe 1 Inch/25mm x€-EG | 1750 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250023 | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | [20561] Bolt+Nut+Fw+Sw JP M6x15 SS316 ->[1C00149] | 2000 | 0 | 2025-01-24 | 2025-01-24 | 0 |
| 1250023 | [20651] Bolt+Nut+Fw+Sw Hex M8x70 SS316 ->[1C00251] | [20651] Bolt+Nut+Fw+Sw Hex M8x70 SS316 ->[1C00251] | 300 | 0 | 2025-01-24 | 2025-01-24 | 0 |
| 1250023 | [29374] Plat SPHC t1.5 x 1200 x 3000 ->[16492] | [29374] Plat SPHC t1.5 x 1200 x 3000 ->[16492] | 200 | 0 | 2025-01-24 | 2025-01-24 | 0 |
| 1250043 | [21246] Plat SPHC t6.0x1200x2400 ->[13774] | [21246] Plat SPHC t6.0x1200x2400 ->[13774] | 3 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250043 | [34271] Plat SPHC t1.5 x 1200 x 1520->[17608] | [34271] Plat SPHC t1.5 x 1200 x 1520->[17608] | 200 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250043 | [36947] Tray Wiremesh / BRC 200x100x3000mm ->[1C00540] | [36947] Tray Wiremesh / BRC 200x100x3000mm ->[1C00540] | 31 | 0 | 2025-01-29 | 2025-01-29 | 0 |
| 1250092 | [21246] Plat SPHC t6.0x1200x2400 ->[13774] | [21246] Plat SPHC t6.0x1200x2400 ->[13774] | 12 | 0 | 2025-02-27 | 2025-02-27 | 0 |

Possible causes:

- ROP/PEMBELIAN request not yet converted to PO.
- PO exists but uses a different product key, UoM, or project reference.
- ROP quantity may have been fulfilled from stock or another procurement document not captured by the current mapping.
- Some rows may represent open procurement follow-up items.

## Recommendation

Recommended path:

A. Keep current conservative mapping.

C. Wait for business review before adding new mapping rules.

D. Compare with one known Excel report first.

Do not add aggressive mapping rules yet. A safe mapping rule can be considered later only for cases where the source row has a verified JO/SO reference or an explicit Internal Order number that is proven to bridge to the SO. Do not infer IO from RKB/ROP `approval_request_numeric_id` without proof.
