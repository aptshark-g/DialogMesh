# -*- coding: utf-8 -*-
"""
main.py
───────
服务启动入口（生产优化）。

用法:
  python main.py                    # 默认 SQLite + 内存 session
  python main.py --store redis      # Redis 存储
  python main.py --store async_sqlite --db-path ./data/sessions.db

配置优先级:
  1. 命令行参数
  2. 环境变量 (AGENT_*) 
  3. 配置文件 config/agent.yaml
  4. 默认值
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Optional

# 确保 core 在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.service.agent_service import AgentService
from core.agent.service.async_session_manager import AsyncSessionManager
from core.agent.service.rate_limiter import RateLimiter
from core.agent.service.request_queue import RequestQueue
from core.agent.service.stores.sqlite import SQLiteSessionStore
from core.agent.service.stores.async_sqlite import AsyncSQLiteSessionStore
from core.agent.service.stores.redis import RedisSessionStore
from core.agent.llm_providers.provider_factory import get_default_router


def load_config():
    """加载配置。"""
    parser = argparse.ArgumentParser(description="Cognitive Router Agent Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--store", choices=["memory", "sqlite", "async_sqlite", "redis"],
                        default="memory", help="Session storage backend")
    parser.add_argument("--db-path", default="sessions.db", help="SQLite database path")
    parser.add_argument("--redis-host", default="localhost", help="Redis host")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--ttl", type=int, default=3600, help="Session TTL (seconds)")
    parser.add_argument("--workers", type=int, default=1, help="Uvicorn workers")
    parser.add_argument("--reload", action="store_true", help="Auto reload (dev only)")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM router")
    parser.add_argument("--llm-provider", choices=["mock", "hybrid", "openai", "local"],
                        default="mock", help="LLM provider type")
    parser.add_argument("--log-level", default="info", help="Logging level")
    return parser.parse_args()


def create_store(config):
    """根据配置创建存储。"""
    store_type = config.store
    if store_type == "memory":
        return None
    elif store_type == "sqlite":
        # 同步 SQLite（简单单机）
        return SQLiteSessionStore(db_path=config.db_path)
    elif store_type == "async_sqlite":
        # 异步 SQLite（FastAPI 推荐）
        return AsyncSQLiteSessionStore(db_path=config.db_path)
    elif store_type == "redis":
        return RedisSessionStore(
            host=config.redis_host,
            port=config.redis_port,
            ttl_seconds=config.ttl,
        )
    else:
        raise ValueError(f"Unknown store type: {store_type}")


async def create_agent_service(config):
    """创建并初始化 AgentService。"""
    # 1. 创建核心引擎
    pcr = RuleBasedPCR()
    parser = IntentParser()

    # 2. 创建存储
    store = create_store(config)

    # 3. 创建异步会话管理器
    session_manager = AsyncSessionManager(
        store=store,
        ttl_seconds=config.ttl,
    )
    await session_manager.start()

    # 4. 创建限流器
    rate_limiter = RateLimiter()

    # 5. 创建 LLM Provider（可选）
    llm_provider = None
    if not config.no_llm:
        if config.llm_provider == "mock":
            from core.agent.llm_providers.mock_provider import MockProvider
            llm_provider = MockProvider("default-mock", {
                "response_text": "[MOCK]",
            })
        elif config.llm_provider == "hybrid":
            llm_provider = get_default_router()
        # openai / local 需配置 API key / 模型路径

    # 6. 创建服务
    service = AgentService(
        pcr=pcr,
        parser=parser,
        session_manager=session_manager,  # 注意: 同步 SessionManager 需要适配
        rate_limiter=rate_limiter,
        llm_provider=llm_provider,
    )

    return service, session_manager


async def main():
    config = load_config()

    # 创建服务
    service, session_manager = await create_agent_service(config)

    # 尝试创建 FastAPI 应用
    try:
        from core.agent.service.api import create_app
        app = create_app(service)
    except ImportError as e:
        print(f"FastAPI not available: {e}")
        print("Install with: pip install fastapi uvicorn")
        sys.exit(1)

    # 启动 uvicorn
    import uvicorn
    print(f"Starting Cognitive Router Agent Service v2.4.0")
    print(f"  Store: {config.store}")
    print(f"  LLM: {config.llm_provider if not config.no_llm else 'disabled'}")
    print(f"  Host: {config.host}:{config.port}")
    print(f"  Session TTL: {config.ttl}s")

    # 启动时清理过期会话
    evicted = await session_manager._evict_expired()
    if evicted > 0:
        print(f"  Evicted {evicted} expired sessions on startup")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        workers=config.workers if not config.reload else 1,
        reload=config.reload,
        log_level=config.log_level,
    )


if __name__ == "__main__":
    asyncio.run(main())
