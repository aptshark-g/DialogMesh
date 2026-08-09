# -*- coding: utf-8 -*-
"""Persistence package — re-exports the legacy module surface.

Keeps `from core.agent.persistence import CLISessionPersistence, TurnRecord`
working for the v3_common integration bridge and the pcr intent-trace CLI
(previously provided by the single-file module core/agent/persistence.py).
"""
from __future__ import annotations

from core.agent.persistence.cli_middleware import CLISessionPersistence
from core.agent.persistence.models import TurnRecord

__all__ = ["CLISessionPersistence", "TurnRecord"]
