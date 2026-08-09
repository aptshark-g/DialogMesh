# -*- coding: utf-8 -*-
"""OS 控制工具 — run_shell / run_python（参考 OpenClaw exec 模式）。

设计（OPENCLAW_OS_TOOLS_20260808）:
  - run_shell: 本地 shell 执行, 走 PermissionEngine 审批门（F1 已接
    executor）, 超时 kill, 结构化返回（失败不抛异常, agent 可自纠正）
  - run_python: 代码执行（测试/计算）, 同权限门 + 输出截断
"""
from __future__ import annotations

import shlex
import subprocess
import sys
import threading
from typing import Dict, Optional

from core.agent.tools.registry import ToolAdapter, ToolResult, ToolRegistry

DEFAULT_TIMEOUT_S = 30
MAX_OUTPUT_CHARS = 20000

# ── 长任务会话管理（OpenClaw node_process 对标, 第一版子集）────────
_SESSIONS: Dict[str, Dict] = {}
_session_lock = threading.Lock()


def _session_new(command: str, cwd: str = "") -> Dict:
    """启动后台会话。返回会话信息。"""
    import uuid
    import subprocess
    if sys.platform == "win32":
        argv = ["cmd", "/c", command]
    else:
        argv = ["/bin/sh", "-c", command]
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd or None, text=True, encoding="utf-8", errors="replace")
    sid = uuid.uuid4().hex[:12]
    with _session_lock:
        _SESSIONS[sid] = {
            "id": sid, "proc": proc, "command": command,
            "created": __import__("time").time(),
            "stdout": "", "stderr": "", "done": False, "exit_code": None,
        }
    return _SESSIONS[sid]


def _session_poll(sid: str) -> Dict:
    """轮询会话（非阻塞）。已结束 → 收割输出。"""
    with _session_lock:
        s = _SESSIONS.get(sid)
    if s is None:
        return {"error": f"session not found: {sid}", "done": True}
    proc = s["proc"]
    if not s["done"]:
        try:
            out, err = proc.communicate(timeout=0.1)
        except Exception:
            out, err = None, None
        if out:
            s["stdout"] += out
        if err:
            s["stderr"] += err
        if proc.poll() is not None:
            s["done"] = True
            s["exit_code"] = proc.returncode
            # 最后一次收割
            try:
                o2, e2 = proc.communicate(timeout=2)
                if o2:
                    s["stdout"] += o2
                if e2:
                    s["stderr"] += e2
            except Exception:
                pass
    return {
        "id": sid, "done": s["done"], "exit_code": s["exit_code"],
        "stdout_tail": _truncate(s["stdout"][-4000:]),
        "stderr_tail": _truncate(s["stderr"][-2000:]),
    }


def _session_kill(sid: str) -> Dict:
    with _session_lock:
        s = _SESSIONS.get(sid)
    if s is None:
        return {"error": f"session not found: {sid}"}
    _kill_tree(s["proc"])
    s["done"] = True
    return {"id": sid, "killed": True}


def _session_list() -> Dict:
    with _session_lock:
        items = [{
            "id": s["id"], "command": s["command"][:60],
            "done": s["done"],
        } for s in _SESSIONS.values()]
    return {"sessions": items, "count": len(items)}


def _run_session(command: str = "", action: str = "new", session_id: str = "",
                 cwd: str = "", **kwargs) -> ToolResult:
    """长任务会话管理: action = new|poll|kill|list."""
    try:
        if action == "list":
            return ToolResult("run_session", True, data=_session_list())
        if action == "kill":
            if not session_id:
                return ToolResult("run_session", False,
                                  error="session_id required for kill")
            result = _session_kill(session_id)
            if "error" in result:
                return ToolResult("run_session", False, error=result["error"])
            return ToolResult("run_session", True, data=result)
        if action == "poll":
            if not session_id:
                return ToolResult("run_session", False,
                                  error="session_id required for poll")
            return ToolResult("run_session", True,
                              data=_session_poll(session_id))
        # new
        if not command:
            return ToolResult("run_session", False, error="command required")
        s = _session_new(command, cwd)
        return ToolResult("run_session", True, data={
            "session_id": s["id"], "command": s["command"][:120],
            "note": "use run_session action=poll to follow up",
        })
    except Exception as e:
        return ToolResult("run_session", False, error=f"session failed: {e}")


def _dir_list(path: str = ".", **kwargs) -> ToolResult:
    """列出目录内容（实现软件: 查看项目结构）。"""
    import os
    try:
        p = path or "."
        entries = []
        for name in sorted(os.listdir(p)):
            full = os.path.join(p, name)
            is_dir = os.path.isdir(full)
            try:
                size = 0 if is_dir else os.path.getsize(full)
            except Exception:
                size = -1
            entries.append({"name": name, "dir": is_dir, "size": size})
        return ToolResult("dir_list", True, data={
            "path": p, "count": len(entries), "entries": entries[:200]})
    except Exception as e:
        return ToolResult("dir_list", False, error=str(e))


def _grep(pattern: str = "", path: str = ".", max_results: int = 50,
          **kwargs) -> ToolResult:
    """代码探索: 递归搜索文本/正则（实现软件: 找代码在哪）。"""
    import os
    import re
    if not pattern:
        return ToolResult("grep", False, error="pattern required")
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return ToolResult("grep", False, error=f"bad regex: {e}")
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist",
                 "build", ".benchmarks", ".pytest_cache"}
    matches = []
    root = path or "."
    if os.path.isfile(root):
        # 单文件直接搜
        try:
            with open(root, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if compiled.search(line):
                        matches.append({
                            "file": root, "line": lineno,
                            "text": line.strip()[:160]})
                        if len(matches) >= max_results:
                            break
        except Exception:
            pass
        return ToolResult("grep", True, data={
            "pattern": pattern, "path": root,
            "count": len(matches), "matches": matches,
            "truncated": len(matches) >= max_results})
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith((".pyc", ".png", ".jpg", ".bin", ".lock")):
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) > 2 * 1024 * 1024:
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if compiled.search(line):
                            matches.append({
                                "file": full, "line": lineno,
                                "text": line.strip()[:160],
                            })
                            if len(matches) >= max_results:
                                return ToolResult("grep", True, data={
                                    "pattern": pattern, "path": root,
                                    "count": len(matches),
                                    "matches": matches,
                                    "truncated": True})
            except Exception:
                continue
        if len(matches) >= max_results:
            break
    return ToolResult("grep", True, data={
        "pattern": pattern, "path": root,
        "count": len(matches), "matches": matches,
        "truncated": False})


def _kill_tree(proc: subprocess.Popen) -> None:
    """杀进程树（Windows: taskkill /T; POSIX: 组杀）。"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5)
        else:
            import os
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"


def _run_shell(command: str = "", timeout_s: int = DEFAULT_TIMEOUT_S,
               cwd: str = "", **kwargs) -> ToolResult:
    """Run a shell command. Structured result — never raises on command failure."""
    if not command or not command.strip():
        return ToolResult("run_shell", False, error="empty command",
                          data={"exit_code": -1, "stdout": "", "stderr": "empty command"})
    # 平台 shell 包装（Windows: cmd /c; POSIX: /bin/sh -c）—
    # 支持内置命令（echo/dir/type）与管道; 链式危险由权限门拦截
    if sys.platform == "win32":
        argv = ["cmd", "/c", command]
    else:
        argv = ["/bin/sh", "-c", command]
    timeout = max(1, min(int(timeout_s or DEFAULT_TIMEOUT_S), 300))
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd or None, text=True, encoding="utf-8", errors="replace")
        timed_out = [False]

        def _timer():
            timed_out[0] = True
            _kill_tree(proc)

        timer = threading.Timer(timeout, _timer)
        timer.daemon = True
        timer.start()
        try:
            out, err = proc.communicate(timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            out, err = proc.communicate()
            timed_out[0] = True
        finally:
            timer.cancel()
        return ToolResult(
            "run_shell", proc.returncode == 0,
            error=None if proc.returncode == 0 else f"exit {proc.returncode}",
            data={
                "exit_code": proc.returncode,
                "stdout": _truncate(out or ""),
                "stderr": _truncate(err or ""),
                "timed_out": timed_out[0],
            },
        )
    except FileNotFoundError as e:
        return ToolResult("run_shell", False, error=f"command not found: {e}",
                          data={"exit_code": -1, "stdout": "", "stderr": str(e)})
    except Exception as e:
        return ToolResult("run_shell", False, error=f"shell failed: {e}",
                          data={"exit_code": -1, "stdout": "", "stderr": str(e)})


def _run_python(code: str = "", timeout_s: int = DEFAULT_TIMEOUT_S,
                cwd: str = "", **kwargs) -> ToolResult:
    """Run Python code (tests/computation). Structured result."""
    if not code or not code.strip():
        return ToolResult("run_python", False, error="empty code",
                          data={"exit_code": -1, "stdout": "", "stderr": ""})
    timeout = max(1, min(int(timeout_s or DEFAULT_TIMEOUT_S), 300))
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd or None, text=True, encoding="utf-8", errors="replace")
        timed_out = [False]

        def _timer():
            timed_out[0] = True
            _kill_tree(proc)

        timer = threading.Timer(timeout, _timer)
        timer.daemon = True
        timer.start()
        try:
            out, err = proc.communicate(timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            out, err = proc.communicate()
            timed_out[0] = True
        finally:
            timer.cancel()
        return ToolResult(
            "run_python", proc.returncode == 0,
            error=None if proc.returncode == 0 else f"exit {proc.returncode}",
            data={
                "exit_code": proc.returncode,
                "stdout": _truncate(out or ""),
                "stderr": _truncate(err or ""),
                "timed_out": timed_out[0],
            },
        )
    except Exception as e:
        return ToolResult("run_python", False, error=f"python failed: {e}",
                          data={"exit_code": -1, "stdout": "", "stderr": str(e)})


def register_os_tools() -> None:
    """注册 OS 工具到 ToolRegistry（executor 蓝图工具节点可用）。"""
    ToolRegistry.register(ToolAdapter(
        name="run_shell",
        description="运行本地 shell 命令。参数: command, timeout_s(默认30), cwd。"
                    "结构化返回 stdout/stderr/exit_code; 链式命令与危险操作被权限门拦截。",
        keywords_zh=["shell", "命令行", "执行命令", "终端", "git", "运行"],
        input_schema={
            "command": "shell 命令(必填)",
            "timeout_s": "int 超时秒(默认30)",
            "cwd": "工作目录(默认当前)",
        },
        category="code",
        availability={"risk": "exec"},
        handler=_run_shell,
    ))
    ToolRegistry.register(ToolAdapter(
        name="run_python",
        description="运行 Python 代码（测试/计算/脚本）。参数: code, timeout_s(默认30), cwd。"
                    "结构化返回 stdout/stderr/exit_code。",
        keywords_zh=["python", "运行代码", "脚本", "测试", "计算"],
        input_schema={
            "code": "Python 代码(必填)",
            "timeout_s": "int 超时秒(默认30)",
            "cwd": "工作目录(默认当前)",
        },
        category="code",
        availability={"risk": "exec"},
        handler=_run_python,
    ))
    ToolRegistry.register(ToolAdapter(
        name="run_session",
        description="长任务会话管理（后台执行, 避免超时杀）。"
                    "action=new(启动)/poll(轮询输出)/kill(终止)/list(列出)。"
                    "参数: command, action, session_id, cwd。",
        keywords_zh=["后台", "长任务", "会话", "进程", "编译", "测试", "服务器"],
        input_schema={
            "command": "后台命令(new 用)",
            "action": "new|poll|kill|list(默认 new)",
            "session_id": "会话 id(poll/kill 用)",
            "cwd": "工作目录",
        },
        category="code",
        availability={"risk": "exec"},
        handler=_run_session,
    ))
    ToolRegistry.register(ToolAdapter(
        name="dir_list",
        description="列出目录内容（查看项目结构）。参数: path(默认当前目录)。",
        keywords_zh=["目录", "文件夹", "列表", "结构", "ls"],
        input_schema={"path": "目录路径(默认当前)"},
        category="file",
        handler=_dir_list,
    ))
    ToolRegistry.register(ToolAdapter(
        name="grep",
        description="递归搜索代码中的文本/正则（找代码在哪, 探索先行）。"
                    "参数: pattern(必填), path(默认当前目录), max_results(默认50)。",
        keywords_zh=["搜索", "查找", "grep", "定位", "代码"],
        input_schema={
            "pattern": "正则/文本(必填)",
            "path": "路径(默认当前)",
            "max_results": "int(默认50)",
        },
        category="file",
        handler=_grep,
    ))
    # 别名: 蓝图 LLM 生成 write_file（OpenClaw 风格）→ 指向 builtin file_write
    try:
        from core.agent.tools.builtin import _file_write
        ToolRegistry.register(ToolAdapter(
            name="write_file",
            description="写入文件（别名, 同 file_write）。参数: path, content。",
            keywords_zh=["写文件", "创建", "写入"],
            input_schema={"path": "文件路径(必填)", "content": "内容(必填)"},
            category="file",
            handler=_file_write,
        ))
    except Exception:
        pass


# 模块导入即注册（与 builtin.py 同约定）
register_os_tools()
