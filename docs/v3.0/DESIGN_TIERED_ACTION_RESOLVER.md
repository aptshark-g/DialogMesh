# DESIGN_TIERED_ACTION_RESOLVER.md — 共享分级动作解析器

> 版本: v1.0 | 日期: 2026-07-12
>
> TieredActionResolver 不是第 N 个 tiered wrapper。它是所有"输入 → 候选类别"场景的共享分类内核。
> 每个认知域通过 DomainAdapter 接入，提供规则、嵌入索引、LLM 提示词即可。

---

## 目录

1. [定位：为什么是共享内核](#1-定位为什么是共享内核)
2. [三级递进谱系](#2-三级递进谱系)
3. [Domain Adapter 接口](#3-domain-adapter-接口)
4. [Schema 定义](#4-schema-定义)
5. [反馈闭环](#5-反馈闭环)
6. [消费者清单](#6-消费者清单)
7. [实现计划](#7-实现计划)

---

## 1. 定位：为什么是共享内核

### 1.1 问题的共性

回顾 v4 中所有"给定输入 → 输出候选类别"的场景：

| 模块 | 输入 | 输出候选 |
|:---|:---|:---|
| DialogueInterpreter | "帮我把 RateLimiter 放 Auth 前面" | reorder? add? configure? |
| EngineeringInterpreter | ui.drag(RateLimiter, Auth) | reorder_pipeline? optimize_perf? |
| BehaviorInterpreter | user clicked node42 × 3 | inspect? explore? modify? |
| IntentParser | 用户输入文本 | question? command? clarify? |
| NegativeKB | 触发文本/操作 | block? warn? soft_discourage? |
| Projector | Event kind | route_to_engineering? route_to_behavior? |

**全部都是同一种计算**：`f(domain_context, input) → ranked_candidates`。

### 1.2 不是第 N 个 wrapper

之前我们为每个模块建了独立的 tiered wrapper：

```
TieredIntentParser / TieredNegativeKB / TieredRuleEngine / ...
```

这些 wrapper 各自拥有自己的 rule→embedding→LLM 逻辑。但它们的核心结构完全相同——只是在不同的域数据集上做分类。

TieredActionResolver 不是又增加一个 wrapper。它是把每个 wrapper **内部的分类逻辑提取出来作为共享引擎**：

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

每个域只需要提供 **DomainAdapter**（规则 + 嵌入索引 + LLM 提示词）。分类的编排、升级、反馈闭环全部由共享引擎完成。

---

## 2. 三级递进谱系

```
Input (text / event / action)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Tier 0: Domain Rule Matching (~1ms, ~70%)           │
│  已知动词/模式 → action 直接映射                     │
│  中文: "添加" → "add", "删除" → "remove"            │
│  英文: "deploy" → "deploy", "restart" → "restart"   │
│  confidence < threshold → Tier 1                    │
├─────────────────────────────────────────────────────┤
│ Tier 1: Domain Embedding Semantic Match (~10ms, ~90%)│
│  embed(input) → nearest neighbor in Domain Index    │
│  cosine_sim > threshold → 匹配                      │
│  confidence < threshold → Tier 2                    │
├─────────────────────────────────────────────────────┤
│ Tier 2: Domain LLM Classification (~500ms, ~98%)    │
│  LLM + domain prompt → structured action output     │
│  ↓                                                   │
│  反馈回流: 新 action → 写回 Tier 0 规则表 +        │
│                        Tier 1 嵌入索引              │
└─────────────────────────────────────────────────────┘
```

### 2.1 Tier 0：域规则匹配

```python
# 每个域的规则表是 domain-specific 的
engineering_rules = {
    "添加": ["add"],
    "删除": ["remove", "uninstall"],
    "修改": ["modify", "update"],
    "重排": ["reorder"],
    "连接": ["connect"],
    "断开": ["disconnect"],
    "查看": ["query_status", "inspect"],
    "回滚": ["rollback"],
}

behavior_rules = {
    "拖拽": ["drag"],
    "点击": ["click"],
    "双击": ["open", "navigate"],
    "选中": ["select"],
    "取消选中": ["deselect"],
    "悬停": ["hover"],
}
```

规则匹配逻辑：文本子串匹配 → 精确映射。带阈值：不匹配任何规则 → 升级到 Tier 1。

### 2.2 Tier 1：域嵌入语义匹配

对每条候选 action 维护一个嵌入式向量。输入文本的向量与各 action 向量做余弦相似度。

```python
# 嵌入索引结构
DomainActionIndex:
    "reorder": [0.12, -0.34, 0.67, ...]
    "add": [0.23, 0.45, -0.11, ...]
    "configure": [-0.08, 0.72, 0.31, ...]
    ...
```

冷启动：初始嵌入向量来自规则表中高置信度 action 的定义。随着 LLM 反馈回流，新 action 的动态嵌入向量被补充到索引。

优势：对同义表达（"加监控" ≈ "添加监控" ≈ "新增 monitoring"）有自然的泛化能力。

### 2.3 Tier 2：域 LLM 分类

```python
domain_prompt = """
You are classifying user actions in the {domain} domain.

Available action types: {action_list}

Input: "{text}"

Output format: JSON with "action" and "confidence".
If the input does not match any existing action, suggest a new action label.
"""
```

LLM 输出格式：
```json
{
  "action": "add_monitoring",
  "confidence": 0.92,
  "is_new_action": false
}
```

标记为 `is_new_action` 的输出会触发反馈回流，写入 Tier 0 和 Tier 1。

---

## 3. Domain Adapter 接口

每个域提供一个 DomainAdapter，它是最小的接入契约：

```python
@dataclass
class DomainAdapter:
    domain: str                         # "engineering" | "behavior" | "dialogue" | ...
    rules: dict[str, list[str]]         # 文本模式 → action 列表
    action_index: EmbeddingIndex | None # 域动作嵌入向量索引（可选，Tier 1）
    llm_prompt_template: str            # Tier 2 LLM 提示词模板
    default_action: str = "unknown"     # 无法解析时的默认动作

    def on_new_action(self, text: str, action: str) -> None:
        """反馈回调：LLM 发现的新 action → 更新 rules + index"""
        # 提取关键词模式 → 加入 rules
        # 计算 action 嵌入向量 → 加入 index
```

### 3.1 EmbeddingIndex

```python
class EmbeddingIndex:
    def add(self, action: str, embedding: list[float]) -> None
    def nearest(self, query_embedding, threshold: float = 0.75) -> str | None
    def get_embedding(self, action: str) -> list[float] | None
    def size(self) -> int
```

支持从规则表初始化（冷启动）和从 LLM 反馈扩展（热运行）。

### 3.2 内置嵌入策略

- **规则表初始化**：取 action 名称的 BOW 向量，或使用预训练的小 embedding
- **LLM 扩展**：LLM 生成 action 名称 → 用领域文本批量编码 → 加入索引
- **TierHeatBridge 联动**：高频命中 → 提升该 action 在索引中的优先级

---

## 4. Schema 定义

### 4.1 ActionCandidate

```python
@dataclass
class ActionCandidate:
    action: str                     # "reorder" | "add" | "configure" | ...
    confidence: float               # 引擎分配的初始置信度
    source: str                     # "rule" | "embedding" | "llm"
    domain: str                     # 所在域
    is_new: bool = False            # 是否是 LLM 创建的新动作
    embedding: list[float] | None = None  # action 的嵌入向量
    evidence_refs: list[str] = field(default_factory=list)  # 证据引用
```

### 4.2 TieredActionResolver

```python
class TieredActionResolver:
    def __init__(self, registry=None):
        self._adapters: dict[str, DomainAdapter] = {}
        self._pipeline = MultiTierPipeline(...)

    def register_domain(self, adapter: DomainAdapter) -> None

    def resolve(self, domain: str, input_text: str) -> list[ActionCandidate]

    def add_action(self, domain: str, action: str, text_patterns: list[str],
                   embedding: list[float] | None = None) -> None

    def stats(self) -> dict
```

核心接口 `resolve(domain, input_text)` → 返回候选动作列表。每个候选附 `confidence`、`source`、`evidence_refs`。

---

## 5. 反馈闭环

```
Tier 2 (LLM) 识别出新的 action
    │
    ├──→ DomainAdapter.on_new_action(text_pattern, new_action)
    │       ├── 提取文本关键词 → 写入 rules 表 (Tier 0)
    │       └── 计算嵌入向量 → 写入 action_index (Tier 1)
    │
    └──→ TierHeatBridge
            ├── new_action 标记为 candidate（冷）
            ├── 随着命中次数增加 → 渐进升温
            └── high confidence × high frequency → promotion
```

**闭环效果**：

- **冷启动**：Tier 0 不匹配 → Tier 1 也不匹配 → Tier 2 LLM 生成新 action → 写入 Tier 0+1
- **预热**：同类输入命中 Tier 1 的嵌入匹配 → 不需要 LLM
- **热运行**：高频输入命中 Tier 0 的精确规则 → 亚毫秒级

---

## 6. 消费者清单

| 消费者 | 域 | 接入方式 | 优先级 |
|:---|:---|:---|:---|
| DialogueInterpreter | dialogue | DomainAdapter(dialogue_rules, dialogue_index, dialogue_prompt) | Phase 1 |
| IntentParser | intent | 替换现有 TieredIntentParser 的 rule+LLM 路径 | Phase 2 |
| EngineeringInterpreter | engineering | DomainAdapter(eng_rules, eng_index, eng_prompt) | Phase 2 |
| BehaviorInterpreter | behavior | DomainAdapter(beh_rules, beh_index, beh_prompt) | Phase 2 |
| NegativeKB | negative | DomainAdapter(neg_rules, neg_index, neg_prompt) | Phase 3 |
| Projector | routing | 替换现有硬编码 ROUTING_TABLE | Phase 3 |

---

## 7. 实现计划

| Phase | 内容 | 依赖 |
|:---|:---|:---|
| Phase 1 | TieredActionResolver 核心引擎 + DomainAdapter + EmbeddingIndex | MultiTierPipeline, ParameterRegistry |
| Phase 2 | 接入 DialogueInterpreter（首个消费者） | Phase 1, TieredParser |
| Phase 3 | 接入 IntentParser / EngineeringInterpreter / BehaviorInterpreter | Phase 1, 各域知识库 |
| Phase 4 | 反馈闭环 + TierHeatBridge 联动 | Phase 2-3, TierHeatBridge |
| Phase 5 | EmbeddingIndex 初始种子数据构建（各域基础规则嵌入式向量） | Phase 1 |

---

> TieredActionResolver 不是又一个 tiered wrapper。
> 它是 v4 中所有"输入 → 候选类别"的统一分类引擎。
> 每个域只需接入 DomainAdapter。
> 反馈闭环使系统从冷启动到热运行自然演化。
