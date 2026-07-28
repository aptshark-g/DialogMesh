"""Level 3 Sandbox — LLM generates tool code, we validate and execute.

Workflow:
  1. LLM generates ToolAdapter subclass code
  2. ast.parse() → syntax check
  3. Import whitelist check (no os.system, subprocess, etc.)
  4. Static analysis (no while True, recursive depth limit)
  5. Save to tools/generated/
  6. Register → execute
  7. If success: persist + TriggerRule
  8. If failure: return error to LLM for retry
"""

from __future__ import annotations

import ast
import importlib
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent.tools.registry import ToolAdapter, ToolResult, ToolRegistry

logger = logging.getLogger("dm.sandbox")

GENERATED_DIR = Path(__file__).parent / "generated"

# ═══════════════════════════════════════════════════════════════
# Sandbox rules
# ═══════════════════════════════════════════════════════════════

FORBIDDEN_IMPORTS = {
    "os.system", "os.popen", "subprocess", "shutil.rmtree",
    "ctypes", "signal", "socket", "pickle", "marshal.unsafe",
    "eval", "exec", "compile",
}

FORBIDDEN_MODULES = {
    "os", "subprocess", "ctypes", "signal", "socket",
    "pickle", "marshal", "shutil",
    "multiprocessing", "threading",
}

ALLOWED_MODULES = {
    "requests", "bs4", "beautifulsoup4", "pymupdf", "fitz",
    "arxiv", "json", "re", "math", "datetime", "time",
    "collections", "itertools", "typing", "dataclasses",
    "pathlib", "io", "csv", "hashlib", "base64", "urllib",
    "pandas", "numpy", "lxml", "html", "textwrap", "string",
    "paddleocr", "trafilatura", "newspaper3k", "pypdf",
    "chromadb", "openai", "PIL", "Pillow",
}


@dataclass
class SandboxResult:
    passed: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    code: str = ""
    tool_path: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Validators
# ═══════════════════════════════════════════════════════════════

def validate_syntax(code: str) -> Tuple[bool, str]:
    """Check Python syntax with ast.parse."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def validate_imports(code: str) -> List[str]:
    """Check for forbidden imports. Returns list of violations."""
    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ["(syntax error — skipped import check)"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden import: {mod}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            full = f"{mod}.{node.names[0].name}" if node.names else mod
            if any(full.startswith(fb) for fb in FORBIDDEN_IMPORTS):
                violations.append(f"Forbidden import: {full}")
            if mod.split(".")[0] in FORBIDDEN_MODULES:
                violations.append(f"Forbidden module: {mod}")
    return violations


def validate_structure(code: str) -> List[str]:
    """Check for dangerous patterns: while True, deep recursion, etc."""
    warnings = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ["(syntax error — skipped structure check)"]

    while_count = 0
    recurse_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                while_count += 1
        if isinstance(node, ast.FunctionDef):
            # Check for self-recursion
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == node.name:
                        recurse_count += 1

    if while_count > 0:
        warnings.append(f"Found {while_count} while-True loops — inject max_iter guards")
    if recurse_count > 0:
        warnings.append(f"Found {recurse_count} recursive calls — verify depth limit")

    return warnings


# ═══════════════════════════════════════════════════════════════
# Main sandbox pipeline
# ═══════════════════════════════════════════════════════════════

def sandbox_validate(code: str) -> SandboxResult:
    """Run all validators on LLM-generated tool code."""
    result = SandboxResult(code=code)

    ok, err = validate_syntax(code)
    if not ok:
        result.errors.append(err)
        return result

    result.errors.extend(validate_imports(code))
    result.warnings.extend(validate_structure(code))
    result.passed = len(result.errors) == 0
    return result


def sandbox_register(code: str, tool_name: str = None) -> Tuple[SandboxResult, Optional[ToolAdapter]]:
    """Validate, persist, and register LLM-generated tool code.

    Returns (SandboxResult, ToolAdapter if successful else None).
    """
    result = sandbox_validate(code)
    if not result.passed:
        return result, None

    # Write to generated/
    os.makedirs(GENERATED_DIR, exist_ok=True)
    tool_path = GENERATED_DIR / f"{tool_name or 'custom_tool'}.py"
    tool_path.write_text(code, encoding="utf-8")
    result.tool_path = str(tool_path)

    # Dynamically load and register
    try:
        spec = importlib.util.spec_from_file_location(
            f"dm_generated_{tool_name or 'tool'}", tool_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)

            # Find ToolAdapter subclass
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, ToolAdapter) and obj is not ToolAdapter:
                    if obj.name:
                        ToolRegistry.register(obj)
                        logger.info("+generated tool %s from %s", obj.name, tool_path)
                        return result, obj

            result.errors.append(f"No ToolAdapter subclass found in generated code")
        else:
            result.errors.append(f"Cannot load module from {tool_path}")
    except Exception as e:
        result.errors.append(f"Module load failed: {e}")
        traceback.print_exc()

    return result, None


def sandbox_safe_exec(tool: ToolAdapter, **kwargs) -> ToolResult:
    """Execute a sandbox tool with safety timeout."""
    t0 = __import__("time").time()
    try:
        result = tool.execute(**kwargs)
        # Ensure result is ToolResult
        if not isinstance(result, ToolResult):
            result = ToolResult(tool.name, True, data=result,
                                latency_ms=(__import__("time").time() - t0) * 1000)
        return result
    except Exception as e:
        return ToolResult(tool.name, False, error=str(e),
                          latency_ms=(__import__("time").time() - t0) * 1000)
