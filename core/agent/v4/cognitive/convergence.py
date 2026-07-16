"""Convergence engine + SQLite persistence (capacitor model aligned).

Capacitor model: memory_chunks use activation_count, not time decay.
Convergence: EMA with dynamic alpha, anomaly detection, freeze.
Persistence: SQLite store for CognitiveProfileV2.
"""
from __future__ import annotations
import json, math, sqlite3, time, logging
from typing import Dict, List, Optional, Tuple

from .models import CognitiveProfileV2, CognitiveDynamics, UserTag

logger = logging.getLogger(__name__)


class ConvergenceEngine:
    """EMA-based convergence with dynamic alpha and freeze detection.

    alpha(turns) = max(0.05, 1.0 / (1 + sqrt(turns)))
    Capacitor-aligned: no time math needed for convergence.
    """

    HISTORY_WINDOW = 20

    def __init__(self, dynamics: CognitiveDynamics):
        self._dyn = dynamics
        self._history: Dict[str, List[float]] = {}

    def alpha(self, turns: int = None) -> float:
        n = turns if turns else max(1, self._dyn.observation_count)
        return max(0.05, 1.0 / (1.0 + math.sqrt(n)))

    def update(self, dim_name: str, observed: float,
               session_weight: float = 1.0) -> Tuple[float, dict]:
        diag = {"anomaly": False, "frozen": False, "alpha": 0.0, "delta": 0.0}
        if dim_name in self._dyn.frozen_dimensions:
            diag["frozen"] = True
            return getattr(self._dyn, dim_name, 0.5), diag

        old_value = getattr(self._dyn, dim_name, 0.5)
        a = self.alpha() * session_weight
        diag["alpha"] = a

        history = self._history.get(dim_name, [])
        if len(history) >= 5:
            mean_h = sum(history) / len(history)
            var = sum((x - mean_h)**2 for x in history) / len(history)
            std = math.sqrt(var) if var > 0 else 0.05
            if abs(observed - mean_h) > 2 * std:
                diag["anomaly"] = True
                a *= 0.3

        new_value = a * observed + (1 - a) * old_value
        setattr(self._dyn, dim_name, new_value)
        diag["delta"] = new_value - old_value

        history.append(observed)
        if len(history) > self.HISTORY_WINDOW:
            history.pop(0)
        self._history[dim_name] = history
        self._check_freeze(dim_name)
        self._dyn.observation_count += 1
        self._dyn.last_updated = time.time()
        return new_value, diag

    def _check_freeze(self, dim_name: str) -> None:
        if dim_name in self._dyn.frozen_dimensions:
            return
        history = self._history.get(dim_name, [])
        if len(history) < self.HISTORY_WINDOW or self._dyn.observation_count < 50:
            return
        mean_h = sum(history) / len(history)
        var = sum((x - mean_h)**2 for x in history) / len(history)
        if var < 0.0025:
            self._dyn.frozen_dimensions.append(dim_name)
            self._dyn.stability = math.sqrt(var)
            logger.info("Dim %s frozen (σ=%.4f, turns=%d)",
                       dim_name, math.sqrt(var), self._dyn.observation_count)

    def stats(self) -> dict:
        return {
            "observations": self._dyn.observation_count,
            "alpha": self.alpha(),
            "frozen": f"{len(self._dyn.frozen_dimensions)}/9",
            "converged": self._dyn.converged,
        }


# ═══════════════════ SQLite Persistence ═══════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS cognitive_profile (
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    profile_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_profile_user ON cognitive_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_profile_updated ON cognitive_profile(updated_at);
"""


class ProfileStore:
    def __init__(self, db_path: str = "data/cognitive_profile.db"):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def open(self):
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    def save(self, profile: CognitiveProfileV2) -> bool:
        profile.updated_at = time.time()
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO cognitive_profile (user_id, session_id, profile_json, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (profile.user_id, profile.session_id,
                 json.dumps(profile.to_dict(), ensure_ascii=False),
                 profile.updated_at))
            self._conn.commit()
            return True
        except Exception as e:
            logger.error("Profile save: %s", e)
            return False

    def load(self, user_id: str, session_id: str = "") -> Optional[CognitiveProfileV2]:
        try:
            if session_id:
                row = self._conn.execute(
                    "SELECT profile_json FROM cognitive_profile WHERE user_id=? AND session_id=?",
                    (user_id, session_id)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT profile_json FROM cognitive_profile WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
                    (user_id,)).fetchone()
            if row:
                return CognitiveProfileV2.from_dict(json.loads(row[0]))
        except Exception as e:
            logger.warning("Profile load: %s", e)
        return None

    def merge_cross_session(self, user_id: str, current_session: str,
                            cross_weight: float = 0.35) -> Optional[CognitiveProfileV2]:
        rows = self._conn.execute(
            "SELECT session_id, profile_json FROM cognitive_profile "
            "WHERE user_id=? AND session_id!=? ORDER BY updated_at DESC LIMIT 5",
            (user_id, current_session)).fetchall()
        if not rows:
            return None
        merged = None
        for sid, pj in rows:
            other = CognitiveProfileV2.from_dict(json.loads(pj))
            if merged is None:
                merged = other
            else:
                a_w = 1.0 - cross_weight
                for dim in ["cognitive_inertia","behavior_inertia","trust_score",
                            "emotional_entropy","attention_anchor","expectation_deviation",
                            "self_value_score","cognitive_resource"]:
                    setattr(merged.track_a, dim,
                            a_w * getattr(merged.track_a, dim, 0.5) +
                            cross_weight * getattr(other.track_a, dim, 0.5))
                for key, tag in other.track_b.items():
                    existing = merged.track_b.get(key)
                    if not existing or tag.confidence > existing.confidence:
                        merged.track_b[key] = tag
                merged.total_sessions = max(merged.total_sessions, other.total_sessions) + 1
                merged.total_turns += other.total_turns
        return merged
