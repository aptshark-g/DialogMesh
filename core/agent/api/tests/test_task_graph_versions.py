"""Task graph workspace versioning — memory state + 409 conflict detection.

Verifies the stage-B P0 contract (状态生命周期: 内存态=热/落盘=温/版本冲突):
  - GET returns version
  - PUT without version = force overwrite (backward compatible)
  - PUT with stale version = 409 + current version
  - LLM seed never overwrites user-confirmed version
  - restart (memory cleared) falls back to disk with version
"""

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.agent.api import v3_session_api


@pytest.fixture()
def tg_client(tmp_path, monkeypatch):
    """Isolated client: temp task_graphs dir + clean workspace."""
    monkeypatch.setattr(v3_session_api, "TASK_GRAPHS_DIR", str(tmp_path / "task_graphs"))
    monkeypatch.setattr(v3_session_api, "DATA_DIR", str(tmp_path))
    with v3_session_api._TASK_GRAPHS_LOCK:
        v3_session_api._TASK_GRAPH_WORKSPACES.clear()
    app = FastAPI()
    app.include_router(v3_session_api.router)
    return TestClient(app)


def _put(client, sid, nodes, edges, version=None):
    body = {"nodes": nodes, "edges": edges}
    if version is not None:
        body["version"] = version
    return client.put(f"/v3/session/{sid}/task-graph", json=body)


def test_get_empty_returns_version_zero(tg_client):
    r = tg_client.get("/v3/session/s1/task-graph")
    assert r.status_code == 200
    data = r.json()
    assert data == {"nodes": [], "edges": [], "version": 0}


def test_put_without_version_forces_overwrite(tg_client):
    r = _put(tg_client, "s1", [{"id": "a"}], [])
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == 1


def test_put_with_version_increments(tg_client):
    assert _put(tg_client, "s1", [{"id": "a"}], [], version=0).json()["version"] == 1
    assert _put(tg_client, "s1", [{"id": "b"}], [], version=1).json()["version"] == 2
    r = tg_client.get("/v3/session/s1/task-graph")
    assert r.json()["version"] == 2
    assert r.json()["nodes"] == [{"id": "b"}]


def test_put_stale_version_returns_409(tg_client):
    assert _put(tg_client, "s1", [{"id": "a"}], [], version=0).json()["version"] == 1
    assert _put(tg_client, "s1", [{"id": "b"}], [], version=1).json()["version"] == 2
    r = _put(tg_client, "s1", [{"id": "stale"}], [], version=1)  # stale: current is 2
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "version_conflict"
    assert detail["current_version"] == 2
    # server copy untouched
    got = tg_client.get("/v3/session/s1/task-graph").json()
    assert got["version"] == 2
    assert got["nodes"] == [{"id": "b"}]


def test_seed_never_overwrites_user_version(tg_client):
    _put(tg_client, "s1", [{"id": "user"}], [], version=0)
    seeded = v3_session_api._seed_task_graph("s1", [{"id": "llm"}])
    assert seeded is False
    got = tg_client.get("/v3/session/s1/task-graph").json()
    assert got["nodes"] == [{"id": "user"}]
    assert got["version"] == 1


def test_seed_writes_when_no_user_version(tg_client):
    seeded = v3_session_api._seed_task_graph("s1", [{"id": "llm"}])
    assert seeded is True
    got = tg_client.get("/v3/session/s1/task-graph").json()
    assert got["nodes"] == [{"id": "llm"}]
    assert got["version"] == 1


def test_restart_falls_back_to_disk_with_version(tg_client, tmp_path):
    _put(tg_client, "s1", [{"id": "a"}], [], version=0)
    # simulate process restart: clear memory, disk keeps version
    with v3_session_api._TASK_GRAPHS_LOCK:
        v3_session_api._TASK_GRAPH_WORKSPACES.clear()
    r = tg_client.get("/v3/session/s1/task-graph")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert data["nodes"] == [{"id": "a"}]


def test_disk_file_contains_version(tg_client):
    v3_session_api._seed_task_graph("sx", [{"id": "n"}])
    path = os.path.join(v3_session_api.TASK_GRAPHS_DIR, "sx.json")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == 1
    assert data["nodes"] == [{"id": "n"}]
