"""CodeWorldAdapter: bridges Code world to the Structural World Model."""
from __future__ import annotations
import os, time, glob
from typing import Dict, List, Optional

from core.agent.v4.world.schema import ReferenceUnit, StructuralEdge, StructuralWorldGraph
from core.agent.v4.adapter.code.extractor import TreeSitterExtractor


class CodeWorldAdapter:
    """WorldAdapter for source code worlds.

    Wraps a StructureExtractor (default: TreeSitterExtractor) to build
    a complete StructuralWorldGraph from a codebase.

    Layer isolation: this is in the Adapter layer. The World layer never
    imports tree-sitter.
    """

    def __init__(self, languages: List[str] = None, tier: int = 1,
                 extractor=None):
        self._languages = languages or ["python"]
        if extractor is not None:
            self._extractor = extractor
        else:
            self._extractor = TreeSitterExtractor(tier=tier)
        self._graph: Optional[StructuralWorldGraph] = None

    def build_graph(self, project_root: str) -> StructuralWorldGraph:
        """Build a full StructuralWorldGraph from a project directory.

        Discovers all supported source files, extracts units and edges.
        """
        graph = StructuralWorldGraph(
            graph_id=f"code::{os.path.basename(project_root)}",
            world="code",
        )

        source_files = self._discover_files(project_root)

        for filepath in source_files:
            try:
                units = self._extractor.extract_units(filepath)
                edges = self._extractor.extract_edges(filepath)

                for unit in units:
                    graph.units[unit.unit_id] = unit
                graph.edges.extend(edges)
            except Exception:
                # Skip files that can't be parsed (syntax errors, etc.)
                continue

        graph.last_extracted_at = time.time()
        self._graph = graph
        return graph

    def incremental_update(self, changed_file: str) -> List[str]:
        """Update graph after a file change. Returns affected unit IDs."""
        if self._graph is None:
            return []

        affected = self._extractor.incremental_update(changed_file)

        # Remove old units and edges for the changed file
        prefix = self._extractor._module_name(changed_file)
        to_remove_units = [uid for uid in self._graph.units if uid.startswith(prefix)]
        for uid in to_remove_units:
            del self._graph.units[uid]

        self._graph.edges = [
            e for e in self._graph.edges
            if e.source_id not in to_remove_units and e.target_id not in to_remove_units
        ]

        # Re-extract
        try:
            units = self._extractor.extract_units(changed_file)
            edges = self._extractor.extract_edges(changed_file)
            for unit in units:
                self._graph.units[unit.unit_id] = unit
            self._graph.edges.extend(edges)
        except Exception:
            pass

        self._graph.last_extracted_at = time.time()
        return affected + [u.unit_id for u in units]

    def resolve_reference(self, ref: str) -> Optional[ReferenceUnit]:
        """Resolve a reference string to a ReferenceUnit."""
        if self._graph is None:
            return None
        return self._graph.get_unit(ref)

    def get_raw_content(self, source_path: str, unit_id: str) -> Optional[str]:
        """Get raw source code for a specific unit."""
        return self._extractor.get_raw_content(source_path, unit_id)

    @property
    def graph(self) -> Optional[StructuralWorldGraph]:
        return self._graph

    # ---- private ----

    def _discover_files(self, root: str) -> List[str]:
        """Discover Python source files in a project directory."""
        patterns = ["**/*.py"]
        files = []
        for pattern in patterns:
            files.extend(glob.glob(os.path.join(root, pattern), recursive=True))
        return sorted(set(files))
