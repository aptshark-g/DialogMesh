@echo off
setlocal

rem DialogMesh v4 - One-Click Startup (Windows)

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - Cognitive Runtime
echo ================================================================
echo.
echo Starting v4 Cognitive Engine...
echo Commands: type text to send events, status to view, quit to exit
echo.

cd /d "%PROJECT_ROOT%"
python main.py
pause
