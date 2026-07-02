(function setupDashboardTableTools() {
  function safeParse(raw) {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function createColumnController(config) {
    const {
      storageKey,
      columns,
      defaultVisibleKeys,
      button,
      panel,
      list,
      showAllButton,
      resetButton,
      root = document,
      onApply,
    } = config;

    const allowedKeys = new Set(columns.map((column) => column.key));
    const fixedKeys = new Set(columns.filter((column) => column.fixed).map((column) => column.key));
    let visibleKeys = loadVisibleKeys();
    let isOpen = false;

    function loadVisibleKeys() {
      const fallback = new Set(defaultVisibleKeys);
      fixedKeys.forEach((key) => fallback.add(key));
      const raw = storageKey ? localStorage.getItem(storageKey) : null;
      if (!raw) return fallback;
      const parsed = safeParse(raw);
      if (!Array.isArray(parsed)) return fallback;
      const cleaned = parsed.filter((key) => allowedKeys.has(key));
      const loaded = new Set(cleaned.length ? cleaned : defaultVisibleKeys);
      fixedKeys.forEach((key) => loaded.add(key));
      return loaded;
    }

    function persist() {
      if (!storageKey) return;
      localStorage.setItem(storageKey, JSON.stringify([...visibleKeys]));
    }

    function isVisible(key) {
      return visibleKeys.has(key);
    }

    function visibleColumnCount() {
      return columns.filter((column) => isVisible(column.key)).length;
    }

    function visibleColumnKeys() {
      return columns.filter((column) => isVisible(column.key)).map((column) => column.key);
    }

    function syncInputs() {
      if (!list) return;
      list.querySelectorAll("[data-column-toggle]").forEach((input) => {
        const key = input.dataset.columnToggle;
        input.checked = isVisible(key);
      });
    }

    function updateButton() {
      if (!button) return;
      button.textContent = `Columns (${visibleColumnCount()})`;
      button.setAttribute("aria-expanded", String(isOpen));
    }

    function apply() {
      columns.forEach((column) => {
        const visible = isVisible(column.key);
        root.querySelectorAll(`[data-column-key="${column.key}"]`).forEach((element) => {
          element.hidden = !visible;
        });
      });
      syncInputs();
      updateButton();
      if (typeof onApply === "function") onApply({ visibleKeys: visibleColumnKeys(), visibleCount: visibleColumnCount() });
    }

    function setVisibleKeys(keys) {
      visibleKeys = new Set(keys.filter((key) => allowedKeys.has(key)));
      if (!visibleKeys.size) {
        visibleKeys = new Set(defaultVisibleKeys);
      }
      fixedKeys.forEach((key) => visibleKeys.add(key));
      persist();
      apply();
    }

    function showAll() {
      setVisibleKeys(columns.map((column) => column.key));
    }

    function resetDefault() {
      setVisibleKeys(defaultVisibleKeys);
    }

    function renderControls() {
      if (!list) return;
      list.innerHTML = columns.map((column) => `
        <label class="column-toggle ${column.fixed ? "is-fixed" : ""}">
          <input type="checkbox" data-column-toggle="${column.key}" ${isVisible(column.key) ? "checked" : ""} ${column.fixed ? "disabled" : ""}>
          <span>${column.label}</span>
        </label>
      `).join("");
    }

    function open(force) {
      isOpen = typeof force === "boolean" ? force : !isOpen;
      if (panel) panel.hidden = !isOpen;
      updateButton();
    }

    function closeOutside(event) {
      if (!isOpen || !panel || !button) return;
      if (panel.contains(event.target) || button.contains(event.target)) return;
      open(false);
    }

    function handleChange(event) {
      const input = event.target.closest("[data-column-toggle]");
      if (!input) return false;
      const key = input.dataset.columnToggle;
      if (!key || fixedKeys.has(key)) return true;
      if (input.checked) visibleKeys.add(key);
      else visibleKeys.delete(key);
      persist();
      apply();
      return true;
    }

    button?.addEventListener("click", () => open());
    showAllButton?.addEventListener("click", showAll);
    resetButton?.addEventListener("click", resetDefault);
    document.addEventListener("click", closeOutside);
    document.addEventListener("change", handleChange);

    renderControls();
    apply();

    return {
      apply,
      open,
      renderControls,
      resetDefault,
      showAll,
      isVisible,
      visibleColumnCount,
      visibleColumnKeys,
      setVisibleKeys,
      handleChange,
    };
  }

  window.DashboardTableTools = {
    createColumnController,
  };
})();
