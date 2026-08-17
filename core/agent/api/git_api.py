"""Git 端点（2026-08-17, 环境信息面板 / 工程链副屏）。

只读: 分支/远端/变更行数/暂存·未暂存·未跟踪/最近提交/变更文件/分支列表。
写（显式用户操作, A21 需明确意图）: 切换分支 / 本地提交 / 推送到远端。
所有命令限 PROJECT_ROOT 仓库, 短超时, 错误诚实返回（不吞）。
"""
from __future__ import annotations

import os
import subprocess
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/git", tags=["v6-git"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _git_raw(*args: str, timeout: int = 20):
    """执行 git 命令, 返回 (returncode, stdout, stderr)。"""
    try:
        r = subprocess.run(
            ["git", "-C", PROJECT_ROOT, *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        logger.debug("git %s failed: %s", args, e)
        return -1, "", str(e)


def _git(*args: str, timeout: int = 8) -> str:
    """只读 git 命令, 成功返回 stdout, 失败返回空串。"""
    code, out, _ = _git_raw(*args, timeout=timeout)
    return out if code == 0 else ""


def _numstat_sum(*args: str) -> tuple:
    """统计 git diff numstat 的增删行数（含未跟踪按 1 文件计）。"""
    added = deleted = 0
    out = _git(*args)
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            a = parts[0].replace("-", "0")
            d = parts[1].replace("-", "0")
            try:
                added += int(a)
                deleted += int(d)
            except ValueError:
                pass
    return added, deleted


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

    # 变更行数（Codex 式 +N / -N）: 暂存 + 未暂存
    st_add, st_del = _numstat_sum("diff", "--cached", "--numstat")
    ws_add, ws_del = _numstat_sum("diff", "--numstat")
    additions = st_add + ws_add + untracked  # 未跟踪文件按 +1 行计
    deletions = st_del + ws_del

    branches = []
    for b in _git("for-each-ref", "--format=%(refname:short)",
                  "refs/heads").splitlines():
        if b:
            branches.append({"name": b, "current": b == branch})

    return {
        "repo_root": PROJECT_ROOT,
        "branch": branch,
        "remote": remote,
        "ahead": ahead,
        "behind": behind,
        "branches": branches,
        "additions": additions,
        "deletions": deletions,
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


class BranchSwitchRequest(BaseModel):
    name: str
    create: bool = False


@router.post("/branch")
async def git_switch_branch(req: BranchSwitchRequest):
    """切换分支（或 -c 新建并切换）。脏工作区时 git 拒绝, 错误诚实返回。"""
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="branch name required")
    args = ["switch", "-c", name] if req.create else ["switch", name]
    code, out, err = _git_raw(*args)
    if code != 0:
        raise HTTPException(status_code=409,
                            detail=err or out or "switch failed")
    return {"ok": True, "branch": name,
            "created": req.create, "detail": out}


class CommitRequest(BaseModel):
    message: str


@router.post("/commit")
async def git_commit(req: CommitRequest):
    """本地提交: git add -A + commit。"""
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="commit message required")
    code, out, err = _git_raw("add", "-A")
    if code != 0:
        raise HTTPException(status_code=409, detail=f"git add failed: {err or out}")
    code, out, err = _git_raw("commit", "-m", msg)
    if code != 0:
        raise HTTPException(status_code=409,
                            detail=err or out or "nothing to commit")
    return {"ok": True, "detail": out}


@router.post("/push")
async def git_push():
    """推送到远端 origin 当前分支。无远端时返回明确错误。"""
    remote = _git("remote", "get-url", "origin")
    if not remote:
        raise HTTPException(status_code=400,
                            detail="未配置远端 origin, 无法推送")
    code, out, err = _git_raw("push", "origin", "HEAD", timeout=60)
    if code != 0:
        raise HTTPException(status_code=409,
                            detail=err or out or "push failed")
    return {"ok": True, "detail": out}
