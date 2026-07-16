"""PathAwareScheduler: path-aware scheduling with state-machine paths.

Replaces ``CognitiveScheduler`` with:
- Per-path state machine (idle → running → backlogged → idle)
- Event counter for automatic Slow Path triggering
- Deep Path trigger evaluation based on runtime stats
- Full backward compatibility with the old ``CognitiveScheduler`` API
"""
from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

# Lazy import to avoid pulling in heavy dependencies (yaml, networkx)
# when only the scheduler is needed.
RuntimeConfig = None  # type: ignore
load_runtime_config = None  # type: ignore
build_default_config = None  # type: ignore

def _ensure_runtime_config():
    global RuntimeConfig, load_runtime_config, build_default_config
    if RuntimeConfig is None:
        import importlib
        config_mod = importlib.import_module('core.agent.v4.runtime.config')
        RuntimeConfig = config_mod.RuntimeConfig
        load_runtime_config = config_mod.load_runtime_config
        build_default_config = config_mod.build_default_config
    return RuntimeConfig, load_runtime_config, build_default_config

from .path_models import (
    PathTask,
    PathTaskStatus,
    PathState,
    PathType,
    PathWorkerPool,
    PathWorker,
    PathTaskMetrics,
)
from .path_policy import PathSchedulerPolicy, PriorityPathPolicy


@dataclass
class PathSnapshot:
    """Snapshot of a single path's state."""

    path: PathType
    state: PathState
    pending: int = 0
    running: int = 0
    success: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    last_triggered_at: float = 0.0


class PathStateMachine:
    """Finite state machine for a single processing path.

    States::

        idle → running → backlogged → idle
    """

    def __init__(self, path: PathType):
        self.path = path
        self.state = PathState.IDLE
        self._lock = threading.Lock()

    def transition(self, new_state: PathState) -> None:
        """Transition to *new_state* if valid."""
        with self._lock:
            valid = self._valid_transition(self.state, new_state)
            if valid:
                self.state = new_state

    @staticmethod
    def _valid_transition(old: PathState, new: PathState) -> bool:
        """Return ``True`` if *old* → *new* is a valid transition."""
        transitions = {
            PathState.IDLE: {PathState.RUNNING},
            PathState.RUNNING: {PathState.BACKLOGGED, PathState.IDLE},
            PathState.BACKLOGGED: {PathState.IDLE, PathState.RUNNING},
        }
        return new in transitions.get(old, set())

    def enter_running(self) -> None:
        self.transition(PathState.RUNNING)

    def enter_backlogged(self) -> None:
        self.transition(PathState.BACKLOGGED)

    def enter_idle(self) -> None:
        self.transition(PathState.IDLE)


class PathAwareScheduler:
    """Path-aware scheduler with per-path state machines and auto-trigger logic.

    Backward-compatible API with ``CognitiveScheduler``:

    - ``submit(task)`` – accepts ``PathTask`` or legacy ``Task``
    - ``tick()`` – single scheduling step
    - ``run_loop(...)`` / ``stop()`` – lifecycle
    - ``stats()`` – returns aggregate statistics

    New features:

    - ``path_states`` – ``Dict[PathType, PathStateMachine]``
    - ``event_counter`` – counts async events for Slow Path auto-trigger
    - ``evaluate_deep_trigger()`` – checks pattern_count + success_rate
    - ``trigger_path(path)`` – manually trigger a path
    """

    def __init__(
        self,
        policy: PathSchedulerPolicy = None,
        pool: PathWorkerPool = None,
        config: RuntimeConfig = None,
        world_params: WorldParams = None,
        registry=None,
        chunk_registry=None,
    ):
        self.policy = policy or PriorityPathPolicy()
        self.pool = pool or PathWorkerPool(size=4)
        _ensure_runtime_config()
        self.config = config or build_default_config()
        self.world_params = world_params
        if self.world_params is None:
            from core.agent.v4.world.params import get_world_params
            self.world_params = get_world_params()
        self._registry = registry

        # Chunk strategy registry for document ingestion (DIL)
        self._chunk_registry = chunk_registry

        # Queues per path
        self._queues: Dict[PathType, List[PathTask]] = {
            PathType.ASYNC: [],
            PathType.SLOW: [],
            PathType.DEEP: [],
            PathType.FAST: [],
        }

        # Path state machines
        self.path_states: Dict[PathType, PathStateMachine] = {
            path: PathStateMachine(path) for path in PathType
        }

        # Per-path metrics
        self._path_metrics: Dict[PathType, Dict[str, Any]] = {
            path: {
                "trigger_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_latency_ms": 0.0,
                "last_triggered_at": 0.0,
            }
            for path in PathType
        }

        # Event counter for Slow Path auto-trigger
        self._event_counter: int = 0
        self._event_counter_lock = threading.Lock()

        # Running flag
        self._running = False

        # Trigger thresholds (loaded from config / world params)
        self._slow_event_threshold: int = 50
        self._deep_pattern_threshold: int = 5
        self._deep_success_rate_threshold: float = 0.9
        self._load_thresholds()

    # ---- Configuration loading ----

    def _load_thresholds(self) -> None:
        """Load trigger thresholds from ``runtime.yaml`` and ``WorldParams``."""
        # Slow path: event_count from config
        slow_config = self.config.get_path("slow")
        if slow_config and slow_config.modules:
            for mc in slow_config.modules:
                if mc.trigger == "checkpoint":
                    self._slow_event_threshold = mc.trigger_config.get(
                        "event_count", 50
                    )
                    break

        # Deep path: pattern_count + success_rate from config
        deep_config = self.config.get_path("deep")
        if deep_config and deep_config.modules:
            for mc in deep_config.modules:
                if mc.trigger == "threshold":
                    self._deep_pattern_threshold = mc.trigger_config.get(
                        "pattern_count", 5
                    )
                    self._deep_success_rate_threshold = mc.trigger_config.get(
                        "success_rate", 0.9
                    )
                    break

        # WorldParams overrides (if present)
        if hasattr(self.world_params, "slow_event_threshold"):
            self._slow_event_threshold = self.world_params.slow_event_threshold
        if hasattr(self.world_params, "deep_pattern_threshold"):
            self._deep_pattern_threshold = self.world_params.deep_pattern_threshold
        if hasattr(self.world_params, "deep_success_rate_threshold"):
            self._deep_success_rate_threshold = self.world_params.deep_success_rate_threshold

    # ---- Backward-compatible API ----

    def submit(self, task: Any) -> None:
        """Submit a task to the appropriate path queue.

        Accepts ``PathTask`` (preferred) or legacy ``Task`` objects.
        """
        if isinstance(task, PathTask):
            path = task.path
        else:
            # Legacy task: infer path from task_id heuristics
            tid = getattr(task, "task_id", "")
            if "obs" in tid:
                path = PathType.ASYNC
            elif "hyp" in tid:
                path = PathType.SLOW
            elif "kn" in tid:
                path = PathType.SLOW
            elif "sk" in tid:
                path = PathType.DEEP
            else:
                path = PathType.ASYNC
            # Wrap in a PathTask adapter if needed
            task = _LegacyTaskAdapter(task, path)

        self._queues[path].append(task)

    def tick(self) -> List[Any]:
        """Execute one scheduling tick: select task, assign worker, run.

        Returns:
            List of results from executed tasks (usually 0 or 1).
        """
        results: List[Any] = []

        # Flatten all queues for selection (priority across paths)
        all_tasks: List[PathTask] = []
        for path, queue in self._queues.items():
            all_tasks.extend(queue)

        task = self.policy.select_task(all_tasks)
        if task is None:
            return results

        worker = self.policy.assign_worker(task, self.pool)
        if worker is None:
            # No idle worker → mark path as backlogged
            self.path_states[task.path].enter_backlogged()
            return results

        # Remove from its queue
        self._queues[task.path].remove(task)

        # Update path state
        self.path_states[task.path].enter_running()

        # Execute
        start = time.time()
        try:
            result = worker.run(task)
            results.append(result)
            self._record_success(task.path, start)
        except Exception:
            self._record_failure(task.path, start)
        finally:
            self.pool.release(worker)
            # Check if queue is empty → idle
            if not self._queues[task.path]:
                self.path_states[task.path].enter_idle()
            else:
                self.path_states[task.path].enter_backlogged()

        return results

    def run_loop(self, max_ticks: int = -1, interval_ms: int = 100) -> None:
        """Run the scheduler loop."""
        self._running = True
        ticks = 0
        while self._running and (max_ticks < 0 or ticks < max_ticks):
            self.tick()
            ticks += 1
            time.sleep(interval_ms / 1000.0)

    def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False

    def stats(self) -> Dict[str, Any]:
        """Return aggregate scheduler statistics."""
        snapshots = {
            path.value: PathSnapshot(
                path=path,
                state=self.path_states[path].state,
                pending=len(self._queues[path]),
                running=len(self.pool.workers_for_path(path)),
                success=self._path_metrics[path]["success_count"],
                failures=self._path_metrics[path]["failure_count"],
                total_latency_ms=self._path_metrics[path]["total_latency_ms"],
                last_triggered_at=self._path_metrics[path]["last_triggered_at"],
            )
            for path in PathType
        }
        return {
            "queue_size": sum(len(q) for q in self._queues.values()),
            "workers": self.pool.stats(),
            "path_snapshots": {
                path.value: {
                    "state": snap.state.value,
                    "pending": snap.pending,
                    "running": snap.running,
                    "success": snap.success,
                    "failures": snap.failures,
                    "total_latency_ms": snap.total_latency_ms,
                    "last_triggered_at": snap.last_triggered_at,
                }
                for path, snap in snapshots.items()
            },
            "event_counter": self._event_counter,
            "deep_trigger_ready": self.evaluate_deep_trigger(),
        }

    # ---- New path-aware API ----

    def submit_to_path(self, task: PathTask, path: PathType = None) -> None:
        """Submit a task explicitly to a given path.

        Args:
            task: The task to submit.
            path: Override path (defaults to ``task.path``).
        """
        target = path or task.path
        task.path = target
        self._queues[target].append(task)

    def trigger_path(self, path: PathType) -> List[Any]:
        """Manually trigger execution of all tasks in *path* queue.

        Returns:
            Results from executed tasks.
        """
        results: List[Any] = []
        queue = self._queues[path]
        while queue:
            task = self.policy.select_task(queue)
            if task is None:
                break
            worker = self.policy.assign_worker(task, self.pool)
            if worker is None:
                self.path_states[path].enter_backlogged()
                break
            queue.remove(task)
            self.path_states[path].enter_running()
            start = time.time()
            try:
                result = worker.run(task)
                results.append(result)
                self._record_success(path, start)
            except Exception:
                self._record_failure(path, start)
            finally:
                self.pool.release(worker)
        if not queue:
            self.path_states[path].enter_idle()
        else:
            self.path_states[path].enter_backlogged()
        return results

    def increment_event_counter(self, count: int = 1) -> bool:
        """Increment the async event counter and check Slow Path trigger.

        Args:
            count: Number of events to add.

        Returns:
            ``True`` if the Slow Path threshold was reached.
        """
        with self._event_counter_lock:
            self._event_counter += count
            return self._event_counter >= self._slow_event_threshold

    def reset_event_counter(self) -> None:
        """Reset the event counter (typically after Slow Path trigger)."""
        with self._event_counter_lock:
            self._event_counter = 0

    def evaluate_deep_trigger(self) -> bool:
        """Evaluate whether Deep Path should be triggered.

        Condition::

            pattern_count >= threshold AND success_rate >= threshold

        Returns:
            ``True`` if Deep Path trigger conditions are met.
        """
        # Use async path stats as proxy for pattern accumulation
        async_metrics = self._path_metrics[PathType.ASYNC]
        total = async_metrics["success_count"] + async_metrics["failure_count"]
        if total == 0:
            return False
        success_rate = async_metrics["success_count"] / total
        pattern_count = async_metrics["success_count"]  # proxy
        return (
            pattern_count >= self._deep_pattern_threshold
            and success_rate >= self._deep_success_rate_threshold
        )

    def get_path_state(self, path: PathType) -> PathState:
        """Return the current state of *path*."""
        return self.path_states[path].state

    def get_queue(self, path: PathType) -> List[PathTask]:
        """Return the task queue for *path* (read-only copy)."""
        return list(self._queues[path])

    # ---- Document Ingestion Layer (DIL) integration ----

    def select_chunk_strategy(self, context, constraints=None):
        """Select the best chunk strategy for document ingestion.

        Args:
            context: TaskContext (file_type, doc_size_chars, doc_depth, ...).
            constraints: RuntimeConstraints (max_latency_ms, llm_available, ...).

        Returns:
            ChunkStrategy instance, or None if no registry configured.
        """
        if self._chunk_registry is None:
            try:
                from core.agent.v4.chunking.strategies import default_registry
                self._chunk_registry = default_registry()
            except Exception as e:
                logger.warning("Failed to load default chunk registry: %s", e)
                return None
        try:
            return self._chunk_registry.select(context, constraints)
        except Exception as e:
            logger.warning("Chunk strategy selection failed: %s", e)
            return None

    # ---- Internal ----

    def _record_success(self, path: PathType, start_time: float) -> None:
        elapsed = (time.time() - start_time) * 1000.0
        self._path_metrics[path]["success_count"] += 1
        self._path_metrics[path]["total_latency_ms"] += elapsed
        self._path_metrics[path]["last_triggered_at"] = time.time()
        self._path_metrics[path]["trigger_count"] += 1

    def _record_failure(self, path: PathType, start_time: float) -> None:
        elapsed = (time.time() - start_time) * 1000.0
        self._path_metrics[path]["failure_count"] += 1
        self._path_metrics[path]["total_latency_ms"] += elapsed
        self._path_metrics[path]["last_triggered_at"] = time.time()
        self._path_metrics[path]["trigger_count"] += 1


class _LegacyTaskAdapter(PathTask):
    """Adapter wrapping a legacy ``Task`` into a ``PathTask``."""

    def __init__(self, legacy_task: Any, path: PathType):
        super().__init__(
            task_id=getattr(legacy_task, "task_id", f"legacy_{id(legacy_task)}"),
            path=path,
            priority=getattr(legacy_task, "priority", 0),
            max_retries=getattr(legacy_task, "max_retries", 3),
            timeout_ms=getattr(legacy_task, "timeout_ms", 30000),
        )
        self._legacy = legacy_task

    def execute(self) -> Any:
        return self._legacy.execute()

    def on_complete(self, result: Any) -> None:
        super().on_complete(result)
        self._legacy.on_complete(result)

    def on_failure(self, error: Exception) -> None:
        super().on_failure(error)
        self._legacy.on_failure(error)

    def on_cancel(self) -> None:
        super().on_cancel()
        self._legacy.on_cancel()
