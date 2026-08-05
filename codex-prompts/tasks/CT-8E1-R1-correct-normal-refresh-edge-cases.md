# CT-8E1-R1 — Correct the Normal Incremental Refresh Path

## Approved task

- **Big goal:** Deliver a practical, trustworthy, read-only Odoo Control Tower whose normal Refresh Data workflow is ready for the owner's controlled staging test.
- **Current milestone:** Phase 3 — Real Refresh Data workflow.
- **One bounded outcome:** Correct four normal-path defects found in the independent review of CT-8E1: truthful no-change classification after mandatory watermark-second replay, complete reconciliation across every pending batch, atomic single-active-run creation, and all-or-nothing watermark bootstrap.
- **Current user or operational review path:** After this correction is independently reviewed, the owner will bootstrap watermarks if required, make one harmless staging Sales Order change, run Refresh Data, verify safe publication, then run Refresh Data again without changes and confirm a truthful no-change result and measured durations.
- **Protected decisions and areas:** Odoo remains read-only; company 3 only; normal Refresh Data remains incremental; full extraction remains maintenance/bootstrap/recovery only; the trusted snapshot and successful watermarks remain unchanged on failure; preserve the approved Control Tower composition and current refresh-panel behavior.
- **Explicit non-scope:** Frontend redesign, progress-animation redesign, module/business-area selectors, new Odoo models or fields, scheduling, notifications, broad observability, generic refactoring, folder cleanup, dependency upgrades, performance campaigns, new reconciliation strategies, multi-company work, Odoo write-back, Gross Profit, Payment interpretation, and later roadmap phases.
- **Acceptance evidence:** Focused deterministic fake-Odoo and disposable-PostgreSQL tests for the four defects, existing API/UI regression tests, the full repository test suite, Node static checks where touched, compile/validation checks, and proof that no real Odoo or office-pilot environment was contacted.
- **Stop condition:** Push exactly one correction commit only when all four cases pass and no unrelated behavior or visual composition changed. Otherwise stop with one concrete blocker. Do not begin staging, another correction, refactoring, or the next roadmap task.
- **Role:** correction.

## Task metadata

- **Task ID:** CT-8E1-R1
- **Capability:** Phase 3 — Real Incremental Refresh Data
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `3c4b019044da3f44fcca241444024e699d618a9c`
- **Classification:** BLOCKER / MUST DO NOW
- **Decision:** ONE CORRECTION
- **Expected run:** One bounded correction commit and one consolidated review.

Use `$scope-lock` and `$stabilize-odoo-control-tower` when available. They verify this exact scope and do not choose another roadmap.

## Why this correction is necessary

CT-8E1 connected the incremental architecture and removed the full extractor from the normal button. The implementation is a valuable accepted checkpoint, but four cases inside the frozen acceptance criteria are not yet safely proven:

1. mandatory precision replay can produce manifest rows whose fetched payloads are all unchanged, but the current lifecycle can still publish them as a changed run;
2. reconciliation claims at most one bounded batch and can mark the stage complete while more sets remain pending;
3. active-run detection and durable run creation are separate database operations, so two processes can race;
4. watermark bootstrap can write a partial set before reporting missing model evidence.

Correct only these four cases. Do not reopen CT-8E1 architecture or expand the product.

## Mandatory preflight

Before editing:

1. Fetch remotes without merging.
2. Confirm the current branch is `feat/control-tower-refresh-center`.
3. Confirm branch HEAD is exactly `3c4b019044da3f44fcca241444024e699d618a9c`.
4. Confirm no unexpected tracked changes exist.
5. Preserve without modifying or deleting:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`
   - local `.codex/TASK_STATE.md`
6. Freshly read the current target-branch `AGENTS.md`, PersonalOS `PROJECT_STATUS.md`, `PILOT_FIRST_DELIVERY_GUARDRAILS.md`, the frozen ROADMAP Phase 3, prompt guardrails, `CURRENT.md`, CT-8E1, and this correction task from the exact prompt commit supplied by ChatGPT.
7. Inspect only the smallest affected implementation and tests, beginning with:
   - `src/control_tower/orchestration.py`
   - `src/control_tower/fetch_apply.py`
   - `src/control_tower/reconciliation.py`
   - `src/control_tower/refresh_continuation.py`
   - `src/control_tower/refresh.py`
   - `src/control_tower/refresh_state.py`
   - `src/control_tower/watermarks.py`
   - `scripts/bootstrap_control_tower_watermarks.py`
   - focused CT-8E1 tests.
8. Update the local uncommitted `.codex/TASK_STATE.md` with this exact correction boundary.

Stop before editing if the branch, base, authority, or working tree is not satisfied.

## Correction 1 — Truthful effective no-change after precision replay

The detector must continue replaying the full displayed watermark second. Do not weaken or remove that safety behavior.

Correct the later lifecycle so manifest presence alone does not prove a business-data change.

Required behavior:

- when replay produces manifest rows but fetch/apply and required reconciliation leave the candidate identical to the trusted base for the supported scope, finalize `SUCCEEDED_NO_CHANGES`;
- keep the trusted pointer unchanged;
- do not run the production derived SQL bundle or publish a replacement snapshot for this effective no-change case;
- update only safe no-change `checked_at` watermark evidence after successful finalization;
- report the existing plain-language no-change result and duration;
- when inserted, updated, missing/deleted, or reconciliation mutations exist, continue through changed publication as before;
- do not classify from elapsed time, manifest count alone, or a fabricated progress value.

Use the smallest deterministic source of truth already available. A bounded candidate-versus-base comparison or existing durable mutation evidence is acceptable. Do not build a second change-detection architecture.

Required focused test:

- watermark-second replay returns one or more detected rows;
- fetched payloads and reconciled sets are identical to the trusted snapshot;
- result is `SUCCEEDED_NO_CHANGES`;
- pointer remains unchanged;
- production publication/derived bundle is not invoked;
- checked-at evidence advances safely;
- no full model fetch occurs beyond detected IDs and required parent sets.

## Correction 2 — Reconcile every pending supported set before validation

The bounded claim size may remain. Do not remove batching.

Required behavior:

- continue claiming and executing reconciliation batches until the run has zero pending supported sets and the execution result says the next stage is `VALIDATING`;
- persist truthful progress between batches;
- set `reconciliation_complete = true` only after zero pending sets remain;
- if pending sets remain but a batch makes no forward progress, fail closed as retryable instead of looping forever or publishing;
- do not add a global deletion crawler, orphan sweep, generic event system, or new reconciliation strategy.

Required focused test:

- create more than one claim batch, preferably 101 supported reconciliation sets with the existing limit of 100;
- prove all sets complete before validation/publication;
- inject a later-batch failure and prove the trusted pointer and successful watermarks remain unchanged.

## Correction 3 — Atomic single-active-run creation

Make the database decision `no active run exists → create one REQUESTED run` atomic across processes.

Use the smallest existing PostgreSQL mechanism, such as a transaction-scoped advisory lock or one state-service transaction. Do not add a worker system, scheduler, queue platform, or broad concurrency framework.

Required behavior:

- two simultaneous normal start attempts for company 3 cannot both create active durable runs;
- exactly one receives an accepted run;
- the other receives the existing safe conflict result;
- retry creation obeys the same active-run exclusion where applicable;
- the in-process lock may remain but is not the only protection;
- no stale or terminal run blocks a legitimate new run.

Required focused test:

- use two independent PostgreSQL connections/coordinators and a synchronization barrier or equivalent deterministic race;
- prove only one active run row is created.

## Correction 4 — All-or-nothing watermark bootstrap

Bootstrap must first inspect the complete required approved-model set.

Required behavior:

- collect and validate evidence for every required model before writing any new watermark;
- when any required model lacks trusted evidence, write no new/adopted watermarks in that operation;
- return or raise the exact missing model list;
- CLI exits non-zero and does not print a success message;
- admin endpoint returns the existing safe conflict/error response;
- when all evidence exists, adopt all required missing watermarks atomically;
- remain idempotent when everything is already ready;
- never move the published pointer and never contact Odoo.

Do not broaden the bootstrap UI or add automatic full-refresh fallback.

Required focused tests:

- one required model is missing: no partial adoption and exact failure evidence;
- all required evidence exists: atomic successful adoption;
- second run: truthful already-ready result;
- pointer unchanged and zero Odoo calls in every case.

## Validation

Run the smallest focused tests first, then the established complete validation for the changed capability.

At minimum:

```bash
python -m pytest tests/test_control_tower_refresh_continuation.py tests/test_control_tower_refresh_coordinator.py
python -m pytest
python -m src.main --validate
python -m compileall src scripts tests
node --check src/static/dashboard/control-tower-shell.js
```

Run existing Node static contract tests if the refresh projection or shell contract changes.

Use mocked Odoo and disposable PostgreSQL only. Do not contact real Odoo, staging, office-pilot, or production.

## Commit and stop

Commit exactly once on `feat/control-tower-refresh-center`:

```text
fix(control-tower): close incremental refresh review gaps
```

The commit body must include:

- task `CT-8E1-R1`;
- base SHA `3c4b019044da3f44fcca241444024e699d618a9c`;
- the four corrected normal-path cases;
- focused and full validation actually performed;
- explicit statement that no real Odoo/staging access occurred;
- explicit statement that no frontend redesign, refactor, or roadmap expansion occurred.

Push normally. Do not merge, rebase, amend, or force-push.

Stop after the correction commit is pushed. Do not run the owner staging test and do not begin another task.

## Final report

Lead with what the owner can now safely do.

Report:

1. outcome in plain language;
2. the four corrected normal-use failures;
3. exact changed files;
4. focused and full test results;
5. proof that the normal button remains incremental and full extraction remains maintenance-only;
6. proof that no real Odoo/staging access occurred;
7. branch, commit SHA, remote SHA, and final git status;
8. narrow readiness: implemented and locally validated, awaiting independent review and owner-controlled staging;
9. Technical / Visual / Behavior status, with Visual remaining unchanged or unverified unless a rendered review was actually performed;
10. stop condition reached: YES or NO.
