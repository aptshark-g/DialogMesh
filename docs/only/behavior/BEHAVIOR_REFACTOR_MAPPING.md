# 行为链改造准备 — 文件关系映射

> 2026-08-01 · 依据: BEHAVIOR_DEEP_INVESTIGATION + BEHAVIOR_REFACTOR_PREP + DESIGN_BEHAVIOR
> 目的: 改造前扯清"行为链牵扯什么、什么耦合一起、改哪些文件才有效"
> 方法: 与 PCR_REFACTOR_PREP_MAPPING 同法 — 逐引用点实测

---

## 一、行为链全景（实测确认）

```
┌─────────────────────────────────────────────────────────────┐
│  行为链 = behavior/ (记录面) + predictor/ + rewarder/ (大脑)   │
├─────────────────────────────────────────────────────────────┤
│  behavior/ 13 文件 (全部可 import ✅):                        │
│    adapter.py (428L) / causal_adapter.py / runtime_hook.py   │
│    llm_collaborative.py (201L) / graph_store.py / models.py  │
│    cold_start.py / weight_updater.py / fast_correction.py    │
│    pruning.py / statistics.py / causal_discovery.py / source │
│                                                              │
│  predictor/ 7 文件 (2 断 ❌):                                 │
│    predictor.py ❌ (import training_loop)                    │
│    training_loop.py ❌ (import ..behavior_graph.*)           │
│    candidate_generator ✅ / value_ranker ✅ / models ✅       │
│    cognitive_load ✅ / profile_matcher ✅                     │
│                                                              │
│  rewarder/ 7 文件 (全部可 import ✅):                         │
│    rewarder.py / reward_rules / time_decay / noise_adaptation│
│    abl_reflection / correction_detector / models             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、断链实况（比审计更严重）

### 断链 1 — predictor 内部断裂 (P0)

```
predictor/predictor.py:5    from .training_loop import TrainingFeedbackLoop  ❌
predictor/training_loop.py:2  from ..behavior_graph.models import BehaviorStep  ❌
predictor/training_loop.py:3  from ..behavior_graph.weight_updater import WeightUpdater  ❌
predictor/training_loop.py:4  from ..behavior_graph.statistics import GraphStatisticsCollector  ❌

→ 实测: import core.agent.predictor.predictor → ModuleNotFoundError
→ 影响: BehaviorPredictor 完全不可用, 不只是"未接线"
```

### 断链 2 — integration.py (V32Pipeline) 断裂 (P0)

```
integration.py:4   from .behavior_graph.graph_store import BehaviorGraph  ❌
integration.py:5   from .behavior_graph.models import BehaviorStep  ❌
integration.py:6   from .behavior_graph.statistics import ...  ❌
integration.py:13  from .behavior_graph.cold_start import ...  ❌
integration.py:29  from .behavior_graph.pruning import ...  ❌
integration.py:34  from .behavior_graph.fast_correction import ...  ❌
integration.py:35  from .behavior_graph.causal_discovery import ...  ❌

→ integration.py 7 处 behavior_graph.* → core/agent/behavior_graph/ 不存在
```

### 断链 3 — 其他引用者 (P0)

```
cold_indexer.py:80    from .behavior_graph.models import BehaviorEdge  ❌
consolidation.py:68   from .behavior_graph.models import BehaviorEdge  ❌
```

### 断链影响链

```
predictor 断 → integration 断 → v3_common/integration_bridge.py:23 断
→ core/agent/__init__.py:10 try/except 吞 → AgentPipeline=None 静默
→ 但: 由于 __init__ 保护, core.agent 包本身仍可 import
```

### 好消息: 所有断链模块在 behavior/ 里都存在

```
behavior/graph_store.py ✅  behavior/models.py ✅  behavior/statistics.py ✅
behavior/cold_start.py ✅   behavior/pruning.py ✅  behavior/fast_correction.py ✅
behavior/causal_discovery.py ✅  behavior/weight_updater.py ✅
→ 断链修复 = 前缀替换 (.behavior_graph. → .behavior.)
```

---

## 三、行为链接线点全景（谁引用什么）

### 3.1 v4 记录面 (已接线 ✅)

| 引用者 | 用什么 | 状态 |
|--------|--------|:---:|
| `runtime/engine.py:45` | `behavior.adapter` (BehaviorGraphAdapter) | ✅ 主链路 |
| `runtime/engine.py:78-80` | `_record_behavior` (getattr _behavior_graph) | ✅ |
| `cli/engine.py:286-288` | 创建 BehaviorGraphAdapter(graph_path) | ✅ |
| `cli/registry.py:289` | register behavior_graph → adapter | ✅ |
| `cli/registry.py:292-294` | causal_adapter factory | ✅ |
| `v4/behavior_graph/__init__.py` | 门面 re-export | ✅ |
| `engineering_bridges.py:377` | `behavior.llm_collaborative` | ✅ |

### 3.2 v4 大脑 (未接线 ❌)

| 组件 | 唯一/主要调用方 | 状态 |
|------|---------------|:---:|
| BehaviorPredictor | integration.py:9 (断链) | ❌ 不可用 |
| BehaviorRewarder | integration.py:26 (断链) | ✅ 可 import 但无调用方 |
| TrainingFeedbackLoop | integration.py:22 + predictor.py:5 | ❌ 双实例 + 断链 |
| CorrectionDetector | integration.py:27 (断链) | ✅ 可 import |
| ValueRanker | integration.py:11 (断链) | ✅ 可 import |

### 3.3 耦合关系（改造时要拆的结）

```
① predictor.py 硬耦合 training_loop (import 链)
   training_loop 硬耦合 ..behavior_graph.* (旧路径)
   → 修 training_loop 前缀 = predictor 复活

② integration.py 混用两套:
   behavior_graph.* (断, 7处) + predictor.*/rewarder.* (通)
   → 前缀替换后可 import, 但 integration 本身 (V32Pipeline)
     是否保留待定 (v4 已替代)

③ predictor.py:17 内部 self.training = TrainingFeedbackLoop() 死实例
   integration.py:106 又建 self._training_loop = TrainingFeedbackLoop(graph)
   → 两个实例, 一个废 — 改造时统一

④ ValueRanker(self.graph) 未传 load_est/prof_matcher
   → cognitive_load/profile_match 恒 0 (两维度不生效)

⑤ rewarder 独立于 behavior_graph (无断链) ✅
   → 奖励层可单独修, 不依赖 predictor
```

---

## 四、有效修改文件清单（按优先级）

### P0 — 断链修复 (让行为链大脑复活)

| # | 文件 | 改动 | 效果 |
|---|------|------|------|
| 1 | `predictor/training_loop.py:2-4` | `..behavior_graph.` → `..behavior.` (3处) | **predictor.py 复活** (最小改动) |
| 2 | `integration.py:4-35` | `.behavior_graph.` → `.behavior.` (7处) | integration.py 可 import |
| 3 | `cold_indexer.py:80` | `.behavior_graph.` → `.behavior.` | cold_indexer 修复 |
| 4 | `consolidation.py:68` | `.behavior_graph.` → `.behavior.` | consolidation 修复 |
| 5 | `v3_common/integration_bridge.py:23` | try/except 或归档 | AgentPipeline 不再静默 None |

### P1 — v4 接入 (按 DESIGN_BEHAVIOR 阶段 3)

| # | 文件 | 改动 |
|---|------|------|
| 6 | `runtime/engine.py` | 初始化 BehaviorPredictor + BehaviorRewarder + TrainingFeedbackLoop |
| 7 | `behavior/runtime_hook.py` | on_event 后接预测 + on_checkpoint 后接奖励 (守 ADR-013) |

### P2 — 修复 predictor/rewarder 缺陷

| # | 文件 | 改动 |
|---|------|------|
| 8 | `predictor/models.py` | 四维权重 0.4/0.3/0.2/0.1 → 参数化 (A18) |
| 9 | `predictor/value_ranker.py` | load_est/prof_matcher 注入修正 |
| 10 | `predictor/candidate_generator.py` | prompt 领域写死 → 通用化 |
| 11 | `predictor/predictor.py:17` | 死实例 self.training 移除/统一 |

### P3 — 四层决策树 + 显式承诺 (新设计)

| # | 文件 | 改动 |
|---|------|------|
| 12 | 新增 `behavior/scheduler.py` | 四层决策树 (成本/风险/冷启动/CI) |
| 13 | 新增 `behavior/explicit_commitment.py` | 显式承诺 (when→should+rather_than+because) |

### 明确不改

- `v3_2/behavior_graph/__init__.py` / `v3_2/predictor/__init__.py` — re-export 层, 无消费方
- `v4/behavior_graph/__init__.py` — 门面正常
- `behavior/adapter.py` + 其余 12 文件 — 已接线, 不动

---

## 五、依赖关系图（目标态）

```
                     ┌────────────────────┐
                     │ behavior/ (13 文件) │ 记录面 (已接线, 不动)
                     │ adapter/runtime_hook│
                     └─────┬──────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ predictor/   │  │ rewarder/    │  │ scheduler/   │ 新增
│ 修断链+权重  │  │ 已通, 可先动  │  │ 四层决策树   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────┬────────┘                 │
                ▼                          │
     ┌──────────────────┐                  │
     │ runtime/engine   │ ← 接线点 (P1)    │
     │ _behavior_graph  │                  │
     └──────────────────┘                  │
                │                          │
                ▼                          ▼
     ┌──────────────────────────────────────────┐
     │ 显式承诺 explicit_commitment (新)          │
     │ 生命周期状态机 + 确定性匹配 + 回流学习      │
     └──────────────────────────────────────────┘
```

---

## 六、关键判断

1. **最小复活改动 = 4 处前缀替换** (training_loop + integration + cold_indexer + consolidation) — 行为链大脑即可 import
2. **rewarder 独立无断链** — 可先于 predictor 改造 (奖励层可单独动)
3. **predictor 复活后仍是"实现未接线"** — 需 runtime/engine 接入 (P1)
4. **integration.py (V32Pipeline) 去留待定** — v4 已用 adapter 替代, 建议归档
5. **四层决策树 + 显式承诺是纯新增** — 不碰现有代码, 可并行设计
6. **与 PCR 同型问题** — 多代演进 → 旧路径断 → try/except 吞 → 静默降级

## 七、建议执行顺序

```
第 1 步: 4 处前缀替换 (P0) → predictor/rewarder/integration 全复活
第 2 步: 验证 import + 跑 v3_2/tests (behavior_graph 测试)
第 3 步: 修 predictor P2 (权重/ranker/prompt/死实例)
第 4 步: runtime/engine 接入预测+奖励 (P1, 守 ADR-013)
第 5 步: 四层决策树 scheduler + 显式承诺 (P3, 新设计)
第 6 步: integration.py (V32Pipeline) 归档决策
```
