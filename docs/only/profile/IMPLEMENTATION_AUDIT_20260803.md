# 画像模块实现审计（阶段二）— 2026-08-03

> 范围：三套画像体系 21 文件精读（OCEAN/行为侧/user_engine）+ v4/cognitive 双轨家族全读 + import 探针 + 引用方全查（engine/CLI/StateMachine/handlers/subscribers/subgraph/L3/intent/PCR/persistence）。
> 方法：anaconda 3.9 实跑 import 探针；rg 全库引用追踪；逐文件精读。

---

## 一、核心发现（四句话）

1. `_cognitive_profile`（CognitiveProfileV2 双轨画像）生产路径从未实例化：engine.py:164 初始化为 None，全库 `CognitiveProfileV2(` 实例化点仅 tests → 双轨架构（Track A/B + Fusion + Convergence + ProfileStore）全部纸面。
2. 唯一活的画像 = OCEAN 画像，且只在 CLI 主路径：cli/engine.py:316-317 挂载 `_ocean_analyst` → PROFILE 阶段（handlers.py:218-231）逐轮 analyze → 子图编译器（subgraph_compiler.py:210-220）读 P/F 域。API/直接实例化路径无 OCEAN 画像。
3. PROFILE_GAP.md 声称"全部修复 ~95%"与实况不符：TrackA EMA（PCR→TrackA）、TagLayer.infer_from_trace、ConvergenceEngine.update 三处全库无调用方；OCEAN 是逐轮 analyze 而非文档说的每 10 轮 update。实际有效实现率约 30-40%。
4. 画像↔L3 意图接口断了：engine.py:470 调 validate() 不传 profile_traits → `_profile_vote`（读 OCEAN C 阈值）永远 ABSTAIN；intent/coordinator.py 的 profile 参数只是签名，未接线。

---

## 二、import 探针实况（anaconda 3.9）

| 目标 | 结果 | 说明 |
|---|---|---|
| v4.cognitive.ocean_profile（OCEANProfile/OCEANProfileAnalyst）| ✅ import OK | 自洽 |
| predictor.cognitive_profile（CognitiveProfile/ProfileUpdater/EnhancedProfileMatcher/ProfileStore）| ✅ import OK | 行为侧，brain.py 已接线 |
| user_engine（UserProfile/UserManager/UserExtractor/ConsistencyChecker）| ✅ import OK | context_manager 懒加载 |
| v4.cognitive.models.CognitiveProfileV2 | ✅ import OK | 仅 tests 实例化 |
| v4.cognitive.llm_profile_analyst | ✅ import OK | 0 引用 = 死代码 |
| compiler.profile_source（ProfileContextSource）| ✅ import OK | 0 引用 = P 域源未注册 |
| v4.cognitive.tag_layer.TagLayerManager | ✅ import OK | 0 引用 = 死代码 |
| v4.cognitive.inertia_graph.InertiaWeightGraph | ✅ import OK | CLI 挂载但无喂数据 |
| meta.ocean_profile | ❌ 模块不存在 | 恢复规划预告"双类"需修正（实际三套体系）|

---

## 三、三套画像体系演进图谱

```
OCEAN 认知画像（LLM 逐轮）:
  v4/cognitive/ocean_profile.py（OCEANProfile 10 维 EMA α=0.3 + MBTI 近似 + to_llm_context）
    ├─ CLI 挂载 _ocean_analyst → handlers PROFILE 阶段 analyze() → 子图 P/F 域
    ├─ bfi_calibrator.py（BFI-10 校准 → analyze_with_bfi_override，无调用方）
    └─ CLI registry 双名注册不一致（registry.py:379 OCEANProfileAnalyst vs subsystem_registrations.py:46 OCEANProfile）

行为侧画像（算法+LLM 会话推断）:
  predictor/cognitive_profile.py（expertise 10 域 + preferences + stable_traits 8 项 + tags）
    ├─ ProfileUpdater.record_action（EMA 更新 expertise/preferences/metacognition/divergence/confidence）
    ├─ EnhancedProfileMatcher.match（行为候选排序，brain.py 注入 ValueRanker）
    └─ brain.py 接线 ✅（behavior 审计 69/69 + 压测 18/18）

用户引擎画像（v3 路径，规则+小模型）:
  user_engine/user_profile.py（tech_level/domains/entities/style/language/patience/preferred_tools/attention_span/topic_switch_rate/last_intent）
    ├─ UserManager（SQLite users/sessions 表，跨会话自动加载）
    ├─ UserExtractor（注入过滤 + 规则提取 + 小模型融合）
    ├─ ConsistencyChecker（tech/patience/style 一致性校验，min_history=3）
    └─ context_manager/discourse_manager.py:143-144 懒加载 UserManager（v3 路径，engine 主路径不触达）

双轨 CognitiveProfileV2（v2 设计家族，全部纸面）:
  models.py(CognitiveProfileV2/CognitiveDynamics/UserTag/MemoryPoint/MemoryChunk)
    ├─ dynamics.py(DynamicsComputer 9 维计算) / tag_layer.py(TagAcquisitionEngine L1/L2 + GFactorInferencer)
    ├─ convergence.py(ConvergenceEngine EMA + ProfileStore SQLite) / fusion.py(FusionContext 渲染)
    ├─ memory_extractor.py(MemoryExtractor/MemoryManager) / inertia_graph.py(InertiaWeightGraph 链08 v2)
    ├─ llm_profile_analyst.py(三源融合,死) / signal_filter.py(ProfileSignalFilter,死)
    生产路径: _cognitive_profile = None → 全部未接线
```

---

## 四、接线追踪（谁在生产路径）

| 路径 | 画像用什么 | 实况 |
|---|---|---|
| CLI 主路径（start_engine）| _ocean_analyst（OCEANProfileAnalyst）| ✅ 挂载；PROFILE 阶段逐轮 analyze；子图 P/F 域有数据 |
| API（v6_app）| 无 | ❌ get_engine 若自动 start 走 A 路径则有；_create_engine_instance（B 路径）无 |
| StateMachine PROFILE 阶段 | handle_profile（handlers.py:218-231）| 🟡 已注册；run_pipeline 从 DISCOURSE/PCR 起会经过；依赖 _ocean_analyst 存在 |
| legacy on_event 主路径 | _feed_profile/_feed_trackb（engine.py:890-891）| ❌ 方法不存在于 CognitiveRuntimeEngine；调用在死代码 _on_event_continue；handlers.py:172 hasattr 静默跳过 |
| 行为链 brain.py | predictor.cognitive_profile | ✅ 已接线（behavior 审计 P0-P3）|
| context_manager（v3）| user_engine | 🟡 discourse_manager 懒加载；engine 主路径不触达 |
| 子图编译器 | engine._ocean_analyst.profile（subgraph_compiler.py:210-220 P/F 域）| ✅ CLI 路径活；B 路径/API 无 → "P/F 域取不到 profile"根因 |
| L3 意图验证 | _profile_vote（l3_intent.py:200-211 读 OCEAN C）| ❌ engine 调 validate() 不传 profile_traits → 永远 ABSTAIN |
| PCR | CognitiveProfile_v1（datacontract.py）| ✅ PCR 输出契约在；PCR→TrackA EMA 无实现（声称 ✅ 实为 ❌）|
| ContextCompiler P 域 | ProfileContextSource（profile_source.py）| ❌ 0 引用 = 未注册 → P 域画像源断 |

---

## 五、断链/死代码/静默降级清单

### 5.1 断链（🔴）

1. `_feed_profile`/`_feed_trackb` 幽灵调用：engine.py:890-891 调用类上不存在的方法（仅 un_use/engine_legacy 有定义）。外层 `_on_event_continue` 无调用方 → 不炸但不执行；handlers.py:172 hasattr 检查静默跳过 → TrackB 画像更新从未运行。
2. PROFILE_GAP 声称的 TrackA EMA / TagLayer infer_from_trace / ConvergenceEngine.update 全无调用方 → 文档声称与代码不符。

### 5.2 死代码（🟡）

1. v4/cognitive/llm_profile_analyst.py（LLMProfileAnalyst 三源融合）0 引用
2. compiler/profile_source.py（ProfileContextSource P 域源）0 引用
3. v4/cognitive/tag_layer.py 的 TagLayerManager 0 引用（TagAcquisitionEngine 仅 bridge 注册）
4. v4/cognitive/signal_filter.py（ProfileSignalFilter）0 引用
5. predictor/profile_matcher.py（ProfileMatcher）1 引用且与 EnhancedProfileMatcher 重复
6. v4/cognitive/inertia_graph.py：CLI 挂载 _inertia_graph 但 detect_quality_centric/add_evidence 无调用方 → 链08 v2 惯性权重图半成品（设计完整、实现未喂数据）
7. ocean_profile.analyze_with_bfi_override：实现完整（BFI 先校准再 EMA）但无调用方

### 5.3 契约不一致（🟡）

1. CLI 注册双名：registry.py:379 "ocean_analyst" → OCEANProfileAnalyst vs subsystem_registrations.py:46 "ocean_analyst" → OCEANProfile（不同类同名）
2. OCEANProfileAnalyst 无 update_dimension：p4_cmd.py cmd_profile_edit 调 ocean.update_dimension → 永远走 else "not available"
3. OCEANProfileAnalyst 无 snapshot：p4_cmd.py cmd_profile_traits 调 ocean.snapshot() → 同断
4. cli.py cmd_profile 读 data/profile/ocean_profile.json：OCEANProfile.save() 有实现但无调用方 → 文件永不写入 → "No profile yet"
5. p10_cmd.py:111 调 ocean.analyze(session_id=sid)：OCEANProfileAnalyst.analyze 签名是 (engine, turn_text, llm_response) → 签名不匹配 → CLI 死命令

---

## 六、画像↔对话树接口（KERNEL_ABSORPTION 对照）

| 对话树内核需求 | 画像侧现状 | 缺口 |
|---|---|---|
| 组块边界 ← 用户认知状态（疲劳/注意力/惯性）| OCEAN 无认知状态字段；Track A cognitive_resource/attention_anchor 纸面 | 对话树 compiler 未读画像（需验证 discourse_block_tree 是否有画像输入）|
| 摘要 = 个体化记忆痕迹（KERNEL §九）| 无画像参与摘要的接线 | 设计空白，待施工 |
| P4 双向先验（画像反哺 PCR）| PCR CognitiveProfile_v1 有 cognitive_level/expertise_level/preferred_detail | PCR→TrackA 未实现 |
| 子图 L1 热缓存 ← 对话树提纯 ← 画像 | 子图读 _ocean_analyst.profile（P/F 域）| ContextCompiler P 域（profile_source）未注册，双路径不一致 |

---

## 七、画像↔意图接口（意图 DESIGN_AUDIT §五 对照）

| 接口 | 意图侧 | 画像侧 | 实况 |
|---|---|---|---|
| L3 _profile_vote | profile_traits["conscientiousness"] > 0.6 → ACCEPT 诊断/修复 | OCEAN C 维度存在 | engine 不传 profile_traits → 永远 ABSTAIN |
| SubIntent.chain_votes[profile] | 意图新包模型字段 | 未接 | 纸面 |
| VerifyContext.profile | 意图新包 VerifyContext 字段 | 未接 | 纸面 |
| intent/coordinator profile 参数 | 默认 {"OCEAN": {"C": 4.5}} | 无接线 | 签名死参数 |
| PCR→L3 zone 播种 | D-14 已通 | — | ✅（L3 侧）|

---

## 八、待拍板清单（阶段五备料）

1. 三套归一 vs 分层：OCEAN（LLM 人格 10 维）/ 行为侧（算法 expertise/preferences）/ user_engine（v3 规则字段）——是否统一为"一内核多门面"（红线 7），建议 OCEAN 人格层 + 行为侧行为层 + user_engine 字段并入
2. _cognitive_profile 复活：CognitiveProfileV2 是否在生产路径实例化并接线（Track A + Track B + Convergence + ProfileStore）——v2 设计 11 模块完整落地还是部分吸收到 OCEAN？
3. PROFILE_GAP 声明修正：95% → 实测 30-40%，更新文档避免误判
4. L3 profile 视角接线：engine validate() 传入 profile_traits（OCEAN dims → conscientiousness 映射）
5. 对话树组块边界 ← 画像：接入用户认知状态（A5/A15 协同，KERNEL §八.8.4）
6. ContextCompiler P 域：注册 ProfileContextSource 或统一走子图 P/F 域
7. inertia_graph 喂数据：链08 v2 惯性权重图谁来喂 evidence（多视角：行为链/关联链/对话树/元认知）
8. CLI 死命令修复：p4_cmd/p10_cmd 签名对齐 + 双名注册归一 + save() 挂载
9. 测试补全：OCEAN/user_engine/双轨家族无真实断言测试（仅 test_cognitive.py 三组模型级测试）

---

*本文件是画像审计阶段二成果；与 AUDIT_ENTRY_20260803.md（资产盘点）、DESIGN_AUDIT_20260803.md（设计审计）共同构成画像审计完整资产。*
