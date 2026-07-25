# DialogMesh — 执行层架构设计 (Execution Layer)

> 2026-07-25 · 多Agent树图协同 · LLM元认知协调 · 记忆即节点 · 结构化归约

---

## 一、核心模型：多树并行

```
DiscourseBlockTree (基类 — 节点/分支/摘要 通用)
  │
  ├── ExecutionTree    最活跃: 任务分解, 派生子Agent, 执行工具
  ├── ConstraintTree   EngineeringChain: 规则, 工程约束, 文件/命令限制
  ├── AssociationTree  RelationSubstrate: 实体关系, 跨模块映射
  ├── BehaviorTree     行为模式: 用户偏好, 工具使用习惯, 修正历史
  ├── MetaTree         元认知仲裁: 审计轨迹, 决策记录, 归约产出
  └── ProfileTree      用户画像: OCEAN 演化, 惯性变化

六棵树并行 — 不是双树
  每棵树 = DiscourseBlockTree 子类 + 域特定字段
  所有树共享节点格式 (EDU → Block → 摘要)

跨树映射:
  ExecutionTree 节点 X ←→ ConstraintTree 节点 Y
  通过 RelationSubstrate.EntityEdge(type=constraint_mapping)
  MetaTree 读取所有映射 → 发现冲突 → 归约裁决

---

## 二、子Agent 派生与协调

### 2.1 派生决策 (LLM 元认知综合判断)

```
默认模式: LLM 综合决策

触发条件 → 元信息传递给 LLM → LLM 决定是否分派子Agent

传递给 LLM 的结构化元信息:
  {
    complexity: 0.75,        # 任务复杂度 (Compass+PCR)
    context_size: 14_000,    # 当前上下文 tokens
    threshold_8k: true,      # 超过8K
    threshold_16k: false,    # 未超16K
    estimated_subtasks: 3,   # 预估子任务数
    tools_involved: ["read","edit","bash"],
    constraint_violations: ["edit targets /etc/"],
  }

LLM决策: "拆分为 3 个子Agent: 阅读配置 / 备份配置 / 修改配置"
         OR "单个Agent可完成, 不需拆分"

可选模式:
  单触发: 仅按上下文阈值 (8K/16K/32K)
  单触发: 仅按复杂度
  纯 LLM: 不看阈值, LLM 自由决定
  关闭:  永不派生 (默认单Agent)
```

### 2.2 父→子 通信模型

```
父节点:
  ┌─ task: "分析 auth.py 并修复安全漏洞"
  ├─ query: "SELECT edge WHERE type=SECURITY"   ← 全局查询
  ├─ query: "SELECT pattern WHERE user=admin"    ← 全局查询
  ├─ pointer: → BehaviorTree.user_style          ← 常访问指针
  ├─ pointer: → ConstraintTree.security_rules    ← 常访问指针
  └─ context: {轻量上下文, 4K tokens}

子Agent:
  1. 接收 task + context + query + pointer
  2. 按需 → query 拉更多 → 类似 L5 Memory 的子图扩展
  3. 4K上下文窗口, 专注单一原子任务
  4. 完成后 → 结构化产出 → 父节点

子→父产出:
  {
    status: "success",
    artifacts: ["patched auth.py", "modified validate.py"],
    findings: [{type: "vulnerability", severity: "high", location: "line 42"}],
    new_queries: [{...}]  # 发现需要额外查询的内容
  }
```

---

## 三、Memory Node：上下文降级与检索

### 3.1 创建时机

```
父Agent 上下文 > 阈值 (8K/16K/32K)
  →
  长上下文 ▸ 语义切块 (Chunking)
       ▸ 降级为 只读 Memory Node
       ▸ 存入 L5 Memory (XML Cards + Federation Index)
       ▸ 子Agent 通过 query 和 pointer 检索
```

### 3.2 检索机制

```
子Agent 检索路径:
  1. pointer → Node.block_id → 直接读取对应块
     ← 常访问节点, 低延迟

  2. query → FederatedIndex.search(query)
     → RAGraphBridge.expand(anchor, 2-hop)
     ← 全局搜索, 类似 L5 Memory 的子图扩展

  3. 不足时 → 继续 query → 拉更多块
     ← 不是一次性全部给, 按需逐步扩展

子Agent 上下文始终保持 ≤4K:
  Hook: ContextAssembler + BudgetAllocator — 已在管线中
```

### 3.3 归档与回档

```
归档: 子Agent 完成 → 归档到 Memory Node (只读)
  
回档: LLM 元认知 决策 → 重新打开归档节点
  条件: 罕见事件 (低概率)
  案例: 
    - 正常的 edit 步骤已完成 → 归档为 "config_edit, 成功"
    - 新bug出现, 追溯到那次 edit → LLM判断需要回档重新检查
    - 回档 → 读取 → 发现问题 → 记录为 Transition (高价值低概率)
    → 写入 L5 Memory → 所有模块学习
```

---

## 四、多Agent 融合与归约

### 4.1 融合策略 (重要性倒置)

```
原则: 合并次数 ∝ 1/重要性

  高价值 → 1次合并 (LLM一次归约) → 信息损失最少
  中价值 → 2次合并 (结构化→压缩→LLM) → 适度压缩
  低价值 → 3次合并 (结构化→摘要→压缩→LLM) → 高度压缩

分类 (由 Meta 判断):
  高: 安全漏洞 / 架构决策 / 用户偏好变化 / 约束冲突
  中: 代码修改 / 配置变更 / 工具调用结果
  低: 完成报告 / 状态更新 / 常规日志
```

### 4.2 Meta 树 归约流程

```
多个子Agent 完成
  │
  ▼
Meta 树
  ├─ 1. 接收所有子Agent 结构化产出
  ├─ 2. 判断重要性 → 分配合并次数
  ├─ 3. 按重要性倒序归约:
  │     高价值: 直接 LLM 归约 → 一行摘要即可
  │     中价值: 结构化提取 → 压缩 → LLM 归约
  │     低价值: 结构化 → 摘要 → 丢弃细节
  ├─ 4. 产出: 融合后的全局状态更新
  │     {
  │       status: "completed",
  │       summary: "3/3 succeeded, 1 vulnerability found and patched",
  │       artifacts: ["auth.py", "validate.py"],
  │       learning_points: [...],   ← 高价值低概率
  │     }
  └─ 5. Transition 记录 → L5 Memory → 后续学习
```

---

## 五、跨树通信与映射

### 5.1 六棵树间的四种通信路径

```
同树内 近邻:
  父 ↔ 子:  结构化消息 (task + result)
  子 ↔ 子:  通过父中转 (不直接通信, 保持隔离)

跨树 映射:
  ExecutionTree 节点 X → ConstraintTree 节点 Y
    通过 RelationSubstrate.EntityEdge(type=constraint_mapping)
    元认知读取映射 → 发现冲突 → 裁决

全局:
  query → FederationIndex → 任意树的节点
  pointer → 指定 block_id → 定位读取

EventBus:
  NODE_CREATED / NODE_COMPLETED / NODE_ARCHIVED / NODE_REOPENED
  → Meta Subscriber 消费 → FeedbackBridge
```

### 5.2 Agent 间结构化消息格式

```python
AgentMessage = {
    "from": "agent_id",
    "to": "agent_id | parent | broadcast",
    "type": "task | result | query | alert",
    "payload": {...},
    "trace": [agent_id, ...],  # 路由追踪
}
```

---

## 六、管线完整路径 (含执行层)

```
Compass → PCR → Intent → L4 → Context → LLM Plan
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                              PlanGate.评估          auto_approved
                              requires_review?           │
                                    │                    ▼
                                    ▼              ExecutionEngine
                              前端展示Plan                │
                              用户审批/调整                ▼
                                    │              子Agent返回
                                    ▼                    │
                              ExecutionEngine             ▼
                              (可能派生子Agent)     Meta归约
                                    │                    │
                                    ▼                    ▼
                              子Agent返回       PlanGate.学习
                                    │           CorrectionJournal
                                    ▼
                              Meta归约 → 父节点 → LLM Answer → 用户
```

---

## 七、与现有模块的关系

```
执行层新增:
  PlanGate          — 人机回环, 风险评估, 行为学习
  ExecutionEngine   — 7工具, 约束验证, 7ms延迟 ✅ 已有
  WebSocket Server  — :9100, Python/TS/Rust 客户端 ✅ 已有

复用现有:
  DiscourseBlockTree   — 多树继承基类
  RelationSubstrate    — 跨树约束映射
  L5 Memory            — Memory Node + 子图扩展
  MetaSubscriber       — 冷路径审计
  FeedbackBridge       — 三层回写
  ContextAssembler     — 子Agent 上下文预算
  BudgetAllocator      — 4K窗口限制
  FederatedIndex       — 全局query

待建:
  AgentTreeManager        — 六棵树生命周期 (Execution/Constraint/Association/
                            Behavior/Meta/Profile: 继承→创建→归档→回档)
  StructuredSynthesizer   — 重要性评估 + 多级归约
```

---

## 八、实施序列

```
Phase 1: AgentTreeManager (六棵树继承)
  继承 DiscourseBlockTree → ExecutionTree + ConstraintTree + AssociationTree
                          + BehaviorTree + MetaTree + ProfileTree

Phase 2: Memory Node 降级检索
  上下文阈值触发 → Chunking → Memory Node → query/pointer 检索

Phase 3: StructuredSynthesizer (归约)
  重要性评估 → 多级归约 → Meta 归约输出

Phase 4: 端到端集成
  子Agent 派生 → 执行 → 归约 → 归档 → 回档
```
