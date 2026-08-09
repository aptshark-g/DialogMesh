# -*- coding: utf-8 -*-
"""FactStore — USER.md-style bounded fact layer (profile R5 ①).

Design: H1/H5 from EXTERNAL_REFERENCE (Hermes MemoryStore adapted):
  - entries are declarative facts, stored as a ``§``-separated list
  - hard char budget (default 1375); over budget the caller/LLM must
    consolidate (replace/remove) — consolidation never blocks a reply
  - injection scan on write AND on snapshot build; poisoned entries are
    replaced with a ``[BLOCKED]`` placeholder in the frozen snapshot while
    the live list keeps the raw text for user inspection (A19 white-box)
  - frozen snapshot for system-prompt injection; live state is mutable
  - drift guard: refuse writes when the on-disk file wouldn't round-trip
    (external edit / sister-session write), snapshot a .bak first
  - per-turn consolidation-failure cap so a fragile replace/add cannot
    loop the turn to budget exhaustion (Hermes #42405 pattern)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.security.input_sanitizer import InputSanitizer

logger = logging.getLogger(__name__)


ENTRY_DELIMITER = "\n§\n"
DEFAULT_CHAR_LIMIT = 1375
MAX_CONSOLIDATION_FAILURES_PER_TURN = 3
BLOCKED_PLACEHOLDER = "[BLOCKED: poisoned entry — inspect source file]"

# H2 (EXTERNAL_REFERENCE): declarative-facts 写入规范 prompt。
# 画像写入引导 — 供 LLM 侧（背景后验/写入工具）生成事实条目时遵守：
#   声明式事实而非指令 / 减少未来 steering 优先 / 7 天时效 / who-vs-how。
WRITE_GUIDANCE = """USER PROFILE (who the user is) — declarative fact entries:
- Save durable facts: user preferences, environment details, tool quirks, stable conventions.
- Prioritize what reduces future user steering — the most valuable fact prevents
  the user from having to correct or remind you again.
- Do NOT save task progress, session outcomes, PR numbers, or anything stale in 7 days.
- Write facts as DECLARATIVE FACTS, not instructions: "User prefers concise responses"
  is a fact; "Always respond concisely" is an instruction.
- Procedures and workflows belong in SKILLS (how), not the profile (who).
- Each entry is one short sentence; the store is bounded — consolidate (merge/remove)
  overlapping or stale entries when over budget, never block the reply on consolidation.
"""


class FactStore:
    """Bounded, curated fact layer with file persistence and snapshot freeze.

    One instance per user profile. Parallel states:
      - ``_system_prompt_snapshot``: frozen at load time, injected into the
        system prompt (prefix-cache stable), sanitized.
      - ``_entries``: live state, mutated by tool calls, persisted to disk.
    """

    def __init__(self, path: str = "", char_limit: int = DEFAULT_CHAR_LIMIT):
        self.path = path
        self.char_limit = char_limit
        self._entries: List[str] = []
        self._system_prompt_snapshot: str = ""
        self._sanitizer = InputSanitizer()
        self._consolidation_failures = 0
        # PE-3 (2026-08-04): 批量写 — begin_batch/end_batch 期间延迟落盘，
        # 避免 consolidate 循环里每次 add 都全量重写文件（磁盘 thrash）。
        self._batch_depth = 0
        self._pending_save = False
        self._save_count = 0  # 监控: 实际磁盘写次数
        if path:
            self.load()

    # ── Loading / snapshot ──────────────────────────────────────────────

    def load(self) -> None:
        """Load entries from disk, dedupe, sanitize the frozen snapshot."""
        if not self.path:
            return
        p = Path(self.path)
        if not p.exists():
            self._entries = []
            self._system_prompt_snapshot = ""
            return
        try:
            raw = p.read_text(encoding="utf-8")
        except (OSError, IOError) as e:
            logger.warning("FactStore read failed: %s", e)
            self._entries = []
            self._system_prompt_snapshot = ""
            return
        entries = [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]
        self._entries = list(dict.fromkeys(entries))  # dedupe, keep order
        self._rebuild_snapshot()

    def _rebuild_snapshot(self) -> None:
        """Frozen, sanitized snapshot for system-prompt injection."""
        sanitized: List[str] = []
        for entry in self._entries:
            res = self._sanitizer.check(entry)
            sanitized.append(BLOCKED_PLACEHOLDER if not res.is_safe else entry)
        self._system_prompt_snapshot = ENTRY_DELIMITER.join(sanitized)

    def reset_consolidation_failures(self) -> None:
        self._consolidation_failures = 0

    # ── PE-3: 批量写（defer full-file rewrite until end_batch）──────────

    def begin_batch(self) -> None:
        """Enter batch mode — mutations defer disk writes until end_batch()."""
        self._batch_depth += 1

    def end_batch(self) -> None:
        """Leave batch mode; flush once if any mutation happened."""
        if self._batch_depth > 0:
            self._batch_depth -= 1
        if self._batch_depth == 0 and self._pending_save:
            self._pending_save = False
            self._save()

    def __enter__(self) -> "FactStore":
        self.begin_batch()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.end_batch()
        return False  # 不吞异常

    def write_stats(self) -> dict:
        """监控: 磁盘写计数 + 批量状态（A18 可观测）。"""
        return {
            "save_count": self._save_count,
            "batch_depth": self._batch_depth,
            "pending_save": self._pending_save,
            "entries": len(self._entries),
        }

    # ── Queries ─────────────────────────────────────────────────────────

    @property
    def entries(self) -> List[str]:
        return list(self._entries)

    @property
    def char_count(self) -> int:
        return len(ENTRY_DELIMITER.join(self._entries))

    @property
    def usage(self) -> dict:
        return {
            "chars": self.char_count,
            "limit": self.char_limit,
            "pct": min(100, int((self.char_count / self.char_limit) * 100))
            if self.char_limit else 0,
            "entries": len(self._entries),
        }

    def format_for_system_prompt(self) -> Optional[str]:
        return self._system_prompt_snapshot or None

    def to_dict(self) -> dict:
        return {
            "entries": list(self._entries),
            "char_count": self.char_count,
            "char_limit": self.char_limit,
            "updated_at": time.time(),
        }

    # ── Mutations ───────────────────────────────────────────────────────

    def add(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}
        scan_error = self._scan(content)
        if scan_error:
            return {"success": False, "error": scan_error}
        drift = self._check_drift()
        if drift is not None:
            return drift
        if content in self._entries:
            return {"success": True, "done": True, "message": "Fact already exists (no duplicate added)."}
        new_total = len(ENTRY_DELIMITER.join(self._entries + [content]))
        if new_total > self.char_limit:
            return self._consolidation_failure({
                "success": False,
                "error": (
                    f"Fact store at {self.char_count:,}/{self.char_limit:,} chars. "
                    "Consolidate now: replace overlapping entries with shorter ones "
                    "or remove stale facts, then retry."
                ),
                "usage": self.usage,
                "current_entries": self._entries,
            })
        self._entries.append(content)
        self._rebuild_snapshot()
        self._save()
        return self._success()

    def replace(self, old_text: str, new_content: str) -> Dict[str, Any]:
        old_text = old_text.strip()
        new_content = new_content.strip()
        if not old_text or not new_content:
            return {"success": False, "error": "old_text and new_content are required."}
        scan_error = self._scan(new_content)
        if scan_error:
            return {"success": False, "error": scan_error}
        drift = self._check_drift()
        if drift is not None:
            return drift
        matches = [i for i, e in enumerate(self._entries) if old_text in e]
        if not matches:
            return self._consolidation_failure({
                "success": False,
                "error": f"No entry matched '{old_text}'.",
                "current_entries": self._entries,
            })
        idx = matches[0]
        test = list(self._entries)
        test[idx] = new_content
        if len(ENTRY_DELIMITER.join(test)) > self.char_limit:
            return self._consolidation_failure({
                "success": False,
                "error": "Replacement would exceed the char limit. Shorten it or remove other facts.",
                "usage": self.usage,
                "current_entries": self._entries,
            })
        self._entries[idx] = new_content
        self._rebuild_snapshot()
        self._save()
        return self._success()

    def remove(self, old_text: str) -> Dict[str, Any]:
        old_text = old_text.strip()
        if not old_text:
            return {"success": False, "error": "old_text is required."}
        drift = self._check_drift()
        if drift is not None:
            return drift
        matches = [i for i, e in enumerate(self._entries) if old_text in e]
        if not matches:
            return {"success": False, "error": f"No entry matched '{old_text}'."}
        del self._entries[matches[0]]
        self._rebuild_snapshot()
        self._save()
        return self._success()

    # ── Persistence / drift guard ───────────────────────────────────────

    def _check_drift(self) -> Optional[Dict[str, Any]]:
        """Verify the on-disk file still parses to the current in-memory entries.

        Runs BEFORE a mutation. If an external actor (patch tool, shell
        append, manual edit, sister session) changed the file, refuse the
        write and snapshot a .bak so the operator can reconcile. Without
        this guard, a full-file rewrite would silently discard foreign
        content (Hermes #26045 pattern).
        """
        if not self.path or not Path(self.path).exists():
            return None
        try:
            raw = Path(self.path).read_text(encoding="utf-8").strip()
        except (OSError, IOError):
            return None
        on_disk = [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]
        if on_disk == self._entries:
            return None
        bak = Path(self.path).with_name(f"{Path(self.path).name}.bak.{int(time.time())}")
        try:
            shutil.copy2(Path(self.path), bak)
        except OSError:
            pass
        logger.warning(
            "FactStore drift: on-disk %s differs from live state; backup at %s. Refusing write.",
            Path(self.path).name, bak.name,
        )
        return {
            "success": False,
            "error": (
                "Refusing to write: file on disk has been modified externally "
                f"(backup saved to {bak.name}). Reconcile the file to a clean "
                "§-delimited entry list, then retry."
            ),
        }

    def _save(self) -> None:
        # PE-3: 批量模式延迟落盘 — 循环内多次 add 只写一次磁盘
        if self._batch_depth > 0:
            self._pending_save = True
            return
        if not self.path:
            return
        self._save_count += 1
        p = Path(self.path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            serialized = ENTRY_DELIMITER.join(self._entries)
            fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            os.replace(tmp, p)
        except (OSError, IOError) as e:
            logger.warning("FactStore save failed: %s", e)

    def _scan(self, content: str) -> Optional[str]:
        res = self._sanitizer.check(content)
        if res.is_safe:
            return None
        return f"Content blocked by injection scan: {', '.join(res.reasons[:3])}"

    def _consolidation_failure(self, response: Dict[str, Any]) -> Dict[str, Any]:
        self._consolidation_failures += 1
        if self._consolidation_failures <= MAX_CONSOLIDATION_FAILURES_PER_TURN:
            return response
        return {
            "success": False,
            "done": True,
            "error": (
                "Fact consolidation failed repeatedly this turn. Stop retrying "
                "fact writes — leave the store unchanged and continue. The fact "
                "can be saved in a later turn."
            ),
        }

    def _success(self) -> Dict[str, Any]:
        self._consolidation_failures = 0
        return {
            "success": True,
            "done": True,
            "usage": self.usage,
            "note": "Fact saved. This update is complete — do not repeat it.",
        }


class FactStoreDriftError(Exception):
    """Raised when on-disk content would not round-trip through FactStore."""

    def __init__(self, backup_path: Path):
        self.backup_path = backup_path
        super().__init__(f"FactStore drift detected, backup at {backup_path}")


__all__ = ["FactStore", "FactStoreDriftError", "ENTRY_DELIMITER", "WRITE_GUIDANCE"]
