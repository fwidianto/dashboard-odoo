# CT-8C2-R1 — Fetch/Apply Integrity Correction and Staging Validation

## Task metadata

- **Task ID:** CT-8C2-R1
- **Phase:** 8C-2 correction/review gate
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Current unaccepted implementation SHA:** `2ff2b41aa35577941bd66ab6872614b56cb11dc7`
- **Last accepted checkpoint:** `1d38f4568db457850baeff25cc8ed5a1954af124`
- **Complexity:** 4.5/5
- **Expected runtime:** 2–4 hours
- **Run-plan position:** Fetch/apply review and correction run; this remains inside the frozen 8–10-run plan.

Use `$stabilize-odoo-control-tower`.

The commit `2ff2b41aa35577941bd66ab6872614b56cb11dc7` is **not approved yet**. Correct the bounded blockers below, validate them, create one follow-up commit, and push normally. Do not amend or force-push the existing commit.

## Review verdict that triggered this task

**FAIL — blocking correctness and auditability issues.**

The overall fetch/apply architecture is usable, but completed reuse, manifest integrity, field normalization, database integrity, and stale-transition handling are not yet strong enough for an accepted checkpoint.

## Absolute restrictions

Do not:

- use production-looking `.env` or `nobi-main`;
- write to Odoo;
- access office-pilot or production databases;
- publish a candidate;
- advance watermarks;
- execute reconciliation;
- regenerate findings;
- add workers, APIs, or frontend changes;
- touch the four protected backup paths;
- amend, rebase, merge, force-push, or open a PR.

Local PostgreSQL modifications and disposable test databases are allowed.

A bounded read-only staging probe is allowed only under the exact rules in Section 10.

## 1. Repository safety

Before editing:

1. Fetch remotes.
2. Check out `feat/control-tower-refresh-center`.
3. Confirm HEAD is exactly `2ff2b41aa35577941bd66ab6872614b56cb11dc7`.
4. Confirm upstream tracking is intact.
5. Confirm only the four protected backup paths are untracked.
6. Inspect the complete diff from accepted checkpoint `1d38f4568db457850baeff25cc8ed5a1954af124` through current HEAD.
7. Stop if unrelated tracked changes exist.

## 2. Blocker A — RECONCILING reuse bypasses fetch/apply validation

Current orchestration classifies `RECONCILING` as a boundary state and returns the generic `_idempotent_boundary_result`. That path validates only copy-forward and detection evidence. The dedicated `FetchApplyService` completed validation path is therefore bypassed, while the `RECONCILING` branch inside `_ensure_fetch_apply` is effectively unreachable.

Correct this so that:

- `RECONCILING` always validates completed fetch/apply evidence through `FetchApplyService` using a strict NoCall Odoo client;
- the generic detection-only boundary result is never used for `RECONCILING`;
- a missing, partial, forged, or tampered fetch/apply header/evidence/candidate row fails closed;
- completed reuse makes zero Odoo calls;
- the returned summary includes the authoritative fetch/apply counts;
- `VALIDATING` remains the detection-only no-change boundary.

Add a regression test that tampers completed fetch/apply evidence after reaching `RECONCILING`, calls the public orchestrator with NoCall Odoo, and proves the call fails rather than returning an idempotent success.

## 3. Blocker B — stale pointer/base is not validated by completed service reuse

`FetchApplyService.run()` currently takes the completed-progress shortcut before `_validate_pointer`.

Correct this so every entry path, including completed `RECONCILING` reuse, validates:

- current trusted published pointer;
- candidate base snapshot identity;
- company identity;
- immutable selected domains;
- candidate run identity.

A completed older run must fail closed after a newer trusted snapshot is published.

Test both:

- direct `FetchApplyService` completed reuse;
- public orchestrator completed reuse.

## 4. Blocker C — manifest integrity is checked by counts, not exact durable content

Current `_detection_inputs` checks status/count/company/base but does not prove that the actual `ct_change_manifest` rows still match the completed detection fingerprint. A record ID or source timestamp can be substituted while preserving counts.

Do not duplicate detector fingerprint logic.

Reuse or cleanly expose the approved completed-detection validation path from `IncrementalChangeDetectionService` so fetch/apply starts only after exact validation of:

- detection contract fingerprint;
- completion fingerprint;
- selected domains;
- resolved models;
- base snapshot;
- company;
- manifest row count;
- exact manifest rows, model, record ID, source `write_date`, parent hints, and deterministic sequence;
- model row counts and scan evidence.

Completed detection validation must use NoCall Odoo and make zero source calls.

Add tampering tests for at least:

- replace one manifest record ID while keeping total/model counts unchanged;
- alter `source_write_date`;
- alter `detection_sequence`;
- change selected domains/models in the detection header;
- add an extra manifest row while removing another to preserve count.

Every case must fail before Odoo fetch or candidate mutation.

## 5. Blocker D — existing RUNNING fetch/apply header is insufficiently validated

`INSERT ... ON CONFLICT DO NOTHING` currently reloads an existing header, while contradictory-evidence validation compares only manifest fingerprint and count.

Before reusing any RUNNING or COMPLETE header, validate every immutable field against authoritative run/detection inputs:

- run ID;
- company ID;
- base snapshot run ID;
- sorted selected domains;
- exact resolved model plan;
- manifest completion fingerprint;
- manifest row count;
- batch size;
- fetch/apply contract version.

Any mismatch must fail closed and require a linked retry. Never silently replace or delete evidence.

## 6. Blocker E — database company/run integrity is incomplete

Migration 004 makes `ct_fetch_apply_run.run_id` a foreign key but does not, by itself, prove that its `company_id` equals the owning `ct_extraction_run.company_id`.

Inspect the existing schema and enforce run/company integrity at the database boundary. Prefer the existing composite `(run_id, company_id)` contract if already present on `ct_extraction_run`.

Because migration 004 has not been accepted or applied to any real database, correct it in a normal follow-up commit without amending history, or add a minimal migration 005 if repository migration rules make that safer. Report the decision.

Also harden relevant constraints so completed evidence cannot claim:

- `FETCHED` without `applied_at`;
- malformed/non-hex SHA-256 fingerprints;
- contradictory source-drift timestamps/statuses;
- impossible batch totals.

Add PostgreSQL constraint tests, including an attempted wrong-company header insert.

## 7. Blocker F — completion validation does not bind all audit evidence

The current fetch/apply completion fingerprint and completed validation do not bind enough durable content. They can miss tampering of detection sequence, source/fetched timestamps, source-drift flags, fetch status, batch rows, or a same-count evidence substitution.

Make completed reuse recompute and validate exact durable truth, including:

- every manifest input row;
- every fetch/apply evidence row;
- model and record ID;
- detection sequence;
- detection source timestamp;
- fetched timestamp;
- fetch status;
- apply status;
- source-drift flag;
- payload fingerprint;
- batch number;
- exact batch counts;
- candidate payload fingerprint/reference;
- missing-at-fetch classification;
- candidate/base/run/company/domain identities;
- field contract fingerprint/version.

Requirements:

- one evidence row exactly per manifest row;
- no missing, extra, substituted, or cross-model evidence;
- batch rows reconcile exactly to their evidence rows;
- header/model totals reconcile exactly;
- fetched candidate rows match payload evidence;
- missing-at-fetch rows remain unresolved and the copied baseline policy is proven or explicitly represented for reconciliation;
- no completed result trusts progress JSON alone.

Add tampering tests for each audit-critical field class above. At minimum prove that same-count row substitution and batch-count tampering are detected.

## 8. Blocker G — stale state writes can falsely report RECONCILING

Finalization currently performs conditional updates without checking affected row counts. A stale writer can move the run, causing the state update to affect zero rows while the method still returns a `RECONCILING` summary.

Correct finalization so:

- the run row is locked or atomically compare-and-set in the final transaction;
- header completion, final progress, and `FETCHING -> RECONCILING` transition are one all-or-nothing transaction;
- every conditional update checks `rowcount` or returns the updated row;
- a zero-row transition rolls back header/progress completion and fails closed;
- `_write_progress` does not silently ignore a stale status;
- no stale progress overwrites later-stage progress.

Add deterministic stale-writer failure injection proving no false success and no partially completed header.

## 9. Blocker H — hard-coded field types diverge from the canonical extractor

`fetch_apply.py` introduces a parallel `_MANY2ONE_FIELDS/_MANY2MANY_FIELDS` map. It already conflicts with the approved relation contract: `sale.order.x_studio_io_1` is declared `many2many` in `LINK_SPECS`, while the new map treats it as `many2one`. Other custom fields can also be char or relational depending on actual Odoo metadata.

Remove the parallel hard-coded normalization contract.

Reuse the canonical extractor normalization behavior:

- approved `MODEL_SPECS` remains the field allowlist;
- field type comes from trusted Odoo model metadata or a single shared explicit contract;
- reuse `normalize_value` or a shared extracted helper rather than duplicating semantics;
- many2one/many2many/one2many normalization matches existing snapshots exactly;
- missing approved fields fail closed;
- unexpected fields fail closed;
- relation IDs reject bool, zero, negative, malformed pairs, and malformed ID lists;
- display names remain non-authoritative.

A read-only metadata call such as the established `get_model_fields` is allowed. Cache it once per model for the run. Do not request unapproved payload fields.

Update fakes/tests so `sale.order.x_studio_io_1` is exercised with its approved cardinality and custom fields are tested as both scalar and relational where repository contracts allow variability.

## 10. Migration downgrade safety

Current downgrade re-adds the old manifest status constraint while `MISSING_AT_FETCH` rows may still exist, which can make a used migration impossible to downgrade.

Make downgrade executable after real migration-004 data exists. Preserve audit meaning as far as possible; for example, map `MISSING_AT_FETCH` manifest statuses back to the prior unresolved status before restoring the old constraint. Do not delete historical manifest rows.

Add a real PostgreSQL upgrade-use-downgrade test containing at least one `MISSING_AT_FETCH` row.

## 11. Authorized bounded staging validation

Only after all fake and disposable-PostgreSQL tests pass:

- use `.env.sandbox` only;
- require database exactly `nobi1-staging2-35813410`;
- require the matching `.dev.odoo.com` host;
- require company ID 3;
- reject `.env`, `nobi-main`, production, or any other database;
- Odoo is strictly read-only;
- do not apply migration 004/005 to staging Odoo or any real PostgreSQL database;
- use a temporary local/disposable PostgreSQL candidate database;
- use bounded metadata reads and bounded `search_read` probes only;
- no create/write/unlink/action/read_batched/full-history reads;
- small limits only.

Validate all 12 approved models for:

- approved fields exist;
- actual field types/cardinalities;
- actual payload shapes;
- company scope;
- `write_date` parser compatibility;
- many2one/many2many/custom-field normalization;
- flat Odoo domains;
- bounded limits;
- canonical payload compatibility with the shared extractor contract.

Then execute a small public fetch/apply path against the disposable local PostgreSQL candidate using staging Odoo reads only. Prove:

- Odoo received only approved read methods;
- candidate writes stayed local;
- source/published pointer/watermarks remained unchanged locally;
- no Odoo mutation method was available or called.

If any approved field is absent or a field type differs, fail closed and correct the contract rather than silently dropping it.

## 12. Regression tests

Retain and rerun all existing Phase 8 tests. Add focused regression coverage for all blockers.

Required suites:

- fetch/apply PostgreSQL tests;
- orchestration PostgreSQL tests;
- change-detection mocked and PostgreSQL tests;
- copy-forward tests;
- refresh-contract tests;
- full focused Control Tower Python suite;
- frontend static tests;
- Python compilation;
- blocked-access imports;
- Alembic offline upgrade/downgrade;
- real PostgreSQL upgrade-use-downgrade;
- `git diff --check`.

Required result:

- zero failures;
- zero PostgreSQL-related skips;
- staging probe PASS for all 12 models;
- no production/office-pilot access;
- no Odoo writes;
- disposable databases removed;
- temporary secrets/artifacts removed;
- `CT_TEST_POSTGRES_URL` unset.

## 13. Self-review gate

Before committing, independently inspect the full diff and explicitly verify:

- RECONCILING public reuse reaches exact FetchApplyService validation;
- stale pointer completed reuse fails;
- exact manifest tampering is detected;
- existing header immutable inputs are all validated;
- database run/company integrity is enforced;
- completion fingerprints bind all audit-critical evidence;
- batch/evidence/candidate totals reconcile;
- stale transition cannot report false success;
- canonical field normalization is shared rather than duplicated;
- migration downgrade works after MISSING_AT_FETCH data;
- no reconciliation/publication/watermark/worker/API/frontend scope entered.

## 14. Commit and push

After a clean PASS:

1. Create one follow-up commit; do not amend `2ff2b41...`.
2. Commit message:
   `fix(control-tower): harden fetch apply integrity`
3. Commit body must include:
   - `Task: CT-8C2-R1`
   - base SHA `2ff2b41aa35577941bd66ab6872614b56cb11dc7`;
   - exact blockers corrected;
   - exact tests/results;
   - migration decision;
   - exact staging database/host/company used;
   - confirmation of read-only staging access;
   - confirmation no publication or watermark advancement occurred.
4. Push normally to `origin/feat/control-tower-refresh-center`.
5. Verify local and remote SHAs match.
6. Final working tree must contain only the four protected backup paths.

If any blocker remains, do not commit a partial correction. Stop and report.

## 15. Final report

Return:

1. verdict;
2. correction commit SHA;
3. pushed remote SHA;
4. exact changed files;
5. blocker-by-blocker resolution;
6. migration decision and downgrade evidence;
7. fake/PostgreSQL test totals;
8. real staging compatibility results for all 12 models;
9. exact Odoo methods/domains/limits used;
10. stale-pointer and tampering evidence;
11. safety confirmation;
12. final git status.

Stop after the push. Do not start reconciliation.
