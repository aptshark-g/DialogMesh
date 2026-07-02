# 规划设计文档对应工程文档检查 审查报告

## 1. 设计文档核心需求提取

### 1.1 DESIGN_TASK_PLANNING_DYNAMIC.md (v1.0, 1478行) 核心需求

| 编号 | 核心模块 | 关键设计决策 | 章节 |
|------|---------|-------------|------|
| D1 | `ToolRegistry` | 动态工具注册中心，支持运行时注册/注销/热更新，单例模式，EMA统计 | §3.1 |
| D2 | `APIDocPreprocessor` | 将OpenAPI/Swagger/JSON Schema转换为`ToolSchema`，支持5种格式 | §3.2 |
| D3 | `ToolShortlister` | 多级漏斗筛选（意图→语义→历史→容量），解决Tool Overflow，max_tools=32 | §3.3 |
| D4 | `DynamicPlanner` | LLM自主生成TaskGraph，多计划生成(3候选)，自我反思，成本估计 | §3.4 |
| D5 | `SchemaGuard` + `ToolExecutor` | 参数验证(JSON Schema) + 执行分发(LOCAL/HTTP/MCP) | §3.5 |
| D6 | 数据流 | IntentParser→ToolShortlister→DynamicPlanner→SchemaGuard→ToolExecutor→ParseResult | §4 |
| D7 | 向后兼容 | 保留静态Blueprint作为fallback，`_build_task_graph`动态优先 | §2.3, §4.3 |

### 1.2 DESIGN_PLANNING_SKILL_LAYER.md (v1.5, 1783行) 核心需求

| 编号 | 核心模块 | 关键设计决策 | 章节 |
|------|---------|-------------|------|
| P1 | 正交分层 | Planning层(How)与Tool层(What)解耦，中间Binding层 | §2 |
| P2 | 通用规划原语库 | **17个原语**（P1-P17），五维模型（分解/分配/排序/资源/反思） | §3 |
| P3 | `PlanningSkill` 数据模型 | `skill_id`, `domain_tags`, `intent_categories`, `primitives`, `step_templates`, `tool_hints`, `constraints`, `level` (SkillLevel), `match_intent()` | §4 |
| P4 | `MixedPlanningEngine` | 三种模式：DYNAMIC / SKILL_ENHANCED / MIXED，自动选择+回退链 | §5 |
| P5 | 三种模式详解 | DYNAMIC（纯LLM自主）、SKILL_ENHANCED（Skill引导+LLM调整）、MIXED（Skill严格骨架+LLM只填充） | §6 |
| P6 | `ToolBindingEngine` | 占位符→实际工具，精确匹配/标签匹配/语义匹配/参数兼容 | §7.1 |
| P7 | `EnhancedToolShortlister` | 在v1.0 ToolShortlister基础上增加Skill tool_hints排序boost | §7.2 |
| P8 | 认知画像联动 | 元认知/发散性/g因子/技术标签/领域标签影响模式选择和工具筛选 | §8 |
| P9 | 完整数据流 | IntentParser→MixedPlanningEngine→ToolBinding→Execution→ParseResult | §9 |
| P10 | 模式回退链 | MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK | §5.4 |

---

## 2. 各工程文档对应检查

### 2.1 PlanningSkillEngine vs MixedPlanningEngine (P4, P5)

- **设计文档需求**: `MixedPlanningEngine` 三种运行模式（DYNAMIC/SKILL_ENHANCED/MIXED），自动模式选择决策树，`_pure_dynamic_plan`/`_skill_enhanced_plan`/`_mixed_plan` 三个方法，回退链 `MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK` (`DESIGN_PLANNING_SKILL_LAYER.md` §5, §6, §5.4)
- **工程文档实现**: `PlanningSkillEngine` 有 `plan_and_execute` 方法，内含三种路径：快速路径（`use_template=True`）、混合路径（`skill`存在但分数不足）、慢速路径（完全动态分解）。`replan` 方法基于错误类型（`skill_mismatch`/`dependency_error`/`execution_error`）处理，但没有模式回退链 (`ENGINEERING_PLANNING_SKILL.md` §5)
- **状态**: ⚠️ 差异
- **差异说明**: 
  1. 工程文档未明确实现三种模式（DYNAMIC/SKILL_ENHANCED/MIXED）的枚举和切换逻辑；
  2. 缺少 `PlanResult`（含 `mode`, `skill_used`, `primitives_used`, `confidence`）数据结构；
  3. `replan` 不是设计文档定义的回退链，而是错误类型分类处理；
  4. 设计文档中 `MIXED` 模式要求 Skill 提供严格骨架、LLM 只填充工具名和参数，工程文档中未实现 `_mixed_plan` 的骨架完整性验证（`_skeleton_matches`）和 `fillable_zones` 逻辑。

---

### 2.2 通用规划原语库 (P2)

- **设计文档需求**: **17个通用规划原语**（P1-P17），定义为 `PlanningPrimitive` 基类，每个原语有 `generate_skeleton()` 方法输出标准 `TaskGraph`，`PrimitiveLibrary` 提供统一管理 (`DESIGN_PLANNING_SKILL_LAYER.md` §3, §3.4)
- **工程文档实现**: **完全缺失**。`ENGINEERING_PLANNING_SKILL.md` 全文中未提及任何 `PlanningPrimitive`、`PrimitiveLibrary` 或17个原语中的任何一个。
- **状态**: ❌ 缺失
- **差异说明**: 这是设计文档 v1.5 的核心创新点（"Planning ≠ Tools"的理论基础），工程文档完全遗漏。这导致工程文档中的 `DecompositionEngine` 只能做简单的LLM动态分解，没有基于认知科学原语的骨架生成能力。

---

### 2.3 PlanningSkill 数据模型 (P3)

- **设计文档需求**: `PlanningSkill` 含 `skill_id`, `domain_tags`, `intent_categories`, `primitives`, `step_templates`, `tool_hints`, `constraints`, `level` (SkillLevel: SKELETON/STANDARD/DETAILED), `match_intent()` 方法 (`DESIGN_PLANNING_SKILL_LAYER.md` §4.2)
- **工程文档实现**: `SkillTemplate` 含 `name`, `version`, `description`, `keywords`, `tags`, `decomposition_pattern`, `subtasks`, `dependencies`, `retry_policy`, `timeout_seconds`, `fallback_skill` (`ENGINEERING_PLANNING_SKILL.md` §6.2)
- **状态**: ⚠️ 差异
- **差异说明**:
  1. **字段缺失**：`skill_id`（全局唯一标识）、`domain_tags`（领域标签）、`intent_categories`（意图类别匹配）、`primitives`（使用的通用原语列表）、`tool_hints`（推荐工具标签）、`constraints`（领域约束，如前置条件/不变量）、`level`（SkillLevel 三级详细度）全部缺失；
  2. **方法缺失**：`match_intent()` 方法不存在，工程文档将匹配逻辑移到 `SkillMatcher` 中，但设计文档要求 Skill 自带匹配能力；
  3. **字段映射偏差**：设计文档的 `step_templates` 在工程文档中变为 `subtasks`，且 `SubtaskTemplate` 的字段与设计文档中 `TaskNode` 模板不完全一致；
  4. **SkillLevel 三级详细度缺失**：这是设计文档中控制LLM调整自由度的关键机制（DETAILED→MIXED模式，STANDARD→SKILL_ENHANCED模式），工程文档完全未实现。

---

### 2.4 ToolBindingEngine (P6)

- **设计文档需求**: `ToolBindingEngine` 将 Planning 层的占位符（如 `search_tool`）绑定到 Tool 层的实际工具（如 `github_api_search_repos`），支持精确匹配/标签匹配/语义匹配/参数兼容性检查，失败时回退到 `ask_user` (`DESIGN_PLANNING_SKILL_LAYER.md` §7.1)
- **工程文档实现**: **完全缺失**。`ENGINEERING_PLANNING_SKILL.md` 全文中未提及 `ToolBindingEngine` 或任何占位符绑定机制。
- **状态**: ❌ 缺失
- **差异说明**: 这是正交分层架构的核心组件——没有 Binding 层，Planning 层的输出无法与 Tool 层对接。工程文档中的 `PlanningSkillEngine` 直接将 `decompose_with_skill` 生成的任务送入 `DependencyResolver` 和 `ExecutionScheduler`，没有工具名绑定环节，导致 Planning 与 Tools 实际上仍耦合（与设计文档"正交分层"原则相悖）。

---

### 2.5 EnhancedToolShortlister (P7)

- **设计文档需求**: `EnhancedToolShortlister` 继承 `ToolShortlister`，增加 `skill` 参数，根据 `tool_hints` 提升相关工具排名 (`DESIGN_PLANNING_SKILL_LAYER.md` §7.2)
- **工程文档实现**: **完全缺失**。`ENGINEERING_PLANNING_SKILL.md` 全文中未提及 `ToolShortlister` 或 `EnhancedToolShortlister`。
- **状态**: ❌ 缺失
- **差异说明**: 设计文档中 `ToolShortlister` 是动态任务规划的核心组件（`DESIGN_TASK_PLANNING_DYNAMIC.md` §3.3），解决Tool Overflow问题。工程文档中既没有实现基础 `ToolShortlister`，也没有实现增强版。虽然 `ToolShortlister` 的工程实现可能在单独的 `ENGINEERING_TOOL_REGISTRY.md` 中，但本工程文档作为规划层的工程文档，未引用或集成该组件。

---

### 2.6 认知画像联动 (P8)

- **设计文档需求**: 元认知/发散性/g因子/技术标签/领域标签影响模式选择（`_select_mode_with_profile`）和工具筛选策略 (`DESIGN_PLANNING_SKILL_LAYER.md` §8)
- **工程文档实现**: **完全缺失**。`ENGINEERING_PLANNING_SKILL.md` 全文中未提及 `cognitive_profile`、画像维度、或任何 `_select_mode_with_profile` 逻辑。
- **状态**: ❌ 缺失
- **差异说明**: 设计文档中这是"与认知-画像v2.0的联动"核心章节，包含7个画像维度的具体映射和完整的 `_select_mode_with_profile` 代码示例。工程文档完全遗漏，导致规划层与认知画像系统脱节。

---

### 2.7 动态任务分解 (D4)

- **设计文档需求**: `DynamicPlanner` 有 `plan` 方法，Pipeline：构建提示词→生成多计划(3候选，temperature 0.2/0.5/0.8)→自我反思与筛选→解析为TaskGraph→验证。自我反思含4维度评分（工具存在性、参数完整性、DAG有效性、意图覆盖） (`DESIGN_TASK_PLANNING_DYNAMIC.md` §3.4)
- **工程文档实现**: `DecompositionEngine` 有 `decompose` 方法，含超时控制（默认1秒），超时回退到单任务直接执行。但**无多计划生成**、**无自我反思**、**无成本估计**、**无验证层** (`ENGINEERING_PLANNING_SKILL.md` §7)
- **状态**: ⚠️ 差异
- **差异说明**:
  1. 多计划生成（3候选）缺失；
  2. 自我反思（4维度评分）缺失；
  3. `_build_decomposition_prompt` 的提示词结构比设计文档的 `_build_planning_prompt` 简单很多，缺少规划约束（Max steps、Supported dependency types、fallback策略）和输出格式规范（nodes+edges结构）；
  4. 设计文档要求解析为 `TaskGraph`（nodes+edges），工程文档解析为 `List[Task]`（无显式边定义，依赖通过 `task.dependencies` 字符串列表表示）；
  5. 超时回退机制是工程文档新增内容，设计文档未明确提及，属于合理扩展。

---

### 2.8 SchemaGuard + ToolExecutor (D5)

- **设计文档需求**: `SchemaGuard` 验证工具名是否存在、必填参数是否齐全、参数类型是否符合JSON Schema、枚举值是否合法。`ToolExecutor` 根据 `ToolType` 分发到 LOCAL_FUNCTION/HTTP_API/MCP_REMOTE 三种后端 (`DESIGN_TASK_PLANNING_DYNAMIC.md` §3.5)
- **工程文档实现**: **完全缺失**。`ENGINEERING_PLANNING_SKILL.md` 中无 `SchemaGuard` 或 `ToolExecutor` 的任何实现。`ExecutionScheduler` 中的 `_execute_tool_task` 仅调用 `worker.execute()`，无Schema验证，无ToolType分发逻辑。
- **状态**: ❌ 缺失
- **差异说明**: 验证与执行层是动态任务规划安全性的核心保障。工程文档缺失此层，意味着LLM生成的工具调用参数不会经过JSON Schema验证，存在安全风险。

---

### 2.9 依赖解析器 (D6, P9)

- **设计文档需求**: `DependencyResolver` 构建DAG、检测循环、拓扑排序。`TaskGraph` 支持 `add_dependency(source.id, target.id, DependencyType, condition)` (`DESIGN_TASK_PLANNING_DYNAMIC.md` §4.1, §4.2)
- **工程文档实现**: `DependencyResolver` 实现了 `build_dag`（创建节点、添加边、检测循环、拓扑排序）和 `find_critical_path`（关键路径）。`TaskDAG` 支持 `add_node`, `add_edge`, `has_cycle`, `topological_sort`, `is_valid` (`ENGINEERING_PLANNING_SKILL.md` §9)
- **状态**: ✅ 一致
- **差异说明**: 工程文档实现了设计文档的核心需求，且增加了 `find_critical_path` 功能（增值）。但 `TaskDAG` 的 `add_edge` 方法不接收 `DependencyType` 和 `condition` 参数（设计文档中 `TaskGraph.add_dependency` 支持），导致条件分支和并行依赖的类型信息丢失。

---

### 2.10 执行调度器 (P5)

- **设计文档需求**: `ExecutionScheduler` 按拓扑排序执行，无依赖并行、有依赖串行，支持重试/超时/回退 (`DESIGN_PLANNING_SKILL_LAYER.md` §5)
- **工程文档实现**: `ExecutionScheduler` 实现了拓扑排序顺序执行、依赖检查、重试逻辑（指数退避）、LLM任务和工具任务分发 (`ENGINEERING_PLANNING_SKILL.md` §10)
- **状态**: ⚠️ 差异
- **差异说明**:
  1. 设计文档要求"无依赖关系的任务并行执行"，但工程文档 `ExecutionScheduler.execute` 是按拓扑排序**顺序遍历**执行的，没有并行执行逻辑（`asyncio.gather` 或 `asyncio.create_task`）；
  2. 重试策略中 `retry_policy` 的 `backoff_factor` 在 `Task` 数据模型中有定义，但 `ExecutionScheduler` 使用的是 `task.retry_policy.backoff_factor`，而 `Task` 的初始化中 `retry_policy` 是可选的，可能导致 `AttributeError`；
  3. 缺少设计文档中的超时控制（`timeout_seconds`）和全局执行超时监控。

---

### 2.11 技能匹配器 (P3)

- **设计文档需求**: `SkillMatcher` 通过 `SkillRegistry.match_intent(intent)` 获取匹配分数，或 `PlanningSkill.match_intent()` 计算分数（意图类别0.4 + 领域标签0.3 + 关键词0.3） (`DESIGN_PLANNING_SKILL_LAYER.md` §4.2, §5.2)
- **工程文档实现**: `SkillMatcher` 实现了 `_score_skill`（关键词0.4 + 语义相似度0.4 + 上下文相关性0.2），阈值策略：≥0.5用模板，<0.5调用LLM动态分解。`SkillRegistry` 接口为 `query()` 而非 `list_skills()` (`ENGINEERING_PLANNING_SKILL.md` §6)
- **状态**: ⚠️ 差异
- **差异说明**:
  1. 权重不一致：设计文档是 意图类别0.4/领域标签0.3/关键词0.3，工程文档是 关键词0.4/语义相似度0.4/上下文相关性0.2；
  2. 设计文档要求 Skill 自带 `match_intent()` 方法，工程文档将匹配逻辑集中到 `SkillMatcher`，失去了 Skill 的自描述匹配能力；
  3. `SkillRegistry` 接口不一致：设计文档要求 `list_skills()`/`get_skill()`/`match_skills()`/`register_skill()`，工程文档使用 `query()`（未明确接口定义）；
  4. 设计文档要求阈值 >0.5 保留，>0.8 触发 MIXED 模式，工程文档阈值0.5且无0.8高匹配度区分。

---

### 2.12 数据流与架构一致性 (P1, P9, D6)

- **设计文档需求**: 
  - 三层架构：Planning层 → Tool层 → Binding层 (`DESIGN_PLANNING_SKILL_LAYER.md` §2.1)
  - 完整数据流：IntentParser → MixedPlanningEngine → ToolBinding → Execution → ParseResult (`DESIGN_PLANNING_SKILL_LAYER.md` §9.1)
  - 动态规划数据流：IntentParser → ToolShortlister → DynamicPlanner → SchemaGuard → ToolExecutor → ParseResult (`DESIGN_TASK_PLANNING_DYNAMIC.md` §4.1)
- **工程文档实现**: 
  - 架构图显示：Planning-LLM/Orchestrator → Planning Skill Layer → Worker层 → Cognitive Compiler (`ENGINEERING_PLANNING_SKILL.md` §4)
  - 数据流：`plan_and_execute` 中：技能匹配 → 任务分解 → 依赖解析 → 智能体分配 → 执行调度 → 结果编译
- **状态**: ⚠️ 差异
- **差异说明**:
  1. 设计文档的 **ToolBinding 层** 在工程文档架构图中完全缺失；
  2. 设计文档的 **SchemaGuard** 和 **ToolExecutor** 在工程文档数据流中缺失；
  3. 工程文档的 `Cognitive Compiler` 结果编译步骤在设计文档数据流中未明确体现，属于工程文档的合理扩展；
  4. 设计文档中的 `ToolShortlister` 在工程文档中未出现，但工程文档的 `plan_and_execute` 中缺少工具筛选环节，直接调用 `decomposition`（可能假设工具已在外部筛选）。

---

### 2.13 SkillRegistry 与 PrimitiveLibrary (P2, P3)

- **设计文档需求**: `SkillRegistry` 管理 `PlanningSkill`，`PrimitiveLibrary` 管理17个 `PlanningPrimitive`，`MixedPlanningEngine` 依赖两者 (`DESIGN_PLANNING_SKILL_LAYER.md` §9.2)
- **工程文档实现**: 有 `SkillRegistry`（用于 `SkillMatcher`），但无 `PrimitiveLibrary` (`ENGINEERING_PLANNING_SKILL.md` §6)
- **状态**: ⚠️ 差异
- **差异说明**: `PrimitiveLibrary` 是通用规划原语库的管理接口，其缺失导致 `MixedPlanningEngine` 的 DYNAMIC 模式无法注入通用原语作为LLM规划参考（设计文档 §6.1 明确"将通用原语库注入LLM提示词"）。

---

## 3. 等价性检查章节验证

工程文档 §13.3 (`ENGINEERING_PLANNING_SKILL.md` 第1153-1162行) 提供了"设计文档等价性检查"表：

| 设计文档章节 | 工程文档声称覆盖 | 声称等价性 | **实际审查结果** |
|-------------|----------------|-----------|----------------|
| `DESIGN_PLANNING_SKILL_LAYER.md` §2 (核心概念：正交分层) | §6 (技能匹配器) | ✅ 等价 | ❌ **不等价** — §2是架构分层概念，§6是具体实现组件，且工程文档未实现Binding层，正交分层不完整 |
| `DESIGN_PLANNING_SKILL_LAYER.md` §4 (PlanningSkill定义与结构) | §8 (智能体分配器) | ✅ 等价 | ❌ **不等价** — §4是Skill数据模型，§8是Agent分配，且Skill数据模型大量字段缺失 |
| `DESIGN_PLANNING_SKILL_LAYER.md` §5 (Mixed Planning Engine) | §10 (执行调度器) | ✅ 等价 | ❌ **不等价** — §5是模式选择与三模式引擎，§10是执行调度，两者是完全不同的组件 |
| `DESIGN_TASK_PLANNING_DYNAMIC.md` §3 (核心模块详细设计) | §7 (任务分解引擎) | ✅ 等价 | ⚠️ **部分等价** — §3包含ToolRegistry/APIDocPreprocessor/ToolShortlister/DynamicPlanner/SchemaGuard，§7仅覆盖DynamicPlanner的部分功能（DecompositionEngine） |
| `DESIGN_TASK_PLANNING_DYNAMIC.md` §4 (数据流与接口定义) | §9 (依赖解析器) | ✅ 等价 | ❌ **不等价** — §4是端到端数据流，§9是单一组件（DependencyResolver） |
| `ENGINEERING_MULTILAYER_LLM.md` §5 (6个LLM实例) | §11 (6个LLM集成) | ✅ 等价 | ✅ **等价** — 此条正确 |

**结论**：工程文档的"等价性检查"章节存在**系统性错误**。6条中有5条将不对应的章节标记为"✅ 等价"，严重误导。唯一正确的是与 `ENGINEERING_MULTILAYER_LLM.md` 的对照。

---

## 4. 问题汇总

| 优先级 | 问题描述 | 涉及文档 | 建议修复 |
|--------|---------|---------|---------|
| **P0-阻塞** | 等价性检查章节系统性错误：将6个不对应关系标记为"✅ 等价" | `ENGINEERING_PLANNING_SKILL.md` §13.3 | 立即修正等价性检查表，删除或修正错误的5条对应关系，增加诚实标注 |
| **P0-阻塞** | **通用规划原语库完全缺失**（17个原语 + PrimitiveLibrary） | `ENGINEERING_PLANNING_SKILL.md` | 新增 §X 实现 `PlanningPrimitive` 基类、`PrimitiveLibrary` 和17个原语的 `generate_skeleton()`，或标记为 S-06 简化项 |
| **P0-阻塞** | **`ToolBindingEngine` 完全缺失** | `ENGINEERING_PLANNING_SKILL.md` | 新增 `ToolBindingEngine` 实现（占位符→实际工具绑定），或标记为 S-06 简化项。当前没有Binding层，Planning与Tool无法正交解耦 |
| **P0-阻塞** | **`SchemaGuard` + `ToolExecutor` 完全缺失** | `ENGINEERING_PLANNING_SKILL.md` | 新增 Schema验证层和Tool执行分发层，或标记为 S-07 简化项。缺少参数验证存在安全风险 |
| **P1-严重** | **`PlanningSkill` 数据模型大幅简化**：缺少 `skill_id`, `primitives`, `tool_hints`, `constraints`, `level`, `domain_tags`, `intent_categories` | `ENGINEERING_PLANNING_SKILL.md` §6.2 | 扩展 `SkillTemplate` 以匹配 `PlanningSkill` 数据模型，或明确说明哪些字段被简化并标记为简化项 |
| **P1-严重** | **`MixedPlanningEngine` 三模式不完整**：无DYNAMIC/SKILL_ENHANCED/MIXED枚举，无 `_pure_dynamic_plan`/`_skill_enhanced_plan`/`_mixed_plan` 方法，无骨架完整性验证 | `ENGINEERING_PLANNING_SKILL.md` §5 | 重构 `PlanningSkillEngine` 以实现三模式架构，或明确标记为简化项 |
| **P1-严重** | **模式回退链缺失**：`MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK` 未实现 | `ENGINEERING_PLANNING_SKILL.md` §5 | 在 `replan` 或 `plan_and_execute` 中实现回退链，或标记为简化项 |
| **P1-严重** | **`EnhancedToolShortlister` 完全缺失** | `ENGINEERING_PLANNING_SKILL.md` | 新增 `EnhancedToolShortlister` 或引用 `ENGINEERING_TOOL_REGISTRY.md` 中的实现，并说明 `tool_hints` boost 逻辑 |
| **P1-严重** | **认知画像联动完全缺失**：`_select_mode_with_profile` 未实现 | `ENGINEERING_PLANNING_SKILL.md` | 新增画像维度注入逻辑，或标记为 S-08 简化项（需明确说明与认知画像系统的集成缺失） |
| **P2-中等** | **`DynamicPlanner` 多计划生成和自我反思缺失**：3候选计划、4维度评分未实现 | `ENGINEERING_PLANNING_SKILL.md` §7 | 在 `DecompositionEngine` 中增加多计划生成和反思筛选，或标记为简化项 |
| **P2-中等** | **`SkillMatcher` 匹配权重与设计不一致**：设计文档意图类别0.4/领域标签0.3/关键词0.3，工程文档关键词0.4/语义0.4/上下文0.2 | `ENGINEERING_PLANNING_SKILL.md` §6.1 | 统一匹配权重策略，或说明为何调整并引用设计文档ADR |
| **P2-中等** | **`TaskDAG` 不支持依赖类型**：缺少 `DependencyType` 和 `condition` 参数 | `ENGINEERING_PLANNING_SKILL.md` §9.2 | 扩展 `add_edge` 以支持 `DependencyType`（SEQUENTIAL/CONDITIONAL/PARALLEL/FALLBACK）和条件表达式 |
| **P2-中等** | **`ExecutionScheduler` 不支持并行执行**：设计文档要求无依赖任务并行，工程文档是顺序遍历 | `ENGINEERING_PLANNING_SKILL.md` §10 | 使用 `asyncio.gather` 实现拓扑层级内的并行执行 |
| **P3-轻微** | `SkillRegistry` 接口不一致：设计文档要求 `list_skills`/`get_skill`/`match_skills`/`register_skill`，工程文档使用 `query()` | `ENGINEERING_PLANNING_SKILL.md` §6 | 统一接口命名，增加 `match_skills` 方法 |
| **P3-轻微** | `SkillTemplate` 名称与设计文档 `PlanningSkill` 不一致 | `ENGINEERING_PLANNING_SKILL.md` §6.2 | 统一命名为 `PlanningSkill` 以保持一致性，或明确说明 `SkillTemplate` 是 `PlanningSkill` 的工程简化版本 |
| **P3-轻微** | `DecompositionEngine` 使用 `asyncio.run()` 在线程池中调用，可能与设计文档意图冲突（设计文档未明确超时实现方式） | `ENGINEERING_PLANNING_SKILL.md` §7.1 | 在工程文档中说明超时策略是工程新增优化，而非设计文档简化 |

---

## 5. 简化项审查 (S-01 ~ S-05)

工程文档 §13.1 标记了5个简化项：

| 编号 | 设计文档要求 | 当前实现 | 审查意见 |
|------|-------------|---------|---------|
| S-01 | 动态技能学习 | 预定义技能模板 | ✅ 合理标记 |
| S-02 | 分布式调度 | 单进程 asyncio | ✅ 合理标记 |
| S-03 | 资源预测 | 使用 estimated_time | ✅ 合理标记 |
| S-04 | 任务迁移 | 不支持 | ✅ 合理标记 |
| S-05 | 执行监控面板 | 日志记录 | ✅ 合理标记 |

**应补充但未标记为简化项的设计文档内容**：

| 建议编号 | 设计文档要求 | 当前实现 | 建议操作 |
|----------|-------------|---------|---------|
| **S-06** | 通用规划原语库（17个）+ PrimitiveLibrary | 完全缺失 | 立即补充为简化项 |
| **S-07** | ToolBindingEngine（占位符绑定） | 完全缺失 | 立即补充为简化项 |
| **S-08** | SchemaGuard + ToolExecutor（验证+执行） | 完全缺失 | 立即补充为简化项 |
| **S-09** | EnhancedToolShortlister（Skill tool_hints boost） | 完全缺失 | 立即补充为简化项 |
| **S-10** | 认知画像联动（`_select_mode_with_profile`） | 完全缺失 | 立即补充为简化项 |
| **S-11** | DynamicPlanner 多计划生成（3候选）+ 自我反思 | 完全缺失 | 立即补充为简化项 |
| **S-12** | PlanningSkill 三级详细度（SkillLevel: SKELETON/STANDARD/DETAILED） | 完全缺失 | 立即补充为简化项 |
| **S-13** | 模式回退链（MIXED→SKILL_ENHANCED→DYNAMIC→FALLBACK） | 部分缺失 | 立即补充为简化项 |

---

## 6. 审查结论

### 总体评估

`ENGINEERING_PLANNING_SKILL.md` 对两份设计文档（`DESIGN_TASK_PLANNING_DYNAMIC.md` + `DESIGN_PLANNING_SKILL_LAYER.md`）的实现**不完整**，存在大量核心功能缺失或简化，且等价性检查章节存在**系统性误导**。

### 设计文档覆盖率估算

| 设计文档 | 核心章节数 | 完全实现 | 部分实现 | 完全缺失 | 覆盖率 |
|---------|-----------|---------|---------|---------|--------|
| `DESIGN_TASK_PLANNING_DYNAMIC.md` | 7 | 1 (D6数据流部分) | 3 (D1, D3, D4) | 3 (D2, D3完全缺失, D5) | ~45% |
| `DESIGN_PLANNING_SKILL_LAYER.md` | 10 | 1 (P9数据流部分) | 2 (P3, P4) | 7 (P2, P6, P7, P8, P10等) | ~35% |

### 关键风险点

1. **架构完整性风险**：缺少 `ToolBindingEngine`，导致"Planning与Tools正交分层"的设计原则无法落实，Planning层与Tool层仍然耦合；
2. **安全性风险**：缺少 `SchemaGuard`，LLM生成的工具调用参数不经过JSON Schema验证，可能导致错误调用或注入攻击；
3. **质量风险**：缺少 `DynamicPlanner` 的多计划生成和自我反思，规划质量可能不稳定；缺少 `EnhancedToolShortlister`，工具筛选不考虑Skill hints，可能导致工具选择不当；
4. **可扩展性风险**：缺少 `PlanningPrimitive` 和 `PrimitiveLibrary`，系统无法沉淀通用规划知识，新增领域只能依赖纯LLM推理，难以达到设计文档预期的"通用规划逻辑沉淀"目标。

### 建议修复优先级

1. **立即修复**：修正等价性检查章节（§13.3），删除错误标记；
2. **P0（本周）**：补充 S-06 ~ S-13 简化项标记，诚实标注缺失内容；
3. **P1（2周内）**：实现 `ToolBindingEngine`（至少占位符匹配）和 `SchemaGuard`（至少必填参数检查）；
4. **P2（1个月内）**：扩展 `SkillTemplate` 以支持 `primitives`/`tool_hints`/`constraints`/`level`，实现 `MixedPlanningEngine` 三模式；
5. **P3（后续版本）**：实现通用规划原语库和认知画像联动。

---

*审查完成时间：基于文档内容分析*
*审查员：DialogMesh 工程文档审查员*
*涉及文件：DESIGN_TASK_PLANNING_DYNAMIC.md, DESIGN_PLANNING_SKILL_LAYER.md, ENGINEERING_PLANNING_SKILL.md*
