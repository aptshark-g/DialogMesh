"""DialogMesh Tool Registry — LLM tool discovery and execution."""
from .registry import ToolAdapter, ToolResult, ToolRegistry
from . import builtin  # noqa: F401 注册内置工具（arxiv/web_fetch/pdf/file_read/file_write）
from . import os_tools  # noqa: F401 注册 OS 工具（run_shell/run_python/run_session/dir_list/grep/write_file）
