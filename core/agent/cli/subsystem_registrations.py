"""Core subsystem registrations for DialogMesh v6 engine.

Registers all 17 subsystems that _create_engine_instance() currently creates manually.
After registration, the factory can use registry.resolve_all() instead of manual imports.
"""
from core.agent.cli.registry import SubsystemRegistry

_registry = SubsystemRegistry()

# ── Tier 0: Foundation (no dependencies) ──
_registry.register("state_machine", "core.agent.event.statemachine:DeciderStateMachine",
                   init_order=0, description="8-phase StateMachine, 12 transitions")

_registry.register("storage", "core.agent.event.storage:StorageLayer",
                   init_order=0, required=False, description="Hot/Warm/Cold 3-tier storage")

_registry.register("event_log", "core.agent.api.api_event_log:EventLog",
                   init_order=0, description="SQLite+WAL event persistence")

_registry.register("tracer", "core.agent.event.tracer:PipelineTracer",
                   init_order=0, required=False, description="Pipeline phase tracer")

# ── Tier 1: Core cognition ──
_registry.register("discourse_tree", "core.agent.compiler.discourse_block_tree:DiscourseBlockTreeManager",
                   init_order=10, description="Discourse block tree for conversation structure")

_registry.register("conversation_tracker", "core.agent.conversation.tracker:ConversationTracker",
                   init_order=10, description="Multi-dimensional follow-up disambiguation")

_registry.register("topic_tree", "core.agent.topic_tree.manager:TopicTreeManager",
                   init_order=10, description="Topic heat tracking + routing")

_registry.register("granularity", "core.agent.compiler.discourse_block_tree:DiscourseBlockGranularityRegulator",
                   init_order=10, required=False, description="BDI+BOR adaptive split/merge")

_registry.register("behavior_graph", "core.agent.behavior.adapter:BehaviorGraphAdapter",
                   init_order=15, description="Behavior chain recording + prediction")

# ── Tier 2: Analysis engines ──
_registry.register("ocean_analyst", "core.agent.v4.cognitive.ocean_profile:OCEANProfile",
                   init_order=20, required=False, factory=True,
                   description="OCEAN 10-dimension personality profiling")

# ── Missing from factory but should be registered ──
_registry.register("tool_registry", "core.agent.tool_registry.registry:ToolRegistry",
                   init_order=20, required=False, description="L1/L2/L3 autonomous tool discovery")

_registry.register("content_fetcher", "core.agent.learning.content_fetcher:ContentFetcher",
                   init_order=35, required=False, description="Content fetching engine")

_registry.register("credibility_eval", "core.agent.learning.credibility:CredibilityEvaluator",
                   init_order=35, required=False, description="Content credibility evaluator")

_registry.register("cascade_detector", "core.agent.event.closure:CascadeDetector",
                   init_order=45, required=False, deps=["rate_guard"],
                   description="Cascade failure detector")

_registry.register("hot_reloader", "core.agent.event.closure:HotReloader",
                   init_order=40, required=False, description="Hot reload engine")

_registry.register("meta_cognition", "core.agent.metacognition:MetaCognitionAdapter",
                   init_order=20, required=False, description="Metacognitive review + audit")

_registry.register("mind", "core.agent.v4.cognitive.mind:Mind",
                   init_order=20, required=False, description="Unified cognitive workspace")

_registry.register("abc", "core.agent.v4.cognitive.abc_orchestrator:ABCOrchestrator",
                   init_order=20, required=False, description="Agent-Behavior-Causal orchestrator")

_registry.register("decider", "core.agent.state.global_decider:GlobalDecider",
                   init_order=20, description="Global state machine decider")

# ── Tier 3: Knowledge + Learning ──
_registry.register("rag_bridge", "core.agent.knowledge.rag_bridge:RAGBridge",
                   init_order=30, required=False, description="Hybrid RAG (dense+sparse+graph)")

_registry.register("frame_library", "core.agent.compiler.rule_engine:FrameLibrary",
                   init_order=30, required=False, description="Cognition frame/pattern library")

_registry.register("inertia_graph", "core.agent.v4.cognitive.inertia_graph:InertiaWeightGraph",
                   init_order=30, required=False, description="Inertia weight decay graph")

_registry.register("behavior_discovery", "core.agent.v4.cognitive.behavior_discovery:CompletionEngine",
                   init_order=30, required=False, description="Behavior pattern discovery engine")

_registry.register("engineering_knowledge", "core.agent.engineering.knowledge_graph:KnowledgeGraph",
                   init_order=30, required=False, description="Engineering knowledge graph")

_registry.register("learning_sources", "core.agent.learning.sources:ArxivSource",
                   init_order=35, required=False, factory=True,
                   description="Arxiv+Scholar+DDG 5-source learning ingestion")

# ── Tier 4: Guards + Bridges ──
_registry.register("rate_guard", "core.agent.event.closure:RateGuard",
                   init_order=35, required=False, description="Rate limiter guard")

_registry.register("capability_guard", "core.agent.event.closure:CapabilityGuard",
                   init_order=40, required=False, description="Capability/permission guard")

# ── Pluggable bridges (all optional, loaded on demand) ──
_registry.register("nats_bridge", "core.agent.event.nats_bridge:HybridEventBus",
                   init_order=90, required=False, description="NATS pub/sub (graceful fallback)")

_registry.register("pg_bridge", "core.agent.event.pluggable:PgBridge",
                   init_order=90, required=False, description="PostgreSQL bridge (fallback to SQLite)")

_registry.register("redis_hotstore", "core.agent.event.redis_otel:RedisHotStore",
                   init_order=90, required=False, description="Redis cache (fallback to memory)")

_registry.register("otel_bridge", "core.agent.event.redis_otel:RedisBridge",
                   init_order=90, required=False, description="OpenTelemetry exporter")

# ── Association chain (L1-L3) ──
_registry.register("l1_modifier", "core.agent.association.l1_modifier:ModifierExtractor",
                   init_order=25, required=False, description="L1: Modifier extraction")

_registry.register("l2_5_belief", "core.agent.association.l2_5_belief:BeliefAccumulator",
                   init_order=25, required=False, deps=["l1_modifier"],
                   description="L2.5: Belief accumulation")

_registry.register("l3_validator", "core.agent.association.l3_intent:MultiPerspectiveValidator",
                   init_order=25, required=False, deps=["l2_5_belief"],
                   description="L3: Multi-perspective validation")

# ── Phase 1: Storage layer (ChunkStore, Splitter, Context) ──
_registry.register("chunk_store", "core.agent.storage.chunk_store:ChunkStore",
                   init_order=5, required=False, description="Semantic atom vector store (ChromaDB)")

_registry.register("semantic_splitter", "core.agent.storage.semantic_splitter:SemanticSplitter",
                   init_order=5, required=False, description="Recursive splitter with overlap + non-chunkable detection")

_registry.register("context_window", "core.agent.storage.context_window:ContextWindow",
                   init_order=5, required=False, description="Per-turn token budget context window")

_registry.register("write_gate", "core.agent.storage.context_window:WriteGate",
                   init_order=5, required=False, description="Pre-write approval gate")

_registry.register("relation_graph", "core.agent.storage.relation_graph:RelationGraph",
                   init_order=6, required=False, description="Entity-relationship graph (pandas+nx)")

_registry.register("block_meta", "core.agent.storage.block_meta:BlockMetaStore",
                   init_order=6, required=False, description="Block metadata store (clustering)")
