# 执行树消费端 — Grok Build 吸收记录 + 施工方案（2026-08-13）

> 触发: 用户"先把后端闭环了，先吸收？看看已有的那些开源的项目以及
> 别人的经验？……还有马斯克的 Grok Build 也是开源的要不去看看？"
> **2026-08-13 立场修订（用户拍板）**: "我更多是想让你去看他们的实现，
> 设计来讲我们的设计应该还不错，一部分内容设计可学习，主旋律还是看
> 我们自己的为主" —— 吸收 = 学**实现纪律**（事件词汇化/门控/审计可查/
> 工程严谨度），不学**设计理念**（认知架构/元认知/蓝图自增长我们自有
> 且更完整）。吸收点分两类: 「实现纪律吸收」与「设计印证」（仅确认
> 我们方向对，不搬）。
> 目标: 执行树消费端（行为链读树学模式 / 元认知读树发现偏差）——
> 淘宝 PES"全链路可回放"写侧已落地, 消费侧是 P0 半截。
> 吸收方法: A20 竞争吸收（来源→映射→代价→优先级, 吸收≠复制）。
> 源码: xai-org/grok-build（Rust, 1653 rs 文件, 2026-08-13 经 clash
> 7877 代理拉取 $TEMP\grok-build）

---

## 一、Grok Build 关键发现（源码级, 非 README 级）

### 1.1 xai-agent-lifecycle — 生命周期钩子 + 贡献者注册表

```
TurnLifecycleContributor: on_turn_start / on_turn_done / on_turn_abort /
                          on_turn_error（abort 区分 Disconnected/Interrupted）
SessionLifecycleContributor: on_session_idle（会话空转时触发）
核心原则: "Contributors receive data-only per-hook inputs at dispatch
time; anything they act through is a capability injected at install time,
and they never own loop control."
```

**映射**: 消费者（行为链/元认知）= 贡献者——只收数据、不控循环。我们
TaskRunner 的 complete_node 就是 hook 点; 消费端必须做成只读观察者,
禁止在消费回调里改执行流程。

### 1.2 xai-grok-session-events — 类型化事件词汇表（events.jsonl）

```
Event (serde tag, schema_version=1.0):
  TurnStarted{session_id, turn_number, model_id, session_relationship,
              redirect_kind}
  PhaseChanged{phase} / FirstToken / LoopStarted{loop_index}
  ToolStarted{tool_name} / ToolCompleted{tool_name, duration_ms,
              outcome, tool_call_id, source}
  PermissionRequested / PermissionResolved{decision, wait_ms}
  TurnEnded{outcome, cancellation_category}
  Interjected{source, image_count}
  GoalAutoPaused{reason} / TodoGateFired / LazinessClassifierFired /
  LazinessNudgeFired / GoalClassifierVerdict / GoalPlannerCompleted / ...

枚举:
  ToolOutcome: Success | Error | PermissionRejected | PermissionCancelled
               | Followup | HookDenied | InvalidTool | Cancelled
  TurnOutcomeLabel: Completed | Cancelled | Error
  Phase: WaitingForModel | StreamingText | StreamingReasoning |
         ToolExecution | PermissionPrompt
  SessionRelationship: Primary | Subagent
  CancellationCategory: HookDenied | PermissionRejected |
                        PermissionCancelled | MidTurnAbort
```

**映射**: 我们 ExecutionTree 节点 content 就是事件源, 但缺"类型化结果
词汇"——complete_node 只塞 result dict。偏差检测（元认知）需要稳定枚举:
工具结果至少区分 Success/Error/Cancelled（PermissionRejected 归入
decision_bus 权限事件, 已有）。

### 1.3 偏差检测器（元认知读树发现偏差的成熟形态）

```
LazinessDetector: 分类器 → verdict（category+confidence）→ nudge 注入,
                  观察模式可先跑分类不注入（max_nudges=0 仍发事件）
TodoGate: 纯内容回合结束但仍有 pending/in_progress todos → 提醒模型
GoalAutoPaused: 用户取消 / 基础设施错误 / 连续失败退避 / 验证阻塞
                → 自动暂停目标（不是无脑重试）
GoalStrategist: 连续 N 次 NotAchieved → 触发策略子 agent（fail-open）
```

**映射**: 元认知消费器的偏差信号集 = 连续失败节点 / 卡 ACTIVE /
工具抖动（同工具连续不同参数失败）/ 无工具纯文本回合 / 策略切换频率。
关键工程原则: 检测与介入分离（classifier 事件先于 nudge, 可观察）——
我们 decision_bus 事件天然支持（先 audit 事件, 后介入建议）。

### 1.4 dream 凝练（行为链学模式的工程形态）

```
门控（cheapest first）: dream.enabled → 距上次凝练 min_hours → 会话数
  >= min_sessions → DreamLock 获取 → LLM 凝练 prompt → 落 MEMORY.md
锁 + 会话计数防重复凝练; 事件日志是原料, 凝练是批处理
```

**映射**: 行为链学模式 = 执行树上的 dream——会话完成/空闲时门控触发,
从树提取工具序列/成败/深度信号 → 行为链沉淀（BehaviorBrain 事件）。
不做实时逐节点学习（噪声大、成本高）; 批量门控凝练。

---

## 二、吸收点 → 施工映射（A20: 来源→映射→代价→优先级）

> 立场: 主旋律 = 我们自己的设计（PARADIGM/执行层设计）。下表「映射」
> 只取实现纪律; 设计理念类（元认知/蓝图/可逆推）我们自有, 仅印证。

| # | 来源 | 映射到我们 | 代价 | 优先级 |
|---|---|---|---|---|
| A1 | agent-lifecycle 钩子（实现纪律） | 消费端只读观察者、触发不阻塞（TaskRunner complete_node 后调用, 不在回调里改执行流） | 低 | P0 |
| A2 | ToolOutcome 枚举（实现纪律） | ExecutionTree 节点结果词汇化: success/error/cancelled（decision_bus 权限事件已有, 不重复） | 低 | P0 |
| A3 | 偏差检测器分类先行（实现纪律） | 元认知消费器: 检测（连续失败/卡 ACTIVE/工具抖动/纯文本回合）→ 先 audit 事件, 介入仍走 PlanGate（不学 nudge 注入, 与 A8 冲突） | 中 | P0 |
| A4 | dream 门控+锁（实现纪律, 产物不搬） | 行为链消费器: 会话空闲门控触发, 从树提取模式 → BehaviorBrain 事件; 凝练产物走我们启发链可逆推标准（A24）, 不学无验证 MEMORY.md | 中 | P0 |
| A5 | SessionRelationship（设计印证） | 我们 task/sub_agent 层级已有同语义, 无需搬 | 低 | P2 |
| A6 | GoalStrategist（设计印证） | 我们 TaskRunner max_replans + 三层监控已覆盖, 不重复建 | 低 | P2 |

**不吸收**: 事件 JSONL 落盘格式（我们用决策总线/执行树, 不引入第二套
日志）; LazinessDetector 的 nudge 注入（我们元认知介入走 PlanGate,
不另做提醒通道）; dream 的无验证凝练产物（A24 可逆推标准优先）;
任何设计理念层内容（认知架构/元认知/蓝图自增长我们自有且更完整）。

**我们设计 vs Grok 实现（立场备忘）**:
- 我们强在设计: 元认知治理层（Grok 只有产品级启发式）、蓝图自增长
  （Grok 的 goal planner 是硬编码机制）、可逆推抽象标准（Grok dream
  无验证）。
- 我们弱在实现纪律: 自由 dict 事件 vs typed+schema_version、无门控
  批处理 vs dream gate+lock、审计事件不可 schema 校验。
- 结论: 学它的工程严谨度, 不学它的架构; 我们的问题不是设计不行,
  是实现跟不上设计（蓝图薄/消费端空转的根源）。

---

## 二.5 实现细节（重点学习, 源码级拆解）

> 用户: "实现的内容写了吗？这个是重点学习的吧？" —— 以下为 Grok Build
> 具体实现机制, 每条标注「可直接借鉴」/「需适配」/「仅参考」。

### E1 EventTracker（回合内状态 → 事件推导, 需适配到决策总线）

```rust
// xai-grok-session-events/src/tracker.rs
struct ActiveTool { tool_name, tool_call_id, dispatch_duration_ms }

EventTracker {
    writer: EventWriter,               // Clone+Send+Sync, 后台任务共享
    turn_ended_emitted: Cell<bool>,    // 双发射守卫
    active_tool: RefCell<Option<ActiveTool>>,  // 在飞工具追踪
    turn_tool_count: Cell<u32>,        // 本回合工具数（TodoGate 用）
    prior_interrupt_category: Cell<Option<CancellationCategory>>,  // 跨回合一次性
    prior_redirect_kind: Cell<Option<RedirectKind>>,               // 跨回合一次性
    pending_interrupt_reminder: Cell<bool>,                        // 跨回合一次性
}

// 关键机制:
// 1) emit_turn_ended: replace(true) 守卫 → 杜绝重复 TurnEnded
// 2) tool_started/finished/cancel_active_tool: 取消复用 dispatch 计时
//    （不二次计时）; 调度中被取消的工具无 tool_completed 行
// 3) 跨回合一次性标记: begin_turn 故意不重置, 由下一个真实用户回合
//    消费（prior_interrupt 给下一轮 prompt 框上"上次被中断"上下文）
// 4) writer() 克隆: 追踪器活在会话 actor, 后台任务拿独立句柄
```

**借鉴**: 双发射守卫（我们 decision_bus 事件防重）、跨回合标记
（我们 ExecutionTree 节点可挂"中断原因"供下一回合消费）。
**适配**: 我们不落 events.jsonl, 事件进决策总线/树节点。

### E2 EventWriter（JSONL 追加, 仅参考——我们用决策总线）

```rust
// xai-grok-session-events/src/log.rs
struct EventEntry { ts: String, #[serde(flatten)] event: Event }
EventWriter { file: Mutex<Option<File>>, error_logged: AtomicBool }
// append(true) 打开; emit 时打 RFC3339 毫秒时间戳; 写失败只告警一次
// （error_logged.swap(true) 抑制重复刷屏）; noop() 供测试丢弃
```

**借鉴**: 写失败只告警一次（我们日志里重复刷屏的坑, 环境坑已记类似）;
noop 写手模式（测试注入）。

### E3 DreamLock + dream 门控（可直接借鉴到行为链消费器）

```rust
// xai-grok-memory/src/dream_lock.rs
DreamLock { path: workspace/.dream-lock }   // PID 锁文件 + mtime
last_consolidated_at()   // 读锁文件 mtime = 上次凝练时间
acquire()                // PID 存活探测（unix kill-0 / win OpenProcess+
                         // WaitForSingleObject(0)）; 持有者死亡或超过
                         // stale_secs → 回收陈旧锁; 失败可 rollback

// dream.rs 门控（cheapest first）:
check_dream_gates(config, lock, sessions_dir) -> DreamGate
  Disabled → TooSoon{hours_since} → TooFewSessions{count, required}
  → Open{sessions}（开锁才凝练, 防并发重复）
```

**借鉴**: 门控顺序（最便宜先查）、PID 锁 + 陈旧回收 + rollback、
会话数门（不是每次都凝练）。我们行为链消费器照此实现:
`session_idle → 距上次 >= N 分钟 → 新增任务数 >= K → 消费`。

### E4 生命周期钩子（数据只入、能力注入、不控循环）

```rust
// xai-agent-lifecycle/src/send/contributors/turn_lifecycle.rs
trait TurnLifecycleContributor {
    async fn on_turn_start(&self, _input: &TurnStartInput) {}
    async fn on_turn_done(&self, _input: &TurnDoneInput) {}
    async fn on_turn_abort(&self, _input: &TurnAbortInput) {}   // Disconnected|Interrupted
    async fn on_turn_error(&self, _input: &TurnErrorInput) {}
}
trait SessionLifecycleContributor {
    async fn on_session_idle(&self, _input: &SessionIdleInput) {}  // 空转触发
}
```

**借鉴**: 钩子输入数据只读（data-only）; 贡献者注册表（ExtensionRegistry）
安装时注入能力; 消费端永远不拥有循环控制——我们消费器保持同一纪律。

### E5 偏差检测器（分类先行, 介入后置）

```
TodoGate: 纯内容回合结束仍 pending/in_progress todos → 提醒模型
          （事件: TodoGateFired{fires, pending, in_progress} /
          TodoGateExhausted —— 命中上限单独成事件, 不与正常触发混淆）
LazinessDetector: classifier → verdict{category, confidence} → nudge
          （观察模式 max_nudges=0 仍发分类事件 —— 先验证质量再介入）
GoalAutoPaused{reason}: 用户取消 / 基础设施错误 / 连续失败退避 /
          验证阻塞 —— 每个暂停原因都是显式枚举
```

**借鉴**: 检测与介入解耦（先事件后动作）; 上限耗尽单独成事件;
暂停原因显式枚举（对齐我们 A12 状态转化词汇）。

### E6 目标子 agent 机制（仅参考——我们有 max_replans + 蓝图重规划）

```
GoalPlanner: 写计划文件（fail-closed）
GoalClassifier: 判定 Achieved/NotAchieved（infra 错 fail-open / 解析错
                fail-closed —— 两类失败语义不同）
GoalStrategist: 连续 N 次 NotAchieved → 策略子 agent（fail-open）
```

**借鉴**: fail-open vs fail-closed 的显式区分（infra 失败放宽、
解析失败收紧）——我们 TaskRunner 错误处理可对齐此语义。

---

## 二.6 实现细节续 — Hermes（NousResearch/hermes-agent, 2026-08-13）

> 背景: benchmark 轮（2026-08-06）只读了能力对标表, 未做源码级深读
> （用户: "之前读过，但是读的不全是吗？"）。本轮按 Grok Build 同方法
> 拉 agent/ 关键实现（API 目录树 + raw 精准下载; 仓库 643MB 不整包拉;
> run_agent.py 触发门控因 raw 限流未取, 记为待补）。

### H1 background_review.py（后台审核 = 元认知"审核"维度的实现样本）

```
形态: 审核 = 子 agent（bounded tools: memory / skill_manage）,
      不是规则扫描器。父 agent 回合后 spawn 后台线程, 审核子 agent
      用专用 prompt + 专用工具改记忆/技能。
触发: review_memory / review_skills 两个布尔维度 → prompt 组合选择
      （_MEMORY_REVIEW_PROMPT / _SKILL_REVIEW_PROMPT / _COMBINED）;
      focus（用户 /refine 指令）追加到 prompt 优先执行。
动作汇总: summarize_background_review_actions — 只报 memory/skill_manage
      工具的成功动作; 对 prior_snapshot 的 tool_call_id/content 去重
      （旧结果不重复呈现, issue #14944）; notification_mode off/on/verbose
      三档。
数据纪律: build_memory_write_metadata — 记忆写入带元数据。
```

**借鉴**: 审核维度化触发（按信号组合选 prompt）; 动作汇报去重;
审核与介入解耦（审核=子 agent 专用工具, 介入=它直接改记忆——注意
这与我们"元认知裁决"不同, 我们审核后动作仍走决策总线留痕）。

### H2 session_activity.py（观察契约 = 消费器频率纪律）

```
observation-only 心跳: timestamp + 有界描述（120 字符钳制）+ provenance
  （名词来源枚举: unknown / agent.compression / compression_timeout /
   compression_cooldown）
频率纪律: SESSION_ACTIVITY_HEARTBEAT_MIN_INTERVAL_SECONDS = 60.0 —
  "deliberately a code constant, independent of any config, so no
  configuration can turn the heartbeat into a high-frequency writer"
  （配置不能把观察投影变成高频写手）; force_persist 是唯一旁路
  （终端标签必须落盘时）。
消费者区分 work 类型（API/tool/compacting/stalled）与描述文本——
  没有独立 phase 枚举。
```

**借鉴**: 消费端/监控端的心跳最小间隔写成代码常量（我们的行为链消费器
同样: 门控间隔不能被配置调成热写）; provenance 枚举（我们 audit 事件
带来源枚举）; 终端状态可绕过频率（任务结束立即消费）。

### H3 learning_graph.py（记忆→技能连接 = 我们 v2 缺口项的实现）

```
节点: 非基础技能（agent 创建/使用过）+ MEMORY.md/USER.md 记忆块
边:   技能 related_skills 声明边 + 记忆→技能词法重叠边（派生）
用途: 桌面端"学习可见化"图（answer: 哪些已学技能和我记的东西相关）
```

**借鉴**: 记忆→技能词法重叠边 = 我们 COMPLETENESS_GAP 的 v2 项
（"记忆→技能连接 learning_graph 词法重叠边"）——执行树消费端可顺带
产出: 执行中高频工具 ↔ 行为链技能节点的重叠边。

### H4 memory_manager.py（50KB, 骨架）

```
（未逐行读; 记录到: 记忆写入带 metadata（build_memory_write_metadata）、
记忆/技能管理走专用工具（memory / skill_manage）, 与 background_review
同一套工具面。）
```

### 待补（raw 限流）

- run_agent.py 的 _spawn_background_review 触发门控（回合后间隔/阈值）;
- curator.py / moa_trace.py（raw 404, 可能路径变更）。

---

## 二.7 实现细节续 — OpenCode（anomalyco/opencode, 2026-08-14）

> 来源: 原 sst/opencode（已迁移 anomalyco/opencode）; 核心在
> packages/opencode/src（session/storage/snapshot/skill/plugin）;
> 仓库 450MB, 用 2.0 分支 tree API + raw 精准下载。TypeScript +
> effect-ts + zod 全契约。

### O1 SessionStatus（最小状态词汇 + 总线事件）

```ts
// packages/opencode/src/session/status.ts
Info = idle | retry{attempt, message, next} | busy
Event = session.status{sessionID, status} | session.idle{sessionID}
// InstanceState + bus.publish; set(idle) 时发 idle 事件并删状态
```

**借鉴**: 状态词汇极小（3 态）却够用; 状态变更即总线事件（我们
decision_bus 同模式）; 状态存储与事件解耦。

### O2 SessionRunState（并发纪律）

```ts
// run-state.ts
runner(sessionID): 复用现有 Runner; busy() 抛 BusyError（防并发双跑）
onIdle → 删 runner + status.set(idle); onBusy → status.set(busy)
cancel: 非 busy 直接置 idle; busy 则 runner.cancel
Scope finalizer: 作用域关闭时 cancel 全部 runner（清理纪律）
```

**借鉴**: 并发守卫（我们 statemachine 同会话重入要防）; Scope finalizer
统一清理（我们 TaskRunner 异常路径的收尾纪律可对齐）。

### O3 Doom loop 检测（最可借鉴的偏差信号）

```ts
// processor.ts
const DOOM_LOOP_THRESHOLD = 3
recentParts = parts.slice(-3)
if (recentParts.length === 3 &&
    recentParts.every(p => p.type === "tool" &&
      p.tool === 当前工具 &&
      JSON.stringify(p.state.input) === JSON.stringify(当前输入))) {
  yield* permission.ask({ permission: "doom_loop", ... })  // 停循环问用户
}
```

**借鉴**: 死循环判定 = 同工具 + 同输入（JSON.stringify 相等）连续 3 次,
不是"失败次数"——**输入不变才是真循环**。我们 ExecutionMonitor 的
"同工具连续失败"可升级为"同工具同输入连续 N 次"（含成功但空转）。

### O4 Todo（事务性全量替换）

```ts
// todo.ts
update: Database.transaction(delete-all + insert-all(带 position))
  → bus.publish("todo.updated", {sessionID, todos})
// 简单可靠: 无 diff/增量, 全量替换 + 排序字段
```

**借鉴**: todos 不做增量合并, 全量替换保一致（我们 ExecutionTree 步骤
记录是追加语义, 场景不同; 但"替换即一致"的纪律可参考）。

### O5 Compaction（prune + 保护 + replay + 模板摘要, 实现最成熟）

```ts
// compaction.ts
PRUNE_MINIMUM = 20_000（少于该量不剪）
PRUNE_PROTECT = 40_000（保留最近这么多 token 的工具调用输出）
PRUNE_PROTECTED_TOOLS = ["skill"]（关键工具输出永不剪）
prune: 从最新消息反向扫描 → completed 工具输出 token 估算累计 →
  超 PROTECT 部分标记 compacted（time.compacted 落库）→
  遇 summary 消息或已 compacted 边界停
process: compaction 专用 agent（agent="compaction"）生成续接摘要,
  模板: Goal / Instructions / Discoveries / Accomplished /
  Relevant files; overflow 时找上一个未压缩用户消息 replay;
  plugin 触发点: "experimental.session.compacting"（可注入上下文/
  替换 prompt）; "experimental.chat.messages.transform"（消息变换）
```

**借鉴**: 剪枝=**只删工具输出不删结构**（对应我们"截断保留结构"的
方向）; 保护阈值 + 保护工具表; 专用压缩 agent + 模板化摘要（对应我们
L2 摘要, 模板更工程化）; overflow replay（我们压缩后的延续性可对齐）;
plugin 触发点（我们蓝图/事件钩子的同构物）。

### O6 Retry policy（退避）

```ts
// retry.ts — SessionRetry.policy({ ... }) → retry{attempt, message, next}
// processor 用 Effect.retry(policy), 失败状态经 status.retry 广播
```

**借鉴**: 重试状态化（attempt/message/next 可见可查）——我们网关已有
退避+jitter, 执行层重试可对齐状态化。

### OpenCode 实现质量评估（诚实）

- **强**: effect-ts + zod 全契约（schema 即文档）; 状态机纪律（Runner/
  BusyError）; 压缩机制成熟（prune+protect+replay+模板）; doom loop
  判定精确（输入相等而非失败次数）; 插件触发点体系。
- **不同**: 单 agent 工具, 无认知多树/元认知/蓝图自增长/召回（我们的
  设计域）; todo 是平面表无依赖图; 无执行树跨会话审计（我们是执行树
  消费端要做的）。
- **结论**: 它是"实现纪律"的上佳样本——尤其 compaction 与 doom loop,
  直接进我们的施工映射（执行树消费端的偏差信号 + 摘要模板）。

---

## 二.8 实现细节续 — OpenClaw（openclaw/openclaw, 2026-08-14）

> 训练知识级（架构）已在会话确认: channels→triggers→agents→skills→
> gates→memories + SOUL.md。以下为源码核实级（agent-core +
> memory-host-sdk, main 分支 tree + raw 下载; 仓库 2.5GB, 只取核心包）。

### C1 内部钩子 + 工具批次生命周期（执行准入的实现纪律）

```ts
// agent-core/src/internal-hooks.ts
InternalBeforeToolBatchHook(context, signal?) → Result | undefined
  // 批次级准入钩子（执行前拦截/放行整批）
InternalToolBatchLifecycle {
  commitReadyCalls(calls)      // 获批调用即将启动时提交（可抛错）
  releaseSkippedCalls(ids)     // 被 steering 跳过的调用释放准入状态
}
InternalToolExecutionPreparer  // 两阶段工具执行准备:
  kind: "immediate" {outcome, dispose}   // 无需执行（本地结果/错误）
  kind: "ready" {args, execute, dispose} // 准备就绪, 真正执行
```

**借鉴**: 批次准入 = 我们的 PermissionEngine 审批, 但多了
commit/release 生命周期（获批后启动前还能拦）; 两阶段准备
（immediate/ready）让"不需真执行的调用"零成本——我们工具层可对齐
（如纯计算工具直接返回）。

### C2 工具循环恢复（doom loop 的批次级处理, 优于单次问询）

```ts
// agent-core/src/agent-loop.ts
toolLoopRecoveryState.criticalToolLoopSeen
executeToolCalls(...) → {messages, terminate, steeringMessages,
                         intervention, terminateRun}
  // 批次内检测到关键循环 → intervention → criticalToolLoopSeen = true
  // → 同批次后续调用全部抑制:
  //   "This tool was not executed because another call in the batch
  //    triggered critical tool-loop recovery."
  // → 下一轮又出现关键循环 → terminateRun:
  //   "OpenClaw stopped this run because tool-loop recovery encountered
  //    another critical loop. No blocked tool action was executed."
```

**借鉴**: 死循环处理三级: 检测 → 批次内抑制（不执行后续调用）→ 二次
循环终止整轮（明确消息, 不静默）。比"每次问用户"更工程化。我们
ExecutionMonitor 的 replan 可对齐: 检测 → 抑制同批 → 二次终止。

### C3 turn-interruption（跨回合中断契约, 与 Grok/OpenCode 同模式）

```ts
// agent-core/src/turn-interruption.ts
createFailureMessage(model, error, aborted)
  // 规范失败消息: stopReason = "aborted" | "error" + errorMessage
INTERRUPTED_TURN_GUIDANCE = `<turn_aborted>上一回合被中断, 后台进程
  可能仍在运行, 被中止的工具可能已部分执行。</turn_aborted>`
  // 下一回合注入（appendInterruptedTurnMessage → messages.push + emit）
isTurnHandoffAbort(signal)
  // turnHandoff=true 的中止（yield 式工具主动交接）不注入中断引导 —
  // 干净停下的回合不该被告知"工具可能部分执行"
```

**借鉴**: 中断语义三态（用户中断 / 工具交接 / 错误）; 交接型中止与
意外中止区分（我们 TaskRunner abort 可对齐）; 中断引导注入下一轮
（对应 Grok prior_interrupt_category 跨回合标记）。

### C4 循环控制细节

```
STEERING_TOOL_SKIP_MESSAGE = "Skipped due to queued user message."
  // steering 检查点: 排队的新用户消息到达 → 跳过本轮工具, 注入说明
prepareNextTurn({model, thinkingLevel})  // 每轮可切模型/思考级别
turnTainted ||= toolResults.some(toolResultTaintsTurn)  // 污染累积
removeNonExecutableToolCalls / ensureToolTurnIdentity
  // 流式后处理: 清不可执行调用 / 保证工具轮身份
```

**借鉴**: steering 优先级（用户新消息打断工具批）; 每轮模型/思考级
切换（我们网关已支持 thinking 开关, 执行层可按轮切）; taint 累积
（我们 _turn_tainted 同语义）。

### C5 memory-host-sdk（骨架, 待补）

```
engine-embeddings / engine-sessions / engine-storage / query /
runtime-core — 记忆宿主 SDK（向量化/会话/存储分层）。
（未逐文件读; 记录为待补: 记忆分层与 query 的具体实现。）
```

**待补**: agent-loop 中 executeToolCalls 的 intervention 判定细节;
memory-host-sdk 记忆分层; skills 发现/生命周期（marketplace 侧）。

---

## 二.9 实现细节续 — OpenWorker（andrewyng/openworker, 2026-08-14）

> 之前读过 CODE_INSTRUCTIONS/agents/code.py（代码方法论）; 本轮补
> 记忆/压缩/审计/技能模块（coworker/memory + compaction + audit +
> skills/store）。

### W1 审计日志（AuditStore, 脱敏纪律）

```python
# coworker/audit.py
audit_events: id/timestamp/session_id/agent/workspace/connector/tool/
              stage/status/approval/args/result_preview/reason/resource
append: 逐事件落 SQLite（RLock 串行）;
  _sanitize_args: 密钥键（token/secret/password/api_key/...）→ [redacted];
    body/content/html 键 → [redacted body]; browser text → [redacted input]
  _resource: 从参数+结果提取资源标识（可过滤维度）
list: session/connector/tool 过滤 + limit(≤500)
```

**借鉴**: 审计落库即脱敏（存储层做, 不依赖调用方）; resource 维度
（我们 audit 事件可补"资源"字段, 过滤查询用）。

### W2 记忆存储（SQLite, 简单可靠）

```python
# coworker/memory/sqlite_store.py + base.py
memories: id/scope(WORKSPACE等)/key/content/summary/workspace/
          session_id/created_at
PRAGMA 迁移: 缺 summary 列 → ALTER TABLE 补（不迁移数据, 渲染时
  回退 content 首行截断）
check_same_thread=False + RLock（服务线程与建库线程不同）
```

**借鉴**: 列级向后兼容（缺列即补, 旧行回退渲染）——我们 G0 索引缓存
的指纹迁移可对齐; 跨线程锁纪律。

### W3 Compaction（spec-in-code 典范, 最值得全文吸收）

```python
# coworker/compaction.py — 纯函数 + 一个 dataclass;
# 引擎只拥有"何时/用什么模型", 注入调用（可测性设计）
DEFAULT_THRESHOLD_PCT = 0.8   # min(0.8×window, cap)
DEFAULT_CAP_TOKENS = 250_000  # 1M 窗口也提前压缩（质量/延迟先退化）
KEEP_RECENT_FRACTION = 0.25   # 最新切片保留（token 预算, 非回合数 —
                              # 一个大工具循环不能饿死工作集）
SUMMARY_MAX_TOKENS = 3_000    # 摘要调用: 关工具 + 上限
_USER_MESSAGE_CLIP = 600      # 用户消息机械保留（裁剪粘贴大块）
_USER_MESSAGES_MAX = 40       # 上限防无限增长（重复压缩不回收窗口）
_TRIM_FRACTION = 0.10         # 无摘要时的修剪兜底
核心原则: "The persisted transcript is never modified; only what is
  sent to the model." —— 压缩只改出站视图, 不改持久化原文
摘要要求列出用户消息 → 被丢用户消息的意图活在摘要里
```

**借鉴**: ①纯函数+注入（我们 recall 的测试性设计可对齐）; ②cap 提前
压缩（1M 模型也 250K 触发）; ③token 预算而非回合数; ④用户消息机械
保留 + 摘要列意图（对应我们"压缩保留行为证据"的 A24 工程化）;
⑤只改出站视图不改持久化（我们 L5 压缩的边界纪律）。

### W4 技能存储（skills/store.py 25KB, 骨架）

```
（未逐行读; 记录: skills 有 base/store 分层, 与 memory 同款
SQLite 持久化。待补: 技能发现/生命周期细节。）
```

---

## 三、吸收汇总（5 项目 × 执行树消费端相关实现纪律）

| 项目 | 状态 | 核心吸收点 | 进施工 |
|---|---|---|---|
| Grok Build | ✅ 深读 | 类型化事件词汇 / 生命周期钩子 / dream 门控+锁 / 偏差检测器 / fail-open-closed | A1-A4 |
| Hermes | ⚠️ 部分 | 后台审核=子agent+专用工具 / 动作汇报去重 / 心跳频率纪律 / 记忆→技能词法边 | H1-H3 |
| OpenCode | ✅ 核心深读 | doom loop=同输入判定 / compaction prune+protect+replay / RunState 并发守卫 / 事务性 todo | O3-O5 |
| OpenClaw | ✅ 核心深读 | 工具批次准入+两阶段准备 / 循环恢复三级（检测→抑制→终止）/ 跨回合中断契约 | C1-C3 |
| OpenWorker | ✅ 本轮补全 | 审计脱敏落库 / 压缩 spec-in-code（纯函数+cap+token预算+只改出站视图） | W1-W3 |

**跨项目共识（可视为实现纪律基线）**:
1. 事件/状态全部类型化 + schema 版本化（Grok/OpenCode/OpenClaw）
2. 检测与介入分离, 偏差判定用"输入不变"而非"失败次数"（Grok/OpenCode/
   OpenClaw 三方印证）
3. 消费/监控有频率纪律（代码常量门控, 配置不能变高频写手）
4. 压缩只改出站视图, 保护阈值 + 保护工具表 + 模板化摘要（OpenCode/
   OpenWorker 双印证）
5. 跨回合中断/交接语义显式化（Grok/OpenClaw 双印证）
6. 审计落库即脱敏（OpenWorker）

**对照我们设计（无冲突, 均为实现纪律）**:
- 执行树消费端 = 检测与介入分离（对应我们元认知: 检测层新消费器 +
  介入仍走 ExecutionMonitor/PlanGate）
- 行为链学模式 = dream 门控（在线学习保持 A9, 只学批处理门控）
- 压缩 = OpenWorker/OpenCode 纪律（我们 L2 摘要/压缩边界对齐）

---

## 四、实施路线（用户拍板: 设计主线 + 学实现思路; 拼凑的根源=没分离）

```
阶段 0 写侧补齐（数据基础）:
  TaskRunner._step_hook 每步 ok/error 写 sub_agent 节点（结果词汇化）;
  complete_node 结果规范化（status: ok/error/cancelled）— 吸收 A2/O3
阶段 1 ExecutionTree 只读消费 API:
  get_tasks/get_subagents/tree_patterns; doom loop 判定=同工具+同输入
  连续 3 次（O3）; 卡 ACTIVE/纯文本回合/深度信号
阶段 2 元认知消费器 MetaTreeConsumer（检测, 不介入）:
  decision_bus exec_tree_audit 事件（schema 化）; 介入权保持
  ExecutionMonitor/PlanGate（吸收纪律 2）
阶段 3 行为链消费器 BehaviorTreeConsumer（学习）:
  dream 门控（E3）+ 最小间隔代码常量（H2）; 工具序列/成败/深度信号
  → BehaviorBrain 事件（A9 在线契约）
阶段 4 执行摘要对齐（压缩纪律）:
  模板摘要（Goal/Discoveries/Accomplished/Files 简化, O5）;
  只改出站视图不动持久化（W3）
阶段 5 接线 + 全量回归:
  engine._consume_execution_tree + TaskRunner 收尾 + v3 API;
  并发守卫同会话防双跑（O2）; 6 条纪律基线验收表
```

## 五、待办（2026-08-14 追加）

- **预测学习加强（用户拍板待办）**: 行为链预测引擎（P(B|A) + Q(state,
  action), A9）后续要系统加强——学术领域可吸收: 世界模型（World
  Models）、预测编码（Predictive Coding）、next-action prediction /
  行为序列建模（contrastive learning / self-supervised prediction /
  RL 世界模型 Dreamer 系）; 与我们的二阶抽象（DMN→ECN→启发链, A24
  可逆推）结合: 预测学习的"预测-验证"闭环天然是启发链的在线形态
  （预测=发散假设, 观测=收敛验证, 回流=可逆推更新）。
  施工形态: 执行模式沉淀（阶段 3）的数据是预测学习的第一手原料
  （工具序列/成败/深度信号）; 后续接预测引擎训练。

## 六、施工完成度（2026-08-14, 执行树消费端）

| 阶段 | 内容 | 状态 | 代码/测试 |
|---|---|---|---|
| 0 | 写侧补齐: step outcome/input 落树（tool_loop + _step_hook + _outcome_of 词汇化） | ✅ | tool_loop.py / task_runner.py / tree_manager.py |
| 1 | 只读 API: get_tasks/get_subagents/tree_patterns + doom loop 同输入判定 + 卡 ACTIVE 修复 | ✅ | tree_manager.py + 5 测试 |
| 2 | MetaTreeConsumer: 5 类偏差信号 → exec_tree_audit 事件（schema 化, 介入分离） | ✅ | tree_consumers.py + 3 测试 |
| 3 | ExecutionPatternStore: dream 门控 + 模式沉淀 + 持久化（不碰 BehaviorBrain 用户模型） | ✅ | tree_consumers.py + 2 测试 |
| 4 | 执行摘要三策略（mechanical/llm/hybrid）+ 只读纯函数 | ✅ | tree_consumers.py + 5 测试 |
| 5 | 接线: engine._consume_execution_tree + v3 收尾触发 + 同会话并发锁 + 限流测试时序修复 | ✅ | engine.py / v3_session_api.py / rate_limiter.py |
| 5.5 | 闭环补: AuditFeedbackLoop（审计事件窗口聚合 → 达阈值触发策略权重回流, A6） | ✅ | tree_consumers.py + 4 测试 |
| 5.6 | 量化评测: scripts/exec_consume_eval.py → docs/test/EXEC_CONSUMPTION_EVAL_20260814.md | ✅ | 36 标注树 + 回流 + 性能 + 确定性 |

### 6 条纪律基线验收表（吸收是否真的落地）

| # | 纪律基线 | 验收 | 状态 |
|---|---|---|---|
| 1 | 事件/状态类型化 + schema | exec_tree_audit 入 VALID_KINDS, 事件字段固定（kind/signal/dimension/reason/payload）; 结果词汇 success/error/cancelled | ✅ |
| 2 | 检测与介入分离, 同输入判定 | MetaTreeConsumer 只发事件（不发 replan/abort）; doom loop = 同工具+同输入连续 3 次 | ✅ |
| 3 | 消费频率门控 = 代码常量 | MIN_INTERVAL_SECONDS 代码常量（60s/300s）, 配置不可调; force 旁路仅终端状态 | ✅ |
| 4 | 压缩只改出站视图 | render_execution_summary 纯函数（测试验证树不变）; 摘要模板化 | ✅ |
| 5 | 跨回合中断语义 | step outcome/input 落树, 树消费可查; 完整跨回合中断引导留待预测学习轮 | ⚠️ 部分 |
| 6 | 审计落库即脱敏 | exec_tree_audit 进决策总线; 脱敏字段（密钥/正文）未做（当前载荷为工具名/输入摘要, 无密钥面） | ⚠️ 待补 |

**回归**: 相关套件 420 passed / 0 failed（执行/LLM/API/蓝图/事件/运行时/服务）;
执行树消费端专项 15 测试; 限流测试时序修复后 9/9 × 3 连跑稳定。

### 量化评测结果（2026-08-14, 只量化有可量化价值的维度）

- **偏差检测**: 5 信号 precision/recall/F1 全 1.00（合成树与规则检测器
  自洽 → 定位为回归保护, 非真实世界精度; 真实执行迹标注集是待办）
- **回流有效性**: 2 次 doom_loop → AuditFeedbackLoop 触发 → MetaFeedback
  收到低分审计(0.2) — 闭环真生效（不是只看事件数）
- **性能缩放**: tree_patterns 10→0.03ms / 100→0.17ms / 500→0.91ms /
  1000→1.66ms — 近线性, 千节点亚 2ms
- **确定性**: 36 棵双跑信号一致

---

## 三、施工方案（后端闭环第一批）

### 3.1 ExecutionTree 消费端只读 API（tree_manager.py）

```
get_tasks(status=None)                     # 全部 task 节点（plan）
get_subagents(task_id)                     # 某任务的全部 sub_agent 步骤
tree_patterns()                            # 提取: 任务数/成功率/失败分布/
                                           # 工具序列统计/卡 ACTIVE 数/
                                           # 每任务步骤数/深度信号
```

### 3.2 行为链消费器（新文件 core/agent/execution/tree_consumers.py）

```
BehaviorTreeConsumer.consume(tree, session_id, engine):
  门控: 会话空闲或任务完成后触发（调用方控制频率, 消费器不自行循环）
  提取: tree_patterns() → 工具序列模式（成功/失败/抖动）→
        BehaviorBrain 事件（engine._run_behavior_brain, 复用既有链路）
  深度信号: 任务步骤数分布 → W7 深度偏好雏形（后续接扩散 k 自适应）
```

### 3.3 元认知消费器（同文件）

```
MetaTreeConsumer.consume(tree, session_id, bus):
  偏差信号（对齐 Grok 检测器）:
    - 连续失败: 同任务 >=2 个 error 子节点 → audit 事件
    - 卡 ACTIVE: 完成时间早于阈值仍 ACTIVE → 卡住告警
    - 工具抖动: 同工具连续失败 >=2 次 → 抖动事件
    - 纯文本回合: task 无任何 sub_agent 步骤 → 无工具回合事件
  输出: decision_bus.log(kind="exec_tree_audit", ...) — 检测与介入分离
```

### 3.4 接线（平台层, 硬编码）

```
TaskRunner.run() 收尾（complete_node 后）: 不阻塞触发消费器
  engine 侧统一入口: engine._consume_execution_tree(session_id)
v3_session_api 工具循环收尾调用（per-session 树）
```

### 3.5 验收

- ExecutionTree 消费端只读 API + 单元测试（造树 → patterns 正确）
- 行为链消费器: 造树（2 成功 1 失败 + 工具序列）→ BehaviorBrain 收到事件
- 元认知消费器: 造树（连续失败/卡 ACTIVE/抖动）→ decision_bus 有
  exec_tree_audit 事件（kind/维度/原因可查）
- 回归: TaskRunner 8/8 + 相关套件全绿

---

## 四、环境记录

- grok-build 拉取: git smart-HTTP 走 clash 代理失败（SSL EOF/侧带中断）,
  GitHub API 走代理正常 → 改用 codeload tar.gz（9.8MB）+ bsdtar 解压;
  1 个文件截断（managed_mcp.rs, 不影响主体）。
- 沙箱内 git 直连 GitHub 卡死（3.6MB 停住）; 代理 7877 对 API/codeload 通。
