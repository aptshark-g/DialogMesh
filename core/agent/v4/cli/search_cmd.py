"""CLI cross-module search command."""
from __future__ import annotations


def _search(engine, keyword: str, module: str = None):
    """Search across all cognitive modules."""
    results = []

    # Search Observations
    if module in (None, "observations"):
        pool = getattr(engine, '_observation_pool', None) if engine else None
        if pool:
            bundles = pool.get_by_domain("all")
            for b in bundles:
                if keyword.lower() in str(getattr(b, 'summary', str(b))).lower():
                    results.append(("observation", getattr(b, 'bundle_id', '?'), str(getattr(b, 'summary', b))[:80]))

    # Search knowledge
    if module in (None, "knowledge"):
        try:
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in pipe._match_vote._hypotheses.items():
                    if h.status == "frozen" and keyword.lower() in h.statement.lower():
                        results.append(("knowledge", hid, h.statement[:80]))
        except Exception:
            pass

    # Search skills
    if module in (None, "skills"):
        try:
            from core.agent.v4.skill_layer.skill_pool import SkillPool
            pool = SkillPool()
            if hasattr(pool, 'list_all'):
                for s in pool.list_all():
                    name = getattr(s, 'name', str(s))
                    if keyword.lower() in name.lower():
                        results.append(("skill", name, name[:80]))
        except Exception:
            pass

    if not results:
        print(f"No results for: {keyword}")
        return 0

    print(f"Search: {keyword} ({len(results)} results)")
    print(f"{'Type':<15s} {'ID':<25s} {'Summary'}")
    print("-" * 100)
    for typ, rid, summary in results[:20]:
        print(f"{typ:<15s} {rid:<25s} {summary}")
    return 0
