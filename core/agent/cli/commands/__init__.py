"""CLI commands (P2-P6)."""
from .discourse_cmd import register_cmds as _d
from .pcr_intent_cmd import register_cmds as _p
from .blueprint_cmd import register_cmds as _b
from .subgraph_cmd import register_cmds as _s
from .p3_cmd import register_cmds as _3
from .p4_cmd import register_cmds as _4
from .p5_cmd import register_cmds as _5
from .app_cmd import register_cmds as _a
from .storage_cmd import register_cmds as _st
from .assoc_cmd import register_cmds as _assoc
from .behavior_cmd import register_cmds as _bh

def register_all(sp):
    _d(sp); _p(sp); _b(sp); _s(sp); _3(sp); _4(sp); _5(sp); _a(sp)
    _assoc(sp); _bh(sp)
    try:
        _st(sp)  # storage commands (Phase 1-3)
    except Exception:
        pass
