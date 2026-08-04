# CT-8C2-R2 — Fetch/Apply Evidence Closure

## Task metadata

- **Task ID:** CT-8C2-R2
- **Phase:** 8C-2 final integrity closure
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Current unaccepted implementation SHA:** `0ea9128b860b46e68d153adb8ab3c5b2eb8d6490`
- **Last accepted checkpoint:** `1d38f4568db457850baeff25cc8ed5a1954af124`
- **Complexity:** 4/5
- **Expected runtime:** 1.5–3 hours; allow up to 4 hours only if a migration 005 is genuinely required
- **Run-plan position:** substantive Run 5 within the frozen 8–10-run office-pilot plan

Use `$stabilize-odoo-control-tower`.

The previous correction fixed the original architecture blockers and passed bounded staging compatibility. It is not accepted yet because several exact-evidence gaps remain. Close only those gaps, validate them, create one follow-up commit, and push normally.

## Absolute restrictions

Do not:

- write to Odoo;
- use production-looking `.env` or `nobi-main`;
- access office-pilot or production databases;
- publish a candidate;
- advance watermarks;
- execute parent or deletion reconciliation;
- regenerate findings;
- add workers, APIs, or frontend changes;
- touch the four protected backup paths;
- amend, rebase, merge, force-push, or open a PR;
- repeat the broad staging probe unless a changed field contract genuinely requires one tiny bounded read-only verification.

Use mocked Odoo and newly created disposable PostgreSQL databases. Odoo remains strictly read-only.

## 1. Repository safety

Before editing:

1. Fetch remotes.
2. Check out `feat/control-tower-refresh-center`.
3. Confirm HEAD is exactly `0ea9128b860b46e68d153adb8ab3c5b2eb8d6490`.
4. Confirm upstream tracking is intact.
5. Confirm only the four protected backup paths are untracked:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`
6. Inspect the full cumulative Phase 8C-2 diff from `1d38f4568db457850baeff25cc8ed5a1954af124`.
7. Stop rather than repairing history if unrelated tracked changes exist.

## 2. Shared immutable-header validation

Create one authoritative validation path used for both RUNNING and COMPLETE fetch/apply headers.

It must compare the durable header against current authoritative inputs:

- run ID;
- run company ID;
- run base snapshot ID;
- run selected domains;
- exact resolved model order;
- completed detection fingerprint;
- manifest row count;
- batch size;
- fetch/apply contract version;
- field-contract fingerprint/version described below.

Do not use the header's own selected domains as the sole source for validating the run. Direct `FetchApplyService` completed reuse must validate `ct_extraction_run.selected_domains` against the header and detection evidence.

A single-field alteration to any immutable header or run identity must fail closed and require a linked retry where appropriate.

Add tests for at least:

- completed header `contract_version` tampering;
- completed run `selected_domains` tampering through direct service reuse;
- completed header base/domain/model/batch-size tampering;
- wrong company/run identity.

## 3. Durable field-contract fingerprint

The plain `ct-fetch-apply-v1` string is not enough to prove the payload contract used for a completed run.

Persist and bind a deterministic field-contract fingerprint that covers:

- fetch/apply contract version;
- ordered resolved models;
- approved ordered field names from `MODEL_SPECS` for every model;
- trusted metadata needed for normalization for every approved field:
  - field type;
  - relation target where provided;
  - cardinality semantics;
- batch size where it affects deterministic stage layout.

Rules:

- During initial fetch, obtain metadata through the existing bounded read-only metadata path, validate it, canonicalize it, and persist the fingerprint as durable run evidence.
- During incomplete resume that still needs Odoo, current metadata must match the persisted contract before new batches are fetched.
- During completed NoCall reuse, validation must recompute the code-side allowlist portion without Odoo and verify the persisted completed contract/fingerprint. Do not contact Odoo.
- A changed `MODEL_SPECS` field list must invalidate an old completion even when a developer forgets to manually bump a string constant.
- Do not persist display names as authoritative schema evidence.

Prefer adding explicit columns to durable fetch/apply run evidence. Since migration 004 is now committed on the feature branch, add a minimal migration **005** rather than editing migration 004 again if new durable columns are required. Migration 005 must have safe upgrade/downgrade behavior and must not apply to any real database in this run.

Add deterministic tests by injecting or monkeypatching a changed approved field contract and proving completed reuse fails without Odoo.

## 4. Bind every audit field

Strengthen exact completed evidence so its recomputed fingerprint includes all durable audit fields.

### Fetch/apply evidence rows

Bind at least:

- model;
- record ID;
- detection sequence;
- detection source timestamp;
- fetched source timestamp;
- fetch status;
- apply status;
- source-drift flag;
- payload fingerprint;
- batch number;
- fetched-at timestamp;
- applied-at timestamp;
- canonical `error_evidence` JSON;
- company/run identity through the parent contract.

Normalize timestamps to deterministic aware UTC strings. Canonicalize JSON with stable sorting.

### Batch rows

Bind at least:

- model;
- batch number;
- every count;
- source-drift count;
- completed-at timestamp.

### Header and progress

Completed validation must compare recomputed truth with:

- stored completion fingerprint;
- stored `model_fetch_counts`;
- fetch/apply progress completion fingerprint;
- progress model plan/completion;
- progress record/batch/classification counts;
- progress completion marker and stage boundary;
- progress started/finished timestamps and elapsed-time consistency.

Progress is not the source of truth, but contradictory progress must fail closed rather than being silently ignored.

Add tampering tests for:

- `fetched_at`;
- `applied_at`;
- `error_evidence`;
- batch `completed_at`;
- header `model_fetch_counts`;
- progress count/model/fingerprint/timestamp contradictions.

## 5. Exact source-drift consistency

Enforce the equivalence, not a one-way implication:

```text
source_drift = (fetched_write_date > detection_source_write_date)
```

For MISSING_AT_FETCH, source drift must be false and fetched timestamp must remain null.

Also enforce and validate:

- batch `source_drift` equals the exact count of evidence rows whose drift flag is true;
- batch source-drift count cannot exceed fetched count;
- aggregate progress drift count equals durable evidence;
- tampering before completion cannot be absorbed into a newly generated completion fingerprint.

Use database constraints where practical and service-level exact reconciliation regardless.

Add tests for false drift with a newer timestamp, true drift without a newer timestamp, and mismatched batch drift totals.

## 6. Manifest lifecycle status reconciliation

The completed detection validator may continue normalizing mutable manifest status to DETECTED for detection-fingerprint purposes.

Fetch/apply validation must separately prove lifecycle status:

- fetched evidence with INSERTED/UPDATED/UNCHANGED → manifest status `APPLIED`;
- missing evidence → manifest status `MISSING_AT_FETCH`;
- no manifest row may remain `DETECTED` or `FETCHED` at the RECONCILING boundary;
- no unknown status may be accepted.

Add completed-reuse and pre-completion tampering tests for mismatched manifest statuses.

## 7. Prove the missing-at-fetch baseline policy

For each `MISSING_AT_FETCH` row, completed validation must prove one of these exact states:

1. the base snapshot contains the record and the candidate still contains an exact copied baseline row; or
2. both base and candidate snapshots do not contain the record.

It must reject:

- candidate deletion when a base row exists;
- candidate payload modification;
- candidate non-payload column modification;
- candidate insertion when the base had no row.

Do not delete missing records in this phase. Leave them explicitly unresolved for reconciliation.

Add tests for missing-row baseline deletion, payload modification, and absent-base/candidate consistency.

## 8. Validate the complete candidate snapshot row

For fetched records, do not validate only JSON payload fingerprint.

Validate candidate columns against canonical normalized payload/evidence:

- `model` and `record_id`;
- `document_number`;
- `state`;
- `company_id`;
- `company_name` as non-authoritative display evidence;
- `write_date`;
- payload;
- extraction run ID.

Tampering any business-relevant snapshot column must fail completed reuse.

Add tests for at least company, state/document number, and write-date column tampering with unchanged payload.

## 9. Deterministic batch membership

Prove each manifest detection sequence maps to the expected batch number from:

- deterministic model order;
- detection-sequence order;
- persisted batch size.

Counts alone are insufficient. Moving evidence rows between batch numbers while preserving all totals must fail.

Validate that:

- expected batch numbers are contiguous per model;
- no extra or missing batch row exists;
- every evidence row belongs to its calculated batch;
- batch requested IDs correspond exactly to the manifest slice.

Add a same-count batch-membership shuffle test.

## 10. State truth for completed evidence

Never return a summary that claims `RECONCILING` when the durable run status/stage is still `FETCHING`.

For a completed header/progress with contradictory run status:

- either perform a separately proven, atomic recovery transition after full exact validation; or
- fail closed and require operator-linked retry/recovery.

Do not merely return a RECONCILING summary.

Also require completed reuse status and stage both equal `RECONCILING`.

Add a forged/corrupt `FETCHING + COMPLETE evidence` test proving no false success.

## 11. Transaction and lock behavior

Preserve the current global lock order and atomic finalization improvements.

Confirm:

- no nested advisory-lock deadlock;
- completed NoCall reuse does not contact Odoo or metadata endpoints;
- shared validation does not write progress;
- finalization remains one transaction;
- conditional updates check row counts;
- stale writers cannot overwrite later-stage progress;
- evidence/header/progress validation happens before reporting success.

## 12. Migration policy

Do not edit migrations 001–004 again unless a repository-enforced rule makes migration 005 impossible and you explicitly report why.

When migration 005 is needed:

- add only the minimal durable contract fields/constraints/indexes;
- preserve existing rows or define a fail-closed bootstrap requirement;
- ensure a clean new-database upgrade to head;
- ensure downgrade 005→004;
- ensure the existing 004→003 downgrade with MISSING_AT_FETCH still works;
- use disposable PostgreSQL only.

## 13. Tests and validation

Run at minimum:

- all new CT-8C2-R2 tests;
- complete fetch/apply PostgreSQL suite;
- orchestration PostgreSQL suite;
- change-detection PostgreSQL and mocked suites;
- copy-forward and refresh-contract PostgreSQL suites;
- all Phase 8 PostgreSQL tests;
- full focused Control Tower Python suite;
- frontend static regressions;
- Python compilation;
- blocked-access imports;
- Alembic offline full upgrade and relevant downgrades;
- real disposable-PostgreSQL upgrade/use/downgrade for migration 005 when added;
- `git diff --check`.

Required:

- zero failures;
- zero PostgreSQL-related skips;
- no real Odoo contact unless one narrowly justified metadata probe is required by an actually changed contract;
- no Odoo write-capable methods;
- no office-pilot/production access;
- no publication, watermark movement, reconciliation, findings, worker, API, or frontend implementation;
- disposable databases removed;
- `CT_TEST_POSTGRES_URL` unset;
- no repository artifacts.

GitHub Actions are not currently attached to the branch, so include exact local test commands and totals in the commit body.

## 14. Self-review gate

Before committing:

1. Inspect the full diff from `0ea9128b860b46e68d153adb8ab3c5b2eb8d6490`.
2. Confirm each blocker above has a direct regression test.
3. Confirm completed reuse is strict NoCall.
4. Confirm field contract changes invalidate old completion.
5. Confirm all evidence fingerprints are canonical and complete.
6. Confirm missing-at-fetch baseline remains untouched.
7. Confirm no reconciliation/publication/watermark behavior entered the diff.
8. Confirm migration ownership and downgrade safety.
9. Run `git diff --check` again.

## 15. Commit and push

After all gates pass:

1. Commit the exact CT-8C2-R2 files in one follow-up commit.
2. Commit message:

   `fix(control-tower): close fetch apply evidence gaps`

3. Commit body must include:
   - `Task: CT-8C2-R2`;
   - `Base SHA: 0ea9128b860b46e68d153adb8ab3c5b2eb8d6490`;
   - exact changed files;
   - migration decision;
   - every blocker closed;
   - exact tests and totals;
   - Odoo/staging access statement;
   - safety confirmation;
   - remaining risks.
4. Push normally to `origin/feat/control-tower-refresh-center`.
5. Do not amend, force-push, merge, or open a PR.
6. Verify local and remote SHA match.
7. Verify the working tree contains only the four protected backup paths.

## 16. Final report

Return a concise report containing:

1. verdict;
2. commit and remote SHA;
3. changed files;
4. migration decision;
5. immutable header and field-contract validation;
6. exact evidence/fingerprint coverage;
7. drift, manifest status, candidate, and missing-baseline checks;
8. deterministic batch proof;
9. state-truth behavior;
10. test totals;
11. safety confirmation;
12. final git status.

Stop after the push. Do not begin reconciliation or any later phase.
