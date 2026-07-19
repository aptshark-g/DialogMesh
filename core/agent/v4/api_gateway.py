"""Gateway API — provider management, model selection, failover config.

Proxies switch gateway for all provider operations.
DialogMesh no longer maintains its own provider config — 
switch's provider.yaml is the single source of truth.

Endpoints:
  GET  /v6/gateway/providers       — proxy switch GET /v1/providers
  PUT  /v6/gateway/providers/{name} — proxy switch PUT /v1/admin/providers
  POST /v6/gateway/providers/{name}/test  — test connection via switch
  POST /v6/gateway/providers/{name}/models — proxy switch model list
  GET  /v6/gateway/config          — proxy switch diagnostics
  PUT  /v6/gateway/config          — proxy switch admin reload
  PUT  /v6/gateway/active          — switch active provider/model
  GET  /v6/gateway/usage           — proxy switch GET /v1/usage
  GET  /v6/gateway/stats           — proxy switch GET /v1/stats
  GET  /v6/gateway/health          — proxy switch GET /v1/health
"""
import json, os, time, logging, urllib.request, urllib.error
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/gateway")

# ---- Switch gateway config ----
SWITCH_URL = os.environ.get("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080")
SWITCH_KEY = os.environ.get("SWITCH_GATEWAY_KEY", "dm-client")

_engine = None

def init(engine):
    global _engine
    _engine = engine


# ---- Helpers ----

def _load_provider_config(name: str) -> dict:
    path = f"{DATA_DIR}/providers/{name}.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def _save_provider_config(name: str, cfg: dict):
    os.makedirs(f"{DATA_DIR}/providers", exist_ok=True)
    with open(f"{DATA_DIR}/providers/{name}.json", "w") as f:
        json.dump(cfg, f, indent=2)

def _load_gateway_config() -> dict:
    path = f"{DATA_DIR}/config.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"active_provider": "deepseek", "active_model": "deepseek-chat",
            "failover_chain": ["deepseek"], "auto_failover": True,
            "max_retries": 2, "timeout_ms": 30000}

def _save_gateway_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/config.json", "w") as f:
        json.dump(cfg, f, indent=2)

def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "●" * (len(key) - 8) + key[-4:]

# ---- Built-in provider definitions ----

BUILTIN_PROVIDERS = {
    "deepseek": {
        "display_name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_models": [
            {"id": "deepseek-chat", "display": "DeepSeek V3", "context": 128000, "max_output": 8192, "cost_in": 0.14, "cost_out": 0.28, "capabilities": ["chat", "reasoning", "code"]},
            {"id": "deepseek-reasoner", "display": "DeepSeek R1", "context": 64000, "max_output": 8192, "cost_in": 0.55, "cost_out": 2.19, "capabilities": ["reasoning", "math"]},
        ],
    },
    "lmstudio": {
        "display_name": "LM Studio (本地)",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "default_models": [],  # fetched dynamically
    },
    "openai": {
        "display_name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_models": [
            {"id": "gpt-4o", "display": "GPT-4o", "context": 128000, "max_output": 16384, "cost_in": 2.50, "cost_out": 10.00, "capabilities": ["chat", "reasoning", "code", "vision"]},
            {"id": "gpt-4o-mini", "display": "GPT-4o Mini", "context": 128000, "max_output": 16384, "cost_in": 0.15, "cost_out": 0.60, "capabilities": ["chat", "code"]},
        ],
    },
}

# ---- Endpoints ----

@router.get("/providers")
async def list_providers():
    """All providers with config status, health, and models."""
    result = []
    active = _load_gateway_config()

    for name, builtin in BUILTIN_PROVIDERS.items():
        saved = _load_provider_config(name)
        configured = bool(saved.get("api_key") or name == "lmstudio")
        base_url = saved.get("base_url") or builtin["default_base_url"]

        # Models: saved cache > builtin defaults
        cache_path = f"{DATA_DIR}/models_cache/{name}.json"
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                models = json.load(f)
        else:
            models = builtin["default_models"]

        # Health check
        healthy = None
        if configured and _engine:
            try:
                from core.agent.llm_providers.openai_provider import OpenAIProvider
                prov = OpenAIProvider(name, {"api_key": saved.get("api_key", "local"),
                                              "base_url": base_url, "model": models[0]["id"] if models else "x"})
                healthy = prov.health_check() if hasattr(prov, 'health_check') else None
            except Exception:
                healthy = False

        result.append({
            "name": name,
            "display_name": builtin["display_name"],
            "configured": configured,
            "healthy": healthy,
            "base_url": base_url,
            "api_key_masked": _mask_key(saved.get("api_key", "")) if saved.get("api_key") else None,
            "models": models,
        })

    return {
        "providers": result,
        "active_provider": active.get("active_provider", "deepseek"),
        "active_model": active.get("active_model", "deepseek-chat"),
    }


class ProviderConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""


@router.put("/providers/{name}")
async def configure_provider(name: str, req: ProviderConfig):
    """Edit provider via switch admin API (soft-config, no restart)."""
    import urllib.request
    body = json.dumps({
        "name": name, "kind": getattr(req, 'kind', 'openai_compatible'),
        "base_url": getattr(req, 'base_url', ''),
        "api_key": getattr(req, 'api_key', ''),
        "models": getattr(req, 'models', []),
        "max_concurrency": getattr(req, 'max_concurrency', 0),
        "rate_limit_rpm": getattr(req, 'rate_limit_rpm', 0),
        "enabled": getattr(req, 'enabled', True),
    }).encode()
    r = urllib.request.Request(f"{SWITCH_URL}/v1/admin/providers/{name}", data=body, method="PUT")
    r.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "fallback": "switch may not be running"}

@router.post("/providers")
async def add_provider(req: ProviderConfig):
    """Add a new provider via switch admin API."""
    if not req.name or not getattr(req, 'base_url', ''):
        raise HTTPException(400, "name and base_url required")
    import urllib.request
    body = json.dumps({
        "name": req.name, "kind": getattr(req, 'kind', 'openai_compatible'),
        "base_url": req.base_url, "api_key": getattr(req, 'api_key', ''),
        "models": getattr(req, 'models', []),
    }).encode()
    r = urllib.request.Request(f"{SWITCH_URL}/v1/admin/providers", data=body, method="POST")
    r.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

@router.delete("/providers/{name}")
async def remove_provider(name: str):
    """Remove a provider via switch admin API."""
    import urllib.request
    r = urllib.request.Request(f"{SWITCH_URL}/v1/admin/providers/{name}", method="DELETE")
    r.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


@router.post("/providers/{name}/test")
async def test_provider(name: str):
    """Test connection to provider."""
    if name not in BUILTIN_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")

    saved = _load_provider_config(name)
    builtin = BUILTIN_PROVIDERS[name]
    api_key = saved.get("api_key", "local")
    base_url = saved.get("base_url") or builtin["default_base_url"]

    try:
        from core.agent.llm_providers.openai_provider import OpenAIProvider
        prov = OpenAIProvider(name, {"api_key": api_key, "base_url": base_url, "model": "x"})
        t0 = time.time()
        healthy = prov.health_check() if hasattr(prov, 'health_check') else None
        latency = int((time.time() - t0) * 1000)
        return {"name": name, "healthy": healthy, "latency_ms": latency, "error": None}
    except Exception as e:
        return {"name": name, "healthy": False, "latency_ms": 0, "error": str(e)[:200]}


@router.post("/providers/{name}/models")
async def fetch_models(name: str):
    """Fetch available models from provider API."""
    if name not in BUILTIN_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {name}")

    saved = _load_provider_config(name)
    builtin = BUILTIN_PROVIDERS[name]
    api_key = saved.get("api_key", "local")
    base_url = saved.get("base_url") or builtin["default_base_url"]

    models = builtin["default_models"]
    try:
        # Try to fetch from API
        import urllib.request, urllib.error
        req = urllib.request.Request(f"{base_url.rstrip('/')}/models")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            fetched = data.get("data", [])
            if fetched and "id" in fetched[0]:
                models = [{"id": m["id"], "display": m["id"], "context": 4096, "max_output": 2048,
                           "cost_in": 0, "cost_out": 0, "capabilities": ["chat"]} for m in fetched[:20]]
                os.makedirs(f"{DATA_DIR}/models_cache", exist_ok=True)
                with open(f"{DATA_DIR}/models_cache/{name}.json", "w") as f:
                    json.dump(models, f, indent=2)
    except Exception:
        pass  # use builtin defaults

    return {"name": name, "models": models}


class ActiveSwitch(BaseModel):
    provider: str
    model: str = ""


@router.put("/active")
async def switch_active(req: ActiveSwitch):
    """Switch active provider and model at runtime."""
    cfg = _load_gateway_config()
    cfg["active_provider"] = req.provider

    # Find model
    if not req.model:
        builtin = BUILTIN_PROVIDERS.get(req.provider, {})
        models = builtin.get("default_models", [])
        req.model = models[0]["id"] if models else "unknown"

    cfg["active_model"] = req.model
    _save_gateway_config(cfg)

    # Apply to engine
    if _engine:
        saved = _load_provider_config(req.provider)
        builtin = BUILTIN_PROVIDERS.get(req.provider, {})
        from core.agent.llm_providers.openai_provider import OpenAIProvider
        new = OpenAIProvider(req.provider, {
            "api_key": saved.get("api_key", "local"),
            "base_url": saved.get("base_url") or builtin.get("default_base_url", ""),
            "model": req.model,
        })
        _engine._llm_provider = new

    return {"active_provider": req.provider, "active_model": req.model, "switched": True}


@router.get("/config")
async def gateway_config():
    """Full gateway configuration."""
    return _load_gateway_config()


class GatewayConfigUpdate(BaseModel):
    failover_chain: list = None
    auto_failover: bool = None
    max_retries: int = None
    timeout_ms: int = None


@router.put("/config")
async def update_gateway_config(req: GatewayConfigUpdate):
    """Update gateway configuration."""
    cfg = _load_gateway_config()
    if req.failover_chain is not None:
        cfg["failover_chain"] = req.failover_chain
    if req.auto_failover is not None:
        cfg["auto_failover"] = req.auto_failover
    if req.max_retries is not None:
        cfg["max_retries"] = req.max_retries
    if req.timeout_ms is not None:
        cfg["timeout_ms"] = req.timeout_ms
    _save_gateway_config(cfg)
    return cfg


@router.get("/usage")
async def gateway_usage():
    """Token usage and cost estimates."""
    d = "data/monitor"
    files = sorted([f for f in os.listdir(d) if f.startswith("chat_") and f.endswith(".jsonl")], reverse=True) if os.path.exists(d) else []
    cur = {"turns": 0, "prompt_tokens": 0, "completion_tokens": 0}
    if files:
        with open(os.path.join(d, files[0])) as f:
            rows = [json.loads(l) for l in f]
        cur["turns"] = len(rows)
        total_chars = sum(r.get("response_len", 0) for r in rows)
        cur["prompt_tokens"] = total_chars * 3
        cur["completion_tokens"] = total_chars // 2

    all_chars = 0
    for cf in files[:50]:
        try:
            with open(os.path.join(d, cf)) as f:
                all_chars += sum(json.loads(l).get("response_len", 0) for l in f)
        except: pass

    cfg = _load_gateway_config()
    return {
        "current_session": {**cur, "provider": cfg.get("active_provider"), "model": cfg.get("active_model")},
        "all_sessions": {"sessions": len(files), "total_tokens": int(all_chars * 3.5)},
        "rates": {"deepseek": "$0.14/M in + $0.28/M out"}
    }

# ── Proxy helpers ──

def _switch_get(path: str) -> dict:
    try:
        req = urllib.request.Request(f"{SWITCH_URL}{path}")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": f"switch unavailable: {e}"}

def _switch_admin(path: str, method: str = "POST", body: dict = None) -> dict:
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{SWITCH_URL}{path}", data=data, method=method)
        req.add_header("Authorization", "Bearer admin-test")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": f"switch unavailable: {e}"}

@router.get("/stats")
async def gateway_stats():
    return _switch_get("/v1/stats")

@router.get("/health")
async def gateway_health():
    return _switch_get("/v1/health")

@router.post("/reload")
async def gateway_reload():
    return _switch_admin("/v1/admin/reload")
