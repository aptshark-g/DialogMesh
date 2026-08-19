# DialogMesh

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python"></a>
  <a href="https://github.com/aptshark-g/DialogMesh"><img src="https://img.shields.io/badge/tests-1900%2B-green" alt="Tests"></a>
</p>

**自增长的认知运行时。** DialogMesh 是一个通用 LLM Agent 引擎——它不只是执行工作流，而是**生长工作流**：遇到新任务时引擎现场生成执行计划，用真实工具跑通，把成功的路径沉淀为可复用模板。用得越多，越会做事。

模型任意带——DeepSeek、OpenAI、Anthropic，或本地 Ollama，都通过内置 switch 网关接入。密钥在你手里，数据在你机器上。

---

## 它能帮你做什么

- **写代码并运行** — "写一个 hello world 并运行" → Agent 自己写文件、执行、看结果、向你汇报（真实 function calling，不是纸面规划）
- **查论文 / 查资料** — 内置 arxiv 检索、网页抓取、PDF 解析；统一召回把历史对话、知识库、语义关系混排
- **控制终端与文件** — 运行 shell、Python、后台长任务会话、目录浏览、grep——全部过权限门（4 级风险分级，链式命令与越权写入被拦截）
- **多步任务自己规划** — 给它一个目标（"规划一个带 JWT 认证的服务"），它生成任务图，你确认后逐节点执行
- **记住你的偏好** — 用户画像（OCEAN/MBTI/惯性）、行为链预测、对话树管理上下文，越聊越懂你
- **每一步都白盒** — 图谱/上下文/画像可查看可编辑，编辑与决策全部留痕，可回看可回滚

一个例子，感受它的差异：让它 **"5 分钟内做一个 Minecraft 风格小游戏"**。普通 Agent 会手搓任务规划直到超时；DialogMesh 的元认知层监视到"这条路要超时"，会主动裁决换方案（比如下载开源成品再改造），并把这次切换作为一条变更日志展示给你——你可以批准、否决或加约束，它不打断当前执行。

---

## 它是怎么工作的

告诉 DialogMesh 你想要什么，它会变成一张**任务地图**（DAG，类似 LangGraph / AWS Step Functions）：

1. **规划** — "查一下最近关于 X 的论文" → 编排器先查已沉淀的工作流，没有就让 LLM 现场生成（LLM 驱动的工作流生成）。
2. **执行** — 依赖允许的步骤**并行跑**（同 Tick fan-out，Petri 网语义）；工具执行前过权限校验，结果回灌对话。
3. **确认** — 高风险步骤暂停等你批准（PlanGate）；低/中风险异步记录为决策事件，之后可回看（GitHub 更新日志式），可 approve / reject。
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

---

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
| **执行链路高可用** | 治理是元认知的子模块（不是基础设施）：熔断/定向重试/幂等 + 异步诊断根因 + 主动体检 + 启动预热 + 请求级预算传播。 |
| **受控自修自迭代** | 元认知读自己的代码（系统自画像）、生成修复包过审批门、验证失败自动回滚；修复凝练为可逆推教训回写经验库（贝叶斯 prior 累积）。 |
| **会老化的记忆** | 事件永不丢弃——热（全量）/ 温（按重要性减枝）/ 冷（语义摘要，可逆推）。 |
| **统一召回** | BGE 向量 + BM25 + 语法结构（SPO）投影 + HyDE 扩展 + 关联链融合（RRF），溯源置信度加权。 |
| **可测可验证** | 1900+ pytest 用例，模块域内全绿；前端 tsc 零错误。 |

---

## 元认知：思考的思考，也是自己的运维

大多数 Agent 的"反思"停留在任务层（让 LLM 重新想一遍）。DialogMesh 的元认知
把**执行链路本身**当成治理对象——像运维团队维护一个生产系统，但审批权内建：

- **小环（秒级止血）**：`ExecutionGovernor` 按阶段/工具熔断（三态+半开恢复）、
  错误定向重试（超时/空返回/连接/解析分策略）、幂等短路。链路不再是"各调用点
  各自设超时、串行叠加到卡死"。
- **大环（分钟级复盘）**：`AsyncDiagnoser` 把失败信号异步深挖——收集熔断状态、
  LLM 调用观测、执行树证据 → LLM 根因分析 → 低风险建议自动应用，高风险留建议。
- **主动体检（无触发也自检）**：`ProactiveHealthProbe` 定期用系统自画像 + 失败
  统计巡检——没出事也防患于未然，薄弱点自动转交诊断。
- **启动预热 + 请求级预算**：懒路径（意图/话语/嵌入模型）启动期预热，重启后
  首请求实测 43.9s → 1.8s；deadline 沿 classify→planning→执行→工具调用传播，
  `run_dag` 移出事件循环——慢上游不再让整个 API 卡死。
- **受控自修自迭代**：`SelfIntrospection` 让元认知读自己的代码（模块地图/测试
  覆盖/变更历史/薄弱点）；`SelfRepair` 生成修复包 → 过审批门 → `git apply` →
  白名单验证 → 失败自动回滚；修复后凝练成"可逆推的设计教训"回写经验库
  （语义检索复用，贝叶斯 prior 累积）——像 codex 开发自己，但每次改动都可审计。

> **设计判断：为什么"对内自修"优于"外部多 Agent 修"？** 外部 bc 在自己约束
> 上下文里执行，缺被修对象 a 的设计约束作先验，只能不断试错；元认知持有 a 的
> 视角（AGENTS.md 铁律 + 追踪矩阵），修复才有逆推验证的锚点——这是贝叶斯共识
> （后验喂回先验）能持续演进的根，也是我们暂不做多 Agent 协作的架构理由。

---

## 与主流 Agent 的对比

| | DialogMesh | Claude Code / Cursor | OpenClaw | 普通 RAG + ReAct Agent |
|---|---|---|---|---|
| 工作流生成 | ✅ LLM 现场生成 + 成功沉淀 | ❌ 固定步骤 | 🟡 模板为主 | ❌ 固定 |
| 执行透明度 | ✅ 每一步可查看/编辑/回滚 | ❌ 黑盒 | 🟡 部分 | ❌ |
| 元认知仲裁 + 自修 | ✅ 微观失败 → 宏观换计划 + 治理链路 + 受控自修（审批门/回滚/经验回写） | ❌ | ❌ | ❌ |
| 决策留痕 | ✅ 变更日志 + 可介入 | ❌ | 🟡 会话记录 | ❌ |
| 记忆分层 | ✅ 热/温/冷 + 事件永不丢 | 🟡 上下文窗口 | 🟡 会话记忆 | 🟡 向量库 |
| 多步并行 | ✅ 同 Tick 并行 + 依赖强制 | 🟡 | 🟡 | ❌ |
| 多渠道/多媒体 | 🕓 未做（路线图） | — | ✅ 强项 | — |
| 生态成熟度 | 🕓 新项目 | ✅ | ✅ | ✅ |

> 诚实声明：渠道接入（Telegram/Slack/Discord 等）、多媒体、Docker/SSH 终端后端是路线图项，尚未实现。

---

## 快速开始

```bash
git clone https://github.com/aptshark-g/DialogMesh.git
cd DialogMesh

# 一键检查 + 安装环境（Python 依赖较大, 首次约几分钟~十几分钟）
# 依赖清单见 docs/SETUP.md
python scripts/setup_env.py

# 启动（Windows）
start.bat

# 或手动:
python scripts/start_server.py
```

> 一键脚本会自动: 建 .venv 装 Python 依赖 → 前端 npm install + build →
> 补齐网关二进制（有 Go 时自动从 switch 源码构建）→ 复制 provider.yaml / .env
> 示例。**记得在 gateway/provider.yaml 填入你的 API Key**（支持 DeepSeek /
> OpenAI / Anthropic / Gemini / Kimi / Groq / OpenRouter / LM Studio / Ollama）。
>
> 也可先检查: `python scripts/setup_env.py --check`; 分段安装: `--deps` /
> `--frontend` / `--gateway` / `--models`。

- switch 网关: http://localhost:8080 (LLM 代理, 9+ 厂商)
- API: http://localhost:8000/docs
- 前端: http://localhost:4173 (React) — `cd frontend && npx vite preview --port 4173`

> 改完 provider.yaml 或后端代码后需重启 start.bat 生效（网关每 5s 热加载配置）。

---

## 架构一览

```
用户输入 → [认知路由] → [意图] → [画像先验] → [编排 DAG]
                  │                              │
                  └── 任务图（并行步骤）←──────────┘

执行层:  StateMachine 逐节点执行（认知链 handler + 工具节点）
        LLM function calling（tool_loop）—— 编码/实现类请求自主调工具
监控层:  Hot 信号 → Warm 裁决（超时/失败率）→ Cold 复盘（每 5 轮）
留痕层:  决策事件流 → /v6/changelog（回看/介入） + /v6/execution（执行迹）
```

状态：编排 ✅ · 记忆树 ✅ · 元认知 ✅（治理/诊断/体检/自修）· 执行层 ✅ · 语义存储 ✅ · 白盒编辑 ✅ · 网关 ✅

详细架构（mermaid 三层图）见 [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) 与 [执行层架构定案](docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md)。

---

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

---

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
| 元认知 (Metacognition) | 自我反思 / 第二大脑——元认知控制环 + 执行链路治理（熔断/诊断/体检）+ 受控自修自迭代 |
| 画像 (Profile) | 用户画像——OCEAN/BFI 特质推断 + 惯性追踪 |
| 白盒化 | 内容可操作、行为必记录——查改增删是承诺不是功能 |
| tool_loop | LLM 自主工具调用循环——function calling / ReAct |

---

## 文档导航

| 文档 | 内容 |
|---|---|
| [架构总览](docs/ARCHITECTURE_OVERVIEW.md) | 三层认知运行时：编排 × 记忆 × 元认知 |
| [第一版功能核对](docs/only/V1_FUNCTION_CHECKLIST_20260808.md) | 端到端自检清单（对标 OpenClaw/Hermes/OpenWorker） |
| [执行层架构定案](docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md) | 蓝图宏观 × 执行微观 × 元认知监控 |
| [设计范式公约](docs/only/wise/PARADIGM.md) | A1-A25 公理 + P1-P28 原则 + 冲突裁决元规则 |
| [API 参考](docs/GUI_API.md) | 130+ 端点 |
| [变更日志](CHANGELOG.md) | 版本演进 |

---

*为会用而学习的 Agent 而生。*
