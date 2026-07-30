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
        # Auto-start with saved config
        result = start_engine()
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


def _create_engine_instance(provider_type: str = None):
    """Create a fresh engine without global singleton. Used by EnginePool."""
    pt = provider_type or _state.get("provider", "deepseek")
    try:
        if pt == "deepseek":
            from core.agent.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider("deepseek", {
                "api_key": _state.get("key") or os.environ.get("DEEPSEEK_API_KEY", ""),
                "base_url": os.environ.get("DM_LLM_BASE", "") or "https://api.deepseek.com/v1",
                "model": _state.get("model", "deepseek-chat"),
            })
        else:
            from core.agent.llm_providers.mock_provider import MockProvider
            provider = MockProvider("mock", {})
    except Exception:
        from core.agent.llm_providers.mock_provider import MockProvider
        provider = MockProvider("mock", {})
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    engine = CognitiveRuntimeEngine(llm_provider=provider)
    # Wire components (per-engine isolation)
    try:
        from core.agent.event.storage import StorageLayer
        engine._storage = StorageLayer()
    except: pass
    try:
        from core.agent.event.tracer import PipelineTracer
        engine._tracer = PipelineTracer()
    except: pass
    try:
        from core.agent.event.nats_bridge import wire_hybrid_bus
        wire_hybrid_bus(engine)
    except: pass
    # Week 4: Redis + OTel
    try:
        from core.agent.event.redis_otel import wire_redis_otel
        wire_redis_otel(engine)
    except: pass
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
            _engine._cap_guard = CapabilityGuard()
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
