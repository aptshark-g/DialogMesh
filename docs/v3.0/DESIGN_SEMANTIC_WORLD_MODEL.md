# DESIGN_STRUCTURAL_WORLD_MODEL.md — 结构化世界模型

> 版本: v1.0 | 日期: 2026-07-12
>
> 不是做"代码知识库"——而是构建一个统一的结构化世界模型。
> 源码/CAD/Unity Scene/DOM/DB Schema 都只是这个世界的不同视图。
>
> Code Adapter 是第一个 World Adapter, 但不是唯一一个。

---

## 目录

1. [定位：结构化世界IR而非代码知识库](#1-定位结构化世界ir而非代码知识库)
2. [Reference Unit：节点的唯一标准](#2-reference-unit节点的唯一标准)
3. [多类型边 + 社区发现](#3-多类型边-社区发现)
4. [主干染色：Betweenness Centrality 多维融合](#4-主干染色betweenness-centrality-多维融合)
5. [三级召回：Intent → Subgraph → Reference → Raw Code](#5-三级召回)
6. [世界适配器架构](#6-世界适配器架构)
7. [Schema 定义](#7-schema-定义)
8. [集成面：与已有 v4 模块的关系](#8-集成面与已有-v4-模块的关系)
9. [实现计划](#9-实现计划)

---

## 1. 定位：结构化世界IR而非代码知识库

### 1.1 为什么不是 Code Context Graph

Code 只是入口。真正要建模的不是代码——是**任何具有结构性的外部对象**。

| 世界 | 输入 |
|:---|:---|
| 源码 | Class, Function, Variable, Module, Package |
| CAD | Part, Assembly, Constraint, Material |
| Unity | GameObject, Prefab, Scene, Component |
| DOM | Element, Style, Script, Event |
| Database | Table, Column, FK, Index, Query |

它们都共享同一个结构：**有拓扑关系、可被引用、可被定位的对象集合。**

### 1.2 Structural World IR

```
External World
      │
      ▼
World Adapter (Code / CAD / Unity / DB / ...)
      │
      ▼
Structure Extractor (Tree-sitter / LSP / Custom)
      │
      ▼
Structural World IR (统一图格式)
      │
      ▼
Context Compiler (推理 + 融合 → 局部子图 → 文本 → LLM)
```

**Code Adapter 是第一个 Adapter。其余世界是预留扩展。**

### 1.3 核心原则

| 原则 | 说明 |
|:---|:---|
| **Reference Unit = Node** | 能被引用、定位、链接、跳转的就是节点 |
| **多类型边** | 不同类型的关系承载不同语义权重 |
| **社区发现替代目录** | Git 树只是 Prior, 真正组团由拓扑决定 |
| **主干 = 信息流关键路径** | 不是访问频率, 是 Betweenness Centrality |
| **产出是子世界而非检索结果** | LLM 看到的是局部工程结构, 不是代码片段 |

---

## 2. Reference Unit：节点的唯一标准

### 2.1 什么能成为节点

标准只有一条：**任何能被外部引用的对象就是 Reference Unit, 就是节点。**

| 是节点 | 不是节点 |
|:---|:---|
| File, Module, Package | if(){}, for(){}, while(){} |
| Class, Interface, Trait, Struct | 局部临时变量 |
| Function, Method, Constructor | 注释, 空白行 |
| Global Variable, Cross-file const | 魔法数字 |
| Enum, Type Alias | inline lambda |

### 2.2 Reference Unit Schema

```python
@dataclass
class ReferenceUnit:
    unit_id: str                    # "pkg::module::ClassName" or file path
    unit_type: str                  # "file" | "class" | "function" | "variable" | "module"
    name: str                       # human-readable name
    world: str                      # "code" | "cad" | "unity" | "dom" | "db"
    language: str = ""              # "python" | "rust" | "java" | ...
    location: Location | None = None # file + line range
    attributes: dict = field(default_factory=dict)  # world-specific metadata
    backbone_score: float = 0.0     # 主干染色分数
    last_updated: float = 0.0
```

这个 Schema 跨语言统一。Python 的 class 和 Rust 的 struct 都是 `unit_type="class"`。

---

## 3. 多类型边 + 社区发现

### 3.1 边的类型体系

关系不是一条 `depends_on`。不同的边承载不同的语义和传播权重：

| 边类型 | 语义 | 传播权重 | 来源 |
|:---|:---|:---|:---|
| `imports` | A 导入 B | 0.30 | 静态分析 |
| `calls` | A 调用 B | 0.25 | 静态分析 + trace |
| `overrides` | A 覆写 B | 0.20 | 静态分析 |
| `references` | A 引用 B (非调用) | 0.15 | 静态分析 |
| `co_changes` | A 和 B 经常一起被修改 | 0.25 | Git history |
| `constrains` | A 约束 B 的行为 | 0.20 | 工程链/配置 |
| `tests` | A 测试 B | 0.10 | 测试文件映射 |
| `implements` | A 实现接口 B | 0.20 | 静态分析 |
| `generates` | A 生成 B | 0.15 | 编译产物 |

### 3.2 社区发现替代 Git 聚类

Git 目录树只是初始 Prior, 不是最终聚类。真正的模块边界由**多类型边的社区发现算法**决定。

```python
class CommunityDetector:
    def detect(self, graph: StructuralWorldGraph) -> List[Community]:
        """Run Louvain / Leiden community detection on multi-edge weighted graph."""
        # 边权重融合: Import*0.3 + Call*0.25 + CoChange*0.25 + Reference*0.15 + ...
        # 社区边界 = 模块边界
```

`utils/` 目录下 `logger.py` 和 `cache.py` 如果没有任何边连接, 就不属于同一社区——即便它们在同一个目录下。

### 3.3 动态索引锚点

社区检测后, 每个社区的核心节点（Bridge → 高 Betweenness）获得动态索引锚点。锚点大小通过 ParameterRegistry 浮点管理, 随访问频率和最新度调整。

---

## 4. 主干染色：Betweenness Centrality 多维融合

### 4.1 主干不是"访问最多"

Logger 被调用次数最多, 但不决定系统拓扑。主干是**信息流必经路径**——用 Betweenness Centrality 衡量。

### 4.2 多维融合

```
BackboneScore =
    0.30 × Structural Centrality      # 图拓扑中多少路径经过
  + 0.30 × Runtime Centrality         # Trace 中的桥梁程度
  + 0.20 × Commit Centrality          # Git 共同修改模式
  + 0.20 × Retrieval Centrality       # Context Compiler 访问频率
```

四种 Centrality 各自归一化后融合。后续加入新的观察源——例如 Test Coverage Centrality——只需要加权一层, 不改公式。

### 4.3 主干染色效果

高 BackboneScore 的节点 → 获得更优先的索引锚点 → 在 ContextCompiler 的图遍历中被优先包含 → 整个子图切得小而准。

所有参数纳入 ParameterRegistry：`world.backbone.structural_weight`、`world.backbone.runtime_weight` 等。

---

## 5. 三级召回

### 5.1 LLM 永远不该直接看到代码

```
用户意图
    │
    ▼
Level 1: Intent → Subgraph
    系统从 World Model 中为当前意图切出一个局部子图 (~300 节点)
    │
    ▼
Level 2: Subgraph → Reference Units
    在 300 节点中提取关键的 Reference Unit (Class/Function 签名 + 关系)
    │
    ▼
Level 3: Reference Units → Raw Code
    只对最相关 5-10 个 Unit 展开源码内容
```

### 5.2 每级的 Token 预算

| 级别 | 内容 | 典型 Token |
|:---|:---|:---|
| L1: 子图 | 节点名 + 边关系 | ~500 |
| L2: Reference Units | 签名 + docstring | ~300 |
| L3: Raw Code | 单个函数的完整源码 | ~200/function |

总额控制在 2000 token 以内——LLM 看到的是一个"局部世界"而非代码堆。

---

## 6. 世界适配器架构

### 6.1 World Adapter 接口

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

class CodeWorldAdapter(WorldAdapter):
    """第一个实现——源码世界。"""
    def __init__(self, languages: List[str] = None):
        self._languages = languages or ["python"]
        self._extractors = {lang: TreeSitterExtractor(lang) for lang in self._languages}
```

### 6.2 双轨提取：一进入就复用 MultiTierPipeline

CodeWorldAdapter 内置三级精度：

| Tier | 工具 | 速度 | 产出 |
|:---|:---|:---|:---|
| Tier 0 | Tree-sitter Query | ~500ms/1000 文件 | Import/Call 关系的快速近似 |
| Tier 1 | Tree-sitter 完整遍历 | ~5s/1000 文件 | 全部 Reference Unit + 精确边 |
| Tier 2 | LSP / HoloGram / knot | 分钟级 | 跨文件语义级关系 |

和 MultiTierPipeline 完全同构——Tier 0 先跑出 Partial Model, 后台补 Tier 1+2。

### 6.3 增量更新

```
git.commit Event → CodeWorldAdapter.evict(file) → re-extract → merge into Structural Graph
```

不是全量重建。只更新变更文件及其直接邻居的边。

---

## 7. Schema 定义

### 7.1 StructuralWorldGraph

```python
@dataclass
class StructuralWorldGraph:
    graph_id: str
    world: str                          # "code" | "cad" | ...
    units: Dict[str, ReferenceUnit]     # unit_id → ReferenceUnit
    edges: List[StructuralEdge]         # 多类型边
    communities: Dict[str, List[str]]   # community_id → unit_ids
    backbone: Dict[str, float]          # unit_id → backbone_score
    created_at: float
    last_extracted_at: float
```

### 7.2 StructuralEdge

```python
@dataclass
class StructuralEdge:
    edge_id: str
    edge_type: str                      # "imports" | "calls" | "references" | ...
    source_id: str                      # 源 ReferenceUnit ID
    target_id: str                      # 目标 ReferenceUnit ID
    weight: float = 1.0                 # 边权重
    source: str = ""                    # "static" | "trace" | "commit" | "test"
    confidence: float = 1.0             # 0-1
```

### 7.3 Context Compiler 接口

```python
class StructuralContextCompiler:
    def compile_subgraph(self, intent: str, world: str = "code",
                         max_nodes: int = 300) -> SubgraphResult:
        """从 World Model 中为给定意图切出局部子图。"""

@dataclass
class SubgraphResult:
    nodes: List[ReferenceUnit]
    edges: List[StructuralEdge]
    backbone_units: List[str]           # 高骨干节点
    total_tokens_estimate: int
```

这个接口不关心 World Model 内部是什么——Code/CAD/Unity 都一样。

---

## 8. 集成面

| 模块 | 关系 |
|:---|:---|
| MultiTierPipeline | CodeWorldAdapter 内置三级精度提取 |
| Projector | `git.commit` → engineering/memory 域（已有） |
| Context Compiler | World Model 输出子图 → 融合其他域 → 变为 LLM 上下文 |
| Observation Compiler | 代码事件（新文件/函数）→ Observation |
| Hypothesis Engine | 主干节点的高共识 Hypothesis → Knowledge |
| Skill Layer | 跨项目结构模式蒸馏（插件/中间件/仓储模式） |
| ParameterRegistry | 所有权重、阈值、锚点大小统一管理 |
| TierHeatBridge | 高 Backbone 节点 = 热数据 → 提升 GC 层级 |
| Cognitive Scheduler | ExtractionTask → Worker Pool 异步执行 |

---

## 9. 实现计划

| Phase | 内容 | 依赖 |
|:---|:---|:---|
| Phase 1 | ReferenceUnit + StructuralEdge + StructuralWorldGraph Schema | 无 |
| Phase 2 | Tree-sitter 集成 + 双轨提取 (Tier 0+1) | Phase 1, tree-sitter |
| Phase 3 | 社区检测 + Betweenness Centrality 染色 | Phase 2 |
| Phase 4 | Subgraph 编译 + ContextCompiler 接口 | Phase 2-3, ContextCompiler |
| Phase 5 | 增量更新 (git.commit → re-extract) | Phase 2, EventBus |
| Phase 6 | ParameterRegistry 集成 (权重/阈值/锚点) | ParameterRegistry |
| Phase 7 | LSP/HoloGram 辅助提取 (Tier 2) | Phase 2 |

---

> 不是做"代码知识库"。
> 是把代码世界压缩成可推理的局部工程子图。
> Code 是第一个 World。CAD、Unity、DB 以后都是同一个接口。
>
> LLM 看到的永远不是代码——是这个局部世界的结构。
