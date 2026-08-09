@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
cd /d "%ROOT%"

if "%DEEPSEEK_API_KEY%"=="" (
    set /p DEEPSEEK_API_KEY="DeepSeek API Key: "
)

set "BASH="
if exist "C:\Program Files\Git\bin\bash.exe" set "BASH=C:\Program Files\Git\bin\bash.exe"
if exist "%SystemDrive%\msys64\usr\bin\bash.exe" set "BASH=%SystemDrive%\msys64\usr\bin\bash.exe"
if exist "%USERPROFILE%\scoop\apps\git\current\bin\bash.exe" set "BASH=%USERPROFILE%\scoop\apps\git\current\bin\bash.exe"

if defined BASH (
    "%BASH%" -c "cd '%ROOT%' && DEEPSEEK_API_KEY='%DEEPSEEK_API_KEY%' PYTHONPATH='%ROOT%' .venv-test/Scripts/python run_chat.py"
) else (
    ".venv-test\Scripts\python.exe" run_chat.py
)
pause
