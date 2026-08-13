# -*- coding: utf-8 -*-
"""网关本地基准（2026-08-13）: 缓存命中路径 = 纯网关开销。

指标: p50/p99 延迟 + 并发吞吐（req/s）+ 热更新生效时间。
缓存路径（相同请求）不经上游 → 隔离网关自身开销。

用法: .venv/Scripts/python.exe scripts/_gw_bench.py
"""
import json
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GW = "http://127.0.0.1:8080"
BODY = json.dumps({
    "provider": "deepseek", "model": "deepseek-v4-flash",
    "thinking": {"type": "disabled"},
    "messages": [{"role": "user", "content": "缓存基准 ping"}],
    "max_tokens": 16, "temperature": 0.0,
}).encode()


def one(_):
    req = urllib.request.Request(GW + "/v1/chat/completions", data=BODY,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000


def main():
    # 预热（首次进缓存）
    one(0)
    time.sleep(0.2)
    # 串行延迟
    lats = [one(i) for i in range(200)]
    lats.sort()
    p50 = lats[len(lats) // 2]
    p99 = lats[int(len(lats) * 0.99)]
    print("串行 200 次（缓存命中）: p50=%.2fms p99=%.2fms max=%.2fms" % (
        p50, p99, lats[-1]))
    # 并发吞吐
    for workers in (8, 32):
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, range(1000)))
        dt = time.perf_counter() - t0
        print("并发 %d: 1000 请求 %.1fs = %.0f req/s" % (
            workers, dt, 1000 / dt))


if __name__ == "__main__":
    main()
