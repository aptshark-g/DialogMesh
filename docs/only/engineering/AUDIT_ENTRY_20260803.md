# 工程链（07）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/engineering/`（11 源码文件 + 4 测试文件）+ 全库接线
> 结论先行: **「工程链无接线」属实，且比审计线索更严重** —— 工程链 11 个文件中只有
> `models.py` + `knowledge_graph.py` 有真实生产消费（CLI 引擎挂载 + 子图 K 域），
> 其余 9 个文件（含 `EngineeringChain` 主类）在生产路径**从未被实例化**。

---

## 一、文件清单与生产消费矩阵

| 文件 | 生产消费者 | 状态 |
|---|---|:---:|
| `models.py` | subgraph_compiler（KnowledgeType/ArtifactType）| ✅ 唯一真实接线 |
| `knowledge_graph.py` | cli/engine.py:332 挂载 `_engineering_knowledge` → 子图 K 域 | ✅ 接线但功能残缺 |
| `chain.py` (EngineeringChain) | 无（仅 docstring 示例 + inspect_v3_cmd import 检查）| 🔴 从未实例化 |
| `constraint_engine.py` | 无（仅测试 + v3_2 shim）| 🔴 孤儿 |
| `registry.py` (ArtifactRegistry) | 无（仅测试）| 🔴 孤儿 |
| `type_system.py` (TypeRegistry) | 被 registry 使用 | 🟡 间接孤儿 |
| `monitor.py` (EngineeringMonitor) | 无（仅测试）| 🔴 孤儿 |
| `persistence.py` | 无（仅测试 + un_use 归档测试）| 🔴 孤儿 |
| `persistence_full.py` | 无 | 🔴 孤儿 + **与 persistence.py 逐字节重复** |
| `api_doc_preprocessor.py` | 无（仅 scripts/ 设计生成脚本引用）| 🔴 孤儿 |
| `__init__.py` | inspect_v3_cmd | 🟡 门面 |

**接线事实链（全库 `rg` 实证）：**
- `EngineeringChain(` 仅在 `chain.py:37` docstring 中出现 —— 生产零实例化。
- `MCPIntegrationHub.__init__(engineering_chain=None)`（mcp/integration.py:46）从未被传参，
  → `validate_against_constraints()` 恒返回 `{"allowed": True}` —— **工程约束校验是空操作**。
- `AgentOrchestrator(engineering_chain=None)`（orchestrator/agent_native.py）→ `bootstrap_v6.bootstrap()`
  → 调用方（chat_api/v6_app）从不传 → 第 6 步 Engineering 恒跳过。
- `CognitiveRuntimeEngine`（runtime/engine.py）**完全没有 import 工程链**。
- 意图模块 `multi_intent_splitter._engineering_chain()` 是显式 abstain stub：
  `"engineering: context not wired"`（与 v5 ENGINEERING_MULTI_INTENT_SPLIT §3.4「预留」一致）。
- CLI `inspect_v3_cmd.py:40-41` 只是 `import EngineeringChain; print("module is importable")` —— 假检查。

---

## 二、测试现状

```
core/agent/engineering/tests/  19 collected, 1 FAILED
  test_auto_persist.py        1F（v3_2 旧路径断裂，见 §四.1）
  test_edge_cases.py          6 passed
  test_engineering_chain.py   9 passed
  test_tier_manager.py        4 passed（测的是 persistence/GraphTierManager，非工程链）
```

- 测试全是**孤立类单元测试**（自建 registry/kg 实例），无一条验证生产接线。
- `test_tier_manager.py` 是放置错位的持久化层测试，不属于工程链。
- 无压测、无并发测试、无真实数据（无真实代码文件导入 → 约束推理从未用真实系统验证）。

---

## 三、生产路径实锤

### 3.1 唯一真实接线：子图 K 域
```
cli/engine.py:332  _engine._engineering_knowledge = KnowledgeGraph()   ← 7 条硬编码 preset
v4/cognitive/subgraph_compiler.py:188-193  K 域取 get_by_type(CONSTRAINT)[:3]
```
- 子图只取**前 3 条约束**、硬编码 50 tokens、无 confidence 计算、无 impact/pattern/decision。
- `_engineering_knowledge` 只由 CLI 引擎（`start_engine` A 路径）挂载；API 的 `_create_engine_instance`
  （B 路径）不挂 → **与子图审计发现的 A/B 双路径不一致同型**。

### 3.2 白盒面缺失
- `KnowledgeGraph.remove/get_node/search` 三个 CLI 方法按 **name** 匹配，但节点键是 UUID
  （`kn_xxxx`）→ **永远匹配不到**（已实测：`remove("Test Impact")=False`）。
- `TypeRegistry.add_custom_type` 是 `pass` 占位 → 白盒扩展（新节点类型）未实现。
- `DESIGN_ENGINEERING_ONTOLOGY §6` 的 `OntologyEditor`（边规则/生命周期/source 置信度/节点类型编辑）
  **完全不存在**。

---

## 四、缺陷清单（按严重度）

### P0 缺陷
1. **v3_2 旧路径断裂（同型 PCR/行为链问题）**
   `core/agent/v3_2/engineering_chain/` 只有 `__init__.py`（re-export KnowledgeGraph/ConstraintEngine），
   **缺 `models.py`** → 任何 `from core.agent.v3_2.engineering_chain.models import *` 直接 ModuleNotFoundError。
   证据：`test_auto_persist.py::test_knowledge_auto_saved` 实测失败。
   → v3_2 → engineering 的合并是**半合并**，旧路径未补 shim。

2. **`KnowledgeGraph.add()` 丢弃 impact 参数**
   `add(name, ktype, binds_to, template, impact=...)` → 调 `_add(name, ktype, binds_to, template, src=MANUAL)`
   **不传 impact** → 所有自定义 Quality 节点 impact 恒为 `{}`（已实测）。
   这直接废掉 `get_impact()` 的「质量影响评估」核心能力。

3. **`check_anti_patterns()` 逻辑残缺**
   只检查 `source_artifact.is_type(ap.binds_to_type)`，**不检查边类型**（`proposed_edge.etype`），
   也不读 `correct_path`。任何 Controller 发出的边都算违反，与设计「禁止连接」语义不符。

### P1 缺陷
4. **`persistence.py` 与 `persistence_full.py` 逐字节重复** —— 复制粘贴产物，应删一留一。
5. **`KnowledgeGraph.remove/get_node/search` 键名不匹配**（UUID 键 vs name 查询）—— 白盒 CLI 失效。
6. **`get_pattern_for(operation)` 空串兜底**：`compile_context()` 里硬编码 `get_pattern_for("")`
   → 恒返回 `patterns[0]`（Plugin Pattern），matched_patterns 恒等于第一条模式，无真实匹配。
7. **`get_related_decisions` 恒空**：preset 里没有 DECISION 节点，接口永远返回 `[]`。
8. **七类节点只实现 4 类**：preset 只有 CONSTRAINT×3 / PATTERN×2 / ANTIPATTERN×1 / QUALITY×1（占位）。
   RULE / DECISION / SKILL 枚举存在但**零节点**，Pattern 蒸馏、Skill 生成（v4.5+）未实现。
9. **`get_impact` 是占位实现**：只汇总 `impact` 字典，没有 `affected_modules` / `violated_constraints` /
   `suggested_patterns`（设计 §5 ③ 要求的三元输出）。
10. **`chain.py` 快照/可行性全是浅实现**：`check_feasibility` 是「前 5 个分词在工具描述里子串匹配」，
    `confidence = min(0.9, matches*0.3)` 硬编码，无权重、无语义、无规则参与。
11. **`EngineeringChain.snapshot()` 的 MCP 分支死代码**：`list_discovered_tools` 返回列表时，
    `state.mcp_servers = list(tool_names)` 存的是工具名，随后用工具名去查 adapter 必然 None
    → MCP 工具永远不会被枚举出来。

### P2 观察
12. `api_doc_preprocessor.py` 只有 1 个类 4 个解析器（openapi/swagger/markdown/json），
    对照 `ENGINEERING_API_DOC_PREPROCESSOR.md` 的 6 组件设计（APIDocParser/OpenAPI3Parser/
    SchemaExtractor/EndpointExtractor/DocNormalizer/ContextBuilder）是**大幅简化 + 孤儿**。
13. 无 `pattern_library.py`（设计 §7 规划过，未建）。
14. 无工程链监控接入生产（`EngineeringMonitor` 仅测试使用）。
15. **e2e 测试引用不存在的端点**：`tests/test_e2e.py::TestEngineeringChain` 打
    `/v6/engineering/modules` 与 `/v6/recursive-map`，但 `core/agent/api/v6_app.py` 中
    **这两个路由不存在**（全文件仅一处 `engineering` 布尔健康字段）→ e2e 测试必失败或悬空，
    属于「先射箭再画靶」的假测试。

---

## 五、与关联链/其他模块的协同现状

| 设计要求的协同 | 现状 |
|---|---|
| 关联链 `depends_on 查询` 工程链 | ❌ 不存在（关联链从不 import engineering）|
| 行为链操作类型 → 工程链模式 | ❌ 不存在 |
| 工程链约束 → 因果候选 | ❌ 不存在 |
| Context 编译器 E 域 `get_constraints_for` | 🟡 仅子图 K 域 3 条硬编码约束 |
| 用户修改 → 元认知 | ❌ 不存在（白盒面缺失）|
| MCP 工具 → 工程约束校验 | ❌ `MCPIntegrationHub._engineering` 恒 None |
| 意图工程链验证链 | 🟡 abstain stub（v5 §3.4 预留）|

---

## 六、结论（第一轮）

工程链是**「数据模型 + 单点挂载」状态**：
- 结构层（models/registry/kg/constraint_engine）约 40% 完成，但推理逻辑残缺（P0-2/3、P1-6/7/8/9）。
- 接入层（chain/MCP/agent_native/意图）**0% 接线**。
- 白盒/学习层（OntologyEditor/Pattern 蒸馏/操作记忆）**0% 实现**。
- 设计文档宣称的「可演化的工程知识库」实际是**内存里 7 条硬编码 preset**，无持久化、无学习、无蒸馏。

下一步拍板点（待讨论）：
1. 工程链定位是否收缩为「子图 K/E 域数据源 + MCP 约束校验」还是补全推理引擎？
2. v3_2 shim 补 `models.py` 还是直接删旧路径？
3. 是否把 `persistence_full.py` 删除（重复文件）？
4. 白盒 CLI（remove/get_node/search）是修键名还是重建为 ID 查询？
