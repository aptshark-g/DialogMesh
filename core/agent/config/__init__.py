# -*- coding: utf-8 -*-
"""
core/agent/config/__init__.py
"""
from core.agent.config.prompt_config import (
    AgentConfig,
    ConfigManager,
    LLMProfile,
    SystemPromptConfig,
    ThresholdConfig,
    get_config,
    reload_config,
    config,
)
from core.agent.config.discourse_config import (
    DiscourseConfig,
    EncoderConfig,
    ParserConfig,
    DecomposerConfig,
    InjectorConfig,
    SegmenterConfig,
    ManagerConfig,
    SummaryConfig,
    ContextConfig,
    PipelineConfig,
    ModelDownloadConfig,
    LoggingConfig,
    get_discourse_config,
    reload_discourse_config,
    create_default_config,
)
from core.agent.config.logging_setup import setup_logging, get_logger

__all__ = [
    # prompt_config exports
    "AgentConfig",
    "ConfigManager",
    "LLMProfile",
    "SystemPromptConfig",
    "ThresholdConfig",
    "get_config",
    "reload_config",
    # discourse_config exports
    "DiscourseConfig",
    "EncoderConfig",
    "ParserConfig",
    "DecomposerConfig",
    "InjectorConfig",
    "SegmenterConfig",
    "ManagerConfig",
    "SummaryConfig",
    "ContextConfig",
    "PipelineConfig",
    "ModelDownloadConfig",
    "LoggingConfig",
    "get_discourse_config",
    "reload_discourse_config",
    "create_default_config",
    "config",
    # logging_setup exports
    "setup_logging",
    "get_logger",
]
