"""B15/B1/B16 — 项目 CRUD + 会话归属（2026-08-17）。

验证: 项目建/改/删/持久化; 会话归属写（set/clear/不存在项目拒绝）;
删除项目自动清除归属; /v6/projects + /v6/sessions/{id}/project 端点;
POST /v3/session 携带 project_id（B16）。
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from fastapi.testclient import TestClient  # noqa: E402

from core.agent.api import projects_api  # noqa: E402


@pytest.fixture(autouse=True)
def iso_store(monkeypatch, tmp_path):
    """隔离存储: 每个测试独立 projects.json + 清缓存。"""
    p = tmp_path / "projects.json"
    monkeypatch.setattr(projects_api, "_PROJECTS_FILE", str(p))
    monkeypatch.setattr(projects_api, "_PROJECTS_CACHE", None)
    yield


@pytest.fixture()
def client():
    from core.agent.api.v6_app import app
    return TestClient(app, headers={
        "X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})


class TestProjectCrud:
    def test_create_update_delete(self):
        p = projects_api.create_project("认知组", "#F59E0B")
        assert p["name"] == "认知组"
        assert p["color"] == "#F59E0B"
        assert p["id"]
        updated = projects_api.update_project(p["id"], name="认知引擎")
        assert updated["name"] == "认知引擎"
        assert projects_api.delete_project(p["id"])
        assert not projects_api.delete_project(p["id"])

    def test_create_with_path_and_create_dir(self, tmp_path):
        target = tmp_path / "ws" / "p1"
        p = projects_api.create_project("带目录", path=str(target),
                                        create_dir=True)
        assert p["path"] == str(target)
        assert target.is_dir()

    def test_update_path(self):
        p = projects_api.create_project("P")
        updated = projects_api.update_project(p["id"], path="data/projects/x")
        assert updated["path"] == "data/projects/x"
        # path=None 清除
        updated2 = projects_api.update_project(p["id"], path=None)
        assert "path" not in updated2 or updated2["path"] is None

    def test_browse_readonly_lists_dirs(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a" / "nested").mkdir()
        (tmp_path / "file.txt").write_text("x", encoding="utf-8")
        result = projects_api._browse_dirs(str(tmp_path))
        names = [e["name"] for e in result["entries"]]
        assert "a" in names and "b" in names
        assert "file.txt" not in names
        assert "nested" not in names  # 只列直接子目录

    def test_browse_missing_returns_empty(self, tmp_path):
        result = projects_api._browse_dirs(str(tmp_path / "missing"))
        assert result["entries"] == []

    def test_update_missing_returns_none(self):
        assert projects_api.update_project("nope", name="x") is None

    def test_persist_across_reload(self, monkeypatch):
        p = projects_api.create_project("持久化")
        monkeypatch.setattr(projects_api, "_PROJECTS_CACHE", None)
        data = projects_api._load()
        assert any(x["id"] == p["id"] for x in data["projects"])


class TestSessionProject:
    def test_set_and_clear(self):
        p = projects_api.create_project("P")
        assert projects_api.set_session_project("s1", p["id"])
        assert projects_api.session_project_map()["s1"] == p["id"]
        assert projects_api.set_session_project("s1", None)
        assert "s1" not in projects_api.session_project_map()

    def test_reject_missing_project(self):
        assert not projects_api.set_session_project("s2", "nonexist")
        assert "s2" not in projects_api.session_project_map()


class TestProjectDesign:
    def test_get_default_empty(self):
        p = projects_api.create_project("设计组")
        d = projects_api.get_project_design(p["id"])
        assert d["philosophy"] == ""
        assert d["axioms"] == [] and d["goals"] == []

    def test_save_manual(self):
        p = projects_api.create_project("设计组")
        saved = projects_api.save_project_design(
            p["id"],
            philosophy="约束长出来, 不是写出来",
            axioms=["产出可逆推回设计意图"],
            goals=["沉淀可复用公理"],
            source="manual")
        assert saved["philosophy"] == "约束长出来, 不是写出来"
        assert saved["axioms"] == ["产出可逆推回设计意图"]
        assert saved["updated_at"] > 0
        # 读取一致
        again = projects_api.get_project_design(p["id"])
        assert again["philosophy"] == saved["philosophy"]

    def test_digest_template_fallback(self, monkeypatch):
        """LLM 失败 → 模板兜底, 且写回项目。"""
        monkeypatch.setattr(projects_api, "_llm_design",
                            lambda *a, **k: None)
        monkeypatch.setattr(projects_api, "_collect_project_sessions",
                            lambda *a, **k: [{"name": "s1", "sample": "x"}])
        p = projects_api.create_project("凝练组")
        d = projects_api.digest_project_design(p["id"], use_llm=True)
        assert d["philosophy"]
        assert d["axioms"] and d["goals"]
        assert d["source"] == "template"

    def test_design_missing_project(self):
        assert projects_api.get_project_design("nope") is None
        assert projects_api.digest_project_design("nope") is None

    def test_delete_project_clears_assignments(self):
        p = projects_api.create_project("P")
        projects_api.set_session_project("s1", p["id"])
        projects_api.set_session_project("s2", p["id"])
        assert projects_api.delete_project(p["id"])
        sp = projects_api.session_project_map()
        assert "s1" not in sp and "s2" not in sp


class TestEndpoints:
    def test_projects_crud_endpoints(self, client):
        r = client.post("/v6/projects", json={"name": "API项目"})
        assert r.status_code == 200
        pid = r.json()["id"]

        r = client.get("/v6/projects")
        assert r.status_code == 200
        body = r.json()
        assert any(x["id"] == pid for x in body["projects"])
        assert body["session_project"] == {}

        r = client.put(f"/v6/sessions/sess1/project",
                       json={"project_id": pid})
        assert r.status_code == 200
        r = client.get("/v6/projects")
        assert r.json()["session_project"]["sess1"] == pid

        r = client.patch(f"/v6/projects/{pid}", json={"name": "改名"})
        assert r.status_code == 200 and r.json()["name"] == "改名"

        r = client.delete(f"/v6/projects/{pid}")
        assert r.status_code == 200
        r = client.get("/v6/projects")
        assert r.json()["session_project"] == {}

    def test_put_project_missing_404(self, client):
        r = client.put("/v6/sessions/s1/project",
                       json={"project_id": "nonexist"})
        assert r.status_code == 404

    def test_create_session_with_project(self, client):
        p = client.post("/v6/projects", json={"name": "会话项目"})
        pid = p.json()["id"]
        r = client.post("/v3/session", json={"project_id": pid})
        assert r.status_code == 200
        sid = r.json()["session_id"]
        sp = client.get("/v6/projects").json()["session_project"]
        assert sp.get(sid) == pid
