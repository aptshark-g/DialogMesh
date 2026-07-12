"""MemoryInterpreter: Parse + Classify + Interpret."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List

from .models import DomainObservation
from .interpretation_generator import InterpretationGenerator
from .memory_domain_adapter import create_memory_adapter


class MemoryInterpreter:

    def __init__(self, action_resolver=None):
        self._action_resolver = action_resolver
        self._interp_generator = InterpretationGenerator()
        if self._action_resolver is not None:
            self._action_resolver.register_domain(create_memory_adapter())

    def interpret(self, normalized: dict, context: dict = None) -> Dict[str, Any]:
        event_id = normalized.get("event_id", "")
        kind = normalized.get("kind", "")
        payload = normalized.get("flat_payload", {})
        text = payload.get("text", payload.get("description", ""))

        domain_action = "remember"
        if self._action_resolver and text:
            try:
                results = self._action_resolver.resolve("memory", text)
                if results: domain_action = results[0].action
            except Exception: pass

        objects = [str(v) for v in payload.values() if isinstance(v, str) and len(v) < 100]
        obs_id = self._new_id("mem")
        domain_obs = DomainObservation(
            domain="memory", observation_id=obs_id, event_id=event_id,
            summary=text[:200], actions=[], objects=objects[:5],
            evidence_sources=[f"ev_mem_{self._new_id('e')}"],
        )
        interpretations = self._interp_generator.generate(domain_obs, context)

        return {
            "summary": text[:200], "actions": [], "objects": objects[:5],
            "interpretations": [
                {"summary": i.summary, "hypothesis": i.hypothesis, "evidence_refs": i.evidence_refs}
                for i in interpretations
            ],
            "evidence_ids": domain_obs.evidence_sources,
            "meta": {"domain_action": domain_action, "event_kind": kind},
        }

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
