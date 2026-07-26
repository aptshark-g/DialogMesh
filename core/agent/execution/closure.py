"""Node Lifecycle + Causal Tracer + UserInLoop + ReActor.

4 thin modules completing the execution layer metacognition system.
All wire existing components — no new infrastructure needed.

NodeLifecycle:  node-level dead loop detection + blocked handling (~50L)
CausalTracer:   reverse causal trace on node failure (~40L)  
UserInLoop:     execution-time human intervention (~60L)
ReActor:        unified inner/outer loop entry + Transition (~50L)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
import logging, time
from enum import Enum

logger = logging.getLogger(__name__)


# ═══ 1. NodeLifecycle — 死循环检测 ═══

class NodeLifecycle:
    """Track node retries → detect loops → block → escalate.

    Same node 3 retries → BLOCKED → Meta audit → reopen or escalate.
    Same subtree 3 blocked nodes → DEGRADED → CascadeDetector.
    Same node reopened 2+ times → persistent_failure → user must intervene.
    """

    MAX_RETRIES = 3
    MAX_REOPENS = 2

    def __init__(self, meta_tree=None, cascade_detector=None):
        self._meta = meta_tree
        self._cascade = cascade_detector
        self._node_retries: Dict[str, int] = {}
        self._node_reopens: Dict[str, int] = {}
        self._blocked_nodes: Set[str] = set()

    def on_retry(self, node_id: str, reason: str = "") -> Optional[str]:
        """Called on each retry. Returns 'block' if threshold exceeded."""
        self._node_retries[node_id] = self._node_retries.get(node_id, 0) + 1
        count = self._node_retries[node_id]
        if count >= self.MAX_RETRIES:
            self._blocked_nodes.add(node_id)
            if self._cascade:
                self._cascade.record(node_id, False, 0)
            logger.warning("Node %s BLOCKED after %d retries: %s", node_id, count, reason)
            return "block"
        return None

    def on_reopen(self, node_id: str, reason: str = "") -> Optional[str]:
        """Called when archived node is reopened. Returns 'user_triage' if too many."""
        self._node_reopens[node_id] = self._node_reopens.get(node_id, 0) + 1
        count = self._node_reopens[node_id]
        if count >= self.MAX_REOPENS:
            logger.warning("Persistent: %s reopened %d times → user triage", node_id, count)
            return "user_triage"
        return None

    def is_blocked(self, node_id: str) -> bool:
        return node_id in self._blocked_nodes

    def clear(self, node_id: str):
        self._node_retries.pop(node_id, None)
        self._node_reopens.pop(node_id, None)
        self._blocked_nodes.discard(node_id)


# ═══ 2. CausalTracer — 逆向因果追溯 ═══

class CausalTracer:
    """Trace a failing node back to its root cause ancestor.

    N fails → check direct parent M's output → if M is incomplete, M is cause.
    Recursive: trace M's parent → find original fault.
    Marks RelationSubstrate causal edges for learning.
    """

    def __init__(self, tree_manager=None, relation_substrate=None):
        self._tm = tree_manager
        self._rs = relation_substrate

    def trace(self, failing_node_id: str) -> Dict[str, Any]:
        """Trace failure upstream → return {root_cause, chain, evidence}."""
        chain = [failing_node_id]
        current = failing_node_id
        evidence = []

        for _ in range(5):  # Max depth
            if not self._tm:
                break
            node = self._tm.get_node_by_pointer(current)
            if not node or not node.parent_id:
                break
            parent = self._tm.get_node_by_pointer(node.parent_id)
            if not parent:
                break

            # Check: did parent produce incomplete output?
            parent_output = parent.content.get("result", {})
            if parent_output.get("status") != "success":
                chain.append(parent.node_id)
                current = parent.node_id
                evidence.append(f"Parent {parent.node_id} had status={parent_output.get('status')}")
            elif not parent_output.get("output"):
                chain.append(parent.node_id)
                current = parent.node_id
                evidence.append(f"Parent {parent.node_id} has empty output")
            else:
                break

        root_cause = chain[-1]
        # Mark causal edge in RelationSubstrate
        if self._rs and len(chain) >= 2:
            try:
                self._rs.create_edge(
                    source=root_cause, target=failing_node_id,
                    type="causal_trace", confidence=0.8,
                    evidence="; ".join(evidence))
            except Exception:
                pass

        return {"root_cause": root_cause, "chain": chain, "evidence": evidence}


# ═══ 3. UserInLoop — 执行中用户干预 ═══

class TriggerReason(Enum):
    LOW_CONFIDENCE = "low_confidence"
    ANOMALY = "anomaly"
    HIGH_RISK = "high_risk"
    NEED_DECISION = "need_decision"
    USER_REQUESTED = "user_requested"
    CONSTRAINT_BOUNDARY = "constraint_boundary"
    RETRY_EXHAUSTED = "retry_exhausted"


@dataclass
class UserIntervention:
    """Snapshot for frontend user intervention display."""
    intervention_id: str
    node_id: str
    trigger: TriggerReason
    message: str                        # LLM explanation
    confidence: float
    alternatives: List[Dict] = field(default_factory=list)
    current_step: int = 1
    total_steps: int = 1
    timestamp: float = field(default_factory=time.time)

    def to_frontend(self) -> dict:
        return {
            "intervention_id": self.intervention_id,
            "node_id": self.node_id,
            "trigger": self.trigger.value,
            "message": self.message,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "step": f"{self.current_step}/{self.total_steps}",
        }


class UserInLoop:
    """Execution-time human intervention.

    LLM self-trigger or user-trigger pause at any execution node.
    Returns intervention for frontend display.
    User response → pipeline resumes / retries / skips / terminates.
    """

    def __init__(self, plan_gate=None, behavior_tree=None, parameter_registry=None):
        self._gate = plan_gate
        self._behavior = behavior_tree
        self._params = parameter_registry
        self._interventions: List[UserIntervention] = []

    def check(self, node_id: str, context: dict) -> Optional[UserIntervention]:
        """Check if intervention is needed. Returns intervention if yes.

        context: {confidence, risk, constraints_hit, behavior_hints, alternatives}
        """
        confidence = context.get("confidence", 1.0)
        risk = context.get("risk", "low")
        threshold = 0.6
        if self._params:
            threshold = self._params.get("plan.confidence_threshold", 0.6)

        trigger = None
        message = ""

        if context.get("retry_exhausted"):
            trigger = TriggerReason.RETRY_EXHAUSTED
            message = "自动重试3次仍失败, 需要您的指导"
        elif context.get("constraint_hit"):
            trigger = TriggerReason.CONSTRAINT_BOUNDARY
            message = f"操作触及约束边界: {context['constraint_hit']}"
        elif confidence < threshold:
            trigger = TriggerReason.LOW_CONFIDENCE
            message = f"LLM 置信度 {confidence:.0%}, 低于阈值 {threshold:.0%}"
        elif risk in ("high", "critical"):
            trigger = TriggerReason.HIGH_RISK
            message = f"高风险操作: {risk}"
        elif context.get("alternatives"):
            trigger = TriggerReason.NEED_DECISION
            message = f"有 {len(context['alternatives'])} 个备选方案需要选择"

        if not trigger:
            return None

        intervention = UserIntervention(
            intervention_id=f"ui_{node_id}_{int(time.time())}",
            node_id=node_id, trigger=trigger, message=message,
            confidence=confidence,
            alternatives=context.get("alternatives", []),
        )
        self._interventions.append(intervention)
        return intervention

    def apply_response(self, intervention_id: str,
                       decision: str,  # "approve" | "adjust" | "retry" | "skip" | "terminate"
                       note: str = "") -> dict:
        """Apply user response to intervention. Returns action dict."""
        return {"decision": decision, "note": note,
                "intervention_id": intervention_id}

    def recent(self, limit: int = 10) -> List[dict]:
        return [i.to_frontend() for i in self._interventions[-limit:]]


# ═══ 4. ReActor — 统一循环入口 ═══

class ReActor:
    """Unified inner/outer loop orchestrator.

    Inner loop (热):  node → retry → continue (NodeLifecycle + ReActRetry)
    Outer loop (冷): archive → Meta audit → reopen → retry (MetaTree + CausalTracer)
    User loop:        node → user intervention → continue (UserInLoop)

    All transitions logged as AuditRecord → EventLog / Transition storage.
    """

    def __init__(self, node_lifecycle=None, causal_tracer=None,
                 user_in_loop=None, react_engine=None,
                 meta_tree=None, event_bus=None):
        self._lc = node_lifecycle or NodeLifecycle()
        self._tracer = causal_tracer or CausalTracer()
        self._uil = user_in_loop or UserInLoop()
        self._react = react_engine
        self._meta = meta_tree
        self._bus = event_bus
        self._transitions: List[dict] = []

    def node_retry(self, node_id: str, reason: str = "") -> str:
        """Inner loop: handle one retry. Returns 'retry' | 'block' | 'escalate'."""
        action = self._lc.on_retry(node_id, reason)
        if action == "block":
            # Trace root cause
            causal = self._tracer.trace(node_id)
            self._record("blocked", node_id, causal=causal)
            return "block"
        self._record("retry", node_id, reason=reason)
        return "retry"

    def node_done(self, node_id: str):
        """Node completed successfully."""
        self._lc.clear(node_id)
        self._record("completed", node_id)

    def check_intervention(self, node_id: str, context: dict) -> Optional[dict]:
        """Check if user intervention needed, return frontend payload."""
        intervention = self._uil.check(node_id, context)
        if intervention:
            self._record("user_paused", node_id, trigger=intervention.trigger.value)
            return intervention.to_frontend()
        return None

    def apply_intervention(self, intervention_id: str, decision: str,
                           note: str = "") -> dict:
        """Apply user response."""
        result = self._uil.apply_response(intervention_id, decision, note)
        self._record("user_resumed", intervention_id, decision=decision)
        return result

    def _record(self, action: str, entity: str, **extra):
        transition = {
            "action": action, "entity": entity,
            "timestamp": time.time(), **extra,
        }
        self._transitions.append(transition)
        if self._bus:
            try:
                import asyncio
                asyncio.ensure_future(
                    self._bus.publish("reactor.transition", transition))
            except Exception:
                pass

    @property
    def history(self) -> List[dict]:
        return self._transitions[-100:]
