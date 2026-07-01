const DEFAULT_INTERNAL_ORDER = "426IO026";

const TAB_DEFS = [
  { key: "all", label: "All Lines", predicate: () => true },
  { key: "trackable", label: "Product Items", predicate: (row) => row.is_trackable_product === true },
  { key: "non_trackable", label: "Non-Product / Service Items", predicate: (row) => row.product_trackability_class !== "TRACKABLE_PRODUCT" },
  { key: "rkb_only", label: "RKB Only", predicate: (row) => row.product_presence_status === "RKB_ONLY" },
  { key: "rkb_rop_po", label: "RKB, ROP, and PO", predicate: (row) => row.product_presence_status === "RKB_ROP_PO" },
  { key: "rop_without_po", label: "ROP Without PO", predicate: (row) => row.rop_without_po_flag === true },
  { key: "po_without_rop", label: "PO Without ROP", predicate: (row) => row.po_without_rop_flag === true },
];

const TRACKABILITY_LABELS = {
  TRACKABLE_PRODUCT: "Product Item",
  NON_TRACKABLE_OTHERS: "Non-Product / Service Item",
  BUDGET_SERVICE_ADJUSTMENT: "Budget / Service Item",
  UNKNOWN_PRODUCT_CLASS: "Unclassified Item",
};

const PRESENCE_LABELS = {
  RKB_ONLY: "RKB Only",
  ROP_ONLY: "ROP Only",
  PO_ONLY: "PO Only",
  RKB_ROP: "RKB and ROP",
  RKB_PO: "RKB and PO",
  ROP_PO: "ROP and PO",
  RKB_ROP_PO: "RKB, ROP, and PO",
};

const CLASSIFICATION_REASON_LABELS = {
  BRACKETED_PRODUCT_CODE: "Product Code",
  DOUBLE_BANG_OTHERS: "Other Item",
  CONTAINS_OTHERS: "Other Item",
  BUDGET_SERVICE_TEXT: "Budget / Service Text",
  UNKNOWN_FALLBACK: "Unclassified",
};

function humanizeEnum(value) {
  if (!value) return "-";
  return String(value)
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function mappedLabel(labels, value) {
  return labels[value] || humanizeEnum(value);
}
const state = {
  payload: null,
  lines: [],
  activeTab: "all",
  loading: false,
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  loadButton: document.getElementById("loadButton"),
  internalOrderInput: document.getElementById("internalOrderInput"),
  loadStatus: document.getElementById("loadStatus"),
  errorBanner: document.getElementById("errorBanner"),
  warningPanel: document.getElementById("warningPanel"),
  warningList: document.getElementById("warningList"),
  kpiInternalOrderNumber: document.getElementById("kpiInternalOrderNumber"),
  kpiCompany: document.getElementById("kpiCompany"),
  kpiSalesOrderLink: document.getElementById("kpiSalesOrderLink"),
  kpiProductCount: document.getElementById("kpiProductCount"),
  kpiFullRkb: document.getElementById("kpiFullRkb"),
  kpiTrackableRkb: document.getElementById("kpiTrackableRkb"),
  kpiNonTrackableRkb: document.getElementById("kpiNonTrackableRkb"),
  kpiRopAmount: document.getElementById("kpiRopAmount"),
  kpiPoAmount: document.getElementById("kpiPoAmount"),
  kpiExcessRopAmount: document.getElementById("kpiExcessRopAmount"),
  kpiReceivedRatio: document.getElementById("kpiReceivedRatio"),
  kpiInvoicedRatio: document.getElementById("kpiInvoicedRatio"),
  trackabilitySummary: document.getElementById("trackabilitySummary"),
  presenceSummary: document.getElementById("presenceSummary"),
  trackabilityBreakdownBody: document.getElementById("trackabilityBreakdownBody"),
  presenceBreakdownBody: document.getElementById("presenceBreakdownBody"),
  tabBar: document.getElementById("tabBar"),
  lineCount: document.getElementById("lineCount"),
  tableSubtitle: document.getElementById("tableSubtitle"),
  tableMeta: document.getElementById("tableMeta"),
  lineTableBody: document.getElementById("lineTableBody"),
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[character]));
}

function safeText(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return escapeHtml(value);
}

function numberValue(value) {
  if (value === null || value === undefined || value === "") {
    return 0;
  }
  return Number(value);
}

function formatCount(value) {
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(numberValue(value));
}

function formatCompactNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const numeric = numberValue(value);
  const absolute = Math.abs(numeric);
  const units = [
    { value: 1000000000000, suffix: "T" },
    { value: 1000000000, suffix: "B" },
    { value: 1000000, suffix: "M" },
    { value: 1000, suffix: "K" },
  ];
  const unit = units.find((entry) => absolute >= entry.value);
  if (!unit) {
    return formatCount(numeric);
  }

  const scaled = numeric / unit.value;
  const decimals = Math.abs(scaled) >= 100 ? 0 : Math.abs(scaled) >= 10 ? 1 : 2;
  return `${scaled.toFixed(decimals).replace(/\.0+$|(?<=\.\d)0+$/, "")}${unit.suffix}`;
}

function formatCompactAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return `Rp ${formatCompactNumber(value)}`;
}
function formatQty(value) {
  const numeric = numberValue(value);
  const digits = Math.abs(numeric % 1) > 0 ? 2 : 0;
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(numeric);
}

function formatAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 2,
  }).format(numberValue(value));
}

function formatRatio(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  return `${(numberValue(value) * 100).toFixed(2)}%`;
}

function badge(label, className) {
  return `<span class="status-badge ${className}">${safeText(label)}</span>`;
}

function boolBadge(value) {
  return value ? badge("Linked to Sales Order", "status-complete") : badge("Pre-SO Internal Order", "status-muted");
}

function classForFlag(flag) {
  if (flag === "danger") return "flag-danger";
  if (flag === "warning") return "flag-warning";
  if (flag === "progress") return "flag-progress";
  return "flag-muted";
}

function flag(label, variant = "muted") {
  return `<span class="line-flag ${classForFlag(variant)}">${safeText(label)}</span>`;
}

function setLoading(isLoading) {
  state.loading = isLoading;
  els.loadButton.disabled = isLoading;
  els.refreshButton.disabled = isLoading;
  els.loadButton.textContent = isLoading ? "Loading..." : "Load Internal Order";
  els.loadStatus.textContent = isLoading ? "Loading data..." : "Ready";
}

function clearError() {
  els.errorBanner.hidden = true;
  els.errorBanner.textContent = "";
}

function showError(message) {
  els.errorBanner.textContent = message;
  els.errorBanner.hidden = false;
}

function clearEmptyState() {
  [
    els.kpiInternalOrderNumber,
    els.kpiCompany,
    els.kpiSalesOrderLink,
    els.kpiProductCount,
    els.kpiFullRkb,
    els.kpiTrackableRkb,
    els.kpiNonTrackableRkb,
    els.kpiRopAmount,
    els.kpiPoAmount,
    els.kpiExcessRopAmount,
    els.kpiReceivedRatio,
    els.kpiInvoicedRatio,
  ].forEach((element) => {
    element.textContent = "-";
    element.innerHTML = "-";
  });
  els.trackabilitySummary.textContent = "-";
  els.presenceSummary.textContent = "-";
  els.trackabilityBreakdownBody.innerHTML = '<tr><td colspan="7" class="empty-cell">Loading breakdown...</td></tr>';
  els.presenceBreakdownBody.innerHTML = '<tr><td colspan="5" class="empty-cell">Loading breakdown...</td></tr>';
  els.lineTableBody.innerHTML = '<tr><td colspan="15" class="empty-cell">Loading Internal Order data...</td></tr>';
  els.tableSubtitle.textContent = "Loading Internal Order...";
  els.tableMeta.textContent = "-";
  els.lineCount.textContent = "- lines";
  els.warningPanel.hidden = true;
  els.warningList.innerHTML = "";
}

function renderWarnings(summary, metadata) {
  const warnings = Array.isArray(metadata?.warnings) ? metadata.warnings : [];
  if (!warnings.length) {
    els.warningPanel.hidden = true;
    els.warningList.innerHTML = "";
    return;
  }
  els.warningPanel.hidden = false;
  els.warningList.innerHTML = warnings.map((warning) => `<li>${safeText(warning)}</li>`).join("");
}

function renderSummary(summary, metadata) {
  els.kpiInternalOrderNumber.textContent = safeText(summary.internal_order_number);
  els.kpiCompany.textContent = safeText(summary.company_name);
  els.kpiSalesOrderLink.innerHTML = boolBadge(summary.has_sales_order_link);
  els.kpiProductCount.textContent = formatCompactNumber(summary.product_count);
  els.kpiFullRkb.textContent = formatCompactAmount(summary.rkb_actual_amount);
  els.kpiTrackableRkb.textContent = formatCompactAmount(summary.rkb_actual_trackable_amount);
  els.kpiNonTrackableRkb.textContent = formatCompactAmount(summary.rkb_actual_non_trackable_amount);
  els.kpiRopAmount.textContent = formatCompactAmount(summary.rop_amount);
  els.kpiPoAmount.textContent = formatCompactAmount(summary.po_amount);
  els.kpiExcessRopAmount.textContent = formatCompactAmount(summary.excess_rop_amount);
  els.kpiReceivedRatio.textContent = formatRatio(summary.received_ratio);
  els.kpiInvoicedRatio.textContent = formatRatio(summary.invoiced_ratio);

  const infoBits = [summary.comparison_basis, summary.summary_scope, metadata?.generated_at].filter(Boolean);
  els.tableSubtitle.textContent = infoBits.join(" | ");
  els.tableMeta.textContent = metadata?.line_count !== undefined ? `${formatCount(metadata.line_count)} lines` : "-";
}

function renderTrackabilityBreakdown(rows) {
  if (!rows.length) {
    els.trackabilityBreakdownBody.innerHTML = '<tr><td colspan="7" class="empty-cell">No breakdown rows.</td></tr>';
    els.trackabilitySummary.textContent = "0 groups";
    return;
  }

  els.trackabilitySummary.textContent = `${formatCount(rows.length)} groups`;
  els.trackabilityBreakdownBody.innerHTML = rows.map((row) => `
    <tr>
      <td>${safeText(mappedLabel(TRACKABILITY_LABELS, row.product_trackability_class))}</td>
      <td>${safeText(mappedLabel(CLASSIFICATION_REASON_LABELS, row.product_classification_reason))}</td>
      <td>${row.is_trackable_product ? badge("Yes", "status-complete") : badge("No", "status-muted")}</td>
      <td class="num">${formatCount(row.product_count)}</td>
      <td class="num">${formatAmount(row.rkb_actual_amount)}</td>
      <td class="num">${formatAmount(row.rop_amount)}</td>
      <td class="num">${formatAmount(row.po_amount)}</td>
    </tr>
  `).join("");
}

function renderPresenceBreakdown(rows) {
  if (!rows.length) {
    els.presenceBreakdownBody.innerHTML = '<tr><td colspan="5" class="empty-cell">No breakdown rows.</td></tr>';
    els.presenceSummary.textContent = "0 groups";
    return;
  }

  els.presenceSummary.textContent = `${formatCount(rows.length)} groups`;
  els.presenceBreakdownBody.innerHTML = rows.map((row) => `
    <tr>
      <td>${safeText(mappedLabel(PRESENCE_LABELS, row.product_presence_status))}</td>
      <td class="num">${formatCount(row.product_count)}</td>
      <td class="num">${formatAmount(row.rkb_actual_amount)}</td>
      <td class="num">${formatAmount(row.rop_amount)}</td>
      <td class="num">${formatAmount(row.po_amount)}</td>
    </tr>
  `).join("");
}

function matchesTab(row, tabKey) {
  const tab = TAB_DEFS.find((entry) => entry.key === tabKey) || TAB_DEFS[0];
  return tab.predicate(row);
}

function activeLines() {
  return state.lines.filter((row) => matchesTab(row, state.activeTab));
}

function renderTabs() {
  const buttons = TAB_DEFS.map((tab) => {
    const count = state.lines.filter((row) => tab.predicate(row)).length;
    const active = tab.key === state.activeTab ? "active" : "";
    return `<button class="tab-button ${active}" type="button" data-tab="${tab.key}"><span>${escapeHtml(tab.label)}</span><strong>${formatCount(count)}</strong></button>`;
  });
  els.tabBar.innerHTML = buttons.join("");
}

function renderLineFlags(row) {
  const flags = [];
  if (row.po_without_rop_flag) flags.push(flag("PO Without ROP", "danger"));
  if (row.rop_without_po_flag) flags.push(flag("ROP Without PO", "danger"));
  if (row.product_trackability_class !== "TRACKABLE_PRODUCT") flags.push(flag("Non-Product / Service", "muted"));
  return flags.length ? `<div class="line-flags">${flags.join("")}</div>` : "-";
}

function renderLines() {
  const rows = activeLines();
  const total = state.lines.length;
  els.lineCount.textContent = `${formatCount(rows.length)} / ${formatCount(total)} lines`;

  if (!rows.length) {
    els.lineTableBody.innerHTML = '<tr><td colspan="15" class="empty-cell">No Internal Order lines match the selected tab.</td></tr>';
    return;
  }

  els.lineTableBody.innerHTML = rows.map((row) => `
    <tr>
      <td>${safeText(row.product_key)}</td>
      <td>${safeText(row.product_name)}</td>
      <td>${badge(mappedLabel(TRACKABILITY_LABELS, row.product_trackability_class), row.is_trackable_product ? "status-complete" : "status-muted")}</td>
      <td>${badge(mappedLabel(PRESENCE_LABELS, row.product_presence_status), row.product_presence_status === "RKB_ROP_PO" ? "status-complete" : "status-progress")}</td>
      <td>${safeText(row.uom_summary)}</td>
      <td class="num">${formatQty(row.rkb_actual_qty)}</td>
      <td class="num">${formatAmount(row.rkb_actual_subtotal)}</td>
      <td class="num">${formatQty(row.rop_qty)}</td>
      <td class="num">${formatAmount(row.rop_subtotal)}</td>
      <td class="num">${formatQty(row.po_qty)}</td>
      <td class="num">${formatAmount(row.po_subtotal)}</td>
      <td class="num">${formatQty(row.po_received_qty)}</td>
      <td class="num">${formatQty(row.po_invoiced_qty)}</td>
      <td class="num">${formatAmount(row.excess_rop_amount)}</td>
      <td>${renderLineFlags(row)}</td>
    </tr>
  `).join("");
}

function renderDashboard() {
  if (!state.payload) {
    renderTabs();
    renderLines();
    return;
  }

  const summary = state.payload.summary || {};
  const metadata = state.payload.metadata || {};
  renderWarnings(summary, metadata);
  renderSummary(summary, metadata);
  renderTrackabilityBreakdown(state.payload.breakdowns?.by_trackability_class || []);
  renderPresenceBreakdown(state.payload.breakdowns?.by_product_presence_status || []);
  renderTabs();
  renderLines();
}

async function loadDashboard(internalOrderNumber) {
  const normalized = (internalOrderNumber || "").trim();
  if (!normalized) {
    showError("internal_order_number is required.");
    return;
  }

  setLoading(true);
  clearError();

  try {
    const params = new URLSearchParams({ internal_order_number: normalized });
    const response = await fetch(`/api/dashboard/internal-order-rekap?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload?.detail?.error || payload?.detail || payload?.message || `Request failed: ${response.status}`;
      throw new Error(message);
    }

    state.payload = payload;
    state.lines = Array.isArray(payload.lines) ? payload.lines : [];
    state.activeTab = "all";
    renderDashboard();
    history.replaceState({}, "", `${location.pathname}?internal_order_number=${encodeURIComponent(normalized)}`);
    els.loadStatus.textContent = `Loaded ${normalized}`;
  } catch (error) {
    state.payload = null;
    state.lines = [];
    clearEmptyState();
    renderTabs();
    renderLines();
    showError(error.message || "Failed to load Internal Order Rekap data.");
    els.loadStatus.textContent = "Failed to load";
  } finally {
    setLoading(false);
  }
}

function activeTabLabel() {
  return (TAB_DEFS.find((entry) => entry.key === state.activeTab) || TAB_DEFS[0]).label;
}

els.tabBar.addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (!button) return;
  state.activeTab = button.dataset.tab || "all";
  renderTabs();
  renderLines();
});

els.loadButton.addEventListener("click", () => loadDashboard(els.internalOrderInput.value));
els.refreshButton.addEventListener("click", () => loadDashboard(els.internalOrderInput.value));
els.internalOrderInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadDashboard(els.internalOrderInput.value);
  }
});

const initialInternalOrder = new URLSearchParams(location.search).get("internal_order_number") || DEFAULT_INTERNAL_ORDER;
els.internalOrderInput.value = initialInternalOrder;
renderDashboard();
loadDashboard(initialInternalOrder);
