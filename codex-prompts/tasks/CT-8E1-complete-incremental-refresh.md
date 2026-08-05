# CT-8E1 — Complete the Real Incremental Refresh Vertical Slice

## Approved task contract

- **Big goal:** Deliver a practical, trustworthy, read-only Odoo Control Tower that users can refresh without waiting for a 2–3 hour full extraction.
- **Current milestone:** Phase 3 — Real Refresh Data workflow.
- **One bounded outcome:** Make the existing normal `Refresh Data` action execute the existing incremental foundation end to end: create/resume run → copy trusted snapshot forward → detect changed records → fetch/apply only changed records → reconcile supported parent/child sets → validate → refresh derived Control Tower data → publish atomically → advance watermarks only after success → expose truthful progress/result in the current UI.
- **Current user review path:** After implementation review, the owner will make one harmless Sales Order change in the approved staging Odoo, run Refresh Data, verify that changed evidence appears only after safe publication, then run Refresh Data again with no changes and record the duration.
- **Protected decisions and areas:** Odoo remains read-only; company 3 only; trusted snapshot remains active until success; no partial publication; no invented relationships; normal Refresh Data is incremental; full extraction is maintenance/bootstrap/recovery only; preserve the current approved Control Tower composition and behavior outside refresh.
- **Explicit non-scope:** Frontend redesign, paused frontend-recovery roadmap, scheduling, notifications, broad observability, new worker infrastructure, multi-company expansion, Odoo write-back, Gross Profit, Payment interpretation, later roadmap phases, generic refactoring, speculative scale hardening.
- **Acceptance evidence:** Deterministic fake-Odoo tests, disposable PostgreSQL integration tests, API/frontend regression tests, proof that changed-record refresh does not fetch the full approved dataset, proof that no-change refresh is truthful and fast by construction, proof that failed runs do not move trusted pointers or watermarks, focused rendered/browser smoke only for changed refresh states, and an owner staging runbook. No claim of live runtime readiness until the owner performs the controlled staging test.
- **Stop condition:** One implementation commit is pushed only when the incremental path is locally end-to-end working for changed and no-change scenarios, the normal API no longer invokes the full extractor, trusted data safety tests pass, and the owner staging review path is documented. Otherwise stop with a concrete blocker and do not publish a partial capability.
- **Role:** implementation.

## Task metadata

- **Task ID:** CT-8E1
- **Capability:** Phase 3 real incremental Refresh Data
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `fe8cb2029210420203dfc43920eb7eb979d3398d`
- **Classification:** BLOCKER / MUST DO NOW
- **Assurance:** High for trusted-snapshot publication and watermark changes; standard for the existing UI projection.
- **Expected run:** One substantial implementation run and one consolidated review. Do not split the result into a chain of backend microtasks.

Use `$scope-lock` and `$stabilize-odoo-control-tower` when those local skills are available. They verify this scope; they do not choose another roadmap.

## 1. Why this task exists

The current Control Tower screen and safety UI exist, but the ordinary button still calls the legacy full extraction path:

```text
POST /api/control-tower/refresh
→ REFRESH_COORDINATOR
→ run_refresh_pipeline()
→ ControlTowerRelationExtractor.run()
→ full approved-dataset extraction
```

The owner observed that a full refresh may require approximately 2–3 hours. That is safe as a maintenance operation but unusable as the ordinary daily Refresh Data workflow.

The repository already contains substantial incremental foundations:

- durable refresh states;
- selected-domain contracts;
- trusted snapshot copy-forward;
- watermark-based precision-safe change detection;
- changed-record fetch/apply;
- parent reconciliation queue contracts;
- guarded watermark persistence;
- existing trusted publication and derived SQL rebuild;
- current Refresh Data API and UI.

Do not rebuild those components. Complete and connect them.

## 2. Mandatory preflight

Before editing:

1. Fetch remotes without merging.
2. Confirm the current branch is `feat/control-tower-refresh-center`.
3. Confirm branch HEAD is exactly `fe8cb2029210420203dfc43920eb7eb979d3398d`.
4. Confirm there are no unexpected tracked changes.
5. Preserve these paths without modifying or deleting them:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`
6. Freshly read:
   - repository `AGENTS.md`;
   - `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PROJECT_STATUS.md` from current `main`;
   - `fwidianto/personal-OS/03_Projects/Odoo_Analytics/ROADMAP.md`, Phase 3;
   - `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PILOT_FIRST_DELIVERY_GUARDRAILS.md`;
   - `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md` from `origin/codex-prompts`;
   - this exact task from the prompt commit supplied by ChatGPT.
7. Inspect only the smallest relevant implementation and tests, beginning with:
   - `src/control_tower/orchestration.py`;
   - `src/control_tower/refresh_state.py`;
   - `src/control_tower/change_detection.py`;
   - `src/control_tower/copy_forward.py`;
   - `src/control_tower/fetch_apply.py`;
   - `src/control_tower/reconciliation.py`;
   - `src/control_tower/watermarks.py`;
   - `src/control_tower/refresh.py`;
   - `src/control_tower/router.py`;
   - `src/control_tower/refresh_ui.py`;
   - `src/control_tower/service.py`;
   - current refresh UI JavaScript and focused tests.
8. Write a concise local `.codex/TASK_STATE.md` with the exact existing boundary and the implementation sequence. Do not commit it.

Stop before editing if the required base, authority, or branch state is not satisfied.

## 3. Preserve the existing foundation

The current `RefreshPipelineOrchestrator` already owns the approved path through copy-forward, change detection, and fetch/apply. Extend or compose it; do not duplicate its SQL, domains, precision cursor logic, field contracts, fingerprints, or candidate validation.

The current normal button must stop calling the full extractor. The legacy full extraction may remain callable only through an explicit maintenance/bootstrap/recovery command or existing maintenance script. Do not delete it and do not silently use it as fallback when incremental refresh fails.

## 4. Required end-to-end incremental lifecycle

Implement one coherent normal refresh lifecycle using the existing durable states:

```text
REQUESTED
→ PREPARING
→ DETECTING_CHANGES
→ FETCHING, when changes exist
→ RECONCILING, when supported relationship sets require it
→ VALIDATING
→ REFRESHING_DERIVED_DATA
→ PUBLISHING
→ SUCCEEDED
```

No-change lifecycle:

```text
REQUESTED
→ PREPARING
→ DETECTING_CHANGES
→ VALIDATING
→ SUCCEEDED_NO_CHANGES
```

The implementation may introduce one small continuation/orchestration service if needed, but it must reuse the existing state, copy-forward, detection, fetch/apply, reconciliation, publication, and watermark contracts.

Do not create a second parallel refresh architecture.

## 5. Run creation and normal coordinator

The normal administrator action must:

1. create one durable refresh run for company 3 with the approved domain selection;
2. record the authenticated dashboard username as `requested_by`;
3. execute the incremental lifecycle in the existing background coordinator;
4. reject a second ordinary refresh while one is active;
5. detect a conflicting durable/database refresh, not only another thread in the same process;
6. close PostgreSQL and Odoo clients safely;
7. sanitize user-facing diagnostics;
8. preserve the current trusted snapshot on every failure.

`POST /api/control-tower/refresh` must never invoke `ControlTowerRelationExtractor.run()` or another full approved-dataset fetch.

Keep `run_refresh_pipeline()` or its equivalent clearly maintenance-only. Rename or document it if needed so future code cannot mistake it for the normal path.

## 6. Watermark/bootstrap readiness

Audit whether the currently published trusted snapshot can safely seed missing Phase 3 watermarks.

Normal Refresh Data must not silently trigger a full extraction when a watermark is absent.

When the current complete trusted snapshot contains sufficient approved model rows and `write_date`/ID evidence, implement the smallest explicit one-time bootstrap/adoption operation that:

- uses only the currently published complete trusted snapshot;
- verifies company 3 and approved model coverage;
- derives each model's canonical successful watermark tuple from trusted snapshot evidence;
- binds the watermark to the currently published run;
- writes all required watermarks atomically;
- does not move the published pointer;
- does not contact Odoo;
- is explicit administrator/maintenance behavior, not an automatic ordinary-refresh fallback;
- is idempotent and reports already-ready state truthfully.

A small CLI or explicit admin maintenance endpoint is acceptable. Do not add a normal-screen design expansion.

If safe bootstrap cannot be proven from current trusted evidence, stop and report the exact missing evidence. Do not invent a watermark or start a full refresh automatically.

## 7. Reconciliation boundary

Use the existing domain and `ParentChildContract` registry plus `ReconciliationQueueService` for the smallest supported reconciliation required by changed parent/child sets.

Required behavior:

- changed child records and parent hints enqueue the affected parent/child set;
- reconciliation reads the current complete child set from Odoo using approved fields and read-only access;
- candidate rows for that supported parent set become an exact representation of current Odoo evidence;
- removed/unlinked children are removed from the candidate only when the native relation proves it;
- company scope is enforced;
- queue claims are generation-safe and resumable;
- failure remains retryable without publishing partial data;
- ambiguous or unsupported relationships fail closed or remain explicit incomplete evidence; they are never force-matched.

Do not build a speculative global deletion crawler, broad periodic orphan sweep, or generic event system in this task. Record such work as `IMPORTANT LATER` unless the normal supported path cannot be truthful without it.

## 8. Candidate validation

Before publication, validate at least:

- run company and selected domains;
- base snapshot still equals the current trusted pointer;
- copy-forward, detection, fetch/apply, and required reconciliation evidence is complete;
- candidate contains no cross-company rows;
- fetched rows match normalized approved source evidence;
- unchanged rows remain exact trusted copies under the existing contract;
- supported reconciled parent/child sets are complete;
- stage and progress evidence is internally sufficient for the normal path;
- no known partial stage is treated as complete.

Use existing validators wherever possible. Add only the validation required to prevent a normal failed or incomplete refresh from publishing.

Do not add forensic or cryptographic hardening unrelated to the supported path.

## 9. Derived Control Tower data

After candidate validation, refresh the current Control Tower SQL/read models and findings using the existing approved SQL and business semantics.

Prefer impacted-only derived work when the repository already has a reliable impact contract. Do not invent a broad invalidation framework in this task.

A bounded full PostgreSQL derived/read-model rebuild is acceptable for this first incremental vertical slice when:

- Odoo fetching remains incremental;
- it runs after candidate validation;
- it completes inside the same safe publication boundary or can fail without moving the trusted pointer;
- its measured local/disposable-database cost is recorded;
- it does not change business-rule meaning.

The 2–3 hour Odoo full extraction must not remain hidden behind a fast SQL stage.

## 10. Atomic publication and watermarks

Changed-data success must be atomic from the user's perspective:

1. all required candidate and derived work succeeds;
2. transition through `PUBLISHING`;
3. update the trusted published snapshot pointer;
4. finalize the run as `SUCCEEDED` with truthful timestamps and counts;
5. advance per-model watermarks only for the successfully published run;
6. expose the new trusted timestamp/data.

If any part fails:

- keep the previous trusted pointer;
- keep all successful watermarks unchanged;
- do not expose candidate data as trusted;
- finalize the run in the correct failed/interrupted state with a sanitized diagnostic and failed stage.

Reuse the existing publication SQL paths and watermark store. Adapt legacy `COMPLETED`/`READY_FOR_PUBLISH` helpers carefully rather than bypassing the new state machine. Preserve the maintenance full-refresh path where possible.

### No-change success

For zero detected changes:

- do not replace the trusted snapshot pointer;
- do not rebuild data unnecessarily unless existing validation requires a bounded check;
- finalize as `SUCCEEDED_NO_CHANGES`;
- update only the appropriate watermark `checked_at` evidence after successful no-change finalization;
- present a truthful no-change result and duration.

## 11. Safe retry

Use the existing retry lineage contract for the smallest user-supported retry:

- only `FAILED_TRANSIENT` or `INTERRUPTED` runs are retryable;
- the server selects the latest eligible run; the browser must not choose an arbitrary run ID;
- create a linked retry with the same immutable domain selection and a new run ID;
- preserve trusted data and watermarks;
- do not automatically retry permanent failures;
- do not reuse a partial candidate when the existing contracts require a clean linked retry.

Add a minimal `Coba Lagi` action only when the current UI can truthfully represent a retryable failure without redesign. Otherwise expose the safe API and current plain-language recovery state, and classify the richer retry control as the one remaining owner-review item. The normal changed/no-change path must not be delayed for visual polish.

## 12. API and progress projection

Keep the existing routes and authentication model.

`GET /api/control-tower/refresh` must project the durable incremental run truthfully, including where available:

- active state;
- stage and plain-language stage label;
- current model/process;
- batch/record counts;
- elapsed duration;
- changed/new/missing counts;
- no-change outcome;
- failed stage and sanitized message;
- trusted snapshot timestamp/run ID;
- whether retry or stale recovery is available.

`POST /api/control-tower/refresh` starts the incremental path.

Keep administrator-only start/retry/recovery behavior and authenticated read status.

Do not expose credentials, connection strings, raw stack traces, internal fingerprints, or arbitrary database identifiers beyond the existing necessary run/status evidence.

## 13. Frontend boundary

Preserve the current Control Tower composition, process map, Temuan, Inspector, colors, spacing, and navigation.

Allowed frontend changes are limited to the existing refresh panel and freshness controls needed to represent the real incremental states.

Required behavior:

- progress panel remains minimizable;
- user can continue using the page;
- selected node, Inspector, scroll, route/query state, and Temuan state remain preserved;
- no full-page reload;
- current trusted evidence remains visible while refreshing;
- success reloads evidence once without accumulation;
- no-change result is explicit;
- failure names the failed stage in business language;
- normal Refresh Data reappears only when another safe run may start;
- full refresh is not presented as the normal button.

Because this is not a visual redesign, visual status remains owner-unverified unless a rendered smoke demonstrates only the required refresh states without composition changes.

## 14. Deterministic validation

Use mocked Odoo and newly created disposable PostgreSQL databases. Do not contact real Odoo, office-pilot, or production during automated validation.

At minimum prove:

### A. Changed Sales Order incremental run

Starting from a complete trusted snapshot and ready watermarks:

- one Sales Order and any required dependent line evidence changes;
- detection requests only the changed IDs/required parent sets;
- fetch/apply does not read the full approved model dataset;
- unchanged trusted rows are copied forward;
- candidate and affected derived evidence update;
- trusted pointer changes only after all stages succeed;
- watermarks advance only after publication;
- GET status and UI show success and the new trusted timestamp.

### B. No-change run

- detection finds zero changes;
- no full model fetch occurs;
- trusted pointer remains unchanged;
- status becomes `SUCCEEDED_NO_CHANGES`;
- checked-at evidence advances safely;
- UI reports no changes and a duration.

### C. Failure safety

Inject representative failures:

- after copy-forward/detection;
- during fetch/apply or reconciliation;
- during derived SQL or publication;
- during watermark advancement.

Prove the prior trusted pointer and successful watermarks remain unchanged, candidate data is not served as trusted, and the failed stage is visible.

Watermark advancement and pointer publication must not leave a split-brain success. Use one transaction or a compensating fail-closed design whose safety is proven deterministically.

### D. Concurrency and authorization

- unauthenticated start/retry is rejected;
- non-admin start/retry is rejected;
- a second process/thread cannot start an ordinary refresh while one durable run is active;
- company 3 scope is enforced;
- browser cannot submit an arbitrary run ID;
- errors are sanitized.

### E. Retry and resume

- transient/interrupted run creates one linked retry;
- permanent failure is not retryable;
- completed stages are reused only when existing evidence contracts allow it;
- inconsistent partial evidence requires a clean linked retry and never publishes.

### F. Existing regressions

Run the focused existing suites for:

- refresh state/contracts;
- change detection;
- copy-forward;
- fetch/apply;
- reconciliation;
- watermarks;
- orchestration;
- refresh API/UI;
- evidence reload;
- current Control Tower static/frontend behavior.

Also run:

- Python compilation for changed modules;
- Alembic upgrade/downgrade generation only if a migration is unavoidable;
- `git diff --check`.

Do not spend the run on unrelated full-repository failures that predate this branch. Record them with evidence and continue only when they do not threaten this capability.

## 15. Owner staging review package

Prepare a concise owner-facing staging test section in the existing office-pilot runbook or the final report. Do not create a competing roadmap document.

The owner test must say exactly how to:

1. confirm the application is using the new incremental implementation commit;
2. confirm the current trusted snapshot and watermarks are ready, using the explicit bootstrap/adoption operation only if required;
3. note one existing Sales Order and its current visible evidence;
4. make one harmless staging-only Sales Order change manually in Odoo;
5. press Refresh Data;
6. observe progress and confirm old trusted evidence stays visible until success;
7. confirm the exact SO evidence and trusted timestamp update after success;
8. press Refresh Data again without another Odoo change;
9. confirm `Tidak ada perubahan` / equivalent and record both durations;
10. confirm no Odoo write was performed by the Control Tower.

Never print secrets or require the owner to edit PostgreSQL manually.

## 16. Scope and file discipline

Expected areas may include:

- `src/control_tower/orchestration.py` or one small continuation service;
- `src/control_tower/refresh.py`;
- `src/control_tower/refresh_state.py`;
- `src/control_tower/reconciliation.py`;
- `src/control_tower/watermarks.py`;
- `src/control_tower/router.py`;
- `src/control_tower/refresh_ui.py`;
- `src/control_tower/service.py`;
- the existing refresh-panel JavaScript/HTML only when needed;
- focused tests;
- one existing office-pilot runbook when needed.

A migration is allowed only when the existing schema cannot truthfully support the frozen lifecycle. Keep it minimal, reversible, tested, and explain why existing columns were insufficient.

Do not modify unrelated dashboards, business-rule semantics, design systems, dependencies, or protected backups.

## 17. Acceptance criteria

Pass only when all are true:

- normal Refresh Data uses the incremental pipeline, never full extraction;
- changed and no-change runs reach truthful terminal states;
- changed Odoo records and required parent sets are fetched without a full approved-dataset read;
- trusted snapshot remains active until complete success;
- no partial or failed candidate is published;
- watermarks advance only after successful publication, and no-change checked-at behavior is safe;
- supported parent/child reconciliation is truthful;
- ordinary concurrency is rejected across process/thread boundaries;
- current refresh UI reflects durable stages and preserves page state;
- safe retry is available for the existing supported retry classes or the exact remaining UI-only limitation is plainly reported;
- focused deterministic tests pass;
- no real Odoo/production contact occurred during automated validation;
- owner staging instructions are ready;
- no unrelated work was included.

## 18. Commit and push

After implementation, focused validation, and self-review:

1. create exactly one new implementation commit on `feat/control-tower-refresh-center`;
2. commit message:

   `feat(control-tower): complete incremental refresh path`

3. include a concise body with:
   - `Task: CT-8E1`;
   - base SHA `fe8cb2029210420203dfc43920eb7eb979d3398d`;
   - user-visible outcome;
   - changed files;
   - changed/no-change/failure/concurrency test evidence;
   - confirmation that the normal button no longer calls full extraction;
   - confirmation of zero real Odoo/office-pilot/production access;
4. push normally;
5. do not amend, rebase, merge, force-push, or open a PR;
6. verify local HEAD equals remote branch SHA;
7. leave only the four protected backup paths untracked.

If the complete capability cannot be delivered safely in this run, do not push a misleading partial implementation commit. Preserve a local checkpoint, report the exact blocker and smallest owner decision required, and stop.

## 19. Required final report

Lead with the owner-visible result.

```text
Outcome:
What this means for the owner:
Start here:
Check first: no more than three steps
Expected result:
What stayed unchanged:
Evidence actually performed:
Current status:
- Implemented:
- Technically validated:
- Live staging validated: NO unless actually performed with explicit approval
- Owner approved: NO
- Frontend Technical / Visual / Behavior:
Changed/no-change Odoo-call evidence:
Trusted pointer and watermark safety evidence:
Known limitations and classified findings:
Repository status:
Commit and remote SHA:
Stop condition reached: YES / NO
```

Use the narrow readiness claim:

> Incremental Refresh Data implemented and locally validated; ready for the owner’s controlled staging test, not yet live-runtime validated.

Stop after the push. Do not start a correction, frontend recovery, later roadmap phase, or production-hardening task.