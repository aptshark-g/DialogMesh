"""Phase 1 — Compression split router.

Information-theoretic decision: P(frequency) × I(value) → storage strategy.
Routes blocks to RAG (high-value low-freq), Compressor (high-freq), or Index-only.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Callable
import logging, json

logger = logging.getLogger(__name__)


@dataclass
class StorageDecision:
    """What to do with a piece of content."""
    strategy: str          # "rag" | "compress" | "index_only" | "working"
    value: float           # I(x) information value
    frequency: float       # P(x) probability estimate
    reason: str = ""


class CompressionRouter:
    """Information-theoretic storage router.

    P × I → strategy:
      P(low) + I(high)  → RAG (raw, high-value, sparse)
      P(high) + I(high) → COMPRESS (rule extraction)
      P(high) + I(low)  → COMPRESS or DROP (routine, low value)
      P(low) + I(low)   → INDEX_ONLY (not worth storing content)

    Usage:
        router = CompressionRouter(ragraph_bridge, compressor, value_fn)
        decision = router.route(block)
        if decision.strategy == "rag":
            router.store_rag(block)
        elif decision.strategy == "compress":
            router.compress_block(block)
    """

    # Thresholds (from config, zero hardcoded magic numbers)
    FREQ_THRESHOLD = 0.3    # P > 0.3 = "frequent"  
    VALUE_THRESHOLD = 0.5   # I > 0.5 = "high value"

    def __init__(self, ragraph_bridge=None, compressor=None, value_fn=None):
        self.ragraph = ragraph_bridge
        self.compressor = compressor
        self._value_fn = value_fn or self._default_value
        self._entity_freq: Dict[str, int] = {}

    def route(self, content: dict) -> StorageDecision:
        """Decision: what storage strategy for this content."""
        value = self._value_fn(content)
        freq = self._estimate_frequency(content)

        if freq < self.FREQ_THRESHOLD and value > self.VALUE_THRESHOLD:
            return StorageDecision("rag", value, freq, 
                                   f"low-freq({freq:.2f})+high-value({value:.2f})")
        if freq >= self.FREQ_THRESHOLD and value > self.VALUE_THRESHOLD:
            return StorageDecision("compress", value, freq,
                                   f"high-freq({freq:.2f})+high-value({value:.2f})")
        if freq >= self.FREQ_THRESHOLD:
            return StorageDecision("compress", value, freq,
                                   f"high-freq({freq:.2f}) — compress/aggregate")
        return StorageDecision("index_only", value, freq,
                               f"low-freq({freq:.2f})+low-value({value:.2f})")

    def _default_value(self, content: dict) -> float:
        """Compute information value from content structure."""
        entities = content.get("entities", [])
        text = content.get("text", "")
        intent = content.get("intent", "")

        # Entity rarity
        rarity = 0.3
        if entities and self._entity_freq:
            rarities = []
            for e in entities:
                name = e.get("name", str(e)) if isinstance(e, dict) else str(e)
                freq = self._entity_freq.get(name, 0)
                total = max(1, sum(self._entity_freq.values()))
                rarities.append(1.0 - freq / total)
            rarity = sum(rarities) / len(rarities) if rarities else 0.3

        # Text novelty (simple: length + punctuation as proxy)
        novelty = min(1.0, len(text) / 200) * 0.5

        return round(rarity * 0.5 + novelty * 0.5, 3)

    def _estimate_frequency(self, content: dict) -> float:
        """Estimate how frequently this content pattern appears."""
        entities = content.get("entities", [])
        if not entities or not self._entity_freq:
            return 0.1  # default: sparse

        total = max(1, sum(self._entity_freq.values()))
        freqs = []
        for e in entities:
            name = e.get("name", str(e)) if isinstance(e, dict) else str(e)
            freqs.append(self._entity_freq.get(name, 0) / total)
        return sum(freqs) / len(freqs) if freqs else 0.1

    def record_entity(self, entity_name: str):
        """Track entity frequency for P(x) estimation."""
        self._entity_freq[entity_name] = self._entity_freq.get(entity_name, 0) + 1

    def store_rag(self, content: dict, entity_name: str = ""):
        """Store high-value low-frequency content in RAG index."""
        if not self.ragraph:
            return
        name = entity_name or content.get("text", "")[:50]
        text = content.get("text", "")
        self.ragraph.index_entity(name, text, {"value": content.get("value", 0.5)})
        logger.debug("RAG indexed: %s (value=%.2f)", name, content.get("value", 0.5))

    def compress_block(self, content: dict) -> Optional[dict]:
        """Compress high-frequency content into rules."""
        if not self.compressor:
            return None
        try:
            return self.compressor.compress(
                content.get("edges", []),
                content.get("beliefs", []),
            )
        except Exception as e:
            logger.debug("Compress failed: %s", e)
            return None

    def status(self) -> dict:
        return {
            "entity_freq": dict(sorted(self._entity_freq.items(), 
                                       key=lambda x: -x[1])[:10]),
            "total_entities": len(self._entity_freq),
        }
