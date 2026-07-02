# DialogMesh 服务层 + 前端协议层 + Docker 部署计划

> 目标：将 DialogMesh 从纯库升级为可独立部署的工业级微服务

## 现状
- 核心引擎：PCR + Intent Parser + 编译器 + 话语块树 已完整实现（~6,800行代码，184测试通过）
- 数据模型：core/agent/models.py 已完整定义（Intent, TaskGraph, Ambiguity, ParseResult等）
- 持久化：设计文档已有（design_persistence.md），但 `service/` 目录不存在
- 服务层：设计文档已有（design_service_layer_addon.md v2.3/v2.4），但代码缺失
- 前端协议：设计文档已有，但代码缺失
- Docker：无
- 依赖：FastAPI/uvicorn 在 requirements.txt 中被注释

## 交付物清单

### Phase 1: 基础设施层（服务目录 + 数据模型 + 持久化）
1. `service/models.py` - 服务层数据模型（Session, TurnRecord, SessionSummary等）
2. `service/stores/base.py` - 存储抽象基类
3. `service/stores/async_sqlite.py` - SQLite 异步实现
4. `service/async_session_manager.py` - 异步会话管理器（内存缓存+持久化双写）
5. `service/__init__.py`

### Phase 2: FastAPI 服务层（HTTP + WebSocket）
6. `service/api/schemas.py` - Pydantic Schema（所有请求/响应模型）
7. `service/api/routes.py` - REST API 路由（session, message, clarify, history, health, metrics）
8. `service/api/websocket.py` - WebSocket 连接管理 + 事件推送
9. `service/api/middleware.py` - 限流、认证、跨域、请求日志
10. `service/api/main.py` - FastAPI 应用入口（含生命周期管理）
11. `service/api/__init__.py`

### Phase 3: 前端协议层
12. `service/protocol/ui_schema.py` - Clarification UI 渲染协议（组件、选项、校验）
13. `service/protocol/task_graph.py` - TaskGraph 可视化协议
14. `service/protocol/fsm.py` - Clarification 有限状态机
15. `service/protocol/events.py` - WebSocket 事件标准格式（EventBuilder + EventSerializer）
16. `service/protocol/__init__.py`

### Phase 4: 核心服务逻辑
17. `service/agent_service.py` - AgentService（FSM + 编排器 + 事件推送）
18. `service/orchestrator.py` - 请求编排器（PCR → Intent Parser → 编译器 → 响应构建）
19. `service/__init__.py` - 公共导出

### Phase 5: Docker 部署
20. `Dockerfile` - 多阶段构建（Python 3.11 slim）
21. `docker-compose.yml` - 服务编排（App + 可选Nginx）
22. `.dockerignore` - 排除构建产物
23. `deploy/nginx.conf` - 反向代理 + WebSocket 支持

### Phase 6: 测试与验证
24. `tests/test_service_api.py` - API 路由测试
25. `tests/test_websocket.py` - WebSocket 实时推送测试
26. `tests/test_persistence.py` - 会话持久化测试
27. `tests/test_protocol.py` - 前端协议层测试

### Phase 7: 依赖与配置更新
28. `requirements.txt` - 取消注释 FastAPI/uvicorn/aiosqlite 等必需依赖
29. `config/agent_config.yaml` - 添加服务层配置项
30. `MANIFEST.md` - 更新文件清单

## 关键设计决策

1. **服务层无状态**：所有状态在 SQLite/Redis，FastAPI 可水平扩展
2. **核心引擎单例**：PCR + Intent Parser 作为单例被服务层复用（线程安全）
3. **WebSocket 事件标准**：所有推送通过 EventBuilder 构造标准 WebSocketEvent
4. **渐进式部署**：先单机 SQLite，预留 Redis/PostgreSQL 接口
5. **版本化 API**：/v1/ 前缀，所有数据契约带版本号
6. **零 breaking change**：现有 core/agent/ 代码不修改，只在 service/ 新增

## 质量目标
- 100% 的 API 端点有测试覆盖
- 100% 的 Pydantic Schema 有输入校验
- WebSocket 心跳 30s，自动重连
- 限流：默认 10 RPS/租户，单会话突发 5 条
- 容器镜像 < 500MB
- 启动时间 < 5 秒
