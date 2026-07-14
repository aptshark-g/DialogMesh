"""CognitiveRuntimeEngine: orchestrates v4 modules across four paths.

Integrates ``PathAwareScheduler`` for path-aware scheduling,
configuration-driven triggers, and per-path state tracking.
"""
from __future__ import annotations
import importlib
import time
import logging
import threading
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
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
from core.agent.v4.cognitive_scheduler.path_models import PathType, PathState
from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    ConfigDrivenTriggerPolicy, EventCounter, PathStateMachine,
)
from core.agent.v4.cognitive_scheduler.tasks import (
    ObservationTask, HypothesisTask, KnowledgeTask, SkillTask,
)

from core.agent.v4.optimizer.signals import FeedbackSignal
from core.agent.v4.optimizer.optimizer import BayesianOptimizer
from core.agent.llm_providers.base import LLMProvider, GenerateRequest, GenerateResult
from core.agent.llm_providers.provider_factory import ProviderFactory

logger = logging.getLogger(__name__)


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

    Path data flow::

        Async: Event -> ObservationCompiler -> ObservationPool
        Slow:  ObservationPool -> HypothesisEngine -> Knowledge
        Deep:  Patterns -> SkillDistiller -> Skill

    Scheduling integration::

        - PathAwareScheduler tracks per-path state machines (idle → running → backlogged → idle)
        - EventCounter auto-triggers Slow Path after configurable threshold (default 50)
        - Deep Path triggers only when pattern_count >= threshold AND success_rate >= threshold
        - Bayesian Optimizer runs on configurable interval (from WorldParams or default 3)
        - All trigger parameters read from runtime.yaml and WorldParams, no hard-coding
        - LLM Provider: compiles CrossDomainContextIR → prompt → LLM → response

    Usage::

        engine = CognitiveRuntimeEngine()
        engine.start()

        # On each user event:
        response = engine.on_event(event_ir)  # Returns LLM response string

        # Or manually trigger checkpoint:
        engine.trigger_checkpoint()

        # On session end:
        engine.on_session_end()
    """

    def __init__(self, config_path: str = None, world_params: WorldParams = None,
                 llm_provider: Optional[LLMProvider] = None):
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
        self._last_event_time = 0.0

        # Observation pool for path-to-path data flow
        self._observation_pool = None
        self._context_assembler: Optional[ContextAssembler] = None
        self._domain_selector: Optional[DomainSelector] = None
        self._last_context: Optional[CrossDomainContextIR] = None

        # LLM Provider integration
        self._llm_provider: Optional[LLMProvider] = llm_provider
        self._last_llm_response: Optional[str] = None
        self._llm_metrics: Optional[Dict[str, Any]] = None

        # Path trigger policy and state machine (from path_trigger_policy)
        self._trigger_policy: Optional[ConfigDrivenTriggerPolicy] = None
        self._path_state_machine: Optional[PathStateMachine] = None
        self._event_counter: Optional[EventCounter] = None

        for path_name in self._config.paths:
            self._stats[path_name] = PathStats(path_name=path_name)

    # ---- Lifecycle ----

    def start(self) -> None:
        """Start the runtime engine: instantiate adapters, pools, scheduler, and timers."""
        self._running = True
        self._session_active = True
        self._instantiate_adapters()
        self._observation_pool = self._create_observation_pool()
        self._context_assembler = self._create_context_assembler()
        self._domain_selector = DomainSelector()

        # Initialize trigger policy from config + world params
        self._trigger_policy = ConfigDrivenTriggerPolicy(
            config=self._config,
            world_params=self._world_params,
        )
        self._path_state_machine = PathStateMachine()

        # Event counter for Slow Path auto-trigger (threshold from config)
        slow_event_threshold = 50
        slow_path = self._config.get_path("slow")
        if slow_path and slow_path.modules:
            for mc in slow_path.modules:
                if mc.trigger == "checkpoint":
                    slow_event_threshold = mc.trigger_config.get("event_count", 50)
                    break
        self._event_counter = EventCounter(threshold=slow_event_threshold)

        # Use PathAwareScheduler for task scheduling (backward-compatible with legacy CognitiveScheduler)
        self._scheduler = PathAwareScheduler(
            config=self._config,
            world_params=self._world_params,
        )

        self._optimizer = BayesianOptimizer(bounds={})
        self._feedback_signal = FeedbackSignal()
        self._checkpoint_count = 0

        # LLM Provider: from config or default to Mock for safety
        self._init_llm_provider()

        # Optimizer interval from WorldParams or default
        self._optimizer_interval = getattr(self._world_params, "optimizer_interval", 3)

        self._start_checkpoint_timer()
        logger.info(
            "CognitiveRuntimeEngine started — %d adapters + Pool + Context + "
            "PathAwareScheduler + Optimizer(interval=%d) + EventCounter(threshold=%d) + LLM=%s",
            len(self._adapters),
            self._optimizer_interval,
            slow_event_threshold,
            self._llm_provider.name if self._llm_provider else "None",
        )

    def stop(self) -> None:
        """Stop the runtime engine and release all resources."""
        self._running = False
        self._session_active = False
        self._cancel_checkpoint_timer()
        self._adapters.clear()
        self._event_buffer.clear()
        self._observation_pool = None
        self._context_assembler = None
        self._domain_selector = None
        self._last_context = None
        self._llm_provider = None
        self._last_llm_response = None
        self._llm_metrics = None
        self._trigger_policy = None
        self._path_state_machine = None
        self._event_counter = None
        if self._scheduler:
            self._scheduler.stop()
            self._scheduler = None
        self._optimizer = None
        self._feedback_signal = None
        logger.info("CognitiveRuntimeEngine stopped")

    # ---- Event-driven triggers ----

    def on_event(self, event: EventIR) -> Optional[str]:
        """Process a single user event through the Async Path.

        Also increments the event counter and auto-triggers Slow Path
        when the configured threshold is reached.

        Returns:
            LLM response string if LLM provider is available, else None.
        """
        if not self._running or not self._session_active:
            return None

        self._event_buffer.append(event)
        self._last_event_time = time.time()
        self._stats["async"].trigger_count += 1
        self._stats["async"].last_triggered_at = self._last_event_time

        # Update path state machine: async -> RUNNING
        if self._path_state_machine is not None:
            self._path_state_machine.transition("async", PathState.RUNNING)

        path_config = self._config.get_path("async")
        if not path_config:
            return None

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
                        # If result.data is not an ObservationBundle, skip
                        pass
                    logger.debug("Observation written to pool: %s", event.id)

                # Feed observation into context for downstream modules
                ctx.observations.append(result.data)
            else:
                pas.failure_count += 1

        # ---- Context Engineering: compile CrossDomainContextIR ----
        self._compile_context(event)

        # ---- LLM Generation: compile context → prompt → LLM → response ----
        llm_response = self._call_llm(event)
        if llm_response:
            self._last_llm_response = llm_response

        # ---- Feedback collection ----
        if self._feedback_signal and pas.success_count > 0:
            self._feedback_signal.with_implicit(accepted=(pas.failure_count == 0))

        # ---- Event counter and Slow Path auto-trigger ----
        if self._event_counter is not None:
            threshold_reached = self._event_counter.increment(n=1)
            if threshold_reached:
                logger.info(
                    "Event threshold reached (%d/%d), triggering Slow Path",
                    self._event_counter.count,
                    self._event_counter.threshold,
                )
                self.trigger_checkpoint()
                self._event_counter.reset()

        # ---- Path state: async -> IDLE (or BACKLOGGED if queue pressure) ----
        if self._path_state_machine is not None:
            if self._scheduler is not None and self._scheduler.get_queue(PathType.ASYNC):
                self._path_state_machine.transition("async", PathState.BACKLOGGED)
            else:
                self._path_state_machine.mark_success("async")

        return llm_response

    def on_session_end(self) -> None:
        """Trigger checkpoint on session end."""
        if not self._running:
            return
        self._session_active = False
        logger.info("Session ended, triggering checkpoint")
        self.trigger_checkpoint()

    def trigger_checkpoint(self) -> List[AdapterResult]:
        """Run the Slow Path (checkpoint) with ObservationPool data.

        Resets the event counter since we're doing a manual checkpoint.
        """
        if self._event_counter is not None:
            self._event_counter.reset()
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
            logger.debug(
                "Context compiled: %d entries, %d tokens",
                len(self._last_context.entries),
                self._last_context.total_tokens,
            )
        except Exception as e:
            logger.warning("Context compilation failed: %s", e)

    def _call_llm(self, event: EventIR) -> Optional[str]:
        """Compile context IR to prompt, call LLM, return response text.

        Args:
            event: The current user event (for extracting user text).

        Returns:
            LLM response text, or None if no provider or compilation failed.
        """
        if self._llm_provider is None:
            logger.debug("No LLM provider configured, skipping generation")
            return None
        if self._last_context is None:
            logger.debug("No compiled context, skipping generation")
            return None

        # Build system instruction from world params
        system_instruction = self._build_system_instruction()

        # Serialize IR to prompt
        prompt = self._last_context.to_prompt(
            system_instruction=system_instruction,
            max_tokens=self._world_params.compiler_token_budget,
        )

        # Append user message
        user_text = event.payload.get("text", "") if hasattr(event, "payload") else ""
        if user_text:
            prompt += f"\n[User]\n{user_text}\n"

        # Call LLM
        try:
            request = GenerateRequest(
                prompt=prompt,
                system_prompt=system_instruction,
                max_tokens=min(self._world_params.compiler_token_budget // 2, 1024),
                temperature=0.7,
                timeout_ms=30000,
            )
            result: GenerateResult = self._llm_provider.generate(request)
            self._llm_metrics = {
                "latency_ms": result.metrics.latency_ms,
                "input_tokens": result.metrics.input_tokens,
                "output_tokens": result.metrics.output_tokens,
                "success": result.metrics.success,
                "provider": result.metrics.provider_name,
                "model": result.metrics.model_id,
            }
            if result.metrics.success:
                logger.debug(
                    "LLM response received: %d chars, latency=%.0fms",
                    len(result.text), result.metrics.latency_ms,
                )
                return result.text
            else:
                logger.warning(
                    "LLM call failed: %s (provider=%s)",
                    result.metrics.error_type, result.metrics.provider_name,
                )
                return None
        except Exception as e:
            logger.warning("LLM generation error: %s", e)
            return None

    def _build_system_instruction(self) -> str:
        """Build system prompt from world params and engine state."""
        lines = [
            "You are DialogMesh, a context-aware AI assistant.",
            "You receive structured context from multiple knowledge domains.",
            "Respond based on the provided context, not general knowledge.",
        ]
        # Add engine state hints
        if self._last_context and self._last_context.primary_domain():
            lines.append(f"Primary context domain: {self._last_context.primary_domain()}")
        return "\n".join(lines)

    def _init_llm_provider(self) -> None:
        """Initialize LLM provider from config or environment.

        Priority:
          1. Already injected via constructor (self._llm_provider)
          2. runtime.yaml llm_provider config
          3. Environment variable DIALOGMESH_LLM_PROVIDER
          4. Default MockProvider (safe fallback)
        """
        if self._llm_provider is not None:
            return

        # Try config
        llm_config = self._config.metadata.get("llm_provider") if hasattr(self._config, "metadata") else None
        if llm_config:
            try:
                self._llm_provider = ProviderFactory.from_config(llm_config)
                logger.info("LLM provider loaded from config: %s", self._llm_provider.name)
                return
            except Exception as e:
                logger.warning("Failed to load LLM from config: %s", e)

        # Try environment
        env_provider = __import__("os").environ.get("DIALOGMESH_LLM_PROVIDER", "")
        if env_provider:
            try:
                if env_provider == "openai":
                    from core.agent.llm_providers.openai_provider import OpenAIProvider
                    self._llm_provider = OpenAIProvider("env-openai", {
                        "api_key": __import__("os").environ.get("OPENAI_API_KEY", ""),
                        "model": __import__("os").environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    })
                elif env_provider == "local":
                    from core.agent.llm_providers.local_provider import LocalProvider
                    self._llm_provider = LocalProvider("env-local", {
                        "backend": "ollama",
                        "model_path": __import__("os").environ.get("OLLAMA_MODEL", "qwen2.5:1.5b"),
                    })
                elif env_provider == "mock":
                    from core.agent.llm_providers.mock_provider import MockProvider
                    self._llm_provider = MockProvider("env-mock", {"response_text": "[Mock response]"})
                logger.info("LLM provider loaded from env: %s", env_provider)
                return
            except Exception as e:
                logger.warning("Failed to load LLM from env: %s", e)

        # Default: MockProvider (safe, no network)
        from core.agent.llm_providers.mock_provider import MockProvider
        self._llm_provider = MockProvider("default-mock", {
            "response_text": "[DialogMesh v4: LLM not configured. Set DIALOGMESH_LLM_PROVIDER or runtime.yaml llm_provider.]",
        })
        logger.info("LLM provider defaulted to Mock (safe fallback)")

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

    @property
    def last_llm_response(self) -> Optional[str]:
        return self._last_llm_response

    @property
    def llm_metrics(self) -> Optional[Dict[str, Any]]:
        return self._llm_metrics

    def _run_path(self, path_name: str) -> List[AdapterResult]:
        """Execute all modules in a named path, updating state machines and stats.

        Args:
            path_name: One of "async", "slow", "deep".

        Returns:
            List of AdapterResult from each module in the path.
        """
        if not self._running:
            return []

        path_config = self._config.get_path(path_name)
        if not path_config:
            return []

        self._stats[path_name].trigger_count += 1
        self._stats[path_name].last_triggered_at = time.time()

        # Update path state machine: path -> RUNNING
        if self._path_state_machine is not None:
            self._path_state_machine.transition(path_name, PathState.RUNNING)

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

        # Clear buffer after checkpoint
        if path_name == "slow":
            self._event_buffer.clear()
            self._checkpoint_count += 1

        # ---- Deep Path trigger evaluation ----
        # Only evaluate after Slow Path produces successful results
        if path_name == "slow" and results and any(r.ok for r in results):
            if self._trigger_policy is not None:
                # Gather stats for trigger evaluation
                async_stats = self._stats.get("async")
                success_count = async_stats.success_count if async_stats else 0
                failure_count = async_stats.failure_count if async_stats else 0
                total = success_count + failure_count
                success_rate = success_count / total if total > 0 else 0.0

                should_trigger_deep = self._trigger_policy.should_trigger(
                    "deep",
                    pattern_count=success_count,
                    success_count=success_count,
                    failure_count=failure_count,
                )
                if should_trigger_deep:
                    logger.info(
                        "Deep Path trigger condition met (pattern_count >= %d, "
                        "success_rate >= %.2f) — triggering Deep Path",
                        self._trigger_policy.get_trigger_config("deep").get("pattern_count", 5),
                        self._trigger_policy.get_trigger_config("deep").get("success_rate", 0.9),
                    )
                    self.trigger_deep()
                else:
                    logger.debug(
                        "Deep Path trigger conditions not met "
                        "(pattern_count=%d, success_rate=%.2f)",
                        success_count,
                        success_rate,
                    )

        # ---- Bayesian Optimizer step ----
        # Runs on configurable interval (from WorldParams or default 3)
        if path_name == "slow" and self._optimizer and self._feedback_signal:
            if self._optimizer_interval > 0 and self._checkpoint_count % self._optimizer_interval == 0:
                try:
                    reward = self._feedback_signal.composite_reward()
                    # Collect current top params
                    current_params = {
                        "min_support": self._world_params.backbone_weights.get("min_support", 8),
                        "community_resolution": self._world_params.community_resolution,
                        "compiler_max_nodes": self._world_params.compiler_max_nodes,
                    }
                    suggestion = self._optimizer.suggest()
                    if suggestion:
                        logger.info("Optimizer suggests: %s", suggestion)
                except Exception as e:
                    logger.debug("Optimizer step skipped: %s", e)

        # Update path state machine: path -> IDLE (or BACKLOGGED on failure)
        if self._path_state_machine is not None:
            path_success = any(r.ok for r in results) if results else False
            if path_success:
                self._path_state_machine.mark_success(path_name)
            else:
                self._path_state_machine.mark_failure(path_name)

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

    @property
    def scheduler(self) -> Optional[PathAwareScheduler]:
        """Access the underlying PathAwareScheduler (for diagnostics)."""
        return getattr(self, "_scheduler", None)

    @property
    def path_states(self) -> Optional[Dict[str, str]]:
        """Return current state of all paths as a read-only snapshot.

        Returns:
            Mapping of path_name -> state string ("idle" | "running" | "backlogged").
        """
        if self._path_state_machine is None:
            return None
        return {
            name: state.value
            for name, state in self._path_state_machine.all_states().items()
        }

    @property
    def event_counter(self) -> Optional[int]:
        """Current event counter value, or None if not initialized."""
        if self._event_counter is None:
            return None
        return self._event_counter.count
