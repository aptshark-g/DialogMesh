"""Monitoring Annotation API — user can annotate any data point.

白盒化 + 学习闭环: 用户对任何监控数据添加注释→LLM深度解读→馈入Mind。

Domain support: trace, ocean, tree, graph, pipeline, relations, abc, mind
Each annotation: timestamp, target, comment, LLM response (async)
"""
import json, os, time, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v6/annotate")
_engine = None
ANNOTATION_PATH = "data/annotations/user_notes.jsonl"


def init(engine):
    global _engine
    _engine = engine
    os.makedirs(os.path.dirname(ANNOTATION_PATH), exist_ok=True)


# ---- Models ----

class AnnotationRequest(BaseModel):
    domain: str = ""              # trace | ocean | tree | graph | pipeline | abc | mind
    target: str = ""              # specific key: "trace.W", "ocean.C", "tree.blk_a1"
    comment: str = ""             # user's observation
    question: str = ""            # user asks LLM to explain
    severity: str = "info"        # info | warn | error (user's assessment)
    tags: list = []               # user-defined tags


# ---- Storage ----

def _save_annotation(entry: dict):
    with open(ANNOTATION_PATH, "a", encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_annotations(domain: str = "", limit: int = 50) -> list:
    if not os.path.exists(ANNOTATION_PATH):
        return []
    entries = []
    with open(ANNOTATION_PATH, encoding='utf-8') as f:
        for line in f:
            try:
                e = json.loads(line)
                if not domain or e.get("domain") == domain:
                    entries.append(e)
            except Exception:
                pass
    return entries[-limit:]


# ---- Endpoints ----

@router.get("")
async def list_annotations(domain: str = "", limit: int = 50):
    """Get user annotations, optionally filtered by domain."""
    return {"annotations": _load_annotations(domain, limit), "total": len(_load_annotations(domain, 9999))}


@router.post("")
async def create_annotation(req: AnnotationRequest):
    """Add user annotation + optionally trigger LLM deep analysis."""
    entry = {
        "ts": time.time(),
        "domain": req.domain,
        "target": req.target,
        "comment": req.comment[:500],
        "question": req.question[:500],
        "severity": req.severity,
        "tags": req.tags,
        "llm_response": None,
    }
    _save_annotation(entry)

    # Journal to correction system
    if _engine:
        journal = getattr(_engine, '_correction_journal', None)
        if journal:
            journal.record(f"note.{req.domain}.{req.target}", "-", req.comment[:200], reason="user_note")

    # LLM deep analysis
    if req.question and _engine and _engine._llm_provider:
        try:
            prompt = _build_analysis_prompt(req)
            from core.agent.llm_providers.base import GenerateRequest
            result = _engine._llm_provider.generate(GenerateRequest(prompt=prompt, max_tokens=500, temperature=0.3))
            text = result.text if hasattr(result, 'text') else str(result)
            entry["llm_response"] = text[:800]
            _save_annotation(entry)  # re-save with LLM response
        except Exception as e:
            entry["llm_response"] = f"LLM analysis failed: {e}"[:200]

    return entry


def _build_analysis_prompt(req: AnnotationRequest) -> str:
    """Build prompt for LLM to analyze user's annotation."""
    # Gather relevant context
    context = {}
    if _engine:
        if req.domain == "trace" and hasattr(_engine, '_trace_v3'):
            m = _engine._trace_v3.meta_analyze()
            context["trace"] = m.get("reason_distribution", {})
        if req.domain == "ocean":
            ocean = getattr(getattr(_engine, '_ocean_analyst', None), 'profile', None)
            if ocean:
                context["ocean"] = ocean.dims
        if req.domain == "abc" and hasattr(_engine, '_abc'):
            context["abc"] = _engine._abc.report()

    return f"""A user has annotated a monitoring data point. Analyze it deeply.

USER ANNOTATION:
  Domain: {req.domain}
  Target: {req.target}
  Comment: {req.comment}
  Question: {req.question}
  Severity: {req.severity}
  Tags: {req.tags}

CURRENT DATA CONTEXT:
{json.dumps(context, ensure_ascii=False, indent=2)[:1000]}

TASKS:
1. Answer the user's question about this data point
2. Explain what this data pattern means in context
3. If severity is "error" or "warn", suggest corrective action
4. Identify hidden correlations the user might have missed
5. Suggest what other data points to check next

Respond in Chinese (中文), be specific and data-driven."""


@router.get("/stats")
async def annotation_stats():
    """Get annotation statistics — counts by domain, severity, trends."""
    entries = _load_annotations("", 99999)
    by_domain = {}
    by_severity = {}
    for e in entries:
        d = e.get("domain", "other")
        s = e.get("severity", "info")
        by_domain[d] = by_domain.get(d, 0) + 1
        by_severity[s] = by_severity.get(s, 0) + 1
    return {
        "total": len(entries),
        "by_domain": by_domain,
        "by_severity": by_severity,
        "with_llm_response": sum(1 for e in entries if e.get("llm_response")),
        "latest": entries[-3:] if entries else [],
    }
