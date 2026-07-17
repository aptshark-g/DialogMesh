"""ReasoningPolicy — structured feedback that changes HOW the system reasons.

Replaces scalar confidence_bias/temperature with actionable reasoning directives:
  perspective: which lens to use
  explanation_mode: how to explain (via_relation / step_by_step / analogy)
  depth: how deep to go
  relation_expansion: which relation types to explore
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════ ReasoningPolicy ═══════════════════════

@dataclass
class ReasoningPolicy:
    """A structured directive that changes reasoning behavior.

    Unlike a scalar bias, this tells the system WHAT to do differently:
      - Change perspective from architecture to engineering
      - Switch explanation mode from abstract to concrete
      - Expand only causal relations, not all relations
    """

    # ── Perspective Control ──
    perspective: Optional[str] = None       # architecture/engineering/evolution/execution
    perspective_confidence: float = 0.5

    # ── Explanation Mode ──
    explanation_mode: Optional[str] = None  # via_relation / step_by_step / analogy / top_down
    mode_confidence: float = 0.5

    # ── Depth Control ──
    depth_adjust: int = 0                   # -1 = shallower, +1 = deeper, 0 = default
    depth_confidence: float = 0.5

    # ── Relation Expansion ──
    expand_relations: List[str] = field(default_factory=list)   # e.g. ["causal","depends_on"]
    relation_confidence: float = 0.5

    # ── Attention Control ──
    focus_objects: List[str] = field(default_factory=list)      # objects to prioritize
    attention_confidence: float = 0.5

    # ── Temperature (keep for backwards compat) ──
    temperature_mod: float = 0.0            # still available but secondary

    # ── Reason ──
    reason: str = ""                        # why this policy was chosen
    source: str = "meta_consumer"           # who generated it

    def is_significant(self) -> bool:
        """Is this policy strong enough to change behavior?"""
        return (
            self.perspective is not None or
            self.explanation_mode is not None or
            self.depth_adjust != 0 or
            len(self.expand_relations) > 0 or
            len(self.focus_objects) > 0
        )

    def apply_to_prompt(self, system_instruction: str) -> str:
        """Inject policy directives into the system prompt."""
        if not self.is_significant():
            return system_instruction

        hints = []
        if self.perspective:
            hints.append(f"Use {self.perspective} perspective")
        if self.explanation_mode:
            hints.append(f"Explain via {self.explanation_mode}")
        if self.depth_adjust > 0:
            hints.append("Go deeper into details")
        elif self.depth_adjust < 0:
            hints.append("Keep explanation concise and high-level")
        if self.expand_relations:
            hints.append(f"Focus on {', '.join(self.expand_relations)} relations")
        if self.focus_objects:
            hints.append(f"Prioritize: {', '.join(self.focus_objects[:3])}")

        if hints:
            return system_instruction + "\n[Reasoning Policy] " + "; ".join(hints)
        return system_instruction

    def apply(self, engine):
        """Apply policy directly to engine components (strong feedback)."""
        # ── Perspective override ──
        if self.perspective:
            if hasattr(engine, '_last_perspective'):
                engine._last_perspective = self.perspective
            if hasattr(engine, '_perspective_planner'):
                engine._perspective_planner._forced_perspective = self.perspective

        # ── Focus objects → attention bias ──
        if self.focus_objects:
            if hasattr(engine, '_world_objects'):
                for obj_name in engine._world_objects:
                    obj = engine._world_objects.get(obj_name)
                    if obj and hasattr(obj, 'data'):
                        obj.data["attention_bias"] = (
                            0.8 if obj_name in self.focus_objects else 0.2
                        )

        # ── Relation expansion → graph query filter ──
        if self.expand_relations and hasattr(engine, '_content_provider'):
            engine._relation_filter = self.expand_relations

        # ── Explanation mode → set on context compiler ──
        if self.explanation_mode and hasattr(engine, '_world_params'):
            engine._world_params.explanation_mode = self.explanation_mode

    def apply_to_context(self, compiler_params: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust context compiler parameters based on policy."""
        params = dict(compiler_params)
        if self.depth_adjust != 0:
            params["compiler_token_budget"] = max(
                512, params.get("compiler_token_budget", 2048) + self.depth_adjust * 512
            )
        if self.focus_objects:
            params["focus_objects"] = self.focus_objects
        return params


from core.agent.v4.cognitive.pattern_learner import PatternLearner


# ═══════════════════════ PolicyGenerator ═══════════════════════

class PolicyGenerator:
    """Generates ReasoningPolicy from MetaConsumer analysis + learned patterns."""

    PERSPECTIVE_ROTATION = ["architecture", "engineering", "evolution", "execution"]
    EXPLANATION_MODES = ["via_relation", "step_by_step", "analogy", "top_down"]

    def __init__(self):
        self._last_perspective_idx = 0
        self._last_mode_idx = 0
        self._pattern_learner = PatternLearner()
        self._turn_patterns: Dict[str, int] = {}  # pattern_id → count this session

    def generate(self, meta_advice: Dict[str, Any], current_context: Dict[str, Any] = None) -> ReasoningPolicy:
        """Generate policy from meta-analysis advice.

        Args:
            meta_advice: output from MetaConsumer.consume()
            current_context: current engine state (perspective, depth, etc.)
        """
        policy = ReasoningPolicy()
        warnings = meta_advice.get("warnings", [])

        # ── Check learned patterns first (override if-else) ──
        pattern_desc = " + ".join(warnings[:2]) if warnings else "generic"
        pid = self._pattern_learner.register_pattern(pattern_desc, meta_advice)
        learned = self._pattern_learner.suggest_policy(pid)
        if learned:
            policy.perspective = learned.get("perspective")
            policy.explanation_mode = learned.get("explanation_mode")
            policy.depth_adjust = learned.get("depth_adjust", 0)
            policy.focus_objects = learned.get("focus_objects", [])
            policy.reason = f"Learned pattern {pid} (effectiveness: {self._pattern_learner._patterns[pid].policy_effectiveness:.2f})"
            policy.source = "pattern_learner"
            return policy

        # ── Pattern 1: Consecutive rejects → rotate perspective ──
        if any("REJECT" in w for w in warnings):
            self._last_perspective_idx = (self._last_perspective_idx + 1) % len(self.PERSPECTIVE_ROTATION)
            policy.perspective = self.PERSPECTIVE_ROTATION[self._last_perspective_idx]
            policy.perspective_confidence = 0.7
            policy.reason = "连续 REJECT — 切换视角尝试新路径"

        # ── Pattern 2: No OBSERVE → expand relations + reduce depth ──
        if any("OBSERVE" in w for w in warnings) or any("外部证据" in w for w in warnings):
            policy.expand_relations = ["depends_on", "contains", "causal"]
            policy.depth_adjust = -1
            policy.relation_confidence = 0.6
            policy.reason = "缺少外部证据 — 扩展关系检索并降低深度"

        # ── Pattern 3: Low confidence → concrete explanation mode ──
        if any("置信度" in w for w in warnings) or any("confidence" in w.lower() for w in warnings):
            policy.explanation_mode = "step_by_step"
            policy.mode_confidence = 0.65
            policy.reason = "低置信度 — 切换到具体步骤解释，减少抽象断言"

        # ── Pattern 4: High infer without reflect → force reflection ──
        if any("过热" in w for w in warnings) or any("缺少反思" in w for w in warnings):
            policy.depth_adjust = -2
            policy.explanation_mode = "top_down"
            policy.reason = "推理过热 — 降低深度，强制概括性反思"

        # ── Pattern 5: Low overall → focus on core objects ──
        if meta_advice.get("confidence_mod", 0) < -0.1:
            policy.focus_objects = ["Runtime", "Observer", "Workspace"]
            policy.attention_confidence = 0.5
            policy.temperature_mod = -0.1

        if policy.is_significant():
            logger.info("Policy generated: %s → %s", policy.reason[:60],
                       {k:v for k,v in policy.__dict__.items() if v and k != 'reason' and not k.endswith('_confidence')})

        return policy
