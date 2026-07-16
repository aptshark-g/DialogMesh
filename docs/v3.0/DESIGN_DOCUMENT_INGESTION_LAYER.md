# Document Ingestion Layer (DIL) — Design Document

**Status:** Draft v0.1  
**Author:** DialogMesh Architecture Team  
**Date:** 2026-07-15  
**Target:** v4.1  
**Depends on:** v4.0 (PathAwareScheduler, ObservationCompiler, HypothesisEngine, ContextAssembler)

---

## 1. 问题陈述

### 1.1 v4 当前的缺口

v4 的认知链（Cognitive Chain）已经完整：

```
EventIR → ObservationCompiler → ObservationPool → HypothesisEngine → Knowledge → Skill
```

但这个链条只能处理**已经进入系统的信息**。外部文档（MD、PDF、代码、网页）还没有被转换成 v4 能理解的"认知对象"。

### 1.2 传统 RAG 为什么不够

| 维度 | 传统 RAG | v4 需要 |
|------|----------|---------|
| 目标 | "用户问什么，返回哪段文本" | "这段文本在知识体系里是什么角色" |
| 输出 | 文本块（chunk） | 结构化 Observation |
| 关系 | 向量相似度 | 概念关系、约束、流程 |
| 演化 | 静态索引 | 可竞争、可冻结、可蒸馏 |
| 认知 | 无 | 支持 Hypothesis 验证 |

### 1.3 核心洞察

> **文档不是事件流，而是静态知识场（Knowledge Field）。**
>
> 对话树 = 动态事件树（按时间产生）  
> 文档树 = 静态结构树（一次性存在）  
>
> 但它们都可以生成 Observation。v4 需要的是：**让块状外部知识进入认知链的入口。**

---

## 2. 设计目标

### 2.1 核心目标

建立 **Document Ingestion Layer（DIL）**，负责：

```
外部文档 → Document Tree → Document Observation Bundle → Observation Pool → 现有认知链
```

### 2.2 非目标

- 不做通用文件解析器（PDF/CAD/网页等 v4.2 再做）
- 不做完美语义提取（先用标题结构 + 轻量 LLM）
- 不替换现有 RAG（HybridIndex 继续作为兜底）

### 2.3 成功标准

| 指标 | 目标 |
|------|------|
| 导入时间 | 100 篇 MD < 5 分钟 |
| 检索质量 | 用户问"Context Compiler 设计"，返回的 Observation 包含定义+流程+参数 |
| 认知闭环 | 导入的文档能进入 Hypothesis → Knowledge 冻结流程 |
| 端到端测试 | `dialogmesh ingest docs/` → `dialogmesh chat "什么是 Context Compiler?"` → 正确回答 |

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        External Documents                             │
│  (MD / PDF / Code / Web / CAD / ...)                                │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Document Ingestion Layer (DIL)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │   Parser    │→ │ Document    │→ │ Observation │→ │  Chunk   │ │
│  │  (MD/...)   │  │    Tree     │  │  Extractor  │  │ Strategy │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  │ Selector │ │
│                                                       └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     v4 Cognitive Chain (Existing)                     │
│  ObservationPool → HypothesisEngine → Knowledge → Skill           │
│                          │                                          │
│                          ▼                                          │
│              ContextAssembler → CrossDomainContextIR → LLM          │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件

#### 3.2.1 DocumentParser

```python
class DocumentParser(ABC):
    """Parse external document into raw DocumentNode tree."""
    
    @abstractmethod
    def parse(self, content: str, source_path: str) -> DocumentNode:
        """Return root DocumentNode with hierarchical children."""
```

**MarkdownParser 实现：**
- 按 `# / ## / ###` 切分标题层级
- 保留代码块、表格、列表结构
- 输出 `DocumentNode` 树

#### 3.2.2 DocumentTree

```python
@dataclass
class DocumentNode:
    """Static structure tree node — NOT a discourse block."""
    node_id: str                    # hash(source_path + heading_path)
    source_path: str                # 原始文件路径
    heading_path: List[str]         # ["# DialogMesh", "## v4", "### Context Compiler"]
    level: int                      # 1, 2, 3, ...
    raw_text: str                   # 该 section 的完整文本
    node_type: str                  # "heading" | "paragraph" | "code" | "table" | "list"
    children: List["DocumentNode"]  # 子节点
    parent: Optional["DocumentNode"] = None
    
    # 认知元数据（由 ObservationExtractor 填充）
    observed_concepts: List[str] = field(default_factory=list)
    observed_relations: List[Relation] = field(default_factory=list)
    observation_type: str = ""       # "definition" | "constraint" | "procedure" | "example"
    confidence: float = 0.0
```

**与 DiscourseBlockTree 的区别：**

| 维度 | DocumentTree | DiscourseBlockTree |
|------|-------------|-------------------|
| 结构来源 | 文档标题层级 | 对话 cohesion score |
| 产生方式 | 一次性解析 | 动态累积 |
| 节点内容 | 章节/段落 | 消息/话语块 |
| 边类型 | 父子（包含） | 回复（因果） |
| 时间性 | 静态 | 动态 |
| 用途 | 知识检索 | 对话上下文 |

#### 3.2.3 ObservationExtractor

```python
class ObservationExtractor:
    """Extract structured observations from DocumentNode.
    
    NOT a simple chunker. It interprets document content into
    cognitive primitives: concepts, relations, constraints, procedures.
    """
    
    def extract(self, node: DocumentNode) -> List[DocumentObservation]:
        """Return observations that can enter the cognitive chain."""
```

**提取策略（按 observation_type）：**

| 类型 | 检测规则 | 示例 |
|------|----------|------|
| `definition` | 含 "是..."、"定义为..."、"指..." | "Context Compiler 是将多域知识编译为 IR 的组件" |
| `constraint` | 含 "必须..."、"不能..."、"限制..." | "BudgetAllocator 必须保证总 token ≤ 预算" |
| `procedure` | 含 "步骤..."、"流程..."、"首先...然后..." | "Hypothesis 冻结流程：观察→假设→投票→知识" |
| `example` | 含 "例如..."、"示例..."、"比如..." | "例如：min_support=8 时..." |
| `relation` | 含 "依赖..."、"基于..."、"导致..." | "Knowledge 依赖于 Hypothesis 的投票收敛" |
| `parameter` | 含 "参数..."、"阈值..."、"默认值..." | "community_resolution: 1.0 (默认)" |

**提取方式：**
- 规则匹配（快速，覆盖 80%）
- LLM 辅助（慢，覆盖复杂语义，可选）

#### 3.2.4 ChunkStrategy Selector

```python
class ChunkStrategyRegistry:
    """Pluggable strategy registry for document chunking.
    
    NOT just for chunking — general strategy selection framework.
    Can be reused for retrieval strategy, LLM provider selection, etc.
    """
    
    def register(self, strategy: ChunkStrategy) -> None: ...
    def select(self, task: TaskContext, constraints: RuntimeConstraints) -> ChunkStrategy: ...
```

**策略列表：**

| 策略 | 速度 | 质量 | 适用场景 |
|------|------|------|----------|
| `FixedSizeChunkStrategy` | ⚡⚡⚡ | ⭐⭐⭐ | Fast Path 紧急处理 |
| `HeaderChunkStrategy` | ⚡⚡⚡ | ⭐⭐⭐⭐ | Markdown 结构保留 |
| `SemanticChunkStrategy` | ⚡⚡ | ⭐⭐⭐⭐⭐ | 高质量语义块 |
| `LLMChunkStrategy` | ⚡ | ⭐⭐⭐⭐⭐ | 最高质量，离线处理 |

**选择逻辑：**

```python
def select(self, task, constraints):
    candidates = filter(supported_types & latency_budget)
    
    # BayesianOptimizer 加权
    if self._optimizer:
        scores = self._optimizer.predict_quality(candidates, task)
        return max(candidates, key=lambda c: scores[c.name])
    
    # 默认：质量/延迟权衡
    return max(candidates, key=lambda c: c.quality_score / (c.latency_ms + 1))
```

### 3.3 数据流

```
用户: dialogmesh ingest docs/v3.0/
    │
    ▼
┌─────────────────────────────────────────┐
│  CLI: ingest 命令                         │
│  - 遍历目录，收集所有 .md 文件              │
│  - 对每个文件调用 DocumentIngestionPipeline │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  DocumentIngestionPipeline.ingest_file()  │
│  1. 读取文件内容                          │
│  2. 检测文件类型 → 选择 Parser             │
│  3. Parser.parse() → DocumentNode tree   │
│  4. 遍历 tree，对每个 node:               │
│     a. ChunkStrategySelector 选择策略     │
│     b. 策略执行 → 子节点或保持原样          │
│     c. ObservationExtractor.extract()   │
│     d. 生成 DocumentObservationBundle      │
│  5. Bundle → ObservationPool.put()        │
│  6. 可选：触发 HypothesisEngine 处理       │
└─────────────────────────────────────────┘
    │
    ▼
ObservationPool (已有组件)
    │
    ▼
后续用户提问: "什么是 Context Compiler?"
    │
    ▼
ContextAssembler.assemble_ir()
    ├── 从 ObservationPool 检索相关 DocumentObservation
    ├── 从 Knowledge 检索已冻结的知识
    ├── 从 World Model 检索相关子图
    └── 组装 CrossDomainContextIR
    │
    ▼
LLM → 回复
```

---

## 4. 与现有 v4 组件的集成

### 4.1 集成点

| 现有组件 | 集成方式 | 文件修改 |
|----------|----------|----------|
| `PathAwareScheduler` | 新增 `ChunkStrategySelector` 子组件 | `scheduler.py` |
| `ObservationPool` | 接受 `DocumentObservationBundle` | `pool.py` (无需修改，已有 put()) |
| `ObservationCompiler` | 新增 `DocumentDomainAdapter` | 新建 `document_domain_adapter.py` |
| `ContextAssembler` | 新增 `DocumentSource` | `source.py` |
| `HypothesisEngine` | 处理 `DocumentObservation` | 无需修改，已有通用接口 |
| `CLI` | 新增 `ingest` 子命令 | `cli/main.py` |
| `API` | 新增 `/v4/ingest` 端点 | `api.py` |

### 4.2 DocumentObservation 数据模型

```python
@dataclass
class DocumentObservation:
    """Observation extracted from document — enters cognitive chain."""
    
    # 继承自 ObservationBundle 的字段
    observation_id: str
    source_path: str              # 原始文档路径
    node_id: str                  # DocumentNode ID
    event_id: str                 # 关联的 ingestion event
    
    # 认知内容
    observation_type: str         # "definition" | "constraint" | "procedure" | "example" | "relation" | "parameter"
    raw_text: str                # 原始文本片段
    concepts: List[str]           # 提取的概念
    relations: List[Relation]     # 概念间关系
    constraints: List[str]      # 约束条件
    
    # 元数据
    confidence: float = 0.0     # 提取置信度
    heading_path: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0
    
    # 进入认知链后的状态
    hypothesis_ids: List[str] = field(default_factory=list)  # 关联的假设
    knowledge_id: Optional[str] = None  # 冻结为知识后的 ID
```

---

## 5. 实现计划

### 5.1 Phase 1: 基础设施（1 天）

| 任务 | 文件 | 行数 |
|------|------|------|
| `ChunkStrategyRegistry` 框架 | `core/agent/v4/chunking/registry.py` | ~100 |
| `FixedSizeChunkStrategy` | `core/agent/v4/chunking/strategies.py` | ~30 |
| `HeaderChunkStrategy` | `core/agent/v4/chunking/strategies.py` | ~60 |
| `SemanticChunkStrategy` | `core/agent/v4/chunking/strategies.py` | ~80 |
| `LLMChunkStrategy` | `core/agent/v4/chunking/strategies.py` | ~50 |
| `PathAwareScheduler` 集成 | `core/agent/v4/cognitive_scheduler/scheduler.py` | ~50 |

### 5.2 Phase 2: 文档摄入核心（1 天）

| 任务 | 文件 | 行数 |
|------|------|------|
| `DocumentNode` / `DocumentTree` | `core/agent/v4/document/tree.py` | ~80 |
| `MarkdownParser` | `core/agent/v4/document/parsers.py` | ~100 |
| `ObservationExtractor` | `core/agent/v4/document/extractor.py` | ~150 |
| `DocumentIngestionPipeline` | `core/agent/v4/document/pipeline.py` | ~100 |
| `DocumentObservation` | `core/agent/v4/document/observation.py` | ~50 |

### 5.3 Phase 3: 集成与入口（1 天）

| 任务 | 文件 | 行数 |
|------|------|------|
| `DocumentDomainAdapter` | `core/agent/v4/observation_compiler/document_domain_adapter.py` | ~80 |
| `DocumentSource` (ContextAssembler) | `core/agent/v4/context/source.py` | ~50 |
| CLI `ingest` 命令 | `core/agent/v4/cli/main.py` | ~50 |
| API `/v4/ingest` 端点 | `core/agent/v4/api.py` | ~30 |
| 端到端测试 | `tests/test_document_ingestion.py` | ~150 |

### 5.4 Phase 4: 验证（半天）

```bash
# 导入 docs/ 目录
dialogmesh ingest docs/v3.0/

# 验证检索
dialogmesh chat "什么是 Context Compiler?"
# 期望：返回包含定义、流程、参数的 Observation

dialogmesh chat "Hypothesis 冻结的阈值是多少？"
# 期望：返回 min_support, max_conflict 等参数

dialogmesh inspect knowledge
# 期望：看到从文档冻结的 KnowledgeNode
```

---

## 6. 关键设计决策

### 6.1 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 文档树 vs 话语块树 | **独立** | 结构来源不同（标题层级 vs cohesion），不能复用 |
| 切分策略选择 | **调度器驱动** | 统一决策框架，可复用于其他策略选择场景 |
| 提取方式 | **规则 + 可选 LLM** | 规则覆盖 80%，LLM 处理复杂语义，避免强依赖 |
| 导入时机 | **Async Path** | 后台处理，不阻塞用户交互 |
| 存储 | **ObservationPool** | 复用现有认知链入口，不新建存储层 |
| 与 RAG 关系 | **互补** | HybridIndex 作为兜底，DocumentObservation 作为认知层 |

### 6.2 不做的内容

| 内容 | 原因 | 计划版本 |
|------|------|----------|
| PDF 解析 | 需要外部依赖（pymupdf/pdfplumber） | v4.2 |
| 代码 AST 解析 | 需要 tree-sitter | v4.2 |
| 网页抓取 | 需要爬虫框架 | v4.2 |
| 完美语义提取 | 需要大量 LLM 调用，成本高 | v4.2 |
| 多语言文档 | 先验证中文/英文 MD | v4.1 |

---

## 7. 与主人方案的对应

主人的核心洞察：

> **"不是缺一个 RAG 模块，而是缺外部知识进入认知链的入口。"**

本文档的对应：

| 主人概念 | 本文档实现 |
|----------|----------|
| "文档不是事件流，是静态知识场" | `DocumentTree` — 静态结构树 |
| "先变成 Observation，再进入 Hypothesis" | `ObservationExtractor` → `DocumentObservation` → `ObservationPool` |
| "块状文档拆成离散观察" | `DocumentNode` → 多个 `DocumentObservation` |
| "检索增强认知（RAC）" | `DocumentSource` → `ContextAssembler` → `CrossDomainContextIR` |
| "Document Ingestion Layer" | `core/agent/v4/document/` 完整模块 |

---

## 8. 附录

### 8.1 术语对照

| 术语 | 含义 |
|------|------|
| DIL | Document Ingestion Layer |
| DocumentTree | 文档结构树（静态） |
| DocumentNode | 文档树节点（标题/段落/代码块） |
| DocumentObservation | 从文档提取的 Observation（进入认知链） |
| ChunkStrategy | 文档切分策略（Fixed/Header/Semantic/LLM） |
| ObservationExtractor | 文档内容 → 结构化 Observation |
| RAC | Retrieval-Augmented Cognition（检索增强认知） |

### 8.2 参考文档

- `DESIGN_V4_KNOWLEDGE_REFINEMENT.md` §3.2 — Knowledge Ingestion 需求
- `DESIGN_CROSS_DOMAIN_CONTEXT.md` — Context IR 设计
- `RFC_PARAMETER_REGISTRY.md` — 参数调优
- `chapter2_relation_over_prompt.md` — 关系优于提示

---

**End of Document**
