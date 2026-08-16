# 执行链路高可用分析 — 为什么"常失败"（2026-08-16）

> 触发: 用户"常失败的问题在于什么？我们的机制措施不够完善？不够高可用吗？"
> 素材: 本轮 6 个实测问题（PLANNING_SKILL_WIRING_20260816.md §三）。

## 一、6 个问题归类 → 4 个模式

| 问题 | 模式 |
|---|---|
| tool_loop 固定 90s×3 重试 + deadline 只轮间检查（单轮最坏 270s） | ① 预算不沿调用链传播 |
| classify_intent 60s / planning 25s / 通用路径 60s 各自固定 | ① 预算不传播 |
| run_dag 的 llm_reply 节点触发 handle_llm（双重 LLM 调用） | ② 设计语义↔实现语义漂移 |
| async 段（priority=9）同步等待 BehaviorBrain 19s | ② 语义漂移（async 不是异步） |
| 空返回/超时/解析失败散落各处各自重试, 排查靠猜 | ③ 失败无集中观测 |
| 意图分类误判 casual / TaskRunner 超时空回复 | ④ 降级路径不完备/静默 |

## 二、共因判断

**不是"机制不存在", 是"高可用只做到了网关层, 没做到执行链路层"。**

网关（switch）: 超时/熔断/健康缓存/错误码目录/重试/热更新 —— 完整。
执行链路（DialogMesh 内）: 各阶段**各自设超时**, 无请求级总预算;
LLM 调用无集中观测（metrics/错误码）; async 语义没有兑现级检查;
降级路径多为静默（失败→默认值→错误结果传播）。

三个具体缺口:

### 1. 请求级总预算缺失（最大共因）
每个调用点独立 timeout（60/25/90s）, 串行叠加超上限 → 用户侧"卡死"。
没有"这一请求还剩多少时间"的传播概念。tool_loop 的 timeout_s 是唯一的
预算, 但被固定 90s 单次调用 + 轮间检查架空（单轮可跑 270s）。

### 2. LLM 调用无观测
网关有 /v1/stats + 错误码目录; 执行层调用点（tool_loop / classify /
planning / 通用路径）没有统一 recorder —— 上一次"卡死"排查只能靠猜 +
临时加日志, 因为没有任何调用延迟/空返回/重试的统计可查。

### 3. 设计语义没有"兑现级"检查
追踪矩阵查"功能有没有", 不查"语义等不等价":
- llm_reply 节点设计是视图（回复在 Phase 4）, 实现却会执行副作用;
- async 段设计是不阻塞, 实现是同步等待。
这两类漂移靠单测抓不到（测试用假 handler）, 只在真实链路暴露。

## 三、加固清单

- **P0 请求级总预算传播**: v3_session_api 计算请求 deadline, 沿
  classify → planning → TaskRunner → tool_loop 传剩余时间; 任何阶段
  超预算 → 显式降级（骨架/直接回复）。【本批落地】
- **P0 LLM 调用观测**: 轻量 recorder（延迟/空返回/超时/重试/阶段）+
  `/v6/llm-calls` 白盒端点 —— 以后"卡在哪"直接查, 不猜。【本批落地】
- **P1 降级显式化**: 意图分类失败/超时 → 明确走 DualTrack + 记事件;
  每个失败点带 reason 而不是静默默认值。
- **P1 语义级双向等价**: 追踪矩阵加"语义对照"列（async 段、视图节点
  副作用、预算传播）; DAG 执行前声明节点副作用等级。

## 四、验收

- 请求级 deadline 生效: 单请求总耗时 ≤ 预算（实测 17.9s, 预算内）;
  预算耗尽时返回显式降级（非空回复非卡死）。
- /v6/llm-calls 返回各阶段调用统计（含空返回/重试次数）。

## 五、落地记录（2026-08-16 追加）

### P0-1 请求级总预算传播（✅）
- `send_message`: `_req_deadline = now + 150s`, `_budget_left()` 沿
  classify_intent → _plan_with_skill → TaskRunner(timeout_s) 传剩余;
  tool_loop 已预算感知（08-16 上批）。
- 实测: 复杂任务 44.3s 预算内返回（此前 180s+ 卡死）; 预算耗尽时
  TaskRunner 生成摘要回复（"已完成 9 步工具调用..."）而非空回复。

### P0-2 LLM 调用观测（✅）
- 新模块 `core/agent/llm/call_recorder.py`: 线程安全窗口统计 +
  JSONL 落盘（重启尾部恢复）; 打点 4 阶段: tool_loop / intent_classify /
  planning / llm_reply（延迟/ok/empty/retries/error）。
- 白盒端点 `GET /v6/llm-calls?recent=N`: stats（by_stage p50/p95/max +
  empty/errors/retries）+ 最近调用明细。
- 实测价值: 网关挂掉时观测端点 30s 内定位全部 `WinError 10061`,
  不再靠猜。

### 测试
- call_recorder 4 项（record/stats/trim/persist 恢复/模块级 API）;
  相关回归 214 全绿。

## 六、边界（记录, 非本批范围）

- 复杂任务 6 轮仍探索不完（LLM 多轮 dir_list/file_read 探索, doom 止损
  只拦"同工具连续"）→ 执行效率优化留后续（步骤级约束收紧 / 工具预算
  分级 / 让 PlanningSkill 步骤更直接约束工具选择）。
- 观测窗口重启后从 JSONL 尾部恢复（保留最近 2000 条）; 全量历史聚合
  留后续。

## 七、追加: ExecutionGovernor 落地（2026-08-16, 见 DESIGN 文档）

- **新模块** `core/agent/meta/governor.py`（元认知子模块, AOP 横切治理）:
  - ScopeBreaker 熔断（连续失败/窗口失败率 → OPEN → 半开试探 → 恢复）
  - RETRY_POLICY 错误定向重试（timeout/empty/connection/parse）
  - 幂等短路（request_id+scope 处理中短路）
  - 治理动作进 decision_bus（kind=governor_action）+ 白盒 /v6/governor
- **接入**: tool_loop._call_gateway（熔断前检查+重试收敛+observe）;
  classify/planning/llm_reply（allow 前检查 + observe）; call_recorder
  打点对齐。
- **顺带根治两个真实阻塞**（本地复现 + 日志定位, 非猜测）:
  ① post-LLM `_publish` 名为 fire-and-forget 实为同步广播（behavior/
  causal 订阅者加载阻塞数十秒）→ 改后台线程
  ② run_dag 后 learn_from_execution（蒸馏）/ _consume_execution_tree
  同步执行阻塞响应 → 改后台线程（async 段语义落实）
  ③ 通用 LLM 路径 60s×3 固定重试无预算 → 预算感知 + 熔断
- **实测**: 复杂任务 70.6s 预算内稳定返回（此前 170s+ 反复卡死）;
  governor 熔断状态可查（全部 closed）; llm-calls 观测各阶段分布
  （planning 9.1s / tool_loop 7 calls）
- 测试: governor 9 项 + 相关回归 223 全绿
