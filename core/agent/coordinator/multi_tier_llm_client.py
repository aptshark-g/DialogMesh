# 核心:core/agent/coordinator/multi_tier_llm_client.py
"""多层 LLM 客户端 —— 低成本层 + 高端层，自动回退。

架构:
  Tier 1 (Fast/Cheap): 意图分类、路由决策、简单回复
  Tier 2 (Premium): 语义摘要、话题仲裁、复杂分析

回退策略:
  - 首选 Tier 1，失败/超时 → Tier 2
  - 复杂任务直接路由到 Tier 2
  - 如果 Tier 2 也失败，返回 None（调用方回退到规则）
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import openai
except ImportError:
    openai = None  # type: ignore

logger = logging.getLogger(__name__)


# ── 默认配置 ───────────────────────────────────────────────────

DEFAULT_TIER1_CONFIG = {
    "name": "fast",
    "base_url": "http://localhost:1234/v1",
    "api_key": "lmstudio",
    "model": "auto",
    "timeout": 10.0,
    "max_tokens": 512,
    "temperature": 0.1,
    "description": "本地小模型/Flash 低成本模型",
}

DEFAULT_TIER2_CONFIG = {
    "name": "premium",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "${DEEPSEEK_API_KEY}",
    "model": "deepseek-v4",
    "timeout": 60.0,
    "max_tokens": 2048,
    "temperature": 0.7,
    "description": "DeepSeek V4 高端模型",
}


# ── 全局单例 ───────────────────────────────────────────────────

_multi_tier_client: Optional[MultiTierLLMClient] = None


def get_multi_tier_client(config_path: Optional[str] = None) -> MultiTierLLMClient:
    """获取全局多层 LLM 客户端实例。"""
    global _multi_tier_client
    if _multi_tier_client is None:
        _multi_tier_client = MultiTierLLMClient(config_path)
    return _multi_tier_client


def reset_multi_tier_client():
    """重置全局实例（测试/配置热加载用）。"""
    global _multi_tier_client
    _multi_tier_client = None


# ── 任务类型到 tier 的映射 ──────────────────────────────────────

TASK_TIER_MAP = {
    # 简单任务 → Tier 1 (fast)
    "intent_classification": 1,
    "simple_reply": 1,
    "routing_decision": 1,
    "topic_overlap": 1,  # 算法为主，LLM 辅助

    # 复杂任务 → Tier 2 (premium)
    "semantic_summary": 2,
    "topic_arbitration": 2,
    "topic_audit": 2,
    "complex_analysis": 2,
    "code_generation": 2,
    "long_context": 2,
    "reasoning": 2,

    # 默认：Tier 1
    "default": 1,
}


def resolve_env_value(value: str) -> str:
    """解析配置值，支持 ${ENV_VAR} 语法。"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        env_val = os.environ.get(env_var)
        if env_val is None:
            logger.warning(f"Environment variable {env_var} not set, config value unresolved")
            return value  # 返回原始值，后续调用会失败
        return env_val
    return value


class LLMProvider:
    """单个 LLM Provider 封装。"""

    def __init__(self, config: Dict[str, Any]):
        self.name = config.get("name", "unknown")
        self.base_url = config.get("base_url", "http://localhost:1234/v1")
        self.api_key = resolve_env_value(config.get("api_key", "lmstudio"))
        self.model = config.get("model", "auto")
        self.timeout = float(config.get("timeout", 10.0))
        self.max_tokens = int(config.get("max_tokens", 512))
        self.temperature = float(config.get("temperature", 0.1))
        self.description = config.get("description", "")
        self.model_priority = config.get("model_priority", [])  # 可选：模型优先级列表

        self._client: Optional[Any] = None
        self._detected_models: List[str] = []
        self._initialized = False
        self._health_failures = 0
        self._max_health_failures = 3

    def _get_openai_client(self) -> Optional[Any]:
        """获取 OpenAI 客户端。"""
        if openai is None:
            logger.error("openai package not installed")
            return None
        if self._client is None:
            self._client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    def is_available(self) -> bool:
        """检查 provider 是否可用。"""
        if self._health_failures >= self._max_health_failures:
            return False
        if not self._initialized:
            self._health_check()
        return self._health_failures < self._max_health_failures

    def _health_check(self) -> bool:
        """健康检查：尝试列出模型。"""
        client = self._get_openai_client()
        if client is None:
            self._health_failures += 1
            return False
        try:
            models = client.models.list(timeout=2.0)
            self._detected_models = [m.id for m in models.data]
            self._initialized = True
            logger.info(
                f"Provider {self.name} health OK: {len(self._detected_models)} models, "
                f"url={self.base_url}"
            )
            return True
        except Exception as e:
            self._health_failures += 1
            logger.warning(
                f"Provider {self.name} health check failed ({self._health_failures}/{self._max_health_failures}): {e}"
            )
            return False

    def _select_model(self) -> str:
        """选择模型：auto → 优先选择小模型/白名单。"""
        if self.model != "auto":
            return self.model
        if not self._detected_models:
            return "auto"  #  fallback

        # 如果有白名单，按优先级选择
        if self.model_priority:
            for preferred in self.model_priority:
                if preferred in self._detected_models:
                    return preferred

        # 自动选择：排除 embedding，优先小参数
        candidates = []
        for m in self._detected_models:
            if "embed" in m.lower():
                continue
            # 简单估算参数大小
            size = self._estimate_model_size(m)
            candidates.append((m, size))

        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]

        return self._detected_models[0]

    @staticmethod
    def _estimate_model_size(model_name: str) -> int:
        """从模型名称估算参数大小（B）。"""
        import re
        name = model_name.lower()
        patterns = [r'(\d+\.?\d*)b', r'(\d+\.?\d*)-b', r'-(\d+\.?\d+)b-']
        for pat in patterns:
            match = re.search(pat, name)
            if match:
                try:
                    return int(float(match.group(1)))
                except ValueError:
                    continue
        if "nano" in name or "small" in name or "tiny" in name or "flash" in name:
            return 1
        if "mini" in name:
            return 4
        if "medium" in name:
            return 10
        if "large" in name:
            return 30
        return 100  # 默认大值

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        parse_json: bool = False,
    ) -> Optional[str]:
        """调用 LLM，返回文本结果。"""
        if not self.is_available():
            return None

        client = self._get_openai_client()
        if client is None:
            return None

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model = self._select_model()
        start_time = time.time()

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature,
                timeout=self.timeout,
            )
            result = response.choices[0].message.content.strip()
            latency = time.time() - start_time

            # 解析 JSON 如果请求
            if parse_json:
                result = self._parse_json(result)

            logger.info(
                f"Provider {self.name} ({model}): {latency:.2f}s, "
                f"result_len={len(result)}, prompt_len={len(prompt)}"
            )
            return result

        except Exception as e:
            latency = time.time() - start_time
            self._health_failures += 1
            logger.warning(
                f"Provider {self.name} call failed after {latency:.2f}s: {e}"
            )
            return None

    @staticmethod
    def _parse_json(text: str) -> Optional[str]:
        """从文本中提取 JSON 部分。"""
        import json
        try:
            json_start = text.find("{")
            json_end = text.rfind("}")
            if json_start >= 0 and json_end > json_start:
                return json.dumps(
                    json.loads(text[json_start:json_end + 1]),
                    ensure_ascii=False
                )
        except json.JSONDecodeError:
            pass
        return text


class MultiTierLLMClient:
    """多层 LLM 客户端：Tier 1 (Fast) + Tier 2 (Premium)。"""

    def __init__(self, config_path: Optional[str] = None):
        self.tiers: Dict[int, LLMProvider] = {}
        self.task_map = dict(TASK_TIER_MAP)
        self._load_config(config_path)
        self._stats = {"tier1_calls": 0, "tier2_calls": 0, "fallbacks": 0, "failures": 0}

    def _load_config(self, config_path: Optional[str] = None):
        """加载配置文件。"""
        # 1. 尝试从 YAML 加载
        config = self._load_yaml_config(config_path)

        # 2. 环境变量覆盖
        tier1_cfg = self._build_tier_config(config, "tier1", DEFAULT_TIER1_CONFIG)
        tier2_cfg = self._build_tier_config(config, "tier2", DEFAULT_TIER2_CONFIG)

        # 3. 创建 provider
        self.tiers[1] = LLMProvider(tier1_cfg)
        self.tiers[2] = LLMProvider(tier2_cfg)

        # 4. 加载任务映射
        if config and "task_routing" in config:
            self.task_map.update(config["task_routing"])

    def _load_yaml_config(self, config_path: Optional[str]) -> Optional[Dict[str, Any]]:
        """加载 YAML 配置文件。

        优先级（从高到低）：
        1. 显式传入的 config_path 参数
        2. 用户级 ~/.memorygraph/config.yaml
        3. 项目级 config/user_config.yaml（用户独立配置）
        4. 项目级 config/agent_config.yaml（默认值）
        """
        import yaml
        from pathlib import Path

        paths = []
        if config_path:
            paths.append(Path(config_path))
        else:
            # 从 multi_tier_llm_client.py 到项目根：core/agent/coordinator/ -> core/agent/ -> core/ -> MemoryGraph/
            project_root = Path(__file__).parent.parent.parent.parent
            paths.extend([
                Path.home() / ".memorygraph" / "config.yaml",           # 用户级（最优先）
                project_root / "config" / "user_config.yaml",             # 项目级用户配置
                project_root / "config" / "agent_config.yaml",            # 项目级默认
            ])

        for path in paths:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    logger.info(f"Loaded config from {path}")
                    return data or {}
                except Exception as e:
                    logger.warning(f"Failed to load config from {path}: {e}")
        return None

    def _build_tier_config(self, config: Optional[Dict], tier_name: str, defaults: Dict) -> Dict:
        """构建 tier 配置：默认值 + 配置文件 + 环境变量。

        支持两种配置格式：
        1. 标准格式：llm_providers.tier1 / llm_providers.tier2
        2. 简化格式：顶层 tier1 / tier2（用户配置文件中可直接写）
        """
        cfg = dict(defaults)

        # 从配置文件读取（两种格式都支持）
        if config:
            # 格式 1: llm_providers.tier1
            if "llm_providers" in config:
                providers = config["llm_providers"]
                if tier_name in providers:
                    cfg.update(providers[tier_name])
            # 格式 2: 顶层 tier1（简化格式，用户配置常用）
            if tier_name in config:
                cfg.update(config[tier_name])

        # 环境变量覆盖（大写）
        env_prefix = f"LLM_{tier_name.upper()}_"
        env_map = {
            "base_url": env_prefix + "BASE_URL",
            "api_key": env_prefix + "API_KEY",
            "model": env_prefix + "MODEL",
            "timeout": env_prefix + "TIMEOUT",
            "max_tokens": env_prefix + "MAX_TOKENS",
            "temperature": env_prefix + "TEMPERATURE",
        }

        for key, env_var in env_map.items():
            val = os.environ.get(env_var)
            if val is not None:
                if key in ("timeout", "temperature"):
                    try:
                        cfg[key] = float(val)
                    except ValueError:
                        pass
                elif key == "max_tokens":
                    try:
                        cfg[key] = int(val)
                    except ValueError:
                        pass
                else:
                    cfg[key] = val

        return cfg

    def invoke(
        self,
        prompt: str,
        task_type: str = "default",
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        parse_json: bool = False,
        allow_fallback: bool = True,
    ) -> Optional[str]:
        """调用多层 LLM，自动路由到合适的 tier。

        Args:
            prompt: 用户提示词
            task_type: 任务类型（决定路由到哪个 tier）
            system_prompt: 系统提示词
            max_tokens: 覆盖默认 max_tokens
            temperature: 覆盖默认 temperature
            parse_json: 是否解析 JSON
            allow_fallback: 是否允许 tier 间回退

        Returns:
            LLM 输出文本，失败返回 None
        """
        # 确定首选 tier
        preferred_tier = self.task_map.get(task_type, 1)

        # 尝试首选 tier
        provider = self.tiers.get(preferred_tier)
        if provider and provider.is_available():
            result = provider.invoke(
                prompt, system_prompt, max_tokens, temperature, parse_json
            )
            if result is not None:
                self._stats[f"tier{preferred_tier}_calls"] += 1
                return result

        # 回退到另一 tier
        if allow_fallback:
            fallback_tier = 2 if preferred_tier == 1 else 1
            fallback_provider = self.tiers.get(fallback_tier)
            if fallback_provider and fallback_provider.is_available():
                logger.info(
                    f"Tier {preferred_tier} failed, falling back to tier {fallback_tier} "
                    f"for task {task_type}"
                )
                result = fallback_provider.invoke(
                    prompt, system_prompt, max_tokens, temperature, parse_json
                )
                if result is not None:
                    self._stats["fallbacks"] += 1
                    self._stats[f"tier{fallback_tier}_calls"] += 1
                    return result

        self._stats["failures"] += 1
        logger.error(f"All tiers failed for task {task_type}")
        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        tier1 = self.tiers.get(1)
        tier2 = self.tiers.get(2)
        return {
            "tier1": tier1.name if tier1 else "N/A",
            "tier2": tier2.name if tier2 else "N/A",
            "tier1_available": tier1.is_available() if tier1 else False,
            "tier2_available": tier2.is_available() if tier2 else False,
            **self._stats,
        }

    def get_provider_for_task(self, task_type: str) -> Optional[LLMProvider]:
        """获取指定任务类型的 provider。"""
        tier = self.task_map.get(task_type, 1)
        # 确保 tier 是整数（配置文件中可能读为字符串）
        if isinstance(tier, dict):
            # 如果 task_map 中存的是 dict（配置错误），使用默认值
            tier = 1
        else:
            try:
                tier = int(tier)
            except (ValueError, TypeError):
                tier = 1
        return self.tiers.get(tier)


# ── 便捷函数：直接调用（兼容现有接口）──────────────────────────

def invoke_llm(
    prompt: str,
    task_type: str = "default",
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    parse_json: bool = False,
    use_cache: bool = True,
) -> Optional[str]:
    """便捷函数：直接调用多层 LLM（支持缓存）。"""
    # 缓存检查
    if use_cache:
        try:
            from core.infrastructure.cache_layer import get_response_cache
            cache = get_response_cache()
            if cache.should_cache(task_type):
                key = cache.make_key(prompt, system_prompt, task_type, max_tokens=max_tokens, temperature=temperature)
                cached = cache.get(key)
                if cached is not None:
                    logger.info(f"Cache hit for {task_type}: {key[:8]}...")
                    return cached
        except Exception as e:
            logger.debug(f"Cache check failed: {e}")

    client = get_multi_tier_client()
    result = client.invoke(
        prompt=prompt,
        task_type=task_type,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        parse_json=parse_json,
    )

    # 缓存写入
    if use_cache and result is not None:
        try:
            from core.infrastructure.cache_layer import get_response_cache
            cache = get_response_cache()
            if cache.should_cache(task_type):
                key = cache.make_key(prompt, system_prompt, task_type, max_tokens=max_tokens, temperature=temperature)
                cache.set(key, result)
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

    return result
