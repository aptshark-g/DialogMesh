# 规划深层次复核（第二轮·实锤验证）

> 日期: 2026-08-03 | 对象: `planner/models.py` + `v4/skill_layer/` + `planner/planner.py` +
> `planner/skill_pool.py` + `causal/planner.py` + `runtime/engine.py` + `orchestrator/orchestrator.py`
> 方法: 源码精读 + 运行时探针（import 解析）+ 全库 rg
> 结论: **第一轮「模型签名漂移」升级为「包级断链」；确认主规划路径在 runtime 恒 None；
> 技能蒸馏子系统（20 测试失败区）与主规划路径是两条腿**。

---

## 一、根因升级: 不是签名漂移，是包级断链

### 证据链（探针实证）
```
planner/models.py:
    try:
        from core.agent.v4.skill_layer.models import (ActionNode, CapabilityBlueprint, SkillBelief, SkillCandidate, Skill)
    except ImportError:
        ...fallback 极薄 dataclass（只有 candidate_id/source 等 2-4 字段）

探针: from core.agent.planner.models import SkillCandidate
  → SkillCandidate.__dataclass_fields__ = {'candidate_id', 'source'}   ← fallback 版

为什么 ImportError？
  v4/skill_layer/__init__.py:
      from .models import ...
      from .skill_pool import SkillPool      ← 模块不存在！
      from .evaluation_engine import EvaluationEngine   ← 模块不存在！
      from .executor_map import EXECUTOR_MAP            ← 模块不存在！
  → 导入包 __init__.py 时 ModuleNotFoundError → 整个包导入失败
  → planner/models.py 静默落入 fallback（try/except 吞掉真实错误）

确认: v4/skill_layer/ 目录只有 models.py + __init__.py（skill_pool/evaluation_engine/executor_map 全缺）
```

### 影响
```
skill_pool.py / distillation_engine.py / evaluation_engine.py / external_adapter.py
期望完整模型（domain/blueprint/belief/references 字段）→ fallback 模型缺字段 → TypeError
→ 20/27 测试失败（test_skill_pool 6 + test_distillation 5 + test_evaluation 3 +
   test_external 5 + test_models 2）
```

---

## 一点五、P0 再升级: 整个 planner/ 包无法 import（2026-08-03 深读补证）

### 证据（运行时探针）

```
import core.agent.planner.*:
  OK    models.py（try/except 静默 fallback 到 5 个极薄类）
  FAIL  agent_allocator.py  -> cannot import name 'AllocationError'
  FAIL  planner.py          -> cannot import name 'PlanRevision'
  FAIL  skill_engine.py     -> cannot import name 'AllocationError'
  FAIL  executor.py         -> cannot import name 'PlanRevision'
  FAIL  scheduler.py        -> cannot import name 'Task'
  FAIL  skill_registry.py   -> cannot import name 'SkillLevel'
  FAIL  strategy_selector.py-> cannot import name 'PlanStrategy'

根因: planner/models.py 被改写成 v4 skill_layer 重导出壳后，
  原 20+ 模型（Task/TaskDAG/PlanStep/PlanStrategy/PlanRevision/PrimitiveLibrary/
  SequentialDecomposition/TreeOfThought/SkillLevel/AllocationError...）全部丢失，
  只剩 fallback 5 类（ActionNode/CapabilityBlueprint/SkillBelief/SkillCandidate/Skill）。
  → 7 个核心模块 import 全炸；v3_0/planning/ 门面连带炸。

上游影响（静默降级链）:
  runtime/engine.py:842  if self._planner is not None:（恒 False）
  runtime/engine.py:847  from core.agent.planner.skill_registry import SkillRegistry
    → ImportError 被 try/except 吞 → 规划功能静默缺失
  orchestrator/bootstrap.py:42  from core.agent.planner.planner import PlanningSkill
    → orchestrator v3 路径同样炸（orchestrator.py:66）
```

### 影响面（比 20 个测试失败严重得多）

```
1. 规划包 = 全部不可用（不是"部分可用"）
2. orchestrator（v3 编排）import PlanningSkill 即炸 → 编排路径可能整体降级
3. runtime v6 规划 = 恒 None（延迟 import 被吞）
4. 需恢复 planner/models.py 完整模型（git 历史可找回）
```

### 修复方向

```
P0-1: 从 git 历史恢复 planner/models.py 的 20+ 模型（git log -- core/agent/planner/models.py）
P0-2: 恢复后验证 7 模块 import + 20 测试
P0-3: v3_0/planning 门面与 v4/skill_layer 的关系拍板（两套模型归一）
```

## 二、规划双路径（重要区分）

### 2.1 主规划路径（v3 orchestrator 真接线，不受 models.py 断链影响）
```
orchestrator/orchestrator.py:66  PlanningSkill（async plan）
orchestrator/orchestrator.py:585,605  await planning_skill.plan(...)
planner/planner.py:59,101  TaskGraphOptimizer（内部使用）
planner/planner.py:301-304  三种策略: RULE_BASED / HYBRID / LLM_DRIVEN
planner/planner.py:494      await self.optimizer.optimize(graph)
→ 主路径数据模型来自 v3_legacy.data_models（Intent_v3/TaskGraph_v3），
   与 v4 skill_layer models **无关**
```

### 2.2 技能蒸馏路径（测试失败区）
```
skill_pool / distillation / evaluation / external_adapter ← 依赖 v4 skill_layer.models
→ 包级断链 → 20 测试失败
```

### 2.3 runtime 路径（恒 None）
```
runtime/engine.py:224  self._planner = None（唯一赋值）
runtime/engine.py:842  if self._planner is not None: ← 恒 False
→ v6 主宿主规划未接线（执行层 DEEP_AUDIT §四）
```

---

## 三、CausalPlanner（D6 确认）

```
causal/planner.py:137-160  CausalPlanner（runtime/engine.py:32 真接线）
方法集: record_step / process_chain / get_chain / get_recent_chain / save / load / stats
→ 无 slow_path 方法（D6 确认，关联链审计已实锤）
→ 关联链审计 F8 修复方向: cognitive_loop.py 调 process_chain()（已标记完成）
```

---

## 四、环境依赖（向量/规划相关）

```
numpy 2.0.2 OK | faiss 1.13.0 OK | jieba OK | nats OK
chromadb FAIL（pydantic_settings 缺失）→ ChromaBridge available=False
sentence_transformers / stanza FAIL（numpy 版本比较 ValueError）→ BGE 静默降级
hnswlib / pymilvus 未安装 → HNSWIndex / MilvusVectorStore 不可用
```

---

## 五、待拍板/待修复清单（规划）

| # | 级别 | 事项 | 方向 |
|---|---|---|---|
| P1 | P0 | v4/skill_layer 包断链（缺 3 模块）| 补 skill_pool/evaluation_engine/executor_map 或改 __init__ 容错 |
| P2 | P0 | planner/models.py try/except 静默降级 | 显式探针日志 + 失败时 raise（拒绝静默）|
| P3 | P1 | runtime _planner 恒 None | 与执行层 X8 联动：v6 规划接线决策 |
| P4 | P2 | CausalPlanner slow_path 缺失 | 全局讨论（slow_path 语义 vs process_chain 替代）|
| P5 | P2 | 两套规划模型（v3_legacy vs v4 skill_layer）归一 | 全局讨论 |
| P6 | P2 | planner 测试 20 失败修复 | 断链修复后跑全量 |
