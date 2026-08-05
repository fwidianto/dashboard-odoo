# Windows Office Pilot Administrator Runbook

This runbook operates one read-only Control Tower instance for company `3` (PT Nobi Putra Angkasa). It is a template until the office host is designated.

## Before starting

Confirm the host URL, service account, Odoo read-only credentials, PostgreSQL target, backup/rollback point, and an owner-approved maintenance window. Do not start the pilot from a developer workstation.

## Start, stop, and restart

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Start-ControlTower.ps1 -ProjectRoot 'C:\OfficePilot\dashboard-odoo'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Stop-ControlTower.ps1 -ProjectRoot 'C:\OfficePilot\dashboard-odoo'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Restart-ControlTower.ps1 -ProjectRoot 'C:\OfficePilot\dashboard-odoo'
```

Expected result: the launcher reports a PID, writes `logs\office-pilot\`, and leaves the existing trusted snapshot untouched until a safe refresh succeeds.

## Check health and freshness

1. Run `Test-ControlTowerHealth.ps1` and expect HTTP 200 from `/health`.
2. Open the authenticated Control Tower and confirm the banner shows one of `CURRENT`, `STALE`, `CRITICALLY_STALE`, `REFRESHING`, or `FAILED`.
3. Confirm the trusted completion timestamp is visible. A service failure is not an empty finding result.

## Trigger a manual refresh

Use the administrator wrapper only after confirming no refresh is active:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Run-ControlTowerRefresh.ps1 `
  -ProjectRoot 'C:\OfficePilot\dashboard-odoo' -RequestedBy 'office-admin' -Trigger manual
```

Expected result: the run is serialized, the candidate remains separate until the full safe pipeline succeeds, SQL validation/publication runs, and the trusted pointer is promoted atomically. Odoo remains read-only.

## Owner staging test — Phase 3 real incremental Refresh Data

This section is the exact controlled staging test for the incremental refresh
capability (CT-8E1). Run it on the staging host with company 3 after this
implementation commit is installed.

### 0. Confirm the new implementation is active

1. Confirm the deployed commit is the incremental implementation commit
   (`feat(control-tower): complete incremental refresh path`).
2. Confirm the application uses the normal incremental coordinator: pressing
   `Refresh Data` must create a durable run and never run the 2–3 hour full
   approved-dataset extraction. The full extractor remains maintenance-only
   through the explicit CLI.

### 1. Confirm trusted snapshot and watermarks are ready

1. Open the authenticated Control Tower and confirm the trusted snapshot
   timestamp and company-3 scope are visible.
2. If Phase 3 watermarks are not yet READY, run the explicit adoption
   operation once (administrator action, not an ordinary-refresh fallback):

   ```powershell
   & .\venv\Scripts\python.exe scripts\bootstrap_control_tower_watermarks.py `
     --company-id 3
   ```

   Expected: the command reports `pointer_moved: false` and `odoo_contacted:
   false`, and marks the approved models READY. It must not contact Odoo and
   must not move the trusted pointer. If it reports missing evidence, stop and
   report the exact missing approved model evidence instead of inventing a
   watermark.

### 2. Baseline

1. Note one existing Sales Order and its current visible evidence in Control
   Tower (e.g. document number, Temuan category, and Process Map badge).

### 3. Make one harmless staging-only change

1. In the approved staging Odoo only, make one harmless Sales Order change,
   for example edit a non-material field on the Sales Order (and its line if
   required) that does not affect any business decision.
2. Do not change payment, profitability, or company scope.

### 4. Run Refresh Data and observe progress

1. Press `Refresh Data`.
2. Confirm the progress panel stays minimizable and the user can keep using
   the page.
3. Confirm the previous trusted evidence remains visible while the refresh
   runs.
4. Confirm progress is truthful (stage, model, counts, elapsed) and is not a
   fabricated fixed number.

### 5. Verify safe publication

1. Wait for success.
2. Confirm changed evidence appears only after successful publication.
3. Confirm the exact Sales Order evidence and the trusted timestamp updated
   after success.
4. Confirm the reported changed/new/missing counts match what was changed.
5. Confirm the trusted pointer advanced only after all stages succeeded.

### 6. Verify a no-change refresh

1. Press `Refresh Data` again without making another Odoo change.
2. Confirm the result is a truthful no-change outcome (`Tidak ada perubahan`
   / equivalent) and the trusted snapshot is not replaced.
3. Record both durations (changed refresh and no-change refresh).

### 7. Verify Odoo remained read-only

1. Confirm the Control Tower performed no Odoo write during the test.
2. If a failure is induced during staging, confirm the previous trusted
   snapshot and successful watermarks remain unchanged and the failed stage is
   named in plain language.

## Inspect logs and recover

- Application stdout/stderr: `logs\office-pilot\control-tower-stdout.log` and `control-tower-stderr.log`.
- Refresh output: timestamped files under `logs\office-pilot\refresh-*.log`.
- A failed refresh must leave the previous trusted snapshot displayed. Capture the failure timestamp, run ID, sanitized message, and stage timings.
- Recover a stale candidate only through the existing explicit recovery command after its age and company-3 scope are verified:

```powershell
& .\venv\Scripts\python.exe scripts\recover_control_tower_refresh.py `
  --run-id '<candidate-run-id>' --requested-by 'office-admin' `
  --reason 'Administrator recovery after host interruption'
```

Do not delete evidence rows and do not manually mark a candidate complete.

## Restore the office display

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Open-ControlTowerKiosk.ps1 `
  -Url 'http://127.0.0.1:8000/dashboard/control-tower'
```

The shared display returns to the default overview after two minutes of inactivity. Users can temporarily focus the Process Map, but the kiosk must not retain one user’s selected finding indefinitely.

## Rollback procedure

1. Stop the application task and close the kiosk browser.
2. Preserve the current `logs\office-pilot\` directory and record the current commit/version.
3. Restore the last owner-approved dashboard-odoo working copy or deployment package; do not use `git reset --hard` on an unclassified worktree.
4. Restore only the approved database schema/read-model version if the release explicitly changed it. Do not overwrite the trusted snapshot with an unverified candidate.
5. Start the application, run the process health check, and inspect the authenticated Control Tower freshness banner.
6. If the trusted snapshot or company isolation cannot be proven, stop the pilot and escalate.

Rollback is a deployment action for the designated host; no rollback is executed by local implementation validation.

## Stop and escalate when

- the health endpoint is unavailable after a bounded restart attempt;
- the Control Tower cannot show a trusted timestamp or company-3 scope;
- a refresh reports success without a completed/published run and reconciled counts;
- a failed run would replace or obscure the last trusted snapshot;
- credentials, write capability, cross-company data, or unexplained process destinations appear;
- the display is clipped, unreadable, or requires essential horizontal scrolling.
