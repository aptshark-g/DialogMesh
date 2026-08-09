# 规划（1.5）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/planner/`（20 源码文件）+ `core/agent/causal/planner.py` +
> 相关接线（orchestrator / runtime / engineering_bridges / v3_0 planning 门面）
> 结论先行: **planner 包是「实现最完整但最分裂」的模块之一** —— 测试 20 失败实锤
> 模型签名漂移（`SkillCandidate`/`Skill` 构造参数与测试不一致）；主类 `PlanningSkill`
> 在 orchestrator（v3 路径）真接线，但 runtime（v4/v6 路径）只用 `skill_registry` 轻量
> 注册表；`causal/planner.py`（CausalPlanner）在 runtime 真接线但**无 slow_path（D6 缺口）**。

---

## 一、文件清单与体量

### 1.1 `core/agent/planner/`（20 文件 + 6 测试）
| 文件 | 体量 | 定位 |
|---|--:|---|
| `planner.py` | 35.7KB | PlanningSkill 主类（混合/LLM/规则三模式）|
| `executor.py` | 26.0KB | TaskGraphExecutor（执行状态机 + checkpoint）|
| `skill_engine.py` | 23.9KB | PlanningSkillEngine（模式选择 + 失败分析）|
| `optimizer.py` | 19.1KB | TaskGraphOptimizer（去重/剪枝/折叠/拓扑）|
| `strategy_selector.py` | 18.3KB | StrategySelector（复杂度/置信度→策略评分）|
| `scheduler.py` | 14.0KB | ExecutionScheduler + ExecutionResult |
| `fallback.py` | 14.4KB | FallbackPlanner（降级链）|
| `skill_registry.py` | 13.8KB | SkillRegistry（技能注册表）|
| `distillation_engine.py` | 9.0KB | 技能蒸馏（从行为/知识聚类）|
| `decomposition.py` | 11.0KB | DecompositionEngine（任务分解）|
| `dependency_resolver.py` | 8.5KB | 依赖解析 |
| `agent_allocator.py` | 7.1KB | Agent 分配 |
| `skill_matcher.py` | 8.6KB | 技能匹配 |
| `external_adapter.py` | 4.2KB | 外部技能适配（harness/json/openapi）|
| `evaluation_engine.py` | 1.5KB | 技能评估 |
| `llm_planner.py` | 2.7KB | LLMPlanner（轻量）|
| `executor_map.py` | 1.8KB | 执行器映射 |
| `skill_pool.py` | 2.3KB | 技能池 |
| `models.py` | 0.7KB | **模型定义（测试漂移源）** |
| `__init__.py` | 0B | 空 |

### 1.2 `core/agent/causal/planner.py`（19.6KB）
CausalPlanner（行为链 IR 记录 + 链处理）+ CausalContextSource（上下文源适配）。

### 1.3 相关门面/桥接
- `core/agent/v3_0/planning/__init__.py`（v3 门面，重导出 planner 全套）
- `core/agent/orchestrator/bootstrap.py:42` + `orchestrator/orchestrator.py:66-67`（PlanningSkill 真接线）
- `core/agent/engineering_bridges.py:131`（LLMPlanner 桥接）

---

## 二、消费矩阵（全库 rg 实证）

### 2.1 PlanningSkill 主类（v3 orchestrator 真接线）
```
orchestrator/bootstrap.py:42          from core.agent.planner.planner import PlanningSkill
orchestrator/orchestrator.py:66-67    PlanningSkill + PlanResult
```
→ orchestrator（v3 编排）是唯一生产消费者；`runtime/engine.py` **未 import planner.py**。

### 2.2 runtime（v4/v6 路径）仅用轻量注册表
```
runtime/engine.py:842-867   if self._planner is not None and parse_result:
                            from core.agent.planner.skill_registry import SkillRegistry
                            self._planner.plan(...)
runtime/engine.py:847       SkillRegistry 延迟导入
```
→ `self._planner` 类型待查（可能是 v3 PlanningSkill 或 v4 新对象）——第二轮深读确认。

### 2.3 CausalPlanner（runtime 真接线）
```
runtime/engine.py:32         from core.agent.causal.planner import CausalPlanner, CausalContextSource
runtime/engine.py:152        self._causal_planner
runtime/engine.py:927-950    record_step + get_recent_chain + process_chain
runtime/engine.py:1167-1175  record_step（每轮）
```
→ **唯一活跃的「因果-规划」耦合**；`process_chain()` 每次调用 = 无 slow_path 的浅处理。

### 2.4 其他消费者
```
cli/inspect_cmd.py:143 / cli/export_cmd.py:34 / cli/search_cmd.py:33   SkillPool（CLI 工具）
engineering_bridges.py:131                                            LLMPlanner（桥接）
compiler/perspective_planner.py（13.2KB）                            PerspectivePlanner（规划视角，独立体系）
```

---

## 三、测试现状（实锤）

```
core/agent/planner/tests/   ⚠️ 20 failed, 7 passed
  test_skill_pool.py   6 failed   TypeError: __init__() got an unexpected keyword argument 'domain'/'blueprint'
  test_distillation.py 5 failed   （同上，SkillCandidate/Skill 构造漂移）
  test_evaluation.py   3 failed   （SkillBelief 构造漂移）
  test_external.py     5 failed   （ExternalSkillAdapter 签名漂移）
  test_models.py       2 failed   （SkillCandidate/Skill 模型字段漂移）
  test_executor.py     1 passed   （executor_map 可用）
  test_models.py       部分通过
```

**根因（第一轮定位）:** `models.py`（0.7KB）极薄，`SkillCandidate`/`Skill`/`SkillBelief`
字段与 `skill_pool.py`/`distillation_engine.py`/`evaluation_engine.py` 实际使用不一致
→ **测试写于旧模型签名，代码演进未同步**（与 PCR/行为链同型的「多代演进→分裂」）。

---

## 四、实锤线索（第一轮）

1. **planner 测试 20/27 失败** = 模块内模型契约断裂（先射箭后画靶的反面：测试陈旧）。
2. **两套规划体系并存**:
   - v3 编排式: `planner/` 全套（PlanningSkill → TaskGraphOptimizer → Executor → Scheduler）
   - v6 运行时式: `runtime/engine.py` 只挂 SkillRegistry + CausalPlanner（无完整规划图执行）
   - 另: `compiler/perspective_planner.py`（策略视角规划，独立第三套）
3. **CausalPlanner 无 slow_path（D6）**——`process_chain()` 是单次浅扫描，无分层回溯。
4. **SkillRegistry/SkillPool 有 CLI 消费但无生产流水线消费**（inspect/export/search 是运维工具）。
5. **planning 与 execution 的耦合**：`executor.py`（TaskGraphExecutor）是否有 production 调用
   需要第二轮确认（runtime 未 import executor.py）。

---

## 五、待第二轮确认清单

- [ ] 设计文档: `BUSINESS_CHAIN_1.5_PLANNING.md` + `BUSINESS_FLOW_TASK_PLANNING.md` +
  `v3.0/DESIGN_PLANNING_SKILL_LAYER.md` + `v3.0/DESIGN_TASK_PLANNING_DYNAMIC.md` +
  `v3.0/ENGINEERING_PLANNING_SKILL.md` + `v3.0/DESIGN_PERSPECTIVE_PLANNER.md` +
  `v5/PLANNER_CONTEXT_AND_REST.md` + `v5/PLANNING_GAP.md` 精读
- [ ] `runtime/engine.py` 中 `self._planner` 真实类型与初始化路径
- [ ] `executor.py` TaskGraphExecutor 的生产消费（v3 orchestrator 是否走它）
- [ ] `models.py` 契约漂移的完整对照（哪些字段被谁用）
- [ ] CausalPlanner slow_path（D6）设计 vs 实现
- [ ] PerspectivePlanner（第三套）与 planner 主体系的边界
- [ ] 规划 ↔ 上下文/子图/执行层接口现状

---

## 六、勘误（深层次复核后）

> 见 `docs/only/planner/DEEP_AUDIT_20260803.md`。根因升级: 20 测试失败不是「模型签名漂移」，
> 而是 `v4/skill_layer/__init__.py` 引用 3 个不存在的模块（skill_pool/evaluation_engine/executor_map）
> → 包级 ModuleNotFoundError → `planner/models.py` try/except 静默落入 fallback 模型。
> 主规划路径（PlanningSkill+TaskGraphOptimizer）用 v3_legacy models，不受影响。

---

## 七、勘误二（设计精读后，P0 再升级）

> 见 `DEEP_AUDIT_20260803.md §一点五` + `DESIGN_FULL_READ_20260803.md §六/§七`。
> **整个 planner/ 包 7 个核心模块 import 全炸**（models.py 从 1,197L 缩到 0.7KB，
> 20+ 模型丢失 → AllocationError/PlanRevision/Task/SkillLevel/PlanStrategy 等全缺）。
> 时间线: 07-21 曾 70% 实现 → 08-xx v4 skill_layer 迁移覆盖 models.py → 整体回归。
> orchestrator v3 路径 import PlanningSkill 连带炸；runtime v6 延迟 import 被吞 → 静默降级。
