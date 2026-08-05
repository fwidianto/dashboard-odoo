(() => {
  "use strict";

  const path = window.location.pathname;
  const isControlTowerOverview = path === "/dashboard/control-tower";
  const modeToggle = document.querySelector("[data-ct-mode-toggle]");
  const freshness = document.querySelector("[data-ct-freshness]");
  const refreshButton = document.querySelector("[data-ct-refresh]");
  const refreshPanel = document.querySelector("[data-ct-refresh-panel]");
  const refreshMinimize = document.querySelector("[data-ct-refresh-minimize]");
  const refreshStage = document.querySelector("[data-ct-refresh-stage]");
  const refreshMessage = document.querySelector("[data-ct-refresh-message]");
  const refreshDiagnostic = document.querySelector("[data-ct-refresh-diagnostic]");
  const refreshTrusted = document.querySelector("[data-ct-refresh-trusted]");
  const refreshElapsed = document.querySelector("[data-ct-refresh-elapsed]");
  const refreshCounts = document.querySelector("[data-ct-refresh-counts]");
  const refreshRecover = document.querySelector("[data-ct-refresh-recover]");
  const refreshRecoverAction = document.querySelector("[data-ct-refresh-recover-action]");
  const params = new URLSearchParams(window.location.search);
  let refreshReloadEvidence = null;
  let refreshPollTimer = 0;
  let refreshPollCount = 0;
  let refreshPanelOpen = false;

  function safeReturnPath(raw) {
    if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || /^[a-z][a-z\d+.-]*:/i.test(raw)) return "";
    try {
      const parsed = new URL(raw, window.location.origin);
      if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith("/dashboard/")) return "";
      decodeURIComponent(parsed.pathname + parsed.search + parsed.hash);
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    } catch {
      return "";
    }
  }

  function routeForPathname(value) {
    if (value === "/dashboard/control-tower") return "control-tower";
    if (value === "/dashboard/control-tower/temuan") return "temuan";
    if (value === "/dashboard/sales-orders") return "sales-orders";
    if (value === "/dashboard/internal-orders") return "internal-orders";
    if (value === "/dashboard/internal-order-rekap") return "internal-order-rekap";
    return "";
  }

  const activeRoute = routeForPathname(path);
  document.querySelectorAll("[data-ct-route]").forEach((link) => {
    const active = link.dataset.ctRoute === activeRoute;
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  function setMode(mode, persist = isControlTowerOverview) {
    const office = mode === "office";
    window.controlTowerOfficeMode = office;
    document.documentElement.dataset.ctMode = office ? "office" : "desk";
    document.body.dataset.ctMode = office ? "office" : "desk";
    if (modeToggle) {
      modeToggle.textContent = office ? "Desk mode" : "Office mode";
      modeToggle.setAttribute("aria-pressed", String(office));
      modeToggle.title = office ? "Switch to desk mode" : "Switch to office mode";
    }
    if (persist) {
      try {
        sessionStorage.setItem("ct-display-mode", office ? "office" : "desk");
      } catch {
        // Session storage is optional.
      }
    }
    window.dispatchEvent(new CustomEvent("control-tower-office-mode", { detail: { office } }));
  }

  let storedMode = "";
  try {
    storedMode = sessionStorage.getItem("ct-display-mode") || "";
  } catch {
    storedMode = "";
  }
  setMode(isControlTowerOverview && storedMode !== "desk" ? "office" : "desk", isControlTowerOverview);
  modeToggle?.addEventListener("click", () => setMode(window.controlTowerOfficeMode ? "desk" : "office", true));

  function formatFreshnessTime(value) {
    if (!value) return "Belum ada timestamp";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" });
  }

  function formatElapsed(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
    const total = Math.max(0, Math.round(Number(seconds)));
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return minutes === 0 ? `${rest} dtk` : `${minutes} mnt ${rest} dtk`;
  }

  function chipStateLabel(payload) {
    const ui = (payload && payload.refresh_ui) || {};
    if (ui.active) return "Memperbarui";
    if (ui.status === "FAILED") return "Gagal";
    if (ui.status === "STALE") return "Pembaruan terhenti";
    if (ui.status === "NO_COMPLETED_EXTRACTION") return "Belum ada data";
    const freshnessState = payload?.freshness_classification?.state || payload?.freshness || "UNAVAILABLE";
    return {
      CURRENT: "Terkini",
      STALE: "Perlu diperbarui",
      CRITICALLY_STALE: "Kedaluwarsa",
      UNAVAILABLE: "Tidak tersedia"
    }[freshnessState] || freshnessState;
  }

  function refreshPanelState(payload) {
    const ui = (payload && payload.refresh_ui) || {};
    const status = String(ui.status || "UNAVAILABLE");
    const outcome = ui.outcome || null;
    const trusted = ui.trusted || null;
    const attempt = ui.latest_attempt || {};
    const failureMessage = "Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil.";
    let panelState = "IDLE";
    if (status === "UNAVAILABLE") panelState = "UNAVAILABLE";
    else if (status === "READING" || status === "CHECKING") panelState = "ACTIVE";
    else if (status === "DONE") panelState = outcome === "SUCCESS" ? "SUCCESS" : "IDLE";
    else if (status === "FAILED") panelState = "FAILED";
    else if (status === "STALE") panelState = "STALE";
    else if (status === "RECOVERED") panelState = "RECOVERED";
    else if (status === "NO_COMPLETED_EXTRACTION") panelState = "NO_COMPLETED_EXTRACTION";
    let message = ui.message || "";
    if (panelState === "FAILED" && !message) message = failureMessage;
    if (panelState === "UNAVAILABLE" && !message) message = "Status pembaruan tidak dapat dibaca.";
    const diagnostic = attempt.error_message && attempt.error_message !== message ? attempt.error_message : "";
    const counts = ui.counts || null;
    const countsText = counts && typeof counts.models_completed === "number"
      ? `${counts.models_completed} model selesai · ${counts.records ?? 0} record`
      : "";
    return {
      panelState,
      stageLabel: ui.stage_label || "Status tidak tersedia",
      message,
      diagnostic,
      trustedText: trusted && trusted.timestamp ? formatFreshnessTime(trusted.timestamp) : "Belum ada snapshot terpercaya",
      elapsedText: formatElapsed(ui.elapsed_seconds),
      countsText,
      active: Boolean(ui.active),
      canRefresh: Boolean(ui.can_refresh),
      canRecoverStale: Boolean(ui.can_recover_stale)
    };
  }

  function renderRefreshPanel(payload) {
    const state = refreshPanelState(payload);
    const forceOpen = state.active || state.panelState === "FAILED" || state.panelState === "STALE";
    if (refreshPanel) {
      refreshPanel.dataset.state = state.panelState;
      if (refreshPanelOpen || forceOpen) {
        refreshPanel.hidden = false;
        refreshPanelOpen = true;
      }
    }
    if (refreshStage) refreshStage.textContent = state.stageLabel;
    if (refreshMessage) refreshMessage.textContent = state.message;
    if (refreshDiagnostic) {
      refreshDiagnostic.hidden = !state.diagnostic;
      refreshDiagnostic.textContent = state.diagnostic;
    }
    if (refreshTrusted) refreshTrusted.textContent = state.trustedText;
    if (refreshElapsed) refreshElapsed.textContent = state.elapsedText;
    if (refreshCounts) refreshCounts.textContent = state.countsText || "—";
    if (refreshButton) refreshButton.hidden = !state.canRefresh || state.active;
    if (refreshRecover) refreshRecover.hidden = !(state.canRecoverStale && state.panelState === "STALE");
    return state;
  }

  function renderFreshness(payload, error = "") {
    if (!freshness) return;
    const stateElement = freshness.querySelector("[data-ct-freshness-state]");
    const timeElement = freshness.querySelector("[data-ct-freshness-time]");
    if (error || !payload) {
      freshness.dataset.state = "UNAVAILABLE";
      if (stateElement) stateElement.textContent = "Tidak tersedia";
      if (timeElement) timeElement.textContent = "Status data tidak tersedia";
      freshness.title = error || "Status freshness tidak dapat dibaca.";
      return;
    }
    const ui = payload.refresh_ui || {};
    const machineState = ui.active
      ? "REFRESHING"
      : ui.status === "FAILED"
        ? "FAILED"
        : ui.status === "STALE"
          ? "STALE"
          : ui.status === "NO_COMPLETED_EXTRACTION"
            ? "NO_COMPLETED_EXTRACTION"
            : payload?.freshness_classification?.state || payload?.freshness || "UNAVAILABLE";
    freshness.dataset.state = machineState;
    if (stateElement) stateElement.textContent = chipStateLabel(payload);
    const trustedTime = ui.trusted?.timestamp || payload.latest_trusted_completed_at;
    if (timeElement) timeElement.textContent = trustedTime ? formatFreshnessTime(trustedTime) : "Belum ada snapshot";
    const failure = ui.message ? ` ${ui.message}` : "";
    freshness.title = `Data terakhir diperbarui: ${trustedTime ? formatFreshnessTime(trustedTime) : "Belum ada"}.${failure}`;
  }

  async function loadRefreshStatus() {
    try {
      const response = await fetch("/api/control-tower/refresh", { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error(`Status ${response.status}`);
      const payload = await response.json();
      renderFreshness(payload);
      renderRefreshPanel(payload);
      return payload;
    } catch (error) {
      renderFreshness(null, error.message);
      if (refreshPanel) {
        refreshPanel.dataset.state = "UNAVAILABLE";
        refreshPanel.hidden = false;
      }
      if (refreshStage) refreshStage.textContent = "Status tidak tersedia";
      if (refreshMessage) refreshMessage.textContent = "Status pembaruan tidak dapat dibaca.";
      return null;
    }
  }

  function setRefreshPanelMinimized(minimized) {
    if (!refreshPanel) return;
    refreshPanel.classList.toggle("is-minimized", minimized);
    if (refreshMinimize) {
      refreshMinimize.setAttribute("aria-expanded", String(!minimized));
      refreshMinimize.textContent = minimized ? "Perluas" : "Minimalkan";
    }
  }

  function openRefreshPanel() {
    if (!refreshPanel) return;
    refreshPanelOpen = true;
    refreshPanel.hidden = false;
    setRefreshPanelMinimized(false);
  }

  function stopRefreshPolling() {
    if (refreshPollTimer) {
      window.clearInterval(refreshPollTimer);
      refreshPollTimer = 0;
    }
  }

  function startRefreshPolling() {
    if (refreshPollTimer) return Promise.resolve();
    refreshPollCount = 0;
    return new Promise((resolve) => {
      const tick = async () => {
        refreshPollCount += 1;
        const payload = await loadRefreshStatus();
        const state = refreshPanelState(payload || {});
        const terminal = !state.active && state.panelState !== "UNAVAILABLE" && state.panelState !== "LOADING";
        const hardStop = refreshPollCount >= 900;
        if (terminal) {
          if (state.panelState === "SUCCESS" && refreshReloadEvidence) void refreshReloadEvidence();
          stopRefreshPolling();
          resolve();
          return;
        }
        if (hardStop) {
          if (refreshMessage) refreshMessage.textContent = "Status pembaruan belum berubah dalam batas waktu pemantauan. Muat ulang halaman untuk memeriksa ulang.";
          stopRefreshPolling();
          resolve();
        }
      };
      void tick();
      refreshPollTimer = window.setInterval(() => { void tick(); }, 4000);
    });
  }

  async function requestRefresh() {
    if (!refreshButton) return;
    refreshButton.disabled = true;
    openRefreshPanel();
    if (refreshStage) refreshStage.textContent = "Menyiapkan pembaruan";
    if (refreshMessage) refreshMessage.textContent = "Memeriksa ketersediaan pembaruan...";
    try {
      const response = await fetch("/api/control-tower/refresh", {
        method: "POST",
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      });
      let payload = {};
      try { payload = await response.json(); } catch { /* response body is optional */ }
      if (response.status === 409) {
        const fresh = await loadRefreshStatus();
        if (fresh) await startRefreshPolling();
        return;
      }
      if (!response.ok) throw new Error(payload.detail || `Request gagal (${response.status}).`);
      await startRefreshPolling();
    } catch (error) {
      if (refreshPanel) {
        refreshPanel.dataset.state = "UNAVAILABLE";
        refreshPanel.hidden = false;
      }
      if (refreshStage) refreshStage.textContent = "Gagal memulai pembaruan";
      if (refreshMessage) refreshMessage.textContent = error.message || "Status pembaruan tidak dapat dibaca.";
    } finally {
      refreshButton.disabled = false;
    }
  }

  async function requestRecoverStale() {
    if (!refreshRecoverAction) return;
    const proceed = window.confirm(
      "Percobaan pembaruan lama akan ditutup. Snapshot terpercaya tidak akan diubah. Lanjutkan?"
    );
    if (!proceed) return;
    refreshRecoverAction.disabled = true;
    if (refreshStage) refreshStage.textContent = "Menutup percobaan pembaruan lama";
    if (refreshMessage) refreshMessage.textContent = "Memproses penutupan percobaan pembaruan lama...";
    try {
      const response = await fetch("/api/control-tower/refresh/recover", {
        method: "POST",
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      });
      let payload = {};
      try { payload = await response.json(); } catch { /* response body is optional */ }
      if (!response.ok) throw new Error(payload.detail || `Permintaan gagal (${response.status}).`);
      await loadRefreshStatus();
    } catch (error) {
      if (refreshPanel) {
        refreshPanel.dataset.state = "FAILED";
        refreshPanel.hidden = false;
      }
      if (refreshStage) refreshStage.textContent = "Gagal menutup percobaan pembaruan";
      if (refreshMessage) refreshMessage.textContent = error.message || "Status pembaruan tidak dapat dibaca.";
    } finally {
      refreshRecoverAction.disabled = false;
    }
  }

  if (freshness) {
    loadRefreshStatus().then((payload) => {
      const state = refreshPanelState(payload || {});
      if (state.active || state.panelState === "FAILED" || state.panelState === "STALE") openRefreshPanel();
      if (state.active) void startRefreshPolling();
    });
  }
  refreshButton?.addEventListener("click", requestRefresh);
  refreshRecoverAction?.addEventListener("click", requestRecoverStale);
  refreshMinimize?.addEventListener("click", () => {
    if (!refreshPanel) return;
    setRefreshPanelMinimized(!refreshPanel.classList.contains("is-minimized"));
  });

  const contextBar = document.querySelector("[data-ct-context-return]");
  const returnTo = safeReturnPath(params.get("return_to"));
  if (contextBar && returnTo) {
    const returnLink = contextBar.matches("a") ? contextBar : contextBar.querySelector("a");
    const summary = contextBar.querySelector("[data-ct-context-summary]");
    if (returnLink) {
      returnLink.href = returnTo;
      returnLink.textContent = returnTo.includes("/temuan") ? "Kembali ke Temuan" : "Kembali ke Control Tower";
    }
    if (summary) {
      const category = params.get("presentation_category") || params.get("category");
      summary.textContent = category ? `Konteks: ${category.replaceAll("_", " ")}` : "Konteks investigasi dipertahankan";
    }
    contextBar.hidden = false;
  }

  function initImmersiveControlTower() {
    const stage = document.querySelector("[data-ct-map-stage]");
    if (!stage) return;

    const categoryOrder = ["MASALAH_AKTIF", "PERLU_DITINJAU", "DATA_BELUM_LENGKAP"];
    const categoryLabels = {
      MASALAH_AKTIF: "Masalah Aktif",
      PERLU_DITINJAU: "Perlu Ditinjau",
      DATA_BELUM_LENGKAP: "Data Belum Lengkap"
    };
    const processAliases = {
      estimate: ["estimate", "estimation", "rkb-kasar"],
      quotation: ["quotation"],
      "sales-order": ["sales-order"],
      "manufacturing-order": ["manufacturing-order"],
      production: ["production", "manufacture"],
      "quality-control": ["quality-control", "qc"],
      "stock-finished-goods": ["stock-finished-goods", "stock-fg", "finished-goods"],
      delivery: ["delivery"],
      invoice: ["invoice"],
      payment: ["payment"],
      "internal-order": ["internal-order"],
      "so-pb": ["so-pb"],
      "material-source": ["material-source"],
      "rkb-pekerjaan": ["rkb-pekerjaan"],
      "stock-check": ["stock-check", "cek-stock"],
      "stock-material": ["stock-material"],
      "rop-pekerjaan": ["rop-pekerjaan"],
      "material-purchase-order": ["material-purchase-order", "purchase-order"],
      "receipt-qc": ["receipt-qc", "material-receipt", "receipt"],
      "rop-non-so": ["rop-non-so"],
      "vendor-bill": ["vendor-bill"],
      "stock-expense": ["stock-expense", "stock-or-expense"]
    };
    // Phase 7 data-trust contract. A visible zero is only allowed when a process
    // is explicitly backed by the current backend rule mapping and the category
    // request succeeded. Other processes remain useful for navigation, but must
    // not imply that Control Tower has checked them.
    const processCoverage = {
      estimate: {
        state: "EXTERNAL_CONTEXT",
        message: "Proses pra-Odoo; belum dinilai oleh pemeriksaan otomatis Control Tower."
      },
      "sales-order": { state: "MAPPED" },
      "manufacturing-order": { state: "MAPPED" },
      "internal-order": { state: "MAPPED" },
      "material-purchase-order": { state: "MAPPED" }
    };
    const defaultCoverage = {
      state: "NOT_MAPPED",
      message: "Belum ada pemeriksaan Control Tower yang dipetakan langsung ke proses ini."
    };

    const temuan = stage.querySelector("[data-ct-temuan]");
    const temuanToggle = stage.querySelector("[data-ct-temuan-toggle]");
    const inspector = stage.querySelector("[data-ct-inspector]");
    const inspectorClose = stage.querySelector("[data-ct-inspector-close]");
    const inspectorTitle = stage.querySelector("[data-ct-inspector-title]");
    const primarySignal = stage.querySelector("[data-ct-primary-signal]");
    const openDocuments = stage.querySelector("[data-ct-open-documents]");
    const hoverPreview = stage.querySelector("[data-ct-hover-preview]");
    const previewTitle = stage.querySelector("[data-ct-preview-title]");
    const mapScroll = stage.querySelector("[data-ct-map-scroll]");
    const mapStatus = stage.querySelector("[data-ct-map-status]");
    const scrollCue = stage.querySelector("[data-ct-scroll-cue]");
    const nodes = [...stage.querySelectorAll("[data-ct-process-node]")];
    const routeElements = [...stage.querySelectorAll("[data-routes]")];
    const connectorSvg = stage.querySelector(".ct-connectors");
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    const routeAnimationSequences = {
      normal: [
        "estimate-quotation",
        "quotation-sales-order",
        "sales-order-mo-trunk",
        "mo-entry",
        "mo-production",
        "production-qc",
        "qc-stock-fg",
        "stock-fg-delivery",
        "delivery-invoice",
        "invoice-payment"
      ],
      internal: [
        "internal-order-mo-trunk",
        "mo-entry",
        "mo-production",
        "production-qc",
        "qc-stock-fg",
        "stock-fg-so-pb",
        "so-pb-delivery-return",
        "delivery-invoice",
        "invoice-payment"
      ],
      material: [
        "sales-order-material-source",
        "material-source-corridor",
        "material-source-entry",
        "material-source-rkb",
        "rkb-stock-check",
        "stock-check-stock-material",
        "stock-material-mo",
        "mo-production",
        "production-qc",
        "qc-stock-fg",
        "stock-fg-delivery",
        "delivery-invoice",
        "invoice-payment"
      ],
      procurement: [
        "sales-order-material-source",
        "material-source-corridor",
        "material-source-entry",
        "material-source-rkb",
        "rkb-stock-check",
        "stock-check-rop",
        "rop-purchase-order",
        "purchase-order-receipt",
        "receipt-stock-material",
        "stock-material-mo",
        "mo-production",
        "production-qc",
        "qc-stock-fg",
        "stock-fg-delivery",
        "delivery-invoice",
        "invoice-payment"
      ],
      nonso: [
        "rop-nonso-purchase-order",
        "purchase-order-vendor-bill",
        "vendor-bill-stock-expense"
      ]
    };
    const categoryButtons = [...stage.querySelectorAll("[data-ct-category]")];
    const inspectorCategoryButtons = [...stage.querySelectorAll("[data-ct-inspector-category]")];

    function createEvidenceAccumulator(categoryOrder) {
      const state = {
        categoryCounts: Object.fromEntries(categoryOrder.map((category) => [category, null])),
        categoryAvailability: Object.fromEntries(categoryOrder.map((category) => [category, false])),
        processCounts: new Map(),
        rowsByCategory: new Map()
      };
      function reset() {
        categoryOrder.forEach((category) => {
          state.categoryCounts[category] = null;
          state.categoryAvailability[category] = false;
        });
        state.processCounts.clear();
        state.rowsByCategory.clear();
      }
      function ingest(category, payload) {
        state.categoryAvailability[category] = true;
        state.rowsByCategory.set(category, Array.isArray(payload?.rows) ? payload.rows : []);
        const counts = payload?.category_counts || {};
        categoryOrder.forEach((key) => {
          if (counts[key] !== undefined && counts[key] !== null) state.categoryCounts[key] = Number(counts[key]) || 0;
        });

        const items = Array.isArray(payload?.process_counts) ? payload.process_counts : [];
        items.forEach((item) => {
          const key = String(item?.process_key || "");
          if (!key) return;
          if (!state.processCounts.has(key)) state.processCounts.set(key, Object.fromEntries(categoryOrder.map((name) => [name, 0])));
          state.processCounts.get(key)[category] += Number(item?.count || 0);
        });
      }
      return { state, reset, ingest };
    }

    const evidence = createEvidenceAccumulator(categoryOrder);
    const categoryCounts = evidence.state.categoryCounts;
    const categoryAvailability = evidence.state.categoryAvailability;
    const processCounts = evidence.state.processCounts;
    const rowsByCategory = evidence.state.rowsByCategory;
    let selectedNode = null;
    let allEvidenceUnavailable = false;
    let routeAnimationRun = 0;
    let routeRunnerLayer = null;

    function formatCount(value) {
      return value === null || value === undefined || Number.isNaN(Number(value))
        ? "—"
        : Number(value).toLocaleString("id-ID");
    }

    function aliasesFor(processKey) {
      return processAliases[processKey] || [processKey];
    }

    function coverageForNode(node) {
      const processKey = node?.dataset.processKey || "";
      return processCoverage[processKey] || defaultCoverage;
    }

    function evidenceStateForNode(node) {
      const coverage = coverageForNode(node);
      if (coverage.state === "EXTERNAL_CONTEXT") return "external";
      if (coverage.state !== "MAPPED") return "not-mapped";
      const availableCount = categoryOrder.filter((category) => categoryAvailability[category]).length;
      if (availableCount === 0) return "unavailable";
      if (availableCount < categoryOrder.length) return "partial";
      return "mapped";
    }

    function coverageMessageForNode(node) {
      const coverage = coverageForNode(node);
      const state = evidenceStateForNode(node);
      if (coverage.message) return coverage.message;
      if (state === "unavailable") return "Data Temuan sedang tidak tersedia; status proses belum dapat dinilai.";
      if (state === "partial") return "Sebagian kategori Temuan tidak tersedia; angka yang tampil belum lengkap.";
      return "";
    }

    function processCount(processKey, category) {
      if (!categoryAvailability[category]) return null;
      const aliases = aliasesFor(processKey);
      return aliases.reduce((total, key) => total + Number(processCounts.get(key)?.[category] || 0), 0);
    }

    function countsForNode(node) {
      const processKey = node?.dataset.processKey || "";
      const coverage = coverageForNode(node);
      if (coverage.state !== "MAPPED") {
        return Object.fromEntries(categoryOrder.map((category) => [category, null]));
      }
      return Object.fromEntries(categoryOrder.map((category) => [category, processCount(processKey, category)]));
    }

    function setTemuanExpanded(expanded, persist = true) {
      temuan?.classList.toggle("is-collapsed", !expanded);
      temuanToggle?.setAttribute("aria-expanded", String(expanded));
      temuanToggle?.setAttribute("aria-label", expanded ? "Tutup ringkasan Temuan" : "Buka ringkasan Temuan");
      if (temuanToggle) temuanToggle.textContent = expanded ? "⌃" : "⌄";
      if (persist) {
        try { sessionStorage.setItem("ct-temuan-expanded", expanded ? "1" : "0"); } catch { /* optional */ }
      }
    }

    function categoryDestination(category, processKey = "") {
      const destination = new URL("/dashboard/control-tower/temuan", window.location.origin);
      destination.searchParams.set("presentation_category", category);
      if (processKey) {
        destination.searchParams.set("selected_process", processKey);
        destination.searchParams.set("process_key", processKey);
      }

      const returnUrl = new URL("/dashboard/control-tower", window.location.origin);
      if (processKey) returnUrl.searchParams.set("selected_process", processKey);
      destination.searchParams.set("return_to", `${returnUrl.pathname}${returnUrl.search}`);
      return `${destination.pathname}${destination.search}`;
    }

    function renderCategoryCounts() {
      categoryOrder.forEach((category) => {
        stage.querySelectorAll(`[data-ct-category-count="${category}"]`).forEach((element) => {
          element.textContent = formatCount(categoryCounts[category]);
        });
      });
      const activeSummary = stage.querySelector("[data-ct-active-summary]");
      if (activeSummary) activeSummary.textContent = allEvidenceUnavailable ? "—" : `${formatCount(categoryCounts.MASALAH_AKTIF)} aktif`;
    }

    function renderNodeSignals() {
      nodes.forEach((node) => {
        const holder = node.querySelector(".ct-node-signals");
        if (!holder) return;
        const counts = countsForNode(node);
        const state = evidenceStateForNode(node);
        const label = node.querySelector("strong")?.textContent || "Proses";
        node.dataset.evidenceState = state;
        holder.replaceChildren();
        if (["mapped", "partial"].includes(state)) {
          categoryOrder.forEach((category) => {
            if (counts[category] === null || counts[category] <= 0) return;
            const signal = document.createElement("span");
            signal.className = "ct-node-signal";
            signal.dataset.category = category;
            signal.title = `${categoryLabels[category]}: ${formatCount(counts[category])}`;
            holder.appendChild(signal);
          });
        }
        const stateDescription = state === "mapped"
          ? "Pemeriksaan tersedia."
          : state === "partial"
            ? "Sebagian data pemeriksaan tidak tersedia."
            : coverageMessageForNode(node);
        node.setAttribute("aria-label", `${label}. ${stateDescription}`.trim());
      });
    }

    function ingestPayload(category, payload) {
      evidence.ingest(category, payload);
    }

    async function fetchEvidenceCategory(category) {
      const query = new URLSearchParams({
        presentation_category: category,
        limit: "50",
        offset: "0"
      });
      const response = await fetch(`/api/control-tower/evidence?${query}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      });
      if (!response.ok) throw new Error(`Evidence ${category} gagal (${response.status}).`);
      return response.json();
    }

    function matchingRow(processKey) {
      const aliases = aliasesFor(processKey);
      for (const category of categoryOrder) {
        const rows = rowsByCategory.get(category) || [];
        const row = rows.find((candidate) => aliases.includes(candidate?.process_key));
        if (row) return { row, category };
      }
      return null;
    }

    function primarySignalFor(node, counts) {
      const state = evidenceStateForNode(node);
      if (["external", "not-mapped", "unavailable"].includes(state)) return coverageMessageForNode(node);
      const processKey = node.dataset.processKey;
      const match = matchingRow(processKey);
      if (match) {
        const row = match.row;
        return row.evidence_wording || row.summary || row.title || row.rule_name || row.rule_id || `${categoryLabels[match.category]} membutuhkan perhatian pada proses ini.`;
      }
      const priorityCategory = categoryOrder.find((category) => counts[category] !== null && counts[category] > 0);
      if (priorityCategory) return `${formatCount(counts[priorityCategory])} evidence ${categoryLabels[priorityCategory].toLowerCase()} terpetakan ke proses ini.`;
      if (state === "partial") return "Kategori yang tersedia tidak menunjukkan temuan, tetapi pemeriksaan belum lengkap karena sebagian data tidak tersedia.";
      return "Tidak ada temuan pada pemeriksaan yang saat ini sudah dipetakan ke proses ini.";
    }

    function routeNames(element) {
      return String(element?.dataset?.routes || "").split(/\s+/).filter(Boolean);
    }

    function animationRouteFor(node) {
      return String(node?.dataset?.routeFocus || routeNames(node)[0] || "").split(/\s+/).filter(Boolean)[0] || "";
    }

    function ensureRouteRunnerLayer() {
      if (!connectorSvg) return null;
      if (routeRunnerLayer?.isConnected) return routeRunnerLayer;
      routeRunnerLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
      routeRunnerLayer.classList.add("ct-route-runner-layer");
      routeRunnerLayer.setAttribute("aria-hidden", "true");
      connectorSvg.appendChild(routeRunnerLayer);
      return routeRunnerLayer;
    }

    function cancelRouteAnimation() {
      routeAnimationRun += 1;
      stage.classList.remove("is-route-animating");
      routeRunnerLayer?.replaceChildren();
    }

    function pointAtPathEnd(path, atEnd) {
      const length = path.getTotalLength();
      return path.getPointAtLength(atEnd ? length : 0);
    }

    function animateRunnerBetween(head, halo, from, to, duration, runId) {
      return new Promise((resolve) => {
        const startedAt = performance.now();
        function frame(now) {
          if (runId !== routeAnimationRun) return resolve(false);
          const progress = Math.min(1, (now - startedAt) / Math.max(duration, 1));
          const eased = progress < 0.5
            ? 2 * progress * progress
            : 1 - Math.pow(-2 * progress + 2, 2) / 2;
          const x = from.x + (to.x - from.x) * eased;
          const y = from.y + (to.y - from.y) * eased;
          head.setAttribute("cx", x.toFixed(2));
          head.setAttribute("cy", y.toFixed(2));
          halo.setAttribute("cx", x.toFixed(2));
          halo.setAttribute("cy", y.toFixed(2));
          if (progress < 1) requestAnimationFrame(frame);
          else resolve(true);
        }
        requestAnimationFrame(frame);
      });
    }

    function animateRunnerAlongPath(path, head, halo, duration, runId) {
      return new Promise((resolve) => {
        const length = path.getTotalLength();
        const startedAt = performance.now();
        function frame(now) {
          if (runId !== routeAnimationRun) return resolve(false);
          const progress = Math.min(1, (now - startedAt) / Math.max(duration, 1));
          const point = path.getPointAtLength(length * progress);
          head.setAttribute("cx", point.x.toFixed(2));
          head.setAttribute("cy", point.y.toFixed(2));
          halo.setAttribute("cx", point.x.toFixed(2));
          halo.setAttribute("cy", point.y.toFixed(2));
          if (progress < 1) requestAnimationFrame(frame);
          else resolve(true);
        }
        requestAnimationFrame(frame);
      });
    }

    async function animateRouteOnce(node) {
      cancelRouteAnimation();
      if (prefersReducedMotion || !connectorSvg || !node) return;

      const routeName = animationRouteFor(node);
      const edgeIds = routeAnimationSequences[routeName] || [];
      const paths = edgeIds
        .map((edgeId) => connectorSvg.querySelector(`[data-edge-id="${edgeId}"]`))
        .filter((path) => path instanceof SVGPathElement);
      if (!paths.length) return;

      const layer = ensureRouteRunnerLayer();
      if (!layer) return;
      const runId = routeAnimationRun;
      const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      const head = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      halo.classList.add("ct-route-runner-halo");
      halo.setAttribute("r", "10");
      head.classList.add("ct-route-runner-head");
      head.setAttribute("r", "5.5");
      layer.append(halo, head);
      stage.classList.add("is-route-animating");

      const speed = 520;
      let previousEnd = null;
      for (const path of paths) {
        if (runId !== routeAnimationRun) return;
        const start = pointAtPathEnd(path, false);
        if (previousEnd) {
          const gap = Math.hypot(start.x - previousEnd.x, start.y - previousEnd.y);
          if (gap > 1) {
            const crossed = await animateRunnerBetween(
              head,
              halo,
              previousEnd,
              start,
              Math.max(70, Math.min(220, gap / 0.9)),
              runId
            );
            if (!crossed) return;
          }
        }
        const length = path.getTotalLength();
        const completed = await animateRunnerAlongPath(
          path,
          head,
          halo,
          Math.max(90, (length / speed) * 1000),
          runId
        );
        if (!completed) return;
        previousEnd = pointAtPathEnd(path, true);
      }

      if (runId !== routeAnimationRun) return;
      layer.replaceChildren();
      stage.classList.remove("is-route-animating");
      const label = node.querySelector("strong")?.textContent || "Proses";
      if (mapStatus) mapStatus.textContent = `${label} dipilih. Animasi alur selesai; jalur tetap disorot untuk ditinjau.`;
    }

    function highlightRoute(node) {
      const selectedRoutes = String(node.dataset.routeFocus || routeNames(node)[0] || "").split(/\s+/).filter(Boolean);
      stage.classList.add("has-route-selection");
      routeElements.forEach((element) => {
        const active = routeNames(element).some((route) => selectedRoutes.includes(route));
        element.classList.toggle("is-route-active", active);
      });
      nodes.forEach((candidate) => candidate.classList.toggle("is-selected", candidate === node));
    }

    function clearRoute() {
      cancelRouteAnimation();
      stage.classList.remove("has-route-selection");
      routeElements.forEach((element) => element.classList.remove("is-route-active"));
      nodes.forEach((node) => node.classList.remove("is-selected"));
    }

    function ensureCoverageNote(container, className) {
      if (!container) return null;
      let note = container.querySelector(`.${className}`);
      if (!note) {
        note = document.createElement("p");
        note.className = className;
        note.hidden = true;
        if (className === "ct-evidence-coverage") container.prepend(note);
        else container.appendChild(note);
      }
      return note;
    }

    const previewCoverageNote = ensureCoverageNote(hoverPreview, "ct-preview-coverage");
    const inspectorCoverageNote = ensureCoverageNote(inspector?.querySelector(".ct-inspector-body"), "ct-evidence-coverage");
    const previewCountRows = [...(hoverPreview?.querySelectorAll(":scope > div") || [])];

    function renderPreview(node) {
      const counts = countsForNode(node);
      const state = evidenceStateForNode(node);
      if (previewTitle) previewTitle.textContent = node.querySelector("strong")?.textContent || "Proses";
      const showCounts = ["mapped", "partial"].includes(state);
      previewCountRows.forEach((row) => { row.hidden = !showCounts; });
      if (previewCoverageNote) {
        previewCoverageNote.hidden = showCounts;
        previewCoverageNote.textContent = showCounts ? "" : coverageMessageForNode(node);
        previewCoverageNote.dataset.state = state;
      }
      categoryOrder.forEach((category) => {
        const element = hoverPreview?.querySelector(`[data-ct-preview-count="${category}"]`);
        if (element) element.textContent = formatCount(counts[category]);
      });
    }

    function positionPreview(node) {
      if (!hoverPreview) return;
      const stageRect = stage.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      const previewWidth = 208;
      const previewHeight = hoverPreview.offsetHeight || 118;
      let left = nodeRect.right - stageRect.left + 10;
      let top = nodeRect.top - stageRect.top - 4;
      if (left + previewWidth > stage.clientWidth - 10) left = nodeRect.left - stageRect.left - previewWidth - 10;
      left = Math.max(10, Math.min(left, stage.clientWidth - previewWidth - 10));
      top = Math.max(10, Math.min(top, stage.clientHeight - previewHeight - 10));
      hoverPreview.style.left = `${left}px`;
      hoverPreview.style.top = `${top}px`;
    }

    function showPreview(node) {
      if (!hoverPreview || !node) return;
      renderPreview(node);
      hoverPreview.hidden = false;
      positionPreview(node);
    }

    function hidePreview() {
      if (hoverPreview) hoverPreview.hidden = true;
    }

    function openInspector(node, updateUrl = true, animateRoute = true) {
      selectedNode = node;
      const processKey = node.dataset.processKey;
      const label = node.querySelector("strong")?.textContent || "Proses";
      const counts = countsForNode(node);
      const evidenceState = evidenceStateForNode(node);
      const showCoverageNote = evidenceState !== "mapped";

      if (inspectorTitle) inspectorTitle.textContent = label;
      if (inspectorCoverageNote) {
        inspectorCoverageNote.hidden = !showCoverageNote;
        inspectorCoverageNote.textContent = showCoverageNote ? coverageMessageForNode(node) : "";
        inspectorCoverageNote.dataset.state = evidenceState;
      }
      categoryOrder.forEach((category) => {
        const count = counts[category];
        const value = inspector?.querySelector(`[data-ct-inspector-count="${category}"]`);
        const button = inspector?.querySelector(`[data-ct-inspector-category="${category}"]`);
        if (value) value.textContent = formatCount(count);
        if (button) button.disabled = count === null || count <= 0 || !["mapped", "partial"].includes(evidenceState);
      });
      if (primarySignal) primarySignal.textContent = primarySignalFor(node, counts);
      if (openDocuments) {
        const hasEvidence = ["mapped", "partial"].includes(evidenceState)
          && categoryOrder.some((category) => counts[category] !== null && counts[category] > 0);
        openDocuments.disabled = !hasEvidence;
        openDocuments.textContent = hasEvidence
          ? "Buka Temuan proses ini"
          : evidenceState === "unavailable"
            ? "Data Temuan tidak tersedia"
            : evidenceState === "mapped"
              ? "Tidak ada Temuan terpetakan"
              : "Belum ada filter proses";
      }

      highlightRoute(node);
      hidePreview();
      if (inspector) inspector.hidden = false;
      if (mapStatus) mapStatus.textContent = animateRoute && !prefersReducedMotion
        ? `${label} dipilih. Alur sedang berjalan dari awal hingga tujuan akhir.`
        : `${label} dipilih. Jalur terkait disorot; detail hanya menampilkan hal yang membutuhkan tindakan.`;
      if (animateRoute) void animateRouteOnce(node);

      if (updateUrl) {
        const url = new URL(window.location.href);
        url.searchParams.set("selected_process", processKey);
        url.searchParams.delete("selected_finding");
        history.replaceState({}, "", url);
      }
    }

    function closeInspector(updateUrl = true) {
      selectedNode = null;
      if (inspector) inspector.hidden = true;
      clearRoute();
      hidePreview();
      if (mapStatus) mapStatus.textContent = "Arahkan pointer ke node untuk ringkasan. Klik node untuk melihat tindakan yang relevan.";
      if (updateUrl) {
        const url = new URL(window.location.href);
        url.searchParams.delete("selected_process");
        url.searchParams.delete("selected_finding");
        history.replaceState({}, "", url);
      }
    }

    function navigateToCategory(category, processKey = "") {
      window.location.assign(categoryDestination(category, processKey));
    }

    function updateScrollCue() {
      if (!scrollCue || !mapScroll) return;
      const overflow = mapScroll.scrollWidth > mapScroll.clientWidth + 4;
      scrollCue.hidden = !overflow || mapScroll.scrollLeft > 12;
    }

    temuanToggle?.addEventListener("click", () => {
      const expanded = temuan?.classList.contains("is-collapsed") ?? true;
      setTemuanExpanded(expanded, true);
      if (mapStatus) mapStatus.textContent = expanded
        ? "Ringkasan Temuan dibuka. Pilih satu kategori untuk menuju daftar terfilter."
        : "Ringkasan Temuan ditutup agar Process Map tetap dominan.";
    });

    categoryButtons.forEach((button) => {
      button.addEventListener("click", () => navigateToCategory(button.dataset.ctCategory || "MASALAH_AKTIF"));
    });

    inspectorCategoryButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (!selectedNode || button.disabled) return;
        navigateToCategory(button.dataset.ctInspectorCategory || "MASALAH_AKTIF", selectedNode.dataset.processKey);
      });
    });

    openDocuments?.addEventListener("click", () => {
      if (!selectedNode || openDocuments.disabled) return;
      const counts = countsForNode(selectedNode);
      const category = categoryOrder.find((candidate) => counts[candidate] !== null && counts[candidate] > 0);
      if (category) navigateToCategory(category, selectedNode.dataset.processKey);
    });

    inspectorClose?.addEventListener("click", () => closeInspector(true));

    nodes.forEach((node) => {
      node.addEventListener("pointerenter", () => showPreview(node));
      node.addEventListener("pointerleave", hidePreview);
      node.addEventListener("focus", () => showPreview(node));
      node.addEventListener("blur", hidePreview);
      node.addEventListener("click", (event) => {
        event.stopPropagation();
        openInspector(node, true, true);
      });
    });

    stage.addEventListener("click", (event) => {
      if (!selectedNode) return;
      if (event.target.closest("[data-ct-process-node], [data-ct-inspector], [data-ct-temuan]")) return;
      closeInspector(true);
    });

    mapScroll?.addEventListener("scroll", () => {
      hidePreview();
      updateScrollCue();
    }, { passive: true });
    window.addEventListener("resize", updateScrollCue, { passive: true });

    let temuanExpanded = false;
    try { temuanExpanded = sessionStorage.getItem("ct-temuan-expanded") === "1"; } catch { temuanExpanded = false; }
    setTemuanExpanded(temuanExpanded, false);
    updateScrollCue();

    function loadEvidenceData(restoreSelection = false) {
      evidence.reset();
      return Promise.allSettled(categoryOrder.map(async (category) => {
        const payload = await fetchEvidenceCategory(category);
        ingestPayload(category, payload);
      })).then((results) => {
        allEvidenceUnavailable = categoryOrder.every((category) => !categoryAvailability[category]);
        if (allEvidenceUnavailable) {
          categoryOrder.forEach((category) => { categoryCounts[category] = null; });
          if (mapStatus) mapStatus.textContent = "Data temuan tidak tersedia. Process Map tetap dapat digunakan untuk orientasi proses.";
        }
        renderCategoryCounts();
        renderNodeSignals();
        if (restoreSelection && selectedNode) openInspector(selectedNode, false, false);
        return results;
      });
    }

    refreshReloadEvidence = () => loadEvidenceData(true);

    loadEvidenceData(false).then(() => {
      const requestedProcess = params.get("selected_process");
      const requestedNode = requestedProcess
        ? nodes.find((node) => aliasesFor(node.dataset.processKey).includes(requestedProcess) || node.dataset.processKey === requestedProcess)
        : null;
      if (requestedNode) openInspector(requestedNode, false, false);
    });
  }

  initImmersiveControlTower();
})();
