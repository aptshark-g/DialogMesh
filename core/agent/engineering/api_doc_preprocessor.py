"""API Doc Preprocessor — ENGINEERING_API_DOC_PREPROCESSOR (765L).

Extracts structured tool definitions from API documentation formats
(OpenAPI/Swagger, Postman, Markdown, raw JSON).
Outputs ToolSchema-compatible definitions for ToolRegistry.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import re
import json
import logging

logger = logging.getLogger(__name__)


class APIDocPreprocessor:
    """Extract tool definitions from API docs → ToolSchema format."""

    def __init__(self):
        self._parsers = {
            "openapi": self._parse_openapi,
            "swagger": self._parse_swagger,
            "markdown": self._parse_markdown,
            "json": self._parse_json_endpoints,
        }

    def parse(self, content: str, source_type: str = "auto") -> List[Dict]:
        """Parse API documentation → list of tool definitions.

        Args:
            content: raw API doc text
            source_type: "openapi"/"swagger"/"markdown"/"json"/"auto"

        Returns:
            List of tool definitions compatible with ToolSchema
        """
        if source_type == "auto":
            source_type = self._detect_format(content)

        parser = self._parsers.get(source_type, self._parse_json_endpoints)
        try:
            return parser(content)
        except Exception as e:
            logger.debug("API doc parse failed (%s): %s", source_type, e)
            return []

    def _detect_format(self, content: str) -> str:
        if '"openapi"' in content or '"swagger"' in content:
            return "openapi"
        if '```' in content and ('GET' in content or 'POST' in content):
            return "markdown"
        if content.strip().startswith('{') or content.strip().startswith('['):
            return "json"
        return "markdown"

    def _parse_openapi(self, content: str) -> List[Dict]:
        """Parse OpenAPI 3.x spec → tool definitions."""
        try:
            spec = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            return self._parse_markdown(content)

        tools = []
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method in ["get", "post", "put", "delete", "patch"]:
                op = methods.get(method)
                if not op:
                    continue
                tools.append({
                    "name": op.get("operationId", f"{method}_{path.replace('/', '_')}"),
                    "description": op.get("summary", op.get("description", "")),
                    "parameters": self._openapi_params_to_schema(op),
                    "source": "api_doc",
                    "tool_type": "http_api",
                    "endpoint_url": path,
                    "http_method": method.upper(),
                    "tags": set(op.get("tags", [])),
                })
        return tools

    def _parse_swagger(self, content: str) -> List[Dict]:
        return self._parse_openapi(content)  # Swagger 2.0 → same structure

    def _parse_markdown(self, content: str) -> List[Dict]:
        """Parse markdown API docs → tool definitions."""
        tools = []
        # Pattern: `METHOD /path` followed by description
        pattern = r'`(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s`]+)`\s*[-–—:]\s*([^\n]+)'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            method, path, desc = match.groups()
            tools.append({
                "name": f"{method.lower()}_{path.replace('/', '_').strip('_')}",
                "description": desc.strip(),
                "parameters": {},
                "source": "api_doc",
                "tool_type": "http_api",
                "endpoint_url": path,
                "http_method": method.upper(),
            })
        return tools

    def _parse_json_endpoints(self, content: str) -> List[Dict]:
        """Parse raw JSON endpoint list → tool definitions."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "endpoints" in data:
            return data["endpoints"]
        return [data] if data else []

    def _openapi_params_to_schema(self, operation: dict) -> Dict:
        """Convert OpenAPI parameters to JSON Schema."""
        schema = {"type": "object", "properties": {}, "required": []}
        for param in operation.get("parameters", []):
            name = param.get("name", "")
            schema["properties"][name] = {
                "type": param.get("schema", {}).get("type", "string"),
                "description": param.get("description", ""),
            }
            if param.get("required"):
                schema["required"].append(name)
        # Request body
        if "requestBody" in operation:
            body = operation["requestBody"]
            schema["properties"]["body"] = {
                "type": "object",
                "description": body.get("description", "Request body"),
            }
            if body.get("required"):
                schema["required"].append("body")
        return schema
