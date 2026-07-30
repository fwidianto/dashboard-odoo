# Windows Office Pilot Deployment Templates

These are repository-side templates for one owner-designated Windows host. They are not host evidence and must not be run until the host, service account, URL, and approved maintenance window are confirmed.

## Files

- `scripts/office_pilot/Start-ControlTower.ps1` — bounded uvicorn launcher with a PID file and stdout/stderr logs.
- `scripts/office_pilot/Stop-ControlTower.ps1` — stops only the recorded launcher process.
- `scripts/office_pilot/Restart-ControlTower.ps1` — stop then start using the same configured root.
- `scripts/office_pilot/Run-ControlTowerRefresh.ps1` — administrator/scheduler wrapper for the company-3 safe refresh command.
- `scripts/office_pilot/Test-ControlTowerHealth.ps1` — unauthenticated process health check for host monitoring.
- `scripts/office_pilot/Open-ControlTowerKiosk.ps1` — Chrome kiosk/display launcher without credentials in the URL.
- `scripts/office_pilot/Register-ControlTowerTasks.ps1` — startup task plus configurable Monday–Friday morning refresh task.

## Configuration boundary

Configure the project root, Python executable, port, stable internal URL, Chrome path, log directory, refresh time, and task account on the designated host. Keep Odoo/PostgreSQL credentials in the host environment or local `.env`; never place them in these scripts or task arguments.

The refresh wrapper is deliberately explicit about `company_id=3` and uses the existing safe refresh pipeline. It does not claim incremental behavior. The benchmark remains a separate host-gated command:

```powershell
& .\venv\Scripts\python.exe scripts\benchmark_control_tower_refresh.py --company-id 3 --runs 3 --confirm-host-preconditions
```

Run that benchmark only after all frozen safety preconditions are proven on the actual pilot host. Until then it is `PENDING_HOST`.

## Registration example — do not run locally as a test

After host approval, an administrator may register the startup and working-day schedule:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Register-ControlTowerTasks.ps1 `
  -ProjectRoot 'C:\OfficePilot\dashboard-odoo' `
  -RefreshTime '07:30' `
  -TaskUser 'SYSTEM'
```

The schedule is Monday through Friday, once each morning, in the host’s local time. The task registration itself is host deployment work, not local validation.

## Manual administrator path

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Run-ControlTowerRefresh.ps1 `
  -ProjectRoot 'C:\OfficePilot\dashboard-odoo' `
  -RequestedBy 'office-admin' `
  -Trigger manual
```

The command is not an ordinary-user capability. It must be run only by an approved administrator and only inside the read-only, company-3 boundary.

## Display and health paths

Process health, without Control Tower data access:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Test-ControlTowerHealth.ps1 -Url 'http://127.0.0.1:8000/health'
```

Open the authenticated display session after login:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\office_pilot\Open-ControlTowerKiosk.ps1 `
  -Url 'http://127.0.0.1:8000/dashboard/control-tower'
```

The authenticated `/api/control-tower/health` endpoint is the operator check for trusted snapshot freshness and refresh state.
