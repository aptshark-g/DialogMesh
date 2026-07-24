"""Engineering Chain — tool availability + environment state for multi-intent routing.

Bridges MCP Client (+ other tool registries) to intent analysis.
Design: docs/v5/ENGINEERING_MULTI_INTENT_SPLIT.md §3.4
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolCapability:
    """One available tool's capability."""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    category: str = ""


@dataclass
class EngineeringState:
    """Current engineering environment state."""
    tools: List[ToolCapability] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    mcp_servers: List[str] = field(default_factory=list)


class EngineeringChain:
    """Queries tool registries (MCP + others) for intent feasibility analysis.

    Usage:
        chain = EngineeringChain(mcp_manager=mcp_client_manager)
        state = chain.snapshot()
        # → {tools: [...], env: {...}, constraints: {...}}
        feasible = chain.check_feasibility("用gdb调试二进制", state)
        # → {feasible: True, blocking: [], suggestions: []}
    """

    def __init__(self, mcp_manager=None, tool_registry=None):
        self.mcp = mcp_manager          # MCPClientManager
        self.tool_registry = tool_registry  # ToolRegistry (if exists)

    def snapshot(self) -> EngineeringState:
        """Take a snapshot of available tools and environment."""
        state = EngineeringState()

        # MCP-discovered tools
        if self.mcp:
            try:
                tool_names = getattr(self.mcp, 'list_discovered_tools', lambda: [])()
                state.mcp_servers = list(tool_names) if callable(tool_names) else []
                
                # Get individual adapter details
                for name in state.mcp_servers:
                    adapter = getattr(self.mcp, '_adapters', {}).get(name)
                    if adapter:
                        for tool in getattr(adapter, 'list_discovered_tools', lambda: [])():
                            state.tools.append(ToolCapability(
                                name=tool,
                                category="mcp",
                            ))
            except Exception as e:
                logger.debug("MCP snapshot failed: %s", e)

        # Tool registry tools
        if self.tool_registry:
            try:
                tools = getattr(self.tool_registry, 'list_all', lambda: [])()
                for t in (tools if callable(tools) else []):
                    state.tools.append(ToolCapability(
                        name=getattr(t, 'name', str(t)),
                        description=getattr(t, 'description', ''),
                        category="registry",
                    ))
            except Exception as e:
                logger.debug("Registry snapshot failed: %s", e)

        # Environment (basic)
        import os, platform
        state.env = {
            "os": platform.system(),
            "python": platform.python_version(),
            "cwd": os.getcwd(),
        }

        return state

    def check_feasibility(self, intent_text: str, state: EngineeringState = None) -> dict:
        """Check if available tools can fulfill this intent.

        Structural check: keyword overlap between intent text and tool names/descriptions.
        Returns: {feasible: bool, matching_tools: [...], confidence: float}
        """
        if state is None:
            state = self.snapshot()

        text_lower = intent_text.lower()
        matches = []
        for tool in state.tools:
            name_lower = tool.name.lower()
            desc_lower = tool.description.lower()
            # Check if intent mentions this tool or its description overlaps
            if name_lower in text_lower or any(
                word in desc_lower and word in text_lower
                for word in text_lower.split()[:5]
            ):
                matches.append(tool.name)

        feasible = len(matches) > 0

        return {
            "feasible": feasible,
            "matching_tools": matches[:5],
            "total_tools": len(state.tools),
            "confidence": min(0.9, len(matches) * 0.3) if feasible else 0.1,
        }

    def llm_context(self, state: EngineeringState = None) -> str:
        """Build LLM context: available tools for intent analysis."""
        if state is None:
            state = self.snapshot()

        parts = [f"Available tools ({len(state.tools)}):"]
        for t in state.tools[:10]:
            parts.append(f"  - {t.name}: {t.description[:80]}")
        
        parts.append(f"Environment: {state.env}")
        parts.append(f"MCP servers: {state.mcp_servers}")

        return "\n".join(parts)
