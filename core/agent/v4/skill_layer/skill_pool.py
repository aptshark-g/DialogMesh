"""SkillPool: Candidate/Verified/Core lifecycle management."""
from __future__ import annotations
import threading, time
from typing import Dict, List, Optional
from .models import Skill, SkillCandidate, CapabilityBlueprint, SkillBelief


class SkillPool:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.Lock()

    def add_candidate(self, candidate: SkillCandidate) -> Skill:
        sid = candidate.candidate_id
        skill = Skill(skill_id=sid, blueprint=candidate.blueprint,
                      belief=candidate.belief, status="candidate",
                      source=candidate.source, references=candidate.references,
                      domain=candidate.domain or candidate.blueprint.domain)
        with self._lock: self._skills[sid] = skill
        return skill

    def get(self, skill_id: str) -> Optional[Skill]:
        with self._lock: return self._skills.get(skill_id)

    def get_ready(self, domain: str = "") -> List[Skill]:
        with self._lock:
            results = [s for s in self._skills.values() if s.status in ("verified", "core")]
            if domain: results = [s for s in results if s.domain == domain]
            return results

    def get_by_domain(self, domain: str) -> List[Skill]:
        with self._lock:
            return [s for s in self._skills.values() if s.domain == domain]

    def promote(self, skill_id: str) -> Optional[str]:
        with self._lock:
            s = self._skills.get(skill_id)
            if s is None: return None
            transitions = {"candidate": "verified", "verified": "core", "core": "core"}
            s.status = transitions.get(s.status, s.status)
            if s.status == "verified" and s.verified_at is None:
                s.verified_at = time.time()
            return s.status

    def deprecate(self, skill_id: str) -> None:
        with self._lock:
            s = self._skills.get(skill_id)
            if s: s.status = "deprecated"

    def stats(self) -> dict:
        with self._lock:
            by_status: Dict[str, int] = {}
            for s in self._skills.values():
                by_status[s.status] = by_status.get(s.status, 0) + 1
            return {"total": len(self._skills), "by_status": by_status}
