"""管线验证 — StateMachine 8 phases + 数据落盘"""
import sys, time, uuid
sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")

t0 = time.time()
import core.agent.cli.engine as eng
eng._engine = None
e = eng._create_engine_instance(provider_config={'type': 'mock'})
print(f"[{time.time()-t0:.1f}s] engine: {sum(1 for r in e._registry._results.values() if r.loaded)}/38 subs")
print(f"[{time.time()-t0:.1f}s] state_machine: {type(getattr(e,'_state_machine',None)).__name__}")

from core.agent.events.event_ir import EventIR
t1 = time.time()
for i in range(3):
    evt = EventIR(
        id=f'turn_{uuid.uuid4().hex[:8]}',
        kind='user_message',
        payload={'text': f'第{i}轮: auth模块要重构。它用JWT认证。', 'session_id': 's1'},
        metadata={}, timestamp=time.time(), refs={'session_id': 's1'},
    )
    result = e.on_event_sm(evt)
print(f"[{time.time()-t1:.1f}s] 3 turns pipeline done")

# Outputs
print(f"  _last_pcr:     {'✅' if getattr(e,'_last_pcr',None) else '❌'}")
print(f"  _last_intent:  {'✅' if getattr(e,'_last_intent',None) else '❌'}")
hs = getattr(getattr(e, '_storage', None), 'hot', None)
if hs:
    print(f"  HotStore:      {hs.stats()}")
else:
    print(f"  HotStore:      ❌ not attached")

# Wiring check
for attr, name in [('_chunk_store','ChunkStore'), ('_pronoun_resolver','Coref'),
                   ('_context_qualifier','Qualifier'), ('_entity_extractor','EntityExt'),
                   ('_semantic_coref','SemCoref'), ('_hybrid_coref','Hybrid')]:
    print(f"  {name:<14} {'✅' if getattr(e, attr, None) else '❌'}")
