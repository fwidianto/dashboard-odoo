const fs = require("node:fs");
"use strict";
const assert = require("node:assert/strict");
const page = fs.readFileSync("src/static/dashboard/control-tower.html", "utf8");
const shell = fs.readFileSync("src/static/dashboard/control-tower-shell.js", "utf8");
const api = fs.readFileSync("src/api.py", "utf8");
assert.doesNotMatch(page, /[\u00c2\u00c3]/);
assert.match(page, /class="ct-immersive-page"/);
for (const attribute of [
  "data-ct-freshness",
  "data-ct-refresh",
  "data-ct-mode-toggle",
  "data-ct-temuan",
  "data-ct-inspector",
  "data-ct-open-documents",
  "data-ct-map-scroll",
  "data-ct-scroll-cue"
]) assert.match(page, new RegExp(attribute), attribute);
for (const key of ["sales-order", "manufacturing-order", "internal-order", "material-purchase-order"]) {
  assert.match(page, new RegExp('data-process-key="' + key + '"'), key);
}
for (const category of ["MASALAH_AKTIF", "PERLU_DITINJAU", "DATA_BELUM_LENGKAP"]) {
  assert.match(page, new RegExp('data-ct-category-count="' + category + '"'), category);
  assert.match(page, new RegExp('data-ct-inspector-count="' + category + '"'), category);
}
assert.match(page, /data-ct-process-node/);
assert.match(shell, /function evidenceStateForNode/);
assert.match(shell, /coverage\.state !== "MAPPED"/);
assert.match(shell, /function coverageMessageForNode/);
assert.match(shell, /function formatCount/);
assert.match(shell, /Promise\.allSettled/);
assert.match(shell, /categoryDestination/);
assert.match(shell, /\/dashboard\/control-tower\/temuan/);
assert.match(api, /@app\.get\("\/dashboard\/control-tower"/);
console.log("Immersive Process Map static contracts passed");
