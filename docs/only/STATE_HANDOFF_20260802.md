# 施工状态交接 — 2026-08-02（压缩前完整快照）

> 目的: 压缩上下文前固化全部进度/决策/问题/下一步。**压缩后以本文档为唯一恢复入口。**
> 范围: 子图施工完成态 + 蓝图 P0 施工完成态 + **关联链审计完成态 + 决策 D-1~D-16 拍板** + 行为链 P0-P3+CLI 完成态（§十四）+ **第二轮冻结快照（§十五，行为链质量深挖 + DPO + 对话树审计入口）** + CLI 基础设施问题 + 待办。
> 恢复顺序（2026-08-03 最终版）: **第一步读 `docs/only/RECOVERY_PLAN_20260803.md`**（压缩恢复规划：文档顺序 + 对话树审计阶段二步骤 + DPO 待办 + 全局剩余）→ 按其中 §一 顺序读 STATE_SNAPSHOT_ROUND2 → 本文档 §十三/§十四/§十五 → BEHAVIOR_IMPL_PROGRESS → **主线 = 对话树专项审计**（`docs/only/discourse_tree/AUDIT_ENTRY_20260802.md` 阶段二具体实现审计）。

---

## 一、子图施工状态（✅ 已完成，40 测试绿）

### 1.1 代码改动（子图会话）

| 文件 | 改动 |
|------|------|
| `core/agent/v4/cognitive/subgraph_compiler.py` | 意图矩阵/cross_ref/修剪/pull_prior/to_ir/事件扩展/图扩展/zone 桥接 |
| `config/subgraph_dimensions.yaml` | 意图矩阵 + alloc + zone_fallback + trim 参数 |
| `core/agent/cli/subsystem_registrations.py` | B registry 补注册 subgraph |
| `core/agent/cli/commands/subgraph_cmd.py` | show/expand 改调 compile_dialogue/compile_meta |
| `core/agent/cli/registry.py` | `_instantiate_with_deps` 修复 engine 注入 |
| `core/agent/cli/engine.py` | B 路径注入 engine + provider |
| `core/agent/event/nats_bridge.py` | NATS 禁用重连（allow_reconnect=False） |
| `tests/test_subgraph_v2.py` | 40 个测试（含对抗性） |
| `pytest.ini` | addopts 加 `-m "not slow"` + faulthandler_timeout |

### 1.2 测试状态

- 子图 40 passed ✅（对抗测试抓到并修复 5 个真 bug: registry 注入连环/悬空指针/缺失 cross_ref/trim 计量/trim 循环）
- 文档: `docs/only/subgraph/DESIGN_SUBGRAPH.md`（施工主文档）、`SUBGRAPH_DEEP_INVESTIGATION.md`、`SUBGRAPH_DESIGN_OVERVIEW.md`

---

## 二、蓝图审计状态（✅ 已完成，三层文档齐备）

| 文档 | 内容 |
|------|------|
| `docs/only/blueprint/BLUEPRINT_AUDIT_20260802.md` | 综合分析（索引级 → v2 深度版）: 15 节设计检查点 + 逐文件行号 + 根因链 |
| `docs/only/blueprint/BLUEPRINT_IMPL_AUDIT_20260802.md` | 实现专项审计（运行时实测）: 20 条探针 + 新增 P0-26/27 等 + state.json 环境差异修正 |
| `docs/only/blueprint/DESIGN_DEEP_AUDIT_20260802.md` | 设计深度审计 + 执行解读: 15 节逐节解读 + §7 决策记录（7.1-7.7）|
| `docs/only/blueprint/P0_COUPLING_INVENTORY_20260802.md` | 施工前耦合盘点: 消费者/依赖/链组件接口/陷阱 |
| `docs/only/blueprint/P0_TASK_PLAN_20260802.md` | 任务计划 + **完成状态表** |
| `docs/only/blueprint/P0_RETRO_20260802.md` | **压缩前复盘: 设计↔实现对照 + P1 待办清单** |
| `docs/only/blueprint/probes/` | 8 个审计探针脚本（可复现实测） |

### 2.1 审计核心结论（回查用）

- 蓝图 = "构建可用、执行虚假"的半成品编排层；根因: 生产 `AgentOrchestrator()`/`bootstrap()` 核心六链（pcr/intent/l4/behavior/engineering/llm）全 None
- 生产 API 是"两套运行时混合": Phase 1/3.5 用空壳 AgentOrchestrator（蓝图段），Phase 4 后用 CLI StateMachine（真实）
- 关键 bug 均已实锤: 全局模板单例污染（P0-1）、llm_reply 不调 LLM、每节点重放线性管线、假画像/假 PCR/假 Intent、权重公式丢 base、Meta 闭环零调用方、两套 EventBus/三个 Decider 命名分裂、CLI `dm decider` 命令连错对象

---

## 三、蓝图 P0 施工状态（✅ 已完成，本轮核心工作）

### 3.1 改动清单（本次会话）

| 文件 | 改动 |
|------|------|
| `core/agent/blueprint/engine.py` | **T1**: deepcopy 隔离全局模板 + RECOVERY strategy 保护 + cache key 去 hash 碰撞 + cache 返回副本 |
| `core/agent/blueprint/llm_dag_builder.py` | **T1**: converge `float()` 防崩 + `required` 严格布尔解析 |
| `core/agent/blueprint/skill_registry.py` | **T1**: `match("")` 空串守卫 |
| `core/agent/blueprint/executor.py` | **T2/T3/T4**: 完整重写——混合式（同步直调 PCR/DualTrack/UnifiedContext/Subgraph + llm_reply 多模式 + EventLog 节点记录 + DAG 快照 + 同 Tick 多轮收敛 + per-node 监控）|
| `core/agent/blueprint/decider.py` | **T2**: 瘦身为委托（统一执行路径，删双实现重复）|
| `core/agent/api/v3_session_api.py` | **T5**: Phase 3.5/5 改用真实 intent（DualTrack）+ 新执行器 + 快照 request_id |
| `core/agent/cli/engine.py` | **§7.7**: start_engine 启动异步预热 |
| `core/agent/orchestrator/bootstrap_v6.py` | **§7.7**: bootstrap 启动异步预热 |
| `core/agent/config/discourse_config.py` | **§7.7**: 修复 `Path.exists()` 权限崩溃（uv 3.13 + ~/.config ACL）|
| `core/infrastructure/model_service.py` | **§7.7**: `prewarm_models()` + `ModelService.warm_up` 复用全局单例（一份 BGE）|
| `tests/test_blueprint_v2.py` | **T6**: 契约测试 10 项（0.9s）|
| `tests/test_blueprint_v2_stress.py` | **T7**: 深度压力 16 项（slow 标记，~103s）|

### 3.2 测试状态

- 默认套件（not slow）: `tests/test_blueprint_v2.py + test_subgraph_v2.py + test_pcr_v2.py` → **59 passed / 4 xfailed**（7.1s）✅
- 压力套件: `pytest tests/test_blueprint_v2_stress.py -m slow` → **16 passed**（~103s）✅
- 压力覆盖: 并发 32×8 共享 executor / 同 request_id 并发快照 / 100 次重复稳定 / 50 次 build 无漂移 / 20 节点多 Tick / 乱序 fan-in / 环检测不挂起 / 极端输入 6 类 / EventLog/快照写失败降级
- 监控: TickResult 加 `node_latency`（每节点耗时随结果返回），执行非黑盒

### 3.3 统一异步预加载（§7.7，已落地）

- `prewarm_models(blocking=False)` 后台线程预热 SemanticEncoder + ModelService + PCR BGE 一条链路
- `ModelService.warm_up` 复用 `get_encoder()` 全局单例（实测 `svc._encoder is get_encoder()` = True，warm encode 135ms vs 冷 16.8s）
- 接入 `start_engine` + `bootstrap_v6`；修复 `discourse_config` 的 `Path.exists()` 权限崩溃

---

## 四、已记录的设计决策（§7.1-7.7，回查用）

| 决策 | 位置 | 实现 |
------|------|------|
| 执行层形态 = 混合式（同步 DAG 段 + 异步事件段 + EventLog）| DESIGN_DEEP_AUDIT §7.2 | ✅ 同步段完成，异步段 P1 |
| 关联链/元认知 = 独立服务（防广播风暴，M→1 定向通道）| §7.3 | ❌ P1 |
| DAG 快照 = 溯源 + 子图逆向扩展（expand_from_dag_trace）| §7.5 | ⚠️ 快照✅，扩展原语 P1 |
| 模式空间: route_mode（template/checkpoint/step）+ reply_mode（llm/template/user/bp）| §7.6 | ⚠️ reply_mode✅，route_mode P1 |
| 统一异步预加载（启动预热全部模型消费者）| §7.7 | ✅ 完成 |
| 子图建完整 · v4 原基础改造 | SUBGRAPH_DESIGN_OVERVIEW §7.2 | ✅ |
| zone↔intent_category 桥接 | DESIGN_SUBGRAPH §4.4 | ✅ |
| 子图溯源跨模块分层 | DESIGN_SUBGRAPH §11 | ✅ |
| 共享检索原语 + 前瞻预热 | DESIGN_SUBGRAPH §13 | ⚠️ 原语 P1 |
| CLI 白盒化哲学（A19）| DESIGN_CLI.md | ⚠️ CLI 假命令待修 |

---

## 五、未解决: CLI 基础设施问题

### 5.1 state.json 权限（已定位 = 环境差异 + 防御缺失）

```
3.11 (Hermes venv): ✅ start_engine running 49 subs / _save_state 正常 / get_engine OK
3.13 (.venv 审计环境): ❌ PermissionError: ~/.dialogmesh/state.json → start_engine 失败 → atexit 崩
根因: uv 3.13 下 Path.exists()/write_text 对 ~/.config|.dialogmesh 受限 ACL 抛 PermissionError
（与 discourse_config 同根因，后者已修）
定级: 环境部分 P1（生产 3.11 不受影响）；防御部分 P0 语义（_save_state 4 处无 try/except + atexit 无保护）
修复方向: _save_state 包 try/except + 失败降级项目内目录
状态: ❌ 未修（防御修复仍待做）
```

### 5.2 pytest hang（未定位）

```
现象: test_real_engine_integration 在 pytest 下 90s+ 超时，直接脚本 7-11s
已排除: NATS 重连（已修）、engine 创建
状态: ❌ 未定位（已标 slow 默认排除）
```

### 5.3 anaconda vs .venv 双环境

```
anaconda(3.9): pytest 可用 + sentence_transformers 坏（numpy/transformers 冲突）
.venv(3.13): 模型完整 + 无 pytest + fastapi 未装（v3_session_api 无法在 .venv import）
建议: Hermes 3.11 做 API 端到端；anaconda 跑测试；.venv 做模型探针
```

---

## 六、工作区未提交改动说明（压缩前核查）

### 6.1 本次会话改动（蓝图 P0，§三 清单）

### 6.2 之前会话改动（子图等，§一 清单 + agent_native/handlers/pcr_router_v2/engineering_bridges）

### 6.3 非本会话未知改动（未触碰，需确认来源）

```
?? .codegraph/（新目录）
M frontend/package.json + package-lock.json
M gateway/gateway.state.json
M persistence_rs/src/lib.rs
M .gitignore
M config/mood_profiles.yaml
M core/agent/association/semantic_coref.py
M core/agent/cli/commands/batch4_cmd.py + pcr_intent_cmd.py
M core/agent/api/v6_app.py
M docs/DESIGN_LEARNING_INGESTION.md
D 一批测试文件 + core/agent/api/api.py（交接 §6.1 已记录的删除，非本会话）
```

### 6.4 判断

- `D` 删除文件 = 之前其他会话的清理（测试归档），非本次；`api/api.py` 删除需确认 v6_app 已替代
- 未知改动非本会话所为，压缩后如要提交需先核对来源

---

## 七、压缩后恢复检查清单

```
1. ✅ tests/test_blueprint_v2.py = 10 passed（0.9s）
2. ✅ tests/test_subgraph_v2.py = 40 passed + tests/test_pcr_v2.py = 9 passed/3 xfail/1 skip
3. ✅ 压力套件 = 16 passed（显式 -m slow 跑，~103s）
4. ✅ docs/only/blueprint/ 6 文档 + probes/ 齐备
5. ✅ P0_RETRO_20260802.md 是设计↔实现对照表
6. ❌ state.json 防御修复未做（P1/P0 语义）
7. ➡️ 下一步 = P1（§八）
```

---

## 八、下一步: P1 待办清单（来自 P0_RETRO）

```
1. PlanGate 暂停 + CorrectionJournal（§7.6 截断点基础）
2. Meta 闭环: MetaFeedback 消费 EventLog + 权重副作用 + 权重公式 base 修复（skill_registry L248）
3. 关联链/元认知 EDA 独立服务（§7.3，防广播风暴）
4. expand_from_dag_trace（子图第三种扩展原语，§7.5）
5. route_mode checkpoint/step（§7.6）
6. PCR 模型统一（bge-small-zh-v1.5 → SemanticEncoder/ModelService，消除 fastembed 重试 ~5-8s）
7. API 层 Hermes 3.11 端到端验证（v3_session_api 需 fastapi + switch 网关）
8. CLI `dm blueprint/decider` 假命令修对象（连 GlobalDecider/StateMachine 而非蓝图 Decider）
9. 行为链 P0 修复性替换 `.behavior_graph.` → `.behavior.`（BEHAVIOR_DEEP_INVESTIGATION.md）
10. 蓝图学习闭环（§十四.4）——等执行产生真实 EventLog 后
```

## 九、测试命令（精确运行方式）

```powershell
# 默认套件（非 slow）
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
C:\Users\APTShark\anaconda3\python.exe -m pytest tests/test_blueprint_v2.py tests/test_subgraph_v2.py tests/test_pcr_v2.py -q --tb=short

# 压力套件（slow）
C:\Users\APTShark\anaconda3\python.exe -m pytest tests/test_blueprint_v2_stress.py -m slow -q --tb=short

# 模型探针（.venv）
.venv\Scripts\python.exe <探针脚本>
```

## 十、Windows 环境坑（压缩后回查）

- GitHub/网络: 用户开 clash 后可访问；沙箱内受限
- 中文文档: 严格 UTF-8 落盘 + 验证
- `.dialogmesh/state.json`: .venv 3.13 下不可写（权限）——用 3.11 Hermes 或修防御
- `~/.config/memorygraph/`: uv 3.13 `Path.exists()` 抛 PermissionError（已修 discourse_config）
- 模型: BGE 缓存于 .venv（bge-small-zh-v1.5 有缓存）；fastembed 无缓存时联网重试 5 次
- Start-Process PATH key collision；优先 Start-Job 或绝对路径

---

## 十一、模块完成度全景（压缩前统计，2026-08-02）

### 11.1 已审计 4 模块完成度

| 模块 | 源码规模 | 测试规模 | 测试通过 | 施工状态 |
|------|---------|---------|---------|---------|
| PCR | 26 文件 / 9,210 行 | 1 文件 / 175 行 | 9p / 3x / 1s | ✅ 设计+施工完成（X 距离 P1 接真实子图向量）|
| 子图 | 1 文件 / 655 行 | 1 文件 / 557 行 | **40p** | ✅ 完整施工（意图矩阵/修剪/溯源/扩展/zone 桥接）|
| 行为链 | 26 文件 / ~2,700 行 | **40 新增测试**（brain 9 + scheduler 23 + cli 8）| **124/124 全套绿** | ✅ **P0-P3+CLI 施工完成**（断链/质量/v4 接入/四层决策树/显式承诺/白盒命令）|
| 蓝图 | 9 文件 / 1,864 行 | 2 文件 / 472 行 | **26p**（10 契约+16 压力）| ✅ P0 施工完成（混合式执行+预热+快照+监控）|
| 关联链 | 26 文件 / ~9,000 行 | 4 文件 / ~1,100 行 | **103p + 压测 12p** | ✅ **Phase 0-6 全部完成**（断链根修→归一→冷路径→因果→范围→测试→服务化隔离）|

### 11.2 模块数量全景（官方统计，更新前）

- **10 条业务链**: 全部有文档+API（COMPLETENESS_AUDIT.md）——对话树/LLM回复/用户修改/元认知+持久化/行为链/关联链/工程链/画像惯性/元认知第二大脑/子图
- **39 篇设计文档**: 业务链引用仅 9/39（23%）——设计资产远多于接线
- **18 个引擎接入点**: 14/18 ✅，4 模块孤岛（CausalPromoter/TTLManager/BehaviorDiscovery.submit_to_meta/MetaSelfRepair）
- **37 个子系统**: CLI registry 实测（cli/registry.py build_dialogmesh_registry）
- **架构 10 维度评分**（ARCHITECTURE_QUANTIFIED.md, 7-25）: 80 分 / A 级；"Blueprint 设计冻结、代码=0"是当时最低项

### 11.3 我们施工后的增量（对照官方评分）

- 蓝图: "代码=0" → 26 测试绿 + 执行层真连通（评分表"未达 S 级原因"的 Blueprint 缺口已补）
- 关联链: "模块独立未接入" → **Phase 0-6 全部完成**（103 回归 + 12 压测；§7.3 独立服务 M→1 定向通道已落地）
- 行为链: "0 测试、断链待修" → **P0-P3+CLI 完成**（124/124 全套绿；断链/质量/v4 接入/四层决策树/显式承诺/白盒命令）

> 数据源: 代码行数=本次统计（core/agent 目录）；官方模块统计=docs/COMPLETENESS_AUDIT.md + docs/ARCHITECTURE_QUANTIFIED.md

---

## 十二、关联链审计完成态（2026-08-02，压缩前新增）

### 12.1 关联链审计三阶段 + 决策全部完成

| 文档 | 内容 |
|------|------|
| `docs/only/association/ASSOCIATION_AUDIT_ENTRY_20260802.md` | 资产盘点：设计 8+18 篇、实现 24+13 文件、断链 D1-D8、测试/配置全景 |
| `docs/only/association/DESIGN_DEEP_READ_ASSOCIATION_20260802.md` | 26 篇设计精读：定位演变 14 步、五层漏斗逐层解读、接口期望表、设计张力 |
| `docs/only/association/DESIGN_PHILOSOPHY_CHECK_20260802.md` | A1-A25 公理一致性检验：哲学裁决设计张力（A13 裁决信念双轨等）|
| `docs/only/association/ASSOCIATION_IMPL_AUDIT_20260802.md` | 实现审计：四套并行实现、断链根因链、接线审计、P0/F1-F8 + P1/F9-F14 清单 |
| `docs/only/association/DECISIONS_20260802.md` | **D-1~D-16 全部拍板（做完整）**——施工唯一依据 |

### 12.2 关键拍板（施工直接依据）

- **架构**: runtime engine 核心 + registry 装配 + v6_app/WS 交互 + CLI 白盒管理；先接线后服务化。
- **L2.5 信念**: 贝叶斯主干 + 单步/跨轮选择器（复用 PCR/AmbiguityGate 信号，不新建）。
- **漏斗糅合**: 一个组件库 + 粗细两个入口（funnel 内联层替换为分层组件调用）。
- **L5 因果**: 基板复活 + RelationSubstrate 解释层衔接；骨架库补 20；do-calculus 三方闭环。
- **范围**: 多意图拆分五链路、A23 检验三层（P0 溯源）、白盒完整 CRUD、PCR 接口、前置富化器、L4 三方闭环——全部做完整。

### 12.3 施工 Phase 0 断链根修清单（F1-F8）

| F# | 修复 | 文件 |
|---|------|------|
| F1 | `models.py` 替换 stub：迁回 `v3_2/causal_substrate/models.py` 正确 dataclass（CausalConstraints/SkeletonMatch 带 to_prior）| `association/models.py` |
| F2 | `skeleton_matcher.py` 对齐新 models | `association/skeleton_matcher.py` |
| F3 | `v3_2/causal_substrate/__init__.py` 修正 import | `v3_2/causal_substrate/__init__.py` |
| F4 | `v4/causal_substrate/source.py` 的 `V4CausalSubstrate` → 修正 | `v4/causal_substrate/source.py` |
| F5 | `runtime/engine.py` 冷路径接线（补 `_l1_extractor` + `_run_association_chain`）| `runtime/engine.py` |
| F6 | `event/subscribers.py` 依赖对齐（engine 补 `_l1_modifier`/`_l2_5_belief` 或改 key）| `event/subscribers.py` + `cli/registry.py` |
| F7 | `topic_quick_match.py` 修 `from __future__` 位置（SyntaxError 阻塞收集）| `compiler/topic_quick_match.py` |
| F8 | `event/cognitive_loop.py` 的 `slow_path()` → `process_chain()` | `event/cognitive_loop.py` |

### 12.4 测试/环境基线（压缩后回查）

- 关联链设计层测试: 13 passed（浅断言，需 A18 重写）；v3_2 旧测试: 40/41（1 挂 = F1 同根因）。
- anaconda 3.9: pytest 可用但 numpy 坏（pronoun_resolver/relation_graph SKIPPED）。
- .venv 3.13: 模型完整无 pytest；NATS 无服务器时 engine 启动重连风暴（anaconda 路径 allow_reconnect=False 未生效）。
- 施工验证命令: `anaconda3\python.exe -m pytest core/agent/v3_2/tests/test_causal_substrate core/agent/v3_2/tests/test_fusion core/agent/v3_2/tests/test_do_calculus -q --tb=short`

### 12.5 模块完成度更新

| 模块 | 审计 | 施工 | 决策 |
|------|------|------|------|
| 关联链 | ✅ 三阶段完成（5 文档）| ⏳ Phase 0 待开工（F1-F8）| ✅ D-1~D-16 拍板（做完整）|

> 恢复后第一件事: 按 §12.3 执行 F1-F8 断链根修（Phase 0），然后 Phase 1 归一（D-4~D-7）。完整施工顺序见 `DECISIONS_20260802.md §6`。

---

## 十三、关联链施工完成态（2026-08-02 晚，压缩前更新）

> **恢复入口（最高优先）**: `docs/only/association/ASSOCIATION_IMPL_PROGRESS_20260802.md`
> （Phase 0-5 全记录：改动文件、验证结果、修复清单、环境坑）。

### 13.1 施工进度（Phase 0-5 全部 ✅）

| Phase | 内容 | 验证 |
|-------|------|------|
| 0 | F1-F8 断链根修（models 迁回/v3_2+v4 import/runtime 冷路径/subscribers/cognitive_loop/topic_quick_match）| v3_2 旧测试 41/41 |
| 1 | D-4 信念主干 + 7D 决策；D-5 漏斗粗细双入口（run_layers）；D-6 L1 降级链判定；D-7 Adapter 一内核两门面 | 关联链回归 57/57 |
| 2 | D-1/D-3/D-15 runtime 冷路径实测（resolve→qualify→belief→L3）+ state machine 前置富化器 | 实测运行 |
| 3 | D-8 基板复活；D-9 骨架库 5→20；D-10 do-calculus HARD_BLOCK（内核+双门面）| 17/17 |
| 4 | D-11 validate_split+FusionDecider+AmbiguityGate/Resolver；D-12 溯源置信（A23×A24 发散/收束/可逆推）；D-13 `dm assoc` CRUD；D-14 zone→intent；D-16 triparty_reconcile | 57/57 |
| 5 | 质量核查修复 7 处 + 深层次测试 25 + 压测 9 | **全量 82/82 + 压测 9/9** |

### 13.2 本次会话新增/修改文件（回查清单）

- `core/agent/association/`: `models.py` `skeleton_library.py` `causal_substrate.py` `l2_5_belief.py` `l3_intent.py` `l4_temporal.py` `association_funnel.py` `pronoun_resolver.py` `causal_provenance.py`(新)
- `core/agent/intent/`: `fusion_decider.py`(新) `ambiguity_gate.py`(新)
- `core/agent/runtime/engine.py`（冷路径 + 白盒存储 + D-14 zone prior）
- `core/agent/event/`: `subscribers.py` `cognitive_loop.py` `handlers.py`（未改，验证过）
- `core/agent/cli/`: `commands/assoc_cmd.py`(新) `commands/__init__.py` `engine.py`（_save_state 加固）
- `core/agent/behavior/causal_adapter.py` + `core/agent/v4/causal_substrate/adapter.py`（HARD_BLOCK 尊重）
- `core/agent/v3_2/causal_substrate/__init__.py` + `core/agent/v4/causal_substrate/source.py`（import 修正）
- `core/agent/context/source.py`（内联第三份删除 → PEP562 lazy re-export）
- `core/agent/compiler/topic_quick_match.py`（from __future__ 修复）
- `config/l2_config.json`（l3.zone_intent_map 新增）
- `tests/test_association_deep.py`(新) + `tests/test_association_stress.py`(新)

### 13.3 质量核查修复（Phase 5 前，7 处）

1. `causal_provenance.diverge()` 行过滤优先级 bug → `startswith("机制")/("mechanism")`
2. `fusion_decider` weighted_mix 副作用污染 ChainVote → 局部 adj 权重
3. `fusion_decider` `std>0.5` 数学不可达（0-1 置信度 pstdev 最大 0.5）→ 诚实修正 `>0.45`
4. `engine` 冷路径 L3 取错 7D（第一个→best）
5. `l2_5_belief.ingest()` 3 次重算 `_best_intent()` → 复用
6. `l4_temporal.triparty_reconcile` turn 不递增/窗口不裁剪 → 修复
7. `association_funnel.run_layers` 每次定义内部类 → `SimpleNamespace`

### 13.4 剩余工作（恢复后下一步）

- **Phase 6 ✅ 已完成**（本轮）: 蓝图 §7.3 关联链 Event Sourcing 独立服务——`AssociationService`（M→1 定向通道 + EventLog 唯一事实源 + last_seq 增量追赶 + 崩溃重放 + 反压丢唤醒信号），engine `_publish` 定向投递（不广播），wire_subscribers 移除关联链广播订阅，blueprint executor `_handle_association` 真接。
- 待办: 蓝图 `P0_RETRO` P1 清单（§八）；行为链 P1 #9 断链可同步修（`docs/only/behavior/BEHAVIOR_DEEP_INVESTIGATION.md`）。

### 13.5 模块完成度更新（终版）

| 模块 | 审计 | 施工 | 决策 |
|------|------|------|------|
| 关联链 | ✅ 三阶段完成（5 文档）| ✅ **Phase 0-6 全部完成（103/103 回归 + 压测 12/12 + subscribers 8/8）** | ✅ D-1~D-16 做完整 |
| 剩余 | 蓝图 P0_RETRO P1（§八）、行为链 P1 #9 断链、PCR 模型统一、子图 expand_from_dag_trace、CLI dm blueprint 修对象 | — | — |

### 13.6 测试命令（恢复用）

```powershell
# 全量回归（103 项 = 82 旧 + 21 Phase6 新）
C:\Users\APTShark\anaconda3\python.exe -m pytest tests/test_association_funnel.py tests/test_l1_modifiers.py tests/test_l1_5_completer.py tests/test_l2_5_belief.py tests/test_l3_intent.py tests/test_multi_intent_split.py tests/test_l2_entity_graph.py tests/test_association_deep.py tests/test_association_service.py core/agent/v3_2/tests/test_causal_substrate core/agent/v3_2/tests/test_fusion core/agent/v3_2/tests/test_do_calculus -q --tb=short
# 压测（12 项 = 9 旧 + 3 Phase6 服务压测）
C:\Users\APTShark\anaconda3\python.exe -m pytest tests/test_association_stress.py -q --tb=short -m slow
# 广播订阅移除验证
C:\Users\APTShark\anaconda3\python.exe -m pytest core/agent/event/tests/test_subscribers.py -q --tb=short -p no:cacheprovider --rootdir=C:\Users\APTShark\PycharmProjects\DialogMesh
```

---

## 十四、行为链施工完成态（2026-08-02 压缩后新增）

> **恢复入口**: `docs/only/behavior/BEHAVIOR_IMPL_PROGRESS_20260802.md`（P0-P3+CLI 全记录：改动清单/验证/环境坑/剩余工作）

### 14.1 完成内容（A1-C3 拍板落地）

- **P0 断链**: training_loop/cold_indexer/consolidation 前缀替换；`core/agent/integration.py`（V32Pipeline）按 A1 归档到 `v3_2/un_use/`；AgentPipeline 静默 None 根修（persistence/observability/cognitive_compiler 三个门面 re-export/来源修正）→ `import core.agent` 全 OK，AgentPipeline 可实例化
- **P2 质量**: 预测四维权重/奖励七档/时间衰减/噪声门槛 25 项入 ParameterRegistry（A18）；BC05 §6.1 七档奖励内核（predictor+rewarder 共享 `evaluate_accuracy`）；ValueRanker 注入 load_est+prof_matcher（P1-2 两维度不再恒 0）；prompt 通用化；死实例清除（C1）；子串误判修正
- **P1 v4 接入**: `BehaviorBrain` 内核（ADR-013 后台先验）→ engine `_run_behavior_brain` + handlers BEHAVIOR 阶段 + runtime_hook 门面 + `shutdown()` join 防后台线程退出竞态
- **P3 新增**: 四层决策树 scheduler（L1 成本/L2 风险/L3 冷启动 ε/L4 CI）+ 显式承诺（when→should+rather_than+because、生命周期状态机、确定性匹配、双向回流、蒸馏 A24、B5 回退重模拟、B7 声明识别）
- **CLI**: `dm behavior show/predict/graph/config/distill` + `dm commitment list/add/arm/fire/complete/cancel/expire/match`（A19 白盒）

### 14.2 测试终态

| 套件 | 结果 |
|------|------|
| 行为链全套（新增 40 + 旧 84）| **124/124** |
| 关联链 103 + 蓝图 10 + 子图 40 + PCR 9 | **162/162** 无破坏 |
| subscribers 8 + parameter_registry 9 + compiler/l1/negative_kb/foa | **107/107** |

### 14.3 剩余工作（非本次范围，记录）

- B5 回退重模拟 engine 接线（PCR 特征板机触发时调用 `simulate_with_retry`）
- B7 显式承诺多视角识别跨模块接口（PCR/关联链/子图）
- 显式承诺持久化路径挂载（registry 已支持 store_path，engine/CLI 未挂固定路径）
- 蓝图 P1 清单（§八）：PlanGate/expand_from_dag_trace/route_mode/PCR 模型统一/CLI dm blueprint 修对象
