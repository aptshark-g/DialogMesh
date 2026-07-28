"""P2-P3 CLI commands."""
from .discourse_cmd import register_cmds as _discourse
from .pcr_intent_cmd import register_cmds as _pcr_intent
from .blueprint_cmd import register_cmds as _blueprint
from .subgraph_cmd import register_cmds as _subgraph
from .p3_cmd import register_cmds as _p3


def register_all(subparsers):
    _discourse(subparsers)
    _pcr_intent(subparsers)
    _blueprint(subparsers)
    _subgraph(subparsers)
    _p3(subparsers)
