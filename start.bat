@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: DialogMesh v6 -- One-Click Startup (Gateway + API + Frontend)

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

:: ==== 1. Check & Start Switch Gateway (:8080) ====
netstat -ano | findstr ":8080 " >nul 2>&1
if errorlevel 1 goto :gateway_port_free
echo [WARN] Port 8080 already in use. Gateway may be running.
goto :skip_gateway
:gateway_port_free

echo ================================================================
echo    DialogMesh v6 -- Gateway + Cognitive Runtime + GUI
echo ================================================================
echo.

:: Start Switch Gateway (must run from gateway/ dir to read provider.yaml)
echo [1/3] Starting Switch Gateway ... http://localhost:8080
cd gateway
start /min "DialogMesh Gateway" cmd /c "gateway.exe"
cd ..
echo [INFO] Waiting 2 seconds for Gateway...
timeout /t 2 /nobreak >nul

:skip_gateway

:: ==== 2. Check & Start DialogMesh API (:8000) ====
netstat -ano | findstr ":8000 " >nul 2>&1
if errorlevel 1 goto :api_port_free
echo [WARN] Port 8000 already in use. API may be running.
goto :skip_api
:api_port_free

echo [2/3] Starting DialogMesh API ... http://localhost:8000
start /min "DialogMesh API" cmd /c "python scripts/start_server.py"
echo [INFO] Waiting 3 seconds for API...
timeout /t 3 /nobreak >nul

:skip_api

:: ==== 3. Start Frontend (Vite preview, auto port) ====
:: NOTE: Gateway uses :8080, so frontend runs on Vite preview default port
echo [3/3] Starting frontend preview ...
cd frontend
start /min "DialogMesh GUI" cmd /c "npm run preview -- --host"

:: ==== Summary ====
echo.
echo ================================================================
echo   All services starting...
echo.
echo   Gateway: http://localhost:8080         (Switch proxy)
echo   API:     http://localhost:8000/docs    (DialogMesh docs)
echo   GUI:     http://localhost:4173         (Vite preview)
echo.
echo   Gateway check: curl http://localhost:8080/v1/health
echo.
echo   Press any key to stop all services.
echo ================================================================
pause >nul

:: ==== Cleanup ====
echo.
echo [STOP] Stopping services...
taskkill /F /FI "WINDOWTITLE eq DialogMesh Gateway" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DialogMesh API" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DialogMesh GUI" >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM gateway.exe >nul 2>&1
echo [DONE] All services stopped.

endlocal
