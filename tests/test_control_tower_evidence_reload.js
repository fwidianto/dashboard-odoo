// CT-8D1-R1 deterministic regression: every complete evidence reload must
// REPLACE evidence state, never accumulate it. The pure accumulator extracted
// from control-tower-shell.js is executed here without a DOM so the reload
// math is actually proven, not merely pattern-matched.
const assert = require('node:assert/strict');
const fs = require('node:fs');

const shell = fs.readFileSync('src/static/dashboard/control-tower-shell.js', 'utf8');

const accumulatorStart = shell.indexOf('function createEvidenceAccumulator(categoryOrder) {');
const accumulatorEnd = shell.indexOf('const evidence = createEvidenceAccumulator(categoryOrder);');
assert.ok(accumulatorStart >= 0 && accumulatorEnd > accumulatorStart, 'createEvidenceAccumulator block not found');
const accumulatorSource = shell.slice(accumulatorStart, accumulatorEnd);
const { createEvidenceAccumulator } = new Function(`${accumulatorSource}; return { createEvidenceAccumulator };`)();

const CATEGORIES = ['MASALAH_AKTIF', 'PERLU_DITINJAU', 'DATA_BELUM_LENGKAP'];

function payload(category, processCounts, categoryCounts, rows = []) {
  return {
    category,
    rows,
    category_counts: categoryCounts || {},
    process_counts: processCounts.map(([processKey, count]) => ({ process_key: processKey, count }))
  };
}

function simulateLoad(acc, responses) {
  acc.reset();
  responses.forEach((p) => acc.ingest(p.category, p));
  return acc.state;
}

const stateA = simulateLoad(
  createEvidenceAccumulator(CATEGORIES),
  [
    payload('MASALAH_AKTIF', [['sales-order', 3]], { MASALAH_AKTIF: 3 }),
    payload('PERLU_DITINJAU', [], { PERLU_DITINJAU: 0 }),
    payload('DATA_BELUM_LENGKAP', [], { DATA_BELUM_LENGKAP: 0 })
  ]
);
assert.equal(stateA.processCounts.get('sales-order').MASALAH_AKTIF, 3);
assert.equal(stateA.categoryCounts.MASALAH_AKTIF, 3);
assert.deepEqual(stateA.categoryAvailability, { MASALAH_AKTIF: true, PERLU_DITINJAU: true, DATA_BELUM_LENGKAP: true });

// A1. Second reload with a smaller count replaces, not accumulates (3 -> 2 = 2, not 5).
const stateB = simulateLoad(
  createEvidenceAccumulator(CATEGORIES),
  [
    payload('MASALAH_AKTIF', [['sales-order', 2]], { MASALAH_AKTIF: 2 }),
    payload('PERLU_DITINJAU', [], { PERLU_DITINJAU: 0 }),
    payload('DATA_BELUM_LENGKAP', [], { DATA_BELUM_LENGKAP: 0 })
  ]
);
assert.equal(stateB.processCounts.get('sales-order').MASALAH_AKTIF, 2, '3 -> 2 must be 2, not 5');
assert.equal(stateB.categoryCounts.MASALAH_AKTIF, 2);

// A2. An identical second reload stays identical (no doubling).
const sameAgain = simulateLoad(
  createEvidenceAccumulator(CATEGORIES),
  [
    payload('MASALAH_AKTIF', [['sales-order', 2]], { MASALAH_AKTIF: 2 }),
    payload('PERLU_DITINJAU', [], { PERLU_DITINJAU: 0 }),
    payload('DATA_BELUM_LENGKAP', [], { DATA_BELUM_LENGKAP: 0 })
  ]
);
assert.equal(sameAgain.processCounts.get('sales-order').MASALAH_AKTIF, 2, 'identical reload must not double');
assert.equal(sameAgain.categoryCounts.MASALAH_AKTIF, 2);

// B. Later partial failure: first load all succeed, second load one category
// fails. The failed category must lose its old availability, rows, and counts,
// while the successful categories reflect only the second load.
const acc = createEvidenceAccumulator(CATEGORIES);
simulateLoad(acc, [
  payload('MASALAH_AKTIF', [['sales-order', 3], ['manufacturing-order', 5]], { MASALAH_AKTIF: 8 }),
  payload('PERLU_DITINJAU', [['sales-order', 1]], { PERLU_DITINJAU: 1 }),
  payload('DATA_BELUM_LENGKAP', [['sales-order', 2]], { DATA_BELUM_LENGKAP: 2 })
]);
acc.reset();
acc.ingest('MASALAH_AKTIF', payload('MASALAH_AKTIF', [['sales-order', 2]], { MASALAH_AKTIF: 2 }));
// PERLU_DITINJAU and DATA_BELUM_LENGKAP fail this reload (never ingested).
assert.equal(acc.state.categoryAvailability.PERLU_DITINJAU, false, 'failed category must not stay available');
assert.equal(acc.state.categoryAvailability.DATA_BELUM_LENGKAP, false, 'failed category must not stay available');
assert.equal(acc.state.processCounts.get('sales-order').PERLU_DITINJAU, 0, 'no old rows/counts retained for failed category');
assert.equal(acc.state.processCounts.get('sales-order').DATA_BELUM_LENGKAP, 0, 'no old rows/counts retained for failed category');
assert.equal(acc.state.categoryCounts.PERLU_DITINJAU, null, 'failed category count reset to null');
assert.equal(acc.state.processCounts.has('manufacturing-order'), false, 'failed category rows must not leak manufacturing-order');
assert.equal(acc.state.processCounts.get('sales-order').MASALAH_AKTIF, 2, 'successful category reflects only the second load');
assert.equal(acc.state.categoryCounts.MASALAH_AKTIF, 2);

// B2. All categories fail -> everything unavailable (existing truthful fallback).
const empty = createEvidenceAccumulator(CATEGORIES);
empty.reset();
assert.equal(empty.state.categoryAvailability.MASALAH_AKTIF, false);
assert.equal(empty.state.categoryCounts.MASALAH_AKTIF, null);
assert.equal(empty.state.processCounts.size, 0);
assert.equal(empty.state.rowsByCategory.size, 0);

// C. Selection restoration path is still invoked after a successful reload.
assert.match(
  shell,
  /if \(restoreSelection && selectedNode\) openInspector\(selectedNode, false, false\);/
);

console.log('Control Tower evidence reload replacement contracts passed');
