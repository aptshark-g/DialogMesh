"""逐 phase 测试 StateMachine pipeline"""
import sys, logging, traceback
logging.disable(logging.CRITICAL)
sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")

import core.agent.cli.engine as eng
eng._engine = None
e = eng._create_engine_instance(provider_config={'type': 'mock'})

from core.agent.event.statemachine import PipelinePhase

sm = e._state_machine
print(f"Registered handlers: {list(sm._phase_handlers.keys())}")
print()

# Test each phase handler individually
ctx = {"text": "auth模块要重构。它用JWT认证。", "session_id": "s1"}
for phase in [PipelinePhase.PCR, PipelinePhase.INTENT, PipelinePhase.DISCOURSE,
              PipelinePhase.BEHAVIOR, PipelinePhase.META, PipelinePhase.PROFILE,
              PipelinePhase.PERSIST]:
    handler = sm._phase_handlers.get(phase)
    if not handler:
        print(f"  {phase.name:<12} ❌ no handler")
        continue
    try:
        result = handler(dict(ctx))
        status = "✅"
        detail = str(result)[:60] if result else ""
    except Exception as ex:
        status = "❌"
        detail = f"{type(ex).__name__}: {str(ex)[:60]}"
    print(f"  {phase.name:<12} {status} {detail}")
