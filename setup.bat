@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
echo ================================================================
echo   DialogMesh 一键环境安装 / 检查
echo ================================================================
python scripts\setup_env.py %*
if errorlevel 1 (
  echo.
  echo 安装失败。请检查上方提示（常见: 未装 Python 3.10+ 或网络不可达）。
  pause
)
