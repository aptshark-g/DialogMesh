"""PerspectivePlanner — intent-to-perspective decision layer.

Design: docs/v3.0/DESIGN_PERSPECTIVE_PLANNER.md §4

Decides HOW to observe before deciding WHAT to retrieve.
Strategy selection: architecture | execution | engineering | evolution.
Plugs in between intent parsing and context compilation.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from core.agent.v4.compiler.view_manager import ViewManager

logger = logging.getLogger(__name__)


class Horizon:
    """Continuous depth control for information expansion."""

    def __init__(self, depth: int = 2, budget: int = 1800,
                 strategy: str = "structural_summary"):
        self.depth = depth
        self.budget = budget
        self.strategy = strategy

    def __repr__(self):
        return f"Horizon(d={self.depth} b={self.budget} s={self.strategy})"


class Perspective:
    """Complete observation plan for one turn."""

    def __init__(self):
        self.strategy: str = "architecture"
        self.horizon: Horizon = Horizon()
        self.targets: List[str] = []
        self.world: str = "knowledge"
        self.domains: Dict[str, float] = {"K": 0.5, "C": 0.2, "E": 0.15, "B": 0.1, "P": 0.05}
        self.token_budget: int = 1800

    def __repr__(self):
        return (f"Perspective({self.strategy} {self.horizon} "
                f"targets={self.targets[:3]} world={self.world})")


class PerspectivePlanner:
    """Intent → Perspective three-layer decision.

    Layer 1: Strategy selection (architecture|execution|engineering|evolution)
    Layer 2: Horizon calculation (continuous depth from token budget)
    Layer 3: Domain allocation (derived from perspective, not independent)
    """

    # Domain allocation by expectation type (PCR output)
    # Design: DESIGN_FULL_CONCEPT §2.2.2, DESIGN_PERSPECTIVE_PLANNER §4.3
    _EXPECTATION_DOMAINS = {
        "TOOL":      {"K": 0.50, "C": 0.10, "E": 0.20, "B": 0.15, "P": 0.05},
        "ADVISOR":   {"K": 0.40, "C": 0.25, "E": 0.15, "B": 0.10, "P": 0.10},
        "COMPANION": {"K": 0.15, "C": 0.45, "E": 0.05, "B": 0.15, "P": 0.20},
        "UNKNOWN":   {"K": 0.35, "C": 0.25, "E": 0.20, "B": 0.12, "P": 0.08},
    }

    # Strategy by expectation
    _EXPECTATION_STRATEGY = {
        "TOOL":      "engineering",
        "ADVISOR":   "architecture",
        "COMPANION": "evolution",
    }

    # Strategy keywords (fallback when expectation is UNKNOWN)
    _STRATEGY_MAP = [
        (["为什么", "原因", "动机", "背景", "历史", "演变", "之前", "为什么这么设计"], "evolution"),
        (["代码", "函数", "class", "实现", "method", "源码"], "engineering"),
        (["流程", "执行", "pipeline", "怎么跑", "运行", "调度", "步骤"], "execution"),
        (["架构", "设计", "整体", "是什么", "结构", "概览", "介绍", "了解"], "architecture"),
    ]

    # BGE strategy descriptions for semantic matching
    _STRATEGY_DESCRIPTIONS = None  # loaded from soft_config

    def __init__(self):
        self._bge = None
        self._meta = None


    def _ensure_descriptions(self):
        """Lazy-load strategy descriptions from soft_config."""
        if PerspectivePlanner._STRATEGY_DESCRIPTIONS is not None:
            return
        try:
            from core.agent.v4.compiler.soft_config import load_perspective_config
            cfg = load_perspective_config()
            PerspectivePlanner._STRATEGY_DESCRIPTIONS = {
                k: v.get("description", k) for k, v in cfg.items()
            }
        except Exception:
            PerspectivePlanner._STRATEGY_DESCRIPTIONS = {
                "architecture": "系统架构设计",
                "evolution": "历史演变原因",
                "engineering": "代码实现细节",
                "execution": "运行流程步骤",
            }


    def set_metacognition(self, mc):
        """Optional: use MetaCognition (LLM) for perspective decisions."""
        self._meta = mc


    def _ensure_bge(self):
        if self._bge is not None:
            return
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            self._bge = SemanticEncoder()
        except Exception:
            self._bge = False


    def _bge_select_strategy(self, text: str) -> str:
        """BGE semantic strategy selection (replaces keyword fallback).

        Also detects command/action patterns before BGE lookup.
        """
        import numpy as np
        self._ensure_bge()
        self._ensure_descriptions()

        # Quick PCR: detect command-like patterns
        cmd_patterns = ["book", "add", "set", "send", "play", "create", "delete", "open", "start"]
        question_patterns = ["what", "who", "how", "why", "tell", "explain", "what's", "is there"]
        if any(text.lower().startswith(p) for p in cmd_patterns):
            return "engineering"  # TOOL → command execution
        if any(text.lower().startswith(p) for p in question_patterns):
            return "evolution"    # COMPANION → information seeking

        if not self._bge or self._bge is False:
            return self._select_strategy(text)  # fallback to keywords

        try:
            qv = self._bge.encode(text)
            best_strat, best_cos = "architecture", 0.0
            # Detect language: use English descriptions for English queries
            is_english = any(ch.isascii() and ch.isalpha() for ch in text[:20])
            for strat, desc in self._STRATEGY_DESCRIPTIONS.items():
                # Append English description when query is English
                if is_english:
                    en_descs = {
                        "architecture": "system architecture design, module relationships",
                        "evolution": "historical changes, design decisions, reasons",
                        "engineering": "code implementation, functions, technical details",
                        "execution": "pipeline execution, step by step process",
                    }
                    desc = desc + " " + en_descs.get(strat, "")
                dv = self._bge.encode(desc)
                cos = float(np.dot(qv, dv) / (np.linalg.norm(qv) * np.linalg.norm(dv) + 1e-8))
                if cos > best_cos:
                    best_cos, best_strat = cos, strat
            return best_strat
        except Exception:
            return self._select_strategy(text)

    # Depth base by strategy
    _DEPTH_BASE = {
        "architecture": 2,
        "execution": 3,
        "engineering": 4,
        "evolution": 2,
    }

    # Domain allocation by strategy
    _DOMAIN_ALLOC = {
        "architecture": {"K": 0.50, "C": 0.15, "E": 0.15, "B": 0.10, "P": 0.10},
        "execution":   {"K": 0.35, "C": 0.15, "E": 0.30, "B": 0.15, "P": 0.05},
        "engineering": {"K": 0.20, "C": 0.10, "E": 0.50, "B": 0.10, "P": 0.10},
        "evolution":   {"K": 0.40, "C": 0.25, "E": 0.10, "B": 0.15, "P": 0.10},
    }

    # World by strategy
    _WORLD_MAP = {
        "architecture": "design",
        "execution": "knowledge",
        "engineering": "code",
        "evolution": "design",
    }

    def plan(self, text: str, token_budget: int = 2000,
             view_manager: Optional[ViewManager] = None,
             expectation: str = "UNKNOWN") -> Perspective:
        """Plan a perspective from user text + PCR expectation.

        Args:
            text: user query text
            token_budget: total token budget available
            view_manager: optional, for persistent view continuation
            expectation: PCR expectation type (TOOL/ADVISOR/COMPANION/UNKNOWN)
        """
        p = Perspective()
        p.token_budget = token_budget

        # Layer 1: Strategy — PCR expectation → BGE semantic → keyword fallback
        expect = expectation.upper() if expectation else "UNKNOWN"
        if expect in self._EXPECTATION_STRATEGY:
            p.strategy = self._EXPECTATION_STRATEGY[expect]
            logger.debug("PerspectivePlanner PCR: %s → %s", expect, p.strategy)
        elif self._meta:
            # MetaCognition (LLM) when available
            from core.agent.v4.cognitive.workspace import CognitiveWorkspace
            ws = CognitiveWorkspace(id="persp", goal=text)
            ref = self._meta.reflect(ws)
            strat_map = {"RETRIEVE":"architecture","EXPAND":"engineering","REASON":"evolution","COMMIT":"execution"}
            p.strategy = strat_map.get(ref.next_action, "architecture")
            logger.info("PerspectivePlanner MetaCognition: %s → %s", ref.next_action, p.strategy)
        else:
            # BGE semantic similarity (replaces keyword fallback)
            p.strategy = self._bge_select_strategy(text)
            logger.debug("PerspectivePlanner BGE: '%s' → %s", text[:40], p.strategy)

        # Layer 2: Horizon from token budget
        base_depth = self._DEPTH_BASE.get(p.strategy, 2)
        affordable = 1
        cumulative = 200
        for d in range(2, 6):
            cumulative += 150 * d
            if cumulative <= token_budget * 0.6:
                affordable = d
        p.horizon = Horizon(
            depth=min(base_depth, affordable),
            budget=token_budget,
            strategy="structural_summary" if affordable < base_depth else "full_content",
        )

        # Layer 3: Domain allocation — from expectation type
        p.domains = dict(self._EXPECTATION_DOMAINS.get(expect, self._EXPECTATION_DOMAINS["UNKNOWN"]))

        # World
        p.world = self._WORLD_MAP.get(p.strategy, "knowledge")

        # Targets: extract key concepts from query
        p.targets = self._extract_targets(text)

        logger.info("PerspectivePlanner: %s (expect=%s)", p, expect)
        return p

    def plan_multi(self, text: str, token_budget: int = 2000,
                   expectation: str = "UNKNOWN") -> List[Perspective]:
        """Return primary + secondary perspectives for multi-view rendering.

        Primary: full depth at primary strategy
        Secondary: shallow (LOD=1) views from other strategies
        """
        perspectives = []
        primary = self.plan(text, token_budget, expectation=expectation)
        perspectives.append(primary)

        # Select one complementary secondary strategy
        all_strategies = ["architecture", "execution", "engineering", "evolution"]
        remain = [s for s in all_strategies if s != primary.strategy]
        if not remain:
            return perspectives

        # Pick most complementary: architecture↔engineering, execution↔evolution
        complement = {"architecture": "engineering", "engineering": "architecture",
                      "execution": "evolution", "evolution": "execution"}
        secondary_strat = complement.get(primary.strategy, remain[0])

        # Copy primary, override strategy, keep shallow horizon
        secondary = Perspective()
        secondary.strategy = secondary_strat
        secondary.horizon = Horizon(depth=1, budget=token_budget // 5,
                                    strategy="structural_summary")
        secondary.targets = primary.targets
        secondary.world = self._WORLD_MAP.get(secondary_strat, "knowledge")
        # Domain allocation follows secondary strategy
        sec_expect = {"architecture": "ADVISOR", "engineering": "TOOL",
                      "execution": "ADVISOR", "evolution": "COMPANION"}.get(secondary_strat, "UNKNOWN")
        secondary.domains = dict(self._EXPECTATION_DOMAINS.get(sec_expect,
                                    self._EXPECTATION_DOMAINS["UNKNOWN"]))
        secondary.token_budget = token_budget // 5
        perspectives.append(secondary)

        logger.info("PerspectivePlanner multi: primary=%s secondary=%s",
                    primary.strategy, secondary.strategy)
        return perspectives

    def _select_strategy(self, text: str) -> str:
        """Pick observation strategy from query keywords."""
        text_lower = text.lower()
        for keywords, strategy in self._STRATEGY_MAP:
            if any(kw in text_lower for kw in keywords):
                return strategy
        return "architecture"

    @staticmethod
    def _extract_targets(text: str) -> List[str]:
        """Extract anchor concept names from query."""
        targets = []
        import re
        # CamelCase patterns (case-insensitive)
        for m in re.finditer(r'\b[A-Za-z][a-z]+(?:[A-Z][a-z]+)+\b', text):
            targets.append(m.group())
        # Quoted phrases
        for m in re.finditer(r'["\'""]([^"\'"」]+)["\'"」]', text):
            targets.append(m.group(1))
        # Chinese concept names
        for m in re.finditer(r'[\u4e00-\u9fff]{2,6}(?:编译器|管理器|选择器|分配器|引擎|工厂|适配器|路由器|解析器)', text):
            targets.append(m.group())
        return targets[:5]
