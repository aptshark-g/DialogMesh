"""Cognitive Profile - user expertise, preferences and behavior pattern tracking"""
import json, time, math
from typing import Optional
from dataclasses import dataclass, field

TIME_DECAY_HALF_LIFE = 86400 * 7  # 7 days
EXPERTISE_DOMAINS = ["debugging", "system_admin", "networking", "security", "performance",

                     "deployment", "configuration", "monitoring", "analysis", "general"]

STABLE_TRAIT_KEYS = ["openness","conscientiousness","extraversion","agreeableness","neuroticism","risk_tolerance","technical_depth","verbosity"]

@dataclass
class CognitiveProfile:
    user_id: str = "default"
    expertise: dict = field(default_factory=dict)
    preferences: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    session_count: int = 0
    total_turns: int = 0
    avg_stability: float = 0.0
    metacognition: float = 0.5
    divergence: float = 0.3
    confidence: float = 0.6
    stability_delta: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0
    stable_traits: dict = field(default_factory=dict)

    @classmethod
    def create(cls, user_id="default"):
        now = time.time()
        profile = cls(user_id=user_id, created_at=now, updated_at=now)
        profile.expertise = {d: 0.5 for d in EXPERTISE_DOMAINS}
        profile.expertise['general'] = 0.3
        return profile

    def to_dict(self):
        return {"user_id": self.user_id, "expertise": self.expertise,
                "preferences": self.preferences, "tags": self.tags,
                "session_count": self.session_count, "total_turns": self.total_turns,
                "avg_stability": self.avg_stability or 0.0,
                "metacognition": self.metacognition,
                "divergence": self.divergence,
                "confidence": self.confidence,
                "stability_delta": self.stability_delta,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "stable_traits": self.stable_traits}
    def from_dict(cls, d):
        return cls(**{k: d.get(k) for k in ["user_id","expertise","preferences","tags",
                    "session_count","total_turns","avg_stability","metacognition","divergence","confidence","stability_delta","created_at","updated_at","stable_traits"]})
 

    def get_expertise(self, domain: str) -> float:
        score = self.expertise.get(domain, 0.0)
        age = time.time() - self.updated_at
        decay = math.pow(0.5, age / TIME_DECAY_HALF_LIFE)
        return max(0.0, score * decay)

    def get_preference(self, action_type: str) -> float:
        return self.preferences.get(action_type, 0.0)

    def get_trait(self, key: str) -> float:
        """Get stable trait value, returns 0.5 if not found"""
        return self.stable_traits.get(key, 0.5)

class ProfileUpdater:
    def __init__(self, profile: CognitiveProfile):
        self.profile = profile

    def record_action(self, action_type: str, action_summary: str, stability: float, uncertainty: bool = False, topic_switch: bool = False):
        p = self.profile
        p.total_turns += 1
        p.avg_stability = (p.avg_stability * (p.total_turns - 1) + stability) / p.total_turns
        p.stability_delta = stability - p.avg_stability
        if uncertainty:
            p.metacognition = max(0.0, p.metacognition - 0.01)
        else:
            p.metacognition = min(1.0, p.metacognition + 0.005)
        if topic_switch:
            p.divergence = min(1.0, p.divergence + 0.02)
        else:
            p.divergence = max(0.0, p.divergence - 0.005)
        if action_type in ("execute", "delete", "stop", "enable", "deploy", "CODE_RUN"):
            p.confidence = min(1.0, p.confidence + 0.008)
        elif action_type in ("query", "explain", "search", "EXPLORATION"):
            p.confidence = max(0.0, p.confidence - 0.005)
        domain = self._infer_domain(action_type, action_summary)
        if domain:
            current = p.expertise.get(domain, 0.0)
            p.expertise[domain] = min(1.0, current + 0.05)
        p.preferences[action_type] = p.preferences.get(action_type, 0.0) + 0.02
        self._update_traits(action_type, action_summary, stability)
        self._acquire_tags(action_type, action_summary)
        p.updated_at = time.time()

    def _update_traits(self, action_type, action_summary, stability):
        p = self.profile
        if action_type in ("config","deploy","scan","debug","trace","compile"):
            p.stable_traits["technical_depth"] = min(1.0, p.stable_traits.get("technical_depth",0.5)+0.005)
        if action_type in ("delete","stop","disable","restart"):
            p.stable_traits["risk_tolerance"] = min(1.0, p.stable_traits.get("risk_tolerance",0.5)+0.01)
        if len(action_summary) > 40:
            p.stable_traits["verbosity"] = min(1.0, p.stable_traits.get("verbosity",0.5)+0.003)
        elif len(action_summary) < 10:
            p.stable_traits["verbosity"] = max(0.0, p.stable_traits.get("verbosity",0.5)-0.003)
        if stability < 0.3 and action_type != "UNKNOWN":
            p.stable_traits["neuroticism"] = min(1.0, p.stable_traits.get("neuroticism",0.5)+0.005)

    def record_session_end(self):
        self.profile.session_count += 1

    def _infer_domain(self, action_type: str, action_summary: str) -> Optional[str]:
        hints = {"debug":"debugging","check":"monitoring","monitor":"monitoring",
            "configure":"configuration","deploy":"deployment","scan":"security",
            "test":"performance","analyze":"analysis","show":"monitoring",
            "fix":"debugging","trace":"debugging","restart":"system_admin",
            "backup":"system_admin","restore":"system_admin","connect":"networking"}
        return hints.get(action_type)

    def _acquire_tags(self, action_type: str, action_summary: str):
        words = action_summary.lower().split()
        for w in words:
            if len(w) > 3 and w not in self.profile.tags:
                self.profile.tags.append(w)
        if len(self.profile.tags) > 50:
            self.profile.tags = self.profile.tags[-50:]

class EnhancedProfileMatcher:
    def __init__(self, profile: CognitiveProfile):
        self.profile = profile

    async def match(self, action_type: str, action_summary: str, profile_dict: dict = None) -> float:
        exp_score = self.profile.get_expertise(self._domain_for(action_type))
        pref_score = self.profile.get_preference(action_type)
        tag_score = self._tag_match(action_summary)
        return min(1.0, (exp_score * 0.5 + pref_score * 0.3 + tag_score * 0.2))

    def _domain_for(self, action_type: str) -> str:
        mapping = {"debug":"debugging","check":"monitoring","configure":"configuration",
            "deploy":"deployment","scan":"security","analyze":"analysis"}
        return mapping.get(action_type, "general")

    def _tag_match(self, text: str) -> float:
        if not self.profile.tags or not text:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for t in self.profile.tags if t.lower() in text_lower)
        return min(1.0, matches / max(len(self.profile.tags), 1) * 5)

class ProfileStore:
    def __init__(self, filepath: str = ""):
        self.filepath = filepath
        self._cache: dict[str, CognitiveProfile] = {}

    def get(self, user_id: str = "default") -> CognitiveProfile:
        if user_id not in self._cache:
            self._cache[user_id] = CognitiveProfile.create(user_id)
        return self._cache[user_id]

    def save(self, profile: CognitiveProfile):
        self._cache[profile.user_id] = profile
        if self.filepath:
            import os
            data = self._serialize()
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> dict:
        if not self.filepath:
            return {}
        try:
            with open(self.filepath, encoding="utf-8") as f:
                data = json.load(f)
            for uid, pd in data.items():
                self._cache[uid] = CognitiveProfile.from_dict(pd)
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _serialize(self) -> dict:
        return {uid: p.to_dict() for uid, p in self._cache.items()}
