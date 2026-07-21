(function runControlTower() {
  "use strict";

  const A = window.ControlTowerAdapter;
  const viewContainer = document.getElementById("viewContainer");
  const pageState = document.getElementById("pageState");
  const systemMessage = document.getElementById("systemMessage");
  const refreshButton = document.getElementById("refreshButton");
  const autoRefreshSelect = document.getElementById("autoRefreshSelect");
  const themeButton = document.getElementById("themeButton");
  const displayButton = document.getElementById("displayButton");
  const motionButton = document.getElementById("motionButton");
  const snapshotTime = document.getElementById("snapshotTime");
  const screenRefreshTime = document.getElementById("screenRefreshTime");
  const toastRegion = document.getElementById("toastRegion");
  const mapTooltip = document.getElementById("mapTooltip");
  const allowedViews = new Set(["overview", "validation", "exceptions", "journey"]);
  const allowedClassifications = new Set(["active", "historical", "review", "incomplete", "document-gap"]);
  const AUTO_REFRESH_VALUES = new Set(["off", "5", "15", "30"]);
  const AUTO_REFRESH_KEY = "control-tower-auto-refresh";
  const THEME_KEY = "control-tower-theme";
  const MOTION_KEY = "control-tower-motion-paused";
  const JOURNEY_PAGE_SIZE = 50;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let activeLoad = null;
  let queuedLoad = false;
  let autoTimer = null;
  let autoDueAt = null;
  let sessionExpired = false;
  let blockingError = false;
  let lastSelectedProcess = "sales-order";
  let overviewCache = null;
  let displayMode = false;
  let motionPaused = reducedMotion.matches || localStorage.getItem(MOTION_KEY) === "true";
  let activeDrawerTrigger = null;

  function routeState() {
    const params = new URLSearchParams(window.location.search);
    const requestedView = params.get("view") || "overview";
    return {
      params,
      view: allowedViews.has(requestedView) ? requestedView : "overview",
      process: params.get("process") || "",
      rule: params.get("rule") || "",
      classification: allowedClassifications.has(params.get("classification")) ? params.get("classification") : "active",
      owner: params.get("owner") || params.get("reviewer") || "",
      severity: params.get("severity") || "",
      document: params.get("document") || "",
      date_from: params.get("date_from") || "",
      date_to: params.get("date_to") || "",
      offset: Math.max(0, Number(params.get("offset")) || 0),
      model: params.get("model") || "",
      id: params.get("id") || "",
      journeyPage: Math.max(1, Number(params.get("journey_page")) || 1),
    };
  }

  function routeHref(view, values = {}) {
    const params = new URLSearchParams({ view });
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== null && value !== "" && value !== 0) params.set(key, String(value));
    }
    return `/control-tower?${params.toString()}`;
  }

  function updateNavigation(view) {
    document.querySelectorAll("[data-view-link]").forEach((link) => {
      if (link.dataset.viewLink === view) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function statusBadge(status) {
    return `<span class="status-badge tone-${A.escapeHtml(status.tone)}">${A.escapeHtml(status.label)}</span>`;
  }

  function technicalReference(rawStatus, ruleIds) {
    const rules = Array.isArray(ruleIds) ? ruleIds.filter(Boolean).join(", ") : ruleIds;
    const parts = [];
    if (rules) parts.push(`Rule: ${rules}`);
    if (rawStatus) parts.push(`Status teknis: ${rawStatus}`);
    return A.escapeHtml(parts.join(" · "));
  }

  function viewHeading(title, description, meta = "") {
    return `
      <header class="view-heading">
        <div><h1>${A.escapeHtml(title)}</h1><p>${A.escapeHtml(description)}</p></div>
        ${meta ? `<span class="view-meta">${A.escapeHtml(meta)}</span>` : ""}
      </header>`;
  }

  function showSystemMessage(message, tone = "info", action = "") {
    systemMessage.hidden = false;
    systemMessage.className = `system-message tone-${tone}`;
    systemMessage.innerHTML = `<span>${A.escapeHtml(message)}</span>${action}`;
  }

  function hideSystemMessage() {
    systemMessage.hidden = true;
    systemMessage.innerHTML = "";
  }

  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.textContent = message;
    toastRegion.replaceChildren(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function setLoading(source) {
    viewContainer.setAttribute("aria-busy", "true");
    refreshButton.disabled = true;
    refreshButton.classList.add("is-loading");
    refreshButton.setAttribute("aria-busy", "true");
    if (!viewContainer.dataset.ready) {
      pageState.innerHTML = `
        <section class="state-panel tone-info" role="status">
          <h2>Memuat Control Tower</h2>
          <p>Membaca snapshot PostgreSQL terbaru yang sudah tersedia.</p>
        </section>`;
    } else if (source === "manual") {
      showSystemMessage("Memuat ulang data Control Tower tanpa menjalankan sinkronisasi Odoo.", "info");
    }
  }

  function finishLoading() {
    viewContainer.setAttribute("aria-busy", "false");
    refreshButton.disabled = false;
    refreshButton.classList.remove("is-loading");
    refreshButton.removeAttribute("aria-busy");
  }

  function updateRefreshTimes(health) {
    snapshotTime.textContent = A.formatDateTime(health?.latest_run?.completed_at);
    screenRefreshTime.textContent = A.formatDateTime(new Date().toISOString());
  }

  function showFreshnessWarning(health) {
    const freshness = A.freshnessState(health);
    if (freshness.state === "fresh") {
      hideSystemMessage();
      return;
    }
    showSystemMessage(`${freshness.label}. ${freshness.detail}`, freshness.tone);
  }

  function errorPanel(error, state) {
    if (error.httpStatus === 401) {
      const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
      return `
        <section class="state-panel tone-warning" role="alert">
          <h2>Sesi Control Tower sudah berakhir</h2>
          <p>Auto-refresh dihentikan. Masuk kembali untuk melanjutkan dari halaman dan filter yang sama.</p>
          <div class="state-actions"><a class="primary-button" href="/login?next=${next}">Masuk kembali</a></div>
        </section>`;
    }
    if (error.httpStatus === 404 && state.view === "journey") {
      return `
        <section class="state-panel tone-warning" role="alert">
          <h2>Dokumen tidak ditemukan</h2>
          <p>Dokumen tidak tersedia pada snapshot terbaru. Model dan native ID tetap dipertahankan pada URL.</p>
          <div class="state-actions"><button class="secondary-button" type="button" data-retry>Muat ulang</button></div>
        </section>`;
    }
    return `
      <section class="state-panel tone-danger" role="alert">
        <h2>Data belum dapat dimuat</h2>
        <p>Detail teknis sensitif tidak ditampilkan. Coba lagi saat layanan PostgreSQL tersedia.</p>
        <div class="state-actions"><button class="secondary-button" type="button" data-retry>Coba lagi</button></div>
      </section>`;
  }

  async function apiJson(url) {
    if (!url.startsWith("/api/control-tower/")) throw new Error("Unsupported Control Tower endpoint");
    const started = performance.now();
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
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

  function commitView(html, health, bind) {
    pageState.innerHTML = "";
    viewContainer.innerHTML = html;
    viewContainer.dataset.ready = "true";
    updateNavigation(routeState().view);
    updateRefreshTimes(health);
    showFreshnessWarning(health);
    bind?.();
  }

  async function performLoad(state, source) {
    const started = performance.now();
    setLoading(source);
    try {
      const renderer = {
        overview: renderOverview,
        validation: renderValidation,
        exceptions: renderExceptions,
        journey: renderJourney,
      }[state.view] || renderOverview;
      await renderer(state);
      sessionExpired = false;
      blockingError = false;
      if (source === "manual") showToast("Data Control Tower berhasil diperbarui.");
      performance.measure(`control-tower-${state.view}-load`, { start: started, end: performance.now() });
    } catch (error) {
      if (error.httpStatus === 401) {
        sessionExpired = true;
        clearAutoTimer();
      }
      if (viewContainer.dataset.ready) {
        showSystemMessage(
          error.httpStatus === 401
            ? "Sesi berakhir. Auto-refresh dihentikan; masuk kembali untuk melanjutkan."
            : "Data terbaru belum dapat dimuat. Informasi di layar berasal dari pembaruan sebelumnya.",
          error.httpStatus === 401 ? "warning" : "danger",
          error.httpStatus === 401
            ? `<a class="primary-button" href="/login?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}">Masuk kembali</a>`
            : "",
        );
      } else {
        blockingError = true;
        pageState.innerHTML = errorPanel(error, state);
        pageState.querySelector("[data-retry]")?.addEventListener("click", () => requestLoad("manual"));
      }
    } finally {
      finishLoading();
      scheduleAutoRefresh();
    }
  }

  function requestLoad(source = "navigation") {
    if (activeLoad) {
      if (source === "navigation" || source === "popstate") queuedLoad = true;
      else if (source === "manual") showToast("Pembaruan data sedang berjalan.");
      return activeLoad;
    }
    const state = routeState();
    activeLoad = performLoad(state, source).finally(() => {
      activeLoad = null;
      if (queuedLoad) {
        queuedLoad = false;
        requestLoad("navigation");
      }
    });
    return activeLoad;
  }

  function classificationForRule(rule) {
    if (rule.activeIssues > 0) return "active";
    if (rule.reviewRequired > 0) return "review";
    if (rule.incompleteEvidence > 0) return "incomplete";
    if (rule.historicalCount > 0) return "historical";
    return "active";
  }

  function processPoint(id) {
    const process = A.PROCESS_DEFINITIONS.find((item) => item.id === id);
    return { x: process.x * 10, y: process.y * 6.5 };
  }

  function processEdges() {
    return A.PROCESS_RELATIONSHIPS.map(([from, to, kind]) => {
      const start = processPoint(from);
      const end = processPoint(to);
      const vertical = Math.abs(end.y - start.y) > Math.abs(end.x - start.x);
      const distance = vertical ? Math.max(42, Math.abs(end.y - start.y) * 0.38) : Math.max(48, Math.abs(end.x - start.x) * 0.42);
      const path = vertical
        ? `M ${start.x} ${start.y} C ${start.x} ${start.y + distance}, ${end.x} ${end.y - distance}, ${end.x} ${end.y}`
        : `M ${start.x} ${start.y} C ${start.x + distance} ${start.y}, ${end.x - distance} ${end.y}, ${end.x} ${end.y}`;
      return `<path class="map-edge map-edge--${kind}" d="${path}" data-from="${from}" data-to="${to}"></path>`;
    }).join("");
  }

  function processNodes(nodes, selectedId) {
    return nodes.map((node) => `
      <button
        class="process-node${node.id === selectedId ? " is-selected" : ""}"
        type="button"
        data-process-id="${A.escapeHtml(node.id)}"
        style="left:${node.x}%;top:${node.y}%"
        aria-pressed="${node.id === selectedId}"
        aria-label="${A.escapeHtml(`${node.label}: ${node.headline}`)}"
      >
        <span class="node-name">${A.escapeHtml(node.label)}</span>
        <span class="node-status tone-${A.escapeHtml(node.status.tone)}"><span>${A.escapeHtml(node.status.label)}</span><strong>${node.totals.active || node.totals.review || node.totals.incomplete || node.totals.historical ? A.formatNumber(node.totals.active || node.totals.review || node.totals.incomplete || node.totals.historical) : "—"}</strong></span>
      </button>`).join("");
  }

  function priorityMarkup(items, selectedId) {
    if (!items.length) return `<p class="attention-summary">Belum ada prioritas aktif pada snapshot ini.</p>`;
    return items.map((item) => `
      <button class="priority-item tone-${A.escapeHtml(item.status.tone)}${item.processId === selectedId ? " is-selected" : ""}" type="button" data-priority-process="${A.escapeHtml(item.processId)}">
        <span class="priority-rail" aria-hidden="true"></span>
        <span class="priority-copy"><strong>${A.escapeHtml(item.title)}</strong><span>${A.escapeHtml(item.process)} · ${A.escapeHtml(item.reviewer)} · ${A.escapeHtml(item.status.label)}</span></span>
        <span class="priority-count">${A.formatNumber(item.count)}</span>
      </button>`).join("");
  }

  function inspectorMarkup(node, snapshot) {
    const rule = node.primaryRule;
    const explanation = rule?.explanation || "Agregat tepercaya untuk proses ini belum tersedia pada kontrak backend saat ini.";
    const why = rule?.why || "Proses tetap ditampilkan agar hubungan bisnis dapat dipahami tanpa menyimpulkan kondisi yang belum didukung bukti.";
    const impact = rule?.impact || "Memerlukan bukti tambahan sebelum kondisi operasional dapat dinilai.";
    const reviewer = rule?.owner || rule?.reviewer || node.reviewer;
    const evidence = rule?.evidenceStrength || (node.specialStatus === "MANUAL_EVIDENCE_REQUIRED" ? "Bukti manual" : "Belum tersedia");
    const ruleIds = node.rules.length ? node.rules.map((item) => item.ruleId) : node.ruleIds;
    const classification = node.totals.active ? "active" : node.totals.review ? "review" : node.totals.incomplete ? "incomplete" : node.totals.historical ? "historical" : "active";
    const primaryRuleId = rule?.ruleId || node.ruleIds[0] || "";
    return `
      <div class="panel-scroll">
        <div class="panel-title-row">
          <div><span class="eyebrow">Proses terpilih</span></div>
          <button class="icon-button drawer-close" type="button" data-close-drawer aria-label="Tutup inspector">Tutup</button>
        </div>
        <section class="inspector-summary">
          <h2>${A.escapeHtml(node.label)}</h2>
          <p>${A.escapeHtml(node.headline)}</p>
          <div class="inline-actions">${statusBadge(node.status)}</div>
        </section>
        <section class="condition-card"><strong>Kondisi bisnis saat ini</strong><span>${A.escapeHtml(explanation)}</span></section>
        <section class="inspector-section"><h3>Mengapa penting</h3><p>${A.escapeHtml(why)}</p></section>
        <section class="inspector-section"><h3>Dampak operasional yang mungkin</h3><p>${A.escapeHtml(impact)}</p></section>
        <section class="inspector-section">
          <h3>Bukti dan penanggung jawab</h3>
          <div class="detail-grid">
            <div class="detail-item"><span>Pemilik proses</span><strong>${A.escapeHtml(node.owner)}</strong></div>
            <div class="detail-item"><span>Peninjau</span><strong>${A.escapeHtml(reviewer)}</strong></div>
            <div class="detail-item"><span>Pemeriksaan</span><strong>${node.rules.length ? A.formatNumber(node.totals.checked) : "Belum tersedia"}</strong></div>
            <div class="detail-item"><span>Kekuatan bukti</span><strong>${A.escapeHtml(evidence)}</strong></div>
            <div class="detail-item"><span>Masalah aktif</span><strong>${A.formatNumber(node.totals.active)}</strong></div>
            <div class="detail-item"><span>Perlu ditinjau</span><strong>${A.formatNumber(node.totals.review)}</strong></div>
            <div class="detail-item"><span>Bukti belum lengkap</span><strong>${A.formatNumber(node.totals.incomplete)}</strong></div>
            <div class="detail-item"><span>Catatan historis</span><strong>${A.formatNumber(node.totals.historical)}</strong></div>
            <div class="detail-item"><span>Snapshot</span><strong>${A.escapeHtml(A.formatDateTime(snapshot))}</strong></div>
          </div>
        </section>
        <div class="technical-reference">${technicalReference(node.status.raw, ruleIds)}</div>
        <div class="inspector-actions">
          <a class="secondary-button" data-route-link href="${routeHref("validation", { process: node.id })}">Lihat Pemeriksaan SOP</a>
          ${primaryRuleId ? `<a class="primary-button" data-route-link href="${routeHref("exceptions", { classification, rule: primaryRuleId })}">Lihat Pengecualian</a>` : ""}
        </div>
      </div>`;
  }

  function overviewMarkup(data, selectedId) {
    const selectedNode = data.map.nodes.find((node) => node.id === selectedId) || data.map.nodes.find((node) => node.id === "sales-order");
    const freshness = A.freshnessState(data.health);
    const metrics = data.metrics;
    return `
      <div class="overview-grid">
        <aside class="panel attention-panel" id="attentionPanel" aria-label="Perhatian dan prioritas">
          <div class="panel-scroll">
            <div class="panel-title-row">
              <div><span class="eyebrow">Perhatian saat ini</span><h2>Prioritas</h2></div>
              <button class="icon-button drawer-close" type="button" data-close-drawer aria-label="Tutup panel prioritas">Tutup</button>
            </div>
            <section class="freshness-card tone-${A.escapeHtml(freshness.tone)}">
              <strong>${A.escapeHtml(freshness.label)}</strong>
              <span>${A.escapeHtml(freshness.detail)}</span>
            </section>
            <div class="metric-strip" aria-label="Hitungan operasional ringkas">
              <div class="metric-item"><span>Pemeriksaan</span><strong>${A.formatNumber(metrics.checksPerformed)}</strong></div>
              <div class="metric-item"><span>Masalah Aktif</span><strong>${A.formatNumber(metrics.active)}</strong></div>
              <div class="metric-item"><span>Perlu Ditinjau</span><strong>${A.formatNumber(metrics.review)}</strong></div>
              <div class="metric-item"><span>Bukti Belum Lengkap</span><strong>${A.formatNumber(metrics.incomplete)}</strong></div>
              <div class="metric-item"><span>Catatan Historis</span><strong>${A.formatNumber(metrics.historical)}</strong></div>
            </div>
            <p class="attention-summary">Masalah aktif diprioritaskan lebih dahulu; catatan historis tetap terlihat sebagai konteks audit.</p>
            <section class="priority-section" aria-labelledby="priorityTitle">
              <span class="eyebrow" id="priorityTitle">Priority feed</span>
              <div class="priority-list">${priorityMarkup(data.priorities, selectedNode.id)}</div>
            </section>
          </div>
        </aside>

        <section class="panel process-stage" aria-labelledby="processMapTitle">
          <header class="process-map-header">
            <div><span class="eyebrow">Hubungan proses bisnis</span><h1 id="processMapTitle">Peta Proses</h1><p>Peta menunjukkan hubungan proses dan dokumen, bukan selalu urutan waktu.</p></div>
            <div class="map-header-actions">
              <button class="icon-button mobile-panel-trigger" type="button" data-panel="attention" aria-controls="attentionPanel" aria-expanded="false">Prioritas</button>
              <button class="icon-button mobile-panel-trigger" type="button" data-panel="inspector" aria-controls="inspectorPanel" aria-expanded="false">Inspector</button>
              <div class="map-legend" aria-label="Legenda hubungan">
                <span><i class="legend-line"></i>Utama</span>
                <span><i class="legend-line legend-line--support"></i>Pendukung</span>
                <span><i class="legend-line legend-line--manual"></i>Manual / belum terbit</span>
              </div>
            </div>
          </header>
          <div class="map-canvas" id="processMap">
            <svg viewBox="0 0 1000 650" preserveAspectRatio="none" aria-hidden="true">${processEdges()}</svg>
            <div>${processNodes(data.map.nodes, selectedNode.id)}</div>
            <div class="map-toolbar" aria-label="Kontrol peta proses">
              <button class="icon-button" id="mapMotionButton" type="button">${motionPaused ? "Lanjut" : "Jeda"}</button>
              <button class="icon-button" id="mapResetButton" type="button">Reset</button>
              <button class="icon-button" id="mapFocusButton" type="button">Fokus</button>
            </div>
            <span class="relationship-note">Nilai yang belum didukung agregat backend ditampilkan sebagai “Belum tersedia”.</span>
          </div>
        </section>

        <aside class="panel inspector-panel" id="inspectorPanel" aria-label="Inspector proses">
          ${inspectorMarkup(selectedNode, data.health.latest_run?.completed_at)}
        </aside>
      </div>
      <button class="drawer-backdrop" type="button" data-close-drawer aria-label="Tutup panel"></button>`;
  }

  function closeDrawers(returnFocus = true) {
    document.querySelectorAll(".attention-panel.is-open,.inspector-panel.is-open,.drawer-backdrop.is-open").forEach((item) => item.classList.remove("is-open"));
    document.querySelectorAll("[data-panel]").forEach((button) => button.setAttribute("aria-expanded", "false"));
    document.querySelector(".process-stage")?.removeAttribute("inert");
    document.querySelector(".topbar")?.removeAttribute("inert");
    document.querySelectorAll(".attention-panel,.inspector-panel").forEach((panel) => panel.removeAttribute("inert"));
    if (returnFocus) activeDrawerTrigger?.focus();
    activeDrawerTrigger = null;
  }

  function openDrawer(button) {
    closeDrawers(false);
    const panel = document.getElementById(`${button.dataset.panel}Panel`);
    if (!panel) return;
    activeDrawerTrigger = button;
    button.setAttribute("aria-expanded", "true");
    panel.classList.add("is-open");
    document.querySelector(".drawer-backdrop")?.classList.add("is-open");
    document.querySelector(".process-stage")?.setAttribute("inert", "");
    document.querySelector(".topbar")?.setAttribute("inert", "");
    document.querySelectorAll(".attention-panel,.inspector-panel").forEach((item) => {
      if (item !== panel) item.setAttribute("inert", "");
    });
    panel.querySelector("[data-close-drawer]")?.focus();
  }

  function trapDrawerFocus(event) {
    if (event.key !== "Tab") return;
    const panel = document.querySelector(".attention-panel.is-open,.inspector-panel.is-open");
    if (!panel) return;
    const focusable = [...panel.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function selectOverviewProcess(processId, push = true) {
    if (!overviewCache || !overviewCache.map.nodes.some((node) => node.id === processId)) return;
    lastSelectedProcess = processId;
    const url = new URL(window.location.href);
    url.searchParams.set("view", "overview");
    url.searchParams.set("process", processId);
    window.history[push ? "pushState" : "replaceState"](null, "", url);
    viewContainer.innerHTML = overviewMarkup(overviewCache, processId);
    bindOverview(processId);
  }

  function bindOverview(selectedId) {
    document.querySelectorAll("[data-process-id]").forEach((node) => {
      const process = overviewCache.map.nodes.find((item) => item.id === node.dataset.processId);
      node.addEventListener("click", () => selectOverviewProcess(node.dataset.processId));
      node.addEventListener("mouseenter", (event) => showMapTooltip(event, process));
      node.addEventListener("mousemove", moveMapTooltip);
      node.addEventListener("mouseleave", hideMapTooltip);
      node.addEventListener("focus", (event) => showMapTooltip(event, process));
      node.addEventListener("blur", hideMapTooltip);
    });
    document.querySelectorAll("[data-priority-process]").forEach((item) => item.addEventListener("click", () => selectOverviewProcess(item.dataset.priorityProcess)));
    document.querySelectorAll("[data-panel]").forEach((button) => button.addEventListener("click", () => openDrawer(button)));
    document.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", closeDrawers));
    document.getElementById("mapMotionButton")?.addEventListener("click", toggleMotion);
    document.getElementById("mapResetButton")?.addEventListener("click", () => selectOverviewProcess("sales-order"));
    document.getElementById("mapFocusButton")?.addEventListener("click", () => {
      const node = document.querySelector(`[data-process-id="${CSS.escape(selectedId)}"]`);
      node?.scrollIntoView({ block: "center", inline: "center", behavior: reducedMotion.matches ? "auto" : "smooth" });
      node?.classList.add("is-focused");
      window.setTimeout(() => node?.classList.remove("is-focused"), 560);
    });
    applyMotionState();
  }

  function showMapTooltip(event, process) {
    if (!process) return;
    mapTooltip.innerHTML = `<strong>${A.escapeHtml(process.label)}</strong><span>${A.escapeHtml(process.headline)}<br>Pemilik: ${A.escapeHtml(process.owner)}</span>`;
    mapTooltip.hidden = false;
    moveMapTooltip(event);
  }

  function moveMapTooltip(event) {
    const x = Math.min(window.innerWidth - 275, Math.max(8, (event.clientX || event.target.getBoundingClientRect().right) + 12));
    const y = Math.min(window.innerHeight - 110, Math.max(8, (event.clientY || event.target.getBoundingClientRect().top) + 12));
    mapTooltip.style.left = `${x}px`;
    mapTooltip.style.top = `${y}px`;
  }

  function hideMapTooltip() {
    mapTooltip.hidden = true;
  }

  async function renderOverview(state) {
    const [health, validation, poScope, ioHealth] = await Promise.all([
      apiJson("/api/control-tower/health"),
      apiJson("/api/control-tower/sop-validation"),
      apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
      apiJson("/api/control-tower/io-health?limit=1&offset=0"),
    ]);
    const context = { completedAt: health.latest_run?.completed_at, po: A.poScopeSummary(poScope.summary) };
    const map = A.normalizeProcessMap(validation.rows, context);
    const metrics = A.overviewMetrics(health, validation.rows, poScope.summary, ioHealth.summary);
    overviewCache = { health, map, metrics, priorities: A.priorityFeed(map.rules, 6), ioHealth };
    const selected = map.nodes.some((node) => node.id === state.process) ? state.process : lastSelectedProcess;
    lastSelectedProcess = map.nodes.some((node) => node.id === selected) ? selected : "sales-order";
    commitView(overviewMarkup(overviewCache, lastSelectedProcess), health, () => bindOverview(lastSelectedProcess));
  }

  function validationRow(rule) {
    const classification = classificationForRule(rule);
    return `
      <tr>
        <td class="validation-title"><strong>${A.escapeHtml(rule.title)}</strong>${rule.currentSummary ? `<span>${A.escapeHtml(rule.currentSummary)}</span>` : ""}<span>${technicalReference(rule.rawStatus, rule.ruleId)}</span></td>
        <td>${statusBadge(rule.status)}</td>
        <td class="business-explanation"><strong>${A.escapeHtml(rule.explanation)}</strong><span><b>Mengapa penting:</b> ${A.escapeHtml(rule.why)}</span><span><b>Dampak:</b> ${A.escapeHtml(rule.impact)}</span></td>
        <td>${A.escapeHtml(rule.process)}</td>
        <td>${A.escapeHtml(rule.processOwner)}</td>
        <td>${A.escapeHtml(rule.reviewer)}</td>
        <td class="num">${A.formatNumber(rule.checkedCount)}</td>
        <td class="num">${A.formatNumber(rule.compliantCount)}</td>
        <td class="num">${A.formatNumber(rule.activeIssues)}</td>
        <td class="num">${A.formatNumber(rule.historicalCount)}</td>
        <td class="num">${A.formatNumber(rule.reviewRequired)}</td>
        <td class="num">${A.formatNumber(rule.incompleteEvidence)}</td>
        <td>${A.escapeHtml(rule.evidenceStrength)}<span class="cell-note">Evaluasi: ${A.escapeHtml(A.formatDateTime(rule.latestEvaluation))}</span></td>
        <td><a class="table-link" data-route-link href="${routeHref("exceptions", { classification, rule: rule.ruleId })}">Lihat pengecualian</a></td>
      </tr>`;
  }

  function bindValidation(state) {
    document.getElementById("validationFilters")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const process = document.getElementById("validationProcessFilter").value;
      const rule = document.getElementById("validationRuleFilter").value;
      navigate(routeHref("validation", { process, rule }));
    });
    document.getElementById("clearValidationFilters")?.addEventListener("click", () => navigate(routeHref("validation")));
  }

  async function renderValidation(state) {
    const [health, validation, poScope] = await Promise.all([
      apiJson("/api/control-tower/health"),
      apiJson("/api/control-tower/sop-validation"),
      apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
    ]);
    const context = { completedAt: health.latest_run?.completed_at, po: A.poScopeSummary(poScope.summary) };
    const allRules = (validation.rows || []).map((row) => A.normalizeRule(row, context));
    const process = A.PROCESS_DEFINITIONS.find((item) => item.id === state.process);
    const rules = allRules.filter((rule) => (!process || process.ruleIds.includes(rule.ruleId)) && (!state.rule || state.rule === rule.ruleId));
    const totals = rules.reduce((result, rule) => {
      result.checked += rule.checkedCount;
      result.active += rule.activeIssues;
      result.review += rule.reviewRequired;
      result.incomplete += rule.incompleteEvidence;
      return result;
    }, { checked: 0, active: 0, review: 0, incomplete: 0 });
    const processOptions = A.PROCESS_DEFINITIONS.filter((item) => item.ruleIds.length).map((item) => `<option value="${A.escapeHtml(item.id)}"${state.process === item.id ? " selected" : ""}>${A.escapeHtml(item.label)}</option>`).join("");
    const ruleOptions = allRules.map((rule) => `<option value="${A.escapeHtml(rule.ruleId)}"${state.rule === rule.ruleId ? " selected" : ""}>${A.escapeHtml(rule.ruleId)} — ${A.escapeHtml(rule.title)}</option>`).join("");
    const html = `
      ${viewHeading("Validasi SOP", "Pemeriksaan bisnis terhubung langsung dengan proses, pengecualian, dan bukti snapshot.", `${A.formatNumber(rules.length)} dari ${A.formatNumber(allRules.length)} pemeriksaan`)}
      ${process ? `<section class="context-banner"><span>Filter proses aktif: <strong>${A.escapeHtml(process.label)}</strong></span><a class="secondary-button" data-route-link href="${routeHref("overview", { process: process.id })}">Kembali ke peta</a></section>` : ""}
      <form class="filter-panel" id="validationFilters">
        <label><span>Proses</span><select id="validationProcessFilter"><option value="">Semua proses</option>${processOptions}</select></label>
        <label class="classification-control"><span>Rule teknis</span><select id="validationRuleFilter"><option value="">Semua rule</option>${ruleOptions}</select></label>
        <div class="filter-actions"><button class="primary-button" type="submit">Terapkan</button><button class="secondary-button" id="clearValidationFilters" type="button">Hapus</button></div>
      </form>
      <section class="summary-strip" aria-label="Ringkasan validasi terpilih">
        <article class="detail-item"><span>Diperiksa</span><strong>${A.formatNumber(totals.checked)}</strong></article>
        <article class="detail-item"><span>Masalah Aktif</span><strong>${A.formatNumber(totals.active)}</strong></article>
        <article class="detail-item"><span>Perlu Ditinjau</span><strong>${A.formatNumber(totals.review)}</strong></article>
        <article class="detail-item"><span>Bukti Belum Lengkap</span><strong>${A.formatNumber(totals.incomplete)}</strong></article>
      </section>
      <section class="table-panel" aria-label="Matriks Validasi SOP">
        <div class="table-toolbar"><div><strong>Matriks Validasi SOP</strong><span>Bahasa bisnis utama; referensi teknis ditampilkan setelahnya.</span></div></div>
        <div class="table-scroll" tabindex="0" aria-label="Tabel Validasi SOP dapat digulir secara horizontal">
          <table class="validation-table"><thead><tr><th>Kontrol bisnis</th><th>Status</th><th>Penjelasan, alasan, dampak</th><th>Proses</th><th>Pemilik</th><th>Peninjau</th><th class="num">Diperiksa</th><th class="num">Sesuai</th><th class="num">Aktif</th><th class="num">Historis</th><th class="num">Ditinjau</th><th class="num">Bukti belum lengkap</th><th>Bukti &amp; evaluasi</th><th>Tindakan</th></tr></thead><tbody>${rules.length ? rules.map(validationRow).join("") : `<tr><td colspan="14" class="empty-cell">Tidak ada pemeriksaan untuk filter yang dipilih.</td></tr>`}</tbody></table>
        </div>
      </section>`;
    commitView(html, health, () => bindValidation(state));
  }

  function classificationOptions(selected) {
    return [
      ["active", "Masalah Aktif"],
      ["historical", "Catatan Historis"],
      ["review", "Perlu Ditinjau"],
      ["incomplete", "Bukti Sistem Belum Lengkap"],
      ["document-gap", "Hubungan Dokumen Belum Lengkap"],
    ].map(([value, label]) => `<option value="${value}"${selected === value ? " selected" : ""}>${label}</option>`).join("");
  }

  function selectOptions(options, selected, emptyLabel) {
    return `<option value="">${A.escapeHtml(emptyLabel)}</option>` + options.map(([value, label]) => `<option value="${A.escapeHtml(value)}"${selected === value ? " selected" : ""}>${A.escapeHtml(label)}</option>`).join("");
  }

  function filtersMarkup(state) {
    const historical = state.classification === "historical";
    const disabled = historical ? " disabled" : "";
    return `
      <form class="filter-panel" id="worklistFilters">
        <label class="classification-control"><span>Klasifikasi</span><select id="classificationFilter">${classificationOptions(state.classification)}</select></label>
        <label><span>Proses</span><select id="processFilter"${disabled}>${selectOptions(A.PROCESS_FILTERS, state.process, "Semua proses")}</select></label>
        <label><span>Peninjau</span><select id="ownerFilter"${disabled}>${selectOptions(A.OWNER_FILTERS.map((owner) => [owner, owner]), state.owner, "Semua tim")}</select></label>
        <label><span>Tingkat dampak</span><select id="severityFilter"${disabled}><option value="">Semua tingkat</option><option value="HIGH"${state.severity === "HIGH" ? " selected" : ""}>Tinggi</option><option value="MEDIUM"${state.severity === "MEDIUM" ? " selected" : ""}>Sedang</option><option value="LOW"${state.severity === "LOW" ? " selected" : ""}>Rendah</option></select></label>
        <label><span>Dokumen</span><input id="documentFilter" type="search" maxlength="100" value="${A.escapeHtml(state.document)}" placeholder="Nomor dokumen"${disabled}></label>
        <label><span>Tanggal dari</span><input id="dateFromFilter" type="date" value="${A.escapeHtml(state.date_from)}"${disabled}></label>
        <label><span>Tanggal sampai</span><input id="dateToFilter" type="date" value="${A.escapeHtml(state.date_to)}"${disabled}></label>
        <div class="filter-actions"><button class="primary-button" type="submit">Terapkan</button><button class="secondary-button" id="clearWorklistFilters" type="button">Hapus</button></div>
      </form>`;
  }

  function selectedFiltersMarkup(state) {
    const labels = { active: "Masalah Aktif", historical: "Catatan Historis", review: "Perlu Ditinjau", incomplete: "Bukti Sistem Belum Lengkap", "document-gap": "Hubungan Dokumen Belum Lengkap" };
    const tokens = [`Klasifikasi: ${labels[state.classification]}`];
    if (state.rule) tokens.push(`Rule: ${state.rule}`);
    if (state.process) tokens.push(`Proses: ${state.process}`);
    if (state.owner) tokens.push(`Peninjau: ${state.owner}`);
    if (state.severity) tokens.push(`Dampak: ${state.severity}`);
    if (state.document) tokens.push(`Dokumen: ${state.document}`);
    if (state.date_from || state.date_to) tokens.push(`Tanggal: ${state.date_from || "…"}–${state.date_to || "…"}`);
    return `<div class="selected-filters" aria-label="Filter terpilih"><span class="selected-filters-label">Filter terpilih</span>${tokens.map((token) => `<span class="filter-token">${A.escapeHtml(token)}</span>`).join("")}</div>`;
  }

  function relatedDocumentText(item) {
    const model = A.MODEL_LABELS[item.model] || item.model || "Dokumen terkait";
    return `${item.number || "Nomor tidak tersedia"} · ${model} · ${A.statePresentation(item.state).label}`;
  }

  function severityLabel(value) {
    return { HIGH: "Tinggi", MEDIUM: "Sedang", LOW: "Rendah", HISTORICAL: "Historis" }[value] || "Belum tersedia";
  }

  function exceptionRow(item, state) {
    const shareUrl = new URL(window.location.href);
    shareUrl.searchParams.set("view", "exceptions");
    shareUrl.searchParams.set("document", item.affectedDocument);
    return `
      <tr>
        <td>${statusBadge(item.status)}<span class="cell-note">${A.escapeHtml(severityLabel(item.severity))}</span></td>
        <td class="exception-situation"><strong>${A.escapeHtml(item.situation)}</strong><span>${A.escapeHtml(item.explanation)}</span><span>${technicalReference(item.rawStatus, item.ruleId)}</span></td>
        <td class="exception-document"><strong>${A.escapeHtml(item.affectedDocument)}</strong><span>${A.escapeHtml(item.affectedModel)}${item.documentId ? ` · Native ID ${A.escapeHtml(item.documentId)}` : ""}</span>${(item.relatedDocuments || []).map((related) => `<span>Dokumen terkait: ${A.escapeHtml(relatedDocumentText(related))}</span>`).join("") || "<span>Dokumen terkait belum tersedia.</span>"}</td>
        <td>${A.escapeHtml(item.process)}</td>
        <td class="exception-impact"><strong>Mengapa penting:</strong> ${A.escapeHtml(item.why)}<span><b>Dampak:</b> ${A.escapeHtml(item.impact)}</span><span><b>Peninjau:</b> ${A.escapeHtml(item.reviewer)}</span></td>
        <td>${statusBadge(item.confidence)}<span class="cell-note">${A.escapeHtml(A.formatDateTime(item.detectedAt))}</span></td>
        <td><div class="table-actions"><button class="secondary-button copy-action" type="button" data-copy="${A.escapeHtml(item.affectedDocument)}">Salin nomor</button><button class="secondary-button copy-action" type="button" data-copy="${A.escapeHtml(shareUrl.toString())}">Salin URL</button>${item.journeyUrl ? `<a class="table-link" data-route-link href="${A.escapeHtml(item.journeyUrl)}">Perjalanan dokumen</a>` : ""}</div></td>
      </tr>`;
  }

  function bindCopyActions() {
    document.querySelectorAll("[data-copy]").forEach((button) => button.addEventListener("click", async () => {
      const value = button.dataset.copy;
      try {
        await navigator.clipboard.writeText(value);
      } catch {
        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      showToast("Disalin ke clipboard.");
    }));
  }

  function bindExceptions(state, total) {
    const form = document.getElementById("worklistFilters");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const classification = document.getElementById("classificationFilter").value;
      const values = { classification };
      if (classification === "historical") values.rule = "PO-CANCEL-001";
      else {
        values.process = document.getElementById("processFilter").value;
        values.owner = document.getElementById("ownerFilter").value;
        values.severity = document.getElementById("severityFilter").value;
        values.document = document.getElementById("documentFilter").value.trim();
        values.date_from = document.getElementById("dateFromFilter").value;
        values.date_to = document.getElementById("dateToFilter").value;
        values.rule = state.rule;
      }
      navigate(routeHref("exceptions", values));
    });
    document.getElementById("classificationFilter").addEventListener("change", () => form.requestSubmit());
    document.getElementById("clearWorklistFilters").addEventListener("click", () => navigate(routeHref("exceptions", { classification: "active" })));
    document.querySelector("[data-page='previous']")?.addEventListener("click", () => navigate(routeHref("exceptions", { ...state, offset: Math.max(0, state.offset - 25), params: undefined, view: undefined, id: undefined, model: undefined, journeyPage: undefined })));
    document.querySelector("[data-page='next']")?.addEventListener("click", () => {
      if (state.offset + 25 < total) navigate(routeHref("exceptions", { ...state, offset: state.offset + 25, params: undefined, view: undefined, id: undefined, model: undefined, journeyPage: undefined }));
    });
    bindCopyActions();
  }

  async function renderExceptions(state) {
    const request = A.exceptionRequest({ ...state, limit: 25 });
    const [payload, poScope, health] = await Promise.all([
      apiJson(request.url),
      apiJson("/api/control-tower/po-cancellation-scope?limit=1&offset=0"),
      apiJson("/api/control-tower/health"),
    ]);
    const rows = request.kind === "historical" ? (payload.rows || []).map(A.normalizeHistoricalPo) : (payload.rows || []).map(A.normalizeException);
    const total = Number(payload.total || 0);
    const po = A.poScopeSummary(poScope.summary);
    const html = `
      ${viewHeading("Daftar Pengecualian", "Default menampilkan masalah operasional aktif; ketidakpastian dan histori tetap dipisahkan.", `${A.formatNumber(total)} hasil`)}
      ${filtersMarkup(state)}
      ${selectedFiltersMarkup(state)}
      ${A.shouldShowActivePoEmptyState(state, total) ? `<section class="state-panel tone-success"><h2>Tidak ada masalah aktif untuk PO yang dibatalkan mulai tahun 2026.</h2><p>${A.formatNumber(po.checked)} PO diperiksa dan ${A.formatNumber(po.checked - po.active)} sesuai. ${A.formatNumber(po.historical)} kasus sebelum 2026 tetap tersedia sebagai Catatan Historis.</p></section><br>` : ""}
      <section class="table-panel" aria-label="Daftar pengecualian Control Tower">
        <div class="table-toolbar"><div><strong>Worklist operasional</strong><span>Filter dan pagination diproses di server; tidak ada write-back pada fase ini.</span></div></div>
        <div class="table-scroll" tabindex="0" aria-label="Tabel pengecualian dapat digulir secara horizontal">
          <table class="exception-table"><thead><tr><th>Klasifikasi</th><th>Apa yang terjadi</th><th>Dokumen</th><th>Proses</th><th>Alasan, dampak, peninjau</th><th>Bukti</th><th>Tindakan</th></tr></thead><tbody>${rows.length ? rows.map((item) => exceptionRow(item, state)).join("") : `<tr><td colspan="7" class="empty-cell">${A.escapeHtml(A.emptyMessage(state.classification, state.rule))}</td></tr>`}</tbody></table>
        </div>
        <footer class="pagination-footer"><button class="secondary-button" type="button" data-page="previous"${state.offset <= 0 ? " disabled" : ""}>Sebelumnya</button><span>${total ? `${A.formatNumber(state.offset + 1)}–${A.formatNumber(Math.min(total, state.offset + 25))} dari ${A.formatNumber(total)}` : "0 hasil"}</span><button class="secondary-button" type="button" data-page="next"${state.offset + 25 >= total ? " disabled" : ""}>Berikutnya</button></footer>
      </section>`;
    commitView(html, health, () => bindExceptions(state, total));
  }

  function journeySearch(model = "", id = "") {
    const models = [
      ["sale.order", "Sales Order"], ["sale.order.line", "Baris Sales Order"],
      ["approval.request", "Internal Order"], ["approval.product.line", "Baris Internal Order"],
      ["mrp.production", "Manufacturing Order"], ["purchase.order", "Purchase Order"],
      ["stock.picking", "Receipt / Delivery"], ["account.move", "Invoice"],
    ];
    return `<form class="filter-panel journey-search" id="journeySearch"><label><span>Jenis dokumen utama</span><select id="journeyModel" required><option value="">Pilih jenis dokumen</option>${models.map(([value, label]) => `<option value="${value}"${model === value ? " selected" : ""}>${label}</option>`).join("")}</select></label><label><span>Native ID</span><input id="journeyId" type="number" min="1" step="1" value="${A.escapeHtml(id)}" placeholder="Contoh: 116" required></label><button class="primary-button" type="submit">Tampilkan hubungan</button></form>`;
  }

  function bindJourneySearch() {
    document.getElementById("journeySearch")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const model = document.getElementById("journeyModel").value;
      const id = document.getElementById("journeyId").value;
      if (model && id) navigate(routeHref("journey", { model, id }));
    });
  }

  function journeyRelationRow(link) {
    return `<tr><td class="num">${A.formatNumber(link.depth)}</td><td class="relation-document"><strong>${A.escapeHtml(link.parent.number)}</strong><span>${A.escapeHtml(link.parent.modelLabel)} · Native ID ${A.escapeHtml(link.parent.id)}</span></td><td>${statusBadge(link.parent.state)}</td><td class="relation-document"><strong>${A.escapeHtml(link.child.number)}</strong><span>${A.escapeHtml(link.child.modelLabel)} · Native ID ${A.escapeHtml(link.child.id)}</span></td><td>${statusBadge(link.child.state)}</td><td>${statusBadge(link.evidence)}<span class="cell-note">${A.escapeHtml(link.linkType || "Tipe hubungan belum tersedia")}</span></td><td>${statusBadge(link.confidence)}</td></tr>`;
  }

  function journeyValidationRows(validations) {
    if (!validations.length) return `<li><span>Tidak ada hasil validasi langsung untuk dokumen utama ini.</span></li>`;
    return validations.map((item) => `<li><span><strong>${A.escapeHtml(item.situation)}</strong><br>${technicalReference(item.rawStatus, item.ruleId)}</span>${statusBadge(item.status)}</li>`).join("");
  }

  function bindJourney(state, totalPages) {
    bindJourneySearch();
    document.querySelector("[data-journey-page='previous']")?.addEventListener("click", () => navigate(routeHref("journey", { model: state.model, id: state.id, journey_page: Math.max(1, state.journeyPage - 1) })));
    document.querySelector("[data-journey-page='next']")?.addEventListener("click", () => navigate(routeHref("journey", { model: state.model, id: state.id, journey_page: Math.min(totalPages, state.journeyPage + 1) })));
    bindCopyActions();
  }

  async function renderJourney(state) {
    if (!state.model || !state.id) {
      const health = await apiJson("/api/control-tower/health");
      const html = `
        ${viewHeading("Perjalanan Dokumen", "Telusuri bukti langsung dan turunan tanpa menganggap hubungan sebagai kronologi.")}
        <section class="context-banner"><strong>Perjalanan Dokumen menunjukkan hubungan dokumen, bukan selalu urutan waktu.</strong></section>
        ${journeySearch()}
        <section class="summary-strip"><article class="detail-item"><span>Bukti langsung</span><strong>Ditampilkan bila tersedia</strong></article><article class="detail-item"><span>Bukti turunan</span><strong>Diberi label terpisah</strong></article><article class="detail-item"><span>Payment</span><strong>Belum dipublikasikan</strong></article><article class="detail-item"><span>Distribusi JO</span><strong>Memerlukan bukti manual</strong></article></section>`;
      commitView(html, health, bindJourneySearch);
      return;
    }

    const [payload, health] = await Promise.all([
      apiJson(`/api/control-tower/journey/${encodeURIComponent(state.model)}/${encodeURIComponent(state.id)}`),
      apiJson("/api/control-tower/health"),
    ]);
    const journey = A.normalizeJourney(payload);
    const validations = (payload.validations || []).map(A.normalizeException);
    const totalPages = Math.max(1, Math.ceil(journey.links.length / JOURNEY_PAGE_SIZE));
    const page = Math.min(state.journeyPage, totalPages);
    const start = (page - 1) * JOURNEY_PAGE_SIZE;
    const visible = journey.links.slice(start, start + JOURNEY_PAGE_SIZE);
    const html = `
      ${viewHeading("Perjalanan Dokumen", "Perjalanan Dokumen menunjukkan hubungan dokumen, bukan selalu urutan waktu.", `${A.formatNumber(journey.links.length)} hubungan`)}
      ${journeySearch(state.model, state.id)}
      <section class="journey-summary" aria-label="Dokumen utama"><article class="detail-item"><span>Jenis dokumen</span><strong>${A.escapeHtml(journey.root.modelLabel)}</strong></article><article class="detail-item"><span>Nomor dokumen</span><strong>${A.escapeHtml(journey.root.number)}</strong></article><article class="detail-item"><span>Native ID</span><strong>${A.escapeHtml(journey.root.id)}</strong></article><article class="detail-item"><span>Status</span><strong>${A.escapeHtml(journey.root.state.label)}</strong></article></section>
      <div class="inline-actions"><button class="secondary-button" type="button" data-copy="${A.escapeHtml(journey.root.number)}">Salin nomor dokumen</button><button class="secondary-button" type="button" data-copy="${A.escapeHtml(window.location.href)}">Salin URL</button></div><br>
      <div class="journey-layout">
        <section class="table-panel" aria-label="Hubungan dokumen"><div class="table-toolbar"><div><strong>Hubungan dokumen</strong><span>Bukti, status, dan native reference—bukan urutan waktu.</span></div></div><div class="table-scroll" tabindex="0" aria-label="Tabel hubungan dapat digulir secara horizontal"><table class="relation-table"><thead><tr><th>Tingkat</th><th>Dokumen asal</th><th>Status asal</th><th>Dokumen terkait</th><th>Status terkait</th><th>Bukti relasi</th><th>Kekuatan bukti</th></tr></thead><tbody>${visible.length ? visible.map(journeyRelationRow).join("") : `<tr><td colspan="7" class="empty-cell">Belum ada hubungan dokumen pada snapshot terbaru.</td></tr>`}</tbody></table></div><footer class="pagination-footer"><button class="secondary-button" type="button" data-journey-page="previous"${page <= 1 ? " disabled" : ""}>Sebelumnya</button><span>${journey.links.length ? `${A.formatNumber(start + 1)}–${A.formatNumber(Math.min(journey.links.length, start + JOURNEY_PAGE_SIZE))} dari ${A.formatNumber(journey.links.length)}` : "0 hubungan"}</span><button class="secondary-button" type="button" data-journey-page="next"${page >= totalPages ? " disabled" : ""}>Berikutnya</button></footer></section>
        <aside class="panel journey-aside" aria-label="Kelengkapan perjalanan"><h3>Tahap yang ditemukan</h3><p>Tahap yang tidak terlihat tidak dianggap gagal; hubungan mungkin belum tersedia atau memang tidak berlaku.</p><ul class="stage-list">${journey.expectedStages.map((stage) => `<li><span>${A.escapeHtml(stage.label)}</span>${statusBadge(stage.available ? { label: "Ditemukan", tone: "success" } : { label: "Tidak ditemukan", tone: "neutral" })}</li>`).join("")}</ul><h3>Validasi dokumen utama</h3><ul class="evidence-list">${journeyValidationRows(validations)}</ul><h3>Cakupan khusus</h3><ul class="stage-list"><li><span>Payment</span>${statusBadge(A.statusPresentation("MAPPING_PENDING"))}</li><li><span>Distribusi JO</span>${statusBadge(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED"))}</li></ul></aside>
      </div>`;
    commitView(html, health, () => bindJourney({ ...state, journeyPage: page }, totalPages));
  }

  function navigate(target) {
    const url = new URL(target, window.location.origin);
    if (url.origin !== window.location.origin || url.pathname !== "/control-tower") return;
    if ((url.searchParams.get("view") || "overview") === "overview" && !url.searchParams.get("process")) url.searchParams.set("process", lastSelectedProcess);
    window.history.pushState(null, "", `${url.pathname}${url.search}`);
    closeDrawers();
    requestLoad("navigation");
  }

  function applyTheme(theme) {
    const selected = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = selected;
    themeButton.setAttribute("aria-pressed", String(selected === "dark"));
    themeButton.textContent = selected === "dark" ? "Tema Terang" : "Tema Gelap";
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  }

  function applyMotionState() {
    document.body.classList.toggle("motion-paused", motionPaused || reducedMotion.matches);
    document.querySelectorAll(".map-edge").forEach((edge) => edge.classList.toggle("is-paused", motionPaused || reducedMotion.matches));
    motionButton.setAttribute("aria-pressed", String(motionPaused));
    motionButton.textContent = reducedMotion.matches ? "Gerak Diminimalkan" : motionPaused ? "Lanjut Animasi" : "Jeda Animasi";
    motionButton.disabled = reducedMotion.matches;
    const mapButton = document.getElementById("mapMotionButton");
    if (mapButton) {
      mapButton.textContent = reducedMotion.matches ? "Gerak minimum" : motionPaused ? "Lanjut" : "Jeda";
      mapButton.disabled = reducedMotion.matches;
    }
  }

  function toggleMotion() {
    if (reducedMotion.matches) {
      showToast("Gerak diminimalkan oleh preferensi sistem.");
      return;
    }
    motionPaused = !motionPaused;
    localStorage.setItem(MOTION_KEY, String(motionPaused));
    applyMotionState();
  }

  function toggleDisplayMode() {
    displayMode = !displayMode;
    document.body.classList.toggle("display-mode", displayMode);
    displayButton.setAttribute("aria-pressed", String(displayMode));
    displayButton.textContent = displayMode ? "Keluar Display" : "Display Mode";
    if (displayMode && routeState().view !== "overview") navigate(routeHref("overview", { process: lastSelectedProcess }));
  }

  function clearAutoTimer() {
    if (autoTimer) window.clearTimeout(autoTimer);
    autoTimer = null;
    autoDueAt = null;
  }

  function scheduleAutoRefresh() {
    clearAutoTimer();
    const value = autoRefreshSelect.value;
    if (value === "off" || document.hidden || sessionExpired || blockingError) return;
    const delay = Number(value) * 60_000;
    autoDueAt = Date.now() + delay;
    autoTimer = window.setTimeout(async () => {
      autoTimer = null;
      if (!document.hidden && !activeLoad && !sessionExpired && !blockingError) await requestLoad("auto");
      scheduleAutoRefresh();
    }, delay);
  }

  function setAutoRefresh(value) {
    const selected = AUTO_REFRESH_VALUES.has(value) ? value : "5";
    autoRefreshSelect.value = selected;
    localStorage.setItem(AUTO_REFRESH_KEY, selected);
    scheduleAutoRefresh();
  }

  document.addEventListener("click", (event) => {
    const anchor = event.target.closest("a[data-route-link]");
    if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(anchor.href, window.location.origin);
    if (url.origin === window.location.origin && url.pathname === "/control-tower") {
      event.preventDefault();
      navigate(url);
    }
  });

  refreshButton.addEventListener("click", () => requestLoad("manual"));
  autoRefreshSelect.addEventListener("change", () => setAutoRefresh(autoRefreshSelect.value));
  themeButton.addEventListener("click", toggleTheme);
  displayButton.addEventListener("click", toggleDisplayMode);
  motionButton.addEventListener("click", toggleMotion);
  window.addEventListener("popstate", () => requestLoad("popstate"));
  window.addEventListener("keydown", (event) => {
    trapDrawerFocus(event);
    if (event.key === "Escape") {
      closeDrawers();
      if (displayMode) toggleDisplayMode();
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearAutoTimer();
    else {
      if (autoDueAt && autoDueAt <= Date.now()) requestLoad("auto");
      scheduleAutoRefresh();
    }
  });
  reducedMotion.addEventListener?.("change", applyMotionState);

  applyTheme(localStorage.getItem(THEME_KEY) || "light");
  applyMotionState();
  setAutoRefresh(localStorage.getItem(AUTO_REFRESH_KEY) || "5");
  updateNavigation(routeState().view);
  requestLoad("initial");

  window.ControlTowerApp = Object.freeze({ requestLoad, routeState, navigate, toggleDisplayMode });
})();
