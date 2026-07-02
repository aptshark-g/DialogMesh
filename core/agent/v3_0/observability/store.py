# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/store.py
──────────────────────────────────────
DialogMesh v3.0 异步观测数据持久化存储。

用途：
  - 使用 aiosqlite 异步写入 SQLite（与同步 store 分离，避免阻塞）
  - 三张表：traces, metrics, alerts
  - 支持批量写入、TTL 清理、WAL 模式

版本：3.0.0

依赖：
  - aiosqlite（已在 requirements.txt 中）
  - 当 aiosqlite 不可用时，自动降级为内存存储
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # type: ignore

from core.agent.v3_0.observability.models import Alert, TurnTrace, SessionMetricsSnapshot

logger = logging.getLogger(__name__)


class AsyncObservabilityStore:
    """
    异步观测数据持久化存储。

    设计要点：
      - 独立数据库：~/.memorygraph/v3_0_observability.db
      - 三张表：obs_traces, obs_metrics, obs_alerts
      - WAL 模式，支持高并发读取
      - 批量写入优化（事务包裹）
      - 当 aiosqlite 不可用时自动降级为内存存储
    """

    def __init__(self, db_path: str = "~/.memorygraph/v3_0_observability.db"):
        self._db_path = os.path.expanduser(db_path)
        Path(os.path.dirname(self._db_path)).mkdir(parents=True, exist_ok=True)

        self._conn: Optional[Any] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._fallback_mode = aiosqlite is None

        if self._fallback_mode:
            logger.warning(
                "[AsyncObservabilityStore] aiosqlite not available, using in-memory fallback"
            )
            self._memory_store: Dict[str, List[Dict[str, Any]]] = {
                "traces": [],
                "metrics": [],
                "alerts": [],
            }

    # ── 连接管理 ───────────────────────────────────────────

    async def _ensure_connection(self) -> Any:
        if self._fallback_mode:
            return None
        if self._conn is not None:
            return self._conn

        async with self._lock:
            if self._conn is not None:
                return self._conn

            self._conn = await aiosqlite.connect(self._db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")

            if not self._initialized:
                await self._create_tables()
                self._initialized = True

            return self._conn

    async def _create_tables(self) -> None:
        if self._fallback_mode:
            return
        conn = await self._ensure_connection()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS obs_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                session_id TEXT,
                turn_index INTEGER,
                query TEXT,
                total_duration_ms REAL,
                has_error INTEGER,
                span_count INTEGER,
                data JSON,
                timestamp REAL,
                date TEXT GENERATED ALWAYS AS (date(timestamp, 'unixepoch')) STORED
            );

            CREATE TABLE IF NOT EXISTS obs_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn_index INTEGER,
                total_turns INTEGER,
                clarification_rate REAL,
                llm_fallback_rate REAL,
                avg_confidence REAL,
                avg_latency_ms REAL,
                health_score REAL,
                intent_distribution JSON,
                data JSON,
                timestamp REAL
            );

            CREATE TABLE IF NOT EXISTS obs_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                severity TEXT,
                message TEXT,
                metric_name TEXT,
                threshold REAL,
                actual_value REAL,
                session_id TEXT,
                dedup_key TEXT,
                timestamp REAL
            );

            CREATE INDEX IF NOT EXISTS idx_v3_traces_session
                ON obs_traces(session_id, turn_index);
            CREATE INDEX IF NOT EXISTS idx_v3_traces_timestamp
                ON obs_traces(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_v3_metrics_session
                ON obs_metrics(session_id);
            CREATE INDEX IF NOT EXISTS idx_v3_metrics_timestamp
                ON obs_metrics(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_v3_alerts_timestamp
                ON obs_alerts(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_v3_alerts_dedup
                ON obs_alerts(dedup_key, timestamp DESC);
            """
        )
        await conn.commit()

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._fallback_mode:
            return
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ── Trace 写入 ───────────────────────────────────────────

    async def save_trace(self, trace: TurnTrace) -> bool:
        """保存单条 trace。"""
        if self._fallback_mode:
            async with self._lock:
                self._memory_store["traces"].append(trace.to_dict())
            return True

        conn = await self._ensure_connection()
        async with self._lock:
            try:
                await conn.execute(
                    """
                    INSERT INTO obs_traces
                        (trace_id, session_id, turn_index, query, total_duration_ms,
                         has_error, span_count, data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.trace_id,
                        trace.session_id,
                        trace.turn_index,
                        trace.query[:200],
                        trace.total_duration_ms,
                        1 if trace.has_error else 0,
                        len(trace.spans),
                        json.dumps(trace.to_dict(), ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"[AsyncObservabilityStore] save_trace failed: {e}")
                return False

    async def save_traces_batch(self, traces: List[TurnTrace]) -> bool:
        """批量保存 trace。"""
        if not traces:
            return True
        if self._fallback_mode:
            async with self._lock:
                for t in traces:
                    self._memory_store["traces"].append(t.to_dict())
            return True

        conn = await self._ensure_connection()
        async with self._lock:
            try:
                await conn.execute("BEGIN")
                for trace in traces:
                    await conn.execute(
                        """
                        INSERT INTO obs_traces
                            (trace_id, session_id, turn_index, query, total_duration_ms,
                             has_error, span_count, data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            trace.trace_id,
                            trace.session_id,
                            trace.turn_index,
                            trace.query[:200],
                            trace.total_duration_ms,
                            1 if trace.has_error else 0,
                            len(trace.spans),
                            json.dumps(trace.to_dict(), ensure_ascii=False, default=str),
                            time.time(),
                        ),
                    )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"[AsyncObservabilityStore] save_traces_batch failed: {e}")
                return False

    # ── Metrics 写入 ───────────────────────────────────────────

    async def save_metrics(
        self, session_id: str, turn_index: int, metrics_summary: Dict[str, Any]
    ) -> bool:
        """保存指标快照。"""
        if self._fallback_mode:
            async with self._lock:
                self._memory_store["metrics"].append(
                    {
                        "session_id": session_id,
                        "turn_index": turn_index,
                        "data": metrics_summary,
                        "timestamp": time.time(),
                    }
                )
            return True

        conn = await self._ensure_connection()
        async with self._lock:
            try:
                await conn.execute(
                    """
                    INSERT INTO obs_metrics
                        (session_id, turn_index, total_turns, clarification_rate,
                         llm_fallback_rate, avg_confidence, avg_latency_ms,
                         health_score, intent_distribution, data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        turn_index,
                        metrics_summary.get("total_turns", 0),
                        metrics_summary.get("clarification_rate", 0.0),
                        metrics_summary.get("llm_fallback_rate", 0.0),
                        metrics_summary.get("avg_confidence", 0.0),
                        metrics_summary.get("avg_latency_ms", 0.0),
                        metrics_summary.get("health_score", 0.0),
                        json.dumps(metrics_summary.get("intent_distribution", {}), ensure_ascii=False),
                        json.dumps(metrics_summary, ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"[AsyncObservabilityStore] save_metrics failed: {e}")
                return False

    # ── Alerts 写入 ───────────────────────────────────────────

    async def save_alert(self, alert: Alert) -> bool:
        """保存单条告警。"""
        if self._fallback_mode:
            async with self._lock:
                self._memory_store["alerts"].append(alert.to_dict())
            return True

        conn = await self._ensure_connection()
        async with self._lock:
            try:
                await conn.execute(
                    """
                    INSERT INTO obs_alerts
                        (severity, message, metric_name, threshold, actual_value,
                         session_id, dedup_key, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.severity.value,
                        alert.message,
                        alert.metric_name,
                        alert.threshold,
                        alert.actual_value,
                        alert.session_id,
                        alert.dedup_key,
                        alert.timestamp,
                    ),
                )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"[AsyncObservabilityStore] save_alert failed: {e}")
                return False

    async def save_alerts(self, alerts: List[Alert]) -> bool:
        """批量保存告警。"""
        if not alerts:
            return True
        if self._fallback_mode:
            async with self._lock:
                for a in alerts:
                    self._memory_store["alerts"].append(a.to_dict())
            return True

        conn = await self._ensure_connection()
        async with self._lock:
            try:
                await conn.execute("BEGIN")
                for alert in alerts:
                    await conn.execute(
                        """
                        INSERT INTO obs_alerts
                            (severity, message, metric_name, threshold, actual_value,
                             session_id, dedup_key, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            alert.severity.value,
                            alert.message,
                            alert.metric_name,
                            alert.threshold,
                            alert.actual_value,
                            alert.session_id,
                            alert.dedup_key,
                            alert.timestamp,
                        ),
                    )
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"[AsyncObservabilityStore] save_alerts failed: {e}")
                return False

    # ── 查询 ───────────────────────────────────────────

    async def get_recent_traces(
        self, limit: int = 20, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查询最近 trace。"""
        if self._fallback_mode:
            async with self._lock:
                items = self._memory_store["traces"][-limit:]
            return items

        conn = await self._ensure_connection()
        query = "SELECT data FROM obs_traces WHERE 1=1"
        params: List[Any] = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def get_recent_metrics(
        self, limit: int = 20, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查询最近指标快照。"""
        if self._fallback_mode:
            async with self._lock:
                items = [
                    m["data"] for m in self._memory_store["metrics"][-limit:]
                ]
            return items

        conn = await self._ensure_connection()
        query = "SELECT data FROM obs_metrics WHERE 1=1"
        params: List[Any] = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def get_recent_alerts(
        self, limit: int = 50, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查询最近告警。"""
        if self._fallback_mode:
            async with self._lock:
                items = self._memory_store["alerts"][-limit:]
            return items

        conn = await self._ensure_connection()
        query = "SELECT * FROM obs_alerts WHERE 1=1"
        params: List[Any] = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    # ── 统计 ───────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """获取存储统计。"""
        if self._fallback_mode:
            async with self._lock:
                return {
                    "obs_traces_count": len(self._memory_store["traces"]),
                    "obs_metrics_count": len(self._memory_store["metrics"]),
                    "obs_alerts_count": len(self._memory_store["alerts"]),
                    "fallback_mode": True,
                }

        conn = await self._ensure_connection()
        stats = {}
        for table in ["obs_traces", "obs_metrics", "obs_alerts"]:
            async with conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ) as cursor:
                row = await cursor.fetchone()
                stats[f"{table}_count"] = row[0] if row else 0
        return stats

    # ── 维护 ───────────────────────────────────────────

    async def cleanup_old(
        self, ttl_seconds: float = 30 * 24 * 3600, dry_run: bool = False
    ) -> Tuple[int, int, int]:
        """清理超过 TTL 的数据。返回 (traces_deleted, metrics_deleted, alerts_deleted)。"""
        cutoff = time.time() - ttl_seconds
        if self._fallback_mode:
            async with self._lock:
                counts = [0, 0, 0]
                for i, key in enumerate(["traces", "metrics", "alerts"]):
                    original = len(self._memory_store[key])
                    if not dry_run:
                        self._memory_store[key] = [
                            item for item in self._memory_store[key]
                            if item.get("timestamp", 0) > cutoff
                        ]
                    counts[i] = original - len(self._memory_store[key])
                return tuple(counts)  # type: ignore

        conn = await self._ensure_connection()
        deleted = [0, 0, 0]

        async with self._lock:
            tables = ["obs_traces", "obs_metrics", "obs_alerts"]
            for i, table in enumerate(tables):
                try:
                    if dry_run:
                        async with conn.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE timestamp < ?",
                            (cutoff,),
                        ) as cursor:
                            row = await cursor.fetchone()
                            deleted[i] = row[0] if row else 0
                    else:
                        await conn.execute(
                            f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,)
                        )
                        deleted[i] = conn.total_changes
                except Exception as e:
                    logger.warning(f"[AsyncObservabilityStore] cleanup {table} failed: {e}")
            await conn.commit()

        return tuple(deleted)  # type: ignore

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> AsyncObservabilityStore:
        await self._ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
