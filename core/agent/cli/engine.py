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
    return {"current_session": None, "provider": "gateway", "key": ""}


def _save_state():
    """Persist CLI state. Defensive: never crash at exit on FS/permission issues."""
    try:
        _ensure_state_dir()
        STATE_FILE.write_text(json.dumps(_state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("State save failed (non-fatal): %s", e)


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
    """Create engine via unified bootstrap (B1).

    Delegates to ``engine.bootstrap()`` with the default subsystem registry
    so CLI, tests and API share the exact same cold-start assembly path.
    Required subsystems that fail raise RuntimeError (do not start).
    """
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    engine = CognitiveRuntimeEngine()

    # Default provider for DI (mock unless the caller already configured one)
    try:
        from core.agent.llm_providers.mock_provider import MockProvider
        if getattr(engine, "_llm_provider", None) is None:
            engine._llm_provider = engine._provider = MockProvider("mock", {})
    except Exception:
        engine._llm_provider = None

    try:
        from core.agent.cli.subsystem_registrations import _registry
    except ImportError as e:
        raise RuntimeError(f"Registry import failed: {e}")

    result = engine.bootstrap(registry=_registry, provider_config=provider_config)
    if result.get("status") != "running":
        raise RuntimeError(f"Bootstrap failed: {result.get('error', 'unknown')}")
    return engine
def start_engine(provider_type: str = None, api_key: str = None,
                 base_url: str = None, model: str = None):
    global _engine, _provider

    if _engine is not None and getattr(_engine, '_running', False):
        return {"status": "already_running"}

    # B8-4 (2026-08-04): 主路径归一 — 默认走 switch 网关；
    # switch 离线时降级到直连（有 key）或 mock（无 key，结构模式）
    provider_type = provider_type or _state.get("provider", "gateway")
    api_key = api_key or _state.get("key") or os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = base_url or os.environ.get("DM_LLM_BASE", "")
    model = model or _state.get("model", "deepseek-chat")

    # ── LLM Provider ──
    try:
        if provider_type == "gateway":
            from core.agent.llm_providers.gateway_provider import GatewayLLMProvider
            switch_url = base_url or os.environ.get("SWITCH_GATEWAY_URL",
                                                     "http://127.0.0.1:8080")
            gw = GatewayLLMProvider(base_url=switch_url)
            if gw.health_check():
                _provider = gw
            else:
                # 降级: switch 离线 → 直连 DeepSeek / mock
                logger.warning("Switch gateway unreachable (%s) — "
                               "falling back to direct provider", switch_url)
                if api_key:
                    from core.agent.llm_providers.openai_provider import OpenAIProvider
                    _provider = OpenAIProvider("deepseek", {
                        "api_key": api_key,
                        "base_url": "https://api.deepseek.com/v1",
                        "model": model,
                    })
                else:
                    from core.agent.llm_providers.mock_provider import MockProvider
                    _provider = MockProvider("mock", {})
        elif provider_type == "deepseek":
            from core.agent.llm_providers.openai_provider import OpenAIProvider
            _provider = OpenAIProvider("deepseek", {
                "api_key": api_key,
                "base_url": base_url or "https://api.deepseek.com/v1",
                "model": model,
            })
        elif provider_type == "mock":
            from core.agent.llm_providers.mock_provider import MockProvider
            _provider = MockProvider("mock", {})
        else:
            return {"status": "error", "error": f"Unknown provider: {provider_type}"}
    except Exception as e:
        return {"status": "error", "error": f"Provider: {e}"}

    # ── Engine + Registry (B1: unified bootstrap) ──
    try:
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        _engine = CognitiveRuntimeEngine(llm_provider=_provider)

        from core.agent.cli.registry import build_dialogmesh_registry
        registry = build_dialogmesh_registry(_engine)

        result = _engine.bootstrap(
            registry=registry,
            provider_config={"type": provider_type, "model": model},
        )
        if result.get("status") != "running":
            raise RuntimeError(result.get("error", "bootstrap failed"))

        _state["provider"] = provider_type
        _state["key"] = api_key
        _state["model"] = model
        _save_state()
        return result
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
