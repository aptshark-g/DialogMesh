"""Agent-Native Orchestrator — LLM-driven full pipeline coordination.

Pipeline: Compass → PCR → Intent → L4 → Behavior → Context → Engineering → LLM.
Cold→Hot: Meta corrections feed back through FeedbackBridge (3-layer).
All modules lazy-loaded; pipeline degrades gracefully on missing deps.
"""

from __future__ import annotations
from typing import Dict, Any
import logging
import time
import uuid

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """LLM-driven orchestrator — 9-stage pipeline with cold→hot feedback."""

    def __init__(self, pcr_router=None, intent_splitter=None, l4_engine=None,
                 behavior_collab=None, engineering_chain=None, llm=None,
                 discourse_tree=None, cognitive_bridge=None, event_log=None,
                 context_assembly=None, cognition_hub=None,
                 feedback_bridge=None, compass_selector=None,
                 plan_gate=None, execution_pipeline=None,
                 file_sandbox=None, permission_guard=None,
                 semantic_diff=None, event_bus=None, reactor=None):
        self.pcr = pcr_router; self.intent = intent_splitter
        self.l4 = l4_engine; self.behavior = behavior_collab
        self.engineering = engineering_chain; self.llm = llm
        self.discourse = discourse_tree
        self.cognitive = cognitive_bridge or self._try_load_bridge()
        self._event_log = event_log
        self._context_assembly = context_assembly or self._try_load_context()
        self._cognition_hub = cognition_hub or self._try_load_cognition()
        self._feedback_bridge = feedback_bridge or self._try_load_feedback()
        self._compass = compass_selector or self._try_load_compass()
        self._plan_gate = plan_gate or self._try_load_gate()
        self._execution_pipeline = execution_pipeline or self._try_load_execution()
        self._file_sandbox = file_sandbox
        self._permission_guard = permission_guard
        self._semantic_diff = semantic_diff
        self._event_bus = event_bus
        self._reactor = reactor
        self._tick = 0


    def process_resume(self, session_id: str, frontend_response: dict):
        """Resume pipeline from PlanGate checkpoint."""
        start = time.time()
        result = {"session": session_id, "status": "resuming"}

        # Apply user response to checkpoint
        if self._plan_gate:
            try:
                from core.agent.planning.checkpoint import PlanCheckpoint, CheckpointDecision
                # Reconstruct checkpoint from stored state
                checkpoint = PlanCheckpoint(
                    checkpoint_id=frontend_response.get("checkpoint_id", ""),
                    session_id=session_id,
                    original_plan={"steps": []})
                checkpoint.apply_user_changes(frontend_response)
                result["plan_gate"] = checkpoint.decision.value
                result["plan_status"] = checkpoint.decision.value
            except Exception as e:
                logger.debug("PlanGate resume: %s", e)

        # ═══ Execution ═══ (re-enter pipeline)
        if self._execution_pipeline and hasattr(self, "_last_plan"):
            try:
                import asyncio
                from core.agent.planning.checkpoint import PlanCheckpoint, CheckpointDecision
                cp = PlanCheckpoint(checkpoint_id="resume", session_id=session_id,
                                    original_plan=self._last_plan)
                cp.apply_user_changes(frontend_response)
                exec_r = asyncio.run(
                    self._execution_pipeline.run(self._last_plan, cp))
                result["execution"] = exec_r
                self._publish("EXECUTION_COMPLETED", exec_r)
                result["plan_status"] = "executed"
            except Exception as e:
                logger.debug("Execution resume: %s", e)
                result["execution"] = {"status": "error", "error": str(e)}

        # LLM Answer
        result["answer"] = "Execution completed"  # Placeholder — real LLM in full pipeline
        result["latency_ms"] = round((time.time() - start) * 1000)
        return result

    def _publish(self, kind: str, payload: dict):
        # EventBus v2 (NATS-patterned) — primary
        if self._event_bus:
            try:
                import asyncio as _a
                _a.ensure_future(self._event_bus.publish(kind, payload))
            except Exception:
                pass
        # EventLog fallback
        if self._event_log:
            try:
                self._tick += 1
                eid = f"{kind}_{self._tick}_{int(time.time()*1000)}"
                self._event_log.put_event(eid, kind, payload)
            except Exception:
                pass

    def process(self, text: str, trace_id: str = None, instrument: bool = True):
        if instrument:
            try:
                from core.agent.monitor.trace_log import PipelineObserver, get_tracer
                observer = PipelineObserver()
                tr = observer.start_request(text[:100])
                trace_id = tr["trace_id"]
            except: pass
        start = time.time(); session_id = str(uuid.uuid4())[:8]; result = {}
        start = time.time()
        result = {"text": text, "session": session_id}

        # Cold→Hot Layer 1: urgent correction
        correction = None
        if self._feedback_bridge:
            correction = self._feedback_bridge.consume()
            if correction:
                result["correction"] = correction

        # 0. Compass — multi-dimensional signal measurement
        if self._compass:
            try:
                cr = self._compass.measure(text)
                result["compass"] = {
                    "lenses": cr.selected_lenses,
                    "signal": cr.summary(),
                    "dimensions": cr.dimensions,
                }
            except Exception as e:
                logger.debug("Compass failed: %s", e)

        # 1. PCR V2
        if self.pcr:
            try:
                route = self.pcr.route(text,
                    override=correction.get("suggested_action") if correction else None)
                result["route"] = {
                    "zone": getattr(route, 'zone', 'MIXED'),
                    "x": getattr(route, 'x', 0.5),
                    "y": getattr(route, 'y', 0.5),
                    "z": getattr(route, 'z', 0.0),
                }
                if self.cognitive:
                    self.cognitive.on_pcr_route(result["route"])
                self._publish("PCR_COMPUTED", result["route"])
            except Exception as e:
                logger.debug("PCR failed: %s", e)
                result["route"] = {"zone": "MIXED", "error": str(e)}

        # 2. Intent — DualTrack hot/cold (replaces direct splitter)
        if self.intent:
            try:
                # DualTrack: hot path returns immediately, cold path optimizes in background
                dt_result = self.intent.process(text)
                result["intents"] = {
                    "multi": dt_result.is_multi,
                    "segments": dt_result.segments,
                    "confidence": dt_result.confidence,
                    "source": dt_result.source,
                    "cold_enqueued": dt_result.cold_enqueued,
                }
                self._publish("INTENT_PARSED", result["intents"])
            except Exception as e:
                # Fallback: direct splitter
                logger.debug("DualTrack failed: %s", e)
                try:
                    split_result = self.intent.split(text)
                    result["intents"] = {
                        "multi": split_result.multi,
                        "segments": [s.text for s in split_result.segments],
                        "confidence": split_result.confidence,
                        "source": "fallback",
                    }
                except Exception:
                    result["intents"] = {"multi": False, "segments": [text], "source": "fallback"}

        # 3. L4 Temporal
        if self.l4:
            try:
                current_intent = result.get("intents", {}).get("segments", [text])[0]
                preds = self.l4.predict_next(current_intent)
                result["temporal"] = {"predictions": [(p[0], round(p[1], 2)) for p in preds]}
                intent_dist = {current_intent: 1.0}
                drift = self.l4.check_drift(intent_dist)
                if drift:
                    result["temporal"]["drift"] = {"magnitude": round(drift.magnitude, 3),
                                                    "cause": drift.likely_cause}
            except Exception as e:
                logger.debug("L4 failed: %s", e)
        if self.cognitive:
            self.cognitive.on_temporal_predict(
                result.get("temporal", {}).get("predictions", []),
                result.get("temporal", {}).get("drift"))
            if result.get("temporal"):
                self._publish("L4_PREDICTED", result["temporal"])

        # 4. Behavior
        if self.behavior:
            try:
                result["behavior"] = {"available": True}
            except Exception:
                result["behavior"] = {"available": False}
        if self.cognitive:
            self.cognitive.on_behavior_update(result.get("behavior", {}))
        if result.get("behavior"):
            self._publish("BEHAVIOR_RECORDED", result["behavior"])

        # 5. Context assembly
        if self._context_assembly:
            try:
                ctx_result = self._context_assembly.assemble(result)
                result["context"] = {"dialogue": ctx_result.get("dialogue_context", ""),
                                     "meta": ctx_result.get("meta_context", ""),
                                     "stats": ctx_result.get("stats", {})}
                self._publish("CONTEXT_COMPILED", result["context"].get("stats", {}))
            except Exception as e:
                logger.debug("Context failed: %s", e)

        # 6. Engineering
        if self.engineering:
            try:
                state = self.engineering.snapshot()
                feasibility = self.engineering.check_feasibility(text, state)
                result["tools"] = {"total": feasibility.get("total_tools", 0),
                                   "matching": feasibility.get("matching_tools", 0),
                                   "feasible": feasibility.get("feasible", 0)}
                self._publish("TOOLS_CHECKED", result["tools"])
            except Exception as e:
                logger.debug("Engineering failed: %s", e)

        # 7. LLM Synthesis
        if self.llm:
            if self.cognitive:
                result["cognitive"] = self.cognitive.build_llm_context()
                self.cognitive.tick()
            self._last_plan = self._llm_synthesize(result)
            result["plan"] = self._last_plan
            self._publish("PLAN_GENERATED", result.get("plan", {}))

            # === CHECKPOINT: human-in-the-loop plan review ===
            if self._plan_gate and result.get("plan", {}).get("steps"):
                checkpoint = self._plan_gate.create_checkpoint(
                    result["plan"], session_id)
                result["checkpoint"] = checkpoint.to_frontend()
                if checkpoint.requires_review:
                    result["requires_user_review"] = True
                    result["plan_status"] = "pending_review"
                    result["latency_ms"] = round((time.time() - start) * 1000)
                    return result

                # === EXECUTION: ExecutionPipeline weld ===
                if self._execution_pipeline:
                    try:
                        import asyncio
                        exec_result = asyncio.run(
                            self._execution_pipeline.run(result["plan"], checkpoint))
                        result["execution"] = exec_result
                        self._publish("EXECUTION_COMPLETED", exec_result)
                        result["plan_status"] = "executed"
                    except Exception as e:
                        logger.debug("Execution pipeline failed: %s", e)
                        result["execution"] = {"status": "error", "error": str(e)}

        # Cold→Hot Layer 2: belief
        if self._cognition_hub and self._cognition_hub.is_loaded:
            try:
                if self._feedback_bridge:
                    belief = self._feedback_bridge.consume_belief()
                    if belief:
                        result["belief_action"] = belief
                result["cognition"] = self._cognition_hub.converge()
            except Exception as e:
                logger.debug("Cognition failed: %s", e)

        # Cold→Hot Layer 3: drift
        if self._feedback_bridge:
            drift = self._feedback_bridge.consume_drift()
            if drift:
                result["parameter_drift"] = drift

        # Record turn
        if self._context_assembly:
            try:
                self._context_assembly.record_turn(text, str(result.get("plan", "")), session_id)
            except Exception:
                pass

        result["latency_ms"] = round((time.time() - start) * 1000)

        # DualTrack status
        if self.intent and hasattr(self.intent, 'status'):
            result["dual_track"] = self.intent.status()

        return result

    def _llm_synthesize(self, context: dict) -> dict:
        import json, re
        ctx = {"user_message": context["text"],
               "compass": context.get("compass", {}).get("signal", ""),
               "cognitive_route": context.get("route", {}),
               "intents": context.get("intents", {}),
               "temporal_predictions": context.get("temporal", {}).get("predictions", []),
               "available_tools": context.get("tools", {}).get("total", 0),
               "cognitive_context": context.get("cognitive", {}),
               "assembled_context": context.get("context", {}).get("dialogue", "")[:2000],
               "correction": context.get("correction", {}),}
        prompt = f"""You are an agent coordinator. Based on the pipeline analysis, create an execution plan.

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Output a JSON execution plan:
{{"steps": [{{"action": "...", "tool": "...", "reason": "..."}}],
  "self_check": "did you review all modules?"}}"""
        try:
            resp = self.llm.generate(prompt, max_tokens=300, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else {}
        except Exception as e:
            logger.debug("LLM failed: %s", e)
            return {"fallback": True, "error": str(e)}

    @staticmethod
    def _try_load_bridge():
        try: from core.agent.v4.cognitive_bridge import V4CognitiveBridge; return V4CognitiveBridge()
        except: return None

    @staticmethod
    def _try_load_context():
        try: from core.agent.assembly.unified_context import UnifiedContext; return UnifiedContext()
        except: return None

    @staticmethod
    def _try_load_cognition():
        try: from core.agent.cognition.hub import CognitionHub; return CognitionHub()
        except: return None

    @staticmethod
    def _try_load_feedback():
        try: from core.agent.meta.feedback_bridge import FeedbackBridge; return FeedbackBridge()
        except: return None

    @staticmethod
    def _try_load_compass():
        try: from core.agent.perception.compass import create_default_compass; return create_default_compass()
        except: return None

    @staticmethod
    def _try_load_gate():
        try:
            from core.agent.planning.checkpoint import PlanGate
            return PlanGate()
        except: return None

    @staticmethod
    def _try_load_execution():
        try:
            from core.agent.execution.tree_manager import AgentTreeManager
            from core.agent.execution.pipeline import ExecutionPipeline
            from core.agent.execution.engine import ExecutionEngine
            atm = AgentTreeManager()
            engine = ExecutionEngine()
            return ExecutionPipeline(tree_manager=atm, engine=engine)
        except: return None
