# Literature Cortex — 发散层设计补充 v0.3 (REVISED)

> **文档编号:** LC-DESIGN-DIVERGENT-v0.3-revised
> **版本:** v0.3
> **日期:** 2026-06-26
> **依赖:** LC-DESIGN-DIVERGENT-v0.1, LC-DESIGN-WEIGHT-QUANT-v1.0, LC-DESIGN-v5.4, LC-DESIGN-v6.0-UNIFIED
> **核心目标:** 补全 v0.1 中未完善的设计细节，将四个核心缺口从"框架"推进到"可工程化"

---

## 1. 补充内容概述

v0.1 设计文档完成了发散层框架和哲学基础，但以下五方面存在缺口：

| 缺口 | 说明 | 补充章节 |
|------|------|---------|
| 双权重约束未嵌入决策 | 只有激活公式，未作为发散约束条件 | 第2章 |
| 全局权重重标定与L5耦合 | 量化评估设计独立，未与发散层联动 | 第3章 |
| 假设生成器为占位实现 | 只有随机示例，缺少真实策略设计 | 第4章 |
| "破坏与怀疑"缺少决策流程 | 哲学描述完整，但流程图缺失 | 第5章 |
| 语义向量距离未深入 | 只有接口声明，无设计细节 | 第6章 |

---

## 2. 双权重约束与发散决策机制

### 2.1 问题：双权重是记录，不是约束

v0.1 中双权重机制记录节点的 `access_count` 和 `last_accessed`，但发散层在生成假设时**未使用这些信息来约束搜索范围**。结果是：发散层仍然可能从休眠节点出发，导致无意义的穷举。

**核心原则：** 人脑发散不是穷举，而是"在双权重约束下偏采样"。

### 2.2 双权重约束的三种介入方式

```
┌─────────────────────────────────────────────────────────────┐
│                    双权重约束介入模型                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  方式一：扩散起点过滤                                          │
│  ─────────────────────────────────                           │
│  起点节点必须满足：Activation(n) > θ_start (默认 0.3)          │
│  不满足的节点 → 不触发发散                                     │
│                                                              │
│  方式二：邻居传播剪枝                                          │
│  ─────────────────────────────────                           │
│  扩散到邻居时：Activation(neighbor) > θ_prune (默认 0.1)       │
│  不满足的邻居 → 停止沿该分支扩散                               │
│                                                              │
│  方式三：假设生成排序                                          │
│  ─────────────────────────────────                           │
│  生成假设后，按激活度加权排序：                                 │
│  priority = hypothesis_score * (1 + activation_boost)          │
│  activation_boost = tanh(Activation(seed_node))               │
│  高激活节点生成的假设优先进入验证队列                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 决策流程图

```
输入：收敛层链路 A→B→C

Step 1: 检查起点激活度
  A_active = get_activation("A")
  B_active = get_activation("B")
  C_active = get_activation("C")
  
  if any(active < θ_start):
    # 优先 touch 低激活节点，确保上下文连续性
    touch(lowest_active_node)
    return WAIT  # 本轮不发散，先激活

Step 2: 确定扩散策略（基于双权重）
  # 高激活节点 → 优先破坏（用户最近验证过，有上下文）
  # 中等激活节点 → 优先溯因（有基础但未被深入探索）
  # 低激活节点 → 不触发（避免冷启动发散）
  
  primary_seed = argmax([A_active, B_active, C_active])
  
  if primary_seed == A:
    strategy = "counterfactual_breaking"  # 从起点破坏链路
  elif primary_seed == B:
    strategy = "abductive_gap"  # 从中间节点溯因
  else:
    strategy = "analogical_mirror"  # 从终点反向类比

Step 3: 扩散过程（带剪枝）
  candidates = get_neighbors(primary_seed)
  pruned = [c for c in candidates if get_activation(c) > θ_prune]
  
  # 如果剪枝后候选不足，放宽阈值但记录警告
  if len(pruned) < min_candidates:
    pruned = [c for c in candidates if get_activation(c) > θ_prune * 0.5]
    log_warning("pruning_relaxed", primary_seed, len(pruned))

Step 4: 生成假设并排序
  hypotheses = generate_hypotheses(primary_seed, strategy, pruned)
  for h in hypotheses:
    h.priority = h.intrinsic_score * (1 + tanh(get_activation(h.seed_node)))
  
  sorted_hypotheses = sorted(hypotheses, key=lambda h: h.priority, reverse=True)
  return sorted_hypotheses[:budget]
```

### 2.4 参数表

| 参数 | 默认值 | 可调范围 | 说明 |
|------|--------|---------|------|
| `θ_start` | 0.3 | [0.1, 0.5] | 扩散起点激活度阈值 |
| `θ_prune` | 0.1 | [0.0, 0.3] | 邻居传播剪枝阈值 |
| `min_candidates` | 3 | [2, 10] | 剪枝后最小候选数 |
| `activation_boost_max` | 0.5 | [0.2, 1.0] | tanh输出上限，控制激活度对优先级的影响强度 |
| `budget_multiplier` | 1.0 | [0.5, 2.0] | 基础预算乘数，高激活方向增加预算 |

### 2.5 与 v0.1 的差异

v0.1 中双权重机制是**独立的数据记录层**，与发散决策无直接耦合。本补充将双权重升级为**发散约束条件**，直接影响：
- 是否触发发散
- 选择哪种发散策略
- 从哪个节点开始扩散
- 哪些邻居可以参与
- 假设生成的优先级排序

---

## 3. 全局权重重标定与 L5 耦合

### 3.1 问题：量化评估与发散层独立运行

`DESIGN-WEIGHT-QUANT-v1.0` 设计了全局权重重标定（突触缩放），但标定后的权重未直接用于发散层的决策。两个系统各自运行，没有形成闭环。

### 3.2 耦合点：重标定后的权重作为发散预算分配器

```
全局权重重标定流程：
  1. 主节拍触发 → 对所有节点执行突触缩放
  2. 产生 RescaleReport：每个节点的新权重 w_new
  3. 标记 w_new < MIN_WEIGHT_THRESHOLD 的节点为"可压缩"

耦合到 L5：
  4. L5 读取 RescaleReport
  5. 可压缩节点 → 发散预算 = 0（禁止从这些节点发散）
  6. 高权重节点 → 发散预算增加（这些节点是系统核心，值得深挖）
  7. 中等权重节点 → 标准预算（系统探索的边界）
```

### 3.3 六维度权重与发散策略映射

全局权重重标定考虑了六维度：使用频率、根基性、解构频率、引用网络中心性、验证通过率、跨域连接度。不同维度主导时，发散策略不同：

| 主导维度 | 节点特征 | 推荐发散策略 | 预算分配 |
|---------|---------|------------|---------|
| 使用频率高 | 核心知识节点 | 跨域类比（寻找镜像） | 高 |
| 根基性高 | 公理/基础概念 | 倒置因果（挑战基础假设） | 中 |
| 解构频率高 | 已被多次质疑 | 反事实破坏（寻找新的替代） | 高 |
| 引用中心性高 | 连接多个领域 | 跨域类比（验证连接质量） | 高 |
| 验证通过率高 | 已被多次验证 | 溯因假设（寻找更简洁解释） | 中 |
| 跨域连接度高 | 多领域通用 | 约束差异分析（对比不同领域） | 高 |

### 3.4 接口定义

```python
class WeightDivergenceCoupling:
    """全局权重重标定与发散层的耦合接口。"""
    
    def __init__(self, rescale_report: RescaleReport, arbiter: MetaCognitiveArbiter):
        self.report = rescale_report
        self.arbiter = arbiter
    
    def apply_budget_adjustment(self):
        """根据重标定结果调整发散预算。"""
        for node_id, new_weight in self.report.rescaled_weights.items():
            if new_weight < self.report.MIN_WEIGHT_THRESHOLD:
                # 可压缩节点：禁止发散
                self.arbiter.anti_bloat.set_budget(node_id, 0)
            elif new_weight > self.report.HIGH_VALUE_PROTECT:
                # 高价值节点：增加预算
                self.arbiter.anti_bloat.set_budget_multiplier(node_id, 1.5)
            else:
                # 标准预算
                self.arbiter.anti_bloat.set_budget_multiplier(node_id, 1.0)
    
    def get_strategy_recommendation(self, node_id: str) -> str:
        """根据节点主导维度推荐发散策略。"""
        dominant = self.report.get_dominant_dimension(node_id)
        strategy_map = {
            "usage_frequency": "cross_domain_analogy",
            "rootedness": "inverted_causality",
            "deconstruction_freq": "counterfactual_breaking",
            "centrality": "cross_domain_analogy",
            "validation_rate": "abductive_hypothesis",
            "cross_domain": "constraint_difference",
        }
        return strategy_map.get(dominant, "general_divergence")
```

---

## 4. 假设生成器真实化设计

### 4.1 问题：v0.1 中假设生成是随机占位

```python
# v0.1 中的示例（占位实现）
def _generate_semantic_bridge(self, node_id: str) -> List[Hypothesis]:
    return [
        Hypothesis(
            id=f"{node_id}::sb::{i}",
            text=f"语义桥接假设 {i}：{node_id} 与领域 X 关联",
            total_value=random.uniform(0.5, 1.0),
        )
        for i in range(3)
    ]
```

这个实现没有使用任何真实知识，只是生成随机假设。需要设计真实的假设生成策略。

### 4.2 假设生成器分类与策略

假设生成器分为**三类**，对应不同的知识来源和可靠性：

| 类型 | 知识来源 | 可靠性 | 适用场景 | 生成策略 |
|------|---------|--------|---------|---------|
| **结构驱动** | 知识图谱拓扑 | 高 | 反事实破坏、溯因 | 图遍历 + 路径搜索 |
| **语义驱动** | 向量嵌入相似度 | 中 | 跨域类比、语义桥接 | 向量检索 + 最近邻 |
| **LLM驱动** | 大语言模型推理 | 低（但泛化强） | 倒置因果、创造性假设 | 约束提示 + 链式推理 |

### 4.3 结构驱动生成器：反事实破坏

**输入：** 收敛链路 `A→B→C`

**策略：**
```
1. 找出所有从 A 到 C 的替代路径（排除 B）
   - 使用 BFS/DFS 在图中搜索 A→?→C
   - 限制路径长度 ≤ 3（避免过长假设）

2. 对每条替代路径 P = A→D→C：
   - 计算结构相似度：sim_struct(P, A→B→C)
   - 计算语义支撑：是否存在 A→D 和 D→C 的边？
   - 如果两条边都存在 → 高置信度假设
   - 如果只有一条边存在 → 中置信度（需验证）
   - 如果两条边都不存在 → 低置信度（纯假设）

3. 生成报告：
   {
     "type": "counterfactual_alternative",
     "original": "A→B→C",
     "alternative": "A→D→C",
     "structural_similarity": 0.85,
     "semantic_support": 0.6,  # 两条边中存在的比例
     "confidence": 0.72,  # 综合评分
     "verification_needed": True
   }
```

### 4.4 语义驱动生成器：跨域类比

**输入：** 收敛链路 `A→B→C`（控制领域）

**策略：**
```
1. 提取结构签名：
   signature = extract_structural_signature(A→B→C)
   # 例如：{feedback_loop, adaptive_filter, error_minimization}

2. 在语义向量空间中搜索相似签名：
   - 使用 sentence-transformers/SciBERT 编码所有已知结构签名
   - 计算 cosine_similarity(signature, known_signatures)
   - 返回 top-k 相似签名及其领域

3. 对 top-k 中的每个签名 S：
   - 找到 S 对应的领域 D 和链路 A'→B'→C'
   - 计算结构同构度（使用 VF2 子图匹配）
   - 如果同构度 > 0.6 → 生成类比假设

4. 生成报告：
   {
     "type": "cross_domain_analogy",
     "source": "A→B→C (control)",
     "target": "A'→B'→C' (thermal)",
     "structural_isomorphism": 0.72,
     "semantic_similarity": 0.85,
     "question": "热控系统能否借鉴控制系统的自适应结构？",
     "confidence": 0.78
   }
```

### 4.5 LLM 驱动生成器：倒置因果

**输入：** 收敛链路 `A→B→C` 及其约束集合 `{c₁, c₂, c₃}`

**策略：**
```
1. 构建约束差异提示：
   prompt = f"""
   当前链路：{A→B→C}
   当前约束：{c₁, c₂, c₃}
   当前结果：{result}
   
   请回答以下问题：
   1. 如果不接受当前结果，需要改变哪些约束？
   2. 哪些约束是结果的必要前提？
   3. 改变哪个约束最容易颠覆结论？
   4. 约束变化的可行性如何（0-1）？
   
   请以 JSON 格式输出：
   {{
     "required_changes": [...],
     "necessary_constraints": [...],
     "most_disruptive": "...",
     "feasibility": 0.0-1.0
   }}
   """

2. 调用 LLM（温度参数 0.7，鼓励创造性但保持约束）

3. 解析 LLM 输出，提取约束变化

4. 对每条约束变化：
   - 使用 CVE 引擎评估变化类型（Type-A/B/C）
   - 使用收敛层验证变化后的结果是否匹配假设
   - 生成最终报告

5. 输出报告：
   {
     "type": "inverted_causality",
     "original_result": "...",
     "assumed_result": "...",
     "required_changes": [...],
     "feasibility": 0.35,
     "disruption_ranking": [...]
   }
```

### 4.6 假设生成器接口统一

```python
class HypothesisGenerator(ABC):
    """假设生成器抽象基类。"""
    
    @abstractmethod
    def generate(self, seed: DivergenceSeed, context: DivergenceContext) -> List[Hypothesis]:
        """生成假设列表。"""
        pass
    
    @abstractmethod
    def get_reliability(self) -> float:
        """返回生成器的可靠性评分（0-1）。"""
        pass

class StructuralHypothesisGenerator(HypothesisGenerator):
    """结构驱动生成器。"""
    reliability = 0.85
    
class SemanticHypothesisGenerator(HypothesisGenerator):
    """语义驱动生成器。"""
    reliability = 0.65
    
class LLMHypothesisGenerator(HypothesisGenerator):
    """LLM 驱动生成器。"""
    reliability = 0.45
```

---

## 5. "破坏与怀疑"的主动哲学机制：决策流程

### 5.1 问题：哲学描述完整，但决策流程图缺失

v0.1 中描述了四种怀疑形态（链路破坏、节点溯因、跨域类比、倒置因果），但没有说明：
- 何时选择哪种怀疑形态？
- 怀疑的触发条件是什么？
- 怀疑后如何验证？
- 怀疑失败后的回退策略？

### 5.2 主动破坏的决策流程

```
┌─────────────────────────────────────────────────────────────┐
│              主动破坏决策流程（Active Destruction）           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  输入：收敛层链路 A→B→C，置信度 conf                          │
│                                                              │
│  Step 1: 评估链路信心指数（Link Confidence Index）             │
│  ────────────────────────────────────────                   │
│  LCI = conf * (1 + validation_count/10) * recency_boost    │
│  recency_boost = exp(-days_since_last_check / 30)            │
│                                                              │
│  如果 LCI > 0.9 → 链路"过自信"，需要强烈怀疑                  │
│  如果 LCI ∈ [0.6, 0.9] → 链路"正常"，标准怀疑                 │
│  如果 LCI < 0.6 → 链路"不自信"，不需要怀疑（本身就不确定）     │
│                                                              │
│  Step 2: 选择怀疑形态（基于 LCI 和链路特征）                   │
│  ────────────────────────────────────────                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  if LCI > 0.9:                                       │    │
│  │    # 过自信链路：强烈怀疑，四种形态全部触发            │    │
│  │    modes = [counterfactual, abductive, analogical, inverted]│    │
│  │  elif 链路长度 == 2:  # A→B→C                          │    │
│  │    # 短链路：优先链路破坏和溯因                        │    │
│  │    modes = [counterfactual, abductive]                 │    │
│  │  elif 链路包含跨领域节点:                              │    │
│  │    # 跨领域链路：优先类比和倒置因果                     │    │
│  │    modes = [analogical, inverted]                      │    │
│  │  else:                                                │    │
│  │    # 标准链路：标准怀疑                                │    │
│  │    modes = [counterfactual, analogical]                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Step 3: 执行怀疑（并行或串行）                              │
│  ────────────────────────────────────────                   │
│  对每个 mode in modes:                                       │
│    result = execute(mode, A→B→C)                            │
│    if result.confidence > 0.7:                                │
│      # 高置信度怀疑 → 立即送收敛层验证                       │
│      enqueue_for_verification(result)                         │
│    elif result.confidence > 0.4:                              │
│      # 中等置信度怀疑 → 存入观察队列，定期重检                 │
│      enqueue_for_observation(result)                        │
│    else:                                                      │
│      # 低置信度怀疑 → 记录负知识，避免重复                     │
│      store_negative_knowledge(result)                       │
│                                                              │
│  Step 4: 验证反馈与迭代                                       │
│  ────────────────────────────────────────                   │
│  等待验证结果：                                               │
│    if 验证通过:                                               │
│      # 怀疑成功，链路存在替代路径或更优解释                     │
│      update_knowledge_graph(result)                           │
│      increase_divergence_budget(seed_node)                  │
│    elif 验证失败:                                             │
│      # 怀疑被证伪，记录失败原因                                │
│      log_failure(result, reason)                             │
│      decrease_divergence_budget(seed_node)                    │
│    elif 验证超时:                                             │
│      # 验证成本过高，标记为"待验证"                           │
│      mark_pending(result)                                    │
│                                                              │
│  Step 5: 回退策略                                             │
│  ────────────────────────────────────────                   │
│  如果所有怀疑都失败：                                          │
│    # 链路确实坚实，增加其置信度                                │
│    increase_link_confidence(A→B→C, delta=0.05)             │
│    # 减少对该链路的怀疑频率                                    │
│    set_suspicion_cooldown(A→B→C, days=30)                   │
│  如果至少一个怀疑成功：                                        │
│    # 系统发现新路径，触发收敛层重新验证                        │
│    trigger_convergence_recheck(A→B→C)                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 怀疑强度的量化控制

```python
class SuspicionIntensity:
    """怀疑强度量化控制器。"""
    
    # 强度等级
    CASUAL = 0.3      # 轻度怀疑：只检查一种形态
    STANDARD = 0.6    # 标准怀疑：检查两种形态
    INTENSE = 0.9     # 强烈怀疑：检查全部四种形态
    
    def compute_intensity(self, link) -> float:
        """基于链路特征计算怀疑强度。"""
        base = 0.5
        
        # 过自信加成
        if link.confidence > 0.9:
            base += 0.2
        
        # 未验证时长加成
        days_since_check = (now() - link.last_verified).days
        if days_since_check > 30:
            base += 0.1
        
        # 用户关注加成（用户多次查询的链路更值得怀疑）
        if link.query_count > 5:
            base += 0.1
        
        # 跨领域加成（跨领域链路更可能隐藏假设）
        if link.cross_domain:
            base += 0.1
        
        return min(base, 1.0)
    
    def select_modes(self, intensity: float) -> list:
        """根据强度选择怀疑形态。"""
        if intensity < 0.4:
            return ["counterfactual"]  # 轻度：只破坏链路
        elif intensity < 0.7:
            return ["counterfactual", "abductive"]  # 标准：破坏+溯因
        else:
            return ["counterfactual", "abductive", "analogical", "inverted"]  # 强烈：全部
```

### 5.4 与元认知仲裁的联动

```
元认知仲裁层决策：

if 发散预算 > 0 且 停滞检测触发:
  intensity = SuspicionIntensity.compute_intensity(stagnant_link)
  modes = SuspicionIntensity.select_modes(intensity)
  
  for mode in modes:
    if 发散预算 <= 0:
      break
    
    result = execute_suspicion(mode, stagnant_link)
    发散预算 -= mode_cost[mode]
    
    if result.confidence > 0.7:
      # 高价值怀疑 → 立即验证
      收敛层验证队列.enqueue(result)
    elif result.confidence > 0.4:
      # 中等价值 → 观察队列
      观察队列.enqueue(result, re_check_interval=30天)
```

---

## 6. 语义向量距离设计（P0）

### 6.1 问题：只有接口声明，无设计细节

v0.1 中提到使用 sentence-transformers 进行语义向量距离计算，但没有设计：
- 使用哪个模型？
- 向量存储和检索策略？
- 与结构匹配的交互方式？
- 当模型不可用时如何回退？

### 6.2 模型选择策略

```python
class SemanticVectorConfig:
    """语义向量配置。"""
    
    # 优先级：先尝试专业模型，后回退通用模型
    MODEL_PRIORITY = [
        "allenai-specter2",      # 科学文献专用，首选
        "sentence-transformers/all-MiniLM-L6-v2",  # 通用，轻量
        "sentence-transformers/all-mpnet-base-v2",  # 通用，高质量
    ]
    
    # 维度配置
    EMBEDDING_DIM = 768  # 与所选模型一致
    
    # 相似度阈值
    SIMILARITY_STRONG = 0.8   # 强相似，可能冗余
    SIMILARITY_WEAK = 0.5     # 弱相似，可能跨域类比
    SIMILARITY_NONE = 0.3     # 不相似，无关
    
    # 缓存配置
    VECTOR_CACHE_SIZE = 10000  # 最多缓存 10000 个向量
    VECTOR_CACHE_TTL = 3600    # 缓存 1 小时
```

### 6.3 向量存储与检索

```python
class VectorStore:
    """语义向量存储与检索。"""
    
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.cache = LRUCache(maxsize=VECTOR_CACHE_SIZE)
    
    def store(self, node_id: str, text: str, embedding: List[float]):
        """存储节点向量。"""
        # 写入数据库
        self.db.execute('''
            INSERT INTO node_embeddings (node_id, text_hash, embedding, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(node_id) DO UPDATE SET
                text_hash = excluded.text_hash,
                embedding = excluded.embedding,
                created_at = CURRENT_TIMESTAMP
        ''', (node_id, hash(text), json.dumps(embedding)))
        
        # 更新缓存
        self.cache[node_id] = embedding
    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Tuple[str, float]]:
        """向量相似度搜索。"""
        # 从缓存中批量加载
        candidates = []
        for node_id, embedding in self.cache.items():
            sim = cosine_similarity(query_embedding, embedding)
            candidates.append((node_id, sim))
        
        # 按相似度排序，返回 top_k
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]
    
    def find_semantic_duplicates(self, node_id: str, threshold: float = 0.95) -> List[str]:
        """查找语义重复（用于创新度评估）。"""
        query_embedding = self.cache.get(node_id)
        if query_embedding is None:
            return []
        
        duplicates = []
        for other_id, other_embedding in self.cache.items():
            if other_id == node_id:
                continue
            sim = cosine_similarity(query_embedding, other_embedding)
            if sim > threshold:
                duplicates.append(other_id)
        
        return duplicates
```

### 6.4 与 CSM 结构匹配的交互

```
CSM 三层匹配中的语义层：

Step 1: 结构匹配（VF2）
  score_structural = vf2_matcher.match(g1, g2)
  if score_structural < 0.3:
    # 结构不匹配，直接判定为 UNRELATED
    return AnalogyVerdict.UNRELATED

Step 2: 元角色对齐
  score_role = role_aligner.align(g1, g2)
  if score_role < 0.3:
    # 角色冲突，可能语义相似但功能不同
    # 进入语义层验证

Step 3: 语义向量过滤
  # 提取两个图的文本描述
  text1 = extract_graph_description(g1)
  text2 = extract_graph_description(g2)
  
  # 计算语义相似度
  embedding1 = vector_store.encode(text1)
  embedding2 = vector_store.encode(text2)
  score_semantic = cosine_similarity(embedding1, embedding2)
  
  # 语义相似度作为"软匹配"信号
  if score_semantic > SIMILARITY_STRONG:
    # 语义强相似，但结构不匹配 → 可能同义不同形
    return AnalogyVerdict.WEAKLY_ISOMORPHIC
  elif score_semantic > SIMILARITY_WEAK:
    # 中等语义相似 → 跨域类比候补
    return AnalogyVerdict.WEAKLY_ISOMORPHIC
  else:
    # 语义不相似 → 确认无关
    return AnalogyVerdict.UNRELATED

Step 4: 综合评分
  combined = 0.5 * score_structural + 0.3 * score_role + 0.2 * score_semantic
```

### 6.5 回退策略

```python
def compute_semantic_similarity(text_a: str, text_b: str) -> float:
    """计算语义相似度，带完整回退链。"""
    
    # 尝试 1：sentence-transformers（首选）
    try:
        model = get_sentence_transformer()
        emb_a = model.encode(text_a)
        emb_b = model.encode(text_b)
        return cosine_similarity(emb_a, emb_b)
    except ImportError:
        pass
    
    # 尝试 2：OpenAI API（备用）
    try:
        emb_a = openai_embedding(text_a)
        emb_b = openai_embedding(text_b)
        return cosine_similarity(emb_a, emb_b)
    except Exception:
        pass
    
    # 尝试 3：TF-IDF 余弦相似度（本地回退）
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform([text_a, text_b])
        return cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0][0]
    except ImportError:
        pass
    
    # 尝试 4：Jaccard 相似度（最终回退）
    set_a = set(text_a.split())
    set_b = set(text_b.split())
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
```

### 6.6 数据库表设计

```sql
-- 语义向量存储表
CREATE TABLE IF NOT EXISTS node_embeddings (
    node_id TEXT PRIMARY KEY,
    text_hash TEXT NOT NULL,  -- 用于检测文本是否变化
    embedding BLOB NOT NULL,  -- JSON 序列化的向量
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

-- 语义相似度缓存表（避免重复计算）
CREATE TABLE IF NOT EXISTS semantic_similarity_cache (
    node_a_id TEXT NOT NULL,
    node_b_id TEXT NOT NULL,
    similarity REAL NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (node_a_id, node_b_id)
);

CREATE INDEX idx_similarity_high ON semantic_similarity_cache(similarity)
WHERE similarity > 0.8;
```

---

## 7. 总结：v0.1 → v0.2 的变更清单

| 变更项 | v0.1 状态 | v0.2 补充 | 影响 |
|--------|----------|----------|------|
| 双权重约束 | 独立记录层 | 升级为发散约束条件 | 高 |
| 全局权重重标定 | 独立量化系统 | 与L5预算分配联动 | 中 |
| 假设生成器 | 随机占位实现 | 三类生成策略（结构/语义/LLM） | 高 |
| 主动破坏机制 | 哲学描述 | 完整决策流程 + 强度控制 | 高 |
| 语义向量距离 | 接口声明 | 完整设计（模型/存储/检索/回退） | 中 |

**下一步工程行动：**
1. 实现双权重约束嵌入（2天）
2. 实现全局权重重标定耦合（1天）
3. 实现结构驱动假设生成器（3天）
4. 实现语义驱动假设生成器（2天）
5. 实现主动破坏决策流程（2天）
6. 实现语义向量存储与检索（2天）

**总工期：12天（并行）/ 8天（串行）**

---

> **文档结束。** 本补充文档与 v0.1 合并后，构成发散层完整设计。
