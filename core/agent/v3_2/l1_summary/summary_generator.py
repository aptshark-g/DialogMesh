from .models import ContentCategory


class SummaryGenerator:
    def __init__(self, llm=None):
        self.llm = llm

    def generate(self, category, turn, meta):
        if category == ContentCategory.DETERMINISTIC:
            return f"{meta.current_action}: {turn.get(chr(114)+chr(101)+chr(115)+chr(117)+chr(108)+chr(116), chr(34)+chr(34))}"
        if category == ContentCategory.TEMPLATE:
            return "[Request] " + turn.get("intent", "")
        return turn.get("raw_text", "")[:100]
