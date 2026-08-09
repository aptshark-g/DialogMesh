"""Association Chain white-box CRUD (A19/P22) — `dm assoc` series.

D-13: full CRUD over association artifacts — L2.5 belief, funnel output,
user-annotated relations, and causal annotations. Everything is inspectable
and editable from the CLI; no runtime behavior is hidden behind black boxes.
"""

import json
import time

from core.agent.cli.engine import get_engine


def _fmt(obj):
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def cmd_assoc(args):
    """Association chain white-box: show/get/add/edit/delete/causal."""
    sub = getattr(args, "subcommand", "show")
    e = get_engine()

    if sub == "show":
        belief = getattr(e, "_l2_5_belief", None)
        funnel = getattr(e, "_association_funnel", None)
        last = getattr(e, "_last_association", None)
        service = getattr(e, "_assoc_service", None)
        out = {
            "components": {
                "l1_extractor": getattr(e, "_l1_extractor", None) is not None,
                "l1_5_qualifier": getattr(e, "_context_qualifier", None) is not None,
                "l2_5_belief": belief is not None,
                "l3_validator": getattr(e, "_l3_validator", None) is not None,
                "funnel": funnel is not None,
                "service": service is not None,
            },
            "service": service.stats() if service is not None else None,
            "last_association": {
                k: (len(v) if isinstance(v, list) else _fmt(v))
                for k, v in (last or {}).items()
            } if last else None,
            "relations": len(getattr(e, "_association_relations", {})),
            "causal_annotations": len(getattr(e, "_association_causal_annotations", [])),
            "blocked_edges": len(getattr(e, "_causal_blocked_edges", [])),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return

    if sub == "get":
        key = getattr(args, "key", "belief")
        if key == "belief" and getattr(e, "_l2_5_belief", None):
            print(json.dumps(e._l2_5_belief.status(), indent=2, ensure_ascii=False, default=str))
        elif key == "last" and getattr(e, "_last_association", None):
            print(json.dumps(e._last_association, indent=2, ensure_ascii=False, default=str))
        elif key == "relations":
            print(json.dumps(getattr(e, "_association_relations", {}), indent=2, ensure_ascii=False, default=str))
        elif key == "causal":
            print(json.dumps(getattr(e, "_association_causal_annotations", []), indent=2, ensure_ascii=False, default=str))
        elif key == "blocked":
            blocked = []
            # Runtime CausalSubstrate instances log HARD_BLOCK decisions.
            for holder in (
                getattr(e, "_causal_substrate_adapter", None),
                getattr(e, "_causal_planner", None),
            ):
                sub = getattr(holder, "_substrate", None)
                if sub is not None:
                    blocked.extend(getattr(sub, "blocked_edges", []) or [])
            print(json.dumps(blocked, indent=2, ensure_ascii=False, default=str))
        elif key == "funnel" and getattr(e, "_association_funnel", None):
            try:
                print(json.dumps(e._association_funnel.run(), indent=2, ensure_ascii=False, default=str))
            except Exception as err:
                print(json.dumps({"error": str(err)}, ensure_ascii=False))
        elif key == "service" and getattr(e, "_assoc_service", None):
            print(json.dumps(e._assoc_service.stats(), indent=2, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"error": f"Unknown key: {key}. Use belief|last|relations|causal|blocked|funnel|service"},
                             ensure_ascii=False))
        return

    if sub == "add":
        subject = getattr(args, "subject", None)
        predicate = getattr(args, "predicate", None)
        obj = getattr(args, "object", None)
        if not subject or not predicate or not obj:
            print(json.dumps({"error": "usage: dm assoc add <subject> <predicate> <object>"}, ensure_ascii=False))
            return
        rels = getattr(e, "_association_relations", None)
        if rels is None:
            rels = {}
            e._association_relations = rels
        rid = f"r{len(rels) + 1}"
        rels[rid] = {
            "id": rid,
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "confidence": float(getattr(args, "confidence", 0.5) or 0.5),
            "source": "user_annotation",
            "ts": time.time(),
        }
        print(json.dumps({"status": "ok", "added": rels[rid]}, indent=2, ensure_ascii=False))
        return

    if sub == "edit":
        rid = getattr(args, "id", None)
        field = getattr(args, "field", None)
        value = getattr(args, "value", None)
        rels = getattr(e, "_association_relations", {})
        if rid not in rels:
            print(json.dumps({"error": f"relation {rid} not found"}, ensure_ascii=False))
            return
        if field not in ("subject", "predicate", "object", "confidence"):
            print(json.dumps({"error": "field must be subject|predicate|object|confidence"}, ensure_ascii=False))
            return
        rels[rid][field] = float(value) if field == "confidence" else value
        rels[rid]["ts"] = time.time()
        print(json.dumps({"status": "ok", "updated": rels[rid]}, indent=2, ensure_ascii=False))
        return

    if sub == "delete":
        rid = getattr(args, "id", None)
        rels = getattr(e, "_association_relations", {})
        if rid in rels:
            removed = rels.pop(rid)
            print(json.dumps({"status": "ok", "removed": removed}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"error": f"relation {rid} not found"}, ensure_ascii=False))
        return

    if sub == "causal":
        csub = getattr(args, "csub", None)
        if csub == "annotate":
            cause = getattr(args, "cause", None)
            effect = getattr(args, "effect", None)
            if not cause or not effect:
                print(json.dumps({"error": "usage: dm assoc causal annotate <cause> <effect>"}, ensure_ascii=False))
                return
            annos = getattr(e, "_association_causal_annotations", None)
            if annos is None:
                annos = []
                e._association_causal_annotations = annos
            entry = {
                "cause": cause,
                "effect": effect,
                "confidence": float(getattr(args, "confidence", 0.9) or 0.9),
                "source": "user_confirm",
                "ts": time.time(),
            }
            annos.append(entry)
            print(json.dumps({"status": "ok", "annotated": entry}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(getattr(e, "_association_causal_annotations", []), indent=2, ensure_ascii=False, default=str))
        return

    print(json.dumps({"error": f"Unknown subcommand {sub}"}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("assoc", help="Association chain white-box (A19)")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    g = sp.add_parser("get"); g.add_argument("key", nargs="?", default="belief")
    a = sp.add_parser("add")
    a.add_argument("subject"); a.add_argument("predicate"); a.add_argument("object")
    a.add_argument("--confidence", default=0.5)
    ed = sp.add_parser("edit")
    ed.add_argument("id"); ed.add_argument("field"); ed.add_argument("value")
    d = sp.add_parser("delete"); d.add_argument("id")
    ca = sp.add_parser("causal")
    cas = ca.add_subparsers(dest="csub")
    an = cas.add_parser("annotate")
    an.add_argument("cause"); an.add_argument("effect")
    an.add_argument("--confidence", default=0.9)
