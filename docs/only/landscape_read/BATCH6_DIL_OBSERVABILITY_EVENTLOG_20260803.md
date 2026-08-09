# 未对应设计文档批量精读 · 批 6 — 文档摄入 / 可观测性 / 事件日志

> 日期: 2026-08-03 | 批次: 6/8 | 状态: 已读完（3 文档；observability 1230 行为精读核心段）

---

## 1. DESIGN_DOCUMENT_INGESTION_LAYER.md（430 行）— 文档摄入层（DIL, v4.1）

**问题**: v4 认知链（EventIR→ObservationCompiler→ObservationPool→HypothesisEngine→
Knowledge→Skill）只能处理"已进入系统的信息"，外部文档（MD/PDF/代码/网页）未被转换成
"认知对象"。

**传统 RAG 为什么不够**: RAG 目标="用户问什么返回哪段文本"（chunk）；v4 需要="这段文本在
知识体系里是什么角色"（结构化 Observation）；RAG 输出文本块 / v4 需要概念关系、约束、流程；
RAG 静态索引 / v4 需要可竞争、可冻结、可蒸馏；RAG 无认知 / v4 需支持 Hypothesis 验证。

**核心洞察**: "文档不是事件流，而是静态知识场（Knowledge Field）。对话树=动态事件树
（按时间产生）；文档树=静态结构树（一次性存在）。但它们都可以生成 Observation——v4
需要的是让块状外部知识进入认知链的入口。"

**冲突登记（暂不裁决）**:
- 与 document/ 包（52KB 活跃，document/pipeline → ObservationPool 真接线）: DIL 是文档摄入
  的设计源，现实现已有 document/pipeline + extractor + parsers + tree（chunking 消费）→
  半实现（结构化 Observation 转化 vs 现状的 DocumentObservationBundle）。
- 与 L5/批2（静态知识场 vs 压缩分治）: 文档树=静态结构树，与 L5 四区存储的 Archived 区
  关系待统一。

---

## 2. design_observability.md（1230 行）— 可观测性设计 v1.0

**问题**: 当前"黑盒运行、无法量化质量"（纯文本 print 输出，无法分析"为什么这次解析错了"/
澄清率是否恶化/延迟瓶颈/降级无感知/A-B 实验无法量化）。

**三层观测架构**: 结构化日志（StructuredLogger）+ 实时指标聚合（MetricsAggregator）+
质量告警（AlertEngine）+ 文本仪表盘（CLI）。关键组件、日志规范、指标与告警、仪表盘设计、
与 CLI 集成、测试策略、风险与回退。

**冲突登记（暂不裁决）**:
- 与 observability/ 包（活跃: metrics/telemetry/logger 真接线，behavior/ 等消费）:
  设计是意图识别引擎视角，现状已是跨模块 observability → 已演进，设计文档本体未引用。
- 与批 1 CognitiveScheduler Monitor/Runtime Advisor: 两套监控（可观测性三层 vs 调度器
  Monitor）关系待统一。

---

## 3. DESIGN_API_EVENT_LOG.md（169 行）— API 网关 + 事件日志层（v1.0）

**架构**: Switch (Go API Gateway) → HTTP POST /v4/event（fire and forget）→ FastAPI
（thin shell <50 行）→ put_event → EventLog（SQLite append-only，立即返回 ack）→ EventBus
（内存环形缓冲）→ CognitiveRuntimeEngine（四路径调度）。

**EventLog 职责**: 持久化（Switch 崩溃不丢）/ 回放（重启恢复未处理事件）/ 审计（查询
trace_id/time/payload）/ 去重（幂等写入，防 Switch 重试重复）。接口设计队列无关：
今天 SQLite，未来换 Kafka 不改 API 层。

**冲突登记（暂不裁决）**:
- 与 Event Sourcing CQRS（批 2）: 本文档是 ES 的雏形（EventLog 缓冲层），EVENT_SOURCING_CQRS
  是其完整化 → 同一演进链，归一待拍板。
- 与执行层 X1（NATS 无限重连）: EventBus"已有"的假设在 X1 处不成立（NATS 未通）→
  基础设施真实现状待修。

---

## 批 6 汇总（冲突登记清单）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B6-1 | DIL 结构化 Observation vs document/ 现状半实现 | 批 6 vs 外围盘点 |
| B6-2 | 文档树静态场 vs L5 四区存储（Archived 区）| 批 6 vs 批 2 |
| B6-3 | 可观测性三层 vs 调度器 Monitor（两套监控）| 批 6 vs 批 1 |
| B6-4 | EventLog 雏形 vs ES+CQRS 完整蓝图 | 批 6 vs 批 2 |
| B6-5 | EventBus"已有"假设 vs NATS 未通现实 | 批 6 vs 执行层 X1 |

