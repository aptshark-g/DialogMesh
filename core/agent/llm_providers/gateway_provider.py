"""GatewayLLMProvider — routes LLM calls through Switch Gateway.

Design: DialogMesh → GatewayClient (HTTP) → Switch (Go) → DeepSeek/LMStudio/OpenAI/...

Does NOT import switch code directly. Just HTTP calls.
"""
from __future__ import annotations
import logging, time, json
from typing import Any, Dict, List, Optional

from core.agent.llm_providers.base import LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics

logger = logging.getLogger(__name__)


class GatewayLLMProvider(LLMProvider):
    """LLM provider that routes via Switch Gateway.

    Usage:
        provider = GatewayLLMProvider(
            "gateway",
            base_url="http://localhost:8080",
            default_provider="deepseek",
            default_model="deepseek-v4-flash",
        )
        result = provider.generate(GenerateRequest(prompt="Hello"))
    """

    def __init__(
        self,
        name: str = "gateway",
        config: Dict[str, Any] = None,
    ):
        super().__init__(name, config or {})
        self._base_url = self.config.get("base_url", "http://localhost:8080")
        self._default_provider = self.config.get("default_provider", "deepseek")
        self._default_model = self.config.get("default_model", "")
        self._timeout = self.config.get("timeout", 60.0)
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from httpx import Client
            self._client = Client(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        except ImportError:
            import urllib.request
            self._client = None  # fallback to urllib

    def _post(self, path: str, body: dict, provider: str = None) -> dict:
        self._ensure_client()
        url = path
        if provider:
            url += f"?provider={provider}"

        if self._client:
            resp = self._client.post(url, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Gateway HTTP {resp.status_code}: {resp.text}")
            return resp.json()
        else:
            import urllib.request
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}{url}",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return json.loads(r.read())

    def generate(self, request: GenerateRequest) -> GenerateResult:
        t0 = time.time()
        provider = request.metadata.get("provider", self._default_provider)
        model = request.metadata.get("model", self._default_model)

        # Build OpenAI-compatible messages
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        if request.messages:
            messages.extend(request.messages)
        elif request.prompt:
            messages.append({"role": "user", "content": request.prompt})

        body = {
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if model:
            body["model"] = model

        if request.response_format == "json":
            body["response_format"] = {"type": "json_object"}

        try:
            data = self._post("/v1/chat/completions", body, provider)
            choices = data.get("choices", [])
            text = ""
            if choices:
                text = choices[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            latency = (time.time() - t0) * 1000

            metrics = LLMCallMetrics(
                provider_name=provider,
                latency_ms=latency,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                success=True,
                model_id=model or data.get("model", ""),
            )
            return GenerateResult(text=text, metrics=metrics, raw_response=data)
        except Exception as e:
            latency = (time.time() - t0) * 1000
            logger.warning("Gateway call failed (provider=%s): %s", provider, e)
            metrics = LLMCallMetrics(
                provider_name=provider,
                latency_ms=latency,
                input_tokens=0,
                output_tokens=0,
                success=False,
                model_id=model or "",
                error_type="connection",
            )
            return GenerateResult(
                text=f"[Gateway Error: {e}]",
                metrics=metrics,
                raw_response={"error": str(e)},
            )

    def health_check(self) -> bool:
        try:
            self._ensure_client()
            if self._client:
                resp = self._client.get("/v1/health")
                return resp.status_code == 200
            return False
        except Exception:
            return False

    def estimate_latency_ms(self, prompt_len: int = 0) -> float:
        """Conservative estimate for gateway routing."""
        return 200.0  # gateway overhead + provider latency

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all providers registered in the gateway."""
        try:
            data = self._post("/v1/providers", {})
            return data.get("providers", [])
        except Exception:
            return []
