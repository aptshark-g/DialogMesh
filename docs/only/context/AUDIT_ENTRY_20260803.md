# 上下文（02）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/context/`（16 文件）+ 并行实现族 + 全库接线
> 结论先行: **上下文不是「未接线的 80%」，而是「v4 Context Engineering 管线在生产路径
> 0% 生效」** —— 与 `CONTEXT_GAP.md` 宣称的 95%「最完整链」完全相反。
> 同时存在 **5 套并行实现**（context / context_manager / context_window / v3_0 门面 /
> v4 门面 / assembly 包装），是「多代演进 → 代码分裂 → 静默降级」的典型样本。

---

## 一、五套并行实现全景

| 包 | 文件/规模 | 角色 | 生产接线 | 测试 |
|---|---|---|---|---|
| `core/agent/context/` | 16 文件（audit 目标）| v3 ContextManager + v4 Context Engineering 混居 | 见 §二 | 仅 test_context_manager.py 47 个 |
| `core/agent/context_manager/` | 5 文件（discourse_manager.py 87KB!）| v3 三权分立 DiscourseManager | ❌ 被 unified_context **显式注释掉** | 无 |
| `core/agent/context_window/` | 4 文件 | v3 增量窗口（WindowManager/RuleBasedCompressor）| 🟡 仅经 integration_bridge（AgentPipeline 非主路径）| test_window.py 12 个 |
| `core/agent/v3_0/context_manager/` | 1 文件 | 门面 → context/* | — | — |
| `core/agent/v4/context/` | 1 文件 | 门面 → context/* | — | — |
| `core/agent/assembly/` | 2 文件 | v6 包装（ContextAssembly/UnifiedContext）| 🔴 接了但**产生空上下文**（见 §二.3）| 无 |

**分裂根源**：`context/` 包同时容纳两代东西：
- v3 会话管理：`manager.py` / `models.py` / `store.py` / `window.py`（session → window → store，Pydantic v2）
- v4 Context Engineering：`assembler.py` / `source.py` / `domain_selector.py` / `budget_allocator.py` /
  `cross_domain_ir.py` / `pruner.py` / `cross_domain_expander.py` / `cross_ref_builder.py` /
  `graph_source.py` / `topic_tree_source.py` / `temperature_patch.py`

两代逻辑互不调用，仅因路径迁移被塞进同一个包 —— 与 discourse_tree 的 A/B 分裂同型。

---

## 二、生产接线实测（三路全断）

### 2.1 主路径（CLI `cmd_event_send` → engine.on_event）
- `runtime/engine.py` 顶部 import `ContextAssembler` / `DomainSelector` / `CrossDomainContextIR` /
  `TopicTreeContextSource`，`__init__` 声明 `_context_assembler` / `_domain_selector` / `_last_context` 字段。
- **但 `_compile_context()` 方法不存在**（已实测 `hasattr(CognitiveRuntimeEngine, "_compile_context") == False`），
  且 `_on_event_continue()`（含该调用）在库里**没有任何调用点** → 整个 v4 管线是死代码。
- 状态机路径（实际主路径）：`event/handlers.py register_all_handlers` 只注册
  PCR / INTENT / DISCOURSE / BEHAVIOR / META / PROFILE / PERSIST / ASSOCIATION 8 个 phase
  —— **PLANNING / CONTEXT / LLM 三个 phase 无 handler（已实测）** → 状态机跑到 CONTEXT 直接空转跳过。
- CLI 主聊天 `cmd_event_send`（cli/entry.py:173-250）在 `engine.on_event()` 后**绕过引擎**，
  自己拼 `system_prompt + user text` 直连 LLM —— 上下文零装配、零 IR、零子图、零画像。

**结论：CLI 主路径的 LLM 上下文 = 裸 prompt，context/ 全部组件零参与。**

### 2.2 API 路径（chat_api → bootstrap_v6 → AgentOrchestrator）
- `bootstrap_v6._load_unified_context()` → `UnifiedContext()`（assembly/unified_context.py）。
- `UnifiedContext.assemble()` 有 **5 处 API 不匹配**（已代码级确认）：
  1. `BudgetAllocator.allocate(raw_dict, budget)` — 签名是 `allocate(intent_category: str, ...)` → dict 不可哈希 → TypeError → fallback；
  2. `ContextAssembler()` 无 sources → `assemble(raw, alloc)` 恒返回空 `CrossDomainContext`；
  3. `ContextAssembler.assemble(intent, top_k)` 被当 `(raw_dict, allocation_dict)` 调用 — 类型错配；
  4. `SubgraphPruner.prune(dialogue_ctx: str, budget)` — 签名要 `List[PruningNode]` → 迭代字符串字符 → AttributeError → fallback 截断；
  5. `ContextLayer.build(perception)` — **ContextLayer 没有 `build` 方法**（有 assemble/inject_for_llm）→ AttributeError → fallback。
- 因此 v6 API 的 `result["context"]["dialogue"]` 恒为空串；`_llm_synthesize` 的
  `assembled_context` 恒为空；工程第 6 步因 `engineering=None` 恒跳过。
- `v3_session_api`（前端桥）同款：`AgentOrchestrator()` 无参 → 同一空上下文 + HTTP 拉画像 + Blueprint DAG。

**结论：API 路径调用了 context/，但每一层都摔进 fallback，产出 = 空上下文。这是「接了但没接对」的假接线。**

### 2.3 v3 服务路径（唯一有效接线）
- `core/service/v3_0/app_factory.py` + `session_manager.py` 用 `ContextManager`（context/manager.py）做
  会话生命周期/窗口/实体缓存 —— 47 个测试全绿，功能真实。
- 但这是 v3 遗留服务层；前端已走 v3_session_api → agent_native。**ContextManager 服务的是退役路径。**

---

## 三、v4 Context Engineering 组件逐一接线盘点

| 组件 | 实现 | 生产调用点 | 状态 |
|---|---|:---:|---|
| `assembler.assemble()` | ✅ | 无（assembly 空壳调了但无 sources）| 🔴 死代码 |
| `assembler.assemble_ir()` | ✅ 完整管线 | 无（全库唯一调用在 compiler/tests，且是另一套 assembler）| 🔴 死代码 |
| `domain_selector` | ✅ | runtime/engine import 但从未构造 | 🔴 死代码 |
| `budget_allocator` | ✅ | assembly 调了但签名错配 | 🔴 假接线 |
| `cross_domain_ir` | ✅（含 to_prompt/from_dict/to_legacy）| engine import；仅 `_on_event_continue` 死代码用 | 🔴 死代码 |
| `pruner` | ✅ 算法完整（4 轮修剪+3 步降落）| assembly 调了但类型错配 | 🔴 假接线 |
| `cross_domain_expander` | 🟡 stub（明确标注 Phase 2 未做）| 无 | 🔴 孤儿 |
| `cross_ref_builder` | 🟡 stub（naive event_id 匹配）| 无 | 🔴 孤儿 |
| `graph_source` (ConceptGraph) | ✅ 多级匹配+BFS | 无 | 🔴 孤儿 |
| `topic_tree_source` | ✅ | runtime/engine `_topic_tree_source = None` 从未赋值 | 🔴 死代码 |
| `temperature_patch` | ✅ patch 工具 | 无（无调用点）| 🔴 孤儿 |
| `CausalSource` | ✅ | 无 | 🔴 孤儿 |
| v3 `manager/store/window/models` | ✅ | service/v3_0（退役路径）| 🟡 服役中但面向旧架构 |

---

## 四、测试现状

```
core/agent/context/tests/test_context_manager.py   47 passed（仅 v3 会话管理）
core/agent/context_window/tests/test_window.py     12 passed（孤立模块自测）
```

- **v4 Context Engineering 全组件（assembler/source/IR/pruner/selector/allocator/graph_source）
  没有任何直接测试** —— 测试覆盖与代码规模严重倒挂。
- 无接线测试：没有任何测试验证 `on_event` 后 `_last_context` 非空 / prompt 包含 IR。
- `CONTEXT_GAP.md` 宣称的「4 项修复 + 95% 有效」无法被任何测试佐证 —— 实际为 **假状态报告**。

---

## 五、已实锤的关键矛盾

1. **`CONTEXT_GAP.md`（v5）说「Context 是当前最完整的链——所有 12 个组件全部接入」**
   vs 实测：主路径 0 接线，API 路径假接线，组件 80% 死代码/孤儿。
2. **`BUSINESS_CHAIN_02_CONTEXT.md` 说「有效实现率 ~80%」**
   vs 实测：DomainSelector ✅ / PerspectivePlanner ✅ / ContextAssembler ✅ 等 ✅ 均不成立。
3. **`engine.py` 的 `_compile_context` 幽灵调用**（同型于画像 `_feed_profile_runtime` 幽灵调用，
   但更彻底——连方法体都不存在，且不在任何 try/except 内；因 `_on_event_continue` 本身无调用点才没炸）。
4. **`p9_cmd.py`（CLI inspect 上下文命令）也查 `_compile_context`** → CLI `p9` 功能同断。
5. **DomainSelector 与 BudgetAllocator 域矩阵不一致**（已实测）：
   - `DomainSelector` QUERY: `C,K,E`（aux1=CAUSAL）
   - `BudgetAllocator` QUERY: `C,E,P`
   → 同一意图两套主域决策，`assemble_ir` 内部二者串联时预算与域选择互相打架。
6. **两套 IntentCategory 枚举**：`cross_domain_ir.IntentCategory` 与 `domain_selector.IntentCategory`
   各自定义（值相同但类型不同），`assemble_ir` 混用两套 —— 类型安全断裂。
7. **冷启动 12.5s 线索的真相**：`runtime/engine.py` 顶层 `from ...assembler import ContextAssembler`
   → 链式 import `numpy` / `SQLiteVectorStore` / `MilvusVectorStore` / `HybridIndex`。
   也就是说**死代码的 import 负担仍在支付**（引擎启动即加载全套向量基础设施），
   且装好的向量管线一次都没用上。

---

## 六、结论（第一轮）

上下文是**「实现最完整、接线最空洞」**的模块：
- 代码层：v3 会话管理 100% 可用（47 测试绿）；v4 管线算法 70-80% 完整（IR/pruner/graph_source 相当扎实）。
- 接线层：CLI 裸 prompt；API 假接线（5 处 API 错配）；v3 服务面向退役路径。
- 治理层：5 套并行实现未收敛；状态文档（CONTEXT_GAP / BUSINESS_CHAIN_02）与事实严重背离；
  v4 管线零测试。

下一步拍板点（待讨论）：
1. v4 管线要不要真正接入主路径？接哪里（CLI prompt 构造 / 状态机 CONTEXT phase / agent_native）？
2. 5 处 API 错配是修包装层（assembly）还是修 context/ 本身？
3. 两套 IntentCategory + 两套域矩阵是否归一？
4. 5 套并行实现收敛策略（context_manager/ 的 87KB discourse_manager 是否归档？）
5. `CONTEXT_GAP.md` / `BUSINESS_CHAIN_02` 状态文档是否立即修正（防止后续误导）？
