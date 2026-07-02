# DialogMesh v3.0

> Multi-layer LLM Cognitive Architecture for Conversational Agents — 6 LLM instances, Cognitive Duplex, Dual-Tree Structure

---

## Introduction

**DialogMesh** is an industrial-grade conversational agent system built on a multi-layer LLM cognitive architecture. Version 3.0 introduces a six-layer LLM collaborative cognitive engine, featuring **Cognitive Duplex** architecture where an Algorithmic Engine runs in parallel with an LLM Engine, with outputs fused by a **Fusion Engine** using weighted scoring. The system is driven by a **Dual-Tree Structure** — the **Cognitive Tree** for precise dialogue state modeling and the **Topic Tree** for persistent user topic tracking.

DialogMesh is designed for complex multi-turn dialogue scenarios, supporting dynamic planning, tool registration and binding, full-stack observability, and an asynchronous FastAPI + WebSocket service layer.

---

## Core Features

### 1. Six-Layer LLM Cognitive Architecture

| LLM Instance | Role | Key Output |
|--------------|------|------------|
| **PCR-LLM** | Protocol Compatible Router — initial routing and intent pre-classification | Routing decision, protocol compatibility judgment |
| **Intent-LLM** | Intent Parsing — structured intent extraction from user queries | IntentLabel, confidence, slot filling |
| **Planning-LLM** | Planning Generation — task decomposition and strategy selection | Plan graph, Skill selection, dependency graph |
| **Meta-Cognitive-LLM** | Meta-Cognitive Monitoring — cognitive state assessment and resource scheduling | Cognitive load, strategy adjustment recommendations |
| **Reflective-LLM** | Reflective Validation — output quality assessment and self-correction | Consistency score, correction suggestions |
| **Answer-LLM** | Answer Generation — final response synthesis and formatting | Structured response, multi-format output |

The six LLM layers are orchestrated by the **Cognitive Compiler**, supporting cascade activation and shortcut optimization.

### 2. Cognitive Duplex Fusion Engine

```
┌─────────────────┐     ┌─────────────────┐
│ Algorithm Engine│     │   LLM Engine    │
│  • Rule routing │  ║  │  • Semantic     │
│  • Vector ret.  │  ║  │    understanding│
│  • Pattern match│  ║  │  • Reasoning    │
│  • Stat. decision│ ║  │  • Generation   │
│                 │  ║  │  • Reflection   │
└────────┬────────┘  ║  └────────┬────────┘
         │           ║            │
         └───────────╫────────────┘
                     ║
              ┌──────┴──────┐
              │ Fusion Engine│
              │ Weighted Fusion│
              └──────┬──────┘
                     ↓
              Final Response
```

The Algorithm Engine and LLM Engine execute in parallel. The Fusion Engine performs dynamic weighted fusion based on multi-dimensional scoring (confidence, latency, cost), enabling collaborative "fast thinking + slow thinking" decision-making.

### 3. Dual-Tree Structure

#### Cognitive Tree
- **Node/Edge Model**: Nodes carry cognitive states; edges represent cognitive transitions
- **Lifecycle Management**: ACTIVE → COOLING → COLD → ARCHIVED state machine
- **Access Control**: Role-based node read/write permissions (RBAC)
- **Transactional Writes**: ACID-guaranteed cognitive state persistence
- **Cross-Reference**: Semantic inter-node associations and navigation

#### Topic Tree
- User topic tracking and hierarchical organization
- Orthogonal dual-tree with Cognitive Tree: Topic Tree tracks "what topics the user discussed", Cognitive Tree tracks "how the system understands"
- Supports topic continuation, switching, backtracking, and nested sub-topics

### 4. Planning Skill Layer

**5 Core Primitives**:

| Primitive | Description | Use Case |
|-----------|-------------|----------|
| **DivideConquer** | Recursive decomposition of complex tasks | Multi-step analysis, batch processing |
| **ConditionalBranch** | Dynamic path selection | Decision trees, user intent routing |
| **LoopUntil** | Iterate until condition is met | Data retrieval, validation convergence |
| **SearchVerifyExecute** | Search → Verify → Execute | RAG, tool invocation, fact-checking |
| **TreeOfThought** | Multi-path exploration with backtracking | Complex reasoning, creative generation |

**Three-Level SkillDetail**:
- `HIGH` — Output planning name and parameters only
- `MEDIUM` — Output planning name + brief description + parameters
- `DETAIL` — Complete plan graph, dependency graph, and execution steps

**Fallback Chain**: Automatic degradation on planning failure (ToT → DivideConquer → Single-step execution), ensuring system robustness.

### 5. Tool Registry & Binding

- **SchemaGuard**: Parameter Schema validation and compatibility checking
- **ToolBindingEngine**: Runtime parameter binding and type coercion
- **Permission Control**: Tool-level access permissions (`tool_registry/permission.py`)
- **Discovery & Shortlisting**: Automatic tool discovery + relevance ranking

### 6. Asynchronous Service Layer

- **FastAPI** + **WebSocket** dual-channel support
- **4 Response Formats**:
  - `BRIEF` — Minimal summary
  - `BALANCED` — Balanced information density
  - `EXPLANATORY` — Detailed explanation
  - `TUTORIAL` — Tutorial-style guided response
- **Session Management**: Multi-session concurrency, state isolation, persistent recovery
- **Response Composer**: Dynamic content assembly based on format selection

### 7. Full-Stack Observability

| Dimension | Component | Capability |
|-----------|-----------|------------|
| **Metrics** | `metrics.py` | Prometheus-compatible metrics collection |
| **Logging** | `logger.py` | Structured logging + multi-level filtering |
| **Tracing** | `tracer.py` | Distributed tracing, call chain visualization |
| **Alerting** | `alert.py` | Threshold alerts + notification channels |
| **Dashboard** | `dashboard.py` | Real-time diagnostic panel |
| **Telemetry** | `telemetry.py` | Telemetry data aggregation and export |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Layer                            │
│  CLI / WebSocket / HTTP API / Third-party Integration        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Service Layer                              │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │   api.py   │ │ agent_service│ │  session_manager     │   │
│  │  (FastAPI) │ │   (Business) │ │   (Session Lifecycle)│   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │websocket_  │ │response_compo│ │   middleware         │   │
│  │  manager   │ │   ser.py     │ │   (Middleware)       │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              app_factory.py (App Factory)             │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  Orchestrator Layer                          │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │ orchestrator│ │  bootstrap   │ │   system_bootstrap   │   │
│  │   .py      │ │   (Runtime)  │ │   (System Boot)      │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Agent Core Layer                           │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │cognitive_  │ │  cognitive_  │ │   context_manager    │   │
│  │  tree/     │ │  compiler/   │ │   (Context Mgmt)     │   │
│  │  (Dual Tree)│ │  (Compiler) │ │                       │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────────────┐   │
│  │  planning/ │ │ llm_providers│ │   tool_registry      │   │
│  │  (Skills)   │ │   (Adapters) │ │   (Tool Registry)    │   │
│  └────────────┘ └──────────────┘ └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              observability/ (Observability)           │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Infrastructure Layer                       │
│  Config (config/) / Data Models (data_models.py) / Test Suite │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Requirements

- Python 3.11+
- PyTorch 2.0+ (CPU sufficient, GPU optional)
- Memory: 8GB+ recommended
- Disk: ~500MB (models + dependencies)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/DialogMesh.git
cd DialogMesh

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# Or in development mode
pip install -e ".[dev]"
```

### Configuration

```bash
# Copy example config
cp config/user_config.yaml.example config/user_config.yaml

# Edit config/user_config.yaml, add your LLM API keys
# Supports: OpenAI / DeepSeek / Local LMStudio / Ollama
```

### Running Tests

```bash
# Run all tests (327 test cases)
pytest core/agent/v3_0/ core/service/v3_0/ -v

# Run specific module tests
pytest core/agent/v3_0/planning/tests/ -v
pytest core/agent/v3_0/cognitive_tree/tests/ -v
pytest core/agent/v3_0/tool_registry/tests/ -v

# With coverage report
pytest core/agent/v3_0/ core/service/v3_0/ --cov=core --cov-report=term-missing
```

### Launch Service

```bash
# Start main service (FastAPI + WebSocket)
python main_v3.py

# Default port: 8000
# API docs: http://localhost:8000/docs
# WebSocket: ws://localhost:8000/ws
```

---

## Project Structure

```
DialogMesh/
├── main_v3.py                          # Service entry point
│
├── core/
│   ├── agent/v3_0/                     # Agent Core (v3.0)
│   │   ├── cognitive_tree/               # Cognitive Tree + Topic Tree Dual-Tree
│   │   │   ├── manager.py                # Tree manager (nodes/edges/lifecycle)
│   │   │   ├── models.py                 # Node/edge data models
│   │   │   ├── cross_ref.py              # Cross-reference navigation
│   │   │   └── tests/
│   │   ├── cognitive_compiler/           # Cognitive Compiler
│   │   │   ├── compiler.py               # Compiler main entry
│   │   │   ├── edge_manager.py           # Edge lifecycle management
│   │   │   ├── access_control.py         # Access control (RBAC)
│   │   │   ├── lifecycle.py              # Node lifecycle state machine
│   │   │   ├── event_bus.py              # Cognitive event bus
│   │   │   └── querier.py                # Cognitive query engine
│   │   ├── llm_providers/                # LLM Provider Adapters
│   │   │   ├── provider_manager.py       # Unified ProviderManager
│   │   │   ├── base.py                   # Abstract base classes
│   │   │   ├── openai_provider.py        # OpenAI / DeepSeek adapter
│   │   │   ├── local_provider.py         # LMStudio / Ollama local adapter
│   │   │   ├── failover_provider.py      # Failover provider
│   │   │   ├── hybrid_router.py          # Hybrid routing
│   │   │   ├── mock_provider.py          # Mock for testing
│   │   │   ├── circuit_breaker.py        # Circuit breaker
│   │   │   └── streaming.py              # Streaming response handler
│   │   ├── context_manager/              # Context Management
│   │   │   ├── manager.py                # Context manager
│   │   │   ├── window.py                 # Context window management
│   │   │   ├── store.py                  # Context storage
│   │   │   └── models.py                 # Context data models
│   │   ├── planning/                     # Planning Skill Layer
│   │   │   ├── planner.py                # Planner main entry
│   │   │   ├── skill_engine.py           # Skill execution engine
│   │   │   ├── skill_registry.py         # Skill registry
│   │   │   ├── skill_matcher.py          # Skill matcher
│   │   │   ├── decomposition.py          # Task decomposition
│   │   │   ├── dependency_resolver.py    # Dependency resolution
│   │   │   ├── scheduler.py              # Execution scheduler
│   │   │   ├── optimizer.py              # Plan optimization
│   │   │   ├── fallback.py               # Fallback chain
│   │   │   ├── strategy_selector.py      # Strategy selector
│   │   │   ├── agent_allocator.py        # Agent allocation
│   │   │   └── tests/
│   │   ├── tool_registry/                # Tool Registry & Binding
│   │   │   ├── registry.py               # Tool registry
│   │   │   ├── binding.py                # ToolBindingEngine
│   │   │   ├── executor.py               # Tool executor
│   │   │   ├── permission.py             # Permission control
│   │   │   ├── discovery.py              # Tool discovery
│   │   │   ├── shortlister.py            # Tool shortlisting
│   │   │   └── models.py                 # Tool data models
│   │   ├── observability/                # Observability
│   │   │   ├── metrics.py                # Metrics collection
│   │   │   ├── logger.py                 # Structured logging
│   │   │   ├── tracer.py                 # Distributed tracing
│   │   │   ├── alert.py                  # Alerting system
│   │   │   ├── dashboard.py              # Diagnostic panel
│   │   │   ├── telemetry.py              # Telemetry aggregation
│   │   │   └── store.py                  # Observability data store
│   │   ├── orchestrator/                 # Orchestrator
│   │   │   ├── orchestrator.py           # Main orchestrator (6 LLM collaboration)
│   │   │   ├── bootstrap.py              # Runtime bootstrap
│   │   │   └── models.py                 # Orchestration data models
│   │   ├── system_bootstrap.py           # System bootstrap entry
│   │   ├── data_models.py                # Global data models
│   │   └── __init__.py
│   │
│   └── service/v3_0/                     # Service Layer (v3.0)
│       ├── api.py                        # FastAPI routes
│       ├── agent_service.py              # Agent business logic
│       ├── session_manager.py            # Session management
│       ├── websocket_manager.py          # WebSocket connection management
│       ├── response_composer.py          # Response format composer
│       ├── app_factory.py                # Application factory
│       ├── middleware.py                 # Middleware
│       ├── data_models.py                # Service data models
│       ├── tests/
│       └── __init__.py
│
├── config/                               # Configuration
│   ├── agent_config.yaml                 # Default configuration
│   ├── user_config.yaml                  # User config (not in git)
│   ├── user_config.yaml.example          # Config example
│   └── expertise_lexicon.yaml            # Domain lexicon
│
├── docs/v3.0/                            # Design Documents
│   ├── DESIGN_FULL_CONCEPT.md            # Overall architecture
│   ├── DESIGN_MULTILAYER_LLM_COGNITIVE.md # Multi-layer LLM design
│   ├── DESIGN_PLANNING_SKILL_LAYER.md    # Planning Skill layer design
│   ├── DESIGN_TASK_PLANNING_DYNAMIC.md   # Dynamic task planning design
│   ├── ENGINEERING_*.md                  # 16 engineering docs
│   └── ...
│
├── tests/                                # Integration tests
├── requirements.txt                      # Dependencies
├── pyproject.toml                        # Project config
├── README.md                             # This file (Chinese)
├── README_EN.md                          # English documentation
├── MANIFEST.md                           # Project manifest
├── CONTRIBUTING.md                       # Contribution guidelines
└── CHANGELOG.md                          # Changelog
```

---

## Technical Highlights

| Technology | Implementation | Advantage |
|------------|----------------|-----------|
| **Six-Layer LLM Collaboration** | PCR → Intent → Planning → Meta → Reflective → Answer | Cascade activation, shortcut optimization, fine-grained cognitive division |
| **Cognitive Duplex** | Algorithm Engine ∥ LLM Engine + Fusion Engine | Optimal trade-off between latency and quality; supports fast/slow thinking switching |
| **Dual-Tree Structure** | Cognitive Tree ⊕ Topic Tree | Orthogonal modeling: system understanding + user topics separated |
| **Planning Skill Primitives** | 5 primitives × 3 detail levels × fallback chain | Complex tasks automatically decomposed; robust execution |
| **SchemaGuard** | Parameter Schema validation + ToolBindingEngine | Type-safe tool invocation; runtime compatibility |
| **Observability** | Metrics/Logs/Traces/Alerts/Dashboard/Telemetry 6D coverage | Production-grade monitoring and diagnostics |
| **Async Service** | FastAPI + WebSocket + 4 response formats | High concurrency, low latency, multi-scenario adaptation |
| **LLM Adapter Layer** | ProviderManager + Circuit Breaker + Failover | Seamless multi-model switching; high availability |

---

## Performance Benchmarks

| Metric | Value |
|--------|-------|
| Total test cases | **327** |
| Test pass rate | **100%** |
| Core source files | **87** |
| Total lines of code | **~31,716** |
| Engineering documents | **16** |
| Design documents | **4** |

### Test Coverage Modules

- `cognitive_tree/tests/` — Node/edge lifecycle, transactional writes, RBAC
- `cognitive_compiler/` — Compiler, edge management, event bus
- `llm_providers/tests/` — ProviderManager, circuit breaker, failover, streaming
- `context_manager/tests/` — Context management, window management, storage
- `planning/tests/` — Planner, Skill engine, decomposition, scheduling, fallback
- `tool_registry/tests/` — Registration, binding, execution, permissions, discovery
- `observability/tests/` — Metrics, logs, traces, alerts
- `orchestrator/tests/` — Orchestrator, six-layer LLM collaboration
- `service/v3_0/tests/` — FastAPI, WebSocket, sessions, response composition

---

## Roadmap

- [x] **v3.0** — Multi-layer LLM cognitive architecture (6 LLM instances, Cognitive Duplex, Dual-Tree, Planning Skills, 327 tests)
- [ ] **v3.1** — Cognitive Tree visualization panel, automatic Topic Tree pruning optimization
- [ ] **v3.2** — Multi-modal input support (images, voice, documents)
- [ ] **v3.3** — Distributed deployment (multi-instance orchestration, load balancing, state sharing)
- [ ] **v4.0** — Autonomous learning and evolution (online Skill learning, Cognitive Tree self-optimization)

---

## License

MIT License

---

## Related Documents

- [Chinese README](README.md)
- [Project Manifest](MANIFEST.md)
- [Changelog](CHANGELOG.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Design Documents](docs/v3.0/)
