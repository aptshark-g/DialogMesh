import re
from .models import ContentCategory


class ContentClassifier:
    SKIP_LLM_AFTER = 5
    PATTERNS = [r"return (0x[0-9a-f]+|\\d+)", r"error (code|message)", r"exit code"]

    def classify(self, turn, consecutive_det=0):
        if turn.get("type") in ("tool_output", "code_result"):
            return ContentCategory.DETERMINISTIC
        text = turn.get("raw_text", "")
        for p in self.PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                return ContentCategory.DETERMINISTIC
        if ("set" in text or "modify" in text or "change" in text) and any(c.isdigit() for c in text):
            return ContentCategory.TEMPLATE
        if consecutive_det >= self.SKIP_LLM_AFTER:
            return ContentCategory.TEMPLATE
        return ContentCategory.LLM
