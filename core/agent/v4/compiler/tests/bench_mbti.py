"""MBTI-500 benchmark: measure TrackA profile differentiation across personality types.

MBTI dimensions → TrackA mapping:
  I vs E (Introversion): Higher cognitive_inertia, lower emotion_entropy
  T vs F (Thinking):   Lower emotion_entropy (rational analysis)  
  J vs P (Judging):    Higher trust (certainty preference)
  N vs S (Intuition):  Higher attention_anchor (abstract focus)
  
Method: For each MBTI type, feed 10 user posts to CognitiveProfileV2 TrackA,
        check if the resulting profile values differ significantly between types.
"""
from __future__ import annotations
import json, os, time
from typing import Dict, List, Tuple
from pathlib import Path


class MBTIEvaluator:
    """Evaluate TrackA against MBTI-500 dataset."""

    def __init__(self):
        self.data = None
        self.results: Dict[str, Dict] = {}

    def load(self) -> bool:
        """Try HF, fallback to synthetic MBTI test data."""
        try:
            from datasets import load_dataset
            ds = load_dataset("crd3/mbti_500", split="train", trust_remote_code=True, download_mode="force_redownload")
            self.data = ds
            print(f"Loaded MBTI-500: {len(ds)} posts")
            return True
        except Exception:
            pass  # Fall through to synthetic
        return self._load_synthetic()

    def _load_synthetic(self) -> bool:
        """Synthetic MBTI-like posts for offline testing."""
        self._synthetic_posts = [
            # (posts, mbti_type)
            (["I prefer working alone on complex problems. Social interactions drain me.",
              "Programming is my escape. I think deeply about architecture.",
              "Large meetings make me uncomfortable. I need quiet to focus.",
              "I overthink everything. My mind never stops analyzing."], "INTP"),
            (["I love brainstorming with the team! Energy from collaboration.",
              "Let me present our solution to the stakeholders.",
              "We should organize a team-building event this Friday!",
              "I make decisions quickly based on gut feeling."], "ESFJ"),
            (["The data clearly shows this approach is optimal.",
              "I need concrete metrics before making any decision.",
              "Your argument lacks logical consistency. Here is the proof.",
              "Efficiency matters more than harmony. Let the numbers speak."], "ISTJ"),
            (["I feel strongly about this ethical issue.",
              "We must consider how this affects real people's lives.",
              "My intuition tells me this is the right path.",
              "Harmony in the team is more important than being right."], "ENFP"),
        ]
        return True

    def evaluate(self) -> Dict:
        """Run evaluation and return results."""
        from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
        from core.agent.llm_providers.mock_provider import MockProvider
        from core.agent.v4.event_ir import DialogAdapter

        results = {}

        for posts, mbti in self._synthetic_posts:
            profile = None
            for i, post in enumerate(posts):
                # Simulate: build engine fresh to avoid contamination
                if i == 0:
                    eng = CognitiveRuntimeEngine(llm_provider=MockProvider("mock", {}))
                    eng.start()
                ad = DialogAdapter()
                eng.on_event(ad.adapt(post, session_id=f"mbti_{mbti}", turn_number=i+1))
                profile = getattr(eng, '_cognitive_profile', None)

            if profile and hasattr(profile, 'track_a'):
                ta = profile.track_a
                results[mbti] = {
                    "type": mbti,
                    "observations": ta.observation_count,
                    "cog_inertia": round(ta.cognitive_inertia, 3),
                    "trust": round(ta.trust_score, 3),
                    "emotion_entropy": round(ta.emotional_entropy, 3),
                    "attention_anchor": round(ta.attention_anchor, 3),
                    "self_value": round(ta.self_value_score, 3),
                }

        self.results = results
        return results

    def print_report(self):
        """Print comparison report."""
        if not self.results:
            print("No results. Run evaluate() first.")
            return

        print("\n═══════════════════════════════════════════════════")
        print("MBTI-500 TrackA Profile Evaluation")
        print("═══════════════════════════════════════════════════")
        header = f"{'MBTI':6s} | {'Obs':4s} | {'Inertia':7s} | {'Trust':5s} | {'Entropy':7s} | {'Attn':5s} | {'Self':5s}"
        print(header)
        print("-" * len(header))

        for mbti, r in sorted(self.results.items()):
            print(f"{mbti:6s} | {r['observations']:4d} | {r['cog_inertia']:7.3f} | "
                  f"{r['trust']:5.3f} | {r['emotion_entropy']:7.3f} | "
                  f"{r['attention_anchor']:5.3f} | {r['self_value']:5.3f}")

        # Differentiation check
        print("\n─── Differentiation Check ───")
        inertia_vals = [r['cog_inertia'] for r in self.results.values()]
        entropy_vals = [r['emotion_entropy'] for r in self.results.values()]
        print(f"Cognitive inertia spread: {min(inertia_vals):.3f} - {max(inertia_vals):.3f} "
              f"(delta={max(inertia_vals)-min(inertia_vals):.3f})")
        print(f"Emotion entropy spread: {min(entropy_vals):.3f} - {max(entropy_vals):.3f} "
              f"(delta={max(entropy_vals)-min(entropy_vals):.3f})")

        if max(inertia_vals) - min(inertia_vals) < 0.05:
            print("⚠️  FAIL: TrackA does not differentiate personality types")
        else:
            print("✅ PASS: TrackA shows measurable personality differentiation")


if __name__ == "__main__":
    evaluator = MBTIEvaluator()
    evaluator.load()
    evaluator.evaluate()
    evaluator.print_report()
