#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd $(dirname $0) && pwd)

echo "================================"
echo "DialogMesh v4 - CLI Terminal Mode"
echo "================================"
echo "Interactive cognitive runtime."
echo "Commands: text=event, status=view, checkpoint=trigger, quit=exit"
echo ""

cd $PROJECT_ROOT
python main.py
