# Business Chain 01: Unified Intent & Association (统一意图解析)

> v2.0 | 2026-07-21 | 合并 BUSINESS_CHAIN_01_INTENT + BUSINESS_CHAIN_06_ASSOCIATION

---

## Unified Pipeline

```mermaid
graph TD
    Q["user input"] --> STRUCT["Tier 0: StructuralFeatures<br/>word_count / has_question / imperative / entity_count / verb_count / repetition"]
    
    STRUCT -->|"conf >= 0.6"| L1["Layer 1: Syntactic<br/>entities + verbs → co-occurrence pairs"]
    STRUCT -->|"conf < 0.6"| TIER1["Tier 1: BGE/SVO<br/>SVO triples + behavior vector cosine"]

    TIER1 -->|"conf >= 0.6"| L2["Layer 2: Semantic<br/>entity types → type-compatible relations"]
    TIER1 -->|"conf < 0.6"| TIER2["Tier 2: LLM few-shot<br/>local nemotron 50ms → remote DeepSeek 1500ms"]

    L1 --> L2
    TIER2 --> L2
    TIER2 -->|"also calibrate"| STRUCT

    L2 --> L3["Layer 3: Pragmatic<br/>behavior_label from entity+verb+expectation"]
    L3 --> L4["Layer 4: Temporal<br/>history_path → Markov transition"]
    L4 --> L5["Layer 5: Causal<br/>if-then → counterfactual → closure"]

    L3 --> RESULT["UnifiedResult<br/>expectation + behavior_label + entities + associations + causal"]
    L4 --> RESULT
    L5 --> RESULT
```

---

## Speed Hierarchy

| Tier | Method | Latency | Output |
|:---:|--------|:-------:|--------|
| 0 | StructuralFeatures (grammar) | 0.1ms | expectation hint, entity_count, verb_count |
| 1 | BGE/SVO (semantic) | 1-5ms | behavior_label, entity_types, cosine_topk |
| 2 | LLM few-shot (local→remote) | 50-1500ms | full UnifiedResult + calibrate T0/T1 |

**Weighted avg**: 85% T0-only (0.1ms) + 10% T1 (3ms) + 5% T2 (200ms) = ~11ms avg.

---

## Data Flow: One Parse, Five Layers

```mermaid
sequenceDiagram
    participant T0 as Tier 0 (0.1ms)
    participant T1 as Tier 1 (3ms)
    participant T2 as Tier 2 (200ms)
    participant L1 as Layer 1
    participant L3 as Layer 3
    participant L5 as Layer 5

    Note over T0: extract(text) → StructuralFeatures
    T0->>L1: entity_count, verb_count, entities[]
    L1->>L1: co-occurrence pairs

    alt conf < 0.6
        T0->>T1: fall through
        T1->>L1: SVO triples + entity_types
        alt conf < 0.6
            T1->>T2: fall through
            T2->>L3: behavior_label, associations
            T2-->>T0: calibrate expectation
        end
    end

    L1->>L3: entities + co-occurrence
    L3->>L5: behavior_label + history
    L5->>L5: causal closure

    L1-->>Result: UnifiedResult
    L3-->>Result: UnifiedResult
    L5-->>Result: UnifiedResult
```

---

## Calibration Loop

```mermaid
graph LR
    T0["Tier 0: expectation='TOOL'"] --> T1["Tier 1: entities wrong?"]
    T1 --> T2["Tier 2 LLM: corrects expectation='ADVISOR' + updates entity_types"]
    T2 -.->|"back-propagate"| T0
    T2 -.->|"update"| T1
```

When Tier 2 LLM fires, it returns:
1. `corrected_expectation` → updates Tier 0 EMA bias
2. `entity_types` → updates Tier 1 entity classifier
3. `behavior_label` → Layer 3

This closes the loop: future inputs get better Tier 0/1 results from past LLM corrections.

---

## Engine Integration

```python
# engine.on_event() — replaces old IntentParser block

if self._unified_parser and text:
    unified = self._unified_parser.parse(
        text=text,
        history=recent_history,
        pcr_output=pcr_output,
    )
    # unified.expectation → system_instruction
    # unified.behavior_label → Layer 3 → context injection
    # unified.entities → ContextAssembler entity boost
    # unified.associations → Association chain push
    # unified.causal_closure → if present, inject into LLM reasoning
```

---

## Comparison: Before vs After

| Dimension | Before (v1) | After (v2 Unified) |
|-----------|------------|-------------------|
| Modules | IntentParser + Association separate | One pipeline |
| Parse count | 2 independent | 1 shared |
| Keyword dependency | Yes (硬编码词表) | No (grammar structure) |
| LLM usage | Never triggers (conf too high) | Triggers at conf < 0.6 |
| Calibration | None | T2 → T0 back-propagation |
| Layers 4-5 | Not implemented | Connected through shared entities |
| Avg latency | 0.1ms (rule only, imprecise) | 11ms (85% rule, 15% LLM) |

---

## Implementation Status

```
✅ v5/DESIGN_UNIFIED_INTENT_ASSOCIATION.md     — design spec
✅ StructuralClassifier                        — Tier 0 (14/14 PASS)
✅ PCR LLM fallback                            — Tier 2 ready (conf < 0.6)
⚠️ Tier 1 BGE/SVO                             — code exists, not wired
❌ Unified pipeline                            — not yet integrated
❌ Association Layers 1-5                      — not connected to StructFeatures
❌ Calibration loop                            — not implemented
```
