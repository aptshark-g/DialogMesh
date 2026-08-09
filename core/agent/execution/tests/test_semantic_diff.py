"""SD-3: SemanticDiff independent tests — AST diff + constraint + sandbox wiring.

Covers:
  1. SemanticDiffer.diff — change classification (new/deleted/signature/body/
     docstring/import) + security detection.
  2. SemanticConstraint.evaluate — allow/block/require_approval + security.
  3. FileSandbox.review — AST-level constraint effective in the real write path.
"""
import os
import tempfile

from core.agent.execution.sandbox import FileSandbox
from core.agent.execution.semantic_diff import (
    ASTChange,
    ChangeClass,
    RiskLevel,
    SemanticConstraint,
    SemanticDiffer,
)


class TestSemanticDiffer:
    def setup_method(self):
        self.differ = SemanticDiffer()

    def test_new_function(self):
        old = "def existing():\n    return 1\n"
        new = "def existing():\n    return 1\n\ndef added():\n    return 2\n"
        changes = self.differ.diff(old, new, "app.py")
        classes = {c.change_class for c in changes}
        assert ChangeClass.NEW_FUNCTION in classes
        new_fn = next(c for c in changes
                      if c.change_class == ChangeClass.NEW_FUNCTION)
        assert new_fn.entity_name == "added"
        assert new_fn.risk in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_deleted_function_is_critical(self):
        old = "def gone():\n    return 1\n\ndef keep():\n    return 2\n"
        new = "def keep():\n    return 2\n"
        changes = self.differ.diff(old, new, "app.py")
        deleted = [c for c in changes if c.change_class == ChangeClass.DELETED_FUNCTION]
        assert deleted and deleted[0].risk == RiskLevel.CRITICAL
        assert deleted[0].entity_name == "gone"

    def test_signature_change(self):
        old = "def f(a, b):\n    return a + b\n"
        new = "def f(a, b, c=0):\n    return a + b + c\n"
        changes = self.differ.diff(old, new, "app.py")
        sig = [c for c in changes if c.change_class == ChangeClass.SIGNATURE_CHANGE]
        assert sig and sig[0].risk == RiskLevel.HIGH

    def test_docstring_only_is_low(self):
        old = 'def f():\n    """old doc."""\n    return 1\n'
        new = 'def f():\n    """new doc."""\n    return 1\n'
        changes = self.differ.diff(old, new, "app.py")
        doc = [c for c in changes if c.change_class == ChangeClass.DOCSTRING_ONLY]
        assert doc and doc[0].risk == RiskLevel.LOW

    def test_import_change_with_dangerous_import(self):
        old = "import os\n"
        new = "import os\nimport subprocess\n"
        changes = self.differ.diff(old, new, "app.py")
        imp = [c for c in changes if c.change_class == ChangeClass.IMPORT_CHANGE]
        assert imp
        assert any("subprocess" in s for s in imp[0].security_concerns)

    def test_sql_in_new_function_is_critical(self):
        old = "def existing():\n    return 1\n"
        new = (
            "def existing():\n    return 1\n\n"
            "def query(user):\n"
            '    return execute(f"SELECT * FROM t WHERE u={user}")\n'
        )
        changes = self.differ.diff(old, new, "app.py")
        new_fn = [c for c in changes if c.change_class == ChangeClass.NEW_FUNCTION
                  and c.entity_name == "query"]
        assert new_fn and new_fn[0].risk == RiskLevel.CRITICAL
        assert new_fn[0].security_concerns

    def test_no_change_is_comment_only_safe(self):
        changes = self.differ.diff("a = 1\n", "a = 1\n", "app.py")
        assert changes[0].change_class == ChangeClass.COMMENT_ONLY
        assert changes[0].risk == RiskLevel.SAFE

    def test_parse_error_degrades(self):
        changes = self.differ.diff("def broken(:\n", "def fixed():\n    pass\n", "app.py")
        assert changes[0].change_class == ChangeClass.FORMATTING


class TestSemanticConstraint:
    def setup_method(self):
        self.constraint = SemanticConstraint()

    def _change(self, cls, name="f", risk=RiskLevel.MEDIUM):
        return ASTChange(cls, name, "app.py:1", risk)

    def test_new_function_allowed(self):
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.NEW_FUNCTION))
        assert allowed and action == "allow"

    def test_deleted_function_blocked(self):
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.DELETED_FUNCTION))
        assert not allowed and action == "block"

    def test_signature_requires_approval(self):
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.SIGNATURE_CHANGE))
        assert not allowed and action == "require_approval"

    def test_security_always_blocks(self):
        allowed, action, reason = self.constraint.evaluate(
            ASTChange(ChangeClass.BODY_CHANGE, "f", "app.py:1", RiskLevel.MEDIUM,
                      security_concerns=["possible SQL injection"]))
        assert not allowed and action == "block"
        assert "SQL" in reason

    def test_blocked_entity(self):
        self.constraint.block("login")
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.BODY_CHANGE, "login"))
        assert not allowed and action == "block"

    def test_protected_entity(self):
        self.constraint.protect("get_profile")
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.NEW_FUNCTION, "get_profile"))
        assert not allowed and action == "require_approval"

    def test_custom_policy(self):
        self.constraint.set_policy(ChangeClass.NEW_FUNCTION, "block")
        allowed, action, _ = self.constraint.evaluate(
            self._change(ChangeClass.NEW_FUNCTION))
        assert not allowed and action == "block"


class TestFileSandboxSemanticWiring:
    """SD-1: FileSandbox.review enforces AST-level constraints."""

    def _sandbox_with_file(self, filename, content):
        ws = tempfile.mkdtemp()
        path = os.path.join(ws, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        sb = FileSandbox(ws)
        sb.snapshot()
        return ws, sb

    def test_delete_function_blocked_by_review(self):
        ws, sb = self._sandbox_with_file(
            "app.py",
            "def login(token):\n    return token\n\ndef keep():\n    return 1\n",
        )
        sb.write("app.py", "def keep():\n    return 1\n")
        sb.diff()
        approved, violations = sb.review()
        assert not approved
        assert any("deleted_function" in v for v in violations)

    def test_sql_new_function_blocked_by_review(self):
        ws, sb = self._sandbox_with_file(
            "app.py",
            "def existing():\n    return 1\n",
        )
        sb.write(
            "app.py",
            "def existing():\n    return 1\n\n"
            "def query(user):\n"
            '    return execute(f"SELECT * FROM t WHERE u={user}")\n',
        )
        sb.diff()
        approved, violations = sb.review()
        assert not approved
        assert any("SQL" in v or "semantic[block]" in v for v in violations)

    def test_safe_new_function_passes_review(self):
        ws, sb = self._sandbox_with_file(
            "app.py",
            "def existing():\n    return 1\n",
        )
        sb.write(
            "app.py",
            "def existing():\n    return 1\n\ndef helper():\n    return 42\n",
        )
        sb.diff()
        approved, violations = sb.review()
        assert approved, violations

    def test_non_python_file_not_semantically_checked(self):
        ws, sb = self._sandbox_with_file("notes.txt", "hello\n")
        sb.write("notes.txt", "hello world\n")
        sb.diff()
        approved, violations = sb.review()
        assert approved, violations
