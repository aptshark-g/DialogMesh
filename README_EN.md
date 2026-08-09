# DialogMesh

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python"></a>
  <a href="https://github.com/aptshark-g/DialogMesh"><img src="https://img.shields.io/badge/tests-1900%2B-green" alt="Tests"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/Lang-中文-blue" alt="中文"></a>
</p>

**A self-growing cognitive runtime.** DialogMesh is a general-purpose LLM Agent engine — it doesn't just run workflows, it **grows them**: when it meets a new task, the engine generates an execution plan on the spot, runs it with real tools, and distills successful paths into reusable templates. The more you use it, the better it gets.

Bring any model — DeepSeek, OpenAI, Anthropic, or local Ollama — all through the built-in switch gateway. Keys stay yours; data stays on your machine.

---

## What it can do for you

- **Write and run code** — "write a hello world and run it" → the agent writes the file, executes it, reads the output, and reports back (real function calling, not a paper plan)
- **Search papers / browse the web** — built-in arxiv search, web fetch, PDF parsing; unified recall mixes history, knowledge, and semantic relations
- **Control terminals and files** — shell, Python, background long-running sessions, directory listing, grep — all behind a permission gate (4-level risk grading; chained commands and out-of-root writes are blocked)
- **Plan multi-step tasks itself** — give it a goal ("design a service with JWT auth"), it generates a task graph, you confirm, it executes node by node
- **Remember your preferences** — user profile (OCEAN/MBTI/inertia), behavior-chain prediction, discourse tree context management
- **Fully white-box** — graphs / context / profiles are viewable and editable; every edit and decision is recorded, reviewable, and revertible

One example that shows the difference: ask it to **"make a Minecraft-style mini-game in 5 minutes"**. A typical agent hand-crafts a task plan until it times out. DialogMesh's metacognitive layer watches the plan, detects "this path will overrun the budget," and proactively rules a switch (e.g. download an open-source build and adapt it) — then surfaces that switch as a changelog entry you can approve, reject, or constrain, without interrupting execution.

---

## How it works

Tell DialogMesh what you want, and it becomes a **task map** (a DAG, similar to LangGraph / AWS Step Functions):

1. **Plan** — "find recent papers about X" → the orchestrator checks distilled workflows first; if none, an LLM generates one on the spot (LLM-driven workflow generation).
2. **Execute** — independent steps run **in parallel** (same-Tick fan-out, Petri-net semantics); tools pass permission checks before running; results feed back into the conversation.
3. **Confirm** — high-risk steps pause for your approval (PlanGate); low/medium-risk changes are recorded as decision events you can review later (GitHub-changelog style) and approve / reject.
4. **Learn** — successful generated workflows are **distilled into templates**; failures carry attribution (plan / constraint / data / tool) that flows back to the responsible layer.

```
┌──────────────────────────────────────────────────────┐
│            Orchestration (task map, macro acyclic)   │
│      built-in templates · LLM-generated · meta sink  │
├───────────────┬────────────────┬─────────────────────┤
│  7 parallel   │  Tool execution│  Metacognition      │
│  memory trees │  pre-check +   │  micro deviation →  │
│  (discourse/  │  ReAct retry   │  macro plan change  │
│  behavior/… ) │  sandbox/perms │                     │
└───────────────┴────────────────┴─────────────────────┘
```

---

## Core capabilities

| Capability | Meaning |
|---|---|
| **Self-growing workflows** | New task → LLM generates plan → success is distilled into a template. No manual enumeration of every flow. |
| **Parallel orchestration** | Same-Tick steps run concurrently (fan-out/fan-in), cross-Tick dependencies enforced — guarded Petri nets. |
| **White-box by design** | Every graph node, tree block, and relation is viewable and editable. Edits are recorded and replayable — Git-style version control for cognition. |
| **Bidirectional attribution learning** | Tool failures carry attribution (plan/constraint/data/tool) back to the responsible layer. Deviation is nutrition, not error. |
| **Metacognitive loop** | A second brain: audits decisions, arbitrates micro failures into macro plan changes, and can change the plan mid-execution. |
| **Approval gating** | Writes, sends, and high-risk steps pause for confirmation — low-risk async logs, high-risk PlanGate. |
| **Model-agnostic gateway** | switch gateway: 9+ providers, circuit breaker, adaptive concurrency, weighted routing. Bring your own key. |
| **Aging memory** | Events are never dropped — hot (full) / warm (pruned by importance) / cold (semantic summaries, invertible). |
| **Unified recall** | BGE vectors + BM25 + syntactic (SPO) projection + HyDE expansion + association fusion (RRF), provenance-weighted confidence. |
| **Testable, verifiable** | 1900+ pytest cases, green within module domains; frontend tsc zero errors. |

---

## Compared with mainstream agents

| | DialogMesh | Claude Code / Cursor | OpenClaw | Plain RAG + ReAct |
|---|---|---|---|---|
| Workflow generation | ✅ LLM-generated + distilled | ❌ fixed steps | 🟡 template-first | ❌ fixed |
| Execution transparency | ✅ view / edit / rollback every step | ❌ black box | 🟡 partial | ❌ |
| Metacognitive arbitration | ✅ micro failure → macro replan (bidirectional) | ❌ | ❌ | ❌ |
| Decision traceability | ✅ changelog + intervene | ❌ | 🟡 session logs | ❌ |
| Tiered memory | ✅ hot/warm/cold + never-dropped events | 🟡 context window | 🟡 session memory | 🟡 vector store |
| Multi-step parallelism | ✅ same-Tick parallel + deps enforced | 🟡 | 🟡 | ❌ |
| Channels / multimedia | 🕓 roadmap | — | ✅ strength | — |
| Ecosystem maturity | 🕓 new project | ✅ | ✅ | ✅ |

> Honest note: channel integrations (Telegram/Slack/Discord…), multimedia, and Docker/SSH terminal backends are roadmap items, not yet implemented.

---

## Quick start

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# Configure provider keys
# edit gateway/provider.yaml → fill in API Key

# Windows
start.bat

# or manually:
python scripts/start_server.py
```

- switch gateway: http://localhost:8080 (LLM proxy, 9+ providers)
- API: http://localhost:8000/docs
- Frontend: http://localhost:4173 (React) — `cd frontend && npx vite preview --port 4173`

> Restart `start.bat` after changing provider.yaml or backend code (the gateway hot-reloads config every 5s).

---

## Architecture at a glance

```
user input → [cognitive routing] → [intent] → [profile prior] → [orchestrator DAG]
                    │                                        │
                    └──────── task graph (parallel) ←────────┘

Execution:  StateMachine runs nodes (cognitive-chain handlers + tool nodes)
            LLM function calling (tool_loop) — code/implementation requests
Monitoring: Hot signals → Warm verdict (timeout/failure-rate) → Cold review (every 5 turns)
Trace:      Decision event stream → /v6/changelog (review/intervene) + /v6/execution
```

Status: orchestration ✅ · memory trees ✅ · metacognition ✅ · execution layer ✅ · semantic storage ✅ · white-box editing ✅ · gateway ✅

Detailed architecture (mermaid three-layer diagram): [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) and [execution-layer design](docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md).

---

## Design philosophy (why)

DialogMesh is built on a cognitive pipeline: **Event → Observation → Hypothesis → Knowledge → Skill**. Each module observes from its own (first-person) view and validates at a finer granularity (second-person: structure / semantics / timing / counter-example).

Core axioms:

| Axiom | Meaning |
|---|---|
| **Tree is the reasoning workbench** | The discourse tree is first a reasoning tree — it manages inference focus, not total recall. Forgetting uses activation counts, not time decay. |
| **Beliefs are contested** | Decisions don't trust a single confidence — they weigh 7 belief dimensions (support/conflict/stability/coverage/novelty/entropy). |
| **Relations > prompts** | Context is a compiled local knowledge snapshot (subgraph), not a sentence in a prompt. |
| **Abstraction quality = invertibility** | Compressed products must be reversible (coverage 60-80%). Summaries change scale, not detail. |
| **Records are never deleted** | Event chains and edit history are not cleaned up for "tidiness". Consistency is recorded, not locked. |
| **Deviation = nutrition** | Every failure carries attribution that flows back to the responsible layer — the system grows stronger through deviation. |
| **Fast feedback, accurate follow-up, non-blocking** | An immediate answer beats a single perfect answer (System 1/2 fast-slow split). |

Full conventions: [docs/only/wise/PARADIGM.md](docs/only/wise/PARADIGM.md) (axioms A1-A25 + principles P1-P28).

---

## Glossary (our terms ↔ mainstream analogs)

| We call it | Mainstream analog |
|---|---|
| Blueprint | LLM-driven workflow orchestration — DAG + same-Tick parallelism (Petri-net semantics), like LangGraph / Step Functions |
| PCR | Cognitive routing — System 1/2 fast-slow split |
| Association Chain | Semantic relation discovery and promotion — knowledge graph building + causal inference |
| Discourse Tree | Conversation state tracking + topic focus — dialogue-state tracking |
| Behavior Chain | User behavior prediction — predictive modeling + DPO preference learning |
| Engineering Chain | Code/design constraint propagation — rule/constraint engine |
| Subgraph | Context compilation — local knowledge retrieval for the LLM (GraphRAG-style) |
| Metacognition | Self-reflection / second brain — metacognitive control loop |
| Profile | User profile — OCEAN/BFI trait inference + inertia tracking |
| White-box | Content operable, behavior always recorded — inspect/edit/add/delete is a promise, not a feature |
| tool_loop | LLM autonomous tool-call loop — function calling / ReAct |

---

## Docs

| Doc | Content |
|---|---|
| [Architecture overview](docs/ARCHITECTURE_OVERVIEW.md) | Three-layer cognitive runtime: orchestration × memory × metacognition |
| [V1 capability checklist](docs/only/V1_FUNCTION_CHECKLIST_20260808.md) | End-to-end self-check (benchmarked against OpenClaw/Hermes/OpenWorker) |
| [Execution-layer design](docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md) | Blueprint macro × execution micro × metacognitive monitoring |
| [Design paradigm](docs/only/wise/PARADIGM.md) | Axioms A1-A25 + principles P1-P28 + conflict meta-rules |
| [API reference](docs/GUI_API.md) | 130+ endpoints |
| [Changelog](CHANGELOG.md) | Version history |

---

*An agent that learns to be useful.*
