"""LLM Tool Call Protocol — parse <tool_call> from LLM response and execute.

The LLM receives tool descriptions in its system prompt.
When it needs a tool, it outputs:
  <tool_call name="tool_name">
    {"arg": "value", ...}
  </tool_call>

We parse this, execute the tool, and inject results back into context.
"""

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.tools.registry import ToolRegistry, ToolResult

logger = logging.getLogger("dm.protocol")


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    raw: str


@dataclass
class ExecutionTrace:
    calls: List[ToolCall] = field(default_factory=list)
    results: List[ToolResult] = field(default_factory=list)

    def to_task_graph(self) -> List[Dict]:
        """Convert execution trace to task_graph nodes for frontend display."""
        nodes = []
        for i, (call, result) in enumerate(zip(self.calls, self.results)):
            nodes.append({
                "id": f"tool_{i}",
                "name": f"{call.name}: {list(call.args.values())[:3]}",
                "tool": call.name,
                "status": "completed" if result.success else "failed",
                "latency_ms": result.latency_ms,
                "error": result.error,
            })
        return nodes


def build_tool_system_prompt() -> str:
    """Generate the tool section of the system prompt."""
    tools = ToolRegistry.list_all()
    if not tools:
        return ""

    lines = ["\n## Available Tools\n"]
    for t in tools:
        args = ", ".join(f"{k}: {v}" for k, v in t["schema"].items()) if t["schema"] else "none"
        lines.append(f"- **{t['name']}** ({t['category']}): {t['description']}")
        if args and args != "none":
            lines.append(f"  Arguments: {args}")
        lines.append("")

    lines.append("""To call a tool, output:
<tool_call name="tool_name">
  {"arg": "value"}
</tool_call>

After tool results are returned, continue your response.""")
    return "\n".join(lines)


def parse_tool_calls(text: str) -> List[ToolCall]:
    """Extract <tool_call> blocks from LLM response text."""
    pattern = r'<tool_call\s+name="([^"]+)"\s*>\s*(.*?)\s*</tool_call>'
    calls = []
    for match in re.finditer(pattern, text, re.DOTALL):
        name = match.group(1)
        raw_args = match.group(2).strip()
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            # Try to recover: maybe it's a single value, not JSON
            args = {"value": raw_args.strip('"\'')}
        calls.append(ToolCall(name=name, args=args, raw=raw_args))
    return calls


def execute_tool_calls(calls: List[ToolCall], trace: ExecutionTrace = None) -> str:
    """Execute tool calls and return formatted results for LLM context.

    Returns a string like:
      <tool_result name="arxiv_search">{"papers": [...]}</tool_result>
    """
    if trace is None:
        trace = ExecutionTrace()

    results_text = []
    for call in calls:
        logger.info("Tool call: %s(%s)", call.name, call.args)
        try:
            result = ToolRegistry.execute(call.name, **call.args)
        except Exception as e:
            result = ToolResult(call.name, False, error=str(e))

        trace.calls.append(call)
        trace.results.append(result)

        if result.success:
            data = result.data
            # For display, truncate large results
            data_str = json.dumps(data, ensure_ascii=False, default=str)
            if len(data_str) > 2000:
                data_str = data_str[:2000] + "..."
            results_text.append(
                f'<tool_result name="{call.name}" success="true">\n{data_str}\n</tool_result>'
            )
        else:
            results_text.append(
                f'<tool_result name="{call.name}" success="false">\n{result.error}\n</tool_result>'
            )

    return "\n".join(results_text)


def strip_tool_calls(text: str) -> str:
    """Remove <tool_call> blocks from LLM text, leaving only the conversational part."""
    return re.sub(r'<tool_call.*?</tool_call>', '', text, flags=re.DOTALL).strip()
