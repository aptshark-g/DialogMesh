@echo off
setlocal

rem ================================================================
rem DialogMesh v3.0 - One-Click Startup (Windows)
rem ================================================================
rem Usage: Double-click this file in File Explorer

set "PROJECT_ROOT=C:\Users\APTShark\PycharmProjects\DialogMesh"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"
set "NODE_PATH=C:\Program Files\nodejs"
set "ANACONDA_PATH=C:\Users\APTShark\anaconda3"

set "PYTHON=py -3.14"

rem Python 3.14 has built-in sqlite3, no Anaconda PATH fix needed

echo.
echo ================================================================
echo    DialogMesh v3.0 - Startup Script
echo ================================================================
echo.

rem --- Check prerequisites ---

echo [Check] Python 3.14 ...
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.14 not found. Install from python.org.
    pause
    exit /b 1
)
%PYTHON% --version
echo [OK]

echo [Check] Node.js ...
"%NODE_PATH%\node.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found at %NODE_PATH%.
    pause
    exit /b 1
)
"%NODE_PATH%\node.exe" --version
echo [OK]

echo [Check] sqlite3 ...
%PYTHON% -c "import sqlite3; print(sqlite3.sqlite_version)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] sqlite3 not working in Python 3.14.
    pause
    exit /b 1
)
echo [OK]

echo [Check] Frontend build ...
if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo [WARN] Frontend dist not found. Building...
    cd /d "%FRONTEND_DIR%"
    call "%NODE_PATH%\npm.cmd" run build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed.
        pause
        exit /b 1
    )
)
echo [OK]

echo.
echo [INFO] Starting services...
echo   Backend : http://localhost:8000
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/docs
echo.

rem --- Start Backend ---

echo [1/2] Starting Backend (FastAPI) ...
cd /d "%PROJECT_ROOT%"
start "DialogMesh-Backend" cmd /k "%PYTHON% main_v3.py --host 0.0.0.0 --port 8000 --log-level info"

timeout /t 5 /nobreak >nul

rem --- Start Frontend ---

echo [2/2] Starting Frontend (SPA Server) ...
cd /d "%FRONTEND_DIR%"
start "DialogMesh-Frontend" cmd /k "%PYTHON% serve.py"

echo.
echo ================================================================
echo  Done! Two console windows opened:
echo    - DialogMesh-Backend  (port 8000)
echo    - DialogMesh-Frontend (port 5173)
echo.
echo  Open browser: http://localhost:5173
echo  API Docs    : http://localhost:8000/docs
echo.
echo  Press Ctrl+C in each window to stop.
echo ================================================================
echo.
pause
