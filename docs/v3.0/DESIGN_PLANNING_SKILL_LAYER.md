# DialogMesh PlanningSkill Layer 架构设计 v1.5

> **文档状态**: 设计冻结 (Design Freeze)  
> **版本**: v1.5  
> **日期**: 2026-07-19  
> **依赖**: [动态任务规划 v1.0](DESIGN_TASK_PLANNING_DYNAMIC.md)  
> **核心命题**: **Planning ≠ Tools**——任务规划方法与工具集是独立正交的抽象层，二者应解耦设计。

---

## 目录

- [1. 动机：为什么需要 PlanningSkill Layer](#1-动机为什么需要-planningskill-layer)
- [2. 核心概念：正交分层](#2-核心概念正交分层)
- [3. 通用规划原语库 (Planning Primitives)](#3-通用规划原语库-planning-primitives)
- [4. PlanningSkill 定义与结构](#4-planningskill-定义与结构)
- [5. Mixed Planning Engine（混合编排引擎）](#5-mixed-planning-engine混合编排引擎)
- [6. 三种运行模式详解](#6-三种运行模式详解)
- [7. 与 ToolRegistry 的集成接口](#7-与-toolregistry-的集成接口)
- [8. 与认知-画像 v2.0 的联动](#8-与认知-画像-v20-的联动)
- [9. 完整数据流](#9-完整数据流)
- [10. 实现路线图](#10-实现路线图)
- [11. 附录](#11-附录)

---

## 1. 动机：为什么需要 PlanningSkill Layer

### 1.1 当前设计的隐含假设及其失效

在 [动态任务规划 v1.0](DESIGN_TASK_PLANNING_DYNAMIC.md) 中，`DynamicPlanner` 的设计隐含了一个关键假设：

> **假设**：只要 LLM 看到了工具列表，它就能自主推理出合理的任务规划。

这个假设在以下场景中会系统性失效：

| 场景 | 问题描述 | 失效原因 |
|------|---------|---------|
| **工具孤岛** | 用户只提供了 20 个零散的 API，无业务关联 | LLM 缺乏领域上下文，只能做线性顺序调用，无法理解业务逻辑链 |
| **业务领域知识** | 用户 API 是"搜索→比价→库存检查→下单→支付确认"的电商流程 | 无预定义流程，LLM 可能漏掉"库存检查"或"优惠券验证"等关键步骤 |
| **复杂认知模式** | 任务为"帮我写一篇论文" | 纯 LLM 可能分解为线性步骤（选题→写大纲→写正文），缺少"并行检索→交叉验证→引用一致性检查"的认知模式 |
| **合规与约束** | 金融/医疗领域的 API 调用 | 必须遵循特定顺序（如"先风险评估再执行"），LLM 无法从工具列表推断合规顺序 |
| **零工具场景** | 用户只提供了 1 个 API，要求完成复杂任务 | 缺乏多工具协作，LLM 只能重复调用同一个 API，无策略可言 |

### 1.2 用户的核心诉求

> "爬取大量的 skill，抽象整理为一套较为全面的任务规划逻辑，然后其他用户可以选择只提供 API 和对应功能，不提供 skill，然后 LLM 更具那个全面的任务规划逻辑与自我判断搭配 API 的信息去进行规划任务。"

这句话拆解为三个核心需求：

1. **通用规划逻辑沉淀**：系统应内置一套跨领域、跨任务的通用规划方法（如 ReAct、CoT、搜索-验证-执行），不依赖特定 API。
2. **即插即用的 Skill 扩展**：用户可以选择只提供 API（无 Skill），系统用通用规划逻辑兜底；也可以提供 Skill（领域模板），增强特定场景的规划质量。
3. **混合编排机制**：系统能自动判断何时用通用逻辑、何时用 Skill 模板，或者将两者混合使用。

### 1.3 文献与工程验证

| 来源 | 核心洞察 | 在本设计中的映射 |
|------|---------|---------------|
| **ReAct** (Yao et al., 2022, 1000+ citations) | Thought → Action → Observation 的循环推理 | 通用规划原语 `ReAct Loop` |
| **CoT** (Wei et al., 2022, 10000+ citations) | 链式思维，逐步推理 | 通用规划原语 `Chain-of-Thought` |
| **Tree-of-Thought** (Yao et al., 2023) | 多分支探索，回溯选择最优路径 | 通用规划原语 `Tree-of-Thought` |
| **Plan-and-Solve** (Wang et al., 2023) | 先制定计划，再逐步执行 | 通用规划原语 `Plan-Execute-Reflect` |
| **Reflexion** (Shinn et al., 2023) | 自我反思，从失败中学习 | 通用规划原语 `Reflect-Retry` |
| **AutoGPT** (2023) | 目标分解 + 优先级排序 + 自动任务创建 | Skill 模板：`GoalDecomposition` |
| **LangGraph** (2024) | 状态图驱动的 Agent 工作流 | 混合编排引擎的底层图模型 |
| **CrewAI** (2024) | 角色分工 + 协作流程 | Skill 模板：`RoleBasedCollaboration` |
| **OpenAI Assistant** (2024) | `planning` + `code_interpreter` + `retrieval` 的分离 | 工具与规划分离的工程实践 |
| **"Understanding Planning of LLM Agents"** (Yang et al., 2024, 561 citations) | 规划能力的 5 个维度：分解、分配、排序、资源、反思 | 通用规划原语的五维分类 |

---

## 2. 核心概念：正交分层

### 2.1 Planning 与 Tools 的独立正交性

```
┌──────────────────────────────────────────────────────────────┐
│                    Planning 层 (How to plan)                 │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ 通用规划原语 │  │ 领域 Skill   │  │ 混合编排引擎        │ │
│  │ (10-20个)   │  │ (30-50个)    │  │ (Mixed Planning)    │ │
│  │              │  │              │  │                     │ │
│  │ • ReAct Loop │  │ • CRUD Flow  │  │ • Skill 匹配检测    │ │
│  │ • Chain-of-Thought│• ETL Pipeline│ │ • 置信度判断        │ │
│  │ • Plan-Execute-Reflect│• Search-Verify│• 混合编排       │ │
│  │ • Tree-of-Thought│• CustomerSupport│ │ • 动态切换        │ │
│  │ • Divide-Conquer│ • DataAnalysis │  │                     │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                              │
│  Planning 层只关心 "如何分解任务"，不关心 "用哪个工具执行"   │
└──────────────────────────────────────────────────────────────┘
                              │
                              │ 正交解耦：Planning 输出的是 TaskGraph 的
                              │ 拓扑结构（步骤、依赖、分支），工具名是占位符
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    Tool 层 (What to do)                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Built-in     │  │ API Doc      │  │ MCP              │ │
│  │ Tools        │  │ Tools        │  │ Tools            │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
│                                                              │
│  Tool 层只关心 "有哪些工具、如何调用"，不关心 "为什么选这个工具"│
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    Binding 层 (适配与填充)                    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 将 Planning 层的占位符（如 "search_tool"）绑定到          │  │
│  │ Tool 层的实际工具（如 "github_api_search_repos"）       │  │
│  │ 基于语义相似度 + 标签匹配 + 参数兼容性进行适配         │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计原则

| 原则 | 说明 | 反例（违反原则） |
|------|------|----------------|
| **Planning 不依赖具体工具** | 通用规划原语只定义"步骤类型"（如"搜索"），不指定具体工具名 | 在规划原语中硬编码 `google_search` 工具名 |
| **Skill 不依赖具体工具** | 领域模板只定义流程骨架（如"先搜索再验证"），工具名是占位符 | 在电商 Skill 中写死 `taobao_search_api` |
| **工具可独立替换** | 同一个 PlanningSkill 可以绑定到不同的工具集（如搜索用 Bing 或 Google） | 规划与工具绑定后，换工具必须重写 Skill |
| **运行时动态绑定** | 规划完成后，在 Binding 层根据实际可用的工具进行适配 | 在规划阶段就确定具体工具名，导致工具不可用时计划失败 |

### 2.3 与现有架构的对比

| 维度 | v1.0 (DynamicPlanner) | v1.5 (PlanningSkill + Mixed Engine) |
|------|----------------------|-------------------------------------|
| 规划能力来源 | 纯 LLM 自主推理 | LLM + 通用原语 + 领域 Skill 三重来源 |
| 是否依赖工具语义 | 强依赖（工具描述是 LLM 唯一输入） | 弱依赖（Planning 有独立知识库） |
| 零工具场景 | 无法规划（无工具 = 无计划） | 可用（通用原语提供纯推理框架） |
| 领域深度 | 浅（依赖 LLM 泛化能力） | 深（Skill 模板提供领域知识） |
| 可扩展性 | 新增工具即可用 | 新增工具 + 可选 Skill 增强 |
| 混合能力 | 无（纯动态） | 有（通用原语 + Skill 模板混合） |

---

## 3. 通用规划原语库 (Planning Primitives)

### 3.1 设计哲学

通用规划原语（Planning Primitives）是**跨领域、跨任务、不依赖具体工具**的认知模式抽象。它们回答的问题是：

> "面对一个目标，人类/Agent 应该如何系统地思考、分解、执行、验证？"

这些原语不是从工具中"爬取"的，而是从**认知科学**（问题解决理论）、**LLM Agent 研究**（ReAct/CoT/ToT）和**软件工程**（设计模式）中抽象出来的。

### 3.2 原语分类：五维模型

基于文献 "Understanding Planning of LLM Agents"（Yang et al., 2024）的五维框架，我们将通用规划原语分为 5 大类：

```
Planning Primitives
├── [分解] Decomposition          → 如何将大目标拆分为小步骤
│   ├── SequentialDecomposition   → 线性顺序分解（步骤 A → B → C）
│   ├── HierarchicalDecomposition → 层级分解（任务 → 子任务 → 原子操作）
│   └── DivideConquer             → 分治（拆分为独立子问题，分别解决）
│
├── [分配] Allocation             → 如何分配资源/角色到子任务
│   ├── SingleAgent               → 单 Agent 串行执行
│   ├── ParallelMap               → 并行映射（多任务同时执行）
│   └── RoleBasedCollaboration    → 角色分工（研究员、编码者、审核者）
│
├── [排序] Ordering               → 如何确定步骤的执行顺序
│   ├── SequentialFlow            → 顺序流（A → B → C）
│   ├── ConditionalBranch         → 条件分支（if X then A else B）
│   ├── LoopUntil                 → 循环直到（while not done）
│   └── PriorityQueue             → 优先级队列（按重要性排序）
│
├── [资源] ResourceManagement     → 如何利用外部资源
│   ├── SearchRetrieve            → 搜索-检索（从外部获取信息）
│   ├── SearchVerifyExecute       → 搜索-验证-执行（验证信息后再行动）
│   └── MemoryAugmented           → 记忆增强（利用历史经验）
│
└── [反思] Reflection             → 如何评估和改进计划
    ├── PlanExecuteReflect        → 计划-执行-反思（PDCA 循环）
    ├── TreeOfThought             → 树状思考（多分支探索 + 回溯）
    ├── ReflectRetry                → 反思-重试（从失败中学习）
    └── EarlyTermination            → 早期终止（发现不可行时及时停止）
```

### 3.3 原语详细定义

以下每个原语定义为一个可执行的 `PlanningPrimitive` 对象，包含：
- 元信息（名称、描述、适用场景）
- 拓扑模板（TaskGraph 的骨架结构）
- 参数化接口（占位符，等待 Binding 层填充）
- 约束规则（前置条件、后置条件、不变量）

---

#### 原语 P1: SequentialDecomposition

```python
@dataclass
class SequentialDecomposition(PlanningPrimitive):
    """
    线性顺序分解：将目标拆分为依次执行的步骤。
    
    适用场景：
    - 步骤之间有明确依赖（后一步需要前一步的结果）
    - 无分支、无循环的简单流程
    - 新手用户或低风险任务
    
    拓扑模板：
        [Step 1] → [Step 2] → [Step 3] → ... → [Step N]
    
    示例：写论文 = 选题 → 查文献 → 写大纲 → 写正文 → 校对
    """
    name: str = "SequentialDecomposition"
    description: str = "将目标分解为线性顺序执行的步骤"
    
    # 参数化：步骤列表，每个步骤是占位符
    steps: List[PrimitiveStep] = field(default_factory=list)
    
    def generate_skeleton(self) -> TaskGraph:
        """生成 TaskGraph 骨架（工具名为占位符）。"""
        graph = TaskGraph()
        prev_node = None
        for i, step in enumerate(self.steps):
            node = TaskNode(
                name=step.name,
                goal=step.goal,
                strategy=step.strategy,
                tool_name=step.tool_placeholder,  # 占位符，如 "search_tool"
                layer=step.layer,
                tags=set(step.tags),
            )
            graph.add_node(node)
            if prev_node:
                graph.add_dependency(prev_node.id, node.id, DependencyType.SEQUENTIAL)
            prev_node = node
        return graph
```

---

#### 原语 P2: PlanExecuteReflect

```python
@dataclass
class PlanExecuteReflect(PlanningPrimitive):
    """
    计划-执行-反思循环：PDCA 的 Agent 版本。
    
    适用场景：
    - 任务需要多轮迭代才能完善
    - 每一步执行后需要评估效果
    - 代码生成、创意写作、策略优化
    
    拓扑模板：
        [Plan] → [Execute] → [Evaluate] → [Reflect] → [Iterate?] → [Plan] ...
                     ↓ (success)
                   [Final Output]
    
    约束：
    - max_iterations: 最大循环次数（默认 5）
    - improvement_threshold: 改进阈值（低于此值则终止）
    """
    name: str = "PlanExecuteReflect"
    description: str = "计划→执行→评估→反思→迭代的循环"
    
    max_iterations: int = 5
    improvement_threshold: float = 0.1
    
    def generate_skeleton(self) -> TaskGraph:
        graph = TaskGraph()
        
        # Plan 节点
        plan_node = TaskNode(name="plan", goal="制定初始计划", tool_name="plan_tool")
        graph.add_node(plan_node)
        
        # Execute 节点
        exec_node = TaskNode(name="execute", goal="执行计划", tool_name="execute_tool")
        graph.add_node(exec_node)
        graph.add_dependency(plan_node.id, exec_node.id, DependencyType.SEQUENTIAL)
        
        # Evaluate 节点
        eval_node = TaskNode(name="evaluate", goal="评估执行结果", tool_name="evaluate_tool")
        graph.add_node(eval_node)
        graph.add_dependency(exec_node.id, eval_node.id, DependencyType.SEQUENTIAL)
        
        # Reflect 节点
        reflect_node = TaskNode(name="reflect", goal="反思改进方向", tool_name="reflect_tool")
        graph.add_node(reflect_node)
        graph.add_dependency(eval_node.id, reflect_node.id, DependencyType.SEQUENTIAL)
        
        # 条件分支：是否继续迭代？
        # 用 CONDITIONAL 边表示
        graph.add_dependency(
            reflect_node.id, plan_node.id,
            DependencyType.CONDITIONAL,
            condition="iteration < max_iterations and improvement > improvement_threshold"
        )
        
        # 终止节点（迭代结束）
        finish_node = TaskNode(name="finalize", goal="输出最终结果", tool_name="finish_tool")
        graph.add_node(finish_node)
        graph.add_dependency(
            reflect_node.id, finish_node.id,
            DependencyType.CONDITIONAL,
            condition="iteration >= max_iterations or improvement <= improvement_threshold"
        )
        
        return graph
```

---

#### 原语 P3: SearchVerifyExecute

```python
@dataclass
class SearchVerifyExecute(PlanningPrimitive):
    """
    搜索-验证-执行：信息驱动决策的标准模式。
    
    适用场景：
    - 需要基于外部信息做决策（如"查找最佳方案"）
    - 信息质量不确定，需要验证
    - 数据查询、竞品分析、故障诊断
    
    拓扑模板：
        [Search] → [Verify] → [Execute]
                    ↓ (info insufficient)
                  [Re-search]
    
    约束：
    - max_search_rounds: 最大搜索轮数（默认 3）
    - verification_criteria: 验证通过标准
    """
    name: str = "SearchVerifyExecute"
    description: str = "先搜索信息，验证可靠性，再执行决策"
    
    max_search_rounds: int = 3
    verification_criteria: str = "cross_reference_min_2_sources"
    
    def generate_skeleton(self) -> TaskGraph:
        graph = TaskGraph()
        
        search_node = TaskNode(name="search", goal="搜索相关信息", tool_name="search_tool")
        verify_node = TaskNode(name="verify", goal="验证信息可靠性", tool_name="verify_tool")
        execute_node = TaskNode(name="execute", goal="基于验证后的信息执行", tool_name="execute_tool")
        
        graph.add_node(search_node)
        graph.add_node(verify_node)
        graph.add_node(execute_node)
        
        graph.add_dependency(search_node.id, verify_node.id, DependencyType.SEQUENTIAL)
        
        # 验证通过 → 执行
        graph.add_dependency(
            verify_node.id, execute_node.id,
            DependencyType.CONDITIONAL,
            condition="verification_passed"
        )
        
        # 验证失败 → 重新搜索
        graph.add_dependency(
            verify_node.id, search_node.id,
            DependencyType.CONDITIONAL,
            condition="not verification_passed and search_round < max_search_rounds"
        )
        
        # 兜底：如果多次搜索仍失败，询问用户
        fallback_node = TaskNode(
            name="ask_user_fallback",
            goal="信息无法验证，询问用户",
            tool_name="ask_user_tool",
        )
        graph.add_node(fallback_node)
        graph.add_dependency(
            verify_node.id, fallback_node.id,
            DependencyType.CONDITIONAL,
            condition="not verification_passed and search_round >= max_search_rounds"
        )
        
        return graph
```

---

#### 原语 P4: TreeOfThought

```python
@dataclass
class TreeOfThought(PlanningPrimitive):
    """
    树状思考：多分支探索，评估后选择最优路径。
    
    适用场景：
    - 有多种可能的解决方案，需要评估比较
    - 决策空间较大，需要系统性探索
    - 策略选择、方案优化、创意生成
    
    拓扑模板：
        [Root Problem]
             │
       ┌────┼────┐
       ▼    ▼    ▼
    [Branch A] [Branch B] [Branch C]
       │        │        │
       ▼        ▼        ▼
    [Evaluate] [Evaluate] [Evaluate]
       │        │        │
       └────────┼────────┘
                ▼
          [Select Best]
                │
                ▼
           [Execute Best]
    
    约束：
    - max_branches: 最大分支数（默认 3）
    - evaluation_criteria: 评估维度（如成本、质量、速度）
    """
    name: str = "TreeOfThought"
    description: str = "生成多分支方案，评估后选择最优路径"
    
    max_branches: int = 3
    evaluation_criteria: List[str] = field(default_factory=lambda: ["cost", "quality", "speed"])
    
    def generate_skeleton(self) -> TaskGraph:
        graph = TaskGraph()
        
        # 根节点：问题定义
        root = TaskNode(name="define_problem", goal="明确问题", tool_name="analysis_tool")
        graph.add_node(root)
        
        # 分支生成节点
        branches = []
        for i in range(self.max_branches):
            branch = TaskNode(
                name=f"branch_{i}",
                goal=f"生成方案 {i+1}",
                tool_name="generate_solution_tool",
            )
            graph.add_node(branch)
            graph.add_dependency(root.id, branch.id, DependencyType.PARALLEL)
            branches.append(branch)
        
        # 评估节点
        evaluate = TaskNode(name="evaluate", goal="评估所有方案", tool_name="evaluate_tool")
        graph.add_node(evaluate)
        for branch in branches:
            graph.add_dependency(branch.id, evaluate.id, DependencyType.SEQUENTIAL)
        
        # 选择最优
        select = TaskNode(name="select_best", goal="选择最优方案", tool_name="select_tool")
        graph.add_node(select)
        graph.add_dependency(evaluate.id, select.id, DependencyType.SEQUENTIAL)
        
        # 执行
        execute = TaskNode(name="execute_best", goal="执行最优方案", tool_name="execute_tool")
        graph.add_node(execute)
        graph.add_dependency(select.id, execute.id, DependencyType.SEQUENTIAL)
        
        return graph
```

---

#### 原语 P5: DivideConquer

```python
@dataclass
class DivideConquer(PlanningPrimitive):
    """
    分治：将问题拆分为独立子问题，分别解决后合并。
    
    适用场景：
    - 问题可分解为独立的子问题
    - 子问题之间无依赖，可并行
    - 大数据处理、批量任务、分布式计算
    
    拓扑模板：
        [Divide] → [Subtask A] → [Merge]
               → [Subtask B] →
               → [Subtask C] →
    
    约束：
    - subtask_count: 子问题数量
    - merge_strategy: 合并策略（如 concat, sum, vote）
    """
    name: str = "DivideConquer"
    description: str = "分治：拆分、并行解决、合并结果"
    
    subtask_count: int = 3
    merge_strategy: str = "concat"
    
    def generate_skeleton(self) -> TaskGraph:
        graph = TaskGraph()
        
        divide = TaskNode(name="divide", goal="拆分为子问题", tool_name="divide_tool")
        graph.add_node(divide)
        
        subtasks = []
        for i in range(self.subtask_count):
            sub = TaskNode(
                name=f"subtask_{i}",
                goal=f"解决子问题 {i+1}",
                tool_name="subtask_tool",
            )
            graph.add_node(sub)
            graph.add_dependency(divide.id, sub.id, DependencyType.PARALLEL)
            subtasks.append(sub)
        
        merge = TaskNode(name="merge", goal="合并子结果", tool_name="merge_tool")
        graph.add_node(merge)
        for sub in subtasks:
            graph.add_dependency(sub.id, merge.id, DependencyType.SEQUENTIAL)
        
        return graph
```

### 3.4 原语库的完整清单

| ID | 原语名称 | 类别 | 适用场景 | 复杂度 |
|----|---------|------|---------|--------|
| P1 | SequentialDecomposition | 分解 | 线性流程 | ⭐ |
| P2 | HierarchicalDecomposition | 分解 | 复杂任务层级拆分 | ⭐⭐ |
| P3 | DivideConquer | 分解 | 可并行子问题 | ⭐⭐ |
| P4 | SingleAgent | 分配 | 单 Agent 串行 | ⭐ |
| P5 | ParallelMap | 分配 | 多任务并行 | ⭐⭐ |
| P6 | RoleBasedCollaboration | 分配 | 多角色协作 | ⭐⭐⭐ |
| P7 | SequentialFlow | 排序 | 简单顺序 | ⭐ |
| P8 | ConditionalBranch | 排序 | 条件分支 | ⭐⭐ |
| P9 | LoopUntil | 排序 | 循环迭代 | ⭐⭐ |
| P10 | PriorityQueue | 排序 | 优先级排序 | ⭐⭐ |
| P11 | SearchRetrieve | 资源 | 信息检索 | ⭐ |
| P12 | SearchVerifyExecute | 资源 | 信息驱动决策 | ⭐⭐⭐ |
| P13 | MemoryAugmented | 资源 | 利用历史经验 | ⭐⭐ |
| P14 | PlanExecuteReflect | 反思 | 迭代优化 | ⭐⭐⭐ |
| P15 | TreeOfThought | 反思 | 多方案探索 | ⭐⭐⭐ |
| P16 | ReflectRetry | 反思 | 失败重试 | ⭐⭐ |
| P17 | EarlyTermination | 反思 | 及时止损 | ⭐⭐ |

---

## 4. PlanningSkill 定义与结构

### 4.1 什么是 PlanningSkill

**PlanningSkill** 是**领域特定的规划模板**，它基于通用规划原语组合而成，并填充了领域知识。与通用原语的区别：

| 维度 | 通用规划原语 | 领域 PlanningSkill |
|------|------------|------------------|
| 领域绑定 | 无（跨领域通用） | 有（特定领域） |
| 工具依赖 | 无（占位符） | 弱（推荐工具标签） |
| 知识来源 | 认知科学 + 算法 | 行业最佳实践 + 用户经验 |
| 可复用性 | 高（任何任务） | 中（同领域任务） |
| 数量 | 少（约 17 个） | 多（可扩展至数百） |

### 4.2 PlanningSkill 的数据模型

```python
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
from enum import Enum

class SkillLevel(Enum):
    """Skill 的详细程度。"""
    SKELETON = "skeleton"      # 仅流程骨架，无具体步骤
    STANDARD = "standard"      # 标准模板，有步骤但无工具绑定
    DETAILED = "detailed"      # 详细模板，包含推荐工具标签和参数提示

@dataclass
class PlanningSkill:
    """
    领域规划 Skill——基于通用原语组合，填充领域知识。
    
    核心字段：
    - skill_id: 唯一标识（如 "ecommerce_order_flow"）
    - primitives: 使用的通用原语列表（如 [P12, P8, P7]）
    - domain_tags: 领域标签（如 {"ecommerce", "order", "payment"}）
    - step_templates: 步骤模板（占位符形式的 TaskNode）
    - tool_hints: 推荐工具标签（非强制，用于 Binding 层参考）
    - constraints: 领域约束（如 "必须先检查库存再下单"）
    """
    
    # ── 标识 ──────────────────────────────────────────────
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    
    # ── 领域 ──────────────────────────────────────────────
    domain_tags: Set[str] = field(default_factory=set)
    intent_categories: Set[str] = field(default_factory=set)  # 匹配的意图类别
    
    # ── 原语组合 ───────────────────────────────────────────
    primitives: List[str] = field(default_factory=list)  # 如 ["SearchVerifyExecute", "ConditionalBranch"]
    
    # ── 步骤模板 ───────────────────────────────────────────
    # 每个 step_template 是一个 TaskNode 的模板，工具名是占位符
    step_templates: List[Dict[str, Any]] = field(default_factory=list)
    
    # ── 工具提示（非强制绑定）──────────────────────────────
    # tool_hints 告诉 Binding 层："这个步骤建议用带什么标签的工具"
    tool_hints: Dict[str, List[str]] = field(default_factory=dict)
    # 示例：{"search_step": ["search", "api", "web"], "verify_step": ["verify", "check"]}
    
    # ── 约束 ───────────────────────────────────────────────
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    # 示例：
    # [{"type": "precedence", "before": "order_step", "after": "inventory_check"}]
    # [{"type": "invariant", "condition": "total_price >= 0"}]
    
    # ── 详细程度 ───────────────────────────────────────────
    level: SkillLevel = SkillLevel.STANDARD
    
    # ── 元数据 ─────────────────────────────────────────────
    author: Optional[str] = None
    source: Optional[str] = None  # 来源（如 "open_source", "user_upload", "system_generated"])
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: float = field(default_factory=time.time)
    
    # ── 方法 ───────────────────────────────────────────────
    
    def generate_skeleton(self) -> TaskGraph:
        """基于 step_templates 生成 TaskGraph 骨架（工具名为占位符）。"""
        graph = TaskGraph()
        
        for step_tmpl in self.step_templates:
            node = TaskNode(
                name=step_tmpl.get("name", "unnamed"),
                goal=step_tmpl.get("goal", ""),
                strategy=step_tmpl.get("strategy", ""),
                tool_name=step_tmpl.get("tool_placeholder", "unknown_tool"),
                layer=step_tmpl.get("layer", 2),
                tags=set(step_tmpl.get("tags", [])),
                fallback_nodes=step_tmpl.get("fallback_nodes", []),
            )
            graph.add_node(node)
        
        # 添加依赖边（从 step_templates 的 dependencies 字段）
        for step_tmpl in self.step_templates:
            node_id = self._find_node_id(graph, step_tmpl["name"])
            for dep in step_tmpl.get("dependencies", []):
                dep_id = self._find_node_id(graph, dep["target"])
                if dep_id:
                    graph.add_dependency(
                        node_id, dep_id,
                        DependencyType(dep.get("type", "sequential")),
                        dep.get("condition")
                    )
        
        return graph
    
    def _find_node_id(self, graph: TaskGraph, name: str) -> Optional[str]:
        for node in graph.nodes.values():
            if node.name == name:
                return node.id
        return None
    
    def match_intent(self, intent: Intent) -> float:
        """
        计算 Skill 与用户意图的匹配度。
        
        返回 0.0-1.0 的匹配分数，用于 Mixed Planning Engine 的 Skill 选择。
        """
        score = 0.0
        
        # 1. 意图类别匹配
        if intent.category.value in self.intent_categories:
            score += 0.4
        
        # 2. 领域标签匹配（基于意图实体的标签）
        entity_tags = set()
        for e in intent.entities:
            entity_tags.update(e.metadata.get("tags", []))
        if self.domain_tags.intersection(entity_tags):
            score += 0.3
        
        # 3. 关键词匹配（意图文本与 Skill 描述）
        intent_words = set(intent.normalized_input.lower().split())
        skill_words = set(self.description.lower().split())
        overlap = len(intent_words.intersection(skill_words))
        score += min(0.3, overlap / max(len(intent_words), 1) * 0.3)
        
        return min(1.0, score)
```

### 4.3 预置领域 Skill 示例

#### Skill S1: 电商下单流程 (E-commerce Order Flow)

```yaml
skill_id: "ecommerce_order_flow"
name: "电商下单流程"
description: "完整的电商下单流程，包括搜索、比价、库存检查、下单、支付"
domain_tags: ["ecommerce", "order", "shopping", "payment"]
intent_categories: ["search_product", "place_order", "checkout"]
primitives: ["SearchVerifyExecute", "ConditionalBranch", "SequentialFlow"]
level: "detailed"

step_templates:
  - name: "search_product"
    goal: "搜索用户想要的商品"
    strategy: "use_search_api"
    tool_placeholder: "search_tool"
    layer: 2
    tags: ["search", "product"]
    dependencies: []

  - name: "compare_price"
    goal: "比较多个商家的价格"
    strategy: "fetch_multiple_prices"
    tool_placeholder: "compare_tool"
    layer: 2
    tags: ["compare", "price"]
    dependencies:
      - target: "search_product"
        type: "sequential"

  - name: "check_inventory"
    goal: "检查选中商品的库存"
    strategy: "query_inventory_api"
    tool_placeholder: "inventory_tool"
    layer: 2
    tags: ["inventory", "check"]
    dependencies:
      - target: "compare_price"
        type: "sequential"

  - name: "apply_coupon"
    goal: "检查并应用优惠券"
    strategy: "validate_and_apply_coupon"
    tool_placeholder: "coupon_tool"
    layer: 2
    tags: ["coupon", "discount"]
    dependencies:
      - target: "check_inventory"
        type: "conditional"
        condition: "inventory > 0"

  - name: "place_order"
    goal: "创建订单"
    strategy: "create_order_api"
    tool_placeholder: "order_tool"
    layer: 2
    tags: ["order", "create"]
    dependencies:
      - target: "apply_coupon"
        type: "sequential"

  - name: "process_payment"
    goal: "处理支付"
    strategy: "call_payment_gateway"
    tool_placeholder: "payment_tool"
    layer: 3
    tags: ["payment", "transaction"]
    dependencies:
      - target: "place_order"
        type: "sequential"

  - name: "confirm_order"
    goal: "确认订单并发送通知"
    strategy: "send_confirmation"
    tool_placeholder: "notification_tool"
    layer: 3
    tags: ["notification", "confirm"]
    dependencies:
      - target: "process_payment"
        type: "sequential"

tool_hints:
  search_tool: ["search", "product", "catalog"]
  compare_tool: ["compare", "price", "aggregate"]
  inventory_tool: ["inventory", "stock", "availability"]
  coupon_tool: ["coupon", "discount", "promotion"]
  order_tool: ["order", "checkout", "create"]
  payment_tool: ["payment", "transaction", "pay"]
  notification_tool: ["notify", "email", "sms"]

constraints:
  - type: "precedence"
    before: "place_order"
    after: "check_inventory"
    reason: "必须先确认库存再下单"
  - type: "precedence"
    before: "process_payment"
    after: "place_order"
    reason: "必须先创建订单再支付"
  - type: "invariant"
    condition: "order_total >= 0"
    reason: "订单金额不能为负"
```

#### Skill S2: 数据分析流程 (Data Analysis Pipeline)

```yaml
skill_id: "data_analysis_pipeline"
name: "数据分析流程"
description: "从数据获取到可视化的完整数据分析流程"
domain_tags: ["data", "analysis", "visualization", "statistics"]
intent_categories: ["analyze_data", "generate_report", "visualize"]
primitives: ["DivideConquer", "PlanExecuteReflect", "SequentialFlow"]
level: "standard"

step_templates:
  - name: "acquire_data"
    goal: "获取数据源"
    tool_placeholder: "data_source_tool"
    layer: 2

  - name: "clean_data"
    goal: "清洗数据（处理缺失值、异常值）"
    tool_placeholder: "clean_tool"
    layer: 2
    dependencies:
      - target: "acquire_data"
        type: "sequential"

  - name: "explore_data"
    goal: "探索性数据分析（EDA）"
    tool_placeholder: "eda_tool"
    layer: 2
    dependencies:
      - target: "clean_data"
        type: "sequential"

  - name: "analyze_data"
    goal: "执行统计分析或机器学习"
    tool_placeholder: "analysis_tool"
    layer: 2
    dependencies:
      - target: "explore_data"
        type: "sequential"

  - name: "visualize_results"
    goal: "生成可视化图表"
    tool_placeholder: "viz_tool"
    layer: 3
    dependencies:
      - target: "analyze_data"
        type: "sequential"

  - name: "generate_report"
    goal: "生成分析报告"
    tool_placeholder: "report_tool"
    layer: 3
    dependencies:
      - target: "visualize_results"
        type: "sequential"
```

#### Skill S3: 代码生成与调试 (Code Generation & Debug)

```yaml
skill_id: "code_generation_debug"
name: "代码生成与调试"
description: "从需求到可运行代码的完整流程，包括生成、测试、调试、优化"
domain_tags: ["code", "programming", "debug", "test"]
intent_categories: ["write_code", "debug_code", "refactor"]
primitives: ["PlanExecuteReflect", "TreeOfThought", "ReflectRetry"]
level: "detailed"

step_templates:
  - name: "analyze_requirement"
    goal: "分析需求，提取功能和约束"
    tool_placeholder: "analysis_tool"
    layer: 1

  - name: "design_solution"
    goal: "设计解决方案架构"
    tool_placeholder: "design_tool"
    layer: 1
    dependencies:
      - target: "analyze_requirement"
        type: "sequential"

  - name: "generate_code"
    goal: "生成代码实现"
    tool_placeholder: "code_gen_tool"
    layer: 2
    dependencies:
      - target: "design_solution"
        type: "sequential"

  - name: "write_tests"
    goal: "编写测试用例"
    tool_placeholder: "test_gen_tool"
    layer: 2
    dependencies:
      - target: "generate_code"
        type: "parallel"

  - name: "run_tests"
    goal: "运行测试并收集结果"
    tool_placeholder: "test_run_tool"
    layer: 3
    dependencies:
      - target: "write_tests"
        type: "sequential"

  - name: "evaluate_coverage"
    goal: "评估测试覆盖率"
    tool_placeholder: "coverage_tool"
    layer: 3
    dependencies:
      - target: "run_tests"
        type: "sequential"

  - name: "reflect_and_fix"
    goal: "反思失败原因并修复"
    tool_placeholder: "fix_tool"
    layer: 3
    dependencies:
      - target: "evaluate_coverage"
        type: "conditional"
        condition: "coverage < 0.8 or tests_failed"

  - name: "optimize_code"
    goal: "优化代码性能"
    tool_placeholder: "optimize_tool"
    layer: 3
    dependencies:
      - target: "reflect_and_fix"
        type: "conditional"
        condition: "all_tests_passed"
```

### 4.4 Skill 的来源与生态

| 来源 | 数量预估 | 质量 | 维护方式 |
|------|---------|------|---------|
| **系统预置** | 30-50 个 | 高 | 官方维护，随版本更新 |
| **开源社区** | 可扩展 | 中 | 社区贡献，审核机制 |
| **用户自定义** | 不限 | 可变 | 用户自维护，可分享 |
| **LLM 自动生成** | 按需 | 中 | 基于通用原语 + 领域描述自动生成 |
| **从现有工作流导入** | 不限 | 高 | 从 LangGraph/CrewAI 等框架转换 |

**核心原则**：系统不维护海量 Skill，而是维护**17 个高质量通用原语**和**30-50 个常见领域模板**。用户自定义 Skill 可以上传、分享、复用。

---

## 5. Mixed Planning Engine（混合编排引擎）

### 5.1 核心职责

Mixed Planning Engine 是 PlanningSkill Layer 的**中央调度器**，负责：

1. **Skill 检测**：判断用户意图是否与某个 Skill 匹配
2. **模式选择**：决定用纯动态规划、Skill 增强规划、还是混合模式
3. **混合编排**：将 Skill 模板与 LLM 动态推理融合，生成最终 TaskGraph
4. **回退机制**：当 Skill 不适用或执行失败时，自动切换模式

### 5.2 三种运行模式的判定逻辑

```python
class MixedPlanningEngine:
    """
    混合编排引擎——自动选择最优规划模式。
    """
    
    def __init__(
        self,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        llm_provider,
        primitive_library: PrimitiveLibrary,
    ):
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._llm = llm_provider
        self._primitives = primitive_library
    
    def plan(
        self,
        intent: Intent,
        intent_context: IntentContext,
        shortlisted_tools: ShortlistResult,
    ) -> PlanResult:
        """
        主入口：根据条件自动选择规划模式。
        
        返回 PlanResult 包含：
        - mode: 使用的模式（DYNAMIC / SKILL_ENHANCED / MIXED）
        - task_graph: 生成的 TaskGraph
        - skill_used: 使用的 Skill（如果有）
        - primitives_used: 使用的通用原语
        - confidence: 规划置信度
        """
        # 步骤 1: 检测匹配的 Skill
        matched_skills = self._detect_matching_skills(intent)
        
        # 步骤 2: 根据匹配度和条件选择模式
        mode = self._select_mode(intent, intent_context, matched_skills)
        
        # 步骤 3: 按模式生成计划
        if mode == PlanningMode.DYNAMIC:
            task_graph = self._pure_dynamic_plan(intent, intent_context, shortlisted_tools)
        elif mode == PlanningMode.SKILL_ENHANCED:
            task_graph = self._skill_enhanced_plan(intent, matched_skills[0], shortlisted_tools)
        elif mode == PlanningMode.MIXED:
            task_graph = self._mixed_plan(intent, matched_skills[0], intent_context, shortlisted_tools)
        else:
            task_graph = self._fallback_plan(intent)
        
        return PlanResult(
            mode=mode,
            task_graph=task_graph,
            skill_used=matched_skills[0] if matched_skills else None,
            primitives_used=self._extract_primitives(task_graph),
            confidence=self._estimate_confidence(task_graph, mode),
        )
    
    def _detect_matching_skills(self, intent: Intent) -> List[Tuple[PlanningSkill, float]]:
        """
        检测与用户意图匹配的 Skill，按匹配度排序。
        
        匹配算法：
        1. 意图类别精确匹配（权重 0.4）
        2. 领域标签重叠（权重 0.3）
        3. 关键词语义相似度（权重 0.3）
        """
        scored = []
        for skill in self._skill_registry.list_skills():
            score = skill.match_intent(intent)
            if score > 0.5:  # 只保留高匹配度
                scored.append((skill, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _select_mode(
        self,
        intent: Intent,
        intent_context: IntentContext,
        matched_skills: List[Tuple[PlanningSkill, float]],
    ) -> PlanningMode:
        """
        选择规划模式的决策逻辑。
        
        决策树：
        1. 是否有高匹配 Skill（> 0.8）？
           - 是 → 检查 Skill 的详细程度
             - DETAILED → MIXED 模式（Skill 骨架 + LLM 动态填充）
             - STANDARD/SKELETON → SKILL_ENHANCED 模式（Skill 引导 + LLM 自由发挥）
           - 否 → 检查是否有中匹配 Skill（> 0.5）
             - 是 → 用户认知水平如何？
               - 高元认知（> 0.7）→ DYNAMIC 模式（用户不需要模板）
               - 低元认知 → SKILL_ENHANCED 模式（用户需要引导）
             - 否 → DYNAMIC 模式（纯 LLM 动态规划）
        """
        if matched_skills and matched_skills[0][1] > 0.8:
            skill = matched_skills[0][0]
            if skill.level == SkillLevel.DETAILED:
                return PlanningMode.MIXED
            else:
                return PlanningMode.SKILL_ENHANCED
        
        if matched_skills and matched_skills[0][1] > 0.5:
            cog = intent_context.cognitive_profile
            if cog.metacognition > 0.7:
                return PlanningMode.DYNAMIC
            else:
                return PlanningMode.SKILL_ENHANCED
        
        return PlanningMode.DYNAMIC
```

### 5.3 三种模式详解

#### 模式 A: DYNAMIC（纯动态模式）

```python
def _pure_dynamic_plan(
    self, intent: Intent, intent_context: IntentContext,
    shortlisted_tools: ShortlistResult
) -> TaskGraph:
    """
    纯动态模式：无 Skill 模板，LLM 基于通用原语自主规划。
    
    流程：
    1. 将通用原语库注入 LLM 提示词（作为"规划方法参考"）
    2. LLM 选择适合的原语组合
    3. 生成 TaskGraph（工具名是占位符）
    4. Binding 层将占位符绑定到实际工具
    """
    # 构建提示词，包含通用原语作为参考
    primitives_desc = self._primitives.describe_all()
    prompt = f"""You are a task planning agent. Create a plan using planning primitives.

## Available Planning Primitives (use as reference, not mandatory)
{primitives_desc}

## User Intent
{intent.to_dict()}

## Available Tools
{[t.to_llm_format() for t in shortlisted_tools.selected_tools]}

## Instructions
- Choose appropriate primitives from the list above
- Generate a TaskGraph with tool placeholders
- The binding layer will match placeholders to actual tools later
"""
    
    # 调用 LLM 生成计划（与 v1.0 DynamicPlanner 相同）
    return self._dynamic_planner.plan(intent, intent_context, shortlisted_tools)
```

**特点**：
- 无 Skill 依赖，始终可用
- LLM 有最大自由度
- 适合：无匹配 Skill、探索性任务、创意任务
- 风险：规划质量不稳定，可能遗漏关键步骤

#### 模式 B: SKILL_ENHANCED（Skill 增强模式）

```python
def _skill_enhanced_plan(
    self, intent: Intent,
    skill: PlanningSkill,
    shortlisted_tools: ShortlistResult,
) -> TaskGraph:
    """
    Skill 增强模式：Skill 提供流程骨架，LLM 填充具体步骤和工具。
    
    流程：
    1. 从 Skill 生成 TaskGraph 骨架（工具名为占位符）
    2. LLM 根据实际工具列表，将占位符替换为具体工具名
    3. LLM 根据意图调整步骤（如跳过不相关步骤）
    4. 输出完整 TaskGraph
    """
    # 1. 生成 Skill 骨架
    skeleton = skill.generate_skeleton()
    
    # 2. 构建提示词，要求 LLM 填充工具名和调整步骤
    prompt = f"""You are a task planning agent. Use the following Skill template as a guide.

## Skill Template
{skill.to_dict()}

## User Intent
{intent.to_dict()}

## Available Tools
{[t.to_llm_format() for t in shortlisted_tools.selected_tools]}

## Instructions
1. Use the Skill template as a guide for the overall flow
2. Replace tool placeholders with actual tools from the Available Tools list
3. Skip steps that are not relevant to the user's intent
4. Add steps if the Skill template misses something important
5. Maintain the constraints specified in the Skill
"""
    
    # 3. LLM 生成填充后的 TaskGraph
    response = self._llm.complete(prompt, json_mode=True)
    task_graph = TaskGraph.from_dict(json.loads(response))
    
    # 4. 验证约束
    self._validate_constraints(task_graph, skill.constraints)
    
    return task_graph
```

**特点**：
- Skill 提供领域知识和流程完整性保障
- LLM 有调整自由度（跳过/添加步骤）
- 适合：有匹配 Skill、需要领域知识、有合规约束的场景
- 风险：LLM 可能过度修改 Skill 模板，破坏流程完整性

#### 模式 C: MIXED（混合模式）

```python
def _mixed_plan(
    self, intent: Intent,
    skill: PlanningSkill,
    intent_context: IntentContext,
    shortlisted_tools: ShortlistResult,
) -> TaskGraph:
    """
    混合模式：Skill 提供严格骨架（不可修改），LLM 只填充工具名和参数。
    
    流程：
    1. 从 DETAILED Skill 生成完整 TaskGraph 骨架
    2. 标记"不可修改"的步骤（Skill 的核心流程）
    3. 标记"可填充"的区域（工具名、参数值）
    4. LLM 只填充可填充区域，保持骨架不变
    5. 如果用户意图与 Skill 不完全匹配，使用条件分支处理
    """
    # 1. 生成完整骨架
    skeleton = skill.generate_skeleton()
    
    # 2. 标记可填充区域
    fillable_zones = []
    for node in skeleton.nodes.values():
        if node.tool_name.endswith("_tool"):  # 占位符
            fillable_zones.append({
                "node_id": node.id,
                "placeholder": node.tool_name,
                "tool_hints": skill.tool_hints.get(node.tool_name, []),
            })
    
    # 3. 构建提示词，要求 LLM 只填充不修改
    prompt = f"""You are a task planning agent. Fill in the blanks of the following Skill template.

## Skill Template (DO NOT MODIFY THE STRUCTURE)
{skeleton.to_dict()}

## Fillable Zones
{fillable_zones}

## Available Tools
{[t.to_llm_format() for t in shortlisted_tools.selected_tools]}

## Instructions
1. ONLY replace tool placeholders with actual tools from Available Tools
2. DO NOT add, remove, or reorder steps
3. Fill in tool_params based on the user's intent and entities
4. If a placeholder cannot be matched, use "ask_user" tool
5. Maintain all dependencies and constraints
"""
    
    # 4. LLM 填充
    response = self._llm.complete(prompt, json_mode=True)
    filled_graph = TaskGraph.from_dict(json.loads(response))
    
    # 5. 验证骨架完整性（步骤不可修改）
    if not self._skeleton_matches(skeleton, filled_graph):
        # 骨架被修改，回退到 SKILL_ENHANCED 模式
        logger.warning("Skeleton modified in MIXED mode, falling back to SKILL_ENHANCED")
        return self._skill_enhanced_plan(intent, skill, shortlisted_tools)
    
    return filled_graph
```

**特点**：
- Skill 提供严格的流程完整性保障（不可修改）
- LLM 只负责工具选择和参数填充
- 适合：合规要求高、流程严格、容错低的场景（如金融、医疗）
- 风险：如果工具不匹配，可能无法完成填充

### 5.4 模式切换与回退机制

```python
class PlanResult:
    """规划结果，包含模式和回退信息。"""
    mode: PlanningMode
    task_graph: TaskGraph
    skill_used: Optional[PlanningSkill]
    primitives_used: List[str]
    confidence: float
    fallback_chain: List[PlanningMode] = field(default_factory=list)  # 回退链

class MixedPlanningEngine:
    def _execute_with_fallback(self, plan_result: PlanResult) -> ExecutionResult:
        """
        执行计划，支持模式回退。
        
        回退链：MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK
        """
        modes_to_try = [plan_result.mode] + plan_result.fallback_chain
        
        for mode in modes_to_try:
            try:
                if mode == PlanningMode.MIXED:
                    return self._execute_mixed(plan_result)
                elif mode == PlanningMode.SKILL_ENHANCED:
                    return self._execute_skill_enhanced(plan_result)
                elif mode == PlanningMode.DYNAMIC:
                    return self._execute_dynamic(plan_result)
                else:
                    return self._execute_fallback(plan_result)
            except Exception as e:
                logger.warning(f"Mode {mode.value} failed: {e}, trying next...")
                continue
        
        return ExecutionResult(False, error="All modes failed")
```

---

## 6. 三种运行模式详解

### 6.1 模式对比矩阵

| 维度 | DYNAMIC (纯动态) | SKILL_ENHANCED (Skill 增强) | MIXED (混合) |
|------|----------------|---------------------------|-------------|
| **Skill 依赖** | 无 | 有（中匹配 Skill） | 有（高匹配 DETAILED Skill） |
| **流程完整性** | 低（依赖 LLM 推理） | 中（Skill 引导 + LLM 调整） | 高（Skill 严格骨架） |
| **灵活性** | 最高 | 中高 | 低（不可修改骨架） |
| **领域深度** | 浅 | 深 | 最深 |
| **合规保障** | 无 | 弱 | 强（约束不可违反） |
| **适用场景** | 探索性、创意、无 Skill | 有 Skill 但需灵活调整 | 流程严格、合规要求高 |
| **LLM 调用成本** | 中（1 次规划） | 中（1 次规划 + 约束验证） | 低（仅填充，无结构调整） |
| **错误回退** | FALLBACK | DYNAMIC | SKILL_ENHANCED → DYNAMIC |

### 6.2 场景示例：不同模式的输出差异

**场景**：用户输入"帮我买一台笔记本电脑"

**假设可用工具**：`search_laptop`, `compare_price`, `check_inventory`, `apply_coupon`, `place_order`, `pay`

**假设可用 Skill**：`ecommerce_order_flow`（匹配度 0.9，DETAILED 级别）

| 模式 | 输出 TaskGraph | 特点 |
|------|---------------|------|
| **DYNAMIC** | 可能只生成 `search_laptop → place_order → pay`，漏掉比价和库存检查 | 自由度高，可能遗漏关键步骤 |
| **SKILL_ENHANCED** | 使用 `ecommerce_order_flow` 骨架，但 LLM 可能觉得"比价"不相关而跳过，添加"查看评价"步骤 | 有骨架引导，但可调整 |
| **MIXED** | 严格遵循 `ecommerce_order_flow` 的全部步骤，只填充工具名 | 流程完整，但可能包含用户不需要的步骤（如优惠券） |

### 6.3 自动模式选择的实际流程

```
用户输入: "帮我买一台笔记本电脑"
  │
  ▼
[IntentParser] → 意图: purchase_product, 类别: ecommerce
  │
  ▼
[SkillRegistry.detect] → 匹配 Skills:
  - ecommerce_order_flow (score: 0.92, DETAILED)
  - general_shopping (score: 0.65, STANDARD)
  │
  ▼
[MixedPlanningEngine._select_mode]
  1. 最高匹配 0.92 > 0.8 ✓
  2. Skill level = DETAILED → 选择 MIXED 模式
  │
  ▼
[MIXED 模式执行]
  1. 生成 ecommerce_order_flow 骨架（7 个步骤）
  2. 标记可填充区域（7 个 tool_placeholder）
  3. LLM 填充：
     - search_tool → search_laptop
     - compare_tool → compare_price
     - inventory_tool → check_inventory
     - coupon_tool → apply_coupon（用户可能不需要，但 Skill 要求）
     - order_tool → place_order
     - payment_tool → pay
     - notification_tool → ask_user（无匹配工具，降级为询问）
  4. 验证约束："place_order 必须在 check_inventory 之后" ✓
  │
  ▼
输出 TaskGraph（7 个节点，严格遵循电商流程）
```

---

## 7. 与 ToolRegistry 的集成接口

### 7.1 Binding 层：规划占位符到实际工具的适配

```python
class ToolBindingEngine:
    """
    工具绑定引擎——将 Planning 层的占位符绑定到 Tool 层的实际工具。
    
    绑定策略：
    1. 精确匹配：占位符名与工具名完全一致（如 "search_tool" → "search_laptop"）
    2. 标签匹配：基于 tool_hints 和工具标签的相似度匹配
    3. 语义匹配：基于描述文本的 embedding 相似度
    4. 参数兼容：检查工具的参数是否能满足步骤的需求
    5. 人工确认：低置信度绑定请求用户确认
    """
    
    def __init__(self, tool_registry: ToolRegistry, embedding_model=None):
        self._tool_registry = tool_registry
        self._embedding_model = embedding_model
    
    def bind(
        self,
        task_graph: TaskGraph,
        skill: Optional[PlanningSkill] = None,
    ) -> TaskGraph:
        """
        将 TaskGraph 中的工具占位符绑定到实际工具。
        
        返回绑定后的 TaskGraph（所有 tool_name 为实际工具名）。
        """
        bound_graph = TaskGraph.from_dict(task_graph.to_dict())
        
        for node in bound_graph.nodes.values():
            if not node.tool_name or not node.tool_name.endswith("_tool"):
                continue  # 不是占位符，跳过
            
            # 尝试绑定
            binding = self._resolve_binding(node, skill)
            if binding:
                node.tool_name = binding.tool_name
                node.tool_params = binding.params
                node.metadata["binding_confidence"] = binding.confidence
                node.metadata["binding_reason"] = binding.reason
            else:
                # 绑定失败，替换为 ask_user
                node.tool_name = "ask_user"
                node.tool_params = {
                    "question": f"需要工具来执行 '{node.name}'，但未找到匹配工具。请提供相关工具。"
                }
                node.metadata["binding_failed"] = True
        
        return bound_graph
    
    def _resolve_binding(
        self, node: TaskNode, skill: Optional[PlanningSkill]
    ) -> Optional[BindingResult]:
        """
        解析单个节点的工具绑定。
        
        策略优先级：
        1. 精确名匹配（占位符去掉 "_tool" 后缀与工具名匹配）
        2. Skill tool_hints 匹配（基于标签）
        3. 语义相似度匹配（基于描述文本）
        4. 参数兼容性检查
        """
        placeholder = node.tool_name
        candidates = []
        
        # 1. 精确名匹配
        base_name = placeholder.replace("_tool", "")
        for tool_name in self._tool_registry._tools.keys():
            if base_name in tool_name.lower():
                candidates.append((tool_name, 0.9, "exact_match"))
        
        # 2. Skill tool_hints 匹配
        if skill:
            hints = skill.tool_hints.get(placeholder, [])
            for tool_name, reg in self._tool_registry._tools.items():
                if reg.schema.tags.intersection(set(hints)):
                    candidates.append((tool_name, 0.7, "skill_hint"))
        
        # 3. 语义相似度匹配
        if self._embedding_model:
            node_desc = f"{node.name} {node.goal}"
            for tool_name, reg in self._tool_registry._tools.items():
                sim = self._embedding_model.similarity(node_desc, reg.schema.description)
                if sim > 0.7:
                    candidates.append((tool_name, sim, "semantic_similarity"))
        
        if not candidates:
            return None
        
        # 选择得分最高的
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_name, best_score, best_reason = candidates[0]
        
        # 4. 参数兼容性检查
        schema = self._tool_registry.get_schema(best_name)
        if schema and node.tool_params:
            # 检查提供的参数是否满足 schema
            required = set(schema.required_params)
            provided = set(node.tool_params.keys())
            if required.issubset(provided):
                return BindingResult(best_name, node.tool_params, best_score, best_reason)
        
        return BindingResult(best_name, {}, best_score, best_reason)
```

### 7.2 与 ToolShortlister 的协同

```python
class EnhancedToolShortlister(ToolShortlister):
    """
    增强版工具筛选器——考虑 PlanningSkill 的 tool_hints。
    
    在 v1.0 的基础上，如果检测到匹配的 Skill，
    优先保留 Skill 中提到的工具标签对应的工具。
    """
    
    def shortlist(
        self,
        intent: Intent,
        intent_context: IntentContext,
        registry: ToolRegistry,
        skill: Optional[PlanningSkill] = None,  # 新增参数
    ) -> ShortlistResult:
        
        # 1. 先执行标准筛选
        result = super().shortlist(intent, intent_context, registry)
        
        # 2. 如果提供了 Skill，根据 tool_hints 调整排序
        if skill:
            result = self._boost_by_skill_hints(result, skill, registry)
        
        return result
    
    def _boost_by_skill_hints(
        self, result: ShortlistResult, skill: PlanningSkill, registry: ToolRegistry
    ) -> ShortlistResult:
        """根据 Skill 的 tool_hints 提升相关工具的排名。"""
        # 收集所有 tool_hints 中的标签
        all_hint_tags = set()
        for tags in skill.tool_hints.values():
            all_hint_tags.update(tags)
        
        # 提升匹配标签的工具得分
        for tool in result.selected_tools:
            if tool.tags.intersection(all_hint_tags):
                result.relevance_scores[tool.name] = result.relevance_scores.get(tool.name, 0.0) + 0.15
        
        # 重新排序
        result.selected_tools.sort(
            key=lambda t: result.relevance_scores.get(t.name, 0.0),
            reverse=True
        )
        
        return result
```

---

## 8. 与认知-画像 v2.0 的联动

### 8.1 画像维度对规划模式的影响

| 画像维度 | 影响 | 具体映射 |
|---------|------|---------|
| **Track A: 元认知 (metacognition)** | 决定模式选择偏好 | 高元认知 → DYNAMIC（自主能力强）；低元认知 → SKILL_ENHANCED/MIXED（需要引导） |
| **Track A: 发散性 (divergence)** | 影响原语选择 | 高发散 → TreeOfThought、PlanExecuteReflect（多方案探索）；低发散 → SequentialDecomposition（线性执行） |
| **Track A: 追踪深度 (tracking_depth)** | 影响 Skill 匹配阈值 | 高追踪深度 → 更严格的 Skill 匹配（用户偏好一致的流程）；低追踪深度 → 更灵活的动态规划 |
| **Track B: 技术标签 (technical_level)** | 影响工具筛选和 Skill 选择 | 专家用户 → 展示高级原语（DivideConquer、ParallelMap）；新手用户 → 展示基础原语（SequentialDecomposition） |
| **Track B: 领域标签 (domain)** | 直接匹配领域 Skill | 用户标签为 "ecommerce" → 优先匹配 `ecommerce_order_flow` 等 Skill |
| **g 因子** | 影响计划复杂度和容错 | 高 g → 允许复杂计划（10+ 步骤、条件分支、循环）；低 g → 简化计划（3-5 步骤、线性流程） |
| **时间衰减** | 影响历史 Skill 使用频率 | 最近常用的 Skill 获得更高的匹配 boost，但随时间衰减 |

### 8.2 动态模式选择中的画像注入

```python
def _select_mode_with_profile(
    self,
    intent: Intent,
    intent_context: IntentContext,
    matched_skills: List[Tuple[PlanningSkill, float]],
) -> PlanningMode:
    """
    结合认知画像选择规划模式。
    
    在原决策树基础上，注入画像调优：
    """
    profile = intent_context.cognitive_profile
    
    # 基础决策（来自第 5.2 节）
    base_mode = self._select_mode(intent, intent_context, matched_skills)
    
    # 画像调优
    if profile.metacognition > 0.8 and base_mode == PlanningMode.SKILL_ENHANCED:
        # 高元认知用户：即使有中匹配 Skill，也倾向于自主规划
        return PlanningMode.DYNAMIC
    
    if profile.divergence > 0.7 and base_mode == PlanningMode.MIXED:
        # 高发散用户：不喜欢严格骨架，改用 Skill 增强模式
        return PlanningMode.SKILL_ENHANCED
    
    if profile.g_factor < 0.3 and base_mode == PlanningMode.DYNAMIC:
        # 低 g 因子用户：即使无高匹配 Skill，也用 Skill 增强（如果可用）
        if matched_skills and matched_skills[0][1] > 0.5:
            return PlanningMode.SKILL_ENHANCED
    
    # 标签直接匹配：如果用户的 domain 标签与 Skill 精确匹配，强制使用 SKILL_ENHANCED
    user_domains = intent_context.cognitive_profile.track_b.get("domains", set())
    if matched_skills:
        for skill, score in matched_skills:
            if skill.domain_tags.intersection(user_domains) and score > 0.6:
                return PlanningMode.SKILL_ENHANCED
    
    return base_mode
```

---

## 9. 完整数据流

### 9.1 全景数据流图

```
用户输入
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Intent Parser                                        │
│  • 解析意图（Intent）                                           │
│  • 提取实体（Entities）                                         │
│  • 生成 IntentContext（含认知画像）                             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼ intent + intent_context
┌──────────────────────────────────────────────────────────────┐
│ Layer 1.5: Mixed Planning Engine                              │
│                                                               │
│  步骤 1: Skill 检测                                            │
│    ├── SkillRegistry.match_intent(intent)                    │
│    └── 返回: [(skill, score), ...]                            │
│                                                               │
│  步骤 2: 模式选择                                              │
│    ├── 结合画像调优 → PlanningMode                            │
│    └── DYNAMIC / SKILL_ENHANCED / MIXED                      │
│                                                               │
│  步骤 3: 生成骨架                                              │
│    ├── DYNAMIC: 通用原语库 → LLM 自主规划                      │
│    ├── SKILL_ENHANCED: Skill.generate_skeleton() → LLM 填充   │
│    └── MIXED: Skill.generate_skeleton() → LLM 只填充占位符      │
│                                                               │
│  输出: TaskGraph（工具名为占位符）                              │
└──────────────────────────────────────────────────────────────┘
  │
  ▼ TaskGraph (skeleton)
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: Tool Binding                                         │
│  • 占位符 → 实际工具名（ToolBindingEngine.bind）                │
│  • 参数适配（根据工具 Schema 填充参数）                         │
│  • 验证绑定完整性                                              │
│                                                               │
│  输出: TaskGraph（工具名已绑定）                                │
└──────────────────────────────────────────────────────────────┘
  │
  ▼ TaskGraph (bound)
┌──────────────────────────────────────────────────────────────┐
│ Layer 3: Execution                                            │
│  • SchemaGuard 验证参数                                        │
│  • ToolExecutor 执行调用                                         │
│  • 结果收集与状态更新                                            │
│                                                               │
│  输出: ExecutionResult                                          │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
ParseResult (与现有系统兼容)
```

### 9.2 模块间接口定义

```python
# MixedPlanningEngine → SkillRegistry
class SkillRegistry:
    def list_skills(self) -> List[PlanningSkill]: ...
    def get_skill(self, skill_id: str) -> Optional[PlanningSkill]: ...
    def match_skills(self, intent: Intent) -> List[Tuple[PlanningSkill, float]]: ...
    def register_skill(self, skill: PlanningSkill) -> bool: ...

# MixedPlanningEngine → PrimitiveLibrary
class PrimitiveLibrary:
    def get_primitive(self, name: str) -> Optional[PlanningPrimitive]: ...
    def list_primitives(self) -> List[PlanningPrimitive]: ...
    def describe_all(self) -> str: ...  # 返回所有原语的人类可读描述

# MixedPlanningEngine → ToolBindingEngine
class ToolBindingEngine:
    def bind(self, task_graph: TaskGraph, skill: Optional[PlanningSkill]) -> TaskGraph: ...

# MixedPlanningEngine → EnhancedToolShortlister
class EnhancedToolShortlister(ToolShortlister):
    def shortlist(self, intent, intent_context, registry, skill=None) -> ShortlistResult: ...
```

---

## 10. 实现路线图

### Phase 1: 通用规划原语库（预计 2-3 天）

- [ ] 设计 `PlanningPrimitive` 基类和 `PrimitiveLibrary`
- [ ] 实现 17 个通用规划原语（P1-P17）
- [ ] 实现 `generate_skeleton()` 方法，输出标准 TaskGraph
- [ ] 编写原语单元测试（每个原语生成骨架并验证拓扑）
- [ ] 实现 `PrimitiveLibrary.describe_all()`（用于 LLM 提示词注入）

### Phase 2: PlanningSkill 定义与注册（预计 3-4 天）

- [ ] 设计 `PlanningSkill` 数据模型（YAML + Python dataclass）
- [ ] 实现 `SkillRegistry`（注册、查询、匹配）
- [ ] 实现 `match_intent()` 匹配算法（意图类别 + 领域标签 + 关键词）
- [ ] 预置 3 个示例 Skill：电商下单、数据分析、代码生成
- [ ] 编写 Skill 解析器（YAML → Python 对象）
- [ ] 编写 Skill 单元测试

### Phase 3: Mixed Planning Engine（预计 4-5 天）

- [ ] 实现 `MixedPlanningEngine` 核心类
- [ ] 实现三种模式：DYNAMIC、SKILL_ENHANCED、MIXED
- [ ] 实现模式选择决策树（含画像调优）
- [ ] 实现回退机制（MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK）
- [ ] 实现 `ToolBindingEngine`（占位符到实际工具的绑定）
- [ ] 编写端到端集成测试（完整数据流测试）

### Phase 4: 与 v1.0 架构集成（预计 2-3 天）

- [ ] 修改 `IntentParser._build_task_graph` 调用 `MixedPlanningEngine`
- [ ] 保留 `DynamicPlanner` 作为 DYNAMIC 模式的底层实现
- [ ] 修改 `ToolShortlister` 为 `EnhancedToolShortlister`
- [ ] 添加 `use_skill_planning` 配置开关（渐进启用）
- [ ] 更新 `ParseResult` 包含 `planning_mode` 和 `skill_used` 字段
- [ ] 编写向后兼容性测试

### Phase 5: 性能优化与监控（预计 2-3 天）

- [ ] 实现 Skill 匹配缓存（避免重复计算匹配度）
- [ ] 实现骨架缓存（相同 Skill + 相同意图 → 复用骨架）
- [ ] 添加规划模式选择监控（各模式使用频率、成功率）
- [ ] 添加 Skill 使用效果监控（使用 Skill 后的成功率 vs 纯动态）
- [ ] 压力测试（100+ Skill + 1000+ 工具 + 100 QPS 规划请求）

### Phase 6: 文档与示例（预计 1-2 天）

- [ ] 编写 `PLANNING_SKILL_GUIDE.md`（面向用户的 Skill 编写指南）
- [ ] 编写 `PRIMITIVE_LIBRARY.md`（通用规划原语参考手册）
- [ ] 提供 5 个示例 Skill：电商、数据分析、代码、客服、科研
- [ ] 提供 Skill 模板生成器（用户输入领域描述 → 自动生成 Skill YAML）
- [ ] 更新主文档和 README

---

## 11. 附录

### 11.1 术语表

| 术语 | 定义 |
|------|------|
| **Planning Primitive** | 通用规划原语，跨领域通用的认知模式（如 ReAct Loop、Divide-Conquer） |
| **PlanningSkill** | 领域规划模板，基于通用原语组合，填充领域知识（如电商下单流程） |
| **Mixed Planning Engine** | 混合编排引擎，自动选择并执行 DYNAMIC/SKILL_ENHANCED/MIXED 三种模式 |
| **SkillRegistry** | Skill 注册中心，管理领域规划模板的注册、查询和匹配 |
| **PrimitiveLibrary** | 通用规划原语库，提供 17 个预定义原语的标准化接口 |
| **ToolBindingEngine** | 工具绑定引擎，将规划占位符适配到实际工具 |
| **Placeholder** | 占位符，规划阶段使用的抽象工具名（如 `search_tool`），等待绑定 |
| **Binding** | 绑定过程，将占位符替换为实际工具名并填充参数 |
| **Skeleton** | 骨架，Skill 生成的 TaskGraph 结构（无具体工具名） |
| **Fallback Chain** | 回退链，执行失败时的模式切换序列（MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK） |

### 11.2 设计决策记录 (ADR)

**ADR-001: Planning 与 Tools 正交解耦**
- **决策**: 将任务规划方法（Planning）与工具集（Tools）设计为独立正交的抽象层。
- **理由**: 避免"工具孤岛"问题，让系统在无工具或工具有限时仍能规划；支持同一 Skill 绑定到不同工具集。
- **后果**: 增加架构复杂度（需要 Binding 层）；开发 Skill 时需要理解两层抽象。

**ADR-002: 通用原语不依赖具体工具**
- **决策**: 通用规划原语（如 ReAct Loop）只定义拓扑结构，不引用具体工具名。
- **理由**: 确保原语的跨领域通用性；避免原语与工具绑定后的维护负担。
- **后果**: 需要 Binding 层做额外的适配工作；原语无法提供精确的工具参数提示。

**ADR-003: Skill 分三级详细度（SKELETON / STANDARD / DETAILED）**
- **决策**: Skill 定义三个详细度级别，控制 LLM 的调整自由度。
- **理由**: 不同场景对灵活性的需求不同（SKELETON 最灵活，DETAILED 最严格）。
- **后果**: 增加 Skill 设计复杂度；需要用户/开发者理解三级区别。

**ADR-004: 混合模式自动选择（非用户手动选择）**
- **决策**: 系统根据意图匹配度和认知画像自动选择规划模式，不暴露手动选择给用户。
- **理由**: 降低用户认知负担；系统可以基于历史数据优化选择策略。
- **后果**: 用户可能不理解为什么选了某种模式；需要完善的可解释性输出。

**ADR-005: 通用原语不"爬取"，而是人工设计**
- **决策**: 17 个通用规划原语从认知科学和文献中人工设计，不从现有系统中自动爬取。
- **理由**: 通用原语需要跨领域抽象能力，自动爬取容易过拟合到特定领域；人工设计可确保质量。
- **后果**: 初始工作量较大；社区贡献新原语需要审核。

### 11.3 参考文献

1. Yao, S., et al. (2022). "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023. (1000+ citations)
2. Wei, J., et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." NeurIPS 2022. (10000+ citations)
3. Yao, S., et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with Large Language Models." arXiv:2305.10601.
4. Wang, L., et al. (2023). "Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models." arXiv:2305.04091.
5. Shinn, N., et al. (2023). "Reflexion: Self-Reflective Agents with Verbal Reinforcement Learning." NeurIPS 2023.
6. Yang, Z., et al. (2024). "Understanding the Planning of LLM Agents: A Survey." arXiv:2406.06530. (561 citations)
7. AutoGPT. (2023). "Autonomous AI Agent Framework." GitHub.
8. LangChain. (2024). "LangGraph: Building Stateful Agent Applications." LangChain Documentation.
9. CrewAI. (2024). "Multi-Agent AI Framework." GitHub.
10. OpenAI. (2024). "Assistant API: Tools and Planning." OpenAI Documentation.
11. Newell, A., & Simon, H. A. (1972). "Human Problem Solving." Prentice-Hall. (认知科学经典)

### 11.4 与 v1.0 的变更对照表

| v1.0 组件 | v1.5 变更 | 说明 |
|----------|----------|------|
| `DynamicPlanner` | 保留为 DYNAMIC 模式底层 | 纯动态规划能力不变，作为 MIXED 引擎的子模块 |
| `ToolShortlister` | 升级为 `EnhancedToolShortlister` | 增加 Skill 相关的 tool_hints 排序 |
| `IntentParser` | `_build_task_graph` 调用 `MixedPlanningEngine` | 保持接口兼容，内部实现替换 |
| `ParseResult` | 增加 `planning_mode` 和 `skill_used` 字段 | 向后兼容（新增可选字段） |
| `TaskGraph` | 无变化 | 完全兼容，所有模式都输出 TaskGraph |
| `ToolRegistry` | 无变化 | 作为 Binding 层的输入 |

---

*本设计文档由 DialogMesh 架构团队基于文献调研、认知科学理论和代码分析生成，遵循"可计算行为特征"公理化体系。核心命题：Planning ≠ Tools。*
