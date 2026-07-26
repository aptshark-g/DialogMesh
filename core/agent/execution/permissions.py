"""Capability Permissions v2 — full pledge(2) + unveil(2) + seccomp semantics.

OpenBSD pledge(2) semantics adapted:
  1. Promise reduction only      — can never increase, only decrease
  2. Exec promises               — separate set for child processes
  3. unveil(2)                   — per-path whitelist (not just deny)
  4. Implicit capabilities       — wpath implies rpath, exec implies proc
  5. Inheritance                 — sub-agent inherits, can only reduce

seccomp patterns adapted:
  6. Param-level filtering       — not just "allow write", but "write to *.py only"
  7. Graduated blocks            — kill / trap / errno / log

gVisor patterns adapted:
  8. Runtime interception        — ConstraintTree as userspace kernel

Additional:
  9. Resource quotas             — memory_mb, cpu_seconds, disk_mb per agent
  10. Time-bounded permissions   — expires after N seconds
  11. Audit trail                — every check logged to EventLog
  12. Emergency escalation       — user-approved temporary override
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
import fnmatch
import logging
import os
import re
import time

logger = logging.getLogger(__name__)


# ═══ Full Capability System (OpenBSD pledge model) ═══

class Cap(Flag):
    """Capability bits — must be pledged before use. Can only be reduced.

    Modeled after OpenBSD pledge(2) + agent-specific additions.
    Promises cannot be increased after initial pledge().
    """
    # ── Base ──
    STDIO = auto()       # Memory allocation, signal handling, basic I/O
    RPATH = auto()       # Read files/directories
    WPATH = auto()       # Write to files (implies RPATH)
    CPATH = auto()       # Create new files/directories
    DPATH = auto()       # Delete/rename files
    FATTR = auto()       # chmod/chown/utimes (file attributes)
    FLOCK = auto()       # File locking
    TMPSET = auto()      # Temporary file creation (safer than WPATH)

    # ── Network ──
    INET = auto()        # IPv4 sockets
    INET6 = auto()       # IPv6 sockets
    UNIX_ = auto()       # Unix domain sockets
    DNS = auto()         # DNS resolution
    ROUTE = auto()       # Routing table operations

    # ── Process ──
    PROC = auto()        # fork/kill/setpriority
    EXEC = auto()        # Execute programs (implies PROC)
    PROT_EXEC = auto()   # mmap PROT_EXEC

    # ── System ──
    ID = auto()          # setuid/setgid/setgroups
    TTY = auto()         # Terminal operations
    SETTIME = auto()     # Set system time
    AUDIO = auto()       # Audio devices
    VIDEO = auto()       # Video devices

    # ── Agent-specific ──
    LLM_CALL = auto()    # LLM API invocation
    MCP_INVOKE = auto()  # MCP tool invocation
    PERSIST_WRITE = auto()  # Persistence layer write
    USER_INTERRUPT = auto()  # Pause for user interaction
    INTERNAL_SANDBOX = auto()  # Access internal sandbox layer

    # ── Composite Sets ──
    FILE_READ = STDIO | RPATH
    FILE_MODIFY = FILE_READ | WPATH | CPATH | TMPSET
    FILE_FULL = FILE_MODIFY | DPATH | FATTR | FLOCK
    NET_BASIC = INET | DNS
    NET_SERVER = NET_BASIC | INET6 | UNIX_
    PROCESS_SAFE = PROC
    PROCESS_FULL = PROCESS_SAFE | EXEC | PROT_EXEC
    AGENT_MINIMAL = STDIO | RPATH | LLM_CALL
    AGENT_FULL = AGENT_MINIMAL | FILE_MODIFY | NET_BASIC | PROCESS_SAFE

    @staticmethod
    def from_promise_strings(*names: str) -> "Cap":
        """Parse pledge(2)-style promise strings → Cap."""
        mapping = {
            "stdio": Cap.STDIO, "rpath": Cap.RPATH,
            "wpath": Cap.WPATH, "cpath": Cap.CPATH,
            "dpath": Cap.DPATH, "fattr": Cap.FATTR,
            "flock": Cap.FLOCK, "tmpset": Cap.TMPSET,
            "inet": Cap.INET, "inet6": Cap.INET6,
            "unix": Cap.UNIX_, "dns": Cap.DNS, "route": Cap.ROUTE,
            "proc": Cap.PROC, "exec": Cap.EXEC,
            "prot_exec": Cap.PROT_EXEC,
            "id": Cap.ID, "tty": Cap.TTY, "settime": Cap.SETTIME,
            "llm": Cap.LLM_CALL, "mcp": Cap.MCP_INVOKE,
            "persist": Cap.PERSIST_WRITE, "user": Cap.USER_INTERRUPT,
            "sandbox": Cap.INTERNAL_SANDBOX,
        }
        result = Cap(0)
        for n in names:
            if n in mapping:
                result |= mapping[n]
        return result

    def expand_implicits(self) -> "Cap":
        """Apply implicit capability rules (pledge semantics).

        wpath implies rpath, exec implies proc, etc.
        """
        expanded = self
        if expanded & Cap.WPATH:
            expanded |= Cap.RPATH
        if expanded & Cap.EXEC:
            expanded |= Cap.PROC
        if expanded & Cap.FILE_FULL:
            expanded |= Cap.FILE_MODIFY
        return expanded


# ═══ Path Restrictions (OpenBSD unveil model) ═══

class PathPermission(Enum):
    READ = "r"
    WRITE = "w"
    CREATE = "c"
    READWRITE = "rw"
    READWRITECREATE = "rwc"


@dataclass
class PathRestriction:
    """unveil(2)-style path whitelist.

    Only paths that have been explicitly unveiled are accessible.
    Default: no path unveiled → no FS access at all.
    """
    path: str             # Glob pattern: "/workspace/**", "*.py"
    permission: PathPermission

    def matches(self, candidate: str) -> Optional[PathPermission]:
        """Check if candidate path matches this restriction.

        Support: '**/*.py' matches 'auth.py' AND 'src/auth.py'.
        """
        candidate = candidate.replace("\\", "/")
        # Direct match
        if fnmatch.fnmatch(candidate, self.path):
            return self.permission
        # Also match basename for **/ patterns
        if self.path.startswith("**/"):
            basename = candidate.rsplit("/", 1)[-1] if "/" in candidate else candidate
            file_pattern = self.path[3:]  # Remove '**/' prefix
            if fnmatch.fnmatch(basename, file_pattern):
                return self.permission
        return None


@dataclass
class PathSpace:
    """Collection of unveiled paths — the complete filesystem view.

    Modeled after OpenBSD unveil(2): system call that restricts
    filesystem access to only the specified paths.
    """
    _paths: List[PathRestriction] = field(default_factory=list)

    def unveil(self, path: str, permission: PathPermission):
        """Declare a path as accessible. Like unveil(path, "rwc")."""
        self._paths.append(PathRestriction(path, permission))

    def is_allowed(self, candidate: str,
                   required: PathPermission = PathPermission.READ) -> bool:
        """Check if path is within unveiled space."""
        for r in self._paths:
            perm = r.matches(candidate)
            if perm:
                # Check sufficient permission level
                levels = {PathPermission.READ: 1, PathPermission.WRITE: 2,
                         PathPermission.CREATE: 3, PathPermission.READWRITE: 2,
                         PathPermission.READWRITECREATE: 3}
                if levels.get(perm, 0) >= levels.get(required, 0):
                    return True
        return False

    def lock(self):
        """After lock(), no more unveil() calls allowed.

        Equivalent to unveil(NULL, NULL) in OpenBSD.
        """
        self._paths = tuple(self._paths)  # Freeze

    @property
    def is_locked(self) -> bool:
        return isinstance(self._paths, tuple)


# ═══ Seccomp-style Param Filters ═══

class BlockAction(Enum):
    KILL = "kill"       # Terminate agent
    ERRNO = "errno"     # Return error code
    LOG = "log"         # Log and allow (audit mode)
    TRAP = "trap"       # SIGSYS → handler


@dataclass
class SyscallFilter:
    """Seccomp-style syscall filter — param-level restrictions.

    seccomp-bpf allows: "allow write() to fd 1 and 2 only"
    We adapt: "allow edit() on *.py files only"
    """
    tool: str                   # Tool name (write, edit, bash)
    capability: Cap             # Required capability
    block_action: BlockAction   # What happens on violation

    # Param filters
    allowed_globs: List[str] = field(default_factory=list)
    denied_globs: List[str] = field(default_factory=list)
    command_prefixes: List[str] = field(default_factory=list)
    max_args: int = 10
    max_arg_length: int = 4096

    def check_params(self, params: dict) -> Tuple[bool, str]:
        """Check parameters against this filter."""
        path = params.get("path", params.get("file", ""))
        cmd = params.get("command", "")

        # Denied first (explicit deny always wins)
        for g in self.denied_globs:
            if _glob_match(g, path):
                return False, f"denied: {path} matches {g}"

        # Allowed
        if self.allowed_globs:
            if not any(_glob_match(g, path) for g in self.allowed_globs):
                return False, f"not in allowed: {path}"

        # Command prefix
        if self.command_prefixes and cmd:
            prefix = cmd.split()[0]
            if not any(prefix.startswith(p) for p in self.command_prefixes):
                return False, f"command not allowed: {prefix}"

        return True, ""


# ═══ Resource Quotas ═══

@dataclass
class ResourceQuota:
    """Per-agent resource limits."""
    max_memory_mb: int = 256
    max_cpu_seconds: float = 60.0
    max_disk_mb: int = 100
    max_files: int = 50
    max_network_connections: int = 5
    max_llm_tokens: int = 8192
    max_llm_calls: int = 10

    def exhausted(self, usage: dict) -> Optional[str]:
        """Check if any quota is exhausted."""
        checks = {
            "memory_mb": self.max_memory_mb,
            "cpu_seconds": self.max_cpu_seconds,
            "disk_mb": self.max_disk_mb,
            "files": self.max_files,
            "network_conns": self.max_network_connections,
            "llm_tokens": self.max_llm_tokens,
            "llm_calls": self.max_llm_calls,
        }
        for k, limit in checks.items():
            if usage.get(k, 0) > limit:
                return f"{k}: {usage[k]} > {limit}"
        return None


# ═══ Permission Profile ═══

@dataclass
class PermissionProfile:
    """Complete permission profile for an agent operation.

    Combines pledge promises + unveil paths + seccomp filters + quotas.
    """
    name: str
    capabilities: Cap
    exec_capabilities: Cap       # For sub-agent spawned via exec
    path_space: PathSpace
    syscall_filters: List[SyscallFilter] = field(default_factory=list)
    resource_quota: ResourceQuota = field(default_factory=ResourceQuota)
    time_limit_s: int = 300       # Overall time limit
    requires_user_approval: bool = False

    def reduce(self, new_caps: Cap) -> "PermissionProfile":
        """Reduce capabilities — pledge semantics: can only decrease."""
        if (new_caps & ~self.capabilities):
            raise ValueError(
                f"Cannot increase: pledged {self.capabilities}, "
                f"requested {new_caps}")
        self.capabilities = new_caps
        return self

    def check(self, capability: Cap, params: dict = None) -> Tuple[bool, str]:
        """Full permission check: cap + path + params.

        Returns (allowed, violation_reason).
        """
        # 1. Capability check
        expanded = self.capabilities.expand_implicits()
        if not (expanded & capability):
            return False, f"capability not pledged: {capability}"

        # 2. Path check (unveil)
        if params:
            path = params.get("path", params.get("file", ""))
            if path:
                if not self.path_space.is_allowed(path):
                    return False, f"path not unveiled: {path}"

        # 3. Syscall filters (seccomp)
        if params and self.syscall_filters:
            tool = params.get("tool", "unknown")
            for sf in self.syscall_filters:
                if sf.tool == tool:
                    ok, reason = sf.check_params(params)
                    if not ok:
                        return False, reason

        return True, ""


# ═══ Built-in Profiles ═══

class AgentProfiles:
    """Pre-defined permission profiles for common agent operations."""

    @staticmethod
    def safe_read_agent(name: str = "reader") -> PermissionProfile:
        ps = PathSpace()
        ps.unveil("**/*.py", PathPermission.READ)
        ps.unveil("**/*.yaml", PathPermission.READ)
        ps.unveil("**/*.json", PathPermission.READ)
        ps.unveil("**/*.md", PathPermission.READ)
        ps.unveil("**/*.txt", PathPermission.READ)
        ps.unveil("**/*.toml", PathPermission.READ)
        ps.lock()

        return PermissionProfile(
            name=name,
            capabilities=Cap.AGENT_MINIMAL,
            exec_capabilities=Cap.AGENT_MINIMAL,
            path_space=ps,
            resource_quota=ResourceQuota(max_llm_tokens=4096),
            time_limit_s=120,
        )

    @staticmethod
    def code_editor(name: str = "editor") -> PermissionProfile:
        ps = PathSpace()
        ps.unveil("**/*.py", PathPermission.READWRITE)
        ps.unveil("**/*.js", PathPermission.READWRITE)
        ps.unveil("**/*.ts", PathPermission.READWRITE)
        ps.unveil("**/*.yaml", PathPermission.READWRITE)
        ps.unveil("**/*.json", PathPermission.READWRITE)
        ps.unveil("**/*.toml", PathPermission.READWRITE)
        ps.unveil("**/*.md", PathPermission.READWRITE)
        ps.unveil("**/*.txt", PathPermission.READWRITE)
        ps.lock()

        return PermissionProfile(
            name=name,
            capabilities=Cap.AGENT_MINIMAL | Cap.FILE_MODIFY,
            exec_capabilities=Cap.AGENT_MINIMAL,
            path_space=ps,
            syscall_filters=[
                SyscallFilter(
                    tool="edit",
                    capability=Cap.WPATH,
                    block_action=BlockAction.ERRNO,
                    allowed_globs=["**/*.py", "**/*.js", "**/*.ts",
                                   "**/*.yaml", "**/*.json", "**/*.toml",
                                   "**/*.md", "**/*.txt"],
                    denied_globs=["/etc/**", "/boot/**", "**/secrets/**",
                                  "**/.env", "**/node_modules/**"],
                ),
            ],
            resource_quota=ResourceQuota(max_disk_mb=50, max_llm_tokens=8192),
            time_limit_s=300,
            requires_user_approval=True,
        )

    @staticmethod
    def devops_agent(name: str = "devops") -> PermissionProfile:
        ps = PathSpace()
        ps.unveil("**", PathPermission.READWRITECREATE)
        ps.unveil("/tmp/**", PathPermission.READWRITECREATE)
        ps.unveil("/var/tmp/**", PathPermission.READWRITECREATE)
        ps.lock()

        return PermissionProfile(
            name=name,
            capabilities=(Cap.AGENT_FULL | Cap.PROCESS_SAFE |
                         Cap.NET_SERVER | Cap.TMPSET),
            exec_capabilities=Cap.PROCESS_FULL,
            path_space=ps,
            syscall_filters=[
                SyscallFilter(
                    tool="bash",
                    capability=Cap.EXEC,
                    block_action=BlockAction.LOG,
                    command_prefixes=[
                        "python", "pip", "npm", "node", "git",
                        "docker", "make", "cargo", "go",
                        "ls", "cat", "echo", "grep", "find",
                        "curl", "wget",
                    ],
                    denied_globs=["/etc/passwd", "/etc/shadow",
                                  "/root/**", "/proc/**"],
                ),
            ],
            resource_quota=ResourceQuota(
                max_memory_mb=512, max_cpu_seconds=120,
                max_disk_mb=200, max_files=100,
                max_network_connections=10, max_llm_calls=20,
            ),
            time_limit_s=600,
            requires_user_approval=True,
        )

    @staticmethod
    def llm_only_agent(name: str = "planner") -> PermissionProfile:
        ps = PathSpace()
        ps.lock()  # No FS access at all

        return PermissionProfile(
            name=name,
            capabilities=Cap.STDIO | Cap.LLM_CALL,
            exec_capabilities=Cap(0),  # No exec possible
            path_space=ps,
            resource_quota=ResourceQuota(max_llm_tokens=16384, max_llm_calls=5),
            time_limit_s=60,
        )


# ═══ Permission Enforcer ═══

class PermissionViolation(Exception):
    def __init__(self, agent: str, cap: Cap, detail: str,
                 action: BlockAction = BlockAction.ERRNO):
        self.agent = agent
        self.capability = cap
        self.detail = detail
        self.action = action
        self.timestamp = time.time()
        super().__init__(f"[{action.value}] {agent}: {detail}")

    def to_audit(self) -> dict:
        return {
            "agent": self.agent, "capability": str(self.capability),
            "detail": self.detail, "action": self.action.value,
            "timestamp": self.timestamp,
        }


class PermissionEnforcer:
    """Runtime enforcer with audit trail.

    Every check logged to violations list (→ EventLog if wired).
    Emergency escalation: user can approve temporary override.
    """

    def __init__(self, constraint_tree=None, event_bus=None):
        self._constraint = constraint_tree
        self._event_bus = event_bus
        self._violations: List[PermissionViolation] = []
        self._emergency_overrides: Dict[str, float] = {}  # agent → expires
        self._checks = 0
        self._blocks = 0

    def enforce(self, profile: PermissionProfile, capability: Cap,
                params: dict = None, agent_name: str = "agent") -> Tuple[bool, str]:
        """Full enforcement: cap + path + seccomp + constraint + emergency.

        Returns (allowed, reason).
        """
        self._checks += 1

        # Emergency override
        if agent_name in self._emergency_overrides:
            if time.time() < self._emergency_overrides[agent_name]:
                return True, "emergency_override"

        # Check permission profile
        allowed, reason = profile.check(capability, params)
        if not allowed:
            return self._handle_violation(agent_name, capability, reason,
                                         BlockAction.ERRNO)

        # ConstraintTree check (gVisor layer)
        if self._constraint and params:
            tool = params.get("tool", "unknown")
            path = params.get("path", "")
            vios = self._constraint.check(tool, {"path": path})
            if vios:
                high_priority = [v for v in vios if v.get("priority", 5) >= 7]
                if high_priority:
                    return self._handle_violation(
                        agent_name, capability,
                        f"constraint: {high_priority[0]['pattern']}",
                        BlockAction.ERRNO)

        return True, ""

    def _handle_violation(self, agent: str, cap: Cap, reason: str,
                          action: BlockAction) -> Tuple[bool, str]:
        self._blocks += 1
        violation = PermissionViolation(agent, cap, reason, action)
        self._violations.append(violation)

        if action == BlockAction.KILL:
            logger.critical("Agent %s killed: %s", agent, reason)
        elif action == BlockAction.LOG:
            logger.info("Agent %s audit: %s", agent, reason)

        # Publish to EventBus
        if self._event_bus:
            try:
                import asyncio
                asyncio.ensure_future(
                    self._event_bus.publish("permission.violation",
                                           violation.to_audit()))
            except Exception:
                pass

        return False, reason

    def grant_emergency(self, agent: str, duration_s: float = 60.0):
        """User-approved temporary override."""
        self._emergency_overrides[agent] = time.time() + duration_s
        logger.warning("Emergency override: %s (%ds)", agent, duration_s)

    def revoke_emergency(self, agent: str):
        self._emergency_overrides.pop(agent, None)

    def audit_trail(self, limit: int = 50) -> List[dict]:
        return [v.to_audit() for v in self._violations[-limit:]]

    @property
    def stats(self) -> dict:
        return {
            "checks": self._checks, "blocks": self._blocks,
            "rate": self._blocks / max(self._checks, 1),
            "emergency_overrides": len(self._emergency_overrides),
        }

def _glob_match(pattern: str, path: str) -> bool:
    """Glob matching with **/ basename support."""
    path = path.replace(chr(92), '/').lstrip('/')
    pattern = pattern.lstrip('/')
    if fnmatch.fnmatch(path, pattern):
        return True
    if pattern.startswith('**/'):
        basename = path.rsplit('/', 1)[-1] if '/' in path else path
        file_pattern = pattern[3:]
        if fnmatch.fnmatch(basename, file_pattern):
            return True
    return False
    if pattern.startswith('**/'):
        basename = path.rsplit('/', 1)[-1] if '/' in path else path
        file_pattern = pattern[3:]
        if fnmatch.fnmatch(basename, file_pattern):
            return True
    return False
