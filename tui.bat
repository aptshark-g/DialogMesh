@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - Terminal Dashboard (TUI)
echo ================================================================

rem Try Windows Terminal first (better Textual support)
where wt >nul 2>&1
if %errorlevel% equ 0 (
    echo Launching in Windows Terminal...
    start wt --title "DialogMesh v4 TUI" python "scripts\tui.py"
    exit /b 0
)

rem Fallback: cmd.exe (may have display issues)
echo.
echo Textual works best in Windows Terminal.
echo Install from Microsoft Store: "Windows Terminal"
echo.
echo Attempting to launch in cmd.exe...
pause

cd /d "%PROJECT_ROOT%"
python scripts/tui.py
pause
