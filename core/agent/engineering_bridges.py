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
            from core.agent.pcr_router_v2 import PCRRouterV2
            self._router = self._router or PCRRouterV2()
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


# ═══ CONTEXT_MANAGER (ENGINEERING_CONTEXT_MANAGER.md, 880L) ═══

class ContextManagerBridge:
    """ENGINEERING_CONTEXT_MANAGER §5: Hot/Warm/Cold context assembly.

    Existing: UnifiedContext + context/ pipeline. DiscourseManager isolated (v3 legacy).
    """

    def __init__(self, unified_context=None):
        self._ctx = unified_context

    def _ensure(self):
        if self._ctx is None:
            try:
                from core.agent.assembly.unified_context import UnifiedContext
                self._ctx = UnifiedContext()
            except Exception:
                pass

    def get_hot_context(self, session_id: str, turns: int = 5) -> list:
        self._ensure()
        return getattr(self._ctx, '_hot_turns', []) if self._ctx else []

    def get_warm_context(self, session_id: str, topic: str = None) -> list:
        return []  # Warm layer: SQLite retrieval (existing in persistence/)

    def get_cold_context(self, key: str) -> dict:
        return {}  # Cold layer: archived data

    def assemble(self, perception: dict, budget: int = 2000) -> dict:
        self._ensure()
        return self._ctx.assemble(perception, budget) if self._ctx else {"dialogue_context": ""}


# ═══ TOOL_REGISTRY (ENGINEERING_TOOL_REGISTRY.md, 1,217L) ═══

class ToolRegistryBridge:
    """ENGINEERING_TOOL_REGISTRY §4: ToolRegistry → ToolSchema contract.

    Existing: tool_registry/ (10 files, 3,442L) — complete implementation.
    """

    def __init__(self):
        self._registry = None

    def _ensure(self):
        if self._registry is None:
            try:
                from core.agent.tool_registry.registry import ToolRegistry
                self._registry = ToolRegistry()
            except Exception:
                pass

    def list_tools(self, tags: list = None) -> list:
        self._ensure()
        return getattr(self._registry, 'list_all', lambda: [])() if self._registry else []

    def register(self, definition: dict) -> bool:
        self._ensure()
        try:
            if self._registry and hasattr(self._registry, 'register_sync'):
                self._registry.register_sync(definition)
                return True
        except Exception:
            pass
        return False

    def discover(self, query: str) -> list:
        return []  # Dynamic discovery (existing code, needs wiring)


# ═══ SERVICE_LAYER (ENGINEERING_SERVICE_LAYER.md, 1,522L) ═══

class ServiceLayerBridge:
    """ENGINEERING_SERVICE_LAYER §4: WebSocket + HTTP + Auth service layer.

    Existing: api/ (5f, 2,868L) + service/ (17f, 3,680L).
    """

    @staticmethod
    def health() -> dict:
        try:
            from core.agent.service.http_controller import ServiceController
            return ServiceController().health()
        except Exception:
            return {"status": "service_layer_not_loaded"}

    @staticmethod
    def is_running(port: int = 8000) -> bool:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            s.connect(('127.0.0.1', port))
            s.close()
            return True
        except Exception:
            return False


# ═══ COGNITIVE_PROFILE (ENGINEERING_COGNITIVE_PROFILE_V2.md, 2,035L) ═══

class CognitiveProfileBridge:
    """ENGINEERING_COGNITIVE_PROFILE_V2 §5: dual-track OCEAN + BFI + Dynamics.

    Existing: v4/cognitive/OCEANProfile + BFIGenerator + dynamics (bridge wired).
    """

    def __init__(self):
        self._ocean = None
        self._bfi = None
        self._dynamics = None

    def _ensure(self):
        if self._ocean is None:
            try:
                from core.agent.v4.cognitive.profile_ocean import OCEANProfile
                self._ocean = OCEANProfile()
            except Exception:
                pass
        if self._bfi is None:
            try:
                from core.agent.v4.cognitive.profile_bfi import BFIGenerator
                self._bfi = BFIGenerator()
            except Exception:
                pass
        if self._dynamics is None:
            try:
                from core.agent.v4.cognitive.dynamics import DynamicsComputer
                self._dynamics = DynamicsComputer()
            except Exception:
                pass

    def get_profile(self) -> dict:
        self._ensure()
        return {
            "ocean": getattr(self._ocean, 'get_profile', lambda: {})() if self._ocean else {},
            "bfi": getattr(self._bfi, 'generate', lambda: {})() if self._bfi else {},
            "dynamics": getattr(self._dynamics, 'tick', lambda: {})() if self._dynamics else {},
        }

    def update_from_route(self, route: dict):
        self._ensure()
        if self._ocean and hasattr(self._ocean, 'apply_pcr_route'):
            self._ocean.apply_pcr_route(route)


# ═══ TOPIC_TREE (ENGINEERING_TOPIC_TREE.md, 910L) ═══

class TopicTreeBridge:
    """ENGINEERING_TOPIC_TREE §4: TopicTree V2 → cohesive topic graph.

    Existing: topic_tree/manager_v2.py (1,091L).
    """

    def __init__(self):
        self._tree = None

    def _ensure(self):
        if self._tree is None:
            try:
                from core.agent.topic_tree.manager_v2 import TopicTreeManagerV2
                self._tree = TopicTreeManagerV2()
                self._tree.activate([])
            except Exception:
                pass

    def get_current_branch(self) -> list:
        self._ensure()
        return getattr(self._tree, 'get_active_path', lambda: [])() if self._tree else []

    def get_summary(self, level: int = 2) -> dict:
        # T3: V2 真数据（此前恒 {}）
        self._ensure()
        if self._tree is None:
            return {}
        return self._tree.get_tree_summary()


# ═══ OBSERVABILITY (ENGINEERING_OBSERVABILITY.md, 865L) ═══

class ObservabilityBridge:
    """ENGINEERING_OBSERVABILITY §4: Metrics + Logger + Tracer + Alert.

    Existing: observability/ (merged from v3_common metrics.py).
    """

    @staticmethod
    def record_latency(chain: str, ms: float):
        try:
            from core.agent.observability.metrics import Metrics
            Metrics.record_latency(chain, ms)
        except Exception:
            pass

    @staticmethod
    def get_snapshot() -> dict:
        try:
            from core.agent.observability.metrics import Metrics
            return Metrics.snapshot()
        except Exception:
            return {"error": "metrics_not_available"}


# ═══ BEHAVIOR_GRAPH (ENGINEERING_V3_3_BEHAVIOR_GRAPH.md, 908L) ═══

class BehaviorGraphBridge:
    """ENGINEERING_V3_3_BEHAVIOR_GRAPH §4: BehaviorChain + BehaviorGraph.

    Existing: behavior/ (16 files, 1,728L).
    """

    def __init__(self):
        self._engine = None

    def _ensure(self):
        if self._engine is None:
            try:
                from core.agent.behavior.llm_collaborative import BehaviorLLMCollaborator
                self._engine = BehaviorLLMCollaborator()
            except Exception:
                pass

    def record_observation(self, pattern: dict):
        self._ensure()
        if self._engine and hasattr(self._engine, 'record_observation'):
            self._engine.record_observation(pattern)

    def get_patterns(self) -> list:
        self._ensure()
        return getattr(self._engine, 'get_patterns', lambda: [])() if self._engine else []
