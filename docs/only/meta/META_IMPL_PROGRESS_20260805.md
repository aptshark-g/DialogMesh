# 元认知 M5/M8/M9 施工记录（2026-08-05）

> 批次: 模块级补全第七批（元认知）。入口: `docs/only/meta/DEEP_AUDIT_20260803.md`
> （M1-M9 实锤清单）+ `docs/only/meta/DESIGN_FULL_READ_20260803.md`（设计全貌）。
> 对象: `core/agent/meta/` + `v4/cognitive/metacognition.py` + `v4/cognitive/meta_consumer.py`
> + `runtime/engine.py`（meta 段）+ `event/handlers.py`（META handler）。
> 原则: 一内核多门面（红线 7）/ A17 记录不删 / 边界纪律（记录不施工）。

---

## 一、完成态（诚实汇报）

| 项 | 级别 | 内容 | 状态 |
|---|---|---|---|
| M5-M1 | P0 | FeedbackBridge post_decision 零调用方 → MetaSubscriber 写回（冷→热三层反馈打通） | ✅ |
| M5-M2 | P0 | MetaSubscriber 实例存在从未订阅 → 新增显式 subscribe() + cli/engine 延迟接线重订阅 | ✅ |
| M5-M3 | P0 | `_meta_consumer`/`_trace_v3` 恒 None → engine 懒初始化 + on_event_sm 每 5 轮 consume | ✅ |
| M4 附带 | P1 | handle_meta retrospect 参数恒 general → 多源取真实意图；stats 覆盖 reviewed 标志修复 | ✅ |
| M8 | P2 | 三套元认知归一 → v4 唯一内核 + MetaConsumer 组件化（consume_trace）+ v3 Adapter 归档 | ✅ |
| M9 | P2 | MetaReviewer/cognitive_loop 归档（零生产消费）；TriggerEngine 保留为组件资产 | ✅ |

**测试**: meta 16/16（新增）；event 63/64（唯一失败 = 预存在 e2e `_persist_state`）；
v4/cognitive 32/33（唯一失败 = 预存在 test_linkage_quality_v2 需 `engine.start()` + 真 LLM）；
runtime 14/14；CLI 28/28。编译探针 12 文件 OK；归档后残留引用 NONE。

---

## 二、逐项明细

### M5-M1 FeedbackBridge 写回（P0）
```
根因: post_decision 全库零调用方（rg 实证）→ FeedbackBridge 恒空，
  agent_native 三层读（consume/consume_belief/consume_drift）永远取不到数据。
修复: MetaSubscriber._review_and_publish 构造 MetaDecision 并 post_decision:
  - profile_drift>0.3 → urgent_correction（recalibrate_profile）
  - behavior_count>=5 → belief_update（review_patterns）
  - 其余每 5 轮 → parameter_shift（periodic_review）
  cli/engine.py wire 块创建共享 FeedbackBridge（engine._feedback_bridge）并注入 meta_subscriber。
验证: 3 项测试（drift 写回 / behavior 写回 / 无 bridge 安全）。
```

### M5-M2 MetaSubscriber 订阅接线（P0）
```
根因: registry _meta_factory 传 bus=None（"Don't subscribe yet"）→ __init__ 跳过订阅；
  cli/engine.py wire 块只赋 obj._bus 不重订阅 → 订阅列表恒空 → _on_event 永不触发。
修复: MetaSubscriber 新增显式 subscribe()（幂等，subscribe_sync 遍历 SUBSCRIBED_KINDS）；
  __init__ 有 bus 即自动订阅（保持兼容）；cli/engine.py 延迟接线后调用 obj.subscribe()。
验证: 3 项测试（延迟订阅 / 构造即订阅 / 事件驱动 _on_event）。
```

### M5-M3 engine 元认知运行时（P0）
```
根因: runtime/engine.py 中 _trace_v3 声明 None 后无赋值点；_meta_consumer 根本不存在
  → v6 MetaConsumer 每 5 轮闭环从未执行（设计 §5.2 勘误: 类完整、引擎未接线）。
修复:
  - engine.__init__ 声明 _meta_consumer / _feedback_bridge
  - _init_meta_runtime(): 懒创建 ExecutionTraceV3 + MetaConsumer（非致命）
  - on_event_sm 每 5 轮（_turn_counter % 5 == 0）→ 初始化 + _run_meta_consume()
  - _run_meta_consume(): consume(trace) → adjust 时提交审核队列（优先走
    MetaCognition.consume_trace，否则兜底 submit）
  - cli/engine.py start_engine 调用 _init_meta_runtime()
验证: 3 项测试（组件创建 / consume 提交 ReviewItem / 每 5 轮钩子触发）。
```

### M4 附带修复（P1）
```
① retrospect 参数: ctx intent 恒空 → 恒 "general"。改为多源提取:
   intent.category → intent.intent_category → pcr.intent → "general"。
② 真实缺陷: handler 的 results.update(stats()) 把 "reviewed" 布尔标志覆盖成
   stats() 的计数（reviewed: 0）→ 消费方（_feed_inertia_evidence 等）判假。
   修复: 标志位统一在 stats 合并后最后写入。
验证: M4 测试（META handler 在 intent 上下文 reviewed=True）。
```

### M8 三套归一（P2）
```
拍板（对齐"一内核多门面"）:
  内核 = v4 MetaCognition（v4/cognitive/metacognition.py）——设计主体
        （审核队列/复盘/双模式决策/自我复盘）
  学习闭环接入 = v6 MetaConsumer（v4/cognitive/meta_consumer.py）——
        作为内核组件，不再独立成"第三套"
  写回通道 = meta/feedback_bridge.py（保留，桥接层）
  冷路径触发 = meta/meta_subscriber.py（保留，事件订阅）
  归档 = 根 metacognition.py（v3 Adapter + Scheduler，零生产调用）
施工:
  - MetaCognition.__init__ 增加 meta_consumer 参数；新增 consume_trace(trace, turn):
    MetaConsumer 建议 → 转 ReviewItem 入审核队列（REJECT 高优先级）
  - 根 metacognition.py → v4/un_use/metacognition_v3.py（A17 保留）
  - subsystem_registrations "meta_cognition" 注册串 → v4 路径
验证: 4 项测试（consume_trace 入队 / 懒创建 / v3 归档存在 / registry 指向 v4）。
```

### M9 MetaReviewer/TriggerEngine 去留（P2）
```
拍板:
  - event/cognitive_loop.py（BehaviorLearner + MetaReviewer + CognitiveLoop +
    wire_cognitive_loop）全文件零生产调用、零测试引用 → 归档
    v4/un_use/cognitive_loop_v1.py。MetaReviewer 与 v4 内核职责重叠
    （review_chains API 在 v4 不存在，hasattr 保护下恒空转）；BehaviorLearner
    已被行为链 DPO 批次覆盖。v4/cognitive/runtime.run_cognitive_loop 是不同
    模块（活路径），不受影响。
  - observability/metacognitive_trigger.py + trigger_wiring.py: 保留为组件资产
    （设计 §6 双模式触发价值），标注待接线，记录不施工。
验证: 2 项测试（cognitive_loop 归档 / TriggerEngine 组件保留）。
```

---

## 三、改动文件清单（未提交，按惯例压缩前不提交）

```
core/agent/meta/meta_subscriber.py          M5-M1/M5-M2（post_decision + subscribe）
core/agent/meta/tests/__init__.py           新增
core/agent/meta/tests/test_meta_wiring.py   新增 16 项
core/agent/runtime/engine.py                M5-M3（_init_meta_runtime/_run_meta_consume/5轮钩子）
core/agent/cli/engine.py                    接线（subscribe + FeedbackBridge + _init_meta_runtime）
core/agent/event/handlers.py                M4（retrospect 真实意图 + reviewed 标志修复）
core/agent/v4/cognitive/metacognition.py    M8（meta_consumer 组件 + consume_trace）
core/agent/cli/subsystem_registrations.py   M8（注册串 → v4）
core/agent/metacognition.py                 M8 删除（归档 v4/un_use/metacognition_v3.py）
core/agent/event/cognitive_loop.py          M9 删除（归档 v4/un_use/cognitive_loop_v1.py）
core/agent/v4/un_use/metacognition_v3.py    归档（A17）
core/agent/v4/un_use/cognitive_loop_v1.py   归档（A17）
```

---

## 四、遗留记录（记录不施工，边界纪律）

| # | 内容 | 归属 |
|---|---|---|
| L1 | `test_linkage_quality_v2` 预存在失败: 调已移除的 `engine.start()` + 硬编码 LLM key；现 `_meta_consumer`/`_trace_v3` 已就位，仅剩 start()/LLM 阻塞 | LLM 全量测试批次 |
| L2 | e2e `_persist_state` 预存在（主题树批次 L5） | event/持久化批次 |
| L3 | `MetaSubscriber` 产出仅进 FeedbackBridge + 审核队列；设计"主动拉取扫描 5 类"仍为 scan() 占位 | 元认知深化/冷启动批次 |
| L4 | `MetaCognition.consume_trace` 建议未联动 `ContextualStrategy`/`strategy_engine` 权重更新（MetaConsumer 内部有，engine 未注入 strategy） | 规划/参数批次 |
| L5 | `ExecutionTraceV3` 只初始化未喂快照（states/transitions 空 → meta_analyze 空）；trace 记录归属执行层 | 执行层批次 |
| L6 | `GlobalVersionControl` 仍只被 MetaCognition 消费，未成为各链统一版本底座（A17 一致性） | 全局深化 |
| L7 | TriggerEngine 保留组件但未挂载（M9 拍板记录不施工） | 可观测性/工程链批次 |

---

## 五、验证命令

```
python -m pytest core/agent/meta/tests -q ...        # 16/16（新增）
python -m pytest core/agent/event/tests -q ...       # 63/64（e2e 预存在 L2）
python -m pytest core/agent/v4/cognitive/tests -q ... # 32/33（L1 预存在）
python -m pytest core/agent/runtime/tests -q ...      # 14/14
python -m pytest core/agent/cli/tests -q ...          # 28/28
编译探针 12 文件 OK + 归档残留引用 NONE
```
