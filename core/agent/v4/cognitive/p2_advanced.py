"""P2: Causal Promoter + TTL Auto-Clean + Subgraph Cache.

CausalPromoter: L4 temporal pattern → L5 causal (sufficiency + necessity check).
TTLManager: HCWA temperature migration (active→paused→cold→frozen→archive).
SubgraphCache: reuse compiled subgraph contexts when intent hasn't changed.
"""
from __future__ import annotations
import time, hashlib, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ══════════ Causal Promoter (L4 → L5) ══════════

@dataclass
class CausalCandidate:
    id: str
    trigger: str
    effect: str
    temporal_support: int      # co-occurrence count (L4)
    confidence: float
    sufficiency: float = 0.0   # P(effect | trigger)
    necessity: float = 0.0     # P(trigger | effect)
    state: str = "L4"          # L4 | candidate_L5 | L5_verified | rejected


class CausalPromoter:
    """Promote temporal patterns (L4) to causal relations (L5).

    L4 → L5 criteria:
      1. Sufficiency: P(effect | trigger) ≥ 0.8
      2. Necessity: P(trigger | effect) ≥ 0.5
      3. Temporal lag: trigger must precede effect
      4. No confounding: no third variable explains both
    """

    def __init__(self):
        self._candidates: Dict[str, CausalCandidate] = {}
        self._action_history: List[tuple] = []  # (action, ts)

    def record_pair(self, trigger: str, effect: str, ts: float):
        """Record a trigger→effect pair for L4 tracking."""
        self._action_history.append((trigger, ts))
        self._action_history.append((effect, ts + 0.001))
        if len(self._action_history) > 1000:
            self._action_history = self._action_history[-1000:]

    def assess(self, pattern_key: str, trigger: str, effect: str, 
               confidence: float, support: int) -> CausalCandidate:
        """Assess L4→L5 promotion eligibility."""
        cid = f"causal_{pattern_key}"
        
        if cid not in self._candidates:
            self._candidates[cid] = CausalCandidate(
                id=cid, trigger=trigger, effect=effect,
                temporal_support=support, confidence=confidence,
            )
        
        c = self._candidates[cid]
        c.temporal_support = support
        c.confidence = confidence

        # Count trigger and effect occurrences
        trigger_count = sum(1 for a, _ in self._action_history if a == trigger)
        effect_count = sum(1 for a, _ in self._action_history if a == effect)

        if trigger_count > 0:
            c.sufficiency = support / trigger_count
        if effect_count > 0:
            c.necessity = support / effect_count

        # Promotion check
        if (c.sufficiency >= 0.8 and c.necessity >= 0.5 
            and support >= 5 and c.state in ("L4", "candidate_L5")):
            c.state = "candidate_L5"
            logger.info("Causal candidate: %s → %s (suff=%.2f, nec=%.2f)", 
                       trigger, effect, c.sufficiency, c.necessity)

        if (c.sufficiency >= 0.9 and c.necessity >= 0.7 
            and support >= 10 and c.state == "candidate_L5"):
            c.state = "L5_verified"
            logger.info("Causal verified: %s → %s", trigger, effect)

        return c

    def get_L5_verified(self) -> List[CausalCandidate]:
        return [c for c in self._candidates.values() if c.state == "L5_verified"]

    def stats(self) -> Dict:
        return {
            "total": len(self._candidates),
            "L4": sum(1 for c in self._candidates.values() if c.state == "L4"),
            "candidate_L5": sum(1 for c in self._candidates.values() if c.state == "candidate_L5"),
            "L5_verified": sum(1 for c in self._candidates.values() if c.state == "L5_verified"),
        }


# ══════════ TTL Auto-Clean (HCWA) ══════════

class TTLManager:
    """HCWA temperature migration automation.

    Temperature lifecycle:
      active → paused (5min silence)
      paused → cold (30min elapsed)
      cold → frozen (24h elapsed)
      frozen → archived (7d elapsed, metadata only)

    Reference: Flink State TTL
    """

    TEMP_THRESHOLDS = {
        "active": 0,              # immediate
        "paused": 300,           # 5min
        "cold": 1800,            # 30min
        "frozen": 86400,         # 24h
        "archived": 604800,      # 7d
    }

    def __init__(self):
        self._nodes: Dict[str, Dict] = {}  # node_id → {state, last_active, created}

    def register(self, node_id: str, state: str = "active"):
        self._nodes[node_id] = {
            "state": state, "last_active": time.time(), "created": time.time(),
        }

    def touch(self, node_id: str):
        """Mark node as active (user referenced it)."""
        if node_id in self._nodes:
            self._nodes[node_id]["last_active"] = time.time()
            self._nodes[node_id]["state"] = "active"

    def tick(self) -> Dict[str, List[str]]:
        """Migrate temperatures for all nodes. Returns changes."""
        changes = {"promoted": [], "demoted": []}
        now = time.time()

        for nid, info in self._nodes.items():
            elapsed = now - info["last_active"]
            old_state = info["state"]

            if elapsed > self.TEMP_THRESHOLDS["archived"]:
                info["state"] = "archived"
            elif elapsed > self.TEMP_THRESHOLDS["frozen"]:
                info["state"] = "frozen"
            elif elapsed > self.TEMP_THRESHOLDS["cold"]:
                info["state"] = "cold"
            elif elapsed > self.TEMP_THRESHOLDS["paused"]:
                info["state"] = "paused"
            elif info["state"] != "active":
                info["state"] = "active"  # reactivate

            if info["state"] != old_state:
                direction = "demoted" if elapsed > 0 else "promoted"
                changes[direction].append(f"{nid}:{old_state}→{info['state']}")

        return changes

    def get_hot_nodes(self) -> List[str]:
        """Nodes currently in active/paused state."""
        return [nid for nid, info in self._nodes.items() 
                if info["state"] in ("active", "paused")]

    def cleanup_archived(self) -> int:
        """Remove metadata-only archived notes. Returns count cleaned."""
        cleaned = [nid for nid, info in self._nodes.items() 
                   if info["state"] == "archived"]
        for nid in cleaned:
            del self._nodes[nid]
        return len(cleaned)

    def stats(self) -> Dict:
        by_state = {}
        for info in self._nodes.values():
            s = info["state"]
            by_state[s] = by_state.get(s, 0) + 1
        return {"by_state": by_state, "total": len(self._nodes)}


# ══════════ Subgraph Context Cache ══════════

@dataclass
class CachedSubgraph:
    intent_hash: str
    entries: List[Any]
    compiled_at: float
    hit_count: int = 0
    stale: bool = False


class SubgraphCache:
    """Reuse compiled subgraph contexts when intent hasn't changed.

    Cache key: hash(intent + discourse_tree_head_id)
    Invalidation: discourse tree fork, profile change, parameter change.
    """

    def __init__(self, max_age_s: float = 30.0):
        self._cache: Dict[str, CachedSubgraph] = {}
        self._max_age = max_age_s
        self._last_tree_hash = ""
        self._last_profile_hash = ""

    def key(self, intent: str, tree_head: str = "") -> str:
        return hashlib.md5(
            f"{intent}|{tree_head}|{self._last_tree_hash}|{self._last_profile_hash}".encode()
        ).hexdigest()[:12]

    def get(self, intent: str, tree_head: str = "") -> Optional[List[Any]]:
        k = self.key(intent, tree_head)
        entry = self._cache.get(k)
        if not entry: return None
        
        if time.time() - entry.compiled_at > self._max_age:
            entry.stale = True
            return None
        
        if entry.intent_hash != k:
            return None
        
        entry.hit_count += 1
        return entry.entries

    def put(self, intent: str, entries: List[Any], tree_head: str = ""):
        k = self.key(intent, tree_head)
        self._cache[k] = CachedSubgraph(
            intent_hash=k, entries=entries, compiled_at=time.time(),
        )

    def invalidate(self, reason: str = ""):
        """Invalidate all cached subgraphs."""
        self._cache.clear()
        if reason:
            logger.info("Subgraph cache invalidated: %s", reason)

    def update_tree_hash(self, tree_hash: str):
        if tree_hash != self._last_tree_hash:
            self._last_tree_hash = tree_hash

    def update_profile_hash(self, profile_hash: str):
        if profile_hash != self._last_profile_hash:
            self._last_profile_hash = profile_hash

    def stats(self) -> Dict:
        return {
            "size": len(self._cache),
            "hits": sum(e.hit_count for e in self._cache.values()),
            "stale": sum(1 for e in self._cache.values() if e.stale),
        }
