(function runControlTower() {
  "use strict";

  const A = window.ControlTowerAdapter;
  const pageState = document.getElementById("pageState");
  const viewContainer = document.getElementById("viewContainer");
  const freshnessBanner = document.getElementById("freshnessBanner");
  const refreshButton = document.getElementById("refreshButton");
  const JOURNEY_PAGE_SIZE = 50;
  const allowedViews = new Set(["overview", "validation", "exceptions", "journey"]);
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view") || "overview";
  const currentView = allowedViews.has(requestedView) ? requestedView : "overview";

  const exceptionState = {
    classification: params.get("classification") || "active",
    rule: params.get("rule") || "",
    process: params.get("process") || "",
    owner: params.get("owner") || "",
    severity: params.get("severity") || "",
    document: params.get("document") || "",
    date_from: params.get("date_from") || "",
    date_to: params.get("date_to") || "",
    limit: 25,
    offset: Math.max(0, Number(params.get("offset")) || 0),
  };

  document.querySelectorAll("[data-view-link]").forEach((link) => {
    if (link.dataset.viewLink === currentView) link.setAttribute("aria-current", "page");
  });

  function statusBadge(status) {
    return `<span class="status-badge tone-${A.escapeHtml(status.tone)}">${A.escapeHtml(status.label)}</span>`;
  }

  function secondaryReference(rawStatus, ruleId) {
    const parts = [];
    if (ruleId) parts.push(`Referensi teknis: ${ruleId}`);
    if (rawStatus) parts.push(`Status teknis: ${rawStatus}`);
    return A.escapeHtml(parts.join(" · "));
  }

  function viewHeading(title, description, meta = "") {
    return `
      <div class="view-heading">
        <div>
          <h2>${A.escapeHtml(title)}</h2>
          <p>${A.escapeHtml(description)}</p>
        </div>
        ${meta ? `<span class="view-meta">${A.escapeHtml(meta)}</span>` : ""}
      </div>`;
  }

  function setLoading(message = "Memuat data Control Tower…") {
    viewContainer.setAttribute("aria-busy", "true");
    pageState.innerHTML = `
      <section class="state-panel tone-info" role="status">
        <h2>Memuat data</h2>
        <p>${A.escapeHtml(message)}</p>
      </section>`;
    viewContainer.innerHTML = "";
  }

  function clearState() {
    pageState.innerHTML = "";
    viewContainer.setAttribute("aria-busy", "false");
  }

  function errorPanel(error) {
    const kind = A.classifyHttpStatus(error.httpStatus || 0);
    if (kind === "session-expired") {
      const next = encodeURIComponent("/dashboard/control-tower");
      return `
        <section class="state-panel tone-warning" role="alert">
          <h2>Sesi dashboard sudah berakhir</h2>
          <p>Masuk kembali untuk melanjutkan. Data belum diubah.</p>
          <div class="state-actions"><a class="secondary-button" href="/login?next=${next}">Masuk kembali</a></div>
        </section>`;
    }
    if (error.httpStatus === 404 && currentView === "journey") {
      return `
        <section class="state-panel tone-warning" role="alert">
          <h2>Dokumen tidak ditemukan</h2>
          <p>Dokumen tidak tersedia pada extraction run terbaru yang sudah selesai. Periksa model dan native ID.</p>
          <div class="state-actions"><button class="secondary-button" type="button" data-retry>Muat ulang</button></div>
        </section>`;
    }
    return `
      <section class="state-panel tone-danger" role="alert">
        <h2>Data tidak dapat dimuat</h2>
        <p>Detail teknis sensitif tidak ditampilkan. Coba lagi, lalu hubungi pemilik layanan bila masalah berlanjut.</p>
        <div class="state-actions"><button class="secondary-button" type="button" data-retry>Coba lagi</button></div>
      </section>`;
  }

  function showError(error) {
    viewContainer.setAttribute("aria-busy", "false");
    viewContainer.innerHTML = "";
    pageState.innerHTML = errorPanel(error);
    pageState.querySelector("[data-retry]")?.addEventListener("click", loadCurrentView);
  }

  async function apiJson(url) {
    const started = performance.now();
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const error = new Error("Control Tower request failed");
      error.httpStatus = response.status;
      throw error;
    }
    const payload = await response.json();
    performance.mark(`control-tower-response-${url.split("?")[0]}`);
    payload.__clientElapsedMs = performance.now() - started;
    return payload;
  }

  function showFreshness(health) {
    const freshness = A.freshnessState(health);
    freshnessBanner.hidden = false;
    freshnessBanner.className = `notice-banner tone-${freshness.tone}`;
    freshnessBanner.innerHTML = `<strong>${A.escapeHtml(freshness.label)}</strong><span>${A.escapeHtml(freshness.detail)}</span>`;
  }

  function kpiCard(label, value, context) {
    return `
      <article class="kpi-card">
        <span class="kpi-label">${A.escapeHtml(label)}</span>
        <strong>${A.escapeHtml(value)}</strong>
        <span class="kpi-context">${A.escapeHtml(context)}</span>
      </article>`;
  }

  async function renderOverview() {
    setLoading("Memuat kesehatan layanan data, validasi SOP, cakupan PO, dan ringkasan Internal Order…");
    try {
      const [health, validation, poScope, ioHealth] = await Promise.all([
        apiJson("/api/control-tower/health"),
        apiJson("/api/control-tower/sop-validation"),
        apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
        apiJson("/api/control-tower/io-health?limit=1&offset=0"),
      ]);
      const metrics = A.overviewMetrics(health, validation.rows, poScope.summary, ioHealth.summary);
      const completedAt = health.latest_run?.completed_at;
      showFreshness(health);
      clearState();
      viewContainer.innerHTML = `
        ${viewHeading(
          "Ringkasan kesehatan proses",
          "KPI aktif dipisahkan dari catatan historis dan bukti yang masih perlu ditinjau.",
          `Status layanan data: ${health.status || "belum tersedia"} · ${A.formatDateTime(completedAt)}`,
        )}
        <section class="kpi-grid" aria-label="Ringkasan KPI Control Tower">
          ${kpiCard("Pemeriksaan Dilakukan", A.formatNumber(metrics.checksPerformed), "Hasil pemeriksaan pada snapshot aktif")}
          ${kpiCard("Proses Sesuai", A.formatNumber(metrics.compliant), "Hasil yang lolos pemeriksaan")}
          ${kpiCard("Masalah Aktif", A.formatNumber(metrics.active), "Tidak termasuk catatan historis")}
          ${kpiCard("Catatan Historis", A.formatNumber(metrics.historical), "PO sebelum tahun 2026")}
          ${kpiCard("Perlu Ditinjau", A.formatNumber(metrics.review), "Belum menjadi masalah terkonfirmasi")}
          ${kpiCard("Bukti Sistem Belum Lengkap", A.formatNumber(metrics.incomplete), "Hubungan data perlu dilengkapi")}
        </section>

        <div class="summary-layout">
          <section class="panel section-panel" aria-labelledby="processHealthTitle">
            <h3 id="processHealthTitle">Peta kesehatan proses</h3>
            <p>Peta ini menunjukkan cakupan proses, bukan tren dan bukan urutan waktu setiap dokumen.</p>
            <ol class="process-map">
              <li>Sales Order</li>
              <li>Internal Order / Manufacturing</li>
              <li>Procurement</li>
              <li>Receipt</li>
              <li>Production</li>
              <li>Delivery</li>
              <li>Invoice</li>
            </ol>
            <ul class="publication-list">
              <li><strong>Payment</strong>${statusBadge(A.statusPresentation("MAPPING_PENDING"))}</li>
              <li><span>Status Payment belum dipublikasikan sampai keputusan Accounting selesai.</span></li>
              <li><strong>Distribusi JO</strong>${statusBadge(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED"))}</li>
              <li><span>Distribusi JO memerlukan bukti manual dan tidak disimpulkan dari status Odoo.</span></li>
            </ul>
          </section>

          <section class="panel section-panel" aria-labelledby="ioHealthTitle">
            <h3 id="ioHealthTitle">Kesehatan Internal Order</h3>
            <p>Ringkasan dihitung oleh layanan data dari view aktif, tanpa mengunduh seluruh baris ke browser.</p>
            <ul class="io-health-list">
              <li><span>Internal Order utama</span><strong>${A.formatNumber(metrics.ioRoots)}</strong></li>
              <li><span>Baris produk–satuan ukur</span><strong>${A.formatNumber(metrics.ioRows)}</strong></li>
              <li><span>Bukti produksi belum lengkap</span><strong>${A.formatNumber(metrics.productionGaps)}</strong></li>
              <li><span>Bukti pemanfaatan belum lengkap</span><strong>${A.formatNumber(metrics.utilizationGaps)}</strong></li>
            </ul>
            <div class="manual-stage state-panel tone-success">
              <strong>PO cancellation 2026</strong>
              <p>${A.formatNumber(metrics.po.checked)} diperiksa, ${A.formatNumber(metrics.po.checked - metrics.po.active)} sesuai, dan ${A.formatNumber(metrics.po.active)} masalah aktif.</p>
            </div>
          </section>
        </div>`;
    } catch (error) {
      showError(error);
    }
  }

  function worklistClassification(status, rule) {
    if (rule.ruleId === "PO-CANCEL-001" && rule.historicalCount > 0 && !rule.activeIssues) return "historical";
    return {
      MISMATCH: "active",
      PARTIAL_MATCH: "review",
      DATA_LINKAGE_GAP: "incomplete",
      DATA_EXCEPTION: "incomplete",
      DOCUMENT_LINK_GAP: "incomplete",
    }[status] || "incomplete";
  }

  function validationRow(rule) {
    const classification = worklistClassification(rule.rawStatus, rule);
    const exceptionUrl = new URLSearchParams({ view: "exceptions", classification, rule: rule.ruleId });
    return `
      <tr>
        <td class="validation-title">
          <strong>${A.escapeHtml(rule.title)}</strong>
          ${rule.currentSummary ? `<span>${A.escapeHtml(rule.currentSummary)}</span>` : ""}
          <span>${secondaryReference(rule.rawStatus, rule.ruleId)}</span>
        </td>
        <td>${statusBadge(rule.status)}</td>
        <td class="business-explanation">
          <strong>${A.escapeHtml(rule.explanation)}</strong>
          <span><b>Mengapa penting:</b> ${A.escapeHtml(rule.why)}</span>
          <span><b>Dampak:</b> ${A.escapeHtml(rule.impact)}</span>
        </td>
        <td>${A.escapeHtml(rule.owner)}</td>
        <td class="num">${A.formatNumber(rule.checkedCount)}</td>
        <td class="num">${A.formatNumber(rule.compliantCount)}</td>
        <td class="num">${A.formatNumber(rule.activeIssues)}</td>
        <td class="num">${A.formatNumber(rule.historicalCount)}</td>
        <td class="num">${A.formatNumber(rule.reviewRequired)}</td>
        <td class="num">${A.formatNumber(rule.incompleteEvidence)}</td>
        <td>${A.escapeHtml(rule.evidenceStrength)}<span class="cell-note">${A.formatPercent(rule.validationRate)}</span></td>
        <td>${A.formatDateTime(rule.latestEvaluation)}</td>
        <td><a class="table-link" href="?${exceptionUrl}">Lihat daftar</a></td>
      </tr>`;
  }

  async function renderValidation() {
    setLoading("Memuat seluruh pemeriksaan yang dipublikasikan dan ringkasan pembatalan PO…");
    try {
      const [health, validation, poScope] = await Promise.all([
        apiJson("/api/control-tower/health"),
        apiJson("/api/control-tower/sop-validation"),
        apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
      ]);
      showFreshness(health);
      const context = {
        completedAt: health.latest_run?.completed_at,
        po: A.poScopeSummary(poScope.summary),
      };
      const rules = (validation.rows || []).map((row) => A.normalizeRule(row, context));
      clearState();
      viewContainer.innerHTML = `
        ${viewHeading(
          "Matriks Validasi SOP",
          "Bahasa bisnis menjadi penjelasan utama; status dan rule teknis tetap tersedia sebagai referensi sekunder.",
          `${A.formatNumber(rules.length)} pemeriksaan dipublikasikan`,
        )}
        <section class="table-panel" aria-label="Matriks validasi SOP">
          <div class="table-scroll" tabindex="0" aria-label="Tabel dapat digulir secara horizontal">
            <table class="validation-table">
              <thead>
                <tr>
                  <th>Kontrol bisnis</th>
                  <th>Status</th>
                  <th>Penjelasan, alasan, dan dampak</th>
                  <th>Tim yang meninjau</th>
                  <th class="num">Diperiksa</th>
                  <th class="num">Sesuai</th>
                  <th class="num">Aktif</th>
                  <th class="num">Historis</th>
                  <th class="num">Ditinjau</th>
                  <th class="num">Bukti belum lengkap</th>
                  <th>Bukti</th>
                  <th>Evaluasi terakhir</th>
                  <th>Pengecualian</th>
                </tr>
              </thead>
              <tbody>${rules.map(validationRow).join("")}</tbody>
            </table>
          </div>
        </section>`;
    } catch (error) {
      showError(error);
    }
  }

  function classificationOptions(selected) {
    const options = [
      ["active", "Masalah Aktif"],
      ["historical", "Catatan Historis"],
      ["review", "Perlu Ditinjau"],
      ["incomplete", "Bukti Sistem Belum Lengkap"],
    ];
    return options.map(([value, label]) => `<option value="${value}"${selected === value ? " selected" : ""}>${label}</option>`).join("");
  }

  function selectOptions(options, selected, emptyLabel) {
    return `<option value="">${A.escapeHtml(emptyLabel)}</option>` + options.map(([value, label]) => `
      <option value="${A.escapeHtml(value)}"${selected === value ? " selected" : ""}>${A.escapeHtml(label)}</option>`).join("");
  }

  function ownerOptions(selected) {
    return `<option value="">Semua tim</option>` + A.OWNER_FILTERS.map((owner) => `
      <option value="${A.escapeHtml(owner)}"${selected === owner ? " selected" : ""}>${A.escapeHtml(owner)}</option>`).join("");
  }

  function filtersHtml() {
    const historical = exceptionState.classification === "historical";
    const disabled = historical ? " disabled" : "";
    return `
      <form class="filter-panel worklist-filters" id="worklistFilters">
        <label class="classification-control">
          <span>Klasifikasi</span>
          <select id="classificationFilter">${classificationOptions(exceptionState.classification)}</select>
        </label>
        <label>
          <span>Proses</span>
          <select id="processFilter"${disabled}>${selectOptions(A.PROCESS_FILTERS, exceptionState.process, "Semua proses")}</select>
        </label>
        <label>
          <span>Tim peninjau</span>
          <select id="ownerFilter"${disabled}>${ownerOptions(exceptionState.owner)}</select>
        </label>
        <label>
          <span>Tingkat dampak</span>
          <select id="severityFilter"${disabled}>
            <option value="">Semua tingkat dampak</option>
            <option value="HIGH"${exceptionState.severity === "HIGH" ? " selected" : ""}>Tinggi</option>
            <option value="MEDIUM"${exceptionState.severity === "MEDIUM" ? " selected" : ""}>Sedang</option>
          </select>
        </label>
        <label>
          <span>Dokumen</span>
          <input id="documentFilter" type="search" maxlength="100" value="${A.escapeHtml(exceptionState.document)}" placeholder="Cari nomor dokumen"${disabled}>
        </label>
        <label>
          <span>Tanggal dari</span>
          <input id="dateFromFilter" type="date" value="${A.escapeHtml(exceptionState.date_from)}"${disabled}>
        </label>
        <label>
          <span>Tanggal sampai</span>
          <input id="dateToFilter" type="date" value="${A.escapeHtml(exceptionState.date_to)}"${disabled}>
        </label>
        <button class="secondary-button" type="submit">Terapkan</button>
        <button class="secondary-button" id="clearWorklistFilters" type="button">Hapus filter</button>
      </form>`;
  }

  function selectedFiltersHtml() {
    const classificationLabel = {
      active: "Masalah Aktif",
      historical: "Catatan Historis",
      review: "Perlu Ditinjau",
      incomplete: "Bukti Sistem Belum Lengkap",
    }[exceptionState.classification];
    const tokens = [`Klasifikasi: ${classificationLabel}`];
    if (exceptionState.rule) tokens.push(`Rule: ${exceptionState.rule}`);
    if (exceptionState.process) tokens.push(`Proses: ${exceptionState.process}`);
    if (exceptionState.owner) tokens.push(`Tim: ${exceptionState.owner}`);
    if (exceptionState.severity) tokens.push(`Tingkat dampak: ${exceptionState.severity}`);
    if (exceptionState.document) tokens.push(`Dokumen: ${exceptionState.document}`);
    if (exceptionState.date_from || exceptionState.date_to) tokens.push(`Tanggal: ${exceptionState.date_from || "…"} sampai ${exceptionState.date_to || "…"}`);
    return `<div class="selected-filters" aria-label="Filter terpilih"><span>Filter terpilih</span>${tokens.map((token) => `<span class="filter-token">${A.escapeHtml(token)}</span>`).join("")}</div>`;
  }

  function relatedDocumentText(item) {
    const model = A.MODEL_LABELS[item.model] || item.model || "Dokumen terkait";
    const state = A.statePresentation(item.state);
    return `${item.number || "Nomor tidak tersedia"} · ${model} · ${state.label}`;
  }

  function severityLabel(value) {
    return { HIGH: "Tinggi", MEDIUM: "Sedang", LOW: "Rendah", HISTORICAL: "Historis" }[value] || "Belum tersedia";
  }

  function exceptionRow(item) {
    return `
      <tr>
        <td>${statusBadge(item.status)}<span class="cell-note">${A.escapeHtml(severityLabel(item.severity))}</span></td>
        <td class="exception-situation">
          <strong>${A.escapeHtml(item.situation)}</strong>
          <span>${A.escapeHtml(item.explanation)}</span>
          <span>${secondaryReference(item.rawStatus, item.ruleId)}</span>
        </td>
        <td class="exception-document">
          <strong>${A.escapeHtml(item.affectedDocument)}</strong>
          <span>${A.escapeHtml(item.affectedModel)}</span>
          ${(item.relatedDocuments || []).map((related) => `<span>Dokumen terkait: ${A.escapeHtml(relatedDocumentText(related))}</span>`).join("") || "<span>Dokumen terkait tersedia melalui Perjalanan Dokumen.</span>"}
        </td>
        <td>${A.escapeHtml(item.process)}</td>
        <td class="exception-impact">
          <strong>Mengapa penting:</strong> ${A.escapeHtml(item.why)}
          <span><b>Dampak:</b> ${A.escapeHtml(item.impact)}</span>
          <span><b>Tim yang perlu meninjau:</b> ${A.escapeHtml(item.reviewer)}</span>
        </td>
        <td>${statusBadge(item.confidence)}<span class="cell-note">${A.escapeHtml(A.formatDateTime(item.detectedAt))}</span></td>
        <td>${item.journeyUrl ? `<a class="table-link" href="${A.escapeHtml(item.journeyUrl)}">Buka perjalanan</a>` : "Tidak tersedia"}</td>
      </tr>`;
  }

  function bindExceptionControls(total) {
    const form = document.getElementById("worklistFilters");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const classification = document.getElementById("classificationFilter").value;
      exceptionState.classification = classification;
      exceptionState.offset = 0;
      if (classification === "historical") {
        Object.assign(exceptionState, { rule: "PO-CANCEL-001", process: "", owner: "", severity: "", document: "", date_from: "", date_to: "" });
      } else {
        exceptionState.process = document.getElementById("processFilter").value;
        exceptionState.owner = document.getElementById("ownerFilter").value;
        exceptionState.severity = document.getElementById("severityFilter").value;
        exceptionState.document = document.getElementById("documentFilter").value.trim();
        exceptionState.date_from = document.getElementById("dateFromFilter").value;
        exceptionState.date_to = document.getElementById("dateToFilter").value;
      }
      updateExceptionUrl();
      renderExceptions();
    });
    document.getElementById("classificationFilter").addEventListener("change", () => form.requestSubmit());
    document.getElementById("clearWorklistFilters").addEventListener("click", () => {
      Object.assign(exceptionState, {
        classification: "active",
        rule: "",
        process: "",
        owner: "",
        severity: "",
        document: "",
        date_from: "",
        date_to: "",
        offset: 0,
      });
      updateExceptionUrl();
      renderExceptions();
    });
    document.querySelector("[data-page='previous']")?.addEventListener("click", () => {
      exceptionState.offset = Math.max(0, exceptionState.offset - exceptionState.limit);
      updateExceptionUrl();
      renderExceptions();
    });
    document.querySelector("[data-page='next']")?.addEventListener("click", () => {
      if (exceptionState.offset + exceptionState.limit < total) {
        exceptionState.offset += exceptionState.limit;
        updateExceptionUrl();
        renderExceptions();
      }
    });
  }

  function updateExceptionUrl() {
    const next = new URLSearchParams({ view: "exceptions", classification: exceptionState.classification });
    for (const key of ["rule", "process", "owner", "severity", "document", "date_from", "date_to"]) {
      if (exceptionState[key]) next.set(key, exceptionState[key]);
    }
    if (exceptionState.offset) next.set("offset", String(exceptionState.offset));
    window.history.replaceState(null, "", `${window.location.pathname}?${next}`);
  }

  async function renderExceptions() {
    setLoading("Memuat pengecualian menggunakan filter dan paginasi layanan data…");
    try {
      const request = A.exceptionRequest(exceptionState);
      const [payload, poScope, health] = await Promise.all([
        apiJson(request.url),
        apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
        apiJson("/api/control-tower/health"),
      ]);
      const rows = request.kind === "historical"
        ? (payload.rows || []).map(A.normalizeHistoricalPo)
        : (payload.rows || []).map(A.normalizeException);
      const total = Number(payload.total || 0);
      const po = A.poScopeSummary(poScope.summary);
      showFreshness(health);
      clearState();
      viewContainer.innerHTML = `
        ${viewHeading(
          "Daftar Pengecualian",
          "Default hanya menampilkan masalah operasional aktif. Catatan historis dan bukti yang belum lengkap dipilih secara terpisah.",
          `${A.formatNumber(total)} hasil`,
        )}
        ${filtersHtml()}
        ${selectedFiltersHtml()}
        ${A.shouldShowActivePoEmptyState(exceptionState, total) ? `
          <section class="state-panel tone-success">
            <h2>Tidak ada masalah aktif untuk PO yang dibatalkan mulai tahun 2026.</h2>
            <p>${A.formatNumber(po.checked)} PO diperiksa dan ${A.formatNumber(po.checked - po.active)} sesuai. ${A.formatNumber(po.historical)} kasus sebelum tahun 2026 tetap tersedia sebagai Catatan Historis.</p>
          </section>` : ""}
        <section class="table-panel" aria-label="Daftar pengecualian Control Tower">
          <div class="table-scroll" tabindex="0" aria-label="Tabel dapat digulir secara horizontal">
            <table class="exception-table">
              <thead>
                <tr>
                  <th>Klasifikasi</th>
                  <th>Apa yang terjadi</th>
                  <th>Dokumen</th>
                  <th>Tahap proses</th>
                  <th>Alasan, dampak, dan peninjau</th>
                  <th>Bukti</th>
                  <th>Perjalanan</th>
                </tr>
              </thead>
              <tbody>
                ${rows.length ? rows.map(exceptionRow).join("") : `<tr><td colspan="7" class="empty-cell">${A.escapeHtml(A.emptyMessage(exceptionState.classification, exceptionState.rule))}</td></tr>`}
              </tbody>
            </table>
          </div>
          <div class="pagination-footer" aria-label="Pagination">
            <button class="secondary-button" type="button" data-page="previous"${exceptionState.offset <= 0 ? " disabled" : ""}>Sebelumnya</button>
            <span>${total ? `${A.formatNumber(exceptionState.offset + 1)}–${A.formatNumber(Math.min(total, exceptionState.offset + exceptionState.limit))} dari ${A.formatNumber(total)}` : "0 hasil"}</span>
            <button class="secondary-button" type="button" data-page="next"${exceptionState.offset + exceptionState.limit >= total ? " disabled" : ""}>Berikutnya</button>
          </div>
        </section>`;
      bindExceptionControls(total);
    } catch (error) {
      showError(error);
    }
  }

  function journeySearch(model = "", id = "") {
    const models = [
      ["sale.order", "Sales Order"],
      ["sale.order.line", "Baris Sales Order"],
      ["approval.request", "Internal Order"],
      ["approval.product.line", "Baris Internal Order"],
      ["mrp.production", "Manufacturing Order"],
      ["purchase.order", "Purchase Order"],
      ["stock.picking", "Receipt / Delivery"],
      ["account.move", "Invoice"],
    ];
    return `
      <form class="filter-panel journey-search" id="journeySearch">
        <label>
          <span>Jenis dokumen utama</span>
          <select id="journeyModel" required>
            <option value="">Pilih jenis dokumen</option>
            ${models.map(([value, label]) => `<option value="${value}"${model === value ? " selected" : ""}>${label}</option>`).join("")}
          </select>
        </label>
        <label>
          <span>Native ID Odoo</span>
          <input id="journeyId" type="number" min="1" step="1" value="${A.escapeHtml(id)}" placeholder="Contoh: 116" required>
        </label>
        <button class="secondary-button" type="submit">Tampilkan hubungan</button>
      </form>`;
  }

  function bindJourneySearch() {
    document.getElementById("journeySearch").addEventListener("submit", (event) => {
      event.preventDefault();
      const model = document.getElementById("journeyModel").value;
      const id = document.getElementById("journeyId").value;
      if (!model || !id) return;
      window.location.assign(A.documentLink(model, id));
    });
  }

  function journeyRelationRow(link) {
    return `
      <tr>
        <td class="num">${A.formatNumber(link.depth)}</td>
        <td class="relation-document">
          <strong>${A.escapeHtml(link.parent.number)}</strong>
          <span>${A.escapeHtml(link.parent.modelLabel)} · Native ID ${A.escapeHtml(link.parent.id)}</span>
        </td>
        <td>${statusBadge(link.parent.state)}</td>
        <td class="relation-document">
          <strong>${A.escapeHtml(link.child.number)}</strong>
          <span>${A.escapeHtml(link.child.modelLabel)} · Native ID ${A.escapeHtml(link.child.id)}</span>
        </td>
        <td>${statusBadge(link.child.state)}</td>
        <td>${statusBadge(link.evidence)}<span class="cell-note">${A.escapeHtml(link.linkType || "Tipe hubungan belum tersedia")}</span></td>
        <td>${statusBadge(link.confidence)}</td>
      </tr>`;
  }

  function bindJourneyPagination(journey) {
    let page = Math.max(1, Number(new URLSearchParams(window.location.search).get("journey_page")) || 1);
    const totalPages = Math.max(1, Math.ceil(journey.links.length / JOURNEY_PAGE_SIZE));
    page = Math.min(page, totalPages);
    const tbody = document.getElementById("journeyRows");
    const status = document.getElementById("journeyPageStatus");
    const previous = document.querySelector("[data-journey-page='previous']");
    const next = document.querySelector("[data-journey-page='next']");

    function draw() {
      const start = (page - 1) * JOURNEY_PAGE_SIZE;
      const visible = journey.links.slice(start, start + JOURNEY_PAGE_SIZE);
      tbody.innerHTML = visible.length
        ? visible.map(journeyRelationRow).join("")
        : `<tr><td colspan="7" class="empty-cell">Belum ada hubungan dokumen pada snapshot terbaru.</td></tr>`;
      status.textContent = journey.links.length
        ? `${A.formatNumber(start + 1)}–${A.formatNumber(Math.min(journey.links.length, start + JOURNEY_PAGE_SIZE))} dari ${A.formatNumber(journey.links.length)}`
        : "0 hubungan";
      previous.disabled = page <= 1;
      next.disabled = page >= totalPages;
      const url = new URL(window.location.href);
      if (page > 1) url.searchParams.set("journey_page", String(page));
      else url.searchParams.delete("journey_page");
      window.history.replaceState(null, "", url);
    }

    previous.addEventListener("click", () => {
      page = Math.max(1, page - 1);
      draw();
    });
    next.addEventListener("click", () => {
      page = Math.min(totalPages, page + 1);
      draw();
    });
    draw();
  }

  function journeyValidationRows(validations) {
    if (!validations.length) return `<li><span>Tidak ada hasil validasi langsung untuk dokumen utama ini.</span></li>`;
    return validations.map((item) => `
      <li>
        <span><strong>${A.escapeHtml(item.situation)}</strong><br>${secondaryReference(item.rawStatus, item.ruleId)}</span>
        ${statusBadge(item.status)}
      </li>`).join("");
  }

  async function renderJourney() {
    const model = params.get("model") || "";
    const id = params.get("id") || "";
    if (!model || !id) {
      setLoading("Memuat status layanan data…");
      try {
        const health = await apiJson("/api/control-tower/health");
        showFreshness(health);
        clearState();
        viewContainer.innerHTML = `
          ${viewHeading(
            "Perjalanan Dokumen",
            "Cari berdasarkan jenis dokumen dan native ID. Tampilan menunjukkan hubungan yang diketahui, bukan kronologi kejadian.",
          )}
          ${journeySearch()}
          <section class="summary-layout">
            <article class="panel section-panel">
              <h3>Bukti hubungan</h3>
              <p>Dokumen dapat memiliki lebih dari satu relasi. Bukti langsung, turunan, dan manual ditampilkan terpisah.</p>
            </article>
            <article class="panel section-panel">
              <h3>Cakupan yang belum diterbitkan</h3>
              <ul class="publication-list">
                <li><span>Payment</span>${statusBadge(A.statusPresentation("MAPPING_PENDING"))}</li>
                <li><span>Distribusi JO</span>${statusBadge(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED"))}</li>
              </ul>
            </article>
          </section>`;
        bindJourneySearch();
      } catch (error) {
        showError(error);
      }
      return;
    }

    setLoading("Memuat dokumen utama, hubungan native, dan validasi terkait…");
    try {
      const [payload, health] = await Promise.all([
        apiJson(`/api/control-tower/journey/${encodeURIComponent(model)}/${encodeURIComponent(id)}`),
        apiJson("/api/control-tower/health"),
      ]);
      const journey = A.normalizeJourney(payload);
      const validations = (payload.validations || []).map(A.normalizeException);
      showFreshness(health);
      clearState();
      viewContainer.innerHTML = `
        ${viewHeading(
          "Perjalanan Dokumen",
          "Hubungan berikut tidak menyatakan urutan waktu. Setiap status berasal dari snapshot terbaru yang sudah selesai.",
          `${A.formatNumber(journey.links.length)} hubungan`,
        )}
        ${journeySearch(model, id)}
        <section class="journey-summary" aria-label="Dokumen utama">
          <article class="detail-item"><span>Jenis dokumen</span><strong>${A.escapeHtml(journey.root.modelLabel)}</strong></article>
          <article class="detail-item"><span>Nomor dokumen</span><strong>${A.escapeHtml(journey.root.number)}</strong></article>
          <article class="detail-item"><span>Native ID</span><strong>${A.escapeHtml(journey.root.id)}</strong></article>
          <article class="detail-item"><span>Status dokumen</span><strong>${A.escapeHtml(journey.root.state.label)}</strong></article>
        </section>
        <div class="journey-layout">
          <section class="table-panel" aria-label="Hubungan dokumen">
            <div class="table-toolbar">
              <div class="table-toolbar-primary"><strong>Hubungan dokumen</strong><span>Bukan urutan waktu; tingkat relasi hanya menunjukkan jarak hubungan.</span></div>
            </div>
            <div class="table-scroll" tabindex="0" aria-label="Tabel hubungan dapat digulir secara horizontal">
              <table class="relation-table">
                <thead>
                  <tr><th>Tingkat relasi</th><th>Dokumen asal</th><th>Status asal</th><th>Dokumen terkait</th><th>Status terkait</th><th>Bukti relasi</th><th>Kekuatan bukti</th></tr>
                </thead>
                <tbody id="journeyRows"></tbody>
              </table>
            </div>
            <div class="pagination-footer" aria-label="Pagination hubungan dokumen">
              <button class="secondary-button" type="button" data-journey-page="previous">Sebelumnya</button>
              <span id="journeyPageStatus">0 hubungan</span>
              <button class="secondary-button" type="button" data-journey-page="next">Berikutnya</button>
            </div>
          </section>
          <aside class="panel section-panel" aria-label="Kelengkapan perjalanan">
            <h3>Tahap yang ditemukan</h3>
            <p>Tahap yang tidak terlihat tidak dianggap gagal; hubungan mungkin memang tidak tersedia atau tidak berlaku.</p>
            <ul class="missing-stages">
              ${journey.expectedStages.map((stage) => `<li><span>${A.escapeHtml(stage.label)}</span>${statusBadge(stage.available ? { label: "Ditemukan", tone: "success" } : { label: "Tidak ditemukan", tone: "neutral" })}</li>`).join("")}
            </ul>
            <h3>Validasi dokumen utama</h3>
            <ul class="evidence-legend">${journeyValidationRows(validations)}</ul>
            <div class="manual-stage">
              <strong>Payment</strong><br>${statusBadge(A.statusPresentation("MAPPING_PENDING"))}
              <p class="muted-note">Belum dipublikasikan.</p>
              <strong>Distribusi JO</strong><br>${statusBadge(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED"))}
              <p class="muted-note">Memerlukan bukti manual.</p>
            </div>
          </aside>
        </div>`;
      bindJourneySearch();
      bindJourneyPagination(journey);
    } catch (error) {
      showError(error);
    }
  }

  function loadCurrentView() {
    ({
      overview: renderOverview,
      validation: renderValidation,
      exceptions: renderExceptions,
      journey: renderJourney,
    }[currentView] || renderOverview)();
  }

  refreshButton.addEventListener("click", loadCurrentView);
  loadCurrentView();
})();
