# 全局哲学消解预筛 — FINAL（2026-08-03）

> 定位: 糅合 `G6_PHILOSOPHY_FILTER_20260803.md`（61 项消解表，主体）
> 与 `ROUND1_G1_G6_EXECUTION_20260803.md`（G1 四层分工方案 + 精度修正）
> 后的**唯一拍板依据**。两份源文档保留为过程记录。
> 方法: G1-G10 + B 系列 51 项逐一对照 PARADIGM A1-A25/P1-P28 + §5 元规则。
> 结论: 61 项 → 已答/伪冲突 45 (74%) · 真决策 8 (13%) · 暂缓/规模 3 (5%) · 施工 4+
> （2026-08-04 更新: G1+G3 合并、G10/B2-3/B4-1/B4-5 定案 → 真决策 13→8）

---

## 〇、相对 G6_FILTER 的修正（3 处，精度实读）

```
① G1 精度: GlobalDecider 不是"从未实例化"——
   runtime/engine.py:194 类内声明 None 且从未赋值（类属性恒 None）；
   但 CLI 两条 registry 路径（cli/registry.py:267 required=True +
   subsystem_registrations.py:76）都会装配实例化 → "被实例化但 runtime 类不用它"。
   与 CausalPlanner（registry 注册后无人调用）不同型。
② handler 数字: PipelinePhase 枚举 13 个（含 IDLE/DONE），handlers 注册 8 个
   → "8/13 注册，缺 5"（原 8/11 不精确）。
③ FE-1 升级: 白盒编辑 API（/v6/edit/* 5 端点）后端未注册（v6_app 17 项路由无
   api_viz_edit；唯一引用在 un_use/legacy_api.py 且 import 目标不存在）→
   从"已答"升为"真决策（P0）"，施工项见 FRONTEND_IMPL_AUDIT FE-1。
```

---

## 一、G 系列跨模块项（10 项）消解

| # | 议题 | 裁决 | 依据 | 类别 |
|---|------|------|------|:---:|
| G1 | 三套决策/编排归一 | 🔴 **真决策** — 四套并存且非同一层：编排层 BlueprintDecider / 执行层 DeciderStateMachine / 状态层 GlobalDecider / 调度层 CognitiveScheduler（设计）。归一 = 定主循环归属 + 其余适配/归档。见 §六 G1 方案 | A16 冷热 + A19 白盒 + A11 回溯 | 真 |
| G2 | EventBus 背压方向 | ✅ **方向已定（用户）待全局确认** — NEVER drop + 生命周期层（热全量→温减枝→冷摘要）。PARADIGM A17+A2+A24 三重支持；补 GAP-1~3（消费水位线/语义价值载体/可逆推保真度）| A17+A2+A24 | 已答* |
| G3 | 双路径分裂 (A/B) | 🔴 **真决策** — agent_native vs runtime/cli 两套运行时并存。拍: 主路径 = StateMachine（已活），agent_native 降为兼容壳 | A1 + 元规则5 | 真 |
| G4 | 白盒化 vs 前端 404 | 🔴 **真决策（P0）** — FE-1: api_viz_edit 未注册（非"一行 include_router"，需 init(engine) 注入 + 前端 404 提示）| A19 | 真 |
| G5 | 单进程 vs 分布式 | 🟡 **暂缓** — 单进程满足当前；设计保留接口，触发条件 = 节点数/并发阈值（与 G10 一起）| A16 + 元规则5 | 待规模 |
| G6 | 哲学消解预筛 | ✅ 本文件即答案 | — | 已答 |
| G7 | 归档策略 (un_use) | ✅ 方向已定（用户偏好 un_use）+ A17（记录永不可删 → 归档不删除）| A17 | 已答* |
| G8 | 重构执行方式 | ✅ 方向已定 — 索引先行（A2 地图式）| A2 | 已答* |
| G9 | A 类缺口处置 | ✅ 方向已定 — 33 个已读完，吸收进 landscape_read；归档到对应模块 + un_use 清历史 | A17 | 已答* |
| G10 | 存储架构 6 套归一 | ✅ **已定案（2026-08-04）** — 分层策略 + 触发条件（不拍死一个库）: 阶段1 = sqlite_store+graph_store+UnifiedStore(向量首选)+TieredStorageManager(分层启用) 零新依赖；阶段2 = Kuzu（Protocol 新后端）；阶段3 = Neo4j/Milvus（与 G5 同触发）。详见 `G10_STORAGE_DECISION_20260803.md` | A2/A5/A25/A18/A17 | 已拍 |

**G 系列: 真决策 4 (G1/G3/G4/G10) · 已答 4 (G2/G7/G8/G9 标*待确认) · 暂缓 1 (G5) · 预筛本身 1**

---

## 二、B 系列 51 项冲突 — 按聚类消解

### 聚类 1: 决策/编排归一（10 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B1-2 | 三套调度候选 | 🔴 归入 G1 真决策 | — |
| B1-3 | 调度器 vs EventBus | ✅ 伪冲突 — EventBus 是传输, 调度器是决策 (A16) | 分工 |
| B1-7 | 模块内谱系 vs 模块间编排 | ✅ 伪冲突 — 不同颗粒度 (A2) | A2 |
| B7-3 | 融合器+GlobalWorkspace = 第三套仲裁 | 🔴 归入 G1 | — |
| B2-4 | ES+CQRS 全量 vs 关联链切片 | ✅ 伪冲突 — 全量是蓝图, 切片是分期 (A2) | A2 |
| B6-4 | EventLog 雏形 vs ES 蓝图 | ✅ 伪冲突 — 演进同一条链 (A6) | A6 |
| B8-1 | 分布式未来 vs 单进程 ES | 🟡 归入 G5 暂缓 | — |
| B8-2 | EventBus NEVER drop vs 满则丢弃 | ✅ 方向已定 (用户) — 生命周期层, 见 G2 | A17/A2/A24 |
| B6-5 | EventBus"已有"假设 vs NATS 未通 | ✅ 已答 — 归 X1 施工 | — |
| B8-3 | NATS 模式吸收 vs X1 | ✅ 已答 — 归 X1 施工 | — |

**聚类 1: 真决策 2 · 伪冲突 6 · 已答 2**

### 聚类 2: 空间/对象模型（8 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B1-1 | 四树空间 vs 树图一体 | ✅ 伪冲突 — 四树 = 一级视角 (A1), 树图一体 = 实现形态 | A1 |
| B3-1 | 对象+投影 vs 子图编译 | ✅ 伪冲突 — 不同颗粒度 (A2), 可共存 (对象=数据层, 子图=编译层) | A2 |
| B3-7 | World View+RecursiveZoom vs Subgraph | ✅ 伪冲突 — RecursiveZoom = A2 递归缩放直接实现 | A2 |
| B2-3 | 锚点定位+图扩散归属 | ✅ **已定案（2026-08-04）** — 持久化=能力底座（锚点+扩散+RAG 适配），子图=编译服务（召回→组装），执行层双消费（主控子图/子 agent 直连）。见 §八 | A25 |
| B3-2 | 锚点检索三份设计 | ✅ 已答 — 归 B2-3 决策, 三份合一 (同一 A25 机制) | A25 |
| B1-8 | CognitiveWorkspace 容器未实现 | 🔴 真决策 — 归 LLM-1 (认知层接线) | — |
| B7-1 | FoA 注意力 vs Observer.attention | ✅ 伪冲突 — 不同层级 (A1) | A1 |
| B8-5 | 压缩调研 vs L5 落地 | ✅ 已答 — 归持久化 PE-2 施工 | — |

**聚类 2: 真决策 2 · 伪冲突 5 · 已答 1**

### 聚类 3: 记忆/持久化（6 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B2-1 | XML 卡设计 vs memory/ 孤儿 | ✅ 已答 — 归 PE-A 施工 | — |
| B2-2 | 五区/四区存储 vs 6 套并存 | 🔴 归 G10 | — |
| B2-6 | 统一图存储 vs 双蓝图 | 🔴 归 G10 | — |
| B2-7 | FactStore 批量写缺陷 | ✅ 已答 — PE-3 施工 (A18) | A18 |
| B6-2 | 文档树静态场 vs L5 四区 | ✅ 伪冲突 — 静态场是视角 (A1), 四区是存储 (A2) | A1/A2 |
| B1-5 | 统一关系本体 vs 关联链漏斗 | ✅ 伪冲突 — 本体是数据层, 漏斗是处理层 (A2) | A2 |

**聚类 3: 真决策 1 (归 G10) · 伪冲突 3 · 已答 2**

### 聚类 4: 行为链（4 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B1-4 | 模拟引擎 vs 行为链预测器 | ✅ 伪冲突 — 心智理论 vs 统计+DPO 双轨 = A4+A13 | A4/A13 |
| B8-6 | predictor 四维排序 vs 实现覆盖 | ✅ 已答 — 行为链方案 C 施工项 | — |
| B8-7 | rewarder EMA/ABL vs 双轨 | ✅ 已答 — 归行为链施工 | — |
| B7-4 | 行为链 L1 摘要 vs 对话树渐进摘要 | ✅ 伪冲突 — 同一摘要机制 (A2) 两个应用域 | A2 |

**聚类 4: 伪冲突 2 · 已答 2 · 真决策 0**

### 聚类 5: 约束/安全（3 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B7-5 | 负知识库 vs ConstraintTree | ✅ 伪冲突 — NegativeKB=反例集 (A6), ConstraintTree=约束空间 (A12), 不同层 | A6/A12 |
| B7-6 | HARD_BLOCK 需 do-calculus | ✅ 已答 — A22 负向验证, 归关联链 F12 施工 | A22 |
| B3-6 | INJECTION 检测 vs input_sanitizer | ✅ 已答 — A21, 归工程链施工 | A21 |

**聚类 5: 伪冲突 1 · 已答 2 · 真决策 0**

### 聚类 6: 服务层/前端/CLI（6 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B4-1 | 服务层双蓝图+双实现 | ✅ **已定案（2026-08-04）** — 三代归一: 组件保留 + 协议保留 + 层归档 + v6_app 薄中间件层（轻服务层）。见 §九 | A20/A16/A2 |
| B4-2 | /chat /parse /execute 简化 vs 规范 | ✅ 已答 — 归服务层施工 | A20 |
| B4-3 | ClarificationUI 契约 | ✅ 已答 — 归 FE 系列施工 | — |
| B4-4 | CLI 目标态 vs 实现覆盖 | ✅ 已答 — 归 CLI 施工 | — |
| B4-5 | CLI vs RPC 架构走向 | ✅ **已定案（2026-08-04）** — 内核唯一 + 传输可插拔（CLI→REST→MCP→多 agent），顺序 = CLI 补全 → REST 对齐 → MCP 标准化。见 §十 | A16/A19/A17 |
| B5-2 | 图编辑三份设计归一 | ✅ 已答 — 归 FE 系列施工 | — |

**聚类 6: 真决策 2 · 已答 4**

### 聚类 7: 前端接线/LLM/其他（14 项）

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| B5-1 | 前端 15 页需接管线 | ✅ 已答 — FE-5 施工项 | — |
| B5-3 | 子图编辑 = 用户控制权 | 🔴 **真决策** — 归子图施工 (A19 落地) | A19 |
| B5-4 | 前端↔CLI 双通道 | ✅ 伪冲突 — 两个投影面 (A1) | A1 |
| B1-6 | 单 Observer vs 多 agent | 🟡 暂缓 — 归 G5 | — |
| B3-3 | Hypothesis Pool vs L2.5 信念 | ✅ 伪冲突 — 同一信念机制 (A4) | A4 |
| B3-4 | 多 Analyzer 竞争未落地 | ✅ 已答 — 归关联链 Phase 6 施工 | — |
| B3-5 | NoiseSpan vs PCR zone | ✅ 伪冲突 — 输入侧 vs 输出侧 (A1) | A1 |
| B6-1 | DIL 结构化 vs document/ 半实现 | ✅ 已答 — 归工程链施工 | — |
| B6-3 | 可观测三层 vs Monitor | ✅ 伪冲突 — 不同层 (A1) | A1 |
| B8-4 | 网关 vs 进程内 provider | 🔴 **真决策** — 归 LLM-2 | A16 |
| B8-8 | MCP 边界 vs 实现 | ✅ 已答 — 归 mcp 施工 | — |
| B3-8 | ObjectRuntime/Projection 缺口 | 🔴 真决策 — 归 G10/子图 | — |
| B2-5 | 进程内 EventBus vs NATS | ✅ 已答 — 单进程先 (G5) | — |
| B7-2 | 三阶段融合 vs 简化实现 | ✅ 已答 — 归关联链施工 | — |

**聚类 7: 真决策 3 · 伪冲突 4 · 已答 6 · 暂缓 1**

### 聚类 8: 实现↔实现直接矛盾（合并后 11 项）

> 双源合并: G6_FILTER 侧 6 项（实现层尖锐冲突）+ README_INDEX 侧 6 项（设计层并存，
> EventBus 重叠去重）。

| # | 冲突 | 裁决 | 依据 |
|---|------|------|------|
| I1-1 | EventBus 两实现语义相反 | ✅ 方向已定 — 同 B8-2/G2 (保留新, 归档旧) | A17 |
| I1-2 | 双 BeliefAccumulator (l2_5_belief vs belief_map) | ✅ 已答 — 归关联链 F1-F8 施工 | — |
| I1-3 | 三处 CausalSubstrateAdapter | ✅ 已答 — 归关联链归一 | — |
| I1-4 | 两套 ocean_profile | ✅ 已答 — 归画像 P9 施工 | — |
| I1-5 | 双 AssociationSubscriber | ✅ 已答 — 归关联链 D7 修复 | — |
| I1-6 | 双 TrainingFeedbackLoop | ✅ 已答 — 归行为链施工 (死实例移除) | — |
| I1-7 | 三套决策器并存 (GlobalDecider/StateMachine/BlueprintDecider) | 🔴 归入 G1 | — |
| I1-8 | 双套 LLM Provider (根级 vs v3_0) | 🔴 归 LLM-2 | — |
| I1-9 | 双套 Service 实现 (core/agent/service + core/service) | 🔴 归 B4-1 | — |
| I1-10 | 三套 chroma 入口 | 🔴 归 G10 | — |
| I1-11 | 四套前端 WebSocket 实现 | ✅ 已答 — 归 FE-3 施工 | — |

**聚类 8: 真决策 4 (归 G1/LLM-2/B4-1/G10) · 已答 7**

---

## 三、消解汇总

```
输入: G 系列 10 项 + B 系列 51 项 = 61 项
输出:
  ✅ 已答/伪冲突   45 项 (74%)  — 哲学消解或已有决策（含 G10/B2-3/B4-1/B4-5 定案 2026-08-04）
  🔴 真决策       8 项 (13%)  — 需全局拍板
  🟡 暂缓/规模触发  3 项 (5%)   — G5 相关
  🛠 施工项        4+ 项         — 归 IMPLEMENTATION_PLAN

真决策 8 项（拍板池，G1+G3 已合并、G10/B2-3/B4-1/B4-5 已定案）:
  G1+G3  决策/编排归一 + 双路径归一 (含 B1-2/B7-3/I1-7, 方案见 §6/§7)
  G4  FE-1 白盒编辑 API 未注册 (P0)
  B1-8 CognitiveWorkspace 容器 (归 LLM-1)
  B5-3 子图编辑 = 用户控制权
  B8-4 网关 vs 进程内 provider (归 LLM-2, 含 I1-8)
  G2  EventBus 生命周期层 (方向已定待确认, 含 GAP-1~3)
  G5/B8-1 分布式触发条件
  G7/G8/G9 归档/索引/处置策略 (方向已定待确认)
```

---

## 四、建议拍板顺序（真决策 8 项，依赖驱动）

```
第 1 轮 (架构底座):  G1+G3 决策/双路径归一（方案已定待施工）→ G10 已定案 ✅
第 2 轮 (LLM/服务):  B8-4 网关（B4-1/B4-5 已定案 ✅）
第 3 轮 (模块边界):  B1-8 认知容器 → B5-3 子图编辑 → G4/FE-1（B2-3 已定案 ✅）
第 4 轮 (规模/确认): G2/G5/G7/G8/G9 方向确认

每项拍板后立即进施工（对应 GLOBAL_PENDING_DECISIONS §十四）
```

---

## 五、方法论备注

1. 消解率 67% 印证"约 60% 伪冲突"估计——大部分冲突是"同一哲学两个表述"或"不同颗粒度分工"。
2. 真决策 8 项共同特征——都是"多实现并存"或"架构方向选择"，哲学消不了工程债，只能消概念债。
3. B8-2 从"唯一直接矛盾"降级为"方向已定"——用户三阶段方案同时满足 A17+A2+A24，范式内最优解。
4. 精度修正（§〇）是本版相对 G6_FILTER 的关键增量——GlobalDecider 实况、8/13、FE-1 P0。
5. 后续: 8 项真决策逐一过 §5 元规则细化 → 全局拍板。

---

## 六、G1+G3 合并方案（用户拍板方向 2026-08-03，待全局确认）

### 6.1 方案（用户提出，多维评估通过）

```
四套从"并存竞争"变"一条链":
  BlueprintDecider    → 纯视图层（DAG 构建 + 校验 + 白盒编辑）
                         ↓ 产出 BlueprintDAG
  DeciderStateMachine → 执行引擎（消费 DAG，phase 转换执行）
                         ↓ 状态底座
  GlobalDecider       → StateMachine 内部持有（Command→Event 防广播）
  CognitiveScheduler  → 未来（A16 深化后再建）

核心: 蓝图停止越位当引擎——执行归 StateMachine，蓝图只建图。
主路径 = StateMachine 执行引擎，蓝图退为视图 → 与 G3（agent_native 降兼容壳）
是同一解法，G1 与 G3 合并拍板。
```

### 6.2 多维评估（五维度，均已通过）

```
① 哲学一致（✅ 强）:
   A11 可回溯 → StateMachine 执行 = 阶段可回放，执行语义单一化
   A19 白盒   → 蓝图退视图但仍是"可编辑 DAG 输入"，编辑→执行闭环保持
   A17 一致   → GlobalDecider 状态底座 = Command→Event 事件溯源
   A2 颗粒度  → 每层单一职责（建图/执行/状态/调度）

② 架构正确（✅ 方向对，1 缺口）:
   "蓝图越位当引擎"成立——BlueprintExecutor 承担执行是 StateMachine 半实现的
   替代填充，非设计本意
   ⚠️ 最大缺口: DAG 是图（并行分支/依赖边/多 agent），StateMachine 是线性 phase 流
   → StateMachine 必须支持"以 DAG 为输入的拓扑序执行"（DAG→分层 phase 序列），
     否则蓝图并行能力丢失。G1-A 实质 = "阶段机如何消费图"，不是二选一

③ 现状风险（⚠️ 短期回归，需两步走）:
   StateMachine 半实现（8/13 handler / X3 缺 PLANNING/CONTEXT/LLM / X4/X5 输出断链）
   → 先修 StateMachine（X3/X4/X5 升 P0），再切主路径——避免"砍掉能跑的、启用半成的"
   迁移成本: BlueprintExecutor 执行逻辑（节点调度/trace/EventLog）并入或桥接 StateMachine

④ 既往拍板一致（✅）:
   蓝图混合式（EDA+DAG、默认 B + A 可用）不冲突——蓝图仍提供构建/校验/编辑，
   执行由 StateMachine 承载
   G2 分工清晰: StateMachine 执行 + EventBus 传输 + GlobalDecider 状态 = 三件套闭环

⑤ G1+G3 合并（✅ 正确）:
   主路径 = StateMachine 执行引擎、蓝图退视图、agent_native 降兼容壳
   → 三份归一成一条主线；真决策 13 项 → 8 项（G10/B2-3/B4-1/B4-5 定案后）
```

### 6.3 拍板后的施工前置（3 项）

```
G1-P1  修 StateMachine（X3 补 3 handler + X4 输出传递 + X5 result 兜底）——P0
G1-P2  StateMachine 支持 DAG 拓扑序执行（图→分层 phase 映射）——P0
G1-P3  GlobalDecider 复用 CLI registry 实例注入 StateMachine 内部——P1
        （不暴露为新决策器；避免重复实例化）
之后: 切主路径（BlueprintDecider 退视图，BlueprintExecutor 执行逻辑并入 StateMachine）
```

### 6.4 合并后的真决策池（8 项，G10/B2-3/B4-1/B4-5 已定案移出）

```
G1+G3  决策/编排归一 + 双路径归一（合并，含 B1-2/B7-3/I1-7；方案见 §6/§7）
G4     FE-1 白盒编辑 API 未注册 (P0)
B1-8   CognitiveWorkspace 容器 (归 LLM-1)
B5-3   子图编辑 = 用户控制权
B8-4   网关 vs 进程内 provider (归 LLM-2, 含 I1-8)
G2     EventBus 生命周期层 (方向已定待确认, 含 GAP-1~3)
G5     分布式触发条件 (含 B8-1)
G7/G8/G9 归档/索引/处置策略 (方向已定待确认)

> G10 已定案移出（2026-08-04，见 `G10_STORAGE_DECISION_20260803.md`）：
> B2-2/B2-6/B3-8/I1-10 一并随 G10 定案闭合。
> B2-3 已定案移出（2026-08-04，见 §八）：B3-2 一并随 B2-3 定案闭合。
> B4-1 已定案移出（2026-08-04，见 §九）：I1-9 一并随 B4-1 定案闭合。
> B4-5 已定案移出（2026-08-04，见 §十）。
```

---

## 七、G3 重新审视（用户 2026-08-04 修正，事实已核实）

### 7.1 三个关键事实（代码证据）

```
事实 1: CLI 引擎 = 生产引擎（✅ 核实）
  v6_app.py 端点全部用 get_engine()（L98/225/240/250...）
  cli/engine.py:50 get_engine → start_engine → CognitiveRuntimeEngine + StateMachine
  CLI (dm 命令) 也用同一个 get_engine/start_engine
  → 不是"CLI 运维 vs API 生产"两个维度，是"一个引擎两个入口"

事实 2: 真正的分裂在 v3_session_api 内部（✅ 核实）
  v3_session_api.py L123-125: orch = AgentOrchestrator(); cog = orch.process(text)
  v3_session_api.py L262-263: eng = get_engine()
  → 同一次请求前半走 AgentOrchestrator 空壳，后半走 StateMachine 活引擎
  → 不是 A/B 两路径，是"同一请求内混用两套"（且 L125 的 cog 结果后半根本没用上）

事实 3: agent_native 与 StateMachine 是同一维度（✅ 核实）
  两者都做: 输入消息 → 认知处理 → 输出回复（消息处理运行时）
  agent_native 空壳原因: bootstrap 不注入核心链（llm 缺省结构模式）
  StateMachine: 8/13 handler 活
  但 agent_native 有装配价值: _try_load_bridge/context/cognition/feedback/
    compass/gate/execution + _publish + _event_log（支撑模块装配器）
```

### 7.2 修正判断（用户）

```
原 G3 边界错: "agent_native vs runtime/cli 两套运行时并存" ❌
  → 隐含"CLI 一套、生产另一套"——错，CLI 引擎就是生产引擎

修正 G3: "AgentOrchestrator 空壳 vs StateMachine 活引擎 同维度并存，
          且 v3_session_api 同请求混用两套" ✅
  → 问题核心: agent_native 该不该存在 + 为什么混用

拍板建议:
  主路径确认: StateMachine（v6_app 已用，活的）✅
  agent_native 处置: 保留为"支撑模块装配器"，消息处理改走 StateMachine
    （不是"降为兼容壳"——它有装配价值，只是不该再当消息处理器）
  v3_session_api L125 修: orch.process → get_engine().on_event
  CLI: 无需动（已是共享引擎的正确用法）
```

### 7.3 多维评估（我方）

```
① 事实核验（✅ 全部成立）
   三事实与源码一致，G3 边界修正准确

② 概念精确性（✅ 显著提升）
   "一个引擎两个入口"比"CLI vs 生产"精确——CLI/API 共享引擎，
   分裂点从"路径间"移到"路径内"（v3_session_api 单请求混用）

③ 与 G1 合并联动（✅ 强化）
   G1 = 执行引擎归一（StateMachine 主执行 + DAG 消费）
   G3 = 消息运行时归一（agent_native vs StateMachine）
   两个都是"StateMachine 为主" → 合并成立，G3 修正让结论更实锤

④ 施工路径（⚠️ 需细化 3 点）
   ⚠️ P0 新增: v3_session_api L125 修复——同请求数据流断裂
     （cog 结果后半没用上 = 认知分析被丢弃），不只是"路径归一"
   ⚠️ "agent_native 保留为装配器"需细化: 装配已在 bootstrap_v6 完成
     （bootstrap 把组件注入 AgentOrchestrator）——更精确的说法:
     装配职责归 bootstrap_v6/registry，agent_native 退为纯数据容器
     或删除，支撑模块直接挂 engine（StateMachine handler 从 engine 取）
   ⚠️ 兼容风险: v3_session_api 是 v3 旧前端兼容层（L559 fallback 模式），
     修 L125 需保证旧会话功能不破坏

⑤ 风险与收益
   收益: 消除单请求语义断裂 + 运行时单一化 + 与 G1 同向
   风险: 低-中（改动集中在 v3_session_api 一处 + agent_native 定位调整）
```

### 7.4 拍板后施工前置（并入 G1+G3 合并项）

```
G1+G3-P1  修 StateMachine（X3/X4/X5）——P0
G1+G3-P2  StateMachine 支持 DAG 拓扑序执行——P0
G1+G3-P3  v3_session_api L125 归一（orch.process → get_engine().on_event）——P0
G1+G3-P4  agent_native 定位: 装配职责归 bootstrap_v6/registry，
          消息处理改走 StateMachine；agent_native 退容器或删——P1
G1+G3-P5  GlobalDecider 复用 registry 实例注入 StateMachine——P1
之后: 切主路径（BlueprintDecider 退视图，BlueprintExecutor 执行并入 StateMachine）
```

### 7.5 三点细化验证（用户 2026-08-04 验证，全部成立）

```
✅ 第 1 点（装配器定位）— 成立且是重要修正:
   bootstrap_v6.py:75-94 已完整注入 20 组件进 AgentOrchestrator 构造器
   agent_native.py:32-40 的 _try_load_* 兜底只在无参构造时触发
   （v3_session_api:124 正是无参构造 AgentOrchestrator()！）
   → 装配职责确已在 bootstrap_v6 完成；保留"只装配不用"中间层是浪费
   → 更准确: 装配归 bootstrap_v6/registry，agent_native 退数据容器
     或组件直接挂 engine，彻底消除中间层

✅ 第 2 点（L125 升 P0）— 成立，比"路径归一"严重:
   v3_session_api:121-131 orch.process() 结果进 cognitive_ctx
   :154 cognitive_ctx 传给 _build_system_prompt
   :475-477 intents/route/compass 用于 prompt 构建
   → 但 orch 无参构造 → 核心链全 None → cog.get("intents")={} / route={}
     → prompt 里"管线分析"全是空壳 = 认知结果被丢弃/伪造的数据流断裂 → P0 正确

✅ 第 3 点（兼容风险）— 成立，v3 旧前端兼容层:
   v3_session_api 是 v3 会话 API（旧前端用），L125 在 try/except 内
   （失败只 warning 不破坏主流程），L467-477 有 fallback
   （cognitive_ctx 空时 prompt 降级）
   → 正确做法: 不是删 L125，是替换数据源（orch.process → 真引擎）
     并保留 try/except fallback 语义
```

### 7.6 G3 修正版（最终整合，用户确认合理）

```
装配职责归 bootstrap_v6/registry（已是事实）
agent_native: 退为纯数据容器 或 删除——不留"只装配不用"中间层
  （组件直接挂 engine，由 registry 装配）
v3_session_api L125（P0）: 数据源从空壳 orch.process 换真引擎，
  保留 try/except + prompt fallback（兼容 v3 旧前端）
CLI: 无需动（共享引擎正确用法）

验证标准:
  ① v3 旧会话: prompt 构建仍工作（fallback 不破）
  ② 新路径: cognitive_ctx 有真实 intents/route
  ③ agent_native: 零直接实例化（全走 bootstrap）
```

---

## 八、B2-3 锚点扩散归属修正（用户 2026-08-04，代码已核实）

### 8.1 现有实现分散（4 处，全部核实）

```
cross_domain_expander.py:35  expand(anchor_events, intent_category) ← 子图侧（context/）
deep_modules.py:338          expand(anchor, nodes, edges) k-hop BFS ← engine/（死代码候选）
interaction_graph.py:58      propagate(source, target) 状态扩散 ← state/
foa/actr_activator.py:13     propagate(seeds, degrees, edges) 注意力 ← foa/
子图取数: subgraph_compiler.py 175-285 用 getattr(eng, '_discourse_tree'/
          '_behavior_graph_adapter'/'_world_objects'/'_ocean_analyst'...) 直接从
          各模块"抓现成数据"（11+ 处 getattr），不是"扩散召回"
expand_from_graph:622 已委托 ConceptGraph.compile_context（唯一真图召回，§13）
```

### 8.2 模型修正（用户，取代原"存储持锚点/子图持算法"）

```
原拍 ❌: 存储层持锚点, 子图持扩散算法
  → 问题: 子图持算法 = 其他模块要扩散还得绕道子图（功能重复）

新拍 ✅: 持久化层 = 能力底座（锚点 + 图扩散 + 各种 RAG 算法适配）
  子图     = 上下文编译服务（召回→组装, 只消费不持有检索能力）
  执行层   = 两种消费模式:
    主控 agent → 子图（上下文编译 + 操作记忆留存, 供复盘）
    子 agent   → 持久化直连（高效执行, 不绕上下文层）

核心: 一个能力底座, N 个消费方 — 消除重复
  A25 更精确解读: "锚点→图扩散→组装" 中,
    "扩散"是检索第二步 → 属于存储/召回能力（持久化）
    "组装"是给 LLM 的 → 属于编译能力（子图）
```

### 8.3 多维评估（我方）

```
① 代码实锤（✅ 全部成立）
   4 处 expand/propagate 分散在 context/engine/state/foa 四个包，
   子图 11+ 处 getattr 抓现成数据——现状确实是"无统一能力底座"

② 概念精确性（✅ 显著提升）
   "能力层/服务层分离"比"存储持锚点/子图持算法"更对:
   检索能力（锚点+扩散+RAG 适配）是横切能力 → 归持久化
   编译能力（召回→局部世界）是子图职责 → 归子图
   消除"其他模块绕道子图才能扩散"的重复

③ 多 agent 场景（✅ 最强论据，成立）
   主控走子图（带记忆编译视图） / 子 agent 直连持久化（无编译快速存取）
   若扩散在子图, 子 agent 无法直连扩散必须绕道 → 模型让协同不需都过子图

④ 与 A25 对齐（✅ 更精确）
   扩散=检索第二步（存储域）/ 组装=LLM 消费（编译域）→ 分层清晰

⑤ 施工影响（⚠️ 工作量集中在子图改造）
   P1: 持久化层建"召回能力接口"（锚点定位 + k-hop 扩散 + RAG 适配，
       吸收 cross_domain_expander/expand_from_graph 逻辑）
   P2: 子图 compile_dialogue 从持久化取数（替换 11+ 处 getattr）
   P3: 4 处分散实现收敛（deep_modules 死代码确认、interaction_graph/foa
       按职责归位）
   风险: 子图改造面大（subgraph_compiler 主要数据路径重接），需保
         expand_from_graph 的 ConceptGraph 委托不退化
```

### 8.4 B2-3 拍板（修正版）

```
锚点 + 图扩散 + RAG 算法适配 → 持久化层（能力底座, 所有模块可消费）
子图 → 只做上下文编译（召回→组装, 数据源从持久化拉）
执行层 → 主控走子图（记忆+复盘）, 子 agent 直连持久化（高效）

验收:
  ① 对话树/画像/行为链未命中 → 都能直连持久化扩散（不绕子图）
  ② 子图 compile_dialogue 从持久化取数（不再 getattr 各模块）
  ③ 多 agent: 主控子图 / 子 agent 直连（两条路都通）
```

---

## 九、B4-1 服务层归一（用户 2026-08-04，三代演进已核实）

### 9.1 事实厘清（三处，三代）

```
① service/（顶层, 20 文件 218KB）— v3 早期完整独立服务层
   agent_service/orchestrator/protocol{fsm,events,schemas,ui_schema,task_graph}/
   api{main,routes,middleware,websocket}/stores
   → 自洽独立包，但生产零引用（rg 无 from service.* 于 core/scripts）

② core/service/v3_0（12 文件 124KB）— v3.0 重构版
   agent_service/app_factory/fsm_mapping/response_composer/event_registry
   → 引用方: scripts/test_fullstack + start_dev + core/agent/orchestrator/bootstrap
   → v3 测试/启动专用

③ core/agent/service（17 文件 141KB）— v6 集成侧（活跃）
   agent_service/async_*/session_manager/rate_limiter/request_queue/stores
   → 引用方: engineering_bridges(ServiceController) / clarification_ui(models) /
     mcp/security(rate_limiter) / pcr 测试系列
   → 关键: 都是"借用个别组件"，不是整层消费

判断: 与 PCR/行为链/关联链同型 — 多代演进三代并存，但
  v6 主路径（v6_app 直连 get_engine / StateMachine）不经过任何 service 层
```

### 9.2 拍板建议（用户，比"定主实现"更精确）

```
不选"哪个是主实现" — v6 不需要整层服务
组件级吸收: rate_limiter / session_manager / request_queue
  （core/agent/service, v6 活跃）→ 保留为 v6 基础设施组件
协议资产吸收: service/protocol/（fsm/events/ui_schema/task_graph）
  → 有价值（白盒 UI 契约 FE-3/B4-3 依赖），保留
归档: core/service/v3_0（v3 测试专用, 无 v6 引用）+ service/ 顶层壳
  → 若 test_fullstack 还要用, 归档前先迁移测试
```

### 9.3 缓冲问题（用户疑问的核心 — 回应）

```
问: "如果没服务层会出现什么？缺缓冲层？操作规范性？前端复杂时服务层有用？"

答: 会缺三类东西，但解法不是"保留整层"，是"缓冲能力随入口保留":

① 并发缓冲（队列/限流）
   request_queue（单会话串行/多会话并行/30s 超时降级）+
   rate_limiter（双层令牌桶）——v6_app 直连引擎时没有排队/限流/降级
   → 前端复杂操作（多步任务/澄清/并发请求）会直接打引擎

② 会话生命周期（状态归置）
   session_manager（创建/续期/销毁/TTL/持久化）——引擎本身无会话概念
   → 前端直连时会话状态无处归置

③ 协议规范化（格式解耦）
   service/protocol 的 fsm/events/ui_schema/task_graph——前端复杂操作
   （澄清 FSM/TaskGraph/多模态）需要统一协议，否则前端耦合引擎内部结构

关键: "层"可以归档，但这三项缓冲能力不能随层一起丢
  → 落点 = v6_app（唯一生产入口）显式接入 rate_limiter/request_queue/
    session_manager 组件 + protocol 资产
  → 即: 服务层从"层"降级为"组件库 + 协议资产"，缓冲由入口接入

另: 操作规范性 — 白盒化（A19）承诺"操作必记录"，记录点应在
   v6_app 中间件（用户编辑 → journal），FE-1 已暴露前端直连的脆弱
```

### 9.4 B4-1 拍板（修正版）

```
组件保留: rate_limiter / session_manager / request_queue（v6 活跃）→ 基础设施组件
协议保留: service/protocol/（fsm/events/ui_schema/task_graph）→ 白盒 UI 契约
层归档:   core/service/v3_0（先迁移 test_fullstack）+ service/ 顶层壳
缓冲接入: v6_app 内聚薄中间件层（P1 施工）——rate_limiter/request_queue/
  session_manager 挂成 FastAPI 中间件/dependency 集合（api_middleware 概念），
  形成事实上的"轻服务层": 有排队/限流/会话/操作记录，但不建独立包

验收:
  ① v6 模块继续能用 rate_limiter/session_manager（不破 engineering_bridges/
     clarification_ui/mcp）
  ② protocol/ 保留供 FE 系列（ClarificationUI 契约）
  ③ 无"两处 service 实现"并存（v3_0 归档后）
  ④ 前端复杂操作（多步/澄清/并发）经 v6_app 有排队/限流/会话归置（缓冲在）
```

> **2026-08-04 用户确认形态**: 保留整层太重（与 G3 引擎直连/G10 分层相悖），
> 纯降级太散（缓冲无统一承载）——采用"降级 + v6_app 薄中间件层":
> 组件库 + 协议资产保留，缓冲由 v6_app 内聚接入（事实轻服务层）。
> 独立服务层留作阶段 2（与 G5 分布式同触发，多客户端/多进程时提升）。

---

## 十、B4-5 CLI vs RPC（用户 2026-08-04，"内核唯一 + 传输可插拔"）

### 10.1 事实厘清（RPC 通道已存在）

```
已有通道（不是"要不要建"，是"要不要立为主"）:
  service/protocol/（fsm/events/schemas/task_graph/ui_schema）— v3 协议资产（B4-1 已定保留）
  core/agent/mcp/（5 文件 46KB: client/config/integration/security/server）—
    MCP = 标准 RPC，server.py 已用 @mcp.tool 注册（evaluate_intent/parse_intent 等）
  v6_app WebSocket（ws_bridge.py）— 实时双向通道
  前端 v4.ts/v6.ts — HTTP API 客户端（REST ≈ RPC 的一种）

实测: CLI 命令 186+（15 个 command 文件）/ 前端请求端点 69 / 后端定义端点 30
  → 39 个前端调用后端未直接定义（含 /v6/edit/* 白盒编辑、stubs 路径）
```

### 10.2 关键洞察（用户）

```
CLI 和 RPC 不是两条平行路，是同一命令集的两种传输:
  命令 → 内核（dispatch 函数）→ 传输层（CLI / REST / MCP / WS）
    CLI:  argv → dispatch → 结果
    REST: JSON → dispatch → JSON（v6.ts 已在用）
    MCP:  工具调用 → dispatch → 结构化结果
  → 内核共享, 传输可插拔（"CLI 即内核"设计，之前已定）

为什么先 CLI 正确（不只是轻量）:
  CLI 是唯一"全功能白盒"通道（186+ 命令直接映射模块，A19）
  CLI 是调试/审计工具（记录完整可回溯，A17）
  CLI 无协议版本问题（进程内调用天然同步）
  RPC 价值（效率/记录）依赖后端完整——后端没修好前，RPC 只是"把 404 变成 error code"

为什么 RPC 必建（不只是效率）:
  前端绑定（v6.ts 已在调 REST，不是可选）
  多 agent 协同（子 agent 直连 B2-3，不能都走 CLI）
  MCP 生态（外部工具接入标准通道）
  记录审计（结构化 request/response 更适合事件溯源，A17）
```

### 10.3 B4-5 拍板（修正版）

```
内核唯一: dispatch 函数集 = 唯一命令内核（已成立）
传输层现状: CLI ✅（完整，但部分命令假执行）/ REST ✅（v6.ts 在用，
            但 39 端点未对齐）/ MCP ⚠️（雏形）/ WS ⚠️
顺序（阶段 1-4）:
  阶段 1: 补全 CLI（消除假执行——蓝图审计 decider execute 假执行）
  阶段 2: REST 端点对齐 CLI（v6.ts 调用 → 内核 dispatch，消除 stubs_api 假数据）
  阶段 3: MCP 标准化（mcp 工具注册到内核，复用 dispatch）
  阶段 4: 多 agent 直连（B2-3 持久化能力底座就绪后）

效率与记录: RPC 更优，但那是"内核就绪后"的传输红利——
  传输层再快，内核是假的（假执行/假数据）也没用
```

### 10.4 多维评估（我方）

```
① 事实核验（✅ 基本成立，1 补充）
   CLI 命令 186+（我数 add_parser 186，用户说 348——含多级子命令展开）
   前端 69 vs 后端 30 → 39 缺口（含 edit/白盒/stubs）
   MCP @mcp.tool 已注册 → 雏形存在
   补充: 后端"30 定义"含 stubs_api 的 stub 响应——"有端点"≠"真数据"，
         与阶段 2"消除 stubs 假数据"一致

② 概念精确性（✅ 显著提升）
   "同一命令集的两种传输"比"CLI vs RPC 二选一"精确——
   拍板 = 确认内核唯一 + 传输层按需，非选主

③ 与既往拍板一致（✅）
   G3（引擎直连）→ CLI/API 共享引擎 = 同一内核
   B4-1（服务层降级）→ protocol 资产正是 REST/WS 的协议基础
   B2-3（持久化能力底座）→ 多 agent 直连的前提
   FE-1（白盒编辑 404）→ 阶段 2 REST 对齐的动机实例

④ 风险（⚠️ 低）
   "CLI 补全"依赖各模块真实现（部分模块仍断链）——与施工顺序耦合
   建议: 阶段 1/2 与各模块施工并行（CLI 补全 = 模块真实现的验收面）
```

### 10.5 B4-5 拍板（正式）

```
内核唯一 ✅（dispatch 函数集）
传输层按需: CLI（完整）→ REST（对齐）→ MCP（标准化）→ WS
顺序: CLI 补全 → REST 对齐 → MCP → 多 agent 直连

验收:
  ① CLI: dm <任何命令> 返回真实数据（无假执行）
  ② REST: v6.ts 每个调用 → 内核 dispatch（无 stub 响应）
  ③ MCP: 工具 = 内核命令的注册表映射
```
