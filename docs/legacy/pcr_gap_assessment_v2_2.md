# PCR v2.2 实现完成度重新评估

**评估基准**：`docs/frontend-agent/design_pcr_interface_v2_1.md`（v2.2）+ `docs/frontend-agent/design_layer0_pcr_and_layer1_intent_parser.md`（v2.2）
**评估日期**：2026-06-15
**当前代码状态**：P8–P13 完成，168 测试通过 166 / 失败 2（PyYAML 环境差异）

---

## 1. 总体完成度：≈ 65%（按 v2.2 标准）

| 维度 | 旧设计 v2.1 完成度 | 新设计 v2.2 新增/修正 | 当前实现状态 | v2.2 完善度 |
|---|---|---|---|---|
| **Layer 0 核心骨架**（7 模块） | 100% | 无改动 | 全部实现 | 100% |
| **数据契约**（datacontract） | 100% | `Modality` 枚举 + `PCRInput_v1` 扩展 + `HistoryEntry.timestamp` | 基础完整，缺新字段 | **60%** |
| **生命周期管理器** | 100% | `evaluate()` 模态分发器 | 基础完整，缺分发器 | **70%** |
| **噪声评估器**（核心修正） | 100% | 三维话题切换检测模型（时间/指代/描述） | 旧逻辑完整，核心算法缺三维模型 | **20%** |
| **ParserConfig** | 100% | 高指代失调时触发同义词扩展 + 上下文回溯 | 基础完整，缺特定调控逻辑 | **80%** |
| **测试基础设施** | 100% | 对抗测试集扩展（时间间隔/话题切换/新任务） | 基础 case 完整，缺新场景 | **70%** |
| **系统集成**（IntentAgent） | 50% | 构造 `PCRInput_v1` 时传入 `modality` + `timestamp` | 直接实例化 + 缺新字段 | **40%** |
| **配置外部化** | 0% | 无改动 | 未实现 | 0% |
| **可选实现**（llm_enhanced/hybrid） | 0% | 无改动 | 未实现 | 0% |

---

## 2. 新设计 v2.2 关键新增/修正点逐一评估

### 2.1 数据契约扩展（P0 优先级）

| 新设计字段/方法 | 当前代码状态 | 实现难度 | 代码位置 |
|---|---|---|---|
| `Modality` 枚举（TEXT/STRUCTURED/IMAGE/AUDIO/MULTIMODAL） | ❌ 完全缺失 | 低 | `datacontract.py` |
| `PCRInput_v1.modality: Modality = Modality.TEXT` | ❌ 缺失 | 低 | `datacontract.py:80` |
| `PCRInput_v1.raw_payload: Optional[Dict]` | ❌ 缺失 | 低 | `datacontract.py:80` |
| `PCRInput_v1.timestamp: float` | ❌ 缺失 | 低 | `datacontract.py:80` |
| `PCRInput_v1.is_text_modality()` | ❌ 缺失 | 低 | `datacontract.py` |
| `PCRInput_v1.is_preprocessing_required()` | ❌ 缺失 | 低 | `datacontract.py` |
| `PCRInput_v1.validate()` 按模态分别校验 | ⚠️ 当前只校验 TEXT 模态 | 低 | `datacontract.py:105` |
| `HistoryEntry.timestamp: float` | ⚠️ `metadata` 字典中可存，但非结构化字段 | 低 | `datacontract.py:55` |

**影响**：`IntentAgent` 构造 `PCRInput_v1` 时（`core/intent_agent.py:1025`）无法传入 `modality` 和 `timestamp`，导致生命周期管理器无法做模态分发，噪声评估器无法做时间间隔计算。

---

### 2.2 生命周期管理器模态分发（P1 优先级）

| 新设计功能 | 当前代码状态 | 实现难度 | 代码位置 |
|---|---|---|---|
| `evaluate()` 按 `modality` 路由 | ❌ 直接 `return self._fallback_engine.evaluate(input_data)` | 低 | `lifecycle.py:166` |
| `TEXT` → 标准 Pipeline | ✅ 已实现 | — | `lifecycle.py` |
| `STRUCTURED` → 快速路径（绕过文本噪声评估） | ❌ 缺失 | 低 | 需新增 `_evaluate_structured()` |
| `IMAGE/AUDIO/MULTIMODAL` → 外部预处理 → 重新构造 TEXT | ❌ 缺失 | 低 | 需新增 `_evaluate_with_preprocessing()` |

**影响**：非文本输入会直接丢给文本规则评估器，导致荒谬的噪声评分。但由于当前系统专注文本，此问题暂不触发。

---

### 2.3 噪声评估器 — 三维话题切换检测模型（核心修正，P0 优先级）

当前代码（`rule_based.py:276-326`）的上下文断裂逻辑：

```python
# 4. Context break (0-0.20): no overlap with previous turn
if history:
    last_query = history[-1].content.lower()
    if not self._has_overlap(text_lower, last_query):
        noise += 0.20   # ← 武断：无实体重叠 = 断裂
```

新设计 v2.2 要求替换为**三维联合评估**：

| 维度 | 当前代码 | 新设计要求 | 状态 |
|---|---|---|---|
| **时间间隔因子 τ** | ❌ 完全缺失 | `HistoryEntry.timestamp` + 工作记忆衰减权重（<30s/5min/30min 三级阈值） | 未实现 |
| **指代意图失调** | ❌ 完全缺失 | 区分"话题切换"（无指代词）vs"上下文断裂"（强指代词 + 无实体匹配） | 未实现 |
| **描述方式变化** | ❌ 完全缺失 | 语义域集中度（domain concentration）区分"认知刷新"vs"混乱断裂" | 未实现 |
| **话题切换豁免** | ❌ 完全缺失 | 检测到"换个话题"/"by the way" → 降低断裂评分 | 未实现 |
| **新任务豁免** | ❌ 完全缺失 | 检测到"我想"/"能不能" + 无指代 → 降低断裂评分 | 未实现 |
| **三维联合评分公式** | ❌ 完全缺失 | `context_break_score = τ × (0.4 × 指代失调 + 0.6 × 描述变化)` | 未实现 |

**影响**：这是新设计 v2.2 的**核心修正**。当前代码会导致：
- 正常话题切换被误判为"噪声"（加 0.2）
- 新任务被误判为"低质量输入"
- 用户沉默 10 分钟后发新问题 → 系统因"无实体重叠"加噪声 → 后续解析策略保守化（降低置信度、增加澄清轮次）

**实现难度**：中（~200 行核心算法，但逻辑复杂，需要大量测试验证）。

---

### 2.4 ParserConfig 调控修正（P1 优先级）

当前代码（`models.py:812-834`）：

```python
@classmethod
def from_intent_context(cls, ctx: IntentContext) -> "ParserConfig":
    return cls(
        # ... 基础字段 ...
        enable_synonym_expansion=ctx.cognitive_profile.stability < 0.5,
        enable_topic_inheritance=ctx.cognitive_profile.tracking_depth > 0.6,
        prompt_style=ctx.prompt_style,
    )
```

新设计 v2.2 要求新增：

| 调控逻辑 | 当前代码 | 新设计要求 | 状态 |
|---|---|---|---|
| 高指代失调 → 同义词扩展 + 上下文回溯 | ❌ 缺失 | `if noise_source == 'referential_dissonance': enable_synonym_expansion=True; context_window_size=20` | 未实现 |
| 噪声来源感知（noise_source 字段） | ❌ 缺失 | `PCROutput_v1` 或 `IntentContext` 需增加 `noise_source` 字段 | 未实现 |

**影响**：当用户用不同方式描述同一话题（如"scan 0x401000" → "看一下那个地址的值"）时，系统不会自动触发同义词扩展，而是直接标记为"低质量输入"并提高保守度。这与新设计的"认知刷新感知"理念相悖。

**实现难度**：低（~20 行逻辑，但依赖 `noise_source` 字段）。

---

### 2.5 对抗测试集扩展（P1 优先级）

当前对抗测试集（`adversarial_suite.py:75-185`）有 6 个 category：
1. ambiguity — 8 cases
2. noise — 15 cases（空/特殊字符/注入/长度）
3. complexity — 9 cases
4. history — 4 cases（空/相关/主题切换/长历史/自指）
5. injection — 4 cases
6. unicode — 6 cases

新设计 v2.2 要求新增/扩展的 case：

| 新场景 | 当前覆盖 | 需要新增 | 状态 |
|---|---|---|---|
| 时间间隔感知（<30s 无实体重叠 → 高断裂） | ❌ 所有 HistoryEntry 无 timestamp | 需构造带时间戳的历史序列 | 未实现 |
| 正常话题切换（30s-5min 切换，无指代词） | ⚠️ 有 "topic switch" 但无时间戳 | 需增加时间维度 case | 未实现 |
| 新任务启动（"我想分析加密算法"，无历史实体重叠） | ❌ 无 | 需新增 case | 未实现 |
| 强指代 + 无实体匹配（"这个怎么弄？"，历史无"这个"） | ❌ 无 | 需新增 case | 未实现 |
| 描述方式变化（"scan 0x401000" → "看下那个地址"） | ❌ 无 | 需新增 case | 未实现 |
| 语义域集中度（单一域集中 → 正常切换） | ❌ 无 | 需新增 case | 未实现 |
| 语义域分散（多域分散 → 混乱断裂） | ❌ 无 | 需新增 case | 未实现 |

**实现难度**：低（~50 行测试 case，但需先实现数据契约的 timestamp 字段）。

---

### 2.6 集成测试扩展（P1 优先级）

当前集成测试（`test_integration.py:35-50`）覆盖 3 期望 × 4 画像 × 5 复杂度 = 60 组合。但画像列表中的 "topic-switching" profile（第 3 个）是静态的，没有动态时间维度测试。

新设计 v2.2 要求：
- 增加"时间间隔变化"维度（短间隔/中等间隔/长间隔/超长间隔）
- 增加"指代词有无"维度
- 增加"语义域集中度"维度

**实现难度**：中（需重构测试矩阵，增加 2-3 个维度）。

---

### 2.7 IntentAgent 集成更新（P1 优先级）

当前代码（`core/intent_agent.py:1025-1037`）：

```python
pcr_input = PCRInput_v1(
    query=latest_user_query,
    session_id=self._session_id or "",
    turn_index=len(self._conversation_history),
    session_history=pcr_history,
    process_context={...} if self._pid else None,
)
```

新设计 v2.2 要求：

| 字段 | 当前 | 新设计 | 状态 |
|---|---|---|---|
| `modality` | 未传入（默认无） | `Modality.TEXT`（当前系统专注文本） | 需更新 |
| `timestamp` | 未传入 | `time.time()`（当前时间戳） | 需更新 |
| `raw_payload` | 未传入 | `None`（当前无多模态输入） | 无需改动 |

**实现难度**：极低（~2 行修改）。

---

## 3. 关键修复清单（按优先级排序）

### P0 — 核心算法修正（影响用户体验）

| # | 修复项 | 改动范围 | 预估代码量 | 依赖 |
|---|---|---|---|---|
| 1 | **数据契约扩展**：`Modality` 枚举 + `PCRInput_v1`/`HistoryEntry` 增加 `timestamp` | `datacontract.py` | ~30 行 | 无 |
| 2 | **三维话题切换检测模型**：`NoiseEstimator` 核心算法替换 | `rule_based.py` | ~200 行 | #1（需 timestamp） |
| 3 | **IntentAgent 传入 timestamp** | `intent_agent.py` | ~2 行 | #1 |

### P1 — 基础设施 + 测试覆盖

| # | 修复项 | 改动范围 | 预估代码量 | 依赖 |
|---|---|---|---|---|
| 4 | **生命周期管理器模态分发器** | `lifecycle.py` | ~30 行 | #1 |
| 5 | **ParserConfig 高指代失调调控修正** | `models.py` + `datacontract.py`（需 `noise_source` 字段） | ~20 行 | #2（需三维模型输出 noise_source） |
| 6 | **对抗测试集扩展**：时间间隔/话题切换/新任务/描述方式变化 case | `adversarial_suite.py` | ~50 行 | #1, #2 |
| 7 | **集成测试扩展**：时间间隔 × 指代词 × 语义域集中度 | `test_integration.py` | ~100 行 | #1, #2 |

### P2 — 延迟优化（记录但不优先实施）

| # | 修复项 | 改动范围 | 预估代码量 | 依赖 |
|---|---|---|---|---|
| 8 | **Lazy Evaluation**：高置信度 TOOL 跳过认知画像更新 | `rule_based.py` | ~30 行 | 无 |
| 9 | **并行评估**：Stage 1/2/3 并行化 | `rule_based.py` | ~50 行 | 无 |

---

## 4. 与旧设计 v2.1 评估的对比

| 维度 | 旧设计 v2.1 评估 | 新设计 v2.2 重新评估 | 变化原因 |
|---|---|---|---|
| **总体完成度** | 78% | **65%** | 新设计增加了核心修正（三维话题切换检测），但代码未实现，拉低整体完成度 |
| **Layer 0 核心骨架** | 100% | 100% | 无改动 |
| **规则实现功能** | 70%（结构偏离） | **20%**（核心算法缺三维模型） | 旧评估侧重"结构未分包"，新评估发现"上下文断裂判定"算法缺陷更严重 |
| **测试基础设施** | 100% | 70% | 对抗测试集缺少新设计要求的场景覆盖 |
| **系统集成** | 50%（直接实例化） | 40% | 新增 `modality`/`timestamp` 字段未传入 |
| **ParserConfig** | 100% | 80% | 缺少高指代失调时的特定调控逻辑 |
| **数据契约** | 100% | 60% | 缺少 `Modality` 枚举 + `timestamp`/`raw_payload` 字段 |

---

## 5. 核心结论

**当前 PCR 实现状态：骨架完整，但新设计 v2.2 的核心修正（三维话题切换检测）完全未实现。**

### 5.1 已实现且无需改动的部分（保持 100%）

- ✅ 接口骨架（interface.py + registry.py + fallback.py + telemetry.py + config.py + lifecycle.py 基础功能）
- ✅ 期望识别器（ExpectationIdentifier）：三层级联（规则 → 历史 → LLM Fallback）
- ✅ 复杂度评估器（ComplexityEstimator）：YAML 配置 + 规则推导
- ✅ 认知画像（CognitiveProfiler）：EMA + Jaccard + 主题追踪
- ✅ Mock 实现 + 基准测试框架
- ✅ IntentParser 8 阶段 Pipeline
- ✅ Layer 1 融合（IntentContext.from_pcr_output + ParserConfig.from_intent_context 基础版）

### 5.2 必须修复的部分（影响正确性）

- ❌ **数据契约**：`PCRInput_v1` 和 `HistoryEntry` 缺少 `timestamp` 字段 → 三维话题切换检测的时间维度无法计算
- ❌ **噪声评估器**："上下文断裂"仍使用旧的一维逻辑（`_has_overlap` 直接加 0.2）→ 正常话题切换被误判为噪声
- ❌ **ParserConfig**：缺少噪声来源感知（noise_source）→ 高指代失调时不会触发同义词扩展

### 5.3 修复工作量预估

- **P0 核心修正**：~232 行代码（数据契约 30 + 三维算法 200 + IntentAgent 2）
- **P1 基础设施 + 测试**：~200 行代码（分发器 30 + 调控修正 20 + 测试 case 150）
- **P2 延迟优化**：~80 行代码（记录但不优先）
- **总计**：~512 行代码，预计 **2–3 个专注开发周期**（约 3–5 天）

### 5.4 与之前评估的关系

旧评估中的"78% 完成"是基于旧设计 v2.1 的标准。新设计 v2.2 发现了旧设计中的**核心算法缺陷**（上下文断裂判定武断），并提供了修正方案。从工程角度看，这 200 行三维算法代码是**修正旧缺陷而非新增功能**，因此应该优先实现。

---

*评估文件：当前代码 vs 新设计 v2.2*
*关键参考：docs/frontend-agent/design_pcr_interface_v2_1.md + docs/frontend-agent/design_layer0_pcr_and_layer1_intent_parser.md + docs/frontend-agent/design_pcr_issues_discussion.md*
