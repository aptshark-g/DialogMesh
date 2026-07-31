"""Coreference resolution via Stanza neural models — zero hardcoded patterns.

Uses pre-trained Stanza coreference models for Chinese (zh) and English (en).
Structural priors come from dependency parse tree, not hand-crafted regex.
Mention detection and coreference chains are model-learned, not enumerated.

Deps: stanza (pip install stanza)
Models: downloaded on first use (~200MB zh, ~50MB en)
"""
from __future__ import annotations

from typing import List, Optional, Dict
import logging

logger = logging.getLogger("dm.coref")


class StanzaCorefResolver:
    """Neural coreference resolution — zero hardcoded patterns.

    Uses Stanza's pre-trained coreference pipeline.
    Falls back gracefully if stanza/models not installed.
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._entity_history: List[str] = []
        self._pipelines: Dict[str, object] = {}
        self._available = self._check_stanza()

    @staticmethod
    def _check_stanza() -> bool:
        try:
            import stanza
            return True
        except ImportError:
            logger.info("Stanza not installed. Install: pip install stanza")
            return False

    def resolve(self, text: str, lang: str = "zh",
                current_entities: List[str] = None) -> str:
        """Resolve coreferences in text. Returns enriched text with [entity] replacements.

        Args:
            text: Raw text to process
            lang: 'zh' (Chinese) or 'en' (English)
            current_entities: Entities from current turn
        Returns:
            Enriched text with coreferent mentions replaced by [entity]
        """
        # Track entities
        if current_entities:
            self._entity_history.extend(current_entities)
            self._entity_history = self._entity_history[-self.window_size:]

        if not self._available:
            return text  # graceful degradation

        # Run coreference pipeline
        chains = self._get_coref_chains(text, lang)
        if not chains:
            return text

        # Build replacement mapping
        replacements = self._build_replacements(chains, text)
        return self._apply_replacements(text, replacements) if replacements else text

    def _get_coref_chains(self, text: str, lang: str) -> List[List[Dict]]:
        """Run Stanza coref pipeline, return mention chains."""
        try:
            import stanza
        except ImportError:
            return []

        # Lazy pipeline init
        if lang not in self._pipelines:
            try:
                processors = "tokenize,mwt,pos,depparse,coref" if lang == "zh" else "tokenize,coref"
                self._pipelines[lang] = stanza.Pipeline(
                    lang=lang, processors=processors,
                    download_method=stanza.DownloadMethod.REUSE_RESOURCES
                )
            except Exception as e:
                logger.warning("Stanza pipeline init failed for %s: %s", lang, e)
                self._available = False
                return []

        doc = self._pipelines[lang](text)
        chains = []
        if hasattr(doc, 'coref'):
            for chain in doc.coref:
                mentions = []
                for mention in chain.mentions:
                    mentions.append({
                        "text": mention.text,
                        "start": mention.start_char,
                        "end": mention.end_char,
                        "is_representative": mention.is_representative,
                    })
                if mentions:
                    chains.append(mentions)
        return chains

    def _build_replacements(
        self, chains: List[List[Dict]], text: str
    ) -> List[tuple]:
        """Build (start, end, replacement) tuples from coref chains."""
        replacements = []
        for chain in chains:
            # Find representative mention (most specific, usually first)
            representative = chain[0]
            rep_text = representative.get("representative_text") or representative["text"]

            # Track entity
            self._entity_history.append(rep_text)
            self._entity_history = self._entity_history[-self.window_size:]

            # Build replacements for non-representative mentions
            for mention in chain[1:]:  # skip representative
                mentions = chain[1:]
                for mention in chain[1:]:
                    repl_text = f"[{rep_text}]"
                    replacements.append((
                        mention["start"],
                        mention["end"],
                        repl_text
                    ))

        # Sort by position (reverse, to preserve indices during replacement)
        replacements.sort(key=lambda x: x[0], reverse=True)
        return replacements

    @staticmethod
    def _apply_replacements(text: str, replacements: List[tuple]) -> str:
        """Apply replacements from end to start to preserve positions."""
        result = text
        for start, end, repl in replacements:
            result = result[:start] + repl + result[end:]
        return result

    def add_entity(self, entity: str) -> None:
        self._entity_history.append(entity)
        self._entity_history = self._entity_history[-self.window_size:]

    @property
    def recent_entities(self) -> List[str]:
        return list(self._entity_history)
