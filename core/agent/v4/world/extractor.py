"""StructureExtractor ABC: abstract interface for structural extraction.

Defined in the World layer -- never imports tree-sitter or adapter-specific code.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from core.agent.v4.world.schema import ReferenceUnit, StructuralEdge


class StructureExtractor(ABC):
    """Abstraction over grammar/parser backends.

    Each world type (code/CAD/DOM) implements its own extractor.
    For code worlds, TreeSitterExtractor is the default implementation.
    """

    @abstractmethod
    def extract_units(self, source_path: str) -> List[ReferenceUnit]:
        """Extract all ReferenceUnits from a source file."""

    @abstractmethod
    def extract_edges(self, source_path: str) -> List[StructuralEdge]:
        """Extract all StructuralEdges from a source file."""

    @abstractmethod
    def incremental_update(self, changed_file: str) -> List[str]:
        """Update after a file change. Returns affected unit IDs."""

    @abstractmethod
    def get_raw_content(self, source_path: str, unit_id: str) -> Optional[str]:
        """Get raw source code content for a specific unit."""
