"""CognitiveScheduler — thin dispatch layer between MetaCognition and execution.

Design: docs/v3.0/DESIGN_COGNITIVE_RUNTIME.md §2

Does NOT make decisions. Maps MetaReflection → CognitiveTask.
MetaCognition (LLM) decides. Scheduler translates.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class CognitiveTask:
    """An executable cognitive operation."""
    type: str                    # PERCEIVE | RETRIEVE | EXPAND | REASON | REFLECT | COMMIT
    priority: float = 0.5
    target: Optional[Any] = None
    reason: str = ""
    retry: int = 0
    max_retry: int = 2


@dataclass
class Observer:
    """Cognitive CPU — holds perspective, workspace, and resource budget."""
    id: str = "observer_0"
    perspective: str = "architecture"
    attention: Dict[str, float] = field(default_factory=dict)
    token_budget: int = 4000
    token_used: int = 0
    max_depth: int = 3
    active: bool = True

    # Will be set after workspace init
    _workspace: Any = None
    _workspace_graph: Any = None

    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, ws):
        self._workspace = ws

    def snapshot(self) -> dict:
        return {
            "perspective": self.perspective,
            "attention": self.attention,
            "token_used": self.token_used,
            "active": self.active,
        }


class CognitiveScheduler:
    """Translates MetaReflection → CognitiveTask. No decision logic."""

    def __init__(self, metacognition=None):
        self._meta = metacognition

    def set_metacognition(self, mc):
        self._meta = mc

    def next(self, observer: Observer) -> CognitiveTask:
        """Ask MetaCognition what to do, translate to task."""
        if self._meta is None or observer.workspace is None:
            return CognitiveTask("REASON", reason="default: no MetaCognition available")

        reflection = self._meta.reflect(observer.workspace)

        action_map = {
            "RETRIEVE": ("RETRIEVE", reflection.action_target),
            "EXPAND":   ("EXPAND", reflection.expand_targets if reflection.expand_targets else []),
            "REASON":   ("REASON", None),
            "COMMIT":   ("COMMIT", None),
        }

        action_type, target = action_map.get(
            reflection.next_action,
            ("REASON", None),
        )

        return CognitiveTask(
            type=action_type,
            priority=reflection.confidence_self,
            target=target,
            reason=reflection.action_reason,
        )

    def execute(self, observer: Observer, task: CognitiveTask, engine=None):
        """Execute one cognitive task against the engine."""
        ws = observer.workspace
        if ws is None:
            return

        if task.type == "RETRIEVE":
            self._do_retrieve(observer, task)
        elif task.type == "EXPAND":
            self._do_expand(observer, task)
        elif task.type == "REASON":
            self._do_reason(observer, task, engine)
        elif task.type == "COMMIT":
            ws.committed = True
            ws.state = "COMMITTED"

        observer.token_used += 100
        ws.reasoning_depth = getattr(ws, 'reasoning_depth', 0) + 1

    def _do_retrieve(self, observer: Observer, task: CognitiveTask):
        ws = observer.workspace
        ws.state = "RETRIEVING"
        if task.reason:
            ws.reflection_log.append({
                "action": "RETRIEVE",
                "reason": task.reason,
                "target": task.target,
            })

    def _do_expand(self, observer: Observer, task: CognitiveTask):
        ws = observer.workspace
        ws.state = "EXPANDING"
        targets = task.target if isinstance(task.target, list) else [task.target] if task.target else []
        for t in targets:
            if t and str(t) not in ws.active_objects:
                ws.active_objects.append(str(t))
        if task.reason:
            ws.reflection_log.append({
                "action": "EXPAND",
                "reason": task.reason,
                "targets": targets,
            })

    def _do_reason(self, observer: Observer, task: CognitiveTask, engine=None):
        ws = observer.workspace
        ws.state = "REASONING"
        ws.reflection_log.append({
            "action": "REASON",
            "reason": task.reason,
        })
