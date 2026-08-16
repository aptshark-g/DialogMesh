# -*- coding: utf-8 -*-
"""SelfIntrospection / SelfRepair 测试（2026-08-16）。"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from core.agent.meta.diagnosis import AsyncDiagnoser
from core.agent.meta.introspection import (
    SystemIntrospector,
    scan_git_history,
    scan_modules,
    scan_tests,
)


class TestSystemIntrospection(unittest.TestCase):
    def test_scan_modules(self):
        mods = scan_modules()
        names = {m["name"] for m in mods}
        # 核心模块应可见
        self.assertTrue({"meta", "execution", "llm", "blueprint"} <= names)
        meta = next(m for m in mods if m["name"] == "meta")
        self.assertIn("meta", meta["path"])

    def test_scan_tests(self):
        t = scan_tests()
        self.assertGreaterEqual(t["test_files"], 10)
        self.assertGreaterEqual(t["test_cases_approx"], 10)
        self.assertIn("by_module", t)

    def test_git_history(self):
        h = scan_git_history(5)
        # 沙箱/CI 下 git 可能不可用 → 容错: 有数据时校验结构
        if h:
            self.assertIn("hash", h[0])
            self.assertIn("subject", h[0])

    def test_profile_snapshot_and_persist(self):
        tmp = os.path.join(tempfile.mkdtemp(prefix="dm_profile_"),
                           "profile.json")
        ins = SystemIntrospector(path=tmp)
        p = ins.build()
        self.assertIn("modules", p)
        self.assertIn("tests", p)
        self.assertIn("git_history", p)
        self.assertIn("weak_spots", p)
        self.assertTrue(os.path.exists(tmp))


class TestSelfRepair(unittest.TestCase):
    def setUp(self):
        self.d = AsyncDiagnoser(min_interval=0.0, llm_enabled=False,
                                auto_attach=False)

    def test_code_fix_queues_repair_pending(self):
        res = self.d._apply_suggestion({
            "action_type": "code_fix", "scope": "tool_loop",
            "params": {"files": ["core/agent/llm/tool_loop.py"],
                       "suggestion": "给 _call_gateway 加熔断前检查",
                       "patch": "--- a/core/agent/llm/tool_loop.py\n"
                                "+++ b/core/agent/llm/tool_loop.py\n",
                       "verify_plan": ["pytest core/agent/llm -q"]},
            "reason": "重复连接失败"})
        self.assertEqual(res["action"], "code_fix")
        rid = res["repair_id"]
        repairs = self.d.repairs()
        self.assertEqual(len(repairs), 1)
        r = repairs[0]
        self.assertEqual(r["status"], "pending")
        self.assertIn("tool_loop.py", r["files"][0])

    def test_apply_requires_gate_and_confirm(self):
        # A21 安全: code_fix 默认 pending, 不 gate 不自动应用
        # （真实应用/回滚由 TestSelfRepairRealApply 在临时 repo 验证）
        res = self.d._apply_suggestion({
            "action_type": "code_fix", "scope": "planning",
            "params": {"patch": "--- a/x\n+++ b/x\n",
                       "verify_plan": ["pytest core/agent/meta -q"]},
            "reason": "planning 失败"})
        rid = res["repair_id"]
        r = self.d.repairs()[0]
        self.assertEqual(r["status"], "pending")
        self.assertIn("patch", r)

    def test_unknown_repair(self):
        out = self.d.apply_repair("fix_nonexistent")
        self.assertIn("error", out)


def _make_git_repo() -> str:
    """临时 git 仓库（自修复真实应用验证用）。"""
    repo = tempfile.mkdtemp(prefix="dm_repair_")
    subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"],
                   cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"],
                   cwd=repo, capture_output=True)
    with open(os.path.join(repo, "bug.py"), "w", encoding="utf-8") as f:
        f.write("def value():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=repo, capture_output=True)
    return repo


class TestSelfRepairRealApply(unittest.TestCase):
    """真实 git apply + 验证 + 回滚（P1）。"""

    def setUp(self):
        self.repo = _make_git_repo()
        self.bug_py = os.path.join(self.repo, "bug.py")
        self.d = AsyncDiagnoser(min_interval=0.0, llm_enabled=False,
                                auto_attach=False)
        self.d._repo_root = self.repo

    def tearDown(self):
        import shutil
        shutil.rmtree(self.repo, ignore_errors=True)

    def _queue(self, patch, verify):
        res = self.d._apply_suggestion({
            "action_type": "code_fix", "scope": "tool_loop",
            "params": {"patch": patch, "verify_plan": verify,
                       "files": ["bug.py"]},
            "reason": "测试修复"})
        return res

    def test_apply_patch_and_verify_passed(self):
        patch = (
            "--- a/bug.py\n+++ b/bug.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def value():\n"
            "-    return 1\n"
            "+    return 2\n")
        verify = ['python -c "import bug; assert bug.value()==2"']
        res = self._queue(patch, verify)
        self.assertEqual(res["action"], "code_fix")
        out = self.d.apply_repair(res["repair_id"])
        self.assertEqual(out["status"], "applied")
        with open(self.bug_py, encoding="utf-8") as f:
            self.assertIn("return 2", f.read())
        self.assertEqual(self.d.repairs()[0]["status"], "applied")
        # 凝练回写经验库（伪二阶抽象: 教训而非补丁）
        from core.agent.meta.experience import get_experience_store
        exp = get_experience_store()
        self.assertGreaterEqual(exp.stats()["total"], 1)
        recent = exp.stats()["recent"][-1]
        self.assertIn("design_lesson", recent)

    def test_apply_fail_rolls_back(self):
        patch = (
            "--- a/bug.py\n+++ b/bug.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def value():\n"
            "-    return 1\n"
            "+    return 2\n")
        # 验证断言旧值 1 → 应用后为 2 → 验证失败 → 自动回滚
        verify = ['python -c "import bug; assert bug.value()==1"']
        res = self._queue(patch, verify)
        out = self.d.apply_repair(res["repair_id"])
        self.assertEqual(out["status"], "failed")
        self.assertTrue(out["rollback"])
        with open(self.bug_py, encoding="utf-8") as f:
            self.assertIn("return 1", f.read())  # 已回滚

    def test_bad_patch_rejected(self):
        res = self._queue("not a valid diff",
                          ['python -c "import bug"'])
        self.assertEqual(res["action"], "code_fix")
        out = self.d.apply_repair(res["repair_id"])
        self.assertIn("error", out)
        self.assertEqual(self.d.repairs()[0]["status"], "pending")

    def test_missing_patch_rejected(self):
        res = self.d._apply_suggestion({
            "action_type": "code_fix", "scope": "tool_loop",
            "params": {"verify_plan": ["pytest -q"]},
            "reason": "无 patch"})
        self.assertIn("error", res)
        self.assertEqual(self.d.repairs(), [])

    def test_verify_allowlist_blocks_arbitrary_command(self):
        res = self.d._apply_suggestion({
            "action_type": "code_fix", "scope": "tool_loop",
            "params": {"patch": "--- a/bug.py\n+++ b/bug.py\n",
                       "verify_plan": ["rm -rf /tmp/x"]},
            "reason": "恶意验证命令"})
        self.assertIn("error", res)
        self.assertIn("not allowed", res["error"])


if __name__ == "__main__":
    unittest.main()
