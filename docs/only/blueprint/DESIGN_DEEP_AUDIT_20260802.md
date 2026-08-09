# Blueprint 设计深度审计 + 执行解读 — 2026-08-02

> 审计对象: `docs/DESIGN_BLUEPRINT_ORCHESTRATION.md`（全文 15 节，已逐节带行号精读）
> **状态（2026-08-02）**: 本审计已完成使命。P0 施工完成，见 `P0_RETRO_20260802.md`（设计 vs 实现对照）+ `P0_TASK_PLAN_20260802.md`（完成状态）。后续工作转向 P1。
> 辅助: `docs/BUSINESS_CHAIN_11_BLUEPRINT.md`（11 链定位）、`docs/DESIGN_BLUEPRINT_SYSTEM.md`（早期）、`docs/ENGINEERING_BLUEPRINT.md`（工程规格）
> 目的: 不是对照代码打勾，而是**把设计内容本身讲透**——每节的设计意图、哲学定位、隐含前提、内在张力，最后给出完整的执行实施规划。
> 关联: 代码实现审计见 `BLUEPRINT_IMPL_AUDIT_20260802.md`（运行时实测）、`BLUEPRINT_AUDIT_20260802.md`（综合分析）。

---

## 〇、设计文档全景（15 节速览）

| 节 | 主题 | 一句话 |
|---|------|--------|
| §一 | 核心理念 | LLM 是图的构建者，不是图的执行者（make menuconfig 类比） |
| §二 | 前沿验证 | LangGraph/BatchDAG/CrewAI/Hermes → 共同结论: LLM 建图、运行时跑图 |
| §三 | 现有资产 | 已设计未接的 8 个模块 + 当前实际跑的线性管线 |
| §四 | 目标架构 | Engine → Decider(EventBus) → PlanGate → Execution 四层 |
| §五 | 5 策略 | RULE_BASED/TEMPLATE/HYBRID/LLM_DRIVEN/RECOVERY |
| §六 | 最小闭环 | 选蓝图→建 DAG→EventBus 执行→PlanGate 审核 |
| §七 | 与前沿差距 | 7 维度对比表（图构造/执行/状态/人机/并行/子图/持久化） |
| §八 | 实施优先级 | P0 建图+执行最短路 → P1 PlanGate → P2 7-Tree → P3 Subgraph |
| §九 | Meta 分层 | 热路径 SkillRegistry（快，非 LLM）；冷路径 Meta 学（异步） |
| §十 | 执行模式矩阵 | Level1 模板 / Level2 单步路由 / Level3 全图构建 |
| §十一 | 放权代价 | LLM_DRIVEN 是特殊模式（人工审核准入）+ 四重保护 |
| §十二 | 三层范式 | 设计(发散/收束/学习)→工程(约束)→执行(确定性) |
| §十三 | 成本控制 | 调迭代/层级而非 token；Profile+Behavior+Meta 代替人 |
| §十四 | 四段传递协议 | schema→订阅表→audit→进化（完整闭环契约） |
| §十五 | DAG 统一可视化 | BlueprintDAG = TaskGraph 超集，前端统一渲染 |

---

## 一、逐节深度解读

### §一 核心理念（L7-24）

**原文主张**: "LLM 是图的构建者，不是图的执行者"。反对硬编码线性管道（10 链写死在 agent_native），主张 LLM 动态构建有向图，确定性引擎执行，LLM 只在关键节点介入。

**设计意图**: 声明式编排——把"做什么"（LLM/声明）与"怎么做"（引擎/确定）分离。make menuconfig 类比的本质是**按目标选模块 + 依赖图编译**，即"按需装配"而非"全量编译"。

**哲学定位**: 这是全文的"公理层"。它默认了一个前提:**存在一个可靠的确定性引擎**。LLM 只负责"选择与组合"，不负责"执行细节"。这与我们 PARADIGM 的"白盒化（A19）+ 可回溯（A17）"一致——图本身是白盒产物，可检视、可编辑、可审计。

**隐含前提**（设计没明说但被依赖）:
1. 引擎必须存在且可靠（实现里 Decider 是假的——§十四契约只建了壳）；
2. 节点 = "链/模块调用"意味着每个链必须有**统一调用协议**（实现里是各 handler 各写各的 fallback）；
3. LLM 构建的 DAG 必须可校验（实现有 ConstraintChecker，但只查结构不查语义）。

**内在张力**: "LLM 建图"与"确定性"之间没有自动仲裁——LLM 建的图质量差怎么办？设计靠 §十一 的触发条件 + §十三 的质量闭环兜底，但这两块在实现里都是死代码。**理念成立，兜底缺失**。

**执行解读**: 理念本身正确且被行业验证，不需要改。施工重点是把"确定性引擎"真正建出来（§十四.3 订阅表）+ 让 LLM 建图有真实约束（§十一 四保护）。

### §二 前沿验证（L26-38）

**原文**: LangGraph（StateGraph+Supervisor+interrupt）、BatchDAG（LLM 生成类型化 DAG→确定性引擎）、CrewAI（@start/@listen 事件驱动隐式 DAG）、Hermes（ReAct+Skills+PlanGate）。共同结论: LLM 负责"建什么图"，运行时负责"怎么跑图"。

**设计意图**: 用行业证据支撑"建图/跑图分离"。四家的差异点其实很有信息量:

| 方案 | 图的粒度 | 图的时机 | LLM 自由度 |
------|---------|---------|-----------|
| LangGraph | 单步边 | 运行时逐步（隐式图） | 每步决策 |
| BatchDAG | 全图 | 一次性（显式图） | 一次性全权 |
| CrewAI | 事件监听 | 声明期（隐式图） | 只响应不主动 |
| Hermes | ReAct 循环 | 运行时 | 无图，靠 checkpoint |

**关键洞察（设计隐含但未展开）**: 这四家其实落在"LLM 自由度光谱"的不同位置。DialogMesh 的 5 策略矩阵（§五/§十）本质是把这条光谱**显式参数化**——这是比照抄一家更完整的做法，设计上是对的。

**实现落差**: 实现只抄了"形"（LLM_DRIVEN 的 diverge/learn/converge），没抄"神"——LangGraph 的 interrupt()（=PlanGate）和 BatchDAG 的确定性引擎（=EventBus）都没实现。所以"验证"只证明了理念，没指导落地。

**执行解读**: 施工时四家的"保护机制"要分别吸收: LangGraph 的 conditional_edges → HYBRID 单步路由真实现；BatchDAG 的一次性图 + 确定性执行 → LLM_DRIVEN 真实现；Hermes 的 PlanGate → checkpoint 真接线；CrewAI 的事件驱动 → 可选，与 EventBus 订阅表同构。

### §三 现有资产（L39-69）

**原文**: 3.1 列 8 个"已设计未接"模块（Blueprint Engine 只有 TEMPLATE / SkillRegistry 5 技能 / EventBus 10 链仍线性 / 7-Tree / PlanGate / Subgraph Compiler / Decider 状态机 / ReactRetryEngine）；3.2 当前实际跑: v3_session_api → AgentOrchestrator.process()（线性 9 阶段）→ /v6/profile（stub）→ switch LLM → Phase5 task_graph。问题: 10 链串行、LLM 只做最后回复、task_graph 有 schema 没接执行。

**设计意图**: 这是一份"现状诊断"——作者清楚认识到"设计资产多、接线少"。8 个模块的列举就是施工清单的雏形。

**实现落差（8-02 复查）**: 设计文档写于 7-26，8-02 的代码里:

| 模块 | 设计标注 | 8-02 实际 |
------|---------|----------|
| Blueprint Engine | ⚠️ 只有 TEMPLATE | ⚠️ HYBRID/LLM_DRIVEN 有了，但单例污染 |
| SkillRegistry | ⚠️ 5 技能 | ⚠️ 6 意图权重，但权重公式丢 base |
| EventBus | ❌ 10 链线性 | ❌ 两套 EventBus，蓝图 Decider 未接任何一套 |
| 7-Tree | ❌ 没接管线 | ❌ 仍没接 |
| PlanGate | ❌ 代码有 API 无 | ❌ 仍无（checkpoint 字段存在但执行不暂停） |
| Subgraph Compiler | ❌ 176L 零接入 | ⚠️ v4 已施工完整，但蓝图 `_handle_subgraph` 只透传 |
| Decider 状态机 | ❌ 替代 agent_native 的设计 | ⚠️ StateMachine 活了（CLI），但蓝图 Decider 是假的 |
| ReactRetryEngine | ⚠️ 没走管线 | ⚠️ 仍没走管线 |

**执行解读**: 这份"现状诊断"的每一行都是施工验收项。8-02 的进展集中在"构建层"（engine/skill_registry/llm_dag_builder），"执行层"几乎零进展。设计文档说的"当前只用了 TEMPLATE"已不准确（HYBRID/LLM_DRIVEN 已实现但未接线生产），需更新。

### §四 目标架构（L71-111）

**原文**: 四层垂直架构:
```
Blueprint Engine（选模板+LLM override+编译 DAG）
  → Decider (EventBus)（逐 Tick 检查依赖→发射 Task，链 = subscriber）
  → PlanGate（interrupt → 前端展示 → approve/adjust/reject → CorrectionJournal 学习）
  → Execution Engine（7-Tree 并行 + Sandbox/Permissions/Diff + ReAct 重试）
```

**设计意图**: 四层 = 构建/路由/审核/执行 的职责分离。关键设计点:
1. **Decider 是"发射器"不是"执行器"**——它检查依赖、发事件，链作为 subscriber 消费。这避免了"编排器直接调用链"的耦合。
2. **PlanGate 是"人机边界"**——高风险节点暂停，用户 approve/adjust/reject，结果进 CorrectionJournal（= 行为链的学习源）。
3. **Execution Engine 是"执行沙箱"**——7-Tree 并行 + 安全三件套（sandbox/permissions/diff）+ ReAct 重试（3 次上限）。

**哲学定位**: 这与 PARADIGM 的"可回溯可修正 + 元认知裁决"直接对应: Decider 发射的事件流 = 可回溯的轨迹；PlanGate = 元认知的人机接口；CorrectionJournal = 行为链的输入。四层架构 = 神经符号系统在工程层的落地。

**实现落差**:
- Decider: `_bus=None`，无订阅表，handler 直接调 `orch.process()`（整条线性管线重放）——**完全没实现"发射器"角色**；
- PlanGate: `blueprint_node.checkpoint` 字段存在，但 executor 从不检查 → 永不暂停；
- Execution: `agent_native` 有 `_execution_pipeline`（真实存在），但蓝图 Decider 不经过它；7-Tree 未接；
- CorrectionJournal: 无。

**执行解读**: 四层架构是合理的，但施工顺序要考虑依赖: **先修 Decider 的"发射器"角色（P0），再补 PlanGate（P1），最后接 Execution（P2）**——因为审核和执行都依赖"执行是真的"。若走"直接组件调用"方案（见实施规划），四层简化为三层（构建→执行→审核），Decider 变成"调度器"而非"总线"，可先不引入 EventBus。

### §五 5 策略（L112-125）

**原文**: RULE_BASED（纯规则）/TEMPLATE（固定模板+参数化）/HYBRID（模板 floor + LLM ceiling，默认）/LLM_DRIVEN（LLM 全权）/RECOVERY（失败重试→替换子图）。

**设计意图**: 这是"确定性→灵活性"的谱系 + 一个执行期兜底。注意 **RECOVERY 是执行期策略**（"失败重试→替换子图"），其余四个是构建期策略——设计把"构建策略"和"执行策略"混在一个枚举里，这是有意为之（策略贯穿全生命周期）。

**实现落差**:
- RULE_BASED 与 TEMPLATE 合并实现（engine.py L182 同一分支）——可接受但丢失"纯规则校验"语义；
- HYBRID 的 LLM override 污染全局模板（P0-1）；
- LLM_DRIVEN 缺 §十一 四保护；
- RECOVERY 只在**构建期约束失败**时用（engine.py L200-209），不是**执行期失败重试**——语义错位。执行期重试（ReAct）在 Execution Engine 层，蓝图没接。

**执行解读**: 策略矩阵保留。施工时: RECOVERY 语义要明确为"执行期"（decider 节点失败 → 替换子图重跑，而非直接 RECOVERY DAG）；RULE_BASED 可选合并但要在 match 里保留"纯规则"标志。

### §六 最小闭环（L126-149）

**原文**: 四步: Step1 SkillRegistry.match 选蓝图 → Step2 LLM 建 DAG → Step3 EventBus 执行 → Step4 PlanGate 审核。标注"本周可做"。

**设计意图**: 最小闭环 = "意图 → 可审核执行计划"的通路。四步的依赖关系: 1、2 是构建，3 是执行，4 是审核。设计把它定位为"最小"——不要求全链，先跑通主干。

**实现落差（8-02）**: Step1 ✅（match 可用）、Step2 ✅（build 可用但有污染 bug）、Step3 ❌（Decider 假）、Step4 ❌（PlanGate 未接）。**"本周可做"的四步，10 天后仍未闭环**。

**执行解读**: 这四步就是施工的验收主线。建议的"直接组件调用"方案下，Step3 改为"Decider 逐节点调用链组件（pcr_router/subgraph_compiler/...）"，Step4 改为"checkpoint 节点检查 + PlanGate 暂停"。闭环后即可作为 P0 交付。

### §七 与前沿差距（L150-163）

**原文**: 7 维度对比表（图构造/图执行/状态管理/人机协作/并行执行/子图嵌套/持久化），每格标注 ✅/❌/⚠️ 与差距。

**设计意图**: 这是"施工验收清单"的原型——7 个维度的差距就是施工范围。设计自评: 状态管理（EventLog）✅、持久化（SHA256）✅，其余 5 项有差距。

**实现落差（8-02 更新）**:
| 维度 | 7-26 设计自评 | 8-02 实际 |
------|-------------|----------|
| 图构造 | ⚠️ 没让 LLM 建图 | ✅ LLM_DRIVEN 有（diverge/learn/converge） |
| 图执行 | ❌ 线性管道 | ❌ 仍是（重放线性，EventBus 未接） |
| 状态管理 | ✅ EventLog | ⚠️ CLI 有，API 的 AgentOrchestrator `_event_log=None` |
| 人机协作 | ⚠️ PlanGate 需接 API | ❌ 仍未接 |
| 并行执行 | ⚠️ 7-Tree 需接 EventBus | ❌ 未接 |
| 子图嵌套 | ⚠️ Subgraph 需接入 | ⚠️ v4 子图已完整，蓝图未接 |
| 持久化 | ✅ SHA256 | ✅ |

**执行解读**: 图构造已完成（核心资产），剩下 4 个缺口（执行/人机/并行/子图接入）就是施工范围。这张表应成为施工验收的对照表。

### §八 实施优先级（L164-171）

**原文**: P0（本周）: LLM 选蓝图+建 DAG → EventBus 执行最短路；P1: PlanGate → 前端展示+编辑+回传；P2: 7-Tree 并行 → Execution Engine；P3: Subgraph Compiler → 上下文子图注入。

**设计意图**: 优先级逻辑 = **先打通"构建→执行"主干，再补审核/并行/子图**。顺序合理（审核依赖执行真，并行依赖执行真）。

**实现落差**: 8-02 的施工顺序反而先做了 P3 的 Subgraph（v4 子图完整）和构建层，P0 的"EventBus 执行最短路"被跳过。结果: 构建层有了但执行层空转。

**执行解读**: 施工应回到设计优先级: **P0 = 执行最短路**（构建→执行闭环）。P3 的子图已经做完，正好作为 P0 执行时的第一个真实链。规划的 P0 应合并"子图接入"——即 P0 闭环 = build(DAG) → decider(pcr/intent/context/subgraph/llm_reply 真执行)。

### §九 Meta 分层（L175-221）

**原文**: 热路径: SkillRegistry 是快速模式匹配（<500ms），不是 LLM 推理；冷路径: Meta LLM 异步消费 EventLog → 审计/对比/修正/学习 → 影响下次 Tick 策略。生命周期: SkillRegistry 匹配 ← Meta 调权重；LLM override ← Meta 审质量；执行 → EventLog → Meta 审计 → 下次更优。

**设计意图**: "热冷分离"是核心——**热路径必须快且确定，冷路径可以有延迟**。SkillRegistry 的权重就是 Meta（元认知）的"裁决"输出物。这与 PARADIGM 的元认知哲学（元认知统筹一切、裁决和复盘）完全一致。

**隐含前提**: 需要一个**持久的学习状态**（权重表）+ 一个**异步消费者**（EventLog → Meta → 权重写回）。设计假设这两块存在，但实现里:
- SkillRegistry 权重是纯内存（进程重启丢失）；
- MetaFeedback 零调用方（死代码）；
- EventLog 有（CLI），但没有 Meta 消费者订阅它。

**内在张力**: "学习不阻塞请求"与"学习需要真实执行数据"之间的管道（EventLog → 消费 → 写回）是整个闭环的**数据高速公路**，设计给了 schema（§14.4）但没给部署形态（谁跑这个循环？同进程后台线程？独立服务？）。

**执行解读**: 施工时 Meta 闭环的优先级应**低于** P0 执行主干——先让执行产生真实 EventLog，再让 Meta 消费它。若 P0 阶段就做 Meta，只会重复"假数据学习"（当前 update_weight 的 bug 就是例子）。

### §十 执行模式矩阵（L222-255）

**原文**: Level1 模板执行（LLM 零介入）/ Level2 单步路由（HYBRID，LLM 在分叉点问"下一步去哪"，=LangGraph conditional_edges，每次只决定一步）/ Level3 全图构建（LLM_DRIVEN，建完整 DAG + PlanGate，=BatchDAG）。

**设计意图**: 三个决策粒度 = LLM 自由度的**可调旋钮**。设计明确 HYBRID 是默认（"模板 floor + LLM ceiling"），且承认 Level2 的风险（局部最优 ≠ 全局最优）。这是对"每步决策"和"全图决策"的平衡。

**关键洞察**: Level2 的设计与当前实现严重不符——**实现里的 HYBRID 是"一次性问 LLM 怎么改模板"（全图修改），不是"每步问下一步去哪"（单步路由）**。实现做的是伪 Level3（问一次改全图），设计要的是真 Level2（执行时分叉点决策）。这是最大的语义落差之一。

**实现落差**: Level1 ✅（TEMPLATE 确定性）；Level2 ❌（实现成了一次性 override 而非分叉点路由）；Level3 ⚠️（有 diverge/learn/converge 但缺 PlanGate/Budget/Loop/Quality 保护）。

**执行解读**: 施工时要决策: 真做 Level2（执行时每步问 LLM）还是保留 Level2=模板+一次性调整？**建议**（对齐 LLM 成本与响应时间）: Level2 定义为"模板 + 构建期 LLM 一次调整 + 执行期仅在 checkpoint 节点询问"，即把"分叉点询问"降级为"checkpoint 询问"——既保留 LLM 介入能力，又不每步付延迟。此决策需拍板。

### §十一 高度放权模式 — 主动性的代价（L256-308）

**原文**: 行业为什么最小闭环（迭代多/死循环/低效果/质量漂移）；前沿解法（BatchDAG 一次性图 / LangGraph 单步 / Hermes checkpoint / CrewAI 事件驱动）→ 共同结论: **限制 LLM 的自由度 = 提升可靠性**；DialogMesh 定位: LLM_DRIVEN 不是默认，是"特殊模式，人工审核准入"；触发条件（置信度>0.8 且历史成功率高 / 因果推理 L5 / 用户手动）；四保护（PlanGate / Budget≤7 / LoopDetector 重访 3 次强制 checkpoint / QualityGate 低分降级 HYBRID）；与 L5 因果层关系（因果推理难点是"决定探索哪条路径"）。

**设计意图**: 这是全文**最有价值的约束哲学**。它明确反对"LLM 全权"，主张"受限的主动性"。四保护 = 给 LLM_DRIVEN 戴上四道保险。

**哲学定位**: 与 PARADIGM 的"收敛/发散"（T=0.8/0.1）、"低概率高价值定位"、"竞争吸收"呼应——放权必须有代价控制和吸收机制。也与我们审计发现的"假数据"问题形成对照: 设计主张**宁可降级也不造假**（QualityGate 降级 HYBRID），实现却在 fallback 里伪造 PCR/Intent 数据——**实现违背了设计哲学**。

**实现落差**:
| 保护 | 实现状态 |
------|---------|
| PlanGate | ❌ 未接 |
| Budget Gate（≤7） | ✅ ConstraintChecker.MAX_NODES=7 |
| LoopDetector（重访 3 次） | ❌ 无 |
| QualityGate（低分降级） | ⚠️ MetaState 有逻辑但零调用方（无副作用） |
| 触发条件（置信度>0.8） | ❌ match 的 confidence 没参与策略选择 |

**执行解读**: LLM_DRIVEN 在 P0 阶段应**默认禁用**（仅测试/CLI 显式启用），直到四保护齐备。这符合设计本意（"特殊模式"），也避免在真实现前让 LLM 全权跑。

### §十二 三层范式 — 设计→工程→执行（L309-384）

**原文**: 人类工程范式映射: 设计文档（发散 T=0.8 无上下文 + 收束 T=0.1 完整上下文 + 学习 arxiv/源码/框架）→ 工程文档（ConstraintTree: 安全/资源/依赖/权限）→ 实际解决（确定性执行，不来回改设计，ReAct 重试 3 次上限）。方案对比: 掩盖约束法（DialogMesh 已有）/ToT/Reflexion/GoT/STILL-ALIVE/DSPy。学习输入源 5 类 + 评估（权威性/相关性/时效性）。

**设计意图**: 三层范式是**认知循环的结构化契约**——每层独立、通过结构化信息传递（设计结论 → 约束 → DAG）。"掩盖约束法"（发散不给上下文→收束给完整）是核心资产，避免上下文锁死。

**哲学定位**: 这一节与用户此前讨论的哲学**高度同源**（掩盖上下文 → LLM 猜 → DMN 发散/ECN 收束；信息源权威性权重 → 与 credibility 学习一致）。设计文档作者与我们的哲学体系是同一脉络——这是宝贵的资产，不是要重写的对象。

**实现落差**:
- 发散/收束 ✅ 有（diverge/converge），但 diverge 的 prompt 仍给了 intent + text 前 1000 字（**没有真正"掩盖"**）；
- 学习 ⚠️ 4 路网络（arxiv/github/scholar/duckduckgo）但查询词是中文 intent（无意义）；
- ConstraintTree ⚠️ 只有资源（节点≤7）+ 依赖（拓扑/无环），安全/权限无；
- "确定性执行，不回头改设计" ❌ 实现是每节点重放线性管线 + 各种 fallback 改道。

**执行解读**: "掩盖约束法"要作为 LLM_DRIVEN 的**标准流程**保留并修正（diverge prompt 真正去掉上下文）。约束层补安全/权限两项（复用 `execution/sandbox.py` + `permissions.py`，registry 已注册）。

### §十三 成本与质量控制 — 自治化的驾驭（L385-462）

**原文**: 不是调 token，是调迭代次数和层级深度（结构性约束）。控制面板 4 参数（探索深度 1-5 / 验证严格度 / 学习广度 / 决策模式，默认 2/标准/核心/自动）。当人不选择时 Profile(OCEAN)+Behavior(历史成功率)+Meta(质量趋势) 加权融合生成代理决策。自调节闭环（3 低分降级+缩量+通知 / 5 高分提信+减 checkpoint）。为什么不是调 token（LLM 不可控/用户不理解/只影响单次）。

**设计意图**: 这是"驾驭自治"的哲学——**控制结构而非 token**。三个要点:
1. 结构性约束（分支数/深度）比 token 预算更可控；
2. 用户不选时，Profile+Behavior+Meta 三路信号融合（对应我们哲学: 画像+行为链+元认知协同）；
3. 自调节是"温度系统 + 参数自适应"的组合（3 低分降级 = 冷却；5 高分提信 = 升温）。

**哲学定位**: 与 PARADIGM 的"温度系统（模拟人+LRU+时空局限）"、"参数自适应（反馈+步长+最值范围）"、"行为链（历史成功率）"直接对应。设计文档作者显然吸收了这些思想。

**实现落差**: **零落地**。没有控制面板、没有 Profile/Behavior/Meta 融合、没有自调节（MetaFeedback 死代码且 check_degradations 无副作用）。

**执行解读**: 这节优先级**低于** P0 执行主干。建议分两步: P2 阶段先做"控制面板参数化"（把深度/严格度/广度/决策模式接进 engine.build 和 diverge/converge 的调用参数）；P3 阶段再做"三路融合 + 自调节"（依赖 Meta 闭环 P1 先有真实数据）。

### §十四 四段传递协议（L463-604）

**原文**: 14.1 全生命周期时序（U→R 选策略→B 建图→[LLM_DRIVEN: 发散/学习/收束/PlanGate]→ConstraintTree→D 逐 Tick→E 执行→L EventLog→M 消费→回写 R）；14.2 BlueprintDAG schema（nodes/edges/strategy/confidence/rationale + node/edge 定义）；14.3 EventBus 订阅表（8 subject: pcr.route/intent.split/context.assemble/subgraph.compile/profile.load/llm.reply/meta.audit/behavior.learn，Tick 0/1/2/async，同 Tick 并行跨 Tick 串行）；14.4 ExecutionAudit + Meta 回写接口（update_strategy_weights/suggest_blueprint/trigger_degradation）；14.5 学习→设计（权重调整/模板建议/节点修正）。

**设计意图**: 四段协议是**完整闭环的数据契约**:
- 设计→工程: BlueprintDAG schema（已实现 models.py ✅）；
- 工程→执行: 订阅表（**未实现**——这是 EventBus 的接线图）；
- 执行→学习: ExecutionAudit（已实现但无人消费）；
- 学习→设计: 权重/模板/节点修正（部分实现但无调用方）。

**关键设计点**（订阅表 14.3）: 8 个 subject 按 Tick 分组——Tick0（pcr/intent 并行）、Tick1（context/subgraph/profile 并行，依赖 Tick0）、Tick2（llm.reply）、async（meta/behavior）。**这是"同 Tick 并行、跨 Tick 串行"的可执行定义**——Decider 只需要按 Tick 发射、收集、再发射。

**实现落差**: 订阅表 8 个 subject 一个都没实现；Decider 直接调 handler 而非发事件。`meta.audit`/`behavior.learn` 的 async 语义没有载体（无后台消费者）。

**执行解读**: 订阅表是施工的核心蓝图。两个实施选项:
- **A. 真 EventBus**（对齐设计）: 用 `core/agent/event/event_bus.py`（v2 asyncio）实现订阅表，各链注册 subscriber。成本高（需处理异步/队列/超时），收益是真正并行 + 解耦。
- **B. 轻量调度**（推荐 P0）: Decider 保持同步循环，但按订阅表语义分 Tick 调用链组件（同 Tick 可 ThreadPoolExecutor 并行），EventBus 留作后续。收益是立即闭环，成本低。

### §十五 DAG 统一可视化（L605-660）

**原文**: BlueprintDAG = TaskGraph 超集；统一前端 TaskPlanningPage；node_type 区分层级（Blueprint 层: pcr/intent/context/subgraph/profile/llm_reply；TaskGraph 层: scan/read/write/analyze/ask_user/explain/fallback）；前后端协议 TaskGraphNode 扩展（params/checkpoint/progress/result）。

**设计意图**: 这是"白盒化（A19）"的实现面——用户可看、可编辑、可拖拽图。Blueprint 层节点可展开为子 task_graph（嵌套树结构，与执行层设计一致）。

**实现落差**: 前端无 TaskPlanningPage；`v3_session_api` 有 task-graph 读写端点（L386-423）+ dag-edit（L344-378）✅，但节点类型协议没落地（task_graph 的 node_type 与蓝图 chain 无映射）；Blueprint 层→task_graph 层展开机制无。

**执行解读**: 这节是 P1+ 的"人机协作"交付，依赖 PlanGate 先接（有暂停才有展示）。施工时先做后端协议（node_type 映射 + checkpoint 字段下发），前端渲染可后置。

---

## 二、设计的核心决策分析（6 个关键决策点评价）

### 决策 1: "LLM 建图、引擎跑图"分离 —— ✅ 正确且必要
这是全文的地基，被 LangGraph/BatchDAG 验证。DialogMesh 的问题从来不是理念，而是引擎没建。**维持**。

### 决策 2: 5 策略矩阵 + 三个 Level —— ✅ 超集设计，但 Level2 语义需修正
把"LLM 自由度光谱"参数化是超越单家的正确做法。但实现把 Level2 做成"一次性全图 override"（伪 Level3），需决策是修正为"分叉点路由"还是"checkpoint 询问"。**建议后者**（成本/延迟可控）。

### 决策 3: LLM_DRIVEN 默认禁用 + 四保护 —— ✅ 正确的风险控制
与"限制自由度=提升可靠性"的行业结论一致。实现四缺三（只有 Budget）。**施工时 LLM_DRIVEN 保持禁用直到保护齐备**。

### 决策 4: 热冷分离（SkillRegistry 快 / Meta 异步学）—— ✅ 正确但依赖学习管道
热冷分离本身对，但闭环依赖 EventLog→Meta→权重的数据管道。管道不存在 → 学习是死代码。**先做执行（产生真数据），再做学习**。

### 决策 5: 订阅表（EventBus 8 subject）—— ✅ 设计精细，实现两难
订阅表是"同 Tick 并行"的可执行定义。但真 EventBus 成本高（asyncio/队列/超时）。**P0 用轻量调度（B 方案），订阅表作为架构目标保留**。

### 决策 6: 控制面板（结构约束 > token）—— ✅ 思想正确，落地最远
调深度/严格度/广度/决策模式是"用户可理解的驾驭"。实现零落地。**P2 阶段接参数化，P3 接三路融合**。

---

## 三、设计的内在张力与未决问题（设计没回答的）

| # | 张力 | 设计立场 | 未决问题 |
|---|------|---------|---------|
| T1 | 真 EventBus vs 轻量调度 | 设计画了订阅表 | 要不要在 P0 引入 asyncio EventBus？还是同步调度先闭环？（建议后者） |
| T2 | Level2 真分叉 vs checkpoint 询问 | 设计写了 conditional_edges | 每步问 LLM 的延迟/token 成本是否可接受？（建议 checkpoint 询问） |
| T3 | RECOVERY 是构建期还是执行期 | 设计写"失败重试→替换子图"（执行期） | 实现把 RECOVERY 用在构建期约束失败——语义错位，谁修？ |
| T4 | Meta 闭环的部署形态 | 设计说"异步不阻塞" | 谁跑消费循环？同进程后台线程 vs 独立服务？（行为链/元认知施工时统一决策） |
| T5 | 学习状态持久化 | 设计隐含权重表 | SkillRegistry 权重纯内存，重启丢失——要不要持久化（对齐 git 式一致性）？ |
| T6 | 前端统一渲染 | 设计画了 TaskPlanningPage | 后端 node_type 协议先落地，前端后置？（建议） |
| T7 | 与第二运行时（CLI StateMachine）的关系 | 设计没提 | 蓝图 Decider 与 CLI 的 DeciderStateMachine 是两套——是统一还是明确分工？（建议: 蓝图管"构建+业务链执行"，StateMachine 管"运行时阶段路由"，接口对齐） |

---

## 四、完整执行实施规划

> 原则（对齐用户偏好）: 质量优先、非简化、先审计后施工、真断言测试、白盒化、可回溯。
> 主方向: **构建层已达标（修 bug 即可），执行层是施工主体**。执行层形态已拍板为**混合式**（详见 §七 决策记录）: 同步聚合段走 DAG 直接调用（白盒/可回溯/类型安全），异步消费段走事件广播（组合/解耦/契合信息消费），EventLog 全量记录（git 式可回溯）。关联链/元认知两个"全连接"模块先以独立服务形态接入，防广播风暴。

### P0 — 执行最短路闭环（构建→执行真连通）

**目标**: `build(DAG)` → `decider.execute` 产生真实链输出（pcr/intent/context/subgraph/profile），`llm_reply` 真调 LLM，无伪造数据。

| 改动 | 文件 | 验收 |
------|------|------|
| 修复全局模板单例污染 | `engine.py`（deepcopy + strategy 不覆盖） | HYBRID 后 BUILTIN_TEMPLATES 不变（对抗测试） |
| 执行器改混合式 | `executor.py`: 同步聚合段（pcr→intent→context/subgraph→llm_reply）直调链组件（复用 `cli/registry.py` 注入模式）；异步消费段（profile/behavior/meta/association）发事件广播；EventLog 全量记录 | 节点输出真实 route/subgraph；同 Tick 并行；事件可回溯；删除关键词 fallback |
| 删伪造数据 | `_handle_pcr/_handle_intent/_handle_profile` fallback 改显式 `{"status":"unavailable"}` | 无假画像/假 PCR/假 Intent 进 prompt |
| llm_reply 真调 switch | `_handle_llm_reply` 复用 v3_session_api Phase 4 调用 | llm_reply 返回真实文本 |
| 生产意图注入 | `v3_session_api` 传真实 intent（或执行器直读 PCR/Intent 结果） | 5 模板可被选中（不再恒 general_chat） |
| 同 Tick 拓扑序 | `decider.py`/`executor.py` 同 Tick 内按依赖迭代 | 乱序定义不丢节点（对抗测试） |
| converge 防崩 | `float()` try/except → None 回退 | 坏 LLM 输出不崩溃 |
| 契约测试 | `tests/test_blueprint_v2.py`（模板不可变/混合执行/无伪造/llm 真实/拓扑/事件记录） | 全绿且对抗性 |

### P1 — PlanGate + 意图链条 + Meta 闭环起步

**目标**: 人工审核可暂停；学习闭环有真实数据源。

| 改动 | 文件 | 验收 |
------|------|------|
| PlanGate 暂停 | `executor.py` 检查 `node.checkpoint` → 返回 `pending_review` | checkpoint 节点不执行、结果可 resume |
| CorrectionJournal 写入 | 审核结果进行为链/EventLog | 有记录 |
| Meta 消费循环 | `meta_feedback.py` 后台线程订阅 EventLog → consume → update_weight（先修权重公式） | 3 低分真实降级（registry 权重变化，副作用） |
| 权重公式修 base | `skill_registry.py` `base × success_rate` | LLM_DRIVEN 一次成功不再反超 |
| 学习状态持久化 | 权重表存 `data/`（对齐 git 式一致性） | 重启不丢 |

### P2 — 控制面板参数化 + 约束补齐 + 执行沙箱

**目标**: 结构约束可调；安全/权限约束齐备；执行接真实沙箱。

| 改动 | 文件 | 验收 |
------|------|------|
| 控制面板参数 | `engine.build(explore_depth, strictness, learn_scope, decision_mode)` 贯穿 diverge/converge | 参数生效且可 CLI 调（`dm blueprint config set`） |
| 安全/权限约束 | `ConstraintChecker` 加 is_destructive → checkpoint、capability 检查（复用 `execution/permissions.py`） | 破坏性节点必须审核 |
| 执行接沙箱 | 蓝图执行结果 → `ExecutionPipeline`（sandbox/diff） | 有真实执行产物 |
| 7-Tree 并行 | 同 Tick 用 ThreadPoolExecutor（异步 I/O 链） | 并行度 >1 且无竞态 |

### P3 — 自调节闭环 + 模板进化 + 前端协议

**目标**: 3 低分降级/5 高分提信真生效；模板可进化；后端 node_type 协议落地。

| 改动 | 文件 | 验收 |
------|------|------|
| 自调节 | MetaState 触发 → 真改 engine 默认参数 + 通知 | 降级后请求策略变化 |
| 模板建议 | suggest_blueprints → CLI 展示可接受为内置模板 | 新模板可注册 |
| node_type 协议 | 蓝图 chain ↔ task_graph node_type 映射 + checkpoint 字段下发 | `dm task-graph` 返回含蓝图层 |

### P4 — EventBus 订阅表（可选，架构目标）

**目标**: 若 P0-P2 证明需要真并行/解耦，按 §14.3 订阅表接 `core/agent/event/event_bus.py`（v2 asyncio）。

| 改动 | 文件 | 验收 |
------|------|------|
| 8 subject 订阅表 | 各链注册 subscriber（pcr.route/intent.split/...） | 同 Tick 真并行，跨 Tick 依赖正确 |
| async 消费者 | meta.audit / behavior.learn 后台订阅 | 学习不阻塞请求 |

### 施工顺序依赖图

```
P0（执行真连通，本轮主战场）
  └─ P1（PlanGate + Meta 起步）     ← 依赖 P0 产生真实执行数据
       └─ P2（控制面板 + 约束 + 沙箱） ← 依赖 P1 的权重/审核
            └─ P3（自调节 + 进化 + 协议）← 依赖 P2 的参数化
                 └─ P4（EventBus，可选） ← 依赖 P0 的调度稳定
```

### 风险与对策

| 风险 | 对策 |
------|------|
| 同步段与事件段边界漂移 | 按"依赖性质"定边界: 需聚合结果才能继续 → 同步调用；可延迟消费的广播 → 事件订阅。边界固化在 §14.3 订阅表 + 调用表双契约中 |
| 事件风暴（关联链/元认知全连接） | 这两个模块**不做全广播订阅**，以独立服务形态（定向通道/专用队列）接入——见 §七 决策记录 |
| 事件可回溯性 | 每个事件写 EventLog（subject/payload/来源/时间），回溯读事件日志（git 式），不依赖调用栈 |
| llm_reply 双调 LLM（蓝图 + v3_session_api Phase 4） | P0 决策: 蓝图 llm_reply 只产出"管线摘要"，最终回复仍由 Phase 4 完成；或 Phase 4 删除、蓝图全权（需拍板） |
| 生产意图恒空（5 模板选不到） | P0 执行器直读真实 PCR/Intent 结果，不依赖 v3_session_api 传参 |
| 两套运行时（API 空壳 vs CLI 真） | P0 只改蓝图执行器（API Phase 3.5 段）；CLI StateMachine 不动，接口对齐即可 |

---

## 五、与项目哲学的呼应（PARADIGM 映射）

| 设计章节 | 对应哲学 | 施工含义 |
---------|---------|---------|
| §一 建图/跑图分离 | A19 白盒化 | DAG 是可检视产物，CLI 可操作 |
| §九 热冷分离 | 元认知（统筹/裁决/复盘） | SkillRegistry 权重 = 元认知裁决物 |
| §十一 四保护 | 竞争吸收 + 收敛/发散 | LLM_DRIVEN 是"特殊模式"非默认 |
| §十二 掩盖约束法 | 伪二阶抽象 + DMN/ECN | diverge 真正掩盖上下文 |
| §十三 结构约束 | 温度系统 + 参数自适应 | 控制迭代/层级而非 token |
| §十四 四段协议 | 可回溯 + git 式一致性 | EventLog/audit = 溯源地基 |
| §十五 统一可视化 | A19 白盒化 | 用户可编辑图，白盒可操作 |

---

## 六、结论

1. **设计文档质量高**——理念（建图/跑图分离）、风险控制（§十一）、闭环契约（§十四）都是正确且前沿的；它与我们的哲学体系同源，**不需要重写**。
2. **核心缺口在执行层**——构建层已达标（修 bug 即可），执行层（Decider/EventBus/PlanGate/Meta）是施工主体；设计自己列的"现状诊断"（§三）和"差距表"（§七）就是施工清单。
3. **施工顺序**——P0 执行最短路（含子图接入，混合式执行）→ P1 PlanGate+Meta 起步（含关联链/元认知 EDA 接入）→ P2 参数化+约束+沙箱 → P3 自调节+进化。LLM_DRIVEN 在四保护齐备前保持禁用。
4. **待拍板点**——执行层形态已拍板（混合式，§七）；剩余: Level2 语义（分叉路由 vs checkpoint 询问）、llm_reply 归属（蓝图全权 vs 外部化）——是施工前必须先定的方向。

---

## 七、执行层形态决策记录（2026-08-02 讨论拍板）

### 7.1 决策背景

原方案二选一（直接组件调用 vs EventBus 真并行）讨论后升级为**混合式**。核心论据:

1. **"蓝图"不是"编排器"**——蓝图的本意是"多组合"（多种模块按需装配），不是中心化逐个调度。组合天然适合 pub/sub（谁需要什么自己订阅），编排才需要 DAG 执行器。
2. **EDA 契合"信息消费"本质**——模块间关系是"消费产出"（PCR 的 route 被 intent/context/subgraph/profile 同时消费），不是"谁调用谁"的线性链。事件表达"需关系"，DAG 表达"给关系"，后者更贴合多对多信息流。
3. **EDA 不是黑盒**——git 式 EventLog 记录可解决可回溯性: 事件流本身就是可回溯历史（subject/payload/来源/时间），能看到"谁消费了、谁没消费"，信息量大于调用栈。
4. **模块强耦合 → 事件解耦是自然形态**——DialogMesh 模块间关联性强、耦合深，发布-订阅把"谁需要什么"从装配表里解放出来，新模块即插即用。

### 7.2 拍板方案: 混合式

按**依赖性质**分，而非按 Tick 分:

```
同步聚合段（需等待全部结果才能继续）→ DAG 直接调用
  pcr → intent → context/subgraph → llm_reply（聚合所有输出做最终回复）
  白盒/断点/类型安全/fan-in join 原语

异步消费段（消费广播、可延迟、可重试）→ 事件广播
  route/intent/context 产出 → 事件 → profile/behavior/meta/association 订阅消费
  新模块即插即用，冷路径不阻塞热路径

全量记录 → EventLog（git 式）
  每个事件/调用都写日志，回溯/审计/学习的地基
```

### 7.3 关联链 / 元认知: 独立服务形态（防广播风暴）

关联链与元认知**几乎和所有模块都有关系**——若两者全广播订阅所有 subject，会产生广播风暴（N 模块 × 双向 = N² 连接）。拍板:

```
关联链 / 元认知 = 独立服务（定向通道/专用队列），不做全广播订阅

  各模块产出 → 写 EventLog（一次，不广播）
  关联链     → 按需消费（拉取/定向投递其关心的主题，L1→L2.5 漏斗）
  元认知     → 拉取 EventLog 全量，周期扫描（冷路径，天然契合）

  ↔ 呼应子图反哺的 C/S 拍板: 同步拉取用 C/S（直接调用/pull），异步通知才用事件
```

**为什么这两个对 EDA 契合度高**（即使不用广播）: 它们是"信息消费者/监督者"——关联链消费所有模块产出做关联推理，元认知消费执行数据做裁决复盘。EDA 的"订阅-消费"语义天然表达这种关系；定向通道（point-to-point）是 EDA 的 work-queue 模式，既保留消费语义，又避免广播风暴。

### 7.4 施工时序

```
① DAG 骨架先做完全部（同步聚合段 + 事件广播段跑通，EventLog 有真实数据）
   → 同步做②
② 关联链 / 元认知 EDA 接入（独立服务 + 定向通道）
   → 依赖①的 EventLog 真实产出 + 事件流稳定
③ 其余异步消费者（behavior/meta 权重学习）按需接事件
```

与 P0→P1 顺序一致: 先让执行产生真实数据，再让"全连接"模块消费它。

### 7.5 DAG 执行快照 = 溯源 + 子图逆向扩展（2026-08-02 追加拍板）

**核心洞察**: 执行结构本身就是溯源结构。Decider 执行时每个节点输出存入 `all_outputs`（node_id → output），加上 DAG 边（from→to）即构成**带数据的执行图**——溯源不需要单独建表，DAG 边就是溯源关系，节点输出就是溯源内容。这直接承接 DESIGN_SUBGRAPH §11 的溯源分层，且提供现成的图结构承载它。

**三个价值点**:
1. **逆向扩展候选现成**: 从任意节点沿入边逆向走，得到"该输出**实际基于**哪些中间结果"（`llm_reply_4 ← subgraph_3 ← context_2 ← intent_1 ← pcr_0`）——高置信候选，非猜测；
2. **跨请求引用**: DAG 快照持久化（EventLog，git 式）后，"继续你刚才的分析"可定位历史请求的节点并沿边取上游——多轮溯源闭合成环；
3. **预期 vs 实际互验**: 子图 = 预期上下文，DAG 轨迹 = 实际用到的上下文——实际节点反哺子图（哪些预期对了/没用上），是"子图反哺 C/S 通道"的天然数据源。

**三个边界**:
- 内存 vs 跨请求: `all_outputs` 是局部变量，跨请求须持久化——每个节点写**摘要 + 指针**（不写全文，对齐 tracer 的 chain_summary 思路）；
- 逆向粒度: 节点输出类型不一（route dict / SubgraphContext / profile_text）——需统一"可检索视图"（文本摘要 + 概念 + 引用），否则逆向拿到异构结构；
- 接口: 新增子图扩展第三种原语 `expand_from_dag_trace(dag_snapshot, target_node)`——沿边收集上游输出 → 提取概念/引用 → 交现有 `expand_from_graph` 融合（与 `_expand_from_event` trace walk 同思路，源从事件变为 DAG 轨迹）。

```
DAG 执行 → 节点输出摘要写入 EventLog（git 式，含边引用）
子图扩展 → expand_from_dag_trace(dag_snapshot, node) 逆向收集
多轮    → 历史快照 = 可检索的溯源库
```

**施工落点**: P0 的"EventLog 全量记录"即 DAG 快照的地基；子图 `expand_from_dag_trace` 随 P0 子图接入一并实现（复用已施工的 v4 子图扩展原语）。

### 7.6 模式空间设计: 路由模式 + 回复模式（2026-08-02 追加拍板）

**核心原则**: 不是二选一，是**模式空间**——默认值 + 显式覆盖。Level2 语义与 llm_reply 归属统一成同一个设计语言。

**路由模式**（决定"何时问 LLM"，`BlueprintNode.params.route_mode` / DAG metadata 可配，进控制面板 §十三 决策模式维度）:

```
mode=template    → 零 LLM 介入（Level1 语义；查天气/数据搜索等已知路径）
mode=checkpoint  → 构建期一次 LLM 调整 + 执行期决策点询问（默认，综合最好）
mode=step        → 每步分叉路由（超高自由度；代价=成本/时间；特定场景显式启用）
```

step 模式的两个设计连接:
1. **截断点 = 执行中人机协作点**——用户在决策边节点暂停，直接与 LLM 沟通调整（PlanGate interrupt() 的运行时版，白盒 A19 的执行态体现）;
2. **分叉点 = 多 agent/联邦启动点**——候选路径可联邦并行评估或异步探测后收束（连接已有联邦/多 agent 设计）。

**回复模式**（决定"回复行为由谁定义"，`node.params.reply_mode`）:

```
mode=llm      → LLM 基于 DAG 聚合上下文回复（默认；复用 v3_session_api Phase 4 的 switch 调用）
mode=template → 确定性模板回复（快速通道；Phase 4 可跳过）
mode=user     → 用户画的 JSON 行为（白盒，行为一等公民）
mode=bp       → 业务流模板（用户提供的蓝图，SkillRegistry 可注册改造，§14.5 模板进化机制）
```

**执行器含义**:
- `route_mode` 决定"何时问 LLM"，`reply_mode` 决定"回复行为谁定义"，两者独立可配;
- 用户截断 = CLI/前端对执行中 DAG 的操作，需要执行器支持"暂停-协商-恢复"——复用 PlanGate 的 checkpoint/resume 机制，触发点从"节点前"扩展到"边决策点";
- 成本（经济/时间）是 step 模式的**特性不是缺陷**——在探索性任务（因果推理 L5、新领域）正是所需，与 §十一"LLM_DRIVEN 特殊模式"同构（step = 执行级 LLM_DRIVEN）。

### 7.7 统一异步预加载（2026-08-02 追加拍板）

**问题**: 模型冷加载（BGE/sentence_transformers 等）首次调用 17-21s 延迟，跨模块重复——不该等用户用到才加载。

**方案**: 统一异步预加载——启动时后台线程预热全部模型消费者，首次请求不付冷加载成本。

```
prewarm_models(blocking=False)  # 后台 daemon 线程，接入 start_engine + bootstrap
  ├── SemanticEncoder.preload(blocking=True)   → 全局单例（get_encoder 用户）
  ├── ModelService.warm_up()                   → 复用同一全局单例（一份 BGE 内存）
  └── PCRRouterV2._load_mood_vectors()         → PCR 类缓存（bge-small-zh-v1.5）
```

**关键设计**: `ModelService.warm_up` 复用 `semantic_encoder.get_encoder()` 全局单例（而非自建 `SemanticEncoder()`）——避免双份 BGE 驻留内存（实测 `svc._encoder is get_encoder()` = True，warm encode 135ms vs 冷 16.8s）。

**工程落地**:
- `core/infrastructure/model_service.py`: `prewarm_models()` + `ModelService.warm_up` 复用单例;
- `core/agent/cli/engine.py` start_engine + `core/agent/orchestrator/bootstrap_v6.py`: 启动时 `prewarm_models(blocking=False)`;
- `core/agent/config/discourse_config.py`: 修复 `Path.exists()` 在 uv 3.13 + `~/.config` ACL 受限时抛 PermissionError（.venv 环境预热链路断根因）。

**已知边界（P1 模型统一）**: PCR 的 fastembed 分支（bge-small-zh-v1.5）与 SemanticEncoder（bge-small-zh）双模型并存——无缓存+网络受限环境 fastembed 联网重试 5 次（~5-8s）。统一到单模型（SemanticEncoder 或 ModelService 支持 v1.5）留 P1。
