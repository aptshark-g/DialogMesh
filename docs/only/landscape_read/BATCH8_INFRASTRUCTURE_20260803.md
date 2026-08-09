# 未对应设计文档批量精读 · 批 8 — 跨切面 / 基础设施

> 日期: 2026-08-03 | 批次: 8/8 | 状态: 已读完（9 文档）

---

## 1. DESIGN_DISTRIBUTED.md（221 行）— 分布式架构（v6）

**现状**: Backend(:8000) 是单点——engine singleton + in-memory EventBus + SQLite/JSON +
per-engine StateMachine(8 handlers) + in-memory PipelineTracer；Gateway(:8080 Go) 9 providers。

**3 个阻塞点 → 3 个升级**:
```
① Engine 单例 → EnginePool（多引擎负载）
② 状态锁内存 → 共享状态层（EventLog/存储外置）
③ 单点 → 多副本（Gateway 已有 Go 支持）
```

**冲突登记（暂不裁决）**: 与蓝图 EventBus/DAG 讨论——分布式化是"未来态"，与当前单进程
ES+CQRS（批 2）的效率论证（10 链单进程更快）方向相反 → 单进程优先 vs 分布式准备的
边界待哲学统一（规模触发条件）。

---

## 2. DESIGN_EVENTBUS_V2.md（56 行）— EventBus v2（NATS 模式）

**NATS 模式吸收**: Subject routing（"pcr.completed"→subscriber "pcr.>"）/ Wildcards
（* 单 token，> 全部）/ Queue groups（同 subject 消费者 round-robin）/ Request-reply
（publish(inbox)→await response）。

**本土化适应（关键）**: NATS 默认 slow consumer → drop oldest；**我们 NEVER drop**——
EventLog 持久化 → subscriber 通过 EventLog replay 追赶；队列满时 subscriber catch up；
GC 后来清理旧事件。

**冲突登记（暂不裁决）**: 与批 2 EVENT_SOURCING_CQRS 的 EventBus（环形缓冲 1024 满则丢弃+
标记）**直接矛盾**——V2 设计"NEVER drop"，ES 设计"满则丢弃+EventLog 可重放" → 背压策略
待统一（哲学: 事件不可丢 vs 有限缓冲）。与执行层 X1（NATS 无限重连）同源（NATS 模式吸收
但本地实现未通）。

---

## 3. DESIGN_GATEWAY_V2.md（51 行）— Gateway v2（pingora 模式）

**pingora 模式吸收**: 7 阶段管线（request_filter→upstream_peer→connected→send_request→
response_filter→log→error）/ Connection pool（per-provider keep-alive/idle_timeout/
max_idle）/ Failover（A→B→C max 3）/ Health check（被动失败计数+主动探测）/ Rate limiter
（per-provider TokenBucket via Guard）。

**Provider 选择**: weighted + health。response_filter 加 _provider/_model 元数据。

**冲突登记（暂不裁决）**: 网关是独立 Go 项目（switch/），本文档是 DialogMesh 侧参考——
与 LLM_PROVIDER_GUIDE / provider_manager 的关系待统一（网关 vs 进程内 provider 双路由）。

---

## 4. CONTEXT_COMPRESSION_RESEARCH.md（305 行）— 上下文压缩调研（2025-2026）

**结论**: 原方案（CONTEXT_COMPRESSION_DESIGN）核心架构正确，需引入 3 项改进以适应 4B
小模型约束。

**调研矩阵**:
```
分层/虚拟内存: MemGPT(OS 分页,正确起点) / MemTier(RAS 太复杂) / H-MEM(需改模型) /
              MemoryBank(艾宾浩斯)
压缩策略: StreamingLLM(丢中间=永久丢失,不适合 Agent) / LLMLingua(剪枝 20x) /
          AgentDiet(需第二 LLM,4B 无法承受) / ACON(依赖失败轨迹,冷启动差) /
          Focus(自主压缩决策 s(c)=αr(c)+βn(c)-γa(c),最启发性) /
          SimpleMem(语义流水线,LoCoMo SOTA) / Context-Folding(折叠已完成子任务,10x,
          对 ReAct 最适用)
```

**冲突登记（暂不裁决）**: 与批 2 L5（信息论分治）——本文档是"压缩策略"外部调研，L5 是
内部落地设计；Focus/Context-Folding 等策略与已实现 context/compressor 的差距待对照。

---

## 5. ENGINEERING_V3_3_PREDICTOR.md（573 行）— BehaviorPredictor（S4）

**原则**: LLM 负责提出可能性，四维排序负责判断好坏（LLM+四维排序）。

**边界**: 输入=最近 5 步行为链+画像+图权重；输出=Top-3 候选+期望价值+分解；不负责最终决策。
依赖 ENGINEERING_V3_3_BEHAVIOR_GRAPH。覆盖 LLM 候选生成、四维价值排序、训练闭环、三态回退。

**冲突登记（暂不裁决）**: 与行为链审计（predictor 断链 P0 已修 + DPO 完成）——本文档是
predictor 的 v3.3 算法设计源；现实现（core/agent/predictor）是否覆盖"四维排序"待对照。

---

## 6. ENGINEERING_V3_3_REWARDER.md（587 行）— BehaviorRewarder（S5）

**原则**: reward 不直接修改边权重，通过 EMA 权重更新器间接影响。**区分信号与噪声是核心**。

**边界**: 输入=TrainingSignal+用户反馈；输出=RewardSignal+ABLReflection；权重更新由
WeightUpdater 负责（rewarder 不直接改边）。覆盖奖励规则表、时间衰减因子、噪声自适应策略、
ABL 反思向量、会话级全局衰减。

**冲突登记（暂不裁决）**: 与行为链审计（rewarder 独立无断链可先单独改）——reward_signal
双轨方案（批 2 前序讨论: 步长/冷却复用 RFC + DeltaAdjuster）与本文档的 EMA/ABL 反思
的关系待统一。

---

## 7. LLM_PROVIDER_GUIDE.md（224 行）— LLM Provider 配置指南

**Provider 类型**: OpenAIProvider（云端+兼容端点: OpenAI/Kimi/DeepSeek/Qwen/AnyScale/LM
Studio，max_retries=2/timeout=30s）/ LocalProvider（本地 HTTP）/ HybridRouter（成本优化+
降级保障）/ MockProvider（测试）。含配置参数、使用场景、故障排查。

**冲突登记（暂不裁决）**: 与 llm_providers/（139.5KB 零测试，LLM 认知层审计）——指南是
用户文档，实现已有；走网关 vs 直连（用户拍板遗留）在此未决。

---

## 8. MCP_DEPLOYMENT_BOUNDARY.md（161 行）— MCP 依赖边界声明

**核心**: MCP 是**可选扩展层**，不是核心依赖。核心能力（无 MCP 可完整运行）: PCR/意图
解析/多轮澄清/任务图/会话/限流审计/认知编译器/话题树/窗口管理/7 内置工具/HTTP API/配置。

**冲突登记（暂不裁决）**: 与 mcp/ 包（mcp/server + security + tests 活跃）——边界声明
与实际 mcp 实现是否一致待对照（工业评估见下）。

---

## 9. mcp_industrial_assessment.md（304 行）— MCP 工业化评估报告

**生态成熟度**: 完全可用——Python SDK v1.x 稳定 + FastMCP（@mcp.tool 20 行暴露工具）+
3 传输（stdio/SSE/Streamable HTTP）+ 月下载 97M+（2026-05），ChatGPT/Claude/Cursor/Gemini/
Copilot 全支持。MCP Server（暴露内部工具）+ MCP Client（连接外部工具）双角色。

**冲突登记（暂不裁决）**: 评估结论"MCP 可用"vs 现状 mcp 审计（MCP 层活跃）——MCP 扩展
策略（Server 暴露哪些内部工具 / Client 接哪些外部工具）待拍板。

---

## 批 8 汇总（冲突登记清单）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B8-1 | 分布式未来态 vs 单进程 ES+CQRS 效率论证 | 批 8 vs 批 2 |
| B8-2 | EventBus v2 NEVER drop vs ES 环形缓冲满则丢弃（背压矛盾）| 批 8 vs 批 2 |
| B8-3 | NATS 模式吸收 vs X1 NATS 无限重连（本地实现未通）| 批 8 vs 执行层 X1 |
| B8-4 | 网关 vs 进程内 provider 双路由 | 批 8 vs LLM 认知层 |
| B8-5 | 压缩调研策略 vs L5 落地 + context/compressor | 批 8 vs 批 2 + 上下文审计 |
| B8-6 | predictor 四维排序 vs 现实现覆盖度 | 批 8 vs 行为链审计 |
| B8-7 | rewarder EMA/ABL vs reward_signal 双轨方案 | 批 8 vs 行为链拍板 |
| B8-8 | MCP 边界声明 vs 实际 mcp 实现一致性 | 批 8 vs mcp 审计 |

