# 历史文档归档索引

> 本文档是 DialogMesh 历史设计文档的归档索引。以下文档保留于 `docs/v3.0/` 和 `docs/` 原位不删除，
> 但它们不再是"当前设计"——当前设计以 `docs/merge/` 下的 5 篇文档为准。
>
> 归档原则：设计文档只写"做什么"和"为什么"。以下文档中的"怎么做"部分应看代码。
> 概念已被 v4 吸收的早期设计文档归档于此，供回溯参考。

---

## 1. v3.0/v3.1/v3.2/v3.3 设计文档（概念已被 v4 吸收）

| 文档 | 行数 | 内容 | 归档原因 |
|:---|:---|:---|:---|
| `DESIGN_V3_1_BEHAVIOR_SUMMARY.md` | 2430 | v3.1 行为总结设计 | 行为链概念已融入 v4 Hypothesis Engine |
| `DESIGN_V3_3_ALGORITHM.md` | 882 | v3.3 算法设计（阈值方案、自适应、在线训练） | 算法已融入 v4 BayesianOptimizer + BeliefState |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` | 1077 | 多层 LLM 认知架构 | 概念已融入 v4 MultiTierPipeline |
| `DESIGN_PLANNING_SKILL_LAYER.md` | 1783 | 规划与技能层设计 | 概念已融入 v4 Skill Layer |
| `DESIGN_TASK_PLANNING_DYNAMIC.md` | 1478 | 任务规划与动态编排 | 概念已融入 v4 Cognitive Scheduler |
| `design_cognitive_compiler.md` | 1882 | 认知编译器：Memory/Graph → Context | 概念已融入 v4 Context Compiler |
| `design_discourse_block_tree.md` | 867 | 对话块树设计 v1 | 概念已融入 v4 Observation Compiler |
| `design_discourse_block_tree_v2.md` | 1306 | 对话块树设计 v2（Tree-Graph Hybrid） | 同上 |
| `design_topic_tree.md` | 1187 | 话题树设计 | 概念已融入 v4 Event Layer + Projection |
| `design_context_window.md` | 968 | 上下文窗口设计 | 概念已融入 v4 BudgetAllocator |
| `design_cognitive_profile_v2.md` | 650 | 认知画像设计 v2（八维画像） | 概念已融入 v4 User Domain |
| `design_observability.md` | 1230 | 可观测性设计 | 概念已融入 v4 Monitor + Health |
| `design_pcr_interface_v2_1.md` | 940 | PCR 接口设计 v2.1 | 概念已融入 DESIGN_03 PCR |
| `design_pcr_issues_discussion.md` | 625 | PCR 问题讨论与修复记录 | 历史记录 |
| `design_layer0_pcr_and_layer1_intent_parser.md` | 2124 | Layer 0 + Layer 1 联合设计 | 概念已融入 DESIGN_03 |
| `design_layer1_intent_parser.md` | 532 | Layer 1 独立设计 | 同上 |
| `design_architecture_gaps.md` | 157 | 架构缺口分析 v1 | 已关闭 |
| `design_architecture_gaps_v2.md` | 107 | 架构缺口分析 v2 | 已关闭 |

---

## 2. ENGINEERING_*.md（实现细节，应看代码）

以下文档描述实现细节，当前应以代码为准。

| 文档 | 行数 | 内容 |
|:---|:---|:---|
| `ENGINEERING_COGNITIVE_PROFILE_V2.md` | 2034 | 认知画像工程实现 |
| `ENGINEERING_MULTILAYER_LLM.md` | 1724 | 多层 LLM 工程实现 |
| `ENGINEERING_PLANNING_SKILL.md` | 1641 | 规划技能工程实现 |
| `ENGINEERING_DATA_MODEL.md` | 1621 | 核心数据模型定义 |
| `ENGINEERING_SERVICE_LAYER.md` | 1521 | 服务层实现 |
| `ENGINEERING_PERSISTENCE.md` | 1320 | 持久化层实现 |
| `ENGINEERING_TOOL_REGISTRY.md` | 1216 | 工具注册表实现 |
| `ENGINEERING_TOPIC_TREE.md` | 909 | 话题树工程实现 |
| `ENGINEERING_INTENT_PARSER.md` | 909 | 意图解析器实现 |
| `ENGINEERING_V3_3_BEHAVIOR_GRAPH.md` | 907 | BehaviorGraph 工程文档 |
| `ENGINEERING_PCR.md` | 907 | PCR 工程实现 |
| `ENGINEERING_LLM_PROVIDERS.md` | 886 | LLM 提供者实现 |
| `ENGINEERING_CONTEXT_MANAGER.md` | 879 | 上下文管理器实现 |
| `ENGINEERING_COGNITIVE_COMPILER.md` | 995 | 认知编译器实现细节 |
| `ENGINEERING_OBSERVABILITY.md` | 864 | 可观测性实现 |
| `ENGINEERING_V3_3_BEHAVIOR_EMBEDDING.md` | 809 | 行为语义嵌入 |
| `ENGINEERING_API_DOC_PREPROCESSOR.md` | 764 | API 文档预处理 |
| `ENGINEERING_INTEGRATION.md` | 745 | v3.0 管线集成 |
| `ENGINEERING_V3_3_REWARDER.md` | 586 | BehaviorRewarder |
| `ENGINEERING_V3_3_PREDICTOR.md` | 573 | BehaviorPredictor |
| `ENGINEERING_V3_3_COMPILER.md` | 407 | v3.3 编译器 |
| `ENGINEERING_V3_3_NEGATIVE_KB.md` | 180 | 负知识库 |
| `ENGINEERING_V3_3_DO_CALCULUS.md` | 169 | do-calculus |
| `ENGINEERING_V3_3_L1SUMMARY.md` | 163 | L1Summary |
| `ENGINEERING_V3_3_FOA.md` | 112 | FoA 注意力焦点 |
| `ENGINEERING_V3_3_CAUSAL_SUBSTRATE.md` | 8 | 因果基地（几乎空） |
| `ENGINEERING_V3_3_FUSION.md` | 0 | 融合器（空文件） |

---

## 3. 审查与审计文档（历史快照）

| 文档 | 行数 | 内容 | 归档原因 |
|:---|:---|:---|:---|
| `ARCHITECTURE_AUDIT_9_ISSUES.md` | 774 | 9 项架构审计问题 | 问题已关闭 |
| `REVIEW_FULL_CONCEPT_ENGINEERING.md` | 216 | 完整概念工程化审查 | 历史快照 |
| `REVIEW_MULTILAYER_LLM_CHECK.md` | 263 | 多层 LLM 审查 | 历史快照 |
| `REVIEW_PLANNING_DESIGN_ENGINEERING.md` | 281 | 规划设计工程化审查 | 历史快照 |
| `reviews/DESIGN_FULL_CONCEPT_Simplification_Review.md` | 455 | 完整概念简化审查 | 历史快照 |
| `reviews/INTEGRATION_CONSISTENCY_REVIEW.md` | 212 | 集成一致性审查 | 历史快照 |
| `reviews/plan.md` | 75 | 审查计划 | 历史快照 |
| `docs/legacy/pcr_gap_assessment.md` | 203 | PCR gap 评估 v1 | 已关闭 |
| `docs/legacy/pcr_gap_assessment_v2_2.md` | 258 | PCR gap 评估 v2 | 已关闭 |
| `docs/legacy/checkpoint_pcr_p13.md` | 91 | PCR 检查点 P13 | 历史记录 |

---

## 4. 文献综述

| 文档 | 行数 | 内容 |
|:---|:---|:---|
| `LITERATURE_CORTEX_CONVERSATION.md` | 620 | 皮层对话文献综述 |
| `LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md` | 609 | 认知画像文献综述 |
| `LITERATURE_REF_DISCOURSE_BLOCK_TREE.md` | 397 | 对话块树参考文献 |
| `Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md` | 342 | ContextAgent vs MemoryGraph 深度分析 |
| `CONTEXT_COMPRESSION_RESEARCH.md` | 305 | 上下文压缩文献调研 |
| `EVALUATION_as_frontend_agent.md` | 198 | 作为前端 Agent 的评估 |
| `mcp_industrial_assessment.md` | 304 | MCP 工业评估 |

文献精华已融入 `DESIGN_00_OVERVIEW.md` §8 竞品对比。

---

## 5. 其他归档

| 文档 | 行数 | 内容 | 归档原因 |
|:---|:---|:---|:---|
| `RFC_PARAMETER_REGISTRY.md` | 337 | 参数注册表 RFC | 概念已融入各模块的 ParameterRegistry 集成 |
| `docs/project/design_service_layer_addon.md` | 1160 | 服务层扩展设计 | 概念已融入 DESIGN_04 |
| `docs/project/design_persistence.md` | 743 | 持久化层设计 | 概念已融入 DESIGN_02 |
| `docs/design/IMPROVEMENTS.md` | 310 | 改进路线笔记 | 进行中，保留参考 |
| `docs/DESIGN_SPECIFICATION.md` | 426 | 设计规范 | 历史参考 |
| `docs/architecture/ARCHITECTURE.md` | 685 | API 架构概览 | 历史参考 |
| `docs/api/README.md` | 609 | API 文档 | 历史参考 |
| `docs/api/CONFIGURATION.md` | 315 | API 配置 | 历史参考 |
| `docs/MCP_DEPLOYMENT_BOUNDARY.md` | 161 | MCP 部署边界 | 历史参考 |
| `docs/LLM_PROVIDER_GUIDE.md` | 224 | LLM Provider 使用指南 | 概念已融入 DESIGN_04 |
| `docs/TEST_REPORT.md` | 217 | 测试报告 | 历史快照 |
| `docs/QUICKSTART.md` | 251 | 快速开始指南 | 保留（用户文档） |
| `docs/v3.0/README.md` | 63 | v3.0 文档索引 | 被 merge/ 替代 |
| `docs/ARCHITECTURE_INDEX.md` | 272 | 原始架构索引 | 被 merge/ 替代 |

---

## 6. 博客（保留，公开内容）

| 文档 | 行数 | 内容 | 状态 |
|:---|:---|:---|:---|
| `docs/blog/chapter1_conversation_tree.md` | 417 | 第一章：对话块树 | 已发布 |
| `docs/blog/chapter1_design_thinking.md` | 237 | 设计声明：对话树不是为了记忆 | 已发布 |
| `docs/blog/chapter2_relation_over_prompt.md` | 575 | 第二章：关系优于提示 | 已发布 |

博客不属于设计文档，保留原位。

---

## 归档统计

| 类别 | 文档数 | 总行数 |
|:---|:---|:---|
| v3.x 设计（已吸收） | 18 | ~20,800 |
| ENGINEERING_*.md | 27 | ~22,800 |
| 审查/审计 | 10 | ~2,630 |
| 文献综述 | 7 | ~2,780 |
| 其他 | 14 | ~5,300 |
| 博客（保留） | 3 | ~1,230 |
| **合计** | **79** | **~55,540** |

当前设计文档（`docs/merge/`）：

| 文档 | 行数 |
|:---|:---|
| `DESIGN_00_OVERVIEW.md` | ~500 |
| `DESIGN_01_COGNITIVE_PIPELINE.md` | ~600 |
| `DESIGN_02_CONTEXT_AND_MEMORY.md` | ~700 |
| `DESIGN_03_INPUT_AND_SKILL.md` | ~500 |
| `DESIGN_04_INTERFACE.md` | ~300 |
| `ARCHIVE_INDEX.md` | ~200 |
| **合计** | **~2,800** |

**压缩率：65,700 行 → 2,800 行核心 + 55,540 行归档 = 96% 核心压缩**

---

> 归档文档不删除，保留原位供回溯。但后续开发以 `docs/merge/` 下的 5 篇核心文档为准。
> 不再新增设计文档——新设计决策追加到对应的 5 篇之一中。
