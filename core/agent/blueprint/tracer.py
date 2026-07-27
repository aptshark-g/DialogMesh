# -*- coding: utf-8 -*-
"""PipelineTracer — per-request trace logging for human + Meta analysis.

Writes to data/pipeline_traces.jsonl.
Meta consumes these traces to learn which chains are healthy vs degraded.
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

TRACE_FILE = Path("data/pipeline_traces.jsonl")
_lock = threading.Lock()


class PipelineTracer:
    """Records per-request pipeline execution traces.

    Each trace: {ts, request_id, session_id, intent, strategy, blueprint_nodes,
                 chain_outputs_summary, ticks, llm_reply_snippet, errors, latency_ms}
    """

    @staticmethod
    def record(request_id: str, session_id: str, data: Dict[str, Any]):
        """Write one trace to JSONL file (thread-safe)."""
        trace = {
            "ts": time.time(),
            "request_id": request_id,
            "session_id": session_id[:8] if session_id else "?",
            "intent": data.get("intent", ""),
            "strategy": data.get("strategy", ""),
            "blueprint_nodes": data.get("blueprint_nodes", 0),
            "chain_summary": data.get("chain_summary", {}),
            "ticks": data.get("ticks", 0),
            "llm_reply_snippet": (data.get("llm_reply", "") or "")[:100],
            "errors": data.get("errors", []),
            "latency_ms": data.get("latency_ms", 0),
        }
        with _lock:
            try:
                TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(TRACE_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
            except Exception as e:
                logger.warning("Failed to write trace: %s", e)

    @staticmethod
    def read_last(n: int = 10) -> list:
        """Read the last N traces for debugging."""
        if not TRACE_FILE.exists():
            return []
        with open(TRACE_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        traces = []
        for line in lines[-n:]:
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return traces

    @staticmethod
    def summary() -> dict:
        """Summary for Meta analysis: chain health, avg latency, error rate."""
        traces = PipelineTracer.read_last(50)
        if not traces:
            return {"status": "no_data"}

        avg_latency = sum(t.get("latency_ms", 0) for t in traces) / len(traces)
        error_count = sum(1 for t in traces if t.get("errors"))
        chain_usage = {}
        for t in traces:
            for chain, status in t.get("chain_summary", {}).items():
                if chain not in chain_usage:
                    chain_usage[chain] = {"ok": 0, "empty": 0, "error": 0}
                if status == "ok":
                    chain_usage[chain]["ok"] += 1
                elif status == "empty":
                    chain_usage[chain]["empty"] += 1
                else:
                    chain_usage[chain]["error"] += 1

        return {
            "total_requests": len(traces),
            "avg_latency_ms": avg_latency,
            "error_rate": error_count / len(traces) if traces else 0,
            "chain_health": chain_usage,
        }
