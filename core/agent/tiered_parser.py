"""Tiered parser — archived. Re-export for backward compat."""
try:
    from core.agent.tiered.parser import TieredParser
except ImportError:
    TieredParser = None
