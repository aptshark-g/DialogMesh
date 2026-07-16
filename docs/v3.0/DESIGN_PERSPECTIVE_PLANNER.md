# Perspective Planner — 多空间视角工程

> 版本: v2.0 | 日期: 2026-07-15
> 状态: Draft
> 关联: DESIGN_V4_CONTEXT_ENGINEERING.md, DESIGN_CROSS_DOMAIN_CONTEXT.md, DESIGN_SEMANTIC_WORLD_MODEL.md

## 一、范式转变

### 1.1 从 Context Engineering 到 Perspective Engineering

```
Context Engineering（旧范式）:
  Query → Embedding → TopK → Context Chunks → LLM
  目标：找到相关内容（Find Relevant Chunks）

Perspective Engineering（新范式）:
  Query → Perspective → Enter a World → Choose Horizon → Observe → World View → LLM
  目标：构造适合当前问题的局部世界（Construct the Right Local World）
```

这不是检索策略的优化，是范式的转变。系统不再围绕"文本块"组织，而是围绕"世界模型"组织。ContextCompiler 最终应演化为 **World Renderer（世界渲染器）**：根据 Perspective、Horizon、SemanticPath 和 World Model，动态渲染出一个适合当前任务的局部世界视图供 LLM 观察。

### 1.2 四个空间

系统管理的信息分属四个不同空间：

```
Document Space     Concept Space      Knowledge Space     Capability Space
（物理）            （语义）            （认知）             （能力）

Heading            Concept             Belief              Skill
Paragraph          Relation            Frozen Fact         Workflow
Page               SemanticPath        Evidence Chain      Procedure
File               Cross-refs                               Constraint
Anchor             Dependencies                             Precondition
```

| 空间 | 产生方式 | 结构 | 例子 |
|------|---------|------|------|
| Document | 作者撰写 | 树 (heading hierarchy) | `DESIGN_RUNTIME.md → H2 → paragraph` |
| Concept | 系统提取+聚合 | DAG (多父归属) | `Observation ← Runtime ∩ KnowledgeRefinement` |
| Knowledge | 竞争冻结 | 图 (已证事实) | `Observation depends_on Evidence → Belief` |
| Capability | 方法定义 | 序列/图 | `Gateway Skill: Health → Metrics → Config → Done` |

**Document Tree 不是 Scale Tree。** 它是 Scale 的一个 Prior，不是唯一来源。
**Concept 不等于 Knowledge。** Concept 是 "可以怎么理解"，Knowledge 是 "系统相信是真的"。
**Capability ≠ Concept。** "Gateway" 概念描述是什么，"Gateway Skill" 描述怎么做。

### 1.3 当前缺陷

```
当前执行:
  heading_path → concept node → co_occurs edge → BFS → flat Context IR → LLM

问题:
  - DocumentSpace 被错误当作 ConceptSpace 的层级
  - ConceptGraph 只有横向 edge，没有纵向归属
  - 不知道 Knowledge 和 Capability 的存在
  - LLM 收到的始终是平面碎片
```

## 二、Information Horizon（信息视野）

### 2.1 概念

替代离散 Scale 档位（PROJECT / MODULE / COMPONENT / FUNCTION），引入连续深度控制：

```
Horizon = 从 Root 允许向下展开的层数

不是离散切换，而是深度参数。
由 token budget 反算，不写死。

Horizon=1: SemanticPath 直接子节点名 + 1 句摘要 (~200t)
Horizon=2: 子节点名 + 关键定义段落 (~500t)
Horizon=3: 孙节点概览 + 关系边 (~1200t)
Horizon=4: 叶子节点完整内容 (~3000t)
```

### 2.2 决策逻辑

```python
class HorizonCalculator:
    """意图 + token budget → 连续深度。"""

    def calculate(self, intent: Intent, token_budget: int,
                  semantic_depth: int) -> Horizon:
        base = {
            "query_overview": 2,      # "DialogMesh 是什么"
            "query_detail": 4,         # "Normalizer 怎么实现"
            "task": 3,
            "correction": 2,
            "discussion": 2,
        }.get(intent.category, 2)

        # Token budget 反算
        affordable = 1
        cumulative = 200
        for d in range(2, semantic_depth + 1):
            cumulative += 150 * d
            if cumulative <= token_budget * 0.6:
                affordable = d

        return Horizon(
            depth=min(base, affordable),
            budget=token_budget,
            strategy="structural_summary" if affordable < base else "full_content",
        )
```

## 三、SemanticPath（语义路径）

### 3.1 数据结构

```python
@dataclass
class SemanticPath:
    """概念在 Concept Space 中的层级位置。

    一个概念只有一个 SemanticPath，但可被多个 DocumentPath 引用。
    SemanticPath 形成 DAG：一个概念可以属于多个父节点。
    """
    segments: List[str]       # ["DialogMesh", "Runtime", "Observation"]
    parents: List[str]         # 父级 SemanticPath ID
    children: List[str]        # 子级 SemanticPath ID
    document_refs: List[str]   # 引用的 DocumentPath（多源）
    node_type: str             # "system" | "subsystem" | "module" | "component"


@dataclass
class DocumentPath:
    """概念在文档中的物理位置。"""
    source: str                # "DESIGN_RUNTIME.md"
    heading_chain: List[str]   # ["Runtime", "Observation Compiler", "Normalizer"]
    line_range: Tuple[int,int]
    semantic_ref: str          # 对应的 SemanticPath ID
```

### 3.2 和 heading_path 的关系

```
heading_path 只能来自作者 → 不同文档的同一个概念在不同位置
SemanticPath 来自系统   → 跨文档收敛到同一个语义位置

例:
  DESIGN_RUNTIME.md heading:    Runtime → Observation → Normalizer
  DESIGN_OBSERVATION.md heading: Knowledge Refinement → Observation → Normalizer

  SemanticPath:  DialogMesh → Runtime → Knowledge Refinement → Observation → Normalizer
                 ↑ DAG 多父
```

**构建：Phase 1 从 heading_path 生成候选 → Phase 2 横切聚合 → Phase 3 人工覆盖校正。**

### 3.3 用途

```
查询时:
  优先使用 SemanticPath 做层级导航
  SemanticPath 未建立时，fallback 到 DocumentPath 做近似
  两者不一致时，以 SemanticPath 为准
```

## 四、Perspective（视角）— 多维观察策略

### 4.1 World 只是 Perspective 的一个维度

Perspective 不是简单的 World Selection，而是完整的**观察策略**：

```
Perspective = {
    observation:  "architecture" | "execution" | "engineering" | "evolution",
    horizon:      Horizon(depth=3),
    target:       ["Runtime"],          # 观察目标
    domains:      {"K": 0.6, "C": 0.2}, # 域分配（降到执行参数）
    world:        "design",             # World 只是其中一个维度
}
```

同一个问题 "Runtime 怎么工作的？" 可以有多种 Perspective：

| Perspective | 观察方式 | 返回结构 |
|-------------|---------|---------|
| Architecture | 逐层展开 | Runtime → Observation → Hypothesis → Knowledge |
| Execution | 沿执行流 | Event → Pipeline → Worker → Scheduler |
| Engineering | 沿代码组织 | Runtime → Module → File → Code |
| Evolution | 沿设计历史 | 为什么这么设计 → 历史版本 → 替代方案 |

### 4.2 PerspectivePlanner 接口

```python
@dataclass
class Perspective:
    """一次 View Request 的完整观察策略。"""
    strategy: str              # "architecture" | "execution" | "engineering" | "evolution"
    horizon: Horizon
    target: List[str]          # 锚点概念 → 定位 SemanticPath
    world: str                 # "design" | "code" | "knowledge"
    domains: Dict[str, float]  # Domain 分配（降级为 Perspective 的输出，非输入）
    token_budget: int


class PerspectivePlanner:
    """意图 → Perspective 的决策层。

    三层决策:
      1. Observation Strategy: 用什么方式观察？
      2. Horizon: 观察多深？
      3. Domain 分配: 从 Perspective 自动生成
    """

    def plan(self, intent: Intent, context: ConversationContext,
             token_budget: int) -> Perspective:
        return Perspective(
            strategy=self._select_strategy(intent, context),
            horizon=HorizonCalculator().calculate(intent, token_budget),
            target=self._extract_anchors(intent.text),
            world=self._select_world(intent, context),
            domains=self._derive_domains(intent),  # 从 Perspective 推导，不是独立决策
            token_budget=token_budget,
        )

    def _select_strategy(self, intent, context) -> str:
        """选择观察策略。根据意图语义决定。"""
        text = intent.text.lower()
        if any(kw in text for kw in ["架构", "设计", "整体", "是什么"]):
            return "architecture"
        if any(kw in text for kw in ["怎么跑", "流程", "执行", "pipeline"]):
            return "execution"
        if any(kw in text for kw in ["代码", "函数", "class", "实现"]):
            return "engineering"
        if any(kw in text for kw in ["为什么", "历史", "演变", "之前"]):
            return "evolution"
        return "architecture"  # default
```

### 4.3 DomainSelector 退化

```
旧: DomainSelector 独立规划 "C=60%, K=25%, E=15%"
新: Perspective 已决定怎么看 → Domain 分配从 Perspective 自动生成
    DomainSelector 只做微调和预算执行，不再参与规划决策
    以后可能完全退化
```

## 五、View Manager（视图管理器）

### 5.1 定位：不是 Query→Result，是 Google Maps 的 Camera

```
旧 ScaleManager:
  locate() → LCA → expand_children → 返回结果
  ↑ 每次从头查询

新 View Manager:
  维护一个持久 View（相机位置）
  zoom_in(concept)  → 下潜到子节点
  zoom_out()        → 上升到父节点
  pan_to(sibling)   → 横向移动到同级概念
  reframe(query)    → 重新定位相机
  ↑ 在世界里持续移动
```

### 5.2 接口

```python
@dataclass
class View:
    """当前的观察窗口。"""
    path: SemanticPath          # 相机所在的语义位置
    horizon: Horizon            # 当前展开深度
    visible_nodes: List[str]    # 当前可见的概念节点
    content: Dict[str, str]     # node_name → rendered summary/content


class ViewManager:
    """在世界模型中维护观察窗口。

    类比 Google Maps:
      SemanticPath = 地图坐标
      Horizon = 缩放级别
      zoom_in/out = 滚轮
      pan = 拖拽
      reframe = 搜索新地点
    """

    def __init__(self, graph: ConceptGraph, semantic_index: SemanticIndex):
        self._graph = graph
        self._semantic = semantic_index
        self._current: Optional[View] = None

    def reframe(self, perspective: Perspective) -> View:
        """根据 Perspective 设定初始相机位置。"""
        path = self._semantic.locate(perspective.target[0])
        self._current = View(
            path=path,
            horizon=perspective.horizon,
            visible_nodes=self._render_children(path, perspective.horizon),
            content=self._render_content(path, perspective.horizon),
        )
        return self._current

    def zoom_in(self, target_concept: str) -> View:
        """下潜一级：以 target 为新根，展开其子节点。"""
        child_path = self._semantic.descend(self._current.path, target_concept)
        self._current = View(
            path=child_path,
            horizon=Horizon(depth=self._current.horizon.depth),
            visible_nodes=self._render_children(child_path, self._current.horizon),
            content=self._render_content(child_path, self._current.horizon),
        )
        return self._current

    def zoom_out(self) -> View:
        """上升到父节点，展开同级。"""
        parent = self._semantic.ascend(self._current.path)
        self._current = View(
            path=parent,
            horizon=Horizon(depth=self._current.horizon.depth),
            visible_nodes=self._render_children(parent, self._current.horizon),
            content=self._render_content(parent, self._current.horizon),
        )
        return self._current

    @property
    def view(self) -> Optional[View]:
        return self._current
```

## 六、Capability Space 预留

### 6.1 定义

Capability 回答 "怎么做"——与 Concept（回答 "是什么"）互补。不是第四个 Graph，是 **语义路径上的叶子层执行体**。

```python
@dataclass
class Capability:
    """一个可执行的能力单元。"""
    capability_id: str
    semantic_path: SemanticPath   # 对应的概念位置
    type: str                     # "skill" | "workflow" | "procedure" | "constraint"
    steps: List[CapabilityStep]   # 执行步骤
    preconditions: List[str]
    postconditions: List[str]
    triggers: List[str]           # 什么事件触发此能力


class CapabilitySpace:
    """能力空间 — 暂不实现，接口预留。"""

    def query(self, concept: str) -> List[Capability]:
        """给定一个概念，返回其关联的能力。"Gateway" → GatewaySkill"""
        ...

    def bind(self, concept_id: str, capability: Capability):
        """将能力绑定到概念节点上。"""
        ...

    def execute(self, capability_id: str, context: dict) -> dict:
        """执行一个能力（未来 OpenClaw 集成点）。"""
        ...
```

### 6.2 和现有 Skill Layer 的关系

```
当前:  SkillSource 是独立 ContextSource，和其他 source 并列
未来:  Skill 不是另一个 Source，而是 Conceptual Hierarchy 中叶子节点的执行面
       
       SemanticPath:  DialogMesh → Runtime → Gateway
                          ↓                       ↓
                       Concept               Capability
                       (是什么)              (GatewaySkill: health→metrics→config→done)
```

## 七、Knowledge Space 暂缓

当前 Knowledge 还是 Observation → Hypothesis → Knowledge 的竞争机制。

```
现在不建独立的 KnowledgeSpace。
等 Perspective + SemanticPath 跑通后，再判断：
  Knowledge 是独立空间？
  还是 ConceptGraph 的一个投影视图（belief ＞ threshold 的节点）？
到那时再决定。
```

## 八、数据流（完整）

```
用户: "Runtime 怎么工作的？"

1. PerspectivePlanner.plan(intent, context, budget=1800)
   → strategy="architecture"
   → horizon=Horizon(depth=3)
   → target=["Runtime"]
   → domains={"K": 0.6, "C": 0.2, "E": 0.2}（自动推导）

2. ViewManager.reframe(perspective)
   → SemanticPath.locate("Runtime") → ["DialogMesh", "Runtime"]
   → render_children at depth=3:
       depth=1: ["Runtime", "Knowledge", "Engineering", "Planning", "Infrastructure"]
       depth=2: ["ObservationCompiler", "HypothesisEngine", "KnowledgePipeline"]
       depth=3: ["Normalizer", "BeliefUpdater", "DecayEngine"]
   → render_content: 浅层摘要, 深层完整 paragraph

3. ContentIndex.scale_aware_query(perspective, view)
   → 按 view.visible_nodes 检索
   → 按 horizon.depth 控制粒度

4. ContextCompiler.compile()
   → Context IR with scale-aware structure:
       [LEVEL 1] Runtime, Knowledge, Engineering, Planning
       [LEVEL 2] ObservationCompiler: "将原始事件转化为结构化观察..."
       [LEVEL 3] Normalizer → depends_on → RawInput

5. LLM
   → "Runtime 子系统包含 ObservationCompiler、HypothesisEngine、
      KnowledgePipeline。ObservationCompiler 负责..."
   → 有整体，有细节，层级清楚
```

## 九、实现路线

### Phase 1: SemanticPath 构建（不改管线）
- 88 篇文档 heading_path → 候选 DocumentPath
- 横切聚合为 SemanticPath DAG
- 在 ConceptGraph 节点上标注 semantic_parent edge
- 验证：`SemanticPath.locate("Runtime")` 返回层级结构

### Phase 2: ViewManager（不改管线）
- 实现 ViewManager.reframe/zoom_in/zoom_out
- ContentIndex 新增 `scale_aware_query(view)`
- 验证：同一问题在 horizon=1 和 horizon=3 下返回不同粒度

### Phase 3: PerspectivePlanner 集成（管线改动）
- PerspectivePlanner 插入 ContextCompiler 之前
- DomainSelector 接收 Perspective 作为 prior
- ViewManager 持久 View，跨轮可 zoom
- 验证：同一问题在 architecture vs execution 策略下不同输出

### Phase 4: Capability Space 接口
- 定义接口，不做实现
- 与 Skill Layer 的绑定点

### Phase 5: Perspective 策略扩展
- World 注册表：design / code / knowledge / conversation
- Evolution Perspective（设计历史 + 替代方案）
- Token budget → Horizon 自动反算
