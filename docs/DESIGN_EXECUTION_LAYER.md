# DialogMesh — 执行层架构设计 (Execution Layer)

> 2026-07-25 · 七棵树并行 · 查询驱动通信 · LLM元认知协调 · 记忆即节点 · 结构化归约

---

## 一、核心模型：七棵树并行

```
DiscourseBlockTree (基类 — 节点/分支/摘要/归档 通用)
  │
  ├── DiscourseTree    对话内容: 用户消息, LLM回答, 对话块
  ├── ExecutionTree    最活跃: 任务分解, 派生子Agent, 执行工具
  ├── ConstraintTree   EngineeringChain: 规则, 约束, 文件/命令限制 (轻量)
  ├── AssociationTree  RelationSubstrate: 实体关系, 跨树映射查询 (辅助)
  ├── BehaviorTree     用户偏好: 工具习惯, 修正历史, PlanGate学习 (协同)
  ├── MetaTree         元认知仲裁: 审计轨迹, 决策记录, 归约产出 (拍板)
  └── ProfileTree      用户画像: OCEAN 演化, 惯性变化 (轻量)

每棵树 = DiscourseBlockTree 子类 + 域特定字段
全部共享: 节点格式, 分支结构, 渐进式摘要, 归档机制

各树活跃度:
  ExecutionTree ████████  最活跃 (任务分解+执行)
  DiscourseTree ██████    活跃 (对话记录)
  MetaTree      ████      中等 (归约时频繁)
  BehaviorTree  ███       中等 (每次修正记录)
  AssociationTree ██      辅助 (仅在跨树查询时)
  ConstraintTree  █       轻量 (仅在约束命中时)
  ProfileTree     ▏       极轻 (仅在变化时更新)
```

---

## 二、跨树信息获取：查询驱动 (Query-Driven)

### 2.1 不是通知 — 是查询

```
不需要树间推送通知。
需要信息时 → 主动查询。

类似多头注意力的 Q 向量:
  需要信息的树 → 发出 query → 目标树返回结果
```

### 2.2 查询路径

```
树 A 需要某信息:

  1. 查活跃节点:
     query → 目标树的活跃节点 → 找到 → 直接读取
     (树的所有活跃节点可被全局 query)

  2. 查归档节点:
     query → 目标树的归档节点 → 找到, 但已归档
     → LLM 决策: 是否需要回档
     → 需要: 回档→读取 (罕见, 高价值低概率)
     → 不需要: 使用归档摘要

  3. 未找到 — 双方案并行:
     方案A: 开新子Agent 去探索/创建这个信息
     方案B: 在持久化层搜索 (L5 Memory, FederationIndex)
     ├─ 持久化层找到 → 方案A 的结果也到了
     │   → LLM 融合 + 去重
     └─ 持久化层未找到 → 等方案A
         → 方案A 返回 → 写入 → 树可用

  4. 去重:
     方案A 和方案B 都返回 → 内容可能重叠
     → LLM 做去重 (不是算法 — LLM理解语义重复)
```

### 2.3 等待策略

```
查询时目标正在计算中 (子Agent 未完成):
  不阻塞 — 查询方继续其他工作
  目标完成后 → 目标树标记为 ready
  查询方下次 Tick → 重新 query → 获取

子Agent 执行中 → 返回 partial → 查询方可获取部分结果
```

---

## 三、树的动态生长

### 3.1 正向: 自顶向下分解 (主路径)

```
根节点 接收任务
  → LLM 评估 (上下文+复杂度+约束)
  → 决定分派 子Agent1, 子Agent2, ...
  → 每个子Agent 专注原子任务 (≤4K 上下文)
  → 完成后 → 结构化产出 → 父节点
```

### 3.2 反向: 回退插入 (Reactive)

```
元认知审核时发现:
  已完成的任务遗漏了关键步骤
  OR 上下文已变, 需要新的分支
  
  → 在树中回退到决策节点
  → 插入新的子任务分支
  → 重新派生子Agent
  → 新分支完成 → 与已有分支融合

触发条件: MetaTree 发现:
  - 冲突: ExecutionTree 的产出违反 ConstraintTree
  - 遗漏: 任务完成但约束检查不通过
  - 环境变化: 用户修改了偏好或约束规则
```

### 3.3 任意位置插入

```
元认知判断: "这一步执行前应该先验证"
  → 在 ExecutionTree 节点 X 前插入 节点 Y (验证步骤)
  → 派生子Agent 执行验证
  → 验证通过 → 继续执行 X
  → 验证失败 → 标记 X 为 blocked → 重新规划
```

---

## 四、子Agent 派生与协调

### 4.1 派生决策 (LLM 元认知综合判断)

```
默认模式: LLM 综合决策 — 传递元信息, LLM 决定

传递给 LLM 的元信息:
  {
    complexity: 0.75,         # 任务复杂度 (Compass+PCR)
    context_size: 14_000,     # 当前上下文 tokens
    threshold_8k: true,       # 超过8K
    threshold_16k: false,     # 未超16K
    estimated_subtasks: 3,    # 预估子任务数
    tools_involved: ["read","edit","bash"],
    constraint_violations: ["edit targets /etc/"],
    behavior_hints: ["user prefers concise output"],  ← BehaviorTree
  }

可选模式:
  单触发: 仅按上下文阈值
  单触发: 仅按复杂度
  纯 LLM: LLM 自由决定
  关闭: 永不派生
```

### 4.2 父→子 消息

```
父节点:
  { task, queries[], pointers[], context(≤4K) }

子Agent:
  1. 接收任务 + 轻量上下文
  2. 按需 → query 拉更多 → 子图扩展 (L5 Memory)
  3. 4K窗口, 专注单一原子任务
  4. 完成 → 结构化产出

子→父:
  {
    status: "success"|"failed"|"partial",
    artifacts: [...],
    findings: [...],
    new_discoveries: [...]  # 发现的未知信息
  }
```

---

## 五、Memory Node：上下文降级与检索

### 5.1 创建时机

```
父Agent 上下文 > 阈值 (8K/16K/32K)
  → 语义切块 (Chunking)
  → 降级为 Memory Node (只读)
  → 存入 L5 Memory (XML Cards + Federation Index)
  → 子Agent 通过 query + pointer 检索
```

### 5.2 检索机制

```
pointer → Node.block_id → 直接读取 (常访问, 低延迟)
query   → FederatedIndex.search(query)
        → RAGraphBridge.expand(anchor, 2-hop)  ← 子图扩展
        → 不足时继续 query → 拉更多块 (按需, 不是一次性)

上下文始终保持 ≤4K
```

### 5.3 归档与回档

```
归档: 完成 → 归档为 Memory Node
回档: 罕见事件, LLM 决策
  案例: 正常 edit → 归档 → 新bug追溯到那次edit
  → LLM 判断需回档 → 重新打开 → 找到根因
  → Transition 记录 (高价值低概率) → L5 Memory → 所有模块学习
```

---

## 六、ReAct 重试闭环

```
子Agent 产出
  │
  ▼
MetaTree 质量评估:
  ├─ 达标 → 归档
  └─ 不达标:
       ├─ 明确错误 → 自动修正 → 重新执行 (Max 3 retries)
       ├─ 模糊 → 降低 temperature → LLM 重新推理
       └─ 信息不足 → 派生检测Agent → 补充信息 → 重新执行

每次重试 → Transition 记录:
  { "retry_N": { "reason", "old_approach", "new_approach", "delta" } }
```

---

## 七、多Agent 融合与归约

### 7.1 融合场景

| 场景 | 触发 | 策略 |
|------|------|------|
| 子Agent 归约 | 多个子Agent 并行完成 | 重要度倒置 → LLM归约 |
| 外部工具协同 | OpenClaw + Codex 同时调用 | 归一化格式 + LLM去重归并 |
| 跨树冲突 | ConstraintTree=违反, ExecutionTree=完成 | Meta 裁决(置信度比较) |
| 用户修正广播 | 用户调整Plan → 影响多树 | FeedbackBridge Layer 1 |

### 7.2 外部工具结果归一化

```
OpenClaw 返回: { stdout, stderr, exit_code, artifacts }
Codex 返回:    { completion, tokens_used, model }
MCP Tool 返回: { result, error, metadata }

归一化 → 统一格式:
  ExecutionResult {
    source: "opencode" | "codex" | "mcp",
    status, output, artifacts, findings, raw
  }

→ LLM 去重 + 融合 → 单一结果
```

### 7.3 归约策略 (重要性倒置)

```
合并次数 ∝ 1/重要性

高价值(1次):  安全漏洞/架构决策/用户偏好变化/约束冲突
中价值(2次):  代码修改/配置变更/工具调用结果
低价值(3次):  完成报告/状态更新/常规日志

高价值: 直接 LLM 归约 — 信息损失最少
中价值: 结构化提取→压缩→LLM 归约
低价值: 结构化→摘要→丢弃细节
```

### 7.4 Meta 归约流程

```
多子Agent 产出 → MetaTree:
  1. 判断重要性 → 分配合并次数
  2. 按重要性倒序归约
  3. 产出: { status, summary, artifacts, learning_points }
  4. Transition → L5 Memory → 后续学习
```

---

## 八、管线完整路径

```
Compass → PCR → Intent → L4 → Context → LLM Plan
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                              PlanGate.create()     auto_approved
                              requires_review?           │
                                    │                    ▼
                                    ▼              ExecutionEngine
                              前端展示+用户审批            │
                                    │              (可能派生子Agent)
                                    ▼                    │
                              ExecutionEngine     ↙      │
                              (7工具, 约束验证)  ←──────┘
                                    │
                                    ▼
                              子Agent 完成 → MetaTree 归约
                                    │
                                    ▼
                              LLM Answer → 用户
                              └→ PlanGate.learn → CorrectionJournal
```

---

## 九、与现有模块关系

```
新增:
  PlanGate           — 人机回环, 风险评估 ✅ 
  ExecutionEngine    — 7工具, 约束验证 ✅

复用:
  DiscourseBlockTree — 七棵树继承基板
  RelationSubstrate  — 跨树映射 (EntityNode 类型化边)
  L5 Memory          — Memory Node + 子图扩展检索
  MetaSubscriber     — 冷路径审计, 跨树协调
  FeedbackBridge     — 三层回写
  ContextAssembler   — 子Agent 上下文预算 (等二选一后)
  FederatedIndex     — 全局 query 入口
  RAGraphBridge      — 子图扩展

待建:
  AgentTreeManager   — 七棵树生命周期 (继承/创建/归档/回档)
  StructuredSynthesizer — 重要性评估 + 多级归约
  ReActRetryLoop     — 质量评估 + 自动重试 (规则: Max 3)
```

---

## 十、实施序列

```
Phase 1: AgentTreeManager
  7棵树: Discourse + Execution + Constraint + Association
        + Behavior + Meta + Profile
  每棵树继承 DiscourseBlockTree, 加域特定字段

Phase 2: Memory Node + 查询驱动
  上下文阈值触发 → Chunking → Memory Node
  全局 Q-style query → pointer/query → 子图扩展
  双方案并行 + LLM 去重

Phase 3: 动态生长
  正向: 自顶向下分解
  反向: 回退插入新分支
  任意位置: 元认知评估 → 重试 → 补充

Phase 4: StructuredSynthesizer
  重要性评估 → 多级归约 → 外部工具归一化

Phase 5: 端到端集成
  子Agent 派生 → 执行 → 归约 → 归档 → 回档 → ReAct 重试
```
