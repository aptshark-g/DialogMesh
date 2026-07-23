"""ExternalSkillAdapter: import external skills into Candidate Pool."""
import uuid
from typing import Any, Dict, List, Optional
from .models import CapabilityBlueprint, ActionNode, SkillBelief, SkillCandidate


class ExternalSkillAdapter:
    """Convert external skill formats into SkillCandidate objects."""

    def import_skill(self, source: str, data: dict) -> Optional[SkillCandidate]:
        if source == "harness": return self._from_harness(data)
        if source == "json": return self._from_json(data)
        if source == "openapi": return self._from_openapi(data)
        return self._from_json(data)  # fallback

    def import_batch(self, source: str, items: List[dict]) -> List[SkillCandidate]:
        candidates = []
        for item in items:
            c = self.import_skill(source, item)
            if c: candidates.append(c)
        return candidates

    # ?? specific adapters ??????????????????????????????????????

    def _from_harness(self, data: dict) -> SkillCandidate:
        name = data.get("name", data.get("identifier", "untitled"))
        steps = data.get("steps", data.get("execution", {}).get("steps", []))
        actions = []
        for i, step in enumerate(steps):
            if isinstance(step, str):
                actions.append(ActionNode(action_id=f"ext_{i}", action=step))
            elif isinstance(step, dict):
                actions.append(ActionNode(
                    action_id=f"ext_{i}", action=step.get("type", step.get("action", "unknown")),
                    preconditions=step.get("preconditions", []),
                    postconditions=step.get("postconditions", []),
                ))
        constraints = data.get("constraints", [])
        if isinstance(constraints, str): constraints = [constraints]
        bp = CapabilityBlueprint(
            blueprint_id=f"bp_ext_{uuid.uuid4().hex[:8]}",
            goal=name, constraints=constraints, action_graph=actions,
            verification=data.get("verification", []),
            domain=data.get("domain", "engineering"),
        )
        return SkillCandidate(
            candidate_id=f"c_ext_{uuid.uuid4().hex[:8]}",
            blueprint=bp, belief=SkillBelief(support=1, generality=0.7),
            source="external", references=data.get("references", []),
            domain=data.get("domain", "engineering"),
        )

    def _from_json(self, data: dict) -> SkillCandidate:
        goal = data.get("goal", data.get("name", "imported"))
        steps = data.get("steps", data.get("actions", []))
        actions = [ActionNode(action_id=f"ext_{i}", action=s if isinstance(s, str) else s.get("action", "unknown"))
                    for i, s in enumerate(steps)]
        bp = CapabilityBlueprint(
            blueprint_id=f"bp_ext_{uuid.uuid4().hex[:8]}",
            goal=goal, constraints=data.get("constraints", []),
            action_graph=actions, domain=data.get("domain", "engineering"),
        )
        return SkillCandidate(
            candidate_id=f"c_ext_{uuid.uuid4().hex[:8]}",
            blueprint=bp, belief=SkillBelief(support=1, generality=0.65),
            source="external", references=[],
            domain=data.get("domain", "engineering"),
        )

    def _from_openapi(self, data: dict) -> SkillCandidate:
        paths = data.get("paths", {})
        actions = []
        for path, methods in paths.items():
            for method in methods:
                actions.append(ActionNode(
                    action_id=f"api_{uuid.uuid4().hex[:8]}",
                    action=f"{method.upper()} {path}",
                ))
        bp = CapabilityBlueprint(
            blueprint_id=f"bp_api_{uuid.uuid4().hex[:8]}",
            goal=data.get("info", {}).get("title", "API") if isinstance(data.get("info"), dict) else "API",
            action_graph=actions, domain="api",
        )
        return SkillCandidate(
            candidate_id=f"c_api_{uuid.uuid4().hex[:8]}",
            blueprint=bp, belief=SkillBelief(support=1, generality=0.5),
            source="external", references=[],
            domain="api",
        )
