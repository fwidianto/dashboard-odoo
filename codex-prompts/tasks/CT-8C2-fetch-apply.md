# CT-8C2 — Fetch Full Changed Records and Apply Candidate Deltas

## Task metadata

- **Task ID:** CT-8C2
- **Phase:** 8C-2
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Approved base SHA:** `1d38f4568db457850baeff25cc8ed5a1954af124`
- **Prompt branch:** `codex-prompts`
- **Complexity:** 5/5
- **Expected runtime:** 2.5–5 hours
- **Expected technical completion after PASS:** approximately 81–82%
- **Primary risks:** payload contracts, missing-at-fetch rows, deterministic upserts, transactional candidate safety, idempotent resume

Use `$stabilize-odoo-control-tower`.

This is one substantial but bounded backend phase.

## Objective

Continue the approved refresh lifecycle from:

```text
FETCHING
```

to the next safe durable boundary after:

1. reading the completed change manifest;
2. fetching complete approved snapshot payloads for detected records using read-only Odoo calls;
3. normalizing and validating those payloads;
4. durably staging fetch evidence;
5. applying deterministic inserts/updates/unchanged results to the copied candidate snapshot;
6. preserving truthful evidence for records missing at fetch time;
7. transitioning the run to:

```text
RECONCILING
```

Stop before any parent or hard-deletion reconciliation executes.

## Absolute restrictions

Do not:

- contact real Odoo during implementation or tests;
- contact production or office-pilot;
- call Odoo create, write, unlink, actions, workflows, server actions, or arbitrary unapproved methods;
- publish a candidate;
- advance watermarks;
- regenerate findings;
- refresh materialized views or derived checks;
- execute parent reconciliation;
- execute hard-deletion reconciliation;
- build background workers, APIs, or frontend UI;
- modify protected backup paths;
- amend, rebase, merge, or force-push;
- open a pull request.

Use mocked Odoo and newly created disposable PostgreSQL databases only.

## 1. Repository and branch safety

Before editing:

1. Fetch remotes.
2. Check out `feat/control-tower-refresh-center`.
3. Confirm HEAD is exactly:
   `1d38f4568db457850baeff25cc8ed5a1954af124`
4. Confirm upstream is `origin/feat/control-tower-refresh-center`.
5. Confirm the working tree contains only the four protected untracked paths:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`
6. Confirm `src/control_tower/refresh.py` is unchanged.
7. Read repository instructions and relevant AGENTS files.
8. Inspect the complete approved Phase 8 implementation before designing.

If branch, SHA, or working-tree conditions differ, stop and report rather than rebasing or repairing automatically.

## 2. Required discovery

Inspect at minimum:

- `src/control_tower/orchestration.py`
- `src/control_tower/change_detection.py`
- `src/control_tower/contracts.py`
- `src/control_tower/relation_extractor.py`
- `src/control_tower/copy_forward.py`
- `src/control_tower/progress.py`
- `src/control_tower/refresh_state.py`
- `src/control_tower/schema_guard.py`
- `src/control_tower/watermarks.py`
- `src/control_tower/refresh.py`
- migrations 001, 002, and 003
- `MODEL_SPECS`, domain registry, and approved field declarations
- the exact schema and keys of `ct_native_record_snapshot`
- the exact schema and lifecycle of `ct_change_manifest`
- Odoo client read batching/search_read behavior
- all Phase 8 tests

Determine from repository evidence:

- the canonical normalization used for full snapshot payloads;
- the exact candidate snapshot upsert key;
- whether existing schema can durably hold fetch/apply evidence;
- whether migration 004 is genuinely required;
- the existing allowed state transition from `FETCHING` to `RECONCILING`.

Do not invent parallel payload formats when the extractor already defines one.

## 3. Approved source scope

Fetch only records present in the completed `ct_change_manifest` for the run.

Use only models already approved by `DOMAIN_REGISTRY` and `MODEL_SPECS`:

- `sale.order`
- `sale.order.line`
- `approval.request`
- `approval.product.line`
- `mrp.production`
- `purchase.order`
- `purchase.order.line`
- `stock.picking`
- `stock.move`
- `account.move`
- `account.move.line`
- `account.partial.reconcile`

Do not add models from configuration files merely because they exist.

Shared models must execute once while preserving all selected-domain metadata.

## 4. Full payload contract

For each approved model, derive the complete snapshot field set from the existing approved `MODEL_SPECS` and extractor contract.

Requirements:

- fetch only fields already approved for Control Tower snapshot use;
- include `id`, `write_date`, and `company_id` where required;
- include approved relations and business fields needed by the existing relation extractor and later findings;
- do not fetch all Odoo fields;
- validate every requested field against explicit model contracts;
- normalize Odoo many2one and relational values using the existing snapshot representation;
- parse Odoo `write_date` using the approved transport parser;
- keep internal timestamps timezone-aware UTC;
- reject malformed, missing, unexpected, or wrong-company payloads;
- reject duplicate conflicting records;
- canonicalize JSON deterministically.

Do not store display names as authoritative identities.

## 5. Read-only Odoo fetching

Use an injected read-only Odoo client.

Allowed methods should remain bounded read operations only, preferably `search_read` through the established client abstraction.

For each model:

1. Read manifest record IDs in deterministic order.
2. Split into bounded ID batches.
3. Query with:
   - company scope where supported;
   - `id in [...]`;
   - approved full payload fields only;
   - deterministic `id asc` ordering;
   - an explicit bounded limit at least equal to the batch size;
   - no offset.
4. Validate exact returned IDs and payloads.
5. Never perform a full-history query.

Prove no call path can invoke create/write/unlink/action methods.

## 6. Source drift after detection

The source may change between detection and full fetch.

Handle these cases explicitly:

### Returned record has a newer `write_date`

- accept the newer source version only when it remains in the intended company scope;
- persist the actual fetched `write_date` and payload fingerprint;
- do not rewrite the original detection manifest evidence;
- classify the fetch as source drift after detection;
- keep deterministic audit evidence.

### Returned record has an older `write_date`

- fail closed as inconsistent source evidence.

### Record is absent from the company-scoped fetch

Treat it as `MISSING_AT_FETCH`, not as a silently successful deletion.

Required behavior:

- persist durable missing evidence;
- do not fabricate a payload;
- do not silently retain a status of FETCHED/APPLIED;
- do not physically remove the candidate row in this phase unless an already-approved repository contract explicitly proves direct removal is safe;
- prefer leaving the copied baseline row for the reconciliation phase;
- include the model/record in later reconciliation requirements;
- do not broaden into unrelated companies to discover where it moved.

The next phase owns parent/hard-deletion reconciliation.

## 7. Durable fetch/apply evidence

Do not put full fetched payloads only in progress JSON.

Implement the smallest audit-safe durable persistence contract needed for:

- run ID;
- company ID;
- model;
- record ID;
- detection source timestamp;
- fetched source timestamp;
- fetch status;
- apply status;
- canonical payload or canonical payload reference;
- payload SHA-256 fingerprint;
- source-drift marker;
- missing-at-fetch marker;
- deterministic sequence;
- fetch/apply timestamps;
- error evidence where applicable.

Prefer a dedicated durable table when required for crash-safe resume.

If schema changes are required:

- add migration 004;
- do not rewrite committed migrations 001–003;
- use PostgreSQL-safe types;
- use deterministic names;
- enforce run/company integrity at the database boundary;
- use audit-safe foreign keys and `ON DELETE RESTRICT`;
- prevent duplicate `(run, model, record)` evidence;
- make downgrade remove only migration-004 objects;
- update schema guards without breaking services that require only earlier revisions.

If no migration is required, explain precisely how existing durable structures safely support payload resume and exact evidence validation.

## 8. Fetch service

Implement a focused service, not a second orchestrator.

Suggested responsibility:

```text
completed manifest
→ bounded full-record fetch
→ strict normalization
→ durable fetch evidence
```

Required validation before fetching:

- Phase 8 schema readiness;
- run exists and belongs to company;
- run state is `FETCHING`;
- selected domains match immutable run inputs;
- copy-forward is complete;
- change detection is complete;
- detection header is COMPLETE;
- manifest fingerprint/count/model evidence is valid;
- candidate base still matches the trusted pointer;
- candidate snapshot exists;
- no prior inconsistent fetch/apply evidence exists.

Partial fetch evidence must fail closed or resume only from a proven safe model/batch boundary.

Do not silently delete partial evidence to restart.

## 9. Candidate delta application

Apply only successfully fetched current records.

Use the existing candidate snapshot shape and canonical extractor serialization.

For each fetched record, classify:

- `INSERTED`: no candidate row existed;
- `UPDATED`: candidate row existed and canonical source content changed;
- `UNCHANGED`: candidate row already equals the canonical fetched content;
- `MISSING_AT_FETCH`: no payload returned; defer physical removal/reconciliation.

Requirements:

- deterministic key and ordering;
- transactionally safe per model or proven safe stage boundary;
- no source snapshot mutation;
- no published snapshot mutation;
- no watermark movement;
- no relation/finding regeneration yet;
- exact before/after counts;
- idempotent repeated application;
- payload fingerprint verification before write;
- no unrelated candidate rows touched;
- missing rows remain explicit and unresolved rather than silently disappearing.

A repeated call after successful apply must not rewrite unchanged rows or contact Odoo when durable fetched evidence is already complete and valid.

## 10. State boundary

Extend the refresh lifecycle only through:

```text
FETCHING
→ RECONCILING
```

Transition to `RECONCILING` only after:

- all manifest models are fetch-complete;
- every manifest row has durable fetch evidence;
- every fetched payload is applied or classified unchanged;
- every missing row is durably classified for reconciliation;
- total/model counts reconcile with PostgreSQL;
- completion fingerprints are persisted;
- no partial model remains.

Do not execute reconciliation.

Runs already at `RECONCILING` may return an exact idempotent boundary result after validating durable evidence.

The no-change `VALIDATING` path must remain unchanged and must not contact Odoo.

## 11. Orchestrator integration

Integrate the new service into the existing `RefreshPipelineOrchestrator` without duplicating fetch/apply logic.

Expected behavior:

- `REQUESTED/PREPARING/DETECTING_CHANGES`: existing Phase 8C-1 behavior continues;
- detection with rows reaches `FETCHING`, then the new stage may continue to `RECONCILING` in the same public orchestration call when safe;
- existing valid `FETCHING`: resume fetch/apply;
- existing valid completed fetch/apply: transition or return `RECONCILING` without Odoo calls;
- `VALIDATING`: retain idempotent no-change boundary behavior;
- partial/inconsistent fetch evidence: fail closed and require a linked retry;
- `RECONCILING`: idempotent return with no Odoo call.

Do not add an outer advisory lock around services that already own their locks.

## 12. Locking and concurrency

Use the established global refresh lock ordering.

Required guarantees:

- no nested lock deadlock;
- no lock inversion with copy-forward or detection;
- same-run concurrent fetch/apply cannot create duplicate evidence or conflicting candidate writes;
- one authoritative attempt wins;
- a losing caller receives a truthful contention/fail-closed result;
- no stale progress overwrites completed evidence;
- no transition to `RECONCILING` before all durable evidence is complete.

## 13. Completion fingerprints and reuse

Persist deterministic completion evidence covering at least:

- contract version;
- company;
- selected domains and resolved models;
- approved full field sets;
- manifest completion fingerprint used as input;
- batch size;
- per-model fetched/missing/applied counts;
- payload fingerprints and statuses;
- candidate run/base snapshot identity;
- source-drift classifications;
- completion timestamps.

Completed reuse must recompute and validate actual durable rows, not trust counts alone.

Reject:

- changed payload rows;
- missing or extra evidence;
- changed field contract;
- changed batch size where contractually relevant;
- changed manifest input;
- stale base snapshot;
- changed company/domains;
- forged progress completion;
- candidate snapshot rows that no longer match recorded application evidence.

## 14. Progress and result contracts

Add truthful fetch/apply progress without overwriting copy-forward, detection, or orchestration evidence.

Track at minimum:

- models planned/completed;
- current model;
- manifest rows planned;
- records requested;
- records fetched;
- missing-at-fetch;
- source-drift rows;
- inserted;
- updated;
- unchanged;
- applied total;
- batches completed;
- started/finished timestamps;
- elapsed duration from timestamps;
- completion marker/fingerprint;
- next required stage `RECONCILING`.

Do not fabricate percentage completion.

Do not label overlap candidates as proven changes before comparison.

Return a compact deterministic summary, not full payloads.

## 15. Failure injection

Add deterministic failure tests at:

- before first fetch;
- midway through a model batch sequence;
- after payload persistence before candidate apply;
- midway through candidate apply;
- after all applies before completion evidence;
- after completion evidence before state transition;
- during final progress persistence.

Verify:

- no false completion;
- partial evidence remains audit-visible;
- safe resume occurs only from proven boundaries;
- unsafe partial state requires linked retry;
- no source/published snapshot or watermark corruption;
- successfully completed fetch evidence prevents unnecessary repeated Odoo calls.

## 16. Mocked Odoo tests

Use a strict stateful fake supporting approved full payloads.

Cover:

- all 12 approved models;
- exact field requests;
- bounded ID batches;
- unordered response normalization;
- wrong-company response rejection;
- missing required fields;
- unexpected fields;
- malformed relations;
- duplicate conflicting rows;
- newer-at-fetch source drift;
- older-at-fetch rejection;
- missing-at-fetch classification;
- no full-history reads;
- no offset;
- no write-capable calls;
- NoCall reuse after durable fetch completion.

## 17. PostgreSQL tests

Use only newly created disposable PostgreSQL databases.

Cover:

- migration 004 upgrade/downgrade when added;
- database constraints and company isolation;
- fetch evidence persistence;
- deterministic payload fingerprints;
- insert/update/unchanged classifications;
- missing-at-fetch evidence;
- source drift;
- idempotent completed reuse;
- partial fetch handling;
- partial apply handling;
- same-run concurrency;
- stale pointer/base;
- changed domains/company;
- forged completion progress;
- candidate-row tampering detection;
- transition to `RECONCILING`;
- `VALIDATING` no-change path unchanged;
- source snapshot unchanged;
- published pointer unchanged;
- watermarks unchanged;
- historical evidence retained.

Do not use SQLite to claim PostgreSQL compatibility.

## 18. Real Odoo policy for this run

Do not contact real Odoo in this implementation run.

The next independent validation run will test bounded real Odoo payload compatibility after GitHub review.

## 19. Full validation

Run:

- new fetch/apply unit tests;
- new fetch/apply PostgreSQL tests;
- orchestration tests;
- change-detection tests;
- copy-forward tests;
- all Phase 8 PostgreSQL suites;
- full focused Control Tower Python suite;
- frontend static regression;
- Python compilation;
- blocked-access imports;
- Alembic offline upgrade and downgrade;
- `git diff --check`.

Required:

- zero failures;
- zero PostgreSQL-related skips;
- no real Odoo contact;
- no office-pilot access;
- no repository artifacts;
- disposable databases removed;
- `CT_TEST_POSTGRES_URL` unset afterward.

## 20. Self-review

Before committing:

1. Inspect the complete diff.
2. Confirm no duplicate detector/extractor/orchestrator logic.
3. Verify all Odoo calls are read-only and bounded.
4. Verify candidate writes affect only detected/fetched IDs.
5. Verify missing records are not silently deleted.
6. Verify no reconciliation, publication, or watermark movement entered the diff.
7. Verify lock ordering and idempotency.
8. Verify migration ownership and downgrade if migration 004 exists.
9. Run `git diff --check` again.

## 21. Commit and push

After implementation, validation, and self-review:

1. Commit the exact Phase 8C-2 files in one commit.
2. Commit message:

   `feat(control-tower): fetch and apply detected records`

3. Include a concise commit body containing:
   - `Task: CT-8C2`
   - `Approved base: 1d38f4568db457850baeff25cc8ed5a1954af124`
   - files changed;
   - tests and results;
   - whether migration 004 was added;
   - known limitations;
   - confirmation no real Odoo or office-pilot was contacted;
   - confirmation no publication or watermark advancement occurred.
4. Push normally to `origin/feat/control-tower-refresh-center`.
5. Do not force-push.
6. Do not open a PR.
7. Verify local HEAD equals remote branch SHA.
8. Verify final working tree contains only the four protected backup paths.

## 22. Final report

Return a concise final report containing:

1. implementation verdict;
2. commit SHA;
3. pushed remote SHA;
4. exact changed files;
5. migration decision;
6. fetch/apply architecture;
7. missing-at-fetch policy;
8. state transition result;
9. tests and exact totals;
10. remaining risks;
11. safety confirmations;
12. final git status.

Stop after the push.
Do not begin reconciliation or the next task.
