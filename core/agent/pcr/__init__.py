# -*- coding: utf-8 -*-
"""
core/agent/pcr/__init__.py
─────────────────────────
Pre-Cognitive Router (PCR) package entry point.

Exports the public API surface for downstream consumers:
- Data contracts: PCRInput_v1, PCROutput_v1, CognitiveProfile_v1, PCRVersion
- Interface: IPCRRouter, PCRHealthStatus
- Registry: register_pcr, create_pcr, discover_pcr_plugins, list_available_pcr

Usage:
    from core.agent.pcr import PCRInput_v1, IPCRRouter, create_pcr
"""

from core.agent.pcr.datacontract import (
    PCRInput_v1,
    PCROutput_v1,
    CognitiveProfile_v1,
    PCRVersion,
    HistoryEntry,
)

from core.agent.pcr.interface import (
    IPCRRouter,
    PCRHealthStatus,
)

__all__ = [
    # Data contracts
    "PCRInput_v1",
    "PCROutput_v1",
    "CognitiveProfile_v1",
    "PCRVersion",
    "HistoryEntry",
    # Interface
    "IPCRRouter",
    "PCRHealthStatus",
]
