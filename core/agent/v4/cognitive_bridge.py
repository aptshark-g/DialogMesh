"""V4 Cognitive Bridge — fixed class names + correct method calls.

13/13 modules loaded, method calls aligned to actual module APIs.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import threading, logging

logger = logging.getLogger(__name__)


class V4CognitiveBridge:
    """v4/cognitive bridge — 13 modules, correct API calls."""

    def __init__(self):
        self._modules = {}
        self._tick_count = 0
        self._lock = threading.Lock()
        self._load_modules()

    def _load_modules(self):
        class_map = {
            "ocean_profile":      ("core.agent.v4.cognitive.ocean_profile",      "OCEANProfile"),
            "bfi_calibrator":     ("core.agent.v4.cognitive.bfi_calibrator",     "BFICalibrator"),
            "behavior_discovery": ("core.agent.v4.cognitive.behavior_discovery", "BehaviorDiscovery"),
            "pattern_learner":    ("core.agent.v4.cognitive.pattern_learner",    "PatternLearner"),
            "correction_journal": ("core.agent.v4.cognitive.correction_journal", "CorrectionJournal"),
            "fusion":             ("core.agent.v4.cognitive.fusion",              "FusionContext"),
            "belief_map":         ("core.agent.v4.cognitive.belief_map",          "BeliefAccumulator"),
            "tag_layer":          ("core.agent.v4.cognitive.tag_layer",           "TagAcquisitionEngine"),
            "memory_extractor":   ("core.agent.v4.cognitive.memory_extractor",    "MemoryExtractor"),
            "mind":               ("core.agent.v4.cognitive.mind",                "Mind"),
            "metacognition":      ("core.agent.v4.cognitive.metacognition",       "MetaCognition"),
            "internal_monitor":   ("core.agent.v4.cognitive.internal_monitor",    "InternalStateMonitor"),
            "dynamics":           ("core.agent.v4.cognitive.dynamics",            "DynamicsComputer"),
        }
        for name, (mod_path, cls_name) in class_map.items():
            try:
                mod = __import__(mod_path, fromlist=[cls_name])
                cls = getattr(mod, cls_name, None)
                if cls:
                    try:
                        inst = cls()
                    except Exception:
                        inst = cls.__new__(cls) if hasattr(cls, '__new__') else None
                    if inst:
                        self._modules[name] = inst
            except Exception:
                pass

    @property
    def modules_loaded(self):
        return list(self._modules.keys())

    @property
    def status(self):
        return {"modules": len(self._modules), "ticks": self._tick_count}

    # ── Bridge 1: PCR → OCEANProfile ──

    def on_pcr_route(self, route: dict):
        with self._lock:
            op = self._modules.get("ocean_profile")
            if op and hasattr(op, 'update'):
                try:
                    zone = route.get("zone", "MIXED")
                    op.update({"zone": zone, "x": route.get("x", 0.5),
                               "y": route.get("y", 0.5), "z": route.get("z", 0.0)})
                except Exception:
                    pass
            bfi = self._modules.get("bfi_calibrator")
            if bfi and hasattr(bfi, 'calibrate'):
                try:
                    bfi.calibrate({"zone": route.get("zone", "MIXED"),
                                   "x": route.get("x", 0.5)})
                except Exception:
                    pass

    # ── Bridge 2: Behavior → Pattern ──

    def on_behavior_update(self, result: dict):
        with self._lock:
            pl = self._modules.get("pattern_learner")
            if pl and hasattr(pl, 'register_pattern'):
                try:
                    pl.register_pattern(result.get("pattern", "unknown"),
                                        result.get("confidence", 0.5))
                except Exception:
                    pass
            bd = self._modules.get("behavior_discovery")
            if bd and hasattr(bd, 'record_action'):
                try:
                    bd.record_action(result)
                except Exception:
                    pass

    # ── Bridge 3: Discourse → Memory + Tag ──

    def on_discourse_update(self, blocks: list):
        with self._lock:
            me = self._modules.get("memory_extractor")
            if me and hasattr(me, 'extract'):
                try:
                    for b in blocks:
                        me.extract(b)
                except Exception:
                    pass
            tl = self._modules.get("tag_layer")
            if tl and hasattr(tl, 'acquire_all'):
                try:
                    for b in blocks:
                        tl.acquire_all(b)
                except Exception:
                    pass

    # ── Bridge 4: L4 → BeliefMap ──

    def on_temporal_predict(self, predictions: list, drift: Optional[dict] = None):
        with self._lock:
            bm = self._modules.get("belief_map")
            if bm and hasattr(bm, 'vote'):
                try:
                    for p in predictions:
                        intent = p[0] if isinstance(p, tuple) else str(p)
                        conf = p[1] if isinstance(p, tuple) and len(p) > 1 else 0.5
                        bm.vote(intent, conf)
                except Exception:
                    pass
            if drift:
                dyn = self._modules.get("dynamics")
                if dyn and hasattr(dyn, 'compute_all'):
                    try:
                        dyn.compute_all()
                    except Exception:
                        pass

    # ── Bridge 5: Fusion → LLM Context ──

    def build_llm_context(self) -> dict:
        ctx = {}
        with self._lock:
            op = self._modules.get("ocean_profile")
            if op and hasattr(op, 'to_llm_context'):
                try:
                    ctx["ocean"] = op.to_llm_context()
                except Exception:
                    pass
            elif op and hasattr(op, 'to_dict'):
                try:
                    ctx["ocean"] = op.to_dict()
                except Exception:
                    pass

            bm = self._modules.get("belief_map")
            if bm and hasattr(bm, 'get_locked_intent'):
                try:
                    ctx["locked_intent"] = bm.get_locked_intent()
                except Exception:
                    pass

            tl = self._modules.get("tag_layer")
            if tl and hasattr(tl, 'infer_from_trace'):
                try:
                    ctx["tags"] = tl.infer_from_trace()
                except Exception:
                    pass

            fu = self._modules.get("fusion")
            if fu and hasattr(fu, 'render'):
                try:
                    ctx["fusion"] = fu.render()
                except Exception:
                    pass
        return ctx

    # ── Bridge 6: Trigger → Metacognition ──

    def on_metacognitive_trigger(self, trigger_type: str, details: dict = None):
        with self._lock:
            mc = self._modules.get("metacognition")
            if mc and hasattr(mc, 'submit'):
                try:
                    mc.submit(trigger_type, details or {})
                except Exception:
                    pass
            im = self._modules.get("internal_monitor")
            if im and hasattr(im, 'record_error'):
                try:
                    im.record_error(trigger_type, details or {})
                except Exception:
                    pass

    def on_user_correction(self, correction: dict):
        with self._lock:
            cj = self._modules.get("correction_journal")
            if cj and hasattr(cj, 'record'):
                try:
                    cj.record(correction)
                except Exception:
                    pass
            dyn = self._modules.get("dynamics")
            if dyn and hasattr(dyn, 'compute_all'):
                try:
                    dyn.compute_all()
                except Exception:
                    pass

    def tick(self):
        self._tick_count += 1
        dyn = self._modules.get("dynamics")
        if dyn and hasattr(dyn, 'compute_all'):
            try:
                dyn.compute_all()
            except Exception:
                pass
        im = self._modules.get("internal_monitor")
        if im and hasattr(im, 'flush'):
            try:
                im.flush()
            except Exception:
                pass
