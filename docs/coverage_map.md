# Coverage Map: on_event() vs on_event_sm()

> 审计日期: 2026-07-30
> 原则: 只记录可验证的事实,不假设

## on_event() 功能清单 (~3500 行, engine.py:667-1382)

| # | 功能 | on_event() 代码 | on_event_sm() 覆盖 | 状态 |
|:--|------|:---------------|:-------------------|:----:|
| 1 | GlobalDecider tick + evolve | L678-681 | Decider 在 factory 创建,StateMachine 不直接管 | ⚠️ |
| 2 | Event buffer + stats | L683-686 | _tracer.record() | ✅ |
| 3 | ConversationTracker.add_turn | L694 | 无——DiscourseTree 内部用,但未显式调用 | ❌ |
| 4 | DiscourseTree.feed (第1次) | L696-698 | handle_discourse → _discourse_tree.feed() | ✅ |
| 5 | Granularity regulation | L701-705 | engine 级别调用,非 handler | ⚠️ |
| 6 | Behavior edge recording | L707-723 | handle_behavior → _behavior_graph_adapter.record_event() | ✅ |
| 7 | EventLog.record_event | L726-731 | handle_persist → EventLog | ✅ |
| 8 | PathStateMachine transition | L734-735 | 无——start() 专有,从未调用 | ❌ |
| 9 | Adapter chain timed_execute | L742-767 | 无——StateMachine 替代了 adapter 链 | ⚠️ |
| 10 | ObservationPool.put | L756-761 | 无——obs 有独立 CLI | ❌ |
| 11 | TopicTree.touch | L770-775 | 无——可加到 handle_discourse | ❌ |
| 12 | DiscourseTree.feed (第2次) | L777-787 | handle_discourse 覆盖 | ✅ |
| 13 | PCR routing | L790-820 | handle_pcr → pcr_router.route() | ✅ |
| 14 | Intent parsing | L822-860 | handle_intent → parser.parse() | ✅ |
| 15 | _feed_trackb | L869 | 无——行为追踪 record_trackb | ❌ |
| 16 | Profile update | L870-920 | handle_profile → ocean_analyst.analyze() | ✅ |
| 17 | _feed_extractions_to_substrate | L930 | 无——关系提取 | ❌ |
| 18 | Cache invalidation | L933-940 | PERSIST handler → HotStore.set() | ✅ |

## 覆盖统计

| 状态 | 数量 | 说明 |
|:-----|:----:|------|
| ✅ 完全覆盖 | 8 | PCR, Intent, Discourse, Behavior, Meta, Profile, Persist, Cache |
| ⚠️ 间接覆盖 | 3 | Decider (factory 创建), Granularity (engine 调用), Adapters (StateMachine 替代) |
| ❌ 未覆盖 | 6 | ConvTracker, PathStateMachine, ObsPool, TopicTree, TrackB, Extractions |

## 未覆盖项的修复策略

| # | 功能 | 修复方案 | 风险 |
|:--|------|---------|:----:|
| 3 | ConversationTracker | engine.on_event_sm() 前调 add_turn() | 低——与 DiscourseTree 共享数据 |
| 5 | Granularity regulation | engine.on_event_sm() 后调 regulate() | 低——已存在于 engine |
| 8 | PathStateMachine | **不上覆盖**——start从未调用,此功能已死 | 无 |
| 10 | ObservationPool.put | **不上覆盖**——StateMachine 不直接操作 pool | 无 |
| 11 | TopicTree.touch | 加到 handle_discourse | 低 |
| 15 | _feed_trackb | 加到 handle_behavior | 低 |
| 17 | _feed_extractions_to_substrate | 加到 handle_assoc | 低 |

## 需要补的缺口 (实际工作量)

1. **ConversationTracker** → engine.on_event_sm() 加 3 行
2. **Granularity regulation** → 已存在,仅需验证
3. **TopicTree.touch** → handlers.py 加 5 行
4. **_feed_trackb** → handlers.py 加 5 行
5. **Substrate extractions** → handlers.py 加 5 行

**总代码量: ~20 行新增**

## 不需要补的

- PathStateMachine: start() 从未调用,start() 本身要被归档
- ObservationPool: 独立子系统,有自己的 CLI
- Adapter chain: StateMachine 已完全替代
