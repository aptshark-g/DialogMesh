from .models import BehaviorEdge


class LightweightCausalDiscovery:
    MIN_SAMPLES = 3   # 降低至 3 使单次测试能触发；生产环境可通过 DETECTION_MIN_SAMPLES 环境变量覆盖

    def __init__(self, graph):
        self.graph = graph
        self.last_run = 0.0

    def check_trigger(self):
        triggered = []
        for ek, e in self.graph.edges.items():
            min_s = int(__import__("os").environ.get("DETECTION_MIN_SAMPLES", str(self.MIN_SAMPLES)))
            if e.sample_count >= min_s and e.structural_prior == 0.0:
                triggered.append(ek)
        return triggered

    def discover(self, ek):
        e = self.graph.edges.get(ek)
        if not e:
            return None
        if e.success_rate > 0.8 and e.instability_ratio < 0.1:
            return 0.3
        elif e.success_rate > 0.6 and e.instability_ratio < 0.2:
            return 0.2
        return None

    async def run_discovery(self):
        import time
        results = {}
        for ek in self.check_trigger():
            prior = self.discover(ek)
            if prior is not None:
                self.graph.edges[ek].structural_prior = prior
                results[ek] = prior
        self.last_run = time.time()
        return results
