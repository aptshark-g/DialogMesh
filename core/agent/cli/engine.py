"""DialogMesh CLI — engine entry point and state management."""
from __future__ import annotations

import json
import os
import sys
import time
import atexit
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("dm")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
STATE_FILE = Path.home() / ".dialogmesh" / "state.json"

_engine = None
_ENGINE_SENTINEL = object()  # recursion breaker for get_engine()
_provider = None
_state: Dict[str, Any] = {}


def _ensure_state_dir():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    _ensure_state_dir()
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"current_session": None, "provider": "deepseek", "key": ""}


def _save_state():
    _ensure_state_dir()
    STATE_FILE.write_text(json.dumps(_state, indent=2, ensure_ascii=False), encoding="utf-8")


_state = _load_state()


def get_engine():
    global _engine
    if _engine is None or not getattr(_engine, '_running', False):
        # Avoid recursion — set _engine to a sentinel first
        _engine = _ENGINE_SENTINEL
        try:
            from core.agent.cli.engine import start_engine as _start
            _start()
        except Exception:
            _engine = None
            raise
    if _engine is _ENGINE_SENTINEL or _engine is None:
        return None
    return _engine


def get_pool_engine():
    """Get an engine from the EnginePool (multi-worker safe). Falls back to singleton."""
    try:
        from core.agent.cli.pool import get_engine as pooled_get_engine
        eng = pooled_get_engine()
        if eng is not None:
            return eng
    except Exception:
        pass
    return get_engine()


def get_provider():
    return _provider


def _create_engine_instance(provider_config=None) -> CognitiveRuntimeEngine:
    """Create engine with registry-primary DI.

    SubsystemRegistry resolves all 37 subsystems in topological order.
    Required subsystems (8) block startup if they fail.
    Optional subsystems (29) log warning but don't block.
    """
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    engine = CognitiveRuntimeEngine()

    # ── Lazy imports for non-registry components ──
    try:
        from core.agent.event.storage import StorageLayer
        from core.agent.api.api_event_log import EventLog
        from core.agent.event.tracer import PipelineTracer
        from core.agent.event.statemachine import DeciderStateMachine
    except ImportError as e:
        raise RuntimeError(f"Core import failed: {e}")

    # ── Phase 1: Create engine + required foundation ──
    engine._running = True
    engine._session_active = True

    # ── Phase 2: Required subsystems via registry (NO try/except pass) ──
    try:
        from core.agent.cli.subsystem_registrations import _registry
    except ImportError as e:
        raise RuntimeError(f"Registry import failed: {e}")

    # Provide provider for DI (before resolve_all — needed by meta_cognition etc.)
    try:
        from core.agent.llm_providers.mock_provider import MockProvider
        engine._llm_provider = engine._provider = MockProvider("mock", {})
        _registry._instances["llm_provider"] = engine._llm_provider
    except Exception:
        engine._llm_provider = None

    try:
        loaded, results = _registry.resolve_all()
        engine._registry = _registry
    except RuntimeError:
        raise  # Required subsystem failed — do not start
    except Exception as e:
        raise RuntimeError(f"Registry resolve failed: {e}")

    # ── Phase 3: Attach all resolved subsystems to engine ──
    _name_map = {"behavior_graph": "_behavior_graph_adapter",
                 "cascade_detector": "_cascade"}
    attached = 0
    failed = 0
    for result in results:
        if result.loaded and result.instance is not None:
            attr_name = _name_map.get(result.name, f"_{result.name}")
            setattr(engine, attr_name, result.instance)
            attached += 1
        else:
            failed += 1
            if result.error:
                import logging
                logging.getLogger("dm.engine").warning(
                    "Subsystem %s: %s", result.name, result.error)

    # ── Phase 4: Non-registry objects (LLM provider, sessions) ──
    # Provider was set before resolve_all (see Phase 2) — keep it
    engine._provider_type = provider_config.get("type", "mock") if provider_config else "mock"

    # ── Phase 5: Register StateMachine handlers (REQUIRED — pipeline execution) ──
    try:
        from core.agent.event.handlers import register_all_handlers
        _ = register_all_handlers(engine, tracer=getattr(engine, '_tracer', None))
    except Exception as e:
        import logging
        logging.getLogger("dm.engine").error("Handler registration failed: %s", e)
        raise RuntimeError(f"Handler registration failed: {e}")

    # ── Phase 1+2 backward-compat wiring ──
    for name, cls_path in [
        ("_chunk_store", "core.agent.storage.chunk_store:ChunkStore"),
        ("_semantic_splitter", "core.agent.storage.semantic_splitter:SemanticSplitter"),
        ("_context_window", "core.agent.storage.context_window:ContextWindow"),
        ("_write_gate", "core.agent.storage.context_window:WriteGate"),
        ("_pronoun_resolver", "core.agent.association.pronoun_resolver:StanzaCorefResolver"),
        ("_context_qualifier", "core.agent.association.context_qualifier:ContextQualifier"),
        ("_semantic_coref", "core.agent.association.semantic_coref:SemanticCorefScorer"),
        ("_hybrid_coref", "core.agent.association.hybrid_coref:HybridCorefResolver"),
        ("_entity_extractor", "core.agent.association.entity_extractor:EntityExtractor"),
    ]:
        try:
            mod_path, cls_name = cls_path.split(":")
            mod = __import__(mod_path, fromlist=[cls_name])
            setattr(engine, name, getattr(mod, cls_name)())
        except Exception:
            pass

    return engine

def start_engine(provider_type: str = None, api_key: str = None,
                 base_url: str = None, model: str = None):
    global _engine, _provider

    if _engine is not None and getattr(_engine, '_running', False):
        return {"status": "already_running"}

    provider_type = provider_type or _state.get("provider", "deepseek")
    api_key = api_key or _state.get("key") or os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = base_url or os.environ.get("DM_LLM_BASE", "")
    model = model or _state.get("model", "deepseek-chat")

    # ── LLM Provider ──
    try:
        if provider_type == "deepseek":
            from core.agent.llm_providers.openai_provider import OpenAIProvider
            _provider = OpenAIProvider("deepseek", {
                "api_key": api_key,
                "base_url": base_url or "https://api.deepseek.com/v1",
                "model": model,
            })
        elif provider_type == "gateway":
            from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
            _provider = GatewayLLMProvider(base_url=base_url or "http://127.0.0.1:8080")
        elif provider_type == "mock":
            from core.agent.llm_providers.mock_provider import MockProvider
            _provider = MockProvider("mock", {})
        else:
            return {"status": "error", "error": f"Unknown provider: {provider_type}"}
    except Exception as e:
        return {"status": "error", "error": f"Provider: {e}"}

    # ── Engine + Registry ──
    try:
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        _engine = CognitiveRuntimeEngine(llm_provider=_provider)

        from core.agent.cli.registry import build_dialogmesh_registry
        registry = build_dialogmesh_registry(_engine)
        t0 = time.time()
        loaded, all_results = registry.resolve_all()
        elapsed = (time.time() - t0) * 1000

        # Map loaded subsystems to engine
        _engine._registry = registry
        for name, instance in loaded.items():
            setattr(_engine, f"_{name}", instance)

        # Ensure EventLog is created with correct path (registry may set wrong path)
        from core.agent.api.api_event_log import EventLog
        import os as _os
        _db = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))), "data", "event_log.db")
        old = getattr(_engine, '_event_log', None)
        if old and hasattr(old, 'close'):
            try: old.close()
            except: pass
        _engine._event_log = EventLog(db_path=_db)
        _engine._event_log.open()

        _engine._running = True
        _engine._session_active = True

        # Phase 3+4: Wire storage + tracer
        try:
            from core.agent.event.storage import StorageLayer
            if getattr(_engine, '_storage', None) is None:
                _engine._storage = StorageLayer()
        except: pass
        try:
            from core.agent.event.tracer import PipelineTracer
            if getattr(_engine, '_tracer', None) is None:
                _engine._tracer = PipelineTracer()
        except: pass

        # Gap closure: RateGuard + CapabilityGuard + HotReloader
        try:
            from core.agent.event.closure import RateGuard, CapabilityGuard, HotReloader, CascadeDetector
            _engine._rate_guard = RateGuard()
            _engine._cascade = CascadeDetector(_engine._rate_guard)
            _engine._capability_guard = CapabilityGuard()
            _engine._cap_guard = _engine._capability_guard  # legacy alias for tests
            _engine._hot_reloader = HotReloader()
        except: pass

        # Week 2: NATS hybrid bus (graceful fallback to memory)
        try:
            from core.agent.event.nats_bridge import wire_hybrid_bus
            nats_ok = wire_hybrid_bus(_engine)
            logger.info("NATS hybrid bus: %s", "active" if nats_ok else "memory fallback")
        except: pass

        # P2: State Machine Engine
        try:
            from core.agent.event.statemachine import DeciderStateMachine, PipelinePhase
            from core.agent.event.handlers import register_all_handlers
            _engine._state_machine = DeciderStateMachine()
            _ = register_all_handlers(_engine, tracer=getattr(_engine, '_tracer', None))
        except: pass

        # Knowledge Graph
        try:
            from core.agent.knowledge.rag_bridge import RAGBridge
            _engine._rag_bridge = RAGBridge()
        except: pass
        try:
            from core.agent.knowledge.frame_source import FrameLibrary
            _engine._frame_library = FrameLibrary()
            _engine._frame_library.load_default()
        except: pass

        # BehaviorGraph adapter
        try:
            from core.agent.behavior.adapter import BehaviorGraphAdapter
            _engine._behavior_graph_adapter = BehaviorGraphAdapter(
                graph_path="data/behavior_graph.json", auto_save=True)
        except: pass
        # ToolRegistry
        try:
            from core.agent.tools.registry import ToolRegistry
            import core.agent.tools.builtin
            _engine._tool_registry = ToolRegistry()
        except: pass

        # Learning Ingestion (DESIGN_LEARNING_INGESTION)
        try:
            from core.agent.learning.sources import ArxivSource, DuckDuckGoSource, ScholarSource
            from core.agent.learning.content_fetcher import ContentFetcher
            from core.agent.learning.credibility import CredibilityEvaluator
            _engine._learning_sources = [ArxivSource(), DuckDuckGoSource(), ScholarSource()]
            _engine._content_fetcher = ContentFetcher()
            _engine._credibility_eval = CredibilityEvaluator()
        except: pass

        # Deep engine objects (DESIGN_RUNTIME_KERNEL §3 — normally in engine.start())
        try:
            from core.agent.v4.cognitive.ocean_profile import OCEANProfileAnalyst
            _engine._ocean_analyst = OCEANProfileAnalyst(_provider)
        except: pass
        try:
            from core.agent.v4.cognitive.metacognition import MetaCognition
            _engine._meta_cognition = MetaCognition(llm_provider=_provider, vcs=None)
        except: pass
        try:
            from core.agent.v4.cognitive.inertia_graph import InertiaWeightGraph
            _engine._inertia_graph = InertiaWeightGraph()
        except: pass
        try:
            from core.agent.v4.cognitive.behavior_discovery import BehaviorDiscovery
            _engine._behavior_discovery = BehaviorDiscovery()
        except: pass
        try:
            from core.agent.engineering.knowledge_graph import KnowledgeGraph
            _engine._engineering_knowledge = KnowledgeGraph()
        except: pass
        try:
            from core.agent.v4.cognitive.abc_orchestrator import ABCOrchestrator
            _engine._abc = ABCOrchestrator(llm_provider=_provider, enable_b=True, enable_c=True)
        except: pass
        try:
            from core.agent.v4.cognitive.mind import Mind
            _engine._mind = Mind(persist_dir="data")
        except: pass

        # Wire cross-deps
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
                    except Exception:
                        pass
        if "meta_cognition" in loaded:
            mc = loaded["meta_cognition"]
            if hasattr(mc, '_vcs') and hasattr(_engine, '_vcs'):
                mc._vcs = getattr(_engine, '_vcs', None)

        _state["provider"] = provider_type
        _state["key"] = api_key
        _state["model"] = model
        _save_state()

        failed = {r.name: r.error for r in all_results if not r.loaded}
        return {
            "status": "running",
            "provider": provider_type,
            "model": model,
            "subsystems_loaded": len(loaded),
            "subsystems_total": len(all_results),
            "startup_ms": round(elapsed, 1),
            "failed": failed,
        }
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        _engine = _provider = None
        import traceback
        return {"status": "error", "error": str(e),
                "trace": traceback.format_exc()[-300:]}


def stop_engine():
    global _engine, _provider
    _engine = None
    _provider = None
    return {"status": "stopped"}


def engine_status():
    if _engine is None or not getattr(_engine, '_running', False):
        return {"running": False}
    reg = getattr(_engine, '_registry', None)
    return {
        "running": True,
        "provider": _state.get("provider", "?"),
        "model": _state.get("model", "?"),
        "session": _state.get("current_session"),
        "subsystems": reg.status() if reg else {},
    }


def get_chain_status():
    if _engine is None:
        return {}
    reg = getattr(_engine, '_registry', None)
    if reg:
        return reg.status()
    return {}


def get_session(sid: str = None) -> str:
    sid = sid or _state.get("current_session")
    if not sid:
        import uuid
        sid = str(uuid.uuid4())[:12]
        _state["current_session"] = sid
        _save_state()
    return sid


def set_session(sid: str):
    _state["current_session"] = sid
    _save_state()
    return {"session_id": sid}


atexit.register(_save_state)
