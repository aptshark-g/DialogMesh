"""Debug log sink — frontend logs POST to backend, stored to file."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Any
import json, os, time

router = APIRouter(prefix="/v6/debug", tags=["debug"])

LOG_FILE = os.path.join("data", "frontend_debug.jsonl")


class DebugLogEntry(BaseModel):
    ts: float
    type: str
    detail: str
    data: Any = None


class DebugLogBatch(BaseModel):
    entries: List[DebugLogEntry]
    url: str = ""
    user_agent: str = ""


@router.post("/logs")
async def receive_logs(batch: DebugLogBatch):
    """Receive frontend debug logs → append to file."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        for entry in batch.entries:
            line = json.dumps({"ts": entry.ts, "type": entry.type,
                               "detail": entry.detail, "data": entry.data,
                               "url": batch.url})
            f.write(line + "\n")
    return {"received": len(batch.entries)}


@router.get("/logs")
async def get_logs(limit: int = 50):
    """Read recent debug logs."""
    if not os.path.exists(LOG_FILE):
        return {"logs": [], "note": "No logs yet"}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return {"logs": [json.loads(l) for l in lines[-limit:]], "total": len(lines)}


@router.delete("/logs")
async def clear_logs():
    """Clear debug logs."""
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    return {"status": "cleared"}
