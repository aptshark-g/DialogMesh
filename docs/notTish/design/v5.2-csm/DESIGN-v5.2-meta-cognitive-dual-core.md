# Literature Cortex v5.2 设计方案：元认知双核心协调引擎

> **文档编号:** LC-DESIGN-v5.2
> **版本:** v5.2-FINAL
> **状态:** 🔄 WIP（Phase 1 完成，Phase 2 待做）
> **完成度:** 40%
> **日期:** 2026-06-16
> **状态:** 设计冻结，待实施
> **依赖:** v5.1 双网络协调设计（Schema 设计完整，实现被简化）
> **注册表:** 参见 `DESIGN-REGISTRY.md` 第 #design-文档清单 节
> **核心升级:** 从「双网络协调」到「元认知仲裁」——增加拍板层（Meta-Cognitive Arbiter）

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-16 | v5.2-FINAL | 初始设计，Phase 1（数据层）完成 |

---

## 修正声明（从 v5.1 到 v5.2）

| v5.1 问题 | v5.2 修正方向 |
|-----------|--------------|
| 双网络协调后无人拍板 | 新增**元认知仲裁层**：决定何时发散、何时收敛、何时切换视角 |
| 发散假设无限生成 | 新增**发散预算控制**：每个种子节点最多 N 个假设，按验证历史动态调整权重 |
| 收敛陷入局部最优无感知 | 新增**收敛停滞检测**：depth=3 内无新假设 → 触发发散扰动 |
| 多视角冲突无仲裁 | 新增**视角切换仲裁**：保留所有视角 + 标记 primary_perspective |
| 无验证反馈循环 | 新增**假设验证反馈**：高通过率方向提升权重，低通过率归档 |
| 概念浮动只存在于设计 | **强制实施**：`node_perspectives` 表必须落地，替代单值 `knowledge_level` |

---

## 1. 问题陈述

### 1.1 v5.1 的遗留问题

v5.1 解决了"单一层级误匹配"问题，但留下了三个核心缺陷：

**缺陷一：发散无节制**

```
DivergentCore.generate_from_fact(fxlms)
→ 语义桥接：20 个候选
→ 反事实扰动：3 个候选  
→ 结构同构：3 个候选
→ 总计：26 个假设
→ 全部进入验证队列？
→ 系统爆炸。
```

v5.1 有 `total_value` 排序，但阈值和预算是硬编码的，没有根据验证历史学习。

**缺陷二：收敛无感知**

```
DeductionEngine.run_forward(fxlms, max_depth=3)
→ depth=1: 8 个新假设
→ depth=2: 2 个新假设
→ depth=3: 0 个新假设
→ 系统不知道"这条路走死了"
→ 继续浪费算力
```

v5.1 的正向演绎没有"停滞检测"机制，无法判断何时应该切换策略。

**缺陷三：视角冲突无人裁决**

```
FxLMS: 
  - vibration_control 视角 → L3 (算法)
  - thermal_coupling 视角 → L4 (系统)
  - fpga_impl 视角 → L5 (实现)

查询："FxLMS 的物理基础是什么？"
→ 应该回答 L3→L1（算法→公理）
→ 还是应该回答 L4→L1（系统→公理）？
→ v5.1 没有 primary_perspective 机制
```

### 1.2 核心目标

在 v5.1 双网络协调基础上，增加**元认知仲裁层**，实现：

1. **发散预算控制**：根据验证历史动态分配发散资源
2. **收敛停滞检测**：识别局部最优陷阱，自动触发发散
3. **视角切换仲裁**：保留多视角，但标记 primary，查询时默认使用
4. **验证反馈循环**：假设验证结果反馈到权重调整
5. **强制多视角落地**：`node_perspectives` 表替代单值 `knowledge_level`

---

## 2. 核心架构：三层仲裁模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                    应用层 (API / UI / Pipeline)                      │
├─────────────────────────────────────────────────────────────────────┤
│                    元认知仲裁层 (Meta-Cognitive Arbiter)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 发散预算控制  │  │ 收敛停滞检测  │  │ 视角切换仲裁  │              │
│  │ Anti-Bloat   │  │ Convergence  │  │ Perspective  │              │
│  │ Controller   │  │ Monitor      │  │ Arbiter      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  验证反馈循环 (Validation Feedback Loop)        │  │
│  │     假设 → 验证 → 结果 → 权重调整 → 预算再分配                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                    双网络协调层 (Dual-Network Coordination)          │
│  ┌─────────────────────┐    ┌─────────────────────┐                │
│  │ 层级网络 (Convergent)│ ↔ │ 发散网络 (Divergent)│                │
│  │ • 六层结构验证       │    │ • 子模块解构         │                │
│  │ • 约束规则校验       │    │ • 模糊关联发现       │                │
│  │ • 多视角管理         │    │ • 误匹配修正建议     │                │
│  │ • 正向演绎           │    │ • 反事实扰动         │                │
│  └─────────────────────┘    └─────────────────────┘                │
├─────────────────────────────────────────────────────────────────────┤
│                    持久化层 (Persistence Layer)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ nodes_v2 │  │node_persp│  │persp_vali│  │ hypo_arch│           │
│  │ edges_v2 │  │ edges_v2 │  │dation    │  │ ive      │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

**关键升级：v5.1 是「双网络协调」，v5.2 是「三层仲裁」。元认知层位于双网络之上，控制双网络的生命周期。**

---

## 3. 元认知仲裁层详细设计

### 3.1 发散预算控制 (Anti-Bloat Controller)

**问题：** 发散假设无限生成。

**机制：**

```python
class AntiBloatController:
    """发散预算控制器。"""
    
    DEFAULT_BUDGET = 10  # 每个种子节点默认最多生成 10 个假设
    
    def __init__(self, store: ConvergentStoreV2):
        self.store = store
        self.budget_history = {}  # 记录每个方向的预算消耗和验证结果
    
    def allocate_budget(self, seed_node_id: str, generator_type: str) -> int:
        """为指定种子节点和生成器类型分配预算。
        
        预算计算公式：
        budget = base_budget * direction_multiplier * recency_discount
        
        direction_multiplier: 基于该方向的验证历史
            - 高验证通过率 (>0.7): 1.5x
            - 中验证通过率 (0.3-0.7): 1.0x
            - 低验证通过率 (<0.3): 0.5x
            - 无历史记录: 1.0x
        
        recency_discount: 最近 7 天内该方向的生成频率
            - 频率 > 5 次/天: 0.5x (防止重复生成)
            - 频率 1-5 次/天: 1.0x
            - 无近期记录: 1.2x (鼓励探索新方向)
        """
        base = self.DEFAULT_BUDGET
        mult = self._get_direction_multiplier(seed_node_id, generator_type)
        disc = self._get_recency_discount(seed_node_id, generator_type)
        return max(1, int(base * mult * disc))
    
    def consume_budget(self, seed_node_id: str, generator_type: str, 
                       hypotheses: list[dict]) -> list[dict]:
        """消耗预算，截断超限假设。按 total_value 降序保留。"""
        budget = self.allocate_budget(seed_node_id, generator_type)
        hypotheses.sort(key=lambda h: h.get("total_value", 0), reverse=True)
        return hypotheses[:budget]
```

**效果：**
- 新方向（无历史记录）：预算 12，鼓励探索
- 高通过率方向（已验证有效）：预算 15，重点投入
- 低通过率方向（经常失败）：预算 5，限制资源浪费
- 近期已大量生成：预算 5-6，防止重复

### 3.2 收敛停滞检测 (Convergence Monitor)

**问题：** 正向演绎陷入局部最优，系统无感知。

**机制：**

```python
class ConvergenceMonitor:
    """收敛停滞检测器。"""
    
    STAGNATION_THRESHOLD = 0.1  # 新假设生成率低于 10% 视为停滞
    MIN_DEPTH_FOR_CHECK = 2     # 至少 depth=2 才开始检测
    
    def check_stagnation(self, depth_stats: dict[int, int]) -> StagnationReport:
        """检测收敛是否停滞。
        
        depth_stats: {depth: 新假设数量}
        
        停滞判定标准（满足任意一条）：
        1. depth=N 的新假设数 < depth=N-1 的 10%
        2. 连续 2 个 depth 的新假设数为 0
        3. depth=3 的总新假设数 < 3（在 17 节点 demo 上）
        
        返回：
        - is_stagnant: bool
        - stagnation_depth: int (在哪个 depth 开始停滞)
        - recommended_action: "diverge" | "switch_perspective" | "expand_rules"
        """
        if len(depth_stats) < self.MIN_DEPTH_FOR_CHECK:
            return StagnationReport(is_stagnant=False)
        
        max_depth = max(depth_stats.keys())
        
        # 判定 1：递减率过低
        for d in range(2, max_depth + 1):
            prev = depth_stats.get(d - 1, 0)
            curr = depth_stats.get(d, 0)
            if prev > 0 and curr / prev < self.STAGNATION_THRESHOLD:
                return StagnationReport(
                    is_stagnant=True,
                    stagnation_depth=d,
                    recommended_action="diverge",  # 触发发散扰动
                )
        
        # 判定 2：连续两层为零
        for d in range(2, max_depth):
            if depth_stats.get(d, 0) == 0 and depth_stats.get(d + 1, 0) == 0:
                return StagnationReport(
                    is_stagnant=True,
                    stagnation_depth=d,
                    recommended_action="switch_perspective",  # 切换视角
                )
        
        # 判定 3：总产出过低
        total = sum(depth_stats.values())
        if total < 3:
            return StagnationReport(
                is_stagnant=True,
                stagnation_depth=max_depth,
                recommended_action="expand_rules",  # 扩展规则集
            )
        
        return StagnationReport(is_stagnant=False)
```

**与发散网络的联动：**

```
正向演绎运行中...
→ depth=1: 14 个新假设 ✓
→ depth=2: 2 个新假设 ✓
→ depth=3: 0 个新假设 ✗
→ ConvergenceMonitor 判定：stagnation_depth=3, action="diverge"
→ Meta-Cognitive Arbiter 暂停收敛，调用 DivergentCore
→ DivergentCore 对 depth=2 的关键节点生成反事实假设
→ 新假设注入收敛网络，打破局部最优
```

### 3.3 视角切换仲裁 (Perspective Arbiter)

**问题：** 同一节点多视角冲突，查询时不知用哪个。

**机制：**

```python
class PerspectiveArbiter:
    """视角切换仲裁器。"""
    
    def resolve_query_perspective(
        self, 
        node_id: str, 
        query_context: str,  # 查询上下文，如"物理基础"、"实现细节"、"数学推导"
    ) -> PerspectiveResolution:
        """根据查询上下文选择最佳视角。
        
        仲裁流程：
        1. 获取该节点所有视角
        2. 分析 query_context 的关键词（物理/数学/算法/实现/验证）
        3. 匹配 perspective 的 constraint_context
        4. 若无匹配，使用 primary_perspective
        5. 返回推荐视角 + 置信度
        """
        perspectives = self.store.get_perspectives(node_id)
        
        # 关键词映射
        context_keywords = {
            "物理": ["physical", "phenomenon", "law", "basis"],
            "数学": ["mathematical", "theorem", "proof", "formula"],
            "算法": ["algorithmic", "procedure", "optimization"],
            "实现": ["engineering", "implementation", "hardware", "deploy"],
            "验证": ["validation", "test", "convergence", "proof"],
        }
        
        # 匹配
        best_match = None
        best_score = 0
        for p in perspectives:
            score = self._match_context(query_context, p.constraint_context)
            if score > best_score:
                best_score = score
                best_match = p
        
        if best_match and best_score > 0.5:
            return PerspectiveResolution(perspective=best_match, confidence=best_score)
        
        # 无匹配，使用 primary
        primary = self.store.get_primary_perspective(node_id)
        return PerspectiveResolution(perspective=primary, confidence=0.5, is_fallback=True)
    
    def set_primary_perspective(self, node_id: str, perspective_name: str, 
                                 reason: str = ""):
        """设置 primary perspective。"""
        # 只能有一个 primary
        self.store.clear_primary_flag(node_id)
        self.store.set_primary_perspective(node_id, perspective_name, reason)
```

**示例：**

```
查询："FxLMS 的物理基础是什么？"
→ query_context 含 "物理" → 匹配 physical 视角
→ 返回 physical 视角 (L1)：信号传播延迟、因果性原理
→ explain_why(fxlms, perspective="physical") 
→ 链：FxLMS → Signal Propagation Delay → Causality Principle

查询："FxLMS 在 FPGA 上怎么实现？"
→ query_context 含 "实现" → 匹配 engineering 视角
→ 返回 engineering 视角 (L5)：定点运算、实时约束
→ explain_how(fxlms, perspective="engineering")
→ 链：FxLMS → Fixed-Point Arithmetic → FPGA Real-Time
```

### 3.4 验证反馈循环 (Validation Feedback Loop)

**问题：** 发散假设的 `total_value` 是硬编码权重，无法学习。

**机制：**

```python
class ValidationFeedbackLoop:
    """验证反馈循环。"""
    
    def __init__(self, store: ConvergentStoreV2):
        self.store = store
        self.direction_stats = {}  # 方向 → 验证统计
    
    def record_validation(self, hypothesis_id: str, result: ValidationResult):
        """记录验证结果。
        
        ValidationResult:
        - validated: bool (是否被验证为真)
        - evidence_type: "literature" | "simulation" | "expert" | "none"
        - confidence: float (验证者给出的置信度)
        """
        # 获取假设的生成方向
        hyp = self.store.get_hypothesis(hypothesis_id)
        generator = hyp.get("generator", "unknown")
        direction = f"{hyp.get('source_fact_id', '')}::{generator}"
        
        # 更新统计
        if direction not in self.direction_stats:
            self.direction_stats[direction] = {"total": 0, "passed": 0, "total_confidence": 0}
        
        self.direction_stats[direction]["total"] += 1
        if result.validated:
            self.direction_stats[direction]["passed"] += 1
        self.direction_stats[direction]["total_confidence"] += result.confidence
    
    def get_direction_score(self, direction: str) -> float:
        """获取方向的验证得分（用于预算分配）。"""
        stats = self.direction_stats.get(direction)
        if not stats or stats["total"] == 0:
            return 0.5  # 无历史记录，中性
        
        pass_rate = stats["passed"] / stats["total"]
        avg_confidence = stats["total_confidence"] / stats["total"]
        
        # 得分 = 通过率 * 0.6 + 平均置信度 * 0.4
        return pass_rate * 0.6 + avg_confidence * 0.4
    
    def adjust_value_weights(self, direction: str) -> dict[str, float]:
        """根据验证历史调整 value_vector 权重。"""
        score = self.get_direction_score(direction)
        
        # 高得分方向：提高 connectivity 和 heuristic_potential 权重
        # 低得分方向：提高 anti_common_sense 权重（鼓励更激进的假设）
        if score > 0.7:
            return {
                "cross_domain": 0.30,
                "connectivity": 0.35,  # 提高
                "heuristic_potential": 0.30,  # 提高
                "anti_common_sense": 0.05,  # 降低
            }
        elif score < 0.3:
            return {
                "cross_domain": 0.25,
                "connectivity": 0.20,
                "heuristic_potential": 0.25,
                "anti_common_sense": 0.30,  # 提高，尝试更激进的方向
            }
        else:
            return {
                "cross_domain": 0.35,
                "connectivity": 0.25,
                "heuristic_potential": 0.25,
                "anti_common_sense": 0.15,
            }
```

**效果：**
- 语义桥接方向经常验证通过 → 预算增加，权重偏向 connectivity
- 反事实扰动方向经常失败 → 预算减少，但权重偏向 anti_common_sense（更激进）
- 系统自适应地调整探索策略

---

## 4. 数据模型重构（强制实施 v5.1 设计）

### 4.1 强制替换：node_perspectives 表

v5.1 设计了但未实施。v5.2 必须落地：

```sql
-- ============================================================
-- 1. 节点表 (nodes_v2) — 修改：knowledge_level 变为可选
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes_v2 (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'concept',
    -- v5.2: knowledge_level 改为可选，实际层级从 node_perspectives 获取
    knowledge_level TEXT
        CHECK(knowledge_level IN ('L1','L2','L3','L4','L5','L6') OR knowledge_level IS NULL),
    layer TEXT DEFAULT 'asserted'
        CHECK(layer IN ('asserted', 'hypothesis', 'auto_gen', 'llm_sug', 'human')),
    confidence REAL DEFAULT 1.0
        CHECK(confidence >= 0 AND confidence <= 1),
    source TEXT DEFAULT 'import',
    is_derived INTEGER DEFAULT 0,
    -- v5.0 六层解构字段
    what TEXT,
    why_exists TEXT,
    physical_basis TEXT,
    mathematical_form TEXT,
    engineering_mapping TEXT,
    failure_modes TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- v5.2 新增
    perspective_count INTEGER DEFAULT 0,  -- 视角数量缓存
    primary_perspective TEXT  -- 默认视角名称
);

-- ============================================================
-- 2. 视角表 (node_perspectives) — v5.1 设计，v5.2 强制实施
-- ============================================================
CREATE TABLE IF NOT EXISTS node_perspectives (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes_v2(id) ON DELETE CASCADE,
    perspective_name TEXT NOT NULL,
    knowledge_level TEXT NOT NULL CHECK(knowledge_level IN ('L1','L2','L3','L4','L5','L6')),
    constraint_context TEXT,  -- 约束描述：什么条件下使用这个视角
    what TEXT,
    why_exists TEXT,
    physical_basis TEXT,
    mathematical_form TEXT,
    engineering_mapping TEXT,
    failure_modes TEXT,
    confidence REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
    is_default INTEGER DEFAULT 0,  -- 是否默认视角（仅一个可为 1）
    is_primary INTEGER DEFAULT 0,  -- 是否 primary（查询时默认使用）
    validation_count INTEGER DEFAULT 0,
    failed_validations INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(node_id, perspective_name)
);

CREATE INDEX idx_perspectives_node ON node_perspectives(node_id);
CREATE INDEX idx_perspectives_level ON node_perspectives(knowledge_level);
CREATE INDEX idx_perspectives_name ON node_perspectives(perspective_name);
CREATE INDEX idx_perspectives_primary ON node_perspectives(node_id, is_primary);

-- ============================================================
-- 3. 视角验证记录表 (perspective_validation) — v5.1 设计
-- ============================================================
CREATE TABLE IF NOT EXISTS perspective_validation (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    perspective_name TEXT NOT NULL,
    validator_type TEXT CHECK(validator_type IN ('convergent', 'divergent', 'human')),
    validation_result TEXT CHECK(validation_result IN ('valid', 'invalid', 'ambiguous')),
    reason TEXT,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. 发散方向统计表 (direction_stats) — v5.2 新增
-- ============================================================
CREATE TABLE IF NOT EXISTS direction_stats (
    id TEXT PRIMARY KEY,
    seed_node_id TEXT NOT NULL,
    generator_type TEXT NOT NULL,  -- semantic_bridge / counterfactual / structural_isomorphism
    total_generated INTEGER DEFAULT 0,
    total_validated INTEGER DEFAULT 0,
    total_passed INTEGER DEFAULT 0,
    total_confidence REAL DEFAULT 0,
    last_generated_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(seed_node_id, generator_type)
);

-- ============================================================
-- 5. 假设归档表 (hypothesis_archive) — 扩展 v4.1 设计
-- ============================================================
CREATE TABLE IF NOT EXISTS hypothesis_archive (
    id TEXT PRIMARY KEY,
    original_node_id TEXT,
    original_perspective TEXT,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,  -- ttl_expired / low_confidence / contradicted / budget_exceeded
    contradiction_details TEXT,  -- JSON
    value_vector TEXT  -- JSON: 记录归档时的权重，用于后续分析
);
```

### 4.2 迁移脚本

```sql
-- 从 v5.0/v5.1 单视角迁移到 v5.2 多视角
INSERT INTO node_perspectives (
    id, node_id, perspective_name, knowledge_level, 
    is_default, is_primary, what
)
SELECT 
    'persp::' || id || '::core',
    id,
    'core',
    COALESCE(knowledge_level, 'L3'),
    1,
    1,
    what
FROM nodes_v2 
WHERE knowledge_level IS NOT NULL;

-- 更新 perspective_count
UPDATE nodes_v2 
SET perspective_count = (
    SELECT COUNT(*) FROM node_perspectives WHERE node_perspectives.node_id = nodes_v2.id
);
```

---

## 5. 推理层重构

### 5.1 MetaCognitiveArbiter 类

```python
class MetaCognitiveArbiter:
    """元认知仲裁器 — 三层仲裁模型的顶层控制器。"""
    
    def __init__(self, convergent_store: ConvergentStoreV2, 
                 divergent_core: DivergentCore,
                 deduction_engine: DeductionEngine):
        self.store = convergent_store
        self.divergent = divergent_core
        self.deduction = deduction_engine
        
        # 三个子模块
        self.anti_bloat = AntiBloatController(convergent_store)
        self.convergence_monitor = ConvergenceMonitor()
        self.perspective_arbiter = PerspectiveArbiter(convergent_store)
        self.feedback = ValidationFeedbackLoop(convergent_store)
    
    def process_node(self, node_id: str, query_context: str = "") -> ProcessingResult:
        """处理节点的完整流程。
        
        流程：
        1. 视角仲裁：确定最佳视角
        2. 收敛演绎：正向演绎
        3. 停滞检测：检查是否陷入局部最优
        4. 发散生成（如需要）：生成假设
        5. 预算控制：截断超限假设
        6. 约束校验：验证假设
        7. 反馈记录：记录验证结果
        """
        # Step 1: 视角仲裁
        perspective = self.perspective_arbiter.resolve_query_perspective(
            node_id, query_context
        )
        
        # Step 2: 收敛演绎
        depth_stats = self.deduction.run_with_stats(node_id, perspective.perspective_name)
        
        # Step 3: 停滞检测
        stagnation = self.convergence_monitor.check_stagnation(depth_stats)
        
        hypotheses = []
        
        # Step 4: 发散生成（如果停滞或用户要求）
        if stagnation.is_stagnant or query_context == "explore":
            node = self.store.get_node(node_id)
            raw_hypotheses = self.divergent.generate_from_fact(node)
            
            # Step 5: 预算控制
            for generator_type in ["semantic_bridge", "counterfactual", "structural"]:
                gen_hyps = [h for h in raw_hypotheses 
                           if h.get("generator") == generator_type]
                filtered = self.anti_bloat.consume_budget(
                    node_id, generator_type, gen_hyps
                )
                hypotheses.extend(filtered)
        
        # Step 6: 约束校验（由 ConvergentStore 完成）
        # Step 7: 反馈记录（验证后由外部调用 record_validation）
        
        return ProcessingResult(
            perspective=perspective,
            depth_stats=depth_stats,
            stagnation=stagnation,
            hypotheses=hypotheses,
        )
```

### 5.2 与 CLI 的集成

```bash
# 查询时自动选择视角
lcortex explain fxlms --why --perspective physical
lcortex explain fxlms --how --perspective engineering

# 查看多视角
lcortex perspective fxlms --list

# 手动设置 primary perspective
lcortex perspective fxlms --set-primary physical

# 运行双网络协调（含元认知仲裁）
lcortex coordinate fxlms

# 查看发散预算和验证统计
lcortex stats --direction fxlms
```

---

## 6. 实施计划

### Phase 1：数据层重构（1-2 天）

| 任务 | 说明 |
|------|------|
| 新建 `node_perspectives` 表 | 替代单值 `knowledge_level` |
| 新建 `direction_stats` 表 | 记录发散方向统计 |
| 迁移脚本 | 将现有 17 节点迁移到多视角 |
| 更新 `ConvergentStoreV2` | 增删查视角接口 |

### Phase 2：元认知层实现（2-3 天）

| 任务 | 说明 |
|------|------|
| `AntiBloatController` | 预算分配与消耗 |
| `ConvergenceMonitor` | 停滞检测 |
| `PerspectiveArbiter` | 视角切换仲裁 |
| `ValidationFeedbackLoop` | 验证反馈循环 |
| `MetaCognitiveArbiter` | 顶层控制器 |

### Phase 3：双网络协调补齐（2-3 天）

| 任务 | 说明 |
|------|------|
| 反事实引擎升级 | LLM-based 替代字符串替换 |
| 语义桥接升级 | Embedding-based 替代 Jaccard |
| 协调循环完整实现 | `coordinate_with_convergent()` 自动执行 |

### Phase 4：测试与验证（1-2 天）

| 任务 | 目标 |
|------|------|
| 多视角查询测试 | `explain_why(fxlms, perspective="physical")` 正确追溯 |
| 停滞检测测试 | 模拟局部最优，验证自动触发发散 |
| 预算控制测试 | 验证历史影响预算分配 |
| 端到端协调测试 | 完整流程 10 个种子节点 |

---

## 7. 与 v5.1/v4.1 的兼容性

| 版本 | 兼容性 |
|------|--------|
| v4.1 | `nodes` 表字段保留，新增表不影响旧数据 |
| v5.0 | `nodes_v2` 表保留，`knowledge_level` 变为可选 |
| v5.1 | `node_perspectives` 表设计不变，v5.2 强制实施 |

**降级策略：**
- 若 `node_perspectives` 为空，回退到 `nodes_v2.knowledge_level`
- 若元认知层不可用，回退到 v5.1 双网络协调
- 若发散层不可用，层级网络独立运行（v5.0 行为）

---

## 8. 风险与边界

| 风险 | 缓解措施 |
|------|---------|
| 视角爆炸（>8 个视角/节点） | 限制最多 8 个视角；相似视角合并 |
| 预算分配不公 | 初始所有方向 budget=10，3 轮验证后自适应 |
| 反馈循环延迟 | 方向统计按天汇总，不实时更新 |
| 人工标注 primary 负担 | 默认取最高 confidence 视角为 primary |
| 停滞检测误触发 | 仅 depth≥2 时检测；误判率容忍 10% |

---

## 9. 一句话总结

**v5.0 是骨架，v5.1 是双关节，v5.2 是大脑。骨架支撑结构，关节协调运动，大脑决定何时动、向哪动、动多少。元认知层不是新功能，是对双网络的「生命管理」——没有它，双网络是死的；有了它，系统是活的。**

---

*设计方案版本: v5.2-FINAL*
*撰写日期: 2026-06-16*
*作者: 合作 (OpenClaw)*
*基于: v5.1 双网络协调设计 + v4.1 主动生长型认知引擎 + 用户元认知层需求*
