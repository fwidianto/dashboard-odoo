(() => {
  "use strict";
  const refs = {};
  "backLink freshnessBanner freshnessLabel freshnessTitle freshnessDetails refreshButton categoryFilter processFilter ruleFilter severityFilter sortFilter clearFilters categorySummary worklistStatus findingList previousPage nextPage paginationStatus inspectorState inspectorBody inspectorPresentation inspectorProcess inspectorRule inspectorStatus inspectorSeverity inspectorConfidence inspectorDocument inspectorExplanation inspectorEvidence inspectorLimitation inspectorDestination inspectorRaw".split(" ").forEach((id) => { refs[id] = document.getElementById(id); });
  const labels = { MASALAH_AKTIF: "Masalah Aktif", PERLU_DITINJAU: "Perlu Ditinjau", DATA_BELUM_LENGKAP: "Data Belum Lengkap" };
  const state = { filters: { presentation_category: "", process_key: "", rule_id: "", severity: "", sort: "attention" }, rows: [], offset: 0, limit: 25, total: 0, selectedKey: null, requestId: 0, health: null, refresh: null };
  let returnTo = "/dashboard/control-tower";
  let idleResetTimer;
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  const display = (value) => value === null || value === undefined || value === "" ? "—" : String(value);
  const formatDate = (value) => {
    if (!value) return "belum tersedia";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" }).format(date);
  };
  const formatEvidence = (value) => {
    if (value === null || value === undefined || value === "") return "Belum tersedia.";
    if (typeof value !== "string") return JSON.stringify(value, null, 2);
    try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
  };
  const safeDestination = (raw) => {
    if (!raw || typeof raw !== "string") return "";
    try {
      const url = new URL(raw, window.location.origin);
      return url.origin === window.location.origin && url.pathname.startsWith("/dashboard/") ? url.pathname + url.search + url.hash : "";
    } catch { return ""; }
  };
  function destinationFor(row) {
    const destination = safeDestination(row && row.destination_url);
    if (!destination) return "";
    const url = new URL(destination, window.location.origin);
    const context = new URL(window.location.href);
    context.searchParams.set("selected_finding", rowKey(row));
    context.searchParams.set("return_to", returnTo);
    url.searchParams.set("return_to", context.pathname + context.search);
    return url.pathname + url.search + url.hash;
  }
  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, ...options });
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) throw new Error((payload && payload.detail) || "Request gagal (" + response.status + ").");
    return payload;
  }
  const rowKey = (row) => String(row.evidence_key || [row.rule_id, row.affected_model, row.document_id].join("|"));
  function setOptions(select, options, selected) {
    select.innerHTML = options.map((option) => '<option value="' + escapeHtml(option.value) + '">' + escapeHtml(option.label) + "</option>").join("");
    select.value = options.some((option) => option.value === selected) ? selected : "";
  }
  function renderFilters(filters = {}) {
    setOptions(refs.categoryFilter, [{ value: "", label: "Semua kategori" }, ...(filters.presentation_categories || [])], state.filters.presentation_category);
    setOptions(refs.processFilter, [{ value: "", label: "Semua proses" }, ...(filters.processes || []).map((value) => ({ value, label: value }))], state.filters.process_key);
    setOptions(refs.ruleFilter, [{ value: "", label: "Semua rule" }, ...(filters.rules || []).map((value) => ({ value, label: value }))], state.filters.rule_id);
    setOptions(refs.severityFilter, [{ value: "", label: "Semua severity" }, ...(filters.severities || []).map((value) => ({ value, label: value }))], state.filters.severity);
    setOptions(refs.sortFilter, (filters.sorts || ["attention"]).map((value) => ({ value, label: value })), state.filters.sort);
    state.filters.presentation_category = refs.categoryFilter.value;
    state.filters.process_key = refs.processFilter.value;
    state.filters.rule_id = refs.ruleFilter.value;
    state.filters.severity = refs.severityFilter.value;
    state.filters.sort = refs.sortFilter.value || "attention";
  }
  function worklistUrl() {
    const url = new URL("/api/control-tower/temuan", window.location.origin);
    Object.entries(state.filters).forEach(([key, value]) => { if (value) url.searchParams.set(key, value); });
    url.searchParams.set("limit", state.limit);
    url.searchParams.set("offset", state.offset);
    return url;
  }
  function syncContextUrl() {
    const url = new URL(window.location.href);
    const queryValues = {
      presentation_category: state.filters.presentation_category,
      process_key: state.filters.process_key,
      rule_id: state.filters.rule_id,
      severity: state.filters.severity,
      sort: state.filters.sort === "attention" ? "" : state.filters.sort,
    };
    Object.entries(queryValues).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    });
    if (state.offset) url.searchParams.set("page", String(Math.floor(state.offset / state.limit) + 1));
    else url.searchParams.delete("page");
    if (state.selectedKey) url.searchParams.set("selected_finding", state.selectedKey);
    else url.searchParams.delete("selected_finding");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
  function renderInspector(row) {
    if (!row) {
      refs.inspectorState.textContent = "Pilih result untuk melihat evidence.";
      refs.inspectorBody.hidden = true;
      return;
    }
    refs.inspectorState.textContent = row.evidence_wording || "Review signal perlu dikonfirmasi oleh pemilik proses.";
    refs.inspectorBody.hidden = false;
    refs.inspectorPresentation.textContent = display(row.presentation_label);
    refs.inspectorProcess.textContent = display(row.process_label || row.process_key);
    refs.inspectorRule.textContent = display(row.original_rule_id || row.rule_id);
    refs.inspectorStatus.textContent = display(row.validation_status || row.current_status);
    refs.inspectorSeverity.textContent = display(row.severity);
    refs.inspectorConfidence.textContent = display(row.confidence);
    refs.inspectorDocument.textContent = display(row.affected_model) + " / " + display(row.document_number || row.document_id);
    refs.inspectorExplanation.textContent = row.evidence_wording || "Penjelasan belum tersedia.";
    refs.inspectorEvidence.textContent = ["Expected: " + formatEvidence(row.expected_condition), "Actual: " + formatEvidence(row.actual_condition), "Source: " + formatEvidence(row.evidence)].join("\n\n");
    refs.inspectorLimitation.textContent = (row.unsupported_destination_reason || "Destination exact belum tersedia.") + " Review signal bukan bukti otomatis bahwa user atau SOP salah.";
    refs.inspectorRaw.textContent = JSON.stringify(row, null, 2);
    const destination = destinationFor(row);
    refs.inspectorDestination.innerHTML = destination ? '<a href="' + escapeHtml(destination) + '">' + escapeHtml(row.destination_label || "Buka evidence") + "</a>" : escapeHtml(row.unsupported_destination_reason || "Destination exact belum tersedia.");
  }
  function renderRows(payload) {
    state.rows = Array.isArray(payload.rows) ? payload.rows : [];
    state.total = Number(payload.total || 0);
    refs.categorySummary.textContent = Object.entries(labels)
      .map(([key, label]) => label + ": " + Number((payload.category_counts || {})[key] || 0))
      .join(" · ");
    refs.findingList.innerHTML = state.rows.length ? state.rows.map((row, index) => {
      const key = rowKey(row);
      const destination = destinationFor(row);
      return '<article class="finding-card" data-key="' + escapeHtml(key) +
        '" data-selected="' + (key === state.selectedKey) + '">' +
        '<button class="finding-select" type="button" data-index="' + index +
        '" aria-pressed="' + (key === state.selectedKey) + '">' +
        '<span class="category">' + escapeHtml(row.presentation_label || "Tidak diklasifikasikan") + "</span>" +
        '<span class="finding-title">' + escapeHtml(row.title || row.document_number || "Temuan") + "</span>" +
        '<span class="finding-summary">' +
        escapeHtml(row.evidence_wording || "Sinyal review belum memiliki ringkasan.") + "</span>" +
        '<span class="finding-meta">Rule <strong>' + escapeHtml(display(row.rule_id)) +
        "</strong> · Status <strong>" + escapeHtml(display(row.validation_status)) +
        "</strong> · Severity <strong>" + escapeHtml(display(row.severity)) +
        "</strong> · Terdeteksi <strong>" + escapeHtml(formatDate(row.detected_at)) +
        "</strong></span></button>" +
        (destination
          ? '<a href="' + escapeHtml(destination) + '">' +
            escapeHtml(row.destination_label || "Buka dokumen") + "</a>"
          : '<span class="muted">' +
            escapeHtml(row.unsupported_destination_reason || "Destination exact belum tersedia.") + "</span>") +
        "</article>";
    }).join("") : '<div class="empty">Tidak ada Temuan pada snapshot trusted saat ini.</div>';
    if (!state.rows.length) {
      refs.worklistStatus.dataset.state = "empty";
      refs.worklistStatus.textContent = "Tidak ada temuan untuk filter saat ini.";
      renderInspector();
    } else {
      refs.worklistStatus.removeAttribute("data-state");
      refs.worklistStatus.textContent =
        "Menampilkan " + (state.offset + 1) + "–" + (state.offset + state.rows.length) +
        " dari " + state.total + " temuan.";
      refs.findingList.querySelectorAll(".finding-select").forEach((button) =>
        button.addEventListener("click", () => {
          const row = state.rows[Number(button.dataset.index)];
          state.selectedKey = row && rowKey(row);
          syncContextUrl();
          renderInspector(row);
          renderRows(payload);
        }));
      if (!state.rows.some((row) => rowKey(row) === state.selectedKey)) {
        state.selectedKey = null;
        syncContextUrl();
        renderInspector();
      }
    }
    refs.previousPage.disabled = state.offset === 0;
    refs.nextPage.disabled = state.offset + state.rows.length >= state.total;
    refs.paginationStatus.textContent = state.total
      ? "Halaman " + (Math.floor(state.offset / state.limit) + 1)
      : "Tidak ada data";
  }
  function renderError(error) {
    refs.worklistStatus.dataset.state = "error";
    refs.worklistStatus.textContent = "Temuan tidak dapat dimuat.";
    refs.findingList.innerHTML =
      '<div class="error">' + escapeHtml(error.message) +
      '<br><button class="button retry" type="button">Coba lagi</button></div>';
    refs.findingList.querySelector("button").addEventListener("click", loadWorklist);
    refs.previousPage.disabled = true;
    refs.nextPage.disabled = true;
    refs.paginationStatus.textContent = "-";
    renderInspector();
  }
  async function loadWorklist() {
    const requestId = ++state.requestId;
    refs.worklistStatus.removeAttribute("data-state");
    refs.worklistStatus.textContent = "Memuat Temuan...";
    refs.findingList.innerHTML = '<div class="loading">Memuat daftar Temuan...</div>';
    try {
      const payload = await fetchJson(worklistUrl());
      if (requestId !== state.requestId) return;
      if (!state.filtersReady) {
        renderFilters(payload.filters);
        state.filtersReady = true;
      }
      renderRows(payload);
    } catch (error) {
      if (requestId === state.requestId) renderError(error);
    }
  }
  function renderFreshness() {
    const health = state.health || {};
    const refresh = state.refresh || {};
    const freshness = health.freshness_classification || {};
    const attempt = health.latest_refresh_attempt_status;
    const status = refresh.active || (attempt === "RUNNING" && !refresh.stale_attempt)
      ? "REFRESHING"
      : refresh.candidate_pending || refresh.stale_attempt || ["FAILED", "ABORTED"].includes(attempt)
        ? "FAILED"
        : (freshness.state || health.status || "FAILED");
    const title = {
      CURRENT: "Snapshot trusted masih current",
      STALE: "Snapshot trusted mulai tertinggal",
      CRITICALLY_STALE: "Snapshot trusted sangat tertinggal",
      REFRESHING: "Refresh sedang berjalan",
      FAILED: "Refresh terakhir gagal",
      NO_COMPLETED_EXTRACTION: "Belum ada snapshot trusted yang selesai",
    }[status] || "Status data tidak tersedia";
    refs.freshnessBanner.dataset.state = status;
    refs.freshnessTitle.textContent = title;
    const trusted = health.latest_trusted_completed_at ? "Selesai " + formatDate(health.latest_trusted_completed_at) + "." : "Belum ada snapshot trusted yang selesai.";
    refs.freshnessDetails.textContent = status === "REFRESHING"
      ? trusted + " Snapshot trusted sebelumnya tetap ditampilkan."
      : status === "FAILED"
        ? trusted + " " + (health.latest_failure_message || (refresh.candidate_pending ? "Kandidat refresh menunggu publikasi atau recovery administrator." : "Periksa log administrator sebelum mencoba kembali."))
        : trusted;
    refs.refreshButton.hidden = !refresh.can_refresh || status === "REFRESHING";
  }
  async function loadHealth() {
    const results = await Promise.allSettled([
      fetchJson("/api/control-tower/health"),
      fetchJson("/api/control-tower/refresh"),
    ]);
    if (results[0].status === "fulfilled") {
      state.health = results[0].value;
    } else {
      refs.freshnessBanner.dataset.state = "FAILED";
      refs.freshnessTitle.textContent = "Status data tidak dapat dimuat";
      refs.freshnessDetails.textContent = results[0].reason.message;
      refs.refreshButton.hidden = true;
    }
    if (results[1].status === "fulfilled") state.refresh = results[1].value;
    if (results[0].status === "fulfilled") renderFreshness();
  }
  async function triggerRefresh() {
    refs.refreshButton.disabled = true;
    state.refresh = { ...(state.refresh || {}), active: true };
    renderFreshness();
    try {
      await fetchJson("/api/control-tower/refresh", { method: "POST" });
      window.setTimeout(() => { loadHealth(); loadWorklist(); }, 1500);
    } catch (error) {
      state.refresh = { ...(state.refresh || {}), active: false };
      refs.refreshButton.disabled = false;
      refs.freshnessBanner.dataset.state = "FAILED";
      refs.freshnessTitle.textContent = "Refresh tidak dapat dimulai";
      refs.freshnessDetails.textContent = error.message;
      refs.refreshButton.hidden = false;
    }
  }
  const filterRefs = {
    presentation_category: refs.categoryFilter,
    process_key: refs.processFilter,
    rule_id: refs.ruleFilter,
    severity: refs.severityFilter,
    sort: refs.sortFilter,
  };
  Object.entries(filterRefs).forEach(([key, select]) => select.addEventListener("change", () => {
    state.filters[key] = select.value;
    state.offset = 0;
    state.selectedKey = null;
    syncContextUrl();
    loadWorklist();
  }));
  refs.clearFilters.addEventListener("click", () => {
    Object.keys(filterRefs).forEach((key) => {
      state.filters[key] = key === "sort" ? "attention" : "";
      filterRefs[key].value = state.filters[key];
    });
    state.offset = 0;
    state.selectedKey = null;
    syncContextUrl();
    loadWorklist();
  });
  refs.previousPage.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    state.selectedKey = null;
    syncContextUrl();
    loadWorklist();
  });
  refs.nextPage.addEventListener("click", () => {
    if (state.offset + state.limit < state.total) {
      state.offset += state.limit;
      state.selectedKey = null;
      syncContextUrl();
      loadWorklist();
    }
  });
  refs.refreshButton.addEventListener("click", triggerRefresh);
  const params = new URLSearchParams(window.location.search);
  const requestedReturn = safeDestination(params.get("return_to"));
  if (requestedReturn && requestedReturn.startsWith("/dashboard/control-tower")) returnTo = requestedReturn;
  refs.backLink.href = returnTo;
  state.filters.presentation_category = params.get("presentation_category") || params.get("category") || "";
  state.filters.process_key = params.get("process_key") || params.get("process") || "";
  state.filters.rule_id = params.get("rule_id") || params.get("rule") || "";
  state.filters.severity = params.get("severity") || "";
  state.filters.sort = params.get("sort") || "attention";
  const requestedPage = Number(params.get("page"));
  if (Number.isInteger(requestedPage) && requestedPage > 1) state.offset = (requestedPage - 1) * state.limit;
  state.selectedKey = params.get("selected_finding") || null;
  function armIdleReset() {
    window.clearTimeout(idleResetTimer);
    if (window.controlTowerOfficeMode !== true) return;
    idleResetTimer = window.setTimeout(() => window.location.assign("/dashboard/control-tower?view=overview"), 120000);
  }
  ["pointerdown", "keydown", "scroll", "touchstart"].forEach((eventName) => window.addEventListener(eventName, armIdleReset, { passive: true }));
  armIdleReset();
  loadHealth();
  loadWorklist();
})();
