"""B3 白盒化: /v6/trace 结构化监控端点 (真数据, 非 stub).

与 stubs_api 的 /v6/trace + /v6/trace/recent 互补:
  /v6/trace/errors        错误聚合 (失败分布/失败率/最近失败明细)
  /v6/trace/turn/{id}     单次消息处理的 phase 明细 (逐拍回放)
  /v6/trace/turns         最近 N 次处理的 turn 级摘要列表

消费: 前端白盒面板 / CLI trace-errors / 测试导出报告。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v6/trace", tags=["v6-trace"])


def _get_tracer():
    from core.agent.cli.engine import get_engine
    eng = get_engine()
    if eng is None:
        return None
    return getattr(eng, "_tracer", None)


@router.get("/errors")
async def trace_errors(window: int = Query(200, ge=10, le=5000)):
    """结构化错误聚合: 哪个 phase 失败多少次、失败率、最近失败明细."""
    tracer = _get_tracer()
    if tracer is None:
        return {"available": False}
    if not hasattr(tracer, "error_report"):
        return {"available": False, "error": "error_report unavailable"}
    return {"available": True, **tracer.error_report(window=window)}


@router.get("/turn/{trace_id}")
async def trace_turn(trace_id: str, limit: int = Query(100, ge=1, le=1000)):
    """单次处理的 phase 明细 (按执行顺序), 供前端逐拍回放."""
    tracer = _get_tracer()
    if tracer is None:
        return {"available": False}
    if not hasattr(tracer, "turn_detail"):
        return {"available": False, "error": "turn_detail unavailable"}
    steps = tracer.turn_detail(trace_id=trace_id, limit=limit)
    return {"available": True, "trace_id": trace_id, "steps": steps,
            "step_count": len(steps)}


@router.get("/turns")
async def trace_turns(limit: int = Query(10, ge=1, le=100)):
    """最近 N 次处理的 turn 级摘要 (按 trace_id 分组, 含 step 数与失败数)."""
    tracer = _get_tracer()
    if tracer is None:
        return {"available": False}
    traces = tracer.recent(limit=limit) if hasattr(tracer, "recent") else []
    return {"available": True, "traces": traces, "count": len(traces)}
