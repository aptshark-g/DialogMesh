# core/agent/config/logging_setup.py
"""统一日志配置初始化。

使用方式：
    from core.agent.config.logging_setup import setup_logging
    setup_logging()  # 在应用入口调用一次

配置来源：
1. discourse_config.yaml 中的 logging 字段
2. 环境变量 MEMORYGRAPH_LOGGING_LEVEL
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（仅终端输出）。"""

    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str, use_color: bool = True):
        super().__init__(fmt)
        self.use_color = use_color and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        result = super().format(record)
        record.levelname = levelname  # 恢复原始值
        return result


def setup_logging(
    level: Optional[str] = None,
    fmt: Optional[str] = None,
    use_color: bool = True,
    json_format: bool = False,
):
    """初始化 Discourse Block Tree 模块的日志配置。

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL），默认从配置读取
        fmt: 日志格式字符串，默认从配置读取
        use_color: 是否使用颜色（仅终端）
        json_format: 是否输出 JSON 格式（适合日志收集器）
    """
    config = get_discourse_config() if get_discourse_config else None
    log_cfg = config.logging if config else None

    # 合并参数优先级：显式传入 > 配置 > 默认值
    level = level or (log_cfg.level if log_cfg else "INFO")
    fmt = fmt or (log_cfg.format if log_cfg else "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    json_format = json_format or (log_cfg.json if log_cfg else False)

    level_int = getattr(logging, level.upper(), logging.INFO)

    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(level_int)

    # 清除现有 handler（避免重复）
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 标准输出 handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level_int)

    if json_format:
        try:
            import json
            class JSONFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    return json.dumps({
                        "timestamp": self.formatTime(record),
                        "name": record.name,
                        "level": record.levelname,
                        "message": record.getMessage(),
                        "pathname": record.pathname,
                        "lineno": record.lineno,
                    }, ensure_ascii=False)
            handler.setFormatter(JSONFormatter())
        except ImportError:
            handler.setFormatter(logging.Formatter(fmt))
    else:
        handler.setFormatter(ColoredFormatter(fmt, use_color=use_color))

    root_logger.addHandler(handler)

    # 为 discourse 相关模块设置级别
    for name in [
        "core.agent.compiler",
        "core.agent.discourse_block_tree",
        "core.agent.discourse_integration",
    ]:
        logging.getLogger(name).setLevel(level_int)

    logging.getLogger(__name__).info(f"Logging initialized: level={level}, format={'json' if json_format else 'text'}")


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器（统一入口）。"""
    return logging.getLogger(name)
