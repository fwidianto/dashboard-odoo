"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const A = require("../src/static/control-tower/control-tower-adapter.js");
const UI = require("../src/static/control-tower/control-tower.js");
const UI_SOURCE = fs.readFileSync(require.resolve("../src/static/control-tower/control-tower.js"), "utf8");
const HTML_SOURCE = fs.readFileSync(require.resolve("../src/static/control-tower/index.html"), "utf8");
const CSS_SOURCE = fs.readFileSync(require.resolve("../src/static/control-tower/control-tower.css"), "utf8");

test("adapter escapes untrusted values and formats unavailable numbers honestly", () => {
  assert.equal(A.escapeHtml('<script>"x"</script>'), "&lt;script&gt;&quot;x&quot;&lt;/script&gt;");
  assert.equal(A.formatNumber("not-a-number"), "—");
  assert.equal(A.formatMoney(null), "Belum tersedia");
  assert.equal(A.categoryTone("Masalah Aktif"), "danger");
});

test("left navigation and freshness copy match the frozen v0.3 contract", () => {
  for (const label of ["Temuan", "Peta Proses", "Tracking", "Arsip"]) {
    assert.match(HTML_SOURCE, new RegExp(`>${label}<`));
  }
  assert.match(HTML_SOURCE, /Sinkronisasi Odoo/);
  assert.match(HTML_SOURCE, /Layar diperbarui/);
  assert.doesNotMatch(HTML_SOURCE, /Snapshot data|Overview|Validasi SOP|Daftar Pengecualian|Perjalanan Dokumen/);
});

test("finding summary contains only the three active categories", () => {
  assert.deepEqual(
    [...UI_SOURCE.matchAll(/const CATEGORIES = \[(.*?)\]/gs)][0][1].match(/"[^"]+"/g).map((item) => item.slice(1, -1)),
    ["Masalah Aktif", "Perlu Ditinjau", "Data Belum Lengkap"],
  );
  assert.match(UI_SOURCE, /data-category=/);
  assert.doesNotMatch(UI_SOURCE.slice(UI_SOURCE.indexOf("function metricCards"), UI_SOURCE.indexOf("function findingRow")), /historis/i);
});

test("finding table uses the frozen columns and inline expansion", () => {
  const source = UI_SOURCE.slice(UI_SOURCE.indexOf("async function renderFindings"), UI_SOURCE.indexOf("function bindFindingActions"));
  for (const heading of ["Dokumen Utama", "Penjelasan Masalah", "Dokumen Terdampak", "Aksi"]) assert.match(source, new RegExp(heading));
  assert.match(UI_SOURCE, /data-expand-finding/);
  assert.match(UI_SOURCE, /Buka Dokumen/);
  assert.doesNotMatch(UI_SOURCE, /Lihat Detail/);
});

test("manual lifecycle supports single and bulk close plus archive reopen", () => {
  assert.match(UI_SOURCE, /\/findings\/bulk-close/);
  assert.match(UI_SOURCE, /\/findings\/bulk-reopen/);
  assert.match(UI_SOURCE, /Tutup Temuan/);
  assert.match(UI_SOURCE, /Buka Kembali/);
  assert.match(UI_SOURCE, /Temuan tetap tersimpan di Arsip/);
  assert.match(UI_SOURCE, /Refresh berikutnya tidak akan membukanya kembali otomatis/);
});

test("normal user bundle does not expose technical rule or source field identifiers", () => {
  assert.doesNotMatch(`${HTML_SOURCE}\n${UI_SOURCE}`, /rule_id|rule_code|fingerprint|x_studio_|database id/i);
});

test("process map contains the frozen lanes and required shared business nodes", () => {
  assert.deepEqual(UI.MAP_LANES.map(([lane]) => lane), ["Commercial", "Production", "Procurement", "Warehouse & QC", "Non-SO / Opex", "Finance"]);
  const labels = UI.MAP_NODES.map((node) => node.label);
  for (const label of ["Estimasi Estimator / RKB Kasar", "Sales Order Normal", "Internal Order", "RKB Pekerjaan", "Cek Stock Material", "ROP Pekerjaan", "Purchase Order", "Receipt & QC", "Stock Material", "Manufacturing Order", "Stock Finished Goods", "Sales Order PB", "Delivery", "Invoice", "Payment", "ROP Non-SO", "Vendor Bill", "Stock atau Expense"]) {
    assert.ok(labels.includes(label), label);
  }
  assert.equal(labels.filter((label) => label === "Manufacturing Order").length, 1);
  assert.equal(labels.filter((label) => label === "Purchase Order").length, 1);
  assert.equal(labels.filter((label) => label === "Payment").length, 1);
  assert.ok(!labels.includes("Keputusan Sumber"));
});

test("every Process Map connector is deterministic and orthogonal", () => {
  assert.deepEqual(UI.validateMapGeometry(), []);
  for (const route of UI.MAP_ROUTES) {
    assert.match(route.d, /^M\d+ \d+(?: [HV]\d+)+$/);
    for (const segment of UI.routeSegments(route.d)) {
      assert.ok(segment.x1 === segment.x2 || segment.y1 === segment.y2, route.d);
    }
  }
});

test("fixed map geometry remains stable for empty, high counts, and long labels", () => {
  const altered = UI.MAP_NODES.map((node) => ({ ...node, label: `${node.label} ${"sangat panjang ".repeat(5)}`, count: 999999 }));
  assert.deepEqual(UI.validateMapGeometry(altered, UI.MAP_ROUTES), []);
  assert.match(CSS_SOURCE, /\.process-map-scroll[\s\S]*overflow: auto/);
  assert.match(CSS_SOURCE, /width: 3620px/);
});

test("Process Map nodes and category badges navigate to the same finding source", () => {
  assert.match(UI_SOURCE, /data-map-category/);
  assert.match(UI_SOURCE, /url\.searchParams\.set\("process", process\)/);
  assert.match(UI_SOURCE, /url\.searchParams\.set\("category", button\.dataset\.mapCategory\)/);
  assert.match(UI_SOURCE, /source: "ct_finding"|\/process-map/);
});

test("document experience implements tabs, line focus, relations, tracking, and SO Gross Profit", () => {
  for (const label of ["Ringkasan", "Line Item", "Dokumen Terkait", "Temuan Aktif", "Tracking", "Gross Profit"]) assert.match(UI_SOURCE, new RegExp(label));
  assert.match(UI_SOURCE, /Tampilkan field lainnya/);
  assert.match(UI_SOURCE, /Tampilkan semua line item/);
  assert.match(UI_SOURCE, /GP Rencana/);
  assert.match(UI_SOURCE, /GP Realisasi/);
  assert.match(UI_SOURCE, /gp\.cogs_account\?\.code/);
});

test("integrated tracking offers one mode at a time and an evidence-limited RKB view", () => {
  for (const label of ["Order Tracking", "RKB Tracking", "Semua Hubungan", "Timeline", "Diagram"]) assert.match(UI_SOURCE, new RegExp(label));
  assert.match(UI_SOURCE, /mode === "Timeline" \?/);
  assert.match(UI_SOURCE, /Tampilkan semua aktivitas/);
  assert.match(UI_SOURCE, /Kekurangan Saat Ini/);
  assert.match(UI_SOURCE, /Stock Awal/);
  assert.match(UI_SOURCE, /Tidak tersedia/);
  assert.match(UI_SOURCE, /dari \$\{branch_po_quantity:g\} sudah diterima|progress_text/);
});

test("global search is grouped and ranks server results without searching findings only", () => {
  assert.match(HTML_SOURCE, /Cari seluruh dokumen/);
  assert.match(UI_SOURCE, /\/search\?q=/);
  assert.match(UI_SOURCE, /data\.groups/);
  assert.match(UI_SOURCE, /Temuan Aktif/);
});

test("refresh exposes eight measurable phases, safe retry, and no cosmetic timer", () => {
  assert.deepEqual(UI.PHASES.map(([, label]) => label), [
    "Persiapan", "Pemeriksaan koneksi dan skema", "Sinkronisasi Odoo", "Update PostgreSQL",
    "Pembentukan relasi line-to-line", "Rerun pemeriksaan terdampak",
    "Update ringkasan, pencarian, tracking, dan Process Map", "Finalisasi dan publish",
  ]);
  assert.match(UI_SOURCE, /completed_work_units|processed_records|percentage/);
  assert.match(UI_SOURCE, /Coba Lagi dari Tahap Gagal/);
  assert.match(UI_SOURCE, /\/retry/);
  assert.match(UI_SOURCE, /setTimeout\(\(\) => pollRefresh/);
  assert.doesNotMatch(UI_SOURCE, /setInterval|elapsed.*percentage|percentage.*elapsed/i);
});

test("native theme, focus, reduced motion, and narrow horizontal map behavior remain", () => {
  assert.match(CSS_SOURCE, /html\[data-theme="dark"\]/);
  assert.match(CSS_SOURCE, /:focus-visible/);
  assert.match(CSS_SOURCE, /prefers-reduced-motion: reduce/);
  assert.match(CSS_SOURCE, /@media \(max-width: 760px\)/);
  assert.doesNotMatch(`${HTML_SOURCE}\n${UI_SOURCE}`, />Reset<|>Fokus</);
});
