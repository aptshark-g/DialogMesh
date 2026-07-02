#!/usr/bin/env python3
"""模型自动下载脚本。

一键下载 Discourse Block Tree 所需的预训练模型：
- BGE-small-zh (语义编码，~91MB)
- DAMO NER (命名实体识别，~390MB)

使用方式：
    python scripts/download_models.py
    python scripts/download_models.py --bge-only
    python scripts/download_models.py --ner-only
    python scripts/download_models.py --check

配置来源：
- 默认从 core.agent.config.discourse_config 读取模型 ID
- 命令行参数可覆盖
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

# 配置路径以便导入
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.agent.config.discourse_config import get_discourse_config
from core.agent.config.logging_setup import setup_logging

logger = logging.getLogger(__name__)


# ── 默认模型配置 ─────────────────────────────────────────────────

DEFAULT_BGE_MODEL_ID = "BAAI/bge-small-zh"
DEFAULT_NER_MODEL_ID = "damo/nlp_raner_named-entity-recognition_chinese-base-news"

# 本地缓存路径（相对于项目根目录）
DEFAULT_CACHE_DIR = "models"


# ── 下载器 ─────────────────────────────────────────────────────

class ModelDownloader:
    """模型下载器（基于 ModelScope CLI）。"""

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download_bge(self, model_id: str = DEFAULT_BGE_MODEL_ID) -> bool:
        """下载 BGE 语义编码模型。"""
        local_dir = self.cache_dir / model_id.replace("/", os.sep)
        if local_dir.exists() and any(local_dir.iterdir()):
            logger.info(f"BGE model already exists at {local_dir}, skipping download")
            return True

        logger.info(f"Downloading BGE model: {model_id}")
        return self._download_with_modelscope(model_id, local_dir)

    def download_ner(self, model_id: str = DEFAULT_NER_MODEL_ID) -> bool:
        """下载 NER 命名实体识别模型。"""
        local_dir = self.cache_dir / model_id.replace("/", os.sep)
        if local_dir.exists() and any(local_dir.iterdir()):
            logger.info(f"NER model already exists at {local_dir}, skipping download")
            return True

        logger.info(f"Downloading NER model: {model_id}")
        return self._download_with_modelscope(model_id, local_dir)

    def _download_with_modelscope(self, model_id: str, local_dir: Path) -> bool:
        """使用 modelscope CLI 下载模型。"""
        try:
            import subprocess
            cmd = [
                sys.executable, "-m", "modelscope", "download",
                model_id,
                "--local_dir", str(local_dir),
            ]
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"Download failed: {result.stderr}")
                return False
            logger.info(f"Download completed: {local_dir}")
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout (10min): {model_id}")
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    def check_models(self, bge_model_id: str, ner_model_id: str) -> dict:
        """检查模型是否已下载。"""
        bge_dir = self.cache_dir / bge_model_id.replace("/", os.sep)
        ner_dir = self.cache_dir / ner_model_id.replace("/", os.sep)

        bge_ok = bge_dir.exists() and any(bge_dir.iterdir())
        ner_ok = ner_dir.exists() and any(ner_dir.iterdir())

        return {
            "bge": {
                "model_id": bge_model_id,
                "local_dir": str(bge_dir),
                "exists": bge_ok,
            },
            "ner": {
                "model_id": ner_model_id,
                "local_dir": str(ner_dir),
                "exists": ner_ok,
            },
            "all_ready": bge_ok and ner_ok,
        }


# ── 主函数 ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download pre-trained models for Discourse Block Tree"
    )
    parser.add_argument("--bge-only", action="store_true", help="Download only BGE model")
    parser.add_argument("--ner-only", action="store_true", help="Download only NER model")
    parser.add_argument("--check", action="store_true", help="Check if models exist, don't download")
    parser.add_argument("--bge-id", type=str, help="Override BGE model ID")
    parser.add_argument("--ner-id", type=str, help="Override NER model ID")
    parser.add_argument("--cache-dir", type=str, help="Override cache directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.verbose else "INFO")

    # 从配置读取默认值
    try:
        config = get_discourse_config()
        bge_id = args.bge_id or config.model_download.bge_model_id
        ner_id = args.ner_id or config.model_download.ner_model_id
        cache_dir = args.cache_dir or config.model_download.cache_dir
    except Exception as e:
        logger.warning(f"Failed to load config: {e}, using defaults")
        bge_id = args.bge_id or DEFAULT_BGE_MODEL_ID
        ner_id = args.ner_id or DEFAULT_NER_MODEL_ID
        cache_dir = args.cache_dir or DEFAULT_CACHE_DIR

    downloader = ModelDownloader(cache_dir=cache_dir)

    if args.check:
        status = downloader.check_models(bge_id, ner_id)
        print(f"BGE  ({bge_id}): {'[OK]' if status['bge']['exists'] else '[MISSING]'}  {status['bge']['local_dir']}")
        print(f"NER  ({ner_id}): {'[OK]' if status['ner']['exists'] else '[MISSING]'}  {status['ner']['local_dir']}")
        print(f"All ready: {'[OK]' if status['all_ready'] else '[MISSING]'}")
        sys.exit(0 if status["all_ready"] else 1)

    results = []
    if not args.ner_only:
        results.append(("BGE", downloader.download_bge(bge_id)))
    if not args.bge_only:
        results.append(("NER", downloader.download_ner(ner_id)))

    all_ok = all(r[1] for r in results)
    for name, ok in results:
        status = "[OK]" if ok else "[FAIL]"
        logger.info(f"{status} {name} model")

    if all_ok:
        logger.info("All models downloaded successfully")
        sys.exit(0)
    else:
        logger.error("Some models failed to download")
        sys.exit(1)


if __name__ == "__main__":
    main()
