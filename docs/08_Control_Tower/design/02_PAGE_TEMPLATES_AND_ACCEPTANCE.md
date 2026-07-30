# Control Tower UI Unification — Page Templates and Acceptance

**Status:** Owner-approved design direction  
**Companion documents:**

- [`00_MASTER_DESIGN_SPEC.md`](00_MASTER_DESIGN_SPEC.md)
- [`01_COMPONENT_AND_INTERACTION_SPEC.md`](01_COMPONENT_AND_INTERACTION_SPEC.md)

---

## 1. Purpose

This document translates the shared design system into page-specific requirements and defines the release gates for the redesign.

The five pages must feel like one product while retaining the layout best suited to each task.

---

## 2. Shared page-frame requirements

Every page must include:

- shared Control Tower Operasional header;
- identical navigation order and labels;
- consistent active-route treatment;
- compact freshness access;
- consistent page gutter and title region;
- consistent buttons, filters, status badges, loading, empty, failure, and unsupported states;
- consistent same-origin navigation behavior;
- explicit company and read-only boundaries where operationally relevant;
- no unrelated decorative metrics.

Every page must preserve its current business data and route semantics unless a separately approved backend change is required.

---

## 3. Template A — Control Tower overview

**Route:** `/dashboard/control-tower`

### 3.1 Primary user question

> What currently requires attention, where is it in the process, how recent is the evidence, and where should I investigate next?

### 3.2 Default wide layout

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Shared application header                                            │
├───────────────┬──────────────────────────────────────┬───────────────┤
│ Temuan rail   │ Process Map workspace                │ Inspector     │
│ expanded      │ dominant                             │ compact       │
│               │                                      │ until select  │
└───────────────┴──────────────────────────────────────┴───────────────┘
```

Recommended wide proportions when both rails are open:

```text
Left rail: 18–20%
Center workspace: 58–62%
Right inspector: 20–22%
```

When the Inspector is compact, the Process Map receives the released space.

### 3.3 Required content

#### Shared header

- product identity;
- primary navigation;
- freshness state and timestamp;
- office/focus control when relevant;
- logout.

#### Temuan rail

- Masalah Aktif count;
- Perlu Ditinjau count;
- Data Belum Lengkap count;
- concise priority findings;
- link to full Temuan page;
- collapse control.

#### Process workspace

- compact operational alert when needed;
- Process Map / Tracking / Temuan local view control where still useful;
- end-to-end primary spine;
- fulfilment branch detail;
- finding indicators only where supported;
- Focus Process Map control.

#### Inspector

- compact selection prompt when nothing is selected;
- selected node or finding context when selected;
- evidence, rule, limitation, related data, and supported destination;
- collapse/pin behavior.

### 3.4 Remove or avoid

- large blank inspector with repeated empty headings;
- duplicate KPI summary row repeating the Temuan rail counts;
- helper sentences below every heading;
- large refresh banner when a compact operational alert is sufficient;
- oversized empty process canvas;
- colored fill on every node;
- decorative activity feed unless it has real operational value and data.

### 3.5 Panel behavior

#### Left rail

- open by default in office overview;
- manual collapse;
- compact counts remain available when collapsed;
- selected category persists;
- idle reset reopens it.

#### Right inspector

- compact or collapsed by default;
- opens on finding or process selection;
- manual pin/collapse;
- no selection clears content and returns to compact state;
- idle reset closes it.

#### Focus mode

- hides both rails;
- expands map;
- preserves branch and selection;
- one clear exit control;
- no page reload required;
- reduced-motion compatible.

### 3.6 Control Tower acceptance criteria

- Process Map is the visual focal point.
- Essential overview fits at 1920 × 1080 and 100% zoom.
- No essential horizontal page scrolling.
- Left and right rails collapse and expand smoothly.
- Inspector does not consume wide blank space before selection.
- Category counts remain authoritative.
- Clicking a category opens filtered Temuan.
- Supported findings and nodes open the correct inspector context.
- Unsupported destinations are explicit.
- Freshness is visible without dominating the page.
- Masalah Aktif and Perlu Ditinjau remain visually and semantically distinct.
- Two-minute office idle reset returns to the approved default state.
- The page remains usable with reduced motion.

---

## 4. Template B — Temuan worklist

**Route:** `/dashboard/control-tower/temuan`

### 4.1 Primary user question

> Which findings match my current scope, what evidence supports them, and where can I investigate each one?

### 4.2 Preferred layout

Wide desktop:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Shared header                                                        │
├──────────────────────────────────────────────────────────────────────┤
│ Page title + context return + freshness                              │
│ Filter toolbar                                                       │
├───────────────────────────────────────────────┬──────────────────────┤
│ Authoritative findings worklist               │ Evidence inspector   │
│ server-side pagination                        │ selected finding     │
└───────────────────────────────────────────────┴──────────────────────┘
```

The worklist remains dominant. The inspector may collapse at narrower widths.

### 4.3 Required filters

- presentation category;
- process;
- rule;
- severity;
- search where supported;
- clear active-filter state;
- reset to defined default.

### 4.4 Worklist content

Each row must make it easy to scan:

- category;
- practical priority;
- finding title;
- original rule ID;
- source model/document reference;
- status/severity/confidence where available;
- supported destination state.

Avoid repeating the full evidence wording in every dense row. Show it in the selected inspector.

### 4.5 Evidence inspector

Show:

- finding title;
- presentation category;
- original validation status;
- original rule ID;
- severity;
- confidence;
- evidence wording;
- source record;
- related process;
- supported destination action or explicit unsupported state.

### 4.6 Return context

When opened from the Control Tower:

- preserve category and process scope;
- show a meaningful return label;
- returning restores the originating Control Tower state.

When moving to a specialist page:

- preserve finding identity and relevant filter context;
- specialist page displays a context-return bar.

### 4.7 Temuan acceptance criteria

- Category click from Control Tower produces the correct filtered total.
- Total reconciles with Control Tower summary.
- Filtering is server-side for authoritative datasets.
- Pagination is authoritative and preserves context.
- Selected finding remains clearly linked to its row.
- Evidence semantics are not rewritten.
- Data Belum Lengkap with zero current findings shows a genuine empty state.
- API or database failure never appears as zero findings.
- Supported destinations are exact and same-origin.
- Unsupported destination is explicit.
- Worklist and inspector use the shared theme and components.
- Layout is readable at 1920 × 1080 and standard desktop width.

---

## 5. Template C — Specialist investigation page

This is the representative template for Sales Orders and the starting point for Internal Orders.

### 5.1 Shared specialist-page structure

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Shared header                                                        │
├──────────────────────────────────────────────────────────────────────┤
│ Context-return bar, when entered from a finding                      │
│ Page title + compact summary + page actions                          │
│ Filter toolbar                                                       │
├──────────────────────────────────────────────────────────────────────┤
│ Dense operational table / case list                                  │
│ Expandable document chain and evidence                               │
└──────────────────────────────────────────────────────────────────────┘
```

The specialist template is table-first, not card-first.

### 5.2 Shared requirements

- authoritative total;
- sticky header;
- sorting;
- filtering;
- selected/expanded row;
- relevant document chain;
- status and evidence shown with shared semantic language;
- contextual return to Temuan or Control Tower;
- existing export and column controls preserved where useful;
- loading, empty, failure, and unsupported states standardized.

### 5.3 Specialist-page restrictions

- do not remove current useful columns solely to create whitespace;
- do not convert rows into large cards;
- do not make every status a colored badge;
- do not duplicate summary information above and inside the table;
- do not imply a relationship unsupported by existing evidence.

---

## 6. Sales Order Traceability page

**Route:** `/dashboard/sales-orders`

### 6.1 Primary user question

> What is the end-to-end operational and document status of this Sales Order, and what requires investigation?

### 6.2 Required information hierarchy

1. Sales Order identity and commercial context already supported by the page;
2. delivery and invoice status;
3. fulfilment source and manufacturing relationships;
4. finding/review indicators;
5. expanded document chain and evidence;
6. secondary values and metadata.

### 6.3 Required behavior

- filters use the shared toolbar system;
- row selection and expansion use the shared table system;
- findings use the same category labels as Control Tower and Temuan;
- incoming finding context highlights the relevant Sales Order or case;
- return control restores Temuan context;
- current specialist functionality and data remain intact.

### 6.4 Sales Order acceptance criteria

- Shared shell and navigation match Control Tower.
- Existing Sales Order workflow remains functional.
- Table density is appropriate for desk use.
- Selected row and expanded detail are clearly distinguished.
- Finding context is visible without turning all rows red or amber.
- Incoming finding opens the intended record or filtered case.
- Return to Temuan preserves category, filter, and selection where practical.
- No unsupported financial conclusion is introduced.

---

## 7. Internal Order Traceability page

**Route:** `/dashboard/internal-orders`

### 7.1 Primary user question

> How does this Internal Order connect to Manufacturing Orders, Sales Orders, fulfilment, delivery, invoicing, and procurement evidence?

### 7.2 Required hierarchy

1. Internal Order identity;
2. IO → MO → SO relationship;
3. fulfilment and stock context;
4. delivery/invoice/procurement relationships;
5. findings and evidence;
6. secondary metadata.

### 7.3 Required behavior

- reuse the specialist table and detail template;
- preserve current expandable rows and filters;
- highlight incoming finding context;
- use shared status categories and evidence treatment;
- retain exact supported document navigation.

### 7.4 Internal Order acceptance criteria

- Visually belongs to the same application as Sales Orders.
- Does not merely copy Sales Order labels where IO terminology differs.
- Existing IO relationships remain intact.
- Finding context and return navigation work.
- Dense operational data remains readable.
- No fabricated relationship is introduced.

---

## 8. Order Material Tracking page

**Route:** `/dashboard/internal-order-rekap`

### 8.1 Primary user question

> What is the material and procurement progression from requirement through PO, receipt, invoice, and related operational documents?

### 8.2 Required hierarchy

1. tracked material/case identity;
2. RKB and ROP context;
3. PO progression;
4. receipt and invoice progression;
5. related IO/MO/SO context where supported;
6. findings and exceptions.

### 8.3 Required behavior

- preserve its tracking-table identity;
- use shared shell, filters, table, statuses, expansion, and error states;
- incoming material/process finding should apply the correct filter or highlight;
- return context should remain explicit;
- numeric and quantity columns must align consistently.

### 8.4 Material Tracking acceptance criteria

- Same theme and navigation as the other pages.
- Existing material relationships and data remain intact.
- Table remains efficient for operational scanning.
- Numeric, quantity, date, and status columns are consistently aligned.
- Finding entry and return context work.
- No general dashboard card redesign replaces the tracking table.

---

## 9. Office mode specification

### 9.1 Target

- 1920 × 1080;
- 100% zoom;
- fullscreen or kiosk-friendly;
- approximately 2–5 metre viewing distance;
- interactive shared display.

### 9.2 Default office state

- Control Tower route;
- left Temuan rail expanded;
- right Inspector compact;
- no selected finding;
- primary process spine visible;
- freshness visible;
- no temporary filters;
- no focus mode.

### 9.3 Office-mode controls

- Focus Process Map;
- expand/collapse Temuan rail;
- expand/collapse Inspector;
- open filtered Temuan;
- open supported investigation destination;
- exit fullscreen or office mode through a clear, non-prominent control.

### 9.4 Idle reset

After two minutes of inactivity in office mode:

- navigate to default Control Tower overview if on a temporary investigation state approved for reset;
- clear temporary selection and filters;
- expand left rail;
- compact right Inspector;
- exit focus mode;
- restore top scroll position;
- do not start a refresh;
- do not hide stale or failure state.

### 9.5 Office acceptance criteria

- Main counts and process names readable at intended distance.
- No essential clipping.
- No essential horizontal page scroll.
- Panel toggles have sufficiently large targets.
- Animation is calm and stable.
- Freshness is understandable.
- Confirmed problems are distinguishable from review signals.
- Idle reset works exactly as specified.
- Reduced-motion preference works.

Physical distance review remains an owner/external gate and cannot be claimed through automated browser tests alone.

---

## 10. Desk-mode specification

### 10.1 Target

- standard desktop browser;
- analytical user at normal viewing distance;
- filters, tables, expansion, and longer investigation sessions.

### 10.2 Behavior

- side panels may preserve session state;
- no forced idle reset unless explicitly in office/kiosk mode;
- tables may use controlled internal horizontal scrolling;
- denser typography and rows are permitted within the shared scale;
- keyboard and pointer interaction must remain efficient.

---

## 11. Implementation sequence

Codex must implement in this order unless the owner explicitly changes it.

### Package 0 — Baseline and visual inventory

- inspect all five pages at 1920 × 1080 and standard desktop width;
- document existing shared and conflicting styles;
- inventory routes, templates, scripts, CSS, and interactions;
- identify current data and workflow contracts that must remain unchanged;
- produce before screenshots.

**Stop condition:** baseline report and exact file-impact plan.

### Package 1 — Shared tokens and application shell

- introduce canonical design tokens;
- unify header and navigation;
- unify page frame, typography, buttons, tabs, freshness, and base states;
- apply to representative pages without broad page-layout redesign.

**Stop condition:** Control Tower, Temuan, and Sales Orders display the shared shell for owner review.

### Package 2 — Control Tower redesign

- collapsible Temuan rail;
- compact/collapsible Inspector;
- Process Map space and hierarchy improvements;
- focus mode;
- remove duplicate or low-value visual clutter;
- office idle state alignment.

**Stop condition:** default, selected, collapsed, and focus states visually reviewed.

### Package 3 — Temuan redesign

- shared filter toolbar;
- worklist hierarchy;
- inspector hierarchy;
- context preservation;
- shared empty/error/freshness states.

**Stop condition:** all three category entry states and one real selected finding reviewed.

### Package 4 — Sales Order representative specialist template

- apply shared specialist page frame;
- table and expansion standards;
- finding context and return bar;
- preserve workflow and data.

**Stop condition:** owner approves the representative specialist template.

### Package 5 — Apply specialist system

- Internal Orders;
- Order Material Tracking;
- page-specific terminology and data hierarchy preserved.

**Stop condition:** all five pages visually unified and functionally validated.

### Package 6 — Cross-page interaction and office validation

- context-preserving navigation;
- panel behavior;
- office/desk mode;
- loading/empty/error/unsupported states;
- reduced motion;
- 1920 × 1080 browser review.

**Stop condition:** consolidated evidence package prepared.

### Package 7 — Consolidated review and release preparation

- independent technical review;
- owner visual review;
- fix BLOCKER and MUST DO NOW findings;
- update runbook and design documentation;
- prepare release boundary.

---

## 12. Visual QA matrix

Each representative state must be captured or reviewed in-browser.

| Page/state | 1920×1080 | Standard desktop | Interaction check | Required |
|---|---:|---:|---:|---:|
| Control Tower default | Yes | Yes | Yes | Yes |
| Control Tower left collapsed | Yes | Yes | Yes | Yes |
| Control Tower Inspector open | Yes | Yes | Yes | Yes |
| Control Tower focus mode | Yes | Yes | Yes | Yes |
| Control Tower stale/failed | Yes | Yes | Yes | Yes |
| Temuan Masalah Aktif | Yes | Yes | Yes | Yes |
| Temuan Perlu Ditinjau | Yes | Yes | Yes | Yes |
| Temuan empty Data Belum Lengkap | Yes | Yes | Yes | Yes |
| Temuan selected evidence | Yes | Yes | Yes | Yes |
| Sales Orders default table | Optional | Yes | Yes | Yes |
| Sales Orders expanded case | Optional | Yes | Yes | Yes |
| Internal Orders default/expanded | Optional | Yes | Yes | Yes |
| Material Tracking default/expanded | Optional | Yes | Yes | Yes |
| API/database unavailable | Yes | Yes | Yes | Yes |
| Reduced motion | Yes | Yes | Yes | Yes |

When automated screenshot capture is unavailable, deterministic browser inspection and owner live review may substitute temporarily, but visual acceptance remains pending until the owner sees the rendered state.

---

## 13. Functional regression matrix

The redesign must preserve:

- current routes;
- authentication boundary;
- company 3 isolation;
- Odoo read-only behavior;
- freshness contract;
- finding counts and category mapping;
- server-side filtering and pagination;
- process-node mapping;
- supported destination routing;
- unsupported destination honesty;
- table sorting/filtering/expansion;
- exports and column visibility where currently accepted;
- idle reset in office mode;
- health and failure behavior.

Any discovered conflict between visual implementation and these contracts must be classified before proceeding.

---

## 14. Acceptance classification

Use:

- `BLOCKER`
- `MUST DO NOW`
- `IMPORTANT LATER`
- `LOW PRIORITY`

### BLOCKER examples

- wrong data or fabricated relationship;
- cross-company exposure;
- broken authentication;
- Odoo write introduced;
- trusted freshness hidden or falsified;
- core route unusable.

### MUST DO NOW examples

- inconsistent navigation across primary pages;
- unreadable office view;
- critical horizontal clipping;
- category counts do not reconcile;
- collapsed panel cannot be restored;
- inspector hides required evidence;
- review signals visually presented as confirmed errors;
- failure appears as empty data;
- return context is lost in the primary investigation flow.

### IMPORTANT LATER examples

- minor noncritical density refinement;
- additional keyboard shortcuts;
- broader component extraction after visual acceptance;
- secondary page polish outside the five-page scope.

### LOW PRIORITY examples

- subtle shadow/radius preference;
- minor nonessential animation refinement;
- decorative icon replacement with no usability impact.

---

## 15. Definition of design complete

The redesign is design-complete only when:

1. all five pages use the same shell and theme;
2. Control Tower panels behave as specified;
3. the representative Control Tower, Temuan, and Sales Order states are owner-approved;
4. Internal Orders and Material Tracking correctly inherit the specialist system;
5. category, freshness, failure, and unsupported language remain truthful;
6. context preservation works through the primary investigation flow;
7. 1920 × 1080 office validation passes;
8. standard desktop validation passes;
9. no unresolved BLOCKER or MUST DO NOW finding remains;
10. the owner approves the consolidated rendered result.

Functional completion without visual owner approval is not design completion.

---

## 16. Codex final report requirements

After each package, Codex must report:

- roadmap position;
- active package;
- user-visible before and after;
- exact changed files;
- preserved behavior;
- visual states reviewed;
- tests run;
- unresolved findings by classification;
- next stopping point;
- explicit confirmation that no unauthorized backend or business-rule change was made.

Before a release PR, Codex must also provide:

- full changed-file inventory;
- representative screenshots or exact live-review URLs;
- cross-page navigation evidence;
- office and standard desktop evidence;
- accessibility and reduced-motion evidence;
- `git diff --check` result;
- owner-review checklist.
