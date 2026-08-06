# DialogMesh v6

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-English-blue" alt="English"></a>
</p>

**自增长的认知运行时。** DialogMesh 是 LLM Agent 的认知引擎——它不只是执行工作流，而是**生长工作流**：遇到新任务时引擎现场生成执行计划，用真实工具跑通，把成功的路径沉淀为可复用模板。用得越多，越会做事。

模型任意带——DeepSeek、OpenAI、Anthropic，或本地 Ollama，都通过内置 switch 网关接入。密钥在你手里，数据在你机器上。

## 它是怎么工作的

告诉 DialogMesh 你想要什么，它会变成一张**任务地图**（DAG，类似 LangGraph / AWS Step Functions）：

1. **规划** — "查一下最近关于 X 的论文" → 编排器先查已知工作流，没有就让 LLM 现场生成（LLM 驱动的工作流生成）。
2. **执行** — 依赖允许的步骤**并行跑**（同 Tick fan-out，Petri 网语义）；工具执行前校验，结果回灌对话。
3. **确认** — 高风险步骤暂停等你批准（PlanGate）；每个决策都记录成事件，之后可回看（GitHub 更新日志式）。
4. **学习** — 跑成功的生成式工作流**蒸馏为模板**；失败带归因（计划/约束/数据/工具），回流到对应层。

```
┌──────────────────────────────────────────────────────┐
│            编排层（任务地图，宏观无环）                 │
│   内置模板 · LLM 生成 · 元认知沉淀                    │
├───────────────┬────────────────┬─────────────────────┤
│  7 棵并行记忆树 │  工具执行      │  元认知（第二大脑）   │
│  （对话/行为/  │  调用前校验 +  │  微观偏差仲裁 →       │
│   画像/…）     │  ReAct 重试    │  宏观计划变更        │
│              │  沙箱/权限      │                     │
└───────────────┴────────────────┴─────────────────────┘
```

## 核心能力

| 能力 | 含义 |
|---|---|
| **工作流自增长** | 新任务 → LLM 生成计划 → 成功沉淀为模板。不靠人工枚举所有流程。 |
| **并行编排** | 同 Tick 步骤并发执行（fan-out/fan-in），跨 Tick 依赖强制——带护栏的 Petri 网。 |
| **白盒化设计** | 每个图节点、树块、关系都可查看、可编辑。编辑被记录并可重放——认知的 Git 式版本控制。 |
| **双向归因学习** | 工具失败带归因（计划/约束/数据/工具），回流到导致它的那一层。偏差是养分，不是错误。 |
| **元认知闭环** | 第二大脑：审计决策、把微观失败仲裁成宏观计划变更、必要时执行中途改计划。 |
| **审批门控** | 写入、发送、高风险步骤暂停等你确认——低风险异步日志，高风险 PlanGate。 |
| **模型无关网关** | switch 网关：9+ 厂商、断路器、自适应并发、加权路由。带你的密钥来。 |
| **会老化的记忆** | 事件永不丢弃——热（全量）/ 温（按重要性减枝）/ 冷（语义摘要，可逆推）。 |

## 快速开始

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# 配置 provider 密钥
# 编辑 gateway/provider.yaml → 填入 API Key

# Windows
start.bat

# 或手动:
python scripts/start_server.py
```

- switch 网关: http://localhost:8080 (LLM 代理, 9+ 厂商)
- API: http://localhost:8000/docs
- 前端: http://localhost:4173 (React) — `cd frontend && npx vite preview --port 4173`

## 架构一览

```
用户输入 → [认知路由] → [意图] → [画像先验] → [编排 DAG]
                  │                              │
                  └── 任务图（并行步骤）←──────────┘

状态:  编排 ✅ · 记忆树 ✅ · 元认知 ✅
      语义存储 ✅ · 白盒编辑 ✅ · 网关 ✅
```

## 设计哲学（为什么这么做）

DialogMesh 建立在一条认知流水线上：**Event → Observation → Hypothesis → Knowledge → Skill**。每个模块从自己的视角（一级视角）观察，在更细颗粒度上验证（二级视角：结构/语义/时序/反例）。

几条核心公理：

| 公理 | 含义 |
|---|---|
| **树是推理工作台** | 对话树首先是推理树——管理推导焦点，不是记住一切。遗忘用激活计数取代时间衰减。 |
| **信念是竞争出来的** | 决策不看单一 confidence，看 7 维信念（支持/冲突/稳定性/覆盖/新颖/熵）。 |
| **关系 > 提示词** | 上下文是编译出来的局部知识快照（子图），不是 prompt 里的一句话。 |
| **抽象质量 = 可逆推性** | 压缩产物必须能反演还原（coverage 60-80%）。摘要不丢细节，只换缩放级别。 |
| **记录永不可删** | 事件链、修改记录不因"干净"而清理。一致性是记录出来的，不是锁出来的。 |
| **偏差 = 养分** | 每个失败都带归因，归因回流对应层——系统在偏差中变强。 |
| **快反馈 + 准后补 + 不阻断** | 用户立即得到回答优先于单次答案精度（System 1/2 快慢分流）。 |

完整公约见 [docs/only/wise/PARADIGM.md](docs/only/wise/PARADIGM.md)（A1-A25 公理 + P1-P28 原则）。

## 术语表（自创词 ↔ 主流类比）

| 我们叫它 | 主流对应 |
|---|---|
| 蓝图 (Blueprint) | LLM 驱动的工作流编排——DAG + 同 Tick 并行（Petri 网语义），类 LangGraph / Step Functions |
| PCR | 认知路由——System 1/2 快慢分流 |
| 关联链 (Association Chain) | 语义关系发现与晋升——知识图谱构建 + 因果推断 |
| 对话树 (Discourse Tree) | 会话状态追踪 + 主题聚焦——dialogue-state tracking |
| 行为链 (Behavior Chain) | 用户行为预测——预测建模 + DPO 偏好学习 |
| 工程链 (Engineering Chain) | 代码/设计约束传导——规则/约束引擎 |
| 子图 (Subgraph) | 上下文编译——为 LLM 检索局部知识（GraphRAG 式） |
| 元认知 (Metacognition) | 自我反思 / 第二大脑——元认知控制环 |
| 画像 (Profile) | 用户画像——OCEAN/BFI 特质推断 + 惯性追踪 |
| 温度系统 (Temperature) | 记忆上的多因子注意力/热度加权 |
| 认知流水线 | Event → Observation → Hypothesis → Knowledge → Skill 五层精炼 |
| 白盒化 | 内容可操作、行为必记录——查改增删是承诺不是功能 |

## 文档导航

| 文档 | 内容 |
|---|---|
| [架构总览](docs/ARCHITECTURE_OVERVIEW.md) | 三层认知运行时：编排 × 记忆 × 元认知 |
| [设计范式公约](docs/only/wise/PARADIGM.md) | A1-A25 公理 + P1-P28 原则 + 冲突裁决元规则 |
| [API 参考](docs/GUI_API.md) | 90+ 端点 |
| [网关设计](switch/docs/BUSINESS_CHAIN_01_GATEWAY.md) | switch 网关内部 |
| [实现现状](docs/IMPLEMENTATION_REALITY.md) | 代码 vs 设计覆盖率 |
| [模块审计](docs/only/) | 23+ 模块深度审计与施工记录 |

---

*为会用而学习的 Agent 而生。*
