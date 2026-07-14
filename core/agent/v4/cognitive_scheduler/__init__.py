"""Cognitive Scheduler: unified scheduling layer.

Exports both legacy and path-aware APIs for backward compatibility.
"""
from .models import Task, CallableTask, Worker, WorkerPool, WorkerStats, PathState, PathStateMachine
from .policy import SchedulerPolicy, PriorityFIFOPolicy, PathAwarePolicy
from .scheduler import CognitiveScheduler, SchedulerMonitor, QueueSnapshot
from .tasks import ObservationTask, HypothesisTask, KnowledgeTask, SkillTask

# Path-aware new API (lazy imports to avoid circular dependencies)
_path_models = None
_path_policy = None
_path_scheduler = None

def _load_path_models():
    global _path_models
    if _path_models is None:
        from . import path_models as _path_models
    return _path_models

def _load_path_policy():
    global _path_policy
    if _path_policy is None:
        from . import path_policy as _path_policy
    return _path_policy

def _load_path_scheduler():
    global _path_scheduler
    if _path_scheduler is None:
        from . import path_scheduler as _path_scheduler
    return _path_scheduler

__all__ = [
    # Legacy
    "Task", "CallableTask", "Worker", "WorkerPool", "WorkerStats",
    "SchedulerPolicy", "PriorityFIFOPolicy", "PathAwarePolicy",
    "CognitiveScheduler", "SchedulerMonitor", "QueueSnapshot",
    "ObservationTask", "HypothesisTask", "KnowledgeTask", "SkillTask",
    # Path-aware (available via lazy import or direct submodule import)
    "PathState", "PathStateMachine",
]
