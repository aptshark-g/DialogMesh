"""GatewayLLMProvider — routes LLM calls through Switch Gateway.

Design: DialogMesh → GatewayClient (HTTP) → Switch (Go) → DeepSeek/LMStudio/OpenAI/...

Does NOT import switch code directly. Just HTTP calls.

B8-4 (2026-08-04): 主路径归一 — switch 网关为唯一内核，本 Provider 是
DialogMesh 侧唯一网关客户端。鉴权用 switch 的 DialogMesh Key（默认 dm-client，
可经 SWITCH_GATEWAY_KEY 覆盖），与 BINDING_DIALOGMESH v1.0 一致。
"""
from __future__ import annotations
import logging, time, json
import os
from typing import Any, Dict, List, Optional

from core.agent.llm_providers.base import LLMProvider, GenerateRequest, GenerateResult, LLMCallMetrics

logger = logging.getLogger(__name__)


class GatewayCallError(RuntimeError):
    """网关错误（2026-08-13）: 携带稳定 code（error_catalog.yaml 查表用）。

    code 来自网关响应（AUTH_FAILED/RATE_LIMITED/UPSTREAM_TIMEOUT/...）,
    客户端按 code 决策（重试/展示）, 不再文本匹配。
    """

    def __init__(self, status: int, code: str, message: str, body: dict):
        super().__init__(f"Gateway HTTP {status} [{code}]: {message}")
        self.status = status
        self.code = code or "UNKNOWN_ERROR"
        self.message = message
        self.body = body or {}

    @classmethod
    def from_response(cls, status: int, text: str) -> "GatewayCallError":
        body = {}
        try:
            body = json.loads(text or "{}")
        except Exception:
            pass
        return cls(status, body.get("code", ""),
                   body.get("error") or text[:200], body)


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
        **kwargs,
    ):
        # B8-4 兼容: 允许 GatewayLLMProvider(base_url=..., default_provider=...)
        # 直传关键字（历史调用方式），合并进 config。
        merged = dict(config or {})
        for k, v in kwargs.items():
            if v is not None:
                merged[k] = v
        super().__init__(name, merged)
        self._base_url = self.config.get("base_url", "http://localhost:8080")
        self._default_provider = self.config.get("default_provider", "deepseek")
        # B3: 空 model 会让 switch 返回 400（"you passed ."）并计入熔断失败。
        # 给一个非空默认，避免"碰巧网关默认模型兜底"的不稳定。
        self._default_model = self.config.get(
            "default_model",
            os.environ.get("DM_LLM_MODEL", "deepseek-v4-flash"),
        )
        self._timeout = self.config.get("timeout", 60.0)
        self._api_key = self.config.get("api_key") or os.environ.get(
            "SWITCH_GATEWAY_KEY", "dm-client")
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from httpx import Client
            self._client = Client(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except ImportError:
            self._client = None  # fallback to urllib

    def _post(self, path: str, body: dict, provider: str = None,
              timeout: float = None) -> dict:
        self._ensure_client()
        url = path
        if provider:
            url += f"?provider={provider}"
        # 2026-08-13: 请求级超时透传（调用方可指定更长/更短超时）
        eff_timeout = timeout if timeout is not None else self._timeout

        if self._client:
            resp = self._client.post(url, json=body, timeout=eff_timeout)
            if resp.status_code != 200:
                raise GatewayCallError.from_response(
                    resp.status_code, resp.text)
            return resp.json()
        else:
            import urllib.request
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}{url}",
                data=data,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self._api_key}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=eff_timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise GatewayCallError.from_response(
                    e.code, e.read().decode("utf-8", errors="replace"))

    def _get(self, path: str) -> dict:
        """Simple GET helper (health/providers) with httpx → urllib fallback."""
        self._ensure_client()
        if self._client:
            resp = self._client.get(path)
            if resp.status_code != 200:
                raise RuntimeError(f"Gateway HTTP {resp.status_code}: {resp.text}")
            return resp.json()
        import urllib.request
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            headers={"Authorization": f"Bearer {self._api_key}"},
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
            # Thinking models (deepseek-v4-flash etc.) burn tokens on
            # reasoning before content; a small max_tokens truncates with
            # finish_reason=length and an empty content. 决策：不截断 —
            # 长度由 prompt 软约束控制（调用方提示词写明期望长度），
            # max_tokens 只当防失控保险丝（4096 实测 thinking 余量充足）。
            # 真正的预算裁剪/摘要发生在上下文组装层，不在 provider 层。
            "max_tokens": max(request.max_tokens, 4096),
        }
        if model:
            body["model"] = model

        # 推理开关透传（2026-08-13）: 提取/分类/HyDE 等任务关思考
        # （{"type":"disabled"}）— 快且不烧 max_tokens。
        thinking = request.metadata.get("thinking")
        if thinking is not None:
            body["thinking"] = thinking

        if request.response_format == "json":
            body["response_format"] = {"type": "json_object"}

        # B8-4/B3: 网关熔断感知重试。Circuit open 时网关 30s 内拒绝所有
        # 请求（half_open 放行首个探测）；突发调用会雪崩式叠加失败。
        # 这里短退避 1 次：half_open 放行后即成功，不加重上游负担。
        # 非熔断错误不冒泡 — 统一走降级路径（失败 metrics + 可观测错误体），
        # 保证调用方永远拿到 GenerateResult 而非裸异常。
        try:
            try:
                _timeout = None
                if getattr(request, "timeout_ms", 0):
                    _timeout = request.timeout_ms / 1000.0
                data = self._post("/v1/chat/completions", body, provider,
                                  timeout=_timeout)
            except RuntimeError as e:
                _code = getattr(e, "code", "") or ""
                # 2026-08-13: 优先按稳定 code 判定（error_catalog 查表）,
                # 文本匹配仅作旧版网关兜底。
                if _code == "CIRCUIT_OPEN" or (
                        "circuit" in str(e).lower()
                        and "open" in str(e).lower()):
                    time.sleep(1.0)
                    data = self._post("/v1/chat/completions", body, provider,
                                      timeout=_timeout)
                else:
                    raise
            choices = data.get("choices", [])
            text = ""
            if choices:
                msg = choices[0].get("message", {})
                text = msg.get("content", "")
                # Reasoning models put output in reasoning_content
                if not text:
                    text = msg.get("reasoning_content", "")
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
            self.record_metrics(metrics)
            return GenerateResult(text=text, metrics=metrics, raw_response=data)
        except Exception as e:
            latency = (time.time() - t0) * 1000
            # B3: 失败详情必须可观测 — 分类 + 状态码 + 错误体进 metrics，
            # 避免"空 model/熔断/上游 4xx"只留一条 warning 靠人工猜。
            msg = str(e)
            code = None
            if isinstance(e, RuntimeError) and "Gateway HTTP " in msg:
                try:
                    code = int(msg.split("Gateway HTTP ")[1].split(":")[0])
                except Exception:
                    code = None
            low = msg.lower()
            if "circuit" in low and "open" in low:
                etype = "circuit_open"
            elif "timeout" in low:
                etype = "timeout"
            elif "rate_limit" in low or "429" in msg:
                etype = "rate_limit"
            elif code is not None and 400 <= code < 500:
                etype = "validation"
            else:
                etype = "connection"
            logger.warning(
                "Gateway call failed (provider=%s, type=%s, status=%s): %s",
                provider, etype, code, msg,
            )
            metrics = LLMCallMetrics(
                provider_name=provider,
                latency_ms=latency,
                input_tokens=0,
                output_tokens=0,
                success=False,
                model_id=model or "",
                error_type=etype,
                status_code=code,
            )
            self.record_metrics(metrics)
            # 透传错误体（网关/上游原始信息）供上层 trace 消费
            return GenerateResult(
                text=f"[Gateway Error: {etype} {code or ''} {msg}]",
                metrics=metrics,
                raw_response={"error": msg, "error_type": etype,
                              "status_code": code, "provider": provider,
                              "model": model},
            )

    def health_check(self) -> bool:
        """Check switch /v1/health. Works without httpx (urllib fallback)."""
        try:
            data = self._get("/v1/health")
            # switch returns {"status": "ok", "providers_healthy": N, ...}
            return data.get("status") in ("ok", "healthy", "degraded")
        except Exception as e:
            logger.debug("Gateway health check failed: %s", e)
            return False

    def estimate_latency_ms(self, prompt_len: int = 0) -> float:
        """Conservative estimate for gateway routing."""
        return 200.0  # gateway overhead + provider latency

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all providers registered in the gateway."""
        try:
            data = self._get("/v1/providers")
            return data.get("providers", [])
        except Exception:
            return []
