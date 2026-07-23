"""ComplexityScorer - dynamic threshold for waterwave retrieval.
Computes query complexity from length, entity density, domain hints.
Adjusts similarity threshold via anchor + range formula."""


class ComplexityScorer:
    """Dynamic threshold for semantic similarity search.
    Complex queries use lower threshold (retrieve more), simple queries use higher."""

    SIMILARITY_ANCHOR = 0.25
    SIMILARITY_RANGE = (0.08, 0.25)

    def score(self, query_text: str) -> float:
        """Score query complexity 0.0-1.0. Higher = more complex."""
        score = 0.2
        # Longer queries tend to be more complex
        score += min(len(query_text) / 200, 0.3)
        # Entity-rich (uppercase, numbers) queries are more specific/complex
        special_chars = sum(1 for c in query_text if c.isupper() or c.isdigit())
        score += min(special_chars / 20, 0.2)
        # Domain specificity: technical terms indicate complexity
        tech_terms = ["debug", "scan", "config", "memory", "firewall", "port", "address", "protocol"]
        found = sum(1 for t in tech_terms if t in query_text.lower())
        score += min(found * 0.05, 0.3)
        return min(score, 1.0)

    def compute_threshold(self, complexity: float) -> float:
        """Map complexity to similarity threshold.
        Simple queries (c=0.2) get high threshold ~0.22 → few precise matches.
        Complex queries (c=0.8) get low threshold ~0.11 → many inclusive matches."""
        thresh = self.SIMILARITY_ANCHOR - complexity * 0.17
        low, high = self.SIMILARITY_RANGE
        return max(low, min(high, thresh))

    def get_threshold_from_text(self, query_text: str) -> float:
        c = self.score(query_text)
        return self.compute_threshold(c)
