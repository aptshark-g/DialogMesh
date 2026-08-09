# 上下文设计 vs 实现 — 第二轮深度对照

> 日期: 2026-08-03 | 方法: 逐设计文档精读 + 逐组件对照 + 运行时实测
> 配套: `AUDIT_ENTRY_20260803.md`（第一轮代码盘点）

---

## 一、设计文档清单与映射

| 设计文档 | 定位 | 对应实现 | 总体符合度 |
|---|---|---|:---:|
| `docs/BUSINESS_CHAIN_02_CONTEXT.md` | v6 链规范（DS+BA+SC+IR 流程）| context/* | 声称 80%，实测 ~15%（未接线）|
| `docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md` | 跨域编译（域选择/预算/IR/剪枝）| assembler/selector/allocator/ir/pruner | ~65%（算法层）|
| `docs/v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md` | 双 Compiler（Memory/Context）| source/graph_source/assembler | ~40%（无 Memory Compiler）|
| `docs/v3.0/ENGINEERING_CONTEXT_MANAGER.md` | v3 分层工作记忆（Hot/Warm/Cool/Cold）| manager/window/store/models | ~45%（降级为 2 层）|
| `docs/v3.0/design_context_window.md` | v3 增量窗口 | context_window/ 模块 | ~70%（但接线靠死链）|
| `docs/v3.0/CONTEXT_COMPRESSION_DESIGN.md` | MemGPT 渐进式摘要 | window.ContextCompressor + context_window.compressor | ~25% |
| `docs/v5/CONTEXT_GAP.md` | 状态报告（95% 完整）| — | ❌ 与事实相反 |
| `docs/v5/DESIGN_THREE_PARADIGM_LLM_CONTEXT.md` | 温度×距离×信息价值 | compiler/three_paradigm_context.py + temperature_patch.py | 实现于 compiler 侧，context 侧仅 patch 且孤儿 |

---

## 二、DESIGN_CROSS_DOMAIN_CONTEXT vs 实现

### 2.1 域选择矩阵 — 🟡 两套矩阵互相打架（P0）
- 设计 §4.2: task=(E,B,P) query=(C,E,P) correction=(B,E,K) discussion=(P,C,E) casual=(C,P) topic_switch=(C,B,P)。
- `domain_selector._MATRIX`: query=(**C,K,E**) —— **与设计不一致**（aux1=K 因果，aux2=E）。
- `budget_allocator._INTENT_DOMAIN_MAP`: query=(C,E,P) —— 与设计一致。
- 已实测: 同一 QUERY 意图，selector 输出 [C,K,E]，allocator 输出 [C,E,P]。
- `assemble_ir()` 串联二者时: selector 决定「哪些域出现在 IR」，allocator 决定「每域预算」——
  K 域有 allocation 但无预算、E 域有预算但 selector 可能不给 allocation → 预算与域选择错位。

### 2.2 预算模型 — 🟡 实现完整但死代码
- 三层预算（200/300/200）✅ 实现于 `budget_allocator`，`redistribute_surplus` ✅。
- 用户可定制预算（§10 provider 自适应/用户习惯/显式设置）**未实现**（无 UserProfile 第九维挂钩）。
- `assemble_ir` 中 mandatory=min(200, budget//4) 的折算与设计「必要层=200」不一致（预算缩水时同比例缩减）。

### 2.3 CrossDomainContextIR — ✅ 结构完整
- `cross_domain_ir.py` 实现 IR v2 全结构 + `to_prompt` + `from_dict` + `to_legacy_context` ✅。
- `to_prompt` 支持 0-budget 域过滤 + cross_ref 标注 + token 截断 ✅（与 §7 对齐）。
- 问题: **两套 IntentCategory 枚举**（cross_domain_ir 与 domain_selector 各一），
  `assemble_ir` 里 `selection.intent_category`（domain_selector 版）直接塞进 `CrossDomainContextIR`（期望 cross_domain_ir 版）——
  类型上错配但值相同，Python 不报错 → 静默降级。

### 2.4 跨域扩展与引用 — 🟡 明确标注 stub
- `cross_domain_expander.py` 头注释自认「Stub: full impl (Phase 2) 未做」，产出全是 `{"stub": True}`。
- `cross_ref_builder.py` 也是 stub（naive shared-event_id 匹配，无多跳/语义/介数）。
- 设计 §3.2 的「Event ID 多跳扩展」核心机制 **未实现**。
- 两者均无生产调用点。

### 2.5 子图溢出修剪 — ✅ 算法层完整（但未接线）
- `pruner.py` 实现 4 轮修剪 + 3 步降落 + 意图权重表 —— **设计 §11 全对齐**（已实现的部分质量最高）。
- `_INTENT_CONFIG` 与设计 §11.2 权重表一致（task 0.3/0.2/0.5 等）✅。
- 但: 唯一调用点在 assembly 包装层且**传 string 而非 List[PruningNode]** → 必然 AttributeError → fallback。
- `topic_switch_landing` 无任何调用点。

### 2.6 事件流粘合剂（设计 §3）— ❌ 0%
- 设计核心主张「Event Log 是唯一权威索引，跨域靠 Event ID JOIN」。
- 实现: `cross_domain_expander` 只收 event_id 参数但**从未与 EventLog 对接**；
  `source_events` 字段在 IR 里存在但生产无人填充（子图 compiler 的 DomainEntry 有 source_events，
  但那条路也是死代码）。Event ID 跨域索引**未实现**。

---

## 三、DESIGN_V4_CONTEXT_ENGINEERING vs 实现

### 3.1 双 Compiler 架构 — ❌ 只做了一半
- 设计: Memory Compiler（懒合并/冲突仲裁/图重写）+ Context Compiler（子图裁剪/IR）。
- 实现: 无独立 Memory Compiler（consolidation/cold_indexer 在行为链域）；Context 侧只有
  `assembler.assemble_ir`（retrieve→rank→IR），**没有「锚点 2 跳水波扩展」的编译器主流程**——
  水波扩展在 `graph_source.ConceptGraph.expand_subgraph` 里，但没接到 assemble_ir。
- Context IR 的「sections 结构」设计（topic/reasoning/constraints/history/profile）
  vs 实现（domain 分组的 entries）—— 实现是更合理的演化，不算偏差。

### 3.2 Patch Chain 持久化 — ❌ 未实现
- 设计 §2.10: Base State + Patch 链。实现: 无。

### 3.3 多源 Source — ✅ 实现扎实（但孤儿）
- `source.py` 提供 Observation/Document/Hybrid/Knowledge/Skill/World/Engineering/Causal/Vector/
  HybridKnowledge/HybridSkill 共 11 类 source + `_keyword_score` + `_extract_bundle_text`。
- `graph_source.py` ConceptGraph 4 级匹配（regex/关键词/embedding/BFS）**是全文审计中最完整的新实现**。
- 但生产零装配: `ContextAssembler.with_hybrid_index / with_tiered_store` 工厂无人调用，
  `CausalSource` 无人调用，`TopicTreeContextSource` 在 engine 里从未赋值。

---

## 四、ENGINEERING_CONTEXT_MANAGER（v3 分层工作记忆）vs 实现

| 设计 | 实现 | 符合度 |
|---|---|:---:|
| 4 层工作记忆 Hot/Warm/Cool/Cold | 🟡 降级为 2 层（ContextSlice + ContextSummary）| 40% |
| Hot→Warm→Cool→Cold 降级 + 回热 | ❌ 无（只有 slices→summaries 单向压缩）| 20% |
| 6 个 LLM 实例专属组装器（PCR/Intent/Planning/Meta/Reflective/Answer）| ❌ 无（v4 已改为域驱动，非 LLM 驱动）| 0%（架构演进，合理）|
| TokenBudgetManager | ❌ 无独立组件（预算在 WindowConfig 里）| 30% |
| 压缩策略 rule/llm/hybrid | 🟡 只有规则提取（关键词/实体/决策拼接）| 30% |
| 与 Topic Tree / Cognitive Tree 集成 | 🟡 CognitiveTree 集成 ✅（manager.py `_write_intent_to_cognitive_tree`）；TopicTree ❌ | 50% |
| 跨会话共享 / 语义回热 / 自适应压缩率 | ❌（设计 §12.1 已诚实标记 S-01~S-05 简化，实现连 S 都没做全）| 0% |

**注意**: 该设计是 v3.0 的 6-LLM 架构，与 v4/v6 域驱动架构是**结构性替代**关系，
不是欠账。真正的欠账是: 设计 §12.1 的简化项 S-01~S-05 在实现中也没有恢复路线。

---

## 五、design_context_window + CONTEXT_COMPRESSION_DESIGN vs context_window/ 模块

### 5.1 design_context_window（v3 增量窗口）
- `context_window/window_manager.py`（WindowManager/WindowConfig）+ `compressor.py`
  （RuleBasedCompressor/CompressionLevel）实现三层窗口 + 规则压缩 ✅ 约 70%。
- 接线: 唯一生产消费者是 `v3_common/integration_bridge.py`（AgentPipeline）——
  该桥非主路径（CLI 走 state machine，API 走 agent_native）。**实现良好但面向退役架构**。

### 5.2 CONTEXT_COMPRESSION_DESIGN（MemGPT 渐进式摘要）
- 设计核心: 渐进式摘要（单级→多级）、LLM 摘要 prompt、依赖感知压缩、跨会话复用。
- 实现: `ContextCompressor.compress` 是**规则关键词提取**（无 LLM、无渐进、无依赖感知）；
  `RuleBasedCompressor` 同样规则化。符合度 ~25%。
- `context_window.models.WindowTurn` 有 `estimated_tokens` 中英分算 ✅（小亮点）。

---

## 六、DESIGN_THREE_PARADIGM_LLM_CONTEXT vs 实现

- 设计（v5）: 温度（访问冷热）× 距离（语义远近）× 信息价值 三正交范式注入。
- 实现: 主实现位于 `core/agent/compiler/three_paradigm_context.py`（对话树域，上次已审计）。
  context 侧只有 `temperature_patch.py`（`patch_context_manager` 用 `ThreeParadigmContext._information_value`
  重排序 ContextManager.entries）—— **无任何调用点**，且依赖 v3 `context_manager.entries` 属性
  （v4 manager.py 根本没有 `entries` 字段，只有 window.slices）→ 即使被调也会静默失效。

---

## 七、第二轮结论（设计 vs 实现）

1. **算法层 > 接线层 > 状态报告层**:
   - 算法层: pruner（§11 全对齐）、IR（§7 全对齐）、graph_source（v4 全对齐）、sources（11 类）——
     **写得最好的是没人用的部分**。
   - 接线层: 3 路全断（CLI 裸 prompt / API 假接线 5 处错配 / v3 服务面向退役路径）。
   - 状态报告层: `CONTEXT_GAP.md` 宣称 95%「最完整链」—— **与实测相反，是假状态**。
2. **两代设计混居**: v3（ENGINEERING_CONTEXT_MANAGER 6-LLM 驱动）与 v4（域驱动 Context Engineering）
   是结构性替代；v3 的窗口/压缩模块（context_window、window.ContextCompressor）没有完成迁移
   或退役，成为并行实现族。
3. **两处真实代码缺陷（非缺接线）**:
   - DomainSelector vs BudgetAllocator 域矩阵不一致（query: C,K,E vs C,E,P）；
   - 两套 IntentCategory 枚举混用。
4. **核心机制缺口**: Event ID 跨域索引（设计 §3 的「唯一权威索引」）**从未实现**，
   这解释了为什么 5 套实现都没能真正把多域信息「织」起来——缺的是粘合剂，不是零件。

---

## 八、对施工的初步指向（待拍板）

1. **接线优先于重构**: 先修 assembly 5 处 API 错配 + 补状态机 CONTEXT phase handler，
   让现有算法层真正跑起来，再谈收敛 5 套实现。
2. **归一并修**: DomainSelector/BudgetAllocator 矩阵 + 两套 IntentCategory 二选一。
3. **事件粘合剂**: 设计 §3 的 Event ID 跨域索引是「上下文的真正内核」，建议单独立项评估
   （关联链 Event Sourcing 已提供类似基建，可复用）。
4. **状态文档纠偏**: CONTEXT_GAP.md / BUSINESS_CHAIN_02 立即修正，防后续误导。
5. **context_manager/ 87KB discourse_manager**: 已无生产调用（unified_context 显式注释），
   归档候选，但归档前需确认无隐藏引用。
