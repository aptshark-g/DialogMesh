"""CognitiveRuntimeEngine: orchestrates v4 modules across four paths."""
from __future__ import annotations
import importlib, time, logging, threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.event_ir import EventIR
from core.agent.v4.runtime.adapter import (
    RuntimeAdapter, RuntimeContext, AdapterResult,
)
from core.agent.v4.runtime.config import (
    RuntimeConfig, ModuleConfig, PathConfig, load_runtime_config, build_default_config,
)
from core.agent.v4.world.params import WorldParams, get_world_params
from core.agent.v4.context.assembler import ContextAssembler
from core.agent.v4.context.source import (
    ObservationSource, KnowledgeSource, SkillSource, WorldSource,
)
from core.agent.v4.context.domain_selector import DomainSelector
from core.agent.v4.context.cross_domain_ir import CrossDomainContextIR
from core.agent.v4.cognitive_scheduler.scheduler import CognitiveScheduler

from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    PathStateMachine, PathState, PathTriggerPolicy, ConfigDrivenTriggerPolicy,
    EventCounter,
)
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
from core.agent.v4.cognitive_scheduler.path_models import PathTask, PathWorkerPool
from core.agent.v4.cognitive_scheduler.path_policy import PathAwarePolicy

from core.agent.v4.optimizer.signals import FeedbackSignal
from core.agent.v4.optimizer.optimizer import BayesianOptimizer

logger = logging.getLogger(__name__)


class PathTriggerContext:
    """Context for trigger policy decisions."""
    def __init__(self, event_count: int = 0, time_since_last: float = 0,
                 slow_results: list = None, checkpoint_count: int = 0):
        self.event_count = event_count
        self.time_since_last = time_since_last
        self.slow_results = slow_results or []
        self.checkpoint_count = checkpoint_count


@dataclass
class PathStats:
    """Runtime statistics for a single path."""
    path_name: str
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_triggered_at: float = 0.0


class CognitiveRuntimeEngine:
    """Orchestrates v4 cognitive modules across Fast/Async/Slow/Deep paths.

    Path data flow:
        Async: Event -> ObservationCompiler -> ObservationPool
        Slow:  ObservationPool -> HypothesisEngine -> Knowledge
        Deep:  Patterns -> SkillDistiller -> Skill

    Usage:
        engine = CognitiveRuntimeEngine()
        engine.start()

        # On each user event:
        engine.on_event(event_ir)

        # Or manually trigger checkpoint:
        engine.trigger_checkpoint()

        # On session end:
        engine.on_session_end()
    """

    def __init__(self, config_path: str = None, world_params: WorldParams = None):
        if config_path:
            self._config = load_runtime_config(config_path)
        else:
            self._config = build_default_config()

        self._world_params = world_params or get_world_params()
        self._adapters: Dict[str, RuntimeAdapter] = {}
        self._stats: Dict[str, PathStats] = {}
        self._event_buffer: List[EventIR] = []
        self._running = False
        self._checkpoint_timer: Optional[threading.Timer] = None
        self._session_active = False
        self._trigger_policy: Optional[PathTriggerPolicy] = None
        self._path_state_machine: Optional[PathStateMachine] = None
        self._event_counter: Optional[EventCounter] = None
        self._last_checkpoint_time = 0.0
        self._observation_pool = None
        self._context_assembler: Optional[ContextAssembler] = None
        self._domain_selector: Optional[DomainSelector] = None
        self._last_context: Optional[CrossDomainContextIR] = None

        for path_name in self._config.paths:
            self._stats[path_name] = PathStats(path_name=path_name)

    # ---- Lifecycle ----

    def start(self) -> None:
        self._running = True
        self._session_active = True
        self._instantiate_adapters()
        self._observation_pool = self._create_observation_pool()
        self._context_assembler = self._create_context_assembler()
        self._domain_selector = DomainSelector()
        # ---- New: Config-driven trigger policy ----
        self._trigger_policy = ConfigDrivenTriggerPolicy(
            self._config, self._world_params
        )
        self._path_state_machine = self._trigger_policy.state_machine
        self._event_counter = self._trigger_policy.event_counter
        # ---- New: Path-aware scheduler ----
        self._scheduler = PathAwareScheduler(
            policy=PathAwarePolicy(),
            pool=PathWorkerPool(size=4),
            state_machine=self._path_state_machine,
        )
        # ---- Optimizer: check enabled flag ----
        if getattr(self._world_params, 'optimizer_enabled', False):
            self._optimizer = BayesianOptimizer(bounds={})
        else:
            self._optimizer = None
        self._feedback_signal = FeedbackSignal()
        self._checkpoint_count = 0
        self._last_checkpoint_time = 0.0
        self._start_checkpoint_timer()
        logger.info("CognitiveRuntimeEngine started — %d adapters + PathAwareScheduler + TriggerPolicy", len(self._adapters))

    def stop(self) -> None:
        self._running = False
        self._session_active = False
        self._cancel_checkpoint_timer()
        self._adapters.clear()
        self._event_buffer.clear()
        self._observation_pool = None
        self._context_assembler = None
        self._domain_selector = None
        self._last_context = None
        if self._scheduler:
            self._scheduler.stop()
            self._scheduler = None
        self._optimizer = None
        self._feedback_signal = None
        logger.info("CognitiveRuntimeEngine stopped")

    # ---- Event-driven triggers ----

    def on_event(self, event: EventIR) -> None:
        """Process a single user event through the Async Path.
        Auto-triggers Slow Path when event threshold reached."""
        if not self._running or not self._session_active:
            return

        self._event_buffer.append(event)
        self._last_event_time = time.time()
        self._stats["async"].trigger_count += 1
        self._stats["async"].last_triggered_at = self._last_event_time

        # ---- New: Event counter + auto-trigger ----
        if self._trigger_policy and self._trigger_policy.on_event():
            logger.info("Event threshold reached — auto-triggering checkpoint")
            self.trigger_checkpoint()

        path_config = self._config.get_path("async")
        if not path_config:
            return

        ctx = RuntimeContext(event=event)
        for module_config in path_config.modules:
            adapter = self._adapters.get(module_config.name)
            if adapter is None:
                continue

            start = time.time()
            result = adapter.timed_execute(ctx)
            elapsed = (time.time() - start) * 1000

            pas = self._stats["async"]
            pas.total_latency_ms += elapsed
            if result.ok:
                pas.success_count += 1
                # ---- Observation Pool integration ----
                if result.data is not None and self._observation_pool is not None:
                    try:
                        self._observation_pool.put(result.data)
                    except (TypeError, AttributeError):
                        pass
                    logger.debug("Observation written to pool: %s", event.id)
                ctx.observations.append(result.data)
            else:
                pas.failure_count += 1

        # ---- Context Engineering ----
        self._compile_context(event)

        # ---- Feedback collection ----
        if self._feedback_signal and pas.success_count > 0:
            self._feedback_signal.with_implicit(accepted=(pas.failure_count == 0))

    def on_session_end(self) -> None:
        """Trigger checkpoint on session end."""
        if not self._running:
            return
        self._session_active = False
        logger.info("Session ended, triggering checkpoint")
        self.trigger_checkpoint()

    def trigger_checkpoint(self) -> List[AdapterResult]:
        """Run the Slow Path (checkpoint) with ObservationPool data."""
        return self._run_path("slow")

    def trigger_deep(self) -> List[AdapterResult]:
        """Run the Deep Path."""
        return self._run_path("deep")

    # ---- Internal ----

    # ---- Context Engineering ----

    def _compile_context(self, event: EventIR) -> None:
        """Compile CrossDomainContextIR from current cognitive state.

        DomainSelector determines which domains are relevant.
        BudgetAllocator (inside assemble_ir) allocates token budget.
        ContextAssembler retrieves from all available sources.
        """
        if self._context_assembler is None or self._domain_selector is None:
            return

        text = event.payload.get("text", "") if hasattr(event, "payload") else ""

        try:
            self._last_context = self._context_assembler.assemble_ir(
                text,
                token_budget=self._world_params.compiler_token_budget,
                domain_boosts=self._get_domain_boosts(event),
            )
            logger.debug("Context compiled: %d entries, %d tokens",
                        len(self._last_context.entries),
                        self._last_context.total_tokens)
        except Exception as e:
            logger.warning("Context compilation failed: %s", e)

    def _create_context_assembler(self) -> ContextAssembler:
        """Build ContextAssembler with all available knowledge sources."""
        sources = []
        if self._observation_pool is not None:
            sources.append(ObservationSource(self._observation_pool))
        sources.append(KnowledgeSource())
        sources.append(SkillSource())
        sources.append(WorldSource())
        return ContextAssembler(sources)

    def _get_domain_boosts(self, event: EventIR) -> dict:
        """Adjust domain weights based on event type."""
        kind = event.kind if hasattr(event, "kind") else ""
        if kind == "dialog.message":
            return {"knowledge": 1.5}
        elif kind in ("ui.drag", "ui.drop", "tool.call"):
            return {"engineering": 2.0}
        elif kind == "git.commit":
            return {"engineering": 1.5, "world": 1.5}
        return {}

    @property
    def last_context(self) -> Optional[CrossDomainContextIR]:
        return self._last_context

    def _run_path(self, path_name: str) -> List[AdapterResult]:
        if not self._running:
            return []

        path_config = self._config.get_path(path_name)
        if not path_config:
            return []

        self._stats[path_name].trigger_count += 1
        self._stats[path_name].last_triggered_at = time.time()

        # Build context from ObservationPool (if available)
        ctx = RuntimeContext()
        if self._observation_pool is not None and path_name == "slow":
            # Read all observations from pool (all domains, since last checkpoint)
            raw_obs = self._observation_pool.get_by_domain("all")
            ctx.observations = list(raw_obs) if raw_obs else []
        elif path_name == "slow":
            # Fallback: use event buffer
            ctx.observations = list(self._event_buffer)

        results = []
        for module_config in path_config.modules:
            adapter = self._adapters.get(module_config.name)
            if adapter is None:
                continue

            start = time.time()
            result = adapter.timed_execute(ctx)
            elapsed = (time.time() - start) * 1000

            stats = self._stats[path_name]
            stats.total_latency_ms += elapsed
            if result.ok:
                stats.success_count += 1
            else:
                stats.failure_count += 1

            results.append(result)

        # ---- New: Deep Path trigger via policy ----
        if path_name == "slow":
            self._event_buffer.clear()
            self._checkpoint_count += 1
            self._last_checkpoint_time = time.time()
            # Check if Deep Path should trigger
            if self._trigger_policy:
                trigger_ctx = PathTriggerContext(
                    slow_results=results,
                    checkpoint_count=self._checkpoint_count,
                )
                if self._trigger_policy.should_trigger("deep", trigger_ctx.__dict__):
                    logger.info("Deep Path threshold met — triggering skill distillation")
                    self.trigger_deep()
            # Bayesian Optimizer step
            if self._optimizer and self._feedback_signal:
                if self._trigger_policy and self._trigger_policy.should_optimize(self._checkpoint_count):
                    try:
                        reward = self._feedback_signal.composite_reward()
                        # Fix: read from correct params
                        current_params = {
                            "min_support": getattr(self._world_params, 'min_support', 8),
                            "community_resolution": self._world_params.community_resolution,
                            "compiler_max_nodes": self._world_params.compiler_max_nodes,
                        }
                        suggestion = self._optimizer.suggest()
                        if suggestion:
                            logger.info("Optimizer suggests: %s", suggestion)
                    except Exception as e:
                        logger.debug("Optimizer step skipped: %s", e)

        return results

    def _start_checkpoint_timer(self) -> None:
        """Start a timer that triggers checkpoint periodically."""
        slow_path = self._config.get_path("slow")
        if not slow_path or not slow_path.modules:
            return

        for mc in slow_path.modules:
            if mc.trigger == "checkpoint":
                time_minutes = mc.trigger_config.get("time_minutes", 30)
                interval_sec = time_minutes * 60
                self._schedule_checkpoint_timer(interval_sec)
                break

    def _schedule_checkpoint_timer(self, interval_sec: float) -> None:
        """Schedule the next checkpoint timer tick."""
        if not self._running:
            return

        def _tick():
            if not self._running:
                return
            elapsed_since_last = time.time() - self._last_event_time
            if self._session_active and elapsed_since_last < interval_sec * 1.5:
                logger.info("Time-based checkpoint triggered")
                self.trigger_checkpoint()
            self._schedule_checkpoint_timer(interval_sec)

        self._checkpoint_timer = threading.Timer(interval_sec, _tick)
        self._checkpoint_timer.daemon = True
        self._checkpoint_timer.start()

    def _cancel_checkpoint_timer(self) -> None:
        if self._checkpoint_timer is not None:
            self._checkpoint_timer.cancel()
            self._checkpoint_timer = None

    def _create_observation_pool(self):
        """Create the ObservationPool for path-to-path data flow."""
        try:
            from core.agent.v4.observation_compiler.pool import ObservationPool
            return ObservationPool()
        except Exception as e:
            logger.warning("Cannot create ObservationPool: %s", e)
            return None

    def _instantiate_adapters(self) -> None:
        for path_config in self._config.paths.values():
            for module_config in path_config.modules:
                adapter_cls = self._import_class(module_config.adapter)
                if adapter_cls is None:
                    logger.error("Cannot import adapter: %s", module_config.adapter)
                    continue

                merged_params = dict(self._world_params.__dict__)
                merged_params.update(module_config.params)

                try:
                    adapter = adapter_cls(
                        name=module_config.name,
                        timeout_ms=module_config.timeout_ms,
                        retry=module_config.retry,
                        params=merged_params,
                    )
                    self._adapters[module_config.name] = adapter
                except Exception as e:
                    logger.error("Failed to instantiate adapter %s: %s", module_config.name, e)

    @staticmethod
    def _import_class(full_path: str):
        try:
            parts = full_path.rsplit(".", 1)
            module = importlib.import_module(parts[0])
            return getattr(module, parts[1])
        except Exception:
            return None

    # ---- Accessors ----

    @property
    def stats(self) -> Dict[str, PathStats]:
        return dict(self._stats)

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    @property
    def observation_pool(self):
        return self._observation_pool
