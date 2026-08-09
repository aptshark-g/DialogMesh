# 规划模块施工记录 — PL-1/2/3（models 恢复 / skill_layer 壳清理 / 三套归一）

> 日期: 2026-08-05 | 批次: 规划（模块级补全第八批）
> 审计依据: `docs/only/planner/AUDIT_ENTRY_20260803.md` + `DEEP_AUDIT_20260803.md`
> + `DESIGN_FULL_READ_20260803.md`
> 状态: ✅ 完成（planner 27/27 全绿 + import 21/21 + 跨模块回归无新破坏）

---

## 一、根因（审计实锤 → 本次修复）

`planner/models.py` 曾被改写为 v4 skill_layer 重导出壳（0.7KB，try/except 静默
fallback 到 5 个极薄 dataclass），而 `v4/skill_layer/__init__.py` 又引用 3 个
不存在的模块（skill_pool / evaluation_engine / executor_map）→ 包级
ModuleNotFoundError → planner/models.py 落入 fallback → 34 个规划模型全丢 →
planner 包 7 个核心模块 import 全炸 → 20/27 测试失败 + orchestrator v3 路径
连带炸 + runtime `_planner` 恒 None（延迟 import 被吞，静默降级）。

时间线: 07-21 曾 70% 有效实现 → 08-xx v4 skill_layer 迁移覆盖 models.py →
整体回归（与 PCR/行为链同型「多代演进→分裂」）。

---

## 二、PL-1: planner/models.py 完整恢复

- **恢复源**: git `d993553`（最后完整版 1014 行，已含 v3_0→v3_legacy 导入修正）。
- **恢复方式**: `git show d993553:core/agent/planner/models.py` 字节级写回
  （Python subprocess，避免 PowerShell GBK 乱码；git restore 因 index.lock
  权限失败，改用 git show）。
- **内核唯一化**: 在恢复的 34 个规划模型后追加 v4 skill_layer 的 5 个 skill
  模型定义（ActionNode / CapabilityBlueprint / SkillBelief / SkillCandidate /
  Skill）→ `planner/models.py` 成为规划模型唯一内核（39 个模型）。
- **消除静默降级**: 删除原 try/except fallback 壳（拒绝静默，符合审计 P2）。

## 三、PL-2: v4/skill_layer 壳清理（门面化）

```
core/agent/v4/skill_layer/__init__.py   → 门面，全部 re-export 自 core.agent.planner
core/agent/v4/skill_layer/models.py     → 门面，re-export 自 planner.models
```

- 原 __init__ 引用 3 个不存在的模块 → 改为从 planner（唯一内核）re-export
  SkillPool / EvaluationEngine / EXECUTOR_MAP / resolve_executor + 5 模型。
- 保留导入路径兼容（cli/health.py probe 仍可 import
  `core.agent.v4.skill_layer.models`），零并行实现。
- 符合「一内核多门面」红线（同 v3_0/planning 门面模式）。

## 四、PL-3: 三套规划归一验证

| 套 | 路径 | 定位 | 验证 |
|---|---|---|---|
| 内核 | `core/agent/planner/`（models + 20 模块）| 唯一实现 | 21/21 import OK |
| 门面 | `core/agent/v3_0/planning/__init__.py` | re-export planner | import OK |
| 门面 | `core/agent/v4/skill_layer/` | re-export planner | import OK |

- runtime `_planner` 恒 None 已由执行层 M4 X8 按设计处理（handle_planning 懒
  初始化 LLMPlanner 轻路径，event/handlers.py 已接线）——本轮不重复接线。
- orchestrator v3 路径（import PlanningSkill + PlanResult）恢复可用。

---

## 五、测试与回归

### 5.1 planner 测试
```
core/agent/planner/tests/  27/27 passed（此前 20 failed, 7 passed）
  test_models / test_skill_pool / test_distillation / test_evaluation /
  test_external / test_executor 全绿
```

### 5.2 import 探针（21/21）
```
planner 18 模块 + v3_0.planning + v4.skill_layer + v4.skill_layer.models 全 OK
orchestrator.orchestrator / bootstrap / cli.health / engineering_bridges 全 OK
core.agent.api.v6_app / runtime.engine / v3_0.planning 全 OK
```

### 5.3 跨模块回归（无新破坏）
```
planner 27/27 | CLI 28/28 | topic_tree+meta+context+intent 121/121
event 63/64（唯一失败 = 预存在 e2e _persist_state，交接已记）
runtime 14/14 | causal+behavior 37/37
```

### 5.4 顺带修复（测试监控，非规划模块）
- `event/pluggable.py` NATS connect 加硬性总超时（asyncio.wait_for 5s +
  connect_timeout=2 + max_reconnect_attempts=0）：本地无 NATS 服务时
  connect 默认会内部重试多次，代理/防火墙拦截 SYN 时无限挂起 → 整个 event
  套件挂死。修复后 test_pluggable 2.8s 内 4/4 通过。
- 补 `import asyncio`（原文件用 asyncio 却未显式导入，靠 import 链巧合可用）。

---

## 六、预存在失败（非本批回归，已核实）

| 失败 | 根因 | 归属 |
|---|---|---|
| PCR `test_integration.py` 8 项 | 旧 IntentParser 弃用 shim（`a984c79`）置 None，测试仍调 `IntentParser()` | 意图批次遗留 |
| event `test_e2e_full_pipeline_mock` | `_persist_state` 消失（engine 重构）| event/持久化批次 |
| `test_linkage_quality_v2` | engine.start() 移除 + 硬编码 key + 真 LLM | LLM 批次 |
| DPO 2 项 flaky | pytest-asyncio 顺序依赖 | 测试基建 |

## 七、记录不施工（边界纪律）

- 归档测试 `un_use/tests_archived/planner/test_planning.py`（1197 行、~40 测试）
  复活 = 可选增强。含大量 `@pytest.mark.asyncio` + 嵌套 asyncio 等待，试跑
  挂起（事件循环问题），需逐个适配，超出本批范围。建议后续批处理。
- 设计文档的 PrimitiveLibrary 17 原语 / MixedPlanningEngine / ToolBindingEngine
  等 v1.5 正交分层设计整体未落地 —— 属设计层缺口，记录不施工。

---

## 八、改动文件
```
M core/agent/planner/models.py           完整恢复（1014→1075 行，含 skill 模型）
M core/agent/v4/skill_layer/__init__.py  门面化（planner re-export）
M core/agent/v4/skill_layer/models.py    门面化（planner re-export）
M core/agent/event/pluggable.py          NATS connect 硬超时 + import asyncio
```
