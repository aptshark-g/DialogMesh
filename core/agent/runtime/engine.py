"""CognitiveRuntimeEngine: orchestrates v4 modules across four paths.

Integrates ``PathAwareScheduler`` for path-aware scheduling,
configuration-driven triggers, and per-path state tracking.
"""
from __future__ import annotations
import time, re
import importlib
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.events.event_ir import EventIR
from core.agent.runtime.adapter import (
    RuntimeAdapter, RuntimeContext, AdapterResult,
)
from core.agent.runtime.config import (
    RuntimeConfig, ModuleConfig, PathConfig, load_runtime_config, build_default_config,
)
from core.agent.world.params import WorldParams, get_world_params
from core.agent.context.assembler import ContextAssembler
from core.agent.context.source import (
    SkillSource, WorldSource,
)
from core.agent.context.topic_tree_source import TopicTreeContextSource
from core.agent.compiler.content_index import ContentIndex
from core.agent.compiler.index_source import IndexSource
from core.agent.conversation.tracker import ConversationTracker
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
from core.agent.causal.planner import CausalPlanner, CausalContextSource
from core.agent.context.domain_selector import DomainSelector
from core.agent.context.cross_domain_ir import CrossDomainContextIR
from core.agent.compiler.perspective_planner import PerspectivePlanner, Perspective
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
from core.agent.v4.cognitive_scheduler.path_models import PathType, PathState
from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    ConfigDrivenTriggerPolicy, EventCounter, PathStateMachine,
)
from core.agent.v4.cognitive_scheduler.tasks import (
    ObservationTask, HypothesisTask, KnowledgeTask, SkillTask,
)

from core.agent.behavior.adapter import BehaviorGraphAdapter, BehaviorGraphState
from core.agent.causal_substrate.adapter import CausalSubstrateAdapter, CausalContextEntry
from core.agent.runtime.event_log_adapter import V4EventLog, EventLogConfig

from core.agent.optimizer.signals import FeedbackSignal
from core.agent.optimizer.optimizer import BayesianOptimizer
from core.agent.llm_providers.base import LLMProvider, GenerateRequest, GenerateResult
from core.agent.llm_providers.provider_factory import ProviderFactory

logger = logging.getLogger(__name__)


@dataclass
class PathStats:
    """Runtime statistics for a single path."""
    path_name: str
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_triggered_at: float = 0.0



def _feed_discourse(engine, ctx):
    """Helper for state machine: feed discourse tree."""
    text = ctx.get("text", "")
    sid = ctx.get("session_id", "default")
    if hasattr(engine, '_discourse_tree') and engine._discourse_tree:
        engine._discourse_tree.feed(text, sid)
        return {"blocks": len(engine._discourse_tree.get_block_relations(sid).get("blocks", {}))}
    return {}

def _record_behavior(engine, ctx):
    """Helper for state machine: record behavior edge."""
    bg = getattr(engine, '_behavior_graph', None)
    if bg and hasattr(bg, 'load'):
        bg.load()
        return {"recorded": True}
    return {}

class CognitiveRuntimeEngine:
    """Orchestrates v4 cognitive modules across Fast/Async/Slow/Deep paths.

    Path data flow::

        Async: Event -> ObservationCompiler -> ObservationPool
        Slow:  ObservationPool -> HypothesisEngine -> Knowledge
        Deep:  Patterns -> SkillDistiller -> Skill

    Scheduling integration::

        - PathAwareScheduler tracks per-path state machines (idle → running → backlogged → idle)
        - EventCounter auto-triggers Slow Path after configurable threshold (default 50)
        - Deep Path triggers only when pattern_count >= threshold AND success_rate >= threshold
        - Bayesian Optimizer runs on configurable interval (from WorldParams or default 3)
        - All trigger parameters read from runtime.yaml and WorldParams, no hard-coding
        - LLM Provider: compiles CrossDomainContextIR → prompt → LLM → response

    Usage::

        engine = CognitiveRuntimeEngine()
        engine.start()

        # On each user event:
        response = engine.on_event(event_ir)  # Returns LLM response string

        # Or manually trigger checkpoint:
        engine.trigger_checkpoint()

        # On session end:
        engine.on_session_end()
    """

    def __init__(self, config_path: str = None, world_params: WorldParams = None,
                 llm_provider: Optional[LLMProvider] = None):
        if config_path:
            self._config = load_runtime_config(config_path)
        else:
            self._config = build_default_config()

        self._world_params = world_params or get_world_params()
        self._world_objects: Dict[str, Any] = {}  # P0: SemanticObject store (lazy init)
        self._adapters: Dict[str, RuntimeAdapter] = {}
        self._stats: Dict[str, PathStats] = {}
        self._event_buffer: List[EventIR] = []
        self._running = False
        self._checkpoint_timer: Optional[threading.Timer] = None
        self._session_active = False
        self._last_event_time = 0.0

        # Observation pool for path-to-path data flow
        self._observation_pool = None
        self._context_assembler: Optional[ContextAssembler] = None
        self._domain_selector: Optional[DomainSelector] = None
        self._perspective_planner: Optional[PerspectivePlanner] = None
        self._last_context: Optional[CrossDomainContextIR] = None

        # v3_2 adapters (BehaviorGraph, CausalSubstrate, EventLog)
        self._behavior_graph_adapter: Optional[BehaviorGraphAdapter] = None
        self._causal_substrate_adapter: Optional[CausalSubstrateAdapter] = None
        self._event_log: Optional[V4EventLog] = None
        # Behavior chain brain (P1: predictor + rewarder + training loop).
        self._behavior_brain = None
        self._behavior_brain_ready = False

        # CausalPlanner: unified v4 adapter for v3_2 BehaviorGraph + CausalSubstrate
        self._causal_planner: Optional[CausalPlanner] = None

        # ConversationTracker: multi-dimensional follow-up disambiguation
        self._conversation_tracker = ConversationTracker()
        # DiscourseBlockTree: conversation-to-tree compiler
        self._discourse_tree = DiscourseBlockTreeManager()
        # TREE_TIERING (2026-08-07): feed 后自动 Hot→Warm 落盘（OS 式 page-out）
        self._discourse_tree._persist_hook = self._persist_discourse_tree
        self._discourse_last_persist = 0.0
        # Granularity regulator: BDI+BOR adaptive split/merge
        from core.agent.compiler.discourse_block_tree import DiscourseBlockGranularityRegulator
        self._granularity_regulator = DiscourseBlockGranularityRegulator()
        self._turn_counter = 0

        # User cognitive profile (dual-track: Track A dynamics + Track B tags)
        self._cognitive_profile: Optional[object] = None  # CognitiveProfileV2
        # R5 ③ 认知状态层 / P8 P 域统一画像源 / P7 惯性权重图（懒挂载）
        self._convergence_engine: Optional[object] = None
        self._profile_source: Optional[object] = None
        self._profile_runtime_ready = False
        self._inertia_graph: Optional[object] = None

        # Extraction orchestration (regex / LMStudio / DeepSeek with fallback)
        self._extraction_orchestrator = None  # ExtractionOrchestrator set in start()

        # Cognitive Runtime (Phase 2): LLM-driven reasoning loop
        self._use_cognitive_runtime = False

        # Internal Simulation Engine: LLM simulates user cognitive state
        self._simulation_engine = None  # Initialized in start()
        self._last_simulation: Optional[object] = None  # SimulationResult from previous turn
        self._simulation_stats = {"matches": 0, "total": 0}
        self._cognitive_observer = None  # Observer set when enabled
        self._cognitive_trace: Optional[object] = None  # ExecutionTrace for last run

        # v6: State evolution tracking (ExecutionTraceV3)
        self._trace_v3: Optional[object] = None  # ExecutionTraceV3 per session
        # M5-M3: v6 元认知学习闭环（MetaConsumer 消费 ExecutionTraceV3）
        self._meta_consumer: Optional[object] = None
        # M5-M1: 冷→热三层反馈桥（MetaSubscriber 写入 / agent_native 等读取）
        self._feedback_bridge: Optional[object] = None

        # Behavior tracking: record user navigation edges in RelationSubstrate
        self._last_concept: Optional[str] = None
        self._content_provider = None  # set by _create_context_assembler

        # TopicTree + DiscourseBlockTree: hierarchical conversation context
        self._topic_tree_source: Optional[TopicTreeContextSource] = None

        # LLM Provider integration
        self._llm_provider: Optional[LLMProvider] = llm_provider
        self._last_llm_response: Optional[str] = None
        self._pcr_router = None  # Pre-Cognitive Router — lazy init in start()
        self._last_pcr = None    # Last PCROutput
        self._decider = None     # GlobalDecider — state machine coordinator
        self._event_log = None   # EventLog — SQLite append-only
        self._event_bus = None   # EventBus — ring buffer pub/sub
        self._meta_sub = None    # MetaSubscriber — cold path
        self._assoc_sub = None   # AssociationSubscriber — cold path
        self._assoc_service = None  # AssociationService — 独立服务（蓝图 §7.3）
        self._assoc_prev_intent = None  # 主题切换粗信号（intent 类别变化）

        # Association chain cold-path components (lazy, non-fatal init).
        # D-3/D-15: runtime engine is the first real runner of the funnel.
        self._l1_extractor = None        # L1 PronounResolver (resolve -> enriched)
        self._pronoun_resolver = None    # StanzaCorefResolver
        self._context_qualifier = None   # ContextQualifier (dependency injection)
        self._l1_modifier = None         # legacy ModifierExtractor (deprel classify)
        self._l2_5_belief = None         # BeliefAccumulator (Bayesian + 7D)
        self._l3_validator = None        # MultiPerspectiveValidator (4-perspective)
        self._association_funnel = None  # AssociationFunnel (coarse five-layer path)
        self._last_association = None    # last cold-path result (white-box A19)
        self._association_components_ready = False

        # D-13: white-box CRUD stores (A19/P22) — user-inspectable/editable.
        self._association_relations: Dict[str, dict] = {}
        self._association_causal_annotations: list = []
        self._causal_blocked_edges: list = []

        self._intent_parser = None     # v3_common IntentParser — lazy init
        self._unified_parser = None   # UnifiedParser — Tier 0→2 pipeline
        self._router_v4 = None        # V4.0 Cognitive Coordinate Router
        self._last_intent_context = None  # Last IntentContext
        self._last_parse_result = None   # Last ParseResult
        self._planner = None             # v3_0 Planner — lazy init
        self._skill_matcher = None       # v3_0 SkillMatcher — lazy init
        self._scheduler = None           # v4 CognitiveScheduler — lazy init
        self._last_plan_result = None    # Last PlanResult
        self._llm_metrics: Optional[Dict[str, Any]] = None

        # Path trigger policy and state machine (from path_trigger_policy)
        self._trigger_policy: Optional[ConfigDrivenTriggerPolicy] = None
        self._path_state_machine: Optional[PathStateMachine] = None
        self._event_counter: Optional[EventCounter] = None

        for path_name in self._config.paths:
            self._stats[path_name] = PathStats(path_name=path_name)

        # D-3: wire the association cold path at construction so the L1 gate
        # (`if text and self._l1_extractor`) is live from the first event.
        self._init_association_components()
        # Phase 6: 关联链独立服务（M→1 定向通道 + EventLog），不广播。
        self._init_association_service()

        # B5-3 白盒编辑后端（M2）: 图编辑/IR 编辑/journal/三档模式。
        # 懒加载 + 非致命 — 即便组件不可用也不阻塞引擎启动。
        self._edit_mode = "smart"              # smart | whitebox | fullwhite
        self._correction_journal = None        # CorrectionJournal (lazy)
        self._interaction_graph = None         # InteractionGraph (lazy)
        self._world_provider = None            # RelationSubstrate 宿主 (lazy)
        self._init_whitebox()

        # B1-8 认知运行时 + LLM-1 共享树 + LLM-3 对内执行预测学习（M3）
        # A16 快慢分流: 认知循环 = LLM 主推理的可选前置（默认关闭）
        self._cognitive_runtime_enabled = False
        self._cognitive_observer = None        # A 套 Observer (lazy)
        self._cognitive_scheduler = None       # A 套 CognitiveScheduler (lazy)
        self._cognitive_tree = None            # v3_0 思考树（唯一共享心智空间）
        self._cognitive_compiler = None        # CognitiveCompiler（唯一写树入口）
        self._prediction_stats = {
            "predictions": 0, "hits": 0, "misses": 0,
        }  # LLM-3 对内预测学习统计
        self._init_cognitive_runtime()

    # ------------------------------------------------------------------ #
    # B1: unified cold-start assembly entry (CLI/tests/API share one path)
    # ------------------------------------------------------------------ #

    def bootstrap(self, registry=None, provider_config=None) -> dict:
        """B1: Unify cold-start assembly (single entry for CLI/tests/API).

        Resolves all engine subsystems through a registry (default:
        ``core.agent.cli.subsystem_registrations._registry``), attaches them
        to the engine, then wires non-registry components (EventLog path /
        Storage / Tracer / Guards / NATS / StateMachine+handlers / KG /
        BehaviorGraph / ToolRegistry / Learning / deep objects / cross-deps /
        meta runtime) with try/except degradation. Optional components never
        block startup; required registry failures raise ``RuntimeError``.

        Idempotent: a second call returns the current state without
        re-assembling. Returns a summary dict compatible with the legacy
        ``start_engine`` return shape.
        """
        if getattr(self, "_bootstrap_done", False):
            return {
                "status": "running" if self._running else "stopped",
                "provider": getattr(self, "_provider_type", "mock"),
                "model": getattr(self, "_provider_model", ""),
                "subsystems_loaded": len(getattr(self, "_loaded_subsystems", {})),
                "subsystems_total": getattr(self, "_subsystems_total", 0),
                "startup_ms": getattr(self, "_bootstrap_ms", 0.0),
                "failed": getattr(self, "_bootstrap_failed", {}),
            }

        import os as _os
        import time as _time
        t0 = _time.time()

        # ---- Phase 0: provider metadata (accept dict or legacy str) ----
        if isinstance(provider_config, str):
            provider_config = {"type": provider_config}
        provider_config = provider_config or {}
        self._provider_type = provider_config.get("type", "mock")
        self._provider_model = provider_config.get("model", "")
        self._running = True
        self._session_active = True

        # ---- Phase 1: registry resolve + attach ----
        if registry is None:
            try:
                from core.agent.cli.subsystem_registrations import _registry
                registry = _registry
            except ImportError as e:
                raise RuntimeError(f"Registry import failed: {e}")
        self._registry = registry

        # Provide provider + engine for DI before resolve_all
        try:
            if getattr(self, "_llm_provider", None) is not None:
                registry._instances["llm_provider"] = self._llm_provider
                registry._instances["provider"] = self._llm_provider
        except Exception:
            pass
        try:
            registry._instances["engine"] = self
        except Exception:
            pass

        try:
            loaded, results = registry.resolve_all()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Registry resolve failed: {e}")

        _name_map = {"behavior_graph": "_behavior_graph_adapter",
                     "cascade_detector": "_cascade"}
        attached = 0
        failed: Dict[str, str] = {}
        for result in results:
            if result.loaded and result.instance is not None:
                attr_name = _name_map.get(result.name, f"_{result.name}")
                setattr(self, attr_name, result.instance)
                # Legacy alias: consumers (BehaviorSubscriber, CLI commands)
                # read the raw subsystem name (e.g. `_behavior_graph`).
                raw_name = f"_{result.name}"
                if raw_name != attr_name:
                    setattr(self, raw_name, result.instance)
                attached += 1
            else:
                if result.error:
                    failed[result.name] = result.error
                    logger.warning("Subsystem %s: %s", result.name, result.error)
        self._loaded_subsystems = loaded
        self._subsystems_total = len(results)

        # TREE_TIERING (2026-08-07): registry 用工厂重建了 _discourse_tree
        # （覆盖 __init__ 实例）— 重挂 Hot→Warm 持久化 hook
        try:
            if getattr(self, "_discourse_tree", None) is not None:
                self._discourse_tree._persist_hook = self._persist_discourse_tree
        except Exception:
            pass

        # ---- Phase 2: backward-compat wiring (legacy attributes) ----
        for name, cls_path in [
            ("_semantic_splitter", "core.agent.storage.semantic_splitter:SemanticSplitter"),
            ("_context_window", "core.agent.storage.context_window:ContextWindow"),
            ("_write_gate", "core.agent.storage.context_window:WriteGate"),
            ("_pronoun_resolver", "core.agent.association.pronoun_resolver:StanzaCorefResolver"),
            ("_context_qualifier", "core.agent.association.context_qualifier:ContextQualifier"),
            ("_semantic_coref", "core.agent.association.semantic_coref:SemanticCorefScorer"),
            ("_hybrid_coref", "core.agent.association.hybrid_coref:HybridCorefResolver"),
            ("_entity_extractor", "core.agent.association.entity_extractor:EntityExtractor"),
        ]:
            if getattr(self, name, None) is not None:
                continue
            try:
                mod_path, cls_name = cls_path.split(":")
                mod = __import__(mod_path, fromlist=[cls_name])
                setattr(self, name, getattr(mod, cls_name)())
            except Exception:
                pass

        # ---- Phase 3: ChunkStore (G10-P1, env-configurable backend) ----
        try:
            if getattr(self, "_chunk_store", None) is None:
                from core.agent.storage.chunk_store import ChunkStore
                chunk_backend = _os.environ.get("DM_CHUNK_BACKEND", "in_memory")
                bge = None
                if chunk_backend == "unified":
                    try:
                        from core.infrastructure.model_service import get_model_service
                        svc = get_model_service()
                        if svc.status == "warm":
                            bge = svc
                    except Exception:
                        bge = None
                self._chunk_store = ChunkStore(backend=chunk_backend, bge_model=bge)
                self._chunk_backend = chunk_backend
            # P0 写即索引（RECALL_SUBGRAPH_BRIDGE §六）: 工具侧经
            # ToolRegistry 配置拿到 chunk_store, write_file 产出内容入库。
            try:
                from core.agent.tools.registry import ToolRegistry
                ToolRegistry.set_config({"chunk_store": self._chunk_store})
            except Exception:
                pass
        except Exception:
            pass

        # ---- Phase 4: EventLog path correction (data/event_log.db) ----
        try:
            from core.agent.api.api_event_log import EventLog
            _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
                _os.path.dirname(_os.path.abspath(__file__)))))
            _db = _os.path.join(_root, "data", "event_log.db")
            old = getattr(self, "_event_log", None)
            if old is not None and hasattr(old, "close"):
                try:
                    old.close()
                except Exception:
                    pass
            self._event_log = EventLog(db_path=_db)
            self._event_log.open()
        except Exception:
            pass

        # ---- Phase 5: Storage + Tracer ----
        try:
            from core.agent.event.storage import StorageLayer
            if getattr(self, "_storage", None) is None:
                # G10-P2: ???????????TieredStorageManager (Hot/Warm/Cold)
                self._storage = StorageLayer(enable_tiered=True)
        except Exception:
            pass
        try:
            from core.agent.event.tracer import PipelineTracer
            if getattr(self, "_tracer", None) is None:
                self._tracer = PipelineTracer()
        except Exception:
            pass

        # ---- Phase 6: Guards + closure (RateGuard/Capability/HotReload) ----
        try:
            from core.agent.event.closure import RateGuard, CapabilityGuard, HotReloader, CascadeDetector
            if getattr(self, "_rate_guard", None) is None:
                self._rate_guard = RateGuard()
            if getattr(self, "_cascade", None) is None:
                self._cascade = CascadeDetector(self._rate_guard)
            if getattr(self, "_capability_guard", None) is None:
                self._capability_guard = CapabilityGuard()
                self._cap_guard = self._capability_guard  # legacy alias
            if getattr(self, "_hot_reloader", None) is None:
                self._hot_reloader = HotReloader()
        except Exception:
            pass

        # ---- Phase 7: NATS hybrid bus (graceful fallback to memory) ----
        try:
            from core.agent.event.nats_bridge import wire_hybrid_bus
            nats_ok = wire_hybrid_bus(self)
            logger.info("NATS hybrid bus: %s", "active" if nats_ok else "memory fallback")
        except Exception:
            pass

        # ---- Phase 8: StateMachine + handlers (REQUIRED pipeline) ----
        try:
            from core.agent.event.statemachine import DeciderStateMachine
            from core.agent.event.handlers import register_all_handlers
            if getattr(self, "_state_machine", None) is None:
                self._state_machine = DeciderStateMachine()
            _ = register_all_handlers(self, tracer=getattr(self, "_tracer", None))
        except Exception as e:
            logger.error("StateMachine assembly failed: %s", e)
            self._state_machine = None

        # ---- Phase 9: Knowledge Graph ----
        try:
            from core.agent.knowledge.rag_bridge import RAGBridge
            if getattr(self, "_rag_bridge", None) is None:
                self._rag_bridge = RAGBridge()
        except Exception:
            pass
        try:
            from core.agent.knowledge.frame_source import FrameLibrary
            if getattr(self, "_frame_library", None) is None:
                self._frame_library = FrameLibrary()
                self._frame_library.load_default()
        except Exception:
            pass

        # ---- Phase 10: BehaviorGraph adapter ----
        try:
            from core.agent.behavior.adapter import BehaviorGraphAdapter
            if getattr(self, "_behavior_graph_adapter", None) is None:
                self._behavior_graph_adapter = BehaviorGraphAdapter(
                    graph_path="data/behavior_graph.json", auto_save=True)
        except Exception:
            pass

        # ---- Phase 11: ToolRegistry ----
        try:
            from core.agent.tools.registry import ToolRegistry
            if getattr(self, "_tool_registry", None) is None:
                import core.agent.tools.builtin
                self._tool_registry = ToolRegistry()
        except Exception:
            pass

        # ---- Phase 12: Learning ingestion ----
        try:
            from core.agent.learning.sources import ArxivSource, DuckDuckGoSource, ScholarSource
            from core.agent.learning.content_fetcher import ContentFetcher
            from core.agent.learning.credibility import CredibilityEvaluator
            if getattr(self, "_learning_sources", None) is None:
                self._learning_sources = [ArxivSource(), DuckDuckGoSource(), ScholarSource()]
                self._content_fetcher = ContentFetcher()
                self._credibility_eval = CredibilityEvaluator()
        except Exception:
            pass

        # ---- Phase 13: Deep engine objects ----
        try:
            from core.agent.v4.cognitive.simulation_engine import InternalSimulationEngine
            if getattr(self, "_simulation_engine", None) is None:
                self._simulation_engine = InternalSimulationEngine(self._llm_provider)
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.ocean_profile import OCEANProfileAnalyst
            if getattr(self, "_ocean_analyst", None) is None:
                self._ocean_analyst = OCEANProfileAnalyst(self._llm_provider)
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.metacognition import MetaCognition
            if getattr(self, "_meta_cognition", None) is None:
                self._meta_cognition = MetaCognition(
                    llm_provider=self._llm_provider, vcs=None)
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.inertia_graph import InertiaWeightGraph
            if getattr(self, "_inertia_graph", None) is None:
                self._inertia_graph = InertiaWeightGraph()
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.behavior_discovery import BehaviorDiscovery
            if getattr(self, "_behavior_discovery", None) is None:
                self._behavior_discovery = BehaviorDiscovery()
        except Exception:
            pass
        try:
            from core.agent.engineering.knowledge_graph import KnowledgeGraph
            if getattr(self, "_engineering_knowledge", None) is None:
                self._engineering_knowledge = KnowledgeGraph()
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.abc_orchestrator import ABCOrchestrator
            if getattr(self, "_abc", None) is None:
                self._abc = ABCOrchestrator(
                    llm_provider=self._llm_provider, enable_b=True, enable_c=True)
        except Exception:
            pass
        try:
            from core.agent.v4.cognitive.mind import Mind
            if getattr(self, "_mind", None) is None:
                self._mind = Mind(persist_dir="data")
        except Exception:
            pass

        # ---- Phase 14: Cross-deps (event_log/event_bus/subscribers) ----
        event_log = loaded.get("event_log")
        event_bus = loaded.get("event_bus")
        if event_log and event_bus:
            for sub in ("meta_subscriber", "assoc_subscriber"):
                if sub in loaded:
                    obj = loaded[sub]
                    try:
                        obj.event_log = event_log
                        obj._bus = event_bus
                        obj.bus = event_bus
                        if sub == "meta_subscriber" and hasattr(obj, "subscribe"):
                            obj.subscribe()
                    except Exception:
                        pass
        # M5-M1: ??? FeedbackBridge (cold-path MetaSubscriber ??/ hot-path ???)
        try:
            from core.agent.meta.feedback_bridge import FeedbackBridge
            fb = getattr(self, "_feedback_bridge", None)
            if fb is None:
                fb = FeedbackBridge()
                self._feedback_bridge = fb
            ms = loaded.get("meta_subscriber")
            if ms is not None and getattr(ms, "_bridge", None) is None:
                ms._bridge = fb
        except Exception:
            pass
        if "meta_cognition" in loaded:
            mc = loaded["meta_cognition"]
            if hasattr(mc, "_vcs") and hasattr(self, "_vcs"):
                mc._vcs = getattr(self, "_vcs", None)

        # P2: intent parser must carry a real LLM (registry no-arg instances
        # silently degrade the splitter). Rebuild if missing.
        try:
            self._init_intent_runtime()
        except Exception:
            pass

        # ---- Phase 15: Meta runtime (ExecutionTraceV3 + MetaConsumer) ----
        if hasattr(self, "_init_meta_runtime"):
            try:
                self._init_meta_runtime()
            except Exception:
                pass

        self._bootstrap_ms = round((_time.time() - t0) * 1000, 1)
        self._bootstrap_failed = failed
        self._bootstrap_done = True

        # TREE_TIERING: 启动预加载 discourse 树（Warm→Hot, 失败不阻塞）
        try:
            self._warm_start_discourse()
        except Exception:
            pass

        # Unified async prewarm (cold-load latency avoidance)
        try:
            from core.infrastructure.model_service import prewarm_models
            prewarm_models(blocking=False)
        except Exception:
            pass

        return {
            "status": "running",
            "provider": self._provider_type,
            "model": self._provider_model,
            "subsystems_loaded": len(loaded),
            "subsystems_total": len(results),
            "startup_ms": self._bootstrap_ms,
            "failed": failed,
        }


    # ------------------------------------------------------------------ #
    # B5-3 白盒编辑后端（M2）— 用户控制权（A19 白盒 + A17 记录永不可删）
    # ------------------------------------------------------------------ #

    def _init_whitebox(self) -> None:
        """Lazily initialize B5-3 white-box editing state (never fatal).

        Wires the three objects the /v6/edit/* API operates on:
          _correction_journal — every user edit is journaled (A17)
          _interaction_graph  — 层1 图结构 (user-editable relations)
          _last_context       — 层2 IR (what the LLM consumes, user-editable)
        The three-mode switch (_edit_mode) defaults to "smart" (A16 快反馈):
          smart     — 系统默认编译的子图 (默认智能)
          whitebox  — 用户可在图编辑层调整 (A19 落地)
          fullwhite — 用户关掉默认编译, 自己搓上下文 (Comfy 式全白)
        """
        # 1) CorrectionJournal — 每次用户修正记录 before/after (A17)
        if self._correction_journal is None:
            try:
                from core.agent.v4.cognitive.correction_journal import CorrectionJournal
                self._correction_journal = CorrectionJournal()
            except Exception as e:
                logger.debug("CorrectionJournal unavailable: %s", e)
                self._correction_journal = None

        # 2) InteractionGraph — 动态状态传播图 (层1 图结构)
        if self._interaction_graph is None:
            try:
                from core.agent.state.interaction_graph import InteractionGraph
                graph = InteractionGraph()
                # 有 substrate 时从真实关系构建（B2-3: 锚点/扩散属能力底座）
                rs = None
                wp = getattr(self, '_world_provider', None)
                if wp is not None:
                    rs = getattr(wp, 'relation_substrate', None)
                if rs is None:
                    rs = getattr(self, '_relation_substrate', None)
                if rs is None and getattr(self, '_behavior_graph_adapter', None) is not None:
                    rs = getattr(self._behavior_graph_adapter, 'graph', None)
                if rs is not None:
                    try:
                        graph.build_from_substrate(rs)
                    except Exception as e:
                        logger.debug("InteractionGraph substrate seed skipped: %s", e)
                self._interaction_graph = graph
            except Exception as e:
                logger.debug("InteractionGraph unavailable: %s", e)
                self._interaction_graph = None

        # 3) _last_context — 层2 IR 实体（IR 编辑/消费的底座）
        if self._last_context is None:
            try:
                from core.agent.context.cross_domain_ir import (
                    CrossDomainContextIR, IntentCategory,
                )
                self._last_context = CrossDomainContextIR(
                    intent_category=IntentCategory.CASUAL,
                    metadata={"source": "whitebox"},
                )
            except Exception as e:
                logger.debug("last_context unavailable: %s", e)

        # 4) _decision_bus — 决策变更事件总线（元认知仲裁 × 异步介入）
        #    EventLog 事件流 + CorrectionJournal 双写（META_ARBITER 设计 §3.2）
        #    每次 _init_whitebox 都刷新 attach（__init__ 时 event_log 尚未建,
        #    bootstrap 后需把真实 EventLog/Journal 绑定到已有 bus）。
        try:
            from core.agent.blueprint.decision_event import DecisionEventBus
            bus = getattr(self, "_decision_bus", None)
            if bus is None:
                bus = DecisionEventBus(
                    event_log=self._event_log,
                    journal=self._correction_journal,
                )
                self._decision_bus = bus
            else:
                bus.attach(
                    event_log=self._event_log,
                    journal=self._correction_journal,
                )
        except Exception as e:
            logger.debug("DecisionEventBus unavailable: %s", e)
            self._decision_bus = None

        # E5/E6 (ERROR_META_REFLECTION): 错误模式追踪器 — 同类错误滑动窗口
        # 计数 ≥ 阈值 → meta_advice 反思事件（自动）+ 用户明示触发（最高优先级）。
        # 与 decision_bus 同源装配（每轮刷新 attach）。
        try:
            from core.agent.common.error_pattern import (
                ErrorPatternTracker, maybe_user_explicit,
            )
            ep = getattr(self, "_error_pattern", None)
            if ep is None:
                ep = ErrorPatternTracker(decision_bus=self._decision_bus)
                self._error_pattern = ep
            else:
                ep.attach_bus(self._decision_bus)
            self._maybe_user_explicit = maybe_user_explicit
        except Exception as e:
            logger.debug("ErrorPatternTracker unavailable: %s", e)
            self._error_pattern = None

        # P1-2: 三层介入分级路由（低/中/高风险 → 介入方式）.
        # 与 decision_bus 同源装配; 提供 approve/reject 介入 API（PR review 语义）。
        try:
            from core.agent.blueprint.intervention import InterventionRouter
            ir = getattr(self, "_intervention", None)
            if ir is None:
                ir = InterventionRouter(decision_bus=self._decision_bus)
                self._intervention = ir
            else:
                ir.attach_bus(self._decision_bus)
        except Exception as e:
            logger.debug("InterventionRouter unavailable: %s", e)
            self._intervention = None

        # GAP-D2/D1/D5: 学习桥 + 技能生命周期（执行层→学习闭环原料管道）.
        #   learning_bridge: learn_blueprint 生产注入 + 蒸馏原料收集
        #   skill_lifecycle: LEARNED_TEMPLATES 活性状态机（只增不减 → 可裁剪）
        try:
            from core.agent.blueprint.learning_bridge import LearningBridge
            lb = getattr(self, "_learning_bridge", None)
            if lb is None:
                lb = LearningBridge(decision_bus=self._decision_bus)
                self._learning_bridge = lb
            else:
                lb.attach_bus(self._decision_bus)
            # 二阶抽象（A24 / blog chapter3）: 挂载变化驱动蒸馏管道
            try:
                from core.agent.blueprint.heuristic_distiller import HeuristicDistiller
                from core.agent.blueprint.heuristic_inventory import HeuristicInventory
                inv = getattr(self, "_heuristic_inventory", None)
                if inv is None:
                    inv = HeuristicInventory()
                    self._heuristic_inventory = inv
                if getattr(lb, "_distiller", None) is None:
                    dist = HeuristicDistiller(
                        llm_provider=getattr(self, "_llm_provider", None),
                        inventory=inv,
                        trace_store=lb.trace_store,
                    )
                    lb.attach_distiller(dist)
            except Exception as e:
                logger.debug("HeuristicDistiller attach failed: %s", e)
            # 生命周期挂到 SkillRegistry（registry 由 BlueprintEngine 懒建,
            # 这里通过 bridge 的 registry 挂; 生产路径 v3_session_api 建的
            # BlueprintEngine 会走 engine 持有的 bridge 共享 registry）
            try:
                from core.agent.blueprint.skill_lifecycle import SkillLifecycle
                lc = getattr(self, "_skill_lifecycle", None)
                if lc is None:
                    lc = SkillLifecycle()
                    self._skill_lifecycle = lc
                lb.registry.set_lifecycle(lc)
            except Exception as e:
                logger.debug("SkillLifecycle attach failed: %s", e)
        except Exception as e:
            logger.debug("LearningBridge unavailable: %s", e)
            self._learning_bridge = None

        # v2 执行层复盘回流（A6, 2026-08-09）: MetaFeedback 实例化 + 挂
        # decision_bus。TaskRunner 执行成败 → ExecutionAudit → consume →
        # 连续低分降级策略权重（check_degradations 由 _run_meta_consume 触发）。
        try:
            from core.agent.blueprint.meta_feedback import MetaFeedback
            mf = getattr(self, "_meta_feedback", None)
            if mf is None:
                mf = MetaFeedback(decision_bus=self._decision_bus)
                self._meta_feedback = mf
            else:
                mf.attach_bus(self._decision_bus)
        except Exception as e:
            logger.debug("MetaFeedback unavailable: %s", e)
            self._meta_feedback = None

    def learn_from_execution(self, dag, intent: str = "", request_id: str = "",
                             success: bool = True) -> dict:
        """GAP-D2: 生产学习入口 — StateMachine.run_dag 之后调用.

        沉淀含 tool 节点的成功 DAG + 收集蒸馏原料 + 周期批量蒸馏.
        """
        lb = getattr(self, "_learning_bridge", None)
        if lb is None:
            return {"learned": False, "reason": "learning bridge unavailable"}
        learned = lb.learn_from_execution(
            dag, intent, request_id=request_id, success=success)
        return {"learned": learned, "summary": lb.summary()}

    def _ensure_negative_kb(self):
        """TieredNegativeKB 懒加载 + 种子规则（负知识约束, 与权限引擎互补）。"""
        nk = getattr(self, "_negative_kb", None)
        if nk is not None:
            return nk
        try:
            from core.agent.negative_kb.tiered import TieredNegativeKB, SEED_RULES
            nk = TieredNegativeKB()
            for rule in SEED_RULES:
                try:
                    nk.register(rule)
                except Exception:
                    pass
            self._negative_kb = nk
        except Exception as e:
            logger.debug("negative kb unavailable: %s", e)
            self._negative_kb = None
        return self._negative_kb

    def skill_lifecycle_report(self, dry_run: bool = True) -> dict:
        """GAP-D5: 技能活性报告（dry_run 预测 / 非 dry 执行迁移）."""
        lc = getattr(self, "_skill_lifecycle", None)
        if lc is None:
            return {"error": "skill lifecycle unavailable"}
        if not dry_run:
            lc.apply_transitions()
        return lc.report(dry_run=dry_run)

    def intervention_approve(self, dimension: str = "",
                             kind: str = "strategy_switch",
                             comment: str = "") -> dict:
        """P1-2: 中风险决策 approve（PR review 语义, 前端/API 调用）."""
        ir = getattr(self, "_intervention", None)
        if ir is None:
            return {"ok": False, "error": "intervention router unavailable"}
        ev = ir.approve(dimension=dimension, kind=kind, comment=comment)
        return {"ok": ev is not None, "event": ev}

    def intervention_reject(self, dimension: str = "",
                            kind: str = "strategy_switch",
                            comment: str = "") -> dict:
        """P1-2: 中风险决策 reject（否决, 事件流留痕）."""
        ir = getattr(self, "_intervention", None)
        if ir is None:
            return {"ok": False, "error": "intervention router unavailable"}
        ev = ir.reject(dimension=dimension, kind=kind, comment=comment)
        return {"ok": ev is not None, "event": ev}

    def trigger_error_reflection(self, text: str = "",
                                 reason: str = "") -> dict:
        """E6: 用户明示触发反思 — "反复出现" 类输入 → 最高优先级 meta_advice.

        显式调用（API/CLI 层在用户消息中检测到 EXPLICIT_PHRASES 时调用）;
        亦提供 maybe_user_explicit 供上层判断。返回触发结果（可回看事件）。
        """
        ep = getattr(self, "_error_pattern", None)
        if ep is None:
            return {"triggered": False, "reason": "error_pattern tracker unavailable"}
        check_explicit = getattr(self, "_maybe_user_explicit", None)
        if check_explicit is None:
            try:
                from core.agent.common.error_pattern import maybe_user_explicit as check_explicit
            except Exception:
                check_explicit = lambda s: False  # noqa: E731
        if text and not check_explicit(text) and not reason:
            return {"triggered": False, "count": ep.counts()}
        return ep.explicit_trigger(
            error_type="user_explicit",
            reason=reason or f"用户明示: {text[:120]}",
            turn=getattr(self, "_turn_counter", 0),
        )

    def llm_health(self) -> dict:
        """B3: LLM provider health snapshot (white-box A19).

        Aggregates the provider's sliding-window metrics (success rate,
        latency, error breakdown) so gateway/provider failures are visible
        without digging into logs.
        """
        prov = getattr(self, "_llm_provider", None)
        if prov is None:
            return {"available": False}
        try:
            stats = prov.get_recent_stats(window=20)
            history = getattr(prov, "_metrics_history", [])
            errs: Dict[str, int] = {}
            for m in history[-50:]:
                if not m.success:
                    et = m.error_type or "unknown"
                    errs[et] = errs.get(et, 0) + 1
            return {
                "available": True,
                "provider": getattr(prov, "name", "?"),
                "model": getattr(prov, "_default_model", ""),
                "recent": stats,
                "errors": errs,
                "last_error": {
                    "type": m.error_type,
                    "status": m.status_code,
                } if history and not history[-1].success else None,
            }
        except Exception as e:
            logger.debug("llm_health failed: %s", e)
            return {"available": False, "error": str(e)}

    def _set_edit_mode(self, mode: str) -> str:
        """三档模式切换（白盒开关）。返回旧模式。"""
        if mode not in ("smart", "whitebox", "fullwhite"):
            raise ValueError(f"invalid edit mode: {mode}")
        old = getattr(self, "_edit_mode", "smart")
        self._edit_mode = mode
        return old

    def whitebox_state(self) -> dict:
        """B5-3 白盒状态快照（A19 可检查）。"""
        self._init_whitebox()
        j = self._correction_journal
        ig = self._interaction_graph
        lc = self._last_context
        return {
            "mode": getattr(self, "_edit_mode", "smart"),
            "journal": j.stats() if j else {"total_corrections": 0},
            "graph_nodes": len(getattr(ig, "_node_states", {})) if ig else 0,
            "graph_edges": len(getattr(ig, "_adjacency", {})) if ig else 0,
            "ir_entries": len(getattr(lc, "entries", [])) if lc else 0,
        }

    # ------------------------------------------------------------------ #
    # B1-8 认知运行时（M3）— Observer/Scheduler/思考树/编译器 懒初始化
    # ------------------------------------------------------------------ #

    def _init_cognitive_runtime(self) -> None:
        """Lazily initialize the cognitive runtime (never fatal).

        B1-8-P2 + LLM-3-P1: engine 挂载 A 套认知运行时 + v3_0 思考树 +
        CognitiveCompiler。默认不启用（_cognitive_runtime_enabled=False,
        A16 快速通道不经过认知循环）；LLM 主推理路径可开启。
        """
        if self._cognitive_observer is None:
            try:
                from core.agent.v4.cognitive.scheduler import Observer
                self._cognitive_observer = Observer()
            except Exception as e:
                logger.debug("Cognitive Observer unavailable: %s", e)
        if self._cognitive_scheduler is None:
            try:
                from core.agent.v4.cognitive.scheduler import CognitiveScheduler
                self._cognitive_scheduler = CognitiveScheduler(
                    metacognition=getattr(self, "_meta_cognition", None))
            except Exception as e:
                logger.debug("Cognitive Scheduler unavailable: %s", e)
        if self._cognitive_tree is None:
            try:
                from core.agent.v3_0.cognitive_tree.manager import CognitiveTree
                self._cognitive_tree = CognitiveTree(session_id="default")
            except Exception as e:
                logger.debug("CognitiveTree unavailable: %s", e)
        if self._cognitive_compiler is None:
            try:
                from core.agent.cognitive_compiler.compiler import CognitiveCompiler
                self._cognitive_compiler = CognitiveCompiler(
                    tree_store=self._cognitive_tree,
                )
            except Exception as e:
                logger.debug("CognitiveCompiler unavailable: %s", e)

    def _init_meta_runtime(self) -> None:
        """M5-M3/M8: 元认知运行时懒初始化（ExecutionTraceV3 + MetaConsumer），非致命。

        审计实锤: _trace_v3/_meta_consumer 此前恒 None → 每 5 轮学习闭环从未执行。
        修复 = 接线实例化（非重写类）。
        """
        if self._trace_v3 is None:
            try:
                from core.agent.state.execution_trace import ExecutionTraceV3
                self._trace_v3 = ExecutionTraceV3(
                    session_id=getattr(self, "_session_id", "default")
                )
            except Exception as e:
                logger.debug("ExecutionTraceV3 unavailable: %s", e)
        if self._meta_consumer is None:
            try:
                from core.agent.v4.cognitive.meta_consumer import MetaConsumer
                # B3: strategy engine is attached by the registry under its
                # subsystem name `strategy_engine`; keep the legacy alias as
                # a fallback for direct constructions.
                strategy = (
                    getattr(self, "_strategy_engine", None)
                    or getattr(self, "_contextual_strategy", None)
                )
                self._meta_consumer = MetaConsumer(strategy_engine=strategy)
            except Exception as e:
                logger.debug("MetaConsumer unavailable: %s", e)

    def _run_meta_consume(self) -> dict:
        """M5-M3: 每 5 轮消费 ExecutionTraceV3 → MetaConsumer 建议 → 审核队列。"""
        if self._trace_v3 is None or self._meta_consumer is None:
            return {"adjust": False}
        try:
            advice = self._meta_consumer.consume(self._trace_v3, self._turn_counter)
            if advice and advice.get("adjust"):
                mc = getattr(self, "_meta_cognition", None)
                if mc is not None:
                    if hasattr(mc, "consume_trace"):
                        mc.consume_trace(self._trace_v3, self._turn_counter)
                    else:
                        for warning in (advice.get("warnings") or [])[:3]:
                            try:
                                mc.submit(
                                    source="self", target="learning_loop",
                                    data={"warning": warning, "turn": self._turn_counter},
                                )
                            except Exception:
                                pass
            # A6 复盘回流: 每 5 轮检查蓝图策略权重降级/升级（真实副作用:
            # 连续低分 LLM_DRIVEN→HYBRID→TEMPLATE, 高分恢复）。
            try:
                mf = getattr(self, "_meta_feedback", None)
                if mf is not None and hasattr(mf, "check_degradations"):
                    mf.check_degradations()
            except Exception:
                pass
            return advice
        except Exception as e:
            logger.debug("Meta consume failed: %s", e)
            return {"adjust": False}

    def _init_intent_runtime(self) -> None:
        """Lazily initialize the Agent-Native intent pipeline (I3/R3, never fatal).

        T1 热路径 = intent/ 新包（DualTrackIntentPipeline → MultiIntentSplitter
        5 链验证 + FusionDecider + AmbiguityGate）。无 LLM 时 splitter 显式
        降级（trace.degraded），不静默跳过。旧 v3_common shim 因断链恒为
        None —— 新包接线后 handle_intent 不再依赖 shim。
        """
        # P2: registry ??????????? _intent_parser?llm=None ?
        # MultiIntentSplitter ?????? llm ???????? T1 ???
        # ???? provider?B3 ???splitter.llm ??? False??
        existing = getattr(self, "_intent_parser", None)
        if existing is not None:
            splitter = getattr(existing, "_splitter", None)
            if splitter is not None and getattr(splitter, "llm", None) is not None:
                return
            # llm ?? ? ????????? belief_acc ??????????
            # ?????????registry ??????????????
        try:
            from core.agent.intent.dual_track import DualTrackIntentPipeline
            self._intent_parser = DualTrackIntentPipeline(
                llm=self._llm_provider,
                belief_acc=getattr(self, "_l2_5_belief", None),
            )
        except Exception as e:
            logger.debug("Intent runtime (Agent-Native) unavailable: %s", e)

    def cognitive_state(self) -> dict:
        """认知层状态快照（A19 白盒可检查）。"""
        self._init_cognitive_runtime()
        tree = self._cognitive_tree
        return {
            "enabled": self._cognitive_runtime_enabled,
            "observer": self._cognitive_observer is not None,
            "scheduler": self._cognitive_scheduler is not None,
            "tree_nodes": len(getattr(tree, "nodes", {})) if tree else 0,
            "tree_edges": len(getattr(tree, "edges", [])) if tree else 0,
            "prediction_stats": dict(self._prediction_stats),
        }

    # ------------------------------------------------------------------ #
    # LLM-1 共享树接线（M3-P3）— 6 LLM 思考记录唯一写树入口
    # ------------------------------------------------------------------ #

    def record_llm_thought(self, llm_instance: str, content: str,
                           node_type: str = "REASONING",
                           confidence: float = 0.5,
                           action: str = None,
                           action_result: str = None,
                           cross_refs: list = None,
                           session_id: str = "default") -> dict:
        """Write one LLM thought into the shared cognitive tree (LLM-1).

        Single entry point (CognitiveCompiler). 6 LLM instances
        (pcr/intent/meta/planning/answer/reflective) all write here.
        """
        self._init_cognitive_runtime()
        compiler = self._cognitive_compiler
        if compiler is None:
            return {"nodes_created": 0, "reason": "compiler unavailable"}
        try:
            from core.agent.cognitive_compiler.compiler import CompileInput
            result = compiler.compile(
                [CompileInput(
                    llm_instance=llm_instance, content=content[:500],
                    node_type=node_type, confidence=confidence,
                    action=action, action_result=action_result,
                    cross_refs=cross_refs or [],
                )],
                session_id=session_id,
            )
            return {"nodes_created": result.nodes_created,
                    "edges_created": result.edges_created}
        except Exception as e:
            logger.debug("record_llm_thought failed: %s", e)
            return {"nodes_created": 0, "reason": str(e)[:100]}

    # ------------------------------------------------------------------ #
    # LLM-3 对内执行预测学习（M3-P4）— PREDICT/EXECUTE/COMPARE/LEARN
    # ------------------------------------------------------------------ #

    def predict_execution(self, action_desc: str) -> dict:
        """PREDICT — 执行前预测结果（LLM-3, 分支预测类比）。

        从思考树读取历史同类预测（PREDICTION 节点），若无历史则
        给出保守默认。规则/历史优先，LLM 可选（A16 快慢）。
        """
        self._init_cognitive_runtime()
        tree = self._cognitive_tree
        prediction = {"expected": "unknown", "confidence": 0.3,
                      "evidence": [], "action": action_desc[:200]}
        if tree is None:
            return prediction
        try:
            from core.agent.v3_0.cognitive_tree.models import CogType
            key = action_desc[:80].lower()
            best = None
            for node in tree.nodes.values():
                if getattr(node, "cog_type", None) != CogType.PREDICTION:
                    continue
                meta = getattr(node, "metadata", {}) or {}
                # action 存在 node.action（compiler 写入）或 metadata（历史格式）
                action_field = str(getattr(node, "action", "") or
                                   meta.get("action", "") or "")
                if key in action_field.lower()[:80]:
                    if best is None or node.confidence > best.confidence:
                        best = node
            if best is not None:
                meta = best.metadata or {}
                result_str = str(getattr(best, "action_result", "") or "")
                expected = meta.get("expected") or ""
                if not expected and result_str.startswith("predicted="):
                    expected = result_str.split("predicted=")[-1].split(" actual=")[0]
                prediction = {
                    "expected": expected or "unknown",
                    "confidence": float(getattr(best, "confidence", 0.3)),
                    "evidence": [best.node_id],
                    "action": action_desc[:200],
                }
            return prediction
        except Exception as e:
            logger.debug("predict_execution failed: %s", e)
            return prediction

    def record_execution_outcome(self, action_desc: str, predicted: str,
                                 actual: str) -> dict:
        """EXECUTE→COMPARE→LEARN — 执行结果对照 + 差异回写思考树。

        COMPARE: predicted vs actual 一致性判定
        LEARN:   写 PREDICTION 节点（含 expected/result/action 元数据）
                 更新自监督统计（命中/未命中, A6）
        """
        self._init_cognitive_runtime()
        hit = str(predicted).strip() == str(actual).strip()
        self._prediction_stats["predictions"] += 1
        if hit:
            self._prediction_stats["hits"] += 1
        else:
            self._prediction_stats["misses"] += 1
        wrote = self.record_llm_thought(
            llm_instance="prediction_engine",
            content=f"action={action_desc[:200]} predicted={predicted} actual={actual}",
            node_type="PREDICTION",
            confidence=0.9 if hit else 0.4,
            action=action_desc[:200],
            action_result=f"predicted={predicted} actual={actual} hit={hit}",
            cross_refs=[],
        )
        return {
            "hit": hit,
            "predicted": predicted,
            "actual": actual,
            "stats": dict(self._prediction_stats),
            "wrote": wrote,
        }

    def _run_cognitive_prepass(self, text: str,
                               session_id: str = "default") -> Optional[object]:
        """B1-8-P3 — run_cognitive_loop 可选前置（A16 快慢分流）。

        快速通道（短文本 / 无深推理需求）不经过认知循环。
        认知循环产出 → workspace → cognitive_tree（B1-8-P4 联动）。
        """
        if not self._cognitive_runtime_enabled:
            return None
        if not text or len(text) < 8:
            return None  # 快速通道: 太短不跑认知循环
        self._init_cognitive_runtime()
        if self._cognitive_observer is None or self._cognitive_scheduler is None:
            return None
        try:
            from core.agent.v4.cognitive.runtime import run_cognitive_loop
            trace = run_cognitive_loop(
                question=text,
                observer=self._cognitive_observer,
                scheduler=self._cognitive_scheduler,
                engine=self,
                max_iterations=3,
            )
            # B1-8-P4: workspace 推理 → 共享树
            ws = getattr(self._cognitive_observer, "workspace", None)
            if ws is not None:
                for hyp in list(getattr(ws, "hypotheses", []))[:5]:
                    self.record_llm_thought(
                        llm_instance="cognitive_loop",
                        content=str(hyp)[:500],
                        node_type="HYPOTHESIS",
                        confidence=getattr(ws, "confidence", 0.5),
                        session_id=session_id,
                    )
                for cand in list(getattr(ws, "candidate_answers", []))[:3]:
                    content = cand.get("content", "") if isinstance(cand, dict) else str(cand)
                    if content:
                        self.record_llm_thought(
                            llm_instance="cognitive_loop",
                            content=content[:500],
                            node_type="REASONING",
                            confidence=getattr(ws, "confidence", 0.5),
                            session_id=session_id,
                        )
            return trace
        except Exception as e:
            logger.debug("cognitive prepass skipped: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Behavior chain brain (P1: ADR-013 — background prior, never same-turn)
    # ------------------------------------------------------------------ #

    def _init_behavior_brain(self) -> None:
        """Lazily build the behavior-chain brain (predictor+rewarder+training).

        Never fatal: the brain is a background prior — if it cannot start, the
        hot path keeps running with behavior recording only.
        """
        if self._behavior_brain_ready:
            return
        self._behavior_brain_ready = True
        try:
            from core.agent.behavior.brain import BehaviorBrain
            graph = None
            if self._behavior_graph_adapter is not None:
                graph = self._behavior_graph_adapter.graph
            self._behavior_brain = BehaviorBrain(
                graph=graph, llm_provider=self._llm_provider,
                # 3.3: 显式承诺持久化固定路径（registry 支持 store_path）
                commitments_store_path="data/behavior/commitments.json",
            )
            logger.debug("BehaviorBrain ready: nodes=%d edges=%d",
                         len(getattr(self._behavior_brain.graph, "nodes", {})),
                         len(getattr(self._behavior_brain.graph, "edges", {})))
        except Exception as e:
            logger.debug("BehaviorBrain unavailable: %s", e)

    def _run_behavior_brain(self, event) -> None:
        """Learn from observed event + background-predict next step (ADR-013)."""
        if self._behavior_brain is None:
            self._init_behavior_brain()
        brain = self._behavior_brain
        if brain is None:
            return
        try:
            # B7 (3.3): PCR 视角传入声明识别（zone 调置信度门槛）
            pcr_zone = ""
            if self._last_pcr is not None:
                pcr_zone = getattr(self._last_pcr, "zone", "") or ""
                if isinstance(self._last_pcr, dict):
                    pcr_zone = self._last_pcr.get("zone", "") or ""
            brain.learn_from_event(event, pcr_zone=pcr_zone)
            brain.predict_next_background()
            # B5 (3.3): 冷启动回退重模拟 — PCR 特征板机触发时后台补承诺
            self._maybe_commitment_resimulation(brain)
        except Exception as e:
            logger.debug("BehaviorBrain event failed: %s", e)
        # C1: CausalPlanner 同步喂因果链（record_step）——行为事件即因果事件。
        # 冷路径失败不阻塞；链长达标由 slow_path 在 on_session_end 触发。
        try:
            self._init_causal_planner()
            if self._causal_planner is not None and hasattr(self._causal_planner, "record_step"):
                self._causal_planner.record_step(event)
        except Exception as e:
            logger.debug("CausalPlanner record_step failed: %s", e)

    def _init_causal_planner(self) -> None:
        """C1: CausalPlanner 懒挂载（行为链审计: 470 行实现零实例化）。

        graph 复用 _behavior_graph_adapter.graph（一内核）；v3_2 组件
        （BehaviorGraph/CausalSubstrate）由 planner._ensure_v3_2 惰性加载。
        非致命：失败则保持 None，热路径不受影响。
        """
        if getattr(self, "_causal_planner", None) is not None:
            return
        try:
            from core.agent.causal.planner import CausalPlanner
            graph = None
            if getattr(self, "_behavior_graph_adapter", None) is not None:
                graph = getattr(self._behavior_graph_adapter, "graph", None)
            planner = CausalPlanner(behavior_graph=graph)
            planner._ensure_v3_2()
            self._causal_planner = planner
            logger.debug("CausalPlanner mounted (nodes=%d)",
                         len(getattr(graph, "nodes", {})))
        except Exception as e:
            logger.debug("CausalPlanner unavailable: %s", e)
            self._causal_planner = None

    def _trigger_causal_slow_path(self) -> Optional[dict]:
        """C1 slow_path: 链长达标时 process_chain（D6「无 slow_path」修复）。

        CausalSubstrate.process_chain → structural prior 更新 → 下游
        （subgraph P/F 域 / ContextAssembler CausalContextSource）消费。
        """
        try:
            self._init_causal_planner()
            if self._causal_planner is None or not hasattr(self._causal_planner, "process_chain"):
                return {"available": False}
            result = self._causal_planner.process_chain()
            return {
                "available": True,
                "triggered": bool(getattr(result, "triggered", False)),
                "edge_updates": len(getattr(result, "edge_updates", []) or []),
                "chain_len": len(getattr(result, "chain", []) or []),
            }
        except Exception as e:
            logger.debug("Causal slow path failed: %s", e)
            return {"available": False}

    def _maybe_commitment_resimulation(self, brain) -> None:
        """B5 (3.3): 回退重模拟 engine 接线。

        ``simulate_with_retry`` 原语已就绪但零调用 — 这里在
        ``cold_start_retry_trigger``（turn<=3 或 PCR ABYSS/CHAOS/MIXED +
        ambiguity>0.5）触发时后台跑一次模拟，产出 Commitment（source=distilled）
        入 registry。冷路径：失败只 debug，不阻塞主流程。
        """
        try:
            from core.agent.behavior.explicit_commitment import (
                cold_start_retry_trigger,
                simulate_with_retry,
            )
            pcr_output = self._last_pcr
            turn = self._turn_counter
            if not cold_start_retry_trigger(pcr_output, turn=turn):
                return
            llm = getattr(brain, "_llm_provider", None)
            if llm is None:
                return
            # 只补一条最近场景的模拟承诺（避免每轮轰炸）
            if getattr(brain, "_resim_ran", False):
                return
            brain._resim_ran = True
            scenario = (
                getattr(pcr_output, "labels", None) or
                (pcr_output.get("labels") if isinstance(pcr_output, dict) else None) or
                "当前会话冷启动"
            )
            scenario = str(scenario)[:200]

            def _run():
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        commit = loop.run_until_complete(simulate_with_retry(
                            llm, scenario, success_check=lambda _: (True, "ok"),
                        ))
                    finally:
                        loop.close()
                    if commit is not None and not brain.commitments.match(scenario):
                        brain.commitments.add(
                            when=scenario[:80],
                            should=commit.should,
                            source="distilled",
                            because=commit.because,
                            metadata={"sim_attempts": commit.metadata.get("sim_attempts", 1)},
                        )
                except Exception as e:
                    logger.debug("B5 re-simulation failed: %s", e)

            import threading
            threading.Thread(target=_run, daemon=True).start()
        except Exception as e:
            logger.debug("B5 trigger check failed: %s", e)

    def _behavior_brain_stats(self) -> dict:
        if self._behavior_brain is None:
            return {"ready": False}
        try:
            stats = self._behavior_brain.stats()
            stats["ready"] = True
            return stats
        except Exception as e:
            return {"ready": False, "error": str(e)[:100]}

    # ------------------------------------------------------------------ #
    # Association chain cold-path components (D-3 / D-15)
    # ------------------------------------------------------------------ #

    def _init_association_components(self) -> None:
        """Lazily instantiate L1→L3 association components (never fatal).

        Kept in one place so the runtime engine, event subscribers, and the
        state-machine pre-processor all read the same instances (D-2: one
        kernel, multiple facades — no second parallel wiring).
        """
        if self._association_components_ready:
            return
        self._association_components_ready = True

        try:
            from core.agent.association.pronoun_resolver import StanzaCorefResolver
            self._pronoun_resolver = StanzaCorefResolver()
            self._l1_extractor = self._pronoun_resolver
        except Exception as e:  # pragma: no cover - env dependent
            logger.debug("Association L1 resolver unavailable: %s", e)

        try:
            from core.agent.association.context_qualifier import ContextQualifier
            self._context_qualifier = ContextQualifier()
        except Exception as e:  # pragma: no cover
            logger.debug("Association L1.5 qualifier unavailable: %s", e)

        try:
            from core.agent.association.l1_modifier import ModifierExtractor
            self._l1_modifier = ModifierExtractor()
        except Exception as e:  # pragma: no cover
            logger.debug("Association L1 modifier unavailable: %s", e)

        try:
            from core.agent.association.l2_5_belief import BeliefAccumulator
            self._l2_5_belief = BeliefAccumulator()
        except Exception as e:  # pragma: no cover
            logger.debug("Association L2.5 belief unavailable: %s", e)

        try:
            from core.agent.association.l3_intent import MultiPerspectiveValidator
            self._l3_validator = MultiPerspectiveValidator(llm_provider=self._llm_provider)
        except Exception as e:  # pragma: no cover
            logger.debug("Association L3 validator unavailable: %s", e)

        try:
            from core.agent.association.association_funnel import AssociationFunnel
            self._association_funnel = AssociationFunnel(llm_provider=self._llm_provider)
        except Exception as e:  # pragma: no cover
            logger.debug("AssociationFunnel unavailable: %s", e)

        logger.debug(
            "Association components: l1=%s qualifier=%s belief=%s l3=%s funnel=%s",
            self._l1_extractor is not None,
            self._context_qualifier is not None,
            self._l2_5_belief is not None,
            self._l3_validator is not None,
            self._association_funnel is not None,
        )

    def _init_association_service(self) -> None:
        """Phase 6: 实例化关联链独立服务（蓝图 §7.3，非致命）。

        ``AssociationService`` 是 M→1 定向通道 + EventLog Event Sourcing 内核：
        各模块产出经 ``_publish`` 定向投递（不广播），服务后台线程按 last_seq
        增量消费、崩溃重放、触发阈值后产出 association_discovered。
        """
        if self._assoc_service is not None:
            return
        try:
            from core.agent.association.association_service import AssociationService
            service = AssociationService(
                llm_provider=self._llm_provider,
                db_path="data/event_log.db",
            )
            self._assoc_service = service
            self._assoc_sub = service  # 旧属性名兼容（CLI registry）
            service.on_discover(self._on_association_discovered)
            service.start()
            logger.debug("AssociationService wired (M→1 directed channel)")
        except Exception as e:
            logger.debug("AssociationService unavailable: %s", e)
            self._assoc_service = None

    def _on_association_discovered(self, event: dict) -> None:
        """关联链定向输出回调：写入白盒（A19），供 `dm assoc`/上下文消费。"""
        payload = event.get("payload", {})
        self._last_association = {
            "discovery": payload,
            "ts": payload.get("ts"),
        }
        self._association_relations.setdefault("discovered", []).append(payload)
        # C2: CognitionHub.ingest_relations — 关联链漏斗产出喂给认知汇聚层
        # （审计: ingest_relations 全库零调用 → converge 空转）。discovery
        # payload 含 l1/l3/l4/l5 摘要与关系线索，转成 relations 缓冲。
        try:
            hub = getattr(self, "_cognition_hub", None)
            if hub is None:
                from core.agent.cognition.hub import CognitionHub
                hub = CognitionHub()
                self._cognition_hub = hub
            relations = payload.get("relations") or payload.get("l3") or []
            if isinstance(relations, list) and relations:
                hub.ingest_relations(relations)
                if hub.is_loaded:
                    hub.converge()
        except Exception as e:
            logger.debug("CognitionHub feed failed: %s", e)
        # 监控: 关联链发现指标接入 tracer（非黑盒，可回查）
        tracer = getattr(self, "_tracer", None)
        if tracer is not None:
            try:
                latency_ms = (time.time() - (payload.get("ts") or time.time())) * 1000.0
                tracer.record(
                    "association.service",
                    "discovered",
                    True,
                    max(0.0, latency_ms),
                    {"intent": payload.get("intent"),
                     "discoveries": self._assoc_service.stats()["discoveries"]
                     if self._assoc_service is not None else 0},
                )
            except Exception as e:
                logger.debug("AssociationService tracer record failed: %s", e)

    def _run_association_chain(self, event, text: str, pcr_output=None) -> Optional[dict]:
        """Cold path: L1 resolve → L1.5 qualify → L2.5 belief → L3 validate.

        Pre-enrichment runs *before* discourse cut so chunks are self-contained
        (D-15). Failures are non-fatal (cold path), but the result snapshot is
        always recorded on ``self._last_association`` for white-box inspection.
        """
        started = time.time()
        self._init_association_components()
        enriched = text
        entities: List[str] = []

        # L1: pronoun resolution → enriched text
        if self._pronoun_resolver is not None:
            try:
                resolved = self._pronoun_resolver.resolve(text)
                if resolved:
                    enriched = resolved
                entities = list(self._pronoun_resolver.recent_entities() or [])
            except Exception as e:
                logger.debug("Association L1 resolve failed: %s", e)

        # L1.5: context qualification (dependency injection)
        if self._context_qualifier is not None:
            try:
                qualified = self._context_qualifier.qualify(enriched, entities)
                if qualified:
                    enriched = qualified
            except Exception as e:
                logger.debug("Association L1.5 qualify failed: %s", e)

        # L2.5: belief accumulation from text evidence
        belief_status: dict = {}
        if self._l2_5_belief is not None:
            try:
                from core.agent.association.l2_5_belief import Evidence
                self._l2_5_belief.ingest(Evidence(
                    entity_id="text",
                    entity_name=enriched[:32],
                    relation_type="co_occurrence",
                    confidence=0.5,
                    turn_num=self._turn_counter,
                    source="runtime_cold_path",
                ))
                belief_status = self._l2_5_belief.status()
            except Exception as e:
                logger.debug("Association L2.5 ingest failed: %s", e)

        # L3: multi-perspective intent validation (coarse; PCR zone as prior)
        intent_result = None
        if self._l3_validator is not None:
            try:
                zone = getattr(pcr_output, "zone", None) if pcr_output else None
                b7d = {}
                if belief_status:
                    best_intent = self._l2_5_belief._best_intent()
                    b7d = belief_status.get("belief_7d", {}).get(best_intent, {})
                intent_hyp = getattr(self._last_parse_result, "intent", None)
                intent_hyp_str = (
                    str(getattr(intent_hyp, "category", ""))
                    if intent_hyp is not None else ""
                )
                if not intent_hyp_str:
                    # D-14: PCR zone seeds the L3 hypothesis when the intent
                    # parser has not produced one yet (coarse → fine).
                    intent_hyp_str = self._l3_validator.zone_intent_prior(zone) or "信息查询"
                intent_result = self._l3_validator.validate(
                    intent_hypothesis=intent_hyp_str,
                    belief_7d=b7d or {"stability": 0.5},
                    discourse_topics=self._l3_discourse_topics(),
                    profile_traits=self._l3_profile_traits(),
                    pcr_zone=zone or "MIXED",
                )
            except Exception as e:
                logger.debug("Association L3 validate failed: %s", e)

        self._last_association = {
            "enriched_text": enriched,
            "entities": entities,
            "belief_status": belief_status,
            "intent_result": intent_result,
            "latency_ms": (time.time() - started) * 1000.0,
        }
        logger.info(
            "Association chain (cold path): enriched=%d chars, entities=%d, intent=%s",
            len(enriched), len(entities),
            intent_result.intent if intent_result else "none",
        )
        return self._last_association

    def _l3_discourse_topics(self) -> list:
        """R4 ② channel: recent discourse topics for the L3 discourse vote."""
        try:
            if self._conversation_tracker is not None:
                topics = self._conversation_tracker.recent_topics(5)
                return [str(t) for t in topics] if topics else []
        except Exception as e:
            logger.debug("L3 discourse topics failed: %s", e)
        return []

    def _l3_profile_traits(self) -> dict:
        """P4: OCEAN dims → profile_traits for the L3 profile vote.

        Maps the OCEANProfileAnalyst dims onto the l3_intent contract keys
        (conscientiousness for 诊断/修复 acceptance). Pure mapping; if the
        analyst is absent, returns {} so the profile vote abstains honestly.
        """
        try:
            ocean = getattr(self, "_ocean_analyst", None)
            profile = getattr(ocean, "profile", None)
            if profile is None:
                return {}
            dims = getattr(profile, "dims", {}) or {}
            traits = {}
            if "C" in dims:
                traits["conscientiousness"] = float(dims["C"])
            if "O" in dims:
                traits["openness"] = float(dims["O"])
            if "E" in dims:
                traits["extraversion"] = float(dims["E"])
            if "A" in dims:
                traits["agreeableness"] = float(dims["A"])
            if "N" in dims:
                traits["neuroticism"] = float(dims["N"])
            return traits
        except Exception as e:
            logger.debug("L3 profile traits failed: %s", e)
        return {}

    def _apply_l3_feedback(self, intent_result) -> None:
        """T2 (R1): consume L3 feedback — tree_annotation + profile_update.

        Runs after the LLM reply is produced so a late intent refinement
        never blocks the user-facing response. Writes are best-effort and
        never raise into the hot path.
        """
        if intent_result is None:
            return
        try:
            feedback = getattr(intent_result, "feedback", None) or {}
            tree_annotation = feedback.get("tree_annotation") or {}
            profile_update = feedback.get("profile_update") or {}

            if tree_annotation:
                topic = tree_annotation.get("topic")
                action = tree_annotation.get("action")
                if topic and self._last_association:
                    # R4 ① channel / D9: annotation layer is the fact source.
                    # DiscourseBlockTreeManager has no annotate() yet — the
                    # block-level annotation cache lands with dialogue-tree
                    # Phase 3 (C+B+A assembly). Until then the annotation is
                    # exposed on the white-box snapshot (A19).
                    self._last_association["tree_annotation"] = {
                        "topic": str(topic),
                        "action": str(action or ""),
                    }

            if profile_update:
                last_intent = profile_update.get("last_intent")
                if last_intent and self._last_association:
                    self._last_association["intent_feedback"] = {
                        "last_intent": last_intent,
                        "confidence": profile_update.get("confidence", 0.5),
                    }
        except Exception as e:
            logger.debug("L3 feedback apply failed: %s", e)

    # ---- Profile runtime (R5 ③ cognitive state layer) ----

    def _init_profile_runtime(self) -> None:
        """Lazily instantiate the R5 fact/cognitive layers (never fatal)."""
        if getattr(self, "_profile_runtime_ready", False):
            return
        self._profile_runtime_ready = True
        try:
            from core.agent.v4.cognitive.models import CognitiveProfileV2
            self._cognitive_profile = CognitiveProfileV2()
        except Exception as e:
            logger.debug("Profile V2 unavailable: %s", e)
        try:
            from core.agent.v4.cognitive.convergence import ConvergenceEngine
            if self._cognitive_profile is not None:
                self._convergence_engine = ConvergenceEngine(self._cognitive_profile.track_a)
        except Exception as e:
            logger.debug("Convergence engine unavailable: %s", e)
        # P8: ProfileContextSource — ContextCompiler P 域的统一画像源。
        # 绑定 CognitiveProfileV2（R5 事实/认知层），ContextCompiler / 子图
        # P/F 域从同一源取数（消除"子图直读 OCEAN / API 路径空"的双路径分裂）。
        try:
            from core.agent.compiler.profile_source import ProfileContextSource
            self._profile_source = ProfileContextSource(profile=self._cognitive_profile)
            if getattr(self, "_convergence_engine", None) is not None:
                self._profile_source.set_engine(self._convergence_engine)
        except Exception as e:
            logger.debug("ProfileContextSource unavailable: %s", e)
            self._profile_source = None

    def _feed_profile_runtime(self, text: str, response: str) -> None:
        """R5 ③: update Track A cognitive state from this turn's observation.

        Runs DynamicsComputer.compute_all on lightweight turn observations and
        EMA-merges each dimension through the ConvergenceEngine. Best-effort:
        any failure leaves the previous state intact (cold path).
        """
        self._init_profile_runtime()
        if self._cognitive_profile is None or self._convergence_engine is None:
            return
        try:
            from core.agent.v4.cognitive.dynamics import DynamicsComputer
            from core.agent.v4.cognitive.tag_layer import TagAcquisitionEngine
            obs: dict = {
                "style_scores": [float(len(text) > 40), float(len(response) > 100)],
                "accept": 1 if response else 0,
                "clarify": 0,
                "dispute": 0,
                "commitments_fulfilled": 1 if response else 0,
                "total_commitments": 1,
                "recent_polarities": [0.0],
                "topic_weights": self._l3_discourse_topic_weights(),
                "satisfaction_deltas": [],
                "self_affirmation_count": 0,
                "total_turns": max(1, self._turn_counter),
                "response_speed_sec": 30.0,
                "response_length_chars": len(response),
                "query_complexity": 0.5,
            }
            computed = DynamicsComputer().compute_all(obs)
            for dim, value in computed.items():
                if hasattr(self._cognitive_profile.track_a, dim):
                    self._convergence_engine.update(dim, float(value))
            # Track B: lightweight L1/L2 tag acquisition from this turn.
            try:
                tags, _ = TagAcquisitionEngine().acquire_all(text, response)
                for name, tag in tags.items():
                    existing = self._cognitive_profile.track_b.get(name)
                    if existing is None or tag.confidence > getattr(existing, "confidence", 0):
                        self._cognitive_profile.track_b[name] = tag
            except Exception as e:
                logger.debug("TrackB tags failed: %s", e)
        except Exception as e:
            logger.debug("Profile runtime feed failed: %s", e)

    def cognitive_state(self) -> dict:
        """P5: Track A 认知状态快照 — 供对话树组块边界判据消费。

        KERNEL §八.8.4: 疲劳/注意力/惯性 → 组块合并倾向 / 边界判据。
        Track A 未就绪时返回中性值（诚实降级，不伪造状态）。
        """
        self._init_profile_runtime()
        if self._cognitive_profile is None:
            return {"available": False}
        try:
            a = self._cognitive_profile.track_a
            return {
                "available": True,
                "cognitive_resource": float(getattr(a, "cognitive_resource", 0.5)),
                "attention_anchor": float(getattr(a, "attention_anchor", 0.5)),
                "behavior_inertia": float(getattr(a, "behavior_inertia", 0.5)),
                "cognitive_inertia": float(getattr(a, "cognitive_inertia", 0.5)),
                "emotional_entropy": float(getattr(a, "emotional_entropy", 0.5)),
                "trust_score": float(getattr(a, "trust_score", 0.5)),
                "self_value_score": float(getattr(a, "self_value_score", 0.5)),
                "expectation_deviation": float(getattr(a, "expectation_deviation", 0.5)),
                "observation_count": int(getattr(a, "observation_count", 0)),
            }
        except Exception as e:
            logger.debug("cognitive_state failed: %s", e)
            return {"available": False}

    def _profile_prior_text(self) -> Optional[str]:
        """P6 画像→PCR: OCEAN 维度 → 3D 路由先验文本。

        PCRRouterV2.route(subgraph_prior=...) 用先验文本做 X 轴参照
        （DESIGN_PCR §5 用户偏置层）。这里把 OCEAN 高偏置维度转成
        一段语义先验，让路由对熟悉用户少走"新颖度"误判。
        """
        try:
            ocean = getattr(self, "_ocean_analyst", None)
            profile = getattr(ocean, "profile", None)
            if profile is None:
                return None
            dims = getattr(profile, "dims", {}) or {}
            parts = []
            if dims.get("C", 0.5) > 0.6:
                parts.append("structured and thorough")
            if dims.get("O", 0.5) > 0.6:
                parts.append("exploratory and abstract")
            if dims.get("DK", 0.5) > 0.6:
                parts.append("deep technical domain knowledge")
            if dims.get("NC", 0.5) > 0.6:
                parts.append("prefers analytical depth")
            return " ".join(parts) if parts else None
        except Exception as e:
            logger.debug("profile_prior_text failed: %s", e)
            return None

    def _update_profile_from_pcr(self, pcr_result) -> None:
        """P6 PCR→TrackA: PCR 坐标/认知等级 → Track A 认知状态 EMA。

        公理 P4 双向先验的 PCR→画像侧：把 PCR 的 cognitive_level / zone
        映射为 Track A 的 cognitive_resource / expectation_deviation /
        attention_anchor 观察值，经 ConvergenceEngine 平滑（不自写 EMA）。
        """
        self._init_profile_runtime()
        if self._cognitive_profile is None or self._convergence_engine is None:
            return
        if pcr_result is None:
            return
        try:
            level = getattr(pcr_result, "cognitive_level", "") or ""
            zone = getattr(pcr_result, "zone", "") or "MIXED"
            x = getattr(pcr_result, "x_axis", 0.5)
            y = getattr(pcr_result, "y_axis", 0.5)
            z = getattr(pcr_result, "z_axis", 0.0)

            obs = {
                # 深度任务 → 认知资源消耗更高（低 cognitive_resource）
                "cognitive_resource": 0.35 if zone in ("PRECISION", "ABYSS") else 0.65,
                # 任务复杂度（Y 轴颗粒度）→ 期望偏差
                "expectation_deviation": max(0.0, min(1.0, float(y))),
                # 新颖度（X 轴）→ 注意力锚点偏移
                "attention_anchor": max(0.0, min(1.0, 1.0 - float(x))),
            }
            if level == "expert":
                obs["self_value_score"] = 0.75
            elif level == "beginner":
                obs["self_value_score"] = 0.45
            for dim, value in obs.items():
                if hasattr(self._cognitive_profile.track_a, dim):
                    self._convergence_engine.update(dim, float(value))
        except Exception as e:
            logger.debug("Profile-from-PCR feed failed: %s", e)

    def _feed_inertia_evidence(self, phase_results: dict) -> None:
        """P7: 跨链多视角证据 → inertia_graph（链08 v2 惯性权重图）。

        6 视角映射（P7 拍板：行为链/关联链/对话树/元认知/LLM/工程链）:
          behavior  → behavior 视角（recorded/edge_count）
          meta      → meta 视角（reviewed）
          profile   → profile/llm 视角（OCEAN C 维度 → quality_centric）
          association → association 视角
        只喂已注册 pattern 的 evidence；未注册 pattern 自动 candidate。
        """
        ig = getattr(self, "_inertia_graph", None)
        if ig is None or not phase_results:
            return
        try:
            from core.agent.v4.cognitive.inertia_graph import InertiaPattern
            evidence: dict = {}

            behavior = phase_results.get("behavior") or {}
            if behavior:
                recorded = bool(behavior.get("recorded", False))
                edges = int(behavior.get("edge_count", 0) or 0)
                if recorded:
                    evidence["behavior"] = min(1.0, 0.5 + 0.02 * edges)

            meta = phase_results.get("meta") or {}
            if meta and meta.get("reviewed"):
                evidence["meta"] = 0.7

            profile = phase_results.get("profile") or {}
            if profile:
                evidence["profile"] = 0.6 if profile.get("dims_updated") else 0.4

            association = phase_results.get("association") or {}
            if association and association.get("pronouns_resolved"):
                evidence["association"] = 0.6

            if not evidence:
                return
            ig.feed_evidence("quality_centric", evidence)
            # 白盒可观测（A18）: 记录最近一次喂证据的视角集
            ig._last_feed = {"sources": list(evidence), "ts": time.time()}
        except Exception as e:
            logger.debug("Inertia evidence feed failed: %s", e)

    def _l3_discourse_topic_weights(self) -> dict:
        """Topic weights from conversation tracker for attention_anchor."""
        try:
            if self._conversation_tracker is not None:
                topics = self._conversation_tracker.recent_topics(5)
                if topics:
                    return {str(t): 1.0 for t in topics}
        except Exception:
            pass
        return {}

    # ---- Lifecycle ----

    def on_event_sm(self, event: EventIR, start_phase: str = "pcr") -> Optional[str]:
        """Process event through StateMachine pipeline (new path).

        Kept alongside on_event() for A/B comparison. Config switch:
          engine.use_state_machine = True → on_event delegates to on_event_sm
        Original on_event() is NEVER modified — both paths coexist.
        """
        from core.agent.event.statemachine import PipelinePhase
        sm = getattr(self, '_state_machine', None)

        # B3: ?????? trace_id?thread-local trace_context ?????
        # ?????????? trace?per-turn ?????????
        try:
            from core.agent.event.tracer import set_trace_context
            import uuid as _uuid
            set_trace_context(
                trace_id=_uuid.uuid4().hex[:12],
                session_id=getattr(event, "session_id", None)
                or ((event.refs or {}).get("session_id") if hasattr(event, "refs") else None)
                or "default",
            )
        except Exception:
            pass
        if not sm:
            # M3 修复: 原 fallback 到 self.on_event(event) 会无限递归
            # (on_event → on_event_sm → on_event ...)。无 StateMachine 时
            # 无法走新管线 — 返回 None, 由调用方降级（v3_session_api 有
            # fallback 语义, 不破坏主流程）。
            logger.warning("on_event_sm: no StateMachine, returning None (M3 anti-recursion)")
            return None

        phase_map = {
            "pcr": PipelinePhase.PCR, "intent": PipelinePhase.INTENT,
            "discourse": PipelinePhase.DISCOURSE, "behavior": PipelinePhase.BEHAVIOR,
            "meta": PipelinePhase.META, "profile": PipelinePhase.PROFILE,
            "persist": PipelinePhase.PERSIST,
        }
        phase = phase_map.get(start_phase, PipelinePhase.PCR)

        # ── Coverage gap: ConversationTracker + Granularity (legacy on_event) ──
        _raw = event.payload.get("text", "") if hasattr(event, "payload") else str(event)
        _concepts = self._extract_concepts_from_text(_raw) if _raw else []
        if _raw and getattr(self, '_conversation_tracker', None):
            self._conversation_tracker.add_turn(_raw, concepts=_concepts)
        self._turn_counter += 1
        if getattr(self, '_granularity_regulator', None) and self._discourse_tree:
            _sid = event.payload.get("session_id", "default") if hasattr(event, "payload") else "default"
            _tree = getattr(self._discourse_tree, "_trees", {}).get(_sid) if hasattr(self._discourse_tree, "_trees") else None
            if _tree:
                self._granularity_regulator.regulate(_tree, self._turn_counter)
        # M5-M3: 元认知学习闭环 — 每 5 轮消费 ExecutionTraceV3（审计 M3 修复）
        if self._turn_counter % 5 == 0:
            if self._trace_v3 is None or self._meta_consumer is None:
                self._init_meta_runtime()
            self._run_meta_consume()

        text = event.payload.get("text", "") if hasattr(event, "payload") else str(event)
        # B3: session_id may live on EventIR.refs (DialogAdapter) instead of a
        # top-level attribute — otherwise every session falls into "default".
        _sid = getattr(event, "session_id", None)
        if _sid is None and hasattr(event, "refs"):
            _sid = (event.refs or {}).get("session_id")
        ctx = {
            "text": text,
            "reply": event.payload.get("reply", "") if hasattr(event, "payload") else "",
            "session_id": _sid or "default",
        }
        self._last_session_id = _sid or "default"

        try:
            result = sm.run_pipeline(phase, ctx)
            phases = result.get("phases", [])
            logger.info("on_event_sm: %d phases completed", len(phases))
            # P7: 跨链多视角 evidence → inertia_graph（链08 v2 惯性权重图）
            if hasattr(self, "_feed_inertia_evidence"):
                try:
                    self._feed_inertia_evidence(result.get("results", {}))
                except Exception as e:
                    logger.debug("Inertia feed failed: %s", e)
            # Phase 6: 活跃路径（state machine）→ 定向投递关联链服务。
            # 各阶段产出先写 EventLog（一次），再按 last_seq 增量消费（§7.3）。
            self._route_pipeline_events(result.get("results", {}))
            # B3: v6 state trace (State→Transition→State) + internal
            # simulation loop — migrated from the legacy on_event path that
            # M3 replaced. Records OBSERVE/INFER/REFLECT transitions and
            # self-supervised user simulation so the meta learning loop has
            # real trace data to consume.
            try:
                self._record_state_trace(result.get("results", {}), text)
            except Exception as e:
                logger.debug("State trace failed: %s", e)
            try:
                reply = None
                llm_result = result.get("results", {}).get("llm")
                if isinstance(llm_result, dict):
                    reply = llm_result.get("reply")
                self._run_internal_simulation(text, reply)
            except Exception as e:
                logger.debug("Simulation loop failed: %s", e)
            # X4 收尾: LLM handler 的 {"reply": ...} 是主回复 — 优先返回
            llm_result = result.get("results", {}).get("llm")
            if isinstance(llm_result, dict) and llm_result.get("reply"):
                return llm_result["reply"]
            # 兼容旧 handler: 字符串结果直接返回
            for phase_result in reversed(result.get("results", {}).values()):
                if isinstance(phase_result, str) and len(phase_result) > 10:
                    return phase_result
            return None
        except Exception as e:
            logger.warning("on_event_sm failed: %s, returning None (M3 anti-recursion)", e)
            return None

    def _record_state_trace(self, results: dict, text: str) -> None:
        """B3: record State→Transition→State trace for the meta loop.

        Migrated from the legacy ``on_event`` path (M3 replaced it with the
        StateMachine). Emits OBSERVE / ACTIVATE / INFER / REFLECT transitions
        into ``ExecutionTraceV3`` so ``meta_analyze()`` has real data.
        """
        trace = getattr(self, "_trace_v3", None)
        if trace is None:
            return
        from core.agent.state.state_object import StateObject, TransitionReason, StateDelta

        pre_state = trace.states[-1] if trace.states else None
        if pre_state is None:
            pre_state = trace.snapshot(StateObject(data={
                "turn": self._turn_counter,
                "user_text": text[:200],
            }))

        # OBSERVE: input concepts observed
        concepts = self._extract_concepts_from_text(text) if text else []
        trace.record_transition(
            reason=TransitionReason.OBSERVE,
            from_state=pre_state, to_state=pre_state,
            evidence=[f"Concepts: {concepts[:5] if concepts else []}",
                      f"Text: {text[:60]}"],
            effects=[StateDelta(key="concept_count", operation="set",
                                value=len(concepts))],
            confidence=0.85,
        )

        # ACTIVATE: discourse blocks activated this turn
        sid = getattr(self, "_last_session_id", "default")
        tree = getattr(self, "_discourse_tree", None)
        if tree is not None and hasattr(tree, "_trees"):
            t = tree._trees.get(sid)
            if t is not None and hasattr(t, "blocks"):
                trace.record_transition(
                    reason=TransitionReason.ACTIVATE,
                    from_state=pre_state, to_state=pre_state,
                    evidence=[f"Blocks: {len(t.blocks)}"],
                    effects=[StateDelta(key="tree.block_count", operation="set",
                                        value=len(t.blocks))],
                    confidence=0.75,
                )

        # INFER: LLM reasoning produced a reply
        reply = None
        llm_res = (results or {}).get("llm")
        if isinstance(llm_res, dict):
            reply = llm_res.get("reply")
        if reply:
            post_state = trace.states[-1] if trace.states else StateObject()
            dyn_conf = 0.7
            if len(reply) < 30 and any(
                w in reply.lower() for w in ("unsure", "guessing", "not sure")
            ):
                dyn_conf = 0.35
            elif len(reply) < 50:
                dyn_conf = 0.55
            elif len(reply) > 500:
                dyn_conf = 0.80
            trace.record_transition(
                reason=TransitionReason.INFER,
                from_state=pre_state, to_state=post_state,
                evidence=[f"Answer: {reply[:80]}"],
                effects=[
                    StateDelta(key="turn", operation="inc", value=1),
                    StateDelta(key="response_length", operation="set",
                               value=len(reply)),
                ],
                confidence=dyn_conf,
            )

            # REFLECT: profile updated after this turn
            ta = getattr(getattr(self, "_cognitive_profile", None), "track_a", None)
            if ta is not None:
                trace.record_transition(
                    reason=TransitionReason.REFLECT,
                    from_state=pre_state, to_state=post_state,
                    evidence=[f"Profile inertia={getattr(ta, 'cognitive_inertia', 0):.2f}"],
                    effects=[StateDelta(
                        key="profile.trust", operation="set",
                        value=getattr(ta, "trust_score", 0))],
                    confidence=0.6,
                )

    def _run_internal_simulation(self, text: str, reply) -> None:
        """B3: internal simulation loop (evaluate last prediction, predict next).

        Self-supervised: when the user actually asks a simulated question the
        engine rewards the strategy; otherwise it penalizes and re-simulates.
        """
        sim = getattr(self, "_simulation_engine", None)
        if sim is None:
            return
        try:
            if getattr(self, "_last_simulation", None) is not None and text:
                feedback = sim.evaluate(self._last_simulation, text)
                if feedback.matched:
                    self._simulation_stats["matches"] += 1
                self._simulation_stats["total"] += 1
                sim.learn(feedback)
        except Exception as e:
            logger.debug("Sim evaluation skipped: %s", e)
        try:
            if reply and getattr(self, "_last_simulation", None) is not None:
                user_understanding = ""
                if self._conversation_tracker is not None:
                    topics = self._conversation_tracker.recent_topics(3)
                    user_understanding = "; ".join(topics) if topics else ""
                profile_summary = ""
                if self._cognitive_profile is not None:
                    profile_summary = str(
                        getattr(self._cognitive_profile, "track_b", {}))[:200]
                self._last_simulation = sim.simulate(
                    last_answer=reply,
                    user_understanding=user_understanding,
                    user_profile=profile_summary,
                )
            elif reply and getattr(self, "_last_simulation", None) is None:
                # First turn: seed a prediction without evaluation
                self._last_simulation = sim.simulate(
                    last_answer=reply,
                    user_understanding="",
                    user_profile="",
                )
        except Exception as e:
            logger.debug("Sim generation skipped: %s", e)

    def _publish(self, event_type, payload=None):
        """Fire-and-forget publish. Priority-scheduled with tracing."""
        kind = event_type.value if hasattr(event_type, 'value') else str(event_type)
        payload = payload or {}
        tracer = getattr(self, '_tracer', None)
        start = time.time()
        success = True
        try:
            # Phase 6（蓝图 §7.3）: 关联链 = 独立服务，M→1 定向投递，不广播。
            # 事件先落 EventLog（一次），服务按 last_seq 增量消费、崩溃重放。
            assoc = getattr(self, '_assoc_service', None)
            if assoc is not None:
                try:
                    assoc.enqueue(kind, payload)
                except Exception:
                    pass
            if self._event_bus:
                try:
                    pub = getattr(self._event_bus, "publish_sync", None)
                    if pub is not None:
                        pub(kind, payload)
                    else:
                        self._event_bus.publish(kind, payload)
                except Exception:
                    pass
            subs = getattr(self, '_event_subscribers', {})
            if subs:
                try:
                    from core.agent.event.scheduler import DeciderScheduler, create_scheduled_task
                    sched = getattr(self, '_scheduler', None)
                    if sched is None:
                        sched = DeciderScheduler()
                        self._scheduler = sched
                    for name, sub in subs.items():
                        sched.submit(create_scheduled_task(name, sub.handle, kind, payload))
                    sched.run_batch()
                except Exception:
                    for name, sub in subs.items():
                        try: sub.handle(kind, payload)
                        except: pass
        except Exception:
            success = False
            raise
        finally:
            if tracer:
                latency = (time.time() - start) * 1000
                tracer.record("publish", kind, success, latency)

    def _route_pipeline_events(self, results: dict) -> None:
        """Phase 6: state machine 阶段结果 → 关联链定向投递（M→1，不广播）。

        映射: pcr→pcr_computed / intent→intent_parsed / discourse→discourse_updated
              / behavior→behavior_recorded / meta→meta_reviewed / profile→profile_updated。
        intent 类别变化 = 主题切换粗信号（topic_switched）。
        """
        if not results:
            return
        phase_map = {
            "pcr": ("pcr_computed", lambda r: {
                "zone": r.get("zone", "MIXED"),
                "cognitive_level": r.get("cognitive_level", ""),
                "execution_mode": r.get("execution_mode", ""),
                "x": r.get("x", 0.5), "y": r.get("y", 0.5), "z": r.get("z", 0.0),
            }),
            "intent": ("intent_parsed", lambda r: {
                "category": r.get("category", "general"),
                "confidence": r.get("confidence", 0.5),
            }),
            "discourse": ("discourse_updated", lambda r: {
                "blocks": r.get("blocks", 0),
                "relations": r.get("relations", 0),
            }),
            "behavior": ("behavior_recorded", lambda r: {
                "recorded": r.get("recorded", False),
                "edge_count": r.get("edge_count", 0),
            }),
            "meta": ("meta_reviewed", lambda r: {
                "reviewed": r.get("reviewed", False),
            }),
            "profile": ("profile_updated", lambda r: {
                "dims_updated": r.get("dims_updated", False),
            }),
        }
        for phase_key, (kind, build) in phase_map.items():
            r = results.get(phase_key)
            if r and not r.get("error"):
                self._publish(kind, build(r))
        # 主题切换粗信号: intent 类别变化（topic_switched → 关联链 topic_shift_count+1）
        intent = results.get("intent") or {}
        cat = intent.get("category", "")
        if cat and self._assoc_prev_intent is not None and cat != self._assoc_prev_intent:
            self._publish("topic_switched", {"from": self._assoc_prev_intent, "to": cat})
        if cat:
            self._assoc_prev_intent = cat

    def on_session_end(self) -> None:
        """Trigger checkpoint on session end."""
        if not self._running:
            return
        self._session_active = False

        # P1: behavior brain session-end (decay + reward close + profile).
        if self._behavior_brain is not None:
            try:
                self._behavior_brain.on_checkpoint()
            except Exception as e:
                logger.debug("BehaviorBrain checkpoint failed: %s", e)

        # C1 slow_path: 链长达标时 CausalPlanner.process_chain →
        # CausalSubstrate structural prior 更新（会话结束时触发一次）。
        try:
            self._trigger_causal_slow_path()
        except Exception as e:
            logger.debug("Causal slow path (session end) failed: %s", e)

        # Persist memory points (capacitor model survives across sessions)
        if self._memory_manager is not None and self._profile_store is not None:
            try:
                self._memory_manager.persist(self._profile_store)
                logger.info("Memory points persisted (%d points)",
                           len(self._cognitive_profile.memory_points))
            except Exception as e:
                logger.warning("Memory persist skipped: %s", e)

        logger.info("Session ended, triggering checkpoint")
        self.trigger_checkpoint()

    def _build_parse_context(self):
        try:
            from core.agent.v3_common.models import ParseContext
            ctx = ParseContext()
            if self._last_context:
                ctx.history = list(self._last_context.entries[:10])
            return ctx
        except Exception:
            return None


    def stop(self) -> None:
        """Stop the engine."""
        self._running = False
        self._session_active = False
        # Behavior brain: stop background prediction threads (clean exit).
        if self._behavior_brain is not None:
            try:
                self._behavior_brain.shutdown()
            except Exception as e:
                logger.debug("BehaviorBrain shutdown failed: %s", e)
        # Phase 6: 停止关联链独立服务（消费线程 + 自持 EventLog）
        if self._assoc_service is not None:
            try:
                self._assoc_service.stop()
            except Exception as e:
                logger.debug("AssociationService stop failed: %s", e)

        # B3: stop the EventBus background loop so no consumer thread keeps
        # issuing LLM calls after the engine is stopped (test/API shutdown).
        if self._event_bus is not None:
            try:
                self._event_bus.stop()
            except Exception as e:
                logger.debug("EventBus stop failed: %s", e)

    # ── Semantic World setter 兼容层（cli/main._init_world + compiler 测试使用）──

    def set_observation_pool(self, pool) -> None:
        """Attach the observation pool (Semantic World path)."""
        self._observation_pool = pool

    def set_content_provider(self, provider) -> None:
        """Attach the content provider and rebuild the context assembler."""
        self._content_provider = provider
        try:
            from core.agent.compiler.perspective_planner import PerspectivePlanner
            if self._perspective_planner is None:
                self._perspective_planner = PerspectivePlanner()
        except Exception:
            pass

    def set_object_store(self, objects, ort, provider) -> None:
        """Attach the semantic object store + runtime (Semantic World path)."""
        self._object_store = objects
        self._object_runtime = ort
        self._content_provider = provider

    def _persist_state(self) -> dict:
        """PERSIST phase: 落盘当前状态快照（P10 e2e + handlers 契约）。

        写 EventLog（append-only）+ 存储层统计。失败非致命 — 持久化是
        后台保障，不影响主回复路径。返回 {"persisted": bool, ...}。
        """
        out = {"persisted": False, "event_log": False}
        try:
            if getattr(self, "_event_log", None) is not None:
                try:
                    self._event_log.put_event(
                        event_id=f"persist_{int(time.time() * 1000)}",
                        kind="state.persisted",
                        payload={"turn": self._turn_counter,
                                 "session": getattr(self, "_last_session_id", "default")},
                    )
                    out["event_log"] = True
                except Exception:
                    pass
            storage = getattr(self, "_storage", None)
            if storage is not None:
                try:
                    if hasattr(storage, "save") and callable(storage.save):
                        storage.save()
                    out["persisted"] = True
                except Exception:
                    pass
            if not out["event_log"] and not out["persisted"]:
                # 无持久化组件时仍标记成功（内存态视为已"保存"到运行态）
                out["persisted"] = True
        except Exception:
            pass
        return out

    # ── OS 式分层持久化（TREE_TIERING_DECISION_20260807）────────────
    # Hot=内存 blocks / Warm=discourse_trees/{sid}.json / Cold=v3_sessions 原文

    def _discourse_warm_dir(self) -> str:
        import os as _os
        from pathlib import Path as _Path
        # 默认与 v3_sessions.json 同处（项目 data/，可写 — ~/.dialogmesh 在
        # 本机有 ACL 权限坑: state.json 同款 Errno 13）；env 可覆盖
        base = _os.environ.get("DM_DISCOURSE_DIR") or _os.path.join(
            str(_Path(__file__).resolve().parents[3]),
            "data", "discourse_trees")
        _os.makedirs(base, exist_ok=True)
        return base

    def _persist_discourse_tree(self, session_id: str = "default",
                                force: bool = False) -> bool:
        """Hot→Warm page-out: 序列化 discourse 树到 {sid}.json。

        force=True 绕过 3s debounce（冷重建批量 feed 后强制落盘,
        否则连续 feed <3s 只落第一块 — TREE_TIERING 实测 bug）。
        """
        import json as _json
        import os as _os
        tm = getattr(self, "_discourse_tree", None)
        if tm is None or not tm.blocks:
            return False
        now = time.time()
        if not force and now - getattr(self, "_discourse_last_persist", 0.0) < 3.0:
            return True  # debounce（冷重建批量 feed 只落一次）
        self._discourse_last_persist = now
        try:
            path = _os.path.join(self._discourse_warm_dir(), f"{session_id}.json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(tm.export_blocks(session_id=session_id), f, ensure_ascii=False)
            _os.replace(tmp, path)
            return True
        except Exception as e:
            logger.warning("Discourse persist failed: %s", e)
            return False

    def _load_discourse_tree(self, session_id: str = "default") -> int:
        """Warm→Hot page-in: 读 {sid}.json 换入 blocks。返回块数。"""
        import json as _json
        import os as _os
        tm = getattr(self, "_discourse_tree", None)
        if tm is None:
            return 0
        path = _os.path.join(self._discourse_warm_dir(), f"{session_id}.json")
        if not _os.path.exists(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = _json.load(f)
            return tm.import_blocks(payload)
        except Exception as e:
            logger.warning("Discourse load failed: %s", e)
            return 0

    def _warm_start_discourse(self) -> int:
        """启动预加载: 把当前/默认会话树从 Warm 换入 Hot。"""
        sid = getattr(self, "_last_session_id", None) or "default"
        n = self._load_discourse_tree(sid)
        if n:
            logger.info("Discourse warm start: %s blocks for %s", n, sid[:12])
        return n

    def on_event(self, event):
        """Compatibility wrapper — delegates to on_event_sm."""
        return self.on_event_sm(event, start_phase="pcr")

    @staticmethod
    def _extract_concepts_from_text(text: str):
        """Extract concepts from text for conversation tracking."""
        import re
        if not text:
            return []
        return re.findall(r'[A-Z][a-z]+|[A-Z]{2,}', text)
