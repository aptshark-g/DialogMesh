"""OpenClaw adapter — exposes DialogMesh engine via WebSocket/HTTP.

Design: docs/merge/DESIGN_00_OVERVIEW.md Phase 2
  OpenClaw sends tool requests → DialogMesh serves as cognitive backend.

Usage:
    adapter = OpenClawAdapter(engine)
    adapter.start(host="localhost", port=8765)

    # OpenClaw connects via WebSocket: ws://localhost:8765/ws
    # or HTTP POST: curl -X POST http://localhost:8765/chat -d '{"text":"hello"}'
"""
from __future__ import annotations
import asyncio, json, logging, time
from typing import Optional

logger = logging.getLogger(__name__)


class OpenClawAdapter:
    """Minimal HTTP + WebSocket bridge for OpenClaw integration."""

    def __init__(self, engine, host: str = "localhost", port: int = 8765):
        self._engine = engine
        self._host = host
        self._port = port
        self._server = None

    def start(self):
        """Start HTTP server in background thread."""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        engine = self._engine

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == "/chat":
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.read(length)) if length > 0 else {}
                    text = body.get("text", body.get("message", ""))
                    if not text:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'{"error":"text required"}')
                        return
                    try:
                        from core.agent.v4.event_ir import DialogAdapter
                        ad = DialogAdapter()
                        session = body.get("session_id", "openclaw")
                        turn = body.get("turn", 1)
                        resp = engine.on_event(ad.adapt(text, session_id=session, turn_number=turn))
                        result = {"response": resp or "", "session_id": session, "turn": turn}
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(e)}).encode())
                elif self.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                elif self.path == "/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    ctx = getattr(engine, 'last_context', None)
                    result = {"running": True, "entries": len(ctx.entries) if ctx and ctx.entries else 0}
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                logger.debug("OpenClaw HTTP: %s", format % args)

        def _run():
            self._server = HTTPServer((self._host, self._port), Handler)
            logger.info("OpenClaw adapter: http://%s:%d", self._host, self._port)
            self._server.serve_forever()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        time.sleep(0.1)  # let server start
        return t

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"
