# DialogMesh 项目清单（v3.0）

> 本文档记录 `DialogMesh/` 目录下 v3.0 版本所有核心文件及其职责。
> 生成时间：2026-07-03

---

## 目录总览

```
DialogMesh/
├── main_v3.py                          # 服务入口点
├── core/
│   ├── agent/v3_0/                     # 认知层核心
│   └── service/v3_0/                   # 服务层
├── config/                             # 配置文件
├── docs/v3.0/                          # 设计文档（v3.0）
├── tests/                              # 集成测试
├── requirements.txt                    # Python 依赖
├── pyproject.toml                      # 项目配置
├── README.md                           # 项目说明（中文）
├── README_EN.md                        # 项目说明（英文）
├── MANIFEST.md                         # 本文件
├── CONTRIBUTING.md                     # 贡献指南
└── CHANGELOG.md                        # 变更日志
```

---

## 服务入口

| 文件 | 职责 |
|------|------|
| `main_v3.py` | 系统启动入口：加载配置、初始化服务、启动 FastAPI + WebSocket 服务器 |

---

## 认知层（core/agent/v3_0/）

### 认知树（cognitive_tree/）

> 认知树（Cognitive Tree）与主题树（Topic Tree）的双树结构实现，支持节点/边生命周期、访问控制、事务性写入。

| 文件 | 职责 |
|------|------|
| `cognitive_tree/manager.py` | 树管理器：节点创建、边连接、生命周期状态转换、事务管理 |
| `cognitive_tree/models.py` | 数据模型：CognitiveNode、CognitiveEdge、TopicNode、TopicEdge、访问控制令牌 |
| `cognitive_tree/cross_ref.py` | 跨引用导航：节点间语义关联、反向引用、引用链追踪 |
| `cognitive_tree/tests/test_cognitive_tree.py` | 单元测试：生命周期、事务写入、RBAC、跨引用 |

### 认知编译器（cognitive_compiler/）

> 认知编译器将用户输入编译为认知图结构，驱动六层 LLM 协同激活。

| 文件 | 职责 |
|------|------|
| `cognitive_compiler/compiler.py` | 编译主入口：输入 → 认知图 → 执行计划 |
| `cognitive_compiler/edge_manager.py` | 边生命周期管理：创建、激活、冷却、归档、垃圾回收 |
| `cognitive_compiler/access_control.py` | 访问控制：基于角色的节点读写权限验证 |
| `cognitive_compiler/lifecycle.py` | 节点生命周期状态机：ACTIVE → COOLING → COLD → ARCHIVED |
| `cognitive_compiler/event_bus.py` | 认知事件总线：发布-订阅模式的事件分发 |
| `cognitive_compiler/querier.py` | 认知查询引擎：节点查询、路径搜索、关联分析 |

### LLM 提供商适配层（llm_providers/）

> 统一 LLM 适配层，支持多模型并发、故障转移、熔断、流式响应。

| 文件 | 职责 |
|------|------|
| `llm_providers/provider_manager.py` | ProviderManager：统一入口，模型注册与调度 |
| `llm_providers/base.py` | 抽象基类：BaseProvider、BaseStreamingProvider |
| `llm_providers/openai_provider.py` | OpenAI / DeepSeek 兼容 API 适配 |
| `llm_providers/local_provider.py` | 本地模型适配：LMStudio、Ollama |
| `llm_providers/failover_provider.py` | 故障转移：主模型失败时自动切换备用 |
| `llm_providers/hybrid_router.py` | 混合路由：根据查询复杂度选择最优模型 |
| `llm_providers/mock_provider.py` | Mock Provider：测试用确定性响应 |
| `llm_providers/circuit_breaker.py` | 熔断器：连续失败时快速失败、自动恢复 |
| `llm_providers/streaming.py` | 流式响应处理：SSE 格式、令牌计数、断点续传 |
| `llm_providers/models.py` | LLM 请求/响应数据模型 |
| `llm_providers/tests/test_base.py` | 单元测试：Provider 基类、熔断、流式 |

### 上下文管理（context_manager/）

> 多轮对话上下文管理：窗口管理、优先级组装、存储与恢复。

| 文件 | 职责 |
|------|------|
| `context_manager/manager.py` | 上下文管理器：热/温/冷三级缓存组装 |
| `context_manager/window.py` | 上下文窗口：Token 计数、滑动窗口、优先级截断 |
| `context_manager/store.py` | 上下文存储：SQLite 持久化、序列化/反序列化 |
| `context_manager/models.py` | 上下文数据模型：ContextBlock、TurnContext、SessionContext |
| `context_manager/tests/test_context_manager.py` | 单元测试：窗口管理、存储、组装 |

### 规划 Skill 层（planning/）

> 5 核心规划原语、SkillLevel 三级详细度、模式回退链。

| 文件 | 职责 |
|------|------|
| `planning/planner.py` | 规划器主入口：任务 → 规划图 → 执行计划 |
| `planning/skill_engine.py` | Skill 执行引擎：原语调度、状态跟踪、结果收集 |
| `planning/skill_registry.py` | Skill 注册表：5 核心原语注册与元数据管理 |
| `planning/skill_matcher.py` | Skill 匹配器：任务 → 最佳 Skill 映射 |
| `planning/decomposition.py` | 任务分解：递归分解、粒度控制、边界检测 |
| `planning/dependency_resolver.py` | 依赖解析：任务间依赖图、拓扑排序、并行检测 |
| `planning/scheduler.py` | 执行调度器：优先级队列、时间片、并发控制 |
| `planning/optimizer.py` | 规划优化：执行计划剪枝、合并、重排序 |
| `planning/fallback.py` | 模式回退链：ToT → DivideConquer → 单步执行 |
| `planning/strategy_selector.py` | 策略选择器：基于任务特征选择最优规划策略 |
| `planning/agent_allocator.py` | Agent 分配：六层 LLM 实例的任务分配与负载均衡 |
| `planning/models.py` | 规划数据模型：PlanNode、SkillInvocation、ExecutionTrace |
| `planning/__init__.py` | 规划层公共接口导出 |
| `planning/tests/test_planning.py` | 单元测试：规划器、Skill 执行、分解、回退 |

### 工具注册与绑定（tool_registry/）

> SchemaGuard + ToolBindingEngine 参数兼容性检查与工具生命周期管理。

| 文件 | 职责 |
|------|------|
| `tool_registry/registry.py` | 工具注册表：Schema 注册、版本管理、命名空间 |
| `tool_registry/binding.py` | ToolBindingEngine：参数绑定、类型转换、默认值填充 |
| `tool_registry/executor.py` | 工具执行器：异步执行、超时控制、结果封装 |
| `tool_registry/permission.py` | 权限控制：工具级别 RBAC、调用权限验证 |
| `tool_registry/discovery.py` | 工具发现：自动扫描、元数据提取、注册 |
| `tool_registry/shortlister.py` | 工具短列表：基于意图的工具相关性排序 |
| `tool_registry/models.py` | 工具数据模型：ToolSchema、ToolBinding、ToolResult |
| `tool_registry/tests/test_tool_registry.py` | 单元测试：注册、绑定、执行、权限 |

### 可观测性（observability/）

> 六维可观测性：指标、日志、追踪、告警、面板、遥测。

| 文件 | 职责 |
|------|------|
| `observability/metrics.py` | 指标采集：Prometheus 兼容格式、Counter/Gauge/Histogram |
| `observability/logger.py` | 结构化日志：JSON 格式、多级过滤、上下文注入 |
| `observability/tracer.py` | 分布式追踪：Span、Trace、调用链可视化 |
| `observability/alert.py` | 告警系统：阈值规则、告警级别、通知通道 |
| `observability/dashboard.py` | 诊断面板：实时指标可视化、系统状态总览 |
| `observability/telemetry.py` | 遥测聚合：数据聚合、批量导出、采样策略 |
| `observability/store.py` | 可观测数据存储：时序数据、日志索引、追踪归档 |
| `observability/models.py` | 可观测性数据模型：Metric、LogEntry、Span、Alert |
| `observability/tests/test_observability.py` | 单元测试：指标、日志、追踪、告警 |

### 编排器（orchestrator/）

> 六层 LLM 认知协同的中央编排器。

| 文件 | 职责 |
|------|------|
| `orchestrator/orchestrator.py` | 主编排器：6 LLM 实例级联激活、认知双工调度、Fusion Engine 融合 |
| `orchestrator/bootstrap.py` | 运行时启动：LLM 实例初始化、认知树加载、状态恢复 |
| `orchestrator/models.py` | 编排数据模型：CognitiveState、OrchestrationResult、LLMInvocation |
| `orchestrator/tests/test_orchestrator.py` | 单元测试：级联激活、融合决策、错误恢复 |

### 系统启动与全局模块

| 文件 | 职责 |
|------|------|
| `system_bootstrap.py` | 系统启动入口：配置加载、依赖注入、健康检查 |
| `orchestrator.py` | 编排器兼容入口（向后兼容） |
| `data_models.py` | 全局数据模型：跨模块共享的 Pydantic 模型 |
| `__init__.py` | v3.0 包公共接口导出 |

---

## 服务层（core/service/v3_0/）

> FastAPI + WebSocket 异步服务层，支持 4 种响应格式。

| 文件 | 职责 |
|------|------|
| `service/v3_0/api.py` | FastAPI 路由：HTTP API 端点定义、请求验证、响应序列化 |
| `service/v3_0/agent_service.py` | Agent 业务逻辑：对话处理、状态管理、结果封装 |
| `service/v3_0/session_manager.py` | 会话管理：多会话并发、状态隔离、超时清理、持久化恢复 |
| `service/v3_0/websocket_manager.py` | WebSocket 连接管理：连接池、心跳、消息广播、断线重连 |
| `service/v3_0/response_composer.py` | 响应合成器：BRIEF/BALANCED/EXPLANATORY/TUTORIAL 格式生成 |
| `service/v3_0/app_factory.py` | 应用工厂：FastAPI 应用创建、中间件注册、依赖注入 |
| `service/v3_0/middleware.py` | 中间件：请求日志、超时控制、限流、CORS、错误处理 |
| `service/v3_0/data_models.py` | 服务数据模型：API 请求/响应、会话、WebSocket 消息 |
| `service/v3_0/tests/test_service.py` | 单元测试：API、WebSocket、会话、响应格式 |
| `service/v3_0/__init__.py` | 服务层公共接口导出 |

---

## 配置（config/）

| 文件 | 职责 | 是否纳入版本控制 |
|------|------|------------------|
| `config/agent_config.yaml` | 默认配置：阈值、窗口大小、模型参数、Skill 默认行为 | ✅ |
| `config/user_config.yaml` | 用户配置：API Key、模型偏好、个性化设置 | ❌（含密钥） |
| `config/user_config.yaml.example` | 用户配置示例（带注释） | ✅ |
| `config/expertise_lexicon.yaml` | 领域词汇表：技术术语、领域关键词 | ✅ |

---

## 设计文档（docs/v3.0/）

### 架构设计文档（DESIGN_*.md）

| 文件 | 说明 |
|------|------|
| `docs/v3.0/DESIGN_FULL_CONCEPT.md` | 总体架构设计：系统目标、设计哲学、模块划分 |
| `docs/v3.0/DESIGN_MULTILAYER_LLM_COGNITIVE.md` | 多层 LLM 认知设计：6 LLM 实例分工、级联协议、认知双工 |
| `docs/v3.0/DESIGN_PLANNING_SKILL_LAYER.md` | 规划 Skill 层设计：5 原语、SkillLevel、回退链、分解算法 |
| `docs/v3.0/DESIGN_TASK_PLANNING_DYNAMIC.md` | 动态任务规划设计：运行时规划调整、自适应重规划 |

### 工程实现文档（ENGINEERING_*.md）

| 文件 | 说明 |
|------|------|
| `docs/v3.0/ENGINEERING_COGNITIVE_COMPILER.md` | 认知编译器工程实现 |
| `docs/v3.0/ENGINEERING_COGNITIVE_PROFILE_V2.md` | 认知画像 V2 工程实现 |
| `docs/v3.0/ENGINEERING_CONTEXT_MANAGER.md` | 上下文管理器工程实现 |
| `docs/v3.0/ENGINEERING_DATA_MODEL.md` | 数据模型工程实现 |
| `docs/v3.0/ENGINEERING_INTEGRATION.md` | 系统集成工程实现 |
| `docs/v3.0/ENGINEERING_INTENT_PARSER.md` | 意图解析器工程实现 |
| `docs/v3.0/ENGINEERING_LLM_PROVIDERS.md` | LLM 提供商工程实现 |
| `docs/v3.0/ENGINEERING_MULTILAYER_LLM.md` | 多层 LLM 工程实现 |
| `docs/v3.0/ENGINEERING_OBSERVABILITY.md` | 可观测性工程实现 |
| `docs/v3.0/ENGINEERING_PCR.md` | PCR 协议兼容层工程实现 |
| `docs/v3.0/ENGINEERING_PERSISTENCE.md` | 持久化层工程实现 |
| `docs/v3.0/ENGINEERING_PLANNING_SKILL.md` | 规划 Skill 工程实现 |
| `docs/v3.0/ENGINEERING_SERVICE_LAYER.md` | 服务层工程实现 |
| `docs/v3.0/ENGINEERING_API_DOC_PREPROCESSOR.md` | API 文档预处理器工程实现 |
| `docs/v3.0/ENGINEERING_TOOL_REGISTRY.md` | 工具注册工程实现 |
| `docs/v3.0/ENGINEERING_TOPIC_TREE.md` | 主题树工程实现 |

### 设计审查文档（REVIEW_*.md）

| 文件 | 说明 |
|------|------|
| `docs/v3.0/REVIEW_FULL_CONCEPT_ENGINEERING.md` | 总体架构设计审查 |
| `docs/v3.0/REVIEW_MULTILAYER_LLM_CHECK.md` | 多层 LLM 设计审查 |
| `docs/v3.0/REVIEW_PLANNING_DESIGN_ENGINEERING.md` | 规划层设计审查 |

### 其他研究文档

| 文件 | 说明 |
|------|------|
| `docs/v3.0/LITERATURE_REVIEW_COGNITIVE_PROFILE_V2.md` | 认知画像文献综述 |
| `docs/v3.0/LITERATURE_REF_DISCOURSE_BLOCK_TREE.md` | 话语块树文献参考 |
| `docs/v3.0/CONTEXT_COMPRESSION_RESEARCH.md` | 上下文压缩研究 |
| `docs/v3.0/CONTEXT_COMPRESSION_DESIGN.md` | 上下文压缩设计 |
| `docs/v3.0/ARCHITECTURE_AUDIT_9_ISSUES.md` | 架构审计 9 项问题 |
| `docs/v3.0/EVALUATION_as_frontend_agent.md` | 前端代理评估 |
| `docs/v3.0/mcp_industrial_assessment.md` | MCP 工业评估 |
| `docs/v3.0/Context-Agent_vs_MemoryGraph_TopicTree_Deep_Dive.md` | Context-Agent vs TopicTree 深度分析 |
| `docs/v3.0/README.md` | docs/v3.0 目录说明 |

---

## 测试状态

| 测试模块 | 文件 | 说明 |
|----------|------|------|
| 认知树 | `core/agent/v3_0/cognitive_tree/tests/` | 节点/边生命周期、事务、RBAC |
| 认知编译器 | `core/agent/v3_0/cognitive_compiler/` | 编译、边管理、事件总线 |
| LLM 提供商 | `core/agent/v3_0/llm_providers/tests/` | Provider、熔断、流式 |
| 上下文管理 | `core/agent/v3_0/context_manager/tests/` | 窗口、存储、组装 |
| 规划 Skill | `core/agent/v3_0/planning/tests/` | 规划器、Skill、分解、回退 |
| 工具注册 | `core/agent/v3_0/tool_registry/tests/` | 注册、绑定、执行、权限 |
| 可观测性 | `core/agent/v3_0/observability/tests/` | 指标、日志、追踪、告警 |
| 编排器 | `core/agent/v3_0/orchestrator/tests/` | 级联激活、融合、恢复 |
| 服务层 | `core/service/v3_0/tests/` | API、WebSocket、会话、响应 |

**总计：327 个测试用例，全部通过。**

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-02 | **v3.0.0 发布**：多层 LLM 认知架构、认知双工、双树结构、规划 Skill 层、327 测试 |
| 2026-06-28 | v0.2.0：工业级重构，编译器三阶段管道，9 维 cohesion 量化 |
| 2026-06-15 | v0.1.0：MVP，端到端意图解析器，基础对话管理 |

---

## 相关文档

- [README.md](README.md) — 项目说明（中文）
- [README_EN.md](README_EN.md) — 项目说明（英文）
- [CONTRIBUTING.md](CONTRIBUTING.md) — 贡献指南
- [CHANGELOG.md](CHANGELOG.md) — 变更日志
