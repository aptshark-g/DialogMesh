"""v3.2 pipeline integration bridge"""
from .compiler.hybrid_compiler import HybridCompiler
from .compiler.models import ParseResult, ParseContext
from .behavior_graph.graph_store import BehaviorGraph
from .behavior_graph.models import BehaviorStep
from .fusion.fusion_engine import FusionEngine
from .fusion.models import TrackResult, TrackType
from .predictor.predictor import BehaviorPredictor
from .predictor.candidate_generator import CandidateGenerator
from .predictor.value_ranker import ValueRanker
from .predictor.profile_matcher import ProfileMatcher
from .behavior_graph.cold_start import ColdStartManager
from .negative_kb.negative_kb import NegativeKB
from .causal_substrate.causal_substrate import CausalSubstrate
from .foa import FoA
from .l1_summary.l1_summary import L1Summary
from .rewarder.rewarder import BehaviorRewarder
from .rewarder.correction_detector import CorrectionDetector
from .rewarder.reward_rules import RewardRuleTable
from .behavior_graph.pruning import GraphPruner
from .behavior_graph.fast_correction import FastCorrectionDetector
from .behavior_graph.causal_discovery import LightweightCausalDiscovery
import time


class V32Pipeline:
    """v3.2 pipeline - Compiler to BehaviorGraph to FusionEngine"""

    def __init__(self, llm_provider, compiler=None, graph=None, fusion=None, enable_graph=True, monitor=None, session_recorder=None, save_path=None):
        self.llm = llm_provider
        self.compiler = compiler or HybridCompiler(llm_provider)
        self.graph = graph or BehaviorGraph()
        self.fusion = fusion or FusionEngine()
        self.enable_graph = enable_graph
        self.monitor = monitor
        self.session_recorder = session_recorder
        self.save_path = save_path
        self.turn = 0
        self._prev_step = None
        self._context = ParseContext()
        self._chain = []
        self.causal = LightweightCausalDiscovery(self.graph)
        self._candidate_gen = CandidateGenerator(self.llm)
        self._value_ranker = ValueRanker(self.graph)
        self._profile_matcher = ProfileMatcher()
        self._cold_start = ColdStartManager()
        self.predictor = BehaviorPredictor(self.graph, self._candidate_gen, self._value_ranker, self._profile_matcher, self._cold_start)
        self.pruner = GraphPruner(self.graph)
        self._correction = FastCorrectionDetector(self.graph)
        self._negative_kb = NegativeKB()
        self._causal_substrate = CausalSubstrate(self.graph)
        self._foa = FoA()
        self._l1 = L1Summary()
        self._rew_rules = RewardRuleTable()
        self._rewarder = BehaviorRewarder(self.graph, rules=self._rew_rules)
        self._corr_detector = CorrectionDetector()

    async def process(self, sentence, context=None, track1=None, track_p=None, causal=None, profile_lite=False):
        self.turn += 1
        parse = await self.compiler.process(sentence, self._context)

        # Causal structural prior
        self._causal_substrate.process_single(parse)
        # Negative KB check
        kb_res = self._negative_kb.check(sentence)
        kb_blocked = getattr(kb_res, 'hard_block', False)

        if self.enable_graph and parse.is_reliable and not parse.undefined:
            action = parse.slots.get("action")
            if action and action.value.strip():
                atype = "CODE_RUN" if any(k in action.value for k in ["run","exec","start","create"]) else "EXPLORATION"
                step = BehaviorStep(f"v32_{self.turn}", action.value, atype)
                self.graph.add_step(step)
                if self._prev_step is not None:
                    ek = self.graph.record_edge(self._prev_step, step)
                    if ek:
                        self._correction.record_observation(ek, False)
                self._prev_step = step
                # Build behavior chain and update context
                self._chain.append(step.step_id)
                for name, sv in parse.slots.items():
                    if sv and sv.value.strip():
                        self._context.add_entity(name, sv.value)
                self._context.turn_count = self.turn
                self._context.prev_stability = parse.stability

        if self.turn > 0 and self.turn % 50 == 0:
            pruned, orphans = self.pruner.prune()
            if pruned > 0 and self.monitor:
                self.monitor.record("graph", "prune", {"nodes_removed": pruned})

        pd = parse.to_dict() if hasattr(parse, "to_dict") else {}
        track0 = TrackResult(TrackType.TRACK_0, {"parse": pd, "stability": parse.stability}, parse.stability, parse.latency_ms)
        if self.monitor:
            overrides = sum(1 for s in parse.slots.values() if s.overridden)
            self.monitor.record("compiler", "process", {"slots": len(parse.slots), "overrides": overrides, "stability": parse.stability, "degraded": parse.degraded}, duration=parse.latency_ms)

        # Capture LLM data
        llm_prompt = ""
        llm_raw = ""
        if hasattr(self.compiler, "llm_parser"):
            llm_prompt = getattr(self.compiler.llm_parser, "last_prompt", "")
            llm_raw = getattr(self.compiler.llm_parser, "last_raw", "")
        if self.monitor and llm_prompt:
            self.monitor.record("llm", "generate", {"prompt": llm_prompt[:150], "raw": llm_raw[:150]}, duration=parse.latency_ms)

        # Session recorder
        # Track 1: LLM-derived intent/utterance
        track1 = TrackResult(TrackType.TRACK_1, {"utterance_type": parse.utterance_type, "sentiment": parse.sentiment, "raw_response": llm_raw[:200]}, 0.7 if parse.is_reliable else 0.3, parse.latency_ms)
        # Track P: Behavior prediction
        pred_result = None
        pred_cands, pred_mode, pred_conf = [], "no_data", 0.0
        chain_str = ""
        if self.predictor and self._chain:
            # Build meaningful chain from action summaries
            chain_actions = []
            for sid in self._chain[-5:]:
                if hasattr(self.graph, 'nodes') and sid in self.graph.nodes:
                    chain_actions.append(self.graph.nodes[sid].action_summary)
            chain_str = ", ".join(chain_actions) if chain_actions else ", ".join(str(s) for s in self._chain[-5:])
            pred_result = await self.predictor.predict(chain_str, self._chain[-1] if self._chain else "last", {})
            if pred_result and pred_result.candidates:
                pred_cands = [c.action_summary for c in pred_result.candidates[:3]]
                pred_conf = max(c.expected_value for c in pred_result.candidates)
                pred_mode = pred_result.query_mode
        track_p = TrackResult(TrackType.TRACK_P, {"predicted_actions": pred_cands, "mode": pred_mode}, pred_conf, 0.0)
        # Track CAUSAL: Lightweight causal discovery
        causal_r = {}
        trig = self.causal.check_trigger()
        if trig:
            causal_r = await self.causal.run_discovery()
        causal_conf = max(causal_r.values()) if causal_r else 0.0
        causal = TrackResult(TrackType.CAUSAL, {"causal_edges": list(causal_r.keys())[:5], "count": len(causal_r)}, causal_conf, 0.0)
        # Session recorder with tracks
        if self.session_recorder:
            turn_data = {"turn": self.turn, "query": sentence, "slots": parse.to_dict().get("slots", {}) if hasattr(parse, "to_dict") else {}, "stability": parse.stability, "degraded": parse.degraded, "prompt": llm_prompt[:300], "llm_raw": llm_raw[:300], "chain_step_id": self._chain[-1] if self._chain else None, "predicted": pred_cands, "causal_count": len(causal_r)}
            self.session_recorder.record_turn(turn_data)
        fusion = await self.fusion.fuse(track0, track1, track_p, causal, profile_lite=profile_lite)
        if self.monitor:
            dt = str(getattr(fusion.dominant_track, "value", fusion.dominant_track))
            self.monitor.record("fusion", "result", {"confidence": fusion.confidence, "track": dt, "conflicts": len(fusion.conflicts), "clarify": fusion.ask_clarification}, duration=getattr(fusion, "latency_ms", 0))
        if self.save_path and self.enable_graph and self.turn % 5 == 1:
            try:
                self.graph.save(self.save_path)
            except Exception:
                pass
        return {"parse": parse, "fusion": fusion, "turn": self.turn, "track1": track1, "track_p": track_p, "causal": causal, "kb_blocked": kb_blocked}

    def get_status(self):
        return {"turn": self.turn, "graph_nodes": len(self.graph.nodes) if self.enable_graph else 0}
