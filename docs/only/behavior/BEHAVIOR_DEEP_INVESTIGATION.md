# 行为链深度审计（BEHAVIOR_DEEP_INVESTIGATION）

> 审计日期: 2026-08-01
> 审计对象: `core/agent/behavior/` + `core/agent/predictor/` + `core/agent/rewarder/` + `core/agent/integration.py`
> 方法: 逐文件全读（含依赖模块）+ 接线追踪 + 测试验证（进行中）
> 结论先行: **核心已实现且接线，但存在 4 处"挂了但未完全生效"问题 + 1 处设计-代码最大差距（四层决策树未落地）+ 1 处纯新增（显式承诺）**

---

## 一、文件清单与落地状态（全部已实现）

| 组件 | 文件 | 行数 | 状态 |
|------|------|:---:|:---:|
| 数据模型 | `behavior/models.py` | 151 | ✅ |
| 图存储 | `behavior/graph_store.py` | 119 | ✅ |
| 权重更新 | `behavior/weight_updater.py` | 50 | ✅ |
| 冷启动 | `behavior/cold_start.py` | 58 | ✅ |
| 快速纠正 | `behavior/fast_correction.py` | 37 | ✅ |
| 预测器入口 | `predictor/predictor.py` | 63 | ✅ |
| 候选生成 | `predictor/candidate_generator.py` | 30 | ✅ |
| 价值排序 | `predictor/value_ranker.py` | 35 | ✅ |
| 认知负载 | `predictor/cognitive_load.py` | 12 | ✅ |
| 画像匹配 | `predictor/profile_matcher.py` | 9 | ✅ |
| 预测模型 | `predictor/models.py` | 58 | ✅ |
| 训练闭环 | `predictor/training_loop.py` | 143 | ✅ |
| 奖励规则 | `rewarder/reward_rules.py` | 23 | ✅ |
| 时间衰减 | `rewarder/time_decay.py` | 9 | ✅ |
| 噪声自适应 | `rewarder/noise_adaptation.py` | 79 | ✅ |
| ABL 反思 | `rewarder/abl_reflection.py` | 64 | ✅ |
| 纠正检测 | `rewarder/correction_detector.py` | 41 | ✅ |
| 奖励模型 | `rewarder/models.py` | 40 | ✅ |
| 奖励器入口 | `rewarder/rewarder.py` | 71 | ✅ |
| LLM 协同 | `behavior/llm_collaborative.py` | 201 | ✅ |
| 适配器 | `behavior/adapter.py` | 428 | ✅ |
| 因果适配 | `behavior/causal_adapter.py` | 82 | ✅ |
| 上下文源 | `behavior/source.py` | 82 | ✅ |
| 裁剪 | `behavior/pruning.py` | 31 | ✅ |
| 统计 | `behavior/statistics.py` | 55 | ✅ |
| 运行时钩子 | `behavior/runtime_hook.py` | 119 | ✅ |

---

## 二、发现的问题（按严重度）

### P1-1 预测器四维权重硬编码（A18 未接入）

`predictor/models.py` `Candidate.compute_value()`:
```
expected_value = llm_probability*0.4 + success_rate*0.3 + (1-cognitive_load)*0.2 + profile_match*0.1
```
- 权重 0.4/0.3/0.2/0.1 硬编码，不在 ParameterRegistry——违反 A18（参数编码 + 可调）
- 设计文档四维权重同样写死，未参数化

### P1-2 ValueRanker 未传 load_est/prof_matcher（两个维度可能恒 0）

`integration.py` L74: `BehaviorPredictor(self.graph, self._candidate_gen, self._value_ranker, self._profile_matcher, self._cold_start)`——predictor 传入 prof_matcher，但 `ValueRanker(self.graph)` 在 integration L73 构造时**未传 load_est/prof_matcher**：
- `value_ranker.rank()` 里 `if self.load_est:` / `if self.prof_matcher:` 为 False → cognitive_load 保持默认 0.0、profile_match 保持默认 0.0
- 实际 expected_value = llm*0.4 + success*0.3 + 1.0*0.2 + 0*0.1 → **认知负载和画像两个维度不生效**
- 需要确认：predictor.py L17 `self.training = TrainingFeedbackLoop()` 无参构造（graph=None）→ 训练闭环的 graph 为空？但 integration L106 又建了 `TrainingFeedbackLoop(graph=self.graph)`——**存在两个 TrainingFeedbackLoop 实例，predictor 内部的可能是废的**

### P1-3 候选生成 prompt 领域写死

`candidate_generator.py`:
```
"You are analyzing a system administrator and developer's behavior."
"...technical/system operations only"
```
- 写死"系统管理员/开发者/技术操作"——与对话系统通用定位不符，非技术用户场景会生成无效候选

### P1-4 奖励规则简化 + 子串匹配误判风险

- `TrainingSignal.compute_reward` 只有三档（+0.10/+0.05/-0.15），设计文档是七档（含部分正确+0.2、纠正-0.2+更新正确路径等）
- `RewardRuleTable.evaluate` 的 partial 用 `any(a in actual for a in acts)` 子串匹配——"写代码" in "写代码注释" 会误判为 partial

### P2-1 奖励计算双实现

- `RewardSignal.compute_effective()`（raw*decay*(1-noise)）与 `NoiseAdaptation.get_effective_reward()`（raw*(1-noise)*(0.5+0.5*eff)*(0.5+0.5*snr)）两套逻辑
- `rewarder.py` 用 `get_effective_reward`，`compute_effective` 疑似死代码

### P2-2 时间衰减硬编码

`time_decay.py`: NO_DECAY=30 / MODERATE_TAU=300 / STRONG_TAU=3600 硬编码，未参数化

### P2-3 噪声自适应 MIN_SAMPLES=500 过高

`noise_adaptation.py`: 需要 500 样本才触发 analyze——单用户早期几乎不可能达到，噪声自适应实际长期不生效（设计说 Phase 1 统一 0.5 攒数据，但 500 门槛需确认是否合理）

### P3-1 四层决策树未落地（设计-代码最大差距）

BC05 §3 的①成本底线②风险劫持③冷启动④CI 宽度**在代码里不存在**——predictor 只有"四模式回退"（full/no_graph/no_llm/fallback），不是"四层调度决策"
- 搜索 risk_hijack/cost_bottom/token_budget/epsilon/confidence_interval 均无命中

### P3-2 显式承诺机制零现状（讨论 2 拍板的新增）

standing/commitment/cron/schedule/remind 全无命中——纯新增

---

## 三、接线确认

- `integration.py` L74 创建 predictor、L261 调用 `predictor.predict()`（条件 `if self.predictor and self._chain:`）
- `_chain` 填充：`if self.enable_graph and parse.is_reliable and not parse.undefined:` + action 非空 → `self._chain.append(step.step_id)`——**predictor 触发依赖编译器可靠性**
- L106 `TrainingFeedbackLoop(graph=self.graph)` + CorrectionDetector 在跑
- `BehaviorGraphAdapter` 接入 ContextSource + runtime_hook；cli/integration/event 均引用

---

## 四、待验证（测试/运行时）

- [ ] 跑 `behavior/tests/` + `predictor/` + `rewarder/` 测试
- [ ] 验证 P1-2（ValueRanker 两维度恒 0）运行时是否真实
- [ ] 验证 predictor 内 `self.training`（无参 TrainingFeedbackLoop）是否为死实例
- [ ] `_chain` 在真实对话中是否真的会填（编译器可靠性门槛）


---

## 五、AST 全局 import 分析（2026-08-01）—— 重大发现

### 5.1 v3.2 主链路 integration.py 断裂（**P0**，2026-08-01 升级）

- `core/agent/integration.py`（V32Pipeline）import `behavior_graph.*`（`from .behavior_graph.graph_store` 等，L4-6/13/29/34-35）→ 指向 `core/agent/behavior_graph/`（**该目录不存在**）→ **一旦 import 即 ImportError**
- `v3_common/integration_bridge.py:23` 引用 `from core.agent.v3_2.integration import V32Pipeline` → **`v3_2/integration.py` 不存在** → **ImportError**
- `core/agent/persistence.py:5` 延迟 import `from .integration import V32Pipeline` → 同断

**结论：v3.2 的 V32Pipeline 完整链路（integration.py + predictor + rewarder）当前是断裂的——BehaviorPredictor/BehaviorRewarder/TrainingFeedbackLoop 只被这条断链引用（除 v4 侧需确认）**

**实证（2026-08-01 细化检查）**:
- `core/agent/__init__.py:10-18`：try/except 包裹 `from core.agent.v3_common.integration_bridge import AgentPipeline` → 失败后 `AgentPipeline = None` + warning——包能 import，但 AgentPipeline 永远静默不可用
- `v3_common/integration_bridge.py:23`：**顶层 import 无 try/except**（`from core.agent.v3_2.integration import V32Pipeline`）→ 直接 ModuleNotFoundError（实测）
- `persistence.py:5`：TYPE_CHECKING 保护（运行时不崩），但 PersistenceManager 依赖的 V32Pipeline 实际不可用
- `deepseek_provider.py`：V32Pipeline 只在 docstring 里（安全）
- AgentPipeline 调用方：仅 `pcr/tests/intent_trace_cli.py`（测试 CLI）——生产路径无消费者，断裂是“安静”的
- **与 PCR 同型**：多代演进 → 代码分裂（behavior/ v4 新 vs behavior_graph v3.2 旧路径）→ 旧路径断裂被 try/except 吞掉 → 静默降级（= PCR 的 “ImportError 被吞 → PCRBridge 永远降级”同构）

### 5.5 用户核查补录（2026-08-01）—— 比审计文档更严重

**核心发现**：行为链的断不是“未接线”，是“整个大脑 import 就炸”。实测：
```
❌ import core.agent.predictor.predictor → ModuleNotFoundError
    (predictor.py:5 → training_loop.py:2-4 → ..behavior_graph.* 旧路径)
```

**断链 3 处**（审计原文只写了 integration）:
| # | 位置 | 状态 |
|---|---------|---------|
| ① | `predictor/training_loop.py:2-4` → `..behavior_graph.*` | ❌ 审计漏网（本文核查新发现） |
| ② | `integration.py` 7 处 `.behavior_graph.*`（L4/5/6/13/29/34/35） | ✓ 审计已写 |
| ③ | `cold_indexer.py:80` + `consolidation.py:68` → `.behavior_graph.models` | ❌ 审计漏网（本文核查新发现） |

**好消息**：所有断链指向的 7 个模块（graph_store/models/statistics/cold_start/pruning/fast_correction/causal_discovery/weight_updater）在 `behavior/` 里**全部存在**——修复 = 前缀替换（`.behavior_graph.` → `.behavior.`），**最小复活改动 4 处文件**（training_loop / integration / cold_indexer / consolidation）

**耦合关系（改造要拆的结）**:
- ① predictor ↔ training_loop 硬耦合（import 链，修一处全复活）
- ② integration 混用两套路径（behavior_graph 断 + predictor/rewarder 通）
- ③ predictor 内部死实例 self.training + integration 又建一个（双实例）
- ④ ValueRanker 未传 load_est/prof_matcher（两维度恒 0）
- ⑤ rewarder 独立无断链 → 可先单独改

**有效改动清单**:
| 级别 | 文件 | 改动 |
|:---:|---------|---------|
| P0 断链 | training_loop / integration / cold_indexer / consolidation | 前缀替换 .behavior_graph. → .behavior. |
| P1 v4 接入 | runtime/engine + runtime_hook | 接 predictor/rewarder（守 ADR-013） |
| P2 修复 | models 权重 / value_ranker 注入 / prompt / 死实例 | 质量修复 |
| P3 新增 | scheduler 四层决策树 + explicit_commitment 显式承诺 | 设计新增 |
| 不改 | v3_2/v4 门面 + behavior/ 13 文件 | 已接线 |

### 5.2 v4 主链路 = core/agent/behavior/（我审计的这套）

- `runtime/engine.py:45` import `core.agent.behavior.adapter`；L437-454 用 BehaviorGraphAdapter.record_event 记录行为
- `cli/engine.py:286-288` 创建 `BehaviorGraphAdapter(graph_path="data/behavior_graph.json")`
- `v4/behavior_graph/__init__.py` 是门面（re-export adapter/causal_adapter/runtime_hook）
- `engineering_bridges.py:377` 用 `core.agent.behavior.llm_collaborative`

**结论：v4 用 `behavior/`（adapter + causal + runtime_hook + llm_collaborative），但 v4 是否用 BehaviorPredictor/BehaviorRewarder 待确认**

### 5.3 v3_2/behavior_graph/__init__.py = re-export 层

- `v3_2/behavior_graph/__init__.py` 存在（re-export core.agent.behavior.*）
- `v3_2/predictor/__init__.py` 存在（re-export core.agent.predictor.*）
- 但 v3_2/integration.py 不存在 → 这些 re-export 层没有消费方（断裂）

### 5.4 待确认（下一步）

- [ ] v4 主链路（runtime/engine、v4/cognitive）是否调用 BehaviorPredictor/BehaviorRewarder/TrainingFeedbackLoop
- [ ] predictor/rewarder 在 v4 是"实现但未接线"还是"仅旧链引用"


---

## 六、CLI 侧审计（2026-08-01）

### 6.1 CLI 行为链接线现状

| CLI 位置 | 行为链相关 | 状态 |
|---------|-----------|:---:|
| `cli/engine.py` L286-288 | 创建 `BehaviorGraphAdapter(graph_path="data/behavior_graph.json")` | ✅ 记录面 |
| `cli/registry.py` L289-298 | 注册 `behavior_graph`（adapter）+ `causal_substrate`（CausalSubstrateAdapter） | ✅ 记录面+因果 |
| `cli/registry.py` L336 | 注册 `behavior_discovery`（v4/cognitive，另一组件） | ✅ 无关 |
| `cli/inspect_v3_cmd.py` L8-18 | 仅检查 "BehaviorGraph module is importable"（空壳） | ⚠️ 无实质 |
| `cli/commands/` | **无专门行为链命令** | ❌ 缺失 |

### 6.2 结论：CLI 侧也是"只有记录面"

- 与 v4 runtime 一致：adapter 接线，predictor/rewarder 连 CLI 命令都没有
- 改造需新增 CLI 命令（白盒 A19）：
  - `dm behavior predict`（看预测结果）
  - `dm behavior graph show`（看行为图）
  - `dm behavior config`（权重/阈值参数化，A18）
  - `dm commitment list/add/cancel`（显式承诺，讨论 2 拍板）
- registry 需注册 predictor/rewarder（对齐 behavior_graph 注册模式）

### 6.3 改造顺序修正

阶段 3（v4 接入）必须包含 CLI 侧：
```
runtime/engine 接 predictor → cli/engine 初始化 predictor
registry 注册 predictor/rewarder → CLI 命令暴露（dm behavior *)
→ 每个能力都有 CLI 通道（A19 白盒）
```
