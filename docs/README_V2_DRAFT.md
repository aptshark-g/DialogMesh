# DialogMesh v6

<p align="center">
  <img src="assets/banner.png" alt="DialogMesh" width="100%">
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python"></a>
  <a href="docs/INDEX.md"><img src="https://img.shields.io/badge/docs-INDEX-green" alt="Docs"></a>
</p>

**The self-growing agentic runtime.** DialogMesh is a cognitive runtime for LLM agents that doesn't just execute workflows — it **grows them**: the engine generates workflows on the fly for new tasks, executes them with real tools, and converts the ones that succeed into reusable templates. The more you use it, the more it knows how to get things done.

Bring any model — DeepSeek, OpenAI, Anthropic, or a local Ollama endpoint — through the built-in switch gateway. Your keys, your machine.

## How it works

Tell DialogMesh what you want, and it turns into a **task map** (a DAG, like LangGraph or AWS Step Functions):

1. **Plan** — "find recent papers about X" → the orchestrator picks a known workflow, or asks the LLM to generate one on the spot (LLM-driven workflow generation).
2. **Execute** — steps run **in parallel** where dependencies allow (same-tick fan-out, Petri-net style); tools execute with pre-call validation, results flow back into the conversation.
3. **Check in** — consequential steps pause for your approval (PlanGate); every decision is recorded as an event you can review later, GitHub-log style.
4. **Learn** — successful generated workflows are **distilled into templates**; failures are attributed (plan/constraint/data/tool) and fed back into the corresponding layer.

```
┌──────────────────────────────────────────────────────┐
│            Orchestration (task map, acyclic)         │
│   built-in templates · LLM-generated · learned       │
├───────────────┬────────────────┬─────────────────────┤
│  7 parallel   │  tool execution│  metacognition      │
│  memory trees │  validation +  │  arbitrates micro-  │
│  (discourse / │  ReAct retry   │  failures → macro   │
│  behavior / …)│  sandbox/perms │  plan changes       │
└───────────────┴────────────────┴─────────────────────┘
```

## What it can do

| Capability | What it means |
|---|---|
| **Self-growing workflows** | New task → LLM generates the plan → success distills into a template. No hand-writing every flow. |
| **Parallel orchestration** | Same-tick steps run concurrently (fan-out/fan-in), cross-tick dependencies are enforced — like a Petri net with guard rails. |
| **White-box by design** | Every graph node, tree block, and relation is visible and editable. Edits are journaled and replayed — Git-style versioning for cognition. |
| **Bidirectional learning** | Tool failures carry attribution (plan / constraint / data / tool) that flows back to the layer that caused them. Deviation is fertilizer, not error. |
| **Metacognition loop** | A second brain that audits decisions, arbitrates micro-failures into macro plan changes, and re-plans mid-execution when needed. |
| **Approval-gated actions** | Writes, sends, and risky steps pause for your OK — asynchronous log for low risk, PlanGate for high. |
| **Model-agnostic gateway** | switch gateway: 9+ providers, circuit breaker, adaptive concurrency, weighted routing. Bring your own key. |
| **Memory that ages** | Events are never dropped — hot (full), warm (pruned by importance), cold (semantically summarized, reversible). |

## Quick start

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# configure provider keys
# edit gateway/provider.yaml → fill in API Key

# Windows
start.bat

# or manually:
python scripts/start_server.py
```

- Switch Gateway: http://localhost:8080 (LLM proxy, 9+ providers)
- API: http://localhost:8000/docs
- Frontend: http://localhost:4173 (React) — `cd frontend && npx vite preview --port 4173`

## Architecture at a glance

```
user input → [cognitive routing] → [intent] → [profile prior] → [orchestration DAG]
                  │                                              │
                  └── task graph (parallel steps) ←──────────────┘

status:   orchestration ✅ · memory trees ✅ · metacognition ✅
          semantic storage ✅ · white-box editing ✅ · gateway ✅
```

## Terminology (self-coined ↔ mainstream)

| We call it | Mainstream analog |
|---|---|
| 蓝图 (Blueprint) | LLM-driven workflow orchestration — DAG + same-tick parallelism (Petri-net semantics), like LangGraph / Step Functions |
| PCR | Cognitive routing — System 1/2 fast-vs-deep dispatch |
| 关联链 (Association Chain) | Semantic relation discovery & promotion — knowledge-graph construction + causal inference |
| 对话树 (Discourse Tree) | Conversation state tracking + topic focus — dialogue-state tracking |
| 行为链 (Behavior Chain) | User behavior prediction — predictive modeling + DPO preference learning |
| 工程链 (Engineering Chain) | Constraint propagation for code/design — rule/constraint engine |
| 子图 (Subgraph) | Context compilation — subgraph retrieval for LLM context (GraphRAG-style) |
| 元认知 (Metacognition) | Self-reflection / second brain — meta-cognitive control loop |
| 画像 (Profile) | User profiling — OCEAN/BFI trait inference + inertia tracking |
| 温度系统 (Temperature) | Multi-factor attention/heat weighting over memory |

## Docs

| Doc | Content |
|---|---|
| [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md) | Three-layer cognitive runtime: orchestration × memory × metacognition |
| [Glossary](docs/GLOSSARY.md) | Full self-coined → mainstream term mapping |
| [API Reference](docs/GUI_API.md) | 90+ endpoints |
| [Gateway Design](switch/docs/BUSINESS_CHAIN_01_GATEWAY.md) | switch gateway internals |
| [Implementation Reality](docs/IMPLEMENTATION_REALITY.md) | Code vs design coverage |

---

*Built with ❤️ for agents that learn from use.*
