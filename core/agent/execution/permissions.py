"""Capability Permissions — pledge(2) + seccomp + ConstraintTree for execution safety.

Patterns adapted:
  OpenBSD pledge(2):  process declares capabilities upfront, killed if violates
  seccomp:            syscall whitelist + argument-level filtering
  gVisor:             userspace kernel interception (our ConstraintTree)

Our model:
  pledge pattern:     tool declares needed permissions → runtime enforces
  seccomp pattern:    param-level restriction (rpath=/workspace/*, not /etc/*)
  ConstraintTree:     dynamic rule evaluation for context-aware blocking

Design:
  - Each tool declares a PermissionSet (what capabilities it needs)
  - Runtime checks every operation against the promised set
  - Param-level: allowed_paths, max_file_size, network_allowlist
  - Violation → blocked (default) or ask_user (in UserInLoop)
  - Transition → recorded for learning
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Pattern
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

# ═══ Capability Primitives (Modeled after OpenBSD pledge) ═══

class Capability(Flag):
    """Capability bits — tool must pledge before using.

    Modeled after OpenBSD pledge(2) but adapted for agent operations.
    Tools declare what they need; runtime enforces.
    """
    # Filesystem
    RPATH = auto()    # Read files
    WPATH = auto()    # Write/create files
    CPATH = auto()    # Create new directories
    DPATH = auto()    # Delete/remove files
    FATTR = auto()    # Change file attributes (chmod, chown)
    FLOCK = auto()    # File locking

    # Network
    INET = auto()     # Network: IPv4
    INET6 = auto()    # Network: IPv6
    UNIX = auto()     # Unix domain sockets
    DNS = auto()      # DNS resolution
    MCAST = auto()    # Multicast

    # Process
    PROC = auto()     # Process management (fork, kill)
    EXEC = auto()     # Execute other programs
    PROT_EXEC = auto()  # Memory mapped executable

    # System
    ID = auto()       # User/group ID operations
    TTY = auto()      # Terminal operations
    SETTIME = auto()  # Set system time

    # Agent-specific
    MCP_CLIENT = auto()  # MCP tool invocation
    LLM_CALL = auto()    # LLM API call
    PERSIST_WRITE = auto()  # Write to persistence store
    USER_INTERACT = auto()  # Interact with user (pause, ask)

    # Composite sets
    FILE_READ_ONLY = RPATH | LLM_CALL  # Read-only agent
    FILE_SAFE = RPATH | WPATH | CPATH  # Read+write, no delete
    FILE_FULL = RPATH | WPATH | CPATH | DPATH  # Full FS access
    NET_FULL = INET | INET6 | DNS | UNIX  # Full network
    SANDBOXED = RPATH | LLM_CALL  # Minimal safe set

    @staticmethod
    def from_strings(*names: str) -> "Capability":
        """Parse capability names → flag."""
        result = Capability(0)
        mapping = {
            "rpath": Capability.RPATH, "wpath": Capability.WPATH,
            "cpath": Capability.CPATH, "dpath": Capability.DPATH,
            "fattr": Capability.FATTR, "flock": Capability.FLOCK,
            "inet": Capability.INET, "inet6": Capability.INET6,
            "dns": Capability.DNS, "unix": Capability.UNIX,
            "proc": Capability.PROC, "exec": Capability.EXEC,
            "id": Capability.ID, "mcp": Capability.MCP_CLIENT,
            "llm": Capability.LLM_CALL, "persist": Capability.PERSIST_WRITE,
            "user": Capability.USER_INTERACT,
        }
        for name in names:
            if name in mapping:
                result |= mapping[name]
        return result


# ═══ Permission Set ═══

@dataclass
class PermissionSet:
    """Declared permissions for a tool/operation.

    Inspired by pledge: tool pledges what it needs upfront.
    Inspired by seccomp: param-level restrictions on top of capabilities.
    """
    tool_name: str
    capabilities: Capability

    # seccomp-style param level restrictions
    allowed_paths: List[str] = field(default_factory=list)      # Glob patterns
    denied_paths: List[str] = field(default_factory=list)       # Glob patterns
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    network_allowlist: List[str] = field(default_factory=list)  # Hosts/ports
    command_allowlist: List[str] = field(default_factory=list)  # Allowed executables
    env_vars: List[str] = field(default_factory=list)           # Allowed env vars

    # Risk
    risk_level: str = "low"  # low / medium / high / critical
    requires_user_approval: bool = False
    max_retries: int = 3

    def check_capability(self, cap: Capability) -> bool:
        """Check if this permission set includes a capability."""
        return (self.capabilities & cap) == cap

    def check_path(self, path: str) -> bool:
        """Check if path is within allowed/denied patterns (seccomp-style)."""
        # Denied paths take priority (seccomp: explicit deny)
        for pattern in self.denied_paths:
            if _glob_match(pattern, path):
                return False

        # If no allowlist, all paths allowed (except denied)
        if not self.allowed_paths:
            return True

        # Check allowlist
        for pattern in self.allowed_paths:
            if _glob_match(pattern, path):
                return True

        return False

    def check_command(self, command: str) -> bool:
        """Check if command is in allowlist."""
        if not self.command_allowlist:
            return True
        cmd_base = command.split()[0].split("/")[-1]  # Extract basename
        for allowed in self.command_allowlist:
            if allowed in cmd_base or _glob_match(allowed, cmd_base):
                return True
        return False


# ═══ Built-in Permission Profiles ═══

class PermissionProfiles:
    """Pre-defined permission sets for common agent tools.

    Modeled after OpenBSD pledge profiles:
      main → stdio rpath wpath cpath inet dns
      dns → stdio inet dns
      etc.
    """

    @staticmethod
    def read_only_tool() -> PermissionSet:
        return PermissionSet("read", Capability.FILE_READ_ONLY,
                             denied_paths=["/etc/**", "/boot/**", "**/secrets/**"],
                             risk_level="low")

    @staticmethod
    def safe_write_tool() -> PermissionSet:
        return PermissionSet("write", Capability.FILE_SAFE,
                             denied_paths=["/etc/**", "/boot/**", "**/.git/config"],
                             risk_level="medium", requires_user_approval=True)

    @staticmethod
    def edit_tool() -> PermissionSet:
        return PermissionSet("edit", Capability.FILE_SAFE,
                             allowed_paths=["**/*.py", "**/*.js", "**/*.ts", "**/*.yaml",
                                           "**/*.json", "**/*.toml", "**/*.md", "**/*.txt"],
                             denied_paths=["/etc/**", "/boot/**"],
                             risk_level="medium", requires_user_approval=True)

    @staticmethod
    def delete_tool() -> PermissionSet:
        return PermissionSet("delete", Capability.DPATH,
                             denied_paths=["/etc/**", "/boot/**", "**/.git/**", "**/node_modules/**"],
                             risk_level="high", requires_user_approval=True)

    @staticmethod
    def bash_tool() -> PermissionSet:
        return PermissionSet("bash", Capability.PROC | Capability.EXEC,
                             command_allowlist=["python", "python3", "pip", "npm", "node",
                                               "git", "docker", "make", "cargo", "go",
                                               "ls", "cat", "echo", "grep", "find"],
                             denied_paths=["/etc/passwd", "/etc/shadow", "/root/**"],
                             risk_level="high", requires_user_approval=True)

    @staticmethod
    def network_tool() -> PermissionSet:
        return PermissionSet("mcp_invoke", Capability.INET | Capability.DNS | Capability.MCP_CLIENT,
                             network_allowlist=["localhost:*", "127.0.0.1:*", "api.deepseek.com:443"],
                             risk_level="high", requires_user_approval=True)

    @staticmethod
    def llm_tool() -> PermissionSet:
        return PermissionSet("llm_call", Capability.LLM_CALL | Capability.INET | Capability.DNS,
                             risk_level="low")


# ═══ Permission Enforcer ═══

class PermissionViolation(Exception):
    """Raised when an operation violates its pledged permissions."""
    def __init__(self, tool: str, cap: Capability = None, detail: str = ""):
        self.tool = tool
        self.capability = cap
        self.detail = detail
        super().__init__(f"Permission denied: {tool} — {detail}")

    def to_dict(self) -> dict:
        return {"tool": self.tool, "capability": str(self.capability),
                "detail": self.detail}


class PermissionGuard:
    """Runtime enforcer — pledge pattern + seccomp param filtering.

    Usage:
        guard = PermissionGuard()
        perms = PermissionProfiles.edit_tool()
        guard.enforce(perms, "rpath", path="/workspace/auth.py")  # OK
        guard.enforce(perms, "rpath", path="/etc/passwd")         # DENIED
    """

    def __init__(self, constraint_tree=None, plan_gate=None):
        self._constraint = constraint_tree
        self._plan_gate = plan_gate
        self._violations: List[PermissionViolation] = []
        self._enforcement_count = 0
        self._blocked_count = 0

    def enforce(self, perms: PermissionSet, capability: str,
                path: str = "", command: str = "", host: str = "",
                size: int = 0) -> Tuple[bool, Optional[str]]:
        """Enforce capability + param restrictions.

        Returns (allowed, violation_reason).
        """
        self._enforcement_count += 1

        # 1. Capability check (pledge pattern)
        cap = Capability.from_strings(capability)
        if not perms.check_capability(cap):
            return self._block(perms.tool_name, cap,
                              f"capability {capability} not pledged")

        # 2. Path check (seccomp pattern)
        if path and not perms.check_path(path):
            return self._block(perms.tool_name, cap,
                              f"path {path} not in allowed patterns")

        # 3. File size check
        if size > perms.max_file_size:
            return self._block(perms.tool_name, cap,
                              f"size {size} exceeds max {perms.max_file_size}")

        # 4. Command check (seccomp arg filter)
        if command and not perms.check_command(command):
            return self._block(perms.tool_name, cap,
                              f"command '{command[:50]}' not in allowlist")

        # 5. ConstraintTree check (gVisor pattern)
        if self._constraint and path:
            vios = self._constraint.check(
                perms.tool_name, {"path": path, "command": command})
            if vios:
                high = [v for v in vios if v.get("priority", 5) >= 7]
                if high:
                    return self._block(perms.tool_name, cap,
                                      f"constraint: {high[0]['pattern']}")

        return True, None

    def _block(self, tool: str, cap: Capability, reason: str) -> Tuple[bool, str]:
        """Record violation and return blocked."""
        self._blocked_count += 1
        violation = PermissionViolation(tool, cap, reason)
        self._violations.append(violation)
        logger.warning("Permission blocked: %s", reason)

        # Notify PlanGate for user approval
        if self._plan_gate:
            try:
                self._plan_gate.record_approval_pattern(None)  # Signal block
            except Exception:
                pass

        return False, reason

    def get_recent_violations(self, limit: int = 10) -> List[dict]:
        return [v.to_dict() for v in self._violations[-limit:]]

    @property
    def stats(self) -> dict:
        return {"enforced": self._enforcement_count,
                "blocked": self._blocked_count,
                "rate": self._blocked_count / max(self._enforcement_count, 1)}


# ═══ SandboxExecutor v2 ═══

class CapabilitySandbox:
    """Wires PermissionGuard into ExecutionEngine for fine-grained safety.

    Replaces the simple ExecutionMode (DRY_RUN/SANDBOX/FULL) with
    pledge-style capability declaration + seccomp-style param filtering.
    """

    def __init__(self, permission_guard: PermissionGuard = None,
                 file_sandbox: "FileSandbox" = None):
        self._guard = permission_guard or PermissionGuard()
        self._file_sandbox = file_sandbox
        self._tool_profiles = {
            "read": PermissionProfiles.read_only_tool(),
            "write": PermissionProfiles.safe_write_tool(),
            "edit": PermissionProfiles.edit_tool(),
            "delete": PermissionProfiles.delete_tool(),
            "bash": PermissionProfiles.bash_tool(),
            "mcp_invoke": PermissionProfiles.network_tool(),
            "llm_call": PermissionProfiles.llm_tool(),
        }

    def execute_safe(self, tool: str, params: dict) -> dict:
        """Execute with capability enforcement. Returns execution result."""
        perms = self._tool_profiles.get(tool)
        if not perms:
            return {"status": "blocked",
                    "error": f"Unknown tool: {tool} (no permission profile)"}

        # Determine what capability this requires
        capability = self._infer_capability(tool, params)

        # Enforce
        path = params.get("path", params.get("file", ""))
        command = params.get("command", "")
        size = params.get("size", 0)

        allowed, reason = self._guard.enforce(
            perms, capability, path=path, command=command,
            host=params.get("host", ""), size=size)

        if not allowed:
            return {"status": "blocked", "error": reason,
                    "tool": tool, "permission": perms.tool_name}

        # User approval gate
        if perms.requires_user_approval:
            return {"status": "pending_approval",
                    "tool": tool, "risk": perms.risk_level,
                    "params": params,
                    "note": "Requires user approval"}

        return {"status": "allowed", "tool": tool, "risk": perms.risk_level}

    def _infer_capability(self, tool: str, params: dict) -> str:
        """Map tool + params → required capability."""
        if tool == "read":
            return "rpath"
        if tool in ("write", "edit"):
            return "wpath"
        if tool == "delete":
            return "dpath"
        if tool == "bash":
            cmd = params.get("command", "")
            if any(kw in cmd for kw in ["pip install", "npm install", "cargo build"]):
                return "exec"
            if any(kw in cmd for kw in ["curl", "wget", "ping"]):
                return "inet"
            return "exec"
        if tool in ("mcp_invoke",):
            return "mcp"
        if tool in ("llm_call",):
            return "llm"
        return "rpath"

    @property
    def stats(self) -> dict:
        return self._guard.stats


# ═══ Helpers ═══

def _glob_match(pattern: str, path: str) -> bool:
    """Simple glob matching for path patterns. Supports **/ prefix."""
    path = path.replace("\\", "/").lstrip("/")
    pattern = pattern.lstrip("/")

    # If path contains wildcards (filename only), match against filename
    if "*" in pattern and "/" not in pattern[1:]:
        # Filename-only pattern: match basename
        path_basename = path.rsplit("/", 1)[-1] if "/" in path else path
        regex = "^" + re.escape(pattern).replace("\\*", "[^/]*") + "$"
        return bool(re.match(regex, path_basename))

    # Full path matching
    # Convert **/ → any directory depth
    regex_pattern = re.escape(pattern)
    regex_pattern = regex_pattern.replace("/\\*\\*/", "/(.*/)?").replace("\\*\\*/", "(.*/)?")
    regex_pattern = regex_pattern.replace("\\*", "[^/]*")
    regex = "^" + regex_pattern + "$"
    try:
        return bool(re.match(regex, path))
    except Exception:
        return pattern in path
