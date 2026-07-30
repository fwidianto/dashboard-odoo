# Control Tower UI Unification — Design Specification Index

**Status:** Owner-approved design direction; implementation not started  
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

## Authority and precedence

For frontend implementation within this redesign, use the following precedence:

1. frozen business rules, data semantics, and safety requirements;
2. this design specification set;
3. accepted current Control Tower behavior;
4. existing dashboard conventions that do not conflict with this set;
5. model-generated recommendations and implementation preferences.

This specification does not authorize changes to validation rules, SQL meaning, document relationships, authentication, company isolation, refresh safety, or Odoo read-only behavior.

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

## Codex operating rule

Before changing UI code, Codex must:

1. read all three specification files;
2. state the active page or component package;
3. identify user-visible before and after states;
4. list exact non-scope;
5. preserve current data and navigation behavior;
6. stop after the authorized bounded package for owner visual review.

Passing unit tests does not equal design acceptance. Each representative page must be rendered and visually reviewed at the required viewport before it is considered complete.
