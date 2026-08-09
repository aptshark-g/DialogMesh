#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DialogMesh 全链路演示 — 健康检查 → 对话 → 召回 → 执行迹 → 变更日志。

用法:
    python scripts/demo.py                  # 默认 8000 API + 8080 网关
    python scripts/demo.py --api 8000       # 自定义端口
    python scripts/demo.py --query "..."    # 自定义提问

服务未启动时优雅降级（打印提示, 不崩溃）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def _api(base: str, method: str, path: str, body=None, timeout: float = 90):
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8")[:300]}
    except Exception as e:
        return {"error": str(e)[:200]}


def _sep(title: str):
    print(f"\n{'=' * 62}\n  {title}\n{'=' * 62}")


def _fmt(value, depth=0):
    return json.dumps(value, ensure_ascii=False, indent=2) if isinstance(
        value, (dict, list)) else str(value)


def _mark(ok: bool, text: str = "") -> str:
    """ASCII 安全状态标记（Windows GBK 控制台不崩溃）。"""
    tag = "[OK]" if ok else "[FAIL]"
    return f"{tag} {text}" if text else tag


def _safe_console():
    """stdout/stderr 重配置为 UTF-8 + replace —— 避免 LLM 回复中的
    emoji/特殊字符在 GBK 控制台抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser(description="DialogMesh demo tour")
    p.add_argument("--api", type=int, default=8000)
    p.add_argument("--gateway", type=int, default=8080)
    p.add_argument("--query", default="写一个 hello_world.py 并运行它")
    args = p.parse_args()
    _safe_console()

    api = f"http://127.0.0.1:{args.api}"
    gw = f"http://127.0.0.1:{args.gateway}"

    # ── 1. 健康检查 ────────────────────────────────────────────
    _sep("1/5 健康检查")
    api_ok = "ok" in _api(api, "GET", "/v6/health").get("status", "")
    gw_ok = False
    try:
        with urllib.request.urlopen(f"{gw}/v1/health", timeout=5) as r:
            gw_ok = r.status == 200
    except Exception:
        pass
    print(f"  API     :{args.api}  {_mark(api_ok, 'up' if api_ok else 'down (run start.bat)')}")
    print(f"  Gateway :{args.gateway}  {_mark(gw_ok, 'up' if gw_ok else 'down')}")
    if not api_ok:
        print("\n  提示: 先运行 start.bat 启动服务后再执行本演示。")
        return

    # ── 2. 对话（真实 LLM, 编码请求走执行层）──────────────────
    _sep("2/5 对话 + 执行层（LLM 自主工具调用）")
    sess = _api(api, "POST", "/v3/session", {"title": "demo"})
    sid = sess.get("session_id") or str(uuid.uuid4())[:12]
    print(f"  session: {sid}")
    print(f"  query  : {args.query}")
    r = _api(api, "POST", f"/v3/session/{sid}/message", {"content": args.query})
    if r.get("error"):
        print(f"  [FAIL] {r.get('error')} {r.get('detail', '')}")
    else:
        content = r.get("content") or r.get("answer") or ""
        print(f"  reply  : {content[:300]}")
        if r.get("intent"):
            print(f"  intent : {r.get('intent')} | "
                  f"latency {r.get('latency_ms', 0):.0f}ms")

    # ── 3. 统一召回 ────────────────────────────────────────────
    _sep("3/5 统一召回")
    rec = _api(api, "GET", "/v6/recall?query=" +
               urllib.request.quote(args.query[:40]) + "&top_k=3")
    hits = rec.get("hits") or []
    print(f"  hits: {len(hits)}")
    for h in hits[:3]:
        print(f"   - [{h.get('score', '?')}] {str(h.get('text', h))[:80]}")
    if rec.get("latency_ms"):
        print(f"  latency: {rec['latency_ms']:.0f}ms")

    # ── 4. 执行迹（v2 执行层白盒视图）──────────────────────────
    _sep("4/5 执行迹 /v6/execution")
    ex = _api(api, "GET", f"/v6/execution/{sid}")
    execs = ex.get("execution") or {}
    if not execs:
        print("  （本次对话未产生执行迹——非编码请求或服务刚重启）")
    for node_id, tr in execs.items():
        print(f"  [{node_id}] status={tr.get('status')} "
              f"verdict={tr.get('verdict')} rounds={tr.get('rounds')} "
              f"latency={tr.get('latency_ms')}ms")
        for tc in (tr.get("tool_calls") or [])[:5]:
            print(f"      -> {tc.get('name')}: "
                  f"{'ok' if tc.get('ok') else 'fail'}")

    # ── 5. 决策变更日志（可回看/可介入）────────────────────────
    _sep("5/5 决策变更日志 /v6/changelog")
    ch = _api(api, "GET", "/v6/changelog?limit=10")
    events = ch.get("events") or []
    print(f"  events: {len(events)}")
    for ev in events[:5]:
        print(f"   - [{ev.get('kind')}/{ev.get('status')}] "
              f"{str(ev.get('reason'))[:80]}")

    print("\n[OK] 演示结束。详细 API 见 http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
