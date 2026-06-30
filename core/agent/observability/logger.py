# -*- coding: utf-8 -*-
"""
core/agent/observability/logger.py
────────────────────────────────
Structured JSONL logger.

设计要点：
  - 每轮输出一行 JSON，可机器解析
  - 异步写入（缓冲 + 定时 flush）
  - 按天切分文件
  - 保留 30 天（可配置）
  - 无外部依赖（不依赖 ELK）
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class StructuredLogger:
    """
    结构化 JSONL 日志器。
    每轮决策链输出一条 JSON 记录。
    """

    def __init__(
        self,
        log_dir: str = "~/.memorygraph/logs",
        buffer_size: int = 50,          # 缓冲条数
        flush_interval_seconds: float = 5.0,
        retention_days: int = 30,
    ):
        self._log_dir = Path(log_dir).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval_seconds
        self._retention_days = retention_days

        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._current_file: Optional[Path] = None
        self._file_handle: Optional[Any] = None

        # 后台 flush 线程
        self._shutdown_event = threading.Event()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="log-flusher")
        self._flush_thread.start()

    # ── 日志写入 ───────────────────────────────────────────

    def log_turn(
        self,
        session_id: str,
        turn_index: int,
        query: str,
        latency_ms: float,
        intent_result: Optional[str] = None,
        confidence: float = 0.0,
        execution_status: Optional[str] = None,
        pcr_noise: float = 0.0,
        pcr_complexity: float = 0.0,
        trace: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录单轮决策日志。"""
        record = {
            "timestamp": time.time(),
            "session_id": session_id[:8] + "...",  # 脱敏
            "turn_index": turn_index,
            "query": query[:200],  # 截断过长查询
            "latency_ms": round(latency_ms, 2),
            "intent_result": intent_result,
            "confidence": round(confidence, 3),
            "execution_status": execution_status,
            "pcr_noise": round(pcr_noise, 3),
            "pcr_complexity": round(pcr_complexity, 3),
            "trace": trace or [],
            "metadata": metadata or {},
        }

        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self._buffer_size:
                self._flush()

    # ── 文件管理 ───────────────────────────────────────────

    def _get_current_file(self) -> Path:
        """获取当天日志文件路径。"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._log_dir / f"decisions-{today}.jsonl"

    def _ensure_file(self) -> None:
        """确保文件句柄打开。"""
        target = self._get_current_file()
        if self._current_file != target:
            # 关闭旧文件
            if self._file_handle is not None:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
            # 打开新文件
            self._file_handle = open(target, "a", encoding="utf-8")
            self._current_file = target

    def _flush(self) -> None:
        """将缓冲写入文件。"""
        if not self._buffer:
            return

        self._ensure_file()
        if self._file_handle is None:
            return

        # 批量写入
        lines = []
        for record in self._buffer:
            lines.append(json.dumps(record, ensure_ascii=False, default=str))

        try:
            self._file_handle.write("\n".join(lines) + "\n")
            self._file_handle.flush()
        except Exception as e:
            print(f"[StructuredLogger] flush failed: {e}")
        finally:
            self._buffer.clear()

    def _flush_loop(self) -> None:
        """后台定时 flush 线程。"""
        while not self._shutdown_event.wait(self._flush_interval):
            with self._lock:
                self._flush()

    # ── 生命周期 ───────────────────────────────────────────

    def shutdown(self) -> None:
        """优雅关闭：flush 所有缓冲并关闭文件。"""
        self._shutdown_event.set()
        with self._lock:
            self._flush()
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except Exception:
                pass
        if self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

    # ── 日志读取 ───────────────────────────────────────────

    def read_recent(self, n_lines: int = 100) -> List[Dict[str, Any]]:
        """读取最近 N 条日志。"""
        target = self._get_current_file()
        if not target.exists():
            return []

        try:
            with open(target, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return []

        records = []
        for line in lines[-n_lines:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    # ── 维护 ───────────────────────────────────────────

    def cleanup_old_logs(self, dry_run: bool = False) -> int:
        """清理超过保留期的日志文件。"""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        count = 0

        for file in self._log_dir.glob("decisions-*.jsonl"):
            try:
                date_str = file.stem.replace("decisions-", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    if not dry_run:
                        file.unlink()
                    count += 1
            except ValueError:
                continue

        return count
