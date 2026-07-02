# -*- coding: utf-8 -*-
"""
core/service/v3_0/__init__.py
────────────────────────────
DialogMesh Service Layer v3.0 包初始化。

用途：
- 暴露 Service Layer v3.0 的核心类与工厂函数。
- 提供版本号与快速入口（create_app_v3）。

版本：3.0.0
"""

from __future__ import annotations

__version__ = "3.0.0"

# 延迟导入以避免循环依赖，保留接口引用
__all__ = [
    "create_app_v3",
    "AgentService_v3",
    "WebSocketManager_v3",
    "SessionManager_v3",
    "DialogMeshAPI_v3",
]


def __getattr__(name: str):
    """延迟加载核心类，避免包初始化时的循环导入。"""
    if name == "create_app_v3":
        from core.service.v3_0.app_factory import create_app_v3
        return create_app_v3
    if name == "AgentService_v3":
        from core.service.v3_0.agent_service import AgentService_v3
        return AgentService_v3
    if name == "WebSocketManager_v3":
        from core.service.v3_0.websocket_manager import WebSocketManager_v3
        return WebSocketManager_v3
    if name == "SessionManager_v3":
        from core.service.v3_0.session_manager import SessionManager_v3
        return SessionManager_v3
    if name == "DialogMeshAPI_v3":
        from core.service.v3_0.api import DialogMeshAPI_v3
        return DialogMeshAPI_v3
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
