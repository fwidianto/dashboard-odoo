const ACTIVE_STATUS_FILTER = "__ACTIVE__";
const DEFAULT_YEAR_FILTER = "2026";

const state = {
  rows: [],
  filteredRows: [],
  expanded: new Set(),
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
  exportExcelButton: document.getElementById("exportExcelButton"),
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
      <thead><tr><th>MO Number</th><th>Status</th><th>Product</th><th class="num">Qty</th><th>Origin</th><th>JO</th><th>Source</th></tr></thead>
      <tbody>
        ${orders.map((order) => `
          <tr>
            <td>${safeText(order.manufacturing_order_number)}</td>
            <td>${safeText(order.manufacturing_order_state)}</td>
            <td>${safeText(order.manufactured_product_name)}</td>
            <td class="num">${formatQty(order.manufacturing_quantity)}</td>
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

function detailRow(row) {
  return `
    <tr class="detail-row">
      <td colspan="22">
        <div class="detail-sections">
          <div class="detail-section">
            <h3>SO Lines</h3>
            ${row.detail_loaded ? renderLineRows(row.sales_order_lines || []) : '<div class="detail-empty">Loading SO lines...</div>'}
          </div>
          <div class="detail-section">
            <h3>Manufacturing Orders / JO</h3>
            ${row.detail_loaded ? renderManufacturingOrders(row.manufacturing_orders || []) : '<div class="detail-empty">Loading Manufacturing Orders / JO...</div>'}
          </div>
          <div class="detail-section">
            <h3>IO-backed Manufacturing</h3>
            ${row.detail_loaded ? renderIoBackedManufacturing(row.io_manufacturing_correlations || []) : '<div class="detail-empty">Loading IO-backed Manufacturing...</div>'}
          </div>
        </div>
      </td>
    </tr>
  `;
}

async function loadRowDetails(soId) {
  const row = state.rows.find((item) => String(item.sales_order_id) === String(soId));
  if (!row || row.detail_loaded || state.detailLoading.has(String(soId))) return;
  state.detailLoading.add(String(soId));
  try {
    const response = await fetch(`/api/dashboard/sales-orders/${encodeURIComponent(soId)}/details`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Detail request failed: ${response.status}`);
    const detail = await response.json();
    row.sales_order_lines = detail.sales_order_lines || [];
    row.manufacturing_orders = detail.manufacturing_orders || [];
    row.io_manufacturing_correlations = detail.io_manufacturing_correlations || [];
    row.detail_loaded = true;
  } catch (error) {
    row.sales_order_lines = [];
    row.manufacturing_orders = [];
    row.io_manufacturing_correlations = [];
    row.detail_loaded = true;
    console.error(error);
  } finally {
    state.detailLoading.delete(String(soId));
    renderTable(state.filteredRows);
  }
}
function tableRow(row) {
  const expanded = state.expanded.has(String(row.sales_order_id));
  return `
    <tr>
      <td><button class="row-action" type="button" data-so="${row.sales_order_id}" title="Toggle details" aria-label="Toggle details">${expanded ? "-" : "+"}</button></td>
      <td class="sales-order-number">${safeText(row.sales_order_number)}</td>
      <td>${safeText(row.customer_name)}</td>
      <td>${safeText(row.product_type_label)}</td>
      <td>${formatDate(row.commitment_date)}</td>
      <td>${sourceBadge(row)}</td>
      <td>${badge(row.sales_order_state, isCancelled(row) ? "status-muted" : "status-progress")}</td>
      <td>${followUpBadge(row.follow_up_status)}</td>
      <td class="num">${formatQty(row.total_related_mo_qty)}</td>
      <td class="num">${formatQty(row.total_done_mo_qty)}</td>
      <td class="num">${formatQty(row.total_in_progress_mo_qty)}</td>
      <td>${safeText(row.shared_io_numbers)}</td>
      <td class="num">${formatQty(row.ordered_qty)}</td>
      <td class="num">${formatQty(row.delivered_qty)}</td>
      <td class="num">${formatQty(row.invoiced_qty)}</td>
      <td class="progress-cell">${miniProgress(row.qty_delivery_progress_ratio)}</td>
      <td class="progress-cell">${miniProgress(row.qty_invoice_progress_ratio)}</td>
      <td class="num">${formatAmount(row.ordered_amount_idr)}</td>
      <td class="num">${formatAmount(row.delivered_amount_idr)}</td>
      <td class="num">${formatAmount(row.invoiced_amount_idr)}</td>
      <td class="progress-cell">${miniProgress(row.amount_delivery_progress_ratio)}</td>
      <td class="progress-cell">${miniProgress(row.amount_invoice_progress_ratio)}</td>
    </tr>
    ${expanded ? detailRow(row) : ""}
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

function renderTable(rows) {
  updateSortIndicators();
  els.rowCount.textContent = `${formatNumber(rows.length)} rows`;
  if (!rows.length) {
    els.dashboardRows.innerHTML = '<tr><td colspan="22" class="empty-cell">No Sales Orders match the current filters.</td></tr>';
    return;
  }
  els.dashboardRows.innerHTML = rows.map(tableRow).join("");
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

  renderKpis(state.filteredRows, rowsForSourceStrip);
  renderStatusStrip(rowsForStatusStrip);
  renderProductTypeStrip(rowsForProductTypeStrip);
  renderSourceStrip(rowsForSourceStrip);
  renderChecklists();
  renderTable(state.filteredRows);
}

function csvCell(value) {
  let text = safeText(value);
  if (text === "-") text = "";
  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }
  return `"${text.replace(/"/g, '""')}"`;
}

function exportFilteredRows() {
  if (!state.filteredRows.length) {
    window.alert("No rows to export with the current filters.");
    return;
  }

  const columns = [
    ["Year", "order_year"],
    ["SO Number", "sales_order_number"],
    ["Customer", "customer_name"],
    ["Product Type", "product_type_label"],
    ["Delivery Date", (row) => dateOnly(row.commitment_date)],
    ["Source Type", (row) => sourceLabel(row)],
    ["SO Status", "sales_order_state"],
    ["Follow-Up", (row) => followUpLabel(row.follow_up_status)],
    ["Ordered Qty", "ordered_qty"],
    ["Delivered Qty", "delivered_qty"],
    ["Invoiced Qty", "invoiced_qty"],
    ["Qty Delivery %", (row) => formatPercent(row.qty_delivery_progress_ratio)],
    ["Qty Invoice %", (row) => formatPercent(row.qty_invoice_progress_ratio)],
    ["Ordered Amount IDR", "ordered_amount_idr"],
    ["Delivered Amount IDR", "delivered_amount_idr"],
    ["Invoiced Amount IDR", "invoiced_amount_idr"],
    ["Amount Delivery %", (row) => formatPercent(row.amount_delivery_progress_ratio)],
    ["Amount Invoice %", (row) => formatPercent(row.amount_invoice_progress_ratio)],
    ["IO Count", "internal_order_count"],
    ["Direct MO Count", "direct_mo_count"],
    ["Direct MO Qty", "direct_mo_qty"],
    ["Related IO MO Count", "io_backed_mo_count"],
    ["Related IO MO Qty", "io_backed_mo_qty"],
    ["Total Related MO Count", "total_related_mo_count"],
    ["Related MO Qty", "total_related_mo_qty"],
    ["Produced MO Qty", "total_done_mo_qty"],
    ["Manufacturing In Progress Qty", "total_in_progress_mo_qty"],
    ["Shared IO", "shared_io_numbers"],
    ["Shared IO Count", "shared_io_count"],
    ["Multi-IO SO Count", "multi_io_so_count"],
    ["Has Multi-IO SO", (row) => row.has_multi_io_so ? "Yes" : "No"],
    ["Linked SO Qty Basis", "linked_so_qty_basis"],
    ["IO Qty Status", "io_qty_correlation_status"],
    ["Accounting Lines", "accounting_line_count"],
  ];

  const header = columns.map(([label]) => csvCell(label)).join(",");
  const rows = state.filteredRows.map((row) => columns
    .map(([, accessor]) => csvCell(typeof accessor === "function" ? accessor(row) : row[accessor]))
    .join(","));
  const csv = `\uFEFF${[header, ...rows].join("\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `sales_orders_traceability_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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
    state.detailLoading.clear();
    populateFilters(payload.filters || {});
    applyFilters();
    els.lastLoaded.textContent = `Loaded ${new Date().toLocaleString()}`;
  } catch (error) {
    els.lastLoaded.textContent = "Failed to load";
    els.dashboardRows.innerHTML = `<tr><td colspan="22" class="empty-cell">${error.message}</td></tr>`;
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
els.exportExcelButton.addEventListener("click", exportFilteredRows);
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
  if (state.expanded.has(soId)) {
    state.expanded.delete(soId);
  } else {
    state.expanded.add(soId);
  }
  renderTable(state.filteredRows);
});

updateSortIndicators();
loadDashboard();
