# v2 执行层分层施工 — 蓝图宏观 + tool_loop 微观 + 元认知监控（2026-08-09）

> 状态: 施工完成 ✅（设计: EXECUTION_LAYER_ARCHITECTURE_20260809.md 定案）
> 验证: 22 项新测试 + 150 项回归全绿 + 真 LLM 端到端冒烟通过

---

## 一、施工内容（四壳补全）

tool_loop（function calling 循环）此前是"无蓝图约束的自由 ReAct"。
本轮补齐四个壳, 让执行层真正走"蓝图宏观约束 → 执行层微观实现 → 元认知
监控 → 用户可见 → 复盘回流"的分层设计。

### 1. tool_loop 增强（微观引擎, `core/agent/llm/tool_loop.py`）
- `allowed_tools`: 工具白名单（蓝图节点约束, 只注入节点范围内工具）
- `system_inject`: 节点目标/约束注入（合并进首条 system 消息）
- `on_step`: Hot 监视钩子（每步工具执行后回调）
- `timeout_s`: 总执行截止（超时提前终止返回 error=timeout）
- 返回新增 `trace`: 每步 {round, tool, ok, latency_ms, error}
- 全部参数可选, 向后兼容（既有 5 项测试不回归）

### 2. ExecutionMonitor（元认知监控, `core/agent/meta/execution_monitor.py` 新建）
- Hot: 每步信号（步骤/失败/工具名/耗时/连续失败）— 零 LLM, 纯算法
- Warm: `evaluate()` 确定性裁决（对齐 META_ARBITER §2.2 三信号）:
  - 预算超时 → replan（MC 例: 手搓超时 → 换 forge）
  - 失败率超阈值 / 同一工具连续失败 → replan
  - 轮次耗尽无结果 → ask_user
  - 正常 → continue
- Cold: `review()` 非 continue 裁决写 `meta_advice` 决策事件（可回看）
- 阈值参数化（failure_rate / repeat_failures / ask_user_rounds）

### 3. TaskRunner（蓝图节点级执行壳, `core/agent/llm/task_runner.py` 新建）
- `build_inject()`: 节点目标/范围/工具白名单 → system 注入文本（层1→层2）
- 重规划循环: 监视裁决 replan → InterventionRouter 三层介入路由 →
  replanner 回调给替代约束 → 重跑（上限 max_replans）
- 三层介入生效（META_ARBITER §3.3）: 低=applied 留痕 / 中=proposed
  不阻塞 / 高=sync_required 停下等用户确认
- 复盘回流（A6）: 执行成败 → ExecutionAudit → MetaFeedback.consume
- 返回 TaskResult: status/verdict/content/tool_calls/trace/events（白盒）
- 事件进 DecisionEventBus（engine 总线 → /v6/changelog 回看可介入）

### 4. 接线（生产路径）
- **statemachine**（`core/agent/event/statemachine.py`）: tool 链节点
  `params.agentic=True` → TaskRunner 按节点目标执行（DAG 内 agentic 节点）;
  静态 tool 节点路径不变（不回归）
- **v3 主流程**（`core/agent/api/v3_session_api.py`）: 编码类请求从裸
  tool_loop 升级为 TaskRunner —— 已确认任务图注入为"允许范围"宏观约束;
  run_dag context 透传 decision_bus/model; 执行迹写入会话工作区
- **白盒端点**（`core/agent/api/stubs_api.py`）: `GET /v6/execution/{sid}`
  返回会话各节点执行迹（verdict/工具链/耗时/决策事件）

## 二、验证

### 新测试 22 项（全绿）
- execution_monitor 8: Hot 信号 / continue / 失败率 replan / 连续失败
  replan / 预算超时 replan / 轮次耗尽 ask_user / 复盘事件 / continue 跳过
- task_runner 7: 约束注入 / continue 无事件 / replanner 重规划循环（事件
  已写、二次注入新目标）/ 无 replanner ask_user / 高风险 sync_required
  abort / MetaFeedback 写回 / build_inject 纪律
- statemachine_agentic 2: agentic 节点走 TaskRunner / 静态节点不回归
- tool_loop 5（既有, 兼容性）: schema 含 OS 工具 / 执行 / 链式 shell 拦截 /
  未知工具 / 编码请求检测

### 回归 150 项（全绿）
event 套件 + meta + llm + blueprint（intervention/meta_side_effect/
protection）+ api（task_graph_versions/changelog/code_exec_postprocess）

### 真 LLM 端到端冒烟（直连网关 8080, deepseek-v4-flash）
`TaskRunner.run("写一个 hello_world.py 并运行它",
allowed_tools=[write_file, run_python, run_shell], max_rounds=6)`
→ LLM 自主 write_file（23 bytes）→ run_shell（stdout "Hello, World!",
exit 0）→ 中文总结 → status=ok verdict=continue, 3 轮, 0 replan,
3.8s。约束注入生效: LLM 只在白名单内调工具, 无越界。

## 三、改动文件

```
M core/agent/llm/tool_loop.py            # 约束/过滤/超时/钩子/trace
A core/agent/meta/execution_monitor.py   # 三层监控
A core/agent/llm/task_runner.py          # 蓝图节点执行壳
M core/agent/event/statemachine.py       # agentic 工具节点分支
M core/agent/api/v3_session_api.py       # Phase 4 TaskRunner + 执行迹
M core/agent/api/stubs_api.py            # /v6/execution/{sid}
A core/agent/meta/tests/test_execution_monitor.py
A core/agent/llm/tests/test_task_runner.py
A core/agent/event/tests/test_statemachine_agentic.py
```

## 四、边界与后续

- Warm 裁决为确定性算法（v1）; Warm 单次 LLM 评估（策略切换深度判断）
  留 P2（META_ARBITER §四监视分层）
- 前端执行迹展示（/v6/execution + changelog）属阶段 B 前端绑定
- "用户可制止/加约束"已具备接口: changelog intervene（approve/reject）;
  前端按钮绑定待阶段 B
- MC 全场景验收（手搓→超时→自动换 forge→前端可见）已由单元测试覆盖
  逻辑; 真 LLM 复现需构造长任务, 留后续
