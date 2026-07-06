# DialogMesh BehaviorGraph --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-BEHAVIOR-GRAPH-003  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: `DESIGN_V3_3_ALGORITHM.md` S3（BehaviorGraph）  
> **依赖模块**: `ENGINEERING_V3_3_BEHAVIOR_EMBEDDING.md`（语义邻居查询）、`ENGINEERING_COGNITIVE_PROFILE_V2.md`（画像增强）  
> **前置算法**: v3.3 算法设计 S3 — EMA 权重更新 + 快速纠正通道 + 稀疏性处理链  
> **原则**: BehaviorGraph 是行为因果关系的纯存储 + 权重引擎。不在此模块中做预测或决策——只做记录、统计、加权。  

---

## 1. 文档目标与范围

### 1.1 目标

为 BehaviorGraph 提供完整的工程实现规范，覆盖：
- 带标签有向加权图的数据结构设计
- 节点（BehaviorStep）的创建、更新、裁剪
- 边（BehaviorEdge）的 EMA 权重更新算法
- 快速纠正通道的实现
- 稀疏性处理链：语义邻居 -> LLM -> 种子 -> 均匀分布
- 冷启动种子的维护与自动废弃
- 轻量因果发现（LightweightCausalDiscovery）的触发逻辑
- 图裁剪策略（不活跃节点清理）
- 与 TopicTreeNode 的集成协议
- 测试策略与覆盖要求

### 1.2 非目标

- 用户行为预测 -> 见 BehaviorPredictor 工程文档
- 语义邻居查询（精确/语义/退避）-> 见行为嵌入层工程文档
- 融合器中的冲突仲裁 -> 见融合器工程文档
- 因果基地元角色映射 -> 见因果基地工程文档
- 反馈奖励计算 -> 见 BehaviorRewarder 工程文档

### 1.3 边界

| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | BehaviorStep 序列 + 用户纠正事件 | 原始用户输入 |
| 输出 | 边权重（用于预测）+ 统计信息 | 预测结果 |
| 职责 | 记录 + 统计 + EMA 加权 | 推理、预测、决策 |
| 异常 | 权重计算失败 -> 保持旧权重 | 不向上传播错误 |

---

## 2. 架构总览

### 2.1 处理管线位置

```
编译器 -> 行为嵌入层 -> [BehaviorGraph] -> BehaviorPredictor -> 融合器
                          |  A
                          v  |
                     BehaviorRewarder
                          |
                          v
                     Cognitive Tree (TopicTreeNode 引用)
```

BehaviorGraph 位于行为嵌入层之后、预测器之前，同时从奖励器接收反馈来更新边权重。

### 2.2 内部架构

```
BehaviorGraph (核心类)
  |-- GraphStore: dict[str, BehaviorNode]    # 节点存储 (step_id -> node)
  |-- EdgeStore: dict[str, BehaviorEdge]     # 边存储 (edge_key -> edge)
  |-- ColdStartSeeds: list[SeedPair]          # 冷启动种子
  |
  |-- add_step()        # 添加行为节点
  |-- record_edge()     # 记录行为边 + EMA 权重更新
  |-- get_weight()      # 查询边权重 (调用 ThreeTierWeightQuery)
  |-- fast_correct()    # 快速纠正通道
  |-- prune_inactive()  # 裁剪不活跃节点
  |-- check_trigger()   # 触发条件检查 (因果发现 / 种子废弃 / 裁剪)
  v
LightweightCausalDiscovery (轻量因果发现)
  |-- discover(sample_count > 100 & structural_prior == 0)
  |-- 输出: structural_prior 建议值
```

### 2.3 文件结构

```
core/agent/v3_2/behavior_graph/
  __init__.py
  models.py              # BehaviorStep, BehaviorEdge, ColdStartSeed
  graph_store.py         # BehaviorGraph 核心类
  weight_updater.py      # EMA 权重更新器
  fast_correction.py     # 快速纠正通道
  cold_start.py          # 冷启动种子管理
  pruning.py             # 图裁剪
  causal_discovery.py    # LightweightCausalDiscovery
  statistics.py          # 统计与诊断
```

---

## 3. 数据模型 (models.py)

### 3.1 BehaviorStep（节点）

```python
@dataclass
class BehaviorStep:
    """行为图中的一个节点"""
    step_id: str                    # 全局唯一 ID
    action_summary: str             # 行为摘要（如 "运行程序"）
    action_type: str                # 行为类型（TOOL_EXEC, CODE_RUN, ...）
    entities: dict[str, str] = field(default_factory=dict)   # 提取的实体
    result: str | None = None       # 行为结果（success/failure/None）
    timestamp: float = 0.0          # 时间戳
    metadata: dict = field(default_factory=dict)  # 扩展字段

    @property
    def edge_key(self) -> str:
        return f"{self.action_type}:{self.action_summary}"

    def to_dict(self) -> dict:
        return asdict(self)
```

### 3.2 BehaviorEdge（边）

```python
@dataclass
class BehaviorEdge:
    """行为图中的一条有向边"""
    edge_id: str                     # 全局唯一 ID
    from_step_id: str                # 源节点 ID
    to_step_id: str                  # 目标节点 ID

    # 权重核心
    weight: float = 0.5              # 当前权重 [0,1]
    llm_causal_prob: float = 0.0     # LLM 因果概率（α项）
    freq_ratio: float = 0.0          # 频率比（β项）
    profile_boost: float = 0.0       # 画像增强（γ项）[0,0.3]
    structural_prior: float = 0.0    # 结构先验（δ项）[0,0.7]

    # 统计
    sample_count: int = 0            # 总出现次数
    success_count: int = 0           # 成功次数
    failure_count: int = 0           # 失败次数
    correction_count: int = 0        # 用户纠正次数
    last_updated: float = 0.0        # 最后更新时间

    # 状态
    is_stable: bool = True           # 是否稳定边
    is_deprecated: bool = False      # 是否已废弃
    correction_mode: bool = False    # 是否在快速纠正模式

    @property
    def edge_key(self) -> str:
        return f"{self.from_step_id}->{self.to_step_id}"

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def instability_ratio(self) -> float:
        return self.correction_count / max(self.sample_count, 1)

    def record_observation(self, success: bool, correction: bool = False):
        self.sample_count += 1
        if success: self.success_count += 1
        else: self.failure_count += 1
        if correction: self.correction_count += 1
        self.last_updated = time.time()
```

### 3.3 ColdStartSeed

```python
@dataclass
class ColdStartSeed:
    """冷启动种子行为对"""
    from_summary: str        # 源行为摘要
    to_summary: str          # 目标行为摘要
    from_type: str           # 源行为类型
    to_type: str             # 目标行为类型
    initial_weight: float    # 初始权重 [0,1]
    sample_count: int = 0    # 被实际数据替代的次数
    is_deprecated: bool = False
    created_at: float = 0.0

    @property
    def edge_key(self) -> str:
        return f"seed:{self.from_summary}->{self.to_summary}"

    def is_usable(self) -> bool:
        return not self.is_deprecated and self.sample_count < 10
```

### 3.4 关键统计量

```python
@dataclass
class GraphStatistics:
    """图统计信息"""
    node_count: int = 0
    edge_count: int = 0
    seed_count: int = 0
    total_samples: int = 0
    avg_weight: float = 0.0
    unstable_edge_count: int = 0
    deprecated_seed_count: int = 0
    last_prune_time: float = 0.0
    last_discovery_time: float = 0.0
```

---

## 4. BehaviorGraph 核心 (graph_store.py)

### 4.1 职责

作为带标签有向加权图的中央存储，管理节点和边的 CRUD。

### 4.2 接口

```python
class BehaviorGraph:
    """行为图核心：带标签有向加权图"""

    def __init__(
        self,
        weight_updater=None,
        cold_start_mgr=None,
        weight_query=None,
        config=None
    ):
        self.nodes: dict[str, BehaviorStep] = {}
        self.edges: dict[str, BehaviorEdge] = {}
        self.weight_updater = weight_updater or WeightUpdater()
        self.cold_start = cold_start_mgr or ColdStartManager()
        self.weight_query = weight_query  # ThreeTierWeightQuery
        self.config = config or {}
        self.stats = GraphStatistics()

    def add_step(self, step: BehaviorStep) -> str:
        """添加行为节点，返回 step_id"""
        if step.step_id in self.nodes:
            return step.step_id
        self.nodes[step.step_id] = step
        self.stats.node_count = len(self.nodes)
        return step.step_id

    def get_step(self, step_id: str) -> BehaviorStep | None:
        return self.nodes.get(step_id)

    def record_edge(
        self, from_step: BehaviorStep, to_step: BehaviorStep,
        success: bool = True, correction: bool = False
    ) -> str:
        """记录行为对并更新边权重"""
        # 确保节点存在
        from_id = self.add_step(from_step)
        to_id = self.add_step(to_step)
        edge_key = f"{from_id}->{to_id}"

        # 创建或获取边
        if edge_key not in self.edges:
            self.edges[edge_key] = BehaviorEdge(
                edge_id=edge_key, from_step_id=from_id, to_step_id=to_id
            )
        edge = self.edges[edge_key]
        edge.record_observation(success, correction)

        # EMA 权重更新
        new_weight = self.weight_updater.update(edge)
        edge.weight = new_weight

        # 统计
        self.stats.edge_count = len(self.edges)
        self.stats.total_samples += 1
        if edge.instability_ratio > 0.5:
            self.stats.unstable_edge_count += 1

        return edge_key

    async def get_weight(
        self, from_summary: str, to_summary: str,
        from_type: str, to_type: str
    ) -> float | None:
        """查询边权重（三层递进）"""
        if self.weight_query:
            result = await self.weight_query.query(from_summary, to_summary, from_type, to_type)
            if result.has_result:
                return result.avg_weight
        # 退避: 冷启动种子
        seed_w = self.cold_start.get_weight(from_summary, to_summary)
        if seed_w is not None:
            return seed_w
        # 最终退避: None -> BehaviorPredictor
        return None

    def get_edge_weight(self, from_summary: str, to_summary: str) -> float | None:
        """精确匹配：在边存储中直接查找"""
        for edge in self.edges.values():
            from_step = self.nodes.get(edge.from_step_id)
            to_step = self.nodes.get(edge.to_step_id)
            if from_step and to_step:
                if from_step.action_summary == from_summary and to_step.action_summary == to_summary:
                    return edge.weight
        return None

    def get_edge_weight_by_key(self, edge_key: str) -> float | None:
        edge = self.edges.get(edge_key)
        return edge.weight if edge else None

    def get_statistics(self) -> GraphStatistics:
        return self.stats
```

---

## 5. 权重更新 (weight_updater.py)

### 5.1 职责

实现 EMA（指数移动平均）+ 增量修正的四项加权公式。

### 5.2 算法

```
新权重 = alpha * LLM因果概率 + beta * 频率比 + gamma * 画像增强 + delta * 结构先验 + (1-alpha-beta-gamma-delta) * 旧权重
```

### 5.3 实现

```python
class WeightUpdater:
    """EMA 权重更新器"""

    ALPHA = 0.25   # LLM 因果概率权重
    BETA = 0.30    # 频率比权重
    GAMMA = 0.05   # 画像增强权重
    DELTA = 0.05   # 结构先验权重

    def __init__(self, alpha=None, beta=None, gamma=None, delta=None):
        self.alpha = alpha or self.ALPHA
        self.beta = beta or self.BETA
        self.gamma = gamma or self.GAMMA
        self.delta = delta or self.DELTA
        self.ema_remainder = 1.0 - self.alpha - self.beta - self.gamma - self.delta

    def update(self, edge: BehaviorEdge, llm_prob: float | None = None) -> float:
        """
        计算新权重。
        如果边处于快速纠正模式，跳过 EMA 直接降低权重。
        """
        if edge.correction_mode:
            return self._fast_correction_weight(edge)

        llm = llm_prob if llm_prob is not None else edge.llm_causal_prob
        freq = edge.freq_ratio
        prof = edge.profile_boost
        struct = edge.structural_prior
        old = edge.weight

        new_w = (self.alpha * llm + self.beta * freq + self.gamma * prof + self.delta * struct + self.ema_remainder * old)
        new_w = max(0.0, min(1.0, new_w))
        return new_w

    def update_freq_ratio(self, edge: BehaviorEdge) -> float:
        """更新频率比 = sample_count / (sample_count + correction_count)"""
        denom = edge.sample_count + edge.correction_count
        edge.freq_ratio = edge.sample_count / denom if denom > 0 else 0.0
        return edge.freq_ratio

    def update_profile_boost(self, edge: BehaviorEdge, match_score: float) -> float:
        """更新画像增强（上限 0.3）"""
        edge.profile_boost = min(0.3, match_score)
        return edge.profile_boost

    def update_structural_prior(self, edge: BehaviorEdge, prior: float) -> float:
        """更新结构先验（上限 0.7）"""
        edge.structural_prior = min(0.7, prior)
        return edge.structural_prior

    def _fast_correction_weight(self, edge: BehaviorEdge) -> float:
        """快速纠正模式：直接设置为 0.3 * 旧权重"""
        return max(0.0, 0.3 * edge.weight)

    def reconfigure(self, alpha, beta, gamma, delta):
        self.alpha = alpha; self.beta = beta; self.gamma = gamma; self.delta = delta
        self.ema_remainder = 1.0 - alpha - beta - gamma - delta
```

### 5.4 数学性质

| 场景 | alpha | beta | gamma | delta | 余量 | 收敛速度 |
|------|-------|------|-------|-------|------|---------|
| 默认 (初期) | 0.25 | 0.30 | 0.05 | 0.05 | 0.35 | 温和 |
| 高 LLM 信任 | 0.40 | 0.20 | 0.05 | 0.05 | 0.30 | 中 |
| 高数据信任 | 0.15 | 0.45 | 0.05 | 0.05 | 0.30 | 慢（平滑）|
| 高结构信任 | 0.20 | 0.25 | 0.05 | 0.20 | 0.30 | 中 |

---

## 6. 快速纠正通道 (fast_correction.py)

### 6.1 职责

当同一行为对连续被用户纠正 2 次以上时，跳过 EMA 平滑直接大幅降低权重。

### 6.2 实现

```python
class FastCorrectionDetector:
    """快速纠正通道检测器"""

    CORRECTION_THRESHOLD = 2  # 连续纠正常
    CORRECTION_WINDOW = 10     # 检测窗口（最近 N 次观测）

    def __init__(self, graph: BehaviorGraph):
        self.graph = graph
        self._correction_log: dict[str, list[bool]] = {}  # edge_key -> [True/False]

    def record_observation(self, edge_key: str, is_correction: bool):
        """记录一次观测"""
        if edge_key not in self._correction_log:
            self._correction_log[edge_key] = []
        log = self._correction_log[edge_key]
        log.append(is_correction)
        # 只保留最近 CORRECTION_WINDOW 条
        if len(log) > self.CORRECTION_WINDOW:
            log.pop(0)

    def is_fast_correction_needed(self, edge_key: str) -> bool:
        """检查是否需要触发快速纠正"""
        log = self._correction_log.get(edge_key, [])
        if len(log) < self.CORRECTION_THRESHOLD:
            return False
        # 最近 CORRECTION_THRESHOLD 条是否全是纠正
        recent = log[-self.CORRECTION_THRESHOLD:]
        return all(recent)

    def apply_fast_correction(
        self, edge_key: str,
        alternative_from: str = None,
        alternative_to: str = None
    ):
        """
        触发快速纠正。
        有替代行为: 设置权重 0.5 * 替代行为的合理值
        无替代行为: 设置权重 0.3 * 旧权重
        """
        edge = self.graph.edges.get(edge_key)
        if not edge:
            return
        edge.correction_mode = True
        # WeightUpdater._fast_correction_weight 会在下次 update 时使用

    def release_correction(self, edge_key: str):
        """由 Meta-Cognitive 调用，恢复慢调整"""
        edge = self.graph.edges.get(edge_key)
        if edge:
            edge.correction_mode = False
        if edge_key in self._correction_log:
            self._correction_log[edge_key] = []
```

### 6.3 纠正信号来源

1. **显式纠正**: 用户说"不是这样"、"不对"、"换一个" -> 从 IntentParser/CognitiveTree 检测
2. **行为回退**: 用户执行 A->B->A（刚做的又撤销了） -> 自动标记为纠正
3. **连续失败**: A->B 执行了 3 次都是 failure -> 视为隐式纠正信号

---

## 7. 稀疏性处理链

### 7.1 四层递进

当 `get_weight()` 在图中找不到精确匹配时：

```
第1层: 语义邻居查询 (ThreeTierWeightQuery)
   |-- cosine > 0.6 -> 加权平均邻居权重
   |-- 无邻居 ->
   v
第2层: LLM 因果概率 (BehaviorPredictor.causal_prob)
   |-- LLM 可用 -> 返回 LLM 估计值
   |-- LLM 不可用 ->
   v
第3层: 冷启动种子 (ColdStartManager.get_weight)
   |-- 种子匹配 -> 返回种子初始权重
   |-- 无种子匹配 ->
   v
第4层: 均匀分布 (返回 0.5)
   |-- 标记 unknown_pair = True
```

### 7.2 BehaviorGraph.get_weight 中的实现

已在 §4.2 中实现：`get_weight()` 方法内嵌了三层递进逻辑。
第一层（语义邻居）由 ThreeTierWeightQuery 完成，第二层由 BehaviorPredictor 完成，
第三层由 ColdStartManager 完成，第四层返回 None 由调用方处理。

---

## 8. 冷启动种子管理 (cold_start.py)

### 8.1 职责

管理 <15 个手工定义的行为对种子，在新系统无数据时提供初始权重。每 50 轮触发 Reflective 检查。

### 8.2 实现

```python
class ColdStartManager:
    """冷启动种子管理"""

    MAX_SEEDS = 15
    DEPRECATION_CHECK_INTERVAL = 50  # 每 50 轮检查一次
    SAMPLE_THRESHOLD = 10            # 超过 10 次实际数据 -> 替代种子

    def __init__(self):
        self.seeds: list[ColdStartSeed] = []
        self.turn_count = 0

    def load_default_seeds(self):
        """加载默认冷启动种子 (<15 个)"""
        seeds = [
            ColdStartSeed("执行", "查看结果", "TOOL_EXEC", "LOG_CHECK", 0.7),
            ColdStartSeed("查看日志", "分析错误", "LOG_CHECK", "ENTITY_ANALYZE", 0.8),
            ColdStartSeed("分析错误", "修改代码", "ENTITY_ANALYZE", "CODE_RUN", 0.7),
            ColdStartSeed("修改代码", "运行测试", "CODE_RUN", "CODE_RUN", 0.8),
            ColdStartSeed("运行测试", "查看结果", "CODE_RUN", "LOG_CHECK", 0.9),
            ColdStartSeed("搜索文档", "查看结果", "EXPLORATION", "LOG_CHECK", 0.6),
            ColdStartSeed("配置环境", "运行程序", "CONFIG_MODIFY", "TOOL_EXEC", 0.7),
            ColdStartSeed("查看结果", "修改代码", "LOG_CHECK", "CODE_RUN", 0.6),
            ColdStartSeed("查看结果", "分析错误", "LOG_CHECK", "ENTITY_ANALYZE", 0.5),
            ColdStartSeed("监控指标", "查看日志", "LOG_CHECK", "LOG_CHECK", 0.6),
        ]
        self.seeds = seeds[:self.MAX_SEEDS]

    def get_weight(self, from_summary: str, to_summary: str) -> float | None:
        for seed in self.seeds:
            if seed.is_usable() and seed.from_summary == from_summary and seed.to_summary == to_summary:
                return seed.initial_weight
        return None

    def on_turn_completed(self):
        """每轮调用，检查是否需要触发种子废弃"""
        self.turn_count += 1
        if self.turn_count % self.DEPRECATION_CHECK_INTERVAL == 0:
            self._check_deprecation()

    def _check_deprecation(self):
        """Reflective 检查: 种子 sample_count >= 10 -> 标记为 deprecated"""
        for seed in self.seeds:
            if not seed.is_deprecated and seed.sample_count >= self.SAMPLE_THRESHOLD:
                seed.is_deprecated = True

    def mark_seed_used(self, from_summary: str, to_summary: str):
        """当种子被实际数据替代时调用"""
        for seed in self.seeds:
            if seed.from_summary == from_summary and seed.to_summary == to_summary:
                seed.sample_count += 1

    def get_active_seeds(self) -> list[ColdStartSeed]:
        return [s for s in self.seeds if s.is_usable()]
```

---

## 9. 图裁剪 (pruning.py)

### 9.1 职责

当图节点数超过 10000 时，触发不活跃节点裁剪（30 天未激活的叶子节点）。

### 9.2 实现

```python
class GraphPruner:
    """图裁剪：管理节点生命周期"""

    MAX_NODES = 10000
    INACTIVE_DAYS = 30
    LEAF_ONLY = True  # 只裁剪叶子节点（出度为 0）

    def __init__(self, graph: BehaviorGraph):
        self.graph = graph
        self.last_prune: float = 0

    def should_prune(self) -> bool:
        return len(self.graph.nodes) >= self.MAX_NODES

    def prune(self) -> int:
        """执行裁剪，返回删除的节点数"""
        if not self.should_prune():
            return 0

        now = time.time()
        cutoff = now - (self.INACTIVE_DAYS * 86400)
        to_delete = []

        for step_id, step in self.graph.nodes.items():
            if self._is_inactive(step, cutoff) and self._is_leaf(step_id):
                to_delete.append(step_id)

        for step_id in to_delete:
            # 同时删除相关的边
            edge_keys = [
                k for k, e in self.graph.edges.items()
                if e.from_step_id == step_id or e.to_step_id == step_id
            ]
            for k in edge_keys:
                del self.graph.edges[k]
            del self.graph.nodes[step_id]

        self.last_prune = now
        self.graph.stats.last_prune_time = now
        return len(to_delete)

    def _is_inactive(self, step: BehaviorStep, cutoff: float) -> bool:
        return step.timestamp < cutoff

    def _is_leaf(self, step_id: str) -> bool:
        """出度为 0 -> 叶子节点"""
        return not any(e.from_step_id == step_id for e in self.graph.edges.values())
```

---
### 9.3 级联标记协议 (Orphaned Marking)

prune() 删除节点时, 调用方(Topic Tree Manager)需同步处理脏引用:

prune() 返回值改为 tuple[int, list[str]]
- 第一项: 删除节点数 (不变)
- 第二项: 被删除的 step_id 列表 (新增)

TopicTreeNode orphaned 规则:
- BehaviorGraph 删除 N -> 所有引用 N 的 TopicTreeNode 标记 orphaned
- orphaned 节点不参与权重计算, 保留在拓扑可视化中
- 关联链和因果链不受影响
- orphaned 是软删除, 不删除引用记录

---

## 10. 轻量因果发现 (causal_discovery.py)

### 10.1 职责

当一条边的 `sample_count > 100` 且 `structural_prior = 0` 时，触发轻量因果发现。

### 10.2 实现

```python
class LightweightCausalDiscovery:
    """轻量因果发现"""

    MIN_SAMPLES = 100

    def __init__(self, graph: BehaviorGraph):
        self.graph = graph
        self.last_run = 0.0

    def check_trigger(self) -> list[str]:
        """返回需要触发因果发现的边 key 列表"""
        triggered = []
        for edge_key, edge in self.graph.edges.items():
            if edge.sample_count >= self.MIN_SAMPLES and edge.structural_prior == 0.0:
                triggered.append(edge_key)
        return triggered

    async def discover(self, edge_key: str) -> float | None:
        """
        对单条边执行轻量因果分析。
        分析: 检查该边的统计模式是否符合因果关系。
        输出: structural_prior 建议值或 None。
        """
        edge = self.graph.edges.get(edge_key)
        if not edge:
            return None

        # 基于统计模式估计: 高成功率 + 低纠正率 -> 可能是因果
        success_rate = edge.success_rate
        correction_rate = edge.instability_ratio

        if success_rate > 0.8 and correction_rate < 0.1:
            return 0.3  # 中等因果置信
        elif success_rate > 0.6 and correction_rate < 0.2:
            return 0.2  # 弱因果置信
        else:
            return None  # 不采用

    async def run_discovery(self) -> dict[str, float]:
        """触发所有符合条件的边的因果发现"""
        results = {}
        for edge_key in self.check_trigger():
            prior = await self.discover(edge_key)
            if prior is not None:
                edge = self.graph.edges[edge_key]
                self.graph.weight_updater.update_structural_prior(edge, prior)
                results[edge_key] = prior
        self.last_run = time.time()
        self.graph.stats.last_discovery_time = self.last_run
        return results
```

---

## 11. 与 TopicTreeNode 的集成

### 11.1 集成原则

"TopicTreeNode 只存储行为链的拓扑结构（节点+边 ID），BehaviorGraph 是独立的图引擎，两者通过 edge_id 引用。"

### 11.2 引用协议

```python
# TopicTreeNode 中存储
class TopicTreeNode:
    behavior_chain_ids: list[str]  # BehaviorStep.step_id 列表
    edge_references: list[str]     # BehaviorEdge.edge_id 列表

# BehaviorGraph 中查找
class BehaviorGraph:
    def get_chain(self, step_ids: list[str]) -> list[BehaviorStep]:
        return [self.nodes[sid] for sid in step_ids if sid in self.nodes]

    def get_edges_for_chain(self, edge_ids: list[str]) -> list[BehaviorEdge]:
        return [self.edges[eid] for eid in edge_ids if eid in self.edges]
```

### 11.3 拓扑数据流

```
TopicTreeNode 新节点创建
  |
  v
BehaviorGraph.add_step()  -> 创建 BehaviorStep
  |
  v
BehaviorGraph.record_edge() -> 创建/更新 BehaviorEdge
  |
  v
TopicTreeNode.behavior_chain_ids.append(step_id)
TopicTreeNode.edge_references.append(edge_id)
```

---

## 12. 测试策略

### 12.1 单元测试 (P0)

| 测试 | 内容 |
|------|------|
| test_models | BehaviorStep 创建, BehaviorEdge.record_observation, success_rate |
| test_weight_updater | 四项 EMA 更新, 快速纠正模式, 频率比计算 |
| test_fast_correction | 2次纠正检测, 应用纠正, 释放纠正 |
| test_cold_start | 种子加载, 权重查询, sample_count 递增, 自动废弃 |
| test_pruning | 节点超限裁剪, 叶子判断, 非叶子保护 |
| test_causal_discovery | 触发条件, 统计模式分析, structural_prior 输出 |
| test_graph_store | add_step, record_edge, get_weight 三层递进 |

### 12.2 集成测试

| 场景 | 预期 |
|------|------|
| 精确边匹配 | get_weight 返回直接匹配的权重 |
| 语义邻居匹配 | get_weight 返回邻居加权平均权重 |
| 冷启动种子匹配 | get_weight 返回种子初始权重 |
| 全都不匹配 | get_weight 返回 None |
| 连续2次纠正 | correction_mode=True, weight = 0.3*old |
| Meta-Cognitive 释放纠正后 | correction_mode=False, 恢复正常 EMA |
| 种子 sample_count >= 10 | 种子标记为 deprecated |
| 图节点 >= 10000 | 触发裁剪, 删除不活跃叶子 |
| sample_count > 100 & structural_prior=0 | 触发轻量因果发现 |

### 12.3 测试数据

```python
# 模拟行为序列
test_steps = [
    BehaviorStep("s1", "运行程序", "TOOL_EXEC"),
    BehaviorStep("s2", "查看日志", "LOG_CHECK"),
    BehaviorStep("s3", "分析错误", "ENTITY_ANALYZE"),
    BehaviorStep("s4", "修改代码", "CODE_RUN"),
]
# 预期: record_edge(s1, s2) -> weight ~ 0.5-0.7
# 预期: record_edge(s2, s3) -> weight ~ 0.5-0.7
```

---

## 13. 附录

### A. 与算法设计对照

| 算法 S3 | 工程实现 | 状态 |
|---------|---------|------|
| 带标签有向加权图 | BehaviorGraph (graph_store.py) | 待实现 |
| EMA 权重更新 | WeightUpdater (weight_updater.py) | 待实现 |
| 快速纠正通道 | FastCorrectionDetector (fast_correction.py) | 待实现 |
| 稀疏性处理链:语义邻居->LLM->种子->均匀 | BehaviorGraph.get_weight + ColdStartManager | 待实现 |
| 冷启动种子维护 | ColdStartManager (cold_start.py) | 待实现 |
| 图裁剪 (10000节点/30天) | GraphPruner (pruning.py) | 待实现 |
| 轻量因果发现触发 | LightweightCausalDiscovery (causal_discovery.py) | 待实现 |

### B. 实现优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | 数据模型 (models.py) | 其他所有模块依赖 |
| P0 | WeightUpdater | 核心权重更新算法 |
| P0 | BehaviorGraph (graph_store.py) | 核心存储 + get_weight |
| P0 | ColdStartManager | 冷启动种子 |
| P1 | FastCorrectionDetector | 用户纠正处理 |
| P1 | GraphPruner | 节点超限保护 |
| P2 | LightweightCausalDiscovery | 有数据后启用 |

### C. 依赖关系

```
WeightUpdater -> 无（纯算法）
ColdStartManager -> 无
FastCorrectionDetector -> BehaviorGraph
GraphPruner -> BehaviorGraph
LightweightCausalDiscovery -> BehaviorGraph + WeightUpdater
BehaviorGraph -> WeightUpdater + ColdStartManager + ThreeTierWeightQuery（行为嵌入层）
```

### D. 待讨论

1. alpha/beta/gamma/delta 初始值是否合理？建议上线后根据用户行为模式动态调整。
2. 冷启动种子 10 条的合理性？是否需要按领域（调试/部署/开发）分组？
3. 轻量因果发现的统计模式太简单（仅基于 success_rate + correction_rate），是否有更好的启发式？
4. 图裁剪的 10000 节点阈值是否适合中文对话场景？建议按实际图增长调整。

---

## 12. 三链并行存储协议

### 12.1 TopicTreeNode 中的存储结构

TopicTreeNode 存储行为链的拓扑索引, 本身不存边权重。

```python
@dataclass
class BehaviorChain:
    steps: list[str] = field(default_factory=list)  # BehaviorStep.step_id 列表
    edges: list[str] = field(default_factory=list)   # BehaviorEdge.edge_id 列表

@dataclass
class CausalChain:
    events: list[dict] = field(default_factory=list)  # {cause, effect, type, confidence}

@dataclass
class AssociationChain:
    refs: list[dict] = field(default_factory=list)  # {source_step, target_topic, ref_type, strength}
```

### 12.2 关键约束

1. **edge_id 全局唯一**: BehaviorEdge.edge_id 是整个系统的唯一边标识符
2. **权重隔离**: TopicTreeNode 不存储边权重 (权重是 BehaviorGraph 的专属职责)
3. **三链更新时机不同**:
   - 行为链: 每轮对话结束时更新 (同步)
   - 因果链: 事件驱动 (ERROR_TRIGGERED / USER_CORRECTION 触发)
   - 关联链: Meta-Cognitive 周期 (跨主题实体引用, 异步)
4. **级联标记**: TopicTreeNode 被裁剪时, 引用的 edge_id 在 BehaviorGraph 中标记为 orphaned (见 S9.3)

### 12.3 跨模块数据流

```
TopicTreeNode 创建新话题节点
  |
  |-> behavior_chain.edges.append(edge_id)   # 引用 BehaviorGraph 的边
  |-> causal_chain.events.append(event)      # 事件驱动
  |-> association_chain.refs.append(ref)     # Meta-Cognitive 周期
  v
BehaviorGraph 只存权重 (不反向索引 TopicTreeNode)
```

### 12.4 orphaned 引用处理

见 S9.3 (级联标记协议)。pruning 时:
1. BehaviorGraph 删除节点 -> 返回 deleted_step_ids
2. 调用方 (Topic Tree Manager) 遍历所有 TopicTreeNode
3. 在 behavior_chain.steps 中标记 orphaned (软删除, 不删除记录)
4. orphaned 节点不参与权重计算, 保留在拓扑可视化中



### 参数配置

| 参数 | 初始值 | 锚点来源 | 区间 | 自适应信号 | 速率 |
|------|--------|---------|------|-----------|------|
| alpha (LLM) | 0.25 | 经验值 | [0.10, 0.40] | LLM 命中率 | +-0.02/50轮 |
| beta (freq) | 0.30 | 经验值 | [0.15, 0.50] | 样本量 N | 自动: N/50*0.4 |
| gamma (profile) | 0.05 | 经验值 | [0.02, 0.15] | 画像匹配度 | +-0.01/100轮 |
| delta (struct) | 0.05 | 经验值 | [0.03, 0.25] | correction_count | 已有 DeltaAdjuster |
| max_nodes | 10000 | 经验值 | [5000, 50000] | 内存使用率 | 手动 |
| inactive_days | 30 | 经验值 | [7, 90] | 图增长率 | 手动 |

--- END OF DOCUMENT ---
