# -*- coding: utf-8 -*-
"""
core/agent/integration_bridge.py
────────────────────────────
Agent Pipeline: 组装五层新模块 + 接入现有 PCR/Gates/IntentParser 流程。

这是新旧系统的集成桥接层。保持原有 run_intent_trace 不变，在其上下游插入新模块：
  上游：CognitiveCompiler（编译） + TopicTreeManager（路由） + WindowManager（过滤）
  下游：Persistence（持久化） + Observability（日志/指标/告警）

向后兼容：所有新模块可通过参数禁用，退化为原有行为。
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.agent.pcr.tests.intent_trace_cli import run_intent_trace
from core.agent.llm_providers.base import LLMProvider
from core.agent.v3_2.integration import V32Pipeline

from core.agent.cognitive_compiler import (
    CognitiveCompiler, CompilerMode, EntityCache, CompiledInput,
)
from core.agent.topic_tree import TopicTreeManager, RoutingDecision
from core.agent.window import (
    ContextWindowManager, WindowBudget,
)
from core.agent.context_window import (
    WindowManager, WindowConfig,
)
from core.agent.persistence import CLISessionPersistence, TurnRecord
from core.agent.observability import (
    StructuredLogger, SessionMetrics, MetricsAggregator, AlertEngine,
)


class AgentPipeline:
    """
    工业级 Agent Pipeline。

    五层新模块 + 现有 PCR 决策链的集成桥接。
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        db_path: str = "~/.memorygraph/sessions.db",
        use_persistence: bool = True,
        use_compiler: bool = True,
        use_topic_tree: bool = True,
        use_window: bool = True,
        use_observability: bool = True,
        compiler_mode: CompilerMode = CompilerMode.AUTO,
        window_config: Optional[WindowConfig] = None,
        verbose_bridge: bool = True,
        conversation_mode: bool = False,
        enable_v32: bool = False,
    ):
        """
        初始化 Pipeline。

        :param session_id: 会话 ID（None 则自动生成）
        :param db_path: 持久化数据库路径
        :param use_persistence: 启用 SQLite 持久化
        :param use_compiler: 启用认知编译器（代词消解 + 粘合度）
        :param use_topic_tree: 启用话题树（路由/分叉/回溯）
        :param use_window: 启用上下文窗口（Hot/Warm/Cold 三层）
        :param use_observability: 启用观测性（日志/指标/告警）
        :param compiler_mode: 编译器模式（auto/fast/hybrid/full）
        :param window_config: 窗口配置（None 则用默认）
        :param verbose_bridge: 打印桥接层信息
        :param conversation_mode: 对话模式 — 当意图为 UNKNOWN 时强制调用 LLM 生成自然语言回复
        :param enable_v32: 启用 v3.2 模块（HybridCompiler + BehaviorGraph + FusionEngine）作为并行分析轨
        """
        self._session_id = session_id or f"cli-{int(time.time())}"
        self._turn_index = 0
        self._session_history: List[Dict[str, Any]] = []
        self._verbose_bridge = verbose_bridge
        self._conversation_mode = conversation_mode
        self._enable_v32 = enable_v32
        self._v32_pipeline = None
        self._v32_monitor = None
        self._v32_recorder = None

        # 模块初始化
        self._persistence = CLISessionPersistence(db_path=db_path) if use_persistence else None
        self._compiler = CognitiveCompiler(mode=compiler_mode) if use_compiler else None
        self._topic_tree = TopicTreeManager() if use_topic_tree else None

        # 话题树自动持久化：从 GraphStore 加载已有话题树
        self._graph_store = None
        if use_persistence and use_topic_tree and self._persistence is not None:
            import sqlite3
            import threading
            from core.agent.persistence.graph_store import GraphStore
            try:
                conn = sqlite3.connect(
                    self._persistence._db_path,
                    check_same_thread=False,
                )
                conn.execute("PRAGMA journal_mode=WAL")
                self._graph_store = GraphStore(conn, threading.Lock())
                # 尝试加载已有话题树
                loaded_tree = TopicTreeManager.load_from_graph_store(
                    self._graph_store, self._session_id
                )
                if loaded_tree is not None:
                    self._topic_tree = loaded_tree
            except Exception as e:
                print(f"[AgentPipeline] topic_tree load skipped: {e}")

        self._window = WindowManager(config=window_config) if use_window else None
        self._entity_cache = EntityCache(max_rounds=5)
        self._logger = StructuredLogger() if use_observability else None
        self._metrics = SessionMetrics(session_id=self._session_id) if use_observability else None
        self._alerts = AlertEngine() if use_observability else None

        # 初始化 v3.2 并行管线
        if self._enable_v32:
            self._init_v32_pipeline()

        # 记录启用的模块
        self._active_modules = {
            "persistence": use_persistence,
            "compiler": use_compiler,
            "topic_tree": use_topic_tree,
            "window": use_window,
            "observability": use_observability,
            "conversation_mode": conversation_mode,
            "v32": enable_v32,
        }

    def _init_v32_pipeline(self) -> None:
        """初始化 v3.2 并行分析管线。"""
        try:
            from core.agent.v3_2.testing_utils import MockLLM, DEFAULT_COMPILER_RESPONSE
            from core.agent.v3_2.integration import V32Pipeline
            from core.agent.v3_2.monitor import Monitor
            from core.agent.v3_2.session_recorder import SessionRecorder
            self._v32_monitor = Monitor(verbose=True)
            self._v32_recorder = SessionRecorder(f"v32_logs_{self._session_id}")
            self._v32_pipeline = V32Pipeline(
                MockLLM(DEFAULT_COMPILER_RESPONSE),
                monitor=self._v32_monitor,
                session_recorder=self._v32_recorder,
                save_path=f"v32_graph_{self._session_id}.json",
            )
            if self._verbose_bridge:
                print(f"[V32] Pipeline initialized (session={self._session_id})")
        except Exception as e:
            print(f"[V32] Init failed: {e}")

    # ── 核心 API ───────────────────────────────────────────

    def process(self, query: str, provider: Optional[LLMProvider] = None, verbose: bool = True, conversation_mode: bool = None) -> Dict[str, Any]:
        """
        处理单轮查询。

        完整链路：
          1. 编译（CognitiveCompiler）
          2. 话题路由（TopicTreeManager）
          3. 窗口过滤（WindowManager）
          4. 现有 PCR 决策链（run_intent_trace）
          5. 持久化（Persistence）
          6. 观测性（Logger + Metrics + Alerts）
          7. 历史累积

        :param query: 用户输入
        :param provider: LLM Provider（可选）
        :param verbose: 是否打印详细过程
        :param conversation_mode: 覆盖默认的对话模式设置（None 则用 self._conversation_mode）
        :return: 与 run_intent_trace 兼容的结果字典
        """
        self._turn_index += 1
        start_time = time.time()
        bridge_trace: List[str] = []
        conv_mode = conversation_mode if conversation_mode is not None else self._conversation_mode

        # 1. 认知编译器
        compiled = self._step_compile(query, bridge_trace)

        # 2. 话题路由
        decision = self._step_route(query, compiled, bridge_trace)

        # 3. 窗口过滤：按话题决策构建历史
        filtered_history = self._step_window_filter(decision, bridge_trace)

        # 4. 运行 v3.2 并行管线（与 PCR 流程并行）
        v32_result = self._step_v32(query, bridge_trace)

        # 5. 调用现有 PCR 决策链
        pcr_result = self._step_pcr(query, compiled, filtered_history, provider, verbose, conv_mode)

        # 将 v3.2 结果合并到 pcr_result
        if v32_result:
            parse = v32_result.get("parse")
            fusion = v32_result.get("fusion")
            if parse:
                pcr_result["v32_parse"] = {
                    "slots": parse.to_dict().get("slots", {}) if hasattr(parse, "to_dict") else {},
                    "stability": parse.stability,
                    "degraded": parse.degraded,
                    "is_reliable": parse.is_reliable,
                }
            if fusion:
                pcr_result["v32_fusion"] = {
                    "confidence": fusion.confidence,
                    "dominant_track": str(fusion.dominant_track) if fusion.dominant_track else None,
                    "final_output": fusion.final_output,
                }

        # 6. 更新窗口
        self._step_window_update(query, compiled, decision, pcr_result, bridge_trace)

        # 6. 持久化
        self._step_persist(query, pcr_result, start_time, bridge_trace)

        # 7. 观测性
        self._step_observe(query, pcr_result, start_time, bridge_trace)

        # 8. 历史累积（供下一轮编译使用）
        self._step_history_update(query, pcr_result, compiled, decision)

        total_ms = (time.time() - start_time) * 1000

        # 桥接层摘要（如果 verbose）
        if self._verbose_bridge and verbose:
            self._print_bridge_summary(bridge_trace, compiled, decision, total_ms)

        # 在 pcr_result 中注入桥接层元信息
        pcr_result["bridge"] = {
            "session_id": self._session_id,
            "turn_index": self._turn_index,
            "modules": dict(self._active_modules),
            "trace": bridge_trace,
            "total_ms": round(total_ms, 2),
        }
        if compiled:
            pcr_result["bridge"]["cohesion_score"] = compiled.cohesion_score
            pcr_result["bridge"]["compiled_query"] = compiled.query
            pcr_result["bridge"]["compiler_mode"] = compiled.mode_used
            pcr_result["bridge"]["backfilled"] = any(c.backfilled for c in compiled.clauses)
        if decision:
            pcr_result["bridge"]["topic_action"] = decision.action
            pcr_result["bridge"]["topic_node_id"] = decision.target_node_id

        return pcr_result

    # ── 各步骤实现 ───────────────────────────────────────────

    def _step_compile(self, query: str, trace: List[str]) -> Optional[CompiledInput]:
        """Step 1: 认知编译器。"""
        if not self._compiler:
            return None
        compiled = self._compiler.compile(
            query,
            turn_index=self._turn_index,
            session_history=list(self._session_history),
            entity_cache=self._entity_cache,
        )
        trace.append(f"[COMPILE] mode={compiled.mode_used} cohesion={compiled.cohesion_score:.3f}")
        if any(c.backfilled for c in compiled.clauses):
            trace.append(f"[COMPILE] backfill detected")
        return compiled

    def _step_route(self, query: str, compiled: Optional[CompiledInput], trace: List[str]) -> Optional[RoutingDecision]:
        """Step 2: 话题路由。"""
        if not self._topic_tree:
            return None
        entities = self._extract_entities(compiled.clauses if compiled else [])
        cohesion = compiled.cohesion_score if compiled else None
        decision = self._topic_tree.route(
            query=query,
            turn_index=self._turn_index,
            cohesion_score=cohesion,
            extracted_entities=entities,
        )
        trace.append(f"[ROUTE] action={decision.action} node={decision.target_node_id}")
        return decision

    def _step_window_filter(self, decision: Optional[RoutingDecision], trace: List[str]) -> List[Dict[str, Any]]:
        """Step 3: 按话题决策过滤历史。"""
        if not self._window:
            # 如果窗口禁用且话题树也禁用，不传递历史（保持 v1 纯内存行为）
            if not self._topic_tree:
                trace.append("[WINDOW] all new modules disabled, empty history")
                return []
            trace.append("[WINDOW] disabled, using full history")
            return self._session_history

        if decision is None or decision.action in ("new", "fork"):
            # 新话题：清空历史（不污染）
            trace.append(f"[WINDOW] topic={decision.action if decision else 'N/A'}, cleared history")
            return []

        if decision.action == "attach":
            # 回溯旧话题：从窗口构建该话题的历史
            node = self._topic_tree.get_node(decision.target_node_id) if self._topic_tree else None
            if node:
                # 从窗口中查找该话题的轮次
                topic_entries = self._window.build_pcr_input()
                trace.append(f"[WINDOW] attach topic={node.name}, history={len(topic_entries)} entries")
                return [e.to_dict() for e in topic_entries] if hasattr(topic_entries[0], 'to_dict') else topic_entries

        # continue: 使用当前窗口历史
        entries = self._window.build_pcr_input()
        trace.append(f"[WINDOW] continue, history={len(entries)} entries")
        return [e.to_dict() for e in entries] if entries and hasattr(entries[0], 'to_dict') else entries

    def _step_pcr(self, query: str, compiled: Optional[CompiledInput],
                  filtered_history: List[Dict[str, Any]],
                  provider: Optional[LLMProvider], verbose: bool, conversation_mode: bool = False) -> Dict[str, Any]:
        """Step 4: 调用现有 PCR 决策链。"""
        # 使用编译后的 query（代词已消解）
        pcr_query = compiled.query if compiled else query
        result = run_intent_trace(
            query=pcr_query,
            provider=provider,
            history=filtered_history,
            session_id=self._session_id,
            verbose=verbose,
            conversation_mode=conversation_mode,
        )
        return result

    def _step_window_update(self, query: str, compiled: Optional[CompiledInput],
                            decision: Optional[RoutingDecision], pcr_result: Dict[str, Any],
                            trace: List[str]) -> None:
        """Step 5: 更新窗口。"""
        if not self._window:
            return
        from core.agent.context_window.models import WindowTurn
        turn = WindowTurn(
            sequence=self._turn_index,
            role="user",
            content=query,
            intent_category=pcr_result.get("summary", {}).get("category", ""),
            metadata={
                "cohesion_score": compiled.cohesion_score if compiled else 0.0,
                "topic_action": decision.action if decision else None,
                "topic_node_id": decision.target_node_id if decision else None,
                "compiled_query": compiled.query if compiled else query,
            },
        )
        self._window.add_turn(turn)
        trace.append(f"[WINDOW] added turn seq={self._turn_index}")

    def _step_persist(self, query: str, pcr_result: Dict[str, Any],
                      start_time: float, trace: List[str]) -> None:
        """Step 6: 持久化。"""
        if not self._persistence:
            return
        total_latency = (time.time() - start_time) * 1000
        summary = pcr_result.get("summary", {})
        self._persistence.add_turn(
            session_id=self._session_id,
            role="user",
            content=query,
            intent_result=summary,
            execution_status=summary.get("execution_status"),
            latency_ms=total_latency,
        )
        trace.append(f"[PERSIST] turn saved to {self._persistence._db_path}")

        # 话题树自动持久化
        if self._topic_tree and self._graph_store:
            try:
                self._topic_tree.save_to_graph_store(self._graph_store, self._session_id)
                trace.append("[PERSIST] topic_tree saved to GraphStore")
            except Exception as e:
                trace.append(f"[PERSIST] topic_tree save failed: {e}")

    def _step_observe(self, query: str, pcr_result: Dict[str, Any],
                      start_time: float, trace: List[str]) -> None:
        """Step 7: 观测性。"""
        if not self._metrics or not self._logger:
            return

        summary = pcr_result.get("summary", {})
        total_latency = (time.time() - start_time) * 1000

        # 指标
        self._metrics.record_turn(
            confidence=summary.get("confidence", 0.0),
            latency_ms=total_latency,
            intent=summary.get("category", "unknown"),
            required_clarification=summary.get("has_ambiguity", False),
        )

        # 日志
        self._logger.log_turn(
            session_id=self._session_id,
            turn_index=self._turn_index,
            query=query,
            latency_ms=total_latency,
            intent_result=summary.get("category"),
            confidence=summary.get("confidence", 0.0),
            execution_status=summary.get("execution_status"),
        )

        # 告警
        alerts = self._alerts.check_session_metrics(self._metrics.get_summary())
        if alerts:
            for alert in alerts:
                trace.append(f"[ALERT] {alert.severity.value}: {alert.message}")

    def _step_history_update(self, query: str, pcr_result: Dict[str, Any],
                             compiled: Optional[CompiledInput],
                             decision: Optional[RoutingDecision]) -> None:
        """Step 8: 累积历史（供下一轮编译使用）。"""
        summary = pcr_result.get("summary", {})
        self._session_history.append({
            "role": "user",
            "content": query,
            "expectation": summary.get("expectation", ""),
            "timestamp": time.time(),
        })
        if summary.get("execution_status") == "direct_reply":
            self._session_history.append({
                "role": "assistant",
                "content": summary.get("message", ""),
                "expectation": "DIRECT_REPLY",
                "timestamp": time.time(),
            })

    # ── 工具方法 ───────────────────────────────────────────

    def _extract_entities(self, clauses) -> List[Dict[str, Any]]:
        """从编译子句提取实体。"""
        entities = []
        for c in clauses:
            if c.subject and not c.backfilled:
                entities.append({"value": c.subject, "type": "subject"})
            if c.object:
                entities.append({"value": c.object, "type": "object"})
            if c.backfilled:
                entities.append({"value": c.subject, "type": "backfilled"})
        return entities

    def _print_bridge_summary(self, trace: List[str], compiled: Optional[CompiledInput],
                              decision: Optional[RoutingDecision], total_ms: float) -> None:
        """打印桥接层摘要。"""
        try:
            print(f"\n{'-'*50}")
            print(f"  [Bridge] Summary (Turn {self._turn_index})")
            print(f"{'-'*50}")
            for t in trace:
                print(f"    {t}")
            if compiled:
                print(f"    cohesion: {compiled.cohesion_score:.3f} | mode: {compiled.mode_used}")
            if decision:
                print(f"    topic: {decision.action} -> {decision.target_node_id}")
            print(f"    total: {total_ms:.1f}ms")
            print(f"{'-'*50}")
        except UnicodeEncodeError:
            pass

    # ── 生命周期 ───────────────────────────────────────────

    def _step_v32(self, query: str, trace: List[str]) -> dict:
        """Run v3.2 pipeline. Optional, requires enable_v32=True."""
        if not self._enable_v32 or not self._v32_pipeline:
            return {}
        import asyncio
        try:
            result = asyncio.run(self._v32_pipeline.process(query))
            trace.append("[V32] v3.2 pipeline completed")
            return result
        except Exception as e:
            trace.append(f"[V32] Error: {e}")
            return {}
    
    
    def shutdown(self) -> None:
        """优雅关闭：保存所有状态。"""
        # 关闭 v3.2 管线
        if self._v32_recorder:
            try:
                self._v32_recorder.close()
                if self._verbose_bridge:
                    print(f"[V32] Session recorder closed")
            except Exception as e:
                print(f"[V32] Recorder close error: {e}")
        if self._v32_monitor:
            try:
                self._v32_monitor.report()
            except Exception:
                pass
        if self._v32_pipeline and self._v32_pipeline.graph:
            try:
                self._v32_pipeline.graph.save(f"v32_graph_{self._session_id}_final.json")
            except Exception:
                pass

        if self._topic_tree and self._graph_store:
            try:
                self._topic_tree.save_to_graph_store(self._graph_store, self._session_id)
            except Exception as e:
                print(f"[AgentPipeline] topic_tree shutdown save failed: {e}")

        if self._persistence:
            self._persistence.close_session(self._session_id)
            self._persistence.shutdown()
        if self._logger:
            self._logger.shutdown()

    # ── 查询 ───────────────────────────────────────────

    def get_session_summary(self) -> Dict[str, Any]:
        """获取会话摘要。"""
        summary = {
            "session_id": self._session_id,
            "turn_index": self._turn_index,
            "modules": dict(self._active_modules),
        }
        if self._topic_tree:
            summary["topic_tree"] = self._topic_tree.get_tree_summary()
        if self._window:
            summary["window"] = self._window.get_window_summary()
        if self._metrics:
            summary["metrics"] = self._metrics.get_summary()
        if self._alerts:
            summary["alerts"] = self._alerts.get_alert_summary()
        return summary

    def list_sessions(self, limit: int = 20) -> List[Any]:
        """列出持久化中的会话。"""
        if not self._persistence:
            return []
        return self._persistence.list_sessions(limit=limit)
