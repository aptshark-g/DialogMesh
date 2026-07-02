# DialogMesh 多层 LLM 认知架构设计 v3.0

> **文档状态**: 设计草案 (Design Draft)  
> **版本**: v3.0  
> **日期**: 2026-07-19  
> **依赖**: [系统概念设计 v2.0](DESIGN_FULL_CONCEPT.md)  
> **核心命题**: **Agent 不是"带 LLM 的规则系统"，而是"以 LLM 为认知核心、算法为神经加速层的多认知体系统"。LLM 本身也需要认知结构——独立的 Tree of Thought 作为其心智空间。

---

## 目录

- [1. 架构演进：从"规则兜底 LLM"到"LLM 认知网络"](#1-架构演进从规则兜底-llm到llm-认知网络)
- [2. 核心范式：双树认知架构](#2-核心范式双树认知架构)
- [3. 三层 LLM 认知层](#3-三层-llm-认知层)
- [4. LLM Cognitive Tree（LLM 心智树）](#4-llm-cognitive-treellm-心智树)
- [5. 穿透层 LLM（回答 LLM）](#5-穿透层-llm回答-llm)
- [6. LLM 间通信协议](#6-llm-间通信协议)
- [7. 幻觉检测与缓解机制](#7-幻觉检测与缓解机制)
- [8. 与现有架构的集成](#8-与现有架构的集成)
- [9. 设计决策与权衡](#9-设计决策与权衡)
- [10. 附录](#10-附录)

---

## 1. 架构演进：从"规则兜底 LLM"到"LLM 认知网络"

### 1.1 当前架构的根本局限

在 v2.0 设计中，DialogMesh 存在一种**隐性的认知不对称**：

- **算法层**被设计为"大脑"（做决策、路由、规划）
- **LLM**被降格为"外挂工具"（仅在规则失效时调用，做兜底）

这种不对称导致系统无法真正称为 **Agent**——因为 Agent 的核心特征不是"高效执行规则"，而是：

1. **自主感知**：理解环境的复杂状态（不仅是模式匹配）
2. **持续学习**：从经验中改进自身行为模型
3. **元认知**：对自身决策过程进行反思和修正
4. **世界模型**：维持对外部（用户）和内部（系统）状态的表征

v2.0 的算法-LLM 关系是**主从式**的：算法为主，LLM 为仆。这种关系在**确定性强**的场景下高效，但在**模糊、开放、需要长期适应**的场景下会系统性失败。

### 1.2 新架构的核心思想：认知双工

v3.0 的架构将算法-LLM 关系重构为**认知双工（Cognitive Duplex）**：

> **算法不是 LLM 的替代，而是 LLM 的**神经加速层**。LLM 不是算法的兜底，而是系统的**认知核心**。两者并行运行，通过结构化的认知树（Cognitive Tree）交换信息，形成**协作式认知网络**。

**关键转变**：

| 维度 | v2.0（主从式） | v3.0（认知双工） |
|------|---------------|-----------------|
| **算法角色** | 主决策器，LLM 是备选 | 实时加速器，提供快速基线决策 |
| **LLM 角色** | 兜底工具，规则失效时调用 | 认知核心，负责理解、推理、反思、学习 |
| **决策流程** | 算法 → 失败 → LLM → 输出 | 算法 ∥ LLM 同时跑 → 融合 → 输出 |
| **学习机制** | 无（规则静态） | 持续：Meta-Cognitive 层评估 → 反馈调优 |
| **元认知** | 无（系统不自省） | 核心：LLM 对 LLM 自身的反思 |
| **树结构** | 仅用户 Topic Tree | 双树：用户 Topic Tree + LLM Cognitive Tree |
| **耦合方式** | 硬耦合（规则调用 LLM） | 受控耦合（通过 Cognitive Tree 结构化通信） |

### 1.3 为什么需要三层 LLM

引入大量 LLM 后，系统面临**三个不同时间尺度的认知问题**：

| 层级 | 时间尺度 | 认知问题 | 类比人类认知 |
|------|---------|---------|------------|
| **Layer 1.5** | 毫秒-秒（每轮） | "当前输入意味着什么？现在该怎么做？" | 直觉/系统 1 |
| **Layer 2.5** | 秒-分钟（跨轮） | "我的判断对吗？有没有更好的方法？用户为什么困惑？" | 反思/系统 2 |
| **Layer 3** | 分钟-小时（跨会话） | "过去 100 轮中，我的模式是什么？哪些算法需要改进？用户画像该怎么更新？" | 元认知/系统 3 |

三层 LLM 不是简单的"三个 LLM 实例"，而是**三个不同认知功能的抽象层**，每个层可以包含多个 LLM 实例（如 PCR-LLM、Intent-LLM、Planning-LLM 等），它们共享同一套 LLM Cognitive Tree。

### 1.4 为什么 LLM 需要独立的 Tree of Thought

用户的对话主题（Topic Tree）和 LLM 的思考过程（Cognitive Tree）必须**物理分离**的原因：

1. **认知主权的区分**：Topic Tree 是**用户世界的模型**（用户在想什么、讨论什么），Cognitive Tree 是**LLM 心智的模型**（LLM 在推理什么、犹豫什么、假设什么）。两者不能混淆。
2. **通信载体的需要**：LLM 之间需要交换的不是"用户说了什么"，而是"我是这样理解的"、"我觉得这里有问题"、"我的置信度是 X"。这些内部认知状态必须结构化的存储和传递。
3. **反思的闭环**：Meta-Cognitive 层要反思的是"Planning-LLM 的推理过程"，而不是"用户的话题切换"。如果不隔离，反思会污染用户对话状态。
4. **幻觉的可追溯性**：当 LLM 出现幻觉时，需要在 Cognitive Tree 中追溯是哪个推理节点产生了错误，而不是在用户话题中找问题。

---

## 2. 核心范式：双树认知架构

### 2.1 架构全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户（User）                                 │
│                         ↕ 自然语言                                   │
├─────────────────────────────────────────────────────────────────────┤
│  穿透层：Answer LLM（回答 LLM）                                      │
│  ──────────────────────────────────────────────────────────────   │
│  • 直接与用户沟通，但其思考受系统内 LLM 的约束和指导                  │
│  • 本身也是 LLM Cognitive Tree 的参与者（其思考被记录、被反思）      │
│  • 同时读取用户的 Topic Tree 和 LLM 的 Cognitive Tree 做上下文决策    │
├─────────────────────────────────────────────────────────────────────┤
│  实时层：Algorithm-LLM Hybrid Layer（Layer 1.5）                     │
│  ──────────────────────────────────────────────────────────────   │
│  算法引擎 ∥ LLM 认知引擎 同时运行，每轮必达                            │
│  • PCR-LLM：语义噪声分析 + 期望推断（与规则引擎并行）                 │
│  • Intent-LLM：深层意图理解 + 隐含实体挖掘（与规则提取并行）          │
│  • Planning-LLM：Skill 模板填充 + 备选方案生成（与算法规划并行）       │
│  • 融合器：算法结果 + LLM 结果 → 加权融合 → 输出                      │
├─────────────────────────────────────────────────────────────────────┤
│  监督层：Meta-Cognitive Supervisory Layer（Layer 2.5）               │
│  ──────────────────────────────────────────────────────────────   │
│  跨轮验证、幻觉检测、质量评估、算法调优建议                            │
│  • 读取 Cognitive Tree 的最近 N 个节点                                 │
│  • 评估实时层 LLM 的决策质量（"这个规划合理吗？"）                      │
│  • 检测算法与 LLM 的系统性冲突（"规则引擎在 X 上持续错误"）          │
│  • 生成调优建议（"建议将阈值从 A 调到 B"）                            │
│  • 调度：后台异步，每轮结束后或每 N 轮触发                            │
├─────────────────────────────────────────────────────────────────────┤
│  复盘层：Reflective Consolidation Layer（Layer 3）                    │
│  ──────────────────────────────────────────────────────────────   │
│  跨会话复盘、长期认知模型更新、系统级学习                              │
│  • 对过去 M 轮的 Cognitive Tree 进行结构分析                          │
│  • 识别 LLM 的系统性偏见（"Planning-LLM 总是高估用户耐心"）          │
│  • 识别算法的结构性盲区（"规则引擎无法处理隐喻表达"）                 │
│  • 更新用户画像的深层模型（Track A 趋势 + Track B 修正）              │
│  • 生成长期学习策略（"未来遇到此类用户应优先使用 Skill X"）            │
│  • 调度：后台异步，会话结束时或触发条件满足时启动                      │
├─────────────────────────────────────────────────────────────────────┤
│  双树结构（Two Trees）                                                │
│  ═══════════════════════════════════════════════════════════        │
│  ┌──────────────────────┐  ┌──────────────────────────────┐       │
│  │  Topic Tree（用户）    │  │  Cognitive Tree（LLM 心智）   │       │
│  │  ───────────────     │  │  ────────────────────────    │       │
│  │  用户对话主题的层次    │  │  LLM 的推理、假设、反思、决策 │       │
│  │  结构：主题→子话题    │  │  结构：感知→推理→决策→反思   │       │
│  │  边权重：话题切换强度  │  │  边权重：推理依赖强度        │       │
│  │  节点：对话轮次        │  │  节点：认知事件（LLM 调用）   │       │
│  │  访问者：用户 + Answer │  │  访问者：所有 LLM 实例       │       │
│  │  ─────────────────────│  │  存储：LLM 的完整推理轨迹     │       │
│  │  持久化：会话级        │  │  持久化：会话级 + 跨会话摘要   │       │
│  └──────────────────────┘  └──────────────────────────────┘       │
│                                                                     │
│  LLM 间通信：通过 Cognitive Tree 的节点引用和边连接实现              │
│  （例如：Planning-LLM 输出一个决策节点，Meta-Cognitive-LLM          │
│  读取该节点并在其下游添加一个验证节点）                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 双树的形式化定义

#### 2.2.1 Topic Tree（用户对话树）

已在 v2.0 中定义，回顾其结构：

```
TopicTree = (V_topic, E_topic, W_topic)
  V_topic: 节点 = {topic_id, content, timestamp, importance}
  E_topic: 边 = {source, target, switch_type, semantic_distance}
  W_topic: 权重函数 = EMA 更新
```

Topic Tree 是**用户世界的认知模型**：用户讨论了什么、从 A 话题跳到了 B 话题、哪些话题对用户更重要。

#### 2.2.2 Cognitive Tree（LLM 心智树）——v3.0 新增

```
CognitiveTree = (V_cog, E_cog, M_cog, T_cog)

V_cog（认知节点）:
  ├─ node_id: 全局唯一标识
  ├─ cog_type: 认知类型（见下表）
  ├─ source_llm: 产生此节点的 LLM 实例（如 "PCR-LLM", "Planning-LLM"）
  ├─ timestamp: 创建时间
  ├─ content: 认知内容（LLM 的推理文本、决策理由、置信度声明）
  ├─ confidence: 该认知的置信度 [0, 1]
  ├─ evidence: 支撑证据（引用哪些其他节点、哪些外部数据）
  ├─ action: 由此认知产生的行动（如"选择了 SKILL_ENHANCED 模式"）
  ├─ status: 状态（active / validated / invalidated / superseded）
  └─ metadata: {latency_ms, token_cost, model_version, temperature}

E_cog（认知边）:
  ├─ source: 源节点（"基于什么推理"）
  ├─ target: 目标节点（"得出了什么结论"）
  ├─ edge_type: 边类型（见下表）
  ├─ weight: 依赖强度 [0, 1]
  └─ condition: 条件（如果是条件边，如"如果验证通过则"）

M_cog（元认知层）:
  ├─ reflections: 对该节点的反思列表（由 Meta-Cognitive 层添加）
  ├─ validations: 验证结果列表（由验证 LLM 添加）
  ├─ version_history: 节点内容的历史版本（如果节点被修正）
  └─ cross_refs: 跨会话引用（"此认知与上次的 X 节点相关"）

T_cog（树结构管理）:
  ├─ root: 根节点（会话初始的"系统启动认知"）
  ├─ active_branch: 当前活跃分支（最近 N 轮的主要推理链）
  ├─ stale_branches: 失效分支（被验证为错误或 superseded 的分支）
  └─ depth_limit: 单分支最大深度（防止无限递归，默认 10）
```

**认知节点类型（CogType）**：

| 类型 | 定义 | 示例 | 产生者 |
|------|------|------|--------|
| **PERCEPTION** | 对外部输入的感知 | "用户输入有 0.3 的噪声，可能是非母语表达" | PCR-LLM |
| **HYPOTHESIS** | 对当前状态的假设 | "用户的真实意图可能是 SCAN_MEMORY 而非 READ_MEMORY" | Intent-LLM |
| **REASONING** | 中间推理过程 | "基于技能匹配度 0.85，MIXED 模式比 DYNAMIC 更可靠" | Planning-LLM |
| **DECISION** | 最终决策 | "选择使用 `ecommerce_order_flow` Skill，进入 MIXED 模式" | Planning-LLM |
| **ACTION** | 产生的行动记录 | "调用了 `github_api_search_repos` 工具，参数 {...}" | 执行层 |
| **OBSERVATION** | 行动结果的观察 | "工具返回 404，repo 不存在" | 执行层 |
| **REFLECTION** | 对前述认知的反思 | "Planning-LLM 的决策忽略了用户的低 g 因子，应简化计划" | Meta-Cognitive-LLM |
| **VALIDATION** | 对认知的验证结果 | "PERCEPTION 节点 P-042 的噪声评估与事后验证一致" | Meta-Cognitive-LLM |
| **LEARNING** | 长期学习结论 | "过去 50 轮中，规则引擎在隐喻表达上失败率 80%" | Reflective-LLM |
| **COMMUNICATION** | LLM 间通信消息 | "Planning-LLM 向 Meta-Cognitive-LLM 请求验证" | 任意 LLM |

**认知边类型（EdgeType）**：

| 类型 | 定义 | 图示 |
|------|------|------|
| **DERIVES** | 推导（A 推导出 B） | A → B |
| **SUPPORTS** | 支持（B 支持 A 的假设） | A ← B |
| **CONTRADICTS** | 矛盾（B 与 A 矛盾） | A ↔ B（红色） |
| **CONDITIONAL** | 条件（如果 A 则 B） | A ⇒ B |
| **ALTERNATIVE** | 备选（B 是 A 的备选方案） | A ∥ B |
| **REFINES** | 细化（B 细化 A） | A ⊃ B |
| **SUMMARIZES** | 摘要（B 是 A 的摘要） | A ⊂ B |
| **CROSS_REF** | 跨引用（B 引用另一会话的 A） | A ~~ B |

### 2.3 双树的交互关系

Topic Tree 和 Cognitive Tree 不是孤立的，而是**交叉引用**的：

```
Topic Tree                         Cognitive Tree
  T-1: "调试程序"                    C-1: PERCEPTION "用户提到调试"
    │                                │
    ├── T-2: "内存扫描" ←────────────→ C-2: HYPOTHESIS "意图是 SCAN_MEMORY"
    │       │                        │       │
    │       └── T-3: "结果分析" ←────→ C-3: DECISION "使用 first_scan"
    │                                 │       │
    │                                 │       └── C-4: ACTION "调用 first_scan"
    │                                 │
    └── T-4: "代码审查" ←────────────→ C-5: REFLECTION "用户突然切换话题，
                                        可能是因为 C-3 的结果不满意"
```

**交叉引用机制**：
- 每个 Cognitive Tree 节点可以引用一个或多个 Topic Tree 节点（通过 `topic_refs` 字段）。
- 每个 Topic Tree 节点可以引用一个或多个 Cognitive Tree 节点（通过 `cog_refs` 字段）。
- 这种交叉引用是**单向的**：Cognitive Tree 的节点生命周期独立于 Topic Tree（即使用户删除了某个话题，LLM 的推理过程仍然保留在 Cognitive Tree 中，供后续反思）。

---

## 3. 三层 LLM 认知层

### 3.1 Layer 1.5: Hybrid Cognitive Layer（实时交织层）

#### 3.1.1 功能定位

**时间尺度**：每轮必达，同步运行，延迟预算 50-200ms。  
**认知功能**："直觉与快速决策"——类比人类的系统 1（System 1）。  
**核心目标**：在算法快速响应的基础上，注入 LLM 的深度理解，实现"又快又准"。

#### 3.1.2 架构：算法引擎 ∥ LLM 认知引擎 并行

每个组件（PCR、Intent Parser、Planning）内部都并行运行两套引擎：

```
输入
  │
  ├──→ [算法引擎] ───────────→ [算法结果 A] ───┐
  │     (规则/统计/启发式)                       │
  │                                              ├──→ [融合器] ──→ 输出
  │                                              │   (加权融合)
  └──→ [LLM 引擎] ───────────→ [LLM 结果 B] ───┘
        (语义理解/推理/生成)
```

**并行调度**：
- 算法引擎和 LLM 引擎同时启动，**不等待对方完成**。
- 如果算法引擎先完成且置信度 > 0.9，**可以立即输出**（LLM 引擎在后台继续运行，其结果用于更新下一轮的认知状态）。
- 如果算法引擎置信度 < 0.6，**必须等待 LLM 引擎完成**，以 LLM 结果为主。
- 如果两者都完成但结果冲突，**融合器**进行加权融合。

#### 3.1.3 融合器（Fusion Engine）算法

**融合问题**：给定算法结果 $A$（置信度 $c_A$）和 LLM 结果 $B$（置信度 $c_B$），如何生成最终输出 $O$？

**融合策略**：

$$O = \begin{cases} 
A & \text{if } c_A > \theta_{high} \text{ and } c_B < \theta_{low} \\
B & \text{if } c_A < \theta_{low} \text{ and } c_B > \theta_{high} \\
\text{weighted}(A, B) & \text{if } c_A \approx c_B \\
\text{ask\_user} & \text{if } c_A < \theta_{low} \text{ and } c_B < \theta_{low}
\end{cases}$$

其中：
- $\theta_{high} = 0.85$（高置信度阈值）
- $\theta_{low} = 0.6$（低置信度阈值）
- $weighted(A, B) = \frac{c_A \cdot A + c_B \cdot B}{c_A + c_B}$（加权平均，适用于数值型输出）
- 对于离散型输出（如意图类别），加权平均不适用，改用**最大置信度**或**多计划投票**。

**冲突检测与消解**：

当 $A$ 和 $B$ 的类型一致（如都是意图类别）但值不同时：

$$Conflict(A, B) = \begin{cases} 
\text{true} & \text{if } A \neq B \text{ and } c_A > 0.5 \text{ and } c_B > 0.5 \\
\text{false} & \text{otherwise}
\end{cases}$$

如果冲突为真：
1. 记录冲突到 Cognitive Tree（添加 CONTRADICTS 边）。
2. 触发 Meta-Cognitive 层的快速检查（如果可用）。
3. 如果 Meta-Cognitive 层不可用（超时），采用"保守策略"：选择置信度较高者，但降低其置信度（$c_{out} = \max(c_A, c_B) \times 0.8$）。

#### 3.1.4 各组件的 LLM 引擎设计

**PCR-LLM**：
- **输入**：用户原始输入 + 上一轮 PCR 输出（作为上下文）
- **输出**：噪声分析（语义/结构/参照）、期望推断（概率分布）、认知快照（4 维度）
- **与算法引擎的关系**：算法引擎做快速分类（规则匹配），PCR-LLM 做深层语义分析（如"用户说'随便看看'，算法引擎分类为 COMPANION，但 LLM 分析用户语气有焦虑，建议标记为 ADVISOR"）。
- **Cognitive Tree 节点**：PERCEPTION（噪声分析）、HYPOTHESIS（期望推断）。

**Intent-LLM**：
- **输入**：规范化后的用户输入 + 提取的实体列表 + 对话历史（Hot Layer）
- **输出**：意图推断（含隐含意图）、实体补全（"规则漏掉的隐含地址"）、歧义消解建议（"这个歧义可以用默认推断消解"）
- **与算法引擎的关系**：算法引擎做规则提取和分类，Intent-LLM 做深层理解（如"用户说'看看这个'，规则无法提取实体，但 LLM 从上下文推断'这个'指的是上一轮提到的地址 0x0040"）。
- **Cognitive Tree 节点**：HYPOTHESIS（意图推断）、REASONING（实体补全推理）。

**Planning-LLM**：
- **输入**：意图 + 可用工具列表 + 匹配 Skill（如果有）+ 用户认知画像
- **输出**：TaskGraph 骨架（含占位符）+ 备选方案 + 每个方案的置信度
- **与算法引擎的关系**：算法引擎（Skill 模板或静态 Blueprint）提供骨架，Planning-LLM 填充细节和生成备选。
- **Cognitive Tree 节点**：REASONING（方案比较）、DECISION（最终选择）、ALTERNATIVE（备选方案）。

### 3.2 Layer 2.5: Meta-Cognitive Supervisory Layer（元认知监督层）

#### 3.2.1 功能定位

**时间尺度**：跨轮（秒-分钟），异步运行，后台调度。  
**认知功能**："反思与验证"——类比人类的系统 2（System 2）。  
**核心目标**：对 Layer 1.5 的 LLM 输出进行**验证、评估、修正**，防止幻觉累积，同时生成算法调优建议。

**关键问题**：大量引入 LLM 后，**幻觉（Hallucination）**成为首要风险。Meta-Cognitive 层的核心使命就是：**"我不信任任何 LLM 的输出，直到我验证过。"**

#### 3.2.2 触发条件

Meta-Cognitive 层不是每轮都运行的，而是**事件驱动**的：

| 触发条件 | 说明 | 优先级 |
|---------|------|--------|
| **冲突事件** | Layer 1.5 的算法结果与 LLM 结果冲突 | 紧急（立即触发） |
| **低置信度事件** | Layer 1.5 的 LLM 输出置信度 < 0.6 | 高（当前轮结束后触发） |
| **用户异常** | 用户连续要求澄清或表达不满 | 高（当前轮结束后触发） |
| **定期巡检** | 每 N 轮（如 5 轮）自动触发一次 | 中（后台排队） |
| **会话结束** | 会话关闭时触发全面复盘 | 低（后台异步） |
| **外部请求** | 开发者手动触发验证 | 手动 |

#### 3.2.3 核心功能：三层验证模型

Meta-Cognitive 层对 LLM 输出进行**三层验证**：

**第一层：事实性验证（Factuality Check）**

验证 LLM 输出是否与客观事实一致。

- **工具调用验证**：Planning-LLM 说"调用了工具 X"，验证工具 X 是否真的存在于 ToolRegistry。
- **参数验证**：Planning-LLM 生成的参数是否符合 JSON Schema。
- **结果验证**：LLM 说"工具返回了 Y"，验证 Y 是否与实际工具返回值一致。
- **引用验证**：LLM 引用的历史信息是否真实存在于 Topic Tree 或 Context Window。

**验证公式**：

$$FactualityScore = \frac{VerifiedFacts}{TotalClaims}$$

如果 $FactualityScore < 0.8$，触发告警，要求 LLM 重新生成或降级到保守策略。

**第二层：一致性验证（Consistency Check）**

验证 LLM 输出是否与系统内部状态一致。

- **跨层一致性**：PCR-LLM 推断的期望类型是否与 Intent-LLM 推断的意图兼容？（如 PCR 推断 TOOL，但 Intent 推断为 CHITCHAT，则冲突）
- **跨轮一致性**：当前轮的推理是否与上一轮的逻辑一致？（如上一轮推断用户是"专家"，当前轮 LLM 却使用"新手"策略）
- **自我一致性**：同一 LLM 在不同 temperature 下是否给出一致的结果？（如果 3 个候选计划差异极大，说明 LLM 自身不确定）

**一致性度量**：

$$ConsistencyScore = 1 - \frac{Conflicts}{TotalCrossChecks}$$

**第三层：合理性验证（Plausibility Check）**

验证 LLM 输出是否在常识和领域知识范围内合理。

- **常识验证**：LLM 生成的计划是否包含明显不合理的步骤（如"先支付后下单"）。
- **领域验证**：LLM 生成的 Skill 填充是否符合领域约束（如电商 Skill 中"库存检查"必须在"下单"之前）。
- **用户画像验证**：LLM 的响应复杂度是否与用户的认知画像匹配（如低 g 因子用户却生成了 10 步计划）。

**合理性度量**：使用规则模板 + 轻量 LLM 评估：

$$PlausibilityScore = LLMJudge(plan, constraints, profile)$$

#### 3.2.4 幻觉检测机制

Meta-Cognitive 层是系统的**幻觉防火墙**。幻觉检测不是简单的"事实核查"，而是**多维度、多来源的交叉验证**。

**幻觉类型与检测策略**：

| 幻觉类型 | 定义 | 检测策略 | 示例 |
|---------|------|---------|------|
| **事实幻觉** | LLM 编造不存在的事实 | 工具存在性验证 + 外部 API 验证 | "工具 `search_api` 存在"（实际不存在） |
| **逻辑幻觉** | LLM 的推理存在逻辑错误 | 一致性验证 + 规则约束检查 | "如果 A 则 B"（但 A 和 B 无因果关系） |
| **引用幻觉** | LLM 引用不存在的上下文 | 引用存在性验证（Topic Tree 回溯） | "正如用户上一轮所说"（用户没说） |
| **参数幻觉** | LLM 生成非法参数 | Schema Guard 验证 | 参数类型错误、必填参数缺失 |
| **策略幻觉** | LLM 选择不存在的策略 | Skill 存在性验证 + 模式合法性检查 | 选择 "MIXED" 模式但无匹配 Skill |
| **自我幻觉** | LLM 对自己的输出过度自信 | 多计划一致性检查 + 置信度校准 | 生成 3 个候选，但 LLM 只推荐置信度最高的 |

**幻觉检测的算法概念**：

$$HallucinationRisk = \alpha \cdot (1 - Factuality) + \beta \cdot (1 - Consistency) + \gamma \cdot (1 - Plausibility)$$

如果 $HallucinationRisk > 0.7$，触发**红色告警**：
1. 当前 LLM 输出被标记为"不可信"
2. 系统回退到算法引擎的保守输出
3. 用户收到澄清请求（"我不确定您的意图，请确认..."）
4. 触发 Reflective 层进行深度分析（"为什么这个 LLM 在这里产生了幻觉？"）

#### 3.2.5 算法调优建议生成

Meta-Cognitive 层不仅验证 LLM，还**评估算法引擎**的决策质量，生成算法调优建议。

**评估方法**：

- 如果算法引擎的结果与 LLM 结果一致，且事后验证为正确 → 算法得分 +1
- 如果算法引擎的结果与 LLM 结果冲突，且事后验证 LLM 正确 → 算法得分 -1，记录"规则盲区"
- 如果算法引擎的结果与 LLM 结果冲突，且事后验证算法正确 → LLM 得分 -1，记录"LLM 过度自信"

**调优建议生成**：

经过 N 轮积累后，Meta-Cognitive 层生成统计报告：

```
报告示例：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
算法引擎评估报告（过去 50 轮）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 意图分类：
   • 准确率: 87%（43/50 正确）
   • 盲区: WRITE_MEMORY 意图（规则正则覆盖不足，失败 5/8 次）
   • 建议: 扩充正则模式，添加 "更新"、"设成"、"改成" 变体

2. 实体提取：
   • 召回率: 91%（平均 0.3 个实体/轮漏检）
   • 盲区: 隐含地址引用（如 "这个地址" 未消解，漏检 4 次）
   • 建议: 增强 Reference Resolver 的代词消解能力

3. 噪声检测：
   • PCR 误判率: 12%（6/50 次将正常输入标记为高噪声）
   • 原因: 用户是第二语言使用者，表达风格被误判为不稳定
   • 建议: 引入语言特征检测，区分"噪声"和"非母语表达"

4. 规划模式选择：
   • 自动选择准确率: 78%（39/50 次用户满意）
   • 过度使用 DYNAMIC: 在电商场景下，用户更偏好 MIXED 的完整性
   • 建议: 电商领域标签匹配时，提高 MIXED 模式优先级
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**建议的持久化与应用**：
- 建议被写入持久化存储（如 `algorithm_tuning_suggestions` 表）。
- 开发者在后台审查建议，选择性地应用到规则库或参数配置。
- 高置信度建议（经过多个会话验证）可以自动应用（如阈值微调）。
- 建议的应用效果被持续监控，如果应用后效果下降，自动回滚。

### 3.3 Layer 3: Reflective Consolidation Layer（复盘整合层）

#### 3.3.1 功能定位

**时间尺度**：跨会话（分钟-小时），异步运行，后台调度。  
**认知功能**："元认知与长期学习"——类比人类的系统 3（System 3，或称为"元-元认知"）。  
**核心目标**：对 LLM 自身的认知模式进行**长期复盘、偏见修正、系统级学习**。

**与 Layer 2.5 的区别**：

| 维度 | Layer 2.5（Meta-Cognitive） | Layer 3（Reflective） |
|------|----------------------------|----------------------|
| **时间尺度** | 跨轮（秒-分钟） | 跨会话（分钟-小时） |
| **验证对象** | 单次 LLM 输出 | LLM 的长期认知模式 |
| **分析粒度** | 节点级（单个决策） | 模式级（系统性偏见） |
| **输出** | 即时修正 + 调优建议 | 长期策略 + 画像更新 + 系统改进 |
| **触发频率** | 每轮或每 N 轮 | 会话结束或定时任务 |

#### 3.3.2 核心功能：认知模式分析

Reflective 层读取整个会话的 Cognitive Tree，进行**结构性分析**。

**分析维度 1：LLM 偏见检测**

检测特定 LLM 实例的系统性偏见：

$$Bias_{llm} = \frac{ObservedBehavior - ExpectedBehavior}{ExpectedBehavior}$$

示例偏见：
- **过度规划偏见**：Planning-LLM 总是生成 8+ 步计划，但用户平均只需要 3 步。
- **保守偏见**：PCR-LLM 总是高估噪声（将正常输入标记为高噪声），导致系统过于保守。
- **Skill 依赖偏见**：Planning-LLM 在有 Skill 时过度依赖 Skill，即使 Skill 不完全匹配。
- **用户画像偏见**：Intent-LLM 对某类用户（如非母语者）的意图推断准确率显著低于平均水平。

**分析维度 2：算法结构性盲区**

识别算法引擎在长期使用中的**系统性盲区**：

- 规则引擎在特定意图类别上的持续低准确率（如隐喻表达、 sarcasm）。
- 算法在特定用户群体上的失效模式（如高发散性用户的多意图拆分失败）。
- 算法与 LLM 冲突的**模式化场景**（如"用户说模糊请求时，算法偏向 TOOL，LLM 偏向 ADVISOR"）。

**分析维度 3：Cognitive Tree 的结构健康度**

评估 Cognitive Tree 的结构质量：

- **分支平衡度**：是否存在某个 LLM 实例过度主导决策（如 Planning-LLM 的节点占比 > 70%）？
- **反思覆盖率**：多少比例的 DECISION 节点有对应的 REFLECTION 或 VALIDATION 节点？
- **错误追踪率**：出现错误的节点，是否能追溯到上游的某个 HYPOTHESIS 或 REASONING 节点？
- **知识复用率**：当前会话的 Cognitive Tree 中，有多少节点引用了历史会话的节点（跨会话学习）？

**结构健康度公式**：

$$TreeHealth = 0.25 \cdot Balance + 0.25 \cdot Coverage + 0.25 \cdot Traceability + 0.25 \cdot Reuse$$

#### 3.3.3 核心功能：用户画像深度更新

Reflective 层更新用户画像的**深层模型**（不是实时快照，而是长期趋势）。

**Track A 更新**：
- 将多轮的认知动力学特征（元认知、发散性、稳定性、信心度）进行时间序列分析。
- 识别用户的**认知模式变化**（如"用户最近 10 轮的元认知持续提升，可能正在学习新领域"）。
- 预测用户的**未来认知状态**（基于趋势外推）。

**Track B 更新**：
- 验证标签的**稳定性**（标签是否持续有效？是否需要更新？）。
- 识别标签的**冲突**（如 `technical_level=expert` 与 `理解速度=0.3` 矛盾）。
- 生成新标签的**获取建议**（基于长期观察，建议获取哪些新标签）。

**更新公式**：

$$Profile_{new} = \alpha \cdot Profile_{current} + (1-\alpha) \cdot Profile_{session}$$

其中 $\alpha$ 是时间衰减因子（老画像权重更高），$Profile_{session}$ 是当前会话的画像汇总。

#### 3.3.4 核心功能：系统级学习策略

Reflective 层生成**面向未来的系统改进策略**。

**策略类型**：

- **参数策略**："将电商场景的 MIXED 模式优先级从 0.5 提升到 0.7"
- **规则策略**："为 WRITE_MEMORY 意图添加 3 个正则变体"
- **Skill 策略**："为高频用户群体创建新的 Skill 模板"
- **LLM 策略**："针对非母语用户，调整 PCR-LLM 的噪声阈值"
- **架构策略**："考虑引入专门处理隐喻表达的 LLM 实例"

**策略生成算法**：

基于 Cognitive Tree 的模式分析 + 用户画像的趋势 + 系统性能指标，使用 LLM 生成自然语言策略，然后结构化解析为可执行的操作列表。

**策略验证**：
- 新策略先在**影子模式**下运行（不影响实际输出，只记录"如果用了新策略，结果会是什么"）。
- 经过 M 轮影子验证后，如果新策略的预期效果 > 当前策略，则自动应用。

---

## 4. LLM Cognitive Tree（LLM 心智树）

### 4.1 为什么需要独立的 LLM 心智空间

Cognitive Tree 不是"给 LLM 用的 Topic Tree"，而是**LLM 的独立心智表征**。它必须满足以下需求：

1. **推理透明化**：LLM 的推理过程（"为什么这样决策"）必须被记录，以便 Meta-Cognitive 层审查。
2. **迭代可追溯**：LLM 的自我反思（"我之前的判断可能是错的，因为..."）必须能在树结构中追溯。
3. **多 LLM 协作**：不同 LLM 实例（PCR-LLM、Intent-LLM、Planning-LLM）之间需要通过共享树结构交换信息。
4. **跨会话持久化**：LLM 的学习成果（"上次遇到类似用户，我发现..."）需要跨会话保留。

### 4.2 树的结构细节

#### 4.2.1 节点生命周期

每个认知节点经历以下生命周期：

```
CREATED → ACTIVE → {VALIDATED | INVALIDATED | SUPERSEDED} → ARCHIVED
```

- **CREATED**：节点刚被 LLM 生成，尚未验证。
- **ACTIVE**：节点被系统采纳，正在影响决策。
- **VALIDATED**：Meta-Cognitive 层验证该节点的推理正确，标记为可信。
- **INVALIDATED**：Meta-Cognitive 层验证该节点的推理错误，标记为不可信。下游依赖该节点的所有节点也需要重新评估。
- **SUPERSEDED**：该节点的内容被新版本替代（如 LLM 修正了之前的推理），旧版本标记为 superseded，新版本链接到旧版本。
- **ARCHIVED**：节点不再影响当前决策，但保留在树中供历史分析。

#### 4.2.2 版本控制

认知节点的内容可以修正，但**不直接覆盖**，而是创建新版本：

```
C-42 (v1): "意图是 READ_MEMORY" → INVALIDATED
  └── C-42 (v2): "意图是 SCAN_MEMORY" → VALIDATED
```

版本控制的好处：
- Meta-Cognitive 层可以分析"为什么 LLM 修正了判断"（学习 LLM 的自我修正模式）。
- Reflective 层可以统计"哪些类型的节点最容易被修正"（识别 LLM 的弱点）。
- 避免信息丢失（旧版本仍然是认知历史的一部分）。

#### 4.2.3 分支管理

Cognitive Tree 允许多个并行分支（代表 LLM 的多个假设或备选方案）：

```
C-1: "用户意图是 SCAN_MEMORY" (confidence: 0.7)
  ├── C-2: "使用 first_scan 工具" (confidence: 0.8) [ACTIVE]
  └── C-3: "意图也可能是 READ_MEMORY" (confidence: 0.3) [STALE]
      └── C-4: "使用 read_memory 工具" (confidence: 0.6) [STALE]
```

- **ACTIVE 分支**：当前被系统采纳的推理链。
- **STALE 分支**：被否决或未被采纳的推理链，但保留在树中（供 Meta-Cognitive 层分析"为什么被否决"）。
- **分支切换**：当 Meta-Cognitive 层发现 ACTIVE 分支有错误时，可以切换到 STALE 分支（如果该分支被验证为正确）。

### 4.3 LLM 间通信：通过 Cognitive Tree 实现

#### 4.3.1 通信模型

传统多 Agent 系统使用**消息传递**（message passing）：Agent A 发送消息给 Agent B。  
DialogMesh 的 LLM 间通信使用**共享认知树**（shared cognitive tree）：LLM 实例通过读写 Cognitive Tree 的节点来交换信息。

**通信示例**：

```
场景：Planning-LLM 生成了一个计划，需要 Meta-Cognitive-LLM 验证

步骤 1: Planning-LLM 在 Cognitive Tree 中创建 DECISION 节点
  C-100: DECISION "选择 MIXED 模式，使用 ecommerce_order_flow Skill"
  
步骤 2: Planning-LLM 在节点中标记 "需要验证"
  C-100.status = "pending_validation"
  C-100.validation_request = {type: "plausibility", priority: "high"}
  
步骤 3: Meta-Cognitive-LLM 检测到 pending_validation 节点，读取 C-100
  
步骤 4: Meta-Cognitive-LLM 创建 VALIDATION 节点作为 C-100 的子节点
  C-101: VALIDATION "验证通过：Skill 匹配度 0.92，约束全部满足"
  E(C-100 → C-101): DERIVES
  
步骤 5: Meta-Cognitive-LLM 更新 C-100 的状态
  C-100.status = "VALIDATED"
  
步骤 6: Planning-LLM 读取到 C-100 已验证，继续执行
```

**通信的优势**（相比消息传递）：

- **可追溯**：任何通信都可以追溯到具体的认知节点，查看完整的上下文。
- **异步友好**：LLM 不需要等待对方回复，写完节点后即可继续自己的工作。
- **多播支持**：一个节点可以被多个 LLM 读取（如 DECISION 节点同时被 Meta-Cognitive-LLM 和 Reflective-LLM 读取）。
- **冲突可检测**：如果两个 LLM 对同一节点创建了矛盾的子节点，Meta-Cognitive 层可以检测到并解决。

#### 4.3.2 通信协议

LLM 间通信的"协议"不是传统 API 调用，而是**结构化认知节点的读写规范**：

| 操作 | 说明 | 示例 |
|------|------|------|
| **CREATE** | 创建新节点 | Planning-LLM 创建 DECISION 节点 |
| **READ** | 读取节点内容 | Meta-Cognitive-LLM 读取 DECISION 节点 |
| **UPDATE** | 更新节点状态（不改变内容） | 将 PENDING 更新为 VALIDATED |
| **FORK** | 基于现有节点创建新版本（修改内容） | 修正错误的 HYPOTHESIS 节点 |
| **LINK** | 创建两个节点之间的边 | 添加 DERIVES 或 CONTRADICTS 边 |
| **SUBSCRIBE** | 订阅某类节点的创建事件 | Meta-Cognitive-LLM 订阅所有 DECISION 节点 |
| **QUERY** | 查询满足条件的节点 | "查找所有 status=INVALIDATED 的节点" |

**节点的访问控制**：
- 每个 LLM 实例有**读写权限**，限制其可以创建/修改哪些类型的节点。
- 例如：Planning-LLM 只能创建 REASONING、DECISION、ALTERNATIVE 节点；不能修改 VALIDATION 节点（那是 Meta-Cognitive-LLM 的权限）。

### 4.4 与 Topic Tree 的交叉引用

#### 4.4.1 引用机制

Cognitive Tree 的节点可以引用 Topic Tree 的节点（反之亦然）：

```
C-50: HYPOTHESIS "用户意图是 SCAN_MEMORY"
  C-50.topic_refs = [T-12]  // 引用 Topic Tree 的节点 T-12（"用户提到扫描内存"）
  C-50.topic_refs = [T-13]  // 引用 T-13（"用户提到第一次扫描"）
```

这种引用的作用：
- **证据链**：Cognitive Tree 的推理可以追溯回用户对话的具体内容。
- **反事实分析**：如果 Topic Tree 的某个节点被修正（如用户澄清了误解），所有引用该节点的 Cognitive Tree 节点也需要重新评估。
- **可视化**：开发者可以查看"针对用户的这句话，系统是怎么推理的"。

#### 4.4.2 引用的一致性维护

当 Topic Tree 发生变化时（如用户删除或修改了某条消息），系统需要：

1. 找到所有引用该 Topic Tree 节点的 Cognitive Tree 节点。
2. 标记这些认知节点为 "needs_revalidation"（需要重新验证）。
3. 触发 Meta-Cognitive 层进行快速验证。
4. 如果验证失败，标记为 INVALIDATED，并触发上游重新推理。

---

## 5. 穿透层 LLM（回答 LLM）

### 5.1 回答 LLM 的特殊地位

回答 LLM（Answer LLM）是系统中**唯一直接面对用户**的 LLM 实例。它有以下特殊特征：

1. **双重身份**：它既是用户接口的"客服"（生成自然语言回复），又是系统认知网络的一部分（其思考过程进入 Cognitive Tree）。
2. **穿透性**：它"穿透"整个系统，读取所有层的输出（算法结果、LLM 结果、Cognitive Tree 的活跃分支），然后综合生成用户回复。
3. **受控性**：它的回复不是自由发挥的，而是**受系统约束的**（如用户画像决定的详细度、Skill 模板决定的回复结构、Meta-Cognitive 层决定的置信度声明）。

### 5.2 回答 LLM 的输入

回答 LLM 的输入是一个**综合上下文包**，包含：

```
AnswerContext = {
  // 用户层
  user_input: 用户原始输入,
  user_profile: 用户认知画像（Track A + Track B）,
  topic_tree: 用户话题树的当前活跃分支,
  
  // 系统层（算法 + Hybrid Layer）
  algorithm_result: 算法引擎的最终输出,
  llm_result: LLM 引擎的最终输出,
  fusion_mode: 融合模式（A-only / B-only / weighted），
  
  // 认知层（Cognitive Tree）
  active_cognitive_branch: 当前活跃的认知推理链（最近 3-5 个节点），
  system_confidence: 系统对当前决策的整体置信度,
  known_uncertainties: 系统已知的歧义和不确定性（用于诚实声明），
  
  // 约束层（Meta-Cognitive）
  response_constraints: {
    style: 响应风格（BRIEF / BALANCED / EXPLANATORY / TUTORIAL）,
    structure: 回复结构（如果有 Skill 模板指定）,
    max_length: 最大长度,
    honesty_required: 是否必须声明不确定性（如果系统置信度 < 0.7）
  },
  
  // 记忆层
  relevant_memories: 与当前话题相关的记忆组块（从记忆系统检索）
}
```

### 5.3 回答 LLM 与系统内 LLM 的强关联

回答 LLM 不是独立工作的，它与系统内 LLM 形成**紧密的认知回路**。

**关联 1：实时约束注入**

- Planning-LLM 生成了一个任务计划，这个计划的结构被注入到回答 LLM 的提示词中（"请按照以下步骤向用户解释..."）。
- Meta-Cognitive-LLM 检测到某个决策有不确定性，要求回答 LLM 在回复中声明："我对这个推断不是完全确定，如果您确认..."

**关联 2：Cognitive Tree 的读写**

- 回答 LLM 在生成回复前，会在 Cognitive Tree 中创建一个 HYPOTHESIS 节点："我计划这样回复用户..."
- Meta-Cognitive-LLM 可以读取这个 HYPOTHESIS，验证其是否合适（"这个回复对于低元认知用户太简略了"）。
- 如果验证不通过，Meta-Cognitive-LLM 创建 REFLECTION 节点，回答 LLM 读取后修正回复。

**关联 3：用户反馈的回路**

- 用户收到回复后表达满意/不满意。
- 这个反馈被记录到 Cognitive Tree（作为 OBSERVATION 节点）。
- 所有参与生成该回复的 LLM 实例（Planning-LLM、Answer-LLM）读取这个反馈，更新其认知模型。
- Meta-Cognitive-LLM 分析"为什么用户对这次回复不满意"，生成改进建议。

### 5.4 回答 LLM 的幻觉问题

回答 LLM 是**幻觉风险最高的 LLM 实例**，因为它直接面对用户，其输出无法被系统内部验证（不像工具调用可以被 Schema Guard 验证）。

**缓解策略**：

1. **系统置信度注入**：如果系统对某个决策的整体置信度 < 0.7，回答 LLM 必须声明不确定性（"我不太确定，但我的最佳推断是..."）。
2. **约束回复结构**：使用 Skill 模板限制回答 LLM 的自由度（如电商场景下，回复必须包含"订单确认"、"预计送达"等字段）。
3. **Cognitive Tree 回溯**：回答 LLM 在生成回复时，必须在 Cognitive Tree 中引用其推理链（"我这样说是因为系统推断用户的意图是 X"）。如果无法找到推理链，回答 LLM 必须声明"我不知道"而不是编造。
4. **Meta-Cognitive 预审**：对于高风险回复（如涉及金融、医疗的建议），Meta-Cognitive 层在回复发送前进行快速预审。

---

## 6. LLM 间通信协议

### 6.1 通信协议的形式化

LLM 间通信不是通过函数调用或消息队列，而是通过**Cognitive Tree 的共享读写**。这种通信方式的形式化定义：

```
通信协议 = (CognitiveTree, AccessControl, EventBus, Schema)

CognitiveTree: 共享的认知树结构（定义见第 4 节）
AccessControl: 每个 LLM 实例的读写权限矩阵
EventBus: 节点创建/更新/删除的事件总线
Schema: 每种节点类型的字段规范和验证规则
```

### 6.2 访问控制矩阵

| LLM 实例 | 可创建的节点类型 | 可读取的节点类型 | 可修改的节点类型 | 不可触碰的节点类型 |
|---------|----------------|----------------|----------------|------------------|
| **PCR-LLM** | PERCEPTION, HYPOTHESIS | PERCEPTION, HYPOTHESIS | 自己创建的 | VALIDATION, LEARNING |
| **Intent-LLM** | HYPOTHESIS, REASONING | PERCEPTION, HYPOTHESIS | 自己创建的 | VALIDATION, DECISION（其他 LLM 的） |
| **Planning-LLM** | REASONING, DECISION, ALTERNATIVE | HYPOTHESIS, REASONING, DECISION | 自己创建的 | VALIDATION（不能自我验证） |
| **Meta-Cognitive-LLM** | VALIDATION, REFLECTION | 所有类型 | 任何节点的 status | 无（只读权限例外） |
| **Reflective-LLM** | LEARNING, REFLECTION | 所有类型 | 无（只创建新节点） | 无（只读） |
| **Answer-LLM** | HYPOTHESIS（回复计划） | 所有类型（用于上下文） | 自己创建的 | VALIDATION, DECISION（其他 LLM 的） |

**约束说明**：
- LLM 只能修改自己创建的节点（除了 Meta-Cognitive-LLM 可以修改任何节点的 status）。
- 这防止了 LLM 互相篡改对方的认知输出（避免"认知冲突"）。
- Meta-Cognitive-LLM 的"超级权限"是合理的：它负责验证，必须能标记任何节点的状态。

### 6.3 事件总线（Event Bus）

Event Bus 用于**异步通知** LLM 实例 Cognitive Tree 中发生了感兴趣的事件。

| 事件类型 | 触发条件 | 订阅者 | 示例 |
|---------|---------|--------|------|
| **NODE_CREATED** | 新节点被创建 | 所有 LLM（可选过滤） | Planning-LLM 创建了 DECISION 节点 → Meta-Cognitive-LLM 收到通知 |
| **STATUS_CHANGED** | 节点状态变化 | 依赖该节点的 LLM | C-100 从 PENDING 变为 VALIDATED → Planning-LLM 继续执行 |
| **CONFLICT_DETECTED** | 检测到矛盾边 | Meta-Cognitive-LLM | C-50 和 C-51 之间被添加了 CONTRADICTS 边 → 触发验证 |
| **BRANCH_SWITCHED** | 活跃分支切换 | 所有活跃 LLM | 系统从分支 A 切换到分支 B → 相关 LLM 重新加载上下文 |
| **USER_FEEDBACK** | 用户表达反馈 | 所有参与该轮决策的 LLM | 用户说"这个回复不好" → Answer-LLM、Planning-LLM 收到通知 |
| **SESSION_ENDED** | 会话结束 | Reflective-LLM | 触发长期复盘 |

**事件过滤**：每个 LLM 实例可以订阅特定类型的事件，并设置过滤条件（如"只接收 source_llm='Planning-LLM' 且 cog_type='DECISION' 的节点"）。

### 6.4 通信的延迟与一致性

**延迟模型**：
- Cognitive Tree 的读写是**内存操作**（Redis + 内存缓存），延迟 < 1ms。
- LLM 实例之间的"通信延迟"主要取决于 LLM 自身的推理时间（50-500ms），而不是树操作的时间。
- 因此，Cognitive Tree 作为通信媒介不会引入额外延迟。

**一致性模型**：
- 使用**最终一致性**：LLM 实例写入节点后，其他 LLM 可能短暂读取到旧版本，但在 100ms 内同步。
- 对于冲突检测（如两个 LLM 同时修改同一节点），使用**乐观锁**：写入时检查版本号，如果版本冲突，则后写入者失败并重新读取。
- Meta-Cognitive-LLM 的验证操作是**原子性的**：验证一个节点时，锁定该节点及其下游依赖，防止其他 LLM 在验证期间修改。

---

## 7. 幻觉检测与缓解机制

### 7.1 幻觉的分类与量化

在 v3.0 架构中，幻觉不再是一个单一的"LLM 说假话"问题，而是一个**多维度的认知偏差问题**。

| 幻觉类型 | 定义 | 量化指标 | 检测层 |
|---------|------|---------|--------|
| **事实幻觉** | 陈述与客观事实不符 | 工具存在性、参数合法性、返回结果一致性 | Layer 2.5 (Schema Guard) |
| **逻辑幻觉** | 推理过程存在逻辑谬误 | 前提-结论一致性、循环依赖、矛盾推导 | Layer 2.5 (Consistency Check) |
| **引用幻觉** | 引用不存在的上下文 | 引用节点存在性、引用内容一致性 | Layer 2.5 (Factuality Check) |
| **置信幻觉** | 过度自信或过度保守 | 置信度校准误差（预测置信度 vs 实际准确率） | Layer 2.5 + Layer 3 |
| **策略幻觉** | 选择不存在的策略或模式 | 策略合法性、模式存在性 | Layer 2.5 (Plausibility Check) |
| **累积幻觉** | 早期错误在后续推理中被放大 | 错误传播链长度、下游受影响节点数 | Layer 3 (Tree Analysis) |
| **自我幻觉** | LLM 对自身状态的误判 | 自我描述与实际行动的一致性 | Layer 3 (Reflective Analysis) |

### 7.2 三层防御体系

系统对幻觉采用**纵深防御**策略：

**第一层：实时拦截（Layer 1.5）**

- Schema Guard：工具调用参数校验
- 规则守卫：硬编码的不变量检查（如"订单金额不能为负"）
- 快速路径：高置信度算法结果绕过 LLM，减少 LLM 介入机会

**第二层：跨轮验证（Layer 2.5）**

- 事实性验证：检查 LLM 声明与外部世界的一致性
- 一致性验证：检查 LLM 输出与系统内部状态的一致性
- 合理性验证：检查 LLM 输出是否符合常识和领域约束

**第三层：长期复盘（Layer 3）**

- 系统性偏见检测：识别 LLM 的重复性错误模式
- 置信度校准：调整 LLM 的置信度输出，使其更真实地反映准确率
- 算法盲区识别：识别规则引擎无法覆盖的幻觉场景

### 7.3 置信度校准（Confidence Calibration）

LLM 的置信度输出往往是**错误校准的**（miscalibrated）：LLM 可能以 0.9 的置信度说出一个错误答案，或以 0.3 的置信度说出一个正确答案。

**校准算法**：

将 LLM 的置信度分为 K 个区间（如 [0,0.2), [0.2,0.4), ..., [0.8,1.0]），计算每个区间内的实际准确率：

$$CalibrationError = \sum_{k=1}^{K} \frac{n_k}{N} |acc_k - conf_k|$$

其中 $n_k$ 是区间 $k$ 的样本数，$acc_k$ 是区间 $k$ 的实际准确率，$conf_k$ 是区间 $k$ 的平均置信度。

**校准策略**：
- 如果 $CalibrationError > 0.1$，触发置信度校准。
- 校准方法：对每个区间的置信度进行线性缩放（Platt Scaling）或等渗回归（Isotonic Regression）。
- 校准后的置信度用于融合器的加权决策。

### 7.4 幻觉的恢复机制

当检测到幻觉时，系统不立即崩溃，而是**优雅降级**：

```
检测到幻觉
  │
  ├── 事实幻觉（工具不存在）
  │   └── 回退：使用 ask_user 工具请求用户确认
  │
  ├── 逻辑幻觉（推理矛盾）
  │   └── 回退：切换到 Cognitive Tree 的备选分支（如果有）
  │   └── 如果无备选：回退到算法引擎的保守输出
  │
  ├── 引用幻觉（上下文不存在）
  │   └── 回退：忽略该引用，基于可用上下文重新推理
  │
  ├── 置信幻觉（过度自信）
  │   └── 回退：降低置信度，触发用户澄清
  │
  └── 累积幻觉（错误传播）
      └── 回退：从最早出错的节点开始，重新推理整条链
```

---

## 8. 与现有架构的集成

### 8.1 对 v2.0 的兼容性策略

v3.0 不是推翻 v2.0，而是在 v2.0 的基础上**叠加 LLM 认知层**。兼容性策略：

- **Layer 0-3 的算法引擎**：保持不变，作为基线系统运行。
- **LLM 层（Layer 1.5-3）**：可选启用，通过配置开关控制。
- **Cognitive Tree**：如果禁用 LLM 层，Cognitive Tree 退化为空树（不影响算法引擎）。
- **Topic Tree**：不受影响，继续使用 v2.0 的实现。
- **用户画像**：v2.0 的 Track A/B 继续维护，v3.0 的 Reflective 层提供更深层更新。

### 8.2 渐进启用路线图

| 阶段 | 启用内容 | 影响 | 风险 |
|------|---------|------|------|
| **Phase 1** | Hybrid Layer（PCR-LLM + Intent-LLM） | 实时层增强，延迟增加 50-100ms | 低（算法结果作为 fallback） |
| **Phase 2** | Planning-LLM + Cognitive Tree | 动态规划增强，Skill 填充更智能 | 中（需要监控幻觉率） |
| **Phase 3** | Meta-Cognitive Layer | 验证与监督，显著降低幻觉 | 中（需要调优触发条件） |
| **Phase 4** | Reflective Layer + 跨会话学习 | 长期优化，系统持续改进 | 高（需要防止过度拟合） |
| **Phase 5** | Answer-LLM 全面替代规则回复 | 用户体验质变，但回复质量完全依赖 LLM | 高（需要完整的幻觉防御） |

### 8.3 性能预算

引入多层 LLM 后的性能预算：

| 层级 | 单次延迟 | 每轮调用次数 | 每轮总延迟 | 成本（tokens） |
|------|---------|-------------|-----------|--------------|
| **Hybrid Layer** | 50-200ms | 2-3 次（PCR+Intent+Planning） | 100-300ms | 2K-5K |
| **Meta-Cognitive** | 200-500ms | 0.3 次（平均每 3 轮触发 1 次） | 60-150ms（均摊） | 1K-3K（均摊） |
| **Reflective** | 1-5s | 0.05 次（每 20 轮触发 1 次） | 50-250ms（均摊） | 5K-10K（均摊） |
| **Answer-LLM** | 100-500ms | 1 次 | 100-500ms | 1K-3K |
| **总计** | — | — | 310-1200ms | 4K-12K |

**优化策略**：
- 使用小模型（7B-13B）做 Hybrid Layer，大模型（70B+）做 Meta-Cognitive 和 Reflective。
- 缓存 LLM 的频繁输出（如相同的意图推断结果）。
- 异步运行 Meta-Cognitive 和 Reflective，不阻塞用户响应。

---

## 9. 设计决策与权衡

### ADR-010: LLM 作为认知核心而非外挂工具

- **决策**：将 LLM 从"兜底工具"提升为"认知核心"，算法引擎作为"神经加速层"。
- **理由**：Agent 的核心特征是认知能力（感知、推理、学习、反思），这些能力 LLM 远强于规则引擎。规则引擎在模糊场景下无法达到 Agent 级别的智能。
- **后果**：系统延迟增加（从 5ms 到 300ms+）；成本增加（token 消耗增加 10-20 倍）；幻觉风险显著上升。

### ADR-011: 三层 LLM 认知层（实时/监督/复盘）

- **决策**：将 LLM 分为三层（Hybrid / Meta-Cognitive / Reflective），每层不同时间尺度和认知功能。
- **理由**：单层 LLM 无法同时满足实时性（每轮 200ms）和深度性（跨会话复盘）。分层解耦允许各层独立优化。
- **后果**：架构复杂度显著增加；LLM 间通信需要精心设计的协议；层间信息传递可能丢失上下文。

### ADR-012: 独立的 LLM Cognitive Tree

- **决策**：为 LLM 创建独立于 Topic Tree 的 Cognitive Tree，作为 LLM 的心智空间。
- **理由**：用户的对话主题和 LLM 的推理过程必须物理分离，以避免反思污染用户状态、支持 LLM 间通信、实现跨会话学习。
- **后果**：存储成本增加（需要维护第二棵树）；查询复杂度增加（需要支持跨树引用）；开发者需要理解两套树模型。

### ADR-013: LLM 间通信通过共享树而非消息传递

- **决策**：LLM 实例通过读写共享的 Cognitive Tree 进行通信，而不是传统的消息传递或函数调用。
- **理由**：树结构天然支持可追溯性、异步性和多播；节点的生命周期管理（版本、状态、依赖）提供了结构化的认知记录。
- **后果**：需要设计复杂的访问控制；节点锁和并发控制增加了实现难度；树查询性能可能成为瓶颈。

### ADR-014: 回答 LLM 的穿透式设计

- **决策**：回答 LLM 直接读取所有层的输出（算法 + LLM + Cognitive Tree），而不是通过中间层传递。
- **理由**：回答 LLM 需要最大化的上下文来生成高质量回复；中间层过滤会丢失重要的认知状态（如不确定性）。
- **后果**：回答 LLM 的提示词变得非常复杂（需要精心设计以避免上下文过载）；回答 LLM 的幻觉风险最高（因为它综合了所有信息）。

### ADR-015: 幻觉的三层纵深防御

- **决策**：对幻觉采用实时拦截（Schema Guard）+ 跨轮验证（Meta-Cognitive）+ 长期复盘（Reflective）的三层防御。
- **理由**：单层防御无法覆盖所有幻觉类型（如累积幻觉需要长期分析）；纵深防御提供了渐进降级的能力。
- **后果**：防御系统本身消耗大量计算资源；误报（将正确输出标记为幻觉）可能导致用户体验下降。

### ADR-016: 渐进启用而非一次性切换

- **决策**：v3.0 的 LLM 层按阶段渐进启用，而非一次性替换 v2.0 的算法引擎。
- **理由**：降低风险，允许逐步验证 LLM 层的可靠性；保留算法引擎作为 fallback，确保系统在 LLM 失效时仍可运行。
- **后果**：系统需要同时维护两套路径（算法 + LLM），代码复杂度增加；渐进切换需要精细的监控和回滚机制。

---

## 10. 附录

### 10.1 术语表（v3.0 新增）

| 术语 | 定义 |
|------|------|
| **Cognitive Duplex** | 认知双工：算法引擎与 LLM 引擎并行运行、融合输出的架构范式 |
| **Cognitive Tree** | LLM 心智树：LLM 的推理、假设、决策、反思的共享树结构 |
| **PERCEPTION** | 认知节点类型：对外部输入的感知记录 |
| **HYPOTHESIS** | 认知节点类型：对当前状态的假设 |
| **REASONING** | 认知节点类型：中间推理过程 |
| **DECISION** | 认知节点类型：最终决策记录 |
| **REFLECTION** | 认知节点类型：对前述认知的反思 |
| **VALIDATION** | 认知节点类型：对认知的验证结果 |
| **LEARNING** | 认知节点类型：长期学习结论 |
| **COMMUNICATION** | 认知节点类型：LLM 间通信消息 |
| **DERIVES** | 认知边类型：推导关系 |
| **CONTRADICTS** | 认知边类型：矛盾关系 |
| **ALTERNATIVE** | 认知边类型：备选方案关系 |
| **Fusion Engine** | 融合引擎：将算法结果和 LLM 结果加权融合 |
| **Hallucination Risk** | 幻觉风险：多维度的幻觉可能性量化 |
| **Confidence Calibration** | 置信度校准：调整 LLM 的置信度输出以匹配实际准确率 |
| **Shadow Mode** | 影子模式：新策略在不改变实际输出的情况下验证效果 |
| **Platt Scaling** | 普拉特缩放：一种置信度校准方法 |
| **Access Control Matrix** | 访问控制矩阵：定义每个 LLM 实例对 Cognitive Tree 的读写权限 |
| **Event Bus** | 事件总线：Cognitive Tree 的异步事件通知系统 |
| **Answer LLM** | 回答 LLM：直接面对用户的 LLM 实例，穿透所有层 |
| **Cognitive Branch** | 认知分支：Cognitive Tree 中的推理链，有 ACTIVE 和 STALE 状态 |
| **Cross-Reference** | 交叉引用：Cognitive Tree 节点与 Topic Tree 节点的双向引用 |
| **Tree Health** | 树健康度：Cognitive Tree 的结构质量评估指标 |
| **Bias Detection** | 偏见检测：识别 LLM 的系统性认知偏见 |
| **Algorithm Blind Spot** | 算法盲区：算法引擎在长期使用中的系统性失效模式 |
| **Shadow Validation** | 影子验证：新策略的并行验证机制 |

### 10.2 核心公式汇总

| 公式 | 说明 | 所在章节 |
|------|------|---------|
| $O = weighted(A, B) = \frac{c_A A + c_B B}{c_A + c_B}$ | 融合器加权融合 | 3.1.3 |
| $Conflict(A,B) = true \text{ if } A \neq B \land c_A > 0.5 \land c_B > 0.5$ | 冲突检测 | 3.1.3 |
| $FactualityScore = \frac{VerifiedFacts}{TotalClaims}$ | 事实性验证 | 3.2.3 |
| $ConsistencyScore = 1 - \frac{Conflicts}{TotalCrossChecks}$ | 一致性验证 | 3.2.3 |
| $HallucinationRisk = \alpha(1-F) + \beta(1-C) + \gamma(1-P)$ | 幻觉风险 | 3.2.4 |
| $TreeHealth = 0.25B + 0.25C + 0.25T + 0.25R$ | 树健康度 | 3.3.2 |
| $Profile_{new} = \alpha Profile_{current} + (1-\alpha)Profile_{session}$ | 画像更新 | 3.3.3 |
| $CalibrationError = \sum \frac{n_k}{N}|acc_k - conf_k|$ | 校准误差 | 7.3 |
| $Bias_{llm} = \frac{Observed - Expected}{Expected}$ | 偏见检测 | 3.3.2 |

### 10.3 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-26 | 初始架构设计（Layer 0-3 + 认知画像 v1.0） |
| v2.0 | 2026-07-19 | 重构：认知画像 v2.0（双轨）、Planning Skill Layer（正交解耦） |
| v3.0 | 2026-07-19 | 架构升级：多层 LLM 认知层（三层）、双树结构（Cognitive Tree）、认知双工范式 |

---

*本设计文档由 DialogMesh 架构团队基于认知科学理论、LLM Agent 研究和系统分析生成。核心命题：Agent 不是"带 LLM 的规则系统"，而是"以 LLM 为认知核心、算法为加速层的多认知体系统"。*
