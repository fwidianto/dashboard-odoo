# Control Tower UI Unification — Master Design Specification

**Status:** Owner-approved design direction  
**Approval date:** 2026-07-30  
**Implementation status:** Not started under this specification  
**Primary target:** Office Pilot Readiness  
**Product name:** Control Tower Operasional

---

## 1. Design intent

The Control Tower should look and behave like one serious internal operations product, not a collection of separate dashboards and not a generic colorful SaaS template.

The redesign must improve:

- operational readability;
- confidence in data freshness and evidence;
- movement from overview to investigation;
- consistency across pages;
- office-screen presentation;
- desk-based analytical work;
- visual restraint and enterprise credibility.

The product must remain familiar to operational users who already understand conventional reports, while presenting end-to-end process relationships more clearly than a conventional report.

The interface should feel calm when the system is healthy and precise when something requires attention.

---

## 2. Reference character

The design may take inspiration from, but must not copy:

- **SAP Fiori:** disciplined enterprise layout, restrained surfaces, clear transactional hierarchy;
- **Celonis process analytics:** process-first visual emphasis and evidence-led investigation;
- **Microsoft Fluent:** neutral visual hierarchy and controlled semantic color.

The result must retain the existing Control Tower identity rather than becoming a clone of another product.

### Desired character

- warm-neutral;
- structured;
- trustworthy;
- modern but not fashionable for its own sake;
- visually quiet until attention is required;
- information-dense where appropriate;
- generous around overview surfaces;
- precise around tables and evidence.

### Explicitly avoid

- purple or blue product accents;
- rainbow status palettes;
- dark sidebars used only for decoration;
- oversized rounded SaaS cards;
- gradients, glow, glassmorphism, or decorative blur;
- every section enclosed inside another card;
- tiny labels and low-contrast text;
- excessive helper copy;
- charts or KPIs added without operational purpose;
- card grids replacing tables;
- visual effects that compete with the process map.

---

## 3. Product architecture

The unified product consists of five primary pages.

| Page | Route | Page family | Primary purpose |
|---|---|---|---|
| Control Tower | `/dashboard/control-tower` | Overview | Understand current findings and process context |
| Temuan | `/dashboard/control-tower/temuan` | Worklist | Filter, inspect, and open findings |
| Sales Orders | `/dashboard/sales-orders` | Investigation | Trace Sales Order delivery, invoice, fulfilment, and evidence |
| Internal Orders | `/dashboard/internal-orders` | Investigation | Trace IO, MO, SO, fulfilment, and related records |
| Order Material Tracking | `/dashboard/internal-order-rekap` | Tracking | Review RKB, ROP, PO, receipt, invoice, and material relationships |

These pages share one application shell, theme, typography, component system, status language, and navigation behavior.

They do **not** share one identical page layout.

### Page-family rule

- Overview pages prioritize orientation and process visibility.
- Worklist pages prioritize filtering, scanning, and evidence selection.
- Investigation pages prioritize dense tables, document chains, and traceability.
- Tracking pages prioritize operational relationships and status progression.

Do not force every page into a three-column dashboard.

---

## 4. Core design principles

### 4.1 Process before decoration

The process map, findings worklist, document chain, or tracking table must be the dominant object of each page. Navigation, cards, alerts, and metadata support the work rather than compete with it.

### 4.2 One product, appropriate layouts

Consistency comes from the shared shell, typography, spacing, controls, status language, and interaction patterns. It does not require identical page composition.

### 4.3 Neutral by default, semantic when necessary

Most of the interface must use neutral colors. Semantic color is reserved for states that have actual operational meaning.

### 4.4 Evidence before conclusion

The interface must retain original validation status, rule identity, severity, confidence, source evidence, and destination limitations. Presentation categories may simplify scanning but must not replace source meaning.

### 4.5 Progressive disclosure

Show the overview first. Reveal inspector content, evidence, expanded rows, and technical metadata when selected or requested.

### 4.6 Dense where work requires density

Tables and traceability workspaces may be compact. The Control Tower overview should remain more spacious. Density must follow the task.

### 4.7 Honest system states

Loading, empty, unavailable, stale, critically stale, failed, unsupported, and selected states must remain visibly distinct.

### 4.8 Office readability without crippling desk work

The product must support a shared 1920 × 1080 office display and a normal analytical desk workflow. The shared visual system remains the same while density and panel behavior may adapt.

---

## 5. Shared application shell

All five pages must use one shared shell.

### 5.1 Global header

The header contains:

- product identity: `Control Tower Operasional`;
- shared primary navigation;
- compact data freshness indicator;
- optional fullscreen or office-mode control where relevant;
- session/logout control.

The header should not contain redundant page explanations or decorative metrics.

### 5.2 Primary navigation

Approved navigation order:

1. Control Tower
2. Temuan
3. Sales Orders
4. Internal Orders
5. Order Material Tracking

`Keluar` remains separated from page navigation.

Navigation should use plain text tabs or restrained buttons. Avoid a row of unrelated rounded pills.

The active route is shown with:

- stronger text weight;
- an amber underline or bottom border;
- optional subtle warm-neutral background;
- no additional active color.

### 5.3 Page header region

Each page may contain:

- page title;
- one concise purpose line when genuinely useful;
- context-return control when entered from a finding;
- page-level actions;
- compact freshness state.

Do not repeat the product name as the page title when the page identity is already clear.

### 5.4 Content container

- full-width application shell;
- consistent horizontal gutters;
- no arbitrary page-by-page maximum-width changes;
- stable alignment between header, filters, tables, and primary content;
- essential content must not require horizontal page scrolling at 1920 × 1080.

Tables may have controlled internal horizontal scrolling when the data model genuinely requires it, but primary actions and record identity must remain visible.

---

## 6. Visual system

### 6.1 Theme name

**Warm Neutral Enterprise**

The interface uses one product accent and a limited semantic palette.

### 6.2 Color allocation

Approximate visual allocation:

- 88–92% neutral surfaces, text, and borders;
- 5–8% amber product accent;
- 1–3% semantic status color.

A page that looks colorful from a distance has exceeded the intended palette.

### 6.3 Core tokens

Implementation may adjust exact values slightly for contrast, but relationships must remain stable.

```css
--ct-bg: #F5F3EF;
--ct-surface: #FFFFFF;
--ct-surface-subtle: #FAF9F7;
--ct-surface-muted: #F0EFEC;

--ct-text: #1F242B;
--ct-text-secondary: #5F6670;
--ct-text-muted: #7B818A;

--ct-border: #D9D7D2;
--ct-border-strong: #C7C3BC;
--ct-divider: #E7E4DF;

--ct-accent: #B86B12;
--ct-accent-strong: #8F4F08;
--ct-accent-soft: #F7EAD7;

--ct-critical: #B42318;
--ct-critical-soft: #FCEAE8;

--ct-success: #287A4B;
--ct-success-soft: #E8F4EC;

--ct-neutral-status: #68707B;
--ct-neutral-status-soft: #EEF0F2;
```

### 6.4 Semantic use

| Meaning | Treatment |
|---|---|
| Product selection / active navigation | Amber |
| Perlu Ditinjau | Amber |
| Masalah Aktif / confirmed critical problem | Muted red |
| CURRENT / completed / successful refresh | Muted green |
| Data Belum Lengkap | Neutral gray |
| Unsupported / inactive / not started | Neutral gray, optionally dashed |
| Loading | Neutral animated indicator |
| Selected neutral record | Amber border or soft amber background |

### 6.5 Color restrictions

- No purple.
- No blue product accent.
- Do not assign separate colors to every process stage.
- Process nodes are neutral by default.
- Red must never be used as general decoration.
- Green must never imply that an unsupported process area is healthy.
- Large solid red or green panels are prohibited.
- Color must always be paired with text, iconography, border treatment, or shape.

### 6.6 Surfaces and borders

- Primary surfaces are white.
- Page background is warm light gray, not yellow beige.
- Borders are thin and visible.
- Shadows are subtle and reserved for floating or layered objects.
- Prefer dividers and spacing over nested cards.

Recommended radii:

```text
Small controls: 6 px
Standard surfaces: 8 px
Large panels: 10–12 px
Pills: only for compact statuses or tags
```

Do not make every button, tab, table, panel, and container pill-shaped.

---

## 7. Typography

### 7.1 Font stack

```css
font-family: Inter, "Segoe UI", Arial, sans-serif;
```

The application must remain legible when Inter is unavailable. External font delivery must not be required for core operation.

### 7.2 Type scale

| Role | Desktop | Office emphasis |
|---|---:|---:|
| Product/page title | 26–30 px | 28–32 px |
| Primary section title | 20–24 px | 22–26 px |
| Panel title | 16–18 px | 17–19 px |
| Finding/record title | 14–16 px | 16–18 px |
| Body | 13–15 px | 14–16 px |
| Table | 13–14 px | 13–15 px |
| Metadata | 12–13 px | 12–14 px |
| KPI | 28–36 px | 32–40 px |

### 7.3 Typography rules

- Use weight and spacing before adding color.
- Use uppercase only for short section labels.
- Avoid all-uppercase page titles or findings.
- Body line height should normally be 1.4–1.55.
- Table text may use tighter line height while remaining readable.
- Metadata must not become unreadably small.
- Technical identifiers may use a monospaced fallback only when it improves scanning.

---

## 8. Spacing and layout rhythm

### 8.1 Spacing scale

```text
4 px   micro
8 px   compact
12 px  component
16 px  standard
24 px  section
32 px  major separation
48 px  exceptional page separation
```

### 8.2 Layout rules

- Use consistent internal padding across component families.
- Avoid mixing very tight panels with excessively empty canvas.
- The process map should expand to use available central space.
- Inspector content should not reserve a wide blank column when no selection exists.
- Tables should use consistent row density and header height.
- Primary actions must remain within predictable page regions.

### 8.3 Container discipline

Prefer:

- open content regions;
- rails;
- tables;
- lists;
- inspectors;
- canvases;
- a small number of purposeful panels.

Avoid:

- card inside card inside card;
- summary card duplication;
- decorative KPI rows that repeat counts already visible elsewhere;
- empty visual containers used only to fill space.

---

## 9. Shared status language

### 9.1 Findings categories

#### Masalah Aktif

- meaning: confirmed mismatch or issue requiring attention;
- color: muted red;
- treatment: red icon, count, border, or compact label;
- avoid full red cards.

#### Perlu Ditinjau

- meaning: review signal, linkage gap, partial match, manual evidence, or data exception;
- color: amber;
- wording must not imply confirmed error.

#### Data Belum Lengkap

- meaning: current open finding or missing evidence that prevents complete evaluation;
- color: neutral gray;
- must remain distinct from an empty result.

### 9.2 Freshness states

The shared shell and relevant page content must support:

- CURRENT;
- STALE;
- CRITICALLY STALE;
- REFRESHING;
- FAILED;
- UNAVAILABLE.

Every freshness state includes the actual trusted timestamp. Color alone is insufficient.

### 9.3 Empty versus unavailable

- Empty means the request succeeded and returned zero matching records.
- Unavailable means the system could not determine the result.
- Never display zero counts during API or database failure.

### 9.4 Unsupported

Unsupported destinations or process areas use:

- explicit text: `Belum didukung` or equivalent;
- neutral gray treatment;
- optional dashed border;
- no fabricated count;
- no green healthy state.

---

## 10. Control Tower layout model

The Control Tower retains three logical regions:

1. Temuan rail;
2. Process Map workspace;
3. Process Inspector.

Both side regions become collapsible.

### 10.1 Default overview

- left Temuan rail open;
- central Process Map dominant;
- right Inspector collapsed or compact when no selection exists;
- freshness visible in the shell or compact page alert;
- no duplicate bottom KPI row when the same counts already exist in the Temuan rail.

### 10.2 Left Temuan rail

Recommended width:

```text
Expanded: 280–320 px
Collapsed: 44–56 px
```

Expanded content:

- three category counts;
- concise priority findings;
- link to full Temuan page.

Collapsed content:

- category icons or initials;
- counts;
- expand control;
- selected category indication.

### 10.3 Right Inspector

Recommended width:

```text
Expanded: 320–380 px
Compact/collapsed: 44–56 px or absent from layout
```

Behavior:

- compact or collapsed when no selection exists;
- opens automatically after node or finding selection;
- may be manually pinned open;
- may be manually collapsed without clearing selection;
- clearing selection returns it to compact state unless pinned.

### 10.4 Process Map workspace

- receives all released width when a rail collapses;
- shows neutral nodes by default;
- selected node receives amber treatment;
- confirmed problematic node may receive a restrained red indicator;
- connectors remain neutral unless active;
- branch detail appears only when relevant;
- large unused canvas should be minimized.

### 10.5 Focus mode

Focus Process Map mode:

- hides both side rails;
- expands map to available viewport;
- preserves selected route and branch;
- exposes one clear `Keluar dari Fokus` control;
- does not create an unrelated visual theme;
- returns to the previous panel state when exited manually;
- returns to default overview after office idle reset.

---

## 11. Shared navigation and context

### 11.1 Context-preserving flow

A user may move through:

```text
Control Tower
→ Temuan
→ Specialist page
→ Temuan
→ Control Tower
```

Preserve when relevant:

- presentation category;
- process/node;
- original rule;
- severity;
- search/filter state;
- pagination;
- selected finding;
- originating route.

### 11.2 Return controls

Use meaningful labels such as:

- `Kembali ke Temuan — Masalah Aktif`
- `Kembali ke Control Tower — Sales Order`

Avoid a generic `Back` when the destination can be stated.

### 11.3 URL behavior

Use same-origin routes and stable query parameters or application state. Do not invent document destinations. Unsupported destinations must remain unsupported.

---

## 12. Office mode and desk mode

### 12.1 Office mode

Primary target:

- 1920 × 1080;
- 100% browser zoom;
- approximately 2–5 metre viewing distance;
- fullscreen or kiosk-friendly;
- default overview;
- larger text and process map;
- minimal controls;
- two-minute idle reset;
- no essential horizontal scrolling.

### 12.2 Desk mode

- denser filters and tables;
- longer investigation sessions;
- expandable detail;
- keyboard and pointer interaction;
- no forced two-minute reset on specialist pages unless explicitly in kiosk mode.

### 12.3 Mode consistency

Office mode and desk mode use the same colors, typography, components, labels, and information architecture. The difference is density, default panel state, and idle behavior.

---

## 13. Responsive boundary

This specification targets desktop and shared office displays.

Minimum intended desktop width should be documented and tested. Recommended design breakpoints:

```text
Office / wide desktop: 1600 px and above
Standard desktop: 1280–1599 px
Compact desktop: 1024–1279 px
```

At compact desktop widths:

- side panels may default collapsed;
- primary navigation may compress responsibly;
- tables may use controlled internal scrolling;
- core content and primary actions remain visible.

A mobile redesign is explicitly out of scope.

---

## 14. Motion

Motion must explain state changes rather than decorate the page.

Approved timing:

```text
Hover/focus feedback: 120–180 ms
Tabs and controls: 150–220 ms
Panel collapse/expand: 220–300 ms
Inspector reveal: 220–300 ms
Process flow cycle: 2–4 seconds
```

Rules:

- no bouncing;
- no constant pulsing;
- no decorative glow;
- no visible animation restart;
- no animated count changes without purpose;
- active route may animate more strongly than inactive routes;
- `prefers-reduced-motion` must remove nonessential animation.

---

## 15. Accessibility and usability

The redesign must include:

- visible keyboard focus states;
- sufficient contrast;
- status text in addition to color;
- usable pointer and touch targets;
- semantic headings;
- labeled controls;
- keyboard-operable collapsible panels;
- no hover-only critical information;
- readable zoom behavior;
- clear table sorting state;
- clear selected-row state;
- clear loading, empty, and failure announcements where appropriate.

Target minimum interactive size:

```text
Desk controls: approximately 36 px
Office/kiosk primary controls: approximately 40–44 px
```

---

## 16. Scope boundaries

### Included

- unified theme across the five named pages;
- shared application shell and navigation;
- shared visual tokens;
- shared status language;
- collapsible Control Tower rails;
- focus mode behavior;
- shared filters, tables, badges, states, and inspectors;
- context-preserving navigation;
- representative page redesigns;
- office and desk validation.

### Not authorized by this specification

- new business rules;
- SQL semantic changes;
- Odoo write-back;
- automatic record correction;
- new document relationships;
- fabricated counts;
- multi-company redesign;
- mobile redesign;
- cloud or deployment architecture changes;
- a new frontend framework solely for styling;
- broad redesign of unrelated pages;
- removal of useful existing specialist data;
- replacing operational tables with cards.

---

## 17. Implementation principles for Codex

- Reuse the current application architecture unless a concrete blocker exists.
- Prefer shared CSS tokens, shell components, and small reusable JavaScript behavior over a framework rewrite.
- Preserve route behavior, APIs, filters, evidence, totals, and document destinations.
- Implement representative page templates before applying them broadly.
- Do not style each page independently.
- Do not introduce a second design system.
- Do not mix old and new themes within one release boundary.
- Use one editing agent at a time.
- Stop after each bounded visual package for owner review.

### Required implementation packages

1. shared tokens and shell;
2. Control Tower overview and panel behavior;
3. Temuan worklist template;
4. Sales Order specialist template;
5. application of specialist template to Internal Orders and Material Tracking;
6. cross-page state and navigation validation;
7. office-screen validation;
8. consolidated final visual review.

---

## 18. Design acceptance principle

A page is not accepted because tests pass or because every control functions.

A page is accepted only when:

- its information hierarchy is clear;
- it uses the shared visual system;
- it preserves existing workflow;
- it is visually reviewed at its target viewport;
- it does not introduce inconsistent colors or controls;
- it meets the page-specific acceptance criteria;
- the owner approves the representative result.

The final product should look deliberate from a distance and remain useful up close.
