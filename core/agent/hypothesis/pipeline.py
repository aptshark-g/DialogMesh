"""HypothesisPipeline: Observation Queue -> Hypothesis Worker -> Knowledge Queue."""
from __future__ import annotations
import time
import threading
import logging
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from .match_vote import MatchVoteEngine
from .decay_resolve import DecayResolveEngine
from .session_manager import SessionManager
from .models import ReasonSession, KnowledgeNode

logger = logging.getLogger(__name__)


class HypothesisPipeline:

    def __init__(self, match_vote: MatchVoteEngine = None,
                 decay_resolve: DecayResolveEngine = None,
                 session_mgr: SessionManager = None,
                 decay_interval_sec: float = 60.0):
        self._match_vote = match_vote or MatchVoteEngine()
        self._decay_resolve = decay_resolve or DecayResolveEngine()
        self._sessions = session_mgr or SessionManager()
        self._decay_interval = decay_interval_sec
        self._observation_queue: deque = deque()
        self._knowledge_nodes: List[KnowledgeNode] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats: Dict[str, int] = {"events_processed": 0, "hypotheses_frozen": 0, "sessions_closed": 0}

    def register_hypothesis(self, hypothesis) -> None:
        self._match_vote.register(hypothesis)
        self._decay_resolve.register(hypothesis)

    def submit(self, evidence: dict, triggering_event: str = "",
               domain: str = "") -> ReasonSession:
        session = self._sessions.open(triggering_event, domain)
        votes = self._match_vote.process(evidence, session=session)
        self._stats["events_processed"] += 1
        return session

    def run_cycle(self) -> Dict[str, list]:
        self._decay_resolve.decay_all()
        result = self._decay_resolve.resolve()
        if result["frozen"]:
            self._stats["hypotheses_frozen"] += len(result["frozen"])
            self._knowledge_nodes.extend(
                [kn for kn in self._decay_resolve._knowledge
                 if kn.knowledge_id in result["frozen"]]
            )
        return result

    def close_resolved_sessions(self):
        for session in self._sessions.list_open():
            for v in session.votes:
                h = self._match_vote._hypotheses.get(v.hypothesis_id)
                if h and h.status == "frozen":
                    self._sessions.close(session.session_id,
                                         winner=h.hypothesis_id,
                                         knowledge_ref=f"kn_{h.hypothesis_id}")
                    self._stats["sessions_closed"] += 1
                    break

    def start_background(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._background_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _background_loop(self) -> None:
        while self._running:
            time.sleep(self._decay_interval)
            with self._lock:
                try:
                    self.run_cycle()
                    self.close_resolved_sessions()
                except Exception:
                    logger.exception("Pipeline cycle failed")

    def stats(self) -> dict:
        return {
            **self._stats,
            "decay_interval_sec": self._decay_interval,
            "running": self._running,
            "hypothesis_count": self._match_vote.hypothesis_count,
            "knowledge_count": len(self._knowledge_nodes),
            "sessions": self._sessions.stats(),
        }
