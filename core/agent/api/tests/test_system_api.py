"""后台进程端点（2026-08-17, 工程链副屏「后台进程」）。"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from fastapi.testclient import TestClient

from core.agent.api import system_api


def test_read_processes_shape():
    data = system_api.read_processes()
    assert isinstance(data["threads"], list)
    assert data["count"] == len(data["threads"])
    assert isinstance(data["memory"], dict)
    for t in data["threads"]:
        assert "name" in t and "alive" in t and "daemon" in t


def test_processes_endpoint():
    from core.agent.api.v6_app import app
    client = TestClient(app, headers={
        "X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})
    r = client.get("/v6/system/processes")
    assert r.status_code == 200
    data = r.json()
    assert "threads" in data and data["count"] > 0
