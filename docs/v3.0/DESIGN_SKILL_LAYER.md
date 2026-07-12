# DESIGN_SKILL_LAYER.md — 能力蒸馏与执行蓝图

> 版本: v1.0 | 日期: 2026-07-12
>
> Skill Layer 不是"结构化 Prompt"。它是从 Knowledge/Pattern/Constraint/Behavior
> 中蒸馏出来的可执行能力蓝图（Capability Blueprint）。
> 分为 External（外部导入）和 Internal（内部蒸馏）双轨，经过 Candidate Pool
> → 多维度评估 → Verified → Core 的生命周期。

---

## 目录

1. [定位：能力蓝图而非结构化 Prompt](#1-定位能力蓝图而非结构化-prompt)
2. [Layered Capability Blueprint](#2-layered-capability-blueprint)
3. [Skill Lifecycle：借鉴 Hypothesis 的共识模型](#3-skill-lifecycle)
4. [双轨：External + Internal Skill](#4-双轨external-internal-skill)
5. [蒸馏引擎：从存储到能力](#5-蒸馏引擎从存储到能力)
6. [Candidate Pool + Multi-Dimensional Evaluation](#6-candidate-pool-multi-dimensional-evaluation)
7. [Action Graph + Executor 映射](#7-action-graph-executor-映射)
8. [Schema 定义](#8-schema-定义)
9. [白盒溯源](#9-白盒溯源)
10. [集成面](#10-集成面)
11. [实现计划](#11-实现计划)

---

## 1. 定位：能力蓝图而非结构化 Prompt

### 1.1 Harness 的 Skill 是什么

Harness 风格的 Skill 本质是带结构的 Prompt：

```
Condition → Prompt Template → LLM
```

它依赖 LLM 执行全部工作。当 LLM 不准确时 Skill 失效，无法被系统独立验证。

### 1.2 v4 的 Capability Blueprint 是什么

```
Capability Blueprint
├── Goal          （为什么做——目标）
├── Constraints   （不能违反哪些——引用 Engineering Chain）
├── Strategy      （推荐策略——引用 Pattern + Decision）
├── Action Graph  （语义动作序列——独立于执行器）
├── Verification  （如何验证——引用 Constraint Engine）
└── Reflection    （执行后反馈——引用 Hypothesis Engine）
```

Goal/Constraint/Strategy 三层来自 Knowledge 蒸馏，
Action Graph 是抽象动作序列，
Verification + Reflection 形成验证与学习闭环。

**Skill 是离散能力，Capability Layer 是能力的演化网络。**

---

## 2. Layered Capability Blueprint

### 2.1 为什么 Procedure 不能是单一形式

| 如果 Procedure 是 | 问题 |
|:---|:---|
| 文本指令序列 | 太依赖 LLM，泛化能力弱 |
| 可执行代码 | 丢失泛化能力，与特定语言/工具绑定 |
| Constraint 集合 | 无法表达流程（先后顺序、条件分支） |

**Procedure 本身也应该是分层对象——和整个 v4 同构。**

### 2.2 四层结构

```
Capability Blueprint
├── Goal          回答：为什么做
│      例: "建立可运行的 Gateway"
│      (Blueprint 自身字段)
│
├── Constraints   回答：哪些不能违反
│      例: 必须有 Metrics, Health, Config
│      不可直接依赖 DB
│      (引用 Engineering Chain: references → Constraint_23, Constraint_45)
│
├── Strategy      回答：推荐怎么做
│      例: Plugin Pattern, Factory Pattern
│      (引用 Engineering Pattern + Decision)
│
└── Action Graph  回答：具体做什么
        抽象动作序列，独立于执行器
        例: Create Module → Register → Run Test → Update Config
        不写 mkdir src，写 Create Module
```

### 2.3 关键设计原则

- **上层只存 references，不重复存储**——Constraint 和 Strategy 的内容在 Engineering Chain 里已经存在，Blueprint 只保存引用
- **Action Graph 是抽象动作**——不绑定工具名。`Create Module` 而非 `mkdir src`
- **Executor 映射独立**——Action → tool/LLM/agent 绑定可在运行时替换

---

## 3. Skill Lifecycle

借鉴 Hypothesis Engine 的共识模型——Skill 不是"达到阈值即创建"，而是渐进生长。

```
Candidate Skill → Verified Skill → Core Skill
     ↑
  (可回退)
```

### 3.1 生命周期状态

| 状态 | 条件 | 说明 |
|:---|:---|:---|
| `candidate` | 蒸馏引擎检测到重复模式 | 初始候选，低置信度 |
| `verified` | 多维度评估通过 | 经过 Evaluation Engine 确认 |
| `core` | 连续 N 次成功应用 | 系统自动启用，无需用户确认 |
| `deprecated` | 长时间未使用或策略更新 | 标记废弃，保留溯源 |

### 3.2 升级条件（复用 BelifeState 模型）

```
SkillCandidate
  belief:
    support: 18          # 被蒸馏次数
    generality: 0.72     # 跨项目泛化程度
    benefit: 0.81        # 应用成功率
    conflict: 0.05       # 与其他 Skill 冲突次数
    stability: 0.93      # 连续未变更比例

candidate → verified:
    support >= 5 AND generality >= 0.60 AND benefit >= 0.70

verified → core:
    support >= 15 AND generality >= 0.80 AND stability >= 0.90
```

所有阈值纳入 ParameterRegistry 统一管理。

---

## 4. 双轨：External + Internal Skill

### 4.1 两类 Skill 的区别

| | External Skill | Internal Skill |
|:---|:---|:---|
| 来源 | GitHub, Docs, RAG, Harness, 用户导入 | Knowledge, Behavior, Engineering Graph, Hypothesis |
| 特点 | 可信但属于通用知识 | 只适用于当前用户/项目/团队 |
| 示例 | FastAPI 初始化, React 组件模板 | "本项目的所有 Middleware 必须有 Metrics" |
| 进入方式 | 外部导入 → Candidate Pool | 蒸馏引擎 → Candidate Pool |

### 4.2 融合——共享 Candidate Pool

```
External Skill (导入) ──┐
                         ├── Candidate Pool ──→ Evaluation ──→ Verified Skill
Internal Skill (蒸馏) ──┘
```

两条来源进入同一个 Candidate Pool，经过同一套 Evaluation Engine 评估。融合不是覆盖——External 和 Internal 可以在同一个 Blueprint 中共存，各自标注来源和权重。

---

## 5. 蒸馏引擎

### 5.1 从存储中识别重复模式

当前 v4 存储已积累足够的信号维度：

| 数据源 | 蒸馏信号 | 产出 |
|:---|:---|:---|
| Engineering Chain Constraint | 多个项目共享相同约束 → "Every Provider needs Metrics" | ConstraintSkill |
| Hypothesis consensus | "用户偏好 reorder 而非 delete" → 共识度 >0.85 | PreferenceSkill |
| Knowledge freeze 聚类 | 多个 Knowledge 共享相同对象/结构 | PatternSkill |
| Behavior 模式 | 重复的行为序列（例如拖拽后查看测试） | BehaviorSkill |

### 5.2 蒸馏算法

```python
class DistillationEngine:
    def scan(self) -> List[SkillCandidate]:
        candidates = []
        # 1. Constraint 聚类
        candidates += self._cluster_constraints()
        # 2. Knowledge freeze 聚类
        candidates += self._cluster_knowledge()
        # 3. Behavior 序列模式
        candidates += self._find_behavior_patterns()
        # 4. Hypothesis 共识
        candidates += self._consensus_hypotheses()
        return candidates
```

**不是"重复 5 次→Skill"——是累计多维信号。**

---

## 6. Candidate Pool + Multi-Dimensional Evaluation

### 6.1 Candidate Pool

```python
@dataclass
class SkillCandidate:
    candidate_id: str
    blueprint: CapabilityBlueprint
    belief: SkillBelief        # 复用 BeliefState 模型
    source: str                 # "external" | "internal"
    references: List[str]       # 引用的 Knowledge/Pattern/Constraint ID
    domain: str = ""
    created_at: float
```

### 6.2 SkillBelief

```python
@dataclass
class SkillBelief:
    support: int = 0            # 蒸馏次数
    generality: float = 0.5     # 跨项目泛化程度 (0-1)
    benefit: float = 0.5        # 应用成功率
    conflict: int = 0           # 冲突次数
    stability: float = 1.0      # 连续未变更比例
    coverage: float = 0.0       # 相关 Knowledge 覆盖率
    recency: float = 1.0        # 最近使用时机
```

### 6.3 Evaluation Engine

```python
class EvaluationEngine:
    def evaluate(self, candidate: SkillCandidate,
                 context: EvaluationContext) -> Tuple[str, float]:
        belief = candidate.belief
        score = (
            belief.generality * 0.30 +
            belief.benefit * 0.25 +
            belief.stability * 0.20 +
            belief.coverage * 0.15 +
            belief.recency * 0.10
        )
        if score > 0.80: return "verified", score
        if score > 0.55: return "candidate", score
        return "candidate", score  # stay in candidate pool
```

---

## 7. Action Graph + Executor 映射

### 7.1 Action Graph

不依赖具体工具。抽象语义动作：

```
Create Module → Register Module → Run Test → Update Config
```

### 7.2 Action Node

```python
@dataclass
class ActionNode:
    action_id: str
    action: str                       # "create_module" | "register" | "test" | ...
    input_refs: List[str]             # 引用的对象/文件
    output_refs: List[str]            # 产生的对象/文件
    preconditions: List[str]          # 前置条件
    postconditions: List[str]         # 后置条件
    depends_on: List[str]             # action_id of dependencies
```

### 7.3 Executor Mapping

```python
EXECUTOR_MAP: Dict[str, Dict[str, str]] = {
    "create_module": {"shell": "mkdir -p {name}", "codex": "create_module({name})", "agent": "agent.create_module"},
    "register": {"shell": "echo register", "codex": "register_module({name})", "agent": "agent.register"},
    ...
}
```

Skill 只定义 `create_module`。运行时根据当前 Executor 查找映射。**Skill 完全独立于执行器。**

---

## 8. Schema 定义

### 8.1 CapabilityBlueprint

```python
@dataclass
class CapabilityBlueprint:
    blueprint_id: str
    goal: str                         # "建立可运行的 Gateway"
    constraints: List[str]            # references → Constraint IDs (Engineering Chain)
    strategy_refs: List[str]          # references → Pattern/Decision IDs
    action_graph: List[ActionNode]    # 抽象动作序列
    verification: List[str]           # Constraint Engine 校验规则
    reflection_hooks: List[str]       # Evidence/Hypothesis 回调钩子
    domain: str = "engineering"
    version: int = 1
    created_at: float = field(default_factory=time.time)
```

### 8.2 Skill（Blueprint + Lifecycle）

```python
@dataclass
class Skill:
    skill_id: str
    blueprint: CapabilityBlueprint
    belief: SkillBelief
    status: str = "candidate"         # candidate | verified | core | deprecated
    source: str = "internal"          # "external" | "internal"
    references: List[str] = field(default_factory=list)  # 溯源: Knowledge/Pattern IDs
    merged_from: List[str] = field(default_factory=list)  # 合并来源
    domain: str = ""
    executor: str = "default"         # 执行器选择
    created_at: float = field(default_factory=time.time)
    verified_at: Optional[float] = None
```

### 8.3 Skill Pool

```python
class SkillPool:
    """Candidate + Verified + Core 的统一管理池"""
    def add_candidate(candidate: SkillCandidate) -> str
    def get(skill_id: str) -> Optional[Skill]
    def get_by_domain(domain: str) -> List[Skill]
    def get_ready(domain: str) -> List[Skill]  # status in (verified, core)
    def promote(skill_id: str) -> str           # candidate → verified → core
    def deprecate(skill_id: str) -> None
    def stats() -> dict
```

---

## 9. 白盒溯源

每个 Skill 标记精确来源：

```
Gateway Init Skill
  来源:
    Engineering Pattern   72%  (5 个项目共享)
    Behavior              15%  (用户 6 次手动使用)
    Knowledge              9%  (1 个 Freeze)
    External               4%  (从文档导入的模板)
```

展开后可以看到：

```
推荐理由:
  - Engineering Chain: 5 个 Gateway 项目都有 Metrics + Health (Constraint_23)
  - Hypothesis: "用户偏好中间件架构" 共识度 0.85
  - Behavior: 用户创建 Gateway 后总是先建 Provider
```

**Skill 第一次变成白盒——不仅知道推荐什么，还知道为什么推荐。**

---

## 10. 集成面

| 模块 | 关系 |
|:---|:---|
| Engineering Chain | Constraint/Pattern 被 Blueprint 引用 |
| Hypothesis Engine | BeliefState 模型复用，Reflection Hook |
| Knowledge | 冻结知识 → 蒸馏输入 |
| Behavior Chain | 行为模式 → 蒸馏输入 |
| ParameterRegistry | 所有评估阈值、蒸馏参数统一管理 |
| TierHeatBridge | 热 Skill（频繁被调用）→ 提升存储层级 |
| ContextCompiler | Blueprint 编译为 LLM 上下文 |
| External Import Adapter | Harness/OpenAPI/文档 → Candidate Pool |

---

## 11. 实现计划

| Phase | 内容 | 依赖 |
|:---|:---|:---|
| Phase 1 | CapabilityBlueprint + ActionGraph + Skill Schema | 无 |
| Phase 2 | SkillPool（Candidate/Verified/Core 生命周期） | Phase 1 |
| Phase 3 | SkillBelief + Evaluation Engine | Phase 1, Hypothesis Engine models |
| Phase 4 | DistillationEngine（聚类扫描） | Phase 1-3, Engineering Chain, Knowledge, Behavior |
| Phase 5 | Executor Mapping | Phase 1 |
| Phase 6 | External Import Adapter | Phase 1-2 |
| Phase 7 | ParameterRegistry 蒸馏/评估参数 | ParameterRegistry |

---

> Skill 不是 Prompt。它是从 Knowledge/Pattern/Constraint/Behavior 中
> 蒸馏出的可执行能力蓝图。
> 它白盒标注来源，独立于执行器，通过 Candidate Pool 渐进生长，
> 最终形成可组合、可演化、可解释的能力网络。
