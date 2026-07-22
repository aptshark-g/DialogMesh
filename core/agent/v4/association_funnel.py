"""Association Funnel — 五层漏斗实体关系发现引擎。

Layer 1: 句法表层 — entities + co-occurrence (复用 IntentParser)
Layer 2: 语义本体 — entity type hierarchy (复用 PCR cognitive)
Layer 3: 语用意图 — behavior labels, 7-dimensional belief
Layer 4: 时序模式 — Markov transition counts
Layer 5: 因果链 — constraint inheritance (if-then closure)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class LayerType(Enum):
    SYNTACTIC = 1
    SEMANTIC = 2
    PRAGMATIC = 3
    TEMPORAL = 4
    CAUSAL = 5


@dataclass
class Entity:
    name: str
    types: List[str] = field(default_factory=list)  # hex_address, function, module, ...
    layer_origin: LayerType = LayerType.SYNTACTIC


@dataclass
class Relation:
    """A discovered relation between entities — first-class, auditable."""
    source: Entity
    target: Entity
    relation_type: str  # co_occurs, type_compatible, behaviorally_linked, temporally_chained, causally_implies
    strength: float = 0.0
    evidence: List[str] = field(default_factory=list)
    layer: LayerType = LayerType.SYNTACTIC
    discovered_at: float = field(default_factory=time.time)


@dataclass
class BeliefState:
    """7-dimensional belief — not a single confidence number."""
    support: int = 0
    conflict: int = 0
    stability: float = 0.5
    coverage: float = 0.0
    recency: float = 1.0
    novelty: float = 0.0
    entropy: float = 1.0

    @property
    def is_consensus(self) -> bool:
        return (self.support >= 2 and self.conflict <= 2 and self.stability >= 0.6)


@dataclass
class Layer1Syntactic:
    """Layer 1: entity co-occurrence from raw events."""
    co_pairs: Dict[Tuple[str, str], int] = field(default_factory=dict)

    def ingest(self, entities: List[str]):
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 3, len(entities))):
                pair = (entities[i], entities[j])
                self.co_pairs[pair] = self.co_pairs.get(pair, 0) + 1

    def top_relations(self, min_count: int = 2) -> List[Relation]:
        return [Relation(
            source=Entity(pair[0]), target=Entity(pair[1]),
            relation_type="co_occurs", strength=count,
            evidence=[f"co-occurred {count} times"], layer=LayerType.SYNTACTIC,
        ) for pair, count in self.co_pairs.items() if count >= min_count]


@dataclass
class Layer2Semantic:
    """Layer 2: entity type compatibility."""
    type_registry: Dict[str, str] = field(default_factory=dict)
    compatible_pairs: Dict[Tuple[str, str], int] = field(default_factory=dict)

    def register(self, entity: str, etype: str):
        self.type_registry[entity] = etype

    def ingest(self, relations: List[Relation]):
        for rel in relations:
            t1 = self.type_registry.get(rel.source.name, "unknown")
            t2 = self.type_registry.get(rel.target.name, "unknown")
            if t1 != "unknown" and t2 != "unknown":
                pair = (t1, t2)
                self.compatible_pairs[pair] = self.compatible_pairs.get(pair, 0) + 1


@dataclass
class Layer3Pragmatic:
    """Layer 3: behavior labels with 7-dimensional belief."""
    behavior_labels: Dict[str, BeliefState] = field(default_factory=dict)

    def vote(self, label: str, evidence: str, support: bool = True):
        if label not in self.behavior_labels:
            self.behavior_labels[label] = BeliefState()
        b = self.behavior_labels[label]
        if support:
            b.support += 1
        else:
            b.conflict += 1
        b.stability = b.support / max(1, b.support + b.conflict)
        b.novelty *= 0.9

    def consensus_labels(self) -> List[str]:
        return [label for label, b in self.behavior_labels.items() if b.is_consensus]


@dataclass
class Layer4Temporal:
    """Layer 4: Markov transition patterns."""
    transitions: Dict[Tuple[str, str], int] = field(default_factory=dict)
    _last_label: Optional[str] = None

    def record(self, label: str):
        if self._last_label and self._last_label != label:
            pair = (self._last_label, label)
            self.transitions[pair] = self.transitions.get(pair, 0) + 1
        self._last_label = label

    def top_chains(self, min_count: int = 3) -> List[Tuple[str, str, int]]:
        return [(s, t, c) for (s, t), c in self.transitions.items() if c >= min_count]


@dataclass
class Layer5Causal:
    """Layer 5: causal closure — if-then constraint inheritance."""
    implications: Dict[str, List[str]] = field(default_factory=dict)

    def learn(self, cause: str, effect: str):
        if cause not in self.implications:
            self.implications[cause] = []
        if effect not in self.implications[cause]:
            self.implications[cause].append(effect)

    def close(self, label: str) -> List[str]:
        """Transitive closure: if A→B and B→C, then A→C."""
        visited = set()
        stack = [label]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(self.implications.get(node, []))
        visited.discard(label)
        return list(visited)


class AssociationFunnel:
    """Five-layer entity relation discovery engine.

    Ingest: events from EventBus (PCR, Intent, Behavior)
    Output: Relation[], behavior_labels[], causal_chains[]
    """

    def __init__(self):
        self.layer1 = Layer1Syntactic()
        self.layer2 = Layer2Semantic()
        self.layer3 = Layer3Pragmatic()
        self.layer4 = Layer4Temporal()
        self.layer5 = Layer5Causal()

    def ingest_pcr(self, expectation: str, entities: List[str] = None):
        """PCR event → Layer3 behavior label vote."""
        self.layer3.vote(expectation, "pcr_expectation")

    def ingest_intent(self, category: str, entities: List[str] = None):
        """Intent event → Layer1 co-occurrence + Layer3 label."""
        if entities:
            self.layer1.ingest(entities)
        self.layer3.vote(category, "intent_category")

    def ingest_behavior(self, label: str = ""):
        """Behavior event → Layer4 temporal transition."""
        self.layer4.record(label)

    def run(self) -> dict:
        """Execute full funnel and return discoveries."""
        discoveries = {
            "layer1_relations": self.layer1.top_relations(min_count=1),
            "layer3_consensus": self.layer3.consensus_labels(),
            "layer4_chains": self.layer4.top_chains(min_count=1),
            "layer5_closure": {},
        }
        # Layer 2: feed Layer 1 relations
        self.layer2.ingest(discoveries["layer1_relations"])

        # Layer 5: causal closure from consensus
        labels = discoveries["layer3_consensus"]
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                self.layer5.learn(labels[i], labels[j])
        for label in labels:
            discoveries["layer5_closure"][label] = self.layer5.close(label)

        return discoveries
