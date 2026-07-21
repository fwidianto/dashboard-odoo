[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$PreferredPort = 8000,
    [ValidateRange(5, 120)]
    [int]$TimeoutSeconds = 35,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$workspaceRoot = Split-Path -Parent $repositoryRoot
$configurationRepository = Join-Path $workspaceRoot 'dashboard-odoo'
$pythonPath = Join-Path $configurationRepository 'venv\Scripts\python.exe'
$environmentPath = Join-Path $configurationRepository '.env'
$runtimeDirectory = Join-Path $repositoryRoot 'output\control-tower-runtime'
$pidPath = Join-Path $runtimeDirectory 'server.json'
$portPath = Join-Path $runtimeDirectory 'port.txt'
$launcherLogPath = Join-Path $runtimeDirectory 'launcher.log'
$requiredPostgresVariables = @('POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')

function Write-LauncherStatus {
    param([string]$Message)
    Write-Host "[Control Tower] $Message"
}

function Write-LauncherLog {
    param([string]$Event, [Nullable[int]]$Port)
    $entry = "{0}`t{1}" -f ([DateTime]::UtcNow.ToString('o')), $Event
    if ($null -ne $Port) { $entry += "`tport=$Port" }
    Add-Content -LiteralPath $launcherLogPath -Value $entry -Encoding UTF8
}

function Read-EnvironmentFile {
    param([string]$Path)
    $values = @{}
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { continue }
        $key = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }
    return $values
}

function Test-TcpEndpoint {
    param([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds = 1800)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return $task.Wait($TimeoutMilliseconds) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-ControlTowerHealth {
    param([int]$Port)
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/control-tower/health" -TimeoutSec 3
        return $response.application -eq 'control-tower' -and $response.status -eq 'READY' -and $response.read_only -eq $true
    } catch {
        return $false
    }
}

function Get-LauncherProcessState {
    param([object]$Record)
    if (-not $Record -or -not $Record.pid -or -not $Record.port -or -not $Record.startedAt) {
        return [pscustomobject]@{ Status = 'invalid'; Process = $null }
    }
    if ($Record.repositoryRoot -ne $repositoryRoot -or $Record.executable -ne $pythonPath) {
        return [pscustomobject]@{ Status = 'different'; Process = $null }
    }
    try {
        $process = Get-Process -Id ([int]$Record.pid) -ErrorAction Stop
        $expectedStart = [DateTime]::Parse([string]$Record.startedAt).ToUniversalTime()
        $actualStart = $process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -gt 2 -or $process.Path -ne $pythonPath) {
            return [pscustomobject]@{ Status = 'different'; Process = $null }
        }
    } catch {
        return [pscustomobject]@{ Status = 'missing'; Process = $null }
    }

    try {
        $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction Stop).CommandLine
        if ([string]::IsNullOrWhiteSpace($commandLine)) {
            return [pscustomobject]@{ Status = 'inconclusive'; Process = $null }
        }
    } catch {
        return [pscustomobject]@{ Status = 'inconclusive'; Process = $null }
    }

    if ($commandLine -notmatch 'uvicorn' -or $commandLine -notmatch 'src\.api:app' -or $commandLine -notmatch "--port\s+$([int]$Record.port)(\s|$)") {
        return [pscustomobject]@{ Status = 'different'; Process = $null }
    }
    return [pscustomobject]@{ Status = 'owned'; Process = $process }
}

function Open-ControlTower {
    param([int]$Port)
    if ($NoBrowser) { return }
    $url = "http://127.0.0.1:$Port/control-tower"
    $edge = Get-Command msedge.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $edge) {
        $edgeCandidates = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
            (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
        )
        $edge = $edgeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    }
    if ($edge) {
        Start-Process -FilePath $edge -ArgumentList "--app=$url"
        Write-LauncherStatus 'Dibuka dalam Microsoft Edge app mode.'
    } else {
        Start-Process $url
        Write-LauncherStatus 'Microsoft Edge tidak ditemukan; dibuka dengan browser default.'
    }
}

New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Python interpreter yang diwajibkan tidak ditemukan.'
}
if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
    throw 'File .env repository utama tidak ditemukan.'
}

$environmentValues = Read-EnvironmentFile -Path $environmentPath
$missingVariables = $requiredPostgresVariables | Where-Object { -not $environmentValues.ContainsKey($_) -or [string]::IsNullOrWhiteSpace([string]$environmentValues[$_]) }
if ($missingVariables) {
    throw "Konfigurasi PostgreSQL belum lengkap. Variabel yang perlu diisi: $($missingVariables -join ', ')."
}

$databasePort = 0
if (-not [int]::TryParse([string]$environmentValues.POSTGRES_PORT, [ref]$databasePort) -or $databasePort -lt 1 -or $databasePort -gt 65535) {
    throw 'POSTGRES_PORT tidak valid.'
}
Write-LauncherStatus 'Python dan konfigurasi PostgreSQL tervalidasi; nilai rahasia tidak ditampilkan.'

if (-not (Test-TcpEndpoint -HostName ([string]$environmentValues.POSTGRES_HOST) -Port $databasePort)) {
    throw 'PostgreSQL tidak dapat dijangkau. Server tidak dijalankan.'
}
Write-LauncherStatus 'PostgreSQL dapat dijangkau.'

if ($CheckOnly) {
    Write-LauncherLog -Event 'configuration-check-passed' -Port $null
    Write-LauncherStatus 'Pemeriksaan konfigurasi selesai.'
    exit 0
}

if (Test-Path -LiteralPath $pidPath) {
    try { $existingRecord = Get-Content -Raw -LiteralPath $pidPath | ConvertFrom-Json } catch { $existingRecord = $null }
    $processState = Get-LauncherProcessState -Record $existingRecord
    if ($processState.Status -eq 'owned') {
        $ownedPort = [int]$existingRecord.port
        if (Get-ControlTowerHealth -Port $ownedPort) {
            Set-Content -LiteralPath $portPath -Value $ownedPort -Encoding ASCII
            Write-LauncherLog -Event 'reused-launcher-process' -Port $ownedPort
            Write-LauncherStatus "Instance launcher yang sehat digunakan kembali pada port $ownedPort."
            Open-ControlTower -Port $ownedPort
            exit 0
        }
        throw 'Proses milik launcher masih berjalan tetapi health check gagal. Jalankan stop-control-tower.cmd sebelum mencoba lagi.'
    }
    if ($processState.Status -eq 'inconclusive') {
        Write-LauncherLog -Event 'identity-check-inconclusive' -Port ([int]$existingRecord.port)
        throw 'Identitas proses belum dapat diverifikasi. State launcher dipertahankan; tidak ada proses yang dihentikan atau diklaim.'
    }
    Remove-Item -LiteralPath $pidPath -Force
    Write-LauncherLog -Event 'stale-pid-removed' -Port $null
    Write-LauncherStatus 'PID file stale dihapus tanpa menghentikan proses lain.'
}

$selectedPort = $PreferredPort
if (Test-TcpEndpoint -HostName '127.0.0.1' -Port $selectedPort -TimeoutMilliseconds 350) {
    if (Get-ControlTowerHealth -Port $selectedPort) {
        Set-Content -LiteralPath $portPath -Value $selectedPort -Encoding ASCII
        Write-LauncherLog -Event 'reused-external-control-tower' -Port $selectedPort
        Write-LauncherStatus "Control Tower yang sehat digunakan kembali pada port $selectedPort; proses tidak diklaim oleh launcher."
        Open-ControlTower -Port $selectedPort
        exit 0
    }
    $fallbackCandidates = if ($PreferredPort -lt 65535) {
        ($PreferredPort + 1)..([Math]::Min(65535, $PreferredPort + 10))
    } else {
        @()
    }
    $fallbackPort = $fallbackCandidates | Where-Object { -not (Test-TcpEndpoint -HostName '127.0.0.1' -Port $_ -TimeoutMilliseconds 250) } | Select-Object -First 1
    if (-not $fallbackPort) { throw 'Port utama digunakan aplikasi lain dan tidak ada fallback port aman yang tersedia.' }
    Write-LauncherStatus "Port $PreferredPort digunakan aplikasi lain; fallback non-destruktif dipilih."
    $selectedPort = [int]$fallbackPort
}

$arguments = @(
    '-m', 'uvicorn', 'src.api:app',
    '--host', '127.0.0.1',
    '--port', [string]$selectedPort,
    '--env-file', $environmentPath,
    '--log-level', 'warning',
    '--no-access-log'
)
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $repositoryRoot -PassThru -WindowStyle Hidden
$serverProcess.Refresh()
$record = [ordered]@{
    pid = $serverProcess.Id
    port = $selectedPort
    executable = $pythonPath
    repositoryRoot = $repositoryRoot
    startedAt = $serverProcess.StartTime.ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding UTF8
Set-Content -LiteralPath $portPath -Value $selectedPort -Encoding ASCII
Write-LauncherLog -Event 'server-started' -Port $selectedPort
Write-LauncherStatus "Server dimulai pada port $selectedPort; menunggu health check."

$stopwatch = [Diagnostics.Stopwatch]::StartNew()
while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    if ($serverProcess.HasExited) { break }
    if (Get-ControlTowerHealth -Port $selectedPort) {
        Write-LauncherLog -Event 'health-ready' -Port $selectedPort
        Write-LauncherStatus 'Health check Control Tower berhasil.'
        Open-ControlTower -Port $selectedPort
        exit 0
    }
    Start-Sleep -Milliseconds 500
    $serverProcess.Refresh()
}

$failureProcessState = Get-LauncherProcessState -Record ([pscustomobject]$record)
if ($failureProcessState.Status -eq 'owned') {
    Stop-Process -Id $failureProcessState.Process.Id
    $failureProcessState.Process.WaitForExit(5000) | Out-Null
} elseif ($failureProcessState.Status -eq 'inconclusive') {
    Write-LauncherLog -Event 'health-timeout-identity-inconclusive' -Port $selectedPort
    throw 'Health check gagal dan identitas proses belum dapat diverifikasi. State launcher dipertahankan; tidak ada proses yang dihentikan.'
}
Remove-Item -LiteralPath $pidPath,$portPath -Force -ErrorAction SilentlyContinue
Write-LauncherLog -Event 'health-timeout' -Port $selectedPort
throw 'Control Tower tidak mencapai status READY dalam batas waktu; proses launcher telah dihentikan.'
