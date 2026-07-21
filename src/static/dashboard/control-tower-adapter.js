(function exposeControlTowerAdapter(root, factory) {
  const adapter = factory();
  if (typeof module === "object" && module.exports) module.exports = adapter;
  root.ControlTowerAdapter = adapter;
})(typeof globalThis !== "undefined" ? globalThis : this, function createControlTowerAdapter() {
  "use strict";

  const STALE_AFTER_HOURS = 24;

  const STATUS_PRESENTATION = Object.freeze({
    VALIDATED: { label: "Sesuai", tone: "success", group: "compliant" },
    MISMATCH: { label: "Masalah Aktif", tone: "danger", group: "active" },
    PARTIAL_MATCH: { label: "Perlu Ditinjau", tone: "warning", group: "review" },
    DATA_EXCEPTION: { label: "Bukti Sistem Belum Lengkap", tone: "info", group: "incomplete" },
    DATA_LINKAGE_GAP: { label: "Bukti Sistem Belum Lengkap", tone: "info", group: "incomplete" },
    DOCUMENT_LINK_GAP: { label: "Hubungan Dokumen Belum Lengkap", tone: "info", group: "incomplete" },
    MANUAL_EVIDENCE_REQUIRED: { label: "Memerlukan Bukti Manual", tone: "neutral", group: "manual" },
    HISTORICAL_EXPOSURE: { label: "Catatan Historis", tone: "history", group: "historical" },
    DATE_SCOPE_UNKNOWN: { label: "Tanggal Dokumen Belum Tersedia", tone: "warning", group: "review" },
    MAPPING_PENDING: { label: "Belum Dapat Diperiksa Otomatis", tone: "neutral", group: "pending" },
    NOT_TESTED: { label: "Belum Dapat Diperiksa Otomatis", tone: "neutral", group: "pending" },
    VALID_EXCEPTION: { label: "Pengecualian Tercatat", tone: "neutral", group: "reviewed" },
  });

  const RULE_PRESENTATION = Object.freeze({
    "SO-PO-001": {
      title: "Referensi PO pelanggan tersedia pada Sales Order terkonfirmasi",
      explanation: "Pemeriksaan memastikan nomor referensi dan tanggal PO pelanggan tersedia untuk Sales Order yang sudah dikonfirmasi mulai tahun 2026.",
      why: "Referensi tersebut menghubungkan pesanan pelanggan dengan dokumen penjualan yang diproses.",
      impact: "Referensi yang tidak lengkap dapat memperlambat verifikasi pesanan dan penelusuran dokumen pelanggan.",
      reviewer: "Marketing / Admin Sales",
      process: "Sales Order",
    },
    "SO-SOURCE-001": {
      title: "Sumber pemenuhan Sales Order belum dapat dipastikan",
      explanation: "Sumber pemenuhan perlu dapat dibaca per baris Sales Order, termasuk ketika satu pesanan memakai lebih dari satu sumber.",
      why: "PPIC dan Marketing perlu mengetahui apakah kebutuhan dipenuhi dari stok, Internal Order, atau proses lain.",
      impact: "Sumber yang belum jelas dapat mengaburkan kebutuhan produksi atau pengadaan.",
      reviewer: "Marketing / PPIC",
      process: "Sales Order",
    },
    "SO-CANCEL-001": {
      title: "Sales Order sudah dibatalkan, tetapi dokumen operasional masih terbuka",
      explanation: "Pembatalan Sales Order perlu ditinjau bersama Manufacturing Order, Delivery, Purchase Order, Invoice, atau backorder yang masih aktif.",
      why: "Dokumen lanjutan yang terbuka dapat tetap terlihat sebagai pekerjaan operasional.",
      impact: "Produksi, gudang, pengadaan, atau penagihan dapat memproses pesanan yang sudah tidak berlaku.",
      reviewer: "Marketing bersama pemilik dokumen terkait",
      process: "Pembatalan Sales Order",
    },
    "PO-CANCEL-001": {
      title: "PO sudah dibatalkan, tetapi penerimaan barang masih terbuka",
      explanation: "Pemeriksaan membandingkan PO yang dibatalkan dengan dokumen penerimaan barang yang masih aktif.",
      why: "Penerimaan harus selaras dengan keputusan pembatalan pembelian.",
      impact: "Dokumen penerimaan yang masih terbuka dapat membuat gudang melihat pekerjaan untuk pembelian yang sudah tidak berlaku.",
      reviewer: "Procurement / WHD",
      process: "Pembatalan Purchase Order",
    },
    "PO-DRAFT-001": {
      title: "PO berstatus draft dengan dokumen lanjutan perlu ditinjau",
      explanation: "Status draft saja tidak membuktikan bahwa Reset to Draft terjadi; histori dan dokumen lanjutan perlu diperiksa.",
      why: "Koreksi PO dapat meninggalkan Receipt, pergerakan stok, atau tagihan yang masih terbuka.",
      impact: "Dokumen lanjutan dapat tidak lagi selaras dengan PO yang sedang dikoreksi.",
      reviewer: "Procurement / WHD",
      process: "Koreksi Purchase Order",
    },
    "SO-IO-MO-001": {
      title: "Hubungan Sales Order, Internal Order, dan Manufacturing Order perlu ditinjau",
      explanation: "Sinyal ini mencari bukti bahwa Manufacturing Order pada Sales Order berbasis Internal Order ditangani sesuai sumber pemenuhannya.",
      why: "Hubungan pada tingkat baris diperlukan sebelum menyimpulkan apakah Manufacturing Order memang harus dihentikan.",
      impact: "Kesimpulan yang terlalu cepat dapat membuat rencana produksi dibaca tidak sesuai konteks pesanan.",
      reviewer: "Marketing / PPIC",
      process: "Sales Order ke Internal Order / Produksi",
    },
    "IO-PROD-001": {
      title: "Bukti produksi untuk Internal Order belum lengkap",
      explanation: "Status produksi dibandingkan pada pasangan produk dan satuan ukur yang sama; bukti ambigu tetap ditandai untuk ditinjau.",
      why: "Status administratif Internal Order bukan bukti kemajuan produksi.",
      impact: "Kemajuan produksi dapat terbaca terlalu tinggi atau terlalu rendah bila hubungan produk atau satuan ukur belum aman.",
      reviewer: "PPIC",
      process: "Internal Order / Produksi",
    },
    "IO-UTIL-001": {
      title: "Bukti pemanfaatan Internal Order belum lengkap",
      explanation: "Pemanfaatan dibandingkan dengan Sales Order terkait tanpa membuat alokasi buatan ketika satu Sales Order terhubung ke beberapa Internal Order.",
      why: "Pemanfaatan harus didukung hubungan dokumen dan kuantitas yang dapat ditelusuri.",
      impact: "Kebutuhan yang belum termanfaatkan atau alokasi ganda dapat tidak terlihat dengan benar.",
      reviewer: "PPIC / Marketing",
      process: "Internal Order / Pemanfaatan",
    },
    "JO-DIST-001": {
      title: "Distribusi JO memerlukan bukti manual",
      explanation: "Distribusi JO berlangsung di luar bukti status Odoo yang tersedia dan tidak disimpulkan otomatis.",
      why: "Bukti manual diperlukan untuk memastikan JO benar-benar sudah didistribusikan.",
      impact: "Tanpa bukti tersebut, status distribusi belum dapat dipastikan dari sistem.",
      reviewer: "Marketing / Operations",
      process: "Distribusi JO",
    },
    "PAY-001": {
      title: "Status Payment belum dipublikasikan",
      explanation: "Klasifikasi Payment menunggu keputusan Accounting mengenai sisa tagihan, rekonsiliasi, penyesuaian, DP, dan kelebihan bayar.",
      why: "Status pembayaran harus mengikuti bukti akuntansi, bukan kolom salinan pada Sales Order.",
      impact: "Menerbitkan status terlalu dini dapat memberi gambaran pelunasan yang keliru.",
      reviewer: "Accounting",
      process: "Payment",
    },
  });

  const MODEL_LABELS = Object.freeze({
    "sale.order": "Sales Order",
    "sale.order.line": "Baris Sales Order",
    "approval.request": "Internal Order",
    "approval.product.line": "Baris Internal Order",
    "mrp.production": "Manufacturing Order",
    "purchase.order": "Purchase Order",
    "purchase.order.line": "Baris Purchase Order",
    "stock.picking": "Penerimaan / Pengiriman",
    "stock.move": "Pergerakan Stok",
    "account.move": "Invoice",
  });

  const STATE_LABELS = Object.freeze({
    draft: "Draft",
    to_submit: "Menunggu Pengajuan",
    pending: "Menunggu",
    confirmed: "Dikonfirmasi",
    approved: "Disetujui",
    sale: "Terkonfirmasi",
    purchase: "Terkonfirmasi",
    assigned: "Siap Diproses",
    waiting: "Menunggu Dokumen Lain",
    confirmed_waiting: "Menunggu",
    progress: "Sedang Diproses",
    done: "Selesai",
    posted: "Dibukukan",
    cancel: "Dibatalkan",
    cancelled: "Dibatalkan",
  });

  const PROCESS_FILTERS = Object.freeze([
    ["Control Point Cancellation", "Pembatalan Sales Order"],
    ["SOP Internal Order", "Internal Order"],
    ["SOP 3.1-3.2", "Sales Order dan sumber pemenuhan"],
  ]);

  const OWNER_FILTERS = Object.freeze([
    "Multi-owner",
    "PPIC",
    "PPIC / Marketing",
    "Marketing / PPIC",
  ]);

  function asNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value) {
    return asNumber(value).toLocaleString("id-ID");
  }

  function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${Number(value).toLocaleString("id-ID", { maximumFractionDigits: 2 })}%`;
  }

  function formatDateTime(value) {
    if (!value) return "Belum tersedia";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Belum tersedia";
    return new Intl.DateTimeFormat("id-ID", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Jakarta",
    }).format(date);
  }

  function statusPresentation(rawStatus) {
    const raw = String(rawStatus || "MAPPING_PENDING").toUpperCase();
    return { raw, ...(STATUS_PRESENTATION[raw] || { label: "Perlu Ditinjau", tone: "warning", group: "review" }) };
  }

  function confidencePresentation(confidence) {
    const raw = String(confidence || "UNKNOWN").toUpperCase();
    if (raw === "HIGH") return { raw, label: "Bukti kuat", tone: "success" };
    if (raw === "MEDIUM") return { raw, label: "Bukti perlu konfirmasi", tone: "warning" };
    if (raw === "LOW") return { raw, label: "Bukti belum lengkap", tone: "info" };
    return { raw, label: "Kekuatan bukti belum tersedia", tone: "neutral" };
  }

  function ruleEvidencePresentation(implementationClass) {
    const raw = String(implementationClass || "").toUpperCase();
    if (raw.startsWith("DETERMINISTIC")) return "Bukti sistem kuat";
    if (raw === "MANUAL_EVIDENCE_ONLY") return "Bukti manual";
    if (raw === "OWNER_DECISION_REQUIRED") return "Menunggu keputusan pemilik proses";
    if (raw === "REVIEW_SIGNAL") return "Sinyal untuk ditinjau";
    return "Bukti sistem perlu konfirmasi";
  }

  function freshnessState(health, now = Date.now()) {
    const completedAt = health?.latest_run?.completed_at;
    if (health?.status !== "READY" || !completedAt) {
      return {
        state: "failed",
        tone: "danger",
        label: "Data terbaru belum tersedia",
        detail: "Run terakhir belum selesai atau backend belum siap. Coba muat ulang setelah proses data selesai.",
      };
    }
    const ageHours = Math.max(0, (now - new Date(completedAt).getTime()) / 3_600_000);
    if (ageHours > STALE_AFTER_HOURS) {
      return {
        state: "stale",
        tone: "warning",
        label: "Data sudah lebih dari 24 jam",
        detail: `Data terakhir diperbarui ${formatDateTime(completedAt)}. Konfirmasikan refresh sebelum mengambil keputusan operasional.`,
      };
    }
    return {
      state: "fresh",
      tone: "success",
      label: "Data terbaru tersedia",
      detail: `Data terakhir diperbarui ${formatDateTime(completedAt)}.`,
    };
  }

  function poScopeSummary(rows) {
    const result = { checked: 0, active: 0, historicalRoots: 0, historical: 0, backorders: 0, unknown: 0 };
    for (const row of rows || []) {
      if (row.date_scope === "ACTIVE_2026_PLUS") {
        result.checked = asNumber(row.cancelled_po_roots);
        result.active = asNumber(row.masalah_aktif_2026_plus);
      } else if (row.date_scope === "HISTORICAL_PRE_2026") {
        result.historicalRoots = asNumber(row.cancelled_po_roots);
        result.historical = asNumber(row.catatan_historis);
        result.backorders = asNumber(row.open_backorders);
      } else if (row.date_scope === "DATE_SCOPE_UNKNOWN") {
        result.unknown = asNumber(row.tanggal_po_belum_tersedia);
      }
    }
    return result;
  }

  function normalizeRule(row, context = {}) {
    const presentation = RULE_PRESENTATION[row.rule_id] || {
      title: row.rule_name || "Pemeriksaan proses",
      explanation: "Pemeriksaan ini memerlukan konteks proses tambahan.",
      why: "Konsistensi dokumen perlu dapat ditelusuri.",
      impact: "Ketidakjelasan dapat memperlambat peninjauan operasional.",
      reviewer: row.owner || "Pemilik proses terkait",
      process: row.sop_section || "Lintas proses",
    };
    const po = context.po || poScopeSummary([]);
    const isPoCancellation = row.rule_id === "PO-CANCEL-001";
    const activeIssues = isPoCancellation ? po.active : asNumber(row.mismatch_records);
    const historicalCount = isPoCancellation ? po.historical : 0;
    const checkedCount = isPoCancellation ? po.checked : asNumber(row.tested_records);
    const compliantCount = isPoCancellation ? po.checked - po.active : asNumber(row.validated_records);
    return {
      ...presentation,
      ruleId: row.rule_id,
      rawRuleName: row.rule_name,
      rawStatus: row.overall_status,
      status: statusPresentation(row.overall_status),
      checkedCount,
      compliantCount,
      activeIssues,
      historicalCount,
      reviewRequired: asNumber(row.partial_match_records),
      incompleteEvidence: asNumber(row.linkage_gap_records),
      evidenceStrength: ruleEvidencePresentation(row.implementation_class),
      latestEvaluation: context.completedAt || null,
      owner: presentation.reviewer || row.owner,
      validationRate: row.validation_rate_percent,
      currentSummary: isPoCancellation
        ? `${formatNumber(po.active)} masalah aktif mulai tahun 2026; ${formatNumber(po.historical)} catatan historis sebelum tahun 2026.`
        : null,
    };
  }

  function overviewMetrics(health, validationRows, poRows, ioSummary) {
    const rows = validationRows || [];
    const po = poScopeSummary(poRows);
    return {
      checksPerformed: asNumber(health?.rule_result_count),
      compliant: rows.reduce((sum, row) => sum + asNumber(row.validated_records), 0),
      active: rows.reduce((sum, row) => sum + asNumber(row.mismatch_records), 0),
      historical: po.historical,
      review: rows.reduce((sum, row) => sum + asNumber(row.partial_match_records), 0),
      incomplete: rows.reduce((sum, row) => sum + asNumber(row.linkage_gap_records), 0),
      ioRoots: asNumber(ioSummary?.internal_order_roots),
      ioRows: asNumber(ioSummary?.product_uom_rows),
      productionGaps: asNumber(ioSummary?.production_evidence_gaps),
      utilizationGaps: asNumber(ioSummary?.utilization_evidence_gaps),
      po,
    };
  }

  function documentLink(model, id) {
    if (!model || !Number.isFinite(Number(id))) return null;
    const params = new URLSearchParams({ view: "journey", model: String(model), id: String(id) });
    return `/dashboard/control-tower?${params.toString()}`;
  }

  function relatedDocuments(row) {
    const actual = row.actual_condition || {};
    const documents = [];
    for (const item of actual.open_documents || []) {
      if (item?.number) documents.push({ number: item.number, model: item.model, state: item.state });
    }
    if (actual.sales_order_number) {
      documents.push({ number: actual.sales_order_number, model: "sale.order", state: null });
    }
    return documents;
  }

  function normalizeException(row) {
    const presentation = RULE_PRESENTATION[row.rule_id] || {};
    const status = statusPresentation(row.validation_status);
    return {
      type: "exception",
      ruleId: row.rule_id,
      status,
      situation: presentation.title || row.rule_name || "Kondisi perlu ditinjau",
      explanation: presentation.explanation || "Bukti sistem memerlukan peninjauan lebih lanjut.",
      why: presentation.why || "Konsistensi dokumen perlu dipastikan.",
      impact: presentation.impact || "Proses terkait dapat tidak terbaca secara lengkap.",
      reviewer: presentation.reviewer || row.owner || "Pemilik proses terkait",
      process: presentation.process || row.sop_section || "Lintas proses",
      affectedDocument: row.document_number || "Nomor dokumen tidak tersedia",
      affectedModel: MODEL_LABELS[row.document_model] || row.document_model || "Dokumen",
      relatedDocuments: relatedDocuments(row),
      confidence: confidencePresentation(row.confidence),
      severity: String(row.severity || "UNKNOWN").toUpperCase(),
      detectedAt: row.detected_at,
      journeyUrl: documentLink(row.document_model, row.document_id),
      rawStatus: row.validation_status,
    };
  }

  function normalizeHistoricalPo(row) {
    const isBackorder = asNumber(row.open_backorder_count) > 0;
    return {
      type: "historical-po",
      ruleId: "PO-CANCEL-001",
      status: statusPresentation("HISTORICAL_EXPOSURE"),
      situation: isBackorder
        ? "PO sudah dibatalkan dan penerimaan utama telah selesai, tetapi dokumen penerimaan sisa atau backorder masih terbuka."
        : "PO sudah dibatalkan, tetapi dokumen penerimaan barang masih terbuka.",
      explanation: "Kasus ini berasal dari PO sebelum tahun 2026. Kasus tetap ditampilkan untuk audit, tetapi tidak masuk ke daftar masalah operasional aktif.",
      why: "Catatan ini mempertahankan jejak audit atas penerimaan yang belum tertutup ketika PO dibatalkan.",
      impact: RULE_PRESENTATION["PO-CANCEL-001"].impact,
      reviewer: RULE_PRESENTATION["PO-CANCEL-001"].reviewer,
      process: RULE_PRESENTATION["PO-CANCEL-001"].process,
      affectedDocument: row.purchase_order_number || "Nomor PO tidak tersedia",
      affectedModel: "Purchase Order",
      relatedDocuments: (row.open_receipts || []).map((receipt) => ({
        number: receipt.number,
        model: "stock.picking",
        state: receipt.state,
      })),
      confidence: confidencePresentation(row.relation_confidence),
      severity: "HISTORICAL",
      detectedAt: row.date_order,
      journeyUrl: documentLink("purchase.order", row.purchase_order_id),
      rawStatus: row.operational_exposure,
      isBackorder,
    };
  }

  function exceptionRequest(filters = {}) {
    const classification = filters.classification || "active";
    const params = new URLSearchParams({
      limit: String(filters.limit || 25),
      offset: String(filters.offset || 0),
    });
    if (classification === "historical") {
      params.set("date_scope", "HISTORICAL_PRE_2026");
      params.set("operational_exposure", "HISTORICAL_EXPOSURE");
      return { kind: "historical", url: `/api/control-tower/po-cancellation-scope?${params}` };
    }
    const technicalStatus = {
      active: "MISMATCH",
      review: "PARTIAL_MATCH",
      incomplete: "DATA_LINKAGE_GAP",
    }[classification] || "MISMATCH";
    params.set("validation_status", technicalStatus);
    if (filters.rule) params.set("rule_id", filters.rule);
    for (const key of ["process", "owner", "severity", "document", "date_from", "date_to"]) {
      if (filters[key]) params.set(key, filters[key]);
    }
    return { kind: "exception", url: `/api/control-tower/exceptions?${params}` };
  }

  function emptyMessage(classification, process) {
    if (classification === "active" && process === "PO-CANCEL-001") {
      return "Tidak ada masalah aktif untuk PO yang dibatalkan mulai tahun 2026.";
    }
    return {
      active: "Tidak ada masalah aktif untuk filter yang dipilih.",
      historical: "Tidak ada catatan historis untuk filter yang dipilih.",
      review: "Tidak ada data yang perlu ditinjau untuk filter yang dipilih.",
      incomplete: "Tidak ada bukti sistem yang belum lengkap untuk filter yang dipilih.",
    }[classification] || "Tidak ada data untuk filter yang dipilih.";
  }

  function shouldShowActivePoEmptyState(filters, total) {
    return filters.classification === "active"
      && filters.rule === "PO-CANCEL-001"
      && asNumber(total) === 0;
  }

  function classifyHttpStatus(status) {
    if (status === 401) return "session-expired";
    if (status >= 500) return "service-error";
    if (status >= 400) return "request-error";
    return "ok";
  }

  function statePresentation(rawState) {
    const raw = String(rawState || "unknown").toLowerCase();
    const tone = ["done", "posted", "sale", "purchase", "approved"].includes(raw)
      ? "success"
      : ["cancel", "cancelled"].includes(raw)
        ? "history"
        : ["draft", "pending", "waiting", "assigned", "progress", "confirmed"].includes(raw)
          ? "warning"
          : "neutral";
    return { raw, label: STATE_LABELS[raw] || "Status belum tersedia", tone };
  }

  function relationEvidencePresentation(rawEvidence) {
    const raw = String(rawEvidence || "MAPPING_PENDING").toUpperCase();
    if (raw === "DIRECT_RELATION") return { raw, label: "Bukti langsung", tone: "success" };
    if (raw === "DERIVED_PATH") return { raw, label: "Bukti turunan", tone: "info" };
    if (raw === "MANUAL_EVIDENCE_REQUIRED") return { raw, label: "Bukti manual", tone: "neutral" };
    return { raw, label: "Hubungan belum lengkap", tone: "warning" };
  }

  function normalizeJourney(payload) {
    const root = payload?.root || null;
    const safeRoot = root
      ? {
          model: root.model,
          modelLabel: MODEL_LABELS[root.model] || root.model,
          id: root.record_id,
          number: root.document_number || "Nomor dokumen tidak tersedia",
          state: statePresentation(root.state),
          extractedAt: root.extracted_at,
        }
      : null;
    const links = (payload?.links || []).map((link) => ({
      depth: asNumber(link.depth),
      parent: {
        model: link.parent_model,
        modelLabel: MODEL_LABELS[link.parent_model] || link.parent_model,
        id: link.parent_id,
        number: link.parent_number || "Nomor tidak tersedia",
        state: statePresentation(link.parent_state),
      },
      child: {
        model: link.child_model,
        modelLabel: MODEL_LABELS[link.child_model] || link.child_model,
        id: link.child_id,
        number: link.child_number || "Nomor tidak tersedia",
        state: statePresentation(link.child_state),
      },
      linkType: link.link_type,
      confidence: confidencePresentation(link.confidence),
      evidence: relationEvidencePresentation(link.relation_evidence),
    }));
    const presentModels = new Set([safeRoot?.model, ...links.flatMap((link) => [link.parent.model, link.child.model])].filter(Boolean));
    const expectedStages = [
      ["sale.order", "Sales Order"],
      ["approval.request", "Internal Order"],
      ["mrp.production", "Manufacturing Order"],
      ["purchase.order", "Purchase Order"],
      ["stock.picking", "Penerimaan / Pengiriman"],
      ["account.move", "Invoice"],
    ].map(([model, label]) => ({ model, label, available: presentModels.has(model) }));
    return { root: safeRoot, links, expectedStages };
  }

  return Object.freeze({
    STALE_AFTER_HOURS,
    STATUS_PRESENTATION,
    RULE_PRESENTATION,
    MODEL_LABELS,
    PROCESS_FILTERS,
    OWNER_FILTERS,
    escapeHtml,
    formatNumber,
    formatPercent,
    formatDateTime,
    statusPresentation,
    confidencePresentation,
    freshnessState,
    poScopeSummary,
    normalizeRule,
    overviewMetrics,
    normalizeException,
    normalizeHistoricalPo,
    exceptionRequest,
    emptyMessage,
    shouldShowActivePoEmptyState,
    classifyHttpStatus,
    statePresentation,
    relationEvidencePresentation,
    normalizeJourney,
    documentLink,
  });
});
