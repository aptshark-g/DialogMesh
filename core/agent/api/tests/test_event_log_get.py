# -*- coding: utf-8 -*-
"""EventLog.get_event 直查测试（情景溯源, 2026-08-09）。"""
import json

from core.agent.api.api_event_log import EventLog


def test_get_event_direct_lookup(tmp_path):
    el = EventLog(str(tmp_path / "evt.db"))
    el.open()
    el.put_event(event_id="m1", kind="user_message",
                 payload={"text": "写文稿"}, trace_id="m1")
    row = el.get_event("m1")
    assert row is not None
    assert row["event_id"] == "m1"
    assert row["kind"] == "user_message"
    assert row["trace_id"] == "m1"
    assert row["payload"].get("text") == "写文稿"


def test_get_event_missing_returns_none(tmp_path):
    el = EventLog(str(tmp_path / "evt2.db"))
    el.open()
    assert el.get_event("nope") is None
