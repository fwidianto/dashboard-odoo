[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$LogDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $LogDirectory) { $LogDirectory = Join-Path $ProjectRoot 'logs\office-pilot' }
$pidPath = Join-Path $LogDirectory 'control-tower.pid'
if (-not (Test-Path -LiteralPath $pidPath)) { Write-Output 'No recorded Control Tower PID; nothing to stop.'; exit 0 }

$processId = [int](Get-Content -Raw -LiteralPath $pidPath)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $processId -ErrorAction Stop
    if (-not $process.WaitForExit(10000)) { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue }
    Write-Output "Control Tower stopped: PID $processId."
} else { Write-Output "Recorded Control Tower PID $processId is not running." }
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
