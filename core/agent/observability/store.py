# -*- coding: utf-8 -*-
"""
core/agent/observability/store.py
───────────────────────────────
Observability SQLite store.
持久化 traces, metrics snapshots, alerts 到本地 SQLite，
与 sessions.db 分离（避免日志膨胀影响会话查询性能）。

设计要点：
  - 独立数据库：~/.memorygraph/observability.db
  - 三张表：traces, metrics, alerts
  - 按天分区索引，支持 TTL 清理
  - 批量写入优化（事务包裹）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.observability.tracer import TurnTrace, Span
from core.agent.observability.alert import Alert


class ObservabilityStore:
    """
    观测数据持久化存储。
    线程安全，懒加载连接。
    """

    def __init__(self, db_path: str = "~/.memorygraph/observability.db"):
        self._db_path = os.path.expanduser(db_path)
        Path(os.path.dirname(self._db_path)).mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    def _ensure_connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        with self._lock:
            if self._conn is not None:
                return self._conn
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row

            if not self._initialized:
                self._create_tables()
                self._initialized = True
            return self._conn

    def _create_tables(self) -> None:
        conn = self._conn
        conn.executescript(
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
                timestamp REAL
            );

            CREATE INDEX IF NOT EXISTS idx_obs_traces_session
                ON obs_traces(session_id, turn_index);
            CREATE INDEX IF NOT EXISTS idx_obs_traces_timestamp
                ON obs_traces(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_obs_metrics_session
                ON obs_metrics(session_id);
            CREATE INDEX IF NOT EXISTS idx_obs_metrics_timestamp
                ON obs_metrics(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_obs_alerts_timestamp
                ON obs_alerts(timestamp DESC);
            """
        )
        conn.commit()

    # ── Trace 写入 ───────────────────────────────────────────

    def save_trace(self, trace: TurnTrace) -> bool:
        """保存单条 trace。"""
        conn = self._ensure_connection()
        with self._lock:
            try:
                conn.execute(
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
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[ObservabilityStore] save_trace failed: {e}")
                return False

    def save_traces_batch(self, traces: List[TurnTrace]) -> bool:
        """批量保存 trace。"""
        conn = self._ensure_connection()
        with self._lock:
            try:
                conn.execute("BEGIN")
                for trace in traces:
                    conn.execute(
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
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[ObservabilityStore] save_traces_batch failed: {e}")
                return False

    # ── Metrics 写入 ───────────────────────────────────────────

    def save_metrics(self, session_id: str, turn_index: int, metrics_summary: Dict[str, Any]) -> bool:
        """保存指标快照。"""
        conn = self._ensure_connection()
        with self._lock:
            try:
                conn.execute(
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
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[ObservabilityStore] save_metrics failed: {e}")
                return False

    # ── Alerts 写入 ───────────────────────────────────────────

    def save_alerts(self, alerts: List[Alert]) -> bool:
        """批量保存告警。"""
        if not alerts:
            return True
        conn = self._ensure_connection()
        with self._lock:
            try:
                conn.execute("BEGIN")
                for alert in alerts:
                    conn.execute(
                        """
                        INSERT INTO obs_alerts
                            (severity, message, metric_name, threshold, actual_value, session_id, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            alert.severity.value,
                            alert.message,
                            alert.metric_name,
                            alert.threshold,
                            alert.actual_value,
                            alert.session_id,
                            alert.timestamp,
                        ),
                    )
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[ObservabilityStore] save_alerts failed: {e}")
                return False

    # ── 查询 ───────────────────────────────────────────

    def load_recent_traces(self, session_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """加载最近 trace。"""
        conn = self._ensure_connection()
        if session_id:
            rows = conn.execute(
                """
                SELECT data FROM obs_traces
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT data FROM obs_traces
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row["data"]))
            except json.JSONDecodeError:
                continue
        return results

    def load_metrics_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """加载某会话的指标历史。"""
        conn = self._ensure_connection()
        rows = conn.execute(
            """
            SELECT data FROM obs_metrics
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

        results = []
        for row in rows:
            try:
                results.append(json.loads(row["data"]))
            except json.JSONDecodeError:
                continue
        return results

    def load_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """加载最近告警。"""
        conn = self._ensure_connection()
        rows = conn.execute(
            """
            SELECT severity, message, metric_name, threshold, actual_value, session_id, timestamp
            FROM obs_alerts
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            {
                "severity": r["severity"],
                "message": r["message"],
                "metric_name": r["metric_name"],
                "threshold": r["threshold"],
                "actual_value": r["actual_value"],
                "session_id": r["session_id"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    # ── 维护 ───────────────────────────────────────────

    def cleanup_old(self, ttl_seconds: float, dry_run: bool = False) -> Tuple[int, int, int]:
        """清理过期数据。返回 (traces_deleted, metrics_deleted, alerts_deleted)。"""
        conn = self._ensure_connection()
        cutoff = time.time() - ttl_seconds
        counts = [0, 0, 0]

        with self._lock:
            for idx, table in enumerate(["obs_traces", "obs_metrics", "obs_alerts"]):
                row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM {table} WHERE timestamp < ?",
                    (cutoff,),
                ).fetchone()
                counts[idx] = row["cnt"] if row else 0

            if not dry_run:
                try:
                    conn.execute("BEGIN")
                    for table in ["obs_traces", "obs_metrics", "obs_alerts"]:
                        conn.execute(
                            f"DELETE FROM {table} WHERE timestamp < ?",
                            (cutoff,),
                        )
                    conn.commit()
                except sqlite3.Error as e:
                    conn.rollback()
                    print(f"[ObservabilityStore] cleanup_old failed: {e}")
                    return 0, 0, 0

        return tuple(counts)

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计。"""
        conn = self._ensure_connection()
        with self._lock:
            t_row = conn.execute("SELECT COUNT(*) as cnt FROM obs_traces").fetchone()
            m_row = conn.execute("SELECT COUNT(*) as cnt FROM obs_metrics").fetchone()
            a_row = conn.execute("SELECT COUNT(*) as cnt FROM obs_alerts").fetchone()

        return {
            "traces": t_row["cnt"] if t_row else 0,
            "metrics": m_row["cnt"] if m_row else 0,
            "alerts": a_row["cnt"] if a_row else 0,
            "db_path": self._db_path,
        }

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None
