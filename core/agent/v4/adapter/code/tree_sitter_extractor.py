"""Tree-sitter Python code structure extractor.

Extracts: class/function definitions, imports, decorators, method calls.
Used by CodeResolver to produce code projections for SemanticObjects.
"""
from __future__ import annotations
from typing import List, Dict, Optional


class PythonCodeExtractor:
    """Extracts structural information from Python source code."""

    def __init__(self):
        self._parser = None
        self._lang = None

    def _ensure_loaded(self):
        if self._parser is not None:
            return
        import tree_sitter_python as tspython
        import tree_sitter
        self._lang = tree_sitter.Language(tspython.language())
        self._parser = tree_sitter.Parser(language=self._lang)

    def extract(self, code: str) -> Dict:
        """Parse Python code and return structured info.

        Returns dict with:
          imports: [module names]
          classes: [{name, methods, decorators}]
          functions: [{name, params, decorators}]
          calls: [call expressions found in code]
        """
        self._ensure_loaded()
        result = {"imports": [], "classes": [], "functions": [], "calls": []}

        if not code.strip():
            return result

        tree = self._parser.parse(code.encode("utf-8"))
        root = tree.root_node

        def _traverse(node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        result["imports"].append(child.text.decode())
            elif node.type == "import_from_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        result["imports"].append(child.text.decode())
            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode() if name_node else "?"
                methods = []
                decs = []
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "function_definition":
                            fn_name = child.child_by_field_name("name")
                            if fn_name:
                                methods.append(fn_name.text.decode())
                        elif child.type == "decorated_definition":
                            for d in child.children:
                                if d.type == "decorator":
                                    decs.append(d.text.decode()[:40])
                result["classes"].append({
                    "name": name, "methods": methods, "decorators": decs,
                })
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode() if name_node else "?"
                params_node = node.child_by_field_name("parameters")
                params = params_node.text.decode() if params_node else ""
                decs = []
                parent = node.parent
                if parent and parent.type == "decorated_definition":
                    for d in parent.children:
                        if d.type == "decorator":
                            decs.append(d.text.decode()[:40])
                result["functions"].append({
                    "name": name, "params": params[:50], "decorators": decs,
                })
            elif node.type == "call":
                fn_node = node.child_by_field_name("function")
                if fn_node:
                    result["calls"].append(fn_node.text.decode())
                else:
                    result["calls"].append(node.text.decode()[:60])

            for child in node.children:
                _traverse(child)

        _traverse(root)
        return result

    def extract_for_concept(self, concept: str, code_blocks: List[str]) -> str:
        """Extract code structure focused on a concept name.

        Searches code blocks for the concept and returns structured summary.
        """
        if not code_blocks:
            return ""

        all_info = {"classes": [], "functions": [], "calls": []}
        for block in code_blocks[:3]:
            if concept.lower() in block.lower():
                info = self.extract(block)
                for cls_info in info.get("classes", []):
                    if concept.lower() in cls_info["name"].lower():
                        all_info["classes"].append(cls_info)
                for fn_info in info.get("functions", []):
                    if concept.lower() in fn_info["name"].lower():
                        all_info["functions"].append(fn_info)
                all_info["calls"].extend(info.get("calls", [])[:5])

        lines = []
        if all_info["classes"]:
            for c in all_info["classes"][:3]:
                methods_str = ", ".join(c["methods"][:5]) if c["methods"] else "(no methods)"
                lines.append(f"class {c['name']}: {methods_str}")
        if all_info["functions"]:
            for f in all_info["functions"][:3]:
                lines.append(f"def {f['name']}({f['params']})")
        if all_info["calls"]:
            unique_calls = list(dict.fromkeys(all_info["calls"]))[:5]
            lines.append(f"calls: {', '.join(unique_calls)}")

        return "\n".join(lines) if lines else ""
