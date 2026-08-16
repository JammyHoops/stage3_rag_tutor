@echo off
REM Double-click entry point — see scripts\stop.ps1 for the real logic.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
echo.
pause
