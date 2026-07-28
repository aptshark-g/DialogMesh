"""CLI command modules."""
from .discourse_cmd import register_cmds as _d
from .pcr_intent_cmd import register_cmds as _p
from .blueprint_cmd import register_cmds as _b
from .subgraph_cmd import register_cmds as _s
from .p3_cmd import register_cmds as _p3
from .p4_cmd import register_cmds as _p4

def register_all(sp):
    _d(sp); _p(sp); _b(sp); _s(sp); _p3(sp); _p4(sp)
