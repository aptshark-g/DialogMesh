"""LSH pruning for ConceptGraph O(n²)→O(n log n) + BGE importance scoring.

P2: Locality-Sensitive Hashing to skip unnecessary edge candidates.
P3: Semantic importance computation replacing string matching.
"""
from __future__ import annotations
import numpy as np
import hashlib
from typing import List, Dict, Tuple


class LSHIndex:
    """MinHash LSH for O(1) candidate pruning in graph edge construction.

    Instead of comparing every pair of nodes (O(n²)), hash each node
    into buckets and only compare within buckets → O(n * bucket_size).
    """

    def __init__(self, num_hashes: int = 64, num_bands: int = 8):
        self.num_hashes = num_hashes
        self.num_bands = num_bands
        self.rows_per_band = num_hashes // num_bands
        self._buckets: Dict[str, List[str]] = {}  # band_hash → [node_ids]

    def _tokenize(self, text: str) -> set:
        """Tokenize for MinHash: character trigrams + word tokens."""
        tokens = set()
        for i in range(len(text) - 2):
            tokens.add(text[i:i+3])
        for word in text.split():
            tokens.add(word.lower())
        return tokens

    def _minhash_signature(self, tokens: set) -> np.ndarray:
        """Compute MinHash signature for a set of tokens."""
        sig = np.full(self.num_hashes, np.iinfo(np.int64).max)
        for token in tokens:
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            for i in range(self.num_hashes):
                # Simple universal hash: h * (i+1) mod large prime
                v = (h * (i + 1) + i * 2654435761) % (2**31 - 1)
                sig[i] = min(sig[i], v)
        return sig

    def add(self, node_id: str, text: str):
        """Add node to LSH buckets."""
        tokens = self._tokenize(text)
        sig = self._minhash_signature(tokens)
        for band in range(self.num_bands):
            start = band * self.rows_per_band
            end = start + self.rows_per_band
            band_sig = tuple(sig[start:end].tolist())
            band_hash = hashlib.md5(str(band_sig).encode()).hexdigest()[:12]
            bucket_key = f"{band}:{band_hash}"
            if bucket_key not in self._buckets:
                self._buckets[bucket_key] = []
            self._buckets[bucket_key].append(node_id)

    def candidates(self, min_bucket_size: int = 2) -> List[Tuple[str, str]]:
        """Return candidate pairs that share at least one bucket."""
        pairs = set()
        for bucket in self._buckets.values():
            if len(bucket) < min_bucket_size:
                continue
            for i in range(len(bucket)):
                for j in range(i + 1, len(bucket)):
                    if bucket[i] < bucket[j]:
                        pairs.add((bucket[i], bucket[j]))
                    else:
                        pairs.add((bucket[j], bucket[i]))
        return list(pairs)


def bge_importance_score(text: str, signal_descriptions: Dict[str, str], encoder=None) -> float:
    """Semantic importance scoring using BGE similarity.

    Replaces string matching ('不是' in text) with semantic similarity
    between the text and importance signal descriptions.

    Args:
        text: User input text
        signal_descriptions: {"correction": "用户纠正系统错误", ...}
        encoder: Optional BGE encoder (lazy-loaded if None)

    Returns:
        Importance score 0-1
    """
    if not text or not signal_descriptions or len(text) < 2:
        return 0.3  # default

    try:
        if encoder is None:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            encoder = SemanticEncoder()

        text_vec = encoder.encode(text)
        best_cos = 0.0

        for desc in signal_descriptions.values():
            desc_vec = encoder.encode(desc)
            cos = float(np.dot(text_vec, desc_vec) / 
                       (np.linalg.norm(text_vec) * np.linalg.norm(desc_vec) + 1e-8))
            best_cos = max(best_cos, cos)

        # Map cosine to importance: 0.5→0.3, 0.8→0.7, 0.95→0.9
        if best_cos > 0.85:
            return 0.9
        elif best_cos > 0.65:
            return 0.7
        elif best_cos > 0.45:
            return 0.5
        return 0.3
    except Exception:
        return 0.3
