# 未对应设计文档批量精读 — 总索引与冲突登记汇总

> 日期: 2026-08-03 | 状态: **8/8 批全部完成，33 个 A 类缺口文档全部读完并记录**
> 定位: 承接 `DOCS_LANDSCAPE_MAPPING_20260803.md`（A 类 33 个真缺口），逐批精读落盘。
> 冲突只记录不拍板——统一交由哲学层（`docs/only/wise/PARADIGM.md`）裁决。

---

## 一、批次索引（8/8 完成）

| 批 | 主题 | 文档 | 覆盖数 | 冲突 |
|---|------|------|:--:|:--:|
| 1 | 认知空间/调度 | `BATCH1_COGNITIVE_SPACE_SCHEDULER_20260803.md` | 6 | 8 (B1-1~8) |
| 2 | 记忆/持久化 | `BATCH2_MEMORY_PERSISTENCE_20260803.md` | 4 | 7 (B2-1~7) |
| 3 | 推理/知识 | `BATCH3_REASONING_KNOWLEDGE_20260803.md` | 5 | 8 (B3-1~8) |
| 4 | 服务层/CLI | `BATCH4_SERVICE_LAYER_CLI_20260803.md` | 5 | 5 (B4-1~5) |
| 5 | 前端/图编辑器 | `BATCH5_FRONTEND_GRAPHEDITOR_20260803.md` | 6 | 4 (B5-1~4) |
| 6 | 文档摄入/可观测/事件日志 | `BATCH6_DIL_OBSERVABILITY_EVENTLOG_20260803.md` | 3 | 5 (B6-1~5) |
| 7 | v3.3 行为子组件 | `BATCH7_V33_BEHAVIOR_SUBCOMPONENTS_20260803.md` | 4 | 6 (B7-1~6) |
| 8 | 跨切面/基础设施 | `BATCH8_INFRASTRUCTURE_20260803.md` | 9 | 8 (B8-1~8) |
| **合计** | | | **42 文档** | **51 项冲突** |

> 注: 覆盖 42 篇 = A 类 33 个 + 补充相关 9 个（如 ENGINEERING_V3_3_PREDICTOR/REWARDER、
> FRONTEND_BUSINESS_FLOW 等）。D 类架构总览与 C/E 类历史快照不在精读范围（已在
> DOCS_LANDSCAPE_MAPPING 分类，处置待拍板）。

---

## 二、冲突登记总表（51 项，按主题聚类）

### 聚类 1: 决策/编排归一（10 项）
- B1-2 三套调度候选（GlobalDecider / DeciderStateMachine / CognitiveScheduler）
- B1-3 调度器 vs EventBus（编排实现关系）
- B1-7 模块内谱系（MultiTier）vs 模块间编排（蓝图）
- B7-3 融合器+GlobalWorkspace = 第三套决策仲裁（vs 双决策器）
- B2-4 ES+CQRS 全量蓝图 vs 关联链 Phase 6 切片
- B6-4 EventLog 雏形 vs ES+CQRS 完整蓝图（同一演进链）
- B8-1 分布式未来态 vs 单进程 ES+CQRS 效率论证
- B8-2 EventBus v2 NEVER drop vs ES 环形缓冲满则丢弃（背压矛盾）⚠️ 直接矛盾
- B6-5 EventBus"已有"假设 vs NATS 未通现实
- B8-3 NATS 模式吸收 vs X1 NATS 无限重连

### 聚类 2: 空间/对象模型（8 项）
- B1-1 四树空间归属（conversation/topic/semantic/reasoning）vs 树图一体哲学
- B3-1 对象+投影渲染 vs 子图编译（两条上下文渲染路线）
- B3-7 World View+RecursiveZoom vs SubgraphCompiler 层级
- B2-3 锚点定位+图扩散归属（子图 vs 持久化）
- B3-2 锚点检索机制三份设计（GRAPH_FALLBACK / L5 / 子图）
- B1-8 CognitiveWorkspace 容器未实现（设计存在，实现缺）
- B7-1 FoA 注意力 vs Observer.attention（两套注意力）
- B8-5 压缩调研策略 vs L5 落地 + context/compressor

### 聚类 3: 记忆/持久化（6 项）
- B2-1 XML 卡设计源 vs memory/ 孤儿实现（零消费）
- B2-2 五区/四区存储 vs 6 套体系并存
- B2-6 统一图存储 vs ENGINEERING_PERSISTENCE 双蓝图
- B2-7 FactStore 批量写缺陷在五区设计中的落点
- B6-2 文档树静态场 vs L5 四区存储（Archived 区）
- B1-5 统一关系本体 vs 关联链分层漏斗

### 聚类 4: 行为链（4 项）
- B1-4 模拟引擎（心智理论）vs 行为链预测器（统计+DPO）
- B8-6 predictor 四维排序 vs 现实现覆盖度
- B8-7 rewarder EMA/ABL vs reward_signal 双轨方案
- B7-4 行为链 L1 摘要 vs 对话树渐进摘要

### 聚类 5: 约束/安全（3 项）
- B7-5 负知识库 vs ConstraintTree 约束体系
- B7-6 HARD_BLOCK 需 do-calculus vs 关联链因果基板
- B3-6 INJECTION 检测 vs security/input_sanitizer 职责边界

### 聚类 6: 服务层/前端/CLI（6 项）
- B4-1 服务层双蓝图（v2.3 addon vs 1521L 工程规范）与两处实现归一
- B4-2 /chat /parse /execute 简化实现 vs 完整规范
- B4-3 ClarificationUISchema/state_change 与 clarification_fsm 契约
- B4-4 CLI 目标态（27 命令/TUI 8 Tab）vs 现实现覆盖度
- B4-5 CLI vs RPC 架构走向
- B5-2 图编辑三份设计（GRAPH_EDITOR / SVG_FLOWCHART / api_viz_edit）归一

### 聚类 7: 前端接线/LLM/其他（14 项）
- B5-1 前端 15 页大部分"有 UI 需接管线"
- B5-3 子图编辑=用户上下文控制权 vs 子图审计
- B5-4 前端↔CLI 双通道 vs CLI 目标态
- B1-6 单 Observer 实例 vs 多 agent/联邦
- B3-3 Hypothesis Pool vs 关联链 L2.5 信念
- B3-4 多 Analyzer 竞争解释（consumer_marks）未落地
- B3-5 NoiseSpan 与 PCR zone/compass 体系的关系
- B6-1 DIL 结构化 Observation vs document/ 现状半实现
- B6-3 可观测性三层 vs 调度器 Monitor（两套监控）
- B8-4 网关 vs 进程内 provider 双路由
- B8-8 MCP 边界声明 vs 实际 mcp 实现一致性
- B3-8 ObjectRuntime/Projection 实现缺口（world/ 只实现数据层）
- B2-5 进程内 EventBus vs NATS 基础设施
- B7-2 三阶段融合 vs orchestrator/fusion_engine 简化实现

### ⭐ 聚类 8（新增·用户评价补盲）: 实现↔实现直接矛盾（6 项）
> 用户评价指出结构性盲区：51 项冲突全部是"设计↔设计"或"设计↔实现"，
> 缺少"实现↔实现"冲突登记。本聚类为补充，全部经源码实测确认。

- I1-1 EventBus 双实现背压语义相反（🔴 与 B8-2 同源，直接矛盾）
  - `core/agent/events/event_bus.py`（旧）: deque(maxlen=1024) + _dropped_count → 满则丢弃
  - `core/agent/event/event_bus.py`（新）: "NEVER drop" + EventLog replay + 队列满 catch-up
- I1-2 三套决策器并存（🔴 与 B1-2/聚类 1 同源）
  - `core/agent/state/global_decider.py` GlobalDecider（Command→Event，状态驱动）
  - `core/agent/event/statemachine.py` DeciderStateMachine（PipelinePhase 阶段机）
  - `core/agent/blueprint/decider.py` BlueprintDecider（抓 executor 私有 handler）
- I1-3 双套 LLM Provider 并存（根级 vs v3_0，139.5KB 零测试）——LLM 认知层审计已记
- I1-4 双套 Service 层实现（core/agent/service 17f 141.5KB + core/service 12f 123.7KB）
- I1-5 三套 chroma 入口（learning/chroma_store + storage/chunk_store + event/pluggable）
- I1-6 四套前端 WebSocket 实现（useWebSocket/websocket/websocketClient/ws——FE-3）

> 补充: 部分"实现↔实现"冲突已在各模块审计记录（如 P-2 多代演进分裂条目），
> 本聚类是首次将其显式聚合——与"设计↔设计"冲突分开裁决。

---

## 三、给全局拍板池的输入（压缩后讨论）

1. **背压矛盾（B8-2）是唯一"直接矛盾"**（NEVER drop vs 满则丢弃）——建议哲学层优先
   裁决，因为它决定 EventBus/ES 的实现方向。
2. **三套决策/编排候选（聚类 1）** 是全局最大的归一主题——与执行层 X 系列、蓝图
   EDA/DAG 讨论同源，应作为全局拍板的第一议题。
3. **服务层归一（B4-1/B4-2）** 与两处实现（core/agent/service + core/service）直接挂钩，
   是"两处服务层"待拍板的完整设计侧证据。
4. **A 类 33 缺口全部读完** → 下一阶段可选: ① 哲学消解（PARADIGM 对照）② 逐缺口
   补实现审计 ③ 进入全局拍板。建议先 ①。

---

## 四、B8-2 背压矛盾 — 用户拍板方向（2026-08-03 已记录，待全局确认）

### 裁决方向（用户建议，语义已澄清）
```
核心澄清: NEVER drop ≠ 永不删除，而是"慢消费者不丢事件"。
  - 消费者没消费 → 事件保留（NEVER drop 满足）
  - 消费者已消费 + 事件变冷 → 摘要化/减枝（新生命周期层）
  → 两个语义不冲突，是不同阶段

裁决:
  ① 保留 event/event_bus.py（新, NEVER drop + EventLog replay）
  ② 废弃 events/event_bus.py（旧, deque 满则丢弃）→ 归档
  ③ 新增 EventLog 生命周期层（三阶段）:
      阶段1 热事件: 全量保留（NEVER drop 不变）
      阶段2 温事件: 按 importance 减枝（复用 ColdIndexer 机制）
      阶段3 冷事件: 语义摘要化（结构降级 C 先做 + LLM 摘要 B 增强）
```

### 三个关键设计点（用户定义）
```
1. 摘要化触发与载体:
   A. L2 摘要（对话树渐进摘要）→ 不通用，对话树专属
   B. LLM 异步摘要（事件批量→摘要事件→替换原文）→ 增强
   C. 结构降级（ModuleState→状态标记，subgraph 修剪第4步）→ 零成本先做
   建议: C 先做 + B 增强，A 不用

2. 减枝标准（不能按时间一刀切，retention_hours=24 太粗）:
   复用 ColdIndexer importance 三信号:
   - activation_count（激活次数）
   - recency（近期性）
   - semantic_value（语义价值 — 摘要后能否还原）
   → 高语义价值事件永不减枝原文；低价值才摘要化/丢弃

3. 与 A24（可逆推）兼容: 摘要保留语义锚点 + cross_ref，
   原文删除后仍可从摘要推回主题
```

### 我方核查（机制真实性确认）
```
✅ EventLog retention_hours=24 + replay_unconsumed（api_event_log.py:34/90/111）
✅ graph_tier_manager H/W/C/A 分层（activation_count + importance）
✅ lsm_store graph_nodes 含 activation_count/importance/tier 字段
✅ subgraph 四轮修剪（第4步摘要压缩，subgraph_compiler.py:400-406）
✅ ColdIndexer 存在（core/agent/cold_indexer.py，行为链已审计）
```

### ⚠️ 三个待补缺口（我方评估，不阻塞裁决）
```
GAP-1 「已消费」无确认机制（必须补，否则温减枝无从判断）:
  EventBus 现为广播式同步调用，无 ack/水位线。
  补: 每 subscriber 记录 last_consumed_seq；减枝只针对所有 subscriber
      都已消费的事件。

GAP-2 semantic_value 载体未定义:
  ColdIndexer 三信号无"语义价值"字段；LLM 每事件打分成本高。
  建议: 用 lsm_store.importance + 摘要可还原性代理（cross_ref 完整性）。

GAP-3 A24 可逆推保真度:
  摘要化需在减枝时校验"锚点完整性"（cross_ref 全保留），否则推不回主题。
  建议: 减枝前校验锚点集 = 原文 anchor set，不完整则跳过减枝。
```

### 结论
```
方案方向正确、与现有机制同构度高（不是新造，是复用）；
建议按用户裁决方向执行，补 GAP-1~3 后进全局拍板池确认。
```
