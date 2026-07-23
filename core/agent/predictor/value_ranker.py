from .models import Candidate, ValueBreakdown

class ValueRanker:
    def __init__(self, graph, load_est=None, prof_matcher=None):
        self.graph = graph
        self.load_est = load_est
        self.prof_matcher = prof_matcher

    async def rank(self, candidates, profile):
        for c in candidates:
            c.success_rate = self._get_success_rate(c)
            if self.load_est:
                c.cognitive_load = self.load_est.estimate(c.action_type)
            if self.prof_matcher:
                c.profile_match = await self.prof_matcher.match(
                    c.action_type, c.action_summary, profile)
            c.compute_value()
        candidates.sort(key=lambda c: -c.expected_value)
        return candidates

    def _get_success_rate(self, cand):
        if not hasattr(self.graph, "edges"): return 0.5
        total = 0; success = 0
        for e in self.graph.edges.values():
            ts = self.graph.nodes.get(e.to_step_id)
            if ts and ts.action_summary == cand.action_summary:
                total += e.success_count + e.failure_count
                success += e.success_count
        return success / total if total > 0 else 0.5

    def get_breakdowns(self, candidates):
        return {c.action_summary: ValueBreakdown(
            llm_prob=c.llm_probability, success_rate=c.success_rate,
            cognitive_load=c.cognitive_load, profile_match=c.profile_match,
            expected_value=c.expected_value) for c in candidates}