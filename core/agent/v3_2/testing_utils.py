"""v3.2 测试工具 — MockLLM + fixtures"""


class MockLLM:
    """v3.2 异步 Mock LLM — 按配置返回 JSON 字符串"""

    def __init__(self, json_response: str = ""):
        self.json_response = json_response

    async def generate(self, prompt: str, max_tokens: int = 120) -> str:
        return self.json_response


DEFAULT_COMPILER_RESPONSE = (
    '{"slots": {"agent": {"value": "human", "confidence": 0.95}, '
    '"action": {"value": "run", "confidence": 0.98}, '
    '"patient": {"value": "program", "confidence": 0.90}}, '
    '"utterance_type": "statement", "sentiment": "neutral"}'
)
