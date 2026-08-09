# 全局待拍板清单总表 — 全模块汇总（2026-08-03）

> 目的: 把分散在各审计文档的待拍板项统一汇总，供"哲学消解 → 全局拍板"使用。
> 来源: PENDING_DECISIONS（意图/画像/对话树）+ 各模块 DEEP_AUDIT + 本批 landscape_read
>       （B1-B8 冲突）+ FRONTEND_IMPL_AUDIT + SEMANTIC_DIFF_AUDIT + 用户拍板方向。
> 统计: **约 130 项**（含已拍板确认项与真待拍板项，已排除纯修复/纯施工条目）。

---

## 〇、已拍板（不再讨论，施工依据）

```
关联链 D-1~D-16（DECISIONS_20260802.md，Phase 0-5 已施工完成）
行为链 方案 C（修断链→修 P2→接 v4→四层决策树→奖励闭环）+ 显式承诺
蓝图  混合式（EDA + DAG，默认 B 综合 + A 可用）+ EventBus 优先做关联链/元认知
PCR   zone 坐标体系 + 权重 YAML 定死一套 + 子图 C/S 被动通道
意图  R1-R6（种子集 + 三时相 + 5 链验证）+ L3 接线 + T2 回写
画像  FactStore 完成 + Track A 复活 + inertia feed
对话树 engine 切 B/C6/C2/C4 + 黄金示例集
执行层 X1-X8 已列（NATS/递归/handler 等，施工方向已定）
B8-4  网关主路径 + 进程内降级回退（switch 嵌入式网关为唯一内核，
       全部 LLM 调用走 switch；ProviderManager 降级为 fallback；详见
       `B84_GATEWAY_DECISION_20260804.md`）
B5-3  子图编辑 = 用户控制权（三层分离: 层1 图编辑 A19 / 层2 编译 A2 /
       层3 数据 A17 + 行为回流 A6 + 三档模式；详见
       `B53_SUBGRAPH_USER_EDIT_DESIGN_20260804.md`）
B1-8  CognitiveWorkspace 容器（归 A 套 v4/cognitive/* 做认知运行时完整落地 +
       接主路径 + 与 LLM-1 共享树联动；详见
       `B18_COGNITIVE_WORKSPACE_DECISION_20260804.md`）
LLM-3 v6 接入认知层（思考树 = 对内执行预测学习: 预测→执行→对照→学习，
       输出吸收进工程链/元认知/skill；详见
       `LLM3_V6_COGNITIVE_INTEGRATION_20260804.md`）
G2    EventBus 生命周期层（NEVER drop + 热/温/冷 + GAP-1~3 细化:
       per-subscriber 水位线 / semantic_value=锚点数 / A24 复用关联链指标；
       详见 `G2_EVENTBUS_LIFECYCLE_20260804.md`）
```

---

## 一、跨模块/全局（哲学层先裁决，约 10 项）

| # | 议题 | 现状 | 建议 |
|---|------|------|------|
| G1 | 三套决策/编排归一（GlobalDecider/DeciderStateMachine/BlueprintDecider + CognitiveScheduler）| 全部存在且并存 | 🔴 全局第一议题，与执行层 X 系列合并 |
| G2 | EventBus 背压方向（B8-2 + I1-1）| 新旧实现语义相反 | ✅ 用户已给方向（保留 NEVER drop + 生命周期层 + GAP-1~3），待全局确认 |
| G3 | 双路径分裂（A 挂 B 没挂）| agent_native vs runtime/cli | 路径归一拍板 |
| G4 | 白盒化承诺（A19）vs 前端编辑 404（FE-1）| 设计有、实现断 | 白盒编辑 API 是否补注册 |
| G5 | 单进程 vs 分布式（B8-1）| 单点 | 规模触发条件拍板 |
| G6 | 哲学消解预筛（用户建议）| 51 项冲突约 60% 伪冲突 | 先做 PARADIGM 消解，聚焦 10-15 项 |
| G7 | 归档策略（un_use vs 散放）| 用户偏好 un_use | 全量归档清单确认 |
| G8 | 重构执行方式（索引先行 vs 逐模块）| — | 先索引后迁移（推荐）|
| G9 | A 类缺口处置顺序（先拍板 vs 先精读吸收）| 33 个已读完 | 先拍板去留 |
| G10 | 存储架构总拍板 | ✅ 已定案（2026-08-04）— 分层+触发: 阶段1 零新依赖（sqlite_store+graph_store+UnifiedStore+TieredStorageManager 接线）→ 阶段2 Kuzu → 阶段3 Neo4j/Milvus。详见 `G10_STORAGE_DECISION_20260803.md` | 统一存储层 |

---

## 二、执行层（X 系列，已列 8 + 本批 6 = 14 项）

| # | 议题 | 级别 |
|---|------|------|
| X1 | NATS 无限重连（nats_bridge + pluggable）| P0 |
| X2 | on_event 无限递归 | P0 |
| X3 | PLANNING/CONTEXT/LLM handler 缺失 | P1 |
| X4 | handler 输出不传下游 | P1 |
| X5 | 无 handler 阶段 result 残留 | P1 |
| X6 | _on_event_continue 460 行死代码 | P2 |
| X7 | _compile_context 幽灵调用 | P2 |
| X8 | _planner 恒 None（规划未接线）| P2 |
| X9 | 7 树体系 5 死树去留 | P1 |
| X10 | ExecutionPipeline B 路径接线 | P1 |
| X11 | ConstraintTree 注入 sandbox/permissions | P1 |
| X12 | closure.py 四类复活 or 删除 | P2 |
| X13 | server/normalizer/p1_gaps 三孤儿处置 | P2 |
| X14 | 执行层测试补全 | P2 |

---

## 三、元认知（M 系列）+ 规划 + 持久化

### 元认知（3 项）
```
M5  P0  写路径整体断（补 post_decision + 订阅 + _meta_consumer/_trace_v3）
M8  P2  三套元认知归一（v3 Adapter / v4 MetaCognition / v6 MetaConsumer）
M9  P2  MetaReviewer/TriggerEngine 去留
```

### 规划（3 项）
```
PL-1  models.py 重导出壳恢复（git 找回 1197 行 vs 0.7KB 壳）——P0 包断裂
PL-2  v4 skill_layer 壳清理（3 处导入即炸）
PL-3  三套规划归一（planner/ + causal/planner + v4 skill_layer）
```

### 持久化（4 项）
```
PE-1  存储架构 ✅ 已定案（2026-08-04）— 分层+触发（G10_STORAGE_DECISION）: 阶段1 零新依赖
PE-2  ENGINEERING_PERSISTENCE 新增部分是否落地 — 随 G10 阶段1 接线（UnifiedStore→ChunkStore / TieredStorageManager→主存储）
PE-3  FactStore 批量写缺陷修复（每次 add 全量落盘 = 磁盘 thrash）— 未定，独立施工项
PE-4  HNSW/Milvus/chromadb 依赖去留 ✅ 随 G10 定案 — 4 孤儿后端（faiss/milvus/hnsw/lsm）归档或吸收进 UnifiedStore；chroma 入口归一
```

---

## 四、主题树（T 系列，7 项）

```
T1  P1  EmbeddingEngine 只 catch ImportError → 改宽异常
T2  P1  context_assembly.get_current_branch 方法不存在（静默空）
T3  P1  engineering_bridges.get_active_path 方法不存在（静默空）
T4  P2  V1/V2 双实现归一并桥接
T5  P2  阈值硬编码（0.55/0.25/0.85）参数化（A18）
T6  P2  ACTIVATION_THRESHOLD=10 延迟激活是否调整
T7  P3  hash 伪向量 vs BGE 编码器契约统一
```

---

## 五、causal / 认知（C 系列，5 项）

```
C1  P1  CausalPlanner 全库零实例化（引擎 3 分支恒死）
C2  P1  CognitionHub.ingest_relations 零调用（converge 空转）
C3  P2  UnifiedContext 的 DiscourseManager 半边被注释（"unified" 名不副实）
C4  P2  discourse/ 包缺 DiscourseBlockTree 符号（inspect CLI 断）
C5  P3  _behavior_brain/_behavior_graph_adapter 声明后零赋值清理
```

---

## 六、外围服务（PE 系列，5 项）

```
PE-A  memory/ 六文件孤儿（L5 概念零接线）——归档 or 接持久化层
PE-B  chroma 三套并存（learning/storage/pluggable）归一
PE-C  orchestrator v3 vs agent_native v6 双宿主
PE-D  coordinator multi_tier_llm_client vs llm_providers 两套 LLM 分层
PE-E  world/observation 深读待施工时补
```

---

## 七、LLM 认知层（3 项）

```
LLM-1  共享树通信接线（6 LLM → CognitiveCompiler 从不调用，node_id=None）
LLM-2  认知模式落地（cognitive_mode/native_async/模式路由零实现）+ 双套 Provider 归一
LLM-3  v6 是否接入认知层（runtime/cli 零引用 cognitive_tree）
```

---

## 八、前端（FE 系列，6 项）

```
FE-1  P0  白盒编辑 API（/v6/edit/*）后端未注册 → 图编辑/对话树编辑 404
FE-2  P1  12+ 组件/hook/lib 死代码去留
FE-3  P1  四套 WebSocket 实现归一
FE-4  P2  stubs_api 假数据问题（前端读到 stub 响应）
FE-5  P2  前端页面"有 UI 需接管线"逐页接线
FE-6  P3  GraphEditPanel 提交失败静默（补 404 提示）
```

---

## 九、SemanticDiff（SD 系列，3 项）

```
SD-1  P1  SemanticDiffer 注入后零调用（AST 约束从未生效）
SD-2  P2  设计文档 0 引用已补（并入执行层/工程链索引）
SD-3  P3  实现无独立测试
```

---

## 十、意图（I 系列，12 项）——详见 PENDING_DECISIONS_20260803.md

```
I1 三时相范式 ✅已拍 / I2 种子集 ✅已拍 / I3 新包接线 / I4 旧 8 阶段归档 /
I5 5 链验证补全 / I6 PCR 调控恢复 / I7 意图↔对话树 4 接口 /
I8 shim 清理 / I9 测试补全 / I10 自适应阈值两套归一 /
I11 多意图拆分验证 / I12 认知双工形态
```

---

## 十一、画像（P 系列 12 + H 系列 6）——详见 PENDING_DECISIONS_20260803.md

```
P1 画像本体归一（事实列表 + OCEAN 投影 + 惯性层）✅方向已定 / P2 _cognitive_profile 复活 /
P3 PROFILE_GAP 修正（95%→30-40%）/ P4 L3 视角接线 / P5 组块边界←认知状态 /
P6 P4 双向先验 / P7 inertia 喂数据 6 源 / P8 ContextCompiler P 域 / P9 v2 双轨 11 模块去留 /
P10 g 因子领域化 / P11 CLI 死命令 / P12 画像测试
H1 事实列表核心 / H2 declarative-facts 写入 / H3 background_review 后验 /
H4 consent 冷启动 / H5 注入扫描+快照 / H6 who-vs-how 分工
```

---

## 十二、对话树（D 系列 13 + 施工清单）——详见 PENDING_DECISIONS_20260803.md

```
D1 输入源 / D2 primary_intent 来源 / D3 分裂归一内核（C 编译器 ✅方向）/
D4 PCR 调控 / D5 温度多因子权重 / D6 摘要边界 / D7 温度接口边界 /
D8 灰区决策（快路径+A13）/ D9 链与树关系 / D10 DualStructure 吸收 /
D11 三范式标签 / D12 ContextCompiler 域接口 / D13 P0 验证集
```

> 2026-08-04 施工发现（模块边界纪律，归对话树模块）:
> **D-14** compiler/discourse_block_tree.py CohesionScore 字段名 bug:
>   类定义用 `total/macro/micro`，内部 794/830 行自引用 `total_score`
>   （与 discourse_block_tree/models.py 版 `total_score/macro_score/micro_score`
>    不一致——同型"3 位置同名类"分裂）。触发: cli test_discourse_write_ops。
>   修复方向: compiler 版字段对齐 models 版或加兼容属性，归对话树施工。

---

## 十三、B 系列冲突（51 项，待哲学消解——见 README_INDEX_20260803.md）

```
聚类 1 决策/编排归一（10 项, 含 B8-2 已给方向）
聚类 2 空间/对象模型（8 项）
聚类 3 记忆/持久化（6 项）
聚类 4 行为链（4 项）
聚类 5 约束/安全（3 项）
聚类 6 服务层/前端/CLI（6 项）
聚类 7 前端接线/LLM/其他（14 项）
聚类 8 实现↔实现直接矛盾（6 项, 新增）
→ 建议先做哲学消解预筛（约 60% 伪冲突），聚焦真冲突 10-15 项
```

---

## 十四、建议的拍板顺序（依赖驱动）

```
第 1 轮（哲学层）: ✅ 已完成 — G1+G3 合并定案 / G6 预筛完成 / G2 方向已定待确认
第 2 轮（架构）:   ✅ G10 存储定案 / B4-1 服务层定案 / G4 白盒编辑（FE-1 P0 待施工）
第 3 轮（模块）:   B8-4 网关 → B1-8 认知容器 → B5-3 子图编辑（B4-5 CLI/RPC 已定案 ✅）
第 4 轮（前端/外围）: FE 系列 → PE 系列 → SD 系列（随定案项施工）
每轮: 先哲学消解 → 真冲突拍板 → 施工
```

> 2026-08-04 更新: 真决策 13→8 项（G1+G3 合并、G10/B2-3/B4-1/B4-5 定案）。
> 2026-08-04 追加: **B8-4 已拍板**（网关主路径，见 B84_GATEWAY_DECISION）。
> 2026-08-04 追加: **B5-3 已拍板**（三层分离设计，见 B53_SUBGRAPH_USER_EDIT_DESIGN）。
> 2026-08-04 追加: **B1-8 已拍板**（认知运行时归 A 套，见 B18_COGNITIVE_WORKSPACE_DECISION）。
> 2026-08-04 追加: **LLM-3 已拍板**（v6 接入认知层 = 对内执行预测学习，见 LLM3_V6_COGNITIVE_INTEGRATION）。
> 2026-08-04 追加: **G2 已拍板**（GAP-1~3 细化，见 G2_EVENTBUS_LIFECYCLE）。
> 剩余真决策: G4/FE-1（方向已明待施工）、G5(暂缓)、G7-9(待确认)。
