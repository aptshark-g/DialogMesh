# core/agent/coordinator/small_model_client.py
"""本地小模型客户端 —— 封装 LMStudio/OpenAI 兼容接口，支持缓存、批处理、超时回退。

设计原则：
- 延迟目标：短 prompt (<200 tokens) 在 CPU 上 < 100ms
- 缓存：相同 prompt 结果复用，避免重复调用
- 超时：默认 2s，超时自动回退到规则
- 批处理：支持批量 prompt 合并为一次调用（减少 LLM 调用次数）
- 中文优化：prompt 使用中文，小模型中文理解更好

使用方式：
    from core.agent.coordinator import get_small_model_client

    client = get_small_model_client()
    result = client.invoke("判断以下两段对话是否同一话题...")
    if result is None:
        # 回退到规则处理
        pass
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── 默认配置 ───────────────────────────────────────────────────

DEFAULT_SMALL_MODEL_CONFIG = {
    "base_url": "http://localhost:1234/v1",
    "api_key": "lmstudio",
    "model": "auto",         # auto = 自动检测可用模型
    "timeout": 10.0,         # 超时秒数（CPU 上小模型可能需要几秒）
    "max_tokens": 300,       # 覆盖 reasoning tokens + 实际输出
    "temperature": 0.1,        # 低温度，确定性输出
    "cache_size": 1000,      # 缓存条目上限
    "batch_enabled": False,  # 批处理（待实现）
    "auto_no_think": True,   # 自动为 Qwen3 系列添加 /no_think
}


# ── 全局单例 ───────────────────────────────────────────────────

_small_model_client: Optional[SmallModelClient] = None


def get_small_model_client(config: Optional[Dict[str, Any]] = None) -> SmallModelClient:
    """获取全局小模型客户端实例。"""
    global _small_model_client
    if _small_model_client is None:
        _small_model_client = SmallModelClient(config)
    return _small_model_client


def reset_small_model_client():
    """重置全局实例（测试/配置热加载用）。"""
    global _small_model_client
    _small_model_client = None


class SmallModelClient:
    """本地小模型客户端。

    支持 OpenAI 兼容接口（LMStudio、Ollama、vLLM 等）。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = dict(DEFAULT_SMALL_MODEL_CONFIG)
        if config:
            cfg.update(config)

        # 从环境变量覆盖
        env_overrides = {
            "base_url": os.environ.get("LMSTUDIO_HOST", os.environ.get("SMALL_MODEL_BASE_URL")),
            "model": os.environ.get("SMALL_MODEL_MODEL", os.environ.get("SMALL_MODEL_MODEL")),
            "timeout": os.environ.get("SMALL_MODEL_TIMEOUT"),
            "api_key": os.environ.get("SMALL_MODEL_API_KEY"),
        }
        for key, value in env_overrides.items():
            if value is not None:
                if key == "timeout":
                    try:
                        cfg[key] = float(value)
                    except ValueError:
                        pass
                else:
                    cfg[key] = value

        self.base_url = cfg["base_url"]
        self.api_key = cfg["api_key"]
        self.model = cfg["model"]
        self.timeout = cfg["timeout"]
        self.max_tokens = cfg["max_tokens"]
        self.temperature = cfg["temperature"]
        self.cache_size = cfg["cache_size"]
        self.auto_no_think = cfg.get("auto_no_think", True)

        self._client = None
        self._available: Optional[bool] = None
        self._cache: Dict[str, str] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._detected_models: List[str] = []
        self._total_latency = 0.0
        self._call_count = 0

        # 健康检查时自动检测模型
        if self.is_available:
            self._detect_and_select_model()

        logger.info(
            f"SmallModelClient initialized: model={self.model}, "
            f"base_url={self.base_url}, timeout={self.timeout}s, "
            f"detected={self._detected_models}"
        )

    @property
    def is_available(self) -> bool:
        """检测小模型服务是否可用（懒检测，只执行一次）。"""
        if self._available is None:
            self._available = self._check_health()
        return self._available

    def _check_health(self) -> bool:
        """健康检查：尝试获取模型列表。"""
        try:
            client = self._get_openai_client()
            if client is None:
                return False
            # 轻量检测：尝试获取模型列表
            models = client.models.list(timeout=1.0)
            logger.info(f"Small model health check OK: {len(models.data)} models available")
            return True
        except Exception as e:
            logger.warning(f"Small model health check failed: {e}")
            return False

    def _get_openai_client(self):
        """延迟初始化 OpenAI 客户端。"""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
            except ImportError:
                logger.error("openai package not installed, small model unavailable")
                return None
        return self._client

    def _hash_prompt(self, prompt: str) -> str:
        """生成 prompt 的缓存 key。"""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    def _manage_cache(self, key: str, value: str) -> None:
        """LRU 缓存管理。"""
        if len(self._cache) >= self.cache_size:
            # 简单 FIFO：移除最早的一个
            try:
                self._cache.pop(next(iter(self._cache)))
            except StopIteration:
                pass
        self._cache[key] = value

    def _detect_and_select_model(self) -> None:
        """检测可用模型并自动选择最优小模型。"""
        try:
            client = self._get_openai_client()
            if client is None:
                return
            models = client.models.list(timeout=2.0)
            self._detected_models = [m.id for m in models.data]
            logger.info(f"Detected models: {self._detected_models}")

            # 如果当前模型不在列表中，自动选择最优
            if self.model not in self._detected_models:
                best_model = self._select_best_model(self._detected_models)
                if best_model:
                    logger.info(f"Auto-selected model: {best_model} (was: {self.model})")
                    self.model = best_model
                else:
                    logger.warning(f"Model {self.model} not available, using first available: {self._detected_models[0]}")
                    self.model = self._detected_models[0]
        except Exception as e:
            logger.warning(f"Model detection failed: {e}")

    def _select_best_model(self, models: List[str]) -> Optional[str]:
        """从可用模型中选择最优小模型。

        策略：
        1. 优先选择小参数模型（<5B 视为"小模型"）
        2. 排除 embedding 模型
        3. 排除已知的超大模型（>30B）
        """
        candidates = []
        for m in models:
            # 排除 embedding 模型
            if "embedding" in m.lower() or "embed" in m.lower():
                continue
            # 估算参数大小
            size = self._estimate_model_size(m)
            candidates.append((m, size))

        if not candidates:
            return None

        # 按参数大小排序，优先选择 <5B 的模型
        candidates.sort(key=lambda x: x[1])
        best = candidates[0]
        logger.info(f"Model candidates ranked: {candidates}")
        return best[0]

    @staticmethod
    def _estimate_model_size(model_name: str) -> int:
        """从模型名称估算参数大小（B），用于排序。"""
        import re
        name = model_name.lower()
        # 常见命名模式
        patterns = [
            r'(\d+\.?\d*)b',
            r'(\d+\.?\d*)-b',
            r'-(\d+\.?\d+)b-',
        ]
        for pat in patterns:
            match = re.search(pat, name)
            if match:
                try:
                    return int(float(match.group(1)))
                except ValueError:
                    continue
        # 特殊名称映射
        if "nano" in name or "small" in name or "tiny" in name:
            return 2
        if "mini" in name:
            return 4
        if "medium" in name:
            return 10
        if "large" in name:
            return 30
        # 默认大值，排在后面
        return 100

    def _is_qwen3_model(self) -> bool:
        """判断当前模型是否为 Qwen3 系列（有 reasoning 模式）。"""
        return "qwen3" in self.model.lower() or "qwen-3" in self.model.lower()

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """构建消息列表，自动处理 Qwen3 的 /no_think。"""
        messages = []
        if system_prompt:
            # Qwen3 系列：/no_think 需要放在 system prompt 或 user prompt 中
            # 实验表明：放在 user message 开头更稳定
            if self.auto_no_think and self._is_qwen3_model():
                # 用户消息中强制关闭 thinking
                prompt = "/no_think\n" + prompt
                # system prompt 不变，保持简洁
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({"role": "system", "content": system_prompt})
        else:
            if self.auto_no_think and self._is_qwen3_model():
                # 无 system prompt 时，创建一个不啰嗦的 system prompt 并加上 /no_think
                messages.append({"role": "system", "content": "直接回答，不要解释。"})
                prompt = "/no_think\n" + prompt
        messages.append({"role": "user", "content": prompt})
        return messages

    def invoke(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        parse_json: bool = False,
    ) -> Optional[str]:
        """调用小模型，返回文本结果。

        Args:
            prompt: 用户 prompt（中文，简洁）
            max_tokens: 覆盖默认最大 token 数
            temperature: 覆盖默认温度
            system_prompt: 可选系统提示词
            parse_json: 是否尝试解析结果为 JSON

        Returns:
            模型输出字符串，失败时返回 None（调用方应回退到规则）
        """
        if not self.is_available:
            logger.debug("Small model unavailable, skipping")
            return None

        # 1. 检查缓存
        cache_key = self._hash_prompt(prompt)
        if cache_key in self._cache:
            self._cache_hits += 1
            logger.debug(f"Cache hit: {cache_key[:8]}...")
            return self._cache[cache_key]

        self._cache_misses += 1

        # 2. 构建消息（自动处理 Qwen3 /no_think）
        messages = self._build_messages(prompt, system_prompt)

        # 3. 调用
        client = self._get_openai_client()
        if client is None:
            return None

        start_time = time.time()
        try:
            messages = self._build_messages(prompt, system_prompt)
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature,
                timeout=self.timeout,
            )
            result = response.choices[0].message.content.strip()
            latency = time.time() - start_time
            self._total_latency += latency
            self._call_count += 1

            # 监控 reasoning tokens（Qwen3 系列）
            usage = response.usage
            reasoning_tok = getattr(usage, "completion_tokens_details", None)
            if reasoning_tok and hasattr(reasoning_tok, "reasoning_tokens"):
                rt = reasoning_tok.reasoning_tokens
                if rt and rt > 0:
                    logger.info(
                        f"Small model call: {latency:.3f}s, "
                        f"model={self.model}, reasoning_tokens={rt}, "
                        f"content_len={len(result)}, prompt_len={len(prompt)}"
                    )
            else:
                logger.debug(
                    f"Small model call: {latency:.3f}s, "
                    f"model={self.model}, result_len={len(result)}, prompt_len={len(prompt)}"
                )

            # 4. 解析 JSON（如果请求）
            if parse_json:
                try:
                    # 尝试提取 JSON 部分
                    json_start = result.find("{")
                    json_end = result.rfind("}")
                    if json_start >= 0 and json_end > json_start:
                        result = json.loads(result[json_start:json_end + 1])
                        result = json.dumps(result, ensure_ascii=False)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from result: {result[:100]}")

            # 5. 缓存
            self._manage_cache(cache_key, result)
            return result

        except Exception as e:
            latency = time.time() - start_time
            logger.warning(f"Small model call failed after {latency:.3f}s: {e}")
            return None

    def invoke_batch(
        self,
        prompts: List[str],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> List[Optional[str]]:
        """批量调用小模型（串行，未来可优化为并行/合并）。"""
        results = []
        for prompt in prompts:
            results.append(self.invoke(prompt, max_tokens, temperature))
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息。"""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        avg_latency = self._total_latency / self._call_count if self._call_count > 0 else 0.0
        return {
            "available": self.is_available,
            "model": self.model,
            "detected_models": self._detected_models,
            "base_url": self.base_url,
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": round(hit_rate, 3),
            "avg_latency_ms": round(avg_latency * 1000, 1),
            "call_count": self._call_count,
        }
