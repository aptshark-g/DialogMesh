# Literature Cortex — 设计文档索引

> 本文档自动维护，按版本与主题分组。

---

## v7.0-external — 当前主线（对外验证引擎）

| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [DESIGN-v7.0-EXTERNAL.md](v7.0-external/DESIGN-v7.0-EXTERNAL.md) | 🔄 设计阶段 | 万能对外验证引擎：统一 Pipeline 入口、L0-L5 验证链、多重检索工作流、辩证引擎、模糊评分、FeedbackLoop 修正回流、与 DialogMesh 协同 |

---

## v6.x — 编排层与认知流

| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [DESIGN-v6.0-UNIFIED.md](v6.x/DESIGN-v6.0-UNIFIED.md) | ✅ 已修正 | 完整架构底座：统一引擎 + 向量延拓 + L5 指挥官 + 量化反馈 + CSM 四层认知流 + 三大死穴修补 |
| [DESIGN-v6.1-ORCHESTRATION.md](v6.x/DESIGN-v6.1-ORCHESTRATION.md) | 🚧 实施中 | L5 指挥官、MetaCognitiveArbiter、CSM 四层认知流、AntiBloat / ValidationFeedback 闭环 |
| [DESIGN-COGNITIVE-FLOW-v6.2-CONCEPT.md](v6.x/DESIGN-COGNITIVE-FLOW-v6.2-CONCEPT.md) | ✅ 概念定型 | 认知智流完整概念设计：从编排引擎到通用认知系统的升级蓝图 |

---

## v5.2-csm — 匹配与形式化引擎系列

| 文档 | 核心内容 |
|------|----------|
| [DESIGN-v5.2-meta-cognitive-dual-core.md](v5.2-csm/DESIGN-v5.2-meta-cognitive-dual-core.md) | 元认知双核架构总纲 |
| [DESIGN-v5.2a-dual-matcher.md](v5.2-csm/DESIGN-v5.2a-dual-matcher.md) | VF2 + 语义双路径匹配 |
| [DESIGN-v5.2b-self-reference.md](v5.2-csm/DESIGN-v5.2b-self-reference.md) | 自指循环检测 |
| [DESIGN-v5.2c-formalization-engine.md](v5.2-csm/DESIGN-v5.2c-formalization-engine.md) | 符号形式化转译 |
| [DESIGN-v5.2d-universal-coarse-matcher.md](v5.2-csm/DESIGN-v5.2d-universal-coarse-matcher.md) | 粗粒度预筛选 |
| [DESIGN-v5.2e-end2end-fixes.md](v5.2-csm/DESIGN-v5.2e-end2end-fixes.md) | 全流程修补 |
| [DESIGN-v5.2f-llm-native-formalization.md](v5.2-csm/DESIGN-v5.2f-llm-native-formalization.md) | LLM 直接输出形式化表示 |
| [DESIGN-v5.3-proportion-controller.md](v5.2-csm/DESIGN-v5.3-proportion-controller.md) | 算力比例化精细调度 |
| [DESIGN-v5.4-coordinative-layer.md](v5.2-csm/DESIGN-v5.4-coordinative-layer.md) | 跨模块协调机制 |

---

## v5.x-legacy — 历史版本

| 文档 | 备注 |
|------|------|
| [v4.1-active-growth.md](v5.x-legacy/v4.1-active-growth.md) | 主动生长型认知引擎：双层持久化 + 双推理内核 |
| [v5.0-causal-deconstruction.md](v5.x-legacy/v5.0-causal-deconstruction.md) | 因果解构，已融入 v6.x |
| [v5.1-dual-network-coordination.md](v5.x-legacy/v5.1-dual-network-coordination.md) | 双网协调，已融入 v6.x |

---

## modules — 专项设计

| 文档 | 核心内容 |
|------|----------|
| [DESIGN-DIVERGENT-v0.1-draft.md](modules/DESIGN-DIVERGENT-v0.1-draft.md) | 发散层初稿 |
| [DESIGN-DIVERGENT-v0.2-supplement.md](modules/DESIGN-DIVERGENT-v0.2-supplement.md) | 发散层补充 |
| [DESIGN-DIVERGENT-v0.3-revised.md](modules/DESIGN-DIVERGENT-v0.3-revised.md) | 发散层终版：主动破坏、权重重标定、双权重约束 |
| [DESIGN-META-COGNITIVE-TREE-v1.0.md](modules/DESIGN-META-COGNITIVE-TREE-v1.0.md) | L5 决策树结构、推理路径记录 |
| [DESIGN-meta-cognitive-retroactive-validation.md](modules/DESIGN-meta-cognitive-retroactive-validation.md) | 逆向验证机制、反思回溯 |
| [DESIGN-L0L4-EVOLUTION-v1.0.md](modules/DESIGN-L0L4-EVOLUTION-v1.0.md) | 公理层动态演化 |
| [DESIGN-L0L4-EVOLUTION-SUPPLEMENT-v1.0.md](modules/DESIGN-L0L4-EVOLUTION-SUPPLEMENT-v1.0.md) | 演化机制补充 |
| [DESIGN-L0L1-INTEGRATION-v1.0.md](modules/DESIGN-L0L1-INTEGRATION-v1.0.md) | 公理层与元理论层衔接 |
| [DESIGN-REGISTRY.md](modules/DESIGN-REGISTRY.md) | 元角色与 35 领域注册 |
| [DESIGN-CALIBRATION-EXECUTOR-v1.0.md](modules/DESIGN-CALIBRATION-EXECUTOR-v1.0.md) | 阈值自校准 |
| [DESIGN-COMPLETENESS-ASSESSMENT-v1.0.md](modules/DESIGN-COMPLETENESS-ASSESSMENT-v1.0.md) | 系统完备性检查 |
| [DESIGN-COORDINATIVE-ASSESSMENT-v1.0.md](modules/DESIGN-COORDINATIVE-ASSESSMENT-v1.0.md) | 模块协调度评估 |
| [DESIGN-ALGORITHM-HERITAGE-v1.0.md](modules/DESIGN-ALGORITHM-HERITAGE-v1.0.md) | 历史算法记录 |
| [DESIGN-WEIGHT-QUANT-v1.0.md](modules/DESIGN-WEIGHT-QUANT-v1.0.md) | 权重量化方案 |
| [DESIGN-GAP-ANALYSIS-Phase1-4.md](modules/DESIGN-GAP-ANALYSIS-Phase1-4.md) | Phase 1-4 缺口分析 |
| [DESIGN-text-cleaning-pipeline.md](modules/DESIGN-text-cleaning-pipeline.md) | 预处理管道 |
| [DESIGN-three-problems-fix.md](modules/DESIGN-three-problems-fix.md) | 专项修补 |
| [DESIGN-claw-ai-bidirectional.md](modules/DESIGN-claw-ai-bidirectional.md) | 与 OpenClaw 双向集成 |
| [DESIGN-LLMCortex-v1.0.md](modules/DESIGN-LLMCortex-v1.0.md) | 早期 LLM 接入设计 |

---

## 快速定位

| 你想查什么 | 目录 |
|-----------|------|
| 当前对外验证系统完整设计 | `v7.0-external/` |
| L0-L5 各层职责与接口 | `v6.x/DESIGN-v6.0-UNIFIED.md` |
| L5 指挥官 / 编排逻辑 | `v6.x/DESIGN-v6.1-ORCHESTRATION.md` |
| 认知智流升级方向 | `v6.x/DESIGN-COGNITIVE-FLOW-v6.2-CONCEPT.md` |
| 发散 / 破坏 / 假设生成 | `modules/DESIGN-DIVERGENT-v0.3-revised.md` |
| CSM 匹配引擎细节 | `v5.2-csm/` |
| 35 领域 / 元角色注册 | `modules/DESIGN-REGISTRY.md` |
| 系统缺口与待办 | `modules/DESIGN-GAP-ANALYSIS-Phase1-4.md` |

---

*索引生成：2026-08-09*
