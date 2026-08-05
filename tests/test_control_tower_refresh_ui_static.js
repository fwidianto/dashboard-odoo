const assert = require('node:assert/strict');
const fs = require('node:fs');

const page = fs.readFileSync('src/static/dashboard/control-tower.html', 'utf8');
const shell = fs.readFileSync('src/static/dashboard/control-tower-shell.js', 'utf8');

// Refresh panel markup contract.
assert.match(page, /data-ct-refresh-panel/);
assert.match(page, /data-ct-refresh-stage/);
assert.match(page, /data-ct-refresh-message/);
assert.match(page, /data-ct-refresh-diagnostic/);
assert.match(page, /data-ct-refresh-trusted/);
assert.match(page, /data-ct-refresh-elapsed/);
assert.match(page, /data-ct-refresh-counts/);
assert.match(page, /data-ct-refresh-minimize/);
assert.match(page, /Data terakhir diperbarui/);
assert.match(page, /<button class="ct-refresh-compact" data-ct-refresh="" type="button" hidden>Refresh Data<\/button>/);

// Refresh logic contracts.
assert.match(shell, /function refreshPanelState/);
assert.match(shell, /function startRefreshPolling/);
assert.match(shell, /async function requestRefresh/);
assert.match(shell, /refreshReloadEvidence/);
assert.match(shell, /refreshButton\.hidden = !state\.canRefresh \|\| state\.active/);
assert.match(shell, /Pembaruan Odoo gagal\. Control Tower tetap menampilkan snapshot terakhir yang berhasil\./);

// Extract the pure state mapper (with its formatting helpers) and test every
// supported refresh state without a DOM.
const start = shell.indexOf('function formatFreshnessTime(value) {');
const end = shell.indexOf('function renderRefreshPanel(payload) {');
assert.ok(start >= 0 && end > start, 'refresh state helper block not found');
const source = shell.slice(start, end);
const refreshPanelState = new Function(`${source}; return refreshPanelState;`)();

assert.equal(
  refreshPanelState({
    refresh_ui: {
      status: 'READING',
      stage_label: 'Membaca perubahan dari Odoo',
      active: true,
      elapsed_seconds: 12,
      trusted: { timestamp: '2026-08-05T01:00:00Z', run_id: 'run-1' }
    }
  }).panelState,
  'ACTIVE'
);

const checking = refreshPanelState({
  refresh_ui: {
    status: 'CHECKING',
    stage_label: 'Memeriksa hasil',
    active: true,
    counts: { models_completed: 7, records: 142 }
  }
});
assert.equal(checking.panelState, 'ACTIVE');
assert.equal(checking.countsText, '7 model selesai · 142 record');

const success = refreshPanelState({
  refresh_ui: {
    status: 'DONE',
    stage_label: 'Selesai',
    outcome: 'SUCCESS',
    trusted: { timestamp: '2026-08-05T01:00:00Z' }
  }
});
assert.equal(success.panelState, 'SUCCESS');
assert.notEqual(success.trustedText, 'Belum ada snapshot terpercaya');

const failed = refreshPanelState({
  refresh_ui: {
    status: 'FAILED',
    stage_label: 'Gagal',
    outcome: 'FAILED',
    latest_attempt: { error_message: 'Odoo unreachable' },
    trusted: { timestamp: '2026-08-05T01:00:00Z' }
  }
});
assert.equal(failed.panelState, 'FAILED');
assert.equal(
  failed.message,
  'Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil.'
);
assert.equal(failed.diagnostic, 'Odoo unreachable');

const stale = refreshPanelState({
  refresh_ui: { status: 'STALE', outcome: 'INTERRUPTED', stage_label: 'Pembaruan terhenti' }
});
assert.equal(stale.panelState, 'STALE');
assert.equal(stale.active, false);

const idle = refreshPanelState({
  refresh_ui: { status: 'IDLE', stage_label: 'Menunggu pembaruan', can_refresh: true, trusted: { timestamp: '2026-08-05T01:00:00Z' } }
});
assert.equal(idle.panelState, 'IDLE');
assert.equal(idle.canRefresh, true);

const noTrust = refreshPanelState({
  refresh_ui: { status: 'NO_COMPLETED_EXTRACTION', stage_label: 'Belum ada snapshot' }
});
assert.equal(noTrust.panelState, 'NO_COMPLETED_EXTRACTION');
assert.equal(noTrust.trustedText, 'Belum ada snapshot terpercaya');

const unavailable = refreshPanelState(null);
assert.equal(unavailable.panelState, 'UNAVAILABLE');
assert.equal(unavailable.canRefresh, false);

console.log('Control Tower refresh UI static contracts passed');
