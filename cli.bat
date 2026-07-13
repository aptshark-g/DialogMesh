@echo off
setlocal

rem ================================================================
rem DialogMesh v4 — CLI Terminal Mode (Windows)
rem ================================================================

set "PROJECT_ROOT=%~dp0"

echo ================================================================
echo    DialogMesh v4 - CLI Terminal Mode
echo ================================================================
echo.
echo Interactive cognitive runtime.
echo Commands: text=event, status=view, checkpoint=trigger, quit=exit
echo.

cd /d "%PROJECT_ROOT%"
python main.py
