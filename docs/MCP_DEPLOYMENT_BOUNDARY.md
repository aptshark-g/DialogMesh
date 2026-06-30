# MCP 依赖边界声明

> 文档版本：v1.0
> 适用版本：MemoryGraph Agent v2.5+

## 概述

MCP（Model Context Protocol）是 MemoryGraph Agent 的**可选扩展层**，不是核心依赖。

**核心能力（无 MCP 也可完整运行）** 与 **扩展能力（需要 MCP）** 的边界如下。

---

## 核心能力（无 MCP 依赖）

以下模块和功能**完全不依赖** MCP 包，在无 MCP 环境下可完整运行：

| 能力 | 模块 | 说明 |
|------|------|------|
| 意图识别（PCR） | `core.agent.pcr.rule_based` | RuleBasedPCR + 21 条规则 |
| 意图解析 | `core.agent.intent_parser` | 实体提取、歧义检测、任务图构建 |
| 多轮澄清 | `core.agent.frontend.clarification_fsm` | FSM 7 状态管理 |
| 任务图可视化 | `core.agent.frontend.taskgraph_viz` | 节点/边/拓扑排序 |
| 会话管理 | `core.agent.service.session_manager` | 内存 + SQLite/Redis 持久化 |
| 限流与审计 | `core.agent.service.rate_limiter` / `audit_logger` | 令牌桶 + 日志 |
| 认知编译器 | `core.agent.cognitive_compiler` | Fast/Full/Hybrid 三模式 |
| 话题树 | `core.agent.topic_tree` | 路由决策 + 图遍历 + 持久化 |
| 窗口管理 | `core.agent.window` / `core.agent.context_window` | 批量压缩 + 增量管理 |
| 内置工具 | `core.agent.tools.cognitive_tools` | 7 个核心工具（scan_memory, read_memory, write_memory, ...） |
| HTTP API | `core.agent.service.api` | 8 端点 + WebSocket + Prometheus |
| 配置管理 | `core.agent.config` | YAML 配置 + 单例访问 |

---

## 扩展能力（需要 MCP）

以下功能**仅在 MCP 包安装且 MCP 客户端/服务端配置正确时**可用：

| 能力 | 模块 | 说明 | 依赖 |
|------|------|------|------|
| 外部工具调用 | `core.agent.mcp.client` | 消费外部 MCP Server 的工具（如数据库查询、代码执行） | `mcp` 包 + 外部 Server |
| Claude Desktop 集成 | `core.agent.mcp.server` | 作为 MCP Server 被 Claude Desktop 消费 | `mcp` 包 + Claude Desktop |
| 工具安全层 | `core.agent.mcp.security` | 路径守卫、鉴权、审计、敏感信息脱敏 | `mcp` 包 |

### 优雅降级

当 `mcp` 包未安装时（`HAS_MCP = False`）：
- `MCPClientAdapter.connect()` → 返回 `False`
- `MCPClientManager` → 所有方法返回空列表/空字典
- `create_mcp_server()` → 返回 `None`
- 核心引擎完全不受影响

---

## 部署矩阵

### 最小部署（单机/无外部依赖）

```bash
pip install -e .
# 或
pip install cognitive-router
```

- 包含：全部核心能力
- 不包含：MCP 扩展能力
- 适用：个人开发、单机测试、无需外部工具调用

### 标准部署（含 MCP 协议层）

```bash
pip install -e .[mcp]
# 或
pip install cognitive-router[mcp]
```

- 包含：核心能力 + MCP 客户端/服务端协议层
- 需要：用户自行配置外部 MCP Server（如文件系统、数据库、代码执行）
- 适用：需要消费外部工具的团队部署

### 完整部署（Claude Desktop 集成）

```bash
pip install -e .[server,mcp]
# 或
pip install cognitive-router[server,mcp]
```

- 包含：核心能力 + MCP Server 暴露 + Claude Desktop 集成
- 需要：Claude Desktop 配置 MCP Server URL
- 适用：与 Claude Desktop 联用的开发者

---

## 环境变量配置

| 变量 | 说明 | 默认值 | 适用部署 |
|------|------|--------|----------|
| `MCP_SERVER_ENABLED` | 是否启用 MCP Server | `false` | 完整部署 |
| `MCP_SERVER_HOST` | MCP Server 监听地址 | `127.0.0.1` | 完整部署 |
| `MCP_SERVER_PORT` | MCP Server 监听端口 | `8080` | 完整部署 |
| `MCP_CLIENT_SERVERS` | 外部 MCP Server 列表（逗号分隔 URL） | `[]` | 标准部署 |
| `MCP_SECURITY_ENABLED` | 是否启用 MCP 安全层 | `true` | 标准/完整部署 |
| `MCP_AUDIT_LOG_PATH` | MCP 审计日志路径 | `.kimi/mcp_audit.log` | 标准/完整部署 |

---

## 功能矩阵

| 功能 | 核心部署 | 标准部署 | 完整部署 |
|------|----------|----------|----------|
| 意图识别 | ✅ | ✅ | ✅ |
| 多轮澄清 | ✅ | ✅ | ✅ |
| 任务图 | ✅ | ✅ | ✅ |
| 会话管理 | ✅ | ✅ | ✅ |
| 限流/审计 | ✅ | ✅ | ✅ |
| 认知编译 | ✅ | ✅ | ✅ |
| 话题树 | ✅ | ✅ | ✅ |
| 窗口管理 | ✅ | ✅ | ✅ |
| 内置工具 | ✅ | ✅ | ✅ |
| HTTP API | ✅ | ✅ | ✅ |
| 外部工具调用 | ❌ | ✅ | ✅ |
| Claude Desktop 集成 | ❌ | ❌ | ✅ |
| 工具安全层 | ❌ | ✅ | ✅ |

---

## 故障排查

### 问题：MCP 客户端连接失败

**症状**：`MCPClientAdapter.connect()` 返回 `False`。

**排查步骤**：
1. 确认 `mcp` 包已安装：`pip list | grep mcp`
2. 检查 `MCP_CLIENT_SERVERS` 环境变量是否配置正确
3. 检查目标 MCP Server 是否可达：`curl <server_url>`
4. 查看日志：`~/.kimi/mcp_audit.log`

### 问题：Claude Desktop 无法发现工具

**症状**：Claude Desktop 中看不到 MemoryGraph 的工具。

**排查步骤**：
1. 确认 `MCP_SERVER_ENABLED=true`
2. 确认 Claude Desktop 的 MCP 配置中添加了 MemoryGraph Server URL
3. 检查 MCP Server 是否运行：`curl http://127.0.0.1:8080/health`
4. 查看 MCP Server 日志

### 问题：核心功能在 MCP 不可用时异常

**症状**：即使没有安装 `mcp`，核心功能也报错。

**排查步骤**：
1. 确认 `HAS_MCP` 检测逻辑正确（`try: from mcp... except ImportError`）
2. 检查是否有代码硬依赖 `mcp` 的导入（应使用 `HAS_MCP` 守卫）
3. 提交 Issue：核心模块不应在 `HAS_MCP=False` 时抛出 ImportError

---

*最后更新：2026-06-23*
