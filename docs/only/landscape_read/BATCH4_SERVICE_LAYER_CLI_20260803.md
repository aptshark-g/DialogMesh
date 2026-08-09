# 未对应设计文档批量精读 · 批 4 — 服务层 / CLI

> 日期: 2026-08-03 | 批次: 4/8 | 状态: 已读完（5 文档，两个服务层文档为精读核心段）

---

## 1. project/design_service_layer_addon.md（1160 行）— 服务层 v2.3 设计补充

**定位**: 将 PCR + IntentParser 核心引擎封装为可独立部署的工业级微服务（HTTP REST +
WebSocket + 多租户会话隔离 + 持久化）。服务层无状态，只负责 5 件事: 会话生命周期 / 请求
路由与限流 / 状态持久化 / 实时推送 / 多租户隔离。

**架构**: Layer 2 服务层（WS Server + HTTP API + Session Manager + RateLimiter/Queue +
Persistence + Multi-Tenant）→ Layer 1 IntentParser → Layer 0 PCR。

**REST API**: 
```
POST /v1/session/create       （tenant_id/user_id/initial_context/preferred_language）
POST /v1/session/{id}/message （modality: text/structured/image/audio/multimodal +
                               attachments + client_sequence 去重）
POST /v1/session/{id}/clarify （selected_option/free_text；response: resolved/
                               needs_more_clarification/expired）
GET  /v1/session/{id}/history + /status
```
SendMessageResponse.status: actionable / needs_clarification / error / processing；
IntentResult: expectation(TOOL/ADVISOR/COMPANION/UNKNOWN) + task_graph + entities +
cognitive_profile。ClarificationPayload: clarification_id/message/ui_schema/suggestions/
timeout/required。

**WebSocket 协议**: auth( jwt+session_id ) → ping/pong(30s) → message → 服务端推送
（intent_result / clarification / progress / error / taskgraph_update）。v2.4 标准:
EventBuilder 构造 WebSocketEvent（event_type/session_id/payload/timestamp），EventSerializer
序列化，send_text 而非 send_json；新增 state_change 事件（FSM 状态变更推送）与
clarification 事件（含 ClarificationUISchema + 超时）。

**SessionManager**: 内存 LRU(10000) + 持久化双写；idle>5min 异步持久化；TTL 1h 驱逐可恢复；
重启加载最近活跃。Session 结构含 parse_context（实体历史/进程上下文）+ cognitive_profile
（EMA 状态）+ history + state(active/idle/clarifying/closed) + pending_clarification +
ws_connections（仅内存）。

**RateLimiter/RequestQueue**: 双层限流（租户级 10 RPS + 会话级 burst 5）；令牌桶 + 优先
队列（Clarification 回复优先于新消息）+ 背压（队列>100 返回 429）。单会话串行、多会话并行；
单消息 30s 超时降级保守默认。

**持久化抽象**: SessionStore ABC（SQLite 单机 / Redis 集群 TTL / PostgreSQL 关系型）；
三表（sessions/turns/cognitive_profiles）。UserProfileStore: 每 user_id 一条、tenant 隔离、
每 10 轮或会话关闭写一次（避免频繁写）、认知画像版本迁移。

**健康/遥测**: /v1/health（healthy/degraded/unhealthy + components）+ /v1/metrics
（Prometheus: pcr_requests_total / pcr_latency_seconds_bucket 等）。

---

## 2. ENGINEERING_SERVICE_LAYER.md（1521 行）— 服务层工程实现文档

**范围**: 定义服务层完整实现规范（用户交互界面: 接收输入/管理会话/路由消息/返回输出）。
对应 DESIGN_FULL_CONCEPT §5-10（WS/HTTP/连接/路由/认证/编排集成）。

**新增文件清单**（9 个）: websocket_server(~200L)/http_api(~200L)/connection_manager(~150L)/
message_router(~150L)/auth(~100L)/middleware(~100L)/session_manager(~200L)/
response_composer(~150L)/service_adapter(~80L)。

**现有实现评估**（Phase 1-7 已补 ~40%）: WS 基础连接/消息收发/会话管理已补；HTTP 管理接口
部分；认证授权/消息路由/响应编排/并发控制/服务指标**全无**。差距分析: P1 优先（WS 高并发/
/chat /parse /execute 完整逻辑/认证/路由/响应编排/Session 持久化/心跳）+ P2（指标/限流）+
P3（负载均衡）。

**核心交互端点**: 
```
POST /api/v1/chat     → MessageRouter.route_sync → Orchestrator.process → ResponseComposer
POST /api/v1/parse    → parse_only（仅解析不执行，前端预检/第三方）
POST /api/v1/execute  → execute_direct（跳过解析直接执行 TaskGraph，澄清后重执行）
```

**Session 生命周期**: SessionState（ACTIVE/IDLE/CLOSED/ARCHIVED/EXPIRED）；close 生成
SessionSummary（turn_count/duration/final_cognitive_profile）持久化后内存驱逐；tick_ttl
后台每 60s 驱逐过期。

**MessageRouter**: route()（WS 后台 create_task 异步）+ route_sync()（HTTP 同步）+
parse_only() + execute_direct()；DialogRequest 带 trace_id；记录 request_latency_ms/
request_success 指标。

**冲突登记（暂不裁决）**:
- 与两处服务层实现（core/agent/service 17 文件 141.5KB + core/service 12 文件 123.7KB）:
  本设计（v2.3 addon + 1521 行工程规范）与现实现的差距 = 认证/路由/响应编排/限流未落地，
  /chat /parse /execute 为简化实现 → 服务层归一拍板时以哪个蓝图为准。
- 与 service 层活跃消费（frontend/ 被 service/ 真消费）: 澄清 FSM（clarification_fsm 18.2KB）
  与本文档 ClarificationUISchema/state_change 事件 → 接口契约待统一。

---

## 3. DESIGN_CLI_INSPECT.md（166 行）— CLI 状态查看系统

**命令体系**: 15 个 inspect 命令分三类:
```
v4 模块:   inspect observations/hypotheses/knowledge/skills/world/context/store
v3.2 模块: inspect behavior/causal/constraints/discourse/fusion/summary
v3 基础:   inspect store(--tiers/--gc)/pcr(--params/--trace)/topics(--tree)
```

**输出格式（统一文本表格）**: observations（ID/Domain/Summary/Time）；hypotheses（ID/
Statement/Status/Support/Conflict/Stability/Consensus）；knowledge（ID/Statement/Domain/
Score/Frozen）；skills（Name/Domain/Status/Usage/Success Rate）；world --stats（节点数/
社区/骨干节点）；context --last（按 source 分组的 relevance 列表）；store --stats。

**设计原则**: 摘要模式默认 + --detail 钻取（7-dim BeliefState 全量）+ --json + --watch
实时刷新。

---

## 4. DESIGN_CLI_REFERENCE.md（492 行）— CLI 命令大全（27 命令）

**命令总览**: 运行时（start/stop/status/event/health）+ 流水线编排（pipeline create/add/
connect/param/show/list/export/default）+ 查看（inspect 15 个 + --detail/--json/--watch）+
审计（event history/replay）+ 运维（maintenance gc/stats + snapshot list/restore + config
show/set）+ 搜索（search）+ 导出（export knowledge/skills + import skills FUTURE）+ 会话
（session list/show）+ 补全（completion bash/zsh/powershell）。

**关键命令语义**: start 加载 runtime.yaml 实例化适配器；status 四路径统计；event 触发
Async Path；health 全面健康检查（模块可导入性/SQLite/磁盘/Runtime 状态）；pipeline 系列
支持 YAML 导出与默认 v4 DAG 生成。

---

## 5. DESIGN_TUI.md（166 行）— Terminal UI（v4）

**参考框架**: Textual（CSS 布局/异步/DataTable）+ htop（实时刷新/渐变色条）+ k9s（导航式
面板）+ lazygit（Tab 切换/状态颜色）+ bpytop（折叠/鼠标/theme）。

**8 Tab 布局**: Dashboard（四路径吞吐 + 池统计）/ Observations（实时流）/ Hypotheses
（竞争池，7-dim BeliefState 钻取 + freeze/discard）/ Knowledge Vault（evidence trace）/
Skill Forge（blueprint/promote/deprecate）/ World Map（社区/骨干展开）/ Context View /
Event Log。快捷键: F1 Help / F2 Refresh / F3 Trigger Checkpoint / F10 Quit。

**冲突登记（暂不裁决）**:
- CLI 设计与实现（cli/ 40+ 命令已实现，audit 59 处引用）: CLI_REFERENCE/INSPECT/TUI 是
  目标态，现实现覆盖度（p5/p10/inspect/behavior 等命令已存在）与目标差距待盘点。
- CLI 与 RPC 讨论（用户此前问题）: 本文档纯 CLI 视角，无 RPC 迁移规划 → 并入 CLI 架构
  拍板。

---

## 批 4 汇总（冲突登记清单，待哲学统一）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B4-1 | 服务层双蓝图（v2.3 addon vs 1521L 工程规范）与两处实现（core/agent/service + core/service）归一 | 批 4 vs 外围盘点 |
| B4-2 | /chat /parse /execute 简化实现 vs 完整规范（认证/路由/响应编排/限流未落地）| ENGINEERING_SERVICE_LAYER vs service 实现 |
| B4-3 | ClarificationUISchema/state_change 与 clarification_fsm 现实现契约 | 批 4 vs frontend 审计 |
| B4-4 | CLI 目标态（27 命令/TUI 8 Tab）vs 现实现覆盖度 | 批 4 vs cli 审计 |
| B4-5 | CLI vs RPC 架构走向（用户提问遗留）| DESIGN_CLI_REFERENCE vs 架构拍板 |

