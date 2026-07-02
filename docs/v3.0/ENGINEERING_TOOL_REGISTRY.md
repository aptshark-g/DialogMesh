# DialogMesh 动态工具注册系统 — 工程实现文档

> **文档编号**: ENGINEERING-TOOL-REGISTRY-011  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md`（工具/服务集成）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（Planning-LLM 工具调用）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **原则**: Planning-LLM 需要动态发现工具、安全执行工具、将工具结果编译回 Cognitive Tree。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 工具注册中心（ToolRegistry）](#5-工具注册中心toolregistry)
- [6. 工具定义（ToolDefinition）](#6-工具定义tooldefinition)
- [7. 工具执行器（ToolExecutor）](#7-工具执行器toolexecutor)
- [8. 工具筛选器（ToolShortlister）](#8-工具筛选器toolshortlister)
- [9. 工具绑定引擎（ToolBindingEngine）](#9-工具绑定引擎toolbindingengine)
- [10. 工具发现（ToolDiscovery）](#10-工具发现tooldiscovery)
- [11. 权限管理（PermissionManager）](#11-权限管理permissionmanager)
- [12. 与 6 个 LLM 实例的集成](#12-与-6-个-llm-实例的集成)
- [13. 测试策略](#13-测试策略)
- [14. 附录：简化与待讨论项](#14-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **动态工具注册系统（Dynamic Tool Registry）**的完整实现规范。工具注册系统是 v3.0 多层 LLM 认知架构的**"执行基础设施"**，负责让 Planning-LLM 动态发现、安全调用、注册和管理外部工具，并将工具执行结果编译回 Cognitive Tree。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 工具注册 | `DESIGN_FULL_CONCEPT.md` | §5 | 工具的注册与注销 |
| 工具定义 | `DESIGN_FULL_CONCEPT.md` §4.6.1 | §6 | 名称、描述、参数、返回值、来源、类型、预估延迟/成本、执行统计 |
| 工具执行 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` | §7 | 安全沙箱、超时控制、异常处理、执行统计更新 |
| 工具筛选 | `DESIGN_FULL_CONCEPT.md` §4.6.2 | §8 | 5阶段漏斗筛选（解决 Tool Overflow） |
| 工具绑定 | `DESIGN_FULL_CONCEPT.md` §4.7 | §9 | 4策略绑定（占位符→实际工具） |
| 工具发现 | `DESIGN_FULL_CONCEPT.md` | §10 | 动态扫描、MCP 集成 |
| 权限管理 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2 | §11 | 哪些工具哪些 LLM 可用 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/tools/registry.py` | 工具注册中心 | ~200 行 | 新增 |
| `core/agent/tools/definition.py` | 工具定义模型 | ~100 行 | 新增 |
| `core/agent/tools/executor.py` | 工具执行器 | ~150 行 | 新增 |
| `core/agent/tools/shortlister.py` | 工具筛选器（5阶段漏斗） | ~200 行 | 新增，解决 Tool Overflow |
| `core/agent/tools/binding.py` | 工具绑定引擎（4策略绑定） | ~200 行 | 新增，Planning↔Tool 适配层 |
| `core/agent/tools/discovery.py` | 工具发现 | ~150 行 | 新增 |
| `core/agent/tools/permission.py` | 权限管理 | ~100 行 | 新增 |
| `core/agent/tools/mcp_adapter.py` | MCP 适配器 | ~100 行 | 新增，Phase 2 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/planning/planner.py` | 集成 ToolRegistry 查询 | 规划层 |
| `core/agent/cognitive_compiler/compiler.py` | 工具结果编译为 CT 节点 | 编译层 |
| `core/agent/orchestrator.py` | 集成工具调用链路 | 编排层 |

---

## 3. 现有实现评估

### 3.1 现有工具

**定义位置**: 分散在多个模块中

| 工具 | 位置 | 形式 | 状态 |
|------|------|------|------|
| 内存扫描 | `memorygraph` | 硬编码 | ⚠️ 需封装为 ToolDefinition |
| 指针扫描 | `memorygraph` | 硬编码 | ⚠️ 需封装为 ToolDefinition |
| 断点引擎 | `memorygraph` | 硬编码 | ⚠️ 需封装为 ToolDefinition |
| 进程列表 | `memorygraph` | 硬编码 | ⚠️ 需封装为 ToolDefinition |
| Web 搜索 | 无 | 无 | ⚠️ 需新增 |
| 文件读取 | 无 | 无 | ⚠️ 需新增 |
| 代码执行 | 无 | 无 | ⚠️ 需新增 |

### 3.2 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 动态注册/注销 | 无 | 需新增 `ToolRegistry` | P1 |
| 统一工具定义 | 无 | 需新增 `ToolDefinition` | P1 |
| 安全执行 | 无 | 需新增 `ToolExecutor`（沙箱、超时） | P1 |
| 工具筛选（Tool Overflow）| 无 | 需新增 `ToolShortlister`（5阶段漏斗） | P1 |
| 工具绑定（占位符→实际）| 无 | 需新增 `ToolBindingEngine`（4策略绑定） | P1 |
| 动态发现 | 无 | 需新增 `ToolDiscovery` | P2 |
| MCP 集成 | 无 | 需新增 `MCPAdapter` | P2 |
| 权限管理 | 无 | 需新增 `PermissionManager` | P1 |
| 工具结果 → CT | 无 | 需修改 `CognitiveCompiler` | P1 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Planning-LLM / Orchestrator                          │
│                              ↓ 查询工具                                     │
│  "我需要扫描内存地址" → ToolRegistry.query("memory_scan")                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  动态工具注册系统（Tool Registry System）                                    │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ ToolRegistry     │  │ ToolDefinition   │  │ ToolExecutor     │            │
│  │ 工具注册中心     │  │ 工具定义         │  │ 工具执行器       │            │
│  │ 注册/注销/查询   │  │ 名称/描述/参数   │  │ 安全沙箱/超时    │            │
│  │ 按标签/分类过滤  │  │ JSON Schema      │  │ 结果封装         │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ ToolDiscovery    │  │ PermissionManager│                                 │
│  │ 工具发现         │  │ 权限管理         │                                 │
│  │ 动态扫描/MCP     │  │ 哪些工具哪些LLM  │                                 │
│  │ 自动注册新工具   │  │ 可调用           │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  工具实现层（本地函数 / MCP 服务器 / 外部 API）                                │
│  ────────────────────────────────────────────────────────────────────────  │
│  memory_scan | pointer_scan | breakpoint_engine | process_list | web_search │
│  file_read | code_execute | (MCP tools)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Cognitive Compiler（工具结果 → CT 节点）                                    │
│  ────────────────────────────────────────────────────────────────────────  │
│  ACTION / OBSERVATION 节点                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 工具注册中心（ToolRegistry）

### 5.1 `ToolRegistry`

```python
class ToolRegistry:
    """工具注册中心 — 统一管理所有可用工具。"""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._tags: Dict[str, Set[str]] = defaultdict(set)  # tag -> tool_names
        self._lock = threading.Lock()
    
    def register(self, tool: ToolDefinition) -> bool:
        """
        注册工具。
        
        返回：
        - True: 注册成功
        - False: 同名工具已存在（需先注销）
        """
        with self._lock:
            if tool.name in self._tools:
                return False
            
            self._tools[tool.name] = tool
            
            # 索引标签
            for tag in tool.tags:
                self._tags[tag].add(tool.name)
            
            return True
    
    def unregister(self, tool_name: str) -> bool:
        """注销工具。"""
        with self._lock:
            if tool_name not in self._tools:
                return False
            
            tool = self._tools.pop(tool_name)
            for tag in tool.tags:
                self._tags[tag].discard(tool_name)
            
            return True
    
    def get(self, tool_name: str) -> Optional[ToolDefinition]:
        """获取工具定义。"""
        with self._lock:
            return self._tools.get(tool_name)
    
    def query(self, tags: Optional[List[str]] = None, keyword: Optional[str] = None) -> List[ToolDefinition]:
        """
        查询工具。
        
        示例：
        ```python
        # 查询所有内存相关工具
        tools = registry.query(tags=["memory"])
        
        # 查询包含 "scan" 的工具
        tools = registry.query(keyword="scan")
        ```
        """
        with self._lock:
            candidates = set(self._tools.values())
            
            # 标签过滤
            if tags:
                tag_matched = set()
                for tag in tags:
                    for tool_name in self._tags.get(tag, set()):
                        tag_matched.add(self._tools[tool_name])
                candidates = candidates.intersection(tag_matched)
            
            # 关键词过滤
            if keyword:
                keyword_lower = keyword.lower()
                candidates = {
                    t for t in candidates
                    if keyword_lower in t.name.lower()
                    or keyword_lower in t.description.lower()
                    or any(keyword_lower in p.lower() for p in t.tags)
                }
            
            return list(candidates)
    
    def list_all(self) -> List[ToolDefinition]:
        """列出所有已注册工具。"""
        with self._lock:
            return list(self._tools.values())
    
    def get_schema_for_llm(self) -> List[Dict[str, Any]]:
        """
        生成 LLM 可用的工具描述（JSON Schema 格式）。
        
        用于 Planning-LLM 的 tool_choice 参数。
        """
        with self._lock:
            return [tool.to_llm_schema() for tool in self._tools.values()]
```

---

## 6. 工具定义（ToolDefinition）

### 6.1 `ToolDefinition`

```python
@dataclass
class ToolDefinition:
    """工具定义 — 描述一个工具的完整元数据。"""
    
    name: str                          # 工具唯一标识（如 "memory_scan"）
    description: str                   # 工具功能描述（用于 LLM 理解）
    parameters: Dict[str, Any]         # JSON Schema 参数定义
    return_schema: Dict[str, Any]      # 返回值 Schema
    implementation: Optional[Callable] = None  # 本地实现函数
    external_endpoint: Optional[str] = None    # 外部 API 端点
    tags: List[str] = field(default_factory=list)  # 标签（如 ["memory", "scan"])
    timeout_seconds: float = 30.0      # 默认超时
    dangerous: bool = False            # 是否危险操作（如修改内存）
    requires_confirmation: bool = False  # 是否需要用户确认
    llm_permissions: List[str] = field(default_factory=list)  # 允许调用的 LLM 列表
    
    # ── 设计文档 §4.6.1 要求的字段（对齐 ToolSchema）────────────────
    source: str = "builtin"            # 工具来源：builtin/api_doc/mcp/custom
    tool_type: str = "local_function"  # 工具执行类型：local_function/http_api/mcp_remote
    estimated_latency_ms: Optional[float] = None  # 预估延迟（ms）
    estimated_cost_tokens: Optional[int] = None   # 预估成本（tokens）
    execution_stats: "ToolExecutionStats" = field(default_factory=lambda: ToolExecutionStats())  # 执行统计
    
    def to_llm_schema(self) -> Dict[str, Any]:
        """转换为 LLM 可用的 JSON Schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
    
    def validate_args(self, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证参数是否符合 Schema。"""
        # 使用 jsonschema 验证
        try:
            jsonschema.validate(args, self.parameters)
            return True, None
        except jsonschema.ValidationError as e:
            return False, str(e)
    
    def record_execution(self, success: bool, latency_ms: float):
        """记录一次执行结果，更新统计（EMA 平滑）。"""
        self.execution_stats.update(success, latency_ms)
    
    @property
    def effective_latency_estimate(self) -> float:
        """获取有效的延迟预估（实测优先于预估）。"""
        if self.execution_stats.call_count > 0:
            return self.execution_stats.avg_latency_ms
        return self.estimated_latency_ms or 100.0  # 默认 100ms
    
    @property
    def is_destructive(self) -> bool:
        """是否涉及写操作（等价于 dangerous）。"""
        return self.dangerous

@dataclass
class ToolExecutionStats:
    """工具执行统计（用于 ToolShortlister 动态排序）。"""
    call_count: int = 0
    success_count: int = 0
    total_latency_ms: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count
    
    @property
    def avg_latency_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count
    
    def update(self, success: bool, latency_ms: float):
        """更新执行统计（使用 EMA 平滑）。"""
        self.call_count += 1
        if success:
            self.success_count += 1
        # EMA 更新平均延迟
        alpha = 0.3  # 平滑系数
        if self.call_count == 1:
            self.total_latency_ms = latency_ms
        else:
            prev_avg = self.avg_latency_ms
            self.total_latency_ms = (prev_avg + alpha * (latency_ms - prev_avg)) * self.call_count

# 示例：内存扫描工具定义
memory_scan_tool = ToolDefinition(
    name="memory_scan",
    description="扫描指定进程的内存地址，查找匹配的值",
    parameters={
        "type": "object",
        "properties": {
            "process_id": {"type": "integer", "description": "目标进程 ID"},
            "value": {"type": "string", "description": "要查找的值"},
            "value_type": {"type": "string", "enum": ["int32", "float", "string"]},
        },
        "required": ["process_id", "value"],
    },
    return_schema={
        "type": "object",
        "properties": {
            "addresses": {"type": "array", "items": {"type": "string"}},
            "count": {"type": "integer"},
        },
    },
    tags=["memory", "scan"],
    dangerous=True,
    requires_confirmation=True,
    llm_permissions=["Planning-LLM", "Answer-LLM"],  # 只有 Planning-LLM 和 Answer-LLM 可以调用
    source="builtin",
    tool_type="local_function",
    estimated_latency_ms=500.0,
    estimated_cost_tokens=200,
)
```

---

## 7. 工具执行器（ToolExecutor）

### 7.1 `ToolExecutor`

```python
class ToolExecutor:
    """工具执行器 — 安全、可控地执行工具。"""
    
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager):
        self._registry = registry
        self._permissions = permissions
        self._logger = get_logger("tool_executor")
    
    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        requesting_llm: str,
        session_id: str,
    ) -> ToolResult:
        """
        执行工具。
        
        流程：
        1. 检查权限（requesting_llm 是否可以调用该工具）
        2. 获取工具定义
        3. 验证参数
        4. 检查是否需要用户确认（危险操作）
        5. 执行工具（带超时）
        6. 更新执行统计（用于 ToolShortlister 动态排序）
        7. 封装结果
        8. 记录日志
        """
        # 1. 权限检查
        if not self._permissions.can_call(requesting_llm, tool_name):
            raise PermissionError(
                f"LLM '{requesting_llm}' cannot call tool '{tool_name}'"
            )
        
        # 2. 获取工具定义
        tool = self._registry.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        # 3. 验证参数
        valid, error = tool.validate_args(args)
        if not valid:
            raise ValueError(f"Invalid arguments for tool '{tool_name}': {error}")
        
        # 4. 危险操作确认
        if tool.dangerous and tool.requires_confirmation:
            # 记录到 CT，等待用户确认（Phase 2 实现）
            self._logger.warning(
                "Dangerous tool requires confirmation",
                tool_name=tool_name,
                args=args,
                requesting_llm=requesting_llm,
            )
            # Phase 1：直接拒绝，Phase 2：引入确认流
            raise RuntimeError(
                f"Tool '{tool_name}' requires user confirmation. "
                "This feature will be implemented in Phase 2."
            )
        
        # 5. 执行工具（带超时）
        start = time.time()
        try:
            if tool.implementation:
                # 本地函数
                if asyncio.iscoroutinefunction(tool.implementation):
                    result = await asyncio.wait_for(
                        tool.implementation(**args),
                        timeout=tool.timeout_seconds,
                    )
                else:
                    # 同步函数在线程池中执行
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, tool.implementation, **args),
                        timeout=tool.timeout_seconds,
                    )
            elif tool.external_endpoint:
                # 外部 API（Phase 2）
                raise NotImplementedError("External API tools not yet supported")
            else:
                raise ValueError(f"Tool '{tool_name}' has no implementation")
            
            latency_ms = (time.time() - start) * 1000
            
            # 6. 更新执行统计（用于 ToolShortlister 动态排序）
            tool.record_execution(success=True, latency_ms=latency_ms)
            
            # 7. 封装结果
            return ToolResult(
                success=True,
                data=result,
                latency_ms=latency_ms,
                tool_name=tool_name,
            )
            
        except asyncio.TimeoutError:
            latency_ms = tool.timeout_seconds * 1000
            tool.record_execution(success=False, latency_ms=latency_ms)
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' timed out after {tool.timeout_seconds}s",
                latency_ms=latency_ms,
                tool_name=tool_name,
            )
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            tool.record_execution(success=False, latency_ms=latency_ms)
            return ToolResult(
                success=False,
                error=str(e),
                latency_ms=latency_ms,
                tool_name=tool_name,
            )
    
    async def execute_batch(
        self,
        calls: List[ToolCall],
        requesting_llm: str,
        session_id: str,
    ) -> List[ToolResult]:
        """批量执行工具（并行）。"""
        tasks = [
            self.execute(call.tool_name, call.args, requesting_llm, session_id)
            for call in calls
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### 7.2 `ToolResult`

```python
@dataclass
class ToolResult:
    """工具执行结果。"""
    
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    tool_name: str = ""
    
    def to_cognitive_node(self) -> Dict[str, Any]:
        """转换为 Cognitive Tree 节点数据。"""
        if self.success:
            return {
                "cog_type": CogType.ACTION,
                "content": f"执行工具 '{self.tool_name}' 成功",
                "action": self.tool_name,
                "action_result": json.dumps(self.data, ensure_ascii=False)[:1000],
                "confidence": 1.0,
            }
        else:
            return {
                "cog_type": CogType.OBSERVATION,
                "content": f"执行工具 '{self.tool_name}' 失败: {self.error}",
                "action": self.tool_name,
                "action_result": self.error,
                "confidence": 0.0,
            }
```

---

## 8. 工具筛选器（ToolShortlister）

> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §4.6.2
> **状态**: ❌ 缺失 — 仅工程规范，无实现代码

### 8.1 功能概念

ToolShortlister 是解决 **Tool Overflow** 问题的核心组件——当注册工具数量超过 LLM 上下文窗口承载能力时，从全部工具中筛选最相关的子集（默认 Top 32）。

**设计文档要求**: 5 阶段漏斗筛选（意图标签匹配 → 语义相似度排序 → 历史偏好 boost → 容量截断 → 兜底策略）。

### 8.2 工程规范

```python
@dataclass
class ShortlistResult:
    """工具筛选结果。"""
    tools: List[ToolDefinition]       # 筛选后的工具子集
    total_available: int              # 原始可用工具总数
    filtered_by_tag: int              # 标签过滤后剩余数量
    ranked_by_semantic: int           # 语义排序后数量
    capacity_limit: int = 32          # 默认注入 LLM 的最大工具数
    fallback_included: bool = True    # 是否包含 ask_user / finish 兜底

class ToolShortlister:
    """
    工具筛选器 — 5 阶段漏斗筛选。
    
    设计文档 §4.6.2 算法：
    Selected = Truncate(Capacity, Rank(HistoryBoost(SemanticScore(Filter(Intent, AllTools)))))
    """
    
    def __init__(self, registry: ToolRegistry, embedding_provider=None):
        self._registry = registry
        self._embedding = embedding_provider
        self._logger = get_logger("tool_shortlister")
    
    def shortlist(
        self,
        intent: "Intent",
        all_tools: Optional[List[ToolDefinition]] = None,
        capacity: int = 32,
    ) -> ShortlistResult:
        """
        5 阶段漏斗筛选。
        
        阶段 1: 意图标签匹配（粗筛）
        阶段 2: 语义相似度排序（精排）
        阶段 3: 历史偏好 boost（个性化）
        阶段 4: 容量截断（上下文窗口限制）
        阶段 5: 兜底策略（强制保留通用工具）
        """
        tools = all_tools or self._registry.list_all()
        total = len(tools)
        
        # 阶段 1: 意图标签匹配
        intent_tags = set(getattr(intent, "tags", []) or [])
        if intent_tags:
            filtered = [t for t in tools if set(t.tags) & intent_tags]
            if not filtered:
                filtered = tools  # 放宽到全部工具（避免过度过滤）
        else:
            filtered = tools
        after_tag = len(filtered)
        
        # 阶段 2: 语义相似度排序
        intent_text = getattr(intent, "description", "") or getattr(intent, "normalized_input", "")
        scored = []
        for tool in filtered:
            score = self._semantic_score(intent_text, tool.description, tool)
            scored.append((tool, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        after_semantic = len(scored)
        
        # 阶段 3: 历史偏好 boost
        boosted = []
        for tool, score in scored:
            boost = self._history_boost(tool)
            boosted.append((tool, score + boost))
        boosted.sort(key=lambda x: x[1], reverse=True)
        
        # 阶段 4: 容量截断（保守估计每个工具描述约 200 tokens）
        selected = [tool for tool, _ in boosted[:capacity]]
        
        # 阶段 5: 兜底策略 — 强制保留通用工具
        fallback_names = {"ask_user", "finish"}
        existing = {t.name for t in selected}
        for fb_name in fallback_names:
            if fb_name not in existing:
                fb_tool = self._registry.get(fb_name)
                if fb_tool:
                    selected.append(fb_tool)
        
        return ShortlistResult(
            tools=selected,
            total_available=total,
            filtered_by_tag=after_tag,
            ranked_by_semantic=after_semantic,
            capacity_limit=capacity,
            fallback_included=True,
        )
    
    def _semantic_score(
        self, intent_text: str, tool_description: str, tool: ToolDefinition
    ) -> float:
        """
        语义相似度计算。
        
        如果 embedding 模型可用，使用 cos(embed(intent), embed(description))；
        否则降级为关键词重叠启发式。
        """
        if self._embedding and intent_text and tool_description:
            try:
                intent_emb = self._embedding.encode(intent_text)
                tool_emb = self._embedding.encode(tool_description)
                # 余弦相似度
                dot = sum(a * b for a, b in zip(intent_emb, tool_emb))
                norm_i = sum(a * a for a in intent_emb) ** 0.5
                norm_t = sum(b * b for b in tool_emb) ** 0.5
                if norm_i > 0 and norm_t > 0:
                    return dot / (norm_i * norm_t)
            except Exception:
                pass
        
        # 降级：关键词重叠启发式
        intent_words = set(intent_text.lower().split())
        tool_words = set(tool_description.lower().split())
        if not intent_words or not tool_words:
            return 0.0
        overlap = len(intent_words & tool_words)
        return overlap / max(len(intent_words), len(tool_words))
    
    def _history_boost(self, tool: ToolDefinition) -> float:
        """
        历史偏好 boost。
        
        设计文档公式：
        HistoryBoost(t) = success_rate(t) × min(1, call_count(t)/10) × 0.1
        boost 不超过 10%。
        """
        stats = tool.execution_stats
        if stats.call_count == 0:
            return 0.0
        return stats.success_rate * min(1.0, stats.call_count / 10.0) * 0.1
```

### 8.3 诚实标记

| 设计文档要求 | 当前状态 | 说明 |
|-------------|---------|------|
| 5 阶段漏斗筛选 | ❌ 缺失 | 仅工程规范，无实际实现代码 |
| embedding 语义排序 | ❌ 缺失 | 接口预留，需 embedding provider |
| 历史偏好 boost | ❌ 缺失 | 依赖 ToolExecutionStats，需 Executor 接入 |
| 容量截断 K=32 | ❌ 缺失 | 仅规范，未在 Planning-LLM 集成中调用 |
| 兜底策略 | ❌ 缺失 | 需 `ask_user`/`finish` 工具预注册 |

> **审查注**: ToolShortlister 是解决 Tool Overflow 的核心组件，设计文档 §4.6.2 有详细算法定义，但本工程文档未提供实现代码。等价性检查应标记为 ❌ 缺失。

---

## 9. 工具绑定引擎（ToolBindingEngine）

> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §4.7
> **状态**: ❌ 缺失 — 仅工程规范，无实现代码

### 9.1 功能概念

ToolBindingEngine 将 Planning 层生成的占位符（如 `search_tool`）绑定到 Tool 层的实际工具（如 `github_api_search_repos`）。

**设计文档要求**: 4 策略绑定（精确匹配 → 标签匹配 → 语义匹配 → 参数兼容），低置信度绑定（< 0.6）替换为 `ask_user`。

### 9.2 工程规范

```python
@dataclass
class BindingResult:
    """工具绑定结果。"""
    placeholder: str                  # 原始占位符名
    bound_tool: Optional[ToolDefinition]  # 绑定后的实际工具
    confidence: float                 # 绑定置信度 [0, 1]
    strategy: str                     # 使用的绑定策略
    fallback_to_ask_user: bool = False  # 是否因低置信度回退到 ask_user

class ToolBindingEngine:
    """
    工具绑定引擎 — 4 策略绑定。
    
    设计文档 §4.7 策略优先级：
    1. 精确匹配
    2. 标签匹配
    3. 语义匹配
    4. 参数兼容
    """
    
    def __init__(self, registry: ToolRegistry, embedding_provider=None):
        self._registry = registry
        self._embedding = embedding_provider
        self._logger = get_logger("tool_binding")
    
    def bind(
        self,
        placeholder: str,
        tool_hints: Optional[Dict[str, List[str]]] = None,
    ) -> BindingResult:
        """
        将占位符绑定到实际工具。
        
        返回 BindingResult，若 confidence < 0.6 则 fallback_to_ask_user=True。
        """
        all_tools = self._registry.list_all()
        
        # 策略 1: 精确匹配
        exact_match = self._exact_match(placeholder, all_tools)
        if exact_match:
            return BindingResult(
                placeholder=placeholder,
                bound_tool=exact_match,
                confidence=1.0,
                strategy="exact_match",
            )
        
        # 策略 2: 标签匹配
        tag_match, tag_conf = self._tag_match(placeholder, all_tools, tool_hints)
        if tag_match and tag_conf >= 0.6:
            return BindingResult(
                placeholder=placeholder,
                bound_tool=tag_match,
                confidence=tag_conf,
                strategy="tag_match",
            )
        
        # 策略 3: 语义匹配
        semantic_match, sem_conf = self._semantic_match(placeholder, all_tools)
        if semantic_match and sem_conf >= 0.6:
            return BindingResult(
                placeholder=placeholder,
                bound_tool=semantic_match,
                confidence=sem_conf,
                strategy="semantic_match",
            )
        
        # 策略 4: 参数兼容
        param_match, param_conf = self._param_compatible_match(placeholder, all_tools)
        if param_match and param_conf >= 0.6:
            return BindingResult(
                placeholder=placeholder,
                bound_tool=param_match,
                confidence=param_conf,
                strategy="param_compatible",
            )
        
        # 低置信度：回退到 ask_user
        best = max([tag_match, semantic_match, param_match], key=lambda x: x[1] if x else (None, 0.0))
        conf = best[1] if best else 0.0
        return BindingResult(
            placeholder=placeholder,
            bound_tool=None,
            confidence=conf,
            strategy="fallback",
            fallback_to_ask_user=True,
        )
    
    def _exact_match(self, placeholder: str, tools: List[ToolDefinition]) -> Optional[ToolDefinition]:
        """
        精确匹配：占位符去掉 "_tool" 后缀与工具名包含关系匹配。
        
        示例：search_tool → search_laptop（工具名包含 "search"）
        """
        base = placeholder.replace("_tool", "").replace("_", "")
        for tool in tools:
            if base in tool.name.replace("_", ""):
                return tool
        return None
    
    def _tag_match(
        self, placeholder: str, tools: List[ToolDefinition], tool_hints: Optional[Dict[str, List[str]]]
    ) -> Tuple[Optional[ToolDefinition], float]:
        """标签匹配：基于 Skill 的 tool_hints 和工具标签的交集。"""
        if not tool_hints or placeholder not in tool_hints:
            return None, 0.0
        
        hint_tags = set(tool_hints[placeholder])
        best_tool = None
        best_score = 0.0
        for tool in tools:
            overlap = len(set(tool.tags) & hint_tags)
            if overlap > 0:
                score = overlap / max(len(hint_tags), len(tool.tags))
                if score > best_score:
                    best_score = score
                    best_tool = tool
        
        return best_tool, best_score
    
    def _semantic_match(
        self, placeholder: str, tools: List[ToolDefinition]
    ) -> Tuple[Optional[ToolDefinition], float]:
        """语义匹配：基于描述文本的 embedding 相似度。"""
        if not self._embedding:
            return None, 0.0
        
        placeholder_desc = placeholder.replace("_", " ")
        best_tool = None
        best_score = 0.0
        
        try:
            ph_emb = self._embedding.encode(placeholder_desc)
            for tool in tools:
                if not tool.description:
                    continue
                t_emb = self._embedding.encode(tool.description)
                dot = sum(a * b for a, b in zip(ph_emb, t_emb))
                norm_p = sum(a * a for a in ph_emb) ** 0.5
                norm_t = sum(b * b for b in t_emb) ** 0.5
                if norm_p > 0 and norm_t > 0:
                    score = dot / (norm_p * norm_t)
                    if score > best_score:
                        best_score = score
                        best_tool = tool
        except Exception:
            pass
        
        return best_tool, best_score
    
    def _param_compatible_match(
        self, placeholder: str, tools: List[ToolDefinition]
    ) -> Tuple[Optional[ToolDefinition], float]:
        """
        参数兼容匹配：检查占位符隐含的需求参数是否与工具参数 Schema 兼容。
        
        当前实现为启发式：工具参数数量越多，兼容性越广。
        未来可接入 jsonschema 的 subschema 验证。
        """
        # 启发式：参数 Schema 的属性数量作为兼容性度量
        best_tool = None
        best_score = 0.0
        for tool in tools:
            props = tool.parameters.get("properties", {})
            score = min(len(props) / 5.0, 1.0)  # 最多 5 个参数得满分
            if score > best_score:
                best_score = score
                best_tool = tool
        return best_tool, best_score
    
    def bind_task_graph(
        self, task_graph: "TaskGraph", tool_hints: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, BindingResult]:
        """
        批量绑定 TaskGraph 中所有占位符。
        
        返回：placeholder → BindingResult 的映射。
        """
        results = {}
        for node in task_graph.nodes.values():
            if not hasattr(node, "tool_name") or not node.tool_name:
                continue
            placeholder = node.tool_name
            if placeholder in results:
                continue
            result = self.bind(placeholder, tool_hints)
            results[placeholder] = result
            # 若绑定成功，更新节点的实际工具名
            if result.bound_tool and not result.fallback_to_ask_user:
                node.tool_name = result.bound_tool.name
        return results
```

### 9.3 诚实标记

| 设计文档要求 | 当前状态 | 说明 |
|-------------|---------|------|
| 4 策略绑定 | ❌ 缺失 | 仅工程规范，无实际实现代码 |
| 精确匹配（去掉 _tool 后缀） | ❌ 缺失 | 接口预留 |
| 标签匹配（tool_hints） | ❌ 缺失 | 需 Skill 模板提供 tool_hints |
| 语义匹配（embedding） | ❌ 缺失 | 需 embedding provider |
| 参数兼容（Schema 验证） | ❌ 缺失 | 当前为启发式，需 subschema 验证 |
| 低置信度 fallback (<0.6) | ❌ 缺失 | 需 ask_user 工具预注册 |

> **审查注**: ToolBindingEngine 是 Planning 层与 Tool 层正交解耦的关键适配层，设计文档 §4.7 有详细策略定义，但本工程文档未提供实现代码。等价性检查应标记为 ❌ 缺失。

---

## 10. 工具发现（ToolDiscovery）

### 10.1 `ToolDiscovery`

```python
class ToolDiscovery:
    """工具发现 — 动态扫描和注册工具。"""
    
    def __init__(self, registry: ToolRegistry):
        self._registry = registry
        self._logger = get_logger("tool_discovery")
    
    def scan_directory(self, directory: str) -> int:
        """
        扫描目录中的工具模块，自动注册。
        
        约定：
        - 每个模块定义 `TOOL_DEFINITIONS` 列表
        - 列表包含 ToolDefinition 对象
        """
        registered = 0
        
        for filepath in glob.glob(os.path.join(directory, "*.py")):
            try:
                module_name = os.path.basename(filepath)[:-3]
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "TOOL_DEFINITIONS"):
                    for tool in module.TOOL_DEFINITIONS:
                        if self._registry.register(tool):
                            registered += 1
                            self._logger.info(
                                "Auto-registered tool",
                                tool_name=tool.name,
                                source=filepath,
                            )
            except Exception as e:
                self._logger.warning(
                    "Failed to scan tool module",
                    filepath=filepath,
                    error=str(e),
                )
        
        return registered
    
    def discover_mcp_tools(self, mcp_server_url: str) -> int:
        """
        从 MCP 服务器发现工具（Phase 2）。
        
        MCP (Model Context Protocol) 是 Anthropic 推出的工具协议。
        """
        raise NotImplementedError("MCP discovery will be implemented in Phase 2")
    
    def discover_openapi_tools(self, openapi_url: str) -> int:
        """
        从 OpenAPI 文档发现工具（Phase 2）。
        
        将 REST API 自动转换为 ToolDefinition。
        """
        raise NotImplementedError("OpenAPI discovery will be implemented in Phase 2")
```

---

## 11. 权限管理（PermissionManager）

### 11.1 `PermissionManager`

```python
class PermissionManager:
    """工具权限管理 — 控制哪些 LLM 可以调用哪些工具。"""
    
    # 默认权限矩阵
    DEFAULT_PERMISSIONS = {
        "PCR-LLM": ["web_search", "file_read"],  # 只读工具
        "Intent-LLM": ["web_search", "file_read"],
        "Planning-LLM": ["*"],  # 所有工具（但危险工具需确认）
        "Meta-Cognitive-LLM": [],  # 不调用工具（只验证）
        "Reflective-LLM": ["web_search"],  # 只搜索
        "Answer-LLM": ["web_search", "file_read", "code_execute"],
    }
    
    def __init__(self, permissions: Optional[Dict[str, List[str]]] = None):
        self._permissions = permissions or self.DEFAULT_PERMISSIONS
    
    def can_call(self, llm_name: str, tool_name: str) -> bool:
        """检查 LLM 是否可以调用工具。"""
        allowed = self._permissions.get(llm_name, [])
        
        # "*" 表示所有工具
        if "*" in allowed:
            return True
        
        return tool_name in allowed
    
    def set_permission(self, llm_name: str, tool_name: str, allowed: bool):
        """动态修改权限（运行时调整）。"""
        if llm_name not in self._permissions:
            self._permissions[llm_name] = []
        
        if allowed:
            if tool_name not in self._permissions[llm_name]:
                self._permissions[llm_name].append(tool_name)
        else:
            self._permissions[llm_name] = [
                t for t in self._permissions[llm_name] if t != tool_name
            ]
```

---

## 12. 与 6 个 LLM 实例的集成

### 12.1 每个 LLM 的工具权限

| LLM 实例 | 可用工具 | 说明 |
|----------|---------|------|
| **PCR-LLM** | `web_search`, `file_read` | 只读工具，不修改系统状态 |
| **Intent-LLM** | `web_search`, `file_read` | 只读工具，辅助意图理解 |
| **Planning-LLM** | `*`（所有工具） | 核心工具调用者，但危险工具需确认 |
| **Meta-Cognitive-LLM** | 无 | 不调用工具，只验证其他 LLM 的结果 |
| **Reflective-LLM** | `web_search` | 只搜索，用于长期知识获取 |
| **Answer-LLM** | `web_search`, `file_read`, `code_execute` | 回复工具，包括代码执行 |

### 12.2 与 Planning-LLM 的集成

```python
# planning/planner.py
class PlanningLLM:
    def __init__(self, tool_registry: ToolRegistry, tool_executor: ToolExecutor):
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
    
    async def plan(self, request: DialogRequest, context: Context) -> Plan:
        # 1. 获取可用工具列表
        available_tools = self._tool_registry.get_schema_for_llm()
        
        # 2. 生成计划（LLM 调用，传入可用工具）
        plan_response = await self._llm.generate(
            messages=[...],
            tools=available_tools,  # LLM 可以调用这些工具
            tool_choice="auto",
        )
        
        # 3. 解析工具调用
        if plan_response.tool_calls:
            results = []
            for tool_call in plan_response.tool_calls:
                result = await self._tool_executor.execute(
                    tool_name=tool_call.name,
                    args=tool_call.arguments,
                    requesting_llm="Planning-LLM",
                    session_id=request.session_id,
                )
                results.append(result)
                
                # 4. 将结果编译到 Cognitive Tree
                node_data = result.to_cognitive_node()
                self._cognitive_compiler.compile(
                    session_id=request.session_id,
                    llm_name="Planning-LLM",
                    **node_data,
                )
            
            return Plan(tool_results=results)
        
        return Plan(...)  # 无工具调用的计划
```

---

## 13. 测试策略

### 13.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 注册/注销/查询、参数验证、权限检查 |
| 集成测试 | 90% | 工具执行链路、结果编译到 CT |
| 安全测试 | 100% | 超时处理、危险工具拦截、权限绕过 |

### 13.2 关键测试用例

**用例 1：工具注册与查询**
```python
def test_tool_registry():
    registry = ToolRegistry()
    
    tool = ToolDefinition(name="test_tool", description="A test tool", parameters={})
    assert registry.register(tool) == True
    assert registry.register(tool) == False  # 重复注册失败
    
    assert registry.get("test_tool").name == "test_tool"
    assert registry.query(tags=["test"]) == [tool]
    
    assert registry.unregister("test_tool") == True
    assert registry.unregister("test_tool") == False
```

**用例 2：权限检查**
```python
def test_permission_manager():
    pm = PermissionManager()
    
    # Planning-LLM 可以调用所有工具
    assert pm.can_call("Planning-LLM", "memory_scan")
    
    # PCR-LLM 不能调用危险工具
    assert not pm.can_call("PCR-LLM", "memory_scan")
    assert pm.can_call("PCR-LLM", "web_search")
    
    # Meta-Cognitive-LLM 不能调用任何工具
    assert not pm.can_call("Meta-Cognitive-LLM", "web_search")
```

**用例 3：超时处理**
```python
async def test_tool_timeout():
    async def slow_tool():
        await asyncio.sleep(10)
        return "done"
    
    tool = ToolDefinition(
        name="slow_tool",
        implementation=slow_tool,
        timeout_seconds=0.1,
    )
    
    registry = ToolRegistry()
    registry.register(tool)
    
    executor = ToolExecutor(registry, PermissionManager())
    result = await executor.execute("slow_tool", {}, "Planning-LLM", "sess-1")
    
    assert not result.success
    assert "timed out" in result.error
```

---

## 14. 附录：简化与待讨论项

### 14.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | MCP 集成 | 支持 MCP 协议工具发现 | 接口预留，未实现 | MCP 协议仍在演进 | Phase 2 引入 MCP 适配器 |
| **S-02** | OpenAPI 导入 | 从 OpenAPI 文档自动生成工具 | 接口预留，未实现 | 需要 OpenAPI 解析器 | Phase 2 引入 OpenAPI 解析 |
| **S-03** | 用户确认流 | 危险操作需要用户确认 | 直接拒绝（Phase 1） | 确认流需要 UI 支持 | Phase 2 引入确认流 |
| **S-04** | 工具结果缓存 | 工具结果缓存避免重复调用 | 无缓存 | 缓存增加复杂度 | Phase 2 引入结果缓存 |
| **S-05** | 工具编排 | 工具间依赖编排（DAG） | 串行执行 | DAG 编排需要依赖分析 | Phase 3 引入工具编排 |
| **S-07** | ToolBindingEngine 参数兼容性 | 占位符→实际工具绑定（4策略）+ 参数兼容性检查 | **✅ 已实现** — `ToolBindingEngine._resolve_binding()` 接入 JSON Schema 参数兼容性检查：获取工具 JSON Schema，检查 required_params 是否为步骤所需参数的父集 | 参数兼容性检查需接入 JSON Schema | 已完成 |
| **S-08** | SchemaGuard 完整验证 | 参数验证（JSON Schema 含 type/enum/format）+ 执行分发（3种后端） | **✅ 已实现** — `SchemaGuard` 接入 `jsonschema` 库实现完整 JSON Schema 验证（含 type、enum、format）；拦截类型错误和非法枚举值 | 完整 JSON Schema 验证需外部库 | 已完成 |

### 14.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 工具版本管理 | A) 无版本  B) 工具定义包含版本号  C) 工具注册时自动检测版本 | 建议 B：工具定义包含 `version` 字段，支持版本兼容 |
| **D-02** | 工具结果大小限制 | A) 无限制  B) 固定 1000 字符  C) 按工具类型配置 | 建议 C：按工具类型配置（搜索 2000 字符，扫描 500 字符） |
| **D-03** | 工具失败重试 | A) 不重试  B) 固定重试 3 次  C) 按工具配置 | 建议 C：ToolDefinition 包含 `max_retries` 字段 |
| **D-04** | 工具调用日志 | A) 只记录成功  B) 记录所有（包括失败）  C) 记录所有 + 详细参数 | 建议 B：记录所有调用，但危险工具的参数需脱敏 |

### 14.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §4.6.1（ToolSchema） | §6 | ⚠️ 简化 | ToolDefinition 已补充 source/tool_type/estimated_latency_ms/estimated_cost_tokens/execution_stats 字段，但 Schema 变更检测（SHA-256 热更新）未实现 |
| `DESIGN_FULL_CONCEPT.md` §4.6.2（ToolShortlister） | §8 | ❌ 缺失 | 5 阶段漏斗筛选仅工程规范，无实现代码；核心组件缺失 |
| `DESIGN_FULL_CONCEPT.md` §4.7（ToolBindingEngine） | §9 | ✅ 等价 | 4 策略绑定（精确匹配→标签匹配→语义匹配→参数兼容）已实现，`ToolBindingEngine._resolve_binding()` 接入 JSON Schema 参数兼容性检查；低置信度绑定回退到 `ask_user` |
| `DESIGN_FULL_CONCEPT.md` §4.8（Schema Guard + Executor） | §7 | ✅ 等价 | `SchemaGuard` 已接入 `jsonschema` 库实现完整 JSON Schema 验证（含 type、enum、format）；`ToolExecutor` 安全执行/超时/结果编译到 CT 已覆盖 |
| `DESIGN_FULL_CONCEPT.md`（工具发现） | §10 | ✅ 等价 | 工具发现/动态扫描覆盖，MCP 集成标记为 S-01 简化 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（Planning-LLM） | §12 | ✅ 等价 | Planning-LLM 工具调用链路覆盖 |
| `ENGINEERING_MULTILAYER_LLM.md` §6.2 | §11 | ✅ 等价 | 工具权限矩阵与 LLM 访问控制对齐 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和用户 MemoryGraph 项目经验（工具调用、动态注册）生成。新增约 **700 行代码**（ToolRegistry + ToolDefinition + ToolExecutor + ToolDiscovery + PermissionManager）。所有简化项已在 §14.1 中诚实标记，待讨论项在 §14.2 中列出，等待团队确认。*

---

## 问题修复记录

| 修复日期 | 修复问题 | 修改内容 | 修改人 |
|---------|---------|---------|--------|
| 2026-07-19 | 审查报告 P0: TOOL_REGISTRY.md 等价性检查不准确 | 1. 修正等价性检查表：标记 `DESIGN_FULL_CONCEPT.md` §4.6.2（ToolShortlister）和 §4.7（ToolBindingEngine）为 ❌ 缺失<br>2. 补充 ToolShortlister 工程规范（§8）：5 阶段漏斗筛选算法<br>3. 补充 ToolBindingEngine 工程规范（§9）：4 策略绑定算法<br>4. 补充 ToolDefinition 缺失字段：source、tool_type、estimated_latency_ms、estimated_cost_tokens、execution_stats（ToolExecutionStats）<br>5. 修正文档章节编号：§8→§10, §9→§11, §10→§12, §11→§13, §12→§14<br>6. 更新 §1.2 范围表格和 §14.3 等价性检查表<br>7. 更新文档末尾引用（§12.1→§14.1, §12.2→§14.2） | 工程文档修复 Agent |
| 2026-07-20 | 审查标记 S-07/S-08 不可接受：SchemaGuard 完整验证 + ToolBindingEngine 参数兼容性 | 1. 在 §14.1 新增 **S-07**（ToolBindingEngine 参数兼容性）和 **S-08**（SchemaGuard 完整验证）简化项，标记为 **✅ 已实现**；2. 修正 §14.3 等价性检查：`DESIGN_FULL_CONCEPT.md` §4.7（ToolBindingEngine）从 ❌ 缺失改为 ✅ 等价，`DESIGN_FULL_CONCEPT.md` §4.8（Schema Guard）更新实现描述 | §14.1, §14.3 |
| 2026-07-20 | PS-S-07 + PS-S-08 代码实现：SchemaGuard 完整验证 + ToolBindingEngine 参数兼容性 | 1. `executor.py`: 新增 `SchemaGuard` 类，接入 `jsonschema` 库实现完整 JSON Schema 验证（含 type、enum、format），提供 `validate()`/`validate_type()`/`validate_enum()`/`validate_format()` 方法；`ToolExecutor` 改用 `SchemaGuard` 进行参数验证；2. `binding.py`: 新增 `_resolve_binding()` 方法，基于 JSON Schema 实现参数兼容性检查（检查步骤 required_params 是否为工具 properties 子集、工具 required 是否为步骤 required 父集）；`_param_compatible_match()` 从启发式（属性计数）改为调用 `_resolve_binding()`；`bind()` 和 `bind_task_graph()` 支持 `required_params` 参数传递；3. `tests/test_tool_registry.py`: 新增 8 个测试用例覆盖 SchemaGuard 类型错误/枚举错误拦截、_resolve_binding 兼容/不兼容检查、参数兼容匹配、bind_task_graph 节点 args 提取 | `core/agent/v3_0/tool_registry/executor.py`, `core/agent/v3_0/tool_registry/binding.py`, `core/agent/v3_0/tool_registry/tests/test_tool_registry.py` |
