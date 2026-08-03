$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path (Join-Path $RepoRoot "src") -PathType Container)) {
    throw "Could not resolve dashboard-odoo repository root from script location: $RepoRoot"
}
$Python = @(
    (Join-Path $RepoRoot "venv\Scripts\python.exe"),
    (Join-Path $RepoRoot ".venv\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $Python) {
    throw "Repository Python interpreter not found. Expected $RepoRoot\venv\Scripts\python.exe or $RepoRoot\.venv\Scripts\python.exe"
}

Push-Location $RepoRoot
try {
    & $Python -c "import playwright, PIL" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing visual-test dependencies into the repository venv..."
        & $Python -m pip install playwright==1.61.0 pillow==12.3.0
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    }

    $Output = Join-Path $RepoRoot "tests\visual\control-tower\baseline"
    & $Python (Join-Path $PSScriptRoot "capture.py") --output $Output
    if ($LASTEXITCODE -ne 0) { throw "Baseline capture failed." }
    Write-Host "Baseline screenshots created at: $Output" -ForegroundColor Green
}
finally {
    Pop-Location
}
