"""BehaviorInterpreter: Parse + Classify + Interpret."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from .models import DomainObservation
from .interpretation_generator import InterpretationGenerator
from .behavior_domain_adapter import create_behavior_adapter


class BehaviorInterpreter:

    def __init__(self, action_resolver=None):
        self._action_resolver = action_resolver
        self._interp_generator = InterpretationGenerator()
        if self._action_resolver is not None:
            self._action_resolver.register_domain(create_behavior_adapter())

    def interpret(self, normalized: dict, context: dict = None) -> Dict[str, Any]:
        event_id = normalized.get("event_id", "")
        kind = normalized.get("kind", "")
        payload = normalized.get("flat_payload", {})
        text = payload.get("text", self._build_text(kind, payload))

        actions = []
        objects = self._extract_objects(kind, payload)

        domain_action = "click"
        if self._action_resolver and text:
            try:
                results = self._action_resolver.resolve("behavior", text)
                if results: domain_action = results[0].action
            except Exception: pass

        obs_id = self._new_id("beh")
        domain_obs = DomainObservation(
            domain="behavior", observation_id=obs_id, event_id=event_id,
            summary=text[:200], actions=actions, objects=objects,
            evidence_sources=[f"ev_beh_{self._new_id('e')}"],
        )
        interpretations = self._interp_generator.generate(domain_obs, context)

        return {
            "summary": text[:200], "actions": actions, "objects": objects,
            "interpretations": [
                {"summary": i.summary, "hypothesis": i.hypothesis, "evidence_refs": i.evidence_refs}
                for i in interpretations
            ],
            "evidence_ids": domain_obs.evidence_sources,
            "meta": {"domain_action": domain_action, "event_kind": kind},
        }

    def _build_text(self, kind: str, payload: dict) -> str:
        if kind == "ui.click":
            n = payload.get("node", payload.get("node.id", "item"))
            return f"click {n}"
        if kind == "ui.drag":
            n = payload.get("node", payload.get("node.id", "item"))
            t = payload.get("target", "")
            return f"drag {n} to {t}".strip()
        if kind == "ui.drop":
            return f"drop item"
        return str(payload.get("description", ""))

    def _extract_objects(self, kind: str, payload: dict) -> List[str]:
        objs = []
        for key in ("node", "node.id", "target", "element"):
            v = payload.get(key, "")
            if v: objs.append(str(v))
        return objs

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
