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
  GET/PUT /v6/projects/{id}/design        → 项目设计元信息（二阶抽象）
  POST   /v6/projects/{id}/design/digest → LLM 从项目会话凝练设计元信息
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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


class DesignUpdateRequest(BaseModel):
    philosophy: Optional[str] = None
    axioms: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    source: Optional[str] = "manual"


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


# ── 项目设计元信息（二阶抽象, 2026-08-17）────────────────────
# 设计理念/公理/目标是项目级"设计哲学"的元信息——二阶抽象 =
# 从项目会话实践中提炼约束与判断准则（约束长出来, 不是写出来）。

_LLM_GATEWAY_URL = os.environ.get(
    "SWITCH_GATEWAY_URL", "http://127.0.0.1:8080") + "/v1/chat/completions"
_LLM_KEY = os.environ.get("SWITCH_GATEWAY_KEY", "dm-client")


def _design_default() -> Dict[str, Any]:
    return {"philosophy": "", "axioms": [], "goals": [],
            "updated_at": 0, "source": ""}


def get_project_design(project_id: str) -> Optional[Dict[str, Any]]:
    with _PROJECTS_LOCK:
        for p in _projects():
            if p["id"] == project_id:
                d = p.setdefault("design", _design_default())
                if not isinstance(d, dict):
                    d = _design_default()
                    p["design"] = d
                return dict(d)
    return None


def save_project_design(project_id: str,
                        philosophy: Optional[str] = None,
                        axioms: Optional[List[str]] = None,
                        goals: Optional[List[str]] = None,
                        source: str = "manual") -> Optional[Dict[str, Any]]:
    with _PROJECTS_LOCK:
        for p in _projects():
            if p["id"] == project_id:
                d = p.setdefault("design", _design_default())
                if not isinstance(d, dict):
                    d = _design_default()
                    p["design"] = d
                if philosophy is not None:
                    d["philosophy"] = (philosophy or "").strip()
                if axioms is not None:
                    d["axioms"] = [a.strip() for a in (axioms or []) if a.strip()]
                if goals is not None:
                    d["goals"] = [g.strip() for g in (goals or []) if g.strip()]
                d["updated_at"] = time.time()
                d["source"] = source
                _save()
                return dict(d)
    return None


def _collect_project_sessions(project_id: str,
                              limit: int = 5,
                              max_chars: int = 600) -> List[Dict[str, str]]:
    """取项目下会话的样本（首条 user 消息）作为凝练输入, 失败返回 []。"""
    try:
        from core.agent.kernel.dispatch import (
            kernel_sessions, kernel_session_detail)
        res = kernel_sessions()
        sp = _session_project()
        sessions = [s for s in res.get("sessions", [])
                    if sp.get(s.get("id", "")) == project_id]
        out: List[Dict[str, str]] = []
        for s in sessions[:limit]:
            det = kernel_session_detail(s.get("id", ""))
            sample = ""
            for m in (det.get("messages") or []):
                if m.get("role") == "user":
                    sample = (m.get("content") or "")[:max_chars]
                    break
            out.append({
                "name": s.get("title") or s.get("id") or s.get("name") or "",
                "sample": sample,
            })
        return out
    except Exception as e:
        logger.warning("collect project sessions failed: %s", e)
        return []


def _template_design(name: str, sessions: List[Dict[str, str]]) -> Dict[str, Any]:
    """模板兜底（无 LLM / 失败）——可逆推句式。"""
    n = len(sessions)
    return {
        "philosophy": (
            "以项目「%s」为载体, 在 %d 个会话实践中提炼约束与判断准则; "
            "约束是长出来的, 不是写出来的。" % (name, n)),
        "axioms": [
            "项目产出须可逆推回设计意图（A24 双向等价）",
            "改动前先对照项目既有公理与约束",
        ],
        "goals": [
            "沉淀该项目可复用的设计理念/公理/目标",
            "以项目为单位支持经验总结与分支管理",
        ],
    }


def _llm_design(name: str, path: str, sessions: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """LLM 二阶抽象凝练: 项目会话 → {philosophy, axioms, goals}。
    失败/超时/解析失败 → None（走模板）。"""
    session_text = "\n".join(
        "- [%s] %s" % (s["name"], (s["sample"] or "（无内容）")[:400])
        for s in sessions[:5]) or "（项目暂无会话）"
    prompt = (
        "你是二阶抽象凝练器。根据项目的会话实践, 提炼该项目的设计元信息"
        "（设计理念 / 设计公理 / 设计目标）。理念=该项目「为什么这样做」的一句话主张;"
        "公理=不可协商的约束（3 条以内）; 目标=该项目要达成的结果（3 条以内）。\n\n"
        "项目名: %s\n工作区: %s\n\n会话样本:\n%s\n\n"
        "只输出 JSON: {\"philosophy\": \"...\", \"axioms\": [\"...\"], \"goals\": [\"...\"]}"
        % (name, path or "（未关联）", session_text[:2000]))
    try:
        import urllib.request
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": 500, "temperature": 0.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            _LLM_GATEWAY_URL, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {_LLM_KEY}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read())
        text = (d["choices"][0]["message"].get("content") or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start:end + 1])
        philosophy = str(data.get("philosophy", "")).strip()
        axioms = [str(a).strip() for a in data.get("axioms", []) if str(a).strip()]
        goals = [str(g).strip() for g in data.get("goals", []) if str(g).strip()]
        if not philosophy and not axioms and not goals:
            return None
        return {"philosophy": philosophy,
                "axioms": axioms[:5], "goals": goals[:5]}
    except Exception as e:
        logger.debug("llm design digest failed: %s", e)
        return None


def digest_project_design(project_id: str,
                          use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """凝练项目设计元信息: LLM（开关开, 失败降级）→ 模板兜底。"""
    with _PROJECTS_LOCK:
        p = next((x for x in _projects() if x["id"] == project_id), None)
    if p is None:
        return None
    sessions = _collect_project_sessions(project_id)
    design = None
    llm_ok = False
    if use_llm and os.environ.get("DM_PROJECT_DESIGN_LLM", "1").lower() not in (
            "0", "false", "off", "no"):
        design = _llm_design(p.get("name", ""), p.get("path", ""), sessions)
        llm_ok = design is not None
    if design is None:
        design = _template_design(p.get("name", ""), sessions)
    saved = save_project_design(
        project_id,
        philosophy=design["philosophy"],
        axioms=design["axioms"],
        goals=design["goals"],
        source="llm_digest" if llm_ok else "template")
    return saved


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


@router.get("/projects/{project_id}/design")
async def get_project_design_api(project_id: str):
    design = get_project_design(project_id)
    if design is None:
        raise HTTPException(status_code=404, detail="project not found")
    return design


@router.put("/projects/{project_id}/design")
async def put_project_design_api(project_id: str, req: DesignUpdateRequest):
    design = save_project_design(
        project_id, req.philosophy, req.axioms, req.goals,
        req.source or "manual")
    if design is None:
        raise HTTPException(status_code=404, detail="project not found")
    return design


@router.post("/projects/{project_id}/design/digest")
async def post_project_design_digest(project_id: str,
                                     use_llm: bool = True):
    """LLM 二阶抽象凝练（失败降级模板）: 项目会话 → 设计理念/公理/目标。"""
    design = digest_project_design(project_id, use_llm=use_llm)
    if design is None:
        raise HTTPException(status_code=404, detail="project not found")
    return design
