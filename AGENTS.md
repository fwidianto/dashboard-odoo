# Codex Working Instructions — dashboard-odoo

## Purpose

This repository implements the shared read-only Odoo-to-PostgreSQL foundation for two related workstreams:

1. **Odoo Analytics Dashboard** — traceability, material and procurement review, data-quality checks, and business-facing dashboards.
2. **Odoo Protocol / Control Tower** — compare actual Odoo evidence with approved process rules, show transaction journeys and exceptions, and support human-reviewed process improvement.

PersonalOS repository `fwidianto/personal-OS` owns durable project direction, approved business decisions, current project status, and the PDS-001 delivery standard. This repository owns code, SQL, tests, runtime configuration, implementation documentation, and technical evidence.

## Read first

Before substantial work, inspect only the smallest relevant set:

1. this file;
2. `README.md`;
3. the relevant document under `docs/`;
4. the affected code, SQL, and tests;
5. the current branch, diff, pull request, and unresolved review notes when applicable.

Do not scan the whole repository unless a blocking dependency requires it.

## Delivery standard

For meaningful work, follow the PersonalOS PDS-001 lifecycle:

`Define → Design → Build → Validate → Release`

Each task must identify:

- one bounded user or business outcome;
- the current global lifecycle stage and local milestone;
- the exact user review path;
- `Must work now`;
- only the `Necessary foundation` required for trustworthiness;
- explicit non-scope and `Later improvements`;
- completion and stopping criteria;
- targeted validation;
- the narrowest justified readiness claim.

Do not combine broad investigation, implementation, redesign, refactoring, production hardening, and the next milestone in one run.

## Incremental production rollout standard

The default delivery model is **production readiness per capability**, not waiting for the entire product to be complete.

Follow the reusable standard in:

`docs/01_Project_Management/INCREMENTAL_PRODUCTION_WORKFLOW.md`

For each release:

1. define the user promise in operational language;
2. select the smallest complete source-to-user vertical slice;
3. state the production boundary and first intended users;
4. build only the foundation required for a trustworthy result;
5. validate source/database, service/API, and browser/user behavior;
6. translate technical output into information the user can understand and act on;
7. deploy at small scale;
8. observe real use;
9. stabilize material trust and usability issues;
10. expand one capability and repeat.

A backend component is supporting progress, not normally a release milestone by itself. Lead milestones with what users can newly see, understand, or do.

Use these capability gates:

- **Gate A — Defined**;
- **Gate B — End-to-end working**;
- **Gate C — Small-scale production ready**;
- **Gate D — User validated**;
- **Gate E — Ready to expand**.

A capability may be production-ready within a narrow boundary while other product areas remain incomplete. Do not imply unsupported breadth.

## Approved baseline and meaningful capability gate

Before implementation, every substantial task must identify:

1. the exact owner-approved product baseline, including the route, file, branch, PR, prototype, or screenshot reference;
2. the user-visible before and after state;
3. the existing implementation that will be reused;
4. whether the work is a capability release or an implementation subtask;
5. whether the proposed result removes, simplifies, or regresses any approved capability.

Do not replace an owner-approved baseline with a simpler implementation unless the owner explicitly approves that regression. The fact that a simpler version is already on `main` does not automatically make it the canonical product baseline.

API filters, connectors, badges, fixtures, tests, SQL helpers, and internal foundations are normally implementation subtasks. Bundle them into the nearest complete user-visible capability rather than presenting each as a separate product release.

A capability release must create a meaningful visible delta: the user should be able to complete or understand a materially improved workflow after the work. If the visible outcome is only one badge, one connector, one filter, or one technical endpoint, treat it as a subtask unless the owner explicitly defines it as the product milestone.

Temporary gates must state their expiry condition. When that condition is met, re-anchor the next task to the canonical product roadmap and baseline before starting more implementation. Do not let a temporary validation branch, simplified shell, or interim workaround silently become the new product direction.

For frontend work, obtain an early screenshot comparison against the approved baseline before completing the full run. Stop for owner review when the emerging result is materially smaller, less capable, or visually inconsistent with the approved baseline.

Default usage-efficient execution pattern:

```text
one Luna implementation run
→ all technical subtasks for one meaningful capability
→ tests and screenshots
→ one Terra independent review of the complete capability
```

Do not invoke independent review repeatedly for micro-changes that belong to the same capability.

## Shared non-negotiable boundaries

- Odoo is **read-only**. Do not call Odoo `create`, `write`, or `unlink`, and do not execute raw SQL against Odoo.
- PostgreSQL may store synced data, derived analytics views, snapshots, validation results, and approved local governance data.
- Default company scope is PT Nobi Putra Angkasa. Do not silently mix companies.
- Preserve native IDs and explicit relations. Text references are secondary evidence and must carry lower confidence.
- Never invent a relationship, quantity allocation, business meaning, metric, owner, or status when the data is ambiguous.
- Represent uncertainty explicitly with terms such as `UNKNOWN`, `DATA_LINKAGE_GAP`, `PARTIAL_MATCH`, `MANUAL_EVIDENCE_REQUIRED`, or the existing project equivalent.
- Cancelled records may remain visible for audit but must not silently contaminate active operational metrics.
- Missing optional data must remain missing; do not manufacture display values.
- Do not expose credentials, tokens, connection strings, confidential data extracts, or production secrets.
- Do not change business rules merely to make tests pass. Report the conflict and stop for owner review.

## Workstream A — Odoo Analytics Dashboard

Primary outcome: help business users understand operational status and required follow-up through trustworthy traceability and simple first-level views.

Preserve these rules:

- business labels should be familiar to users;
- the first view should be simple, with diagnostics available on demand;
- main-table fields and drill-down evidence must have clear boundaries;
- active filters, data freshness, limitations, and review meaning should be visible when relevant;
- Review Signals are operational review helpers, not accounting conclusions or proof that a process is fully correct;
- profitability, revenue, AR, COGS, margin, labor, overhead, and valuation claims remain blocked until their mappings are explicitly approved;
- frontend simplification must not weaken reconciled traceability logic.

Prefer one complete visible workflow over adding more pages or feature breadth.

## Workstream B — Odoo Protocol / Control Tower

Primary outcome: compare approved process expectations with actual Odoo evidence and show where human review is needed.

Preserve these rules:

- a mismatch is a review signal, not an accusation;
- every rule result should expose expected condition, actual evidence, source records, confidence, and traceable document path;
- native relations are stronger than exact-text references;
- multi-IO, conflicting product/UoM, or incomplete lineage must not be resolved through invented allocation;
- manual evidence must never be presented as a confirmed system error;
- failed extraction runs must not replace the latest completed published snapshot;
- Payment remains traceability-only until Accounting approves the interpretation;
- the dashboard must remain read-only until a separate approved write-back or ticket-governance milestone exists;
- frontend Process Map work must not outrun reconciled graph and rule evidence.

Current Control Tower business direction and canonical UI baseline are governed by:

`fwidianto/personal-OS/03_Projects/Odoo_Analytics/PROJECT_STATUS.md`

The repository roadmap under `docs/08_Control_Tower/` is supporting implementation history and planning evidence. It must not override a newer owner-approved baseline or current milestone recorded in PersonalOS.

## Implementation discipline

- Work on a descriptive branch, never directly on `main`.
- Inspect `git status` and the current diff before changing files.
- Change only the smallest relevant files.
- Avoid unrelated refactoring, folder reorganization, dependency upgrades, and generic cleanup.
- Reuse existing architecture, shared components, SQL conventions, and business terminology.
- Add or update tests for changed deterministic behavior.
- Keep implementation and independent review separate.
- Stop when the bounded acceptance criteria pass or when owner judgment is required.

For long or interrupted Codex tasks, use a concise local `.codex/TASK_STATE.md` checkpoint. Record the outcome, decisions, files inspected, validation, blockers, and exact next step. Do not use it as a competing project-status authority, and do not commit it unless explicitly requested.

## Validation

Use the smallest relevant checks first.

General repository checks:

```bash
python -m src.main --validate
python -m pytest
```

Run the application when visual or API behavior changes:

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Control Tower checks, when that workstream is affected:

```bash
python scripts/validate_control_tower.py
```

Use `python scripts/run_control_tower_refresh.py` only when the task explicitly requires a refresh and the correct Odoo/PostgreSQL environment is available. Prefer `--sql-only` when existing snapshots are sufficient. Never claim live validation when only static checks or unit tests ran.

For visual work, tests and builds are insufficient by themselves. Provide a working route or screen and obtain visual review.

## Readiness language

Use the narrowest supported description. Distinguish among:

- implementation written;
- static checks passed;
- unit-tested;
- database-reconciled;
- behaviorally validated;
- visually reviewed;
- user-ready for the stated scenario;
- small-scale production ready for the stated boundary;
- user validated;
- operationally ready;
- production-engineering ready.

Do not call a feature `complete`, `production-ready`, or `validated` without evidence for that exact claim and boundary.

## Required completion report

Every substantial Codex run must finish with:

### A. User-visible outcome

1. **Outcome** — what users can newly see, understand, or do.
2. **Start here** — the exact command, route, screen, document, or artifact.
3. **Check first** — no more than three user review steps.
4. **Expected result** — what each check should show.
5. **User states** — success, empty, loading, error, and not-found behavior when relevant.
6. **Production boundary** — first users, supported scenario, and explicit non-scope.

### B. Technical evidence

1. **Evidence** — tests, database checks, reconciliation, visual proof, or operational proof actually performed.
2. **Implementation** — the smallest relevant schema, API, files, or architecture changed.
3. **Safety** — authentication, company scope, migration, rollback, and read-only evidence when applicable.
4. **Readiness** — the narrowest justified capability gate and label.
5. **Limitations** — incomplete, uncertain, deferred, or unsafe areas.
6. **Repository status** — branch, commit, push, PR, and uncommitted state.
7. **Next task** — one bounded recommendation only.

Lead with the product or business outcome, not a list of changed files.
