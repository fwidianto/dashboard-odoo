# Control Tower Process Map — Approved Design Reference

**Status:** Owner-approved visual direction; implementation contract  
**Scope:** Process Map composition and interaction only  
**Canonical prototype:** `process-map-owner-review-prototype.html`  
**Not production code:** The HTML prototype is a visual and interaction reference, not code to copy blindly.

## Codex read-first rule

Before any Control Tower Process Map planning, implementation, refactor, or visual repair, inspect:

1. `docs/08_Control_Tower/design-references/process-map-owner-review-prototype.html`
2. `docs/08_Control_Tower/design-references/PROCESS_MAP_VISUAL_ELEGANCE_STANDARD.md`
3. the current Process Map implementation, tests, branch diff, and unresolved review notes.

`process-map-primary-spine-v2.html` remains historical context only. The owner-review prototype supersedes it as the visual reference.

Do not redesign the Process Map before comparing the running result against the canonical prototype.

## Approved direction

The Process Map is an executive-level overview, not the complete document relationship graph.

### Default main spine

```text
Estimasi / RKB Kasar
→ Quotation
→ Sales Order
→ Fulfilment
→ Delivery
→ Invoice
→ Payment
```

The default state must remain calm, readable within five seconds, and free from spaghetti lines.

### Fulfilment expansion

Fulfilment has exactly two source choices:

```text
Fulfilment
├── Manufacturing Order
└── From Stock / Internal Order
```

- **Manufacturing Order:** production starts after the Sales Order is active.
- **From Stock / Internal Order:** goods are already available or were produced before the Sales Order became active.

Do not present Kebutuhan Material as a third Fulfilment option.

### Kebutuhan Material

Kebutuhan Material is a supporting flow derived from Sales Order:

```text
Sales Order
→ RKB Pekerjaan
→ Cek Stock
→ ROP
→ Purchase Order
→ Receipt & QC
```

It must be visually separate from the Fulfilment source choice while remaining clearly connected to Sales Order.

### Production journey

The focused journey may expose the production sequence only when one source is selected:

```text
Stock Material
→ Manufacture
→ Finished Goods
```

The complete document graph remains in Tracking.

## Interaction states to preserve

### State 1 — Overview

- show only the main spine;
- no full relationship graph;
- no unnecessary animation;
- badges may show the three approved finding categories only after trusted data is connected.

### State 2 — Fulfilment expanded

- show the two Fulfilment sources;
- show Kebutuhan Material separately as a Sales Order supporting flow;
- keep the main spine visible and readable;
- do not cover or shrink the primary nodes.

### State 3 — Manufacturing Order focused

- highlight the MO source;
- show the Sales Order material flow and production sequence;
- animate only this selected journey;
- dim unrelated paths without removing necessary context.

### State 4 — From Stock / Internal Order focused

- highlight the From Stock / Internal Order source;
- show Internal Order as the production trigger when applicable;
- show the production sequence leading to Finished Goods;
- animate only this selected journey;
- do not imply that every From Stock case requires new production.

## Product boundaries

Preserve:

- Warm Amber visual language;
- clean enterprise surfaces and typography;
- node-first visual hierarchy;
- thin orthogonal connectors;
- small directional arrows;
- restrained motion;
- one active animated journey at a time;
- fixed readable node sizes with horizontal scrolling at narrower viewports.

Do not:

- restore the 25-route always-visible wiring diagram as the default view;
- animate every connector simultaneously;
- use oversized arrowheads, heavy glow, or thick presentation-style lines;
- mix material procurement into the Fulfilment source selector;
- place the complete document graph inside the overview screen;
- invent process relationships or imply mandatory production for every stock case;
- claim production readiness from geometry tests alone.

## Implementation sequence

1. Implement the static visual shell and the four interaction states.
2. Compare browser output against the canonical prototype at 1536 × 1024 and 1024 × 768.
3. Obtain owner visual approval.
4. Connect trusted process counts and three-category badges.
5. Connect node clicks to filtered Temuan.
6. Connect selected documents or findings to a focused journey.

Do not combine these steps into one autonomous implementation run.

## Current bounded task

Implement only the static frontend shell and four visual states in the real Control Tower UI.

Explicit non-scope:

- API or database integration;
- real counts or findings;
- SQL or Odoo changes;
- Tracking implementation;
- broad frontend refactor;
- production hardening;
- commit, push, or PR before owner visual review.

## Acceptance gate

The implementation is ready for owner review only when:

- the main flow is understandable in five seconds;
- the default view has no spaghetti lines;
- Fulfilment shows exactly two sources;
- Kebutuhan Material visibly descends from Sales Order;
- both focused journeys are available;
- only one journey is visually dominant and animated;
- arrow and motion support reading instead of becoming decoration;
- the result remains clean at 1536 px and usable at 1024 px;
- the browser output visibly resembles the canonical prototype;
- no production data, API, SQL, or Odoo behavior was changed.
