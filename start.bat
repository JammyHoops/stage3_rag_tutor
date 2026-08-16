@echo off
REM Double-click entry point — see scripts\start.ps1 for the real logic.
REM A .bat file is used here (not a bare .ps1) because Windows' default
REM execution policy often blocks .ps1 from running on double-click.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
echo.
pause
