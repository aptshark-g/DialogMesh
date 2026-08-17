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


def test_git_status_endpoint():
    from core.agent.api.v6_app import app
    client = TestClient(app, headers={
        "X-Session-Id": f"test-{uuid.uuid4().hex[:12]}"})
    r = client.get("/v6/git/status")
    assert r.status_code == 200
    data = r.json()
    assert data["branch"]
    assert "changed_files" in data
