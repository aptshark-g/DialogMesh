"""Track B — tag layer with L1-L2 acquisition + g-factor inference.

Design: docs/v3.0/design_cognitive_profile_v2.md §2.3, §4.2
  L1: passive observation (no user interaction)
  L2: implicit inference from dialogue patterns
  g-factor: LLM-based ability assessment
"""
from __future__ import annotations
import re, math, time, logging
from typing import Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

from .models import UserTag, CognitiveProfileV2


class TagAcquisitionEngine:
    """L1 + L2 tag acquisition for Track B.

    L1 (passive): language, emoji, device — directly observed
    L2 (inferred): occupation, domain, technical_depth — from patterns
    """

    # L1 detection patterns
    EMOJI_PATTERN = re.compile(r'[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]')
    ENGLISH_PATTERN = re.compile(r'[a-zA-Z]{3,}')
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,}')

    # L2 domain keywords → domain tags
    DOMAIN_KEYWORDS = {
        "software": ["代码", "部署", "API", "数据库", "Python", "Java", "架构", "测试",
                     "debug", "docker", "k8s", "git", "ci/cd", "微服务"],
        "ai_ml": ["模型", "训练", "推理", "神经网络", "深度学习", "transformer",
                  "embedding", "token", "prompt", "RAG"],
        "security": ["漏洞", "扫描", "攻击", "权限", "加密", "fuzz", "exploit",
                     "payload", "shellcode", "逆向"],
        "data": ["分析", "可视化", "统计", "pandas", "spark", "ETL", "数仓"],
        "devops": ["运维", "监控", "告警", "自动化", "ansible", "terraform", "pipeline"],
        "product": ["用户", "需求", "PRD", "体验", "交互", "设计"],
    }

    TECH_DEPTH_KEYWORDS = [
        "源码", "底层", "原理", "算法", "复杂度", "内存", "寄存器",
        "汇编", "内核", "协议", "抽象", "编译器",
    ]

    # Personality trait keywords (L2 inference)
    PERSONALITY_TRAITS = {
        "introvert": ["alone", "solitary", "quiet", "focus", "deep thinking", "avoid",
                      "独自", "安静", "深度思考", "不喜欢社交", "独处", "内向"],
        "extrovert": ["team", "collaborate", "present", "brainstorm", "energy", "people",
                      "团队", "合作", "交流", "分享", "外向", "社交"],
        "analytical": ["analysis", "systematic", "data", "logic", "evidence", "prove",
                       "分析", "系统化", "数据驱动", "逻辑", "证明"],
        "emotional": ["feel", "intuition", "heart", "harmony", "empathy", "value",
                      "感觉", "直觉", "内心", "和谐", "共情", "重视"],
        "planner": ["plan", "schedule", "organize", "deadline", "structure",
                    "计划", "安排", "组织", "截止", "结构"],
        "explorer": ["curious", "wonder", "maybe", "explore", "discover",
                     "好奇", "探索", "发现", "或许", "试试"],
    }

    SELF_AFFIRM_WORDS = [
        "我知道", "我做过", "我实现", "我解决了", "我理解", "我发现了",
        "i did", "i know", "i built", "i solved",
    ]

    def __init__(self):
        self._domain_frequencies: Counter = Counter()
        self._tech_depth_count: int = 0
        self._self_affirm_count: int = 0
        self._response_count: int = 0

    def acquire_l1(self, text: str, user_id: str = "default") -> Dict[str, UserTag]:
        """L1 passive: language, emoji, device — directly from input."""
        tags = {}

        # Language preference
        cn_count = len(self.CHINESE_PATTERN.findall(text))
        en_count = len(self.ENGLISH_PATTERN.findall(text))
        if cn_count > en_count:
            lang = "zh"
        elif en_count > cn_count:
            lang = "en"
        else:
            lang = "mixed"
        tags["language_preference"] = UserTag(
            name="language_preference", value=lang,
            confidence=0.9, source="L1",
        )

        # Emoji usage
        emoji_count = len(self.EMOJI_PATTERN.findall(text))
        tags["emoji_usage"] = UserTag(
            name="emoji_usage", value="frequent" if emoji_count > 2 else (
                "occasional" if emoji_count > 0 else "rare"),
            confidence=0.95, source="L1",
        )

        return tags

    def acquire_l2(self, user_text: str, system_response: str = "",
                   turn_count: int = 1, corrections: int = 0,
                   topic_words: List[str] = None) -> Dict[str, UserTag]:
        """L2 implicit inference from dialogue patterns."""
        tags = {}
        self._response_count += 1

        # Domain inference from keyword frequency
        all_text = (user_text + " " + system_response).lower()
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in all_text:
                    self._domain_frequencies[domain] += 1

        if self._domain_frequencies:
            top_domain, top_count = self._domain_frequencies.most_common(1)[0]
            conf = min(0.7, 0.3 + top_count * 0.1)
            tags["domain"] = UserTag(
                name="domain", value=top_domain,
                confidence=conf, source="L2",
            )

        # Technical depth
        for kw in self.TECH_DEPTH_KEYWORDS:
            if kw.lower() in all_text:
                self._tech_depth_count += 1
        td_ratio = self._tech_depth_count / self._response_count
        tags["technical_depth"] = UserTag(
            name="technical_depth",
            value="high" if td_ratio > 0.3 else ("medium" if td_ratio > 0.1 else "low"),
            confidence=min(0.7, 0.3 + td_ratio * 1.5), source="L2",
        )

        # Self-affirmation count (for Track A self_value_score)
        for word in self.SELF_AFFIRM_WORDS:
            if word.lower() in user_text.lower():
                self._self_affirm_count += 1

        # Personality trait detection (BGE semantic → no new keywords needed)
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            import numpy as np
            bge = SemanticEncoder()
            tv = bge.encode(user_text[:500])
            scored = []

            trait_descs = {
                "introvert": "preferring solitude, deep thinking, quiet analysis, working alone, internal focus",
                "extrovert": "team collaboration, social energy, presenting, brainstorming, group interaction",
                "analytical": "logical reasoning, data-driven, systematic thinking, evidence-based analysis",
                "emotional": "intuitive feeling, empathy, harmony-focused, people-oriented, value-driven",
                "planner": "organized, scheduled, structured, deadline-driven, systematic preparation",
                "explorer": "curious, wondering, exploring possibilities, open-ended, discovering new ideas",
            }
            for trait, description in trait_descs.items():
                dv = bge.encode(description)
                a = tv.flatten() if len(tv.shape) > 1 else tv
                b = dv.flatten() if len(dv.shape) > 1 else dv
                cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
                scored.append((trait, cos))
            # Keep only top-2 traits (relative ranking, not absolute threshold)
            scored.sort(key=lambda x: x[1], reverse=True)
            for trait, cos in scored[:2]:
                if cos > 0.55:
                    tags[f"personality_{trait}"] = UserTag(
                        name=f"personality_{trait}",
                        value="high" if cos > 0.72 else "moderate",
                        confidence=min(0.9, cos * 1.1),
                        source="L2_BGE",
                    )
        except Exception as e:
            # Fallback: keyword matching
            logger.debug("BGE personality skip, falling back to keywords (%s)", e)
            for trait, keywords in self.PERSONALITY_TRAITS.items():
                matches = sum(1 for kw in keywords if kw.lower() in user_text.lower())
                if matches >= 2:
                    tags[f"personality_{trait}"] = UserTag(
                        name=f"personality_{trait}",
                        value="high" if matches >= 4 else "moderate" if matches >= 2 else "low",
                        confidence=min(0.9, 0.5 + matches * 0.1),
                        source="L2",
                    )

        return tags

    def acquire_all(self, user_text: str, system_response: str = "",
                    turn_count: int = 1, corrections: int = 0) -> Tuple[
                        Dict[str, UserTag], dict]:
        """L1 + L2 combined. Returns (tags, track_a_observation)."""
        tags = {}
        tags.update(self.acquire_l1(user_text))
        tags.update(self.acquire_l2(user_text, system_response, turn_count, corrections))

        obs = {
            "self_affirmation_count": self._self_affirm_count,
            "total_turns": self._response_count,
        }
        return tags, obs

    @property
    def accumulated_obs(self) -> dict:
        return {
            "self_affirmation_count": self._self_affirm_count,
            "total_turns": self._response_count,
        }


# ═══════════════════ g-Factor Inference ═══════════════════

    def infer_from_trace(self, trace, profile=None):
        """Infer personality from ExecutionTrace transition signals."""
        if trace is None: return {}
        m = trace.meta_analyze()
        rd = m.get("reason_distribution", {})
        s, w = rd.get("strengthen", 0), rd.get("weaken", 0)
        total = max(1, sum(rd.values()))
        tags = {}
        if s >= 3:
            from .models import UserTag
            tags["personality_analytical"] = UserTag("personality_analytical",
                confidence=min(0.9, s/total*3), source="trace_strengthen")
        if w >= 3:
            from .models import UserTag
            tags["personality_emotional"] = UserTag("personality_emotional",
                confidence=min(0.9, w/total*3), source="trace_weaken")
        if profile:
            for k, v in tags.items():
                profile.track_b[k] = v
        return tags


class GFactorInferencer:
    """g-factor (general cognitive ability) inference.

    Design: design_cognitive_profile_v2.md §2.3.2
    Three methods: indirect inference, embedded task, LLM assessment.
    Phase 1: LLM assessment from dialogue history.
    """

    ASSESSMENT_PROMPT = """Based on the following user dialogue history, assess the user's
cognitive ability level. Consider:

1. Abstract reasoning: does the user understand abstract concepts?
2. Domain transfer: does the user connect ideas across domains?
3. Problem complexity: how complex are the problems they raise?
4. Learning speed: how quickly does the user pick up new concepts?

Return a JSON with:
  - level: one of "low", "medium", "high", "expert"
  - score: float 0.0-1.0
  - reasoning: brief explanation (max 100 chars)

History:
{history}

Return ONLY the JSON, no other text."""

    def __init__(self, llm_provider=None):
        self._provider = llm_provider

    def assess_from_history(self, dialogue_history: List[str]) -> dict:
        """LLM-based g-factor assessment from last N turns."""
        if not self._provider:
            return {"level": "medium", "score": 0.5, "reasoning": "no LLM available"}

        history_text = "\n".join(dialogue_history[-10:])
        prompt = self.ASSESSMENT_PROMPT.format(history=history_text)

        try:
            result = self._provider.generate(prompt, max_tokens=150)
            import json
            parsed = json.loads(result)
            return parsed
        except Exception:
            return {"level": "medium", "score": 0.5, "reasoning": "assessment failed"}

    def build_tag(self, result: dict) -> UserTag:
        """Build UserTag from assessment result."""
        return UserTag(
            name="g_factor",
            value=result.get("level", "medium"),
            confidence=min(0.8, result.get("score", 0.5)),
            source="L2",
        )


# ═══════════════════ TagLayer Manager ═══════════════════

class TagLayerManager:
    """Manages Track B tag acquisition and updates profile.

    Usage:
        mgr = TagLayerManager()
        mgr.process_turn(user_text, system_response, profile)
    """

    def __init__(self):
        self._engine = TagAcquisitionEngine()
        self._gf_inferencer: Optional[GFactorInferencer] = None

    def set_llm(self, provider) -> None:
        self._gf_inferencer = GFactorInferencer(provider)

    def process_turn(self, user_text: str, system_response: str = "",
                     profile: CognitiveProfileV2 = None,
                     turn_count: int = 1) -> Tuple[Dict[str, UserTag], dict]:
        """Process one turn: L1+L2 tag acquisition, return new tags + obs."""
        tags, obs = self._engine.acquire_all(
            user_text, system_response, turn_count,
            corrections=0,  # TODO: track corrections from engine
        )

        # Merge into profile
        if profile:
            for name, tag in tags.items():
                existing = profile.track_b.get(name)
                if existing is None:
                    profile.track_b[name] = tag
                elif tag.confidence > existing.confidence:
                    existing.update_confidence(tag.confidence, tag.source)

        return tags, obs

    def assess_g_factor(self, dialogue_history: List[str],
                        profile: CognitiveProfileV2 = None) -> Optional[UserTag]:
        """Run g-factor assessment (async-compatible)."""
        if not self._gf_inferencer:
            return None
        result = self._gf_inferencer.assess_from_history(dialogue_history)
        tag = self._gf_inferencer.build_tag(result)
        if profile:
            profile.track_b["g_factor"] = tag
        return tag

    @property
    def engine(self) -> TagAcquisitionEngine:
        return self._engine

    def infer_from_trace(self, trace, profile=None):
        """Infer personality from ExecutionTrace transition signals.
        STRENGTHEN=T-type alignment, WEAKEN=F-type mismatch."""
        if trace is None: return {}
        m = trace.meta_analyze()
        rd = m.get("reason_distribution", {})
        s, w = rd.get("strengthen", 0), rd.get("weaken", 0)
        total = max(1, sum(rd.values()))
        tags = {}
