"""MCP Integration — bridges external MCP tools into DialogMesh ToolRegistry.

Completes: ENGINEERING_TOOL_REGISTRY §4 MCP integration + 
          ENGINEERING_MULTILAYER_LLM §11.2 external tool binding.

Architecture:
  MCP Server (Claude Code / OpenCode / any MCP tool)
    → MCPClientManager (mcp/client.py, 已有)
    → ToolRegistryBridge (engineering_bridges.py)
    → EngineeringChain constraint validation
    → PlanningBridge tool selection
    → LLM execution
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class MCPToolBinding:
    """A discovered MCP tool bound to DialogMesh constraints."""
    tool_name: str
    mcp_server: str          # e.g. "claude_code", "opencode"
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)  # EngineeringChain rules
    permission: str = "auto"  # auto / confirm / deny
    tags: List[str] = field(default_factory=list)


class MCPIntegrationHub:
    """Single entry point for MCP tool management in DialogMesh.

    Usage:
        hub = MCPIntegrationHub()
        await hub.discover_all()                    # scan all configured MCP servers
        tools = hub.bind_to_registry()              # register in ToolRegistry
        validated = hub.validate_against_constraints(tool_name, params)
    """

    def __init__(self, tool_registry_bridge=None, engineering_chain=None):
        self._mcp_manager = None
        self._tool_registry = tool_registry_bridge
        self._engineering = engineering_chain
        self._discovered: List[MCPToolBinding] = []
        self._configs: List[dict] = []

    def configure(self, configs: List[dict]):
        """Add MCP server configs. Example:
        [{"type": "stdio", "command": "claude", "args": ["mcp", "serve"], "label": "claude_code"},
         {"type": "http", "url": "http://localhost:9000/mcp", "label": "opencode"}]
        """
        self._configs = configs

    async def discover_all(self) -> List[MCPToolBinding]:
        """Discover tools from all configured MCP servers."""
        if not self._mcp_manager:
            try:
                from core.agent.mcp.client import MCPClientManager
                self._mcp_manager = MCPClientManager()
            except Exception as e:
                logger.debug("MCPClientManager unavailable: %s", e)
                return []

        # Add configs
        for cfg in self._configs:
            try:
                from core.agent.mcp.config import MCPClientConfig
                mcp_cfg = MCPClientConfig(
                    label=cfg.get("label", "mcp_server"),
                    transport=cfg.get("type", "http"),
                    url=cfg.get("url"),
                    command=cfg.get("command"),
                    args=cfg.get("args", []),
                )
                self._mcp_manager.add_config(mcp_cfg)
            except Exception as e:
                logger.debug("Config add failed: %s", e)

        # Discover
        await self._mcp_manager.connect_all()
        discovered_tools = self._mcp_manager.list_all_tools()
        server_labels = self._mcp_manager.list_servers()

        self._discovered = []
        for server_name, tools in discovered_tools.items():
            for tool in tools:
                binding = MCPToolBinding(
                    tool_name=f"mcp_{server_name}_{tool.get('name', 'unknown')}",
                    mcp_server=server_name,
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {}),
                    tags=["mcp", server_name],
                )
                self._discovered.append(binding)

        logger.info("MCP: discovered %d tools from %d servers",
                    len(self._discovered), len(server_labels))
        return self._discovered

    def bind_to_registry(self) -> int:
        """Register all discovered MCP tools into ToolRegistry."""
        if not self._tool_registry:
            from core.agent.engineering_bridges import ToolRegistryBridge
            self._tool_registry = ToolRegistryBridge()

        count = 0
        for binding in self._discovered:
            if self._tool_registry.register({
                "name": binding.tool_name,
                "description": f"[MCP:{binding.mcp_server}] {binding.description}",
                "parameters": binding.parameters,
                "source": "mcp",
                "tool_type": "mcp_remote",
                "tags": set(binding.tags),
            }):
                count += 1
        return count

    def validate_against_constraints(self, tool_name: str, params: dict) -> dict:
        """Validate tool call against EngineeringChain constraints.

        Returns: {"allowed": bool, "warnings": [...], "blocking": [...]}
        """
        if not self._engineering:
            return {"allowed": True, "warnings": [], "blocking": []}

        try:
            result = self._engineering.check_feasibility(tool_name, params)
            return result
        except Exception:
            return {"allowed": True, "warnings": [], "blocking": []}

    def list_bound_tools(self) -> List[Dict]:
        return [{
            "name": b.tool_name,
            "server": b.mcp_server,
            "description": b.description,
            "permission": b.permission,
        } for b in self._discovered]

    def sync_discover_and_bind(self) -> int:
        """Synchronous wrapper — discover + bind in one call."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.discover_all())
        except Exception as e:
            logger.debug("MCP discover failed: %s", e)
        return self.bind_to_registry()


# ═══ Pre-built adapter: Claude Code ═══

CLAUDE_CODE_MCP_CONFIG = {
    "type": "stdio",
    "command": "claude",
    "args": ["mcp", "serve"],
    "label": "claude_code",
}

# ═══ Pre-built adapter: OpenCode ═══

OPENCODE_MCP_CONFIG = {
    "type": "http",
    "url": "http://localhost:9000/mcp",
    "label": "opencode",
}
