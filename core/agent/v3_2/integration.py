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
from ..discourse_block_tree import DiscourseBlockTreeManager
from .predictor.cognitive_profile import ProfileUpdater, CognitiveProfile, EnhancedProfileMatcher
from .predictor.training_loop import TrainingFeedbackLoop
from .foa import FoA
from .l1_summary.l1_summary import L1Summary
from .l2_summary.l2_summary import L2Summary
from .rewarder.rewarder import BehaviorRewarder
from .rewarder.correction_detector import CorrectionDetector
from .rewarder.reward_rules import RewardRuleTable
from .behavior_graph.pruning import GraphPruner
from .behavior_graph.fast_correction import FastCorrectionDetector
from .behavior_graph.causal_discovery import LightweightCausalDiscovery
from .embedding.behavior_embedding import PredicateMapper
from .embedding.behavior_embedding import EMBEDDER, PROTOTYPES
import time
from .persistence import PersistenceManager
from .circuit_breaker import CircuitBreaker
from .metacognition import MetaCognitionAdapter

_PRED_MAPPER = PredicateMapper()
CODE_RUN_CLASSES = set(_PRED_MAPPER.classes)  # 使用 PredicateMapper 全部分类


class V32Pipeline:
    """v3.2 pipeline - Compiler to BehaviorGraph to FusionEngine"""

    def __init__(self, llm_provider, compiler=None, graph=None, fusion=None, enable_graph=True, monitor=None, session_recorder=None, save_path=None, save_dir=""):
        self.llm = llm_provider
        self.block_tree = DiscourseBlockTreeManager(llm_provider=self.llm)
        self.save_dir = save_dir or ""
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
        self._profile = CognitiveProfile.create()
        self._profile_updater = ProfileUpdater(self._profile)
        self._profile_matcher = EnhancedProfileMatcher(self._profile)
        self._cold_start = ColdStartManager()
        self.predictor = BehaviorPredictor(self.graph, self._candidate_gen, self._value_ranker, self._profile_matcher, self._cold_start)
        self.pruner = GraphPruner(self.graph)
        self._correction = FastCorrectionDetector(self.graph)
        self._negative_kb = NegativeKB()
        self._causal_substrate = CausalSubstrate(self.graph)
        self._foa = FoA()
        self._edge_embs = {}  # BGE embedding cache for graph edges
        self._bridge_cache = {}
        self._bridge_enabled = False
        self._v30_orchestrator = None
        try:
            from core.agent.v3_0.orchestrator.orchestrator import Orchestrator
            self._v30_orchestrator = Orchestrator(llm_provider=self.llm)
            self._bridge_enabled = True
            import logging; logging.info('[Bridge] v3.0 Orchestrator attached')
        except Exception as e:
            import logging; logging.warning(f'[Bridge] v3.0 Orchestrator unavailable: {e}')
        self._l1 = L1Summary()
        self._l2 = L2Summary()
        # L2Summary - lazy import in process() to avoid relative import issue
        self._rew_rules = RewardRuleTable()
        self._rewarder = BehaviorRewarder(self.graph, rules=self._rew_rules)
        self._training_loop = TrainingFeedbackLoop(rewarder=self._rewarder)
        self._corr_detector = CorrectionDetector()
        # Circuit breaker for LLM calls
        self._llm_cb = CircuitBreaker(name="llm", max_failures=3, cooldown=30)
        self._llm_fallback = '[LLM Fallback] Service unavailable'
        # Metacognition (off by default, enable via set_meta_cog)
        self._meta_cog = MetaCognitionAdapter(self.llm, enabled=False)
        # Persistence (lazy init, call init_persistence() to start)
        self.persistence = None

    async def process(self, sentence, context=None, track1=None, track_p=None, causal=None, profile_lite=False, hy_memory_mode=False):
        self.turn += 1
        block_ids = self.block_tree.ingest_turn(self.turn, sentence)
        if self.monitor:
            bt = self.block_tree.get_tree_summary()
            ts = getattr(self.block_tree, '_last_switch', None)
            self._last_topic_switch = bool(ts and ts[0])
            self.monitor.record("block_tree", "ingest",
                {"blocks": bt.get("total_blocks", 0), "active": bt.get("active", 0),
                 "topic_switch": str(self._last_topic_switch)},
                status="ok")
        else:
            self._last_topic_switch = False
        parse = await self.compiler.process(sentence, self._context)

        # Causal structural prior
        self._causal_substrate.process_single(parse)
        if self.monitor:
            self.monitor.record("causal", "process_single",
                {"stable": parse.stability > 0.6,
                 "slots": len(parse.slots),
                 "reliable": parse.is_reliable})
        # Negative KB check
        kb_res = self._negative_kb.check(sentence)
        kb_blocked = getattr(kb_res, 'hard_block', False)
        if self.monitor:
            self.monitor.record("negative_kb", "check", {"blocked": str(kb_blocked)})

        _turn_has_action = False
        if self.enable_graph and parse.is_reliable and not parse.undefined:
            action = parse.slots.get("action")
            if action and action.value.strip():
                pred_class = _PRED_MAPPER.map_verb(action.value)
                atype = pred_class if pred_class else "EXPLORATION"
                step = BehaviorStep(f"v32_{self.turn}", action.value, atype)
                self.graph.add_step(step)
                if self._prev_step is not None:
                    ek = self.graph.record_edge(self._prev_step, step)
                    if ek:
                        # 矫正检测: 检测 text 是否包含纠正信号
                        prev_actions_list = [self.graph.nodes[sid].action_summary for sid in self._chain[-3:] if sid in self.graph.nodes] if hasattr(self.graph, 'nodes') else []
                        corr_check = self._corr_detector.detect(sentence, prev_actions_list, action.value)
                        is_correction = corr_check.is_correction if hasattr(corr_check, 'is_correction') else False
                        self._correction.record_observation(ek, is_correction)
                        if block_ids and ek:
                            self.block_tree.add_cross_ref(block_ids[0], "graph:{ek}", "behavior_similar", 0.3, "auto_graph")
                        if is_correction and self.monitor:
                            self.monitor.record("graph", "correction_signal",
                                {"edge": str(ek)[:20], "type": getattr(corr_check, 'correction_type', 'unknown')})
                        if self.monitor:
                            self.monitor.record("graph", "edge",
                            {"ek": str(ek)[:20],
                             "w": round(self.graph.edges.get(ek).weight, 3) if ek in self.graph.edges else 0,
                             "samples": self.graph.edges.get(ek).sample_count if ek in self.graph.edges else 0,
                             "corrections": self.graph.edges.get(ek).correction_count if ek in self.graph.edges else 0})
                if hasattr(self, "_profile_updater"):
                    uncertainty = parse.stability < 0.6 or parse.undefined
                    self._profile_updater.record_action(atype, action.value, parse.stability,
                        uncertainty=uncertainty, topic_switch=self._last_topic_switch)
                    self._profile_updater.record_turn_to_buffer(
                        atype, action.value, parse.stability,
                        kb_blocked, self._last_topic_switch)
                    if self.monitor:
                        p = self._profile_updater.profile
                        if uncertainty:
                            self.monitor.record("profile", "uncertainty",
                                {"stability": f"{parse.stability:.2f}", "meta": f"{p.metacognition:.2f}"})
                        self.monitor.record("profile", "update",
                            {"action": action.value[:30], "meta": f"{p.metacognition:.2f}",
                             "div": f"{p.divergence:.2f}", "conf": f"{p.confidence:.2f}"})
                _turn_has_action = True
                self._prev_step = step
                # Build behavior chain and update context
                self._chain.append(step.step_id)
                for name, sv in parse.slots.items():
                    if sv and sv.value.strip():
                        self._context.add_entity(name, sv.value)
                self._context.turn_count = self.turn
                self._context.prev_stability = parse.stability

        # Always update profile, even for unreliable parses
        if hasattr(self, "_profile_updater") and not _turn_has_action:
            raw_action = getattr(parse, "utterance_type", "") or "unknown"
            self._profile_updater.record_action("UNKNOWN", raw_action, parse.stability,
            uncertainty=True, topic_switch=self._last_topic_switch)
            if self.monitor:
                p = self._profile_updater.profile
                self._profile_updater.record_turn_to_buffer(
                    "UNKNOWN", raw_action, parse.stability,
                    kb_blocked, self._last_topic_switch)
                self.monitor.record("profile", "uncertainty",
                    {"stability": f"{parse.stability:.2f}", "meta": f"{p.metacognition:.2f}"})
                self.monitor.record("profile", "update",
                    {"action": "UNKNOWN", "meta": f"{p.metacognition:.2f}",
                     "div": f"{p.divergence:.2f}", "conf": f"{p.confidence:.2f}"})

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
                pred_cands = [{"action": c.action_summary, "value": round(c.expected_value, 3)} for c in pred_result.candidates[:3]]
                pred_conf = max(c.expected_value for c in pred_result.candidates)
                pred_mode = pred_result.query_mode
                if self.monitor:
                    self.monitor.record("predictor", "result",
                        {"candidates": len(pred_cands), "mode": pred_mode, "confidence": f"{pred_conf:.3f}"})
                if hasattr(self, "_training_loop") and self._prev_step:
                    # 使用真实矫正检测结果而非 kb_blocked
                    corr_for_train = self._corr_detector.detect(sentence, chain_actions if chain_actions else prev_actions_list, self._chain[-1] if self._chain else "")
                    is_corr = corr_for_train.is_correction if hasattr(corr_for_train, 'is_correction') else kb_blocked
                    sig = self._training_loop.on_user_action(
                        pred_result, getattr(self._prev_step, 'edge_key', '') if self._prev_step else "",
                        actual_type=atype if 'atype' in dir() else "", is_correction=is_corr)
                    if self.monitor:
                        self.monitor.record("training", "signal",
                            {"reward": getattr(sig, "reward", 0), "is_correction": is_corr})
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
        # Create strategic track from cached orchestrator planning result
        strategic_track = None
        orch_plan = self._bridge_cache.get("planning")
        if orch_plan and isinstance(orch_plan, dict):
            strategic_track = TrackResult(
                track=TrackType.STRATEGIC,
                output=orch_plan,
                confidence=orch_plan.get("confidence", 0.5),
            )
        if hy_memory_mode:
            sys1 = max(getattr(track0, chr(34) + 'confidence' + chr(34), 0), getattr(track_p, chr(34) + 'confidence' + chr(34), 0))
            t1 = track1 if sys1 < 0.6 else None
        else:
            t1 = track1
        fusion = await self.fusion.fuse(track0, t1, track_p, causal, strategic=strategic_track, profile_lite=profile_lite)
        if self.monitor:
            dt = str(getattr(fusion.dominant_track, "value", fusion.dominant_track))
            self.monitor.record("fusion", "result", {"confidence": fusion.confidence, "track": dt, "conflicts": len(fusion.conflicts), "clarify": fusion.ask_clarification}, duration=getattr(fusion, "latency_ms", 0))
        if self.save_path and self.enable_graph and self.turn % 5 == 1:
            try:
                self.graph.save(self.save_path)
            except Exception:
                pass
        bt_summary = self.block_tree.get_tree_summary()
        bt_context = self.block_tree.build_context()
        # Heartbeat: unmonitored modules
        if self.monitor and self.turn % 5 == 0:
            self.monitor.record("foa", "heartbeat", {"active": "1"})
            self.monitor.record("l1", "heartbeat", {"active": "1"})
        if self.monitor and hasattr(self, "_l2"):
            self.monitor.record("l2", "heartbeat", {"turns": self.turn})
        ww = self._waterwave_activate()
        await self._bridge_v32_to_v30(parse, fusion, self.turn, sentence)
        return {"parse": parse, "fusion": fusion, "turn": self.turn, "track1": track1,
                "track_p": track_p, "causal": causal, "kb_blocked": kb_blocked,
                "block_tree": {"summary": bt_summary, "context": bt_context},
                "waterwave": ww}


    async def init_persistence(self, save_dir=""):
        """Initialize persistence: restore profile, start auto-save"""
        if self.save_dir or save_dir:
            sd = save_dir or self.save_dir
            self.persistence = PersistenceManager(self, save_dir=sd)
            await self.persistence.restore()
            self.persistence.start_auto_save()
            import logging
            logging.info(f"[Pipeline] Persistence started: {sd}")
        else:
            import logging
            logging.info("[Pipeline] No save_dir, persistence disabled")

    async def set_meta_cog(self, enabled=True):
        if hasattr(self, "_meta_cog"):
            self._meta_cog.enabled = enabled


    def _fire_event(self, event_type, edge_key=None, data=None):
        if edge_key and edge_key in self.graph.edges:
            e = self.graph.edges[edge_key]
            if event_type == "SUCCESS":
                e.weight = min(1.0, e.weight + 0.05)
            elif event_type == "CORRECTION":
                e.weight = max(0.0, e.weight - 0.10)
            elif event_type == "CONSOLIDATE":
                if hasattr(e, 'importance'):
                    e.importance = min(1.0, e.importance + 0.08)
        if self.monitor:
            self.monitor.record("mem_events", event_type, {"edge": str(edge_key)[:20]})

    def _waterwave_activate(self, expand_hops=1) -> dict:

        """Content-aware semantic cascade: tree -> graph -> profile.
        Uses BGE embeddings + cosine similarity. NOT BFS.
        """
        result = {"tree_blocks": 0, "graph_edges": [], "profile_traits": {}}
        if not self.enable_graph or not self.graph:
            return result
        bt = self.block_tree
        if not bt or not bt.current_block_id:
            return result
        current = bt.blocks.get(bt.current_block_id)
        if not current:
            return result
        result["tree_blocks"] = len(bt.blocks)
        # Build query context from current block
        qparts = []
        if current.primary_intent: qparts.append(current.primary_intent)
        for e in getattr(current, "entities", [])[:10]:
            if hasattr(e, "text"): qparts.append(e.text)
            elif isinstance(e, str): qparts.append(e)
        if not qparts: qparts.append(str(getattr(current, "name", "")))
        query_text = " ".join(qparts).lower()
        qtokens = set(query_text.split())
        if not qtokens: return result
        # Try BGE embeddings, fall back to token overlap
        try:
            qvec = EMBEDDER.encode(query_text)
            use_bge = True
        except Exception:
            use_bge = False
        # Layer 2: Semantic search in BehaviorGraph (cosine, not BFS)
        for ek, e in self.graph.edges.items():
            fn = self.graph.nodes.get(e.from_step_id)
            tn = self.graph.nodes.get(e.to_step_id)
            if not fn or not tn: continue
            etext = f"{fn.action_summary} {tn.action_summary}"
            if use_bge:
                if ek not in self._edge_embs:
                    self._edge_embs[ek] = EMBEDDER.encode(etext)
                sim = PROTOTYPES.cosine_sim(qvec, self._edge_embs[ek])
            else:
                etoks = set(etext.lower().split())
                olap = len(qtokens & etoks)
                sim = olap / max(len(qtokens | etoks), 1)
            sim = sim * (1 + min(e.sample_count / 10, 0.5))
            if sim > 0.12:
                result["graph_edges"].append({
                    "key": ek, "weight": round(e.weight, 3),
                    "samples": e.sample_count, "similarity": round(sim, 3),
                    "from": fn.action_summary, "to": tn.action_summary})
        result["graph_edges"].sort(key=lambda x: -x["similarity"])
        result["graph_edges"] = result["graph_edges"][:10]
        # Layer 3: Semantic match to profile traits
        if hasattr(self, "_profile_updater") and self._profile_updater:
            p = self._profile_updater.profile
            for key in list(p.stable_traits.keys()):
                entry = p.stable_traits[key]
                if not isinstance(entry, dict): continue
                matched = []
                for ev in entry.get("evidence", []):
                    et = ev.get("text", "") if isinstance(ev, dict) else str(ev)
                    if len(set(et.lower().split()) & qtokens) > 0:
                        matched.append(et[:120])
                if matched:
                    result["profile_traits"][key] = {"value": entry["value"], "evidence": matched[:3]}
        result["waterwave_count"] = len(result["graph_edges"]) + len(result["profile_traits"])
        return result


    async def _bridge_v32_to_v30(self, parse, fusion, turn, sentence=''):
        """Bridge v3.2 state to v3.0 orchestrator infrastructure.
        Collects and caches v3.2 state for v3.0 back-end processing.
        Currently a placeholder; will feed v3.0 meta-cognitive/
        reflective phases when orchestrator is available."""
        try:
            import time
            state = dict(
                turn=turn,
                stability=getattr(parse, 'stability', 0),
                fusion_confidence=getattr(fusion, 'confidence', 0) if fusion else 0,
                slots=len(getattr(parse, 'slots', {})),
                graph_nodes=len(self.graph.nodes) if self.graph else 0,
                graph_edges=len(self.graph.edges) if self.graph else 0,
                timestamp=time.time(),
            )
            self._bridge_cache[turn] = state
            while len(self._bridge_cache) > 10:
                oldest = min(self._bridge_cache.keys())
                del self._bridge_cache[oldest]
            # Call v3.0 orchestrator if available
            if self._v30_orchestrator:
                try:
                    h = await self._v30_orchestrator.health_check()
                    state["v30_healthy"] = h.get("healthy", False)
                except Exception:
                    state["v30_healthy"] = False
            try:
                if hasattr(self._v30_orchestrator, "update_v32_state"):
                    self._v30_orchestrator.update_v32_state(self.pull_v32_state())
            except Exception:
                pass
            if turn % 3 == 0 and sentence:
                asyncio.create_task(self._run_orchestrator_background(sentence))
        except Exception:
            pass

    def get_bridge_status(self) -> dict:
        return dict(
            enabled=self._bridge_enabled,
            v30_healthy=getattr(self, '_v30_orchestrator', None) is not None,
            orch_ready=self._bridge_cache.get('orchestrator_ready', False),
            orch_result=self._bridge_cache.get('orchestrator_result', {}),
            last_turn=max(self._bridge_cache.keys()) if self._bridge_cache else None,
        )


    async def _run_orchestrator_background(self, sentence):
        try:
            result = await self._v30_orchestrator.process_turn(
                session_id="v32_session",
                user_input=sentence,
            )
            self._bridge_cache["orchestrator_result"] = {
                "answer": str(result.answer)[:200] if result.answer else "",
                "confidence": result.answer_confidence,
                "status": result.status,
            }
            self._bridge_cache["orchestrator_ready"] = True
        except Exception as e:
            import logging
            logging.debug(f"[Bridge] Orchestrator background run failed: {e}")

    async def close(self):
        """Graceful shutdown - save all state"""
        if hasattr(self, '_profile_updater'):
            await self._profile_updater.record_session_end(llm=self.llm)
        if self.persistence:
            self.persistence.close()
        if self.session_recorder:
            self.session_recorder.close()
    def pull_v32_state(self) -> dict:
        """Extract compact v3.2 state for v3.0 orchestration injection."""
        state = {"compiler": {}, "behavior_graph": [], "cognitive_profile": {}, "block_tree": {}}
        if hasattr(self, "_profile_updater") and self._profile_updater:
            p = self._profile_updater.profile
            state["cognitive_profile"] = {
                "metacognition": p.metacognition,
                "confidence": p.confidence,
                "divergence": p.divergence,
                "total_turns": p.total_turns,
            }
        if self.graph and self.graph.edges:
            succ = []
            for ek, e in self.graph.edges.items():
                if not e.is_deprecated and e.sample_count > 0:
                    succ.append({"edge": str(ek)[:30], "weight": round(e.weight, 3), "samples": e.sample_count, "corrections": e.correction_count})
            state["behavior_graph"] = sorted(succ, key=lambda x: -x["weight"])[:5]
        state["block_tree"] = self.block_tree.get_tree_summary() if hasattr(self, "block_tree") else {}
        if hasattr(self, "compiler") and self.compiler:
            state["compiler"] = {"type": type(self.compiler).__name__}
        return state


    def get_status(self):
        return {"turn": self.turn, "graph_nodes": len(self.graph.nodes) if self.enable_graph else 0, "bridge": self.get_bridge_status()}
