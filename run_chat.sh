#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -z "$DEEPSEEK_API_KEY" ]; then
    read -rsp "DeepSeek API Key: " DEEPSEEK_API_KEY
    echo ""
fi

unset PYTHONPATH PYTHONHOME
export PYTHONPATH="$ROOT"
export DEEPSEEK_API_KEY

PYTHON="$ROOT/.venv-test/Scripts/python.exe"
[ -f "$PYTHON" ] || { echo "ERROR: .venv-test not found"; exit 1; }

echo "============================================"
echo " DialogMesh v4 - Semantic World Runtime"
echo " Python:  $("$PYTHON" --version 2>&1)"
echo " Key:     ${DEEPSEEK_API_KEY:0:8}***"
curl -s http://127.0.0.1:1234/v1/models >/dev/null 2>&1 && echo " LMStudio: connected" || echo " LMStudio: offline"
echo "============================================"
echo ""

exec "$PYTHON" -B run_chat.py
