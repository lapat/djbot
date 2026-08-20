@echo off
rem DJ Kyoko — double-click launcher for Windows.
rem This just hands off to the real logic in "DJ Kyoko.ps1" (PowerShell is
rem far less error-prone than batch for the install/download steps below).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DJ Kyoko.ps1"
echo.
pause
