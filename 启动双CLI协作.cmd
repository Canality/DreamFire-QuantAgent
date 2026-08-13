@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0output\bridge_runtime\start-track2-collaboration.ps1"
if errorlevel 1 (
  echo.
  echo Track 2 collaboration launcher failed. Press any key to close.
  pause >nul
)
endlocal
