"""ENGINEERING Compliance Layer — bridges existing implementations to v3.0 specs.

Each module maps existing code to the ENGINEERING_*.md interface contract.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


# ═══ PCR (ENGINEERING_PCR.md, 908L) ═══

class PCRBridge:
    """ENGINEERING_PCR §4: PCR → PCROutput interface contract.

    Existing code: pcr/ (11 files, ~4,000L)
    Gap: PCROutput data contract alignment, NoiseSpan integration.
    """

    def __init__(self, router=None, compass=None):
        self._router = router
        self._compass = compass
        self._loaded = False

    def _ensure(self):
        if self._loaded: return
        self._loaded = True
        try:
            from core.agent.pcr_router_v2 import PCRV2Router
            self._router = self._router or PCRV2Router()
        except Exception as e:
            logger.debug("PCRV2Router: %s", e)

    def evaluate(self, text: str) -> dict:
        """ENGINEERING_PCR §5: text → PCROutput fields."""
        self._ensure()
        result = {"expectation": "UNKNOWN", "noise": 0.0, "complexity": 0.0,
                  "metacognition": 0.0, "divergence": 0.0, "stability": 0.0, "confidence": 0.0}
        if self._router:
            try:
                route = self._router.route(text)
                result.update({
                    "expectation": getattr(route, 'zone', 'UNKNOWN'),
                    "complexity": getattr(route, 'x', 0.5),
                })
            except Exception:
                pass
        if self._compass:
            try:
                cr = self._compass.measure(text)
                if "noise_span" in cr.dimensions:
                    ns = cr.dimensions["noise_span"]
                    result["noise"] = ns.get("score", 0.0)
                if "coordinate_3d" in cr.dimensions:
                    cd = cr.dimensions["coordinate_3d"]
                    result["complexity"] = cd.get("y_complexity", 0.0)
            except Exception:
                pass
        return result

    # Gaps (documented, not yet implemented):
    # - NoiseSpan ENGINEERING_PCR §3.2 integration
    # - CognitiveQuickScan ENGINEERING_PCR §3.3
    # - RouteDecision ENGINEERING_PCR §3.4


# ═══ INTENT (ENGINEERING_INTENT_PARSER.md, 910L) ═══

class IntentBridge:
    """ENGINEERING_INTENT_PARSER §4: IntentParser → Intent data contract.

    Existing code: intent/ (8 files, ~1,200L)
    Gap: IntentCategory enum alignment, EntityType standardization.
    """

    def __init__(self, splitter=None):
        self._splitter = splitter
        self._loaded = False

    def _ensure(self):
        if self._loaded: return
        self._loaded = True
        try:
            from core.agent.intent.multi_intent_splitter import MultiIntentSplitter
            self._splitter = self._splitter or MultiIntentSplitter()
        except Exception as e:
            logger.debug("MultiIntentSplitter: %s", e)

    def parse(self, text: str) -> dict:
        """ENGINEERING_INTENT_PARSER §5: text → Intent contract."""
        self._ensure()
        result = {"category": "UNKNOWN", "confidence": 0.0, "entities": [],
                  "sub_intents": [], "ambiguities": []}
        if self._splitter:
            try:
                sr = self._splitter.split(text)
                result["category"] = "MULTI" if sr.multi else "SINGLE"
                result["confidence"] = sr.confidence
                result["sub_intents"] = [{"text": s.text, "confidence": sr.confidence}
                                         for s in getattr(sr, 'sub_intents', []) or []]
            except Exception:
                pass
        return result

    # Gaps:
    # - Entity extraction (ENGINEERING_INTENT_PARSER §5.2)
    # - Ambiguity detection (ENGINEERING_INTENT_PARSER §5.3)
    # - TaskGraph generation (ENGINEERING_INTENT_PARSER §6)


# ═══ PLANNING (ENGINEERING_PLANNING_SKILL.md, 1,642L) ═══

class PlanningBridge:
    """ENGINEERING_PLANNING_SKILL §4: Planner → TaskGraph + Blueprint.

    Existing code: planner/ (28 files, 7,908L)
    Gap: Blueprint engine (designed, code zero), StrategySelector integration.
    """

    def __init__(self, planner=None, strategy_selector=None):
        self._planner = planner
        self._selector = strategy_selector
        self._loaded = False

    def _ensure(self):
        if self._loaded: return
        self._loaded = True
        try:
            from core.agent.planner.llm_planner import LLMPlanner
            self._planner = self._planner or LLMPlanner()
        except Exception as e:
            logger.debug("LLMPlanner: %s", e)

    def plan(self, intent: dict, pcr_output: dict, context: dict = None) -> dict:
        """ENGINEERING_PLANNING_SKILL §5: intent + PCR → TaskGraph."""
        self._ensure()
        result = {"steps": [], "blueprint": "RULE_BASED", "confidence": 0.5}
        if self._planner:
            try:
                plan = self._planner.plan(intent.get("sub_intents", [{}])[0].get("text", ""))
                result["steps"] = plan.get("steps", [])
                result["blueprint"] = plan.get("strategy", "RULE_BASED")
                result["confidence"] = plan.get("confidence", 0.5)
            except Exception:
                pass
        return result

    def select_strategy(self, complexity: float, expectation: str) -> str:
        """ENGINEERING_PLANNING_SKILL §3: complexity → strategy selection."""
        if complexity < 0.3: return "RULE_BASED"
        if complexity < 0.6: return "TEMPLATE"
        if complexity < 0.8: return "HYBRID"
        return "LLM_DRIVEN"

    # Gaps:
    # - Blueprint engine (BLUEPRINT_SYSTEM, code zero) — P0
    # - Skill lifecycles (DistillationEngine, existing code in planner/)
    # - CognitiveScheduler integration (existing code by not wired)
