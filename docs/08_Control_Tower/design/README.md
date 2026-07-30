# Control Tower UI Unification — Design Specification Index

**Status:** Design direction retained; renewed owner visual acceptance required before further broad UI implementation  
**Approved:** 2026-07-30  
**Implementation repository:** `fwidianto/dashboard-odoo`  
**Applies to:** Office Pilot Readiness and the shared operational dashboard experience

## Purpose

This folder is the canonical implementation-facing design reference for the Odoo Control Tower interface.

It records the approved decision to unify the theme, navigation, interaction language, and shared components across:

- `/dashboard/control-tower`
- `/dashboard/control-tower/temuan`
- `/dashboard/sales-orders`
- `/dashboard/internal-orders`
- `/dashboard/internal-order-rekap`

The Control Tower remains the overview and process-map surface. Temuan remains the findings worklist. The three specialist pages remain investigation and tracking workspaces. They share one product system but do not use one identical layout.

## Reading order

1. [`00_MASTER_DESIGN_SPEC.md`](00_MASTER_DESIGN_SPEC.md)  
   Product identity, visual principles, shared shell, layout model, color, typography, status language, scope, and governance.

2. [`01_COMPONENT_AND_INTERACTION_SPEC.md`](01_COMPONENT_AND_INTERACTION_SPEC.md)  
   Shared components, panel behavior, navigation, tables, filters, inspectors, states, accessibility, motion, and context preservation.

3. [`02_PAGE_TEMPLATES_AND_ACCEPTANCE.md`](02_PAGE_TEMPLATES_AND_ACCEPTANCE.md)  
   Per-page requirements, office and desk modes, implementation sequence, validation matrix, and owner acceptance gates.

## Visual design authority and precedence

For frontend implementation, use this precedence:

1. latest owner-approved golden-screen image or browser-rendered prototype stored as a durable project artifact;
2. owner-approved annotated layout, dimensions, panel states, and interaction notes;
3. frozen business rules, process structure, terminology, data semantics, and safety requirements;
4. this design specification set;
5. accepted implementation behavior that does not conflict with the above;
6. external visual references;
7. model-generated recommendations and implementation preferences.

External references are **modifiers, not replacements**. A reference may improve only a named property such as spacing, density, panel collapse behavior, typography, table treatment, or motion. It must not replace the approved Control Tower identity, process structure, terminology, information hierarchy, or composition without explicit owner approval.

The earliest owner-approved Control Tower design remains the visual lineage until a later golden screen is explicitly approved as its successor. A new session, agent, model, reference, or generated concept does not reset that lineage.

This specification does not authorize changes to validation rules, SQL meaning, document relationships, authentication, company isolation, refresh safety, or Odoo read-only behavior.

## Current baseline gate

The repository does not yet contain one owner-approved golden-screen artifact that can serve as the precise visual comparison target for the next Control Tower implementation pass.

Therefore:

- do not begin another broad Control Tower redesign;
- first recover or recreate the owner-approved visual lineage as one bounded golden screen;
- use real approved process structure and terminology;
- obtain owner approval of the rendered golden screen;
- store the approved artifact durably in this design folder or another explicitly named canonical path;
- only then implement or propagate the design.

Generated images may support mood or composition discussion, but they are not precise UI specifications and must not become the canonical baseline.

## Required Control Tower golden-screen states

The next authoritative Control Tower visual baseline must cover at least:

- viewport: `1920 × 1080`, browser zoom `100%`;
- left Temuan rail expanded and collapsed;
- right Inspector expanded and collapsed;
- both panels collapsed in focus mode;
- the complete approved Process Map centered within the currently available canvas;
- the Process Map proportionally resizing or reflowing when either panel changes state;
- no large unexplained dead space;
- no generic `Fulfilment` replacement for the approved production, stock, procurement, warehouse/QC, and finance structure;
- no invented labels, counts, stages, or relationships.

The Process Map is the primary workspace. The left rail answers what needs attention; the right Inspector explains the current selection. Neither supporting panel may visually overpower the map.

## Core decisions already approved

- One warm-neutral enterprise theme across all five pages.
- White and light warm-gray surfaces, charcoal typography, and restrained amber product accent.
- Red only for confirmed critical problems; green only for current/success; gray for incomplete, unsupported, or inactive states.
- No purple or multi-color decorative dashboard palette.
- One shared navigation shell and freshness language.
- Collapsible left Temuan rail and right Inspector on the Control Tower.
- Inspector collapsed or compact when nothing is selected.
- Focus Process Map mode hides both side panels.
- Shared components and behavior, while preserving page-specific information architecture.
- Tables remain tables; operational worklists must not be converted into card grids.
- Context must be preserved when moving from Control Tower to Temuan and specialist tracking pages.
- Office-screen readability and normal desk investigation are both first-class use cases.

## Required frontend preflight

Before changing UI code, Codex must record:

```text
Frontend visual preflight
- Authoritative baseline:
- Exact screen and viewport:
- Elements that must remain unchanged:
- One visual problem being solved:
- Allowed reference influence:
- Explicit non-scope:
- Required rendered states:
- Owner acceptance path:
- Stop condition:
```

If the authoritative baseline is missing, contradictory, or not recoverable, stop in Design and obtain owner approval before editing production UI.

## Codex operating rule

Before changing UI code, Codex must:

1. read all three specification files and this README;
2. identify the authoritative golden-screen artifact;
3. state the active page or component package;
4. identify user-visible before and after states;
5. list exact non-scope;
6. preserve current data and navigation behavior;
7. render the representative page at the required viewport;
8. compare it side by side with the approved baseline;
9. stop after the authorized bounded package for owner visual review.

Passing unit tests, DOM inspection, accessibility checks, or overflow checks does not equal design acceptance.

Every material frontend package must report both:

- **Technical:** `COMPLETE`, `PARTIAL`, or `BLOCKED`;
- **Visual:** `APPROVED`, `UNVERIFIED`, or `REJECTED`.

A frontend package is complete only when `Technical = COMPLETE` and `Visual = APPROVED`. When screenshot or rendered inspection fails, the visual status must remain `UNVERIFIED` or `BLOCKED` and implementation must stop for owner review rather than continue to the next page.