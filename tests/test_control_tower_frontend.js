"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const A = require("../src/static/dashboard/control-tower-adapter.js");
const UI_SOURCE = fs.readFileSync(
  require.resolve("../src/static/dashboard/control-tower.js"),
  "utf8",
);

test("technical statuses use centralized Indonesian language", () => {
  const expected = {
    VALIDATED: "Sesuai",
    MISMATCH: "Masalah Aktif",
    PARTIAL_MATCH: "Perlu Ditinjau",
    DATA_EXCEPTION: "Bukti Sistem Belum Lengkap",
    DOCUMENT_LINK_GAP: "Hubungan Dokumen Belum Lengkap",
    MANUAL_EVIDENCE_REQUIRED: "Memerlukan Bukti Manual",
    HISTORICAL_EXPOSURE: "Catatan Historis",
    DATE_SCOPE_UNKNOWN: "Tanggal Dokumen Belum Tersedia",
    MAPPING_PENDING: "Belum Dapat Diperiksa Otomatis",
  };

  for (const [raw, label] of Object.entries(expected)) {
    assert.equal(A.statusPresentation(raw).label, label);
  }
  assert.equal(A.statusPresentation("DATA_LINKAGE_GAP").label, "Bukti Sistem Belum Lengkap");
  assert.notEqual(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED").tone, "danger");
});

test("PO cancellation keeps active and historical counts separate", () => {
  const po = A.poScopeSummary([
    {
      date_scope: "ACTIVE_2026_PLUS",
      cancelled_po_roots: 348,
      masalah_aktif_2026_plus: 0,
    },
    {
      date_scope: "HISTORICAL_PRE_2026",
      cancelled_po_roots: 861,
      catatan_historis: 35,
      open_backorders: 1,
    },
  ]);
  const rule = A.normalizeRule(
    {
      rule_id: "PO-CANCEL-001",
      rule_name: "technical",
      overall_status: "VALIDATED",
      implementation_class: "DETERMINISTIC",
      tested_records: 348,
      validated_records: 348,
    },
    { po },
  );

  assert.deepEqual(po, {
    checked: 348,
    active: 0,
    historicalRoots: 861,
    historical: 35,
    backorders: 1,
    unknown: 0,
  });
  assert.equal(rule.checkedCount, 348);
  assert.equal(rule.compliantCount, 348);
  assert.equal(rule.activeIssues, 0);
  assert.equal(rule.historicalCount, 35);
  assert.equal(rule.currentSummary, "0 masalah aktif mulai tahun 2026; 35 catatan historis sebelum tahun 2026.");
});

test("historical open backorder uses the approved explanation", () => {
  const item = A.normalizeHistoricalPo({
    purchase_order_id: 1,
    purchase_order_number: "PO-TEST",
    operational_exposure: "HISTORICAL_EXPOSURE",
    open_backorder_count: 1,
    open_receipts: [{ number: "WH-IN-TEST", state: "assigned" }],
    relation_confidence: "HIGH",
  });

  assert.equal(
    item.situation,
    "PO sudah dibatalkan dan penerimaan utama telah selesai, tetapi dokumen penerimaan sisa atau backorder masih terbuka.",
  );
  assert.match(item.explanation, /sebelum tahun 2026/);
  assert.equal(item.status.label, "Catatan Historis");
});

test("exception requests are filtered and paginated on the server", () => {
  const active = A.exceptionRequest({
    classification: "active",
    rule: "SO-CANCEL-001",
    process: "Control Point Cancellation",
    document: "SO-TEST",
    date_from: "2026-01-01",
    date_to: "2026-07-21",
    limit: 25,
    offset: 25,
  });
  const historical = A.exceptionRequest({ classification: "historical", limit: 25, offset: 0 });

  assert.match(active.url, /validation_status=MISMATCH/);
  assert.match(active.url, /rule_id=SO-CANCEL-001/);
  assert.match(active.url, /process=Control\+Point\+Cancellation/);
  assert.match(active.url, /document=SO-TEST/);
  assert.match(active.url, /offset=25/);
  assert.match(historical.url, /po-cancellation-scope/);
  assert.match(historical.url, /HISTORICAL_PRE_2026/);
  assert.match(historical.url, /HISTORICAL_EXPOSURE/);
});

test("overview totals do not mix historical PO findings into active issues", () => {
  const metrics = A.overviewMetrics(
    { rule_result_count: 5207 },
    [
      { validated_records: 348, mismatch_records: 0, partial_match_records: 0, linkage_gap_records: 0 },
      { validated_records: 23, mismatch_records: 1, partial_match_records: 0, linkage_gap_records: 0 },
      { validated_records: 562, mismatch_records: 0, partial_match_records: 280, linkage_gap_records: 324 },
    ],
    [{ date_scope: "HISTORICAL_PRE_2026", catatan_historis: 35 }],
    { internal_order_roots: 118, product_uom_rows: 824 },
  );

  assert.equal(metrics.active, 1);
  assert.equal(metrics.historical, 35);
  assert.equal(metrics.review, 280);
  assert.equal(metrics.incomplete, 324);
  assert.equal(metrics.ioRoots, 118);
  assert.equal(metrics.ioRows, 824);
});

test("Payment and Distribusi JO remain neutral unpublished/manual states", () => {
  assert.equal(A.RULE_PRESENTATION["PAY-001"].title, "Status Payment belum dipublikasikan");
  assert.equal(A.RULE_PRESENTATION["JO-DIST-001"].title, "Distribusi JO memerlukan bukti manual");
  assert.notEqual(A.statusPresentation("MAPPING_PENDING").tone, "danger");
  assert.notEqual(A.statusPresentation("MANUAL_EVIDENCE_REQUIRED").tone, "danger");
});

test("journey normalization ignores raw payload and keeps relation states", () => {
  const journey = A.normalizeJourney({
    root: {
      model: "purchase.order",
      record_id: 10,
      document_number: "PO-TEST",
      state: "cancel",
      payload: { private_value: "must-not-render" },
    },
    links: [
      {
        depth: 1,
        parent_model: "purchase.order",
        parent_id: 10,
        parent_number: "PO-TEST",
        parent_state: "cancel",
        child_model: "stock.picking",
        child_id: 20,
        child_number: "WH-IN-TEST",
        child_state: "assigned",
        relation_evidence: "DIRECT_RELATION",
        confidence: "HIGH",
      },
    ],
  });

  assert.equal(journey.root.payload, undefined);
  assert.equal(journey.root.state.label, "Dibatalkan");
  assert.equal(journey.links[0].child.state.label, "Siap Diproses");
  assert.equal(journey.links[0].evidence.label, "Bukti langsung");
});

test("empty, failure, session, and stale states are explicit", () => {
  assert.equal(
    A.emptyMessage("active", "PO-CANCEL-001"),
    "Tidak ada masalah aktif untuk PO yang dibatalkan mulai tahun 2026.",
  );
  assert.equal(A.classifyHttpStatus(401), "session-expired");
  assert.equal(A.classifyHttpStatus(500), "service-error");
  assert.equal(
    A.freshnessState(
      { status: "READY", latest_run: { completed_at: "2026-07-19T00:00:00+07:00" } },
      new Date("2026-07-21T12:00:00+07:00").getTime(),
    ).state,
    "stale",
  );
});

test("active PO empty state never contradicts another active issue", () => {
  assert.equal(A.shouldShowActivePoEmptyState({ classification: "active", rule: "" }, 1), false);
  assert.equal(A.shouldShowActivePoEmptyState({ classification: "active", rule: "PO-CANCEL-001" }, 1), false);
  assert.equal(A.shouldShowActivePoEmptyState({ classification: "active", rule: "PO-CANCEL-001" }, 0), true);
});

test("worklist and journey deep-links load freshness evidence", () => {
  const exceptionSource = UI_SOURCE.slice(
    UI_SOURCE.indexOf("async function renderExceptions"),
    UI_SOURCE.indexOf("function journeySearch"),
  );
  const journeySource = UI_SOURCE.slice(
    UI_SOURCE.indexOf("async function renderJourney"),
    UI_SOURCE.indexOf("function loadCurrentView"),
  );
  assert.match(exceptionSource, /api\/control-tower\/health/);
  assert.match(exceptionSource, /showFreshness\(health\)/);
  assert.match(journeySource, /api\/control-tower\/health/);
  assert.match(journeySource, /showFreshness\(health\)/);
});
