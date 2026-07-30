"""Subsystem Registry — dependency injection + lazy loading for engine subsystems.

Each subsystem declares:
  - name: unique string key
  - path: import path (module.Class or module.function)
  - required: True = engine won't start without it, False = optional (skip + log)
  - deps: list of subsystem names that must load first
  - init_order: weight for topological sort (0=earliest, 100=latest)
  - description: human-readable

Engine.start() uses:
  registry.resolve_all() → {name: instance, ...}
  Returns both loaded and a report of what failed/skipped.
"""

from __future__ import annotations

import importlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("dm.registry")


@dataclass
class SubsystemDef:
    name: str
    path: str                       # "core.agent.pcr.router:PCRRouter"
    required: bool = True
    deps: List[str] = field(default_factory=list)
    init_order: int = 50            # 0=earliest, 100=latest
    description: str = ""
    factory: Optional[Callable] = None  # if set, called to create the instance


@dataclass
class LoadResult:
    name: str
    loaded: bool
    instance: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0


class SubsystemRegistry:
    """Central registry for all engine subsystems."""

    def __init__(self):
        self._defs: Dict[str, SubsystemDef] = {}
        self._instances: Dict[str, Any] = {}
        self._results: Dict[str, LoadResult] = {}

    def register(self, name: str, path: str, required: bool = True,
                 deps: List[str] = None, init_order: int = 50,
                 description: str = "", factory: Callable = None):
        """Register a subsystem definition."""
        if name in self._defs:
            raise ValueError(f"Duplicate subsystem: {name}")
        self._defs[name] = SubsystemDef(
            name=name, path=path, required=required,
            deps=deps or [], init_order=init_order,
            description=description, factory=factory,
        )

    def _import_from_path(self, path: str) -> Any:
        """Import a class/function from dotted path like 'mod.sub:ClassName'."""
        if ":" in path:
            mod_path, attr = path.rsplit(":", 1)
        else:
            mod_path, attr = path, path.rsplit(".", 1)[-1]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr)

    def resolve_one(self, name: str) -> LoadResult:
        """Resolve a single subsystem. Returns LoadResult."""
        t0 = time.time()
        result = LoadResult(name=name, loaded=False)

        if name not in self._defs:
            result.error = f"Unknown subsystem: {name}"
            return result

        d = self._defs[name]

        try:
            if d.factory is True:
                # factory=True means: import the function and call it
                fn = self._import_from_path(d.path)
                instance = fn() if callable(fn) else fn
            elif callable(d.factory):
                # factory is a callable — use it directly
                instance = d.factory()
            else:
                cls_or_fn = self._import_from_path(d.path)
                if isinstance(cls_or_fn, type):
                    instance = cls_or_fn()
                elif callable(cls_or_fn):
                    instance = cls_or_fn
                else:
                    instance = cls_or_fn
            self._instances[name] = instance
            result.loaded = True
            result.instance = instance
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            if d.required:
                raise RuntimeError(f"Required subsystem '{name}' failed: {e}") from e

        result.latency_ms = (time.time() - t0) * 1000
        self._results[name] = result
        return result

    def resolve_all(self, parallel: bool = False) -> Tuple[Dict[str, Any], List[LoadResult]]:
        """Resolve all registered subsystems in dependency order.
        
        Returns (instances_dict, results_list).
        Required subs that fail raise RuntimeError.
        Optional subs that fail are logged but don't block.
        """
        order = self._topological_order()
        loaded: Dict[str, Any] = {}
        all_results: List[LoadResult] = []

        for name in order:
            d = self._defs[name]
            try:
                result = self.resolve_one(name)
                all_results.append(result)
                if result.loaded:
                    loaded[name] = result.instance
                    logger.info("+%s (%.0fms) %s", name, result.latency_ms,
                                d.description or "")
                else:
                    if d.required:
                        raise RuntimeError(f"Required {name}: {result.error}")
                    logger.warning("-%s SKIPPED: %s", name, result.error)
            except RuntimeError:
                raise
            except Exception as e:
                result = LoadResult(name=name, loaded=False, error=str(e))
                all_results.append(result)
                if d.required:
                    raise
                logger.warning("-%s FAILED: %s", name, e)

        return loaded, all_results

    def _topological_order(self) -> List[str]:
        """Topological sort by deps + init_order. Kahn's algorithm."""
        in_degree: Dict[str, int] = {n: 0 for n in self._defs}
        adj: Dict[str, List[str]] = {n: [] for n in self._defs}

        for name, d in self._defs.items():
            for dep in d.deps:
                if dep in adj:
                    adj[dep].append(name)
                    in_degree[name] += 1

        queue = sorted(
            [n for n, deg in in_degree.items() if deg == 0],
            key=lambda n: self._defs[n].init_order,
        )
        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort(key=lambda n: self._defs[n].init_order)

        return result

    def status(self) -> Dict[str, Any]:
        """Return load status for all subsystems."""
        return {
            name: {
                "loaded": self._results[name].loaded if name in self._results else False,
                "error": self._results[name].error if name in self._results else "not_attempted",
                "required": d.required,
                "latency_ms": self._results[name].latency_ms if name in self._results else 0,
            }
            for name, d in self._defs.items()
        }

    def get(self, name: str) -> Any:
        """Get a loaded subsystem instance."""
        if name not in self._instances:
            raise KeyError(f"Subsystem '{name}' not loaded")
        return self._instances[name]

    def __contains__(self, name: str) -> bool:
        return name in self._instances


# ══════════════════════════════════════════════════════════════════════════════
# Standard DialogMesh subsystems
# ══════════════════════════════════════════════════════════════════════════════

def build_dialogmesh_registry(engine: Any = None) -> SubsystemRegistry:
    """Build a registry with all DialogMesh engine subsystems.
    
    Args:
        engine: The CognitiveRuntimeEngine instance (for factory closures).
    """
    r = SubsystemRegistry()

    # ── Tier 0: Core infrastructure (init_order 0-10) ──
    r.register("event_log", "core.agent.api.api_event_log:EventLog",
               required=True, init_order=0, description="EventLog (SQLite append-only)")
    r.register("event_bus", "core.agent.events.event_bus:EventBus",
               required=True, init_order=0, description="EventBus (ring buffer pub/sub)")
    r.register("decider", "core.agent.state.global_decider:GlobalDecider",
               required=True, init_order=0, description="GlobalDecider (state machine)")

    # ── Tier 1: PCR + Intent (init_order 10-20) ──
    def _pcr_factory():
        from core.agent.llm_providers.llm_instances.pcr_llm import PCRLLM
        return PCRLLM(provider=getattr(engine, '_llm_provider', None))
    r.register("pcr_router", "", required=False, init_order=10,
               description="Pre-Cognitive Router", factory=_pcr_factory)
    r.register("topic_tree", "core.agent.topic_tree.manager:TopicTreeManager",
               required=False, init_order=15, description="TopicTree")
    r.register("discourse_tree", "core.agent.compiler.discourse_block_tree:DiscourseBlockTreeManager",
               required=False, init_order=18, description="DiscourseBlockTree (3-stage compiler)")
    r.register("granularity", "core.agent.compiler.discourse_block_tree:DiscourseBlockGranularityRegulator",
               required=False, init_order=19, description="Granularity (BDI+BOR)")

    # ── Tier 2: Intent + Planning (init_order 20-30) ──
    r.register("intent_parser", "core.agent.v3_common.intent_parser:IntentParser",
               required=False, init_order=20, description="Intent Parser v3")
    r.register("planner", "core.agent.causal.planner:CausalPlanner",
               required=False, init_order=25, description="Causal Task Planner")

    # ── Tier 3: Context + Assembly (init_order 30-40) ──
    r.register("observation_pool", "core.agent.observation.pool:ObservationPool",
               required=False, init_order=30, description="ObservationPool")
    r.register("context_assembler", "core.agent.context.assembler:ContextAssembler",
               required=False, init_order=32, description="Context Assembler")
    r.register("domain_selector", "core.agent.context.domain_selector:DomainSelector",
               required=False, init_order=35, description="Domain Selector")
    r.register("perspective_planner", "core.agent.compiler.perspective_planner:PerspectivePlanner",
               required=False, init_order=38, description="Perspective Planner")

    # ── Tier 4: Chain subsystems (init_order 40-60) ──
    r.register("behavior_graph", "core.agent.behavior.adapter:BehaviorGraphAdapter",
               required=False, init_order=40, description="BehaviorGraph Adapter")
    def _causal_factory():
        from core.agent.behavior.causal_adapter import CausalSubstrateAdapter
        from core.agent.behavior.adapter import BehaviorGraphAdapter
        bg = BehaviorGraphAdapter()
        return CausalSubstrateAdapter(behavior_adapter=bg)
    r.register("causal_substrate", "", required=False, init_order=42,
               description="CausalSubstrate Adapter",
               deps=["behavior_graph"], factory=_causal_factory)
    def _meta_factory():
        from core.agent.meta.meta_subscriber import MetaSubscriber
        # Don't subscribe yet — wired later when bus is available
        ms = MetaSubscriber(event_log=None, bus=None)
        # Override with delayed subscription
        if hasattr(ms, 'subscribe') and callable(ms.subscribe):
            ms._delayed_subscribe = True
        return ms
    r.register("meta_subscriber", "", required=False, init_order=45,
               description="Meta Subscriber", deps=["event_log", "event_bus"],
               factory=_meta_factory)
    def _assoc_factory():
        from core.agent.assoc_subscriber import AssociationSubscriber
        # Don't subscribe yet
        a = AssociationSubscriber(event_log=None, bus=None)
        if hasattr(a, 'subscribe') and callable(a.subscribe):
            a._delayed_subscribe = True
        return a
    r.register("assoc_subscriber", "", required=False, init_order=46,
               description="Association Subscriber", deps=["event_log", "event_bus"],
               factory=_assoc_factory)

    # ── Tier 5: Association chain (init_order 50-65) ──
    r.register("l1_modifier", "core.agent.association.l1_modifier:ModifierExtractor",
               required=False, init_order=50, description="Association L1: Modifier")
    r.register("l1_5_completer", "core.agent.association.l1_5_completer:CollaborativeCompleter",
               required=False, init_order=52, description="Association L1.5: Completer")
    r.register("l2_5_belief", "core.agent.association.l2_5_belief:BeliefAccumulator",
               required=False, init_order=55, description="Association L2.5: Belief")
    r.register("l3_validator", "core.agent.association.l3_intent:MultiPerspectiveValidator",
               required=False, init_order=58, description="Association L3: Validator")

    # ── Tier 6: Cognitive + v6 subsystems (init_order 60-80) ──
    r.register("meta_cognition", "core.agent.v4.cognitive.metacognition:MetaCognition",
               required=False, init_order=60, description="MetaCognition v8")
    r.register("inertia", "core.agent.v4.cognitive.inertia_graph:InertiaWeightGraph",
               required=False, init_order=62, description="Inertia Weight Graph")
    r.register("behavior_discovery", "core.agent.v4.cognitive.behavior_discovery:BehaviorDiscovery",
               required=False, init_order=65, description="Behavior Discovery")
    r.register("belief_map", "core.agent.v4.cognitive.belief_map:RecursiveMap",
               required=False, init_order=68, description="Recursive Belief Map")
    r.register("subgraph", "core.agent.v4.cognitive.subgraph_compiler:SubgraphCompiler",
               required=False, init_order=70, description="Subgraph Compiler")
    r.register("parameter_registry", "core.agent.compiler.parameter_registry:ParameterRegistry",
               required=False, init_order=72, description="Parameter Registry")

    # ── Tier 7: Engineering + Mind (init_order 80-100) ──
    r.register("engineering_knowledge", "core.agent.engineering.knowledge_graph:KnowledgeGraph",
               required=False, init_order=80, description="Engineering Knowledge Graph")
    r.register("mind", "core.agent.v4.cognitive.mind:Mind",
               required=False, init_order=85, description="Mind (unified cognitive structure)")
    r.register("abc_orchestrator", "core.agent.v4.cognitive.abc_orchestrator:ABCOrchestrator",
               required=False, init_order=90, description="ABC Orchestrator")
    r.register("strategy_engine", "core.agent.v4.cognitive.contextual_strategy:ContextualStrategyEngine",
               required=False, init_order=92, description="Contextual Strategy Engine")

    # ── Tier 8: Deep engine modules (init_order 100-120) ──
    r.register("memory_compiler", "", required=False, init_order=100,
               description="MemoryCompiler (Hot/Warm/Cold tier)",
               deps=[], factory=lambda: __import__("core.agent.engine.deep_modules", fromlist=["MemoryCompiler"]).MemoryCompiler())
    r.register("context_ir_compiler", "", required=False, init_order=102,
               description="Context Assembler v2 (ContextIR compilation)",
               deps=[], factory=lambda: __import__("core.agent.engine.deep_modules", fromlist=["ContextAssembler"]).ContextAssembler())
    r.register("format_serializer", "", required=False, init_order=104,
               description="FormatEngine (serialize/deserialize to tokens)",
               deps=[], factory=lambda: __import__("core.agent.engine.deep_modules", fromlist=["FormatEngine"]).FormatEngine())
    r.register("event_log_store", "", required=False, init_order=106,
               description="EventLogDB (SQLite persistent event log)",
               deps=[], factory=lambda: __import__("core.agent.engine.deep_modules", fromlist=["EventLogDB"]).EventLogDB())
    r.register("ocean_analyst", "core.agent.v4.cognitive.ocean_profile:OCEANProfileAnalyst",
               required=False, init_order=95, description="OCEAN Profile Analyst")

    r.register("semantic_pipeline", "", required=False, init_order=108,
               description="SemanticObjectPipeline (entity extraction + LLM classification)",
               deps=[], factory=lambda: __import__("core.agent.engine.semantic_pipeline", fromlist=["SemanticObjectPipeline"]).SemanticObjectPipeline())

    return r
