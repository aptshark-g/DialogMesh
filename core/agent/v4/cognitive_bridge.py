"""V4 Cognitive Integration — 6 bridges connecting perception layer to cognition layer.

Bridges:
  1. PCR → OceanProfile   (route→personality modulation)
  2. Behavior → Pattern   (edges→pattern discovery)
  3. Discourse → Memory   (blocks→tagged memory)
  4. L4 → BeliefMap        (transitions→beliefs)
  5. PCR+Discourse+Behavior → Fusion (Track A+B)
  6. Trigger → Metacognition  (events→review)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class V4CognitiveBridge:
    """Connects perception-layer outputs to v4/cognitive modules.

    Usage:
        bridge = V4CognitiveBridge()
        
        # After PCR route:
        ocean_input = bridge.pcr_to_profile(route)
        
        # After behavior update:
        patterns = bridge.behavior_to_pattern(edges)
        
        # Build full fusion context:
        ctx = bridge.build_fusion_context(route, blocks, edges, temporal)
    """

    def __init__(self, ocean_profile=None, pattern_learner=None, 
                 memory_extractor=None, tag_layer=None, belief_map=None,
                 fusion=None, metacognition=None):
        self.ocean = ocean_profile
        self.pattern = pattern_learner
        self.memory = memory_extractor
        self.tags = tag_layer
        self.belief = belief_map
        self.fusion = fusion
        self.meta = metacognition

    # ── Bridge 1: PCR → OceanProfile ──

    def pcr_to_profile(self, route: dict) -> dict:
        """PCR route modulates OCEAN profile weights."""
        zone = route.get("zone", "MIXED")
        x = route.get("x", 0.5)  # cognitive distance
        z = route.get("z", 0.0)  # mood

        adjustments = {}
        if x > 0.7:
            adjustments["openness"] = 0.2      # novel domain → O↑
        if z < -0.3:
            adjustments["neuroticism"] = 0.15   # mirror mood → N↑
        
        return {
            "zone": zone,
            "adjustments": adjustments,
            "trigger_profile_update": bool(adjustments),
        }

    def profile_to_pcr(self, profile: dict, pcr_z: float) -> float:
        """Modulate PCR Z-axis with OCEAN profile."""
        c = profile.get("c", 0.5)  # conscientiousness
        n = profile.get("n", 0.5)  # neuroticism
        
        if c > 0.7:
            return pcr_z + 0.2   # toward PRECISION
        if n > 0.7:
            return pcr_z - 0.3   # toward PSYCHE
        return pcr_z

    # ── Bridge 2: Behavior → Pattern ──

    def behavior_to_pattern(self, edges: list) -> dict:
        """Behavior edges → pattern learner input."""
        unstable = []
        correction_chains = []
        
        for e in edges[-10:]:
            success_rate = getattr(e, 'success_rate', 0.5)
            corrections = getattr(e, 'correction_count', 0)
            
            if success_rate < 0.5 or corrections > 3:
                unstable.append({
                    "from": getattr(e, 'from_step_id', ''),
                    "to": getattr(e, 'to_step_id', ''),
                    "success_rate": round(success_rate, 2),
                    "corrections": corrections,
                })
            
            if corrections >= 2:
                correction_chains.append({
                    "from": getattr(e, 'from_step_id', ''),
                    "to": getattr(e, 'to_step_id', ''),
                    "corrected_count": corrections,
                })
        
        return {
            "unstable_edges": unstable,
            "correction_chains": correction_chains,
            "total_edges": len(edges),
        }

    # ── Bridge 3: Discourse → Memory + Tags ──

    def discourse_to_memory(self, blocks: list, current_turn: int = 0) -> dict:
        """Discourse blocks → tagged memory entries."""
        entries = []
        for b in blocks[-5:]:
            text = getattr(b, 'raw_text', '') or ''
            intent = getattr(b, 'primary_intent', '')
            entities = [getattr(e, 'name', str(e)) for e in getattr(b, 'entities', [])]
            temperature = {"active": 0, "paused": 1, "cold": 2, "frozen": 3}.get(
                getattr(b, 'status', 'active'), 0)
            
            entries.append({
                "text": text[:200],
                "intent": intent,
                "entities": entities[:5],
                "temperature": temperature,
                "turn": getattr(b, 'last_active_turn', current_turn),
            })
        
        return {"entries": entries, "current_turn": current_turn}

    # ── Bridge 4: L4 → BeliefMap ──

    def temporal_to_belief(self, transitions: dict, drift: dict = None) -> dict:
        """L4 transitions + drift → belief map update."""
        beliefs = []
        
        for to_intent, prob in transitions.get("predictions", []):
            beliefs.append({
                "intent": to_intent,
                "confidence": prob,
                "source": "temporal_prediction",
            })
        
        if drift and drift.get("magnitude", 0) > 0.3:
            beliefs.append({
                "intent": "drift_warning",
                "confidence": drift.get("magnitude", 0),
                "source": "intent_drift",
            })
        
        return {"beliefs": beliefs, "trigger_update": len(beliefs) > 0}

    # ── Bridge 5: PCR + Discourse + Behavior → Fusion ──

    def build_fusion_context(self, route: dict = None, blocks: list = None,
                            edges: list = None, temporal: dict = None) -> dict:
        """Build Track A + Track B fusion context for LLM."""
        
        # Track A: dynamic signals (current turn)
        track_a = {
            "cognitive_zone": route.get("zone", "MIXED") if route else "MIXED",
            "intent_prediction": temporal.get("predictions", [])[:2] if temporal else [],
            "discourse_cohesion": self._estimate_cohesion(blocks),
        }
        
        # Track B: prior anchors (historical)
        track_b = {
            "behavior_patterns": self._extract_behavior_patterns(edges),
            "entity_signatures": self._extract_entities(blocks),
        }
        
        return {
            "track_a": track_a,
            "track_b": track_b,
            "fusion_ready": True,
        }

    def _estimate_cohesion(self, blocks: list) -> float:
        if not blocks or len(blocks) < 2:
            return 0.5
        cohesions = [getattr(b, 'cohesion_internal', 0.5) for b in blocks]
        return sum(cohesions) / len(cohesions) if cohesions else 0.5

    def _extract_behavior_patterns(self, edges: list) -> list:
        if not edges:
            return []
        return [
            {"from": getattr(e, 'from_step_id', ''), 
             "to": getattr(e, 'to_step_id', ''),
             "rate": round(getattr(e, 'success_rate', 0.5), 2)}
            for e in edges[-3:]
        ]

    def _extract_entities(self, blocks: list) -> list:
        entities = []
        for b in (blocks or [])[-3:]:
            for e in getattr(b, 'entities', [])[:3]:
                entities.append(getattr(e, 'name', str(e)))
        return list(set(entities))[:10]

    # ── Bridge 6: Trigger → Metacognition ──

    def trigger_to_metacognitive(self, events: list) -> dict:
        """Trigger events → metacognitive review queue."""
        reviews = []
        for event in events:
            action = getattr(event, 'action', '')
            severity = getattr(event, 'severity', 'info')
            message = getattr(event, 'message', '')
            
            # Decision mode based on severity
            if severity == "critical":
                mode = "auto"      # auto-correct
            elif severity == "warning":
                mode = "assisted"  # LLM review
            else:
                mode = "info"      # log only

            reviews.append({
                "action": action,
                "mode": mode,
                "message": message,
            })
        
        return {"reviews": reviews, "trigger_immediate": any(
            r["mode"] in ("auto", "assisted") for r in reviews
        )}
