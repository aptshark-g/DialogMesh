# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_frontend_layer.py
────────────────────────────────────────────
前端协议层（Layer 3）测试（v2.4 新增）。

覆盖：
  - Clarification UI Schema 序列化/反序列化
  - ClarificationUIFactory 工厂方法
  - ClarificationUICompat 降级兼容
  - TaskGraph 可视化协议
  - Clarification FSM 状态机
  - WebSocket 事件构建
"""

from __future__ import annotations

import json
import time
import unittest

from core.agent.frontend import (
    ClarificationUISchema, UIComponent, UIOption, UIValidation,
    ClarificationUIFactory, ClarificationUICompat,
    TaskNodePayload, TaskEdgePayload, TaskGraphPayload, TaskGraphUpdateEvent,
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent,
    EventType, WebSocketEvent, EventBuilder, EventSerializer,
)


class TestClarificationUISchema(unittest.TestCase):
    """验证 Clarification UI Schema。"""

    def test_basic_schema(self):
        schema = ClarificationUISchema(
            message_style="info",
            components=[
                UIComponent(
                    type="show_info",
                    id="info-1",
                    label="请选择一个进程：",
                ),
                UIComponent(
                    type="single_select",
                    id="select-1",
                    label="进程",
                    options=[
                        UIOption(value="pid1", display_text="Game.exe (1234)"),
                        UIOption(value="pid2", display_text="Game.exe (5678)"),
                    ],
                ),
            ],
            allow_free_text=False,
            timeout_hint="60秒内选择",
        )
        d = schema.to_dict()
        self.assertEqual(d["message_style"], "info")
        self.assertEqual(len(d["components"]), 2)
        self.assertEqual(d["allow_free_text"], False)

        # 反序列化
        schema2 = ClarificationUISchema.from_dict(d)
        self.assertEqual(schema2.message_style, "info")
        self.assertEqual(len(schema2.components), 2)
        self.assertEqual(schema2.components[1].options[0].value, "pid1")

    def test_validation(self):
        comp = UIComponent(
            type="text_input",
            id="input-1",
            validation=UIValidation(
                type="regex",
                pattern=r"^\d+$",
                error_message="请输入数字",
            ),
        )
        d = comp.to_dict()
        self.assertEqual(d["validation"]["type"], "regex")
        self.assertEqual(d["validation"]["pattern"], r"^\d+$")


class TestClarificationUIFactory(unittest.TestCase):
    """验证 Clarification UI 工厂。"""

    def test_process_selector(self):
        schema = ClarificationUIFactory.create_process_selector(
            candidates=["Game.exe:1234", "Game.exe:5678"],
            recommended_idx=0,
        )
        self.assertEqual(schema.message_style, "info")
        self.assertEqual(len(schema.components), 3)
        self.assertEqual(schema.components[1].type, "single_select")
        self.assertEqual(len(schema.components[1].options), 2)
        self.assertTrue(schema.components[1].options[0].highlighted)
        self.assertEqual(schema.timeout_hint, "60秒内选择进程")

    def test_address_selector(self):
        schema = ClarificationUIFactory.create_address_selector(
            addresses=["0x1000", "0x2000"],
            recommended_idx=1,
        )
        self.assertEqual(schema.message_style, "warning")
        self.assertEqual(schema.components[1].type, "multi_select")
        self.assertTrue(schema.components[1].options[1].highlighted)
        self.assertEqual(schema.components[2].type, "address_input")

    def test_value_input(self):
        schema = ClarificationUIFactory.create_value_input(
            field_name="扫描地址",
            expected_type="number",
            default="1000",
        )
        self.assertEqual(schema.components[1].type, "number_input")
        self.assertEqual(schema.components[1].default_value, "1000")
        self.assertIsNotNone(schema.components[1].validation)

    def test_dangerous_confirm(self):
        schema = ClarificationUIFactory.create_dangerous_confirm(
            action_description="修改内存值",
        )
        self.assertEqual(schema.message_style, "warning")
        self.assertEqual(schema.components[1].type, "confirm_dangerous")
        self.assertEqual(len(schema.components[1].options), 2)
        self.assertEqual(schema.timeout_hint, "30秒内确认")

    def test_tutorial_hint(self):
        schema = ClarificationUIFactory.create_tutorial_hint(
            hint_text="您似乎想扫描内存，请选择扫描类型：",
            suggestions=["精确扫描", "模糊扫描", "范围扫描"],
        )
        self.assertEqual(schema.message_style, "tutorial")
        self.assertEqual(schema.components[1].type, "single_select")
        self.assertEqual(len(schema.components[1].options), 3)
        self.assertTrue(schema.allow_skip)

    def test_progress_indicator(self):
        schema = ClarificationUIFactory.create_progress_indicator(
            message="正在扫描内存...",
            progress_pct=30.0,
        )
        self.assertEqual(schema.components[0].type, "progress_indicator")
        self.assertTrue(schema.allow_skip)


class TestClarificationUICompat(unittest.TestCase):
    """验证旧前端兼容性降级。"""

    def test_downgrade_unknown_type(self):
        schema = ClarificationUISchema(
            components=[
                UIComponent(type="unknown_future_type", id="uf1", label="未来组件"),
                UIComponent(type="single_select", id="ss1", label="标准选择"),
            ],
        )
        downgraded = ClarificationUICompat.downgrade(schema)
        self.assertEqual(downgraded.components[0].type, "show_info")
        self.assertIn("不支持的组件类型", downgraded.components[0].label)
        self.assertEqual(downgraded.components[1].type, "single_select")

    def test_downgrade_no_interactive(self):
        schema = ClarificationUISchema(
            components=[
                UIComponent(type="show_info", id="info1", label="仅展示"),
                UIComponent(type="progress_indicator", id="prog1", label="进度"),
            ],
        )
        downgraded = ClarificationUICompat.downgrade(schema)
        # 应该添加一个 fallback text_input
        self.assertTrue(
            any(c.type == "text_input" for c in downgraded.components)
        )
        self.assertTrue(downgraded.allow_free_text)


class TestTaskGraphViz(unittest.TestCase):
    """验证 TaskGraph 可视化协议。"""

    def test_node_serialization(self):
        node = TaskNodePayload(
            node_id="n1",
            name="扫描内存",
            description="扫描目标进程的内存区域",
            status="RUNNING",
            progress_pct=45.0,
            node_type="scan",
            is_destructive=False,
        )
        d = node.to_dict()
        self.assertEqual(d["node_id"], "n1")
        self.assertEqual(d["status"], "RUNNING")
        self.assertEqual(d["progress_pct"], 45.0)
        self.assertEqual(d["node_type"], "scan")

    def test_edge_serialization(self):
        edge = TaskEdgePayload(
            source_id="n1",
            target_id="n2",
            edge_type="conditional",
            label="found==true",
            active=True,
        )
        d = edge.to_dict()
        self.assertEqual(d["edge_type"], "conditional")
        self.assertEqual(d["label"], "found==true")

    def test_taskgraph_payload(self):
        tg = TaskGraphPayload(
            task_graph_id="tg-123",
            nodes=[
                TaskNodePayload(node_id="n1", name="扫描", status="SUCCESS"),
                TaskNodePayload(node_id="n2", name="读取", status="RUNNING"),
                TaskNodePayload(node_id="n3", name="分析", status="PENDING"),
            ],
            edges=[
                TaskEdgePayload(source_id="n1", target_id="n2"),
                TaskEdgePayload(source_id="n2", target_id="n3"),
            ],
        )
        self.assertEqual(tg.overall_status, "running")
        self.assertAlmostEqual(tg.progress_pct, 33.333, places=2)

        d = tg.to_dict()
        self.assertEqual(len(d["nodes"]), 3)
        self.assertEqual(len(d["edges"]), 2)

        tg2 = TaskGraphPayload.from_dict(d)
        self.assertEqual(tg2.task_graph_id, "tg-123")
        self.assertEqual(tg2.nodes[0].name, "扫描")

    def test_node_status_update(self):
        tg = TaskGraphPayload(
            nodes=[
                TaskNodePayload(node_id="n1", name="扫描", status="PENDING"),
                TaskNodePayload(node_id="n2", name="读取", status="RUNNING"),
            ],
        )
        result = tg.update_node_status("n1", "SUCCESS", result_summary="找到 3 个地址")
        self.assertTrue(result)
        self.assertEqual(tg.nodes[0].status, "SUCCESS")
        self.assertEqual(tg.nodes[0].result_summary, "找到 3 个地址")
        self.assertEqual(tg.overall_status, "running")
        self.assertEqual(tg.progress_pct, 50.0)

    def test_all_completed(self):
        tg = TaskGraphPayload(
            nodes=[
                TaskNodePayload(node_id="n1", name="扫描", status="SUCCESS"),
                TaskNodePayload(node_id="n2", name="读取", status="SUCCESS"),
            ],
        )
        self.assertEqual(tg.overall_status, "completed")
        self.assertEqual(tg.progress_pct, 100.0)

    def test_failed(self):
        tg = TaskGraphPayload(
            nodes=[
                TaskNodePayload(node_id="n1", name="扫描", status="SUCCESS"),
                TaskNodePayload(node_id="n2", name="读取", status="FAILED"),
            ],
        )
        self.assertEqual(tg.overall_status, "failed")

    def test_update_event(self):
        event = TaskGraphUpdateEvent(
            task_graph_id="tg-123",
            update_type="node_status_change",
            node_id="n2",
            new_status="SUCCESS",
            result_summary="完成",
            overall_status="running",
            overall_progress_pct=50.0,
        )
        d = event.to_dict()
        self.assertEqual(d["update_type"], "node_status_change")
        self.assertEqual(d["node_id"], "n2")
        self.assertEqual(d["new_status"], "SUCCESS")
        self.assertEqual(d["overall_progress_pct"], 50.0)


class TestClarificationFSM(unittest.TestCase):
    """验证 Clarification FSM 状态机。"""

    def setUp(self):
        self.fsm = ClarificationFSM(ClarificationFSMContext(session_id="s1"))

    def test_initial_state(self):
        self.assertEqual(self.fsm.current_state, ClarificationState.START)
        self.assertEqual(self.fsm.get_state_description(), "等待用户输入...")

    def test_start_to_parsing(self):
        new_state, response = self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        self.assertEqual(new_state, ClarificationState.PARSING)
        self.assertEqual(response["type"], "progress")
        self.assertIn("正在分析", response["message"])

    def test_parsing_to_actionable(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        new_state, response = self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY,
            {"intent_result": {"expectation": "TOOL"}},
        )
        self.assertEqual(new_state, ClarificationState.ACTIONABLE)
        self.assertEqual(response["type"], "actionable")
        self.assertEqual(response["intent_result"]["expectation"], "TOOL")

    def test_parsing_to_clarifying(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        new_state, response = self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "ambiguous_process", "candidates": ["A", "B"]}]},
        )
        self.assertEqual(new_state, ClarificationState.CLARIFYING)
        self.assertEqual(response["type"], "clarification")
        self.assertIsNotNone(response["clarification_id"])
        self.assertIn("ui_schema", response)

        # 检查澄清计数和截止时间
        self.assertEqual(self.fsm.context.clarification_count, 1)
        self.assertGreater(self.fsm.context.clarification_deadline, time.time())

    def test_clarifying_to_re_parsing(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "ambiguous_process", "candidates": ["A", "B"]}]},
        )
        new_state, response = self.fsm.handle_event(ClarificationEvent.USER_CLARIFY)
        self.assertEqual(new_state, ClarificationState.RE_PARSING)
        self.assertEqual(response["type"], "progress")

    def test_re_parsing_to_clarifying_again(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "ambiguous_process", "candidates": ["A", "B"]}]},
        )
        self.fsm.handle_event(ClarificationEvent.USER_CLARIFY)
        new_state, response = self.fsm.handle_event(
            ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "missing_value", "field": "地址"}]},
        )
        self.assertEqual(new_state, ClarificationState.CLARIFYING)
        self.assertEqual(self.fsm.context.clarification_count, 2)

    def test_clarifying_timeout(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "ambiguous_process", "candidates": ["A", "B"]}]},
        )
        # 手动设置超时的截止时间
        self.fsm.context.clarification_deadline = time.time() - 1
        event = self.fsm.check_timeout()
        self.assertEqual(event, ClarificationEvent.TIMEOUT)

        new_state, response = self.fsm.handle_event(ClarificationEvent.TIMEOUT)
        self.assertEqual(new_state, ClarificationState.EXPIRED)
        self.assertEqual(response["type"], "expired")

    def test_invalid_transition(self):
        new_state, response = self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY
        )
        self.assertEqual(new_state, ClarificationState.START)
        self.assertIn("error", response)
        self.assertIn("Invalid transition", response["error"])

    def test_can_transition(self):
        self.assertTrue(self.fsm.can_transition(ClarificationEvent.USER_MESSAGE))
        self.assertFalse(self.fsm.can_transition(ClarificationEvent.TIMEOUT))

    def test_max_clarifications(self):
        self.fsm.context.clarification_count = 5
        self.fsm.context.max_clarifications = 5
        self.assertFalse(self.fsm.can_clarify_more())

    def test_serialization(self):
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        self.fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY)

        d = self.fsm.to_dict()
        self.assertEqual(d["session_id"], "s1")
        self.assertEqual(d["state"], ClarificationState.ACTIONABLE)
        self.assertEqual(len(d["history"]), 2)

        fsm2 = ClarificationFSM.from_dict(d)
        self.assertEqual(fsm2.current_state, ClarificationState.ACTIONABLE)
        self.assertEqual(fsm2.context.session_id, "s1")

    def test_fsm_ambiguity_types(self):
        """验证不同歧义类型生成正确的 UI。"""
        # missing_value
        self.fsm.handle_event(ClarificationEvent.USER_MESSAGE)
        state, resp = self.fsm.handle_event(
            ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "missing_value", "field": "扫描值", "expected_type": "number"}]},
        )
        self.assertEqual(state, ClarificationState.CLARIFYING)
        ui = resp["ui_schema"]
        self.assertEqual(ui["components"][1]["type"], "number_input")

        # destructive_action
        self.fsm.handle_event(ClarificationEvent.USER_CLARIFY)
        state, resp = self.fsm.handle_event(
            ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "destructive_action", "description": "写入内存"}]},
        )
        self.assertEqual(state, ClarificationState.CLARIFYING)
        ui = resp["ui_schema"]
        self.assertEqual(ui["message_style"], "warning")
        self.assertEqual(ui["components"][1]["type"], "confirm_dangerous")

        # unknown_intent
        self.fsm.handle_event(ClarificationEvent.USER_CLARIFY)
        state, resp = self.fsm.handle_event(
            ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY,
            {"ambiguities": [{"type": "unknown_intent", "suggestions": ["扫描", "读取"], "hint": "您想做什么？"}]},
        )
        self.assertEqual(state, ClarificationState.CLARIFYING)
        ui = resp["ui_schema"]
        self.assertEqual(ui["message_style"], "tutorial")
        self.assertTrue(ui["allow_skip"])


class TestWebSocketEvents(unittest.TestCase):
    """验证 WebSocket 事件。"""

    def test_intent_result_event(self):
        event = EventBuilder.intent_result(
            session_id="s1",
            message_id="msg1",
            status="actionable",
            intent_result={"expectation": "TOOL"},
            latency_ms=25.0,
        )
        self.assertEqual(event.event_type, EventType.INTENT_RESULT)
        self.assertEqual(event.session_id, "s1")
        self.assertEqual(event.payload["status"], "actionable")
        self.assertEqual(event.payload["latency_ms"], 25.0)

    def test_clarification_event(self):
        schema = ClarificationUIFactory.create_process_selector(["A", "B"]).to_dict()
        event = EventBuilder.clarification(
            session_id="s1",
            clarification_id="cid123",
            message="请选择进程",
            ui_schema=schema,
        )
        self.assertEqual(event.event_type, EventType.CLARIFICATION)
        self.assertEqual(event.payload["clarification_id"], "cid123")
        self.assertIn("deadline", event.payload)
        self.assertGreater(event.payload["deadline"], time.time())

    def test_progress_event(self):
        event = EventBuilder.progress(
            session_id="s1",
            message_id="msg1",
            stage="entity_extract",
            status="started",
            detail="提取实体中",
            elapsed_ms=12.0,
        )
        self.assertEqual(event.event_type, EventType.PROGRESS)
        self.assertEqual(event.payload["stage"], "entity_extract")
        self.assertEqual(event.payload["detail"], "提取实体中")

    def test_error_event(self):
        event = EventBuilder.error(
            session_id="s1",
            code="RATE_LIMITED",
            message="请求过多",
            retryable=True,
            retry_after_ms=1000,
        )
        self.assertEqual(event.event_type, EventType.ERROR)
        self.assertEqual(event.payload["code"], "RATE_LIMITED")
        self.assertTrue(event.payload["retryable"])
        self.assertEqual(event.payload["retry_after_ms"], 1000)

    def test_state_change_event(self):
        event = EventBuilder.state_change(
            session_id="s1",
            old_state="PARSING",
            new_state="CLARIFYING",
            event="parse_complete_has_ambiguity",
            description="解析有歧义，需要澄清",
        )
        self.assertEqual(event.event_type, EventType.STATE_CHANGE)
        self.assertEqual(event.payload["old_state"], "PARSING")
        self.assertEqual(event.payload["new_state"], "CLARIFYING")

    def test_pong_event(self):
        event = EventBuilder.pong("s1", server_time=12345.0)
        self.assertEqual(event.event_type, EventType.PONG)
        self.assertEqual(event.payload["server_time"], 12345.0)

    def test_serialization(self):
        event = EventBuilder.intent_result(
            session_id="s1", message_id="m1", status="ok"
        )
        raw = EventSerializer.serialize(event)
        d = json.loads(raw)
        self.assertEqual(d["event_type"], EventType.INTENT_RESULT)
        self.assertEqual(d["payload"]["status"], "ok")

        # 反序列化
        event2 = EventSerializer.deserialize(raw)
        self.assertEqual(event2.event_type, EventType.INTENT_RESULT)
        self.assertEqual(event2.payload["status"], "ok")

    def test_serialize_batch(self):
        events = [
            EventBuilder.progress("s1", "m1", "pcr", "started"),
            EventBuilder.progress("s1", "m1", "entity", "completed"),
        ]
        raw = EventSerializer.serialize_batch(events)
        arr = json.loads(raw)
        self.assertEqual(len(arr), 2)
        self.assertEqual(arr[0]["event_type"], EventType.PROGRESS)
        self.assertEqual(arr[1]["payload"]["stage"], "entity")

    def test_event_roundtrip(self):
        event = EventBuilder.intent_result(
            session_id="s1",
            message_id="msg1",
            status="needs_clarification",
            clarification={"id": "c1", "message": "请澄清"},
        )
        raw = EventSerializer.serialize(event)
        event2 = EventSerializer.deserialize(raw)
        self.assertEqual(event2.event_type, event.event_type)
        self.assertEqual(event2.session_id, event.session_id)
        self.assertEqual(event2.payload["status"], event.payload["status"])
        self.assertEqual(event2.payload["clarification"]["id"], "c1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
