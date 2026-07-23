"""InterpretationGenerator: produce multiple candidate interpretations from a DomainObservation."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from .models import Interpretation, DomainObservation, Evidence


class InterpretationGenerator:
    """Generate multiple interpretations from a single DomainObservation.

    Uses 5 strategies:
      - Action-driven: from interaction action
      - Object-driven: from domain objects
      - Relation-driven: from surface relations
      - Context-driven: from history / engineering graph / user profile
      - Uncertainty-driven: low-confidence signals
    """

    def generate(self, domain_obs: DomainObservation,
                 context: dict = None) -> List[Interpretation]:
        ctx = context or {}
        results: List[Interpretation] = []
        seen_hypotheses: set = set()

        # Strategy 1: Action-driven
        for action in domain_obs.actions:
            interp = self._gen_from_strategy("action", action, domain_obs, ctx)
            if interp and interp.hypothesis not in seen_hypotheses:
                seen_hypotheses.add(interp.hypothesis)
                results.append(interp)

        # Strategy 2: Object-driven
        if domain_obs.objects:
            objs_str = ", ".join(domain_obs.objects[:3])
            interp = self._gen_from_strategy("object", objs_str, domain_obs, ctx)
            if interp and interp.hypothesis not in seen_hypotheses:
                seen_hypotheses.add(interp.hypothesis)
                results.append(interp)

        # Strategy 3: Relation-driven
        for rel in (domain_obs.relations or [])[:2]:
            rel_str = f"{rel.get('type', '')}:{rel.get('from', '')}->{rel.get('to', '')}"
            interp = self._gen_from_strategy("relation", rel_str, domain_obs, ctx)
            if interp and interp.hypothesis not in seen_hypotheses:
                seen_hypotheses.add(interp.hypothesis)
                results.append(interp)

        # Strategy 4: Context-driven
        if ctx:
            interp = self._gen_from_strategy("context", "history_or_profile", domain_obs, ctx)
            if interp and interp.hypothesis not in seen_hypotheses:
                seen_hypotheses.add(interp.hypothesis)
                results.append(interp)

        # Strategy 5: Uncertainty-driven (always produce at least one)
        if not results:
            interp = self._gen_from_strategy("fallback", "unclear_intent", domain_obs, ctx)
            results.append(interp)

        # Limit to 5 interpretations max
        return results[:5]

    def _gen_from_strategy(self, strategy: str, seed: str,
                           domain_obs: DomainObservation, context: dict) -> Optional[Interpretation]:
        templates = {
            "action": "Interpretation based on action: {seed} involving {objects}",
            "object": "Interpretation focused on objects: {seed} with action {actions}",
            "relation": "Interpretation from relation: {seed}",
            "context": "Interpretation considering prior context and user profile",
            "fallback": "Uncertain intent: further evidence needed for {objects}",
        }
        hypothesis = templates.get(strategy, "Interpretation: {seed}").format(
            seed=seed,
            objects=", ".join(domain_obs.objects[:3]) if domain_obs.objects else "unknown",
            actions=", ".join(domain_obs.actions[:3]) if domain_obs.actions else "unknown",
        )
        evidence_ids = [
            f"ev_{strategy}_{uuid.uuid4().hex[:6]}",
            *(domain_obs.evidence_sources or [])[:2],
        ]
        return Interpretation(
            interpretation_id=self._new_id("int"),
            domain_observation_id=domain_obs.observation_id,
            summary=f"[{strategy}] {seed[:60]}",
            hypothesis=hypothesis,
            evidence_refs=evidence_ids,
        )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
