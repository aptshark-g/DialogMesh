# 元认知（09）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/meta/` + `core/agent/metacognition.py` +
> `core/agent/v4/cognitive/metacognition.py` + `core/agent/v4/cognitive/meta_consumer.py` +
> `core/agent/observability/metacognitive_trigger.py` + `core/agent/event/cognitive_loop.py`（Meta 部分）
> 结论先行: **元认知体系存在 5 套并行实现，且「蓝图审计：Meta 学习闭环零调用方」已被本轮修正**
> —— v4 MetaConsumer 在 runtime/engine.py:1218 有真实调用（每 5 轮），但 v4 MetaCognition
> 主类（提交/扫描/复盘/自审）**零生产调用**，只有 CLI 诊断入口。

---

## 一、文件清单与体量

| 文件 | 体量 | 定位 | 生产消费者 |
|---|--:|---|---|
| `meta/feedback_bridge.py` | 3.0KB | 决策/信念/漂移 3 队列 | orchestrator/agent_native + bootstrap_v6（真实接线）|
| `meta/meta_subscriber.py` | 2.5KB | MetaState + 事件订阅审查 | cli/engine.py:348 + cli/registry.py:311（冷路径）|
| `metacognition.py`（根）| 6.7KB | MetaCognitionAdapter + Scheduler（v3 旧版）| 仅 cli/subsystem_registrations.py:67 注册，零生产调用 |
| `v4/cognitive/metacognition.py` | 13.8KB | v4 MetaCognition（提交/扫描/复盘/自审）| 仅 cli/engine.py:320 挂载 `_meta_cognition` + p3_cmd/p10_cmd 诊断 |
| `v4/cognitive/meta_consumer.py` | 4.7KB | v6 MetaConsumer（收口学习闭环）| **runtime/engine.py:1218 真实调用**（每 5 轮）|
| `observability/metacognitive_trigger.py` | 6.3KB | 触发引擎（信号阈值→事件）| observability/trigger_wiring.py（无生产挂载证据）|
| `event/cognitive_loop.py` | 9.6KB | BehaviorLearner + MetaReviewer + CognitiveLoop | v4/cognitive/runtime.py:18 run_cognitive_loop（低层）|
| `v4/cognitive/mind.py` | 5.4KB | Mind（拉 trace/profile/MetaConsumer）| 仅 bench 脚本 |

**5 套并行实现族:**
1. **v3 规则式**: `metacognition.py`（MetaCognitionAdapter + Scheduler，token 阈值触发）
2. **v4 审查式**: `v4/cognitive/metacognition.py`（ReviewItem / Rapid+Deliberate 双通道 / Retrospection）
3. **v6 消费式**: `v4/cognitive/meta_consumer.py`（consume(trace, turn_count) → 建议）
4. **桥接式**: `meta/feedback_bridge.py`（决策/信念/漂移三队列，agent_native 消费）
5. **触发式**: `observability/metacognitive_trigger.py`（Trigger 规则 → MetacognitiveTriggerEngine）

---

## 二、消费矩阵（全库 rg 实证）

### 2.1 FeedbackBridge（唯一真实主路径接线）
```
orchestrator/agent_native.py:121-122   correction = feedback_bridge.consume()      ← 每轮消费
orchestrator/agent_native.py:272-273   belief = feedback_bridge.consume_belief()
orchestrator/agent_native.py:281-282   drift = feedback_bridge.consume_drift()
orchestrator/agent_native.py:346       _try_load_feedback() → FeedbackBridge()   ← 兜底自建
orchestrator/bootstrap_v6.py:57,87,129-131  _load_feedback_bridge() → FeedbackBridge
```
→ **agent_native 主路径真接线，但数据源（谁 post_decision？）需在第二轮核查**。

### 2.2 MetaSubscriber（冷路径）
```
cli/engine.py:348      meta_subscriber 启动项（engine 冷路径）
cli/registry.py:311-318 注册 MetaSubscriber（init_order=45, required=False）
cli/commands/p3_cmd.py:32-38 诊断读取 _meta_subscriber._turn_count
event/tests/test_subscribers.py:63 单测
```
→ 生产路径有实例，但 **MetaSubscriber 的事件消费（`_on_event` → `_should_review` → 发布）
是否真正生效需要验证**（第二轮深读）。

### 2.3 v4 MetaCognition（诊断级）
```
cli/engine.py:320-321  _meta_cognition = MetaCognition(llm_provider=..., vcs=None)
cli/commands/p10_cmd.py  self-audit 入口
cli/commands/p3_cmd.py:50  诊断
cli/registry.py:343-344     注册（required=False, init_order=60）
```
→ **submit()/scan()/process_queue()/retrospect()/self_audit() 均无生产调用**。

### 2.4 v6 MetaConsumer（真实闭环）
```
runtime/engine.py:1217-1219  every 5 turns: advice = meta_consumer.consume(trace_v3, turn_counter)
runtime/engine.py:1242       Mind: learn from trace, profile, MetaConsumer warnings
v4/cognitive/mind.py:76-78   拉 MetaConsumer 输出
v4/cognitive/mind_mistakes.py:27  从 MetaConsumer warnings 学习
v4/cognitive/quality_scorer.py     用 MetaConsumer warnings 做 Epistemic Detection Rate
```
→ 这是目前**唯一收口的元认知学习闭环**，但依赖 `_meta_consumer` 与 `_trace_v3`
（ExecutionTraceV3）均需在 runtime/engine 初始化处核实是否真的创建（第二轮）。

### 2.5 MetacognitiveTriggerEngine（孤儿）
```
observability/trigger_wiring.py:6-33  wire_trigger_to_engine / wire_trigger_to_compressor
```
→ 仅有 wiring 函数，**无任何生产模块调用 wiring**（需在第二轮确认是否全库孤儿）。

---

## 三、测试现状

| 测试文件 | 结果 | 说明 |
|---|:--:|---|
| event/tests/test_subscribers.py:63 | ✅ 8 passed | 仅测 MetaSubscriber 基本行为 |
| v4/cognitive/tests/test_cognitive.py | ⏳ 未单跑 | 覆盖 mind/meta_consumer 系列 |
| runtime/tests/test_behavior_causal_integration.py | ✅ 14 passed | 涉及 engine 集成，MetaConsumer 间接覆盖 |

**缺口:** 无 MetaCognition 主类（submit/scan/retrospect/self_audit）的直接测试；
无 FeedbackBridge 生产路径集成测试；无 MetacognitiveTriggerEngine 测试。

---

## 四、实锤线索（第一轮）

1. **v4 MetaCognition = 设计主体的「零调用方」**——四职责（协同/学习/裁决/复盘）
   仅实现为 CLI 可调 API，未进入生产流水线（A10 公理对应缺口）。
2. **两套 EventBus 并存**: `events/event_bus.py`（meta_subscriber 引用）vs
   `event/event_bus.py`（handlers/closure 引用）——需确认是否同构双份（第二轮）。
3. **MetaSubscriber 使用 `events/` 旧路径**，而 StateMachine/handlers 用 `event/` 新路径
   —— 跨代演进分裂的同型问题（与 PCR/行为链一致）。
4. **MetaReviewer（cognitive_loop.py:85）无生产消费证据**——`run_cognitive_loop`
   仅在 v4/cognitive/runtime.py:18 定义，调用方待查。
5. **MetaConsumer 依赖 `_trace_v3`**——ExecutionTraceV3 在 engine.py:179-180 声明
   "v6 State evolution tracking"，是否实例化需验证（关联规划/执行层审计）。

---

## 五、待第二轮确认清单

- [ ] 设计文档: `BUSINESS_CHAIN_09_METACOGNITION.md` + `DESIGN_METACOGNITION_RUNTIME.md` 精读
- [ ] `meta/feedback_bridge.py` 数据源（谁 post_decision）与 agent_native 消费闭环
- [ ] runtime/engine 中 `_meta_consumer`/`_trace_v3` 的真实初始化
- [ ] `events/` vs `event/` 双 EventBus 是否同构、谁在用
- [ ] MetaCognition v4 设计四职责 vs 实现的完整对照
- [ ] MetaReviewer / CognitiveLoop / MetacognitiveTriggerEngine 生产接线核查
- [ ] 元认知 ↔ 行为链（A10 协同/学习/裁决/复盘）接口现状

---

## 六、勘误（深层次复核后）

> 见 `docs/only/meta/DEEP_AUDIT_20260803.md`。修正 2 处:
> ① v4 MetaCognition 并非零生产调用——CLI 路径下 StateMachine META handler 会调用
> （但 retrospect 参数恒 "general"，输入断裂）；② MetaSubscriber 有实例但**从未订阅**
> （factory 传 bus=None + cli 只赋属性不重订阅）。实锤 4 个静默失效（M1-M4）。
