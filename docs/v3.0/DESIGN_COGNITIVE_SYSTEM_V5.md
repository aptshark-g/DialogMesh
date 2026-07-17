# DialogMesh v5: From Retrieval System to Cognitive System

## Status: Design Phase (July 2026)
## Authors: APTShark + Agent

---

## 1. Core Insight

DialogMesh v4 successfully built SemanticObject, RelationSubstrate, CognitiveWorkspace, and Runtime. But the system remained fundamentally **reactive** — the LLM answered, then waited. 

The v5 upgrade is a single architectural shift:

```
Reactive LLM  →  Active LLM
Prediction    →  Simulation
BehaviorGraph →  Cognitive Trace
State         →  State Transition
```

## 2. Architecture: Before vs After

### v4 (Current)
```
Conversation
    ↓
BehaviorGraph (external: Q1→Q2→Q3)
    ↓
ConceptGraph
    ↓
Knowledge
    ↓
Reflection
```

### v5 (Target)
```
External Conversation
    ↓
Conversation Tree (user-visible history)
    ↓
Semantic Object World (what exists)
    ↓
Cognitive Workspace (active reasoning space)
    ↓
Internal Simulation (LLM stands in user's mind and asks itself)
    ↓
Prediction / Question Generation
    ↓
Reflection (was prediction correct?)
    ↓
Learning (improve simulation strategy)
    ↓
Knowledge Update (commit what was learned)
```

### Key: Simulation replaces Prediction

| | v4 Prediction | v5 Simulation |
|---|---|---|
| Method | Topic transition statistics | LLM constructs User Cognitive State, stands inside it |
| Cold start | Useless (no history) | Works immediately (Theory of Mind) |
| Output | "User might ask X" | "I would ask X, Y, Z with confidence 0.82" |
| Learning | None | Self-supervised: match→reward, miss→penalize |
| Meta | None | Learns WHICH simulation strategy works best |

## 3. Simulation Engine Design

### 3.1 Core Loop
```
Turn N: LLM answers user
    ↓
Simulation Engine activates:
  1. Build User Cognitive State (what user knows, what gaps remain)
  2. LLM: "If I were this user, what 3 questions would I ask next?"
  3. Generate questions + confidence scores
    ↓
Turn N+1: User asks actual question
    ↓
Evaluation:
  BGE semantic similarity between predicted and actual
  Match > 0.6 → Reward (+0.09 to +0.15 confidence delta)
  No match → Penalty (-0.05)
    ↓
Strategy Learning:
  simulation strategy weight += 0.05 (match) or -= 0.02 (miss)
  topic_transition weight adjusted similarly
  gap_filling weight adjusted similarly
```

### 3.2 Key Design Decisions

**Why Theory of Mind instead of statistics?**
- Statistical prediction needs history → cold start failure
- ToM works from turn 1: "User asked about Runtime. They probably don't know about Observation or Normalizer. If I were them, I'd ask how these connect."

**Why BGE for evaluation instead of exact match?**
- User may ask semantically equivalent question with different words
- BGE cosine > 0.6 counts as partial match → enables gradient learning

**Why strategy weights?**
- Different situations need different simulation approaches
- System learns which approach works best for which user
- This is meta-learning: learning HOW to simulate, not WHAT to simulate

## 4. Cognitive Trace (BehaviorGraph → ExecutionTrace)

### 4.1 The Problem with BehaviorGraph
BehaviorGraph records: `User Q1 → Assistant A1 → User Q2 → Assistant A2`

This is the **visible surface**. It doesn't capture:
- What observations were made
- Which hypotheses were formed and rejected
- Where conflicts occurred
- How confidence evolved

### 4.2 Cognitive Trace
Records the **internal execution**:
```
Trace {
  perspective: "architecture",
  active_objects: [Runtime, Observation, Normalizer],
  attention: {Runtime: 0.9, Observation: 0.7},
  retrieved_objects: [EventIR, ConceptGraph],
  hypotheses: [
    "User needs understanding of Runtime→Observation flow",
    "User may be confused about Normalizer role"
  ],
  rejected_hypotheses: [],
  reasoning_tree: {
    root: "Runtime → Observation → Normalizer → Projector",
    branches: ["Why Normalizer?", "Alternative: direct parsing"]
  },
  reflection: {
    confidence_delta: +0.12,
    knowledge_commits: ["Normalizer bridges EventIR to SemanticObject"]
  }
}
```

### 4.3 Why This Matters
- **Replay**: Can re-run the same reasoning path
- **Replay halfway**: Can start from Trace and re-reason from any point
- **Diff**: Compare two Traces to see what changed
- **Meta-learning**: Learn which reasoning patterns work

## 5. RelationGraph as Unified Ontology

### 5.1 The Problem
v4 had separate relation systems:
- ConceptGraph edges (co-occurrence)
- RelationSubstrate edges (typed)
- CausalChain edges (cause→effect)

These were three parallel systems with different semantics.

### 5.2 Unified Relation Model
```
Relation
├── causal (A causes B)
├── contains (A contains B)
├── depends_on (A depends on B)
├── defines (A defines B)
├── implements (A implements B)
├── evolves_to (A evolves into B)
├── contradicts (A contradicts B)
├── analogous_to (A is analogous to B)
└── uses (A uses B)
```

Key insight: **Causal is just one Relation kind with direction and constraint.**

### 5.3 What This Enables
- SemanticObject connected through RelationGraph (single source of truth)
- ReasoningTree uses Relations to traverse
- CausalChain is a high-confidence subset of RelationGraph
- CognitiveTrace records which Relations were activated/created

## 6. Four Spaces → Unified Cognitive Runtime

### 6.1 Current (Four Spaces)
| Space | Purpose | State |
|-------|---------|-------|
| Document | Raw text ingestion | Stable |
| Concept | Structured concepts (10477 objects) | Stable |
| Knowledge | Committed knowledge (persistent) | Partial |
| Cognitive | Active workspace (transient) | Active |

### 6.2 Target: Cognitive Ontology

Answers four questions:
1. **What exists?** → SemanticObject
2. **How are they related?** → RelationGraph (causal is one kind)
3. **How do they activate/evolve during reasoning?** → Workspace + Runtime + Trace
4. **What gets committed?** → KnowledgeSpace

## 7. Implementation Status

| Component | Status | File |
|-----------|--------|------|
| InternalSimulationEngine | ✅ v1 implemented | `cognitive/simulation_engine.py` |
| Engine integration (simulate→evaluate→learn) | ✅ Wired into `on_event()` | `runtime/engine.py` |
| Self-supervised strategy learning | ✅ Strategy weights update | `simulation_engine.py` |
| Cognitive Trace | ⚠️ Design only | — |
| Unified RelationGraph | ⚠️ Design only | — |
| Mental Model (persistent across workspaces) | ❌ Not started | — |

## 8. Relationship to External Research

| Research | Shared Concept | DialogMesh Difference |
|----------|---------------|----------------------|
| Reflexion | Post-hoc reflection | We run simulation BEFORE user asks, not after failure |
| Self-Refine | Generate→critique→revise | We simulate user, not self-critique |
| PreFlect | Pre-execution risk prediction | We simulate cognitive state, not execution risk |
| Anthropic J-space | Internal model representations | We build an EXTERNAL cognitive runtime that surrounds the LLM |
| MIRROR | Inter-agent reflection | We do human-AI co-reflection through simulation |

## 9. Next Steps

1. **Cognitive Trace implementation**: Replace BehaviorGraph with ExecutionTrace
2. **RelationGraph unification**: Merge ConceptGraph + RelationSubstrate + CausalChain
3. **Mental Model**: Persistent model that survives workspace destruction
4. **Simulation quality benchmark**: Track match rate over 100+ turns
