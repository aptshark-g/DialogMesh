"""File Sandbox — Git-staging + OverlayFS + WAL patterns for atomic execution.

Patterns adapted:
  Git staging:    snapshot → worktree → diff → commit / reset
  Docker Overlay: base(lower) ⊕ overlay(upper) → merged → commit layer / discard
  SQLite WAL:     append changes → review → checkpoint / truncate

Our model:
  1. snapshot(workspace)          — capture current state
  2. execute in overlay           — all writes go to temp layer
  3. diff(snapshot, overlay)      — what changed?
  4. review(ConstraintTree+User)  — safe?
  5. commit() / rollback()        — merge or discard

Design principle (用户需求):
  - 不改原有设计: 执行仅添加, 不修改原始文件 (OverlayFS copy-on-write)
  - 可回滚: snapshot → rollback 一键恢复
  - 修改意图: diff 暴露给用户/LLM/ConstraintTree → 审批 → 合并
  - 低概率高价值: 改造原有文件 → Transition 记录 → 学习
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)


# ═══ Data Models ═══

class ChangeType(Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class FileChange:
    """One file change recorded by the sandbox."""
    path: str                    # Relative path in workspace
    change_type: ChangeType
    old_hash: Optional[str] = None   # sha256 before change
    new_hash: Optional[str] = None   # sha256 after change
    old_content: Optional[str] = None  # Stored for rollback
    new_content: Optional[str] = None  # Stored for review
    old_size: int = 0
    new_size: int = 0
    lines_added: int = 0
    lines_removed: int = 0

    def to_diff(self) -> str:
        """Generate unified diff string."""
        import difflib
        if self.change_type == ChangeType.ADDED:
            return f"+ {self.path} (new: {self.new_size} bytes)"
        if self.change_type == ChangeType.DELETED:
            return f"- {self.path} (was: {self.old_size} bytes)"
        if self.old_content and self.new_content:
            diff = ''.join(difflib.unified_diff(
                self.old_content.splitlines(True),
                self.new_content.splitlines(True),
                f"a/{self.path}", f"b/{self.path}",
            ))
            return diff
        return f"  {self.path} ({self.change_type.value})"


# ═══ Overlay Layer ═══

class OverlayLayer:
    """OverlayFS layer — all writes go here, base is untouched.

    Like Docker: base(lowerdir, read-only) ⊕ overlay(upperdir, writable)
    = merged view (what the execution sees).
    """

    def __init__(self, workspace: str):
        self._workspace = os.path.abspath(workspace)
        self._overlay_dir = os.path.join(
            self._workspace, ".dm_sandbox", f"overlay_{int(time.time())}")
        os.makedirs(self._overlay_dir, exist_ok=True)
        self._writes: Dict[str, str] = {}  # path → temp file
        self._deletions: Set[str] = set()

    def resolve(self, path: str) -> str:
        """Resolve path to actual file location.

        Overlay check: if path was written to overlay, use overlay copy.
        Otherwise, use original file.
        """
        abs_path = os.path.join(self._workspace, path)

        if path in self._writes:
            return self._writes[path]
        return abs_path

    def write(self, path: str, content: str):
        """Write to overlay — never touches original file."""
        abs_path = os.path.join(self._workspace, path)
        overlay_path = os.path.join(
            self._overlay_dir,
            hashlib.sha256(abs_path.encode()).hexdigest()[:16]
        )

        os.makedirs(os.path.dirname(overlay_path), exist_ok=True)
        with open(overlay_path, 'w', encoding='utf-8') as f:
            f.write(content)

        self._writes[path] = overlay_path

    def delete(self, path: str):
        """Mark file for deletion."""
        self._deletions.add(path)

    def read(self, path: str) -> Optional[str]:
        """Read file content through overlay."""
        actual = self.resolve(path)
        if os.path.exists(actual):
            with open(actual, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        return None

    def cleanup(self):
        """Remove overlay temp files."""
        if os.path.exists(self._overlay_dir):
            shutil.rmtree(self._overlay_dir, ignore_errors=True)

    @property
    def changed_paths(self) -> Set[str]:
        return set(self._writes.keys()) | self._deletions


# ═══ File Sandbox ═══

class FileSandbox:
    """Git-staging style sandbox for atomic file operations.

    Usage:
        sb = FileSandbox(workspace)
        sb.snapshot()           # Capture baseline
        sb.write("auth.py", content)  # All writes go to overlay
        sb.edit("config.yaml", ...)   # All edits go to overlay
        diff = sb.diff()        # Review changes
        if safe:
            sb.commit()         # Merge overlay → workspace
        else:
            sb.rollback()       # Discard all changes
    """

    def __init__(self, workspace: str, constraint_tree=None):
        self._workspace = os.path.abspath(workspace)
        self._constraint = constraint_tree
        self._overlay: Optional[OverlayLayer] = None
        self._snapshot: Dict[str, str] = {}     # path → sha256
        self._snapshot_content: Dict[str, str] = {}  # path → content (small files)
        self._changes: List[FileChange] = []
        self._committed = False
        self._rolled_back = False

    # ═══ Lifecycle ═══

    def snapshot(self) -> int:
        """Capture workspace state — equivalent to git's index snapshot."""
        if self._overlay:
            self.rollback()

        self._overlay = OverlayLayer(self._workspace)
        self._snapshot = {}
        self._snapshot_content = {}
        self._changes = []
        self._committed = False
        self._rolled_back = False

        count = 0
        for root, _, files in os.walk(self._workspace):
            if '.dm_sandbox' in root or '.git' in root:
                continue
            for f in files:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self._workspace)
                h = self._hash_file(fpath)
                self._snapshot[rel] = h
                # Cache content for small files (<100KB)
                if os.path.getsize(fpath) < 100 * 1024:
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                            self._snapshot_content[rel] = fh.read()
                    except Exception:
                        pass
                count += 1

        logger.info("Sandbox snapshot: %d files", count)
        return count

    def diff(self) -> List[FileChange]:
        """Diff overlay against snapshot — equivalent to git diff."""
        if not self._overlay:
            return []

        changes = []
        changed = self._overlay.changed_paths

        for path in changed:
            old_hash = self._snapshot.get(path)
            old_content = self._snapshot_content.get(path)

            if path in self._overlay._deletions:
                changes.append(FileChange(
                    path=path, change_type=ChangeType.DELETED,
                    old_hash=old_hash, old_size=len(old_content or ""),
                ))
                continue

            new_content = self._overlay.read(path)
            new_hash = hashlib.sha256(
                (new_content or "").encode()).hexdigest()

            if old_hash is None:
                changes.append(FileChange(
                    path=path, change_type=ChangeType.ADDED,
                    new_hash=new_hash, new_content=new_content,
                    new_size=len(new_content or ""),
                    lines_added=(new_content or "").count('\n'),
                ))
            elif old_hash != new_hash:
                old_lines = old_content.count('\n') if old_content else 0
                new_lines = (new_content or "").count('\n')
                changes.append(FileChange(
                    path=path, change_type=ChangeType.MODIFIED,
                    old_hash=old_hash, new_hash=new_hash,
                    old_content=old_content, new_content=new_content,
                    old_size=len(old_content or ""), new_size=len(new_content or ""),
                    lines_added=new_lines - old_lines,
                    lines_removed=old_lines - new_lines,
                ))

        self._changes = changes
        return changes

    def review(self, audit_fn: callable = None) -> Tuple[bool, List[str]]:
        """Review changes through ConstraintTree + optional user audit.

        Returns (approved, violations).
        """
        violations = []

        for change in self._changes:
            path = change.path

            # ConstraintTree check
            if self._constraint:
                vios = self._constraint.check(
                    "edit" if change.change_type == ChangeType.MODIFIED else "write",
                    {"path": path})
                violations.extend([v["pattern"] for v in vios])

            # System file protection
            if "/etc/" in path or "/boot/" in path or "C:\\Windows" in path:
                violations.append(f"system path: {path}")

            if change.change_type == ChangeType.DELETED:
                violations.append(f"deletion: {path} (needs explicit approval)")

        # Custom audit
        if audit_fn:
            custom = audit_fn(self._changes)
            if custom:
                violations.extend(custom)

        approved = len(violations) == 0
        if not approved:
            logger.warning("Sandbox review: %d violations", len(violations))

        return approved, violations

    def commit(self) -> int:
        """Commit overlay → workspace. Equivalent to git commit."""
        if not self._overlay or self._committed or self._rolled_back:
            return 0

        count = 0
        for path in self._overlay.changed_paths:
            if path in self._overlay._deletions:
                abs_path = os.path.join(self._workspace, path)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                    count += 1
            else:
                content = self._overlay.read(path)
                if content is not None:
                    abs_path = os.path.join(self._workspace, path)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    with open(abs_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    count += 1

        self._overlay.cleanup()
        self._committed = True
        logger.info("Sandbox commit: %d files", count)
        return count

    def rollback(self):
        """Discard all overlay changes. Equivalent to git reset --hard."""
        if self._overlay:
            self._overlay.cleanup()
        self._overlay = None
        self._snapshot = {}
        self._snapshot_content = {}
        self._changes = []
        self._rolled_back = True
        logger.info("Sandbox rollback: all changes discarded")

    # ═══ Overlay Operations ═══

    def read(self, path: str) -> Optional[str]:
        """Read through overlay (sees current changes)."""
        if self._overlay:
            return self._overlay.read(path)
        return None

    def write(self, path: str, content: str):
        """Write to overlay."""
        if not self._overlay:
            raise RuntimeError("Must snapshot() first")
        self._overlay.write(path, content)

    def edit(self, path: str, edits: List[dict]):
        """Edit file through overlay (read→modify→write)."""
        current = self.read(path) or ""
        for e in edits:
            old_t = e.get("old_string", "")
            new_t = e.get("new_string", "")
            if old_t in current:
                current = current.replace(old_t, new_t,
                                         1 if not e.get("replace_all") else -1)
        self.write(path, current)

    def delete(self, path: str):
        if self._overlay:
            self._overlay.delete(path)

    # ═══ Snapshot diff helpers ═══

    def has_changed(self, path: str) -> bool:
        return path in self._overlay.changed_paths if self._overlay else False

    @property
    def snapshot_files(self) -> int:
        return len(self._snapshot)

    @staticmethod
    def _hash_file(path: str) -> str:
        try:
            with open(path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""


# ═══ SandboxIntegration — Wire into ExecutionEngine ═══

class SandboxIntegration:
    """Wires FileSandbox into ExecutionEngine for safe file operations.

    ExecutionEngine tools (write/edit/delete) → route through sandbox overlay.
    diff→review→commit/rollback after execution batch.
    """

    def __init__(self, sandbox: FileSandbox = None,
                 constraint_tree=None, plan_gate=None):
        self._sandbox = sandbox
        self._constraint = constraint_tree
        self._plan_gate = plan_gate
        self._execution_count = 0
        self._commits = 0
        self._rollbacks = 0

    async def execute_batch(self, steps: list,
                            require_review: bool = True) -> dict:
        """Execute a batch of file operations through sandbox.

        Returns:
          { status, changes: [...], approved, violations: [...], action }
        """
        self._execution_count += 1
        sandbox = self._sandbox or FileSandbox(os.getcwd(), self._constraint)

        # 1. Snapshot
        n = sandbox.snapshot()
        logger.info("Batch #%d: snapshot %d files", self._execution_count, n)

        # 2. Execute through overlay
        for step in steps:
            tool = step.get("tool", "read")
            params = step.get("params", {})

            if tool == "write":
                sandbox.write(params["path"], params["content"])
            elif tool == "edit":
                sandbox.edit(params.get("path", params.get("file", "")),
                            params.get("edits", params.get("changes", [])))
            elif tool == "delete" or tool == "rm":
                sandbox.delete(params.get("path", ""))
            # read/glob/grep: no sandbox needed

        # 3. Diff
        changes = sandbox.diff()
        if not changes:
            return {"status": "no_changes", "changes": [], "action": "skip"}

        # 4. Review
        approved, violations = sandbox.review()

        # User approval via PlanGate
        if require_review and not approved and self._plan_gate:
            # Send to PlanGate for user review
            pass  # User-in-Loop handles this

        # 5. Commit or Rollback
        if approved or not require_review:
            count = sandbox.commit()
            self._commits += 1
            return {
                "status": "committed",
                "files_changed": count,
                "changes": [{"path": c.path, "type": c.change_type.value}
                           for c in changes],
                "action": "commit",
            }
        else:
            sandbox.rollback()
            self._rollbacks += 1
            return {
                "status": "rolled_back",
                "changes": [{"path": c.path, "type": c.change_type.value}
                           for c in changes],
                "violations": violations,
                "action": "rollback",
            }

    @property
    def stats(self) -> dict:
        return {
            "executions": self._execution_count,
            "commits": self._commits,
            "rollbacks": self._rollbacks,
        }
