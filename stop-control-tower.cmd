@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-control-tower.ps1" %*
if errorlevel 1 pause
endlocal
