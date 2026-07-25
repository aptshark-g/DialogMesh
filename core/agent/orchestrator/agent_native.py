"""Agent-Native Orchestrator — LLM-driven full pipeline coordination.

Pipeline: PCR V2 → MultiIntent → L4 Temporal → Behavior → Planner → Engineering.
LLM is the coordinator: routes, plans, and adapts.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """LLM-driven agent orchestrator — full pipeline coordination.

    Integrates all current modules: PCR V2, MultiIntent, L4, Behavior, Engineering.
    LLM is the coordinator — receives structured context, makes routing decisions.

    Usage:
        orch = AgentOrchestrator(pcr_router, intent_splitter, l4_engine, 
                                  behavior_collab, engineering_chain, llm)
        result = await orch.process("先定位延迟，然后修复")
    """

    def __init__(self, pcr_router=None, intent_splitter=None, l4_engine=None,
                 behavior_collab=None, engineering_chain=None, llm=None,
                 discourse_tree=None, cognitive_bridge=None, event_log=None,
                 context_assembly=None, cognition_hub=None):
        self.pcr = pcr_router
        self.intent = intent_splitter
        self.l4 = l4_engine
        self.behavior = behavior_collab
        self.engineering = engineering_chain
        self.llm = llm
        self.discourse = discourse_tree
        self.cognitive = cognitive_bridge or self._try_load_bridge()
        self._event_log = event_log
        self._context_assembly = context_assembly or self._try_load_context()
        self._cognition_hub = cognition_hub or self._try_load_cognition()
        self._tick = 0

    def _publish(self, kind: str, payload: dict):
        """Fire-and-forget publish to EventLog. 不阻塞热路径."""
        if self._event_log:
            try:
                self._tick += 1
                eid = f"{kind}_{self._tick}_{int(time.time()*1000)}"
                self._event_log.put_event(eid, kind, payload)
            except Exception:
                pass

    def process(self, text: str, session_id: str = "default") -> dict:
        """Full pipeline: PCR → Intent → L4 → Behavior → Engineering → Plan.

        Returns: {route, intents, temporal_pred, behavior_insight, tools, plan}
        """
        import time
        start = time.time()
        result = {"text": text, "session": session_id}

        # 1. PCR V2 — cognitive routing
        if self.pcr:
            try:
                route = self.pcr.route(text)
                result["route"] = {
                    "zone": getattr(route, 'zone', 'MIXED'),
                    "x": getattr(route, 'x', 0.5),
                    "y": getattr(route, 'y', 0.5),
                    "z": getattr(route, 'z', 0.0),
                }
                # === Cognitive: PCR → OceanProfile ===
                if self.cognitive:
                    self.cognitive.on_pcr_route(result["route"])
                self._publish("PCR_COMPUTED", result["route"])
            except Exception as e:
                logger.debug("PCR failed: %s", e)
                result["route"] = {"zone": "MIXED", "error": str(e)}

        # 2. MultiIntent — split if needed
        if self.intent:
            try:
                split_result = self.intent.split(text)
                result["intents"] = {
                    "multi": split_result.multi,
                    "segments": [s.text for s in split_result.segments],
                    "confidence": split_result.confidence,
                }
                self._publish("INTENT_PARSED", result["intents"])
            except Exception as e:
                logger.debug("Intent split failed: %s", e)
                result["intents"] = {"multi": False, "segments": [text]}

        # 3. L4 Temporal — predict next intent
        if self.l4:
            try:
                current_intent = result.get("intents", {}).get("segments", [text])[0]
                preds = self.l4.predict_next(current_intent)
                result["temporal"] = {
                    "predictions": [(p[0], round(p[1], 2)) for p in preds],
                    "anomaly": None,
                }
                # Check drift
                intent_dist = {current_intent: 1.0}
                drift = self.l4.check_drift(intent_dist)
                if drift:
                    result["temporal"]["drift"] = {
                        "magnitude": round(drift.magnitude, 3),
                        "cause": drift.likely_cause,
                    }
            except Exception as e:
                logger.debug("L4 failed: %s", e)

        # === Cognitive: L4 → BeliefMap ===
        if self.cognitive:
            preds = result.get("temporal", {}).get("predictions", [])
            drift = result.get("temporal", {}).get("drift")
            self.cognitive.on_temporal_predict(preds, drift)
            if result.get("temporal"):
                self._publish("L4_PREDICTED", result["temporal"])

        # 4. Behavior — insight
        if self.behavior:
            try:
                result["behavior"] = {"available": True}
            except Exception:
                result["behavior"] = {"available": False}

        # === Cognitive: Behavior → Pattern Learner ===
        if self.cognitive:
            self.cognitive.on_behavior_update(result.get("behavior", {}))
        if result.get("behavior"):
            self._publish("BEHAVIOR_RECORDED", result["behavior"])

        # === CONTEXT: ContextAssembly — compile subgraph ===
        if self._context_assembly:
            try:
                ctx_result = self._context_assembly.assemble(result)
                result["context"] = {
                    "dialogue": ctx_result.get("dialogue_context", ""),
                    "meta": ctx_result.get("meta_context", ""),
                    "stats": ctx_result.get("stats", {}),
                }
                self._publish("CONTEXT_COMPILED", result["context"].get("stats", {}))
            except Exception as e:
                logger.debug("Context assembly failed: %s", e)

        # 5. Engineering — tool feasibility
            try:
                state = self.engineering.snapshot()
                feasibility = self.engineering.check_feasibility(text, state)
                result["tools"] = {
                    "total": feasibility["total_tools"],
                    "matching": feasibility["matching_tools"],
                    "feasible": feasibility["feasible"],
                }
                self._publish("TOOLS_CHECKED", result["tools"])
            except Exception as e:
                logger.debug("Engineering failed: %s", e)

        # 6. LLM Synthesis — master coordination
        if self.llm:
            # === Cognitive: build context for LLM ===
            if self.cognitive:
                cognitive_ctx = self.cognitive.build_llm_context()
                result["cognitive"] = cognitive_ctx
                self.cognitive.tick()
            result["plan"] = self._llm_synthesize(result)
            self._publish("PLAN_GENERATED", result.get("plan", {}))

        # === COGNITION: convergent hub — Match→Vote→Decay→Resolve ===
        if self._cognition_hub and self._cognition_hub.is_loaded:
            try:
                cog_result = self._cognition_hub.converge()
                result["cognition"] = cog_result
            except Exception as e:
                logger.debug("Cognition hub failed: %s", e)

        result["latency_ms"] = round((time.time() - start) * 1000)
        return result

    def _llm_synthesize(self, context: dict) -> dict:
        """LLM receives full pipeline context → makes coordinated plan."""
        import json
        
        ctx = {
            "user_message": context["text"],
            "cognitive_route": context.get("route", {}),
            "intents": context.get("intents", {}),
            "temporal_predictions": context.get("temporal", {}).get("predictions", []),
            "available_tools": context.get("tools", {}).get("total", 0),
            "cognitive_context": context.get("cognitive", {}),
            "assembled_context": context.get("context", {}).get("dialogue", "")[:1000],
        }

        prompt = f"""You are an agent coordinator. Based on the pipeline analysis, create an execution plan.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Output a JSON execution plan:
{{"steps": [{{"action": "name", "tool": "tool_name", "reason": "why"}}], 
  "self_check": "did you review all modules?"}}"""

        try:
            import re
            resp = self.llm.generate(prompt, max_tokens=300, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else {}
        except Exception as e:
            logger.debug("LLM synthesis failed: %s", e)
            return {"fallback": True, "error": str(e)}

    @staticmethod
    def _try_load_bridge():
        """Lazy-load v4 cognitive bridge if available."""
        try:
            from core.agent.v4.cognitive_bridge import V4CognitiveBridge
            return V4CognitiveBridge()
        except Exception:
            return None

    @staticmethod
    def _try_load_context():
        """Lazy-load unified context if available."""
        try:
            from core.agent.assembly.unified_context import UnifiedContext
            return UnifiedContext()
        except Exception:
            return None

    @staticmethod
    def _try_load_cognition():
        """Lazy-load cognition hub if available."""
        try:
            from core.agent.cognition.hub import CognitionHub
            return CognitionHub()
        except Exception:
            return None
