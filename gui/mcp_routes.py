# -*- coding: utf-8 -*-
"""MemoryGraph MCP Flask Routes (SSE Transport)

提供 Flask Blueprint，将 MCP 协议通过 SSE 暴露给外部客户端。

端点:
  GET  /mcp/sse       — SSE 事件流（客户端接收消息）
  POST /mcp/message  — 客户端发送消息，返回 JSON 响应

Usage:
  from gui.mcp_routes import mcp_bp, init_mcp_server
  
  app = Flask(__name__)
  init_mcp_server(app)
  app.register_blueprint(mcp_bp, url_prefix="/mcp")
"""

import json
import asyncio
import logging
import time
from typing import Optional

from flask import Blueprint, request, jsonify, Response, current_app

from core.mcp_protocol import MCPServer, MCPSSETransport, JSONRPCError
from core.mcp_tools import register_all_tools, register_resources, register_prompts

logger = logging.getLogger(__name__)

# ── Blueprint ──

mcp_bp = Blueprint("mcp", __name__)

# 全局 MCP 状态（单例）
_mcp_server: Optional[MCPServer] = None
_mcp_transport: Optional[MCPSSETransport] = None


# ──────────────────────────────────────────────────────────────
# Initialization
# ──────────────────────────────────────────────────────────────

def init_mcp_server(app=None) -> MCPServer:
    """初始化 MCP Server 并注册所有工具。"""
    global _mcp_server, _mcp_transport
    
    if _mcp_server is not None:
        return _mcp_server
    
    _mcp_server = MCPServer(
        name="memorygraph",
        version="1.0.0"
    )
    
    # 注册所有工具
    register_all_tools(_mcp_server)
    register_resources(_mcp_server)
    register_prompts(_mcp_server)
    
    # 创建 SSE 传输层
    _mcp_transport = MCPSSETransport(_mcp_server)
    
    logger.info("[MCP] Server initialized with %d tools", len(_mcp_server._tools))
    
    if app:
        app.extensions = getattr(app, "extensions", {})
        app.extensions["mcp_server"] = _mcp_server
        app.extensions["mcp_transport"] = _mcp_transport
    
    return _mcp_server


# ──────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────

@mcp_bp.route("/sse")
def mcp_sse():
    """SSE 端点：客户端连接后，建立会话并接收事件流。"""
    global _mcp_transport
    
    if _mcp_transport is None:
        init_mcp_server()
    
    session_id = _mcp_transport.create_session()
    logger.info(f"[MCP] SSE connection established: {session_id}")
    
    def event_stream():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 发送初始事件（会话 ID）
            yield f"event: endpoint\n"
            yield f"data: {json.dumps({'sessionId': session_id})}\n\n"
            
            # 发送事件流
            async def stream():
                queue = _mcp_transport.get_session_queue(session_id)
                if not queue:
                    yield f"event: error\n"
                    yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                    return
                
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"event: message\n"
                        yield f"data: {message}\n\n"
                    except asyncio.TimeoutError:
                        # 发送心跳保持连接
                        yield f": heartbeat\n\n"
                    except Exception as e:
                        logger.exception(f"[MCP] SSE stream error")
                        yield f"event: error\n"
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        break
            
            for msg in loop.run_until_complete(stream()):
                yield msg
                
        finally:
            _mcp_transport.close_session(session_id)
            logger.info(f"[MCP] SSE connection closed: {session_id}")
            loop.close()
    
    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )


@mcp_bp.route("/message", methods=["POST"])
def mcp_message():
    """消息端点：客户端通过 POST 发送 JSON-RPC 消息，返回同步响应。
    
    支持两种模式：
    1. 同步响应：直接返回 JSON-RPC 响应
    2. 异步推送：通过 SSE 发送响应（如果 session_id 提供）
    """
    global _mcp_server, _mcp_transport
    
    if _mcp_server is None:
        init_mcp_server()
    
    body = request.get_data(as_text=True)
    if not body:
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error: empty body"},
            "id": None
        }), 400
    
    session_id = request.headers.get("Mcp-Session-Id") or request.args.get("sessionId")
    
    try:
        # 在事件循环中运行异步处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        response = loop.run_until_complete(_mcp_server.process_message(body))
        loop.close()
        
        if response:
            # 如果有 session_id，同时推送到 SSE 队列
            if session_id and _mcp_transport:
                queue = _mcp_transport.get_session_queue(session_id)
                if queue:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(response),
                        asyncio.get_event_loop()
                    )
            
            return Response(
                response,
                mimetype="application/json",
                status=200
            )
        else:
            # 通知类消息（无响应）
            return Response("", status=202)
            
    except Exception as e:
        logger.exception(f"[MCP] Message processing error")
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            "id": None
        }), 500


@mcp_bp.route("/health")
def mcp_health():
    """健康检查端点。"""
    global _mcp_server
    
    if _mcp_server is None:
        return jsonify({"status": "not_initialized"}), 503
    
    return jsonify({
        "status": "ok",
        "server": _mcp_server.name,
        "version": _mcp_server.version,
        "tools": len(_mcp_server._tools),
        "resources": len(_mcp_server._resources),
        "prompts": len(_mcp_server._prompts),
        "initialized": _mcp_server._initialized,
    })


# ──────────────────────────────────────────────────────────────
# Convenience: Direct Tool Call (non-MCP, for internal use)
# ──────────────────────────────────────────────────────────────

@mcp_bp.route("/tools/<tool_name>", methods=["POST"])
def mcp_tool_direct(tool_name: str):
    """直接调用工具（非 MCP 协议，用于内部 HTTP 调用）。
    
    请求体: JSON 参数对象
    响应: JSON 工具结果
    """
    global _mcp_server
    
    if _mcp_server is None:
        init_mcp_server()
    
    if tool_name not in _mcp_server._tool_handlers:
        return jsonify({
            "error": f"Tool not found: {tool_name}",
            "available_tools": list(_mcp_server._tools.keys())
        }), 404
    
    arguments = request.get_json() or {}
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        contents = loop.run_until_complete(
            _mcp_server._tool_handlers[tool_name](**arguments)
        )
        loop.close()
        
        # 提取文本内容
        result_text = ""
        for c in contents:
            if c.type == "text":
                result_text += c.text
        
        # 尝试解析为 JSON
        try:
            result_json = json.loads(result_text)
        except json.JSONDecodeError:
            result_json = {"text": result_text}
        
        return jsonify({
            "success": True,
            "tool": tool_name,
            "result": result_json
        })
        
    except Exception as e:
        logger.exception(f"[MCP] Direct tool call failed: {tool_name}")
        return jsonify({
            "success": False,
            "tool": tool_name,
            "error": str(e)
        }), 500


# ──────────────────────────────────────────────────────────────
# WebSocket Alternative (for future use)
# ──────────────────────────────────────────────────────────────

# 如果以后需要 WebSocket 支持，可以在这里添加：
# @mcp_bp.route("/ws")
# def mcp_ws():
#     ...
