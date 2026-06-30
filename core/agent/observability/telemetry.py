# -*- coding: utf-8 -*-
"""
core/agent/observability/telemetry.py
─────────────────────────────────────
Telemetry facade: unified observability interface.

设计要点：
  - 集成：Logger + Metrics + Alert + Tracer + Store
  - 对外只暴露两个 API：
      - record_turn(...)      : 记录一轮完整数据（一键式）
      - start_span / end_span : 链路追踪细粒度控制
  - 配置化：从 ConfigManager 读取开关、阈值、路径
  - 零外部依赖：不依赖 Prometheus / Grafana / ELK
  - 与 AgentPipeline 集成点：在 process() 前后调用

调用示例：
    telemetry = Telemetry.from_config()
    telemetry.start_trace(session_id, turn_idx, query)
    telemetry.start_span("COMPILE")
    ... compile logic ...
    telemetry.end_span("ok", output_summary="fast_path")
    telemetry.end_trace(
        intent="scan_memory",
        confidence=0.9,
        execution_status="success",
        metadata={"cohesion": 0.7}
    )
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.observability.logger import StructuredLogger
from core.agent.observability.metrics import MetricsAggregator
from core.agent.observability.alert import AlertEngine, Alert
from core.agent.observability.tracer import Tracer, TurnTrace
from core.agent.observability.store import ObservabilityStore


class Telemetry:
    """
    统一观测门面。
    """

    def __init__(
        self,
        logger: Optional[StructuredLogger] = None,
        metrics: Optional[MetricsAggregator] = None,
        alert: Optional[AlertEngine] = None,
        tracer: Optional[Tracer] = None,
        store: Optional[ObservabilityStore] = None,
        enabled: bool = True,
        store_enabled: bool = True,
        trace_enabled: bool = True,
    ):
        self.logger = logger or StructuredLogger()
        self.metrics = metrics or MetricsAggregator()
        self.alert = alert or AlertEngine()
        self.tracer = tracer or Tracer()
        self.store = store
        self._enabled = enabled
        self._store_enabled = store_enabled and (store is not None)
        self._trace_enabled = trace_enabled

        # 告警回调：触发时写入 store
        if self.store and self._store_enabled:
            self.alert._on_alert = self._on_alert_callback

    @classmethod
    def from_config(cls, store_db_path: Optional[str] = None) -> "Telemetry":
        """从 ConfigManager 构建 Telemetry。"""
        try:
            from core.agent.config import config as cfg_mgr
            cfg = cfg_mgr.get()

            # 读取 observability 配置段
            obs_cfg = {}
            if hasattr(cfg, "observability") and cfg.observability:
                obs_cfg = cfg.observability if isinstance(cfg.observability, dict) else {}

            # 读取路径配置
            log_dir = "~/.memorygraph/logs"
            if hasattr(cfg, "paths") and cfg.paths:
                paths = cfg.paths if isinstance(cfg.paths, dict) else {}
                log_dir = paths.get("log_dir", log_dir)

            store = ObservabilityStore(db_path=store_db_path or "~/.memorygraph/observability.db")

            return cls(
                logger=StructuredLogger(
                    log_dir=log_dir,
                    buffer_size=obs_cfg.get("log_buffer_size", 50),
                    flush_interval_seconds=obs_cfg.get("log_flush_interval", 5.0),
                    retention_days=obs_cfg.get("log_retention_days", 30),
                ),
                metrics=MetricsAggregator(max_sessions=obs_cfg.get("metrics_max_sessions", 100)),
                alert=AlertEngine(),
                tracer=Tracer(max_traces=obs_cfg.get("tracer_max_traces", 1000)),
                store=store,
                enabled=obs_cfg.get("enabled", True),
                store_enabled=obs_cfg.get("store_enabled", True),
                trace_enabled=obs_cfg.get("trace_enabled", True),
            )
        except Exception:
            # 回退默认
            return cls(store=ObservabilityStore(db_path=store_db_path or "~/.memorygraph/observability.db"))

    def _on_alert_callback(self, alert: Alert) -> None:
        """告警触发回调：写入 store。"""
        if self.store and self._store_enabled:
            self.store.save_alerts([alert])

    # ── 一键式记录 ───────────────────────────────────────────

    def record_turn(
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
        self.logger.log_turn(
            session_id=session_id,
            turn_index=turn_index,
            query=query,
            latency_ms=latency_ms,
            intent_result=intent,
            confidence=confidence,
            execution_status=execution_status,
            pcr_noise=pcr_noise,
            pcr_complexity=pcr_complexity,
            trace=trace_steps or [],
            metadata=metadata or {},
        )

        # 2. Metrics
        session_metrics = self.metrics.get_or_create(session_id)
        session_metrics.record_turn(
            confidence=confidence,
            latency_ms=latency_ms,
            intent=intent,
            required_clarification=required_clarification,
            used_llm_fallback=used_llm_fallback,
            execution_status=execution_status,
        )
        metrics_summary = session_metrics.get_summary()

        # 3. Alerts
        alerts = self.alert.check_session_metrics(metrics_summary)

        # 4. Store (metrics snapshot)
        if self.store and self._store_enabled:
            self.store.save_metrics(session_id, turn_index, metrics_summary)
            if trace_steps:
                # 构造简单 trace 存入
                trace = self._build_simple_trace(
                    session_id, turn_index, query, latency_ms, trace_steps, metadata
                )
                self.store.save_trace(trace)

        return None, alerts

    # ── 链路追踪 API ───────────────────────────────────────────

    def start_trace(self, session_id: str, turn_index: int, query: str) -> Optional[TurnTrace]:
        """开始一轮追踪。"""
        if not self._enabled or not self._trace_enabled:
            return None
        return self.tracer.start_turn(session_id, turn_index, query)

    def end_trace(
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

        trace = self.tracer.end_turn()
        if trace is None:
            return None, []

        latency_ms = trace.total_duration_ms
        session_id = trace.session_id
        turn_index = trace.turn_index
        query = trace.query

        # 记录 metrics
        session_metrics = self.metrics.get_or_create(session_id)
        session_metrics.record_turn(
            confidence=confidence,
            latency_ms=latency_ms,
            intent=intent,
            required_clarification=required_clarification,
            used_llm_fallback=used_llm_fallback,
            execution_status=execution_status,
        )
        metrics_summary = session_metrics.get_summary()
        alerts = self.alert.check_session_metrics(metrics_summary)

        # 持久化
        if self.store and self._store_enabled:
            self.store.save_trace(trace)
            self.store.save_metrics(session_id, turn_index, metrics_summary)

        return trace, alerts

    def start_span(self, name: str, input_summary: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        """开始一个 span。"""
        if not self._enabled or not self._trace_enabled:
            return
        self.tracer.start_span(name, input_summary=input_summary, metadata=metadata)

    def end_span(self, status: str = "ok", output_summary: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        """结束当前 span。"""
        if not self._enabled or not self._trace_enabled:
            return
        self.tracer.end_span(status=status, output_summary=output_summary, metadata=metadata)

    def annotate_span(self, key: str, value: Any) -> None:
        """为当前 span 添加注解。"""
        if not self._enabled or not self._trace_enabled:
            return
        self.tracer.annotate_span(key, value)

    # ── 查询 API ───────────────────────────────────────────

    def get_session_health(self, session_id: str) -> Dict[str, Any]:
        """获取会话健康度。"""
        metrics = self.metrics.get_or_create(session_id)
        return metrics.get_summary()

    def get_global_health(self) -> Dict[str, Any]:
        """获取全局健康度。"""
        return self.metrics.get_global_summary()

    def get_recent_traces(self, n: int = 10) -> List[TurnTrace]:
        """获取最近追踪。"""
        return self.tracer.get_recent_traces(n)

    def get_active_alerts(self, max_age_seconds: float = 3600) -> List[Alert]:
        """获取活跃告警。"""
        return self.alert.get_active_alerts(max_age_seconds)

    def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警统计。"""
        return self.alert.get_alert_summary()

    def get_store_stats(self) -> Dict[str, Any]:
        """获取持久化存储统计。"""
        if self.store and self._store_enabled:
            return self.store.get_stats()
        return {"store_enabled": False}

    # ── 维护 ───────────────────────────────────────────

    def flush(self) -> None:
        """强制 flush 所有缓冲数据。"""
        self.logger._flush()

    def cleanup(self, ttl_seconds: float = 30 * 24 * 3600) -> Dict[str, int]:
        """清理过期数据。"""
        log_count = self.logger.cleanup_old_logs(dry_run=False)
        store_counts = (0, 0, 0)
        if self.store and self._store_enabled:
            store_counts = self.store.cleanup_old(ttl_seconds, dry_run=False)
        return {
            "logs_deleted": log_count,
            "traces_deleted": store_counts[0],
            "metrics_deleted": store_counts[1],
            "alerts_deleted": store_counts[2],
        }

    def shutdown(self) -> None:
        """优雅关闭。"""
        self.logger.shutdown()
        if self.store:
            self.store.close()

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
        import time
        base_ns = time.time_ns() - int(latency_ms * 1_000_000)
        for step in trace_steps:
            span = trace.add_span(name=step, start_ns=base_ns)
            base_ns += int(latency_ms / len(trace_steps) * 1_000_000) if trace_steps else 0
            span.end_ns = base_ns
        trace.end_ns = base_ns
        trace.metadata = metadata or {}
        return trace
