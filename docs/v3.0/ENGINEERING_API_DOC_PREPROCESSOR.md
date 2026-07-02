# DialogMesh API 文档预处理器 — 工程实现文档

> **文档编号**: ENGINEERING-API-DOC-PREPROCESSOR-012  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md`（API 文档解析）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（上下文构建）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **原则**: 将外部 API 文档解析为 LLM 可理解的结构化上下文，支撑工具调用和知识查询。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. API 文档解析器（APIDocParser）](#5-api-文档解析器apidocparser)
- [6. Schema 提取器（SchemaExtractor）](#6-schema-提取器schemaextractor)
- [7. 端点提取器（EndpointExtractor）](#7-端点提取器endpointextractor)
- [8. 文档标准化器（DocNormalizer）](#8-文档标准化器docnormalizer)
- [9. 上下文构建器（ContextBuilder）](#9-上下文构建器contextbuilder)
- [10. 与 6 个 LLM 实例的集成](#10-与-6-个-llm-实例的集成)
- [11. 测试策略](#11-测试策略)
- [12. 附录：简化与待讨论项](#12-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **API 文档预处理器（API Doc Preprocessor）**的完整实现规范。API 文档预处理器负责将外部 API 文档（OpenAPI、Swagger、GraphQL、Markdown）解析为 LLM 可理解的结构化上下文，支撑工具调用、知识查询和自动文档生成。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| OpenAPI 解析 | `DESIGN_FULL_CONCEPT.md` | §5 | 解析 OpenAPI 3.0 文档 |
| Schema 提取 | `DESIGN_FULL_CONCEPT.md` | §6 | 提取数据模型定义 |
| 端点提取 | `DESIGN_FULL_CONCEPT.md` | §7 | 提取 API 端点信息 |
| 文档标准化 | `DESIGN_FULL_CONCEPT.md` | §8 | 统一格式为内部标准 |
| 上下文构建 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` | §9 | 构建 LLM 可用的上下文 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/api_doc/parser.py` | API 文档解析器 | ~200 行 | 新增 |
| `core/agent/api_doc/schema_extractor.py` | Schema 提取器 | ~150 行 | 新增 |
| `core/agent/api_doc/endpoint_extractor.py` | 端点提取器 | ~150 行 | 新增 |
| `core/agent/api_doc/normalizer.py` | 文档标准化器 | ~100 行 | 新增 |
| `core/agent/api_doc/context_builder.py` | 上下文构建器 | ~150 行 | 新增 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/tools/discovery.py` | 集成 OpenAPI 解析 | 工具发现层 |
| `core/agent/context_manager.py` | 集成 API 上下文 | 上下文管理层 |

---

## 3. 现有实现评估

### 3.1 现有 API 文档处理

**定义位置**: 无

| 功能 | 状态 | 说明 |
|------|------|------|
| OpenAPI 解析 | 无 | 需新增 |
| Swagger 解析 | 无 | 需新增 |
| GraphQL 解析 | 无 | 需新增 |
| Markdown 解析 | 无 | 需新增 |
| 文档缓存 | 无 | 需新增 |

### 3.2 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| OpenAPI 3.0 解析 | 无 | 需新增 `APIDocParser` | P1 |
| Schema 提取 | 无 | 需新增 `SchemaExtractor` | P1 |
| 端点提取 | 无 | 需新增 `EndpointExtractor` | P1 |
| 文档标准化 | 无 | 需新增 `DocNormalizer` | P1 |
| 上下文构建 | 无 | 需新增 `ContextBuilder` | P1 |
| 文档缓存 | 无 | 需新增缓存层 | P2 |
| 增量更新 | 无 | 需支持文档版本对比 | P2 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         外部 API 文档（OpenAPI / Swagger / GraphQL）           │
│                              ↓ 下载/加载                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  API 文档预处理器（API Doc Preprocessor）                                    │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ APIDocParser     │  │ SchemaExtractor│  │ EndpointExtractor│            │
│  │ 文档解析器       │  │ Schema 提取器    │  │ 端点提取器       │            │
│  │ OpenAPI/Swagger  │  │ 数据模型定义     │  │ API 端点信息     │            │
│  │ GraphQL/Markdown │  │ 字段/类型/约束   │  │ 方法/路径/参数   │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ DocNormalizer    │  │ ContextBuilder   │                                 │
│  │ 文档标准化器     │  │ 上下文构建器     │                                 │
│  │ 统一内部格式     │  │ LLM 可用上下文   │                                 │
│  │ 去重/合并/简化   │  │ Token 优化       │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  输出：结构化 API 上下文（JSON / Markdown）                                   │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐                 │
│  │ 工具定义（ToolDefinition）│  │ 知识上下文（KnowledgeContext）│                 │
│  │ 自动注册到 ToolRegistry   │  │ 注入到 ContextManager         │                 │
│  └──────────────────────┘  └──────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. API 文档解析器（APIDocParser）

### 5.1 `APIDocParser`

```python
class APIDocParser:
    """API 文档解析器 — 支持多种文档格式。"""
    
    SUPPORTED_FORMATS = ["openapi3", "swagger2", "graphql", "markdown"]
    
    def __init__(self):
        self._parsers = {
            "openapi3": OpenAPI3Parser(),
            "swagger2": Swagger2Parser(),
            "graphql": GraphQLParser(),
            "markdown": MarkdownParser(),
        }
    
    def parse(self, doc_source: str, doc_format: str = "auto") -> Optional[ParsedAPIDoc]:
        """
        解析 API 文档（容错版本）。
        
        参数：
        - doc_source: 文档内容（JSON/YAML/字符串）或 URL
        - doc_format: 文档格式（auto/openapi3/swagger2/graphql/markdown）
        
        返回：
        - ParsedAPIDoc: 解析成功
        - None: 解析失败（URL 下载失败或格式不支持）
        
        注意：此方法不会抛出异常。调用者（如 ToolDiscovery）应检查返回值，
        并在返回 None 时记录日志并跳过，不阻塞系统启动。
        """
        # 自动检测格式
        if doc_format == "auto":
            doc_format = self._detect_format(doc_source)
        
        # 如果 _detect_format 下载失败，返回 None
        if doc_format is None:
            return None
        
        parser = self._parsers.get(doc_format)
        if not parser:
            self._logger.warning(f"Unsupported format: {doc_format}")
            return None
        
        try:
            return parser.parse(doc_source)
        except Exception as e:
            self._logger.warning(f"Parser failed for format {doc_format}: {e}")
            return None
    
    def _detect_format(self, doc_source: str) -> Optional[str]:
        """
        自动检测文档格式（容错版本）。
        
        如果 source 是 URL 且下载失败，返回 None。
        """
        # 如果 source 是 URL，尝试下载并检测
        if doc_source.startswith("http"):
            doc_source = self._download(doc_source)
            if doc_source is None:
                return None  # 下载失败，不抛出异常
        
        # 检测 JSON 中的 swagger/openapi 字段
        if doc_source.strip().startswith("{"):
            try:
                data = json.loads(doc_source)
                if "openapi" in data:
                    return "openapi3"
                elif "swagger" in data:
                    return "swagger2"
            except json.JSONDecodeError:
                pass
        
        # 检测 YAML 中的 openapi 字段
        if doc_source.strip().startswith("openapi:"):
            return "openapi3"
        
        # 检测 GraphQL（包含 type/query/mutation）
        if "type Query" in doc_source or "type Mutation" in doc_source:
            return "graphql"
        
        # 默认 Markdown
        return "markdown"
    
    def _download(self, url: str) -> Optional[str]:
        """
        从 URL 下载文档（容错版本）。
        
        失败处理：
        - 超时（10 秒）：记录警告，返回 None
        - 连接失败：记录警告，返回 None
        - 解析错误：记录警告，返回 None
        
        调用者（ToolDiscovery）应检查返回值，None 表示跳过此文档。
        """
        import urllib.request
        import urllib.error
        import socket
        
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as e:
            self._logger.warning(f"Failed to download API doc from {url}: {e}")
            return None
        except socket.timeout:
            self._logger.warning(f"Timeout downloading API doc from {url}")
            return None
        except Exception as e:
            self._logger.warning(f"Unexpected error downloading {url}: {e}")
            return None
    
    def parse_safe(self, doc_source: str, doc_format: str = "auto") -> Optional[ParsedAPIDoc]:
        """
        安全解析 API 文档（不抛出异常）。
        
        返回：
        - ParsedAPIDoc: 解析成功
        - None: 解析失败（调用者应记录日志并跳过）
        """
        try:
            return self.parse(doc_source, doc_format)
        except Exception as e:
            self._logger.warning(f"Failed to parse API doc: {e}", source=doc_source[:100])
            return None
```

### 5.2 `OpenAPI3Parser`

```python
class OpenAPI3Parser:
    """OpenAPI 3.0 解析器。"""
    
    def parse(self, doc_source: str) -> ParsedAPIDoc:
        """解析 OpenAPI 3.0 文档。"""
        # 解析 YAML/JSON
        if doc_source.strip().startswith("{"):
            spec = json.loads(doc_source)
        else:
            import yaml
            spec = yaml.safe_load(doc_source)
        
        return ParsedAPIDoc(
            title=spec.get("info", {}).get("title", "Unknown API"),
            version=spec.get("info", {}).get("version", "1.0.0"),
            description=spec.get("info", {}).get("description", ""),
            servers=[s["url"] for s in spec.get("servers", [])],
            endpoints=self._extract_endpoints(spec),
            schemas=self._extract_schemas(spec),
            security=spec.get("security", []),
        )
    
    def _extract_endpoints(self, spec: Dict) -> List[APIEndpoint]:
        """提取端点。"""
        endpoints = []
        paths = spec.get("paths", {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    endpoints.append(APIEndpoint(
                        path=path,
                        method=method.upper(),
                        summary=details.get("summary", ""),
                        description=details.get("description", ""),
                        parameters=details.get("parameters", []),
                        request_body=details.get("requestBody", {}),
                        responses=details.get("responses", {}),
                        tags=details.get("tags", []),
                    ))
        
        return endpoints
    
    def _extract_schemas(self, spec: Dict) -> Dict[str, APISchema]:
        """提取 Schema 定义。"""
        schemas = {}
        components = spec.get("components", {})
        schemas_section = components.get("schemas", {})
        
        for name, definition in schemas_section.items():
            schemas[name] = APISchema(
                name=name,
                type=definition.get("type", "object"),
                properties=definition.get("properties", {}),
                required=definition.get("required", []),
                description=definition.get("description", ""),
            )
        
        return schemas
```

---

## 6. Schema 提取器（SchemaExtractor）

### 6.1 `SchemaExtractor`

```python
class SchemaExtractor:
    """Schema 提取器 — 提取和简化数据模型。"""
    
    def extract(self, parsed_doc: ParsedAPIDoc) -> List[APISchema]:
        """提取所有 Schema。"""
        return list(parsed_doc.schemas.values())
    
    def simplify(self, schema: APISchema, max_depth: int = 3) -> SimplifiedSchema:
        """
        简化 Schema，控制嵌套深度。
        
        用于 LLM 上下文：过深的嵌套会消耗大量 Token。
        """
        simplified = SimplifiedSchema(
            name=schema.name,
            type=schema.type,
            description=schema.description,
            fields=[],
        )
        
        for prop_name, prop_def in schema.properties.items():
            field = self._simplify_field(prop_name, prop_def, depth=0, max_depth=max_depth)
            simplified.fields.append(field)
        
        return simplified
    
    def _simplify_field(self, name: str, definition: Dict, depth: int, max_depth: int) -> SchemaField:
        """递归简化字段。"""
        field_type = definition.get("type", "unknown")
        
        # 控制嵌套深度
        if depth >= max_depth:
            return SchemaField(
                name=name,
                type=field_type,
                description=definition.get("description", ""),
                nested=None,
            )
        
        # 处理嵌套对象
        if field_type == "object" and "properties" in definition:
            nested = SimplifiedSchema(
                name=name,
                type="object",
                fields=[
                    self._simplify_field(n, d, depth + 1, max_depth)
                    for n, d in definition["properties"].items()
                ],
            )
            return SchemaField(name=name, type="object", nested=nested)
        
        # 处理数组
        if field_type == "array" and "items" in definition:
            item_type = definition["items"].get("type", "unknown")
            return SchemaField(
                name=name,
                type=f"array[{item_type}]",
                description=definition.get("description", ""),
            )
        
        # 基础类型
        return SchemaField(
            name=name,
            type=field_type,
            description=definition.get("description", ""),
            required=name in definition.get("required", []),
        )
    
    def to_markdown(self, schema: SimplifiedSchema) -> str:
        """转换为 Markdown 格式（用于 LLM 上下文）。"""
        lines = [
            f"## {schema.name}",
            f"{schema.description}",
            "",
            "| Field | Type | Required | Description |",
            "|-------|------|----------|-------------|",
        ]
        
        for field in schema.fields:
            req = "Yes" if field.required else "No"
            lines.append(f"| {field.name} | {field.type} | {req} | {field.description} |")
        
        return "\n".join(lines)
```

---

## 7. 端点提取器（EndpointExtractor）

### 7.1 `EndpointExtractor`

```python
class EndpointExtractor:
    """端点提取器 — 提取和简化 API 端点。"""
    
    def extract(self, parsed_doc: ParsedAPIDoc) -> List[APIEndpoint]:
        """提取所有端点。"""
        return parsed_doc.endpoints
    
    def simplify(self, endpoint: APIEndpoint) -> SimplifiedEndpoint:
        """简化端点信息。"""
        # 简化请求参数
        simplified_params = []
        for param in endpoint.parameters:
            simplified_params.append({
                "name": param.get("name", ""),
                "in": param.get("in", "query"),
                "type": param.get("schema", {}).get("type", "string"),
                "required": param.get("required", False),
                "description": param.get("description", ""),
            })
        
        # 简化响应
        simplified_responses = {}
        for code, response in endpoint.responses.items():
            content = response.get("content", {})
            if "application/json" in content:
                schema = content["application/json"].get("schema", {})
                simplified_responses[code] = {
                    "type": schema.get("type", "object"),
                    "description": response.get("description", ""),
                }
        
        return SimplifiedEndpoint(
            path=endpoint.path,
            method=endpoint.method,
            summary=endpoint.summary,
            description=endpoint.description,
            parameters=simplified_params,
            responses=simplified_responses,
            tags=endpoint.tags,
        )
    
    def to_tool_definition(self, endpoint: SimplifiedEndpoint, base_url: str) -> ToolDefinition:
        """转换为 ToolDefinition（用于 ToolRegistry）。"""
        # 构建参数 Schema
        properties = {}
        required = []
        
        for param in endpoint.parameters:
            properties[param["name"]] = {
                "type": param["type"],
                "description": param["description"],
            }
            if param["required"]:
                required.append(param["name"])
        
        return ToolDefinition(
            name=f"{endpoint.method.lower()}_{endpoint.path.replace('/', '_').replace('{', '').replace('}', '')}",
            description=f"{endpoint.summary}: {endpoint.description}",
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
            external_endpoint=f"{base_url}{endpoint.path}",
            tags=endpoint.tags,
        )
```

---

## 8. 文档标准化器（DocNormalizer）

### 8.1 `DocNormalizer`

```python
class DocNormalizer:
    """文档标准化器 — 统一文档格式。"""
    
    def normalize(self, parsed_doc: ParsedAPIDoc) -> NormalizedAPIDoc:
        """标准化文档。"""
        return NormalizedAPIDoc(
            title=parsed_doc.title,
            version=parsed_doc.version,
            description=self._clean_description(parsed_doc.description),
            servers=parsed_doc.servers,
            endpoints=[self._normalize_endpoint(e) for e in parsed_doc.endpoints],
            schemas=[self._normalize_schema(s) for s in parsed_doc.schemas.values()],
        )
    
    def _clean_description(self, description: str) -> str:
        """清理描述文本。"""
        if not description:
            return ""
        
        # 移除 HTML 标签
        import re
        description = re.sub(r'<[^>]+>', '', description)
        
        # 移除多余空行
        description = "\n".join(line for line in description.split("\n") if line.strip())
        
        # 截断过长描述（>1000 字符）
        if len(description) > 1000:
            description = description[:997] + "..."
        
        return description
    
    def _normalize_endpoint(self, endpoint: APIEndpoint) -> NormalizedEndpoint:
        """标准化端点。"""
        return NormalizedEndpoint(
            path=endpoint.path,
            method=endpoint.method,
            summary=endpoint.summary or endpoint.description[:100],
            description=self._clean_description(endpoint.description),
            tags=endpoint.tags,
        )
    
    def _normalize_schema(self, schema: APISchema) -> NormalizedSchema:
        """标准化 Schema。"""
        return NormalizedSchema(
            name=schema.name,
            type=schema.type,
            description=self._clean_description(schema.description),
            fields=list(schema.properties.keys())[:20],  # 限制字段数量
        )
```

---

## 9. 上下文构建器（ContextBuilder）

### 9.1 `ContextBuilder`

```python
class ContextBuilder:
    """上下文构建器 — 构建 LLM 可用的 API 上下文。"""
    
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self._token_estimate = 0  # 粗略 Token 计数
    
    def build(self, normalized_doc: NormalizedAPIDoc) -> APIContext:
        """构建 API 上下文。"""
        sections = []
        
        # 1. API 概览
        sections.append(self._build_overview(normalized_doc))
        
        # 2. 端点列表（按标签分组）
        sections.append(self._build_endpoints(normalized_doc))
        
        # 3. 关键 Schema
        sections.append(self._build_schemas(normalized_doc))
        
        # 合并并截断
        context = "\n\n".join(sections)
        if self._token_estimate > self.max_tokens:
            context = self._truncate(context)
        
        return APIContext(
            title=normalized_doc.title,
            content=context,
            token_estimate=self._token_estimate,
        )
    
    def _build_overview(self, doc: NormalizedAPIDoc) -> str:
        """构建 API 概览。"""
        self._token_estimate += 100
        return f"""# {doc.title} (v{doc.version})

{doc.description}

Base URL: {doc.servers[0] if doc.servers else "N/A"}
"""
    
    def _build_endpoints(self, doc: NormalizedAPIDoc) -> str:
        """构建端点列表。"""
        lines = ["## Endpoints"]
        
        # 按标签分组
        by_tag = defaultdict(list)
        for endpoint in doc.endpoints:
            tag = endpoint.tags[0] if endpoint.tags else "General"
            by_tag[tag].append(endpoint)
        
        for tag, endpoints in by_tag.items():
            lines.append(f"\n### {tag}")
            for endpoint in endpoints[:10]:  # 每标签限制 10 个
                lines.append(f"- `{endpoint.method}` {endpoint.path}: {endpoint.summary}")
                self._token_estimate += 20
        
        return "\n".join(lines)
    
    def _build_schemas(self, doc: NormalizedAPIDoc) -> str:
        """构建关键 Schema。"""
        lines = ["## Key Schemas"]
        
        for schema in doc.schemas[:5]:  # 限制 5 个关键 Schema
            lines.append(f"\n### {schema.name}")
            lines.append(f"Type: {schema.type}")
            lines.append(f"Fields: {', '.join(schema.fields)}")
            self._token_estimate += 50
        
        return "\n".join(lines)
    
    def _truncate(self, context: str) -> str:
        """截断上下文至 Token 限制。"""
        # 简单策略：保留概览，截断端点和 Schema
        lines = context.split("\n")
        
        # 保留概览部分（直到第一个 ##）
        truncated = []
        for line in lines:
            if line.startswith("## Endpoints") and self._token_estimate > self.max_tokens:
                break
            truncated.append(line)
        
        truncated.append("\n... (truncated due to token limit)")
        return "\n".join(truncated)
```

---

## 10. 与 6 个 LLM 实例的集成

### 10.1 每个 LLM 的 API 文档使用场景

| LLM 实例 | 使用场景 | 上下文类型 |
|----------|---------|-----------|
| **PCR-LLM** | 分析用户输入是否涉及 API 调用 | 工具名称列表 |
| **Intent-LLM** | 理解用户意图是否需要调用 API | 工具描述 |
| **Planning-LLM** | 生成 API 调用计划 | 完整端点 + Schema |
| **Meta-Cognitive-LLM** | 验证 API 调用参数是否正确 | 参数 Schema |
| **Reflective-LLM** | 分析 API 调用模式 | 历史调用记录 |
| **Answer-LLM** | 解释 API 返回结果 | 响应 Schema |

### 10.2 与 ToolDiscovery 的集成

```python
# 从 OpenAPI 文档自动注册工具
def auto_register_from_openapi(registry: ToolRegistry, openapi_url: str):
    """从 OpenAPI 文档自动注册工具。"""
    parser = APIDocParser()
    parsed = parser.parse(openapi_url)
    
    extractor = EndpointExtractor()
    base_url = parsed.servers[0] if parsed.servers else ""
    
    for endpoint in parsed.endpoints:
        simplified = extractor.simplify(endpoint)
        tool = extractor.to_tool_definition(simplified, base_url)
        registry.register(tool)
```

---

## 11. 测试策略

### 11.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 解析、提取、标准化、上下文构建 |
| 集成测试 | 90% | 从 OpenAPI 到 ToolDefinition 的完整链路 |
| 性能测试 | 80% | 大文档解析性能（>1MB） |

### 11.2 关键测试用例

**用例 1：OpenAPI 解析**
```python
def test_openapi_parse():
    parser = OpenAPI3Parser()
    doc = parser.parse("""
    openapi: 3.0.0
    info:
      title: Test API
      version: 1.0.0
    paths:
      /users:
        get:
          summary: List users
          responses:
            200:
              description: OK
    """)
    
    assert doc.title == "Test API"
    assert len(doc.endpoints) == 1
    assert doc.endpoints[0].path == "/users"
    assert doc.endpoints[0].method == "GET"
```

**用例 2：上下文 Token 限制**
```python
def test_context_truncate():
    builder = ContextBuilder(max_tokens=500)
    
    # 构建大文档上下文
    doc = NormalizedAPIDoc(
        title="Large API",
        endpoints=[NormalizedEndpoint(path=f"/endpoint{i}", method="GET", summary=f"Endpoint {i}") for i in range(100)],
        schemas=[],
    )
    
    context = builder.build(doc)
    assert context.token_estimate <= 500
    assert "... (truncated" in context.content
```

---

## 12. 附录：简化与待讨论项

### 12.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | GraphQL 解析 | 支持 GraphQL introspection | 接口预留 | GraphQL 使用较少 | Phase 2 引入 GraphQL 解析 |
| **S-02** | 文档缓存 | 缓存解析结果，避免重复下载 | 无缓存 | 缓存增加存储复杂度 | Phase 2 引入 Redis 缓存 |
| **S-03** | 增量更新 | 检测文档变更，只更新变更部分 | 全量重新解析 | 增量更新需要版本对比 | Phase 2 引入版本对比 |
| **S-04** | 认证解析 | 解析 OAuth/API Key 等认证方式 | 基础 security 字段 | 完整认证解析复杂 | Phase 2 引入认证解析 |
| **S-05** | 代码示例生成 | 自动生成调用示例 | 无 | 示例生成需要模板 | Phase 2 引入示例生成 |

### 12.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 文档更新频率 | A) 手动触发  B) 启动时检查  C) 定时轮询 | 建议 B：启动时检查，避免运行时变更 |
| **D-02** | 多文档合并 | A) 独立上下文  B) 合并为一个上下文  C) 按标签分组 | 建议 C：按标签分组，保持清晰 |
| **D-03** | 文档来源验证 | A) 不验证  B) 验证 HTTPS 证书  C) 验证数字签名 | 建议 B：验证 HTTPS 证书，防止中间人攻击 |
| **D-04** | 敏感信息过滤 | A) 不过滤  B) 过滤 API Key 示例  C) 过滤所有认证信息 | 建议 B：过滤 API Key 示例，避免泄露 |

### 12.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md`（API 文档） | §5-§9 | ✅ 等价 | 解析/提取/标准化/上下文构建全部覆盖 |
| `ENGINEERING_TOOL_REGISTRY.md` | §10 | ✅ 等价 | 与 ToolRegistry 的集成覆盖 |
| `ENGINEERING_CONTEXT_MANAGER.md` | §9 | ✅ 等价 | 上下文构建与 Token 管理对齐 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档生成。新增约 **600 行代码**（APIDocParser + SchemaExtractor + EndpointExtractor + DocNormalizer + ContextBuilder）。所有简化项已在 §12.1 中诚实标记，待讨论项在 §12.2 中列出，等待团队确认。*
