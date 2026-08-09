# gui/streaming.py
"""StreamingResponse — NiceGUI 流式输出组件。

解决核心问题：LLM 响应慢（3-10秒），用户界面卡死，无反馈。
方案：两阶段流式（thinking → streaming → done）

使用方式：
    from gui.streaming import StreamingResponse

    async def on_send():
        query = input.value
        # 1. 创建流式响应占位
        stream = StreamingResponse(container, name="MemoryGraph")
        stream.start()
        
        # 2. 后台调用 LLM（非阻塞 UI）
        result = await run_in_thread(lambda: state.send_message(query))
        
        # 3. 完成：替换为完整内容
        stream.end(result["result"])
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from nicegui import ui


class StreamingResponse:
    """流式响应占位组件。

    生命周期：
        start()   → 显示 "思考中..." 旋转动画
        update()  → 追加内容（逐字流式，可选）
        end()     → 替换为完整内容，显示元数据
    """

    def __init__(self, container: ui.element, name: str = "MemoryGraph"):
        self.container = container
        self.name = name
        self._element: Optional[ui.element] = None
        self._content_label: Optional[ui.label] = None
        self._spinner: Optional[ui.element] = None
        self._meta_row: Optional[ui.element] = None
        self._is_done = False

    def start(self, hint: str = "思考中..."):
        """显示思考中占位。"""
        with self.container:
            self._element = ui.card().style("max-width: 80%; background: #f5f5f5;")
            with self._element:
                with ui.row().classes("items-center q-gutter-sm"):
                    # 旋转动画（CSS）
                    ui.html(
                        '<span class="spinning" style="display:inline-block;width:16px;height:16px;'
                        'border:2px solid #ccc;border-top-color:#2196f3;border-radius:50%;'
                        'animation:spin 1s linear infinite;"></span>'
                    )
                    ui.label(f"{self.name} 正在{hint}").classes("text-caption text-grey")

        # 注入 CSS 动画
        ui.add_css("""
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .streaming-fade-in {
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
        }
        """)

    def update(self, text: str):
        """追加内容（逐字流式，当前用于模拟）。"""
        if self._is_done:
            return
        # 当前实现：一次性替换（真正的流式需要 LLM 客户端支持 streaming）
        # 后续扩展：逐字追加
        pass

    def end(self, content: str, meta: Optional[Dict[str, Any]] = None):
        """完成：替换为完整内容 + 元数据。"""
        if self._is_done:
            return
        self._is_done = True

        # 删除旧元素
        if self._element:
            self._element.delete()

        with self.container:
            card = ui.card().style("max-width: 80%; background: #f5f5f5;")
            with card:
                with ui.row().classes("items-center q-gutter-sm"):
                    ui.icon("smart_toy", color="secondary")
                    ui.label(self.name).classes("text-bold text-secondary")
                    if meta and meta.get("mode"):
                        color = {"rule": "grey", "small_model": "orange", "remote_llm": "red"}.get(meta["mode"], "grey")
                        ui.badge(meta["mode"], color=color)

                # 内容（限制高度，避免过长）
                max_len = 3000
                display = content[:max_len] + ("..." if len(content) > max_len else "")
                ui.markdown(display).classes("streaming-fade-in q-mt-sm")

                # 元数据
                if meta:
                    with ui.row().classes("q-mt-sm q-gutter-sm items-center"):
                        if meta.get("latency"):
                            ui.label(f"⏱️ {meta['latency']:.2f}s").classes("text-caption text-grey")
                        if meta.get("context_len"):
                            ui.label(f"📄 {meta['context_len']} 字符").classes("text-caption text-grey")
                        if meta.get("reply_len"):
                            ui.label(f"💬 {meta['reply_len']} 字符").classes("text-caption text-grey")
                        if meta.get("intent") and meta["intent"] != "unknown":
                            ui.badge(f"意图: {meta['intent']}", color="info")
                        if meta.get("tech_level") and meta["tech_level"] != "unknown":
                            ui.badge(f"技术: {meta['tech_level']}", color="positive")

        return card
