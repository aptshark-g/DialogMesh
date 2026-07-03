# -*- coding: utf-8 -*-
"""
core/agent/config/prompt_config.py
───────────────────────────────────
Agent 配置集中管理器。

将系统提示词、阈值、LLM 参数从代码中剥离，支持：
  - 配置文件热加载（YAML/JSON）
  - 多 LLM 适配（不同 LLM 不同 prompt 风格、token 预算、timeout）
  - 阈值调参无需改代码

配置文件路径（按优先级）：
  1. ~/.memorygraph/config.yaml（用户级覆盖）
  2. 项目根目录 config/agent_config.yaml（项目级默认）
  3. 内置默认值（本文件中的 DEFAULT_CONFIG）

设计原则：
  - 配置是"接口契约"，不是"实现细节"
  - 只暴露 LLM 需要知道的参数含义（阈值语义、格式模板），不暴露算法公式
  - 多 LLM profile：每个 profile 有独立的 system_prompt、max_tokens、reasoning_mode 等
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 内置默认配置（兜底，当外部配置文件不存在时使用）
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG: Dict[str, Any] = {
    # ── 版本 ───────────────────────────────────────────
    "version": "1.0.0",

    # ── 全局阈值（决策层参数，非算法实现）────────────────
    "thresholds": {
        # PCR 触发策略补全器的条件（任一满足即触发）
        "strategy_completer": {
            "confidence_low": 0.3,           # 意图置信度 < 此值触发 LLM
            "noise_complexity_combo": 0.3,   # noise > 此值 AND complexity > 此值
            "advisor_confidence_low": 0.5,   # ADVISOR 意图置信度 < 此值触发
        },
        # 话题树路由阈值
        "topic_tree": {
            "cohesion_continue": 0.6,        # cohesion >= 此值 → continue
            "cohesion_fork": 0.3,            # cohesion < 此值 → new/fork
        },
        # 上下文窗口压缩阈值
        "context_window": {
            "hot_max": 5,                    # Hot 区最大轮数
            "warm_max": 15,                  # Warm 区最大轮数
            "cold_max": 80,                  # Cold 区最大轮数
        },
        # 认知编译器模式切换阈值
        "cognitive_compiler": {
            "fast_max_length": 20,           # 字符数 < 此值 → FAST 模式
            "hybrid_max_length": 100,        # 字符数 < 此值 → HYBRID 模式
            # 超过此值 → FULL 模式
        },
    },

    # ── LLM Profile（多模型适配）──────────────────────────
    "llm_profiles": {
        # 默认 profile（通用云端模型：GPT-4、Kimi、Claude 等）
        "default": {
            "max_tokens": 512,
            "temperature": 0.7,
            "timeout_ms": 30000,
            "reasoning_mode": False,          # 是否 thinking model（如 Qwen 3.5、DeepSeek-R1）
            "response_format_support": True,  # 是否支持 response_format=json_object
            "context_window": 16000,          # 模型上下文窗口（用于预算计算）
        },
        # 本地 thinking model（Qwen 3.5、DeepSeek-R1 等）
        "local_thinking": {
            "max_tokens": 2048,               # thinking model 需要更多输出 token
            "temperature": 0.7,
            "timeout_ms": 120000,             # 本地模型慢，timeout 更长
            "reasoning_mode": True,
            "response_format_support": False,   # llama.cpp 通常不支持 json_object
            "context_window": 16000,
        },
        # 极速模式（简单意图分类、路由决策）
        "fast": {
            "max_tokens": 128,
            "temperature": 0.0,
            "timeout_ms": 10000,
            "reasoning_mode": False,
            "response_format_support": True,
            "context_window": 16000,
        },
        # 健康检查探测
        "health_check": {
            "max_tokens": 1,
            "temperature": 0.0,
            "timeout_ms": 5000,
            "reasoning_mode": False,
            "response_format_support": False,
            "context_window": 16000,
        },
    },

    # ── 系统提示词模板（按角色/模块）───────────────────────
    "system_prompts": {
        # 对话回退模块（conversation_handler）
        "conversation_handler": {
            # 索引卡（角色 + 格式 + 极简规则）
            "index_card": """你是对话回退模块。当规则引擎无法识别意图时，你负责回复。

格式：
分析：用户意图是...，回复策略是...
Final Output: [自然语言回复，80字以内]

规则：
1. 问候→友好回应
2. 问能力→列举扫描/分析/教程/对话
3. 技术未识别→推测并建议
4. 模糊输入→礼貌澄清，不提系统状态
5. 用户困惑→安抚，用大白话解释""",
            # 参数速查字典（和值一起注入 prompt，不是 system prompt）
            "parameter_glossary": {
                "expectation": "系统期望意图。tool=技术操作, advisor=咨询, companion=对话, unknown=未识别（触发你）",
                "confidence": "意图置信度（0~1）。低置信时触发你",
                "cohesion_score": "上下文关联度（0~1）。高值继续话题，低值切换话题",
                "topic_action": "话题树决策。continue=继续, fork=分叉, attach=回溯, new=全新",
                "noise_level": "输入噪声（0~1）。高值表示输入模糊",
                "complexity_level": "输入复杂度（0~1）。高值表示需要分步处理",
            },
        },
        # 策略补全器（strategy_completer）
        "strategy_completer": {
            "index_card": """你是一个策略决策助手。你的输出必须且只能是合法的 JSON 对象。

允许的 action 值："ask_user", "direct_reply", "execute"

示例输出：
{"action": "ask_user", "question": "您想扫描哪个数值？"}
{"action": "direct_reply", "text": "学习内存扫描可以参考以下步骤..."}
{"action": "execute", "blueprint_id": "RULE_FAST_PATH"}

CRITICAL: 只输出 JSON 对象。不要添加任何解释、思考过程、markdown 标记。""",
        },
        # 意图分析器（用于测试/集成）
        "intent_analyzer": {
            "index_card": """你是一个意图分析助手。你的输出必须且只能是合法的 JSON 对象，禁止输出任何解释、思考过程、Markdown 代码块标记。直接输出纯 JSON 文本。""",
        },
        # 路由决策器
        "router": {
            "index_card": """你是一个路由决策助手。根据用户意图选择最合适的蓝图，只输出蓝图 ID 字符串，禁止输出任何解释。""",
        },
    },

    # ── 提示词预算（基于 context_window 的自动计算）───────
    "prompt_budget": {
        # 系统提示词预算（占 context_window 的比例）
        "system_prompt_max_ratio": 0.05,     # 5%（16K → 800 tokens）
        # 历史摘要预算
        "history_max_ratio": 0.10,             # 10%（16K → 1600 tokens）
        # 参数速查字典预算
        "glossary_max_ratio": 0.05,           # 5%（16K → 800 tokens）
        # 输出预算（max_tokens）占剩余空间的比例
        "output_max_ratio": 0.30,             # 30%（16K → 4800 tokens）
        # 预留（给 reasoning tokens、安全余量）
        "reserve_ratio": 0.10,               # 10%（16K → 1600 tokens）
    },

    # ── 观测性阈值（告警触发）────────────────────────────
    "observability": {
        "alert_latency_ms": 200,              # 单轮延迟 > 200ms 告警
        "alert_clarification_rate": 0.3,      # 澄清率 > 30% 告警
        "alert_unknown_rate": 0.5,           # UNKNOWN 率 > 50% 告警
        "alert_confidence_low": 0.5,          # 平均置信度 < 0.5 告警
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 配置类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ThresholdConfig:
    """阈值配置。"""
    strategy_completer: Dict[str, float] = field(default_factory=dict)
    topic_tree: Dict[str, float] = field(default_factory=dict)
    context_window: Dict[str, int] = field(default_factory=dict)
    cognitive_compiler: Dict[str, int] = field(default_factory=dict)


@dataclass
class LLMProfile:
    """LLM Profile 配置。"""
    max_tokens: int = 512
    temperature: float = 0.7
    timeout_ms: int = 30000
    reasoning_mode: bool = False
    response_format_support: bool = True
    context_window: int = 16000


@dataclass
class SystemPromptConfig:
    """系统提示词配置。"""
    index_card: str = ""
    parameter_glossary: Optional[Dict[str, str]] = None


@dataclass
class PromptBudgetConfig:
    """提示词预算配置。"""
    system_prompt_max_ratio: float = 0.05
    history_max_ratio: float = 0.10
    glossary_max_ratio: float = 0.05
    output_max_ratio: float = 0.30
    reserve_ratio: float = 0.10


@dataclass
class ObservabilityConfig:
    """观测性阈值配置。"""
    alert_latency_ms: int = 200
    alert_clarification_rate: float = 0.3
    alert_unknown_rate: float = 0.5
    alert_confidence_low: float = 0.5


@dataclass
class AgentConfig:
    """Agent 全局配置。"""
    version: str = "1.0.0"
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    llm_profiles: Dict[str, LLMProfile] = field(default_factory=dict)
    system_prompts: Dict[str, SystemPromptConfig] = field(default_factory=dict)
    prompt_budget: PromptBudgetConfig = field(default_factory=PromptBudgetConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)

    # 内部原始字典（用于动态访问）
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)


class ConfigManager:
    """
    配置管理器。

    加载优先级：
      1. ~/.memorygraph/config.yaml（用户级覆盖）
      2. 项目根目录 config/agent_config.yaml（项目级默认）
      3. 内置默认值（DEFAULT_CONFIG）
    """

    _instance: Optional["ConfigManager"] = None
    _config: Optional[AgentConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self.reload()

    def reload(self) -> AgentConfig:
        """热加载配置。"""
        raw = self._load_raw()
        self._config = self._parse(raw)
        return self._config

    def get(self) -> AgentConfig:
        """获取当前配置。"""
        if self._config is None:
            self.reload()
        return self._config

    def get_threshold(self, path: str, default: Any = None) -> Any:
        """按路径获取阈值，如 'strategy_completer.confidence_low'。"""
        keys = path.split(".")
        d = self.get().thresholds.__dict__
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def get_llm_profile(self, name: str = "default") -> LLMProfile:
        """获取 LLM Profile。"""
        profiles = self.get().llm_profiles
        if name in profiles:
            return profiles[name]
        # 回退：尝试从名称推断（如含 "thinking" 用 local_thinking）
        if "thinking" in name.lower() or "qwen" in name.lower() or "deepseek" in name.lower():
            return profiles.get("local_thinking", LLMProfile())
        return profiles.get("default", LLMProfile())

    def get_system_prompt(self, role: str) -> SystemPromptConfig:
        """获取系统提示词配置。"""
        return self.get().system_prompts.get(role, SystemPromptConfig())

    def get_prompt_budget(self) -> PromptBudgetConfig:
        """获取提示词预算配置。"""
        return self.get().prompt_budget

    def get_observability(self) -> ObservabilityConfig:
        """获取观测性阈值配置。"""
        return self.get().observability

    # ── 内部加载 ───────────────────────────────────────

    def _load_raw(self) -> Dict[str, Any]:
        """按优先级加载原始配置字典。"""
        config = dict(DEFAULT_CONFIG)  # 深拷贝内置默认

        # 优先级 2：项目根目录 config/agent_config.yaml
        project_root = self._find_project_root()
        project_config = Path(project_root) / "config" / "agent_config.yaml"
        if project_config.exists():
            self._merge_yaml(config, str(project_config))

        # 优先级 1：用户级覆盖 ~/.memorygraph/config.yaml
        user_config = Path.home() / ".memorygraph" / "config.yaml"
        if user_config.exists():
            self._merge_yaml(config, str(user_config))

        return config

    def _find_project_root(self) -> str:
        """查找项目根目录。"""
        # 从当前文件向上查找 marker
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "core").exists() and (parent / "core" / "agent").exists():
                return str(parent)
        # 兜底：向上 3 层
        return str(current.parent.parent.parent)

    def _merge_yaml(self, base: Dict[str, Any], path: str) -> None:
        """将 YAML 文件合并到 base 字典（深度合并）。"""
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                override = yaml.safe_load(f) or {}
            self._deep_merge(base, override)
        except ImportError:
            # 无 yaml 时尝试 JSON
            json_path = path.replace(".yaml", ".json")
            if Path(json_path).exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    override = json.load(f)
                self._deep_merge(base, override)
        except Exception as e:
            print(f"[ConfigManager] 加载配置失败 {path}: {e}")

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """深度合并两个字典。"""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def _parse(self, raw: Dict[str, Any]) -> AgentConfig:
        """将原始字典解析为 AgentConfig dataclass。"""
        return AgentConfig(
            version=raw.get("version", "1.0.0"),
            thresholds=ThresholdConfig(
                strategy_completer=raw.get("thresholds", {}).get("strategy_completer", {}),
                topic_tree=raw.get("thresholds", {}).get("topic_tree", {}),
                context_window=raw.get("thresholds", {}).get("context_window", {}),
                cognitive_compiler=raw.get("thresholds", {}).get("cognitive_compiler", {}),
            ),
            llm_profiles={
                k: LLMProfile(**v)
                for k, v in raw.get("llm_profiles", {}).items()
            },
            system_prompts={
                k: SystemPromptConfig(
                    index_card=v.get("index_card", ""),
                    parameter_glossary=v.get("parameter_glossary"),
                )
                for k, v in raw.get("system_prompts", {}).items()
            },
            prompt_budget=PromptBudgetConfig(
                **raw.get("prompt_budget", {})
            ),
            observability=ObservabilityConfig(
                **{k: v for k, v in raw.get("observability", {}).items() if k in ObservabilityConfig.__dataclass_fields__}
            ),
            _raw=raw,
        )


# 全局单例访问点
config = ConfigManager()


def get_config() -> AgentConfig:
    """快捷访问函数。"""
    return config.get()


def reload_config() -> AgentConfig:
    """热重载配置。"""
    return config.reload()
