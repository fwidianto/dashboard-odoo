const assert = require('node:assert/strict');
const fs = require('node:fs');

const page = fs.readFileSync('src/static/dashboard/control-tower.html', 'utf8');
assert.match(page, /class="temuan-panel"/);
assert.match(page, /id="integratedFindingList"/);
assert.match(page, /id="salesOrderFindingBadge"/);
assert.match(page, /class="inspector-panel"/);
assert.match(page, /affected_model: 'sale\.order'/);
assert.match(page, /category: 'DATA_BELUM_LENGKAP'/);
assert.match(page, /rule_code: 'DH2-SALES-001'/);
assert.match(page, /current_status/);
assert.match(page, /actualEvidence/);
assert.match(page, /selected_finding/);
assert.match(page, /return_to/);
assert.match(page, /integratedFindingRetry/);
assert.match(page, /Temuan yang dipilih tidak ditemukan/);
assert.match(page, /stockChoice\.cx.*elbowY.*internalOrder\.cx.*internalOrder\.top/s);
console.log('Integrated three-panel static contracts passed');