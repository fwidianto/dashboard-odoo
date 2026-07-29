const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const controlTower = fs.readFileSync(path.join(root, 'src/static/dashboard/control-tower.html'), 'utf8');
const salesOrders = fs.readFileSync(path.join(root, 'src/static/dashboard/sales-orders.js'), 'utf8');

test('Temuan view has loading, empty, error, and finding contracts', () => {
  assert.match(controlTower, /id="temuanView"[^>]*hidden/);
  assert.match(controlTower, /<h1[^>]*>Temuan<\/h1>/);
  assert.match(controlTower, /Data Belum Lengkap/);
  assert.match(controlTower, /Memuat Temuan/);
  assert.match(controlTower, /Tidak ada Temuan Data Belum Lengkap/);
  assert.match(controlTower, /Temuan tidak dapat dimuat/);
  assert.match(controlTower, /\/api\/control-tower\/findings/);
  assert.match(controlTower, /affected_model/);
  assert.match(controlTower, /category/);
  assert.match(controlTower, /rule_code/);
  assert.match(controlTower, /payload.total/);
});

test('Temuan uses the exact native Sales Order destination and view switch', () => {
  assert.match(controlTower, /view=temuan/);
  assert.match(controlTower, /finding\.destination_url/);
  assert.match(controlTower, /overviewView\.hidden = isTemuan/);
  assert.match(controlTower, /temuanView\.hidden = !isTemuan/);
});

test('Sales Order deep link requires an exact native id and focuses the expanded row', () => {
  assert.match(salesOrders, /URLSearchParams\(window\.location\.search\)\.get\('sales_order_id'\)/);
  assert.match(salesOrders, /sales_order_id/);
  assert.match(salesOrders, /String\(item\.sales_order_id\) === requestedId/);
  assert.match(salesOrders, /scrollIntoView/);
  assert.match(salesOrders, /button\.focus/);
  assert.match(salesOrders, /Sales Order dengan ID .* tidak ditemukan/);
});
