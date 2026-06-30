# core/agent/health_check.py
"""健康检查接口 —— 系统就绪状态诊断。

使用方式：
    from core.agent.health_check import HealthChecker

    checker = HealthChecker()
    status = checker.check_all()
    print(status.is_healthy)  # True/False
    print(status.to_dict())     # 完整诊断信息

支持检查项：
- 模型就绪（BGE 已下载、NER 已下载）
- 编码器可加载
- 语义解析器就绪
- jieba 词典可加载
- 配置系统正常
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

def _setup_path():
    """确保项目根目录在 Python 路径中。"""
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

_setup_path()

try:
    from core.agent.config.discourse_config import get_discourse_config
    from core.agent.config.logging_setup import setup_logging
except ImportError:
    get_discourse_config = None  # type: ignore
    setup_logging = None  # type: ignore

def _setup_logging_safe(level="INFO"):
    if setup_logging is not None:
        setup_logging(level=level)
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@dataclass
class CheckItem:
    """单个检查项结果。"""
    name: str
    status: str  # "ok" | "warning" | "error"
    message: str
    latency_ms: float = 0.0


@dataclass
class HealthStatus:
    """整体健康状态。"""
    is_healthy: bool
    checks: List[CheckItem] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "healthy": self.is_healthy,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "latency_ms": round(c.latency_ms, 2),
                }
                for c in self.checks
            ],
        }


class HealthChecker:
    """系统健康检查器。"""

    def __init__(self):
        self.config = get_discourse_config() if get_discourse_config else None

    def check_all(self) -> HealthStatus:
        """运行所有检查项。"""
        checks = []

        checks.append(self._check_config())
        checks.append(self._check_bge_model())
        checks.append(self._check_ner_model())
        checks.append(self._check_jieba())
        checks.append(self._check_encoder_load())
        checks.append(self._check_semantic_parser())

        is_healthy = all(c.status in ("ok", "warning") for c in checks)
        return HealthStatus(is_healthy=is_healthy, checks=checks)

    def _check_config(self) -> CheckItem:
        """检查配置系统。"""
        start = time.time()
        try:
            if self.config is None:
                return CheckItem("config", "error", "Config system not loaded", latency_ms=0)
            return CheckItem(
                "config", "ok",
                f"Config loaded: encoder={self.config.encoder.model_path}, "
                f"hot_turns={self.config.manager.hot_turns}",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("config", "error", f"Config check failed: {e}", latency_ms=0)

    def _check_bge_model(self) -> CheckItem:
        """检查 BGE 模型是否已下载。"""
        start = time.time()
        try:
            model_id = self.config.model_download.bge_model_id if self.config else "BAAI/bge-small-zh"
            cache_dir = self.config.model_download.cache_dir if self.config else "models"
            model_path = Path(cache_dir) / model_id.replace("/", os.sep)
            if model_path.exists() and any(model_path.iterdir()):
                return CheckItem(
                    "bge_model", "ok",
                    f"BGE model exists: {model_path}",
                    latency_ms=(time.time() - start) * 1000,
                )
            return CheckItem(
                "bge_model", "error",
                f"BGE model missing: {model_path}. Run: python scripts/download_models.py",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("bge_model", "error", f"BGE check failed: {e}", latency_ms=0)

    def _check_ner_model(self) -> CheckItem:
        """检查 NER 模型是否已下载。"""
        start = time.time()
        try:
            model_id = self.config.model_download.ner_model_id if self.config else \
                "damo/nlp_raner_named-entity-recognition_chinese-base-news"
            cache_dir = self.config.model_download.cache_dir if self.config else "models"
            model_path = Path(cache_dir) / model_id.replace("/", os.sep)
            if model_path.exists() and any(model_path.iterdir()):
                return CheckItem(
                    "ner_model", "ok",
                    f"NER model exists: {model_path}",
                    latency_ms=(time.time() - start) * 1000,
                )
            return CheckItem(
                "ner_model", "warning",
                f"NER model missing: {model_path}. NER features will be unavailable. "
                f"Run: python scripts/download_models.py",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("ner_model", "warning", f"NER check failed: {e}", latency_ms=0)

    def _check_jieba(self) -> CheckItem:
        """检查 jieba 分词器是否可用。"""
        start = time.time()
        try:
            import jieba
            jieba.lcut("健康检查")
            return CheckItem(
                "jieba", "ok", "jieba tokenizer ready",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("jieba", "warning", f"jieba not available: {e}", latency_ms=0)

    def _check_encoder_load(self) -> CheckItem:
        """检查语义编码器是否可加载。"""
        start = time.time()
        try:
            from core.agent.compiler.semantic_encoder import get_encoder
            encoder = get_encoder()
            encoder.encode("test")
            return CheckItem(
                "encoder", "ok",
                f"Encoder loaded on {encoder.device}, dim={encoder.embedding_dim}",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("encoder", "error", f"Encoder load failed: {e}", latency_ms=0)

    def _check_semantic_parser(self) -> CheckItem:
        """检查语义解析器是否可初始化。"""
        start = time.time()
        try:
            from core.agent.compiler.semantic_parser import SemanticParser
            sp = SemanticParser()
            entities = sp.extract_entities("测试")
            return CheckItem(
                "semantic_parser", "ok",
                f"SemanticParser ready, extracted {len(entities)} entities from test text",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return CheckItem("semantic_parser", "warning", f"SemanticParser init failed: {e}", latency_ms=0)

logger = logging.getLogger(__name__)


# ── CLI ────────────────────────────────────────────────────────

def main():
    import json
    import sys

    _setup_logging_safe(level="INFO")
    checker = HealthChecker()
    status = checker.check_all()

    print(f"\n{'=' * 50}")
    print(f"Health Check: {'HEALTHY' if status.is_healthy else 'UNHEALTHY'}")
    print(f"{'=' * 50}")

    for check in status.checks:
        icon = "[OK]" if check.status == "ok" else "[WARN]" if check.status == "warning" else "[FAIL]"
        print(f"  {icon} {check.name:20s} {check.message}")
        if check.latency_ms > 0:
            print(f"       latency: {check.latency_ms:.1f}ms")

    print(f"\nJSON:\n{json.dumps(status.to_dict(), ensure_ascii=False, indent=2)}")

    sys.exit(0 if status.is_healthy else 1)


if __name__ == "__main__":
    main()
