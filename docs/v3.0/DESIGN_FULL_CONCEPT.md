# DialogMesh 系统概念设计文档 v2.0

> **文档状态**: 设计冻结 (Design Freeze)  
> **版本**: v2.0  
> **日期**: 2026-07-19  
> **范围**: 覆盖 DialogMesh 全部架构层级（Layer 0-3）及横切关注点  
> **说明**: 本文档为纯概念设计，不涉及具体代码实现，但包含算法原理、数学公式与实现概念描述。

---

## 目录

- [1. 系统概述与架构全景](#1-系统概述与架构全景)
- [2. Layer 0: Pre-Cognitive Router (PCR)](#2-layer-0-pre-cognitive-router-pcr)
- [3. Layer 1: Intent Parser](#3-layer-1-intent-parser)
- [4. Layer 1.5: Planning Skill Layer](#4-layer-15-planning-skill-layer)
- [5. Layer 2: 对话管理与状态层](#5-layer-2-对话管理与状态层)
- [6. Layer 3: 服务接口层](#6-layer-3-服务接口层)
- [7. 横切关注点：认知画像系统 v2.0](#7-横切关注点认知画像系统-v20)
- [8. 横切关注点：记忆系统](#8-横切关注点记忆系统)
- [9. 横切关注点：可观测性](#9-横切关注点可观测性)
- [10. 完整数据流与生命周期](#10-完整数据流与生命周期)
- [11. 设计决策记录](#11-设计决策记录)
- [12. 附录](#12-附录)

---

## 1. 系统概述与架构全景

### 1.1 设计哲学

DialogMesh 是一个**认知增强型对话系统**，核心设计哲学可概括为：

> **"对话不是一问一答，而是基于用户认知模型的持续推断与自适应。"**

系统通过四个关键设计原则实现这一目标：

1. **认知优先**：先理解用户的认知状态（元认知、发散性、稳定性等），再决定响应策略。
2. **正交解耦**：规划方法（Planning）与工具集（Tools）独立演化；领域知识与通用推理分离。
3. **渐进抽象**：从原始输入到最终响应，经过多层抽象（信号→意图→任务→执行→输出），每层可独立调试和优化。
4. **可计算行为特征**：所有概念（包括用户画像、对话状态、记忆权重）都必须是可量化、可衰减、可推断的。

### 1.2 架构分层

系统采用严格的分层架构，共 4 个核心层 + 3 个横切关注点：

```
┌──────────────────────────────────────────────────────────────────────┐
│ 用户接口层 (WebSocket / REST / 前端)                                │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 3: 服务接口层 (Service Layer)                                   │
│  • Session 管理  • 响应编排  • 协议转换  • 速率限制                     │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 2: 对话管理与状态层 (Dialogue & State)                         │
│  • 主题树 (Topic Tree)  • 上下文窗口 (Context Window)                  │
│  • 对话状态机  • 多轮继承机制                                         │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 1.5: 规划技能层 (Planning Skill Layer)                        │
│  • 认知编译器 (Cognitive Compiler)                                   │
│  • 通用规划原语 (Planning Primitives)                                │
│  • 领域规划模板 (Planning Skills)                                   │
│  • 混合编排引擎 (Mixed Planning Engine)                             │
│  • 动态工具规划 (Dynamic Tool Planning)                               │
│  • 工具绑定与验证 (Tool Binding & Schema Guard)                     │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 1: 意图解析层 (Intent Parser)                                  │
│  • 预处理  • 实体提取  • 意图分类  • 歧义检测与消解                     │
│  • 多意图拆分  • 上下文合并  • 任务图构建                              │
├──────────────────────────────────────────────────────────────────────┤
│ Layer 0: 预认知路由器 (Pre-Cognitive Router)                         │
│  • 噪声检测  • 期望推断  • 认知画像快速评估  • 路由决策                  │
├──────────────────────────────────────────────────────────────────────┤
│ 横切关注点：认知画像系统 (Cognitive Profile System)                   │
│  • Track A: 认知动力学 (Cognitive Dynamics)                         │
│  • Track B: 标签化信息 (Tag Layer)                                   │
│  • g 因子推断  • 时间衰减机制  • 标签获取策略                          │
├──────────────────────────────────────────────────────────────────────┤
│ 横切关注点：记忆系统 (Memory System)                                   │
│  • 记忆组块 (Memory Chunks)  • 加权指数衰减                            │
│  • 阶梯跃迁 (Hot→Warm→Cool→Cold)  • 二级摘要                            │
├──────────────────────────────────────────────────────────────────────┤
│ 横切关注点：可观测性 (Observability)                                   │
│  • 诊断层 (Diagnostics)  • 归因层 (Attribution)                       │
│  • 遥测层 (Telemetry)  • 追踪层 (Tracing)                             │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.3 核心数据契约

系统内部的数据流转依赖以下核心数据契约，贯穿所有层级：

| 数据契约 | 定义 | 流转层级 | 核心字段 |
|---------|------|---------|---------|
| **UserInput** | 用户原始输入 | L3 → L0 | `text`, `metadata`, `timestamp` |
| **PCROutput** | PCR 路由输出 | L0 → L1 | `expectation`, `noise_level`, `cognitive_profile`, `complexity_level` |
| **Intent** | 解析后的意图 | L1 → L1.5 | `category`, `entities`, `confidence`, `ambiguities` |
| **TaskGraph** | 任务依赖图 | L1.5 → L2 | `nodes`, `edges`, `intent_id` |
| **DialogueState** | 对话状态 | L2 内部 | `topic_tree`, `context_window`, `turn_history` |
| **CognitiveProfileV2** | 双轨用户画像 | 横切所有层 | `track_a`, `track_b`, `temporal_state` |
| **MemorySnapshot** | 记忆快照 | 横切 L1-L2 | `chunks`, `weights`, `stage_transitions` |

---

## 2. Layer 0: Pre-Cognitive Router (PCR)

### 2.1 功能概念

PCR 是系统的**最前端过滤器**，在完整解析之前对用户输入进行快速认知评估。其核心功能不是"理解内容"，而是"评估认知情境"——在毫秒级确定：

1. 用户的输入是否值得解析？（噪声过滤）
2. 用户期望什么样的响应模式？（期望推断）
3. 用户的当前认知状态如何？（画像快速评估）

PCR 的哲学是：**"不解析无意义的输入，不浪费计算在无价值的路由上。"**

### 2.2 核心组件

#### 2.2.1 噪声检测器 (Noise Detector)

**概念**：噪声不是"输入中的随机字符"，而是**与用户意图无关的、会降低解析质量的信号成分**。噪声检测在三个维度进行：

- **语义噪声**：输入中的填充词、无关修饰、情绪性语言
- **结构噪声**：输入的语法混乱程度、格式异常
- **参照噪声**：与对话历史不一致的引用（代词消解失败）

**噪声度量公式**（概念级）：

$$N = \alpha \cdot N_{semantic} + \beta \cdot N_{structural} + \gamma \cdot N_{referential}$$

其中：
- $N_{semantic}$：语义噪声，通过关键词密度与信息熵计算。输入中包含大量低信息熵词汇（如"那个"、"嗯"、"就是"）时得分高。
- $N_{structural}$：结构噪声，通过句法解析失败率与标点异常计算。
- $N_{referential}$：参照噪声，通过与对话历史的一致性检测计算。若用户引用前文中不存在的实体，得分高。
- $\alpha, \beta, \gamma$：权重系数，默认 $\alpha=0.5, \beta=0.3, \gamma=0.2$。

**噪声检测的实现概念**：
- 规则引擎：基于正则和词典的快速预过滤（如检测到纯表情符号则 $N=1.0$）。
- 轻量 LLM：对中等长度输入使用轻量模型（如 1B-3B 参数）进行噪声分类。
- 自适应阈值：基于用户历史噪声水平调整判定阈值。若用户平均噪声为 0.4，则当前输入 $N=0.6$ 视为高噪声；若用户平均噪声为 0.8，则 $N=0.6$ 视为正常。

#### 2.2.2 期望推断器 (Expectation Inferencer)

**概念**：用户期望不是用户"说了什么"，而是用户"希望系统怎么回应"。DialogMesh 定义三种基本期望类型：

- **TOOL（工具执行）**：用户期望系统执行一个具体动作（如"读取内存地址 0x0040"）。
- **ADVISOR（分析建议）**：用户期望系统提供分析、解释或建议（如"这段代码有什么问题？"）。
- **COMPANION（陪伴对话）**：用户期望系统进行开放式对话（如"你觉得呢？"）。

**期望推断的算法概念**：

基于**多特征贝叶斯分类**：

$$P(E \mid X) = \frac{P(X \mid E) \cdot P(E)}{P(X)}$$

其中 $E \in \{TOOL, ADVISOR, COMPANION, UNKNOWN\}$，$X$ 是特征向量。

特征向量 $X$ 包含：
- 句法特征：祈使句/疑问句/陈述句比例、情态动词（"can", "should"）出现频率
- 语义特征：操作动词（"读取"、"修改"）与认知动词（"分析"、"解释"）的比例
- 实体特征：是否存在数值、地址、具体对象等可执行实体
- 历史特征：上一轮对话的期望类型（马尔可夫假设：用户期望具有短期连续性）

**先验概率 $P(E)$ 的动态调整**：

$$P_{t}(E) = \lambda \cdot P_{global}(E) + (1-\lambda) \cdot P_{user}(E)$$

其中：
- $P_{global}(E)$：全局先验（基于训练数据集的统计）。
- $P_{user}(E)$：用户特定先验（基于该用户历史对话中各类期望的频率）。
- $\lambda$：平滑系数，新用户 $\lambda=0.9$，老用户 $\lambda=0.3$。

#### 2.2.3 认知画像快速评估 (Cognitive Profile Quick Assessment)

**概念**：PCR 不是做完整画像评估（那是横切关注点的职责），而是做**快速画像快照**——基于当前输入的特征，推断用户当前的认知状态，用于后续层级的动态调优。

**快速评估的四个维度**（与完整画像 v2.0 的 Track A 对应）：

- **元认知 (Metacognition)**：用户是否清楚自己在问什么？通过输入的精确性、自指性语言（"我想知道" vs "随便看看"）推断。
- **发散性 (Divergence)**：用户是在收敛到具体问题，还是在发散探索？通过输入的主题切换频率和词汇多样性推断。
- **稳定性 (Stability)**：用户的表达风格是否一致？通过输入长度、词汇使用、标点风格的一致性推断。
- **信心度 (Confidence)**：用户对问题的确信程度？通过情态动词（"可能"、"应该"）、不确定词（"也许"、"大概"）的频率推断。

**快速评估的实现概念**：
- 使用轻量特征工程（词典匹配 + 统计特征），无需 LLM 调用。
- 输出为 $[0,1]$ 区间的四个数值，作为后续层的控制信号。
- 与完整认知画像（横切系统）的关系：PCR 的快照是"实时读数"，完整画像是"长期模型"。两者通过时间衰减机制融合。

### 2.3 PCR 输出 (PCROutput)

PCR 的输出是后续所有层的**控制信号**，包含：

| 字段 | 类型 | 说明 | 下游使用 |
|------|------|------|---------|
| `expectation` | 枚举 | 用户期望类型 | 决定 IntentParser 的解析策略 |
| `noise_level` | float | 噪声水平 [0,1] | 影响解析阈值和澄清策略 |
| `complexity_level` | float | 复杂度评估 [0,1] | 决定任务分解粒度 |
| `cognitive_profile` | 对象 | 四维度快速快照 | 动态调优所有层的参数 |
| `execution_mode` | 枚举 | 执行模式 | 决定系统响应的保守/激进程度 |
| `parser_config_overrides` | 对象 | 解析器参数覆盖 | 直接注入 IntentParser 配置 |

### 2.4 设计决策

- **为什么 PCR 不做完整解析？** 因为完整解析（LLM 调用）成本高，PCR 用规则+轻量特征工程在毫秒级完成，过滤掉无意义输入后再进入深层解析。
- **为什么期望推断用贝叶斯而非纯规则？** 因为用户期望具有模糊性（"帮我看看这个"可能既是 TOOL 又是 ADVISOR），概率方法更适配。
- **为什么认知画像有快速评估和完整评估两个版本？** 因为快速评估需要实时响应（<5ms），完整评估需要多轮数据积累（秒级），两者通过时间衰减融合。

---

## 3. Layer 1: Intent Parser

### 3.1 功能概念

Intent Parser 是系统的**语义理解核心**，将自然语言输入转换为结构化的意图表示（Intent）。其设计哲学是：

> **"确定性优先，LLM 兜底。"**

系统在 95% 的场景下使用规则引擎完成解析，仅在规则失效时调用 LLM。这保证了可预测性、可调试性和低成本。

### 3.2 流水线架构

Intent Parser 采用**八阶段流水线**：

```
Raw Input → Preprocessor → Reference Resolver → Entity Extractor → 
Intent Classifier → Multi-Intent Splitter → Ambiguity Detector → 
Ambiguity Resolver → Context Merger → TaskGraph Builder → ParseResult
```

每个阶段都是**可配置、可观测、可跳过**的。

### 3.3 核心组件与算法

#### 3.3.1 预处理器 (Preprocessor)

**概念**：对输入进行规范化，同时根据用户认知状态进行**词汇调优**。

**核心算法**：

- **基础规范化**：去除多余空格、统一标点符号（中文标点→ASCII 等价物）、统一大小写。
- **词汇调优（稳定性感知）**：
  - 高稳定性用户（$stability \geq 0.7$）：**不扩展词汇**，因为用户用词风格一致，规则已覆盖其常用表达。
  - 低稳定性用户（$stability < 0.5$）：**收缩词汇**，去除模糊填充词（"那个"、"这个"、"东西"），避免虚假实体匹配。
  - 中等稳定性用户：保持原样，仅在分类阶段启用同义词扩展作为 fallback。

**稳定性感知的实现概念**：基于 PCR 输出的 `cognitive_profile.stability` 动态选择调优策略。

#### 3.3.2 参照消解器 (Reference Resolver)

**概念**：在实体提取**之前**解决代词和指示词引用（如"这个地址"、"那个值"），避免实体提取遗漏。

**核心算法**：

$$Ref\_target = \arg\max_{e \in H_{t-1}} P(e \mid ref, type(ref))$$

其中：
- $H_{t-1}$：上一轮对话历史中解析出的高置信度实体（$confidence \geq 0.8$）。
- $ref$：当前输入中的引用标记（如"这个地址"、"it"）。
- $type(ref)$：引用标记的类型（通过词典映射，如"地址"→ MEMORY_ADDRESS）。
- 选择策略：在历史实体中查找与引用类型匹配的最高置信度实体，将其值替换到当前输入中。

**实现概念**：维护一个跨轮的**实体缓存**（Entity Cache），存储最近 N 轮的高置信度实体。参照消解器在预处理阶段读取此缓存，将引用替换为实体值，并将继承的实体标记为"inherited"（置信度 × 0.9 衰减）。

#### 3.3.3 实体提取器 (Entity Extractor)

**概念**：从文本中抽取类型化的值（地址、数值、模块名、字节模式等）。

**核心算法**：**基于正则模式的多规则匹配**，而非 LLM 提取。

规则类型：
- 确定性模式：十六进制地址（`0x[0-9A-Fa-f]+`）、数值（`\b\d+(?:\.\d+)?\b`）、模块名（`[A-Za-z_]\w*\.(exe|dll)`）
- 条件性模式：函数名（`sub_[0-9A-Fa-f]+`）仅在 ADVISOR 模式下启用
- 复合模式：字节模式（`(?:[0-9A-Fa-f]{2}\s+){2,}`）用于 AOB 扫描

**期望感知的提取策略**：
- TOOL 模式：激进提取，所有可能实体都提取（因为用户可能执行操作）。
- ADVISOR 模式：选择性提取，只提取与分析和解释相关的实体（如条件、函数名）。
- COMPANION 模式：最小提取，只提取用户明确提及的实体。

**实体置信度计算**：

$$conf(entity) = base\_confidence \times mode\_factor \times regex\_specificity$$

其中：
- `base_confidence`：规则预设的置信度（地址 1.0，数值 0.9，函数名 0.7）。
- `mode_factor`：模式调节（TOOL=1.0, ADVISOR=0.8, COMPANION=0.6）。
- `regex_specificity`：正则表达式的特异性（精确匹配=1.0，通配符多=0.8）。

#### 3.3.4 意图分类器 (Intent Classifier)

**概念**：将输入映射到预定义的意图类别（如 SCAN_MEMORY、READ_MEMORY、DISASSEMBLE）。

**核心算法**：**多规则优先匹配 + 冲突检测 + 同义词回退**。

**规则匹配引擎**：

每个规则包含：
- 正则模式集合（触发条件）
- 必需实体类型（AND 逻辑）
- 可选实体类型（OR 逻辑，提升置信度）
- 优先级权重
- 冲突规则声明

**置信度计算**：

$$score(rule) = 0.6 \cdot pattern\_score + 0.3 \cdot entity\_score + 0.1 \cdot context\_score$$

其中：
- $pattern\_score$：模式匹配程度（完全匹配=1.0，部分匹配=0.8）。
- $entity\_score$：必需实体覆盖率 + 可选实体匹配率。
- $context\_score$：追踪深度调节（如果上一轮意图相同，提升得分）。

**冲突检测**：当两个高置信度规则（$score > 0.6$）在相同领域或声明冲突时，生成歧义标记（Ambiguity），进入歧义消解阶段。

**同义词回退**：当原始文本无规则匹配时，使用同义词扩展后的文本重新匹配一次。

**期望感知的分类调优**：
- TOOL 模式：如果最佳匹配不是工具类意图，强制提升到最近似的工具类意图（如"帮我看看"在 TOOL 模式下强制映射为 READ_MEMORY）。
- COMPANION 模式：降低分类阈值，允许低置信度匹配通过（因为用户可能在探索）。

#### 3.3.5 多意图拆分器 (Multi-Intent Splitter)

**概念**：检测用户是否在一次输入中表达了多个意图（如"先扫描内存，然后读取地址"），并将其拆分为独立的子意图。

**核心算法**：**连接词检测 + 段落实体继承**。

- **连接词检测**：通过正则检测连接词（"然后"、"接着"、"and then"、"after that"）。
- **复杂度限制**：最大拆分数量由 PCR 输出的 `complexity_level` 决定。高复杂度（>0.8）允许最多 10 个子意图，低复杂度（<0.5）最多 3 个。
- **实体继承**：每个子意图继承父意图的全部实体，但标记为"inherited"（置信度 × 0.8）。如果子意图文本中直接包含某实体，则该实体标记为"direct"（置信度不变）。

**实现概念**：拆分后每个子意图独立进入歧义检测和任务图构建阶段，最终合并为一个包含多个入口的复合 TaskGraph。

#### 3.3.6 歧义检测器 (Ambiguity Detector)

**概念**：识别解析结果中的不确定性，将其显式标记为需要澄清或自动消解。

**歧义类型**：

| 类型 | 定义 | 触发条件 | 自动消解策略 |
|------|------|---------|------------|
| **MISSING_ENTITY** | 缺少必需实体 | 高置信度意图缺少关键实体 | 低噪声时尝试默认值；高噪声时要求澄清 |
| **AMBIGUOUS_ENTITY** | 实体多义 | 同一类型有多个低置信度候选 | 无法自动消解，要求澄清 |
| **CONFLICTING_ENTITIES** | 实体冲突 | 提取的实体相互矛盾 | 无法自动消解，要求澄清 |
| **VAGUE_SCOPE** | 范围模糊 | 噪声高 + TOOL 模式但无明确操作对象 | 要求澄清 |
| **UNSUPPORTED_OPERATION** | 不支持的操作 | 意图为 UNKNOWN 且噪声高 | 要求澄清，提供建议 |
| **MULTIPLE_INTENTS** | 多意图冲突 | 规则冲突检测触发 | 无法自动消解，要求澄清 |

**噪声感知的歧义处理**：
- 低噪声（$noise < 0.5$）：歧义倾向于自动消解（用户输入清晰，有合理的默认推断）。
- 高噪声（$noise > 0.7$）：歧义倾向于要求澄清（用户输入模糊，推断风险高）。

#### 3.3.7 上下文合并器 (Context Merger)

**概念**：将当前意图与对话历史中的上下文信息进行合并，实现多轮信息继承。

**继承策略**：

- **进程上下文继承**：如果当前意图缺少 PID 或进程名，且 ParseContext 中有历史记录，自动继承（置信度 1.0）。
- **话题继承**：如果当前意图与上一轮意图类别相同，且追踪深度（tracking_depth）> 0.6，则继承上一轮的非数值实体（置信度 × 0.9）。
- **实体缓存更新**：将当前高置信度实体（≥ 0.8）写入跨轮实体缓存，供下一轮参照消解使用。

**实现概念**：ParseContext 是跨轮状态容器，每个 session 维护一个实例。IntentParser 的每次调用都读取和更新 ParseContext。

#### 3.3.8 任务图构建器 (TaskGraph Builder)

**概念**：将解析后的意图转换为可执行的 TaskGraph（有向无环图）。

**期望感知的任务图模板**：

- **TOOL 模式**：最小任务图，单节点（直接映射到工具）。
- **COMPANION 模式**：对话式任务图，在末尾添加主动询问节点（"还有什么想分析的吗？"）。
- **ADVISOR 模式**：完整分析任务图，每个操作节点后添加解释节点，并添加 FALLBACK 边（操作失败时回退到询问）。

**意图到工具的映射**：使用分类映射表（Category → Tool Name），支持主工具和备选工具（fallback chain）。例如：
- SCAN_MEMORY → 主工具：first_scan，备选：next_scan, ask_user
- READ_MEMORY → 主工具：read_memory，备选：ask_user

### 3.4 快速路径 (Fast Path)

**概念**：当输入高度明确时（所有实体高置信度 + 意图强匹配），跳过中间阶段（多意图拆分、歧义检测、歧义消解），直接构建任务图。

**触发条件**：

$$FastPath = \left( \forall e \in Entities: conf(e) \geq \theta_{entity} \right) \land \left( conf(intent) \geq \theta_{intent} \right)$$

其中 $\theta_{entity}$ 和 $\theta_{intent}$ 是自适应阈值，基于用户认知画像调整（默认 0.85 和 0.40，高信心用户可提升）。

**快速路径的价值**：覆盖约 60-70% 的常规输入，将解析延迟从 200-500ms 降至 5-10ms。

---

## 4. Layer 1.5: Planning Skill Layer

### 4.1 功能概念

Planning Skill Layer 是 DialogMesh 的**任务规划中枢**，解决核心问题：

> **"给定一个意图和一组可用工具，如何生成一个最优的执行计划？"**

其设计哲学是：**Planning 与 Tools 正交解耦**——规划方法（如何做）与工具集（做什么）是独立演化的两个抽象层。这实现了：

1. **零工具场景可用**：即使没有工具，系统仍能基于通用规划逻辑进行推理和规划。
2. **即插即用扩展**：上传 API 文档即可自动纳入规划，无需修改规划逻辑。
3. **领域深度可控**：通过 Skill 模板提供领域知识，但用户可以选择不使用 Skill（纯动态模式）。

### 4.2 架构组件

Planning Skill Layer 包含 6 个核心组件：

```
Planning Skill Layer
├── 通用规划原语库 (Primitive Library)
│   └── 17 个跨领域认知模式
├── 领域规划模板库 (Skill Registry)
│   └── 30-50 个领域模板 + 用户自定义
├── 混合编排引擎 (Mixed Planning Engine)
│   ├── 模式检测器
│   ├── 模式选择器
│   └── 回退协调器
├── 动态工具规划器 (Dynamic Tool Planner)
│   ├── 工具筛选器 (Tool Shortlister)
│   └── LLM 规划器 (LLM Planner)
├── 工具绑定引擎 (Tool Binding Engine)
└── 验证与执行守卫 (Schema Guard + Executor)
```

### 4.3 通用规划原语库 (Primitive Library)

#### 4.3.1 设计哲学

通用规划原语是**跨领域、跨任务、不依赖具体工具**的认知模式抽象。它们从三个来源提炼：

1. **认知科学**：人类问题解决理论（Newell & Simon, 1972）
2. **LLM Agent 研究**：ReAct、CoT、ToT、Plan-and-Solve 等
3. **软件工程**：设计模式（如管道、分治、迭代器）

每个原语回答的问题是：**"面对一个目标，如何系统地思考、分解、执行、验证？"**

#### 4.3.2 五维分类模型

基于文献 "Understanding Planning of LLM Agents"（Yang et al., 2024）的五维框架：

| 维度 | 原语示例 | 核心问题 |
|------|---------|---------|
| **分解 (Decomposition)** | SequentialDecomposition, HierarchicalDecomposition, DivideConquer | "如何将大目标拆分为小步骤？" |
| **分配 (Allocation)** | SingleAgent, ParallelMap, RoleBasedCollaboration | "如何分配资源/角色到子任务？" |
| **排序 (Ordering)** | SequentialFlow, ConditionalBranch, LoopUntil, PriorityQueue | "如何确定步骤的执行顺序？" |
| **资源 (Resource Management)** | SearchRetrieve, SearchVerifyExecute, MemoryAugmented | "如何利用外部资源？" |
| **反思 (Reflection)** | PlanExecuteReflect, TreeOfThought, ReflectRetry, EarlyTermination | "如何评估和改进计划？" |

#### 4.3.3 原语的形式化定义

每个原语是一个**拓扑模板生成器**，输出一个 TaskGraph 骨架（工具名为占位符）。

**原语的结构定义**：

- **元信息**：名称、描述、适用场景、复杂度评级
- **拓扑模板**：节点（步骤）和边（依赖关系）的预设结构
- **参数化接口**：占位符（如 `search_tool`），等待绑定层填充
- **约束规则**：前置条件、后置条件、不变量

**示例：PlanExecuteReflect 原语**

拓扑模板：
```
[Plan] → [Execute] → [Evaluate] → [Reflect] → [Iterate?] → [Plan] ...
                                      ↓ (终止条件)
                                    [Finalize]
```

约束：
- `max_iterations`：最大循环次数（默认 5）
- `improvement_threshold`：改进阈值（低于此值则终止）
- 终止条件：$iteration \geq max\_iterations \lor improvement \leq threshold$

#### 4.3.4 原语清单

| ID | 名称 | 维度 | 拓扑特征 | 复杂度 |
|----|------|------|---------|--------|
| P1 | SequentialDecomposition | 分解 | 线性链 | ★ |
| P2 | HierarchicalDecomposition | 分解 | 树状层级 | ★★ |
| P3 | DivideConquer | 分解 | 并行子问题 + 合并 | ★★ |
| P4 | SingleAgent | 分配 | 单节点串行 | ★ |
| P5 | ParallelMap | 分配 | 多节点并行 → 同步点 | ★★ |
| P6 | RoleBasedCollaboration | 分配 | 多角色并行 → 协作点 | ★★★ |
| P7 | SequentialFlow | 排序 | 顺序依赖链 | ★ |
| P8 | ConditionalBranch | 排序 | 条件分叉（if-else） | ★★ |
| P9 | LoopUntil | 排序 | 循环回边 | ★★ |
| P10 | PriorityQueue | 排序 | 按优先级排序执行 | ★★ |
| P11 | SearchRetrieve | 资源 | 搜索 → 获取 | ★ |
| P12 | SearchVerifyExecute | 资源 | 搜索 → 验证 → 执行（失败则重搜） | ★★★ |
| P13 | MemoryAugmented | 资源 | 检索历史 → 增强当前决策 | ★★ |
| P14 | PlanExecuteReflect | 反思 | 计划 → 执行 → 评估 → 反思 → 迭代 | ★★★ |
| P15 | TreeOfThought | 反思 | 多分支 → 评估 → 选择最优 → 执行 | ★★★ |
| P16 | ReflectRetry | 反思 | 执行 → 失败 → 反思 → 重试 | ★★ |
| P17 | EarlyTermination | 反思 | 条件触发 → 提前终止 | ★★ |

### 4.4 领域规划模板 (Planning Skill)

#### 4.4.1 概念定义

Planning Skill 是**基于通用原语组合的领域特定规划模板**。与通用原语的区别：

| 维度 | 通用原语 | Planning Skill |
|------|---------|---------------|
| 领域绑定 | 无（跨领域） | 有（特定领域） |
| 工具依赖 | 无（占位符） | 弱（推荐工具标签） |
| 知识来源 | 认知科学 + 算法 | 行业最佳实践 + 用户经验 |
| 可复用性 | 高（任何任务） | 中（同领域任务） |
| 数量 | 少（17 个） | 多（可扩展至数百） |

#### 4.4.2 Skill 的结构定义

每个 Skill 包含：

- **标识**：skill_id, name, description, version
- **领域**：domain_tags, intent_categories（匹配的意图类别）
- **原语组合**：primitives（使用的通用原语列表）
- **步骤模板**：step_templates（TaskNode 的模板，工具名为占位符）
- **工具提示**：tool_hints（推荐工具标签，非强制绑定）
- **约束**：constraints（领域规则，如"必须先检查库存再下单"）
- **详细度**：level（SKELETON / STANDARD / DETAILED）

#### 4.4.3 详细度三级模型

| 级别 | 定义 | LLM 自由度 | 适用场景 |
|------|------|-----------|---------|
| **SKELETON** | 仅流程骨架（3-5 个步骤），无具体参数 | 最高（LLM 填充全部细节） | 探索性任务、新领域 |
| **STANDARD** | 标准模板（5-10 个步骤），有推荐工具标签 | 中高（LLM 调整步骤 + 填充工具） | 常见领域任务 |
| **DETAILED** | 详细模板（10+ 步骤），包含约束和参数提示 | 最低（LLM 仅填充工具名和参数） | 合规严格、流程不可变 |

#### 4.4.4 示例 Skill：电商下单流程

**步骤模板**（骨架）：
1. 搜索商品 (`search_tool`)
2. 比较价格 (`compare_tool`)
3. 检查库存 (`inventory_tool`)
4. 应用优惠券 (`coupon_tool`)
5. 创建订单 (`order_tool`)
6. 处理支付 (`payment_tool`)
7. 确认订单 (`notification_tool`)

**约束**：
- 前置：`place_order` 必须在 `check_inventory` 之后（必须先确认库存）
- 前置：`process_payment` 必须在 `place_order` 之后（必须先创建订单）
- 不变量：`order_total \geq 0`（订单金额不能为负）

**工具提示**：
- `search_tool` → 标签：["search", "product", "catalog"]
- `payment_tool` → 标签：["payment", "transaction", "pay"]

### 4.5 混合编排引擎 (Mixed Planning Engine)

#### 4.5.1 核心职责

Mixed Planning Engine 是 Planning Skill Layer 的**中央调度器**，负责：

1. **Skill 检测**：判断用户意图是否与某个 Skill 匹配
2. **模式选择**：决定使用 DYNAMIC、SKILL_ENHANCED 还是 MIXED 模式
3. **混合编排**：将 Skill 模板与 LLM 动态推理融合
4. **回退机制**：执行失败时自动切换模式

#### 4.5.2 三种运行模式

**模式 A: DYNAMIC（纯动态模式）**

**条件**：无高匹配 Skill（匹配度 < 0.5），或用户认知画像表明高自主能力。

**行为**：
- 将通用规划原语库注入 LLM 提示词（作为"规划方法参考"）
- LLM 选择适合的原语组合，自主生成 TaskGraph 骨架
- 工具名为占位符（如 `search_tool`），等待绑定层填充
- 多计划生成（3 个候选，temperature 0.2/0.5/0.8），自我反思筛选最优

**适用场景**：探索性任务、创意任务、无 Skill 覆盖的新领域、高元认知用户。

**模式 B: SKILL_ENHANCED（Skill 增强模式）**

**条件**：有中匹配 Skill（匹配度 0.5-0.8），或用户认知画像表明需要引导。

**行为**：
- Skill 提供流程骨架（TaskGraph 模板）
- LLM 根据实际工具列表，将占位符替换为具体工具名
- LLM 可根据意图调整步骤（跳过不相关步骤、添加缺失步骤）
- 约束验证：确保最终计划不违反 Skill 的约束规则

**适用场景**：有领域知识但需灵活调整、用户意图与 Skill 部分匹配。

**模式 C: MIXED（混合模式）**

**条件**：有高匹配 DETAILED Skill（匹配度 > 0.8），且场景对流程完整性要求高。

**行为**：
- Skill 提供**严格骨架**，标记"不可修改"的步骤
- LLM **只填充**可修改区域（工具名、参数值）
- 骨架不可增删改，保持流程完整性
- 若用户意图与 Skill 不完全匹配，使用条件分支处理

**适用场景**：金融合规、医疗流程、电商订单、任何步骤不可跳过的场景。

#### 4.5.3 模式选择决策树

```
用户意图 + 可用 Skills
  │
  ├── 最高匹配度 > 0.8 ?
  │   ├── 是 → Skill.level == DETAILED ?
  │   │   ├── 是 → MIXED 模式
  │   │   └── 否 → SKILL_ENHANCED 模式
  │   └── 否 → 最高匹配度 > 0.5 ?
  │       ├── 是 → 用户元认知 > 0.7 ?
  │       │   ├── 是 → DYNAMIC 模式（用户不需要模板）
  │       │   └── 否 → SKILL_ENHANCED 模式（用户需要引导）
  │       └── 否 → DYNAMIC 模式（无匹配 Skill）
  │
  └── 画像调优（覆盖上述决策）：
      ├── 高发散性 + MIXED → 降级为 SKILL_ENHANCED
      ├── 低 g 因子 + DYNAMIC → 升级为 SKILL_ENHANCED（如果有中匹配 Skill）
      └── 领域标签精确匹配 → 强制 SKILL_ENHANCED
```

#### 4.5.4 回退链

执行失败时的自动回退序列：

$$MIXED \rightarrow SKILL\_ENHANCED \rightarrow DYNAMIC \rightarrow FALLBACK(ask\_user)$$

每级失败都会记录失败原因，用于后续优化模式选择策略。

### 4.6 动态工具规划器 (Dynamic Tool Planner)

#### 4.6.1 工具注册中心 (Tool Registry)

**概念**：统一管理所有可用工具的 Schema 和执行句柄，支持运行时注册、注销、热更新。

**核心数据结构**：

- **ToolSchema**：工具的标准化描述，包含：
  - name（全局唯一，格式：`{source_id}_{operation_name}`）
  - description（功能描述，用于 LLM 理解）
  - parameters（JSON Schema 格式的参数定义）
  - source（来源：BUILTIN / API_DOC / MCP / CUSTOM）
  - tool_type（类型：LOCAL_FUNCTION / HTTP_API / MCP_REMOTE）
  - tags（分类标签，用于筛选）
  - estimated_latency_ms / estimated_cost_tokens（性能与成本预估）
  - is_destructive（是否涉及写操作）

- **ToolRegistration**：包含 Schema + 可执行句柄 + 执行统计（调用次数、成功率、平均延迟）

**注册机制**：
- 内置工具：系统启动时注册
- API 文档工具：通过 APIDocPreprocessor 解析 OpenAPI/Swagger/JSON Schema/自然语言描述后注册
- MCP 工具：通过 MCP 协议动态发现后注册
- 自定义工具：用户通过 API 注册

**Schema 变更检测**：基于内容哈希（SHA-256）检测 Schema 变更，支持热更新。

#### 4.6.2 工具筛选器 (Tool Shortlister)

**概念**：解决 **Tool Overflow** 问题——当工具数量超过 LLM 上下文窗口承载能力时，从全部工具中筛选最相关的子集。

**核心算法**：**多级漏斗筛选**

$$Selected = Truncate(Capacity, Rank(HistoryBoost(SemanticScore(Filter(Intent, AllTools)))))$$

**阶段 1: 意图标签匹配（粗筛）**

基于 IntentCategory 与工具标签的精确匹配：

$$Filter_{tag}(T) = \{t \in T \mid tags(t) \cap tags(intent) \neq \emptyset\}$$

如果标签匹配结果为空，放宽到全部工具（避免过度过滤）。

**阶段 2: 语义相似度排序（精排）**

基于意图描述与工具描述的相似度：

$$SemanticScore(t) = \cos(embed(intent), embed(description(t)))$$

如果 embedding 模型不可用，降级为关键词重叠启发式：

$$KeywordScore(t) = \frac{|words(intent) \cap words(description(t))|}{max(|words(intent)|, |words(description(t))|)}$$

**阶段 3: 历史偏好 boost（个性化）**

基于用户历史调用成功率提升排名：

$$HistoryBoost(t) = success\_rate(t) \times min(1, \frac{call\_count(t)}{10}) \times 0.1$$

常用且成功的工具自然上浮，但 boost 不超过 10%。

**阶段 4: 容量截断（上下文窗口限制）**

保守估计每个工具描述约 200 tokens，默认注入 LLM 的最大工具数为 32。

$$Selected = TopK(\{t \in T \mid score(t) > 0\}, K=32)$$

**阶段 5: 兜底策略**

强制保留通用工具（`ask_user`, `finish`），确保 LLM 始终有澄清和终止选项。

#### 4.6.3 LLM 规划器 (LLM Planner)

**概念**：基于筛选后的工具子集，让 LLM 自主生成 TaskGraph。

**多计划生成策略**：

- 生成 3 个候选计划，使用不同 temperature（0.2, 0.5, 0.8）增加多样性
- 温度分布：低温度保证可用性，高温度探索创造性

**自我反思与筛选**：

基于 4 维度评分（无需额外 LLM 调用）：

1. **工具存在性**：引用的工具是否在可用列表中
2. **参数完整性**：必填参数是否已提供或有获取策略
3. **依赖合理性**：是否存在循环依赖（DAG 验证）
4. **意图覆盖**：计划是否覆盖了用户的全部意图

$$PlanScore = 0.3 \cdot ValidTools + 0.3 \cdot CompleteParams + 0.2 \cdot DAGValid + 0.2 \cdot IntentCoverage$$

选择得分最高的计划。

**Fallback 策略**：

如果全部候选失败，返回最小可用计划（`ask_user` 询问用户）。

### 4.7 工具绑定引擎 (Tool Binding Engine)

**概念**：将 Planning 层生成的占位符（如 `search_tool`）绑定到 Tool 层的实际工具（如 `github_api_search_repos`）。

**绑定策略优先级**：

1. **精确匹配**：占位符去掉 "_tool" 后缀与工具名包含关系匹配（如 `search_tool` → `search_laptop`）
2. **标签匹配**：基于 Skill 的 tool_hints 和工具标签的交集匹配
3. **语义匹配**：基于描述文本的 embedding 相似度
4. **参数兼容**：检查工具的参数 Schema 是否能满足步骤的需求

**绑定置信度**：

$$BindingConfidence = \max(ExactMatch, TagMatch, SemanticMatch, ParamCompat)$$

低置信度绑定（< 0.6）替换为 `ask_user` 请求用户确认。

### 4.8 验证与执行守卫 (Schema Guard + Executor)

#### 4.8.1 Schema Guard

**概念**：验证 LLM 生成的工具调用参数是否符合 ToolSchema 定义。

**验证项**：
- 工具名是否存在于 ToolRegistry
- 必填参数是否齐全
- 参数类型是否符合 JSON Schema（通过 jsonschema 验证）
- 枚举值是否合法

#### 4.8.2 Executor

**概念**：根据 ToolType 分发到不同的执行后端。

- **LOCAL_FUNCTION**：直接调用 Python 函数
- **HTTP_API**：构造 HTTP 请求（requests），将参数分类到 path/query/body
- **MCP_REMOTE**：通过 MCP 客户端发送 JSON-RPC 2.0 请求

**执行统计**：记录每次调用的成功/失败状态、延迟，使用指数移动平均（EMA）更新成功率和平均延迟，用于 ToolShortlister 的动态排序。

---

## 5. Layer 2: 对话管理与状态层

### 5.1 功能概念

Layer 2 是系统的**状态管理层**，负责维护对话的长期结构和短期上下文。其设计哲学是：

> **"对话不是线性的消息序列，而是树状的主题演化结构。"**

系统维护两个核心结构：
- **主题树 (Topic Tree)**：对话的长期结构，记录话题的层次关系和切换历史
- **上下文窗口 (Context Window)**：对话的短期工作记忆，决定当前轮次可见的历史范围

### 5.2 主题树 (Topic Tree)

#### 5.2.1 概念定义

Topic Tree 是一个**多叉树**，每个节点代表一个对话主题，边代表主题切换关系。

- **根节点**：对话的总体目标（如"调试程序"、"写论文"）
- **子节点**：子话题（如"调试程序"→"内存扫描"→"结果分析"）
- **边权重**：主题切换的频率和强度

#### 5.2.2 节点权重更新算法

每个节点维护一个**权重**（Topic Weight），表示该主题在当前对话中的重要性。权重通过**指数移动平均（EMA）**更新：

$$W_{t+1}(node) = \alpha \cdot W_t(node) + (1-\alpha) \cdot I_t(node)$$

其中：
- $W_t(node)$：节点在时间 $t$ 的权重
- $I_t(node)$：时间 $t$ 的指示函数（如果当前轮涉及该节点则 1，否则 0）
- $\alpha$：平滑系数，默认 0.8

**新节点创建**：当当前意图与现有所有节点的语义相似度低于阈值 $\theta_{new}$（默认 0.5）时，创建新节点。

**节点激活**：当前轮涉及的节点标记为"激活"，其父节点权重轻微提升（继承性）。

#### 5.2.3 主题切换检测

**主题切换的判定**：

$$TopicSwitch = SemanticDistance(current, previous) > \theta_{switch}$$

其中 $SemanticDistance$ 基于当前意图与上一轮意图的类别差异和实体重叠计算。如果类别不同且实体重叠 < 20%，判定为切换。

**切换处理**：
- 如果是**向上切换**（回到父话题）：激活父节点，子节点权重衰减
- 如果是**横向切换**（同级话题）：创建新同级节点或激活现有同级节点
- 如果是**向下切换**（深入子话题）：创建子节点或激活现有子节点

#### 5.2.4 对话树导航

系统提供基于 Topic Tree 的导航能力：
- **回溯**：用户说"回到刚才的话题" → 激活最近的高权重非当前节点
- **列举**：用户说"列出我们讨论过的主题" → 返回按权重排序的节点列表
- **聚焦**：用户说"专注于 X" → 提升节点 X 的权重，衰减其他节点

### 5.3 上下文窗口 (Context Window)

#### 5.3.1 概念定义

Context Window 是系统的**短期工作记忆**，决定当前轮次 LLM 能看到的对话历史范围。

与简单的"最近 N 轮"不同，DialogMesh 的 Context Window 是**分层、可压缩、自适应**的。

#### 5.3.2 分层存储模型

```
Context Window
├── 热层 (Hot Layer): 最近 1-3 轮，完整保留
├── 温层 (Warm Layer): 最近 4-10 轮，压缩摘要
├── 凉层 (Cool Layer): 最近 11-30 轮，二级摘要 + 关键实体
└── 冷层 (Cold Layer): 超过 30 轮，仅保留主题标签和关键决策
```

#### 5.3.3 压缩算法

**一级摘要（温层压缩）**：

对每轮对话提取：
- 意图类别
- 关键实体（高置信度）
- 执行结果（成功/失败）
- 用户满意度信号（如果有）

存储格式：`[Turn N] {category} | entities: {e1, e2} | result: {status}`

**二级摘要（凉层压缩）**：

对多个相邻轮次（同一主题内）合并为一段自然语言摘要：
- 使用轻量 LLM 或规则模板生成
- 保留：主题、关键决策、未解决问题、用户偏好
- 丢弃：具体参数、中间结果、失败尝试

**冷层存储**：

仅保留：
- 主题标签（Topic Tree 节点 ID）
- 关键决策（如"用户选择了方案 A"）
- 用户偏好更新（如"用户偏好 Python 而非 C++"）

#### 5.3.4 自适应窗口大小

Context Window 的大小不是固定的，而是基于以下因素动态调整：

$$WindowSize = BaseSize \times ComplexityFactor \times UserPreference \times TokenBudget$$

其中：
- $BaseSize$：基础大小（默认 10 轮）
- $ComplexityFactor$：当前任务复杂度（PCR 输出），高复杂度允许更大窗口
- $UserPreference$：用户追踪深度偏好（高追踪深度用户保留更多历史）
- $TokenBudget$：剩余 token 预算（确保不超出 LLM 上下文限制）

#### 5.3.5 引用消解与上下文注入

**显式引用**：用户说"刚才那个地址" → 通过 Reference Resolver 在 Hot Layer 中查找最近一轮的 MEMORY_ADDRESS 实体。

**隐式引用**：用户说"结果呢？" → 通过 Topic Tree 的激活节点和上下文窗口中的最近结果推断。

**上下文注入策略**：在构造 LLM 提示词时，按以下优先级注入历史信息：
1. Hot Layer 的完整轮次（最高优先级）
2. Warm Layer 的摘要（如果相关主题匹配）
3. Cool Layer 的二级摘要（如果涉及跨主题引用）
4. Cold Layer 的主题标签（仅在用户明确提及历史话题时）

### 5.4 对话状态机

**概念**：DialogMesh 的对话状态不是简单的"进行中/结束"，而是基于意图和歧义的**精细化状态机**。

**状态定义**：

| 状态 | 定义 | 触发条件 | 转移条件 |
|------|------|---------|---------|
| **IDLE** | 等待用户输入 | 初始化或上一轮回合结束 | 收到用户输入 → PARSING |
| **PARSING** | 正在解析意图 | 收到输入 | 解析完成 → {ACTIONABLE, CLARIFYING, ERROR} |
| **ACTIONABLE** | 意图可执行 | 解析无歧义，TaskGraph 就绪 | 执行完成 → RESPONDING |
| **CLARIFYING** | 需要澄清 | 检测到歧义 | 用户澄清 → PARSING |
| **EXECUTING** | 正在执行任务 | TaskGraph 开始执行 | 执行完成 → RESPONDING |
| **RESPONDING** | 正在生成响应 | 执行结果就绪 | 响应发送 → IDLE |
| **ERROR** | 发生错误 | 解析失败或执行失败 | 回退处理 → {CLARIFYING, IDLE} |

**状态转换的触发**：由 Layer 3 的 Session Manager 协调，但状态定义在 Layer 2。

---

## 6. Layer 3: 服务接口层

### 6.1 功能概念

Layer 3 是系统的**对外接口层**，负责：
- 协议转换（WebSocket / REST / 前端协议）
- Session 管理（创建、维护、销毁）
- 响应编排（将 TaskGraph 执行结果转换为用户可读的响应）
- 速率限制与安全控制

### 6.2 Session 管理

**Session 生命周期**：

```
Create → Active → {Idle Timeout / Explicit Close} → Archive → Delete
```

**Session 状态**：
- 每个 Session 绑定一个 `ParseContext`（跨轮解析状态）
- 每个 Session 绑定一个 `CognitiveProfileV2`（双轨用户画像）
- 每个 Session 绑定一个 `TopicTree`（对话主题结构）
- 每个 Session 绑定一个 `ContextWindow`（上下文窗口）

**Session 持久化**：
- 活跃 Session 存储在内存（Redis）
- 非活跃 Session 序列化到持久化存储（PostgreSQL）
- 长期 Session 归档到对象存储（S3 兼容）

### 6.3 响应编排器 (Response Composer)

**概念**：将 TaskGraph 的执行结果转换为适合用户认知状态的响应。

**编排策略基于认知画像**：

- **高元认知用户**：简洁响应，只给关键结果，不解释过程
- **低元认知用户**：详细解释，逐步说明，包含"为什么"和"怎么做"
- **高稳定性用户**：保持一致的响应风格和格式
- **高发散性用户**：提供多个选项或替代方案

**响应格式层级**：

| 层级 | 内容 | 适用用户 |
|------|------|---------|
| **BRIEF** | 仅结果（1-2 句话） | 高元认知、专家用户 |
| **BALANCED** | 结果 + 简要解释 | 普通用户 |
| **EXPLANATORY** | 结果 + 详细解释 + 步骤说明 | 低元认知、新手用户 |
| **TUTORIAL** | 结果 + 教学式解释 + 练习建议 | 极低元认知、学习场景 |

**响应格式由 PCR 输出的 `prompt_style` 决定。**

### 6.4 协议层

**WebSocket 协议**：
- 实时双向通信，支持流式响应（SSE 风格）
- 消息类型：user_input, system_response, clarification_request, progress_update, error

**REST API 协议**：
- 同步请求/响应模式
- 端点：/chat, /parse, /execute, /session
- 支持文件上传（用于 API 文档导入）

**前端协议 (Agent Protocol)**：
- 标准化的前端-后端通信协议
- 包含：消息格式、状态码、错误码、事件类型
- 支持心跳检测、重连机制、消息确认

---

## 7. 横切关注点：认知画像系统 v2.0

### 7.1 功能概念

认知画像系统（Cognitive Profile System）是贯穿 DialogMesh 所有层的**用户认知模型**。其设计哲学是：

> **"用户画像不是静态标签，而是动态演化的认知动力学过程。"**

v2.0 版本采用**双轨架构**：
- **Track A: 认知动力学**（Cognitive Dynamics）—— 从对话行为中实时推断的动态特征
- **Track B: 标签化信息**（Tag Layer）—— 通过不同侵入度策略获取的静态/半静态标签

### 7.2 Track A: 认知动力学

#### 7.2.1 核心维度

Track A 包含 5 个可计算的认知维度：

| 维度 | 定义 | 计算方法 | 取值范围 |
|------|------|---------|---------|
| **元认知 (Metacognition)** | 用户对自身认知过程的觉察能力 | 输入精确性 + 自指性语言频率 + 问题结构化程度 | [0, 1] |
| **发散性 (Divergence)** | 用户思维的发散程度 | 主题切换频率 + 词汇多样性 + 同轮多意图率 | [0, 1] |
| **追踪深度 (Tracking Depth)** | 用户维持话题连续性的能力 | 跨轮引用成功率 + 历史话题复用率 | [0, 1] |
| **稳定性 (Stability)** | 用户表达风格的一致性 | 输入长度方差 + 词汇使用一致性 + 标点风格方差 | [0, 1] |
| **信心度 (Confidence)** | 用户对问题的确信程度 | 情态动词频率 + 不确定词频率的反面 | [0, 1] |

#### 7.2.2 推断算法

Track A 的 5 个维度通过**对话行为的统计分析**推断，无需 LLM 调用。

**元认知推断**：

$$Metacognition = 0.4 \cdot Precision + 0.3 \cdot SelfRef + 0.3 \cdot Structure$$

- $Precision$：输入精确性（实体提取的完整度 / 用户意图的明确度）
- $SelfRef$：自指性语言（"我想"、"我需要"、"我的目标是"）的频率
- $Structure$：问题结构化程度（是否包含明确的条件、约束、目标）

**发散性推断**：

$$Divergence = 0.4 \cdot TopicSwitchRate + 0.3 \cdot VocabularyDiversity + 0.3 \cdot MultiIntentRate$$

- $TopicSwitchRate$：每轮话题切换概率
- $VocabularyDiversity$：Type-Token Ratio（词汇类型数 / 总词数）
- $MultiIntentRate$：多意图输入的比例

#### 7.2.3 时间衰减机制

Track A 的认知动力学特征随时间衰减，使用**加权单指数衰减 + 阶梯跃迁**模型。

**衰减公式**：

$$W(t) = W_0 \cdot e^{-t/\tau} \cdot S(t)$$

其中：
- $W_0$：初始权重（事件的重要性）
- $t$：距离事件发生的时间
- $\tau$：时间常数（控制衰减速率，默认 24 小时）
- $S(t)$：阶梯跃迁因子（阶段系数）

**阶段跃迁**：

| 阶段 | 时间范围 | 衰减因子 $S(t)$ | 说明 |
|------|---------|----------------|------|
| **Hot** | $< 1$ 小时 | 1.0 | 热记忆，权重不变 |
| **Warm** | $1-24$ 小时 | 0.8 | 温记忆，轻微衰减 |
| **Cool** | $1-7$ 天 | 0.5 | 凉记忆，显著衰减 |
| **Cold** | $7-30$ 天 | 0.2 | 冷记忆，权重很低 |
| **Frozen** | $> 30$ 天 | 0.05 | 冻结，需要上下文恢复确认 |

**跃迁不是平滑的**，而是阶梯式的：当时间跨过阈值时，权重突然跳跃到下一个阶段。这种设计避免了长期记忆的缓慢衰减导致的模糊性。

**双指数衰减（可选增强）**：

$$W(t) = A \cdot e^{-t/\tau_1} + B \cdot e^{-t/\tau_2}$$

- 快衰减项（$\tau_1 = 1$ 小时）：处理短期遗忘
- 慢衰减项（$\tau_2 = 7$ 天）：处理长期保留

#### 7.2.4 g 因子推断 (g-Factor Inference)

**概念**：g 因子（general cognitive ability）是用户的一般认知能力指标，从对话历史中推断。

**g 因子的五个子指标**：

| 子指标 | 计算方式 | 说明 |
|--------|---------|------|
| **理解速度** | 首次正确理解意图所需的轮数 | 越少越好 |
| **追问深度** | 用户追问的层级和复杂度 | 越深越好 |
| **跨域迁移** | 用户将 A 领域知识应用到 B 领域的频率 | 越高越好 |
| **错误修正率** | 用户从错误反馈中快速修正的比例 | 越高越好 |
| **嵌入式任务** | 微型认知任务（如"请总结上文"）的完成质量 | 越高越好 |

**g 因子综合计算**：

$$g = \sum_{i=1}^{5} w_i \cdot g_i$$

其中 $w_i$ 是权重（默认等权 0.2），$g_i$ 是各子指标的归一化值。

**g 因子的使用约束**：
- 仅用于动态调整响应复杂度（高 g → 复杂回复，低 g → 简化回复）
- 不用于歧视、排名或向用户展示
- 嵌入式微型任务仅在用户同意或自然嵌入时触发

### 7.3 Track B: 标签化信息

#### 7.3.1 概念定义

Track B 是**用户标签的集合**，每个标签包含：
- name（标签名，如 "technical_level"）
- value（标签值，如 "expert"）
- confidence（置信度 [0,1]）
- source（来源：L1/L2/L3/L4）
- verification_count（验证次数）
- is_sensitive（是否敏感）

#### 7.3.2 标签获取策略（四级侵入度）

| 级别 | 名称 | 获取方式 | 侵入度 | 用户反感风险 | 典型标签 |
|------|------|---------|--------|------------|---------|
| **L1** | 被动观测 | 从对话行为中统计推断 | 零 | 无 | 表达风格、活跃时段、偏好格式 |
| **L2** | 间接推断 | LLM 分析对话历史，推断标签 | 低 | 极低 | 技术领域、沟通风格、决策偏好 |
| **L3** | 暗示试探 | 将标签验证自然嵌入对话（如"你更喜欢哪种？"） | 中 | 低 | 技术栈偏好、工作流程偏好 |
| **L4** | 主动询问 | 直接询问用户（仅用于高价值标签） | 高 | 中 | 身份、职业、具体需求 |

**侵入度-收益决策**：

$$AcquireDecision = \frac{Value(tag) \times ConfidenceGain}{Intrusiveness(tag) \times UserAnnoyanceProbability}$$

当 $AcquireDecision > 1$ 时，执行获取；否则跳过。

**用户反感检测**：如果用户在 L3/L4 获取后表现出回避（如"随便"、"都行"），标记该标签为 "user_resistant"，未来不再主动获取同类标签。

#### 7.3.3 双轨融合机制

Track A 和 Track B 不是独立的，而是**相互补充、动态融合**：

- **Track B 提供先验**：已知标签（如 "technical_level=expert"）降低 Track A 的推断成本
- **Track A 修正偏见**：Track B 的标签可能过时，Track A 的实时行为特征可以动态修正
- **融合公式**：

$$Profile_{effective} = \alpha \cdot TrackA_{dynamics} + (1-\alpha) \cdot TrackB_{tags}$$

其中 $\alpha$ 基于标签的时效性和置信度动态调整：新标签 $\alpha$ 低（更信任标签），旧标签 $\alpha$ 高（更信任行为）。

### 7.4 认知画像的全局使用

认知画像 v2.0 作为**控制信号**注入所有层级：

| 层级 | 画像调优点 | 具体映射 |
|------|----------|---------|
| **L0 PCR** | 噪声阈值、期望先验 | 高稳定性用户 → 降低噪声阈值；高信心用户 → 调整先验 |
| **L1 IntentParser** | 解析参数、Fast Path 阈值 | 高元认知 → 提高阈值；高发散 → 启用多意图拆分 |
| **L1.5 Planning** | 模式选择、计划复杂度 | 高元认知 → DYNAMIC；低 g → 简化计划；高发散 → TreeOfThought |
| **L2 Context** | 窗口大小、压缩策略 | 高追踪深度 → 大窗口；高发散 → 保留更多话题分支 |
| **L3 Response** | 响应风格、详细度 | 高元认知 → BRIEF；低元认知 → TUTORIAL |

---

## 8. 横切关注点：记忆系统

### 8.1 功能概念

记忆系统是 DialogMesh 的**长期存储层**，管理对话历史、用户画像、工具执行记录的持久化与检索。其设计哲学是：

> **"记忆不是存储所有对话，而是存储对当前决策有价值的认知痕迹。"**

### 8.2 记忆组块 (Memory Chunks)

#### 8.2.1 概念定义

记忆组块是记忆的基本单位，每个组块包含：
- content（内容：文本摘要、实体列表、决策结果）
- importance（重要性 [0,1]，由事件显著性和用户关注度决定）
- timestamp（创建时间）
- stage（当前阶段：hot/warm/cool/cold/frozen）
- tags（分类标签，用于检索）
- source_layer（来源层级：L0/L1/L2/L3）

#### 8.2.2 重要性计算

记忆组块的重要性由以下因素决定：

$$Importance = Base \times UserAttention \times SystemSignificance$$

- $Base$：基础重要性（事件类型决定：错误=1.0, 澄清=0.8, 成功执行=0.6, 普通对话=0.3）
- $UserAttention$：用户关注度（用户是否追问、是否重复提及）
- $SystemSignificance$：系统显著性（是否涉及错误、歧义、新工具发现）

### 8.3 加权指数衰减

#### 8.3.1 核心算法

每个记忆组块的有效权重随时间衰减：

$$W_{effective}(t) = Importance \cdot e^{-t/\tau} \cdot StageFactor$$

其中：
- $t$：距离创建的时间
- $\tau$：时间常数（可配置，默认 24 小时）
- $StageFactor$：阶段跃迁因子（见 7.2.3 阶段表）

#### 8.3.2 阶梯跃迁机制

当记忆组块的年龄跨过阈值时，其阶段发生跃迁：

- Hot → Warm：1 小时后，衰减因子从 1.0 → 0.8
- Warm → Cool：24 小时后，衰减因子从 0.8 → 0.5
- Cool → Cold：7 天后，衰减因子从 0.5 → 0.2
- Cold → Frozen：30 天后，衰减因子从 0.2 → 0.05

**跃迁触发**：定时任务（如每 5 分钟扫描）或惰性检查（访问时检查）。

**Frozen 记忆的恢复**：当用户主动提及 Frozen 记忆的内容时，触发"上下文恢复确认"——询问用户"是否继续讨论 X？"，确认后该记忆的权重临时提升回 Warm 阶段。

### 8.4 二级摘要系统

#### 8.4.1 概念

二级摘要系统解决"如何在有限 token 内保留长对话的核心信息"问题。

**两级摘要**：
- **一级摘要 (Per-Turn Summary)**：对单轮对话的压缩，保留意图、实体、结果
- **二级摘要 (Multi-Turn Summary)**：对多个相邻轮次（同一主题内）的合并摘要，保留主题、关键决策、未解决问题

#### 8.4.2 摘要生成策略

**一级摘要生成**（规则驱动）：
- 提取意图类别和置信度
- 提取高置信度实体（≥ 0.8）
- 记录执行结果（成功/失败/部分成功）
- 记录用户满意度信号（如果有）

**二级摘要生成**（LLM 驱动或模板驱动）：
- 当同一主题内积累超过 $N$ 轮（默认 5 轮）时触发
- 输入：该主题内的所有一级摘要
- 输出：一段自然语言摘要（50-100 字），包含：主题、关键决策、未解决问题、用户偏好变化
- 触发后，该主题内的一级摘要可标记为"已压缩"（可选删除）

#### 8.4.3 摘要的存储与检索

- 一级摘要存储在内存（Redis），快速检索
- 二级摘要存储在持久化数据库（PostgreSQL），支持语义检索
- Frozen 记忆仅保留二级摘要的索引（主题标签 + 关键决策）

**检索策略**：
- 当用户提及历史话题时，先检索二级摘要索引
- 如果需要详细信息，再检索一级摘要
- 如果一级摘要已删除，则基于二级摘要重构上下文

### 8.5 记忆与认知画像的协同

- 记忆组块的 tags 用于填充 Track B 的标签（L1/L2 获取）
- 记忆的重要性和阶段影响 Track A 的稳定性推断（频繁回忆 → 稳定性高）
- 记忆的衰减曲线与认知画像的时间衰减共享同一套数学模型

---

## 9. 横切关注点：可观测性

### 9.1 功能概念

可观测性系统确保 DialogMesh 的**内部状态对外可见、问题可诊断、性能可度量**。采用**四层可观测性模型**。

### 9.2 四层可观测性

#### 9.2.1 诊断层 (Diagnostics)

**目标**：快速定位"系统哪里出了问题"。

**组件**：
- **健康检查端点**：/health, /ready, /alive
- **依赖状态检查**：数据库、缓存、LLM 服务、外部 API 的连通性
- **资源监控**：CPU、内存、磁盘、网络 I/O
- **关键指标阈值告警**：响应延迟 > 500ms、错误率 > 1%、内存使用 > 80%

#### 9.2.2 归因层 (Attribution)

**目标**：确定"问题是谁的责任"。

**组件**：
- **请求追踪 (Request Tracing)**：每个请求的唯一 ID，贯穿所有层级
- **Span 标记**：每个处理步骤（解析、规划、执行、响应）的时间戳和状态
- **错误归因**：错误发生时记录当前层、当前组件、输入快照
- **性能归因**：延迟分解（各层贡献的延迟占比）

**延迟分解公式**：

$$Latency_{total} = Latency_{PCR} + Latency_{IntentParser} + Latency_{Planning} + Latency_{Execution} + Latency_{Response}$$

#### 9.2.3 遥测层 (Telemetry)

**目标**：收集"系统的运行数据"。

**指标类型**：
- **Counter**：请求数、错误数、工具调用次数
- **Gauge**：当前活跃 Session 数、队列深度、内存使用
- **Histogram**：响应延迟分布、解析时间分布、LLM 调用 token 数分布
- **Summary**：成功率、用户满意度、任务完成率

**关键指标**：

| 指标 | 定义 | 目标值 |
|------|------|--------|
| **解析成功率** | 解析无歧义且可执行的请求比例 | > 95% |
| **规划成功率** | TaskGraph 生成成功且通过验证的比例 | > 90% |
| **执行成功率** | 工具调用成功完成的比例 | > 95% |
| **用户满意度** | 用户未要求澄清或重试的比例 | > 85% |
| **端到端延迟** | 从输入到响应的完整延迟 | < 500ms (p95) |
| **LLM 调用成本** | 每轮对话的平均 LLM token 消耗 | < 2000 tokens |

#### 9.2.4 追踪层 (Tracing)

**目标**：重现"用户做了什么、系统怎么响应的"。

**组件**：
- **对话日志**：每轮对话的完整输入、输出、中间状态
- **决策轨迹**：每个层级的决策过程（如"为什么选择了 DYNAMIC 模式？"）
- **状态快照**：关键时间点的完整系统状态（用于事后调试）
- **可视化追踪**：将对话过程可视化为流程图（Topic Tree + TaskGraph 叠加）

### 9.3 可观测性数据的使用闭环

```
收集 (Telemetry) → 分析 (Attribution) → 诊断 (Diagnostics) → 优化 → 收集
```

- **A/B 测试**：基于遥测数据比较不同策略的效果（如 Skill 增强 vs 纯动态规划）
- **自动调优**：基于性能归因自动调整系统参数（如 ToolShortlister 的容量限制）
- **告警与回退**：当关键指标超过阈值时触发告警，并自动降级到保守策略

---

## 10. 完整数据流与生命周期

### 10.1 单次对话轮的数据流

```
[用户输入] ──────────────────────────────────────────────────────
  │
  ▼
[Layer 3: Session Manager] ──→ 检查 Session 是否存在，恢复上下文
  │
  ▼
[Layer 0: PCR]
  ├── Noise Detector → 计算噪声水平 N
  ├── Expectation Inferencer → 推断期望类型 E
  ├── Cognitive Quick Assessment → 评估四维度快照
  └── 输出: PCROutput (期望 + 噪声 + 复杂度 + 认知快照 + 执行模式)
  │
  ▼
[Layer 1: Intent Parser]
  ├── Preprocessor → 规范化 + 词汇调优（基于稳定性）
  ├── Reference Resolver → 代词消解（读取实体缓存）
  ├── Entity Extractor → 规则提取实体（期望感知）
  ├── Intent Classifier → 多规则匹配 + 冲突检测
  ├── Multi-Intent Splitter → 连接词检测 + 实体继承
  ├── Ambiguity Detector → 6 类歧义检测（噪声感知）
  ├── Ambiguity Resolver → 自动消解或标记澄清
  ├── Context Merger → 继承历史实体 + 更新实体缓存
  └── TaskGraph Builder → 期望感知的任务图模板
  │
  ▼
[Layer 1.5: Mixed Planning Engine]
  ├── Skill Detection → 匹配 Planning Skills（意图 + 标签）
  ├── Mode Selection → 决策树：DYNAMIC / SKILL_ENHANCED / MIXED
  ├── Planning Execution:
  │   ├── DYNAMIC: 通用原语 + LLM 自主规划
  │   ├── SKILL_ENHANCED: Skill 骨架 + LLM 填充
  │   └── MIXED: Skill 严格骨架 + LLM 仅填充占位符
  ├── Tool Binding → 占位符 → 实际工具名
  └── Schema Guard → 验证参数合法性
  │
  ▼
[Layer 2: 状态管理]
  ├── Topic Tree → 更新/创建节点，调整权重
  ├── Context Window → 更新分层存储，压缩过期内容
  └── 对话状态机 → 状态转换
  │
  ▼
[Layer 3: Response Composer]
  ├── 执行结果 → 认知画像感知的响应编排
  ├── 响应格式选择 → BRIEF / BALANCED / EXPLANATORY / TUTORIAL
  └── 协议转换 → WebSocket/REST 响应
  │
  ▼
[用户接收响应] ─────────────────────────────────────────────────
```

### 10.2 长期生命周期

```
Session 创建
  │
  ├── PCR 初始化：设置用户特定先验（基于历史画像）
  ├── IntentParser 初始化：加载用户特定的规则覆盖（如果有）
  ├── Topic Tree 初始化：创建根节点（基于对话初始目标）
  ├── Context Window 初始化：空窗口
  └── Cognitive Profile 加载：从历史归档恢复 Track B 标签 + Track A 基线
  │
  ▼
对话轮次循环（每轮执行上述单次数据流）
  │
  ├── 每轮更新：
  │   ├── 认知画像：更新 Track A 动态特征
  │   ├── 记忆系统：存储新记忆组块，更新衰减
  │   ├── Topic Tree：调整节点权重
  │   └── Context Window：更新分层存储
  │
  ▼
Session 结束（超时关闭 / 用户显式关闭）
  │
  ├── 画像归档：Track A 特征序列化 + Track B 标签持久化
  ├── 记忆归档：Hot/Warm 记忆转存，Cool/Cold 记忆保留索引
  ├── Topic Tree 归档：完整树结构保存
  └── 遥测归档：性能指标汇总，用于 A/B 测试和自动调优
  │
  ▼
Session 删除（长期不活跃）
  │
  └── 仅保留：
      ├── 用户画像（Track B 标签 + Track A 长期趋势）
      ├── 二级摘要（跨对话的主题摘要）
      └── 聚合遥测（统计数据，不含个体追踪）
```

---

## 11. 设计决策记录

### ADR-001: 分层架构而非端到端黑盒

- **决策**：采用严格的分层架构（L0-L3），每层有明确的职责边界和数据契约。
- **理由**：可调试性（每层独立测试）、可优化性（每层独立升级）、可解释性（决策过程透明）。
- **后果**：层间通信开销增加；需要维护数据契约的兼容性。

### ADR-002: 规则优先，LLM 兜底

- **决策**：在 Intent Parser 中，95% 场景使用规则引擎，仅在规则失效时调用 LLM。
- **理由**：规则引擎可预测、低成本、可调试；LLM 用于处理规则无法覆盖的模糊场景。
- **后果**：需要维护规则库；规则冲突时需要人工干预。

### ADR-003: Planning 与 Tools 正交解耦

- **决策**：任务规划方法（Planning）与工具集（Tools）设计为独立正交的抽象层。
- **理由**：支持零工具场景规划；同一 Skill 可绑定到不同工具集；降低工具变更对规划的影响。
- **后果**：增加 Binding 层的复杂度；开发 Skill 时需要理解两层抽象。

### ADR-004: 双轨认知画像

- **决策**：用户画像分为 Track A（动态认知特征）和 Track B（静态标签信息）。
- **理由**：Track A 提供实时行为修正，Track B 提供先验降低推断成本；两者互补避免单一模型的偏见。
- **后果**：画像系统复杂度翻倍；需要设计融合机制。

### ADR-005: 时间衰减的阶梯跃迁模型

- **决策**：记忆和画像特征使用阶梯跃迁（非平滑衰减）的阶段模型。
- **理由**：避免长期记忆的缓慢衰减导致的模糊性；明确区分"热"和"冷"记忆的可用性。
- **后果**：跃迁阈值的选择影响系统行为；需要 Frozen 记忆的恢复机制。

### ADR-006: 通用原语人工设计，不自动爬取

- **决策**：17 个通用规划原语从认知科学和文献中人工设计，不从现有系统自动爬取。
- **理由**：通用原语需要跨领域抽象能力，自动爬取易过拟合到特定领域；人工设计可确保质量。
- **后果**：初始工作量较大；社区贡献新原语需要审核。

### ADR-007: 三种规划模式自动选择

- **决策**：系统根据意图匹配度和认知画像自动选择规划模式，不暴露手动选择给用户。
- **理由**：降低用户认知负担；系统可基于历史数据优化选择策略。
- **后果**：用户可能不理解为什么选了某种模式；需要完善的可解释性输出。

### ADR-008: 上下文窗口的分层压缩

- **决策**：上下文窗口分为 Hot/Warm/Cool/Cold 四层，每层采用不同压缩策略。
- **理由**：在有限 token 预算内最大化信息密度；热层保留完整细节，冷层仅保留索引。
- **后果**：压缩策略需要持续调优；压缩可能导致信息丢失。

### ADR-009: 可观测性的四层模型

- **决策**：可观测性分为 Diagnostics / Attribution / Telemetry / Tracing 四层。
- **理由**：不同场景需要不同粒度的可观测性（快速诊断 vs 深度追踪）；分层避免信息过载。
- **后果**：需要维护四套数据采集系统；存储成本增加。

---

## 12. 附录

### 12.1 术语表

| 术语 | 定义 |
|------|------|
| **PCR** | Pre-Cognitive Router，预认知路由器，系统的最前端过滤器 |
| **Intent** | 意图，用户输入的结构化表示（类别 + 实体 + 置信度） |
| **TaskGraph** | 任务图，有向无环图（DAG），表示任务的依赖关系 |
| **Planning Primitive** | 通用规划原语，跨领域通用的认知模式（如 ReAct Loop、Divide-Conquer） |
| **Planning Skill** | 领域规划模板，基于通用原语组合，填充领域知识 |
| **Mixed Planning Engine** | 混合编排引擎，自动选择 DYNAMIC/SKILL_ENHANCED/MIXED 三种模式 |
| **ToolRegistry** | 动态工具注册中心，运行时管理工具 Schema 和执行句柄 |
| **ToolShortlister** | 工具筛选引擎，从工具池中选择相关子集注入 LLM 上下文 |
| **ToolBindingEngine** | 工具绑定引擎，将规划占位符适配到实际工具 |
| **SchemaGuard** | Schema 验证层，确保工具调用参数符合定义 |
| **TopicTree** | 主题树，对话的长期结构，记录话题的层次关系 |
| **ContextWindow** | 上下文窗口，对话的短期工作记忆，分层存储 |
| **CognitiveProfile** | 认知画像，用户的认知状态模型（双轨：Track A + Track B） |
| **Track A** | 认知动力学轨道，动态可计算的行为特征（元认知、发散性等） |
| **Track B** | 标签化信息轨道，静态/半静态的用户标签（技术领域、偏好等） |
| **MemoryChunk** | 记忆组块，记忆的基本单位，包含内容、重要性、时间戳 |
| **g-Factor** | 一般认知能力因子，从对话行为中推断的综合认知指标 |
| **L1/L2/L3/L4** | 标签获取的四级侵入度策略（被动/间接/暗示/主动） |
| **Hot/Warm/Cool/Cold/Frozen** | 记忆的五个阶段，对应不同衰减权重 |
| **EMA** | 指数移动平均，用于更新权重和统计指标 |
| **FastPath** | 快速路径，当输入高度明确时跳过中间解析阶段 |
| **ParseContext** | 解析上下文，跨轮状态容器，存储历史意图和实体缓存 |
| **EntityCache** | 实体缓存，跨轮存储的高置信度实体，用于参照消解 |
| **PCROutput** | PCR 的输出，包含期望、噪声、复杂度、认知快照等控制信号 |
| **Ambiguity** | 歧义，解析结果中的不确定性，需要消解或澄清 |
| **Binding** | 绑定，将规划占位符替换为实际工具名的过程 |
| **SkillLevel** | Skill 详细度级别（SKELETON / STANDARD / DETAILED） |
| **Diagnostics** | 诊断层，快速定位系统问题 |
| **Attribution** | 归因层，确定问题责任归属 |
| **Telemetry** | 遥测层，收集系统运行数据 |
| **Tracing** | 追踪层，重现用户操作和系统响应过程 |

### 12.2 核心数学公式汇总

| 公式 | 说明 | 所在章节 |
|------|------|---------|
| $N = \alpha N_{semantic} + \beta N_{structural} + \gamma N_{referential}$ | 噪声度量 | 2.2.1 |
| $P(E \mid X) = \frac{P(X \mid E) P(E)}{P(X)}$ | 期望推断（贝叶斯） | 2.2.2 |
| $P_t(E) = \lambda P_{global}(E) + (1-\lambda) P_{user}(E)$ | 先验概率动态调整 | 2.2.2 |
| $score(rule) = 0.6 \cdot pattern + 0.3 \cdot entity + 0.1 \cdot context$ | 规则匹配置信度 | 3.3.4 |
| $W(t) = W_0 \cdot e^{-t/\tau} \cdot S(t)$ | 加权单指数衰减 | 7.2.3 |
| $W(t) = A e^{-t/\tau_1} + B e^{-t/\tau_2}$ | 双指数衰减 | 7.2.3 |
| $g = \sum w_i \cdot g_i$ | g 因子综合计算 | 7.2.4 |
| $AcquireDecision = \frac{Value \times ConfidenceGain}{Intrusiveness \times UserAnnoyance}$ | 标签获取决策 | 7.3.2 |
| $Profile_{eff} = \alpha \cdot TrackA + (1-\alpha) \cdot TrackB$ | 双轨融合 | 7.3.3 |
| $Importance = Base \times UserAttention \times SystemSignificance$ | 记忆重要性 | 8.2.2 |
| $W_{eff}(t) = Importance \cdot e^{-t/\tau} \cdot StageFactor$ | 记忆有效权重 | 8.3.1 |
| $FastPath = (\forall e: conf(e) \geq \theta_e) \land (conf(intent) \geq \theta_i)$ | 快速路径触发 | 3.4 |
| $WindowSize = Base \times Complexity \times Preference \times TokenBudget$ | 自适应窗口大小 | 5.3.4 |

### 12.3 参考文献

1. Yao, S., et al. (2022). "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023.
2. Wei, J., et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." NeurIPS 2022.
3. Yao, S., et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with Large Language Models." arXiv:2305.10601.
4. Shinn, N., et al. (2023). "Reflexion: Self-Reflective Agents with Verbal Reinforcement Learning." NeurIPS 2023.
5. Yang, Z., et al. (2024). "Understanding the Planning of LLM Agents: A Survey." arXiv:2406.06530.
6. Newell, A., & Simon, H. A. (1972). "Human Problem Solving." Prentice-Hall.
7. Wang, L., et al. (2023). "Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning." arXiv:2305.04091.
8. Qin, Y., et al. (2025). "ToolACE: Win the Tool Using Competition." ICLR 2025.
9. Schmidgall, S., et al. (2025). "ToolRegistry: A Protocol-Agnostic Tool Management Library." arXiv:2507.10593.
10. Anthropic (2024). "Model Context Protocol (MCP) Specification."
11. LangChain (2024). "LangGraph: Building Stateful Agent Applications." LangChain Documentation.
12. CrewAI (2024). "Multi-Agent AI Framework." CrewAI Documentation.

### 12.4 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-26 | 初始架构设计（Layer 0-3 + 认知画像 v1.0） |
| v2.0 | 2026-07-19 | 重构：认知画像 v2.0（双轨）、Planning Skill Layer（正交解耦）、完整概念整合 |

---

*本设计文档由 DialogMesh 架构团队基于文献调研、认知科学理论和系统分析生成。所有概念遵循"可计算行为特征"公理化体系——任何不可量化、不可推断、不可衰减的概念都不进入系统核心。*
