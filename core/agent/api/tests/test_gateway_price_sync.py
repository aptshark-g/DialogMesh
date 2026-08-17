"""价格目录同步（LiteLLM 源, 2026-08-17）— 纯函数单测, 无网络依赖。

验证:
  1. _catalog_entry_for 匹配策略（精确 key / provider 前缀 / 后缀）。
  2. _enrich_model 单位换算（per-token -> per-1M）+ 上下文/最大输出富化。
  3. _apply_catalog_to_builtins: 已有模型富化 + 空列表 provider 发现新模型（封顶）。
"""

import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from core.agent.api import api_gateway as gw


# LiteLLM catalog 结构的最小夹具（key = 模型名, 含 provider 前缀）
FIXTURE_CATALOG = {
    "deepseek/deepseek-chat": {
        "litellm_provider": "deepseek", "mode": "chat",
        "input_cost_per_token": 0.00000014, "output_cost_per_token": 0.00000028,
        "max_input_tokens": 128000, "max_output_tokens": 8192,
        "supports_function_calling": True,
    },
    "deepseek/deepseek-reasoner": {
        "litellm_provider": "deepseek", "mode": "chat",
        "input_cost_per_token": 0.00000055, "output_cost_per_token": 0.00000219,
        "max_input_tokens": 64000, "max_output_tokens": 8192,
    },
    "openai/gpt-4o": {
        "litellm_provider": "openai", "mode": "chat",
        "input_cost_per_token": 0.0000025, "output_cost_per_token": 0.00001,
        "max_input_tokens": 128000, "max_output_tokens": 16384,
        "supports_function_calling": True,
    },
    "groq/llama-3.3-70b-versatile": {
        "litellm_provider": "groq", "mode": "chat",
        "input_cost_per_token": 0.00000059, "output_cost_per_token": 0.00000079,
        "max_input_tokens": 131072, "max_output_tokens": 32768,
    },
    "moonshot/kimi-k2": {
        "litellm_provider": "moonshot", "mode": "chat",
        "input_cost_per_token": 0.0000004, "output_cost_per_token": 0.000004,
        "max_input_tokens": 128000, "max_output_tokens": 8192,
    },
}


def test_catalog_entry_matching():
    # 精确 key
    assert gw._catalog_entry_for("deepseek/deepseek-chat", "deepseek", FIXTURE_CATALOG)["litellm_provider"] == "deepseek"
    # provider 前缀
    assert gw._catalog_entry_for("deepseek-chat", "deepseek", FIXTURE_CATALOG)["max_input_tokens"] == 128000
    # 后缀匹配
    assert gw._catalog_entry_for("gpt-4o", "openai", FIXTURE_CATALOG)["input_cost_per_token"] == 0.0000025
    # 未命中
    assert gw._catalog_entry_for("nope-model", "deepseek", FIXTURE_CATALOG) is None
    # 空目录/空 id
    assert gw._catalog_entry_for("", "deepseek", FIXTURE_CATALOG) is None
    assert gw._catalog_entry_for("deepseek-chat", "deepseek", {}) is None


def test_enrich_model_units():
    base = {"id": "deepseek-chat", "display": "DeepSeek V3", "context": 0,
            "max_output": 0, "cost_in": 0, "cost_out": 0, "capabilities": ["chat"]}
    entry = FIXTURE_CATALOG["deepseek/deepseek-chat"]
    out = gw._enrich_model(base, entry)
    # per-token -> per-1M
    assert out["cost_in"] == 0.14
    assert out["cost_out"] == 0.28
    assert out["context"] == 128000
    assert out["max_output"] == 8192
    assert "function" in out["capabilities"]
    # 原对象不被污染（capabilities 列表拷贝）
    assert "function" not in base["capabilities"]
    assert base["cost_in"] == 0


def test_apply_catalog_to_builtins():
    # 备份后打补丁: 给 kimi/groq 空 default_models（正常场景即空）
    orig_kimi = gw.BUILTIN_PROVIDERS["kimi"]["default_models"]
    orig_groq = gw.BUILTIN_PROVIDERS["groq"]["default_models"]
    gw.BUILTIN_PROVIDERS["kimi"]["default_models"] = []
    gw.BUILTIN_PROVIDERS["groq"]["default_models"] = []
    try:
        enriched, added = gw._apply_catalog_to_builtins(FIXTURE_CATALOG)
        assert enriched >= 1  # deepseek-chat / deepseek-reasoner / openai gpt-4o 已内置
        assert added >= 2     # kimi-k2 + llama-3.3-70b-versatile 发现
        kimi_ids = [m["id"] for m in gw.BUILTIN_PROVIDERS["kimi"]["default_models"]]
        assert "kimi-k2" in kimi_ids
        k2 = next(m for m in gw.BUILTIN_PROVIDERS["kimi"]["default_models"] if m["id"] == "kimi-k2")
        assert k2["cost_in"] == 0.4 and k2["cost_out"] == 4.0
        # 本地模型不做目录发现
        assert gw.BUILTIN_PROVIDERS["lmstudio"]["default_models"] == []
        # 幂等性: 二次执行不重复添加
        e2, a2 = gw._apply_catalog_to_builtins(FIXTURE_CATALOG)
        assert a2 == 0
        assert len(gw.BUILTIN_PROVIDERS["kimi"]["default_models"]) == 1
    finally:
        gw.BUILTIN_PROVIDERS["kimi"]["default_models"] = orig_kimi
        gw.BUILTIN_PROVIDERS["groq"]["default_models"] = orig_groq


def test_price_cache_stale():
    assert gw._price_cache_stale({}) is True
    old = {"fetched_at": "2020-01-01T00:00:00+00:00"}
    assert gw._price_cache_stale(old) is True
    fresh = {"fetched_at": datetime.utcnow().isoformat() + "Z"}
    assert gw._price_cache_stale(fresh) is False
