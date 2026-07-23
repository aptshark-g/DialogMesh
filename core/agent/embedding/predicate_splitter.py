"""Predicate-argument splitter using LLM."""
from typing import Tuple, Optional


class PredicateArgumentSplitter:
    """Split action text into predicate (verb) and argument (noun)."""

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def split(self, action: str) -> Tuple[str, str]:
        """Return (predicate, argument). Falls back to simple split."""
        if not action:
            return ("", "")
        # Try LLM light split if available
        if self.llm and hasattr(self.llm, "generate"):
            try:
                result = self.llm.generate(
                    f'Split "{action}" into verb and noun. Return JSON: {{"verb":"","noun":""}}',
                    max_tokens=60,
                )
                import json
                data = json.loads(result.strip().removeprefix("`json").removesuffix("`").strip())
                return (data.get("verb", ""), data.get("noun", ""))
            except Exception:
                pass
        # Fallback: first word = predicate, rest = argument
        parts = action.strip().split(None, 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")
