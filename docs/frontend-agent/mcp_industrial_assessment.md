# MCP 工业化评估报告

> 基于 2026 年 6 月 MCP 生态现状 + 当前项目代码状态

---

## 一、生态成熟度：完全可用

### 1.1 官方 SDK 状态

| 维度 | 状态 | 说明 |
|------|------|------|
| **Python SDK** | ✅ v1.x 稳定版 | `pip install "mcp[cli]"` 即用 |
| **FastMCP** | ✅ 高层封装 | `@mcp.tool()` 装饰器注册工具，≈ 20 行暴露一个工具 |
| **传输层** | ✅ 3 种支持 | stdio（Claude Desktop）、SSE（旧）、Streamable HTTP（新推荐） |
| **v2 Alpha** | ⚠️ 6-30 beta | 不建议现在用，v1.x 维护中 |
| **月下载量** | 97M+ | 2026 年 5 月数据，ChatGPT/Claude/Cursor/Gemini/Copilot 全支持 |

**核心库**（无需自己开发）：
```python
from mcp.server.fastmcp import FastMCP, Context
from mcp.client import Client  # 连接外部 MCP Server
```

### 1.2 与现有代码的关系

```
┌─────────────────────────────────────────────────────────┐
│  MCP 协议层（新增）                                        │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │  MCP Server     │  │  MCP Client     │               │
│  │  (暴露内部工具)  │  │  (连接外部工具)  │               │
│  └────────┬────────┘  └────────┬────────┘               │
│           │                    │                          │
│           └────────┬───────────┘                          │
│                    │                                      │
│  现有核心引擎（已完成，345 测试全部通过）                    │
│  ┌─────────────────────────────────────────────────┐     │
│  │  CognitiveTools (7 工具)                         │     │
│  │  BlueprintExecutor (状态快照/回滚/超时/fallback)  │     │
│  │  DualTrackOrchestrator (3 层门控)                │     │
│  │  ...                                              │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

**MCP 是增量层，不替代任何现有逻辑。** 它只做两件事：
1. 把 `CognitiveTools` 注册为 MCP 标准工具（让外部 LLM 发现）
2. 连接外部 MCP Server（如 GitHub、Fetch、文件系统）的工具

---

## 二、三个需求的具体实现

### 2.1 需求 A：现有工具执行层（已完成）✅

| 组件 | 状态 |
|------|------|
| 工具注册表 `CognitiveTools` | ✅ 7 工具 |
| 蓝图 `Blueprint` + 4 预置 | ✅ 启动校验 |
| 执行引擎 `BlueprintExecutor` | ✅ 状态/回滚/超时/fallback |
| 测试 | ✅ 32 测试（v24_orchestration） |

**工作量：0。** 已完成。

---

### 2.2 需求 B：把自己的工具暴露为 MCP Server（让外部 LLM 调用）

**目标**：让 Claude Desktop / Cursor / ChatGPT 等客户端发现我们的 `CognitiveTools`，并调用 `scan_process`、`read_memory` 等工具。

**实现路径**：

```python
# core/agent/mcp/server.py — 约 150-200 行
from mcp.server.fastmcp import FastMCP, Context
from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.intent_parser import IntentParser

mcp = FastMCP("MemoryGraph Agent")

# 工具适配器：把 CognitiveTools 注册为 MCP 标准工具
@mcp.tool()
def scan_process(query: str) -> str:
    """扫描进程内存。输入自然语言查询，返回扫描结果。"""
    pcr = RuleBasedPCR()  # 或从上下文获取单例
    parser = IntentParser()
    ctx = ExecutionContext(raw_input=query, pcr_instance=pcr, parser_instance=parser)
    result = CognitiveTools.run("pcr_evaluate", ctx, {})
    return result.to_json()

@mcp.tool()
def get_task_graph_status() -> dict:
    """获取当前 TaskGraph 执行状态。"""
    # 从 ExecutionContext 或全局状态读取
    pass

# stdio 传输（Claude Desktop 集成）
if __name__ == "__main__":
    mcp.run()  # 默认 stdio

# Streamable HTTP（Web 服务）
# app = mcp.streamable_http_app()  # 返回 ASGI app，可 mount 到 FastAPI
```

**Claude Desktop 配置**（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "memorygraph": {
      "command": "python",
      "args": ["-m", "core.agent.mcp.server"]
    }
  }
}
```

**工作量估算**：

| 模块 | 代码量 | 说明 |
|------|--------|------|
| `core/agent/mcp/server.py` | 150-200 行 | 工具适配器 + 生命周期管理 |
| `core/agent/mcp/__init__.py` | 20 行 | 导出 |
| 测试 | 100 行 | 用 `mcp.Client` 测试工具调用 |
| **总计** | **~300 行** | **1 人 1-2 天** |

**关键设计决策**：
- 每个 `CognitiveTools` 注册为 1-2 个 MCP 工具（暴露给 LLM 的粒度）
- 会话状态通过 `FastMCP` 的 `lifespan` 管理（数据库连接、PCR 实例）
- 认证：启动时通过环境变量 `MCP_API_KEY` 或 OAuth 2.0（客户端支持）

---

### 2.3 需求 C：对接外部 MCP Server（如 GitHub MCP、Fetch MCP）

**目标**：在 `BlueprintExecutor` 执行流程中，调用外部 MCP Server 的工具（如 `github_search_code`、`fetch_url`）。

**实现路径**：

```python
# core/agent/mcp/client.py — 约 200-300 行
from mcp.client import Client
from mcp.transports import StreamableHTTPTransport
from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext

class MCPClientAdapter:
    """连接外部 MCP Server，将其工具注册为 CognitiveTools 的别名。"""
    
    def __init__(self, server_url: str, api_key: Optional[str] = None):
        self.client = Client(transport=StreamableHTTPTransport(server_url))
        self._tools: Dict[str, Any] = {}  # 缓存发现的工具
    
    async def discover(self) -> List[str]:
        """连接 Server，发现可用工具列表。"""
        await self.client.connect()
        tools = await self.client.list_tools()
        self._tools = {t.name: t for t in tools}
        return list(self._tools.keys())
    
    async def call(self, tool_name: str, arguments: Dict) -> Any:
        """调用外部工具。"""
        return await self.client.call_tool(tool_name, arguments)
    
    def register_as_cognitive_tools(self):
        """将外部工具注册到 CognitiveTools 注册表。"""
        for name, tool_meta in self._tools.items():
            # 包装为 ExecutionContext 兼容的签名
            async def wrapper(ctx: ExecutionContext, state: Dict, _name=name):
                args = _extract_args(ctx, state, tool_meta.input_schema)
                return await self.call(_name, args)
            CognitiveTools.register(f"mcp_{name}", wrapper)

# 使用示例：在 Blueprint 中引用外部工具
BLUEPRINT_DEEP_EXTENDED = Blueprint(
    id="LLM_DEEP_EXTENDED",
    sequence=[
        "pcr_evaluate",
        "extract_entities",
        "detect_ambiguities",
        "mcp_github_search_code",  # 外部 MCP 工具
        "ask_user",
        "build_task_graph",
    ],
    ...
)
```

**工作量估算**：

| 模块 | 代码量 | 说明 |
|------|--------|------|
| `core/agent/mcp/client.py` | 150-200 行 | Client 适配器 + 工具发现 + 调用 |
| `core/agent/mcp/config.py` | 50 行 | Server URL 配置、API Key 管理 |
| 测试 | 100 行 | Mock MCP Server 测试 |
| **总计** | **~300 行** | **1 人 2-3 天** |

---

## 三、工业级安全考量（必须做，不能跳过）

根据 2026 年 MCP 安全报告：

| 风险 | 数据 | 防御措施 |
|------|------|----------|
| **生产失败率** | 41-86% | 79% 是规范/协调问题，非模型能力 |
| **CVE 数量** | 16+（2025-2026） | 5 个 CVSS ≥ 9.0（严重） |
| **公共暴露 Server** | 1467 个（半年增长 3 倍） | 默认不暴露公网 |
| **路径遍历** | 82% 的文件操作工具 | 输入路径白名单 + 沙箱 |
| **静态凭证** | 53% 使用长期凭证 | OAuth 2.0 + 短期 Token |

### 工业级 checklist

**Server 端（暴露工具）**：
- [ ] **认证**：OAuth 2.0 / API Key（FastMCP 支持 `mcp.settings` 配置）
- [ ] **输入验证**：JSON Schema 严格校验（`mcp.tool()` 的 `input_schema` 参数）
- [ ] **速率限制**：复用现有 `RateLimiter`（已有 Token Bucket 实现）
- [ ] **审计日志**：每次工具调用记录（用户、输入、输出、耗时）
- [ ] **只读优先**：先上线 `read_memory`、`get_status`，`write_memory` 放审批门控后
- [ ] **沙箱**：文件操作工具在 chroot/容器内运行
- [ ] **敏感信息过滤**：输出中脱敏 PID、内存地址、路径

**Client 端（连接外部工具）**：
- [ ] **工具白名单**：只调用显式注册的外部工具（已有 `CognitiveTools` 注册表）
- [ ] **输入消毒**：外部工具参数经过 `RouterOutputValidator` 校验（已有危险模式拦截）
- [ ] **超时控制**：外部调用 5s 超时（已有 `latency_budget_ms`）
- [ ] **错误隔离**：外部工具失败不阻断主流程（已有 `fallback` 机制）

---

## 四、与现有架构的集成点

### 4.1 最小侵入原则

MCP 层只新增 2-3 个文件，不修改任何现有 345 测试覆盖的代码：

```
core/agent/
├── mcp/
│   ├── __init__.py          # 导出
│   ├── server.py            # FastMCP Server（暴露内部工具）
│   ├── client.py            # MCP Client（连接外部工具）
│   ├── config.py            # 配置（URL、API Key、白名单）
│   └── security.py          # 安全层（认证、审计、脱敏）
├── tools/
│   ├── cognitive_tools.py   # ✅ 已有（不修改）
│   └── __init__.py          # ✅ 已有（不修改）
├── orchestrator.py          # ✅ 已有（不修改）
├── blueprints.py            # ✅ 已有（不修改）
└── ...
```

### 4.2 启动时集成

```python
# main.py 或 api.py 启动时
from core.agent.mcp.server import create_mcp_server
from core.agent.mcp.client import MCPClientAdapter

# 1. 创建 MCP Server（暴露内部工具）
mcp_server = create_mcp_server(
    pcr=pcr_instance,
    parser=parser_instance,
    rate_limiter=rate_limiter,
)

# 2. 连接外部 MCP Server（如 GitHub）
github_mcp = MCPClientAdapter(server_url="https://github-mcp.example.com")
await github_mcp.discover()  # 发现工具
github_mcp.register_as_cognitive_tools()  # 注册到 CognitiveTools

# 3. 启动 HTTP 服务（Streamable HTTP）
app = create_fastapi_app(agent_service)  # 现有 API
app.mount("/mcp", mcp_server.streamable_http_app())  # MCP 端点
```

---

## 五、工作量总结

| 模块 | 代码量 | 工期 | 优先级 |
|------|--------|------|--------|
| **需求 A（现有）** | 0 | 0 | ✅ 已完成 |
| **需求 B（MCP Server）** | ~300 行 | 1-2 天 | P1 |
| **需求 C（MCP Client）** | ~300 行 | 2-3 天 | P2 |
| **Security 层** | ~200 行 | 1-2 天 | P0（必须） |
| **测试** | ~200 行 | 1 天 | P0 |
| **总计** | **~1000 行** | **5-7 人天** | |

---

## 六、建议的实现顺序

1. **先实现 MCP Server（需求 B）** — 让 Claude Desktop 能调用我们的工具，验证 FastMCP 集成
2. **同时实现 Security 层** — 认证、审计、输入验证，不能后补
3. **再实现 MCP Client（需求 C）** — 连接 1-2 个外部 Server（如 GitHub MCP）验证端到端
4. **最后扩展到多 Server + 动态发现** — 生产级部署

---

## 七、一句话结论

> **MCP 生态已成熟，无需自己开发协议。官方 `mcp` Python SDK + FastMCP 足以支撑工业级部署。** 核心工作量是把自己的 `CognitiveTools` 用 `@mcp.tool()` 暴露出去，以及用 `mcp.Client` 连接外部 Server。安全层必须同步建设，不能后补。总工作量约 **1000 行 / 5-7 人天**。

