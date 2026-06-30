# core/agent/config/discourse_config.py
"""Discourse Block Tree 配置系统。

支持三层配置（优先级降序）：
1. 环境变量（MEMORYGRAPH_* 前缀）
2. 用户配置文件（~/.config/memorygraph/discourse.yaml）
3. 默认配置（代码内嵌）

使用方式：
    from core.agent.config.discourse_config import get_discourse_config

    config = get_discourse_config()
    threshold = config.segmenter.threshold
    model_path = config.encoder.model_path
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 默认配置 ───────────────────────────────────────────────────

_DEFAULT_CONFIG: Dict[str, Any] = {
    # 语义编码器
    "encoder": {
        "model_path": "models/BAAI/bge-small-zh",
        "device": "auto",  # auto / cpu / cuda
        "cache_size": 10000,
        "max_length": 512,
    },
    # 语义解析器
    "parser": {
        "ner_enabled": True,
        "bge_filter_enabled": True,
        "bge_filter_threshold": 0.5,
    },
    # 语法分解器
    "decomposer": {
        "complex_clause_length": 30,
        "max_clauses_per_input": 5,
        "hybrid_path_enabled": True,
        "semantic_parser_enabled": True,
    },
    # 头文件注入器
    "injector": {
        "context_window_size": 5,
        "domain": "default",
        "kb_path": None,  # 默认使用 ~/.memorygraph/kb/header_kb.json
        "semantic_parser_enabled": True,
    },
    # 话语块切分器
    "segmenter": {
        "threshold": 0.5,
        "macro_weight": 0.6,
        "micro_weight": 0.4,
        "bdi_enabled": True,
    },
    # 话语块管理器
    "manager": {
        "hot_turns": 5,
        "cooling_turns": 5,  # 5-10 轮为 cooling
        "cold_turns": 10,    # > 10 轮为 cold
        "merge_threshold": 0.55,
    },
    # 摘要引擎
    "summary": {
        "v3_trigger_turn_count": 5,
    },
    # 上下文构建器
    "context": {
        "hot_turns": 5,
    },
    # 管道集成
    "pipeline": {
        "enabled": True,
        "hot_turns": 5,
    },
    # 模型下载
    "model_download": {
        "bge_model_id": "BAAI/bge-small-zh",
        "ner_model_id": "damo/nlp_raner_named-entity-recognition_chinese-base-news",
        "cache_dir": "models",
    },
    # 日志
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "json": False,
    },
}


# ── 数据类 ───────────────────────────────────────────────────

@dataclass
class EncoderConfig:
    model_path: str = "models/BAAI/bge-small-zh"
    device: str = "auto"
    cache_size: int = 10000
    max_length: int = 512

    @property
    def resolved_device(self) -> str:
        if self.device == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return self.device


@dataclass
class ParserConfig:
    ner_enabled: bool = True
    bge_filter_enabled: bool = True
    bge_filter_threshold: float = 0.5


@dataclass
class DecomposerConfig:
    complex_clause_length: int = 30
    max_clauses_per_input: int = 5
    hybrid_path_enabled: bool = True
    semantic_parser_enabled: bool = True


@dataclass
class InjectorConfig:
    context_window_size: int = 5
    domain: str = "default"
    kb_path: Optional[str] = None
    semantic_parser_enabled: bool = True

    @property
    def resolved_kb_path(self) -> str:
        if self.kb_path:
            return self.kb_path
        return os.path.expanduser("~/.memorygraph/kb/header_kb.json")


@dataclass
class SegmenterConfig:
    threshold: float = 0.5
    macro_weight: float = 0.6
    micro_weight: float = 0.4
    bdi_enabled: bool = True


@dataclass
class ManagerConfig:
    hot_turns: int = 5
    cooling_turns: int = 5
    cold_turns: int = 10
    merge_threshold: float = 0.55


@dataclass
class SummaryConfig:
    v3_trigger_turn_count: int = 5


@dataclass
class ContextConfig:
    hot_turns: int = 5


@dataclass
class PipelineConfig:
    enabled: bool = True
    hot_turns: int = 5


@dataclass
class ModelDownloadConfig:
    bge_model_id: str = "BAAI/bge-small-zh"
    ner_model_id: str = "damo/nlp_raner_named-entity-recognition_chinese-base-news"
    cache_dir: str = "models"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    json: bool = False


@dataclass
class DiscourseConfig:
    """Discourse Block Tree 完整配置。"""
    encoder: EncoderConfig = field(default_factory=EncoderConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    decomposer: DecomposerConfig = field(default_factory=DecomposerConfig)
    injector: InjectorConfig = field(default_factory=InjectorConfig)
    segmenter: SegmenterConfig = field(default_factory=SegmenterConfig)
    manager: ManagerConfig = field(default_factory=ManagerConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    model_download: ModelDownloadConfig = field(default_factory=ModelDownloadConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# ── 配置加载器 ─────────────────────────────────────────────────

class ConfigLoader:
    """配置加载器：支持默认配置 → YAML 文件 → 环境变量覆盖。"""

    ENV_PREFIX = "MEMORYGRAPH_"
    CONFIG_DIR = Path.home() / ".config" / "memorygraph"
    CONFIG_FILE = CONFIG_DIR / "discourse.yaml"

    def __init__(self):
        self._config: Optional[DiscourseConfig] = None

    def load(self) -> DiscourseConfig:
        """加载完整配置（三层合并）。"""
        # 1. 从默认配置构建
        raw = self._deep_copy(_DEFAULT_CONFIG)

        # 2. 从 YAML 文件覆盖
        self._load_from_yaml(raw)

        # 3. 从环境变量覆盖
        self._load_from_env(raw)

        # 4. 转换为数据类
        config = self._build_dataclass(raw)
        self._config = config
        return config

    def reload(self) -> DiscourseConfig:
        """重新加载配置（热加载）。"""
        logger.info("Reloading discourse configuration...")
        return self.load()

    def _deep_copy(self, d: Dict) -> Dict:
        """深拷贝字典。"""
        import copy
        return copy.deepcopy(d)

    def _load_from_yaml(self, raw: Dict) -> None:
        """从 YAML 配置文件加载并覆盖。"""
        if not self.CONFIG_FILE.exists():
            return

        try:
            import yaml
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
            if user_config and isinstance(user_config, dict):
                self._deep_merge(raw, user_config)
                logger.info(f"Loaded configuration from {self.CONFIG_FILE}")
        except ImportError:
            logger.warning("PyYAML not installed, skipping YAML config loading")
        except Exception as e:
            logger.warning(f"Failed to load YAML config from {self.CONFIG_FILE}: {e}")

    def _load_from_env(self, raw: Dict) -> None:
        """从环境变量加载并覆盖。"""
        # 环境变量格式：MEMORYGRAPH_ENCODER_MODEL_PATH=models/custom-bge
        # 支持点分隔：MEMORYGRAPH_ENCODER__MODEL_PATH（双下划线表示嵌套）
        for key, value in os.environ.items():
            if not key.startswith(self.ENV_PREFIX):
                continue

            # 去掉前缀
            config_key = key[len(self.ENV_PREFIX):].lower()

            # 支持双下划线嵌套：encoder__model_path → encoder.model_path
            if "__" in config_key:
                parts = config_key.split("__")
                self._set_nested(raw, parts, self._convert_type(value))
            else:
                # 单层级：直接映射到顶层键
                if config_key in raw:
                    raw[config_key] = self._convert_type(value)

        logger.debug("Applied environment variable overrides")

    def _deep_merge(self, base: Dict, override: Dict) -> None:
        """递归合并字典。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _set_nested(self, d: Dict, keys: list, value: Any) -> None:
        """设置嵌套字典值。"""
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value

    def _convert_type(self, value: str) -> Any:
        """转换环境变量字符串值为合适类型。"""
        # 布尔值
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        if value.lower() in ("false", "0", "no", "off"):
            return False
        # 数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        # 字符串
        return value

    def _build_dataclass(self, raw: Dict) -> DiscourseConfig:
        """从原始字典构建数据类。"""
        return DiscourseConfig(
            encoder=EncoderConfig(**raw.get("encoder", {})),
            parser=ParserConfig(**raw.get("parser", {})),
            decomposer=DecomposerConfig(**raw.get("decomposer", {})),
            injector=InjectorConfig(**raw.get("injector", {})),
            segmenter=SegmenterConfig(**raw.get("segmenter", {})),
            manager=ManagerConfig(**raw.get("manager", {})),
            summary=SummaryConfig(**raw.get("summary", {})),
            context=ContextConfig(**raw.get("context", {})),
            pipeline=PipelineConfig(**raw.get("pipeline", {})),
            model_download=ModelDownloadConfig(**raw.get("model_download", {})),
            logging=LoggingConfig(**raw.get("logging", {})),
        )

    @staticmethod
    def create_default_config_file() -> None:
        """创建默认配置文件（如果不存在）。"""
        config_dir = ConfigLoader.CONFIG_DIR
        config_file = ConfigLoader.CONFIG_FILE

        if config_file.exists():
            return

        config_dir.mkdir(parents=True, exist_ok=True)

        default_yaml = """# Discourse Block Tree 配置文件
# 优先级：环境变量 > 本文件 > 代码默认值

encoder:
  model_path: models/BAAI/bge-small-zh
  device: auto  # auto / cpu / cuda
  cache_size: 10000
  max_length: 512

parser:
  ner_enabled: true
  bge_filter_enabled: true
  bge_filter_threshold: 0.5

decomposer:
  complex_clause_length: 30
  max_clauses_per_input: 5
  hybrid_path_enabled: true
  semantic_parser_enabled: true

injector:
  context_window_size: 5
  domain: default
  kb_path: null  # 默认使用 ~/.memorygraph/kb/header_kb.json
  semantic_parser_enabled: true

segmenter:
  threshold: 0.5
  macro_weight: 0.6
  micro_weight: 0.4
  bdi_enabled: true

manager:
  hot_turns: 5
  cooling_turns: 5
  cold_turns: 10
  merge_threshold: 0.55

summary:
  v3_trigger_turn_count: 5

context:
  hot_turns: 5

pipeline:
  enabled: true
  hot_turns: 5

model_download:
  bge_model_id: BAAI/bge-small-zh
  ner_model_id: damo/nlp_raner_named-entity-recognition_chinese-base-news
  cache_dir: models

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  json: false
"""
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(default_yaml)
            logger.info(f"Created default config file at {config_file}")
        except Exception as e:
            logger.warning(f"Failed to create default config file: {e}")


# ── 全局配置实例 ───────────────────────────────────────────────

_loader = ConfigLoader()
_discourse_config: Optional[DiscourseConfig] = None


def get_discourse_config() -> DiscourseConfig:
    """获取全局 Discourse 配置（首次调用时加载）。"""
    global _discourse_config
    if _discourse_config is None:
        _discourse_config = _loader.load()
    return _discourse_config


def reload_discourse_config() -> DiscourseConfig:
    """重新加载配置（热加载）。"""
    global _discourse_config
    _discourse_config = _loader.reload()
    return _discourse_config


def create_default_config() -> None:
    """创建默认配置文件（如果不存在）。"""
    ConfigLoader.create_default_config_file()
