# 全概念设计文档对应工程文档检查 审查报告

## 1. 设计文档核心需求提取

基于 `DESIGN_FULL_CONCEPT.md`，提取以下核心设计决策：

| 编号 | 设计决策 | 所在章节 | 关键内容 |
|------|---------|---------|---------|
| D-01 | 6个核心数据契约 | §1.3 | UserInput, PCROutput, Intent, TaskGraph, DialogueState, CognitiveProfileV2, MemorySnapshot |
| D-02 | PCR层 | §2 | 噪声检测(3维)、期望推断(贝叶斯)、认知快照(4维→5维)、执行模式、数据契约 |
| D-03 | Intent Parser八阶段流水线 | §3 | 预处理→参照消解→实体提取→意图分类→多意图拆分→歧义检测(6种)→歧义消解→上下文合并→任务图构建 |
| D-04 | Fast Path快速路径 | §3.4 | 双阈值触发，跳过歧义阶段 |
| D-05 | Planning Skill Layer | §4 | 17个通用原语、3模式混合编排引擎、动态工具规划、工具绑定、Schema Guard |
| D-06 | 对话状态层 | §5 | Topic Tree(EMA/切换检测)、Context Window(4层/自适应)、对话状态机(7状态) |
| D-07 | 服务接口层 | §6 | Session管理(生命周期/持久化)、响应编排(4种格式)、协议层(WebSocket/REST) |
| D-08 | 认知画像v2.0 | §7 | Track A(5维)、Track B(4级侵入度)、g因子、双轨融合 |
| D-09 | 记忆系统 | §8 | 记忆组块、加权指数衰减、阶梯跃迁、二级摘要 |
| D-10 | 可观测性 | §9 | 4层模型：Diagnostics/Attribution/Telemetry/Tracing |
| D-11 | 完整数据流与生命周期 | §10 | 单次轮次数据流 + 长期Session生命周期 |

---

## 2. 各工程文档对应检查

### 2.1 ENGINEERING_PCR.md (PCR层)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §2 (Layer 0: PCR)
  - 噪声检测器(3维：语义/结构/参照)
  - 期望推断器(多特征贝叶斯分类 + 动态先验)
  - 认知快照快速评估(4/5维)
  - PCROutput数据契约(含execution_mode枚举)
  - 回退策略、生命周期、插件、遥测
- **工程文档实现**: 
  - 已实现RuleBasedPCR + 认知双工(HybridEngine ∥ PCR-LLM + FusionEngine)
  - 噪声估计器扩展为6维 + 3D Context Break Detection
  - 认知画像器EMA 5维更新
  - 数据契约v3.0定义(PCROutput_v3/PCRInput_v3/CognitiveProfile_v3)
  - 但文档声明"现有代码使用字符串"，v3.0为规划升级
- **状态**: ⚠️ 差异
- **差异说明**: 
  - §14.1 S-04标记"认知画像v2.0双轨"为简化，但 `ENGINEERING_DATA_MODEL.md` §9.1声称已完全覆盖CognitiveProfileV2。两者声明不一致。
  - §14.1 S-01标记数据契约v3.0为简化(现有代码使用字符串)，但 `ENGINEERING_DATA_MODEL.md` §4.1明确使用ExecutionMode/UserExpectation枚举。这是跨文档不一致。
  - 设计文档§2.2.1噪声公式为3维加权，工程文档实现为6维，虽覆盖设计需求但扩展超出设计范围。

### 2.2 ENGINEERING_INTENT_PARSER.md (意图解析层)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §3 (Layer 1: Intent Parser)
  - 八阶段流水线
  - 6种歧义类型检测(MISSING_ENTITY, AMBIGUOUS_ENTITY, CONFLICTING_ENTITIES, VAGUE_SCOPE, UNSUPPORTED_OPERATION, MULTIPLE_INTENTS)
  - 上下文合并(实体缓存更新、话题继承、进程上下文继承)
  - 多意图拆分(复杂度限制：高>0.8最多10个，低<0.5最多3个)
  - Fast Path、自适应阈值
- **工程文档实现**:
  - 八阶段流水线完整实现(含认知双工Intent-LLM)
  - 歧义检测仅明确列出5种，缺少`CONFLICTING_ENTITIES`
  - 上下文合并§5.8未提及"实体缓存更新"(设计文档§3.3.7要求将高置信度实体≥0.8写入跨轮实体缓存)
  - 多意图拆分§5.5仅提到"受max_sub_intents限制"，未映射设计文档的复杂度分级限制(高>0.8→10个, 低<0.5→3个)
  - Fast Path和自适应阈值完整实现
- **状态**: ⚠️ 差异
- **差异说明**: 
  - 缺少`CONFLICTING_ENTITIES`歧义检测类型(设计文档§3.3.6表格第3行)
  - 上下文合并未实现实体缓存更新机制
  - 多意图拆分的复杂度分级映射缺失
  - §11.1 S-03和S-04完全重复(都是"多模态实体提取")，属于文档内部错误

### 2.3 ENGINEERING_DATA_MODEL.md (数据模型)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §1.3, §5.2, §5.3, §7.2, §8.2, §9.2
  - 6个核心数据契约
  - TopicTree/ContextWindow/DialogueState
  - CognitiveProfileV2(Track A+Track B)
  - MemoryChunk
  - Telemetry/Tracing
- **工程文档实现**:
  - 6个核心数据契约全部定义(§4-§11)
  - 但**缺少`MemorySnapshot`数据契约**(设计文档§1.3定义包含chunks, weights, stage_transitions)
  - DialogueState完整(含7状态DialogueStatus枚举)
  - ContextWindow 4层模型完整(Hot/Warm/Cool/Cold)
  - CognitiveProfileV2完整(TrackA/TrackB/GFactor/TemporalState)
  - MemoryChunk和MemoryDecayManager完整
- **状态**: ⚠️ 差异
- **差异说明**:
  - 缺少`MemorySnapshot`数据契约模型
  - 等价性检查§16.3声称"6个核心数据契约全部覆盖"，但实际只覆盖了5个(缺MemorySnapshot)
  - 等价性检查声称全部✅，但§16.1存在S-01至S-05简化项，未在等价性检查中反映

### 2.4 ENGINEERING_PERSISTENCE.md (分层存储)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §8 (记忆系统)
  - 三层存储(Hot/Warm/Cold)
  - 五层记忆映射(Hot→Warm→Cool→Cold→Frozen)
  - 记忆衰减(加权单指数 + 阶梯跃迁 + 双指数可选)
  - 图存储、实体索引、版本迁移
- **工程文档实现**:
  - 三层存储架构完整(TieredStorageManager)
  - 五层记忆映射完整(MemoryStorage适配器)
  - 图存储和实体索引已有
  - 版本迁移工具(SchemaMigration)新增
  - 双指数衰减标记为S-03简化(仅单指数)
- **状态**: ⚠️ 差异
- **差异说明**:
  - 设计文档§7.2.3和§8.3.1将双指数衰减标记为"可选增强"，但工程文档仍标记为S-03简化项，属于合理的诚实标记。
  - Redis后端(S-01)和PostgreSQL后端(S-02)标记为简化，符合初期部署策略。

### 2.5 ENGINEERING_TOOL_REGISTRY.md (动态工具注册)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §4.6, §4.7, §4.8
  - ToolRegistry(注册/注销/Schema变更检测)
  - ToolShortlister(5阶段漏斗筛选)
  - ToolBindingEngine(4策略绑定)
  - Schema Guard + Executor
- **工程文档实现**:
  - ToolRegistry实现(注册/注销/查询/LLM Schema生成)
  - ToolDefinition实现(但缺少source/tool_type/estimated_latency_ms/estimated_cost_tokens/执行统计)
  - ToolExecutor实现(安全执行/超时/权限)
  - PermissionManager实现(6个LLM实例权限矩阵)
  - **缺少ToolShortlister**
  - **缺少ToolBindingEngine**
  - 工具发现(ToolDiscovery)和MCP适配器预留
- **状态**: ❌ 缺失
- **差异说明**:
  - **ToolShortlister**(设计文档§4.6.2)完全缺失——这是解决Tool Overflow的核心组件
  - **ToolBindingEngine**(设计文档§4.7)完全缺失——将占位符绑定到实际工具的关键层
  - ToolDefinition字段与设计文档§4.6.1的ToolSchema不完全对齐：缺少source(BUILTIN/API_DOC/MCP/CUSTOM)、tool_type(LOCAL_FUNCTION/HTTP_API/MCP_REMOTE)、estimated_latency_ms、estimated_cost_tokens、执行统计
  - 等价性检查§12.3声称"全部覆盖"，但上述关键组件缺失，**等价性检查不准确**

### 2.6 ENGINEERING_API_DOC_PREPROCESSOR.md (API文档预处理)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §4.6.1 (API文档工具注册来源)
  - OpenAPI/Swagger/GraphQL/Markdown解析
  - Schema提取、端点提取、标准化、上下文构建
- **工程文档实现**:
  - APIDocParser支持OpenAPI3/Swagger2/GraphQL/Markdown(容错设计)
  - SchemaExtractor(含嵌套简化)
  - EndpointExtractor(可转换为ToolDefinition)
  - DocNormalizer和ContextBuilder(含Token截断)
  - 与ToolRegistry和ContextManager集成
- **状态**: ✅ 一致
- **差异说明**: 
  - 设计文档要求通过APIDocPreprocessor解析后注册工具，工程文档§10.2明确实现了`auto_register_from_openapi`函数，对齐良好。
  - 诚实标记S-01至S-05(GraphQL/缓存/增量/认证/示例生成)合理。

### 2.7 ENGINEERING_SERVICE_LAYER.md (服务层)
- **设计文档需求**: `DESIGN_FULL_CONCEPT.md` §6 (Layer 3: 服务接口层)
  - WebSocket实时双向通信 + 流式响应
  - REST API端点(/chat, /parse, /execute, /session)
  - Session管理(生命周期: Create→Active→Archive→Delete, Redis/PostgreSQL/S3持久化)
  - 响应编排器(4种格式: BRIEF/BALANCED/EXPLANATORY/TUTORIAL)
  - 协议层(前端协议、心跳、重连)
- **工程文档实现**:
  - WebSocket服务端实现(含异步后台处理、5秒SLA降级、30秒硬超时)
  - HTTP REST API部分实现：提供 `/health`, `/sessions/{id}`, `/sessions/{id}/messages`, `/sessions/{id}/reset`, `/metrics`, `/skills`, `/tools`
  - **缺少端点**: `/chat`, `/parse`, `/execute`
  - ConnectionManager(连接生命周期/心跳/断线检测)
  - MessageRouter(请求→Orchestrator路由)
  - AuthMiddleware(简单API Key，JWT为S-01简化)
  - 但**无响应编排器实现**：SystemResponse只有`text/tool_call/status_update/error`，没有BRIEF/BALANCED/EXPLANATORY/TUTORIAL格式
  - Session管理不完整：无完整的生命周期状态机(ACTIVE/IDLE/CLOSED/ARCHIVED在数据模型中有，但服务层未实现状态转换)
  - 无持久化策略实现(Redis/PostgreSQL/S3)
- **状态**: ❌ 缺失
- **差异说明**:
  - **缺失REST端点**: 设计文档§6.4要求`/chat`, `/parse`, `/execute`, `/session`，工程文档仅实现部分管理端点，缺少核心交互端点
  - **缺失响应编排器**: 设计文档§6.3要求4种响应格式(BRIEF/BALANCED/EXPLANATORY/TUTORIAL)基于认知画像动态选择，工程文档完全未实现
  - **Session管理不完整**: 设计文档§6.2要求完整的生命周期和持久化策略，工程文档仅实现内存连接管理，无Redis/PostgreSQL/S3分层持久化
  - 等价性检查§12.3声称"全部覆盖"，但上述关键功能缺失，**等价性检查不准确**

---

## 3. 等价性检查章节验证

### 3.1 各工程文档等价性检查章节存在性

| 工程文档 | 等价性检查章节 | 状态 |
|---------|--------------|------|
| ENGINEERING_PCR.md | §14.3 | ✅ 存在 |
| ENGINEERING_INTENT_PARSER.md | §11.3 | ✅ 存在 |
| ENGINEERING_DATA_MODEL.md | §16.3 | ✅ 存在 |
| ENGINEERING_PERSISTENCE.md | §16.3 | ✅ 存在 |
| ENGINEERING_TOOL_REGISTRY.md | §12.3 | ✅ 存在 |
| ENGINEERING_API_DOC_PREPROCESSOR.md | §12.3 | ✅ 存在 |
| ENGINEERING_SERVICE_LAYER.md | §12.3 | ✅ 存在 |

### 3.2 等价性检查准确性问题

| 工程文档 | 问题描述 | 严重程度 |
|---------|---------|---------|
| ENGINEERING_PCR.md §14.3 | 声称§2.4数据契约⚠️简化，但DATA_MODEL.md声称完全覆盖 | 中 |
| ENGINEERING_INTENT_PARSER.md §11.3 | 声称§3.3.2(意图分类)⚠️简化(S-05)，但对应设计文档§3.3.4(非§3.3.2) | 低 |
| ENGINEERING_DATA_MODEL.md §16.3 | 声称"6个核心数据契约全部覆盖"，但缺少MemorySnapshot | **高** |
| ENGINEERING_TOOL_REGISTRY.md §12.3 | 声称"全部覆盖"，但缺ToolShortlister/ToolBindingEngine | **高** |
| ENGINEERING_SERVICE_LAYER.md §12.3 | 声称"全部覆盖"，但缺响应编排/核心REST端点/Session持久化 | **高** |

---

## 4. 问题汇总

| 优先级 | 问题描述 | 涉及文档 | 建议修复 |
|--------|---------|---------|---------|
| P0 | **TOOL_REGISTRY.md 等价性检查不准确**：声称全部覆盖，但缺少ToolShortlister和ToolBindingEngine两个核心组件 | ENGINEERING_TOOL_REGISTRY.md §12.3 | 修正等价性检查表，将§4.6.2和§4.7标记为❌缺失；补充ToolShortlister和ToolBindingEngine的工程规范 |
| P0 | **SERVICE_LAYER.md 等价性检查不准确**：声称全部覆盖，但缺少响应编排器和核心REST端点 | ENGINEERING_SERVICE_LAYER.md §12.3 | 修正等价性检查表，将§6.3响应编排和§6.4协议层标记为❌缺失；补充响应编排器实现规范 |
| P0 | **DATA_MODEL.md 等价性检查不准确**：声称6个核心数据契约全部覆盖，但缺少MemorySnapshot | ENGINEERING_DATA_MODEL.md §16.3 | 修正等价性检查表，补充MemorySnapshot数据契约；或明确声明其为简化项 |
| P1 | **缺少CONFLICTING_ENTITIES歧义检测**：设计文档§3.3.6定义6种歧义类型，工程文档仅实现5种 | ENGINEERING_INTENT_PARSER.md §5.6 | 补充CONFLICTING_ENTITIES检测逻辑，或标记为简化项并说明原因 |
| P1 | **缺少上下文合并的实体缓存更新**：设计文档§3.3.7要求将高置信度实体写入跨轮缓存 | ENGINEERING_INTENT_PARSER.md §5.8 | 补充实体缓存更新机制，ParseContext已有`_entity_cache`字段但未在Context Merger中更新 |
| P1 | **多意图拆分复杂度分级映射缺失**：设计文档要求高复杂度>0.8最多10个、低<0.5最多3个 | ENGINEERING_INTENT_PARSER.md §5.5 | 明确将complexity_level映射到max_sub_intents |
| P1 | **REST端点缺失**：设计文档§6.4要求`/chat`, `/parse`, `/execute`，工程文档未实现 | ENGINEERING_SERVICE_LAYER.md §6.2 | 补充核心REST端点实现，或标记为简化项 |
| P1 | **响应编排器缺失**：设计文档§6.3要求4种响应格式(BRIEF/BALANCED/EXPLANATORY/TUTORIAL) | ENGINEERING_SERVICE_LAYER.md | 补充ResponseComposer实现规范，或标记为简化项 |
| P2 | **INTENT_PARSER.md S-03/S-04重复**：简化项表中S-03和S-04内容完全相同 | ENGINEERING_INTENT_PARSER.md §11.1 | 删除重复的S-04行，重新编号后续项 |
| P2 | **PCR.md与DATA_MODEL.md数据契约不一致**：PCR.md说v1使用字符串，DATA_MODEL.md说使用枚举 | ENGINEERING_PCR.md §5, ENGINEERING_DATA_MODEL.md §4 | 统一声明：v1使用字符串(遗留)，v3使用枚举(新实现)，明确兼容策略 |
| P2 | **PCR.md S-04与DATA_MODEL.md声明冲突**：PCR.md标记认知画像双轨为简化，DATA_MODEL.md声称完全覆盖 | ENGINEERING_PCR.md §14.1, ENGINEERING_DATA_MODEL.md §9.1 | 统一声明：DATA_MODEL.md定义了模型，PCR.md的"简化"指运行时行为未完全接入双轨融合 |
| P2 | **Session持久化策略未实现**：设计文档§6.2要求Redis/PostgreSQL/S3分层持久化 | ENGINEERING_SERVICE_LAYER.md | 补充Session持久化规范，或引用PERSISTENCE.md的Session存储 |
| P3 | **ToolDefinition字段不完全对齐**：缺少source/tool_type/estimated_latency_ms/estimated_cost_tokens/执行统计 | ENGINEERING_TOOL_REGISTRY.md §6 | 补充字段，或标记为Phase 2扩展 |
| P3 | **缺少对话状态机实现**：设计文档§5.4定义7状态对话状态机，工程文档未明确实现 | ENGINEERING_DATA_MODEL.md §7.1 | 数据模型已定义DialogueStatus枚举，但需在服务层或编排层实现状态转换逻辑 |

---

**审查结论**：

- **ENGINEERING_API_DOC_PREPROCESSOR.md** 质量最高，等价性检查诚实准确，简化项合理。
- **ENGINEERING_PCR.md**、**ENGINEERING_INTENT_PARSER.md**、**ENGINEERING_PERSISTENCE.md**、**ENGINEERING_DATA_MODEL.md** 基本覆盖设计需求，但存在局部差异和跨文档不一致。
- **ENGINEERING_TOOL_REGISTRY.md** 和 **ENGINEERING_SERVICE_LAYER.md** 存在**核心功能缺失**且等价性检查**未诚实反映**这些缺失，需要优先修正。

*审查员注：建议所有工程文档在等价性检查章节中，对任何未实现或部分实现的设计需求统一使用"❌ 缺失"或"⚠️ 简化"标记，避免使用"✅ 等价"掩盖实际差距。*
