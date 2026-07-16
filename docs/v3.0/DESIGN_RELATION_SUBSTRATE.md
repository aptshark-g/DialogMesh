# Relation Substrate — 统一关系基座

> 版本: v2.0 | 日期: 2026-07-16
> 状态: Draft
> 关联: DESIGN_SEMANTIC_OBJECT.md, DESIGN_PERSPECTIVE_PLANNER.md
> 变更: edge_type 拆为 relation_kind + semantic_strength; causal 从 type 提升为解释层; 增加 predicate/inverse

## 一、问题定义

### 1.1 当前架构：五张平行图

```
ConceptGraph (relations)     ← 语义边
BehaviorGraph               ← 用户操作序列（A→B→C）
CausalSubstrate              ← 因果推理（cold start，≥10 step 才触发）
KnowledgeSpace               ← 冻结事实（暂缓）
SemanticObject.composition   ← 纵向归属
```

五者各自独立建模。

### 1.2 核心错误

**CausalSubstrate 试图从行为序列直接推理因果。** 这等同于只从导航路径反推路网结构。

```
行为证据:   用户先问 A 再问 B           → 弱信号（巧合）
文档证据:   设计文档说 "A 导致 B"        → 强信号（显式）
代码证据:   B 的输入来自 A 的输出        → 强信号（数据流）
时序证据:   A 的变更总是引起 B 的更改    → 中信号（共变）
```

### 1.3 正确的模型

> **因果不是推理产物，是关系基座上多源证据融合后的解释层。**

```
所有关系证据（文档/代码/行为/时序/设计）
  → RelationSubstrate（统一存储 + 证据链）
  → relation_kind + semantic_strength + evidence
  → confidence 达到阈值 + mechanism 解释 → causal explanation
```

### 1.4 v1.0 设计的关键错误

v1.0 把 `edge_type` 作为单枚举：
```
association → semantic → dependency → causal
```

**这些不是同一维度的东西。** `behavioral` 描述的是观察来源，`dependency` 描述的是语义强度，`causal` 应该是解释层——不是 type。

## 二、RelationEdge 模型

### 2.1 核心定义

```python
@dataclass  
class RelationEdge:
    """世界中的一个关系。"""

    identity: str
    source: str                     # 源 SemanticObject identity
    target: str                     # 目标 SemanticObject identity

    # === 关系分类（正交的两个维度）===

    relation_kind: str              # 什么性质的关系
    # "structural"  | 结构性关系（contains, depends_on, implements）
    # "behavioral"  | 行为观察（用户在 A 之后访问 B）
    # "temporal"    | 时序共变（A 变更后 B 也变更）

    semantic_strength: str          # 关系的语义强度
    # "association"      | 仅相关（共现、同文档）
    # "reference"        | 引用关系
    # "dependency"       | 一方依赖另一方
    # "implementation"   | 实现关系

    # === 关系语义（RDF方向）===

    predicate: str                  # "depends_on" | "produces" | "calls" | "contains" | ...
    inverse: str                    # "depended_by" | "consumed_by" | "called_by" | ...
    direction: str                  # "directed" | "undirected" | "bidirectional"

    # === 置信度与证据 ===

    confidence: float               # [0, 1]，多证据融合后的综合评分
    evidence: List[Evidence]        # 多源证据链

    # === 因果解释层（仅当 confidence > 0.8 + 多来源 evidence 时存在）===

    mechanism: Optional[str]        # 因果机制解释
    # 例: "多域上下文竞争 → 需要动态域选择 → DomainSelector 依赖 IntentParser"

    # === 生命周期 ===

    created_at: float
    ttl: Optional[float]            # Time-to-live（behavioral 短，structural 长）
    decay_rate: float


@dataclass
class Evidence:
    """一条支持关系的证据。"""
    evidence_id: str
    source: str                     # "document" | "code" | "behavior" | "git"
    claim: str                      # 证据陈述
    confidence: float               # 证据本身可信度
    predicate: str                  # 证据声称的谓语
    extracted_at: float
    raw_ref: Optional[str]          # 原始引用
```

### 2.2 两个正交维度

```
relation_kind          semantic_strength
────────────────────────────────────────
structural             dependency        → "DomainSelector depends_on IntentParser"
structural             contains          → "Runtime contains Observation"
structural             implements        → "RedisLockAdapter implements DistributedLock"
behavioral             association       → "用户从 A 导航到 B"
temporal               association       → "A 变更后 B 也变更"

     ×                         ×
  (性质)                  (强度)
```

**relation_kind 回答 "这是什么性质的关系"，semantic_strength 回答 "这个关系有多强"。**

### 2.3 因果不是 type，是解释层

```
旧模型（v1.0）:
  causal 是 edge_type 枚举中的一个值
  因果和 association、dependency 并列

新模型:
  causal 是 edge 上的一个解释层
  edge.relation_kind = "structural"
  edge.semantic_strength = "dependency"
  edge.confidence > 0.8
  edge.evidence 来自 ≥2 个不同 source
  edge.mechanism != None          ← 这才是 causal

即:
  causal = high-confidence structural edge + mechanism explanation
```

一个 relation 可以升级到 causal 解释层，当：
- `confidence > 0.8`
- `evidence` 来自至少 2 个不同来源（document + code）
- `mechanism` 不为空（知道为什么 A 导致 B）

### 2.4 置信度融合

```
edge.confidence = f(evidence_list)

融合规则:
  - 多条独立证据 → 互补，置信度提升
  - 同源重复证据 → 冗余，不提升
  - 显式文档声明 > 代码依赖 > 行为序列 > LLM 推断
  - 每种 source 只取最高的一条 evidence

实现:
  confidence = 1 - ∏(1 - max_confidence_per_source)
  where max_confidence_per_source = max(e.confidence for e in evidence if e.source == s)
```

### 2.5 关系类型与 LOD 的对照

| LOD | 返回的 relation |
|-----|-----------------|
| 1.0 | 仅名称，不展开关系 |
| 2.0 | structural_kind + dependency/implementation 强度 |
| 3.0 | 全部 relation_kind + 所有强度 |
| 4.0 | + causal explanation (mechanism) |

## 三、和现有模块的映射

### 3.1 简化方案

```
旧模块                          新位置
────────────────────────────────────────────────────
ConceptGraph.relations          → RelationSubstrate
                                    (relation_kind="structural")
BehaviorGraph                   → 撤销
                                    (操作序列 → relation_kind="behavioral")
CausalSubstrate                 → 撤销
                                    (因果推理 → relation.mechanism 解释层)
CausalContextSource             → RelationContextSource (统一检索)
KnowledgeSpace (暂缓)          → RelationSubstrate.filter(confidence > 0.8)
SemanticObject.composition      → 保留（纵向归属，非横向关系）
```

### 3.2 不变的部分

| 模块 | 状态 |
|------|------|
| `SemanticObject` 模型 | 不变 — 关系查询通过 RelationSubstrate |
| `PerspectivePlanner` | 不变 — 新增 causal view 策略 |
| `ObjectRuntime` | 微调 — render 接受 relation_view 参数 |
| `ContentProvider` | 新增 `relation_query()` 方法 |

## 四、Relation Projection

### 4.1 SemanticObject 上的关系投影

```python
SemanticObject("DomainSelector")
├── projection_resolvers["design"]        = DesignResolver
├── projection_resolvers["code"]          = CodeResolver
├── projection_resolvers["knowledge"]     = KnowledgeResolver
├── projection_resolvers["causal"]        = CausalResolver       ← 新增
├── projection_resolvers["behavior"]      = BehaviorResolver     ← 新增
└── projection_resolvers["implementation"]= ImplementationResolver ← 新增
```

### 4.2 CausalResolver — 因果解释层

```python
class CausalResolver(ProjectionResolver):
    """因果投影：查询 high-confidence edges with mechanism."""
    name = "CausalResolver"

    def resolve(self, target, view, provider) -> str:
        edges = provider.relation_query(
            source=target.identity, min_confidence=0.75)

        # causal = high-confidence edges that HAVE a mechanism
        causal_edges = [e for e in edges if e.mechanism]

        if not causal_edges:
            # Fallback: show structural edges with highest confidence
            structural = [e for e in edges if e.relation_kind == "structural"]
            if structural:
                best = max(structural, key=lambda e: e.confidence)
                return (f"{target.name} {best.predicate} {best.target} "
                        f"(confidence={best.confidence:.1f}, "
                        f"no causal mechanism yet)")
            return ""

        edges_sorted = sorted(causal_edges, key=lambda e: e.confidence, reverse=True)
        parts = []
        for e in edges_sorted[:3]:
            parts.append(
                f"{target.name} {e.predicate} {e.target}\n"
                f"  mechanism: {e.mechanism}\n"
                f"  evidence: {len(e.evidence)} sources, confidence={e.confidence:.2f}"
            )
        return "\n".join(parts)


class BehaviorResolver(ProjectionResolver):
    """行为投影：behavioral edges + navigation patterns."""
    name = "BehaviorResolver"

    def resolve(self, target, view, provider) -> str:
        edges = provider.relation_query(
            source=target.identity,
            relation_kind="behavioral",
            min_confidence=0.15)

        if not edges:
            return ""

        # Aggregate: what comes before/after this concept
        after = [e.target for e in edges if e.predicate == "navigated_from"]
        before = [e.source for e in edges if e.predicate == "navigated_to"]

        parts = []
        if before:
            parts.append(f"User often navigates to {target.name} after: {', '.join(before[:3])}")
        if after:
            parts.append(f"User often continues to: {', '.join(after[:3])}")
        return " | ".join(parts)
```

### 4.3 Perspective 对应的关系视图

| Perspective.strategy | 默认 relation_kind 过滤 | 说明 |
|----------------------|------------------------|------|
| architecture | structural | 结构关系（contains, depends_on） |
| execution | structural + behavioral | 结构 + 行为路径 |
| engineering | structural (implementation) | 代码实现关系 |
| evolution | structural (with mechanism) | 因果解释层 |

## 五、RelationSubstrate 构建

### 5.1 初始化来源

```
Phase 1 (Phase A):
  ConceptGraph relations → RelationSubstrate
    (relation_kind="structural", predicate from edge type)
  heading hierarchy → structural / contains edges
  co-occurrence → structural / association (low confidence)

Phase 2:
  Document evidence → semantic strength upgrade
    (显式 "A 依赖于 B" → dependency 升级)

Phase 3:
  Behavior evidence → behavioral edges (low confidence)
    (ConversationTracker 操作序列)

Phase 4 (预留):
  Code evidence → structural / implementation edges
  Git evidence → temporal edges

Phase 5 (预留):
  Multi-source upgrade:
    ≥2 来源 evidence + confidence > 0.8
    → mechanism 生成 (LLM 推断 why)
    → causal explanation
```

### 5.2 置信度阈值

| 行为 | 阈值 |
|------|------|
| 创建 edge | confidence > 0.15 |
| semantic_strength 从 association → reference | confidence > 0.5, ≥2 evidence |
| semantic_strength → dependency | confidence > 0.7, ≥1 document/code evidence |
| 生成 causal mechanism | confidence > 0.8, ≥2 不同 source 的 evidence |

## 六、数据流

```
用户: "为什么需要 DomainSelector？"

1. PerspectivePlanner.plan(text)
   → strategy="evolution"
   → relation_view="causal"

2. SemanticObject.locate("DomainSelector")

3. ObjectRuntime.render(obj, LOD(2.0), perspective)
   → 激活 projection: design + causal
   → CausalResolver.resolve():
       edges = provider.relation_query(source="DomainSelector", min_confidence=0.75)
       causal = [e for e in edges if e.mechanism]
       → [
           RelationEdge(
             source="DomainSelector", target="MultiDomainCompetition",
             predicate="created_because", inverse="motivates",
             relation_kind="structural", semantic_strength="dependency",
             confidence=0.85,
             evidence=[doc_evidence, design_evidence],
             mechanism="多域上下文竞争 → 需要动态域选择 → DomainSelector 依赖 IntentParser"
           )
         ]

4. Context IR:
   [DESIGN] DomainSelector: "负责根据意图选择知识域"
   [CAUSAL] created_because: 多域上下文竞争
            mechanism: 多域上下文竞争 → 需要动态域选择 → DomainSelector 依赖 IntentParser
            evidence: 2 个来源, confidence=0.85
```

## 七、完整架构

```
                 PerspectivePlanner (决策)
                         |
                    ObjectRuntime (行为)
                         |
        ┌────────────────┼────────────────┐
        |                |                |
   Projection      Recursive Zoom   RelationSubstrate
   (多世界面)       (连续缩放)        (统一连接)
        |                |                |
   design/code       hierarchy         edges
   knowledge         LOD               evidence
   causal/behavior   scale             behavior
                         |
                  Context Compiler
                         |
                        LLM
```

SemanticObject + RelationSubstrate + Projection + RecursiveZoom = Semantic World Model。

## 八、实现路线

### Phase 1: RelationSubstrate 数据模型（~150行）

1. `compiler/relation_substrate.py`:
   - `RelationEdge` + `Evidence` 数据类
   - `RelationSubstrate` — add/query/filter
   - `_build_from_concept_graph()` — Phase 1 初始化

2. 只实现 `relation_kind="structural"`，`semantic_strength` 由 edge type 推导
3. 验证: relation_query("DomainSelector") 返回 ≥1 条 edge

### Phase 2: Behavior evidence（~80行）

1. `engine.on_event()` 记录 behavioral edges（低置信）
2. `relation_kind="behavioral"`, `semantic_strength="association"`

### Phase 3: Relation Ranking（~100行）

1. 置信度融合、衰减、冲突处理
2. `semantic_strength` 升级规则

### Phase 4: Causal explanation（预留）

1. ≥2 来源 evidence → mechanism 推断（LLM）
2. 废弃 CausalSubstrate

### Phase 5: Code + Git evidence（预留）
