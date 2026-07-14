"""DialogMesh v4 TUI — Dual-mode data source (API + Offline).

Auto-detects connectivity:
  1. Try API (localhost:8000) first
  2. If API unavailable, fall back to direct engine import
  3. If engine unavailable, show degraded state

Usage:
    from tools.tui.data_source import DataSource

    ds = DataSource()           # auto-detect
    ds = DataSource("api")      # force API mode
    ds = DataSource("offline")  # force offline mode

    status = ds.get_status()
    obs = ds.get_observations(limit=15)
"""
from __future__ import annotations
import time, os, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DataResult:
    """Unified result wrapper — both modes return this."""
    ok: bool
    data: Any = None
    error: str = ""
    mode: str = "unknown"   # "api" | "offline" | "none"


class DataSource:
    """Dual-mode data source: API first, offline fallback.

    Mode detection happens at first call, then cached.
    Call refresh_mode() to re-detect (e.g. after network change).
    """

    def __init__(self, mode: Optional[str] = None,
                 api_url: str = "http://localhost:8000",
                 api_timeout: float = 2.0):
        """Args:
            mode: "api" | "offline" | None (auto-detect)
            api_url: REST API base URL
            api_timeout: health check timeout (seconds)
        """
        self._forced_mode = mode
        self._api_url = api_url
        self._api_timeout = api_timeout
        self._mode: Optional[str] = None
        self._client: Optional[Any] = None
        self._engine: Optional[Any] = None
        self._last_error: str = ""

    # ---- Mode management ----

    @property
    def mode(self) -> str:
        """Current mode: 'api' | 'offline' | 'none'."""
        if self._mode is None:
            self._detect_mode()
        return self._mode or "none"

    def refresh_mode(self) -> str:
        """Re-detect mode. Call after network/engine state changes."""
        self._mode = None
        self._client = None
        self._engine = None
        return self.mode

    def _detect_mode(self):
        """Auto-detect best available mode."""
        if self._forced_mode:
            self._mode = self._forced_mode
            return

        # 1. Try API
        if self._api_available():
            self._mode = "api"
            logger.info("DataSource: API mode (localhost:8000)")
            return

        # 2. Try offline (direct engine import)
        if self._offline_available():
            self._mode = "offline"
            logger.info("DataSource: Offline mode (direct engine)")
            return

        # 3. Nothing available
        self._mode = "none"
        logger.warning("DataSource: No data source available")

    def _api_available(self) -> bool:
        """Quick health check to API."""
        try:
            import urllib.request
            url = self._api_url + "/v4/health"
            with urllib.request.urlopen(url, timeout=self._api_timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _offline_available(self) -> bool:
        """Check if engine module is importable and has instance."""
        try:
            import core.agent.v4.cli.main as cm
            return cm._engine is not None
        except Exception:
            return False

    def _get_client(self):
        """Lazy-init API client."""
        if self._client is None:
            from tools.api_client.client import DialogMeshClient
            self._client = DialogMeshClient(self._api_url, timeout=int(self._api_timeout))
        return self._client

    def _get_engine(self):
        """Lazy-get engine instance."""
        if self._engine is None:
            import core.agent.v4.cli.main as cm
            self._engine = cm._engine
        return self._engine

    # ---- Unified API ----

    def get_status(self) -> DataResult:
        """Get runtime status."""
        m = self.mode
        if m == "api":
            return self._api_status()
        elif m == "offline":
            return self._offline_status()
        return DataResult(ok=False, error="No data source available", mode="none")

    def get_observations(self, limit: int = 15) -> DataResult:
        if self.mode == "api":
            return self._api_observations(limit)
        elif self.mode == "offline":
            return self._offline_observations(limit)
        return DataResult(ok=False, error="No data source", mode="none")

    def get_hypotheses(self, limit: int = 15, status: str = "active") -> DataResult:
        if self.mode == "api":
            return self._api_hypotheses(limit, status)
        elif self.mode == "offline":
            return self._offline_hypotheses(limit, status)
        return DataResult(ok=False, error="No data source", mode="none")

    def get_knowledge(self, limit: int = 15) -> DataResult:
        if self.mode == "api":
            return self._api_knowledge(limit)
        elif self.mode == "offline":
            return self._offline_knowledge(limit)
        return DataResult(ok=False, error="No data source", mode="none")

    def get_skills(self, limit: int = 15) -> DataResult:
        if self.mode == "api":
            return self._api_skills(limit)
        elif self.mode == "offline":
            return self._offline_skills(limit)
        return DataResult(ok=False, error="No data source", mode="none")

    def get_world(self) -> DataResult:
        if self.mode == "api":
            return self._api_world()
        elif self.mode == "offline":
            return self._offline_world()
        return DataResult(ok=False, error="No data source", mode="none")

    def get_context(self) -> DataResult:
        if self.mode == "api":
            return self._api_context()
        elif self.mode == "offline":
            return self._offline_context()
        return DataResult(ok=False, error="No data source", mode="none")

    def get_events(self, limit: int = 20) -> DataResult:
        if self.mode == "api":
            return self._api_events(limit)
        elif self.mode == "offline":
            return self._offline_events(limit)
        return DataResult(ok=False, error="No data source", mode="none")

    # ---- API implementations ----

    def _api_status(self) -> DataResult:
        c = self._get_client()
        r = c.get_status()
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_observations(self, limit: int) -> DataResult:
        c = self._get_client()
        r = c.inspect("observations", limit=limit)
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_hypotheses(self, limit: int, status: str) -> DataResult:
        c = self._get_client()
        r = c.inspect("hypotheses", limit=limit)
        # Filter by status if needed
        if r.ok and r.data and status != "all":
            items = r.data if isinstance(r.data, list) else []
            # API returns structured data; filtering depends on response shape
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_knowledge(self, limit: int) -> DataResult:
        c = self._get_client()
        r = c.inspect("knowledge", limit=limit)
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_skills(self, limit: int) -> DataResult:
        c = self._get_client()
        r = c.inspect("skills", limit=limit)
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_world(self) -> DataResult:
        c = self._get_client()
        r = c.inspect("world")
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_context(self) -> DataResult:
        c = self._get_client()
        r = c.inspect("context")
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    def _api_events(self, limit: int) -> DataResult:
        c = self._get_client()
        r = c.health()  # API doesn't have dedicated events endpoint yet
        return DataResult(ok=r.ok, data=r.data, error=r.error, mode="api")

    # ---- Offline implementations ----

    def _offline_status(self) -> DataResult:
        engine = self._get_engine()
        if engine is None:
            return DataResult(ok=False, error="Engine not running", mode="offline")
        stats = engine.stats
        data = {}
        for path_name in ["async", "slow", "deep"]:
            s = stats.get(path_name)
            if s:
                data[path_name] = {
                    "trigger_count": getattr(s, 'trigger_count', 0),
                    "success_count": getattr(s, 'success_count', 0),
                    "failure_count": getattr(s, 'failure_count', 0),
                    "total_latency_ms": getattr(s, 'total_latency_ms', 0.0),
                }
        return DataResult(ok=True, data=data, mode="offline")

    def _offline_observations(self, limit: int) -> DataResult:
        engine = self._get_engine()
        if engine is None:
            return DataResult(ok=False, error="Engine not running", mode="offline")
        pool = getattr(engine, '_observation_pool', None)
        if pool is None:
            return DataResult(ok=True, data=[], mode="offline")
        bundles = pool.get_by_domain("all")
        items = []
        for b in bundles[-limit:]:
            items.append({
                "id": str(getattr(b, 'bundle_id', '?')),
                "domain": str(getattr(b, 'domain', '?')),
                "summary": str(getattr(b, 'summary', str(b)))[:60],
                "timestamp": str(getattr(b, 'timestamp', ''))[:8],
            })
        return DataResult(ok=True, data={"items": items, "count": len(bundles)}, mode="offline")

    def _offline_hypotheses(self, limit: int, status: str) -> DataResult:
        try:
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            items = []
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in list(pipe._match_vote._hypotheses.items()):
                    if status != "all" and h.status != status:
                        continue
                    items.append({
                        "id": hid,
                        "statement": h.statement,
                        "domain": h.domain,
                        "status": h.status,
                        "support": h.belief_state['support'],
                        "conflict": h.belief_state['conflict'],
                        "stability": h.belief_state['stability'],
                    })
                    if len(items) >= limit:
                        break
            return DataResult(ok=True, data={"items": items, "count": len(items)}, mode="offline")
        except Exception as e:
            return DataResult(ok=False, error=str(e), mode="offline")

    def _offline_knowledge(self, limit: int) -> DataResult:
        try:
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            items = []
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in pipe._match_vote._hypotheses.items():
                    if h.status == "frozen":
                        items.append({
                            "id": hid,
                            "statement": h.statement,
                            "domain": h.domain,
                            "score": h.belief_score(),
                        })
                        if len(items) >= limit:
                            break
            return DataResult(ok=True, data={"items": items, "count": len(items)}, mode="offline")
        except Exception as e:
            return DataResult(ok=False, error=str(e), mode="offline")

    def _offline_skills(self, limit: int) -> DataResult:
        try:
            from core.agent.v4.skill_layer.skill_pool import SkillPool
            pool = SkillPool()
            skills = pool.list_all() if hasattr(pool, 'list_all') else []
            items = []
            for s in skills[:limit]:
                items.append({
                    "name": getattr(s, 'name', str(s)),
                    "domain": getattr(s, 'domain', '?'),
                    "usage": getattr(s, 'usage_count', 0),
                    "status": getattr(s, 'status', '?'),
                })
            return DataResult(ok=True, data={"items": items, "count": len(items)}, mode="offline")
        except Exception as e:
            return DataResult(ok=False, error=str(e), mode="offline")

    def _offline_world(self) -> DataResult:
        engine = self._get_engine()
        if engine is None:
            return DataResult(ok=False, error="Engine not running", mode="offline")
        world_graph = getattr(engine, '_world_graph', None)
        if world_graph is None:
            return DataResult(ok=False, error="World Graph not loaded", mode="offline")
        data = {
            "world": world_graph.world,
            "nodes": world_graph.node_count,
            "edges": world_graph.edge_count,
            "communities": len(world_graph.communities),
            "backbone": sorted(world_graph.backbone.items(), key=lambda x: x[1], reverse=True)[:8],
        }
        return DataResult(ok=True, data=data, mode="offline")

    def _offline_context(self) -> DataResult:
        engine = self._get_engine()
        if engine is None:
            return DataResult(ok=False, error="Engine not running", mode="offline")
        ctx = getattr(engine, '_last_context', None)
        if ctx is None:
            return DataResult(ok=True, data={"intent": "", "items": 0}, mode="offline")
        data = {
            "intent": getattr(ctx, 'intent', '?'),
            "total_items": getattr(ctx, 'total_items', 0),
        }
        if hasattr(ctx, 'items'):
            from collections import Counter
            sources = Counter(i.source for i in ctx.items)
            data["sources"] = dict(sources)
        return DataResult(ok=True, data=data, mode="offline")

    def _offline_events(self, limit: int) -> DataResult:
        try:
            from core.agent.v4.api_event_log import EventLog
            el = EventLog("data/event_log.db")
            el.open()
            events = el.replay_unconsumed(limit=limit)
            stats = el.stats
            el.close()
            items = []
            for ev in events[-limit:]:
                items.append({
                    "event_id": ev["event_id"],
                    "kind": ev["kind"],
                    "payload_preview": str(ev.get("payload", {}).get("text", ""))[:35],
                })
            return DataResult(ok=True, data={
                "items": items,
                "total": stats.get("total", 0),
                "unconsumed": stats.get("unconsumed", 0),
            }, mode="offline")
        except Exception as e:
            return DataResult(ok=False, error=str(e), mode="offline")
