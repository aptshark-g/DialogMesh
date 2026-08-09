# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EventSchema(BaseModel):
    name: str
    version: str = "1.0"
    description: str = ""
    required_fields: List[str] = Field(default_factory=list)
    allowed_fields: List[str] = Field(default_factory=list)
    is_core: bool = False

_CORE_EVENTS = {
    "message": EventSchema(name="message", version="1.0", description="用户消息", required_fields=["content"], is_core=True),
    "pong": EventSchema(name="pong", version="1.0", description="心跳回复", required_fields=["timestamp"], is_core=True),
    "session_created": EventSchema(name="session_created", version="1.0", description="会话创建", required_fields=["session_id"], is_core=True),
    "error": EventSchema(name="error", version="1.0", description="错误通知", required_fields=["message"], is_core=True),
}

class EventRegistry:
    def __init__(self):
        self._schemas: Dict[str, EventSchema] = dict(_CORE_EVENTS)
        self._extensions: Dict[str, str] = {}

    def register(self, schema: EventSchema, extension_id: Optional[str] = None) -> bool:
        if schema.name in _CORE_EVENTS:
            logger.warning("Cannot override core event: %s", schema.name)
            return False
        if schema.name in self._schemas and self._schemas[schema.name].is_core:
            return False
        self._schemas[schema.name] = schema
        if extension_id:
            self._extensions[schema.name] = extension_id
        return True

    def validate(self, event_type: str, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        schema = self._schemas.get(event_type)
        if not schema:
            errors.append(f"Unknown event type: {event_type}")
            return False, errors
        for field in schema.required_fields:
            if field not in payload:
                errors.append(f"Missing required field: {field}")
        if schema.allowed_fields:
            for key in payload:
                if key not in schema.allowed_fields and key not in schema.required_fields:
                    errors.append(f"Unexpected field: {key}")
        return len(errors) == 0, errors

    def get_schema(self, event_type: str) -> Optional[EventSchema]:
        return self._schemas.get(event_type)

    def list_events(self) -> Dict[str, EventSchema]:
        return dict(self._schemas)

    def is_core_event(self, event_type: str) -> bool:
        schema = self._schemas.get(event_type)
        return schema is not None and schema.is_core

__all__ = ["EventRegistry", "EventSchema"]
