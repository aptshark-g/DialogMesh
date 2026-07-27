# -*- coding: utf-8 -*-
"""ContentFetcher — fetch URL → extract text → chunk."""

from __future__ import annotations

import logging
import time
import urllib.request
import urllib.error
import re
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128


class ContentFetcher:
    """Fetch + extract + chunk web content.

    Supports: HTML, plain text, JSON, Markdown.
    PDF support: requires pymupdf (optional, graceful fallback).
    """

    def fetch(self, url: str, timeout: float = 8.0) -> Tuple[Optional[str], Optional[bytes]]:
        """Fetch URL. Returns (content_type, raw_bytes)."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ct = resp.headers.get("Content-Type", "text/html")
                raw = resp.read()
                return ct, raw
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", url[:80], e)
            return None, None

    def extract_text(self, content_type: str, raw: bytes) -> str:
        """Extract plain text from raw bytes based on content type."""
        ct_lower = content_type.lower()

        if "html" in ct_lower:
            return self._extract_html(raw)
        elif "pdf" in ct_lower:
            return self._extract_pdf(raw)
        elif "json" in ct_lower:
            return self._extract_json(raw)
        elif "markdown" in ct_lower or "text/md" in ct_lower:
            return raw.decode(errors="replace")
        elif "text/" in ct_lower:
            return raw.decode(errors="replace")
        else:
            # Unknown type — try as text, truncate
            text = raw.decode(errors="replace")[:5000]
            logger.debug("Unknown content type '%s', returning %d chars", ct_lower[:50], len(text))
            return text

    def _extract_html(self, raw: bytes) -> str:
        """Extract main text from HTML — priority: article > main > body."""
        html = raw.decode(errors="replace")

        # Try to find main content area
        for selector in ("article", "main"):
            pattern = rf'<{selector}[^>]*>(.*?)</{selector}>'
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                return self._strip_html(m.group(1))[:10000]

        # Fallback: strip all tags from body or entire doc
        body_m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        target = body_m.group(1) if body_m else html
        return self._strip_html(target)[:10000]

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags + normalize whitespace."""
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def _extract_pdf(self, raw: bytes) -> str:
        """Extract text from PDF — requires pymupdf (marker-pdf fallback)."""
        try:
            import fitz  # pymupdf
            import io
            doc = fitz.open(stream=raw, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text[:10000]
        except ImportError:
            logger.debug("pymupdf not installed — PDF extraction unavailable")
            return ""
        except Exception as e:
            logger.warning("PDF extraction failed: %s", e)
            return ""

    def _extract_json(self, raw: bytes) -> str:
        """Extract readable fields from JSON."""
        try:
            import json
            data = json.loads(raw)
            # Extract interesting fields
            parts = []
            if isinstance(data, dict):
                for key in ("description", "summary", "content", "text", "body", "readme"):
                    if key in data and isinstance(data[key], str):
                        parts.append(data[key])
            if isinstance(data, list):
                for item in data[:5]:
                    if isinstance(item, dict):
                        parts.append(str(item.get("description", "")) or str(item)[:200])
            return "\n".join(parts)[:10000] if parts else json.dumps(data, indent=2)[:10000]
        except Exception:
            return raw.decode(errors="replace")[:5000]

    def chunk(self, text: str, chunk_size: int = CHUNK_SIZE,
              overlap: int = CHUNK_OVERLAP) -> List[str]:
        """Split text into overlapping chunks for embedding."""
        if not text:
            return []
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks
