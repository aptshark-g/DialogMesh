"""TieredRelationExtractor: three-tier relation extraction (pattern -> embedding -> LLM)."""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from core.agent.v4.tiered.pipeline import Tier, MultiTierPipeline
from core.agent.v4.tiered.action_resolver import EmbeddingIndex
from .surface_relation_extractor import SurfaceRelationExtractor

logger = logging.getLogger(__name__)

RELATION_TYPES = [
    "before", "after", "inside", "between", "beside",
    "above", "below", "left_of", "right_of", "contains",
    "precedes", "follows", "adjacent_to", "within",
]


class TieredRelationExtractor:

    def __init__(self, registry=None, llm_callable=None):
        self._extractor = SurfaceRelationExtractor()
        self._llm_callable = llm_callable
        self._rel_index = EmbeddingIndex(dim=32)
        for rt in RELATION_TYPES:
            self._rel_index.add(rt, EmbeddingIndex.hash_embedding(rt, dim=32))
        self._rel_words: Dict[str, str] = {
            "before": "before", "after": "after", "inside": "inside",
            "between": "between", "beside": "beside", "above": "above",
            "below": "below", "precedes": "before", "follows": "after",
            "prior to": "before", "subsequent": "after", "contained in": "inside",
            "left of": "left_of", "right of": "right_of",
        }
        rule_tier = Tier(level=0, name="relation.pattern", process=self._tier_pattern,
                         confidence_threshold=0.80, time_budget_ms=5)
        embed_tier = Tier(level=1, name="relation.embedding", process=self._tier_embedding,
                          confidence_threshold=0.70, time_budget_ms=20)
        llm_tier = Tier(level=2, name="relation.llm", process=self._tier_llm,
                        confidence_threshold=0.50, time_budget_ms=2000)
        self._pipeline = MultiTierPipeline([rule_tier, embed_tier, llm_tier], name="relation_extractor")

    def extract(self, text: str, entities: list = None) -> List[dict]:
        ctx = {"text": text, "entities": entities or []}
        result = self._pipeline.execute(ctx)
        val = result.value
        if isinstance(val, dict) and "relations" in val:
            return val["relations"]
        return val if isinstance(val, list) else []

    def stats(self) -> dict:
        return self._pipeline.stats()

    def on_new_phrase(self, callback):
        if callback not in self._feedback_callbacks:
            self._feedback_callbacks.append(callback)

    def _promote_phrase(self, phrase, rel_type, source):
        if phrase not in self._rel_words:
            self._rel_words[phrase] = rel_type
            for cb in self._feedback_callbacks:
                try: cb(phrase, rel_type, source)
                except Exception: pass
        c = self._phrase_hits.get(phrase, 0) + 1
        self._phrase_hits[phrase] = c
        if c >= 3 and self._rel_index.get_embedding(rel_type) is None:
            self._rel_index.add(rel_type, EmbeddingIndex.hash_embedding(rel_type, dim=32))

    def _tier_pattern(self, input_data: dict, _ctx: dict) -> dict:
        rels = self._extractor.extract(input_data["text"], input_data.get("entities", []))
        return {"relations": rels, "confidence": 0.90 if rels else 0.0, "source": "pattern"}

    def _tier_embedding(self, input_data: dict, _ctx: dict) -> dict:
        text = input_data["text"]
        results: List[dict] = []
        text_lower = text.lower()
        for phrase, rel_type in self._rel_words.items():
            if phrase in text_lower:
                results.append({"type": rel_type, "text": phrase, "source": "embedding_quick"})
        if not results:
            words = re.findall(r"[a-zA-Z]+", text_lower)
            for word in words:
                if len(word) < 4: continue
                emb = EmbeddingIndex.hash_embedding(word, dim=32)
                best = self._rel_index.nearest(emb, threshold=0.55)
                if best and best not in [r.get("type") for r in results]:
                    results.append({"type": best, "text": word, "source": "embedding_semantic"})
                    self._promote_phrase(word, best, "embedding")
        return {"relations": results, "confidence": 0.75 if results else 0.0, "source": "embedding"}

    def _tier_llm(self, input_data: dict, _ctx: dict) -> dict:
        if not self._llm_callable: return []
        text = input_data["text"]
        prompt = "Extract spatial/ordering relations. Return JSON list with type (before/after/inside/between/beside/above/below/left_of/right_of), from, to. If no relations, return [].\nText: " + repr(text) + "\nJSON:"
        try:
            response = self._llm_callable(prompt)
            data = json.loads(response) if isinstance(response, str) else response
            if isinstance(data, list):
                for item in data:
                    item["source"] = "llm"
                    rt = item.get("type", "")
                    if rt and rt not in self._rel_words:
                        self._rel_words[rt] = rt
                    if rt and self._rel_index.get_embedding(rt) is None:
                        self._rel_index.add(rt, EmbeddingIndex.hash_embedding(rt, dim=32))
                return {"relations": data, "confidence": 0.85 if data else 0.0, "source": "llm"}
        except Exception:
            logger.exception("LLM relation extraction failed")
        return {"relations": [], "confidence": 0.0, "source": "llm_error"}
