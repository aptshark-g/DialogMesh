"""Viz edit versioning (B1) — 图谱编辑内存态版本 + 409 冲突检测。

同型推广自 task_graph 版本化（TASK_GRAPH_VERSIONING_IMPL）:
  - /v6/edit/* 共享 engine._viz_version
  - 请求带 version 且落后 → 409 version_conflict
  - GET /v6/graph 等返回 version（kernel dispatch）
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.agent.api import api_viz_edit
from core.agent.kernel import dispatch as kernel_dispatch


class FakeEdge:
    def __init__(self, target, influence_weight):
        self.target = target
        self.influence_weight = influence_weight


class FakeIG:
    def __init__(self):
        self._adjacency = {}

    def add_edge(self, source, target, _typ, weight):
        self._adjacency.setdefault(source, []).append(FakeEdge(target, weight))

    def get_node_state(self, _nid):
        return None

    def set_node_state(self, _nid, _state):
        pass


class FakeBlock:
    temperature = "active"
    topic = "old"
    parent = "root"


class FakeTree:
    def __init__(self):
        self.blocks = {"b1": FakeBlock()}


class FakeDT:
    def __init__(self):
        self._trees = {"t1": FakeTree()}


class FakeEngine:
    def __init__(self):
        self._interaction_graph = FakeIG()
        self._init_whitebox = lambda: None
        self._correction_journal = None
        self._behavior_graph = None
        self._turn_counter = 0
        self._world_objects = {}
        self._discourse_tree = FakeDT()
        self._world_provider = None
        self._relation_substrate = None
        self._last_context = None


@pytest.fixture()
def viz_client(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(api_viz_edit, "_engine", fake)
    app = FastAPI()
    app.include_router(api_viz_edit.router)
    return TestClient(app), fake


def _edit_graph(client, weight=0.9, version=None):
    body = {"action": "update_weight", "source": "a", "target": "b", "weight": weight}
    if version is not None:
        body["version"] = version
    return client.put("/v6/edit/graph", json=body)


def test_edit_without_version_forces(viz_client):
    client, eng = viz_client
    r = _edit_graph(client)
    assert r.status_code == 200
    assert eng._viz_version == 1


def test_edit_with_version_increments(viz_client):
    client, eng = viz_client
    assert _edit_graph(client, version=0).status_code == 200
    assert eng._viz_version == 1
    assert _edit_graph(client, weight=0.5, version=1).status_code == 200
    assert eng._viz_version == 2


def test_edit_stale_version_returns_409(viz_client):
    client, eng = viz_client
    assert _edit_graph(client, version=0).status_code == 200
    assert _edit_graph(client, weight=0.5, version=1).status_code == 200
    r = _edit_graph(client, weight=0.1, version=1)  # stale: current is 2
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "version_conflict"
    assert detail["current_version"] == 2
    assert eng._viz_version == 2  # conflict does not bump


def test_shared_version_across_endpoints(viz_client):
    client, eng = viz_client
    assert _edit_graph(client, version=0).status_code == 200
    assert eng._viz_version == 1
    r = client.put("/v6/edit/discourse-tree", json={
        "action": "rename", "block_id": "b1", "topic": "new", "version": 1,
    })
    assert r.status_code == 200
    assert eng._viz_version == 2


def test_kernel_graph_returns_version(monkeypatch):
    monkeypatch.setattr(kernel_dispatch, "get_engine", lambda: None)
    data = kernel_dispatch.kernel_graph()
    assert "version" in data
    assert data["version"] == 0
