"""EngineeringInterpreter: Parse + Classify + Extract Relations + Generate Interpretations."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from .models import DomainObservation
from .surface_relation_extractor import SurfaceRelationExtractor
from .interpretation_generator import InterpretationGenerator
from .engineering_domain_adapter import create_engineering_adapter


class EngineeringInterpreter:

    def __init__(self, tiered_parser=None, action_resolver=None):
        self._tiered_parser = tiered_parser
        self._action_resolver = action_resolver
        self._relation_extractor = SurfaceRelationExtractor()
        self._interp_generator = InterpretationGenerator()

        if self._action_resolver is not None:
            self._action_resolver.register_domain(create_engineering_adapter())

    def interpret(self, normalized: dict, context: dict = None) -> Dict[str, Any]:
        event_id = normalized.get("event_id", "")
        kind = normalized.get("kind", "")
        payload = normalized.get("flat_payload", {})
        text = payload.get("text", self._build_text(kind, payload))

        # Parse
        parsed = None
        if self._tiered_parser and text:
            try: parsed = self._tiered_parser.parse(text)
            except Exception: pass

        predicate = getattr(parsed, "predicate", None) if parsed else None
        entities = getattr(parsed, "entities", []) if parsed else []
        imperative = getattr(parsed, "imperative", False) if parsed else False

        actions = [predicate] if predicate else []
        if imperative: actions.append("modify")
        objects = list(entities) if entities else self._extract_objects(kind, payload)

        # Action classification
        domain_action = "query_status"
        if self._action_resolver and text:
            try:
                results = self._action_resolver.resolve("engineering", text)
                if results: domain_action = results[0].action
            except Exception: pass

        # Surface relations
        relations = self._relation_extractor.extract(text, entities)

        # Generate interpretations
        obs_id = self._new_id("eng")
        domain_obs = DomainObservation(
            domain="engineering", observation_id=obs_id, event_id=event_id,
            summary=text[:200], actions=actions, objects=objects,
            relations=relations,
            evidence_sources=[f"ev_eng_{self._new_id('e')}"],
        )
        interpretations = self._interp_generator.generate(domain_obs, context)

        return {
            "summary": text[:200], "actions": actions, "objects": objects,
            "relations": relations,
            "interpretations": [
                {"summary": i.summary, "hypothesis": i.hypothesis, "evidence_refs": i.evidence_refs}
                for i in interpretations
            ],
            "evidence_ids": domain_obs.evidence_sources,
            "meta": {"domain_action": domain_action, "event_kind": kind},
        }

    def _build_text(self, kind: str, payload: dict) -> str:
        if kind == "ui.drag":
            n = payload.get("node", payload.get("node.id", "item"))
            t = payload.get("target", "")
            p = payload.get("position", "")
            return f"drag {n} to {t} {p}".strip()
        if kind == "ui.click":
            n = payload.get("node", payload.get("node.id", "item"))
            return f"click {n}"
        if kind == "git.commit":
            return payload.get("message", "")
        if kind == "tool.call":
            return payload.get("tool", "tool")
        if kind == "config.change":
            return payload.get("key", "config")
        return str(payload.get("description", ""))

    def _extract_objects(self, kind: str, payload: dict) -> List[str]:
        objs = []
        for key in ("node", "node.id", "target", "module", "tool", "key"):
            v = payload.get(key, "")
            if v: objs.append(str(v))
        return objs

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
