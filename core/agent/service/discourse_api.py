# -*- coding: utf-8 -*-
"""
core/agent/service/discourse_api.py
──────────────────────────────────
FastAPI 路由模块：暴露 DiscoursePipeline 核心能力。

端点:
  - POST /discourse/process   - 处理单轮输入，返回上下文
  - POST /discourse/preload   - 预加载模型（消除冷启动延迟）
  - GET  /discourse/health    - 健康检查
  - GET  /discourse/blocks    - 获取当前话语块列表
  - POST /discourse/reset     - 重置会话
  - GET  /discourse/config    - 获取当前 Discourse 配置

设计原则:
  - 纯路由层，不持有业务状态（状态由调用方传入的 DiscoursePipeline 实例维护）
  - 所有同步 DiscoursePipeline 操作通过 asyncio.to_thread 放入线程池
  - 可选 FastAPI 依赖（未安装时抛 ImportError）
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

# 可选导入 FastAPI
try:
    from fastapi import APIRouter, HTTPException, Request
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    APIRouter = None
    HTTPException = Exception
    BaseModel = object
    Field = lambda *a, **k: None

try:
    from core.agent.discourse_integration import DiscoursePipeline
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    DiscoursePipeline = None  # type: ignore
    get_discourse_config = None  # type: ignore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型（仅在 FastAPI 可用时定义）
# ═══════════════════════════════════════════════════════════════════════════════

if HAS_FASTAPI:

    class ProcessRequest(BaseModel):
        raw_query: str
        turn_index: int = 0
        session_history: Optional[List[Dict[str, Any]]] = None

    class ProcessResponse(BaseModel):
        status: str
        context: str
        latency_ms: float
        turn_index: int

    class PreloadRequest(BaseModel):
        blocking: bool = False

    class PreloadResponse(BaseModel):
        status: str
        message: str

    class ResetResponse(BaseModel):
        status: str
        message: str

    class HealthResponse(BaseModel):
        status: str
        pipeline_enabled: bool
        encoder_loaded: bool
        block_count: int

    class BlocksResponse(BaseModel):
        block_count: int
        blocks: List[Dict[str, Any]]

    class ConfigResponse(BaseModel):
        config: Dict[str, Any]

else:
    ProcessRequest = None
    ProcessResponse = None
    PreloadRequest = None
    PreloadResponse = None
    ResetResponse = None
    HealthResponse = None
    BlocksResponse = None
    ConfigResponse = None


# ═══════════════════════════════════════════════════════════════════════════════
# 路由创建
# ═══════════════════════════════════════════════════════════════════════════════

def create_discourse_router(pipeline: DiscoursePipeline) -> "APIRouter":
    """创建 Discourse API 路由。

    Args:
        pipeline: 已初始化的 DiscoursePipeline 实例（由调用方管理生命周期）

    Returns:
        APIRouter: FastAPI 路由对象
    """
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required for the discourse API layer. "
            "Install with: pip install fastapi uvicorn"
        )

    if pipeline is None:
        raise ValueError("DiscoursePipeline instance is required")

    router = APIRouter(prefix="/discourse", tags=["discourse"])

    # ── 辅助函数 ──────────────────────────────────────────────────

    def _check_encoder_status() -> bool:
        """检查语义编码器是否已加载。"""
        try:
            from core.agent.compiler.semantic_encoder import _global_encoder
            return _global_encoder is not None and _global_encoder._initialized
        except Exception:
            return False

    # ── 单轮处理 ──────────────────────────────────────────────────

    @router.post("/process", response_model=ProcessResponse)
    async def process_turn(req: ProcessRequest):
        """处理单轮输入，返回话语上下文。"""
        start_ms = time.time() * 1000
        try:
            # 同步 DiscoursePipeline 放入线程池
            context = await asyncio.to_thread(
                pipeline.process_turn,
                req.raw_query,
                req.session_history,
                req.turn_index,
            )
            latency_ms = (time.time() * 1000) - start_ms
            return ProcessResponse(
                status="success",
                context=context,
                latency_ms=latency_ms,
                turn_index=req.turn_index,
            )
        except Exception as e:
            logger.error(f"Discourse process failed: {e}")
            raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    # ── 预加载 ────────────────────────────────────────────────────

    @router.post("/preload", response_model=PreloadResponse)
    async def preload_models(req: PreloadRequest):
        """预加载 BGE 模型、jieba 词典等（消除冷启动延迟）。"""
        try:
            # 同步 preload 放入线程池
            success = await asyncio.to_thread(pipeline.preload, req.blocking)
            if success:
                return PreloadResponse(
                    status="success",
                    message="Preload completed or started (background)" if not req.blocking else "Preload completed",
                )
            return PreloadResponse(
                status="failed",
                message="Preload failed",
            )
        except Exception as e:
            logger.error(f"Discourse preload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Preload error: {e}")

    # ── 健康检查 ──────────────────────────────────────────────────

    @router.get("/health", response_model=HealthResponse)
    async def health_check():
        """话语系统健康检查。"""
        encoder_loaded = _check_encoder_status()
        block_count = pipeline.manager.block_count if pipeline and pipeline.manager else 0
        return HealthResponse(
            status="healthy" if encoder_loaded else "degraded",
            pipeline_enabled=pipeline.enabled if pipeline else False,
            encoder_loaded=encoder_loaded,
            block_count=block_count,
        )

    # ── 获取话语块列表 ────────────────────────────────────────────

    @router.get("/blocks", response_model=BlocksResponse)
    async def get_blocks():
        """获取当前会话的所有话语块列表（概要信息）。"""
        if not pipeline or not pipeline.manager:
            raise HTTPException(status_code=503, detail="Pipeline not initialized")

        blocks = pipeline.manager.get_blocks()
        return BlocksResponse(
            block_count=len(blocks),
            blocks=[b.to_dict() for b in blocks],
        )

    # ── 重置会话 ──────────────────────────────────────────────────

    @router.post("/reset", response_model=ResetResponse)
    async def reset_session():
        """重置会话状态（清空所有话语块）。"""
        if not pipeline:
            raise HTTPException(status_code=503, detail="Pipeline not initialized")

        await asyncio.to_thread(pipeline.reset)
        return ResetResponse(
            status="success",
            message="Session reset successfully",
        )

    # ── 获取配置 ───────────────────────────────────────────────────

    @router.get("/config", response_model=ConfigResponse)
    async def get_config():
        """获取当前 Discourse 配置（序列化后返回）。"""
        if get_discourse_config is None:
            raise HTTPException(status_code=503, detail="Config module not available")

        try:
            config = get_discourse_config()
            config_dict = {}
            if config.encoder:
                config_dict["encoder"] = {
                    "model_path": config.encoder.model_path,
                    "device": config.encoder.device,
                    "max_length": config.encoder.max_length,
                }
            if config.segmenter:
                config_dict["segmenter"] = {
                    "threshold": config.segmenter.threshold,
                    "macro_weight": config.segmenter.macro_weight,
                    "micro_weight": config.segmenter.micro_weight,
                    "bdi_enabled": config.segmenter.bdi_enabled,
                }
            if config.manager:
                config_dict["manager"] = {
                    "hot_turns": config.manager.hot_turns,
                    "cooling_turns": config.manager.cooling_turns,
                    "cold_turns": config.manager.cold_turns,
                    "merge_threshold": config.manager.merge_threshold,
                }
            if config.pipeline:
                config_dict["pipeline"] = {
                    "enabled": config.pipeline.enabled,
                    "hot_turns": config.pipeline.hot_turns,
                }
            return ConfigResponse(config=config_dict)
        except Exception as e:
            logger.error(f"Failed to get config: {e}")
            raise HTTPException(status_code=500, detail=f"Config error: {e}")

    return router
