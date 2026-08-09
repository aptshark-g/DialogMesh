@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - Terminal Dashboard (TUI)
echo ================================================================
echo.
echo  Dual-mode: API (localhost:8000) ^| Offline (direct engine)
echo  Mode auto-detected on startup.
echo.
echo  First launch may take 5-10 seconds for Python imports.
echo  Subsequent launches are faster.
echo.

rem Try Windows Terminal first (better Textual support)
where wt >nul 2>&1
if %errorlevel% equ 0 (
    echo Launching in Windows Terminal...
    start wt --title "DialogMesh v4 TUI" python "scripts\tui.py"
    exit /b 0
)

rem Fallback: cmd.exe
echo.
echo Textual works best in Windows Terminal.
echo Install from Microsoft Store: "Windows Terminal"
echo.
echo Attempting to launch in cmd.exe...
pause

cd /d "%PROJECT_ROOT%"
python scripts/tui.py
pause
