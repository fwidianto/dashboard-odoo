(function setupDashboardExport() {
  function timestampSuffix() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return [
      now.getFullYear(),
      pad(now.getMonth() + 1),
      pad(now.getDate()),
      "_",
      pad(now.getHours()),
      pad(now.getMinutes()),
    ].join("");
  }

  function safeFilePart(value, fallback = "dashboard") {
    const text = String(value || "").trim();
    if (!text) return fallback;
    return text.replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || fallback;
  }

  function buildSheetData({ columns, rows, visibleKeys }) {
    const visibleSet = new Set(visibleKeys || []);
    const exportColumns = columns
      .filter((column) => column.exportable !== false)
      .filter((column) => !visibleKeys || visibleSet.has(column.key))
      .map((column) => ({
        key: column.key,
        label: column.exportLabel || column.label,
        type: column.exportType || "string",
        value: column.exportValue || ((row) => row[column.key]),
      }));

    const exportRows = rows.map((row) => Object.fromEntries(
      exportColumns.map((column) => [column.key, column.value(row)])
    ));

    return {
      columns: exportColumns.map(({ key, label, type }) => ({ key, label, type })),
      rows: exportRows,
    };
  }

  async function exportXlsx({ endpoint, button, fileName, sheetName, columns, rows }) {
    if (!rows.length) {
      window.alert("No rows to export with the current filters.");
      return;
    }

    const previousLabel = button?.textContent;
    if (button) {
      button.disabled = true;
      button.textContent = "Exporting...";
    }

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        body: JSON.stringify({
          file_name: fileName,
          sheet_name: sheetName,
          columns,
          rows,
        }),
      });

      if (!response.ok) {
        let message = `Export failed: ${response.status}`;
        try {
          const payload = await response.json();
          message = payload.detail || payload.message || message;
        } catch {
          // Keep the status-based message.
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      window.alert(error.message || "Export failed.");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = previousLabel || "Export Excel";
      }
    }
  }

  window.DashboardExport = {
    buildSheetData,
    exportXlsx,
    safeFilePart,
    timestampSuffix,
  };
})();
