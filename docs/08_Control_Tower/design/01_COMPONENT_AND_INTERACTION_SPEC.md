# Control Tower UI Unification — Component and Interaction Specification

**Status:** Owner-approved design direction  
**Companion document:** [`00_MASTER_DESIGN_SPEC.md`](00_MASTER_DESIGN_SPEC.md)

---

## 1. Purpose

This document defines how shared interface elements must look and behave across the Control Tower, Temuan, Sales Orders, Internal Orders, and Order Material Tracking pages.

The goal is not merely identical CSS. The same component must communicate the same meaning, use the same labels, and respond the same way wherever it appears.

---

## 2. Shared component architecture

Codex should implement or consolidate the following shared families before page-by-page styling:

- application shell;
- primary navigation;
- page header;
- freshness indicator;
- operational alert;
- buttons and links;
- tabs and segmented views;
- filters and search;
- status badges;
- findings summary;
- findings rows/cards;
- tables;
- pagination;
- expandable record rows;
- inspector;
- collapsible rails;
- process nodes and connectors;
- empty/loading/error/unsupported states;
- context-return bar;
- toast or operation feedback where necessary.

Do not create page-local copies when the component meaning is shared.

---

## 3. Application shell

### 3.1 Header anatomy

Recommended order:

```text
[Product identity] [Primary navigation] [Freshness] [Display control] [Keluar]
```

At wide widths, navigation remains visible. At compact desktop widths, it may collapse into a controlled overflow or menu, but core routes must remain reachable.

### 3.2 Header behavior

- sticky at the top when content scrolls;
- neutral surface with one bottom divider;
- no large shadow;
- product identity links to Control Tower;
- active navigation uses amber underline and stronger weight;
- freshness is compact but always inspectable;
- `Keluar` is visually separated from page navigation.

### 3.3 Header restrictions

- no large logo illustration;
- no decorative badge next to the product name;
- no duplicate KPI counts;
- no second navigation row unless the page requires local tabs;
- no purple or blue active state.

---

## 4. Page header

### 4.1 Anatomy

```text
[Context return, when applicable]
[Page title]                         [Page-level actions]
[Optional concise description]
```

### 4.2 Rules

- one H1 per page;
- descriptions should explain purpose, not restate the title;
- actions align consistently to the right;
- page header must not become another card unless it contains a meaningful operational state;
- freshness remains in the shared shell or a compact operational alert, not duplicated without reason.

---

## 5. Buttons and links

### 5.1 Button hierarchy

#### Primary

Use only for the main page action.

- amber background;
- strong contrast text;
- no gradient;
- maximum one dominant primary action in a local region.

#### Secondary

- white or subtle surface;
- neutral border;
- charcoal text;
- amber hover/focus border.

#### Tertiary

- text or icon button;
- no enclosing pill unless compact status control requires it.

#### Destructive

- reserved for genuinely destructive actions;
- muted red treatment;
- not expected in read-only Office Pilot workflows.

### 5.2 Labels

Use action-oriented labels:

- `Lihat Temuan`
- `Buka Sales Order`
- `Fokus Process Map`
- `Keluar dari Fokus`
- `Coba Lagi`
- `Tampilkan Filter`

Avoid vague labels such as `Open`, `View`, or `Go` when the destination can be named.

### 5.3 Icon rules

- icons clarify action; they do not replace clear labels for important controls;
- use one consistent stroke family;
- arrows and chevrons must be vector icons, not text glyphs;
- icon size and baseline alignment must be consistent.

---

## 6. Tabs and local navigation

### 6.1 Use cases

Local tabs may switch between:

- Process Map;
- Tracking;
- Temuan;
- summary/detail subviews within specialist pages.

### 6.2 Treatment

- neutral text by default;
- amber underline or subtle soft-amber selected background;
- no rainbow tab colors;
- no oversized rounded pill container around the entire tab group;
- active state must be visible without relying on color alone.

### 6.3 Behavior

- preserve state when switching back where practical;
- keyboard-operable;
- URL or stable state should reflect significant view changes;
- tabs must not silently change data scope.

---

## 7. Freshness indicator

### 7.1 Required information

The component must expose:

- freshness state;
- actual trusted snapshot timestamp;
- age or human-readable relative time;
- latest refresh attempt state when relevant;
- indication that older trusted data is being served after failure.

### 7.2 Compact header treatment

Example structure:

```text
CURRENT
22/07/2026 13:07
```

The state may appear as a small label, but the timestamp remains readable.

### 7.3 Expanded detail

Clicking or focusing the compact indicator may reveal:

- trusted run ID;
- latest attempt time;
- latest attempt result;
- safe failure message;
- read-only status;
- company context.

### 7.4 State treatment

| State | Visual treatment |
|---|---|
| CURRENT | muted green label, neutral surface |
| STALE | amber label, neutral surface |
| CRITICALLY STALE | muted red label, neutral surface |
| REFRESHING | neutral/amber progress treatment |
| FAILED | muted red icon and border, neutral surface |
| UNAVAILABLE | neutral gray icon and explicit message |

Do not display a green CURRENT label next to a failed latest attempt without explaining that the page is serving an older trusted snapshot.

---

## 8. Operational alerts

### 8.1 Use cases

- failed refresh;
- critically stale data;
- unavailable API or database;
- administrator recovery required;
- important read-only limitation.

### 8.2 Anatomy

```text
[Icon] [Short title]
       [One-line explanation]                [Relevant action]
```

### 8.3 Rules

- neutral or very lightly tinted surface;
- semantic color appears in icon, border, or compact label;
- alert must not dominate the entire page unless the page is unusable;
- user-safe wording only;
- no raw stack traces or secrets;
- avoid multiple simultaneous banners for the same underlying problem.

---

## 9. Findings summary

### 9.1 Categories

- Masalah Aktif;
- Perlu Ditinjau;
- Data Belum Lengkap.

### 9.2 Control Tower presentation

Each category shows:

- label;
- authoritative count;
- one concise meaning line when space permits;
- selected state;
- action to open filtered Temuan.

Counts should be prominent but not decorative KPI tiles.

### 9.3 Collapsed rail presentation

When the left rail is collapsed:

- show compact category markers;
- keep counts visible where space allows;
- preserve selected category;
- provide accessible labels and tooltips;
- clicking a category opens the rail and selects it, or directly opens the filtered Temuan according to the final interaction pattern chosen during implementation.

The chosen behavior must be consistent and tested.

---

## 10. Finding row/card

### 10.1 Use cases

- recent priority findings on Control Tower;
- worklist rows on Temuan;
- selected evidence summaries.

### 10.2 Anatomy

```text
[Category/status] [Rule ID] [Severity]
Finding title
Source model · document reference
Evidence summary
[Supported destination / Unsupported]
```

Not every field must be shown at once. Progressive disclosure is preferred.

### 10.3 Visual rules

- white or open-list surface;
- category shown with compact label/icon;
- title receives strongest emphasis;
- metadata remains secondary;
- selected state uses amber border or soft amber background;
- avoid using a full red background for Masalah Aktif;
- list separators may replace individual cards in dense contexts.

### 10.4 Evidence integrity

The finding presentation must retain:

- presentation category;
- original rule ID;
- original status;
- severity;
- confidence when available;
- evidence wording;
- source model and record;
- destination support state.

Do not rewrite review signals into confirmed errors.

---

## 11. Filters and search

### 11.1 Shared filter anatomy

Recommended order:

```text
[Search] [Category] [Process] [Rule] [Severity] [More filters] [Reset]
```

Only show controls supported by the page data contract.

### 11.2 Behavior

- filters update authoritative server-side results where required;
- selected filters remain visible;
- active filter count may be shown compactly;
- reset returns to a defined default, not an arbitrary empty state;
- filters survive navigation back when context preservation applies;
- loading state appears during updates;
- totals update with filters.

### 11.3 Visual rules

- controls share height, typography, borders, and focus treatment;
- avoid a separate colored chip for every active filter;
- use compact removable tokens only when they improve clarity;
- labels must remain understandable without placeholder text.

### 11.4 Search

- search scope must be stated or obvious;
- debounce appropriately;
- do not execute a full browser-side scan of large datasets;
- preserve query on return navigation.

---

## 12. Tables

Operational specialist pages remain table-first.

### 12.1 Required table system

- sticky header;
- consistent header height;
- consistent row density;
- clear sortable columns;
- selected row;
- expandable row where needed;
- authoritative total;
- pagination or controlled incremental loading;
- loading, empty, and error states;
- aligned numeric, quantity, date, and amount values;
- preserved column visibility where already supported.

### 12.2 Density

Recommended row modes:

```text
Compact: 36–40 px
Standard: 44–48 px
Expanded: content-driven detail row
```

Do not use office-display text sizing for every dense specialist table. Keep row identity readable and allow detail expansion.

### 12.3 Alignment

- text: left;
- dates: consistent left or centered treatment;
- numbers and currency: right;
- status: consistent column position;
- identifiers: stable width where practical.

### 12.4 Header behavior

- sorting state visible through icon and text treatment;
- header stays readable during horizontal internal scrolling;
- essential identity columns may be sticky;
- avoid multi-row headers unless the data requires them.

### 12.5 Row expansion

Expanded rows may show:

- document chain;
- evidence;
- fulfilment detail;
- delivery/invoice relationships;
- material or manufacturing links;
- supported actions.

Expansion must not shift the user to a separate visual language.

---

## 13. Pagination

### 13.1 Required elements

- current page;
- total pages or sufficient next/previous context;
- authoritative total records;
- page-size control when useful;
- previous/next controls;
- disabled states.

### 13.2 Behavior

- pagination state preserved on return navigation;
- changing filters resets to a valid page;
- selection should be handled deliberately when moving pages;
- no fake client-side pagination over an incomplete dataset.

---

## 14. Inspector

### 14.1 Purpose

The inspector provides supporting context without navigating away from the current overview or worklist.

### 14.2 Empty state

When nothing is selected:

- Control Tower inspector is collapsed or compact;
- Temuan inspector may show a concise selection prompt;
- do not reserve a large empty white panel filled with repeated placeholder sections.

### 14.3 Selected state anatomy

Recommended order:

1. selected object title;
2. category/status;
3. purpose or process context;
4. evidence summary;
5. source classification;
6. original rule/status/severity/confidence;
7. related documents;
8. limitations;
9. supported destination action.

### 14.4 Behavior

- opens automatically on selection;
- supports manual collapse;
- optional pin state on Control Tower;
- selection remains visually linked to the source row/node;
- clearing selection returns to compact state unless pinned;
- keyboard focus moves sensibly when opened.

### 14.5 Restrictions

- do not display unsupported sections as if data exists;
- omit empty sections or group them under a concise unavailable explanation;
- do not show raw JSON;
- do not repeat the same finding text in multiple inspector sections.

---

## 15. Collapsible rails

### 15.1 Shared behavior

- manual toggle available;
- state transition 220–300 ms;
- center content reflows rather than remaining fixed-width;
- toggle remains reachable in both states;
- state is accessible to keyboard and assistive technology;
- panel state may persist during the current session where appropriate.

### 15.2 Control Tower defaults

#### Left rail

- expanded in default overview;
- collapsed in focus mode;
- restored after focus exit;
- reopened after office idle reset.

#### Right rail

- compact/collapsed when no selection;
- opens on selection;
- collapsed in focus mode;
- cleared and compact after office idle reset.

### 15.3 Compact desktop behavior

At narrower desktop widths, both rails may default collapsed. The process map remains the primary surface.

---

## 16. Process map components

### 16.1 Node anatomy

```text
[Optional process icon]
Process name
Short business reference
Compact finding badge when supported
```

### 16.2 Node states

- default: white surface, neutral border;
- hover/focus: stronger neutral border;
- selected: amber border and soft amber surface;
- active route: restrained amber connector;
- confirmed problem: small red marker or badge;
- review signal: small amber marker or badge;
- unsupported: neutral/dashed treatment with explicit text;
- complete: muted green marker only when evidence supports completion.

### 16.3 Connector rules

- neutral connectors by default;
- animated only for active or selected route;
- selected branch may use amber;
- no simultaneous rainbow routes;
- direction remains clear without animation;
- reduced-motion mode uses static emphasis.

### 16.4 Branches

Fulfilment branch detail must preserve the approved process logic. Visual branch containers should be subtle and use one consistent structure.

Avoid large empty branch containers when branch detail is not shown.

---

## 17. Context-return bar

### 17.1 Use case

Shown when a user enters a page from a finding, process node, or filtered context.

### 17.2 Anatomy

```text
[Kembali ke Temuan — Masalah Aktif]
Sales Order · SO-XXXX · Rule SO-PO-001
```

### 17.3 Behavior

- returns to the originating page and preserved state;
- same-origin only;
- does not rely solely on browser history;
- disappears when the page is opened directly without context.

---

## 18. Loading states

### 18.1 Rules

- show loading close to the region being updated;
- preserve stable page structure;
- do not replace the entire application shell;
- use neutral skeletons or indicators;
- avoid long animated shimmer on office display;
- loading must not look like empty data.

### 18.2 Tables and worklists

Keep headers and filters visible where possible. Show a clear progress state in the results region.

---

## 19. Empty states

### 19.1 Required content

- clear statement of what is empty;
- relationship to current filters;
- reset action when filters caused the empty result;
- no celebratory success claim unless the underlying rule meaning supports it.

Examples:

- `Tidak ada temuan Data Belum Lengkap pada snapshot ini.`
- `Tidak ada hasil untuk filter yang dipilih.`

### 19.2 Restrictions

- no large decorative illustration;
- no fabricated “all clear” state;
- do not display zero when data retrieval failed.

---

## 20. Error and unavailable states

### 20.1 API unavailable

- explicit service-unavailable title;
- no zero counts;
- retry action;
- last trusted state only when safely available.

### 20.2 Database unavailable

- distinct from API route failure;
- no implication that no issues exist;
- administrator-safe diagnostic reference where appropriate.

### 20.3 Refresh failure

- previous trusted snapshot remains visible;
- state and timestamp shown;
- explain that older trusted data is being served;
- recovery action limited to authorized administrators.

### 20.4 Unsupported destination

- explicit `Destination belum tersedia` or equivalent;
- neutral treatment;
- no disabled button that looks actionable without explanation.

---

## 21. Feedback and notifications

Use lightweight feedback for:

- filter update failure;
- copied reference;
- administrator refresh request accepted or rejected;
- restored panel/default state.

Do not use persistent toast stacks on the office display. Important system failures belong in the page state or operational alert.

---

## 22. Keyboard interaction

Minimum expected behavior:

- tab through primary navigation and controls;
- Enter/Space activates buttons and rail toggles;
- Escape closes transient detail where safe;
- table sorting is keyboard-operable;
- expandable rows are keyboard-operable;
- selected finding/node is announced through focus and state;
- focus is not trapped in collapsed panels;
- focus returns logically after closing inspector or focus mode.

---

## 23. Office idle behavior

Idle reset applies to the shared office Control Tower session.

After two minutes of no meaningful interaction:

- return to default Control Tower overview;
- left Temuan rail expanded;
- right Inspector compact/collapsed;
- selected finding and process cleared;
- focus mode exited;
- temporary filters cleared;
- scroll position restored to overview start;
- no automatic refresh triggered;
- trusted freshness state remains visible.

Meaningful interactions include keyboard, pointer, touch, selection, filter, and navigation activity.

Do not apply the same forced reset to normal desk investigation pages unless office/kiosk mode is active.

---

## 24. Shared implementation checklist

Before a shared component is accepted:

- uses master tokens;
- has default, hover, focus, active, disabled, loading, and error states where relevant;
- supports keyboard use;
- does not rely on color alone;
- works at 1920 × 1080 and standard desktop width;
- does not break existing route or data behavior;
- is reused across representative pages;
- has static or browser contract coverage;
- has been visually inspected in context.

---

## 25. Prohibited implementation shortcuts

- copying page-specific CSS with renamed selectors;
- hardcoding status colors inside each page;
- duplicating navigation markup with diverging labels;
- client-side filtering of incomplete server datasets;
- hiding unsupported data without explanation;
- representing all findings as red errors;
- using browser-default typography for controls;
- implementing collapse as `display: none` without accessible state;
- introducing a new frontend framework solely to achieve the redesign;
- replacing functional tables with screenshot-like static mockups.
