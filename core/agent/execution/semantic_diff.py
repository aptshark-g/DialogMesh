"""Semantic Diff — AST-level code change detection + semantic ConstraintTree.

Patterns adapted:
  Tree-sitter:   parse → AST → classify node types → detect changes
  Semantic Diff:  not "file X modified" but "function Y signature changed"

Our ConstraintTree upgrade:
  Before:  path-level — "auth.py can be edited, /etc/hosts blocked"
  After:   AST-level — "auth.py: new function OK, delete function BLOCKED,
                        signature change NEEDS_APPROVAL, docstring OK ALWAYS"

Built on Python's `ast` module (no external dependency).
Language-agnostic interface for future tree-sitter integration.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import ast
import logging
import re

logger = logging.getLogger(__name__)


# ═══ Change Types (AST-level) ═══

class ChangeClass(Enum):
    """Classification of what changed in the code."""
    NEW_FUNCTION = "new_function"         # New function/method added
    DELETED_FUNCTION = "deleted_function" # Function removed
    SIGNATURE_CHANGE = "signature_change"  # Function params/return type changed
    BODY_CHANGE = "body_change"           # Function body modified
    DOCSTRING_ONLY = "docstring_only"     # Only docstring changed
    IMPORT_CHANGE = "import_change"       # Import statements modified
    CLASS_CHANGE = "class_change"         # Class added/removed/modified
    VARIABLE_CHANGE = "variable_change"   # Global/class variable changed
    DECORATOR_CHANGE = "decorator_change" # Decorator added/changed
    COMMENT_ONLY = "comment_only"         # Only comments changed
    FORMATTING = "formatting"             # Whitespace/formatting only


class RiskLevel(Enum):
    """Security/quality risk of a change."""
    SAFE = "safe"               # Always allowed (comments, formatting)
    LOW = "low"                 # Low risk (docstring, new variable)
    MEDIUM = "medium"           # Medium risk (body change, import change)
    HIGH = "high"               # High risk (signature, new function)
    CRITICAL = "critical"       # Security-critical (auth logic, SQL, delete function)


@dataclass
class ASTChange:
    """One semantic change detected by AST diff."""
    change_class: ChangeClass
    entity_name: str                # Function/class/variable name
    location: str                   # "auth.py:42"
    risk: RiskLevel
    old_snippet: str = ""           # Before change
    new_snippet: str = ""           # After change
    security_concerns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "class": self.change_class.value,
            "entity": self.entity_name,
            "location": self.location,
            "risk": self.risk.value,
            "security": self.security_concerns,
            "snippet": self.new_snippet[:100] if self.new_snippet else "",
        }


# ═══ AST Analyzer ═══

class ASTAnalyzer:
    """Parse Python code → extract semantic structure.

    Language interface (for future tree-sitter support):
      parse(code) → AST tree
      extract_functions(tree) → {name: {params, body, line, returns, decorators}}
      extract_classes(tree) → ...
      extract_imports(tree) → ...
    """

    def parse(self, code: str, filepath: str = "<unknown>") -> "CodeAST":
        """Parse code → CodeAST."""
        try:
            tree = ast.parse(code)
            return CodeAST(tree, code, filepath)
        except SyntaxError as e:
            logger.warning("AST parse failed: %s — %s", filepath, e)
            return CodeAST(None, code, filepath, parse_error=str(e))


@dataclass
class FunctionInfo:
    name: str
    params: str            # "token: str" or ""
    returns: str           # "str" or ""
    body_lines: int
    start_line: int
    end_line: int
    docstring: str = ""
    decorators: List[str] = field(default_factory=list)
    has_yield: bool = False
    has_async: bool = False
    contains_sql: bool = False
    contains_exec: bool = False
    contains_network: bool = False
    raises_exceptions: List[str] = field(default_factory=list)


class CodeAST:
    """Parsed AST representation of a source file."""

    def __init__(self, tree: Optional[ast.AST], code: str, filepath: str,
                 parse_error: str = ""):
        self.tree = tree
        self.code = code
        self.filepath = filepath
        self.parse_error = parse_error

        self.functions: Dict[str, FunctionInfo] = {}
        self.classes: Dict[str, Dict] = {}
        self.imports: List[str] = []
        self.global_variables: Dict[str, str] = {}

        if tree:
            self._extract()

    def _extract(self):
        """Extract semantic information from AST."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                self._extract_function(node)
            elif isinstance(node, ast.ClassDef):
                self._extract_class(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._extract_import(node)

    def _extract_function(self, node: ast.FunctionDef):
        body_text = ast.get_source_segment(self.code, node) or ""
        security = self._detect_security_concerns(body_text)

        fn = FunctionInfo(
            name=node.name,
            params=self._format_args(node.args),
            returns=self._format_returns(node.returns),
            body_lines=len(node.body),
            start_line=node.lineno or 0,
            end_line=node.end_lineno or 0,
            docstring=ast.get_docstring(node) or "",
            decorators=[d.id for d in node.decorator_list
                       if isinstance(d, ast.Name)],
            has_async=False,
            contains_sql=security.get("sql", False),
            contains_exec=security.get("exec", False),
            contains_network=security.get("network", False),
        )
        # Store raw body text for diff comparison
        fn._raw_body = body_text
        self.functions[node.name] = fn

    def _extract_class(self, node: ast.ClassDef):
        methods = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods[item.name] = self._format_args(item.args)
        self.classes[node.name] = {
            "methods": methods,
            "line": node.lineno,
        }

    def _extract_import(self, node):
        if isinstance(node, ast.Import):
            for alias in node.names:
                self.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                self.imports.append(f"{module}.{alias.name}")

    def _format_args(self, args: ast.arguments) -> str:
        parts = []
        for a in args.args:
            annotation = ""
            if a.annotation:
                if isinstance(a.annotation, ast.Name):
                    annotation = f": {a.annotation.id}"
                elif isinstance(a.annotation, ast.Constant):
                    annotation = f": {a.annotation.value}"
            parts.append(f"{a.arg}{annotation}")
        return ", ".join(parts)

    def _format_returns(self, returns) -> str:
        if returns is None:
            return ""
        if isinstance(returns, ast.Name):
            return returns.id
        if isinstance(returns, ast.Constant):
            return str(returns.value)
        return ""

    def _detect_security_concerns(self, body: str) -> Dict[str, bool]:
        concerns = {"sql": False, "exec": False, "network": False}
        body_lower = body.lower()

        # SQL injection patterns
        if re.search(r'(execute|cursor|query).*SELECT.*\{', body, re.IGNORECASE):
            concerns["sql"] = True
        if re.search(r'(execute|cursor|query).*f[\"\\\'].*SELECT', body, re.IGNORECASE):
            concerns["sql"] = True

        # exec/eval
        if re.search(r'\bexec\s*\(', body) or re.search(r'\beval\s*\(', body):
            concerns["exec"] = True

        # Network calls
        if re.search(r'(requests|urllib|socket|http)\.(get|post|connect)', body):
            concerns["network"] = True

        return concerns


# ═══ Semantic Differ ═══

class SemanticDiffer:
    """AST-level diff between two code versions.

    Classifies changes by semantic impact, not text diff.
    Outputs structured change list for ConstraintTree.
    """

    def diff(self, old_code: str, new_code: str,
             filepath: str = "<unknown>") -> List[ASTChange]:
        """Compare two code versions → list of semantic changes."""
        analyzer = ASTAnalyzer()
        old_ast = analyzer.parse(old_code, filepath)
        new_ast = analyzer.parse(new_code, filepath)

        if old_ast.parse_error or new_ast.parse_error:
            return [ASTChange(
                ChangeClass.FORMATTING, "parse_error", filepath,
                RiskLevel.MEDIUM,
                security_concerns=["unparseable code — treating as full body change"]
            )]

        changes = []

        # 1. New functions
        for name, fn in new_ast.functions.items():
            if name not in old_ast.functions:
                risk = self._assess_risk_new_function(fn)
                changes.append(ASTChange(
                    ChangeClass.NEW_FUNCTION, name,
                    f"{filepath}:{fn.start_line}", risk,
                    new_snippet=self._snippet(new_ast, fn),
                    security_concerns=self._security_flags(fn),
                ))

        # 2. Deleted functions
        for name, fn in old_ast.functions.items():
            if name not in new_ast.functions:
                changes.append(ASTChange(
                    ChangeClass.DELETED_FUNCTION, name,
                    f"{filepath}:{fn.start_line}",
                    RiskLevel.CRITICAL,
                    old_snippet=self._snippet(old_ast, fn),
                ))

        # 3. Modified functions
        for name in set(old_ast.functions) & set(new_ast.functions):
            old_fn = old_ast.functions[name]
            new_fn = new_ast.functions[name]
            fn_changes = self._compare_functions(old_fn, new_fn, filepath, old_ast, new_ast)
            changes.extend(fn_changes)

        # 4. Import changes
        old_imports = set(old_ast.imports)
        new_imports = set(new_ast.imports)
        if old_imports != new_imports:
            added = new_imports - old_imports
            removed = old_imports - new_imports
            risks = []
            for imp in added:
                if any(k in imp for k in ['os', 'subprocess', 'socket', 'requests']):
                    risks.append(f"new dangerous import: {imp}")
            changes.append(ASTChange(
                ChangeClass.IMPORT_CHANGE, "imports", filepath,
                RiskLevel.MEDIUM if risks else RiskLevel.LOW,
                old_snippet=str(old_imports),
                new_snippet=str(new_imports),
                security_concerns=risks,
            ))

        return changes or [ASTChange(
            ChangeClass.COMMENT_ONLY, "no_change", filepath, RiskLevel.SAFE
        )]

    def _compare_functions(self, old_fn: FunctionInfo, new_fn: FunctionInfo,
                           filepath: str, old_ast: CodeAST, new_ast: CodeAST
                           ) -> List[ASTChange]:
        changes = []

        # Signature change
        if old_fn.params != new_fn.params or old_fn.returns != new_fn.returns:
            changes.append(ASTChange(
                ChangeClass.SIGNATURE_CHANGE, new_fn.name,
                f"{filepath}:{new_fn.start_line}",
                RiskLevel.HIGH,
                old_snippet=f"{new_fn.name}({old_fn.params}) -> {old_fn.returns}",
                new_snippet=f"{new_fn.name}({new_fn.params}) -> {new_fn.returns}",
            ))

        # Decorator change
        if old_fn.decorators != new_fn.decorators:
            changes.append(ASTChange(
                ChangeClass.DECORATOR_CHANGE, new_fn.name,
                f"{filepath}:{new_fn.start_line}",
                RiskLevel.LOW,
                old_snippet=str(old_fn.decorators),
                new_snippet=str(new_fn.decorators),
            ))

        # Body change
        raw_body_changed = (hasattr(old_fn, '_raw_body') and hasattr(new_fn, '_raw_body') and
                           old_fn._raw_body != new_fn._raw_body)
        if (old_fn.body_lines != new_fn.body_lines or
            old_fn.docstring != new_fn.docstring or raw_body_changed):

            if old_fn.docstring != new_fn.docstring and old_fn.body_lines == new_fn.body_lines:
                # Only docstring changed
                changes.append(ASTChange(
                    ChangeClass.DOCSTRING_ONLY, new_fn.name,
                    f"{filepath}:{new_fn.start_line}",
                    RiskLevel.LOW,
                ))
            else:
                # Body changed
                security = self._security_flags(new_fn)
                risk = RiskLevel.MEDIUM
                if security:
                    risk = RiskLevel.CRITICAL
                elif any(k in new_fn.name.lower() for k in ['auth', 'login', 'admin', 'token', 'password']):
                    risk = RiskLevel.HIGH

                changes.append(ASTChange(
                    ChangeClass.BODY_CHANGE, new_fn.name,
                    f"{filepath}:{new_fn.start_line}",
                    risk,
                    security_concerns=security,
                ))

        return changes

    def _assess_risk_new_function(self, fn: FunctionInfo) -> RiskLevel:
        """Assess risk level of a new function."""
        if fn.contains_sql or fn.contains_exec:
            return RiskLevel.CRITICAL
        if fn.contains_network:
            return RiskLevel.HIGH
        if any(k in fn.name.lower() for k in ['auth', 'login', 'admin']):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    def _security_flags(self, fn: FunctionInfo) -> List[str]:
        flags = []
        if fn.contains_sql:
            flags.append("possible SQL injection")
        if fn.contains_exec:
            flags.append("exec/eval call")
        if fn.contains_network:
            flags.append("network call")
        return flags

    def _snippet(self, ast_obj: CodeAST, fn: FunctionInfo) -> str:
        if not ast_obj.tree:
            return ""
        lines = ast_obj.code.split('\n')
        start = max(0, fn.start_line - 1)
        end = min(len(lines), fn.end_line)
        return '\n'.join(lines[start:end])[:200]


# ═══ Semantic Constraint ═══

class SemanticConstraint:
    """Constraint applied at AST level, not file level.

    Examples:
      "allow new functions, block function deletion"
      "allow body changes, require approval for signature changes"
      "block any change to auth.py::login()"
      "block SQL-injection patterns in any function"
    """

    def __init__(self):
        # Default policy: per change class → action
        self._policy: Dict[ChangeClass, str] = {
            ChangeClass.NEW_FUNCTION: "allow",
            ChangeClass.DELETED_FUNCTION: "block",
            ChangeClass.SIGNATURE_CHANGE: "require_approval",
            ChangeClass.BODY_CHANGE: "allow",
            ChangeClass.DOCSTRING_ONLY: "allow",
            ChangeClass.IMPORT_CHANGE: "require_approval",
            ChangeClass.CLASS_CHANGE: "allow",
            ChangeClass.VARIABLE_CHANGE: "allow",
            ChangeClass.DECORATOR_CHANGE: "allow",
            ChangeClass.COMMENT_ONLY: "allow",
            ChangeClass.FORMATTING: "allow",
        }

        # Critical: any change with security concern → block
        # Protected: specific function/class that always needs approval
        self._protected_entities: Set[str] = set()
        self._blocked_entities: Set[str] = set()

    def protect(self, entity: str):
        """Mark an entity as protected (always needs approval)."""
        self._protected_entities.add(entity)

    def block(self, entity: str):
        """Mark an entity as blocked (no changes allowed)."""
        self._blocked_entities.add(entity)

    def set_policy(self, change_class: ChangeClass, action: str):
        """Set policy for a change class: allow/block/require_approval."""
        self._policy[change_class] = action

    def evaluate(self, change: ASTChange) -> Tuple[bool, str, str]:
        """Evaluate a semantic change → (allowed, action, reason).

        Returns:
          allowed: True/False
          action: "allow" / "block" / "require_approval"
          reason: Human-readable explanation
        """
        # 1. Security concerns → always block
        if change.security_concerns:
            return False, "block", \
                f"security: {', '.join(change.security_concerns)}"

        # 2. Blocked entities → always block
        if change.entity_name in self._blocked_entities:
            return False, "block", \
                f"entity '{change.entity_name}' is blocked"

        # 3. Protected entities → always need approval
        if change.entity_name in self._protected_entities:
            return False, "require_approval", \
                f"entity '{change.entity_name}' requires approval"

        # 4. Policy-based
        action = self._policy.get(change.change_class, "require_approval")
        if action == "block":
            return False, "block", \
                f"'{change.change_class.value}' changes are blocked"
        if action == "require_approval":
            return False, "require_approval", \
                f"'{change.change_class.value}' requires approval"

        return True, "allow", ""
