# DialogMesh v3.1：行为推演链 + 双层摘要树 + 在线训练闭环 设计文档

> **文档状态**: 设计草案 (Design Draft)
> **版本**: v3.1
> **日期**: 2026-07-04
> **依赖**: [系统概念设计 v2.0](DESIGN_FULL_CONCEPT.md) + [多层 LLM 认知架构 v3.0](DESIGN_MULTILAYER_LLM_COGNITIVE.md)
> **核心命题**: 对话树不止是主题切分——它是行为因果链的载体、预测引擎的训练数据源、摘要系统的组织骨架。

---

## 目录

- [1. 背景：v3.0 遗留的四个缺口](#1-背景v30-遗留的四个缺口)
- [2. 设计目标](#2-设计目标)
- [2.5 前置改造：约束补全编译器](#25-前置改造约束补全编译器)
- [3. 核心改造一：对话树升级为"行为推演树"](#3-核心改造一对话树升级为行为推演树)
- [4. 核心改造二：双层摘要系统重构](#4-核心改造二双层摘要系统重构)
- [5. 核心改造三：在线训练闭环（预测→验证→修正→回流）](#5-核心改造三在线训练闭环预测验证修正回流)
- [6. 核心改造四：融合器升级为结构化合并](#6-核心改造四融合器升级为结构化合并)
- [7. 数据流与生命周期](#7-数据流与生命周期)
- [8. 工程实现计划](#8-工程实现计划)
- [9. 设计决策记录](#9-设计决策记录)
- [10. 附录：与现有设计的对照](#10-附录与现有设计的对照)
- [11. v3.1.1 补充设计：泛化能力与实现细节](#11-v311-补充设计泛化能力与实现细节)
- [12. v3.2：因果基地——从概率关联到结构因果](#12-v32因果基地从概率关联到结构因果)

---

## 1. 背景：v3.0 遗留的四个缺口

### 1.1 缺口一览

| # | 缺口 | 影响 | 根本原因 |
|---|------|------|---------|
| G-01 | **Topic Tree 只有主题切分，没有行为推演链** | 无法预测用户下一步行为，无法利用行为因果缩小搜索空间 | 节点只记录"话题是什么"，不记录"用户做了什么操作以及为什么" |
| G-02 | **摘要系统与双树架构脱节** | v2.0的一级/二级摘要只做压缩存储，没有元信息（行为链、因果链、关联链），与v3.0的Cognitive Tree无关联 | 第8章摘要系统写于v2.0时代，v3.0引入双树后未重新对齐 |
| G-03 | **预测→验证→修正的闭环缺失** | 系统每次从零推理，不学习用户的纠正反馈，无法持续改善预测准确率 | Cognitive Tree记录了PERCEPTION/REASONING/DECISION节点，但没有"预测了什么→实际发生了什么→权重如何更新"的回路 |
| G-04 | **融合器假设A和B同维度可加权** | 算法结果和LLM结果往往不在同一维度（算法提取了实体，LLM理解了隐含意图），简单加权平均丢失信息 | 融合器设计偏数学化，缺少"结构化合并"的概念 |

### 1.2 解决思路

v3.1 不做重构，做**增量**：

- **不改动**：PCR、Intent Parser、Layer 2 (Topic Tree/Cognitive Tree)、三层LLM的层级结构
- **升级**：Cognitive Compiler → 约束补全编译器（§2.5）
- **改动/新增**：
  1. Topic Tree 节点增加行为链字段
  2. 新增 BehaviorGraph 组件（在 `topic_tree/` 旁）
  3. 重构第8章记忆系统的摘要部分
  4. 在 Meta-Cognitive 层增加训练信号生成
  5. 融合器增加结构化合并分支

---

## 2. 设计目标

| ID | 目标 | 优先级 | 验收标准 |
|----|------|--------|---------|
| OB-01 | 对话树节点内建行为链、因果链、关联链 | P0 | 每个 TopicTreeNode 包含 behavior_chain、causal_chain、association_chain 字段 |
| OB-02 | 一级摘要信息丢失 ≤20%，包含元信息 | P0 | 一级摘要为 LLM 生成的结构化 JSON，包含核心意思 + 三个链 + 原始对话索引 + 二级摘要索引 |
| OB-03 | 二级摘要展开元信息，与原始扁平对话双向索引 | P0 | 二级摘要包含完整行为推演图 + 正向索引（摘要→轮次）+ 反向索引（轮次→摘要） |
| OB-04 | 行为预测引擎接入双轨仲裁 | P0 | BehaviorPredictor 输出作为融合器的第三个输入源，与算法/LLM结果共同参与融合 |
| OB-05 | 纠错即训练：1轮内更新行为权重 | P1 | 用户纠正行为后，BehaviorGraph 的边权重在 1 轮内完成更新 |
| OB-06 | 不破坏现有测试 | P1 | 现有 327 个测试全部通过，新增行为图专用测试 |
| OB-07 | 认知编译器具备约束补全能力 | P0 | 输入"这个饮料喝了很呛" → 输出结构化表示 {agent:人, patient:汽水, effect:呛, stability:0.78} |

---

## 2.5 前置改造：约束补全编译器

> **理论基础**：因果不是世界固有的属性，而是认知主体在约束空间中做出的投射。当一组约束的稳定性超过观测者的参考框架时，这组约束定义的关系就是"足够好的因果"。认知编译器的核心任务不是寻找"真正的因果"，而是在当前输入激活的约束空间中找到最稳定的解释。

### 2.5.1 LLM 为什么不拆语法树

LLM 看起来"理解"自然语言，但它不做显式的句法解析——它做的是 token-by-token 的概率生成。

```
输入："这个饮料喝了很呛"

LLM 实际做的：
  token序列 → 注意力分布 → 下一个token概率 → 继续生成
  "这个" → 指示代词 → 怎么用？训练数据中类似模式匹配
  "饮料" → 名词 → "喝"的受事 → 概率激活
  "很呛" → 程度修饰 → 碳酸饮料的关联 → 概率激活

LLM 没有做的：
  ✗ 构造语法树 {predicate: "喝", agent: ???, patient: "饮料"}
  ✗ 检测施事缺失并标记为"需要补全"
  ✗ 显式激活"喝"的语义框架约束
  ✗ 消解"呛"的多种可能原因并返回置信度
```

**结果**：LLM 在简单场景下正确率 70-80%。但上下文复杂时（前面提到自制酵素饮料，呛是因为发酵气体），LLM 可能被干扰。因为它没有显式的约束消解步骤——它的"推理"是被注意力权重隐式完成的，一旦权重被强信号（如"酵素"）抢占，弱约束（"饮料+呛→汽水"）就被压制了。

### 2.5.2 二合一架构：LLM 粗切割 + 规则选择性深挖 + 流式验证

#### 设计动机

纯规则方案的瓶颈不是句法解析本身（2ms），而是**约束消解的组合爆炸**：

```
"这个饮料喝了很呛"经过约束激活后：
  "喝"的agent候选：{人, 动物, 机器, ...} → 5个
  "呛"的原因候选：{碳酸, 辛辣, 气管误入, 过敏, ...} → 10个
  "饮料"的类型候选：{汽水, 果汁, 茶, 咖啡, 酒, 酵素, ...} → 20个
  交叉验证组合：5 × 10 × 20 = 1000 种 → 每种 0.1ms → 100ms
```

复杂句的约束空间更大，直接全量消解不可行。

纯 LLM 方案的问题相反——它不做约束消解，做 token-by-token 生成，遇到强信号压制弱约束时会出错。

**二合一的核心思路**：LLM 不去做约束消解（它不擅长），规则引擎不去做全量约束消解（会爆炸）。让 LLM 做它擅长的（粗粒度语义角色标注 + 置信度评估），让规则引擎做它擅长的（只在 LLM 不确定的维度上做确定性深挖）。

#### 三步流水线

```python
class HybridCompiler:
    """
    二合一编译器：LLM 粗切割 → 规则选择性深挖 → 流式验证。

    核心理念：
    - LLM 不画语法树，只做"伪拆解"——语块的语义角色标注
    - 规则引擎不做全量消解，只对 LLM 不确定的维度深挖
    - 流式校验在 LLM 输出过程中并行检查，硬冲突即时拦截
    """

    def compile(self, sentence: str, context: ParseContext) -> CompiledSentence:
        # ====== 第一步：LLM 伪拆解（粗切割，50-150ms）======
        # 不是语法树，不是完整 L1Summary JSON
        # 只是语块级别的语义角色标注 + 每个维度的置信度
        
        llm_result = self._llm_pseudo_parse(sentence, context)
        # 输入："这个饮料喝了很呛"
        # 输出（轻量 JSON，~100 tokens 输出）:
        # {
        #   "who": {"value": "人", "confidence": 0.95},
        #   "did_what": {"value": "喝", "confidence": 0.98},
        #   "to_what": {"value": "饮料", "confidence": 0.90},
        #   "result": {"value": "呛", "confidence": 0.95},
        #   "why_result": {"value": "碳酸刺激", "confidence": 0.60}
        # }
        
        # ====== 第二步：规则选择性深挖（<3ms）======
        # 只对 LL M 不确定的维度做功
        
        weak_dims = [d for d in llm_result if d.confidence < 0.75]
        # weak_dims = ["why_result"]  ← 只有这个 LLM 不确定
        
        for dim in weak_dims:
            # 约束空间从 1000 种组合缩小到只针对这一个维度
            # frame:"呛" → {碳酸, 辛辣, 气管误入, ...}
            # frame:"饮料" → 排除辛辣
            # context: 没有"辣"、"热"关键词 → 排除气管刺激
            # → 约束基数: 1×1×1×3 = 3，而非 1000
            resolved = self._deep_resolve_dimension(dim, constraints)
            llm_result[dim] = resolved  # 用规则结果覆盖 LLM 的模糊结果
        
        # ====== 第三步：稳定性评分 ======
        stability = self._assess_stability(llm_result)
        # 高置信度维度（LLM确定的） → stability 来自 LLM confidence
        # 低置信度维度（规则深挖的） → stability 来自约束消解的确定性
        
        return CompiledSentence(llm_result, stability)
```

#### 流式验证

不等 LLM 完整输出再检查——LLM 流式输出的同时规则引擎并行校验：

```
LLM 流式输出                                规则引擎并行检查
───────────                                ────────────────
{"who": "人",        ─────────────────→    frame:"喝"→agent=人 ✓
                                           confidence 0.95 → 放行
                                           如果输出"汽车" → 即时标记 + 中断

"did_what": "喝",    ─────────────────→    动词+受事匹配 ✓

"why_result": "碳酸刺激" →               frame:"呛"+frame:"饮料"
                                           → 碳酸在候选列表 ✓
                                           → 放行
                                           如果输出"辣椒" → 
                                           frame:"饮料"排除了辛辣
                                           → 硬冲突 → 标记+规则重算
```

**硬冲突处理**：
- 检测到硬冲突（LLM 输出违反已知的语义框架约束）→ 不中断 LLM 流
- 标记该维度 → LLM 输出完成后用规则结果覆盖
- 不重跑完整 LLM 调用（省 token）

#### Token 消耗分析

```
纯 LLM 方案（之前的 L1Summary 生成）:
  LLM 调用: 1次/轮
  Prompt: ~500 tokens（含行为链上下文、认知树引用）
  Output: ~200 tokens（完整结构化JSON）
  合计: ~700 tokens/轮

二合一方案:
  LLM 调用: 1次/轮
  Prompt: ~350 tokens（只需上下文，不需要行为链/认知树引用）
  Output: ~100 tokens（轻量语义角色标注JSON）
  合计: ~450 tokens/轮
  节省: ~35% token消耗
```

LLM 的 prompt 明确指示"不需要推理原因，只需要结构化回显输入的内容"，思维链开销也被省掉。

#### 方案对比

| 维度 | 纯语法树全量消解 | 纯 LLM | 二合一 |
|------|----------------|--------|--------|
| 正确率 | 高 | 中（70-80%） | 高（LLM出错被规则拦截） |
| 延迟 | 不可控（组合爆炸） | 50-200ms | 50-150ms |
| Token 消耗 | 0 | ~700/轮 | ~450/轮 |
| 幻视风险 | 零 | 中 | 低（硬冲突流式拦截） |
| 覆盖范围 | 窄（需有规则） | 宽 | 宽（LLM全覆盖，规则补盲区） |
| 可调试 | 高 | 低 | 高（每维度来源可追溯） |

### 2.5.3 之前的四步流水线（保留用于认知负荷低的场景）

**保留**纯规则四步流水线作为**降级路径**——当 LLM 不可用或 budget 已耗尽时使用：

```python
class ConstraintCompletingCompiler:
    """
    约束补全编译器——不靠概率猜，靠约束推。

    输入：自然语言句子
    输出：结构化约束图 + 稳定性评分

    设计原则：
    1. 句法分解是确定性的（不依赖LLM）
    2. 约束激活是基于规则的（语义框架 + 常识规则库）
    3. 约束消解是形式化的（交叉验证 + 优先级排序）
    4. LLM 只在约束空间无法确定时兜底
    """

    def compile(self, sentence: str, context: ParseContext) -> CompiledSentence:
        # Step 1: 语法分解（确定性，<1ms）
        tree = self._syntax_decompose(sentence)
        # "这个饮料喝了很呛" →
        #   {dem: "这个", subj: "饮料", pred: "喝", complement: "很呛"}
        #   检测：施事缺失（谁喝了？）

        # Step 2: 引头文件——激活约束（规则+框架，<2ms）
        constraints = self._activate_constraints(tree, context)
        # frame:"喝" → {agent_default: 人, 必要条件: 液体}
        # frame:"呛" → {原因: [碳酸刺激, 辛辣, 气管误入液体]}
        # frame:"饮料" → {排除: [辛辣]}
        # context: 前文是否提到喝饮料的人？

        # Step 3: 约束消解（交叉验证，<5ms）
        resolved = self._resolve_constraints(constraints)
        # agent: {候选:[人(0.95), 动物(0.04), 未知(0.01)]} → 选定: 人
        # patient: 饮料(已明确)
        # 隐式属性: 碳酸饮料(0.82) ← "饮料+呛" 交叉约束

        # Step 4: 稳定性评估
        stability = self._assess_stability(resolved)
        # agent=人: stability=0.95（"喝"的语义框架强约束）
        # patient=汽水: stability=0.82（交叉约束消解，信息有限）
        # overall: 0.78

        return CompiledSentence(tree, resolved, stability)
```

### 2.5.4 为什么这能大幅减少幻视

| 幻视来源 | LLM 为什么触发 | 约束编译器为什么避免 |
|---------|--------------|-------------------|
| 强信号压制弱约束 | "酵素"抢走注意力 → 忽略"呛→碳酸" | 约束不是注意力——所有激活的约束平等参与消解 |
| 过度自信 | 总是输出最高概率token，不说"不确定" | stability < 0.6 → 显式标记为"不确定"，交给上层 |
| 因果混淆 | 相关即因果（"呛"常和"辣"共现 → 推断是辣的） | 约束交叉验证："饮料"+frame排除辛辣 → 不可能是辣的 |
| 遗漏隐式前提 | 不做施事补全，直接用默认值 | 语法分解显式检测缺口 → LLM伪拆解标注维度+confidence |

### 2.5.5 约束层级（从强到弱）

```
第1层：语法约束（确定性 100%）
  → 依存句法、词性标注、指代消解
  → 来源：规则引擎
  → 稳定性: 1.0

第2层：语义框架约束（确定性 90-95%）
  → FrameNet/VerbNet 的论元结构和默认填充
  → 来源：预置框架库 + 规则映射
  → 稳定性: 0.90-0.95
  → 示例："喝"的agent默认是人；"呛"的原因集合

第3层：物理/逻辑约束（确定性 80-95%）
  → 键合图的功率守恒、Petri网的可达性
  → 来源：因果基地（v3.2）
  → 稳定性: 0.80-0.95

第4层：领域常识约束（确定性 60-85%）
  → "饮料+呛→汽水"、"洗车需要车到店"
  → 来源：规则库 + LLM兜底
  → 稳定性: 0.60-0.85

第5层：开放语义关联（确定性 <60%）
  → LLM 语义推理
  → 来源：LLM
  → 稳定性: 0.30-0.60
```

**消解策略**：
- 高层约束可以直接裁定低层（语法约束说"喝"必须有 agent → 不可跳过）
- 低层约束不能否定高层但可以补充（LLM 说"这个饮料可能是酵素" → 作为候选，但"呛"的约束说碳酸概率更高 → 保留两者，按稳定性排序）
- `overall_stability < 0.6` → 编译器输出"不确定"，交由上层（PCR 或用户澄清）

### 2.5.6 与因果基地（§12）的关系

约束补全编译器是**在线**的约束激活层——每轮对话实时运行，<10ms。因果基地是**离线**的约束发现层——通过键合图/Petri网/系统动力学发现深层因果骨架。

```
在线（<10ms/轮）:                     离线（后台异步）:

约束补全编译器                         因果基地
├─ 语法分解                            ├─ 键合图元解析
├─ 语义框架激活                        ├─ Petri网分析
├─ 约束消解                            ├─ 系统动力学识别
├─ 常识规则补全                        ├─ CSM跨域类比
└─ 稳定性评分                          └─ 元角色骨架生成
        │                                    │
        │  第4层: 常识约束                    │  第3层: 物理/逻辑约束
        │  靠规则库+LLM兜底                   │  靠形式化引擎
        │                                    │
        └──────────── 互补 ──────────────────┘

因果基地离线产出 → 更新编译器的第3层约束规则库
编译器在线使用 → 不需要知道键合图怎么算的，只需要读 constraints.yaml
```

### 2.5.7 与现有 Cognitive Compiler（v3.0）的升级关系

| 能力 | v3.0 Cognitive Compiler | v3.2 约束补全编译器 |
|------|------------------------|-------------------|
| 语法分解 | ✅ 基础分词 | ✅ 完整依存句法树 |
| 隐式实体补全 | ✅ 代词消解 + 实体缓存 | ✅ + 语义框架驱动的施事/受事补全 |
| 粘合度计算 | ✅ 关键词+实体重叠 | ✅ + 约束一致性检查 |
| 约束激活 | ❌ 无 | ✅ 五层约束系统 |
| 约束消解 | ❌ 无 | ✅ 交叉验证 + 优先级排序 |
| 稳定性评分 | ❌ 无 | ✅ 每个补充项的可信度 |
| LLM 兜底 | ✅ 全 LLM 或全规则 | ✅ 约束空间内规则，约束空间外 LLM |
| **新增核心能力** | | **从"补全缺失实体"升级为"发现并消解隐性约束冲突"** |

---

## 3. 核心改造一：对话树升级为"行为推演树"

### 3.1 当前 Topic TreeNode 的数据模型（v3.0）

```python
# v3.0 现状
TopicTreeNode:
    node_id: str
    content: str              # 主题描述
    importance: float         # EMA 更新
    children: List[TopicTreeNode]
    parent: Optional[TopicTreeNode]
    cog_refs: List[str]       # 引用的 Cognitive Tree 节点ID
    created_at: float
    last_activated: float
```

**缺失**：没有任何字段记录"用户在这个话题下执行了什么操作序列"，也没有字段记录"操作 A 和操作 B 有什么因果关系"。

### 3.2 v3.1 升级后的 TopicTreeNode

```python
@dataclass
class TopicTreeNode_v3_1:
    # === 保留 v3.0 的所有字段 ===
    node_id: str
    content: str
    importance: float
    children: List['TopicTreeNode_v3_1']
    parent: Optional['TopicTreeNode_v3_1']
    cog_refs: List[str]
    created_at: float
    last_activated: float

    # === v3.1 新增：行为推演链 ===
    # 注意：behavior_chain 存储行为序列的结构（节点+拓扑），
    # 边的因果权重（causal_weight）存储在 BehaviorGraph 中，
    # 通过 edge_id 引用。这样 TopicTreeNode 是"行为发生了什么"的索引，
    # BehaviorGraph 是"行为权重如何变化"的引擎，避免数据重复。
    behavior_chain: BehaviorChain      # 该话题下用户的行为序列（节点+拓扑）
    causal_chain: CausalChain          # 行为间的因果关系
    association_chain: AssociationChain # 跨主题的关联引用

    # === v3.1 新增：摘要索引 ===
    summary_level_1: Optional[str]     # 一级摘要ID（当该节点被摘要时）
    summary_level_2: Optional[str]     # 二级摘要ID（多个节点合并时）
```

### 3.3 三种链的形式化定义

#### 3.3.1 行为链（Behavior Chain）

行为链是**时序因果链**——记录了用户在这个话题下执行了什么操作、操作的顺序、以及操作间的因果概率。

```
行为链 = 有序行为节点序列 + 有向边(带因果权重)

行为链节点 (BehaviorStep):
  ├─ step_id: 全局唯一标识
  ├─ turn_id: 对应的原始对话轮次ID
  ├─ action_type: 行为类型（TOOL_EXEC / CODE_RUN / LOG_CHECK / CONFIG_MODIFY / ...）
  ├─ action_summary: 行为的自然语言摘要（≤50字）
  ├─ entities: 涉及的实体列表（工具名、文件名、参数值等）
  ├─ result: 执行结果 (SUCCESS / FAILURE / PARTIAL / UNKNOWN)
  └─ timestamp: 时间戳

行为链边 (BehaviorEdge):
  ├─ from_step: 前序行为
  ├─ to_step: 后续行为
  ├─ causal_weight: 因果概率 P(后续|前序) [0, 1]
  ├─ sample_count: 历史中这条边的出现次数
  ├─ correction_count: 这条边被用户纠正的次数
  ├─ llm_predicted: LLM是否预测到了这条边
  └─ last_updated: 上次更新权重的时间
```

**示例**：

```
调试程序（TopicTreeNode）
  │
  ▼
[运行程序] ──causal=0.73──→ [查看日志] ──causal=0.89──→ [定位报错行]
     │                          │
     │                          └──causal=0.11──→ [修改配置]  ← 低频路径
     │
     └──causal=0.15──→ [反汇编分析]  ← 罕见路径，通常跳过
```

#### 3.3.2 因果链（Causal Chain）

因果链回答 **"为什么"**——不只是一个行为后面跟着另一个行为，而是前一个行为**导致了**后一个行为的发生。

```
因果链 = 因果事件列表

因果事件 (CausalEvent):
  ├─ cause: 触发原因（可以是另一个行为、一个错误、用户的一句话）
  ├─ effect: 产生的后果（行为、状态变化、用户的情绪变化）
  ├─ causal_type: 因果类型
  │   ├─ ERROR_TRIGGERED: 错误触发了修复行为
  │   ├─ USER_CORRECTION: 用户纠正触发了方向转变
  │   ├─ RESULT_CHAINED: 上一个结果作为下一个的输入
  │   ├─ EXPLORATION: 用户主动探索新方向
  │   └─ EXTERNAL: 外部事件触发（如定时任务结果）
  └─ confidence: 因果置信度 [0, 1]
```

**示例**：

```
因果链:
  [运行程序](cause) → [日志报错：Segmentation Fault](effect) ERROR_TRIGGERED
  [日志报错](cause) → [查看日志详细堆栈](effect) RESULT_CHAINED
  [查看日志](cause) → [LLM预测：修复代码](wrong) → [用户纠正：分析日志](correct) USER_CORRECTION
```

#### 3.3.3 关联链（Association Chain）

关联链回答 **"和什么相关"**——这个行为/话题引用了其他话题里的哪些实体、决策、结果。

```
关联链 = 跨节点引用列表

关联引用 (AssociationRef):
  ├─ source: 当前节点中的哪个 step/turn
  ├─ target: 引用的目标（可以是另一个 TopicTreeNode、一个 CognitiveTreeNode、一个实体）
  ├─ ref_type: 引用类型
  │   ├─ ENTITY: 同一个实体（工具名、文件名等）
  │   ├─ DECISION: 引用了其他话题中的一个决策
  │   ├─ RESULT: 引用了其他话题中的一个执行结果
  │   └─ SIMILAR: 语义相似但不是同一个话题
  └─ strength: 关联强度 [0, 1]
```

**示例**：

```
关联链:
  话题"调试程序"的 [查看日志] step
    ←ENTITY→ 话题"日志分析" (同一个日志文件)
    ←RESULT→ 话题"代码审查" (审查范围基于此日志异常)
    ←SIMILAR→ 上次会话的"排查 crash" (相似的调试模式)
```

### 3.4 三链的更新时机

| 触发条件 | 更新的链 | 更新内容 |
|---------|---------|---------|
| 每轮对话结束 | 行为链 | 追加新的 BehaviorStep + 更新/创建 BehaviorEdge |
| 用户明确纠正系统预测 | 行为链 + 因果链 | 下调旧边权重 + 创建 USER_CORRECTION 因果事件 + 新增正确边 |
| Meta-Cognitive 层检测到跨主题引用 | 关联链 | 创建 AssociationRef |
| Reflective 层跨会话复盘 | 因果链 + 关联链 | 补充/修正因果推断 + 发现长期关联模式 |
| 用户说"回到刚才的话题" | 三链都读 | 回溯行为链找到最近断点 + 因果链理解为什么切换 + 关联链补充上下文 |

---

## 4. 核心改造二：双层摘要系统重构

### 4.1 当前摘要系统的问题（v2.0 第8章）

```
现有设计:
  一级摘要 = 规则模板: "[Turn N] {category} | entities: {e1,e2} | result: {status}"
    → 信息丢失约 60-70%
    → 没有任何元信息（行为链/因果链/关联链）

  二级摘要 = LLM压缩 5轮 → 50-100字自然语言
    → 信息丢失约 40-50%
    → 与一级摘要隔离（是"更高层的有损压缩"而非"展开+聚合"）

  与双树无关联:
    → 摘要不知道 Cognitive Tree 中对应的推理节点
    → 摘要不参与行为预测
```

### 4.2 v3.1 的双层摘要体系

核心理念改变：

> **一级摘要不是"压缩"，而是"结构化快照"——以最小信息丢失（≤20%）记录每轮对话的完整认知剖面。**
> **二级摘要不是"再次压缩"，而是"展开+聚合"——将同一个主题下的一级摘要元信息展开为可检索的完整行为推演图。**

```
Level 0: 原始对话轮次 (Turn)
  │
  ▼
Level 1: 一级摘要 (Per-Turn/Per-N-Turns Structured Snapshot)
  ├─ 核心语义（LLM生成的自然语言，≤100字）
  ├─ 元信息结构体 (MetaInfo)
  │   ├─ 行为链快照: [prev_action → current_action → predicted_next]
  │   ├─ 因果链快照: [cause → effect, causal_type]
  │   ├─ 关联链快照: [refs_to_other_topics/entities]
  │   ├─ 对话树定位: {topic_node_id, position_in_chain}
  │   └─ 认知树引用: [{cog_node_id, cog_type}]
  ├─ 正向索引: → 原始轮次ID列表
  └─ 二级摘要索引: → 所属二级摘要ID
  │
  ▼
Level 2: 二级摘要 (Topic-Level Structural Expansion)
  ├─ 该主题的完整行为推演图（DAG）
  ├─ 所有一级摘要的元信息展开（非压缩，是结构化的重新组织）
  ├─ 关键决策点 + 分歧点 + 未解决问题
  ├─ 正向索引: → 所有相关一级摘要ID
  └─ 反向索引: ← 所有原始轮次ID（保留完整追溯链路）
```

### 4.3 一级摘要的严格数据模型

```python
@dataclass
class Level1Summary:
    """一级摘要——结构化快照，信息丢失 ≤20%"""

    summary_id: str                    # UUID
    topic_node_id: str                 # 所属 TopicTreeNode

    # ── 核心语义 ──
    core_semantics: str               # LLM生成的自然语言摘要（≤100字）
    intent_category: str              # 意图类别
    intent_confidence: float          # 意图置信度

    # ── 元信息 ──
    meta_info: MetaInfo

    # ── 双树交叉引用 ──
    topic_tree_refs: List[str]        # Topic Tree 节点ID列表
    cognitive_tree_refs: List[CogRef] # Cognitive Tree 节点引用

    # ── 索引 ──
    raw_turn_ids: List[str]           # 原始对话轮次ID（正向索引）
    l2_summary_id: Optional[str]      # 所属二级摘要ID

    # ── 元数据 ──
    created_at: float
    compression_strategy: str         # RULE_DETERMINISTIC / TEMPLATE / LLM_SEMANTIC
    compression_ratio: Optional[float] # 实际信息保留率（仅 LLM_SEMANTIC 策略下评估，软目标）
    source_mode: str                  # RULE / LLM / HYBRID

    # 确定性内容专用（RULE_DETERMINISTIC 策略时填充）
    raw_content_slice: Optional[str]       # 原文切片（工具输出/日志/代码块）
    structured_extraction: Optional[dict]  # 结构化提取结果


@dataclass
class MetaInfo:
    """一级摘要的元信息——这是预测引擎的直接输入"""

    # 行为链快照
    prev_action: Optional[str]        # 前序行为（如 "运行程序"）
    current_action: str               # 当前行为（如 "查看日志"）
    predicted_next: List[PredictedAction]  # LLM预测的后续行为

    # 因果链快照
    causal_events: List[CausalEvent]  # 本轮相关的因果事件

    # 关联链快照
    associations: List[AssociationRef]  # 跨主题/跨实体的引用

    # 对话树定位
    position_in_topic: str            # "根→子话题→当前节点"的路径
    topic_depth: int                  # 在主题树中的深度
    is_topic_switch: bool             # 是否发生了话题切换

    # 用户信号
    user_satisfaction: Optional[float] # 用户满意度信号（如果可检测）
    correction_detected: bool         # 用户是否纠正了系统
    correction_detail: Optional[str]  # 纠正的详细描述
```

### 4.4 二级摘要的严格数据模型

```python
@dataclass
class Level2Summary:
    """二级摘要——主题级展开，是元信息的结构化聚合而非有损压缩"""

    summary_id: str                    # UUID
    topic_node_id: str                 # 所属 TopicTreeNode

    # ── 核心 ──
    topic_description: str            # 主题描述
    topic_started_at: float           # 话题起始时间
    topic_ended_at: Optional[float]   # 话题结束时间

    # ── 展开的行为推演图 ──
    behavior_dag: BehaviorDAG         # 该主题下完整的行为推演图
    # BehaviorDAG 是从所有一级摘要的 meta_info.prev_action/current_action/predicted_next
    # 合并去重后生成的有向图

    # ── 展开的因果链 ──
    causal_chain_full: List[CausalEvent]  # 该主题下所有因果事件

    # ── 展开的关联链 ──
    association_map: Dict[str, List[AssociationRef]]  # 按目标主题分组

    # ── 关键节点 ──
    key_decisions: List[KeyDecision]  # 关键决策点
    # KeyDecision: {timestamp, description, alternatives, chosen, outcome}
    divergence_points: List[DivergencePoint]  # 分歧点（用户走向了不同路径）
    unresolved_issues: List[str]      # 未解决的问题

    # ── 双向索引 ──
    l1_summary_ids: List[str]         # 正向索引：包含哪些一级摘要
    raw_turn_ids: List[str]           # 反向索引：包含哪些原始轮次（完整追溯）

    # ── 性能指标 ──
    total_turns: int                  # 总轮次数
    avg_confidence: float             # 该主题下的平均置信度
    correction_rate: float            # 纠正率（用户纠正次数/总轮次）
    prediction_accuracy: float        # 预测准确率

    # ── 元数据 ──
    created_at: float
    last_updated: float
    next_l2_id: Optional[str]         # 如果话题继续，链接到下一个二级摘要
```

### 4.5 摘要生成策略

#### 一级摘要生成

**时机**：每轮对话结束后立即生成。

**方式**：三级自适应策略——根据内容类型选择不同的摘要方式。

```
内容分类（规则驱动，<1ms）：
  ├─ 确定性内容: 工具输出 / 代码块 / 日志 → 规则引擎（直接切片 + 结构化提取）
  ├─ 半确定性内容: 明确指令 / 参数调整 / 配置修改 → 模板填充
  └─ 非确定性内容: 模糊需求 / 情感表达 / 歧义消解 → LLM 语义压缩
```

**LLM 模式 Prompt 结构**（仅非确定性内容触发）:

```
Prompt 结构:
  System: "你是一个对话摘要引擎。你的任务是将一轮对话转换为结构化的认知快照。
           输出JSON。信息丢失目标：≤20%。"
  Input:
    - 用户原始输入
    - 系统响应
    - 上一轮的一级摘要（用于行为链继承）
    - 当前 Topic Tree 节点的行为链上下文
    - Cognitive Tree 的最新节点（用于认知引用）
  Output: Level1Summary JSON
```

**质量约束**（软目标，非硬约束）:
- 确定性内容：信息丢失 0%（原文保留）
- 半确定性内容：信息丢失 ≤10%
- 非确定性内容：信息丢失目标 ≤20%，如果超过，标记为需要重生成但**不阻塞流程**

#### 二级摘要生成

**时机**：触发条件满足时后台异步生成（不阻塞用户交互）。

**触发条件**：
- 同主题积累 ≥ 5 轮且距上次二级摘要生成 ≥ 10 轮
- 用户切换到新主题（触发旧主题的二级摘要封存）
- 会话结束时
- 时间衰减触发 Cool Layer 压缩时

**方式**：结构化聚合（非压缩），从所有关联一级摘要的元信息中提取并合并。

```
聚合算法（结构化操作为主，语义矛盾时触发 LLM 消解）:
  1. 遍历该主题下所有一级摘要
  2. 合并行为链：去重 + 构建 DAG（节点=行为，边=因果权重）
  3. 合并因果链：去重 + 排序 + 标注关键事件
  4. 合并关联链：按目标分组 + 更新关联强度
  5. 提取关键决策点：遍历决策→结果对，计算影响范围
  6. 提取分歧点：找出行为链中分叉的节点
  7. 提取未解决问题：遍历元信息中 user_satisfaction < 0.5 的节点
  8. 语义矛盾检测：如果两个一级摘要对同一事件的判断矛盾
     （如 L1-A 标记 "用户满意"，L1-B 标记 "用户不满意"），
     触发一次轻量 LLM 调用做语义消解，确认最终结论
  9. 构建双向索引
```

### 4.6 检索策略

```
用户提及历史话题
  │
  ▼
Step 1: 检索二级摘要
  → 语义搜索 L2Summary.topic_description
  → 命中 → 返回完整 BehaviorDAG + 因果链 + 关联链
  │
  ▼
Step 2: 如果 Step 1 未命中，检索一级摘要
  → 语义搜索 L1Summary.core_semantics
  → 命中 → 返回 MetaInfo + 原始轮次ID
  │
  ▼
Step 3: 如果用户需要细节，通过索引下钻
  → L2Summary.raw_turn_ids → 加载原始轮次
  → L1Summary.raw_turn_ids → 加载原始轮次
  │
  ▼
Step 4: 如果原始轮次已被清理（Frozen）
  → 通过 L2Summary 的 BehaviorDAG 重构上下文
  → 通过 L2Summary.causal_chain_full 还原因果
```

---

## 5. 核心改造三：在线训练闭环（预测→验证→修正→回流）

### 5.1 整体架构

```
                              ┌──────────────────────┐
                              │   BehaviorPredictor   │
                              │  (LLM推理引擎)         │
                              │                      │
                              │  输入:               │
                              │  • 当前行为链快照     │
                              │  • 用户认知画像       │
                              │  • 历史行为图权重     │
                              │  • 可用工具集         │
                              │                      │
                              │  输出:               │
                              │  • Top-N 预测行为    │
                              │  • 每个行为的概率     │
                              │  • 预测理由          │
                              └──────────┬───────────┘
                                         │ 预测列表
                                         ▼
                              ┌──────────────────────┐
┌──────────────┐              │    融合器 (v3.1)      │              ┌──────────────┐
│ 算法引擎结果  │────────────→│                      │←─────────────│  LLM引擎结果  │
│ (Track-0)    │              │  Triple-Input Fusion │              │ (Track-1)    │
└──────────────┘              │                      │              └──────────────┘
                              │  新增: 预测结果作为   │
                              │  第三个输入源参与融合  │
                              └──────────┬───────────┘
                                         │ 融合结果
                                         ▼
                              ┌──────────────────────┐
                              │      用户行为         │
                              │  (实际的下一步操作)    │
                              └──────────┬───────────┘
                                         │
                              ┌──────────┴───────────┐
                              │                      │
                              ▼                      ▼
                    ┌─────────────────┐    ┌─────────────────┐
                    │  BehaviorRewarder│    │  BehaviorGraph   │
                    │  (奖励计算)       │    │  (权重更新)       │
                    │                 │    │                 │
                    │ 命中: +0.1      │──→│ w_new = α×causal │
                    │ 部分: +0.05     │    │  + β×freq       │
                    │ 失败: -0.2      │    │  + γ×profile    │
                    │ 纠正: +更新正确  │    │  + (1-α-β-γ)×w │
                    └─────────────────┘    └────────┬────────┘
                                                     │
                                                     ▼
                                           ┌─────────────────┐
                                           │ 写入行为链       │
                                           │  → TopicTreeNode │
                                           │  → L1Summary     │
                                           │  → L2Summary     │
                                           │  → Cognitive Tree│
                                           └─────────────────┘
```

### 5.2 BehaviorPredictor（预测引擎）

```python
class BehaviorPredictor:
    """
    基于用户画像 + 行为链历史 + 对话上下文预测用户下一步行为。

    这是一个 LLM 驱动的推理引擎，不是规则引擎。
    预测结果作为融合器的第三个输入源 (Prediction Track)。

    设计原则：
    - 不阻塞主流程：预测在后台并行运行
    - 不强制等待：如果预测未完成，融合器只用算法+LLM两个输入
    - 持续学习：每次预测被验证后，更新 BehaviorGraph 权重
    """

    def predict(
        self,
        current_behavior: BehaviorStep,
        behavior_history: List[BehaviorStep],    # 当前话题的历史行为链
        cognitive_profile: CognitiveProfileV2,    # 用户认知画像
        active_topic: TopicTreeNode_v3_1,         # 当前活跃话题节点
        available_tools: List[ToolSchema],        # 可用工具集
    ) -> List[Prediction]:
        """
        预测用户最可能的 N 个下一步行为。

        LLM Prompt 核心要素：
        1. 用户画像——Track A (认知动力学) + Track B (标签偏好)
           → 高级用户倾向快速操作序列，新手倾向逐步确认
        2. 前序行为链——类似 CPU Cache Line Prefetch
           → "运行程序"后常见序列：[看日志(0.73), 看结果(0.15), 反汇编(0.05)]
        3. 当前话题上下文——缩小预测空间
           → 在"调试"话题下，预测偏向工具操作；在"讨论设计"下，预测偏向分析请求
        4. 可用工具集——约束预测范围
           → 不可用的工具不在预测列表中

        输出：
        [
            Prediction(action="查看日志", probability=0.73, reasoning="历史中73%的'运行程序'后跟随'查看日志'"),
            Prediction(action="分析日志详情", probability=0.15, reasoning="当工具返回非零退出码时常见"),
            Prediction(action="修改配置重新运行", probability=0.08, reasoning="日志显示配置错误后的典型修复路径"),
        ]
        """
```

### 5.3 BehaviorRewarder（奖励计算器）

```python
class BehaviorRewarder:
    """
    计算预测奖励——预测命中/失败/纠正对应不同的奖励/惩罚信号。

    奖励信号不直接用于 LLM 微调（避免灾难性遗忘），
    而是用于更新 BehaviorGraph 的边权重，影响下一次融合时的预测概率。
    """

    def compute_reward(
        self,
        predicted_actions: List[Prediction],
        actual_action: BehaviorStep,
        user_correction: Optional[str] = None,  # 用户的纠正消息
    ) -> RewardResult:
        """
        奖励规则:

        | 场景                       | 奖励值    | 说明                          |
        |----------------------------|----------|-------------------------------|
        | 预测命中 (Top-1)           | +0.10    | 预测精准，快速通道可用           |
        | 预测命中 (Top-3)           | +0.05    | 预测在候选中，方向对但不够精准    |
        | 预测相关 (实体部分匹配)     | +0.03    | 行为不同但有语义相关性           |
        | 预测失败                   | -0.15    | 完全预测错误                   |
        | 用户明确纠正               | -0.20    | 不仅是错误，还暴露了推理盲区      |
        | 用户纠正 + 指定正确行为     | -0.20 + 更新 | 惩罚旧路径 + 提升正确路径权重  |
        | 用户无反馈（被动接收）       | 0.00     | 无信号，权重温和衰减            |
        """

    def detect_correction(
        self,
        user_input: str,
        system_prediction: Prediction,
    ) -> bool:
        """
        检测用户是否在纠正系统。

        识别模式（基于 PCR 的 noise_level + stability 画像区分纠错 vs 新需求）:
        - "不对，..." → 明确纠正
        - "不是这样的，应该..." → 纠正 + 指定正确方向
        - "算了，直接..." → 隐式纠正（放弃预测路径，走另一条）
        - "等一下，先..." → 优先级纠正（行为对但顺序错）
        """
```

### 5.4 BehaviorGraph（行为图——权重持久化层）

```python
class BehaviorGraph:
    """
    行为图是 BehaviorPredictor 的长期记忆。
    存储所有行为间的因果概率权重，随时间衰减，被纠正后快速修正。

    区别于 Cognitive Tree:
    - Cognitive Tree 记录 LLM 的推理过程（"为什么这样想"）
    - BehaviorGraph 记录行为间的统计规律（"现实中发生了什么"）
    """

    def update_edge(
        self,
        from_action: str,
        to_action: str,
        reward: float,
        cognitive_profile: CognitiveProfileV2,
    ):
        """
        核心权重更新公式 (v3.1 改进版):

        w_new = α × causal_prob   (LLM的因果推断概率)
              + β × freq_ratio    (历史频次 N(a→b)/N(a))
              + γ × profile_boost (用户画像加成)
              + (1-α-β-γ) × w_old

        默认权重: α=0.3, β=0.4, γ=0.1
        → LLM 推理占 30%，统计频次占 40%，用户画像占 10%，旧值占 20%

        用户纠正时的修正:
        - 如果 reward < 0 (预测失败):
          w_old_path *= 0.6      # 旧路径权重下调 40%
          w_new_path = max(w_old_path + 0.3, 0.1)  # 正确路径提权
        """

    def decay_weights(self):
        """
        定期衰减所有边权重（后台任务，每 30 分钟）:
        w(t+1) = w(t) × e^(-1/τ)
        其中 τ 默认为 24 小时

        长期未被使用的路径权重自然归零。
        高频路径即使衰减也保持较高权重。
        """

    def export_for_summary(self, topic_id: str) -> BehaviorDAG:
        """
        导出某个话题的完整行为推演图。
        供二级摘要系统使用。
        """
```

### 5.5 与 Meta-Cognitive 和 Reflective 层的协同

```
训练闭环的三个时间尺度：

┌───────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ 实时 (每轮)    │     │ 准实时 (每N轮)     │     │ 离线 (每会话/每天)  │
├───────────────┤     ├──────────────────┤     ├───────────────────┤
│ BehaviorRewarder│   │ Meta-Cognitive层  │     │ Reflective层       │
│               │     │                  │     │                   │
│ 计算即时奖励    │     │ 检测系统性预测偏差  │     │ 跨会话模式发现     │
│ 更新边权重     │     │ 生成算法调优建议    │     │ 更新全局行为模板   │
│ 写入行为链     │     │ 标记预测盲区       │     │ 跨用户行为规律提取  │
│               │     │ 生成训练报告       │     │ 用户画像长期更新    │
└───────────────┘     └──────────────────┘     └───────────────────┘
```

---

## 6. 核心改造四：融合器升级为结构化合并

### 6.1 当前融合器的局限（v3.0）

v3.0 的融合器对两个输入做**加权平均**：`O = weighted(A, B)`。

**问题**：算法结果和 LLM 结果往往不在同一维度：

| 场景 | 算法引擎输出 A | LLM 引擎输出 B | v3.0 融合 | 正确的做法 |
|------|--------------|---------------|----------|-----------|
| 实体提取 | 提取了 PID=1234 | 理解了"那个进程"指 PID=1234 | 不知道如何加权 | **合并为互补信息**：实体 + 推理依据 |
| 意图分类 | SCAN_MEMORY(c=0.55) | READ_MEMORY(c=0.60) | 加权选一个 | 两个都保留为候选，由后续决策确认 |
| 计划生成 | 3步模板 | 5步详细计划 | 不知道如何融合 | **模板做骨架，LLM做填充，合并输出** |
| 行为预测 | 无此能力 | N/A | N/A | v3.1 新增 Prediction Track |

### 6.2 v3.1 三重融合架构

```
                     输入
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────────┐
   │ Track-0 │  │ Track-1 │  │ Track-P      │
   │ 算法引擎 │  │ LLM引擎  │  │ Prediction   │  ← v3.1 新增
   │         │  │         │  │ (行为预测)    │
   └────┬────┘  └────┬────┘  └──────┬──────┘
        │            │              │
        ▼            ▼              ▼
   ┌─────────┐  ┌─────────┐  ┌─────────────┐
   │ 算法结果 │  │ LLM结果  │  │  预测结果    │
   │ (快速)   │  │ (深度)   │  │  (前瞻)     │
   └────┬────┘  └────┬────┘  └──────┬──────┘
        │            │              │
        └────────────┼──────────────┘
                     ▼
        ┌─────────────────────────┐
        │  结构化合并器 (v3.1)      │
        │                         │
        │  分维度合并策略:          │
        │  • 同维度 → 加权融合      │
        │  • 互补维度 → 合并        │
        │  • 冲突维度 → 深度仲裁    │
        │  • 预测维度 → 联动融合    │
        └─────────────┬───────────┘
                      ▼
                   输出
```

### 6.3 结构化合并策略

```python
class StructuredFusionEngine:
    """
    v3.1 结构化合并器。

    核心理念：
    - 不是"算法 vs LLM"的二选一，而是"算法+LLM+预测"的三维互补
    - 不同维度的信息不应该加权，应该合并
    - 同维度的信息冲突才需要仲裁
    - 预测维度提供前瞻性，不参与当前决策的核心逻辑
    """

    def fuse(
        self,
        algorithm_result: AlgorithmOutput,   # Track-0
        llm_result: LLMOutput,               # Track-1
        predictions: List[Prediction],       # Track-P (v3.1新增)
        context: FusionContext,
    ) -> FusionOutput:
        """
        分维度合并策略：

        维度 1: 实体 (Entities)
          → 算法提取 + LLM补充 → 合并为联合实体集
          → 每个实体标注来源和置信度

        维度 2: 意图 (Intent)
          → 如果算法和LLM的意图一致 → 加权置信度
          → 如果冲突 → 保留两个候选，标记为需要澄清
          → 不丢信息（v3.0会丢弃一个）

        维度 3: 计划 (Plan)
          → 算法的模板做骨架 (skeleton)
          → LLM的细节做填充 (filling)
          → 如果模板步骤在LLM计划中不存在 → 标记为"算法盲区"
          → 如果LLM步骤在模板中不存在 → 标记为"创新点"

        维度 4: 行为预测 (Prediction)
          → 预测结果不参与当前轮决策（不猜用户意图）
          → 预测结果用于：
             a) 预取上下文（类似 cache prefetch）
             b) 预加载工具（减少延迟）
             c) 调整 PCR 期望推断的 prior
          → 预测被用户行为验证后才影响权重

        维度 5: 认知推断 (Cognitive)
          → LLM 的推理过程写入 Cognitive Tree
          → 算法的规则匹配不写入（确定性操作不产生认知节点）
          → 融合输出包含 cog_refs 供后续追溯
        """

    def detect_and_resolve_conflicts(
        self,
        algorithm_result: AlgorithmOutput,
        llm_result: LLMOutput,
    ) -> List[Conflict]:
        """
        冲突检测（v3.0已有，v3.1增强）。

        新增：
        - 不仅检测"是否冲突"，还检测"冲突类型"
        - FACTUAL: 事实性冲突（如实体值不同）→ 必须以算法为准（算法提取是确定性的）
        - SEMANTIC: 语义冲突（如意图理解不同）→ 以 LLM 为准（LLM理解更深）
        - STRATEGIC: 策略冲突（如计划路径不同）→ 保留两个候选

        冲突类型决定了降级策略。
        """

    def fast_path_check(
        self,
        algorithm_result: AlgorithmOutput,
        predictions: List[Prediction],
    ) -> bool:
        """
        v3.1 快速通道检查（比v3.0更智能）。

        v3.0: c_A > 0.85 → 直接输出
        v3.1: c_A > 0.85 AND 预测 Top-1 与算法结果一致 → 直接输出
              c_A > 0.85 BUT 预测 Top-1 与算法冲突 → 等待 LLM 验证
        
        这一点很关键：即使算法置信度很高，如果预测引擎说"不对劲"，
        也应该等一下LLM的深度分析。避免算法在高置信度盲区犯错。
        """
```

### 6.4 融合决策树

```
算法结果 (c_A)  LLM结果 (c_B)  预测结果 (Top-1)
     │              │              │
     ▼              ▼              ▼
┌─────────────────────────────────────────────┐
│              融合决策树                       │
├─────────────────────────────────────────────┤
│                                             │
│ c_A > 0.85 AND 预测一致?                     │
│   ├─ YES → Fast Path: 算法输出 + 预测预加载    │
│   └─ NO  → c_B 完成?                         │
│             ├─ YES → 合并 A + B + 预测         │
│             └─ NO  → 等待 B (最多 200ms)       │
│                                             │
│ c_A < 0.6?                                  │
│   ├─ YES → 等待 B（以 LLM 为主）               │
│   └─ NO  → A 和 B 都可用                      │
│             ├─ 冲突?                          │
│             │   ├─ FACTUAL → 算法为准          │
│             │   ├─ SEMANTIC → LLM 为准        │
│             │   └─ STRATEGIC → 保留候选        │
│             └─ 不冲突 → 结构化合并              │
│                                             │
│ c_A < 0.5 AND c_B < 0.5?                    │
│   ├─ YES → 检查预测是否可用                    │
│   │         ├─ 预测高置信度 → 基于预测引导询问  │
│   │         └─ 预测低置信度 → 完全降级要求澄清   │
│   └─ NO  → 结构化合并                          │
└─────────────────────────────────────────────┘
```

---

## 7. 数据流与生命周期

### 7.1 单轮对话的完整数据流

```
时间轴 ──────────────────────────────────────────────────────────→

T=0ms   用户输入到达
   │
   ▼
T=0-2ms  约束补全编译器 前置解析（原 Cognitive Compiler 升级）
   │        → 语法分解 + 隐式实体补全 + 约束激活 + 约束消解 + 稳定性评分（§2.5）
   │
   ▼
T=2-5ms  PCR 噪声检测 + 期望推断
   │
   ▼
T=5-10ms Intent Parser 解析
   │
   ├─→ [Track-0 算法引擎启动]  ─────────┐
   ├─→ [Track-1 LLM引擎启动]   ─────────┤
   └─→ [Track-P 预测引擎启动]  ─────────┤  ← v3.1 新增，并行运行
                                          │
T=10-50ms  三个 Track 并行执行              │
   │                                       │
   ├─ Track-0 完成 (最快，~10ms)          │
   │   → 如果 Fast Path 条件满足 → 立即输出  │
   │   → 否则等待                          │
   │                                       │
   ├─ Track-1 完成 (~50-200ms)            │
   │                                       │
   └─ Track-P 完成 (~100-300ms, 不阻塞)   │
   │                                       │
   ▼                                       │
T=50-200ms  结构化合并器融合三路结果         │
   │                                       │
   ▼                                       │
T=200ms    输出响应给用户                   │
   │                                       │
   ▼                                       │
T=200-500ms  后处理（不阻塞下一个轮次）:      │
   ├─→ 生成 L1Summary（一级摘要）           │
   ├─→ 更新 TopicTreeNode 的行为链          │
   ├─→ 更新 Cognitive Tree（记录决策节点）   │
   ├─→ 触发 BehaviorRewarder（下一轮用户行为后）│
   └─→ 检查 L2Summary 触发条件              │
```

### 7.2 跨轮次的训练闭环

```
Turn N-1                       Turn N                        Turn N+1
─────────                      ──────                       ─────────

系统输出 + 预测列表              用户行为到达                   系统输出（权重已更新）
      │                            │                              │
      │  预测: [A(0.73), B(0.15)]   │  用户实际执行了 C             │  预测: [C(0.48), A(0.35), B(0.10)]
      │  timestamp: T+0             │  timestamp: T+Δt             │
      │                            │                              │
      └────────────────────────────┤                              │
                                   │                              │
                              BehaviorRewarder                     │
                              ├─ 计算时间衰减因子:                  │
                              │   decay = e^(-Δt/τ)                │
                              │   若 Δt < 30s, τ=∞（无衰减）       │
                              │   若 Δt > 5min, τ=300s（温和衰减）  │
                              │   若 Δt > 1h, τ=3600s（显著衰减）  │
                              │   奖励 = 原始奖励 × decay           │
                              ├─ 预测失败: -0.15 × decay           │
                              ├─ 用户纠正: "不对，应该C" -0.20 × decay│
                              └─ 更新 BehaviorGraph:              │
                                   ├─ w(A→B) *= 0.6 (下降)        │
                                   └─ w(A→C) = 0.35 (新增)         │
                                                                   │
                              写入:                                │
                              ├─ L1Summary(Turn N-1).meta_info.    │
                              │   predicted_next → [标记: 预测失败] │
                              ├─ TopicTreeNode.causal_chain        │
                              │   → USER_CORRECTION 事件            │
                              └─ Cognitive Tree                    │
                                  → REFLECTION 节点                 │

收敛效果:
  - Turn N-1: 预测准确率 0%（首次遇到 A→C 路径）
  - Turn N+1: 预测准确率提升（C 进入候选 Top-1，weight=0.48）
  - Turn N+5: 预测准确率趋稳（经过3-5轮验证，C 权重达到 0.6+）
```

### 7.3 摘要的生命周期

```
L1Summary 生命周期:
  创建: 每轮结束后立即生成
  存储: Redis (Hot/Warm) + PostgreSQL (Cool/Cold)
  衰减: 随记忆阶梯跃迁 (Hot→Warm→Cool→Cold→Frozen)
  删除: Frozen 后可被 GC 清理（L2Summary 已包含聚合信息）

L2Summary 生命周期:
  创建: 触发条件满足时后台生成
  更新: 话题继续时增量合并新的一级摘要
  封存: 话题切换时标记为 completed
  删除: 永不删除（L2Summary 是长期记忆，大小可控）
```

---

## 8. 工程实现计划

### 8.1 目录结构

```
core/agent/v3_1/                    # v3.1 新增模块
├── behavior_graph/                 # 行为图（核心新增）
│   ├── __init__.py
│   ├── graph.py                    # BehaviorGraph 核心
│   ├── predictor.py                # BehaviorPredictor（LLM推理）
│   ├── rewarder.py                 # BehaviorRewarder（奖励计算）
│   ├── models.py                   # 数据模型（BehaviorStep, BehaviorEdge等）
│   └── decay.py                    # 权重衰减定时任务
│
├── summary/                        # 双层摘要系统（重构v2.0第8章）
│   ├── __init__.py
│   ├── level1.py                   # L1Summary 生成器
│   ├── level2.py                   # L2Summary 聚合器
│   ├── index.py                    # 双向索引管理
│   ├── retrieval.py                # 分层检索策略
│   └── models.py                   # 摘要数据模型
│
├── fusion/                         # 融合器升级
│   ├── __init__.py
│   ├── structured_fusion.py        # StructuredFusionEngine
│   ├── conflict_resolver.py        # 冲突检测与消解 + 主动矛盾消解
│   ├── fast_path.py                # 快速通道（含预测验证）
│   └── constraints.py              # HardConstraintGuard + Schema Guard
│
├── embedding/                       # 行为语义嵌入层（§3.5 / §11.1）
│   ├── __init__.py
│   ├── encoder.py                   # BGE-small 推理封装
│   ├── neighbor.py                  # 语义邻居查询
│   └── index.py                     # 向量索引管理
│
├── outcome/                         # 轻量结果预测（§11.3）
│   ├── __init__.py
│   ├── predictor.py                 # OutcomePredictor
│   └── value.py                     # 候选计划价值评估
│
└── training/                       # 训练闭环 + 冷启动
    ├── __init__.py
    ├── loop.py                     # 训练闭环主逻辑
    ├── coldstart.py                # Skill 元数据冷启动提供器
    ├── metrics.py                  # 预测准确率等指标
    └── report.py                   # Meta-Cognitive 训练报告生成

core/agent/v3_0/                    # 现有代码不改动
├── topic_tree/                     # TopicTreeNode 增加字段
├── cognitive_tree/                 # 保持不变
└── ...
```

### 8.2 分阶段 Roadmap

| 阶段 | 内容 | 工作量 | 风险 | 验收 |
|------|------|--------|------|------|
| **Phase 1** | TopicTreeNode 增加三链字段 + L1Summary 数据模型 | ~200行 | 低 | 现有测试通过 + 新字段可读写 |
| **Phase 2** | BehaviorGraph + BehaviorPredictor + BehaviorRewarder | ~500行 | 中 | 单元测试: 预测→验证→更新闭环 |
| **Phase 3** | L2Summary 聚合器 + 双向索引 | ~300行 | 中 | 单元测试: 聚合正确性 + 索引完整性 |
| **Phase 4** | 融合器升级为结构化合并 + Prediction Track | ~300行 | 高 | 集成测试: 三路融合正确性 |
| **Phase 5** | 训练闭环与 Meta-Cognitive/Reflective 协同 | ~200行 | 中 | E2E测试: 用户纠正后权重更新可观测 |
| **Phase 6** | 性能优化 + 线上验证 | ~200行 | 低 | 延迟增加 <50ms + 预测准确率 >70% |

### 8.3 关键技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| BehaviorPredictor 延迟过高 | 拖慢 Fast Path | 异步运行，不阻塞输出 |
| L1Summary 信息保留率不达标 | 摘要质量差 | 三级自适应：确定性内容零丢失，非确定性软目标 |
| BehaviorGraph 在高维行为空间稀疏 | 预测准确率低 | 语义嵌入邻居泛化 + Skill 冷启动模板 |
| 训练信号噪声（纠错 vs 新需求的误判） | 权重被错误更新 | PCR noise_level + stability 画像联合判断 |
| v3.0已有测试回归 | 阻塞上线 | 新增模块不影响现有代码路径 |
| 语义嵌入层的邻居质量衰减 | 泛化能力下降 | 定期重建索引 + 相似度阈值动态调整 |
| 分层存储同步延迟 | 数据不一致 | Redis→PG 30s批量，PG→Neo4j 5min增量，会话结束全量flush |

---

## 9. 设计决策记录

### ADR-011: 为什么不替换 Topic Tree 而是扩展它？

**决策**：在现有 TopicTreeNode 上增加三链字段，不新建独立的行为树。

**理由**：
- Topic Tree 已经有话题→行为的多对一关系（一个话题下发生一组行为）
- 新增独立的行为树会让查询变复杂（查一个行为需要跨两棵树）
- 三链字段作为可选字段，向后兼容

### ADR-012: 为什么 L1Summary 用 LLM 生成而不是规则模板？

**决策**：L1Summary 由 LLM 生成结构化 JSON，不再使用规则模板。

**理由**：
- 规则模板信息丢失 60-70%（只能提取意图+实体+结果）
- 行为链、因果链、关联链无法由规则提取（需要语义理解）
- LLM 生成的一次调用成本（约 0.001 USD）远低于因信息丢失导致的后续决策错误成本
- degrpade：如果 LLM 生成失败或超时，回退到规则模板

### ADR-013: 为什么预测结果不参与当前轮决策？

**决策**：Track-P 的预测结果只用于预加载和 prior 调整，不参与当前轮的核心决策。

**理由**：
- 预测是"猜用户会做什么"，当前轮决策是"理解用户说了什么"——两者不应混淆
- 如果预测错误 → 参与了决策 → 可能导致系统误解当前意图
- 预测的正确用法是：在后台准备资源，等用户下一步行为确认后再调整权重

### ADR-014: 为什么 BehaviorGraph 权重不直接用于 LLM fine-tuning？

**决策**：BehaviorGraph 的权重用于在线推演，不用于 LLM 模型的参数更新。

**理由**：
- 在线 fine-tuning 会引入灾难性遗忘
- BehaviorGraph 的权重是会话级/用户级的，LLM 参数是跨用户的
- 行为权重的价值在于"为当前用户提供个性化预测"，不应泛化到所有用户

---

## 10. 附录：与现有设计的对照

### 10.1 v2.0/v3.0 → v3.1 变更映射

| v2.0/v3.0 组件 | v3.1 变更 | 变更类型 |
|---------------|----------|---------|
| TopicTreeNode | 增加 behavior_chain / causal_chain / association_chain / summary_level_1 / summary_level_2 | 字段扩展 |
| BehaviorGraph | 新组件 | 新增 |
| BehaviorSemanticEmbedding | 新组件（v3.1.1） | 新增 |
| BehaviorPredictor | 新组件 | 新增 |
| BehaviorRewarder | 新组件 | 新增 |
| OutcomePredictor | 新组件（v3.1.1） | 新增 |
| 记忆系统 §8.4 一级摘要 | 重构为 L1Summary（三级自适应：规则/模板/LLM） | 重构 |
| 记忆系统 §8.4 二级摘要 | 重构为 L2Summary（结构化聚合，非压缩） | 重构 |
| 摘要存储与检索 | 新增双向索引 + 分层检索策略 + 分层存储（Redis/PG/Neo4j） | 新增 |
| 融合器 (HybridEngine) | 升级为 StructuredFusionEngine + Prediction Track + 主动矛盾消解 | 升级 |
| 认知双工 (Cognitive Duplex) | 从双轨升级为三轨（算法 ∥ LLM ∥ 预测） | 升级 |
| PCR 期望推断 | 预测结果作为 prior 调整因子 | 增强 |
| Planning-LLM | 新增 HardConstraintGuard + 神经符号约束注入 | 增强 |
| Meta-Cognitive 层 | 新增训练报告生成 + 系统性预测偏差检测 | 增强 |
| Reflective 层 | 新增跨会话行为模式发现 | 增强 |
| ColdStartProvider | 新组件（v3.1.1，Skill 元数据冷启动） | 新增 |

### 10.2 不变的部分

以下组件在 v3.1 中完全不变：

- Cognitive Compiler（前置解析层）→ **v3.2 升级为约束补全编译器**
- PCR 噪声检测器 + 期望推断器
- Intent Parser 八阶段流水线
- Layer 1.5 Planning Skill Layer
- Layer 2 对话状态机
- Layer 3 服务接口层
- 认知画像系统 v2.0（Track A + Track B）
- 可观测性系统
- Topic Tree 节点权重更新算法（EMA）
- 上下文窗口分层存储模型（Hot/Warm/Cool/Cold）
- 三层 LLM 架构（Layer 1.5 / Layer 2.5 / Layer 3）
- Cognitive Tree 数据模型
- 幻觉检测机制

### 10.3 v3.2 新增组件与 Literature Cortex v6.0 的对照

| DialogMesh v3.2 组件 | 来源 | 用途 |
|---|---|---|
| 因果基地 (Causal Substrate) | Literature Cortex 键合图+Petri网+系统动力学+范畴论 | 结构因果先验 |
| MetaRole 枚举 (8角色) | Literature Cortex 元角色注册表 | 行为链→元角色映射 |
| BehaviorNegativeKnowledge | Literature Cortex negative_matches | 负知识库，永久禁止 |
| CausalSubstrateScheduler | Literature Cortex BudgetScheduler | 成本分级调度 |
| STRUCTURAL 冲突仲裁 | Literature Cortex CL2 硬闸门 | 融合器最高优先级因果判定 |

### 10.4 与 v3.0 Cognitive Tree 的协同

```
                  BehaviorGraph                 Cognitive Tree
                  ─────────────                 ──────────────
记录内容:          用户做过什么                     LLM想过什么
节点类型:          BehaviorStep                  PERCEPTION/HYPOTHESIS/REASONING/...
边类型:           时序因果概率                     DERIVES/SUPPORTS/CONTRADICTS/...
更新驱动:          用户实际行为                      LLM推理过程
预测用途:          预测下一步行为                    不预测（纯记录）
与摘要关系:        写入 L1Summary.meta_info         写入 L1Summary.cognitive_tree_refs
与TopicTree关系:   作为 TopicTreeNode 的子结构       通过 cog_refs/topic_refs 交叉引用
```

两者**不重复**：BehaviorGraph 是"真实世界发生了什么"，Cognitive Tree 是"LLM怎么理解这个世界"。

---

## 11. v3.1.1 补充设计：泛化能力与实现细节

> **说明**：本章是对 v3.1 的补充和修正，涵盖设计审查中发现的泛化能力缺口和工程实现细节。

---

### 11.1 泛化与精确的张力分析

#### 11.1.1 问题陈述

v3.1 设计中存在一条从精确到泛化的光谱，但**缺少中间层**：

```
精确型 ←──────────────────────────────────────────→ 泛化型
(专攻性强、确定性强)                              (关联性强、覆盖广)

 算法引擎     BehaviorGraph      [ 空缺 ]      LLM引擎    BehaviorPredictor
 规则匹配     精确行为对统计                    语义理解    行为预测
 零波动      字面匹配                         高波动     概率推断
```

**核心问题**：BehaviorGraph 的边权重基于精确的 `(action_A, action_B)` 字面匹配，不做语义泛化。当遇到未见过的行为对时（冷启动或长尾场景），直接退到 LLM 的 `causal_prob`，中间没有任何过渡层。

这导致两个问题：
1. **稀疏性**：高维行为空间中，大多数行为对的 `freq_ratio = 0`
2. **孤岛效应**："运行程序→查看日志"和"启动服务→查看日志"是两个完全独立的统计，无法共享经验

#### 11.1.2 解决方案：行为语义嵌入层 + 动词-名词解耦

在 BehaviorGraph 和 LLM 之间插入一个**行为语义嵌入层（Behavior Semantic Embedding）**，并在嵌入之上加一层**动词-名词解耦后处理**，防止"运行程序"和"删除程序"因共享名词而在向量空间中靠太近。

```
精确型 ←─────────────────────────────────────────→ 泛化型

 算法引擎  BehaviorGraph  语义嵌入层   LLM引擎  BehaviorPredictor
 规则匹配  精确统计      邻居泛化     语义理解   行为预测
 零波动   字面匹配      有限泛化     高波动    概率推断
```

```python
class BehaviorSemanticEmbedding:
    """
    将行为映射到向量空间，在泛化和精确之间建立连续过渡。

    这是 BehaviorGraph 和 LLM 之间的桥梁：
    - BehaviorGraph 提供精确的行为对频率统计
    - LLM 提供深度语义理解和泛化
    - 嵌入层让两者在同一坐标系中工作，填补中间地带

    嵌入模型：BGE-small-en（384维）或类似轻量模型
    推理延迟：<5ms（本地推理，不依赖 LLM 调用）
    """

    def embed(self, action: str) -> np.ndarray:
        """将行为描述（≤50字的自然语言）映射到 384 维向量"""

    def query_weight(
        self,
        from_action: str,
        to_action: str,
        behavior_graph: BehaviorGraph,
    ) -> Tuple[float, str]:
        """
        分层权重查询（精确→邻居→LLM 三级退避）:

        Step 1: 精确匹配
          → 在 BehaviorGraph 中查 (from_action, to_action)
          → 命中 → 直接返回精确权重 + 来源标记: "EXACT"

        Step 2: 语义邻居泛化
          → 未命中 → 在嵌入空间中找 Top-K 语义邻居行为对
          → 计算: weight = Σ(neighbor_weight × cosine_sim) / Σ(cosine_sim)
          → 来源标记: "NEIGHBOR(k=N)"

        Step 3: 全局退避
          → 无合适邻居 → 返回 None + 来源标记: "LLM_FALLBACK"
          → 调用者自行使用 LLM causal_prob
        """

    def find_semantic_neighbors(
        self,
        action: str,
        k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> List[Tuple[str, float]]:
        """
        在嵌入空间中找到 Top-K 语义相似的行为。

        示例:
          "运行程序" → [("启动服务", 0.94), ("执行脚本", 0.89), ...]
          "查看日志" → [("检查输出", 0.91), ("分析日志", 0.87), ...]

        相似度阈值 0.7 是一个经验值：
        - 太高层（>0.9）：邻居太少，泛化不足
        - 太低（<0.5）：引入噪声，精确性受损
        """
```

**效果**：
- 泛化能力从"全有或全无"（精确 OR LLM）变为**连续过渡**
- 新行为从相似行为继承先验权重，不需要从零积累
- 不增加 LLM 调用（嵌入推理是纯本地计算，<5ms）

##### 动词-名词解耦后处理

**问题**：纯 BGE-small 嵌入下，`"运行程序"` 和 `"删除程序"` 可能因为共享"程序"而在向量空间中距离很近（余弦相似度 0.78），但这两个行为在因果上是灾难性的对立。

**方案**：在嵌入计算相似度时，按行为类型动态加权动词和名词成分：

```python
class ActionAwareEmbedding:
    """
    在 BGE-small 嵌入之上加一层动词-名词解耦后处理。

    不是"动词永远比名词重要"——取决于行为类型。
    """

    # 行为类型 → (动词权重, 名词权重)
    WEIGHT_MAP = {
        "TOOL_EXEC":      (0.7, 0.3),   # 执行/删除/修改是本质区别
        "CODE_RUN":       (0.7, 0.3),
        "LOG_CHECK":      (0.4, 0.6),   # 名词更重要：看什么日志
        "ENTITY_ANALYZE": (0.3, 0.7),   # 名词更重要：分析什么实体
        "CONFIG_MODIFY":  (0.5, 0.5),
        "EXPLORATION":    (0.3, 0.7),   # 名词（领域）决定探索方向
    }

    def compute_similarity(
        self,
        action_a: str, action_b: str,
        action_type: str,
    ) -> float:
        # 1. 用轻量 LLM（~50 tokens prompt）拆分动词/名词成分
        #    Prompt: "将行为描述拆为动词成分和名词成分。只输出JSON。"
        #    输入: "运行程序" → {"verb": "运行", "noun": "程序"}
        a_verb, a_noun = self._split(action_a)
        b_verb, b_noun = self._split(action_b)

        # 2. 分别嵌入
        a_verb_vec = self.embed(a_verb)
        a_noun_vec = self.embed(a_noun)
        b_verb_vec = self.embed(b_verb)
        b_noun_vec = self.embed(b_noun)

        # 3. 按行为类型加权组合
        w_verb, w_noun = self.WEIGHT_MAP.get(action_type, (0.5, 0.5))
        a_vec = w_verb * a_verb_vec + w_noun * a_noun_vec
        b_vec = w_verb * b_verb_vec + w_noun * b_noun_vec

        return cosine_similarity(a_vec, b_vec)
```

**效果验证**：

```
行为类型: TOOL_EXEC (动词权重 0.7, 名词权重 0.3)

  纯 BGE-small:
    sim("运行程序", "删除程序") = 0.78  ← 危险！
  加解耦后:
    sim("运行程序", "删除程序") = 0.31  ← 安全，动词差异主导
    sim("运行程序", "启动服务") = 0.62  ← 合理，工具操作语义接近

行为类型: ENTITY_ANALYZE (动词权重 0.3, 名词权重 0.7)

  纯 BGE-small:
    sim("分析日志", "分析代码") = 0.72
  加解耦后:
    sim("分析日志", "分析代码") = 0.48  ← 名词差异拉大
    sim("分析日志", "检查日志") = 0.71  ← 动词不同但名词相同，合理
```

动词-名词拆分的轻量 LLM 调用（~50 tokens prompt + ~20 tokens output）在嵌入层初始化时批量完成，不增加运行时开销。

#### 11.1.3 组件泛化/精确能力总览

| 组件 | 精确性 | 泛化性 | 实现方式 | 典型场景 |
|------|--------|--------|---------|---------|
| 算法引擎 (Track-0) | 极高 | 极低 | 确定性规则匹配 | 已知实体提取、固定模板 |
| BehaviorGraph (精确层) | 高 | 低 | 字面行为对频率统计 | 高频路径、个性化模式 |
| **语义嵌入层（新增）** | **中** | **中高** | **向量空间邻居查询** | **冷启动、长尾行为** |
| LLM 引擎 (Track-1) | 低 | 高 | 深度语义理解 | 隐含意图、歧义消解 |
| BehaviorPredictor | 中低 | 极高 | LLM 推理 + 历史权重 | 行为预测、路径推演 |

---

### 11.2 融合器的主动矛盾消解

#### 11.2.1 问题

当前 v3.1 融合器在 Track-P（预测）和 Track-1（LLM理解）矛盾时，等待 Meta-Cognitive 层来仲裁。这个等待太慢——Meta-Cognitive 是跨轮运行的，矛盾可能在下轮才被发现。

#### 11.2.2 解决方案：融合器内嵌主动消解

```python
class StructuredFusionEngine:
    # ... 已有方法 ...

    def proactive_conflict_detection(
        self,
        llm_understanding: LLMOutput,    # Track-1: "用户想做什么"
        predictions: List[Prediction],   # Track-P: "用户下一步会做什么"
        context: FusionContext,
    ) -> ProactiveResolution:
        """
        主动消解：在矛盾发生时立即处理，不等 Meta-Cognitive。

        矛盾信号检测:
        1. LLM 认为用户在"讨论设计"，但预测引擎说用户很可能"执行代码"
           → 矛盾类型: INTENT_ACTION_MISMATCH
           → 这意味着LLM可能低估了用户的工具使用倾向

        2. Track-0 提取了实体 X，Track-P 预测的行为通常需要实体 Y
           → 矛盾类型: ENTITY_PREDICTION_MISMATCH
           → 可能是实体提取遗漏或用户意图不明确

        消解策略:
        ┌────────────────────────────────────────────┐
        │ 矛盾类型               │ 消解动作             │
        ├────────────────────────┼─────────────────────┤
        │ INTENT_ACTION_MISMATCH │ 降低当前决策置信度    │
        │                        │ 预加载预测的工具      │
        │                        │ 延长响应窗口          │
        ├────────────────────────┼─────────────────────┤
        │ ENTITY_PREDICTION_MISMATCH │ 触发实体二次提取 │
        │                        │ 扩大实体搜索范围      │
        │                        │ 标记为"需澄清"        │
        ├────────────────────────┼─────────────────────┤
        │ CONFIDENCE_DIVERGENCE  │ 同时降低两者权重      │
        │                        │ 强制走保守路径        │
        │                        │ 生成澄清问题          │
        └────────────────────────────────────────────┘

        矛盾不是 bug，是信号。
        它告诉系统"当前认知模型可能有问题"，应该立即降级。
        """

    def compute_trust_decay(
        self,
        contradiction_count: int,
        time_window: float,  # 时间窗口（秒）
    ) -> float:
        """
        矛盾累积检测：如果在短时间内连续出现矛盾，
        可能意味着系统模型本身在当前场景下不适用。

        decay = 1 / (1 + contradiction_count / time_window)

        例如: 10秒内 3 次矛盾 → decay = 1/(1+3/10) = 0.77
              融合器输出置信度 × 0.77
        """
```

---

### 11.3 轻量结果预测

#### 11.3.1 设计定位

不做全量 World Model（推演完整状态变化），做**结果分类预测 + 价值排序**：

```python
class OutcomePredictor:
    """
    轻量结果预测器——不模拟执行，只预测结果的类型和概率。

    数据来源（按优先级）:
    1. Skill 元数据定义的返回值类型和错误码
    2. BehaviorGraph 中该行为链路的历史结果统计
    3. 语义嵌入层的相似行为结果分布
    4. LLM 常识推理（仅在前三者都不可用时）
    """

    def predict_outcomes(
        self,
        action: BehaviorStep,
        skill_metadata: SkillMetadata,
        behavior_graph: BehaviorGraph,
    ) -> List[OutcomePrediction]:
        """
        返回:
        [
            Outcome("成功返回预期结果", probability=0.65),
            Outcome("工具报错（参数错误）", probability=0.20),
            Outcome("权限不足", probability=0.10),
            Outcome("超时", probability=0.05),
        ]

        用途:
        - 融合器多候选价值排序
        - 预加载错误恢复路径
        - PCR 期望推断的 prior 调整
        """

    def compute_candidate_value(
        self,
        candidate: PlanCandidate,
        outcome_prediction: List[OutcomePrediction],
        cognitive_profile: CognitiveProfileV2,
    ) -> float:
        """
        价值评估 = 成功率 × 0.5 + 用户满意度先验 × 0.3 + (1 - 认知负载) × 0.2

        只在融合器多个候选计划置信度接近（差值 < 0.1）时启用。
        不替代用户选择，只做排序辅助。
        """
```

---

### 11.4 三级自适应摘要引擎

#### 11.4.1 替代统一的 ≤20% 硬约束

§4 中 L1Summary 的"信息丢失 ≤20%"从硬约束改为**分级软目标**：

```
┌─────────────────────────────────────────────────────────────┐
│                   三级自适应摘要引擎                         │
├───────────────┬─────────────────┬───────────────────────────┤
│ 内容类型      │ 摘要策略         │ 信息丢失目标    │ 延迟     │
├───────────────┼─────────────────┼─────────────────┼─────────┤
│ 确定性内容     │ 规则引擎         │ 0%（原文保留）   │ <1ms    │
│ • 工具输出     │ 直接切片          │                 │         │
│ • 代码块       │ + 结构化提取      │                 │         │
│ • 日志         │ （意图+实体+结果） │                 │         │
├───────────────┼─────────────────┼─────────────────┼─────────┤
│ 半确定性内容   │ 模板填充         │ ≤10%             │ 1-3ms   │
│ • 明确指令     │ 提取意图+实体     │                 │         │
│ • 参数调整     │ + 参数+操作类型    │                 │         │
│ • 配置修改     │                  │                 │         │
├───────────────┼─────────────────┼─────────────────┼─────────┤
│ 非确定性内容   │ LLM 语义压缩      │ ≤20%（软目标）   │ 50-200ms│
│ • 模糊需求     │ 生成结构化 JSON    │                 │         │
│ • 情感表达     │ （核心语义+元信息） │                 │         │
│ • 歧义消解     │                  │                 │         │
└───────────────┴─────────────────┴─────────────────┴─────────┘
```

**实现改动**：

```python
@dataclass
class Level1Summary:
    # ... 已有字段 ...

    # 修改：从 hard constraint 改为 strategy tag
    compression_strategy: str  # RULE_DETERMINISTIC / TEMPLATE / LLM_SEMANTIC
    compression_ratio: Optional[float]  # 仅 LLM_SEMANTIC 策略下评估，非硬约束

    # 确定性内容专用字段（RULE_DETERMINISTIC 策略时填充）
    raw_content_slice: Optional[str]    # 原文切片（工具输出/日志/代码块）
    structured_extraction: Optional[dict]  # 结构化提取结果
```

内容分类检测（规则驱动，不依赖 LLM）：

```python
class ContentClassifier:
    def classify(self, turn: DialogueTurn) -> CompressionStrategy:
        # 确定性检测
        if turn.contains_tool_output():
            return RULE_DETERMINISTIC
        if turn.contains_code_block():
            return RULE_DETERMINISTIC
        if self._is_log_output(turn.response):
            return RULE_DETERMINISTIC

        # 半确定性检测
        if self._has_explicit_command(turn.user_input):
            return TEMPLATE
        if self._is_parameter_modification(turn.user_input):
            return TEMPLATE

        # 其余：LLM 语义压缩
        return LLM_SEMANTIC
```

---

### 11.5 神经符号约束

#### 11.5.1 定位

不放在融合器层，放在 **Planning-LLM 的 Prompt 层 + 输出后的 Schema Guard**：

**第一层：Prompt 硬约束注入**

```
Planning-LLM System Prompt 中动态注入:

"""
你必须遵守以下硬约束（违反将导致计划被拒绝）：

[实体约束]
- PID 必须为 1234 （来源：算法引擎提取，100% 可信）
- 工作目录: /home/user/project/

[工具约束]
- 工具 'scan_memory' 的地址参数必须为 0x 开头的十六进制数
- 工具 'read_file' 的路径参数必须在工作目录内

[计划约束]
- 步骤数不超过 5 （用户认知负载限制）
- 每个步骤必须可独立执行
"""
```

**第二层：Schema Guard（输出后即时验证）**

```python
class HardConstraintGuard:
    """在 LLM 输出后立即验证硬约束，不等待完整生成（流式检查）"""

    def validate_streaming(self, llm_output_chunk: dict) -> bool:
        # 1. 实体强制包含
        for entity in self.algorithm_result.high_confidence_entities:
            if entity.key in llm_output_chunk:
                if entity.value not in str(llm_output_chunk[entity.key]):
                    return False  # 实体值被篡改 → 拒绝

        # 2. 参数模式验证
        if 'address' in llm_output_chunk:
            if not re.match(r'^0x[0-9A-Fa-f]+$', llm_output_chunk['address']):
                return False

        return True

    def on_violation(self, violation: Violation):
        """
        违反硬约束时:
        1. 不向用户展示被拒绝的输出
        2. 重新调用 LLM，在 Prompt 中加入违规信息
        3. 如果连续 2 次违规 → 降级到算法引擎的模板计划
        4. 记录违规到 Cognitive Tree（用于 Meta-Cognitive 分析）
        """
```

---

### 11.6 BehaviorGraph 冷启动优化

#### 11.6.1 Skill 元数据驱动的冷启动

```python
class ColdStartProvider:
    """
    从 Skill 元数据中提取典型行为序列作为冷启动 prior。
    数据来源：内置 Skill、开源 Skill 仓库、在线凝练。
    """

    def get_coldstart_weight(
        self,
        from_action: str,
        to_action: str,
        skill: SkillMetadata,
    ) -> Optional[float]:
        """
        Skill 元数据中预定义的典型行为序列：

        skill: debug_program
          typical_sequence:
            - run_program
            - check_logs          → P(check_logs|run_program) = 0.70
            - analyze_stacktrace  → P(analyze|check_logs) = 0.60
            - fix_code            → P(fix|analyze) = 0.40
          alternatives:
            - check_config        → P(check_config|run_program) = 0.20
            - restart_service     → P(restart|run_program) = 0.15

        冷启动权重公式:
          w_coldstart = 0.5 × LLM_causal_prob + 0.5 × Skill_typical_weight

        动态衰减（随实际数据积累，Skill 权重逐渐降低）:
          β = min(0.4, N/50 × 0.4)          # 50次样本后达到满权重
          Skill_weight_eff = max(0, 0.5 - β)  # 随实际数据增多衰减到0
        """

    def sources(self) -> Dict[str, ColdStartSource]:
        """
        | 来源               | 获取方式                    | 适用场景         |
        |--------------------|---------------------------|-----------------|
        | 内置 Skill 元数据    | 设计时预定义                 | 所有内置 Skill   |
        | 开源 Skill 仓库      | 下载 + 解析 typical_sequence | 社区贡献 Skill   |
        | 在线凝练             | 首次完成 Skill 任务后自动提取  | 持续改进         |
        | 语义嵌入邻居         | 向量空间中相似行为的权重继承   | 无 Skill 匹配时  |
        """
```

---

### 11.7 分层存储架构

#### 11.7.1 问题

BehaviorGraph 的边权重更新频繁（每轮都可能变），图数据库的写入延迟（5-20ms）不适合热点数据。

#### 11.7.2 方案

```
┌──────────────────────────────────────────────────────────┐
│                   分层存储架构                            │
├──────────────┬──────────────────┬───────────┬────────────┤
│ 存储层        │ 数据类型           │ 读写延迟   │ 容量       │
├──────────────┼──────────────────┼───────────┼────────────┤
│ Redis        │ BehaviorGraph     │ <1ms      │ 当前会话    │
│ (内存)        │ 热点边权重          │           │ + 最近活跃   │
│              │ L1Summary (热/温)  │           │             │
│              │ 融合器状态缓存       │           │             │
├──────────────┼──────────────────┼───────────┼────────────┤
│ PostgreSQL   │ BehaviorGraph 全量  │ 1-5ms     │ 永久       │
│ (关系型)      │ Topic Tree 结构     │           │             │
│              │ L1/L2Summary       │           │             │
│              │ 用户认知画像         │           │             │
│              │ 会话元数据           │           │             │
├──────────────┼──────────────────┼───────────┼────────────┤
│ Neo4j        │ 跨主题关联链         │ 5-20ms    │ 永久       │
│ (图数据库)    │ Cognitive Tree      │           │             │
│              │ 行为语义嵌入索引      │           │             │
│              │ 跨会话模式图          │           │             │
└──────────────┴──────────────────┴───────────┴────────────┘
```

**同步策略**：
- Redis → PostgreSQL：每 30 秒批量写入（非关键路径）
- PostgreSQL → Neo4j：每 5 分钟增量同步（Meta-Cognitive/Reflective 层使用）
- 会话结束时：全量 flush

---

### 11.8 变更映射

| 章节 | 内容 | 类型 |
|------|------|------|
| §3 新增 §3.5 | 行为语义嵌入层（BehaviorSemanticEmbedding） | 新增 |
| §4.3 L1Summary | compression_ratio 从硬约束改为软目标 + compression_strategy | 修正 |
| §4.5 L1 摘要策略 | 从"LLM 生成"改为"三级自适应（规则/模板/LLM）" | 修正 |
| §5.1 训练闭环 | 新增 OutcomePredictor（轻量结果预测+价值评估） | 新增 |
| §6.3 融合器 | 新增主动矛盾消解（proactive_conflict_detection） | 新增 |
| §6.4 | 新增 Planning-LLM 神经符号约束 + Schema Guard | 新增 |
| §8.1 目录结构 | 新增 embedding/ 和 constraints/ 模块 | 新增 |
| §8.3 技术风险 | 新增泛化能力风险和存储策略 | 新增 |
| 新增 §11 | 泛化能力分析与补充设计 | 新增 |

---

## 12. v3.2：因果基地——从概率关联到结构因果

> **设计来源**：Literature Cortex v6.0 的键合图 + 范畴论 + 系统动力学 + Petri 网 + 元角色注册表
> **核心命题**：LLM 可以告诉你"A 和 B 有关"，但只有形式化因果引擎可以告诉你"A 为什么导致 B"。这两者不是替代而是互补。

---

### 12.1 问题：v3.1 的因果推断全部依赖 LLM

当前设计中的所有"因果"都是统计因果：

| 组件 | 因果来源 | 缺陷 |
|------|---------|------|
| BehaviorEdge.causal_weight | LLM推理(30%) + 历史频次(40%) | 频率 ≠ 因果，冷启动时纯依赖LLM |
| CausalChain 因果事件 | LLM 从文本推断 causal_type | 可能混淆相关性和因果性 |
| BehaviorPredictor | LLM 推理行为序列因果 | 基于模式匹配，非结构推演 |
| 融合器冲突仲裁 | FACTUAL→算法 / SEMANTIC→LLM | 没有"底层因果结构才是对的"的第三种判定 |

**根本问题**：DialogMesh 目前没有"硬因果"——基于物理/数学/逻辑定律的确定性因果推演能力。

### 12.2 方案：因果基地作为第四支柱

在 Track-0（算法）、Track-1（LLM）、Track-P（预测）之外，新增**因果基地（Causal Substrate）**作为离线预计算、在线可查询的结构因果知识源。

```
DialogMesh 的四支柱：

  Track-0             Track-1           Track-P           因果基地
  (算法引擎)          (LLM引擎)          (预测引擎)         (形式化引擎)
  确定性强            泛化性强           前瞻性强            结构因果强
  规则匹配            语义理解           行为预测            法则推导
  实体提取            意图推断           推演预加载          键合图/PN/范畴论
  "提取了什么"        "意味着什么"        "可能会怎样"        "为什么必然这样"
```

### 12.3 因果基地的核心组件

**来自 Literature Cortex v6.0 的形式化工具栈**：

#### 12.3.1 键合图元解析器（物理域因果）

处理**物理世界**的因果：热传导、力学振动、电路、流体。

```python
class BondGraphCausalEngine:
    """
    不去模拟物理世界，而是提取物理行为的因果骨架。
    
    适用于 DialogMesh 的场景：
    - 用户调试嵌入式系统（温度→电压漂移→ADC读数错误）
    - 用户分析机械故障（振动→疲劳→断裂）
    - 用户排查电路问题（热耗散→电阻漂移→信号失真）
    
    输入：用户行为描述（自然语言）
    输出：因果链骨架（source → dissipate → store → transform）
    
    不运行数值仿真（太慢），只输出因果拓扑。
    """

    def extract_causal_skeleton(self, behavior_chain: BehaviorChain) -> CausalSkeleton:
        """
        示例：
        输入行为链：运行电机 → 温度升高 → 传感器读数异常 → 触发保护停机
        
        输出因果骨架：
          [电源](source) → [电机](transform) → [热耗散](dissipate) → 
          [传感器](monitor) → [控制器](junction_sum) → [停机](sink)
        
        这个骨架不是 LLM 猜的——是键合图的功率流约束推导的。
        """
```

#### 12.3.2 Petri 网引擎（离散事件因果）

处理**离散事件系统**的因果：并发、冲突、资源竞争。

```python
class PetriNetCausalEngine:
    """
    适用于 DialogMesh 的场景：
    - 用户调试多线程程序（死锁、竞争条件）
    - 用户分析工作流（步骤依赖、资源瓶颈）
    - 用户排查 CI/CD 流水线（构建失败、队列阻塞）
    
    核心价值：Petri 网能形式化判断"这个操作序列是否必然导致死锁"，
    而不是"历史上 60% 的情况下会死锁"。
    """

    def check_deadlock_potential(self, action_sequence: List[BehaviorStep]) -> DeadlockReport:
        """
        对多步骤操作序列做可达性分析：
        - 是否存在 token 竞争导致死锁？
        - 是否存在不可达的状态？
        - 并发操作是否有冲突？
        """
```

#### 12.3.3 系统动力学引擎（反馈回路因果）

处理**含反馈回路**的因果：增长、饱和、振荡、崩溃。

```python
class SystemDynamicsCausalEngine:
    """
    适用于 DialogMesh 的场景：
    - 用户分析性能问题（流量增加→延迟增加→超时→重试→更多流量）
    - 用户讨论资源管理（内存泄漏→swap→变慢→用户抱怨→加内存→泄漏继续）
    - 用户排查级联故障
    
    核心价值：识别正/负反馈回路，预测系统行为的可能性空间。
    """

    def identify_feedback_loops(self, behavior_chain: BehaviorChain) -> List[FeedbackLoop]:
        """
        输出：
        [
            FeedbackLoop(
                type="positive",  # 正反馈：放大效应
                path=[A→B→C→A],
                characteristic="指数增长 → 边界条件 → 崩溃"
            ),
            FeedbackLoop(
                type="negative",  # 负反馈：稳态效应
                path=[D→E→F→D],
                characteristic="振荡 → 阻尼 → 收敛"
            )
        ]
        """
```

#### 12.3.4 元角色注册表（跨域因果统一）

**这是因果基地的"语言统一层"。** 四个形式化工具各有各的语言，元角色是它们的共同语义。

```python
class MetaRole(str, Enum):
    """
    跨域因果统一语义。

    键合图的元件、Petri网的place/transition、系统动力学的存量/流量、
    范畴论的函子，都映射到这个统一的7+2角色体系。
    """
    SOURCE = "source"           # 因果起源（入度=0，出度≥1）
    SINK = "sink"               # 因果终点（入度≥1，出度=0）
    STORE = "store"             # 因果累积（入度=1，出度=1，反馈环）
    DISSIPATE = "dissipate"     # 因果耗散（入度=1，出度=0或1）
    TRANSFORM = "transform"     # 因果转换（入度=1，出度=1，映射）
    MONITOR = "monitor"         # 因果感知（入度=1，出度=1，旁路）
    JUNCTION_SUM = "junction_sum"    # 因果汇聚（入度≥2，出度=1）
    JUNCTION_SPLIT = "junction_split"  # 因果分流（入度=1，出度≥2）

# 对 DialogMesh 行为链的元角色映射示例：
#
# 行为链：运行程序 → 查看日志 → 分析报错 → 修复代码 → 验证
# 元角色：  [source]   [monitor]  [transform] [transform] [sink]
#
# 行为链：启动服务 → CPU飙升 → 延迟增加 → 用户投诉 → 回滚
# 元角色：  [source]   [store]    [dissipate] [junction_sum] [sink]
```

**对融合器的关键价值**：如果两个行为链映射到相同的元角色骨架，融合器可以**确信**它们是同构的——即使 LLM 认为是"不同话题"。这种结构因果一致性是 LLM 的语义匹配无法提供的确定性。

### 12.4 因果基地的运行时定位

因果基地不做实时推理。四个形式化引擎（键合图、Petri网、系统动力学、跨域类比）都是 Heavy 操作（50-500ms）。在实时对话中不可接受。

**架构决策：离线预计算 + 在线查询**

```
┌──────────────────────────────────────────────────────────┐
│                    因果基地运行时定位                      │
├──────────────┬──────────────────┬────────────────────────┤
│ 层           │ 操作              │ 时间尺度                │
├──────────────┼──────────────────┼────────────────────────┤
│ 离线批处理    │ 行为链→元角色映射  │ 每次会话间隙/每天        │
│ (Reflective) │ CSM 跨域结构类比  │ 后台异步，不阻塞交互     │
│              │ 发现新因果模式     │                        │
│              │ 更新 structural_prior│                     │
├──────────────┼──────────────────┼────────────────────────┤
│ 在线查询      │ BehaviorGraph     │ 每轮对话，<1ms          │
│ (每轮)        │ 读取 structural_prior│                     │
│              │ 查询负知识库       │                        │
│              │ 融合器读取因果约束  │                        │
├──────────────┼──────────────────┼────────────────────────┤
│ 准实时        │ Meta-Cognitive    │ 每N轮或触发条件满足时    │
│ (Meta-Cog)   │ 发现因果骨架与     │                        │
│              │ LLM推断的矛盾      │                        │
│              │ 提交离线重新分析    │                        │
└──────────────┴──────────────────┴────────────────────────┘
```

### 12.5 因果基地在 DialogMesh 中的应用场景

#### 场景 1：BehaviorGraph 的结构因果先验

```python
# 原来的权重公式（纯统计）
w = α×LLM_causal_prob + β×freq_ratio + γ×profile_boost + (1-α-β-γ)×w_old

# 加入因果基地后
w = α×LLM_causal_prob + β×freq_ratio + γ×profile_boost + δ×structural_prior + (1-α-β-γ-δ)×w_old

# δ = 0.15 ~ 0.25（初始值，随形式化证据积累可提高）
# structural_prior 来源：
#   1.0 → 键合图/Petri网证明必然因果链
#   0.7 → 元角色骨架同构（高置信类比）
#   0.3 → 元角色部分匹配
#   0.0 → 无形式化证据，退回到纯统计
```

#### 场景 2：融合器新增 STRUCTURAL 冲突仲裁

```python
# 原来的冲突分类
FACTUAL   → 算法为准
SEMANTIC  → LLM 为准
STRATEGIC → 保留候选项

# 新增
STRUCTURAL → 因果基地为准（优先级最高）

# 示例：
# 算法说"热→传感器→故障"是一个时序链
# LLM说"热和传感器可能无关，是偶发故障"
# 键合图证明"热 → 传感器漂移 → 读数异常"是确定性的因果链
# → STRUCTURAL 冲突，因果基地胜出（即使算法和LLM都不同意）
```

#### 场景 3：负知识库（来自 Literature Cortex v6.0）

在 BehaviorGraph 中增加负知识库——但**不是一刀切的"永久禁止"**，而是三级分类 + 上下文开关 + 熔断机制。

##### 三级分类

```python
class NegativeKnowledgeLevel:
    HARD_BLOCK = "hard_block"       # 物理/数学上不可能（键合图/Petri网形式化证明）
    WARN = "warn"                   # 常态下不该做，有已知特例存在
    SOFT_DISCOURAGE = "soft"         # 统计上几乎不可能，但逻辑上不矛盾

class BehaviorNegativeKnowledge:
    """
    负知识的三层来源（按可信度排序）：

    HARD_BLOCK 来源：
    - 键合图证明物理不可能（"无功率输入→无限输出"）
    - Petri 网证明必然死锁（"两个资源形成等待环"）
    - 范畴论证明范畴不兼容（"物理域结构不能映射到完全正交的逻辑域"）
    → 行为：直接拦截，不询问。

    WARN 来源：
    - 常态约束，但存在已知特例：
      "纯水不导电" ← 高压电解是特例
      "5米要开车很荒谬" ← 但目的地是洗车，车必须到店
    - 系统动力学预测的边界风险：
      "正反馈回路，增长到边界后可能崩溃"
    → 行为：第一次拦截+展示风险说明；第二次提醒但允许；第三次+不再拦截。

    SOFT_DISCOURAGE 来源：
    - 用户连续3次纠正同一行为路径
    - 语义嵌入层发现严重语义漂移
    → 行为：降低权重但不禁止，允许用户覆盖。
    """
```

##### 上下文开关

负知识不是全局生效的——必须在特定约束空间内：

```python
class ContextualNegativeRule:
    """
    每条负知识规则带上前提条件。

    不是: water → conduct = False
    而是: IF (voltage < HIGH_VOLTAGE_THRESHOLD AND purity > 99.9%)
          THEN water → conduct = False

    不是: "5米开车" → blocked
    而是: IF (context.purpose != "洗车" AND context.has_vehicle == False)
          THEN "5米开车" → WARN "步行更方便"
    """
    condition: Callable[[Context], bool]
    level: NegativeKnowledgeLevel
    message: str  # 向用户解释的话

# 示例规则
rule_water_conduct = ContextualNegativeRule(
    condition=lambda ctx: ctx.domain != "electrochemistry",
    level=NegativeKnowledgeLevel.WARN,
    message="纯水在常温常压下几乎不导电。如果是电化学实验场景，请确认电解质条件。"
    # ← 不是说"违反物理定律"，而是说"在什么条件下这通常不行"
)
```

##### 熔断机制

```python
class NegativeKnowledgeCircuitBreaker:
    """
    防止负知识库变成死锁。
    用户坚持 → 系统学习 → 规则更新。
    """

    def check(self, action: BehaviorStep, rule: ContextualNegativeRule) -> Decision:
        times_blocked = self.get_times_blocked(action, rule)

        if rule.level == HARD_BLOCK:
            # HARD_BLOCK 不接受绕过：物理不可能
            return Decision.BLOCK

        if rule.level == WARN:
            if times_blocked == 0:
                # 第一次：拦截，但用"可能存在 X 问题"的语气
                return Decision.BLOCK_AND_WARN(
                    message=rule.message  # 不是"你错了"，而是"可能有问题"
                )
            elif times_blocked == 1:
                return Decision.WARN_BUT_ALLOW
            else:
                # 用户坚持3次 → 降级为软规则，记住这个特例
                rule.downgrade_to(NegativeKnowledgeLevel.SOFT_DISCOURAGE)
                return Decision.ALLOW_AND_LEARN  # 允许 + 记录为学习样本

        if rule.level == SOFT_DISCOURAGE:
            return Decision.ALLOW  # 不拦截，只降低了权重
```

#### 场景 4：BehaviorPredictor 的因果约束

```python
class BehaviorPredictor:
    def predict(
        self,
        current_behavior: BehaviorStep,
        behavior_history: List[BehaviorStep],
        cognitive_profile: CognitiveProfileV2,
        active_topic: TopicTreeNode_v3_1,
        available_tools: List[ToolSchema],
        causal_constraints: CausalConstraints,  # 新增：因果基地提供的硬约束
    ) -> List[Prediction]:
        """
        causal_constraints 的内容：
        - 正向约束：键合图证明"A之后必然是B" → B的概率提升
        - 负向约束：Petri网证明"A之后不可能是C" → C从预测列表中移除
        - 环路约束：系统动力学证明"D→E→D是正反馈" → 标记为高风险路径
        """
```

### 12.6 成本模型与调度

因果基地的四个形式化引擎都是 Heavy 操作，必须有成本控制（借鉴 Literature Cortex v6.0 的 BudgetScheduler）：

```python
class CausalSubstrateScheduler:
    """
    因果基地成本分级调度。

    不追求"每轮都做因果推演"——那会拖死系统。
    只在关键时机触发，并且错开执行。
    """

    # 每轮在线查询（Micro，<1ms）
    def query_structural_prior(self, from_action, to_action) -> float
    def check_negative_knowledge(self, from_action, to_action) -> bool

    # 触发条件（Heavy，50-500ms，后台异步）
    def trigger_full_analysis(self, behavior_chain) → 触发条件：
        - 用户连续 2 次纠正同一行为路径
        - 行为链长度超过 10 步（可能存在隐藏的反馈回路）
        - 融合器检测到 STRUCTURAL 级别冲突
        - Reflective 层跨会话复盘时
        - 会话结束后

    # 超时降级
    def degrade_on_timeout(self, engine, timeout_ms=500):
        # 键合图 → 只做拓扑分析，跳过数值仿真
        # Petri网 → 只做死锁检测，跳过完整可达性分析
        # 系统动力学 → 只做回路识别，跳过量化模拟
        # CSM跨域类比 → 只做结构匹配，跳过语义过滤
```

### 12.7 实施顺序

```
Phase 1（和 BehaviorGraph 同步上线）:
  ├─ 元角色注册表（纯数据结构，200行）
  ├─ 行为链→元角色映射规则（基于 action_type 匹配，100行）
  └─ structural_prior 字段加入 BehaviorEdge

Phase 2（BehaviorGraph 有数据后）:
  ├─ 键合图元解析器（处理物理域行为链）
  ├─ Petri网引擎（处理离散事件行为链）
  └─ 负知识库表设计

Phase 3（系统稳定后）:
  ├─ 系统动力学引擎（处理反馈回路）
  ├─ CSM 跨域类比（需要足够多的行为链数据）
  └─ CausalSubstrateScheduler 全量上线
```

**关键原则**：元角色层最先做——它是最低成本的统一语义，不依赖任何 Heavy 操作。行为链能映射到元角色后，structural_prior 就能提供价值。四个形式化引擎逐步接入，不急。

### 12.8 与 Literature Cortex v6.0 的对照

| Literature Cortex v6.0 | DialogMesh v3.2 中的落地 |
|---|---|
| 键合图元解析器 + 配置表 | BondGraphCausalEngine（物理域行为链因果） |
| Petri网引擎 | PetriNetCausalEngine（离散事件行为链因果） |
| 系统动力学引擎 | SystemDynamicsCausalEngine（反馈回路因果） |
| 元角色注册表（7+2角色） | MetaRole 枚举（直接复用，行为链映射） |
| CSM 三层降级链 | 离线预计算 structural_prior |
| BudgetScheduler + ActionCost | CausalSubstrateScheduler |
| 负知识库（negative_matches） | BehaviorNegativeKnowledge |
| CL2 锚点硬闸门 | 融合器 STRUCTURAL 冲突仲裁 |
| L5 decide() 优先级仲裁 | 融合器高级别冲突（STRUCTURAL > FACTUAL > SEMANTIC > STRATEGIC） |

### 12.9 关键边界

1. **因果基地不做实时推理**：所有重型操作离线运行，在线只读缓存。这是工程可行性的底线。
2. **因果基地不是替代 LLM**：它只告诉"必然的因果关系"——必然的因果关系之外的一切仍然交还给 LLM。不是竞争是互补。
3. **冷启动时因果基地提供先验而非判定**：键合图说"A→B 在物理上确定"时，给一个高 structural_prior，让 BehaviorGraph 在无数据时也能做出合理预测。
4. **因果基地的错误不致命**：如果形式化引擎做出了错误的因果判定，Meta-Cognitive 层会在跨轮验证中发现矛盾并触发重新分析。错误会被修复，不会累积。

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-07-04 | v3.1-draft | 初始草案：行为推演链 + 双层摘要 + 训练闭环 + 融合器升级 |
| 2026-07-04 | v3.1.1 | 补充：语义嵌入层 + 三级自适应摘要 + 神经符号约束 + 冷启动 + 分层存储 + 主动矛盾消解 + 轻量结果预测 |
| 2026-07-04 | v3.2 | 因果基地：键合图 + Petri网 + 系统动力学 + 元角色注册表 + 负知识库 + STRUCTURAL 冲突仲裁 + BudgetScheduler |
| 2026-07-05 | v3.2.1 | 约束补全编译器（§2.5）：五层约束系统 + 约束消解 + 稳定性评分 + 与因果基地的离线/在线协作 |