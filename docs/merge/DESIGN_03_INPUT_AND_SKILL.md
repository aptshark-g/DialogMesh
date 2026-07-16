# 输入解析与技能层设计

> **本文档合并自以下源头文档**（原文件保留于 `docs/v3.0/` 不删除）：
> - `DESIGN_TIERED_PARSER.md` — 三层递进句法分析（规则→spaCy→LLM）
> - `DESIGN_TIERED_ACTION_RESOLVER.md` — 共享分级动作解析器、DomainAdapter
> - `DESIGN_SKILL_LAYER.md` — Capability Blueprint、Skill Lifecycle、蒸馏引擎
> - `DESIGN_DOCUMENT_INGESTION_LAYER.md` — Document Tree、Observation Extractor
> - `design_layer0_pcr_and_layer1_intent_parser.md` — PCR + IntentParser 概念（取 v4 仍需要的部分）

---

## 1. PCR (Pre-Cognitive Router)

> 源自 `design_layer0_pcr_and_layer1_intent_parser.md` §2 + `DESIGN_FULL_CONCEPT.md` §2

### 1.1 定位

PCR 是系统的最前端过滤器，在完整解析之前对用户输入进行快速认知评估。核心功能不是"理解内容"，而是"评估认知情境"——在毫秒级确定：

1. 用户的输入是否值得解析？（噪声过滤）
2. 用户期望什么样的响应模式？（期望推断）
3. 用户的当前认知状态如何？（画像快速评估）

哲学：**"不解析无意义的输入，不浪费计算在无价值的路由上。"**

### 1.2 核心组件

#### 噪声检测器

三维噪声度量：

$$N = \alpha \cdot N_{semantic} + \beta \cdot N_{structural} + \gamma \cdot N_{referential}$$

- 语义噪声：填充词、无关修饰、情绪性语言（关键词密度+信息熵）
- 结构噪声：语法混乱程度、格式异常
- 参照噪声：与对话历史不一致的引用

默认权重 α=0.5, β=0.3, γ=0.2。自适应阈值基于用户历史噪声水平调整。

#### 期望推断器

三种基本期望类型：

| 期望 | 定义 | 示例 |
|:---|:---|:---|
| TOOL | 用户期望系统执行具体动作 | "读取内存地址 0x0040" |
| ADVISOR | 用户期望分析、解释或建议 | "这段代码有什么问题？" |
| COMPANION | 用户期望开放式对话 | "你觉得呢？" |

基于多特征贝叶斯分类，先验概率动态调整：$P_{t}(E) = \lambda \cdot P_{global}(E) + (1-\lambda) \cdot P_{user}(E)$

#### 认知画像快速评估

四个维度（与完整画像 Track A 对应）：

| 维度 | 推断方式 |
|:---|:---|
| 元认知 | 输入的精确性、自指性语言 |
| 发散性 | 主题切换频率、词汇多样性 |
| 稳定性 | 输入长度、词汇、标点风格一致性 |
| 信心度 | 情态动词、不确定词频率 |

使用轻量特征工程（词典匹配 + 统计特征），无需 LLM 调用，<5ms 完成。

### 1.3 PCR 输出

| 字段 | 说明 | 下游使用 |
|:---|:---|:---|
| `expectation` | TOOL / ADVISOR / COMPANION | 决定 IntentParser 解析策略 |
| `noise_level` | [0,1] | 影响解析阈值和澄清策略 |
| `complexity_level` | [0,1] | 决定任务分解粒度 |
| `cognitive_profile` | 四维度快照 | 动态调优所有层参数 |
| `execution_mode` | 保守/激进 | 决定系统响应风格 |

---

## 2. Tiered Parser

> 源自 `DESIGN_TIERED_PARSER.md`

### 2.1 为什么需要三层

| 方案 | 延迟 | 准确率 | 瓶颈 |
|:---|:---|:---|:---|
| 纯规则 | <5ms | ~75% | 词典覆盖率有限 |
| spaCy 依存分析 | ~30ms | ~92% | 中文准确率低于英文 |
| LLM | ~500ms | ~97% | 延迟太高 |

三层递进：规则先跑（75% 覆盖，<5ms），置信度不够升级到 spaCy（92%，~30ms），再不够升级到 LLM（97%，~500ms）。加权平均延迟 ~10ms。

### 2.2 三层架构

```
输入文本
  │
  ▼
Tier 1: SyntacticDecomposer v2（规则，<5ms）
  │  confidence > 0.7 → 返回
  │  confidence < 0.7
  ▼
Tier 2: spaCy + Benepar 协同（~30ms）
  │  confidence > 0.85 → 返回
  │  confidence < 0.85 或多主语/歧义
  ▼
Tier 3: LLM + Schema Guard（~500ms）
  │  Schema Guard 验证 + 硬约束注入
  ▼
  返回高置信度 ParsedClause
```

### 2.3 Tier 1: SyntacticDecomposer v2

零依赖，中英双语词典，<5ms。

能力：否定检测（30+ 词）、不确定检测（15+ 词）、祈使检测（20+ 词）、谓语提取（七类动词 80+ 词）、宾语提取、实体提取（CamelCase + 关键词）。

触发升级条件：谓语未匹配、否定+不确定同时出现、多连词检测。

### 2.4 Tier 2: spaCy + Benepar 协同

spaCy 提供依存句法（谁是什么角色），Benepar 提供成分句法（短语边界在哪）。

协同：VP 边界取 Benepar 的 VP 子树，根动词取 spaCy 的 ROOT。两个模型同时确认时置信度 0.92。

中文场景：Benepar 不支持中文，Tier 2 中文用 Stanza 替代。

### 2.5 Tier 3: LLM + Schema Guard

仅当 Tier 2 无法确定时触发。

Prompt 注入 Tier 1/2 已解析的部分作为种子。注入硬约束（谓语必须在 PREDICATE_DICT 中）。

Schema Guard 验证：谓语必须在词典中、否定句不能有 create 意图、主谓宾必须非空。LLM 做神经部分，Schema Guard 做符号约束。

### 2.6 级联协同

每层输出同一 `ParsedClause` 结构。上层结果不丢弃——传给下层当种子。减少下层搜索空间。

### 2.7 与 Observation Compiler 的关系

Observation Compiler 是 TieredParser 的唯一调用方：

```
Event IR → TieredParser.parse(text) → ParsedClause
  ParsedClause.predicate → Observation ActionType
  ParsedClause.object → Observation Entity
  ParsedClause.negation → Observation.modifiers[negated]
  ParsedClause.confidence → Observation.confidence
```

---

## 3. Tiered Action Resolver

> 源自 `DESIGN_TIERED_ACTION_RESOLVER.md`

### 3.1 定位：共享分类内核

v4 中所有"给定输入 → 输出候选类别"的场景全部是同一种计算：`f(domain_context, input) → ranked_candidates`。

TieredActionResolver 不是又增加一个 wrapper。它是把每个 wrapper 内部的分类逻辑提取出来作为共享引擎：

```
TieredActionResolver (共享内核)
  ├── Tier 0: 域规则匹配
  ├── Tier 1: 域嵌入语义匹配
  └── Tier 2: 域 LLM 分类

DialogueInterpreter    = TieredActionResolver + dialogue_adapter
EngineeringInterpreter = TieredActionResolver + engineering_adapter
BehaviorInterpreter    = TieredActionResolver + behavior_adapter
IntentParser           = TieredActionResolver + intent_adapter
NegativeKB             = TieredActionResolver + negative_adapter
```

每个域只需提供 DomainAdapter（规则 + 嵌入索引 + LLM 提示词）。分类的编排、升级、反馈闭环全部由共享引擎完成。

### 3.2 三级递进

```
Tier 0: Domain Rule Matching (~1ms, ~70%)
  已知动词/模式 → action 直接映射
  "添加" → "add", "删除" → "remove"

Tier 1: Domain Embedding Semantic Match (~10ms, ~90%)
  embed(input) → nearest neighbor in Domain Index
  cosine_sim > threshold → 匹配

Tier 2: Domain LLM Classification (~500ms, ~98%)
  LLM + domain prompt → structured action output
  反馈回流: 新 action → 写回 Tier 0 规则表 + Tier 1 嵌入索引
```

### 3.3 DomainAdapter 接口

每个域提供：
- 规则表（动词/模式 → action 映射）
- 嵌入索引（action → 向量）
- LLM 提示词模板

### 3.4 Interaction Action vs Domain Action

关键设计：两个 action 层分离。

- **Interaction Action**（对话域）：`ask`/`confirm`/`reject`/`request_change`/`inform` — 描述用户交互意图
- **Domain Action**（工程/行为域）：`reorder`/`add`/`remove`/`configure` — 描述领域动作

同一 Event 的两个 DomainObservation 自然承载这两层。

---

## 4. Skill Layer

> 源自 `DESIGN_SKILL_LAYER.md`

### 4.1 定位：能力蓝图而非结构化 Prompt

Harness 风格的 Skill 本质是带结构的 Prompt：`Condition → Prompt Template → LLM`。它依赖 LLM 执行全部工作。

v4 的 Capability Blueprint：

```
Capability Blueprint
├── Goal          （为什么做——目标）
├── Constraints   （不能违反哪些——引用 Engineering Chain）
├── Strategy      （推荐策略——引用 Pattern + Decision）
├── Action Graph  （语义动作序列——独立于执行器）
├── Verification  （如何验证——引用 Constraint Engine）
└── Reflection    （执行后反馈——引用 Hypothesis Engine）
```

Skill 是离散能力，Capability Layer 是能力的演化网络。

### 4.2 四层 Procedure 结构

| 层 | 回答 | 示例 |
|:---|:---|:---|
| Goal | 为什么做 | "建立可运行的 Gateway" |
| Constraints | 哪些不能违反 | 必须有 Metrics, Health, Config（引用 Engineering Chain） |
| Strategy | 推荐怎么做 | Plugin Pattern, Factory Pattern |
| Action Graph | 具体做什么 | Create Module → Register → Run Test → Update Config |

关键设计原则：
- 上层只存 references，不重复存储
- Action Graph 是抽象动作——不绑定工具名。`Create Module` 而非 `mkdir src`
- Executor 映射独立——Action → tool/LLM/agent 绑定可运行时替换

### 4.3 Skill Lifecycle

借鉴 Hypothesis Engine 的共识模型——Skill 不是"达到阈值即创建"，而是渐进生长。

```
Candidate Skill → Verified Skill → Core Skill
     ↑
  (可回退)
```

| 状态 | 条件 | 说明 |
|:---|:---|:---|
| `candidate` | 蒸馏引擎检测到重复模式 | 初始候选，低置信度 |
| `verified` | 多维度评估通过 | support≥5, generality≥0.60, benefit≥0.70 |
| `core` | 连续 N 次成功应用 | support≥15, generality≥0.80, stability≥0.90 |
| `deprecated` | 长时间未使用或策略更新 | 标记废弃，保留溯源 |

### 4.4 双轨：External + Internal

| | External Skill | Internal Skill |
|:---|:---|:---|
| 来源 | GitHub, Docs, RAG, 用户导入 | Knowledge, Behavior, Engineering Graph |
| 特点 | 可信但属于通用知识 | 只适用于当前用户/项目 |
| 示例 | FastAPI 初始化, React 组件模板 | "本项目的所有 Middleware 必须有 Metrics" |

两条来源进入同一个 Candidate Pool，经过同一套 Evaluation Engine 评估。

### 4.5 蒸馏引擎

从存储中识别重复模式：

| 数据源 | 蒸馏信号 | 产出 |
|:---|:---|:---|
| Engineering Chain Constraint | 多个项目共享相同约束 | ConstraintSkill |
| Hypothesis consensus | 共识度 > 0.85 | PreferenceSkill |
| Knowledge freeze 聚类 | 多个 Knowledge 共享相同对象/结构 | PatternSkill |
| Behavior 模式 | 重复的行为序列 | BehaviorSkill |

不是"重复 5 次 → Skill"——是累计多维信号。

### 4.6 白盒溯源

每个 Skill 的 Goal/Constraint/Strategy 都引用具体的 Knowledge/Pattern/Decision 节点。可以追溯到：
- 哪些 Observation 产生了这条 Knowledge
- 哪些 Hypothesis 投票支持了冻结
- 哪些 Pattern 匹配了当前操作

---

## 5. Document Ingestion Layer

> 源自 `DESIGN_DOCUMENT_INGESTION_LAYER.md`

### 5.1 问题

v4 的认知链只能处理已经进入系统的信息。外部文档（MD、PDF、代码、网页）还没有被转换成 v4 能理解的"认知对象"。

传统 RAG 的问题：它做的是"用户问什么，返回哪段文本"。v4 需要的是"这段文本在知识体系里是什么角色"。

核心洞察：**文档不是事件流，而是静态知识场。** 但它们都可以生成 Observation。

### 5.2 架构

```
外部文档 (MD/PDF/Code/Web)
  │
  ▼
DocumentParser → DocumentTree → ObservationExtractor → ChunkStrategy
  │
  ▼
v4 认知链 (ObservationPool → HypothesisEngine → Knowledge → Skill)
```

### 5.3 DocumentNode

```python
@dataclass
class DocumentNode:
    node_id: str                    # hash(source_path + heading_path)
    source_path: str
    heading_path: List[str]         # ["# DialogMesh", "## v4", "### Context Compiler"]
    level: int
    raw_text: str
    node_type: str                  # heading | paragraph | code | table | list
    children: List["DocumentNode"]
    # 认知元数据（由 ObservationExtractor 填充）
    observed_concepts: List[str]
    observation_type: str           # definition | constraint | procedure | example | relation | parameter
```

与 DiscourseBlockTree 的区别：

| 维度 | DocumentTree | DiscourseBlockTree |
|:---|:---|:---|
| 结构来源 | 文档标题层级 | 对话 cohesion score |
| 产生方式 | 一次性解析 | 动态累积 |
| 时间性 | 静态 | 动态 |
| 用途 | 知识检索 | 对话上下文 |

### 5.4 ObservationExtractor

不是简单的 chunker。它解释文档内容为认知原语：

| 类型 | 检测规则 | 示例 |
|:---|:---|:---|
| `definition` | 含 "是..."、"定义为..." | "Context Compiler 是将多域知识编译为 IR 的组件" |
| `constraint` | 含 "必须..."、"不能..." | "BudgetAllocator 必须保证总 token ≤ 预算" |
| `procedure` | 含 "步骤..."、"首先...然后..." | "Hypothesis 冻结流程" |
| `example` | 含 "例如..." | "例如：min_support=8 时..." |
| `relation` | 含 "依赖..."、"导致..." | "Knowledge 依赖于 Hypothesis 投票" |
| `parameter` | 含 "参数..."、"默认值..." | "community_resolution: 1.0" |

提取方式：规则匹配（快速，覆盖 80%）+ LLM 辅助（慢，覆盖复杂语义，可选）。

### 5.5 ChunkStrategy

| 策略 | 速度 | 质量 | 适用场景 |
|:---|:---|:---|:---|
| FixedSizeChunk | ⚡⚡⚡ | ⭐⭐⭐ | Fast Path 紧急处理 |
| HeaderChunk | ⚡⚡⚡ | ⭐⭐⭐⭐ | Markdown 结构保留 |
| SemanticChunk | ⚡⚡ | ⭐⭐⭐⭐⭐ | 精度优先 |

### 5.6 成功标准

| 指标 | 目标 |
|:---|:---|
| 导入时间 | 100 篇 MD < 5 分钟 |
| 检索质量 | 问"Context Compiler 设计"，返回定义+流程+参数 |
| 认知闭环 | 导入的文档能进入 Hypothesis → Knowledge 冻结 |
| 端到端 | `dialogmesh ingest docs/` → `dialogmesh chat "什么是 Context Compiler?"` → 正确回答 |

---

## 6. 实现状态

| 组件 | 文件 | 状态 |
|------|------|------|
| `TieredParser` | `tiered/parser.py` | ✅ 三层递进 |
| `SyntacticDecomposer` | `tiered/syntactic_decomposer.py` | ✅ Tier 1 规则 |
| `MultiTierPipeline` | `tiered/pipeline.py` | ✅ 通用级联框架 |
| `TieredActionResolver` | `tiered/action_resolver.py` | ✅ 共享分类内核 |
| `DomainAdapter` | `observation_compiler/*_adapter.py` | ✅ 多域适配器 |
| `IntentParser` | `tiered/intent_parser.py` | ✅ 规则+LLM |
| `CognitiveCompiler` | `tiered/cognitive_compiler.py` | ✅ 编译器 |
| `ContextCompiler` | `tiered/context_compiler.py` | ✅ 上下文编译 |
| `NegativeKB` | `tiered/negative_kb.py` | ✅ 负知识库 |
| `RuleEngine` | `tiered/rule_engine.py` | ✅ 规则引擎 |
| `SkillPool` | `skill_layer/skill_pool.py` | ✅ Candidate/Verified/Core 生命周期 |
| `DistillationEngine` | `skill_layer/distillation_engine.py` | ✅ 蒸馏引擎 |
| `EvaluationEngine` | `skill_layer/evaluation_engine.py` | ✅ 多维评估 |
| `ExternalAdapter` | `skill_layer/external_adapter.py` | ✅ 外部 Skill 导入 |
| `DocumentIngestionLayer` | — | ❌ 未实现（v4.1 目标） |
| `LSPExtractor` | `adapter/code/lsp_extractor.py` | ⚠️ stub |

---

> 本文档定义输入解析与技能层的完整设计。具体实现见代码 `core/agent/v4/tiered/` 和 `core/agent/v4/skill_layer/`。
