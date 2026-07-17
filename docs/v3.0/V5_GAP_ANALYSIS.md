# v5 实现差距分析

## 2026-07-17 核查

| v5 设计 | 当前实际 | 差距 | 需讨论 |
|---------|---------|------|--------|
| **Simulation 引擎** | ✅ 已实现, 接入 `on_event()` | — | 需测试端到端效果 |
| **`recent_topics()`** | ❌ 不存在, engine 引用了它 | 会崩溃 | P0 修复 |
| **认知轨迹(Cognitive Trace)** | ⚠️ `ExecutionTrace` 存在但太浅 | TraceStep 只记录 PERCEIVE/REASON/REFLECT, 未记录假设/冲突/关系激活 | 需重新设计 |
| **行为图→轨迹** | ❌ `core/agent/v4/graph/` 目录不存在 | 行为图已消失但未替换 | 确认状态 |
| **统一关系图** | ⚠️ `RelationSubstrate`(21方法) + `CausalPlanner`(独立) | 因果链是独立系统, 未作为 Relation 子类 | 合并方案? |
| **心智模型(Mental Model)** | ❌ 不存在 | 工作区销毁后无持久心智 | 设计优先 |
| **状态变迁追踪** | ❌ 只存 snapshot, 不存 delta | confidence 0.3→0.6→0.75 无法追溯 | 需 Trace 支持 |

## P0 问题

1. **`self._conversation_tracker.recent_topics(3)` 不存在** — simulation 引擎会崩溃
2. **行为图目录已删除但 engine 仍有引用** `BehaviorGraphAdapter` — 需清理或替换

## P1 问题

3. **ExecutionTrace 太浅** — 只能追 PERCEIVE/REASON/REFLECT, 不能追假设/冲突/关系
4. **关系图不统一** — `RelationSubstrate` + `CausalPlanner` + `ConceptGraph` 三套并行

## P2 问题

5. **心智模型不存在** — 设计中有但从未实现
6. **状态变迁未追踪** — TrackA/B 的变化历史不可回放
