"""DialogueInterpreter: Parse + Classify + Extract Relations + Generate Interpretations."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from .models import DomainObservation, Interpretation, Evidence
from .surface_relation_extractor import SurfaceRelationExtractor
from .interpretation_generator import InterpretationGenerator
from .dialogue_domain_adapter import create_dialogue_adapter


class DialogueInterpreter:
    """Interpret dialog.message events into DomainResult dicts.

    Pipeline:
      1. TieredParser.parse(text) ? facts (subject, predicate, object, entities)
      2. TieredActionResolver.resolve("dialogue", text) ? interaction_action
      3. SurfaceRelationExtractor.extract(text, entities) ? surface_relations
      4. InterpretationGenerator.generate(domain_obs, context) ? interpretations
      5. Return DomainResult dict
    """

    def __init__(self, tiered_parser=None, action_resolver=None):
        self._tiered_parser = tiered_parser
        self._action_resolver = action_resolver
        self._relation_extractor = SurfaceRelationExtractor()
        self._interp_generator = InterpretationGenerator()

        if self._action_resolver is not None:
            adapter = create_dialogue_adapter()
            self._action_resolver.register_domain(adapter)

    def interpret(self, normalized: dict, context: dict = None) -> Dict[str, Any]:
        """Interpret a normalized dialog event. Returns DomainResult dict."""
        text = normalized.get("flat_payload", {}).get("text", "")
        event_id = normalized.get("event_id", "")

        # 1. Parse text
        parsed = None
        if self._tiered_parser and text:
            try:
                parsed = self._tiered_parser.parse(text)
            except Exception:
                pass

        # Extract facts
        predicate = getattr(parsed, "predicate", None) if parsed else None
        entities = getattr(parsed, "entities", []) if parsed else []
        imperative = getattr(parsed, "imperative", False) if parsed else False
        question = getattr(parsed, "question", False) if parsed else False

        actions = []
        if predicate:
            actions.append(predicate)
        if imperative:
            actions.append("request")
        if question:
            actions.append("question")

        objects = list(entities) if entities else []

        # 2. Classify action
        interaction_action = "inform"
        if self._action_resolver and text:
            try:
                results = self._action_resolver.resolve("dialogue", text)
                if results:
                    interaction_action = results[0].action
            except Exception:
                pass

        # 3. Extract surface relations
        relations = self._relation_extractor.extract(text, entities)

        # 4. Build DomainObservation + generate interpretations
        obs_id = self._new_id("obs")
        domain_obs = DomainObservation(
            domain="dialogue",
            observation_id=obs_id,
            event_id=event_id,
            summary=text[:200],
            actions=actions,
            objects=objects,
            relations=relations,
            evidence_sources=[f"ev_dialog_{self._new_id('e')}"],
        )

        interpretations = self._interp_generator.generate(domain_obs, context)

        return {
            "summary": text[:200],
            "actions": actions,
            "objects": objects,
            "relations": relations,
            "interpretations": [
                {"summary": i.summary, "hypothesis": i.hypothesis,
                 "evidence_refs": i.evidence_refs}
                for i in interpretations
            ],
            "evidence_ids": domain_obs.evidence_sources,
            "meta": {"interaction_action": interaction_action},
        }

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
