"""TreeSitterExtractor: Python code extraction via tree-sitter.

Lives in the Adapter layer. Uses tree-sitter-python grammar.
"""
from __future__ import annotations
import os, time
from typing import Dict, List, Optional
from tree_sitter import Language, Parser, Node
import tree_sitter_python as tspython

from core.agent.v4.world.schema import ReferenceUnit, StructuralEdge, Location
from core.agent.v4.world.extractor import StructureExtractor


# tree-sitter-python node types
FUNCTION_DEF = "function_definition"
CLASS_DEF = "class_definition"
IMPORT_STMT = "import_statement"
IMPORT_FROM = "import_from_statement"
CALL = "call"
DECORATED_DEF = "decorated_definition"
MODULE = "module"
IDENTIFIER = "identifier"
DOTTED_NAME = "dotted_name"
ALIASED_IMPORT = "aliased_import"
ASSIGNMENT = "assignment"
EXPRESSION_STMT = "expression_statement"
RETURN_STMT = "return_statement"


def _get_text(node: Node, source: bytes) -> str:
    """Get the source text for a node."""
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _find_child(node: Node, node_type: str):
    """Find first child of given type."""
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _find_children(node: Node, node_type: str) -> List[Node]:
    """Find all children of given type."""
    return [c for c in node.children if c.type == node_type]


class TreeSitterExtractor(StructureExtractor):
    """Extract ReferenceUnits and StructuralEdges from Python source files.

    Tier 0: quick parse of imports + top-level definitions only (~500ms/1000 files)
    Tier 1: full AST traversal for all units + call edges (~5s/1000 files)
    """

    def __init__(self, tier: int = 1):
        self._tier = tier
        self._language = Language(tspython.language())
        self._parser = Parser(self._language)

    def extract_units(self, source_path: str) -> List[ReferenceUnit]:
        """Extract all ReferenceUnits from a Python source file."""
        source_bytes = self._read_source(source_path)
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        module_name = self._module_name(source_path)
        units: List[ReferenceUnit] = []

        # Module itself as a ReferenceUnit
        units.append(ReferenceUnit(
            unit_id=module_name,
            unit_type="file",
            name=os.path.basename(source_path),
            world="code",
            language="python",
            location=Location(file_path=source_path, start_line=1),
            last_updated=time.time(),
        ))

        # Walk top-level definitions
        for child in root.children:
            unit = self._extract_definition(child, source_path, source_bytes, module_name)
            if unit:
                units.append(unit)

        return units

    def extract_edges(self, source_path: str) -> List[StructuralEdge]:
        """Extract all StructuralEdges from a Python source file."""
        source_bytes = self._read_source(source_path)
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        module_name = self._module_name(source_path)
        edges: List[StructuralEdge] = []
        edge_ids: set[str] = set()

        for child in root.children:
            if child.type in (IMPORT_STMT, IMPORT_FROM):
                import_edges = self._extract_import_edges(
                    child, source_bytes, module_name
                )
                for e in import_edges:
                    if e.edge_id not in edge_ids:
                        edges.append(e)
                        edge_ids.add(e.edge_id)

            if self._tier >= 1 and child.type in (FUNCTION_DEF, CLASS_DEF, DECORATED_DEF):
                call_edges = self._extract_call_edges(
                    child, source_bytes, module_name
                )
                for e in call_edges:
                    if e.edge_id not in edge_ids:
                        edges.append(e)
                        edge_ids.add(e.edge_id)

        return edges

    def incremental_update(self, changed_file: str) -> List[str]:
        """Return unit IDs that need re-extraction after a file change."""
        module_name = self._module_name(changed_file)
        return [module_name]

    def get_raw_content(self, source_path: str, unit_id: str) -> Optional[str]:
        """Get raw source for a specific ReferenceUnit."""
        source_bytes = self._read_source(source_path)
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        module_name = self._module_name(source_path)

        if unit_id == module_name:
            return source_bytes.decode("utf-8")

        # Search for the specific definition
        for child in root.children:
            def_node = self._find_def_node(child)
            if def_node:
                def_name = self._definition_name(def_node, source_bytes)
                def_unit_id = f"{module_name}::{def_name}"
                if def_unit_id == unit_id:
                    return _get_text(child, source_bytes)

        return None

    # ---- private helpers ----

    def _read_source(self, source_path: str) -> bytes:
        with open(source_path, "rb") as f:
            return f.read()

    def _module_name(self, source_path: str) -> str:
        """Derive module name from file path (e.g., pkg/sub/mod.py -> pkg.sub.mod)."""
        rel = os.path.relpath(source_path)
        if rel.endswith(".py"):
            rel = rel[:-3]
        if rel == "__init__":
            rel = os.path.basename(os.path.dirname(source_path))
        return rel.replace(os.sep, ".")

    def _extract_definition(
        self, node: Node, source_path: str, source: bytes, module_name: str
    ) -> Optional[ReferenceUnit]:
        """Extract a ReferenceUnit from a top-level definition node."""
        def_node = self._find_def_node(node)
        if def_node is None:
            return None

        name = self._definition_name(def_node, source)
        if not name:
            return None

        node_type = def_node.type
        if node_type == FUNCTION_DEF:
            unit_type = "function"
        elif node_type == CLASS_DEF:
            unit_type = "class"
        else:
            return None

        # Collect class methods as attributes
        attributes: dict = {}
        if unit_type == "class":
            body = _find_child(def_node, "block")
            if body:
                methods = _find_children(body, FUNCTION_DEF)
                attributes["method_count"] = len(methods)
                attributes["methods"] = [
                    _get_text(_find_child(m, "identifier"), source) or f"<unnamed>"
                    for m in methods
                ]

        return ReferenceUnit(
            unit_id=f"{module_name}::{name}",
            unit_type=unit_type,
            name=name,
            world="code",
            language="python",
            location=Location(
                file_path=source_path,
                start_line=def_node.start_point[0] + 1,
                end_line=def_node.end_point[0] + 1,
            ),
            attributes=attributes,
            last_updated=time.time(),
        )

    def _find_def_node(self, node: Node) -> Optional[Node]:
        """Get the actual definition node (unwrapping decorated_definition)."""
        if node.type == DECORATED_DEF:
            for child in node.children:
                if child.type in (FUNCTION_DEF, CLASS_DEF):
                    return child
        if node.type in (FUNCTION_DEF, CLASS_DEF):
            return node
        return None

    def _definition_name(self, def_node: Node, source: bytes) -> Optional[str]:
        """Get the name of a function or class definition."""
        name_node = _find_child(def_node, "identifier")
        if name_node:
            return _get_text(name_node, source)
        return None

    def _extract_import_edges(
        self, node: Node, source: bytes, module_name: str
    ) -> List[StructuralEdge]:
        """Extract import edges from an import statement."""
        edges: List[StructuralEdge] = []

        if node.type == IMPORT_STMT:
            # import foo, bar.baz
            for name_node in _find_children(node, DOTTED_NAME):
                imported = _get_text(name_node, source)
                edges.append(StructuralEdge(
                    edge_id=f"{module_name}|{imported}|imports",
                    edge_type="imports",
                    source_id=module_name,
                    target_id=imported,
                    weight=1.0,
                    source="static",
                ))

        elif node.type == IMPORT_FROM:
            # from foo import bar
            module_node = _find_child(node, DOTTED_NAME)
            if module_node:
                from_module = _get_text(module_node, source)
                for name_node in _find_children(node, DOTTED_NAME):
                    if name_node != module_node:
                        imported = _get_text(name_node, source)
                        target_id = f"{from_module}.{imported}"
                        edges.append(StructuralEdge(
                            edge_id=f"{module_name}|{target_id}|imports",
                            edge_type="imports",
                            source_id=module_name,
                            target_id=target_id,
                            weight=1.0,
                            source="static",
                        ))
                # Also add aliased imports
                for alias_node in _find_children(node, ALIASED_IMPORT):
                    name_node = _find_child(alias_node, DOTTED_NAME)
                    if name_node:
                        imported = _get_text(name_node, source)
                        target_id = f"{from_module}.{imported}"
                        edges.append(StructuralEdge(
                            edge_id=f"{module_name}|{target_id}|imports",
                            edge_type="imports",
                            source_id=module_name,
                            target_id=target_id,
                            weight=1.0,
                            source="static",
                        ))

        return edges

    def _extract_call_edges(
        self, node: Node, source: bytes, module_name: str
    ) -> List[StructuralEdge]:
        """Extract call edges from within a function/class definition."""
        edges: List[StructuralEdge] = []
        def_node = self._find_def_node(node)
        if def_node is None:
            return edges

        def_name = self._definition_name(def_node, source) or "<unnamed>"
        source_unit_id = f"{module_name}::{def_name}"

        self._walk_calls(def_node, source, source_unit_id, edges)
        return edges

    def _walk_calls(
        self, node: Node, source: bytes, source_unit_id: str, edges: List[StructuralEdge]
    ):
        """Recursively walk AST to find call expressions."""
        if node.type == CALL:
            # Get the function being called
            func_node = node.child_by_field_name("function")
            if func_node:
                func_name = _get_text(func_node, source)
                if func_name and not func_name.startswith("self."):
                    edges.append(StructuralEdge(
                        edge_id=f"{source_unit_id}|{func_name}|calls",
                        edge_type="calls",
                        source_id=source_unit_id,
                        target_id=func_name,
                        weight=1.0,
                        source="static",
                    ))

        for child in node.children:
            self._walk_calls(child, source, source_unit_id, edges)
