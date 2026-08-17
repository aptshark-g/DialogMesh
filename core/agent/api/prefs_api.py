# -*- coding: utf-8 -*-
"""用户偏好持久化（B8, 2026-08-17）。

跨设备同步用户偏好（槽位配对、UI 选项等）的服务端落点。
前端 B8 迁移: layoutStore 的 dm_layout_pairing → /v6/prefs/layout_pairing。

端点:
  GET    /v6/prefs                     → {prefs:{key:value}}
  PUT    /v6/prefs/{key} {value}       → 写偏好（值可为任意 JSON）
  DELETE /v6/prefs/{key}               → 删偏好
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

router = APIRouter(prefix="/v6/prefs", tags=["v6-prefs"])

_PREFS_FILE = os.path.join(_DATA_DIR, "user_prefs.json")
_PREFS_LOCK = threading.RLock()
_PREFS_CACHE: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _PREFS_CACHE
    if _PREFS_CACHE is not None:
        return _PREFS_CACHE
    try:
        if os.path.exists(_PREFS_FILE):
            with open(_PREFS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _PREFS_CACHE = data
                return _PREFS_CACHE
    except Exception:
        pass
    _PREFS_CACHE = {}
    return _PREFS_CACHE


def _save() -> None:
    with _PREFS_LOCK:
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            tmp = _PREFS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_PREFS_CACHE or {}, f, ensure_ascii=False)
            os.replace(tmp, _PREFS_FILE)
        except Exception:
            pass


def prefs_all() -> dict:
    return {"prefs": _load()}


def prefs_get(key: str) -> dict:
    prefs = _load()
    if key not in prefs:
        raise HTTPException(404, f"pref not found: {key}")
    return {"key": key, "value": prefs[key]}


def prefs_put(key: str, value: Any) -> dict:
    if not key or not key.strip():
        raise HTTPException(422, "key required")
    prefs = _load()
    with _PREFS_LOCK:
        prefs[key] = value
        _PREFS_CACHE = prefs
        _save()
    return {"key": key, "value": value, "saved": True}


def prefs_delete(key: str) -> dict:
    prefs = _load()
    with _PREFS_LOCK:
        existed = key in prefs
        prefs.pop(key, None)
        _PREFS_CACHE = prefs
        _save()
    return {"key": key, "deleted": existed}


class PrefValueReq(BaseModel):
    value: Any = None


@router.get("")
async def get_prefs():
    return prefs_all()


@router.get("/{key}")
async def get_pref(key: str):
    return prefs_get(key)


@router.put("/{key}")
async def put_pref(key: str, req: PrefValueReq):
    return prefs_put(key, req.value)


@router.delete("/{key}")
async def delete_pref(key: str):
    return prefs_delete(key)
