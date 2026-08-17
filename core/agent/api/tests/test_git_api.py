"""Git 只读状态端点（2026-08-17, 环境信息面板）。

验证: /v6/git/status 返回分支/远端/提交/变更计数等只读字段;
所有字段在仓库内可解析, 不触发任何写操作。
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from fastapi.testclient import TestClient

from core.agent.api import git_api


def test_git_status_shape():
    r = git_api._git("rev-parse", "--is-inside-work-tree")
    assert r == "true"  # 本仓库
    data = git_api.read_git_status()
    assert isinstance(data["branch"], str) and data["branch"]
    assert isinstance(data["staged"], int)
    assert isinstance(data["unstaged"], int)
    assert isinstance(data["untracked"], int)
    assert isinstance(data["ahead"], int) and isinstance(data["behind"], int)
    assert isinstance(data["changed_files"], list)
    assert isinstance(data["dirty"], bool)
    assert "last_commit" in data
    # 2026-08-18: Codex 式变更统计 + 分支列表
    assert isinstance(data["additions"], int) and data["additions"] >= 0
    assert isinstance(data["deletions"], int) and data["deletions"] >= 0
    assert isinstance(data["branches"], list)
    assert any(b["current"] for b in data["branches"])


def test_git_status_endpoint():
    from core.agent.api.v6_app import app
    client = TestClient(app, headers={
        "X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})
    r = client.get("/v6/git/status")
    assert r.status_code == 200
    data = r.json()
    assert data["branch"]
    assert "changed_files" in data


def _make_temp_repo(tmp_path):
    """建临时 git 仓库（独立, 不碰生产仓库）。"""
    import subprocess

    def run(*args, cwd):
        return subprocess.run(args, cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8",
                              errors="replace")

    repo = tmp_path / "repo"
    repo.mkdir()
    run("git", "init", cwd=str(repo))
    run("git", "config", "user.email", "t@t", cwd=str(repo))
    run("git", "config", "user.name", "t", cwd=str(repo))
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    run("git", "add", ".", cwd=str(repo))
    run("git", "commit", "-q", "-m", "init", cwd=str(repo))
    run("git", "branch", "b1", cwd=str(repo))
    return str(repo)


def test_git_switch_commit_against_temp_repo(monkeypatch, tmp_path):
    import uuid
    repo = _make_temp_repo(tmp_path)
    monkeypatch.setattr(git_api, "PROJECT_ROOT", repo)

    from core.agent.api.v6_app import app
    client = TestClient(app, headers={
        "X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})

    # 切到 b1
    r = client.post("/v6/git/branch", json={"name": "b1"})
    assert r.status_code == 200, r.text
    # 切不存在分支 → 409
    r = client.post("/v6/git/branch", json={"name": "nope"})
    assert r.status_code == 409

    # 修改 + 提交
    import pathlib
    pathlib.Path(repo, "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    r = client.post("/v6/git/commit", json={"message": "test commit"})
    assert r.status_code == 200, r.text
    log = git_api._git("log", "-1", "--format=%s")
    assert log == "test commit"

    # 无远端 → push 明确 400
    r = client.post("/v6/git/push")
    assert r.status_code == 400
    assert "远端" in r.json()["detail"]
