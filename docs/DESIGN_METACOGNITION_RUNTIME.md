# 运行时元认知 — Workflow Graph Loop 设计

> 2026-07-25 · 小环(热)+大环(冷)+死循环检测+逆向溯源

---

## 一、核心模型：双环结构

```
                    ┌─── DAG 外层 (有向无环) ─────────┐
                    │                                   │
  Agent N ────────→ Agent N+1 ────────→ Agent N+2      │
    │                   │                   │           │
    │ 小环              │ 小环              │ 小环       │
    ▼                   ▼                   ▼           │
  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
  │ Think        │   │ Think        │   │ Think        │  │
  │  → Act      │   │  → Act      │   │  → Act      │  │
  │  → SelfChk  │   │  → SelfChk  │   │  → SelfChk  │  │
  │  → Correct  │   │  → Correct  │   │  → Correct  │  │
  │  → Retry    │   │  → Retry    │   │  → Retry    │  │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   │
         │ 输出             │ 输出             │ 输出      │
         ▼                  ▼                  ▼          │
      归档              归档              归档            │
                    │                                   │
                    └─────────── 5 tick ────────────────┘
                                    │
                                    ▼
                              Meta 冷路径审计
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
                      通过                  发现问题
                      保留                  回档→修正→重新执行
                                                │
                                                ▼
                                         Transition 记录
                                         (高价值低概率)
                                              │
                                              ▼
                                         所有模块学习
```

---

## 二、小环：节点内运行时元认知 (热路径)

### 2.1 定义

小环 = 节点内部的 think→act→self-check→correct→retry 循环。
修正对象：**当前节点产出**，不回溯到根。
先验切分效果好 → 大多数错误是局部性的 → 增量修正即可。

### 2.2 循环结构

```
Step 1: Think
  LLM 分析当前节点任务 + 约束 + 上下文
  → 生成执行计划 (≤3个原子步骤)

Step 2: Act
  ExecutionEngine 执行计划
  → 产出 ExecutionResult (status / output / artifacts)

Step 3: Self-Check
  LLM 或规则检查产出:
    ✅ 产出是否满足当前节点需求？
    ✅ 是否违反 ConstraintTree 约束？
    ✅ 输出是否完整？(无截断、无格式错误)

Step 4: Correct (仅对当前节点)
  不满足 → 修正 (不是回退到上一个节点)
  修正方式:
    - 参数调整: 换工具参数
    - 上下文扩展: 加载更多上下文 (≤4K→扩展)
    - 温度降低: 0.3→0.1→LLM重新推理
    - 策略切换: 换Blueprint策略 (RECOVERY)

Step 5: Retry
  修正后重新 Act
  → Max 3 retries (由 ReActRetryEngine 控制)
  → 3次仍失败 → 标记此节为 blocked → 退出小环
```

### 2.3 与 ReActRetryEngine 的关系

```
ReActRetryEngine 已实现 5 种重试策略:
  AUTO_FIX       → 自动修正 (diff冲突, 重读文件)
  TEMPERATURE_DROP → 降低LLM温度→重新推理
  EXPAND_CONTEXT   → 加载更多上下文
  SPAWN_DETECTOR   → 派生检测Agent辅助
  ESCALATE          → 升级到用户/Meta

这些策略全部在小环内执行。
小环元认知 = ReActRetryEngine + Self-Check逻辑
```

---

## 三、大环：归档回档 + 元认知审计 (冷路径)

### 3.1 定义

大环 = 节点完成/归档 → MetaTree 审计 → 发现系统性问题 → 回档→修正。
罕见事件，高价值信息 → Transition 记录 → 所有模块学习。

### 3.2 触发条件

```
MetaTree 5 tick 一次审计:

检查:
  1. 归档节点产出是否与其他树冲突？
     例: Execution树节点修改了 /etc/hosts，Constraint树规则 "forbidden:/etc/*"
     → RelationSubstrate 跨树映射发现冲突

  2. 下游节点失败是否由上游节点引起？
     例: Agent N+2 失败 → 上溯到 Agent N 的产出不完整
     → 逆向因果追溯 (见 §四)

  3. 用户后续行为是否暗示之前的执行有误？
     例: 用户编辑了一个刚执行过的文件 → 暗示输出不满足需求
     → BehaviorTree 检测到修正模式

  4. 长期模式: 某类工具/操作反复失败
     → ParameterRegistry 自适应降低相关置信度
```

### 3.3 回档流程

```
Meta 决定回档节点 X:
  1. X.status: ARCHIVED → REOPENED
  2. X 的上下文重新加载到工作区
  3. Meta 写入修正建议 → X.metadata["correction_hint"]
  4. X 重新进入小环 → Think→Act→SelfCheck→Retry
  5. 完成后 → 新版本归档 (版本链)
        X_v1 (ARCHIVED, 不再修改)
        X_v2 (ARCHIVED, 修正后)
  6. Transition 记录: { type:"archive_reopen", cause, correction, value:"high" }
  7. → L5 Memory → 所有学习性模块
```

---

## 四、逆向因果追溯

### 4.1 问题

当前节点 N 失败 → 真的是 N 自己的问题吗？

```
Agent N-2: 读取配置 (成功)
Agent N-1: 解析配置 (成功，但解析结果有遗漏)
Agent N:   基于解析结果执行 (失败！)

→ 问题不在 N，在 N-1 的解析遗漏
→ 但 N 的 Self-Check 只能看到自己的输入和产出
→ 需要向上追溯
```

### 4.2 追溯算法

```
节点 N 失败:

  Step 1: 检查直接上游 (N 的 depends_on)
    读取父节点 M 的产出 → 比对 N 的输入
    → 输入完整 ≠ M 产出完整？→ M 是问题源

  Step 2: 上溯一阶
    检查 M 的祖先 → M 的产出不完整是由谁引起的？

  Step 3: 标记问题边
    RelationSubstrate.create_edge(
      source=M.node_id, target=N.node_id,
      type="causal_trace", evidence="M 产出不完整导致 N 失败",
      confidence=0.8
    )

  Step 4: 修正
    小环: 修正 M (重解析) → N 自动重新执行
    大环: 标记 M→N 边为"需审查" → Meta 审计 → 回档 M

### 4.3 与现有模块关系

```
AgentTreeManager    — 维护节点父子关系 (depends_on)
RelationSubstrate   — 存储因果追溯边
MetaTree            — 读取边, 决定修正策略
ReActRetryEngine    — 执行修正 (小环内)
```

---

## 五、死循环保护

### 5.1 小环死循环

```
同一节点 3 次重试仍失败:
  → 标记 node.status = BLOCKED
  → 记录 Transition: { type:"loop_blocked", node_id, attempts:3 }
  → 退出小环

节点 blocked 后:
  1. Meta 审核 blocked 原因
  2. 如果可自动修复 → 大环回档
  3. 如果无法自动 → upgrade 到 PlanGate → 用户介入

同一子树 3 个节点 blocked:
  → 整个子树 marked as DEGRADED
  → 链路级联检测: CascadeDetector → root_cause
```

### 5.2 CascadeDetector 接入

```
已实现: CascadeDetector 在管线级检测级联故障
需接入: 节点级检测

节点 blocked:
  → CascadeDetector.record(node_id, success=False, latency=...)

CascadeDetector 检测到级联:
  → 输出 { detected:true, root_cause: "Agent N-1", chain: ["N-1","N","N+1"] }
  → Meta 读取 → 直接回档 root_cause 节点
  → 修复 N-1 → N 和 N+1 自动重试
```

### 5.3 大环死循环

```
回档→重新执行→再次回档→再次执行 (循环):
  同一节点被回档 > 2 次:
    → 标记 "persistent_failure"
    → Meta 记录: { type:"reopen_loop", node_id, reopen_count:3 }
    → 升级到 PlanGate → 用户必须介入
    → 不再自动回档此节点
```

---

## 六、与现有模块对接

### 6.1 需要新增的代码

```
1. NodeLifecycle     — 节点级死循环检测 + blocked处理
   (~80L, 挂在 ExecutionPipeline 内)

2. CausalTracer      — 节点失败→向上追溯到根因
   (~60L, 使用 AgentTreeManager.depends_on 边)

3. ReActor            — 统一小环/大环入口 + Transition 记录
   (~50L, 封装 ReActRetryEngine + MetaTree.reopen)
```

### 6.2 已有模块复用

```
ReActRetryEngine      ✅ 5 种策略 (小环)
MetaTree              ✅ 审计/回档 (大环)
CascadeDetector       ✅ 级联检测
AgentTreeManager      ✅ depends_on 边
RelationSubstrate     ✅ 因果追溯边
ParameterRegistry     ✅ 自适应阈值
EventLog              ✅ Transition 记录
```

---

## 七、完整状态机

```
每个节点 (Agent) 的状态:

PENDING ─→ ACTIVE ─→ THINKING ─→ ACTING ─→ SELF_CHECK
                        ↑            │          │
                        │ (retry)    │          │
                        └──── Correct ←── fail ─┤
                                                │ pass
                                                ▼
                                            COMPLETED ─→ ARCHIVED
                                                │             │
                                                │ (blocked)   │ (reopen)
                                                ▼             ▼
                                            BLOCKED ←── ReOPENED
                                                │
                                                │ (persistent)
                                                ▼
                                          USER_TRIAGE
```

---

## 八、死循环/级联 → 学习 → 所有模块受益

```
Transition 记录 (高价值低概率):
  {
    type: "reopen_loop" | "cascade_blocked" | "parent_fault",
    root_cause: "Agent_N1",
    impact_chain: ["N1", "N2", "N3"],
    resolution: "fixed N1 parsing bug",
  }

→ L5 Memory (XML Card, 永久存储)
→ BehaviorTree      "用户在此类任务中常遇到 N1 级问题"
→ ParameterRegistry  降低 N1 类节点拆分的置信度阈值
→ BlueprintEngine   "此类任务加验证步骤，避免 N1 遗漏"
→ ProfileTree       记录用户耐心/容忍度变化
```

---

## 九、与 ReAct/Reflexion/ToT/LATS 的对标

```
能力                   ReAct  Reflex  ToT    LATS   我们
─────────────────────────────────────────────────────────
节点内重试              ✅      ✅      ✅     ✅     ✅ ReActRetryEngine
跨节点因果追溯          ❌      ❌      ❌     ❌     ✅ CausalTracer
冷路径事后审计          ❌      ❌      ❌     ❌     ✅ MetaTree 大环
死循环检测+自动剥离      ❌      ❌      ❌     ❌     ✅ CascadeDetector
归档回档+版本链          ❌      ❌      ❌     ❌     ✅ NodeLifecycle
多树约束冲突消解         ❌      ❌      ❌     ❌     ✅ RelationSubstrate 映射
自我反思注入热路径       ❌      ✅      ❌     ❌     ⚠️ 部分 (FeedbackBridge)
思考树搜索 (BFS/DFS)     ❌      ❌      ✅     ✅     ❌ (先验切分, 不需搜索)
MCTS 模拟回传            ❌      ❌      ❌     ✅     ❌ (成本太高, 不做)

独有优势: 小环快速修正 + 大环深度审计 + 死循环自动剥离 + 多树因果关系
```

---

## 十、实施优先级

```
P0 (本文件):
  NodeLifecycle     — 小环死循环检测 + blocked处理
  CausalTracer      — 逆向因果关系追溯

P1:
  ReActor           — 统一循环入口 + Transition格式化
  cascade→root_cause → 节点级接入
```
