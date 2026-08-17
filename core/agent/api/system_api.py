"""系统运行信息端点（2026-08-17, 工程链副屏「后台进程」）。

只读: 当前进程内的后台线程（probe/warmup/diagnosis/price-sync 等）+ 内存。
"""
from __future__ import annotations

import os
import threading

from fastapi import APIRouter

router = APIRouter(prefix="/v6/system", tags=["v6-system"])

# 已知后台工作线程（启动器注册的名字）
KNOWN_WORKERS = {
    "price-sync": "价格目录同步",
    "probe": "主动体检",
    "warmup": "模型预热",
    "diagnosis": "异步诊断",
}


def read_processes() -> dict:
    threads = []
    for t in threading.enumerate():
        label = KNOWN_WORKERS.get(t.name, "")
        threads.append({
            "name": t.name,
            "label": label,
            "daemon": t.daemon,
            "alive": t.is_alive(),
            "ident": t.ident,
        })
    threads.sort(key=lambda x: (not x["alive"], x["name"].lower()))
    mem = {}
    try:
        import resource
        mem = {"rss_bytes": resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss * 1024}
    except Exception:
        pass
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem = {"rss_bytes": proc.memory_info().rss,
               "cpu_percent": proc.cpu_percent(interval=None)}
    except Exception:
        pass
    return {"threads": threads, "count": len(threads),
            "memory": mem}


@router.get("/processes")
async def system_processes():
    return read_processes()
