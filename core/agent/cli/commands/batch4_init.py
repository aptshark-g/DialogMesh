"""Batch 4 auto-injection — overrides p9_cmd placeholders at import time.

This is imported by p9_cmd.py after all functions are defined.
It replaces placeholder handlers with real data functions from batch4_cmd.
"""
import json, os


def _inject():
    """Replace p9_cmd placeholder handlers with batch4 real data handlers."""
    try:
        from core.agent.cli.commands import batch4_cmd as b4
    except ImportError:
        return False

    try:
        from core.agent.cli.commands import p9_cmd as p9
    except ImportError:
        return False

    # Map: (target attribute in p9_cmd) → (function in batch4_cmd)
    overrides = {
        # Profile corrections
        'cmd_profile_correction_add': b4.profile_correction_add,
        'cmd_profile_correction_list': b4.profile_correction_list,
        'cmd_profile_correction_undo': b4.profile_correction_undo,
        'cmd_profile_history': b4.profile_history,
        'cmd_profile_reset': b4.profile_reset,
        # Engineering
        'cmd_engineering_constraint_check': b4.engineering_constraint_check,
        'cmd_engineering_constraint_add': b4.engineering_constraint_add,
        'cmd_engineering_constraint_remove': b4.engineering_constraint_remove,
        'cmd_engineering_constraint_list': b4.engineering_constraint_list,
        'cmd_engineering_propagate': b4.engineering_propagate,
        'cmd_engineering_impact': b4.engineering_impact,
        # Association
        'cmd_assoc_promote': b4.assoc_promote,
        'cmd_assoc_demote': b4.assoc_demote,
        'cmd_assoc_search': b4.assoc_search,
        'cmd_assoc_path': b4.assoc_path,
        # Discourse
        'cmd_discourse_topic_heat': b4.discourse_topic_heat,
        # Context
        'cmd_context_ir_export': b4.context_ir_export,
    }

    count = 0
    for attr, fn in overrides.items():
        if hasattr(p9, attr):
            setattr(p9, attr, fn)
            count += 1

    return count > 0


_injected = False
try:
    _injected = _inject()
except Exception:
    _injected = False
