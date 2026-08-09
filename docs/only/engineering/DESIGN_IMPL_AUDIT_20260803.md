# 工程链设计 vs 实现 — 第二轮深度对照

> 日期: 2026-08-03 | 方法: 逐设计文档精读 + 逐文件对照 + 运行时实测
> 配套: `AUDIT_ENTRY_20260803.md`（第一轮代码盘点）

---

## 一、设计文档清单与映射

| 设计文档 | 定位 | 对应实现 | 总体符合度 |
|---|---|---|:---:|
| `docs/BUSINESS_CHAIN_07_ENGINEERING.md` | v6 链规范（递归地图/七类节点/白盒）| engineering/* | ~15% |
| `docs/v3.0/DESIGN_ENGINEERING_CHAIN.md` | 工程链 RFC（约束推理）| models/registry/kg/constraint_engine | ~35% |
| `docs/v3.0/DESIGN_ENGINEERING_ONTOLOGY.md` | 本体层（类型/来源/生命周期/边规则/白盒）| models.py + type_system.py | ~25% |
| `docs/v3.0/ENGINEERING_API_DOC_PREPROCESSOR.md` | API 文档预处理（6 组件）| api_doc_preprocessor.py | ~30% |
| `docs/v3.0/ENGINEERING_INTEGRATION.md` | v3 全系统整合（15 组件）| 已被 v4/v6 取代，工程链部分未接 | ~0%（工程链侧）|
| `docs/v5/ENGINEERING_MULTI_INTENT_SPLIT.md` §3.4 | 意图工程链验证（预留）| multi_intent_splitter abstain stub | 100%（预留=未做）|

---

## 二、BUSINESS_CHAIN_07（v6 链规范）vs 实现

### 2.1 递归地图模型 — ❌ 0% 实现
- 设计: 文件 → DocumentTree（tree-sitter 解析）→ Module/Rule/Pattern 节点 → 约束推理，多颗粒度展开/折叠。
- 实现: **无 tree-sitter、无文件解析、无颗粒度层级**。`ARTIFACT_TREE` 只是 14 个类型的静态 is_a 树，
  不是「同一结构的多尺度表示」。

### 2.2 七类节点 — 只实现 4 类
| 节点 | 设计 | 实现 |
|---|---|---|
| Module | 事实性，注册/卸载 | ✅ Artifact + ArtifactRegistry（有）|
| Constraint | 强制性，evidence 列表 | ✅ KnowledgeType.CONSTRAINT（3 条 preset）|
| Rule | 顺序性（谁在谁前面）| ❌ 枚举有，零节点 |
| Pattern | template 结构，可蒸馏 | ✅ 2 条 preset，无蒸馏 |
| AntiPattern | 禁止边，correct_path | 🟡 1 条 preset，无 correct_path 字段 |
| Decision | 追溯性，tradeoff+benefit | ❌ 零节点（`get_related_decisions` 恒空）|
| QualityAttribute | 量化 impact | 🟡 1 条占位（impact 全 0）+ `add()` 丢 impact（P0 bug）|
| Skill | 从 Pattern 蒸馏 | ❌ 枚举有，零节点 |

### 2.3 边类型 + 权限矩阵 — 🟡 半实现
- `EdgeType` 16 种枚举齐全，但 **`check_anti_patterns()` 不看边类型**（P0），
  `ArtifactEdge`/`KnowledgeEdge` 存在但**没有任何生产代码建边**（graph 从不生长）。
- 权限矩阵（Module→Constraint: requires 等）**无实现** —— 没有边合法性校验代码。

### 2.4 约束推理引擎 — 🟡 接口齐、逻辑残
| 设计接口 | 实现 | 评价 |
|---|---|---|
| `get_constraints_for(module_type)` | ✅ is_a 匹配 | 可用 |
| `get_pattern_for(operation)` | 🟡 子串匹配 + 空串兜底恒返回 patterns[0] | 假匹配 |
| `get_impact_of_change(module)` | ❌ 只有占位 `get_impact`（无 affected_modules/建议）| 未实现 |
| `check_violations(module, connection)` | 🟡 只按类型判，不看边 | 半实现 |
| `get_related_decisions(module)` | ❌ 恒空 | 未实现 |

### 2.5 白盒化 — ❌ 0% 实现
- `OntologyEditor`（add_edge_rule / add_lifecycle_state / add_node_type / set_source_confidence）**不存在**。
- `TypeRegistry.add_custom_type()` 是 `pass`。
- 白盒 CLI（`kg remove/get_node/search`）键名不匹配（UUID vs name），实测全失效。
- 「修改 → Event Log → 学习管线」**不存在**。

### 2.6 跨链交互 — ❌ 除子图 K 域外全部缺失
（详见第一轮 §五 —— 关联链/行为链/因果链/元认知/MCP 全部未接。）

---

## 三、DESIGN_ENGINEERING_CHAIN（RFC）vs 实现

### 3.1 已实现（核心骨架）
- `models.py`: ArtifactType/KnowledgeType/EdgeType/Lifecycle/Source/Artifact/KnowledgeNode —— 与 RFC §2 对齐（但 Decision/Quality 字段简化，无 tradeoff/benefit/impact_score 独立结构）。
- `registry.py`: ArtifactRegistry 注册/卸载/按类型查询 ✅。
- `knowledge_graph.py`: 约束/模式/反模式存储 + 类型绑定 ✅（7 preset）。
- `constraint_engine.py`: 约束查询/模式查询/反模式检查 ✅（浅实现）。

### 3.2 未实现（RFC 明确要求）
- `pattern_library.py`（RFC §5 规划文件）**未建**。
- Pattern 蒸馏演化（重复实例 → Candidate → Verified）**未实现**。
- Decision 记录（不可自动生成，manual 输入）**零节点**。
- QualityAttribute 影响量化（impact_score）**占位**。
- 与 ContextCompiler E 域对接：仅子图 K 域取 3 条约束，无 E 域模块状态快照。

### 3.3 RFC 推理示例逐条核验
RFC §4 的推理链示例（加 RateLimiter）要求同时输出: 约束 + Pattern 模板 + Rule 位置 + AntiPattern 警示 + 质量影响。
实测 `compile_context()` 输出: applicable_constraints（最多）+ **恒为 Plugin Pattern 的假匹配** +
**空 violated_anti_patterns**（compile_context 硬编码空列表，不走 check_anti_patterns！）+
**空 relevant_decisions**。→ 五要素只交付 1.5 个。

---

## 四、DESIGN_ENGINEERING_ONTOLOGY（本体层）vs 实现

| 设计项 | 实现 | 符合度 |
|---|---|:---:|
| 来源分类 source + 置信度 | ✅ `Source` + `source_confidence()` | 100% |
| 生命周期 | ✅ `Lifecycle` 枚举 | 100%（但无状态机流转代码）|
| 类型树 + is_a | ✅ `ARTIFACT_TREE` + `is_a()` | 100% |
| 类型推断三层 fallback | 🟡 只有名字推断，无结构/LLM 推断 | 30% |
| 约束绑定到类型 | ✅ `binds_to_type` | 100% |
| 边规则权限矩阵 | ❌ 无 | 0% |
| OntologyEditor 白盒 | ❌ 无 | 0% |
| 操作记忆与学习闭环 | ❌ 无 | 0% |
| 与 Belief Update 统一 | ❌ 无 | 0% |
| 三层架构（Artifact Graph/Knowledge Graph/Reasoning Engine）| 🟡 models 分两层，Reasoning Engine 只有接口 | 40% |

---

## 五、ENGINEERING_API_DOC_PREPROCESSOR vs 实现

| 设计组件 | 实现 | 评价 |
|---|---|---|
| `APIDocParser`（openapi3/swagger2/graphql/markdown + URL 下载 + auto detect + parse_safe）| 🟡 单类 4 解析器（openapi/swagger/markdown/json），无 URL 下载、无 parse_safe、无 GraphQL | 40% |
| `OpenAPI3Parser` | 🟡 简单 paths→tools 转换，无 components/schema 引用解析 | 40% |
| `SchemaExtractor` | ❌ 并入 `_openapi_params_to_schema`（简化版）| 20% |
| `EndpointExtractor` | ❌ 无独立组件（markdown 正则内联）| 20% |
| `DocNormalizer` | ❌ 无 | 0% |
| `ContextBuilder` | ❌ 无（输出直接是 tool 定义 dict，不是 ParsedAPIDoc）| 0% |
| 与 ToolDiscovery 集成 | ❌ 无（模块本身孤儿）| 0% |

**核心问题**: 该模块产出 ToolSchema 兼容 dict，但 ToolRegistry（engineering_bridges.py）从未消费它；
它挂在 `engineering/` 包下但与其 10 个兄弟文件零交互。

---

## 六、ENGINEERING_INTEGRATION（v3 全系统）vs 现状

- 该文档描述 v3.0 的 15 组件 + 6 LLM 实例 + 6 阶段启动 —— **已被 v4/v6（CognitiveRuntimeEngine +
  StateMachine + agent_native）取代**，作为「历史架构快照」保留。
- 其中工程链相关内容（ToolRegistry 注册 / MCP 集成 / 约束校验）在 v6 中：
  - MCP 集成 `MCPIntegrationHub` 存在但 `engineering_chain` 恒 None → 校验空转；
  - ToolRegistryBridge 存在但未接工程约束；
  - **结论：v3 整合文档的工程链部分，v6 时代既没迁移也没删除，静默失效。**

---

## 七、第二轮结论（设计 vs 实现）

1. **实现是「枚举齐全、逻辑空转」**：模型层（枚举/数据类）对齐度 80%+，推理层（约束引擎/白盒/学习）
   对齐度 <30%，接入层 0%。
2. **多处「接口存在但语义空洞」**：`get_pattern_for("")` 兜底、`compile_context` 硬编码空
   anti_patterns、`add()` 丢 impact、UUID 键 vs name 查询 —— 不是缺代码，是**写出来就是错的**。
3. **v3 → v6 的工程链迁移没有完成**：v3_2 shim 缺 models.py（旧路径直接炸），
   v6 各消费者（agent_native/MCP/意图）要么传 None 要么 abstain。
4. **设计愿景（可演化工程知识库）与实现（7 条硬编码 preset）之间是「代差」**，
   不是增量差距 —— 现有代码无法通过小修逼近设计，需要结构性重写或明确定位收缩。
