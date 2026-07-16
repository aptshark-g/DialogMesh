# Semantic World Model — 语义世界运行时

> 版本: v1.0 | 日期: 2026-07-16
> 状态: Draft
> 关联: DESIGN_PERSPECTIVE_PLANNER.md, DESIGN_SEMANTIC_OBJECT.md, DESIGN_RELATION_SUBSTRATE.md

## 一、范式转变

### 1.1 RAG → Semantic World Runtime

```mermaid
flowchart LR
    subgraph OLD["RAG 范式"]
        T["文本"] --> C["Chunk"] --> E["Embedding"] --> R["Top-K 检索"] --> L["LLM"]
    end

    subgraph NEW["Semantic World Runtime"]
        I["现实输入"] --> WC["构建世界模型"]
        WC --> OB["对象化"]
        OB --> RL["关系化"]
        RL --> ZM["多尺度观察"]
        ZM --> CC["上下文编译"]
        CC --> L2["LLM 推理"]
    end
```

> **LLM 不直接面对信息碎片，而是通过一个可缩放的世界接口观察。**

### 1.2 核心命题

| 旧假设 | 新假设 |
|--------|--------|
| 信息 = 独立片段 (Chunk) | 信息 = 持续展开的结构实体 (SemanticObject) |
| 图上的 Node = 世界里的 Object | Node 是子图的入口，不是终点 |
| 检索 = 找到相关文本 | 渲染 = 构造适合当前问题的局部世界 |
| Context = 拼接片段 | Context = 世界视图 (World View) |

## 二、宏观架构

### 2.1 世界构建层

```mermaid
flowchart TB
    subgraph INPUT["外部世界"]
        DOC["文档"]
        CODE["代码"]
        BEH["对话/行为"]
    end

    subgraph EXTRACT["提取层"]
        DE["DocumentExtractor"]
        CE["CodeExtractor<br/>(预留)"]
        BR["BehaviorRecorder"]
    end

    subgraph OBS["Observation 层"]
        O["Observation<br/>· source<br/>· content<br/>· location<br/>· evidence"]
    end

    DOC --> DE
    CODE --> CE
    BEH --> BR
    DE --> O
    CE --> O
    BR --> O
```

### 2.2 语义世界模型（核心）

```mermaid
flowchart TB
    OBS["Observation Layer"] --> SBO["SemanticObjectBuilder"]

    SBO --> SWM["Semantic World Model"]

    SWM --> SO["SemanticObject<br/>· identity<br/>· name<br/>· semantic_path<br/>· composition_edges"]
    SWM --> RS["RelationSubstrate<br/>· relation_kind × semantic_strength<br/>· evidence chain<br/>· causal explanation"]
    SWM --> PR["Projection System<br/>· design<br/>· code<br/>· knowledge<br/>· causal<br/>· behavior"]

    SO --> RZ["RecursiveZoom"]
    RS --> RQ["Relation Query"]
    PR --> WV["World View"]
```

### 2.3 模块职责

| 模块 | 回答的问题 | 职责 |
|------|-----------|------|
| **SemanticObject** | 这个东西是什么？ | identity, hierarchy, composition, projection |
| **RelationSubstrate** | 它和其他东西有什么关系？ | depends, implements, produces, causes, follows |
| **Projection** | 从哪个世界看它？ | design / code / knowledge / behavior / causal |
| **RecursiveZoom** | 我要看到多细？ | LOD 1-4 连续缩放 |
| **PerspectivePlanner** | 我应该怎么看？ | strategy, horizon, domain allocation |
| **ContextCompiler** | 如何压缩成 LLM 可读的上下文？ | 结构化 IR 组装 |

## 三、运行时查询流程

```mermaid
flowchart TB
    Q["用户: Runtime 怎么工作？"] --> IP["IntentParser<br/>target=Runtime<br/>world=design"]

    IP --> PP["PerspectivePlanner"]
    PP --> P["Perspective<br/>· world=design<br/>· horizon=3<br/>· strategy=architecture<br/>· budget=3000"]

    P --> SI["SemanticIndex.locate('Runtime')"]
    SI --> SO["SemanticObject(Runtime)"]

    SO --> RZ["RecursiveZoom<br/>LOD=3 展开"]
    RZ --> EXP["展开结果<br/>Runtime<br/>├── Observation<br/>│   ├── Normalizer<br/>│   ├── Parser<br/>│   └── Projector<br/>├── Hypothesis<br/>└── Knowledge"]

    RS["RelationSubstrate.query<br/>type=structural"] --> REL["关系<br/>Observation → produces → Hypothesis<br/>Hypothesis → freezes → Knowledge"]

    PR["Projection<br/>resolve('design', 'definition')"] --> PROJ["设计投影<br/>'Runtime是v4核心执行引擎'"]

    EXP --> CC["ContextCompiler"]
    REL --> CC
    PROJ --> CC

    CC --> IR["Context IR<br/>[Level 1] Runtime定义<br/>[Level 2] Composition<br/>[Level 3] 展开详情<br/>{Relations}<br/>{Projection}"]

    IR --> LLM["LLM<br/>观察这个小世界后回答"]
```

## 四、RecursiveZoom — 连续尺度

```mermaid
flowchart TB
    L1["LOD 1: ● Runtime<br/>一句话摘要"] --> L2
    L2["LOD 2: Runtime<br/>├── Observation<br/>├── Hypothesis<br/>└── Knowledge<br/>名称 + 定义段落"]

    L2 --> L3
    L3["LOD 3: Observation<br/>├── Normalizer<br/>│   ├── Clean<br/>│   ├── Canonicalize<br/>│   └── Validate<br/>├── Parser<br/>└── Projector<br/>子节点概览 + 关系边"]

    L3 --> L4
    L4["LOD 4: Normalizer<br/>├── remove_noise()<br/>├── unify_format()<br/>└── build_observation()<br/>叶子节点完整内容"]

    classDef active fill:#4a9,stroke:#333,color:#fff
    class L2 active
```

## 五、Projection 路由

```mermaid
flowchart LR
    subgraph PERSPECTIVE["PerspectivePlanner 决策"]
        ARC["architecture<br/>设计理念"]
        EXE["execution<br/>执行流程"]
        ENG["engineering<br/>代码实现"]
        EVO["evolution<br/>设计演变"]
    end

    subgraph PROJECTION["Projection 选择"]
        D["design projection<br/>文档定义/架构说明"]
        C["code projection<br/>类/函数/实现关系"]
        K["knowledge projection<br/>冻结事实/Belief"]
        CA["causal relation<br/>为什么这样设计"]
    end

    ARC --> D
    EXE --> K
    ENG --> C
    EVO --> CA
```

## 六、完整模块关系

```mermaid
flowchart TB
    subgraph USER["User / External Data"]
        U1["文档"]
        U2["代码"]
        U3["对话/行为"]
    end

    subgraph BUILD["World Construction Layer"]
        B1["DocumentExtractor"]
        B2["CodeExtractor"]
        B3["BehaviorRecorder"]
        B4["SemanticObjectBuilder"]
    end

    U1 --> B1
    U2 --> B2
    U3 --> B3
    B1 --> B4
    B2 --> B4
    B3 --> B4

    subgraph MODEL["Semantic World Model"]
        M1["SemanticObject"]
        M2["RelationSubstrate"]
        M3["Projection System"]
    end

    B4 --> M1
    B1 --> M2
    B2 --> M2
    B3 --> M2
    M1 --> M2
    M1 --> M3

    subgraph RUNTIME["Query Runtime"]
        R1["IntentParser"]
        R2["PerspectivePlanner"]
        R3["RecursiveZoom"]
        R4["ContextCompiler"]
    end

    U3 --> R1
    R1 --> R2
    M1 --> R3
    R2 --> R3
    M2 --> R4
    M3 --> R4
    R3 --> R4

    R4 --> LLM["LLM"]
```

## 七、和现有实现的对照

| 模块 | 设计 | 实现 | 缺口 |
|------|------|------|------|
| SemanticObject | 纯数据 + identity + composition + projection | ✅ 9.8K objects | ContextCompiler 未消费 |
| RelationSubstrate | 统一关系基座 + evidence chain | ✅ 5.4K edges, 6 Resolver | Context IR 未注入关系 |
| PerspectivePlanner | 期望→策略→域分配 | ✅ 接入 PCR 期望推断 | 域权重未改变渲染路径 |
| RecursiveZoom | LOD + perspective 的 continuous zoom | ✅ ObjectRuntime.render | ContextCompiler 未调用 |
| ContextCompiler | 世界渲染器 | ❌ BFS + keyword match | 仍是检索模式 |
| Projection | Resolver 动态生成 | ⚠️ DesignResolver 可用，其余 stub | 未接入管线 |

**核心缺口：ContextCompiler 从 "检索模式" 升级为 "世界渲染模式"。**

## 八、ContextCompiler 升级路线

```mermaid
flowchart LR
    subgraph OLD["当前"]
        Q1["query"] --> CS1["ContentIndex<br/>find_seeds()"]
        CS1 --> EX1["expand_subgraph()"]
        EX1 --> CX1["代码片段"]
    end

    subgraph NEW["目标"]
        Q2["query + Perspective"] --> SO2["SemanticObject.locate()"]
        SO2 --> RZ2["ObjectRuntime.render<br/>LOD + perspective"]
        SO2 --> RS2["RelationSubstrate.query()"]
        SO2 --> PR2["ProjectionResolver.resolve()"]
        RZ2 --> CC2["ContextCompiler"]
        RS2 --> CC2
        PR2 --> CC2
        CC2 --> CX2["结构化 World View"]
    end
```

### 实现步骤

1. **ContextCompiler 接 ObjectRuntime**: `render(obj, LOD=horizon.d, perspective=persp)`
2. **注入 RelationSubstrate**: 每条 context entry 附带 relation edges
3. **注入 Projection**: design/code/knowledge/causal 按 perspective 选择
4. **废弃 ContentIndex BFS**: 替换为 SemanticPath 导航
