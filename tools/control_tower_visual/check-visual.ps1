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

$Baseline = Join-Path $RepoRoot "tests\visual\control-tower\baseline"
if (-not (Test-Path $Baseline)) { throw "Baseline not found. Run capture-baseline.ps1 first." }

$ArtifactRoot = Join-Path $RepoRoot "artifacts\control-tower-visual"
$Current = Join-Path $ArtifactRoot "current"
$Diff = Join-Path $ArtifactRoot "diff"
$Report = Join-Path $ArtifactRoot "VISUAL_REGRESSION_REPORT.md"

Push-Location $RepoRoot
try {
    Remove-Item $Current -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $Diff -Recurse -Force -ErrorAction SilentlyContinue
    & $Python (Join-Path $PSScriptRoot "capture.py") --output $Current
    if ($LASTEXITCODE -ne 0) { throw "Current screenshot capture failed." }

    & $Python (Join-Path $PSScriptRoot "compare.py") --baseline $Baseline --current $Current --diff $Diff --report $Report
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Visual differences were detected. Review: $Report"
        exit 1
    }
    Write-Host "Visual regression passed. Report: $Report" -ForegroundColor Green
}
finally {
    Pop-Location
}
