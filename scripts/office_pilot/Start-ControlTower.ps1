[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$PythonPath,
    [string]$Host = '127.0.0.1',
    [int]$Port = 8000,
    [string]$LogDirectory,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $PythonPath) { $PythonPath = Join-Path $ProjectRoot 'venv\Scripts\python.exe' }
if (-not $LogDirectory) { $LogDirectory = Join-Path $ProjectRoot 'logs\office-pilot' }
$pidPath = Join-Path $LogDirectory 'control-tower.pid'
$stdoutPath = Join-Path $LogDirectory 'control-tower-stdout.log'
$stderrPath = Join-Path $LogDirectory 'control-tower-stderr.log'

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python executable not found: $PythonPath" }
if (Test-Path -LiteralPath $pidPath) {
    $existingId = [int](Get-Content -Raw -LiteralPath $pidPath)
    $existing = Get-Process -Id $existingId -ErrorAction SilentlyContinue
    if ($existing) { Write-Output "Control Tower already running with PID $existingId."; exit 0 }
    Remove-Item -LiteralPath $pidPath -Force
}

$arguments = @('-m', 'uvicorn', 'src.api:app', '--host', $Host, '--port', [string]$Port)
if ($Foreground) {
    Push-Location $ProjectRoot
    try {
        & $PythonPath @arguments 2>&1 | Tee-Object -FilePath $stdoutPath
        $exitCode = $LASTEXITCODE
    } finally { Pop-Location }
    exit $exitCode
}

$process = Start-Process -FilePath $PythonPath -ArgumentList $arguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $pidPath -Value ([string]$process.Id) -NoNewline
Write-Output "Control Tower started with PID $($process.Id). Logs: $LogDirectory"
