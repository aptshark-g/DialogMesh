"""DeepSeek LLM provider for v3.2

Usage:
  export DEEPSEEK_API_KEY="sk-..."
  python -c "import asyncio; from core.agent.v3_2.deepseek_provider import DeepSeekProvider; from core.agent.v3_2.integration import V32Pipeline; pipe=V32Pipeline(DeepSeekProvider()); r=asyncio.run(pipe.process('test')); print(r['parse'].slots)"

!!! WARNING !!!
Remove API keys before publishing to GitHub.
Use environment variables, never hardcode keys.
"""
import os, json, asyncio
from urllib.request import Request, urlopen

API_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider:
    """v3.2 Async LLM provider for DeepSeek API"""

    def __init__(self, api_key=None, model=None, base_url=None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.base_url = base_url or API_BASE

    async def generate(self, prompt, max_tokens=120):
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()
        req = Request(self.base_url + "/chat/completions", data=body, headers=headers)
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: urlopen(req, timeout=30))
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return "[DeepSeek Error: " + str(e) + "]"