# CT-8D1 — Visible Refresh Data Vertical Slice

## Task metadata

- **Task ID:** CT-8D1
- **Capability:** User-visible Control Tower data freshness and refresh experience
- **Target repository:** `fwidianto/dashboard-odoo`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Accepted implementation base:** `fa4809f3e3435d1976b3720703630548f532239c`
- **Complexity:** 3/5
- **Expected runtime:** 2–4 hours; stop rather than broadening scope
- **Run-plan position:** substantive Run 8; this run must deliver visible owner-reviewable behavior

Use `$stabilize-odoo-control-tower`.

## 1. User promise

> An administrator can open the Control Tower, understand when the displayed trusted data was last refreshed, click **Refresh Data**, follow truthful progress, receive a clear success or failure result, and continue seeing the last trusted snapshot if the refresh fails.

This is a product-facing vertical slice. Lead with the user experience, not backend completeness.

## 2. Mandatory authority and repository preflight

Before editing, freshly read:

1. repository `AGENTS.md`;
2. `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md` from `origin/codex-prompts` using `git show`;
3. `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PILOT_FIRST_DELIVERY_GUARDRAILS.md` if locally available or through the supplied project context;
4. `docs/08_Control_Tower/INCREMENTAL_PRODUCTION_ROADMAP.md`;
5. the existing Control Tower route, refresh API, service/health projection, refresh coordinator, frontend assets, and tests.

Then:

- fetch remotes;
- check out `feat/control-tower-refresh-center`;
- confirm HEAD is exactly `fa4809f3e3435d1976b3720703630548f532239c`;
- confirm upstream tracking is intact;
- confirm no unrelated tracked changes exist;
- preserve the four protected backup paths without modifying or deleting them:
  - `.phase6-1-backup/`
  - `.phase6-backup/`
  - `.phase7-1-backup/`
  - `src/static/dashboard/sales-orders.js.phase7-3-backup`

Stop rather than repairing history or absorbing unrelated work.

## 3. Canonical product and visual baseline

The canonical working screen is the existing `/dashboard/control-tower` implementation on the target branch.

Preserve:

- the existing warm-neutral enterprise visual direction;
- the three-panel Control Tower composition;
- Process Map geometry, navigation, animation, and horizontal scrolling;
- Temuan behavior and filters;
- Process Inspector behavior;
- existing authentication and admin-role semantics;
- existing data and finding APIs;
- all accepted Phase 7 visual behavior.

Do not redesign the Control Tower page. Add the refresh experience as a compact, integrated control/panel using the existing design language.

## 4. Reuse-first implementation boundary

Inspect and reuse the existing authenticated refresh path before adding anything:

- `GET /api/control-tower/refresh`;
- `POST /api/control-tower/refresh`;
- current `ControlTowerService.health()` / latest attempt projection;
- current refresh coordinator and trusted snapshot behavior;
- existing frontend state/reload utilities.

This run may make the **smallest adapter changes** needed for truthful user-visible status, but must not create another orchestration system.

### Hard boundary

Do not:

- modify the accepted Phase 8 fetch/apply engine except for an unavoidable import/interface compatibility issue that directly blocks this UI; report and stop before broadening;
- add or edit migrations;
- implement reconciliation, deletion handling, validation, publication redesign, or watermark advancement;
- replace the current refresh execution path with the unfinished incremental orchestrator;
- add Celery, Redis, Temporal, RabbitMQ, WebSockets, or SSE;
- add scheduling, broad history, notifications, or multi-company UI;
- add a new worker/service process;
- redesign reports, Temuan, Process Map, or Inspector;
- contact real Odoo, office-pilot, or production during implementation or tests;
- auto-trigger refresh on page load.

If the current administrator-safe POST refresh path cannot truthfully and safely complete within its existing declared boundary, stop and report the concrete normal-use blocker. Do not invent a second refresh mechanism.

## 5. Required visible experience

### 5.1 Idle/trusted state

On the Control Tower screen, show a compact freshness control with:

- label: **Data terakhir diperbarui**;
- timestamp of the latest trusted successful snapshot, in the existing user locale;
- a truthful fallback when no successful refresh exists;
- a clear indication that the currently displayed data is the trusted snapshot;
- **Refresh Data** action for administrators only;
- non-admin users may see freshness/status but must not see an enabled refresh action.

Do not display fabricated freshness when the database cannot provide it.

### 5.2 Starting refresh

When an administrator selects **Refresh Data**:

- call the existing authenticated POST endpoint;
- handle `202 Accepted` without a full-page reload;
- handle `409` as “refresh already running” rather than a generic failure;
- disable duplicate submission while active;
- open or update the compact refresh panel;
- continue displaying the trusted snapshot.

### 5.3 Progress

Poll the existing status endpoint at a modest interval while active. Do not add streaming infrastructure.

Show only progress supported by durable/current evidence:

- current stage using plain Indonesian business language;
- active model/process when available;
- record/batch counts when available;
- elapsed time when available;
- indeterminate progress when totals are unknown;
- the distinction between the **trusted displayed snapshot** and the **running candidate**.

Do not invent a percentage or claim completion from an in-memory thread alone when durable evidence contradicts it.

Use a compact stage vocabulary such as:

- Menyiapkan pembaruan
- Membaca perubahan dari Odoo
- Memperbarui data kandidat
- Memeriksa hasil
- Menyelesaikan pembaruan
- Selesai
- Gagal

Map labels to actual backend status/stage. Do not force these labels when the evidence does not support them.

### 5.4 Success/no-change

On successful completion:

- show a plain-language success message;
- update the trusted refresh timestamp;
- update freshness/status without a page reload;
- refresh the Control Tower’s affected data through existing fetch/reload hooks;
- preserve the user’s current context;
- represent a truthful no-change outcome distinctly when the API exposes it.

### 5.5 Failure/stale attempt

On failure, the user must see:

> **Pembaruan Odoo gagal. Control Tower tetap menampilkan snapshot terakhir yang berhasil.**

Also show a short sanitized diagnostic when available, without credentials or raw connection information.

The trusted snapshot must stay visible and must not be labelled as newly refreshed.

Handle stale or interrupted attempts truthfully. Do not silently label them successful.

### 5.6 Minimize/reopen

The active or completed refresh panel may be minimized and reopened without losing its current state. Keep this interaction simple and consistent with the existing page; do not build a new notification system.

## 6. Preserve UI state

Refresh polling, success, failure, and data reload must preserve all applicable existing state, including:

- selected Process Map node;
- Process Inspector state;
- Temuan category/filter state;
- map scroll position;
- selected finding/case;
- expanded row;
- active view;
- applicable search/filter values.

Do not solve this with a full-page reload.

Reuse the existing route/state contract. Add only the smallest state capture/restore mechanism where a gap genuinely exists.

## 7. API projection boundary

The frontend must not infer raw database lifecycle meaning independently when a small server-side projection can provide stable user-facing fields.

The existing refresh status response may be extended narrowly to expose values such as:

- `latest_trusted_refresh_at`;
- `displayed_snapshot_run_id`;
- `latest_attempt` status/stage;
- sanitized message;
- durable progress/count values already stored;
- truthful no-change/success/failure indicators;
- administrator refresh availability.

Do not expose credentials, raw environment values, full metadata payloads, or unnecessary internal evidence.

Do not add a new endpoint when the existing refresh endpoint can be extended clearly.

## 8. User states to implement and validate

At minimum:

1. loading freshness status;
2. trusted idle state;
3. administrator versus normal-user state;
4. refresh accepted;
5. refresh already active;
6. progress with known counts;
7. progress with unknown totals;
8. success;
9. no changes, when supported;
10. failure while trusted snapshot remains visible;
11. stale/interrupted attempt;
12. API unavailable/error;
13. no previous successful refresh.

Use concise Indonesian business language. Avoid technical database terminology in the primary UI.

## 9. Validation

Use mocked Odoo and newly created disposable PostgreSQL databases only.

Run the smallest relevant checks first, then the complete focused capability checks.

Required evidence:

### Backend/API

- authenticated GET refresh status;
- administrator POST accepted;
- non-admin POST forbidden;
- unauthenticated behavior;
- duplicate/active refresh conflict;
- trusted timestamp/status projection;
- failure keeps previous trusted snapshot;
- sanitized diagnostic;
- no schema or publication changes introduced by this task.

### Frontend

- deterministic tests for every supported refresh state;
- no duplicate submissions;
- polling starts/stops correctly;
- no fabricated progress;
- success/failure wording;
- admin visibility;
- preservation of Process Map, Inspector, Temuan, scroll, and applicable route state;
- existing Control Tower frontend regressions remain green.

### Rendered browser evidence

Run the application with a safe local fixture/mock boundary and capture browser-rendered screenshots for at least:

1. trusted idle state;
2. refresh in progress;
3. failed refresh while the trusted snapshot remains visible;
4. successful refresh, when the fixture supports it.

Use the existing representative desktop viewport. Add one narrower office/laptop viewport only when the existing responsive harness already supports it cheaply.

Visually compare against the existing approved screen. Stop for owner review rather than completing a materially smaller or visually inconsistent implementation.

### General

- Python compilation/import checks;
- focused Control Tower Python tests;
- relevant PostgreSQL tests with zero PostgreSQL-related skips;
- frontend static/unit tests;
- browser tests;
- `git diff --check`.

Do not repeat broad unrelated test suites solely for numerical coverage.

## 10. Owner review path

The completion report must start with:

1. exact local command to run the app;
2. exact route to open;
3. login role needed to trigger refresh;
4. no more than three owner checks:
   - confirm trusted timestamp and Refresh Data action;
   - trigger/observe progress while the current page state remains intact;
   - confirm success or failure wording and trusted-snapshot behavior;
5. screenshot/artifact paths;
6. narrow readiness claim.

The expected readiness claim is no broader than:

> **User-visible Refresh Data experience implemented and locally behaviorally/visually validated with mocked Odoo and disposable PostgreSQL; ready for owner review, not yet live Odoo validated.**

## 11. Acceptance criteria

The task passes when:

- the Control Tower visibly communicates freshness;
- an administrator can initiate the existing safe refresh path;
- progress and outcomes are truthful and understandable;
- the old trusted snapshot remains visible on failure;
- the latest trusted timestamp updates only after success;
- UI state is preserved without a full-page reload;
- non-admin users cannot initiate refresh;
- no new orchestration architecture or migration was added;
- rendered screenshots demonstrate the states;
- focused tests pass with zero PostgreSQL-related skips;
- no real Odoo/office-pilot/production access occurred.

## 12. Explicitly deferred

Record but do not implement:

- activation of the unfinished Phase 8 incremental pipeline;
- reconciliation/deletion/publication/watermark completion;
- durable multi-run history UI;
- retry-from-specific-stage controls;
- scheduling;
- notifications;
- multi-company selection;
- broad analytics/report UX changes;
- cryptographic/forensic hardening;
- generic cleanup unrelated to this capability.

## 13. Commit and push

After implementation, validation, screenshots, and self-review:

1. create one commit on `feat/control-tower-refresh-center`;
2. commit message:

   `feat(control-tower): add visible refresh experience`

3. include a concise commit body with:
   - `Task: CT-8D1`;
   - base SHA;
   - exact changed files;
   - user-visible outcome;
   - existing refresh path reused;
   - tests and rendered evidence;
   - confirmation of zero real Odoo/office-pilot/production access;
   - explicit deferred scope;
4. push normally;
5. do not amend, rebase, merge, force-push, or open a PR;
6. verify local HEAD equals remote SHA;
7. leave only the four protected backup paths untracked.

## 14. Final report and stop

Return a concise, user-first report containing:

1. user-visible outcome;
2. exact route and login role;
3. three owner review checks;
4. screenshots/artifacts;
5. success/failure/trusted-snapshot behavior;
6. UI state preservation;
7. technical changes;
8. tests and their actual scope;
9. safety confirmations;
10. limitations and findings classified as `BLOCKER`, `MUST DO NOW`, `IMPORTANT LATER`, or `LOW PRIORITY`;
11. commit and remote SHA;
12. final git status.

Stop after the push. Do not start another task or propose another backend correction automatically.
