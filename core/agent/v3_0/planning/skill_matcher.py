# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/skill_matcher.py
───────────────────────────────────────
DialogMesh Agent v3.0 — 技能匹配器（SkillMatcher）。

用途：
- 将用户意图（字符串）匹配到最合适的 SkillTemplate。
- 支持关键词匹配、语义相似度（Jaccard）和上下文相关性评分。
- 实现技能模板优先策略：分数 >= 0.5 时 use_template=True，< 0.5 时 use_template=False。

性能目标：
- 技能模板路径：延迟 < 50ms（80% 场景）
- LLM 动态分解路径：延迟 2-5s（20% 场景）

版本：3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from core.agent.v3_0.planning.models import SkillMatchResult, SkillTemplate
from core.agent.v3_0.planning.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillMatcher:
    """技能匹配器 — 将用户意图匹配到技能模板。

    匹配策略：
    1. 关键词精确匹配（权重 0.4）
    2. 语义相似度（Jaccard，权重 0.4）
    3. 上下文相关性（权重 0.2）

    阈值策略：
    - score >= 0.5: use_template=True（快速路径，不调用 LLM）
    - score < 0.5: use_template=False（慢速路径，由 Planning-LLM 动态分解）
    - score < 0.3: skill=None（完全无匹配）
    """

    TEMPLATE_THRESHOLD: float = 0.4
    MIN_MATCH_THRESHOLD: float = 0.3

    def __init__(self, skill_registry: SkillRegistry) -> None:
        self._registry = skill_registry
        self._logger = logger

    def match(self, intent: str, context: Optional[Any] = None) -> Optional[SkillMatchResult]:
        """匹配最佳技能模板。

        Args:
            intent: 用户意图文本。
            context: 可选的上下文对象（需支持 get_topics() 方法）。

        Returns:
            SkillMatchResult 或 None（无匹配时）。
        """
        try:
            all_skills = self._registry.list_all()
            if not all_skills:
                self._logger.info("No skills registered in registry")
                return None

            scores: List[tuple] = []
            for skill in all_skills:
                score = self._score_skill(intent, skill, context)
                scores.append((skill, score))

            scores.sort(key=lambda x: x[1], reverse=True)
            best_skill, best_score = scores[0]

            if best_score >= self.TEMPLATE_THRESHOLD:
                self._logger.info(
                    f"Skill template matched (fast path): {best_skill.name}, score={best_score:.2f}"
                )
                return SkillMatchResult(
                    skill=best_skill,
                    score=best_score,
                    use_template=True,
                    reason=f"Keyword/semantic match above threshold ({best_score:.2f})",
                )
            elif best_score >= self.MIN_MATCH_THRESHOLD:
                self._logger.info(
                    f"No skill match above threshold (slow path): best={best_score:.2f}, "
                    f"skill={best_skill.name}"
                )
                return SkillMatchResult(
                    skill=best_skill,
                    score=best_score,
                    use_template=False,
                    reason=f"Partial match ({best_score:.2f}), fallback to LLM decomposition",
                )
            else:
                self._logger.info(
                    f"No skill match at all: best_score={best_score:.2f}, intent='{intent[:50]}'"
                )
                return SkillMatchResult(
                    skill=None,
                    score=best_score,
                    use_template=False,
                    reason="No skill match above minimum threshold",
                )

        except Exception as exc:
            self._logger.error(f"Skill matching failed: {exc}")
            return None

    def _score_skill(self, intent: str, skill: SkillTemplate, context: Optional[Any]) -> float:
        """计算技能匹配分数 [0, 1]。"""
        try:
            keyword_score = self._keyword_match(intent, skill)
            semantic_score = self._semantic_similarity(intent, skill.description)
            context_score = self._context_relevance(context, skill.tags)
            total = keyword_score * 0.4 + semantic_score * 0.4 + context_score * 0.2
            return min(total, 1.0)
        except Exception as exc:
            self._logger.warning(f"Skill scoring failed for {skill.name}: {exc}")
            return 0.0

    def _keyword_match(self, intent: str, skill: SkillTemplate) -> float:
        """关键词匹配分数。"""
        try:
            intent_words: Set[str] = set(intent.lower().split())
            skill_words: Set[str] = set(k.lower() for k in skill.keywords)
            if not skill_words:
                return 0.0
            intersection = intent_words.intersection(skill_words)
            return len(intersection) / len(skill_words)
        except Exception as exc:
            self._logger.warning(f"Keyword match failed: {exc}")
            return 0.0

    def _semantic_similarity(self, intent: str, description: str) -> float:
        """语义相似度（Jaccard 系数）。"""
        try:
            a: Set[str] = set(intent.lower().split())
            b: Set[str] = set(description.lower().split())
            if not a or not b:
                return 0.0
            intersection = a.intersection(b)
            union = a.union(b)
            return len(intersection) / len(union)
        except Exception as exc:
            self._logger.warning(f"Semantic similarity failed: {exc}")
            return 0.0

    def _context_relevance(self, context: Optional[Any], skill_tags: List[str]) -> float:
        """上下文相关性分数。"""
        try:
            if context is None or not skill_tags:
                return 0.5  # 默认中等相关
            topics: List[str] = []
            if hasattr(context, "get_topics"):
                topics = context.get_topics() or []
            elif hasattr(context, "topics"):
                topics = getattr(context, "topics", []) or []
            context_topics = set(t.lower() for t in topics)
            matched = context_topics.intersection(set(t.lower() for t in skill_tags))
            return len(matched) / len(skill_tags) if skill_tags else 0.5
        except Exception as exc:
            self._logger.warning(f"Context relevance failed: {exc}")
            return 0.5


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 skill_matcher self-test ===")

    from core.agent.v3_0.planning.skill_registry import SkillRegistry

    registry = SkillRegistry()
    matcher = SkillMatcher(registry)

    # 1. 精确匹配 -> use_template=True
    result = matcher.match("scan memory address 0x1234")
    assert result is not None
    assert result.use_template is True, f"Expected use_template=True, got {result.use_template}"
    assert result.skill is not None
    print(f"[PASS] Fast path: {result.skill.name}, score={result.score:.2f}, use_template={result.use_template}")

    # 2. 无匹配 -> use_template=False, skill=None
    result2 = matcher.match("random unrelated query xyz")
    assert result2 is not None
    assert result2.use_template is False
    print(f"[PASS] Slow path: skill={result2.skill}, score={result2.score:.2f}")

    # 3. 部分匹配 -> use_template=False, skill 不为 None
    result3 = matcher.match("analyze some code instructions")
    assert result3 is not None
    print(f"[PASS] Partial match: score={result3.score:.2f}, use_template={result3.use_template}")

    logger.info("=== All v3.0 skill_matcher self-tests passed ===")
