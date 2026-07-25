"""Execution Engine v2 — Pi-ported native execution layer.

All 9 Pi tools ported to Python: bash, read, write, edit, glob, grep, image.
Bridges DialogMesh cognitive pipeline to real-world actions.
WebSocket JSON protocol — Python/TS/Rust compatible.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import base64
import difflib
import glob
import logging
import os
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    DRY_RUN = "dry_run"
    SANDBOX = "sandbox"
    FULL = "full"


class ExecutionStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCESS = "success"
    FAILED = "failed"; BLOCKED = "blocked"; TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    task_id: str; tool: str; status: ExecutionStatus
    output: Optional[str] = None; error: Optional[str] = None
    details: Optional[dict] = None; duration_ms: float = 0.0
    artifacts: List[str] = field(default_factory=list)


@dataclass
class ExecutionTask:
    task_id: str; tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.FULL
    timeout_s: int = 30
    constraints: Dict[str, Any] = field(default_factory=dict)


# ═══ File Mutation Queue (Pi port) ═══

class FileMutationQueue:
    """Serializes mutations to the same file. Ensures atomic writes."""
    _locks: Dict[str, threading.Lock] = {}
    _lock = threading.Lock()

    @classmethod
    def _get_lock(cls, path: str) -> threading.Lock:
        with cls._lock:
            key = os.path.realpath(path)
            if key not in cls._locks:
                cls._locks[key] = threading.Lock()
            return cls._locks[key]

    @staticmethod
    def atomic_write(path: str, content: str) -> None:
        lock = FileMutationQueue._get_lock(path)
        with lock:
            tmp = f"{path}.tmp.{os.getpid()}"
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmp, path)


# ═══ Image Detection (Pi port) ═══

class ImageDetector:
    """Detect image MIME types from binary signatures."""
    _SIG = {
        b'\xff\xd8\xff': 'image/jpeg',
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'GIF87a': 'image/gif',
        b'GIF89a': 'image/gif',
        b'RIFF': 'image/webp',
        b'BM': 'image/bmp',
    }

    @staticmethod
    def detect(buf: bytes) -> Optional[str]:
        for sig, mime in ImageDetector._SIG.items():
            if buf.startswith(sig):
                return mime
        return None

    @staticmethod
    def to_base64(buf: bytes) -> str:
        return base64.b64encode(buf).decode('ascii')


# ═══ Execution Engine v2 ═══

class ExecutionEngine:
    """All 7 Pi tools ported to Python with atomic writes and image support."""

    MAX_LINES = 2000
    MAX_BYTES = 100 * 1024

    def __init__(self, mode: ExecutionMode = ExecutionMode.FULL,
                 workspace: str = None):
        self._mode = mode
        self._workspace = workspace or os.getcwd()
        self._tools: Dict[str, Callable] = {}
        self._task_count = 0
        self._register()

    def _register(self):
        self._tools = {
            "bash": self._bash, "read": self._read,
            "write": self._write, "edit": self._edit,
            "glob": self._glob, "grep": self._grep,
            "image": self._image,
        }

    # ═══ Public ═══

    async def execute(self, task: ExecutionTask) -> ExecutionResult:
        self._task_count += 1; t0 = time.time()
        if task.mode == ExecutionMode.DRY_RUN:
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.SUCCESS, "dry_run", duration_ms=0)
        fn = self._tools.get(task.tool)
        if not fn:
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.FAILED, error=f"unknown: {task.tool}")
        block = self._check_constraints(task)
        if block:
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.BLOCKED, error=block)
        try:
            if asyncio.iscoroutinefunction(fn):
                out, det = await asyncio.wait_for(fn(task.params), task.timeout_s)
            else:
                out, det = await asyncio.get_event_loop().run_in_executor(None, fn, task.params)
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.SUCCESS, out, details=det, duration_ms=(time.time()-t0)*1000)
        except asyncio.TimeoutError:
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.TIMEOUT, error=f"timeout {task.timeout_s}s", duration_ms=task.timeout_s*1000)
        except Exception as e:
            return ExecutionResult(task.task_id, task.tool, ExecutionStatus.FAILED, error=str(e), duration_ms=(time.time()-t0)*1000)

    # ═══ bash — streaming shell ═══

    def _bash(self, p: dict) -> Tuple[str, Optional[dict]]:
        cmd = p["command"]; timeout = p.get("timeout", 30); cwd = p.get("cwd", self._workspace)
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        out = r.stdout
        if r.stderr:
            out += f"\n\n[exit: {r.returncode}]\n{r.stderr[:2000]}"
        out, tr = self._trunc(out)
        return out, {"exit_code": r.returncode, "truncated": tr, "cwd": cwd}

    # ═══ read — paginated + image-aware ═══

    def _read(self, p: dict) -> Tuple[str, Optional[dict]]:
        path = self._path(p["path"])
        with open(path, 'rb') as f:
            head = f.read(32)
        mime = ImageDetector.detect(head)
        if mime:
            return f"[{mime}] {self._fsize(os.path.getsize(path))}, preview: {ImageDetector.to_base64(head)[:80]}...", {"mime": mime}

        offset = p.get("offset", 1); limit = p.get("limit", 500)
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        total = len(lines); s = max(0, offset-1); e = min(total, s+limit)
        out = ''.join(lines[s:e]); out, tr = self._trunc(out)
        return out, {"total_lines": total, "offset": offset, "truncated": tr or e < total}

    # ═══ write — atomic via mutation queue ═══

    def _write(self, p: dict) -> Tuple[str, Optional[dict]]:
        path = self._path(p["path"]); content = p["content"]
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        FileMutationQueue.atomic_write(path, content)
        return f"Wrote {len(content)} bytes to {path}", {"path": path, "bytes": len(content), "lines": content.count('\n')+1}

    # ═══ edit — multi-edit + unified diff ═══

    def _edit(self, p: dict) -> Tuple[str, Optional[dict]]:
        path = self._path(p["path"]); edits = p["edits"]
        with open(path, 'r', encoding='utf-8') as f:
            orig = f.read()
        cur, applied, conflicts = orig, 0, []
        for i, e in enumerate(edits):
            old_t = e.get("old_string") or e.get("oldText", "")
            new_t = e.get("new_string") or e.get("newText", "")
            if old_t not in cur:
                conflicts.append(f"edit[{i}]: not found"); continue
            if cur.count(old_t) > 1 and not e.get("replace_all"):
                conflicts.append(f"edit[{i}]: appears {cur.count(old_t)}x"); continue
            cur = cur.replace(old_t, new_t, 1 if not e.get("replace_all") else -1)
            applied += 1
        if conflicts:
            return f"Partial: {applied}/{len(edits)}\n" + '\n'.join(conflicts), {"applied": applied, "conflicts": len(conflicts)}
        FileMutationQueue.atomic_write(path, cur)
        diff = ''.join(difflib.unified_diff(orig.splitlines(True), cur.splitlines(True), f"a/{path}", f"b/{path}"))
        return f"Applied {applied} edit(s)\n\n```diff\n{diff}\n```", {"applied": applied, "path": path}

    # ═══ glob — file pattern search ═══

    def _glob(self, p: dict) -> Tuple[str, Optional[dict]]:
        pattern = p["pattern"]; base = p.get("path", self._workspace)
        matches = glob.glob(os.path.join(base, pattern), recursive=True)[:200]
        lines = [f"{os.path.relpath(m, self._workspace)} ({self._fsize(os.path.getsize(m) if os.path.isfile(m) else 0)})" for m in sorted(matches)]
        return '\n'.join(lines) or f"No matches for {pattern}", {"count": len(matches)}

    # ═══ grep — content search ═══

    def _grep(self, p: dict) -> Tuple[str, Optional[dict]]:
        pattern = p["pattern"]; path = p.get("path", self._workspace); g = p.get("glob")
        try:
            cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
            if g: cmd.extend(["--glob", g])
            cmd.extend([pattern, path])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out, tr = self._trunc(r.stdout)
            return out or "No matches", {"count": len([l for l in r.stdout.split('\n') if l.strip()]), "truncated": tr}
        except FileNotFoundError:
            import fnmatch
            matches, regex = [], re.compile(pattern)
            for root, _, files in os.walk(path):
                for f in files:
                    if g and not fnmatch.fnmatch(f, g): continue
                    try:
                        with open(os.path.join(root, f), 'r', encoding='utf-8', errors='replace') as fh:
                            for i, line in enumerate(fh, 1):
                                if regex.search(line):
                                    matches.append(f"{os.path.join(root, f)}:{i}:{line.rstrip()}")
                    except: pass
                    if len(matches) > 500: break
            return '\n'.join(matches[:500]), {"count": len(matches)}

    # ═══ image — MIME detection ═══

    def _image(self, p: dict) -> Tuple[str, Optional[dict]]:
        path = self._path(p["path"]); size = os.path.getsize(path)
        with open(path, 'rb') as f:
            head = f.read(32)
        mime = ImageDetector.detect(head)
        if not mime:
            return "Not an image", {"mime": None, "size": size}
        return f"[{mime}] {self._fsize(size)}", {"mime": mime, "size": size, "preview": ImageDetector.to_base64(head)[:80]}

    # ═══ Helpers ═══

    def _path(self, p: str) -> str:
        return p if os.path.isabs(p) else os.path.join(self._workspace, p)

    def _trunc(self, text: str) -> Tuple[str, bool]:
        lines = text.split('\n'); tr = len(lines) > self.MAX_LINES or len(text) > self.MAX_BYTES
        if len(lines) > self.MAX_LINES:
            text = '[truncated]\n' + '\n'.join(lines[-self.MAX_LINES:])
        if len(text) > self.MAX_BYTES:
            text = text[:self.MAX_BYTES] + f'\n... ({len(text)} bytes)'
        return text, tr

    @staticmethod
    def _fsize(s: int) -> str:
        if s < 1024: return f"{s}B"
        if s < 1048576: return f"{s/1024:.1f}KB"
        return f"{s/1048576:.1f}MB"

    def _check_constraints(self, task: ExecutionTask) -> Optional[str]:
        if not task.constraints or task.mode == ExecutionMode.FULL:
            return None
        if task.tool in ("write", "edit") and task.constraints.get("forbidden_paths"):
            tgt = self._path(task.params.get("path", ""))
            for fb in task.constraints["forbidden_paths"]:
                if fb in tgt:
                    return f"path blocked: {fb}"
        return None

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def task_count(self) -> int:
        return self._task_count
