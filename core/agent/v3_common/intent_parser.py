"""DEPRECATED: Legacy intent parser moved to un_use/.

Use PCR V2 (core/agent/pcr_router_v2.py) for routing + Association Chain L1→L3 for intent validation.
"""

# Import shim for backward compatibility
try:
    from core.agent.v3_common.un_use.intent_parser import IntentParser
except ImportError:
    IntentParser = None
