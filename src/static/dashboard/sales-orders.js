const ACTIVE_STATUS_FILTER = "__ACTIVE__";
const DEFAULT_YEAR_FILTER = "2026";
const COLUMN_STORAGE_KEY = "dashboard.visibleColumns.salesOrders.v1";
const TABLE_COLUMNS = [
  { key: "expand", label: "Detail", defaultVisible: true, fixed: true, exportable: false },
  { key: "sales_order_number", label: "SO Number", defaultVisible: true, exportType: "string", exportValue: (row) => row.sales_order_number || "" },
  { key: "customer_name", label: "Customer", defaultVisible: true, exportType: "string", exportValue: (row) => row.customer_name || "" },
  { key: "product_type_label", label: "Product Type", defaultVisible: true, exportType: "string", exportValue: (row) => row.product_type_label || "" },
  { key: "delivery_date", label: "Delivery Date", defaultVisible: true, exportType: "date", exportValue: (row) => dateOnly(row.commitment_date) || "" },
  { key: "source_type", label: "Source Type", defaultVisible: true, exportType: "string", exportValue: (row) => sourceLabel(row) || "" },
  { key: "sales_order_state", label: "SO Status", defaultVisible: true, exportType: "string", exportValue: (row) => row.sales_order_state || "" },
  { key: "follow_up_status", label: "Follow-Up", defaultVisible: true, exportType: "string", exportValue: (row) => followUpLabel(row.follow_up_status) || "" },
  { key: "related_mo_qty", label: "Related MO Qty", defaultVisible: false, exportType: "number", exportValue: (row) => numberValue(row.total_related_mo_qty) },
  { key: "produced_mo_qty", label: "Produced MO Qty", defaultVisible: false, exportType: "number", exportValue: (row) => numberValue(row.total_done_mo_qty) },
  { key: "manufacturing_in_progress_qty", label: "Manufacturing In Progress Qty", defaultVisible: false, exportType: "number", exportValue: (row) => numberValue(row.total_in_progress_mo_qty) },
  { key: "shared_io", label: "Shared IO", defaultVisible: false, exportType: "string", exportValue: (row) => row.shared_io_numbers || "" },
  { key: "ordered_qty", label: "Ordered Qty", defaultVisible: true, exportType: "number", exportValue: (row) => numberValue(row.ordered_qty) },
  { key: "delivered_qty", label: "Delivered Qty", defaultVisible: true, exportType: "number", exportValue: (row) => numberValue(row.delivered_qty) },
  { key: "invoiced_qty", label: "Invoiced Qty", defaultVisible: true, exportType: "number", exportValue: (row) => numberValue(row.invoiced_qty) },
  { key: "qty_delivery_percent", label: "Qty Delivery %", defaultVisible: true, exportType: "percent", exportValue: (row) => row.qty_delivery_progress_ratio },
  { key: "qty_invoice_percent", label: "Qty Invoice %", defaultVisible: true, exportType: "percent", exportValue: (row) => row.qty_invoice_progress_ratio },
  { key: "sales_amount_idr", label: "Sales Amount IDR", defaultVisible: true, exportType: "currency", exportValue: (row) => numberValue(row.ordered_amount_idr) },
  { key: "rkb_planned_cost", label: "RKB Planned Cost", defaultVisible: true, exportType: "currency", exportValue: (row) => numberValue(row.rkb_planned_cost) },
  { key: "rkb_kontribusi_percent", label: "RKB Kontribusi %", defaultVisible: true, exportType: "percent", exportValue: (row) => row.rkb_kontribusi_percent },
  { key: "actual_cost", label: "Actual Cost", defaultVisible: false, exportType: "currency", exportValue: (row) => numberValue(row.actual_cost) },
  { key: "kontribusi_aktual_percent", label: "Kontribusi Aktual %", defaultVisible: false, exportType: "percent", exportValue: (row) => row.kontribusi_aktual_percent },
  { key: "delivered_amount_idr", label: "Delivered Amount IDR", defaultVisible: false, exportType: "currency", exportValue: (row) => numberValue(row.delivered_amount_idr) },
  { key: "invoiced_amount_idr", label: "Invoiced Amount IDR", defaultVisible: false, exportType: "currency", exportValue: (row) => numberValue(row.invoiced_amount_idr) },
  { key: "amount_delivery_percent", label: "Amount Delivery %", defaultVisible: false, exportType: "percent", exportValue: (row) => row.amount_delivery_progress_ratio },
  { key: "amount_invoice_percent", label: "Amount Invoice %", defaultVisible: false, exportType: "percent", exportValue: (row) => row.amount_invoice_progress_ratio },
];
const DEFAULT_VISIBLE_COLUMNS = TABLE_COLUMNS.filter((column) => column.defaultVisible).map((column) => column.key);

const state = {
  rows: [],
  filteredRows: [],
  expanded: new Set(),
  detailCache: new Map(),
  detailLoading: new Set(),
  sortKey: "commitment_date",
  sortDirection: "asc",
  filterOptions: {
    year: [],
    customer: [],
    productType: [],
    source: [],
    status: [],
    followUp: [],
  },
  filters: {
    year: new Set(),
    customer: new Set(),
    productType: new Set(),
    source: new Set(),
    status: new Set(),
    followUp: new Set(),
  },
  filtersInitialized: false,
  quickFilter: "",
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  clearToolbarFiltersButton: document.getElementById("clearToolbarFiltersButton"),
  clearSortButton: document.getElementById("clearSortButton"),
  exportExcelButton: document.getElementById("exportExcelButton"),
  columnsButton: document.getElementById("columnsButton"),
  columnsPanel: document.getElementById("columnsPanel"),
  columnsList: document.getElementById("columnsList"),
  columnsShowAllButton: document.getElementById("columnsShowAllButton"),
  columnsResetButton: document.getElementById("columnsResetButton"),
  activeFilterSummary: document.getElementById("activeFilterSummary"),
  soFilter: document.getElementById("soFilter"),
  yearFilter: document.getElementById("yearFilter"),
  customerFilter: document.getElementById("customerFilter"),
  productTypeFilter: document.getElementById("productTypeFilter"),
  commitmentFromFilter: document.getElementById("commitmentFromFilter"),
  commitmentToFilter: document.getElementById("commitmentToFilter"),
  sourceFilter: document.getElementById("sourceFilter"),
  statusFilter: document.getElementById("statusFilter"),
  followUpFilter: document.getElementById("followUpFilter"),
  statusStrip: document.getElementById("statusStrip"),
  productTypeStrip: document.getElementById("productTypeStrip"),
  sourceStrip: document.getElementById("sourceStrip"),
  kpiGrid: document.querySelector(".kpi-grid"),
  salesOrderTable: document.getElementById("salesOrderTable"),
  dashboardRows: document.getElementById("dashboardRows"),
  rowCount: document.getElementById("rowCount"),
  lastLoaded: document.getElementById("lastLoaded"),
  kpiActiveSo: document.getElementById("kpiActiveSo"),
  kpiDeliveredSo: document.getElementById("kpiDeliveredSo"),
  kpiInvoicedSo: document.getElementById("kpiInvoicedSo"),
  kpiDelayedDelivery: document.getElementById("kpiDelayedDelivery"),
  kpiWaitingInvoice: document.getElementById("kpiWaitingInvoice"),
  kpiQtyDelivery: document.getElementById("kpiQtyDelivery"),
  kpiQtyInvoice: document.getElementById("kpiQtyInvoice"),
  kpiAmountDelivery: document.getElementById("kpiAmountDelivery"),
  kpiAmountInvoice: document.getElementById("kpiAmountInvoice"),
  kpiFromIo: document.getElementById("kpiFromIo"),
  kpiMakeToOrder: document.getElementById("kpiMakeToOrder"),
  kpiFromStock: document.getElementById("kpiFromStock"),
  kpiMixedSource: document.getElementById("kpiMixedSource"),
  kpiUnknownSource: document.getElementById("kpiUnknownSource"),
  unknownSourceCard: document.getElementById("unknownSourceCard"),
  barQtyDelivery: document.getElementById("barQtyDelivery"),
  barQtyInvoice: document.getElementById("barQtyInvoice"),
  barAmountDelivery: document.getElementById("barAmountDelivery"),
  barAmountInvoice: document.getElementById("barAmountInvoice"),
};
const sourceLabels = {
  FROM_INTERNAL_ORDER: "From IO",
  FROM_STOCK: "From Stock",
  MAKE_TO_ORDER: "From Manufacture Order",
  MIXED_SOURCE: "From IO & Manufacture Order",
  UNKNOWN_SOURCE: "Unknown Source",
  CANCELLED_RECORD: "Cancel",
};

const followUpLabels = {
  CANCELLED_RECORD: "Cancel",
  UNKNOWN_SOURCE: "Unknown Source",
  DELAYED_DELIVERY: "Delayed Delivery",
  WAITING_PRODUCTION: "Waiting Manufacture Order",
  WAITING_DELIVERY: "Waiting to Deliver",
  WAITING_INVOICE: "Waiting to Invoice",
  COMPLETED: "Completed",
};

const sourceOrder = ["FROM_INTERNAL_ORDER", "FROM_STOCK", "MAKE_TO_ORDER", "MIXED_SOURCE", "UNKNOWN_SOURCE", "CANCELLED_RECORD"];
const followUpOrder = ["CANCELLED_RECORD", "UNKNOWN_SOURCE", "DELAYED_DELIVERY", "WAITING_PRODUCTION", "WAITING_DELIVERY", "WAITING_INVOICE", "COMPLETED"];

let columnController = null;

let columnController = null;

function isCancelStatusValue(value) {
  return ["cancel", "cancelled"].includes(String(value || "").toLowerCase());
}

function activeStatusValues() {
  return state.filterOptions.status.filter((status) => !isCancelStatusValue(status));
}

function sourceLabel(rowOrSource) {
  const source = typeof rowOrSource === "object" && rowOrSource !== null ? rowOrSource.source_type : rowOrSource;
  if (source === "UNKNOWN_SOURCE" && typeof rowOrSource === "object" && isCancelled(rowOrSource)) return "";
  return sourceLabels[source] || safeText(source);
}

function followUpLabel(status) {
  return followUpLabels[status] || safeText(status);
}

function setSingleFilter(filterKey, value) {
  const selected = state.filters[filterKey];
  if (selected.size === 1 && selected.has(value)) selected.clear();
  else state.filters[filterKey] = new Set([value]);
  applyFilters();
}

function selectionMatches(filterKey, value) {
  const selected = state.filters[filterKey];
  if (filterKey === "status" && !selected.size) return false;
  return !selected.size || selected.has(String(value || ""));
}

function setsEqualToArray(set, values) {
  return set.size === values.length && values.every((value) => set.has(String(value)));
}

function checklistSummary(filterKey, allLabel, labelFn) {
  const selected = state.filters[filterKey];
  const options = state.filterOptions[filterKey] || [];
  if (filterKey === "status" && selected.size && setsEqualToArray(selected, activeStatusValues())) return "Active only";
  if (!selected.size || selected.size === options.length) return allLabel;
  if (selected.size === 1) return labelFn([...selected][0]);
  return `${selected.size} selected`;
}

const checklistConfigs = {
  year: { el: () => els.yearFilter, allLabel: "All years", label: (value) => safeText(value) },
  customer: { el: () => els.customerFilter, allLabel: "All customers", label: (value) => safeText(value) },
  productType: { el: () => els.productTypeFilter, allLabel: "All product types", label: (value) => safeText(value) },
  source: { el: () => els.sourceFilter, allLabel: "All sources", label: sourceLabel },
  status: { el: () => els.statusFilter, allLabel: "All statuses", label: (value) => safeText(value) },
  followUp: { el: () => els.followUpFilter, allLabel: "All follow-up", label: followUpLabel },
};
const quickFilterLabels = {
  DELIVERED_SO: "Delivered SO",
  INVOICED_SO: "Invoiced SO",
};

function setDefaultYearFilter() {
  state.filters.year = state.filterOptions.year.includes(DEFAULT_YEAR_FILTER)
    ? new Set([DEFAULT_YEAR_FILTER])
    : new Set();
}
function setActiveOnlyStatus() {
  state.filters.status = new Set(activeStatusValues());
}

function setAllStatuses() {
  state.filters.status = new Set(state.filterOptions.status);
}

function toggleQuickFilter(value) {
  state.quickFilter = state.quickFilter === value ? "" : value;
  applyFilters();
}

function setFollowUpFilter(status) {
  const selected = state.filters.followUp;
  if (selected.size === 1 && selected.has(status)) selected.clear();
  else state.filters.followUp = new Set([status]);
  state.quickFilter = "";
  applyFilters();
}
const ioQtyStatusLabels = {
  NO_IO_MO_FOUND: "No IO MO found",
  IO_QTY_SURPLUS_VS_LINKED_SO: "IO qty surplus vs linked SO",
  LINKED_SO_QTY_EXCEEDS_IO_QTY: "Linked SO qty exceeds IO qty",
  IO_QTY_BALANCED_WITH_LINKED_SO: "IO qty balanced with linked SO",
  IO_QTY_UNALLOCATED_MULTI_IO_SO: "IO qty unallocated multi-IO SO",
  IO_QTY_UNCLEAR: "IO qty unclear",
};

function numberValue(value) {
  return Number(value || 0);
}

function formatNumber(value, digits = 0) {
  return numberValue(value).toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatQty(value) {
  const numeric = numberValue(value);
  const digits = Math.abs(numeric % 1) > 0 ? 2 : 0;
  return formatNumber(numeric, digits);
}

function formatAmount(value) {
  return numberValue(value).toLocaleString("en-US", {
    maximumFractionDigits: 0,
  });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatContributionPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${(numeric * 100).toFixed(1)}%`;
}

function contributionClass(value) {
  if (value === null || value === undefined || value === "") return "";
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric < 0 ? "contribution-negative" : "";
}

function progressWidth(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "0%";
  }
  return `${Math.max(0, Math.min(100, Number(value) * 100))}%`;
}

function dateOnly(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function formatDate(value) {
  return dateOnly(value) || "-";
}

function safeText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function ratio(numerator, denominator) {
  const den = numberValue(denominator);
  if (!den) return null;
  return numberValue(numerator) / den;
}

function cssClassForFollowUp(status) {
  if (status === "COMPLETED") return "status-complete";
  if (status === "WAITING_INVOICE" || status === "WAITING_DELIVERY" || status === "WAITING_PRODUCTION") {
    return "status-followup";
  }
  if (status === "DELAYED_DELIVERY" || status === "UNKNOWN_SOURCE") return "status-danger";
  if (status === "CANCELLED_RECORD") return "status-muted";
  return "status-progress";
}

function cssClassForSource(source) {
  if (source === "FROM_INTERNAL_ORDER" || source === "FROM_STOCK") return "status-progress";
  if (source === "MAKE_TO_ORDER" || source === "MIXED_SOURCE") return "status-followup";
  if (source === "UNKNOWN_SOURCE") return "status-danger";
  if (source === "CANCELLED_RECORD") return "status-muted";
  return "status-muted";
}

function badge(label, className) {
  const text = safeText(label);
  if (text === "-") return "";
  return `<span class="status-badge ${className}">${text}</span>`;
}

function sourceBadge(rowOrSource) {
  const source = typeof rowOrSource === "object" && rowOrSource !== null ? rowOrSource.source_type : rowOrSource;
  return badge(sourceLabel(rowOrSource), cssClassForSource(source));
}

function followUpBadge(status) {
  return badge(followUpLabel(status), cssClassForFollowUp(status));
}

function ioQtyStatusLabel(status) {
  return ioQtyStatusLabels[status] || safeText(status);
}

function miniProgress(value) {
  return `
    <div class="progress-value"><span>${formatPercent(value)}</span></div>
    <div class="mini-progress"><span style="width:${progressWidth(value)}"></span></div>
  `;
}

function isCancelled(row) {
  return row.is_cancelled || row.follow_up_status === "CANCELLED_RECORD";
}

function summarize(rows) {
  const active = rows.filter((row) => !isCancelled(row));
  const orderedQty = active.reduce((sum, row) => sum + numberValue(row.ordered_qty), 0);
  const deliveredQty = active.reduce((sum, row) => sum + numberValue(row.delivered_qty), 0);
  const invoicedQty = active.reduce((sum, row) => sum + numberValue(row.invoiced_qty), 0);
  const orderedAmount = active.reduce((sum, row) => sum + numberValue(row.ordered_amount), 0);
  const deliveredAmount = active.reduce((sum, row) => sum + numberValue(row.delivered_amount), 0);
  const invoicedAmount = active.reduce((sum, row) => sum + numberValue(row.invoiced_amount), 0);

  return {
    activeSalesOrders: active.length,
    deliveredSalesOrders: active.filter((row) => row.has_delivered_qty).length,
    invoicedSalesOrders: active.filter((row) => row.has_invoiced_qty).length,
    delayedDelivery: active.filter((row) => row.follow_up_status === "DELAYED_DELIVERY").length,
    waitingInvoice: active.filter((row) => row.follow_up_status === "WAITING_INVOICE").length,
    qtyDeliveryProgress: ratio(deliveredQty, orderedQty),
    qtyInvoiceProgress: ratio(invoicedQty, orderedQty),
    amountDeliveryProgress: ratio(deliveredAmount, orderedAmount),
    amountInvoiceProgress: ratio(invoicedAmount, orderedAmount),
    fromIo: active.filter((row) => row.source_type === "FROM_INTERNAL_ORDER").length,
    makeToOrder: active.filter((row) => row.source_type === "MAKE_TO_ORDER").length,
    fromStock: active.filter((row) => row.source_type === "FROM_STOCK").length,
    mixedSource: active.filter((row) => row.source_type === "MIXED_SOURCE").length,
    unknownSource: active.filter((row) => row.source_type === "UNKNOWN_SOURCE").length,
  };
}

function renderKpis(rows, sourceRows = rows) {
  const summary = summarize(rows);
  const sourceSummary = summarize(sourceRows);
  els.kpiActiveSo.textContent = formatNumber(summary.activeSalesOrders);
  els.kpiDeliveredSo.textContent = formatNumber(summary.deliveredSalesOrders);
  els.kpiInvoicedSo.textContent = formatNumber(summary.invoicedSalesOrders);
  els.kpiDelayedDelivery.textContent = formatNumber(summary.delayedDelivery);
  els.kpiWaitingInvoice.textContent = formatNumber(summary.waitingInvoice);
  els.kpiQtyDelivery.textContent = formatPercent(summary.qtyDeliveryProgress);
  els.kpiQtyInvoice.textContent = formatPercent(summary.qtyInvoiceProgress);
  els.kpiAmountDelivery.textContent = formatPercent(summary.amountDeliveryProgress);
  els.kpiAmountInvoice.textContent = formatPercent(summary.amountInvoiceProgress);
  els.kpiFromIo.textContent = formatNumber(sourceSummary.fromIo);
  els.kpiMakeToOrder.textContent = formatNumber(sourceSummary.makeToOrder);
  els.kpiFromStock.textContent = formatNumber(sourceSummary.fromStock);
  els.kpiMixedSource.textContent = formatNumber(sourceSummary.mixedSource);
  els.kpiUnknownSource.textContent = formatNumber(sourceSummary.unknownSource);
  els.unknownSourceCard.hidden = sourceSummary.unknownSource <= 0 && !state.filters.source.has("UNKNOWN_SOURCE");
  document.querySelectorAll("[data-source-type]").forEach((card) => {
    card.classList.toggle("is-active", state.filters.source.size === 1 && state.filters.source.has(card.dataset.sourceType));
  });
  document.querySelectorAll("[data-kpi-action]").forEach((card) => {
    const action = card.dataset.kpiAction;
    const isActiveOnly = action === "ACTIVE_SO" && setsEqualToArray(state.filters.status, activeStatusValues()) && !state.quickFilter;
    const isQuick = action === state.quickFilter;
    const isFollowUp = action === "DELAYED_DELIVERY" || action === "WAITING_INVOICE"
      ? state.filters.followUp.size === 1 && state.filters.followUp.has(action)
      : false;
    card.classList.toggle("is-active", isActiveOnly || isQuick || isFollowUp);
  });
  els.barQtyDelivery.style.width = progressWidth(summary.qtyDeliveryProgress);
  els.barQtyInvoice.style.width = progressWidth(summary.qtyInvoiceProgress);
  els.barAmountDelivery.style.width = progressWidth(summary.amountDeliveryProgress);
  els.barAmountInvoice.style.width = progressWidth(summary.amountInvoiceProgress);
}

function renderStatusStrip(rows) {
  const counts = rows.reduce((acc, row) => {
    acc[row.follow_up_status] = (acc[row.follow_up_status] || 0) + 1;
    return acc;
  }, {});
  const order = [
    "CANCELLED_RECORD",
    "UNKNOWN_SOURCE",
    "DELAYED_DELIVERY",
    "WAITING_PRODUCTION",
    "WAITING_DELIVERY",
    "WAITING_INVOICE",
    "COMPLETED",
  ];

  const selectedFollowUp = state.filters.followUp.size === 1 ? [...state.filters.followUp][0] : "";
  els.statusStrip.innerHTML = order
    .filter((status) => counts[status])
    .map((status) => `
      <button class="status-chip ${cssClassForFollowUp(status)} ${selectedFollowUp === status ? "is-active" : ""}" type="button" data-follow-up-status="${status}">
        ${followUpLabel(status)}
        <strong>${counts[status]}</strong>
      </button>
    `)
    .join("");
}

function renderProductTypeStrip(rows) {
  const counts = rows.reduce((acc, row) => {
    const label = row.product_type_label || "Unknown Product Type";
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});

  els.productTypeStrip.innerHTML = Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, count]) => `
      <button class="status-chip product-type-chip ${state.filters.productType.size === 1 && state.filters.productType.has(label) ? "is-active" : ""}" type="button" data-product-type="${encodeURIComponent(label)}">
        ${safeText(label)}
        <strong>${formatNumber(count)}</strong>
      </button>
    `)
    .join("");
}

function renderSourceStrip(rows) {
  const counts = rows.reduce((acc, row) => {
    if (row.source_type === "UNKNOWN_SOURCE" && isCancelled(row)) return acc;
    acc[row.source_type] = (acc[row.source_type] || 0) + 1;
    return acc;
  }, {});

  els.sourceStrip.innerHTML = sourceOrder
    .filter((source) => source !== "CANCELLED_RECORD")
    .filter((source) => counts[source] || state.filters.source.has(source))
    .map((source) => `
      <button class="status-chip ${cssClassForSource(source)} ${state.filters.source.size === 1 && state.filters.source.has(source) ? "is-active" : ""}" type="button" data-source-type="${source}">
        ${sourceLabel(source)}
        <strong>${formatNumber(counts[source] || 0)}</strong>
      </button>
    `)
    .join("");
}

function renderLineRows(lines) {
  if (!lines || !lines.length) {
    return '<div class="detail-empty">No SO lines found.</div>';
  }
  return `
    <table class="detail-table">
      <thead>
        <tr>
          <th>Product</th>
          <th class="num">Ordered Qty</th>
          <th class="num">Delivered Qty</th>
          <th class="num">Invoiced Qty</th>
          <th class="num">Unit Price IDR</th>
          <th class="num">Ordered Amount IDR</th>
          <th class="num">Delivered Amount IDR</th>
          <th class="num">Invoiced Amount IDR</th>
          <th>Qty Delivery %</th>
          <th>Qty Invoice %</th>
          <th>Progress Basis</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        ${lines.map((line) => `
          <tr>
            <td>${safeText(line.product_name)}</td>
            <td class="num">${formatQty(line.ordered_qty)}</td>
            <td class="num">${formatQty(line.delivered_qty)}</td>
            <td class="num">${formatQty(line.invoiced_qty)}</td>
            <td class="num">${formatAmount(line.unit_price_idr)}</td>
            <td class="num">${formatAmount(line.ordered_amount_idr)}</td>
            <td class="num">${formatAmount(line.delivered_amount_idr)}</td>
            <td class="num">${formatAmount(line.invoiced_amount_idr)}</td>
            <td>${formatPercent(line.qty_delivery_progress_ratio)}</td>
            <td>${formatPercent(line.qty_invoice_progress_ratio)}</td>
            <td>${safeText(line.progress_basis || (line.is_countable_sales_line ? "Counted" : "Excluded"))}</td>
            <td>${sourceBadge(line.line_source_type)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderManufacturingOrders(orders) {
  if (!orders || !orders.length) {
    return '<div class="detail-empty">No linked Manufacturing Orders / JO.</div>';
  }
  return `
    <table class="detail-table">
      <thead><tr><th>MO Number</th><th>Status</th><th>Product</th><th class="num">MO Qty</th><th class="num">Cost of Analysis</th><th class="num">Actual Cost / Unit</th><th>Cost Basis</th><th>Origin</th><th>JO</th><th>Source</th></tr></thead>
      <tbody>
        ${orders.map((order) => `
          <tr>
            <td>${safeText(order.manufacturing_order_number)}</td>
            <td>${safeText(order.manufacturing_order_state)}</td>
            <td>${safeText(order.manufactured_product_name)}</td>
            <td class="num">${formatQty(order.manufacturing_quantity)}</td>
            <td class="num">${formatAmount(order.cost_of_analysis)}</td>
            <td class="num">${formatAmount(order.actual_cost_per_unit)}</td>
            <td>${safeText(order.cost_basis)}</td>
            <td>${safeText(order.origin)}</td>
            <td>${safeText(order.job_order_number)}</td>
            <td>${safeText(order.manufacturing_source_type)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderIoBackedManufacturing(correlations) {
  if (!correlations || !correlations.length) {
    return '<div class="detail-empty">No IO-backed Manufacturing correlation found.</div>';
  }
  return `
    <table class="detail-table">
      <thead>
        <tr>
          <th>Internal Order Number</th>
          <th class="num">Related IO MO Count</th>
          <th class="num">Related IO MO Qty</th>
          <th class="num">IO Actual Cost Full</th>
          <th class="num">IO Actual Cost / Unit</th>
          <th class="num">Linked SO Count</th>
          <th class="num">Multi-IO SO Count</th>
          <th>Linked SO Qty Basis</th>
          <th class="num">Linked SO Ordered Qty</th>
          <th class="num">Linked SO Delivered Qty</th>
          <th>IO Qty Status</th>
        </tr>
      </thead>
      <tbody>
        ${correlations.map((item) => `
          <tr>
            <td>${safeText(item.internal_order_number)}</td>
            <td class="num">${formatNumber(item.io_mo_count)}</td>
            <td class="num">${formatQty(item.io_mo_qty)}</td>
            <td class="num">${formatAmount(item.io_actual_cost_full || item.io_actual_cost)}</td>
            <td class="num">${formatAmount(item.io_actual_cost_per_unit)}</td>
            <td class="num">${formatNumber(item.linked_so_count)}</td>
            <td class="num">${formatNumber(item.multi_io_so_count)}</td>
            <td>${safeText(item.linked_so_qty_basis)}</td>
            <td class="num">${formatQty(item.linked_so_ordered_qty)}</td>
            <td class="num">${formatQty(item.linked_so_delivered_qty)}</td>
            <td>${safeText(ioQtyStatusLabel(item.io_qty_correlation_status))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function detailContent(row, options = {}) {
  if (options.error) {
    return '<div class="detail-empty">Failed to load details.</div>';
  }
  if (options.loading || !row.detail_loaded) {
    return '<div class="detail-empty">Loading details...</div>';
  }
  return `
        <div class="detail-sections">
          <div class="detail-section">
            <h3>SO Lines</h3>
            ${renderLineRows(row.sales_order_lines || [])}
          </div>
          <div class="detail-section">
            <h3>Manufacturing Orders / JO</h3>
            ${renderManufacturingOrders(row.manufacturing_orders || [])}
          </div>
          <div class="detail-section">
            <h3>IO-backed Manufacturing</h3>
            ${renderIoBackedManufacturing(row.io_manufacturing_correlations || [])}
          </div>
        </div>
  `;
}

function detailRow(row, options = {}) {
  return `
    <tr class="detail-row" data-detail-so-id="${row.sales_order_id}">
      <td colspan="${Math.max(1, visibleColumnCount())}">
        ${detailContent(row, options)}
      </td>
    </tr>
  `;
}

async function loadRowDetails(soId) {
  const key = String(soId);
  const row = state.rows.find((item) => String(item.sales_order_id) === key);
  if (!row) return;

  const detailRowEl = document.querySelector(`tr[data-detail-so-id="${CSS.escape(key)}"]`);
  if (state.detailCache.has(key)) {
    Object.assign(row, state.detailCache.get(key), { detail_loaded: true });
    if (detailRowEl) detailRowEl.querySelector("td").innerHTML = detailContent(row);
    return;
  }
  if (state.detailLoading.has(key)) return;

  state.detailLoading.add(key);
  try {
    const response = await fetch(`/api/dashboard/sales-orders/${encodeURIComponent(key)}/details`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Detail request failed: ${response.status}`);
    const detail = await response.json();
    const cached = {
      sales_order_lines: detail.sales_order_lines || [],
      manufacturing_orders: detail.manufacturing_orders || [],
      io_manufacturing_correlations: detail.io_manufacturing_correlations || [],
    };
    state.detailCache.set(key, cached);
    Object.assign(row, cached, { detail_loaded: true });
    const currentDetailRow = document.querySelector(`tr[data-detail-so-id="${CSS.escape(key)}"]`);
    if (currentDetailRow) currentDetailRow.querySelector("td").innerHTML = detailContent(row);
  } catch (error) {
    console.error(error);
    const currentDetailRow = document.querySelector(`tr[data-detail-so-id="${CSS.escape(key)}"]`);
    if (currentDetailRow) currentDetailRow.querySelector("td").innerHTML = detailContent(row, { error: true });
  } finally {
    state.detailLoading.delete(key);
  }
}

function tableRow(row) {
  const expanded = state.expanded.has(String(row.sales_order_id));
  return `
    <tr data-row-so-id="${row.sales_order_id}">
      <td data-column-key="expand"><button class="row-action" type="button" data-so="${row.sales_order_id}" title="Toggle details" aria-label="Toggle details">${expanded ? "-" : "+"}</button></td>
      <td class="sales-order-number" data-column-key="sales_order_number">${safeText(row.sales_order_number)}</td>
      <td data-column-key="customer_name">${safeText(row.customer_name)}</td>
      <td data-column-key="product_type_label">${safeText(row.product_type_label)}</td>
      <td data-column-key="delivery_date">${formatDate(row.commitment_date)}</td>
      <td data-column-key="source_type">${sourceBadge(row)}</td>
      <td data-column-key="sales_order_state">${badge(row.sales_order_state, isCancelled(row) ? "status-muted" : "status-progress")}</td>
      <td data-column-key="follow_up_status">${followUpBadge(row.follow_up_status)}</td>
      <td class="num" data-column-key="related_mo_qty">${formatQty(row.total_related_mo_qty)}</td>
      <td class="num" data-column-key="produced_mo_qty">${formatQty(row.total_done_mo_qty)}</td>
      <td class="num" data-column-key="manufacturing_in_progress_qty">${formatQty(row.total_in_progress_mo_qty)}</td>
      <td data-column-key="shared_io">${safeText(row.shared_io_numbers)}</td>
      <td class="num" data-column-key="ordered_qty">${formatQty(row.ordered_qty)}</td>
      <td class="num" data-column-key="delivered_qty">${formatQty(row.delivered_qty)}</td>
      <td class="num" data-column-key="invoiced_qty">${formatQty(row.invoiced_qty)}</td>
      <td class="progress-cell" data-column-key="qty_delivery_percent">${miniProgress(row.qty_delivery_progress_ratio)}</td>
      <td class="progress-cell" data-column-key="qty_invoice_percent">${miniProgress(row.qty_invoice_progress_ratio)}</td>
      <td class="num" data-column-key="sales_amount_idr">${formatAmount(row.ordered_amount_idr)}</td>
      <td class="num" data-column-key="rkb_planned_cost">${formatAmount(row.rkb_planned_cost)}</td>
      <td class="num ${contributionClass(row.rkb_kontribusi_percent)}" data-column-key="rkb_kontribusi_percent">${formatContributionPercent(row.rkb_kontribusi_percent)}</td>
      <td class="num" data-column-key="actual_cost">${formatAmount(row.actual_cost)}</td>
      <td class="num ${contributionClass(row.kontribusi_aktual_percent)}" data-column-key="kontribusi_aktual_percent">${formatContributionPercent(row.kontribusi_aktual_percent)}</td>
      <td class="num" data-column-key="delivered_amount_idr">${formatAmount(row.delivered_amount_idr)}</td>
      <td class="num" data-column-key="invoiced_amount_idr">${formatAmount(row.invoiced_amount_idr)}</td>
      <td class="progress-cell" data-column-key="amount_delivery_percent">${miniProgress(row.amount_delivery_progress_ratio)}</td>
      <td class="progress-cell" data-column-key="amount_invoice_percent">${miniProgress(row.amount_invoice_progress_ratio)}</td>
    </tr>
    ${expanded ? detailRow(row, { loading: !row.detail_loaded }) : ""}
  `;
}
function sortableValue(row, key) {
  const numericKeys = new Set([
    "ordered_qty",
    "delivered_qty",
    "invoiced_qty",
    "qty_delivery_progress_ratio",
    "qty_invoice_progress_ratio",
    "ordered_amount",
    "delivered_amount",
    "invoiced_amount",
    "ordered_amount_idr",
    "delivered_amount_idr",
    "invoiced_amount_idr",
    "sales_amount_idr",
    "rkb_planned_cost",
    "direct_rkb_planned_cost",
    "io_correlated_rkb_planned_cost",
    "direct_actual_cost",
    "direct_actual_cost_per_unit",
    "io_backed_actual_cost",
    "io_backed_actual_cost_full",
    "io_backed_actual_cost_allocated",
    "io_backed_actual_cost_per_unit",
    "total_related_actual_cost",
    "total_related_actual_cost_full",
    "actual_cost",
    "actual_cost_quantity_based",
    "actual_cost_per_unit",
    "rkb_kontribusi_amount",
    "rkb_kontribusi_percent",
    "kontribusi_aktual_amount",
    "kontribusi_aktual_percent",
    "amount_delivery_progress_ratio",
    "amount_invoice_progress_ratio",
    "direct_mo_count",
    "direct_mo_qty",
    "io_backed_mo_count",
    "io_backed_mo_qty",
    "total_related_mo_count",
    "total_related_mo_qty",
    "total_done_mo_qty",
    "total_in_progress_mo_qty",
    "shared_io_count",
  ]);
  if (key === "commitment_date") return dateOnly(row[key]);
  if (numericKeys.has(key)) return numberValue(row[key]);
  return safeText(row[key]).toLowerCase();
}

function sortedRows(rows) {
  const direction = state.sortDirection === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const aValue = sortableValue(a, state.sortKey);
    const bValue = sortableValue(b, state.sortKey);
    if (typeof aValue === "number" && typeof bValue === "number") {
      return (aValue - bValue) * direction;
    }
    return String(aValue).localeCompare(String(bValue)) * direction;
  });
}

function updateSortIndicators() {
  document.querySelectorAll("[data-sort]").forEach((button) => {
    const active = button.dataset.sort === state.sortKey;
    button.dataset.direction = active ? state.sortDirection : "";
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function visibleColumnCount() {
  return columnController ? columnController.visibleColumnCount() : TABLE_COLUMNS.length;
}

function renderTable(rows) {
  updateSortIndicators();
  els.rowCount.textContent = `${formatNumber(rows.length)} rows`;
  if (!rows.length) {
    els.dashboardRows.innerHTML = `<tr><td colspan="${Math.max(1, visibleColumnCount())}" class="empty-cell">No Sales Orders match the current filters.</td></tr>`;
    return;
  }
  els.dashboardRows.innerHTML = rows.map(tableRow).join("");
  columnController?.apply();
}
function uniqueOptionValues(values) {
  return [...new Set((values || [])
    .filter((value) => value !== null && value !== undefined && String(value).trim())
    .map(String))];
}

function renderChecklist(filterKey) {
  const config = checklistConfigs[filterKey];
  const options = state.filterOptions[filterKey] || [];
  const selected = state.filters[filterKey];
  const summary = checklistSummary(filterKey, config.allLabel, config.label);
  const actions = filterKey === "status"
    ? `
      <div class="checklist-actions">
        <button type="button" data-checklist-action="active" data-filter="${filterKey}">Active only</button>
        <button type="button" data-checklist-action="all" data-filter="${filterKey}">All statuses</button>
      </div>`
    : `
      <div class="checklist-actions">
        <button type="button" data-checklist-action="select" data-filter="${filterKey}">Select All</button>
        <button type="button" data-checklist-action="clear" data-filter="${filterKey}">Clear</button>
      </div>`;
  config.el().innerHTML = `
    <button class="checklist-button" type="button" data-checklist-toggle="${filterKey}" aria-expanded="false">
      <span>${summary}</span>
    </button>
    <div class="checklist-menu" role="group" aria-label="${config.allLabel}">
      ${actions}
      <div class="checklist-options">
        ${options.map((value) => `
          <label class="checklist-option">
            <input type="checkbox" data-checklist-input="${filterKey}" value="${value}" ${selected.has(String(value)) ? "checked" : ""}>
            <span>${config.label(value)}</span>
          </label>
        `).join("")}
      </div>
    </div>
  `;
}

function renderChecklists() {
  Object.keys(checklistConfigs).forEach(renderChecklist);
}

function keepValidSelections(filterKey) {
  const valid = new Set(state.filterOptions[filterKey]);
  state.filters[filterKey] = new Set([...state.filters[filterKey]].filter((value) => valid.has(value)));
}

function populateFilters(filters) {
  state.filterOptions.year = uniqueOptionValues(filters.years || []).sort((a, b) => Number(b) - Number(a));
  state.filterOptions.customer = uniqueOptionValues(filters.customers || []).sort((a, b) => a.localeCompare(b));
  state.filterOptions.productType = uniqueOptionValues(filters.product_types || []).sort((a, b) => a.localeCompare(b));
  state.filterOptions.source = uniqueOptionValues(filters.source_types || []).sort((a, b) => sourceOrder.indexOf(a) - sourceOrder.indexOf(b));
  state.filterOptions.status = uniqueOptionValues(filters.sales_order_statuses || []).sort((a, b) => a.localeCompare(b));
  state.filterOptions.followUp = uniqueOptionValues(filters.follow_up_statuses || []).sort((a, b) => followUpOrder.indexOf(a) - followUpOrder.indexOf(b));

  Object.keys(state.filters).forEach(keepValidSelections);
  if (!state.filtersInitialized) {
    setDefaultYearFilter();
    setActiveOnlyStatus();
    state.filtersInitialized = true;
  }
  renderChecklists();
}

function dateOverlaps(row, fromFilter, toFilter) {
  if (!fromFilter && !toFilter) return true;
  const commitment = dateOnly(row.commitment_date);
  if (!commitment) return false;
  if (fromFilter && commitment < fromFilter) return false;
  if (toFilter && commitment > toFilter) return false;
  return true;
}

function rowMatchesCurrentFilters(row, options = {}) {
  const soTerm = els.soFilter.value.trim().toLowerCase();
  const commitmentFrom = els.commitmentFromFilter.value;
  const commitmentTo = els.commitmentToFilter.value;

  const matchesSo = !soTerm || safeText(row.sales_order_number).toLowerCase().includes(soTerm);
  const matchesYear = options.skipYear || selectionMatches("year", row.order_year);
  const matchesCustomer = options.skipCustomer || selectionMatches("customer", row.customer_name);
  const matchesProductType = options.skipProductType || selectionMatches("productType", row.product_type_label);
  const matchesSource = options.skipSource || selectionMatches("source", row.source_type);
  const matchesStatus = options.skipStatus || selectionMatches("status", row.sales_order_state);
  const matchesFollowUp = options.skipFollowUp || selectionMatches("followUp", row.follow_up_status);
  const matchesQuickFilter = !state.quickFilter
    || (state.quickFilter === "DELIVERED_SO" && row.has_delivered_qty)
    || (state.quickFilter === "INVOICED_SO" && row.has_invoiced_qty);

  return matchesSo
    && matchesYear
    && matchesCustomer
    && matchesProductType
    && matchesSource
    && matchesStatus
    && matchesFollowUp
    && matchesQuickFilter
    && dateOverlaps(row, commitmentFrom, commitmentTo);
}

function applyFilters() {
  const rowsForTable = state.rows.filter((row) => rowMatchesCurrentFilters(row));
  const rowsForStatusStrip = state.rows.filter((row) => rowMatchesCurrentFilters(row, { skipFollowUp: true }));
  const rowsForProductTypeStrip = state.rows.filter((row) => rowMatchesCurrentFilters(row, { skipProductType: true }));
  const rowsForSourceStrip = state.rows.filter((row) => rowMatchesCurrentFilters(row, { skipSource: true }));

  state.filteredRows = sortedRows(rowsForTable);
  els.activeFilterSummary.textContent = activeFilterSummary();
  els.clearSortButton.disabled = state.sortKey === "commitment_date" && state.sortDirection === "asc";

  renderKpis(state.filteredRows, rowsForSourceStrip);
  renderStatusStrip(rowsForStatusStrip);
  renderProductTypeStrip(rowsForProductTypeStrip);
  renderSourceStrip(rowsForSourceStrip);
  renderChecklists();
  renderTable(state.filteredRows);
}

function activeFilterSummary() {
  const entries = [];
  if (els.soFilter.value.trim()) entries.push(`SO: ${els.soFilter.value.trim()}`);
  if (state.filters.year.size && !setsEqualToArray(state.filters.year, state.filterOptions.year)) entries.push(`Year: ${checklistSummary("year", "All years", (value) => safeText(value))}`);
  if (state.filters.customer.size) entries.push(`Customer: ${checklistSummary("customer", "All customers", (value) => safeText(value))}`);
  if (state.filters.productType.size) entries.push(`Product Type: ${checklistSummary("productType", "All product types", (value) => safeText(value))}`);
  if (state.filters.source.size) entries.push(`Source: ${checklistSummary("source", "All sources", sourceLabel)}`);
  if (state.filters.status.size && !setsEqualToArray(state.filters.status, activeStatusValues())) entries.push(`SO Status: ${checklistSummary("status", "All statuses", (value) => safeText(value))}`);
  if (state.filters.followUp.size) entries.push(`Follow-Up: ${checklistSummary("followUp", "All follow-up", followUpLabel)}`);
  if (els.commitmentFromFilter.value || els.commitmentToFilter.value) entries.push(`Delivery Date: ${els.commitmentFromFilter.value || "..."} to ${els.commitmentToFilter.value || "..."}`);
  if (state.quickFilter) entries.push(`Quick Filter: ${quickFilterLabels[state.quickFilter] || state.quickFilter}`);
  return entries.length ? `Filters: ${entries.join(", ")}` : "Filters: Active current-year Sales Orders";
}

function clearSort() {
  state.sortKey = "commitment_date";
  state.sortDirection = "asc";
  applyFilters();
}

async function exportCurrentView() {
  const sheet = DashboardExport.buildSheetData({
    columns: TABLE_COLUMNS,
    rows: state.filteredRows,
    visibleKeys: columnController?.visibleColumnKeys(),
  });
  await DashboardExport.exportXlsx({
    endpoint: "/api/dashboard/export/xlsx",
    button: els.exportExcelButton,
    fileName: `sales_orders_${DashboardExport.timestampSuffix()}.xlsx`,
    sheetName: "Sales Orders",
    columns: sheet.columns,
    rows: sheet.rows,
  });
}
async function loadDashboard() {
  els.lastLoaded.textContent = "Loading...";
  try {
    const response = await fetch("/api/dashboard/sales-orders", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    const payload = await response.json();
    state.rows = (payload.rows || []).map((row) => ({ ...row, detail_loaded: false }));
    state.expanded.clear();
    state.detailCache.clear();
    state.detailLoading.clear();
    populateFilters(payload.filters || {});
    applyFilters();
    els.lastLoaded.textContent = `Loaded ${new Date().toLocaleString()}`;
  } catch (error) {
    els.lastLoaded.textContent = "Failed to load";
    els.dashboardRows.innerHTML = `<tr><td colspan="${Math.max(1, visibleColumnCount())}" class="empty-cell">${error.message}</td></tr>`;
  }
}

function clearFilters() {
  els.soFilter.value = "";
  els.commitmentFromFilter.value = "";
  els.commitmentToFilter.value = "";
  setDefaultYearFilter();
  state.filters.customer.clear();
  state.filters.productType.clear();
  state.filters.source.clear();
  state.filters.followUp.clear();
  setActiveOnlyStatus();
  state.quickFilter = "";
  applyFilters();
}

[els.soFilter, els.commitmentFromFilter, els.commitmentToFilter].forEach((el) => el.addEventListener("input", applyFilters));

function handleChecklistClick(event) {
  const toggle = event.target.closest("[data-checklist-toggle]");
  if (toggle) {
    const wrapper = toggle.closest(".checklist-filter");
    const wasOpen = wrapper.classList.contains("is-open");
    document.querySelectorAll(".checklist-filter.is-open").forEach((el) => {
      el.classList.remove("is-open");
      el.querySelector(".checklist-button")?.setAttribute("aria-expanded", "false");
    });
    wrapper.classList.toggle("is-open", !wasOpen);
    toggle.setAttribute("aria-expanded", !wasOpen ? "true" : "false");
    event.stopPropagation();
    return;
  }

  const action = event.target.closest("[data-checklist-action]");
  if (action) {
    const filterKey = action.dataset.filter;
    if (action.dataset.checklistAction === "select") state.filters[filterKey] = new Set(state.filterOptions[filterKey]);
    else if (action.dataset.checklistAction === "active") setActiveOnlyStatus();
    else if (action.dataset.checklistAction === "all") setAllStatuses();
    else state.filters[filterKey].clear();
    applyFilters();
    event.stopPropagation();
  }
}

function handleChecklistChange(event) {
  const input = event.target.closest("[data-checklist-input]");
  if (!input) return;
  const selected = state.filters[input.dataset.checklistInput];
  if (input.checked) selected.add(input.value);
  else selected.delete(input.value);
  applyFilters();
}

document.addEventListener("click", (event) => {
  handleChecklistClick(event);
  if (!event.target.closest(".checklist-filter")) {
    document.querySelectorAll(".checklist-filter.is-open").forEach((el) => {
      el.classList.remove("is-open");
      el.querySelector(".checklist-button")?.setAttribute("aria-expanded", "false");
    });
  }
});
document.addEventListener("change", handleChecklistChange);

els.refreshButton.addEventListener("click", loadDashboard);
els.clearFiltersButton.addEventListener("click", clearFilters);
els.clearToolbarFiltersButton.addEventListener("click", clearFilters);
els.clearSortButton.addEventListener("click", clearSort);
els.exportExcelButton.addEventListener("click", exportCurrentView);
els.salesOrderTable.addEventListener("click", (event) => {
  const button = event.target.closest("[data-sort]");
  if (!button) return;
  const key = button.dataset.sort;
  if (state.sortKey === key) {
    state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = key;
    state.sortDirection = "asc";
  }
  applyFilters();
});
els.statusStrip.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-follow-up-status]");
  if (!chip) return;
  setSingleFilter("followUp", chip.dataset.followUpStatus);
});
els.productTypeStrip.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-product-type]");
  if (!chip) return;
  setSingleFilter("productType", decodeURIComponent(chip.dataset.productType));
});
els.sourceStrip.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-source-type]");
  if (!chip) return;
  setSingleFilter("source", chip.dataset.sourceType);
});
function handleKpiAction(card) {
  const action = card.dataset.kpiAction;
  if (action === "ACTIVE_SO") {
    setActiveOnlyStatus();
    state.quickFilter = "";
    applyFilters();
    return;
  }
  if (action === "DELIVERED_SO" || action === "INVOICED_SO") {
    toggleQuickFilter(action);
    return;
  }
  if (action === "DELAYED_DELIVERY" || action === "WAITING_INVOICE") {
    setFollowUpFilter(action);
  }
}

els.kpiGrid.addEventListener("click", (event) => {
  const kpiCard = event.target.closest("[data-kpi-action]");
  if (kpiCard) {
    handleKpiAction(kpiCard);
    return;
  }
  const sourceCard = event.target.closest("[data-source-type]");
  if (!sourceCard) return;
  setSingleFilter("source", sourceCard.dataset.sourceType);
});
els.kpiGrid.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const kpiCard = event.target.closest("[data-kpi-action]");
  const sourceCard = event.target.closest("[data-source-type]");
  const card = kpiCard || sourceCard;
  if (!card) return;
  event.preventDefault();
  if (kpiCard) handleKpiAction(kpiCard);
  else setSingleFilter("source", sourceCard.dataset.sourceType);
});
els.dashboardRows.addEventListener("click", (event) => {
  const button = event.target.closest("[data-so]");
  if (!button) return;
  const soId = String(button.dataset.so);
  const mainRow = button.closest("tr[data-row-so-id]");
  if (!mainRow) return;

  const existingDetail = els.dashboardRows.querySelector(`tr[data-detail-so-id="${CSS.escape(soId)}"]`);
  if (existingDetail) {
    existingDetail.remove();
    state.expanded.delete(soId);
    button.textContent = "+";
    return;
  }

  const row = state.rows.find((item) => String(item.sales_order_id) === soId);
  if (!row) return;
  state.expanded.add(soId);
  button.textContent = "-";
  if (state.detailCache.has(soId)) {
    Object.assign(row, state.detailCache.get(soId), { detail_loaded: true });
    mainRow.insertAdjacentHTML("afterend", detailRow(row));
    return;
  }

  row.detail_loaded = false;
  mainRow.insertAdjacentHTML("afterend", detailRow(row, { loading: true }));
  loadRowDetails(soId);
});

columnController = DashboardTableTools.createColumnController({
  storageKey: COLUMN_STORAGE_KEY,
  columns: TABLE_COLUMNS,
  defaultVisibleKeys: DEFAULT_VISIBLE_COLUMNS,
  button: els.columnsButton,
  panel: els.columnsPanel,
  list: els.columnsList,
  showAllButton: els.columnsShowAllButton,
  resetButton: els.columnsResetButton,
  root: els.salesOrderTable,
});

updateSortIndicators();
loadDashboard();






