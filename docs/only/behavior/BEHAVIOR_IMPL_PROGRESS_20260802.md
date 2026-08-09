# 行为链施工进度 — 2026-08-02

> 状态: **P0-P3 + CLI 全部完成**（124/124 行为链测试绿；关联链/蓝图/子图/PCR 全量回归 162/162 无破坏）
> 依据: `docs/only/behavior/BEHAVIOR_DEEP_INVESTIGATION.md`（深审计）+ `BEHAVIOR_REFACTOR_MAPPING.md`（关系映射）+ `DESIGN_BEHAVIOR.md`（拍板 A1-C3）

---

## 一、施工总览

| 阶段 | 内容 | 验证 |
|:---:|------|------|
| P0 | 断链修复 + integration.py 归档（A1）| import 探针 12/12 全 OK + AgentPipeline 不再静默 None |
| P2 | predictor/rewarder 质量修复（权重/ranker/prompt/死实例/奖励内核）| 84/84（rewarder+predictor+behavior_graph+adapter）|
| P1 | v4 接入（BehaviorBrain + engine + handlers + runtime_hook，ADR-013）| tests/test_behavior_brain.py 9/9 |
| P3 | 四层决策树 + 显式承诺（完整版，B4/B6）| tests/test_behavior_scheduler.py 23/23 |
| CLI | `dm behavior` + `dm commitment` 白盒命令（A19）| tests/test_behavior_cli.py 8/8 |

---

## 二、改动文件清单

### P0 — 断链修复（大脑复活）

| 文件 | 改动 |
|------|------|
| `core/agent/predictor/training_loop.py` | `..behavior_graph.` → `..behavior.`（3 处）+ 移除冗余 correction 覆盖（P2 顺带）|
| `core/agent/cold_indexer.py` | `.behavior_graph.` → `.behavior.`（1 处）|
| `core/agent/consolidation.py` | `.behavior_graph.` → `.behavior.`（1 处）|
| `core/agent/v3_common/integration_bridge.py` | 移除顶层 `from core.agent.v3_2.integration import V32Pipeline`（硬断）→ AgentPipeline 可 import/实例化 |
| `core/agent/persistence/__init__.py` | re-export `CLISessionPersistence`/`TurnRecord`（包化后门面丢失）|
| `core/agent/observability/__init__.py` | re-export `StructuredLogger`/`SessionMetrics`/`MetricsAggregator`/`AlertEngine` |
| `core/agent/cognitive_compiler/__init__.py` | `CompilerMode` 改从 `decomposer` 导入——修掉 try/except 吞成 None 的静默降级（用户红线）|
| `core/agent/v3_2/rewarder/__init__.py` | `RewardRuleTable` 来源 `models` → `reward_rules` |
| `core/agent/v3_2/un_use/integration.py` | `core/agent/integration.py`（V32Pipeline）**归档**（A1：归档+倡合到已用架构）——除 behavior_graph 外还有 fusion/l1_summary/l2_summary/causal_substrate 等多处永久性断裂，对应模块已被 v4 替代 |
| `core/agent/persistence.py` | 移除未使用的 TYPE_CHECKING 死 import |

### P2 — predictor/rewarder 质量修复（A18）

| 文件 | 改动 |
|------|------|
| `core/agent/compiler/parameter_registry.py` | 新增 `behavior.*` 25 项参数：预测四维权重 / 奖励七档 / 时间衰减 / 噪声样本门槛 / 调度阈值（A18 全参数化）|
| `core/agent/predictor/models.py` | `Candidate.compute_value()` 权重走 `get_predict_weights()`（registry，冷启动兜底字面值）；`TrainingSignal.compute_reward()` 改用共享内核 |
| `core/agent/predictor/value_ranker.py` | `rank()` 从 registry 取权重一次传入 |
| `core/agent/predictor/predictor.py` | **C1** 死实例 `self.training` 清除；no_graph 模式硬编码 `*0.7` 改为 `compute_value()`；新增 `mode_hint` 执行器契约（stats/ask/llm）|
| `core/agent/predictor/candidate_generator.py` | prompt 领域写死（"system administrator"）→ 通用化 + `domain_prompt` 可注入；`llm=None` 守卫 |
| `core/agent/rewarder/reward_rules.py` | **BC05 §6.1 七档内核** `evaluate_accuracy`（top1 +1.0 / top3 +0.5 / partial +0.2 / alt -0.3 / miss -0.5 / corr -0.2 / none 0）；`_shared_direction` 修正子串误判（"写代码"⊂"写代码注释"→ miss 而非 partial）；ASCII 词级 + CJK 中段重叠 |
| `core/agent/rewarder/time_decay.py` | 硬编码 NO_DECAY/TAU 参数化（registry）+ 修复 `delta_t <= 300` 字面量 bug → `self.MODERATE_TAU` |
| `core/agent/rewarder/noise_adaptation.py` | MIN_SAMPLES 500→30（registry，单用户早期可触发）；`get_effective_reward` 复用 `compute_effective` 基核（P2-1 双实现合一）|
| `core/agent/rewarder/rewarder.py` | 硬覆盖阈值 3→2（对齐 fast_correction/设计）；apply_rate 参数化 `behavior.reward_apply_rate` |

### P1 — v4 接入（ADR-013：预测=后台先验，不参与当前轮）

| 文件 | 改动 |
|------|------|
| `core/agent/behavior/brain.py`（新）| **BehaviorBrain 内核**：predictor + ValueRanker（**P1-2 注入 load_est+prof_matcher**，两维度不再恒 0）+ 单 TrainingFeedbackLoop（C1）+ rewarder + profile；`learn_from_event`（学习）+ `predict_next_background`（daemon 线程预测）+ `on_checkpoint` + `shutdown`（join 防退出竞态）+ `commitment_context` |
| `core/agent/runtime/engine.py` | `_init_behavior_brain()`（惰性、非致命）+ `_run_behavior_brain(event)` + `_behavior_brain_stats()` + `stop()` 里 `brain.shutdown()` + `on_session_end` 触发 checkpoint |
| `core/agent/event/handlers.py` | BEHAVIOR 阶段 handler 记录后调用 `engine._run_behavior_brain(evt)` |
| `core/agent/behavior/runtime_hook.py` | 门面支持 `brain`；`register_with_engine(llm_provider=...)` 把 brain 挂到 engine（一内核多门面）|

### P3 — 新增（完整版，B4）

| 文件 | 改动 |
|------|------|
| `core/agent/behavior/scheduler.py`（新）| **四层决策树**：L1 成本底线→stats / L2 风险劫持（delete/pay/permission）→LLM / L3 冷启动（turns≤3）→explore ε=0.6 / L4 CI 宽度（Wald 区间）收敛→stats、混沌→LLM 黄金区、发散→ask；`epsilon_for_turns` BC05 §4 动态衰减；参数全 registry |
| `core/agent/behavior/explicit_commitment.py`（新）| **显式承诺**：`when→should+rather_than+because` 存储；pending→armed→fired→done 生命周期；确定性 FTS 匹配（≤3 上下文块，不参与隐式预测）；显式→隐式回流（完成/取消入图，**触发本身不算学习信号**）；稳定模式蒸馏（隐式→显式，A24）；B5 回退重模拟 `simulate_with_retry` + PCR 触发闸 `cold_start_retry_trigger`；B7 声明识别 `recognize_declaration` |
| `core/agent/v4/behavior_graph/__init__.py` | 门面 re-export 新增（Scheduler/Commitment/BehaviorBrain）|

### CLI — 白盒（A19）

| 文件 | 改动 |
|------|------|
| `core/agent/cli/commands/behavior_cmd.py`（新）| `dm behavior show/predict/graph/config/distill` + `dm commitment list/add/arm/fire/complete/cancel/expire/match` |
| `core/agent/cli/commands/__init__.py` | 注册 `_bh` |

### 测试

| 文件 | 说明 |
|------|------|
| `tests/test_behavior_brain.py`（新，9）| brain 内核（fallback/no_llm/学习链/shutdown/注入验证）+ engine wiring |
| `tests/test_behavior_scheduler.py`（新，23）| 四层决策树 9 + 承诺生命周期/匹配/回流/蒸馏/声明识别/重模拟 15 |
| `tests/test_behavior_cli.py`（新，8）| CLI 白盒命令全路径（fixture 双 patch get_engine 解决模块级绑定）|
| `core/agent/compiler/tests/test_parameter_registry.py`（修）| 对齐真实实现（`load_defaults`→去掉；2 个不存在参数断言→真实参数）——预先存在的坏测试 |
| `core/agent/v3_2/tests/test_rewarder/test_rew_core.py` / `test_predictor/test_pred_core.py`（修）| 奖励断言更新为 BC05 七档 + 新增对抗断言（partial 拒绝前缀、top3、alternative、correction）|

---

## 三、验证结果（2026-08-02）

```powershell
# 行为链全套（新增 + 旧）: 124/124
pytest tests/test_behavior_brain.py tests/test_behavior_scheduler.py tests/test_behavior_cli.py
       core/agent/v3_2/tests/test_rewarder core/agent/v3_2/tests/test_predictor
       core/agent/v3_2/tests/test_behavior_graph core/agent/behavior/tests

# 全量回归（防破坏）: 162/162 (103 关联链 + 10 蓝图 + 40 子图 + 9 PCR)
pytest tests/test_association_funnel.py tests/test_l1_modifiers.py tests/test_l1_5_completer.py
       tests/test_l2_5_belief.py tests/test_l3_intent.py tests/test_multi_intent_split.py
       tests/test_l2_entity_graph.py tests/test_association_deep.py tests/test_association_service.py
       core/agent/v3_2/tests/test_causal_substrate core/agent/v3_2/tests/test_fusion
       core/agent/v3_2/tests/test_do_calculus tests/test_blueprint_v2.py tests/test_subgraph_v2.py
       tests/test_pcr_v2.py

# 其余旧测试: 107/107 (subscribers 8 + parameter_registry 9 + compiler + l1_summary + negative_kb + foa)
```

## 四、环境坑与防御

- **anaconda 3.9 numpy 坏** → 全管线 state machine 偶发硬崩溃 0xC000013D（后台预测线程与解释器退出竞态）→ `BehaviorBrain.shutdown()` join 防御已加；隔离 BEHAVIOR 阶段探针干净退出（predict 1/learn 0）
- stderr `State save failed PermissionError: ~/.dialogmesh/state.json` 为 .venv 3.13 环境差异噪音（`_save_state` 已 try/except 防御，生产 3.11 正常）
- `BehaviorGraphAdapter.record_event` 的 kind 映射与 `brain.extract_action` 保持一致（dialog/ui/config/api/document/tool）

## 五、剩余工作（记录，非本次范围）

- B5 回退重模拟的 engine 接线：`simulate_with_retry` 原语已就绪，需在 PCR 特征板机触发时接入 brain/engine
- B7 显式承诺多视角识别：brain.learn_from_event 已有单视角识别；各模块（PCR/关联链/子图）识别接口未接
- 显式承诺持久化路径：registry 支持 store_path，engine/CLI 未挂载固定路径
- 蓝图 P1 清单（§八）：PlanGate/expand_from_dag_trace/route_mode/PCR 模型统一等
