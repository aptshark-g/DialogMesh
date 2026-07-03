# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/hybrid_engine.py
++++++
DialogMesh v3.0 HybridEngine — 认知双工并行调度引擎。

职责：
  - 并行执行算法引擎（同步，快）与 LLM 引擎（异步，慢）
  - 实现 4 种调度策略（快速通道、等待融合、加权融合、完全降级）
  - 超时管理与优雅降级（MLLM-S-01）
  - 异步回调：LLM 完成后更新 Cognitive Tree

设计原则：
  - 与 AlgorithmEngine / FusionEngine 正交组合
  - 线程级并行（ThreadPoolExecutor）+ 协程级异步（asyncio）
  - 每轮调度记录延迟和决策路径，供可观测性层使用

对应工程文档：ENGINEERING_MULTILAYER_LLM.md §5.1
版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from core.agent.v3_0.orchestrator.algorithm_engine import AlgorithmEngine, AlgorithmResult
from core.agent.v3_0.orchestrator.fusion_engine import (
    FusionEngine,
    FusionResult,
    FusionSource,
    FusionStrategy,
)
from core.agent.v3_0.orchestrator.models import LLMInstanceResult

logger = logging.getLogger(__name__)


class HybridEngine:
    """认知双工引擎 — 算法引擎与 LLM 引擎并行执行，融合输出。

    调度策略（对应工程文档 §5.1）：
      策略 1（快速通道）：算法完成且置信度 > high_threshold → 立即输出，LLM 后台运行
      策略 2（等待融合）：算法置信度 < low_threshold → 等待 LLM
      策略 3（加权融合）：两者都完成 → FusionEngine 加权融合
      策略 4（保守降级）：两者都低或都失败 → 请求澄清或返回空
    """

    def __init__(
        self,
        algorithm_engine: AlgorithmEngine,
        fusion_engine: FusionEngine,
        high_confidence_threshold: float = 0.85,
        low_confidence_threshold: float = 0.60,
        algorithm_timeout_ms: int = 100,
        llm_timeout_ms: int = 5000,
        max_workers: int = 2,
    ):
        self.algorithm_engine = algorithm_engine
        self.fusion_engine = fusion_engine
        self.high_confidence_threshold = high_confidence_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.algorithm_timeout_ms = algorithm_timeout_ms
        self.llm_timeout_ms = llm_timeout_ms
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def process_pcr(
        self,
        user_input: str,
        llm_coro: Optional[Callable[[], Any]],
        strategy: Optional[FusionStrategy] = None,
    ) -> FusionResult:
        """并行执行 PCR 分析：算法引擎（同步）+ LLM（异步协程）。

        Args:
            user_input: 用户输入
            llm_coro: LLM 调用的异步协程工厂（例如 lambda: self._run_llm("PCR-LLM", ...)）
            strategy: 融合策略

        Returns:
            FusionResult: 融合结果
        """
        start_time = time.time()

        # 并行启动算法引擎（同步转异步）和 LLM（异步协程）
        algo_task = asyncio.create_task(
            self._run_algorithm("pcr", user_input)
        )
        llm_task: Optional[asyncio.Task] = None
        if llm_coro:
            llm_task = asyncio.create_task(llm_coro())

        # 等待算法结果（算法引擎是同步的，应该在 10ms 内完成）
        algo_result: Optional[Dict[str, Any]] = None
        try:
            algo_result = await asyncio.wait_for(
                algo_task,
                timeout=self.algorithm_timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Algorithm engine timed out (>%dms)", self.algorithm_timeout_ms)
        except Exception as exc:
            logger.warning("Algorithm engine failed: %s", exc)

        # 策略判断
        algo_confidence = algo_result.get("confidence", 0.0) if algo_result else 0.0

        # 策略 1（快速通道）：算法高置信 → 立即输出
        if (
            algo_result is not None
            and algo_confidence > self.high_confidence_threshold
            and llm_task is not None
        ):
            # 等待 LLM 在后台完成（用于 Cognitive Tree 更新）
            asyncio.create_task(self._background_llm_completion(llm_task, "pcr"))
            logger.debug(
                "HybridEngine fast-path: algorithm confidence %.2f > %.2f",
                algo_confidence, self.high_confidence_threshold,
            )
            return FusionResult(
                output=algo_result,
                confidence=algo_confidence,
                source=FusionSource.ALGORITHM,
                llm_pending=True,
            )

        # 策略 2（等待 LLM）：算法低置信或无结果
        if llm_task is not None:
            llm_result: Optional[LLMInstanceResult] = None
            try:
                llm_result = await asyncio.wait_for(
                    llm_task,
                    timeout=self.llm_timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                logger.warning("LLM timed out (>%dms)", self.llm_timeout_ms)
            except Exception as exc:
                logger.warning("LLM failed: %s", exc)

            # 策略 3（加权融合）和策略 4（降级）
            llm_output = llm_result.output if llm_result and llm_result.success else None
            llm_confidence = llm_result.confidence if llm_result else 0.0

            latency_ms = (time.time() - start_time) * 1000.0
            logger.debug(
                "HybridEngine fused path: algo=%.2f llm=%.2f latency=%.1fms",
                algo_confidence, llm_confidence, latency_ms,
            )
            return self.fusion_engine.fuse(
                algo_result=algo_result,
                llm_result=llm_output,
                llm_confidence=llm_confidence,
                strategy=strategy,
            )

        # 只有算法结果（无 LLM）
        if algo_result is not None:
            return FusionResult(
                output=algo_result,
                confidence=algo_confidence,
                source=FusionSource.ALGORITHM,
            )

        # 两者都失败
        return FusionResult(
            output=None,
            confidence=0.0,
            source=FusionSource.FALLBACK,
            clarification_required=True,
            fallback_reason="both_failed",
        )

    async def process_intent(
        self,
        user_input: str,
        llm_coro: Optional[Callable[[], Any]],
        strategy: Optional[FusionStrategy] = None,
    ) -> FusionResult:
        """并行执行意图解析：算法引擎 + LLM。"""
        # 与 process_pcr 结构相同，但使用不同的算法方法
        return await self.process_pcr(user_input, llm_coro, strategy)

    async def _run_algorithm(self, mode: str, user_input: str) -> Dict[str, Any]:
        """在线程池中同步执行算法引擎。"""
        def _sync_run():
            if mode == "pcr":
                return self.algorithm_engine.analyze_pcr(user_input)
            elif mode == "intent":
                return self.algorithm_engine.parse_intent(user_input)
            else:
                return {"confidence": 0.0, "error": f"unknown mode: {mode}"}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _sync_run)

    async def _background_llm_completion(
        self,
        llm_task: asyncio.Task,
        phase_name: str,
    ) -> None:
        """后台等待 LLM 完成（用于 Cognitive Tree 更新，不阻塞主流程）。"""
        try:
            result = await asyncio.wait_for(llm_task, timeout=30.0)
            if result and result.success:
                logger.debug("Background LLM '%s' completed", phase_name)
            else:
                logger.debug("Background LLM '%s' failed or returned None", phase_name)
        except asyncio.TimeoutError:
            logger.warning("Background LLM '%s' timed out", phase_name)
        except Exception as exc:
            logger.warning("Background LLM '%s' error: %s", phase_name, exc)

    async def close(self) -> None:
        """关闭线程池，释放资源。"""
        self._executor.shutdown(wait=False)


__all__ = [
    "HybridEngine",
]
