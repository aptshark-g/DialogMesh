# -*- coding: utf-8 -*-
"""Root pytest configuration — test monitoring (no guessing).

On failure, prints:
  - environment encoding facts (stdout/stderr/filesystem, PYTHONIOENCODING)
  - the two sides of any assertion repr'd as ASCII escapes (locale-proof)
  - captured stdout/stderr tail from the failing test

Also forces UTF-8 output so console encoding cannot silently corrupt
assertion diffs (the previous failure mode we were guessing about).
"""
from __future__ import annotations

import io
import locale
import os
import sys


# Force UTF-8 for stdout/stderr at the Python level so pytest output and
# captured text survive GBK consoles.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 2026-08-16: 测试进程统一离线 —— 模型加载绝不联网（HF hub / transformers
# 在受限网络下无超时挂起, 实测 faulthandler 180s 杀进程）。生产由
# start_server.py 与各加载点 local_files_only 兜底。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault(
    "SENTENCE_TRANSFORMERS_HOME",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))


def _ascii_repr(value) -> str:
    """Locale-proof repr: escape any non-ASCII so GBK consoles don't mangle it."""
    try:
        return repr(value).encode("ascii", "backslashreplace").decode("ascii")
    except Exception:
        return f"<unrepr: {type(value).__name__}>"


def _env_facts() -> str:
    return (
        f"fs_encoding={sys.getfilesystemencoding()} "
        f"stdout={getattr(sys.stdout, 'encoding', '?')} "
        f"stderr={getattr(sys.stderr, 'encoding', '?')} "
        f"preferred={locale.getpreferredencoding()} "
        f"PYTHONIOENCODING={os.environ.get('PYTHONIOENCODING', '')}"
    )


def pytest_assertrepr_compare(config, op, left, right):
    """Render assertion diffs with ASCII-safe reprs."""
    if op == "in":
        try:
            contained = right in left
        except Exception:
            contained = False
        return [
            f"left(container): {_ascii_repr(left)}",
            f"right(value):    {_ascii_repr(right)}",
            f"right in left:   {contained}",
        ]
    if op == "==":
        return [
            f"left:  {_ascii_repr(left)}",
            f"right: {_ascii_repr(right)}",
        ]
    if op == "is":
        return [
            f"left is:  {_ascii_repr(left)}",
            f"right is: {_ascii_repr(right)}",
        ]
    return None


def pytest_runtest_makereport(item, call):
    """Attach environment facts + captured output to every failure."""
    report = getattr(call, "result", None)
    if call.when == "call" and call.excinfo is not None:
        try:
            cap = item.config.pluginmanager.getplugin("capturemanager")
            out = ""
            if cap:
                captured = cap.get_global_captured_text()
                out = captured[-1500:] if captured else ""
            extra = (
                f"\n[MONITOR] {_env_facts()}\n"
                f"[MONITOR] captured tail:\n{out}\n"
            )
            sys.stderr.write(extra)
            sys.stderr.flush()
        except Exception:
            pass
    return report
