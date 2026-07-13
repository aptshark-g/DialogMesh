#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd $(dirname $0) && pwd)

echo "================================"
echo "DialogMesh v4 - Cognitive Runtime"
echo "================================"
echo "Starting v4 Cognitive Engine..."
echo "Commands: text=event, status=view, quit=exit"
echo ""

cd $PROJECT_ROOT
python main.py
