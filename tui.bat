@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - Terminal Dashboard (TUI)
echo ================================================================
echo.
echo  Textual framework starting...
echo  First launch may take 5-10 seconds for Python imports.
echo  Subsequent launches are faster.
echo.

rem Try Windows Terminal first (better Textual support)
where wt >nul 2>&1
if %errorlevel% equ 0 (
    echo Launching in Windows Terminal (Textual startup ~5-10s)...
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
