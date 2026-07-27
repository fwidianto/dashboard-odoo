(function exposeControlTowerUI(root, factory) {
  const ui = factory(root.ControlTowerAdapter || {});
  if (typeof module === "object" && module.exports) module.exports = ui;
  root.ControlTowerUI = ui;
  if (root.document) ui.start();
})(typeof globalThis !== "undefined" ? globalThis : this, function createControlTowerUI(A) {
  "use strict";

  const API = "/api/control-tower";
  const CATEGORIES = ["Masalah Aktif", "Perlu Ditinjau", "Data Belum Lengkap"];
  const CATEGORY_KEYS = { "Masalah Aktif": "active", "Perlu Ditinjau": "review", "Data Belum Lengkap": "incomplete" };
  const PHASES = [
    ["PREPARATION", "Persiapan"],
    ["SCHEMA_CHECK", "Pemeriksaan koneksi dan skema"],
    ["ODOO_SYNC", "Sinkronisasi Odoo"],
    ["POSTGRES_UPDATE", "Update PostgreSQL"],
    ["LINEAGE", "Pembentukan relasi line-to-line"],
    ["RULES", "Rerun pemeriksaan terdampak"],
    ["READ_MODELS", "Update ringkasan, pencarian, tracking, dan Process Map"],
    ["FINALIZE", "Finalisasi dan publish"],
  ];

  const MAP_LANES = [
    ["Commercial", 0], ["Production", 150], ["Procurement", 300],
    ["Warehouse & QC", 450], ["Non-SO / Opex", 600], ["Finance", 750],
  ];
  const MAP_NODES = Object.freeze([
    { id: "estimate", label: "Estimasi Estimator / RKB Kasar", lane: "Commercial", x: 40, y: 45, w: 170, h: 76, external: true },
    { id: "quotation", label: "Quotation", lane: "Commercial", x: 250, y: 45, w: 170, h: 76, process: "Quotation" },
    { id: "sales-order", label: "Sales Order Normal", lane: "Commercial", x: 470, y: 45, w: 180, h: 76, process: "Sales Order" },
    { id: "internal-order", label: "Internal Order", lane: "Production", x: 470, y: 195, w: 180, h: 76, process: "Internal Order" },
    { id: "rkb-work", label: "RKB Pekerjaan", lane: "Procurement", x: 690, y: 345, w: 180, h: 76, process: "RKB Pekerjaan" },
    { id: "stock-check", label: "Cek Stock Material", lane: "Procurement", x: 910, y: 345, w: 190, h: 76, process: "Cek Stock Material" },
    { id: "rop-work", label: "ROP Pekerjaan", lane: "Procurement", x: 1130, y: 345, w: 180, h: 76, process: "ROP Pekerjaan" },
    { id: "purchase-order", label: "Purchase Order", lane: "Procurement", x: 1350, y: 345, w: 180, h: 76, process: "Purchase Order" },
    { id: "receipt", label: "Receipt & QC", lane: "Warehouse & QC", x: 1580, y: 495, w: 180, h: 76, process: "Receipt & QC" },
    { id: "stock-material", label: "Stock Material", lane: "Warehouse & QC", x: 1800, y: 495, w: 180, h: 76, process: "Stock Material" },
    { id: "manufacturing", label: "Manufacturing Order", lane: "Production", x: 1900, y: 195, w: 180, h: 76, process: "Manufacturing" },
    { id: "production", label: "Production", lane: "Production", x: 2120, y: 195, w: 180, h: 76, process: "Manufacturing" },
    { id: "qc", label: "QC", lane: "Warehouse & QC", x: 2340, y: 495, w: 180, h: 76, process: "QC" },
    { id: "finished-stock", label: "Stock Finished Goods", lane: "Warehouse & QC", x: 2560, y: 495, w: 180, h: 76, process: "Stock Finished Goods" },
    { id: "sales-order-pb", label: "Sales Order PB", lane: "Commercial", x: 2730, y: 45, w: 180, h: 76, process: "Sales Order PB" },
    { id: "delivery", label: "Delivery", lane: "Warehouse & QC", x: 2950, y: 495, w: 180, h: 76, process: "Delivery" },
    { id: "rop-non-so", label: "ROP Non-SO", lane: "Non-SO / Opex", x: 1130, y: 645, w: 180, h: 76, process: "ROP Non-SO" },
    { id: "expense", label: "Stock atau Expense", lane: "Non-SO / Opex", x: 1800, y: 645, w: 180, h: 76, process: "Stock atau Expense" },
    { id: "vendor-bill", label: "Vendor Bill", lane: "Finance", x: 1580, y: 795, w: 180, h: 76, process: "Vendor Bill" },
    { id: "invoice", label: "Invoice", lane: "Finance", x: 3170, y: 795, w: 180, h: 76, process: "Invoice" },
    { id: "payment", label: "Payment", lane: "Finance", x: 3390, y: 795, w: 180, h: 76, process: "Payment" },
  ]);
  const MAP_ROUTES = Object.freeze([
    { from: "estimate", to: "quotation", d: "M210 83 H250" },
    { from: "quotation", to: "sales-order", d: "M420 83 H470" },
    { from: "sales-order", to: "manufacturing", d: "M650 83 H1850 V233 H1900" },
    { from: "internal-order", to: "manufacturing", d: "M650 233 H1900" },
    { from: "manufacturing", to: "production", d: "M2080 233 H2120" },
    { from: "production", to: "qc", d: "M2300 233 H2310 V533 H2340" },
    { from: "qc", to: "finished-stock", d: "M2520 533 H2560" },
    { from: "finished-stock", to: "delivery", d: "M2740 533 H2950" },
    { from: "finished-stock", to: "sales-order-pb", d: "M2740 520 H2800 V135 H2820 V121" },
    { from: "sales-order-pb", to: "delivery", d: "M2910 83 H3040 V495" },
    { from: "delivery", to: "invoice", d: "M3130 533 H3260 V795" },
    { from: "invoice", to: "payment", d: "M3350 833 H3390" },
    { from: "sales-order", to: "rkb-work", d: "M650 83 H660 V383 H690" },
    { from: "internal-order", to: "rkb-work", d: "M650 233 H675 V383 H690" },
    { from: "manufacturing", to: "rkb-work", d: "M1900 233 H1870 V315 H680 V383 H690" },
    { from: "rkb-work", to: "stock-check", d: "M870 383 H910" },
    { from: "stock-check", to: "rop-work", d: "M1100 383 H1130" },
    { from: "rop-work", to: "purchase-order", d: "M1310 383 H1350" },
    { from: "purchase-order", to: "receipt", d: "M1530 383 H1670 V495" },
    { from: "receipt", to: "stock-material", d: "M1760 533 H1800" },
    { from: "stock-check", to: "stock-material", d: "M1005 421 V465 H1890 V495" },
    { from: "stock-material", to: "manufacturing", d: "M1890 495 V300 H1990 V271" },
    { from: "rop-non-so", to: "purchase-order", d: "M1310 683 H1330 V430 H1440 V421" },
    { from: "purchase-order", to: "vendor-bill", d: "M1440 421 V760 H1670 V795" },
    { from: "vendor-bill", to: "expense", d: "M1760 833 H1780 V683 H1800" },
  ]);

  const state = {
    view: "findings", selected: new Set(), expanded: new Set(), currentRows: [],
    searchTimer: null, refreshTimer: null, refreshJob: null, trackingMode: "Timeline",
    trackingScope: "Order Tracking", showAllActivities: false, includeAllLines: false,
    currentDocumentNumber: null,
    collapsedBranches: new Set(),
  };

  const esc = (value) => A.escapeHtml ? A.escapeHtml(value) : String(value ?? "");
  const number = (value, options) => A.formatNumber ? A.formatNumber(value, options) : String(value ?? "—");
  const money = (value) => A.formatMoney ? A.formatMoney(value) : String(value ?? "Belum tersedia");
  const percent = (value) => A.formatPercent ? A.formatPercent(value) : String(value ?? "Belum tersedia");
  const dateTime = (value) => A.formatDateTime ? A.formatDateTime(value) : String(value ?? "Belum tersedia");
  const tone = (category) => A.categoryTone ? A.categoryTone(category) : "neutral";

  function qs(selector, scope = document) { return scope.querySelector(selector); }
  function qsa(selector, scope = document) { return Array.from(scope.querySelectorAll(selector)); }

  async function apiJson(path, method = "GET", body) {
    const response = await fetch(`${API}${path}`, {
      method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 401) {
      location.assign("/login");
      throw new Error("Sesi berakhir.");
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Permintaan tidak dapat diproses.");
    return payload;
  }

  function setBusy(active) {
    qs("#viewContainer")?.setAttribute("aria-busy", String(active));
  }

  function toast(message, kind = "success") {
    const item = document.createElement("div");
    item.className = `toast toast--${kind}`;
    item.textContent = message;
    qs("#toastRegion").append(item);
    setTimeout(() => item.remove(), 5000);
  }

  function navigate(input, replace = false) {
    const url = input instanceof URL ? input : new URL(input, location.origin);
    const scroll = window.scrollY;
    history.replaceState({ ...(history.state || {}), scroll }, "", location.href);
    const previousDocument = url.searchParams.get("view") === "document" && state.view === "document"
      ? state.currentDocumentNumber
      : null;
    history[replace ? "replaceState" : "pushState"]({ scroll: 0, previousDocument }, "", url);
    loadCurrentView().then(() => window.scrollTo(0, 0));
  }

  function currentParams() { return new URL(location.href).searchParams; }

  function syncNavigation(view) {
    qsa("[data-view-link]").forEach((link) => {
      const active = link.dataset.viewLink === view || (view === "document" && link.dataset.viewLink === "tracking");
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
  }

  function documentLink(document, label = "Buka") {
    if (!document?.detail_url) return "";
    return `<a class="button-link" data-route-link href="${esc(document.detail_url)}">${esc(label)}</a>`;
  }

  function nativeLink(document, label = "Buka Dokumen") {
    if (!document?.open_url) return "";
    return `<a class="button-link button-link--native" target="_blank" rel="noopener" href="${esc(document.open_url)}">${esc(label)}</a>`;
  }

  function badge(category, count) {
    return `<span class="category-badge category-badge--${tone(category)}"><span>${esc(category)}</span>${count === undefined ? "" : `<strong>${number(count)}</strong>`}</span>`;
  }

  function metricCards(summary, activeCategory) {
    return `<div class="summary-cards" aria-label="Ringkasan temuan">${CATEGORIES.map((category) => {
      const key = CATEGORY_KEYS[category];
      const selected = category === activeCategory;
      return `<button class="summary-card summary-card--${tone(category)}${selected ? " is-selected" : ""}" data-category="${esc(category)}" type="button" aria-pressed="${selected}">
        <span>${esc(category)}</span><strong>${number(summary?.[key] || 0)}</strong>
      </button>`;
    }).join("")}</div>`;
  }

  function findingRow(row, archive) {
    const expanded = state.expanded.has(row.finding_id);
    const checked = state.selected.has(row.finding_id);
    const primary = row.primary_document || {};
    const details = expanded ? `<tr class="finding-detail-row"><td colspan="5">${findingDetail(row, archive)}</td></tr>` : "";
    return `<tr class="finding-row">
      <td class="expand-cell"><input type="checkbox" data-select-finding="${esc(row.finding_id)}" ${checked ? "checked" : ""} aria-label="Pilih ${esc(row.title)}"><button class="icon-button" data-expand-finding="${esc(row.finding_id)}" type="button" aria-expanded="${expanded}" aria-label="${expanded ? "Tutup" : "Buka"} rincian">${expanded ? "−" : "+"}</button></td>
      <td><strong>${esc(primary.number)}</strong><span class="native-state">${esc(primary.status || "Status tidak tersedia")}</span></td>
      <td>${badge(row.category)}<strong class="finding-title">${esc(row.title)}</strong></td>
      <td>${esc(row.affected_summary)}</td>
      <td class="actions-cell">${nativeLink(primary)}${archive ? `<button class="button-link" data-reopen-finding="${esc(row.finding_id)}" type="button">Buka Kembali</button>` : `<button class="button-link" data-close-finding="${esc(row.finding_id)}" type="button">Tutup Temuan</button>`}</td>
    </tr>${details}`;
  }

  function findingDetail(row, archive) {
    const facts = (row.facts || []).map((fact) => `<li><span>${esc(fact.label)}</span><strong>${esc(fact.value ?? "Belum tersedia")}</strong></li>`).join("");
    const documents = (row.impacted_documents || []).map((document) => `<li><div><strong>${esc(document.number)}</strong><span>${esc(document.status || "Status tidak tersedia")}</span></div><div>${documentLink(document)}${nativeLink(document, "Buka")}</div></li>`).join("");
    const lines = (row.impacted_lines || []).map((line) => `<li>${(line.values || []).map((item) => `<span><small>${esc(item.label)}</small>${esc(item.value ?? "Belum tersedia")}</span>`).join("")}</li>`).join("");
    return `<section class="finding-detail">
      <div><h3>Fakta yang ditemukan</h3><ul class="fact-list">${facts || "<li>Fakta bisnis belum tersedia.</li>"}</ul></div>
      <div><h3>Dokumen yang perlu diperiksa</h3><ul class="document-list">${documents || "<li>Dokumen terkait belum dapat dibuktikan.</li>"}</ul>${lines ? `<ul class="line-evidence">${lines}</ul>` : ""}</div>
      <div><h3>${esc(row.recommendation_heading)}</h3><p>${esc(row.recommendation || "Konfirmasi dengan pemilik proses terkait.")}</p></div>
      <div><h3>Perlu diperiksa oleh</h3><p><strong>${esc(row.process_owner)}</strong>${row.responsible_user ? `<br>${esc(row.responsible_user)}` : ""}</p></div>
      ${archive ? `<div class="archive-note"><strong>${row.lifecycle_state === "AUTO_RESOLVED" ? "Selesai Otomatis" : esc(row.closed_reason || "Ditutup")}</strong>${row.closed_note ? `<p>${esc(row.closed_note)}</p>` : ""}<small>${dateTime(row.auto_resolved_at || row.closed_at)}</small></div>` : ""}
    </section>`;
  }

  async function renderFindings(archive = false) {
    const params = currentParams();
    const category = params.get("category") || "";
    const process = params.get("process") || "";
    const query = new URLSearchParams({ archive: String(archive), limit: "500" });
    if (category) query.set("category", category);
    if (process) query.set("process_node", process);
    const data = await apiJson(`/findings?${query}`);
    state.currentRows = data.rows || [];
    const visibleIds = new Set(state.currentRows.map((row) => row.finding_id));
    state.selected = new Set([...state.selected].filter((id) => visibleIds.has(id)));
    const title = archive ? "Arsip" : "Temuan";
    const bulkLabel = archive ? "Buka kembali pilihan" : "Tutup pilihan";
    qs("#viewContainer").innerHTML = `<section class="page-heading"><div><p class="eyebrow">Control Tower · cakupan ${new Date().getFullYear()}</p><h1>${title}</h1><p>${archive ? "Riwayat temuan yang ditutup manual atau selesai otomatis." : "Satu baris menunjukkan satu pelanggaran bisnis pada satu dokumen utama."}</p></div></section>
      ${archive ? "" : metricCards(data.summary, category)}
      <section class="table-toolbar">
        <div><strong>${number(data.total)} ${archive ? "temuan di arsip" : "temuan aktif"}</strong>${process ? `<span>Proses: ${esc(process)}</span>` : ""}</div>
        <div>${category || process ? `<button class="button-secondary" data-clear-filter type="button">Hapus filter</button>` : ""}<button class="button-primary" id="bulkAction" type="button" disabled>${bulkLabel}</button></div>
      </section>
      <div class="table-shell"><table class="findings-table"><thead><tr><th><span class="sr-only">Pilih dan buka</span></th><th>Dokumen Utama</th><th>Penjelasan Masalah</th><th>Dokumen Terdampak</th><th>Aksi</th></tr></thead><tbody>${data.rows.length ? data.rows.map((row) => findingRow(row, archive)).join("") : `<tr><td colspan="5"><div class="empty-state"><h2>${archive ? "Arsip masih kosong" : "Tidak ada temuan untuk filter ini"}</h2><p>Data ditampilkan dari hasil sinkronisasi terakhir yang berhasil.</p></div></td></tr>`}</tbody></table></div>`;
    bindFindingActions(archive, data);
  }

  function bindFindingActions(archive, data, rerender = () => renderFindings(archive)) {
    qsa("[data-category]").forEach((button) => button.addEventListener("click", () => {
      const url = new URL(location.href);
      if (url.searchParams.get("category") === button.dataset.category) url.searchParams.delete("category");
      else url.searchParams.set("category", button.dataset.category);
      navigate(url);
    }));
    qs("[data-clear-filter]")?.addEventListener("click", () => {
      const url = new URL(location.href); url.searchParams.delete("category"); url.searchParams.delete("process"); navigate(url);
    });
    qsa("[data-select-finding]").forEach((input) => input.addEventListener("change", () => {
      if (input.checked) state.selected.add(input.dataset.selectFinding); else state.selected.delete(input.dataset.selectFinding);
      qs("#bulkAction").disabled = state.selected.size === 0;
      qs("#bulkAction").textContent = `${archive ? "Buka kembali" : "Tutup"} ${state.selected.size || ""} pilihan`.trim();
    }));
    qsa("[data-expand-finding]").forEach((button) => button.addEventListener("click", () => {
      const key = button.dataset.expandFinding;
      if (state.expanded.has(key)) state.expanded.delete(key); else state.expanded.add(key);
      rerender().catch(showFailure);
    }));
    qsa("[data-close-finding]").forEach((button) => button.addEventListener("click", () => openCloseDialog([button.dataset.closeFinding], data, rerender)));
    qsa("[data-reopen-finding]").forEach((button) => button.addEventListener("click", () => openReopenDialog([button.dataset.reopenFinding], rerender)));
    qs("#bulkAction")?.addEventListener("click", () => archive ? openReopenDialog([...state.selected], rerender) : openCloseDialog([...state.selected], data, rerender));
  }

  function openCloseDialog(ids, data, rerender) {
    const dialog = qs("#actionDialog");
    qs("#actionDialogTitle").textContent = `Tutup ${ids.length} temuan`;
    qs("#actionDialogBody").innerHTML = `<p>Temuan tetap tersimpan di Arsip. Refresh berikutnya tidak akan membukanya kembali otomatis.</p><label>Alasan<select id="closeReason" required><option value="">Pilih alasan</option>${(data.close_reasons || []).map((reason) => `<option>${esc(reason)}</option>`).join("")}</select></label><label>Catatan<textarea id="closeNote" rows="4" placeholder="Wajib untuk alasan tertentu"></textarea></label>`;
    qs("#actionSubmit").onclick = async (event) => {
      event.preventDefault();
      try {
        const reason = qs("#closeReason").value;
        const note = qs("#closeNote").value;
        await apiJson("/findings/bulk-close", "POST", { finding_ids: ids, reason, note: note || null });
        dialog.close(); toast(`${ids.length} temuan dipindahkan ke Arsip.`); await rerender();
      } catch (error) { toast(error.message, "danger"); }
    };
    dialog.showModal();
  }

  function openReopenDialog(ids, rerender) {
    const dialog = qs("#actionDialog");
    qs("#actionDialogTitle").textContent = `Buka kembali ${ids.length} temuan`;
    qs("#actionDialogBody").innerHTML = `<p>Temuan akan kembali ke ringkasan aktif.</p><label>Alasan buka kembali<textarea id="reopenReason" rows="4" required></textarea></label>`;
    qs("#actionSubmit").onclick = async (event) => {
      event.preventDefault();
      try {
        await apiJson("/findings/bulk-reopen", "POST", { finding_ids: ids, reason: qs("#reopenReason").value });
        dialog.close(); toast(`${ids.length} temuan dibuka kembali.`); await rerender();
      } catch (error) { toast(error.message, "danger"); }
    };
    dialog.showModal();
  }

  function mapBadgeMarkup(node, counts) {
    const short = { "Masalah Aktif": "M", "Perlu Ditinjau": "T", "Data Belum Lengkap": "D" };
    return CATEGORIES.map((category) => `<button data-map-category="${esc(category)}" data-process="${esc(node.process || "")}" type="button" title="${esc(category)}"><span aria-hidden="true">${short[category]}</span><span class="sr-only">${esc(category)}</span><strong>${number(counts?.[category] || 0)}</strong></button>`).join("");
  }

  async function renderProcessMap() {
    const data = await apiJson("/process-map");
    const paths = MAP_ROUTES.map((route) => `<path class="process-route" data-from="${route.from}" data-to="${route.to}" d="${route.d}" marker-end="url(#arrow)"/>`).join("");
    const lanes = MAP_LANES.map(([label, y]) => `<div class="process-lane" style="top:${y}px;height:150px"><strong>${esc(label)}</strong></div>`).join("");
    const nodes = MAP_NODES.map((node) => `<article class="process-node${node.external ? " process-node--external" : ""}" data-process-node="${node.id}" style="left:${node.x}px;top:${node.y}px;width:${node.w}px;height:${node.h}px">
      <button class="process-node-title" data-process="${esc(node.process || "")}" type="button" ${node.process ? "" : "disabled"}><strong>${esc(node.label)}</strong>${node.external ? "<small>Di luar Odoo · integrasi mendatang</small>" : ""}</button>
      ${node.external ? "" : `<div class="process-node-counts">${mapBadgeMarkup(node, data.counts?.[node.process] || {})}</div>`}
    </article>`).join("");
    qs("#viewContainer").innerHTML = `<section class="page-heading"><div><p class="eyebrow">Struktur proses perusahaan</p><h1>Peta Proses</h1></div><div class="map-legend"><span class="legend-line"></span>Alur bisnis</div></section>
      <div class="process-map-scroll" tabindex="0" aria-label="Peta proses; geser horizontal untuk melihat seluruh alur"><div class="process-map-canvas">${lanes}<svg class="process-route-layer" width="3620" height="900" viewBox="0 0 3620 900" aria-hidden="true"><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 H7 V7 H0 Z"/></marker></defs>${paths}</svg><div class="process-node-layer">${nodes}</div></div></div>`;
    qsa("[data-process]").forEach((button) => button.addEventListener("click", (event) => {
      event.stopPropagation();
      const process = button.dataset.process;
      if (!process) return;
      const url = new URL("/control-tower?view=findings", location.origin);
      url.searchParams.set("process", process);
      if (button.dataset.mapCategory) url.searchParams.set("category", button.dataset.mapCategory);
      navigate(url);
    }));
  }

  function fieldList(items) {
    return `<dl class="field-list">${(items || []).map((item) => `<div><dt>${esc(item.label)}</dt><dd>${esc(item.value)}</dd></div>`).join("")}</dl>`;
  }

  function documentTabs(tabs, selected) {
    const slug = { "Ringkasan": "summary", "Line Item": "lines", "Dokumen Terkait": "related", "Temuan Aktif": "findings", "Tracking": "tracking", "Gross Profit": "gross-profit" };
    return `<nav class="document-tabs" aria-label="Bagian dokumen">${tabs.map((tab) => `<button class="${slug[tab] === selected ? "is-active" : ""}" data-document-tab="${slug[tab]}" type="button">${esc(tab)}</button>`).join("")}</nav>`;
  }

  function renderSummaryTab(data) {
    const gp = data.gross_profit?.cards;
    return `${gp ? `<div class="gp-cards"><article><span>GP Rencana</span><strong>${money(gp.planned_gp)}</strong></article><article><span>Margin Rencana</span><strong>${percent(gp.planned_margin)}</strong></article><article><span>GP Realisasi</span><strong>${money(gp.realized_gp)}</strong></article><article><span>Margin Realisasi</span><strong>${percent(gp.realized_margin)}</strong></article></div>` : ""}
      <section class="detail-section"><h2>Ringkasan</h2>${fieldList(data.summary?.primary)}${data.summary?.additional?.length ? `<details><summary>Tampilkan field lainnya</summary>${fieldList(data.summary.additional)}</details>` : ""}</section>`;
  }

  function renderLinesTab(data) {
    const rows = data.line_items || [];
    return `<section class="detail-section"><div class="section-heading"><div><h2>Line Item</h2><p>${data.showing_problematic_only ? "Hanya line bermasalah ditampilkan." : "Seluruh line ditampilkan."}</p></div>${data.showing_problematic_only ? `<button class="button-secondary" data-show-all-lines type="button">Tampilkan semua line item</button>` : data.problematic_line_count ? `<button class="button-secondary" data-problem-lines type="button">Tampilkan line bermasalah</button>` : ""}</div><div class="line-grid">${rows.length ? rows.map((line) => `<article class="line-card${line.problematic ? " line-card--problem" : ""}">${fieldList(line.values)}</article>`).join("") : `<div class="empty-state"><p>Tidak ada line item untuk ditampilkan.</p></div>`}</div></section>`;
  }

  function renderRelatedTab(data) {
    return `<section class="detail-section"><h2>Dokumen Terkait</h2><div class="related-groups">${(data.related_groups || []).length ? data.related_groups.map((group) => `<details open><summary>${esc(group.module)} <span>${number(group.documents.length)}</span></summary><ul>${group.documents.map((document) => `<li><div><strong>${esc(document.number)}</strong><span>${esc(document.status || "Status tidak tersedia")}</span></div><div>${documentLink(document)}${nativeLink(document, "Buka")}</div></li>`).join("")}</ul></details>`).join("") : `<div class="empty-state"><p>Dokumen terkait belum dapat dibuktikan.</p></div>`}</div></section>`;
  }

  function renderFindingsTab(data) {
    return `<section class="detail-section"><h2>Temuan Aktif</h2><div class="table-shell"><table class="findings-table"><thead><tr><th></th><th>Dokumen Utama</th><th>Penjelasan Masalah</th><th>Dokumen Terdampak</th><th>Aksi</th></tr></thead><tbody>${(data.findings || []).length ? data.findings.map((row) => findingRow(row, false)).join("") : `<tr><td colspan="5"><div class="empty-state"><p>Tidak ada temuan aktif pada dokumen ini.</p></div></td></tr>`}</tbody></table></div></section>`;
  }

  function trackingMarkup(tracking, embedded = false) {
    const timeline = tracking?.timeline || [];
    const visible = state.showAllActivities ? timeline : timeline.filter((item) => item.depth === 0 || ["SO", "IO", "MO", "RKB", "ROP", "PO", "Receipt", "Delivery", "Invoice", "Vendor Bill", "Payment"].includes(item.type));
    const edges = tracking?.diagram?.edges || [];
    const outgoing = new Map();
    for (const edge of edges) outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target]);
    const hidden = new Set();
    const visited = new Set(state.collapsedBranches);
    function hideChildren(key) {
      for (const child of outgoing.get(key) || []) {
        if (visited.has(child)) continue;
        visited.add(child);
        hidden.add(child);
        hideChildren(child);
      }
    }
    for (const key of state.collapsedBranches) hideChildren(key);
    const diagramNodes = timeline.filter((item) => !hidden.has(item.key));
    const mode = state.trackingMode;
    return `<section class="detail-section tracking-section"><div class="section-heading"><div><h2>${embedded ? "Tracking" : "Tracking Terintegrasi"}</h2>${tracking?.context ? `<p>Konteks utama: <strong>${esc(tracking.context.number)}</strong></p>` : ""}</div><div class="segmented"><button data-tracking-mode="Timeline" class="${mode === "Timeline" ? "is-active" : ""}" type="button">Timeline</button><button data-tracking-mode="Diagram" class="${mode === "Diagram" ? "is-active" : ""}" type="button">Diagram</button></div></div>
      ${mode === "Timeline" ? `<div class="timeline-toolbar"><button class="button-secondary" data-toggle-activities type="button">${state.showAllActivities ? "Tampilkan milestone saja" : "Tampilkan semua aktivitas"}</button></div><ol class="tracking-timeline">${visible.map((item) => `<li><span class="timeline-dot"></span><div><small>${esc(item.type)}</small><a data-route-link href="${esc(item.detail_url)}">${esc(item.number)}</a><span>${esc(item.status || "Status tidak tersedia")}</span>${item.summary ? `<p>${esc(item.summary)}</p>` : ""}</div></li>`).join("") || `<li><div>Hubungan dokumen belum dapat dibuktikan.</div></li>`}</ol>` : `<div class="tracking-diagram">${diagramNodes.map((item) => `<article style="--depth:${Math.min(Number(item.depth) || 0, 6)}">${outgoing.has(item.key) ? `<button class="branch-toggle" data-branch-key="${esc(item.key)}" type="button" aria-expanded="${!state.collapsedBranches.has(item.key)}">${state.collapsedBranches.has(item.key) ? "+" : "−"}</button>` : `<span class="branch-spacer"></span>`}<a data-route-link href="${esc(item.detail_url)}"><small>${esc(item.type)}</small><strong>${esc(item.number)}</strong><span>${esc(item.status || "Status tidak tersedia")}</span></a></article>`).join("") || `<div class="empty-state">Hubungan dokumen belum dapat dibuktikan.</div>`}</div>`}
    </section>`;
  }

  function grossProfitMarkup(gp) {
    if (!gp) return `<div class="empty-state"><p>Gross Profit belum tersedia untuk Sales Order ini.</p></div>`;
    return `<section class="detail-section"><h2>Gross Profit</h2><p>Rekonsiliasi utama dalam IDR. COGS memakai akun ${esc(gp.cogs_account?.code)} — ${esc(gp.cogs_account?.name)}.</p>
      <div class="gp-cards"><article><span>Revenue Rencana</span><strong>${money(gp.planned.revenue)}</strong></article><article><span>Total RKB</span><strong>${money(gp.planned.rkb)}</strong></article><article><span>GP Rencana</span><strong>${money(gp.planned.gross_profit)}</strong></article><article><span>Margin Rencana</span><strong>${percent(gp.planned.margin)}</strong></article><article><span>Revenue Realisasi</span><strong>${money(gp.realized.revenue)}</strong></article><article><span>COGS</span><strong>${money(gp.realized.cogs)}</strong></article><article><span>GP Realisasi</span><strong>${money(gp.realized.gross_profit)}</strong></article><article><span>Margin Realisasi</span><strong>${percent(gp.realized.margin)}</strong></article></div>
      <div class="table-shell"><table><thead><tr><th>Produk</th><th>Invoice</th><th>Qty</th><th>Revenue</th><th>COGS langsung</th><th>Gross Profit Line</th></tr></thead><tbody>${(gp.lines || []).map((line) => `<tr><td>${esc(line.product || "Belum tersedia")}</td><td>${esc(line.invoice_number)}</td><td>${number(line.quantity)}</td><td>${money(line.revenue_idr)}</td><td>${line.cogs_idr === null ? "Belum dapat dialokasikan" : money(line.cogs_idr)}</td><td>${line.gross_profit_idr === null ? "Belum dapat dihitung" : money(line.gross_profit_idr)}</td></tr>`).join("") || `<tr><td colspan="6">Belum ada line Posted yang dapat direkonsiliasi.</td></tr>`}</tbody></table></div>
      ${(gp.limitations || []).length ? `<aside class="data-limitation"><strong>Data yang perlu dilengkapi</strong><ul>${gp.limitations.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></aside>` : ""}</section>`;
  }

  async function renderDocument() {
    const params = currentParams();
    const model = params.get("model");
    const id = params.get("id");
    const tab = params.get("tab") || "summary";
    if (!model || !id) throw new Error("Dokumen belum dipilih.");
    const data = await apiJson(`/documents/${encodeURIComponent(model)}/${encodeURIComponent(id)}?include_all_lines=${state.includeAllLines}&include_tracking=${tab === "tracking"}`);
    const previous = history.state?.previousDocument;
    state.currentDocumentNumber = data.document.number;
    let content;
    if (tab === "lines") content = renderLinesTab(data);
    else if (tab === "related") content = renderRelatedTab(data);
    else if (tab === "findings") content = renderFindingsTab(data);
    else if (tab === "tracking") content = trackingMarkup(data.tracking, true);
    else if (tab === "gross-profit") content = grossProfitMarkup(data.gross_profit);
    else content = renderSummaryTab(data);
    qs("#viewContainer").innerHTML = `<nav class="document-breadcrumb" aria-label="Breadcrumb"><button data-history-back type="button">← ${previous ? `Kembali ke ${esc(previous)}` : "Kembali"}</button><span>…</span><strong>${esc(data.document.number)}</strong></nav>
      <header class="document-header"><div><span class="document-type">${esc(data.document.type)}</span><h1>${esc(data.document.number)}</h1><span class="native-state">${esc(data.document.status || "Status tidak tersedia")}</span></div>${nativeLink(data.document)}</header>
      ${documentTabs(data.tabs, tab)}${content}`;
    qs("#odooSyncTime").textContent = dateTime(data.odoo_sync_at);
    qsa("[data-document-tab]").forEach((button) => button.addEventListener("click", () => {
      const url = new URL(location.href); url.searchParams.set("tab", button.dataset.documentTab); navigate(url);
    }));
    qs("[data-history-back]")?.addEventListener("click", () => history.length > 1 ? history.back() : navigate("/control-tower?view=findings"));
    qs("[data-show-all-lines]")?.addEventListener("click", () => { state.includeAllLines = true; renderDocument().catch(showFailure); });
    qs("[data-problem-lines]")?.addEventListener("click", () => { state.includeAllLines = false; renderDocument().catch(showFailure); });
    bindTrackingActions(data.tracking, true);
    bindFindingActions(false, { close_reasons: ["Dokumen terlalu lama untuk diperbaiki", "Sudah tidak relevan", "Pengecualian bisnis yang sah", "Sudah dikoreksi di luar sistem", "Duplikat temuan", "Alasan lain"] }, renderDocument);
  }

  function trackingChooser() {
    return `<section class="tracking-start"><p class="eyebrow">Mulai dari dokumen apa pun</p><h1>Tracking Terintegrasi</h1><p>Cari dokumen melalui pencarian global, lalu buka tab Tracking. Jika Sales Order terkait tersedia, dokumen tersebut menjadi konteks utama.</p><button class="button-primary" data-open-search type="button">Cari dokumen</button></section>`;
  }

  async function renderTracking() {
    const params = currentParams();
    const model = params.get("model");
    const id = params.get("id");
    if (!model || !id) { qs("#viewContainer").innerHTML = trackingChooser(); qs("[data-open-search]").onclick = openSearch; return; }
    let data;
    if (state.trackingScope === "RKB Tracking" && model === "approval.request") data = await apiJson(`/rkb-tracking/${encodeURIComponent(id)}`);
    else data = await apiJson(`/tracking/${encodeURIComponent(model)}/${encodeURIComponent(id)}`);
    qs("#viewContainer").innerHTML = `<section class="page-heading"><div><p class="eyebrow">Hubungan dokumen berbasis relasi Odoo</p><h1>Tracking Terintegrasi</h1></div><div class="segmented tracking-scope"><button data-tracking-scope="Order Tracking" class="${state.trackingScope === "Order Tracking" ? "is-active" : ""}" type="button">Order Tracking</button><button data-tracking-scope="RKB Tracking" class="${state.trackingScope === "RKB Tracking" ? "is-active" : ""}" type="button">RKB Tracking</button><button data-tracking-scope="Semua Hubungan" class="${state.trackingScope === "Semua Hubungan" ? "is-active" : ""}" type="button">Semua Hubungan</button></div></section>${state.trackingScope === "RKB Tracking" && data.rkb ? rkbMarkup(data) : trackingMarkup(data)}`;
    qsa("[data-tracking-scope]").forEach((button) => button.addEventListener("click", () => { state.trackingScope = button.dataset.trackingScope; renderTracking().catch(showFailure); }));
    bindTrackingActions(data, false);
  }

  function rkbMarkup(data) {
    return `<section class="detail-section"><div class="section-heading"><div><span class="document-type">RKB</span><h2>${esc(data.rkb.number)}</h2><span class="native-state">${esc(data.rkb.status)}</span><p>${esc(data.rkb.work_reference || "Referensi pekerjaan belum tersedia")}</p></div>${nativeLink(data.rkb)}</div>
      <div class="rkb-items">${(data.items || []).map((item) => `<article><header><h3>${esc(item.product)}</h3><span>${esc(item.uom || "")}</span></header><div class="rkb-summary"><span>Kebutuhan<strong>${number(item.summary.required)}</strong></span><span>Stock Awal<strong>${item.summary.opening_stock === null ? "Tidak tersedia" : number(item.summary.opening_stock)}</strong></span><span>Diproses ke ROP<strong>${item.summary.processed_to_rop === null ? "Tidak tersedia" : number(item.summary.processed_to_rop)}</strong></span><span>Sudah Di-PO<strong>${number(item.summary.ordered_for_rkb)}</strong></span><span>Sudah Diterima<strong>${number(item.summary.received)}</strong></span><span>Kekurangan Saat Ini<strong>${number(item.summary.current_shortage)}</strong></span></div><p class="material-state">${esc(item.material_status)}</p>
        <details><summary>${number(item.branches.length)} cabang procurement</summary>${(item.branches || []).map((branch) => `<div class="rkb-branch"><div><strong>${esc(branch.po_number)}</strong><span>${esc(branch.po_status)}</span><p>Untuk kebutuhan RKB: ${number(Math.min(Number(branch.po_quantity || 0), Number(item.summary.required || 0)))} · Tambahan untuk stock: ${number(Math.max(Number(branch.po_quantity || 0) - Number(item.summary.required || 0), 0))} · Total PO: ${number(branch.po_quantity)}</p></div><div>${branch.po_open_url ? `<a class="button-link" target="_blank" rel="noopener" href="${esc(branch.po_open_url)}">Buka PO</a>` : ""}</div>${branch.receipt_number ? `<div><strong>${esc(branch.receipt_number)}</strong><span>${esc(branch.receipt_status)}</span><p>${esc(branch.progress_text)}</p>${branch.receipt_open_url ? `<a class="button-link" target="_blank" rel="noopener" href="${esc(branch.receipt_open_url)}">Buka Receipt</a>` : ""}</div>` : ""}</div>`).join("") || `<p>Cabang ROP/PO/Receipt belum dapat dibuktikan.</p>`}</details>
        <details><summary>Nilai finansial</summary><p>Nilai RKB: ${money(item.financial.rkb_value)} · Nilai PO: ${money(item.financial.po_value)}</p></details></article>`).join("")}</div>
      <aside class="data-limitation"><strong>Data yang perlu dilengkapi</strong><ul>${(data.limitations || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul></aside></section>`;
  }

  function bindTrackingActions(data, embedded) {
    qsa("[data-tracking-mode]").forEach((button) => button.addEventListener("click", () => { state.trackingMode = button.dataset.trackingMode; embedded ? renderDocument().catch(showFailure) : renderTracking().catch(showFailure); }));
    qs("[data-toggle-activities]")?.addEventListener("click", () => { state.showAllActivities = !state.showAllActivities; embedded ? renderDocument().catch(showFailure) : renderTracking().catch(showFailure); });
    qsa("[data-branch-key]").forEach((button) => button.addEventListener("click", () => {
      const key = button.dataset.branchKey;
      if (state.collapsedBranches.has(key)) state.collapsedBranches.delete(key); else state.collapsedBranches.add(key);
      embedded ? renderDocument().catch(showFailure) : renderTracking().catch(showFailure);
    }));
  }

  function openSearch() {
    const dialog = qs("#searchDialog");
    dialog.showModal();
    setTimeout(() => qs("#globalSearchInput").focus(), 0);
  }

  async function performSearch(query) {
    const target = qs("#searchResults");
    if (query.trim().length < 2) { target.innerHTML = `<p class="search-help">Ketik minimal dua karakter.</p>`; return; }
    target.innerHTML = `<p class="search-help">Mencari…</p>`;
    try {
      const data = await apiJson(`/search?q=${encodeURIComponent(query.trim())}&limit=100`);
      target.innerHTML = data.groups.length ? data.groups.map((group) => `<section><h3>${esc(group.type)}</h3><ul>${group.documents.map((document) => `<li><a data-search-detail href="${esc(document.detail_url)}"><strong>${esc(document.number)}</strong><span>${esc(document.status || "Status tidak tersedia")}</span><small>${esc(document.secondary || "Informasi tambahan belum tersedia")}</small>${document.active_findings ? `<em>${number(document.active_findings)} Temuan Aktif</em>` : ""}</a><a class="button-link" target="_blank" rel="noopener" href="${esc(document.open_url)}">Buka Odoo</a></li>`).join("")}</ul></section>`).join("") : `<div class="empty-state"><p>Dokumen tidak ditemukan.</p></div>`;
      qsa("[data-search-detail]", target).forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); qs("#searchDialog").close(); navigate(link.href); }));
    } catch (error) { target.innerHTML = `<p class="error-copy">${esc(error.message)}</p>`; }
  }

  async function startRefresh() {
    try {
      const started = await apiJson("/refresh", "POST");
      state.refreshJob = started;
      qs("#refreshButton").disabled = true;
      renderRefreshPanel(started);
      pollRefresh(started.poll_url || `/api/control-tower/refresh/${started.job_id}`);
    } catch (error) { toast(error.message, "danger"); }
  }

  async function pollRefresh(pollUrl) {
    clearTimeout(state.refreshTimer);
    try {
      const path = pollUrl.startsWith(API) ? pollUrl.slice(API.length) : pollUrl.replace(/^\/api\/control-tower/, "");
      const job = await apiJson(path);
      state.refreshJob = job;
      renderRefreshPanel(job);
      if (["QUEUED", "RUNNING"].includes(job.status)) state.refreshTimer = setTimeout(() => pollRefresh(pollUrl), 1200);
      else {
        qs("#refreshButton").disabled = false;
        if (job.status === "COMPLETED") { toast(job.message || "Data berhasil diperbarui."); await loadCurrentView(); }
      }
    } catch (error) { qs("#refreshButton").disabled = false; toast(error.message, "danger"); }
  }

  function renderRefreshPanel(job) {
    const panel = qs("#refreshPanel");
    const currentIndex = PHASES.findIndex(([key]) => key === job.phase);
    const percentageValue = Math.max(0, Math.min(100, Number(job.percentage || (job.status === "COMPLETED" ? 100 : 0))));
    panel.hidden = false;
    panel.innerHTML = `<header><div><strong>Refresh Data Odoo</strong><span>${esc(job.phase_label || job.message || "Persiapan")}</span></div><button data-minimize-refresh type="button" aria-label="Minimalkan">−</button></header><div class="refresh-panel-body"><div class="progress-heading"><strong>${number(percentageValue, { maximumFractionDigits: 1 })}%</strong><span>${esc(job.current_work || "Menunggu proses berikutnya")}</span></div><progress max="100" value="${percentageValue}">${percentageValue}%</progress>${job.processed_records !== null && job.processed_records !== undefined ? `<p>${number(job.processed_records)} / ${job.total_records === null ? "?" : number(job.total_records)} record</p>` : ""}<ol>${PHASES.map(([key, label], index) => `<li class="${job.status === "FAILED" && key === job.failed_phase ? "is-failed" : index < currentIndex || job.status === "COMPLETED" ? "is-done" : index === currentIndex ? "is-active" : ""}"><span></span>${esc(label)}</li>`).join("")}</ol>${job.status === "FAILED" ? `<div class="refresh-error"><strong>${esc(job.failed_phase_label || job.phase_label || "Tahap gagal")}</strong><p>${esc(job.error_message || job.message)}</p><div><button class="button-primary" data-retry-refresh type="button">Coba Lagi dari Tahap Gagal</button><button class="button-secondary" data-close-refresh type="button">Tutup</button></div></div>` : job.status === "COMPLETED" && job.final_summary ? `<div class="refresh-summary"><strong>Selesai</strong><p>${number(job.final_summary.documents_changed || job.changed_documents)} dokumen berubah · ${number(job.final_summary.new_findings || 0)} temuan baru · ${number(job.final_summary.auto_resolved_findings || 0)} selesai otomatis</p><small>${esc(job.final_summary.duration || "")} · ${dateTime(job.completed_at)}</small></div>` : ""}</div>`;
    qs("[data-minimize-refresh]")?.addEventListener("click", () => panel.classList.toggle("is-minimized"));
    qs("[data-close-refresh]")?.addEventListener("click", () => { panel.hidden = true; });
    qs("[data-retry-refresh]")?.addEventListener("click", async () => {
      try { const retry = await apiJson(`/refresh/${job.job_id}/retry`, "POST"); pollRefresh(retry.poll_url); } catch (error) { toast(error.message, "danger"); }
    });
  }

  async function updateFreshness() {
    try {
      const health = await apiJson("/health");
      const completed = health.latest_run?.completed_at || health.last_successful_odoo_sync_at;
      qs("#odooSyncTime").textContent = dateTime(completed);
      qs("#screenRefreshTime").textContent = dateTime(new Date().toISOString());
    } catch (_error) {
      qs("#odooSyncTime").textContent = "Belum tersedia";
      qs("#screenRefreshTime").textContent = dateTime(new Date().toISOString());
    }
  }

  function showFailure(error) {
    setBusy(false);
    qs("#viewContainer").innerHTML = `<div class="error-state"><h1>Data terbaru belum dapat dimuat</h1><p>${esc(error.message)}</p><button class="button-primary" data-retry-view type="button">Coba lagi</button></div>`;
    qs("[data-retry-view]").onclick = () => loadCurrentView();
  }

  async function loadCurrentView() {
    const params = currentParams();
    state.view = params.get("view") || "findings";
    syncNavigation(state.view);
    setBusy(true);
    try {
      if (state.view === "archive") await renderFindings(true);
      else if (state.view === "process-map") await renderProcessMap();
      else if (state.view === "tracking") await renderTracking();
      else if (state.view === "document") await renderDocument();
      else await renderFindings(false);
      setBusy(false);
      qs("#screenRefreshTime").textContent = dateTime(new Date().toISOString());
    } catch (error) { showFailure(error); }
  }

  function parseRoute(path) {
    const tokens = String(path).trim().split(/\s+/);
    const points = [];
    let x = 0, y = 0;
    for (let index = 0; index < tokens.length; index += 1) {
      const command = tokens[index][0];
      const raw = tokens[index].slice(1);
      if (command === "M") { x = Number(raw); y = Number(tokens[++index]); points.push([x, y]); }
      else if (command === "H") { x = Number(raw); points.push([x, y]); }
      else if (command === "V") { y = Number(raw); points.push([x, y]); }
      else throw new Error(`Unsupported route command: ${command}`);
    }
    return points;
  }

  function routeSegments(path) {
    const points = parseRoute(path);
    return points.slice(1).map((point, index) => ({ x1: points[index][0], y1: points[index][1], x2: point[0], y2: point[1] }));
  }

  function segmentCrossesNode(segment, node, allowEndpoint = false) {
    const left = node.x, right = node.x + node.w, top = node.y, bottom = node.y + node.h;
    const inside = (x, y) => x > left && x < right && y > top && y < bottom;
    if (allowEndpoint && (inside(segment.x1, segment.y1) || inside(segment.x2, segment.y2))) return false;
    if (segment.y1 === segment.y2) return segment.y1 > top && segment.y1 < bottom && Math.max(segment.x1, segment.x2) > left && Math.min(segment.x1, segment.x2) < right;
    return segment.x1 > left && segment.x1 < right && Math.max(segment.y1, segment.y2) > top && Math.min(segment.y1, segment.y2) < bottom;
  }

  function validateMapGeometry(nodes = MAP_NODES, routes = MAP_ROUTES) {
    const errors = [];
    for (let index = 0; index < nodes.length; index += 1) {
      for (let other = index + 1; other < nodes.length; other += 1) {
        const a = nodes[index], b = nodes[other];
        if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) errors.push(`node-overlap:${a.id}:${b.id}`);
      }
    }
    for (const route of routes) {
      for (const segment of routeSegments(route.d)) {
        if (segment.x1 !== segment.x2 && segment.y1 !== segment.y2) errors.push(`diagonal:${route.from}:${route.to}`);
        for (const node of nodes) {
          if ([route.from, route.to].includes(node.id)) continue;
          if (segmentCrossesNode(segment, node)) errors.push(`route-node:${route.from}:${route.to}:${node.id}`);
        }
      }
    }
    return errors;
  }

  function bindShell() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest("[data-route-link]");
      if (!link || link.target === "_blank" || event.ctrlKey || event.metaKey || event.shiftKey) return;
      event.preventDefault(); navigate(link.href);
    });
    qs("#searchButton").addEventListener("click", openSearch);
    qs("#globalSearchInput").addEventListener("input", (event) => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => performSearch(event.target.value), 250);
    });
    qs("#refreshButton").addEventListener("click", startRefresh);
    qs("#themeButton").addEventListener("click", () => {
      const selected = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = selected; localStorage.setItem("control-tower-theme", selected);
      qs("#themeButton").textContent = `Dark Mode · ${selected === "dark" ? "On" : "Off"}`;
    });
    window.addEventListener("popstate", () => loadCurrentView().then(() => window.scrollTo(0, history.state?.scroll || 0)));
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !/input|textarea|select/i.test(event.target.tagName)) { event.preventDefault(); openSearch(); }
    });
  }

  function start() {
    const selectedTheme = localStorage.getItem("control-tower-theme") || "light";
    document.documentElement.dataset.theme = selectedTheme;
    qs("#themeButton").textContent = `Dark Mode · ${selectedTheme === "dark" ? "On" : "Off"}`;
    bindShell(); updateFreshness(); loadCurrentView();
  }

  return Object.freeze({ MAP_LANES, MAP_NODES, MAP_ROUTES, PHASES, parseRoute, routeSegments, segmentCrossesNode, validateMapGeometry, start });
});
