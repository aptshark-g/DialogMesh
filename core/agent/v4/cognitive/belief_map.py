"""P2 Modules: Belief Accumulator + Recursive Map.

L2.5 Belief Accumulator: Bayesian sequential update across turns.
  Design: BUSINESS_CHAIN_06 §2.4
  Accumulates weak signals into strong intent via posterior updates.
  5-turn crystallization timeout.

Recursive Map: Hierarchical granularity map for engineering chain.
  Design: BUSINESS_CHAIN_07 §2
  File→Module→System with expandable/collapsible granularity.
  High-coupling regions: expand. Low-coupling: collapse.
"""
from __future__ import annotations
import json, os, time, math, logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ══════════ L2.5 Belief Accumulator ══════════


@dataclass
class BeliefState:
    """Posterior probability for one intent hypothesis."""
    hypothesis: str              # "diagnostic" | "feature_request" | "clarification" | ...
    prior: float = 0.3           # initial P(H)
    posterior: float = 0.3       # updated P(H|E1,...,En)
    evidence_count: int = 0      # number of evidence rounds
    last_updated: float = field(default_factory=time.time)
    locked: bool = False         # true when posterior >= lock_threshold


class BeliefAccumulator:
    """Cross-turn implicit voting engine — Bayesian sequential update.
    
    Each turn's L2 semantic features = one vote.
    Votes accumulate via P(H|E) = P(E|H) * P(H) / P(E).
    
    Lock threshold: 0.85 → intent is confirmed.
    Timeout: 5 turns without lock → force crystallize to max posterior.
    """

    def __init__(self, lock_threshold: float = 0.85, timeout_turns: int = 5,
                 persist_path: str = "data/belief/belief_state.json"):
        self._beliefs: Dict[str, BeliefState] = {}  # session_id → beliefs
        self._lock_threshold = lock_threshold
        self._timeout_turns = timeout_turns
        self._path = persist_path
        self._turn_counter: Dict[str, int] = {}      # session → turns since last lock
        self._load()

    def vote(self, session_id: str, hypothesis: str, 
             p_e_given_h: float,  # P(evidence | hypothesis)
             p_e: float = 0.5):   # P(evidence) — marginal
        """Cast one vote (evidence round) for a hypothesis."""
        key = f"{session_id}:{hypothesis}"
        
        if key not in self._beliefs:
            self._beliefs[key] = BeliefState(hypothesis=hypothesis)
        
        bs = self._beliefs[key]
        if bs.locked: return

        # Bayesian update: P(H|E) = P(E|H) * P(H) / P(E)
        prior = bs.posterior
        p_e = max(p_e, 0.01)  # avoid div by zero
        posterior = (p_e_given_h * prior) / p_e
        posterior = min(0.99, max(0.01, posterior))

        bs.posterior = 0.3 * posterior + 0.7 * bs.posterior  # EMA smoothing
        bs.evidence_count += 1
        bs.last_updated = time.time()

        # Check lock
        if bs.posterior >= self._lock_threshold:
            bs.locked = True
            self._turn_counter[session_id] = 0
            logger.info("Belief locked: %s (posterior=%.3f, evidence=%d)", 
                       hypothesis, bs.posterior, bs.evidence_count)

        self._save()

    def get_locked_intent(self, session_id: str) -> Optional[str]:
        """Get the locked (confirmed) intent for a session."""
        best = None
        best_post = 0
        for key, bs in self._beliefs.items():
            if key.startswith(session_id) and bs.locked and bs.posterior > best_post:
                best = bs.hypothesis
                best_post = bs.posterior
        return best

    def force_crystallize(self, session_id: str) -> Optional[str]:
        """After timeout: pick max posterior hypothesis even if below lock threshold."""
        best_key = None
        best_post = 0
        for key, bs in self._beliefs.items():
            if key.startswith(session_id) and bs.posterior > best_post and not bs.locked:
                best_key = key
                best_post = bs.posterior
        
        if best_key:
            bs = self._beliefs[best_key]
            bs.locked = True
            bs.posterior = max(bs.posterior, 0.5)  # floor at 0.5
            logger.info("Belief crystallized: %s (forced, posterior=%.3f)", 
                       bs.hypothesis, bs.posterior)
            self._save()
            return bs.hypothesis
        return None

    def tick(self, session_id: str):
        """Called each turn. Increments timeout counter."""
        current = self._turn_counter.get(session_id, 0) + 1
        self._turn_counter[session_id] = current
        if current >= self._timeout_turns:
            self.force_crystallize(session_id)

    def reset(self, session_id: str):
        """Reset beliefs for a session."""
        to_delete = [k for k in self._beliefs if k.startswith(session_id)]
        for k in to_delete:
            del self._beliefs[k]
        self._turn_counter.pop(session_id, None)

    def stats(self) -> Dict[str, Any]:
        locked = sum(1 for bs in self._beliefs.values() if bs.locked)
        return {
            "total_hypotheses": len(self._beliefs),
            "locked": locked,
            "avg_evidence": sum(bs.evidence_count for bs in self._beliefs.values()) / max(1, len(self._beliefs)),
            "by_hypothesis": {bs.hypothesis: {"posterior": round(bs.posterior, 3), "locked": bs.locked}
                            for bs in self._beliefs.values()},
        }

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {}
        for k, bs in self._beliefs.items():
            data[k] = {
                "hypothesis": bs.hypothesis, "posterior": bs.posterior,
                "evidence_count": bs.evidence_count, "locked": bs.locked,
                "last_updated": bs.last_updated,
            }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(self._path): return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        for k, d in data.items():
            self._beliefs[k] = BeliefState(
                hypothesis=d["hypothesis"], posterior=d["posterior"],
                evidence_count=d["evidence_count"], locked=d["locked"],
                last_updated=d.get("last_updated", time.time()),
            )


# ══════════ Recursive Map (Engineering Chain) ══════════


@dataclass
class GranularityNode:
    """One node in the recursive map — a code unit at a specific granularity."""
    name: str
    path: str                   # file path
    granularity: int = 1        # 0=leaf(function), 1=module(file), 2=system(dir)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    
    # Binding to engineering chain
    module_constraints: List[str] = field(default_factory=list)  # constraint IDs
    depends_on: List[str] = field(default_factory=list)
    implemented_by: List[str] = field(default_factory=list)
    
    # Granularity control
    expanded: bool = True       # currently expanded or collapsed
    coupling_score: float = 0.5 # 0=isolated, 1=highly coupled
    access_count: int = 0       # how often queried


class RecursiveMap:
    """Hierarchical granularity map for engineering chain.
    
    Levels:
      L0 (function): individual functions/methods
      L1 (file): single source file
      L2 (module): directory of related files
      L3 (system): top-level component
    
    Expanding/collapsing driven by:
      - Coupling score: high → expand (show more detail)
      - Access frequency: often queried → expand
      - User preference: OCEAN C → prefers fine granularity
    """

    def __init__(self, persist_path: str = "data/engineering/recursive_map.json"):
        self._nodes: Dict[str, GranularityNode] = {}
        self._path = persist_path
        self._load()

    def add_node(self, name: str, path: str, granularity: int = 1,
                 parent: str = None) -> GranularityNode:
        """Add a node to the map."""
        node = GranularityNode(name=name, path=path, granularity=granularity, parent=parent)
        self._nodes[name] = node
        if parent and parent in self._nodes:
            self._nodes[parent].children.append(name)
        return node

    def bind_constraint(self, node_name: str, constraint_id: str):
        """Bind an engineering constraint to a node."""
        if node_name in self._nodes:
            self._nodes[node_name].module_constraints.append(constraint_id)

    def bind_dependency(self, node_name: str, depends_on: str):
        """Bind a dependency edge."""
        if node_name in self._nodes:
            self._nodes[node_name].depends_on.append(depends_on)
            # Increase coupling score
            self._nodes[node_name].coupling_score = min(1.0, 
                self._nodes[node_name].coupling_score + 0.1)

    def get_visible_nodes(self, min_granularity: int = 0, 
                          max_coupling: float = 1.0) -> List[GranularityNode]:
        """Get nodes that should be visible based on granularity preference."""
        visible = []
        for n in self._nodes.values():
            if n.granularity >= min_granularity and n.coupling_score <= max_coupling:
                visible.append(n)
        return visible

    def expand(self, node_name: str):
        """Expand a node to show children."""
        if node_name in self._nodes:
            self._nodes[node_name].expanded = True
            self._nodes[node_name].access_count += 1

    def collapse(self, node_name: str):
        """Collapse a node to hide children."""
        if node_name in self._nodes:
            self._nodes[node_name].expanded = False

    def query_context(self, intent: str, max_nodes: int = 20) -> Dict[str, Any]:
        """Get relevant engineering context for an intent."""
        # Simple: return most-accessed + high-coupling nodes
        nodes = sorted(self._nodes.values(), 
                      key=lambda n: n.access_count * 0.4 + n.coupling_score * 0.6, 
                      reverse=True)
        
        result = {"modules": [], "constraints": [], "dependencies": []}
        for n in nodes[:max_nodes]:
            result["modules"].append({
                "name": n.name, "path": n.path, "granularity": n.granularity,
                "coupling": round(n.coupling_score, 2), "expanded": n.expanded,
            })
            result["constraints"].extend(n.module_constraints)
            result["dependencies"].extend(n.depends_on)
        
        return result

    def stats(self) -> Dict[str, Any]:
        by_level = {}
        for n in self._nodes.values():
            lvl = f"L{n.granularity}"
            by_level[lvl] = by_level.get(lvl, 0) + 1
        return {
            "total_nodes": len(self._nodes),
            "by_level": by_level,
            "high_coupling": sum(1 for n in self._nodes.values() if n.coupling_score > 0.7),
            "expanded": sum(1 for n in self._nodes.values() if n.expanded),
        }

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {}
        for name, n in self._nodes.items():
            data[name] = {
                "path": n.path, "granularity": n.granularity,
                "parent": n.parent, "children": n.children,
                "constraints": n.module_constraints,
                "depends_on": n.depends_on,
                "coupling": n.coupling_score, "expanded": n.expanded,
                "access_count": n.access_count,
            }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(self._path): return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        for name, d in data.items():
            self._nodes[name] = GranularityNode(
                name=name, path=d["path"], granularity=d["granularity"],
                parent=d.get("parent"), children=d.get("children", []),
                module_constraints=d.get("constraints", []),
                depends_on=d.get("depends_on", []),
                coupling_score=d.get("coupling", 0.5),
                expanded=d.get("expanded", True),
                access_count=d.get("access_count", 0),
            )
