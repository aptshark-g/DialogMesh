"""Normalizer: standardizes Event IR fields for downstream processing."""
from __future__ import annotations
import time
from typing import Any, Dict

from core.agent.v4.event_ir import EventIR


class Normalizer:
    """Normalizes EventIR fields: timestamp, refs, payload flattening."""

    def normalize(self, event: EventIR) -> Dict[str, Any]:
        return {
            "event_id": event.id,
            "kind": event.kind,
            "timestamp": self._normalize_timestamp(event),
            "flat_payload": self._flatten(event.payload),
            "refs": dict(event.refs),
            "metadata": dict(event.metadata),
        }

    @staticmethod
    def _normalize_timestamp(event: EventIR) -> float:
        ts = event.timestamp
        if ts > 1e12:  # milliseconds → seconds
            ts = ts / 1000.0
        return ts

    @staticmethod
    def _flatten(payload: dict) -> dict:
        """Flatten one level of nesting. Deep nesting stays as-is."""
        flat = {}
        for k, v in payload.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    flat[f"{k}.{sk}"] = sv
            else:
                flat[k] = v
        return flat
