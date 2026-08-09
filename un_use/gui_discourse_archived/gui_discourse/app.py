# gui_discourse/app.py
"""MemoryGraph Discourse Block Tree — Gradio 傻瓜式 GUI。

运行方式：
    python gui_discourse/app.py

自动打开浏览器，包含 5 个 Tab：
- 快速开始：引导流程
- 对话测试：聊天 + Discourse 上下文可视化
- 配置管理：查看/修改 discourse.yaml
- 系统健康：Health Check 可视化
- 模型管理：模型下载状态与操作
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

# ── 路径设置 ─────────────────────────────────────────────────────

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ── 日志 ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gui_discourse")

# ── 依赖检测 ─────────────────────────────────────────────────────

_GRADIO_AVAILABLE = False
_GRADIO_IMPORT_ERROR = ""

try:
    import gradio as gr

    _GRADIO_VERSION = getattr(gr, "__version__", "unknown")
    _GRADIO_AVAILABLE = True
    logger.info(f"Gradio loaded: v{_GRADIO_VERSION}")
except Exception as e:
    _GRADIO_IMPORT_ERROR = str(e)
    logger.error(f"Gradio import failed: {e}")

# ── 核心组件导入（延迟/容错）───────────────────────────────────

_discourse_pipeline = None
_onboarding_agent = None
_health_checker = None
_model_downloader = None


def _get_discourse_pipeline():
    global _discourse_pipeline
    if _discourse_pipeline is not None:
        return _discourse_pipeline
    try:
        from core.agent.v3_common.discourse_integration import DiscoursePipeline

        _discourse_pipeline = DiscoursePipeline(session_id="gui_chat", hot_turns=5)
        return _discourse_pipeline
    except Exception as e:
        logger.error(f"DiscoursePipeline init failed: {e}")
        return None


def _get_onboarding_agent():
    global _onboarding_agent
    if _onboarding_agent is not None:
        return _onboarding_agent
    try:
        from core.agent.onboarding import OnboardingAgent

        _onboarding_agent = OnboardingAgent(session_id="gui")
        return _onboarding_agent
    except Exception as e:
        logger.error(f"OnboardingAgent init failed: {e}")
        return None


def _get_health_checker():
    global _health_checker
    if _health_checker is not None:
        return _health_checker
    try:
        from core.agent.v3_common.health_check import HealthChecker

        _health_checker = HealthChecker()
        return _health_checker
    except Exception as e:
        logger.error(f"HealthChecker init failed: {e}")
        return None


def _get_model_downloader():
    global _model_downloader
    if _model_downloader is not None:
        return _model_downloader
    try:
        from scripts.download_models import ModelDownloader

        _model_downloader = ModelDownloader()
        return _model_downloader
    except Exception as e:
        logger.error(f"ModelDownloader import failed: {e}")
        return None


# ── 工具函数 ─────────────────────────────────────────────────────


def _check_models_status() -> Dict[str, Any]:
    """检查模型下载状态。"""
    try:
        from scripts.download_models import ModelDownloader

        downloader = ModelDownloader()
        from core.agent.config.discourse_config import get_discourse_config

        config = get_discourse_config()
        return downloader.check_models(
            config.model_download.bge_model_id,
            config.model_download.ner_model_id,
        )
    except Exception as e:
        return {
            "bge": {"exists": False, "error": str(e)},
            "ner": {"exists": False, "error": str(e)},
            "all_ready": False,
        }


def _run_health_check() -> Dict[str, Any]:
    """运行健康检查。"""
    checker = _get_health_checker()
    if checker is None:
        return {"healthy": False, "error": "HealthChecker not available", "checks": []}
    try:
        status = checker.check_all()
        return status.to_dict()
    except Exception as e:
        return {"healthy": False, "error": str(e), "checks": []}


def _format_health_html(status: Dict[str, Any]) -> str:
    """将健康检查结果格式化为 HTML（绿/红可视化）。"""
    if "error" in status and not status.get("checks"):
        return f'<div style="color:red; padding:10px;">❌ 错误: {status["error"]}</div>'

    checks = status.get("checks", [])
    healthy = status.get("healthy", False)

    header_color = "#28a745" if healthy else "#dc3545"
    header_icon = "✅" if healthy else "❌"
    header_text = "HEALTHY" if healthy else "UNHEALTHY"

    rows = []
    for c in checks:
        s = c.get("status", "error")
        if s == "ok":
            color = "#28a745"
            icon = "✅"
        elif s == "warning":
            color = "#ffc107"
            icon = "⚠️"
        else:
            color = "#dc3545"
            icon = "❌"
        msg = c.get("message", "")
        latency = c.get("latency_ms", 0)
        latency_str = f"<span style='color:#666;font-size:12px;'>({latency:.1f}ms)</span>" if latency > 0 else ""
        rows.append(
            f'<div style="margin:4px 0; padding:8px; border-left:4px solid {color}; background:#f8f9fa; border-radius:4px;">'
            f'  <span style="font-weight:bold;">{icon} {c.get("name", "")}</span> '
            f'  <span style="color:{color};">{s.upper()}</span> {latency_str}<br/>'
            f'  <span style="color:#555; font-size:13px;">{msg}</span>'
            f'</div>'
        )

    html = f"""
    <div style="font-family: sans-serif; max-width: 800px;">
        <div style="padding:10px; background:{header_color}; color:white; border-radius:6px; margin-bottom:10px;">
            <strong style="font-size:18px;">{header_icon} Health Check: {header_text}</strong>
        </div>
        {''.join(rows)}
        <div style="margin-top:10px; padding:10px; background:#f0f0f0; border-radius:4px; font-size:12px; color:#666;">
            Timestamp: {status.get('timestamp', 'N/A')}
        </div>
    </div>
    """
    return html


def _format_config_html(config: Dict[str, Any]) -> str:
    """将配置格式化为 HTML 展示。"""
    sections = []
    for section, values in config.items():
        rows = []
        for k, v in values.items():
            rows.append(f'<tr><td style="padding:6px; border:1px solid #ddd;"><code>{k}</code></td><td style="padding:6px; border:1px solid #ddd;"><strong>{v}</strong></td></tr>')
        sections.append(
            f'<h3 style="margin-top:16px; color:#333;">📦 {section}</h3>'
            f'<table style="border-collapse:collapse; width:100%; max-width:600px; font-size:14px;">'
            f'<thead><tr style="background:#f0f0f0;"><th style="padding:8px; border:1px solid #ddd; text-align:left;">参数</th>'
            f'<th style="padding:8px; border:1px solid #ddd; text-align:left;">值</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
        )
    return f'<div style="font-family:sans-serif;">{"".join(sections)}</div>'


def _format_discourse_blocks(pipeline) -> str:
    """格式化 DiscoursePipeline 的块状态为 HTML。"""
    if pipeline is None or not hasattr(pipeline, "manager"):
        return "<div style='color:#666;'>Pipeline 未初始化</div>"
    try:
        blocks = pipeline.manager.get_blocks()
        if not blocks:
            return "<div style='color:#666;'>暂无话语块</div>"

        parts = []
        for b in blocks:
            if b.is_hot:
                color = "#d4edda"
                border = "#28a745"
                label = "🔥 Hot"
            elif b.is_warm:
                color = "#fff3cd"
                border = "#ffc107"
                label = "🌤 Warm"
            else:
                color = "#d1ecf1"
                border = "#17a2b8"
                label = "❄️ Cold"

            summary = b.latest_summary or "(无摘要)"
            text_preview = b.text[:120] + "..." if len(b.text) > 120 else b.text

            parts.append(
                f'<div style="margin:6px 0; padding:10px; background:{color}; border-left:4px solid {border}; border-radius:4px;">'
                f'  <div style="font-weight:bold; margin-bottom:4px;">{label} {b.id} (turns {b.start_turn}-{b.end_turn})</div>'
                f'  <div style="font-size:13px; color:#555; margin-bottom:4px;"><strong>Summary:</strong> {summary}</div>'
                f'  <div style="font-size:12px; color:#777;"><strong>Text:</strong> {text_preview}</div>'
                f'</div>'
            )
        return f'<div style="font-family:sans-serif; max-height:400px; overflow-y:auto;">{"".join(parts)}</div>'
    except Exception as e:
        return f'<div style="color:red;">Error formatting blocks: {e}</div>'


# ── Gradio 回调函数 ──────────────────────────────────────────────


def _greet_and_check() -> Tuple[str, str, str, str]:
    """Tab 1 初始化：欢迎语 + 健康检查 + 模型状态 + 预加载状态。"""
    agent = _get_onboarding_agent()
    if agent:
        try:
            welcome = agent.greet()
        except Exception as e:
            welcome = f"欢迎使用 MemoryGraph Discourse Block Tree！\n\n（引导 Agent 初始化失败: {e}）"
    else:
        welcome = "欢迎使用 MemoryGraph Discourse Block Tree！"

    health = _run_health_check()
    health_html = _format_health_html(health)

    models = _check_models_status()
    model_html = _format_model_status_html(models)

    return welcome, health_html, model_html, "⏳ 等待预加载..."


def _format_model_status_html(status: Dict[str, Any]) -> str:
    """格式化模型状态为 HTML。"""
    bge = status.get("bge", {})
    ner = status.get("ner", {})
    bge_ok = bge.get("exists", False)
    ner_ok = ner.get("exists", False)
    all_ok = status.get("all_ready", False)

    bge_color = "#28a745" if bge_ok else "#dc3545"
    ner_color = "#28a745" if ner_ok else "#dc3545"
    all_color = "#28a745" if all_ok else "#dc3545"

    return f"""
    <div style="font-family:sans-serif; padding:10px;">
        <div style="margin:4px 0;">
            <span style="color:{bge_color}; font-weight:bold;">{'✅' if bge_ok else '❌'} BGE</span>
            <span style="font-size:12px; color:#666;">{bge.get('model_id', 'N/A')}</span>
        </div>
        <div style="margin:4px 0;">
            <span style="color:{ner_color}; font-weight:bold;">{'✅' if ner_ok else '❌'} NER</span>
            <span style="font-size:12px; color:#666;">{ner.get('model_id', 'N/A')}</span>
        </div>
        <div style="margin:8px 0; padding:6px; background:{all_color}; color:white; border-radius:4px; text-align:center;">
            {'✅ 全部就绪' if all_ok else '❌ 部分模型缺失'}
        </div>
    </div>
    """


def _download_all_models() -> Generator[str, None, None]:
    """一键下载模型（生成器，用于进度显示）。"""
    yield "🚀 开始下载模型..."
    try:
        from scripts.download_models import ModelDownloader

        downloader = ModelDownloader()
        from core.agent.config.discourse_config import get_discourse_config

        config = get_discourse_config()
        bge_id = config.model_download.bge_model_id
        ner_id = config.model_download.ner_model_id

        yield f"📥 下载 BGE 模型: {bge_id}..."
        bge_ok = downloader.download_bge(bge_id)
        yield f"{'✅' if bge_ok else '❌'} BGE 下载完成\n📥 下载 NER 模型: {ner_id}..."
        ner_ok = downloader.download_ner(ner_id)
        yield f"{'✅' if bge_ok else '❌'} BGE 完成\n{'✅' if ner_ok else '❌'} NER 完成\n\n🎉 全部完成！"
    except Exception as e:
        yield f"❌ 下载失败: {e}"


def _preload_models() -> Generator[str, None, None]:
    """预加载模型（生成器，用于进度显示）。"""
    yield "🚀 开始预加载..."
    pipeline = _get_discourse_pipeline()
    if pipeline is None:
        yield "❌ DiscoursePipeline 不可用"
        return
    try:
        yield "⏳ 正在预加载 BGE 编码器和 jieba 词典...（可能需要 1-2 分钟）"
        pipeline.preload(blocking=True)
        yield "✅ 预加载完成！系统已就绪。"
    except Exception as e:
        yield f"❌ 预加载失败: {e}"


def _chat_with_discourse(user_input: str, history: List[List[str]]) -> Tuple[List[List[str]], str, str]:
    """对话测试：处理用户输入，返回对话历史和 Discourse 上下文。"""
    if not user_input.strip():
        return history, "", ""

    pipeline = _get_discourse_pipeline()
    if pipeline is None:
        return history + [[user_input, "❌ Pipeline 不可用"]], "", ""

    try:
        # 将 history 转换为 DiscoursePipeline 需要的格式
        session_history = []
        for h in history:
            if h[0]:
                session_history.append({"role": "user", "content": h[0]})
            if h[1]:
                session_history.append({"role": "assistant", "content": h[1]})

        turn_index = len(history)
        discourse_ctx = pipeline.process_turn(user_input, session_history, turn_index)

        # 简单回复（TODO: 可接入 LLM）
        reply = f"已处理。Discourse 上下文长度: {len(discourse_ctx)} 字符。"

        # 块可视化
        blocks_html = _format_discourse_blocks(pipeline)

        new_history = history + [[user_input, reply]]
        return new_history, discourse_ctx, blocks_html
    except Exception as e:
        return history + [[user_input, f"❌ Error: {e}"]], "", ""


def _load_current_config() -> Tuple[str, str]:
    """加载当前配置用于显示。"""
    agent = _get_onboarding_agent()
    if agent is None:
        return "无法加载配置", ""
    try:
        cfg = agent.get_config()
        cfg_json = json.dumps(cfg, ensure_ascii=False, indent=2)
        cfg_html = _format_config_html(cfg)
        return cfg_html, cfg_json
    except Exception as e:
        return f"加载配置失败: {e}", ""


def _save_config_changes(
    threshold: float,
    hot_turns: int,
    cooling_turns: int,
    cold_turns: int,
    merge_threshold: float,
    v3_trigger: int,
    complex_length: int,
) -> str:
    """保存配置修改到 discourse.yaml。"""
    agent = _get_onboarding_agent()
    if agent is None:
        return "❌ Agent 不可用"

    results = []
    updates = [
        ("segmenter.threshold", threshold),
        ("manager.hot_turns", hot_turns),
        ("manager.cooling_turns", cooling_turns),
        ("manager.cold_turns", cold_turns),
        ("manager.merge_threshold", merge_threshold),
        ("summary.v3_trigger_turn_count", v3_trigger),
        ("decomposer.complex_clause_length", complex_length),
    ]

    for key, value in updates:
        try:
            result = agent.update_config(key, value)
            if result.get("success"):
                results.append(f"✅ {key} = {value}")
            else:
                results.append(f"❌ {key}: {result.get('error', 'unknown')}")
        except Exception as e:
            results.append(f"❌ {key}: {e}")

    return "\n".join(results)


def _run_and_show_health() -> str:
    """运行健康检查并返回 HTML 可视化。"""
    status = _run_health_check()
    return _format_health_html(status)


# ── GUI 构建 ─────────────────────────────────────────────────────


def _build_app() -> "gr.Blocks":  # type: ignore
    """构建 Gradio 应用。"""
    import gradio as gr

    with gr.Blocks(
        title="MemoryGraph Discourse Block Tree — 傻瓜式 GUI",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown(
            "# 🧠 MemoryGraph Discourse Block Tree\n"
            "### 傻瓜式 GUI — 一键上手话语块树系统"
        )

        # ═══════════════════════════════════════
        # Tab 1: 快速开始
        # ═══════════════════════════════════════
        with gr.Tab("🚀 快速开始"):
            gr.Markdown("## 欢迎使用！我是 Momo，你的引导助手。")

            with gr.Row():
                with gr.Column(scale=2):
                    welcome_box = gr.Textbox(
                        label="👋 欢迎语",
                        lines=10,
                        interactive=False,
                        value="正在初始化...",
                    )
                with gr.Column(scale=1):
                    gr.Markdown(
                        "### 快速导航\n"
                        "- **Tab 2: 对话测试** — 体验 Discourse Block Tree 上下文管理\n"
                        "- **Tab 3: 配置管理** — 调整 threshold、hot_turns 等参数\n"
                        "- **Tab 4: 系统健康** — 运行诊断检查\n"
                        "- **Tab 5: 模型管理** — 下载/检查模型状态"
                    )

            gr.Markdown("---")
            gr.Markdown("### 步骤 2：系统健康检查")
            health_html = gr.HTML(label="健康状态", value="<div>等待检查...</div>")

            gr.Markdown("---")
            gr.Markdown("### 步骤 3：模型状态")
            model_html = gr.HTML(label="模型状态", value="<div>检查中...</div>")
            with gr.Row():
                download_btn = gr.Button("📥 一键下载模型", variant="primary")
                download_output = gr.Textbox(label="下载进度", lines=6, interactive=False)

            gr.Markdown("---")
            gr.Markdown("### 步骤 4：预加载模型（消除冷启动）")
            with gr.Row():
                preload_btn = gr.Button("⚡ 预加载模型", variant="secondary")
                preload_output = gr.Textbox(label="预加载进度", lines=4, interactive=False)

            gr.Markdown("---")
            gr.Markdown("### 步骤 5：简单对话测试")
            quick_chat_input = gr.Textbox(label="输入一句话试试", placeholder="例如：你好，请介绍一下系统")
            quick_chat_output = gr.Textbox(label="回复", lines=3, interactive=False)

            # 初始化加载
            app.load(
                fn=_greet_and_check,
                inputs=[],
                outputs=[welcome_box, health_html, model_html, preload_output],
            )

            download_btn.click(
                fn=_download_all_models,
                inputs=[],
                outputs=[download_output],
            )
            preload_btn.click(
                fn=_preload_models,
                inputs=[],
                outputs=[preload_output],
            )

            def _quick_chat(text: str) -> str:
                if not text.strip():
                    return ""
                agent = _get_onboarding_agent()
                if agent:
                    return agent.respond(text)
                return "引导 Agent 不可用"

            quick_chat_input.submit(
                fn=_quick_chat,
                inputs=[quick_chat_input],
                outputs=[quick_chat_output],
            )

        # ═══════════════════════════════════════
        # Tab 2: 对话测试
        # ═══════════════════════════════════════
        with gr.Tab("💬 对话测试"):
            gr.Markdown(
                "## 对话测试 — 体验 Discourse Block Tree\n"
                "输入文本后，系统会运行完整编译器管道（Stage 1-3），"
                "输出 Hot/Warm/Cold 话语块上下文。"
            )

            chatbot = gr.Chatbot(label="对话", height=300)
            with gr.Row():
                chat_input = gr.Textbox(
                    label="输入",
                    placeholder="输入任意文本...",
                    scale=4,
                )
                chat_submit = gr.Button("发送", variant="primary", scale=1)
            chat_clear = gr.Button("清空对话")

            gr.Markdown("---")
            gr.Markdown("### Discourse 上下文输出（原始文本）")
            discourse_ctx = gr.Textbox(label="Discourse Context", lines=8, interactive=False)

            gr.Markdown("---")
            gr.Markdown("### 话语块可视化（Hot 🔥 / Warm 🌤 / Cold ❄️）")
            blocks_html = gr.HTML(label="话语块", value="<div>暂无对话</div>")

            chat_submit.click(
                fn=_chat_with_discourse,
                inputs=[chat_input, chatbot],
                outputs=[chatbot, discourse_ctx, blocks_html],
            ).then(lambda: "", outputs=[chat_input])
            chat_input.submit(
                fn=_chat_with_discourse,
                inputs=[chat_input, chatbot],
                outputs=[chatbot, discourse_ctx, blocks_html],
            ).then(lambda: "", outputs=[chat_input])

            def _reset_chat():
                """清空对话并重置 DiscoursePipeline 状态。"""
                pipeline = _get_discourse_pipeline()
                if pipeline is not None:
                    try:
                        pipeline.reset()
                    except Exception as e:
                        logger.debug(f"Pipeline reset failed: {e}")
                return [], "", "<div style='color:#666;'>对话已清空，Pipeline 已重置</div>"

            chat_clear.click(
                fn=_reset_chat,
                inputs=[],
                outputs=[chatbot, discourse_ctx, blocks_html],
            )

        # ═══════════════════════════════════════
        # Tab 3: 配置管理
        # ═══════════════════════════════════════
        with gr.Tab("⚙️ 配置管理"):
            gr.Markdown(
                "## 配置管理\n"
                "当前配置从代码默认值 + `~/.config/memorygraph/discourse.yaml` + 环境变量合并而来。\n"
                "修改后保存到 YAML 文件并自动热重载。"
            )

            with gr.Row():
                with gr.Column(scale=1):
                    config_refresh = gr.Button("🔄 刷新配置")
                    config_save = gr.Button("💾 保存修改", variant="primary")
                    config_result = gr.Textbox(label="保存结果", lines=8, interactive=False)

                with gr.Column(scale=1):
                    gr.Markdown("### 关键参数")
                    cfg_threshold = gr.Number(
                        label="segmenter.threshold（切分阈值，默认 0.5）",
                        value=0.5,
                        step=0.05,
                        minimum=0.0,
                        maximum=1.0,
                    )
                    cfg_hot_turns = gr.Number(
                        label="manager.hot_turns（Hot 轮数，默认 5）",
                        value=5,
                        step=1,
                        minimum=1,
                        maximum=50,
                        precision=0,
                    )
                    cfg_cooling_turns = gr.Number(
                        label="manager.cooling_turns（Warm 起始偏移，默认 5）",
                        value=5,
                        step=1,
                        minimum=1,
                        maximum=50,
                        precision=0,
                    )
                    cfg_cold_turns = gr.Number(
                        label="manager.cold_turns（Cold 起始偏移，默认 10）",
                        value=10,
                        step=1,
                        minimum=1,
                        maximum=100,
                        precision=0,
                    )
                    cfg_merge_threshold = gr.Number(
                        label="manager.merge_threshold（合并阈值，默认 0.55）",
                        value=0.55,
                        step=0.05,
                        minimum=0.0,
                        maximum=1.0,
                    )
                    cfg_v3_trigger = gr.Number(
                        label="summary.v3_trigger_turn_count（v3 触发轮数，默认 5）",
                        value=5,
                        step=1,
                        minimum=1,
                        maximum=50,
                        precision=0,
                    )
                    cfg_complex_length = gr.Number(
                        label="decomposer.complex_clause_length（复杂子句长度，默认 30）",
                        value=30,
                        step=1,
                        minimum=10,
                        maximum=200,
                        precision=0,
                    )

            gr.Markdown("---")
            gr.Markdown("### 完整配置 JSON")
            config_json = gr.JSON(label="Config JSON")

            gr.Markdown("### 配置可视化")
            config_html = gr.HTML(label="Config HTML")

            # 刷新配置
            def _refresh_config():
                html, json_str = _load_current_config()
                try:
                    cfg = json.loads(json_str) if json_str else {}
                except Exception:
                    cfg = {}

                seg = cfg.get("segmenter", {})
                mgr = cfg.get("manager", {})
                summ = cfg.get("summary", {})
                dec = cfg.get("decomposer", {})

                return (
                    html,
                    cfg,
                    seg.get("threshold", 0.5),
                    mgr.get("hot_turns", 5),
                    mgr.get("cooling_turns", 5),
                    mgr.get("cold_turns", 10),
                    mgr.get("merge_threshold", 0.55),
                    summ.get("v3_trigger_turn_count", 5),
                    dec.get("complex_clause_length", 30),
                )

            config_refresh.click(
                fn=_refresh_config,
                inputs=[],
                outputs=[
                    config_html,
                    config_json,
                    cfg_threshold,
                    cfg_hot_turns,
                    cfg_cooling_turns,
                    cfg_cold_turns,
                    cfg_merge_threshold,
                    cfg_v3_trigger,
                    cfg_complex_length,
                ],
            )

            # 保存配置
            config_save.click(
                fn=_save_config_changes,
                inputs=[
                    cfg_threshold,
                    cfg_hot_turns,
                    cfg_cooling_turns,
                    cfg_cold_turns,
                    cfg_merge_threshold,
                    cfg_v3_trigger,
                    cfg_complex_length,
                ],
                outputs=[config_result],
            ).then(
                fn=_refresh_config,
                inputs=[],
                outputs=[
                    config_html,
                    config_json,
                    cfg_threshold,
                    cfg_hot_turns,
                    cfg_cooling_turns,
                    cfg_cold_turns,
                    cfg_merge_threshold,
                    cfg_v3_trigger,
                    cfg_complex_length,
                ],
            )

            # 初始化加载
            app.load(
                fn=_refresh_config,
                inputs=[],
                outputs=[
                    config_html,
                    config_json,
                    cfg_threshold,
                    cfg_hot_turns,
                    cfg_cooling_turns,
                    cfg_cold_turns,
                    cfg_merge_threshold,
                    cfg_v3_trigger,
                    cfg_complex_length,
                ],
            )

        # ═══════════════════════════════════════
        # Tab 4: 系统健康
        # ═══════════════════════════════════════
        with gr.Tab("🏥 系统健康"):
            gr.Markdown(
                "## 系统健康检查\n"
                "运行所有诊断项：模型就绪、编码器可加载、语义解析器、jieba 词典、配置系统。"
            )
            health_run_btn = gr.Button("🔍 运行健康检查", variant="primary")
            health_display = gr.HTML(label="检查结果", value="<div>点击按钮运行检查...</div>")
            health_json = gr.JSON(label="原始 JSON")

            def _run_health():
                status = _run_health_check()
                return _format_health_html(status), status

            health_run_btn.click(
                fn=_run_health,
                inputs=[],
                outputs=[health_display, health_json],
            )

            # 初始化加载
            app.load(
                fn=_run_health,
                inputs=[],
                outputs=[health_display, health_json],
            )

        # ═══════════════════════════════════════
        # Tab 5: 模型管理
        # ═══════════════════════════════════════
        with gr.Tab("📦 模型管理"):
            gr.Markdown(
                "## 模型管理\n"
                "查看模型下载状态，一键下载 BGE 和 NER 模型。"
            )

            with gr.Row():
                with gr.Column(scale=1):
                    model_check_btn = gr.Button("🔄 刷新状态")
                    model_bge_btn = gr.Button("📥 下载 BGE 模型")
                    model_ner_btn = gr.Button("📥 下载 NER 模型")
                    model_all_btn = gr.Button("📥 一键下载全部", variant="primary")
                with gr.Column(scale=2):
                    model_status_display = gr.HTML(label="模型状态")
                    model_log = gr.Textbox(label="操作日志", lines=10, interactive=False)

            def _refresh_model_status():
                status = _check_models_status()
                return _format_model_status_html(status)

            def _download_model_single(model_name: str) -> Generator[str, None, None]:
                yield f"🚀 开始下载 {model_name}..."
                try:
                    from scripts.download_models import ModelDownloader

                    downloader = ModelDownloader()
                    from core.agent.config.discourse_config import get_discourse_config

                    config = get_discourse_config()
                    if model_name == "bge":
                        ok = downloader.download_bge(config.model_download.bge_model_id)
                    elif model_name == "ner":
                        ok = downloader.download_ner(config.model_download.ner_model_id)
                    else:
                        bge_ok = downloader.download_bge(config.model_download.bge_model_id)
                        yield f"BGE: {'✅' if bge_ok else '❌'}\n下载 NER..."
                        ner_ok = downloader.download_ner(config.model_download.ner_model_id)
                        ok = bge_ok and ner_ok
                        yield f"BGE: {'✅' if bge_ok else '❌'}\nNER: {'✅' if ner_ok else '❌'}\n全部: {'✅' if ok else '❌'}"
                        return
                    yield f"{'✅' if ok else '❌'} {model_name} 下载完成"
                except Exception as e:
                    yield f"❌ 下载失败: {e}"

            model_check_btn.click(
                fn=_refresh_model_status,
                inputs=[],
                outputs=[model_status_display],
            )
            model_bge_btn.click(
                fn=_download_model_single,
                inputs=[gr.State("bge")],
                outputs=[model_log],
            )
            model_ner_btn.click(
                fn=_download_model_single,
                inputs=[gr.State("ner")],
                outputs=[model_log],
            )
            model_all_btn.click(
                fn=_download_model_single,
                inputs=[gr.State("all")],
                outputs=[model_log],
            )

            # 初始化加载
            app.load(
                fn=_refresh_model_status,
                inputs=[],
                outputs=[model_status_display],
            )

        # ═══════════════════════════════════════
        # Footer
        # ═══════════════════════════════════════
        gr.Markdown(
            "---\n"
            "<div style='text-align:center; color:#666; font-size:12px;'>\n"
            "MemoryGraph Discourse Block Tree | 运行命令: <code>python gui_discourse/app.py</code>\n"
            "</div>"
        )

    return app


# ── 主入口 ───────────────────────────────────────────────────────


def main():
    """启动 GUI。"""
    if not _GRADIO_AVAILABLE:
        print("=" * 60)
        print("❌ Gradio 未安装")
        print(f"导入错误: {_GRADIO_IMPORT_ERROR}")
        print()
        print("请安装依赖：")
        print("    pip install gradio>=4.0.0")
        print()
        print("或安装完整依赖：")
        print("    pip install -r requirements.txt")
        print("=" * 60)
        sys.exit(1)

    try:
        app = _build_app()
    except Exception as e:
        print(f"构建 GUI 失败: {e}")
        traceback.print_exc()
        sys.exit(1)

    print("=" * 60)
    print("🚀 MemoryGraph Discourse Block Tree GUI 启动中...")
    print(f"项目根目录: {project_root}")
    print("=" * 60)

    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
        show_error=True,
    )


if __name__ == "__main__":
    main()
