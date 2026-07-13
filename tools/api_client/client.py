"""DialogMesh v4 API Client — shared library for TUI/GUI.

Usage:
    from tools.api_client import DialogMeshClient

    client = DialogMeshClient("http://localhost:8000")
    client.send_event("add monitoring", event_id="ev1")
    status = client.get_status()
    hypotheses = client.inspect("hypotheses")
"""
from __future__ import annotations
import json, urllib.request, urllib.error
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class APIResponse:
    ok: bool
    data: Any = None
    error: str = ""
    status_code: int = 0


class DialogMeshClient:
    """HTTP client for DialogMesh v4 REST API."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 10):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # ---- Event ----

    def send_event(self, text: str, event_id: str = None, kind: str = "dialog.message",
                   trace_id: str = "") -> APIResponse:
        """Send a user event. Fire-and-forget."""
        import time
        payload = {
            "event_id": event_id or f"cli_{int(time.time() * 1000)}",
            "kind": kind,
            "payload": {"text": text, "source": "api_client"},
            "trace_id": trace_id,
        }
        return self._post("/v4/event", payload)

    # ---- Status ----

    def get_status(self) -> APIResponse:
        """Get runtime engine stats."""
        return self._get("/v4/status")

    # ---- Inspect ----

    def inspect(self, module: str, limit: int = 10, detail: bool = False) -> APIResponse:
        """Inspect cognitive state. Modules: observations, hypotheses, knowledge,
        skills, world, context."""
        params = f"limit={limit}&detail={str(detail).lower()}"
        return self._get(f"/v4/inspect/{module}?{params}")

    def inspect_observations(self, limit: int = 10) -> APIResponse:
        return self.inspect("observations", limit)

    def inspect_hypotheses(self, limit: int = 10) -> APIResponse:
        return self.inspect("hypotheses", limit)

    def inspect_knowledge(self, limit: int = 10) -> APIResponse:
        return self.inspect("knowledge", limit)

    def inspect_skills(self, limit: int = 10) -> APIResponse:
        return self.inspect("skills", limit)

    def inspect_world(self, limit: int = 10) -> APIResponse:
        return self.inspect("world", limit)

    def inspect_context(self) -> APIResponse:
        return self.inspect("context")

    # ---- Checkpoint ----

    def trigger_checkpoint(self) -> APIResponse:
        """Manually trigger Slow Path."""
        return self._post("/v4/checkpoint", {})

    # ---- Health ----

    def health(self) -> APIResponse:
        """Health check."""
        return self._get("/v4/health")

    # ---- Internal ----

    def _get(self, path: str) -> APIResponse:
        try:
            url = self._base_url + path
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode())
                return APIResponse(ok=True, data=data, status_code=resp.status)
        except urllib.error.HTTPError as e:
            return APIResponse(ok=False, error=str(e), status_code=e.code)
        except Exception as e:
            return APIResponse(ok=False, error=str(e))

    def _post(self, path: str, payload: dict) -> APIResponse:
        try:
            url = self._base_url + path
            data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode())
                return APIResponse(ok=True, data=result, status_code=resp.status)
        except urllib.error.HTTPError as e:
            return APIResponse(ok=False, error=str(e), status_code=e.code)
        except Exception as e:
            return APIResponse(ok=False, error=str(e))
