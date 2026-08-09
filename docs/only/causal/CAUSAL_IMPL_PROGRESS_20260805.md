# causal C1-C5 批次施工记录 — 2026-08-05

> 依据：`GLOBAL_PENDING_DECISIONS_20260803.md` §五（C 系列 5 项）+ 审计
> `docs/only/causal/CAUSAL_COGNITION_ASSEMBLY_DISCOURSE_AUDIT_20260803.md`。
> 状态：**causal C1-C5 批次完成**。

---

## 一、施工内容（按 C 项）

| # | 项 | 施工 | 验证 |
|---|---|---|---|
| C1 | CausalPlanner 零实例化（P1）| engine 新增 `_init_causal_planner`（懒挂载，graph 复用 `_behavior_graph_adapter.graph` 一内核）+ `_run_behavior_brain` 同步 `record_step` 喂因果链 + `_trigger_causal_slow_path`（process_chain → structural prior）+ `on_session_end` 触发 slow_path | test_causal_wiring TestC1 5 项 + 冒烟（3 steps / slow_path 链短正确不触发 / 12 步触发）✅ |
| C2 | CognitionHub.ingest_relations 零调用（P1）| `_on_association_discovered` 喂 relations（payload relations/l3 字段）→ hub 惰性创建 → `ingest_relations` + `converge`；`converge` 消费即清空（缓冲语义正确）| TestC2 3 项 + 冒烟 ✅ |
| C3 | UnifiedContext DiscourseManager 半边注释（P2）| **裁决**：v6 minimal loop 不启用 v3 DiscourseManager（依赖链 UserEngine/TaskEngine/Coordinator 重 + 与 B 内核功能重叠）；discourse 职责由 `discourse_block_tree/`（R6 D3 内核）承担；注释更新明确裁决 + 激活前提（红线 7）| 代码注释 ✅ |
| C4 | discourse/ 包缺 DiscourseBlockTree 符号（P2）| `discourse/__init__.py` re-export `DiscourseBlockTree` → `discourse_block_tree.manager.DiscourseBlockTreeManager`（inspect_v3_cmd 断链修复）| TestC4 2 项（可导入 + 指向真实实现）✅ |
| C5 | _behavior_brain/_behavior_graph_adapter 零赋值（P3）| **行为链批次已修**：`_init_behavior_brain` 挂载 + cli/engine 挂载 adapter；本批复核 | TestC5 核对 ✅ |

---

## 二、改动文件清单

```
M core/agent/runtime/engine.py        C1 _init_causal_planner/_trigger_causal_slow_path/
                                     record_step 接线 + on_session_end slow_path
                                     C2 _on_association_discovered 喂 CognitionHub
M core/agent/discourse/__init__.py    C4 DiscourseBlockTree re-export（新增）
M core/agent/assembly/unified_context.py  C3 DiscourseManager 裁决注释
A core/agent/causal/tests/test_causal_wiring.py  C1/C2/C4/C5 11 项
```

---

## 三、验证数字

```
causal 批次新测试:      causal/tests/test_causal_wiring.py 11/11
跨模块回归:             behavior + statemachine + discourse + profile 99/99
端到端冒烟（UTF-8 文件）:
  C1 planner mounted=True / steps=3 / slow_path available=True, triggered=False(链短)
  C2 ingest buffer=1 → converge 消费清空=0 / engine hub created=True
  C4 DiscourseBlockTree importable=True
```

---

## 四、遗留（记录不施工，边界纪律）

1. C3 属裁决而非激活：v3 DiscourseManager 若要启用需先解决依赖链 + 双内核归一。
2. C1 slow_path 目前只在 `on_session_end` 触发一次；运行中链长达标的实时触发
   归执行层批次（与 StateMachine PERSIST/checkpoint 协同，避免越界）。
3. CognitionHub 的 `converge` 结果目前只内部消费，未写白盒快照——补白盒
   `get_status` 暴露归元认知批次（Meta 学习闭环零调用方一并处理）。

---

*本文件是 causal 批次施工记录；交接入口见 `STATE_HANDOFF_IMPLEMENTATION_20260804.md`。*
