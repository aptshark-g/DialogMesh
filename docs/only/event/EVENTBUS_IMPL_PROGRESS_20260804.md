# M5 EventBus 生命周期（G2）— 施工记录（2026-08-04）

> 定位: 阶段 A 后端模块化施工 M5。G2（EventBus 背压方向）全部 P1/P2 项完成。
> 依据: `docs/only/G2_EVENTBUS_LIFECYCLE_20260804.md`（GAP-1~3 定案）。
> 状态: ✅ 完成（新增测试 12/12 + 核心回归 110/110 + 压测 3 项全绿）。

---

## 一、交付内容（G2-P1 ~ P6）

### G2-P1 event_consumer 表 + per-subscriber 水位线（P1）✅
```
api_event_log.py:
  + event_consumer(consumer_id PK, last_seq, updated_at) 表
  + register_consumer / unregister_consumer / consumer_watermark / consumers
  + event_seq(event_id)（rowid 单调递增 = 全局 seq）
  + ack_consumer(consumer_id, seq)（单调前进，不回退）
  + replay_for_consumer(consumer_id, limit)（增量拉取 seq > 水位线）
  + all_registered_consumed(seq)（所有注册消费者均已越过；空消费者集退化为 legacy）
  + prunable_events(limit, retention_sec)（全消费 + 超期候选；有消费者按 min 水位线，
    无消费者退化为 consumed=1 legacy 判据）
  + ack_event 保留为单消费者快捷路径（兼容 association_service / CLI event_cmd）
```

### G2-P2 semantic_value 锚点数计算（P1）✅
```
api_event_log.py:
  + event_log.semantic_value 列（老库 open() 时 ALTER TABLE 自动迁移）
  + compute_semantic_value(payload) 静态方法: cross_ref/cross_refs/references/
    anchors/refs 条目数 + l2_summary 存在性（+1）—— 不 LLM 打分（GAP-2 定案）
  + put_event 写入时计算并落列
```

### G2-P3 温减枝接入（P1）✅
```
event/log_lifecycle.py（新增）:
  EventLogLifecycle.prune_warm(limit):
    候选 = prunable_events（全消费 + 超 retention）
    importance 三信号 = 0.4*recency + 0.3*activation + 0.3*semantic（0..1）
    低于阈值 → 结构降级 C（保留锚点 cross_ref/l2_summary + 顶层键摘要，
    丢弃非锚点细节）
```

### G2-P4 冷摘要化（P2）✅
```
EventLogLifecycle.summarize_cold(limit):
  更老（cold_age = retention*3）+ 有锚点 + 未减枝 → 语义摘要
  结构降级 C 先做（默认）；llm_summarizer 回调可选（LLM 摘要 B 增强，
  失败自动降级结构摘要）
```

### G2-P5 A24 锚点完整性校验（P2）✅
```
EventLogLifecycle.anchor_integrity(original, summary):
  摘要锚点集 ⊇ 原文锚点集（cross_ref 条目 + l2_summary）
  不完整 → 跳过减枝/摘要（保原文，A24 可逆推不违反）
  无锚点 → 视为可降级（结构降级不引入歧义）
```

### G2-P6 旧 events/event_bus.py 归档（P2）✅
```
core/agent/events/event_bus.py（旧 deque 满则丢弃）→
  un_use/event_bus_archived/event_bus_v1_ringbuffer.py
消费方迁移到 v2（core/agent/event/event_bus.py）:
  cli/registry.py:265        event_bus 注册指向 v2
  runtime/engine.py _publish 优先 publish_sync（新 bus 同步桥）
  event/subscribers.py       wire_subscribers 用 subscribe_sync + Event 解包
  meta/meta_subscriber.py    换 v2 主题订阅 + publish_sync（EventType 枚举废弃）
  tests/test_integration.py  导入与发布改 v2
```

## 二、EventBus v2 升级（G2 归一底座）
```
core/agent/event/event_bus.py:
  修复 _deliver 重复入队 bug（原实现消息入队两次 → 双倍投递）
  双模: 保留 async API（agent_native/permissions/closure 的 ensure_future 用法）
        + 新增后台事件循环线程 + publish_sync/subscribe_sync/request_sync/
        drain_sync（CLI 引擎同步路径 / wire_subscribers / meta_subscriber）
  慢消费者 NEVER drop: 溢出计数 overflow（stats 可观测），EventLog replay 兜底
  cb 型订阅回调即投递（不入队，drain 不等待）；无 cb 入队供 next_msg 消费
```

## 三、验证

### 新增测试（tests/test_event_log_lifecycle.py 12/12）
```
① test_multiconsumer_watermark_protects_unconsumed    B 未消费 → 不减枝
① test_multiconsumer_partial_ack_one_event            部分 ack → 按 min 水位线减枝
② test_fresh_event_not_pruned                         未超期 → 不减枝
② test_legacy_consumed_fallback                       无消费者 → legacy consumed 判据
③ test_semantic_value_observable                      semantic_value 可观测无 LLM
④ test_anchor_integrity_keeps_anchors                 摘要后锚点保留、细节降级
④ test_anchor_incomplete_skips_prune                  锚点不完整 → 跳过保原文
⑤ test_old_event_bus_archived                         旧 bus 在 un_use
⑤ test_registry_points_to_v2_bus                      registry 指向 v2
⑥ test_never_drop_sync_and_async                      同步桥 + 异步零丢
   test_run_gc_end_to_end                              温减枝 + 冷摘要一次跑通
   test_association_service_still_replays              关联链 legacy 路径回归
```

### 回归（核心集 110/110）
```
tests: event_log_lifecycle 12 + association_service 21 + association_funnel 2 +
  l1_5 1 + l2_5 3 + l3 1 + integration 1
core/agent: event/tests/test_subscribers 8 + test_statemachine_m4 10 +
  api/tests/test_viz_edit 29 + behavior/tests 8 + runtime/tests 11
= 110 passed（另 12 deselected = 关联链 stress 常跳过项）
```

### 压测（3 项全绿）
```
S1 同步桥 5000 事件: 1056ms（≈4.7k/s），delivered=5000 零丢
S2 慢消费者 max_pending=8 + 2000 事件: 全投递，overflow=0（回调型直接投递）
S3 多消费者水位线: A 全消费 / B 到 seq[49] → 精确减枝 50，后半段保原文
```

### 已知预存在（非 M5 引入，回归记录）
```
cli/tests 1/28: test_discourse_write_ops（D-14，归对话树模块）
v4/cognitive/test_linkage_quality_v2::test_all: engine() 返回对象无 .start()
  （旧接口损坏测试，预存在）
全量收集 18 个 ERROR: v3_legacy / v3_2 缺失模块等历史遗留（预存在）
state.json PermissionError: 环境差异（3.13/.venv 与 3.9/anaconda3），非致命
```

## 四、改动文件清单
```
core/agent/api/api_event_log.py            G2-P1/P2（水位线 + semantic_value + 迁移）
core/agent/event/log_lifecycle.py          新增（G2-P3/P4/P5 生命周期层）
core/agent/event/event_bus.py              v2 双模 + _deliver 修复
core/agent/cli/registry.py                  event_bus → v2
core/agent/runtime/engine.py                _publish 用 publish_sync
core/agent/event/subscribers.py             wire_subscribers 用 subscribe_sync
core/agent/meta/meta_subscriber.py          迁移 v2 API
tests/test_integration.py                   导入/发布改 v2
tests/test_event_log_lifecycle.py           新增（12 测试）
un_use/event_bus_archived/event_bus_v1_ringbuffer.py   旧 bus 归档
```

## 五、遗留（不阻塞）
```
event_cmd.py / 其他 CLI 仍用 legacy replay_unconsumed/ack_event —— 保留为快捷路径，
  与 G2 "ack_event 保留单消费者快捷路径" 一致
EventLogLifecycle 尚未接入引擎周期 GC 定时器（M6 存储接线时一并接线或独立定时任务）
```
