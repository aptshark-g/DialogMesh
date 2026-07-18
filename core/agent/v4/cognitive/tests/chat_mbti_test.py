"""MBTI Chat Test v2 — full persistence + comprehensive monitoring.

Every turn recorded to JSONL. Session end: Mind.save + ABC rules save + Profile snapshot.
Output: data/monitor/chat_<ts>.jsonl + _summary.json + _profile.json
"""
import sys, os, json, time
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter
from core.agent.v4.cognitive.tag_layer import TagAcquisitionEngine
from core.agent.v4.cognitive.monitor_report import MonitorReport
from core.agent.v4.cognitive.ocean_profile import DIMENSIONS

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

def run_chat_test(turns: int = 10):
    ts = int(time.time())
    os.makedirs("data/monitor", exist_ok=True)
    log_path = f"data/monitor/chat_{ts}.jsonl"

    print("=" * 70)
    print("DialogMesh v6 — Chat MBTI Test (Full Persistence)")
    print(f"Log: {log_path}")
    print("=" * 70)

    prov = OpenAIProvider("deepseek", {
        "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
    })
    eng = CognitiveRuntimeEngine(llm_provider=prov)
    eng.start()
    ad = DialogAdapter()
    report = MonitorReport(f"chat_{ts}")

    all_events = []

    for i in range(turns):
        print(f"\n[轮 {i+1}/{turns}] ")
        text = input("> ").strip()
        if text.lower() in ('quit', 'exit', 'q'):
            break
        if not text:
            continue

        response = eng.on_event(ad.adapt(text, "user", i + 1))
        if response:
            print(f"回复: {response[:400]}...")

        # Per-turn snapshot
        m = eng._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})
        abc_rpt = eng._abc.report() if hasattr(eng, '_abc') and eng._abc else {}
        tb = list(getattr(getattr(eng, '_cognitive_profile', None), 'track_b', {}).keys())

        # OCEAN + BFI calibration
        ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
        ocean_dims = ocean.dims if ocean else {}
        ocean_mbti = ocean.to_mbti() if ocean else ""
        cali = getattr(getattr(eng, '_bfi_calibrator', None), '_bfi_history', [])
        last_cali = cali[-1] if cali else {}

        event = {
            "turn": i + 1,
            "timestamp": time.time(),
            "text": text[:200],
            "response_len": len(response) if response else 0,
            "trace_S": rd.get("strengthen", 0),
            "trace_W": rd.get("weaken", 0),
            "trace_R": rd.get("reject", 0),
            "trace_conf": m.get("avg_confidence", 0),
            "abc_hits": abc_rpt.get("by_layer", {}),
            "trackB_tags": tb,
            "ocean_dims": {k: round(v, 2) for k, v in ocean_dims.items()},
            "ocean_mbti": ocean_mbti,
            "bfi10_scores": last_cali.get("bfi_scores", {}),
            "bfi_divergence": last_cali.get("divergence", {}).get("total_divergence", 0),
            "mind_relations": getattr(getattr(eng, '_mind', None), 'stats', lambda: {})().get("active_relations", 0),
            "mind_anchors": getattr(getattr(eng, '_mind', None), 'stats', lambda: {})().get("active_anchors", 0),
        }
        all_events.append(event)

        # Write incrementally
        with open(log_path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ── Session end: save everything ──
    print("\n" + "=" * 70)
    print("Session end — persisting...")
    print("=" * 70)

    # 1. Mind persistence
    if hasattr(eng, '_mind') and eng._mind:
        try:
            stats = eng._mind.stats()
            print(f"  Mind: relations={stats.get('active_relations',0)} "
                  f"anchors={stats.get('active_anchors',0)} "
                  f"rules={stats.get('active_rules',0)}")
        except Exception as e:
            print(f"  Mind save: {e}")

    # 2. ABC rules persistence
    if hasattr(eng, '_abc') and eng._abc:
        try:
            n_new = eng._abc.generate_rules_from_session(eng)
            print(f"  ABC: {n_new} new rules learned from session")
        except Exception as e:
            print(f"  ABC save: {e}")

    # 3. AnnotationStore stats
    if hasattr(eng, '_annotation_store') and eng._annotation_store:
        stats = eng._annotation_store.stats()
        print(f"  AnnotationStore: {stats.get('total_kb',0)}KB in {len(stats.get('namespaces',{}))} namespaces")
        print(f"  Integrity: {'✅' if stats.get('integrity',{}).get('healthy') else '❌'}")

    # 4. Profile snapshot
    profile_path = f"data/monitor/chat_{ts}_profile.json"
    tb = getattr(getattr(eng, '_cognitive_profile', None), 'track_b', {})
    profile_data = {"track_b": {k: (v if isinstance(v,dict) else getattr(v,'name','?')) for k,v in tb.items()},
                    "total_turns": len(all_events)}
    with open(profile_path, "w") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)

    # 5. MonitorReport
    report.collect(eng)
    report.finish()

    # 6. Summary
    summary_path = f"data/monitor/chat_{ts}_summary.json"
    abc_rpt = eng._abc.report() if hasattr(eng, '_abc') and eng._abc else {}
    summary = {
        "session_id": ts,
        "turns": len(all_events),
        "final_trace": {"S": rd.get("strengthen", 0), "W": rd.get("weaken", 0), "R": rd.get("reject", 0)},
        "abc_layers": abc_rpt.get("by_layer", {}),
        "trackB_tags": list(tb.keys()),
        "files": {"log": log_path, "profile": profile_path, "summary": summary_path},
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ── Analysis ──
    print(f"\n{'=' * 70}")
    print("Personality Analysis — OCEAN 10-dimension")
    print(f"{'=' * 70}")
    if hasattr(eng, '_ocean_analyst'):
        p = eng._ocean_analyst.profile
        print(f"  MBTI(approx): {p.to_mbti()}")
        print(f"  Top dimensions:")
        for dim in p.top_dimensions(5):
            v = p.dims[dim]
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            desc = DIMENSIONS.get(dim, dim)
            print(f"    {dim}: {v:.2f} {bar}  {desc[:40]}")
    print(f"\n  STRENGTHEN: {rd.get('strengthen',0)}  WEAKEN: {rd.get('weaken',0)}  REJECT: {rd.get('reject',0)}")

    print(f"\n  输出: {log_path}")
    print(f"  画像: {profile_path}")
    print(f"  摘要: {summary_path}")
    return eng, all_events


if __name__ == "__main__":
    run_chat_test(10)
