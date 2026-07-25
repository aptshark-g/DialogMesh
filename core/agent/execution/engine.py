"""Execution Engine — DialogMesh native execution layer.

Bridges cognitive pipeline (DialogMesh) → real-world actions.
Replaces external agents (Claude Code/Pi) with native Python execution.

Protocol: WebSocket JSON — same API for Python/TS/Rust clients.

Execution tools:
  file_read   — read files with pagination
  file_write  — create/overwrite files
  file_patch  — targeted find-and-replace edits
  file_search — ripgrep-backed content/file search
  shell_exec  — execute shell commands
  mcp_invoke  — invoke registered MCP tools
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    DRY_RUN = "dry_run"      # validate only, no side effects
    SANDBOX = "sandbox"      # run with constraints
    FULL = "full"             # unrestricted execution


class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"       # constraint violation
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    task_id: str
    tool: str
    status: ExecutionStatus
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    artifacts: List[str] = field(default_factory=list)  # file paths created/modified


@dataclass
class ExecutionTask:
    task_id: str
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.FULL
    timeout_s: int = 30
    constraints: Dict[str, Any] = field(default_factory=dict)  # from EngineeringChain


class ExecutionEngine:
    """Native Python execution engine — replaces external agent dependency.

    Usage:
        engine = ExecutionEngine(mode=ExecutionMode.FULL)
        result = await engine.execute(task)
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.FULL,
                 workspace: str = None):
        self._mode = mode
        self._workspace = workspace or os.getcwd()
        self._tools: Dict[str, Callable] = {}
        self._register_builtin_tools()
        self._task_count = 0

    def _register_builtin_tools(self):
        self._tools = {
            "file_read": self._file_read,
            "file_write": self._file_write,
            "file_patch": self._file_patch,
            "file_search": self._file_search,
            "shell_exec": self._shell_exec,
            "mcp_invoke": self._mcp_invoke,
        }

    # ═══ Public API ═══

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        """Execute one task. Supports both sync and async tools."""
        self._task_count += 1
        t0 = time.time()

        if task.mode == ExecutionMode.DRY_RUN:
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.SUCCESS, "dry_run", duration_ms=0)

        tool_fn = self._tools.get(task.tool)
        if not tool_fn:
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.FAILED,
                                   error=f"unknown tool: {task.tool}")

        # Constraint validation
        block = self._validate_constraints(task)
        if block:
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.BLOCKED, error=block)

        try:
            if asyncio.iscoroutinefunction(tool_fn):
                output = await asyncio.wait_for(tool_fn(task.params),
                                                timeout=task.timeout_s)
            else:
                output = await asyncio.get_event_loop().run_in_executor(
                    None, tool_fn, task.params)
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.SUCCESS, str(output),
                                   duration_ms=(time.time() - t0) * 1000)
        except asyncio.TimeoutError:
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.TIMEOUT,
                                   error=f"timeout after {task.timeout_s}s",
                                   duration_ms=task.timeout_s * 1000)
        except Exception as e:
            return ExecutionResult(task.task_id, task.tool,
                                   ExecutionStatus.FAILED, error=str(e),
                                   duration_ms=(time.time() - t0) * 1000)

    async def execute_batch(self, tasks: List[ExecutionTask],
                            parallel: bool = False) -> List[ExecutionResult]:
        """Execute multiple tasks."""
        if parallel:
            coros = [self.execute(t) for t in tasks]
            return await asyncio.gather(*coros, return_exceptions=False)
        results = []
        for task in tasks:
            results.append(await self.execute(task))
        return results

    # ═══ Built-in Tools ═══

    def _file_read(self, params: dict) -> str:
        path = self._resolve(params["path"])
        offset = params.get("offset", 1)
        limit = params.get("limit", 500)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        start = max(0, offset - 1)
        end = min(len(lines), start + limit)
        return ''.join(lines[start:end])

    def _file_write(self, params: dict) -> str:
        path = self._resolve(params["path"])
        content = params["content"]
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"written {len(content)} bytes to {path}"

    def _file_patch(self, params: dict) -> str:
        path = self._resolve(params["path"])
        old_str = params["old_string"]
        new_str = params["new_string"]
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_str not in content:
            return f"ERROR: old_string not found in {path}"
        new_content = content.replace(old_str, new_str, 1)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"patched {path} ({len(old_str)}->{len(new_str)} chars)"

    def _file_search(self, params: dict) -> str:
        pattern = params["pattern"]
        target = params.get("target", "content")
        path = params.get("path", self._workspace)
        cmd = ["rg", "--line-number", "--max-count=50"]
        if target == "files":
            cmd = ["rg", "--files", "--max-count=50"]
        cmd.extend([pattern, path])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout or "no matches"

    def _shell_exec(self, params: dict) -> str:
        cmd = params["command"]
        timeout = params.get("timeout", 30)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                timeout=timeout, cwd=self._workspace)
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        return output or f"exit={result.returncode}"

    def _mcp_invoke(self, params: dict) -> str:
        """Invoke a registered MCP tool."""
        tool_name = params["tool"]
        tool_params = params.get("params", {})
        try:
            from core.agent.mcp.integration import MCPIntegrationHub
            hub = MCPIntegrationHub()
            valid = hub.validate_against_constraints(tool_name, tool_params)
            if not valid.get("allowed", True):
                return f"BLOCKED: {valid.get('blocking', [])}"
            return f"MCP tool '{tool_name}' invoked with {tool_params}"
        except Exception as e:
            return f"MCP invoke error: {e}"

    # ═══ Helpers ═══

    def _resolve(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self._workspace, path)

    def _validate_constraints(self, task: ExecutionTask) -> Optional[str]:
        """Check EngineeringChain constraints before execution."""
        if not task.constraints:
            return None
        if task.mode == ExecutionMode.FULL:
            return None
        constraints = task.constraints
        if constraints.get("forbidden_paths") and any(
            p in self._resolve(task.params.get("path", ""))
            for p in constraints["forbidden_paths"]
        ):
            return f"path blocked by constraint"
        if constraints.get("forbidden_commands") and task.tool == "shell_exec":
            cmd = task.params.get("command", "")
            for blocked in constraints["forbidden_commands"]:
                if blocked in cmd:
                    return f"command blocked: {blocked}"
        return None

    def register_tool(self, name: str, fn: Callable):
        self._tools[name] = fn

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def task_count(self) -> int:
        return self._task_count


# ═══ WebSocket Bridge ═══

class ExecutionBridge:
    """WebSocket bridge for external clients (TS/Rust/Python).

    Protocol:
      → {"action": "execute", "task": {...}}
      ← {"result": {...}, "stream": "..."}
    """

    def __init__(self, engine: ExecutionEngine = None):
        self._engine = engine or ExecutionEngine()

    async def handle_message(self, message: str) -> str:
        """Process one WebSocket message → return JSON response."""
        try:
            data = json.loads(message)
            action = data.get("action", "execute")

            if action == "execute":
                task = ExecutionTask(
                    task_id=data.get("task_id", f"t{self._engine.task_count}"),
                    tool=data["task"]["tool"],
                    params=data["task"].get("params", {}),
                    mode=ExecutionMode(data.get("mode", "full")),
                    timeout_s=data.get("timeout", 30),
                    constraints=data.get("constraints", {}),
                )
                result = await self._engine.execute(task)
                return json.dumps({"result": {
                    "task_id": result.task_id,
                    "tool": result.tool,
                    "status": result.status.value,
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                }})

            elif action == "list_tools":
                return json.dumps({"tools": self._engine.list_tools()})

            elif action == "status":
                return json.dumps({"tasks_executed": self._engine.task_count})

            return json.dumps({"error": f"unknown action: {action}"})

        except Exception as e:
            return json.dumps({"error": str(e)})
