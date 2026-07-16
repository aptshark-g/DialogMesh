# Literature Cortex — Ontology Architecture

> Version: 1.0  
> For DialogMesh cross-project alignment.

---

## System Overview

Literature Cortex is a multi-layer cognitive architecture for automated literature analysis and knowledge graph construction. It operates across five abstraction layers (L0-L4) with a unified verification pipeline (v7.0) and persistent data layer.

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5 (L5) — Meta-Cognitive Arbiter                       │
│  Decision: converge / diverge / far-think / switch-perspective│
├─────────────────────────────────────────────────────────────┤
│  Layer 4 (L4) — Physics / Reality                            │
│  Mechanical, Thermal, Electromagnetic, Material              │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 (L3) — Methods / Algorithms                         │
│  Search, DP, Adaptive, Feedback, Feedforward, ...            │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 (L2) — Mathematics                                  │
│  Optimization, Dynamical Systems, Spectral, Probability      │
├─────────────────────────────────────────────────────────────┤
│  Layer 1 (L1) — Axioms / Foundations                         │
│  ZFC, Peano, Gödel, Noether, Turing, ...                     │
├─────────────────────────────────────────────────────────────┤
│  Layer 0 (L0) — Meta-Theory / Epistemology                   │
│  Double-Loop, Causation, Convergence, Hierarchy, Boundary    │
└─────────────────────────────────────────────────────────────┘
         ↕
┌─────────────────────────────────────────────────────────────┐
│  Unified Verification Pipeline (v7.0)                        │
│  SourceVerify → Prescreen → Layer1-5 → Report               │
├─────────────────────────────────────────────────────────────┤
│  Unified Data Layer (SQLite)                                 │
│  events | nodes | edges | verification_runs | parameters    │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

| Layer | Role | Stability | Update Frequency |
|-------|------|-----------|-----------------|
| L0 | Meta-rules for reasoning about reasoning | Ultra-stable | Manual revision only |
| L1 | Mathematical foundations | Stable | Decades |
| L2 | Mathematical tools and frameworks | Semi-stable | Years |
| L3 | Algorithmic paradigms | Moderate | Months-Years |
| L4 | Physical reality constraints | Stable | New physics only |
| v7 Pipeline | Content verification and validation | Adaptive | Per-query |
| Unified Store | Event sourcing and audit trail | Append-only | Per-operation |

---

## Core Design Principles

1. **Idea over Implementation** — L3 records "adaptive update" as paradigm, not LMS/RLS/Adam as separate entries.
2. **Mathematics over Engineering** — Every node links to its mathematical substrate (e.g., "Adaptive Update" → linear algebra + gradient descent).
3. **Cross-Domain Generality** — L0-L4 usable across control, materials, chemistry, biology, economics.
4. **No External Dependency** — All seeds are JSON files, loadable without network or AI.
5. **Causal Upgrade Ready** — All nodes have `node_id` for graph edge creation.

---

## Data Flow

```
Input (paper / claim / query)
    ↓
[Unified Pipeline v7.0]
    ├─ Source Verification (domain reputation)
    ├─ Prescreen (FAST / SLOW / SKIP)
    ├─ Layer 1: Content classification
    ├─ Layer 2: Formal translation
    ├─ Layer 3-5: Retrieval → Parallel verify → Dialectic → Fuzzy score
    ↓
[Verification Report]
    ├─ Trust level (VERIFIED → MALICIOUS)
    ├─ Confidence score
    ├─ Dialectic report (pro/con)
    └─ Fuzzy score (5 dimensions)
    ↓
[Unified Store]
    ├─ Event log (append-only)
    ├─ Verification runs
    ├─ Feedback records
    └─ Parameters
```

---

## DialogMesh Alignment Points

| Cortex Component | DialogMesh Equivalent | Interop Strategy |
|-----------------|----------------------|-----------------|
| UnifiedEvent | EventIR | Field-compatible, bidirectional adapter |
| UnifiedStore | UnifiedGraphStore | Shared SQLite schema (nodes/edges/events) |
| ParameterRegistry | BeliefState config | Direct parameter map |
| L0-L4 seeds | WorldModel seeds | Seed loader cross-compatible |
| Domain Registry | Domain taxonomy | Shared domain IDs |
| Verification Pipeline | ValidationEngine | Plugin adapter |
| TraceQuery | AuditTrail | Same query interface |

---

## File Index

| File | Purpose | DialogMesh Relevance |
|------|---------|---------------------|
| `docs/SEEDS_L0L4_REFERENCE.md` | L0-L4 node catalog | Seed loading, cross-domain analogy |
| `docs/DOMAIN_REGISTRY.md` | 27-domain mapping table | Domain classification, routing |
| `docs/PARAMETER_REGISTRY.md` | 20+ tunable parameters | Config sync, calibration |
| `lcortex/seeds/seed_L{0-4}.json` | Raw seed data | Direct import |
| `lcortex/seeds/l0l4_reverse_index.json` | Domain → node index | Reverse lookup |
| `lcortex/unified/registry.py` | ParameterRegistry impl | Runtime config |
| `lcortex/unified/store.py` | UnifiedStore impl | Shared persistence |
| `lcortex/unified/event.py` | UnifiedEvent / EventIR | Event bus interop |
| `lcortex/unified/adapter.py` | Legacy → unified adapter | Migration path |

---

## Version History

| Date | Version | Change |
|------|---------|--------|
| 2026-06-14 | 0.1 | Initial L0-L4 seed library |
| 2026-07-02 | 0.2 | Phase 3 lifecycle mechanisms |
| 2026-07-11 | 0.3 | v7.0 unified verification pipeline |
| 2026-07-13 | 0.4 | Unified data layer v1.0 |
| 2026-07-14 | 0.5 | Legacy adapter + CLI unified commands |
| 2026-07-15 | 1.0 | DialogMesh alignment docs |
