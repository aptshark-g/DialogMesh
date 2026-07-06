"""BehaviorGraph core"""
from .models import BehaviorStep, BehaviorEdge, GraphStatistics
from .weight_updater import WeightUpdater
from .cold_start import ColdStartManager

class BehaviorGraph:
    def __init__(self, wu=None, csm=None, wq=None):
        self.nodes = {}
        self.edges = {}
        self.weight_updater = wu or WeightUpdater()
        self.cold_start = csm or ColdStartManager()
        self.weight_query = wq
        self.stats = GraphStatistics()

    def add_step(self, st):
        if st.step_id in self.nodes: return st.step_id
        self.nodes[st.step_id] = st
        self.stats.node_count = len(self.nodes)
        return st.step_id

    def record_edge(self, fs, ts, success=True, correction=False):
        fid = self.add_step(fs); tid = self.add_step(ts)
        ek = fid + "->" + tid
        if ek not in self.edges:
            self.edges[ek] = BehaviorEdge(ek, fid, tid)
        e = self.edges[ek]
        e.record_observation(success, correction)
        self.weight_updater.update_freq_ratio(e)
        e.weight = self.weight_updater.update(e)
        self.stats.edge_count = len(self.edges)
        self.stats.total_samples += 1
        return ek

    def get_step(self, sid):
        return self.nodes.get(sid)

    def get_edge_weight(self, fsum, tsum):
        for e in self.edges.values():
            fs = self.nodes.get(e.from_step_id)
            ts = self.nodes.get(e.to_step_id)
            if fs and ts and fs.action_summary==fsum and ts.action_summary==tsum:
                return e.weight
        return None

    async def get_weight(self, fsum, tsum, ft="", tt=""):
        if self.weight_query:
            r = await self.weight_query.query(fsum, tsum, ft, tt)
            if r and r.has_result: return r.avg_weight
        return self.cold_start.get_weight(fsum, tsum)

    
    def save(self, path):
        import json
        data = {"nodes": {}, "edges": {}, "stats": {}}
        for sid, n in self.nodes.items():
            data["nodes"][sid] = {"step_id": n.step_id, "action_summary": n.action_summary, "action_type": n.action_type, "entities": getattr(n, "entities", {}), "result": n.result, "timestamp": n.timestamp}
        for ek, e in self.edges.items():
            data["edges"][ek] = {"edge_id": e.edge_id, "from_step_id": e.from_step_id, "to_step_id": e.to_step_id, "weight": e.weight, "llm_causal_prob": e.llm_causal_prob, "freq_ratio": e.freq_ratio, "profile_boost": e.profile_boost, "structural_prior": e.structural_prior, "sample_count": e.sample_count, "success_count": e.success_count, "failure_count": e.failure_count, "correction_count": e.correction_count, "is_stable": e.is_stable, "is_deprecated": e.is_deprecated, "correction_mode": e.correction_mode}
        data["stats"] = {"node_count": self.stats.node_count, "edge_count": self.stats.edge_count, "total_samples": self.stats.total_samples}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path):
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        from .models import BehaviorStep, BehaviorEdge, GraphStatistics
        bg = cls.__new__(cls)
        bg.nodes = {}
        bg.edges = {}
        bg.weight_updater = None
        bg.cold_start = None
        bg.weight_query = None
        bg.config = {}
        bg.stats = GraphStatistics()
        for sid, nd in data.get("nodes", {}).items():
            bg.nodes[sid] = BehaviorStep(step_id=nd["step_id"], action_summary=nd["action_summary"], action_type=nd["action_type"], entities=nd.get("entities", {}), result=nd.get("result", ""), timestamp=nd.get("timestamp", 0))
        for ek, ed in data.get("edges", {}).items():
            bg.edges[ek] = BehaviorEdge(edge_id=ed["edge_id"], from_step_id=ed["from_step_id"], to_step_id=ed["to_step_id"], weight=ed.get("weight", 0.5), llm_causal_prob=ed.get("llm_causal_prob", 0), freq_ratio=ed.get("freq_ratio", 0), profile_boost=ed.get("profile_boost", 0), structural_prior=ed.get("structural_prior", 0), sample_count=ed.get("sample_count", 0), success_count=ed.get("success_count", 0), failure_count=ed.get("failure_count", 0), correction_count=ed.get("correction_count", 0), is_stable=ed.get("is_stable", True), is_deprecated=ed.get("is_deprecated", False), correction_mode=ed.get("correction_mode", False))
        bg.stats.node_count = data.get("stats", {}).get("node_count", len(bg.nodes))
        bg.stats.edge_count = data.get("stats", {}).get("edge_count", len(bg.edges))
        bg.stats.total_samples = data.get("stats", {}).get("total_samples", 0)
        return bg

    def get_statistics(self):
        return self.stats
