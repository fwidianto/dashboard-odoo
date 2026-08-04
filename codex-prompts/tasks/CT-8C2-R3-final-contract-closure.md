# CT-8C2-R3 — Final Fetch/Apply Contract Closure

## Task metadata

- **Task ID:** CT-8C2-R3
- **Phase:** 8C-2 final bounded correction
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Current unaccepted implementation SHA:** `87d536cdd4edabd12375892630e3c551e1130170`
- **Last accepted checkpoint:** `1d38f4568db457850baeff25cc8ed5a1954af124`
- **Complexity:** 3/5
- **Expected runtime:** 1–2 hours; allow up to 3 hours only if existing copy-forward timestamp semantics require additional focused tests
- **Run-plan position:** substantive Run 6 within the frozen 8–10-run office-pilot plan

Use `$stabilize-odoo-control-tower`.

The previous correction closed most evidence gaps. Do not redesign fetch/apply. Close only the four remaining contract issues below, validate them, create one follow-up commit, and push normally.

## Absolute restrictions

Do not:

- write to Odoo;
- contact real Odoo unless an implementation change truly cannot be validated with existing staging evidence and fakes; the expected result is no real Odoo contact;
- use production-looking `.env` or `nobi-main`;
- access office-pilot or production databases;
- publish a candidate;
- advance watermarks;
- execute reconciliation;
- regenerate findings;
- add workers, APIs, or frontend changes;
- edit migrations 001–005;
- touch the four protected backup paths;
- amend, rebase, merge, force-push, or open a PR.

Use mocked Odoo and newly created disposable PostgreSQL databases only.

## 1. Repository safety

Before editing:

1. Fetch remotes.
2. Check out `feat/control-tower-refresh-center`.
3. Confirm HEAD is exactly `87d536cdd4edabd12375892630e3c551e1130170`.
4. Confirm upstream tracking is intact.
5. Confirm only the four protected backup paths are untracked:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`
6. Inspect the cumulative Phase 8C-2 diff from `1d38f4568db457850baeff25cc8ed5a1954af124`.
7. Stop rather than repairing history if unrelated tracked changes exist.

## 2. Blocker A — Fetch/apply schema guard must require revision 005

Current fetch/apply code unconditionally selects and writes the migration-005 field-contract columns, while `ensure_phase8_fetch_schema_ready()` still accepts revision 004.

Correct the service boundary so:

- current `FetchApplyService` requires Alembic revision 005;
- revision 004 fails immediately and cleanly with `Phase8SchemaNotReady` before fetch/apply SQL accesses missing columns;
- revision 002/003 services keep their existing independent readiness behavior;
- the guard verifies all migration-004 tables and all migration-005 contract columns;
- no migration is applied automatically.

Add PostgreSQL tests proving:

- revision 004 is rejected cleanly by the fetch/apply service/guard;
- revision 005 is accepted;
- detection and earlier-stage guards still accept their documented revisions.

## 3. Blocker B — Exact trusted metadata contract

The persisted full field-contract fingerprint currently records field type and only whether metadata contains a relation. It substitutes `LINK_SPECS` for relation targets, but `LINK_SPECS` is a business graph contract and does not cover every relational snapshot field.

Correct the metadata contract so, for every approved field in every resolved model, the full fingerprint binds the actual trusted Odoo metadata normalization inputs:

- field name;
- exact field type;
- exact metadata relation target string where provided, not only truthiness;
- cardinality semantics represented by the exact field type;
- ordered model and field allowlists;
- batch size and fetch/apply contract version.

Requirements:

- validate that metadata contains an object definition for every approved field before fingerprinting or fetching;
- reject a missing approved metadata definition rather than treating it as an untyped scalar;
- reject missing/blank field type;
- relational field types must have a valid relation target where Odoo provides/requires one;
- do not use display names as schema evidence;
- completed NoCall reuse must remain Odoo-free and validate the persisted full fingerprint plus the recomputed code-side allowlist;
- incomplete resume may use cached bounded metadata and must match the stored full fingerprint before new batches execute.

Do not add another migration. Migration 005 already provides the durable columns.

Add deterministic fake-Odoo/PostgreSQL tests proving:

- changing only the metadata relation target changes the full contract fingerprint and blocks incomplete resume before another payload fetch;
- missing metadata for one approved field fails before candidate mutation;
- blank/malformed metadata field type fails closed;
- valid metadata for all 12 approved models still works.

## 4. Blocker C — Exact MISSING_AT_FETCH baseline equality

Current completed validation proves only that base and candidate rows are both present or both absent. It does not prove that a present candidate is an exact copy of the trusted base row.

For each `MISSING_AT_FETCH` evidence row, compare the base and candidate snapshot rows exactly according to the copy-forward contract.

At minimum bind and compare:

- model and record ID;
- document number;
- state;
- company ID;
- company name as display evidence;
- write date;
- canonical payload.

Inspect `CandidateSnapshotCopyForwardService` to determine the intended treatment of `extraction_run_id` and `extracted_at`:

- run identity is expected to differ between base and candidate;
- compare `extracted_at` only when copy-forward is contractually expected to preserve it;
- otherwise document and test the exact intentional exception.

Required states:

1. base exists and candidate retains the exact copied business row; or
2. both base and candidate are absent.

Reject:

- candidate deletion when base exists;
- candidate insertion when base is absent;
- candidate payload modification;
- candidate document/state/company/company-name/write-date modification.

Do not delete or modify missing-at-fetch candidate rows in this phase.

Add PostgreSQL tests for payload and non-payload tampering while both rows remain present.

## 5. Blocker D — Complete fetched-row column validation

Fetched-record completed validation compares most snapshot columns but omits `company_name`, despite the approved task requiring the complete snapshot row to be checked.

Add exact comparison of candidate `company_name` against the normalized payload's non-authoritative company display evidence.

Also remove the duplicated unreachable `write_date` comparison block currently present in `_validate_candidate_rows`.

Add a test that changes only candidate `company_name` while leaving payload and company ID unchanged and proves completed NoCall reuse fails.

## 6. Preserve all accepted behavior

Do not weaken existing guarantees:

- exact detection-manifest validation;
- immutable RUNNING/COMPLETE headers;
- field allowlist invalidation;
- evidence/batch/progress fingerprints;
- exact source-drift equivalence;
- manifest lifecycle status reconciliation;
- deterministic batch membership;
- transactional finalization and row-count checks;
- RECONCILING status/stage truth;
- candidate/source/pointer/watermark immutability;
- strict read-only Odoo calls;
- no Odoo call during completed reuse.

## 7. Tests and validation

Run at minimum:

- all new CT-8C2-R3 tests;
- complete fetch/apply PostgreSQL suite;
- orchestration PostgreSQL suite;
- change-detection mocked and PostgreSQL suites;
- copy-forward and refresh-contract PostgreSQL suites;
- all Phase 8 PostgreSQL tests;
- full focused Control Tower Python suite;
- frontend static regressions;
- Python compilation;
- blocked-access imports;
- Alembic offline full upgrade and downgrade 005→001;
- real disposable-PostgreSQL clean upgrade to 005 and relevant downgrade checks;
- `git diff --check`.

Required:

- zero failures;
- zero PostgreSQL-related skips;
- no real Odoo contact unless narrowly justified and reported;
- no office-pilot/production access;
- no repository artifacts;
- disposable databases removed;
- `CT_TEST_POSTGRES_URL` unset afterward.

## 8. Self-review

Before committing:

1. Inspect the complete diff from `87d536c...`.
2. Confirm only the bounded contract fixes and tests are present.
3. Confirm no reconciliation/publication/watermark/finding/worker/API/frontend work entered the diff.
4. Confirm revision 004 now fails cleanly at the fetch/apply boundary.
5. Confirm actual metadata relation targets are fingerprinted.
6. Confirm every approved field requires valid metadata.
7. Confirm missing-at-fetch present rows are compared against the full base business row.
8. Confirm fetched candidate `company_name` is validated.
9. Confirm completed NoCall reuse makes zero Odoo or metadata calls.
10. Run `git diff --check` again.

## 9. Commit and push

After implementation, validation, and self-review:

1. Commit the exact CT-8C2-R3 files in one commit.
2. Commit message:

   `fix(control-tower): finalize fetch apply contracts`

3. Include a concise commit body containing:
   - `Task: CT-8C2-R3`
   - `Base SHA: 87d536cdd4edabd12375892630e3c551e1130170`
   - exact changed files;
   - test totals and zero PostgreSQL skips;
   - schema-guard decision;
   - metadata-contract decision;
   - missing-at-fetch equality policy;
   - confirmation no real Odoo/office-pilot/production access occurred;
   - confirmation no publication, watermark advancement, or reconciliation occurred.
4. Push normally to `origin/feat/control-tower-refresh-center`.
5. Do not force-push.
6. Do not open a PR.
7. Verify local HEAD equals remote SHA.
8. Verify final working tree contains only the four protected backup paths.

## 10. Final report

Return a concise report containing:

1. implementation verdict;
2. commit and verified remote SHA;
3. exact changed files;
4. revision-004 rejection evidence;
5. exact metadata-fingerprint contract;
6. missing-at-fetch full-row policy;
7. fetched company-name validation;
8. tests and totals;
9. safety confirmations;
10. remaining risks;
11. final git status.

Stop after the push.
Do not begin reconciliation or another phase.
