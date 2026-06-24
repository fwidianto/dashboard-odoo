const state = {
  rows: [],
  filteredRows: [],
  expanded: new Set(),
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  soFilter: document.getElementById("soFilter"),
  customerFilter: document.getElementById("customerFilter"),
  commitmentFromFilter: document.getElementById("commitmentFromFilter"),
  commitmentToFilter: document.getElementById("commitmentToFilter"),
  sourceFilter: document.getElementById("sourceFilter"),
  statusFilter: document.getElementById("statusFilter"),
  followUpFilter: document.getElementById("followUpFilter"),
  statusStrip: document.getElementById("statusStrip"),
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

function miniProgress(value) {
  return `
    <div class="progress-value"><span>${formatPercent(value)}</span></div>
    <div class="mini-progress"><span style="width:${progressWidth(value)}"></span></div>
  `;
}

function summarize(rows) {
  const active = rows.filter((row) => row.follow_up_status !== "CANCELLED_RECORD");
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

  els.statusStrip.innerHTML = order
    .filter((status) => counts[status])
    .map((status) => `
      <span class="status-chip ${cssClassForFollowUp(status)}">
        ${followUpLabels[status] || status}
        <strong>${counts[status]}</strong>
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

function detailRow(row) {
  const diagnostics = row.diagnostics || {};
  return `
    <tr class="detail-row">
      <td colspan="17">
        <div class="detail-grid">
          <div class="detail-item"><span>Delivery Status</span><strong>${safeText(row.delivery_status)}</strong></div>
          <div class="detail-item"><span>Invoice Status</span><strong>${safeText(row.invoice_status)}</strong></div>
          <div class="detail-item"><span>IO Count</span><strong>${formatNumber(row.internal_order_count)}</strong></div>
          <div class="detail-item"><span>MO Count</span><strong>${formatNumber(row.manufacturing_order_count)}</strong></div>
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
      <td>${formatDate(row.commitment_date)}</td>
      <td>${sourceBadge(row.source_type)}</td>
      <td>${badge(row.sales_order_state, row.is_cancelled ? "status-muted" : "status-progress")}</td>
      <td>${followUpBadge(row.follow_up_status)}</td>
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

function renderTable(rows) {
  els.rowCount.textContent = `${formatNumber(rows.length)} rows`;
  if (!rows.length) {
    els.dashboardRows.innerHTML = '<tr><td colspan="17" class="empty-cell">No Sales Orders match the current filters.</td></tr>';
    return;
  }
  els.dashboardRows.innerHTML = rows.map(tableRow).join("");
}

function populateSelect(select, values) {
  const first = select.querySelector("option")?.outerHTML || '<option value="">All</option>';
  select.innerHTML = first + values.map((value) => `<option value="${value}">${value}</option>`).join("");
}

function populateFilters(filters) {
  populateSelect(els.customerFilter, filters.customers || []);
  populateSelect(els.sourceFilter, filters.source_types || []);
  populateSelect(els.statusFilter, filters.sales_order_statuses || []);
  populateSelect(els.followUpFilter, filters.follow_up_statuses || []);
}

function dateOverlaps(row, fromFilter, toFilter) {
  if (!fromFilter && !toFilter) return true;
  const commitment = dateOnly(row.commitment_date);
  if (!commitment) return false;
  if (fromFilter && commitment < fromFilter) return false;
  if (toFilter && commitment > toFilter) return false;
  return true;
}

function applyFilters() {
  const soTerm = els.soFilter.value.trim().toLowerCase();
  const customer = els.customerFilter.value;
  const source = els.sourceFilter.value;
  const status = els.statusFilter.value;
  const followUp = els.followUpFilter.value;
  const commitmentFrom = els.commitmentFromFilter.value;
  const commitmentTo = els.commitmentToFilter.value;

  state.filteredRows = state.rows.filter((row) => {
    const matchesSo = !soTerm || safeText(row.sales_order_number).toLowerCase().includes(soTerm);
    const matchesCustomer = !customer || row.customer_name === customer;
    const matchesSource = !source || row.source_type === source;
    const matchesStatus = !status || row.sales_order_state === status;
    const matchesFollowUp = !followUp || row.follow_up_status === followUp;
    return matchesSo && matchesCustomer && matchesSource && matchesStatus && matchesFollowUp && dateOverlaps(row, commitmentFrom, commitmentTo);
  });

  renderKpis(state.filteredRows);
  renderStatusStrip(state.filteredRows);
  renderTable(state.filteredRows);
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
    els.dashboardRows.innerHTML = `<tr><td colspan="17" class="empty-cell">${error.message}</td></tr>`;
  }
}

function clearFilters() {
  els.soFilter.value = "";
  els.customerFilter.value = "";
  els.commitmentFromFilter.value = "";
  els.commitmentToFilter.value = "";
  els.sourceFilter.value = "";
  els.statusFilter.value = "";
  els.followUpFilter.value = "";
  applyFilters();
}

[
  els.soFilter,
  els.customerFilter,
  els.commitmentFromFilter,
  els.commitmentToFilter,
  els.sourceFilter,
  els.statusFilter,
  els.followUpFilter,
].forEach((el) => el.addEventListener("input", applyFilters));

els.refreshButton.addEventListener("click", loadDashboard);
els.clearFiltersButton.addEventListener("click", clearFilters);
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

loadDashboard();
