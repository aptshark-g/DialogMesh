"""Git 状态只读端点（2026-08-17, 环境信息面板）。

只读仓库信息: 分支/远端/前后/暂存/未暂存/未跟踪/最近提交/变更文件。
全部 subprocess 调用只读（rev-parse / status / log / remote）, 不做任何
写操作（A21 权限只减不增）。git 不可用或非仓库时优雅降级为空态。
"""
from __future__ import annotations

import os
import subprocess
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/git", tags=["v6-git"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _git(*args: str, timeout: int = 8) -> str:
    """只读 git 命令, 失败返回空串。"""
    try:
        r = subprocess.run(
            ["git", "-C", PROJECT_ROOT, *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return ""
        return r.stdout.strip()
    except Exception as e:
        logger.debug("git %s failed: %s", args, e)
        return ""


def read_git_status() -> dict:
    """仓库状态（环境信息面板用）。"""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "（无分支）"
    remote = _git("remote", "get-url", "origin")
    ahead = behind = 0
    ab = _git("rev-list", "--left-right", "--count",
              "HEAD...@{upstream}")
    if ab and "\t" in ab:
        try:
            parts = ab.split("\t")
            behind, ahead = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            ahead = behind = 0

    last_commit: dict = {}
    log = _git("log", "-1", "--format=%H%n%s%n%ad%n%an", "--date=iso")
    if log:
        parts = log.splitlines()
        last_commit = {
            "hash": (parts[0][:12] if parts else ""),
            "message": parts[1] if len(parts) > 1 else "",
            "date": parts[2] if len(parts) > 2 else "",
            "author": parts[3] if len(parts) > 3 else "",
        }

    porcelain = _git("status", "--porcelain")
    staged = unstaged = untracked = 0
    changed: list = []
    for line in porcelain.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked += 1
        else:
            if code[0] != " ":
                staged += 1
            if code[1] != " ":
                unstaged += 1
        if len(changed) < 30:
            changed.append({"path": path[:140],
                            "status": code.strip() or "modified"})

    return {
        "repo_root": PROJECT_ROOT,
        "branch": branch,
        "remote": remote,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "last_commit": last_commit,
        "changed_files": changed,
        "dirty": bool(porcelain.strip()),
    }


@router.get("/status")
async def git_status():
    return read_git_status()
