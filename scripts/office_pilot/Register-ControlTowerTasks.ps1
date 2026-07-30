[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$PythonPath,
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$RefreshTime = '07:30',
    [string]$TaskUser = 'SYSTEM',
    [string]$TaskNamePrefix = 'OdooControlTowerOfficePilot'
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $PythonPath) { $PythonPath = Join-Path $ProjectRoot 'venv\Scripts\python.exe' }
$powerShell = (Get-Command powershell.exe).Source
$startScript = Join-Path $PSScriptRoot 'Start-ControlTower.ps1'
$refreshScript = Join-Path $PSScriptRoot 'Run-ControlTowerRefresh.ps1'
$startArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -ProjectRoot `"$ProjectRoot`" -PythonPath `"$PythonPath`""
$refreshArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$refreshScript`" -ProjectRoot `"$ProjectRoot`" -PythonPath `"$PythonPath`" -Trigger scheduled -RequestedBy scheduler"
$principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType ServiceAccount -RunLevel Highest
$startupAction = New-ScheduledTaskAction -Execute $powerShell -Argument $startArgs -WorkingDirectory $ProjectRoot
$refreshAction = New-ScheduledTaskAction -Execute $powerShell -Argument $refreshArgs -WorkingDirectory $ProjectRoot
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$refreshAt = [DateTime]::Today.Add([TimeSpan]::Parse($RefreshTime))
$refreshTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $refreshAt
Register-ScheduledTask -TaskName "$TaskNamePrefix-Startup" -Action $startupAction -Trigger $startupTrigger -Principal $principal -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskNamePrefix-WeekdayRefresh" -Action $refreshAction -Trigger $refreshTrigger -Principal $principal -Force | Out-Null
Write-Output "Registered startup and Monday-Friday $RefreshTime refresh tasks for $TaskUser."
