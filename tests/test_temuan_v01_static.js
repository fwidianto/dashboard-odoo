const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const controlTower = fs.readFileSync(path.join(root, 'src/static/dashboard/control-tower.html'), 'utf8');
const controlTowerShell = fs.readFileSync(path.join(root, 'src/static/dashboard/control-tower-shell.js'), 'utf8');
const salesOrders = fs.readFileSync(path.join(root, 'src/static/dashboard/sales-orders.js'), 'utf8');
const dedicatedTemuan = fs.readFileSync(path.join(root, 'src/static/dashboard/temuan.html'), 'utf8');
const dedicatedTemuanJs = fs.readFileSync(path.join(root, 'src/static/dashboard/temuan.js'), 'utf8');

test('Immersive Control Tower exposes trusted Temuan summary and inspector states', () => {
  assert.match(controlTower, /class="ct-immersive-page"/);
  assert.match(controlTower, /data-ct-temuan/);
  assert.match(controlTower, /data-ct-inspector/);
  assert.match(controlTower, /data-ct-open-documents/);
  for (const category of ['MASALAH_AKTIF', 'PERLU_DITINJAU', 'DATA_BELUM_LENGKAP']) {
    assert.match(controlTower, new RegExp('data-ct-category-count="' + category + '"'));
    assert.match(controlTower, new RegExp('data-ct-inspector-count="' + category + '"'));
  }
  assert.match(controlTowerShell, /function evidenceStateForNode/);
  assert.match(controlTowerShell, /function coverageMessageForNode/);
  assert.match(controlTowerShell, /function formatCount/);
  assert.match(controlTowerShell, /coverage\.state !== "MAPPED"/);
});

test('Control Tower routes findings through the dedicated Temuan destination', () => {
  assert.match(controlTowerShell, /function categoryDestination/);
  assert.match(controlTowerShell, /\/dashboard\/control-tower\/temuan/);
  assert.match(controlTowerShell, /presentation_category/);
  assert.match(controlTowerShell, /return_to/);
  assert.match(dedicatedTemuanJs, /destinationFor/);
  assert.match(dedicatedTemuanJs, /unsupported_destination_reason/);
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
  assert.match(controlTower, /data-ct-freshness/);
  assert.match(controlTower, /data-ct-refresh/);
  assert.match(controlTower, /data-ct-mode-toggle/);
  assert.match(controlTower, /data-ct-map-scroll/);
  assert.match(controlTowerShell, /fetch\("\/api\/control-tower\/health"/);
  assert.match(controlTowerShell, /fetch\("\/api\/control-tower\/refresh"/);
  assert.match(controlTowerShell, /Promise\.allSettled/);
  assert.match(controlTowerShell, /categoryDestination/);
  assert.match(controlTowerShell, /UNAVAILABLE/);
});
