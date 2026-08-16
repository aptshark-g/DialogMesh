# -*- coding: utf-8 -*-
"""SelfIntrospection — 元认知读自己的系统（系统自画像）。

设计: SELF_REPAIR_DESIGN_20260816.md §二
  元认知"认识自己": 模块地图 / 测试覆盖 / 变更历史 / 已知薄弱点。
  快照落盘 data/system_profile.json; 白盒 /v6/system-profile。
  自画像用于诊断/修复时的证据注入（A19 白盒 + A10 复盘）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CORE_DIR = os.path.join(PROJECT_ROOT, "core", "agent")


def _default_profile_path() -> str:
    return os.path.join(PROJECT_ROOT, "data", "system_profile.json")


def scan_modules() -> List[Dict[str, Any]]:
    """core/agent 模块地图（目录 + 各模块职责注释首行）。"""
    modules = []
    try:
        for name in sorted(os.listdir(CORE_DIR)):
            d = os.path.join(CORE_DIR, name)
            if not os.path.isdir(d) or name.startswith((".", "_")):
                continue
            init = os.path.join(d, "__init__.py")
            doc = ""
            if os.path.exists(init):
                try:
                    with open(init, "r", encoding="utf-8",
                              errors="ignore") as f:
                        text = f.read(2000)
                    if text.startswith(('"""', "'''")):
                        end = text.find('"""', 3) if text.startswith('"""') \
                            else text.find("'''", 3)
                        doc = text[3:end if end > 0 else 300].strip()
                        doc = " ".join(doc.split())[:120]
                except Exception:
                    pass
            modules.append({"name": name, "path": d, "doc": doc})
    except Exception as e:
        logger.debug("module scan failed: %s", e)
    return modules


def scan_tests() -> Dict[str, Any]:
    """测试覆盖统计（core/agent 下测试文件/用例数, 不执行）。"""
    files = 0
    cases = 0
    by_module: Dict[str, int] = {}
    try:
        for root, _dirs, fnames in os.walk(CORE_DIR):
            for fn in fnames:
                if not (fn.startswith("test_") and fn.endswith(".py")):
                    continue
                files += 1
                rel = os.path.relpath(root, CORE_DIR)
                mod = rel.split(os.sep)[0]
                by_module[mod] = by_module.get(mod, 0) + 1
                try:
                    with open(os.path.join(root, fn), "r", encoding="utf-8",
                              errors="ignore") as f:
                        text = f.read()
                    cases += (text.count("def test_")
                              + text.count("    def test_"))
                except Exception:
                    pass
    except Exception as e:
        logger.debug("test scan failed: %s", e)
    return {"test_files": files, "test_cases_approx": cases,
            "by_module": dict(sorted(
                by_module.items(), key=lambda kv: -kv[1])[:20])}


def scan_git_history(limit: int = 20) -> List[Dict[str, Any]]:
    """最近变更（git log）→ 活跃/薄弱区线索。"""
    out = []
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", PROJECT_ROOT, "log", "--oneline", "-n",
             str(limit)],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                out.append({"hash": parts[0][:12],
                            "subject": parts[1][:100]})
    except Exception as e:
        logger.debug("git history failed: %s", e)
    return out


def weak_spots() -> Dict[str, Any]:
    """已知薄弱点: 诊断报告 + governor 熔断失败统计。"""
    out: Dict[str, Any] = {"diagnosis_reports": 0, "high_failure_scopes": []}
    try:
        from core.agent.meta.diagnosis import get_diagnoser
        s = get_diagnoser().stats()
        out["diagnosis_reports"] = len(s.get("reports") or [])
    except Exception:
        pass
    try:
        from core.agent.meta.governor import get_governor
        for b in get_governor().stats().get("breakers", []):
            if b.get("total_failures", 0) > 0:
                out["high_failure_scopes"].append(b)
    except Exception:
        pass
    return out


class SystemIntrospector:
    """系统自画像（快照 + 落盘; 线程安全）。"""

    def __init__(self, path: str = ""):
        self._path = path or _default_profile_path()
        self._lock = threading.Lock()
        self._profile: Dict[str, Any] = {}

    def build(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            if not force and self._profile.get("ts", 0) > now - 300:
                return self._profile
            profile = {
                "ts": now,
                "modules": scan_modules(),
                "tests": scan_tests(),
                "git_history": scan_git_history(),
                "weak_spots": weak_spots(),
            }
            self._profile = profile
            self._save()
            return profile

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._profile, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path)
        except Exception as e:
            logger.debug("system profile save failed: %s", e)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._profile) if self._profile else self.build()


_introspector: Any = None


def get_introspector() -> SystemIntrospector:
    global _introspector
    if _introspector is None:
        _introspector = SystemIntrospector()
    return _introspector


def system_profile(force: bool = False) -> Dict[str, Any]:
    try:
        return get_introspector().build(force=force)
    except Exception:
        return {}
