# 意图设计文档审计 + 接口预扫描（阶段三/四）— 2026-08-03

> 范围：15 篇意图相关设计文档全部精读（layer0/layer1/ENGINEERING/CHAIN_01/UNIFIED/MULTI_SIGNAL/ROUTING_MATRIX/TIERED/MULTI_INTENT_SPLIT/AGENT_NATIVE...）。
> 配套：`IMPLEMENTATION_AUDIT_20260803.md`（阶段二实现审计）、`AUDIT_ENTRY_20260803.md`（资产盘点）。
> 定位：意图内核拍板备料 + **意图↔对话树接口预扫描**（解对话树拍板 #5/#6 悬空依赖）。

---

## 一、设计资产地图与演进脉络

### 1.1 演进代际

| 代际 | 文档 | 范式 | 状态 |
|---|---|---|---|
| v1 | `design_layer1_intent_parser.md`（532L）| 8 阶段纯规则 + LLM fallback + TaskGraph DAG | 设计完成 |
| v2.2 | `design_layer0_...`（2124L，宪法级）| PCR 认知调控 9 模块 + 认知刷新感知三维模型 + 编排门控 | 核心引擎已验证（184 测试）|
| v2.2.1 | 同上修正 | 代词消解前置（Pre-Stage 3.5）+ Fast Path 门控 + 同义词方向反转 | 设计修正 |
| v3.0 | `ENGINEERING_INTENT_PARSER.md`（909L）| 认知双工（规则∥Intent-LLM）+ 自适应阈值（GP+MLP+Thompson）| 工程规格 |
| v5 | UNIFIED / MULTI_SIGNAL / ROUTING_MATRIX / MULTI_INTENT_SPLIT / AGENT_NATIVE | **Agent-Native（LLM 决策，算法给 hints）** + 五链并行 + 贝叶斯融合 + 3D 路由 | 设计完成 |

### 1.2 三条设计主线（并存未收敛）

```
主线 A（规则优先）: 8 阶段 Pipeline → 确定性 90%+ → LLM 仅 fallback（v1/v2.2/ENGINEERING）
主线 B（多信号融合）: 5 路弱信号贝叶斯（SVO/峰度/OCEAN/时间/画像）→ V3.2 升维 3D 路由矩阵
主线 C（Agent-Native）: LLM 决策 + 算法 hints → 五链并行验证 → Fusion/Reflexion（v5）
```

### 1.3 统一方案

`BUSINESS_CHAIN_01_UNIFIED_INTENT.md` + `DESIGN_UNIFIED_INTENT_ASSOCIATION.md`：3 Tier（结构 0.1ms / BGE-SVO 1-5ms / LLM 50-200ms）+ 5 层漏斗（L1 句法→L1.5 补全→L2 语义→L2.5 信念→L3 语用→L4 时序→L5 因果）。

---

## 二、设计内部矛盾（6 项）

### 2.1 范式对立：确定性优先 vs LLM-first（最核心）
- 旧 8 阶段：**确定性优先**（规则 80%+，LLM fallback 仅长尾）
- 新包（v5 Agent-Native）：**LLM 决策**（`multi_intent_splitter` 注释"Trust LLM split—no fragment verification"）
- **文档自打脸**：`ENGINEERING_MULTI_INTENT_SPLIT.md` §八 决策记录明确写"链路验证方式选**规则为主**（80%+ 情况字面+行为链可判断，LLM 仅严重分歧）"——但**实现（intent/ 新包）是 LLM-first**，且跳过了文档要求的 5 链验证（`split()` 注释"Trust LLM, no verification"）。

### 2.2 三套意图类别体系
| 体系 | 来源 | 粒度 | 示例 |
|---|---|---|---|
| IntentCategory | 旧 8 阶段（领域特定）| 细 | SCAN_MEMORY / HACK_VALUE / DISASSEMBLE |
| SubIntent.category | 新包（通用）| 粗 | 诊断/修复/探索/吐槽/信息查询 |
| expectation | PCR/Unified（服务模式）| 最粗 | TOOL / ADVISOR / COMPANION |

→ 三套并存，对话树 `primary_intent` 用哪套未定。

### 2.3 PCR 调控：设计 9 模块 vs 实现几乎不读
- 设计（layer0 §5.1）：expectation/noise/complexity/stability/noise_source 调控全部 9 个子模块
- 新包实现：仅 `fusion_decider` 读 complexity/noise；`dual_track` 不读 PCR
- 旧版实现读 PCR 但断链（registry 丢失）

### 2.4 认知刷新感知三维模型（设计）vs 实现缺失
- layer0 §4.3：上下文断裂 = 时间间隔 τ × (0.4 指代失调 + 0.6 描述方式变化)，含话题切换/新任务双豁免
- **这是对话树"组块边界=方向性断裂"公理的最精确实现判据**（见 §四）
- 实现：需确认 PCR noise_estimator 是否实现三维模型（阶段二未查 PCR）

### 2.5 Tier/Layer/Stage 三套维度命名混乱
- Tier 0/1/2 = 速度谱系（规则/BGE/LLM）
- Layer 1-5 = 语义漏斗（句法→补全→语义→信念→语用→时序→因果）
- Stage 0-7 = 8 阶段流水线
- 三套维度在同一文档混用，接口易错位

### 2.6 多意图拆分的验证被实现跳过
- 设计（ENGINEERING_MULTI_INTENT_SPLIT）：5 链并行验证（profile/association/discourse/literal/engineering）→ FusionDecider 三策略
- 实现（multi_intent_splitter）：`accepted = candidates  # trust LLM`——**直接信任 LLM 拆分，跳过链验证**（注释：nemotron rejects partial fragments）
- fusion_decider/ambiguity_gate 零引用 = 设计的验证层在实现里被绕过

---

## 三、设计-实现对照（新包 vs 设计 vs 旧版）

| 设计概念 | 设计文档 | 新包实现 | 旧版实现 | 状态 |
|---|---|---|---|---|
| 8 阶段 Pipeline | layer1/ENGINEERING | — | un_use（断链）| ❌ 已死 |
| 认知双工（规则∥LLM）| ENGINEERING §9.2 | coordinator（单 LLM 调用）| — | ⚠️ 变了形态 |
| 多意图拆分 | ENGINEERING_MULTI_INTENT_SPLIT | multi_intent_splitter（LLM-first）| 正则连词 | ⚠️ 跳过验证 |
| 五链验证 | 同上 §3 | literal_chain/llm_chain（仅字面链）| — | ⚠️ 只实现 1/5 |
| FusionDecider | 同上 §4 | fusion_decider（三策略+PCR）| — | ✅ 实现，未接线 |
| AmbiguityGate | 同上 §5 | ambiguity_gate（5 触发器）| _detect_ambiguities（5/6 类型）| ✅ 实现，未接线 |
| 3D 路由矩阵 | DESIGN_V3.2_ROUTING_MATRIX | — | — | ❌ 未实现 |
| 5 路贝叶斯融合 | DESIGN_MULTI_SIGNAL_INTENT | — | — | ❌ 未实现 |
| 递归收敛快匹配 | INTENT_RECURSIVE_CONVERGENCE | — | — | ❌ 未实现 |
| 自适应阈值 | ENGINEERING §7 | — | adaptive_threshold（632L，未接线）| ⚠️ 存在未接 |
| 共享分类内核 | DESIGN_TIERED_ACTION_RESOLVER | — | — | ❌ 未实现 |

---

## 四、认知刷新感知 → 对话树组块公理的强化（接口预扫描核心发现）

### 4.1 三维模型与公理的映射

| layer0 三维判据 | 对话树公理（KERNEL_ABSORPTION §八）| 说明 |
|---|---|---|
| 时间间隔因子 τ（<30s=活跃 / >30min=新会话）| 短期缓存的时间局部性 | 工作记忆刷新的工程化 |
| 指代失调（强指代词+无实体匹配=断裂 0.85）| **组块间引用（cross_ref 的触发信号）** | "这个/刚才那个"试图跨组块引用 |
| 描述方式变化（高域集中度=正常表达变化）| **组块内表达变异（不应切分）** | 同一组块内换说法是正常的 |
| 话题切换豁免（"换个话题"×0.1）| 显式组块边界信号 | 与 topic_markers 一致 |
| 新任务豁免（"帮我/我想"+无指代 ×0.2）| 新组块创建信号 | 不是断裂是刷新 |

### 4.2 结论
**对话树的"方向性断裂"判据应该用 PCR 三维模型，而不是只有 topic_markers + cohesion**——三维模型天然区分"组块内表达变化（不切）"、"组块间引用（建 cross_ref）"、"组块切换（新块）"、"新组块（豁免）"四种情况，正是公理需要的边界语义。这是本次审计对对话树最直接的贡献。

---

## 五、意图↔对话树接口预扫描（4 接口）

| 接口 | 意图侧现状 | 对话树侧 | 结论 |
|---|---|---|---|
| primary_intent | 三套类别体系未定（§二.2）| B models：segmenter 用 `first.predicate` 规则填；A 无 | **需拍板用哪套 + 谁产出** |
| 话题切换信号 | 认知刷新三维模型（设计）+ MultiPerspectiveValidator（engine 已接）| A/B 用 topic_markers + cohesion | **建议对话树切分接入三维模型**（§四）|
| 域选择输入 | DESIGN_CROSS_DOMAIN_CONTEXT：意图类别→域 C 权重 | ContextCompiler 域 C | 意图断了 → 域选择输入待恢复 |
| compass intent_novelty | ThreeParadigmContext._information_value 用 intent_history | engine 已注入 | 意图历史喂给 compass 的接线待查 |

---

## 六、待拍板清单（意图内核）

1. **范式**：确定性优先 vs LLM-first vs 认知双工——建议：PCR/三维模型做**确定性边界预判**（Fast 路径），LLM 做**灰区决策**（A13 长证明后验），算法与 LLM 分颗粒度投影（P2）
2. **意图类别统一**：三套合一（expectation 服务模式 / category 领域意图 / sub_intent 子任务）——建议分层而不是替换
3. **新包接线**：engine 是否启用 dual_track 热路径；补 llm 缺失时诚实降级（现全 pass 静默）
4. **registry 断链**：旧 8 阶段复活 vs 新包替代——倾向后者，旧版归档 un_use
5. **5 链验证补全**：fusion_decider/ambiguity_gate 零引用 → 接入 multi_intent_splitter（A4 多链投票）
6. **PCR 调控恢复**：9 模块调控点在新包落地（至少 fusion/ambiguity 两处）
7. **意图↔对话树**：primary_intent 来源定一；三维模型接入切分；域选择输入恢复（§五 4 接口）
8. **测试补全**：intent/ 10 文件无专属测试；adaptive_threshold 632L 未接线未测试

---

## 七、阶段三/四结论

1. **意图设计资产同样未收敛**：三主线（规则/贝叶斯/Agent-Native）并存，v5 设计自打脸（文档说规则为主，实现是 LLM-first 且跳过验证）。
2. **最有价值的发现**：layer0 认知刷新感知三维模型 = 对话树组块公理的最精确实现判据——一次审计解开两个模块。
3. **新包质量高但半成品**：fusion/ambiguity 是金矿（设计完备），但被 splitter 绕过；dual_track 冷路径（DerivationCompressor 启发链）是 A24 在意图域的落地，未接线。
4. **意图↔对话树 4 接口全断**：primary_intent/话题切换/域选择/compass 四接口无一闭环——印证"先审计意图"的正确性。

---

*本文件是意图审计阶段三/四成果；与 IMPLEMENTATION_AUDIT_20260803.md、AUDIT_ENTRY_20260803.md 共同构成意图审计完整资产。*
