# DESIGN_SEMANTIC_WORLD_MODEL.md — Structural World Model

> Version: v1.1 | Date: 2026-07-12
>
> Not a code knowledge base — a unified Structural World Model.
> Source code / CAD / Unity Scene / DOM / DB Schema are just different views.
>
> Code Adapter is the first World Adapter, not the only one.

---

## 1. Positioning: Structural World IR, Not a Code Knowledge Base

### 1.1 Why Not Code Context Graph

Code is just the entry point. What we are really modeling is **any structured external object**.

| World | Input |
|:---|:---|
| Source Code | Class, Function, Variable, Module, Package |
| CAD | Part, Assembly, Constraint, Material |
| Unity | GameObject, Prefab, Scene, Component |
| DOM | Element, Style, Script, Event |
| Database | Table, Column, FK, Index, Query |

They all share the same structure: **a collection of objects with topological relationships, that can be referenced and located.**

### 1.2 Structural World IR

```
External World
       |
       v
World Adapter (Code / CAD / Unity / DB / ...)
       |
       v
StructureExtractor (ABC)
       |
 +-----+-----+-----+
 |     |     |     |
 v     v     v     v
Tree  AST   LSP   Custom
Sitter      (deep) (CAD/Unity...)
       |
       v
Structural World IR (unified graph format)
       |
       v
Context Compiler (reason + fuse -> local subgraph -> text -> LLM)
```

**Code Adapter is the first Adapter. Other worlds are reserved for extension.**

| **Dual-axis ranking** | BackboneScore (long-term importance) + ContextScore (current relevance) |
| **Progressive expansion** | Intent -> Community -> Reference Summary -> Reference Unit -> Raw Code |
| **Projection decoupling** | Same Reference Unit can be projected to different cognitive domains |
| **World as Observer** | World Model continuously emits World Observations |
| **LLM sees the world** | LLM never sees raw code directly; it sees the local engineering world structure |

---

## 2. Reference Unit: The Only Node Criterion

### 2.1 What Qualifies as a Node

There is only one rule: **anything that can be externally referenced is a Reference Unit, i.e., a node.**

| Is a Node | Is NOT a Node |
|:---|:---|
| File, Module, Package | if(){}, for(){}, while(){} |
| Class, Interface, Trait, Struct | Local temporary variables |
| Function, Method, Constructor | Comments, blank lines |
| Global Variable, Cross-file const | Magic numbers |
| Enum, Type Alias | inline lambda |

### 2.2 ReferenceUnit Schema

```python
@dataclass
class ReferenceUnit:
    unit_id: str                    # pkg::module::ClassName or file path
    unit_type: str                  # file | class | function | variable | module
    name: str                       # human-readable name
    world: str                      # code | cad | unity | dom | db
    language: str = ""              # python | rust | java | ...
    location: Location | None = None # file + line range
    attributes: dict = field(default_factory=dict)  # world-specific metadata
    backbone_score: float = 0.0     # backbone coloring score
    last_updated: float = 0.0
```

This schema is language-agnostic. Python class and Rust struct are both `unit_type="class"`.

---
## 3. Multi-Type Edges + Community Detection

### 3.1 Edge Type System

Relationships are not a single `depends_on`. Different edges carry different semantics and propagation weights:

| Edge Type | Semantics | Propagation Weight | Source |
|:---|:---|:---|:---|
| `imports` | A imports B | 0.30 | Static analysis |
| `calls` | A calls B | 0.25 | Static analysis + trace |
| `overrides` | A overrides B | 0.20 | Static analysis |
| `references` | A references B (non-call) | 0.15 | Static analysis |
| `co_changes` | A and B are frequently co-modified | 0.25 | Git history |
| `constrains` | A constrains B's behavior | 0.20 | Engineering chain / config |
| `tests` | A tests B | 0.10 | Test file mapping |
| `implements` | A implements interface B | 0.20 | Static analysis |
| `generates` | A generates B | 0.15 | Build artifacts |

### 3.2 Community Detection Replaces Git Clustering

The Git directory tree is only an initial Prior, not the final cluster. True module boundaries are determined by **community detection on multi-type edges**.

```python
class CommunityDetector:
    def detect(self, graph: StructuralWorldGraph) -> List[Community]:
        # Run Louvain / Leiden community detection on multi-edge weighted graph.
        # Edge weight fusion: Import*0.3 + Call*0.25 + CoChange*0.25 + Reference*0.15 + ...
        # Community boundary = module boundary
```

If `utils/logger.py` and `utils/cache.py` have no edges between them, they do not belong to the same community --- even though they are in the same directory.

### 3.3 Dynamic Index Anchors

After community detection, core nodes in each community (i.e., high StructuralImportance nodes) receive dynamic index anchors. Anchor sizes are managed via ParameterRegistry floating-point, adjusting with access frequency and freshness.

---
## 4. Backbone Coloring: StructuralImportance Multi-Dimensional Fusion (Strategy Pattern)

### 4.1 Backbone Is Not Most Accessed

Logger may be the most called, but it does not determine system topology. Backbone is about **information flow paths**. However, **we do not bind to a single algorithm** --- use the Strategy pattern, switchable via ParameterRegistry.

### 4.2 StructuralImportance Strategy

```python
class StructuralImportanceStrategy(ABC):
    # Strategy interface for computing node importance in a structural graph.
    @abstractmethod
    def compute(self, graph: StructuralWorldGraph) -> Dict[str, float]: ...

class BetweennessStrategy(StructuralImportanceStrategy):
    # Betweenness centrality: how many shortest paths pass through this node.
    def compute(self, graph): ...

class PageRankStrategy(StructuralImportanceStrategy):
    # PageRank: importance by incoming edge weight.
    def compute(self, graph): ...

class DegreeStrategy(StructuralImportanceStrategy):
    # Weighted degree: simple but fast.
    def compute(self, graph): ...

class HybridStrategy(StructuralImportanceStrategy):
    # Ensemble of multiple strategies, weighted by registry params.
    def compute(self, graph): ...
```

Strategy selection via ParameterRegistry:

| Param | Description | Default |
|:---|:---|:---|
| `world.importance.strategy` | Current strategy name | `betweenness` |
| `world.importance.strategies` | Available strategies | `[betweenness, pagerank, degree, hybrid]` |

**Default**: betweenness (accurate for small/medium projects). Later switch to Hybrid or auto-learn the best strategy for the project scale.

### 4.3 Multi-Dimensional Fusion (Strategy-Agnostic)

Regardless of which StructuralImportance strategy is used, the BackboneScore fuses four dimensions:

```
BackboneScore =
    0.30 x Structural Importance      # Graph topology importance (strategy output)
  + 0.30 x Runtime Centrality         # Bridge degree in traces
  + 0.20 x Commit Centrality          # Git co-change patterns
  + 0.20 x Retrieval Centrality       # Context Compiler access frequency
```

Each dimension is independently normalized before fusion. Adding a new observation source --- e.g., Test Coverage Centrality --- only requires adding one weighted layer, without changing the formula.

### 4.4 Backbone Coloring Effects

High BackboneScore node -> higher priority index anchor -> prioritized in ContextCompiler graph traversal -> subgraph is smaller and more precise.

All parameters in ParameterRegistry: `world.backbone.structural_weight`, `world.backbone.runtime_weight`, etc.

---
## 5. Three-Level Recall

### 5.1 LLM Should Never See Raw Code Directly

```
User Intent
     |
     v
Level 1: Intent -> Subgraph
    System cuts a local subgraph from World Model for the current intent (~300 nodes)
     |
     v
Level 2: Subgraph -> Reference Units
    Extract key Reference Units (Class/Function signatures + relationships) from 300 nodes
     |
     v
Level 3: Reference Units -> Raw Code
    Only expand source code content for the top 5-10 most relevant Units
```

### 5.2 Per-Level Token Budget

| Level | Content | Typical Tokens |
|:---|:---|:---|
| L1: Subgraph | Node names + edge relationships | ~500 |
| L2: Reference Units | Signatures + docstrings | ~300 |
| L3: Raw Code | Full source of a single function | ~200/function |

Total controlled under 2000 tokens --- LLM sees a local world, not a code dump.

---

## 6. World Adapter Architecture: StructureExtractor Abstraction + Plugin Grammar

### 6.1 WorldAdapter Interface (Unchanged)

```python
class WorldAdapter(ABC):
    @abstractmethod
    def extract_units(self, source) -> List[ReferenceUnit]: ...
    @abstractmethod
    def extract_edges(self, source) -> List[StructuralEdge]: ...
    @abstractmethod
    def resolve_reference(self, ref: str) -> Optional[ReferenceUnit]: ...
    @abstractmethod
    def get_raw_content(self, unit_id: str) -> Optional[str]: ...
```

### 6.2 StructureExtractor Abstraction (NEW --- replaces direct Tree-sitter binding)

WorldAdapter does not depend on Tree-sitter directly. It depends on the `StructureExtractor` abstract interface:

```python
class StructureExtractor(ABC):
    # Abstraction over grammar/parser backends.
    # Each world type (code/CAD/DOM) implements its own extractor.
    # For code worlds, TreeSitterExtractor is the default implementation.
    @abstractmethod
    def extract_units(self, source_path: str) -> List[ReferenceUnit]: ...
    @abstractmethod
    def extract_edges(self, source_path: str) -> List[StructuralEdge]: ...
    @abstractmethod
    def incremental_update(self, changed_file: str) -> List[str]: ...
```

Concrete implementations:

```
StructureExtractor (ABC)
    +-- TreeSitterExtractor    # Code worlds: tree-sitter syntax trees
    +-- ASTExtractor           # Fallback: stdlib AST
    +-- LSPExtractor           # Deep: LSP semantic analysis
    +-- RegexExtractor         # Lightweight: regex quick scan
    +-- CustomExtractor        # CAD/Unity/DOM: own implementations
```

### 6.3 Grammar Plugin-Based Loading

Grammars are not compiled into the main program. They are loaded on demand, per language:

```
extractors/
    python/
        grammar.so        # tree-sitter-python compiled artifact
    rust/
        grammar.so
    typescript/
        grammar.so
    ...
```

On first use, `load("python")` caches the Parser. Subsequent uses reuse it directly. Grammar updates do not affect core code.

### 6.4 CodeWorldAdapter Composes Extractors

```python
class CodeWorldAdapter(WorldAdapter):
    def __init__(self, languages: List[str] = None):
        self._languages = languages or ["python"]
        self._extractors: Dict[str, StructureExtractor] = {}
        for lang in self._languages:
            # Default: TreeSitterExtractor; switchable via config
            self._extractors[lang] = TreeSitterExtractor(lang)
```

### 6.5 Dual-Track Extraction: Reuses MultiTierPipeline

CodeWorldAdapter has three built-in precision tiers:

| Tier | Tool | Speed | Output |
|:---|:---|:---|:---|
| Tier 0 | Tree-sitter Query | ~500ms/1000 files | Quick Import/Call approximations |
| Tier 1 | Tree-sitter Full Traversal | ~5s/1000 files | All Reference Units + precise edges |
| Tier 2 | LSP / HoloGram / knot | minutes | Cross-file semantic relationships |

Fully isomorphic with MultiTierPipeline --- Tier 0 runs first to produce a Partial Model, then Tier 1+2 fill in the background.

### 6.6 Incremental Updates

```
git.commit Event -> CodeWorldAdapter.evict(file) -> re-extract -> merge into Structural Graph
```

Not a full rebuild. Only update changed files and their direct neighbor edges.

---

## 7. Schema Definitions

### 7.1 StructuralWorldGraph

```python
@dataclass
class StructuralWorldGraph:
    graph_id: str
    world: str                          # code | cad | ...
    units: Dict[str, ReferenceUnit]     # unit_id -> ReferenceUnit
    edges: List[StructuralEdge]         # multi-type edges
    communities: Dict[str, List[str]]   # community_id -> unit_ids
    backbone: Dict[str, float]          # unit_id -> backbone_score
    created_at: float
    last_extracted_at: float
```

### 7.2 StructuralEdge

```python
@dataclass
class StructuralEdge:
    edge_id: str
    edge_type: str                      # imports | calls | references | ...
    source_id: str                      # source ReferenceUnit ID
    target_id: str                      # target ReferenceUnit ID
    weight: float = 1.0                 # edge weight
    source: str = ""                    # static | trace | commit | test
    confidence: float = 1.0             # 0-1
```

### 7.3 Context Compiler Interface (Stub-Ready)

```python
class StructuralContextCompiler:
    def compile_subgraph(self, intent: str, world: str = "code",
                         max_nodes: int = 300) -> SubgraphResult:
        # Cut a local subgraph from World Model for the given intent.

@dataclass
class SubgraphResult:
    nodes: List[ReferenceUnit]
    edges: List[StructuralEdge]
    backbone_units: List[str]           # high-backbone nodes
    total_tokens_estimate: int
```

This interface does not care what is inside the World Model --- Code/CAD/Unity are all the same.

---
## 8. Integration Surface

| Module | Relationship |
|:---|:---|
| MultiTierPipeline | CodeWorldAdapter built-in three-tier precision extraction |
| Projector | `git.commit` -> engineering/memory domains (existing) |
| Context Compiler | World Model outputs subgraph -> fuse with other domains -> LLM context |
| Observation Compiler | Code events (new file/function) -> Observation |
| Hypothesis Engine | High-consensus Hypothesis on backbone nodes -> Knowledge |
| Skill Layer | Cross-project structural pattern distillation (plugin/middleware/repository) |
| ParameterRegistry | All weights, thresholds, anchor sizes, strategy selection |
| TierHeatBridge | High Backbone nodes = hot data -> elevate GC tier |
| Cognitive Scheduler | ExtractionTask -> Worker Pool async execution |

---

## 9. Implementation Plan

| Phase | Content | Dependencies |
|:---|:---|:---|
| Phase 1 | ReferenceUnit + StructuralEdge + StructuralWorldGraph Schema | None |
| Phase 2 | StructureExtractor(ABC) + TreeSitterExtractor + dual-track extraction (Tier 0+1) | Phase 1, tree-sitter |
| Phase 3 | Community Detection + StructuralImportance strategy coloring | Phase 2, networkx |
| Phase 4 | Subgraph compilation + ContextCompiler interface (Stub) | Phase 2-3 |
| Phase 5 | Incremental updates (git.commit -> re-extract) | Phase 2, EventBus |
| Phase 6 | ParameterRegistry integration (weights/thresholds/anchors/strategy) | ParameterRegistry |
| Phase 7 | LSP/HoloGram assisted extraction (Tier 2) | Phase 2 |

---

> Not a code knowledge base.
> It compresses the code world into a reasonable local engineering subgraph.
> Code is the first World. CAD, Unity, DB will all share the same interface.
>
> LLM never sees raw code --- it sees the structure of this local world.