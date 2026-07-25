# ExecutionEngine + PlanGate — 内部业务流

> 2026-07-25 · Phase 0: 内部闭环设计 (先内后外)

---

## 一、单次执行流程

```
LLM Plan (已生成, 含4个步骤)
  │
  ▼
PlanGate.create_checkpoint(plan)
  ├─ 逐步骤风险评估
  │   Step 0: read config.yaml          → LOW
  │   Step 1: edit auth.py              → MEDIUM, first_use → requires_review ✅
  │   Step 2: bash "python test.py"     → LOW  
  │   Step 3: write report.md           → LOW
  │
  ├─ 整体评估: confidence=0.5 < threshold=0.6 → requires_review ✅
  │
  └─ 返回 checkpoint → 前端展示
      { requires_review: true, reasons: ["first_use:edit","confidence<0.6"],
        steps: [4个步骤详情, 每步风险/约束/可编辑] }

──────────────── 用户审批 ────────────────
  用户: 批准 Step 0, 1, 3 / 修改 Step 2 参数
  前端 → PlanGate.apply_user_changes({decision:"adjusted", steps:{...}})

   Pipeline 恢复
     │
     ▼
  ExecutionEngine.execute_batch(steps)
     │
     ├─ Step 0: _read({path:"config.yaml"})    → success, 150ms
     │    产出: file content + {total_lines:42, offset:1}
     │
     ├─ Step 1: _edit({path:"auth.py", edits:[...]})
     │    → 约束检查: /etc/ not in path → pass
     │    → 执行: unified diff 生成
     │    → success, 12ms
     │    产出: "Applied 1 edit(s)\n```diff\n...```"
     │
     ├─ Step 2: _bash({command:"python test.py", timeout:30})
     │    → exit=0, stdout: "3 tests passed"
     │    → success, 850ms
     │    产出: test output + {exit_code:0}
     │
     └─ Step 3: _write({path:"report.md", content:"..."})
          → FileMutationQueue.atomic_write
          → success, 7ms
          产出: "Wrote 512 bytes to report.md"

  ──────────────── 全部完成 ────────────────
  
  归约:
    { status: "completed",
      summary: "4/4 steps completed",
      artifacts: ["auth.py", "report.md"],
      total_duration: 1019ms }
```

---

## 二、异常路径

### 2.1 约束拦截

```
Step: edit /etc/nginx.conf
  → ConstraintTree 检查: "/etc/" in forbidden_paths
  → ExecutionStatus.BLOCKED
  → 产出: error="path blocked: /etc/"
  → 不执行, 直接跳到下一步 (或全部终止, 取决于 PlanGate 配置)
```

### 2.2 超时

```
Step: bash {command:"long_running.sh", timeout:10}
  → 10秒超时
  → ExecutionStatus.TIMEOUT
  → 产出: error="timeout 10s", partial stdout
  → 不阻塞后续步骤
```

### 2.3 用户拒绝

```
PlanGate → requires_review=true → 前端展示
  用户: decision="rejected"
  → 所有步骤 user_approved=false
  → 管线回到 LLM Plan 阶段 → 根据用户反馈重新规划
  → 用户修改记录 → CorrectionJournal → BehaviorChain 学习
```

### 2.4 DRY_RUN 模式

```
PlanGate 可选: 先 dry-run 再真执行
  ExecutionEngine.execute(dry_run_step)
    → 约束检查 + 工具验证
    → 不产生副作用 (不写文件, 不执行命令)
    → success, 3ms
    → 产出: "dry_run: would read config.yaml"
```

---

## 三、行为学习闭环

```
每次用户审批 → PlanGate.record_approval_pattern()
  │
  ├─ tool_use_count[edit] += 1
  ├─ BehaviorGraphBridge.record_observation({
  │     tool: "edit", risk: "medium",
  │     approved: true, modified: false
  │   })
  │
  └─ 下次: 同样用户, edit 非 first_use → 不再 requires_review
      (除非 constraints_violated 或 confidence < threshold)

用户拒绝 → CorrectionJournal.record()
  → 漂移检测: 用户反复拒绝某类操作 → 触发 LLM review
  → Parameter shift: 降低该用户的 complexity_threshold
  → 下一次 Plan 更保守
```

---

## 四、状态机

```
PlanGate 状态:
  CREATED → PENDING_REVIEW → APPROVED → EXECUTING → COMPLETED
                              │            │
                              ├─ REJECTED → RE-PLAN
                              └─ ADJUSTED → EXECUTING

Execution 状态 (每个 step):
  PENDING → RUNNING → SUCCESS
                    → FAILED
                    → BLOCKED
                    → TIMEOUT

异常恢复:
  FAILED/TIMEOUT → 检查 PlanGate 配置
    stop_on_error: true  → 终止全部后续步骤
    stop_on_error: false → 继续下一步 (标记失败)
  无论哪种 → 最终归约包含所有步骤的状态
```

---

## 五、前端交互协议

```
PlanGate 产出 → 前端:
  {
    checkpoint_id: "ckpt_xxx",
    requires_review: true,
    reasons: ["first_use:edit", "confidence<0.6"],
    steps: [
      {idx:0, action:"Read config", tool:"read", risk:"low",
       violated:[], approved:null, modified:false},
      {idx:1, action:"Edit auth", tool:"edit", risk:"medium",
       violated:[], approved:null, modified:false},
      ...
    ],
    decision: "skipped",
    general_note: ""
  }

前端 → PlanGate.apply:
  {
    checkpoint_id: "ckpt_xxx",
    decision: "adjusted",
    note: "change step 2 timeout to 60",
    steps: {
      "0": {approved: true},
      "1": {approved: true},
      "2": {approved: true, params: {timeout: 60}},
      "3": {approved: true}
    }
  }

Execution 结果 → 前端 (流式):
  { step: 0, status: "running", tool: "read", ... }
  { step: 0, status: "success", output: "...", duration_ms: 150 }
  { step: 1, status: "running", tool: "edit", ... }
  { step: 1, status: "success", output: "...```diff", duration_ms: 12 }
  ...
  { status: "completed", summary: "4/4", total_ms: 1019 }
```
