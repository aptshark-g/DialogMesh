"""DeepSeek LLM provider — direct API for bootstrap.

Uses OPENAI_BASE_URL and OPENAI_API_KEY env vars or direct config.
Falls back gracefully when API is unreachable.
"""

from __future__ import annotations
from typing import Optional
import os
import json
import logging

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """Minimal DeepSeek LLM provider for agent_native pipeline.

    Tries in order:
      1. Direct API (api.deepseek.com with DEEPSEEK_API_KEY)
      2. Switch Gateway (localhost:8080)
      3. LM Studio (localhost:1234)
    """

    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = "deepseek-chat"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL",
                                                    "https://api.deepseek.com/v1")
        self.model = model
        self._available = None  # lazy check

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = bool(self.api_key)
        return self._available

    def generate(self, prompt: str, max_tokens: int = 300,
                 temperature: float = 0.1) -> str:
        """Generate text. Returns empty string on failure."""
        if not self.available:
            return self._try_local_fallback(prompt)

        try:
            import urllib.request
            url = f"{self.base_url}/chat/completions"
            body = json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }).encode("utf-8")

            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.debug("DeepSeek API failed: %s, trying local fallback", e)
            return self._try_local_fallback(prompt)

    def _try_local_fallback(self, prompt: str) -> str:
        """Try LM Studio or Switch Gateway as fallback."""
        # Try LM Studio
        try:
            import urllib.request
            url = "http://localhost:1234/v1/chat/completions"
            body = json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.1,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"].get("content", "")
        except Exception:
            pass

        # Try Switch Gateway
        try:
            import urllib.request
            url = "http://localhost:8080/v1/chat/completions"
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"].get("content", "")
        except Exception:
            pass

        return ""
