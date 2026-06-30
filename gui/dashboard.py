import sys, os, re, html, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from nicegui import ui

from core.agent.context_manager.discourse_manager import DiscourseManager
from core.agent.coordinator.adaptive_threshold import ThresholdProfile
from core.agent.coordinator.small_model_client import reset_small_model_client


# ═══════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════

@dataclass
class AppState:
    user_id: str = "demo_user"
    session_id: str = "demo_session"
    dm: Optional[DiscourseManager] = None
    dm_ready: bool = False

    tech_level: str = "unknown"
    patience_level: str = "neutral"
    attention_span: str = "medium"
    turn_count: int = 0
    topic_switches: int = 0
    domains: List[str] = field(default_factory=list)

    tasks: List[Dict] = field(default_factory=list)
    messages: List[Dict] = field(default_factory=list)

    bayesian_evaluations: int = 0
    bayesian_mode_pref: Dict[str, float] = field(default_factory=dict)
    base_offset_mu: float = 0.0
    base_offset_std: float = 1.0
    is_satisfied: float = 0.5
    is_impatient: float = 0.5

    last_mode: str = "unknown"
    last_latency: float = 0.0

    def init_dm(self):
        if self.dm is None:
            try:
                reset_small_model_client()
                self.dm = DiscourseManager(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    mode="auto",
                    cost_budget="standard",
                    preload=True,
                )
                self.dm_ready = True
            except Exception as e:
                print(f"DM init failed: {e}")
                self.dm_ready = False

    def refresh_from_dm(self):
        if self.dm is None or not self.dm_ready:
            return
        p = self.dm.user_profile
        if p:
            self.tech_level = p.tech_level or "unknown"
            self.patience_level = p.patience_level or "neutral"
            self.attention_span = p.attention_span or "medium"
            self.turn_count = p.turn_count
            self.topic_switches = p.topic_switches
            self.domains = list(p.domains[:10])

        if self.dm.task_manager:
            self.tasks = [
                {
                    "id": t.task_id[:8],
                    "type": t.task_type,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "progress": t.progress,
                    "sub": t.is_subtask,
                }
                for t in self.dm.task_manager.get_all_tasks()
            ]

        if p and p.threshold_profile:
            try:
                tp = ThresholdProfile.from_dict(p.threshold_profile)
                be = tp._get_bayesian()
                if be:
                    self.bayesian_evaluations = tp.total_evaluations
                    self.bayesian_mode_pref = be.get_categorical_probs("mode_preference")
                    self.base_offset_mu = be.get_gaussian_mean("base_offset")
                    self.base_offset_std = be.get_gaussian_std("base_offset")
                    self.is_satisfied = be.get_binary_mean("is_satisfied")
                    self.is_impatient = be.get_binary_mean("is_impatient")
            except Exception:
                pass

    def parse_context_summary(self, result: str, query: str) -> Dict:
        summary = {
            "raw_context": result,
            "tech_level": "unknown",
            "intent": "unknown",
            "domains": [],
            "tasks": [],
            "has_profile": False,
            "has_task": False,
            "turn_index": len(self.messages) // 2,
        }
        if "[user_profile]" in result or "[技术水平" in result:
            summary["has_profile"] = True
            m = re.search(r'"tech_level"\s*:\s*"([^"]+)"', result)
            if m:
                summary["tech_level"] = m.group(1)
            m = re.search(r'"domains"\s*:\s*\[([^\]]*)\]', result)
            if m:
                summary["domains"] = [d.strip().strip('"') for d in m.group(1).split(",") if d.strip()]
        if "[task_progress]" in result or "任务" in result:
            summary["has_task"] = True
            m = re.search(r'"task_type"\s*:\s*"([^"]+)"', result)
            if m:
                summary["tasks"].append(m.group(1))
        if "[intent" in result or "intent" in result:
            m = re.search(r'"intent_label"\s*:\s*"([^"]+)"', result)
            if m:
                summary["intent"] = m.group(1)
        return summary

    def record_user_feedback(self, turn_index: int, is_satisfied: Optional[bool] = None, is_correction: bool = False) -> bool:
        if not self.dm_ready or self.dm is None or not self.dm.user_profile:
            return False
        try:
            if self.dm.user_profile.threshold_profile:
                tp = ThresholdProfile.from_dict(self.dm.user_profile.threshold_profile)
                tp.record_feedback(
                    original_score=5,
                    used_mode=self.last_mode,
                    user_correction=is_correction,
                    user_satisfied=is_satisfied,
                )
                self.dm.user_profile.threshold_profile = tp.to_dict()
                self.refresh_from_dm()
                return True
        except Exception as e:
            print(f"Feedback failed: {e}")
        return False

    def send_message(self, query: str) -> Dict:
        if self.dm is None:
            self.init_dm()
        if not self.dm_ready or self.dm is None:
            return {"error": "DiscourseManager not ready", "mode": "error"}

        turn_idx = len(self.messages) // 2
        start = time.time()
        try:
            # 1. 组装上下文（历史 + 用户画像 + 任务等）
            context = self.dm.process_turn(query, turn_index=turn_idx)
            context_latency = time.time() - start

            # 2. 调用 LLM 生成实际回复
            llm_start = time.time()
            try:
                from core.agent.coordinator.multi_tier_llm_client import invoke_llm
                # 构建对话 prompt：上下文 + 当前查询
                conversation_prompt = self._build_chat_prompt(context, query)
                llm_reply = invoke_llm(
                    conversation_prompt,
                    task_type="simple_reply",
                    system_prompt="你是一个 helpful 的 AI 助手。根据提供的上下文，回复用户的问题。回复要简洁、自然。",
                    max_tokens=1024,  # 增加：为 reasoning tokens 留出空间
                    temperature=0.7,
                )
                if llm_reply and len(llm_reply.strip()) > 0:
                    reply = llm_reply.strip()
                else:
                    # LLM 返回空，回退到上下文摘要
                    reply = context[:500] if context else "（系统处理中...）"
            except Exception as e:
                # LLM 调用失败，回退到上下文
                reply = context[:500] if context else f"（处理出错：{e}）"
            llm_latency = time.time() - llm_start
            total_latency = time.time() - start

            # 3. 确定模式
            mode = "rule"
            if self.dm.user_profile and self.dm.user_profile.threshold_profile:
                try:
                    tp = ThresholdProfile.from_dict(self.dm.user_profile.threshold_profile)
                    mode = tp.get_mode(5)
                except Exception:
                    pass

            self.last_mode = mode
            self.last_latency = total_latency
            summary = self.parse_context_summary(context, query)

            self.messages.append({
                "role": "user",
                "content": query,
                "turn": turn_idx,
                "time": time.strftime("%H:%M:%S"),
            })
            self.messages.append({
                "role": "system",
                "content": reply,               # ← 显示 LLM 生成的自然语言回复
                "raw_context": context,          # ← 保留原始上下文（调试用）
                "parsed_summary": summary,
                "mode": mode,
                "latency": total_latency,
                "context_latency": context_latency,
                "llm_latency": llm_latency,
                "context_len": len(context),
                "reply_len": len(reply),
                "turn": turn_idx,
                "time": time.strftime("%H:%M:%S"),
            })
            self.refresh_from_dm()
            return {
                "result": reply,
                "context": context,
                "parsed_summary": summary,
                "mode": mode,
                "latency": total_latency,
                "context_len": len(context),
                "reply_len": len(reply),
            }
        except Exception as e:
            return {"error": str(e), "mode": "error"}

    def _build_chat_prompt(self, context: str, query: str) -> str:
        """构建精简对话 prompt，适合小模型处理。"""
        # 只提取最近 2 轮对话历史（避免过长）
        history_lines = []
        for msg in self.messages[-4:]:  # 最近 2 轮（4 条消息）
            if msg["role"] == "user":
                history_lines.append(f"用户：{msg['content'][:100]}")
            elif msg["role"] == "system":
                history_lines.append(f"助手：{msg['content'][:100]}")
        
        history_text = "\n".join(history_lines) if history_lines else "（无历史对话）"
        
        # 精简上下文：只取前 300 字符（用户画像等关键信息）
        context_summary = context[:300] if context else ""
        
        prompt = f"""用户画像：{context_summary}

历史对话：
{history_text}

当前问题：{query}

请用中文简洁回复："""
        return prompt


state = AppState()


# ═══════════════════════════════════════════════════════════════
# 反馈按钮工厂
# ═══════════════════════════════════════════════════════════════

def feedback_factory(ti, sat, corr):
    def _fn():
        state.record_user_feedback(ti, is_satisfied=sat, is_correction=corr)
        ui.notify(f"已记录: {'满意' if sat else '不满意'}" + (" (纠错)" if corr else ""), color="positive")
    return _fn


# ═══════════════════════════════════════════════════════════════
# 仪表盘面板
# ═══════════════════════════════════════════════════════════════

def dashboard_panel():
    with ui.column().classes("w-full q-pa-md"):
        ui.label("仪表盘").classes("text-h4 q-mb-md")

        with ui.row().classes("w-full q-gutter-md"):
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("对话轮次").classes("text-subtitle2 text-grey")
                    ui.label().bind_text_from(state, "turn_count").classes("text-h4 text-primary")
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("话题切换").classes("text-subtitle2 text-grey")
                    ui.label().bind_text_from(state, "topic_switches").classes("text-h4 text-orange")
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("技术等级").classes("text-subtitle2 text-grey")
                    ui.label().bind_text_from(state, "tech_level").classes("text-h4 text-primary")
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("上次模式").classes("text-subtitle2 text-grey")
                    ui.label().bind_text_from(state, "last_mode").classes("text-h4 text-primary")
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("延迟").classes("text-subtitle2 text-grey")
                    latency_label = ui.label("0.00s").classes("text-h4 text-primary")
                    def update_latency():
                        latency_label.set_text(f"{state.last_latency:.2f}s")
                    ui.timer(1.0, update_latency)

        with ui.row().classes("w-full q-gutter-md q-mt-md"):
            with ui.card().classes("col-6"):
                with ui.card_section():
                    ui.label("用户画像雷达图").classes("text-h6")
                    radar_options = {
                        "radar": {
                            "indicator": [
                                {"name": "技术深度", "max": 10},
                                {"name": "耐心", "max": 10},
                                {"name": "注意力", "max": 10},
                                {"name": "活跃度", "max": 10},
                                {"name": "稳定性", "max": 10},
                            ]
                        },
                        "series": [{
                            "type": "radar",
                            "data": [{"value": [0, 5, 6, 0, 10], "name": "用户画像"}]
                        }]
                    }
                    radar_chart = ui.echart(radar_options).classes("w-full").style("height: 300px")

                    def update_radar():
                        tech_map = {"beginner": 3, "intermediate": 6, "expert": 9, "unknown": 0}
                        pat_map = {"impatient": 2, "neutral": 5, "patient": 8}
                        attn_map = {"short": 3, "medium": 6, "long": 9}
                        new_val = [
                            tech_map.get(state.tech_level, 0),
                            pat_map.get(state.patience_level, 5),
                            attn_map.get(state.attention_span, 6),
                            min(10, state.turn_count / 3),
                            max(0, 10 - state.topic_switches),
                        ]
                        radar_chart._props['options'] = {
                            "radar": {"indicator": [
                                {"name": "技术深度", "max": 10},
                                {"name": "耐心", "max": 10},
                                {"name": "注意力", "max": 10},
                                {"name": "活跃度", "max": 10},
                                {"name": "稳定性", "max": 10},
                            ]},
                            "series": [{"type": "radar", "data": [{"value": new_val, "name": "用户画像"}]}]
                        }
                        radar_chart.update()

                    update_radar()
                    ui.timer(2.0, update_radar)

            with ui.card().classes("col-6"):
                with ui.card_section():
                    ui.label("关注领域").classes("text-h6")
                    domain_container = ui.row().classes("q-gutter-sm")
                    def update_domains():
                        domain_container.clear()
                        with domain_container:
                            for d in state.domains:
                                ui.chip(d, color="primary")
                    ui.timer(2.0, update_domains)


# ═══════════════════════════════════════════════════════════════
# 对话树面板
# ═══════════════════════════════════════════════════════════════

def tree_panel():
    """对话树面板 -- 按话题聚合树形展示。"""
    with ui.column().classes("w-full q-pa-md"):
        ui.label("🌳 对话树浏览器（按话题聚合）").classes("text-h4 q-mb-md")
        
        tree_container = ui.column().classes("w-full")
        
        def render_tree():
            dm = state.dm
            if not dm or not hasattr(dm, "_topic_tree") or not dm._topic_tree:
                tree_container.clear()
                with tree_container:
                    ui.label("暂无对话数据。请在实时对话面板发送消息。").classes("text-grey")
                return
            
            html_parts = ['<div style="font-family: monospace; line-height: 1.6;">']
            
            # 按话题 ID 排序
            topic_ids = sorted(dm._topic_tree.keys())
            
            for topic_id in topic_ids:
                node = dm._topic_tree[topic_id]
                topic_name = node.get("name", f"话题 {topic_id}")
                turns = node.get("turns", [])
                domains = list(node.get("domains", set()))[:5]
                parent = node.get("parent_topic")
                intent = node.get("intent", "unknown")
                start_idx = node.get("start_idx", 0)
                end_idx = node.get("end_idx", 0)
                
                # 话题分支颜色（根据是否有父话题区分主分支/子分支）
                bg_color = "#fff3e0" if parent is not None else "#e3f2fd"
                border_color = "#ff9800" if parent is not None else "#2196f3"
                
                html_parts.append('<details style="margin: 6px 0; border: 2px solid ' + border_color + '; border-radius: 6px; background: ' + bg_color + ';">')
                html_parts.append('<summary style="cursor: pointer; padding: 10px 14px; font-weight: bold; font-size: 15px; background: ' + bg_color + '; border-radius: 6px; display: flex; align-items: center;">')
                
                # 话题标题
                parent_label = " ↳ " if parent is not None else " "
                html_parts.append("📁" + parent_label + "话题 " + str(topic_id) + ": " + html.escape(topic_name))
                
                # 元信息标签
                html_parts.append('<span style="margin-left: auto; font-size: 12px; color: #666; font-weight: normal;">')
                html_parts.append("T" + str(start_idx) + "-T" + str(end_idx) + " | " + str(len(turns)) + " 轮")
                if domains:
                    html_parts.append(" | " + " · ".join(domains))
                html_parts.append("</span>")
                html_parts.append("</summary>")
                html_parts.append('<div style="padding: 8px 12px 8px 24px;">')
                
                # 该话题下的所有 Turn
                for turn in turns:
                    raw = html.escape(getattr(turn, "raw_query", "")[:50])
                    full_raw = html.escape(getattr(turn, "raw_query", ""))
                    turn_idx = turn.turn_index
                    
                    html_parts.append('<details style="margin: 3px 0; border: 1px solid #ddd; border-radius: 4px; background: #fafafa;">')
                    html_parts.append('<summary style="cursor: pointer; padding: 6px 10px; font-weight: bold; background: #f5f5f5; border-radius: 4px; font-size: 13px;">')
                    html_parts.append("📝 T" + str(turn_idx) + ": " + raw + ("..." if len(full_raw) > 50 else ""))
                    html_parts.append("</summary>")
                    html_parts.append('<div style="padding: 6px 10px 6px 20px;">')
                    
                    # Query Block
                    html_parts.append('<details style="margin: 2px 0;">')
                    html_parts.append('<summary style="cursor: pointer; color: #1565c0; font-size: 12px;">📄 [query] ' + raw + "</summary>")
                    html_parts.append('<div style="padding-left: 14px; color: #555; font-size: 11px;">')
                    html_parts.append("<div>📝 V1 原文 (" + str(len(full_raw)) + " 字)</div>")
                    html_parts.append("<div>📋 意图: query</div>")
                    html_parts.append("</div></details>")
                    
                    # Context Blocks
                    if hasattr(turn, "context_blocks") and turn.context_blocks:
                        html_parts.append('<details style="margin: 2px 0;">')
                        html_parts.append('<summary style="cursor: pointer; color: #2e7d32; font-size: 12px;">📎 系统上下文 (' + str(len(turn.context_blocks)) + " 块)</summary>")
                        html_parts.append('<div style="padding-left: 14px; color: #555; font-size: 11px;">')
                        for i, cb in enumerate(turn.context_blocks):
                            c = html.escape(str(cb.content)[:60])
                            suffix = "..." if len(str(cb.content)) > 60 else ""
                            html_parts.append("<div>[" + cb.type + "] " + c + suffix + "</div>")
                        html_parts.append("</div></details>")
                    
                    # Discourse Blocks
                    if hasattr(turn, "discourse_blocks") and turn.discourse_blocks:
                        for block in turn.discourse_blocks:
                            bid = getattr(block, "id", "T" + str(turn_idx) + "-B")
                            intent = getattr(block, "intent_label", "unknown")
                            text = getattr(block, "text", "") or getattr(block, "raw_text", "")
                            btype = getattr(block, "type", "unknown")
                            text_display = html.escape(text[:50]) if text else "(empty)"
                            
                            html_parts.append('<details style="margin: 2px 0;">')
                            suffix = "..." if len(text) > 50 else ""
                            html_parts.append('<summary style="cursor: pointer; color: #6a1b9a; font-size: 12px;">📄 [' + intent + "] " + text_display + suffix + "</summary>")
                            html_parts.append('<div style="padding-left: 14px; color: #555; font-size: 11px;">')
                            html_parts.append("<div>📝 V1 原文 (" + str(len(text)) + " 字)</div>")
                            html_parts.append("<div>📋 类型: " + btype + " | 意图: " + intent + "</div>")
                            
                            v2 = getattr(block, "compressed", None)
                            if v2:
                                v2d = html.escape(str(v2)[:60])
                                suffix2 = "..." if len(str(v2)) > 60 else ""
                                html_parts.append("<div>✂️ V2 (" + str(len(v2)) + " 字): " + v2d + suffix2 + "</div>")
                            
                            v3 = getattr(block, "tags", None)
                            if v3:
                                v3d = html.escape(str(v3)[:60])
                                suffix3 = "..." if len(str(v3)) > 60 else ""
                                html_parts.append("<div>🏷️ V3: " + v3d + suffix3 + "</div>")
                            
                            html_parts.append("</div></details>")
                    
                    html_parts.append("</div></details>")
                
                html_parts.append("</div></details>")
            
            html_parts.append("</div>")
            
            tree_container.clear()
            with tree_container:
                ui.html("".join(html_parts)).classes("w-full")
        
        ui.timer(2.0, render_tree)
        ui.button("刷新", on_click=render_tree).props("size=sm")


# ═══════════════════════════════════════════════════════════════
# 任务看板面板
# ═══════════════════════════════════════════════════════════════

def tasks_panel():
    with ui.column().classes("w-full q-pa-md"):
        ui.label("任务看板").classes("text-h4 q-mb-md")
        tasks_container = ui.column().classes("w-full")
        def update_tasks():
            tasks_container.clear()
            with tasks_container:
                if not state.tasks:
                    ui.label("暂无任务。发送技术性消息以生成任务。").classes("text-grey")
                    return
                for task in state.tasks:
                    with ui.card().classes("w-full q-mb-md"):
                        with ui.card_section():
                            with ui.row().classes("items-center q-gutter-md"):
                                icon_map = {"code": "💻", "analyze": "🔍", "learn": "📚", "compare": "⚖️", "debug": "🐛", "none": "📝"}
                                ui.label(icon_map.get(task["type"], "📝")).classes("text-h4")
                                with ui.column():
                                    ui.label(f"{task['type'].upper()} — {task['id']}").classes("text-h6")
                                    ui.label(f"状态: {task['status']} {'(子任务)' if task['sub'] else ''}").classes("text-caption")
                                ui.space()
                                ui.label(f"{task['progress']}%").classes("text-h5 text-primary")
                            ui.linear_progress(value=task["progress"] / 100.0, show_value=False).classes("q-mt-sm")
        ui.timer(2.0, update_tasks)


# ═══════════════════════════════════════════════════════════════
# 贝叶斯监控面板
# ═══════════════════════════════════════════════════════════════

def bayesian_panel():
    with ui.column().classes("w-full q-pa-md"):
        ui.label("贝叶斯监控").classes("text-h4 q-mb-md")

        with ui.row().classes("w-full q-gutter-md"):
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("评估次数").classes("text-subtitle2 text-grey")
                    ui.label().bind_text_from(state, "bayesian_evaluations").classes("text-h4 text-primary")
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("Base Offset μ").classes("text-subtitle2 text-grey")
                    mu_label = ui.label("0.00").classes("text-h4 text-primary")
                    def update_mu():
                        mu_label.set_text(f"{state.base_offset_mu:.2f}")
                    ui.timer(2.0, update_mu)
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("满意度").classes("text-subtitle2 text-grey")
                    sat_label = ui.label("50%").classes("text-h4 text-primary")
                    def update_sat():
                        sat_label.set_text(f"{state.is_satisfied:.0%}")
                    ui.timer(2.0, update_sat)
            with ui.card().classes("col"):
                with ui.card_section():
                    ui.label("不耐烦").classes("text-subtitle2 text-grey")
                    imp_label = ui.label("50%").classes("text-h4 text-primary")
                    def update_imp():
                        imp_label.set_text(f"{state.is_impatient:.0%}")
                    ui.timer(2.0, update_imp)

        with ui.card().classes("w-full q-mt-md"):
            with ui.card_section():
                ui.label("模式偏好分布").classes("text-h6")
                pie_options = {
                    "series": [{
                        "type": "pie",
                        "radius": ["40%", "70%"],
                        "data": [
                            {"value": 33, "name": "rule"},
                            {"value": 33, "name": "small_model"},
                            {"value": 34, "name": "remote_llm"},
                        ],
                    }]
                }
                pie_chart = ui.echart(pie_options).classes("w-full").style("height: 300px")

                def update_pie():
                    prefs = state.bayesian_mode_pref
                    if not prefs:
                        prefs = {"rule": 0.33, "small_model": 0.33, "remote_llm": 0.34}
                    pie_chart._props['options'] = {
                        "series": [{
                            "type": "pie",
                            "radius": ["40%", "70%"],
                            "data": [
                                {"value": round(v * 100), "name": k}
                                for k, v in prefs.items()
                            ],
                        }]
                    }
                    pie_chart.update()
                ui.timer(2.0, update_pie)


# ═══════════════════════════════════════════════════════════════
# 实时对话面板
# ═══════════════════════════════════════════════════════════════

def chat_panel():
    with ui.column().classes("w-full q-pa-md"):
        ui.label("实时对话").classes("text-h4 q-mb-md")

        with ui.row().classes("items-center q-gutter-sm q-mb-md"):
            ui.label("DiscourseManager:")
            status_label = ui.label("未初始化").classes("text-caption")
            def init_dm():
                state.init_dm()
                if state.dm_ready:
                    status_label.set_text(f"✅ 已连接 ({state.user_id})")
                    status_label.classes("text-positive")
                else:
                    status_label.set_text("❌ 初始化失败")
                    status_label.classes("text-negative")
            ui.button("初始化", on_click=init_dm, icon="power_settings_new").props("size=sm")

        # 消息区域 — 增量渲染，只添加新消息
        msg_area = ui.scroll_area().classes("w-full").style("min-height: 400px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px;")
        msg_container = ui.column().classes("w-full")
        with msg_area:
            with msg_container:
                ui.label("发送消息开始对话...").classes("text-grey text-center w-full").style("margin-top: 40px;")

        # 渲染单条消息
        def render_message(msg: Dict, container: ui.element) -> None:
            with container:
                if msg["role"] == "user":
                    with ui.row().classes("q-mb-md justify-end"):
                        with ui.card().classes("bg-primary text-white").style("max-width: 80%; margin-left: auto;"):
                            with ui.card_section():
                                ui.label(msg["content"]).classes("text-body1")
                                with ui.row().classes("q-mt-xs justify-end"):
                                    ui.label(f"T{msg.get('turn', '?')} • {msg.get('latency', 0):.2f}s").classes("text-caption")
                else:
                    with ui.row().classes("q-mb-md w-full"):
                        with ui.card().style("max-width: 80%; background: #f5f5f5;"):
                            with ui.card_section():
                                with ui.row().classes("items-center q-gutter-sm"):
                                    ui.icon("smart_toy", color="secondary")
                                    ui.label("MemoryGraph").classes("text-bold text-secondary")
                                    if msg.get("mode") and msg["mode"] != "error":
                                        color = {"rule": "grey", "small_model": "orange", "remote_llm": "red"}.get(msg["mode"], "grey")
                                        ui.badge(msg["mode"], color=color)

                                if msg.get("error"):
                                    ui.label(f"错误: {msg['error']}").classes("text-negative q-mt-sm")
                                else:
                                    parsed = msg.get("parsed_summary", {})
                                    with ui.row().classes("q-mt-sm q-gutter-sm items-center"):
                                        if parsed.get("tech_level") and parsed["tech_level"] != "unknown":
                                            ui.badge(f"技术: {parsed['tech_level']}", color="positive")
                                        if parsed.get("intent") and parsed["intent"] != "unknown":
                                            ui.badge(f"意图: {parsed['intent']}", color="info")
                                        if parsed.get("domains"):
                                            ui.badge(f"领域: {', '.join(parsed['domains'][:3])}", color="warning")

                                    ui.label(f"路由: {msg.get('mode', 'unknown')} • 延迟: {msg.get('latency', 0):.2f}s • 上下文: {msg.get('context_len', 0)} 字符").classes("text-caption text-grey q-mt-sm")

                                    # 反馈按钮
                                    with ui.row().classes("q-mt-sm q-gutter-sm"):
                                        ti = msg.get("turn", 0)
                                        ui.button("👍", on_click=feedback_factory(ti, True, False)).props("flat dense color=positive").tooltip("满意")
                                        ui.button("👎", on_click=feedback_factory(ti, False, False)).props("flat dense color=negative").tooltip("不满意")
                                        ui.button("🔧", on_click=feedback_factory(ti, None, True)).props("flat dense color=warning").tooltip("纠错")

                                    # 原生 HTML details 折叠（不受重建影响）
                                    content = msg.get("content", "")
                                    if content:
                                        display = html.escape(content[:3000]) + ("..." if len(content) > 3000 else "")
                                        ui.html(
                                            f'<details style="margin-top:8px;border:1px solid #ddd;border-radius:4px;">'
                                            f'<summary style="cursor:pointer;padding:8px;font-size:12px;color:#666;background:#f0f0f0;">📄 查看完整上下文</summary>'
                                            f'<div style="padding:8px;font-size:11px;white-space:pre-wrap;word-break:break-all;max-height:400px;overflow-y:auto;font-family:monospace;background:#fafafa;">{display}</div>'
                                            f'</details>'
                                        )

        # 增量渲染器
        last_rendered = [0]
        def check_and_render():
            total = len(state.messages)
            if total > last_rendered[0]:
                # 首次有消息时清除占位符
                if last_rendered[0] == 0 and total > 0:
                    msg_container.clear()
                for i in range(last_rendered[0], total):
                    render_message(state.messages[i], msg_container)
                last_rendered[0] = total
        ui.timer(1.0, check_and_render)

        # 输入区域
        ui.separator().classes("q-my-md")
        with ui.row().classes("w-full items-center q-gutter-sm"):
            input_field = ui.input("输入消息...").classes("flex-grow").props("outlined")
            async def on_send():
                query = input_field.value.strip()
                if not query:
                    return
                input_field.set_value("")
                
                # 立即显示用户消息
                with msg_container:
                    with ui.row().classes("q-mb-md justify-end"):
                        with ui.card().classes("bg-primary text-white").style("max-width: 80%; margin-left: auto;"):
                            with ui.card_section():
                                ui.label(query).classes("text-body1")
                
                # 创建流式响应占位（"思考中..."）
                from gui.streaming import StreamingResponse
                stream = StreamingResponse(msg_container, name="MemoryGraph")
                stream.start()
                
                # 后台调用（非阻塞 UI）
                import threading
                result_container = {}
                def do_send():
                    result_container["result"] = state.send_message(query)
                thread = threading.Thread(target=do_send, daemon=True)
                thread.start()
                thread.join(timeout=60.0)  # 最多等 60 秒
                
                result = result_container.get("result", {"error": "请求超时"})
                
                # 完成：替换为完整回复
                meta = {
                    "mode": result.get("mode", "unknown"),
                    "latency": result.get("latency", 0),
                    "context_len": result.get("context_len", 0),
                    "reply_len": result.get("reply_len", 0),
                    "intent": result.get("parsed_summary", {}).get("intent", "unknown"),
                    "tech_level": result.get("parsed_summary", {}).get("tech_level", "unknown"),
                }
                if result.get("error"):
                    stream.end(f"❌ 错误: {result['error']}", meta={"mode": "error"})
                    ui.notify(f"错误: {result['error'][:50]}", color="negative")
                else:
                    stream.end(result.get("result", ""), meta=meta)
                    ui.notify(f"完成 ({result.get('mode', '?')}, {result.get('latency', 0):.2f}s)", color="positive")
            ui.button("发送", on_click=on_send, icon="send").props("color=primary")
            def clear_chat():
                state.messages.clear()
                last_rendered[0] = 0
                msg_container.clear()
                with msg_container:
                    ui.label("发送消息开始对话...").classes("text-grey text-center w-full").style("margin-top: 40px;")
            ui.button("清空", on_click=clear_chat, icon="delete").props("flat")


# ═══════════════════════════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════════════════════════

@ui.page("/")
def main_page():
    with ui.header(elevated=True).classes("bg-primary text-white"):
        with ui.row().classes("items-center w-full"):
            ui.icon("psychology", size="32px")
            ui.label("MemoryGraph 智能对话系统").classes("text-h5 q-ml-sm")
            ui.space()
            ui.label(f"用户: {state.user_id}").classes("text-caption")

    with ui.tabs().classes("w-full") as tabs:
        t_dash = ui.tab("仪表盘", icon="dashboard")
        t_tree = ui.tab("对话树", icon="account_tree")
        t_tasks = ui.tab("任务看板", icon="assignment")
        t_bay = ui.tab("贝叶斯监控", icon="analytics")
        t_chat = ui.tab("实时对话", icon="chat")

    with ui.tab_panels(tabs, value=t_dash).classes("w-full"):
        with ui.tab_panel(t_dash):
            dashboard_panel()
        with ui.tab_panel(t_tree):
            tree_panel()
        with ui.tab_panel(t_tasks):
            tasks_panel()
        with ui.tab_panel(t_bay):
            bayesian_panel()
        with ui.tab_panel(t_chat):
            chat_panel()

    def global_refresh():
        state.refresh_from_dm()
    ui.timer(3.0, global_refresh)
    ui.notify("MemoryGraph Dashboard 已启动", color="positive", timeout=3000)


# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════

def start_dashboard(native: bool = True, port: int = 8080, reload: bool = False):
    ui.run(
        title="MemoryGraph Dashboard",
        native=native,
        port=port,
        reload=reload,
        window_size=(1400, 900),
        fullscreen=False,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MemoryGraph NiceGUI Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--no-native", action="store_true", help="Run in browser mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")
    args = parser.parse_args()
    start_dashboard(
        native=not args.no_native,
        port=args.port,
        reload=args.reload,
    )
