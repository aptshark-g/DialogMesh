"""Tool Registry — dynamic tool discovery, auto-install, LLM self-authoring.

Level 1: Tool exists → direct execute
Level 2: Tool missing → auto pip install → register → execute
Level 3: Cannot install → LLM generates code → sandbox validate → register → execute
"""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("dm.tools")


# ═══════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    artifact_path: Optional[str] = None


@dataclass
class ToolAdapter:
    """One tool that LLM can discover and call.

    Registration: 3 lines:
        ToolRegistry.register(MyTool)
    """
    name: str
    description: str               # LLM uses this to decide if tool matches
    category: str = "general"      # search | file | parse | compute | code | web
    keywords_zh: List[str] = field(default_factory=list)  # 中文关键词（discover 双语言匹配）
    dependencies: List[str] = field(default_factory=list)  # pip packages
    input_schema: Dict[str, str] = field(default_factory=dict)
    handler: Optional[Callable] = None  # execute(**kwargs) → ToolResult
    enabled: bool = True
    auto_install: bool = True
    availability: Dict[str, Any] = field(default_factory=dict)
    # P1-4 (FLOW_SELF_GROWTH §5.5 OpenClaw availability signal):
    #   条件工具可见性 — {"env": ["GITHUB_TOKEN"], "config": ["gateway.url"],
    #   "auth": True, "note": "需要 GitHub token"}
    #   env    — 全部 env 变量存在才可见
    #   config — 全部配置键存在才可见（ToolRegistry._config 注入, 默认空）
    #   auth   — 需要认证（ToolRegistry._auth_ok 注入）
    #   note   — 不可用原因（LLM/前端可见）
    _instance: Any = None           # cached class instance

    def execute(self, **kwargs) -> ToolResult:
        t0 = time.time()
        try:
            if self.handler:
                result = self.handler(**kwargs)
            elif self._instance and hasattr(self._instance, 'execute'):
                result = self._instance.execute(**kwargs)
            else:
                return ToolResult(self.name, False, error="No handler")
            if isinstance(result, ToolResult):
                result.latency_ms = (time.time() - t0) * 1000
                return result
            return ToolResult(self.name, True, data=result, latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return ToolResult(self.name, False, error=str(e), latency_ms=(time.time() - t0) * 1000)


# ═══════════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════════

class ToolRegistry:
    _tools: Dict[str, ToolAdapter] = {}
    _categories: Dict[str, List[str]] = {}
    _auto_install_log: List[str] = []
    _config: Dict[str, Any] = {}     # P1-4: 配置注入（engine/bootstrap 挂载）
    _auth_ok: bool = False           # P1-4: 认证状态（auth 条件工具）

    # ── Registration ──

    @classmethod
    def register(cls, tool: ToolAdapter) -> None:
        if tool.name in cls._tools:
            logger.warning("Tool %s already registered, overwriting", tool.name)
        cls._tools[tool.name] = tool
        cls._categories.setdefault(tool.category, []).append(tool.name)
        logger.info("+tool %s (%s)", tool.name, tool.category)

    @classmethod
    def unregister(cls, name: str) -> bool:
        tool = cls._tools.pop(name, None)
        if tool:
            cls._categories.get(tool.category, []).remove(name)
            return True
        return False

    # ── P1-4 availability signal ──

    @classmethod
    def set_config(cls, cfg: Dict[str, Any]):
        """注入配置（engine/bootstrap 装配时调用; 影响 config 条件可见性）."""
        if isinstance(cfg, dict):
            cls._config = cfg

    @classmethod
    def set_auth(cls, ok: bool):
        """注入认证状态（auth 条件工具可见性）."""
        cls._auth_ok = bool(ok)

    @classmethod
    def availability_reason(cls, tool: ToolAdapter) -> str:
        """返回空串 = 可用; 非空 = 不可用原因."""
        if not tool.enabled:
            return "disabled"
        for key in tool.availability.get("env", []):
            if not os.environ.get(key):
                return f"missing env {key}"
        for key in tool.availability.get("config", []):
            if key not in cls._config:
                return f"missing config {key}"
        if tool.availability.get("auth") and not cls._auth_ok:
            return "auth required"
        return ""

    @classmethod
    def is_available(cls, name: str) -> tuple:
        """(ok, reason) — 工具是否当前可见/可用."""
        tool = cls._tools.get(name)
        if tool is None:
            return (False, f"not registered: {name}")
        reason = cls.availability_reason(tool)
        return (reason == "", reason)

    # ── Discovery ──

    @classmethod
    def discover(cls, query: str, limit: int = 5) -> List[ToolAdapter]:
        """Return tools whose description/name matches the query.

        LLM calls this: "有没有搜论文的工具？" → matches arxiv_search

        E2 (ERROR_META_REFLECTION): 接 zh_keyword_match — 中文意图匹配
        英文工具描述（"查论文" ↔ arxiv_search.keywords_zh），根治子串
        匹配缺陷。
        """
        from core.agent.common.text_utils import zh_keyword_match
        scored = []
        for t in cls._tools.values():
            if cls.availability_reason(t):
                continue
            if zh_keyword_match(query, t.keywords_zh,
                                en_text=t.description, name=t.name):
                scored.append((1.0, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]

    @classmethod
    def list_all(cls, include_unavailable: bool = False) -> List[Dict[str, Any]]:
        """Return summary of all tools for LLM context."""
        out = []
        for t in cls._tools.values():
            reason = cls.availability_reason(t)
            if reason and not include_unavailable:
                continue
            item = {"name": t.name, "description": t.description,
                    "category": t.category, "schema": t.input_schema,
                    "enabled": t.enabled}
            if reason:
                item["unavailable_reason"] = reason
                item["availability_note"] = t.availability.get("note", "")
            out.append(item)
        return out

    # ── Resolution (Level 1 + 2) ──

    @classmethod
    def resolve(cls, name: str, auto_install: bool = True) -> ToolAdapter:
        """Get tool by name. If deps missing and auto_install=True, pip install."""
        if name not in cls._tools:
            raise KeyError(f"Tool '{name}' not registered. Available: {list(cls._tools)}")
        tool = cls._tools[name]
        reason = cls.availability_reason(tool)
        if reason:
            note = tool.availability.get("note", "")
            raise RuntimeError(
                f"Tool '{name}' unavailable: {reason}"
                + (f" ({note})" if note else "")
            )

        # Check dependencies
        missing = []
        for dep in tool.dependencies:
            try:
                importlib.import_module(dep.replace("-", "_"))
            except ImportError:
                missing.append(dep)

        if missing and auto_install and tool.auto_install:
            logger.info("Installing deps for %s: %s", name, missing)
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-q"] + missing,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=120,
                )
                cls._auto_install_log.append(f"{name}: installed {missing}")
            except Exception as e:
                cls._auto_install_log.append(f"{name}: install failed {missing} → {e}")
                raise RuntimeError(
                    f"Auto-install failed for tool '{name}': {missing}. "
                    f"You can write a custom tool: class MyTool(ToolAdapter): ..."
                ) from e

        return tool

    # ── Execution ──

    @classmethod
    def execute(cls, name: str, **kwargs) -> ToolResult:
        """Resolve and execute a tool. Handles Level 1 + 2 automatically."""
        tool = cls.resolve(name)
        return tool.execute(**kwargs)

    # ── Status ──

    @classmethod
    def status(cls) -> Dict[str, Any]:
        return {
            "total_tools": len(cls._tools),
            "categories": {c: len(ts) for c, ts in cls._categories.items()},
            "tools": {n: {"enabled": t.enabled, "category": t.category,
                          "deps_ok": cls._check_deps(t),
                          "available": cls.availability_reason(t) == ""}
                     for n, t in cls._tools.items()},
            "auto_installs": cls._auto_install_log[-5:],
        }

    @classmethod
    def _check_deps(cls, tool: ToolAdapter) -> bool:
        for dep in tool.dependencies:
            try:
                importlib.import_module(dep.replace("-", "_"))
            except ImportError:
                return False
        return True


# ═══════════════════════════════════════════════════════════════
# Built-in tools (lightweight, no external deps)
# ═══════════════════════════════════════════════════════════════

def _builtin_echo(**kwargs) -> ToolResult:
    return ToolResult("echo", True, data=kwargs)

def _builtin_time(**kwargs) -> ToolResult:
    return ToolResult("time", True, data={"iso": time.strftime("%Y-%m-%dT%H:%M:%SZ")})

ToolRegistry.register(ToolAdapter(
    name="echo", description="Echo back the input arguments for testing",
    category="general", handler=_builtin_echo,
    input_schema={"message": "string to echo back"},
))
ToolRegistry.register(ToolAdapter(
    name="time", description="Get current UTC time in ISO 8601 format",
    category="general", handler=_builtin_time,
    input_schema={},
))
