# 开源调研与缺口审查 — 持续待办清单（2026-08-12）

> 目的: 持续扫描开源项目 → 提取可借鉴模式 → 对照 DialogMesh 找缺口
> 方法: 每个项目深读后写"借鉴点 + 我们现状对照 + 缺口分级"，
>       优先吸收 P0 缺口，其余进 backlog。
> 状态: 进行中。已调研: 淘宝 PES 笔记(md_big) / LoopX / Grok Build。

---

## 一、已调研项目（含借鉴点与缺口）

### 1.1 淘宝 GrowBrain + 商品域 Agent（md_big.md，2026-08-12 深读）

```
核心: PES 三段式 (Plan→Execute→Summarize) 替代 ReAct
     + Agent 矩阵分工 + 双 Pipeline 物理隔离 + 决策白盒化 + 小模型可靠性

我们现状对照:
  ✅ PES 已对齐 — 蓝图 DAG=Planning / executor=Execute / llm_reply=Summarize
  ✅ 双 Pipeline — CLI 内核 (B4-5) + v6 REST, 共享能力底座
  ✅ 决策白盒化 — A19 白盒 (决策理由=决策过程附属产物)
  ⚠️ Agent 矩阵分工 — 我们有子 agent 概念 (B2-3) 但无"职责专一子 agent"落地
  ⚠️ 规则信号前置 + LLM 只做基于事实的 CoT — 我们部分有 (结构先验)

缺口 (分级):
  [ ] P1 Agent 矩阵: 职责专一子 agent (潜力预估/流量分配/诊断) 模式
      → 对应我们: 蓝图子图作为职责单元 (B2-3 已定方向, 未工程化)
  [ ] P2 诊断口径与策略口径同源 (诊断结论回流下一轮决策)
      → 我们: 双向归因已做 (计划/约束/数据/工具), 可对齐"诊断→投放→反馈"
  [ ] P3 AB 评测体系 (新桶 vs 老桶召回对比)
      → 我们: 检索消融已做 (parallel_decompose +9.5pp), 可扩展为 AB 框架
```

### 1.2 LoopX（huangruiteng/loopx，⭐4.5K，MIT，2026-08-13 核实）

```
定位: "The open, provider-neutral, stateful control plane for long-running agents"
     — 长时间运行 agent 的状态控制平面
核心概念: objectives / gates / todos / evidence / quota / handoffs
     = 目标、门控、待办、证据、配额、交接 六个稳定状态
     "Keep ... stable while Codex/Claude Code/Cursor/your own runtime
      executes bounded turns" — 外部运行时只执行有界回合

我们现状对照:
  ✅ 目标/门控 — 我们有 PlanGate (A19 审批门) + 蓝图 checkpoint
  ✅ 证据 — decision_bus 事件 (executor.py:794, T4+T5 每步记录)
  ⚠️ todos — 我们有 ExecutionTree 但零消费 (执行轨迹不落树, 已识别 P0)
  ⚠️ quota — 我们有 rate_limit/预算 (网关) 但 agent 级配额没有
  ⚠️ handoffs — 多 agent 交接 (B2-3 子图) 无工程化

缺口 (分级):
  [x] P0 执行轨迹落树: ExecutionTree 接入 T4 (可回放/审计/归因)
      ✅ 2026-08-13 完成: TaskRunner(execution_tree=) — create_task →
      spawn_sub_agent(每步工具) → complete_node(结果摘要); v3_session_api
      + statemachine agentic 节点接线（per-session 树）; 正式测试
      test_execution_trace_lands_in_tree（8/8 绿）
      → LoopX 的 "evidence" 概念印证: 执行证据是控制平面的核心
  [ ] P1 agent 级 quota: 长任务配额 (预算/时间/回合数) 独立于网关限流
  [ ] P1 handoffs 状态化: 子 agent 交接时状态持久化 (LoopX handoffs)
  [ ] P2 objectives 层级化: 目标分解树 (我们蓝图有 DAG, 缺目标-执行映射)
```

### 1.3 Grok Build（xai-org/grok-build，⭐24.9K，Rust，2026-08-13 核实）

```
定位: SpaceXAI 的终端 AI 编码 agent — 全屏 TUI + 理解代码库 + 编辑文件 +
     执行 shell + 网页搜索 + 管理长任务; headless 模式支持脚本/CI;
     通过 Agent Client Protocol (ACP) 嵌入编辑器

可借鉴点:
  ① TUI 交互: 全屏可交互终端 (我们 CLI 是纯文本命令 — TUI 是升级方向)
  ② ACP (Agent Client Protocol): 标准 agent 协议 — 我们 MCP 有雏形,
     ACP 是"编辑器嵌入"方向的补充 (B4-5 传输层可插拔可对齐)
  ③ 长任务管理: grok 管理 long-running tasks — 我们有 run_session (后台会话)
  ④ Rust 实现: 全 Rust — 我们 Rust 只做召回核心 (0.4%), 方向一致但范围小

缺口 (分级):
  [ ] P2 TUI 升级: CLI → 全屏交互 (对比 grok 的交互体验)
      → 或先用现成 TUI 库 (textual/prompter) 做轻量升级
  [ ] P2 ACP 支持: agent 协议嵌入编辑器 (VSCode/JetBrains)
      → 我们 MCP server 已有 (mcp/ 5 文件), 可扩展 ACP
  [ ] P3 Rust 覆盖扩大: 当前 0.4% (召回核心), 可考虑执行路径
```

### 1.4 DeerFlow 2.0（字节，md_big 收录，2026-08-12 深读）

```
核心: 18 层中间件流水线 (AOP before/after 钩子) + Sub-Agent 并发
     (调度池3+执行池3, 最大3并发, 独立上下文, 5s轮询+SSE)

我们现状对照:
  ⚠️ 中间件 — 我们有 middleware 概念 (网关) 但 agent 执行链没有 18 层式清单
  ⚠️ 循环检测 LoopDetection — 我们有"小代价小闭环"哲学 (A16) 但无显式中间件
  ⚠️ 中断工具调用恢复 DanglingToolCall — 我们有 run_session 但无恢复机制
  ⚠️ Sub-Agent 并发池 — B2-3 子图方向, 无工程化

缺口 (分级):
  [ ] P1 执行链中间件清单化: 对照 18 层逐项核查 (哪些已有/缺)
      → 重点: LoopDetection / DanglingToolCall / Clarification 拦截
  [ ] P1 Sub-Agent 并发池: 调度池+执行池 (对齐 DeerFlow 参数: 3/3/15min)
  [ ] P2 上下文摘要中间件: 长上下文 Summarization (我们有 ContextWindow,
      但无自动摘要中间件)
```

### 1.5 小红书（md_big 收录，2026-08-12 深读）

```
核心: 三层记忆 (L1 Context Window / L2 Redis / L3 向量+PG+Neo4j)
     + 三维评分检索 (Recency × Relevance × Importance, 权重可调)

我们现状对照:
  ✅ 三层记忆 — A15 温度系统 (Hot/Warm/Cold/Frozen) 对齐
  ✅ 多维检索 — 五路融合 (BGE+BM25+SPO+HyDE+图) 超出三维
  ⚠️ 权重可调 — 我们温度多因子有, 但"按场景调权重"没显式接口

缺口 (分级):
  [ ] P2 检索权重场景化: recency/relevance/importance 按场景调参接口
      (客服场景 recency 高 / 知识问答 relevance 高 — 我们 A18 自适应可做)
```

### 1.6 腾讯 ClawPro / EDD（md_big 收录，2026-08-12 深读）

```
核心: 评估驱动开发 (EDD): 循环上限+熔断 / Bad Case 闭环测试集 /
     LLM-as-a-Judge 多维打分 / 状态管理外置 Redis

我们现状对照:
  ✅ 循环上限+熔断 — 网关断路器 + 小代价小闭环 (A16)
  ✅ Bad Case 测试集 — 检索 benchmark 39+61=100 评测集
  ⚠️ LLM-as-a-Judge — 无! 工具闭环/回复质量无自动评估
  ⚠️ 状态外置 Redis — 我们 sqlite/本地文件 (G10 阶段1), 分布式时需 Redis

缺口 (分级):
  [ ] P1 LLM-as-a-Judge: 工具闭环 benchmark 的自动评估器
      (相关性/准确性/逻辑性 三维打分 — 正好用于端到端成功率评测)
  [ ] P2 状态外置: G10 阶段 2 时对齐 (触发式, 非现在)
```

---

## 二、待调研队列（backlog，按优先级）

```
[ ] P1 OpenWorker (andrewyng, ⭐11K) — Connector 生命周期 / TurnEngine
    异步循环 / 审批门控 (ASK/ALWAYS_ALLOW/ALWAYS_DENY) — 已读部分, 补全
[ ] P1 OpenClaw (⭐385K) — 工具一等公民 / taint 机制 / 渠道集成
     (对标文档已提 taint 是我们缺口, 深读实现)
[ ] P1 Hermes (Nous) — skills 自增长 / 记忆持久化 / 多通道
     (我们对标过能力矩阵, 深读 skills 机制)
[ ] P2 Anthropic Claude Code — hooks / 子 agent / 许可系统
[ ] P2 Google ADK / JADE — agent 开发套件模式
[ ] P2 LangGraph — checkpoint 持久化 / 流式 / 人类介入模式
[ ] P2 AutoGen / Semantic Kernel — 多 agent 对话协议
[ ] P3 Midscene (web-infra-dev) — UI 自动化 (已列入 deepops 调研)
[ ] P3 UI-TARS-desktop — 完整本地运行 (deepops 阶段 C 已列)
[ ] P3 Microsoft OmniParser v2 — 屏幕解析 (deepops 阶段 C 已列)
```

---

## 三、调研→缺口转化规则

```
1. 每个项目深读后必须产出: 借鉴点 / 我们现状对照 / 缺口分级
2. 缺口分级:
   P0 = 影响核心闭环 (如: 执行轨迹落树 — 行为链/元认知消费前提)
   P1 = 影响能力完整性 (如: LLM-as-a-Judge, 并发池)
   P2 = 增强/体验 (如: TUI, ACP)
   P3 = 未来 (如: Rust 覆盖扩大)
3. 已识别的 P0 优先吸收 (执行轨迹落树), 其余进 backlog
4. 每吸收一个缺口, 更新对应设计文档 (引用来源)
5. 诚实原则: 借鉴 = 模式吸收, 不复制代码; 标注来源
```

---

## 四、已识别 P0/P1 缺口汇总（待施工）

```
P0 (核心闭环):
  [ ] 执行轨迹落树 — T4 每步写 ExecutionTree (可回放/审计/归因)
      → 证据: LoopX evidence 概念 + 淘宝"全链路可回放" + 我们多树设计意图

P1 (能力完整性):
  [ ] LLM-as-a-Judge — 工具闭环/回复自动评估 (腾讯 EDD)
  [ ] Agent 矩阵分工 — 职责专一子 agent (淘宝)
  [ ] 执行链中间件清单化 — 对照 DeerFlow 18 层核查 (LoopDetection 等)
  [ ] Sub-Agent 并发池 — 调度池+执行池 (DeerFlow 参数)
  [ ] agent 级 quota — 长任务配额独立于网关 (LoopX)
  [ ] handoffs 状态化 — 子 agent 交接持久化 (LoopX)

P2 (增强):
  [ ] 检索权重场景化 (小红书) / TUI 升级 (Grok Build) / ACP (Grok Build)
  [ ] AB 评测框架 (淘宝) / 诊断口径回流 (淘宝)

P3 (未来):
  [ ] Rust 覆盖扩大 / 状态外置 Redis (G10 触发)
```

---

## 五、调研记录格式（每项目一节）

```
### X.X <项目名>（<org/repo>，⭐N，<license>，<日期>核实）

定位: 一句话
核心概念: 提炼 2-5 个
我们现状对照: ✅已对齐 / ⚠️部分 / ❌缺口
缺口 (分级): [ ] P? 描述 → 对应我们哪个模块
```
