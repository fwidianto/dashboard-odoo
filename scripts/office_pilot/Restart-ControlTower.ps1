[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$PythonPath,
    [string]$HostAddress = '127.0.0.1',
    [int]$Port = 8000,
    [string]$LogDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$stopScript = Join-Path $PSScriptRoot 'Stop-ControlTower.ps1'
$startScript = Join-Path $PSScriptRoot 'Start-ControlTower.ps1'
& $stopScript -ProjectRoot $ProjectRoot -LogDirectory $LogDirectory
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $startScript -ProjectRoot $ProjectRoot -PythonPath $PythonPath -HostAddress $HostAddress -Port $Port -LogDirectory $LogDirectory
exit $LASTEXITCODE
