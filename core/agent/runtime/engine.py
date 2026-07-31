"""CognitiveRuntimeEngine: orchestrates v4 modules across four paths.

Integrates ``PathAwareScheduler`` for path-aware scheduling,
configuration-driven triggers, and per-path state tracking.
"""
from __future__ import annotations
import time, re
import importlib
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.events.event_ir import EventIR
from core.agent.runtime.adapter import (
    RuntimeAdapter, RuntimeContext, AdapterResult,
)
from core.agent.runtime.config import (
    RuntimeConfig, ModuleConfig, PathConfig, load_runtime_config, build_default_config,
)
from core.agent.world.params import WorldParams, get_world_params
from core.agent.context.assembler import ContextAssembler
from core.agent.context.source import (
    SkillSource, WorldSource,
)
from core.agent.context.topic_tree_source import TopicTreeContextSource
from core.agent.compiler.content_index import ContentIndex
from core.agent.compiler.index_source import IndexSource
from core.agent.conversation.tracker import ConversationTracker
from core.agent.compiler.discourse_block_tree import DiscourseBlockTreeManager
from core.agent.causal.planner import CausalPlanner, CausalContextSource
from core.agent.context.domain_selector import DomainSelector
from core.agent.context.cross_domain_ir import CrossDomainContextIR
from core.agent.compiler.perspective_planner import PerspectivePlanner, Perspective
from core.agent.v4.cognitive_scheduler.path_scheduler import PathAwareScheduler
from core.agent.v4.cognitive_scheduler.path_models import PathType, PathState
from core.agent.v4.cognitive_scheduler.path_trigger_policy import (
    ConfigDrivenTriggerPolicy, EventCounter, PathStateMachine,
)
from core.agent.v4.cognitive_scheduler.tasks import (
    ObservationTask, HypothesisTask, KnowledgeTask, SkillTask,
)

from core.agent.behavior.adapter import BehaviorGraphAdapter, BehaviorGraphState
from core.agent.causal_substrate.adapter import CausalSubstrateAdapter, CausalContextEntry
from core.agent.runtime.event_log_adapter import V4EventLog, EventLogConfig

from core.agent.optimizer.signals import FeedbackSignal
from core.agent.optimizer.optimizer import BayesianOptimizer
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



def _feed_discourse(engine, ctx):
    """Helper for state machine: feed discourse tree."""
    text = ctx.get("text", "")
    sid = ctx.get("session_id", "default")
    if hasattr(engine, '_discourse_tree') and engine._discourse_tree:
        engine._discourse_tree.feed(text, sid)
        return {"blocks": len(engine._discourse_tree.get_block_relations(sid).get("blocks", {}))}
    return {}

def _record_behavior(engine, ctx):
    """Helper for state machine: record behavior edge."""
    bg = getattr(engine, '_behavior_graph', None)
    if bg and hasattr(bg, 'load'):
        bg.load()
        return {"recorded": True}
    return {}

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
        self._world_objects: Dict[str, Any] = {}  # P0: SemanticObject store (lazy init)
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
        # Granularity regulator: BDI+BOR adaptive split/merge
        from core.agent.compiler.discourse_block_tree import DiscourseBlockGranularityRegulator
        self._granularity_regulator = DiscourseBlockGranularityRegulator()
        self._turn_counter = 0

        # User cognitive profile (dual-track: Track A dynamics + Track B tags)
        self._cognitive_profile: Optional[object] = None  # CognitiveProfileV2

        # Extraction orchestration (regex / LMStudio / DeepSeek with fallback)
        self._extraction_orchestrator = None  # ExtractionOrchestrator set in start()

        # Cognitive Runtime (Phase 2): LLM-driven reasoning loop
        self._use_cognitive_runtime = False

        # Internal Simulation Engine: LLM simulates user cognitive state
        self._simulation_engine = None  # Initialized in start()
        self._last_simulation: Optional[object] = None  # SimulationResult from previous turn
        self._simulation_stats = {"matches": 0, "total": 0}
        self._cognitive_observer = None  # Observer set when enabled
        self._cognitive_trace: Optional[object] = None  # ExecutionTrace for last run

        # v6: State evolution tracking (ExecutionTraceV3)
        self._trace_v3: Optional[object] = None  # ExecutionTraceV3 per session

        # Behavior tracking: record user navigation edges in RelationSubstrate
        self._last_concept: Optional[str] = None
        self._content_provider = None  # set by _create_context_assembler

        # TopicTree + DiscourseBlockTree: hierarchical conversation context
        self._topic_tree_source: Optional[TopicTreeContextSource] = None

        # LLM Provider integration
        self._llm_provider: Optional[LLMProvider] = llm_provider
        self._last_llm_response: Optional[str] = None
        self._pcr_router = None  # Pre-Cognitive Router — lazy init in start()
        self._last_pcr = None    # Last PCROutput
        self._decider = None     # GlobalDecider — state machine coordinator
        self._event_log = None   # EventLog — SQLite append-only
        self._event_bus = None   # EventBus — ring buffer pub/sub
        self._meta_sub = None    # MetaSubscriber — cold path
        self._assoc_sub = None   # AssociationSubscriber — cold path
        self._intent_parser = None     # v3_common IntentParser — lazy init
        self._unified_parser = None   # UnifiedParser — Tier 0→2 pipeline
        self._router_v4 = None        # V4.0 Cognitive Coordinate Router
        self._last_intent_context = None  # Last IntentContext
        self._last_parse_result = None   # Last ParseResult
        self._planner = None             # v3_0 Planner — lazy init
        self._skill_matcher = None       # v3_0 SkillMatcher — lazy init
        self._scheduler = None           # v4 CognitiveScheduler — lazy init
        self._last_plan_result = None    # Last PlanResult
        self._llm_metrics: Optional[Dict[str, Any]] = None

        # Path trigger policy and state machine (from path_trigger_policy)
        self._trigger_policy: Optional[ConfigDrivenTriggerPolicy] = None
        self._path_state_machine: Optional[PathStateMachine] = None
        self._event_counter: Optional[EventCounter] = None

        for path_name in self._config.paths:
            self._stats[path_name] = PathStats(path_name=path_name)

    # ---- Lifecycle ----

    def on_event_sm(self, event: EventIR, start_phase: str = "pcr") -> Optional[str]:
        """Process event through StateMachine pipeline (new path).
        
        Kept alongside on_event() for A/B comparison. Config switch:
          engine.use_state_machine = True → on_event delegates to on_event_sm
        Original on_event() is NEVER modified — both paths coexist.
        """
        from core.agent.event.statemachine import PipelinePhase
        sm = getattr(self, '_state_machine', None)
        if not sm:
            logger.warning("on_event_sm: no StateMachine, falling back to on_event")
            return self.on_event(event)

        phase_map = {
            "pcr": PipelinePhase.PCR, "intent": PipelinePhase.INTENT,
            "discourse": PipelinePhase.DISCOURSE, "behavior": PipelinePhase.BEHAVIOR,
            "meta": PipelinePhase.META, "profile": PipelinePhase.PROFILE,
            "persist": PipelinePhase.PERSIST,
        }
        phase = phase_map.get(start_phase, PipelinePhase.PCR)

        # ── Coverage gap: ConversationTracker + Granularity (legacy on_event) ──
        _raw = event.payload.get("text", "") if hasattr(event, "payload") else str(event)
        _concepts = self._extract_concepts_from_text(_raw) if _raw else []
        if _raw and getattr(self, '_conversation_tracker', None):
            self._conversation_tracker.add_turn(_raw, concepts=_concepts)
        self._turn_counter += 1
        if getattr(self, '_granularity_regulator', None) and self._discourse_tree:
            _sid = event.payload.get("session_id", "default") if hasattr(event, "payload") else "default"
            _tree = getattr(self._discourse_tree, "_trees", {}).get(_sid) if hasattr(self._discourse_tree, "_trees") else None
            if _tree:
                self._granularity_regulator.regulate(_tree, self._turn_counter)

        text = event.payload.get("text", "") if hasattr(event, "payload") else str(event)
        ctx = {
            "text": text,
            "reply": event.payload.get("reply", "") if hasattr(event, "payload") else "",
            "session_id": getattr(event, "session_id", "default"),
        }

        try:
            result = sm.run_pipeline(phase, ctx)
            phases = result.get("phases", [])
            logger.info("on_event_sm: %d phases completed", len(phases))
            # Return last phase's output as response
            for phase_result in reversed(result.get("results", {}).values()):
                if isinstance(phase_result, str) and len(phase_result) > 10:
                    return phase_result
            return None
        except Exception as e:
            logger.warning("on_event_sm failed: %s, falling back to on_event", e)
            return self.on_event(event)

    def _publish(self, event_type, payload=None):
        """Fire-and-forget publish. Priority-scheduled with tracing."""
        kind = event_type.value if hasattr(event_type, 'value') else str(event_type)
        payload = payload or {}
        tracer = getattr(self, '_tracer', None)
        start = time.time()
        success = True
        try:
            if self._event_bus:
                try: self._event_bus.publish(kind, payload)
                except: pass
            subs = getattr(self, '_event_subscribers', {})
            if subs:
                try:
                    from core.agent.event.scheduler import DeciderScheduler, create_scheduled_task
                    sched = getattr(self, '_scheduler', None)
                    if sched is None:
                        sched = DeciderScheduler()
                        self._scheduler = sched
                    for name, sub in subs.items():
                        sched.submit(create_scheduled_task(name, sub.handle, kind, payload))
                    sched.run_batch()
                except Exception:
                    for name, sub in subs.items():
                        try: sub.handle(kind, payload)
                        except: pass
        except Exception:
            success = False
            raise
        finally:
            if tracer:
                latency = (time.time() - start) * 1000
                tracer.record("publish", kind, success, latency)

    def _on_event_continue(self, event, pcr_output=None, parse_result=None, unified_result=None, text=""):
        """Phase 2 of on_event — V4 Router after PCR."""
        # ---- V4.0 Cognitive Coordinate Router ----
        route = None
        if self._router_v4 is not None and text:
            try:
                result, route = self._router_v4.route(text, pcr_output=pcr_output)
                logger.debug('RouterV4: zone=%s cost=%dms', route.zone, route.cost_ms)
                self._publish("route_generated", {"zone": route.zone, "strategy": route.strategy})
                if self._decider:
                    from core.agent.state.global_decider import Command
                    self._decider.evolve(self._decider.decide(
                        Command(type="routing", payload={"zone": route.zone, "strategy": route.strategy})
                    ))
            except Exception as e:
                logger.debug('RouterV4 failed: %s', e)

        # ---- Intent Parser (Layer 1) ----
        parse_result = None
        intent_context = None
        if self._intent_parser is not None and text:
            try:
                # Build IntentContext from PCR output
                if pcr_output:
                    from core.agent.v3_common.models import IntentContext
                    intent_context = IntentContext.from_pcr_output(pcr_output)
                else:
                    intent_context = IntentContext()

                parse_result = self._intent_parser.parse(
                    user_input=text,
                    intent_context=intent_context,
                    parse_context=self._build_parse_context(),
                )
                self._last_intent_context = intent_context
                self._last_parse_result = parse_result
                cat = str(getattr(parse_result.intent, 'category', 'UNKNOWN')) if hasattr(parse_result, 'intent') else 'UNKNOWN'
                self._publish("intent_parsed", {"category": cat})
                if self._decider and parse_result:
                    from core.agent.state.global_decider import Command
                    cat = str(getattr(parse_result.intent, 'category', 'UNKNOWN')) if hasattr(parse_result, 'intent') else 'UNKNOWN'
                    self._decider.evolve(self._decider.decide(
                        Command(type="intent", payload={"category": cat})
                    ))
            except Exception as e:
                logger.warning('IntentParser failed: %s', e)

        # ---- Planning (Layer 1.5) ----
        plan_result = None
        if self._planner is not None and parse_result:
            try:
                intent = parse_result.intent if hasattr(parse_result, 'intent') else None
                if intent:
                    from core.agent.v3_legacy.data_models import IntentContext_v3
                    from core.agent.planner.skill_registry import SkillRegistry
                    plan_ctx = IntentContext_v3()
                    if pcr_output:
                        plan_ctx.expectation = getattr(pcr_output, 'expectation', None)
                        plan_ctx.complexity = getattr(pcr_output, 'complexity_level', 0.5)
                        plan_ctx.cognitive_profile = getattr(pcr_output, 'cognitive_profile', None)

                    # Skill matching
                    blueprint = None
                    if self._skill_matcher:
                        try:
                            intent_str = str(getattr(intent, 'category', intent))
                            blueprint = self._skill_matcher.match(intent_str)
                        except: pass

                    # Run async plan() in executor
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        plan_result = loop.run_until_complete(
                            self._planner.plan(
                                intent=intent,
                                intent_context=plan_ctx,
                                blueprint=blueprint,
                            )
                        )
                    finally:
                        loop.close()
                    self._last_plan_result = plan_result
                    self._publish("plan_generated")
                    if self._decider and plan_result:
                        from core.agent.state.global_decider import Command
                        tg = getattr(plan_result, 'task_graph', None)
                        task_count = len(getattr(tg, 'nodes', [])) if tg else 0
                        self._decider.evolve(self._decider.decide(
                            Command(type="planning", payload={"task_count": task_count})
                        ))

                    # Submit TaskGraph to scheduler
                    if self._scheduler and hasattr(plan_result, 'task_graph') and plan_result.task_graph:
                        try:
                            self._scheduler.submit(plan_result.task_graph)
                        except: pass
            except Exception as e:
                logger.warning('Planning failed: %s', e)

        # ---- Context Engineering: compile CrossDomainContextIR ----
        self._compile_context(event, pcr_output=pcr_output, parse_result=parse_result, unified_result=unified_result)
        
        # ---- DiscourseBlockTree context injection (3-paradigm compass) ----
        if self._discourse_tree and self._last_context:
            try:
                session_id = getattr(event, 'session_id', 'default')
                tree = self._discourse_tree._trees.get(session_id)
                if tree and tree.blocks:
                    from core.agent.compiler.three_paradigm_context import ThreeParadigmContext
                    compass = ThreeParadigmContext(topic_tree=self._topic_tree)
                    block_list = list(tree.blocks.values())[:8]
                    discourse_ctx = compass.build(block_list, current_text=text,
                                                 max_tokens=2000)
                    if discourse_ctx:
                        from core.agent.context.cross_domain_ir import ContextEntry
                        entry = ContextEntry(
                            source="discourse_tree",
                            content=discourse_ctx,
                            relevance=0.7,
                        )
                        self._last_context.entries.append(entry)
                        logger.debug('Compass context injected: %s chars', len(discourse_ctx))
            except Exception as e:
                logger.debug('Discourse context injection skipped: %s', e)

        # ---- Association Chain L1→L2.5 (cold path, parallel to hot path) ----
        if text and self._l1_extractor:
            try:
                self._run_association_chain(event, text, pcr_output)
            except Exception as e:
                logger.debug('Association chain skipped: %s', e)

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

        # v6 Trace: snapshot state before reasoning
        pre_state = None
        if self._trace_v3:
            from core.agent.state.state_object import StateObject, TransitionReason, StateDelta
            pre_state = StateObject(data={
                "turn": self._turn_counter,
                "user_text": text[:200],
            })
            pre_state = self._trace_v3.snapshot(pre_state)

            # OBSERVE: concepts extracted, tree updated
            self._trace_v3.record_transition(
                reason=TransitionReason.OBSERVE,
                from_state=pre_state, to_state=pre_state,
                evidence=[f"Concepts: {concepts[:5] if concepts else []}", f"Text: {text[:60]}"],
                effects=[StateDelta(key="concept_count", operation="set", value=len(concepts))],
                confidence=0.85,
            )
            # Monitor
            if self._monitor:
                self._monitor.record_transition(self._turn_counter, "observe",
                    text[:60],
                    [{"concepts": concepts[:3] if concepts else []}])

            # REJECT: detect if user input signals rejection of previous answer
            reject_signals = ['wrong', 'incorrect', 're-read', 'you are wrong', "you're wrong",
                            'still wrong', 'not correct', 'no,', 'try again']
            if text and any(s in text.lower() for s in reject_signals):
                self._trace_v3.record_transition(
                    reason=TransitionReason.REJECT,
                    from_state=pre_state, to_state=pre_state,
                    evidence=[f"User rejected: {text[:60]}"],
                    effects=[StateDelta(key="reject_count", operation="inc", value=1)],
                    confidence=0.85,
                )
                if self._monitor:
                    self._monitor.record_transition(self._turn_counter, "reject",
                        f"User rejected: {text[:50]}", [])

            # ACTIVATE: DiscourseTree block activated
            sid = (event.refs.get('session_id') if hasattr(event,'refs') and event.refs.get('session_id') else event.payload.get('session_id', 'default')) if hasattr(event, 'payload') else 'default'
            tree = self._discourse_tree._trees.get(sid) if hasattr(self._discourse_tree, '_trees') else None
            if tree:
                self._trace_v3.record_transition(
                    reason=TransitionReason.ACTIVATE,
                    from_state=pre_state, to_state=pre_state,
                    evidence=[f"Blocks: {len(tree.blocks)}", f"Active: {len(tree.active_blocks())}"],
                    effects=[StateDelta(key="tree.block_count", operation="set", value=len(tree.blocks))],
                    confidence=0.75,
                )
                # Monitor ACTIVATE
                if self._monitor:
                    self._monitor.record_tree(self._turn_counter, len(tree.blocks),
                        len(tree.active_blocks()), len(tree.blocks) - 1)

        llm_response = self._call_llm(event, pcr_output=pcr_output, parse_result=parse_result, plan_result=plan_result, unified_result=unified_result)
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
        self._feed_trackb(text)  # TrackB: accumulate tags from user input

                # ---- Internal Simulation: evaluate last prediction, simulate next ----
        if self._simulation_engine:
            try:
                if self._last_simulation and text:
                    feedback = self._simulation_engine.evaluate(self._last_simulation, text)
                    if feedback.matched:
                        self._simulation_stats["matches"] += 1
                    self._simulation_stats["total"] += 1
                    self._simulation_engine.learn(feedback)
                    if self._monitor:
                        self._monitor.record_simulation(self._turn_counter,
                            feedback.predicted_question, text, feedback.matched, feedback.similarity)
            except Exception as e:
                logger.debug("Sim evaluation skipped: %s", e)

            try:
                if llm_response and self._last_simulation:
                    user_understanding = ""
                    if self._conversation_tracker:
                        topics = self._conversation_tracker.recent_topics(3)
                        user_understanding = "; ".join(topics) if topics else ""
                    profile_summary = str(self._cognitive_profile.track_b)[:200] if self._cognitive_profile else ""
                    self._last_simulation = self._simulation_engine.simulate(
                        last_answer=llm_response,
                        user_understanding=user_understanding,
                        user_profile=profile_summary,
                    )
            except Exception as e:
                logger.debug("Sim generation skipped: %s", e)

        # ---- v6 Trace: record post-reasoning transition ----
        post_state = None
        if self._trace_v3 and llm_response and pre_state:
            from core.agent.state.state_object import Transition, TransitionReason, StateDelta, StateObject
            # INFER: LLM reasoning result
            post_state = self._trace_v3.states[-1] if self._trace_v3.states else StateObject()
            # Dynamic confidence from response quality
            dyn_conf = 0.7
            if len(llm_response) < 30 and any(w in llm_response.lower() for w in ['unsure','guessing','not sure']):
                dyn_conf = 0.35
            elif len(llm_response) < 50:
                dyn_conf = 0.55
            elif len(llm_response) > 500:
                dyn_conf = 0.80
            self._trace_v3.record_transition(
                reason=TransitionReason.INFER,
                from_state=pre_state, to_state=post_state,
                evidence=[f"Answer: {llm_response[:80]}"],
                effects=[
                    StateDelta(key="turn", operation="inc", value=1),
                    StateDelta(key="response_length", operation="set", value=len(llm_response)),
                ],
                confidence=dyn_conf,
            )

            # Monitor: record INFER transition
            if self._monitor:
                self._monitor.record_transition(self._turn_counter, "infer",
                    f"Answer: {llm_response[:60]}",
                    [{"response_len": len(llm_response)}])

        # ---- v6 Trace: reflect after profile update ----
        if self._trace_v3 and llm_response and pre_state:
            ta = getattr(getattr(self, '_cognitive_profile', None), 'track_a', None)
            if ta:
                self._trace_v3.record_transition(
                    reason=TransitionReason.REFLECT,
                    from_state=pre_state, to_state=post_state or pre_state,
                    evidence=[f"Profile updated: inertia={getattr(ta,'cognitive_inertia',0):.2f}"],
                    effects=[
                        StateDelta(key="profile.trust", operation="set", value=getattr(ta,'trust_score',0)),
                    ],
                    confidence=0.6,
                )

            # ---- v6 Contextual Strategy: record what worked ----
            if hasattr(self, '_strategy_engine') and self._strategy_engine:
                from core.agent.v4.cognitive.contextual_strategy import StrategyContext
                ctx = StrategyContext.from_engine(self)
                # Record the explanation strategy effectiveness (inferred from profile delta)
                trust_delta = getattr(ta, 'trust_score', 0.5) - 0.5
                self._strategy_engine.record(
                    "explain_answer",
                    ctx,
                    effectiveness=0.5 + trust_delta * 0.5,
                    confidence_gain=trust_delta,
                )

            # STRENGTHEN: confidence changed — record direction and magnitude
            if self._trace_v3 and ta and abs(trust_delta) > 0.01:
                reason = TransitionReason.STRENGTHEN if trust_delta > 0 else TransitionReason.WEAKEN
                self._trace_v3.record_transition(
                    reason=reason,
                    from_state=pre_state, to_state=post_state or pre_state,
                    evidence=[f"Trust delta: {trust_delta:+.3f}"],
                    effects=[StateDelta(key="trust", operation="set", value=getattr(ta,'trust_score',0.5))],
                    confidence=0.65,
                )
            # Monitor profile
            if self._monitor and ta:
                self._monitor.record_profile(self._turn_counter, ta,
                    {k: v.get('confidence', 0.5) if isinstance(v, dict) else getattr(v, 'value', 0.5)
                     for k, v in getattr(self._cognitive_profile, 'track_b', {}).items()})

            # ---- v6 InteractionGraph: propagate state through architecture ----
            if hasattr(self, '_interaction_graph') and self._interaction_graph and ta:
                trust = getattr(ta, 'trust_score', 0.5)
                deltas = self._interaction_graph.propagate(
                    "Observer",
                    {"confidence": trust, "attention": 0.5 + trust * 0.3},
                )
                if deltas:
                    logger.debug("InteractionGraph: %d deltas from Observer propagation", len(deltas))

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

        # ---- v6 MetaConsumer: close the learning loop (every 5 turns) ----
        if self._meta_consumer and self._trace_v3 and self._turn_counter % 5 == 0:
            advice = self._meta_consumer.consume(self._trace_v3, self._turn_counter)
            if advice.get("adjust"):
                logger.info(
                    "Meta: %d warnings — %s",
                    len(advice.get("warnings", [])),
                    "; ".join(advice.get("suggestions", [])[:2]),
                )
                # Generate structured ReasoningPolicy (LLM-driven or rule fallback)
                if self._policy_generator:
                    # Use LLM-driven generator if available
                    if hasattr(self, '_llm_policy_generator') and self._llm_policy_generator:
                        trace_text = self._trace_v3.reasoning_path if self._trace_v3 else ""
                        self._active_policy = self._llm_policy_generator.generate(
                            advice, trace_summary=trace_text, turn_count=self._turn_counter
                        )
                    else:
                        self._active_policy = self._policy_generator.generate(advice)
                    # Monitor policy
                    if self._monitor and self._active_policy:
                        self._monitor.record_policy(self._turn_counter, self._active_policy)
                    # Persist learned patterns
                    if self._policy_generator:
                        self._policy_generator._pattern_learner.save()
                    # Mind: learn from trace, profile, and MetaConsumer warnings
                    if self._mind:
                        self._mind.learn(self)
                    logger.info(
                        "Policy: perspective=%s mode=%s depth=%d",
                        self._active_policy.perspective or '-',
                        self._active_policy.explanation_mode or '-',
                        self._active_policy.depth_adjust,
                    )

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

    def _build_parse_context(self):
        try:
            from core.agent.v3_common.models import ParseContext
            ctx = ParseContext()
            if self._last_context:
                ctx.history = list(self._last_context.entries[:10])
            return ctx
        except Exception:
            return None


    def stop(self) -> None:
        """Stop the engine."""
        self._running = False
        self._session_active = False

    def on_event(self, event):
        """Compatibility wrapper — delegates to on_event_sm."""
        return self.on_event_sm(event, start_phase="pcr")

    @staticmethod
    def _extract_concepts_from_text(text: str):
        """Extract concepts from text for conversation tracking."""
        import re
        if not text:
            return []
        return re.findall(r'[A-Z][a-z]+|[A-Z]{2,}', text)
