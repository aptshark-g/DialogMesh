# MemoryGraph API Reference

> Core API documentation for the Discourse Block Tree system.  
> All classes are organized by pipeline stage and management layer.

---

## Table of Contents

1. [DiscoursePipeline](#discoursepipeline)
2. [HeaderInjector](#headerinjector)
3. [SyntacticDecomposer](#syntacticdecomposer)
4. [MacroMicroQuantizer](#macromicroquantizer)
5. [Segmenter](#segmenter)
6. [DiscourseBlockTreeManager](#discourseblocktreemanager)
7. [SummaryEngine](#summaryengine)
8. [ContextBuilder](#contextbuilder)

---

## DiscoursePipeline

**Module:** `core.agent.discourse_integration`

**Purpose:** Full-pipeline wrapper that orchestrates the three compiler stages, the Segmenter, the Manager, the SummaryEngine, and the ContextBuilder into a single `process_turn()` call.

### Constructor

```python
DiscoursePipeline(
    session_id: str = "default",
    hot_turns: int = 5,
    enabled: bool = True,
    strategy: Optional[Dict[str, str]] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `str` | `"default"` | Session identifier for entity-cache isolation. |
| `hot_turns` | `int` | `5` | Number of recent turns considered "hot" (ACTIVE). |
| `enabled` | `bool` | `True` | Master switch; when `False` the pipeline returns an empty string. |
| `strategy` | `Dict[str, str]` | `None` | Custom strategy overrides. Keys: `segmenter`, `summary_engine`, `header_injector`. Values are registered strategy names via `PluginRegistry`. |

### Key Methods

#### `process_turn(raw_query, session_history=None, turn_index=0) -> str`

Process a single turn and return the assembled context string.

| Parameter | Type | Description |
|-----------|------|-------------|
| `raw_query` | `str` | Raw user input. |
| `session_history` | `List[Dict]` | List of `{"role": "user"\|"assistant", "content": str}` dicts. |
| `turn_index` | `int` | Monotonically increasing turn index. |

**Returns:** `str` — context assembled from Hot/Warm/Cold blocks, or empty string if disabled.

**Internal Flow:**
1. `HeaderInjector.inject()` → resolves implicit entities.
2. `SyntacticDecomposer.decompose()` → splits into `ParsedClause`s.
3. Convert clauses to `EDU` instances.
4. `MacroMicroQuantizer.quantize()` → fills `micro_dimensions` + `macro_dimensions`.
5. `DiscourseBlockTreeManager.ingest_turn()` → segment & route blocks.
6. `SummaryEngine.summarize_block()` → generate v1/v2/v3 summaries.
7. `ContextBuilder.build_context()` → tiered assembly.

**Metrics:** On success, increments `discourse_pipeline_requests_total`, `discourse_edu_processed_total`, `discourse_blocks_total`, and records latency into `discourse_pipeline_latency_seconds`.

#### `reset()`

Reset all internal state (blocks, caches). Use this when starting a new conversation.

#### `preload(blocking=False) -> bool`

Pre-load BGE encoder, jieba dictionary, and optional NER pipeline to eliminate cold-start latency.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `blocking` | `bool` | `False` | If `True`, blocks until all loaders finish. |

**Returns:** `True` if pre-loading started successfully.

#### `get_metrics() -> Optional[Dict]`

Return a snapshot of DiscourseBlockTree metrics (counters, gauges, histograms).

#### `get_metrics_prometheus() -> str`

Return metrics in Prometheus text exposition format.

### Usage Example

```python
from core.agent.discourse_integration import DiscoursePipeline

dp = DiscoursePipeline(session_id="sess-001", hot_turns=5)
dp.preload(blocking=True)

ctx = dp.process_turn("How does list comprehension work?", turn_index=0)
print(ctx)
```

---

## HeaderInjector

**Module:** `core.agent.compiler.header_injector`

**Purpose:** Stage 1 of the compiler. Analogous to a C preprocessor `#include <context.h>` — injects implicit entities (pronoun resolution, omitted objects) by drawing from the session entity cache, the topic-tree summary, and a domain knowledge base.

### Constructor

```python
HeaderInjector(
    context_window_size: int = 5,
    kb_path: Optional[str] = None,
    domain: str = "default",
    use_semantic_parser: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `context_window_size` | `int` | `5` | Number of recent turns to keep in the entity cache. |
| `kb_path` | `Optional[str]` | `None` | Path to a JSON/YAML knowledge base. Defaults to `~/.memorygraph/kb/header_kb.json`. |
| `domain` | `str` | `"default"` | Domain key inside the KB dictionary. |
| `use_semantic_parser` | `bool` | `True` | Whether to use the open-domain `SemanticParser` for entity extraction and coreference chains. |

### Key Methods

#### `inject(raw_text, session_id, session_history=None, turn_index=0) -> InjectionResult`

Resolve pronouns and omitted objects in the input text.

| Parameter | Type | Description |
|-----------|------|-------------|
| `raw_text` | `str` | Raw user message. |
| `session_id` | `str` | Session ID for cache isolation. |
| `session_history` | `List[Dict]` | Conversation history (optional). |
| `turn_index` | `int` | Current turn index. |

**Returns:** `InjectionResult` dataclass with fields:
- `text: str` — the resolved/augmented text.
- `replacements: List[Tuple[str, str, EntityCandidate]]` — list of `(original, replacement, candidate)` tuples.
- `unresolved_pronouns: List[str]` — pronouns that could not be resolved.

**Resolution Priority:**
1. Coreference chains (SemanticParser)
2. Same-turn explicit reference
3. Context nearest entity
4. Causal KB inference
5. Session history entity pool
6. Semantic similarity (BGE encoder)

#### `reset_session(session_id: str)`

Clear all per-session caches (entity cache, last entity, turn cache, coreference chains).

### Usage Example

```python
from core.agent.compiler.header_injector import HeaderInjector

hi = HeaderInjector()
result = hi.inject("How does it work?", session_id="s1", session_history=[
    {"role": "user", "content": "I love Python."}
])
# result.text may become "How does Python work?"
```

---

## SyntacticDecomposer

**Module:** `core.agent.compiler.syntactic_decomposer`

**Purpose:** Stage 2 of the compiler. Splits natural-language input into clauses (EDU candidates) and extracts Subject-Predicate-Object skeletons plus modifiers.

### Constructor

```python
SyntacticDecomposer(
    enable_hybrid_path: bool = True,
    use_semantic_parser: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_hybrid_path` | `bool` | `True` | If the input is too complex (too many clauses, ambiguous conjunctions, or long clauses without entities), return a single `ParsedClause` with `parse_failed=True` instead of crashing. |
| `use_semantic_parser` | `bool` | `True` | Use `SemanticParser` for open-domain entity recognition and relation extraction. |

### Key Methods

#### `decompose(text: str) -> List[ParsedClause]`

Segment text and extract syntax.

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Raw (possibly post-injection) user input. |

**Returns:** `List[ParsedClause]` — each clause contains:
- `raw_text: str`
- `subject`, `predicate`, `object: Optional[str]`
- `subject_attrs`, `object_attrs: List[str]` (modifiers such as `NEG`, `safe`, `unsafe`)
- `negation: bool`, `uncertainty: bool`, `imperative: bool`, `question: bool`
- `raw_entities: List[str]`
- `parse_failed: bool`, `parse_failed_reason: str`

**Fallback logic:** If `SemanticParser` fails or is unavailable, the decomposer falls back to regex-based entity extraction and dictionary-based predicate detection.

### Usage Example

```python
from core.agent.compiler.syntactic_decomposer import SyntacticDecomposer

sd = SyntacticDecomposer()
clauses = sd.decompose("Python is great and I want to learn it.")
for c in clauses:
    print(f"S={c.subject}, P={c.predicate}, O={c.object}")
```

---

## MacroMicroQuantizer

**Module:** `core.agent.compiler.macro_micro_quantizer`

**Purpose:** Stage 3 of the compiler. Computes 9-dimensional cohesion scores for every EDU and every adjacent EDU pair, producing `MicroDimensions` and `MacroDimensions`.

### Constructor

```python
MacroMicroQuantizer(
    embedding_model_name: Optional[str] = None,
    macro_weight: float = 0.6,
    micro_weight: float = 0.4,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding_model_name` | `Optional[str]` | `None` | HuggingFace model ID for the encoder. `None` triggers auto-loading from config (`models/BAAI/bge-small-zh`). |
| `macro_weight` | `float` | `0.6` | Weight of macro dimensions in the fused cohesion score. |
| `micro_weight` | `float` | `0.4` | Weight of micro dimensions in the fused cohesion score. |

### Key Methods

#### `quantize(edus: List[EDU]) -> List[EDU]`

Fill `micro_dimensions` and `macro_dimensions` for every EDU in the list.

| Parameter | Type | Description |
|-----------|------|-------------|
| `edus` | `List[EDU]` | EDUs produced by Stage 2. |

**Returns:** the same list, mutated in-place with dimensions and embeddings.

**Dimension Definitions:**

| Dimension | Symbol | Weight | Description |
|-----------|--------|--------|-------------|
| Semantic similarity | M1 | 0.35 | Cosine similarity of EDU embeddings. |
| Intent consistency | M2 | 0.25 | `1.0` if intent labels match, else `0.0`. |
| Entity overlap | M3 | 0.20 | Jaccard similarity of entity sets. |
| Temporal coherence | M4 | 0.20 | Exponential decay by turn distance. |
| Entity density | μ1 | 0.30 | Normalized entity count. |
| Causal chain | μ2 | 0.25 | Presence of causal markers (因为/所以/if/then). |
| Reference resolution | μ3 | 0.20 | Pronoun/omission density. |
| Tense coherence | μ4 | 0.15 | Temporal adverb density. |
| Voice alignment | μ5 | 0.10 | Active/passive marker density. |

#### `compute_inter_edu_cohesion(edu_i, edu_j) -> float`

Compute the fused cohesion between two adjacent EDUs.

**Formula:** `λ × MacroComposite + (1-λ) × MicroComposite`

#### `compute_block_cohesion(block_edus) -> float`

Average cohesion inside a single block (for diagnostics).

### Usage Example

```python
from core.agent.compiler.macro_micro_quantizer import MacroMicroQuantizer
from core.agent.discourse_block_tree.models import EDU

mmq = MacroMicroQuantizer()
edus = [EDU(id="e1", turn_index=0, edu_index=0, raw_text="Hello world")]
mmq.quantize(edus)
print(edus[0].macro_dimensions)
```

---

## Segmenter

**Module:** `core.agent.discourse_block_tree.segmenter`

**Purpose:** Boundary detector and clusterer. Consumes quantized EDUs and emits `DiscourseBlock`s based on cohesion cliffs and BDI (Burst Drift of Intent) detection.

### Constructor

```python
Segmenter(
    threshold: float = 0.5,
    macro_weight: float = 0.6,
    micro_weight: float = 0.4,
    bdi_enabled: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `threshold` | `float` | `0.5` | Fused cohesion below this value triggers a block boundary. |
| `macro_weight` | `float` | `0.6` | Same as quantizer; used for recomputing cohesion if dimensions are missing. |
| `micro_weight` | `float` | `0.4` | Same as quantizer. |
| `bdi_enabled` | `bool` | `True` | Enable Burst Drift of Intent detection (intent-label mismatch → forced boundary). |

### Key Methods

#### `segment(edus: List[EDU]) -> List[DiscourseBlock]`

Mark boundaries and cluster EDUs into blocks.

| Parameter | Type | Description |
|-----------|------|-------------|
| `edus` | `List[EDU]` | Quantized EDUs (must have `macro_dimensions` and `micro_dimensions`). |

**Returns:** `List[DiscourseBlock]` — new blocks for this turn.

**Boundary Rules:**
1. The first EDU is always a boundary (block start).
2. If `bdi_enabled` and adjacent EDUs have different intent labels (excluding generic `statement`/`meta`) → BDI boundary.
3. If fused cohesion `< threshold` → cohesion-cliff boundary.
4. All non-boundary EDUs between two boundaries are clustered into one block.

#### `compute_block_boundary_cohesion(block_a, block_b) -> float`

Compute inter-block cohesion used by the Manager for merge decisions.

**Fusion:** `0.40 × embedding_cosine + 0.35 × intent_match + 0.25 × entity_jaccard`

### Usage Example

```python
from core.agent.discourse_block_tree.segmenter import Segmenter

seg = Segmenter(threshold=0.5)
blocks = seg.segment(edus)
print(f"Created {len(blocks)} blocks")
```

---

## DiscourseBlockTreeManager

**Module:** `core.agent.discourse_block_tree.manager`

**Purpose:** Lifecycle manager for blocks. Ingests new blocks, routes them into the tree (merge vs. append), and updates `ACTIVE → COOLING → COLD` states based on turn distance.

### Constructor

```python
DiscourseBlockTreeManager(
    segmenter: Optional[Segmenter] = None,
    hot_turns: int = 5,
    warm_turns: int = 10,
    enabled: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `segmenter` | `Optional[Segmenter]` | `None` | Segmenter instance used for inter-block cohesion computation. If `None`, a default `Segmenter()` is created. |
| `hot_turns` | `int` | `5` | Turns within this distance are `ACTIVE`. |
| `warm_turns` | `int` | `10` | Turns within this distance (but > hot_turns) are `COOLING`. |
| `enabled` | `bool` | `True` | When `False`, ingest falls back to turn-level blocks (one block per turn). |

### Key Methods

#### `ingest_turn(edus: List[EDU]) -> List[DiscourseBlock]`

Ingest a new turn's EDUs, segment, route, and update states.

| Parameter | Type | Description |
|-----------|------|-------------|
| `edus` | `List[EDU]` | EDUs from the current turn. |

**Returns:** `List[DiscourseBlock]` — the blocks that were created or updated.

**Routing Logic:**
1. Segment EDUs into new blocks.
2. For each new block, compute cohesion with the current active block.
3. If cohesion `≥ merge_threshold` (default 0.55) → merge into active block.
4. Otherwise → append as a new block.
5. Update lifecycle states for all existing blocks.

#### `get_blocks(state=None) -> List[DiscourseBlock]`

Return all blocks, optionally filtered by `BlockState`.

#### `get_hot_blocks() / get_warm_blocks() / get_cold_blocks()`

Convenience wrappers for `get_blocks(BlockState.ACTIVE)` etc.

#### `get_block_by_id(block_id) -> Optional[DiscourseBlock]`

Lookup by block ID.

#### `get_latest_block() / get_active_block()`

Return the most recent block or the currently active (merge-target) block.

#### `reset()`

Clear all blocks and indices.

### Usage Example

```python
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
from core.agent.discourse_block_tree.segmenter import Segmenter

mgr = DiscourseBlockTreeManager(segmenter=Segmenter(), hot_turns=5)
new_blocks = mgr.ingest_turn(edus)
print(f"Total blocks: {mgr.block_count}")
```

---

## SummaryEngine

**Module:** `core.agent.discourse_block_tree.summary_engine`

**Purpose:** Progressive summarizer. Produces v1 (single-turn), v2 (intra-block), and v3 (evolutionary) summaries for each block.

### Constructor

```python
SummaryEngine(v3_trigger_turn_count: int = 5)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `v3_trigger_turn_count` | `int` | `5` | Minimum `turn_count` inside a block before v3 summary is triggered. |

### Key Methods

#### `summarize_block(block: DiscourseBlock) -> ProgressiveSummary`

Generate or update summaries for a block. Only fills missing levels; does not recompute existing v1/v2 unless explicitly invalidated.

| Parameter | Type | Description |
|-----------|------|-------------|
| `block` | `DiscourseBlock` | The block to summarize. |

**Returns:** `ProgressiveSummary` attached to `block.summary`.

**Summary Levels:**

| Level | Trigger | Content | Latency |
|-------|---------|---------|---------|
| v1 | Always | One-line per EDU: `[NOT]Subject Predicate [NOT]Object` | < 1 ms |
| v2 | Always | Block-level: dominant intent + top-3 entities + action sequence | < 2 ms |
| v3 | `turn_count > v3_trigger_turn_count` | Evolutionary: topic + core behavior + conclusion | < 1 ms (rule-based) |

#### `update_v1(block: DiscourseBlock) -> str`

Force-regenerate v1 after new EDUs are appended, and invalidate v2/v3 so they will be regenerated on the next call.

### Usage Example

```python
from core.agent.discourse_block_tree.summary_engine import SummaryEngine

se = SummaryEngine(v3_trigger_turn_count=5)
for block in blocks:
    se.summarize_block(block)
    print(block.summary.latest)
```

---

## ContextBuilder

**Module:** `core.agent.discourse_block_tree.context_builder`

**Purpose:** Assembles the final context string fed to the LLM by selecting the appropriate summary level for each block based on its lifecycle state.

### Constructor

```python
ContextBuilder(hot_turns: int = 5)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hot_turns` | `int` | `5` | Turn distance threshold for "hot" blocks. Warm = `hot_turns*2`, Cold = everything else. |

### Key Methods

#### `build_context(blocks, current_turn, max_tokens=None) -> str`

Assemble a plain-text context string.

| Parameter | Type | Description |
|-----------|------|-------------|
| `blocks` | `List[DiscourseBlock]` | All blocks (usually from `manager.get_blocks()`). |
| `current_turn` | `int` | Current turn index (used to compute turn distance). |
| `max_tokens` | `Optional[int]` | Token budget (MVP: not yet enforced precisely). |

**Tier Rules:**

| Distance | Tier | Content |
|----------|------|---------|
| `≤ hot_turns` | Hot | Full text + v1 summary |
| `≤ hot_turns*2` | Warm | v2 summary (falls back to v1) |
| `> hot_turns*2` | Cold | v3 summary (falls back to v2, then "archived") |

**Returns:** `str` — newline-separated context segments, ordered by block creation time.

#### `build_structured_context(blocks, current_turn) -> List[Dict]`

Same logic as `build_context`, but returns a list of dicts for debugging or special rendering:
```python
{
    "state": "hot" | "warm" | "cold",
    "block_id": str,
    "full_text": str,   # only for hot
    "v1": Optional[str],
    "v2": Optional[str],
    "v3": Optional[str],
}
```

### Usage Example

```python
from core.agent.discourse_block_tree.context_builder import ContextBuilder

cb = ContextBuilder(hot_turns=5)
ctx = cb.build_context(mgr.get_blocks(), current_turn=7)
print(ctx)
```

---

## Data Models (Quick Reference)

### `EDU` — Elementary Discourse Unit

```python
@dataclass
class EDU:
    id: str                          # e.g. "edu:T3:U1"
    turn_index: int
    edu_index: int
    raw_text: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    embedding: Optional[List[float]] = None
    micro_dimensions: Optional[MicroDimensions] = None
    macro_dimensions: Optional[MacroDimensions] = None
    boundary_type: Optional[BoundaryType] = None
```

### `DiscourseBlock`

```python
@dataclass
class DiscourseBlock:
    id: str
    edus: List[EDU]
    start_turn: int
    end_turn: int
    state: BlockState = BlockState.ACTIVE
    summary: Optional[ProgressiveSummary] = None
    entities: List[Entity] = field(default_factory=list)
    entity_signature: str = ""
    macro_embedding: Optional[List[float]] = None
    intent_label: Optional[str] = None
    parent_id: Optional[str] = None
    node_id: Optional[str] = None
```

### `ProgressiveSummary`

```python
@dataclass
class ProgressiveSummary:
    v1: Optional[str] = None
    v2: Optional[str] = None
    v3: Optional[str] = None
    v3_trigger_reason: Optional[str] = None

    @property
    def latest -> Optional[str]: ...
    @property
    def latest_level -> int: ...
```

---

*See also:* `docs/api/CONFIGURATION.md` for the full configuration table, and `docs/api/ARCHITECTURE.md` for data-flow and state-machine diagrams.
