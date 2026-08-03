const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = path.join(__dirname, '..', 'src', 'static', 'dashboard', 'sales-orders.js');
const source = fs.readFileSync(sourcePath, 'utf8').replace(/^\uFEFF/, '') + `
globalThis.__salesOrdersTest = { state, els, loadDashboard };
`;

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(...names) {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }

  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : force;
    if (enabled) this.values.add(name);
    else this.values.delete(name);
    return enabled;
  }

  contains(name) {
    return this.values.has(name);
  }
}

class FakeElement {
  constructor(id, tagName = 'div') {
    this.id = id;
    this.tagName = tagName.toUpperCase();
    this.dataset = {};
    this.value = '';
    this.hidden = false;
    this.disabled = false;
    this.href = '';
    this.textContent = '';
    this.innerHTML = '';
    this.style = {};
    this.classList = new FakeClassList();
    this.listeners = {};
    this.children = [];
    this.focused = false;
  }

  addEventListener(type, callback) {
    this.listeners[type] = callback;
  }

  setAttribute(name, value) {
    this[name] = String(value);
  }

  removeAttribute(name) {
    delete this[name];
  }

  querySelector() {
    return null;
  }

  querySelectorAll() {
    return [];
  }

  closest() {
    return null;
  }

  insertAdjacentHTML() {}

  appendChild(child) {
    this.children.push(child);
    this.textContent += child.textContent || '';
    return child;
  }

  replaceChildren(...children) {
    this.children = children;
    this.innerHTML = '';
    this.textContent = children.map((child) => child.textContent || '').join('');
  }

  remove() {}

  focus() {
    this.focused = true;
  }

  scrollIntoView() {
    this.scrolled = true;
  }
}

class FakeDetailRow extends FakeElement {
  constructor(rows, id) {
    super('', 'tr');
    this.rows = rows;
    this.id = id;
    this.cell = new FakeElement('', 'td');
  }

  querySelector(selector) {
    return selector === 'td' ? this.cell : null;
  }

  remove() {
    this.rows.details.delete(this.id);
  }
}

class FakeMainRow extends FakeElement {
  constructor(rows, id) {
    super('', 'tr');
    this.rows = rows;
    this.id = id;
    this.dataset.rowSoId = id;
  }

  insertAdjacentHTML(position) {
    if (position === 'afterend') {
      this.rows.details.set(this.id, new FakeDetailRow(this.rows, this.id));
    }
  }
}

class FakeButton extends FakeElement {
  constructor(rows, id) {
    super('', 'button');
    this.rows = rows;
    this.dataset.so = id;
    this.row = new FakeMainRow(rows, id);
  }

  closest(selector) {
    return selector === 'tr[data-row-so-id]' ? this.row : null;
  }
}

class FakeRowsElement extends FakeElement {
  constructor() {
    super('dashboardRows', 'tbody');
    this.details = new Map();
  }

  set innerHTML(value) {
    this._innerHTML = String(value);
    this.details?.clear();
  }

  get innerHTML() {
    return this._innerHTML || '';
  }

  querySelector(selector) {
    const detailMatch = selector.match(/^tr\[data-detail-so-id="([^"]+)"\]$/);
    if (detailMatch) return this.details.get(detailMatch[1]) || null;

    const buttonMatch = selector.match(/^\[data-so="([^"]+)"\]$/);
    if (buttonMatch && this.innerHTML.includes(`data-so="${buttonMatch[1]}"`)) {
      return new FakeButton(this, buttonMatch[1]);
    }
    return null;
  }

  replaceChildren(...children) {
    this.details.clear();
    this.children = children;
    this._innerHTML = '';
    this.textContent = children.map((child) => child.textContent || '').join('');
  }
}

function makeRow(id, status) {
  const cancelled = status === 'cancel';
  return {
    sales_order_id: id,
    sales_order_number: `SO${id}`,
    order_year: '2026',
    customer_name: 'Acme',
    product_type_label: 'Finished',
    source_type: cancelled ? 'CANCELLED_RECORD' : 'FROM_STOCK',
    sales_order_state: status,
    follow_up_status: cancelled ? 'CANCELLED_RECORD' : 'COMPLETED',
    is_cancelled: cancelled,
    commitment_date: '2026-01-01',
    ordered_qty: 1,
    delivered_qty: 1,
    invoiced_qty: 1,
    ordered_amount: 100,
    delivered_amount: 100,
    invoiced_amount: 100,
    ordered_amount_idr: 100,
    delivered_amount_idr: 100,
    invoiced_amount_idr: 100,
    qty_delivery_progress_ratio: 1,
    qty_invoice_progress_ratio: 1,
    amount_delivery_progress_ratio: 1,
    amount_invoice_progress_ratio: 1,
  };
}

function makePayload() {
  return {
    rows: [makeRow(101, 'sale'), makeRow(202, 'cancel')],
    filters: {
      years: ['2026'],
      customers: ['Acme'],
      product_types: ['Finished'],
      source_types: ['CANCELLED_RECORD', 'FROM_STOCK'],
      sales_order_statuses: ['sale', 'cancel'],
      follow_up_statuses: ['COMPLETED', 'CANCELLED_RECORD'],
    },
  };
}

function makeDocument() {
  const elements = new Map();
  const rows = new FakeRowsElement();
  elements.set('dashboardRows', rows);
  const kpiGrid = new FakeElement('kpiGrid');
  const toolbarActions = new FakeElement('toolbarActions');

  return {
    rows,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new FakeElement(id));
      return elements.get(id);
    },
    querySelector(selector) {
      if (selector === '.kpi-grid') return kpiGrid;
      if (selector === '.table-toolbar-actions') return toolbarActions;
      if (selector === '.table-toolbar') return null;
      if (selector.startsWith('[data-so=') || selector.startsWith('tr[data-detail-so-id=')) return rows.querySelector(selector);
      return null;
    },
    querySelectorAll() {
      return [];
    },
    createElement(tagName) {
      return new FakeElement('', tagName);
    },
    addEventListener() {},
  };
}

async function loadScenario(search = '') {
  const document = makeDocument();
  const payload = makePayload();
  const window = {
    location: {
      origin: 'http://test.local',
      href: `http://test.local/dashboard/sales-orders${search}`,
      search,
    },
    addEventListener() {},
  };
  const context = {
    console,
    document,
    window,
    URL,
    URLSearchParams,
    CSS: { escape: (value) => String(value) },
    requestAnimationFrame: (callback) => callback(),
    fetch: async (url) => {
      if (String(url).includes('/details')) {
        return {
          ok: true,
          json: async () => ({
            sales_order_lines: [{ product_name: 'Widget' }],
            manufacturing_orders: [],
            io_manufacturing_correlations: [],
          }),
        };
      }
      return { ok: true, json: async () => payload };
    },
    localStorage: {
      getItem: () => null,
      setItem: () => {},
    },
    DashboardTableTools: {
      createColumnController: () => ({
        visibleColumnKeys: () => [],
        visibleColumnCount: () => 28,
        apply: () => {},
      }),
    },
    DashboardExport: {
      buildSheetData: () => ({ columns: [], rows: [] }),
      exportXlsx: async () => {},
      timestampSuffix: () => 'test',
    },
  };

  vm.runInNewContext(source, context, { filename: sourcePath });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  return { ...context.__salesOrdersTest, document };
}

test('default Sales Order browsing remains active-only', async () => {
  const { state } = await loadScenario();

  assert.deepEqual([...state.filters.status], ['sale']);
  assert.deepEqual([...state.filteredRows].map((row) => Number(row.sales_order_id)), [101]);
});

test('direct linked active Sales Order remains visible and expands', async () => {
  const { state, document } = await loadScenario('?sales_order_id=101');

  assert.deepEqual([...state.filters.status], ['sale']);
  assert.equal(state.filtersInitialized, true);
  assert.deepEqual([...state.filteredRows].map((row) => Number(row.sales_order_id)), [101]);
  assert.equal(state.expanded.has('101'), true);
  assert.equal(state.rows.find((row) => row.sales_order_id === 101).detail_loaded, true);
  assert.match(document.rows.innerHTML, /data-row-so-id="101"/);
});

test('direct linked cancelled Sales Order selects its status and expands without broadening browsing', async () => {
  const { state, document } = await loadScenario('?sales_order_id=202');

  assert.deepEqual([...state.filters.status], ['cancel']);
  assert.deepEqual([...state.filteredRows].map((row) => Number(row.sales_order_id)), [202]);
  assert.equal(state.expanded.has('202'), true);
  assert.equal(state.rows.find((row) => row.sales_order_id === 202).detail_loaded, true);
  assert.match(document.rows.innerHTML, /data-row-so-id="202"/);
});

test('unknown requested Sales Order ID shows the truthful not-found state', async () => {
  const { state, document } = await loadScenario('?sales_order_id=999');

  assert.equal(document.getElementById('lastLoaded').textContent, 'Sales Order not found');
  assert.match(document.rows.textContent, /Sales Order dengan ID 999 tidak ditemukan pada snapshot ini/);
  assert.deepEqual([...state.filters.status], ['sale']);
});
