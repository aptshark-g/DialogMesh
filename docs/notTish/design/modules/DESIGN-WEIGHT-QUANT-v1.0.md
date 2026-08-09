# Literature Cortex — 全局权重重标定与多维度量化评估体系设计

> **文档编号:** LC-DESIGN-WEIGHT-QUANT-v1.0
> **版本:** v1.0
> **日期:** 2026-06-20
> **依赖:** v5.4 协同层 + L0-L4 种子库
> **核心目标:** 建立全局权重重标定（突触缩放）机制 + 完善六维度节点权重量化评估

---

## 1. 问题陈述

### 1.1 当前缺口

v5.4 协同层评估报告指出三个关键缺口：

| 缺口 | 根因 | 解决方向 |
|------|------|---------|
| **突触缩放缺失** | 压缩是节点级的，没有全局重标定 | 引入全局权重重标定（主节拍执行） |
| **反馈闭环缺失** | 健康报告→比例控制无具体规则 | 量化健康指标，定义触发阈值 |
| **主动触发链缺失** | 协同层只被动整理 | 量化"盲区信号"，触发自引用/L0-L4演化 |

**共同根因：缺少统一的量化评估体系。**

### 1.2 为什么需要量化

当前评估依赖定性判断（"高频""根基""解构"），没有：
- **统一量纲**：使用频率是整数、根基性是布尔值、解构频率是文本出现次数
- **权重融合**：多个维度如何加权成单一优先级分数
- **动态衰减**：旧数据的权重是否衰减？多快？
- **全局归一化**：节点A的分数能否与节点B直接比较？

---

## 2. 全局权重重标定（突触缩放）

### 2.1 神经科学基础

**文献来源：**
- Tononi & Cirelli (2006). *Sleep function and synaptic homeostasis*. Sleep Medicine Reviews. [Cited 3014]
- González-Rueda et al. (2018). *Activity-Dependent Downscaling of Subthreshold Synaptic Inputs during Slow-Wave-Sleep-like Activity In Vivo*. Journal of Neuroscience. [Cited 160]

**核心发现：**
1. **全局比例缩放**：睡眠期间所有突触按比例降低强度（如统一降至0.8），保留相对差异
2. **信号噪声比提升**：弱突触被抹去，强突触保留，SNR从2.5升至11.2
3. **自限制性**：突触权重回到基线后，慢波幅度降低，缩放自动停止
4. **与LTD不同**：LTD针对特定突触组，downscaling是全局的

**关键公式（来自文献）：**
```
w_after = w_before × α  (α ≈ 0.8, 全局统一比例)
```

### 2.2 工程化设计

```python
class GlobalWeightRescaling:
    """
    全局权重重标定：突触缩放的工程化实现。
    
    核心原则：
    1. 全局缩放保留相对秩序（强者仍强，弱者仍弱）
    2. 低权重节点低于阈值后标记为可压缩
    3. 高价值节点获得保护加成
    4. 过程自限制：当全局平均接近基线时自动停止
    """
    
    # 配置参数
    BASELINE_RATIO = 0.75      # 目标：全局平均降至基线的75%
    DOWNSCALE_RATE = 0.9       # 每轮缩放比例（文献中≈0.8，系统可调）
    MIN_WEIGHT_THRESHOLD = 0.05  # 低于此值标记为可压缩
    HIGH_VALUE_PROTECT = 0.8    # 价值分>0.8的节点保护加成
    PROTECT_BOOST = 1.15        # 保护节点缩放后反向增强15%
    
    def rescale(self, all_nodes: list[Node]) -> RescaleReport:
        """执行全局权重重标定。主节拍触发。"""
        
        # Step 1: 计算当前全局统计
        weights = [n.composite_weight for n in all_nodes]
        global_avg = sum(weights) / len(weights)
        global_max = max(weights)
        global_min = min(weights)
        
        # Step 2: 判断是否需要缩放（自限制）
        if global_avg <= self.baseline_target(global_max, global_min):
            return RescaleReport(skipped=True, reason="already_at_baseline")
        
        # Step 3: 执行全局比例缩放
        for node in all_nodes:
            # 全局缩放：保留相对差异
            node.composite_weight *= self.DOWNSCALE_RATE
            
            # 高价值节点保护（强者更强）
            if node.value_score > self.HIGH_VALUE_PROTECT:
                node.composite_weight *= self.PROTECT_BOOST
            
            # 确保不越界
            node.composite_weight = clamp(node.composite_weight, 0.001, 1.0)
        
        # Step 4: 标记可压缩节点
        compressible = []
        for node in all_nodes:
            if node.composite_weight < self.MIN_WEIGHT_THRESHOLD:
                node.compression_flag = True
                compressible.append(node)
        
        # Step 5: 生成报告
        return RescaleReport(
            global_avg_before=global_avg,
            global_avg_after=sum(n.composite_weight for n in all_nodes) / len(all_nodes),
            compressible_count=len(compressible),
            protected_count=sum(1 for n in all_nodes if n.value_score > self.HIGH_VALUE_PROTECT),
            skipped=False
        )
    
    def baseline_target(self, global_max: float, global_min: float) -> float:
        """计算基线目标：动态的，基于当前分布。"""
        # 基线 = 最小值 + (最大值-最小值) × BASELINE_RATIO
        # 这比固定阈值更自适应
        return global_min + (global_max - global_min) * self.BASELINE_RATIO
```

### 2.3 与压缩归档的联动

```
主节拍触发：
  ├─ Step 1: 全局权重重标定（GlobalWeightRescaling）
  │   └─ 所有节点权重统一缩放
  │   └─ 高价值节点反向增强
  │   └─ 低于阈值的节点标记为"可压缩"
  │
  ├─ Step 2: 压缩引擎（原有逻辑）
  │   └─ 优先处理标记为"可压缩"的节点
  │   └─ 不再依赖固定活跃度阈值
  │
  └─ Step 3: 恢复管理（原有逻辑）
      └─ 恢复后的节点获得"恢复期加成"（临时权重+50%）
```

**关键变化：** 压缩决策从"固定阈值"变为"相对排序"——始终压缩当前权重最低的N%节点，而不是压缩低于固定线的节点。

---

## 3. 六维度节点权重量化评估

### 3.1 维度总览

| 维度 | 符号 | 含义 | 量化基础 | 衰减机制 |
|------|------|------|---------|---------|
| **使用频率** | F (Frequency) | 被系统/用户引用的次数 | 计数器 | EMA衰减 |
| **最近使用** | R (Recency) | 最后一次使用距今天数 | 时间戳 | 自然衰减 |
| **根基性** | G (Groundedness) | 跨领域引用深度 | 领域覆盖度 | 无（相对静态） |
| **解构频率** | D (Deconstruction) | 发散层引用为桥接的次数 | 反事实/溯因计数 | EMA衰减 |
| **拓扑中心性** | C (Centrality) | 在网络中的结构重要性 | PageRank变体 | 随网络演化重算 |
| **价值评估** | V (Value) | 人工/系统综合评分 | 多源加权 | 慢速EMA |

### 3.2 各维度量化方案

#### 3.2.1 使用频率 (F)

**文献基础：** 突触稳态假说（Tononi & Cirelli 2006）——清醒时高频使用的突触增强。

**量化公式：**
```python
class FrequencyTracker:
    """使用频率：带EMA衰减的引用计数。"""
    
    DECAY_HALF_LIFE = 7  # 7天半衰期
    
    def record_access(self, node: Node):
        """记录一次节点访问。"""
        now = time.time()
        days_since_last = (now - node.last_access_time) / 86400
        
        # EMA衰减：旧分数按时间衰减
        decay_factor = 0.5 ** (days_since_last / self.DECAY_HALF_LIFE)
        node.frequency_score = node.frequency_score * decay_factor + 1.0
        node.last_access_time = now
```

**为什么EMA：**
- 纯计数会无限增长，新旧节点不公平
- EMA让近期访问更有权重，旧访问自然淡化
- 半衰期7天：一周前的访问贡献减半

#### 3.2.2 最近使用 (R)

**文献基础：** 海马体回放机制——近期记忆在睡眠中优先巩固（Walker 2005）。

**量化公式：**
```python
class RecencyTracker:
    """最近使用：时间衰减函数。"""
    
    def compute_recency(self, node: Node) -> float:
        """返回0-1的最近使用分数。1=刚刚使用，0=从未使用/太久。"""
        if node.last_access_time is None:
            return 0.0
        
        days_ago = (time.time() - node.last_access_time) / 86400
        
        # 指数衰减：3天内接近1，30天后接近0
        return math.exp(-days_ago / 10.0)
```

**为什么指数衰减：**
- 人脑对近期事件的记忆强度呈指数下降（Ebbinghaus遗忘曲线）
- 3天内视为"热"，30天后视为"冷"
- 与使用频率的EMA衰减不同：频率是"累积"的，最近使用是"瞬时"的

#### 3.2.3 根基性 (G)

**文献基础：** 系统巩固理论——海马体向皮层的迁移依赖于记忆的"根基化"（多重关联）。

**量化公式：**
```python
class GroundednessEvaluator:
    """根基性：跨领域引用深度。"""
    
    MIN_DOMAIN_COUNT = 3       # 至少3个领域才算有根基性
    MAX_DOMAIN_COUNT = 10      # 超过10个领域不再额外加分（饱和）
    
    def compute_groundedness(self, node: Node) -> float:
        """
        根基性 = 领域覆盖度 × 引用深度 × 持久化匹配度
        """
        # 1. 领域覆盖度（0-1）
        domains = set()
        for edge in node.incoming_edges:
            domains.add(edge.source_domain)
        for edge in node.outgoing_edges:
            domains.add(edge.target_domain)
        
        domain_coverage = min(len(domains) / self.MAX_DOMAIN_COUNT, 1.0)
        
        # 2. 引用深度：是否有L0-L4节点指向它
        l0l4_refs = sum(1 for e in node.incoming_edges if e.source_level <= 4)
        depth_bonus = min(l0l4_refs / 3.0, 1.0)  # 3个L0-L4引用即满分
        
        # 3. 持久化匹配度：是否匹配L0-L4种子
        persistence_match = 1.0 if node.matched_l0l4 else 0.3
        
        # 综合
        groundedness = (domain_coverage * 0.4 + 
                       depth_bonus * 0.3 + 
                       persistence_match * 0.3)
        
        return clamp(groundedness, 0.0, 1.0)
```

**为什么这样设计：**
- 领域覆盖度（40%）：跨领域越多，根基越牢
- 引用深度（30%）：被L0-L4引用说明是基础概念
- 持久化匹配（30%）：已纳入种子库说明通过验证

#### 3.2.4 解构频率 (D)

**文献基础：** 反事实推理在记忆重组中的作用（Byrne 2007）；发散思维的网络激活扩散（Mednick 1962）。

**量化公式：**
```python
class DeconstructionTracker:
    """解构频率：发散层引用为桥接的次数。"""
    
    DECAY_HALF_LIFE = 14  # 14天半衰期（比使用频率慢，因为解构是深层处理）
    
    def record_deconstruction(self, node: Node, bridge_type: str):
        """
        记录一次解构引用。
        
        bridge_type: "counterfactual" | "abduction" | "inverted_causality" | "analogy"
        """
        now = time.time()
        days_since_last = (now - node.last_decon_time) / 86400
        
        # EMA衰减
        decay_factor = 0.5 ** (days_since_last / self.DECAY_HALF_LIFE)
        
        # 权重：不同类型的解构有不同的"深度"
        type_weights = {
            "counterfactual": 1.0,      # 反事实：标准深度
            "abduction": 1.2,           # 溯因：更高，因为涉及因果推理
            "inverted_causality": 1.5,  # 倒置因果：最高，涉及约束重构
            "analogy": 0.8              # 类比：较低，因为可能较浅
        }
        weight = type_weights.get(bridge_type, 1.0)
        
        node.deconstruction_score = node.deconstruction_score * decay_factor + weight
        node.last_decon_time = now
```

#### 3.2.5 拓扑中心性 (C)

**文献基础：** PageRank（Brin & Page 1998）；Eigenvector Centrality（Bonacich 1972）；知识图谱节点重要性（Zhang et al. 2022, Physica A）。

**量化公式（Weighted PageRank变体）：**
```python
class TopologyCentrality:
    """
    拓扑中心性：基于加权PageRank的节点结构重要性。
    
    文献：Zhang, P., Wang, T. and Yan, J. (2022). 
    PageRank centrality and algorithms for weighted, directed networks.
    Physica A, 586, 126438.
    """
    
    DAMPING = 0.85   # 标准PageRank阻尼因子
    ITERATIONS = 50  # 收敛迭代次数
    
    def compute_pagerank(self, graph: Graph) -> dict[str, float]:
        """计算所有节点的Weighted PageRank。"""
        
        # 初始化
        N = len(graph.nodes)
        pr = {node.id: 1.0 / N for node in graph.nodes}
        
        for _ in range(self.ITERATIONS):
            new_pr = {}
            for node in graph.nodes:
                # 计算流入权重和
                rank_sum = 0.0
                for edge in node.incoming_edges:
                    source = edge.source
                    # Weighted PageRank：考虑边权重
                    weight = edge.weight if edge.weight else 1.0
                    out_strength = sum(e.weight for e in source.outgoing_edges)
                    if out_strength > 0:
                        rank_sum += pr[source.id] * weight / out_strength
                
                # PageRank公式
                new_pr[node.id] = (1 - self.DAMPING) / N + self.DAMPING * rank_sum
            
            pr = new_pr
        
        # 归一化到0-1
        max_pr = max(pr.values())
        return {k: v / max_pr for k, v in pr.items()}
```

**为什么PageRank：**
- 被重要节点指向的节点更重要（递归定义，符合知识网络直觉）
- 考虑边的权重（Weighted PageRank）
- 50次迭代收敛（Zhang et al. 2022实证）
- 阻尼因子0.85是网络科学标准值

#### 3.2.6 价值评估 (V)

**量化公式：**
```python
class ValueEvaluator:
    """价值评估：人工+系统的综合评分。"""
    
    def compute_value(self, node: Node) -> float:
        """
        价值 = 系统评分 × 0.7 + 人工评分 × 0.3
        
        系统评分基于：
        - 被高价值节点引用的次数
        - 跨层引用数（收敛→发散→L0-L4）
        - 压缩后的恢复率（恢复率高=价值被低估）
        """
        # 系统评分
        high_value_refs = sum(1 for e in node.incoming_edges 
                             if e.source.value_score > 0.8)
        cross_layer_refs = sum(1 for e in node.incoming_edges 
                              if e.source.layer != node.layer)
        
        system_score = min((high_value_refs * 0.3 + cross_layer_refs * 0.2) / 5.0, 1.0)
        
        # 人工评分（默认0.5，未评分时中性）
        human_score = node.human_value_rating if node.human_value_rating else 0.5
        
        # 恢复率修正：恢复率高说明之前被低估
        if node.compress_count > 0:
            recovery_rate = node.recover_count / node.compress_count
            if recovery_rate > 0.5:
                system_score = min(system_score * (1 + recovery_rate * 0.3), 1.0)
        
        return clamp(system_score * 0.7 + human_score * 0.3, 0.0, 1.0)
```

### 3.3 综合权重计算

```python
class CompositeWeightCalculator:
    """
    综合权重 = 六维度加权融合。
    
    权重分配原则：
    - 使用频率和最近使用：反映"活跃度"（短期）
    - 根基性和拓扑中心性：反映"结构重要性"（中长期）
    - 解构频率：反映"认知深度"（深层处理）
    - 价值评估：反映"质量"（人工+系统综合）
    """
    
    # 维度权重（可调，总和=1.0）
    WEIGHTS = {
        'frequency': 0.20,       # 使用频率：活跃度的基础
        'recency': 0.15,         # 最近使用：短期热度
        'groundedness': 0.20,    # 根基性：跨领域稳定性
        'deconstruction': 0.15,  # 解构频率：认知深度
        'centrality': 0.15,      # 拓扑中心性：结构位置
        'value': 0.15            # 价值评估：综合质量
    }
    
    def compute_composite(self, node: Node) -> float:
        """计算节点的综合权重。"""
        scores = {
            'frequency': normalize_log(node.frequency_score),
            'recency': node.recency_score,
            'groundedness': node.groundedness_score,
            'deconstruction': normalize_log(node.deconstruction_score),
            'centrality': node.centrality_score,
            'value': node.value_score
        }
        
        composite = sum(scores[k] * w for k, w in self.WEIGHTS.items())
        return clamp(composite, 0.001, 1.0)
    
    def normalize_log(self, x: float) -> float:
        """对数归一化：处理计数器的长尾分布。"""
        return min(math.log1p(x) / math.log1p(1000), 1.0)  # 1000次访问≈满分
```

**为什么对数归一化：**
- 计数器（频率、解构）通常呈长尾分布（少数节点极高，多数极低）
- 对数压缩极端值，让中等活跃节点也有区分度
- log1p(1000) ≈ 7.0，作为归一化基准

---

## 4. 反馈闭环规则（量化版）

基于六维度量化，定义协同层→比例控制的具体反馈规则：

```python
class QuantifiedFeedbackLoop:
    """量化反馈闭环：将健康状态转化为比例调整指令。"""
    
    def compute_adjustment(self, metrics: SystemMetrics) -> RatioAdjustment:
        """
        根据量化指标调整收敛/发散比例。
        """
        adjustments = []
        
        # 规则1：全局平均权重过高 → 需要整理，降低发散
        if metrics.global_avg_weight > 0.6:
            adjustments.append(("high_global_weight", -0.15))
        
        # 规则2：可压缩节点比例 > 20% → 系统臃肿
        if metrics.compressible_ratio > 0.2:
            adjustments.append(("compressible_overflow", -0.15))
        
        # 规则3：limbo恢复率 > 30% → 压缩过度
        if metrics.limbo_recovery_rate > 0.3:
            adjustments.append(("over_compression", -0.10))
        
        # 规则4：高价值节点被压缩 → 严重错误
        if metrics.high_value_compressed > 0:
            adjustments.append(("value_violation", -0.25))
        
        # 规则5：解构活跃度低（30天<5次）→ 发散不足
        if metrics.avg_deconstruction_30d < 5.0:
            adjustments.append(("low_divergence", +0.10))
        
        # 规则6：拓扑中心性断层（部分区域PageRank骤降）→ 结构危机
        if metrics.centrality_variance > 0.5:
            adjustments.append(("structure_crisis", -0.20))
        
        # 规则7：系统空闲 + 健康良好 → 提高发散（探索窗口）
        if metrics.is_idle and metrics.global_avg_weight < 0.4:
            adjustments.append(("exploration_window", +0.10))
        
        # 综合调整（加总后clamp）
        total_delta = sum(delta for _, delta in adjustments)
        return RatioAdjustment(
            diverge_delta=clamp(total_delta, -0.3, +0.2),
            reasons=adjustments
        )
```

---

## 5. 主动触发链（量化版）

基于六维度量化，定义协同层主动触发的条件：

```python
class QuantifiedTriggerChain:
    """量化触发链：从压缩统计中发现系统级信号。"""
    
    def analyze_compression(self, report: CompressionReport) -> list[SystemTrigger]:
        """分析压缩报告，生成触发信号。"""
        triggers = []
        
        # 信号1：大量节点无法匹配L0-L4 → 盲区发现
        unmatched_ratio = report.unmatched_count / report.total_compressed
        if unmatched_ratio > 0.3:
            triggers.append(SystemTrigger(
                type="BLIND_SPOT_DETECTED",
                priority="HIGH",
                data={
                    "unmatched_nodes": report.unmatched_nodes,
                    "suggested_action": "trigger_self_reference",
                    "reason": f"{unmatched_ratio:.1%}压缩节点无法归入L0-L4，可能存在知识盲区"
                }
            ))
        
        # 信号2：某领域节点集中被压缩 → 领域衰退
        domain_compress_ratios = report.domain_compression_ratios
        for domain, ratio in domain_compress_ratios.items():
            if ratio > 0.5:  # 某领域>50%节点被压缩
                triggers.append(SystemTrigger(
                    type="DOMAIN_DECLINE",
                    priority="MEDIUM",
                    data={
                        "domain": domain,
                        "ratio": ratio,
                        "suggested_action": "trigger_divergent_exploration",
                        "reason": f"{domain}领域节点大量被压缩，可能需要重新探索"
                    }
                ))
        
        # 信号3：高解构频率节点被压缩 → 认知深度受损
        for node in report.compressed_nodes:
            if node.deconstruction_score > 10.0:
                triggers.append(SystemTrigger(
                    type="DEPTH_LOSS",
                    priority="HIGH",
                    data={
                        "node_id": node.id,
                        "decon_score": node.deconstruction_score,
                        "suggested_action": "restore_and_protect",
                        "reason": "高频解构节点被压缩，发散层桥接受损"
                    }
                ))
        
        return triggers
```

---

## 6. 与文献的对应关系

| 设计元素 | 神经科学/网络科学来源 | 关键文献 |
|---------|---------------------|---------|
| 全局权重重标定 | 突触稳态假说（synaptic homeostasis） | Tononi & Cirelli 2006 |
| 比例缩放（α=0.9） | 慢波睡眠期间突触按比例降低 | González-Rueda 2018 |
| 高价值保护 | 强突触在downscaling中保留 | Walker 2005 |
| 使用频率EMA | 突触使用依赖强化（LTP） | Hebbian learning |
| 最近使用指数衰减 | Ebbinghaus遗忘曲线 | 经典记忆理论 |
| 根基性（跨领域） | 系统巩固（海马→皮层迁移） | Rasch & Born 2013 |
| 拓扑中心性 | Weighted PageRank | Zhang et al. 2022 |
| 阻尼因子0.85 | PageRank标准参数 | Brin & Page 1998 |
| 对数归一化 | 信息检索TF-IDF的log压缩 | Manning et al. 2008 |

---

## 7. 实施优先级

| 阶段 | 内容 | 工作量 | 阻塞项 |
|------|------|--------|--------|
| **P0** | 全局权重重标定（GlobalWeightRescaling） | ~150行 | 无 |
| **P0** | 六维度评估器（六类Tracker） | ~400行 | 无 |
| **P1** | 综合权重计算（CompositeWeightCalculator） | ~100行 | 依赖六维度 |
| **P1** | 反馈闭环规则（QuantifiedFeedbackLoop） | ~150行 | 依赖综合权重 |
| **P2** | 主动触发链（QuantifiedTriggerChain） | ~200行 | 依赖压缩统计 |
| **P2** | 拓扑中心性（PageRank） | ~200行 | 需要完整图结构 |

---

## 8. 一句话总结

**全局权重重标定解决"相对排序"问题，六维度量化解决"凭什么排序"问题，反馈闭环解决"排序后怎么办"问题。三者结合，协同层从"定期清洁工"升级为"主动调节器"。**

---

*文档版本: v1.0*
*日期: 2026-06-20*
*设计: 合作 (OpenClaw)*
*文献基础: Tononi & Cirelli 2006; González-Rueda 2018; Zhang et al. 2022; Brin & Page 1998*
