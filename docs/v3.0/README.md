# 前置 Agent 文档索引

本目录包含 **MemoryGraph 前置 Agent（Frontend Agent）** 的所有设计文档，覆盖 Layer 0（PCR 认知路由器）至 Layer 1（Intent Parser 意图解析器）的完整链路。

---

## 目录结构

### 核心设计文档

| 文件 | 说明 | 对应代码 |
|---|---|---|
| `design_layer0_pcr_and_layer1_intent_parser.md` | Layer 0 + Layer 1 联合设计：PCR 调控 Intent Parser 的完整链路 | `core/agent/pcr/`, `core/agent/intent_parser.py` |
| `design_layer1_intent_parser.md` | Layer 1 独立设计：10 阶段解析管道详细规范 | `core/agent/intent_parser.py` |
| `design_pcr_interface_v2_1.md` | PCR 接口 v2.1：期望识别、噪声评估、认知维度 | `core/agent/pcr/rule_based.py` |
| `design_pcr_issues_discussion.md` | PCR 问题讨论与修复记录 | `core/agent/pcr/` |

### 上下文管理

| 文件 | 说明 | 对应代码 |
|---|---|---|
| `design_context_window.md` | 上下文窗口管理：压缩、截断、滑动窗口策略 | `core/agent/window/context_window_manager.py` |
| `design_topic_tree.md` | 对话树管理：话题切换、fork/attach/continue 语义 | `core/agent/topic_tree/` |
| `CONTEXT_COMPRESSION_DESIGN.md` | 上下文压缩设计：多级压缩策略 | `core/agent/window/` |
| `CONTEXT_COMPRESSION_RESEARCH.md` | 上下文压缩研究：算法选型与基准测试 | 研究参考 |

### 可观测性与工业化

| 文件 | 说明 | 对应代码 |
|---|---|---|
| `design_observability.md` | 可观测性设计：Metrics、Logging、Alerting | `core/agent/metrics.py`, `core/agent/structured_logger.py`, `core/agent/alert_manager.py` |
| `design_architecture_gaps.md` | 架构缺口分析（原始版） | 已修复 |
| `design_architecture_gaps_v2.md` | 架构缺口分析（v2） | 已修复 |
| `ARCHITECTURE_AUDIT_9_ISSUES.md` | 9 项架构审计问题与修复 | `tests/` |
| `mcp_industrial_assessment.md` | 工业化落地评估：P0-P2 完成度 | 综合评估 |

### 认知编译器与评估

| 文件 | 说明 | 对应代码 |
|---|---|---|
| `design_cognitive_compiler.md` | 认知编译器：多层认知处理流水线 | 设计阶段 |
| `EVALUATION_as_frontend_agent.md` | 作为前置 Agent 的评估报告 | 评估报告 |

---

## 快速入口

- **想理解完整流水线**：从 `design_layer0_pcr_and_layer1_intent_parser.md` 开始
- **只看 Intent Parser 10 阶段**：`design_layer1_intent_parser.md`
- **想了解可观测性实现**：`design_observability.md` + `mcp_industrial_assessment.md`
- **想了解架构修复过程**：`ARCHITECTURE_AUDIT_9_ISSUES.md`

---

## 实现状态

| 层级 | 设计状态 | 代码状态 | 测试 |
|---|---|---|---|
| Layer 0: PCR | ✅ 完成 | ✅ 实现 | ✅ 通过 |
| Layer 1: Intent Parser | ✅ 完成 | ✅ 实现 (10 Stage) | ✅ 通过 |
| Layer 2-5: 规划/执行/反思 | ⚠️ 设计 | ⚠️ 未实现 | — |

> 注：Layer 2-5 的设计文档位于 `../../legacy/project/design_v2_complete.md`（逆向工程完整系统），与本前置 Agent 独立。
