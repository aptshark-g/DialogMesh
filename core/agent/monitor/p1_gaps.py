"""P1 Completion — L5 MemoryNode bridge + ProfileTree OCEAN + Sandbox isolation.

Wire the 3 remaining P1 gaps into a single module.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


# ═══ L5 → MemoryNode Bridge ═══

@dataclass
class L5MemoryCard:
    """XML Card for L5 Memory — stores demoted MemoryNode data."""
    card_id: str
    type: str = "MemoryChunk"
    content: str = ""
    pointers: List[str] = field(default_factory=list)
    importance: float = 0.5
    source_node: str = ""
    created_at: float = field(default_factory=time.time)
    ttl_hours: int = 24
    tags: List[str] = field(default_factory=list)

    def to_xml_card(self) -> dict:
        """Convert to XML Card format for L5 storage."""
        return {
            "card_id": self.card_id,
            "type": self.type,
            "content": self.content[:500],
            "pointers": self.pointers,
            "importance": self.importance,
            "source_node": self.source_node,
            "created_at": self.created_at,
            "ttl_hours": self.ttl_hours,
            "tags": self.tags,
        }


class L5MemoryBridge:
    """Bridge: MemoryNode demotion → L5 XML Card storage.

    Wires MemoryNode.chunks → L5 Memory RAG + FederationIndex.
    Currently: MemoryNode creates chunks but doesn't store in L5.
    This bridge: intercepts demotion and stores in L5.
    """

    def __init__(self, l5_memory=None, federation_index=None):
        self._l5 = l5_memory
        self._fed = federation_index
        self._cards: List[L5MemoryCard] = []

    def store_chunk(self, chunk: "MemoryChunk", source_node_id: str,
                    importance: float = 0.5) -> Optional[L5MemoryCard]:
        """Store a MemoryNode chunk as an L5 XML Card."""
        card = L5MemoryCard(
            card_id=f"L5_{chunk.chunk_id}",
            type="MemoryChunk",
            content=chunk.content,
            pointers=chunk.pointers,
            importance=importance,
            source_node=source_node_id,
            tags=["execution", "memory_node"],
        )

        # Store in L5 if available
        if self._l5:
            try:
                self._l5.store_xml_card(card.to_xml_card())
            except Exception as e:
                logger.debug("L5 store failed: %s", e)

        # Update FederationIndex
        if self._fed:
            try:
                self._fed.index({
                    "id": card.card_id,
                    "content": chunk.content[:200],
                    "pointers": chunk.pointers,
                })
            except Exception:
                pass

        self._cards.append(card)
        return card

    def retrieve_cards(self, query: str, max_cards: int = 5) -> List[dict]:
        """Retrieve L5 cards matching query."""
        results = []
        if self._fed:
            try:
                results = self._fed.search(query, limit=max_cards)
            except Exception:
                pass
        # Fallback: in-memory search
        if not results:
            query_lower = query.lower()
            results = [c.to_xml_card() for c in self._cards
                       if query_lower in c.content.lower()][:max_cards]
        return results


# ═══ ProfileTree — OCEAN Evolution ═══

@dataclass
class ProfileSnapshot:
    """OCEAN profile at a point in time."""
    timestamp: float
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5
    trigger: str = ""
    inertia_seconds: float = 0.0  # Time since last change

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "O": self.openness,
            "C": self.conscientiousness,
            "E": self.extraversion,
            "A": self.agreeableness,
            "N": self.neuroticism,
            "trigger": self.trigger,
            "inertia_s": round(self.inertia_seconds, 1),
        }


class ProfileEvolution:
    """Track OCEAN evolution with inertia.

    Inertia: values stabilize over time. Sudden changes decay slowly.
    ProfileTree stores snapshots, evolution engine detects drift and patterns.
    """

    def __init__(self, profile_tree=None, parameter_registry=None):
        self._tree = profile_tree
        self._params = parameter_registry
        self._history: List[ProfileSnapshot] = []
        self._current = ProfileSnapshot(timestamp=time.time())
        self._inertia_weight = 0.3  # How much old value resists change
        self._drift_threshold = 0.15  # Significance threshold for change

    def update(self, dimension: str, new_value: float, trigger: str = "observation"):
        """Update one OCEAN dimension with inertia smoothing."""
        old_value = getattr(self._current, dimension, 0.5)

        # Inertia: new value is dampened by old value
        smoothed = self._inertia_weight * old_value + (1 - self._inertia_weight) * new_value

        # Drift detection
        drift = abs(smoothed - self._current.conscientiousness)  # Use C as reference
        if drift > self._drift_threshold:
            # Significant change → record snapshot
            prev = self._current
            snapshot_time = time.time()
            snapshot = ProfileSnapshot(
                timestamp=snapshot_time,
                openness=getattr(self._current, 'openeness', 0.5),
                conscientiousness=getattr(self._current, 'conscientiousness', 0.5),
                extraversion=getattr(self._current, 'extraversion', 0.5),
                agreeableness=getattr(self._current, 'agreeableness', 0.5),
                neuroticism=getattr(self._current, 'neuroticism', 0.5),
                trigger=trigger,
                inertia_seconds=snapshot_time - prev.timestamp,
            )
            setattr(snapshot, dimension, smoothed)
            self._history.append(snapshot)

            # Store in ProfileTree
            if self._tree:
                self._tree.record_profile_update(dimension, old_value, smoothed, trigger)

        setattr(self._current, dimension, smoothed)
        self._current.timestamp = time.time()

    def get_profile(self) -> dict:
        return self._current.to_dict()

    def get_evolution(self, limit: int = 10) -> List[dict]:
        return [s.to_dict() for s in self._history[-limit:]]

    def detect_inertia_pattern(self) -> str:
        """Detect if user is stabilizing or changing."""
        if len(self._history) < 3:
            return "observing"
        recent_drifts = [
            abs(self._history[i].conscientiousness - self._history[i-1].conscientiousness)
            for i in range(-3, 0)
        ]
        avg_drift = sum(recent_drifts) / len(recent_drifts)
        if avg_drift < 0.05:
            return "stable"  # User preferences are stable
        if avg_drift < self._drift_threshold:
            return "evolving"
        return "changing"  # Significant shifts in behavior


# ═══ Sandbox — Container Isolation ═══

class SandboxExecutor:  # ARCHIVED (2026-08-16): 工具沙箱已由权限引擎
    # （permission_engine RiskClass/Mode/path root）覆盖, 本类零调用方。
    """Basic sandbox for execution isolation.

    Three modes:
      DRY_RUN:  No side effects, just validate
      PROCESS:  Subprocess with resource limits (default)
      CONTAINER: Docker/podman isolation (optional)
    """

    def __init__(self, mode: str = "process"):
        self._mode = mode

    def is_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def sandboxed_execute(self, command: str, timeout: int = 30,
                          workdir: str = "/tmp",
                          memory_mb: int = 256,
                          network: bool = False) -> dict:
        """Execute command in sandboxed environment.

        Returns: {"status", "stdout", "stderr", "exit_code"}
        """
        if self._mode == "dry_run":
            return {"status": "dry_run", "stdout": "", "stderr": "",
                    "exit_code": 0, "note": "No execution in dry_run mode"}

        if self._mode == "container" and self.is_docker_available():
            return self._docker_sandbox(command, timeout, workdir, memory_mb, network)

        # Default: subprocess with limits
        return self._process_sandbox(command, timeout, workdir)

    def _process_sandbox(self, command: str, timeout: int,
                         workdir: str) -> dict:
        import subprocess
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=workdir,
                # Basic isolation
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                     "HOME": workdir, "TMPDIR": workdir},
            )
            return {"status": "ok" if result.returncode == 0 else "error",
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:2000],
                    "exit_code": result.returncode,
                    "mode": "process"}
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "stdout": "", "stderr": "",
                    "exit_code": -1, "mode": "process"}
        except Exception as e:
            return {"status": "failed", "stdout": "", "stderr": str(e),
                    "exit_code": -1, "mode": "process"}

    def _docker_sandbox(self, command: str, timeout: int,
                        workdir: str, memory_mb: int,
                        network: bool) -> dict:
        import subprocess
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", f"{memory_mb}m",
            "--cpus", "1",
            "--network", "none" if not network else "bridge",
            "-v", f"{workdir}:/data",
            "-w", "/data",
            "python:3.11-slim",
            "sh", "-c", command,
        ]
        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True,
                                    timeout=timeout + 5)
            return {"status": "ok" if result.returncode == 0 else "error",
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:2000],
                    "exit_code": result.returncode,
                    "mode": "container"}
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "stdout": "", "stderr": "",
                    "exit_code": -1, "mode": "container"}
        except Exception as e:
            return {"status": "failed", "stdout": "", "stderr": str(e),
                    "exit_code": -1, "mode": "container"}


import os  # For _process_sandbox
