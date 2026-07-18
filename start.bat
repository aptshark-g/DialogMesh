@echo off
setlocal EnableDelayedExpansion

:: DialogMesh v4 -- One-Click Startup (API + Frontend)

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

:: Check port 8000
netstat -ano | findstr ":8000 " >nul 2>&1
if errorlevel 1 goto :port8000_free
echo [WARN] Port 8000 already in use. API may be running.
goto :skip_backend
:port8000_free

:: Check port 8080
netstat -ano | findstr ":8080 " >nul 2>&1
if errorlevel 1 goto :port8080_free
echo [WARN] Port 8080 already in use. Frontend may be running.
goto :skip_frontend
:port8080_free

echo ================================================================
echo    DialogMesh v4 -- Cognitive Runtime + GUI
echo ================================================================
echo.

:: Start backend API
echo [1/2] Starting backend API ... http://localhost:8000
start /min "DialogMesh API" cmd /c "python scripts/start_server.py"

echo [INFO] Waiting 3 seconds for API...
timeout /t 3 /nobreak >nul

:skip_backend

:: Start frontend
echo [2/2] Starting frontend ... http://localhost:8080
cd frontend
start /min "DialogMesh GUI" cmd /c "npm run dev -- --port 8080 --host"

:skip_frontend

echo.
echo ================================================================
echo   Both services starting...
echo   API:    http://localhost:8000/docs
echo   GUI:    http://localhost:8080
echo.
echo   Press any key to stop all services.
echo ================================================================
pause >nul

:: Cleanup
echo.
echo [STOP] Stopping services...
taskkill /F /FI "WINDOWTITLE eq DialogMesh API" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DialogMesh GUI" >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
echo [DONE] All services stopped.

endlocal
