# M7 服务层薄中间件（B4-1）施工记录 — 2026-08-04

> 状态: ✅ 完成。B4-1 全部施工项落地 + 测试全绿。
> 依据: `GLOBAL_PHILOSOPHY_FILTER_FINAL_20260803.md` §九（B4-1 拍板）+
> IMPLEMENTATION_PLAN M7 清单。

---

## 一、施工项完成情况

### B4-1-P1 ✅ v6_app 薄中间件层（rate_limiter/queue/session 挂 FastAPI）
```
新增: core/agent/api/service_middleware.py
  ServiceLayer（轻服务层组件库，惰性单例）:
    - rate_limiter   : core.agent.service.rate_limiter.RateLimiter（双层令牌桶）
    - session_manager: SessionManager（TTL 触达/关闭/持久化）
    - request_queue  : RequestQueue（背压/超时降级）
    - 监控: blocked_429 / saturated_503 / sessions_seen（A18 可观测）
  三个 FastAPI 中间件（纯 ASGI，协议顺序: 限流→背压→会话）:
    - RateLimitMiddleware : 租户+会话双层限流 → 429 + Retry-After
    - QueueGuardMiddleware: 队列深度饱和 → 503 + Retry-After
    - SessionMiddleware   : X-Session-Id → request.state.service_session_id
  /v6/service/* 路由:
    - GET /stats                      监控统计
    - POST /session                   创建会话
    - GET /session/{sid}              状态
    - POST /session/{sid}/close       关闭 + 释放限流桶
接线: core/agent/api/v6_app.py
  install_service_middleware(app) + include_router(service_router)
阈值: DM_SERVICE_TENANT_RPS / SESSION_BURST / QUEUE_MAX / SESSION_TTL /
  TIMEOUT env 可调（默认宽松不破坏直连语义）
```

### B4-1-P2 ✅ core/service/v3_0 归档（test_fullstack 迁移）
```
迁移: scripts/test_fullstack.py → scripts/test_fullstack_v6.py（新建）
  - 走 v6_app（生产唯一入口）+ start_engine mock provider 真数据链
  - 覆盖: health / service 会话 / v3 会话+消息+历史+状态 /
    薄中间件 stats / 限流 429 / 多会话隔离 — 10/10 全绿
归档（Move 到 un_use/，A17 保留）:
  core/service/v3_0/            → un_use/service_v3_0_archived/v3_0/
  scripts/test_fullstack.py     → un_use/service_v3_0_archived/
                                 test_fullstack_v3_archived.py
  service/agent_service.py      → un_use/service_layer_archived/
  service/orchestrator.py       → un_use/service_layer_archived/
  service/api/                  → un_use/service_layer_archived/api/
保留（协议/组件资产, 4 测试消费, B4-1 明确）:
  service/protocol/（fsm/events/ui_schema/task_graph/schemas）
  service/models.py / async_session_manager.py / stores/
  service/__init__.py → 精简为仅导出保留资产
更新:
  scripts/start_dev.py: uvicorn 入口 core.service.v3_0.app_factory
    → core.agent.api.v6_app:app
  core/agent/orchestrator/bootstrap.py:413 注释（指向 v6_app）
```

### 真实缺陷修复（M7 实测发现，非表面测试）
```
① core/agent/service/request_queue.py
   asyncio.PriorityQueue + asyncio.Lock 在构造时绑定事件循环 →
   v6_app 模块级导入（主线程无 loop）直接 RuntimeError。
   修复: 惰性初始化（_ensure_queue 首次 async 调用时创建）。
② core/agent/service/rate_limiter.py
   RateLimiter.check 先扣租户令牌，会话桶拒绝时不退还 →
   无效请求白白耗尽租户配额（会话 A 打满拖垮会话 B）。
   修复: 会话拒绝时退还租户令牌（+1）。
③ core/agent/api/v3_session_api.py:353
   task_graph 在 try 内 Phase 5 才赋值，网关离线走 except 跳过后
   `if task_graph:` UnboundLocalError — 本环境 switch 8080 未运行
   正是常态路径。修复: 防御初始化 task_graph = [] 提到 try 前。
```

---

## 二、验证数字

```
新增测试: core/agent/api/tests/test_service_middleware.py 8/8
  （限流 429+Retry-After / 会话桶独立 / 会话 roundtrip /
    state 归置 / stats / 队列 503 / 中间件次序）
全栈脚本: scripts/test_fullstack_v6.py 10/10（归档替代 v3 版）
回归: M7 核心集 91/91
  （middleware 8 + viz_edit 29 + statemachine_m4 10 + subscribers 8 +
    association_service 21 + funnel 2 + integration 1 +
    event_log_lifecycle 12）
既有协议/组件测试: test_persistence 8 + test_protocol 12 = 20/20
  （test_websocket/test_service_api 22 errors = 预存在缺 app/client
    fixture，归档前后一致，非本批引入）
CLI: 27/28（唯一失败 D-14 归对话树, 预存在）
引擎实测: start_engine running 48/49; v6_app import OK
```

---

## 三、归档/改动清单

```
新增:
  core/agent/api/service_middleware.py
  scripts/test_fullstack_v6.py
  core/agent/api/tests/test_service_middleware.py
改动:
  core/agent/api/v6_app.py             （挂薄中间件 + service 路由）
  core/agent/service/request_queue.py  （惰性队列/锁）
  core/agent/service/rate_limiter.py   （租户令牌退还）
  core/agent/api/v3_session_api.py     （task_graph 防御初始化）
  service/__init__.py                  （精简为资产导出）
  scripts/start_dev.py                 （uvicorn 入口 → v6_app）
  core/agent/orchestrator/bootstrap.py （注释更新）
归档: un_use/service_v3_0_archived/（v3_0 包 + 旧 test_fullstack）
      un_use/service_layer_archived/（agent_service/orchestrator/api）
```
