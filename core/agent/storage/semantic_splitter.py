"""Semantic text splitter with overlap — from LangChain _merge_splits pattern.

OPENSOURCE_DEEP_READ.md §1: RecursiveCharacterTextSplitter._merge_splits.
  - Recursive separator fallback: ["\n\n", "\n", ". ", " ", ""]
  - chunk_size + chunk_overlap with tail-based overlap retention
  - Non-chunkable detection: code blocks, exact quotes, structured data
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Patterns that mark text as non-chunkable (keep whole, don't split)
NON_CHUNKABLE_PATTERNS = [
    (re.compile(r"```[\s\S]*?```", re.MULTILINE), "code_block"),
    (re.compile(r"`[^`]+`"), "inline_code"),
    (re.compile(r"> .*(?:\n> .*)*"), "quote_block"),
    (re.compile(r"^\s*\{[\s\S]*?\}\s*$", re.MULTILINE), "json_block"),
    (re.compile(r"^\s*\[[\s\S]*?\]\s*$", re.MULTILINE), "array_block"),
]


class SemanticSplitter:
    """Recursive text splitter with overlap and non-chunkable detection."""

    SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str, block_id: str = "") -> List[Tuple[str, bool]]:
        """Split text into chunks. Returns [(chunk_text, is_chunkable), ...].

        Non-chunkable: whole text returned as single chunk with is_chunkable=False.
        """
        if self._is_non_chunkable(text):
            return [(text, False)]

        return self._recursive_split(text, list(self.SEPARATORS))

    def _is_non_chunkable(self, text: str) -> bool:
        """Check if text matches any non-chunkable pattern."""
        for pattern, _ in NON_CHUNKABLE_PATTERNS:
            if pattern.fullmatch(text.strip()) or pattern.search(text):
                return True
        return False

    def _recursive_split(
        self, text: str, separators: List[str]
    ) -> List[Tuple[str, bool]]:
        """Recursive separator fallback — from LangChain _split_text."""
        # Find first matching separator
        sep = separators[-1]  # default: character-level
        next_seps: List[str] = []
        for i, s in enumerate(separators):
            if not s:  # empty string = split by character
                sep = s
                break
            if s in text:
                sep = s
                next_seps = separators[i + 1 :]
                break

        # Split
        if sep:
            splits = text.split(sep) if sep != "" else list(text)
        else:
            splits = list(text)

        # Merge with overlap
        return self._merge_splits(splits, sep, next_seps)

    def _merge_splits(
        self, splits: List[str], separator: str, remaining_seps: List[str]
    ) -> List[Tuple[str, bool]]:
        """Merge short splits into chunks with overlap.

        LangChain algorithm: accumulate until chunk_size exceeded,
        then merge with overlap from tail.
        """
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for split in splits:
            split_len = len(split) + (len(separator) if current else 0)

            if split_len < self.chunk_size:
                # Short enough — accumulate
                current.append(split)
                current_len += split_len
            else:
                # Too long — recursively split with next separator
                if remaining_seps:
                    sub = self._recursive_split(split, remaining_seps)
                    for sub_text, _ in sub:
                        self._add_to_current(sub_text, current, current_len)
                else:
                    # Last resort: truncate
                    self._add_to_current(split[: self.chunk_size], current, current_len)

            # Flush if chunk_size exceeded
            if current and len("".join(current)) >= self.chunk_size:
                chunks.append(separator.join(current))
                # Overlap: keep tail
                overlap_tokens = 0
                overlap = []
                for d in reversed(current):
                    d_len = len(d) + len(separator)
                    if overlap_tokens + d_len > self.chunk_overlap:
                        break
                    overlap.insert(0, d)
                    overlap_tokens += d_len
                current = overlap
                current_len = overlap_tokens

        if current:
            chunks.append(separator.join(current))

        return [(c, True) for c in chunks]

    def _add_to_current(self, text: str, current: List[str], current_len: int) -> None:
        current.append(text)
