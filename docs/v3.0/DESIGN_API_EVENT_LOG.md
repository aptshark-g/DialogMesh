# DESIGN_API_EVENT_LOG.md -- API 网关 + 事件日志层

> 版本: v1.0 | 日期: 2026-07-13
>
> 为 DialogMesh v4 提供 HTTP API 接口和持久化事件日志。
> Switch (Go) 通过标准 REST 调用接入，EventLog 保证 crash recovery。
> 接口设计队列无关：今天用 SQLite，未来换 Kafka 不改 API 层。

---

## 1. 架构定位

`
Switch (Go API Gateway)
    |
    | HTTP POST /v4/event  (fire and forget)
    v
FastAPI (thin shell, <50 lines)
    |
    | put_event(event)
    v
EventLog (SQLite, append-only)
    | 持久化写入，立即返回 ack
    v
EventBus (内存环形缓冲, 已有)
    |
    v
CognitiveRuntimeEngine (四路径调度)
`

EventLog 是 Switch 和 Runtime 之间的缓冲层。职责：
- **持久化**: Switch 崩溃后 Event 不丢
- **回放**: DialogMesh 重启后从 EventLog 恢复未处理事件
- **审计**: 可查询历史 Event（trace_id、时间、payload）
- **去重**: 幂等写入，防止 Switch 重试产生重复 Event

## 2. API 端点

### POST /v4/event
`
Request:
{
    "event_id": "sw-2026-001",
    "kind": "dialog.message",
    "payload": {"text": "add monitoring", "source": "switch"},
    "trace_id": "trace-abc",      # Switch 侧请求追踪
    "timestamp": 1234567890.123
}

Response (200):
{
    "status": "accepted",
    "event_id": "sw-2026-001"
}
`
规则: 立即写入 EventLog -> 返回 ack -> 异步入 EventBus。

### GET /v4/status
`
Response (200):
{
    "async": {"trigger_count": 42, "success": 38, "failure": 4},
    "slow":  {"trigger_count": 3,  "success": 3,  "failure": 0},
    "deep":  {"trigger_count": 1,  "success": 1,  "failure": 0}
}
`

### GET /v4/inspect/{module}
`
GET /v4/inspect/observations?limit=10
GET /v4/inspect/hypotheses?status=active
GET /v4/inspect/context
`
返回 JSON，结构与 CLI inspect --json 一致。

### POST /v4/checkpoint
`
POST /v4/checkpoint
Response (200):
{
    "status": "completed",
    "results": [{"adapter": "hypothesis_engine", "ok": true}]
}
`
手动触发 Slow Path。

## 3. EventLog (SQLite)

复用 UnifiedGraphStore 的 nodes 表。Event 作为 
ode_type="event" 存入。

`
event_id TEXT PRIMARY KEY  -- 全局唯一
kind TEXT NOT NULL         -- dialog.message | ui.drag | ...
payload TEXT               -- JSON
trace_id TEXT              -- Switch 侧追踪 ID
created_at REAL            -- 写入时间
consumed BOOLEAN DEFAULT 0 -- 是否已被 Runtime 消费
`

写入: INSERT OR IGNORE (幂等，防止重复)。
查询: SELECT * WHERE consumed=0 ORDER BY created_at LIMIT N (回放未消费)。

## 4. 数据流

### 正常流程
1. Switch POST /v4/event
2. API 写入 EventLog (SQLite INSERT)
3. 立即返回 200 ack
4. API 线程调用 engine.on_event(event)
5. Runtime 消费 Event

### Switch 崩溃
1. Switch 重启后查询 GET /v4/status（确认 DialogMesh 存活）
2. Switch 重新发送失败的 Event（相同 event_id）
3. EventLog 幂等去重，不产生重复

### DialogMesh 重启
1. Runtime 启动时从 EventLog 读取 consumed=0 的 Event
2. 按 created_at 顺序回放
3. 标记 consumed=1

### 高吞吐场景 (UDP 或突发)
- EventLog 异步写入，不阻塞 API 返回
- EventBus 背压: buffer 满时丢弃最旧事件，记录 dropped 计数
- 不会丢失: SQLite 已持久化，重启后回放

## 5. 接口与队列无关设计

`
put_event(event)      # 写入持久化日志
ack_event(event_id)   # 标记已消费
replay_unconsumed()   # 回放未消费事件
`

今天实现为 SQLite。未来迁移到 Kafka 时：
- put_event → Kafka producer.send()
- 
eplay_unconsumed → Kafka consumer.poll(from_beginning)
- API 层不变

## 6. 文件规划

`
core/agent/v4/
├── api.py                # FastAPI 路由 (<100 行)
├── api_event_log.py      # EventLog SQLite 实现 (<80 行)

config/
├── api_config.yaml       # API 配置 (端口, CORS, 日志级别)

scripts/
├── serve.py              # uvicorn 启动脚本 (已有, 更新)
`

## 7. 开发顺序

| 优先级 | 组件 | 工作量 |
|:---|:---|:---|
| 1 | EventLog (SQLite) | 小 |
| 2 | FastAPI 路由 (event/status/checkpoint/inspect) | 小 |
| 3 | Switch 侧 provider (Go HTTP client) | Switch 项目 |
| 4 | Kafka adapter (future) | Switch 项目 |

## 8. 快照与备份策略

- SQLite WAL 模式 + 定期快照 (已有 SnapshotManager)
- 默认 24 小时 Event 保留，超出自动清理
- 清理前确保 consumed=1 或超过保留期
