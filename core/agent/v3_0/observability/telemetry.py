# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/telemetry.py
─────────────────────────────────────────
DialogMesh v3.0 统一可观测性门面（Telemetry Facade）。

用途：
  - 集成 Logger + Metrics + Alert + Tracer + Store 为一个统一接口
  - 对外暴露极简 API：record_turn、start_trace / end_trace、start_span / end_span
  - 支持配置化启动和优雅关闭

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.observability.models import (
    Alert,
    DecisionLogEntry,
    LogLevel,
    SessionMetricsSnapshot,
    TurnTrace,
)
from core.agent.v3_0.observability.logger import AsyncStructuredLogger
from core.agent.v3_0.observability.metrics import AsyncMetricsAggregator
from core.agent.v3_0.observability.alert import AsyncAlertEngine
from core.agent.v3_0.observability.tracer import AsyncTracer
from core.agent.v3_0.observability.store import AsyncObservabilityStore

logger = logging.getLogger(__name__)


class Telemetry:
    """
    统一可观测性门面。

    使用示例：
        async with Telemetry.from_config() as telemetry:
            trace = telemetry.start_trace("sess-123", 1, "scan 100")
            async with telemetry.span("COMPILE"):
                ... compile logic ...
            trace, alerts = await telemetry.end_trace(
                intent="scan_memory", confidence=0.9
            )
    """

    def __init__(
        self,
        logger: Optional[AsyncStructuredLogger] = None,
        metrics: Optional[AsyncMetricsAggregator] = None,
        alert: Optional[AsyncAlertEngine] = None,
        tracer: Optional[AsyncTracer] = None,
        store: Optional[AsyncObservabilityStore] = None,
        enabled: bool = True,
        store_enabled: bool = True,
        trace_enabled: bool = True,
    ):
        self.logger = logger or AsyncStructuredLogger()
        self.metrics = metrics or AsyncMetricsAggregator()
        self.alert = alert or AsyncAlertEngine()
        self.tracer = tracer or AsyncTracer()
        self.store = store
        self._enabled = enabled
        self._store_enabled = store_enabled and (store is not None)
        self._trace_enabled = trace_enabled

        # 告警回调：写入 store
        if self.store and self._store_enabled:
            self.alert._on_alert = self._on_alert_callback

    @classmethod
    async def from_config(
        cls, store_db_path: Optional[str] = None
    ) -> "Telemetry":
        """从配置构建 Telemetry。"""
        try:
            from core.agent.config import config as cfg_mgr
            cfg = cfg_mgr.get()

            obs_cfg: Dict[str, Any] = {}
            if hasattr(cfg, "observability") and cfg.observability:
                obs_cfg = cfg.observability if isinstance(cfg.observability, dict) else {}

            log_dir = "~/.memorygraph/logs/v3_0"
            if hasattr(cfg, "paths") and cfg.paths:
                paths = cfg.paths if isinstance(cfg.paths, dict) else {}
                log_dir = paths.get("log_dir", log_dir)

            store = AsyncObservabilityStore(
                db_path=store_db_path or "~/.memorygraph/v3_0_observability.db"
            )
            await store._ensure_connection()

            return cls(
                logger=AsyncStructuredLogger(
                    log_dir=log_dir,
                    buffer_size=obs_cfg.get("log_buffer_size", 200),
                    flush_interval_seconds=obs_cfg.get("log_flush_interval", 3.0),
                    retention_days=obs_cfg.get("log_retention_days", 30),
                ),
                metrics=AsyncMetricsAggregator(
                    max_sessions=obs_cfg.get("metrics_max_sessions", 100)
                ),
                alert=AsyncAlertEngine(),
                tracer=AsyncTracer(
                    max_traces=obs_cfg.get("tracer_max_traces", 1000)
                ),
                store=store,
                enabled=obs_cfg.get("enabled", True),
                store_enabled=obs_cfg.get("store_enabled", True),
                trace_enabled=obs_cfg.get("trace_enabled", True),
            )
        except Exception as e:
            logger.warning(f"[Telemetry] from_config failed: {e}, using defaults")
            store = AsyncObservabilityStore(
                db_path=store_db_path or "~/.memorygraph/v3_0_observability.db"
            )
            await store._ensure_connection()
            return cls(store=store)

    def _on_alert_callback(self, alert: Alert) -> None:
        """告警触发回调：异步写入 store。"""
        if self.store and self._store_enabled:
            # 创建后台任务避免阻塞告警检查
            try:
                asyncio.create_task(self.store.save_alert(alert))
            except RuntimeError:
                pass

    # ── 一键式记录 ───────────────────────────────────────────

    async def record_turn(
        self,
        session_id: str,
        turn_index: int,
        query: str,
        latency_ms: float,
        intent: str = "unknown",
        confidence: float = 0.0,
        execution_status: str = "unknown",
        required_clarification: bool = False,
        used_llm_fallback: bool = False,
        pcr_noise: float = 0.0,
        pcr_complexity: float = 0.0,
        pcr_cohesion: Optional[float] = None,
        trace_steps: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[TurnTrace], List[Alert]]:
        """
        记录一轮完整观测数据。
        返回 (trace, alerts)。
        """
        if not self._enabled:
            return None, []

        # 1. Logger
        await self.logger.log_turn(
            session_id=session_id,
            turn_index=turn_index,
            query=query,
            latency_ms=latency_ms,
            intent_result=intent,
            confidence=confidence,
            execution_status=execution_status,
            pcr_noise=pcr_noise,
            pcr_complexity=pcr_complexity,
            pcr_cohesion=pcr_cohesion,
            trace=trace_steps or [],
            metadata=metadata or {},
        )

        # 2. Metrics
        snapshot = await self.metrics.record_turn(
            session_id=session_id,
            confidence=confidence,
            latency_ms=latency_ms,
            intent=intent,
            required_clarification=required_clarification,
            used_llm_fallback=used_llm_fallback,
            execution_status=execution_status,
        )
        metrics_summary = snapshot.to_dict()

        # 3. Alerts
        alerts = await self.alert.check_session_metrics(metrics_summary)

        # 4. Store
        if self.store and self._store_enabled:
            await self.store.save_metrics(session_id, turn_index, metrics_summary)
            if trace_steps:
                trace = self._build_simple_trace(
                    session_id, turn_index, query, latency_ms, trace_steps, metadata
                )
                await self.store.save_trace(trace)

        return None, alerts

    # ── 链路追踪 API ───────────────────────────────────────────

    async def start_trace(
        self, session_id: str, turn_index: int, query: str
    ) -> Optional[TurnTrace]:
        """开始一轮追踪。"""
        if not self._enabled or not self._trace_enabled:
            return None
        return await self.tracer.start_turn(session_id, turn_index, query)

    async def end_trace(
        self,
        intent: str = "unknown",
        confidence: float = 0.0,
        execution_status: str = "unknown",
        required_clarification: bool = False,
        used_llm_fallback: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[TurnTrace], List[Alert]]:
        """结束当前追踪，并记录 metrics / alerts。"""
        if not self._enabled:
            return None, []

        trace = await self.tracer.end_turn()
        if trace is None:
            return None, []

        latency_ms = trace.total_duration_ms
        session_id = trace.session_id
        turn_index = trace.turn_index

        snapshot = await self.metrics.record_turn(
            session_id=session_id,
            confidence=confidence,
            latency_ms=latency_ms,
            intent=intent,
            required_clarification=required_clarification,
            used_llm_fallback=used_llm_fallback,
            execution_status=execution_status,
        )
        metrics_summary = snapshot.to_dict()
        alerts = await self.alert.check_session_metrics(metrics_summary)

        if self.store and self._store_enabled:
            await self.store.save_trace(trace)
            await self.store.save_metrics(session_id, turn_index, metrics_summary)

        return trace, alerts

    def span(
        self,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """返回 span 异步上下文管理器。"""
        return self.tracer.span(name, input_summary, metadata)

    async def start_span(
        self, name: str, input_summary: str = "", metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """显式开始一个 span。"""
        if not self._enabled or not self._trace_enabled:
            return
        await self.tracer.start_span(name, input_summary, metadata)

    async def end_span(
        self, status: str = "ok", output_summary: str = "", metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """显式结束当前 span。"""
        if not self._enabled or not self._trace_enabled:
            return
        await self.tracer.end_span(status, output_summary, metadata)

    async def annotate_span(self, key: str, value: Any) -> None:
        """为当前 span 添加注解。"""
        if not self._enabled or not self._trace_enabled:
            return
        await self.tracer.annotate_span(key, value)

    # ── 查询 API ───────────────────────────────────────────

    async def get_session_health(self, session_id: str) -> Dict[str, Any]:
        """获取会话健康度。"""
        snapshot = await self.metrics.get_session_snapshot(session_id)
        return snapshot.to_dict() if snapshot else {}

    async def get_global_health(self) -> Dict[str, Any]:
        """获取全局健康度。"""
        snapshot = await self.metrics.get_global_snapshot()
        return snapshot.to_dict()

    async def get_recent_traces(self, n: int = 10) -> List[TurnTrace]:
        """获取最近追踪。"""
        return await self.tracer.get_recent_traces(n)

    async def get_active_alerts(self, max_age_seconds: float = 3600) -> List[Alert]:
        """获取活跃告警。"""
        return await self.alert.get_active_alerts(max_age_seconds)

    async def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警统计。"""
        return await self.alert.get_alert_summary()

    async def get_store_stats(self) -> Dict[str, Any]:
        """获取持久化存储统计。"""
        if self.store and self._store_enabled:
            return await self.store.get_stats()
        return {"store_enabled": False}

    # ── 维护 ───────────────────────────────────────────

    async def flush(self) -> None:
        """强制 flush 所有缓冲数据。"""
        await self.logger.shutdown()
        await self.logger.start()

    async def cleanup(self, ttl_seconds: float = 30 * 24 * 3600) -> Dict[str, int]:
        """清理过期数据。"""
        log_count = self.logger.cleanup_old_logs(dry_run=False)
        store_counts = (0, 0, 0)
        if self.store and self._store_enabled:
            store_counts = await self.store.cleanup_old(ttl_seconds, dry_run=False)
        return {
            "logs_deleted": log_count,
            "traces_deleted": store_counts[0],
            "metrics_deleted": store_counts[1],
            "alerts_deleted": store_counts[2],
        }

    async def shutdown(self) -> None:
        """优雅关闭所有组件。"""
        await self.logger.shutdown()
        if self.store:
            await self.store.close()

    # ── 内部 ───────────────────────────────────────────

    def _build_simple_trace(
        self,
        session_id: str,
        turn_index: int,
        query: str,
        latency_ms: float,
        trace_steps: List[str],
        metadata: Optional[Dict[str, Any]],
    ) -> TurnTrace:
        """从 trace_steps 列表构造简单 TurnTrace。"""
        trace = TurnTrace(
            session_id=session_id,
            turn_index=turn_index,
            query=query,
        )
        base_ns = time.time_ns() - int(latency_ms * 1_000_000)
        for step in trace_steps:
            span = trace.add_span(name=step, start_ns=base_ns)
            base_ns += int(latency_ms / len(trace_steps) * 1_000_000) if trace_steps else 0
            span.end_ns = base_ns
        trace.end_ns = base_ns
        trace.metadata = metadata or {}
        return trace

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> Telemetry:
        await self.logger.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown()
