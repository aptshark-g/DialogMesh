---
name: ocr-first
description: Extract text from images with the Windows built-in OCR engine (Windows.Media.Ocr) before any visual processing. Use when a task involves images/screenshots/slides/PDF pages that may contain text, or when the user shares an image and text extraction helps.
metadata:
  short-description: OCR 优先——遇到图片先用 Windows 自带 OCR 提取文字
---

# OCR First

当任务涉及图片、截图、幻灯片、PDF 页面等可能含文字的视觉内容时，
**先用 OCR 提取文字**，再决定后续处理。本 skill 使用 Windows 自带 OCR
引擎（`Windows.Media.Ocr`），**零依赖、纯离线**，原生支持 en-US 与
zh-Hans-CN，对真实截图（浏览器渲染/文档/UI）识别准确。

## 何时使用

- 用户分享截图/图片，需要读其中的文字（报错、日志、配置、文档、UI 文本）
- 处理 PPT/PDF 页面（可先渲染成图再 OCR）
- 长截图（聊天记录/网页滚动截图）：先定位文字区域或裁剪分块，再逐块 OCR
- 任何"图里有什么字"的场景，优先 OCR 而不是凭视觉猜测

## 使用方式

```bash
python "C:/Users/APTShark/.codex/skills/ocr-first/scripts/ocr.py" <image_path> [more...]

# 多图一次处理
python .../ocr.py a.png b.png c.png
```

输出格式：每张图一行 `=== 路径 ===`，随后每行 `[置信度] 文本`。
可加 `--min-conf <值>` 过滤低置信度词。

## 原则

1. **OCR 先行**：视觉类任务第一步永远是 OCR 提取文字，除非确认图里无文字。
2. **保留原文**：OCR 结果作为上下文引用时保留原文与置信度，不臆改。
3. **先定位后识别**：大图/长截图先做文字区域定位（像素梯度/边缘密度分析）
   或裁剪分块，再逐块 OCR，避免漏字与全屏无结果。
4. **互补不替代**：OCR 只解决"文字提取"；需要物体定位/布局理解时再考虑
   视觉模型或与用户确认。
5. **失败降级**：OCR 无结果或异常时，如实说明，不要编造图中内容。

## 关联

- 设计哲学 A3（关系第一）/ A8（表达形式）：OCR 把像素转成可引用的文本事实，
  是后续一切处理的事实底座。
- 若未来接入视觉 API（Gemini/qwen-vl），本 skill 仍是快速路径：先 OCR，
  再按需视觉理解。
