# CT-8D1-R1 — Replace Evidence State on Refresh Reload

## Task metadata

- **Task ID:** CT-8D1-R1
- **Capability:** Truthful visible Refresh Data experience
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `f0f0eff84d9a5122ff6d84bb92f58244ea4d4a18`
- **Classification:** MUST DO NOW
- **Correction allowance:** The single default correction run for CT-8D1
- **Expected runtime:** 30–90 minutes; stop rather than broadening

Use `$stabilize-odoo-control-tower`.

## 1. User-visible problem

The CT-8D1 Refresh Data experience is implemented, but its successful post-refresh evidence reload currently reuses mutable browser state.

`loadEvidenceData(true)` fetches the categories again and `ingestPayload()` adds each returned process count with `+=` without first replacing the previous evidence state.

Normal user consequence:

```text
initial visible process count = 3
→ successful Refresh Data reload returns 3
→ visible process count becomes 6
→ another refresh can make it 9
```

A category request that succeeded previously but fails during a later reload can also leave the old category availability, rows, or process counts in memory and make stale evidence look current.

This violates CT-8D1's frozen requirement that refreshed data remain truthful.

## 2. Mandatory preflight

Before editing:

1. freshly read repository `AGENTS.md`;
2. read `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md` from `origin/codex-prompts` with `git show`;
3. read the original CT-8D1 prompt;
4. inspect current `src/static/dashboard/control-tower-shell.js` and its focused frontend tests;
5. fetch remotes and confirm branch HEAD is exactly `f0f0eff84d9a5122ff6d84bb92f58244ea4d4a18`;
6. confirm no unexpected tracked changes;
7. preserve these paths without modifying or deleting them:
   - `.phase6-1-backup/`
   - `.phase6-backup/`
   - `.phase7-1-backup/`
   - `src/static/dashboard/sales-orders.js.phase7-3-backup`

Stop if the required base or working-tree condition is not met.

## 3. Required correction

Make the smallest coherent frontend-state correction so that every complete evidence reload is a **replacement**, never an accumulation.

The corrected behavior must ensure:

1. a second successful evidence load replaces category counts, availability, rows, and per-process counts from the first load;
2. repeated successful refreshes with identical backend data keep identical visible counts;
3. when a category fails on a later reload, its old availability, rows, and process counts are not retained as though they were current;
4. successful categories from that same reload still render truthfully as partial evidence;
5. when all categories fail, the existing unavailable behavior remains truthful;
6. the selected Process Map node and Inspector are restored after the reload;
7. map scroll, Temuan expansion, route/query state, and refresh panel behavior are not regressed;
8. do not perform a full-page reload.

Prefer either:

- rebuilding a fresh temporary evidence snapshot and replacing the current state after `Promise.allSettled`, or
- explicitly resetting all evidence accumulators before ingesting a new complete load.

Choose the smaller reliable implementation. Do not add a state-management framework or broad abstraction.

## 4. Strict scope

Expected implementation files are limited to:

- `src/static/dashboard/control-tower-shell.js`;
- the smallest relevant frontend test file(s).

A tiny change to an existing browser fixture/harness is allowed only when required for deterministic proof.

Do not change:

- refresh API or backend projection;
- Odoo/PostgreSQL extraction, fetch/apply, publication, reconciliation, or watermark logic;
- migrations or schema;
- authentication or authorization;
- HTML/CSS or visual composition unless an unavoidable test hook is required;
- other dashboards;
- business-rule semantics;
- dependencies or infrastructure.

Do not contact real Odoo, office-pilot, or production.

## 5. Required regression proof

Add deterministic tests that execute the reload behavior, not merely search source text.

At minimum prove:

### A. Repeated successful reload

```text
first load:  process A / Masalah Aktif = 3
second load: process A / Masalah Aktif = 2
result:      visible/in-memory count = 2, not 5
```

Also prove an identical second response remains identical rather than doubling.

### B. Later partial failure

```text
first load: all categories succeed
second load: one category fails, remaining categories succeed
result: failed category is unavailable and contributes no retained old rows/counts;
        successful categories reflect only the second load
```

### C. Existing user state

Prove the selected process/Inspector restoration path still runs after a successful reload. Preserve existing state tests where available; do not build a broad new browser framework.

Run:

- the new focused frontend regression test;
- existing CT-8D1 frontend/static tests;
- the smallest existing Control Tower frontend regressions affected by the file;
- `git diff --check`.

Run Python tests only if Python files unexpectedly need modification; normally they should not.

Rendered screenshots do not need to be regenerated when markup/CSS are unchanged. Perform one quick browser smoke check only when the existing safe local harness is immediately available; do not turn this correction into another visual-design run.

## 6. Acceptance criteria

Pass when:

- repeated refresh reloads cannot accumulate visible process counts;
- failed category reloads cannot retain old evidence as current;
- partial and unavailable states remain truthful;
- selected node/Inspector restoration remains intact;
- no backend, migration, visual redesign, or unrelated change was introduced;
- focused deterministic tests pass;
- no real Odoo, office-pilot, or production access occurred.

## 7. Commit and push

After implementation, focused validation, and self-review:

1. create exactly one new commit on `feat/control-tower-refresh-center`;
2. commit message:

   `fix(control-tower): replace evidence state on refresh`

3. include a concise body with:
   - `Task: CT-8D1-R1`;
   - base SHA;
   - changed files;
   - repeated-reload and partial-failure tests;
   - confirmation that no backend/API/schema/visual scope changed;
   - confirmation of zero real Odoo/office-pilot/production access;
4. push normally;
5. do not amend, rebase, merge, force-push, or open a PR;
6. verify local HEAD equals remote branch SHA;
7. leave only the four protected backup paths untracked.

## 8. Final report and stop

Report briefly:

1. what normal user-visible error was fixed;
2. exact changed files;
3. proof that `3 → 2` results in `2`, not `5`;
4. proof that a later failed category does not retain its old evidence;
5. selected process/Inspector preservation result;
6. tests run and results;
7. commit and remote SHA;
8. final git status;
9. narrow readiness claim: ready for owner review of CT-8D1, not live Odoo validated.

Stop after the push. Do not start another correction or next capability.