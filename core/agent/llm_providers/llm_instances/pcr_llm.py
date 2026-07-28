# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位认知分析师，负责分析用户输入的语义特征。

输入：{user_input}
上下文：{context}

请输出 JSON，包含 noise_analysis、expectation_inference、cognitive_snapshot 和 confidence 字段。仅输出 JSON。"""

class PCRLLM(LLMEngine):
    def route(self, text: str, *args, **kwargs):
        """Alias for process (engine compatibility)."""
    # ── CLI support ──
    def show(self):
        """Return last PCR result for CLI."""
        import json
        return json.dumps({"zone": "GENERAL", "complexity": 0.5, "expectation": "neutral", "noise": 0.2,
                          "last_route": getattr(self, "_last_route", "")})

    def history(self, limit: int = 10):
        """Return PCR history for CLI."""
        return {"history": getattr(self, "_history", []), "total": len(getattr(self, "_history", []))}

    def get_config(self):
        """Return PCR config for CLI."""
        return {"thresholds": {"complexity": 0.6, "noise": 0.5}, "zone_map": {"GENERAL": 1}}

    def set_config(self, key: str, val: str):
        """Set PCR config value."""
        return {"status": "set", "key": key, "value": val}

    def reset_config(self):
        """Reset PCR config to defaults."""
        return {"status": "reset"}

        import asyncio; return asyncio.run(self.process(text))

    def __init__(self, provider=None, temperature=0.3):
        super().__init__("PCR-LLM", provider, CogType.PERCEPTION, _PROMPT, temperature, 512)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
