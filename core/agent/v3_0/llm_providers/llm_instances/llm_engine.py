# -*- coding: utf-8 -*-
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.agent.v3_0.llm_providers.base import (
    GenerateRequest_v3, GenerateResult_v3, LLMProvider_v3,
)
from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogType, CogNodeStatus

logger = logging.getLogger(__name__)


class LLMEngineResult:
    def __init__(self, output=None, confidence=0.0, success=False, latency_ms=0.0, node_id=None, error=None):
        self.output = output or {}
        self.confidence = confidence
        self.success = success
        self.latency_ms = latency_ms
        self.node_id = node_id
        self.error = error


class LLMEngine(ABC):
    def __init__(self, name: str, provider, cog_type: CogType, prompt_template: str = "",
                 temperature: float = 0.3, max_tokens: int = 512):
        self.name = name
        self.provider = provider
        self.cog_type = cog_type
        self.prompt_template = prompt_template
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def _build_prompt(self, context_data: Dict[str, Any]) -> str:
        ...

    @abstractmethod
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        ...

    async def process(self, context_data: Dict[str, Any], timeout_ms: int = 5000) -> LLMEngineResult:
        start = time.time()
        prompt = self._build_prompt(context_data)
        if not self.provider:
            return LLMEngineResult(output={"fallback": True}, confidence=0.0, success=False, error="no_provider")
        try:
            request = GenerateRequest_v3(prompt=prompt, max_tokens=self.max_tokens, temperature=self.temperature,
                                          timeout_ms=timeout_ms, response_format="json")
            result = await self.provider.generate_async(request)
            latency_ms = (time.time() - start) * 1000.0
            if not result.success:
                return LLMEngineResult(success=False, latency_ms=latency_ms, error=result.text[:200] if result.text else "provider_failure")
            parsed = self._parse_response(result.text)
            confidence = parsed.get("confidence", 0.5) if parsed else 0.5
            return LLMEngineResult(output=parsed, confidence=confidence, success=True, latency_ms=latency_ms)
        except Exception as exc:
            return LLMEngineResult(success=False, latency_ms=(time.time()-start)*1000.0, error=str(exc))

    def build_cog_node(self, parsed_output: Dict[str, Any], confidence: float) -> CognitiveTreeNode:
        return CognitiveTreeNode(
            cog_type=self.cog_type, source_llm=self.name,
            content=json.dumps(parsed_output, ensure_ascii=False)[:500],
            confidence=confidence, evidence=parsed_output.get("evidence", []),
            action=parsed_output.get("action"), status=CogNodeStatus.ACTIVE,
            metadata={"model": getattr(self.provider, "model_name", "unknown")},
        )

    def _try_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r'`(?:json)?\s*\n?(.*?)\n?`', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        bm = re.search(r'\{.*\}', text, re.DOTALL)
        if bm:
            try:
                return json.loads(bm.group(0))
            except json.JSONDecodeError:
                pass
        return None

__all__ = ["LLMEngine", "LLMEngineResult"]
