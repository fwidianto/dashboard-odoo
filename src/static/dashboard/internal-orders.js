const COLUMN_STORAGE_KEY = "dashboard.visibleColumns.internalOrders.v1";
const TABLE_COLUMNS = [
  { key: "expand", label: "Detail", defaultVisible: true, fixed: true, exportable: false },
  { key: "io_number", label: "IO Number", defaultVisible: true, exportLabel: "IO Number", exportValue: (row) => safeText(row.internal_order_number) },
  { key: "status", label: "Status", defaultVisible: true, exportLabel: "Status", exportValue: (row) => row.status_summary || "" },
  { key: "products", label: "Products", defaultVisible: true, exportLabel: "Products", exportType: "number", exportValue: (row) => numberValue(row.product_count) },
  { key: "mo", label: "MO", defaultVisible: true, exportLabel: "MO", exportType: "number", exportValue: (row) => numberValue(row.linked_mo_count) },
  { key: "so", label: "SO", defaultVisible: true, exportLabel: "SO", exportType: "number", exportValue: (row) => numberValue(row.linked_so_count) },
  { key: "delivery_percent", label: "Delivery %", defaultVisible: true, exportLabel: "Delivery %", exportType: "percent", exportValue: (row) => row.so_delivery_progress_ratio },
  { key: "invoice_percent", label: "Invoice %", defaultVisible: true, exportLabel: "Invoice %", exportType: "percent", exportValue: (row) => row.so_invoice_progress_ratio },
  { key: "receipt_percent", label: "Receipt %", defaultVisible: true, exportLabel: "Receipt %", exportType: "percent", exportValue: (row) => row.po_receipt_progress_ratio },
  { key: "billing_percent", label: "Billing %", defaultVisible: false, exportLabel: "Billing %", exportType: "percent", exportValue: (row) => row.po_invoice_progress_ratio },
  { key: "traceability", label: "Traceability", defaultVisible: true, exportLabel: "Traceability", exportValue: (row) => statusLabels[row.traceability_status] || row.traceability_status || "" },
];

const DEFAULT_VISIBLE_COLUMNS = TABLE_COLUMNS.filter((column) => column.defaultVisible).map((column) => column.key);

const state = {
  rows: [],
  filteredRows: [],
  expanded: new Set(),
  pagination: {
    page: 1,
    pageSize: 100,
  },
};

const els = {
  refreshButton: document.getElementById("refreshButton"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  clearToolbarFiltersButton: document.getElementById("clearToolbarFiltersButton"),
  exportExcelButton: document.getElementById("exportExcelButton"),
  columnsButton: document.getElementById("columnsButton"),
  columnsPanel: document.getElementById("columnsPanel"),
  columnsList: document.getElementById("columnsList"),
  columnsShowAllButton: document.getElementById("columnsShowAllButton"),
  columnsResetButton: document.getElementById("columnsResetButton"),
  dateFromFilter: document.getElementById("dateFromFilter"),
  dateToFilter: document.getElementById("dateToFilter"),
  ioFilter: document.getElementById("ioFilter"),
  requesterFilter: document.getElementById("requesterFilter"),
  statusFilter: document.getElementById("statusFilter"),
  traceabilityFilter: document.getElementById("traceabilityFilter"),
  statusStrip: document.getElementById("statusStrip"),
  dashboardRows: document.getElementById("dashboardRows"),
  rowCount: document.getElementById("rowCount"),
  lastLoaded: document.getElementById("lastLoaded"),
  activeFilterSummary: document.getElementById("activeFilterSummary"),
  internalOrdersTable: document.getElementById("internalOrdersTable"),
  kpiActiveIo: document.getElementById("kpiActiveIo"),
  kpiWithMo: document.getElementById("kpiWithMo"),
  kpiWithSo: document.getElementById("kpiWithSo"),
  kpiDelivered: document.getElementById("kpiDelivered"),
  kpiInvoiced: document.getElementById("kpiInvoiced"),
  kpiDeliveryProgress: document.getElementById("kpiDeliveryProgress"),
  kpiInvoiceProgress: document.getElementById("kpiInvoiceProgress"),
  kpiPoReceipt: document.getElementById("kpiPoReceipt"),
  kpiPoBilling: document.getElementById("kpiPoBilling"),
  barDelivery: document.getElementById("barDelivery"),
  barInvoice: document.getElementById("barInvoice"),
  barReceipt: document.getElementById("barReceipt"),
  barBilling: document.getElementById("barBilling"),
};

const statusLabels = {
  HAS_ACCOUNTING_LINK: "Accounting linked",
  HAS_INVOICED_SO: "Invoiced SO",
  HAS_DELIVERED_SO: "Delivered SO",
  HAS_LINKED_SO: "Linked SO",
  HAS_MO_NO_SO_YET: "MO, no SO yet",
  NEW_OR_TO_SUBMIT_NO_MO: "New/no MO",
  OLD_OR_UNLINKED_NO_MO: "Review/no MO",
  CANCELLED_RECORD: "Cancelled",
};

let columnController = null;

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

function formatDateRange(from, to) {
  if (!from && !to) return "-";
  if (from && to && from !== to) return `${from} - ${to}`;
  return from || to;
}

function safeText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function cssClassForStatus(status) {
  if (status === "HAS_ACCOUNTING_LINK" || status === "HAS_INVOICED_SO") {
    return "status-complete";
  }
  if (status === "HAS_DELIVERED_SO" || status === "HAS_LINKED_SO") {
    return "status-progress";
  }
  if (status === "CANCELLED_RECORD") {
    return "status-muted";
  }
  return "status-followup";
}

function statusBadge(status) {
  const label = statusLabels[status] || safeText(status);
  return `<span class="status-badge ${cssClassForStatus(status)}">${label}</span>`;
}

function ratio(numerator, denominator) {
  const den = numberValue(denominator);
  if (!den) return null;
  return numberValue(numerator) / den;
}

function summarize(rows) {
  const active = rows.filter((row) => row.traceability_status !== "CANCELLED_RECORD");
  const soOrdered = active.reduce((sum, row) => sum + numberValue(row.total_so_ordered_qty), 0);
  const soDelivered = active.reduce((sum, row) => sum + numberValue(row.total_so_delivered_qty), 0);
  const soInvoiced = active.reduce((sum, row) => sum + numberValue(row.total_so_invoiced_qty), 0);
  const poOrdered = active.reduce((sum, row) => sum + numberValue(row.total_po_ordered_qty), 0);
  const poReceived = active.reduce((sum, row) => sum + numberValue(row.total_po_received_qty), 0);
  const poInvoiced = active.reduce((sum, row) => sum + numberValue(row.total_po_invoiced_qty), 0);

  return {
    activeInternalOrders: active.length,
    withMo: active.filter((row) => numberValue(row.linked_mo_count) > 0).length,
    withSo: active.filter((row) => numberValue(row.linked_so_count) > 0).length,
    delivered: active.filter((row) => row.has_delivered_so).length,
    invoiced: active.filter((row) => row.has_invoiced_so).length,
    deliveryProgress: ratio(soDelivered, soOrdered),
    invoiceProgress: ratio(soInvoiced, soOrdered),
    receiptProgress: ratio(poReceived, poOrdered),
    billingProgress: ratio(poInvoiced, poOrdered),
  };
}

function renderKpis(rows) {
  const summary = summarize(rows);
  els.kpiActiveIo.textContent = formatNumber(summary.activeInternalOrders);
  els.kpiWithMo.textContent = formatNumber(summary.withMo);
  els.kpiWithSo.textContent = formatNumber(summary.withSo);
  els.kpiDelivered.textContent = formatNumber(summary.delivered);
  els.kpiInvoiced.textContent = formatNumber(summary.invoiced);
  els.kpiDeliveryProgress.textContent = formatPercent(summary.deliveryProgress);
  els.kpiInvoiceProgress.textContent = formatPercent(summary.invoiceProgress);
  els.kpiPoReceipt.textContent = formatPercent(summary.receiptProgress);
  els.kpiPoBilling.textContent = formatPercent(summary.billingProgress);
  els.barDelivery.style.width = progressWidth(summary.deliveryProgress);
  els.barInvoice.style.width = progressWidth(summary.invoiceProgress);
  els.barReceipt.style.width = progressWidth(summary.receiptProgress);
  els.barBilling.style.width = progressWidth(summary.billingProgress);
}

function renderStatusStrip(rows) {
  const counts = rows.reduce((acc, row) => {
    acc[row.traceability_status] = (acc[row.traceability_status] || 0) + 1;
    return acc;
  }, {});

  const order = [
    "HAS_ACCOUNTING_LINK",
    "HAS_INVOICED_SO",
    "HAS_DELIVERED_SO",
    "HAS_LINKED_SO",
    "HAS_MO_NO_SO_YET",
    "NEW_OR_TO_SUBMIT_NO_MO",
    "OLD_OR_UNLINKED_NO_MO",
    "CANCELLED_RECORD",
  ];

  els.statusStrip.innerHTML = order
    .filter((status) => counts[status])
    .map((status) => `
      <span class="status-chip ${cssClassForStatus(status)}">
        ${statusLabels[status] || status}
        <strong>${counts[status]}</strong>
      </span>
    `)
    .join("");
}

function miniProgress(value) {
  return `
    <div class="progress-value"><span>${formatPercent(value)}</span></div>
    <div class="mini-progress"><span style="width:${progressWidth(value)}"></span></div>
  `;
}

function detailRow(row) {
  const colspan = columnController ? columnController.visibleColumnCount() : TABLE_COLUMNS.length;
  return `
    <tr class="detail-row">
      <td colspan="${Math.max(1, colspan)}">
        <div class="detail-grid">
          <div class="detail-item"><span>Requester</span><strong>${safeText(row.requester)}</strong></div>
          <div class="detail-item"><span>Need Date</span><strong>${formatDateRange(row.needed_date_from, row.needed_date_to)}</strong></div>
          <div class="detail-item"><span>Accounting Lines</span><strong>${formatNumber(row.accounting_line_count)}</strong></div>
          <div class="detail-item"><span>SO Ordered</span><strong>${formatQty(row.total_so_ordered_qty)}</strong></div>
          <div class="detail-item"><span>SO Delivered</span><strong>${formatQty(row.total_so_delivered_qty)}</strong></div>
          <div class="detail-item"><span>SO Invoiced</span><strong>${formatQty(row.total_so_invoiced_qty)}</strong></div>
          <div class="detail-item"><span>PO Ordered</span><strong>${formatQty(row.total_po_ordered_qty)}</strong></div>
          <div class="detail-item"><span>PO Received</span><strong>${formatQty(row.total_po_received_qty)}</strong></div>
          <div class="detail-item"><span>PO Invoiced</span><strong>${formatQty(row.total_po_invoiced_qty)}</strong></div>
          <div class="detail-item"><span>SO Lines</span><strong>${formatNumber(row.linked_so_line_count)}</strong></div>
          <div class="detail-item"><span>SO Amount</span><strong>${formatNumber(row.total_so_amount, 2)}</strong></div>
          <div class="detail-item"><span>Delivery Status</span><strong>${safeText(row.delivery_status_summary)}</strong></div>
          <div class="detail-item"><span>Invoice Status</span><strong>${safeText(row.invoice_status_summary)}</strong></div>
          <div class="detail-item"><span>PO Lines</span><strong>${formatNumber(row.linked_po_line_count)}</strong></div>
          <div class="detail-item"><span>Purchase Status</span><strong>${safeText(row.purchase_status_summary)}</strong></div>
          <div class="detail-item"><span>IO Lines</span><strong>${formatNumber(row.line_count)}</strong></div>
          <div class="detail-item"><span>Manufacturing Moves</span><strong>${formatNumber(row.manufacturing_movement_count)}</strong></div>
          <div class="detail-item"><span>Finished Goods Moves</span><strong>${formatNumber(row.finished_goods_store_count)}</strong></div>
          <div class="detail-item"><span>Delivery Moves</span><strong>${formatNumber(row.delivery_movement_count)}</strong></div>
        </div>
      </td>
    </tr>
  `;
}

function tableRow(row) {
  const expanded = state.expanded.has(row.internal_order_number);
  return `
    <tr>
      <td data-column-key="expand"><button class="row-action" type="button" data-io="${row.internal_order_number}" title="Toggle diagnostics" aria-label="Toggle diagnostics">${expanded ? "-" : "+"}</button></td>
      <td class="io-number" data-column-key="io_number">${safeText(row.internal_order_number)}</td>
      <td data-column-key="status">${statusBadge(row.status_summary)}</td>
      <td class="num" data-column-key="products">${formatNumber(row.product_count)}</td>
      <td class="num" data-column-key="mo">${formatNumber(row.linked_mo_count)}</td>
      <td class="num" data-column-key="so">${formatNumber(row.linked_so_count)}</td>
      <td class="progress-cell" data-column-key="delivery_percent">${miniProgress(row.so_delivery_progress_ratio)}</td>
      <td class="progress-cell" data-column-key="invoice_percent">${miniProgress(row.so_invoice_progress_ratio)}</td>
      <td class="progress-cell" data-column-key="receipt_percent">${miniProgress(row.po_receipt_progress_ratio)}</td>
      <td class="progress-cell" data-column-key="billing_percent">${miniProgress(row.po_invoice_progress_ratio)}</td>
      <td data-column-key="traceability">${statusBadge(row.traceability_status)}</td>
    </tr>
    ${expanded ? detailRow(row) : ""}
  `;
}

function visibleColumnCount() {
  return columnController ? columnController.visibleColumnCount() : TABLE_COLUMNS.length;
}

function ensurePaginationControls(prefix) {
  if (els.paginationStatus) return;

  const host = document.querySelector(".table-toolbar-actions") || document.querySelector(".table-toolbar");
  if (!host) return;

  host.insertAdjacentHTML("beforeend", `
    <div class="pagination-controls" id="${prefix}PaginationControls">
      <button class="secondary-button" id="${prefix}PrevPageButton" type="button">Prev</button>
      <span class="pagination-status" id="${prefix}PaginationStatus">Page 1 of 1</span>
      <button class="secondary-button" id="${prefix}NextPageButton" type="button">Next</button>
      <select id="${prefix}PageSizeSelect" aria-label="Rows per page">
        <option value="50">50 rows</option>
        <option value="100" selected>100 rows</option>
        <option value="250">250 rows</option>
        <option value="500">500 rows</option>
      </select>
    </div>
  `);

  els.paginationStatus = document.getElementById(`${prefix}PaginationStatus`);
  els.prevPageButton = document.getElementById(`${prefix}PrevPageButton`);
  els.nextPageButton = document.getElementById(`${prefix}NextPageButton`);
  els.pageSizeSelect = document.getElementById(`${prefix}PageSizeSelect`);

  els.pageSizeSelect.value = String(state.pagination.pageSize);

  els.prevPageButton.addEventListener("click", () => {
    state.pagination.page = Math.max(1, state.pagination.page - 1);
    renderTable(state.filteredRows);
  });

  els.nextPageButton.addEventListener("click", () => {
    state.pagination.page += 1;
    renderTable(state.filteredRows);
  });

  els.pageSizeSelect.addEventListener("change", () => {
    state.pagination.pageSize = Number(els.pageSizeSelect.value) || 100;
    state.pagination.page = 1;
    renderTable(state.filteredRows);
  });
}

function getPaginatedRows(rows) {
  const pageSize = state.pagination.pageSize;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));

  state.pagination.page = Math.min(Math.max(1, state.pagination.page), totalPages);

  const start = (state.pagination.page - 1) * pageSize;
  const end = Math.min(start + pageSize, rows.length);

  return {
    rows: rows.slice(start, end),
    start,
    end,
    totalPages,
  };
}

function updatePaginationControls(totalRows, start, end, totalPages) {
  if (!els.paginationStatus) return;

  if (!totalRows) {
    els.paginationStatus.textContent = "No rows";
  } else {
    els.paginationStatus.textContent =
      `Showing ${formatNumber(start + 1)}-${formatNumber(end)} of ${formatNumber(totalRows)} | Page ${formatNumber(state.pagination.page)} of ${formatNumber(totalPages)}`;
  }

  els.prevPageButton.disabled = state.pagination.page <= 1;
  els.nextPageButton.disabled = state.pagination.page >= totalPages;
}

function renderTable(rows) {
  ensurePaginationControls("internalOrders");

  els.rowCount.textContent = `${formatNumber(rows.length)} rows`;

  if (!rows.length) {
    els.dashboardRows.innerHTML = `<tr><td colspan="${Math.max(1, visibleColumnCount())}" class="empty-cell">No Internal Orders match the current filters.</td></tr>`;
    updatePaginationControls(0, 0, 0, 1);
    return;
  }

  const page = getPaginatedRows(rows);
  els.dashboardRows.innerHTML = page.rows.map(tableRow).join("");
  updatePaginationControls(rows.length, page.start, page.end, page.totalPages);
  columnController?.apply();
}

function populateSelect(select, values) {
  const first = select.querySelector("option")?.outerHTML || '<option value="">All</option>';
  select.innerHTML = first + values.map((value) => `<option value="${value}">${value}</option>`).join("");
}

function populateFilters(filters) {
  populateSelect(els.requesterFilter, filters.requesters || []);
  populateSelect(els.statusFilter, filters.statuses || []);
  populateSelect(els.traceabilityFilter, filters.traceability_statuses || []);
}

function dateOverlaps(row, fromFilter, toFilter) {
  if (!fromFilter && !toFilter) return true;
  const rowFrom = row.needed_date_from || row.needed_date_to;
  const rowTo = row.needed_date_to || row.needed_date_from;
  if (!rowFrom && !rowTo) return false;
  if (fromFilter && rowTo < fromFilter) return false;
  if (toFilter && rowFrom > toFilter) return false;
  return true;
}

function activeFilterSummary() {
  const entries = [];
  if (els.ioFilter.value.trim()) entries.push(`IO: ${els.ioFilter.value.trim()}`);
  if (els.requesterFilter.value) entries.push(`Requester: ${els.requesterFilter.value}`);
  if (els.statusFilter.value) entries.push(`Status: ${els.statusFilter.value}`);
  if (els.traceabilityFilter.value) entries.push(`Traceability: ${els.traceabilityFilter.value}`);
  if (els.dateFromFilter.value || els.dateToFilter.value) {
    entries.push(`Need Date: ${els.dateFromFilter.value || "..."} to ${els.dateToFilter.value || "..."}`);
  }
  return entries.length ? `Filters: ${entries.join(", ")}` : "Filters: All Internal Orders";
}

function applyFilters() {
  const ioTerm = els.ioFilter.value.trim().toLowerCase();
  const requester = els.requesterFilter.value;
  const status = els.statusFilter.value;
  const traceability = els.traceabilityFilter.value;
  const dateFrom = els.dateFromFilter.value;
  const dateTo = els.dateToFilter.value;

  state.filteredRows = state.rows.filter((row) => {
    const matchesIo = !ioTerm || safeText(row.internal_order_number).toLowerCase().includes(ioTerm);
    const matchesRequester = !requester || row.requester === requester;
    const matchesStatus = !status || row.status_summary === status;
    const matchesTraceability = !traceability || row.traceability_status === traceability;
    return matchesIo && matchesRequester && matchesStatus && matchesTraceability && dateOverlaps(row, dateFrom, dateTo);
  });

  els.activeFilterSummary.textContent = activeFilterSummary();
  renderKpis(state.filteredRows);
  renderStatusStrip(state.filteredRows);
  state.pagination.page = 1;
  renderTable(state.filteredRows);
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
    fileName: `internal_orders_${DashboardExport.timestampSuffix()}.xlsx`,
    sheetName: "Internal Orders",
    columns: sheet.columns,
    rows: sheet.rows,
  });
}

async function loadDashboard() {
  els.lastLoaded.textContent = "Loading...";
  try {
    const response = await fetch("/api/dashboard/internal-orders", { headers: { Accept: "application/json" } });
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
    els.dashboardRows.innerHTML = `<tr><td colspan="${Math.max(1, visibleColumnCount())}" class="empty-cell">${error.message}</td></tr>`;
  }
}

function clearFilters() {
  els.dateFromFilter.value = "";
  els.dateToFilter.value = "";
  els.ioFilter.value = "";
  els.requesterFilter.value = "";
  els.statusFilter.value = "";
  els.traceabilityFilter.value = "";
  applyFilters();
}

[
  els.dateFromFilter,
  els.dateToFilter,
  els.ioFilter,
  els.requesterFilter,
  els.statusFilter,
  els.traceabilityFilter,
].forEach((el) => el.addEventListener("input", applyFilters));

els.refreshButton.addEventListener("click", loadDashboard);
els.clearFiltersButton.addEventListener("click", clearFilters);
els.clearToolbarFiltersButton.addEventListener("click", clearFilters);
els.exportExcelButton.addEventListener("click", exportCurrentView);
els.dashboardRows.addEventListener("click", (event) => {
  const button = event.target.closest("[data-io]");
  if (!button) return;
  const ioNumber = button.dataset.io;
  if (state.expanded.has(ioNumber)) {
    state.expanded.delete(ioNumber);
  } else {
    state.expanded.add(ioNumber);
  }
  renderTable(state.filteredRows);
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
  root: els.internalOrdersTable,
});

loadDashboard();

