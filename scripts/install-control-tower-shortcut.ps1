[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$launcherPath = Join-Path $repositoryRoot 'start-control-tower.cmd'
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw 'Launcher start-control-tower.cmd tidak ditemukan.'
}

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Control Tower.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $repositoryRoot
$shortcut.Description = 'Buka Control Tower Operasional'
$edge = Get-Command msedge.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if ($edge) { $shortcut.IconLocation = "$edge,0" }
$shortcut.Save()

Write-Host "Shortcut Control Tower dibuat di Desktop."
