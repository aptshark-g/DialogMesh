"""第一轮粗查 — 引擎启动 + 管线 + 数据落盘 + wiring

目标: 暴露问题面 (不是验证通过, 是找出所有 broken 的地方)
"""
from __future__ import annotations

import sys, os, time, uuid, json
sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")

issues = []
ok = []

# ═══ 1. Engine start ═══
try:
    import core.agent.cli.engine as eng
    eng._engine = None
    e = eng._create_engine_instance(provider_config={'type': 'mock'})
    e._running = True
    ok.append("engine instance created")
except Exception as ex:
    issues.append(f"engine create: {ex}")
    print(json.dumps({"issues": issues}, ensure_ascii=False, indent=2))
    sys.exit(1)

# ═══ 2. StateMachine ═══
sm = getattr(e, '_state_machine', None)
if sm:
    ok.append(f"state_machine: {type(sm).__name__}")
else:
    issues.append("state_machine NOT attached — on_event_sm falls back")

# ═══ 3. SubsystemRegistry ═══
reg = getattr(e, '_registry', None)
if reg:
    ok.append(f"registry: {len(reg._defs)} defs")
    # Find failures
    failed = [name for name, r in reg._results.items() if not r.loaded]
    if failed:
        issues.append(f"registry failed: {failed[:5]}")
else:
    issues.append("registry NOT attached")

# ═══ 4. Phase 1-3 wiring ═══
wiring = {
    '_chunk_store': 'ChunkStore',
    '_semantic_splitter': 'SemanticSplitter',
    '_context_window': 'ContextWindow',
    '_write_gate': 'WriteGate',
    '_pronoun_resolver': 'CorefResolver',
    '_context_qualifier': 'ContextQualifier',
    '_semantic_coref': 'SemanticCoref',
    '_hybrid_coref': 'HybridCoref',
    '_entity_extractor': 'EntityExtractor',
}
for attr, name in wiring.items():
    if hasattr(e, attr) and getattr(e, attr) is not None:
        ok.append(f"wired: {name}")
    else:
        issues.append(f"NOT wired: {name}")

# ═══ 5. Pipeline run (2 turns) ═══
from core.agent.events.event_ir import EventIR
try:
    for i in range(2):
        evt = EventIR(
            id=f'turn_{uuid.uuid4().hex[:8]}',
            kind='user_message',
            payload={'text': f'第{i}轮: auth模块要重构。它用JWT认证。', 'session_id': 's1'},
            metadata={}, timestamp=time.time(), refs={'session_id': 's1'},
        )
        e.on_event_sm(evt)
    ok.append("pipeline ran 2 turns")
except Exception as ex:
    issues.append(f"pipeline: {type(ex).__name__}: {str(ex)[:80]}")

# ═══ 6. HotStore data ═══
hs = getattr(getattr(e, '_storage', None), 'hot', None)
if hs:
    s = hs.stats()
    if s.get('size', 0) > 0:
        ok.append(f"HotStore: {s['size']} keys")
    else:
        issues.append("HotStore EMPTY after 2 turns")
else:
    issues.append("HotStore NOT attached")

# ═══ 7. PCR/Intent outputs ═══
if getattr(e, '_last_pcr', None):
    ok.append("PCR output populated")
else:
    issues.append("_last_pcr empty")
if getattr(e, '_last_intent', None):
    ok.append("Intent output populated")
else:
    issues.append("_last_intent empty")

# ═══ 8. Disk persistence ═══
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
data_dir = os.path.normpath(data_dir)
for fname in ['annotations.json', 'corrections.json', 'discourse_state.json']:
    fp = os.path.join(data_dir, fname)
    if os.path.exists(fp) and os.path.getsize(fp) > 0:
        ok.append(f"disk: {fname} ({os.path.getsize(fp)}B)")
    else:
        issues.append(f"disk: {fname} missing/empty")

# ═══ Report ═══
print(f"\n═══ 第一轮粗查 ═══")
print(f"  ✅ OK ({len(ok)}):")
for line in ok:
    print(f"    {line}")
print(f"\n  ❌ ISSUES ({len(issues)}):")
for line in issues:
    print(f"    {line}")
