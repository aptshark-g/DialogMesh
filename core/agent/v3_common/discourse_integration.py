# core/agent/discourse_integration.py
"""Discourse Integration — 编译器管道与 InteractiveAgent 的集成入口。

为 interactive_test.py 提供最小化集成：
- 接收原始用户输入 + 会话历史
- 运行完整编译器管道（Stage 1-3 + Segmenter + Manager + SummaryEngine）
- 返回上下文字符串（Hot/Warm/Cold 组装）

使用方式（在 interactive_test.py 的 respond() 中）:
    from core.agent.v3_common.discourse_integration import DiscoursePipeline
    
    # 在 __init__ 中初始化
    self.discourse = DiscoursePipeline()
    
    # 在 respond() 中调用
    discourse_ctx = self.discourse.process_turn(query, self.history, self.turn_index)
    # 将 discourse_ctx 附加到 LLM messages 中
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.compiler.header_injector import HeaderInjector
    from core.agent.compiler.syntactic_decomposer import SyntacticDecomposer
    from core.agent.compiler.macro_micro_quantizer import MacroMicroQuantizer
    from core.agent.discourse_block_tree.segmenter import Segmenter
    from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
    from core.agent.discourse_block_tree.summary_engine import SummaryEngine
    from core.agent.discourse_block_tree.context_builder import ContextBuilder
    from core.agent.discourse_block_tree.models import EDU
except ImportError:
    import importlib.util
    import os
    import sys

    def _load(rel_path):
        abs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)
        abs_path = os.path.normpath(abs_path)
        name = rel_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(name, abs_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    hi = _load("compiler/header_injector.py")
    sd = _load("compiler/syntactic_decomposer.py")
    mm = _load("compiler/macro_micro_quantizer.py")
    seg = _load("discourse_block_tree/segmenter.py")
    mgr = _load("discourse_block_tree/manager.py")
    se = _load("discourse_block_tree/summary_engine.py")
    cb = _load("discourse_block_tree/context_builder.py")
    models = _load("discourse_block_tree/models.py")

    HeaderInjector = hi.HeaderInjector
    SyntacticDecomposer = sd.SyntacticDecomposer
    MacroMicroQuantizer = mm.MacroMicroQuantizer
    Segmenter = seg.Segmenter
    DiscourseBlockTreeManager = mgr.DiscourseBlockTreeManager
    SummaryEngine = se.SummaryEngine
    ContextBuilder = cb.ContextBuilder
    EDU = models.EDU

logger = logging.getLogger(__name__)

class DiscoursePipeline:
    """编译器管道集成器。

    封装完整的三阶段编译器 + 话语块树管理，对外只暴露 process_turn() 接口。
    """

    def __init__(
        self,
        session_id: str = "default",
        hot_turns: int = 5,
        enabled: bool = True,
        strategy: Optional[Dict[str, str]] = None,
    ):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        pipe_cfg = config.pipeline if config else None

        self.session_id = session_id
        self.hot_turns = hot_turns if (pipe_cfg is None) else pipe_cfg.hot_turns
        self.enabled = enabled if (pipe_cfg is None) else pipe_cfg.enabled
        self.strategy = strategy or {}

        # Metrics collector (optional, lightweight)
        self._metrics = None
        try:
            from core.agent.v3_common.metrics import MetricsCollector
            self._metrics = MetricsCollector(prefix="memorygraph")
        except Exception:
            pass

        # 编译器三阶段
        self.header_injector = self._resolve_component("header_injector", HeaderInjector)
        self.decomposer = SyntacticDecomposer()
        self.quantizer = MacroMicroQuantizer(embedding_model_name=None)

        # 话语块管理
        self.segmenter = self._resolve_component("segmenter", Segmenter)
        self.manager = DiscourseBlockTreeManager(
            segmenter=self.segmenter,
            hot_turns=self.hot_turns,
            enabled=self.enabled,
        )
        self.summary_engine = self._resolve_component("summary_engine", SummaryEngine)
        self.context_builder = ContextBuilder(hot_turns=self.hot_turns)

        logger.debug(
            f"DiscoursePipeline initialized (session={self.session_id}, "
            f"hot_turns={self.hot_turns}, enabled={self.enabled})"
        )

    def _resolve_component(self, component_type: str, default_cls):
        """Resolve a component via PluginRegistry if a custom strategy is specified."""
        strategy_name = self.strategy.get(component_type)
        if strategy_name:
            try:
                from core.agent.v3_common.plugin_system import PluginRegistry
                instance = PluginRegistry.get_strategy(component_type, strategy_name)
                if instance is not None:
                    logger.info(f"Using custom strategy '{strategy_name}' for {component_type}")
                    return instance
            except Exception as e:
                logger.warning(f"Failed to load strategy '{strategy_name}' for {component_type}: {e}")
        return default_cls()

    def process_turn(
        self,
        raw_query: str,
        session_history: Optional[List[Dict[str, Any]]] = None,
        turn_index: int = 0,
    ) -> str:
        """处理单轮输入，返回话语上下文字符串。

        Args:
            raw_query: 原始用户输入
            session_history: 会话历史（List[{"role": "user"/"assistant", "content": str}]）
            turn_index: 当前轮次索引

        Returns:
            话语上下文字符串（可为空字符串，如果 disabled 或处理失败）
        """
        if not self.enabled:
            return ""

        import time as _time
        _start = _time.time()

        try:
            # Stage 1: HeaderInjector
            injected = self.header_injector.inject(
                raw_query, self.session_id, session_history, turn_index
            )

            # Stage 2: SyntacticDecomposer
            clauses = self.decomposer.decompose(injected.text)

            # 转换为 EDU
            edus = []
            for i, clause in enumerate(clauses):
                if not clause.parse_failed:
                    edu = EDU(
                        id=f"edu:T{turn_index}:U{i}",
                        turn_index=turn_index,
                        edu_index=i,
                        raw_text=clause.raw_text,
                        subject=clause.subject,
                        predicate=clause.predicate,
                        object=clause.object,
                        subject_attrs=clause.subject_attrs,
                        object_attrs=clause.object_attrs,
                        negation=clause.negation,
                        uncertainty=clause.uncertainty,
                        imperative=clause.imperative,
                        question=clause.question,
                        raw_entities=clause.raw_entities,
                        parse_failed=clause.parse_failed,
                        intent_label="analyze" if clause.predicate else "statement",
                    )
                else:
                    edu = EDU(
                        id=f"edu:T{turn_index}:U{i}",
                        turn_index=turn_index,
                        edu_index=i,
                        raw_text=clause.raw_text,
                        parse_failed=True,
                        intent_label="statement",
                    )
                edus.append(edu)

            # Stage 3: MacroMicroQuantizer
            self.quantizer.quantize(edus)

            # 话语块管理：ingest → summarize → build context
            blocks = self.manager.ingest_turn(edus)
            for block in blocks:
                self.summary_engine.summarize_block(block)

            context = self.context_builder.build_context(
                self.manager.get_blocks(),
                current_turn=turn_index,
            )

            # Metrics: record success
            if self._metrics:
                elapsed = _time.time() - _start
                self._metrics.inc_discourse_requests()
                self._metrics.observe_discourse_latency(elapsed)
                self._metrics.inc_edu_processed(len(edus))
                self._metrics.inc_total_blocks(len(blocks))
                self._metrics.set_active_blocks(len(self.manager.get_hot_blocks()))
                # v3 trigger check
                for block in blocks:
                    if block.summary and block.summary.v3:
                        self._metrics.inc_v3_triggered()

            return context

        except Exception as e:
            # 失败时静默回退，不影响主流程
            if self._metrics:
                self._metrics.record_error("discourse_pipeline", str(e))
            return f"[DiscoursePipeline error: {e}]"

    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """Return current DiscourseBlockTree metrics snapshot."""
        if self._metrics:
            return self._metrics.discourse_summary()
        return None

    def get_metrics_prometheus(self) -> str:
        """Return metrics in Prometheus text format (fallback if prometheus_client missing)."""
        if self._metrics:
            return self._metrics.to_prometheus()
        return ""

    def reset(self):
        """重置所有状态（新会话）。"""
        self.manager.reset()
        self.header_injector.reset_session(self.session_id)

    def preload(self, blocking: bool = False) -> bool:
        """预加载所有组件（消除冷启动延迟）。

        预加载内容：
        - BGE 语义编码模型（后台线程）
        - jieba 分词词典（首次触发）

        Args:
            blocking: 是否阻塞等待加载完成（默认后台线程）

        Returns:
            True 如果预加载启动成功
        """
        logger.info(f"DiscoursePipeline preload starting (blocking={blocking})")

        # 1. 预加载 BGE 模型
        from core.agent.compiler.semantic_encoder import preload as preload_encoder
        preload_encoder(blocking=blocking)

        # 2. 预加载 jieba 词典（触发首次加载，生成缓存文件）
        try:
            import jieba
            jieba.lcut("预加载测试")  # 触发词典加载和缓存生成
            logger.info("jieba dictionary preloaded")
        except Exception as e:
            logger.warning(f"jieba preload failed: {e}")

        # 3. 预加载 NER（可选，当前可能不可用）
        try:
            from core.agent.compiler.semantic_parser import _load_ner_pipeline
            _load_ner_pipeline()
        except Exception as e:
            logger.warning(f"NER preload failed: {e}")

        logger.info("DiscoursePipeline preload completed")
        return True
