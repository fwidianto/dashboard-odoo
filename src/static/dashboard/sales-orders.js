const ACTIVE_STATUS_FILTER = "__ACTIVE__";

const state = {
  rows: [],
  filteredRows: [],
  expanded: new Set(),
  sortKey: "commitment_date",
  sortDirection: "asc",
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  exportExcelButton: document.getElementById("exportExcelButton"),
  soFilter: document.getElementById("soFilter"),
  customerFilter: document.getElementById("customerFilter"),
  productTypeFilter: document.getElementById("productTypeFilter"),
  commitmentFromFilter: document.getElementById("commitmentFromFilter"),
  commitmentToFilter: document.getElementById("commitmentToFilter"),
  sourceFilter: document.getElementById("sourceFilter"),
  statusFilter: document.getElementById("statusFilter"),
  followUpFilter: document.getElementById("followUpFilter"),
  statusStrip: document.getElementById("statusStrip"),
  productTypeStrip: document.getElementById("productTypeStrip"),
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
  kpiUnknownSource: document.getElementById("kpiUnknownSource"),
  barQtyDelivery: document.getElementById("barQtyDelivery"),
  barQtyInvoice: document.getElementById("barQtyInvoice"),
  barAmountDelivery: document.getElementById("barAmountDelivery"),
  barAmountInvoice: document.getElementById("barAmountInvoice"),
};

const sourceLabels = {
  FROM_STOCK: "From stock",
  FROM_INTERNAL_ORDER: "From IO",
  MAKE_TO_ORDER: "Make to order / JO",
  MIXED_SOURCE: "Mixed source",
  UNKNOWN_SOURCE: "Unknown source",
  CANCELLED_RECORD: "Cancelled",
};

const followUpLabels = {
  CANCELLED_RECORD: "Cancelled",
  UNKNOWN_SOURCE: "Unknown source",
  DELAYED_DELIVERY: "Delayed delivery",
  WAITING_PRODUCTION: "Waiting production",
  WAITING_DELIVERY: "Waiting delivery",
  WAITING_INVOICE: "Waiting invoice",
  COMPLETED: "Completed",
};

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
  if (source === "MAKE_TO_ORDER") return "status-followup";
  if (source === "UNKNOWN_SOURCE") return "status-danger";
  if (source === "CANCELLED_RECORD") return "status-muted";
  return "status-muted";
}

function badge(label, className) {
  return `<span class="status-badge ${className}">${safeText(label)}</span>`;
}

function sourceBadge(source) {
  return badge(sourceLabels[source] || source, cssClassForSource(source));
}

function followUpBadge(status) {
  return badge(followUpLabels[status] || status, cssClassForFollowUp(status));
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
    unknownSource: active.filter((row) => row.source_type === "UNKNOWN_SOURCE").length,
  };
}

function renderKpis(rows) {
  const summary = summarize(rows);
  els.kpiActiveSo.textContent = formatNumber(summary.activeSalesOrders);
  els.kpiDeliveredSo.textContent = formatNumber(summary.deliveredSalesOrders);
  els.kpiInvoicedSo.textContent = formatNumber(summary.invoicedSalesOrders);
  els.kpiDelayedDelivery.textContent = formatNumber(summary.delayedDelivery);
  els.kpiWaitingInvoice.textContent = formatNumber(summary.waitingInvoice);
  els.kpiQtyDelivery.textContent = formatPercent(summary.qtyDeliveryProgress);
  els.kpiQtyInvoice.textContent = formatPercent(summary.qtyInvoiceProgress);
  els.kpiAmountDelivery.textContent = formatPercent(summary.amountDeliveryProgress);
  els.kpiAmountInvoice.textContent = formatPercent(summary.amountInvoiceProgress);
  els.kpiFromIo.textContent = formatNumber(summary.fromIo);
  els.kpiMakeToOrder.textContent = formatNumber(summary.makeToOrder);
  els.kpiFromStock.textContent = formatNumber(summary.fromStock);
  els.kpiUnknownSource.textContent = formatNumber(summary.unknownSource);
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

  const selectedFollowUp = els.followUpFilter.value;
  els.statusStrip.innerHTML = order
    .filter((status) => counts[status])
    .map((status) => `
      <button class="status-chip ${cssClassForFollowUp(status)} ${selectedFollowUp === status ? "is-active" : ""}" type="button" data-follow-up-status="${status}">
        ${followUpLabels[status] || status}
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
      <span class="status-chip product-type-chip">
        ${safeText(label)}
        <strong>${formatNumber(count)}</strong>
      </span>
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
          <th class="num">Ordered</th>
          <th class="num">Delivered</th>
          <th class="num">Invoiced</th>
          <th class="num">Unit Price</th>
          <th>Qty Delivery</th>
          <th>Qty Invoice</th>
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
            <td class="num">${formatAmount(line.unit_price)}</td>
            <td>${formatPercent(line.qty_delivery_progress_ratio)}</td>
            <td>${formatPercent(line.qty_invoice_progress_ratio)}</td>
            <td>${sourceBadge(line.line_source_type)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderInternalOrders(orders) {
  if (!orders || !orders.length) {
    return '<div class="detail-empty">No linked Internal Orders.</div>';
  }
  return `
    <table class="detail-table">
      <thead><tr><th>Internal Order ID</th><th>Internal Order Number</th><th>Raw SO IO Field</th></tr></thead>
      <tbody>
        ${orders.map((order) => `
          <tr>
            <td>${safeText(order.internal_order_id)}</td>
            <td>${safeText(order.internal_order_number)}</td>
            <td>${safeText(order.raw_x_studio_io_1)}</td>
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
  const diagnostics = row.diagnostics || {};
  return `
    <tr class="detail-row">
      <td colspan="21">
        <div class="detail-grid">
          <div class="detail-item"><span>Company</span><strong>${safeText(row.company_id)}</strong></div>
          <div class="detail-item"><span>Raw Product Type</span><strong>${safeText(row.product_type_raw)}</strong></div>
          <div class="detail-item"><span>Delivery Status</span><strong>${safeText(row.delivery_status)}</strong></div>
          <div class="detail-item"><span>Invoice Status</span><strong>${safeText(row.invoice_status)}</strong></div>
          <div class="detail-item"><span>IO Count</span><strong>${formatNumber(row.internal_order_count)}</strong></div>
          <div class="detail-item"><span>Direct MO Count</span><strong>${formatNumber(row.direct_mo_count)}</strong></div>
          <div class="detail-item"><span>Related IO MO Count</span><strong>${formatNumber(row.io_backed_mo_count)}</strong></div>
          <div class="detail-item"><span>Related IO MO Qty</span><strong>${formatQty(row.io_backed_mo_qty)}</strong></div>
          <div class="detail-item"><span>Total Related MO Count</span><strong>${formatNumber(row.total_related_mo_count)}</strong></div>
          <div class="detail-item"><span>Total Related MO Qty</span><strong>${formatQty(row.total_related_mo_qty)}</strong></div>
          <div class="detail-item"><span>Shared IO</span><strong>${formatNumber(row.shared_io_count)}</strong></div>
          <div class="detail-item"><span>Multi-IO SO Count</span><strong>${formatNumber(row.multi_io_so_count)}</strong></div>
          <div class="detail-item"><span>Has Multi-IO SO</span><strong>${row.has_multi_io_so ? "Yes" : "No"}</strong></div>
          <div class="detail-item"><span>Linked SO Qty Basis</span><strong>${safeText(row.linked_so_qty_basis)}</strong></div>
          <div class="detail-item"><span>IO Qty Status</span><strong>${safeText(ioQtyStatusLabel(row.io_qty_correlation_status))}</strong></div>
          <div class="detail-item"><span>Accounting Lines</span><strong>${formatNumber(row.accounting_line_count)}</strong></div>
          <div class="detail-item"><span>Source Link</span><strong>${safeText(row.source_link_status)}</strong></div>
          <div class="detail-item"><span>Stock Moves</span><strong>${formatNumber(diagnostics.stock_movement_diagnostic_count)}</strong></div>
          <div class="detail-item"><span>Unknown Moves</span><strong>${formatNumber(diagnostics.unknown_movement_diagnostic_count)}</strong></div>
          <div class="detail-section">
            <h3>SO Lines</h3>
            ${renderLineRows(row.sales_order_lines || [])}
          </div>
          <div class="detail-section">
            <h3>Internal Orders</h3>
            ${renderInternalOrders(row.internal_orders || [])}
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
      </td>
    </tr>
  `;
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
      <td>${sourceBadge(row.source_type)}</td>
      <td>${badge(row.sales_order_state, isCancelled(row) ? "status-muted" : "status-progress")}</td>
      <td>${followUpBadge(row.follow_up_status)}</td>
      <td class="num">${formatNumber(row.total_related_mo_count)}</td>
      <td class="num">${formatQty(row.total_related_mo_qty)}</td>
      <td class="num">${formatNumber(row.shared_io_count)}</td>
      <td class="num">${formatQty(row.ordered_qty)}</td>
      <td class="num">${formatQty(row.delivered_qty)}</td>
      <td class="num">${formatQty(row.invoiced_qty)}</td>
      <td class="progress-cell">${miniProgress(row.qty_delivery_progress_ratio)}</td>
      <td class="progress-cell">${miniProgress(row.qty_invoice_progress_ratio)}</td>
      <td class="num">${formatAmount(row.ordered_amount)}</td>
      <td class="num">${formatAmount(row.delivered_amount)}</td>
      <td class="num">${formatAmount(row.invoiced_amount)}</td>
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
    els.dashboardRows.innerHTML = '<tr><td colspan="21" class="empty-cell">No Sales Orders match the current filters.</td></tr>';
    return;
  }
  els.dashboardRows.innerHTML = rows.map(tableRow).join("");
}

function populateSelect(select, values, firstOptions = null) {
  const options = firstOptions || [{ value: "", label: "All" }];
  select.innerHTML = options
    .map((option) => `<option value="${option.value}">${option.label}</option>`)
    .join("") + values.map((value) => `<option value="${value}">${value}</option>`).join("");
}

function restoreSelectValue(select, previousValue, fallback = "") {
  const hasPrevious = Array.from(select.options).some((option) => option.value === previousValue);
  select.value = hasPrevious ? previousValue : fallback;
}

function populateFilters(filters) {
  const previous = {
    customer: els.customerFilter.value,
    productType: els.productTypeFilter.value,
    source: els.sourceFilter.value,
    status: els.statusFilter.value || ACTIVE_STATUS_FILTER,
    followUp: els.followUpFilter.value,
  };

  populateSelect(els.customerFilter, filters.customers || [], [{ value: "", label: "All customers" }]);
  populateSelect(els.productTypeFilter, filters.product_types || [], [{ value: "", label: "All product types" }]);
  populateSelect(els.sourceFilter, filters.source_types || [], [{ value: "", label: "All sources" }]);
  populateSelect(els.statusFilter, filters.sales_order_statuses || [], [
    { value: ACTIVE_STATUS_FILTER, label: "Active only" },
    { value: "", label: "All statuses" },
  ]);
  populateSelect(els.followUpFilter, filters.follow_up_statuses || [], [{ value: "", label: "All follow-up" }]);

  restoreSelectValue(els.customerFilter, previous.customer);
  restoreSelectValue(els.productTypeFilter, previous.productType);
  restoreSelectValue(els.sourceFilter, previous.source);
  restoreSelectValue(els.statusFilter, previous.status, ACTIVE_STATUS_FILTER);
  restoreSelectValue(els.followUpFilter, previous.followUp);
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
  const customer = els.customerFilter.value;
  const productType = els.productTypeFilter.value;
  const source = els.sourceFilter.value;
  const status = els.statusFilter.value;
  const followUp = els.followUpFilter.value;
  const commitmentFrom = els.commitmentFromFilter.value;
  const commitmentTo = els.commitmentToFilter.value;

  const matchesSo = !soTerm || safeText(row.sales_order_number).toLowerCase().includes(soTerm);
  const matchesCustomer = !customer || row.customer_name === customer;
  const matchesProductType = !productType || row.product_type_label === productType;
  const matchesSource = !source || row.source_type === source;
  const matchesStatus = status === ACTIVE_STATUS_FILTER ? !isCancelled(row) : !status || row.sales_order_state === status;
  const matchesFollowUp = options.skipFollowUp || !followUp || row.follow_up_status === followUp;

  return matchesSo
    && matchesCustomer
    && matchesProductType
    && matchesSource
    && matchesStatus
    && matchesFollowUp
    && dateOverlaps(row, commitmentFrom, commitmentTo);
}

function applyFilters() {
  const rowsForTable = state.rows.filter((row) => rowMatchesCurrentFilters(row));
  const rowsForStatusStrip = state.rows.filter((row) => rowMatchesCurrentFilters(row, { skipFollowUp: true }));

  state.filteredRows = sortedRows(rowsForTable);

  renderKpis(state.filteredRows);
  renderStatusStrip(rowsForStatusStrip);
  renderProductTypeStrip(state.filteredRows);
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
    ["SO Number", "sales_order_number"],
    ["Customer", "customer_name"],
    ["Product Type", "product_type_label"],
    ["Commitment Date", (row) => dateOnly(row.commitment_date)],
    ["Source Type", (row) => sourceLabels[row.source_type] || row.source_type],
    ["SO Status", "sales_order_state"],
    ["Follow-Up", (row) => followUpLabels[row.follow_up_status] || row.follow_up_status],
    ["Ordered Qty", "ordered_qty"],
    ["Delivered Qty", "delivered_qty"],
    ["Invoiced Qty", "invoiced_qty"],
    ["Qty Delivery %", (row) => formatPercent(row.qty_delivery_progress_ratio)],
    ["Qty Invoice %", (row) => formatPercent(row.qty_invoice_progress_ratio)],
    ["Ordered Amount", "ordered_amount"],
    ["Delivered Amount", "delivered_amount"],
    ["Invoiced Amount", "invoiced_amount"],
    ["Amount Delivery %", (row) => formatPercent(row.amount_delivery_progress_ratio)],
    ["Amount Invoice %", (row) => formatPercent(row.amount_invoice_progress_ratio)],
    ["IO Count", "internal_order_count"],
    ["Direct MO Count", "direct_mo_count"],
    ["Direct MO Qty", "direct_mo_qty"],
    ["Related IO MO Count", "io_backed_mo_count"],
    ["Related IO MO Qty", "io_backed_mo_qty"],
    ["Total Related MO Count", "total_related_mo_count"],
    ["Total Related MO Qty", "total_related_mo_qty"],
    ["Shared IO", "shared_io_count"],
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
    state.rows = payload.rows || [];
    state.expanded.clear();
    populateFilters(payload.filters || {});
    applyFilters();
    els.lastLoaded.textContent = `Loaded ${new Date().toLocaleString()}`;
  } catch (error) {
    els.lastLoaded.textContent = "Failed to load";
    els.dashboardRows.innerHTML = `<tr><td colspan="21" class="empty-cell">${error.message}</td></tr>`;
  }
}

function clearFilters() {
  els.soFilter.value = "";
  els.customerFilter.value = "";
  els.productTypeFilter.value = "";
  els.commitmentFromFilter.value = "";
  els.commitmentToFilter.value = "";
  els.sourceFilter.value = "";
  els.statusFilter.value = ACTIVE_STATUS_FILTER;
  els.followUpFilter.value = "";
  applyFilters();
}

[
  els.soFilter,
  els.customerFilter,
  els.productTypeFilter,
  els.commitmentFromFilter,
  els.commitmentToFilter,
  els.sourceFilter,
  els.statusFilter,
  els.followUpFilter,
].forEach((el) => el.addEventListener("input", applyFilters));

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
  const status = chip.dataset.followUpStatus;
  els.followUpFilter.value = els.followUpFilter.value === status ? "" : status;
  applyFilters();
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
