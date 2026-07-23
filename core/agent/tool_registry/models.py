# -*- coding: utf-8 -*-
"""
core/agent/v3_0/tool_registry/models.py
────────────────────────────────────────
DialogMesh v3.0 工具注册系统数据模型。

用途：
- 定义 ToolRegistry 体系中所有 Pydantic v2 数据模型。
- 包括工具定义（ToolDefinition）、执行统计（ToolExecutionStats）、
  执行结果（ToolResult）、工具调用（ToolCall）、筛选结果（ShortlistResult）
  与绑定结果（BindingResult）。
- 所有模型支持 JSON 序列化与异步校验，兼容 FastAPI Schema 生成。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════════

class ToolSource(str, Enum):
    """工具来源——标识工具的注册渠道。"""
    BUILTIN = "builtin"       # 系统内置工具
    API_DOC = "api_doc"       # 从 API 文档自动生成
    MCP = "mcp"               # MCP 协议远程工具
    CUSTOM = "custom"         # 用户自定义工具


class ToolType(str, Enum):
    """工具执行类型——标识工具的运行时形态。"""
    LOCAL_FUNCTION = "local_function"   # 本地 Python 函数
    HTTP_API = "http_api"               # REST API 调用
    MCP_REMOTE = "mcp_remote"           # MCP 远程工具


class BindingStrategy(str, Enum):
    """工具绑定策略——标识占位符到实际工具的匹配方式。"""
    EXACT_MATCH = "exact_match"           # 精确匹配
    TAG_MATCH = "tag_match"               # 标签匹配
    SEMANTIC_MATCH = "semantic_match"     # 语义匹配
    PARAM_COMPATIBLE = "param_compatible"  # 参数兼容匹配
    FALLBACK = "fallback"                 # 低置信度回退


# ═══════════════════════════════════════════════════════════════════════════════
# 基础统计模型
# ═══════════════════════════════════════════════════════════════════════════════

class ToolExecutionStats(BaseModel):
    """工具执行统计——用于 ToolShortlister 动态排序与自适应路由。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    call_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    total_latency_ms: float = Field(default=0.0, ge=0.0)
    last_executed_at: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """计算成功率。"""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count

    @property
    def avg_latency_ms(self) -> float:
        """计算平均延迟（ms）。"""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count

    def update(self, success: bool, latency_ms: float) -> None:
        """更新执行统计——使用 EMA 平滑平均延迟。"""
        try:
            self.call_count += 1
            if success:
                self.success_count += 1

            alpha = 0.3  # EMA 平滑系数
            if self.call_count == 1:
                self.total_latency_ms = latency_ms
            else:
                prev_avg = self.avg_latency_ms
                # 修正 total_latency_ms，使其保持 avg = total / count 的关系
                new_avg = prev_avg + alpha * (latency_ms - prev_avg)
                self.total_latency_ms = new_avg * self.call_count

            self.last_executed_at = datetime.utcnow().timestamp()
        except Exception as exc:
            logger.error(f"ToolExecutionStats.update failed: {exc}")
            raise

    async def async_update(self, success: bool, latency_ms: float) -> None:
        """异步更新执行统计。"""
        try:
            await asyncio.sleep(0)
            self.update(success, latency_ms)
        except Exception as exc:
            logger.error(f"ToolExecutionStats.async_update failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════════
# 工具定义模型
# ═══════════════════════════════════════════════════════════════════════════════

class ToolDefinition(BaseModel):
    """工具定义——描述一个工具的完整元数据，供 LLM 理解与执行器调用。

    字段对齐设计文档 §4.6.1（ToolSchema），包含来源、类型、预估延迟/成本、
    执行统计等扩展属性。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    name: str = Field(..., min_length=1, description="工具唯一标识名")
    description: str = Field(default="", description="工具功能描述，用于 LLM 理解")
    parameters: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="JSON Schema 参数定义",
    )
    return_schema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="返回值 JSON Schema",
    )
    implementation: Optional[Callable] = Field(
        default=None, exclude=True, description="本地实现函数（不可序列化）"
    )
    external_endpoint: Optional[str] = Field(
        default=None, description="外部 API 端点（HTTP_API 类型使用）"
    )
    tags: List[str] = Field(default_factory=list, description="标签列表，如 ['memory', 'scan']")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="默认执行超时（秒）")
    dangerous: bool = Field(default=False, description="是否为危险操作（如修改内存）")
    requires_confirmation: bool = Field(default=False, description="执行前是否需要用户确认")
    llm_permissions: List[str] = Field(
        default_factory=list, description="允许调用的 LLM 列表；空列表表示所有 LLM 可用"
    )
    source: ToolSource = Field(default=ToolSource.BUILTIN, description="工具来源")
    tool_type: ToolType = Field(default=ToolType.LOCAL_FUNCTION, description="工具执行类型")
    estimated_latency_ms: Optional[float] = Field(default=None, description="预估延迟（ms）")
    estimated_cost_tokens: Optional[int] = Field(default=None, description="预估 Token 成本")
    execution_stats: ToolExecutionStats = Field(
        default_factory=ToolExecutionStats, description="执行统计"
    )
    max_retries: int = Field(default=3, ge=0, description="失败时最大重试次数")
    version: str = Field(default="1.0.0", description="工具版本号")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _clamp_timeout(cls, v: Union[float, int]) -> float:
        """将超时裁剪到合法范围。"""
        try:
            return float(max(0.1, min(3600.0, v)))
        except Exception as exc:
            logger.warning(f"Timeout validation error ({exc}), defaulting to 30.0")
            return 30.0

    def to_llm_schema(self) -> Dict[str, Any]:
        """转换为 LLM 可用的 JSON Schema（OpenAI function 格式）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate_args(self, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证参数是否符合 JSON Schema。

        当前优先使用 jsonschema 完整校验；若未安装或校验通过，仍做一层
        required 字段的二次检查，确保版本兼容性。
        """
        try:
            # 优先尝试 jsonschema 完整校验
            import jsonschema
            jsonschema.validate(instance=args, schema=self.parameters)
        except ImportError:
            pass
        except jsonschema.ValidationError as e:
            return False, str(e)
        except Exception as exc:
            logger.error(f"validate_args jsonschema check failed for {self.name}: {exc}")
            return False, str(exc)

        # 二次检查：无论 jsonschema 是否安装，都确保 required 字段存在
        required = self.parameters.get("required", [])
        missing = [key for key in required if key not in args]
        if missing:
            return False, f"Missing required arguments: {missing}"
        return True, None

    def record_execution(self, success: bool, latency_ms: float) -> None:
        """记录一次执行结果，更新统计。"""
        try:
            self.execution_stats.update(success, latency_ms)
        except Exception as exc:
            logger.error(f"record_execution failed for {self.name}: {exc}")

    @property
    def effective_latency_estimate(self) -> float:
        """获取有效的延迟预估——实测优先于预估。"""
        if self.execution_stats.call_count > 0:
            return self.execution_stats.avg_latency_ms
        return self.estimated_latency_ms or 100.0

    @property
    def is_destructive(self) -> bool:
        """是否涉及写操作（等价于 dangerous）。"""
        return self.dangerous

    def __str__(self) -> str:
        return (
            f"ToolDefinition({self.name}, type={self.tool_type.value}, "
            f"dangerous={self.dangerous}, stats_calls={self.execution_stats.call_count})"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 执行相关模型
# ═══════════════════════════════════════════════════════════════════════════════

class ToolCall(BaseModel):
    """工具调用请求——标识一次待执行的工具调用。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    tool_name: str = Field(..., description="目标工具名")
    args: Dict[str, Any] = Field(default_factory=dict, description="调用参数")
    call_id: str = Field(default_factory=lambda: f"tc-{__import__('uuid').uuid4().hex[:8]}")
    requesting_llm: str = Field(default="", description="发起调用的 LLM 标识")
    session_id: str = Field(default="", description="所属会话 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """工具执行结果——封装单次工具调用的输出与元数据。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    success: bool = Field(default=False, description="是否执行成功")
    data: Any = Field(default=None, description="成功时的返回数据")
    error: Optional[str] = Field(default=None, description="失败时的错误信息")
    latency_ms: float = Field(default=0.0, ge=0.0, description="执行耗时（ms）")
    tool_name: str = Field(default="", description="执行的工具名")
    call_id: Optional[str] = Field(default=None, description="关联的 ToolCall ID")
    retried: int = Field(default=0, ge=0, description="实际重试次数")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_cognitive_node(self) -> Dict[str, Any]:
        """转换为 Cognitive Tree 节点数据字典。

        返回包含 action / observation 类型的通用结构，供上层 CognitiveCompiler
        进一步编译为具体的 CT 节点。
        """
        if self.success:
            # 限制结果序列化长度，避免过大的 payload 进入上下文
            result_str = json.dumps(self.data, ensure_ascii=False, default=str)[:2000]
            return {
                "cog_type": "ACTION",
                "content": f"执行工具 '{self.tool_name}' 成功",
                "action": self.tool_name,
                "action_result": result_str,
                "latency_ms": self.latency_ms,
                "confidence": 1.0,
            }
        else:
            return {
                "cog_type": "OBSERVATION",
                "content": f"执行工具 '{self.tool_name}' 失败: {self.error}",
                "action": self.tool_name,
                "action_result": self.error or "unknown error",
                "latency_ms": self.latency_ms,
                "confidence": 0.0,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 筛选与绑定模型
# ═══════════════════════════════════════════════════════════════════════════════

class ShortlistResult(BaseModel):
    """工具筛选结果——5 阶段漏斗输出的子集与统计信息。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    tools: List[ToolDefinition] = Field(default_factory=list, description="筛选后的工具子集")
    total_available: int = Field(default=0, description="原始可用工具总数")
    filtered_by_tag: int = Field(default=0, description="标签过滤后剩余数量")
    ranked_by_semantic: int = Field(default=0, description="语义排序后数量")
    capacity_limit: int = Field(default=32, description="容量截断上限")
    fallback_included: bool = Field(default=True, description="是否包含兜底工具")


class BindingResult(BaseModel):
    """工具绑定结果——占位符到实际工具的映射。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    placeholder: str = Field(..., description="原始占位符名")
    bound_tool: Optional[ToolDefinition] = Field(default=None, description="绑定后的实际工具")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="绑定置信度")
    strategy: BindingStrategy = Field(default=BindingStrategy.FALLBACK, description="使用的绑定策略")
    fallback_to_ask_user: bool = Field(default=False, description="是否因低置信度回退到 ask_user")

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: Union[float, int]) -> float:
        """将置信度裁剪到 [0.0, 1.0]。"""
        try:
            return float(max(0.0, min(1.0, v)))
        except Exception as exc:
            logger.warning(f"Confidence validation error ({exc}), defaulting to 0.0")
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 前向引用解析
# ═══════════════════════════════════════════════════════════════════════════════
ToolDefinition.model_rebuild()
ToolResult.model_rebuild()
ShortlistResult.model_rebuild()
BindingResult.model_rebuild()


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 tool_registry/models self-test ===")

        # 1. ToolExecutionStats
        stats = ToolExecutionStats()
        stats.update(success=True, latency_ms=120.0)
        stats.update(success=False, latency_ms=300.0)
        assert stats.call_count == 2
        assert stats.success_rate == 0.5
        print(f"[PASS] ToolExecutionStats: calls={stats.call_count}, rate={stats.success_rate}")

        # 2. ToolDefinition
        tool = ToolDefinition(
            name="memory_scan",
            description="扫描进程内存",
            parameters={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "value": {"type": "string"},
                },
                "required": ["pid", "value"],
            },
            tags=["memory", "scan"],
            dangerous=True,
            estimated_latency_ms=500.0,
        )
        assert tool.name == "memory_scan"
        assert tool.is_destructive is True
        print(f"[PASS] ToolDefinition: {tool}")

        # 3. validate_args
        ok, err = tool.validate_args({"pid": 1234, "value": "100"})
        assert ok is True and err is None
        ok2, err2 = tool.validate_args({"pid": 1234})
        assert ok2 is False
        print(f"[PASS] validate_args")

        # 4. ToolResult
        result = ToolResult(
            success=True, data={"addresses": ["0x1234"]}, latency_ms=120.0, tool_name="memory_scan"
        )
        node = result.to_cognitive_node()
        assert node["cog_type"] == "ACTION"
        print(f"[PASS] ToolResult: {node['cog_type']}")

        # 5. BindingResult
        binding = BindingResult(placeholder="search_tool", confidence=0.85, strategy=BindingStrategy.TAG_MATCH)
        assert binding.confidence == 0.85
        assert binding.fallback_to_ask_user is False
        print(f"[PASS] BindingResult: strategy={binding.strategy.value}")

        # 6. ShortlistResult
        shortlist = ShortlistResult(tools=[tool], total_available=10, filtered_by_tag=5, ranked_by_semantic=3)
        assert len(shortlist.tools) == 1
        print(f"[PASS] ShortlistResult: {shortlist.total_available}")

        # 7. async_update
        await stats.async_update(success=True, latency_ms=100.0)
        assert stats.call_count == 3
        print(f"[PASS] ToolExecutionStats.async_update")

        logger.info("=== All v3.0 tool_registry/models self-tests passed ===")

    asyncio.run(_self_test())
