@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: DialogMesh v6 -- One-Click Startup (Gateway + API + Frontend)

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

:: ==== 1. Check & Start Switch Gateway (:8080) ====
netstat -ano | findstr ":8080 .*LISTENING" >nul 2>&1
if errorlevel 1 goto :gateway_port_free
echo [WARN] Port 8080 in use - killing old Gateway process...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080 .*LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 1 /nobreak >nul
:gateway_port_free

echo ================================================================
echo    DialogMesh v6 -- Gateway + Cognitive Runtime + GUI
echo ================================================================
echo.

echo [1/3] Starting Switch Gateway ... http://localhost:8080
cd gateway
start /min "DialogMesh Gateway" cmd /c "gateway.exe"
cd ..
echo [INFO] Waiting 2 seconds for Gateway...
timeout /t 2 /nobreak >nul

:: ==== 2. Check & Start DialogMesh API (:8000) ====
netstat -ano | findstr ":8000 .*LISTENING" >nul 2>&1
if errorlevel 1 goto :api_port_free
echo [WARN] Port 8000 in use - killing old API process...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 1 /nobreak >nul
:api_port_free

echo [2/3] Starting DialogMesh API ... http://localhost:8000
start "DialogMesh API" cmd /k "C:\Users\APTShark\PycharmProjects\DialogMesh\.venv\Scripts\python.exe scripts\start_server.py --no-gateway"
echo [INFO] Waiting 3 seconds for API...
timeout /t 3 /nobreak >nul

:: ==== 3. Start Frontend (Vite preview, fixed port) ====
:: NOTE: Gateway uses :8080, so frontend runs on Vite preview default port
:: 2026-08-17 FIX: pin --port 4173 --strictPort - otherwise vite drifts to
:: 4174 when 4173 is taken, but the hint prints 4173 -> frontend invisible.
netstat -ano | findstr ":4173 .*LISTENING" >nul 2>&1
if errorlevel 1 goto :frontend_port_free
echo [WARN] Port 4173 in use - killing old Frontend process...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":4173 .*LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 1 /nobreak >nul
:frontend_port_free

echo [3/3] Starting frontend preview ...
cd frontend
start /min "DialogMesh GUI" cmd /c "npm run preview -- --host --port 4173 --strictPort"

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
taskkill /F /IM gateway.exe >nul 2>&1
:: 2026-08-17 FIX: do NOT taskkill /F /IM node.exe - it kills every node
:: on the system (including the Codex desktop app itself). Clean by port:
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":4173 .*LISTENING"') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080 .*LISTENING"') do taskkill /F /PID %%a 2>nul
echo [DONE] All services stopped.

endlocal