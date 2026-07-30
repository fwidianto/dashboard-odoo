# Control Tower Frontend Recovery Roadmap

**Status:** Approved guidance for staged frontend recovery  
**Owner:** Fauzan Widianto  
**Approved:** 2026-07-30  
**Implementation repository:** `fwidianto/dashboard-odoo`  
**Current phase:** Phase 1 — Establish visual evidence

## 1. Purpose

This roadmap governs the recovery and improvement of the Odoo Control Tower frontend after repeated design drift, broad implementation before visual approval, and late visual validation.

The objective is not to restore the earliest design unchanged and not to restart the product from zero.

The objective is to:

> Polish the current Control Tower as the working base, compare it with earlier more mature design evidence and selected external references, approve one browser-rendered golden screen, and only then implement or propagate the design.

This roadmap controls frontend design and implementation order. It does not change business rules, data semantics, SQL, authentication, refresh behavior, or Odoo read-only boundaries.

## 2. Success definition

The recovery succeeds when:

- the Process Map is the clear center of gravity;
- the current product identity and valid interaction behavior are preserved;
- the complete approved business process remains available without invented simplification;
- the left Temuan rail clearly answers what needs attention;
- the right Inspector clearly explains the selected process, case, or finding;
- panel collapse and expansion preserve map balance, readability, and centering;
- one rendered Control Tower composition is explicitly owner-approved;
- production implementation reproduces that approved composition without redesigning it;
- deterministic screenshots prevent later visual drift;
- other pages are not changed until the representative Control Tower screen succeeds.

## 3. Working design position

### 3.1 Current implementation

The current Control Tower implementation is the working technical and visual base unless the owner explicitly selects another starting point.

It may be revised substantially where the evidence shows weak composition, hierarchy, scale, density, or usability.

### 3.2 Earlier design

Earlier Control Tower designs are comparative evidence. They are valuable where they demonstrate more mature:

- composition;
- hierarchy;
- process visibility;
- panel balance;
- visual rhythm;
- enterprise credibility.

They are not automatically the target and do not have to be restored unchanged.

### 3.3 External references

External references are controlled inputs. Each reference must solve one named problem and must be verified against the actual Control Tower before adoption.

Examples:

- process-map dominance;
- progressive disclosure;
- panel behavior;
- stable mainline geometry;
- node selection and contextual inspection;
- enterprise typography and spacing.

A reference does not authorize copying another product’s overall visual identity or replacing approved process terminology and structure.

## 4. Product model to preserve

The frontend must keep three distinct conceptual layers.

### Expected process

The approved business process, legitimate branches, and expected document journey.

### Actual evidence

The Odoo and PostgreSQL documents, relations, statuses, quantities, dates, values, and traceable records showing what happened.

### Findings

The evidence requiring attention:

- Masalah Aktif;
- Perlu Ditinjau;
- Data Belum Lengkap.

The interface must not collapse these layers into one ambiguous diagram.

## 5. Lessons adopted from comparable products

### 5.1 Process map as primary workspace

Process-intelligence products such as Celonis make the process graph the main workspace and place filtering or supporting controls in collapsible areas.

**Control Tower application:** the map receives most of the available canvas. Supporting panels may not overpower it.

### 5.2 Progressive disclosure

Microsoft Process Mining, Celonis, and SAP Signavio do not give every path and detail equal visual prominence at all times.

**Control Tower application:** the complete process remains available, while the default view emphasizes the operational backbone. Selection, focus, filtering, zoom, or inspection reveals additional detail.

### 5.3 Expected process versus actual execution

SAP Signavio conformance views distinguish a planned process from event-derived actual paths and hotspots.

**Control Tower application:** expected process, actual evidence, and findings remain conceptually distinguishable even when shown in one workspace.

### 5.4 Overview versus case path

Mature tools distinguish an overall process map from the exact path taken by one case.

**Control Tower application:**

- default map = end-to-end overview;
- selected case = exact relevant path and evidence;
- Inspector = contextual explanation;
- Temuan = prioritized entry point.

### 5.5 Stable geometry

A mature process workspace keeps the mainline visually stable when filters, panels, or selections change.

**Control Tower application:** collapsing panels must resize and recenter the map without random movement or broken visual hierarchy.

### 5.6 Visual complexity controls do not change data truth

Hiding secondary detail for readability must not imply that the process or evidence does not exist.

**Control Tower application:** progressive disclosure changes presentation only. It must not alter process meaning, counts, relationships, or evidence.

## 6. Tool responsibilities

| Tool | Correct role |
| --- | --- |
| ChatGPT | Product reasoning, diagnosis, decisions, research synthesis, bounded briefs, and owner review guidance |
| Web research | Find proven solutions to a specifically diagnosed design problem |
| Static browser prototype | Primary tool for composition, layout, panel behavior, process-map geometry, and interaction testing |
| Figma | Optional for annotation, comparison boards, and quick layout exploration |
| Codex / Luna | Implement an already approved composition in the real application |
| Terra | Independently review behavior, evidence, regression risk, and visual fidelity |
| Playwright | Deterministic state capture and visual regression after the golden screen is approved |
| GitHub | Store the roadmap, decisions, approved baseline, screenshots, prototype history, and implementation evidence |
| Image generation | Mood and broad inspiration only; never the precision UI authority |
| Storybook | Later option when reusable frontend components and many isolated states justify the overhead |

## 7. Seven-phase recovery plan

No phase may silently continue into the next. Each phase ends with a visible deliverable and an owner gate.

### Phase 1 — Establish visual evidence

**Question:** What do we actually have today?

**Work:**

- capture the current Control Tower at `1920 × 1080`, browser zoom `100%`;
- capture both panels expanded;
- capture left expanded and right collapsed;
- capture left collapsed and right expanded;
- capture both panels collapsed;
- recover the most mature surviving earlier design screenshot or browser render;
- record the exact source, branch, commit, route, and capture conditions.

**Deliverable:** one visual evidence set or comparison board.

**Exit gate:** the owner confirms the current working base and the earlier evidence worth studying.

**Prohibited:** redesign, CSS changes, production edits, new concepts, or page propagation.

### Phase 2 — Comparative design diagnosis

**Question:** Why did the earlier design feel more mature, and why does the current one feel weak?

Assess both against:

- focal point;
- space distribution;
- Process Map scale;
- panel balance;
- hierarchy;
- typography;
- spacing;
- density;
- process completeness;
- interaction clarity;
- unnecessary visual noise.

Use only four classifications:

```text
Keep
Improve
Remove
Missing
```

**Deliverable:** a concise diagnosis with annotated evidence.

**Exit gate:** the owner agrees with the diagnosis before composition work begins.

**Prohibited:** selecting references before the problem they solve is named.

### Phase 3 — Define the UX architecture

**Question:** What must the screen show and do?

Define:

- what the map shows by default;
- how expected process and actual evidence are distinguished;
- what the Temuan rail contains and controls;
- what the Inspector explains;
- what happens when a process node is selected;
- what happens when a finding is selected;
- what happens when one SO, IO, or business case is selected;
- how progressive detail is revealed;
- how panel state affects the map;
- what remains deliberately out of scope.

**Deliverable:** one interaction and information model, independent of visual styling.

**Exit gate:** the owner confirms that the screen behavior makes sense before visual polish.

### Phase 4 — Test two compositions

**Question:** Which composition best supports the approved UX architecture?

Create no more than two `1920 × 1080` low-fidelity alternatives.

Both must preserve:

- current product identity;
- current navigation direction;
- real approved process terminology;
- complete legitimate process availability;
- collapsible Temuan rail;
- collapsible Inspector;
- map-centered workspace behavior.

They may differ in:

- panel widths;
- map orientation;
- lane treatment;
- toolbar position;
- node density;
- secondary-path disclosure;
- typography scale;
- whitespace distribution.

**Deliverable:** two precise wireframes or browser compositions.

**Exit gate:** the owner selects one direction. The rejected direction is archived with the reason and is not repeatedly blended back into the chosen design.

### Phase 5 — Build the interactive golden screen

**Question:** Does the chosen composition work in a browser?

Build an isolated static HTML/CSS/JavaScript prototype using fixture data.

It must demonstrate:

- the complete approved Process Map;
- all four panel states;
- automatic map recentering;
- fit-to-view and readable minimum node size;
- controlled pan or internal scroll when needed;
- node selection;
- selected-path emphasis;
- finding selection;
- Inspector behavior;
- normal, loading, empty, and error states where visually relevant;
- current header and product identity;
- no backend dependency.

**Deliverable:** one browser-rendered golden screen and state screenshots.

**Exit gate:**

```text
Technical prototype: COMPLETE
Visual: APPROVED
```

Without explicit visual approval, production implementation remains blocked.

### Phase 6 — Implement the approved screen

**Question:** Can the real application reproduce the golden screen without regressions?

Scope:

- Control Tower page only;
- preserve current backend contracts and data meaning;
- preserve authentication, company scope, refresh safety, and Odoo read-only behavior;
- no redesign during implementation;
- no unrelated refactoring;
- no other-page propagation.

Luna implements the approved composition. Terra independently reviews behavior and visual fidelity.

**Deliverable:** real Control Tower implementation with side-by-side evidence.

**Exit gate:**

```text
Technical: COMPLETE
Visual: APPROVED
Behavior: APPROVED
```

### Phase 7 — Stabilize and expand

**Question:** Is the approved design reliable enough to become the product standard?

Work:

- store deterministic Playwright screenshots;
- add visual regression checks;
- test real data and important edge cases;
- observe office and desk usage;
- correct material usability problems;
- freeze the shared component and design rules that have proven useful;
- only then propagate approved patterns to Temuan and specialist pages.

**Deliverable:** stable representative frontend and controlled expansion plan.

**Exit gate:** no material trust, behavior, or usability issue blocks the next bounded page.

## 8. Anti-failure controls

1. One phase at a time.
2. One representative screen until approved.
3. Maximum two composition alternatives.
4. Every reference must solve one named problem.
5. No production UI edits before golden-screen approval.
6. No other-page propagation before Control Tower approval.
7. No visual completion claim without rendered evidence.
8. Tests and DOM checks do not substitute for visual review.
9. After two unsuccessful prototype revisions, return to diagnosis instead of generating a random third direction.
10. Preserve rejected concepts and decision reasons to avoid rediscovering them.
11. Do not invent labels, counts, process stages, relationships, or business meaning for visual convenience.
12. Do not reduce real process structure to generic nodes merely to make the layout easier.
13. Do not add tools, component frameworks, or architecture unless they remove a demonstrated blocker.
14. Stop when owner judgment is required.

## 9. Required artifact structure

```text
docs/08_Control_Tower/design/
  README.md
  00_MASTER_DESIGN_SPEC.md
  01_COMPONENT_AND_INTERACTION_SPEC.md
  02_PAGE_TEMPLATES_AND_ACCEPTANCE.md
  03_FRONTEND_RECOVERY_ROADMAP.md
  baseline/
    current/
    earlier-reference/
    approved-golden-screen/
```

Suggested approved-state files:

```text
baseline/approved-golden-screen/
  control-tower-1920x1080-default.png
  control-tower-both-panels-open.png
  control-tower-left-collapsed.png
  control-tower-right-collapsed.png
  control-tower-focus-mode.png
  APPROVAL.md
```

The baseline directory is created when real capture artifacts are available. Empty placeholder image files must not be committed.

## 10. Status and approval language

Every material frontend checkpoint reports separately:

- **Technical:** `COMPLETE`, `PARTIAL`, or `BLOCKED`;
- **Visual:** `APPROVED`, `UNVERIFIED`, or `REJECTED`;
- **Behavior:** `APPROVED`, `UNVERIFIED`, or `REJECTED` when interaction exists.

A frontend package is complete only when all required statuses are approved for the declared boundary.

Only the owner can grant visual or product approval.

## 11. Current starting point

```text
Global lifecycle: Design
Current milestone: Control Tower frontend recovery
Current phase: Phase 1 — Establish visual evidence
Working base: Current Control Tower implementation
Earlier design role: Comparative evidence
Production UI changes: Blocked until golden-screen approval
Other-page propagation: Blocked until Control Tower approval
```

## 12. Immediate next task

Capture and catalogue the current four Control Tower panel states and the best surviving earlier design evidence without changing application files.

Stop after the evidence set is ready for owner review.