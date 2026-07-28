"""Blueprint + Decider CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_session


def cmd_blueprint_show(args):
    e = get_engine()
    be = getattr(e, '_planner', None) or getattr(e, '_strategy_engine', None)
    if not be:
        print(json.dumps({"error": "No blueprint/planner loaded"}, ensure_ascii=False))
        return
    # Show DAG if available
    dag = getattr(e, '_last_dag', None)
    if dag:
        nodes = [{"id": nd.id, "label": nd.label if hasattr(nd, 'label') else str(nd),
                    "op": getattr(nd, 'handler', '?')} for nd in dag.nodes]
        edges = [{"from": ed.source, "to": ed.target, "type": getattr(ed, 'type', 'directed')}
                 for ed in dag.edges]
        print(json.dumps({"nodes": len(nodes), "edges": len(edges),
                           "detail": {"nodes": nodes, "edges": edges}}, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"status": "no DAG built yet"}, ensure_ascii=False))


def cmd_blueprint_build(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    e = get_engine()
    be = getattr(e, '_planner', None)
    if be and hasattr(be, 'plan'):
        try:
            result = be.plan(text)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return
        except Exception as err:
            pass
    # Fallback: run on_event to trigger blueprint
    try:
        from core.agent.events.event_ir import DialogAdapter
        adapter = DialogAdapter()
        event = adapter.adapt(text, session_id=get_session(), turn_number=1)
        e.on_event(event)
    except Exception:
        pass
    dag = getattr(e, '_last_dag', None)
    if dag:
        nodes = [{"id": nd.id, "label": getattr(nd, 'label', str(nd))} for nd in dag.nodes]
        print(json.dumps({"dag": nodes}, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"status": "DAG triggered, check engine state"}, ensure_ascii=False))


def cmd_decider_show(args):
    e = get_engine()
    decider = getattr(e, '_decider', None)
    if not decider:
        print(json.dumps({"error": "Decider not loaded"}, ensure_ascii=False))
        return
    info = {"name": type(decider).__name__}
    if hasattr(decider, 'status'):
        info["status"] = decider.status()
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_decider_chains(args):
    e = get_engine()
    # Use registry status to show chain states
    reg = getattr(e, '_registry', None)
    if reg:
        status = reg.status()
        chains = {k: v for k, v in status.items() if not k.startswith("_")}
        print(json.dumps(chains, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No registry"}, ensure_ascii=False))


def cmd_decider_execute(args):
    e = get_engine()
    decider = getattr(e, '_decider', None)
    dag = getattr(e, '_last_dag', None)
    if not dag:
        print(json.dumps({"error": "No DAG to execute. Run 'dm blueprint build <text>' first."}, ensure_ascii=False))
        return
    try:
        result = decider.execute(dag)
        print(json.dumps({"chains_executed": len(result) if isinstance(result, list) else 1}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def register_cmds(subparsers):
    # Blueprint
    p = subparsers.add_parser("blueprint", help="BlueprintEngine operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Show current DAG")
    b = sp.add_parser("build", help="Build DAG from text")
    b.add_argument("text", nargs="+")

    # Decider
    p = subparsers.add_parser("decider", help="Decider operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Decider status")
    sp.add_parser("chains", help="Chain states")
    sp.add_parser("execute", help="Execute current DAG")
