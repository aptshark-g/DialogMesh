"""Document parsers: external file → DocumentNode tree."""
from __future__ import annotations
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from .tree import DocumentNode, make_node_id

logger = logging.getLogger(__name__)


class DocumentParser(ABC):
    """Parse external document into raw DocumentNode tree."""

    @abstractmethod
    def parse(self, content: str, source_path: str) -> DocumentNode:
        """Return root DocumentNode with hierarchical children."""


class MarkdownParser(DocumentParser):
    """Parse Markdown into DocumentNode tree by heading hierarchy."""

    # 匹配 ATX 标题: # / ## / ###
    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    # 代码块围栏
    _CODE_FENCE_RE = re.compile(r"^```(\w*)\s*$")

    def parse(self, content: str, source_path: str) -> DocumentNode:
        root = DocumentNode(
            node_id=make_node_id(source_path, []),
            source_path=source_path,
            heading_path=[],
            level=0,
            raw_text="",
            node_type="root",
        )
        if not content or not content.strip():
            return root

        lines = content.splitlines()
        stack: List[DocumentNode] = [root]  # level -> current node at that level

        i = 0
        while i < len(lines):
            line = lines[i]
            heading_match = self._HEADING_RE.match(line)
            if heading_match:
                hashes, title = heading_match.groups()
                level = len(hashes)
                heading_path = self._build_heading_path(stack, level, title)
                node = DocumentNode(
                    node_id=make_node_id(source_path, heading_path),
                    source_path=source_path,
                    heading_path=heading_path,
                    level=level,
                    raw_text=title,
                    node_type="heading",
                )
                # Attach to parent
                parent = self._find_parent(stack, level)
                parent.children.append(node)
                node.parent = parent
                # Update stack
                self._trim_stack(stack, level)
                stack.append(node)
                i += 1
                continue

            # Code block
            code_match = self._CODE_FENCE_RE.match(line)
            if code_match:
                lang = code_match.group(1)
                code_lines: List[str] = []
                i += 1
                while i < len(lines) and not self._CODE_FENCE_RE.match(lines[i]):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                code_text = "\n".join(code_lines)
                parent = stack[-1] if stack else root
                node = DocumentNode(
                    node_id=make_node_id(
                        source_path, parent.heading_path + [f"[code:{lang}]"]
                    ),
                    source_path=source_path,
                    heading_path=parent.heading_path + [f"[code:{lang}]"],
                    level=parent.level + 1,
                    raw_text=code_text,
                    node_type="code",
                    parent=parent,
                )
                parent.children.append(node)
                continue

            # Regular paragraph / list item / table row — accumulate until next heading or code fence
            para_lines: List[str] = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if self._HEADING_RE.match(next_line) or self._CODE_FENCE_RE.match(next_line):
                    break
                para_lines.append(next_line)
                i += 1
            para_text = "\n".join(para_lines).strip()
            if para_text:
                parent = stack[-1] if stack else root
                node_type = "list" if any(l.strip().startswith(("- ", "* ", "1. ")) for l in para_lines) else "paragraph"
                node = DocumentNode(
                    node_id=make_node_id(
                        source_path, parent.heading_path + [para_text[:40]]
                    ),
                    source_path=source_path,
                    heading_path=parent.heading_path,
                    level=parent.level + 1,
                    raw_text=para_text,
                    node_type=node_type,
                    parent=parent,
                )
                parent.children.append(node)

        return root

    # ---- helpers ----

    @staticmethod
    def _build_heading_path(stack: List[DocumentNode], level: int, title: str) -> List[str]:
        path: List[str] = []
        for node in stack[1:]:  # skip root
            if node.level < level:
                path.append(node.raw_text)
        path.append(title)
        return path

    @staticmethod
    def _find_parent(stack: List[DocumentNode], level: int) -> DocumentNode:
        for node in reversed(stack):
            if node.level < level:
                return node
        return stack[0] if stack else DocumentNode("", "", [], 0, "", "root")

    @staticmethod
    def _trim_stack(stack: List[DocumentNode], level: int) -> None:
        while len(stack) > level:
            stack.pop()


class ParserRegistry:
    """Registry for DocumentParser implementations."""

    def __init__(self):
        self._parsers: List[DocumentParser] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(MarkdownParser())

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    def get_parser(self, file_path: str) -> Optional[DocumentParser]:
        """Select parser by file extension."""
        ext = os.path.splitext(file_path)[1].lower()
        for parser in self._parsers:
            if isinstance(parser, MarkdownParser) and ext in (".md", ".markdown"):
                return parser
        logger.warning("No parser found for %s", file_path)
        return None

    def parse_file(self, file_path: str) -> Optional[DocumentNode]:
        """Convenience: read + parse file."""
        parser = self.get_parser(file_path)
        if parser is None:
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return parser.parse(content, file_path)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", file_path, e)
            return None
