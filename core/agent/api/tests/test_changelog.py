"""GAP-F1 变更日志视图测试 — 决策事件流（git log）+ PR review 介入。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.agent.api import stubs_api
from core.agent.blueprint.decision_event import DecisionEventBus


class _Eng:
    def __init__(self):
        self._decision_bus = DecisionEventBus()


@pytest.fixture()
def client(monkeypatch):
    engine = _Eng()
    monkeypatch.setattr(
        "core.agent.kernel.dispatch.get_engine", lambda: engine)
    app = FastAPI()
    app.include_router(stubs_api.router)
    return TestClient(app)


def test_changelog_empty(client):
    r = client.get("/v6/changelog")
    assert r.status_code == 200
    data = r.json()
    assert data["events"] == []
    assert data["stats"]["total"] == 0


def test_changelog_events_and_stats(client):
    from core.agent.kernel.dispatch import get_engine
    bus = get_engine()._decision_bus
    bus.log(kind="strategy_switch", dimension="plan.node.n1",
            before="n1", after="n2", reason="RECOVERY", status="proposed")
    bus.log(kind="user_correction", dimension="plan.node.n1",
            before="n2", after="n1", reason="user edit", status="applied")
    r = client.get("/v6/changelog?limit=50")
    data = r.json()
    assert data["stats"]["total"] == 2
    assert data["stats"]["proposed"] == 1
    assert data["stats"]["applied"] == 1
    kinds = {e["kind"] for e in data["events"]}
    assert "strategy_switch" in kinds and "user_correction" in kinds


def test_changelog_filter_by_kind(client):
    from core.agent.kernel.dispatch import get_engine
    bus = get_engine()._decision_bus
    bus.log(kind="strategy_switch", dimension="d1", reason="x", status="proposed")
    bus.log(kind="meta_advice", dimension="d2", reason="y", status="proposed")
    r = client.get("/v6/changelog?kind=strategy_switch")
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["kind"] == "strategy_switch"


def test_intervene_approve_reject(client):
    from core.agent.kernel.dispatch import get_engine
    bus = get_engine()._decision_bus
    bus.log(kind="strategy_switch", dimension="plan.node.n1",
            before="a", after="b", reason="switch", status="proposed")
    r = client.post("/v6/changelog/intervene", json={
        "status": "applied", "comment": "同意", "dimension": "plan.node.n1",
    })
    assert r.json()["intervened"] is True
    events = bus.recent()
    assert events[0]["status"] == "applied"
    assert events[0]["comment"] == "同意"
    # 再 reject 一个新的 proposed 事件
    bus.log(kind="strategy_switch", dimension="plan.node.n2",
            before="c", after="d", reason="switch2", status="proposed")
    r2 = client.post("/v6/changelog/intervene", json={
        "status": "rejected", "comment": "不同意", "dimension": "plan.node.n2",
    })
    assert r2.json()["intervened"] is True
    # intervene 会追加 user_correction 评论事件 — 按 dimension 定位原事件
    ev = next(e for e in bus.recent() if e.get("dimension") == "plan.node.n2")
    assert ev["status"] == "rejected"
    assert ev["comment"] == "不同意"
