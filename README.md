# DialogMesh v4

[![Python](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-179%2B-green)](core/agent/v4/compiler/tests/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![Phase](https://img.shields.io/badge/phase-1%20complete-blue)](docs/merge/DESIGN_01_COGNITIVE_PIPELINE.md)

> **认知引擎** — 不是写更好的 prompt，是构建让 LLM 理解代码世界的结构化上下文。
>
> **白盒化**：每一个模块都是可探索的。你不只是在"用"一个引擎——你在理解它如何观察世界、如何决策、如何推理。从 SemanticObject 到 RelationEdge，从 DiscourseBlock 到 Perspective，全部可查看、可调试、可扩展。

---

## 是什么

DialogMesh 是一个**语义世界运行时**——将设计文档、对话历史、行为链编译为 LLM 可导航的结构化世界模型。

当前导入的文档（`docs/v3.0/DESIGN_*.md`）是**测试数据**——用来验证世界模型构建管线。你自己的代码库、设计文档、API 规范同样可以摄入，构建属于你项目的语义世界。

[世界模型设计 →](docs/v3.0/DESIGN_SEMANTIC_WORLD_MODEL.md) ·
[关系基座 →](docs/v3.0/DESIGN_RELATION_SUBSTRATE.md) ·
[视角决策 →](docs/v3.0/DESIGN_PERSPECTIVE_PLANNER.md) ·
[对象系统 →](docs/v3.0/DESIGN_SEMANTIC_OBJECT.md)

---

## 5 分钟跑起来

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh
uv venv .venv && uv pip install -r requirements.txt

# 交互对话（需要 DeepSeek API Key）
export DEEPSEEK_API_KEY=sk-...
.venv/Scripts/python run_chat.py

# 或使用 CLI
.venv/Scripts/python -m core.agent.v4.cli.main status
.venv/Scripts/python -m core.agent.v4.cli.main inspect world
```

[完整 CLI 参考 →](docs/v3.0/DESIGN_CLI_REFERENCE.md) ·
[安装帮助 →](docs/v3.0/SETUP.md)

---

## 架构

```
用户输入 ─→ PerspectivePlanner ─→ Multi-Perspective 渲染
                  │                       │
           Domain Allocator         SemanticObject × ObjectRuntime
                  │                       │
           DiscourseBlockTree ────→ ContextCompiler ──→ LLM
                  │
           RelationSubstrate (typed edges + evidence)
```

[认知管线 →](docs/merge/DESIGN_01_COGNITIVE_PIPELINE.md) ·
[上下文编译 →](docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md) ·
[话语块树 →](docs/v3.0/design_discourse_block_tree_v2.md)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 🧠 **语义世界** | 9.8K SemanticObject + 5.4K RelationEdges，基于 88 篇设计文档构建 |
| 🎯 **多视角渲染** | primary (depth=2) + secondary (depth=1) 互补观察，token budget 自适应 |
| 🌳 **对话树** | 9 维粘合度模型，continue/fork/attach 分支决策 |
| 🔗 **关系基座** | relation_kind × semantic_strength 正交模型，typed edges + evidence chain |
| 👤 **用户画像** | TrackA 动态认知 (认知惯性/信任度/注意力锚点) 每轮累积 |
| 📊 **多层次提取** | jieba (10ms) → Stanza (50ms) → LMStudio (500ms) → DeepSeek (2s) 四层降级 |

---

## 测试

```bash
.venv/Scripts/python -m pytest core/agent/v4/compiler/tests/ -q
```

[测试报告 →](docs/v3.0/TEST_REPORT.md)

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [DESIGN_SEMANTIC_WORLD_MODEL](docs/v3.0/DESIGN_SEMANTIC_WORLD_MODEL.md) | 世界模型架构 + 6 Mermaid 图 |
| [DESIGN_SEMANTIC_OBJECT](docs/v3.0/DESIGN_SEMANTIC_OBJECT.md) | 递归语义对象 + 投影解析器 |
| [DESIGN_RELATION_SUBSTRATE](docs/v3.0/DESIGN_RELATION_SUBSTRATE.md) | 统一关系基座 + 因果解释层 |
| [DESIGN_PERSPECTIVE_PLANNER](docs/v3.0/DESIGN_PERSPECTIVE_PLANNER.md) | 意图→策略→域分配 + Multi-Perspective |
| [DESIGN_DISCOURSE_BLOCK_TREE](docs/v3.0/design_discourse_block_tree_v2.md) | 话语块树 + 粘合度模型 |
| [DESIGN_CROSS_DOMAIN_CONTEXT](docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md) | 跨域上下文编译 IR |
| [CLI 参考](docs/v3.0/DESIGN_CLI_REFERENCE.md) | 27 个命令完整参考 |
| [认知管线](docs/merge/DESIGN_01_COGNITIVE_PIPELINE.md) | 四路径调度 + 快慢系统 |
| [Phase 计划](docs/merge/DESIGN_00_OVERVIEW.md) | Phase 0-4 里程碑 |
