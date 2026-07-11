# DialogMesh Architecture Index

> 架构文档目录。按层次组织，每一层指向对应的设计文档和工程文档。
> 最后更新: 2026-07-09

---

## 导航

- [L0 系统定位与愿景](#l0)
- [L1 核心架构（v3.x / v4）](#l1)
- [L2 编译器层（Cognitive Compiler / Context Compiler）](#l2)
- [L3 记忆层（Persistent Graph / Discourse Block Tree / Topic Tree）](#l3)
- [L4 推理与行为层（BehaviorGraph / Causal / Predictor / Rewarder）](#l4)
- [L5 安全与护栏（PCR / NegativeKB / Hallucination）](#l5)
- [L6 交互与画像（CognitiveProfile / Intent Parser / Frontend）](#l6)
- [L7 服务与基础设施（API / LLM Provider / Observability / 持久化）](#l7)
- [L8 审查与评估](#l8)
- [L9 文献与参考](#l9)
- [L10 博客与公开文档](#l10)

---

## L0: 系统定位与愿景 {#l0}

| 文档 | 内容 | 状态 |
|:-----|:-----|:-----|
| [DESIGN_FULL_CONCEPT.md](v3.0/DESIGN_FULL_CONCEPT.md) | 完整概念设计（最早期，全系统范围） | 历史参考 |
| [DIALOGMESH_CONCEPT_DESIGN.md](../DIALOGMESH_CONCEPT_DESIGN.md) | 核心概念简介 | 可发布 |
| [design/IMPROVEMENTS.md](../design/IMPROVEMENTS.md) | 改进路线笔记 | 进行中 |
| [docs/blog/chapter1_conversation_tree.md](../blog/chapter1_conversation_tree.md) | 公开博客：对话树第一章 | 已发布 |
| [docs/blog/chapter1_design_thinking.md](../blog/chapter1_design_thinking.md) | 设计声明：对话树不是为了记忆 | 已发布 |

## L1: 核心架构（v3.x / v4） {#l1}

| 文档 | 内容 | 版本 | 状态 |
|:-----|:-----|:-----|:-----|
| [DESIGN_V4_CONTEXT_ENGINEERING.md](v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md) | **v4: Context Engineering（双 Compiler + Event Log + Context IR）** | v4 | **当前主设计** |
| [DESIGN_V3_2.md](v3.0/DESIGN_V3_2.md) | v3.2 模块蓝图（编译器、BehaviorGraph、因果基地等 12 模块） | v3.2 | 实现中 |
| [DESIGN_V3_1_BEHAVIOR_SUMMARY.md](v3.0/DESIGN_V3_1_BEHAVIOR_SUMMARY.md) | v3.1 行为总结设计 | v3.1 | 已整合 |
| [DESIGN_V3_3_ALGORITHM.md](v3.0/DESIGN_V3_3_ALGORITHM.md) | v3.3 算法设计（阈值方案、自适应、在线训练） | v3.3 | 部分实现 |
| [DESIGN_MULTILAYER_LLM_COGNITIVE.md](v3.0/DESIGN_MULTILAYER_LLM_COGNITIVE.md) | 多层 LLM 认知架构 | v3.0 | 基础参考 |
| [DESIGN_PLANNING_SKILL_LAYER.md](v3.0/DESIGN_PLANNING_SKILL_LAYER.md) | 规划与技能层设计 | v3.0 | 基础参考 |
| [DESIGN_TASK_PLANNING_DYNAMIC.md](v3.0/DESIGN_TASK_PLANNING_DYNAMIC.md) | 任务规划与动态编排 | v3.0 | 基础参考 |
| [design_architecture_gaps.md](v3.0/design_architecture_gaps.md) | 架构缺口分析 v1 | 历史 | 已关闭 |
| [design_architecture_gaps_v2.md](v3.0/design_architecture_gaps_v2.md) | 架构缺口分析 v2 | 历史 | 已关闭 |
| [docs/architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) | API 架构概览 | 通用 | 参考 |

---

## L2: 编译器层 {#l2}

### 设计文档

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_cognitive_compiler.md](v3.0/design_cognitive_compiler.md) | 认知编译器：将 Memory/Graph 编译为 Context | v3.0 |
| [DESIGN_V4_CONTEXT_ENGINEERING.md](v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md#44-context-compiler) | v4 Context Compiler：子图裁剪 + Context IR 生成 | v4 |
| [ENGINEERING_V3_2_COMPILER.md](v3.0/ENGINEERING_V3_2_COMPILER.md) | v3.2 编译器工程文档 | v3.2 |
| [ENGINEERING_V3_3_COMPILER.md](v3.0/ENGINEERING_V3_3_COMPILER.md) | v3.3 编译器工程文档 | v3.3 |

### 工程文档

| 文档 | 内容 |
|:-----|:-----|
| [ENGINEERING_COGNITIVE_COMPILER.md](v3.0/ENGINEERING_COGNITIVE_COMPILER.md) | 认知编译器实现细节 |
| [CONTEXT_COMPRESSION_DESIGN.md](v3.0/CONTEXT_COMPRESSION_DESIGN.md) | 上下文压缩设计 |
| [CONTEXT_COMPRESSION_RESEARCH.md](v3.0/CONTEXT_COMPRESSION_RESEARCH.md) | 上下文压缩文献调研 |

---

## L3: 记忆层 {#l3}

### 对话块树 / 话题树

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_discourse_block_tree.md](v3.0/design_discourse_block_tree.md) | 对话块树设计 v1 | v3.0 |
| [design_discourse_block_tree_v2.md](v3.0/design_discourse_block_tree_v2.md) | 对话块树设计 v2（Tree-Graph Hybrid、指针机制） | v3.2 |
| [design_topic_tree.md](v3.0/design_topic_tree.md) | 话题树设计 | v3.0 |
| [ENGINEERING_TOPIC_TREE.md](v3.0/ENGINEERING_TOPIC_TREE.md) | 话题树工程实现 | v3.0 |

### 持久化 / Context Manager

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_context_window.md](v3.0/design_context_window.md) | 上下文窗口设计 | v3.0 |
| [ENGINEERING_CONTEXT_MANAGER.md](v3.0/ENGINEERING_CONTEXT_MANAGER.md) | 上下文管理器实现 | v3.0 |
| [ENGINEERING_PERSISTENCE.md](v3.0/ENGINEERING_PERSISTENCE.md) | 持久化层实现 | v3.0 |
| [docs/project/design_persistence.md](../project/design_persistence.md) | 持久化层设计 | 通用 |
| [v4 Persistent Graph](v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md#42-persistent-graph) | v4: Property Graph + Typed Edge + Patch Chain | v4 |

### 数据模型

| 文档 | 内容 |
|:-----|:-----|
| [ENGINEERING_DATA_MODEL.md](v3.0/ENGINEERING_DATA_MODEL.md) | 核心数据模型定义 |

---

## L4: 推理与行为层 {#l4}

### BehaviorGraph / 行为语义嵌入

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_V3_3_BEHAVIOR_GRAPH.md](v3.0/ENGINEERING_V3_3_BEHAVIOR_GRAPH.md) | BehaviorGraph 工程文档 | v3.3 |
| [ENGINEERING_V3_3_BEHAVIOR_EMBEDDING.md](v3.0/ENGINEERING_V3_3_BEHAVIOR_EMBEDDING.md) | 行为语义嵌入工程文档 | v3.3 |

### 因果链 / do-calculus

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_V3_3_CAUSAL_SUBSTRATE.md](v3.0/ENGINEERING_V3_3_CAUSAL_SUBSTRATE.md) | 因果基地工程文档 | v3.3 |
| [ENGINEERING_V3_3_DO_CALCULUS.md](v3.0/ENGINEERING_V3_3_DO_CALCULUS.md) | do-calculus 工程文档 | v3.3 |

### Predictor / Rewarder / FoA / L1Summary

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_V3_3_PREDICTOR.md](v3.0/ENGINEERING_V3_3_PREDICTOR.md) | BehaviorPredictor 工程文档 | v3.3 |
| [ENGINEERING_V3_3_REWARDER.md](v3.0/ENGINEERING_V3_3_REWARDER.md) | BehaviorRewarder 工程文档 | v3.3 |
| [ENGINEERING_V3_3_FOA.md](v3.0/ENGINEERING_V3_3_FOA.md) | FoA 注意力焦点工程文档 | v3.3 |
| [ENGINEERING_V3_3_L1SUMMARY.md](v3.0/ENGINEERING_V3_3_L1SUMMARY.md) | L1Summary 工程文档 | v3.3 |

### 融合器

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_V3_3_FUSION.md](v3.0/ENGINEERING_V3_3_FUSION.md) | 分阶段融合器工程文档 | v3.3 |
| [ENGINEERING_INTEGRATION.md](v3.0/ENGINEERING_INTEGRATION.md) | v3.0 管线集成文档 | v3.0 |

---

## L5: 安全与护栏 {#l5}

### PCR（预处理 / 约束 / 规则）

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_layer0_pcr_and_layer1_intent_parser.md](v3.0/design_layer0_pcr_and_layer1_intent_parser.md) | Layer0 PCR + Layer1 意图解析设计 | v3.0 |
| [design_pcr_interface_v2_1.md](v3.0/design_pcr_interface_v2_1.md) | PCR 接口设计 v2.1 | v3.0 |
| [design_pcr_issues_discussion.md](v3.0/design_pcr_issues_discussion.md) | PCR 问题讨论 | v3.0 |
| [ENGINEERING_PCR.md](v3.0/ENGINEERING_PCR.md) | PCR 工程实现 | v3.0 |

### NegativeKB / 安全检测

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_V3_3_NEGATIVE_KB.md](v3.0/ENGINEERING_V3_3_NEGATIVE_KB.md) | 负知识库工程文档 | v3.3 |

---

## L6: 交互与画像 {#l6}

### 意图解析 / 前端

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_layer1_intent_parser.md](v3.0/design_layer1_intent_parser.md) | Layer1 意图解析设计 | v3.0 |
| [ENGINEERING_INTENT_PARSER.md](v3.0/ENGINEERING_INTENT_PARSER.md) | 意图解析器实现 | v3.0 |
| [DESIGN_FRONTEND.md](v3.0/DESIGN_FRONTEND.md) | 前端设计（GUI / WebSocket / 图可视化） | v3.0 |
| [design_observability.md](v3.0/design_observability.md) | 可观测性设计 | v3.0 |

### 用户画像

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [design_cognitive_profile_v2.md](v3.0/design_cognitive_profile_v2.md) | 认知画像设计 v2（八维画像） | v3.0 |
| [ENGINEERING_COGNITIVE_PROFILE_V2.md](v3.0/ENGINEERING_COGNITIVE_PROFILE_V2.md) | 认知画像工程实现 | v3.0 |

---

## L7: 服务与基础设施 {#l7}

### API / 服务层

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_SERVICE_LAYER.md](v3.0/ENGINEERING_SERVICE_LAYER.md) | 服务层实现 | v3.0 |
| [docs/project/design_service_layer_addon.md](../project/design_service_layer_addon.md) | 服务层扩展设计 | 通用 |
| [docs/api/ARCHITECTURE.md](../api/ARCHITECTURE.md) | API 架构 | 通用 |
| [docs/api/README.md](../api/README.md) | API 文档 | 通用 |
| [docs/api/CONFIGURATION.md](../api/CONFIGURATION.md) | API 配置 | 通用 |

### LLM Provider

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_LLM_PROVIDERS.md](v3.0/ENGINEERING_LLM_PROVIDERS.md) | LLM 提供者实现 | v3.0 |
| [ENGINEERING_MULTILAYER_LLM.md](v3.0/ENGINEERING_MULTILAYER_LLM.md) | 多层 LLM 工程实现 | v3.0 |
| [docs/LLM_PROVIDER_GUIDE.md](../LLM_PROVIDER_GUIDE.md) | LLM Provider 使用指南 | 通用 |

### 可观测性 / 监控

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_OBSERVABILITY.md](v3.0/ENGINEERING_OBSERVABILITY.md) | 可观测性实现 | v3.0 |
| [design_observability.md](v3.0/design_observability.md) | 可观测性设计 | v3.0 |

### MCP / Tool Registry

| 文档 | 内容 | 版本 |
|:-----|:-----|:-----|
| [ENGINEERING_TOOL_REGISTRY.md](v3.0/ENGINEERING_TOOL_REGISTRY.md) | 工具注册表实现 | v3.0 |
| [docs/MCP_DEPLOYMENT_BOUNDARY.md](../MCP_DEPLOYMENT_BOUNDARY.md) | MCP 部署边界 | 通用 |

---

## L8: 审查与评估 {#l8}

| 文档 | 内容 |
|:-----|:-----|
| [ARCHITECTURE_AUDIT_9_ISSUES.md](v3.0/ARCHITECTURE_AUDIT_9_ISSUES.md) | 架构审计：9 个问题 |
| [REVIEW_FULL_CONCEPT_ENGINEERING.md](v3.0/REVIEW_FULL_CONCEPT_ENGINEERING.md) | 完整概念工程化审查 |
| [REVIEW_MULTILAYER_LLM_CHECK.md](v3.0/REVIEW_MULTILAYER_LLM_CHECK.md) | 多层 LLM 审查 |
| [REVIEW_PLANNING_DESIGN_ENGINEERING.md](v3.0/REVIEW_PLANNING_DESIGN_ENGINEERING.md) | 规划设计工程化审查 |
| [reviews/DESIGN_FULL_CONCEPT_Simplification_Review.md](v3.0/reviews/DESIGN_FULL_CONCEPT_Simplification_Review.md) | 完整概念简化审查 |
| [reviews/INTEGRATION_CONSISTENCY_REVIEW.md](v3.0/reviews/INTEGRATION_CONSISTENCY_REVIEW.md) | 集成一致性审查 |
| [implementation_assessment.md](../implementation_assessment.md) | 实现评估 |
| [docs/TEST_REPORT.md](../TEST_REPORT.md) | 测试报告 |

---

## L9: 文献与参考 {#l9}

| 文档 | 内容 |
|:-----|:-----|
| [LITERATURE_CORTEX_CONVERSATION.md](v3.0/LITERATURE_CORTEX_CONVERSATION.md) | 皮层对话文献综述 |
| [LITERATURE_REF_DISCOURSE_BLOCK_TREE.md](v3.0/LITERATURE_REF_DISCOURSE_BLOCK_TREE.md) | 对话块树参考文献 |
| [LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md](v3.0/LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md) | 认知画像文献综述 |
| [THOUGHT_IMPRINT.md](v3.0/THOUGHT_IMPRINT.md) | 思考印记：认知架构设计哲学 |
| [EVALUATION_as_frontend_agent.md](v3.0/EVALUATION_as_frontend_agent.md) | 作为前端 Agent 的评估 |
| [mcp_industrial_assessment.md](v3.0/mcp_industrial_assessment.md) | MCP 工业评估 |
| [Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md](v3.0/Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md) | ContextAgent vs MemoryGraph 深度分析 |

---

## L10: 博客与公开文档 {#l10}

| 文档 | 内容 | 状态 |
|:-----|:-----|:-----|
| [chapter1_conversation_tree.md](../blog/chapter1_conversation_tree.md) | 第一章：对话块树（技术博客 + 附录论文式） | 已发布知乎/GitHub |
| [chapter1_design_thinking.md](../blog/chapter1_design_thinking.md) | 设计声明：对话树不是为了记忆 | 已发布知乎/GitHub |
| [docs/QUICKSTART.md](../QUICKSTART.md) | 快速开始指南 | 可发布 |

---

## 快速导航: 按角色查找

### 新手入门
1. [QUICKSTART.md](../QUICKSTART.md)
2. [DIALOGMESH_CONCEPT_DESIGN.md](../DIALOGMESH_CONCEPT_DESIGN.md)
3. [chapter1_conversation_tree.md](../blog/chapter1_conversation_tree.md)

### 核心开发者：当前主线
1. [DESIGN_V4_CONTEXT_ENGINEERING.md](v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md) ← **从这里开始**
2. [DESIGN_V3_2.md](v3.0/DESIGN_V3_2.md) ← 已实现模块的蓝图
3. 然后按需进入 L2-L6 的对应层

### 安全/护栏开发
1. L5: PCR + NegativeKB
2. [design_layer0_pcr_and_layer1_intent_parser.md](v3.0/design_layer0_pcr_and_layer1_intent_parser.md)

### 推理链/行为链开发
1. L4: BehaviorGraph → Causal Substrate → Predictor/Rewarder
2. [ENGINEERING_V3_3_BEHAVIOR_GRAPH.md](v3.0/ENGINEERING_V3_3_BEHAVIOR_GRAPH.md)

---

> 文档数量统计: ~80+ 篇设计/工程/审查/文献文档。本索引按层次组织，每个文档只出现一次（在其最相关的层次中）。
> 需要新增设计文档时，请同步更新本索引。
