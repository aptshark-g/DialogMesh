"""CLI inspect commands — v4 cognitive module status viewers.

All commands are read-only. Each is a thin shell (<20 lines) over
an existing module. Output is text tables and summary views.
"""
from __future__ import annotations
from typing import Optional, List


# ---- v4: observations ----

def _inspect_observations(engine, detail: bool = False, item_id: str = None,
                          page: int = 1, page_size: int = 10):
    """Show observations from the ObservationPool."""
    pool = getattr(engine, '_observation_pool', None)
    if pool is None:
        print("Observation pool not available")
        return 1

    bundles = pool.get_by_domain("all")
    if not bundles:
        print("No observations")
        return 0

    # Single item drill-down
    if item_id:
        for b in bundles:
            if str(getattr(b, 'bundle_id', '')) == item_id:
                _show_observation_detail(b)
                return 0
        print(f"Observation {item_id} not found")
        return 1

    # Paginated summary
    start = (page - 1) * page_size
    end = start + page_size
    shown = list(bundles)[start:end]

    if detail:
        for b in shown:
            _show_observation_detail(b)
            print("-" * 60)
    else:
        print(f"{'ID':<20s} {'Domain':<15s} {'Summary':<50s} {'Time':<8s}")
        print("-" * 95)
        for b in shown:
            bid = str(getattr(b, 'bundle_id', '?'))
            bdomain = str(getattr(b, 'domain', '?'))
            summary = str(getattr(b, 'summary', str(b)))[:50]
            ts = str(getattr(b, 'timestamp', ''))[:8]
            print(f"{bid:<20s} {bdomain:<15s} {summary:<50s} {ts:<8s}")
        total = len(bundles)
        pages = (total + page_size - 1) // page_size
        print(f"Page {page}/{pages} ({len(shown)} of {total} observations)")
    return 0


def _show_observation_detail(b):
    """Show full detail of a single ObservationBundle."""
    bid = getattr(b, 'bundle_id', '?')
    bdomain = getattr(b, 'domain', '?')
    print(f"ID:      {bid}")
    print(f"Domain:  {bdomain}")
    print(f"Summary: {getattr(b, 'summary', 'N/A')}")
    if hasattr(b, 'interpretations'):
        for intr in getattr(b, 'interpretations', []):
            print(f"  Interpretation: {str(intr)[:100]}")
    if hasattr(b, 'evidence'):
        ev = getattr(b, 'evidence', [])
        print(f"  Evidence: {len(ev)} items")


# ---- v4: hypotheses ----

def _inspect_hypotheses(engine, status: str = "all", limit: int = 10):
    """Show active/frozen hypotheses from HypothesisEngine."""
    try:
        from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
        pipe = HypothesisPipeline()
        print(f"{'ID':<20s} {'Statement':<40s} {'Status':<8s} {'Support':<8s} {'Conflict':<9s} {'Stability':<10s}")
        print("-" * 100)
        # Access registered hypotheses
        if hasattr(pipe, '_match_vote'):
            engine_mv = pipe._match_vote
            if hasattr(engine_mv, '_hypotheses'):
                count = 0
                for hid, h in list(engine_mv._hypotheses.items())[:limit]:
                    if status != "all" and h.status != status:
                        continue
                    bs = h.belief_state
                    print(f"{hid:<20s} {h.statement[:40]:<40s} {h.status:<8s} "
                          f"{bs['support']:<8d} {bs['conflict']:<9d} {bs['stability']:<10.2f}")
                    count += 1
                    if count >= limit:
                        break
                if count == 0:
                    print("(no hypotheses)")
                return 0
        print("HypothesisEngine not available")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


# ---- v4: knowledge ----

def _inspect_knowledge(engine, limit: int = 10):
    """Show frozen Knowledge nodes."""
    try:
        from core.agent.v4.hypothesis_engine.decay_resolve import DecayResolveEngine
        d = DecayResolveEngine()
        print(f"{'ID':<20s} {'Domain':<15s} {'Score':<8s}")
        print("-" * 45)
        # DecayResolveEngine tracks knowledge count but not individual nodes
        # Access from the pipeline's match_vote
        from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
        pipe = HypothesisPipeline()
        if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
            count = 0
            for hid, h in pipe._match_vote._hypotheses.items():
                if h.status == "frozen":
                    print(f"{hid:<20s} {h.domain:<15s} {h.belief_score():<8.2f}")
                    count += 1
                    if count >= limit:
                        break
                if count >= limit:
                    break
            if count == 0:
                print("(no frozen knowledge)")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# ---- v4: skills ----

def _inspect_skills(engine, detail: bool = False, item_id: str = None,
                    page: int = 1, page_size: int = 10):
    """Show distilled Skills from SkillPool."""
    try:
        from core.agent.v4.skill_layer.skill_pool import SkillPool
        pool = SkillPool()
        skills = pool.list_all() if hasattr(pool, 'list_all') else []
        if not skills:
            print("No skills")
            return 0

        if item_id:
            for s in skills:
                if getattr(s, 'name', str(s)) == item_id:
                    _show_skill_detail(s)
                    return 0
            print(f"Skill {item_id} not found")
            return 1

        start = (page - 1) * page_size
        shown = skills[start:start + page_size]

        if detail:
            for s in shown:
                _show_skill_detail(s)
                print("-" * 50)
        else:
            print(f"{'Name':<25s} {'Domain':<12s} {'Usage':<6s} {'Status':<10s}")
            print("-" * 55)
            for s in shown:
                name = getattr(s, 'name', str(s))[:25]
                sdomain = getattr(s, 'domain', '?')[:12]
                usage = str(getattr(s, 'usage_count', '?'))[:6]
                sstatus = getattr(s, 'status', '?')[:10]
                print(f"{name:<25s} {sdomain:<12s} {usage:<6s} {sstatus:<10s}")
            pages = (len(skills) + page_size - 1) // page_size
            print(f"Page {page}/{pages} ({len(shown)} of {len(skills)} skills)")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _show_skill_detail(s):
    """Show full detail of a single Skill."""
    print(f"Name:      {getattr(s, 'name', 'N/A')}")
    print(f"Domain:    {getattr(s, 'domain', 'N/A')}")
    print(f"Status:    {getattr(s, 'status', 'N/A')}")
    print(f"Usage:     {getattr(s, 'usage_count', 0)}")
    if hasattr(s, 'trigger'):
        print(f"Trigger:   {s.trigger}")
    if hasattr(s, 'constraints'):
        cons = getattr(s, 'constraints', [])
        print(f"Constraints: {len(cons)} items" if cons else "Constraints: none")
    if hasattr(s, 'procedure'):
        proc = getattr(s, 'procedure', None)
        print(f"Procedure:  {'defined' if proc else 'none'}")


# ---- v4: world ----

def _inspect_world(engine, mode: str = "stats"):
    """Show World Graph stats."""
    world_graph = getattr(engine, '_world_graph', None) if hasattr(engine, '_world_graph') else None
    # Try to get from adapter
    if world_graph is None:
        try:
            from core.agent.v4.adapter.code.adapter import CodeWorldAdapter
        except Exception:
            pass

    if world_graph is None:
        print("World Graph not loaded")
        return 1

    if mode == "stats":
        print(f"Graph: {world_graph.world} ({world_graph.node_count} nodes, {world_graph.edge_count} edges)")
        print(f"Communities: {len(world_graph.communities)}")
        backbone_nodes = sorted(world_graph.backbone.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"Top backbone: {', '.join(f'{k}({v:.2f})' for k,v in backbone_nodes)}")
    elif mode == "community":
        for cid, units in world_graph.communities.items():
            print(f"  {cid}: {len(units)} nodes ({', '.join(units[:3])}...)")
    return 0


# ---- v4: context ----

def _inspect_context(engine):
    """Show last compiled CrossDomainContextIR."""
    ctx = getattr(engine, '_last_context', None)
    if ctx is None:
        print("No context compiled yet")
        return 1

    print(f"Intent: {ctx.intent}")
    print(f"Total entries: {ctx.total_items} ({ctx.total_tokens if hasattr(ctx, 'total_tokens') else '?'} tokens)")

    # Group by source
    if hasattr(ctx, 'items'):
        from collections import Counter
        sources = Counter(i.source for i in ctx.items)
        for src, count in sources.most_common():
            items = [i for i in ctx.items if i.source == src]
            rel_range = f"{min(i.relevance for i in items):.2f}-{max(i.relevance for i in items):.2f}" if items else "?"
            print(f"  [{src:<15s}] {count} items (relevance: {rel_range})")
    elif hasattr(ctx, 'entries'):
        print(f"  Domains: {list(ctx.entries.keys()) if hasattr(ctx, 'entries') else '?'}")
    return 0
