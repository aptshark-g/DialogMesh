# G2 EventBus 生命周期层 — GAP-1~3 细化定案（2026-08-04）

> 定位: G2（EventBus 背压方向）GAP-1~3 细化正式定案。
> 方向已拍（用户 2026-08-03）: 保留 NEVER drop + 生命周期层（热全量→温减枝→冷摘要）。
> 本文件 = GAP-1~3 机制细化 + 代码基础核实。
> 关联: B8-2 / I1-1（两套 EventBus 归一）/ A17（记录不可删）/ A2（摘要=缩放）/
> A24（可逆推）/ 关联链 A24 验收指标（已拍板）。
> 状态: ✅ 已拍板（2026-08-04）

---

## 一、方向（用户已拍，2026-08-03）

```
保留 core/agent/event/event_bus.py（NEVER drop）
新增 EventLog 生命周期层（三阶段）:
  阶段1 热事件: 全量保留（NEVER drop 不变）
  阶段2 温事件: 按 importance 减枝（ColdIndexer 机制）
  阶段3 冷事件: 语义摘要化（结构降级 C + LLM 摘要 B）
废弃 events/event_bus.py（旧 deque 满则丢弃）→ 归档
```

---

## 二、代码基础核实（全部实测）

### 2.1 GAP-1「已消费」确认机制 — 已有 70%，缺 per-subscriber 水位线
```
EventLog (api_event_log.py):
  SCHEMA: event_log(consumed INTEGER DEFAULT 0)
  ack_event(event_id)             — 标记已消费 ✅
  replay_unconsumed(limit)        — 只拉未消费（崩溃恢复）✅
  cleanup_old()                   — 只删 consumed=1 且超期 ✅
真实消费者接线: association_service.py:230 处理完 ack_event，
  崩溃从 replay_unconsumed 恢复 → NEVER drop + 慢消费者回放已落地

真缺陷: consumed 是全局单字段，非 per-subscriber
  消费者 A/B 订阅同一事件 → A 消费后 ack，B 未消费
  但事件已标记 consumed → 温减枝可能减掉 B 未看的事件
```

### 2.2 GAP-2 semantic_value 载体 — 已有 80%，缺"锚点数"字段
```
graph_tier_manager.py 已实现 H/W/C/A 四区迁移:
  HOT_MAX_NODES=999 / WARM_TO_COLD_IMPORTANCE=0.3 /
  WARM_TO_COLD_ACTIVATION=5 / HOT_TO_WARM_INACTIVE_ROUNDS=10
lsm_store.py graph_nodes 表已有:
  activation_count INTEGER DEFAULT 0 + importance REAL DEFAULT 0.5
缺: semantic_value 字段（语义价值）—— 不需要 LLM 打分（太贵），
  用可还原性代理: cross_ref 完整性 + l2_summary 存在性
```

### 2.3 GAP-3 A24 可逆推保真度 — 完全复用关联链已拍指标
```
关联链 Phase 0-5 已做 A24 可逆推验收（ASSOCIATION_IMPL_PROGRESS）:
  coverage 60-80% 目标 / coverage=1.0 → 过拟合拒绝 /
  coverage<40% → 没学到拒绝
EventBus 减枝复用同一套指标
```

---

## 三、GAP-1~3 细化（正式拍板）

```
GAP-1: consumed 升级为 per-subscriber 水位线
  新增表: event_consumer(consumer_id, last_seq)
  判据: 所有注册消费者 last_seq >= 事件 seq → 可减枝
  兼容: 现有 ack_event 保留为快捷路径（单消费者场景）

GAP-2: semantic_value = 摘要锚点数（不 LLM 打分）
  三信号: activation_count（已有）+ recency（已有）+
          semantic_value（新增 = 锚点数）
  锚点 = cross_ref + l2_summary 存在性
  锚点多 → 永不减枝原文；锚点少 → 允许摘要化/丢弃

GAP-3: A24 保真度复用关联链指标
  减枝前: 校验摘要锚点集 == 原文锚点集
  不完整 → 跳过减枝（保原文）
  完整   → 允许摘要化（结构降级 C 先做 + LLM 摘要 B 增强）
```

---

## 四、生命周期层三阶段（最终形态）

```
热:   全量保留（NEVER drop 不变）
温:   所有消费者已消费（per-subscriber 水位线）+ 超 retention
       → 按 importance 三信号减枝（锚点保留）
冷:   锚点完整 → 语义摘要化（结构降级 C → LLM 摘要 B）
      锚点不完整 → 跳过（保原文）
废弃: events/event_bus.py（旧 deque）→ un_use 归档
```

---

## 五、施工前置

```
G2-P1  event_consumer 表 + per-subscriber 水位线（ack 升级）P1
G2-P2  semantic_value 锚点数计算（cross_ref + l2_summary 存在性）P1
G2-P3  温减枝接入（importance 三信号 + 水位线判据）P1
G2-P4  冷摘要化（结构降级 C 先做 + LLM 摘要 B 增强）P2
G2-P5  A24 锚点完整性校验（减枝前）P2
G2-P6  events/event_bus.py 归档 un_use P2
```

## 六、验收标准

```
① 多消费者场景: B 未消费的事件不会被温减枝减掉
② 减枝只针对"所有消费者已消费 + 超期"的事件
③ semantic_value 锚点数可观测（无需 LLM 打分）
④ 摘要化后 coverage 60-80%（关联链同指标），锚点不完整则跳过
⑤ 旧 events/event_bus.py 已在 un_use
⑥ 慢消费者永不丢事件（NEVER drop 语义保持）
```

---

> 关联: B8-2 / I1-1（EventBus 归一）/ A17+A2+A24 / 关联链 A24 验收指标
