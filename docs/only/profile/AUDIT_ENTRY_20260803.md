# 画像（Profile）模块审计入口 — 2026-08-03

> 状态: **阶段一 资产盘点 ✅（本文件）/ 阶段二 实现审计 ✅（IMPLEMENTATION_AUDIT_20260803.md）/ 阶段三 设计文档审计 ✅（DESIGN_AUDIT_20260803.md，6 篇全读）/ 阶段四 接口预扫描 ✅（画像↔对话树/意图/PCR/L3）/ 阶段五 拍板待开工**
> 严重度: 🟡（子图审计已点：P/F 域取不到 profile；恢复规划预告"双 ocean_profile"，实测为**三套画像体系 + 多处死代码**）
> 审计方法: 与意图/对话树同法——资产盘点（本文件）→ import/引用全查 → 实现精读 → 设计文档精读 → 接口预扫描 → 拍板

---

## 一、审计对象全景（2026-08-03 实测）

### 1.1 画像实现三套体系（非"双类"，恢复规划预告需修正）

| 体系 | 文件 | 规模 | 引用数 | 角色 | 接线状态 |
|---|---|---:|---:|---|---|
| **OCEAN 认知画像** | `v4/cognitive/ocean_profile.py` | 11KB | 9 处 | OCEANProfile（10 维 EMA）+ OCEANProfileAnalyst（LLM 逐轮评分）| 🟡 CLI 主路径挂载为 `_ocean_analyst`（cli/engine.py:316-317），PROFILE 阶段调用 analyze；API/直接实例化路径无 |
| **行为侧画像** | `predictor/cognitive_profile.py` | 16.8KB | 5 处精确 import | CognitiveProfile + ProfileUpdater + EnhancedProfileMatcher + ProfileStore | ✅ 被行为链 brain.py 使用（behavior 审计已确认接线）|
| **用户引擎画像** | `user_engine/user_profile.py` + user_manager + user_extractor + consistency_checker | 16.5KB | 2 处 | UserProfile（tech_level/domains/patience/correction...）+ SQLite UserManager | 🟡 仅 context_manager（v3 路径）懒加载使用；engine 主路径不触达 |

### 1.2 v4/cognitive 双轨实现（CognitiveProfileV2 家族，设计对应 DESIGN_COGNITIVE_PROFILE_V2）

| 文件 | 角色 | 引用数 | 接线状态 |
|---|---|---:|---|
| `models.py` | CognitiveProfileV2 + CognitiveDynamics（Track A）+ UserTag（Track B）| 多 | ❌ **生产路径从未实例化 CognitiveProfileV2**（全库仅 tests 实例化）|
| `dynamics.py` | DynamicsComputer（Track A 9 维计算）| 1（bridge）| ❌ 仅 cognitive_bridge 注册，无 engine 调用 |
| `tag_layer.py` | TagAcquisitionEngine（L1/L2）+ TagLayerManager + GFactorInferencer | 1（bridge）| ❌ TagLayerManager 0 引用；TagAcquisitionEngine 仅 bridge 注册 |
| `convergence.py` | ConvergenceEngine（EMA 收敛）+ ProfileStore（SQLite）| 2（profile_source/fusion import）| ❌ 无 engine 调用；ProfileStore 仅 tests |
| `fusion.py` | FusionContext（TrackA+B 渲染）| 1（profile_source）| ❌ 无 engine 调用 |
| `bfi_calibrator.py` | BFICalibrator（BFI-10 校准）| 2（ocean_profile/bridge）| 🟡 analyze_with_bfi_override 存在，无调用方 |
| `llm_profile_analyst.py` | LLMProfileAnalyst（三源融合）| **0** | ❌ 死代码 |
| `signal_filter.py` | ProfileSignalFilter | 0 | ❌ 死代码（仅 legacy engine_full `_feed_profile` 引用）|
| `inertia_graph.py` | InertiaWeightGraph（链08 v2 惯性权重图）| 1（cli/engine）| 🟡 CLI 挂载 `_inertia_graph`，但无数据源喂入（detect_quality_centric 无调用方）|
| `memory_extractor.py` | MemoryExtractor + MemoryManager（记忆点）| 1（bridge）| 🟡 bridge 注册，engine 未用 |
| `version_control.py` | VersionStore（git 式记录）| 待查 | 画像版本控制候选（A17）|

### 1.3 周边画像相关（非 v4/cognitive）

| 文件 | 角色 | 引用数 |
|---|---|---:|
| `compiler/profile_source.py` | **ProfileContextSource（P 域上下文源）** | **0** ❌（ContextCompiler 的 P 域画像源未注册——子图审计"P/F 域取不到 profile"的根因）|
| `v3_0/cognitive_compiler/profile_updater.py` | ProfileUpdater（Cognitive Tree 节点 → 画像）| 2（orchestrator + cognitive_compiler/__init__）|
| `predictor/profile_matcher.py` | ProfileMatcher | 1（死链，与 EnhancedProfileMatcher 重复）|
| `prompts/user_profiler.py` | 用户特征提取 prompt | user_extractor 用 |
| `pcr/datacontract.py` | CognitiveProfile_v1（cognitive_level/expertise_level/preferred_detail）| PCR 输出契约 |
| `v3_legacy/data_models.py` | CognitiveProfile_v3（第五套模型）| context/models.py 引用 |
| `persistence/multi_domain_adapters.py` | UserProfileAdapter（P 域持久化）| 待查 |
| `association/l3_intent.py` | `_profile_vote`（OCEAN C 阈值 → 意图投票）| engine 已接 L3 |
| `intent/coordinator.py` | profile 参数（OCEAN 默认 C=4.5）| 默认参数，未接线 |

### 1.4 测试

```
core/agent/v4/cognitive/tests/test_cognitive.py  ← 唯一画像测试（TestModels/TestConvergence/TestDynamics）
core/agent/v4/cognitive/tests/bench_ab_ocean.py   ← OCEAN A/B 基准（非断言测试）
core/agent/v4/cognitive/tests/chat_mbti_test.py   ← MBTI 聊天测试（非断言）
core/agent/v3_0/cognitive_tree/tests/test_cognitive_tree.py ← Cognitive Tree（ProfileUpdater 数据源）
（tests/ 根目录无 test_profile*.py；user_engine 无专属测试）
```

---

## 二、设计文档资产（6 篇，2026-08-03 全读）

| 文档 | 规模 | 内容 | 状态 |
|---|---:|---|---|
| `BUSINESS_CHAIN_08_PROFILE.md` | 4.4KB | 链08 v1：双 Track + OCEAN + Convergence + ExecutionTrace 信号流 | 设计（自认 50% 接入）|
| `BUSINESS_CHAIN_08_PROFILE_FEEDBACK.md` | 9KB | **链08 v2：画像=惯性权重图**（多视角共识 + 惯性打破 + 设计约束投射）| 设计（v2.0）|
| `v3.0/design_cognitive_profile_v2.md` | 33KB | 双轨架构（Track A 认知动力学 / Track B 标签）+ 时间衰减 + L1-L4 标签获取 + g 因子 | 设计蓝图 |
| `v3.0/ENGINEERING_COGNITIVE_PROFILE_V2.md` | 88KB（2034L）| 11 模块工程实现规格（models/dynamics/tag_layer/temporal/acquisition/g_factor/dialogue_tree_weight/memory_decay/fusion/engine）| 工程规格（冻结）|
| `v3.0/LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md` | 33KB | 文献调研：记忆衰减/摘要/画像/信任/g 因子 + 修正建议 | 调研 |
| `v5/PROFILE_GAP.md` | 1.2KB | 接入后差距声明（**"全部修复 ~95%"**——审计实况不符）| 声明（2026-07-21）|

---

## 三、审计计划

```
阶段一: 资产盘点 ✅（2026-08-03，本文件）
阶段二: 实现审计 ✅ —— 三套体系 21 文件精读 + import 探针 + 接线追踪 → IMPLEMENTATION_AUDIT_20260803.md
阶段三: 设计文档审计 ✅ —— 6 篇全读（ENGINEERING 2034L 全文）→ DESIGN_AUDIT_20260803.md
阶段四: 接口预扫描 ✅ —— 画像↔对话树/意图/PCR/L3/子图（DESIGN_AUDIT §五）
阶段五: 内核拍板 + 待办清单（待开工，IMPLEMENTATION_AUDIT §八 + DESIGN_AUDIT §六）
```

---

## 四、待查清单（审计开工问题）

1. `_cognitive_profile` 在生产路径**从未实例化**——双轨 CognitiveProfileV2 是纸面架构？（实锤：engine.py:164 = None，全库实例化仅 tests）
2. OCEAN 画像只在 CLI `start_engine` 挂载——API（v6_app get_engine 自动 start 也算 A 路径？）与 B 路径 `_create_engine_instance` 差异（对照子图审计的 A/B 路径结论）
3. `handlers.py handle_profile`（PROFILE 阶段）真的会执行吗——状态机 META→PROFILE→PERSIST 已注册，需确认 run_pipeline 从 DISCOURSE 起是否经过 PROFILE（v3_session_api.py:268 从 DISCOURSE 起，engine on_event_sm 从 PCR 起）
4. `_feed_profile`/`_feed_trackb` 在 engine.py:890-891 被调用但类上无此方法——确认在死代码 `_on_event_continue` 内（无调用方），还是生产路径 AttributeError（实锤：`_on_event_continue` 仅定义无调用 = 死代码；handlers.py:172 hasattr 检查静默跳过 = TrackB 未执行）
5. PCR→TrackA EMA 是否真接通（PROFILE_GAP 声称 ✅）：`_update_profile_from_trace` 全库无定义 → 声称与实况矛盾
6. 对话树 compiler（discourse_block_tree）是否读画像认知状态（疲劳/注意力/惯性）→ 待验证（KERNEL_ABSORPTION §九 要求）
7. inertia_graph（链08 v2 惯性权重图）只挂载无数据源——谁来喂 evidence/反例？
8. user_engine 是否应并入统一画像内核（tech_level/domains/patience 与 OCEAN 的映射关系）
