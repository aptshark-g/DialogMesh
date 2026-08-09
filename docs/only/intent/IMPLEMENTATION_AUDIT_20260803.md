# 意图模块实现审计（阶段二）— 2026-08-03

> 范围：`intent/` 新包 10 文件全读 + shim/un_use 两版旧实现 + import 探针 + 引用方全查（MCP/Service/Engine/Blueprint/Bridge）。
> 方法：anaconda 3.9 实跑 import；rg 全库引用追踪；逐文件精读。

---

## 一、核心发现（三句话）

1. **旧 8 阶段 IntentParser 从源头断开**：`un_use/intent_parser.py:100-101` import 一个**不存在的模块** `core.agent.v3_common.intent_rule_registry`（全库 `*rule*` 搜索零结果）→ `ModuleNotFoundError` → shim（`v3_common/intent_parser.py`）try 失败 → `IntentParser = None`。
2. **11 个引用方全部拿到 None parser**：MCP Server、Service（agent_service/async_agent_service）、v4/un_use、gates、cognitive_tools、pcr/tests 等——**生产路径意图解析静默降级**。
3. **新包 `intent/`（Agent-Native LLM-first）几乎没接线**：10 文件全部可 import，但仅 2 个懒加载引用点（blueprint executor + engineering bridge），engine 主路径不用。

---

## 二、import 探针实况

| 目标 | 结果 | 说明 |
|---|---|---|
| `v3_common.intent_parser`（shim）| ⚠️ `IntentParser = None` | try 分支因 un_use 断链失败，被 except 吞 |
| `v3_common.un_use.intent_parser`（旧 3000 行）| ❌ `ModuleNotFoundError: intent_rule_registry` | **文件已丢失（文档说存在，304 行）** |
| `intent.coordinator` / `dual_track` / `multi_perspective` / `fusion_decider` / `ambiguity_gate` / `ambiguity_bridge` / `multi_intent_splitter` | ✅ 全部可 import | 新包自洽 |
| `intent/` 包 | ⚠️ 无 `__init__.py` | namespace package（Python 3.3+ 可 import）|
| `v4/tiered/` | ⚠️ 空壳（66B `__init__.py` + tests 空目录）| 内容已搬走/遗留 |

---

## 三、新旧代际关系（演进图谱）

```
旧: v3_common/un_use/intent_parser.py（3000 行 8 阶段，规则优先）
      └─ import 断链: intent_rule_registry 不存在 ❌
      └─ shim（325B）: try → 失败 → IntentParser = None
           └─ 引用方 11 处（MCP/Service/gates/cognitive_tools/v4-un_use/tests）全部 None

中间: v4/tiered/（TieredIntentParser 规则+LLM）→ 空壳遗留（__init__ + tests 空）
      v4/un_use/intent_parser.py（5KB 精简版）→ 依赖 shim，同样 None

新: intent/（Agent-Native LLM-first，Pi-like）10 文件
      ├─ models.py: SubIntent/ChainVote/ChainVotes/AmbiguityDecision/MultiIntentResult/VerifyContext
      ├─ coordinator.py: IntentCoordinator（单次 LLM 调用，全上下文注入）
      ├─ multi_intent_splitter.py: LLM 决定拆分点；信任 LLM 不验证片段
      ├─ multi_perspective.py: 多视角独立推理 + Master LLM 综合（Multi-Agent Debate）
      ├─ literal_chain.py / llm_chain.py: LLM-first 验证链（stanza 只给 hints）
      ├─ dual_track.py: 热路径（单 LLM 拆分）+ 冷路径（多视角→belief→HeuristicChain）
      ├─ ambiguity_bridge.py: 多视角死锁 → L2.5 belief 贝叶斯累积
      ├─ ambiguity_gate.py: 5 触发器 → pass/auto/llm/ask_user
      └─ fusion_decider.py: 三策略自动选（vote/weighted/llm）+ PCR 调控
      └─ 接线: 仅 blueprint/executor.py（DualTrackIntentPipeline 懒加载）
               + engineering_bridges.py（MultiIntentSplitter 懒加载）
```

---

## 四、新包范式：Agent-Native LLM-first（与旧 8 阶段范式相反）

| 维度 | 旧（un_use）| 新（intent/）|
|---|---|---|
| 决策者 | 规则/正则优先，LLM 仅 fallback（80% 规则层）| **LLM 决策，算法只给 hints** |
| 多意图拆分 | Stage 3 规则连词检测 | LLM 直接决定是否 multi + 输出 segments |
| 验证 | — | 多链投票（literal/profile/association/discourse）|
| 融合 | — | FusionDecider 三策略 + PCR 调控（complexity>0.8 强制 LLM；noise>0.7 加权 literal×1.5）|
| 歧义 | Stage 4-5 规则检测+消解 | AmbiguityGate 5 触发器 + 5 级成本升序（context→behavior→profile→LLM→ask_user）|
| 冷路径 | 无 | dual_track: 多视角→L2.5 belief→DerivationCompressor 启发链 |

**范式对照公约**：
- 新包符合 P2（算法与 LLM 不同颗粒度投影——算法给 hints，LLM 决策）、A4（ChainVotes 多链投票=信念竞争）、A13（ambiguity_bridge 贝叶斯累积=长证明后验）、A24（dual_track 冷路径用 DerivationCompressor 启发链=逆向动力系统）
- 但**几乎所有模块没有 llm 时静默退化**（`if not self.llm: return pass/单段`）——与 A6 后验学习、A18 真实验证的哲学有张力（退化即降级，无错误信号）

---

## 五、接线追踪（谁在生产路径）

| 路径 | 意图用什么 | 实况 |
|---|---|---|
| **engine 主路径** | `_intent_parser = None`（219 行，**只有 None 赋值无 lazy init**）| ⚠️ 意图解析实际是空的；`_l3_validator`（MultiPerspectiveValidator，关联链 L3）是真正接线的多视角验证（335-336 初始化）|
| **MCP Server** | `parser or IntentParser()` → **None** | 🔴 生产路径拿 None parser，ExecutionContext.parser_instance=None |
| **Service** | `DualTrackOrchestrator(pcr, parser)` → parser=None | 🔴 orchestrator.parser=None，意图段静默跳过 |
| **BlueprintExecutor** | `DualTrackIntentPipeline()` 懒加载 | ⚠️ 新包唯一真实接线点（但 executor 本身是否被 engine 调用待查）|
| **IntentBridge**（engineering_bridges）| `MultiIntentSplitter()` 懒加载 | ⚠️ 同上 |
| **association/l3_intent** | `MultiPerspectiveValidator`（4 视角：discourse/profile/association/pcr）| ✅ engine 已接（这是真正跑着的意图验证）|

---

## 六、意图↔对话树接口预扫描（对话树拍板 #5/#6 的解）

| 接口 | 意图侧现状 | 对话树侧 | 缺口 |
|---|---|---|---|
| `primary_intent` 来源 | 新包 SubIntent.category（LLM 产出）；旧版 IntentCategory（规则，已断）| DiscourseBlock.primary_intent | **LLM 产 category vs 规则产 category 两套，未统一** |
| 话题切换信号 | "意图类别突变"（design_topic_tree）；新包 multi_intent_splitter 的 LLM 拆分 | A/B 用 topic_markers + cohesion | 意图类别突变信号**未接入**对话树切分 |
| 域选择 | DESIGN_CROSS_DOMAIN_CONTEXT：意图类别→域 C 主/辅 | ContextCompiler 域 C | 意图类别来源断了 → 域选择靠什么？待查 |
| compass 信息价值 | `intent_novelty`（ThreeParadigmContext._information_value）| engine 已注入 | 意图历史是否被喂给 compass？待查 |
| VerifyContext.discourse | 新包模型已有 `discourse` 字段（DiscourseBlockTree context）| 对话树块 | **模型层接口已定义，接线无** |

---

## 七、阶段二结论

1. **意图模块是三代分裂 + 一处断链 + 一个空壳**：旧 8 阶段断链（registry 丢失）、v4/tiered 空壳、新包 Agent-Native 未接线——与 PCR/行为链/对话树同型问题（多代演进 → 旧路径断裂 → try/except 吞 → 静默降级）。
2. **生产路径意图实际由关联链 L3 MultiPerspectiveValidator 承担**（engine 已接 4 视角），旧 shim 和新包都是"纸面"的。
3. **新包设计质量高**（Agent-Native 符合公约多公理），但缺接线、缺测试、缺 llm 时的诚实降级。
4. **对话树接口**：VerifyContext.discourse 已定义（模型层），但 primary_intent 来源、话题切换信号、域选择三接口全断。

---

## 八、待拍板清单（阶段四/五备料）

1. **内核选型**：旧 8 阶段（修复 registry 断链即复活）vs 新 Agent-Native 包（补接线）vs 关联链 L3 为准（现状）——倾向新包 + L3 协同（A4 多链投票已在两处实现，可归一）
2. **registry 断链**：`intent_rule_registry` 是补回旧文件还是由新包替代（倾向后者）
3. **shim 清理**：11 个引用方改为防御式（IntentParser None 时显式降级日志）或全部切新包
4. **意图↔对话树三接口**：primary_intent 来源定一（LLM category）、话题切换信号接入、域选择输入恢复
5. **新包接线**：engine 是否启用 dual_track 热路径（补 llm 缺失时的诚实降级）
6. **测试补全**：intent/ 10 文件无专属测试（tests 目录空），需按 v2 §11.1 标准补

---

## 九、补读发现（2026-08-03 第二轮完整执行）

> 首轮遗漏 + 截断补全：l3_intent 全文 / v4_un_use / adaptive_threshold 两套 / prompts / engine L3 调用 / layer0 全文 / ENGINEERING 截断段 / gates 编排门控。

### 9.1 engine 真正接线的意图链 = 关联链 L3（实锤）
```
engine.py:454-470  _run_association_chain 内:
  zone = pcr_output.zone（PCR zone 先验）
  b7d = L2.5 belief（best_intent 的 belief_7d）
  intent_hyp = _last_parse_result.intent（旧 shim parser 产物，通常 None）
  if not intent_hyp_str: → zone_intent_prior(zone) or "信息查询"  ← D-14 PCR zone 播种
  intent_result = _l3_validator.validate(intent_hypothesis, belief_7d, pcr_zone)
```
- **L3 4 视角**：discourse_tree / profile / association / pcr（vote，consensus=accepts≥3 或 ≥2 且 0 reject；死锁→LLM）
- `zone_intent_prior` 从 `l2_config.get('l3.zone_intent_map')` 读——**PCR zone → 意图先验已接通**（D-14）
- `validate_split` 已实现（多意图拆分验证）——但新包 splitter 绕过它（trust LLM）
- **反馈信号**：`feedback.tree_annotation = {topic, action}` + `profile_update`——意图→对话树/画像的反馈接口已存在
- **DEFAULT_INTENTS = ["诊断","修复","探索","吐槽","信息查询","指令"] = 新包 SubIntent.category 体系**（同源）

### 9.2 第四套意图类别体系（prompts/intent_classifier.py 16 类）
chat/question/analyze/compare/apply/evaluate/recommend/plan/debug/refactor/code/search/summarize/statement/imperative/unclear——与 IntentCategory（旧）/ SubIntent.category（新）/ expectation（PCR）**四套并存**。

### 9.3 v4/un_use TieredIntentParser（中间代，也已断）
- 依赖 `core.agent.v4.tiered.pipeline`（空壳目录！）+ `RecursiveConvergenceMatcher`（`tiered/topic_matcher.py`，可能不存在）
- 依赖 shim IntentParser → None → `_parser._extract_entities` 调用即炸
- 归因：`v4/tiered/` 空壳 = TieredIntentParser 的实现基座被搬走/删除，留下引用残骸

### 9.4 adaptive_threshold 两套并存
| 位置 | 结构 | 用途 |
|---|---|---|
| `v3_common/adaptive_threshold.py` | PCRFeatureVector + SmallMLP(8→16→8) + IncrementalGP + Thompson | ENGINEERING §7 规格的 GP+MLP 实现 |
| `coordinator/adaptive_threshold.py` | ThresholdProfile + Bayesian feedback + 模式选择 | 另一套（双轨/打分）|

两套均未接入 engine（engine 只用 `gates.AdaptiveThresholds` 简单 EMA）。

### 9.5 MCP 生产路径：走旧 shim parser（None）的残骸
`mcp/server.py:146` `parse_intent` → `CognitiveTools.run("intent_parser_full_pipeline")` → 旧 shim → None → **MCP 的 parse_intent/explain_intent 实际是空转**（ExecutionContext.parser_instance=None）。

### 9.6 layer0 编排门控（v2.4，设计完整、代码已有部分）
- 三层门控：Gate-0（Hard，>0.95 直接 RULE_FAST_PATH）/ Gate-1（PCR 完整）/ Gate-2（Router LLM 3B，只读 PCR 结构化输出，选 Blueprint）
- Tool Registry + Blueprint 4 预置 + RouterOutputValidator（硬约束防注入）——**与 DESIGN_HYBRID_ARCHITECTURE 同构的"规则保底、LLM 增强"**
- LLM Provider 四后端（OpenAI/Local/Hybrid/Mock）已实现（§11.10.7 全 ✅）
- **实现状态**：gates.py 的 `DualTrackOrchestrator` 存在（P0 修复：adaptive 传入），但 `HardGate`/`PCRGate`/`OrchestrationGate` 是否全实现待查——至少 `_call_router_llm` 与 BlueprintExecutor 在 orchestrator/ 有实现

### 9.7 意图↔对话树接口补全（更新 §六）
- **L3 tree_annotation 是现成的意图→对话树反馈通道**（`{topic, action}`）——对话树 primary_intent 可直接消费
- **认知刷新三维模型**（layer0 §4.3）= 对话树组块边界判据的最精确实现（时间/指代/描述 + 双豁免）
- **D-14 zone→intent 先验已通**：PCR zone → L3 intent，域选择输入可借道（zone 已进 L3，L3 产物可喂 ContextCompiler）

---

*本文件是意图审计阶段二成果；与 AUDIT_ENTRY_20260803.md（资产盘点）、后续设计文档审计共同构成意图审计资产。*
