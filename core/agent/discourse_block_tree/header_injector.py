"""Stage 1: HeaderInjector ? ????????????"""
import re
from typing import List, Optional
from .models import EDU, DiscourseEntity


NEGATION_MARKERS = {"不", "没有", "无", "非", "不要", "不用", "别", "never", "not", "no", "never"}
UNCERTAINTY_MARKERS = {"可能", "也许", "大概", "或许", "应该", "maybe", "perhaps", "possibly"}
IMPERATIVE_MARKERS = {"请", "帮", "帮我", "please", "help"}
PRONOUNS = {"这个", "那个", "它", "其", "该", "这", "那", "它们", "这些", "那些",
            "this", "that", "these", "those", "it", "its", "there"}


class EntityCache:
    """??????"""
    def __init__(self, max_rounds=5):
        self._recent: List[DiscourseEntity] = []
        self._max = max_rounds

    def push(self, entities: List[DiscourseEntity]):
        for e in entities:
            if e.confidence >= 0.6:
                self._recent.append(e)
        if len(self._recent) > self._max * 3:
            self._recent = self._recent[-self._max * 3:]

    def find(self, pronoun: str) -> Optional[DiscourseEntity]:
        # Demonstratives (这个/那个/这些/那些) resolve to the most recent entity;
        # others (它/其) also fall back to the last entity — the cache only
        # holds recent discourse entities, so "last" is the correct referent.
        demonstrative = pronoun in ("这个", "那个", "这些", "那些", "它", "其", "该")
        for e in reversed(self._recent):
            if demonstrative or pronoun in ("this", "that", "these", "those", "it", "its"):
                return e
        return None

    def find_by_type(self, etype: str) -> Optional[DiscourseEntity]:
        for e in reversed(self._recent):
            if e.etype == etype:
                return e
        return None


class HeaderInjector:
    """
    ????????????????/??????
    ???: ??????(0.95) > ?????(0.85) > ???(0.70) > ???(0.60)
    ??: < 1ms (???)
    """

    def __init__(self, entity_cache: Optional[EntityCache] = None):
        self.cache = entity_cache or EntityCache()

    def inject(self, text: str) -> str:
        """??: ?????????????????"""
        result = text
        for pronoun in PRONOUNS:
            if pronoun in result:
                resolved = self.cache.find(pronoun)
                if resolved:
                    result = result.replace(pronoun, resolved.text, 1)
        return result

    def extract_entities(self, text: str) -> List[DiscourseEntity]:
        """??????????"""
        entities = []
        patterns = [
            (r"([A-Za-z_]\w*(?:\.\w+)+)", "module"),        # module.path
            (r"(0x[0-9A-Fa-f]+)", "address"),                # hex address
            (r"(\d+(?:\.\d+)?)", "number"),                  # numbers
            (r"(\"[^\"]+\")", "string"),                     # quoted string
            (r"(\'[^\']+\')", "string"),                     # single-quoted
        ]
        for pat, etype in patterns:
            for m in re.finditer(pat, text):
                entities.append(DiscourseEntity(text=m.group(1), etype=etype, confidence=0.9))
        return entities

    def detect_pragmatics(self, text: str) -> dict:
        """??????: ??/???/??/??"""
        return {
            "negation": any(m in text for m in NEGATION_MARKERS),
            "uncertainty": any(m in text for m in UNCERTAINTY_MARKERS),
            "imperative": any(m in text for m in IMPERATIVE_MARKERS),
            "question": "?" in text,
        }


HEADER_INJECTOR = HeaderInjector()
