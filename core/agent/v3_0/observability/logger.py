# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/logger.py
──────────────────────────────────────
DialogMesh v3.0 异步结构化日志器。

用途：
  - 以异步方式写入 JSONL 日志，避免阻塞主线程
  - 支持按天切分、异步缓冲、批量 flush
  - 支持 LogLevel 过滤和日志采样

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from core.agent.v3_0.observability.models import LogEntry, LogLevel, DecisionLogEntry


logger = logging.getLogger(__name__)


class AsyncStructuredLogger:
    """
    异步结构化 JSONL 日志器。

    设计要点：
      - 基于 asyncio.Queue 的缓冲队列，写操作不阻塞业务逻辑
      - 后台任务批量 flush 到磁盘
      - 按天切分文件，支持日志保留期自动清理
      - 支持日志级别过滤（默认 INFO 及以上）
    """

    def __init__(
        self,
        log_dir: str = "~/.memorygraph/logs/v3_0",
        buffer_size: int = 200,
        flush_interval_seconds: float = 3.0,
        retention_days: int = 30,
        min_level: LogLevel = LogLevel.INFO,
        enable_console: bool = False,
        on_flush: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ):
        self._log_dir = Path(log_dir).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval_seconds
        self._retention_days = retention_days
        self._min_level = min_level
        self._enable_console = enable_console
        self._on_flush = on_flush

        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._buffer: List[Dict[str, Any]] = []
        self._current_file: Optional[Path] = None
        self._file_handle: Optional[Any] = None
        self._shutdown_event = asyncio.Event()
        self._flush_task: Optional[asyncio.Task] = None

        self._lock = asyncio.Lock()

    # ── 生命周期 ───────────────────────────────────────────

    async def start(self) -> None:
        """启动后台 flush 任务。"""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(
                self._flush_loop(), name="v3_0_log_flusher"
            )
            logger.debug("[AsyncStructuredLogger] flush loop started")

    async def shutdown(self) -> None:
        """优雅关闭：flush 所有缓冲并关闭文件。"""
        self._shutdown_event.set()
        if self._flush_task and not self._flush_task.done():
            try:
                await asyncio.wait_for(self._flush_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("[AsyncStructuredLogger] flush loop timeout during shutdown")

        async with self._lock:
            await self._flush_buffer()
            if self._file_handle is not None:
                try:
                    self._file_handle.close()
                except Exception as e:
                    logger.warning(f"[AsyncStructuredLogger] close file error: {e}")

    # ── 日志写入 API ───────────────────────────────────────────

    async def log(
        self,
        level: LogLevel,
        source: str,
        message: str,
        session_id: Optional[str] = None,
        turn_index: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """写入一条通用日志。"""
        if self._level_value(level) < self._level_value(self._min_level):
            return

        entry = LogEntry(
            timestamp=time.time(),
            level=level,
            source=source,
            message=message,
            session_id=session_id,
            turn_index=turn_index,
            metadata=metadata or {},
            trace_id=trace_id,
        )
        await self._enqueue(entry.to_dict())

    async def log_decision(self, entry: DecisionLogEntry) -> None:
        """写入决策链日志。"""
        await self._enqueue(entry.to_dict())

    async def log_turn(
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
        pcr_cohesion: Optional[float] = None,
        trace: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录单轮决策日志（向后兼容接口）。"""
        entry = DecisionLogEntry(
            timestamp=time.time(),
            session_id=session_id,
            turn_index=turn_index,
            query=query,
            total_latency_ms=latency_ms,
            intent_category=intent_result,
            intent_confidence=confidence,
            execution_status=execution_status,
            pcr_noise=pcr_noise,
            pcr_complexity=pcr_complexity,
            pcr_cohesion=pcr_cohesion,
            metadata=metadata or {},
        )
        await self._enqueue(entry.to_dict())

    # ── 便捷方法 ───────────────────────────────────────────

    async def debug(self, source: str, message: str, **kwargs) -> None:
        await self.log(LogLevel.DEBUG, source, message, **kwargs)

    async def info(self, source: str, message: str, **kwargs) -> None:
        await self.log(LogLevel.INFO, source, message, **kwargs)

    async def warning(self, source: str, message: str, **kwargs) -> None:
        await self.log(LogLevel.WARNING, source, message, **kwargs)

    async def error(self, source: str, message: str, **kwargs) -> None:
        await self.log(LogLevel.ERROR, source, message, **kwargs)

    async def critical(self, source: str, message: str, **kwargs) -> None:
        await self.log(LogLevel.CRITICAL, source, message, **kwargs)

    # ── 内部实现 ───────────────────────────────────────────

    async def _enqueue(self, record: Dict[str, Any]) -> None:
        """将记录放入队列。"""
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning("[AsyncStructuredLogger] queue full, dropping record")

    async def _flush_loop(self) -> None:
        """后台定时 flush 协程。"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=self._flush_interval
                )
            except asyncio.TimeoutError:
                pass

            async with self._lock:
                await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        """将缓冲队列中的数据批量写入文件。"""
        # 从队列中批量取出
        while not self._queue.empty() and len(self._buffer) < self._buffer_size:
            try:
                self._buffer.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not self._buffer:
            return

        self._ensure_file()
        if self._file_handle is None:
            return

        lines = []
        for record in self._buffer:
            lines.append(json.dumps(record, ensure_ascii=False, default=str))

        try:
            self._file_handle.write("\n".join(lines) + "\n")
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())
        except Exception as e:
            logger.error(f"[AsyncStructuredLogger] flush failed: {e}")
        finally:
            if self._on_flush:
                try:
                    self._on_flush(list(self._buffer))
                except Exception:
                    pass
            self._buffer.clear()

    def _ensure_file(self) -> None:
        """确保当天日志文件已打开。"""
        today = datetime.now().strftime("%Y-%m-%d")
        target = self._log_dir / f"v3_decisions-{today}.jsonl"

        if self._current_file != target:
            if self._file_handle is not None:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
            self._file_handle = open(target, "a", encoding="utf-8")
            self._current_file = target

    # ── 日志读取 ───────────────────────────────────────────

    def read_recent(self, n_lines: int = 100) -> List[Dict[str, Any]]:
        """读取最近 N 条日志（同步阻塞，仅用于调试）。"""
        target = self._get_current_file()
        if not target.exists():
            return []

        try:
            with open(target, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning(f"[AsyncStructuredLogger] read_recent failed: {e}")
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

    def _get_current_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self._log_dir / f"v3_decisions-{today}.jsonl"

    # ── 维护 ───────────────────────────────────────────

    def cleanup_old_logs(self, dry_run: bool = False) -> int:
        """清理超过保留期的日志文件。"""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        count = 0

        for file in self._log_dir.glob("v3_decisions-*.jsonl"):
            try:
                date_str = file.stem.replace("v3_decisions-", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    if not dry_run:
                        file.unlink()
                    count += 1
            except ValueError:
                continue

        return count

    # ── 工具方法 ───────────────────────────────────────────

    @staticmethod
    def _level_value(level: LogLevel) -> int:
        """日志级别数值映射。"""
        mapping = {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50,
        }
        return mapping.get(level, 0)

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> AsyncStructuredLogger:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown()
