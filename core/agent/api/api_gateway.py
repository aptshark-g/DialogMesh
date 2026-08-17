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
import json, os, time, logging, threading, urllib.request, urllib.error
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/gateway")

# ---- Switch gateway config ----
SWITCH_URL = os.environ.get("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080")
SWITCH_KEY = os.environ.get("SWITCH_GATEWAY_KEY", "dm-client")
ADMIN_KEY = os.environ.get("SWITCH_ADMIN_KEY", "admin-test")
DATA_DIR = os.environ.get("DM_GATEWAY_DATA_DIR", os.path.join("data", "gateway"))

_engine = None

def init(engine):
    global _engine
    _engine = engine
    # 2026-08-17: 启动即后台拉取 LiteLLM 价格目录（非阻塞, 失败仅告警回退内置定价）
    try:
        start_price_sync()
    except Exception as e:
        logger.warning("price sync start failed: %s", e)


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
    "anthropic": {
        "display_name": "Anthropic",
        "default_base_url": "https://api.deepseek.com/anthropic",
        "default_models": [],
    },
    "gemini": {
        "display_name": "Google Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_models": [],
    },
    "kimi": {
        "display_name": "Kimi (Moonshot)",
        "default_base_url": "https://api.moonshot.cn/v1",
        "default_models": [],
    },
    "groq": {
        "display_name": "Groq",
        "default_base_url": "https://api.groq.com/openai/v1",
        "default_models": [],
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "default_models": [],
    },
    "ollama": {
        "display_name": "Ollama (本地)",
        "default_base_url": "http://localhost:11434",
        "default_models": [],
    },
}

# ---- Model price sync (LiteLLM catalog, 2026-08-17) ----
# 来源: LiteLLM model_prices_and_context_window.json —— 社区维护、2500+ 模型、
# 每日更新, 是网关成本追踪的事实标准源（参考 ferro-labs/model-catalog 等备选）。
# 设计: 启动后台拉取 + 手动 POST /v6/gateway/sync-prices; 缓存到本地 JSON;
# 网络失败回退缓存/内置定价, 永不阻断启动; 本地已保存的 base_url 覆盖优先。
PRICE_CACHE_PATH = os.path.join(DATA_DIR, "models_prices.json")
PRICE_CACHE_MAX_AGE_H = 24
PRICE_SOURCES = [
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
    "https://cdn.jsdelivr.net/gh/BerriAI/litellm@main/model_prices_and_context_window.json",
]
# litellm_provider -> builtin provider name（含别名）
LITELLM_TO_BUILTIN = {
    "deepseek": "deepseek",
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini", "google": "gemini",
    "moonshot": "kimi",
    "groq": "groq",
    "openrouter": "openrouter",
    "ollama": "ollama",
    "lm_studio": "lmstudio", "lmstudio": "lmstudio",
}
PRICE_ENRICH_CAP = 25  # 每 provider 从目录补充新模型的上限（防模型列表爆炸）

_PRICE_CATALOG: dict = None  # 内存缓存, sync 后刷新


def _load_price_cache() -> dict:
    try:
        if os.path.exists(PRICE_CACHE_PATH):
            with open(PRICE_CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("price cache read failed: %s", e)
    return {}


def _save_price_cache(catalog: dict, fetched_at: str, source: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PRICE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": fetched_at, "source": source,
                   "model_count": len(catalog), "catalog": catalog},
                  f, ensure_ascii=False, indent=1)


def _price_cache_stale(cache: dict) -> bool:
    fetched = cache.get("fetched_at")
    if not fetched:
        return True
    try:
        t = datetime.fromisoformat(fetched)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() > PRICE_CACHE_MAX_AGE_H * 3600
    except Exception:
        return True


def _fetch_price_catalog(timeout: int = 20):
    """Fetch LiteLLM catalog. Returns (catalog_dict, source_url). Raises on total failure."""
    last_err = None
    for url in PRICE_SOURCES:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "DialogMesh/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict) and data:
                return data, url
            last_err = "empty catalog"
        except Exception as e:
            last_err = f"{e}"
    raise RuntimeError(f"price catalog fetch failed: {last_err}")


def _catalog_entry_for(model_id: str, provider: str, catalog: dict):
    """Match a model id against LiteLLM catalog keys.
    优先级: 精确 key > f"{provider}/{model_id}" > 任意 "/{model_id}" 后缀。
    """
    if not catalog or not model_id:
        return None
    if model_id in catalog:
        return catalog[model_id]
    prefixed = f"{provider}/{model_id}"
    if prefixed in catalog:
        return catalog[prefixed]
    for key, entry in catalog.items():
        if key.endswith("/" + model_id):
            return entry
    return None


def _enrich_model(model: dict, entry: dict) -> dict:
    """Apply LiteLLM catalog entry to a model dict (cost 换算为每 1M tokens)。"""
    out = dict(model)
    out["capabilities"] = list(model.get("capabilities") or [])
    if entry.get("input_cost_per_token"):
        out["cost_in"] = round(float(entry["input_cost_per_token"]) * 1e6, 4)
    if entry.get("output_cost_per_token"):
        out["cost_out"] = round(float(entry["output_cost_per_token"]) * 1e6, 4)
    ctx = entry.get("max_input_tokens")
    if ctx:
        out["context"] = int(ctx)
    mout = entry.get("max_output_tokens") or entry.get("max_tokens")
    if mout:
        out["max_output"] = int(mout)
    if entry.get("supports_function_calling") and "function" not in out["capabilities"]:
        out["capabilities"].append("function")
    return out


def _apply_catalog_to_builtins(catalog: dict) -> tuple:
    """富化 BUILTIN_PROVIDERS.default_models（就地, 幂等）:
    1) 已有模型按目录补全定价/上下文; 2) 空列表 provider 从目录发现新模型（封顶）。"""
    enriched = added = 0
    if not catalog:
        return enriched, added
    for provider_name, builtin in BUILTIN_PROVIDERS.items():
        for m in builtin["default_models"]:
            entry = _catalog_entry_for(m["id"], provider_name, catalog)
            if entry:
                m.update(_enrich_model(m, entry))
                enriched += 1
        if builtin["default_models"] or provider_name in ("lmstudio", "ollama"):
            continue
        for key, entry in catalog.items():
            mapped = LITELLM_TO_BUILTIN.get(entry.get("litellm_provider"))
            if mapped != provider_name and not key.startswith(provider_name + "/"):
                continue
            if entry.get("mode") not in (None, "chat"):
                continue
            short = key.split("/", 1)[-1]
            m = {"id": short, "display": short, "context": 0, "max_output": 0,
                 "cost_in": 0, "cost_out": 0, "capabilities": ["chat"]}
            builtin["default_models"].append(_enrich_model(m, entry))
            added += 1
            if len(builtin["default_models"]) >= PRICE_ENRICH_CAP:
                break
    return enriched, added


def sync_model_prices(force: bool = False, timeout: int = 20) -> dict:
    """拉取 LiteLLM 价格目录 → 本地缓存 → 富化内置模型。
    返回摘要; 任何失败不阻断（回退缓存/内置定价）。"""
    global _PRICE_CATALOG
    cache = _load_price_cache()
    catalog, fetched_at, source = None, None, None
    if force or not cache.get("catalog") or _price_cache_stale(cache):
        try:
            catalog, source = _fetch_price_catalog(timeout)
            fetched_at = datetime.now(timezone.utc).isoformat()
            _save_price_cache(catalog, fetched_at, source)
        except Exception as e:
            logger.warning("price sync fetch failed (use cache/builtin): %s", e)
    if catalog is None:
        catalog = cache.get("catalog") or {}
        fetched_at = cache.get("fetched_at")
        source = cache.get("source", "cache")
    _PRICE_CATALOG = catalog
    enriched, added = _apply_catalog_to_builtins(catalog)
    return {
        "synced": bool(catalog),
        "fetched_at": fetched_at,
        "source": source,
        "model_count": len(catalog),
        "enriched_models": enriched,
        "added_models": added,
        "note": "prices per 1M tokens; local overrides preserved",
    }


def _get_catalog() -> dict:
    """内存缓存的目录（惰性从磁盘加载一次, sync 后刷新）。"""
    global _PRICE_CATALOG
    if _PRICE_CATALOG is None:
        _PRICE_CATALOG = _load_price_cache().get("catalog") or {}
    return _PRICE_CATALOG


def _enrich_model_list(models: list, provider: str) -> list:
    catalog = _get_catalog()
    if not catalog:
        return models
    out = []
    for m in models:
        entry = _catalog_entry_for(m.get("id", ""), provider, catalog)
        out.append(_enrich_model(m, entry) if entry else m)
    return out


def start_price_sync():
    """后台（非阻塞）启动时拉取价格目录; 失败仅告警, 不影响启动。"""
    def _run():
        try:
            summary = sync_model_prices()
            logger.info("price sync done: synced=%s models=%s added=%s",
                        summary.get("synced"), summary.get("model_count"),
                        summary.get("added_models"))
        except Exception as e:
            logger.warning("price sync skipped: %s", e)
    threading.Thread(target=_run, daemon=True, name="price-sync").start()


# ---- Endpoints ----

@router.get("/providers")
async def list_providers():
    """All providers with config status, health, and models.

    Switch gateway is the source of truth: key configured via the admin API
    lives in switch memory/state, so the list must reflect switch state.
    Falls back to builtin definitions + local JSON when switch is down.
    """
    active = _load_gateway_config()

    def _adapt(sw: dict) -> dict:
        """Adapt switch /v1/providers item to the GUI contract."""
        name = sw.get("name", "")
        builtin = BUILTIN_PROVIDERS.get(name, {})
        # 2026-08-17: switch 模型列表为纯字符串, 用价格目录富化定价/上下文
        catalog = _get_catalog()
        models = []
        for m in (sw.get("models") or []):
            md = {"id": m, "display": m, "context": 0, "max_output": 0,
                  "cost_in": 0, "cost_out": 0, "capabilities": ["chat"]}
            entry = _catalog_entry_for(m, name, catalog)
            models.append(_enrich_model(md, entry) if entry else md)
        return {
            "name": name,
            "display_name": builtin.get("display_name", name),
            "configured": bool(sw.get("key_configured")) or name in ("lmstudio", "ollama"),
            "healthy": sw.get("healthy"),
            "active": bool(sw.get("active")),
            "circuit_state": sw.get("circuit_state") or None,
            "base_url": builtin.get("default_base_url", ""),
            "api_key_masked": None,  # switch never exposes keys
            "models": models,
        }

    # Preferred path: proxy switch (source of truth for keys/health)
    try:
        req = urllib.request.Request(f"{SWITCH_URL}/v1/providers")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        items = data.get("providers") if isinstance(data, dict) else data
        if items:
            result = [_adapt(sw) for sw in items]
            result.sort(key=lambda p: (not p["active"], p["name"]))
            active_names = [p["name"] for p in result if p.get("active")]
            return {
                "providers": result,
                "active_provider": active_names[0] if active_names else active.get("active_provider", "deepseek"),
                "active_model": active.get("active_model", "deepseek-chat"),
                "source": "switch",
            }
    except Exception as e:
        logger.warning("switch /v1/providers unavailable, fallback to builtin: %s", e)

    # Fallback: builtin definitions + local JSON (switch offline)
    result = []
    for name, builtin in BUILTIN_PROVIDERS.items():
        saved = _load_provider_config(name)
        configured = bool(saved.get("api_key") or name in ("lmstudio", "ollama"))
        base_url = saved.get("base_url") or builtin["default_base_url"]

        # Models: saved cache > builtin defaults
        cache_path = f"{DATA_DIR}/models_cache/{name}.json"
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                models = json.load(f)
        else:
            models = builtin["default_models"]
        models = _enrich_model_list(models, name)

        result.append({
            "name": name,
            "display_name": builtin["display_name"],
            "configured": configured,
            "healthy": None,
            "active": False,
            "circuit_state": None,
            "base_url": base_url,
            "api_key_masked": _mask_key(saved.get("api_key", "")) if saved.get("api_key") else None,
            "models": models,
        })

    return {
        "providers": result,
        "active_provider": active.get("active_provider", "deepseek"),
        "active_model": active.get("active_model", "deepseek-chat"),
        "source": "fallback",
    }


class ProviderConfig(BaseModel):
    name: str = ""
    kind: str = ""                               # openai | openai_compatible | ollama
    api_key: str = ""
    base_url: str = ""
    models: list = []
    max_concurrency: int = 0
    rate_limit_rpm: int = 0
    enabled: bool = True


@router.put("/providers/{name}")
async def configure_provider(name: str, req: ProviderConfig):
    """Edit provider via switch admin API (soft-config, no restart)."""
    import urllib.request
    body = json.dumps({
        "name": name, "kind": req.kind or "openai_compatible",
        "base_url": req.base_url, "api_key": req.api_key,
        "models": req.models,
        "max_concurrency": req.max_concurrency,
        "rate_limit_rpm": req.rate_limit_rpm,
        "enabled": req.enabled,
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
    if not req.name or not req.base_url:
        raise HTTPException(400, "name and base_url required")
    import urllib.request
    body = json.dumps({
        "name": req.name, "kind": req.kind or "openai_compatible",
        "base_url": req.base_url, "api_key": req.api_key,
        "models": req.models,
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
    """Test connection + measure real latency.

    When switch is online → reads provider config + does real HTTP ping.
    When switch is offline → falls back to builtin + OpenAIProvider.health_check.
    """
    # Try switch gateway first
    sw_info = None
    try:
        req = urllib.request.Request(f"{SWITCH_URL}/v1/providers")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        items = data.get("providers") if isinstance(data, dict) else data
        sw_info = next((p for p in (items or []) if p.get("name") == name), None)
    except Exception:
        pass  # switch offline → fallback below

    if sw_info and not sw_info.get("key_configured") and name not in ("lmstudio", "ollama"):
        return {"name": name, "healthy": False, "latency_ms": 0,
                "error": "API Key 未配置"}

    # ═══ Real latency test via HTTP ping ═══
    base_url = (sw_info or {}).get("base_url", "")
    api_key = (sw_info or {}).get("api_key", "")
    if not base_url:
        # Fallback to builtin
        builtin = BUILTIN_PROVIDERS.get(name)
        if not builtin:
            raise HTTPException(404, f"Unknown provider: {name}")
        saved = _load_provider_config(name)
        base_url = saved.get("base_url") or builtin["default_base_url"]
        api_key = saved.get("api_key", "local")

    t0 = time.time()
    try:
        # Ping the provider to measure real latency (no auth needed for reachability)
        # Switch holds the real API key — we test connectivity, switch tests authentication
        req = urllib.request.Request(f"{base_url.rstrip('/')}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
        latency = int((time.time() - t0) * 1000)
        return {"name": name, "healthy": True, "latency_ms": latency, "error": None}
    except urllib.error.HTTPError as e:
        # Got a response (e.g. 401 Unauthorized) — server IS reachable
        latency = int((time.time() - t0) * 1000)
        return {"name": name, "healthy": True, "latency_ms": latency, "error": None}
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return {"name": name, "healthy": False, "latency_ms": latency, "error": str(e)[:200]}


@router.post("/providers/{name}/models")
async def fetch_models(name: str):
    """Fetch available models. Prefer switch's live model list; fallback to
    the provider's own /models API with locally saved key, then builtin."""
    # Switch path: models already known to the gateway
    try:
        req = urllib.request.Request(f"{SWITCH_URL}/v1/providers")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        items = data.get("providers") if isinstance(data, dict) else data
        sw = next((p for p in (items or []) if p.get("name") == name), None)
        if sw and sw.get("models"):
            models = [{"id": m, "display": m, "context": 0, "max_output": 0,
                       "cost_in": 0, "cost_out": 0, "capabilities": ["chat"]}
                      for m in sw["models"]]
            return {"name": name, "models": models}
    except HTTPException:
        raise
    except Exception:
        pass

    builtin = BUILTIN_PROVIDERS.get(name)
    if not builtin:
        raise HTTPException(404, f"Unknown provider: {name}")

    saved = _load_provider_config(name)
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
    """Switch active provider and model at runtime.

    B8-4 (2026-08-04): 全部 LLM 调用走 switch 网关 — 切换只改网关配置，
    不再用 OpenAIProvider 直连替换引擎 provider（旧实现违反 B8-4，
    且切换后引擎绕过网关直连上游）。参考 cc-switch 热切换 UX:
    更新本地 active 配置 + 热通知 switch + 更新网关客户端默认值。
    """
    cfg = _load_gateway_config()
    cfg["active_provider"] = req.provider

    # Find model
    if not req.model:
        builtin = BUILTIN_PROVIDERS.get(req.provider, {})
        models = builtin.get("default_models", [])
        req.model = models[0]["id"] if models else "unknown"

    cfg["active_model"] = req.model
    _save_gateway_config(cfg)

    # 热通知 switch（软配置，不重启）— 尽力而为，switch 离线不阻断
    try:
        import urllib.request
        body = json.dumps({
            "name": req.provider,
            "default_model": req.model,
            "enabled": True,
        }).encode()
        r = urllib.request.Request(
            f"{SWITCH_URL}/v1/admin/providers/{req.provider}",
            data=body, method="PUT")
        r.add_header("Authorization", f"Bearer {ADMIN_KEY}")
        r.add_header("Content-Type", "application/json")
        urllib.request.urlopen(r, timeout=5)
    except Exception as e:
        logger.warning("switch hot-switch failed (config saved locally): %s", e)

    # 更新引擎网关客户端默认值（不替换实例 — 仍是 GatewayLLMProvider）
    if _engine:
        prov = getattr(_engine, "_llm_provider", None)
        if prov is not None and hasattr(prov, "_default_provider"):
            prov._default_provider = req.provider
            if req.model:
                prov._default_model = req.model
            logger.info("Engine gateway client hot-switched → %s/%s",
                        req.provider, req.model)

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
    # 2026-08-17: 费率从内置/富化定价动态取, 不再硬编码
    ds_models = BUILTIN_PROVIDERS.get("deepseek", {}).get("default_models", [])
    if ds_models and ds_models[0].get("cost_in"):
        rates = {f"{ds_models[0]['id']}": f"${ds_models[0]['cost_in']}/M in + ${ds_models[0]['cost_out']}/M out"}
    else:
        rates = {"deepseek": "$0.14/M in + $0.28/M out"}
    return {
        "current_session": {**cur, "provider": cfg.get("active_provider"), "model": cfg.get("active_model")},
        "all_sessions": {"sessions": len(files), "total_tokens": int(all_chars * 3.5)},
        "rates": rates,
    }


@router.get("/cost")
async def gateway_cost():
    """网关计费（2026-08-13 接线）: 转发 switch /v1/usage 的 cost 数据 —
    total（token/请求/费用）+ by_key + by_model（精细化分摊）。"""
    return _switch_get("/v1/usage")


@router.get("/prices")
async def gateway_prices():
    """价格目录同步状态（2026-08-17）: 供前端展示最近同步时间/覆盖模型数。"""
    cache = _load_price_cache()
    return {
        "synced": bool(cache.get("catalog")),
        "fetched_at": cache.get("fetched_at"),
        "source": cache.get("source"),
        "model_count": cache.get("model_count", len(cache.get("catalog") or {})),
        "stale": _price_cache_stale(cache),
    }


@router.post("/sync-prices")
async def gateway_sync_prices(force: bool = True):
    """手动触发价格同步（默认强制拉新）: 更新价格/上下文并富化内置模型。"""
    try:
        return sync_model_prices(force=force)
    except Exception as e:
        raise HTTPException(502, f"price sync failed: {e}")


@router.get("/error-catalog")
async def gateway_error_catalog():
    """错误目录（2026-08-13）: 转发 switch /v1/error-catalog（YAML 文本）。"""
    return _switch_get_text("/v1/error-catalog")

# ── Proxy helpers ──

def _switch_get(path: str) -> dict:
    try:
        req = urllib.request.Request(f"{SWITCH_URL}{path}")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": f"switch unavailable: {e}"}


def _switch_get_text(path: str) -> str:
    """文本透传（2026-08-13）: error-catalog 是 YAML 文本, 不走 JSON。"""
    try:
        req = urllib.request.Request(f"{SWITCH_URL}{path}")
        req.add_header("Authorization", f"Bearer {SWITCH_KEY}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"# switch unavailable: {e}"

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
