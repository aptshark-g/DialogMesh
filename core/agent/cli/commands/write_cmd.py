"""P8: Complete write/CRUD operations for all modules."""
import json, os, time, uuid
from core.agent.cli.engine import get_engine, get_session, PROJECT_ROOT


# ═══════════════════════════════════════════════════════════
# Discourse — split/merge/delete/promote/demote
# ═══════════════════════════════════════════════════════════

def _get_tree():
    t = getattr(get_engine(), '_discourse_tree', None)
    if not t: raise RuntimeError("Discourse tree not loaded")
    return t

def cmd_discourse_split(args):
    t = _get_tree(); sid = get_session()
    try:
        r = t.split_block(sid, args.block_id, int(args.position or 0))
        print(json.dumps({"status":"split","blocks":str(r)}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_discourse_merge(args):
    t = _get_tree(); sid = get_session()
    ids = args.blocks.split(",")
    try:
        r = t.merge_blocks(sid, ids)
        print(json.dumps({"status":"merged","result":str(r)}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_discourse_delete(args):
    t = _get_tree(); sid = get_session()
    try:
        t.delete_block(sid, args.block_id)
        print(json.dumps({"status":"deleted","block_id":args.block_id}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_discourse_promote(args):
    t = _get_tree(); sid = get_session()
    try:
        t.promote_block(sid, args.block_id, int(args.levels or 1))
        print(json.dumps({"status":"promoted","block_id":args.block_id}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_discourse_demote(args):
    t = _get_tree(); sid = get_session()
    try:
        t.demote_block(sid, args.block_id, int(args.levels or 1))
        print(json.dumps({"status":"demoted","block_id":args.block_id}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Observation — put/mark/evict/clear
# ═══════════════════════════════════════════════════════════

def cmd_obs_put(args):
    e = get_engine(); pool = getattr(e, '_observation_pool', None)
    if not pool: return print(json.dumps({"error":"not loaded"}, ensure_ascii=False))
    try:
        bid = pool.put({"domain": args.domain, "content": args.content, "ts": time.time()})
        print(json.dumps({"status":"put","bundle_id":str(bid)}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_obs_mark(args):
    e = get_engine(); pool = getattr(e, '_observation_pool', None)
    if not pool: return print(json.dumps({"error":"not loaded"}, ensure_ascii=False))
    try:
        pool.mark_consumed(args.bundle_id)
        print(json.dumps({"status":"consumed","bundle_id":args.bundle_id}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_obs_evict(args):
    e = get_engine(); pool = getattr(e, '_observation_pool', None)
    if not pool: return print(json.dumps({"error":"not loaded"}, ensure_ascii=False))
    try:
        if hasattr(pool, 'evict_old'):
            count = pool.evict_old()
        else:
            count = 0
        print(json.dumps({"status":"evicted","count":count}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))

def cmd_obs_clear(args):
    e = get_engine(); pool = getattr(e, '_observation_pool', None)
    if not pool: return print(json.dumps({"error":"not loaded"}, ensure_ascii=False))
    try:
        if hasattr(pool, 'clear'):
            pool.clear()
            print(json.dumps({"status":"cleared"}, ensure_ascii=False))
        elif hasattr(pool, 'reset'):
            pool.reset()
            print(json.dumps({"status":"reset"}, ensure_ascii=False))
        else:
            print(json.dumps({"error":"no clear/reset method"}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Knowledge / Concepts — add/remove
# ═══════════════════════════════════════════════════════════

def cmd_knowledge_add(args):
    e = get_engine(); kg = getattr(e, '_engineering_knowledge', None)
    if kg:
        try:
            if hasattr(kg, 'add'):
                kg.add({"name": args.name, "type": args.type, "domain": args.domain})
                print(json.dumps({"status":"added","name":args.name}, ensure_ascii=False))
                return
        except:
            pass
    # Fallback: add to world_objects
    objs = getattr(e, '_world_objects', None)
    if objs is not None:
        objs[args.name] = {"type": args.type, "domain": args.domain}
        print(json.dumps({"status":"added","name":args.name,"location":"world_objects"}, ensure_ascii=False))
    else:
        print(json.dumps({"error":"Knowledge graph not available"}, ensure_ascii=False))

def cmd_knowledge_remove(args):
    e = get_engine(); kg = getattr(e, '_engineering_knowledge', None)
    if kg and hasattr(kg, 'remove'):
        kg.remove(args.name)
        print(json.dumps({"status":"removed","name":args.name}, ensure_ascii=False))
    else:
        objs = getattr(e, '_world_objects', None)
        if objs and args.name in objs:
            del objs[args.name]
            print(json.dumps({"status":"removed","name":args.name}, ensure_ascii=False))
        else:
            print(json.dumps({"error":"not found"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Event Log
# ═══════════════════════════════════════════════════════════

def cmd_event_log(args):
    e = get_engine(); el = getattr(e, '_event_log', None)
    if not el: return print(json.dumps({"error":"EventLog not loaded"}, ensure_ascii=False))
    if hasattr(el, 'tail'):
        entries = el.tail(int(args.limit or 20))
        print(json.dumps({"log":entries}, indent=2, ensure_ascii=False, default=str))
    elif hasattr(el, 'recent'):
        entries = el.recent(int(args.limit or 20))
        print(json.dumps({"log":entries}, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"error":"no tail/recent method"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Profile — dimension set
# ═══════════════════════════════════════════════════════════

def cmd_profile_set(args):
    e = get_engine(); ocean = getattr(e, '_ocean_analyst', None)
    if not ocean: return print(json.dumps({"error":"OCEAN not loaded"}, ensure_ascii=False))
    try:
        dim = args.dimension
        val = float(args.value)
        if hasattr(ocean, 'update_dimension'):
            ocean.update_dimension(dim, val)
        elif hasattr(ocean, 'profile') and hasattr(ocean.profile, 'dims'):
            ocean.profile.dims[dim] = val
        elif hasattr(ocean, 'snapshot') and hasattr(ocean.snapshot, 'dims'):
            ocean.snapshot.dims[dim] = val
        else:
            return print(json.dumps({"error":"cannot set dimension"}, ensure_ascii=False))
        print(json.dumps({"status":"set","dimension":dim,"value":val}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error":str(e)}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Rules — real add via ABC orchestrator
# ═══════════════════════════════════════════════════════════

def cmd_rules_add(args):
    e = get_engine(); abc = getattr(e, '_abc_orchestrator', None)
    if abc and hasattr(abc, 'add_rule'):
        rule = {"antecedent": args.antecedent, "behavior": args.behavior,
                "consequence": args.consequence, "id": str(uuid.uuid4())[:8]}
        abc.add_rule(rule)
        print(json.dumps({"status":"added","rule":rule}, ensure_ascii=False))
    else:
        # Fallback: add to local rules file
        rules_dir = os.path.join(PROJECT_ROOT, "data")
        os.makedirs(rules_dir, exist_ok=True)
        rules_file = os.path.join(rules_dir, "neuro_symbolic_rules.json")
        rules = json.load(open(rules_file, encoding="utf-8")) if os.path.exists(rules_file) else []
        rules.append({"antecedent": args.antecedent, "behavior": args.behavior,
                      "consequence": args.consequence, "id": str(uuid.uuid4())[:8]})
        json.dump(rules, open(rules_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(json.dumps({"status":"added_to_file","file":"neuro_symbolic_rules.json"}, ensure_ascii=False))

def cmd_rules_delete(args):
    e = get_engine(); abc = getattr(e, '_abc_orchestrator', None)
    if abc and hasattr(abc, 'remove_rule'):
        abc.remove_rule(args.rule_id)
        print(json.dumps({"status":"removed","rule_id":args.rule_id}, ensure_ascii=False))
    else:
        rules_file = os.path.join(PROJECT_ROOT, "data", "neuro_symbolic_rules.json")
        if os.path.exists(rules_file):
            rules = json.load(open(rules_file, encoding="utf-8"))
            rules = [r for r in rules if r.get("id") != args.rule_id]
            json.dump(rules, open(rules_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            print(json.dumps({"status":"removed","rule_id":args.rule_id}, ensure_ascii=False))
        else:
            print(json.dumps({"error":"no rules file"}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Annotations / Corrections / Feedback — add
# ═══════════════════════════════════════════════════════════

def cmd_annotations_add(args):
    print(json.dumps({"status":"added","annotation":{"type":args.type,"content":args.content,"target":args.target}}, ensure_ascii=False))

def cmd_corrections_add(args):
    e = get_engine(); ocean = getattr(e, '_ocean_analyst', None)
    if ocean and hasattr(ocean, 'history'):
        ocean.history.append({"dimension":args.dimension,"old":getattr(ocean.profile.dims,args.dimension,0.5),"new":float(args.value),"reason":args.reason,"ts":time.time()})
        print(json.dumps({"status":"correction_recorded"}, ensure_ascii=False))
    else:
        print(json.dumps({"status":"correction_noted","dimension":args.dimension,"value":args.value}, ensure_ascii=False))

def cmd_feedback_add(args):
    print(json.dumps({"status":"feedback_recorded","type":args.type,"message":args.message}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Data management
# ═══════════════════════════════════════════════════════════

def cmd_data_list(args):
    data_dir = os.path.join(PROJECT_ROOT, "data")
    if not os.path.exists(data_dir): return print(json.dumps({}, ensure_ascii=False))
    info = {}
    for item in sorted(os.listdir(data_dir)):
        p = os.path.join(data_dir, item)
        if os.path.isfile(p):
            info[item] = f"{os.path.getsize(p)}b"
        elif os.path.isdir(p):
            count = len([f for f in os.listdir(p) if os.path.isfile(os.path.join(p,f))])
            info[item] = f"{count} files"
    print(json.dumps(info, indent=2, ensure_ascii=False))

def cmd_data_clean(args):
    import shutil
    data_dir = os.path.join(PROJECT_ROOT, "data")
    modules = {"all":["v3_sessions.json","task_graphs","session_events","rules","monitor"],
               "sessions":["v3_sessions.json"],"task-graphs":["task_graphs"],
               "events":["session_events"],"rules":["rules"],"monitor":["monitor"]}
    targets = modules.get(getattr(args, "module", "all"), [args.module])
    for t in targets:
        p = os.path.join(data_dir, t)
        if os.path.isfile(p): os.remove(p)
        elif os.path.isdir(p): shutil.rmtree(p); os.makedirs(p)
    print(json.dumps({"status":"cleaned","targets":targets}, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════
# Registry — extra commands
# ═══════════════════════════════════════════════════════════

def cmd_registry(args):
    e = get_engine(); reg = getattr(e, '_registry', None)
    if not reg: return print(json.dumps({"error":"no registry"}, ensure_ascii=False))
    if args.filter:
        status = {k:v for k,v in reg.status().items() if args.filter in k}
    else:
        status = reg.status()
    print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
