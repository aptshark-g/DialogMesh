# DiscourseBlock Tree（摘要树）设计方案 v1.0

> **定位**：将当前以"轮次(turn)"为原子单元的 TopicTree，升级为以"话语块(DiscourseBlock)"为原子单元的**摘要树**。通过**编译器三阶段管道**（头文件引入→语法分解→宏观/微观量化）实现轮内多话题切分，通过**动态粒度调节**维持树的健康密度，通过**渐进式摘要**实现长对话的可持续存储。
>
> **状态**：设计文档，待实现。上游依赖：`TopicTreeManagerV2`（已具备 embedding、Ψ 分类器、ForkPointLocator、MergeEngine）。

## 目录

- [1. 背景：轮次树的结构性缺陷](#1-背景轮次树的结构性缺陷)
- [2. 核心概念：DiscourseBlock](#2-核心概念discourseblock)
- [3. 编译器三阶段管道](#3-编译器三阶段管道)
- [4. 宏观-微观双层量化框架](#4-宏观-微观双层量化框架)
- [5. 动态粒度调节机制](#5-动态粒度调节机制)
- [6. 渐进式摘要树](#6-渐进式摘要树)
- [7. 数据模型](#7-数据模型)
- [8. 核心算法](#8-核心算法)
- [9. 与现有系统集成](#9-与现有系统集成)
- [10. 评估指标](#10-评估指标)
- [11. 实现计划与风险](#11-实现计划与风险)

---

## 1. 背景：轮次树的结构性缺陷

### 当前 TopicTree 的原子单元

```python
TopicNode = 整轮对话(user_query + assistant_response)
```

**问题场景**：用户一轮输入包含多个独立话题时，整轮被塞进单一节点，embedding 语义被稀释，路由精度下降。

| 用户输入示例 | 当前行为 | 缺陷 |
|---|---|---|
| "帮我写个Python函数。对了，昨天那个神经网络的方案怎么样了？顺便推荐个轻量embedding模型。" | 一个节点，embedding 混合三话题语义 | 后续路由偏向其中某一话题，丢失其他分支 |
| "这个喝了很呛。我不认为那个API安全。" | 一个节点，实体为空 | 隐含实体（汽水、API）未解析，PCR 误判 |
| "回到刚才那个" | 线性搜索 history | 无结构回溯，只能匹配关键词 |

### 摘要树的核心升级

| 维度 | 轮次树 (当前) | 摘要树 (目标) |
|---|---|---|
| **原子单元** | 一轮对话 | 话语块（子句/子话题） |
| **切分能力** | 无 | 轮内多话题切分（EDU级） |
| **隐含信息** | 不处理 | 头文件引入（指代补全） |
| **量化维度** | 单一粘合度 | 宏观语义 + 微观联系 |
| **粒度控制** | 固定 | 动态调节（过密再切/过疏合并） |
| **摘要策略** | 静态截断 | 渐进式四级摘要 |
| **树深度** | 用户轮次驱动 | 语义密度驱动 |

---

## 2. 核心概念：DiscourseBlock

DiscourseBlock（话语块）是摘要树的原子节点。它不是自然语言的一轮，而是**语义完整、可独立路由**的最小话题单元。

### 2.1 块的边界判定

一个 DiscourseBlock 必须满足：**内部 cohesion ≥ 外部 cohesion**。即块内语义紧密度显著高于块与相邻单元的紧密度。

### 2.2 块的结构

```
DiscourseBlock
├── atomic_units: List[EDU]          # 基本话语单元（子句/片段）
├── macro_vector: Embedding          # 宏观语义向量（整体意思）
├── micro_graph: RelationGraph       # 微观关系图（实体-谓语-实体）
├── cohesion_internal: float         # 内部粘合度 [0,1]
├── cohesion_boundary: float         # 与左邻块的边界粘合度 [0,1]
├── summary: ProgressiveSummary      # 渐进式摘要
├── primary_intent: IntentCategory   # 主导意图
├── secondary_intents: List[Intent]  # 次要意图（可能产生挂接分支）
├── entities: List[Entity]           # 提取的实体（已补全）
├── capacity: int                    # 当前容量上限（动态调节）
├── depth: int                       # 在树中的深度
└── parent_block: Optional[ref]      # 父块（逻辑归属）
```

---

## 3. 编译器三阶段管道

类比 C 语言编译器：源文件 → 预处理（头文件引入）→ 编译（语法分解）→ 链接（量化粘合）。

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: 预处理器 (Preprocessor / HeaderInjector)           │
│  ─────────────────────────────────────────────────────────  │
│  输入：原始自然语言                                          │
│  "这个喝了很呛，我不认为那个API安全"                          │
│  ↓                                                           │
│  隐含信息解析：                                               │
│    • "这个" → 上下文最近实体 "汽水"（头文件引入）              │
│    • "那个API" → 会话历史中 "PaymentGateway API"（跨轮解析）   │
│  ↓                                                           │
│  输出：实体补全后的文本                                        │
│  "汽水喝了很呛，我不认为PaymentGateway API安全"                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: 语法分解器 (SyntacticDecomposer)                   │
│  ─────────────────────────────────────────────────────────  │
│  输入：补全后的文本                                            │
│  ↓                                                           │
│  按边界标记切分：                                              │
│    • 句法边界：。！？；                                       │
│    • 话题切换标记："对了"、"另外"、"顺便"、"换个话题"            │
│    • 逻辑转折标记："但是"、"然而"、"不过"                       │
│  ↓                                                           │
│  对每个子句提取：                                              │
│    ┌─────────────┐    ┌─────────────┐                       │
│    │ 子句1        │    │ 子句2        │                       │
│    │ 主语: 汽水   │    │ 主语: (我)   │                       │
│    │ 谓语: 喝     │    │ 谓语: 认为   │                       │
│    │ 宾语: 很呛   │    │ 宾语: API不安全│                       │
│    │ 属性: NEG    │    │ 属性: NOT(unsafe)                  │
│    └─────────────┘    └─────────────┘                       │
│  ↓                                                           │
│  输出：List[ParsedClause]（每个含主谓宾+属性）                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: 量化器 (Quantizer / CohesionScorer)              │
│  ─────────────────────────────────────────────────────────  │
│  输入：相邻两个 ParsedClause                                   │
│  ↓                                                           │
│  宏观量化：整体语义相似度（embedding cosine）                   │
│  微观量化：实体-谓语-实体联系（因果/从属/并列/对比）             │
│  ↓                                                           │
│  输出：CohesionScore                                         │
│    • total_score: 0.82 (continue) / 0.15 (fork)             │
│    • macro_score: 0.75                                       │
│    • micro_score: 0.88                                       │
│    • decision: continue | fork | gray_zone                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Stage 1: 头文件引入（HeaderInjector）

**核心问题**：自然语言大量省略主语/宾语，依赖上下文推断。如"这个喝了很呛"——"这个"指代什么？

**类比 C 语言**：`#include <context.h>` —— 将当前会话的实体缓存、历史话题的摘要、领域知识库作为"头文件"引入，补全隐含信息。

**补全策略（按优先级）**：

| 优先级 | 策略 | 示例 | 置信度 |
|---|---|---|---|
| 1 | 同轮显性指代 | "汽水很好喝，这个很呛" → "这个"=汽水 | 0.95 |
| 2 | 上下文最近实体 | 上一轮主语/宾语继承 | 0.85 |
| 3 | 因果知识库推断 | "很呛" → 候选["汽水","辣椒","烟雾"] | 0.70 |
| 4 | 会话历史实体池 | 过去 10 轮出现过的实体 | 0.60 |
| 5 | 领域默认补全 | 谓语"scan"→ 默认宾语"内存" | 0.50 |

**实现约束**：
- 不调用 LLM（延迟 < 1ms）
- 基于 jieba 分词 + 规则词典 + 实体缓存
- 歧义时保留多个候选，标记置信度，传入下游决策

### 3.2 Stage 2: 语法分解（SyntacticDecomposer）

**核心问题**：不是做完整 NLP 依存句法分析，而是**快速提取主谓宾骨架**，保留修饰语作为属性标签。

**设计原则**：
- 主语/宾语是**认知核心**——决定话题归属
- 谓语是**意图核心**——决定路由方向
- 修饰语（否定、形容词、副词）是**属性标签**——不能丢弃，否则"不安全的API"变成"API"

**Fast Path 规则（无需 LLM）**：

```python
def fast_extract(clause: str) -> ParsedClause:
    # 1. 否定/不确定/祈使检测（词典匹配）
    negation = any(m in clause for m in NEGATION_MARKERS)   # 不/没/非/not
    uncertainty = any(m in clause for m in UNCERTAINTY_MARKERS)  # 可能/也许
    imperative = any(m in clause for m in IMPERATIVE_MARKERS)    # 请/帮我

    # 2. 主语提取：代词优先 → 实体优先 → 名词短语
    subject = extract_pronoun(clause) or extract_first_entity(clause)

    # 3. 谓语提取：动词词典匹配（跑/写/分析/scan/推荐）
    predicate = match_verb_dictionary(clause)

    # 4. 宾语提取：谓语后的第一个实体/名词短语
    object = extract_after_predicate(clause, predicate)

    # 5. 属性提取：主语/宾语前的形容词/修饰语
    subject_attrs = extract_modifiers_before(clause, subject)
    object_attrs = extract_modifiers_before(clause, object)

    return ParsedClause(...)
```

**Hybrid Path 触发条件**：
- 单句 > 30 字且含 2+ 个连词（"和/或/但/如果"）
- 多主语信号（多个代词或多个独立实体）
- 存在嵌套从句（正则无法可靠解析）

→ 标记 `parse_failed=True`，跳过 Fast Path，直接整句送入 LLM 做轻量解析（或在 TopicDecisionClassifier 中处理）。

### 3.3 Stage 3: 量化器（宏观 + 微观）

这是**核心创新**。传统 cohesion 是单一标量，我们拆分为**正交的宏观/微观二维**。

---

## 4. 宏观-微观双层量化框架

### 4.1 宏观量化（Macro Cohesion）

**定义**：两个话语块在**整体语义空间**中的距离。不关心内部结构，只关心"说的是不是同一件事"。

**计算维度**：

| 维度 | 指标 | 权重 | 说明 |
|---|---|---|---|
| M1 | 语义向量相似度 | 0.35 | Embedding cosine（sentence-transformers 或伪向量） |
| M2 | 意图类别一致性 | 0.25 | 同意图 → 高 cohesion，跨意图 → 低 cohesion |
| M3 | 领域/场景重叠 | 0.20 | 技术/生活/学术等场景标签是否一致 |
| M4 | 情绪/语气连续性 | 0.20 | 疑问→疑问，陈述→陈述；突变→低 cohesion |

```python
macro_score = 0.35*cos_sim(emb_A, emb_B) + \
              0.25*(intent_A == intent_B) + \
              0.20*domain_overlap(A, B) + \
              0.20*mood_continuity(A, B)
```

**特点**：
- 对**同义词替换**敏感（"Python" vs "py" → embedding 捕获）
- 对**结构变化**不敏感（"A写B" vs "B被A写" → 相似度高）
- 对**虚假关联**不敏感（"苹果好吃" vs "苹果手机" → 依赖微观区分）

### 4.2 微观量化（Micro Cohesion）

**定义**：两个话语块在**实体关系层面**的联系强度。关注"实体如何相互作用"。

**计算维度**：

| 维度 | 指标 | 权重 | 说明 |
|---|---|---|---|
| μ1 | 实体重叠度 | 0.30 | Jaccard(entities_A, entities_B)，主语/宾语匹配 |
| μ2 | 因果链强度 | 0.25 | 含"所以/因此/导致/因为"→强因果；含"然后/接着"→弱因果 |
| μ3 | 指代继承度 | 0.20 | 代词"它/这/那"是否明确指向前块实体 |
| μ4 | 谓语-宾语关联 | 0.15 | 同谓语不同宾语 → 弱（"讨论A" vs "讨论B"）；同宾语 → 强 |
| μ5 | 修饰语一致性 | 0.10 | 属性标签是否冲突（"unsafe API" vs "safe API" → 对比关系） |

```python
micro_score = 0.30*entity_jaccard(A, B) + \
              0.25*causal_chain_strength(A, B) + \
              0.20*anaphora_inheritance(A, B) + \
              0.15*verb_object_relation(A, B) + \
              0.10*modifier_consistency(A, B)
```

**微观独有的能力**：
- 区分**同形异义**（"苹果"水果 vs 公司 → 通过谓语-宾语关联区分）
- 检测**隐性因果**（"我按了按钮。屏幕亮了。" → 无显性因果词，但时间+动作序列暗示因果）
- 识别**对比关系**（"A是安全的。B不安全。" → 微观 cohesion 低，但话题仍相关）

### 4.3 宏观-微观的协同决策

单一维度不足以决策。四种组合产生不同语义：

| 宏观 | 微观 | 语义解释 | 决策倾向 |
|---|---|---|---|
| 高 | 高 | 同话题，实体继承 | **continue**（强延续） |
| 高 | 低 | 同领域但换主体/视角 | **attach**（同分支下挂新子块） |
| 低 | 高 | 跨领域但实体关联（如"代码写了。部署到服务器。"） | **continue** 或 **fork+link**（工作流延续） |
| 低 | 低 | 完全无关 | **fork**（新分支） |

**综合决策函数**：

```python
def route_decision(macro: float, micro: float, threshold: dict) -> str:
    # 极端区：无需 LLM
    if macro > 0.8 and micro > 0.7:
        return "continue"          # 强延续
    if macro < 0.3 and micro < 0.3:
        return "fork"              # 强切换

    # 灰区：需要 LLM 或 Ψ 分类器辅助
    # 定义四个象限
    if macro > 0.5 and micro > 0.5:
        return "continue"          # 高-高
    elif macro > 0.5 and micro <= 0.5:
        return "attach"            # 高-低：同域换主体
    elif macro <= 0.5 and micro > 0.5:
        return "continue_or_link"  # 低-高：跨域关联，需人工/LLM 确认
    else:
        return "fork"              # 低-低
```

---

## 5. 动态粒度调节机制

### 5.1 问题定义

树的粒度不是固定的。存在两种病态：

- **过密（Over-segmentation）**：一个话题被切成太多碎块，深度过大，检索效率低
- **过疏（Under-segmentation）**：多个话题混在一个块里，语义不纯，路由精度低

### 5.2 健康指标：Block Density Index (BDI)

```python
BDI = avg_blocks_per_topic / optimal_blocks_per_topic

optimal_blocks_per_topic = 3~5  # 经验值：一个话题有 3-5 个话语块最健康
```

| BDI 范围 | 状态 | 动作 |
|---|---|---|
| < 0.5 | 过疏（话题混在一块） | **分裂(Split)**：再切割 |
| 0.5 ~ 2.0 | 健康 | 维持 |
| > 2.0 | 过密（碎块过多） | **合并(Merge)** 或 **提升容量(Promote)** |

### 5.3 一家独大 → 再切割（Split）

**条件**：
- 某话语块内部 cohesion > 0.9（内部极度紧密）
- 但该块包含 > 5 个 EDU（基本话语单元）
- 块内存在**子主题漂移**（通过 EDU 间 pairwise cohesion 检测断崖）

**操作**：
```python
# 在块内部运行 TextTiling 算法
sub_boundaries = detect_cohesion_cliffs(edu_list, window_size=2)
# 将原块分裂为 2-3 个子块，挂到父块下作为子节点
parent_block.child_blocks = split_into_subblocks(edu_list, sub_boundaries)
```

### 5.4 主题过多 → 提升容量（Promote / Merge）

**条件**：
- 同一父节点下的子块数量 > 8
- 相邻子块间 cohesion > 0.7（高度相关）
- BDI > 2.0

**操作**：
```python
# 策略1：合并相邻高相关块
if cohesion(block_i, block_{i+1}) > 0.75:
    merged = merge_blocks(block_i, block_{i+1})
    # 合并后摘要：LLM 生成新摘要，或规则拼接

# 策略2：提升容量上限，允许单个块容纳更多 EDU
block.capacity = min(block.capacity * 1.5, MAX_CAPACITY)
# 触发重新切分：将相邻小块聚类到容量更大的块中
```

### 5.5 BOR-based 全局粒度校准

引入**边界重叠率（Boundary Overlap Ratio, BOR）**（源自对话切分前沿研究）：

```python
BOR = 系统检测到的边界数 / 人类标注的边界数（或期望边界数）

# 自适应调节阈值
if BOR > 1.5:      # 系统切得比期望多（过密）
    global_split_threshold *= 1.2   # 提高切分门槛，减少边界
elif BOR < 0.6:    # 系统切得比期望少（过疏）
    global_split_threshold *= 0.8   # 降低切分门槛，增加边界
```

**BOR 的估计**：在没有人工标注的情况下，用**熵变检测**作为代理：
- 相邻块间语义熵突增 → 边界
- 期望边界数 = 轮次数 × 平均每轮话题数（由 Ψ 分类器估计）

---

## 6. 渐进式摘要树

### 6.1 问题：长对话的摘要不是一次性的

当前：`summary = query[:80]` —— 一次性截断，永不更新。

升级：**渐进式四级摘要**，随对话演化动态升级。

### 6.2 四级摘要模型

```python
class ProgressiveSummary:
    v1_first_sentence: str      # 初始：首句（零成本）
    v2_key_entities: str        # 第一轮后：提取的实体列表（<1ms）
    v3_topic_evolution: str     # 多轮后：关键转折/决策点（规则提取）
    v4_condensed: str           # 长期：LLM 压缩为命题级摘要（异步触发）
    
    version: int = 1            # 当前最高可用版本
    last_updated: int = 0       # 最后更新轮次
    update_trigger: str = ""    # 触发条件："first_turn"/"entity_change"/"milestone"/"cold_compress"
```

**升级规则**：

| 触发条件 | 从 → 到 | 操作 | 延迟 |
|---|---|---|---|
| 块创建 | 无 → v1 | 取首句 | 0ms |
| 块内 EDU > 3 | v1 → v2 | 提取实体列表 + 意图标签 | <1ms |
| 块内轮次 > 5 或话题转折 | v2 → v3 | 提取关键决策点/转折点（规则） | <2ms |
| 块进入 Cold 状态（10轮未访问） | v3 → v4 | LLM 异步压缩为命题摘要 | 30-100ms（后台） |
| 块从 Cold 恢复为 Hot | v4 → v3 | 反压缩：加载 v3 + 最近 2 轮原文 | <1ms |

### 6.3 摘要作为树的"压缩表示"

```
活跃分支（Hot Path）：保留完整 EDU 原文
├─ [节点A] 完整对话
│   ├─ EDU1: "帮我写Python函数"
│   ├─ EDU2: "要处理CSV"
│   └─ EDU3: "输出JSON格式"

非活跃分支（Cold Path）：只保留摘要
├─ [节点B] v4摘要: "用户要求用Python编写CSV→JSON转换脚本，已讨论输入格式和输出结构"

归档分支（Frozen）：只保留 v2 实体标签
├─ [节点C] v2摘要: "实体: [Python, CSV, JSON] | 意图: TECHNICAL | 状态: resolved"
```

**上下文构建时**（供 LLM 使用）：
- Hot 块：完整原文（最近 3-5 轮）
- Warm 块：v3 演化摘要 + 最近 1 轮原文
- Cold 块：v4 压缩摘要
- Frozen 块：v2 实体标签（仅用于检索，不注入 LLM）

---

## 7. 数据模型

### 7.1 DiscourseBlock（话语块）

```python
@dataclass
class DiscourseBlock:
    block_id: str                          # UUID
    session_id: str
    
    # 内容
    atomic_units: List[EDU]                # 基本话语单元（子句/片段）
    raw_text: str                          # 原始文本（完整拼接）
    
    # 语义向量
    macro_embedding: List[float]           # 宏观语义向量（整体意思）
    micro_signature: str                   # 微观签名（主谓宾+属性的序列化）
    
    # 量化分数
    cohesion_internal: float               # 内部粘合度（块内 EDU 间平均 cohesion）
    cohesion_boundary_left: float          # 与左邻块的边界粘合度
    cohesion_boundary_right: float         # 与右邻块的边界粘合度
    
    # 意图
    primary_intent: str                    # 主导意图（TECHNICAL/ADVISOR/COMPANION/...）
    secondary_intents: List[str]           # 次要意图（可能产生挂接分支）
    intent_confidence: float               # 意图分类置信度
    
    # 实体（已补全）
    entities: List[Entity]                 # 结构化实体
    entity_signature: str                  # 实体签名（用于快速匹配）
    
    # 摘要
    summary: ProgressiveSummary            # 渐进式摘要
    
    # 树结构
    parent_block_id: Optional[str]         # 父块（逻辑归属）
    child_block_ids: List[str]             # 子块（再切割后）
    sibling_block_ids: List[str]           # 兄弟块（同父的其他块）
    depth: int                             # 在树中的深度
    
    # 动态容量
    capacity: int = 5                      # 当前可容纳的 EDU 上限
    current_edu_count: int = 0             # 当前 EDU 数量
    
    # 状态
    status: str = "active"                 # active | paused | resumed | cold | frozen
    created_at_turn: int = 0               # 创建轮次
    last_active_turn: int = 0              # 最后活跃轮次
    access_count: int = 0                  # 访问次数（用于冷热判定）
    
    # 索引
    _embedding_cache: Optional[List[float]] = None  # 缓存
    _hash: Optional[str] = None            # 文本哈希（用于去重）

@dataclass
class EDU:
    """基本话语单元（Elementary Discourse Unit）"""
    edu_id: str
    raw_text: str
    parsed_clause: ParsedClause            # 语法分解结果
    embedding: Optional[List[float]] = None # 子句级语义向量
    turn_index: int = 0                    # 所属轮次
    position_in_turn: int = 0              # 在该轮中的位置

@dataclass
class Entity:
    """结构化实体（已补全）"""
    text: str                              # 实体文本
    type: str                              # 类型：person/location/tech/object/abstract
    role: str                              # 角色：subject/object/predicate/attribute
    source: str                            # 来源：explicit（显式）/injected（头文件引入）/inferred（推断）
    confidence: float                      # 补全置信度
    origin_reference: Optional[str] = None # 指代来源（如 "上下文_轮次3"）
```

### 7.2 DiscourseBlockTreeManager

```python
class DiscourseBlockTreeManager:
    """
    摘要树管理器。
    上游：接收编译器三阶段输出的 List[ParsedClause] + CohesionScore
    下游：为 TopicTreeManagerV2 提供 Block 级路由，为 LLM 提供分层上下文
    """
    
    def __init__(self, session_id: str, 
                 embedding_engine: Optional[EmbeddingEngine] = None,
                 llm_provider: Optional[LLMProvider] = None):
        self.session_id = session_id
        self.embedding_engine = embedding_engine
        self.llm_provider = llm_provider
        
        # 内存结构
        self.blocks: Dict[str, DiscourseBlock] = {}
        self.root_block_id: Optional[str] = None
        self.current_block_id: Optional[str] = None
        
        # 快速索引
        self._entity_to_blocks: Dict[str, List[str]] = {}    # 实体 → 块ID列表
        self._intent_to_blocks: Dict[str, List[str]] = {}      # 意图 → 块ID列表
        self._turn_to_blocks: Dict[int, List[str]] = {}        # 轮次 → 块ID列表
        
        # 动态粒度参数
        self.global_split_threshold: float = 0.5               # 切分阈值（可自适应）
        self.optimal_blocks_per_topic: int = 4                 # 健康粒度目标
        self.max_capacity: int = 10                            # 单块最大 EDU 数
    
    def ingest_turn(self, turn_index: int, 
                    parsed_clauses: List[ParsedClause],
                    cohesion_scores: List[CohesionScore]) -> List[str]:
        """
        摄入一轮对话的编译器输出，创建/更新 DiscourseBlock。
        
        返回：本轮涉及的 block_id 列表（可能多个，因为一轮被切分到多个块）
        """
        # 1. 按 cohesion_score 将 parsed_clauses 聚类为 blocks
        # 2. 对每个 block：检查是延续当前块、挂接到历史块、还是新建块
        # 3. 触发动态粒度检查（过密/过疏）
        # 4. 更新索引
        # 5. 返回 block_id 列表
        pass
    
    def get_context_for_llm(self, active_block_id: str, 
                           max_tokens: int = 4000) -> str:
        """
        为 LLM 构建分层上下文。
        
        策略：
        - 活跃块（Hot）：完整原文（最近 3-5 轮）
        - 祖先块（Warm）：v3 演化摘要
        - 兄弟/非活跃块（Cold）：v4 压缩摘要
        - 远距离块（Frozen）：不注入（仅保留索引）
        """
        pass
    
    def find_block_by_reference(self, reference_text: str) -> Optional[str]:
        """
        解析指代（"回到刚才那个"、"那个Python脚本"）→ 定位 block_id。
        
        策略：
        1. 提取 reference_text 中的实体和意图
        2. 在 _entity_to_blocks 和 _intent_to_blocks 中检索
        3. 按 last_active_turn 排序，返回最匹配的块
        """
        pass
    
    def compress_cold_blocks(self):
        """后台任务：将 Cold 状态的块从 v3 升级到 v4 摘要。"""
        pass
```

---

## 8. 核心算法

### 8.1 轮内切分算法（Intra-turn Segmentation）

```python
def segment_turn(parsed_clauses: List[ParsedClause], 
                 window_size: int = 2) -> List[List[ParsedClause]]:
    """
    将一轮的 parsed_clauses 切分为 1~N 个话语块。
    
    基于 TextTiling + Cohesion Cliff 检测。
    """
    if not parsed_clauses:
        return []
    
    # 1. 计算相邻子句间的 cohesion（宏观+微观）
    cohesion_scores = []
    for i in range(len(parsed_clauses) - 1):
        macro = compute_macro_cohesion(parsed_clauses[i], parsed_clauses[i+1])
        micro = compute_micro_cohesion(parsed_clauses[i], parsed_clauses[i+1])
        score = combine_macro_micro(macro, micro)
        cohesion_scores.append(score)
    
    # 2. 检测 cohesion 断崖（局部最小值且低于阈值）
    boundaries = []
    for i, score in enumerate(cohesion_scores):
        # 局部最小值：比左右邻居都低
        left = cohesion_scores[i-1] if i > 0 else 1.0
        right = cohesion_scores[i+1] if i < len(cohesion_scores)-1 else 1.0
        
        if score < left and score < right and score < SPLIT_THRESHOLD:
            boundaries.append(i)  # 在 i 和 i+1 之间切分
    
    # 3. 按边界聚类
    blocks = []
    start = 0
    for b in boundaries:
        blocks.append(parsed_clauses[start:b+1])
        start = b + 1
    blocks.append(parsed_clauses[start:])
    
    # 4. 后处理：检查块大小（避免单句孤块）
    merged_blocks = merge_isolated_blocks(blocks, min_size=2)
    
    return merged_blocks
```

### 8.2 动态粒度调节算法（Dynamic Granularity Regulation）

```python
def regulate_granularity(self, parent_block_id: str):
    """
    检查并调节某父块下的子块粒度。
    """
    children = self.get_children(parent_block_id)
    if not children:
        return
    
    # 1. 计算 BDI
    avg_edus = sum(len(b.atomic_units) for b in children) / len(children)
    bdi = avg_edus / self.optimal_blocks_per_topic
    
    # 2. 过密检测：一家独大（某子块内部 cohesion 极高且 EDU 多）
    for child in children:
        if child.cohesion_internal > 0.9 and len(child.atomic_units) > self.max_capacity:
            # 再切割：在子块内部运行 TextTiling
            sub_blocks = self.split_block(child)
            self.replace_block(child, sub_blocks)
            return  # 一次只处理一个，避免震荡
    
    # 3. 过疏检测：主题过多（子块数量 > 8）
    if len(children) > 8:
        # 合并相邻高相关块
        for i in range(len(children) - 1):
            cohesion = self.compute_boundary_cohesion(children[i], children[i+1])
            if cohesion > 0.75:
                merged = self.merge_blocks(children[i], children[i+1])
                self.replace_blocks([children[i], children[i+1]], [merged])
                return
    
    # 4. 全局阈值自适应
    self.adapt_global_threshold(children)

def adapt_global_threshold(self, children: List[DiscourseBlock]):
    """基于 BOR 自适应调节全局切分阈值。"""
    # 估计 BOR：实际边界数 / 期望边界数
    actual_boundaries = len(children) - 1
    expected_boundaries = len(children) * 0.5  # 假设平均每话题 2 块
    bor = actual_boundaries / expected_boundaries if expected_boundaries > 0 else 1.0
    
    if bor > 1.5:
        self.global_split_threshold = min(self.global_split_threshold * 1.2, 0.9)
    elif bor < 0.6:
        self.global_split_threshold = max(self.global_split_threshold * 0.8, 0.1)
```

### 8.3 上下文构建算法（Context Assembly for LLM）

```python
def build_llm_context(self, active_block_id: str, max_tokens: int) -> str:
    """
    构建注入 LLM 的上下文字符串。
    核心策略：活跃路径完整原文 + 非活跃分支摘要 + 远距离冻结块不注入。
    """
    active_block = self.blocks[active_block_id]
    parts = []
    total_tokens = 0
    
    # 1. 活跃块：完整原文（最近 3-5 轮）
    hot_text = self.get_hot_text(active_block, max_turns=5)
    parts.append(f"【当前话题】\n{hot_text}")
    total_tokens += estimate_tokens(hot_text)
    
    # 2. 祖先链（Warm）：v3 演化摘要
    ancestor = self.get_parent(active_block_id)
    while ancestor and total_tokens < max_tokens * 0.7:
        summary = ancestor.summary.get_v3_or_best()
        parts.append(f"【前文摘要】{summary}")
        total_tokens += estimate_tokens(summary)
        ancestor = self.get_parent(ancestor.block_id)
    
    # 3. 相关兄弟块（Cold）：v4 压缩摘要
    siblings = self.get_relevant_siblings(active_block_id, top_k=3)
    for sib in siblings:
        if total_tokens >= max_tokens * 0.9:
            break
        summary = sib.summary.get_v4_or_best()
        parts.append(f"【相关话题】{summary}")
        total_tokens += estimate_tokens(summary)
    
    # 4. Frozen 块：不注入（保留索引，LLM 不知道其存在）
    
    return "\n\n".join(parts)
```

---

## 9. 与现有系统集成

### 9.1 与认知编译器的集成

`DiscourseBlockTree` 不是替换认知编译器，而是**承接其输出**。

```
用户输入
  ↓
【认知编译器】（已存在）
  ├── Stage 1: HeaderInjector → 实体补全
  ├── Stage 2: SyntacticDecomposer → 主谓宾提取
  └── Stage 3: CohesionScorer → 宏观/微观量化
  ↓
【DiscourseBlockTreeManager】（本设计）
  ├── ingest_turn() → 创建/更新 DiscourseBlock
  ├── regulate_granularity() → 动态调节
  └── build_llm_context() → 输出给 LLM
  ↓
【TopicTreeManagerV2】（已存在）
  ├── 将 DiscourseBlock 映射到 TopicNode（1:N 或 1:1）
  └── 提供 ReactFlow 导出、ForkPoint 检测等
```

### 9.2 与现有 TopicTreeManagerV2 的映射

| DiscourseBlockTree | TopicTreeManagerV2 | 映射关系 |
|---|---|---|
| DiscourseBlock | TopicNode | 1:1（块主导意图决定节点归属） |
| secondary_intents → 挂接分支 | 子节点（fork） | 次要意图创建挂接子节点 |
| cohesion_boundary | ForkPointLocator | 块边界检测为 ForkPointLocator 提供输入 |
| macro_embedding | EmbeddingEngine | 复用 embedding 向量 |
| progressive_summary | summary 字段 | 替换静态摘要 |
| entity_to_blocks | entity_index | 扩展为更细粒度的块级索引 |

**数据流**：
```python
# 在 InteractiveAgent.respond() 中
parsed_clauses = compiler.stage2.decompose(user_input)          # 语法分解
header_injected = compiler.stage1.inject(parsed_clauses, ...)    # 头文件引入
scores = compiler.stage3.score(header_injected, ...)             # 量化

# 新步骤：DiscourseBlockTree 处理
block_ids = block_tree.ingest_turn(turn_index, header_injected, scores)
# block_ids 可能包含多个块（一轮被切分）

# 映射到 TopicTree
for block_id in block_ids:
    block = block_tree.blocks[block_id]
    topic_tree.route_block(block)  # 将块路由到话题树节点
```

---

## 10. 评估指标

### 10.1 切分质量指标

| 指标 | 计算 | 目标 |
|---|---|---|
| **Purity** | 块内单一意图占比 | > 0.85 |
| **Coverage** | 所有意图被块覆盖的比例 | > 0.90 |
| **BOR** (Boundary Overlap Ratio) | 预测边界数 / 期望边界数 | 0.8 ~ 1.2 |
| **Cohesion Gini** | 块间 cohesion 分布的均衡度 | < 0.4 |

### 10.2 摘要质量指标

| 指标 | 计算 | 目标 |
|---|---|---|
| **ROUGE-L** | 摘要 vs 原文的 longest common subsequence | > 0.35（v4） |
| **Entity Recall** | 摘要中保留的实体占比 | > 0.80 |
| **Context Hit Rate** | 用户指代"刚才那个"时，系统正确召回率 | > 0.75 |
| **Token Compression** | 摘要 token 数 / 原文 token 数 | < 0.20（v4） |

### 10.3 系统性能指标

| 指标 | 目标 |
|---|---|
| 轮内切分延迟 | < 2ms（Fast Path） |
| 动态粒度调节 | < 5ms（每 10 轮触发一次） |
| 渐进摘要升级（v3→v4） | 后台异步，不阻塞主线程 |
| 上下文构建 | < 1ms（内存检索） |

---

## 11. 实现计划与风险

### 11.1 分阶段实现

| 阶段 | 内容 | 工期 | 依赖 |
|---|---|---|---|
| **Phase 1** | 认知编译器改造（通用化） | 1-2 天 | 已存在 `design_cognitive_compiler.md`，需去域化 |
| **Phase 2** | 轮内切分算法（Intra-turn Segmentation） | 2-3 天 | 复用现有 `EmbeddingEngine` + jieba |
| **Phase 3** | 宏观/微观量化框架 | 2-3 天 | 新增 `MacroScorer` / `MicroScorer` |
| **Phase 4** | 动态粒度调节 | 2-3 天 | 依赖 Phase 2/3 的 cohesion 输出 |
| **Phase 5** | 渐进式摘要 | 2-3 天 | 需 LLM 异步调用（v4） |
| **Phase 6** | 与 TopicTreeManagerV2 集成 | 1-2 天 | 调整 `TopicNode` 映射 |
| **Phase 7** | 评估与调优 | 2-3 天 | 构建测试数据集 |

**总工期**：约 12-18 天（串行，假设 1 人全职）。

### 11.2 风险与回退

| 风险 | 影响 | 缓解策略 |
|---|---|---|
| 轮内切分误切（一个话题被切成两块） | Purity 下降，用户体验断裂 | 阈值保守（默认 0.5），允许用户反馈纠正 |
| 微观量化依赖实体提取质量 | 主谓宾提取错误 → 微观失真 | Fast Path 失败时 fallback 到整句 embedding（宏观主导） |
| 渐进摘要 v4 的 LLM 调用成本 | 后台异步可缓解，但长会话累积 | 仅对 Cold 块触发，Hot 块永不调用 LLM |
| 动态粒度震荡（反复分裂-合并） | 树结构不稳定，缓存失效 | 引入冷却期（调节后 5 轮内不再次调节） |
| 与现有 V2 代码的兼容性 | 数据结构变更 | `DiscourseBlock` 作为 `TopicNode` 内部字段，不破坏现有 API |

---

## 附录 A：与现有设计文档的关系

| 本文档概念 | 来源文档 | 状态 |
|---|---|---|
| 头文件引入（HeaderInjector） | `design_cognitive_compiler.md` §4.2 | 已设计，需**通用化改造**（去域化） |
| 语法分解（SyntacticDecomposer） | `design_cognitive_compiler.md` §4.1 | 已设计，需**通用化改造** |
| 粘合度计算（CohesionScorer） | `design_cognitive_compiler.md` §4.3 | 已设计，需**拆分为宏观/微观** |
| 双结构管理（DualStructureManager） | `design_cognitive_compiler.md` §4.4 | 已设计，可复用 |
| TopicTreeManager | `design_topic_tree.md` | 已设计，需**适配 Block 级输入** |
| EmbeddingEngine / Ψ 分类器 | `manager_v2.py`（已实现） | 已运行，直接复用 |
| ForkPointLocator / MergeEngine | `manager_v2.py`（已实现） | 已运行，直接复用 |

**结论**：认知编译器的三阶段思想已存在，但面向**逆向工程域**（含 scan/patch/hook 等术语）。本文档将其**升维为通用对话框架**，并新增**动态粒度调节**、**渐进式摘要**、**宏观/微观量化**三个核心创新。

---

## 附录 B：快速参考卡片

```python
# 一句话判断：何时需要 DiscourseBlockTree？
if 用户一轮说多件事 or 隐含实体多 or 对话>50轮:
    use_discourse_block_tree = True
else:
    use_turn_level_tree = True  # 保持简单

# 一句话判断：何时分裂？
if block.cohesion_internal > 0.9 and len(block.atomic_units) > 8:
    split_block(block)

# 一句话判断：何时合并？
if len(siblings) > 8 and cohesion(sibling_i, sibling_{i+1}) > 0.75:
    merge_blocks(sibling_i, sibling_{i+1})

# 一句话构建 LLM 上下文：
context = hot_text(full) + warm_summary(v3) + cold_summary(v4) + frozen(exclude)
```
