#!/usr/bin/env python3
"""
DialogMesh v3.0 CLI — 跨平台命令行客户端

通过 HTTP API 与 DialogMesh 后端通信，无需浏览器/WebSocket/Node.js。

用法:
  python scripts/cli.py                        交互模式
  python scripts/cli.py "scan memory"          单次查询
  python scripts/cli.py --json "read value"    JSON输出（给AI工具用）
  echo "query" | python scripts/cli.py         管道输入
  python scripts/cli.py --help                 帮助

安装依赖: 无需额外安装 (只用标准库 urllib)
"""

import json
import sys
import urllib.request
import urllib.parse
import argparse

VERSION = "3.0.0"
DEFAULT_BASE = "http://localhost:8000"


def post(base: str, path: str, data: dict = None) -> dict:
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise SystemExit(f"[ERROR] HTTP {e.code} {e.reason}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"[ERROR] 无法连接到 {url}: {e.reason}")


def get(base: str, path: str) -> dict:
    """发送 GET 请求并返回 JSON。"""
    url = f"{base}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise SystemExit(f"[ERROR] HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"[ERROR] 无法连接到 {url}: {e.reason}")


def health_check(base: str) -> bool:
    """检查后端是否可用。"""
    try:
        r = get(base, "/v3/health")
        ok = r.get("status") == "ok" or "status" in r
        if ok:
            print(f"[OK] 后端已就绪 (version={r.get('version','?')})", file=sys.stderr)
        return ok
    except Exception:
        return False


def create_session(base: str) -> str:
    """创建新会话，返回 session_id。"""
    r = post(base, "/v3/session")
    sid = r.get("session_id", "")
    if not sid:
        raise SystemExit("[ERROR] 创建会话失败：返回中没有 session_id")
    print(f"[会话] {sid[:12]}...", file=sys.stderr)
    return sid


def format_response(r: dict) -> str:
    """格式化响应内容为可读文本。"""
    lines = []

    # 回答内容
    content = r.get("content") or r.get("answer") or ""
    if content:
        lines.append(content)

    # 结构化信息
    info_parts = []
    if r.get("intent"):
        info_parts.append(f"Intent: {r['intent']}")
    if r.get("latency_ms"):
        info_parts.append(f"Latency: {r['latency_ms']:.0f}ms")
    if r.get("status"):
        info_parts.append(f"Status: {r['status']}")
    if r.get("confidence"):
        info_parts.append(f"Confidence: {r['confidence']:.2f}")
    if info_parts:
        lines.append("  " + " | ".join(info_parts))

    # 建议/澄清
    if r.get("suggestions"):
        lines.append("  Suggestions:")
        for s in r["suggestions"]:
            lines.append(f"    - {s}")

    # 错误
    if r.get("error"):
        lines.append(f"  [ERROR] {r['error']}")

    # 任务图
    if r.get("task_graph"):
        nodes = r["task_graph"].get("nodes", [])
        if nodes:
            lines.append(f"  Plan: {len(nodes)} steps")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description="DialogMesh v3.0 CLI — 跨平台命令行客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/cli.py "scan memory at 0x004000"
  python scripts/cli.py --json "read value"
  echo "help me" | python scripts/cli.py
  python scripts/cli.py --base http://192.168.1.100:8000
        """,
    )
    p.add_argument("query", nargs="?", help="查询内容（省略则进入交互模式）")
    p.add_argument("--json", action="store_true", help="输出 JSON 格式（供 AI/脚本调用）")
    p.add_argument("--base", default=DEFAULT_BASE, help=f"后端地址 (默认: {DEFAULT_BASE})")
    p.add_argument("--session", default=None, help="指定已有 session_id 而非新建")
    p.add_argument("--no-health", action="store_true", help="跳过健康检查")
    p.add_argument("--version", action="store_true", help="显示版本号")
    args = p.parse_args()

    if args.version:
        print(f"DialogMesh CLI v{VERSION}")
        return

    base = args.base.rstrip("/")

    # 健康检查
    if not args.no_health:
        if not health_check(base):
            print(f"[WARN] 后端 {base} 无响应，继续尝试...", file=sys.stderr)

    # 获取或创建会话
    sid = args.session
    if not sid:
        try:
            sid = create_session(base)
        except Exception as e:
            print(f"[ERROR] 创建会话失败: {e}", file=sys.stderr)
            sys.exit(1)

    # 获取查询列表
    if args.query:
        queries = [args.query]
    elif not sys.stdin.isatty():
        # 管道输入
        queries = [line.strip() for line in sys.stdin if line.strip()]
    else:
        # 交互模式
        print("DialogMesh v3.0 CLI. 输入 exit/quit 退出。", file=sys.stderr)
        queries = [line.strip() for line in sys.stdin if line.strip()]

    # 执行查询
    for q in queries:
        if q.lower() in ("exit", "quit"):
            break
        if not q:
            continue

        try:
            r = post(base, f"/v3/session/{sid}/message", {"content": q})
            if args.json:
                print(json.dumps(r, ensure_ascii=False))
            else:
                print(format_response(r))
                print()
        except SystemExit:
            raise
        except Exception as e:
            print(f"[ERROR] 查询失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()