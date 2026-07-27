(function exposeControlTowerAdapter(root, factory) {
  const adapter = factory();
  if (typeof module === "object" && module.exports) module.exports = adapter;
  root.ControlTowerAdapter = adapter;
})(typeof globalThis !== "undefined" ? globalThis : this, function createControlTowerAdapter() {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value, options = {}) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("id-ID", options) : "—";
  }

  function formatMoney(value) {
    if (value === null || value === undefined || value === "") return "Belum tersedia";
    const number = Number(value);
    if (!Number.isFinite(number)) return "Belum tersedia";
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(number);
  }

  function formatPercent(value) {
    if (value === null || value === undefined || value === "") return "Belum tersedia";
    const number = Number(value);
    if (!Number.isFinite(number)) return "Belum tersedia";
    const normalized = Math.abs(number) <= 1 ? number * 100 : number;
    return `${normalized.toLocaleString("id-ID", { maximumFractionDigits: 2 })}%`;
  }

  function formatDateTime(value) {
    if (!value) return "Belum tersedia";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "Belum tersedia";
    return new Intl.DateTimeFormat("id-ID", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Jakarta",
    }).format(parsed);
  }

  function categoryTone(category) {
    return {
      "Masalah Aktif": "danger",
      "Perlu Ditinjau": "warning",
      "Data Belum Lengkap": "info",
    }[category] || "neutral";
  }

  function detailRoute(model, recordId, tab = "summary") {
    const query = new URLSearchParams({ view: "document", model, id: String(recordId), tab });
    return `/control-tower?${query}`;
  }

  return Object.freeze({
    escapeHtml,
    formatNumber,
    formatMoney,
    formatPercent,
    formatDateTime,
    categoryTone,
    detailRoute,
  });
});
