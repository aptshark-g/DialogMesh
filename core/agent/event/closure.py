"""Gap closure: Process isolation, hot reload, rate limiting, capability security.

All 5 zero-score items from DESIGN_RUNTIME_KERNEL.md Linux kernel mapping.
References: DESIGN_EXECUTION_LAYER, DESIGN_GUARD_SYSTEM, DESIGN_FILESANDBOX, DESIGN_CLI.
"""
import subprocess, time, threading, importlib, sys, json, os, logging
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Gap 1: Process Isolation — subprocess per subsystem
# ═══════════════════════════════════════════════════════════

class SubprocessRunner:
    """Run a subscriber handler in an isolated subprocess.
    One crash doesn't affect other subsystems.

    Design: DESIGN_EXECUTION_LAYER.md §3 — subprocess pool pattern.
    """

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._active: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def run_isolated(self, name: str, module: str, func: str,
                     args: tuple = (), kwargs: dict = None,
                     timeout_sec: float = 5.0) -> dict:
        """Execute a Python function in an isolated subprocess.

        Returns {"success": bool, "result": ..., "pid": int}
        """
        payload = json.dumps({
            "module": module, "func": func,
            "args": list(args), "kwargs": kwargs or {},
        })
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", (
                    "import json,sys; d=json.loads(sys.stdin.read()); "
                    "m=__import__(d['module'],fromlist=[d['func']]);"
                    "r=getattr(m,d['func'])(*d['args'],**d['kwargs']);"
                    "print(json.dumps({'ok':True,'result':str(r)[:1000]}))"
                )],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            stdout, stderr = proc.communicate(input=payload, timeout=timeout_sec)
            if proc.returncode == 0:
                return {"success": True, "result": stdout.strip()[:500], "pid": proc.pid}
            return {"success": False, "error": stderr.strip()[:200], "pid": proc.pid}
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"timeout after {timeout_sec}s", "pid": proc.pid}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════
#  Gap 2: Hot Reload — dynamic subsystem replacement
# ═══════════════════════════════════════════════════════════

class HotReloader:
    """Hot-reload a subsystem without restarting the engine.

    Design: DESIGN_RUNTIME_KERNEL.md §Linux kmod mapping.
    Uses importlib.reload() + registry re-injection.
    """

    @staticmethod
    def reload(engine, subsystem_name: str) -> dict:
        """Reload a single subsystem module and re-inject into engine."""
        reg = getattr(engine, '_registry', None)
        if not reg:
            return {"status": "error", "reason": "no registry attached"}
        
        # Find the subsystem definition
        subs_def = None
        for name, sdef in getattr(reg, '_defs', {}).items():
            if name == subsystem_name:
                subs_def = sdef
                break
        
        if not subs_def:
            return {"status": "error", "reason": f"{subsystem_name} not registered"}
        
        try:
            # Reload the module
            mod_path = subs_def.module_path
            if mod_path in sys.modules:
                mod = importlib.reload(sys.modules[mod_path])
            else:
                mod = importlib.import_module(mod_path)
            
            # Re-create instance
            factory = subs_def.factory
            if callable(factory):
                new_instance = factory()
            else:
                cls = getattr(mod, subs_def.class_name, None)
                new_instance = cls() if cls else None
            
            if new_instance:
                setattr(engine, f"_{subsystem_name}", new_instance)
                logger.info("Hot-reloaded: %s", subsystem_name)
                return {"status": "reloaded", "subsystem": subsystem_name}
            return {"status": "error", "reason": "factory returned None"}
        except Exception as e:
            logger.warning("Hot-reload failed for %s: %s", subsystem_name, e)
            return {"status": "error", "reason": str(e)[:200]}

    @staticmethod
    def list_reloadable(engine) -> List[str]:
        """List all subsystems that can be hot-reloaded."""
        reg = getattr(engine, '_registry', None)
        if not reg:
            return []
        return [name for name in getattr(reg, '_defs', {})]


# ═══════════════════════════════════════════════════════════
#  Gap 3: Rate Limiter — TokenBucket per stage
# ═══════════════════════════════════════════════════════════

class TokenBucket:
    """Token bucket rate limiter. DESIGN_GUARD_SYSTEM.md §2.

    Constant refill rate, burst capacity for spikes.
    """

    def __init__(self, rate_per_sec: float = 100, burst: int = 200):
        self._rate = rate_per_sec
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def available(self) -> float:
        with self._lock:
            return self._tokens


class RateGuard:
    """Multi-stage rate limiter with per-stage token buckets.

    DESIGN_GUARD_SYSTEM.md §1 — TokenBucket × 9 stages.
    """

    DEFAULT_RATES = {
        "pcr":      200,    # PCR routing — high throughput
        "intent":   100,    # Intent parsing
        "llm":      10,     # LLM calls — expensive, limit to 10/s
        "discourse": 50,    # Discourse tree updates
        "behavior": 30,     # Behavior graph recording
        "meta":     20,     # Meta cognition
        "profile":  10,     # Profile updates
        "persist":  5,      # Persistence — IO bound
        "association": 30,  # Association chain
    }

    def __init__(self, rates: dict = None):
        self._buckets: Dict[str, TokenBucket] = {}
        for stage, rate in (rates or self.DEFAULT_RATES).items():
            self._buckets[stage] = TokenBucket(rate, burst=int(rate * 2))

    def allow(self, stage: str) -> bool:
        bucket = self._buckets.get(stage)
        if not bucket:
            return True  # No limiter → allow
        return bucket.consume(1)

    def stats(self) -> dict:
        return {stage: {"available": b.available(), "rate": b._rate}
                for stage, b in self._buckets.items()}


class CascadeDetector:
    """Detect cascade failures — when one slow stage causes upstream stalls.

    DESIGN_GUARD_SYSTEM.md §1 — CascadeDetector.
    """

    def __init__(self, rate_guard: RateGuard, threshold_ms: float = 500):
        self._guard = rate_guard
        self._threshold = threshold_ms
        self._stage_latencies: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def record(self, stage: str, latency_ms: float):
        with self._lock:
            if stage not in self._stage_latencies:
                self._stage_latencies[stage] = []
            lst = self._stage_latencies[stage]
            lst.append(latency_ms)
            if len(lst) > 20:
                lst.pop(0)

    def check(self) -> dict:
        """Check for cascade: if any stage is slow, flag it."""
        alerts = {}
        with self._lock:
            for stage, latencies in self._stage_latencies.items():
                if len(latencies) < 5:
                    continue
                avg = sum(latencies) / len(latencies)
                if avg > self._threshold:
                    alerts[stage] = {
                        "avg_latency_ms": round(avg, 1),
                        "threshold_ms": self._threshold,
                        "action": "throttle",
                    }
                    # Auto-throttle: reduce rate by 50%
                    bucket = self._guard._buckets.get(stage)
                    if bucket:
                        bucket._rate = max(1, bucket._rate * 0.5)
        return {"alerts": alerts, "stages_monitored": len(self._stage_latencies)}


# ═══════════════════════════════════════════════════════════
#  Gap 4: Capability Model — per-subsystem permissions
# ═══════════════════════════════════════════════════════════

class Capability(Enum):
    """What a subsystem is allowed to do."""
    READ_DISK = "read_disk"
    WRITE_DISK = "write_disk"
    NETWORK_OUT = "network_out"   # HTTP calls
    NETWORK_IN = "network_in"     # Listen on ports
    EXEC_SUBPROCESS = "exec_subprocess"
    ACCESS_LLM = "access_llm"
    READ_USER_DATA = "read_user_data"
    MODIFY_PROFILE = "modify_profile"


@dataclass
class CapabilityProfile:
    """Declared capabilities for a subsystem."""
    name: str
    allowed: List[Capability] = field(default_factory=list)
    denied: List[Capability] = field(default_factory=list)


class CapabilityGuard:
    """Enforce capability-based security per subsystem.

    Design: DESIGN_FILESANDBOX.md + Linux SELinux pattern.
    Each subsystem declares what it needs. Guard checks before allowing operations.
    """

    # Default profiles per subsystem
    DEFAULT_PROFILES = {
        "discourse_tree": [Capability.READ_DISK, Capability.WRITE_DISK],
        "behavior_graph": [Capability.READ_DISK, Capability.WRITE_DISK, Capability.READ_USER_DATA],
        "meta_cognition": [Capability.READ_DISK],
        "ocean_analyst": [Capability.READ_USER_DATA, Capability.MODIFY_PROFILE],
        "l1_modifier": [Capability.READ_DISK],
        "l2_5_belief": [Capability.READ_DISK, Capability.WRITE_DISK],
        "pcr_router": [Capability.READ_USER_DATA],
        "intent_parser": [Capability.READ_USER_DATA, Capability.ACCESS_LLM],
        "planner": [Capability.ACCESS_LLM, Capability.NETWORK_OUT],
        "persistence": [Capability.READ_DISK, Capability.WRITE_DISK],
    }

    def __init__(self):
        self._profiles: Dict[str, CapabilityProfile] = {}
        for name, caps in self.DEFAULT_PROFILES.items():
            self._profiles[name] = CapabilityProfile(name=name, allowed=list(caps))

    def check(self, subsystem: str, capability: Capability) -> bool:
        """Check if a subsystem is allowed to perform an operation."""
        profile = self._profiles.get(subsystem)
        if not profile:
            return False  # Unknown subsystem → deny by default

        if capability in profile.denied:
            return False
        if capability in profile.allowed:
            return True
        return False  # Not explicitly allowed → deny

    def grant(self, subsystem: str, capability: Capability):
        """Grant a capability to a subsystem."""
        if subsystem not in self._profiles:
            self._profiles[subsystem] = CapabilityProfile(name=subsystem)
        if capability not in self._profiles[subsystem].allowed:
            self._profiles[subsystem].allowed.append(capability)

    def revoke(self, subsystem: str, capability: Capability):
        if subsystem in self._profiles:
            caps = self._profiles[subsystem].allowed
            if capability in caps:
                caps.remove(capability)

    def profile(self, subsystem: str) -> Optional[CapabilityProfile]:
        return self._profiles.get(subsystem)

    def all_profiles(self) -> Dict[str, list]:
        return {name: [c.value for c in p.allowed]
                for name, p in self._profiles.items()}


# ═══════════════════════════════════════════════════════════
#  Gap 5: CLI Version + ABI compatibility
# ═══════════════════════════════════════════════════════════

CLI_VERSION = "6.0.0"
CLI_COMPAT_TABLE = {
    "6.0.0": ["5.0.0", "5.1.0"],  # Backward compatible with v5
    "5.0.0": ["4.0.0"],
}

DM_ABI = {
    "version": CLI_VERSION,
    "protocol": "json-over-stdout",
    "commands": 237,
    "breaking_changes": [],
    "deprecated": [],
}


def check_compatibility(client_version: str) -> dict:
    """Check if a client CLI version is compatible with the server."""
    server = CLI_VERSION
    compat = CLI_COMPAT_TABLE.get(server, [])
    if client_version == server:
        return {"compatible": True, "match": "exact"}
    if client_version in compat:
        return {"compatible": True, "match": "compatible"}
    return {"compatible": False, "match": "incompatible",
            "server": server, "client": client_version,
            "supported": compat}


def get_cli_abi() -> dict:
    return dict(DM_ABI)
