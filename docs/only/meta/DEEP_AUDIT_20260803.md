# 元认知深层次复核（第二轮·实锤验证）

> 日期: 2026-08-03 | 对象: `meta/feedback_bridge.py` + `meta/meta_subscriber.py` +
> `v4/cognitive/metacognition.py` + `v4/cognitive/meta_consumer.py` +
> `runtime/engine.py`（meta 相关段）+ `cli/engine.py` + `cli/registry.py`（接线路径）
> 方法: 源码精读 + 全库 rg（赋值点/调用点）+ 运行时探针
> 结论: **第一轮 2 处说法被修正；实锤 4 个「有实例无数据流」的静默失效**。

---

## 一、第一轮修正

### 1.1 「v4 MetaCognition 零生产调用」→ 部分错误

```
cli/engine.py:320-321  _engine._meta_cognition = MetaCognition(llm_provider=..., vcs=None)
cli/engine.py:274-277  _state_machine = DeciderStateMachine() + register_all_handlers
event/handlers.py:182-216  handle_meta: mc.retrospect(...) + mc.scan(engine) + stats
→ CLI 生产路径（start_engine）下，META 阶段会调用 v4 MetaCognition。
```

**但**（数据流断，见执行层 DEEP_AUDIT §3.2）:

```
handle_meta 里 ctx.get("intent", {}) 恒空（handler 输出不传下游）
→ mc.retrospect(target="general") 永远用 "general" —— 参数实际无意义
→ v4 MetaCognition 有调用、有副作用（scan 扫描 engine），但输入参数断裂。
```

### 1.2 「MetaSubscriber 生产路径有实例」→ 有实例但从未订阅

```
cli/registry.py:311-319  _meta_factory: MetaSubscriber(event_log=None, bus=None) ← bus=None
  MetaSubscriber.__init__: if self._bus is not None: 订阅 8 个 EventType ← bus=None 跳过
cli/engine.py:348-355  wire: obj.event_log = event_log; obj._bus = event_bus; obj.bus = event_bus
  ← 只赋属性，不重新订阅
→ 实例存在，但订阅列表为空 → _on_event 永远不会被调用 → 审查逻辑全死
```

### 1.3 「FeedbackBridge 真接线」→ 读路径通、写路径断

```
读路径（agent_native）: consume()/consume_belief()/consume_drift() 被调用
写路径: post_decision() 全库零调用方（rg 实证，仅 feedback_bridge.py 自身 docstring）
→ FeedbackBridge 恒空，三层写回（urgent/belief/drift）从未产生数据
```

### 1.4 「v6 MetaConsumer 是唯一收口闭环」→ 死代码

```
runtime/engine.py:1218  if self._meta_consumer and self._trace_v3 and ...:
→ _meta_consumer 全库无赋值点（rg 实证）→ 恒 None → 条件恒 False
→ _trace_v3 除 None 初始化外无赋值点（rg 实证）→ 恒 None
→ v6 MetaConsumer 闭环（每 5 轮 consume）从未执行
```

> **勘误（DESIGN_FULL_READ §5.2）**: 更准确表述为「类实现完整、引擎未接线」——
> `ExecutionTraceV3`（state/execution_trace.py:17，含 meta_analyze/diff）与
> `MetaConsumer`（v4/cognitive/meta_consumer.py:15）类均完整；断点是
> `runtime/engine.py` 从未创建 `_trace_v3`/`_meta_consumer` 实例（恒 None）。
> 修复 = 接线实例化，非重写。

---

## 二、实锤汇总（4 个静默失效）

| # | 组件 | 现状 | 根因 |
|---|---|---|---|
| M1 | FeedbackBridge | 恒空（读通写断）| post_decision 零调用方 |
| M2 | MetaSubscriber | 实例存在、从未订阅 | factory 传 bus=None + cli 不重订阅 |
| M3 | v6 MetaConsumer 闭环 | 死代码 | _meta_consumer/_trace_v3 恒 None |
| M4 | v4 MetaCognition | 有调用但参数断裂 | handler 输出不传下游（retrospect 恒 general）|

### 补充: MetaReviewer / MetacognitiveTriggerEngine（第一轮确认）

```
event/cognitive_loop.py:85 MetaReviewer —— 生产无消费证据
observability/metacognitive_trigger.py + trigger_wiring.py —— 无生产挂载
```

---

## 三、元认知 ↔ 行为链/持久化接口（现状）

```
元认知写路径（设计）: Meta 审查 → FeedbackBridge → agent_native（PCR 参数/信念/漂移）
  → 实际断在 post_decision（无人写）
元认知持久化（设计）: MetaState/决定 → meta_state.json / EventLog
  → event/handlers.py:216-231 handle_meta 只回读 stats，不落盘
  → MetaCognition._save()/_load() 内部 JSON（v4/cognitive/metacognition.py:302-321）
行为链联动（设计）: BehaviorLearner（cognitive_loop.py）→ slow_path
  → D6 已确认: slow_path 不存在（关联链审计 F8 方向 = process_chain）
```

---

## 四、待拍板/待修复清单（元认知）

| # | 级别 | 事项 | 方向 |
|---|---|---|---|
| M5 | P0 | 元认知写路径整体断（M1+M2+M3）| 补 post_decision 调用 + 订阅接线 + _meta_consumer/_trace_v3 初始化 |
| M6 | P1 | MetaSubscriber 延迟订阅机制 | registry 或 cli 提供显式 subscribe() |
| M7 | P1 | handler 输出传下游（联动 X4）| run_pipeline 注入阶段结果 |
| M8 | P2 | 三套元认知（v3 Adapter/v4 MetaCognition/v6 MetaConsumer）归一 | 全局讨论拍板 |
| M9 | P2 | MetaReviewer/TriggerEngine 去留 | 全局讨论拍板 |
