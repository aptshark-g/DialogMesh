# ExecutionGovernor 设计 — 执行链路横切治理（元认知子模块, AOP）

> 状态: 设计定案 + 骨架落地 | 触发: 用户"需要再做一个 AOP 模块? 专门做
> 纠错/熔断/降级/幂等/复盘, 应属元认知子模块, 否则内部对高可用匮乏。
> 为什么之前看开源项目没看到这个?"
> 关联: HA_EXECUTION_ANALYSIS_20260816（共因）; PARADIGM A10/P14（元认知
> 治理）; A16（快反馈后修正）; A18（真实验证）。

## 〇、为什么之前吸收开源时没看到"治理层"

1. **吸收视角把高可用归给了网关** — OPENSOURCE_SURVEY 明确写"循环上限+
   熔断 — 网关断路器"; md_big 只落"最大循环次数与超时熔断"（tool_loop
   轮数/超时）。即: 熔断被视为基础设施层的事, 没有上升为业务执行链路
   的横切层。
2. **开源 agent 没有独立治理层** — Grok Build 的 LazinessDetector /
   GoalStrategist、OpenClaw 的循环恢复都是**产品级启发式**（挂业务上）,
   不是横切组件; 吸收时聚焦执行轨迹/树消费/doom loop, 没提炼"治理切面"。
3. **我们的设计有哲学无落点** — PARADIGM A10"元认知治理一切"、P14"治理
   可修改对象"讲的是**治理内容**（审核/版本化）, 没承诺**治理执行链路**
   （熔断/降级/幂等/重试策略）。所以执行链路的高可用散落成"各调用点
   各自超时重试"（上轮 HA 分析已实锤）。

结论: 不是没看, 是**看了但归错了层**。ExecutionGovernor 把它补回元认知
子模块, 正好兑现我们自己 A10/P14 的设计（元认知 = 治理层）。

## 一、定位

**ExecutionGovernor = 执行链路的横切治理切面（AOP 风格）**, 属元认知
（A10）子模块。职责五件:

| 能力 | 说明 | 现状（无 Governor 前） |
|---|---|---|
| 熔断 | 按 scope（阶段/工具）统计失败率, 连续失败达阈值 → 开断快速失败, 半开试探恢复 | 只有网关 HTTP 层, 业务链路无 |
| 降级 | 熔断/预算耗尽时的显式降级路径（骨架/摘要/缓存） | 散落, 部分静默 |
| 幂等 | 同 request_id+scope 重入保护（处理中短路/去重） | 只有会话级执行锁 |
| 纠错 | 失败原因分类 → 定向重试策略（timeout/empty/connection/parse 不同处理） | 各调用点各写一套 |
| 复盘 | 每次治理动作写 decision_bus + 统计, 元认知消费 | 无链路级复盘 |

## 二、与现有组件边界

- **ExecutionMonitor**（任务级）: 单任务 Hot/Warm/Cold 监控裁决 —
  Governor 是**链路级**（跨任务/跨阶段）, 不抢任务裁决。
- **call_recorder**（观测）: 只记录（延迟/空/错）— Governor 是**决策**
  （熔断/重试/降级）, 消费 recorder 的统计。
- **网关熔断**（switch）: 单次 HTTP 连接层 — Governor 是**业务链路层**
  （阶段/工具维度, 含规划/意图分类/工具执行）。
- **decision_bus**（事件）: Governor 的复盘输出进总线, 与
  tree_consumers/MetaFeedback 闭环（A6/A10）。

## 三、核心机制

### 1. CircuitBreaker（按 scope 键）
```
状态: CLOSED → OPEN（失败率≥阈值 或 连续失败≥N）→ HALF_OPEN（冷却后）
      → 试探成功回 CLOSED / 失败回 OPEN
参数: failure_threshold, min_calls, cooldown_s, half_open_max
动作: OPEN 时该 scope 快速失败（返回降级信号, 不再发 LLM/工具调用）
```

### 2. RetryPolicy（按错误类型定向）
```
timeout      → 降预算重试 1 次（剩余预算/2）
empty        → 重试 2 次（现有）; 预算 <30s 不重试
connection   → 快速重试 1 次（网关瞬时抖动）
parse        → 不重试（返回骨架/降级）
```
收敛现有散落重试（tool_loop 3 次 / llm_reply 3 次 / planning 0 次）。

### 3. IdempotencyGuard（幂等短路）
```
键 = (request_id, scope); 处理中 → 短路返回"in_flight"（不重复调用）
```

### 4. 降级 + 复盘
- 降级: OPEN/预算耗尽 → 显式降级（骨架/摘要/缓存）, 带 reason 进事件
- 复盘: governor 动作（open/close/degrade/retry）→ decision_bus.log
  kind="governor_action" → 元认知消费器可审计（复用 tree_consumers 通道）

## 四、落点（骨架已落地）

- 模块: `core/agent/meta/governor.py`（元认知子模块）
- 接入: call_recorder 观察失败 → governor 判定; tool_loop._call_gateway
  熔断前检查 + 重试策略; _plan_with_skill/classify 熔断降级
- 白盒: /v6/governor（熔断状态/统计/最近治理动作）

## 五、验收

- 单测: 熔断三态/半开恢复/错误定向重试/幂等短路/治理事件
- 真实链路: 网关挂 → governor 熔断该阶段 → 快速失败 + 事件可查
  （不再每次请求磨蹭 3 次重试）
