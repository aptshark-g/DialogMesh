"""TieredActionResolver: shared multi-tier classification kernel for v4.
Rule (fast) -> Embedding (medium) -> LLM (slow), with feedback loop.
"""
from __future__ import annotations
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActionCandidate:
    action: str
    confidence: float
    source: str = "rule"
    domain: str = ""
    is_new: bool = False
    embedding: Optional[List[float]] = None
    evidence_refs: List[str] = field(default_factory=list)


class EmbeddingIndex:

    def __init__(self, dim: int = 64):
        self._dim = dim
        self._store: Dict[str, List[float]] = {}
        self._access_count: Dict[str, int] = {}
        self._heat: Dict[str, float] = {}

    def add(self, action: str, embedding: List[float]) -> None:
        if len(embedding) != self._dim:
            embedding = list(embedding[:self._dim]) if len(embedding) > self._dim else embedding + [0.0] * (self._dim - len(embedding))
        self._store[action] = embedding

    def nearest(self, query_embedding: List[float], threshold: float = 0.75) -> Optional[str]:
        if not self._store:
            return None
        query = list(query_embedding[:self._dim]) if len(query_embedding) > self._dim else query_embedding + [0.0] * (self._dim - len(query_embedding))
        best_action, best_score = None, -1.0
        for action, emb in self._store.items():
            score = self._cosine(query, emb)
            if score > best_score:
                best_score = score
                best_action = action
        if best_score >= threshold:
            self._access_count[best_action] = self._access_count.get(best_action, 0) + 1
            return best_action
        return None

    def get_embedding(self, action: str) -> Optional[List[float]]:
        return self._store.get(action)

    def size(self) -> int:
        return len(self._store)

    def promote(self, action: str) -> None:
        self._heat[action] = self._heat.get(action, 0.0) + 1.0

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0

    @staticmethod
    def hash_embedding(text: str, dim: int = 64) -> List[float]:
        return [(hash(f"{text}_{i}") % 10000) / 10000.0 - 0.5 for i in range(dim)]


@dataclass
class DomainAdapter:
    domain: str
    rules: Dict[str, List[str]] = field(default_factory=dict)
    action_index: Optional[EmbeddingIndex] = None
    llm_prompt_template: str = ""
    default_action: str = "unknown"
    llm_callable: Optional[Callable] = None

    def on_new_action(self, text: str, action: str) -> None:
        words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        pattern = " ".join(words[:3])
        if action not in self.rules:
            self.rules[action] = []
        if pattern not in self.rules[action]:
            self.rules[action].append(pattern)
        if self.action_index is not None:
            emb = EmbeddingIndex.hash_embedding(action)
            self.action_index.add(action, emb)


class TieredActionResolver:

    def __init__(self, registry=None):
        self._registry = registry
        self._adapters: Dict[str, DomainAdapter] = {}

    def register_domain(self, adapter: DomainAdapter) -> None:
        self._adapters[adapter.domain] = adapter
        if adapter.action_index is None:
            adapter.action_index = EmbeddingIndex()

    def resolve(self, domain: str, input_text: str) -> List[ActionCandidate]:
        adapter = self._adapters.get(domain)
        if adapter is None:
            return [ActionCandidate(action="unknown", confidence=0.0, domain=domain)]

        results: List[ActionCandidate] = []

        r = self._tier_rule(input_text, adapter)
        if r is not None and r.confidence >= 0.70:
            return [r]
        if r is not None:
            results.append(r)

        if adapter.action_index and adapter.action_index.size() > 0:
            e = self._tier_embedding(input_text, adapter)
            if e is not None and e.confidence >= 0.75:
                return [e]
            if e is not None:
                results.append(e)

        if adapter.llm_callable is not None:
            l = self._tier_llm(input_text, adapter)
            if l is not None:
                if l.is_new:
                    adapter.on_new_action(input_text, l.action)
                results.append(l)

        if not results:
            results.append(ActionCandidate(action=adapter.default_action, confidence=0.1, source="fallback", domain=domain))
        return results

    def add_action(self, domain: str, action: str, text_patterns: List[str], embedding: Optional[List[float]] = None) -> None:
        adapter = self._adapters.get(domain)
        if adapter is None:
            return
        for pat in text_patterns:
            adapter.rules.setdefault(action, []).append(pat)
        if adapter.action_index is not None:
            adapter.action_index.add(action, embedding or EmbeddingIndex.hash_embedding(action))

    def stats(self) -> dict:
        return {
            "domains": list(self._adapters.keys()),
            "per_domain": {
                d: {"rules_count": len(a.rules), "index_size": a.action_index.size() if a.action_index else 0}
                for d, a in self._adapters.items()
            },
        }

    @staticmethod
    def _tier_rule(text: str, adapter: DomainAdapter) -> Optional[ActionCandidate]:
        tl = text.lower()
        for action, patterns in adapter.rules.items():
            for pat in patterns:
                if pat in tl or tl in pat:
                    return ActionCandidate(action=action, confidence=0.85, source="rule", domain=adapter.domain)
        return None

    @staticmethod
    def _tier_embedding(text: str, adapter: DomainAdapter) -> Optional[ActionCandidate]:
        if adapter.action_index is None or adapter.action_index.size() == 0:
            return None
        q = EmbeddingIndex.hash_embedding(text)
        best = adapter.action_index.nearest(q, threshold=0.65)
        if best:
            return ActionCandidate(action=best, confidence=0.78, source="embedding", domain=adapter.domain, embedding=q)
        return None

    @staticmethod
    def _tier_llm(text: str, adapter: DomainAdapter) -> Optional[ActionCandidate]:
        if not adapter.llm_callable or not adapter.llm_prompt_template:
            return None
        prompt = adapter.llm_prompt_template.format(text=text)
        try:
            response = adapter.llm_callable(prompt)
            data = json.loads(response) if isinstance(response, str) else response
            return ActionCandidate(
                action=data.get("action", adapter.default_action),
                confidence=float(data.get("confidence", 0.6)),
                source="llm",
                domain=adapter.domain,
                is_new=bool(data.get("is_new_action", False)),
            )
        except Exception:
            logger.exception("LLM failed for domain=%s", adapter.domain)
            return None
