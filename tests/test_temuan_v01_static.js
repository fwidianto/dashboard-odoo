const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const controlTower = fs.readFileSync(path.join(root, 'src/static/dashboard/control-tower.html'), 'utf8');
const salesOrders = fs.readFileSync(path.join(root, 'src/static/dashboard/sales-orders.js'), 'utf8');
const dedicatedTemuan = fs.readFileSync(path.join(root, 'src/static/dashboard/temuan.html'), 'utf8');
const dedicatedTemuanJs = fs.readFileSync(path.join(root, 'src/static/dashboard/temuan.js'), 'utf8');

test('Temuan view has loading, empty, error, and finding contracts', () => {
  assert.match(controlTower, /id="temuanView"[^>]*hidden/);
  assert.match(controlTower, /<h1[^>]*>Temuan<\/h1>/);
  assert.match(controlTower, /Data Belum Lengkap/);
  assert.match(controlTower, /Memuat Temuan/);
  assert.match(controlTower, /Tidak ada Temuan Data Belum Lengkap/);
  assert.match(controlTower, /Temuan tidak dapat dimuat/);
  assert.match(controlTower, /\/api\/control-tower\/findings/);
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

test('Office Pilot Temuan worklist preserves trusted freshness and evidence states', () => {
  assert.match(dedicatedTemuan, /id="freshnessBanner"/);
  assert.match(dedicatedTemuan, /id="refreshButton"/);
  assert.match(dedicatedTemuan, /id="inspectorBody"/);
  assert.match(dedicatedTemuan, /temuan\.js/);
  assert.match(dedicatedTemuanJs, /\/api\/control-tower\/health/);
  assert.match(dedicatedTemuanJs, /\/api\/control-tower\/refresh/);
  assert.match(dedicatedTemuanJs, /\/api\/control-tower\/temuan/);
  assert.match(dedicatedTemuanJs, /Promise\.allSettled/);
  assert.match(dedicatedTemuanJs, /Tidak ada Temuan/);
  assert.match(dedicatedTemuanJs, /Temuan tidak dapat dimuat/);
  assert.match(dedicatedTemuanJs, /safeDestination/);
  assert.match(dedicatedTemuanJs, /Review signal bukan bukti otomatis/);
  assert.match(dedicatedTemuan, /id="backLink"/);
  assert.match(dedicatedTemuanJs, /return_to/);
  assert.match(dedicatedTemuanJs, /destinationFor/);
  assert.match(dedicatedTemuanJs, /latest_refresh_attempt_status/);
  assert.match(dedicatedTemuanJs, /stale_attempt/);
  assert.match(dedicatedTemuanJs, /120000/);
});

test('Canonical Control Tower exposes office freshness and navigation contracts', () => {
  assert.match(controlTower, /id="controlTowerFreshness"/);
  assert.match(controlTower, /id="controlTowerRefreshButton"/);
  assert.match(controlTower, /fetchControlTowerJson\('\/api\/control-tower\/health'\)/);
  assert.match(controlTower, /fetchControlTowerJson\('\/api\/control-tower\/refresh'/);
  assert.match(controlTower, /Promise\.allSettled/);
  assert.match(controlTower, /window\.location\.assign\(`\$\{destination\.pathname\}/);
  assert.match(controlTower, /map-focus-control/);
  assert.match(controlTower, /120000/);
  assert.match(controlTower, /Control Tower data service unavailable/);
});
