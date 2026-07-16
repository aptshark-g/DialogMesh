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
    SkillSource, WorldSource,
)
from core.agent.v4.context.topic_tree_source import TopicTreeContextSource
from core.agent.v4.compiler.content_index import ContentIndex
from core.agent.v4.compiler.index_source import IndexSource
from core.agent.v4.conversation.tracker import ConversationTracker
from core.agent.v4.compiler.discourse_block_tree import DiscourseBlockTreeManager
from core.agent.v4.causal.planner import CausalPlanner, CausalContextSource
from core.agent.v4.context.domain_selector import DomainSelector
from core.agent.v4.context.cross_domain_ir import CrossDomainContextIR
from core.agent.v4.compiler.perspective_planner import PerspectivePlanner, Perspective
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
from core.agent.v4.cognitive_scheduler.path_models import PathType, PathState
from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    ConfigDrivenTriggerPolicy, EventCounter, PathStateMachine,
)
from core.agent.v4.cognitive_scheduler.tasks import (
    ObservationTask, HypothesisTask, KnowledgeTask, SkillTask,
)

from core.agent.v4.behavior_graph.adapter import BehaviorGraphAdapter, BehaviorGraphState
from core.agent.v4.causal_substrate.adapter import CausalSubstrateAdapter, CausalContextEntry
from core.agent.v4.runtime.event_log_adapter import V4EventLog, EventLogConfig

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
        self._perspective_planner: Optional[PerspectivePlanner] = None
        self._last_context: Optional[CrossDomainContextIR] = None

        # v3_2 adapters (BehaviorGraph, CausalSubstrate, EventLog)
        self._behavior_graph_adapter: Optional[BehaviorGraphAdapter] = None
        self._causal_substrate_adapter: Optional[CausalSubstrateAdapter] = None
        self._event_log: Optional[V4EventLog] = None

        # CausalPlanner: unified v4 adapter for v3_2 BehaviorGraph + CausalSubstrate
        self._causal_planner: Optional[CausalPlanner] = None

        # ConversationTracker: multi-dimensional follow-up disambiguation
        self._conversation_tracker = ConversationTracker()
        # DiscourseBlockTree: conversation-to-tree compiler
        self._discourse_tree = DiscourseBlockTreeManager()

        # User cognitive profile (dual-track: Track A dynamics + Track B tags)
        self._cognitive_profile: Optional[object] = None  # CognitiveProfileV2

        # Extraction orchestration (regex / LMStudio / DeepSeek with fallback)
        self._extraction_orchestrator = None  # ExtractionOrchestrator set in start()

        # Behavior tracking: record user navigation edges in RelationSubstrate
        self._last_concept: Optional[str] = None
        self._content_provider = None  # set by _create_context_assembler

        # TopicTree + DiscourseBlockTree: hierarchical conversation context
        self._topic_tree_source: Optional[TopicTreeContextSource] = None

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
        self._perspective_planner = PerspectivePlanner()

        # Initialize v3_2 adapters via CausalPlanner (unified interface)
        self._causal_planner = CausalPlanner()

        # ---- Extraction Orchestrator (regex → jieba → stanza → LMStudio → DeepSeek) ----
        self._init_extraction_orchestrator()

        self._behavior_graph_adapter = BehaviorGraphAdapter(
            graph_path="data/behavior_graph.json",
            auto_save=True,
        )
        self._causal_substrate_adapter = CausalSubstrateAdapter(
            name="causal_substrate",
            params={"min_chain": 10},
        )
        self._event_log = V4EventLog(EventLogConfig())

        # Initialize trigger policy from config + world params
        self._trigger_policy = ConfigDrivenTriggerPolicy(
            config=self._config,
            world_params=self._world_params,
        )
        self._path_state_machine = PathStateMachine()

        # Event counter for Slow Path auto-trigger (from ParameterRegistry, velocity-adjusted)
        slow_event_threshold = self._get_slow_threshold()
        self._event_counter = EventCounter(threshold=slow_event_threshold)
        self._slow_threshold_base = slow_event_threshold
        self._last_threshold_adjust = time.time()

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
            "PathAwareScheduler + Optimizer(interval=%d) + EventCounter(threshold=%d) + "
            "LLM=%s + EventLog=%s",
            len(self._adapters),
            self._optimizer_interval,
            slow_event_threshold,
            self._llm_provider.name if self._llm_provider else "None",
            "active" if self._event_log and self._event_log.is_open else "inactive",
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
        # Close v3_2 adapters
        if self._event_log is not None:
            self._event_log.close()
            self._event_log = None
        self._behavior_graph_adapter = None
        self._causal_substrate_adapter = None
        self._causal_planner = None
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

        # ---- ConversationTracker: record turn for follow-up disambiguation ----
        text = event.payload.get("text", "") if hasattr(event, "payload") else ""
        if text:
            # Extract concepts from text for content-overlap scoring
            concepts = self._extract_concepts_from_text(text)
            self._conversation_tracker.add_turn(text, concepts=concepts)

            # Feed DiscourseBlockTree for conversation tree structure
            sid = event.payload.get('session_id', 'default') if hasattr(event, 'payload') else 'default'
            self._discourse_tree.feed(text, sid, history=None)

            # Record behavior edge: user navigated from previous concept
            # Semantic filter: only record if concept exists in world model
            if self._content_provider and concepts:
                curr = concepts[0] if concepts else None
                objects = getattr(self, '_world_objects', {})
                # Filter: keep only concepts that match objects in store
                valid = [c for c in concepts if c in objects]
                if curr and self._last_concept and valid:
                    self._content_provider.add_behavior_edge(
                        self._last_concept, valid[0])
                # Also check case-insensitive match
                if not valid and objects:
                    for obj_name in objects:
                        if obj_name.lower() == curr.lower():
                            valid.append(obj_name)
                            break
                self._last_concept = valid[0] if valid else (curr if curr else None)

        # ---- EventLog persistence ----
        if self._event_log is not None:
            try:
                self._event_log.record_event(event, trace_id=event.id)
                logger.debug("Event persisted to EventLog: %s", event.id)
            except Exception as e:
                logger.warning("EventLog record failed: %s", e)

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

        # ---- BehaviorGraph: record event as step ----
        if self._causal_planner is not None:
            try:
                edge_id = self._causal_planner.record_step(
                    event, success=True, correction=False,
                )
                if edge_id:
                    logger.debug("CausalPlanner edge recorded: %s", edge_id)
            except Exception as e:
                logger.warning("CausalPlanner record_step failed: %s", e)
        # Legacy fallback via BehaviorGraphAdapter
        elif self._behavior_graph_adapter is not None:
            try:
                step_id = self._behavior_graph_adapter.record_event(event, success=True)
                if step_id:
                    logger.debug("BehaviorGraphAdapter step recorded: %s", step_id)
            except Exception as e:
                logger.warning("BehaviorGraphAdapter record failed: %s", e)

        # ---- CausalPlanner: trigger causal processing if chain long enough ----
        if self._causal_planner is not None:
            try:
                recent = self._causal_planner.get_recent_chain(max_steps=10)
                if len(recent) > CausalPlanner.MIN_CHAIN_LEN:
                    chain_result = self._causal_planner.process_chain()
                    if chain_result.triggered and chain_result.edge_updates:
                        logger.info(
                            "CausalPlanner triggered: %d priors updated from chain of %d",
                            len(chain_result.edge_updates), len(recent),
                        )
            except Exception as e:
                logger.debug("CausalPlanner trigger failed: %s", e)
        # Legacy fallback via CausalSubstrateAdapter
        elif self._causal_substrate_adapter is not None and self._behavior_graph_adapter is not None:
            try:
                recent = self._behavior_graph_adapter.get_recent_chain(n_steps=10)
                chain_len = len(recent.steps) if recent else 0
                if self._causal_substrate_adapter.should_trigger(chain_len):
                    ctx.world_graph = self._behavior_graph_adapter.graph
                    result = self._causal_substrate_adapter.execute(ctx)
                    if result.ok and result.data.get("triggered"):
                        logger.info(
                            "CausalSubstrate triggered: %d priors updated from chain of %d",
                            result.data.get("entry_count", 0), chain_len,
                        )
            except Exception as e:
                logger.debug("CausalSubstrate trigger failed: %s", e)

        # ---- LLM Generation: compile context → prompt → LLM → response ----
        llm_response = self._call_llm(event)
        if llm_response:
            self._last_llm_response = llm_response

        # ---- Multi-hop subgraph refinement ----
        # If LLM response indicates missing context (asks about specific concepts),
        # expand subgraph for those concepts and re-call LLM. Max 3 rounds.
        llm_response = self._multi_hop_refine(event, llm_response, max_hops=3)
        if llm_response:
            self._last_llm_response = llm_response

        # ---- Memory Point extraction (dialogue tree → capacitor model) ----
        # ---- Feed cognitive profile from current turn ----
        self._feed_profile(text, llm_response)
        if self._memory_manager is not None and text and llm_response:
            try:
                turn_num = event.metadata.get("turn_number", 1) if hasattr(event, "metadata") else 1
                self._memory_manager.ingest_turn(
                    user_text=text,
                    system_response=llm_response or "",
                    turn_number=int(turn_num),
                )
            except Exception as e:
                logger.debug("MemoryPoint extraction skipped: %s", e)

        # ---- Behavior chain: feed conversation patterns to CausalPlanner ----
        if self._causal_planner is not None and text:
            try:
                pattern = self._conversation_tracker.behavior_pattern
                topic = self._conversation_tracker.get_current_topic()
                action_type = pattern[-1] if pattern else "unknown"
                action_summary = text[:120]
                if topic and action_type == "drill_down":
                    action_summary = f"[follow-up on: {topic[:60]}] {text[:60]}"
                self._causal_planner.record_step(
                    EventIR(id=f"behavior_{event.id}", kind="conversation.pattern",
                           payload={"text": text, "pattern": action_type, "topic": topic}),
                    success=True, correction=False,
                )
                logger.debug("Behavior chain fed: pattern=%s topic=%s", action_type, topic[:40] if topic else None)
            except Exception as e:
                logger.debug("CausalPlanner behavior feed skipped: %s", e)

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
                # Semantic extraction on Slow Path
                self._slow_extract()

        # ---- Path state: async -> IDLE (or BACKLOGGED if queue pressure) ----
        if self._path_state_machine is not None:
            if self._scheduler is not None and self._scheduler.get_queue(PathType.ASYNC):
                self._path_state_machine.transition("async", PathState.BACKLOGGED)
            else:
                self._path_state_machine.mark_success("async")

        # ---- Feed discourse tree compiler for hierarchical topic tracking ----
        if self._topic_tree_source is not None and text:
            try:
                turn_num = self._stats.get('async', PathStats('async')).trigger_count
                self._topic_tree_source.feed_turn(turn_index=int(turn_num), text=text)
            except Exception as e:
                logger.debug('TopicTree feed skipped: %s', e)

        return llm_response

    def on_session_end(self) -> None:
        """Trigger checkpoint on session end."""
        if not self._running:
            return
        self._session_active = False

        # Persist memory points (capacitor model survives across sessions)
        if self._memory_manager is not None and self._profile_store is not None:
            try:
                self._memory_manager.persist(self._profile_store)
                logger.info("Memory points persisted (%d points)",
                           len(self._cognitive_profile.memory_points))
            except Exception as e:
                logger.warning("Memory persist skipped: %s", e)

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

        Conversation memory: prior turns are injected as context entries
        and used to enrich retrieval queries for follow-up questions.

        v4.1: PerspectivePlanner decides HOW to observe (strategy, horizon,
        domain allocation) before the assembler runs. This replaces the
        flat domain matrix with perspective-aware context compilation.
        """
        if self._context_assembler is None or self._domain_selector is None:
            return

        text = event.payload.get("text", "") if hasattr(event, "payload") else ""

        # ---- Enrich query with conversation history ----
        enriched_text = self._enrich_query_with_history(text)

        # ---- Perspective: decide how to observe ----
        token_budget = self._world_params.compiler_token_budget
        # Infer expectation type from query + conversation context
        expectation = self._infer_expectation(text)
        perspectives = self._perspective_planner.plan_multi(
            enriched_text, token_budget=token_budget,
            expectation=expectation)
        perspective = perspectives[0]  # primary for pipeline
        self._last_perspective = perspective  # expose for logging

        # Perspective-aware domain boosts override default matrix
        domain_boosts = self._get_domain_boosts(event)
        for domain, weight in perspective.domains.items():
            domain_boosts[domain] = domain_boosts.get(domain, 0) + weight * 0.5

        try:
            self._last_context = self._context_assembler.assemble_ir(
                enriched_text,
                token_budget=token_budget,
                domain_boosts=domain_boosts,
            )
        except Exception as e:
            logger.warning("Context compilation failed: %s", e)
            return

        # ---- Inject cognitive profile (always, regardless of domain allocation) ----
        self._inject_cognitive_profile()

        # ---- Inject conversation history as context entries ----
        self._inject_conversation_history(event)

        # ---- Inject topic tree context (hierarchical discourse, backtracking) ----
        self._inject_topic_tree_context(event)

        # ---- Inject CausalPlanner context (unified BehaviorGraph + CausalSubstrate) ----
        if self._causal_planner is not None and self._last_context is not None:
            try:
                from core.agent.v4.context.cross_domain_ir import IREntry

                # Inject recent behavior steps
                recent_steps = self._causal_planner.get_recent_chain(max_steps=5)
                for step in recent_steps:
                    self._last_context.add_entry(
                        domain="B",
                        entry=IREntry(
                            domain="B",
                            type="behavior_step",
                            content=f"[{step.action_type}] {step.action_summary}",
                            confidence=0.5,
                            estimated_tokens=(len(step.action_summary) + 20) // 4,
                            metadata={"step_id": step.step_id, "event_id": step.event_id},
                        ),
                    )

                # Inject causal edges if query hints at causality
                causal_keywords = {"why", "because", "cause", "lead", "result", "trigger"}
                if any(kw in text.lower() for kw in causal_keywords):
                    chain = self._causal_planner.get_chain(
                        start_event_id=recent_steps[-1].event_id if recent_steps else "",
                        max_depth=3,
                    )
                    for step_ir, edge_ir in chain:
                        self._last_context.add_entry(
                            domain="K",
                            entry=IREntry(
                                domain="K",
                                type="causal_prior",
                                content=(
                                    f"Causal: {edge_ir.from_step_id} -> {edge_ir.to_step_id} "
                                    f"(prior={edge_ir.structural_prior:.2f})"
                                ),
                                confidence=edge_ir.structural_prior,
                                estimated_tokens=30,
                                metadata={
                                    "edge_id": edge_ir.edge_id,
                                    "structural_prior": edge_ir.structural_prior,
                                    "weight": edge_ir.weight,
                                },
                            ),
                        )
            except Exception as e:
                logger.debug("CausalPlanner context injection failed: %s", e)

            # ---- Semantic World Model additional context ----
            self._inject_semantic_world(event, text, perspectives)

        elif self._behavior_graph_adapter is not None and self._last_context is not None:
            try:
                from core.agent.v4.context.cross_domain_ir import IREntry

                recent = self._behavior_graph_adapter.get_recent_chain(n_steps=5)
                for step in recent.steps:
                    self._last_context.add_entry(
                        domain="B",
                        entry=IREntry(
                            domain="B",
                            type="behavior_step",
                            content=f"[{step.action_type}] {step.action_summary}",
                            confidence=step.edge_weight,
                            estimated_tokens=(len(step.action_summary) + 20) // 4,
                            metadata={"step_id": step.step_id},
                        ),
                    )

                # Inject causal edges if query hints at causality
                causal_keywords = {"why", "because", "cause", "lead", "result", "trigger"}
                if any(kw in text.lower() for kw in causal_keywords):
                    for edge in recent.edges:
                        prior = edge.get("structural_prior", 0.0)
                        if prior > 0.0:
                            self._last_context.add_entry(
                                domain="K",
                                entry=IREntry(
                                    domain="K",
                                    type="causal_prior",
                                    content=(
                                        f"Causal: {edge.get('from_step_id', '')} -> "
                                        f"{edge.get('to_step_id', '')} (prior={prior:.2f})"
                                    ),
                                    confidence=prior,
                                    estimated_tokens=30,
                                    metadata={"edge_id": edge.get("edge_id", ""), "structural_prior": prior},
                                ),
                            )
            except Exception as e:
                logger.debug("BehaviorGraph context injection failed: %s", e)

        # ---- Inject EventLog replay context ----
        if self._event_log is not None and self._last_context is not None:
            try:
                from core.agent.v4.context.cross_domain_ir import IREntry

                replay_events = self._event_log.replay_unconsumed(limit=5)
                for ev in replay_events:
                    ev_text = ev.payload.get("text", "") if hasattr(ev, "payload") else ""
                    if not ev_text:
                        continue
                    self._last_context.add_entry(
                        domain="C",
                        entry=IREntry(
                            domain="C",
                            type="event_log_replay",
                            content=ev_text,
                            confidence=0.4,
                            estimated_tokens=len(ev_text) // 4,
                            metadata={"event_id": ev.id, "kind": ev.kind},
                        ),
                    )
                # Mark replayed events as consumed to avoid duplication
                for ev in replay_events:
                    self._event_log.ack_event(ev.id)
            except Exception as e:
                logger.debug("EventLog replay injection failed: %s", e)

        # Recalculate totals after injection
        if self._last_context is not None:
            self._last_context.recalc_total()
            logger.debug(
                "Context compiled: %d entries, %d tokens (with v3_2 injection)",
                len(self._last_context.entries),
                self._last_context.total_estimated_tokens,
            )

    def _enrich_query_with_history(self, current_text: str) -> str:
        """Multi-dimensional follow-up disambiguation via ConversationTracker.

        Uses temporal proximity, content overlap, and behavior patterns
        to resolve follow-ups to the correct prior topic. Much smarter than
        just prepending the prior turn.
        """
        return self._conversation_tracker.enrich(current_text)

    def _inject_conversation_history(self, current_event: EventIR) -> None:
        """Inject conversation history + topic info via ConversationTracker."""
        if self._last_context is None:
            return
        from core.agent.v4.context.cross_domain_ir import IREntry

        history = self._conversation_tracker.get_history_entries(max_entries=5)
        for entry in history:
            self._last_context.add_entry(
                domain="C",
                entry=IREntry(
                    domain="C", type="conversation_history",
                    content=f"[User T{entry['turn']}] {entry['text']}",
                    confidence=0.9,
                    estimated_tokens=len(entry['text']) // 4,
                ),
            )

        # Inject topic info if available
        topic = self._conversation_tracker.get_current_topic()
        behavior = self._conversation_tracker.behavior_pattern
        if topic or behavior:
            parts = []
            if topic:
                parts.append(f"Current topic: {topic[:100]}")
            if behavior:
                parts.append(f"Behavior: {' → '.join(behavior[-4:])}")
            self._last_context.add_entry(
                domain="C",
                entry=IREntry(
                    domain="C", type="topic_context",
                    content=" | ".join(parts),
                    confidence=0.8,
                    estimated_tokens=len(" | ".join(parts)) // 4,
                ),
            )

        self._last_context.recalc_total()

    def _inject_topic_tree_context(self, current_event: EventIR) -> None:
        if self._last_context is None:
            return
        from core.agent.v4.context.cross_domain_ir import IREntry

        # DiscourseBlockTree: conversation tree structure
        try:
            session_id = getattr(current_event, 'session_id', 'default')
            tree_ctx = self._discourse_tree.build_context(session_id)
            if tree_ctx:
                self._last_context.add_entry(domain='C', entry=IREntry(
                    domain='C', type='discourse_tree',
                    content=f"[Conversation Tree]\n{tree_ctx}",
                    confidence=0.7, estimated_tokens=len(tree_ctx) // 4,
                ))
        except Exception as e:
            logger.debug("DiscourseBlockTree injection skipped: %s", e)

        # Legacy TopicTree
        if self._topic_tree_source and self._topic_tree_source.has_context():
            try:
                text = current_event.payload.get('text', '') if hasattr(current_event, 'payload') else ''
                items = self._topic_tree_source.retrieve(text, top_k=3, expand_macro=True)
                for item in items:
                    self._last_context.add_entry(domain='C', entry=IREntry(
                        domain='C', type=item.metadata.get('type', 'discourse'),
                        content=item.text, confidence=item.relevance,
                        estimated_tokens=len(item.text) // 4,
                    ))
            except Exception as e:
                logger.debug("TopicTree context injection skipped: %s", e)
        self._last_context.recalc_total()

    @staticmethod
    def _extract_concepts_from_text(text: str) -> List[str]:
        """Extract concept names using JiebaRelationParser entity detection.

        No stop words. No regex segmentation. Just entity extraction.
        Only records concepts that appear in SemanticObject store.
        """
        try:
            from core.agent.v4.tiered.jieba_parser import JiebaRelationParser
            jrp = JiebaRelationParser()
            tuples = jrp.extract(text)
            entities = set()
            for t in tuples:
                entities.add(t["subject"])
                obj = t.get("object", "")
                if obj and len(obj) >= 2:
                    entities.add(obj)
            # Also grab CamelCase from raw text
            import re
            for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text):
                if len(m.group()) >= 4:
                    entities.add(m.group())
            return list(entities)[:5]
        except Exception:
            import re
            return [m.group() for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text)][:5]

    # ---- Expectation inference ----

    @staticmethod
    def _infer_expectation(text: str) -> str:
        """Lightweight expectation classifier.
        TOOL=imperative, ADVISOR=analysis, COMPANION=social.
        """
        tl = text.lower()
        if any(k in tl for k in ["执行","运行","读取","打开","创建","删除","修改","配置","安装","启动","停止","run","start"]):
            return "TOOL"
        if any(k in tl for k in ["你觉得","你怎么看","聊聊","讨论","看法","感觉","随便看看","怎么样"]):
            return "COMPANION"
        if any(k in tl for k in ["分析","解释","是什么","为什么","怎么看","介绍","说明","讲讲","讲一下"]):
            return "ADVISOR"
        return "ADVISOR"

    def _infer_profile_snapshot(self, text: str, response: str) -> dict:
        import re
        tech_terms = len(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text))
        expertise = min(1.0, tech_terms / max(1, len(text) / 20))
        has_analysis = any(k in text for k in ['分析','解释','为什么','怎么看','是什么'])
        is_exploration = any(k in text for k in ['你觉得','讨论','聊聊','看法'])
        style = "analytical" if has_analysis else ("exploratory" if is_exploration else "neutral")
        sentences = re.split(r'[。！？.!?\n]', text)
        lens = [len(s) for s in sentences if len(s) > 3]
        divergence = 0.3 if len(lens) < 2 else min(1.0, max(lens) / max(1, sum(lens) / len(lens)) / 3)
        return {"expertise": expertise, "divergence": divergence, "stability": 0.5, "style": style}
    def _feed_profile(self, text: str, response: str):
        """Feed current turn data into cognitive profile."""
        if not hasattr(self, '_cognitive_profile') or self._cognitive_profile is None:
            return
        if not hasattr(self, '_convergence_engine') or self._convergence_engine is None:
            return
        try:
            snap = self._infer_profile_snapshot(text, response)
            engine = self._convergence_engine
            # Map snapshot dimensions to TrackA attributes
            mapping = {
                'expertise': 'cognitive_inertia',
                'divergence': 'attention_anchor',
                'stability': 'stability',
            }
            for snap_dim, ta_dim in mapping.items():
                engine.update(ta_dim, snap.get(snap_dim, 0.5), session_weight=0.3)
            # Also feed trust: higher analysis ratio = higher trust
            if snap.get('style') == 'analytical':
                engine.update('trust_score', 0.6, session_weight=0.3)
        except Exception as e:
            logger.debug("Profile feed failed: %s", e)

    def _inject_cognitive_profile(self):
        """Inject user profile as P domain context entries."""
        if (not hasattr(self, '_cognitive_profile') or self._cognitive_profile is None
                or self._last_context is None):
            return
        from core.agent.v4.cognitive.fusion import FusionContext
        from core.agent.v4.context.cross_domain_ir import IREntry

        p = self._cognitive_profile
        engine = getattr(self, '_convergence_engine', None)
        text = FusionContext().render(p, engine)
        if text:
            self._last_context.add_entry(domain="P", entry=IREntry(
                domain="P", type="cognitive_profile",
                content=text, confidence=0.6,
                estimated_tokens=len(text) // 4,
            ))


    def _init_extraction_orchestrator(self):
        try:
            from core.agent.v4.compiler.extraction_blueprint import (
                ExtractionOrchestrator, ExtractionBlueprint,
                RegexExtractionProvider, StanzaExtractionProvider,
                LMStudioExtractionProvider, DeepSeekExtractionProvider,
            )
            self._extraction_orchestrator = ExtractionOrchestrator()
            self._extraction_orchestrator.register(ExtractionBlueprint(
                "regex", RegexExtractionProvider()))
            self._extraction_orchestrator.register(ExtractionBlueprint(
                "stanza", StanzaExtractionProvider()))
            self._extraction_orchestrator.register(ExtractionBlueprint(
                "lmstudio", LMStudioExtractionProvider()))
            self._extraction_orchestrator.register(ExtractionBlueprint(
                "deepseek", DeepSeekExtractionProvider()))
            logger.info("ExtractionOrchestrator ready: deepseek=%s lmstudio=%s",
                        DeepSeekExtractionProvider().available(),
                        LMStudioExtractionProvider().available())
        except Exception as e:
            logger.warning("ExtractionOrchestrator init failed: %s", e)

    def _get_slow_threshold(self) -> int:
        try:
            from core.agent.v4.compiler.parameter_registry import ParameterRegistry
            return ParameterRegistry().get_int("slow_path.event_threshold", 5)
        except Exception:
            return 5

    def _adjust_slow_threshold(self):
        now = time.time()
        if now - self._last_threshold_adjust < 10:
            return
        self._last_threshold_adjust = now
        if self._event_counter is None:
            return
        velocity = self._event_counter.count / max(1, now - self._last_threshold_adjust)
        base = self._slow_threshold_base
        if velocity > 0.3:
            new_threshold = max(2, base - 2)
        elif velocity < 0.1:
            new_threshold = min(50, base + 5)
        else:
            new_threshold = base
        if new_threshold != self._event_counter.threshold:
            self._event_counter.threshold = new_threshold
            logger.debug("Slow Path threshold adjusted: %d -> %d (velocity=%.2f)", base, new_threshold, velocity)

    def _slow_extract(self):
        if self._extraction_orchestrator is None or not self._observation_pool:
            return
        concepts = list(getattr(self, "_world_objects", {}).keys())[:10]
        if not concepts:
            return
        processed = 0
        for domain in self._observation_pool.stats().get("by_domain", {}):
            for bundle in self._observation_pool.get_by_domain(domain):
                for obs in getattr(bundle, "domain_observations", {}).values():
                    text = " ".join(
                        i.get("summary","") if isinstance(i,dict) else getattr(i,"summary","")
                        for i in getattr(obs,"interpretations",[])
                    )
                    if len(text) < 50:
                        continue
                    result = self._extraction_orchestrator.extract(text, concepts)
                    self._apply_extraction(result)
                    processed += 1
                    if processed >= 3:
                        break
                if processed >= 3:
                    break
            if processed >= 3:
                break

    def _feed_extractions_to_substrate(self):
        """Feed jieba extraction results into RelationSubstrate at build time."""
        if not self._content_provider or not self._observation_pool:
            return
        rs = getattr(self._content_provider, '_relation_substrate', None)
        if not rs:
            return
        try:
            from core.agent.v4.tiered.jieba_parser import JiebaRelationParser
            jrp = JiebaRelationParser()
            extractions = []
            for domain in self._observation_pool.stats().get("by_domain", {}):
                for bundle in self._observation_pool.get_by_domain(domain)[:3]:
                    for obs in getattr(bundle, "domain_observations", {}).values():
                        for ip in getattr(obs, "interpretations", []):
                            summary = ip.get("summary", "") if isinstance(ip, dict) else getattr(ip, "summary", "")
                            if len(summary) > 30:
                                extractions.extend(jrp.extract(summary))
                            if len(extractions) > 50:
                                break
                        if len(extractions) > 50:
                            break
                    if len(extractions) > 50:
                        break
                if extractions:
                    break
            if extractions:
                count = rs.build_from_extractions(extractions)
                logger.info("Build-time extraction: %d edges from %d extractions", count, len(extractions))
        except Exception as e:
            logger.debug("Build-time extraction skipped: %s", e)

    def _apply_extraction(self, result):
        from core.agent.v4.compiler.relation_substrate import RelationEdge, Evidence
        prov = getattr(self, "_content_provider", None)
        if not prov:
            return

        # Write relations to RelationSubstrate
        for r in result.relations:
            if not r.source or not r.target:
                continue
            eid = f"ext:{r.source}\u2192{r.target}:{r.predicate}"
            edge = RelationEdge(
                identity=eid, source=r.source, target=r.target,
                relation_kind="structural", semantic_strength="dependency",
                predicate=r.predicate, inverse=f"inv_{r.predicate}",
                confidence=r.confidence,
                evidence=[Evidence(
                    evidence_id=eid, source=result.provider,
                    claim=f"{r.source} {r.predicate} {r.target}",
                    confidence=r.confidence, predicate=r.predicate,
                )],
            )
            if hasattr(prov, "_relation_substrate") and prov._relation_substrate:
                prov._relation_substrate.add(edge)

        # Write definitions to SemanticObject if store is available
        objects = getattr(self, '_world_objects', {})
        for d in result.definitions:
            obj = objects.get(d.subject)
            if obj and d.text:
                # Add definition to the object's semantic_path for richer rendering
                if not hasattr(obj, '_extracted_defs'):
                    obj._extracted_defs = []
                obj._extracted_defs.append(d.text[:500])

    def set_object_store(self, objects: dict, runtime, provider):
        """Inject SemanticObject store + ObjectRuntime + ContentProvider for world rendering."""
        self._world_objects = objects
        self._object_runtime = runtime
        self._world_provider = provider
        self._bge_index = None  # invalidate BGE cache on new objects

    def _bge_retrieve(self, text: str, objects: dict) -> set:
        """Build BGE index once, reuse for all queries."""
        if not hasattr(self, '_bge_index') or self._bge_index is None:
            self._build_bge_index(objects)
        if self._bge_index is None or not self._bge_index.get('vectors'):
            return set()
        import numpy as np
        from core.agent.compiler.semantic_encoder import SemanticEncoder
        enc = SemanticEncoder()
        q_vec = enc.encode(text)
        vecs = self._bge_index['vectors']
        names = self._bge_index['names']
        sims = np.dot(vecs, q_vec)
        top_k = min(5, len(sims))
        top_idx = np.argpartition(sims, -top_k)[-top_k:]
        top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
        results = set()
        for idx in top_idx:
            if sims[idx] > 0.30:
                results.add(names[idx])
        return results

    def _build_bge_index(self, objects: dict):
        try:
            import numpy as np
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            enc = SemanticEncoder()
            names = list(objects.keys())
            vecs = enc.encode(names)
            self._bge_index = {'vectors': np.array(vecs), 'names': names}
            logger.info("BGE index built: %d vectors", len(names))
        except Exception as e:
            logger.warning("BGE index build failed: %s", e)
            self._bge_index = None

    def _find_targets_semantic(self, text: str, objects: dict) -> list:
        """BGE semantic retrieval + jieba heading backtracking.

        Hybrid: BGE encodes query → cosine similarity to object names
        + jieba keywords → heading_path lookup → objects.
        Works across languages (Chinese, Japanese, English).
        """
        targets = set()

        # ---- BGE semantic retrieval (cross-language) ----
        try:
            import numpy as np
            targets |= self._bge_retrieve(text, objects)
        except Exception as e:
            logger.debug("BGE retrieval skipped: %s", e)

        # ---- jieba keyword → heading match (fast path) ----
        try:
            import jieba
            keywords = set(w for w in jieba.cut(text) if len(w) >= 2)
            # Also add JiebaRelationParser entities
            try:
                from core.agent.v4.tiered.jieba_parser import JiebaRelationParser
                for t in JiebaRelationParser().extract(text):
                    keywords.add(t["subject"]); keywords.add(t["object"])
            except Exception:
                pass

            # Fast scan: object name + heading_path match
            for name, obj in objects.items():
                if any(kw.lower() in name.lower() for kw in keywords):
                    targets.add(name)
                else:
                    path = getattr(obj, 'semantic_path', []) or getattr(obj, 'heading_path', [])
                    path_str = " ".join(str(p) for p in path).lower()
                    if any(kw.lower() in path_str for kw in keywords):
                        targets.add(name)
                if len(targets) >= 10:
                    break
        except Exception as e:
            logger.debug("Jieba match skipped: %s", e)

        # ---- Final fallback: substring scan (original logic) ----
        if not targets:
            text_lower = text.lower()
            for name in objects:
                if name.lower() in text_lower:
                    targets.add(name)
                    if len(targets) >= 3:
                        break

        return list(targets)[:5]

    def _inject_semantic_world(self, event, text: str, perspectives):
        """Render multi-perspective world view."""
        if not (hasattr(self, '_world_objects') and self._world_objects
                and self._last_context is not None):
            return

        from core.agent.v4.context.cross_domain_ir import IREntry
        from core.agent.v4.compiler.semantic_object import LOD as LODObj
        objects = self._world_objects
        runtime = getattr(self, '_object_runtime', None)
        provider = getattr(self, '_world_provider', None)

        if not runtime or not provider:
            return

        # Find targets from primary perspective or semantic retrieval
        primary = perspectives[0] if perspectives else None
        if not primary:
            return

        targets = getattr(primary, 'targets', [])
        if not targets:
            targets = self._find_targets_semantic(text, objects)

        for target in targets[:5]:
            obj = objects.get(target)
            if not obj:
                continue

            # Render under each perspective (primary depth + secondary shallow)
            prev_design = ""
            for idx, persp in enumerate(perspectives[:2]):
                try:
                    lod_level = getattr(persp.horizon, 'depth', 2)
                    lod = LODObj(level=float(lod_level))
                    view = runtime.render(obj, lod, persp)
                except Exception as e:
                    logger.debug("Multi render failed %s/%s: %s", obj.name, persp.strategy, e)
                    continue

                strategy_label = persp.strategy.upper()
                et = f"world_view_{persp.strategy}" if idx == 0 else f"world_view_aux"

                design = view.get('design', '') if isinstance(view, dict) else ''
                # Deduplicate: skip if secondary returns same content as primary
                if idx > 0 and design[:100] == prev_design[:100]:
                    continue
                if idx == 0 and design:
                    prev_design = design

                if design:
                    self._last_context.add_entry(domain="K", entry=IREntry(
                        domain="K", type=et,
                        content=f"[{strategy_label}] {obj.name}\n{design[:500]}",
                        confidence=0.7, estimated_tokens=len(design[:500]) // 4,
                    ))

                # Relations only for primary
                if idx == 0 and provider:
                    edges = provider.relation_query(source=obj.identity, min_confidence=0.3)[:5]
                    if edges:
                        rel_lines = [f"  {obj.name} {e.predicate} {e.target} ({e.relation_kind})" for e in edges]
                        self._last_context.add_entry(domain="K", entry=IREntry(
                            domain="K", type="world_relation",
                            content=f"[RELATIONS]\n" + "\n".join(rel_lines),
                            confidence=0.5, estimated_tokens=80,
                        ))

        logger.debug("Semantic world injected: %d objects x %d perspectives", len(targets), len(perspectives))

        # Remove static graph entries when world views present
        has_world = any('world_view' in getattr(e, 'type', '') for e in self._last_context.entries)
        if has_world:
            self._last_context.entries = [
                e for e in self._last_context.entries
                if getattr(e, 'type', '') != 'graph'
            ]

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
            "Prioritize the provided context when it contains relevant information.",
            "When context lacks information on a general topic (e.g. AST trees, compilation)",
            "use your own training knowledge to answer directly.",
            "Only say the context is insufficient for DialogMesh-specific concepts",
            "(DomainSelector, BudgetAllocator, CrossDomainContextIR, etc.) —",
            "the system will fetch more details. For those, use phrases like:",
            "'需要了解 DomainSelector 的选择矩阵' to trigger subgraph expansion.",
        ]
        # Add engine state hints
        if self._last_context and self._last_context.primary_domain():
            lines.append(f"Primary context domain: {self._last_context.primary_domain()}")
        return "\n".join(lines)

    # ---- Multi-hop subgraph refinement ----

    def _multi_hop_refine(self, event: EventIR, response: str, max_hops: int = 3) -> str:
        """If LLM asks for more details, expand subgraph and re-call LLM.

        Detects patterns like:
          - "需要了解 [ConceptName] 的..."
          - "请问 [ConceptName] 是什么..."
          - "[ConceptName] 的具体细节..."
        Then does BFS expansion for those concepts and re-calls the LLM.
        """
        if not response:
            return response
        if self._last_context is None:
            return response

        import re
        prev_missing = set()
        for hop in range(max_hops):
            # Detect if we need a "zoom out" — LLM stuck in narrow cluster
            overview_injected = False
            if self._needs_overview(response, hop, max_hops):
                logger.info("Multi-hop %d: injecting architecture overview", hop+1)
                self._inject_overview()
                overview_injected = True
            
            missing = self._detect_missing_concepts(response)
            # Filter out concepts already expanded in previous hops
            missing = [c for c in missing if c not in prev_missing]
            prev_missing.update(missing)

            # If overview was injected but no specific concepts to expand,
            # re-call LLM with the enriched context
            if overview_injected and not missing:
                new_response = self._call_llm(event)
                if new_response:
                    response = new_response
                continue
            
            if not missing:
                break

            logger.info("Multi-hop %d/%d: expanding for %s", hop+1, max_hops, missing)
            self._expand_subgraph_for(missing)

            # Re-call LLM with enriched context
            new_response = self._call_llm(event)
            if new_response:
                response = new_response
            else:
                break

        return response

    def _detect_missing_concepts(self, response: str) -> list:
        """Detect if LLM response indicates it needs more info about specific concepts.

        Matches CamelCase identifiers that LLM explicitly asks about:
          "需要了解 DomainSelector 的选择矩阵"
          "BudgetAllocator 的具体分配策略是什么"
          "请问 CrossDomainContextIR 的..."
        """
        import re
        concepts = []
        patterns = [
            r'(?:需要|缺少|没有|不足).*?(?:了解|知道|信息|细节|内容).*?([A-Z][a-zA-Z]{2,}(?:[A-Z][a-zA-Z]+)*)',
            r'(?:请问|询问|想知道).*?([A-Z][a-zA-Z]{2,}(?:[A-Z][a-zA-Z]+)*)',
            r'([A-Z][a-zA-Z]{2,}(?:[A-Z][a-zA-Z]+)*)(?:的|是|指).*?(?:什么|怎么|如何|具体)',
        ]
        for p in patterns:
            for m in re.finditer(p, response):
                c = m.group(1)
                if len(c) >= 4:  # skip short acronyms
                    concepts.append(c)
        return list(dict.fromkeys(concepts))  # deduplicate, preserve order

    def _expand_subgraph_for(self, concepts: list) -> None:
        """Expand subgraph for specific concepts and inject into context."""
        if not self._last_context:
            return
        from core.agent.v4.context.cross_domain_ir import IREntry

        # Find graph source
        graph_src = None
        for s in getattr(self._context_assembler, '_sources', []):
            if hasattr(s, '_graph') and getattr(getattr(s, '_graph', None), '_built', False):
                graph_src = s
                break

        if graph_src is None:
            return

        for concept in concepts:
            items = graph_src._graph.compile_context(concept, top_k=3, max_hops=1, max_nodes=10)
            for item in items:
                self._last_context.add_entry(
                    domain="K",
                    entry=IREntry(
                        domain="K", type="subgraph_expand",
                        content=item.text,
                        confidence=item.relevance,
                        estimated_tokens=len(item.text) // 4,
                    ),
                )
        self._last_context.recalc_total()

    def _needs_overview(self, response: str, hop: int, max_hops: int) -> bool:
        """Detect if LLM needs the architecture overview.

        Triggers when LLM asks for big-picture structure or appears stuck:
        - "宏观" / "整体架构" / "全景" / "全貌"
        - "架构图" / "层级关系" / "分层"
        - Hop 2+ and same concepts repeatedly
        """
        overview_keywords = ['宏观', '整体架构', '全景', '全貌', '架构图', '层级关系',
                            '分层', '系统蓝图', '完整的系统', 'L0', 'Layer']
        resp_lower = response.lower()
        if any(kw in resp_lower for kw in overview_keywords):
            return True
        # Hop 2+: if we're still expanding, the LLM likely needs the big picture
        if hop >= 2:
            return True
        return False

    def _inject_overview(self) -> None:
        """Inject architecture overview from the merged design docs."""
        if not self._last_context:
            return
        from core.agent.v4.context.cross_domain_ir import IREntry
        import os

        # Try to load the architecture overview from merge docs
        overview_paths = [
            "docs/merge/DESIGN_00_OVERVIEW.md",
            os.path.join(os.path.dirname(__file__),
                        "..", "..", "..", "..", "docs", "merge", "DESIGN_00_OVERVIEW.md"),
        ]
        overview_text = ""
        for p in overview_paths:
            try:
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        overview_text = f.read()
                    break
            except Exception:
                continue

        if overview_text:
            # Extract key sections: architecture layers, data contracts, data flow
            sections = []
            for section_start in ['## 3. 架构分层全', '## 4. 核心数据契约', '## 5. 数据流全']:
                idx = overview_text.find(section_start)
                if idx >= 0:
                    end = overview_text.find('\n## ', idx + len(section_start))
                    if end < 0:
                        end = min(idx + 3000, len(overview_text))
                    sections.append(overview_text[idx:end].strip())

            for i, section in enumerate(sections[:3]):
                self._last_context.add_entry(
                    domain="K",
                    entry=IREntry(
                        domain="K", type="architecture_overview",
                        content=section[:1500],
                        confidence=0.95,
                        estimated_tokens=len(section[:1500]) // 4,
                    ),
                )
            logger.info("Injected %d architecture overview sections", len(sections[:3]))
        else:
            # Fallback: inject minimal architecture hint
            self._last_context.add_entry(
                domain="K",
                entry=IREntry(
                    domain="K", type="architecture_hint",
                    content=(
                        "DialogMesh 架构分为 4 层: L0 PCR(前置路由) -> L1 IntentParser(意图解析) -> "
                        "L1.5 PlanningSkill Layer(规划技能) → L2 对话管理与状态层 → L3 服务接口层。"
                        "横切关注点: 认知画像系统、记忆系统、可观测性。"
                        "核心数据契约: EventIR → ObservationBundle → HypothesisNode → KnowledgeNode → CrossDomainContextIR。"
                    ),
                    confidence=0.9,
                    estimated_tokens=100,
                ),
            )

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
        """Build ContextAssembler with unified ContentIndex pipeline.

        Design: ContentIndex → IndexSource → ContextAssembler.
        ContentIndex wraps concept graph + document pool into a single
        retrieval hub. IndexSource exposes it as a ContextSource for
        the assembler. This replaces the previous scatter of
        ObservationSource + ConceptGraphSource + DocumentSource.
        """
        sources = []
        if self._observation_pool is not None:
            # ContentIndex: unified retrieval hub
            self._content_index = ContentIndex(self._observation_pool)
            embedder = self._load_embedder()
            if embedder:
                self._content_index._graph._embedder = embedder
            self._content_index.build()
            sources.append(IndexSource(self._content_index))
            logger.info("ContentIndex + IndexSource added (%s)", self._content_index.graph_stats)

        sources.append(SkillSource())
        sources.append(WorldSource())


        # CausalPlanner integration (preferred)
        if self._causal_planner is not None:
            sources.append(CausalContextSource(self._causal_planner))
            logger.info("CausalContextSource (via CausalPlanner) added to ContextAssembler")
        # ---- Legacy fallback: direct v3_2 adapters ----
        elif self._behavior_graph_adapter is not None and self._causal_substrate_adapter is not None:
            try:
                from core.agent.v4.context.source import CausalSource, CausalSubstrateAdapter as CausalSubstrateInit
                graph = self._behavior_graph_adapter.graph
                if graph is not None:
                    init = CausalSubstrateInit(graph)
                    substrate = init.substrate
                    if substrate is not None:
                        sources.append(CausalSource(
                            behavior_graph=graph,
                            causal_substrate=substrate,
                            max_chain_depth=5,
                        ))
                        logger.info("Legacy CausalSource added to ContextAssembler")
            except Exception as e:
                logger.warning("Legacy CausalSource init skipped: %s", e)

        # ---- Topic + Behavior domain adapters (v4 design: C and B domains) ----
        from core.agent.v4.compiler.domain_adapters import TopicContextSource, BehaviorContextSource
        if self._conversation_tracker is not None:
            sources.append(TopicContextSource(self._conversation_tracker))
            sources.append(BehaviorContextSource(self._conversation_tracker))
            logger.info("TopicContextSource + BehaviorContextSource added")

        # ---- TopicTree + DiscourseBlockTree: hierarchical conversation context ----
        try:
            from core.agent.topic_tree.manager import TopicTreeManager
            from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
            from core.agent.v4.context.topic_tree_source import TopicTreeContextSource
            topic_tree = TopicTreeManager()
            discourse = DiscourseBlockTreeManager()
            self._topic_tree_source = TopicTreeContextSource(
                topic_tree=topic_tree, discourse_manager=discourse,
            )
            sources.append(self._topic_tree_source)
            logger.info("TopicTree + DiscourseBlockTree added to ContextAssembler")
        except Exception as e:
            logger.warning("TopicTree/DiscourseBlockTree init skipped: %s", e)
            self._topic_tree_source = None

        # ---- User Profile V2 (P domain) ----
        from core.agent.v4.compiler.profile_source import ProfileContextSource
        from core.agent.v4.cognitive.models import CognitiveProfileV2
        from core.agent.v4.cognitive.convergence import ConvergenceEngine, ProfileStore
        profile_v2 = CognitiveProfileV2(user_id="default", session_id=getattr(self, '_session_id', '') or "")
        self._convergence_engine = ConvergenceEngine(profile_v2.track_a)
        self._profile_store = ProfileStore()
        self._profile_store.open()
        pcs = ProfileContextSource(profile_v2)
        pcs.set_engine(self._convergence_engine)
        sources.append(pcs)
        self._cognitive_profile = profile_v2
        logger.info("ProfileContextSource (CognitiveProfileV2) added")

        # MemoryManager: extracts MemoryPoints from turns, feeds capacitor model
        from core.agent.v4.cognitive.memory_extractor import MemoryManager
        self._memory_manager = MemoryManager(profile_v2)
        logger.info("MemoryManager initialized (capacitor model)")

        return ContextAssembler(sources)

    @staticmethod
    def _load_embedder():
        """Load semantic embedder (BGE-small-zh) if available. Returns None gracefully."""
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            enc = SemanticEncoder()
            # Quick smoke test
            _ = enc.encode("test")
            logger.info("SemanticEncoder (BGE) loaded for Tier2 concept matching")
            return enc
        except Exception as e:
            logger.info("SemanticEncoder not available (Tier2 disabled): %s", e)
            return None

    def set_observation_pool(self, pool) -> None:
        """Replace the ObservationPool and rebuild ContextAssembler."""
        self._observation_pool = pool
        self._context_assembler = self._create_context_assembler()
        logger.info(
            "ObservationPool replaced + ContextAssembler rebuilt — pool: %s, sources: %d",
            pool.stats() if pool else "None",
            self._context_assembler.source_count,
        )

    def set_content_provider(self, provider):
        self._content_provider = provider
        self._feed_extractions_to_substrate()

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

    @property
    def event_log(self) -> Optional[V4EventLog]:
        """Access the underlying EventLog adapter (for diagnostics / replay)."""
        return self._event_log

    @property
    def event_log_stats(self) -> Optional[Dict[str, int]]:
        """Return EventLog stats, or None if not initialized."""
        if self._event_log is None:
            return None
        return self._event_log.stats

    def replay_unconsumed_events(self, limit: int = 100, auto_ack: bool = True) -> Dict[str, int]:
        """Replay unconsumed events from EventLog back into the engine.

        Args:
            limit: Max events to replay.
            auto_ack: If True, ack each event after successful on_event().

        Returns:
            {"replayed": int, "failed": int, "remaining": int}
        """
        if self._event_log is None or not self._event_log.is_open:
            logger.warning("EventLog replay not available")
            return {"replayed": 0, "failed": 0, "remaining": 0}

        events = self._event_log.replay_unconsumed(limit=limit)
        replayed = 0
        failed = 0

        for event in events:
            try:
                self.on_event(event)
                replayed += 1
                if auto_ack:
                    self._event_log.ack_event(event.id)
            except Exception as e:
                logger.warning("Replay failed for %s: %s", event.id, e)
                failed += 1

        remaining = self._event_log.stats.get("unconsumed", 0)
        logger.info(
            "Replay complete: %d replayed, %d failed, %d remaining",
            replayed, failed, remaining,
        )
        return {"replayed": replayed, "failed": failed, "remaining": remaining}

    def cleanup_event_log(self) -> int:
        """Delete old consumed events from EventLog."""
        if self._event_log is None:
            return 0
        return self._event_log.cleanup()
