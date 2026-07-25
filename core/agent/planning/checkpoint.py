"""Plan Checkpoint — human-in-the-loop plan review and adjustment.

Exposes the LLM-generated TaskGraph to the user for review before execution.
User can: approve, adjust steps, modify constraints, reject, or add new steps.

Learning: every user modification → CorrectionJournal → BehaviorChain.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class CheckpointDecision(Enum):
    """User decision on a plan checkpoint."""
    APPROVED = "approved"           # Execute as-is
    ADJUSTED = "adjusted"           # User modified steps, execute adjusted
    REJECTED = "rejected"           # User rejected, re-plan needed
    SKIPPED = "skipped"             # Auto-approved (below threshold)


class StepRisk(Enum):
    LOW = "low"            # Read-only, read files, search
    MEDIUM = "medium"      # Write files, shell without destructive flags
    HIGH = "high"          # Edit, delete, destructive shell, MCP calls
    CRITICAL = "critical" # Permission changes, system config, network out


@dataclass
class PlanStep:
    """One step in the execution plan, exposed for user review."""
    index: int
    action: str                 # Human-readable: "Read auth.py", "Install requests"
    tool: str                   # Tool name: read, write, edit, bash, mcp_invoke
    params: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""         # Why the LLM chose this step
    risk: StepRisk = StepRisk.LOW
    constraints_violated: List[str] = field(default_factory=list)  # EngineeringChain findings
    estimated_cost_tokens: int = 50
    estimated_duration_ms: int = 100
    # User modification
    user_approved: Optional[bool] = None   # None = pending, True = approved
    user_modified: bool = False             # User changed params
    user_notes: str = ""                    # User's comment on this step


@dataclass
class PlanCheckpoint:
    """Full plan checkpoint exposed to frontend for user review."""
    checkpoint_id: str
    session_id: str
    original_plan: Dict[str, Any]    # Raw LLM plan output
    steps: List[PlanStep] = field(default_factory=list)
    requires_review: bool = False    # Whether to pause pipeline
    review_reasons: List[str] = field(default_factory=list)  # Why review is needed
    decision: CheckpointDecision = CheckpointDecision.SKIPPED
    # User adjustments
    adjusted_steps: List[PlanStep] = field(default_factory=list)
    user_constraint_overrides: Dict[str, Any] = field(default_factory=dict)
    user_general_note: str = ""
    created_at: float = field(default_factory=time.time)
    reviewed_at: Optional[float] = None

    def to_frontend(self) -> dict:
        """Serialize for frontend display."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "requires_review": self.requires_review,
            "reasons": self.review_reasons,
            "steps": [
                {
                    "idx": s.index,
                    "action": s.action,
                    "tool": s.tool,
                    "reasoning": s.reasoning,
                    "risk": s.risk.value,
                    "violated": s.constraints_violated,
                    "approved": s.user_approved,
                    "modified": s.user_modified,
                    "notes": s.user_notes,
                    "params_preview": _safe_params_preview(s.params),
                }
                for s in self.steps
            ],
            "decision": self.decision.value,
            "general_note": self.user_general_note,
        }

    def apply_user_changes(self, frontend_response: dict) -> "PlanCheckpoint":
        """Apply user modifications from frontend."""
        self.reviewed_at = time.time()

        decision = frontend_response.get("decision", "approved")
        self.decision = CheckpointDecision(decision)
        self.user_general_note = frontend_response.get("note", "")

        if decision == "approved":
            for s in self.steps:
                s.user_approved = True
            return self

        if decision == "adjusted":
            step_updates = frontend_response.get("steps", {})
            for s in self.steps:
                update = step_updates.get(str(s.index), {})
                if update.get("rejected"):
                    s.user_approved = False
                else:
                    s.user_approved = True
                    if "params" in update:
                        s.params.update(update["params"])
                        s.user_modified = True
                    s.user_notes = update.get("notes", "")
            self.adjusted_steps = [s for s in self.steps if s.user_approved is not False]
            return self

        if decision == "rejected":
            for s in self.steps:
                s.user_approved = False
            return self

        return self


class PlanGate:
    """Middleware between LLM Plan and Execution. Decides when to pause.

    Rules for requiring review:
      1. Any step with HIGH/CRITICAL risk
      2. First use of a tool category (user hasn't approved before)
      3. Plan complexity > threshold (user preference)
      4. EngineeringChain flagged constraints
      5. User has set "always review" preference
    """

    ALWAYS_REVIEW_TOOLS = {"edit", "bash", "mcp_invoke"}

    def __init__(self, behavior_bridge=None, engineering_chain=None,
                 user_preference: str = "auto"):
        """
        Args:
            behavior_bridge: BehaviorGraphBridge for learning patterns
            engineering_chain: EngineeringChain for constraint validation
            user_preference: "always_review" | "auto" | "skip_all"
        """
        self._behavior = behavior_bridge
        self._engineering = engineering_chain
        self._user_pref = user_preference
        self._tool_use_count: Dict[str, int] = {}  # Tool usage history
        self._checkpoint_count = 0

    def create_checkpoint(self, plan: dict, session_id: str,
                          user_complexity_threshold: float = 0.6) -> PlanCheckpoint:
        """Build a checkpoint from LLM plan output.

        Returns checkpoint with requires_review=True if plan needs user attention.
        """
        self._checkpoint_count += 1
        steps = self._parse_steps(plan)
        requires, reasons = self._assess_need_review(steps, plan, user_complexity_threshold)

        cp = PlanCheckpoint(
            checkpoint_id=f"ckpt_{session_id}_{self._checkpoint_count}",
            session_id=session_id,
            original_plan=plan,
            steps=steps,
            requires_review=requires,
            review_reasons=reasons,
        )
        return cp

    def _parse_steps(self, plan: dict) -> List[PlanStep]:
        """Parse LLM plan output into PlanStep list."""
        raw_steps = plan.get("steps", [])
        parsed = []
        for i, rs in enumerate(raw_steps):
            tool = rs.get("tool", rs.get("action", "unknown"))
            risk = self._assess_risk(tool, rs)

            # Validate against EngineeringChain
            violated = []
            if self._engineering:
                try:
                    feasibility = getattr(self._engineering, 'check_feasibility',
                                         lambda *a: {})(tool, rs.get("params", {}))
                    if not feasibility.get("feasible", True):
                        violated = feasibility.get("blocking", [])
                except Exception:
                    pass

            parsed.append(PlanStep(
                index=i,
                action=rs.get("action", rs.get("reason", f"Step {i+1}")),
                tool=tool,
                params=rs.get("params", {}),
                reasoning=rs.get("reason", rs.get("reasoning", "")),
                risk=risk,
                constraints_violated=violated,
                estimated_cost_tokens=rs.get("estimated_cost", 50),
            ))
        return parsed

    def _assess_risk(self, tool: str, step: dict) -> StepRisk:
        """Assess risk level of one step."""
        tool_lower = tool.lower()
        params = step.get("params", {})

        # Destructive bash commands
        if tool_lower == "bash":
            cmd = params.get("command", "")
            if any(kw in cmd for kw in ["rm -rf", "dd if=", "mkfs.", "> /dev/"]):
                return StepRisk.CRITICAL
            if any(kw in cmd for kw in ["sudo", "chmod", "chown", "kill", "reboot"]):
                return StepRisk.HIGH
            if any(kw in cmd for kw in ["rm ", "mv ", "pip install", "npm install"]):
                return StepRisk.MEDIUM

        # File mutations
        if tool_lower in ("edit", "write"):
            path = params.get("path", "")
            if "/etc/" in path or "/boot/" in path or "C:\\Windows" in path:
                return StepRisk.CRITICAL
            return StepRisk.MEDIUM

        if tool_lower == "mcp_invoke":
            return StepRisk.HIGH

        if tool_lower in ("read", "glob", "grep"):
            return StepRisk.LOW

        return StepRisk.MEDIUM

    def _assess_need_review(self, steps: List[PlanStep], plan: dict,
                            threshold: float) -> Tuple[bool, List[str]]:
        """Determine if this plan requires user review."""
        reasons = []

        if self._user_pref == "always_review":
            reasons.append("User preference: always review")
        if self._user_pref == "skip_all":
            return False, []

        for s in steps:
            if s.risk in (StepRisk.HIGH, StepRisk.CRITICAL):
                reasons.append(f"Step {s.index}: {s.risk.value} risk ({s.tool})")
            if s.tool in self.ALWAYS_REVIEW_TOOLS and s.tool not in self._tool_use_count:
                reasons.append(f"Step {s.index}: first use of {s.tool}")
            if s.constraints_violated:
                reasons.append(f"Step {s.index}: constraint violation: {s.constraints_violated}")

        confidence = plan.get("confidence", 0.5)
        if confidence < threshold:
            reasons.append(f"Plan confidence ({confidence:.2f}) below threshold ({threshold})")

        return len(reasons) > 0, reasons

    def record_approval_pattern(self, checkpoint: PlanCheckpoint):
        """Learn from user's approval/adjustment patterns."""
        if not self._behavior:
            return
        for s in checkpoint.steps:
            if s.tool:
                self._tool_use_count[s.tool] = self._tool_use_count.get(s.tool, 0) + 1
            if s.user_approved is not None:
                self._behavior.record_observation({
                    "tool": s.tool,
                    "risk": s.risk.value,
                    "approved": s.user_approved,
                    "modified": s.user_modified,
                })


def _safe_params_preview(params: dict, max_len: int = 80) -> str:
    """Safe preview of tool params for frontend display."""
    if not params:
        return "{}"
    import json
    s = json.dumps(params, ensure_ascii=False)
    return s[:max_len] + ("..." if len(s) > max_len else "")
