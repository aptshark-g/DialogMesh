# 上下文编译与记忆设计

> **本文档合并自以下源头文档**（原文件保留于 `docs/v3.0/` 不删除）：
> - `DESIGN_CROSS_DOMAIN_CONTEXT.md` — 跨域上下文编译、域选择、预算分配、子图修剪
> - `DESIGN_SEMANTIC_WORLD_MODEL.md` — Structural World Model、ReferenceUnit、Backbone Coloring
> - `DESIGN_UNIFIED_PERSISTENCE.md` — UnifiedGraphStore、分层存储、水波检索
> - `DESIGN_ENGINEERING_CHAIN.md` — 七类节点、约束推理引擎
> - `DESIGN_ENGINEERING_ONTOLOGY.md` — 工程本体定义
> - `DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md` — 对话树持久化修正网关
> - `CONTEXT_COMPRESSION_DESIGN.md` — 多级压缩策略

---

## 1. 核心命题

> 源自 `DESIGN_CROSS_DOMAIN_CONTEXT.md` §1

DialogMesh 对 Prompt Engineering 的特化回答：**不是写更好的 prompt，而是构建更好的 Context**。

当前问题：对话树、行为图、因果链、工程链、用户画像各自正确运行，但它们产出的认知资产从不流入 LLM 的视野。LLM 在蒙眼状态下推理。

即使把所有域的信息都传给 LLM，如果它们是各自独立传递的孤立段落，LLM 仍然无法利用跨域关联。

Context Compiler 的任务：从事件流出发，识别当前意图，选择最相关的域组合，编译为一个带内部指针的统一信息网络，让 LLM 像系统的一部分一样思考。

---

## 2. Persistent Graph

> 源自 `DESIGN_V4_CONTEXT_ENGINEERING.md` §4.2 + `DESIGN_UNIFIED_PERSISTENCE.md`

### 2.1 Property Graph + Typed Edge

```
Node {
  id: UUID
  type: "topic" | "concept" | "action" | "constraint" | "entity"
  text: str
  embedding: vector(384)
  activation_count: int      # 电容模型
  importance_score: float    # Memory Compiler 计算
  source_events: [UUID]
}

Edge {
  id: UUID
  source: UUID
  target: UUID
  type: "depends" | "creates" | "updates" | "constrains" | "reason" | "corrects" | "extends"
  weight: float              # α/β/γ/δ 四因子
  activation_count: int
  confidence: float
  source_events: [UUID]
}
```

关键属性：Property Graph、Typed Edge、跨会话持久化、Patch Chain 存储。

### 2.2 Patch Chain

持久化的不是"当前最终状态"，而是：`Base State + Patch1 + Patch2 + Patch3 + ...`

Memory Compiler 在 Checkpoint 时 apply 所有 patch，生成新的 base state。每次追加 O(1)、可回放撤销审计、Merge 冲突延迟到 Checkpoint。

### 2.3 Memory Compiler

> 源自 `DESIGN_V4_CONTEXT_ENGINEERING.md` §4.3

```
process(checkpoint_events: [Event]) -> MergePlan

步骤:
1. 冲突检测：同节点的多个 patch 有没有矛盾
2. 冲突解决：
   - 确定性冲突 → 规则引擎
   - 模糊冲突 → 轻量 LLM 仲裁
   - 高置信度冲突 → 保留两个版本，标记分叉
3. 节点合并：embedding 去重
4. 边融合：同类型同方向加权合并
5. 重要性重算：activation_count + 结构位置 + 推理参与度
6. ColdIndexer 更新：低重要性下沉，回升策略
7. Summary 生成：L1 节点级 / L2 话题级
```

LLM 参与程度推荐 90% 规则 + 10% LLM（仅冲突仲裁、节点去重）。

---

## 3. Unified Graph Store

> 源自 `DESIGN_UNIFIED_PERSISTENCE.md`

### 3.1 通用节点表

存储层不知道节点类型，只提供通用行，类型信息作为字段：

```sql
graph_nodes {
  node_id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL,      -- topic_block / artifact / constraint / behavior / causal / profile
  domain TEXT NOT NULL,          -- T / E / B / K / P
  session_id TEXT,
  data JSON NOT NULL,            -- 节点数据，自由格式
  summary TEXT,                  -- L1 摘要（节点级，~2句）
  l2_summary TEXT,               -- L2 摘要（话题级，LLM 生成）
  activation_count INT DEFAULT 0,
  importance REAL DEFAULT 0.0,
  tier TEXT DEFAULT 'H',         -- H/W/C/A: Hot/Warm/Cold/Archive
  source_events TEXT,            -- JSON数组
  created_at TIMESTAMP,
  updated_at TIMESTAMP
}
```

### 3.2 分层存储（JVM GC 模型）

| 层 | 存储位置 | 保留内容 | 访问延迟 | 降级条件 |
|:---|:---|:---|:---|:---|
| H (Hot) | Python dict 内存 | 完整 data + summary + l2_summary | <1ms | activation_count 连续10轮=0 |
| W (Warm) | SQLite | 完整 data + summary + l2_summary | <10ms | importance < 0.3 且 activation < 5 |
| C (Cold) | SQLite + 压缩 | summary + l2_summary + 索引 | <50ms | importance < 0.1 |
| A (Archive) | 压缩 JSONL | 仅 node_id + l2_summary + source_events | <500ms | 永久不活跃 |

### 3.3 多粒度索引（RAG 大小块）

| 粒度 | 存储字段 | 用途 |
|:---|:---|:---|
| 全文 (Full) | data | 精确事实检索 |
| 摘要 (Coarse) | summary | 话题级浏览 |
| 极简 (Tiny) | l2_summary | 跨会话概览 |

检索策略：Coarse scan（summary 快速匹配）→ Full recall（候选集加载完整内容）。

### 3.4 水波检索扩展

```python
wave_from_node(anchor_id, max_depth=3,
               domain_filter=[E, B],    # 限定域
               tier_filter=[H, W],       # 只查热/温层
               granularity=coarse)       # 先用摘要快速扫描
```

### 3.5 强化检索模式

| 模式 | 说明 |
|:---|:---|
| 问题预生成 | 每个节点存入时自动生成 1-3 个潜在用户问题 |
| HyDE | 用 LLM 先展开用户查询为假设答案，再做语义检索 |
| 混合检索 | 语义 (0.7) + 关键词 BM25 (0.3) 双通路并行，合并去重重排序 |

### 3.6 各域映射

| 域 | 模型 | node_type | 存储内容 |
|:---|:---|:---|:---|
| T (对话树) | DiscourseBlock | topic_block | 话语文本+意图+实体 |
| E (工程链) | Artifact | artifact | 名称+类型+状态 |
| E (工程链) | KnowledgeNode | constraint/pattern/decision | 名称+描述+模板 |
| B (行为链) | BehaviorEdge | behavior_edge | 操作类型+上下文+置信度 |
| K (因果链) | CausalEdge | causal_edge | 因果对+骨架+置信度 |
| P (用户画像) | ProfileDimension | profile_dim | 维度名+值+置信度 |

---

## 4. Structural World Model

> 源自 `DESIGN_SEMANTIC_WORLD_MODEL.md`

### 4.1 定位：不是代码知识库

代码只是入口。真正建模的是**任何结构化的外部对象**。

| World | Input |
|:---|:---|
| Source Code | Class, Function, Variable, Module, Package |
| CAD | Part, Assembly, Constraint, Material |
| Unity | GameObject, Prefab, Scene, Component |
| DOM | Element, Style, Script, Event |
| Database | Table, Column, FK, Index, Query |

它们共享同一结构：一组有拓扑关系、可被引用和定位的对象。Code Adapter 是第一个 World Adapter，不是唯一一个。

### 4.2 ReferenceUnit：唯一的节点标准

规则：**任何能被外部引用的东西都是 Reference Unit，即节点。**

| 是节点 | 不是节点 |
|:---|:---|
| File, Module, Package | if(){}, for(){} |
| Class, Interface, Struct | 局部临时变量 |
| Function, Method | 注释、空行 |
| Global Variable | Magic numbers |

```python
@dataclass
class ReferenceUnit:
    unit_id: str                    # pkg::module::ClassName or file path
    unit_type: str                  # file | class | function | variable | module
    name: str                       # human-readable name
    world: str                      # code | cad | unity | dom | db
    language: str = ""              # python | rust | java | ...
    location: Location | None       # file + line range
    attributes: dict                # world-specific metadata
    backbone_score: float = 0.0     # backbone coloring score
```

### 4.3 多类型边

| Edge Type | 语义 | 传播权重 | 来源 |
|:---|:---|:---|:---|
| `imports` | A imports B | 0.30 | 静态分析 |
| `calls` | A calls B | 0.25 | 静态分析 + trace |
| `overrides` | A overrides B | 0.20 | 静态分析 |
| `references` | A references B | 0.15 | 静态分析 |
| `co_changes` | A 和 B 经常一起改 | 0.25 | Git history |
| `constrains` | A 约束 B | 0.20 | 工程链 / config |
| `tests` | A 测试 B | 0.10 | 测试文件映射 |
| `implements` | A 实现接口 B | 0.20 | 静态分析 |

### 4.4 Community Detection

Git 目录树只是初始 Prior。真正的模块边界由多类型边上的社区检测决定（Louvain/Leiden）。

如果 `utils/logger.py` 和 `utils/cache.py` 之间没有边，它们不属于同一社区——即使在同一目录。

### 4.5 Backbone Coloring：分层重要性管线

Backbone 不是"最常访问的"——是信息流路径。Pipeline 根据图大小自动选择策略：

| 图大小 | 策略 | 速度 | 质量 |
|:---|:---|:---|:---|
| <5000 nodes | Exact Betweenness | fast | 100% |
| 5000-20000 | K-Sampling (Brandes) | medium | ~95% |
| 20000-50000 | Community Chunk | slow | ~85% |
| >50000 | Exact Betweenness | very slow | 100% |

多维融合：

```
BackboneScore =
    0.30 × Structural Importance   # 图拓扑重要性
  + 0.30 × Runtime Centrality      # trace 中的桥接度
  + 0.20 × Commit Centrality       # Git co-change 模式
  + 0.20 × Retrieval Centrality    # Context Compiler 访问频率
```

### 4.6 三级召回

LLM 永远不直接看原始代码。

```
Level 1: Intent → Subgraph (~300 nodes, ~500 tokens)
Level 2: Subgraph → Reference Units (signatures + docstrings, ~300 tokens)
Level 3: Reference Units → Raw Code (top 5-10 most relevant, ~200 tokens/function)
```

总计控制在 2000 tokens 以内——LLM 看到的是局部世界，不是代码 dump。

### 4.7 World Adapter 架构

```
WorldAdapter (ABC)
  → StructureExtractor (ABC)
      ├── TreeSitterExtractor    # 代码世界：tree-sitter 语法树
      ├── ASTExtractor           # 回退：stdlib AST
      ├── LSPExtractor           # 深层：LSP 语义分析
      └── CustomExtractor        # CAD/Unity/DOM
```

双轨提取：Tier 0 (Tree-sitter Query, ~500ms/1000 files) → Tier 1 (Full Traversal, ~5s/1000 files) → Tier 2 (LSP, minutes)。

增量更新：`git.commit Event → CodeWorldAdapter.evict(file) → re-extract → merge`。不全量重建。

---

## 5. Engineering Chain

> 源自 `DESIGN_ENGINEERING_CHAIN.md` + `DESIGN_ENGINEERING_ONTOLOGY.md`

### 5.1 定位

工程链不记录历史——它回答：**如果系统发生变化，还有哪些地方必须跟着变化。**

| 链 | 回答的问题 | 边的语义 |
|:---|:---|:---|
| 对话树 | 当前在聊什么话题 | 承接/细化/切换 |
| 行为链 | 用户做了什么 | 时序/模式 |
| 因果链 | 为什么这个关联存在 | reason/corrects |
| **工程链** | **如果系统变化，什么必须跟着变** | **requires/improves/violates** |

### 5.2 七类节点

| 节点类型 | 定义 | 示例 |
|:---|:---|:---|
| Constraint | 必须满足的条件 | Every Provider must expose Metrics |
| Rule | 流程中的位置约束 | RateLimit must be placed before Auth |
| Pattern | 可复用架构模板 | Plugin Pattern: Interface+Factory+Registry+Lifecycle |
| AntiPattern | 禁止连接（负边） | Controller must NOT directly access Database |
| Decision | 架构决策记录 | Use Event Bus for module communication |
| QualityAttribute | 量化质量影响 | RateLimiter: Performance +0.4, Complexity +0.2 |
| Module | 实际系统组件 | Gateway: monitor_missing, translation_ok |

### 5.3 边类型

正边：`requires`, `depends_on`, `implements`, `improves`, `derived_from`
负边：`violates`（禁止连接）

### 5.4 约束推理引擎

核心查询接口（供 Context Compiler E 域使用）：

1. `get_constraints_for(module_type)` → 返回所有 applicable Constraints
2. `get_pattern_for(operation)` → 返回匹配的 Pattern
3. `get_impact(change)` → 评估变更对 QualityAttribute 的影响
4. `check_anti_patterns(proposed_connection)` → 检测是否违反 AntiPattern
5. `get_related_decisions(module)` → 查询影响该模块的历史架构决策

推理链示例（LLM 加 RateLimiter）：

```
Operation: add module RateLimiter(type=Middleware)
  → Constraint: Every Middleware must expose Metrics → add Metrics
  → Pattern: Middleware Pattern includes config, lifecycle → follow template
  → Rule: Middleware must be before Auth → place correctly
  → AntiPattern: Middleware cannot bypass Auth → do NOT skip
  → Quality: Performance +0.2, Observability +0.5 → show cost/benefit
```

### 5.5 Pattern Library 演化

预置模式：Plugin Pattern, Middleware Pattern, Service Pattern, Pipeline Pattern。

演化机制：用户连续 N 次以相同模式执行操作 → 自动蒸馏为 Pattern → Candidate → Verified → Core。

---

## 6. Context Compiler

> 源自 `DESIGN_CROSS_DOMAIN_CONTEXT.md` + `DESIGN_V4_CONTEXT_ENGINEERING.md` §4.4

### 6.1 设计原则

1. **单一源头，多域投影** — 从 Event Chain 出发，沿 Event ID 多跳扩展，自然覆盖所有相关域
2. **意图感知，非平均分配** — 不同意图需要不同的域组合
3. **带指针的子图，非独立段落** — 每条信息标注跨域关联（cross_ref 指针）
4. **预算约束下的信息选择** — 总预算 500 tokens，基于意图优先级分配
5. **LLM 是推理引擎，Context Compiler 是认知编译引擎**

### 6.2 编译流程

```
compile(query, persistent_graph, user_profile) -> ContextIR

步骤:
1. 话题定位 (TopicBoundaryDetector)
2. 子图裁剪：锚点出发 k 跳水波扩展
   - 沿 typed edge 按类型权重扩展
   - 沿 reason 边高优先级
   - 沿 depends 边次优先级
   - 相关性过滤 + 激活计数过滤
3. 信息选择：在 500 token 预算内最大化推理路径+约束+行为链+画像
4. Context IR 生成：结构化序列化
5. 验证：每个 token 是否必要，超预算降级到摘要模式
```

### 6.3 意图感知的域选择矩阵

| 意图类别 | 主域(60%) | 辅助域1(25%) | 辅助域2(15%) | 策略名 |
|:-----|:-----|:-----|:-----|:-----|
| task (工程操作) | E | B (相关操作) | P (操作偏好) | 深度聚焦 |
| query (信息查询) | C (相关话题) | E (相关模块) | P (知识水平) | 话题锚定 |
| correction (纠正) | B (之前操作) | E (受影响模块) | K (可能因果) | 因果回溯 |
| discussion (思路讨论) | P (认知风格) | C (相关对话) | E (相关模块) | 广度发散 |
| casual (闲聊) | C (话题结构) | P (兴趣偏好) | — | 轻量组织 |
| topic_switch | C (全话题树) | B (切换模式) | P (主题偏好) | 结构重建 |

域选择不是硬编码——用户画像中的修正历史可以覆盖。

### 6.4 预算分配模型

| 层 | 预算 | 内容 |
|:---|:-----|:-----|
| 必要层 | 200 tokens | 用户消息本身。不可裁剪 |
| 策略层 | 300 tokens | 跨域编译子图。意图感知分配 |
| 弹性层 | 200 tokens | 溢出预算。仅在子预算充足时使用 |

策略层分配：主域 60% (180t) → 辅助域1 25% (75t) → 辅助域2 15% (45t)。

Provider 自适应：

| Provider | 推荐默认预算 | 策略 |
|:---|:---|:---|
| DeepSeek | 800-1000 tokens | 慷慨 |
| OpenAI GPT-4 | 400-500 tokens | 标准 |
| 本地模型 (Ollama) | 1500+ tokens | 不受限 |

### 6.5 Context IR 序列化

`to_prompt()` 将结构化 IR 序列化为 LLM 可读的 prompt 字符串：

```
[System]
You are DialogMesh, a context-aware AI assistant.
[Context]
intent=task strategy=primary_deep
Domain Allocation
★ engineering: 180 tokens (60%)
• behavior: 75 tokens (25%)
◎ profile: 45 tokens (15%)
[ENGINEERING]
• MODULE [0.95] Gateway — status: monitor_missing (120t)
  ^ref: B.event_87 = 用户在前3轮连续调整此模块
[BEHAVIOR]
• ACTION [0.88] set_timeout(ModuleA, 5000) (45t)
  ^ref: E.ModuleA = 最近3轮中的2轮关联此模块
Total: 300 tokens used
```

cross_ref 是双向的。LLM 收到的是可导航的子图网络。

### 6.6 子图溢出修剪

当 Context IR tokens 超过预算时，四轮修剪：

1. **电容排序** — activation_count 排序，后 30% 为候选
2. **结构保护** — betweenness > 0.6 的节点从候选移除（跨域连接器）
3. **时序修复** — last_accessed < 3 轮的新节点从候选移除
4. **摘要压缩** — 对候选节点执行域特定压缩（L2 Summary / 只保留模块名+状态）

三维节点保留评分，权重按意图类别调整：

| 意图 | alpha(频率) | beta(时序) | gamma(结构) |
|:---|:---|:---|:---|
| task | 0.3 | 0.2 | 0.5 |
| discussion | 0.2 | 0.5 | 0.3 |
| correction | 0.5 | 0.3 | 0.2 |

### 6.7 话题切换时的结构重组（三步降落法）

1. **旧话题摘要压缩** — DiscourseBlock → L2 Summary（~50 tokens/话题），保留 cross_ref
2. **结构保活** — betweenness > 0.6 的连接器节点保持完整内容
3. **新话题展开** — 按默认策略展开 2-3 跳，检查预算

---

## 7. 对话树持久化适配器

> 源自 `DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md`

对话树是内存态的刚性结构（树），持久化层是灵活结构（图）。本模块定义"修正网关"——在持久化时做重分类 + 结构校验，确保从图加载回来的数据永远是已修正版本。

### 7.1 修正网关

```
内存态 DiscourseBlockTree (树)
  ↓ 持久化
修正网关:
  1. 重分类：检查每个 Block 的 type 是否与实际内容匹配
  2. 结构校验：parent/child 关系是否有环、是否断裂
  3. 边类型修正：follow_up/elaborate/switch_to 是否正确
  ↓
UnifiedGraphStore (图)
```

### 7.2 加载时反序列化

从图存储加载时，通过 `node_type` 字段反序列化为正确的模型类。修正网关确保加载的数据已通过校验。

---

## 8. 上下文压缩策略

> 源自 `CONTEXT_COMPRESSION_DESIGN.md`

### 8.1 Hot/Warm/Cold 三层

| 层 | 内容 | 压缩方式 |
|:---|:---|:---|
| Hot | 当前活跃块的完整文本 | 不压缩 |
| Warm | 近期块的 v2 摘要 | 结构化摘要（意图+实体+谓语） |
| Cold | 早期块的 v3 摘要 | LLM 生成的高阶压缩 |

### 8.2 渐进式压缩 v1→v2→v3

- **v1**：完整文本
- **v2**：结构化摘要 `[analyze] entities=Python, pandas actions=import → use`
- **v3**：LLM 高阶压缩（或规则降级：`Topic:Python | Intent:analyze | Conclusion: pending`）

### 8.3 已知问题

v3 规则生成质量远低于 LLM 压缩。信息熵过低。改进方案：
- 方案 A：v3 调用 LLM 做高阶压缩（+500ms 延迟）
- 方案 B：保持规则 v3，增加关键问答对和用户偏好标记

---

## 9. 实现状态

| 组件 | 文件 | 状态 |
|------|------|------|
| `ContextAssembler` | `context/assembler.py` (303行) | ✅ 多源聚合 + HybridIndex + noise 过滤 |
| `DomainSelector` | `context/domain_selector.py` | ✅ 意图感知域选择 |
| `BudgetAllocator` | `context/budget_allocator.py` | ✅ 三层预算分配 |
| `CrossDomainContextIR` | `context/cross_domain_ir.py` | ✅ 数据结构 + to_prompt() |
| `ContentIndex` | `compiler/content_index.py` | ✅ 统一检索入口（keyword + graph hybrid） |
| `SubgraphCompiler` | `compiler/subgraph_compiler.py` | ✅ 优先级水波扩展（reason > depends > co_occurs） |
| `SemanticIndex` | `compiler/semantic_path.py` | ✅ 7540 节点 DAG + 1695 概念绑定 |
| `ViewManager` | `compiler/view_manager.py` | ✅ 持久相机 + zoom_in/zoom_out/reframe |
| `PerspectivePlanner` | `compiler/perspective_planner.py` | ✅ intent → strategy → domain 三层决策 |
| `TopicContextSource` | `compiler/domain_adapters.py` | ✅ C 域：话题层级 + 历史关联 |
| `BehaviorContextSource` | `compiler/domain_adapters.py` | ✅ B 域：drill-down/switch 检测 |
| `IndexSource` | `compiler/index_source.py` | ✅ ContentIndex → ContextSource 适配 |
| `StructuralWorldGraph` | `world/schema.py` | ✅ Schema 定义 |
| `StructuralContextCompiler` | `world/compiler.py` | ⚠️ stub — keyword-based fallback |
| `CodeWorldAdapter` | `adapter/code/adapter.py` | ✅ TreeSitterExtractor |
| `CrossDomainExpander` | `context/cross_domain_expander.py` | ⚠️ stub（由 SubgraphCompiler 部分覆盖） |
| `CrossRefBuilder` | `context/cross_ref_builder.py` | ⚠️ stub（由 semantic_parent edge 部分覆盖） |
| `SubgraphPruner` | `context/pruner.py` | ⚠️ stub — "4-round trim" 未实现 |
| `VectorStore` | `persistence/vector_store.py` | ⚠️ stub — 返回空结果 |
| `MilvusVectorStore` | `persistence/milvus_store.py` | ✅ 实际实现（需 pymilvus） |
| `HybridIndex` | `persistence/hybrid_index.py` | ✅ 语义+关键词双通路 |
| `UnifiedGraphStore` | `persistence/unified_store.py` | ✅ 通用节点表 |
| `LSPExtractor` | `adapter/code/lsp_extractor.py` | ⚠️ stub — 返回空 |

---

> 本文档定义上下文编译与记忆层的完整设计。具体的数据结构和算法见代码 `core/agent/v4/context/` 和 `core/agent/v4/persistence/`。
