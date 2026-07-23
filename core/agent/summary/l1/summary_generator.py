from .models import ContentCategory


class SummaryGenerator:
    def __init__(self, llm=None):
        self.llm = llm

    def generate(self, category, turn, meta):
        if category == ContentCategory.DETERMINISTIC:
            return f"{meta.current_action}: {turn.get('result', '')}"
        if category == ContentCategory.TEMPLATE:
            return "[Request] " + turn.get("intent", "")
        if category == ContentCategory.LLM:
            return self._llm_compress(turn.get("raw_text", ""))
        return turn.get("raw_text", "")[:100]

    def _llm_compress(self, raw_text: str) -> str:
        """Compress raw text to ≤100 chars using LLM, falling back to truncation."""
        if not self.llm:
            return raw_text[:100]
        prompt = (
            "Compress the following text into a concise summary of at most 100 characters. "
            "Preserve the core meaning. Return only the compressed text, no explanation.\n\n"
            f"Text: {raw_text}\n\nCompressed:"
        )
        try:
            import asyncio
            result = asyncio.run(self.llm.generate(prompt, max_tokens=50))
            if result and len(str(result).strip()) > 0:
                compressed = str(result).strip()
                return compressed[:100]
        except Exception:
            pass
        return raw_text[:100]
