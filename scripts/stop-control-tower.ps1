[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$workspaceRoot = Split-Path -Parent $repositoryRoot
$pythonPath = Join-Path (Join-Path $workspaceRoot 'dashboard-odoo') 'venv\Scripts\python.exe'
$runtimeDirectory = Join-Path $repositoryRoot 'output\control-tower-runtime'
$pidPath = Join-Path $runtimeDirectory 'server.json'
$portPath = Join-Path $runtimeDirectory 'port.txt'
$launcherLogPath = Join-Path $runtimeDirectory 'launcher.log'

function Remove-StaleLauncherState {
    Remove-Item -LiteralPath $pidPath,$portPath -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $runtimeDirectory) {
        Add-Content -LiteralPath $launcherLogPath -Value "$( [DateTime]::UtcNow.ToString('o') )`tstale-state-removed" -Encoding UTF8
    }
}

if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    Write-Host '[Control Tower] Tidak ada proses milik launcher yang tercatat.'
    exit 0
}

try { $record = Get-Content -Raw -LiteralPath $pidPath | ConvertFrom-Json } catch {
    Remove-StaleLauncherState
    Write-Host '[Control Tower] PID file tidak valid dan sudah dibersihkan; tidak ada proses yang dihentikan.'
    exit 0
}

if (-not $record.pid -or -not $record.port -or -not $record.startedAt -or $record.repositoryRoot -ne $repositoryRoot -or $record.executable -ne $pythonPath) {
    Remove-StaleLauncherState
    Write-Host '[Control Tower] PID file bukan milik launcher saat ini dan sudah dibersihkan; tidak ada proses yang dihentikan.'
    exit 0
}

try { $process = Get-Process -Id ([int]$record.pid) -ErrorAction Stop } catch {
    Remove-StaleLauncherState
    Write-Host '[Control Tower] PID file stale sudah dibersihkan.'
    exit 0
}

$expectedStart = [DateTime]::Parse([string]$record.startedAt).ToUniversalTime()
$actualStart = $process.StartTime.ToUniversalTime()
$commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction Stop).CommandLine
$identityMatches = (
    $process.Path -eq $pythonPath -and
    [Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -le 2 -and
    $commandLine -match 'uvicorn' -and
    $commandLine -match 'src\.api:app' -and
    $commandLine -match "--port\s+$([int]$record.port)(\s|$)"
)

if (-not $identityMatches) {
    Remove-StaleLauncherState
    throw 'PID sekarang dimiliki proses lain. Proses tersebut tidak dihentikan.'
}

Stop-Process -Id $process.Id
$process.WaitForExit(8000) | Out-Null
if (-not $process.HasExited) { throw 'Proses milik launcher belum berhenti; state kepemilikan dipertahankan.' }

Remove-Item -LiteralPath $pidPath,$portPath -Force -ErrorAction SilentlyContinue
Add-Content -LiteralPath $launcherLogPath -Value "$( [DateTime]::UtcNow.ToString('o') )`tserver-stopped`tport=$([int]$record.port)" -Encoding UTF8
Write-Host '[Control Tower] Server milik launcher telah dihentikan.'
