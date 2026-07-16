"""SubgraphCompiler — priority-based water-wave subgraph expansion.

Design ref: docs/v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md §4.4

Implements the full Context Compiler subgraph algorithm:
  1. Find seed nodes via keyword + semantic match
  2. k-hop water-wave expansion along typed edges by priority:
     reason > depends > creates > updates > constrains > references > co_occurs
  3. Activation count filtering + relevance scoring
  4. Structured Context IR with sections and cross-references
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.v4.context.source import ContextItem
from core.agent.v4.context.graph_source import ConceptGraph

logger = logging.getLogger(__name__)

# Edge type priority weights (higher = expanded first)
_EDGE_PRIORITY: Dict[str, float] = {
    "reason": 1.0,
    "depends_on": 0.9,
    "corrects": 0.85,
    "creates": 0.8,
    "updates": 0.7,
    "constrains": 0.65,
    "extends": 0.6,
    "imports": 0.5,
    "calls": 0.45,
    "references": 0.4,
    "implements": 0.35,
    "tests": 0.3,
    "co_occurs": 0.2,
    "leads_to": 0.55,
}


class SubgraphResult:
    """Result of subgraph compilation."""
    def __init__(self):
        self.nodes: Dict[str, dict] = {}     # node_name -> node_data
        self.edges: List[dict] = []          # [{source, target, type, weight, hop}]
        self.sections: Dict[str, List[str]] = {
            "topic": [], "reasoning": [], "constraints": [], "history": [], "profile": [],
        }
        self.total_tokens: int = 0
        self.seed_concepts: List[str] = []


class SubgraphCompiler:
    """Priority-based water-wave subgraph expansion from concept graph.

    Usage:
        compiler = SubgraphCompiler(content_index)
        result = compiler.compile("什么是 Context Compiler", max_tokens=500)
    """

    def __init__(self, graph: ConceptGraph = None, observation_pool=None):
        self._graph = graph
        self._pool = observation_pool

    def compile(self, query: str, max_tokens: int = 500,
                max_hops: int = 2, max_nodes: int = 20) -> SubgraphResult:
        """Full subgraph compilation pipeline."""
        result = SubgraphResult()

        if self._graph is None or not self._graph._built:
            return result

        # Step 1: Find seed concepts
        seeds = self._graph.find_seeds(query, top_k=4)
        if not seeds:
            return result
        result.seed_concepts = [s[0] for s in seeds]

        # Step 2: Priority-based water-wave expansion (not uniform BFS)
        node_set, edge_list = self._water_wave_expand(
            seeds, max_hops=max_hops, max_nodes=max_nodes)

        # Step 3: Activation count filtering
        node_set = self._filter_by_activation(node_set, edge_list)

        # Step 4: Assign nodes to Context IR sections
        sections = self._assign_sections(node_set, edge_list, query)

        # Step 5: Compile entries with cross-references
        entries, total_tokens = self._compile_entries(
            node_set, edge_list, sections, max_tokens)

        result.nodes = {n: self._graph._nodes.get(n, {}) for n in node_set}
        result.edges = edge_list
        result.sections = sections
        result.total_tokens = total_tokens
        return result

    def to_context_items(self, result: SubgraphResult, top_k: int = 15) -> List[ContextItem]:
        """Convert SubgraphResult to ContextItems for the assembler."""
        items = []
        seed_set = set(result.seed_concepts)

        for node_name, node in result.nodes.items():
            if not node:
                continue

            # Build rich context per concept
            parts = []
            # Assign section header
            section = self._classify_node_section(node_name, node, result.edges)
            parts.append(f"[{section.upper()}] {node_name}")

            for obs in node.get("observations", [])[:3]:
                parts.append(f"  {obs[:250]}")

            docs = list(node.get("docs", []))[:3]
            if docs:
                parts.append(f"  Sources: {', '.join(docs)}")

            # Cross-references to related concepts
            related = []
            for e in result.edges:
                if e["source"] == node_name and e["target"] in result.nodes:
                    related.append(f"→ {e['type']} {e['target']}")
                elif e["target"] == node_name and e["source"] in result.nodes:
                    related.append(f"← {e['type']} {e['source']}")
            if related:
                # Cap to top 8 by edge weight
                related.sort(key=lambda x: self._rel_weight(x), reverse=True)
                parts.append(f"  Relations: {'; '.join(related[:8])}")

            # Relevance score
            is_seed = node_name in seed_set
            degree = len(node.get("relations", []))
            edge_count = sum(1 for e in result.edges
                           if e["source"] == node_name or e["target"] == node_name)
            relevance = 0.8 if is_seed else min(1.0, 0.3 + edge_count * 0.1)

            items.append(ContextItem(
                source="graph",
                content={"concept": node_name},
                text="\n".join(parts),
                relevance=relevance,
            ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    # ---- Internal ----

    def _water_wave_expand(self, seeds: List[Tuple[str, float]],
                           max_hops: int, max_nodes: int
                           ) -> Tuple[Set[str], List[dict]]:
        """Priority-based k-hop water-wave expansion.

        Not uniform BFS. At each hop:
          - reason edges expanded first (weight 1.0)
          - depends edges next (weight 0.9)
          - co_occurs edges last (weight 0.2)
        Higher priority edges reach further hops.
        """
        visited: Set[str] = set()
        edges: List[dict] = []
        seed_names = [s[0] for s in seeds]

        # Multi-level frontier: each priority level expands independently
        frontiers: Dict[float, Set[str]] = {}
        for name in seed_names:
            if name in self._graph._nodes:
                visited.add(name)
                # Seed nodes go into highest priority frontier
                frontiers.setdefault(1.0, set()).add(name)

        for hop in range(max_hops):
            next_frontiers: Dict[float, Set[str]] = {}
            # Process frontiers from highest to lowest priority
            for priority in sorted(frontiers.keys(), reverse=True):
                for node_name in frontiers[priority]:
                    if node_name not in self._graph._nodes:
                        continue
                    for rel in self._graph._nodes[node_name].get("relations", []):
                        target = rel["target"]
                        rel_type = rel.get("type", "co_occurs")
                        edge_weight = _EDGE_PRIORITY.get(rel_type, 0.2)

                        # Only expand if edge priority >= current hop threshold
                        hop_threshold = 1.0 - hop * 0.3
                        if edge_weight < hop_threshold and rel_type != "co_occurs":
                            continue

                        edges.append({
                            "source": node_name, "target": target,
                            "type": rel_type, "weight": edge_weight,
                            "hop": hop,
                        })

                        if target not in visited:
                            visited.add(target)
                            next_frontiers.setdefault(edge_weight, set()).add(target)

                        if len(visited) >= max_nodes:
                            break
                    if len(visited) >= max_nodes:
                        break
                if len(visited) >= max_nodes:
                    break

            frontiers = next_frontiers
            if not frontiers or len(visited) >= max_nodes:
                break

        return visited, edges

    def _filter_by_activation(self, node_set: Set[str],
                               edge_list: List[dict]) -> Set[str]:
        """Filter nodes by activation: keep nodes with sufficient connections."""
        # Count edge participation
        activation: Dict[str, int] = {}
        for e in edge_list:
            activation[e["source"]] = activation.get(e["source"], 0) + 1
            activation[e["target"]] = activation.get(e["target"], 0) + 1

        # Keep nodes with at least 2 edges, or seed nodes
        seed_set = set(getattr(self, '_last_seeds', []))
        return {
            n for n in node_set
            if n in seed_set or activation.get(n, 0) >= 1
        }

    def _assign_sections(self, node_set: Set[str], edge_list: List[dict],
                          query: str) -> Dict[str, List[str]]:
        """Assign concepts to Context IR sections based on edge types and content."""
        sections: Dict[str, List[str]] = {
            "topic": [], "reasoning": [], "constraints": [], "history": [], "profile": [],
        }

        for node_name in node_set:
            if node_name not in self._graph._nodes:
                continue
            node = self._graph._nodes[node_name]
            relations = node.get("relations", [])

            # Classify by relation types
            rel_types = {r.get("type", "") for r in relations}
            if "reason" in rel_types or "depends_on" in rel_types:
                sections["reasoning"].append(node_name)
            elif "constrains" in rel_types or "corrects" in rel_types:
                sections["constraints"].append(node_name)
            else:
                # Default: topic area
                sections["topic"].append(node_name)

        return sections

    def _compile_entries(self, node_set: Set[str], edge_list: List[dict],
                          sections: Dict[str, List[str]], max_tokens: int
                          ) -> Tuple[List[dict], int]:
        """Compile structured entries with cross-references."""
        entries = []
        total = 0
        # Allocate budget per section
        section_budgets = {
            "topic": int(max_tokens * 0.25),
            "reasoning": int(max_tokens * 0.40),
            "constraints": int(max_tokens * 0.20),
            "history": int(max_tokens * 0.10),
            "profile": int(max_tokens * 0.05),
        }

        for section_name, concept_names in sections.items():
            budget = section_budgets.get(section_name, 50)
            section_tokens = 0
            for name in concept_names:
                if name not in self._graph._nodes or section_tokens >= budget:
                    break
                node = self._graph._nodes[name]

                # Build cross-refs: edges where this concept is source or target
                cross_refs = []
                for e in edge_list:
                    if e["source"] == name and e["target"] in node_set:
                        cross_refs.append({
                            "target_domain": e.get("type", "related"),
                            "target_concept": e["target"],
                            "note": f"hop={e.get('hop', 0)}",
                        })

                content_parts = [f"[{section_name.upper()}] {name}"]
                for obs in node.get("observations", [])[:2]:
                    content_parts.append(obs[:200])

                content = "\n".join(content_parts)
                tokens = len(content) // 4
                if section_tokens + tokens > budget:
                    content = content[:budget - section_tokens]
                    tokens = len(content) // 4

                entries.append({
                    "section": section_name,
                    "concept": name,
                    "content": content,
                    "cross_refs": cross_refs[:5],
                    "tokens": tokens,
                })
                section_tokens += tokens
                total += tokens

        return entries, total

    @staticmethod
    def _classify_node_section(name: str, node: dict, edges: List[dict]) -> str:
        """Classify a single node into a section."""
        rel_types = {r.get("type", "") for r in node.get("relations", [])}
        if "reason" in rel_types or "depends_on" in rel_types:
            return "reasoning"
        if "constrains" in rel_types or "corrects" in rel_types:
            return "constraints"
        return "topic"

    @staticmethod
    def _rel_weight(rel_str: str) -> float:
        """Extract weight from relation string for sorting."""
        for etype, weight in sorted(_EDGE_PRIORITY.items(), key=lambda x: x[1], reverse=True):
            if etype in rel_str:
                return weight
        return 0.0
