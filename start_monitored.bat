@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: DialogMesh v6 — Monitored Startup (logs everything)
set "PROJECT_ROOT=%~dp0"
set "TS=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TS=%TS: =0%"
set "LOGDIR=%PROJECT_ROOT%tests\log"
mkdir "%LOGDIR%" 2>nul
cd /d "%PROJECT_ROOT%"

echo.
echo ═══════════════════════════════════════════════════════════
echo   DialogMesh v6 — Monitored Startup %TS%
echo ═══════════════════════════════════════════════════════════

:: ==== 0. Kill stale services ====
echo [0] Cleaning stale services...
taskkill /F /IM gateway.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: ==== 1. Start Gateway ====
echo [1/3] Starting Gateway ... http://localhost:8080
cd gateway
start /min "DM_GW" cmd /c "gateway.exe > ..\tests\log\gw_%TS%.log 2>&1"
cd ..
set "GW_OK=0"
for /L %%i in (1,1,15) do (
  timeout /t 1 /nobreak >nul
  curl -s -m 1 http://127.0.0.1:8080/v1/health >nul 2>&1 && set GW_OK=1 && goto :gw_up
)
:gw_up
if %GW_OK%==1 (echo   [OK] Gateway UP) else (echo   [FAIL] Gateway NOT UP — check tests\log\gw_%TS%.log)

:: ==== 2. Start API ====
echo [2/3] Starting API ... http://localhost:8000
:: Use system Python (not .venv-test — has websockets)
start "DM_API" cmd /k "python scripts\start_server.py --no-gateway > tests\log\api_%TS%.log 2>&1"
set "API_OK=0"
for /L %%i in (1,1,20) do (
  timeout /t 1 /nobreak >nul
  curl -s -m 1 -H "Authorization: Bearer dev-token" http://127.0.0.1:8000/v4/health | findstr "ok" >nul 2>&1 && set API_OK=1 && goto :api_up
)
:api_up
if %API_OK%==1 (echo   [OK] API UP) else (echo   [FAIL] API NOT UP — check tests\log\api_%TS%.log)

:: ==== 3. Frontend ====
echo [3/3] Starting Frontend ...
cd frontend
start /min "DM_GUI" cmd /c "npm run preview -- --host > ..\tests\log\fe_%TS%.log 2>&1"

:: ==== 4. Health dump ====
echo.
echo ─── Health Dump ───
echo Gateway:
curl -s http://127.0.0.1:8080/v1/health 2>nul
echo.
echo.
echo API:
curl -s -H "Authorization: Bearer dev-token" http://127.0.0.1:8000/v4/health 2>nul
echo.
echo.
echo DeepSeek Key:
curl -s -H "Authorization: Bearer dev-token" http://127.0.0.1:8000/v6/gateway/providers 2>nul | python -c "import sys,json; d=json.load(sys.stdin); ds=[p for p in d.get('providers',[]) if p['name']=='deepseek']; print(f\"  key_configured={ds[0].get('key_configured','?')} healthy={ds[0].get('healthy','?')} active={ds[0].get('active','?')}\")" 2>nul

echo.
echo ─── Logs: %LOGDIR% ───
echo   gw_%TS%.log  api_%TS%.log  fe_%TS%.log
echo.
echo ═══════════════════════════════════════════════════════════
echo   Press any key to stop all services.
echo ═══════════════════════════════════════════════════════════
pause >nul

:: ==== Cleanup ====
echo [STOP] Stopping services...
taskkill /F /FI "WINDOWTITLE eq DM_GW" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DM_API" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq DM_GUI" >nul 2>&1
taskkill /F /IM gateway.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
echo [DONE]
endlocal
