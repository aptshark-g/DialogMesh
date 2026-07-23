"""HNSWIndex: Pure-Python Hierarchical Navigable Small World index.

Approximate nearest neighbor search with O(log n) complexity.
Zero external dependencies — uses only Python stdlib + numpy (already required).

Reference: Malkov & Yashunin, "Efficient and robust approximate nearest neighbor
search using Hierarchical Navigable Small World graphs", 2018.

Usage:
    index = HNSWIndex(dim=384, M=16, ef_construction=200)
    index.add("node1", vector1)
    index.add("node2", vector2)
    index.build()  # finalize
    results = index.search(query_vector, top_k=10)
    # -> [("node1", 0.87), ("node2", 0.72), ...]
"""
from __future__ import annotations
import math, random, json, logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False

logger = logging.getLogger(__name__)


@dataclass
class HNSWNode:
    """A node in the HNSW graph."""
    node_id: str
    vector: Any  # np.ndarray or list
    level: int
    neighbors: Dict[int, List[str]] = field(default_factory=dict)  # level -> [node_id]


class HNSWIndex:
    """Pure-Python HNSW index for approximate nearest neighbor search.

    Args:
        dim: Vector dimension
        M: Max neighbors per node (higher = better recall, more memory)
        ef_construction: Search depth during construction
        ef_search: Search depth during query (can be changed at runtime)
        metric: "cosine" or "euclidean"
    """

    def __init__(self, dim: int, M: int = 16, ef_construction: int = 200,
                 ef_search: int = 64, metric: str = "cosine"):
        self.dim = dim
        self.M = M
        self.M_max = M
        self.M_max0 = M * 2  # level 0 has more connections
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.metric = metric

        self._nodes: Dict[str, HNSWNode] = {}
        self._entry_point: Optional[str] = None
        self._max_level = 0
        self._level_mult = 1.0 / math.log(M)
        self._count = 0
        self._built = False

    # ---- Core: distance computation ----

    def _distance(self, a, b) -> float:
        """Compute distance between two vectors."""
        if HAS_NUMPY and isinstance(a, np.ndarray):
            if self.metric == "cosine":
                a_norm = np.linalg.norm(a)
                b_norm = np.linalg.norm(b)
                if a_norm == 0 or b_norm == 0:
                    return 1.0
                return 1.0 - float(np.dot(a, b) / (a_norm * b_norm))
            else:  # euclidean
                return float(np.linalg.norm(a - b))
        else:
            # Pure Python fallback
            if self.metric == "cosine":
                dot = sum(x * y for x, y in zip(a, b))
                a_norm = math.sqrt(sum(x * x for x in a))
                b_norm = math.sqrt(sum(x * x for x in b))
                if a_norm == 0 or b_norm == 0:
                    return 1.0
                return 1.0 - dot / (a_norm * b_norm)
            else:
                return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def _similarity(self, a, b) -> float:
        """Return similarity score (higher = closer)."""
        if self.metric == "cosine":
            return 1.0 - self._distance(a, b)
        else:
            # Convert euclidean distance to similarity
            dist = self._distance(a, b)
            return 1.0 / (1.0 + dist)

    # ---- Core: random level assignment ----

    def _random_level(self) -> int:
        """Assign random level using exponential distribution."""
        r = random.random()
        level = int(-math.log(r) * self._level_mult)
        return level

    # ---- Core: neighbor selection ----

    def _select_neighbors(self, candidates: List[Tuple[str, float]],
                          M: int) -> List[str]:
        """Select M neighbors from candidates sorted by distance."""
        # Simple heuristic: take closest M
        candidates.sort(key=lambda x: x[1])
        return [node_id for node_id, _ in candidates[:M]]

    # ---- Core: greedy search ----

    def _search_layer(self, query, entry_points: List[str],
                      ef: int, level: int) -> List[Tuple[str, float]]:
        """Greedy beam search in a single layer.

        Returns: list of (node_id, distance) sorted by distance.
        """
        visited = set(entry_points)
        candidates = []
        for ep in entry_points:
            if ep in self._nodes:
                dist = self._distance(query, self._nodes[ep].vector)
                candidates.append((ep, dist))

        # Min-heap by distance (using list + sort)
        candidates.sort(key=lambda x: x[1])
        results = list(candidates)  # Best found so far

        while candidates:
            current_id, current_dist = candidates.pop(0)

            # Check if we can improve
            if len(results) >= ef and current_dist > results[ef - 1][1]:
                break

            node = self._nodes.get(current_id)
            if node is None:
                continue

            for neighbor_id in node.neighbors.get(level, []):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)

                neighbor = self._nodes.get(neighbor_id)
                if neighbor is None:
                    continue

                dist = self._distance(query, neighbor.vector)

                # Add to candidates if promising
                if len(results) < ef or dist < results[-1][1]:
                    candidates.append((neighbor_id, dist))
                    results.append((neighbor_id, dist))
                    results.sort(key=lambda x: x[1])
                    if len(results) > ef:
                        results = results[:ef]
                    candidates.sort(key=lambda x: x[1])

        return results

    # ---- Public API: add ----

    def add(self, node_id: str, vector: Any) -> None:
        """Add a vector to the index. Call build() after all adds."""
        if node_id in self._nodes:
            # Update existing
            self._nodes[node_id].vector = vector
            return

        # Normalize vector for cosine similarity
        if self.metric == "cosine":
            if HAS_NUMPY and isinstance(vector, np.ndarray):
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm
            else:
                norm = math.sqrt(sum(x * x for x in vector))
                if norm > 0:
                    vector = [x / norm for x in vector]

        level = self._random_level()
        node = HNSWNode(node_id=node_id, vector=vector, level=level)

        if self._entry_point is None:
            # First node
            node.neighbors[0] = []
            self._nodes[node_id] = node
            self._entry_point = node_id
            self._max_level = 0
            self._count += 1
            return

        # Find entry point for each level
        ep = self._entry_point
        ep_node = self._nodes[ep]

        # Search from top level down to level+1
        for l in range(self._max_level, level, -1):
            results = self._search_layer(vector, [ep], 1, l)
            if results:
                ep = results[0][0]

        # Add connections from level down to 0
        for l in range(min(level, self._max_level), -1, -1):
            # Search for neighbors at this level
            M_eff = self.M_max0 if l == 0 else self.M_max
            results = self._search_layer(vector, [ep], self.ef_construction, l)

            # Select neighbors
            neighbors = self._select_neighbors(results, M_eff)
            node.neighbors[l] = neighbors

            # Bidirectional connections
            for nid in neighbors:
                neighbor = self._nodes.get(nid)
                if neighbor:
                    if l not in neighbor.neighbors:
                        neighbor.neighbors[l] = []
                    neighbor.neighbors[l].append(node_id)
                    # Trim if too many
                    if len(neighbor.neighbors[l]) > M_eff:
                        # Re-sort and trim — filter out missing nodes
                        valid = []
                        for n in neighbor.neighbors[l]:
                            n_node = self._nodes.get(n)
                            if n_node is not None:
                                valid.append((n, self._distance(n_node.vector, neighbor.vector)))
                        neighbor.neighbors[l] = self._select_neighbors(valid, M_eff)

            if results:
                ep = results[0][0]

        self._nodes[node_id] = node
        if level > self._max_level:
            self._max_level = level
            self._entry_point = node_id
        self._count += 1

    # ---- Public API: build ----

    def build(self) -> None:
        """Finalize the index after all adds."""
        self._built = True
        logger.info("HNSWIndex built: %d nodes, %d levels", self._count, self._max_level + 1)

    # ---- Public API: search ----

    def search(self, query: Any, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search for nearest neighbors.

        Returns: list of (node_id, similarity_score) sorted by score desc.
        """
        if not self._built:
            self.build()

        if self._entry_point is None or self._count == 0:
            return []

        # Normalize query
        if self.metric == "cosine":
            if HAS_NUMPY and isinstance(query, np.ndarray):
                norm = np.linalg.norm(query)
                if norm > 0:
                    query = query / norm
            else:
                norm = math.sqrt(sum(x * x for x in query))
                if norm > 0:
                    query = [x / norm for x in query]

        ep = self._entry_point

        # Search from top level down to level 1
        for l in range(self._max_level, 0, -1):
            results = self._search_layer(query, [ep], 1, l)
            if results:
                ep = results[0][0]

        # Search level 0 with ef_search
        results = self._search_layer(query, [ep], self.ef_search, 0)

        # Return top_k by similarity (not distance)
        scored = [(node_id, self._similarity(query, self._nodes[node_id].vector))
                  for node_id, _ in results[:top_k]
                  if node_id in self._nodes]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ---- Public API: delete ----

    def delete(self, node_id: str) -> bool:
        """Remove a node from the index."""
        if node_id not in self._nodes:
            return False
        node = self._nodes.pop(node_id)
        # Remove from neighbor lists
        for level, neighbors in node.neighbors.items():
            for nid in neighbors:
                if nid in self._nodes and level in self._nodes[nid].neighbors:
                    if node_id in self._nodes[nid].neighbors[level]:
                        self._nodes[nid].neighbors[level].remove(node_id)
        self._count -= 1
        if self._entry_point == node_id:
            # Pick new entry point
            if self._nodes:
                self._entry_point = max(self._nodes.keys(),
                                        key=lambda k: self._nodes[k].level)
            else:
                self._entry_point = None
        return True

    # ---- Public API: stats ----

    @property
    def count(self) -> int:
        return self._count

    def stats(self) -> Dict[str, Any]:
        level_counts = {}
        for node in self._nodes.values():
            level_counts[node.level] = level_counts.get(node.level, 0) + 1
        total_edges = sum(
            len(neighbors)
            for node in self._nodes.values()
            for neighbors in node.neighbors.values()
        )
        return {
            "nodes": self._count,
            "max_level": self._max_level,
            "level_distribution": level_counts,
            "total_edges": total_edges,
            "avg_edges_per_node": total_edges / max(1, self._count),
        }

    # ---- Serialization ----

    def save(self, path: str) -> None:
        """Save index to JSON file."""
        data = {
            "dim": self.dim,
            "M": self.M,
            "ef_construction": self.ef_construction,
            "ef_search": self.ef_search,
            "metric": self.metric,
            "entry_point": self._entry_point,
            "max_level": self._max_level,
            "nodes": {
                nid: {
                    "vector": node.vector.tolist() if HAS_NUMPY and isinstance(node.vector, np.ndarray) else list(node.vector),
                    "level": node.level,
                    "neighbors": node.neighbors,
                }
                for nid, node in self._nodes.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "HNSWIndex":
        """Load index from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        index = cls(
            dim=data["dim"],
            M=data["M"],
            ef_construction=data["ef_construction"],
            ef_search=data["ef_search"],
            metric=data["metric"],
        )
        index._entry_point = data.get("entry_point")
        index._max_level = data.get("max_level", 0)

        for nid, ndata in data["nodes"].items():
            vec = np.array(ndata["vector"]) if HAS_NUMPY else ndata["vector"]
            node = HNSWNode(
                node_id=nid,
                vector=vec,
                level=ndata["level"],
                neighbors={int(k): v for k, v in ndata["neighbors"].items()},
            )
            index._nodes[nid] = node
            index._count += 1

        index._built = True
        return index
