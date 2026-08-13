#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent 量化评测 — 任务成功率 / 端到端延迟 / Token 消耗（2026-08-10）。

补测试缺口（用户清单）:
  Agent 任务成功率 / 端到端响应延迟 / Token 消耗成本

方法:
  - 走真实 v3 链路: POST /v3/session → POST /v3/session/{sid}/message
  - N 次重复任务, 统计成功率/延迟分布
  - Token: 网关 /v1/stats 前后差值（tokens_prompt/completion）
  - 任务集: 简单（hello world）/ 中等（文件+运行）/ 编码类（自动走 tool_loop）

用法:
  .venv\\Scripts\\python.exe scripts/agent_bench.py --n 3 --tasks simple,code
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "http://127.0.0.1:8000"
GW = "http://127.0.0.1:8080"

TASKS = {
    "simple": "写一个 hello.py 打印 Hello DialogMesh，并运行它，告诉我输出。",
    "code": "写一个 Python 脚本计算 1 到 100 的质数之和并运行验证，然后告诉我结果。",
    "web": "写一个 index.html 展示 DialogMesh 标题，用蓝色标题。",
    "explain": "解释什么是依赖注入，给出 Python 代码示例，不要运行。",
}

def post(path, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(API + path, data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw), (time.time() - t0) * 1000

def gw_tokens():
    req = urllib.request.Request(GW + "/v1/stats",
        headers={"Authorization": "Bearer dm-client"})
    d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
    tp = sum(d.get("tokens_prompt", {}).values())
    tc = sum(d.get("tokens_completion", {}).values())
    return tp, tc

def run_task(task_name: str, query: str, timeout_s: float = 180.0) -> dict:
    sid, _ = post("/v3/session")
    t_start = time.time()
    resp, latency_ms = post(f"/v3/session/{sid['session_id']}/message",
                            {"content": query})
    total_ms = (time.time() - t_start) * 1000
    content = resp.get("content", "") or ""
    return {
        "task": task_name, "latency_ms": latency_ms,
        "total_ms": total_ms, "content_len": len(content),
        "content": content[:200], "status": resp.get("status", "?"),
        "intent": resp.get("intent", "?"),
    }

def success(task_name: str, r: dict) -> bool:
    """任务成功率判定（宽松: 有实质回复 + 无 error + 非超时）。"""
    if r.get("error"):
        return False
    c = r.get("content") or ""
    if len(c) < 20:
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="每任务重复次数")
    ap.add_argument("--tasks", default="simple,code",
                    help="任务集逗号分隔: simple,code,web,explain")
    args = ap.parse_args()
    tasks = {k: TASKS[k] for k in args.tasks.split(",") if k in TASKS}

    tp0, tc0 = gw_tokens()
    print(f"任务: {list(tasks)} x{args.n} 次, 开始 token: prompt={tp0} completion={tc0}")
    results = []
    for name, query in tasks.items():
        for i in range(args.n):
            try:
                r = run_task(name, query)
                r["success"] = success(name, r)
                results.append(r)
                print(f"  [{name}#{i+1}] ok={r['success']} latency={r['latency_ms']:.0f}ms "
                      f"total={r['total_ms']:.0f}ms len={r['content_len']} intent={r['intent']}")
            except Exception as e:
                results.append({"task": name, "success": False,
                                "error": str(e)[:120], "latency_ms": 0,
                                "total_ms": 0, "content_len": 0})
                print(f"  [{name}#{i+1}] FAIL: {str(e)[:100]}")

    tp1, tc1 = gw_tokens()
    print("\n=== 汇总 ===")
    total = len(results)
    ok = sum(1 for r in results if r["success"])
    lat = [r["latency_ms"] for r in results if r.get("latency_ms")]
    total_ms = [r["total_ms"] for r in results if r.get("total_ms")]
    print(f"成功率: {ok}/{total} ({100.0*ok/max(total,1):.1f}%)")
    if lat:
        lat.sort()
        print(f"端到端延迟: avg={sum(lat)/len(lat):.0f}ms p50={lat[len(lat)//2]:.0f}ms "
              f"p95={lat[int(len(lat)*0.95)-1]:.0f}ms")
    if total_ms:
        total_ms.sort()
        print(f"总耗时(含会话创建): avg={sum(total_ms)/len(total_ms):.0f}ms "
              f"p50={total_ms[len(total_ms)//2]:.0f}ms")
    print(f"Token: prompt +{tp1-tp0} / completion +{tc1-tc0} "
          f"(总计 +{tp1-tp0+tc1-tc0}, 每任务 ~{(tp1-tp0+tc1-tc0)/max(total,1):.0f})")
    print(f"单任务成本估算: {((tp1-tp0+tc1-tc0)/max(total,1)) * 0.00000027 * 7.2:.4f} CNY "
          f"(deepseek-v4-flash 按 ¥0.27/M in + ¥1.10/M out 混合估)")
    out = "docs/test/AGENT_BENCH_20260810.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"summary": {
            "tasks": args.tasks, "n": args.n, "success_rate": ok/max(total,1),
            "avg_latency_ms": sum(lat)/len(lat) if lat else 0,
            "p95_latency_ms": lat[int(len(lat)*0.95)-1] if lat else 0,
            "tokens_prompt": tp1-tp0, "tokens_completion": tc1-tc0,
        }, "results": results}, ensure_ascii=False, indent=1))
    print(f"详情: {out}")

if __name__ == "__main__":
    main()
