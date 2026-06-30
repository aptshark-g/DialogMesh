# -*- coding: utf-8 -*-
"""
core/agent/frontend/tests/test_multimodal.py
────────────────────────────────────────────
多模态预处理测试（Mock 实现，零外部依赖）。
"""

from __future__ import annotations

import unittest
import asyncio

from core.agent.frontend.multimodal import (
    MediaAttachment,
    PreprocessedContent,
    MockOCREngine,
    MockASREngine,
    ImagePreprocessor,
    AudioPreprocessor,
    DocumentPreprocessor,
    MultimodalPipeline,
)


class TestMockOCREngine(unittest.TestCase):
    def test_recognize_known_keyword(self):
        """OCR Mock 能识别已知关键词。"""
        engine = MockOCREngine()
        result = asyncio.run(engine.recognize("扫描 Game.exe 内存", "base64"))
        self.assertIn("扫描", result)
        self.assertTrue(result.startswith("[OCR]"))

    def test_recognize_unknown_image(self):
        """OCR Mock 对未知图片返回占位符。"""
        engine = MockOCREngine()
        result = asyncio.run(engine.recognize("random_binary_data", "base64"))
        self.assertIn("未能识别", result)

    def test_recognize_with_address(self):
        """OCR Mock 识别内存地址关键词。"""
        engine = MockOCREngine()
        result = asyncio.run(engine.recognize("0x00400000", "base64"))
        self.assertIn("0x00400000", result)


class TestMockASREngine(unittest.TestCase):
    def test_transcribe_known_keyword(self):
        """ASR Mock 能识别已知关键词。"""
        engine = MockASREngine()
        result = asyncio.run(engine.transcribe("帮我扫描内存", "url"))
        self.assertIn("扫描", result)
        self.assertTrue(result.startswith("[ASR]"))

    def test_transcribe_unknown_audio(self):
        """ASR Mock 对未知音频返回占位符。"""
        engine = MockASREngine()
        result = asyncio.run(engine.transcribe("noise_noise_noise", "base64"))
        self.assertIn("未能识别", result)


class TestImagePreprocessor(unittest.TestCase):
    def test_preprocess_image_success(self):
        """图片预处理成功。"""
        pre = ImagePreprocessor()
        att = MediaAttachment("image", "base64", "扫描 PID 1234", "image/png")
        result = asyncio.run(pre.preprocess(att))
        self.assertIn("PID", result.text)
        self.assertEqual(result.modality_trace, ["image_ocr"])
        self.assertEqual(len(result.warnings), 0)

    def test_preprocess_image_no_text(self):
        """图片无文字时产生警告。"""
        pre = ImagePreprocessor()
        att = MediaAttachment("image", "base64", "just_a_photo", "image/jpeg")
        result = asyncio.run(pre.preprocess(att))
        self.assertTrue(result.text.startswith("[OCR] 未能"))
        self.assertEqual(len(result.warnings), 1)

    def test_preprocess_wrong_type(self):
        """传入非图片类型应抛异常。"""
        pre = ImagePreprocessor()
        att = MediaAttachment("audio", "url", "http://x.wav", "audio/wav")
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(pre.preprocess(att))
        self.assertIn("image", str(ctx.exception))


class TestAudioPreprocessor(unittest.TestCase):
    def test_preprocess_audio_success(self):
        """音频预处理成功。"""
        pre = AudioPreprocessor()
        att = MediaAttachment("audio", "url", "修改血量", "audio/wav")
        result = asyncio.run(pre.preprocess(att))
        # ASR 匹配 "修改" 关键词，返回固定模板
        self.assertTrue(result.text.startswith("[ASR]"))
        self.assertEqual(result.modality_trace, ["audio_asr"])

    def test_preprocess_audio_no_speech(self):
        """音频无语音时产生警告。"""
        pre = AudioPreprocessor()
        att = MediaAttachment("audio", "base64", "white_noise", "audio/wav")
        result = asyncio.run(pre.preprocess(att))
        self.assertTrue(result.text.startswith("[ASR] 未能"))
        self.assertEqual(len(result.warnings), 1)


class TestDocumentPreprocessor(unittest.TestCase):
    def test_preprocess_document(self):
        """文档预处理直接透传文本。"""
        pre = DocumentPreprocessor()
        att = MediaAttachment("document", "file_path", "{\"key\": \"value\"}", "application/json")
        result = asyncio.run(pre.preprocess(att))
        self.assertIn("key", result.text)
        self.assertEqual(result.modality_trace, ["document_text"])

    def test_preprocess_long_document_truncated(self):
        """长文档自动截断。"""
        pre = DocumentPreprocessor()
        long_text = "x" * 5000
        att = MediaAttachment("document", "base64", long_text, "text/plain")
        result = asyncio.run(pre.preprocess(att))
        self.assertIn("[内容截断", result.text)
        self.assertLess(len(result.text), 3000)

    def test_preprocess_wrong_type(self):
        """传入非文档类型应抛异常。"""
        pre = DocumentPreprocessor()
        att = MediaAttachment("image", "url", "http://x.png", "image/png")
        with self.assertRaises(ValueError):
            asyncio.run(pre.preprocess(att))


class TestMultimodalPipeline(unittest.TestCase):
    def test_text_only(self):
        """纯文本：直接透传。"""
        pipeline = MultimodalPipeline()
        result = asyncio.run(pipeline.process("扫描 Game.exe", []))
        self.assertEqual(result.text, "扫描 Game.exe")
        self.assertEqual(result.modality_trace, ["text"])

    def test_image_only(self):
        """仅图片：提取 OCR 文本。"""
        pipeline = MultimodalPipeline()
        att = MediaAttachment("image", "base64", "PID 5678", "image/png")
        result = asyncio.run(pipeline.process("", [att]))
        self.assertIn("PID", result.text)
        self.assertIn("image_ocr", result.modality_trace)

    def test_text_plus_image(self):
        """文本 + 图片：合并。"""
        pipeline = MultimodalPipeline()
        att = MediaAttachment("image", "base64", "0x7FF00000", "image/png")
        result = asyncio.run(pipeline.process("帮我分析这个地址", [att]))
        self.assertIn("帮我分析这个地址", result.text)
        # OCR 匹配 "0x" 关键词，返回固定模板中的地址
        self.assertIn("0x", result.text)
        self.assertEqual(result.modality_trace, ["text", "image_ocr"])

    def test_parallel_multiple_attachments(self):
        """多个附件并行处理。"""
        pipeline = MultimodalPipeline()
        atts = [
            MediaAttachment("image", "base64", "扫描", "image/png"),
            MediaAttachment("audio", "url", "读取", "audio/wav"),
        ]
        result = asyncio.run(pipeline.process("主文本", atts))
        self.assertIn("主文本", result.text)
        self.assertIn("image_ocr", result.modality_trace)
        self.assertIn("audio_asr", result.modality_trace)

    def test_unknown_attachment_skipped(self):
        """未知类型附件被跳过，不影响其他。"""
        pipeline = MultimodalPipeline()
        atts = [
            MediaAttachment("video", "url", "http://x.mp4", "video/mp4"),  # 未知
            MediaAttachment("image", "base64", "PID", "image/png"),
        ]
        result = asyncio.run(pipeline.process("", atts))
        self.assertIn("PID", result.text)
        # video 被跳过，不产生 trace
        self.assertNotIn("video", result.modality_trace)

    def test_image_only_convenience(self):
        """便捷方法：process_image_only。"""
        pipeline = MultimodalPipeline()
        result = asyncio.run(pipeline.process_image_only("0x1234", "base64", "image/png"))
        # OCR 匹配 "0x" 关键词，返回固定模板
        self.assertIn("0x", result.text)
        self.assertTrue(result.text.startswith("[OCR]"))

    def test_audio_only_convenience(self):
        """便捷方法：process_audio_only。"""
        pipeline = MultimodalPipeline()
        result = asyncio.run(pipeline.process_audio_only("扫描", "base64", "audio/wav"))
        # ASR 匹配 "扫描" 关键词，返回固定模板
        self.assertTrue(result.text.startswith("[ASR]"))
        self.assertIn("扫描", result.text)

    def test_empty_input(self):
        """空输入返回空文本。"""
        pipeline = MultimodalPipeline()
        result = asyncio.run(pipeline.process("", []))
        self.assertEqual(result.text, "")
        self.assertEqual(result.modality_trace, [])

    def test_metadata_and_warnings(self):
        """元数据和警告被正确收集。"""
        pipeline = MultimodalPipeline()
        atts = [
            MediaAttachment("image", "base64", "no_text_here", "image/png"),  # 会产生警告
        ]
        result = asyncio.run(pipeline.process("", atts))
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("image", result.metadata)


class TestRealOCRStub(unittest.TestCase):
    """验证可注入真实 OCR 引擎的接口。"""

    def test_custom_ocr_engine(self):
        """自定义 OCR 引擎被正确调用。"""
        class CustomOCR:
            async def recognize(self, image_data, source, mime_type=None):
                return f"Custom: {image_data}"

        pre = ImagePreprocessor(ocr_engine=CustomOCR())
        att = MediaAttachment("image", "base64", "anything", "image/png")
        result = asyncio.run(pre.preprocess(att))
        self.assertEqual(result.text, "Custom: anything")


class TestRealASRStub(unittest.TestCase):
    """验证可注入真实 ASR 引擎的接口。"""

    def test_custom_asr_engine(self):
        """自定义 ASR 引擎被正确调用。"""
        class CustomASR:
            async def transcribe(self, audio_data, source, mime_type=None):
                return f"Custom: {audio_data}"

        pre = AudioPreprocessor(asr_engine=CustomASR())
        att = MediaAttachment("audio", "url", "anything", "audio/wav")
        result = asyncio.run(pre.preprocess(att))
        self.assertEqual(result.text, "Custom: anything")


if __name__ == "__main__":
    unittest.main()
