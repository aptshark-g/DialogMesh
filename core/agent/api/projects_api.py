# -*- coding: utf-8 -*-
"""项目 CRUD + 会话归属（B15/B1/B16, 2026-08-17）。

前端 P2 项目组已 localStorage 全量可用（dm_projects: projects +
sessionProject）; 本模块提供服务端持久化, 上线迁移时以前端本地数据做
初始导入。数据结构对齐前端 Project{id,name,color,createdAt} +
sessionProject{session_id: project_id}（字段 snake_case, 前端切换时映射）。

  端点:
  GET    /v6/projects                    → {projects, session_project}
  POST   /v6/projects {name, color?, path?, create_dir?} → 建项目
  PATCH  /v6/projects/{id} {name?, color?, path?} → 改名/改色/改路径
  DELETE /v6/projects/{id}               → 删项目（归属自动清除）
  PUT    /v6/sessions/{session_id}/project {project_id|null} → 会话归属写
  GET    /v6/projects/browse?path=       → 只读列出子目录（项目文件夹选择）
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

router = APIRouter(prefix="/v6", tags=["v6-projects"])

_PROJECTS_FILE = os.path.join(_DATA_DIR, "projects.json")
_PROJECTS_LOCK = threading.RLock()   # 可重入: _save 在调用方持锁时二次获取
_PROJECTS_CACHE: Optional[Dict[str, Any]] = None
_UNSET = object()  # 哨兵: 区分「未提供」vs「显式置 None（清除）」


def _load() -> Dict[str, Any]:
    global _PROJECTS_CACHE
    if _PROJECTS_CACHE is not None:
        return _PROJECTS_CACHE
    try:
        if os.path.exists(_PROJECTS_FILE):
            with open(_PROJECTS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _PROJECTS_CACHE = {
                    "projects": data.get("projects") or [],
                    "session_project": data.get("session_project") or {},
                }
                return _PROJECTS_CACHE
    except Exception:
        pass
    _PROJECTS_CACHE = {"projects": [], "session_project": {}}
    return _PROJECTS_CACHE


def _save() -> None:
    with _PROJECTS_LOCK:
        try:
            os.makedirs(os.path.dirname(_PROJECTS_FILE), exist_ok=True)
            tmp = _PROJECTS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_PROJECTS_CACHE, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _PROJECTS_FILE)
        except Exception:
            pass


def _projects() -> List[dict]:
    return _load().setdefault("projects", [])


def _session_project() -> Dict[str, str]:
    return _load().setdefault("session_project", {})


def session_project_map() -> Dict[str, str]:
    """会话→项目映射（B1, 供 /v6/sessions 列表与前端过滤）。"""
    return dict(_session_project())


# ── 服务函数（v3_session_api 等可复用）──────────────────────────

def set_session_project(session_id: str, project_id: Optional[str]) -> bool:
    """会话归属写（B1）: project_id=None 清除归属; 项目不存在返回 False。"""
    with _PROJECTS_LOCK:
        data = _load()
        sp = data.setdefault("session_project", {})
        if project_id is None or project_id == "":
            sp.pop(session_id, None)
            _save()
            return True
        if not any(p["id"] == project_id for p in data["projects"]):
            return False
        sp[session_id] = project_id
        _save()
        return True


def create_project(name: str, color: Optional[str] = None,
                   path: Optional[str] = None,
                   create_dir: bool = False) -> dict:
    with _PROJECTS_LOCK:
        data = _load()
        project = {
            "id": str(uuid.uuid4())[:8],
            "name": (name or "").strip() or "未命名项目",
            "color": color or "#F59E0B",
            "created_at": time.time(),
        }
        if path:
            project["path"] = path.strip()
            if create_dir:
                try:
                    os.makedirs(path.strip(), exist_ok=True)
                except Exception as e:
                    raise HTTPException(status_code=400,
                                        detail=f"create dir failed: {e}")
        data.setdefault("projects", []).append(project)
        _save()
        return project


def update_project(project_id: str, name: Optional[str] = None,
                   color: Optional[str] = None,
                   path=_UNSET,
                   create_dir: bool = False) -> Optional[dict]:
    with _PROJECTS_LOCK:
        for p in _projects():
            if p["id"] == project_id:
                if name is not None:
                    p["name"] = (name or "").strip() or p["name"]
                if color is not None:
                    p["color"] = color
                if path is not _UNSET:
                    p["path"] = (path or "").strip() or None
                    if create_dir and p.get("path"):
                        try:
                            os.makedirs(p["path"], exist_ok=True)
                        except Exception as e:
                            raise HTTPException(
                                status_code=400,
                                detail=f"create dir failed: {e}")
                _save()
                return p
        return None


def delete_project(project_id: str) -> bool:
    with _PROJECTS_LOCK:
        data = _load()
        before = len(data["projects"])
        data["projects"] = [p for p in data["projects"]
                            if p["id"] != project_id]
        sp = data.setdefault("session_project", {})
        for sid in [k for k, v in sp.items() if v == project_id]:
            sp.pop(sid, None)
        if len(data["projects"]) != before:
            _save()
            return True
        return False


# ── API 模型 ─────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    color: Optional[str] = None
    path: Optional[str] = None
    create_dir: bool = False


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    path: Optional[str] = None
    create_dir: bool = False


class SessionProjectRequest(BaseModel):
    project_id: Optional[str] = None


@router.get("/projects")
async def get_projects():
    data = _load()
    return {
        "projects": data["projects"],
        "session_project": data["session_project"],
    }


@router.post("/projects")
async def post_project(req: CreateProjectRequest):
    return create_project(req.name, req.color, req.path, req.create_dir)


@router.patch("/projects/{project_id}")
async def patch_project(project_id: str, req: UpdateProjectRequest):
    fields = req.model_fields_set
    updated = update_project(
        project_id,
        req.name,
        req.color,
        req.path if "path" in fields else _UNSET,
        req.create_dir)
    if updated is None:
        raise HTTPException(status_code=404, detail="project not found")
    return updated


@router.get("/projects/browse")
async def browse_project_dirs(path: str = ""):
    """只读目录浏览（2026-08-17, 项目文件夹选择用）:
    列出 path 下的直接子目录; path 为空 → 默认项目工作区 data/projects。
    仅读目录, 不创建不删除（A21 权限只减不增）。"""
    root = path.strip() or os.path.join(_DATA_DIR, "projects")
    return _browse_dirs(root)


def _browse_dirs(root: str) -> dict:
    """只读列出 root 的直接子目录（供端点与测试复用）。"""
    import errno
    try:
        entries = sorted(
            (e for e in os.scandir(root) if e.is_dir()),
            key=lambda e: e.name.lower(),
        )
        return {
            "path": os.path.abspath(root),
            "entries": [
                {"name": e.name, "path": os.path.abspath(e.path)}
                for e in entries[:200]
            ],
        }
    except OSError as e:
        if e.errno == errno.ENOENT:
            # 目录不存在不是错误: 返回空列表（首次使用 data/projects 尚未创建）
            return {"path": os.path.abspath(root), "entries": []}
        raise HTTPException(status_code=400, detail=f"browse failed: {e}")


@router.delete("/projects/{project_id}")
async def delete_project_api(project_id: str):
    if not delete_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    return {"deleted": True, "id": project_id}


@router.put("/sessions/{session_id}/project")
async def put_session_project(session_id: str, req: SessionProjectRequest):
    ok = set_session_project(session_id, req.project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")
    return {"session_id": session_id,
            "project_id": req.project_id or None}
