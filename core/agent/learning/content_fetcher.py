# -*- coding: utf-8 -*-
"""ContentFetcher — fetch URL → extract clean text → chunk.

Extraction pipeline:
  1. trafilatura (primary) — purpose-built for web content extraction
  2. newspaper3k — article metadata + NLP summary
  3. bs4 regex (fallback) — only when neither is available
"""

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
    """Fetch + extract clean text + chunk using trafilatura/newspaper3k.

    trafilatura: precision content extraction (removes nav/ads/sidebar)
    newspaper3k: article metadata + NLP summary
    bs4: fallback when neither available
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
        """Extract clean text from raw bytes.

        Priority: trafilatura > newspaper3k > bs4 fallback.
        """
        ct_lower = content_type.lower()

        if "html" in ct_lower:
            return self._extract_html(raw)
        elif "pdf" in ct_lower:
            return self._extract_pdf(raw)
        elif "json" in ct_lower:
            return self._extract_json(raw)
        elif "text/" in ct_lower or "markdown" in ct_lower:
            return raw.decode(errors="replace")[:10000]
        else:
            text = raw.decode(errors="replace")[:5000]
            return text

    # ─── HTML extraction pipeline ───

    def _extract_html(self, raw: bytes) -> str:
        """Extract main content from HTML.

        Layer 1: trafilatura — precision extraction (preferred)
        Layer 2: newspaper3k — article pipeline
        Layer 3: bs4 — basic HTML stripping (fallback)
        """
        html = raw.decode(errors="replace")

        # L1: trafilatura (best — removes nav, ads, sidebar, boilerplate)
        text = self._try_trafilatura(html)
        if text and len(text) > 200:
            logger.debug("Extracted via trafilatura: %d chars", len(text))
            return text[:10000]

        # L2: newspaper3k (good — article metadata + NLP summary)
        text = self._try_newspaper(html)
        if text and len(text) > 100:
            logger.debug("Extracted via newspaper3k: %d chars", len(text))
            return text[:10000]

        # L3: bs4 fallback (basic — strip tags only)
        text = self._strip_html_basic(html)
        logger.debug("Extracted via bs4 fallback: %d chars", len(text))
        return text[:10000]

    def _try_trafilatura(self, html: str) -> Optional[str]:
        """Extract using trafilatura — the gold standard."""
        try:
            import trafilatura
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
                output_format="txt",
            )
            return text
        except ImportError:
            logger.debug("trafilatura not installed — skipping L1 extraction")
        except Exception as e:
            logger.debug("trafilatura failed: %s", e)
        return None

    def _try_newspaper(self, html: str) -> Optional[str]:
        """Extract using newspaper3k — article NLP pipeline."""
        try:
            import newspaper
            from newspaper import Article
            import io

            # newspaper3k needs a URL, but we only have HTML
            # Use Config to parse from raw HTML
            config = newspaper.Config()
            config.fetch_images = False
            config.memoize_articles = False

            article = Article("", config=config)
            article.download(input_html=html)
            article.parse()

            # Try NLP summary if available
            try:
                article.nlp()
                if article.summary:
                    return f"{article.title}\n\n{article.text}\n\n摘要: {article.summary}"
            except Exception:
                pass

            text = article.text
            if article.title:
                text = f"{article.title}\n\n{text}"
            return text
        except ImportError:
            logger.debug("newspaper3k not installed — skipping L2 extraction")
        except Exception as e:
            logger.debug("newspaper3k failed: %s", e)
        return None

    @staticmethod
    def _strip_html_basic(html: str) -> str:
        """Basic HTML stripping — removes tags + scripts + styles.

        Only used as L3 fallback when trafilatura/newspaper3k unavailable.
        """
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    # ─── PDF / JSON extraction ───

    def _extract_pdf(self, raw: bytes) -> str:
        """Extract text from PDF — pymupdf → OCR fallback.

        L1: pymupdf text extraction (works for native PDFs)
        L2: PaddleOCR (scan detection: if text < 50 chars → OCR)
        """
        text = ""
        is_scan = False

        # L1: pymupdf native extraction
        try:
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            logger.debug("pymupdf not installed")
        except Exception as e:
            logger.warning("PDF text extraction failed: %s", e)

        is_scan = len(text.strip()) < 50  # scan detection

        # L2: PaddleOCR for scanned PDFs
        if is_scan:
            ocr_text = self._try_paddleocr(raw)
            if ocr_text:
                text = ocr_text
                logger.info("OCR extracted %d chars from scanned PDF", len(ocr_text))

        return text[:10000] if text else ""

    def _try_paddleocr(self, raw: bytes) -> Optional[str]:
        """OCR via PaddleOCR — best for Chinese + multilingual."""
        try:
            from paddleocr import PaddleOCR
            import tempfile, os
            ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            # Write to temp file (PaddleOCR needs file path)
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                f.write(raw)
                tmp_path = f.name
            result = ocr.ocr(tmp_path, cls=True)
            os.unlink(tmp_path)
            if result and result[0]:
                return " ".join(line[1][0] for line in result[0])
        except ImportError:
            logger.debug("PaddleOCR not installed — skipping OCR")
        except FileNotFoundError:
            logger.debug("PaddleOCR model not downloaded — run: paddleocr --download")
        except Exception as e:
            logger.warning("PaddleOCR failed: %s", e)
        return None

    def _extract_json(self, raw: bytes) -> str:
        """Extract readable fields from JSON."""
        try:
            import json
            data = json.loads(raw)
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

    # ─── Chunking ───

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
