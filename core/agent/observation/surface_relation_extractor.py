"""SurfaceRelationExtractor: extract explicit positional/ordering relations from text."""
import re
from typing import List, Dict


class SurfaceRelationExtractor:
    """Extract surface relations (before, after, inside, between, etc.) from text.
    These are explicit in the text and do NOT require inference.
    Semantic relations (depends_on, implements, causes) are left for Hypothesis Engine.
    """

    ZH_PATTERNS: List[tuple] = [
        (re.compile(r"前\s*面|之前|在[^。]*?前"), "before"),  # ??, ??, ?...?
        (re.compile(r"后\s*面|之后|在[^。]*?后"), "after"),   # ??, ??, ?...?
        (re.compile(r"里\s*面|内\s*部|在[^。]*?里"), "inside"), # ??, ??, ?...?
        (re.compile(r"中\s*间|之间|在[^。]*?之间"), "between"), # ??, ??
        (re.compile(r"旁\s*边|附近|在[^。]*?旁"), "beside"),  # ??, ??
        (re.compile(r"上\s*面|下\s*面"), "above_below"),  # ??, ??
    ]

    EN_PATTERNS: List[tuple] = [
        (re.compile(r"\bbefore\b", re.IGNORECASE), "before"),
        (re.compile(r"in front of", re.IGNORECASE), "before"),
        (re.compile(r"\bafter\b", re.IGNORECASE), "after"),
        (re.compile(r"behind", re.IGNORECASE), "after"),
        (re.compile(r"\binside\b|\bwithin\b", re.IGNORECASE), "inside"),
        (re.compile(r"\bbetween\b", re.IGNORECASE), "between"),
        (re.compile(r"\bbeside\b|\bnext to\b", re.IGNORECASE), "beside"),
        (re.compile(r"\babove\b|\bbelow\b", re.IGNORECASE), "above_below"),
    ]

    def __init__(self):
        self._patterns = self.ZH_PATTERNS + self.EN_PATTERNS

    def extract(self, text: str, entities: list = None) -> List[dict]:
        relations: List[dict] = []
        ents = entities or []
        for pattern, rel_type in self._patterns:
            for match in pattern.finditer(text):
                relations.append({
                    "type": rel_type,
                    "text": match.group(),
                    "span": (match.start(), match.end()),
                })
        # Attach entities to relations if they appear near the relation text
        if ents and relations:
            relations = self._attach_entities(relations, text, ents)
        return relations

    def _attach_entities(self, relations: List[dict], text: str, entities: list) -> List[dict]:
        for rel in relations:
            start, end = rel["span"]
            nearby = [e for e in entities if e in text[max(0, start - 20):end + 20]]
            if len(nearby) >= 2:
                rel["from"] = nearby[0]
                rel["to"] = nearby[-1]
            elif nearby:
                rel["from"] = nearby[0]
        return relations
