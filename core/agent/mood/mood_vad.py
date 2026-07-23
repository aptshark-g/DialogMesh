"""NRC-VAD Mood Classifier — VAD lexicon → Z-axis mapping.

NRC-VAD: ~20k words with Valence-Arousal-Dominance scores (0-1).
Public domain research lexicon from Saif Mohammad (NRC Canada).

Mapping:
  High Dominance (D>0.6) + High Valence (V>0.5) → solution_seeking (+1)
  High Arousal (A>0.6) + Low Dominance → exploration (0)  
  Low Valence (V<0.3) + High Arousal → mirror_emotional (-1)
  Everything else → neutral (0)

Usage:
  1. Download NRC-VAD-Lexicon.txt from https://saifmohammad.com/WebPages/nrc-vad.html
  2. Save as config/nrc_vad_lexicon.tsv
  3. MoodClassifierVAD.classify(text) → Z-axis value
"""

import re, logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class MoodClassifierVAD:
    """NRC-VAD based mood classification. 20k words, zero LLM, < 0.1ms."""

    def __init__(self, lexicon_path: str = "config/nrc_vad_lexicon.tsv"):
        self._vad: Dict[str, Tuple[float, float, float]] = {}
        self._load(lexicon_path)

    def _load(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('Word'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        word = parts[0].lower()
                        try:
                            v, a, d = float(parts[1]), float(parts[2]), float(parts[3])
                            self._vad[word] = (v, a, d)
                        except ValueError:
                            continue
            logger.info("NRC-VAD loaded: %d words", len(self._vad))
        except FileNotFoundError:
            logger.warning("NRC-VAD lexicon not found at %s. Download from https://saifmohammad.com/WebPages/nrc-vad.html", path)

    def classify(self, text: str) -> float:
        """Text → Z-axis (-1 to +1) via VAD word aggregation."""
        if not self._vad or not text.strip():
            return 0.0

        words = re.findall(r'[a-zA-Z]+', text.lower())
        if not words:
            return 0.0

        v_sum, a_sum, d_sum = 0.0, 0.0, 0.0
        count = 0
        for w in words:
            if w in self._vad:
                v, a, d = self._vad[w]
                v_sum += v
                a_sum += a
                d_sum += d
                count += 1

        if count == 0:
            return 0.0

        v_avg = v_sum / count
        a_avg = a_sum / count
        d_avg = d_sum / count

        # VAD → Z-axis
        # High D + High V → solution seeking
        # Low V + High A → emotional/mirror
        # High A + Low D → exploration
        if d_avg > 0.55 and v_avg > 0.5:
            return 1.0
        if v_avg < 0.35 and a_avg > 0.5:
            return -1.0
        if a_avg > 0.55 and d_avg < 0.45:
            return 0.0

        # Default: neutral
        return 0.0

    def __len__(self):
        return len(self._vad)
