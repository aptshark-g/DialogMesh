# DESIGN_BEHAVIOR.md — 行为链改造设计（凝练版 v0.1）

> 状态: **v0.1 凝练基线**（2026-08-01）
> 定位: 行为链改造的设计主文档——三块依据（设计全貌/代码审计/外部方案）见 BEHAVIOR_REFACTOR_PREP.md
> 方案: **C 分阶段**（修断链 → 修 P2 → 接 v4 → 四层决策树 → 奖励闭环）+ 显式承诺（行为认知系统）

---

## 0. 一句话定位

行为链 = **行为认知系统**：隐式预测（四层决策树 + 行为图权重）+ 显式承诺（用户声明 + 系统蒸馏原则）一体，双向可逆（A24）。

---

## 1. 分阶段改造计划（方案 C）

### 阶段 1: 修断链（P0）

**问题**: `core/agent/integration.py` import `behavior_graph.*`（目录不存在）→ ModuleNotFoundError；`v3_common/integration_bridge.py:23` 顶层 import `v3_2.integration`（不存在）→ AgentPipeline=None 静默

**改动**:
| # | 文件 | 改动 |
|---|------|------|
| 1 | `core/agent/integration.py` | `behavior_graph.*` → `behavior.*`（graph_store/models/statistics/cold_start/pruning/fast_correction/causal_discovery） |
| 2 | `core/agent/v3_common/integration_bridge.py:23` | 顶层 import 改为 try/except 或归档（若 v4 已替代职责则归档） |
| 3 | 决定 integration.py（V32Pipeline）去留 | **建议归档**（v4 已用 adapter 替代其职责），避免继续维护双链路 |

**验证**: `python -c "import core.agent.integration"` 通过；`import core.agent` 无 AgentPipeline warning

### 阶段 2: 修 predictor/rewarder P2（接入前提）

**问题**: 权重硬编码(0.4/0.3/0.2/0.1)、ValueRanker 未传 load_est/prof_matcher（两维度恒 0）、prompt 写死领域、零测试

**改动**:
| # | 文件 | 改动 |
|---|------|------|
| 4 | `predictor/models.py` Candidate.compute_value | 权重进 ParameterRegistry（A18）或至少配置化 |
| 5 | `predictor/value_ranker.py` | 修正 load_est/prof_matcher 注入（integration 或新接线点传参） |
| 6 | `predictor/candidate_generator.py` | prompt 领域写死 → 通用化（"system administrator" → 按场景） |
| 7 | 新增 `predictor/tests/` + `rewarder/tests/` | 补预测/奖励单元测试（当前零测试） |

### 阶段 3: 接 v4 runtime（跑通现有 predictor）

**改动**:
| # | 文件 | 改动 |
|---|------|------|
| 8 | `core/agent/runtime/engine.py` | 初始化 BehaviorPredictor + BehaviorRewarder + TrainingFeedbackLoop（对齐 integration.py L74/L105/L106 的组装） |
| 9 | `core/agent/behavior/runtime_hook.py` | on_event 后接预测 + on_checkpoint 后接奖励 |

**守 ADR-013**: 预测结果只做后台准备 + prior 调整，不参与当前轮融合决策

### 阶段 4: 补四层决策树调度层（BC05 §3 落地）

**新增** `core/agent/behavior/scheduler.py`（或并入 predictor）:
```
L1 成本底线: token_budget_remaining ≤ 0 → 纯统计（禁 LLM）
L2 风险劫持: action ∈ {delete, pay, grant_permission} → 无条件 LLM
L3 冷启动探索: total_turns ≤ 3 → LLM + ε=0.6
L4 CI 宽度: <0.15 收敛→贝叶斯; 0.15-0.4 混沌→LLM 黄金区; >0.4 发散→主动询问
```
- 参数进 ParameterRegistry（budget/epsilon/CI 阈值，A18）
- predictor 现有四模式回退降为"执行器"（混沌区调用），调度由 scheduler 负责

### 阶段 5: 接奖励闭环

**改动**:
| # | 文件 | 改动 |
|---|------|------|
| 10 | `behavior/runtime_hook.py` | 用户实际行为 → TrainingFeedbackLoop.on_user_action + BehaviorRewarder（CorrectionDetector 反馈） |
| 11 | `behavior/llm_collaborative.py` | DPO 偏好对积累（LLM_COLLABORATIVE §四，N>20 触发） |

**纠错即训练**: 纠正惩罚 = 命中奖励 2 倍（+0.10/-0.20）；连续纠正 2 次硬覆盖（fast_correction 已有）

---

## 2. 显式承诺（讨论 2 拍板 + PRINCIPLES 映射）

### 2.1 定位

行为链的显式层——用户声明承诺 + 系统蒸馏原则，与隐式预测一体，双向可逆（A24）

### 2.2 存储格式（PRINCIPLES 结构）

```
when(situation) -> should(strategy) + rather_than(failed) + because(reason)
```

| 来源 | 生成方式 | 生命周期 |
|------|---------|---------|
| 用户声明（"当X提醒Y"） | 意图/PCR 识别 → 显式承诺 | pending/armed/fired/done/cancelled/expired |
| 系统蒸馏（隐式→显式） | 行为图稳定模式 + 元认知审核通过 → 原则 | 同上（PRINCIPLES 机制） |
| rather_than(failed) | NegativeKB 关联 | 常驻（反面教材） |

### 2.3 三个实现边界（已确认）

1. **存储**: 行为图节点/边加 `explicit: true` + 生命周期字段，共享图结构（不新建子系统）
2. **调度**: 显式承诺命中 → 确定性 FTS 匹配 → 隐藏上下文块（每轮≤3），不参与隐式预测权重竞争
3. **回流**: 承诺完成/取消回流行为图学习（显式→隐式），但触发本身不算学习信号（防自我强化）

### 2.4 冷启动升级（PRINCIPLES 回退重模拟）

```
冷启动模拟升级: 模拟→失败→回退到失败起点→修订策略→重模拟→成功/预算耗尽
（对应温度/cooldown 防死循环）
```

### 2.5 评测（ProactiveEval 结构）

```
environment = {user_information(OCEAN), trigger_factor}
→ LLM-as-judge 评估 should(strategy) 合理性 → score + reason
6 领域模板（劝说/模糊指令/长期跟进/系统操作/助手/推荐）= 黄金样例集领域
```

---

## 3. 验证基准

- 阶段 1: import 实测通过（断链修复）
- 阶段 2: predictor/rewarder 单元测试全绿（新增）
- 阶段 3: runtime 集成测试（行为记录→预测→建议 全链路）
- 阶段 4: 四层决策树各分支测试（成本/风险/冷启动/CI 分别断言）
- 阶段 5: 奖励闭环测试（命中/纠正/无反馈 三信号断言）
- 显式承诺: 黄金样例集（6 领域 × 中英）+ ProactiveEval score+reason

---

## 4. 拍板记录（2026-08-01）

| # | 议题 | 拍板 | 说明 |
|---|---------|---------|---------|
| A1 | integration.py 去留 | **归档到 un_use + 倡合到已用内容** | 不是简单丢弃：V32Pipeline 有价值的组装逻辑倡合进 v4 已用架构（统一化/包容性原则） |
| A2 | v4 接入方式 | **接 runtime/engine + runtime_hook（复用现有 predictor/rewarder）** | 侧重前者；predictor vs rewarder 质量/健壮性对比待评估 |
| A3 | ADR-013 落法 | **接对** | track_p 只影响 prior/后台准备，不参与当前轮决策 |
| B4 | 四层决策树 | **完整版** | 不留半截技术债（费用/风险/冷启动/CI 全实现） |
| B5 | 冷启动回退重模拟 | **做，但非次次启用** | 专门板机：**PCR 检测到具体特征才触发**（控 token/速度） |
| B6 | DPO 偏好学习 | **做完整** | 短期看不到不影响；不完整只会成为后续负担 |
| B7 | 显式承诺触发识别 | **多视角** | 每个模块都识别；模糊 → 问用户确认；准确 → 多视角一致判定 |
| C1 | predictor 死实例 | **清 predictor 内部 self.training（无参构造）** | 保留 integration/runtime 的有图实例 |
| C2 | 权重参数化 | **ParameterRegistry** | 与 PCR 一致（A18） |
| C3 | 黄金样例集 | **ProactiveEval 6 领域模板** | 劝说/模糊指令/长期跟进/系统操作/助手/推荐 |

---

## 5. 待后续细化

- [ ] predictor vs rewarder 质量/健壮性对比评估（A2 前置）
- [ ] 断链归档方案细节（integration.py 到 un_use 的具体落点 + 倡合内容清单）
- [ ] predictor 权重参数化的具体参数表（进 ParameterRegistry）
- [ ] 四层决策树的 budget/epsilon/CI 初始值（文献锚点）
- [ ] 显式承诺的确定性 FTS 匹配实现（对齐 openclaw）
- [ ] 系统蒸馏原则的触发条件（行为图稳定阈值 + 元认知审核标准）
- [ ] 冷启动回退重模拟的 PCR 特征板机定义（B5）
- [ ] 显式承诺多视角识别的模块接口（B7）
