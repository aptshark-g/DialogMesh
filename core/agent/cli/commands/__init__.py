"""P2 CLI commands — discourse, pcr, intent, context, subgraph, format, graph."""
from .discourse_cmd import register_cmds as _discourse

def register_all(subparsers):
    _discourse(subparsers)
