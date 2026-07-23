"""Association Funnel V2 — LLM Hypothesis Generation + Rule-based Verification.

Layer 1.5: LLM Cognitive Completer — infer implicit entities
Layer 2:   LLM Type Inference — entity type classification  
Layer 3:   LLM Hypothesis Generation — behavior label hypotheses, 7D belief verification
Layer 5:   LLM Causal Discovery — causal chain discovery

Pattern: LLM generates hypotheses, rules vote/verify, consensus emerges from 7D belief.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class LayerType(Enum):
    SYNTACTIC = 1
    COMPLETER = 1.5
    SEMANTIC = 2
    PRAGMATIC = 3
    TEMPORAL = 4
    CAUSAL = 5


@dataclass
class Entity:
    name: str
    types: List[str] = field(default_factory=list)
    layer_origin: LayerType = LayerType.SYNTACTIC


@dataclass
class BeliefState:
    """7-dimensional belief — bridges LLM output and rule verification."""
    support: int = 0
    conflict: int = 0
    stability: float = 0.5
    coverage: float = 0.0
    recency: float = 1.0
    novelty: float = 0.0
    entropy: float = 1.0
    llm_generated: bool = False
    llm_rationale: str = ""

    @property
    def is_consensus(self) -> bool:
        return self.support >= 2 and self.conflict <= 2 and self.stability >= 0.6


@dataclass
class Relation:
    source: Entity
    target: Entity
    relation_type: str
    strength: float = 0.0
    evidence: List[str] = field(default_factory=list)
    layer: LayerType = LayerType.SYNTACTIC
    llm_rationale: str = ""


# ═══════════════════════════════════════════════════
# Layer-by-layer with LLM integration
# ═══════════════════════════════════════════════════

@dataclass
class Layer1Syntactic:
    """Co-occurrence pairs from entity extraction. No LLM needed."""
    co_pairs: Dict[Tuple[str, str], int] = field(default_factory=dict)

    def ingest(self, entities: List[str]):
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 3, len(entities))):
                pair = (entities[i], entities[j])
                self.co_pairs[pair] = self.co_pairs.get(pair, 0) + 1

    def top_relations(self, min_count: int = 1) -> List[Relation]:
        return [Relation(
            source=Entity(pair[0]), target=Entity(pair[1]),
            relation_type="co_occurs", strength=count,
            evidence=[f"co-occurred {count} times"], layer=LayerType.SYNTACTIC,
        ) for pair, count in self.co_pairs.items() if count >= min_count]


@dataclass
class Layer1_5Completer:
    """LLM Cognitive Completer — infer implicit entities from text.

    Pattern: LLM(question) → implicit entities → feed back to Layer 1.
    """
    implicit_entities: List[str] = field(default_factory=list)
    llm_calls: int = 0

    def complete(self, text: str, llm_provider=None) -> List[str]:
        """Ask LLM: 'what entities are IMPLIED but not explicitly named?'"""
        if llm_provider is None:
            return self._fallback_complete(text)

        prompt = f"""You are analyzing user text for implicit entities.
Text: "{text[:200]}"

List entities that are IMPLIED but not explicitly named.
Return JSON array of strings. Example: ["virtual_memory", "stack_frame"]"""

        try:
            response = llm_provider.generate(prompt, max_tokens=100)
            entities = json.loads(response) if response else []
            return entities if isinstance(entities, list) else []
        except Exception as e:
            logger.debug("Completer LLM failed: %s", e)
            return self._fallback_complete(text)

    def _fallback_complete(self, text: str) -> List[str]:
        """Rule-based fallback: context keywords."""
        ctx_keywords = {
            "reverse": ["binary_analysis", "disassembly"],
            "patch": ["binary_modification", "offset_patching"],
            "analyze": ["static_analysis", "dynamic_analysis"],
            "encrypt": ["cryptographic_algorithm", "key_derivation"],
        }
        result = []
        for kw, implied in ctx_keywords.items():
            if kw in text.lower():
                result.extend(implied)
        return result


@dataclass
class Layer2Semantic:
    """LLM Type Inference + type compatibility tracking."""
    type_registry: Dict[str, str] = field(default_factory=dict)
    compatible_pairs: Dict[Tuple[str, str], int] = field(default_factory=dict)
    llm_calls: int = 0

    def register(self, entity: str, etype: str):
        self.type_registry[entity] = etype

    def infer_types(self, entities: List[str], llm_provider=None) -> Dict[str, str]:
        """Ask LLM: 'classify each entity into a type category.'"""
        if llm_provider is None:
            return self._fallback_types(entities)

        prompt = f"""Classify each entity into a type category.
Entities: {entities}

Categories: hex_address, function_name, module_name, register, flag, tool_name,
            data_structure, protocol, algorithm_name, file_format, unknown

Return JSON: {{"entity_name": "category", ...}}"""

        try:
            response = llm_provider.generate(prompt, max_tokens=200)
            result = json.loads(response) if response else {}
            self.llm_calls += 1
            if isinstance(result, dict):
                self.type_registry.update(result)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.debug("Type inference LLM failed: %s", e)
            return self._fallback_types(entities)

    def _fallback_types(self, entities: List[str]) -> Dict[str, str]:
        """Rule-based: hex → address, lowercase words → tool/function, uppercase → flag."""
        import re
        result = {}
        for e in entities:
            if re.match(r'^0x[0-9a-fA-F]+$', e):
                result[e] = "hex_address"
            elif e.islower() and len(e) > 2:
                result[e] = "function_name"
            elif e.isupper():
                result[e] = "flag"
            else:
                result[e] = "unknown"
        self.type_registry.update(result)
        return result

    def ingest(self, relations: List[Relation]):
        for rel in relations:
            t1 = self.type_registry.get(rel.source.name, "unknown")
            t2 = self.type_registry.get(rel.target.name, "unknown")
            if t1 != "unknown" and t2 != "unknown":
                pair = (t1, t2)
                self.compatible_pairs[pair] = self.compatible_pairs.get(pair, 0) + 1


@dataclass
class Layer3Pragmatic:
    """LLM Hypothesis Generation + 7D belief verification.

    Pattern: LLM generates behavior labels → rules vote → belief states decide.
    """
    behavior_labels: Dict[str, BeliefState] = field(default_factory=dict)
    llm_calls: int = 0

    def generate_hypotheses(self, text: str, entities: List[str],
                            llm_provider=None) -> List[str]:
        """LLM generates candidate behavior labels. Rules verify via vote()."""
        if llm_provider is None:
            return self._fallback_hypotheses(text, entities)

        prompt = f"""User is performing reverse engineering. Generate behavior labels.
Text: "{text[:200]}"
Entities: {entities[:10]}

Return JSON array of behavior labels from: memory_scan, code_patch, crypto_analysis,
    function_hook, packer_identification, protocol_reverse, anti_debug_analysis,
    network_trace, data_structure_recovery, exploit_development

Return: ["label1", "label2"]"""

        try:
            response = llm_provider.generate(prompt, max_tokens=100)
            labels = json.loads(response) if response else []
            self.llm_calls += 1
            if isinstance(labels, list):
                for label in labels:
                    self.vote(label, "llm_hypothesis")
            return labels if isinstance(labels, list) else []
        except Exception as e:
            logger.debug("Hypothesis generation failed: %s", e)
            return self._fallback_hypotheses(text, entities)

    def _fallback_hypotheses(self, text: str, entities: List[str]) -> List[str]:
        """Keyword-based fallback when LLM unavailable."""
        hints = {
            "scan": "memory_scan", "memor": "memory_scan", "dump": "memory_scan",
            "patch": "code_patch", "nop": "code_patch", "modif": "code_patch",
            "encrypt": "crypto_analysis", "cipher": "crypto_analysis", "aes": "crypto_analysis",
            "hook": "function_hook", "detour": "function_hook", "inline": "function_hook",
            "packer": "packer_identification", "upx": "packer_identification",
            "debug": "anti_debug_analysis", "anti": "anti_debug_analysis",
        }
        labels = []
        lower = text.lower()
        for cue, label in hints.items():
            if cue in lower and label not in labels:
                labels.append(label)
        for label in labels:
            self.vote(label, "fallback_keyword")
        return labels

    def vote(self, label: str, evidence: str, support: bool = True):
        if label not in self.behavior_labels:
            self.behavior_labels[label] = BeliefState()
        b = self.behavior_labels[label]
        if support:
            b.support += 1
        else:
            b.conflict += 1
        b.stability = b.support / max(1, b.support + b.conflict)
        b.novelty *= 0.95

    def consensus_labels(self) -> List[str]:
        return [l for l, b in self.behavior_labels.items() if b.is_consensus]


@dataclass
class Layer4Temporal:
    """Markov transitions. No LLM needed — pattern is in the counts."""
    transitions: Dict[Tuple[str, str], int] = field(default_factory=dict)
    _last_label: Optional[str] = None

    def record(self, label: str):
        if self._last_label and self._last_label != label:
            pair = (self._last_label, label)
            self.transitions[pair] = self.transitions.get(pair, 0) + 1
        self._last_label = label

    def top_chains(self, min_count: int = 1) -> List[Tuple[str, str, int]]:
        return [(s, t, c) for (s, t), c in self.transitions.items() if c >= min_count]


@dataclass
class Layer5Causal:
    """LLM Causal Discovery — constraint inheritance + transitive closure.

    Pattern: LLM(consensus labels) → causal edges → rule verifies via evidence.
    """
    implications: Dict[str, List[str]] = field(default_factory=dict)
    llm_calls: int = 0
    _evidence_log: List[dict] = field(default_factory=list)

    def discover(self, consensus_labels: List[str], evidence: List[str] = None,
                 llm_provider=None) -> dict:
        """LLM: 'given these consensus labels, what causal relationships exist?'"""
        if evidence:
            self._evidence_log.extend(evidence)

        if llm_provider is None:
            return self._fallback_causal(consensus_labels)

        prompt = f"""Given these system behavior labels: {consensus_labels}
Evidence log (last 5): {self._evidence_log[-5:] if self._evidence_log else 'none'}

Discover causal relationships between labels. Format: {{"cause": "effect"}}
Example: {{"memory_scan": "code_patch"}} means scanning memory CAUSES patches.

Return JSON object of cause→effect pairs."""

        try:
            response = llm_provider.generate(prompt, max_tokens=150)
            causal = json.loads(response) if response else {}
            self.llm_calls += 1
            if isinstance(causal, dict):
                for cause, effect in causal.items():
                    self.learn(cause, effect)
            return causal if isinstance(causal, dict) else {}
        except Exception as e:
            logger.debug("Causal discovery LLM failed: %s", e)
            return self._fallback_causal(consensus_labels)

    def learn(self, cause: str, effect: str):
        self.implications.setdefault(cause, [])
        if effect not in self.implications[cause]:
            self.implications[cause].append(effect)

    def _fallback_causal(self, labels: List[str]) -> dict:
        """Transitive closure: if A,B appear together, A→B."""
        result = {}
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                self.learn(labels[i], labels[j])
                result[labels[i]] = labels[j]
        return result

    def close(self, label: str) -> List[str]:
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


# ═══════════════════════════════════════════════════
# Funnel orchestration
# ═══════════════════════════════════════════════════

class AssociationFunnel:
    """Five-layer + LLM hypothesis generation. Bridge between events and knowledge."""

    def __init__(self, llm_provider=None):
        self.llm = llm_provider
        self.layer1 = Layer1Syntactic()
        self.layer15 = Layer1_5Completer()
        self.layer2 = Layer2Semantic()
        self.layer3 = Layer3Pragmatic()
        self.layer4 = Layer4Temporal()
        self.layer5 = Layer5Causal()
        self._text_buffer: List[str] = []

    def ingest_event(self, event: dict):
        """Consume events from EventBus. Maps to appropriate layers."""
        kind = event.get("kind", "")
        payload = event.get("payload", {})
        text = payload.get("text", "")

        if text:
            self._text_buffer.append(text)

        if kind == "pcr_computed":
            expectation = payload.get("expectation", "UNKNOWN")
            self.layer3.vote(expectation, "pcr_expectation")

        elif kind == "intent_parsed":
            category = payload.get("category", "UNKNOWN")
            entities = payload.get("entities", [])
            if entities:
                self.layer1.ingest(entities)
                # Layer 2: type inference on new entities
                unknown = [e for e in entities if e not in self.layer2.type_registry]
                if unknown:
                    self.layer2.infer_types(unknown, self.llm)
            self.layer3.vote(category, "intent_category")
            self.layer4.record(category)

            # Layer 1.5: complete implicit entities
            if text:
                implicit = self.layer15.complete(text, self.llm)
                if implicit:
                    self.layer1.ingest(implicit)
                    self.layer2.infer_types(implicit, self.llm)

            # Layer 3: LLM generates behavior label hypotheses
            self.layer3.generate_hypotheses(
                text or "", entities or [], self.llm)

        elif kind == "behavior_recorded":
            self.layer4.record(payload.get("label", ""))

    def run(self) -> dict:
        """Execute full funnel with LLM at each layer."""
        consensus = self.layer3.consensus_labels()

        # Layer 2: feed Layer 1 relations
        l1_relations = self.layer1.top_relations(min_count=1)
        self.layer2.ingest(l1_relations)

        # Layer 5: LLM causal discovery from consensus
        if consensus:
            self.layer5.discover(
                consensus, [f"label:{l}" for l in consensus], self.llm)

        return {
            "layer1_relations": l1_relations,
            "layer1.5_implicit": self.layer15.implicit_entities,
            "layer2_compatible": dict(self.layer2.compatible_pairs),
            "layer3_consensus": consensus,
            "layer3_all_beliefs": {l: b.__dict__ for l, b in self.layer3.behavior_labels.items()},
            "layer4_chains": self.layer4.top_chains(min_count=1),
            "layer5_causal": {k: v for k, v in self.layer5.implications.items()},
            "stats": {
                "llm_calls": (self.layer15.llm_calls + self.layer2.llm_calls +
                             self.layer3.llm_calls + self.layer5.llm_calls),
                "total_entities": len(self.layer2.type_registry),
                "total_beliefs": len(self.layer3.behavior_labels),
            }
        }
