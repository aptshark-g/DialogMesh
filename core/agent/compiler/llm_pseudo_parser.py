"""LLM 伪拆解器 — 粗粒度语义槽位标注"""
import json
from .models import SlotValue, ParseContext


class LLMPseudoParser:
    def __init__(self, llm_provider, max_retries: int = 1):
        self.llm = llm_provider
        self.max_retries = max_retries
        self.last_prompt = ""
        self.last_raw = ""

    async def parse(self, sentence: str, context: object = None) :
        prompt = self._build_prompt(sentence, context)
        for attempt in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=120)
            self.last_raw = raw
            parsed = self._parse_response(raw)
            if parsed:
                return parsed
        return None

    def _build_prompt(self, sentence: str, context: object = None) -> str:
        prompt = (
            "你是一个语义槽位标注器。将以下句子拆解为语义槽位。\n"
            "不要推理原因, 不要添加额外信息, 只需结构化回显。\n"
            "对每个槽位输出 value 和 confidence (0-1, 你对此判断的确定程度)。\n\n"
            "标准槽位: agent(主体), action(动作), patient(受体), result(结果), cause(原因)\n\n"
            "输出格式(JSON):\n"
            '{"slots": {"agent": {"value": "...", "confidence": 0.95}, ...}, '
            '"utterance_type": "statement|question|command", '
            '"sentiment": "positive|negative|neutral"}\n\n'
            f"句子: {sentence}"
        )
        if context and context.entities:
            prompt += f"\n\n前序实体参考: {json.dumps(context.entities, ensure_ascii=False)}"
        return prompt

    def _parse_response(self, raw: str) :
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            data = json.loads(raw[start:end + 1])
            if "slots" not in data:
                return None
            for k, v in data["slots"].items():
                if "value" not in v or "confidence" not in v:
                    return None
                v["confidence"] = max(0.0, min(1.0, float(v.get("confidence", 0))))
            return data
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
