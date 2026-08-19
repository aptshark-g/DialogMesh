#!/usr/bin/env python3
"""DialogMesh 一键环境检查与安装（2026-08-19, 仅标准库, 跨平台）。

用法:
  python scripts/setup_env.py             # 检查 + 安装全部（默认）
  python scripts/setup_env.py --check     # 只检查并打印依赖清单状态
  python scripts/setup_env.py --deps      # 只装 Python 依赖
  python scripts/setup_env.py --frontend  # 只装前端并构建
  python scripts/setup_env.py --gateway   # 只确保网关二进制
  python scripts/setup_env.py --models    # 预下载嵌入模型（可选）

Python 依赖较大（torch 等, 数 GB）, 首次安装需要几分钟到十几分钟。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(ROOT, ".venv")
FRONTEND = os.path.join(ROOT, "frontend")
GATEWAY_DIR = os.path.join(ROOT, "gateway")
GATEWAY_EXE = os.path.join(GATEWAY_DIR,
                           "gateway.exe" if os.name == "nt" else "gateway")
SWITCH_REPO = "https://github.com/aptshark-g/switch.git"


def say(msg: str) -> None:
    print(f"  [OK] {msg}" if not msg.startswith(" ") else f"  {msg}")


def run(cmd, cwd=None, check=True):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd)
    if check and r.returncode != 0:
        raise SystemExit(f"[X] 命令失败: {' '.join(cmd)} (exit {r.returncode})")
    return r


def check_python() -> tuple:
    # 优先用已存在的 .venv 解释器（PATH 上的旧 Python 不阻塞）
    exe = venv_python() or sys.executable
    if exe and os.path.abspath(exe) != os.path.abspath(sys.executable):
        r = subprocess.run([exe, "-c",
                            "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                           capture_output=True, text=True)
        ver = (r.stdout or "").strip()
        parts = [int(x) for x in ver.split(".")[:2]] if ver else [0, 0]
    else:
        parts = [sys.version_info.major, sys.version_info.minor]
    ok = (3, 10) <= tuple(parts) <= (3, 13)
    return ok, f"Python {'.'.join(map(str, parts))} (需要 3.10-3.13)"


def check_node() -> tuple:
    node = shutil.which("node")
    if not node:
        return False, "Node.js 未安装 (需要 >= 18)"
    r = subprocess.run([node, "--version"], capture_output=True, text=True)
    ver = (r.stdout or "").strip()
    major = int(ver.lstrip("v").split(".")[0]) if ver else 0
    return major >= 18, f"Node {ver} (需要 >= 18)"


def venv_python() -> str:
    if os.name == "nt":
        p = os.path.join(VENV_DIR, "Scripts", "python.exe")
    else:
        p = os.path.join(VENV_DIR, "bin", "python")
    return p if os.path.exists(p) else ""


def ensure_venv() -> str:
    p = venv_python()
    if p:
        say("已存在 .venv")
        return p
    say("创建 .venv ...")
    run([sys.executable, "-m", "venv", VENV_DIR])
    p = venv_python()
    if not p:
        raise SystemExit("[X] 无法创建 .venv, 请检查 Python 安装")
    return p


def install_python_deps(py: str) -> None:
    say("升级 pip 并安装 requirements.txt (torch 等较大, 请耐心) ...")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-r",
         os.path.join(ROOT, "requirements.txt")])


def ensure_configs() -> None:
    pairs = [
        (os.path.join(ROOT, ".env.example"), os.path.join(ROOT, ".env")),
        (os.path.join(GATEWAY_DIR, "provider.example.yaml"),
         os.path.join(GATEWAY_DIR, "provider.yaml")),
    ]
    for src, dst in pairs:
        if os.path.exists(dst):
            say(f"已存在: {os.path.relpath(dst, ROOT)}")
        elif os.path.exists(src):
            shutil.copyfile(src, dst)
            say(f"已从示例复制: {os.path.relpath(dst, ROOT)}"
                " (记得填入你的 API Key)")
        else:
            say(f"[!] 缺少示例文件: {src}")


def ensure_frontend() -> None:
    if not shutil.which("npm"):
        raise SystemExit("[X] 未找到 npm, 请先安装 Node.js >= 18")
    if not os.path.exists(os.path.join(FRONTEND, "node_modules")):
        say("npm install (前端依赖) ...")
        run(["npm", "install"], cwd=FRONTEND)
    else:
        say("前端依赖已存在, 跳过 npm install")
    if not os.path.exists(os.path.join(FRONTEND, "dist", "index.html")):
        say("npm run build (前端构建) ...")
        run(["npm", "run", "build"], cwd=FRONTEND)
    else:
        say("前端 dist 已存在, 跳过构建")


def _download(url: str, dst: str) -> bool:
    say(f"下载 {url} ...")
    try:
        urllib.request.urlretrieve(url, dst)
        return True
    except Exception as e:
        say(f"[!] 下载失败: {e}")
        return False


def ensure_gateway() -> None:
    if os.path.exists(GATEWAY_EXE):
        say(f"网关二进制已存在: {os.path.relpath(GATEWAY_EXE, ROOT)}")
        return
    os.makedirs(GATEWAY_DIR, exist_ok=True)
    # 1) 优先从环境变量指定的 release URL 下载
    url = os.environ.get("DM_GATEWAY_BIN_URL", "").strip()
    if url and _download(url, GATEWAY_EXE):
        say("网关二进制已下载 (DM_GATEWAY_BIN_URL)")
        return
    # 2) 其次用 Go 从源码构建
    go = shutil.which("go")
    if go:
        tmp = os.path.join(ROOT, ".setup_gateway_src")
        say(f"从 {SWITCH_REPO} 克隆并构建网关 (需要几分钟) ...")
        if not os.path.exists(os.path.join(tmp, "go.mod")):
            run(["git", "clone", "--depth", "1", SWITCH_REPO, tmp])
        run(["go", "build", "-o", GATEWAY_EXE, "./cmd/gateway"], cwd=tmp)
        say("网关已从源码构建")
        return
    raise SystemExit(
        "[X] 缺少网关二进制, 且无 Go 环境。\n"
        "  请任选其一:\n"
        "    A) 安装 Go 后重跑: python scripts/setup_env.py --gateway\n"
        "    B) 从 GitHub release 下载 gateway 二进制放到 gateway/ 目录\n"
        "    C) 设置 DM_GATEWAY_BIN_URL=<下载地址> 后重跑")


def ensure_models() -> None:
    """可选: 预下载嵌入模型 BGE-small-zh（运行时也会按需自动下载）。"""
    try:
        import modelscope  # noqa: F401
    except ImportError:
        say("[!] modelscope 未安装（运行时会自动按需下载模型, 可跳过预下载）")
        return
    say("预下载 BGE-small-zh (13MB) ...")
    run([venv_python() or sys.executable, "-c",
         "from modelscope import snapshot_download; "
         "snapshot_download('BAAI/bge-small-zh-v1.5')"])


def print_table(results: list) -> None:
    print("\n=== DialogMesh 依赖清单 ===\n")
    for name, ok, detail in results:
        mark = "OK" if ok else "XX"
        print(f"  [{mark}] {name:<28} {detail}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="DialogMesh 一键环境安装")
    ap.add_argument("--check", action="store_true", help="只检查并打印清单")
    ap.add_argument("--deps", action="store_true", help="只装 Python 依赖")
    ap.add_argument("--frontend", action="store_true", help="只装前端并构建")
    ap.add_argument("--gateway", action="store_true", help="只确保网关二进制")
    ap.add_argument("--models", action="store_true", help="预下载嵌入模型")
    args = ap.parse_args()

    only = args.check or args.deps or args.frontend or args.gateway or args.models

    print(f"DialogMesh 环境设置 @ {ROOT}\n")
    py_ok, py_detail = check_python()
    node_ok, node_detail = check_node()
    results = [
        ("Python", py_ok, py_detail),
        ("Node.js", node_ok, node_detail),
        (".venv", bool(venv_python()), ".venv 是否存在"),
        ("Python 依赖", os.path.exists(os.path.join(ROOT, "requirements.txt")),
         "requirements.txt 存在"),
        ("网关二进制", os.path.exists(GATEWAY_EXE),
         os.path.relpath(GATEWAY_EXE, ROOT) + " 是否存在"),
        ("provider.yaml", os.path.exists(os.path.join(GATEWAY_DIR, "provider.yaml")),
         "网关 Provider 配置"),
        (".env", os.path.exists(os.path.join(ROOT, ".env")), "本地环境配置"),
        ("前端构建", os.path.exists(os.path.join(FRONTEND, "dist", "index.html")),
         "frontend/dist 是否存在"),
    ]

    if args.check or not only:
        print_table(results)
    if args.check:
        bad = [n for n, ok, _ in results if not ok]
        if bad:
            print("缺失项: " + ", ".join(bad))
            print("运行  python scripts/setup_env.py  一键补齐。")
        else:
            print("全部就绪! 运行 start.bat 启动。")
        return

    if not py_ok:
        raise SystemExit(f"[X] {py_detail} —— 请先安装 Python 3.10+")

    if args.deps or not only:
        py = ensure_venv()
        install_python_deps(py)
    else:
        py = venv_python() or sys.executable

    if args.frontend or not only:
        ensure_frontend()
    if args.gateway or not only:
        ensure_gateway()
    if args.models:
        ensure_models()

    ensure_configs()

    print("\n=== 完成 ===")
    print_table([(n, o, d) for n, o, d in results])
    print("启动: start.bat  (或手动: python scripts/start_server.py)")
    print("入口: API http://localhost:8000/docs · 前端 http://localhost:4173")


if __name__ == "__main__":
    main()
