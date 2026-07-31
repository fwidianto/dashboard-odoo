---
name: frontend-golden-screen
description: Preserve and incrementally improve an existing owner-approved frontend screen. Use when changing a UI that already has an approved screenshot, browser-rendered prototype, golden screen, or clearly recorded visual baseline. Do not use for greenfield visual exploration.
---

# Frontend Golden Screen

## Purpose

Deliver one bounded, user-visible frontend change without losing the owner-approved design lineage.

This skill converts the repository's frontend preservation rules into a required working procedure. It does not replace `AGENTS.md`, project status, or owner approval.

## Use this skill when

- an existing screen, route, panel, component, or interaction already has an approved visual baseline;
- the request is to improve, fix, reproduce, or extend that baseline;
- an external reference is being used to improve one named visual property;
- a previous implementation may have drifted from the approved direction.

## Do not use this skill when

- the owner explicitly requests open-ended visual exploration or a new visual architecture;
- no authoritative baseline exists and the task is still in early design discovery;
- the task is backend-only and has no material visible effect.

For greenfield visual exploration, remain in Design and obtain an approved golden screen before implementation.

## Authority order

Use this order when evidence conflicts:

1. latest owner-approved golden-screen image or browser-rendered prototype;
2. owner-approved annotated layout, dimensions, and interaction states;
3. frozen business structure, terminology, interactions, and safety rules;
4. approved component or design-system specification;
5. accepted implementation behavior that does not conflict with higher authority;
6. external references;
7. agent-generated recommendations.

External references are modifiers, not replacements. Use them only for the property explicitly named by the owner.

## Required workflow

### 1. Re-anchor to the approved state

Read only the smallest relevant sources:

- applicable `AGENTS.md` files;
- the current project-status authority;
- the authoritative visual baseline;
- the affected frontend files;
- the current branch and diff.

Do not restart broad repository discovery when these sources are sufficient.

### 2. Produce the frontend visual preflight

Before editing UI code, state:

```text
Frontend visual preflight
- Authoritative baseline:
- Exact route, screen, and viewport:
- Current requested change:
- Elements that must remain unchanged:
- Allowed reference influence:
- Explicit non-scope:
- Required rendered states:
- Owner acceptance path:
- Stop condition:
```

The requested change must be one bounded visible delta. If it cannot be stated clearly, stop before implementation.

### 3. Inspect the current rendered screen

Open the existing implementation at the required route and viewport before making material changes.

Record only differences relevant to the requested change. Do not silently repair, redesign, or normalize unrelated differences.

If the current implementation is materially smaller, less capable, or visually inconsistent with the authoritative baseline, flag that conflict before continuing.

### 4. Implement the smallest approved delta

- Preserve layout, hierarchy, terminology, interactions, and visual identity outside the approved change.
- Modify only the smallest relevant files.
- Do not propagate the design to other routes or screens.
- Do not perform unrelated refactoring, cleanup, dependency upgrades, or architecture changes.
- Do not invent labels, counts, process stages, data relationships, or simplified business structure for visual convenience.
- Add backend or data work only when it is strictly necessary for the requested visible outcome.

### 5. Render early

After the first material implementation pass, render the affected screen and compare it with the baseline before expanding the change.

Stop for owner review when the emerging result:

- changes the approved composition or hierarchy;
- removes or simplifies an approved capability;
- uses an external reference as a replacement design;
- requires a new visual direction;
- materially affects protected areas outside the request.

### 6. Validate the complete requested state

Render every state required by the preflight, including relevant default, selected, expanded, collapsed, loading, empty, or error states.

Perform the smallest relevant technical checks for the changed behavior. Browser rendering is mandatory for visual claims. Unit tests, DOM inspection, accessibility checks, and overflow checks support visual review but do not replace it.

If rendered inspection is unavailable, report the visual status as `UNVERIFIED` or `BLOCKED`. Do not call the frontend package complete.

### 7. Compare and stop

Compare the final rendered result side by side with the authoritative baseline at the required viewport.

Confirm:

- the requested visible delta is present;
- protected areas remain unchanged;
- approved capability and business structure are preserved;
- no unrelated redesign or propagation occurred;
- the stopping condition has been reached.

Do not begin a follow-up improvement unless the active request explicitly authorizes it.

## Required completion report

Lead with what the owner can now see or do.

```text
Outcome:
Start here:
Check first:              # no more than three owner review steps
Expected result:
What stayed unchanged:
Evidence actually performed:
Technical status: COMPLETE | PARTIAL | BLOCKED
Visual status: APPROVED | UNVERIFIED | REJECTED
Limitations or conflicts:
Repository status:
Next bounded recommendation:
```

Only the owner can mark the visual result `APPROVED`. Until then, a technically complete implementation remains visually `UNVERIFIED`.

## Hard stop conditions

Stop and request owner judgment when:

- the authoritative baseline is missing, contradictory, or not recoverable;
- the request conflicts with an approved capability or design decision;
- a proposed improvement would replace rather than modify the approved direction;
- the required result needs unrelated architecture or broad scope expansion;
- the screen cannot be rendered or compared;
- evidence is insufficient to distinguish implementation completion from visual approval.
