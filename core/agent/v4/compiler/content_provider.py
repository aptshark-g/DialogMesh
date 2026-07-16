"""ContentProvider — storage isolation layer.

Design: docs/v3.0/DESIGN_SEMANTIC_OBJECT.md §3.3
"""
from __future__ import annotations
from typing import Dict, List, Optional
import re


class ContentProvider:
    """Unified content source."""

    def __init__(self, observation_pool=None, semantic_index=None,
                 code_adapter=None, knowledge_space=None, skill_layer=None):
        self._pool = observation_pool
        self._semantic = semantic_index
        self._code = code_adapter
        self._knowledge = knowledge_space
        self._skill = skill_layer

    _CHUNK_RE = re.compile(r'\[chunk\s*\d+\]')
    _DEF_KW = re.compile(r'是|指|负责|定义|定义为|指的是|用于|一种|核心|作用是|is\b|refers to|responsible for|defined as', re.IGNORECASE)

    def query_design(self, path: List[str], pattern: str = None,
                     limit: int = 3, max_chars: int = 500) -> str:
        if self._pool is None:
            return ""
        cp = [re.sub(self._CHUNK_RE, '', s).strip() for s in path if s and not self._CHUNK_RE.match(s.strip())]
        cs = "/".join(cp)
        scored = []
        for d in self._pool.stats().get("by_domain", {}):
            for b in self._pool.get_by_domain(d):
                for obs in getattr(b, "domain_observations", {}).values():
                    for idx, ip in enumerate(getattr(obs, "interpretations", [])):
                        hp = ip.get("heading_path") if isinstance(ip, dict) else getattr(ip, "heading_path", None)
                        if not hp: continue
                        ch = [re.sub(self._CHUNK_RE, '', s).strip() for s in hp if s and not self._CHUNK_RE.match(s.strip())]
                        hk = "/".join(ch)
                        if not hk.endswith(cs) and not all(seg in ch for seg in cp[-2:]):
                            continue
                        s = ip.get("summary", "") if isinstance(ip, dict) else getattr(ip, "summary", "")
                        if not s or len(s) < 20: continue
                        hyp = ip.get("hypothesis", "") if isinstance(ip, dict) else getattr(ip, "hypothesis", "")
                        sc = 0.0
                        if self._DEF_KW.search(s): sc += 3.0
                        if "definition" in hyp: sc += 2.0
                        sl = len(s)
                        if 80 <= sl <= 300: sc += 1.5
                        elif 40 <= sl <= 80: sc += 0.5
                        sc += max(0, 2.0 - idx * 0.5)
                        scored.append((sc, s[:max_chars]))
        scored.sort(key=lambda x: x[0], reverse=True)
        seen = set(); results = []
        for _, s in scored:
            k = s[:80]
            if k not in seen: seen.add(k); results.append(s)
            if len(results) >= limit: break
        return " | ".join(results) if results else ""

    def relation_query(self, source=None, target=None, relation_kind=None, min_confidence=0.0, limit=20):
        if hasattr(self, '_relation_substrate') and self._relation_substrate:
            return self._relation_substrate.query(source=source, target=target, relation_kind=relation_kind, min_confidence=min_confidence, limit=limit)
        return []

    def set_relation_substrate(self, substrate):
        self._relation_substrate = substrate

    def add_behavior_edge(self, source, target):
        if hasattr(self, '_relation_substrate') and self._relation_substrate:
            self._relation_substrate.add_behavior(source, target)

    def code_lookup(self, name: str) -> str:
        if self._pool is None: return ""
        blocks = []
        for d in self._pool.stats().get("by_domain", {}):
            for b in self._pool.get_by_domain(d):
                for obs in getattr(b, "observations", []):
                    raw = getattr(obs, "raw_text", "")
                    if name.lower() in raw.lower() and "```" in raw:
                        for m in re.finditer(r'```(?:python)?\n?([\s\S]*?)```', raw):
                            bl = m.group(1).strip()[:500]
                            if name.lower() in bl.lower(): blocks.append(bl)
                    if len(blocks) >= 2: break
                if blocks: break
            if blocks: break
        if blocks:
            try:
                from core.agent.v4.adapter.code.tree_sitter_extractor import PythonCodeExtractor
                return "[CODE:" + name + "]\n" + PythonCodeExtractor().extract_for_concept(name, blocks)
            except: pass
            return "\n---\n".join(blocks[:2])
        return ""

    def knowledge_lookup(self, name): return ""
    def skill_lookup(self, name): return ""
