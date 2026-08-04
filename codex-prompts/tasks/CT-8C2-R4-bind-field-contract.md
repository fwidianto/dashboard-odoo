# CT-8C2-R4 — Bind Durable Field-Contract Evidence

## Task metadata

- **Task ID:** CT-8C2-R4
- **Phase:** 8C-2 final integrity closure
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Current unaccepted implementation SHA:** `9c4d11aeb45f9ace18300aa1135e20cd0c1d4a00`
- **Last accepted checkpoint:** `1d38f4568db457850baeff25cc8ed5a1954af124`
- **Complexity:** 2.5/5
- **Expected runtime:** 45–90 minutes; stop and report before broadening scope

Use `$stabilize-odoo-control-tower`.

The CT-8C2-R3 correction closes its four named issues, but one exact-evidence gap remains. Fix only this gap and the directly related dead-code cleanup. Do not redesign fetch/apply or start reconciliation.

## Absolute restrictions

Do not:

- write to or contact real Odoo;
- access office-pilot or production;
- modify migrations 001–005;
- add migration 006;
- publish candidates or advance watermarks;
- execute reconciliation or regenerate findings;
- add workers, APIs, or frontend changes;
- touch the four protected backup paths;
- amend, rebase, merge, force-push, or open a PR.

Use mocked Odoo and newly created disposable PostgreSQL databases only.

## 1. Repository safety

Before editing:

1. Fetch remotes and check out `feat/control-tower-refresh-center`.
2. Confirm HEAD is exactly `9c4d11aeb45f9ace18300aa1135e20cd0c1d4a00`.
3. Confirm upstream tracking is intact.
4. Confirm the working tree contains only the four protected untracked paths.
5. Inspect the cumulative Phase 8C-2 diff from `1d38f4568db457850baeff25cc8ed5a1954af124`.
6. Stop rather than repairing history if unrelated tracked changes exist.

## 2. Blocking defect

The durable `field_contract_fingerprint` is currently not cryptographically bound to completed fetch/apply evidence.

Current behavior:

- completed reuse recomputes and validates the code-side allowlist fingerprint;
- it verifies only that the full metadata fingerprint is non-empty;
- `_completion_fingerprint()` does not include `field_contract_version`, `field_contract_fingerprint`, or `field_contract_allowlist_fingerprint`;
- therefore changing the stored full metadata fingerprint to another valid 64-character hex value can still allow completed NoCall reuse to succeed.

This violates the approved requirement that completed NoCall reuse validate the persisted full field-contract fingerprint as well as the recomputed code-side allowlist.

## 3. Required correction

Bind all three durable field-contract values into the authoritative completion fingerprint:

- `field_contract_version`;
- `field_contract_fingerprint`;
- `field_contract_allowlist_fingerprint`.

Requirements:

1. `_completion_fingerprint()` must include their exact persisted values.
2. Finalization must never calculate completion from a stale in-memory header whose `field_contract_fingerprint` is still `None` after the database update.
3. When the initial full fingerprint is persisted:
   - require the conditional update to affect exactly one row;
   - fail closed on zero-row/stale updates;
   - refresh or update the authoritative in-memory header before finalization.
4. Completed NoCall reuse must:
   - make zero Odoo and metadata calls;
   - recompute the code-side allowlist;
   - recompute completion evidence using the exact stored full metadata fingerprint;
   - fail when any one of the three field-contract values is altered.
5. Preserve valid incomplete-resume metadata checks and all accepted Phase 8C-2 behavior.
6. Do not store or expose full Odoo metadata payloads merely to solve this.

## 4. Focused cleanup

Remove only directly related dead code introduced or exposed by the R3 change:

- the now-unused `LINK_SPECS` import and `_relation_target()` helper, provided repository search confirms no remaining use;
- the duplicate unreachable `return self._metadata_cache[model]`.

Do not perform unrelated formatting or refactoring.

## 5. Required tests

Add deterministic PostgreSQL tests proving:

1. A successful run stores a non-null 64-character full field-contract fingerprint and its completion fingerprint is stable on NoCall reuse.
2. Changing only `field_contract_fingerprint` to another valid 64-character hex value causes completed NoCall reuse to fail.
3. Changing `field_contract_version` causes completed reuse to fail.
4. Changing `field_contract_allowlist_fingerprint` causes completed reuse to fail.
5. A stale/zero-row conditional full-fingerprint persistence cannot proceed to payload fetch/finalization or false completion.
6. Completed reuse still makes zero Odoo and metadata calls.
7. Existing relation-target-change incomplete-resume test still passes.

Use the smallest practical deterministic mechanism for the stale update test. Do not add production-only hooks unless existing failure-injection infrastructure cannot express the boundary; prefer a focused test seam consistent with the current service.

## 6. Validation

Run at minimum:

- complete fetch/apply PostgreSQL suite;
- orchestration PostgreSQL suite;
- all Phase 8 PostgreSQL suites;
- full focused Control Tower Python suite;
- frontend static regressions;
- Python compilation;
- blocked-access imports;
- Alembic offline upgrade and downgrade 005→001;
- `git diff --check`.

Required:

- zero failures;
- zero PostgreSQL-related skips;
- no real Odoo/office-pilot/production access;
- no repository artifacts;
- disposable databases removed;
- `CT_TEST_POSTGRES_URL` unset afterward.

## 7. Self-review

Before committing, verify:

- all three field-contract values are bound into completion evidence;
- finalization cannot use a stale `None` fingerprint;
- tampering with a valid-looking full fingerprint fails completed reuse;
- completed reuse remains strict NoCall;
- no schema, reconciliation, publication, watermark, finding, worker, API, or frontend scope entered the diff;
- only focused dead code was removed;
- `git diff --check` is clean.

## 8. Commit and push

After implementation, validation, and self-review:

1. Commit the exact correction files in one commit.
2. Commit message:

   `fix(control-tower): bind fetch field contract evidence`

3. Include a concise body containing:
   - `Task: CT-8C2-R4`
   - `Base SHA: 9c4d11aeb45f9ace18300aa1135e20cd0c1d4a00`
   - exact changed files;
   - tests and totals;
   - field-contract binding decision;
   - stale-update behavior;
   - confirmation of zero real Odoo/office-pilot/production access;
   - confirmation no reconciliation/publication/watermark advancement occurred.
4. Push normally to `origin/feat/control-tower-refresh-center`.
5. Do not force-push or open a PR.
6. Verify local HEAD equals remote SHA.
7. Verify final working tree contains only the four protected backup paths.

## 9. Final report

Return a concise report with:

1. verdict;
2. local and remote SHA;
3. changed files;
4. completion-fingerprint binding;
5. stale update handling;
6. tests and totals;
7. safety confirmation;
8. remaining risks;
9. final git status.

Stop after the push. Do not start reconciliation or another phase.
