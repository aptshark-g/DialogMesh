# MemoryGraph Architecture

> System architecture diagrams, data-flow pipelines, and state machines for the Discourse Block Tree.  
> All diagrams are rendered in Mermaid syntax and can be previewed in GitHub, VS Code, or any Mermaid-compatible viewer.

---

## 1. High-Level Data Flow

```mermaid
flowchart TD
    A[User Input] --> B[HeaderInjector<br/>Stage 1]
    B --> C[SyntacticDecomposer<br/>Stage 2]
    C --> D[MacroMicroQuantizer<br/>Stage 3]
    D --> E[EDU List]
    E --> F[Segmenter]
    F --> G[DiscourseBlockTreeManager]
    G --> H[SummaryEngine]
    H --> I[ContextBuilder]
    I --> J[LLM Input]

    style B fill:#e1f5fe
    style C fill:#e1f5fe
    style D fill:#e1f5fe
    style F fill:#fff3e0
    style G fill:#fff3e0
    style H fill:#fff3e0
    style I fill:#fff3e0
```

**Legend:**
- Blue = Compiler stages (stateless, deterministic)
- Orange = Discourse Block Tree management (stateful, lifecycle-aware)

---

## 2. Component Relationship Diagram

```mermaid
flowchart LR
    subgraph Compiler["Compiler (Stateless)"]
        HI[HeaderInjector]
        SD[SyntacticDecomposer]
        MM[MacroMicroQuantizer]
        SE[SemanticEncoder]
        SP[SemanticParser]
    end

    subgraph DBT["Discourse Block Tree (Stateful)"]
        SEG[Segmenter]
        MGR[DiscourseBlockTreeManager]
        SUM[SummaryEngine]
        CB[ContextBuilder]
        IDX[Indexer]
    end

    subgraph Config["Configuration"]
        CFG[DiscourseConfig]
        LOG[LoggingSetup]
    end

    subgraph External["External / Optional"]
        BGE[BGE Model]
        NER[NER Model]
        PROM[Prometheus]
    end

    HI --> SD
    SD --> MM
    MM --> SEG
    SEG --> MGR
    MGR --> SUM
    SUM --> CB
    MGR --> IDX

    SE -.-> MM
    SP -.-> HI
    SP -.-> SD

    BGE -.-> SE
    NER -.-> SP

    CFG -.-> HI
    CFG -.-> SD
    CFG -.-> MM
    CFG -.-> SEG
    CFG -.-> MGR
    CFG -.-> SUM
    CFG -.-> CB

    MGR -.-> PROM
    SUM -.-> PROM
```

**Key relationships:**
- `SemanticEncoder` and `SemanticParser` are shared utilities consumed by multiple compiler stages.
- `DiscourseConfig` is read by every major component; values are snapshotted at construction time.
- `Indexer` maintains four-dimensional indices (time, entity, intent, turn) over the block tree for fast queries.
- Prometheus metrics are emitted optionally; the system falls back to plain-text if `prometheus-client` is not installed.

---

## 3. Compiler Three-Stage Pipeline

```mermaid
flowchart TD
    subgraph Stage1["Stage 1: Header Injection"]
        S1A[Raw Input] --> S1B[Pronoun Resolution]
        S1B --> S1C[Object Omission Completion]
        S1C --> S1D[Entity Cache Update]
        S1D --> S1E[InjectionResult]
    end

    subgraph Stage2["Stage 2: Syntactic Decomposition"]
        S2A[InjectionResult.text] --> S2B[Clause Splitting]
        S2B --> S2C{Complex?}
        S2C -- Yes --> S2D[Hybrid Path<br/>parse_failed=True]
        S2C -- No --> S2E[Entity Extraction]
        S2E --> S2F[SVO Extraction]
        S2F --> S2G[Modifier Detection]
        S2G --> S2H[ParsedClause List]
    end

    subgraph Stage3["Stage 3: Macro-Micro Quantization"]
        S3A[ParsedClause → EDU] --> S3B[Batch Embedding]
        S3B --> S3C[MicroDimensions μ1-μ5]
        S3C --> S3D[MacroDimensions M1-M4]
        S3D --> S3E[Quantized EDU List]
    end

    S1E --> S2A
    S2H --> S3A
    S3E --> SEG[Segmenter]
```

**Stage 1 details:**
- Resolution priority: coreference chains > same-turn reference > context nearest > causal KB > history pool > semantic similarity.
- Maintains per-session entity cache and coreference-chain cache.

**Stage 2 details:**
- Clause splitting uses Chinese/English punctuation regex (`。！？；.!?;`).
- Complexity detection triggers when: >5 clauses, ≥2 ambiguous conjunctions, or a long clause without entities.
- SVO extraction uses `SemanticParser` first; falls back to regex + dictionary lookup.

**Stage 3 details:**
- Batch embedding: collects all uncached EDU texts, encodes them in one BGE forward pass, then populates the cache.
- Micro dimensions are computed per-EDU (intra-EDU density).
- Macro dimensions are computed per adjacent pair (inter-EDU cohesion).

---

## 4. DiscourseBlock Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> ACTIVE: first EDU ingested

    ACTIVE --> COOLING: turn_distance > hot_turns
    COOLING --> COLD: turn_distance > hot_turns + cooling_turns

    COLD --> ACTIVE: user returns to topic<br/>(new EDU appended to block)
    COLD --> MERGED: merged into parent block<br/>by manager

    COOLING --> ACTIVE: user returns to topic
    COOLING --> MERGED: merged into parent block

    ACTIVE --> MERGED: merged into parent block

    MERGED --> [*]

    note right of ACTIVE
        Hot blocks:
        - Full text + v1 summary
        - Visible in LLM context
    end note

    note right of COOLING
        Warm blocks:
        - v2 summary only
        - Compressed context
    end note

    note right of COLD
        Cold blocks:
        - v3 summary (if available)
        - Otherwise omitted
    end note
```

**State definitions:**

| State | Condition | Context Tier |
|-------|-----------|--------------|
| `ACTIVE` | `current_turn - end_turn ≤ hot_turns` | Hot (full text + v1) |
| `COOLING` | `hot_turns < distance ≤ hot_turns + cooling_turns` | Warm (v2) |
| `COLD` | `distance > hot_turns + cooling_turns` | Cold (v3 or omitted) |
| `MERGED` | Block was absorbed into a parent block | Removed from independent context |

**Transitions are triggered by:**
- `DiscourseBlockTreeManager._update_block_states()` — called on every `ingest_turn()`.
- Manager merge logic — when a new block's cohesion with the active block exceeds `merge_threshold`.

---

## 5. Segmenter Boundary Detection Logic

```mermaid
flowchart TD
    A[EDU_i] --> B[EDU_j]
    B --> C{BDI enabled?}
    C -- Yes --> D{Intent labels differ?<br/>and not generic?}
    D -- Yes --> E[BDI Boundary]
    D -- No --> F{Cohesion < threshold?}
    C -- No --> F
    F -- Yes --> G[Cohesion Cliff Boundary]
    F -- No --> H[No Boundary<br/>Same Block]

    E --> I[New Block]
    G --> I
    H --> J[Continue Block]
```

**Boundary priority:**
1. BDI (Burst Drift of Intent) — highest priority, forced split regardless of cohesion.
2. Cohesion Cliff — second priority, splits when the fused 9-dimensional score drops below `threshold`.
3. No boundary — EDU continues the current block.

---

## 6. Context Builder Assembly Logic

```mermaid
flowchart TD
    A[Get all blocks] --> B[Sort by start_turn]
    B --> C{For each block}
    C --> D{turn_distance ≤ hot_turns?}
    D -- Yes --> E[Format as Hot:<br/>full_text + v1]
    D -- No --> F{turn_distance ≤ hot_turns*2?}
    F -- Yes --> G[Format as Warm:<br/>v2 (fallback v1)]
    F -- No --> H[Format as Cold:<br/>v3 (fallback v2 → archived)]
    E --> I[Join with newlines]
    G --> I
    H --> I
    I --> J[Return context string]
```

---

## 7. Plugin System Architecture

```mermaid
flowchart TD
    A[DiscoursePipeline] --> B{strategy dict?}
    B -- Yes --> C[PluginRegistry.get_strategy]
    B -- No --> D[Default Class Constructor]
    C --> E[Custom Segmenter]
    C --> F[Custom SummaryEngine]
    C --> G[Custom HeaderInjector]
    D --> H[Default Segmenter]
    D --> I[Default SummaryEngine]
    D --> J[Default HeaderInjector]

    E --> K[Pipeline Execution]
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K
```

**PluginRegistry** is a global, module-level registry. It supports:
- `register_strategy(name, component_type, factory_func)`
- `get_strategy(component_type, name=None)` — returns default if name missing.
- `list_strategies()` — introspection for debugging.
- `unregister_strategy()` / `clear()` — for testing and hot-swapping.

---

## 8. Metrics Export Flow

```mermaid
flowchart LR
    A[DiscoursePipeline.process_turn] --> B{success?}
    B -- Yes --> C[inc_discourse_requests]
    B -- Yes --> D[observe_discourse_latency]
    B -- Yes --> E[inc_edu_processed]
    B -- Yes --> F[inc_total_blocks]
    B -- Yes --> G[set_active_blocks]
    B -- Yes --> H{v3 triggered?}
    H -- Yes --> I[inc_v3_triggered]
    B -- No --> J[record_error]

    C --> K[MetricsCollector]
    D --> K
    E --> K
    F --> K
    G --> K
    I --> K
    J --> K

    K --> L[to_prometheus]
    K --> M[discourse_summary]
    L --> N[/metrics endpoint or log]
    M --> O[In-memory snapshot]
```

**Prometheus text format fallback:**
If `prometheus-client` is not installed, `MetricsCollector.to_prometheus()` still produces a valid Prometheus exposition string (lines of `# TYPE ...` and `name value`). The only difference is that no `MetricFamily` objects or `CollectorRegistry` are used — the output is built with pure string concatenation.

---

## 9. Session / Persistence Overview (Future)

```mermaid
flowchart TD
    A[InteractiveAgent] --> B[SessionManager]
    B --> C[SQLiteStore]
    B --> D[GraphStore]
    C --> E[Message History]
    C --> F[Turn Metadata]
    D --> G[DiscourseBlock Nodes]
    D --> H[Entity Nodes]
    D --> I[Topic Tree Nodes]
    D --> J[Cohesion Edges]
```

*Note: Persistence layer is implemented in `core/agent/persistence/` but is outside the scope of the real-time DiscourseBlockTree pipeline. The pipeline can be run entirely in-memory without SQLite or graph stores.*
