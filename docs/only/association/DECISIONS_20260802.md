# 关联链拍板决策记录 — 2026-08-02

> 目的: 固化关联链审计后的全部拍板决策（D-1~D-16），作为施工的唯一依据。
> 原则: 用户明确要求——**做完整，不做简化**（与 PCR/子图/蓝图施工的既有偏好一致）。
> 前置: `ASSOCIATION_AUDIT_ENTRY_20260802.md` + `DESIGN_DEEP_READ_ASSOCIATION_20260802.md` + `DESIGN_PHILOSOPHY_CHECK_20260802.md` + `ASSOCIATION_IMPL_AUDIT_20260802.md`。

---

## 1. 决策总览

| # | 议题 | 拍板 | 哲学依据 |
|---|------|------|---------|
| D-1 | 冷路径接线方式 | **先接线验证漏斗，再服务化隔离**（蓝图 §7.3 顺序）| A16 快反馈后修正 |
| D-2 | 三套 engine 路径归一 | **runtime engine 为核心 + registry 装配 + v6_app/WS 交互 + CLI 保留为白盒管理通道** | A19 白盒化 + P22 |
| D-3 | 死代码处置 | `_run_association_chain` **补实现**（前置富化器接入），不删 | A6 修正回流必须有 |
| D-4 | L2.5 信念归一 | **贝叶斯为主干 + 单步/跨轮选择器**（①=②一体）；选择器复用 PCR `IntentContext` + `AmbiguityGate` 信号，**不新建模块** | A13 两种力度 |
| D-5 | 旧漏斗去留 | **糅合为粗细颗粒度**：一个组件库 + 粗细两个入口（funnel 内联层替换为分层组件调用）| A2 颗粒度 + A16 |
| D-6 | L1 新旧契约 | **降级链 = 模型→结构正则回退**（PronounResolver 已含）；旧 `l1_modifier.py` deprel 分类按用途保留或归档 | A16 兜底 |
| D-7 | 三处 Adapter 归一 | **一个内核 + 两个门面**（ContextSource 版 + RuntimeAdapter 版）；`context/source.py` 内联第三份删除 | P1 多认知域投影 |
| D-8 | L5 实现路线 | **做完整**：基板复活（迁正确 models + 三步映射）**与** RelationSubstrate 解释层（mechanism）**衔接**——基板产 prior、解释层产 mechanism | A22 因果克制 + A3 |
| D-9 | 骨架库规模 | **补齐 20 个**（按 ENGINEERING_V3_3 清单）| 做完整 |
| D-10 | do-calculus 接入 | **接入完整闭环**：行为链 weight updater（HARD_BLOCK 阻断）+ 子图/工程链 + 元认知审核 | A22 负向验证 |
| D-11 | 多意图拆分 | **本次纳入 L3 扩展**：五链路并行 + FusionDecider + AmbiguityGate/Resolver | 做完整 |
| D-12 | A23 检验型三层 | **全部立项**：溯源置信层 → 反事实推导 → 仿真检验（P0 溯源）| A23 + P26 |
| D-13 | 白盒 CRUD | **完整 CRUD**（含因果标注），`dm assoc` 系列命令 | A19 + P22 |
| D-14 | PCR↔关联链接口 | **接入**：zone→intent 映射表接 L3（DISCUSSION_PARALLEL_REUSE P0）| P4 先验双向 |
| D-15 | 前置富化器位置 | **挂在 discourse 切分前**（event/handlers ASSOCIATION Phase），与 D-3 冷路径绑定 | 07-31 设计修正 |
| D-16 | L4 三方交汇 | **完整三方闭环**：关联链×行为链×工程链数据格式对齐 + 交互 | A14 约束在事实中 |

---

## 2. 架构级决策详情（D-1 ~ D-3）

### D-1 冷路径接线：先接线、后服务化

- **顺序**: F1-F8 断链根修 → runtime 冷路径接线（漏斗跑通）→ 蓝图 §7.3 独立服务化（Event Sourcing 隔离）。
- **理由**: 先验证漏斗正确性（组件级可运行），再做服务化隔离；跳过验证直接服务化会把断链带进新架构。

### D-2 三 engine 归一：runtime 核心 + registry 装配 + WS 交互 + CLI 白盒

```
组件装配层:  CLI registry（build_dialogmesh_registry + lazy loader）——DI 全集，保留
核心运行层:  runtime/engine.py（CognitiveRuntimeEngine）——唯一运行核心
交互层:     v6_app.py（FastAPI）+ ws_bridge（WebSocket）——面向用户/前端
白盒管理:   CLI 命令（dm assoc ...）——查改增删通道（A19），不承载运行时交互
```

- CLI 单例（`start_engine` 全局 `_engine`）不再作为长期运行载体；服务化交互走 v6_app/WS。
- `agent_native.py`（AgentOrchestrator）作为 v6 编排层保留，与 runtime engine 的关系后续对齐（当前 CognitionHub 在其上真实加载）。

### D-3 死代码处置：补实现

- `runtime/engine.py` 的 `_l1_extractor` 赋值 + `_run_association_chain` 实现（前置富化器：resolve→enriched→qualify），接入 D-15。

---

## 3. 实现归一决策详情（D-4 ~ D-7）

### D-4 L2.5 信念：贝叶斯主干 + 单步/跨轮选择器（一体）

- **①=② 是一体**: 贝叶斯是主干；单步可解时用 7D 投票式直接判断，跨轮收敛时进贝叶斯序贯。
- **选择器不新建**: 复用 PCR `IntentContext`（complexity/noise）+ `AmbiguityGate`（ambiguity_score）作为信号源——`entropy/ambiguity 超阈值 → 进贝叶斯`的门控函数。
- **7D 变真正决策维度**: `l2_5_belief.py` 的 7D 从"说明字段"升级为决策输入（A4）。
- **`hypothesis/` 包关系**: 离散投票实现保留为"单步可解"路径的实现载体（A13 证据投票力度）。

### D-5 旧漏斗糅合：一个组件库 + 粗细两个入口

- **粗入口**: `AssociationFunnel.run()`（一次跑完五层，拿整体结论——缩小到国家级摘要）。
- **细入口**: 分层组件逐层调用（L1→L1.5→L2→L2.5→L3→L4→L5——放大到省份）。
- **红线**: 不保留两套内联实现——`association_funnel.py` 内联的简化层（Layer1Syntactic 等）替换为分层组件调用；粗 = 每层最小逻辑，细 = 每层完整逻辑。
- **对应 A2**: 同一漏斗的递归缩放，不是两套漏斗。

### D-6 L1 新旧契约：降级链 = 模型→结构回退

- 新 L1 = PronounResolver（text 输入，zh 用 parse-only pipeline + PRON→最近前序 NOUN/PROPN 结构回退）——已含正确降级。
- 旧 `l1_modifier.py`（stanza Document 契约）**依赖更重，不是降级选项**；其 deprel 分类若与 PCR 结构特征相关则保留为特征提取，否则归档 `un_use`。
- 降级链定义: 模型可用 → PronounResolver 全功能；模型不可用 → 结构正则回退（`_zh_structural_chains`）。

### D-7 三处 Adapter：一个内核 + 两个门面

- **内核**: `association/causal_substrate.py` CausalSubstrate（F1/F2 修好后唯一实现）。
- **门面 A**: `behavior/causal_adapter.py` CausalSubstrateAdapter（ContextSource 版，供 ContextAssembler 检索）。
- **门面 B**: `v4/causal_substrate/adapter.py` CausalSubstrateAdapter（RuntimeAdapter 版，供 v4 slow path 执行）。
- **删除**: `context/source.py` 内联第三份（合并到门面 A）；`v4/causal_substrate/source.py` 的 `V4CausalSubstrate` 引用修正（F4）。

---

## 4. L5 因果完整路线（D-8 ~ D-10）

### D-8 基板 + 解释层衔接（做完整）

```
发现型三层（A22）:
  粗发现:  CausalSubstrate 三步映射 → structural_prior（≤0.7）→ BehaviorEdge.δ
  负向验证: do-calculus 后门准则 → HARD_BLOCK（排除，不发现）
  深度确认: 键合图/Petri/系统动力学（离线，人工标注）

解释层（RelationSubstrate）:
  conf>0.8 + ≥2 来源 + mechanism → causal explanation（供 LLM 上下文）

衔接: 基板产 prior（先验骨架），解释层产 mechanism（可解释性），prior 满足条件时晋升为 mechanism 候选
```

- F1/F2（models 迁回 + matcher 对齐）是基板复活的第一步。
- 骨架库补齐 20（D-9）: 按 ENGINEERING_V3_3 的 7 个初始 + 扩展（buffered/cascade 等）。

### D-10 do-calculus 接入完整闭环

- 行为链 weight updater: HARD_BLOCK 阻断不合理的因果边更新。
- 子图/工程链: 约束满足做伪因果晋升候选筛选（A14）。
- 元认知审核: 伪因果→用户确认→实因果的晋升/降级路径。

---

## 5. 范围决策（D-11 ~ D-16，全部做完整）

| # | 项 | 完整范围 |
|---|----|---------|
| D-11 | 多意图拆分 | 五链路并行（画像/关联/话语/字面/工程）+ FusionDecider（三策略自动选）+ AmbiguityGate（5 触发）+ AmbiguityResolver（5 级消解）|
| D-12 | 因果检验三层 | P0 溯源置信层（来源链决定可信度：键合图 0.95/人工 0.9/LLM 0.3-0.5）→ P1 反事实推导（必要性/可逆性/部分干预）→ P2 仿真检验（matlab）|
| D-13 | 白盒 CRUD | `dm assoc show/get/add/edit/delete` + `dm assoc causal annotate` + API 端点（/relations /causal /belief 从空壳补齐）|
| D-14 | PCR↔关联链 | zone→intent_category 映射表 + `IntentContext` 注入 L3 先验 + 画像反哺（P4 双向）|
| D-15 | 前置富化器 | event/handlers ASSOCIATION Phase 挂 discourse 切分前：resolve→enriched→qualify→cut 管线 + runtime 冷路径绑定（D-3）|
| D-16 | L4 三方交汇 | 关联链提供 A↔B 边权重、行为链提供 A→B 序列、工程链提供约束条件；三者数据格式对齐 + 交互验证 |

---

## 6. 施工顺序（完整版）

```
Phase 0 — 断链根修（F1-F8）: 关联链组件全部可 import/可运行，旧测试 41/41 绿
Phase 1 — 实现归一（D-4~D-7）: 信念主干 + 漏斗粗细入口 + L1 降级链 + Adapter 两门面
Phase 2 — 冷路径接线（D-1/D-3/D-15）: runtime 首次真正跑关联链 + 前置富化器
Phase 3 — L5 因果完整（D-8~D-10）: 基板复活 + 骨架 20 + do-calculus 闭环
Phase 4 — 范围完整（D-11~D-16）: 多意图拆分 + 因果检验三层 + 白盒 CRUD + PCR 接口 + L4 三方
Phase 5 — 测试重写（A18）: 黄金样例集 + 对抗性断言，拒绝浅断言
Phase 6 — 服务化隔离（蓝图 §7.3）: Event Sourcing 冷路径，关联链独立服务
```

---

## 7. 记录在案的约束（施工红线）

1. **冷热分层不可丢**（A16）: Fast/Async/Slow 路径骨架保留。
2. **关系必须可查询**（A3）: RelationSubstrate 必须有产出路径。
3. **修正回流必须有**（A6）: 用户改 L1.5/L2/L5 必须回流。
4. **测试必须真实**（A18）: 黄金样例集 + 对抗性断言，拒绝浅断言。
5. **白盒通道必须建**（A19/P22）: `dm assoc` 系列。
6. **因果克制**（A22/P25）: prior≤0.7 + do-calculus 负向验证，绝不输出 1.0。
7. **不制造第 N 套并行实现**: 所有糅合/归一以"一个内核 + 多门面"为原则。

--- END OF DOCUMENT ---
