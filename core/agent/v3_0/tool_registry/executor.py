# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/executor.py
──────────────────────────────────────────
DialogMesh v3.0 工具执行器。

用途：
- 安全、可控地执行已注册工具，支持超时控制、异常处理与执行统计更新。
- 提供批量执行能力（asyncio.gather 并行）。
- 危险操作拦截（Phase 1 直接拒绝，Phase 2 引入用户确认流）。
- 与 PermissionManager 联动，确保 LLM 调用权限合规。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v3_0.tool_registry.models import (
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from core.agent.v3_0.tool_registry.registry import ToolRegistry

logger = logging.getLogger(__name__)


class PermissionManager:
    """权限管理占位引用——在导入 permission.py 实际类前避免循环依赖。

    实际运行时应从 core.agent.v3_0.tool_registry.permission 导入。
    """
    pass


class SchemaGuard:
    """Schema 验证守卫 — 完整 JSON Schema 参数校验（对应设计文档 §4.8.1）。

    验证项：
    - 工具名是否存在于 ToolRegistry
    - 必填参数是否齐全
    - 参数类型是否符合 JSON Schema（通过 jsonschema 库验证）
    - 枚举值是否合法
    - 格式约束（format）是否满足

    版本：3.0.0
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._logger = logging.getLogger("schema_guard")

    async def validate(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """完整 JSON Schema 验证。

        使用 jsonschema.Draft7Validator 进行逐项验证，返回结构化错误信息。
        若 jsonschema 未安装，降级为必填参数兜底检查。

        参数:
            tool_name: 目标工具名。
            args: 待验证的调用参数字典。

        返回:
            (valid, error_msg) — valid=True 表示验证通过。
        """
        try:
            tool = await self._registry.get(tool_name)
            if tool is None:
                return False, f"工具 '{tool_name}' 未在注册中心找到"

            import jsonschema

            validator = jsonschema.Draft7Validator(tool.parameters)
            errors = list(validator.iter_errors(args))
            if errors:
                messages: List[str] = []
                for err in errors:
                    path = " -> ".join(str(p) for p in err.path) if err.path else "根"
                    messages.append(f"[{err.validator}] {path}: {err.message}")
                return False, "; ".join(messages)
            return True, None

        except ImportError:
            self._logger.warning("jsonschema 未安装，降级为必填参数检查")
            return await self._fallback_validate(tool_name, args)
        except jsonschema.SchemaError as e:
            self._logger.error(f"工具 '{tool_name}' 的参数 Schema 本身无效: {e}")
            return False, f"Schema 定义错误: {e.message}"
        except Exception as exc:
            self._logger.error(f"SchemaGuard.validate 异常: {exc}")
            return False, str(exc)

    async def validate_type(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """仅验证参数类型约束。

        返回类型错误信息；若验证通过返回 (True, None)。
        """
        try:
            tool = await self._registry.get(tool_name)
            if tool is None:
                return False, f"工具 '{tool_name}' 未找到"

            import jsonschema

            validator = jsonschema.Draft7Validator(tool.parameters)
            type_errors = [e for e in validator.iter_errors(args) if e.validator == "type"]
            if type_errors:
                err = type_errors[0]
                path = " -> ".join(str(p) for p in err.path) if err.path else "根"
                return False, f"类型错误 [{path}]: {err.message}"
            return True, None
        except ImportError:
            return await self._fallback_validate(tool_name, args)
        except Exception as exc:
            return False, str(exc)

    async def validate_enum(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """仅验证枚举值约束。

        返回枚举错误信息；若验证通过返回 (True, None)。
        """
        try:
            tool = await self._registry.get(tool_name)
            if tool is None:
                return False, f"工具 '{tool_name}' 未找到"

            import jsonschema

            validator = jsonschema.Draft7Validator(tool.parameters)
            enum_errors = [e for e in validator.iter_errors(args) if e.validator == "enum"]
            if enum_errors:
                err = enum_errors[0]
                path = " -> ".join(str(p) for p in err.path) if err.path else "根"
                return False, f"非法枚举值 [{path}]: {err.message}"
            return True, None
        except ImportError:
            return await self._fallback_validate(tool_name, args)
        except Exception as exc:
            return False, str(exc)

    async def validate_format(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """仅验证 format 约束（如 email、uri、date-time 等）。

        返回格式错误信息；若验证通过返回 (True, None)。
        """
        try:
            tool = await self._registry.get(tool_name)
            if tool is None:
                return False, f"工具 '{tool_name}' 未找到"

            import jsonschema

            validator = jsonschema.Draft7Validator(tool.parameters)
            fmt_errors = [e for e in validator.iter_errors(args) if e.validator == "format"]
            if fmt_errors:
                err = fmt_errors[0]
                path = " -> ".join(str(p) for p in err.path) if err.path else "根"
                return False, f"格式错误 [{path}]: {err.message}"
            return True, None
        except ImportError:
            return await self._fallback_validate(tool_name, args)
        except Exception as exc:
            return False, str(exc)

    async def _fallback_validate(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """jsonschema 未安装时的降级验证：仅检查必填参数是否存在。"""
        try:
            tool = await self._registry.get(tool_name)
            if tool is None:
                return False, f"工具 '{tool_name}' 未找到"
            required = tool.parameters.get("required", [])
            missing = [key for key in required if key not in args]
            if missing:
                return False, f"缺少必填参数: {missing}"
            return True, None
        except Exception as exc:
            return False, str(exc)


class ToolExecutor:
    """工具执行器 — 安全、可控地执行工具。

    执行流程:
        1. 权限检查（requesting_llm 是否可以调用该工具）
        2. 获取工具定义
        3. 验证参数
        4. 检查危险操作（Phase 1 直接拒绝）
        5. 执行工具（带超时）
        6. 更新执行统计
        7. 封装结果
        8. 记录日志
    """

    def __init__(
        self,
        registry: ToolRegistry,
        permissions: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._logger = logging.getLogger("tool_executor")
        self._schema_guard = SchemaGuard(registry)

    # ── 单工具执行 ─────────────────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        requesting_llm: str,
        session_id: str,
    ) -> ToolResult:
        """执行单个工具。

        参数:
            tool_name: 目标工具名。
            args: 调用参数字典。
            requesting_llm: 发起调用的 LLM 标识（用于权限检查）。
            session_id: 所属会话 ID。

        返回:
            ToolResult 封装执行结果。

        异常:
            内部捕获所有异常并封装为失败的 ToolResult，不向上抛出。
        """
        start_time = time.time()
        call_id = f"tc-{__import__('uuid').uuid4().hex[:8]}"

        try:
            # 1. 权限检查
            if self._permissions is not None:
                try:
                    # 延迟导入避免循环依赖
                    from core.agent.v3_0.tool_registry.permission import PermissionManager as RealPM

                    if isinstance(self._permissions, RealPM):
                        if not self._permissions.can_call(requesting_llm, tool_name):
                            raise PermissionError(
                                f"LLM '{requesting_llm}' cannot call tool '{tool_name}'"
                            )
                except ImportError:
                    pass
                except PermissionError:
                    raise
                except Exception as perm_exc:
                    self._logger.warning(f"Permission check error: {perm_exc}")

            # 2. 获取工具定义
            tool = await self._registry.get(tool_name)
            if tool is None:
                raise ValueError(f"Tool '{tool_name}' not found in registry")

            # 3. SchemaGuard 完整验证（含 type、enum、format）
            valid, error = await self._schema_guard.validate(tool_name, args)
            if not valid:
                raise ValueError(f"SchemaGuard 验证失败: {error}")

            # 4. 危险操作拦截（Phase 1）
            if tool.dangerous and tool.requires_confirmation:
                self._logger.warning(
                    f"Dangerous tool '{tool_name}' requires confirmation (Phase 1: rejected)",
                    extra={"tool_args": args, "requesting_llm": requesting_llm, "session_id": session_id},
                )
                raise RuntimeError(
                    f"Tool '{tool_name}' requires user confirmation. "
                    "This feature will be implemented in Phase 2."
                )

            # 5. 执行工具（带超时）
            result_data = await self._run_tool(tool, args)
            latency_ms = (time.time() - start_time) * 1000

            # 6. 更新执行统计
            tool.record_execution(success=True, latency_ms=latency_ms)

            # 7. 封装结果
            return ToolResult(
                success=True,
                data=result_data,
                latency_ms=latency_ms,
                tool_name=tool_name,
                call_id=call_id,
                metadata={"session_id": session_id, "requesting_llm": requesting_llm},
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            # 尝试获取工具以更新统计
            try:
                tool = await self._registry.get(tool_name)
                if tool:
                    tool.record_execution(success=False, latency_ms=latency_ms)
            except Exception:
                pass
            self._logger.error(f"Tool '{tool_name}' timed out after configured timeout")
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' timed out",
                latency_ms=latency_ms,
                tool_name=tool_name,
                call_id=call_id,
                metadata={"session_id": session_id, "requesting_llm": requesting_llm},
            )
        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000
            try:
                tool = await self._registry.get(tool_name)
                if tool:
                    tool.record_execution(success=False, latency_ms=latency_ms)
            except Exception:
                pass
            self._logger.error(f"Tool '{tool_name}' execution failed: {exc}")
            return ToolResult(
                success=False,
                error=str(exc),
                latency_ms=latency_ms,
                tool_name=tool_name,
                call_id=call_id,
                metadata={"session_id": session_id, "requesting_llm": requesting_llm},
            )

    async def _run_tool(
        self, tool: ToolDefinition, args: Dict[str, Any]
    ) -> Any:
        """底层运行工具，处理同步/异步实现与超时。"""
        if tool.implementation is None and tool.external_endpoint is None:
            raise ValueError(f"Tool '{tool.name}' has no implementation or endpoint")

        if tool.implementation is not None:
            if asyncio.iscoroutinefunction(tool.implementation):
                return await asyncio.wait_for(
                    tool.implementation(**args),
                    timeout=tool.timeout_seconds,
                )
            else:
                # 同步函数在线程池中执行，避免阻塞事件循环
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.implementation(**args)),
                    timeout=tool.timeout_seconds,
                )

        # 外部 API（Phase 2）
        if tool.external_endpoint:
            raise NotImplementedError("External API tools not yet supported (Phase 2)")

        raise RuntimeError(f"Tool '{tool.name}' execution path unreachable")

    # ── 批量执行 ───────────────────────────────────────────────────────────

    async def execute_batch(
        self,
        calls: List[ToolCall],
        requesting_llm: str,
        session_id: str,
    ) -> List[ToolResult]:
        """批量执行工具（并行）。

        参数:
            calls: 工具调用请求列表。
            requesting_llm: 发起调用的 LLM 标识。
            session_id: 所属会话 ID。

        返回:
            与 calls 顺序对应的 ToolResult 列表。
        """
        try:
            tasks = [
                self.execute(call.tool_name, call.args, requesting_llm, session_id)
                for call in calls
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)
        except Exception as exc:
            self._logger.error(f"execute_batch failed: {exc}")
            raise

    async def execute_batch_gather(
        self,
        calls: List[ToolCall],
        requesting_llm: str,
        session_id: str,
        return_exceptions: bool = True,
    ) -> List[Any]:
        """批量执行工具，可保留异常。

        参数:
            return_exceptions: True 时异常对象保留在结果列表中；
                               False 时第一个异常直接抛出。
        """
        try:
            tasks = [
                self.execute(call.tool_name, call.args, requesting_llm, session_id)
                for call in calls
            ]
            return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
        except Exception as exc:
            self._logger.error(f"execute_batch_gather failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/executor self-test ===")

        from core.agent.v3_0.tool_registry.registry import ToolRegistry

        registry = ToolRegistry()

        # 定义测试工具
        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        def sync_mul(a: int, b: int) -> int:
            return a * b

        tool_add = ToolDefinition(
            name="add",
            description="加法",
            implementation=async_add,
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
        tool_mul = ToolDefinition(
            name="mul", description="乘法", implementation=sync_mul, timeout_seconds=1.0
        )
        await registry.register(tool_add)
        await registry.register(tool_mul)

        executor = ToolExecutor(registry)

        # 1. 异步工具执行
        result = await executor.execute("add", {"a": 2, "b": 3}, "Planning-LLM", "sess-1")
        assert result.success is True and result.data == 5
        print(f"[PASS] async tool execute: {result.data}")

        # 2. 同步工具在线程池执行
        result2 = await executor.execute("mul", {"a": 4, "b": 5}, "Planning-LLM", "sess-1")
        assert result2.success is True and result2.data == 20
        print(f"[PASS] sync tool execute (thread pool): {result2.data}")

        # 3. 参数校验失败（必填参数缺失）
        result3 = await executor.execute("add", {"a": 2}, "Planning-LLM", "sess-1")
        assert result3.success is False and "SchemaGuard 验证失败" in (result3.error or "")
        print(f"[PASS] arg validation failure")

        # 4. SchemaGuard 类型错误拦截
        tool_type_test = ToolDefinition(
            name="type_test",
            description="类型测试工具",
            implementation=async_add,
            timeout_seconds=1.0,
            parameters={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                },
                "required": ["count"],
            },
        )
        await registry.register(tool_type_test)
        result_type = await executor.execute("type_test", {"count": "not_an_int"}, "Planning-LLM", "sess-1")
        assert result_type.success is False
        assert "type" in (result_type.error or "").lower() or "SchemaGuard" in (result_type.error or "")
        print(f"[PASS] SchemaGuard type error interception")

        # 5. SchemaGuard 非法枚举值拦截
        tool_enum_test = ToolDefinition(
            name="enum_test",
            description="枚举测试工具",
            implementation=async_add,
            timeout_seconds=1.0,
            parameters={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["level"],
            },
        )
        await registry.register(tool_enum_test)
        result_enum = await executor.execute("enum_test", {"level": "invalid_value"}, "Planning-LLM", "sess-1")
        assert result_enum.success is False
        assert ("enum" in (result_enum.error or "").lower() or "SchemaGuard" in (result_enum.error or ""))
        print(f"[PASS] SchemaGuard enum validation interception")

        # 6. SchemaGuard 直接调用验证通过
        guard = SchemaGuard(registry)
        ok, err = await guard.validate("add", {"a": 1, "b": 2})
        assert ok is True and err is None
        ok2, err2 = await guard.validate_type("type_test", {"count": 42})
        assert ok2 is True and err2 is None
        ok3, err3 = await guard.validate_enum("enum_test", {"level": "high"})
        assert ok3 is True and err3 is None
        print(f"[PASS] SchemaGuard direct validation")

        # 7. 工具不存在
        result4 = await executor.execute("nonexist", {}, "Planning-LLM", "sess-1")
        assert result4.success is False and "not found" in (result4.error or "")
        print(f"[PASS] tool not found")

        # 8. 超时
        async def slow_tool():
            await asyncio.sleep(10)
            return "done"

        tool_slow = ToolDefinition(
            name="slow", description="慢工具", implementation=slow_tool, timeout_seconds=0.1
        )
        await registry.register(tool_slow)
        result5 = await executor.execute("slow", {}, "Planning-LLM", "sess-1")
        assert result5.success is False and "timed out" in (result5.error or "").lower()
        print(f"[PASS] timeout handling")

        # 9. 批量执行
        calls = [
            ToolCall(tool_name="add", args={"a": 1, "b": 2}),
            ToolCall(tool_name="mul", args={"a": 3, "b": 4}),
        ]
        batch = await executor.execute_batch(calls, "Planning-LLM", "sess-1")
        assert len(batch) == 2
        assert batch[0].data == 3 and batch[1].data == 12
        print(f"[PASS] batch execute")

        # 10. 执行统计更新
        assert tool_add.execution_stats.call_count > 0
        print(f"[PASS] execution stats: calls={tool_add.execution_stats.call_count}")

        logger.info("=== All v3.0 tool_registry/executor self-tests passed ===")

    asyncio.run(_self_test())
