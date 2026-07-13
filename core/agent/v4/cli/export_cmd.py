"""CLI export/import commands."""
from __future__ import annotations
import json


def _export_knowledge(engine, output: str = None):
    """Export frozen Knowledge nodes as JSON. If no output path, print to stdout."""
    try:
        from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
        pipe = HypothesisPipeline()
        frozen = []
        if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
            for hid, h in pipe._match_vote._hypotheses.items():
                if h.status == "frozen":
                    frozen.append(h.to_dict() if hasattr(h, 'to_dict') else {
                        "id": hid, "statement": h.statement,
                        "domain": h.domain, "score": h.belief_score(),
                    })
        data = {"type": "knowledge", "count": len(frozen), "items": frozen}
        if output:
            pathlib.Path(output).write_text(json.dumps(data, indent=2), encoding='utf-8')
            print(f"Exported {len(frozen)} knowledge nodes to {output}")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"Export error: {e}")
        return 1


def _export_skills(engine, output: str = None):
    """Export Skills as JSON."""
    try:
        from core.agent.v4.skill_layer.skill_pool import SkillPool
        pool = SkillPool()
        skills = pool.list_all() if hasattr(pool, 'list_all') else []
        items = []
        for s in skills:
            items.append({
                "name": getattr(s, 'name', str(s)),
                "domain": getattr(s, 'domain', ''),
                "status": getattr(s, 'status', ''),
                "usage": getattr(s, 'usage_count', 0),
            })
        data = {"type": "skills", "count": len(items), "items": items}
        if output:
            pathlib.Path(output).write_text(json.dumps(data, indent=2), encoding='utf-8')
            print(f"Exported {len(items)} skills to {output}")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"Export error: {e}")
        return 1
