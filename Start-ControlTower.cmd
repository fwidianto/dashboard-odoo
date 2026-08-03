@echo off
setlocal
set "ProjectRoot=%~dp0."
set "PowerShell=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "Url=http://127.0.0.1:8000/dashboard/control-tower"
set "HealthUrl=http://127.0.0.1:8000/health"

"%PowerShell%" -NoProfile -ExecutionPolicy Bypass -File "%ProjectRoot%\scripts\office_pilot\Start-ControlTower.ps1" -ProjectRoot "%ProjectRoot%"
if errorlevel 1 goto :error
for /L %%N in (1,1,30) do (
    "%PowerShell%" -NoProfile -ExecutionPolicy Bypass -File "%ProjectRoot%\scripts\office_pilot\Test-ControlTowerHealth.ps1" -Url "%HealthUrl%" >nul 2>&1
    if not errorlevel 1 goto :open
    "%PowerShell%" -NoProfile -Command Start-Sleep -Seconds 1
)
echo Control Tower did not become ready at %Url%.
goto :error

:open
start "" "%Url%"
exit /b 0

:error
echo Start failed. Inspect logs\office-pilot\control-tower-*.log.
pause
exit /b 1
