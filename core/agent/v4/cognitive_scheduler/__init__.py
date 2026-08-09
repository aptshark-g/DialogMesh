"""Cognitive Scheduler: path-aware scheduling layer (engine 在用).

B1-8 定案归档修正 (2026-08-04):
  * scheduler.py / policy.py（B 套统一调度循环 + WorkerPool 策略）→ 已归档
    un_use/cognitive_scheduler_b/（被 PathAwareScheduler 演进取代, 零生产引用）
  * path_* + tasks 保留 — engine._scheduler = PathAwareScheduler 实际消费
  * 认知运行时调度职责归 A 套 v4/cognitive/scheduler.py（CognitiveScheduler）
"""
from .models import Task
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
    "Task",
    "ObservationTask", "HypothesisTask", "KnowledgeTask", "SkillTask",
]
