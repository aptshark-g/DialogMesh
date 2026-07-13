@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - Terminal Dashboard (TUI)
echo ================================================================
echo.
echo 8-panel real-time dashboard. Press Ctrl+C to exit.
echo.

cd /d "%PROJECT_ROOT%"
python scripts/tui.py

pause
