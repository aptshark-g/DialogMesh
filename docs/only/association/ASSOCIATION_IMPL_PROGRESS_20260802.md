# 关联链施工进度记录 — 2026-08-02（Phase 0-3 完成态）

> 目的: 记录关联链施工（按 DECISIONS_20260802.md §6）的实际落地与验证结果，作为继续施工与状态恢复的依据。
> 原则: 做完整；测试必须真实（A18）；一个内核多门面（红线 7）；不制造第 N 套并行实现。

---

## 1. Phase 0 — 断链根修（F1-F8）✅ 完成

| F# | 修复 | 文件 | 状态 |
|---|------|------|------|
| F1 | `models.py` stub 替换为正确 dataclass（`CausalConstraints` 6 字段 + `SkeletonMatch` 带 `to_prior()`）| `core/agent/association/models.py` | ✅ |
| F2 | `skeleton_matcher.py` 自动对齐新 models（`CausalConstraints(*mapped)` 6 元组 / `SkeletonMatch(roles,cov,cov,multi)`）| `skeleton_matcher.py` | ✅（F1 后自动成立）|
| F3 | `v3_2/causal_substrate/__init__.py` 修正为从顶层 `core.agent.association` re-export | `v3_2/causal_substrate/__init__.py` | ✅ |
| F4 | `v4/causal_substrate/source.py` `V4CausalSubstrate` → 本包 `CausalSubstrateAdapter`，retrieve 改读 adapter 内核 | `v4/causal_substrate/source.py` | ✅ |
| F5 | `runtime/engine.py` 冷路径接线：`_init_association_components()`（惰性、非致命）+ `_run_association_chain()`（resolve→qualify→belief→L3）| `runtime/engine.py` | ✅ |
| F6 | `event/subscribers.py` AssociationSubscriber 对齐新 L1（PronounResolver.resolve）+ 正式 `Evidence` ingest | `event/subscribers.py` | ✅ |
| F7 | `compiler/topic_quick_match.py` 修 `from __future__` 位置（SyntaxError 阻塞收集）| `compiler/topic_quick_match.py` | ✅ |
| F8 | `event/cognitive_loop.py` `cp.slow_path()` → `cp.process_chain()`（+triggered/updates 记录）| `event/cognitive_loop.py` | ✅ |

**附带根修**: `pronoun_resolver.py` `_check_stanza()` 从只捕 `ImportError` 改为捕宽泛异常——anaconda 环境 numpy 损坏导致 `import stanza` 抛 `ValueError` 被吞、`_l1_extractor` 恒 None（与审计同型的静默降级）。已修。

**验证**: 探针 8/8 OK；v3_2 旧测试包 **41/41 绿**；关联链设计层 **16/16 绿**（含 `test_l2_entity_graph` 3 项，F7 后收集正常）。

---

## 2. Phase 1 — 实现归一（D-4~D-7）✅ 完成

| 决策 | 落地 | 文件 |
|------|------|------|
| D-4 | `select_belief_mode()` A13 门控（PCR IntentContext complexity/noise + ambiguity 超阈值 → bayesian，否则 single_step）；`belief_dimension_score()` + `decision_scores()`（0.55 概率 + 0.45 7D）；`_best_intent()` 改用 7D 融合（A4 决策看 7 维）| `association/l2_5_belief.py` |
| D-5 | 旧漏斗糅合：`AssociationFunnel.run()` 保留为粗入口（每层最小逻辑）；新增 `run_layers()` 细入口（逐层调用分层组件完整 API：L1 EntityExtractor→L1.5 CollaborativeCompleter→L2.5 BeliefAccumulator→L3 MultiPerspectiveValidator→L4 L4TemporalEngine→L5 CausalSubstrate）| `association/association_funnel.py` |
| D-6 | L1 降级链判定：**保留** `l1_modifier.py`（`DepRelClassifier` config-driven 特征提取，被 CLI registry/命令/权限表引用，非死代码）；L1 主路径 = PronounResolver（内部已含模型→结构正则回退）| —（判定，无代码改动）|
| D-7 | `context/source.py` 内联第三份 `CausalSubstrateAdapter` 删除，改 PEP562 `__getattr__` 惰性 re-export 门面 A（`behavior/causal_adapter.py`）——一个内核 + 两个门面成立 | `context/source.py` |

**验证**: 关联链全量回归 **57/57 绿**；探针确认 `context.source.CausalSubstrateAdapter` 与 `v4.context` re-export 均指向 `core.agent.behavior.causal_adapter`；`select_belief_mode` 三态正确；`decision_scores` 进 status。

---

## 3. Phase 2 — 冷路径接线（D-1/D-3/D-15）✅ 核心完成

- **D-3/D-15**: runtime engine 冷路径实测运行——组件全加载、L2.5 真实 ingest（`belief turn=1`）、L3 出意图（`信息查询`，anaconda 环境 stanza 不可用走结构回退，符合设计降级）。
- **D-15 前置富化器**: `event/handlers.py` ASSOCIATION Phase 实测返回 `pronouns_resolved`/`deps_injected` 状态（不再静默无操作），state machine 8 阶段注册完整。
- **D-1**: 先接线验证漏斗，再做服务化隔离（蓝图 §7.3 顺序保留到 Phase 6）。

---

## 4. Phase 3 — L5 因果完整（D-8~D-10）✅ 完成

| 决策 | 落地 | 文件 |
|------|------|------|
| D-8 | 基板复活（F1/F2 已迁正确 models + matcher 对齐），`to_prior()` 上限 0.7 保持（A22）| `association/models.py` + `skeleton_matcher.py` |
| D-9 | 骨架库 **5 → 20**（设计 7 初始 + buffered/cascade/feedback 变体/汇聚/分发/循环等 13 扩展），`SkeletonMatcher` 契约不变 | `association/skeleton_library.py` |
| D-10 | do-calculus 负向验证接入内核：`verify_negative(from,to)`（HARD_BLOCK/WARN）+ `process_chain` 产出 `blocked` 标志 + `blocked_edges` 白盒日志；双门面（`behavior/causal_adapter.py` + `v4/causal_substrate/adapter.py`）对 blocked 边跳过权重更新 | `association/causal_substrate.py` + 两门面 |

**验证**: 17/17 绿（causal_substrate 5 + do_calculus 6 + l2_5 3 + funnel 2 + l3 1）；`verify_negative` 实测返回 WARN（弱信号默认宽容，HARD_BLOCK 仅在 P(do)≥0.95）；`process_chain` 带 blocked 标志。

---

## 5. 待施工（DECISIONS §6 剩余）

- **Phase 4 — 范围完整（D-11~D-16）**: 多意图拆分（L3 validate_split + 五链路 + FusionDecider + AmbiguityGate/Resolver）/ 因果检验三层（P0 溯源置信）/ 白盒 CRUD（`dm assoc` 系列）/ PCR zone→intent 映射表（D-14）/ L4 三方交汇（D-16）。
- **Phase 5 — 测试重写（A18）**: 黄金样例集 + 对抗性断言（现有 funnel/l2_5 测试多为浅断言）。
- **Phase 6 — 服务化隔离（蓝图 §7.3）**: 关联链 Event Sourcing 独立服务（M→1 定向通道，防广播风暴）。

**环境坑提醒**: anaconda 3.9 numpy 损坏 → stanza/pronoun_resolver 结构回退、transformers 版本检查失败；.venv 3.13 模型完整但无 pytest。恢复时用 anaconda 跑测试、用 .venv 验模型。

---

## 6. Phase 4 施工中（追加）

### D-14 PCR↔关联链 ✅
- `config/l2_config.json` 新增 `l3.zone_intent_map`（ATOMIC→信息查询 / PSYCHE→吐槽 / EXPLORE→探索 / PRECISION→诊断 / ABYSS→修复 / MIXED→信息查询），config-driven 零硬编码。
- `l3_intent.py` 新增 `zone_intent_prior(zone)`；`validate()` 在无假设时用 zone 先验种子（PCR 粗判 → L3 细验）。
- `runtime/engine.py` 冷路径 L3 假设优先取 zone prior。

### D-13 白盒 CRUD ✅
- 新建 `cli/commands/assoc_cmd.py`：`dm assoc show/get/add/edit/delete` + `dm assoc causal annotate`（关系 CRUD + 因果标注 + blocked 审计），已注册 `commands/__init__.py`。
- `runtime/engine.py` 新增 `_association_relations` / `_association_causal_annotations` 白盒存储。

### 附带加固 ✅
- `cli/engine.py` `_save_state()` 加 try/except（atexit 不再因权限/FS 异常崩——蓝图审计同型环境差异，任何环境都该防御）。

### D-11 多意图拆分（施工中）
- 现状: 五链路组件已存在（multi_perspective / coordinator / multi_intent_splitter / literal_chain / ambiguity_bridge）。
- 缺: `l3_intent.validate_split()`、FusionDecider（三策略）、AmbiguityGate（5 触发）+ AmbiguityResolver（5 级消解）。

### D-11 多意图拆分 ✅
- 新建 `intent/fusion_decider.py`：FusionDecider 三策略自动选（vote_consensus std<0.3 / weighted_mix 0.3-0.5 / llm_adjudicate std>0.5；PCR complexity>0.8 强制 LLM 裁决、noise>0.7 literal×1.5 discourse×0.7）。
- 新建 `intent/ambiguity_gate.py`：AmbiguityGate 5 触发（high_entropy/low_confidence/chain_disagreement/multi_intent_conflict/needs_clarification）+ AmbiguityResolver 5 级消解（上下文继承→行为链→画像→LLM→ask_user，成本升序）。
- `l3_intent.py` 新增 `validate_split()`：拆分方案逐段四视角验证 + 聚合裁决（无上下文时保守拒绝，符合真实原则）。

### D-12 因果检验 P0 溯源置信层（A23 × A24 融合）✅
- **设计升级（用户拍板）**: P0 不是单一"来源查表"，而是把 A24 逆向动力系统（DMN 发散→ECN 收束→可逆推）与 A23 溯源置信统一。
- 新建 `association/causal_provenance.py`：
  - `diverge()`（DMN 发散）: 掩盖上下文，LLM 高温度(0.8)无约束候选假设 + 规则来源（键合图/行为链/骨架）结构假设。
  - `converge()`（ECN 收束）: do-calculus HARD_BLOCK 第一道负向筛选 → 证据覆盖检查 → 驳回假设记录拒绝理由（知识边界学习）→ 来源融合置信。
  - 来源置信度: 键合图 0.95 / 人工 0.9 / 行为链 0.7 / do-calculus 0.6 / LLM 0.3-0.5；融合 `1-∏(1-max_conf)`。
  - 可逆推验收（A24）: coverage 60-80% 目标；coverage=1.0 → 过拟合拒绝，coverage<40% → 没学到拒绝。
- 验证: HARD_BLOCK 排除 / 无证据不通过 / coverage 1.0 判过拟合，全部符合设计。

### D-16 L4 三方交汇 ✅
- `l4_temporal.py` 新增 `triparty_reconcile(behavior_sequences, engineering_constraints)`：
  - 行为链 A→B 序列 → 注入转移计数（真实支持强化矩阵）。
  - 工程链约束（forbidden_transitions / resource_constraints）→ 阻断违反约束的转移（A14: 约束在事实中）。
  - 三方数据格式统一为 `(from, to, weight)`。
- 验证: 行为链注入生效（FIX→EXPLORE、EXPLORE→QUERY 入矩阵）；工程链阻断生效（FIX→EXPLORE 因 resource_constraints 被移出矩阵）。

### Phase 4 完成态
| # | 项 | 状态 |
|---|----|------|
| D-11 | 多意图拆分（validate_split + FusionDecider + AmbiguityGate/Resolver）| ✅ |
| D-12 | 因果检验 P0 溯源置信层（A23 × A24 发散/收束/可逆推）| ✅ |
| D-13 | 白盒 CRUD（`dm assoc` 系列）| ✅ |
| D-14 | PCR zone→intent 映射表接 L3 | ✅ |
| D-16 | L4 三方交汇（triparty_reconcile）| ✅ |

**剩余**: Phase 5 测试重写（A18 黄金样例集 + 对抗性断言，现 funnel/l2_5 测试多为浅断言）；Phase 6 服务化隔离（蓝图 §7.3 Event Sourcing 独立服务）。

---

## 7. 质量核查 + Phase 5 测试重写（A18）✅

### 质量核查修复（先核查后测试，用户要求）
| # | 问题 | 修复 |
|---|------|------|
| 1 | `causal_provenance.py` `diverge()` 行过滤优先级 bug（`and` 优先 `or` → 任意 >4 字符行被当假设）| 改为 `startswith("机制") or startswith("mechanism")` |
| 2 | `fusion_decider.py` weighted_mix 在 score 计算后修改 ChainVote（副作用 + 对决策无效）| 改为局部 `adj` 权重字典，不污染调用方对象 |
| 3 | `fusion_decider.py` `std>0.5 → llm_adjudicate` 数学不可达（0-1 置信度 pstdev 理论最大 0.5）| 阈值诚实修正为 `>0.45`（高分歧真实可达）|
| 4 | `engine.py` 冷路径 L3 取第一个 intent 的 7D | 改为取 `_best_intent()` 的 7D |
| 5 | `l2_5_belief.py` `ingest()` 3 次重算 `_best_intent()` | 复用一次局部变量 |
| 6 | `l4_temporal.py` triparty 注入序列时 `_total_turns` 不递增、窗口不裁剪 | 递增 turn + 裁剪窗口 |
| 7 | `association_funnel.py` run_layers 每次定义内部类 | 改用 `SimpleNamespace` |

### Phase 5 测试（A18：黄金样例集 + 对抗性断言，拒绝浅断言）

**深层次测试 `tests/test_association_deep.py`（25 项）**: 覆盖 D-4（A13 门控边界 0.8/0.7/0.5）、贝叶斯收敛真实性、7D 决策面、骨架库 20 完整性 + requires 字段合法性、`to_prior()` 上限 0.7、HARD_BLOCK 短路、溯源融合数学精确（1-∏(1-c)=0.985）、coverage 1.0 过拟合拒绝、diverge 行过滤、FusionDecider 三策略边界 + PCR 强制 LLM + **无副作用断言**、AmbiguityGate 升级路径、Resolver 5 级顺序、validate_split 保守裁决、triparty 注入/阻断/窗口、run_layers 六层完整。

**压测 `tests/test_association_stress.py`（9 项, `-m slow`）**: 500 轮 belief 收敛 <2s、10k 转移矩阵 <3s、15 步长链触发 + prior≤0.7、1000 骨架匹配 <2s、5000 序列三方调和 <3s、100 次 run_layers <10s。

**验证**: 深层次 25/25 ✅；压测 9/9 ✅；全量回归 **82/82** ✅（57 旧 + 25 深层次）。

---

## 8. Phase 6 — 服务化隔离（蓝图 §7.3 / DESIGN_HYBRID §四/§六）✅ 完成

**目标**: 关联链从"广播订阅"改为**独立服务**（M→1 定向通道 + EventLog Event Sourcing），防广播风暴。

### 落地（一内核 + 薄门面，红线 7）

| 项 | 内容 | 文件 |
|---|------|------|
| 服务内核 | `AssociationService`: M→1 定向通道（有界唤醒队列）+ EventLog 唯一事实源 + last_seq 增量追赶 + 崩溃重放 + 反压丢唤醒信号+计数 + 纯函数 evolve + 触发阈值（topic_shift≥2 / behavior≥10）+ 同步 C/S `pull()` + 白盒 `stats()` | `association/association_service.py`(新) |
| engine 接线 | `_publish` 对关联链关心的 6 类主题**定向投递**（不广播）；`_route_pipeline_events` 将 state machine 阶段结果映射为事件（pcr/intent/discourse/behavior/meta/profile + intent 类别变化→topic_switched）；发现回调写白盒 + tracer 指标 | `runtime/engine.py` |
| 门面归一 | `assoc_subscriber.py` 与 `v4/assoc_subscriber.py` 均为薄门面指向服务内核（第三份并行实现消除） | `assoc_subscriber.py` / `v4/assoc_subscriber.py` |
| 广播移除 | `wire_subscribers` 不再注册 association 广播订阅（§7.3） | `event/subscribers.py` |
| executor 真接 | `_handle_association` 从 deferred stub → 定向投递服务（无 service 时显式 unavailable） | `blueprint/executor.py` |
| CLI 监控 | `dm assoc show/get service` 暴露服务 stats（队列/发现/消费/丢弃/重放/错误） | `cli/commands/assoc_cmd.py` |

### 监控驱动修复（真实缺陷，非表面）

1. **`stop()` 死锁**: `queue_size` 满时 `_queue.put(None)` 阻塞（Queue.put 默认阻塞）→ 改 `put_nowait(_WAKE)`。
2. **EventLog 并发事务冲突**: 多线程 `put_event` 报 `cannot start a transaction within a transaction` → `_log_lock` 串行化写入（§六：写入单线程强一致）。
3. **重复消费（consumed>enqueued）**: 队列事件与 `_replay_unconsumed` 并发处理同一批未 ack 事件；且发现产出 `association_discovered` 落入消费循环回流。→ 队列改**纯唤醒信号**（EventLog 唯一事实源，天然去重）+ 发现产出写后立即 ack。对账 `consumed == enqueued`、`unconsumed == 0` 精确成立。

### 测试（A18 对抗性断言）

- `tests/test_association_service.py`（21 项）: M→1 不广播/拒绝非主题、EventLog 幂等、崩溃重放、ack 后不重放、反压丢最旧+EventLog 兜底、触发阈值（topic/behavior/低于阈值不误触发）、evolve 纯函数+重放收敛、C/S pull、生命周期幂等、白盒 stats、engine 路由→发现闭环、tracer 指标、wire 移除广播、executor 真接/unavailable 无伪数据、CLI show/get service 监控。
- `tests/test_association_stress.py` 新增 3 项（`-m slow`）: 2000 事件吞吐精确对账、5000 反压 EventLog 不损坏不丢、4 线程并发 enqueue 无事务冲突。

**验证**: 关联链全量回归 **103/103** ✅（82 旧 + 21 新）；压测 **12/12** ✅（9 旧 + 3 新）；`event/tests/test_subscribers.py` **8/8** ✅（wire 数量 6→5 断言已同步）。

### 环境坑（回查）

- anaconda 3.9: `EventLog.stats` 是 property 不是方法（测试断言需 `stats["total"]`）。
- `AgentPipeline lazy import failed: No module named 'core.agent.v3_2.integration'` —— 行为链断链，非关联链问题（P1 #9 待修）。

--- END OF DOCUMENT ---
