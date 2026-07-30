[CmdletBinding()]
param(
    [string]$Url = 'http://127.0.0.1:8000/dashboard/control-tower',
    [string]$ChromePath,
    [string]$ProfileDirectory
)

$ErrorActionPreference = 'Stop'
if (-not $ChromePath) {
    $ChromePath = Join-Path ${env:ProgramFiles} 'Google\Chrome\Application\chrome.exe'
}
if (-not $ProfileDirectory) {
    $ProfileDirectory = Join-Path $env:TEMP 'control-tower-office-pilot-chrome'
}
if (-not (Test-Path -LiteralPath $ChromePath)) { throw "Chrome executable not found: $ChromePath" }
New-Item -ItemType Directory -Force -Path $ProfileDirectory | Out-Null
$arguments = @('--kiosk', '--no-first-run', '--disable-session-crashed-bubble', "--user-data-dir=$ProfileDirectory", $Url)
Start-Process -FilePath $ChromePath -ArgumentList $arguments -WindowStyle Hidden | Out-Null
Write-Output "Control Tower kiosk opened at $Url."
