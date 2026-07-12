"""UserInterpreter: Parse + Classify + Interpret."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List

from .models import DomainObservation
from .interpretation_generator import InterpretationGenerator
from .user_domain_adapter import create_user_adapter


class UserInterpreter:

    def __init__(self, action_resolver=None):
        self._action_resolver = action_resolver
        self._interp_generator = InterpretationGenerator()
        if self._action_resolver is not None:
            self._action_resolver.register_domain(create_user_adapter())

    def interpret(self, normalized: dict, context: dict = None) -> Dict[str, Any]:
        event_id = normalized.get("event_id", "")
        kind = normalized.get("kind", "")
        payload = normalized.get("flat_payload", {})
        text = payload.get("text", payload.get("description", ""))

        domain_action = "preference_set"
        if self._action_resolver and text:
            try:
                results = self._action_resolver.resolve("user", text)
                if results: domain_action = results[0].action
            except Exception: pass

        objects = [str(v) for v in payload.values() if isinstance(v, str)]
        obs_id = self._new_id("usr")
        domain_obs = DomainObservation(
            domain="user", observation_id=obs_id, event_id=event_id,
            summary=text[:200], actions=[], objects=objects[:3],
            evidence_sources=[f"ev_usr_{self._new_id('e')}"],
        )
        interpretations = self._interp_generator.generate(domain_obs, context)

        return {
            "summary": text[:200], "actions": [], "objects": objects[:3],
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
