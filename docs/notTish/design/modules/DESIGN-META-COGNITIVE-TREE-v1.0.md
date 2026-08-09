# Meta-Cognitive Tree (MCT) — 元认知树设计方案 v1.0

> **文档编号**: LC-DESIGN-MCT-v1.0  
> **日期**: 2026-06-29  
> **依赖**: LC-DESIGN-v6.0-UNIFIED-rev5, CL0双盘位设计  
> **状态**: 设计阶段

---

## 1. 核心问题

当前系统的决策记录是**扁平化日志**：时间顺序排列，不可分叉，不可回溯，不可重评估。这导致：

- **决策债务累积**：错误决策无法被识别和修正，直到引发系统性故障
- **路径锁定**：一旦选择某条路径，替代方案永久丢失，无法复活
- **元认知缺失**：系统无法对"自己的决策过程"进行决策

**目标**：将决策历史从线性日志升级为**可再决策的树状数据结构**。

---

## 2. 核心概念

### 2.1 决策节点（DecisionNode）

决策的最小原子单位。不是"做了什么"，而是"在何种前提下，为何选择A而非B"。

```
DecisionNode {
  id: UUID
  
  // 决策上下文（不可变快照）
  context_hash: SHA256          // 保证可重现
  timestamp: ISO8601
  layer: CL0|CL1|CL2|CL3|CL4|L5 // 决策发生层
  
  // 决策内容
  premise: [Assertion]         // 当时被认定为"真"的前提集合
  options: [Option]            // 可选方案（含未选方案）
  selected: Option             // 实际选择
  reasoning: ReasoningTrace    // 推理过程（规则引用/LLM输出/计算路径）
  
  // 树结构
  parent: UUID | null          // 触发此决策的父决策
  children: [UUID]             // 此决策触发的子决策
  alternatives: [Branch]       // 被丢弃的分支（保留完整信息）
  
  // 可再决策支持
  confidence: float            // 当前置信度 [0,1]
  confidence_history: [(t, v)] // 置信度随时间变化
  reassessment_count: int      // 被重新评估次数
  
  // 结果追踪（可能滞后）
  predicted_outcome: Outcome   // 决策时的预测
  actual_outcome: Outcome | null // 实际结果（验证后回填）
  outcome_verified: bool       // 结果是否被外部验证
  
  // 支撑性（核心指标）
  support_score: float         // 多少后续决策依赖此节点
  dependents: [UUID]           // 直接依赖此决策的节点列表
}
```

### 2.2 分支（Branch）

被丢弃的方案不是垃圾，是**认知资产**。

```
Branch {
  option: Option               // 未选择的方案
  abort_reason: string         // 当时放弃的原因
  abort_confidence: float      // 当时对"放弃正确"的置信度
  
  // 复活机制
  resurrected: bool            // 是否被复活
  resurrected_as: UUID | null  // 复活后的新决策节点
  resurrect_trigger: string    // 复活触发原因
  
  // 持续评估
  post_hoc_evaluation: [Evaluation] // 事后评估（新证据下的重新打分）
}
```

### 2.3 推理痕迹（ReasoningTrace）

不是黑盒"选了A"，而是**可审计的推理链**。

```
ReasoningTrace {
  type: RULE_BASED | LLM_BASED | HYBRID | COMPUTATIONAL
  
  // 规则驱动
  rules_applied: [RuleRef]     // 引用的规则ID及版本
  rule_versions: {rule_id: hash} // 规则版本快照（防止规则变更后推理失效）
  
  // LLM驱动
  llm_prompt_hash: SHA256      // 提示词哈希
  llm_response_hash: SHA256    // 响应哈希
  llm_model: string            // 模型版本
  
  // 计算驱动
  computation_steps: [Step]    // 计算步骤（公式/数值/代码路径）
  input_hash: SHA256           // 输入数据哈希
  output_hash: SHA256          // 输出数据哈希
}
```

---

## 3. 树操作：五种核心行为

### 3.1 分叉（Fork）

**触发**：同一前提，不同时间产生矛盾决策。

不是覆盖，而是生成**兄弟节点**。

```
原始决策 D (confidence=0.8)
    ↓ 新证据出现，与D冲突
D' (confidence=0.6) —— 兄弟节点，共享同一parent
    ↓ 继续演化
D'-1, D'-2, ...
```

**关键**：原节点D保留，标记为`superseded_by: D'`，但 subtree 仍在。系统可以同时维护多条"认知时间线"。

### 3.2 回溯（Reassess）

**触发**：
- 结果与预测偏差 > threshold
- 新证据与历史决策前提冲突
- 支撑性追踪发现高支撑节点存在隐患
- 人工触发

**行为**：不是修改原节点，而是生成**重评估节点**。

```
D (原始决策)
    ↓ reassess()
D_re (重评估节点)
    ├── premise: [原premise + 新证据]
    ├── options: [重新计算的可选方案]
    ├── selected: [可能不同]
    └── link_to_original: D
```

### 3.3 合并（Merge）

**触发**：两条独立路径到达**认知同构**状态。

```
P
├── A → B → C
└── X → Y → Z

if isomorphic(C, Z):  // 结构等价 + 结果等价
    merge(C, Z) → M
    保留双路径历史，但后续决策共享同一出口
```

### 3.4 复活（Resurrect）

**触发**：被丢弃分支的事后评估置信度上升。

```
Branch B (abandoned 30 days ago, abort_confidence=0.9)
    ↓ 新证据出现，post_hoc_evaluation显示 B 应该被选择
B.resurrect() → 生成新决策节点 B'，作为独立时间线
```

### 3.5 剪枝（Prune）

**触发**：奥卡姆剃刀引擎定期审查。

**标准**：
- 分支30天未被重新访问
- 事后评估置信度持续下降
- 存在更短路径到达等价结果
- 支撑性 < 0.1 且无依赖

**行为**：不是删除，而是**归档到冷存储**（Limbo Zone for Decisions）。

---

## 4. 支撑性追踪（Support Tracking）

这是将"公理化支撑性"应用到决策层的关键。

### 4.1 支撑性定义

```
S(D) = |{D' ∈ Descendants(D) : D ∈ premise(D')}| / |AllActiveDecisions|
```

即：此决策作为前提出现在多少活跃决策中。

### 4.2 支撑性等级

| 等级 | S(D) | 含义 | 变更约束 |
|------|------|------|----------|
| 骨架 | >0.5 | 系统核心决策 | 需全量回测 + 人工确认 |
| 支撑 | 0.1-0.5 | 重要但可替代 | 需影响分析 + 影子验证 |
| 边缘 | <0.1 | 局部决策 | 可自动重评估 |

### 4.3 支撑性传播

```
D1 (S=0.6, 骨架级)
    ├── D2 (S=0.3)
    │     └── D4 (S=0.05)
    └── D3 (S=0.1)

若 D1 被重评估：
    D2, D3 标记为 STALE
    D4 标记为 STALE（级联传播）
    所有 STALE 节点进入重评估队列
```

---

## 5. 奥卡姆剃刀引擎（Razor Engine for Decisions）

### 5.1 输入

- 决策树当前状态
- 事后评估数据（actual_outcome vs predicted_outcome）
- 支撑性图谱

### 5.2 输出

- 剃除清单（归档候选）
- 合并建议（认知同构检测）
- 复活建议（被低估分支）

### 5.3 算法

```python
def razor_pass(tree):
    candidates = []
    
    # 1. 检测冗余分支
    for branch in tree.branches:
        if branch.post_hoc_confidence < 0.2 and not branch.resurrected:
            # 事后评估持续低迷
            if tree.support_of(branch.parent) < 0.1:
                candidates.append(("archive", branch))
    
    # 2. 检测可合并路径
    for pair in tree.leaf_pairs():
        if isomorphic(pair[0], pair[1], threshold=0.9):
            candidates.append(("merge", pair))
    
    # 3. 检测被低估分支
    for branch in tree.abandoned_branches:
        recent_evals = [e for e in branch.post_hoc_evaluations if e.age < 7_days]
        if recent_evals and mean(e.confidence for e in recent_evals) > 0.7:
            candidates.append(("resurrect", branch))
    
    return candidates
```

---

## 6. 元认知层：对决策的决策

### 6.1 元决策类型

| 元决策 | 问题 | 行动 |
|--------|------|------|
| 深度审计 | "这棵决策树的平均深度是否过深？" | 触发抽象化（子树合并为高层决策） |
| 置信度审计 | "置信度方差是否过大？" | 触发证据收集 / 强制人工审查 |
| 循环检测 | "是否存在决策循环依赖？" | 触发解耦 / 引入外部裁决 |
| 覆盖率审计 | "是否某些 premise 从未被质疑？" | 触发反事实探索 |
| 时效审计 | "高支撑节点是否过时？" | 触发强制重评估 |

### 6.2 元认知节点

元决策本身也是决策，因此也进入决策树。

```
MetaDecisionNode : DecisionNode {
    target_decisions: [UUID]  // 此元决策审查的目标
    meta_type: DEPTH_AUDIT | CONFIDENCE_AUDIT | ...
    recommendation: string     // 建议行动
    enforced: bool             // 是否被自动执行
}
```

这形成**自指循环**：决策树包含对自身的决策。

---

## 7. 数据库 Schema

### 7.1 核心表

```sql
-- 决策节点
CREATE TABLE decision_nodes (
    id UUID PRIMARY KEY,
    context_hash BLOB NOT NULL,          -- SHA256
    timestamp REAL NOT NULL,
    layer TEXT CHECK(layer IN ('CL0','CL1','CL2','CL3','CL4','L5')),
    premise_json TEXT NOT NULL,          -- JSON [Assertion]
    selected_option_id UUID NOT NULL,
    reasoning_trace_id UUID,
    parent_id UUID REFERENCES decision_nodes(id),
    confidence REAL NOT NULL DEFAULT 0.5,
    reassessment_count INT DEFAULT 0,
    predicted_outcome_json TEXT,
    actual_outcome_json TEXT,
    outcome_verified BOOLEAN DEFAULT FALSE,
    support_score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','stale','superseded','archived')),
    superseded_by UUID REFERENCES decision_nodes(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 可选方案（含未选方案）
CREATE TABLE decision_options (
    id UUID PRIMARY KEY,
    node_id UUID NOT NULL REFERENCES decision_nodes(id),
    option_json TEXT NOT NULL,
    was_selected BOOLEAN DEFAULT FALSE,
    predicted_outcome_json TEXT,
    abort_reason TEXT,                   -- NULL = 被选中
    abort_confidence REAL,
    resurrected BOOLEAN DEFAULT FALSE,
    resurrected_as UUID REFERENCES decision_nodes(id),
    post_hoc_eval_json TEXT              -- JSON [Evaluation]
);

-- 树结构（父子关系）
CREATE TABLE decision_tree_edges (
    parent_id UUID REFERENCES decision_nodes(id),
    child_id UUID REFERENCES decision_nodes(id),
    edge_type TEXT DEFAULT 'triggers' CHECK(edge_type IN ('triggers','supersedes','resurrects')),
    PRIMARY KEY (parent_id, child_id)
);

-- 支撑性依赖
CREATE TABLE decision_support_edges (
    supporter_id UUID REFERENCES decision_nodes(id),  -- 作为前提
    dependent_id UUID REFERENCES decision_nodes(id),  -- 依赖此前提
    PRIMARY KEY (supporter_id, dependent_id)
);

-- 推理痕迹
CREATE TABLE reasoning_traces (
    id UUID PRIMARY KEY,
    type TEXT CHECK(type IN ('RULE_BASED','LLM_BASED','HYBRID','COMPUTATIONAL')),
    rules_applied_json TEXT,             -- [RuleRef]
    rule_versions_json TEXT,             -- {rule_id: hash}
    llm_prompt_hash BLOB,
    llm_response_hash BLOB,
    llm_model TEXT,
    computation_steps_json TEXT,
    input_hash BLOB,
    output_hash BLOB
);

-- 元认知决策
CREATE TABLE meta_decisions (
    id UUID PRIMARY KEY REFERENCES decision_nodes(id),
    target_decisions_json TEXT NOT NULL, -- [UUID]
    meta_type TEXT CHECK(meta_type IN ('DEPTH_AUDIT','CONFIDENCE_AUDIT','CYCLE_DETECTION','COVERAGE_AUDIT','STALE_AUDIT')),
    recommendation TEXT NOT NULL,
    enforced BOOLEAN DEFAULT FALSE
);

-- 归档（Limbo Zone for Decisions）
CREATE TABLE decision_archive (
    id UUID PRIMARY KEY,
    original_id UUID NOT NULL,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archive_reason TEXT NOT NULL,
    node_snapshot_json TEXT NOT NULL     -- 完整快照
);
```

### 7.2 索引

```sql
-- 支撑性查询
CREATE INDEX idx_support_edges_supporter ON decision_support_edges(supporter_id);
CREATE INDEX idx_support_edges_dependent ON decision_support_edges(dependent_id);

-- 时间线查询
CREATE INDEX idx_nodes_timestamp ON decision_nodes(timestamp);
CREATE INDEX idx_nodes_layer ON decision_nodes(layer);
CREATE INDEX idx_nodes_status ON decision_nodes(status);

-- 父子查询
CREATE INDEX idx_tree_edges_parent ON decision_tree_edges(parent_id);

-- 支撑性分数（用于Razor Engine）
CREATE INDEX idx_nodes_support ON decision_nodes(support_score) WHERE status = 'active';
```

---

## 8. 与现有架构的集成

### 8.1 与CL层的集成

| CL层 | 决策类型 | MCT记录内容 |
|------|----------|-------------|
| CL0 | 规则匹配结果 | 哪条规则触发、输入哈希、输出结果 |
| CL1 | 近迁移匹配 | 历史案例ID、匹配分数、迁移路径 |
| CL2 | 远迁移/类比 | CSM结果、锚点列表、置信度 |
| CL3 | 质疑结论 | 发现的矛盾、风险评估、建议行动 |
| CL4 | 调度决策 | 算力分配、层切换理由、预算消耗 |
| L5 | 元认知决策 | 发散/收敛/视角切换、预算分配 |

### 8.2 与双盘位的集成

- **硬编码规则变更**：生成 MetaDecision，记录支撑性分析、回测结果、人工确认
- **软编码规则准入**：记录观察窗口数据、MDL惩罚计算、影子模式对比结果
- **软→硬晋升**：完整的决策树路径，从观察到规则到验证

### 8.3 与Limbo Zone的集成

- 决策剪枝 → 进入 `decision_archive`
- 复活时从归档恢复，生成 resurrect 关系边

---

## 9. 关键算法复杂度

| 操作 | 时间 | 说明 |
|------|------|------|
| 插入决策 | O(1) | 单次写入 |
| 支撑性查询 | O(k) | k = 依赖此决策的节点数 |
| 支撑性传播 | O(n) | n = 受影响子树大小 |
| 认知同构检测 | O(n²) | 叶节点对比较，可优化为局部敏感哈希 |
| Razor Engine | O(m) | m = 活跃分支数 |

---

## 10. 交付物

| 文件 | 说明 |
|------|------|
| `lcortex/meta_cognition/decision_tree.py` | 核心DecisionTree类 |
| `lcortex/meta_cognition/tree_ops.py` | Fork/Reassess/Merge/Resurrect/Prune |
| `lcortex/meta_cognition/support_tracker.py` | 支撑性追踪与传播 |
| `lcortex/meta_cognition/razor_engine.py` | 奥卡姆剃刀引擎 |
| `lcortex/meta_cognition/meta_auditor.py` | 元认知审计器 |
| `lcortex/meta_cognition/schema.sql` | 数据库Schema |
| `tests/test_meta_cognitive_tree.py` | 单元测试 |

---

## 11. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 决策树爆炸增长 | TTL + Razor Engine + 归档机制 |
| 支撑性计算延迟 | 异步更新 + 增量传播 |
| 循环依赖（决策依赖自身） | 拓扑排序检测 + 人工介入 |
| 存储膨胀 | 归档压缩 + 快照去重 |

---

## 12. 下一步

1. 确认本设计方案
2. 编写核心 `DecisionTree` 类（约300行）
3. 实现 Fork + Reassess 操作
4. 支撑性追踪器
5. Razor Engine MVP
6. 集成到现有CL层管道

---

*本设计将决策历史从"写死的日志"变成"可操作的认知资产"。*
