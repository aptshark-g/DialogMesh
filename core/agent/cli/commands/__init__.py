"""CLI command modules (P2-P5)."""
from .discourse_cmd import register_cmds as _d
from .pcr_intent_cmd import register_cmds as _p
from .blueprint_cmd import register_cmds as _b
from .subgraph_cmd import register_cmds as _s
from .p3_cmd import register_cmds as _3
from .p4_cmd import register_cmds as _4
from .p5_cmd import register_cmds as _5

def register_all(sp):
    _d(sp); _p(sp); _b(sp); _s(sp); _3(sp); _4(sp); _5(sp)
