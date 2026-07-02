# DialogMesh 动态任务规划架构设计 (Dynamic Task Planning v1.0)

> **文档状态**: 设计冻结 (Design Freeze)  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **依赖**: [认知-画像 v2.0 架构设计](design_cognitive_profile_v2.md)  
> **相关**: [工程实现文档](ENGINEERING_COGNITIVE_PROFILE_V2.md)

---

## 1. 问题诊断：为什么静态 Blueprint 是瓶颈

### 1.1 现状剖析

当前任务规划位于 **Layer 1 (IntentParser)**，核心由三部分组成：

1. **`Blueprint` (core/agent/blueprints.py)**  
   - `frozen=True` 的不可变 dataclass，预定义固定工具序列 (`steps`)。  
   - 工具名硬编码在 `steps` 中，如 `"pcr_evaluate"`, `"intent_parser_full_pipeline"`, `"ask_user"`。  
   - 启动时 `validate_blueprint_registry()` 校验所有工具名是否已注册——**运行时无法动态扩展**。
   - LLM 只能**选择**已注册的 Blueprint，不能**发明**新的执行计划。

2. **`_map_atomic_intent` (core/agent/intent_parser.py:1158)**  
   - 固定字典 `category_tool_map` 将 `IntentCategory` 映射到工具名。  
   - 新增工具需要修改此字典，否则意图无法映射到工具。  
   - 不支持工具参数的动态推断（`tool_params` 为空 dict）。

3. **`_build_task_graph` (core/agent/intent_parser.py:1080)**  
   - 根据 `UserExpectation` (TOOL/ADVISOR/COMPANION) 选择预设模板构建 TaskGraph。  
   - 工具名固定（如 `ask_user`），无法根据新注册的工具动态调整。

### 1.2 用户痛点

> "给一个 API 接口文档，系统就能自动规划任务，不需要改代码，即插即用。"

当前架构无法满足此需求：
- 新 API 需要开发者手动修改 `blueprints.py` 和 `intent_parser.py` 两处代码。
- 没有机制让 LLM 理解新 API 的语义并自动将其纳入规划。
- 工具数量增加后，LLM 上下文窗口无法承载全部工具定义（Tool Overflow 问题）。

### 1.3 文献验证

| 来源 | 核心洞察 | 在本设计中的映射 |
|------|---------|---------------|
| **ToolACE** (2025, ICLR) | LLM 可从 API 领域自动提取工具定义 | `APIDocPreprocessor` 的 schema 提取模块 |
| **ToolRegistry** (2025) | Protocol-agnostic 工具注册中心，支持 MCP/OpenAPI/LangChain 适配器 | `ToolRegistry` 核心设计 |
| **MCP** (Anthropic, 2024) | JSON-RPC 2.0 标准化协议，即插即用 | 工具通信协议层 |
| **OpenAPI-to-MCP** (2025) | OpenAPI/Swagger 自动转换为 MCP 格式 | `APIDocPreprocessor` 的 OpenAPI 解析器 |
| **LangChain Dynamic Tool** (2025) | 运行时工具发现 + `wrap_model_call`/`wrap_tool_call` | `ToolShortlister` 动态筛选机制 |
| **Tool Shortlisting** (General Agent Evaluation, 2023) | 预处理组件按上下文过滤工具集，解决 LLM 工具数量限制 | `ToolShortlister` 的 Relevance Scoring |
| **Understanding Planning of LLM Agents** (2024, 561 citations) | 多计划生成、任务分解、自我反思 | `DynamicPlanner` 的多计划生成与回溯 |

---

## 2. 目标架构：Dynamic Task Planning v1.0

### 2.1 核心思想

**"从静态编排到动态发现：LLM 看到什么工具，就能规划什么任务。"**

- **API 文档即注册**：上传 OpenAPI/Swagger/JSON Schema → 自动提取为工具定义 → 注册到中心。
- **意图驱动筛选**：用户输入 → 意图解析 → 从工具池中筛选**相关子集** → 注入 LLM 上下文。
- **LLM 动态规划**：LLM 基于筛选后的工具子集，自主生成 TaskGraph（而非选择预定义 Blueprint）。
- **Schema 守卫执行**：验证 LLM 生成的工具调用参数，执行 HTTP 请求或本地函数。

### 2.2 架构全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Layer 1: Intent & Planning Layer                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌─────────────────┐    ┌──────────────────────────┐  │
│  │   Intent     │───→│  ToolShortlister │───→│    DynamicPlanner        │  │
│  │   Parser     │    │  (工具筛选引擎)   │    │   (动态规划引擎)          │  │
│  │  (existing)  │    │                  │    │                          │  │
│  └──────────────┘    │ • RelevanceScore │    │ • Multi-plan generation  │  │
│       │              │ • ContextualRank │    │ • Self-reflection        │  │
│       │ intent+category   │              │    │ • Backtracking           │  │
│       ▼              └─────────────────┘    │    │ • Cost estimation        │  │
│  ┌────────────────────────────────────────┐ │    └──────────────────────────┘  │
│  │         ToolRegistry (工具注册中心)     │ │              │               │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐│ │              ▼               │
│  │  │Built-in │ │API Doc  │ │  MCP     ││ │         ┌──────────┐         │
│  │  │ Tools   │ │ Tools   │ │ Tools    ││ │         │ TaskGraph│         │
│  │  └─────────┘ └─────────┘ └──────────┘│ │         │(dynamic) │         │
│  │              ┌─────────┐              │ │         └──────────┘         │
│  │              │Custom   │              │ │              │               │
│  │              │ Tools   │              │ │              ▼               │
│  │              └─────────┘              │ │    ┌──────────────────┐        │
│  └────────────────────────────────────────┘ │    │  SchemaGuard     │        │
│              ▲                              │    │  + Executor      │        │
│              │ register_tool()              │    │  (验证+执行)      │        │
│  ┌───────────┴──────────┐                 │    └──────────────────┘        │
│  │ APIDocPreprocessor   │                 │              │               │
│  │ (API 文档预处理层)     │─────────────────┘              ▼               │
│  │                      │                      ┌──────────────────┐       │
│  │ • OpenAPI parser     │                      │   External API   │       │
│  │ • Schema extractor   │                      │   / Local Func   │       │
│  │ • Semantic enricher  │                      └──────────────────┘       │
│  │ • Tool generator     │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 与现有架构的兼容性

| 现有组件 | 变化 | 兼容性策略 |
|---------|------|-----------|
| `Blueprint` | 废弃静态注册，保留为"策略模板"概念 | 保留 `BLUEPRINT_REGISTRY` 作为 fallback，新增 `DynamicPlanner` 优先 |
| `IntentParser` | `_build_task_graph` 从静态模板改为动态调用 | 保留现有接口，内部实现替换为调用 `DynamicPlanner` |
| `TaskGraph` / `TaskNode` | 无变化 | 完全兼容，动态规划仍然输出 `TaskGraph` |
| `ParseResult` | 无变化 | 完全兼容 |
| `CognitiveTools` | 作为 Built-in Tools 注册到 `ToolRegistry` | 保留现有功能，改为动态注册 |

---

## 3. 核心模块详细设计

### 3.1 ToolRegistry — 动态工具注册中心

**职责**：统一管理所有可用工具，支持运行时注册、注销、版本管理和热更新。

**核心模型** (`core/agent/tool_registry.py`)：

```python
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Set
from enum import Enum
import json
import hashlib
import time

class ToolSource(Enum):
    """工具来源分类，用于权限管理和筛选策略。"""
    BUILTIN = "builtin"        # DialogMesh 内置工具（如 pcr_evaluate, first_scan）
    API_DOC = "api_doc"        # 从 API 文档自动提取的工具
    MCP = "mcp"                # Model Context Protocol 远程工具
    CUSTOM = "custom"          # 用户自定义 Python 函数

class ToolType(Enum):
    """工具类型，决定执行方式。"""
    LOCAL_FUNCTION = "local_function"  # 本地 Python 函数调用
    HTTP_API = "http_api"            # HTTP REST API 调用
    MCP_REMOTE = "mcp_remote"        # MCP 远程服务器调用

@dataclass
class ToolSchema:
    """
    工具标准化 Schema，兼容 OpenAPI 3.1 + JSON Schema + MCP Tool 格式。
    
    这是 LLM 理解工具的唯一接口——所有工具无论来源，必须转换为此格式。
    """
    name: str                       # 工具唯一标识名（蛇形命名，如 "get_user_profile"）
    description: str                # 人类可读的功能描述（用于 LLM 理解）
    parameters: Dict[str, Any]      # JSON Schema 格式的参数定义
    required_params: List[str] = field(default_factory=list)
    
    # 元数据
    source: ToolSource = ToolSource.BUILTIN
    tool_type: ToolType = ToolType.LOCAL_FUNCTION
    version: str = "1.0.0"
    tags: Set[str] = field(default_factory=set)  # 用于分类和筛选
    
    # 执行相关（非必须，用于 Schema Guard 验证）
    endpoint_url: Optional[str] = None  # HTTP_API 类型的目标 URL
    http_method: Optional[str] = None   # GET/POST/PUT/DELETE
    
    # 性能与成本
    estimated_latency_ms: int = 100
    estimated_cost_tokens: int = 50    # 每次调用预估消耗的 LLM token 数
    
    # 权限与安全
    requires_auth: bool = False
    auth_type: Optional[str] = None    # "bearer", "api_key", "oauth2"
    is_destructive: bool = False       # 是否涉及写操作（用于 ADVISOR 模式警告）
    
    # 时间戳
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    @property
    def schema_hash(self) -> str:
        """Schema 内容哈希，用于变更检测和热更新。"""
        content = json.dumps({
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "required_params": self.required_params,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_llm_format(self) -> Dict[str, Any]:
        """
        转换为 LLM 友好的工具描述格式（OpenAI Function Calling / Claude Tool Use）。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

@dataclass
class ToolRegistration:
    """工具注册记录，包含 Schema 和可执行句柄。"""
    schema: ToolSchema
    # 可执行句柄：本地函数、HTTP 客户端或 MCP 客户端
    executor: Optional[Callable] = None
    # 执行统计（用于动态排序和性能监控）
    call_count: int = 0
    success_rate: float = 1.0
    avg_latency_ms: float = 0.0
    # 运行时状态
    is_active: bool = True
    last_error: Optional[str] = None


class ToolRegistry:
    """
    动态工具注册中心——单例模式。
    
    支持：
    - 运行时注册/注销/更新工具（无需重启）
    - 按来源、标签、类型筛选工具
    - 工具执行统计与性能监控
    - Schema 变更检测（热更新）
    """
    
    _instance = None
    _lock = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, ToolRegistration] = {}
            cls._instance._tag_index: Dict[str, Set[str]] = {}  # tag -> tool_names
            cls._instance._source_index: Dict[str, Set[str]] = {}  # source -> tool_names
        return cls._instance
    
    # ── 注册接口 ─────────────────────────────────────────────
    
    def register(self, registration: ToolRegistration) -> bool:
        """
        注册工具。如果同名工具已存在，比较 schema_hash 决定是否更新。
        
        Returns:
            True if registered/updated, False if unchanged.
        """
        schema = registration.schema
        name = schema.name
        
        if name in self._tools:
            existing = self._tools[name]
            if existing.schema.schema_hash == schema.schema_hash:
                return False  # 无变化，跳过
            # Schema 变更：更新并记录
            registration.call_count = existing.call_count
            registration.success_rate = existing.success_rate
        
        self._tools[name] = registration
        self._update_indices(registration)
        return True
    
    def unregister(self, name: str) -> bool:
        """注销工具。"""
        if name not in self._tools:
            return False
        tool = self._tools.pop(name)
        self._remove_from_indices(tool)
        return True
    
    def get(self, name: str) -> Optional[ToolRegistration]:
        """获取工具注册记录。"""
        return self._tools.get(name)
    
    def get_schema(self, name: str) -> Optional[ToolSchema]:
        """获取工具 Schema（用于 LLM 上下文）。"""
        reg = self._tools.get(name)
        return reg.schema if reg else None
    
    # ── 查询接口 ─────────────────────────────────────────────
    
    def list_tools(
        self,
        source: Optional[ToolSource] = None,
        tags: Optional[Set[str]] = None,
        active_only: bool = True,
    ) -> List[ToolSchema]:
        """按条件筛选工具列表。"""
        result = []
        for reg in self._tools.values():
            if active_only and not reg.is_active:
                continue
            if source and reg.schema.source != source:
                continue
            if tags and not tags.intersection(reg.schema.tags):
                continue
            result.append(reg.schema)
        return result
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的 LLM 格式描述（用于注入 LLM 上下文）。"""
        return [reg.schema.to_llm_format() for reg in self._tools.values() if reg.is_active]
    
    def get_tool_count(self) -> int:
        return len(self._tools)
    
    # ── 执行统计 ─────────────────────────────────────────────
    
    def record_call(self, name: str, success: bool, latency_ms: float):
        """记录工具调用结果，用于动态排序。"""
        reg = self._tools.get(name)
        if not reg:
            return
        reg.call_count += 1
        # 指数移动平均更新成功率
        reg.success_rate = 0.9 * reg.success_rate + 0.1 * (1.0 if success else 0.0)
        reg.avg_latency_ms = 0.9 * reg.avg_latency_ms + 0.1 * latency_ms
        if not success:
            reg.last_error = f"Failed at {time.time()}"
    
    # ── 内部索引管理 ─────────────────────────────────────────
    
    def _update_indices(self, reg: ToolRegistration):
        """更新标签和来源索引。"""
        name = reg.schema.name
        for tag in reg.schema.tags:
            self._tag_index.setdefault(tag, set()).add(name)
        src = reg.schema.source.value
        self._source_index.setdefault(src, set()).add(name)
    
    def _remove_from_indices(self, reg: ToolRegistration):
        name = reg.schema.name
        for tag in reg.schema.tags:
            self._tag_index.get(tag, set()).discard(name)
        src = reg.schema.source.value
        self._source_index.get(src, set()).discard(name)
```

**关键设计决策** (KDD)：

| 决策 | 选择 | 理由 |
|------|------|------|
| 单例 vs 依赖注入 | 单例（当前阶段） | 简化与现有 `IntentParser` 的集成，后续可迁移到 DI |
| Schema 格式标准 | 兼容 OpenAI Function Calling + JSON Schema | 最大化 LLM 兼容性，支持 GPT/Claude/LLaMA 等 |
| 工具名唯一性 | 全局唯一（`source_category` 前缀） | 避免冲突，如 `api_doc_github_get_repo` |
| 执行句柄分离 | `executor` 可选，Schema 独立 | 允许先注册 Schema 让 LLM 规划，再延迟绑定执行器 |
| 统计信息 | EMA 更新成功率/延迟 | 用于 `ToolShortlister` 的动态排序 |

---

### 3.2 APIDocPreprocessor — API 文档预处理层

**职责**：将外部 API 文档（OpenAPI/Swagger/JSON Schema/自然语言描述）转换为标准化的 `ToolSchema`。

**核心模型** (`core/agent/api_doc_preprocessor.py`)：

```python
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
import json
import yaml

class DocFormat(Enum):
    """支持的 API 文档格式。"""
    OPENAPI_3 = "openapi_3"      # OpenAPI 3.0/3.1 YAML/JSON
    SWAGGER_2 = "swagger_2"      # Swagger 2.0
    JSON_SCHEMA = "json_schema"  # 纯 JSON Schema
    NATURAL_LANGUAGE = "natural" # 自然语言 API 描述（LLM 提取）
    CURL_EXAMPLES = "curl"       # curl 命令集合

@dataclass
class APIDocInput:
    """API 文档输入容器。"""
    source_id: str                    # 唯一标识（如 "github_api_v3"）
    raw_content: str                  # 原始文档内容
    format: DocFormat                 # 文档格式
    base_url: Optional[str] = None    # API 基础 URL（用于构造完整 endpoint）
    auth_info: Optional[Dict] = None # 认证信息（仅用于执行，不暴露给 LLM）
    metadata: Dict[str, Any] = field(default_factory=dict)


class APIDocPreprocessor:
    """
    API 文档预处理引擎。
    
    Pipeline: 原始文档 → 格式识别 → 解析提取 → Schema 生成 → 语义增强 → ToolSchema 列表
    """
    
    def __init__(self, llm_provider=None):
        self._llm_provider = llm_provider
        self._parsers: Dict[DocFormat, Callable] = {
            DocFormat.OPENAPI_3: self._parse_openapi,
            DocFormat.SWAGGER_2: self._parse_swagger,
            DocFormat.JSON_SCHEMA: self._parse_json_schema,
            DocFormat.NATURAL_LANGUAGE: self._parse_natural_language,
            DocFormat.CURL_EXAMPLES: self._parse_curl_examples,
        }
    
    def process(self, doc_input: APIDocInput) -> List[ToolSchema]:
        """
        主入口：处理 API 文档，输出 ToolSchema 列表。
        
        Returns:
            List of ToolSchema ready for ToolRegistry registration.
        """
        # 1. 格式识别（如果未指定）
        fmt = doc_input.format or self._detect_format(doc_input.raw_content)
        
        # 2. 解析提取
        parser = self._parsers.get(fmt)
        if not parser:
            raise ValueError(f"Unsupported format: {fmt}")
        raw_operations = parser(doc_input)
        
        # 3. Schema 生成 + 语义增强
        tools = []
        for op in raw_operations:
            schema = self._generate_schema(op, doc_input)
            schema = self._semantic_enrichment(schema, doc_input)
            tools.append(schema)
        
        return tools
    
    # ── 解析器实现 ─────────────────────────────────────────────
    
    def _parse_openapi(self, doc_input: APIDocInput) -> List[Dict]:
        """
        解析 OpenAPI 3.0/3.1 规范，提取所有操作。
        
        提取字段：
        - operationId → tool name (fallback: method + path)
        - summary + description → tool description
        - parameters → JSON Schema properties
        - requestBody → JSON Schema properties
        - responses → 用于生成返回类型描述（可选）
        """
        content = doc_input.raw_content
        try:
            spec = yaml.safe_load(content) if content.strip().startswith("{") else json.loads(content)
        except Exception:
            spec = yaml.safe_load(content)
        
        operations = []
        paths = spec.get("paths", {})
        base_url = doc_input.base_url or spec.get("servers", [{}])[0].get("url", "")
        
        for path, methods in paths.items():
            for method, operation in methods.items():
                if method in ("parameters", "servers"):  # skip common fields
                    continue
                
                op_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")
                desc = operation.get("summary", "") + " " + operation.get("description", "")
                
                # 提取参数 schema
                properties = {}
                required = []
                
                # Path/Query/Header parameters
                for param in operation.get("parameters", []):
                    name = param["name"]
                    param_schema = param.get("schema", {"type": "string"})
                    properties[name] = param_schema
                    if param.get("required", False):
                        required.append(name)
                
                # Request body
                request_body = operation.get("requestBody", {})
                if request_body:
                    content_types = request_body.get("content", {})
                    for ct, content_spec in content_types.items():
                        if "schema" in content_spec:
                            body_schema = content_spec["schema"]
                            # 扁平化 body 参数到顶层（简化 LLM 理解）
                            if body_schema.get("type") == "object":
                                for prop_name, prop_schema in body_schema.get("properties", {}).items():
                                    properties[prop_name] = prop_schema
                                    if prop_name in body_schema.get("required", []):
                                        required.append(prop_name)
                            else:
                                properties["body"] = body_schema
                
                operations.append({
                    "name": op_id.lower().replace(" ", "_"),
                    "description": desc.strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                    "endpoint": f"{base_url}{path}",
                    "method": method.upper(),
                    "tags": operation.get("tags", []),
                })
        
        return operations
    
    def _parse_natural_language(self, doc_input: APIDocInput) -> List[Dict]:
        """
        解析自然语言 API 描述（如 Markdown 文档、README 中的 API 说明）。
        
        使用 LLM 提取结构化信息：
        - 提示词模板："从以下 API 文档中提取所有操作，每个操作包含：名称、描述、参数列表、HTTP 方法、URL..."
        """
        prompt = f"""Analyze the following API documentation and extract all available operations.
For each operation, provide:
1. name: A concise snake_case name
2. description: What this operation does (1-2 sentences)
3. parameters: List of parameter names with their types and descriptions
4. method: HTTP method (GET/POST/PUT/DELETE)
5. endpoint: The URL path

API Documentation:
{doc_input.raw_content}

Output as JSON list."""
        
        # 调用 LLM 提取（需要 llm_provider）
        response = self._llm_provider.complete(prompt, json_mode=True)
        return json.loads(response)
    
    # ── Schema 生成与增强 ──────────────────────────────────────
    
    def _generate_schema(self, operation: Dict, doc_input: APIDocInput) -> ToolSchema:
        """从解析后的操作生成 ToolSchema。"""
        return ToolSchema(
            name=f"{doc_input.source_id}_{operation['name']}",  # 前缀避免冲突
            description=operation["description"],
            parameters=operation["parameters"],
            required_params=operation["parameters"].get("required", []),
            source=ToolSource.API_DOC,
            tool_type=ToolType.HTTP_API,
            endpoint_url=operation.get("endpoint"),
            http_method=operation.get("method"),
            tags=set(operation.get("tags", [])),
        )
    
    def _semantic_enrichment(self, schema: ToolSchema, doc_input: APIDocInput) -> ToolSchema:
        """
        语义增强：自动推断工具的语义标签和属性。
        
        - 检测 destructive 操作（POST/PUT/DELETE）
        - 添加领域标签（如 "github", "finance", "memory"）
        - 生成示例调用（用于 few-shot prompt）
        """
        if schema.http_method in ("POST", "PUT", "DELETE", "PATCH"):
            schema.is_destructive = True
        
        # 从 source_id 提取领域标签
        domain = doc_input.source_id.split("_")[0]
        schema.tags.add(domain)
        
        return schema
    
    def _detect_format(self, content: str) -> DocFormat:
        """启发式检测文档格式。"""
        if "openapi" in content.lower() or "swagger" in content.lower():
            return DocFormat.OPENAPI_3
        if content.strip().startswith("{"):
            return DocFormat.JSON_SCHEMA
        if "curl " in content.lower():
            return DocFormat.CURL_EXAMPLES
        return DocFormat.NATURAL_LANGUAGE
```

**关键设计决策** (KDD)：

| 决策 | 选择 | 理由 |
|------|------|------|
| 格式支持优先级 | OpenAPI 3.1 → Swagger 2.0 → JSON Schema → Natural Language | OpenAPI 是最广泛的 API 文档标准 |
| 参数扁平化 | 将 requestBody 扁平化到顶层参数 | 减少 LLM 理解层次，提高调用准确率 |
| 工具名前缀 | `source_id + operation_name` | 避免不同 API 文档间的命名冲突 |
| Natural Language 解析 | LLM 提取 + JSON 模式 | 覆盖非结构化文档（如内部 API 的 README） |
| 语义增强 | 规则启发式（HTTP 方法）+ 领域推断 | 零配置自动标注，减少人工干预 |

---

### 3.3 ToolShortlister — 工具筛选引擎

**职责**：在 LLM 规划前，根据用户意图和上下文从工具池中筛选**最相关的工具子集**，解决 Tool Overflow 问题。

**核心模型** (`core/agent/tool_shortlister.py`)：

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set
import numpy as np

@dataclass
class ShortlistResult:
    """工具筛选结果。"""
    selected_tools: List[ToolSchema]       # 选中的工具子集
    relevance_scores: Dict[str, float]    # 每个工具的相关性得分
    selection_reason: str                  # 筛选策略说明（用于调试）
    excluded_count: int                    # 被排除的工具数量


class ToolShortlister:
    """
    工具筛选引擎——解决 LLM 工具数量限制问题。
    
    策略：多级漏斗筛选
    1. 意图匹配：基于 IntentCategory 与工具标签的精确匹配
    2. 语义相似度：基于描述文本的 embedding 相似度
    3. 历史相关性：基于用户历史调用模式的个性化排序
    4. 动态容量：根据 LLM 上下文窗口限制调整子集大小
    """
    
    def __init__(
        self,
        embedding_model=None,      # 可选：用于语义相似度计算
        max_tools_for_llm: int = 32,  # 注入 LLM 的最大工具数
    ):
        self._embedding_model = embedding_model
        self._max_tools = max_tools_for_llm
        # 意图 → 工具标签的映射规则（可扩展）
        self._intent_tag_map: Dict[IntentCategory, Set[str]] = {
            IntentCategory.SCAN_MEMORY: {"memory", "scan", "search"},
            IntentCategory.READ_MEMORY: {"memory", "read", "dump"},
            IntentCategory.WRITE_MEMORY: {"memory", "write", "modify"},
            IntentCategory.DISASSEMBLE: {"code", "disassemble", "assembly"},
            IntentCategory.FIND_PATTERN: {"pattern", "search", "scan"},
            IntentCategory.SET_BREAKPOINT: {"debug", "breakpoint", "trace"},
            # ... 更多映射
        }
    
    def shortlist(
        self,
        intent: Intent,
        intent_context: IntentContext,
        registry: ToolRegistry,
    ) -> ShortlistResult:
        """
        主入口：根据意图筛选工具子集。
        
        Pipeline: 全部工具 → 意图过滤 → 语义排序 → 容量截断 → 结果
        """
        all_tools = registry.list_tools(active_only=True)
        if not all_tools:
            return ShortlistResult([], {}, "No tools available", 0)
        
        # 阶段 1: 意图标签匹配（粗筛）
        tag_matched = self._filter_by_intent_tags(intent, all_tools)
        
        # 阶段 2: 语义相似度排序（精排）
        scored = self._score_by_semantic_similarity(intent, tag_matched)
        
        # 阶段 3: 历史偏好 boost（个性化）
        scored = self._apply_history_boost(intent_context, scored, registry)
        
        # 阶段 4: 容量截断（上下文窗口限制）
        selected = self._truncate_by_capacity(scored)
        
        # 阶段 5: 兜底策略（确保至少包含通用工具）
        selected = self._ensure_fallback_tools(selected, registry)
        
        relevance_scores = {tool.name: score for tool, score in scored}
        
        return ShortlistResult(
            selected_tools=selected,
            relevance_scores=relevance_scores,
            selection_reason=f"Intent-tag match + semantic similarity + history boost, capped at {self._max_tools}",
            excluded_count=len(all_tools) - len(selected),
        )
    
    def _filter_by_intent_tags(
        self, intent: Intent, tools: List[ToolSchema]
    ) -> List[ToolSchema]:
        """基于意图类别与工具标签的精确匹配。"""
        target_tags = self._intent_tag_map.get(intent.category, set())
        if not target_tags:
            return tools  # 无匹配规则，保留全部
        
        matched = []
        for tool in tools:
            if tool.tags.intersection(target_tags):
                matched.append(tool)
        
        # 如果标签匹配结果为空，放宽到全部工具（避免过度过滤）
        return matched if matched else tools
    
    def _score_by_semantic_similarity(
        self, intent: Intent, tools: List[ToolSchema]
    ) -> List[Tuple[ToolSchema, float]]:
        """
        基于意图描述与工具描述的语义相似度打分。
        
        如果 embedding_model 可用，使用向量相似度；
        否则使用关键词重叠的启发式评分。
        """
        intent_text = f"{intent.category.value} {intent.normalized_input}"
        scored = []
        
        for tool in tools:
            if self._embedding_model:
                # 向量相似度
                score = self._embedding_model.similarity(intent_text, tool.description)
            else:
                # 启发式：关键词重叠率
                score = self._keyword_overlap_score(intent_text, tool.description)
            scored.append((tool, score))
        
        # 按得分降序
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _keyword_overlap_score(self, text1: str, text2: str) -> float:
        """简单的关键词重叠率计算。"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        overlap = len(words1.intersection(words2))
        return overlap / max(len(words1), len(words2))
    
    def _apply_history_boost(
        self,
        intent_context: IntentContext,
        scored: List[Tuple[ToolSchema, float]],
        registry: ToolRegistry,
    ) -> List[Tuple[ToolSchema, float]]:
        """基于历史调用成功率提升常用工具排名。"""
        boosted = []
        for tool, score in scored:
            reg = registry.get(tool.name)
            if reg and reg.call_count > 0:
                # 成功率越高、调用次数越多，boost 越大
                history_boost = reg.success_rate * min(1.0, reg.call_count / 10.0) * 0.1
                score += history_boost
            boosted.append((tool, score))
        boosted.sort(key=lambda x: x[1], reverse=True)
        return boosted
    
    def _truncate_by_capacity(
        self, scored: List[Tuple[ToolSchema, float]]
    ) -> List[ToolSchema]:
        """根据 LLM 上下文窗口限制截断工具列表。"""
        # 保守估计：每个工具描述约 200 tokens
        max_tools = self._max_tools
        
        # 如果工具数量适中，全部保留
        if len(scored) <= max_tools:
            return [tool for tool, _ in scored]
        
        # 否则截断，保留得分最高的
        return [tool for tool, _ in scored[:max_tools]]
    
    def _ensure_fallback_tools(
        self, selected: List[ToolSchema], registry: ToolRegistry
    ) -> List[ToolSchema]:
        """确保选中列表包含通用工具（如 ask_user, finish）。"""
        essential_tools = {"ask_user", "finish"}
        selected_names = {t.name for t in selected}
        
        for tool_name in essential_tools:
            if tool_name not in selected_names:
                schema = registry.get_schema(tool_name)
                if schema:
                    selected.append(schema)
        
        return selected
```

**关键设计决策** (KDD)：

| 决策 | 选择 | 理由 |
|------|------|------|
| 筛选策略 | 多级漏斗（意图→语义→历史→容量） | 平衡精确性与召回率，避免过度过滤 |
| 默认容量 | 32 个工具 | 基于 GPT-4 函数调用 128 个限制的安全余量（考虑其他上下文占用） |
| 无 embedding 时的降级 | 关键词重叠启发式 | 确保零依赖启动，BGE 模型可选 |
| 历史 boost 公式 | `success_rate * min(1, call_count/10) * 0.1` | 常用且成功的工具自然上浮，但不超过 10% 影响 |
| 兜底工具 | 强制保留 `ask_user`, `finish` | 确保 LLM 始终有澄清和终止选项 |

---

### 3.4 DynamicPlanner — 动态规划引擎

**职责**：取代静态 `Blueprint`，让 LLM 基于筛选后的工具子集自主生成 `TaskGraph`。

**核心模型** (`core/agent/dynamic_planner.py`)：

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json

class DynamicPlanner:
    """
    动态规划引擎——基于 LLM 自主生成 TaskGraph。
    
    与静态 Blueprint 的区别：
    - Blueprint: "LLM 从 4 个预定义模板中选择一个"
    - DynamicPlanner: "LLM 基于可用工具，自主构建执行计划"
    
    支持：
    - 多计划生成（生成 3 个候选计划，选择最优）
    - 自我反思（检查计划的完整性和可行性）
    - 成本估计（预估 token 消耗和执行时间）
    - 与现有 TaskGraph 的 100% 兼容
    """
    
    def __init__(self, llm_provider, tool_registry: ToolRegistry):
        self._llm = llm_provider
        self._registry = tool_registry
    
    def plan(
        self,
        intent: Intent,
        intent_context: IntentContext,
        shortlisted_tools: ShortlistResult,
    ) -> TaskGraph:
        """
        主入口：生成动态 TaskGraph。
        
        Pipeline:
        1. 构建 LLM 规划提示词（包含工具定义 + 意图 + 规划约束）
        2. 生成多计划（默认 3 个候选）
        3. 自我反思与筛选
        4. 解析为 TaskGraph
        5. 验证与后处理
        """
        # 1. 构建提示词
        prompt = self._build_planning_prompt(intent, intent_context, shortlisted_tools)
        
        # 2. 生成多计划
        candidates = self._generate_candidates(prompt, n_candidates=3)
        
        # 3. 反思与筛选
        best_plan = self._reflect_and_select(candidates, intent)
        
        # 4. 解析为 TaskGraph
        task_graph = self._parse_to_taskgraph(best_plan, intent)
        
        # 5. 验证
        self._validate_taskgraph(task_graph, shortlisted_tools)
        
        return task_graph
    
    def _build_planning_prompt(
        self,
        intent: Intent,
        intent_context: IntentContext,
        shortlisted: ShortlistResult,
    ) -> str:
        """
        构建规划提示词。
        
        包含：
        - 系统角色定义
        - 可用工具列表（JSON Schema 格式）
        - 用户意图和提取的实体
        - 规划约束（最大步骤数、依赖类型、fallback 策略）
        - 输出格式规范（必须输出为 JSON 格式的 TaskGraph）
        """
        tools_json = json.dumps([t.to_llm_format() for t in shortlisted.selected_tools], ensure_ascii=False, indent=2)
        entities_json = json.dumps([e.to_dict() for e in intent.entities], ensure_ascii=False)
        
        prompt = f"""You are a task planning agent. Your job is to create an execution plan (TaskGraph) based on the user's intent and available tools.

## Available Tools
{tools_json}

## User Intent
- Category: {intent.category.value}
- Normalized Input: {intent.normalized_input}
- Extracted Entities: {entities_json}
- Expectation Mode: {intent_context.expectation.value}

## Planning Constraints
- Max steps: 10
- Supported dependency types: sequential, conditional, fallback, parallel
- Each step must use exactly one tool from the Available Tools list
- If a required parameter is missing, use "ask_user" tool to request it
- Include fallback steps for destructive operations (write, delete, modify)

## Output Format
Output a JSON object with this structure:
{{
  "nodes": [
    {{
      "name": "human-readable step name",
      "goal": "what this step achieves",
      "strategy": "how it achieves it",
      "tool_name": "exact tool name from Available Tools",
      "tool_params": {{"param_name": "value_or_entity_ref"}},
      "layer": 1,  // 1=concept, 2=engineering, 3=execution
      "tags": ["tag1", "tag2"],
      "fallback_nodes": ["fallback_step_name_if_any"]
    }}
  ],
  "edges": [
    {{
      "source": "step_name",
      "target": "next_step_name",
      "type": "sequential|conditional|fallback|parallel",
      "condition": "optional condition expression"
    }}
  ],
  "reasoning": "brief explanation of why this plan was chosen"
}}"""
        return prompt
    
    def _generate_candidates(self, prompt: str, n_candidates: int = 3) -> List[Dict]:
        """生成多个候选计划（使用 temperature 变化增加多样性）。"""
        candidates = []
        temperatures = [0.2, 0.5, 0.8]
        
        for i, temp in enumerate(temperatures[:n_candidates]):
            try:
                response = self._llm.complete(prompt, temperature=temp, json_mode=True)
                plan = json.loads(response)
                candidates.append(plan)
            except Exception as e:
                # 如果某个候选失败，继续生成其他
                continue
        
        # 如果全部失败，返回一个最小可用计划（fallback）
        if not candidates:
            return [self._create_fallback_plan()]
        
        return candidates
    
    def _reflect_and_select(self, candidates: List[Dict], intent: Intent) -> Dict:
        """
        自我反思：评估候选计划的完整性、可行性，选择最优。
        
        评估维度：
        1. 工具存在性：引用的工具是否在可用列表中
        2. 参数完整性：必填参数是否已提供或有获取策略
        3. 依赖合理性：是否存在循环依赖或不可达节点
        4. 意图覆盖：计划是否覆盖了用户的全部意图
        """
        scored = []
        for plan in candidates:
            score = 0.0
            
            # 维度 1: 工具存在性
            nodes = plan.get("nodes", [])
            valid_tools = sum(1 for n in nodes if self._registry.get_schema(n.get("tool_name")))
            score += (valid_tools / max(len(nodes), 1)) * 0.3
            
            # 维度 2: 参数完整性
            complete_params = 0
            for node in nodes:
                schema = self._registry.get_schema(node.get("tool_name"))
                if schema:
                    required = set(schema.required_params)
                    provided = set(node.get("tool_params", {}).keys())
                    if required.issubset(provided) or node.get("tool_name") == "ask_user":
                        complete_params += 1
            score += (complete_params / max(len(nodes), 1)) * 0.3
            
            # 维度 3: 依赖合理性（无循环依赖检测）
            edges = plan.get("edges", [])
            if self._is_dag_valid(nodes, edges):
                score += 0.2
            
            # 维度 4: 意图覆盖（简单启发式：节点数量与意图复杂度匹配）
            expected_steps = 1 + len(intent.sub_intents)
            actual_steps = len(nodes)
            if abs(actual_steps - expected_steps) <= 2:
                score += 0.2
            
            scored.append((plan, score))
        
        # 选择得分最高的
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored else self._create_fallback_plan()
    
    def _parse_to_taskgraph(self, plan: Dict, intent: Intent) -> TaskGraph:
        """将 JSON 计划解析为 TaskGraph 对象。"""
        graph = TaskGraph(intent_id=intent.id)
        
        # 创建节点映射
        node_map = {}
        for node_data in plan.get("nodes", []):
            node = TaskNode(
                name=node_data.get("name", "unnamed"),
                goal=node_data.get("goal", ""),
                strategy=node_data.get("strategy", ""),
                tool_name=node_data.get("tool_name"),
                tool_params=node_data.get("tool_params", {}),
                layer=node_data.get("layer", 3),
                tags=set(node_data.get("tags", [])),
                fallback_nodes=node_data.get("fallback_nodes", []),
            )
            graph.add_node(node)
            node_map[node.name] = node
        
        # 创建边
        for edge_data in plan.get("edges", []):
            source = node_map.get(edge_data.get("source"))
            target = node_map.get(edge_data.get("target"))
            if source and target:
                dep_type = DependencyType(edge_data.get("type", "sequential"))
                graph.add_dependency(source.id, target.id, dep_type, edge_data.get("condition"))
        
        return graph
    
    def _validate_taskgraph(self, graph: TaskGraph, shortlisted: ShortlistResult) -> None:
        """验证 TaskGraph 的合法性。"""
        # 检查所有工具名是否在 shortlisted 中
        allowed_tools = {t.name for t in shortlisted.selected_tools}
        for node in graph.nodes.values():
            if node.tool_name and node.tool_name not in allowed_tools:
                raise ValueError(f"TaskGraph references unauthorized tool: {node.tool_name}")
        
        # 检查循环依赖
        order = graph.topological_order()
        if len(order) != len(graph.nodes):
            raise ValueError("TaskGraph contains circular dependencies")
    
    def _create_fallback_plan(self) -> Dict:
        """创建最小 fallback 计划（直接询问用户）。"""
        return {
            "nodes": [
                {
                    "name": "clarify",
                    "goal": "Ask user for clarification",
                    "strategy": "fallback_ask",
                    "tool_name": "ask_user",
                    "tool_params": {"question": "I need more information to create a plan. What would you like to do?"},
                    "layer": 1,
                    "tags": ["fallback"],
                }
            ],
            "edges": [],
            "reasoning": "Fallback plan due to planning failure",
        }
    
    def _is_dag_valid(self, nodes: List[Dict], edges: List[Dict]) -> bool:
        """简单的 DAG 验证（检测循环依赖）。"""
        # 构建邻接表
        node_names = {n["name"] for n in nodes}
        adj = {name: set() for name in node_names}
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src in adj and tgt in adj:
                adj[src].add(tgt)
        
        # DFS 检测循环
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False
        
        for node in node_names:
            if node not in visited:
                if dfs(node):
                    return False
        return True
```

**关键设计决策** (KDD)：

| 决策 | 选择 | 理由 |
|------|------|------|
| 规划方式 | LLM 自主生成 JSON TaskGraph（而非选择模板） | 最大化灵活性，新工具无需预定义模板 |
| 多计划生成 | 3 个候选，temperature 0.2/0.5/0.8 | 平衡确定性与创造性，低 temperature 保证可用性 |
| 自我反思 | 4 维度评分（工具存在、参数完整、DAG 有效、意图覆盖） | 无需额外 LLM 调用，规则化评估降低成本 |
| 输出格式 | 严格 JSON Schema（nodes + edges） | 便于解析为 `TaskGraph`，与现有系统兼容 |
| Fallback 策略 | 最小计划（ask_user） | 任何失败都不阻断对话，优雅降级 |
| 验证层 | 工具名白名单 + DAG 检测 | 防止 LLM 幻觉引用不存在的工具或构造循环依赖 |

---

### 3.5 SchemaGuard + Executor — 验证与执行层

**职责**：验证 LLM 生成的工具调用参数是否符合 Schema，并执行实际调用。

```python
class SchemaGuard:
    """
    Schema 守卫——验证 LLM 生成的工具调用。
    
    检查项：
    1. 工具名是否存在
    2. 必填参数是否齐全
    3. 参数类型是否符合 JSON Schema
    4. 枚举值是否合法
    """
    
    def validate(self, tool_name: str, params: Dict, registry: ToolRegistry) -> ValidationResult:
        schema = registry.get_schema(tool_name)
        if not schema:
            return ValidationResult(False, f"Unknown tool: {tool_name}")
        
        # 检查必填参数
        required = set(schema.required_params)
        provided = set(params.keys())
        missing = required - provided
        if missing:
            return ValidationResult(False, f"Missing required parameters: {missing}")
        
        # 验证参数类型（使用 JSON Schema 验证）
        # ... jsonschema.validate(params, schema.parameters) ...
        
        return ValidationResult(True, "Valid")


class ToolExecutor:
    """
    工具执行器——根据 ToolType 分发到不同的执行后端。
    
    - LOCAL_FUNCTION: 直接调用 Python 函数
    - HTTP_API: 构造 HTTP 请求并发送
    - MCP_REMOTE: 通过 MCP 客户端发送 JSON-RPC 2.0 请求
    """
    
    def execute(self, tool_name: str, params: Dict, registry: ToolRegistry) -> ExecutionResult:
        reg = registry.get(tool_name)
        if not reg:
            return ExecutionResult(False, error=f"Tool not found: {tool_name}")
        
        schema = reg.schema
        start_time = time.time()
        
        try:
            if schema.tool_type == ToolType.LOCAL_FUNCTION:
                if reg.executor:
                    result = reg.executor(**params)
                else:
                    return ExecutionResult(False, error="No executor bound for local function")
            
            elif schema.tool_type == ToolType.HTTP_API:
                result = self._execute_http(schema, params)
            
            elif schema.tool_type == ToolType.MCP_REMOTE:
                result = self._execute_mcp(schema, params)
            
            else:
                return ExecutionResult(False, error=f"Unknown tool type: {schema.tool_type}")
            
            # 记录成功
            latency = (time.time() - start_time) * 1000
            registry.record_call(tool_name, success=True, latency_ms=latency)
            return ExecutionResult(True, result=result, latency_ms=latency)
        
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            registry.record_call(tool_name, success=False, latency_ms=latency)
            return ExecutionResult(False, error=str(e), latency_ms=latency)
    
    def _execute_http(self, schema: ToolSchema, params: Dict) -> Any:
        """执行 HTTP API 调用。"""
        import requests
        url = schema.endpoint_url
        method = schema.http_method or "GET"
        
        # 将参数分类到 path/query/body
        # 简化为全部放入 JSON body 或 query string
        if method == "GET":
            response = requests.get(url, params=params)
        else:
            response = requests.request(method, url, json=params)
        
        response.raise_for_status()
        return response.json()
    
    def _execute_mcp(self, schema: ToolSchema, params: Dict) -> Any:
        """执行 MCP 远程调用（JSON-RPC 2.0）。"""
        # 通过 MCP 客户端发送请求
        # ... MCP client implementation ...
        pass
```

---

## 4. 数据流与接口定义

### 4.1 完整数据流

```
用户输入
  │
  ▼
┌─────────────────┐
│  IntentParser   │  ← 现有 Layer 1，保持不变
│  (parse)        │
└─────────────────┘
  │
  ▼ intent + category + entities
┌─────────────────┐
│ ToolShortlister │  ← 新增：从全部工具中筛选相关子集
│  (shortlist)    │
└─────────────────┘
  │
  ▼ selected_tools (≤32)
┌─────────────────┐
│ DynamicPlanner  │  ← 新增：LLM 自主生成 TaskGraph
│    (plan)       │
└─────────────────┘
  │
  ▼ TaskGraph (dynamic)
┌─────────────────┐
│  SchemaGuard    │  ← 新增：验证每个节点的工具调用
│  (validate)     │
└─────────────────┘
  │
  ▼ validated
┌─────────────────┐
│  ToolExecutor   │  ← 新增：执行实际调用
│  (execute)      │
└─────────────────┘
  │
  ▼ result
┌─────────────────┐
│  ParseResult    │  ← 现有格式，保持不变
│  (existing)     │
└─────────────────┘
```

### 4.2 关键接口定义

```python
# ToolRegistry 接口（已在上文详细定义）
class ToolRegistry:
    def register(self, registration: ToolRegistration) -> bool: ...
    def get_schema(self, name: str) -> Optional[ToolSchema]: ...
    def list_tools(...) -> List[ToolSchema]: ...

# APIDocPreprocessor 接口
class APIDocPreprocessor:
    def process(self, doc_input: APIDocInput) -> List[ToolSchema]: ...

# ToolShortlister 接口
class ToolShortlister:
    def shortlist(self, intent: Intent, intent_context: IntentContext, 
                  registry: ToolRegistry) -> ShortlistResult: ...

# DynamicPlanner 接口
class DynamicPlanner:
    def plan(self, intent: Intent, intent_context: IntentContext,
             shortlisted_tools: ShortlistResult) -> TaskGraph: ...

# SchemaGuard 接口
class SchemaGuard:
    def validate(self, tool_name: str, params: Dict, 
                 registry: ToolRegistry) -> ValidationResult: ...

# ToolExecutor 接口
class ToolExecutor:
    def execute(self, tool_name: str, params: Dict,
                registry: ToolRegistry) -> ExecutionResult: ...
```

### 4.3 与现有系统的集成点

```python
# core/agent/intent_parser.py — _build_task_graph 修改
class IntentParser:
    def __init__(self, llm_provider=None, adaptive_threshold=None,
                 tool_registry: Optional[ToolRegistry] = None,
                 use_dynamic_planning: bool = True):  # 新增参数
        self._llm_provider = llm_provider
        self._adaptive_threshold = adaptive_threshold
        self._tool_registry = tool_registry or ToolRegistry()
        self._use_dynamic_planning = use_dynamic_planning
        self._shortlister = ToolShortlister()
        self._planner = DynamicPlanner(llm_provider, self._tool_registry)
    
    def _build_task_graph(self, intent: Intent, 
                          intent_context: IntentContext) -> TaskGraph:
        """修改后的 TaskGraph 构建：优先动态规划，fallback 到静态 Blueprint。"""
        if self._use_dynamic_planning and self._llm_provider:
            # 动态规划路径
            shortlisted = self._shortlister.shortlist(
                intent, intent_context, self._tool_registry
            )
            return self._planner.plan(intent, intent_context, shortlisted)
        else:
            # 静态 Blueprint 路径（向后兼容）
            return self._build_static_task_graph(intent, intent_context)
```

---

## 5. 使用场景演示

### 场景 1：即插即用新 API

```python
# 用户上传 GitHub API 文档（OpenAPI 3.0 YAML）
from core.agent.api_doc_preprocessor import APIDocPreprocessor, APIDocInput, DocFormat
from core.agent.tool_registry import ToolRegistry

# 1. 预处理
preprocessor = APIDocPreprocessor(llm_provider=llm)
doc_input = APIDocInput(
    source_id="github_api",
    raw_content=open("github_api.yaml").read(),
    format=DocFormat.OPENAPI_3,
    base_url="https://api.github.com",
)
tools = preprocessor.process(doc_input)  # 提取约 200+ 个操作

# 2. 注册到中心
registry = ToolRegistry()
for tool_schema in tools:
    registry.register(ToolRegistration(schema=tool_schema))

# 3. 用户对话（自动使用新工具）
user_input = "帮我查找 DialogMesh 仓库最近的 issues"
# IntentParser 会自动筛选出 github_api_get_repo_issues 等工具
# DynamicPlanner 生成调用计划：
#   1. github_api_search_repos (name=DialogMesh) → 获取 repo full_name
#   2. github_api_list_issues (repo=aptshark-g/DialogMesh) → 返回 issues 列表
```

### 场景 2：工具数量膨胀后的自动筛选

```python
# 假设已注册 500 个工具（内置 20 + API 文档 200 + MCP 280）
registry = ToolRegistry()
print(registry.get_tool_count())  # 500

# 用户意图：读取内存
intent = Intent(category=IntentCategory.READ_MEMORY, ...)

# ToolShortlister 自动筛选：
# - 意图标签匹配：保留 memory/read/dump 标签的工具（约 15 个）
# - 语义相似度：提升 read_memory, direct_read 排名
# - 历史 boost：用户最近常用 read_memory，额外加分
# - 最终注入 LLM 的：8 个最相关工具 + 2 个通用工具（ask_user, finish）
```

### 场景 3：动态规划 vs 静态 Blueprint 对比

| 维度 | 静态 Blueprint (旧) | 动态规划 (新) |
|------|---------------------|---------------|
| 新工具接入 | 改 `blueprints.py` + `intent_parser.py` | 上传 API 文档，自动注册 |
| 计划灵活性 | 4 个固定模板 | LLM 基于工具自主组合 |
| 意图覆盖 | 需预定义每个 IntentCategory 的映射 | 自动语义匹配，无需预定义 |
| 参数推断 | 固定 `tool_params={}` | LLM 根据实体自动填充参数 |
| 错误处理 | 固定 fallback 链 | 动态生成 fallback 节点 |
| 成本 | 低（规则匹配） | 中（一次 LLM 调用） |
| 延迟 | 5ms | 200-500ms（取决于 LLM） |

---

## 6. 实现路线图

### Phase 1: 基础设施（预计 2-3 天）

- [ ] 实现 `ToolRegistry` 核心（注册、查询、索引、统计）
- [ ] 实现 `ToolSchema` 模型和 `to_llm_format()` 转换
- [ ] 将现有 `CognitiveTools` 迁移为 `ToolRegistry` 的 Built-in 注册
- [ ] 编写 `ToolRegistry` 单元测试（覆盖率 ≥ 90%）

### Phase 2: API 文档预处理（预计 3-4 天）

- [ ] 实现 `APIDocPreprocessor` 核心框架
- [ ] 实现 OpenAPI 3.0/3.1 解析器
- [ ] 实现 Swagger 2.0 解析器（降级兼容）
- [ ] 实现 JSON Schema 解析器
- [ ] 实现 Natural Language 解析器（LLM 提取）
- [ ] 编写端到端测试（上传 GitHub API 文档 → 提取工具 → 注册）

### Phase 3: 工具筛选与动态规划（预计 4-5 天）

- [ ] 实现 `ToolShortlister`（意图匹配 + 语义相似度 + 历史 boost）
- [ ] 实现 `DynamicPlanner`（提示词构建 + 多计划生成 + 反思筛选）
- [ ] 实现 `SchemaGuard`（参数验证）
- [ ] 实现 `ToolExecutor`（本地函数 + HTTP API + MCP 分发）
- [ ] 修改 `IntentParser._build_task_graph` 集成动态规划（保持向后兼容）
- [ ] 编写集成测试（完整数据流测试）

### Phase 4: 性能优化与监控（预计 2-3 天）

- [ ] 实现 `ToolShortlister` 的 embedding 缓存（避免重复计算）
- [ ] 实现 `DynamicPlanner` 的计划缓存（相似意图直接复用）
- [ ] 添加工具调用延迟和成功率监控（Prometheus metrics）
- [ ] 添加动态规划失败的告警和自动降级到静态 Blueprint
- [ ] 压力测试（1000+ 工具注册 + 100 QPS 筛选请求）

### Phase 5: 文档与示例（预计 1-2 天）

- [ ] 编写 `API_DOC_PREPROCESSING_GUIDE.md`（面向用户的 API 文档上传指南）
- [ ] 编写 `TOOL_REGISTRY_API.md`（面向开发者的工具注册接口文档）
- [ ] 提供 3 个示例：GitHub API、天气 API、内部微服务 API
- [ ] 更新 `README.md` 和 `docker-compose.yml`（如有必要）

---

## 7. 风险评估与缓解

| 风险 | 可能性 | 影响 | 缓解策略 |
|------|--------|------|---------|
| LLM 规划失败（幻觉、格式错误） | 中 | 高 | 多计划生成 + 自我反思 + fallback 到静态 Blueprint |
| 工具数量过多导致筛选性能下降 | 低 | 中 | 多级索引（标签 + 来源）+ embedding 缓存 |
| API 文档解析不准确 | 中 | 中 | 多格式解析器 + LLM 提取兜底 + 人工审核入口 |
| 动态规划延迟过高（>1s） | 中 | 高 | 计划缓存 + 异步预生成 + 静态 Blueprint 降级 |
| Schema 验证漏检导致错误调用 | 低 | 高 | JSON Schema 严格验证 + 参数白名单 + 沙箱执行 |
| 向后兼容性问题 | 低 | 高 | 保留静态 Blueprint 作为 fallback，默认渐进启用 |

---

## 8. 与认知-画像 v2.0 的协同

动态任务规划与认知-画像 v2.0 的联动点：

| 画像维度 | 在动态规划中的应用 |
|---------|-----------------|
| **Track A: 认知动力学** | 高元认知用户 → 更复杂的计划（更多步骤、条件分支）；低元认知用户 → 简化计划，增加解释节点 |
| **Track B: 标签化信息** | `technical_level` 标签影响 `ToolShortlister` 的筛选策略（专家用户展示高级工具，新手隐藏） |
| **时间衰减** | 历史调用频率的衰减权重，避免过时偏好长期主导工具排序 |
| **g 因子** | 高 g 因子用户 → 允许更长的工具链（10+ 步）；低 g 因子用户 → 限制为 3-5 步，增加确认节点 |
| **标签获取策略** | L3/L4 获取的技术偏好标签，可直接用于 `ToolShortlister` 的初始过滤 |

---

## 9. 附录

### 9.1 术语表

| 术语 | 定义 |
|------|------|
| **ToolRegistry** | 动态工具注册中心，运行时管理工具 Schema 和执行句柄 |
| **ToolShortlister** | 工具筛选引擎，基于意图和上下文从工具池中选择相关子集 |
| **DynamicPlanner** | 动态规划引擎，让 LLM 基于可用工具自主生成 TaskGraph |
| **SchemaGuard** | Schema 验证层，确保 LLM 生成的工具调用符合参数规范 |
| **APIDocPreprocessor** | API 文档预处理层，将 OpenAPI/Swagger 等转换为 ToolSchema |
| **Tool Overflow** | LLM 上下文窗口无法承载全部工具定义的问题 |
| **MCP** | Model Context Protocol，Anthropic 提出的标准化工具通信协议 |

### 9.2 参考文献

1. Qin, Y., et al. (2025). "ToolACE: Win the Tool Using Competition." ICLR 2025.
2. Wang, L., et al. (2024). "Tool learning in the wild." arXiv:2501.10757.
3. Qiao, B., et al. (2024). "AutoGUI: autonomous GUI control." NeurIPS 2024.
4. Anthropic (2024). "Model Context Protocol (MCP) Specification."
5. rustho (2025). "openapi-to-mcp: Generate AI-friendly interfaces from OpenAPI specs." GitHub.
6. Yang, Z., et al. (2024). "Understanding the planning of LLM agents." arXiv:2406.06530. (561 citations)
7. Schmidgall, S., et al. (2025). "ToolRegistry: A Protocol-Agnostic Tool Management Library." arXiv:2507.10593.
8. LangChain (2025). "Dynamic tool selection and middleware." LangChain Documentation.
9. "General Agent Evaluation" (2023). Tool Shortlisting, Schema Guard, Communication Protocol analysis.

### 9.3 设计决策记录 (ADR)

**ADR-001: 保留静态 Blueprint 作为 fallback**
- **决策**: 动态规划启用时，静态 Blueprint 保留为 fallback 路径。
- **理由**: 降低迁移风险，确保 LLM 规划失败时系统仍可运行。
- **后果**: 维护两套路径，增加代码复杂度。

**ADR-002: 全局工具名唯一（source_id 前缀）**
- **决策**: 工具名格式为 `{source_id}_{operation_name}`。
- **理由**: 避免不同 API 文档间的命名冲突。
- **后果**: 工具名变长，LLM 需要更长的上下文窗口。

**ADR-003: 参数扁平化（requestBody → 顶层参数）**
- **决策**: 将 HTTP requestBody 的字段扁平化到工具参数的顶层。
- **理由**: 减少 LLM 理解层次，提高函数调用准确率。
- **后果**: 与原始 API 结构不完全一致，可能需要特殊处理嵌套对象。

**ADR-004: Embedding 模型可选（非必须）**
- **决策**: `ToolShortlister` 的语义相似度支持无 embedding 的降级模式。
- **理由**: 确保零依赖启动，Docker 镜像无需包含 BGE 模型即可运行。
- **后果**: 无 embedding 时筛选精度下降，依赖关键词匹配。

---

*本设计文档由 DialogMesh 架构团队基于文献调研和代码分析生成，遵循"可计算行为特征"公理化体系。*
