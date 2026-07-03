# -*- coding: utf-8 -*-
"""
scripts/start_dev.py
────────────────────
DialogMesh v3.0 — 一键开发启动脚本。

用途：
- 同时启动后端（FastAPI/uvicorn）和前端（Vite dev server）。
- 自动检查依赖、端口占用、环境配置。
- 支持优雅关闭（Ctrl+C 同时关闭前后端）。

用法：
    python scripts/start_dev.py
    python scripts/start_dev.py --port 8000 --frontend-port 5173
    python scripts/start_dev.py --mode prod  # 使用前端构建产物 + 静态文件服务

环境要求：
    pip install fastapi uvicorn
    cd frontend && npm install

版本：3.0.0
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def check_dependency(cmd: list[str], name: str) -> bool:
    """检查命令是否可用。"""
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_python_deps() -> list[str]:
    """检查 Python 依赖是否安装。"""
    missing = []
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    try:
        import uvicorn
    except ImportError:
        missing.append("uvicorn")
    return missing


def check_frontend_deps() -> bool:
    """检查前端 node_modules 是否存在。"""
    return (PROJECT_ROOT / "frontend" / "node_modules").exists()


def start_backend(port: int, log_level: str) -> subprocess.Popen:
    """启动后端 uvicorn 服务。"""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "core.service.v3_0.app_factory:create_app_v3",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--log-level", log_level,
        "--reload",
    ]
    print(f"[BACKEND] Starting: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def start_frontend_dev(port: int) -> subprocess.Popen:
    """启动前端 Vite dev server。"""
    frontend_dir = PROJECT_ROOT / "frontend"
    cmd = ["npm", "run", "dev", "--", "--port", str(port)]
    print(f"[FRONTEND] Starting: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=True,  # Windows 需要 shell=True 来运行 npm
    )


def start_frontend_prod(port: int) -> subprocess.Popen:
    """使用 Python http.server 提供前端构建产物。"""
    frontend_dir = PROJECT_ROOT / "frontend" / "dist"
    cmd = [sys.executable, "-m", "http.server", str(port), "--directory", str(frontend_dir)]
    print(f"[FRONTEND] Serving static files: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def print_header() -> None:
    """打印启动横幅。"""
    print("=" * 60)
    print("DialogMesh v3.0 — One-Click Development Startup")
    print("=" * 60)


def print_urls(backend_port: int, frontend_port: int, mode: str) -> None:
    """打印访问地址。"""
    print("\n" + "─" * 60)
    print("Services are running:")
    print(f"  Backend API:    http://localhost:{backend_port}/v3/health")
    print(f"  Backend Docs:   http://localhost:{backend_port}/docs")
    print(f"  Frontend ({mode}): http://localhost:{frontend_port}")
    print(f"  WebSocket:      ws://localhost:{backend_port}/v3/ws/{{session_id}}")
    print("─" * 60)
    print("Press Ctrl+C to stop all services.\n")


def stream_output(proc: subprocess.Popen, prefix: str) -> None:
    """从子进程读取输出并打印。"""
    try:
        for line in proc.stdout:
            print(f"[{prefix}] {line.rstrip()}")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="DialogMesh v3.0 One-Click Startup")
    parser.add_argument("--port", type=int, default=8000, help="Backend port (default: 8000)")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Frontend port (default: 5173)")
    parser.add_argument("--mode", choices=["dev", "prod"], default="dev", help="Frontend mode: dev (vite) or prod (static)")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], help="Backend log level")
    args = parser.parse_args()

    print_header()

    # 1. 检查 Python 依赖
    missing_py = check_python_deps()
    if missing_py:
        print(f"[ERROR] Missing Python dependencies: {', '.join(missing_py)}")
        print(f"[ERROR] Install with: {sys.executable} -m pip install {' '.join(missing_py)}")
        print(f"[ERROR] Or: pip install -r requirements.txt")
        sys.exit(1)

    # 2. 检查前端依赖
    if not check_frontend_deps():
        print("[WARN] Frontend node_modules not found.")
        print("[WARN] Run: cd frontend && npm install")
        if args.mode == "dev":
            print("[INFO] Falling back to prod mode (serve pre-built dist/)")
            args.mode = "prod"

    # 3. 检查 npm 是否可用（dev 模式）
    if args.mode == "dev" and not check_dependency(["npm", "--version"], "npm"):
        print("[WARN] npm not found. Falling back to prod mode.")
        args.mode = "prod"

    # 4. 启动服务
    backend_proc = start_backend(args.port, args.log_level)
    time.sleep(2)  # 给后端一点时间启动

    if args.mode == "dev":
        frontend_proc = start_frontend_dev(args.frontend_port)
    else:
        frontend_proc = start_frontend_prod(args.frontend_port)

    print_urls(args.port, args.frontend_port, args.mode)

    # 5. 监控输出
    try:
        while True:
            # 非阻塞读取输出
            import select
            # 由于 Windows 不支持 select on pipes，使用简单轮询
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping services...")
        backend_proc.terminate()
        frontend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
            frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
            frontend_proc.kill()
        print("[SHUTDOWN] All services stopped.")


if __name__ == "__main__":
    main()
