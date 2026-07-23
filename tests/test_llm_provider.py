"""Test LLM provider — zero hardcoded API keys.

Priority: LM Studio (local) → DeepSeek (env var) → None (skip LLM tests).
"""

import os, json, urllib.request


def get_test_llm():
    """Returns an LLM provider for testing. Never hardcodes keys."""
    
    # Try 1: LM Studio (local, no key needed)
    if _lm_studio_available():
        return LMStudioProvider()
    
    # Try 2: DeepSeek (needs DEEPSEEK_KEY env var)
    key = os.environ.get("DEEPSEEK_KEY", "")
    if key:
        return DeepSeekProvider(key)
    
    # No LLM available — tests will skip LLM paths
    return None


def _lm_studio_available() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:1234/v1/models")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


class LMStudioProvider:
    """LM Studio local LLM — no API key needed."""
    
    def generate(self, prompt: str, max_tokens: int = 300, temperature: float = 0.7) -> str:
        req = urllib.request.Request(
            "http://127.0.0.1:1234/v1/chat/completions",
            data=json.dumps({
                "model": "nvidia/nemotron-3-nano-4b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"].get("content", "")
        if not content:
            content = data["choices"][0]["message"].get("reasoning_content", "")
        return content


class DeepSeekProvider:
    """DeepSeek API — key from env var only."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def generate(self, prompt: str, max_tokens: int = 300, temperature: float = 0.7) -> str:
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        opener = urllib.request.build_opener()
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
            )
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )
        resp = opener.open(req, timeout=30)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
