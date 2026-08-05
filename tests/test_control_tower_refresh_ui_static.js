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
assert.match(page, /data-ct-refresh-recover/);
assert.match(page, /data-ct-refresh-recover-action/);
assert.match(page, /data-ct-refresh-retry/);
assert.match(page, /data-ct-refresh-retry-action/);
assert.match(page, /Tutup percobaan lama/);
assert.match(page, /Percobaan pembaruan yang terhenti akan ditutup\./);
assert.match(page, /Coba Lagi/);
assert.match(page, /Data terakhir diperbarui/);
assert.match(page, /<button class="ct-refresh-compact" data-ct-refresh="" type="button" hidden>Refresh Data<\/button>/);

// Refresh logic contracts.
assert.match(shell, /function refreshPanelState/);
assert.match(shell, /function startRefreshPolling/);
assert.match(shell, /async function requestRefresh/);
assert.match(shell, /async function requestRecoverStale/);
assert.match(shell, /async function requestRetry/);
assert.match(shell, /\/api\/control-tower\/refresh\/recover/);
assert.match(shell, /\/api\/control-tower\/refresh\/retry/);
assert.match(shell, /refreshRecoverAction\.disabled = true/);
assert.match(shell, /refreshRecover\.hidden = !\(state\.canRecoverStale && state\.panelState === "STALE"\)/);
assert.match(shell, /refreshRetry\.hidden = !\(state\.canRetry && \(state\.panelState === "FAILED" \|\| state\.panelState === "STALE"\)\)/);
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

const noChanges = refreshPanelState({
  refresh_ui: {
    status: 'DONE',
    stage_label: 'Tidak ada perubahan',
    outcome: 'NO_CHANGES',
    trusted: { timestamp: '2026-08-05T01:00:00Z' }
  }
});
assert.equal(noChanges.panelState, 'NO_CHANGES');
assert.equal(noChanges.stageLabel, 'Tidak ada perubahan');

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

const retryable = refreshPanelState({
  refresh_ui: {
    status: 'FAILED',
    stage_label: 'Gagal',
    outcome: 'FAILED',
    can_retry: true,
    can_refresh: false,
    trusted: { timestamp: '2026-08-05T01:00:00Z' }
  }
});
assert.equal(retryable.canRetry, true);
assert.equal(retryable.canRefresh, false);

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

// Stale administrator sees the recovery action and no Refresh Data.
const staleAdmin = refreshPanelState({
  refresh_ui: {
    status: 'STALE',
    stage_label: 'Pembaruan terhenti',
    outcome: 'INTERRUPTED',
    can_recover_stale: true,
    can_refresh: false,
    latest_attempt: { error_message: 'Refresh attempt exceeded the stale threshold' }
  }
});
assert.equal(staleAdmin.panelState, 'STALE');
assert.equal(staleAdmin.canRecoverStale, true);
assert.equal(staleAdmin.canRefresh, false);

// Stale normal user receives no enabled recovery action.
const staleUser = refreshPanelState({
  refresh_ui: { status: 'STALE', stage_label: 'Pembaruan terhenti', can_recover_stale: false, can_refresh: false }
});
assert.equal(staleUser.canRecoverStale, false);
assert.equal(staleUser.canRefresh, false);

// Recovered state is truthful and reveals Refresh Data.
const recovered = refreshPanelState({
  refresh_ui: {
    status: 'RECOVERED',
    stage_label: 'Pembaruan lama ditutup',
    outcome: 'RECOVERED',
    can_recover_stale: false,
    can_refresh: true,
    trusted: { timestamp: '2026-08-05T01:00:00Z' }
  }
});
assert.equal(recovered.panelState, 'RECOVERED');
assert.equal(recovered.stageLabel, 'Pembaruan lama ditutup');
assert.equal(recovered.canRecoverStale, false);
assert.equal(recovered.canRefresh, true);

console.log('Control Tower refresh UI static contracts passed');
