# -*- coding: utf-8 -*-
"""
core/agent/frontend/multimodal.py
─────────────────────────────────
多模态预处理（Layer 3 扩展）

将图片 / 音频 / 多模态混合输入统一转换为文本，送入 PCR 核心引擎。

设计原则：
  - 与具体 OCR/ASR 引擎解耦：通过抽象接口，可注入真实实现（Tesseract, Whisper, …）
  - 默认提供 Mock 实现，不引入任何外部依赖
  - 完全异步：OCR/ASR 可能调用外部服务，使用 asyncio.gather 并行处理
  - 统一输出 PreprocessedContent（text + metadata），下游直接送入 PCRInput_v1

支持模态：
  - TEXT      → 直接透传
  - STRUCTURED → 直接透传（JSON 序列化）
  - IMAGE     → OCR 提取文本（Mock 或真实）
  - AUDIO     → ASR 提取文本（Mock 或真实）
  - MULTIMODAL → 并行预处理 TEXT + IMAGE + AUDIO，合并文本
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据契约
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MediaAttachment:
    """多模态附件描述。"""
    media_type: str                       # "image" | "audio" | "document"
    source: str                           # "url" | "base64" | "file_path"
    data: str                             # URL / base64 字符串 / 文件路径
    mime_type: Optional[str] = None      # 如 "image/png", "audio/wav"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreprocessedContent:
    """预处理后的统一内容，可直接送入 PCR。"""
    text: str                             # 提取/合并后的文本
    modality_trace: List[str] = field(default_factory=list)  # ["text", "image_ocr", "audio_asr"]
    metadata: Dict[str, Any] = field(default_factory=dict)   # 各模态的原始元数据
    warnings: List[str] = field(default_factory=list)        # 预处理警告（如 OCR 置信度低）


# ═══════════════════════════════════════════════════════════════════════════════
# 抽象接口：可插拔的 OCR / ASR 引擎
# ═══════════════════════════════════════════════════════════════════════════════

class OCREngine(Protocol):
    """OCR 引擎协议。生产环境可注入 Tesseract、PaddleOCR、云 OCR 等。"""

    async def recognize(self, image_data: str, source: str, mime_type: Optional[str] = None) -> str:
        """
        识别图片中的文本。

        :param image_data: 图片数据（URL / base64 / 路径）
        :param source: "url" | "base64" | "file_path"
        :param mime_type: MIME 类型（可选，用于格式校验）
        :return: 提取的文本字符串
        """
        ...


class ASREngine(Protocol):
    """ASR 引擎协议。生产环境可注入 Whisper、云 ASR 等。"""

    async def transcribe(self, audio_data: str, source: str, mime_type: Optional[str] = None) -> str:
        """
        转录音频中的文本。

        :param audio_data: 音频数据（URL / base64 / 路径）
        :param source: "url" | "base64" | "file_path"
        :param mime_type: MIME 类型（可选，用于格式校验）
        :return: 转录的文本字符串
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Mock 实现（默认，零外部依赖）
# ═══════════════════════════════════════════════════════════════════════════════

class MockOCREngine:
    """
    Mock OCR 引擎。

    识别规则（启发式）：
      - 如果图片数据包含已知关键词（如 "PID", "0x", "扫描", "内存"），返回模拟文本
      - 否则返回通用占位符
    """

    KEYWORD_HINTS: Dict[str, str] = {
        "PID": "检测到进程信息：PID 1234",
        "0x": "检测到内存地址：0x00400000",
        "扫描": "扫描目标：Game.exe 内存区域",
        "内存": "内存分析：基址 0x7FF00000",
        "血量": "数值：HP 100/100",
        "金币": "数值：Gold 9999",
    }

    async def recognize(self, image_data: str, source: str, mime_type: Optional[str] = None) -> str:
        await asyncio.sleep(0.001)  # 模拟 I/O 延迟
        text = image_data.lower() if isinstance(image_data, str) else ""
        for keyword, hint in self.KEYWORD_HINTS.items():
            if keyword.lower() in text:
                return f"[OCR] {hint}"
        return "[OCR] 未能识别图片中的可读文本"


class MockASREngine:
    """
    Mock ASR 引擎。

    识别规则（启发式）：
      - 如果音频数据包含已知关键词，返回模拟文本
      - 否则返回通用占位符
    """

    KEYWORD_HINTS: Dict[str, str] = {
        "扫描": "扫描 Game.exe 的内存",
        "修改": "把血量改成 999",
        "读取": "读取当前金币数量",
        "分析": "分析这个进程的内存结构",
    }

    async def transcribe(self, audio_data: str, source: str, mime_type: Optional[str] = None) -> str:
        await asyncio.sleep(0.001)  # 模拟 I/O 延迟
        text = audio_data.lower() if isinstance(audio_data, str) else ""
        for keyword, hint in self.KEYWORD_HINTS.items():
            if keyword.lower() in text:
                return f"[ASR] {hint}"
        return "[ASR] 未能识别音频中的语音内容"


# ═══════════════════════════════════════════════════════════════════════════════
# 预处理器实现
# ═══════════════════════════════════════════════════════════════════════════════

class ImagePreprocessor:
    """
    图片预处理器：提取图片中的文本，返回 PreprocessedContent。

    使用方式：
      preprocessor = ImagePreprocessor()  # 默认 Mock
      preprocessor = ImagePreprocessor(real_ocr_engine)  # 注入真实 OCR
    """

    def __init__(self, ocr_engine: Optional[OCREngine] = None):
        self.ocr = ocr_engine or MockOCREngine()

    async def preprocess(self, attachment: MediaAttachment) -> PreprocessedContent:
        if attachment.media_type != "image":
            raise ValueError(f"ImagePreprocessor 只接受 image 类型，收到 {attachment.media_type}")

        extracted = await self.ocr.recognize(
            attachment.data, attachment.source, attachment.mime_type
        )

        warnings = []
        if extracted.startswith("[OCR] 未能"):
            warnings.append("OCR 未提取到有效文本，图片可能不含文字或分辨率不足")

        return PreprocessedContent(
            text=extracted,
            modality_trace=["image_ocr"],
            metadata={"image": {"source": attachment.source, "mime_type": attachment.mime_type}},
            warnings=warnings,
        )


class AudioPreprocessor:
    """
    音频预处理器：提取音频中的文本，返回 PreprocessedContent。

    使用方式：
      preprocessor = AudioPreprocessor()  # 默认 Mock
      preprocessor = AudioPreprocessor(real_asr_engine)  # 注入真实 ASR
    """

    def __init__(self, asr_engine: Optional[ASREngine] = None):
        self.asr = asr_engine or MockASREngine()

    async def preprocess(self, attachment: MediaAttachment) -> PreprocessedContent:
        if attachment.media_type != "audio":
            raise ValueError(f"AudioPreprocessor 只接受 audio 类型，收到 {attachment.media_type}")

        extracted = await self.asr.transcribe(
            attachment.data, attachment.source, attachment.mime_type
        )

        warnings = []
        if extracted.startswith("[ASR] 未能"):
            warnings.append("ASR 未识别到语音内容，音频可能为空或噪声过大")

        return PreprocessedContent(
            text=extracted,
            modality_trace=["audio_asr"],
            metadata={"audio": {"source": attachment.source, "mime_type": attachment.mime_type}},
            warnings=warnings,
        )


class DocumentPreprocessor:
    """
    文档预处理器：提取文本文件内容（JSON / YAML / CSV 等）。

    直接读取文本内容，无需 OCR/ASR。
    """

    async def preprocess(self, attachment: MediaAttachment) -> PreprocessedContent:
        if attachment.media_type != "document":
            raise ValueError(f"DocumentPreprocessor 只接受 document 类型，收到 {attachment.media_type}")

        # 如果 data 是 URL 或路径，这里简化处理：直接视为文本内容
        text = attachment.data
        if len(text) > 2000:
            text = text[:2000] + "\n...[内容截断，共 {} 字符]".format(len(attachment.data))

        return PreprocessedContent(
            text=text,
            modality_trace=["document_text"],
            metadata={"document": {"source": attachment.source, "mime_type": attachment.mime_type, "length": len(attachment.data)}},
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 多模态合并器
# ═══════════════════════════════════════════════════════════════════════════════

class MultimodalPipeline:
    """
    多模态统一处理管道。

    处理流程：
      1. 接收 MultimodalInput（text + attachments[]）
      2. 根据 attachment 类型分派到对应预处理器（并行）
      3. 合并所有文本（主文本 + 附件提取文本）
      4. 返回 PreprocessedContent（可直接送入 PCR）

    使用示例：
      pipeline = MultimodalPipeline()
      result = await pipeline.process(MultimodalInput(
          text="帮我扫描这个进程的内存",
          attachments=[MediaAttachment("image", "url", "https://.../screenshot.png")]
      ))
      # result.text = "帮我扫描这个进程的内存\n[OCR] 检测到进程信息：PID 1234"
    """

    def __init__(
        self,
        image_preprocessor: Optional[ImagePreprocessor] = None,
        audio_preprocessor: Optional[AudioPreprocessor] = None,
        document_preprocessor: Optional[DocumentPreprocessor] = None,
    ):
        self._image = image_preprocessor or ImagePreprocessor()
        self._audio = audio_preprocessor or AudioPreprocessor()
        self._document = document_preprocessor or DocumentPreprocessor()

    async def process(self, text: str, attachments: List[MediaAttachment]) -> PreprocessedContent:
        """
        处理多模态输入。

        :param text: 用户输入的主文本（可为空）
        :param attachments: 附件列表（图片/音频/文档）
        :return: 合并后的 PreprocessedContent
        """
        # 并行预处理所有附件
        tasks = []
        for att in attachments:
            if att.media_type == "image":
                tasks.append(self._image.preprocess(att))
            elif att.media_type == "audio":
                tasks.append(self._audio.preprocess(att))
            elif att.media_type == "document":
                tasks.append(self._document.preprocess(att))
            else:
                logger.warning("未知附件类型: %s，跳过", att.media_type)

        results: List[PreprocessedContent] = []
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 过滤异常
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.error("附件预处理失败 [%d]: %s", i, r)
                    results[i] = PreprocessedContent(
                        text="[附件处理失败]",
                        modality_trace=["error"],
                        warnings=[str(r)],
                    )

        # 合并文本：主文本 + 各附件提取文本
        parts = [text] if text else []
        trace = ["text"] if text else []
        metadata: Dict[str, Any] = {}
        all_warnings: List[str] = []

        for r in results:
            if r.text:
                parts.append(r.text)
            trace.extend(r.modality_trace)
            metadata.update(r.metadata)
            all_warnings.extend(r.warnings)

        merged_text = "\n".join(parts)

        return PreprocessedContent(
            text=merged_text,
            modality_trace=trace,
            metadata=metadata,
            warnings=all_warnings,
        )

    async def process_image_only(self, image_data: str, source: str = "base64", mime_type: Optional[str] = None) -> PreprocessedContent:
        """便捷方法：只处理单张图片。"""
        return await self._image.preprocess(MediaAttachment("image", source, image_data, mime_type))

    async def process_audio_only(self, audio_data: str, source: str = "base64", mime_type: Optional[str] = None) -> PreprocessedContent:
        """便捷方法：只处理单段音频。"""
        return await self._audio.preprocess(MediaAttachment("audio", source, audio_data, mime_type))


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷：同步包装（用于非 async 上下文）
# ═══════════════════════════════════════════════════════════════════════════════

def run_sync(coro):
    """在已有事件循环中运行协程（或新建一个）。"""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # 在已有循环中，需要 nest_asyncio 或返回 future
            # 这里简化：假设调用方在 sync 上下文
            import nest_asyncio
            nest_asyncio.apply()
    except RuntimeError:
        pass
    return asyncio.run(coro)
