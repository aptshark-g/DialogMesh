"""Domain-specific Task types."""
from typing import Any, Callable
from .models import Task


class ObservationTask(Task):
    def __init__(self, event: dict, compiler):
        super().__init__(task_id=f"obs_{id(self)}", priority=8)
        self._event = event; self._compiler = compiler
    def execute(self): return self._compiler.process(self._event)


class HypothesisTask(Task):
    def __init__(self, evidence: dict, engine):
        super().__init__(task_id=f"hyp_{id(self)}", priority=5)
        self._evidence = evidence; self._engine = engine
    def execute(self): return self._engine.submit(self._evidence)


class KnowledgeTask(Task):
    def __init__(self, engine):
        super().__init__(task_id=f"kn_{id(self)}", priority=3)
        self._engine = engine
    def execute(self): return self._engine.run_cycle()


class SkillTask(Task):
    def __init__(self, engine, stores: dict = None):
        super().__init__(task_id=f"sk_{id(self)}", priority=1)
        self._engine = engine; self._stores = stores or {}
    def execute(self): return self._engine.scan(**self._stores)
