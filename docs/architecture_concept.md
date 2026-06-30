# MemoryGraph 概念架构设计文档

## 1. 总体架构

MemoryGraph 是一个面向长对话的上下文记忆系统，采用**三级协同处理架构**（规则 → 本地小模型 → 远程大模型），通过**用户画像驱动**的自适应阈值系统实现个性化路由，以**话语树（Discourse Tree）**为核心数据结构组织多轮对话历史。

### 1.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层（App Layer）                        │
│  ─ 单轮输入接口（process_turn）                              │
│  ─ 语义搜索接口（semantic_search）                           │
│  ─ 任务查询接口（get_task_summary）                          │
├─────────────────────────────────────────────────────────────┤
│                   对话管理层（DiscourseManager）              │
│  ─ Turn 驱动（原始查询不可变）                               │
│  ─ ContextLayer（上下文注入，不污染原始查询）                │
│  ─ 一致性校验（ConsistencyChecker）                          │
├─────────────────────────────────────────────────────────────┤
│              核心引擎层（Core Engines）                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ 模式路由器   │  │ 用户识别引擎 │  │ 任务引擎            │   │
│  │ ModeRouter  │  │ UserEngine  │  │ TaskEngine          │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              话语引擎（DiscoursePipeline）             │   │
│  │  ─ 话语分割（DiscourseManager）                       │   │
│  │  ─ 语义索引（SemanticIndex）                         │   │
│  │  ─ 语义编码（SemanticEncoder）                       │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│              协同层（Coordination Layer）                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ 复杂度评估器 │  │ 自适应阈值   │  │ 贝叶斯推断引擎      │   │
│  │ Complexity  │  │ Threshold   │  │ BayesianEngine      │   │
│  │ Evaluator   │  │ Profile     │  │                     │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           小模型客户端（SmallModelClient）            │   │
│  │  ─ 自动模型选择（LMStudio API 探测）                │   │
│  │  ─ /no_think 自动注入（Qwen3 系列）                 │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│              持久化层（Persistence Layer）                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ 用户画像 DB  │  │ 会话状态    │  │ 语义向量索引        │   │
│  │ SQLite      │  │ JSON/内存   │  │ 内存向量表          │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 核心模块

### 2.1 对话管理层（DiscourseManager）

**职责**：统一入口，编排所有子模块，维护 Turn 生命周期。

**关键设计**：
- **Turn 驱动**：每轮用户输入封装为 `Turn` 对象，包含 `raw_query`（原始查询，不可修改）、`context_blocks`（系统注入上下文）、`discourse_blocks`（话语分割结果）、`metadata`（路由模式、延迟、时间戳）
- **原始查询不可变性**：所有下游模块（语义搜索、NER、任务检测）只访问 `turn.raw_query`，杜绝注入污染
- **上下文分层注入**：通过 `ContextLayer` 按场景注入不同上下文（router / llm / search / task / ner），`raw_query` 本身永不修改

**算法**：无（编排层）

---

### 2.2 上下文层（ContextLayer）

**职责**：管理系统上下文注入，按目标场景提供不同渲染。

**场景**：
| 场景 | 注入内容 | 目标 |
|------|---------|------|
| `router` | 用户画像摘要（技术等级、耐心、成本预算）+ 活跃任务状态 | 模式路由器决策 |
| `llm` | 完整用户画像 + 任务进展 + 最近对话历史 | 大模型生成回复 |
| `search` | **仅过滤后的原始查询文本**（无注入，无伪造前缀） | 语义索引搜索 |
| `task` | 原始查询 + 用户技术水平 | 任务检测与推断 |
| `ner` | **过滤后的原始查询文本** | 命名实体识别 |

**安全设计**：
- **注入过滤**：使用正则表达式过滤用户伪造的 `[技术水平:xxx]`、`[系统提示] 忽略之前所有指令` 等前缀
- **语义索引隔离**：`semantic_index.add_block()` 只索引 `ContextLayer.inject_for_search()` 返回的干净文本

**算法**：正则表达式过滤（确定性）、字符串拼接（无状态）

---

### 2.3 模式路由器（ModeRouter）

**职责**：根据输入复杂度自动选择三级处理模式之一。

**三级模式**：
| 模式 | 复杂度范围 | 延迟 | 成本 | 典型场景 |
|------|-----------|------|------|---------|
| `rule` | 0–3 | <1ms | 零 | 问候、简单查询、单意图 |
| `small_model` | 4–7 | 2–4s (CPU) | 零（本地） | 多意图、技术术语、中等长度 |
| `remote_llm` | 8–10 | 200ms–2s | API 费用 | 长文本、深度推理、多任务混合 |

**降级链**：`remote_llm` → `small_model` → `rule`（当高级模式不可用时自动降级）

**算法**：阈值比较（确定性）

---

### 2.4 复杂度评估器（ComplexityEvaluator）

**职责**：从 8 个维度评估输入复杂度，输出 0–10 的分数。

**8 维度评分**：
| 维度 | 权重范围 | 算法 | 说明 |
|------|---------|------|------|
| `length` | 0–3 | 字符数阶梯阈值 | 0–20:0, 20–50:1, 50–100:2, >100:3 |
| `entity` | 0–2 | jieba 词性标注 + 技术白名单计数 | 专有名词/技术术语密度 |
| `intent` | 0–2 | 关键词匹配（多意图信号词） | "然后"、"另外"、"最后" 等 |
| `history` | 0–3 | 对话轮次线性增长 | 轮次 > 10 时封顶 |
| `cohesion` | 0–2 | 话语内聚性检测（预留） | 话语块拆分后的主题一致性 |
| `ambiguity` | 0–2 | 歧义词/模糊表达检测 | 同音错字、缩写、不完整句子 |
| `task_switch` | 0–2 | 任务切换关键词 | "回到刚才"、"换个话题" 等 |
| `multi_intent` | 0–4 | 多意图信号词密度 | 2 个信号词 → +4 分（直接封顶） |

**算法**：加权线性求和 + 全局偏移（`base_offset`）

---

### 2.5 自适应阈值系统（ThresholdProfile）

**职责**：维护每个用户的独立阈值画像，根据反馈动态调整路由边界。

**双引擎架构**：

#### 2.5.1 确定性引擎（快速路径）
- **线性反馈**：用户纠错 → `base_offset += 1`；小模型不够 → `small_model_threshold -= 1`
- **模式分布学习**：80%+ 查询触发 `small_model`/`remote_llm` → 整体提升 `base_offset`
- **满意度 EMA**：指数移动平均更新满意度估计

#### 2.5.2 贝叶斯引擎（概率推断）
- **Beta 分布**：二分类观测（`is_impatient`、`is_satisfied`）
  - 更新：`α += strength`（成功）/ `β += strength`（失败）
  - 后验均值：`α / (α + β)`
- **Dirichlet 分布**：多分类观测（`tech_level`、`mode_preference`、`style`）
  - 伪计数 + 置信度更新
  - 后验概率：`count_i / Σcount_j`
- **Gaussian 分布**：连续值观测（`base_offset`、维度权重）
  - 共轭先验更新：precision 加权平均
  - 后验：`μ_post = (μ_prior * τ_prior + x * τ_obs) / (τ_prior + τ_obs)`
- **Thompson Sampling**：从后验分布采样选择阈值，实现探索-利用平衡

**触发条件**：评估次数 > 5 时自动切换贝叶斯采样；≤ 5 时使用确定性阈值（冷启动保护）

**算法**：Beta 分布、Dirichlet 分布、Gaussian 共轭先验、Thompson Sampling

---

### 2.6 用户识别引擎（UserEngine）

**职责**：从用户输入中提取多维度画像，并做一致性校验。

**画像维度**：
| 维度 | 类别 | 推断方式 |
|------|------|---------|
| `tech_level` | beginner / intermediate / expert / unknown | 关键词密度（自我描述 + 行为复杂度） |
| `patience_level` | impatient / neutral / patient | 情绪关键词检测 |
| `style` | concise / detailed / tutorial / unknown | 风格关键词匹配 |
| `attention_span` | short / medium / long | 话题切换频率统计 |
| `preferred_tools` | List[str] | 正则表达式匹配工具名 |
| `domains` | List[str] | jieba 词性标注 + 技术白名单过滤 |
| `language` | zh / en / mixed / unknown | 字符集检测 |

**一致性校验器（ConsistencyChecker）**：
- **自我描述 vs 行为推断**：用户自称 "expert" 但查询复杂度低（beginner 级）→ 采信行为推断
- **跨轮比较**：最近 5 轮 Turn 的行为模式 vs 当前轮自我描述
- **加权置信度**：一致时置信度 0.9，不一致时降权至 0.5–0.7

**算法**：
- 关键词匹配（确定性）
- jieba 分词 + 词性过滤（POS tagging）
- 正则表达式（工具提取）
- 一致性校验：行为-描述对比 + 跨轮投票

---

### 2.7 任务引擎（TaskEngine）

**职责**：从对话中检测任务类型、追踪进展、管理子任务树。

**任务类型**：`code`（编码）、`analyze`（分析）、`learn`（学习）、`compare`（对比）、`debug`（调试）、`none`（无任务）

**任务状态**：`started` → `continued` / `switched` → `completed` / `paused`

**子任务树**：
- `parent_task_id` + `children_ids` 双向链表
- DFS 遍历 `get_task_tree()` 获取完整子树
- 自动进展推断：
  - 第一轮 → 10%
  - 中间轮 → 50%
  - 结果确认 → 100%

**里程碑（Milestone）**：
- 每 2 块话语自动触发摘要
- 标签："需求分析"、"方案设计"、"实现完成"、"测试调试"
- 百分比：0–100% 连续进展

**任务恢复**：
- 关键词检测："回到刚才的…"、"继续之前的…"、"刚才那个…"
- 匹配历史活跃任务类型，恢复为 `continued` 状态

**算法**：
- 关键词模板匹配（任务类型检测）
- 状态机（任务生命周期）
- 规则推断（进展百分比）
- 小模型辅助（LLM 生成摘要，预留接口）

---

### 2.8 话语引擎（DiscoursePipeline）

**职责**：将长文本分割为话语块（Discourse Block），组织为树结构。

**话语分割策略**：
- 长文本（> 100 字）→ 按段落/句子切分
- 短文本 → 保持为单一块
- 每个块包含：ID、类型、文本、摘要（v1/v2/v3）、意图标签、时间戳

**三级摘要**：
- v1：原文（100% 保留）
- v2：压缩文本（保留关键信息，去除冗余）
- v3：结构化标签（主题词 + 意图 + 关键实体，LLM 生成）

**热/温/冷分层**：
- 热层：最近 5 轮，完整文本
- 温层：5–20 轮，v2 摘要
- 冷层：> 20 轮，v3 结构化标签

**算法**：
- 字符数阈值分割（确定性）
- 话语粘合度检测（预留：语义连贯性模型）

---

### 2.9 语义索引（SemanticIndex）

**职责**：对所有话语块进行向量编码，支持语义搜索和跨会话引用。

**编码器**：BGE-small-zh（512-dim，BAAI 开源）
- 中文语义质量优秀，模型仅 13MB
- 延迟：首次加载 ~2s，后续编码 <100ms
- 设备：CPU（torch 推理）

**索引结构**：
- `block_id → 512-dim 向量`（内存哈希表）
- `block_id → raw_text`（文本映射）
- 懒加载：首次搜索时初始化编码器

**搜索算法**：
- 余弦相似度：`sim = (q · d) / (||q|| · ||d||)`
- Top-k 返回（默认 k=5）
- 最小阈值过滤（默认 0.3）

**跨会话引用**：
- 全局块索引：`_global_block_index[block_id] → DiscourseBlock`
- 支持通过 `block_id` 直接获取任意会话的历史块

**算法**：
- BGE 编码（Transformer 编码器）
- 向量归一化 + 余弦相似度
- Top-k 排序（快速选择）

---

### 2.10 小模型客户端（SmallModelClient）

**职责**：与本地 LMStudio 小模型交互，提供降级保护。

**自动模型选择**：
1. 通过 LMStudio `/v1/models` API 探测可用模型
2. 排除 Embedding 模型
3. 按参数大小排序，选择最小模型（Nemotron-3-Nano-4B 优先于 Qwen3.5-9B）
4. 自动注入 `/no_think`（Qwen3 系列 reasoning 模式修复）

**参数覆盖**：
- `max_tokens=300`（覆盖 reasoning tokens 占用）
- `temperature=0.1`（低熵，确定性输出）
- 超时：10 秒

**降级链**：
- 小模型不可用 → 回退到规则模式
- 小模型超时 → 标记为不可用，后续调用跳过

**算法**：无（HTTP 客户端 + 启发式模型选择）

---

## 3. 数据流

### 3.1 单轮处理流程（Turn 驱动）

```
用户输入 query
    │
    ▼
┌────────────────────────┐
│ 1. 创建 Turn           │  ← raw_query = query（不可修改）
│    Turn(turn_index,    │
│          raw_query)    │
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 2. ContextLayer 注入   │  ← 生成 ContextBlock[]，不修改 raw_query
│    - router_context    │
│    - llm_context       │
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 3. 用户特征提取        │  ← 在 raw_query 上运行（过滤后）
│    UserExtractor       │
│    - 注入过滤          │  ← 正则过滤伪造前缀
│    - 一致性校验        │  ← 跨轮行为对比
│    - 更新画像          │
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 4. 模式路由            │  ← ComplexityEvaluator + ThresholdProfile
│    ModeRouter.decide() │
│    - 贝叶斯 Thompson    │  ← 采样（如果 evaluations > 5）
│      Sampling           │
│    - 降级检查           │  ← remote → small → rule
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 5. 话语分割            │  ← 在 raw_query 上运行（干净文本）
│    DiscoursePipeline   │
│    - split_blocks()    │
│    - 生成摘要 v1/v2/v3 │
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 6. 任务检测            │  ← 在 raw_query 上运行
│    TaskManager         │
│    - detect_and_update()│
│    - 记录轮次（一次）   │  ← _record_turn_once()
│    - 话题切换检测       │  ← 加权重叠度 < 0.5 → switch
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 7. 语义索引            │  ← 只索引过滤后的干净文本
│    SemanticIndex       │
│    - add_block()       │
│    - BGE 编码          │
└────────────────────────┘
    │
    ▼
┌────────────────────────┐
│ 8. 组装输出            │  ← ContextBlock + DiscourseBlock
│    _assemble_context() │
│    - 用户画像前缀      │  ← 仅用于 LLM 输入，不污染原始数据
│    - 话语上下文        │
└────────────────────────┘
    │
    ▼
返回最终上下文字符串
```

### 3.2 话题切换检测数据流

```
Turn N-1: raw_query = "帮我写一个 Flask API"
    │
    ▼ jieba 分词 → 提取关键词（名词/动词/英文）
    keywords = {flask, api, 写, 搭}
    │
Turn N: raw_query = "赣州天气怎么样"
    │
    ▼ jieba 分词 → 提取关键词
    keywords = {赣州, 天气, 怎么样}
    │
    ▼
┌────────────────────────┐
│ 加权重叠度计算          │
│ - 语义相似度 (BGE)    │  ← 50% 权重
│ - 关键词 Jaccard      │  ← 17% 权重
│ - 技术术语重叠        │  ← 17% 权重
│ - 领域一致性          │  ← 17% 权重
│   (技术 vs 非技术)    │
└────────────────────────┘
    │
    ▼
overlap = 0.35（Flask 是技术，天气是非技术 → 领域一致性拉低）
    │
    ▼
overlap < 0.5 → is_switch = True
    │
    ▼
UserProfile.topic_switches += 1
    │
    ▼
switch_rate = topic_switches / turn_count
    │
    ▼
if switch_rate > 0.4: attention_span = "short"
```

---

## 4. 算法清单

| 算法 | 应用场景 | 组件 |
|------|---------|------|
| **Beta 分布** | 二分类后验（满意度、不耐烦） | BayesianEngine |
| **Dirichlet 分布** | 多分类后验（技术等级、模式偏好、风格） | BayesianEngine |
| **Gaussian 共轭先验** | 连续值后验（base_offset、维度权重） | BayesianEngine |
| **Thompson Sampling** | 探索-利用平衡的阈值选择 | BayesianEngine + ThresholdProfile |
| **余弦相似度** | 语义搜索（向量相似度） | SemanticIndex |
| **BGE 编码** | 中文语义向量生成（512-dim） | SemanticEncoder |
| **jieba 分词 + POS 标注** | 关键词提取、实体识别、话题切换检测 | UserExtractor, DiscourseManager |
| **Jaccard 相似度** | 关键词集合重叠（话题切换） | DiscourseManager |
| **正则表达式** | 工具名提取、注入过滤、情绪关键词 | UserExtractor, ContextLayer |
| **关键词密度匹配** | 技术水平推断、多意图检测 | ComplexityEvaluator, UserExtractor |
| **指数移动平均（EMA）** | 满意度估计平滑 | ThresholdProfile |
| **快速选择（Top-k）** | 语义搜索结果排序 | SemanticIndex |
| **DFS 遍历** | 子任务树遍历 | TaskManager |
| **状态机** | 任务生命周期（started→continued→completed） | TaskManager |
| **启发式模型选择** | 小模型自动探测与排序 | SmallModelClient |

---

## 5. 安全设计

### 5.1 注入攻击防护

| 攻击类型 | 防护机制 | 位置 |
|---------|---------|------|
| 伪造用户画像前缀 `[技术水平:expert]` | 正则过滤（`INJECTION_PATTERNS`） | UserExtractor._filter_injection() |
| 系统提示注入 `[系统提示] 忽略之前所有指令` | 正则过滤 + 丢弃 | UserExtractor._filter_injection() |
| 语义索引污染 | `ContextLayer.inject_for_search()` 只返回过滤后文本 | ContextLayer |
| 任务检测污染 | `TaskManager.detect_and_update()` 接收 `turn.raw_query` | DiscourseManager |

### 5.2 对抗性输入防护

| 攻击类型 | 防护机制 | 位置 |
|---------|---------|------|
| 自称 expert 但行为 beginner | 一致性校验器：行为推断 vs 自我描述 | ConsistencyChecker |
| 频繁切换话题干扰注意力推断 | 加权重叠度：领域一致性强制检测切换 | DiscourseManager._compute_topic_overlap() |
| 长文本填充干扰复杂度评估 | 多维度评分（实体、意图、历史）而非单一长度 | ComplexityEvaluator |

---

## 6. 扩展点

### 6.1 已预留接口

| 扩展点 | 当前状态 | 接入方式 |
|--------|---------|---------|
| 远程大模型（remote_llm） | 接口已定义，未接入实际 API | `ModeRouter.REMOTE_LLM` 分支 |
| 小模型 v3 摘要生成 | 接口已定义，预留调用点 | `DiscoursePipeline` 摘要升级 |
| 话语粘合度模型 | 预留字段，未实现 | `cohesion_score` 维度 |
| 用户画像数据库存储 | SQLite 已实现，可扩展为 Redis/PostgreSQL | `UserManager._save_to_db()` |
| 语义索引持久化 | 内存哈希表，可扩展为 FAISS/Milvus | `SemanticIndex._vectors` |

### 6.2 未来增强方向

| 方向 | 可能算法 |
|------|---------|
| 多轮对话意图追踪 | HMM / CRF / 对话状态追踪（DST） |
| 用户画像向量化 | 用户 Embedding（类似用户画像的 dense representation） |
| 动态话语重排序 | 强化学习（RLHF 风格，根据用户反馈重排历史） |
| 跨用户群体先验 | 层次贝叶斯（Hierarchical Bayesian），用户群体共享超参数 |
| 语义索引 ANN 加速 | HNSW / FAISS IVF，支持百万级向量 |
| 多模态输入 | CLIP 编码器（图像 + 文本联合语义） |

---

## 7. 性能基准

| 指标 | 数值 | 环境 |
|------|------|------|
| 规则模式延迟 | <1ms | 纯本地计算 |
| 小模型模式延迟 | 2–4s / 轮 | Nemotron-3-Nano-4B, CPU, 8GB RAM |
| BGE 编码延迟 | <100ms / 块 | 首次加载 ~2s |
| 50 轮压力测试 | 23.1s 总时间 | 0.46s / 轮，无内存泄漏 |
| 贝叶斯收敛 | 100 次观测后置信度 >0.98 | 远程 LLM 偏好 |
| SQLite 持久化 | <10ms / 写 | 用户画像序列化 |

---

## 8. 术语表

| 术语 | 定义 |
|------|------|
| **Turn** | 用户的一次完整输入轮次，包含原始查询、上下文块、话语块、元数据 |
| **ContextBlock** | 系统注入的上下文单元（类型、内容、优先级），不进入原始查询 |
| **DiscourseBlock** | 话语分割后的单元，包含文本、摘要、意图标签 |
| **ThresholdProfile** | 用户自适应阈值画像，包含维度权重、全局偏移、贝叶斯后验 |
| **Thompson Sampling** | 从后验分布采样做决策，高不确定性时自动探索 |
| **SemanticIndex** | 基于 BGE 向量的内存语义搜索引擎 |
| **ContextLayer** | 按场景（router/llm/search/task/ner）注入不同上下文的中间层 |
| **ConsistencyChecker** | 跨轮行为一致性校验器，检测自我描述与实际行为的不匹配 |
| **PersistentSnapshot** | 跨会话持久化的用户画像快照（明确字段边界） |
| **RuntimeState** | 仅内存的会话状态（活跃任务、当前轮次、会话起始时间） |
