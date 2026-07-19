"""Switch Gateway Provider — OpenAIProvider wrapper pointing to switch.

DialogMesh no longer connects directly to upstream LLM providers.
All LLM calls go through the switch gateway, which handles:
  - weighted routing across providers
  - circuit breaker + retry + failover
  - response caching + request coalescing
  - rate limiting + cost tracking
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import os, json, logging

logger = logging.getLogger(__name__)

# Default switch gateway address
DEFAULT_SWITCH_URL = os.environ.get("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080")
DEFAULT_SWITCH_KEY = os.environ.get("SWITCH_GATEWAY_KEY", "dm-client")


class SwitchGatewayProvider:
    """Factory that creates an OpenAIProvider pointed at switch gateway.

    Usage:
        from core.agent.llm_providers.switch_provider import SwitchGatewayProvider
        prov = SwitchGatewayProvider.create(
            model="deepseek-chat",
            switch_url="http://127.0.0.1:8080",
            switch_key="dm-client",
        )
        result = prov.generate(request)
    """

    @staticmethod
    def create(
        model: str = "deepseek-chat",
        switch_url: Optional[str] = None,
        switch_key: Optional[str] = None,
        max_retries: int = 1,          # switch handles retries — keep low
        timeout_s: int = 120,           # generous: switch may do failover
        trace_id: Optional[str] = None,
    ):
        """Create an LLMProvider routed through switch gateway."""
        from core.agent.llm_providers.openai_provider import OpenAIProvider

        url = (switch_url or DEFAULT_SWITCH_URL).rstrip("/")
        key = switch_key or DEFAULT_SWITCH_KEY

        config: Dict[str, Any] = {
            "api_key": key,
            "base_url": url,
            "model": model,
            "max_retries": max_retries,
            "timeout_s": timeout_s,
        }
        return OpenAIProvider("switch-gateway", config)

    @staticmethod
    def health() -> bool:
        """Quick check: is switch reachable?"""
        try:
            import urllib.request
            req = urllib.request.Request(f"{DEFAULT_SWITCH_URL}/v1/health")
            req.add_header("Authorization", f"Bearer {DEFAULT_SWITCH_KEY}")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode()) if hasattr(resp, 'read') else {}
                return resp.status == 200
        except Exception:
            return False

    @staticmethod
    def auto_create(model: str = "deepseek-chat", fallback_provider=None):
        """Auto-detect switch. If available → use it. Else → use fallback."""
        if SwitchGatewayProvider.health():
            logger.info("Switch gateway detected — routing through :8080")
            return SwitchGatewayProvider.create(model=model)
        logger.info("Switch gateway not available — using fallback")
        return fallback_provider
