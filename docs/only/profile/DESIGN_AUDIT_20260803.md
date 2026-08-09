# 画像设计文档审计 + 接口预扫描（阶段三/四）— 2026-08-03

> 范围：6 篇画像设计文档全部精读（BUSINESS_CHAIN_08_PROFILE / BUSINESS_CHAIN_08_PROFILE_FEEDBACK / design_cognitive_profile_v2 / ENGINEERING_COGNITIVE_PROFILE_V2（2034L 全文）/ LITERATURE_REVIEW_COGNITIVE_PROFILE_V2 / v5 PROFILE_GAP）+ 跨模块设计（意图 DESIGN_MULTI_SIGNAL_INTENT S3/S5、V3.2 ROUTING_MATRIX 用户偏置层、PARADIGM P4 公理）。
> 配套：`IMPLEMENTATION_AUDIT_20260803.md`（阶段二实现审计）、`AUDIT_ENTRY_20260803.md`（资产盘点）。
> 定位：画像内核拍板备料 + 画像↔对话树/意图/PCR 接口预扫描。

---

## 一、设计资产地图与演进脉络

### 1.1 演进代际

| 代际 | 文档 | 范式 | 状态 |
|---|---|---|---|
| v1 | `BUSINESS_CHAIN_08_PROFILE.md`（链08）| ExecutionTrace（STRENGTHEN/WEAKEN/REJECT）→ TrackA 认知动力学 7 维 + TrackB 标签 + OCEAN + Convergence | 设计（自认 50% 接入）|
| v2.0 | `BUSINESS_CHAIN_08_PROFILE_FEEDBACK.md` | **画像=惯性权重图**（多视角共识确认惯性 / 反例降权 / 惯性打破=最强学习信号 / 投射为设计约束+参数覆盖）| 设计（v2.0）|
| v2 | `design_cognitive_profile_v2.md`（33KB）| 双轨架构：Track A 认知动力学（rz.txt 抽象化 9 维）+ Track B 标签化信息（7 类）+ 时间衰减（双指数+阶梯）+ L1-L4 标签获取 + g 因子 + 融合层 | 设计蓝图 |
| v2-eng | `ENGINEERING_COGNITIVE_PROFILE_V2.md`（88KB）| 11 模块工程规格（models/dynamics/tag_layer/temporal/acquisition/g_factor/dialogue_tree_weight/memory_decay/fusion/engine）+ API + 集成 + 简化诚实标记（S-01~S-05）| 工程冻结 |
| v5 | `v5/PROFILE_GAP.md` | 接入后差距声明（PCR→TrackA EMA / LLM trust / TrackB / OCEAN / Convergence 全部 ✅，~95%）| **与实现审计实况不符（30-40%）** |
| 文献 | `LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md` | MemoryBank/Keep-updated/Hello-again/Ebbinghaus 等 20+ 文献 → 记忆衰减/摘要/画像/信任/g 因子 | 调研 |

### 1.2 三条设计主线（并存未收敛）

```
主线 A（链08 v1）: ExecutionTrace 信号 → 双 Track + OCEAN 映射（行为反馈驱动）
主线 B（链08 v2）: 惯性权重图（跨链多视角共识 → 稳定惯性 → 设计约束/参数覆盖）
主线 C（v2 双轨）: Track A 认知动力学 ∥ Track B 标签化信息 + 时间衰减 + g 因子 + 融合层
```

### 1.3 实现映射现状

| 设计概念 | 设计文档 | 实现 | 状态 |
|---|---|---|---|
| 双 Track | 链08 v1 / DESIGN v2 | CognitiveProfileV2（models.py）| ❌ 纸面（生产未实例化）|
| OCEAN 10 维 | 链08 v1 | ocean_profile.py | 🟡 CLI 路径活 |
| BFI-10 校准 | PROFILE_GAP | bfi_calibrator.py | ❌ 无调用方 |
| Convergence 收敛 | 链08 v1 / PROFILE_GAP | convergence.py | ❌ 无调用方 |
| 惯性权重图 | 链08 v2（FEEDBACK）| inertia_graph.py | 🟡 挂载未喂数据 |
| 时间衰减（双指数+阶梯）| DESIGN v2 §3 | models.py MemoryChunk（单指数+阶梯，S-01）| ❌ 无调用方 |
| L1-L4 标签获取 | DESIGN v2 §4 / ENG §3.4 | tag_layer.py 仅 L1/L2 | 🟡 L3/L4 未实现（设计空白）|
| g 因子 | DESIGN v2 §4.3.2 / ENG §3.5 | tag_layer.GFactorInferencer | ❌ 无调用方 |
| 融合层 | DESIGN v2 §5 / ENG §3.8 | fusion.py FusionContext | ❌ 无调用方 |
| P 域上下文源 | DESIGN_CROSS_DOMAIN_CONTEXT | profile_source.py | ❌ 0 引用 |
| 记忆点/组块 | DESIGN v2 §3 / rz.txt | memory_extractor.py / models.MemoryPoint | 🟡 bridge 注册，engine 未用 |

---

## 二、设计内部矛盾（5 项）

### 2.1 PROFILE_GAP 声称与实现不符（最核心）
- PROFILE_GAP（2026-07-21）声称：PCR→TrackA EMA ✅ / LLM trust feedback ✅ / TrackB TagLayer ✅（每5轮）/ OCEAN ✅（每10轮）/ Convergence ✅（每3轮），有效实现率 ~95%
- 实现审计实况：三处全库无调用方（`_update_profile_from_trace` 无定义、`TagLayerManager.infer_from_trace` 0 引用、`ConvergenceEngine.update` 仅 tests/profile_source）；OCEAN 是逐轮 analyze 而非每 10 轮 update
- 结论：**PROFILE_GAP 是"先射箭再画靶"的乐观声明**，实际约 30-40%（同 PCR 审计教训）

### 2.2 画像本体定义漂移
- 链08 v1：OCEAN 10 维浮点数
- 链08 v2：惯性权重图（InertiaPattern + evidence + weight + 反例 + 设计约束）
- v2 双轨：Track A 动力学 + Track B 标签
- 三套定义无统一本体；实现侧又有第三套（user_engine 字段）

### 2.3 画像更新源分裂
- 链08 v1：ExecutionTrace 信号（STRENGTHEN/WEAKEN/REJECT）
- 链08 v2：跨链多视角共识（对话树/工程链/行为链/LLM/元认知/关联链 6 视角）
- v2 双轨：对话历史标签推断（L1/L2/L3/L4）+ 认知动力学观察
- 实现：OCEAN 用 LLM 逐轮评分 + BFI 校准（未接）；行为侧用 record_action EMA（已接）；user_engine 用规则+小模型（v3 路径）

### 2.4 时间衰减 vs 温度系统
- DESIGN v2 §3：双指数衰减 + 阶梯跃迁（hot/warm/cool/cold）
- KERNEL_ABSORPTION（对话树）：温度系统 = 多因子复合场（时间×访问×主题×语义唤醒），画像应暴露"缩放级别建议"
- 实现：models.MemoryChunk 有单指数+阶梯（S-01 简化），但无调用方；temperature 系统属记忆侧
- **未对齐**：画像的"记忆点"（MemoryPoint）与对话树"组块/温度"关系未定义

### 2.5 g 因子伦理边界
- DESIGN v2 决策 2：g 因子不用于歧视/标签固化，仅调整回复复杂度，领域相对
- 实现：GFactorInferencer 评估后存 track_b["g_factor"]——无领域维度（domain 恒 "general"），与"领域相对"矛盾

---

## 三、文献支撑结论（LITERATURE_REVIEW 精读）

| 模块 | 支撑 | 成熟度 | 关键文献 |
|---|---|---|---|
| 记忆衰减 | MemoryBank / Ebbinghaus / Keep-updated / Hello-again / Beyond-Dialogue-Time | ⭐⭐⭐⭐⭐ | Zhong 2024（1054 cites）|
| 对话摘要 | Compress-to-impress / Compressed-context-memory | ⭐⭐⭐⭐⭐ | Li 2023 / Chen 2025 |
| 用户画像 | One-chatbot-per-person / Know-me-respond / ProfiLLM | ⭐⭐⭐⭐ | Ma 2021（154 cites）|
| 信任/惯性 | Trust-Recalibration / Navigating-shifts | ⭐⭐⭐ | Troussas 2025 |
| g 因子推断 | **文献空白**（对话中推断 g 因子无先例）| 创新 | Goertzel 2023（LLM 侧）|
| L3/L4 标签获取 | **文献空白**（暗示试探/反感检测）| 创新 | — |
| 情绪单调度 | 信息熵用于 EEG，对话应用空白 | 创新 | — |

**文献修正建议（§4）**：
1. 记忆衰减：双指数 → 加权单指数 + 阶梯跃迁（与文献一致，高重要性记忆 τ×1.5）
2. 摘要：三级摘要（原始→会话→全局），与对话树 v1-v4 分级方向一致
3. 画像更新：Confidence-Gated Writing（Sun 2023）→ 低置信度不写入
4. g 因子：多任务评估，不标签固化
5. 标签获取：L1/L2 为主，L3/L4 谨慎（侵入-收益比）

---

## 四、链08 v2 惯性权重图（画像=惯性）— 最有价值的设计增量

### 4.1 核心命题
```
画像 ≠ OCEAN 浮点聚合
画像 = 惯性模式的加权图（稳定=高权重；多视角共识=证实；打破惯性=最强信号）
惯性不被消除，只被降低权重或掩盖。画像即设计约束。
```

### 4.2 生命周期（candidate → confirmed → stable → weakening/broken/archived）
- 碎片信号重复≥3 次且跨视角≥2 → 候选（weight=0.4）
- 多视角证实 ≥3 → 确认（0.7）；≥5 → 稳定（0.9）
- 任 1 视角反例 → weight -= 0.05；任 3 视角反例 → inertia_break_review
- 打破 + 情绪信号（WEAKEN spike）→ 情境性打破（不永久降权）；打破无情绪 → 真实惯性迁移

### 4.3 投射机制
- 稳定惯性 → 设计约束（回复含量化指标/白盒暴露/对抗性验证）
- 参数覆盖（高于用户可调默认值）+ 各链阈值微调（行为链 min_repeat_count、关联链 L1.5 置信度、工程链颗粒度）

### 4.4 实现对照
- inertia_graph.py：InertiaPattern/InertiaWeightGraph 完整（register/add_evidence/record_counter/record_stable_round/_update_state/detect_quality_centric/stats）
- CLI engine 挂载 `_inertia_graph`；**但 add_evidence/record_counter/detect_quality_centric 无调用方** → 图存在、无数据源
- 待拍板：6 视角 evidence 谁来喂（行为链 pattern / 关联链 L3 intent 聚类 / 对话树 topic / 元认知 review / LLM 回复分析 / 工程链约束）

---

## 五、画像↔对话树/意图/PCR/子图接口预扫描（4 接口 + 2 公理）

### 5.1 对话树组块边界 ← 用户认知状态（KERNEL §八.8.4）
| 认知状态 | 画像来源 | 对话树用途 | 实况 |
|---|---|---|---|
| 疲劳/认知资源 | Track A cognitive_resource（纸面）| 组块合并倾向 | ❌ 对话树 compiler 无画像输入 |
| 注意力锚点 | Track A attention_anchor（纸面）| 组块边界判据（layer0 三维模型 τ 因子）| ❌ 未接 |
| 惯性/方向性 | OCEAN C + 行为侧 stable_traits | 组块内方向性强度（树纯度函数）| ❌ 未接 |

### 5.2 L3 意图 ← 画像（`_profile_vote`）
- l3_intent.py:200-211：`traits["conscientiousness"] > 0.6` → ACCEPT 诊断/修复；> 0.7 → REJECT 吐槽
- **engine.py:470 不传 profile_traits → 永远 ABSTAIN**（🔴 唯一已实现接口却断线）
- 修复方向：`validate(..., profile_traits={"conscientiousness": ocean.dims["C"]})`

### 5.3 意图新包 ← 画像
- `intent/coordinator.py`：`profile={"OCEAN": {"C": 4.5}}`（默认签名，未接线）
- `VerifyContext.profile` + `SubIntent.chain_votes[profile]`（意图新包模型字段，未接）
- DESIGN_MULTI_SIGNAL_INTENT S3（OCEAN+DMN 用户状态）/ S5（画像后验 P(intent|history)）→ 贝叶斯融合设计存在，未实现

### 5.4 PCR ↔ 画像（P4 公理双向先验）
- PCR 输出 `CognitiveProfile_v1`（cognitive_level/expertise_level/preferred_detail）→ 应注入画像（TrackA EMA）
- 画像 → PCR（认知偏置）：3D 路由矩阵用户偏置层（attention_anchor/expertise → X 偏置；cog_resource/疲劳/时段 → Y 偏置）设计存在（V3.2 ROUTING_MATRIX §四），未实现
- **实况：双向均断**（PCR→TrackA 无实现；画像→PCR 无实现）

### 5.5 子图 P/F 域 ← 画像
- subgraph_compiler.py:210-220 直接读 `engine._ocean_analyst.profile`（MBTI + top dims）
- ContextCompiler P 域：`ProfileContextSource`（profile_source.py）0 引用 → 未注册
- **双路径不一致**：子图绕过 ContextCompiler 直读 OCEAN；API/B 路径无 OCEAN → P/F 域空

---

## 六、待拍板清单（画像内核）

1. **画像本体**：OCEAN 10 维 vs 惯性权重图 vs 双轨（Track A+B）——三套定义归一（建议：OCEAN=人格层、惯性图=行为模式层、Track A=认知状态层，三层合一）
2. **三套实现归一**：OCEAN（LLM）/ 行为侧（算法）/ user_engine（v3 规则）→ 一内核多门面（红线 7）
3. **PROFILE_GAP 修正**：95% → 30-40% 实测（A18 诚实标记）
4. **L3 profile 视角接线**：engine validate() 传 profile_traits（§五.2）
5. **对话树认知状态接入**：组块边界判据融合 Track A（§五.1）
6. **P4 双向先验落地**：PCR→TrackA EMA + 画像→3D 路由偏置（§五.4）
7. **inertia_graph 喂数据**：6 视角 evidence 源拍板（§四.4）
8. **ContextCompiler P 域**：注册 ProfileContextSource 或统一子图路径（§五.5）
9. **v2 双轨 11 模块去留**：全部吸收进统一内核 vs 部分废弃（llm_profile_analyst/signal_filter 死代码已废弃）
10. **g 因子领域化**：domain 相对（§二.5）
11. **CLI 死命令 + 双名注册修复**（IMPLEMENTATION_AUDIT §五.3）
12. **测试补全**：黄金示例集先行（A18，对话树/PCR 教训）

---

## 七、阶段三/四结论

1. **画像设计资产三主线未收敛**：链08 v1（信号→双轨）/ 链08 v2（惯性权重图）/ v2 双轨（标签+动力学）——设计本身在演进中，实现又新增第三套（user_engine），**设计-实现双分裂**（同意图/对话树模式）。
2. **最有价值的增量 = 链08 v2 惯性权重图**：把"画像=稳定的用户模式"从"OCEAN 浮点"提升为"跨链多视角共识的加权图"，与行为链/关联链/元认知天然协同——这是画像内核应该吸收的核心（对应 PARADIGM：行为一等公民 + 多视角 + 后验学习）。
3. **P4 双向先验（画像↔PCR）是公理级断点**：PCR 有 CognitiveProfile_v1 输出、3D 路由矩阵有用户偏置层设计，但双向均未接线——与对话树组块边界（KERNEL §八）一样是"设计完整、实现断线"。
4. **画像与对话树的关系确认**：用户判断正确（对话树模拟记忆组块、画像是用户缩影）——对话树需要画像的认知状态做组块边界判据，画像需要对话树的组块结构做兴趣/惯性证据源，双向依赖，必须先归一画像本体再施工。

---

*本文件是画像审计阶段三/四成果；与 IMPLEMENTATION_AUDIT_20260803.md、AUDIT_ENTRY_20260803.md 共同构成画像审计完整资产。*
