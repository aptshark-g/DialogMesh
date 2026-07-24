# PCR 设计审计报告：DESIGN_V4.0 vs 代码实现

> 审计日期：2026-07-24
> 审计范围：两套设计文档 × 五份代码实现
>
> 设计文档：
> - `docs/v5/DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md`（三维坐标路由，257 行）
> - `docs/BUSINESS_CHAIN_00_PCR.md`（5 阶段 Pipeline + 8 链调控，328 行）
> - `docs/v5/DESIGN_ALIGNMENT_CHECK.md`（EventBus 集成对齐确认）
>
> 代码实现：
> - `core/agent/pcr_router_v2.py`（PCR V2，403 行）
> - `core/agent/router/router_v4.py`（Router V4，117 行）
> - `core/agent/router/coordinate_router.py`（V1 硬编码版，257 行）
> - `core/agent/mood/mood_vector_library.py`（情绪向量库，126 行）
> - `core/agent/classifier/structural_classifier.py`（结构分类器，158 行）
> - `config/mood_profiles.yaml`（情绪描述符配置，51 行）

---

## 一、设计目标 vs 代码现状完整对比表

| 序号 | 设计要求 | 设计来源 | pcr_router_v2 | router_v4 | coordinate_router | 评估 |
|:---:|------|------|:---:|:---:|:---:|:---:|
| 1 | **三维连续坐标** X/Y/Z 替代离散标签 | V4.0 §一 | ✅ 完整 | ✅ 完整 | ✅ 完整 | 达成 |
| 2 | **6-zone 路由** ATOMIC/ABYSS/PSYCHE/PRECISION/EXPLORE/MIXED | V4.0 §四 | ⚠️ 阈值不同 | ⚠️ 阈值不同 | ✅ 完全一致 | 不一致 |
| 3 | **X轴：SVO语义引力** G=1-cos(S,O) + IDF修正 | V4.0 §3.1 | ❌ 完全不同 | ❌ 简单启发式 | ✅ 接近设计 | 断裂 |
| 4 | **Y轴：StructuralFeatures** verb/entity/word_count | V4.0 §3.2 | ✅ 完全一致 | ❌ 用的 Stanza | ❌ 用的 Stanza | 部分实现 |
| 5 | **Z轴：BGE情绪向量库** mood_profiles.yaml 32描述符 | V4.0 §3.3 | ✅ 三级fallback | ✅ BGE | ❌ 硬编码关键词 | 部分实现 |
| 6 | **Z轴 LLM fallback** MoodClassifierLLM 75% | V4.0 §3.3 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 | 缺失 |
| 7 | **后验校准** 用户反馈→权重微调 | V4.0 §五 | ❌ 未实现 | ❌ 未实现 | ⚠️ calibrate()骨架 | 骨架存在 |
| 8 | **8链调控映射** PCR→10条下游链信号投递 | BUSINESS_CHAIN §四 | ❌ 完全缺失 | ❌ 完全缺失 | ❌ 完全缺失 | 缺失 |
| 9 | **5阶段Pipeline** Expectation/NoiseSpan/Complexity/Cognitive/Strategy | BUSINESS_CHAIN §二 | ❌ 完全缺失 | ❌ 完全缺失 | ❌ 完全缺失 | 缺失 |
| 10 | **NoiseSpan拓扑** 6种噪声类型+差异化下游处理 | BUSINESS_CHAIN §三 | ❌ 完全缺失 | ❌ 完全缺失 | ❌ 完全缺失 | 缺失 |
| 11 | **FallbackEngine** 三级降级回退 | BUSINESS_CHAIN §七 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 | 缺失 |
| 12 | **LifecycleManager** 生命周期管理 | BUSINESS_CHAIN §六 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 | 缺失 |
| 13 | **TelemetryCollector** 遥测收集 | BUSINESS_CHAIN §六 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 | 缺失 |
| 14 | **EventBus集成** PCR_COMPUTED 事件发布 | ALIGNMENT_CHECK | ❌ 未集成 | ❌ 未集成 | ❌ 未集成 | 缺失 |
| 15 | **StrategyDeriver决策矩阵** expectation×noise×complexity | BUSINESS_CHAIN §五 | ❌ 完全缺失 | ❌ 完全缺失 | ❌ 完全缺失 | 缺失 |
| 16 | **ExpectationIdentifier** 三级意图识别 | BUSINESS_CHAIN §二 | ❌ 完全缺失 | ❌ 完全缺失 | ❌ 完全缺失 | 缺失 |

---

## 二、X/Y/Z 三轴计算公式的详细差异

### 2.1 X轴：认知距离 — 设计 vs 三份代码

| 维度 | 设计公式 | pcr_router_v2 | router_v4 | coordinate_router |
|------|---------|:---:|:---:|:---:|
| **公式** | G×0.7 + IDF_avg×0.3 | entity_density×0.5 + rarity×0.5 | 0.5 or 0.3（首尾词是否相同） | semantic_distance×0.7 + IDF×0.3 |
| **SVO提取** | BGE encode(S)和(O) | ❌ 无 | ❌ 无 | ✅ tokens[0]/tokens[-1] |
| **语义引力G** | 1-Cosine(S_vec, O_vec) | ❌ 无 | ❌ 无 | ⚠️ 有但依赖 BGE |
| **IDF修正** | 对话日志中S和O的IDF均值 | ❌ 无 | ❌ 无 | ⚠️ _idf_cache 但值固定为0.3 |
| **NRC-VAD** | 设计未提及用于X轴 | ✅ 作为主要信号源 | ❌ 无 | ❌ 无 |

**结论**：
- `pcr_router_v2` 完全未按设计实现 X 轴。设计公式是 BGE 语义距离 + IDF 修正，代码变成了实体密度 + 词汇罕见度。
- `router_v4` 的 X 轴是占位启发式（首尾词比较），没有实际价值。
- `coordinate_router` **最接近设计**，但 IDF 缓存没有实际填充（永远返回 0.3），BGE 条件依赖外部注入。

### 2.2 Y轴：操作粒度 — 设计 vs 三份代码

| 维度 | 设计公式 | pcr_router_v2 | router_v4 | coordinate_router |
|------|---------|:---:|:---:|:---:|
| **骨架** | StructuralFeatures 三板斧 | ✅ 完全一致 | ❌ Stanza 依存解析 | ❌ Stanza 依存解析 |
| **verb_count权重** | min(v/5,1.0) × 0.4 | ✅ 0.4 | ❌ depth×0.4 | ❌ depth×0.4 |
| **entity_count权重** | min(e/5,1.0) × 0.3 | ✅ 0.3 | ❌ coord×0.4 | ❌ coord×0.4 |
| **word_count权重** | min(w/20,1.0) × 0.3 | ✅ 0.3 | ❌ prep×0.2 | ❌ prep×0.2 |
| **后处理** | 无（直接Clip到[0,1]） | ✅ 无 | ❌ sigmoid变换 | ❌ sigmoid变换 |
| **依赖** | 零网络依赖 | ✅ 0.1ms | ❌ 需要 Stanza | ❌ 需要 Stanza |

**结论**：
- `pcr_router_v2` 的 Y 轴是**唯一完全按照设计实现的**。
- `router_v4` 和 `coordinate_router` 都用 Stanza，与设计明确声明的"不使用 Stanza（离线超时，导入卡死）"矛盾。
- 设计文档 §七 明确写"Stanza 依存解析 → offline超时，暂用 StructuralFeatures 替代"，但 router_v4 和 coordinate_router 仍然硬依赖 Stanza。

### 2.3 Z轴：反馈期望 — 设计 vs 三份代码

| 维度 | 设计公式 | pcr_router_v2 | router_v4 | coordinate_router |
|------|---------|:---:|:---:|:---:|
| **主路径** | BGE mood向量余弦最近邻 | ✅ LM Studio nomic → BGE → fastembed | ✅ BGE（需注入） | ❌ 硬编码关键词 |
| **Fallback 1** | NRC-VAD 50% | ✅ 有 | ❌ 无 | ❌ 无 |
| **Fallback 2** | LLM few-shot 75% | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **Fallback 3** | 结构特征 | ✅ imperative=1.0, question=0.0 | ❌ 无 | ❌ 无 |
| **kurtosis/fatigue** | 设计§3.3提及但未在Z公式中纳入 | ❌ 无 | ❌ 无 | ⚠️ 有kurtosis+fatigue但被硬编码词覆盖 |
| **配置驱动** | mood_profiles.yaml | ✅ | ✅ | ❌ 硬编码 |

**结论**：
- LLM fallback（MoodClassifierLLM 75%）在所有三份代码中均**完全缺失**。
- kurtosis/fatigue 信号在设计中被提及但未纳入主公式；coordinate_router 独有。
- `pcr_router_v2` 的三级 fallback 是**最完整的 Z 轴实现**，但仍缺 LLM 层。

---

## 三、完全未实现的设计点

按严重程度排序：

### 🔴 P0（核心架构缺失）

| # | 设计点 | 设计要求 | 实际情况 |
|:---:|------|---------|------|
| 1 | **BUSINESS_CHAIN 5阶段Pipeline** | Expectation → NoiseSpan → Complexity → Cognitive → Strategy 串行流水线 | **完全不存在**。pcr_router_v2 只有一个 `route()` 方法，直接 XYZ → zone。 |
| 2 | **NoiseSpanDetector** | 3维噪声（语义/结构/指代）+ 6种噪声类型 + 局部定位 | **零实现**。pcr_router_v2 完全不做噪声检测。 |
| 3 | **ExpectationIdentifier** | 3级 tier 意图识别（规则/历史/LLM） | **零实现**。代码没有 TOOL/ADVISOR/COMPANION/UNKNOWN 输出。 |
| 4 | **ComplexityEstimator** | YAML 配置表 + 步骤计数 + 领域跨度 | **零实现**。pcr_router_v2 只有 Y 轴 = 语法复杂度，不是 BUSINESS_CHAIN 的 complexity_level。 |
| 5 | **8链调控映射** | PCR Output → 链01/02/04/05/07/08/09/10 的差异化信号 | **零实现**。PCR 输出只返回 PCRResult，没有投递到 EventBus。 |
| 6 | **X轴 BGE SVO 语义距离** | G=1-cos+BGE + IDF 修正 | pcr_router_v2 的 X 轴公式完全不同。router_v4 的 X 轴是占位符。 |

### 🟡 P1（核心组件缺失）

| # | 设计点 | 设计要求 |
|:---:|------|---------|
| 7 | **LLM MoodClassifier fallback** | 75% 准确率，200ms，作为 Z 轴第三级 |
| 8 | **FallbackEngine 三级降级** | Level 1 conservative → Level 2 degraded → Level 3 pass_through |
| 9 | **LifecycleManager** | initialize/warm_up/start/shutdown + Telemetry |
| 10 | **StrategyDeriver 决策矩阵** | 3D 矩阵（expectation×noise×complexity）决定 execution_mode |

### 🟢 P2（增强特性缺失）

| # | 设计点 | 设计要求 |
|:---:|------|---------|
| 11 | **后验校准追踪器** | 用户反馈积累 → 权重自动微调 |
| 12 | **OCEAN/DMN 状态信号** | 人格/认知状态注入 Z 轴 |
| 13 | **Telemetry 集成** | 运行时指标收集 |
| 14 | **CognitiveProfiler** | 用户画像驱动的 cognitive_level/expertise_level/preferred_detail |

---

## 四、实现了但质量不够的设计点

### 4.1 6-zone 路由阈值不一致

设计文档定义的精确阈值：
```
ATOMIC:     x < 0.2 and y < 0.2
ABYSS:      x > 0.7 and y > 0.7 and z > 0.5
PRECISION:  x < 0.5 and y > 0.5 and z > 0
EXPLORE:    x > 0.5 and y < 0.5 and z <= 0
```

pcr_router_v2 的实际阈值：
```
ATOMIC:     x < 0.3 and y < 0.3     ❌ 放宽了
ABYSS:      x > 0.7 and y > 0.6 and z > 0.3  ❌ Y和Z都放宽了
PRECISION:  x < 0.5 and y > 0.4 and z > 0    ❌ Y边界从0.5降到0.4
EXPLORE:    x > 0.4 and y < 0.4 and z <= 0   ❌ X从0.5降到0.4, Y从0.5降到0.4
```

影响：更多输入会落入 ATOMIC/PRECISION/EXPLORE 而非 MIXED，可能导致过度优化路由。

router_v4 的阈值又不同（x>0.6 for ABYSS），三份代码三个版本。

### 4.2 Z轴缺少 LLM fallback

设计明确要求 MoodClassifierLLM（75%, 200ms），但在所有代码中均缺失。当前 pcr_router_v2 的 Z 轴流程是：
```
BGE（主） → NRC-VAD（辅） → 结构特征（三）
```
缺少 LLM 层意味着对复杂情绪的识别召回率不足（NRC-VAD 仅 50%，structure fallback 更弱）。

### 4.3 X轴占位实现

`pcr_router_v2._compute_distance()` 使用实体密度+NRC-VAD 稀有度，完全绕过了设计核心——BGE 语义引力。`router_v4._compute_x()` 更糟——它比较首尾词是否相同来决定输出 0.3 或 0.5。

唯一接近设计的 `coordinate_router._compute_x()` 实际上 IDF 缓存永远不填充，BGE 在 PCRRouterV2 的类方法调用中也不可用。

### 4.4 两份 V4 router 代码并存 — 架构分裂

- `core/agent/pcr_router_v2.py`：用 StructuralFeatures，零硬编码
- `core/agent/router/router_v4.py`：用 Stanza，不同公式
- `core/agent/router/coordinate_router.py`：用 Stanza+硬编码 MoodClassifier，但有 calibrate()

三份代码对同一设计的三个不同解读，且 pcr_router_v2 的文件头注释声称"V4.0 Design"，但实现与设计多处偏离。`router_v4.py` 文件头声称"V4.0 Cognitive Coordinate Router"，但 Y 轴用 Stanza（与设计矛盾）。

---

## 五、优先级排序的改进建议

### 🔴 P0 — 必须立即修复（阻塞核心架构）

| 优先级 | 项目 | 当前状态 | 建议动作 | 预估工作量 |
|:---:|------|---------|------|:---:|
| **P0-1** | **统一 X 轴实现** | pcr_router_v2 公式完全不同 | 按设计公式重写 `_compute_distance()`：BGE SVO 语义引力 0.7 + IDF 修正 0.3。从 coordinate_router 移植 BGE SVO 逻辑，接入 _idf_cache 累积 | 1-2天 |
| **P0-2** | **统一 Zone 路由阈值** | 三份代码三个版本 | 以设计文档为准（ATOMIC 0.2/0.2, ABYSS 0.7/0.7/0.5, PRECISION 0.5/0.5, EXPLORE 0.5/0.5），在三份代码中统一 | 0.5天 |
| **P0-3** | **合并两份 V4 router** | 两份活跃代码冲突 | 以 pcr_router_v2 为骨架（StructuralFeatures 零硬编码），从 coordinate_router 移植 calibrate() 和 BGE SVO X轴，废弃 router_v4 的 Stanza 依赖 | 1-2天 |

### 🟡 P1 — 应该尽快完成（核心组件空缺）

| 优先级 | 项目 | 建议动作 | 预估工作量 |
|:---:|------|------|:---:|
| **P1-1** | **实现 ExpectationIdentifier** | 在 pcr_router_v2 中增加 Tier 0（规则快路径）+ Tier 1（历史推断）+ Tier 2（LLM few-shot），输出 TOOL/ADVISOR/COMPANION/UNKNOWN | 2-3天 |
| **P1-2** | **实现 NoiseSpanDetector** | 检测 6 种噪声类型（TYPO/AMBIGUOUS/JARGON/FLUFF/LEAP/INJECTION），输出局部 NoiseSpan[]，替代全局 noise_level | 2-3天 |
| **P1-3** | **实现 LLM MoodClassifier** | 增加 Z 轴第三级 fallback：用 LLM few-shot 做情绪分类（75% accuracy，200ms），在 BGE 和 NRC-VAD 均不可用时触发 | 1天 |
| **P1-4** | **对接 EventBus** | 在 route() 返回前 publish PCR_COMPUTED 事件，让 Meta/Assoc 订阅 | 0.5天 |

### 🟢 P2 — 应在下一迭代完成（增强特性）

| 优先级 | 项目 | 建议动作 | 预估工作量 |
|:---:|------|------|:---:|
| **P2-1** | **实现 StrategyDeriver 决策矩阵** | 基于 expectation × noise × complexity 的 4×4 矩阵 → execution_mode/prompt_style/ambiguity_strategy | 1-2天 |
| **P2-2** | **实现 FallbackEngine** | 三级降级：conservative → degraded → pass_through | 1天 |
| **P2-3** | **实现 ComplexityEstimator** | YAML 配置表匹配 + 步骤计数 + 领域跨度，输出 0-1 complexity_level | 1天 |
| **P2-4** | **实现后验校准完整链路** | 移植 coordinate_router.calibrate() → 接入用户反馈 → 自动调整 X/Y/Z 公式权重 | 1-2天 |
| **P2-5** | **实现 8 链调控映射** | PCR Output → 链01/02/04/05/07/08/09/10 的差异化信号路由 | 2-3天 |

---

## 六、代码健康度评估

| 维度 | 评分 | 说明 |
|------|:---:|------|
| **设计对齐度** | 3/10 | 核心公式（X轴）完全偏离设计；BUSINESS_CHAIN 5阶段零实现；zone 阈值三个版本 |
| **代码一致性** | 2/10 | 三份 router 实现互不兼容；两套 StructuralFeatures 定义不同；Y 轴用了 Stanza 和 StructuralFeatures 两种方案 |
| **完整性** | 2/10 | 403 行 pcr_router_v2 只做坐标→zone，缺失 5 阶段 Pipeline、NoiseSpan、期望识别、降级等核心模块 |
| **可维护性** | 6/10 | 零硬编码设计好；mood_profiles.yaml 配置驱动好；但代码分裂和多版本问题严重 |
| **可测试性** | 4/10 | StructuralFeatures 有测试覆盖；但 router_v4/coordinate_router 没有独立测试；X 轴没有正确性验证 |

---

## 七、总结

**核心发现**：DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md 定义的"三维连续坐标路由器"在 pcr_router_v2 中有骨架实现，但存在三处关键断裂：

1. **X 轴公式完全偏离设计** — 设计是 BGE SVO 语义引力，代码是实体密度 + 词汇稀有度
2. **BUSINESS_CHAIN_00_PCR.md 的 5 阶段 Pipeline 零实现** — pcr_router_v2 跳过了 ExpectationIdentifier、NoiseSpanDetector、ComplexityEstimator、CognitiveProfiler、StrategyDeriver 全部五个阶段
3. **三份 router 代码并存** — pcr_router_v2、router_v4、coordinate_router 各自走了不同路线，Y 轴公式分岔为 StructuralFeatures vs Stanza，zone 阈值三版本

**正面信号**：Y 轴公式在 pcr_router_v2 中完全按设计实现；Z 轴的三级 fallback 架构（BGE→NRC-VAD→结构）正确；mood_profiles.yaml 配置驱动是好的设计；零硬编码方向正确。

**建议优先做的事**：
1. 统一 pcr_router_v2 的 X 轴为设计公式（BGE SVO + IDF），从 coordinate_router 移植
2. 统一 zone 阈值为设计文档定义值
3. 删除或标记 router_v4 为 deprecated（Stanza 依赖与设计冲突）
4. 在 pcr_router_v2 中增加 ExpectationIdentifier（Tier 0 规则快路径即可覆盖 90%）
5. 接入 EventBus publish PCR_COMPUTED
