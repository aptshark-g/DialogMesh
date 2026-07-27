# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/tests/test_tool_registry.py
─────────────────────────────────────────────────────────
DialogMesh v3.0 Tool Registry 综合测试套件。

覆盖范围：
- models: ToolExecutionStats, ToolDefinition, ToolResult, ToolCall, ShortlistResult, BindingResult
- registry: 注册/注销/查询/Schema 导出/统计
- executor: 单工具执行/同步函数在线程池执行/超时/参数校验失败/批量执行/执行统计更新
- shortlister: 5 阶段漏斗筛选/语义排序降级/历史偏好 boost/兜底策略
- binding: 精确匹配/标签匹配/语义匹配/参数兼容/低置信度回退/TaskGraph 批量绑定
- discovery: 目录扫描/模块内联注册/Phase 2 预留接口
- permission: 默认权限/动态修改/异步检查/通配符

运行方式:
    cd C:/Users/APTShark/PycharmProjects/DialogMesh
    python -m pytest core/agent/v3_0/tool_registry/tests/test_tool_registry.py -v

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

_HAS_JSONSCHEMA: bool = False
try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    pass


# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest

from core.agent.tool_registry.models import (
    BindingResult,
    BindingStrategy,
    ShortlistResult,
    ToolCall,
    ToolDefinition,
    ToolExecutionStats,
    ToolResult,
    ToolSource,
    ToolType,
)
from core.agent.tool_registry.registry import ToolRegistry
from core.agent.tool_registry.executor import ToolExecutor, SchemaGuard
from core.agent.tool_registry.shortlister import ToolShortlister
from core.agent.tool_registry.binding import ToolBindingEngine
from core.agent.tool_registry.discovery import ToolDiscovery
from core.agent.tool_registry.permission import PermissionManager


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def permission_manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def executor(registry: ToolRegistry, permission_manager: PermissionManager) -> ToolExecutor:
    return ToolExecutor(registry, permissions=permission_manager)


@pytest.fixture
def sample_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="memory_scan",
            description="扫描指定进程的内存地址，查找匹配的值",
            parameters={
                "type": "object",
                "properties": {
                    "process_id": {"type": "integer"},
                    "value": {"type": "string"},
                    "value_type": {"type": "string", "enum": ["int32", "float", "string"]},
                },
                "required": ["process_id", "value"],
            },
            tags=["memory", "scan"],
            dangerous=True,
            requires_confirmation=True,
            estimated_latency_ms=500.0,
        ),
        ToolDefinition(
            name="pointer_scan",
            description="扫描指针链",
            tags=["memory", "pointer"],
        ),
        ToolDefinition(
            name="web_search",
            description="网页搜索",
            tags=["web", "search"],
        ),
        ToolDefinition(
            name="file_read",
            description="读取文件内容",
            tags=["file", "read"],
        ),
        ToolDefinition(
            name="code_execute",
            description="执行代码片段",
            tags=["code", "execute"],
            dangerous=True,
        ),
        ToolDefinition(
            name="ask_user",
            description="询问用户以获取澄清",
            tags=["meta"],
        ),
        ToolDefinition(
            name="finish",
            description="结束当前会话",
            tags=["meta"],
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Models Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolExecutionStats:
    def test_initial_state(self):
        stats = ToolExecutionStats()
        assert stats.call_count == 0
        assert stats.success_rate == 0.0
        assert stats.avg_latency_ms == 0.0

    def test_update_success(self):
        stats = ToolExecutionStats()
        stats.update(success=True, latency_ms=100.0)
        assert stats.call_count == 1
        assert stats.success_count == 1
        assert stats.success_rate == 1.0

    def test_update_failure(self):
        stats = ToolExecutionStats()
        stats.update(success=True, latency_ms=100.0)
        stats.update(success=False, latency_ms=200.0)
        assert stats.call_count == 2
        assert stats.success_count == 1
        assert stats.success_rate == 0.5

    def test_ema_smoothing(self):
        stats = ToolExecutionStats()
        for i in range(10):
            stats.update(success=True, latency_ms=100.0 + i * 10)
        assert stats.call_count == 10
        assert 120.0 < stats.avg_latency_ms < 150.0

    @pytest.mark.asyncio
    async def test_async_update(self):
        stats = ToolExecutionStats()
        await stats.async_update(success=True, latency_ms=120.0)
        assert stats.call_count == 1


class TestToolDefinition:
    def test_basic_creation(self):
        tool = ToolDefinition(name="test_tool", description="A test tool")
        assert tool.name == "test_tool"
        assert tool.tool_type == ToolType.LOCAL_FUNCTION
        assert tool.source == ToolSource.BUILTIN

    def test_to_llm_schema(self):
        tool = ToolDefinition(name="test_tool", description="A test tool")
        schema = tool.to_llm_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test_tool"

    def test_validate_args_success(self):
        tool = ToolDefinition(
            name="add",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        ok, err = tool.validate_args({"a": 1, "b": 2})
        assert ok is True and err is None

    def test_validate_args_missing_required(self):
        tool = ToolDefinition(
            name="add",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        ok, err = tool.validate_args({"a": 1})
        assert ok is False
        assert "required" in (err or "").lower()

    def test_record_execution(self):
        tool = ToolDefinition(name="test_tool")
        tool.record_execution(success=True, latency_ms=100.0)
        assert tool.execution_stats.call_count == 1
        assert tool.execution_stats.avg_latency_ms == 100.0

    def test_effective_latency_estimate(self):
        tool = ToolDefinition(name="test_tool", estimated_latency_ms=200.0)
        assert tool.effective_latency_estimate == 200.0
        tool.record_execution(success=True, latency_ms=150.0)
        assert tool.effective_latency_estimate == 150.0

    def test_is_destructive(self):
        tool = ToolDefinition(name="safe_tool", dangerous=False)
        assert tool.is_destructive is False
        tool2 = ToolDefinition(name="unsafe_tool", dangerous=True)
        assert tool2.is_destructive is True


class TestToolResult:
    def test_success_to_cognitive_node(self):
        result = ToolResult(
            success=True,
            data={"addresses": ["0x1234"]},
            latency_ms=120.0,
            tool_name="memory_scan",
        )
        node = result.to_cognitive_node()
        assert node["cog_type"] == "ACTION"
        assert node["confidence"] == 1.0
        assert "memory_scan" in node["content"]

    def test_failure_to_cognitive_node(self):
        result = ToolResult(
            success=False,
            error="timeout",
            latency_ms=300.0,
            tool_name="memory_scan",
        )
        node = result.to_cognitive_node()
        assert node["cog_type"] == "OBSERVATION"
        assert node["confidence"] == 0.0
        assert "失败" in node["content"]


class TestBindingResult:
    def test_confidence_clamping(self):
        r = BindingResult(placeholder="test", confidence=1.5)
        assert r.confidence == 1.0
        r2 = BindingResult(placeholder="test", confidence=-0.5)
        assert r2.confidence == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Registry Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolRegistry:
    @pytest.mark.asyncio
    async def test_register_and_get(self, registry: ToolRegistry):
        tool = ToolDefinition(name="test_tool", description="A test tool")
        assert await registry.register(tool) is True
        fetched = await registry.get("test_tool")
        assert fetched is not None
        assert fetched.name == "test_tool"

    @pytest.mark.asyncio
    async def test_register_duplicate(self, registry: ToolRegistry):
        tool = ToolDefinition(name="test_tool", description="A test tool")
        assert await registry.register(tool) is True
        assert await registry.register(tool) is False

    @pytest.mark.asyncio
    async def test_unregister(self, registry: ToolRegistry):
        tool = ToolDefinition(name="test_tool", description="A test tool")
        await registry.register(tool)
        assert await registry.unregister("test_tool") is True
        assert await registry.unregister("test_tool") is False

    @pytest.mark.asyncio
    async def test_query_by_tag(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)
        results = await registry.query(tags=["memory"])
        assert len(results) == 2
        names = {t.name for t in results}
        assert names == {"memory_scan", "pointer_scan"}

    @pytest.mark.asyncio
    async def test_query_by_keyword(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)
        results = await registry.query(keyword="search")
        names = {t.name for t in results}
        assert "web_search" in names

    @pytest.mark.asyncio
    async def test_list_all(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)
        all_tools = await registry.list_all()
        assert len(all_tools) == len(sample_tools)

    @pytest.mark.asyncio
    async def test_get_schema_for_llm(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)
        schema = await registry.get_schema_for_llm()
        assert len(schema) == len(sample_tools)
        assert all(s["type"] == "function" for s in schema)

    @pytest.mark.asyncio
    async def test_registry_stats(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)
        stats = await registry.get_registry_stats()
        assert stats["total_tools"] == len(sample_tools)
        assert stats["dangerous_tools"] == 2  # memory_scan, code_execute

    def test_sync_register(self, registry: ToolRegistry):
        tool = ToolDefinition(name="sync_tool", description="Sync tool")
        assert registry.register_sync(tool) is True
        assert registry.get_sync("sync_tool") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Executor Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_async_tool(self, registry: ToolRegistry, executor: ToolExecutor):
        async def add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        tool = ToolDefinition(name="add", implementation=add, timeout_seconds=1.0)
        await registry.register(tool)

        result = await executor.execute("add", {"a": 2, "b": 3}, "Planning-LLM", "sess-1")
        assert result.success is True
        assert result.data == 5
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_execute_sync_tool(self, registry: ToolRegistry, executor: ToolExecutor):
        def mul(a: int, b: int) -> int:
            return a * b

        tool = ToolDefinition(name="mul", implementation=mul, timeout_seconds=1.0)
        await registry.register(tool)

        result = await executor.execute("mul", {"a": 4, "b": 5}, "Planning-LLM", "sess-1")
        assert result.success is True
        assert result.data == 20

    @pytest.mark.asyncio
    async def test_execute_timeout(self, registry: ToolRegistry, executor: ToolExecutor):
        async def slow():
            await asyncio.sleep(10)
            return "done"

        tool = ToolDefinition(name="slow", implementation=slow, timeout_seconds=0.1)
        await registry.register(tool)

        result = await executor.execute("slow", {}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert "timed out" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_args(self, registry: ToolRegistry, executor: ToolExecutor):
        async def add(a: int, b: int) -> int:
            return a + b

        tool = ToolDefinition(
            name="add",
            implementation=add,
            timeout_seconds=1.0,
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        await registry.register(tool)

        result = await executor.execute("add", {"a": 2}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert "SchemaGuard 验证失败" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, registry: ToolRegistry, executor: ToolExecutor):
        result = await executor.execute("nonexistent", {}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_batch(self, registry: ToolRegistry, executor: ToolExecutor):
        def add(a: int, b: int) -> int:
            return a + b

        def mul(a: int, b: int) -> int:
            return a * b

        await registry.register(ToolDefinition(name="add", implementation=add, timeout_seconds=1.0))
        await registry.register(ToolDefinition(name="mul", implementation=mul, timeout_seconds=1.0))

        calls = [
            ToolCall(tool_name="add", args={"a": 1, "b": 2}),
            ToolCall(tool_name="mul", args={"a": 3, "b": 4}),
        ]
        results = await executor.execute_batch(calls, "Planning-LLM", "sess-1")
        assert len(results) == 2
        assert results[0].data == 3
        assert results[1].data == 12

    @pytest.mark.asyncio
    async def test_dangerous_tool_blocked(self, registry: ToolRegistry, executor: ToolExecutor):
        async def hack():
            return "hacked"

        tool = ToolDefinition(
            name="hack",
            implementation=hack,
            dangerous=True,
            requires_confirmation=True,
            timeout_seconds=1.0,
        )
        await registry.register(tool)

        result = await executor.execute("hack", {}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert "requires user confirmation" in (result.error or "").lower()

    @pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema not installed")
    @pytest.mark.asyncio
    async def test_execute_schema_guard_type_error(self, registry: ToolRegistry, executor: ToolExecutor):
        """SchemaGuard 应拦截类型错误参数。"""
        async def process(count: int) -> int:
            return count

        tool = ToolDefinition(
            name="process",
            implementation=process,
            timeout_seconds=1.0,
            parameters={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
        )
        await registry.register(tool)

        result = await executor.execute("process", {"count": "not_an_int"}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert ("type" in (result.error or "").lower() or "SchemaGuard" in (result.error or ""))

    @pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema not installed")
    @pytest.mark.asyncio
    async def test_execute_schema_guard_enum_error(self, registry: ToolRegistry, executor: ToolExecutor):
        """SchemaGuard 应拦截非法枚举值。"""
        async def set_level(level: str) -> str:
            return level

        tool = ToolDefinition(
            name="set_level",
            implementation=set_level,
            timeout_seconds=1.0,
            parameters={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["level"],
            },
        )
        await registry.register(tool)

        result = await executor.execute("set_level", {"level": "ultra"}, "Planning-LLM", "sess-1")
        assert result.success is False
        assert ("enum" in (result.error or "").lower() or "SchemaGuard" in (result.error or ""))

    @pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema not installed")
    @pytest.mark.asyncio
    async def test_schema_guard_direct_validate(self, registry: ToolRegistry):
        """SchemaGuard 直接验证接口。"""
        tool = ToolDefinition(
            name="direct_test",
            parameters={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "format": "email"},
                    "count": {"type": "integer", "minimum": 0},
                },
                "required": ["email", "count"],
            },
        )
        await registry.register(tool)

        guard = SchemaGuard(registry)

        # 验证通过
        ok, err = await guard.validate("direct_test", {"email": "test@example.com", "count": 5})
        assert ok is True and err is None

        # 类型错误
        ok2, err2 = await guard.validate_type("direct_test", {"email": "test@example.com", "count": "five"})
        assert ok2 is False
        assert "type" in (err2 or "").lower()

        # 非法枚举（无 enum 字段，所以验证通过）
        ok3, err3 = await guard.validate_enum("direct_test", {"email": "test@example.com", "count": 5})
        assert ok3 is True and err3 is None


# ═══════════════════════════════════════════════════════════════════════════════
# Shortlister Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolShortlister:
    @pytest.mark.asyncio
    async def test_shortlist_with_tag_filter(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)

        class FakeIntent:
            tags = ["memory"]
            description = "scan memory for health"
            normalized_input = "scan memory"
            raw_input = "scan memory for health"

        shortlister = ToolShortlister(registry)
        result = await shortlister.shortlist(FakeIntent(), capacity=4)

        assert len(result.tools) <= 6  # capacity + 2 fallback
        names = {t.name for t in result.tools}
        assert "ask_user" in names
        assert "finish" in names
        assert result.total_available == len(sample_tools)
        assert result.filtered_by_tag == 2  # memory_scan, pointer_scan

    @pytest.mark.asyncio
    async def test_shortlist_no_tag_match(self, registry: ToolRegistry, sample_tools: list[ToolDefinition]):
        for t in sample_tools:
            await registry.register(t)

        class FakeIntent:
            tags = []
            description = "do something"
            normalized_input = "do something"
            raw_input = "do something"

        shortlister = ToolShortlister(registry)
        result = await shortlister.shortlist(FakeIntent(), capacity=4)
        assert result.filtered_by_tag == len(sample_tools)  # 放宽到全部

    def test_history_boost(self):
        tool = ToolDefinition(name="test")
        tool.execution_stats.update(success=True, latency_ms=100.0)
        tool.execution_stats.update(success=True, latency_ms=100.0)
        boost = ToolShortlister._history_boost(tool)
        assert boost > 0.0
        assert boost <= 0.1

    def test_keyword_overlap(self):
        score = ToolShortlister._keyword_overlap("scan memory address", "scan memory")
        assert score > 0.0
        score2 = ToolShortlister._keyword_overlap("", "something")
        assert score2 == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Binding Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolBindingEngine:
    @pytest.mark.asyncio
    async def test_exact_match(self, registry: ToolRegistry):
        await registry.register(ToolDefinition(name="github_search", description="搜索 GitHub"))
        engine = ToolBindingEngine(registry)
        result = await engine.bind("search_tool")
        assert result.strategy == BindingStrategy.EXACT_MATCH
        assert result.bound_tool is not None
        assert result.bound_tool.name == "github_search"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_tag_match(self, registry: ToolRegistry):
        await registry.register(ToolDefinition(name="memory_scan", description="扫描内存", tags=["memory", "scan"]))
        engine = ToolBindingEngine(registry)
        hints = {"scan_tool": ["memory", "scan"]}
        result = await engine.bind("scan_tool", tool_hints=hints)
        assert result.strategy == BindingStrategy.EXACT_MATCH
        assert result.bound_tool.name == "memory_scan"

    @pytest.mark.asyncio
    async def test_fallback_to_ask_user(self, registry: ToolRegistry):
        await registry.register(ToolDefinition(name="existing_tool", description="Existing"))
        engine = ToolBindingEngine(registry)
        result = await engine.bind("totally_unknown_xyz")
        assert result.fallback_to_ask_user is True
        assert result.strategy == BindingStrategy.FALLBACK
        assert result.confidence < 0.6

    @pytest.mark.asyncio
    async def test_bind_task_graph(self, registry: ToolRegistry):
        await registry.register(ToolDefinition(name="github_search", description="搜索 GitHub"))
        await registry.register(ToolDefinition(name="memory_scan", description="扫描内存", tags=["memory"]))

        class FakeNode:
            def __init__(self, tool_name):
                self.tool_name = tool_name

        class FakeGraph:
            def __init__(self, nodes):
                self.nodes = nodes

        graph = FakeGraph({
            "n1": FakeNode("search_tool"),
            "n2": FakeNode("scan_tool"),
        })
        engine = ToolBindingEngine(registry)
        hints = {"scan_tool": ["memory"]}
        results = await engine.bind_task_graph(graph, tool_hints=hints)
        assert "search_tool" in results
        assert "scan_tool" in results
        assert results["search_tool"].strategy == BindingStrategy.EXACT_MATCH
        assert results["scan_tool"].strategy == BindingStrategy.EXACT_MATCH

    @pytest.mark.asyncio
    async def test_resolve_binding_compatible(self, registry: ToolRegistry):
        """_resolve_binding 应正确评估参数兼容性。"""
        tool = ToolDefinition(
            name="query",
            description="查询",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "columns": {"type": "array"},
                },
                "required": ["table", "columns"],
            },
        )
        await registry.register(tool)
        engine = ToolBindingEngine(registry)

        compatible, score = engine._resolve_binding("query_tool", tool, ["table", "columns"])
        assert compatible is True
        assert score >= 0.6

    @pytest.mark.asyncio
    async def test_resolve_binding_incompatible(self, registry: ToolRegistry):
        """_resolve_binding 应识别不兼容的参数需求。"""
        tool = ToolDefinition(
            name="simple_query",
            description="简单查询",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                },
                "required": ["table"],
            },
        )
        await registry.register(tool)
        engine = ToolBindingEngine(registry)

        # 步骤需要 "limit"，但工具没有定义
        compatible, score = engine._resolve_binding("query_tool", tool, ["table", "limit"])
        assert compatible is False
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_param_compatible_match_with_required_params(self, registry: ToolRegistry):
        """参数兼容匹配应使用 _resolve_binding 进行真实检查。"""
        tool_a = ToolDefinition(
            name="query_a",
            description="查询A",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "columns": {"type": "array"},
                },
                "required": ["table", "columns"],
            },
        )
        tool_b = ToolDefinition(
            name="query_b",
            description="查询B",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                },
                "required": ["id"],
            },
        )
        await registry.register(tool_a)
        await registry.register(tool_b)
        engine = ToolBindingEngine(registry)

        # 使用不会触发精确匹配的占位符
        result = await engine.bind("fetch_tool", required_params=["table", "columns"])
        assert result.strategy == BindingStrategy.PARAM_COMPATIBLE
        assert result.bound_tool.name == "query_a"

    @pytest.mark.asyncio
    async def test_bind_task_graph_with_node_args(self, registry: ToolRegistry):
        """bind_task_graph 应从节点 args 提取 required_params。"""
        tool = ToolDefinition(
            name="data_fetch",
            description="获取数据",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "filter": {"type": "string"},
                },
                "required": ["source"],
            },
        )
        await registry.register(tool)
        engine = ToolBindingEngine(registry)

        class FakeNode:
            def __init__(self, tool_name, args):
                self.tool_name = tool_name
                self.args = args

        class FakeGraph:
            def __init__(self, nodes):
                self.nodes = nodes

        # 使用不会触发精确匹配的占位符
        graph = FakeGraph({
            "n1": FakeNode("fetch_data_tool", {"source": "db", "filter": "active"}),
        })
        results = await engine.bind_task_graph(graph)
        assert "fetch_data_tool" in results
        assert results["fetch_data_tool"].bound_tool.name == "data_fetch"


# ═══════════════════════════════════════════════════════════════════════════════
# Discovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolDiscovery:
    @pytest.mark.asyncio
    async def test_scan_directory(self, registry: ToolRegistry):
        discovery = ToolDiscovery(registry)
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = os.path.join(tmpdir, "demo_tools.py")
            with open(module_path, "w", encoding="utf-8") as f:
                f.write(
                    "from core.agent.tool_registry.models import ToolDefinition\n"
                    "TOOL_DEFINITIONS = [\n"
                    "    ToolDefinition(name='demo_a', description='Demo A', tags=['demo']),\n"
                    "    ToolDefinition(name='demo_b', description='Demo B', tags=['demo']),\n"
                    "]\n"
                )
            count = await discovery.scan_directory(tmpdir)
            assert count == 2
            assert await registry.get("demo_a") is not None
            assert await registry.get("demo_b") is not None

    @pytest.mark.asyncio
    async def test_register_from_module(self, registry: ToolRegistry):
        discovery = ToolDiscovery(registry)

        class FakeModule:
            __name__ = "fake_module"
            TOOL_DEFINITIONS = [
                ToolDefinition(name="mod_a", description="Module A"),
                ToolDefinition(name="mod_b", description="Module B"),
            ]

        count = await discovery.register_from_module(FakeModule(), prefix="pref")
        assert count == 2
        assert await registry.get("pref_mod_a") is not None
        assert await registry.get("pref_mod_b") is not None

    @pytest.mark.asyncio
    async def test_mcp_not_implemented(self, registry: ToolRegistry):
        discovery = ToolDiscovery(registry)
        with pytest.raises(NotImplementedError):
            await discovery.discover_mcp_tools("http://localhost:8080")

    @pytest.mark.asyncio
    async def test_openapi_not_implemented(self, registry: ToolRegistry):
        discovery = ToolDiscovery(registry)
        with pytest.raises(NotImplementedError):
            await discovery.discover_openapi_tools("http://localhost:8080/openapi.json")


# ═══════════════════════════════════════════════════════════════════════════════
# Permission Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermissionManager:
    def test_default_permissions(self):
        pm = PermissionManager()
        assert pm.can_call("Planning-LLM", "any_tool") is True
        assert pm.can_call("PCR-LLM", "web_search") is True
        assert pm.can_call("PCR-LLM", "memory_scan") is False
        assert pm.can_call("Meta-Cognitive-LLM", "web_search") is False

    def test_set_permission(self):
        pm = PermissionManager()
        pm.set_permission("PCR-LLM", "memory_scan", True)
        assert pm.can_call("PCR-LLM", "memory_scan") is True
        pm.set_permission("PCR-LLM", "memory_scan", False)
        assert pm.can_call("PCR-LLM", "memory_scan") is False

    def test_get_allowed_tools(self):
        pm = PermissionManager()
        tools = pm.get_allowed_tools("Answer-LLM")
        assert "web_search" in tools
        assert "file_read" in tools
        assert "code_execute" in tools

    def test_list_llms(self):
        pm = PermissionManager()
        llms = pm.list_llms()
        assert "Planning-LLM" in llms
        assert "PCR-LLM" in llms

    def test_to_dict(self):
        pm = PermissionManager()
        data = pm.to_dict()
        assert isinstance(data, dict)
        assert "Planning-LLM" in data

    @pytest.mark.asyncio
    async def test_async_can_call(self):
        pm = PermissionManager()
        ok = await pm.async_can_call("Answer-LLM", "code_execute")
        assert ok is True

    @pytest.mark.asyncio
    async def test_async_set_permission(self):
        pm = PermissionManager()
        await pm.async_set_permission("PCR-LLM", "memory_scan", True)
        assert pm.can_call("PCR-LLM", "memory_scan") is True

    def test_remove_llm(self):
        pm = PermissionManager()
        assert pm.remove_llm("PCR-LLM") is True
        assert pm.can_call("PCR-LLM", "web_search") is False
        assert pm.remove_llm("NonExistent") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_tool_call_flow(self):
        """完整链路：注册 → 筛选 → 绑定 → 权限检查 → 执行 → 结果编译"""
        registry = ToolRegistry()
        pm = PermissionManager()
        executor = ToolExecutor(registry, permissions=pm)
        shortlister = ToolShortlister(registry)
        binder = ToolBindingEngine(registry)

        # 注册工具
        async def add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        tools = [
            ToolDefinition(name="add", description="加法", implementation=add, tags=["math"]),
            ToolDefinition(name="ask_user", description="询问用户", tags=["meta"]),
            ToolDefinition(name="finish", description="结束", tags=["meta"]),
        ]
        for t in tools:
            await registry.register(t)

        # 模拟意图
        class FakeIntent:
            tags = ["math"]
            description = "calculate sum"
            normalized_input = "calculate sum"
            raw_input = "calculate sum"

        # 筛选
        shortlist = await shortlister.shortlist(FakeIntent(), capacity=2)
        assert "add" in [t.name for t in shortlist.tools]

        # 绑定
        bind_result = await binder.bind("math_tool", tool_hints={"math_tool": ["math"]})
        assert bind_result.bound_tool is not None
        assert bind_result.bound_tool.name == "add"

        # 权限 + 执行
        result = await executor.execute("add", {"a": 3, "b": 4}, "Planning-LLM", "sess-1")
        assert result.success is True
        assert result.data == 7

        # 结果编译
        node = result.to_cognitive_node()
        assert node["cog_type"] == "ACTION"
        assert node["action"] == "add"
