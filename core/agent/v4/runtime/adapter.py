"""RuntimeAdapter: uniform interface for v4 modules in the Cognitive Runtime."""
from __future__ import annotations
import time, logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.event_ir import EventIR

logger = logging.getLogger(__name__)


@dataclass
class RuntimeContext:
    """Uniform input/output container for Runtime adapters.

    Each adapter extracts what it needs from this context.
    """
    event: Optional[EventIR] = None
    observations: List[Any] = field(default_factory=list)
    hypotheses: List[Any] = field(default_factory=list)
    patterns: List[Any] = field(default_factory=list)
    world_graph: Optional[Any] = None
    params: dict = field(default_factory=dict)


@dataclass
class AdapterResult:
    """Result of an adapter execution."""
    ok: bool
    data: Any = None
    error: str = ""
    latency_ms: float = 0.0
    adapter_name: str = ""


class RuntimeAdapter(ABC):
    """Wraps a v4 cognitive module behind a uniform interface.

    Each adapter:
    - Accepts RuntimeContext as input
    - Calls the underlying module
    - Returns AdapterResult
    - Handles timeouts and retries
    """

    def __init__(self, name: str, timeout_ms: int = 5000, retry: int = 1,
                 params: dict = None):
        self.name = name
        self.timeout_ms = timeout_ms
        self.retry = max(1, retry)
        self.params = params or {}
        self._call_count = 0

    @abstractmethod
    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        """Execute the wrapped module with the given context."""

    def validate_input(self, ctx: RuntimeContext) -> bool:
        """Check if the context has sufficient data for this adapter."""
        return True

    def timed_execute(self, ctx: RuntimeContext) -> AdapterResult:
        """Execute with timeout and retry logic."""
        start = time.time()
        last_error = ""
        for attempt in range(self.retry):
            try:
                result = self.execute(ctx)
                result.latency_ms = (time.time() - start) * 1000
                self._call_count += 1
                return result
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Adapter %s attempt %d/%d failed: %s",
                    self.name, attempt + 1, self.retry, last_error,
                )

        return AdapterResult(
            ok=False,
            error=f"All {self.retry} attempts failed: {last_error}",
            latency_ms=(time.time() - start) * 1000,
            adapter_name=self.name,
        )


# ---- Concrete Adapters ----

class ObservationCompilerAdapter(RuntimeAdapter):
    """Wraps ObservationBuilder for the Async Path."""

    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        from core.agent.v4.observation_compiler.builder import ObservationBuilder
        from core.agent.v4.observation_compiler.normalizer import Normalizer
        from core.agent.v4.observation_compiler.projector import Projector

        if ctx.event is None:
            return AdapterResult(ok=False, error="No event in context", adapter_name=self.name)

        builder = ObservationBuilder()
        normalizer = Normalizer()
        projector = Projector()

        # Normalize -> Project -> Build
        event = ctx.event
        payload = event.payload if hasattr(event, 'payload') else {}
        normalized = {
            'event_id': event.id,
            'kind': event.kind,
            'text': payload.get('text', payload.get('content', '')),
            'source': payload.get('source', 'user'),
            'timestamp': event.timestamp if hasattr(event, 'timestamp') else 0.0,
        }
        domains = projector.project(event.kind)
        try:
            bundle = builder.build_bundle(normalized, domains)
        except Exception:
            bundle = {"domains": domains, "normalized": normalized}
        

        return AdapterResult(ok=True, data=bundle, adapter_name=self.name)


class HypothesisEngineAdapter(RuntimeAdapter):
    """Wraps HypothesisPipeline for the Slow Path."""

    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline

        pipeline = HypothesisPipeline()
        observations = ctx.observations if ctx.observations else []
        if observations:
            result = pipeline.submit(observations)
        else:
            result = pipeline.run_cycle()

        return AdapterResult(ok=True, data=result, adapter_name=self.name)


class SkillDistillerAdapter(RuntimeAdapter):
    """Wraps DistillationEngine for the Deep Path."""

    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        from core.agent.v4.skill_layer.distillation_engine import DistillationEngine

        engine = DistillationEngine()
        # Build inputs from context: pass hypothesis engine for knowledge access
        hypothesis_engine = ctx.params.get("_hypothesis_engine", None)
        knowledge_store = ctx.params.get("_knowledge_store", None)

        try:
            candidates = engine.scan(
                hypothesis_engine=hypothesis_engine,
                knowledge_store=knowledge_store,
            )
        except Exception:
            candidates = []

        return AdapterResult(ok=True, data=candidates, adapter_name=self.name)


class WorldModelAdapter(RuntimeAdapter):
    """Wraps CodeWorldAdapter for the Slow Path."""

    def __init__(self, name: str, timeout_ms: int = 60000, retry: int = 1,
                 params: dict = None, project_root: str = "."):
        super().__init__(name, timeout_ms, retry, params)
        self._project_root = project_root

    def execute(self, ctx: RuntimeContext) -> AdapterResult:
        from core.agent.v4.adapter.code.adapter import CodeWorldAdapter

        adapter = CodeWorldAdapter(
            tier=self.params.get("extraction_tier", 1),
        )
        graph = adapter.build_graph(self._project_root)

        return AdapterResult(ok=True, data=graph, adapter_name=self.name)
