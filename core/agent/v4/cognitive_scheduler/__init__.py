"""Cognitive Scheduler: unified scheduling layer."""
from __future__ import annotations

# Base models
from .models import Task, CallableTask, Worker, WorkerPool, WorkerStats

# Path-aware extensions (new in v4.1)
from .path_models import PathTask, PathWorkerPool
from .path_policy import PathAwarePolicy, PriorityFIFOPolicy, SchedulerPolicy
from .path_trigger_policy import (
    PathState, PathName, PathStateRecord, PathStateMachine,
    EventCounter, PathTriggerPolicy, ConfigDrivenTriggerPolicy,
)
from .path_scheduler import PathAwareScheduler

# Legacy scheduler (kept for backward compatibility)
from .scheduler import CognitiveScheduler, SchedulerMonitor, QueueSnapshot

# Task types
from .tasks import ObservationTask, HypothesisTask, KnowledgeTask, SkillTask

__all__ = [
    # Base
    "Task", "CallableTask", "Worker", "WorkerPool", "WorkerStats",
    # Path-aware (new)
    "PathTask", "PathWorkerPool",
    "PathAwarePolicy", "PriorityFIFOPolicy", "SchedulerPolicy",
    "PathState", "PathName", "PathStateRecord", "PathStateMachine",
    "EventCounter", "PathTriggerPolicy", "ConfigDrivenTriggerPolicy",
    "PathAwareScheduler",
    # Legacy
    "CognitiveScheduler", "SchedulerMonitor", "QueueSnapshot",
    # Tasks
    "ObservationTask", "HypothesisTask", "KnowledgeTask", "SkillTask",
]
