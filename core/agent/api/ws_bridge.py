"""v6 WebSocket streaming — ExecutionPipeline status → TaskFlow frontend.

Protocol: JSON messages over WebSocket at /v6/ws
Types: step_start, step_progress, step_complete, execution_done
"""

import asyncio, json, logging, time
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_ws_clients: set = set()

async def ws_handler(websocket: WebSocket):
    """WebSocket endpoint: /v6/ws — execution status stream."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        await websocket.send_json({"type":"connected","ts":time.time()})
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type":"pong","ts":time.time()})
            elif msg.get("type") == "subscribe":
                await websocket.send_json({"type":"subscribed","topic":msg.get("topic")})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


async def broadcast_status(event: str, payload: dict):
    """Broadcast execution status to all WebSocket clients."""
    msg = {"type": event, "payload": payload, "ts": time.time()}
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# ═══ Wired into ExecutionPipeline ═══

class WSBridge:
    """Call from ExecutionPipeline to push status to frontend."""
    @staticmethod
    async def step_start(step_index: int, tool: str, action: str):
        await broadcast_status("step_start", {"index": step_index, "tool": tool, "action": action})

    @staticmethod
    async def step_progress(step_index: int, output: str = ""):
        await broadcast_status("step_progress", {"index": step_index, "output": output[:200]})

    @staticmethod
    async def step_complete(step_index: int, status: str, duration_ms: float):
        await broadcast_status("step_complete", {"index": step_index, "status": status, "duration_ms": duration_ms})

    @staticmethod
    async def execution_done(summary: str, total_ms: float, passed: int, failed: int):
        await broadcast_status("execution_done", {"summary": summary, "total_ms": total_ms, "passed": passed, "failed": failed})
