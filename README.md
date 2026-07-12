# DialogMesh v4

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Tests: 304/304](https://img.shields.io/badge/tests-304%2F304-green)](docs/v3.0/TEST_REPORT.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

Multi-layer LLM Cognitive Architecture with **Event -> Observation -> Hypothesis -> Knowledge -> Skill** knowledge refinement pipeline.

---

## Overview

DialogMesh is an industrial-grade conversational agent system that goes beyond RAG and graph-memory: it builds a **cognitive model of the user and the codebase**, continuously refining its understanding through a multi-tier belief update pipeline.

**v4 Architecture** (three-line architecture):

`
Cognitive Scheduler  (when to think)
        |
        v
Cognitive Pipeline   (how to think)
  Event -> Observation -> Hypothesis -> Knowledge -> Skill -> Capability
        |
        v
Semantic World Model (what to think about)
  Code/CAD/Unity -> World Adapters -> Structural World IR -> Context Compiler
`

**Key differentiators**:
- **Not just retrieval** — forms beliefs through evidence competition, not vector similarity
- **Multi-domain observation** — an Event is projected into Behavior, Engineering, Memory, Dialogue, and User domains simultaneously
- **Structural world model** — codebase modeled as a graph with community detection, backbone coloring, and multi-type edges
- **Knowledge refinement chain** — Event (fact) -> Observation (candidate interpretations) -> Hypothesis (competing beliefs) -> Knowledge (stable consensus) -> Skill (reusable capability)

---

## Architecture

### Core Modules (9 design docs, 8 implemented)

| Layer | Module | Description | Status |
|:---|:---|:---|:---|
| **Infrastructure** | Event IR + EventBus | Unified event representation, lock-free ring buffer | Implemented |
| | MultiTierPipeline | Fast/slow/deep path orchestration (Tier 0: rule, Tier 1: embedding, Tier 2: LLM) | Implemented |
| | ParameterRegistry | 60+ tunable parameters (anchors + float ranges + adaptive) | Implemented |
| **Observation** | Observation Compiler | 5 domain interpreters (Dialogue/Engineering/Behavior/Memory/User), interpretation generator, surface relation extractor | Implemented |
| **Belief** | Hypothesis Engine | MatchVote + DecayResolve engines, belief state (7-dimension: support/conflict/stability/coverage/recency/novelty/entropy), session tracking | Implemented |
| **Knowledge** | Skill Layer | Distillation engine, evaluation engine, external skill adapter, executor map, capability blueprint | Implemented |
| **World** | Semantic World Model | 7 phases: schema, tree-sitter extraction, community detection (Louvain), backbone coloring (betweenness/pagerank/degree/hybrid), context compiler, incremental updater, LSP interface | Implemented |
| **Scheduling** | Cognitive Scheduler | Task/Worker/Pool/Policy/Scheduler/Monitor + domain tasks | Implemented |
| **Persistence** | Unified Persistence | Node annotation store, dialogue tree persistence adapter | Implemented |

### Knowledge Refinement Pipeline

`
Event (fact) -> Observation (candidate interpretations)
    -> Hypothesis (competing beliefs, evidence voting)
    -> Knowledge (stable consensus, frozen)
    -> Skill (reusable capability blueprint)
`

---

## Project Structure

`
core/agent/v4/
    tiered/              # Multi-tier pipeline system (12 modules)
    world/               # Semantic World Model
    adapter/code/        # Code world adapter (tree-sitter, LSP interface)
    observation_compiler/ # Observation compiler (5 domain interpreters)
    hypothesis_engine/   # Hypothesis engine (belief state, voting, decay)
    skill_layer/         # Skill layer (distillation, evaluation)
    cognitive_scheduler/ # Task scheduling
    persistence/         # Unified persistence
    event_ir.py          # Event IR + EventBus

core/agent/v3_common/    # v3 shared kernel (models, intent, integration)
core/agent/v3_2/         # v3.2 behavioral cognitive framework (20+ modules)
core/agent/v3_0/         # v3.0 six-layer compiler architecture

docs/v3.0/               # 38 design documents (9 v4 + reviews + legacy)
`

---

## Quick Start

### Installation
`ash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh
pip install -r requirements.txt
`

### CLI (v3.2, Mock Mode)
`ash
python scripts/cli_v32.py "write a python function"
python scripts/cli_v32.py --demo
python scripts/cli_v32.py --interactive
`

### Running Tests
`ash
# All v4 tests (304)
python -m pytest core/agent/v4/ -q --noconftest

# Specific module
python -m pytest core/agent/v4/world/tests/ -q --noconftest
`

---

## Design Documents

All design documents in [docs/v3.0/](docs/v3.0/):

| # | Document | Module |
|:---|:---|:---|
| 1 | DESIGN_OBSERVATION_COMPILER.md | Observation Compiler |
| 2 | DESIGN_MULTI_TIER_PIPELINE.md | MultiTierPipeline |
| 3 | DESIGN_TIERED_ACTION_RESOLVER.md | TieredActionResolver |
| 4 | DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md | Persistence Adapter |
| 5 | DESIGN_HYPOTHESIS_ENGINE.md | Hypothesis Engine |
| 6 | DESIGN_SKILL_LAYER.md | Skill Layer |
| 7 | DESIGN_COGNITIVE_SCHEDULER.md | Cognitive Scheduler |
| 8 | DESIGN_SEMANTIC_WORLD_MODEL.md | Semantic World Model |
| 9 | DESIGN_TIERED_PARSER.md | Syntactic Decomposer |


---

## Usage Example

### Programmatic Pipeline

`python
from core.agent.v4.event_ir import EventIR
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

# Start the v4 cognitive runtime
engine = CognitiveRuntimeEngine()
engine.start()

# Send a user event - triggers Observation -> Hypothesis pipeline
event = EventIR(
    id="ev1",
    kind="dialog.message",
    payload={"text": "add monitoring to the gateway", "source": "user"}
)
engine.on_event(event)

# Checkpoint: run Hypothesis Engine on accumulated observations
results = engine.trigger_checkpoint()

# Inspect stats
for path_name, stats in engine.stats.items():
    print(f"{path_name}: {stats.trigger_count} triggers, "
          f"{stats.success_count} success, {stats.failure_count} failure")

engine.stop()
`

### Runtime DAG Builder

`python
from core.agent.v4.cli.builder import RuntimeBuilder

# Build a custom pipeline
builder = RuntimeBuilder("my-pipeline")
dag = (builder
    .add_module("obs", "observation_compiler")
    .add_module("hyp", "hypothesis_engine", path="slow", trigger="checkpoint")
    .connect("obs", "hyp")
    .param("hyp", "min_support", 8)
    .build())

# Export as YAML config
dag.save("config/my-runtime.yaml")
`

### Context Assembly

`python
from core.agent.v4.context.assembler import ContextAssembler
from core.agent.v4.context.source import KnowledgeSource, WorldSource

# Create knowledge sources
sources = [KnowledgeSource(nodes), WorldSource(graph)]
assembler = ContextAssembler(sources)

# Assemble context for an intent
ctx = assembler.assemble("gateway monitoring", top_k=10)
for item in ctx.top_k(5):
    print(f"[{item.source}] relevance={item.relevance:.2f}")
`

---

## Deployment Guide

### Prerequisites
- Python 3.9+
- pip

### Quick Deploy (Development)
`ash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh
pip install -r requirements.txt
python -m pytest core/agent/v4/ -q --noconftest  # Verify: 376 tests pass
`

### Production Setup
`ash
# 1. Create persistent database
mkdir -p data
python -c "from core.agent.v4.persistence.unified_store import UnifiedGraphStore; s=UnifiedGraphStore('data/dialogmesh.db'); s.open(); s.close()"

# 2. Customize runtime config
cp config/runtime.yaml config/runtime-prod.yaml
# Edit: adjust timeouts, retry counts, trigger thresholds

# 3. Start runtime
python -c "
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
engine = CognitiveRuntimeEngine(config_path='config/runtime-prod.yaml')
engine.start()
# ... handle events ...
engine.stop()
"
`

### Configuration
Edit [config/runtime.yaml](config/runtime.yaml) to adjust:
- Path timeouts and retry policies
- Checkpoint trigger thresholds (event count, time interval)
- Parameter overrides for each module

---

## Known Limitations

### Current Scope
- **Python-only**: No cross-language SDK (Go/Java/JS). Designed as a Python cognitive engine.
- **Single-machine**: Designed for single-node deployment. No distributed coordination beyond basic etcd locks.
- **Text + Code**: Multimodal (image/audio/video) not yet supported. Focus on text and code reasoning.
- **Pre-1.0**: API stability not guaranteed. Breaking changes may occur between releases.

### Performance
- **Not benchmarked at scale**: Test datasets are small/medium projects and short conversations. No performance data for 10M+ graph nodes or 100K+ dialogue events.
- **Betweenness centrality**: O(N^3) on large graphs. Use PageRank or Degree strategy via world.importance.strategy for graphs >5000 nodes.
- **No GPU optimization**: All computation is CPU-bound. Hypothesis Engine belief propagation runs on CPU.

### Integrations
- **Storage backends**: SQLite is the only production-ready backend. Neo4j and Milvus adapters are reserved as future interfaces.
- **No cloud-native features**: No multi-tenancy, RBAC, quota management, or billing modules. Designed for private/internal deployment.
- **Fast Path**: The DomainSelector/BudgetAllocator/ContextSerializer pipeline is not yet implemented. LLM context assembly currently uses the ContextSource + Assembler pattern.

### Maintenance
- **Solo maintainer**: No team schedule, community contributors, or fixed release cadence.
- **Feedback lag**: Temporal misalignment between events and observations not yet compensated. May affect convergence metrics on rapid interaction sequences.


---

## License

MIT
