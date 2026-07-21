# DialogMesh v6 — 业务链设计 · 第二章：Context (上下文装配)

> 版本: v1.0 | 日期: 2026-07-21
> 
> 设计来源: DESIGN_CROSS_DOMAIN_CONTEXT.md (501行) + design_context_window.md (968行) +
>          CONTEXT_COMPRESSION_DESIGN.md (461行) + DESIGN_V4_CONTEXT_ENGINEERING.md (421行) +
>          ENGINEERING_CONTEXT_MANAGER.md (879行) +
>          代码: v4/context/ (11文件·3542行) + discourse_block_tree (12文件·1600行) +
>                + topic_tree (3文件·1868行) + context_window (6文件·1100行)
>
> 核心命题: 对话不是平铺的文本——是 DiscourseTree + TopicTree + Subgraph 三层结构的动态上下文。
>          Context 回答: "LLM 应该看到什么？多少？以什么优先级？"

---

## 一、Context 在 10 链中的位置

```mermaid
graph TD
    PCR["PCR Output"]
    IP["IntentParser · ParseResult"]
    PLAN["Planner · TaskGraph"]

    subgraph CONTEXT["链02: Context Assembly"]
        direction TB
        DS["DomainSelector<br/>领域匹配+预算分配"]
        PP["PerspectivePlanner<br/>多空间视角策略"]
        CA["ContextAssembler<br/>多源组装→CrossDomainContextIR"]
        BA["BudgetAllocator<br/>Token预算"]
        SC["SubgraphCompiler<br/>水波扩展"]
        PR["Pruner<br/>上下文剪枝"]
    end

    PCR -->|"expectation→domain boost"| DS
    PCR -->|"complexity→budget"| BA
    IP -->|"intent→domain selector"| DS
    PLAN -->|"TaskGraph→context entries"| CA

    CA --> IR["CrossDomainContextIR<br/>entries[] + domain_allocation"]
    IR -->|"to_prompt()"| LLM["链02 LLM调用"]

    SC -.->|"需要时扩展"| CA
```

---

## 二、数据源

```mermaid
graph TD
    CA["ContextAssembler<br/>assemble_ir()"]

    CA --> S1["DiscourseBlockTree<br/>当前活跃块的上下文"]
    CA --> S2["TopicTree<br/>当前分支的主题摘要"]
    CA --> S3["ObservationPool<br/>文档检索结果"]
    CA --> S4["ConversationHistory<br/>最近N轮对话"]
    CA --> S5["SemanticWorld<br/>语义对象图"]
    CA --> S6["SubgraphCompiler<br/>水波扩展子图"]

    CA --> IR["CrossDomainContextIR<br/>统一表示"]
```

**实现**: `v4/context/source.py` (835行) — 多源数据提供者  
**当前接入**: DiscourseBlockTree ✅ · TopicTree ✅ · ObservationPool ✅ · SubgraphCompiler ✅

---

## 三、DomainSelector + BudgetAllocator

```mermaid
graph TD
    TEXT["用户输入"]

    TEXT --> DS["DomainSelector<br/>领域关键词匹配"]
    
    PCR["PCR expectation"] -->|"TOOL→P域优先<br/>ADVISOR→G域优先"| DS
    IP["IntentParser intent"] -->|"C→P域<br/>EXPLAIN→G域"| DS
    
    DS --> BOOSTS["domain_boosts<br/>{P:0.8, G:0.5, ...}"]
    
    BOOSTS --> BA["BudgetAllocator<br/>Token 预算分配"]
    BOOSTS --> PP["PerspectivePlanner<br/>多空间视角"]
    
    BA --> ALLOC["domain_allocation<br/>[P:200t, G:100t, ...]"]
    PP --> PERSPECTIVE["perspective strategy<br/>/ horizon depth"]
```

**实现**: `v4/context/domain_selector.py` (100行) + `budget_allocator.py` (217行)  
**PCR 调控**: ✅ `expectation→domain_boosts` 已接  
**当前问题**: budget 在 to_prompt 时已按 0-budget 过滤 ✅ (上次修复)

---

## 四、SubgraphCompiler

```mermaid
graph TD
    TEXT["用户输入"] --> FIND["_find_targets_semantic()<br/>匹配语义对象"]
    
    FIND --> TARGETS["targets: Set[str]<br/>语义匹配到的概念"]

    TARGETS -->|"非空"| EXPAND["SubgraphCompiler.expand()<br/>max_depth=2 · max_nodes=50"]
    
    EXPAND --> NODES["subgraph nodes[]<br/>水波扩展结果"]
    
    NODES --> INJECT["添加到 context<br/>domain=G · type=subgraph_node<br/>confidence=0.6"]

    PCR_LOGICAL["PCR LOGICAL_LEAP"] -."未接".-> EXPAND
```

**实现**: `v4/compiler/subgraph_compiler.py` (326行)  
**当前接入**: ✅ `_find_targets_semantic()` + `SubgraphCompiler.expand()`  
**待接**: LOGICAL_LEAP → 水波扩展 (来自 PCR NoiseSpan)

---

## 五、上下文编译流程 (完整)

```mermaid
sequenceDiagram
    participant EV as on_event
    participant DS as DomainSelector
    participant PP as PerspectivePlanner
    participant CA as ContextAssembler
    participant SC as SubgraphCompiler
    participant IR as CrossDomainContextIR
    participant LLM as _call_llm

    EV->>DS: match(text, domain_boosts)
    DS-->>EV: domain_boosts

    EV->>PP: plan_multi(text, budget, expectation)
    PP-->>EV: perspectives[]

    EV->>CA: assemble_ir(text, budget, boosts)
    CA->>CA: DiscourseBlockTree.context()
    CA->>CA: TopicTree.branch_context()
    CA->>CA: ObservationPool.search()
    CA-->>EV: CrossDomainContextIR

    EV->>SC: expand(targets, depth=2, nodes=50)
    SC-->>EV: subgraph nodes
    EV->>IR: add_entry(domain=G, subgraph_nodes)

    EV->>LLM: to_prompt() → Gateway → DeepSeek
```

---

## 六、to_prompt 序列化

```mermaid
graph TD
    IR["CrossDomainContextIR<br/>entries[] + domain_allocation"]

    IR --> FILTER["过滤: 0-budget domain 跳过"]
    FILTER --> PER_DOMAIN["按 domain 分组<br/>[P] entries · [G] entries · ..."]
    PER_DOMAIN --> TRUNCATE["max_tokens 截断"]

    TRUNCATE --> PROMPT["[System]<br/>...<br/>[Context]<br/>## [P] ···<br/>## [G] ···<br/>[User]<br/>..."]
```

**实现**: `v4/context/cross_domain_ir.py` L173-275 `to_prompt()`  
**已修复**: ✅ 0-budget domain 跳过 (上次修复)

---

## 七、代码 ↔ 设计映射

```mermaid
graph TD
    subgraph DESIGN["设计文档"]
        D1["DESIGN_CROSS_DOMAIN_CONTEXT<br/>501行"]
        D2["design_context_window<br/>968行"]
        D3["DESIGN_V4_CONTEXT_ENGINEERING<br/>421行"]
    end

    subgraph CODE["代码 (~8000行)"]
        C1["v4/context/assembler.py 373行"]
        C2["v4/context/domain_selector.py 100行"]
        C3["v4/context/budget_allocator.py 217行"]
        C4["v4/context/source.py 835行"]
        C5["v4/context/cross_domain_ir.py 279行"]
        C6["v4/context/pruner.py 303行"]
        C7["v4/compiler/subgraph_compiler.py 326行"]
    end

    D1 --> C1
    D1 --> C5
    D2 --> C2
    D2 --> C3
    D3 --> C4
    D3 --> C7
```

---

## 八、接入 Engine 现状

```
✅ DomainSelector          — 领域匹配 + PCR 调控
✅ PerspectivePlanner      — 多空间视角
✅ ContextAssembler        — 多源组装
✅ BudgetAllocator         — Token 分配
✅ SubgraphCompiler        — 水波扩展
✅ DiscourseBlockTree      — 活跃块上下文
✅ TopicTree               — 主题摘要
✅ to_prompt 0-budget过滤   — 已修复

⚠️ ContextCompressor       — 增量压缩未触发 (代码有, engine未调)
⚠️ Pruner                  — 上下文剪枝未触发
⚠️ LOGICAL_LEAP → Subgraph — PCR 信号未接
⚠️ ContextWindow TTL       — 时间衰减未激活

有效实现率: ~80%
```

---

## 九、剩余差距

| 差距 | 工作量 | 
|------|:---:|
| ContextCompressor 接入 | 10行 |
| Pruner 接入 | 5行 |
| LOGICAL_LEAP → Subgraph | 5行 |
| ContextWindow TTL | 5行 |

**总计: ~25 行**
