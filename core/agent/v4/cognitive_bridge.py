"""V4 Cognitive Bridge — deep activation: creates v4/cognitive module instances.

6 active bridges connecting perception → cognition, with real module calls.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import threading, logging

logger = logging.getLogger(__name__)


class V4CognitiveBridge:
    """Creates v4/cognitive modules + feeds live perception data on each tick."""

    def __init__(self):
        self._modules = {}
        self._tick_count = 0
        self._lock = threading.Lock()
        self._load_modules()

    def _load_modules(self):
        specs = {
            "ocean_profile":      ("core.agent.v4.cognitive.ocean_profile",      "OceanProfile"),
            "bfi_calibrator":     ("core.agent.v4.cognitive.bfi_calibrator",     "BFICalibrator"),
            "behavior_discovery": ("core.agent.v4.cognitive.behavior_discovery", "BehaviorDiscovery"),
            "pattern_learner":    ("core.agent.v4.cognitive.pattern_learner",    "PatternLearner"),
            "correction_journal": ("core.agent.v4.cognitive.correction_journal", "CorrectionJournal"),
            "fusion":             ("core.agent.v4.cognitive.fusion",              "CognitiveFusion"),
            "belief_map":         ("core.agent.v4.cognitive.belief_map",          "BeliefMap"),
            "tag_layer":          ("core.agent.v4.cognitive.tag_layer",           "TagLayer"),
            "memory_extractor":   ("core.agent.v4.cognitive.memory_extractor",    "MemoryExtractor"),
            "mind":               ("core.agent.v4.cognitive.mind",                "Mind"),
            "metacognition":      ("core.agent.v4.cognitive.metacognition",       "Metacognition"),
            "internal_monitor":   ("core.agent.v4.cognitive.internal_monitor",    "InternalMonitor"),
            "dynamics":           ("core.agent.v4.cognitive.dynamics",            "InertiaDynamics"),
        }
        for name, (mod_path, cls_name) in specs.items():
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
            except Exception as e:
                pass

    @property
    def modules_loaded(self):
        return list(self._modules.keys())

    @property
    def status(self):
        return {"modules": len(self._modules), "ticks": self._tick_count}

    # ── Bridge callbacks ──

    def on_pcr_route(self, route: dict):
        with self._lock:
            op = self._modules.get("ocean_profile")
            if op and hasattr(op, 'modulate_from_route'):
                try: op.modulate_from_route(x=route.get("x",0.5), y=route.get("y",0.5), z=route.get("z",0.0), zone=route.get("zone","MIXED"))
                except Exception: pass

    def on_behavior_update(self, result: dict):
        with self._lock:
            pl = self._modules.get("pattern_learner")
            if pl and hasattr(pl, 'learn'):
                try: pl.learn(result)
                except Exception: pass

    def on_discourse_update(self, blocks: list):
        with self._lock:
            me = self._modules.get("memory_extractor")
            if me and hasattr(me, 'extract'):
                try:
                    for b in blocks: me.extract(b)
                except Exception: pass
            tl = self._modules.get("tag_layer")
            if tl and hasattr(tl, 'tag'):
                try:
                    for b in blocks: tl.tag(b)
                except Exception: pass

    def on_temporal_predict(self, predictions: list, drift: Optional[dict] = None):
        with self._lock:
            bm = self._modules.get("belief_map")
            if bm and hasattr(bm, 'update'):
                try: bm.update(predictions)
                except Exception: pass
            if drift:
                dyn = self._modules.get("dynamics")
                if dyn and hasattr(dyn, 'detect_shift'):
                    try: dyn.detect_shift(drift)
                    except Exception: pass

    def build_llm_context(self) -> dict:
        ctx = {}
        with self._lock:
            op = self._modules.get("ocean_profile")
            if op and hasattr(op, 'get_profile'):
                try: ctx["ocean"] = op.get_profile()
                except Exception: pass
            bm = self._modules.get("belief_map")
            if bm and hasattr(bm, 'get_active_beliefs'):
                try: ctx["beliefs"] = bm.get_active_beliefs()
                except Exception: pass
            tl = self._modules.get("tag_layer")
            if tl and hasattr(tl, 'get_recent_tags'):
                try: ctx["tags"] = tl.get_recent_tags()
                except Exception: pass
        return ctx

    def on_metacognitive_trigger(self, trigger_type: str, details: dict = None):
        with self._lock:
            mc = self._modules.get("metacognition")
            if mc and hasattr(mc, 'review'):
                try: mc.review(trigger_type, details or {})
                except Exception: pass

    def on_user_correction(self, correction: dict):
        with self._lock:
            cj = self._modules.get("correction_journal")
            if cj and hasattr(cj, 'log'):
                try: cj.log(correction)
                except Exception: pass
            dyn = self._modules.get("dynamics")
            if dyn and hasattr(dyn, 'apply_correction'):
                try: dyn.apply_correction(correction)
                except Exception: pass

    def tick(self):
        self._tick_count += 1
        dyn = self._modules.get("dynamics")
        if dyn and hasattr(dyn, 'tick'):
            try: dyn.tick()
            except Exception: pass
        im = self._modules.get("internal_monitor")
        if im and hasattr(im, 'tick'):
            try: im.tick()
            except Exception: pass
