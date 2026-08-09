# 第一轮执行 — G1 三套决策归一 + G6 冲突预筛（2026-08-03）

> 状态: 第一轮执行完成。G1 给归一方案（哲学层），G6 完成 51 项冲突预筛。
> 方法: PARADIGM 公理（A1-A25/P1-P28）对照 + 三套决策器源码实读。

---

## 一、G1 三套决策器归一（哲学层分析）

### 1.1 三套（+1 设计）实况

| 决策器 | 位置 | 模式 | 现状 |
|---|---|---|---|
| GlobalDecider | state/global_decider.py | Command→Event→evolve→State（防广播风暴，每次只产 1 Event）| ⚠️ 精度修正: runtime/engine.py:194 类内声明 None 且从未赋值 → 类属性恒 None；但 CLI 两条 registry 路径（cli/registry.py:267 required=True + subsystem_registrations.py:76）都会装配实例化 → **被实例化但 runtime 类不用它**（与 CausalPlanner 真零实例化不同型）|
| DeciderStateMachine | event/statemachine.py | PipelinePhase 阶段机（8/13 handler 注册，缺 5）| 半实现：handler 输出不传下游 + 无 handler 阶段 result 残留 |
| BlueprintDecider | blueprint/decider.py | 薄门面 → BlueprintExecutor（同步 DAG + EventLog trace 混合）| 已工作（agent_native.process_dag + v3_session_api 真调用）|
| CognitiveScheduler（设计）| DESIGN_COGNITIVE_SCHEDULER | 任务级调度（谁/何时/多久/优先级）| 纯设计，无实现 |

### 1.2 哲学分析（它们不是"同一层竞争"，是四层分工）

```
用 PARADIGM 分层:
  编排层（用户可编辑 DAG）  ← BlueprintDecider     [A19 白盒化: 用户可编排]
  执行层（阶段流水线）      ← DeciderStateMachine   [A11 可回溯可修正 + A16 冷热编排]
  状态层（跨链一致性）      ← GlobalDecider         [A17 记录即一致性 + 防广播风暴]
  调度层（资源分配）        ← CognitiveScheduler    [A16 冷热: 快/慢/深路径]

关键洞察: 四者是"不同抽象层"，不是四选一。
  现状问题不在"选谁"，而在:
  ① GlobalDecider 被 CLI registry 实例化但 runtime 类属性不用它
     （runtime/engine.py:194 声明 None 从未赋值；registry 装配的实例未注入类）
  ② DeciderStateMachine 半实现（输出断链 X4/X5）
  ③ BlueprintDecider 实际承担了主执行（薄门面背后的 BlueprintExecutor）
  ④ CognitiveScheduler 纯设计（未来态）
```

### 1.3 归一方案（哲学层建议，待拍板）

```
G1 建议: "一主两辅一未来"分层保留
  主路径:   BlueprintDecider（DAG 编排，白盒，已工作）——用户可编辑的顶层
  执行宿主: DeciderStateMachine（阶段流水线）——修复 X3/X4/X5 后作为 DAG 节点的执行载体
  状态层:   GlobalDecider（防广播风暴）——已有 registry 实例，注入 StateMachine
            作为状态底座（不是并行的第二个决策器，是状态源）
  调度层:   CognitiveScheduler——未来态，当前不建（与 MultiTier 精度谱系同域，待 A16 深化）

哲学依据:
  A19 白盒 → BlueprintDecider 保留（用户可改 DAG）
  A11 可回溯 → StateMachine 保留（阶段可回放）
  A17 一致性 → GlobalDecider 的 Command→Event 模式保留（事件溯源基底）
  A16 冷热 → CognitiveScheduler 是冷热编排的调度实现（未来）
  → 四层不冲突，是 A19/A11/A17/A16 的各自落点；冲突的是"哪层拥有主循环"
```

### 1.4 待拍板焦点（收窄为 2 项）
```
G1-A  主循环归属: BlueprintDecider(DAG) vs DeciderStateMachine(阶段机)
      → 建议: 阶段机作为 DAG 节点的内部执行，主循环归 DAG（用户可编排优先）
G1-B  GlobalDecider 实例化: runtime 注入 or 由 StateMachine 内部持有
      → 建议: 复用 CLI registry 已装配的实例，注入 StateMachine 内部持有
        （状态底座，不暴露为新决策器；避免重复实例化）
```

---

## 二、G6 51 项冲突预筛（PARADIGM 对照）

### 2.1 预筛结果统计

```
🔴 真冲突（需拍板）: 10 项
🟡 伪冲突（哲学可消解/不同层分工）: 27 项
⚪ 实现缺口（非冲突，是未接线/未实现）: 14 项
→ 与用户预估吻合（约 60% 伪冲突，真冲突 10-15 项）
```

### 2.2 🔴 真冲突（10 项，进拍板池）

| # | 冲突 | 消解依据缺失 | 建议 |
|---|---|---|---|
| B1-2 | 三套调度候选 | 主循环归属未定 | 并入 G1-A |
| B1-6 | 单 Observer vs 多 agent/联邦 | 并发模型未拍板 | 与蓝图多 agent 讨论合并 |
| B2-2 | 五区/四区存储 vs 6 套并存 | 存储架构未拍板 | 并入 G10 |
| B2-5/B6-5/B8-3 | 进程内 EventBus vs NATS 基础设施 | 基础设施选型未定 | 并入 X1（NATS 修复方向）|
| B2-6 | 统一图存储 vs ENGINEERING_PERSISTENCE | 双蓝图 | 并入 G10 |
| B4-1 | 服务层双蓝图 + 两处实现 | 服务层归一 | 单独议题（B4）|
| B4-5 | CLI vs RPC | 架构走向 | 单独议题 |
| B8-4 | 网关 vs 进程内 provider | 双路由 | 单独议题（LLM 认知层）|
| B8-7 | rewarder EMA/ABL vs reward_signal 双轨 | 奖励机制 | 并入行为链 |
| B7-3 | 融合器 vs 双决策器 | 决策仲裁 | 并入 G1 |

### 2.3 🟡 伪冲突（27 项，哲学可消解——列出消解公理）

```
B1-1 四树空间 vs 树图一体        → A5 树是推理工作台 + A2 递归地图（同一哲学两表述）
B1-3 调度器 vs EventBus          → A16 分层（调度层 vs 事件层不同层）
B1-5 统一关系本体 vs 分层漏斗    → A2 颗粒度（分层是内部递归）
B1-7 模块内谱系 vs 模块间编排    → A16 冷热（同构不同尺度）
B2-3 锚点定位归属               → A25 召回哲学（机制统一，归属是组织问题）
B2-4 ES 全量 vs Phase6 切片      → 渐进（全量是目标、切片是路径）
B3-1 对象投影 vs 子图编译        → A8 表达形式 + A11 渲染管线分工
B3-2 锚点检索三份               → A25 归一（同一机制三份表述）
B3-3 Hypothesis Pool vs L2.5     → A4 信念竞争（同一机制不同代）
B3-5 NoiseSpan vs PCR zone       → A2 颗粒度（局部标记是 zone 细粒度）
B3-6 INJECTION vs sanitizer      → A21 护栏分工（可归一）
B3-7 World View vs Subgraph      → A2 递归地图（世界模型=子图连续缩放）
B5-2 图编辑三份                 → A19 白盒统一交互规范
B5-3 子图编辑 vs 审计           → A19 白盒方向一致
B5-4 前端 CLI 双通道            → A19 多通道
B6-2 文档树 vs L5               → A2 静态场 vs 记忆分层
B6-3 可观测 vs Monitor           → A19 白盒监控统一
B6-4 EventLog vs ES             → 演进链同一
B7-1 FoA vs Observer.attention   → A1 视角（注意力是模块属性）
B7-4 L1 摘要 vs 对话树摘要       → A2 不同域摘要分工
B7-5 负知识库 vs ConstraintTree  → A21 一套约束空间
B7-6 HARD_BLOCK do-calculus     → A22 已定义分工
B8-1 分布式 vs 单进程           → A16 渐进（规模触发）
B8-5 压缩调研 vs L5             → A20 竞争吸收输入
B8-8 MCP 边界                   → 边界声明（非冲突）
```

### 2.4 ⚪ 实现缺口（14 项，非冲突——直接进施工/修复队列）

```
B1-8 CognitiveWorkspace 未实现   → 实现缺口
B2-1 XML 卡 vs memory 孤儿       → 接线缺口
B2-7 FactStore 批量写            → 缺陷修复
B3-4 多 Analyzer consumer_marks  → 未实现
B3-8 ObjectRuntime/Projection    → 未实现
B4-2 /chat /parse /execute 简化  → 渐进实现
B4-3 Clarification 契约          → 接口对齐
B4-4 CLI 目标 vs 实现            → 覆盖度
B5-1 前端 15 页接线              → 接线（FE 系列）
B6-1 DIL vs document             → 半实现
B7-2 融合简化 vs 三阶段          → 渐进实现
B8-6 predictor 四维 vs 实现      → 覆盖度
（另含 FE-1~6 / SD-1~3 / X9~X14 等已列修复项）
```

---

## 三、第一轮输出（待确认）

```
1. G1 归一方案: "一主两辅一未来"（BlueprintDecider 主 + StateMachine 宿主 +
   GlobalDecider 状态底座 + CognitiveScheduler 未来）——收窄拍板焦点为 G1-A/G1-B
2. G6 预筛: 51 项 → 真冲突 10 / 伪冲突 27 / 实现缺口 14
3. 伪冲突消解依据已标注（PARADIGM 公理），可直接进消解文档
```

---

## 四、G6_PHILOSOPHY_FILTER_20260803.md 评估（第一轮后复核）

> 按用户要求"第一轮执行完再去看"。结论: 整体质量高，但有三处需修正合并。

### 4.1 与第一轮的一致性
```
✅ 伪冲突比例吻合（G6: 67% vs 第一轮: 60%+，同为"约 60% 伪冲突"）
✅ 真决策 12 项收得比第一轮更准（补上 B2-3 锚点归属 / B5-3 子图编辑 / B8-4 网关）
✅ B8-2 降级为已答 + A17/A2/A24 三重依据（与 README_INDEX §四一致）
✅ G 系列裁决表简洁，拍板顺序合理
```

### 4.2 需修正的三处
```
① 聚类 8 不同源（必须合并）:
   README_INDEX 聚类 8（我写）: I1-1 EventBus / I1-2 三套决策器 / I1-3 双 Provider /
     I1-4 双 Service / I1-5 三 chroma / I1-6 四 WS（偏"设计层并存"）
   G6 聚类 8（另一批）: I1-1 EventBus / I1-2 双 BeliefAccumulator / I1-3 三处
     CausalSubstrateAdapter / I1-4 两套 ocean_profile / I1-5 双 AssociationSubscriber /
     I1-6 双 TrainingFeedbackLoop（偏"实现层尖锐冲突"，已核实全部真实存在，
     且归因到 F1-F8/D7/行为链 C1 等已有拍板）
   → 合并为完整实现↔实现清单（10 项），拍板时不能漏任何一半

② "已答"标签偏激进:
   G4 白盒"FE-1 一行 include_router" —— 实际需 init(engine) 注入 + 前端 404 提示，
     不是一行；FE-1 是 P0 级真实断裂，应列为真决策而非纯已答
   G2/G7/G8/G9 —— 是"用户方向/偏好"，建议标"方向已定，待全局确认"而非"已拍"

③ 缺一项: 真决策 12 项未含 FE-1（白盒编辑 API 未注册）本体
```

### 4.3 修正动作（已执行/建议）
```
① 合并聚类 8 → 见 README_INDEX §二 聚类 8（追加 G6 侧 5 项实现冲突）
② G4 升级: FE-1 从"已答"升为"真决策（P0）"，施工项见 FRONTEND_IMPL_AUDIT FE-1
③ G2/G7/G8/G9 标注改为"方向已定（用户），待全局确认"
```
