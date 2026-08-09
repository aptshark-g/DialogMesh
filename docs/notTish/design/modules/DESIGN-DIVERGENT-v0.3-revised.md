# Literature Cortex — 发散层设计补充 v0.3 (REVISED)

> **文档编号:** LC-DESIGN-DIVERGENT-v0.3-revised
> **版本:** v0.3
> **日期:** 2026-06-26
> **依赖:** LC-DESIGN-DIVERGENT-v0.1, LC-DESIGN-WEIGHT-QUANT-v1.0, LC-DESIGN-v5.4, LC-DESIGN-v6.0-UNIFIED
> **核心目标:** 补全 v0.1 中未完善的设计细节，将四个核心缺口从"框架"推进到"可工程化"

---

## 1. 补充内容概述

v0.1 设计文档完成了发散层框架和哲学基础，但以下四方面存在关键缺口，本补充将逐一补齐并给出可直接工程化的方案：

| 缺口 | 核心问题 | 补充章节 |
|------|---------|---------|
| **"破坏与怀疑"主动化不足** | 反事实引擎只做"删边检查"，是"保守检修员"而非"科学批评者" | 第2章 |
| **全局权重重标定维度缺失** | 只有access_count/last_accessed，缺少根基性+解构频率 | 第3章 |
| **双权重约束未编码为决策** | 有双计数但发散引擎决策时未使用 | 第4章 |
| **假设生成器与CSM脱节** | 占位实现，未接入VF2/CSM/持久化层 | 第5章 |

---

## 2. "破坏与怀疑"主动化：从"删边检查"到"置换-验证-评估"

### 2.1 问题诊断

v0.1 中反事实引擎的核心逻辑：
```python
# 当前实现（保守检修员）
def break_link(path, edge_to_remove):
    remove_edge(edge_to_remove)
    is_reachable = check_reachable(source, target)
    return "目标仍可达" if is_reachable else "目标不可达"
```

这只是在问：**"如果这个零件坏了，系统还能用吗？"**

但发散层应该问：**"为什么这条链是唯一的？为什么不能有别的路？"**

### 2.2 主动破坏机制：置换-验证-评估

**核心升级：** 将反事实引擎与假设生成器（AbductiveEngine）耦合，从"删边检查"升级为"主动置换"。

```
给定收敛链路 a→b→c：

Step 1: 主动置换（置换而非删除）
  调用 AbductiveEngine，查找与 b 在语义/结构上相近的候选节点 {d₁, d₂, ...}
  
  候选节点来源：
  - 结构来源：VF2子图匹配中，与 b 结构签名相似的其他节点
  - 语义来源：向量嵌入空间中，与 b 余弦相似度 > 0.6 的邻居
  - 持久化来源：analogical_matches 表中已有记录的跨域映射节点

Step 2: 约束可行性验证（CVE介入）
  对每个候选 dᵢ：
    a) 测试 a→dᵢ 的边是否可建立（结构兼容性检查）
    b) 测试 dᵢ→c 的边是否可建立（功能兼容性检查）
    c) 使用 CVE 引擎评估约束变化类型：
       - Type-A（技术创新）：约束变化带来性能提升
       - Type-B（工程权衡）：约束变化带来成本/复杂度变化
       - Type-C（作弊/简化）：约束变化降低模型可信度 → 直接过滤

Step 3: 潜力分数评估
  对通过约束验证的候选 dᵢ，计算：
  
  potential_score(dᵢ) = α * structural_similarity(b, dᵢ)
                        + β * semantic_similarity(b, dᵢ)
                        + γ * constraint_feasibility(a→dᵢ→c)
                        + δ * innovation_value(cve_type)
  
  其中：
  - α = 0.25（结构权重）
  - β = 0.25（语义权重）
  - γ = 0.30（约束可行性权重，最高）
  - δ = 0.20（创新价值权重）
  - innovation_value(Type-A) = 1.0, Type-B = 0.5, Type-C = 0.0（已过滤）

Step 4: 输出"破坏报告"（非简单的"可替代/不可替代"）
  {
    "type": "active_destruction_report",
    "original_link": "a→b→c",
    "operation": "replace",
    "target_node": "b",
    "candidate_replacements": [
      {
        "node": "d₁",
        "new_link": "a→d₁→c",
        "potential_score": 0.82,
        "structural_similarity": 0.85,
        "semantic_similarity": 0.78,
        "constraint_feasibility": 0.90,
        "innovation_value": 1.0,  // Type-A
        "why_valuable": "d₁引入在线辨识，可突破10.82dB上限",
        "verification_needed": true
      },
      {
        "node": "d₂",
        "new_link": "a→d₂→c",
        "potential_score": 0.45,
        "structural_similarity": 0.60,
        "semantic_similarity": 0.55,
        "constraint_feasibility": 0.40,
        "innovation_value": 0.5,  // Type-B
        "why_valuable": "d₂简化传感器数量但牺牲精度，需权衡",
        "verification_needed": true
      }
    ],
    "best_candidate": "d₁",
    "insight": "原始链路 a→b→c 并非唯一路径，存在至少2个结构/语义兼容的替代节点"
  }
```

### 2.3 为什么这是"主动发现"而非"被动检查"

| 维度 | 旧机制（删边检查） | 新机制（置换-验证） |
|------|-------------------|-------------------|
| 操作 | 删除边，观察系统是否崩溃 | 替换节点，验证新链路是否可行 |
| 输出 | "目标仍可达/不可达" | "d₁可替代，潜力0.82，原因：..." |
| 信息量 | 二元（是/否） | 多维（结构/语义/约束/创新） |
| 对创新贡献 | 仅确认链路关键性 | 直接发现新路径和升级方向 |
| 与假设生成器关系 | 独立运行 | 深度耦合（AbductiveEngine提供候选） |

### 2.4 接口定义

```python
class ActiveDestructionEngine:
    """主动破坏引擎：从"删边检查"升级为"置换-验证-评估"。"""
    
    def __init__(self, abductive_engine: AbductiveEngine, 
                 cve_engine: CVEEvaluator,
                 csm_orchestrator: CSMOrchestrator):
        self.abductive = abductive_engine
        self.cve = cve_engine
        self.csm = csm_orchestrator
    
    def destroy(self, link: str, target_node: str) -> ActiveDestructionReport:
        """
        对链路中的指定节点执行主动破坏。
        
        流程：
        1. 调用 AbductiveEngine 查找候选替代节点
        2. 对每个候选：VF2结构验证 + 向量语义验证 + CVE约束评估
        3. 计算潜力分数，排序输出
        """
        # Step 1: 获取候选节点
        candidates = self.abductive.find_alternatives(target_node, top_k=10)
        
        # Step 2: 验证每个候选
        validated = []
        for candidate in candidates:
            new_link = link.replace(target_node, candidate)
            
            # 2a: 结构验证
            struct_sim = self.csm.vf2_match(target_node, candidate)
            
            # 2b: 语义验证
            sem_sim = self.csm.semantic_filter(target_node, candidate)
            
            # 2c: 约束验证
            constraint_check = self.cve.evaluate_constraint_change(
                original=link,
                modified=new_link
            )
            
            # 过滤 Type-C
            if constraint_check.value_verdict == ValueVerdict.TYPE_C_CHEATING:
                continue
            
            # 2d: 潜力分数
            potential = self._compute_potential(
                struct_sim, sem_sim, 
                constraint_check.feasibility,
                constraint_check.value_verdict
            )
            
            validated.append({
                "node": candidate,
                "new_link": new_link,
                "potential_score": potential,
                "structural_similarity": struct_sim,
                "semantic_similarity": sem_sim,
                "constraint_feasibility": constraint_check.feasibility,
                "innovation_value": constraint_check.value_verdict,
                "why_valuable": self._generate_insight(constraint_check),
            })
        
        # Step 3: 排序并输出报告
        validated.sort(key=lambda x: x["potential_score"], reverse=True)
        return ActiveDestructionReport(
            original_link=link,
            target_node=target_node,
            candidates=validated,
            best_candidate=validated[0] if validated else None
        )
    
    def _compute_potential(self, struct_sim, sem_sim, feasibility, cve_type) -> float:
        """计算潜力分数。"""
        alpha, beta, gamma, delta = 0.25, 0.25, 0.30, 0.20
        innovation_map = {ValueVerdict.TYPE_A_TECHNOLOGY: 1.0,
                         ValueVerdict.TYPE_B_ENGINEERING: 0.5,
                         ValueVerdict.TYPE_C_CHEATING: 0.0}
        return (alpha * struct_sim + beta * sem_sim + 
                gamma * feasibility + delta * innovation_map.get(cve_type, 0))
```

---

## 3. 全局权重重标定：扩展根基性+解构频率

### 3.1 问题诊断

v0.1 中 `node_activation` 表只有 `access_count` 和 `last_accessed`：
```sql
CREATE TABLE node_activation (
    node_id TEXT PRIMARY KEY,
    access_count INTEGER DEFAULT 0,   -- 被查次数
    last_accessed TIMESTAMP,          -- 最近访问
    base_activation REAL DEFAULT 0.0,
    spreading_weight REAL DEFAULT 0.0
);
```

这只能反映节点"**热不热**"（最近是否被访问），不能反映节点"**重不重要**"（在知识体系中的位置）。

### 3.2 扩展：增加根基性与解构频率

**新增字段：**
```sql
ALTER TABLE node_activation ADD COLUMN foundational_score REAL DEFAULT 0.0;
ALTER TABLE node_activation ADD COLUMN deconstruction_count INTEGER DEFAULT 0;
```

**字段含义：**

| 字段 | 含义 | 计算方式 | 取值范围 |
|------|------|---------|---------|
| `foundational_score` | 根基性：节点在L0-L4知识体系中的层级 | 基于种子库深度：L0=1.0, L1=0.8, L2=0.6, L3=0.4, L4=0.2, 非种子库=0.0 | [0, 1] |
| `deconstruction_count` | 解构频率：节点被主动关注（作为目标）的次数 | 每次被AbductiveEngine/CounterfactualEngine作为目标时+1 | [0, ∞) |

### 3.3 修改激活公式

**旧公式（v0.1）：**
```
Activation(n) = ln(freq_n + 1) − λ * ln(Δt_n + 1) + Σ w_i * Activation(n_i)
```

**新公式（v0.3）：**
```
Activation(n) = [ln(freq_n + 1) − λ * ln(Δt_n + 1)] * foundational_score(n) 
                + μ * deconstruction_count(n)
                + Σ w_i * Activation(n_i)
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `λ` | 0.5 | 遗忘衰减系数（不变） |
| `μ` | 0.1 | 解构频率权重（新增，控制解构次数对激活度的影响强度） |
| `foundational_score` | 动态 | 根基性乘数：高根基性节点即使低频，也能保持较高激活度 |

**关键变化：**

- **根基性作为乘数**：高根基性节点（如"反馈控制"L0）的 `foundational_score=1.0`，其激活度不会被衰减到极低。即使很久未被访问，仍保持可达。
- **解构频率作为加数**：被主动解构的节点获得额外激活度 boost，确保"被怀疑的对象"不会从视野中消失。

### 3.4 工程实现

```python
class EnhancedActivationTracker(ActivationTracker):
    """增强版激活追踪器：增加根基性与解构频率。"""
    
    def __init__(self, db, lambda_decay=0.5, mu_deconstruction=0.1):
        super().__init__(db, lambda_decay)
        self.mu = mu_deconstruction
    
    def compute_activation(self, node_id: str) -> float:
        """计算节点当前激活度（增强公式）。"""
        row = self.db.fetchone('''
            SELECT access_count, last_accessed, base_activation,
                   foundational_score, deconstruction_count
            FROM node_activation WHERE node_id = ?
        ''', (node_id,))
        
        if not row:
            return -float('inf')
        
        freq, last, base, foundational, deconstruction = row
        
        # 1. 基础双权重（频率 + 新近性）
        delta_t = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
        base_activation = math.log(freq + 1) - self.lambda_decay * math.log(delta_t + 1)
        
        # 2. 根基性乘数（关键升级）
        # 高根基性节点即使低频，也能保持较高激活度
        weighted_base = base_activation * foundational
        
        # 3. 解构频率加数（关键升级）
        # 被主动解构的节点获得额外激活度
        deconstruction_boost = self.mu * deconstruction
        
        # 4. 传播激活（Hebbian，保持不变）
        spreading = self._compute_spreading(node_id)
        
        return weighted_base + deconstruction_boost + spreading
    
    def record_deconstruction(self, node_id: str):
        """记录节点被解构（作为目标）。"""
        self.db.execute('''
            UPDATE node_activation 
            SET deconstruction_count = deconstruction_count + 1
            WHERE node_id = ?
        ''', (node_id,))
        self.db.commit()
    
    def set_foundational_score(self, node_id: str, layer_level: int):
        """根据L0-L4层级设置根基性分数。"""
        # L0=1.0, L1=0.8, L2=0.6, L3=0.4, L4=0.2
        score = max(0.0, 1.0 - layer_level * 0.2)
        self.db.execute('''
            UPDATE node_activation SET foundational_score = ? WHERE node_id = ?
        ''', (score, node_id))
        self.db.commit()
```

### 3.5 对发散引擎的影响

**根基性影响：** 发散起点优先从L0-L1层级节点出发（系统核心），而非随机活跃节点。

**解构频率影响：** 被多次解构的节点（如"FxLMS"被反复质疑）保持高激活度，确保系统持续探索其边界。

```python
def select_divergence_seeds(self, top_k=5) -> List[str]:
    """选择发散起点（基于增强激活度）。"""
    return self.db.fetchall('''
        SELECT node_id, 
               (ln(access_count + 1) - ? * ln(julianday('now') - julianday(last_accessed) + 1)) 
               * foundational_score + ? * deconstruction_count as enhanced_activation
        FROM node_activation
        WHERE enhanced_activation > ?
        ORDER BY enhanced_activation DESC
        LIMIT ?
    ''', (self.lambda_decay, self.mu, self.theta_start, top_k))
```

---

## 4. 双权重约束机制：编码为决策参数

### 4.1 问题诊断

v0.1 中双权重机制（`access_count` + `last_accessed`）只是**数据记录**，发散引擎在决策时**未将其作为约束条件**使用。

系统决定"下一步发散从哪里开始"时，应该主动区分：
- **长期记忆路径**（最常使用的节点）
- **短期记忆路径**（最近使用的节点）

### 4.2 工程化：constraint_mode 参数

在 `DivergenceEngine` 中增加 `constraint_mode` 参数，直接编码人脑认知倾向：

```python
class DivergenceEngine:
    """发散引擎：支持双权重约束模式。"""
    
    class ConstraintMode(Enum):
        """约束模式：模拟人脑不同认知倾向。"""
        RECENT = "recent"      # 短期记忆驱动：只从最近24h访问的节点中选择
        FREQUENT = "frequent"  # 长期记忆驱动：只从历史频率最高的节点中选择
        DUAL = "dual"          # 双权重融合：最常用(0.6) + 最近(0.4)
        BALANCED = "balanced"  # 平衡模式：直接按增强激活度排序
    
    def __init__(self, ..., constraint_mode: ConstraintMode = ConstraintMode.DUAL):
        self.constraint_mode = constraint_mode
    
    def select_start_nodes(self, top_k: int = 5) -> List[Tuple[str, float]]:
        """根据约束模式选择发散起点。"""
        if self.constraint_mode == ConstraintMode.RECENT:
            return self._select_recent(top_k)
        elif self.constraint_mode == ConstraintMode.FREQUENT:
            return self._select_frequent(top_k)
        elif self.constraint_mode == ConstraintMode.DUAL:
            return self._select_dual(top_k)
        else:
            return self._select_balanced(top_k)
    
    def _select_recent(self, top_k: int) -> List[Tuple[str, float]]:
        """短期记忆驱动：只从最近24h访问的节点中选择。"""
        return self.db.fetchall('''
            SELECT node_id, 
                   (1.0 / (julianday('now') - julianday(last_accessed) + 1)) as recency_score
            FROM node_activation
            WHERE last_accessed > datetime('now', '-1 day')
            ORDER BY recency_score DESC
            LIMIT ?
        ''', (top_k,))
    
    def _select_frequent(self, top_k: int) -> List[Tuple[str, float]]:
        """长期记忆驱动：只从历史频率最高的节点中选择。"""
        return self.db.fetchall('''
            SELECT node_id, ln(access_count + 1) as frequency_score
            FROM node_activation
            ORDER BY frequency_score DESC
            LIMIT ?
        ''', (top_k,))
    
    def _select_dual(self, top_k: int) -> List[Tuple[str, float]]:
        """双权重融合：最常用(0.6) + 最近(0.4)。"""
        return self.db.fetchall('''
            SELECT node_id,
                   0.6 * ln(access_count + 1) 
                   + 0.4 * (1.0 / (julianday('now') - julianday(last_accessed) + 1))
                   as dual_score
            FROM node_activation
            ORDER BY dual_score DESC
            LIMIT ?
        ''', (top_k,))
```

### 4.3 与L5元认知仲裁的联动

```python
class MetaCognitiveArbiter:
    def decide_mode(self, query_context: str) -> DivergenceEngine.ConstraintMode:
        """根据查询上下文决定约束模式。"""
        
        # 用户要求"快速回顾"或"最近进展" → 短期记忆
        if any(kw in query_context for kw in ["最近", "最新", "进展", "更新"]):
            return DivergenceEngine.ConstraintMode.RECENT
        
        # 用户要求"深度探索"或"核心知识" → 长期记忆
        if any(kw in query_context for kw in ["深度", "核心", "基础", "根本"]):
            return DivergenceEngine.ConstraintMode.FREQUENT
        
        # 用户要求"全面分析"或"综合评估" → 双权重融合
        if any(kw in query_context for kw in ["全面", "综合", "整体", "系统"]):
            return DivergenceEngine.ConstraintMode.DUAL
        
        # 默认：平衡模式
        return DivergenceEngine.ConstraintMode.BALANCED
```

### 4.4 为什么这比v0.2更直接

v0.2 设计中，双权重是"发散约束条件"（起点过滤、传播剪枝、假设排序），但**没有明确区分长期/短期记忆的选择策略**。

v0.3 直接将 `constraint_mode` 编码为 `DivergenceEngine` 的参数，让L5可以通过调整模式来**模拟不同的人脑认知倾向**：

| 任务类型 | 推荐模式 | 人脑类比 |
|---------|---------|---------|
| "最近有什么新发现？" | RECENT | 工作记忆回溯 |
| "最核心的知识是什么？" | FREQUENT | 长期记忆提取 |
| "全面分析这个问题" | DUAL | 前额叶统筹协调 |
| 默认状态 | BALANCED | 默认认知模式 |

---

## 5. 假设生成器真实化：接入CSM与持久化层

### 5.1 问题诊断

当前 `MetaCognitiveArbiter._generate_semantic_bridge()` 是占位实现：
```python
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

这**没有使用任何真实知识**，只是生成3个随机假设。需要将其接入：
- **VF2结构匹配**（结构层面）
- **ConstraintSpaceMapper**（语义层面）
- **持久化层**（已有假设表）

### 5.2 重写假设生成器：接入CSM三层匹配

```python
class CSMHypothesisGenerator(HypothesisGenerator):
    """基于CSM三层匹配的假设生成器。"""
    
    def __init__(self, csm_orchestrator: CSMOrchestrator, 
                 vector_store: VectorStore,
                 db: sqlite3.Connection):
        self.csm = csm_orchestrator
        self.vector_store = vector_store
        self.db = db
    
    def generate(self, seed: DivergenceSeed, context: DivergenceContext) -> List[Hypothesis]:
        """
        生成假设，接入CSM三层匹配。
        
        流程：
        1. 从持久化层检索已有假设（避免重复生成）
        2. 从结构层（VF2）获取候选节点
        3. 从语义层（ConstraintSpaceMapper）获取候选节点
        4. 对每个候选：CSM三层匹配 → 综合评分
        5. 过滤（相似度 > 0.6）→ 输出有效假设
        """
        hypotheses = []
        
        # Step 1: 从持久化层检索已有假设
        existing = self._load_existing_hypotheses(seed.node_id)
        hypotheses.extend(existing)
        
        # Step 2: 结构层候选（VF2子图匹配）
        struct_candidates = self.csm.vf2_matcher.find_similar_structures(seed.node_id, top_k=5)
        
        # Step 3: 语义层候选（向量空间最近邻）
        sem_candidates = self.vector_store.find_neighbors(seed.node_id, top_k=5)
        
        # 合并候选池，去重
        all_candidates = set(struct_candidates + sem_candidates)
        
        # Step 4: 对每个候选执行CSM三层匹配
        for candidate in all_candidates:
            if candidate == seed.node_id:
                continue
            
            # CSM三层匹配
            csm_result = self.csm.evaluate(seed.node_id, candidate)
            
            # 过滤：只保留相似度 > 0.6 的候选
            if csm_result.combined_score < 0.6:
                continue
            
            # Step 5: 生成假设，附带CSM置信度作为 validity_score
            hypothesis = Hypothesis(
                id=f"{seed.node_id}::csm::{candidate}",
                source_fact_id=seed.node_id,
                generator="csm_three_layer_match",
                text=f"{seed.node_id} 与 {candidate} 存在跨域/同域类比关系",
                total_value=csm_result.combined_score,  # CSM综合评分作为价值
                validity_score=csm_result.combined_score,  # CSM置信度作为有效性
                structural_evidence=csm_result.structural_score,
                semantic_evidence=csm_result.semantic_score,
                role_evidence=csm_result.role_score,
            )
            hypotheses.append(hypothesis)
        
        # 按 validity_score 降序排序
        hypotheses.sort(key=lambda h: h.validity_score, reverse=True)
        return hypotheses[:context.budget]  # 受预算限制
    
    def _load_existing_hypotheses(self, node_id: str) -> List[Hypothesis]:
        """从持久化层加载已有假设。"""
        rows = self.db.fetchall('''
            SELECT id, hypothesis, confidence, verification_status
            FROM abductive_hypothesis
            WHERE observation LIKE ?
        ''', (f"%{node_id}%",))
        
        return [
            Hypothesis(
                id=row[0],
                source_fact_id=node_id,
                generator="persistence_layer",
                text=row[1],
                total_value=row[2],
                validity_score=row[2],
            )
            for row in rows
        ]
```

### 5.3 关键接口：CSM与发散层的桥接

```python
class CSMToDivergenceBridge:
    """CSM核心引擎与发散层的桥接接口。"""
    
    def __init__(self, csm_flow: CSMCognitiveFlow, divergence_engine: DivergenceEngine):
        self.csm = csm_flow
        self.divergence = divergence_engine
    
    def feed_csm_results_to_divergence(self, csm_result: CSMCognitiveFlowResult):
        """将CSM匹配结果送入发散层作为假设种子。"""
        
        if csm_result.verdict == AnalogyVerdict.STRONGLY_ISOMORPHIC:
            # 强匹配：直接生成假设，高置信度
            hypothesis = Hypothesis(
                text=f"强匹配：{csm_result.node_a} 与 {csm_result.node_b} 结构/语义同构",
                total_value=csm_result.combined_score,
                validity_score=csm_result.combined_score,
            )
            self.divergence.inject_hypothesis(hypothesis, priority=1.0)
        
        elif csm_result.verdict == AnalogyVerdict.WEAKLY_ISOMORPHIC:
            # 弱匹配：存入观察队列，定期重检
            self.divergence.observation_queue.enqueue(
                csm_result,
                re_check_interval=timedelta(days=30)
            )
        
        elif csm_result.verdict == AnalogyVerdict.UNRELATED:
            # 不匹配：存入负知识库
            self.divergence.negative_matches.store(
                (csm_result.node_a, csm_result.node_b),
                failure_mode=csm_result.classify_failure()
            )
```

### 5.4 为什么这是关键接口

没有这个接口，CSM跑得再好，发散层也无法利用。具体场景：

| 场景 | 没有桥接 | 有桥接 |
|------|---------|--------|
| CSM发现"PID→FxLMS"与"温控器→在线补偿"结构同构 | 结果停留在CSM层，发散层不知道 | 发散层自动生成假设："热控能否借鉴ANC自适应结构？" |
| CSM发现"FxLMS"与"LMS"语义相似但功能不同 | 结果丢弃 | 发散层生成质疑："FxLMS的额外约束是否必要？" |
| 持久化层已有"FxLMS→温度补偿"的假设 | 每次重新生成，重复计算 | 直接加载已有假设，避免重复 |

---

## 6. 总结：v0.1 → v0.3 的变更清单

| 变更项 | v0.1 状态 | v0.3 改进 | 影响 |
|--------|----------|----------|------|
| **主动破坏机制** | "删边检查"（保守检修员） | **"置换-验证-评估"**（科学批评者），耦合AbductiveEngine+CVE，输出潜力分数 | 高 |
| **全局权重重标定** | 只有access_count/last_accessed | **增加foundational_score+deconstruction_count**，修改激活公式（根基性乘数+解构加数） | 高 |
| **双权重约束** | 双计数作为记录 | **`constraint_mode`参数**（RECENT/FREQUENT/DUAL/BALANCED），直接编码人脑认知倾向 | 高 |
| **假设生成器** | 随机占位 | **接入CSM三层匹配**（VF2结构+向量语义+角色对齐），`validity_score`来自CSM综合评分 | 高 |

**下一步工程行动（按优先级）：**

1. **修改数据库schema**：增加`foundational_score`和`deconstruction_count`字段（0.5天）
2. **实现ActiveDestructionEngine**：置换-验证-评估流程（2天）
3. **重写假设生成器**：接入CSM三层匹配（2天）
4. **实现ConstraintMode**：双权重约束编码（1天）
5. **更新激活公式**：根基性乘数+解构加数（1天）
6. **实现CSM→Divergence桥接**：`feed_csm_results_to_divergence`（1天）

**总工期：7.5天（并行）/ 5天（串行，按优先级顺序）**

---

> **文档结束。** 本补充文档与 v0.1 合并后，构成发散层可直接工程化的完整设计。所有接口定义、参数表、SQL语句均可在实现阶段直接复用。
