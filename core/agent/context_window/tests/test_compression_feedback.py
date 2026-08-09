"""GAP-4 压缩反馈闭环测试（Hermes manual_compression_feedback 对齐）."""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.agent.context_window.compression_feedback import CompressionFeedbackStore
from core.agent.context_window.window_manager import WindowManager, WindowConfig
from core.agent.context_window.models import WindowTurn
from core.agent.api import stubs_api


@pytest.fixture()
def store(tmp_path):
    return CompressionFeedbackStore(str(tmp_path / "feedback.json"))


def test_record_good_bad(store):
    item = store.record("good", "摘要保留了要点")
    assert item is not None
    assert item["quality"] == "good"
    bad = store.record("bad", "丢了关键实体", compression_id="c1")
    assert bad["compression_id"] == "c1"
    st = store.stats()
    assert st["total"] == 2
    assert st["good"] == 1
    assert st["bad"] == 1
    assert st["good_rate"] == 0.5


def test_record_invalid_quality_rejected(store):
    assert store.record("meh") is None
    assert store.stats()["total"] == 0


def test_persist_reload(tmp_path):
    path = tmp_path / "feedback.json"
    s1 = CompressionFeedbackStore(str(path))
    s1.record("bad", "压缩过度")
    s2 = CompressionFeedbackStore(str(path))
    assert s2.stats()["total"] == 1
    assert s2.stats()["bad"] == 1


def test_window_manager_compression_log(tmp_path, monkeypatch):
    monkeypatch.setattr(WindowConfig, "hot_size", 1)
    monkeypatch.setattr(WindowConfig, "warm_size", 2)
    wm = WindowManager(WindowConfig(hot_size=1, warm_size=2, cold_size=4))
    for i in range(5):
        wm.add_turn(WindowTurn(sequence=i, content=f"轮次 {i} 内容", role="user",
                               intent_category="test"))
    # 温窗口溢出触发 promote → 压缩日志应有记录
    assert len(wm.compression_log) >= 1
    entry = wm.compression_log[-1]
    assert entry["id"].startswith("c")
    # MEDIUM 压缩可能只加标签不删内容（RuleBasedCompressor 既有行为）—
    # 日志记录 before/after 供反馈关联, 不要求必然减少
    assert "before_tokens" in entry
    assert "after_tokens" in entry
    assert "saved_tokens" in entry
    assert wm.get_window_summary()["recent_compressions"]


def test_api_feedback_endpoint(tmp_path, monkeypatch):
    from core.agent.context_window import compression_feedback as cf_mod

    class _FakeStore(CompressionFeedbackStore):
        def __init__(self):
            super().__init__(str(tmp_path / "fb.json"))

    monkeypatch.setattr(cf_mod, "CompressionFeedbackStore", _FakeStore)
    app = FastAPI()
    app.include_router(stubs_api.router)
    client = TestClient(app)
    r = client.post("/v6/context/compression-feedback",
                    json={"quality": "good", "comment": "不错", "compression_id": "c1"})
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is True
    assert body["stats"]["total"] == 1
    r2 = client.post("/v6/context/compression-feedback",
                     json={"quality": "meh"})
    assert r2.json()["recorded"] is False
    r3 = client.get("/v6/context/compression-feedback/stats")
    assert r3.json()["stats"]["good"] == 1
