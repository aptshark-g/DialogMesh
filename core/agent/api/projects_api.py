# -*- coding: utf-8 -*-
"""项目 CRUD + 会话归属（B15/B1/B16, 2026-08-17）。

前端 P2 项目组已 localStorage 全量可用（dm_projects: projects +
sessionProject）; 本模块提供服务端持久化, 上线迁移时以前端本地数据做
初始导入。数据结构对齐前端 Project{id,name,color,createdAt} +
sessionProject{session_id: project_id}（字段 snake_case, 前端切换时映射）。

端点:
  GET    /v6/projects                    → {projects, session_project}
  POST   /v6/projects {name, color?}     → 建项目
  PATCH  /v6/projects/{id} {name?, color?} → 改名/改色
  DELETE /v6/projects/{id}               → 删项目（归属自动清除）
  PUT    /v6/sessions/{session_id}/project {project_id|null} → 会话归属写
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


def create_project(name: str, color: Optional[str] = None) -> dict:
    with _PROJECTS_LOCK:
        data = _load()
        project = {
            "id": str(uuid.uuid4())[:8],
            "name": (name or "").strip() or "未命名项目",
            "color": color or "#F59E0B",
            "created_at": time.time(),
        }
        data.setdefault("projects", []).append(project)
        _save()
        return project


def update_project(project_id: str, name: Optional[str] = None,
                   color: Optional[str] = None) -> Optional[dict]:
    with _PROJECTS_LOCK:
        for p in _projects():
            if p["id"] == project_id:
                if name is not None:
                    p["name"] = (name or "").strip() or p["name"]
                if color is not None:
                    p["color"] = color
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


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


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
    return create_project(req.name, req.color)


@router.patch("/projects/{project_id}")
async def patch_project(project_id: str, req: UpdateProjectRequest):
    updated = update_project(project_id, req.name, req.color)
    if updated is None:
        raise HTTPException(status_code=404, detail="project not found")
    return updated


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
