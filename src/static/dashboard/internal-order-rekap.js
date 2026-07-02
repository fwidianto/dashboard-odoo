const DEFAULT_INTERNAL_ORDER = "426IO026";
const DEFAULT_PERSPECTIVE = "internal_order";

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

const CARD_FILTER_DEFS = [
  { key: "all", label: "All Lines", predicate: () => true },
  { key: "trackable", label: "Product Items", predicate: (row) => row.is_trackable_product === true },
  { key: "non_trackable", label: "Non-Product / Service Items", predicate: (row) => row.product_trackability_class !== "TRACKABLE_PRODUCT" },
  { key: "rop_amount", label: "ROP Amount", predicate: (row) => numberValue(row.rop_qty) > 0 || Math.abs(numberValue(row.rop_subtotal)) > 0 },
  { key: "po_amount", label: "PO Amount", predicate: (row) => numberValue(row.po_qty) > 0 || Math.abs(numberValue(row.po_subtotal)) > 0 },
  { key: "excess_rop_amount", label: "ROP Excess Amount", predicate: (row) => Math.abs(numberValue(row.excess_rop_amount)) > 0 },
  { key: "po_excess_amount", label: "PO Excess Amount", predicate: (row) => Math.abs(numberValue(row.po_excess_amount)) > 0 },
  { key: "po_received_ratio", label: "PO Received Ratio", predicate: (row) => numberValue(row.po_qty) > 0 || numberValue(row.po_received_qty) > 0 },
  { key: "po_invoiced_ratio", label: "PO Invoiced Ratio", predicate: (row) => numberValue(row.po_qty) > 0 || numberValue(row.po_invoiced_qty) > 0 },
];

const FILTER_DEFS = [...TAB_DEFS, ...CARD_FILTER_DEFS];

const ITEM_TYPE_OPTIONS = [
  { value: "all", label: "All Item Types" },
  { value: "TRACKABLE_PRODUCT", label: "Product Item" },
  { value: "NON_TRACKABLE_OTHERS", label: "Non-Product / Service Item" },
  { value: "BUDGET_SERVICE_ADJUSTMENT", label: "Budget / Service Item" },
  { value: "UNKNOWN_PRODUCT_CLASS", label: "Unclassified Item" },
];

const MATERIAL_STATUS_OPTIONS = [
  { value: "all", label: "All Material Statuses" },
  { value: "RKB Only", label: "RKB Only" },
  { value: "ROP Created", label: "ROP Created" },
  { value: "PO Created", label: "PO Created" },
  { value: "Partially Received", label: "Partially Received" },
  { value: "Fully Received", label: "Fully Received" },
  { value: "Needs Review", label: "Needs Review" },
  { value: "From Stock", label: "From Stock" },
];

const SALES_ORDER_STATUS_OPTIONS = [
  { value: "all", label: "All Sales Order Statuses" },
  { value: "linked", label: "Linked" },
  { value: "pre_so", label: "Pre-SO" },
];

const PRESENCE_STATUS_OPTIONS = [
  { value: "all", label: "All Presence States" },
  { value: "RKB_ONLY", label: "RKB Only" },
  { value: "ROP_ONLY", label: "ROP Only" },
  { value: "PO_ONLY", label: "PO Only" },
  { value: "RKB_ROP", label: "RKB and ROP" },
  { value: "RKB_PO", label: "RKB and PO" },
  { value: "ROP_PO", label: "ROP and PO" },
  { value: "RKB_ROP_PO", label: "RKB, ROP, and PO" },
];

const SOURCE_PATH_LABELS = {
  INTERNAL_ORDER: "Internal Order",
  LINKED_INTERNAL_ORDER: "Linked IO",
  DIRECT_SALES_ORDER: "Direct SO / JO",
  FROM_STOCK: "From Stock",
  UNKNOWN_SOURCE: "Needs Review",
};

const CLASSIFICATION_REASON_LABELS = {
  BRACKETED_PRODUCT_CODE: "Product Code",
  DOUBLE_BANG_OTHERS: "Other Item",
  CONTAINS_OTHERS: "Other Item",
  BUDGET_SERVICE_TEXT: "Budget / Service Text",
  UNKNOWN_FALLBACK: "Unclassified",
};

const COLUMN_VISIBILITY_STORAGE_KEY = "orderMaterialTracking.visibleColumns.v1";
const DEFAULT_VISIBLE_COLUMNS = [
  "internal_order_number",
  "source_path",
  "sales_order_status",
  "linked_sales_order",
  "product_name",
  "item_type",
  "material_status",
  "rkb_request",
  "rkb_amount",
  "rop_request",
  "rop_amount",
  "related_po",
  "po_amount",
  "received_qty",
  "receipt_status",
];
const TABLE_COLUMNS = [
  { key: "internal_order_number", label: "Internal Order", defaultVisible: true },
  { key: "source_path", label: "Source Path", defaultVisible: true },
  { key: "sales_order_status", label: "Sales Order Status", defaultVisible: true },
  { key: "linked_sales_order", label: "Linked Sales Order", defaultVisible: true },
  { key: "rkb_request", label: "RKB Number", defaultVisible: true },
  { key: "rop_request", label: "ROP / Approval Number", defaultVisible: true },
  { key: "related_po", label: "Related PO Number", defaultVisible: true },
  { key: "product_name", label: "Product Name", defaultVisible: true },
  { key: "item_type", label: "Item Type", defaultVisible: true },
  { key: "material_status", label: "Material Status", defaultVisible: true },
  { key: "uom", label: "UoM", defaultVisible: false },
  { key: "rkb_qty", label: "RKB Qty", defaultVisible: false },
  { key: "rkb_amount", label: "RKB Amount", defaultVisible: true },
  { key: "rop_qty", label: "ROP Qty", defaultVisible: false },
  { key: "rop_amount", label: "ROP Amount", defaultVisible: true },
  { key: "po_qty", label: "PO Qty", defaultVisible: false },
  { key: "po_amount", label: "PO Amount", defaultVisible: true },
  { key: "received_qty", label: "Received Qty", defaultVisible: true },
  { key: "invoiced_qty", label: "Invoiced Qty", defaultVisible: false },
  { key: "flags", label: "Flags", defaultVisible: true },
];

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
  perspective: DEFAULT_PERSPECTIVE,
  filters: {
    tab: "all",
    card: "all",
    itemType: "all",
    materialStatus: "all",
    salesOrderStatus: "all",
    presenceStatus: "all",
    flags: {
      po_without_rop: false,
      rop_without_po: false,
      mixed_uom: false,
      non_trackable: false,
    },
  },
  sort: {
    key: null,
    direction: "asc",
  },
  loading: false,
  visibleColumns: new Set(DEFAULT_VISIBLE_COLUMNS),
  columnsPanelOpen: false,
};

const els = {
  pageTitle: document.getElementById("pageTitle"),
  pageSubtitle: document.getElementById("pageSubtitle"),
  refreshButton: document.getElementById("refreshButton"),
  loadButton: document.getElementById("loadButton"),
  internalOrderInput: document.getElementById("internalOrderInput"),
  searchInputLabel: document.getElementById("searchInputLabel"),
  perspectiveInputs: Array.from(document.querySelectorAll('input[name="rekapPerspective"]')),
  perspectiveContextNote: document.getElementById("perspectiveContextNote"),
  loadStatus: document.getElementById("loadStatus"),
  errorBanner: document.getElementById("errorBanner"),
  warningPanel: document.getElementById("warningPanel"),
  warningList: document.getElementById("warningList"),
  kpiPrimaryLabel: document.getElementById("kpiPrimaryLabel"),
  kpiInternalOrderNumber: document.getElementById("kpiInternalOrderNumber"),
  kpiCompany: document.getElementById("kpiCompany"),
  kpiLinkStatusLabel: document.getElementById("kpiLinkStatusLabel"),
  kpiSalesOrderLink: document.getElementById("kpiSalesOrderLink"),
  kpiProductCountLabel: document.getElementById("kpiProductCountLabel"),
  kpiProductCount: document.getElementById("kpiProductCount"),
  kpiIoReferenceLabel: document.getElementById("kpiIoReferenceLabel"),
  kpiIoReferenceAmount: document.getElementById("kpiIoReferenceAmount"),
  kpiFullRkb: document.getElementById("kpiFullRkb"),
  kpiRkbKontribusiLabel: document.getElementById("kpiRkbKontribusiLabel"),
  kpiRkbKontribusi: document.getElementById("kpiRkbKontribusi"),
  kpiRkbKontribusiPctLabel: document.getElementById("kpiRkbKontribusiPctLabel"),
  kpiRkbKontribusiPct: document.getElementById("kpiRkbKontribusiPct"),
  kpiTrackableRkb: document.getElementById("kpiTrackableRkb"),
  kpiNonTrackableRkb: document.getElementById("kpiNonTrackableRkb"),
  kpiRopAmount: document.getElementById("kpiRopAmount"),
  kpiPoAmount: document.getElementById("kpiPoAmount"),
  kpiExcessRopAmount: document.getElementById("kpiExcessRopAmount"),
  kpiPoExcessAmount: document.getElementById("kpiPoExcessAmount"),
  kpiReceivedRatio: document.getElementById("kpiReceivedRatio"),
  kpiInvoicedRatio: document.getElementById("kpiInvoicedRatio"),
  kpiGrid: document.querySelector(".kpi-grid-io"),
  clearFilterButton: document.getElementById("clearFilterButton"),
  clearSortButton: document.getElementById("clearSortButton"),
  activeFilterLabel: document.getElementById("activeFilterLabel"),
  itemTypeFilter: document.getElementById("itemTypeFilter"),
  materialStatusFilter: document.getElementById("materialStatusFilter"),
  salesOrderStatusFilter: document.getElementById("salesOrderStatusFilter"),
  presenceStatusFilter: document.getElementById("presenceStatusFilter"),
  trackabilitySummary: document.getElementById("trackabilitySummary"),
  presenceSummary: document.getElementById("presenceSummary"),
  trackabilityBreakdownBody: document.getElementById("trackabilityBreakdownBody"),
  presenceBreakdownBody: document.getElementById("presenceBreakdownBody"),
  tabBar: document.getElementById("tabBar"),
  lineCount: document.getElementById("lineCount"),
  tableSubtitle: document.getElementById("tableSubtitle"),
  tableMeta: document.getElementById("tableMeta"),
  columnsButton: document.getElementById("columnsButton"),
  columnsPanel: document.getElementById("columnsPanel"),
  columnsList: document.getElementById("columnsList"),
  columnsShowAllButton: document.getElementById("columnsShowAllButton"),
  columnsResetButton: document.getElementById("columnsResetButton"),
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

function formatIndonesianCompactNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  const numeric = numberValue(value);
  const absolute = Math.abs(numeric);
  const units = [
    { value: 1000000000000, suffix: " Triliun" },
    { value: 1000000000, suffix: " Miliar" },
    { value: 1000000, suffix: " Juta" },
    { value: 1000, suffix: " Ribu" },
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
  return `Rp ${formatIndonesianCompactNumber(value)}`;
}

function formatCompactAmountOrNA(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  return formatCompactAmount(value);
}

function formatReceiptStatus(row) {
  const received = numberValue(row.po_received_qty);
  const ordered = numberValue(row.po_qty);
  if (ordered > 0 && received >= ordered) return "Fully Received";
  if (received > 0) return "Partially Received";
  return ordered > 0 ? "PO Created" : "-";
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
    return "-";
  }
  return `${(numberValue(value) * 100).toFixed(2)}%`;
}

function badge(label, className) {
  return `<span class="status-badge ${className}">${safeText(label)}</span>`;
}

function boolBadge(value) {
  return value ? badge("Linked to Sales Order", "status-complete") : badge("Pre-SO Internal Order", "status-muted");
}

function currentPerspective() {
  return state.perspective === "sales_order" ? "sales_order" : "internal_order";
}

function perspectiveLabel() {
  return currentPerspective() === "sales_order" ? "Sales Order" : "Internal Order";
}

function updatePerspectiveUI() {
  const isSalesOrder = currentPerspective() === "sales_order";
  if (els.pageTitle) els.pageTitle.textContent = isSalesOrder ? "Order Material Tracking - Sales Order Perspective" : "Internal Order Rekap";
  if (els.pageSubtitle) {
    els.pageSubtitle.textContent = isSalesOrder
      ? "Related material/procurement chain from linked Internal Orders"
      : "RKB Actual vs ROP vs PO reconciliation";
  }
  if (els.searchInputLabel) els.searchInputLabel.textContent = isSalesOrder ? "Sales Order Number" : "Internal Order Number";
  if (els.internalOrderInput) {
    els.internalOrderInput.placeholder = isSalesOrder ? "Enter Sales Order number" : "Enter Internal Order number";
  }
  if (els.loadButton && !state.loading) els.loadButton.textContent = isSalesOrder ? "Load Sales Order" : "Load Internal Order";
  if (els.perspectiveContextNote) els.perspectiveContextNote.hidden = !isSalesOrder;
  els.perspectiveInputs.forEach((input) => {
    input.checked = input.value === currentPerspective();
  });
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
  els.loadButton.textContent = isLoading ? "Loading..." : `Load ${perspectiveLabel()}`;
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
    els.kpiIoReferenceAmount,
    els.kpiFullRkb,
    els.kpiRkbKontribusi,
    els.kpiRkbKontribusiPct,
    els.kpiTrackableRkb,
    els.kpiNonTrackableRkb,
    els.kpiRopAmount,
    els.kpiPoAmount,
    els.kpiExcessRopAmount,
    els.kpiPoExcessAmount,
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
  els.lineTableBody.innerHTML = makeTableEmptyRow("Loading data...");
  els.tableSubtitle.textContent = `Loading ${perspectiveLabel()}...`;
  els.tableMeta.textContent = "-";
  els.lineCount.textContent = "- lines";
  els.warningPanel.hidden = true;
  els.warningList.innerHTML = "";
}

function resetInteractiveState() {
  state.filters = {
    tab: "all",
    card: "all",
    itemType: "all",
    materialStatus: "all",
    salesOrderStatus: "all",
    presenceStatus: "all",
    flags: {
      po_without_rop: false,
      rop_without_po: false,
      mixed_uom: false,
      non_trackable: false,
    },
  };
  state.sort = {
    key: null,
    direction: "asc",
  };
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
  const isSalesOrder = currentPerspective() === "sales_order";
  if (els.kpiPrimaryLabel) els.kpiPrimaryLabel.textContent = isSalesOrder ? "Sales Order Number" : "Internal Order Number";
  if (els.kpiLinkStatusLabel) els.kpiLinkStatusLabel.textContent = isSalesOrder ? "Linked Internal Orders" : "Sales Order Link Status";
  if (els.kpiIoReferenceLabel) els.kpiIoReferenceLabel.textContent = isSalesOrder ? "Sales Order Amount" : "IO Reference Amount";
  if (els.kpiRkbKontribusiLabel) els.kpiRkbKontribusiLabel.textContent = isSalesOrder ? "SO RKB Kontribusi" : "RKB Kontribusi";
  if (els.kpiRkbKontribusiPctLabel) els.kpiRkbKontribusiPctLabel.textContent = isSalesOrder ? "SO RKB Kontribusi %" : "RKB Kontribusi %";
  if (els.kpiProductCountLabel) els.kpiProductCountLabel.textContent = isSalesOrder ? "Material Chain Rows" : "Product Count";

  els.kpiInternalOrderNumber.textContent = isSalesOrder
    ? safeText(metadata?.selected_sales_order_number || state.payload?.sales_order_number)
    : safeText(summary.internal_order_number);
  els.kpiCompany.textContent = safeText(summary.company_name);
  if (isSalesOrder) {
    const linkedCount = numberValue(metadata?.linked_internal_order_count);
    const directCount = numberValue(metadata?.direct_sales_order_chain_count) + numberValue(metadata?.from_stock_chain_count);
    if (linkedCount > 0 && directCount > 0) {
      els.kpiSalesOrderLink.innerHTML = badge(`${formatCount(linkedCount)} Linked IO + ${formatCount(directCount)} Direct Rows`, "status-progress");
    } else if (linkedCount > 0) {
      els.kpiSalesOrderLink.innerHTML = badge(`${formatCount(linkedCount)} Linked IO`, "status-progress");
    } else if (directCount > 0) {
      els.kpiSalesOrderLink.innerHTML = badge(`${formatCount(directCount)} Direct Rows`, "status-progress");
    } else {
      els.kpiSalesOrderLink.innerHTML = badge("No Material Chain", "status-muted");
    }
  } else {
    els.kpiSalesOrderLink.innerHTML = boolBadge(summary.has_sales_order_link);
  }
  els.kpiProductCount.textContent = formatCount(summary.product_count);
  [els.kpiIoReferenceAmount, els.kpiRkbKontribusi, els.kpiRkbKontribusiPct].forEach((element) => {
    if (element?.closest) element.closest(".kpi-card").hidden = false;
  });
  const primaryAmount = isSalesOrder ? summary.sales_order_amount : summary.io_reference_amount;
  const kontribusiAmount = isSalesOrder ? summary.so_rkb_kontribusi : summary.rkb_kontribusi;
  const kontribusiPct = isSalesOrder ? summary.so_rkb_kontribusi_pct : summary.rkb_kontribusi_pct;
  els.kpiIoReferenceAmount.textContent = formatCompactAmountOrNA(primaryAmount);
  els.kpiFullRkb.textContent = formatCompactAmount(summary.rkb_actual_amount);
  els.kpiRkbKontribusi.textContent = formatCompactAmountOrNA(kontribusiAmount);
  els.kpiRkbKontribusiPct.textContent = formatRatio(kontribusiPct);
  els.kpiTrackableRkb.textContent = formatCompactAmount(summary.rkb_actual_trackable_amount);
  els.kpiNonTrackableRkb.textContent = formatCompactAmount(summary.rkb_actual_non_trackable_amount);
  els.kpiRopAmount.textContent = formatCompactAmount(summary.rop_amount);
  els.kpiPoAmount.textContent = formatCompactAmount(summary.po_amount);
  els.kpiExcessRopAmount.textContent = formatCompactAmount(summary.excess_rop_amount);
  els.kpiPoExcessAmount.textContent = formatCompactAmount(summary.po_excess_amount);
  els.kpiReceivedRatio.textContent = formatRatio(summary.received_ratio);
  els.kpiInvoicedRatio.textContent = formatRatio(summary.invoiced_ratio);

  const linkedIoText = isSalesOrder && metadata?.linked_internal_order_numbers
    ? `Linked IO: ${metadata.linked_internal_order_numbers}`
    : null;
  const directText = isSalesOrder && (numberValue(metadata?.direct_sales_order_chain_count) > 0 || numberValue(metadata?.from_stock_chain_count) > 0)
    ? `Direct SO/JO rows: ${formatCount(numberValue(metadata.direct_sales_order_chain_count) + numberValue(metadata.from_stock_chain_count))}`
    : null;
  const infoBits = [linkedIoText, directText, summary.comparison_basis, summary.summary_scope, metadata?.generated_at, activeFilterSummary()].filter(Boolean);
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

function getColumnConfig(columnKey) {
  return TABLE_COLUMNS.find((column) => column.key === columnKey);
}

function loadVisibleColumns() {
  try {
    const raw = localStorage.getItem(COLUMN_VISIBILITY_STORAGE_KEY);
    if (!raw) return new Set(DEFAULT_VISIBLE_COLUMNS);
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set(DEFAULT_VISIBLE_COLUMNS);
    const allowed = new Set(TABLE_COLUMNS.map((column) => column.key));
    const cleaned = parsed.filter((value) => allowed.has(value));
    return new Set(cleaned.length ? cleaned : DEFAULT_VISIBLE_COLUMNS);
  } catch {
    return new Set(DEFAULT_VISIBLE_COLUMNS);
  }
}

function persistVisibleColumns() {
  localStorage.setItem(COLUMN_VISIBILITY_STORAGE_KEY, JSON.stringify([...state.visibleColumns]));
}

function isColumnVisible(columnKey) {
  return state.visibleColumns.has(columnKey);
}

function applyColumnVisibility() {
  TABLE_COLUMNS.forEach((column) => {
    const visible = isColumnVisible(column.key);
    document.querySelectorAll(`[data-column-key="${column.key}"]`).forEach((element) => {
      element.hidden = !visible;
    });
  });
  if (els.columnsList) {
    els.columnsList.querySelectorAll('input[data-column-toggle]').forEach((input) => {
      input.checked = isColumnVisible(input.dataset.columnToggle);
    });
  }
}

function setVisibleColumns(keys) {
  state.visibleColumns = new Set(keys.filter((key) => getColumnConfig(key)));
  if (!state.visibleColumns.size) {
    state.visibleColumns = new Set(DEFAULT_VISIBLE_COLUMNS);
  }
  persistVisibleColumns();
  applyColumnVisibility();
}

function resetVisibleColumnsToDefault() {
  setVisibleColumns(DEFAULT_VISIBLE_COLUMNS);
}

function showAllColumns() {
  setVisibleColumns(TABLE_COLUMNS.map((column) => column.key));
}

function renderColumnControls() {
  if (!els.columnsList) return;
  els.columnsList.innerHTML = TABLE_COLUMNS.map((column) => `
    <label class="column-toggle">
      <input type="checkbox" data-column-toggle="${column.key}" ${isColumnVisible(column.key) ? 'checked' : ''}>
      <span>${escapeHtml(column.label)}</span>
    </label>
  `).join('');
  applyColumnVisibility();
}

function toggleColumnsPanel(force) {
  state.columnsPanelOpen = typeof force === 'boolean' ? force : !state.columnsPanelOpen;
  if (els.columnsPanel) els.columnsPanel.hidden = !state.columnsPanelOpen;
  if (els.columnsButton) els.columnsButton.setAttribute('aria-expanded', String(state.columnsPanelOpen));
}

function updateColumnsButtonLabel() {
  if (!els.columnsButton) return;
  els.columnsButton.textContent = `Columns (${state.visibleColumns.size})`;
}

function columnsClickOutside(event) {
  if (!state.columnsPanelOpen) return;
  if (!els.columnsPanel || !els.columnsButton) return;
  if (els.columnsPanel.contains(event.target) || els.columnsButton.contains(event.target)) return;
  toggleColumnsPanel(false);
}

function handleColumnsChange(event) {
  const toggle = event.target.closest('[data-column-toggle]');
  if (!toggle) return;
  const key = toggle.dataset.columnToggle;
  if (!key) return;
  if (toggle.checked) state.visibleColumns.add(key);
  else state.visibleColumns.delete(key);
  persistVisibleColumns();
  applyColumnVisibility();
  updateColumnsButtonLabel();
}

function makeTableEmptyRow(message) {
  const visibleColumnCount = TABLE_COLUMNS.filter((column) => isColumnVisible(column.key)).length;
  return `<tr><td colspan="${Math.max(1, visibleColumnCount)}" class="empty-cell">${safeText(message)}</td></tr>`;
}

function getFilterDefinition(filterKey) {
  return FILTER_DEFS.find((entry) => entry.key === filterKey) || FILTER_DEFS[0];
}

function matchesTab(row, tabKey) {
  return getFilterDefinition(tabKey).predicate(row);
}

function selectOptionLabel(options, value) {
  return options.find((entry) => entry.value === value)?.label || humanizeEnum(value);
}

function activeFilterSummary() {
  const entries = [];
  if (state.filters.tab !== "all") entries.push(`Tab: ${getFilterDefinition(state.filters.tab).label}`);
  if (state.filters.card !== "all") entries.push(`Card: ${getFilterDefinition(state.filters.card).label}`);
  if (state.filters.itemType !== "all") entries.push(`Item Type: ${selectOptionLabel(ITEM_TYPE_OPTIONS, state.filters.itemType)}`);
  if (state.filters.materialStatus !== "all") entries.push(`Material Status: ${selectOptionLabel(MATERIAL_STATUS_OPTIONS, state.filters.materialStatus)}`);
  if (state.filters.salesOrderStatus !== "all") entries.push(`Sales Order Status: ${selectOptionLabel(SALES_ORDER_STATUS_OPTIONS, state.filters.salesOrderStatus)}`);
  if (state.filters.presenceStatus !== "all") entries.push(`Presence: ${selectOptionLabel(PRESENCE_STATUS_OPTIONS, state.filters.presenceStatus)}`);
  if (state.filters.flags.po_without_rop) entries.push("Flag: PO Without ROP");
  if (state.filters.flags.rop_without_po) entries.push("Flag: ROP Without PO");
  if (state.filters.flags.mixed_uom) entries.push("Flag: Mixed UoM");
  if (state.filters.flags.non_trackable) entries.push("Flag: Non-Product / Service");
  return entries.length ? `Active filters: ${entries.join(", ")}` : "Active filters: All Lines";
}

function setSingleFilter(group, filterKey) {
  const nextFilter = FILTER_DEFS.some((entry) => entry.key === filterKey) ? filterKey : "all";
  const current = state.filters[group] || "all";
  state.filters[group] = current === nextFilter ? "all" : nextFilter;
  renderDashboard();
}

function setSelectFilter(group, value) {
  state.filters[group] = value || "all";
  renderDashboard();
}

function setFlagFilter(flagKey, checked) {
  if (!(flagKey in state.filters.flags)) return;
  state.filters.flags[flagKey] = checked;
  renderDashboard();
}

function clearAllFilters() {
  state.filters.tab = "all";
  state.filters.card = "all";
  state.filters.itemType = "all";
  state.filters.materialStatus = "all";
  state.filters.salesOrderStatus = "all";
  state.filters.presenceStatus = "all";
  state.filters.flags = {
    po_without_rop: false,
    rop_without_po: false,
    mixed_uom: false,
    non_trackable: false,
  };
  renderDashboard();
}

function clearSort() {
  state.sort.key = null;
  state.sort.direction = "asc";
  renderDashboard();
}

function renderTabs() {
  const buttons = TAB_DEFS.map((tab) => {
    const count = state.lines.filter((row) => tab.predicate(row)).length;
    const active = tab.key === state.filters.tab ? "active" : "";
    return `<button class="tab-button ${active}" type="button" data-filter="${tab.key}" data-tab="${tab.key}" aria-pressed="${tab.key === state.filters.tab}"><span>${escapeHtml(tab.label)}</span><strong>${formatCount(count)}</strong></button>`;
  });
  els.tabBar.innerHTML = buttons.join("");
}

function renderFilterState() {
  if (els.activeFilterLabel) {
    els.activeFilterLabel.textContent = activeFilterSummary();
  }
  if (els.clearFilterButton) {
    const hasActiveFilters =
      state.filters.tab !== "all" ||
      state.filters.card !== "all" ||
      state.filters.itemType !== "all" ||
      state.filters.materialStatus !== "all" ||
      state.filters.salesOrderStatus !== "all" ||
      state.filters.presenceStatus !== "all" ||
      Object.values(state.filters.flags).some(Boolean);
    els.clearFilterButton.disabled = !hasActiveFilters;
  }
  if (els.clearSortButton) {
    els.clearSortButton.disabled = !state.sort.key;
  }
  if (els.itemTypeFilter) els.itemTypeFilter.value = state.filters.itemType;
  if (els.materialStatusFilter) els.materialStatusFilter.value = state.filters.materialStatus;
  if (els.salesOrderStatusFilter) els.salesOrderStatusFilter.value = state.filters.salesOrderStatus;
  if (els.presenceStatusFilter) els.presenceStatusFilter.value = state.filters.presenceStatus;
  document.querySelectorAll("input[data-flag-filter]").forEach((input) => {
    const flagKey = input.dataset.flagFilter;
    if (flagKey in state.filters.flags) {
      input.checked = !!state.filters.flags[flagKey];
    }
  });

  document.querySelectorAll("#tabBar [data-filter]").forEach((element) => {
    const isActive = element.dataset.filter === state.filters.tab;
    element.classList.toggle("active", isActive);
    element.setAttribute("aria-pressed", String(isActive));
  });

  document.querySelectorAll(".kpi-grid-io [data-filter]").forEach((element) => {
    const isActive = element.dataset.filter === state.filters.card;
    element.classList.toggle("active", isActive);
    element.setAttribute("aria-pressed", String(isActive));
  });
}

function renderSortState() {
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    const key = button.dataset.sortKey;
    const indicator = button.querySelector(".sort-indicator");
    const isActive = key && key === state.sort.key;
    const direction = isActive ? state.sort.direction : "";
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-sort", isActive ? (direction === "asc" ? "ascending" : "descending") : "none");
    if (indicator) {
      indicator.textContent = isActive ? (direction === "asc" ? "↑" : "↓") : "";
    }
  });
}

function splitSummaryValues(value) {
  if (!value) return [];
  return String(value)
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizeUomSummary(value) {
  if (!value) return "";
  const seen = new Set();
  const values = String(value)
    .split(/[;,]/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .filter((entry) => {
      const key = entry.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  return values.join(" ; ");
}

function renderDocumentReferences(value) {
  const values = splitSummaryValues(value);
  if (!values.length) {
    return "-";
  }
  return `<span class="doc-ref-inline">${values.map((entry) => safeText(entry)).join(", ")}</span>`;
}

function renderSalesOrderLinkCell(row) {
  return row.has_sales_order_link
    ? badge("Linked", "status-progress")
    : badge("Pre-SO", "status-muted");
}

function renderSourcePathCell(row) {
  const source = row.material_chain_source || "UNKNOWN_SOURCE";
  const label = mappedLabel(SOURCE_PATH_LABELS, source);
  const tone = source === "FROM_STOCK"
    ? "status-complete"
    : (source === "DIRECT_SALES_ORDER" || source === "LINKED_INTERNAL_ORDER" ? "status-progress" : "status-muted");
  return badge(label, tone);
}

function materialStatusMeta(row) {
  const poQty = numberValue(row.po_qty);
  const receivedQty = numberValue(row.po_received_qty);
  const ropQty = numberValue(row.rop_qty);
  const rkbQty = numberValue(row.rkb_actual_qty);
  const poAmount = Math.abs(numberValue(row.po_subtotal));
  const ropAmount = Math.abs(numberValue(row.rop_subtotal));
  const rkbAmount = Math.abs(numberValue(row.rkb_actual_subtotal));

  if (row.material_chain_source === "FROM_STOCK") {
    return { label: "From Stock", tone: "status-complete" };
  }

  if (receivedQty > 0) {
    if (poQty > 0 && receivedQty >= poQty) {
      return { label: "Fully Received", tone: "status-complete" };
    }
    return { label: "Partially Received", tone: "status-progress" };
  }

  if (poQty > 0 || poAmount > 0) {
    return { label: "PO Created", tone: "status-progress" };
  }

  if (ropQty > 0 || ropAmount > 0) {
    return { label: "ROP Created", tone: "status-progress" };
  }

  if (row.product_presence_status === "RKB_ONLY" || rkbQty > 0 || rkbAmount > 0) {
    return { label: "RKB Only", tone: "status-muted" };
  }

  return { label: "Needs Review", tone: "status-followup" };
}

function renderLineFlags(row) {
  const flags = [];
  if (row.po_without_rop_flag) flags.push(flag("PO Without ROP", "danger"));
  if (row.rop_without_po_flag) flags.push(flag("ROP Without PO", "danger"));
  if (row.mixed_uom_flag) flags.push(flag("Mixed UoM", "warning"));
  if (row.product_trackability_class !== "TRACKABLE_PRODUCT") flags.push(flag("Non-Product / Service", "muted"));
  return flags.length ? `<div class="line-flags">${flags.join("")}</div>` : "-";
}

function matchesSelectFilter(value, selectedValue) {
  return selectedValue === "all" || value === selectedValue;
}

function matchesMaterialStatus(row, selectedValue) {
  return selectedValue === "all" || materialStatusMeta(row).label === selectedValue;
}

function matchesSalesOrderStatus(row, selectedValue) {
  if (selectedValue === "all") return true;
  const rowValue = row.has_sales_order_link ? "linked" : "pre_so";
  return rowValue === selectedValue;
}

function matchesFlags(row) {
  const { flags } = state.filters;
  if (flags.po_without_rop && !row.po_without_rop_flag) return false;
  if (flags.rop_without_po && !row.rop_without_po_flag) return false;
  if (flags.mixed_uom && !row.mixed_uom_flag) return false;
  if (flags.non_trackable && row.product_trackability_class === "TRACKABLE_PRODUCT") return false;
  return true;
}

function matchesAllFilters(row) {
  const { tab, card, itemType, materialStatus, salesOrderStatus, presenceStatus } = state.filters;
  if (!matchesTab(row, tab)) return false;
  if (!getFilterDefinition(card).predicate(row)) return false;
  if (!matchesSelectFilter(row.product_trackability_class, itemType)) return false;
  if (!matchesMaterialStatus(row, materialStatus)) return false;
  if (!matchesSalesOrderStatus(row, salesOrderStatus)) return false;
  if (!matchesSelectFilter(row.product_presence_status, presenceStatus)) return false;
  if (!matchesFlags(row)) return false;
  return true;
}

function getSortValue(row, key) {
  switch (key) {
    case "internal_order_number":
      return row.internal_order_number || "";
    case "source_path":
      return mappedLabel(SOURCE_PATH_LABELS, row.material_chain_source || "UNKNOWN_SOURCE");
    case "sales_order_status":
      return row.has_sales_order_link ? 1 : 0;
    case "linked_sales_order":
      return row.linked_sales_order_numbers || "";
    case "rkb_request":
      return row.rkb_actual_request_summary || row.rkb_actual_request_numeric_summary || "";
    case "rop_request":
      return row.rop_request_summary || row.rop_request_numeric_summary || "";
    case "related_po":
      return row.po_order_reference_summary || "";
    case "product_name":
      return row.product_name || "";
    case "item_type":
      return mappedLabel(TRACKABILITY_LABELS, row.product_trackability_class);
    case "material_status":
      return materialStatusMeta(row).label;
    case "uom":
      return normalizeUomSummary(row.uom_summary || "");
    case "rkb_qty":
      return numberValue(row.rkb_actual_qty);
    case "rkb_amount":
      return numberValue(row.rkb_actual_subtotal);
    case "rop_qty":
      return numberValue(row.rop_qty);
    case "rop_amount":
      return numberValue(row.rop_subtotal);
    case "po_qty":
      return numberValue(row.po_qty);
    case "po_amount":
      return numberValue(row.po_subtotal);
    case "received_qty":
      return numberValue(row.po_received_qty);
    case "invoiced_qty":
      return numberValue(row.po_invoiced_qty);
    default:
      return "";
  }
}

function sortRows(rows) {
  if (!state.sort.key) return rows.slice();
  const collator = new Intl.Collator("id", { numeric: true, sensitivity: "base" });
  const direction = state.sort.direction === "desc" ? -1 : 1;
  return rows.slice().sort((left, right) => {
    const a = getSortValue(left, state.sort.key);
    const b = getSortValue(right, state.sort.key);

    const aEmpty = a === null || a === undefined || a === "";
    const bEmpty = b === null || b === undefined || b === "";
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1 * direction;
    if (bEmpty) return -1 * direction;

    if (typeof a === "number" && typeof b === "number") {
      return (a - b) * direction;
    }

    return collator.compare(String(a), String(b)) * direction;
  });
}

function visibleRows() {
  return sortRows(state.lines.filter((row) => matchesAllFilters(row)));
}

function renderLines() {
  const rows = visibleRows();
  const total = state.lines.length;
  els.lineCount.textContent = `${formatCount(rows.length)} / ${formatCount(total)} lines`;

  if (!rows.length) {
    const emptyMessage = total === 0
      ? (state.payload?.metadata?.empty_state_message || `No ${perspectiveLabel()} material rows found.`)
      : `No ${perspectiveLabel()} rows match the selected filters.`;
    els.lineTableBody.innerHTML = makeTableEmptyRow(emptyMessage);
    return;
  }

  els.lineTableBody.innerHTML = rows.map((row) => {
    const status = materialStatusMeta(row);
    const receiptStatus = formatReceiptStatus(row);
    return `
    <tr>
      <td data-column-key="internal_order_number">${safeText(row.internal_order_number)}</td>
      <td data-column-key="source_path">${renderSourcePathCell(row)}</td>
      <td data-column-key="sales_order_status">${renderSalesOrderLinkCell(row)}</td>
      <td data-column-key="linked_sales_order">${renderDocumentReferences(row.linked_sales_order_numbers)}</td>
      <td data-column-key="rkb_request">${renderDocumentReferences(row.rkb_actual_request_summary || row.rkb_actual_request_numeric_summary)}</td>
      <td data-column-key="rop_request">${renderDocumentReferences(row.rop_request_summary || row.rop_request_numeric_summary)}</td>
      <td data-column-key="related_po">${renderDocumentReferences(row.po_order_reference_summary)}</td>
      <td data-column-key="product_name">
        <div>${safeText(row.product_name)}</div>
        <div class="subtle-cell">${safeText(row.product_key)}</div>
      </td>
      <td data-column-key="item_type">${badge(mappedLabel(TRACKABILITY_LABELS, row.product_trackability_class), row.is_trackable_product ? "status-complete" : "status-muted")}</td>
      <td data-column-key="material_status">${badge(status.label, status.tone)}</td>
      <td data-column-key="uom">${safeText(normalizeUomSummary(row.uom_summary))}</td>
      <td data-column-key="rkb_qty" class="num">${formatQty(row.rkb_actual_qty)}</td>
      <td data-column-key="rkb_amount" class="num">${formatAmount(row.rkb_actual_subtotal)}</td>
      <td data-column-key="rop_qty" class="num">${formatQty(row.rop_qty)}</td>
      <td data-column-key="rop_amount" class="num">${formatAmount(row.rop_subtotal)}</td>
      <td data-column-key="po_qty" class="num">${formatQty(row.po_qty)}</td>
      <td data-column-key="po_amount" class="num">${formatAmount(row.po_subtotal)}</td>
      <td data-column-key="received_qty" class="num">${formatQty(row.po_received_qty)}</td>
      <td data-column-key="invoiced_qty" class="num">${formatQty(row.po_invoiced_qty)}</td>
      <td data-column-key="flags"><div>${renderLineFlags(row)}</div><div class="receipt-status">${safeText(receiptStatus)}</div></td>
    </tr>
  `;
  }).join("");
}

function renderDashboard() {
  if (!state.payload) {
    renderTabs();
    renderLines();
    renderFilterState();
    renderSortState();
    applyColumnVisibility();
    updateColumnsButtonLabel();
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
  renderFilterState();
  renderSortState();
  applyColumnVisibility();
  updateColumnsButtonLabel();
}

async function loadDashboard(searchValue) {
  const normalized = (searchValue || "").trim();
  const perspective = currentPerspective();
  if (!normalized) {
    showError(`${perspectiveLabel()} number is required.`);
    return;
  }

  setLoading(true);
  clearError();

  try {
    const params = new URLSearchParams({ perspective });
    if (perspective === "sales_order") {
      params.set("sales_order_number", normalized);
    } else {
      params.set("internal_order_number", normalized);
    }
    const response = await fetch(`/api/dashboard/internal-order-rekap?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload?.detail?.error || payload?.detail || payload?.message || `Request failed: ${response.status}`;
      throw new Error(message);
    }

    state.payload = payload;
    state.perspective = payload?.metadata?.perspective || payload?.perspective || perspective;
    state.lines = Array.isArray(payload.lines) ? payload.lines : [];
    resetInteractiveState();
    updatePerspectiveUI();
    renderDashboard();
    history.replaceState({}, "", `${location.pathname}?${params.toString()}`);
    els.loadStatus.textContent = `Loaded ${normalized}`;
  } catch (error) {
    state.payload = null;
    state.lines = [];
    resetInteractiveState();
    clearEmptyState();
    renderTabs();
    renderLines();
    renderFilterState();
    renderSortState();
    applyColumnVisibility();
    updateColumnsButtonLabel();
    showError(error.message || `Failed to load ${perspectiveLabel()} data.`);
    els.loadStatus.textContent = "Failed to load";
  } finally {
    setLoading(false);
  }
}

function handleTabInteraction(event) {
  const control = event.target.closest("[data-filter]");
  if (!control) return;
  setSingleFilter("tab", control.dataset.filter || "all");
}

function handleCardInteraction(event) {
  const control = event.target.closest("[data-filter]");
  if (!control) return;
  setSingleFilter("card", control.dataset.filter || "all");
}

function handleTabKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const control = event.target.closest("[data-filter]");
  if (!control) return;
  event.preventDefault();
  setSingleFilter("tab", control.dataset.filter || "all");
}

function handleCardKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const control = event.target.closest("[data-filter]");
  if (!control) return;
  event.preventDefault();
  setSingleFilter("card", control.dataset.filter || "all");
}

function handleSortInteraction(event) {
  const control = event.target.closest("[data-sort-key]");
  if (!control) return;
  const key = control.dataset.sortKey;
  if (!key) return;
  if (state.sort.key !== key) {
    state.sort.key = key;
    state.sort.direction = "asc";
  } else if (state.sort.direction === "asc") {
    state.sort.direction = "desc";
  } else {
    state.sort.key = null;
    state.sort.direction = "asc";
  }
  renderDashboard();
}

function handleSortKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const control = event.target.closest("[data-sort-key]");
  if (!control) return;
  event.preventDefault();
  handleSortInteraction(event);
}

function handleControlChange(event) {
  const columnToggle = event.target.closest("[data-column-toggle]");
  if (columnToggle) {
    const key = columnToggle.dataset.columnToggle;
    if (!key) return;
    if (columnToggle.checked) state.visibleColumns.add(key);
    else state.visibleColumns.delete(key);
    persistVisibleColumns();
    applyColumnVisibility();
    updateColumnsButtonLabel();
    return;
  }

  const select = event.target.closest("[data-filter-control]");
  if (select) {
    setSelectFilter(select.dataset.filterControl, select.value);
    return;
  }

  const checkbox = event.target.closest("[data-flag-filter]");
  if (checkbox) {
    setFlagFilter(checkbox.dataset.flagFilter, checkbox.checked);
  }
}

els.tabBar.addEventListener("click", handleTabInteraction);
els.tabBar.addEventListener("keydown", handleTabKeydown);
els.kpiGrid?.addEventListener("click", handleCardInteraction);
els.kpiGrid?.addEventListener("keydown", handleCardKeydown);
els.clearFilterButton?.addEventListener("click", clearAllFilters);
els.clearSortButton?.addEventListener("click", clearSort);
els.columnsButton?.addEventListener("click", () => toggleColumnsPanel());
els.columnsShowAllButton?.addEventListener("click", () => showAllColumns());
els.columnsResetButton?.addEventListener("click", () => resetVisibleColumnsToDefault());
document.addEventListener("click", (event) => {
  handleSortInteraction(event);
  columnsClickOutside(event);
});
document.addEventListener("keydown", handleSortKeydown);
document.addEventListener("change", handleControlChange);
els.perspectiveInputs.forEach((input) => {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    state.perspective = input.value === "sales_order" ? "sales_order" : "internal_order";
    clearError();
    updatePerspectiveUI();
  });
});

els.loadButton.addEventListener("click", () => loadDashboard(els.internalOrderInput.value));
els.refreshButton.addEventListener("click", () => loadDashboard(els.internalOrderInput.value));
els.internalOrderInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadDashboard(els.internalOrderInput.value);
  }
});

const initialParams = new URLSearchParams(location.search);
const initialPerspective = initialParams.get("perspective") === "sales_order" || initialParams.has("sales_order_number") ? "sales_order" : "internal_order";
state.perspective = initialPerspective;
const initialSearchValue = initialPerspective === "sales_order"
  ? (initialParams.get("sales_order_number") || "")
  : (initialParams.get("internal_order_number") || DEFAULT_INTERNAL_ORDER);
els.internalOrderInput.value = initialSearchValue;
state.visibleColumns = loadVisibleColumns();
updatePerspectiveUI();
renderColumnControls();
renderDashboard();
if (initialSearchValue) {
  loadDashboard(initialSearchValue);
}
