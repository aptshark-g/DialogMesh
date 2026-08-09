# 系统级外部对标 — OpenClaw × Hermes × OpenWorker（2026-08-06）

> 触发: 用户判断"后端完备性需要外部参照系——别人的项目有大量检验，
> 我们的功能/效果要在别人已有的基础上更进一步"（哲学包容性 A1）。
> 方法: 官方 README + GitHub API 拉取核心源码定向精读（真实代码证据,
> 非二手描述）。已有基础: GATEWAY_BENCHMARK（网关域）、
> BEHAVIOR_RESEARCH_SURVEY（行为域）、FLOW_SELF_GROWTH §5.5（工具调度域）。
> 本文档是**系统级**对标（执行/工具/认知/编排/记忆/元认知/上下文/存储/网关）。

---

## 一、对标对象速览（2026-08-06 实测 GitHub）

| 项目 | 仓库 | 语言 | Stars | 定位 | 与我们最贴近的域 |
|------|------|------|-------|------|----------------|
| OpenClaw | openclaw/openclaw | TypeScript | 385K | 单操作员个人 AI 助手, Gateway 本地控制平面, 多渠道 | 执行层/工具层/网关 |
| Hermes | NousResearch/hermes-agent | Python | 226K | **自我改进 agent**（技能自建自修 + 记忆闭环） | 元认知/技能/记忆 |
| OpenWorker | andrewyng/openworker | Python | 13K | 本地优先 AI coworker（交付成品 + 审批门控 + 连接器） | 审批/调度/蓝图编排 |

三个项目合计覆盖我们后端全部核心域: 执行/工具（OpenClaw）、认知/学习（Hermes）、
编排/安全（OpenWorker）。注意: **三个都是 2025-2026 爆发项目, 且 Hermes 提供
`hermes claw migrate`（从 OpenClaw 迁移）——生态在快速收敛到同一套模式**。

---

## 二、能力矩阵（按域, ✅有 / ⚠️部分 / ❌无 / 🟢领先）

### A. 执行循环

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 消息处理运行时 | ✅ StateMachine + BlueprintExecutor | ✅ agentLoop | ✅ conversation_loop | ✅ agent loop |
| 同 Tick/批处理并行 | ✅ run_dag 同 Tick 并行 | ✅ executeToolCallsParallel | ⚠️ 子代理并行 | ❌ 串行 |
| 工具循环恢复 | ✅ T4 ReAct + RECOVERY | ✅ toolLoopRecoveryState | ⚠️ | ❌ |
| 执行中断/重定向 | ✅ 前端可介入 | ✅ turn-interruption | ✅ /interrupt | ⚠️ |
| 回合污染跟踪（taint） | ❌ | 🟢 toolResultTaintsTurn | ❌ | ❌ |
| 终止条件批判定 | ✅ RECOVERY | 🟢 shouldTerminateToolBatch | ❌ | ❌ |

**OpenClaw 唯一我们缺的**: taint 机制（工具结果可"污染"回合, 影响后续判定）——
轻量增益, 可并入执行层 T6 归因。

### B. 工具层

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 工具注册/发现 | ✅ ToolRegistry + discover | ✅ tools | ✅ 40+ tools/toolsets | ✅ 25+ connectors |
| 延迟工具解析 | ✅ resolve + MCP 桥（P1-5） | 🟢 resolveDeferredTool | ⚠️ | ✅ aisuite |
| 调用前校验 | ✅ T2 必填参数 | 🟢 prepareToolCallArguments + validate | ❌ | ✅ |
| 执行前拦截钩子 | ✅ PlanGate（block） | 🟢 beforeToolCall / beforeToolBatch | ⚠️ command approval | ✅ PermissionEngine |
| 工具结果完整回灌 | ✅ T3（summary 进 llm_reply） | 🟢 完整 tool_result 回 messages | ✅ | ✅ |
| 多工具并行批 | ✅ P1-5 parallel 组 | 🟢 顺序回填 + abort 补全 | ❌ | ❌ |
| availability signal | ✅ P1-4（env/config/auth） | ⚠️ 插件可见性 | ⚠️ toolset 门控 | ⚠️ 连接器控制 |
| MCP 客户端 | ✅ P1-5 tool_bridge | ✅ | ✅ | ✅（aisuite MCP） |
| 技能自建自修 | ✅ LEARNED_TEMPLATES（G2） | ✅ skills/plugins | 🟢 skills 系统 + curator | ✅ skills |

**结论**: 工具层我们已与 OpenClaw 对齐（P1-4/P1-5 补齐后）; OpenClaw 的
`beforeToolBatch`（批次级介入）比我们的 PlanGate 多一层"批次批准"——
可吸收为"同一批 tool 调用合并 approve"（对应我们三层介入的中风险批量场景）。

### C. 审批 / 安全介入（OpenWorker 最强域）

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 风险分级 | ✅ P1-2 三层（low/medium/high） | ⚠️ 粗略 | ⚠️ | 🟢 RiskClass 4 级（read/write_local/exec/external） |
| 模式门控 | ⚠️ 三档（smart/whitebox/fullwhite） | ⚠️ | ✅ Plan/Interactive/Auto | 🟢 5 模式（discuss/plan/interactive/auto/custom） |
| 写路径根限制 | ⚠️ Sandbox | ⚠️ | ✅ file_safety | 🟢 多根 + writable 标志 |
| shell 操作符检测 | ❌ | ❌ | ❌ | 🟢 `;`/`\|`/`$(` 等链式命令 → 强制审批 |
| 会话级白名单 | ⚠️ | ❌ | ✅ | 🟢 session_allow_tools/commands |
| 任务级 standing rules | ❌ | ❌ | ❌ | 🟢 `tool → target` 精确目标授权（automation 专属） |
| 无人值守收件箱 | ⚠️ 异步介入概念 | ❌ | ❌ | 🟢 unattended inbox 挂起审批 |

**这是最大差距域**: OpenWorker 的权限引擎（risk.py + permissions.py）在
"可解释、可配置、精确到目标"三个维度全面领先。我们的 P1-2 三层介入是
**概念等价但实现粗**（无 shell 操作符检测、无路径根限制、无 standing rules）。

### D. 蓝图 / 任务编排（OpenWorker 对应最紧）

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| DAG 式任务编排 | 🟢 BlueprintDAG（LLM 生成/模板/沉淀） | ❌ 线性 agent-loop | ❌ | ⚠️ 线性步骤 |
| 计划契约（plan→approve→execute） | ✅ PlanGate checkpoint | ⚠️ | ✅ PLAN mode | ✅ |
| 定时自动化 | ⚠️ 部分（事件调度） | ✅ cron/skills | ✅ cron 调度 | 🟢 Scheduler（catch-up/overlap/standing rules） |
| 自动化=独立持久实体 | ⚠️ | ⚠️ | ✅ | 🟢 ScheduledTask（自有线程/工作区/运行记录） |
| 自动化结果可续跑 | ❌ | ❌ | ⚠️ | 🟢 TaskRun.session 持久续跑 |

**差距**: 我们的蓝图强在**动态生成**（别人都是静态步骤）; 弱在**定时自动化**与
**自动化生命周期**（OpenWorker 的 ScheduledTask/TaskRun 是完整持久实体）。
结合执行层 X 系列（子 agent 直连）+ B2-3（持久化底座）, 可补"自动化=任务地图
持久实例"。

### E. 记忆 / 技能生命周期（Hermes 最强域）

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 持久记忆 | ✅ L5 四区（Hot/Warm/Cold/Archived） | ✅ memory-host | ✅ MEMORY.md/USER.md + FTS5 | ✅ sqlite_store |
| 技能活性状态机 | ❌ | ⚠️ | 🟢 curator（active→stale→archive→prune + reactivate） | ❌ |
| 技能自动合并（LLM umbrella） | ❌ | ❌ | 🟢 consolidate（forked AIAgent review） | ❌ |
| 学习可视化 | ⚠️ 决策事件流 | ⚠️ | 🟢 learning_graph（skill 节点+memory 卡片+边密度） | ❌ |
| 记忆检索（跨会话） | ⚠️ 部分 | ✅ | 🟢 FTS5 + LLM 摘要 + nudge | ⚠️ |
| 用户建模 | ✅ 画像 Track A/B | ⚠️ | ✅ Honcho | ⚠️ |
| 记忆→技能连接 | ❌ | ❌ | 🟢 词法重叠边（learning_graph） | ❌ |

**差距**: 我们 L5 四区已覆盖"分层存储", 但**缺技能生命周期管理**（Hermes curator:
确定性活性裁剪 + 可选的 LLM 合并 + dry-run/备份/报告 = 我们的 LEARNED_TEMPLATES
只增不减）。curator 的"确定性自动迁移（零 LLM）+ 可选 LLM 深化"分治
与我们的 Hot/Warm/Cold 哲学完全同构——高价值吸收。

### E2. 技能蒸馏 — 自查补录（用户追问: "我们没有 skill 蒸馏？"）

**结论: 我们有设计 + 有引擎 + 有哲学, 缺的是"执行层 → 蒸馏引擎"的原料管道。**

| 资产 | 现状 | 证据 |
|------|------|------|
| 蒸馏哲学 A24 逆向动力系统 | ✅ 设计完整（聚类凝练→规则化→反向推导验证 coverage 60-80%; 100%=过拟合, 0%=没学到） | PARADIGM.md A24 |
| A24 工程形态 | ⚠️ **PARADIGM L744 未勾选**: coverage 量化方式、DMN/ECN 调度、启发链存储检索 | PARADIGM.md:744 |
| 蒸馏引擎 DistillationEngine | ✅ 完整实现（9K: scan 四源 constraints/knowledge/behavior/hypotheses → SkillCandidate, 含重叠聚类/序列模式） | planner/distillation_engine.py |
| 蒸馏引擎消费方 | ❌ **零消费方**（仅自身测试 + CLI SkillDistillerAdapter 懒注册, 无数据流接入） | runtime/adapter.py:141 + 全库引用 |
| 执行层学习钩子 | ⚠️ 只有 learn_hook → learn_blueprint（LEARNED_TEMPLATES = DAG 模板沉淀, **不是技能蒸馏**） | blueprint/skill_registry.py:316 |
| A24 域内部分落地 | ✅ 行为链 explicit_commitment.distill_from_graph / 意图 dual_track DerivationCompressor 启发链 / 关联 causal_provenance | 各域实现 |

**差距本质（用户判断成立）**: 不是没有工具——DistillationEngine 就在那里;
是**原料断流**: 执行层跑完的轨迹（EventLog / tool 调用序列 / DAG 快照 / 成败）
从未喂进 DistillationEngine.scan()。这与之前"审计发现的零调用方组件"同型
（组件齐备, 接线断裂）。Hermes 的 curator 是"技能养护"（活性/合并）,
我们的 A24 是"模式→技能蒸馏"（可逆推验证）——两者互补, 都缺。

### F. 元认知 / 学习闭环

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 执行后复盘 | ✅ MetaConsumer + QualityGate（P1 批） | ❌ | ✅ background_review | ❌ |
| 错误模式反思 | ✅ E5/E6（本批） | ❌ | ⚠️ error_classifier | ❌ |
| 偏差归因回流 | ✅ T5/T6（plan/constraint/data/tool） | ⚠️ tool-call-repair | ⚠️ | ❌ |
| 策略权重自适应 | ✅ MetaFeedback degrade/promote | ❌ | ⚠️ | ❌ |
| 微观→宏观仲裁 | 🟢 META_ARBITER（双向纽带） | ❌ | ❌ | ❌ |
| 三层介入 | 🟢 P1-2（本批, 概念领先） | ⚠️ | ⚠️ | ✅（实现细） |
| 用户明示触发反思 | 🟢 E6 | ❌ | ❌ | ❌ |

**结论**: 元认知/仲裁域我们**领先**——三个项目都没有"微观偏差→宏观计划变更"
的仲裁环; Hermes 只有单向的"技能生命周期养护"。这验证了 META_ARBITER 设计
的独特性。我们的短板是把领先概念做粗（见 C 域审批实现粒度）。

### G. 上下文 / 压缩

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 上下文组装 | ✅ ContextAssembler + UnifiedContext | ✅ | ✅ context_engine | ✅ |
| 上下文压缩 | ✅ L2 渐进摘要 + EventBus 生命周期（G2） | ✅ | 🟢 context_compressor（34万行成熟实现） | ✅ compaction |
| 压缩反馈闭环 | ⚠️ | ❌ | 🟢 manual_compression_feedback | ❌ |
| 压缩质量评测 | ❌ | ❌ | ⚠️ | ❌ |

**注意**: Hermes context_compressor.py 34 万字符（8 倍于我们整个 context 域）——
成熟度高。我们的 G2 事件生命周期（热/温/冷）概念更新, 但压缩质量/反馈/评测
维度缺。建议定向吸收 Hermes 压缩反馈机制（manual_compression_feedback）。

### H. 存储

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| SQLite 持久化 | ✅（G10 定案阶段1） | ✅ | ✅ FTS5 | ✅ sqlite_store |
| 向量检索 | ✅ UnifiedStore（BGE+LSH） | ⚠️ | ✅ | ⚠️ |
| 图存储 | ✅ networkx + GraphBackend Protocol | ❌ | ❌ | ❌ |
| 分层存储 | 🟢 TieredStorageManager + L5 四区 | ❌ | ❌ | ❌ |

**结论**: 存储域我们领先（无人有分层 + 向量 + 图三合一）; G10 分层策略已覆盖。

### I. 网关 / 多通道

| 能力 | DialogMesh | OpenClaw | Hermes | OpenWorker |
|------|:---:|:---:|:---:|:---:|
| 多渠道接入 | ⚠️ v6_app + WS | 🟢 WhatsApp/Telegram/Slack/Discord/Signal/iMessage | 🟢 同上 + Home Assistant | ⚠️ Slack/桌面 |
| 消息配对安全 | ⚠️ | 🟢 pairing approve | ✅ DM pairing | ⚠️ |
| 统一网关架构 | ✅ switch 8080 唯一内核（B8-4） | ✅ Gateway 本地控制平面 | ✅ gateway 进程 | ✅ 本地 server |
| 语音/多媒体 | ❌ | ✅ companion apps | ✅ TTS/voice | ✅ STT sidecar |

**差距**: 多渠道（OpenClaw/Hermes 全面）+ 多媒体（语音/相机/屏幕）我们
完全空白——但这符合我们"先后端完备, 后渠道"的施工顺序（阶段 B 之后）。
网关内核（B8-4）已对齐。

---

## 三、差距清单（真差距 → 施工建议）

按价值 × 与现有架构的耦合度排序:

| # | 差距 | 对标来源 | 我们现状 | 建议 | 优先级 |
|---|------|---------|---------|------|:---:|
| GAP-1 | 权限引擎细化（shell 操作符检测/路径根限制/standing rules） | OpenWorker risk+permissions | P1-2 三层概念等价, 实现粗 | 吸收 RiskClass 4 级 + Mode 5 档到 P1-2; 加 `_has_shell_operators` + writable root 校验 | P1 |
| GAP-2 | 技能生命周期管理（active→stale→archive→prune） | Hermes curator | LEARNED_TEMPLATES 只增不减 | 加 SkillLifecycle: 确定性活性裁剪（零 LLM）+ cron 引用保护 + 可选 LLM 合并 + dry-run/报告 | P1 |
| GAP-3 | 定时自动化=持久实体（ScheduledTask/TaskRun 续跑） | OpenWorker scheduler+models | 蓝图无定时层 | 蓝图加"任务地图持久实例": 自有会话/运行记录/standing rules/通知 | P1 |
| GAP-4 | 工具批次级介入（beforeToolBatch） | OpenClaw agent-loop | PlanGate 单节点 | 中风险批量场景合并 approve（对应三层介入中风险批量） | P2 |
| GAP-5 | 压缩反馈闭环（manual_compression_feedback） | Hermes | G2 有生命周期无反馈 | 压缩质量反馈 + 评测维度 | P2 |
| GAP-6 | 回合污染跟踪（taint） | OpenClaw agent-loop | 无 | 工具结果污染标记 → 影响后续判定 | P2 |
| GAP-7 | 多渠道 + 多媒体 | OpenClaw/Hermes | 空白 | 阶段 B 之后（施工顺序决定, 非缺陷） | P3 |

## 四、已验证优势（不因对标而改, 防止为对标丢优势）

1. **元认知仲裁环（微观→宏观双向纽带）** — 三家均无; META_ARBITER 独有。
2. **蓝图 DAG 动态生成 + 模板自增长（LLM_DRIVEN + LEARNED_TEMPLATES）** —
   三家均静态步骤。
3. **存储三合一（分层 + 向量 + 图）** — G10 阶段1 已定案。
4. **三层介入概念（异步日志/PR review/同步 PlanGate）** — 概念领先,
   实现粒度需向 OpenWorker 学（GAP-1）。
5. **错误反思闭环（E5/E6）** — 三家无同类"错误模式→元认知反思"机制。

## 五、数据来源与局限

- README: openclaw/openclaw (111K chars), NousResearch/hermes-agent (17.5K),
  andrewyng/openworker (7.4K) — 2026-08-06 GitHub API 实测。
- 源码精读: OpenWorker risk.py/permissions.py/scheduler.py/automation/models.py
  （权限引擎 + 调度全读）; Hermes learning_graph.py（全读）+ curator.py
  （结构 + 迁移/触发/评审流程）; OpenClaw agent-loop.ts（批处理/校验/终止
  + 并行批全读）。
- 局限: 未读 Hermes context_compressor 全文（34 万字符, 只确认存在与反馈
  机制）; OpenClaw memory-host/plan-gate 路径未定位到文件（README+agent-loop
  证据已覆盖主要结论）; 未做运行时性能对比（仅能力/架构对比）。
- 网络环境: raw.githubusercontent 不可达, 全程走 GitHub API（base64）,
  已保留副本于 C:\tmp（可复查）。
