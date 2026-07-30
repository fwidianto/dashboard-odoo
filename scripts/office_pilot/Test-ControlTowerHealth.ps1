[CmdletBinding()]
param(
    [string]$Url = 'http://127.0.0.1:8000/health',
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = 'Stop'
try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    $payload = $response.Content | ConvertFrom-Json
    $payload | ConvertTo-Json -Depth 5
    if ($response.StatusCode -ne 200) { exit 1 }
} catch {
    Write-Error "Control Tower process health failed: $($_.Exception.Message)"
    exit 1
}
