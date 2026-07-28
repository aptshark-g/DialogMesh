"""P2 CLI commands."""
from .discourse_cmd import register_cmds as _discourse
from .pcr_intent_cmd import register_cmds as _pcr_intent

def register_all(subparsers):
    _discourse(subparsers)
    _pcr_intent(subparsers)
