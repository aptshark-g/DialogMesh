#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a real snippet of docs/only text into an HTML page for OCR testing."""
import html
import os

lines = [
    "压缩恢复规划 — 2026-08-03（2026-08-03 更新）",
    "目的: 压缩后按此文档顺序恢复上下文，避免丢状态。",
    "DialogMesh B5 前端绑定 smoke 验证：13 页 × 真数据端点。",
]
body = "".join(f"<p style='font-size:28px;margin:0 0 18px 0'>{html.escape(t)}</p>"
               for t in lines)
doc = ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
       "<style>body{{background:#fff;padding:40px;font-family:'Microsoft YaHei',sans-serif;}}</style>"
       "</head><body>" + body + "</body></html>")
out = os.path.join(os.environ.get("TEMP", "."), "doc_test.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(doc)
print("written", out)
