# DialogMesh v6 — 分布式架构设计 (DESIGN_DISTRIBUTED)

> v1.0 | 2026-07-29
> 从单进程到分布式——3 个阻塞点的插拔升级方案

---

## 一、当前架构拓扑

```
Browser (:5173)
    ↓
Backend (:8000, FastAPI)
    ├── engine singleton (CognitiveRuntimeEngine)
    ├── EventBus (in-memory dict)
    ├── StorageLayer (SQLite + JSON files)
    ├── StateMachine (per-engine, 8 handlers)
    └── PipelineTracer (in-memory buffer)
    ↓
Gateway (:8080, Go) → 9 providers
```

**问题：Backend 是单点。一个进程一个 engine，状态锁在内存里。**

---

## 二、3 个阻塞点 → 3 个升级

### 2.1 Engine 单例 → EnginePool

```
当前:
  get_engine() → 全局单例 _engine
  问题: 多请求共享同一 engine 状态，不可水平扩展

方案: EnginePool (类比线程池)
  ┌─────────────────────────────────┐
  │          EnginePool             │
  │  _engines: List[CognitiveRuntimeEngine]  │
  │  _leased:  Set[engine_id]       │
  │                                 │
  │  lease()  → 返回 engine handle  │
  │  return() → 归还                 │
  │  health() → 检查崩溃/超时       │
  └─────────────────────────────────┘

每个请求 lease 一个 engine → 处理 → return。
共享状态通过 NATS + StorageLayer 同步。
```

**实施量: ~120 行 (修改 get_engine + cli/engine.py)**

### 2.2 EventBus 内存 → NATS

```
当前:
  _publish(kind, payload) → 内存 dict → 6 个 subscriber.handle()

方案: NATS 替换内存 dict
  _publish(kind, payload) → nats.publish("dialogmesh.{kind}", payload)
                                    ↓ (NATS server)
  6 个 subscriber → nats.subscribe("dialogmesh.*") → handle()

已有铺垫:
  - NATSBridge 类存在 (pluggable.py)，支持 connect/publish/subscribe
  - EventBus.subscribe/notify 接口已定义

迁移路径:
  Phase 1: NATS server 启动 (docker run nats -js)
  Phase 2: _publish 改为 NATSBridge.publish
  Phase 3: subscriber 改为 NATSBridge.subscribe
  Phase 4: 保留内存 fallback (NATS 不可用时降级)
```

**实施量: ~80 行 (修改 engine._publish + subscribers.py)**

### 2.3 SQLite → PostgreSQL

```
当前:
  WarmStore(SQLite+WAL) → 单写者
  ColdStore(JSON files)  → 文件锁

方案: PostgreSQL 替换 SQLite + JSON
  WarmStore → PostgreSQL (connection pool, multi-writer)
  ColdStore → PostgreSQL JSONB column (取代 JSON 文件)

已有铺垫:
  - StorageLayer 统一接口 (save/load/query/stats)
  - 所有端点通过 StorageLayer 读写
  - SQLite 和 PostgreSQL 的 SQL 语法高度兼容

迁移路径:
  Phase 1: PostgreSQL docker + 建表
  Phase 2: StorageLayer.backend = "postgresql"
  Phase 3: 数据迁移脚本 (sqlite → pg)
  Phase 4: JSON files → PostgreSQL JSONB
```

**实施量: ~150 行 (新增 PgWarmStore + PgColdStore)**

---

## 三、分布式完整拓扑 (目标)

```
                   ┌──────────────────┐
                   │   NATS Server    │
                   │ (pub/sub + JetStream) │
                   └──────┬───────────┘
                          │
        ┌─────────────────┼─────────────────────┐
        │                 │                      │
   ┌────▼─────┐     ┌────▼─────┐          ┌────▼─────┐
   │ Backend 1│     │ Backend 2│    ...   │ Backend N│
   │ :8001    │     │ :8002    │          │ :800N    │
   │ EnginePool│    │ EnginePool│         │ EnginePool│
   └────┬─────┘     └────┬─────┘          └────┬─────┘
        │                 │                      │
        └─────────────────┼──────────────────────┘
                          │
                   ┌──────▼───────────┐
                   │   PostgreSQL     │
                   │ (Warm + Cold)    │
                   └──────┬───────────┘
                          │
                   ┌──────▼───────────┐
                   │     Redis        │
                   │ (HotStore +      │
                   │  RateLimiter)    │
                   └──────────────────┘
                          │
                   ┌──────▼───────────┐
                   │   Gateway :8080  │
                   │ (Go, 9 providers)│
                   └──────────────────┘
```

**组件职责重新分配:**

| 组件 | 单进程 | 分布式 |
|------|--------|--------|
| **Engine** | 全局单例 | EnginePool per worker |
| **EventBus** | 内存 dict | NATS pub/sub |
| **HotStore** | 内存 dict | Redis (共享) |
| **WarmStore** | SQLite WAL | PostgreSQL |
| **ColdStore** | JSON 文件 | PostgreSQL JSONB |
| **RateGuard** | 内存 TokenBucket | Redis (全局限流) |
| **PipelineTracer** | 内存 buffer | OTel → Jaeger/Prometheus |
| **Gateway** | 独立进程 | 不变 (已独立) |
| **CLI** | 直接调 engine | 不变 (无状态命令) |
| **Frontend** | Vite dev | 不变 (独立进程) |

---

## 四、实施路径 (4 周)

```
Week 1: EnginePool + 多 worker 验证
  → EnginePool class, lease/return/health
  → 4 uvicorn workers × EnginePool(4 engines)
  → 验证: 并发请求不冲突

Week 2: NATS pub/sub
  → NATS server 部署 (docker)
  → _publish 改走 NATSBridge
  → subscriber 注册改为 nats.subscribe
  → 验证: 跨 worker 事件传递

Week 3: PostgreSQL 迁移
  → PostgreSQL docker + 建表
  → PgWarmStore + PgColdStore 实现
  → 数据迁移脚本
  → 验证: 多 worker 读写一致

Week 4: Redis + OTel 完整集成
  → Redis HotStore → 多进程共享
  → Redis RateLimiter → 全局限流
  → OTel → Jaeger 端到端追踪
  → 验证: 完整分布式链路
```

---

## 五、风险 & 降级方案

| 风险 | 概率 | 降级 |
|------|:----:|------|
| NATS 不可用 | 低 | 自动降级到内存 EventBus (已有) |
| PostgreSQL 不可用 | 低 | 降级到 SQLite (已有, WAL 并发读) |
| Redis 不可用 | 低 | HotStore 降级到 engine 本地内存 |
| EnginePool 泄漏 | 中 | lease 超时自动回收 (timeout=30s) |
| NATS 消息丢失 | 低 | JetStream persistent mode |

**核心原则：每个分布式组件都有本地降级方案。分布式是"增强"不是"替代"。**

---

## 六、与 LangGraph/CrewAI 的分布式对比

| | LangGraph | DialogMesh (分布式) |
|---|---|---|
| 状态同步 | Checkpoint API | NATS + StorageLayer |
| 并行执行 | Send API fan-out | EventBus pub/sub + NATS |
| 持久化 | PostgresSaver | PostgreSQL + SQLite fallback |
| 多 agent | Supervisor pattern | 7-Tree + EnginePool (垂直更深) |
| 扩展方式 | LangGraph Cloud (managed) | 自部署 (+ Gateway colocation) |

**我们的优势: 每层都有降级，不锁云厂商，CLI 可直接连分布式后端。**

---

## 七、当前状态 & 下一步

```
当前: 70% design target, 单进程可生产
阻塞: 3 个组件升级即可分布式
路线: 单进程 → docker-compose 多 worker → k8s
```

**不需要重新设计。现有架构的抽象层 (StorageLayer, EventBus, PluggableBridge) 已经为分布式做好了接口。**
