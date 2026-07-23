import time
from .models import Candidate, PredictionResult, ValueBreakdown
from .candidate_generator import CandidateGenerator
from .value_ranker import ValueRanker
from .training_loop import TrainingFeedbackLoop

class BehaviorPredictor:
    MODE_FULL = "full"; MODE_NO_GRAPH = "no_graph"
    MODE_NO_LLM = "no_llm"; MODE_FALLBACK = "fallback"

    def __init__(self, graph, candidate_gen, value_ranker, profile_matcher=None, cold_start=None):
        self.graph = graph
        self.gen = candidate_gen
        self.ranker = value_ranker
        self.prof = profile_matcher
        self.cold_start = cold_start
        self.training = TrainingFeedbackLoop()

    async def predict(self, chain_summary, current_step_id, profile):
        start = time.monotonic()
        hints = self._get_graph_hints(current_step_id)
        llm_cands = await self.gen.generate(chain_summary, profile, hints)

        if llm_cands and hints:
            cands = [Candidate(a, "", p) for a, p in llm_cands]
            ranked = await self.ranker.rank(cands, profile)
            return self._result(ranked, "full", start)

        if llm_cands:
            cands = [Candidate(a, "", llm_probability=p) for a, p in llm_cands]
            for c in cands:
                c.expected_value = c.llm_probability * 0.7 + 0.0
                if self.prof:
                    c.profile_match = await self.prof.match("", c.action_summary, profile)
            return self._result(cands, "no_graph", start)

        if hints:
            cands = [Candidate(h[0], "", expected_value=h[1]) for h in hints]
            return self._result(cands, "no_llm", start)

        fb = self._fallback()
        return self._result(fb, "fallback", start)

    def _result(self, cands, mode, start):
        top1 = cands[0].action_summary if cands else ""
        low = all(c.expected_value < 0.3 for c in cands) if cands else True
        bd = self.ranker.get_breakdowns(cands) if hasattr(self.ranker, "get_breakdowns") else {}
        return PredictionResult(cands or [], bd, mode, top1, low, (time.monotonic()-start)*1000)

    def _fallback(self):
        if self.cold_start:
            seeds = self.cold_start.get_active_seeds()
            return [Candidate(s.to_summary, s.to_type, expected_value=s.initial_weight) for s in seeds[:5]]
        return [Candidate("ask_clarification")]

    def _get_graph_hints(self, sid):
        if not hasattr(self.graph, "edges"): return []
        succ = []
        for ek, e in self.graph.edges.items():
            if e.from_step_id == sid and not e.is_deprecated:
                ts = self.graph.nodes.get(e.to_step_id)
                if ts: succ.append((ts.action_summary, e.weight))
        return sorted(succ, key=lambda x: -x[1])[:3]
