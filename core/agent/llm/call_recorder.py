# -*- coding: utf-8 -*-
"""LLM 调用观测（2026-08-16, 执行链路高可用）。

背景: 执行层各 LLM 调用点（tool_loop / 意图分类 / 规划 / 通用回复）散落,
无集中统计 → 卡死/空返回排查靠猜。本模块: 内存窗口统计 + JSONL 落盘,
白盒端点 /v6/llm-calls 可查"哪个阶段慢/空/重试"。

记录字段: stage / latency_ms / ok / empty / retries / error / ts。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_path() -> str:
    # 项目根 data/（与 introspection/experience 等一致）; 2026-08-16 修:
    # 此前少一层 dirname, 落到了 core/data/, 与 data/ 约定不一致。
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "data", "llm_calls.jsonl")


class LLMCallRecorder:
    """线程安全的调用观测器（内存窗口 + JSONL 落盘）。"""

    def __init__(self, path: Optional[str] = None,
                 max_entries: int = 2000,
                 persist_every: int = 50):
        self._lock = threading.Lock()
        self._calls: List[Dict[str, Any]] = []
        self._max = max_entries
        self._path = path or _default_path()
        self._persist_every = persist_every
        self._since_persist = 0
        self._load_tail()

    def _load_tail(self) -> None:
        """重启后从 JSONL 尾部恢复窗口（观测不丢）。"""
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[-self._max:]:
                line = line.strip()
                if line:
                    try:
                        self._calls.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("llm calls tail load failed: %s", e)

    def record(self, stage: str, latency_ms: float, ok: bool,
               empty: bool = False, retries: int = 0,
               error: str = "") -> None:
        entry = {
            "ts": time.time(), "stage": stage,
            "latency_ms": round(latency_ms, 1),
            "ok": bool(ok), "empty": bool(empty),
            "retries": int(retries), "error": str(error)[:120],
        }
        with self._lock:
            self._calls.append(entry)
            if len(self._calls) > self._max:
                self._calls = self._calls[-self._max:]
            self._since_persist += 1
            should_persist = self._since_persist >= self._persist_every
        if should_persist:
            self._persist()

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with self._lock:
                snapshot = list(self._calls)
                self._since_persist = 0
            with open(self._path, "a", encoding="utf-8") as f:
                for e in snapshot[-self._persist_every:]:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("llm calls persist failed: %s", e)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            calls = list(self._calls)
        if not calls:
            return {"total": 0}
        by_stage: Dict[str, List[float]] = {}
        empty_total = 0
        error_total = 0
        retry_total = 0
        for c in calls:
            by_stage.setdefault(c.get("stage", "?"), []).append(
                float(c.get("latency_ms", 0)))
            if c.get("empty"):
                empty_total += 1
            if c.get("error"):
                error_total += 1
            retry_total += int(c.get("retries", 0))
        stage_stats = {}
        for stage, lats in by_stage.items():
            lats_sorted = sorted(lats)
            n = len(lats_sorted)
            stage_stats[stage] = {
                "count": n,
                "avg_ms": round(sum(lats_sorted) / n, 1),
                "p50_ms": round(lats_sorted[n // 2], 1),
                "p95_ms": round(lats_sorted[min(
                    n - 1, int(n * 0.95))], 1),
                "max_ms": round(lats_sorted[-1], 1),
            }
        return {
            "total": len(calls),
            "empty": empty_total,
            "errors": error_total,
            "retries": retry_total,
            "by_stage": stage_stats,
        }

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._calls[-n:])


_recorder: Optional[LLMCallRecorder] = None


def _get_recorder() -> LLMCallRecorder:
    global _recorder
    if _recorder is None:
        _recorder = LLMCallRecorder()
    return _recorder


def record_llm_call(stage: str, latency_ms: float, ok: bool,
                    empty: bool = False, retries: int = 0,
                    error: str = "") -> None:
    try:
        _get_recorder().record(
            stage, latency_ms, ok, empty=empty,
            retries=retries, error=error)
    except Exception:
        pass


def llm_call_stats() -> Dict[str, Any]:
    try:
        return _get_recorder().stats()
    except Exception:
        return {"total": 0}


def llm_call_recent(n: int = 20) -> List[Dict[str, Any]]:
    try:
        return _get_recorder().recent(n)
    except Exception:
        return []
