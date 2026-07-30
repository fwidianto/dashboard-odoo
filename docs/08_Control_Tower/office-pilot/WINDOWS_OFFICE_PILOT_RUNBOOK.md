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
