# 执行层 — 整体业务流

> 2026-07-25 · 七棵树协同 · 子Agent派生/执行/归约/归档 · 查询驱动 · ReAct闭环

---

## 流一：子Agent 派生决策 (LLM 元认知综合判断)

```
LLM Plan 产出
  │  { steps: [...], confidence: 0.72, 
  │    risk_flags: ["edit targets auth/"], complexity: 0.75 }
  │
  ▼
元信息组装 (Compass+PCR+PlanGate):
  {
    complexity: 0.75,          ← Compass + PCR
    context_size: 14_000,      ← ContextAssembler
    threshold_8k: true,
    estimated_subtasks: 3,
    tools_involved: ["read","edit","bash"],
    constraints: ["forbidden:/etc/*"],
    behavior_hints: ["user prefers concise","approved edit before"],
    confidence: 0.72,
  }
  │
  ▼
LLM 决策 (Meta 调用):
  输入: 元信息 + TaskGraph
  输出: { action: "split", sub_agents: [
            {id:"a1", task:"read config", context_size:1200, pointers:[→ConstraintTree.security]},
            {id:"a2", task:"edit auth.py", context_size:3500, pointers:[→ConstraintTree.security,→BehaviorTree.code_style]},
            {id:"a3", task:"test changes", context_size:800, pointers:[→ConstraintTree.test_rules]}
          ] }
  │
  ▼
AgentTreeManager: 创建 3 个子节点挂在 ExecutionTree 下
  每个子节点 = DiscourseBlock + task + pointers + query
  上下文: ≤4K (ContextAssembler 裁剪)

模式切换 (可在 PlanGate 配置):
  纯阈值: context_size > 8K → 自动 split (无 LLM)
  纯 LLM: 不看阈值, LLM 自由决定
  关闭: 永不派生 (单Agent 顺序执行)
```

---

## 流二：子树并行执行 + 查询驱动

```
AgentTreeManager 创建 3 个子Agent
  │
  ├─ 子Agent a1: "read config"
  │     接收: { task, context(1200 tokens), pointers:[→ConstraintTree.security], queries:[] }
  │     │
  │     ├─ 需要约束规则 → query → ConstraintTree
  │     │     query "SELECT rule WHERE domain=security AND scope=config_file"
  │     │     ├─ 活跃节点找到 → 直接返回规则
  │     │     └─ 未找到 → 双方案:
  │     │          ① 开子Agent 搜索持久化层
  │     │          ② 同时在 L5 Memory 搜索
  │     │          → 两结果 LLM 去重 → 返回
  │     │
  │     ├─ 执行: _read(path) → 成功
  │     └─ 产出: { status:"success", artifacts:[], findings:[], duration_ms:150 }
  │
  ├─ 子Agent a2: "edit auth.py"                              ← 并行
  │     接收: { task, context(3500 tokens), 
  │            pointers:[→ConstraintTree.security,→BehaviorTree.code_style] }
  │     │
  │     ├─ 查约束: pointer → ConstraintTree.security_rules
  │     │     找到: "auth模块修改必须加注释"
  │     │
  │     ├─ 查偏好: pointer → BehaviorTree.code_style
  │     │     找到: "用户偏好4空格缩进, 单行<80字符"
  │     │
  │     ├─ 执行: _edit(path, edits) → ConstraintTree 实时验证 → 通过
  │     │     产出: "Applied 2 edits\n```diff...```"
  │     └─ 产出: { status:"success", artifacts:["auth.py"], duration_ms:45 }
  │
  └─ 子Agent a3: "test changes"                              ← 并行
      接收: { task, context(800 tokens), pointers:[→ConstraintTree.test_rules] }
      │
      ├─ 查约束: pointer → ConstraintTree.test_rules
      │     "测试必须在修改后运行"
      │
      ├─ 执行: _bash("python test.py") → exit=0, "3 tests passed"
      └─ 产出: { status:"success", artifacts:[], findings:[], duration_ms:850 }

等待所有完成 (最多 timeout)
  │
  ▼
三个子Agent 全部完成 → MetaTree 归约
```

---

## 流三：MetaTree 归约 + 质量评估

```
三个子Agent 产出集合
  │
  ▼
MetaTree.StructuredSynthesizer:
  │
  ├─ 1. 重要性评估
  │     a1: config read → 低价值 (常规操作)
  │     a2: edit auth.py → 中价值 (代码修改)
  │     a3: tests passed → 低价值 (常规结果)
  │
  ├─ 2. 分配合并次数
  │     a2: 2次合并 (结构化→压缩→LLM)
  │     a1, a3: 3次合并 (结构化→摘要→丢弃)
  │
  ├─ 3. 归约
  │     a1+a3: 摘要为 "配置读取完毕, 3个测试通过"
  │     a2:   LLM 归约 "修改auth.py: 添加安全校验+统一代码风格"
  │
  └─ 4. 产出:
       {
         status: "completed",
         summary: "3/3 子Agent完成. 修改auth.py添加安全校验, 3个测试通过.",
         artifacts: ["auth.py"],
         learning_points: ["首次edit操作已获用户批准"],
         total_ms: 1045,
       }
  │
  ▼
父Agent 接收归约结果:
  → ConstraintTree: 更新 "auth.py 已被修改" 状态
  → BehaviorTree: 记录 "用户批准edit" 模式
  → ExecutionTree: 子节点归档为 Memory Node
  → DiscourseTree: 追加本次执行摘要
```

---

## 流四：归档 + 回档 + ReAct 重试

```
子Agent 完成 → MetaTree 质量评估
  │
  ├─ 达标 → 归档
  │     子节点 → Memory Node (只读)
  │     Transition 记录: { completed, artifacts, duration }
  │     L5 Memory: FederationIndex 更新索引
  │
  └─ 不达标 → ReAct 重试
        │
        ├─ 明确错误: edit diff 冲突
        │    → 自动修正: 重新读取文件, 重新 diff
        │    → Max 3 retries
        │    → 3次仍失败 → 提升到父节点 → LLM 决策
        │
        ├─ 模糊: 测试失败但原因不明
        │    → 降低 temperature (0.3→0.1) → LLM 重新推理
        │    → 扩展子Agent 上下文: 加载更多相关历史
        │
        └─ 信息不足:
             → 派生检测Agent: "检查依赖是否完整"
             → 检测Agent 返回 → 补充信息 → 重新执行

每次重试 → Transition 记录:
  {
    retry_1: { reason:"diff conflict", new_approach:"re-read file", result:"success" },
    retry_2: null,  # 一次修正即可
  }

回档 (罕见, 低概率高价值):
  归档 3 ticks 后 → 新bug 发生 → Meta 追溯
  → LLM: "这可能是之前 auth.py edit 引起的"
  → MetaTree.reopen(memory_node_id)
  → 打开归档节点 → 检查历史 diff
  → 发现: edit 时遗漏了一个边界条件
  → Transition 记录 → L5 Memory:
     { type:"rare_reopen", cause:"edit_auth_missed_boundary",
       value:"high" } → 所有模块学习

回档的特殊处理:
  - 不是"删除归档" — 是 "重新激活为工作节点"
  - 原归档节点 → status:REOPENED → 加载到 trees 的工作区
  - 修正完成后 → 新的归档节点 (版本链)
  - 原归档节点 保留 (不可变)
```

---

## 流五：跨树冲突裁决 + 外部工具融合

### 5.1 跨树冲突

```
ExecutionTree: 完成 edit /etc/hosts
ConstraintTree: 规则 "forbidden:/etc/*"

  → RelationSubstrate 映射发现冲突
  → MetaTree 裁决:
      1. 查 BehaviorTree: 用户之前批准过 /etc/ 编辑? → 否
      2. 查 ProfileTree: 用户技术级别? → expert
      3. 决策: "用户是 expert, 但规则明确禁止"
      4. 动作: notify PlanGate → 返回用户确认
      5. 用户批准 → BehaviorTree 记录例外
                 → ConstraintTree 添加白名单规则
```

### 5.2 外部工具融合

```
任务: "分析代码安全, 用 OpenCode 做静态分析 + Codex 做漏洞检测"
  │
  ├─ OpenCode Agent → MCP → 结果: { findings: [sql_injection, xss] }
  ├─ Codex Agent    → MCP → 结果: { vulnerabilities: [sql_injection, path_traversal] }
  │
  ▼
外部工具归一化:
  OpenCode → ExecutionResult { source:"opencode", findings:[{type:"sql_injection",...},{type:"xss",...}] }
  Codex    → ExecutionResult { source:"codex", findings:[{type:"sql_injection",...},{type:"path_traversal",...}] }

LLM 去重 + 融合:
  输入: 两个归一化结果
  LLM: sql_injection 重复 → 保留 Codex 版本 (置信度更高)
       xss 仅 OpenCode 报告 → 保留
       path_traversal 仅 Codex 报告 → 保留
  融合输出: { findings: [sql_injection(Codex,0.92), xss(OpenCode,0.85), path_traversal(Codex,0.78)] }

→ MetaTree 归约 → 写入 AssociationTree (关联到代码文件)
→ ConstraintTree: 添加安全规则 "所有PR需通过sql_injection检查"
→ BehaviorTree: 记录 "用户关注安全"
```

---

## 完整端到端时序

```
T=0     用户输入: "分析 auth.py 安全性并修复, 跑测试确认"
T=50ms   Compass → PCR → Intent → L4 → Context (全部 <50ms)
T=1200ms LLM Plan 生成: 3个步骤
T=1210ms PlanGate.check: Step 2(edit) first_use → requires_review
         → 前端展示 Plan → 用户审批 → 批准 (用户耗时 ~5s)
T=6220ms PlanGate.approved → AgentTreeManager.split → 3个子Agent
         ┌ a1: read config         (1200 tokens)
         │ a2: edit auth.py        (3500 tokens)   ← 并行
         └ a3: bash test           (800 tokens)
T=6230ms a2 query → ConstraintTree (查询安全规则)
         ├─ 活跃节点命中 → 返回 "auth修改需加注释" (1ms)
         └─ query → AssociationTree (查实体关系) (未命中)
T=6240ms a2 查偏好 → pointer → BehaviorTree.code_style → 命中 (1ms)
T=6250ms a1 执行: read config.yaml → 成功 (150ms)
T=6400ms a1 返回
T=6285ms a2 执行: edit auth.py → Constraint 实时验证 → 通过 (45ms)
T=6330ms a2 返回  
T=7150ms a3 执行: bash "python test.py" → 3 tests passed (850ms)
T=8000ms a3 返回 ← 所有子Agent 完成
T=8010ms MetaTree 归约: 重要性评估 → a2:2次合并, a1+a3:3次合并 (10ms)
T=8025ms 归约完成 → 父Agent 收到 summary
T=8100ms LLM Answer 生成: "已修复, 测试通过" (75ms)
T=8200ms 归档: 3个子节点 → Memory Node → FederationIndex 更新
T=8200ms ─── 用户看到回答 (8.2s 总耗时, 含 5s 用户审批) ───

异步:
T=8200ms NODE_COMPLETED × 3 → EventLog → Subscriber 消费
T=5 ticks Meta Subscriber 审计 → FeedbackBridge
  审核: "a2 edit 通过了约束检查, a3 测试覆盖完整" → 无修正
```

---

## 各树活跃度时间线

```
          T0         T1         T2         T3         T4         T5
          Plan       派生      执行       归约      归档       审计
Discourse  ████       ██        ██        ██        ███        █
Execution  ████       ███████   █████████  ███       ██         -
Constraint ██         ████      ████       ██        ██         -
Association-          ██        ██         -         -          █
Behavior   ██         ███       ██         ██        ██         ██
Meta       -          ██        ██         ███████   ██         ███
Profile    -          -         -          █         █          █
```
