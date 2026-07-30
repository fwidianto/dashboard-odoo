[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$PythonPath,
    [ValidateSet('manual', 'scheduled', 'recovery')]
    [string]$Trigger = 'manual',
    [string]$RequestedBy = 'office-admin',
    [int]$BatchSize = 500,
    [string]$LogDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $PythonPath) { $PythonPath = Join-Path $ProjectRoot 'venv\Scripts\python.exe' }
if (-not $LogDirectory) { $LogDirectory = Join-Path $ProjectRoot 'logs\office-pilot' }
$refreshScript = Join-Path $ProjectRoot 'scripts\run_control_tower_refresh.py'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python executable not found: $PythonPath" }
if (-not (Test-Path -LiteralPath $refreshScript)) { throw "Refresh script not found: $refreshScript" }
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $LogDirectory "refresh-$stamp.log"
$env:PYTHONIOENCODING = 'utf-8'
$arguments = @($refreshScript, '--company-id', '3', '--batch-size', [string]$BatchSize, '--requested-by', $RequestedBy, '--trigger', $Trigger)
Push-Location $ProjectRoot
try {
    & $PythonPath @arguments 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
} finally { Pop-Location }
if ($exitCode -ne 0) { Write-Error "Control Tower refresh failed. Review $logPath." }
exit $exitCode
