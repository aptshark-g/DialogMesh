# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_frontend_service_integration.py
──────────────────────────────────────────────────────────
前端协议层（Layer 3）与服务层（Layer 2）集成测试。

验证：
  - AgentService 使用 ClarificationFSM 管理多轮澄清
  - FSM 状态持久化到 Session
  - 事件回调通过标准 WebSocketEvent 格式发送
  - 歧义类型自动生成对应 UI Schema
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, ANY

from core.agent.service.agent_service import AgentService
from core.agent.service.models import Session, TurnRecord, IntentResult, ClarificationPayload, ErrorPayload
from core.agent.service.session_manager import SessionManager
from core.agent.service.rate_limiter import RateLimiter
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.frontend import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent,
    EventBuilder, EventSerializer,
)
from core.agent.v3_common.gates import ExecutionResult, GateResult
from core.agent.pcr.datacontract import PCROutput_v1, CognitiveProfile_v1


class MockPCR(RuleBasedPCR):
    """可控制输出的 Mock PCR。"""
    def __init__(self):
        self._next_result = None
    def set_next_result(self, result):
        self._next_result = result
    def parse(self, raw: str, history=None, parse_context=None, user_id=None):
        return self._next_result or PCROutput_v1()


class MockParser(IntentParser):
    """可控制输出的 Mock Parser。"""
    def __init__(self):
        self._next_result = None
    def set_next_result(self, result):
        self._next_result = result
    def parse(self, raw: str, history=None, parse_context=None, user_id=None):
        return self._next_result or PCROutput_v1()


class MockOrchestrator:
    """可控制输出的 Mock 编排器。"""
    def __init__(self):
        self._next_result = None
    def set_next_result(self, result):
        self._next_result = result
    def process(self, raw: str, history=None, **kwargs):
        return self._next_result or GateResult(track="track_0", blueprint_id="test", pcr_output=PCROutput_v1())


class TestAgentServiceFSMIntegration(unittest.TestCase):
    """验证 AgentService 与 FSM 集成。"""

    def setUp(self):
        self.pcr = MockPCR()
        self.parser = MockParser()
        self.session_manager = SessionManager(store=None, ttl_seconds=3600)
        self.rate_limiter = RateLimiter()
        self.events = []

        def event_callback(session_id, event_type, payload):
            self.events.append((session_id, event_type, payload))

        self.service = AgentService(
            pcr=self.pcr,
            parser=self.parser,
            session_manager=self.session_manager,
            rate_limiter=self.rate_limiter,
            event_callback=event_callback,
        )
        # 替换编排器为 mock
        self.mock_orch = MockOrchestrator()
        self.service.orchestrator = self.mock_orch

        self.session = self.service.create_session()
        self.session_id = self.session.session_id

    def test_initial_message_no_ambiguity(self):
        """正常消息 -> ACTIONABLE，FSM 状态 CLOSED。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN", cognitive_profile=CognitiveProfile_v1())
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))

        status, intent_result, clarification, error, trace = self.service.process_message(
            self.session_id, "扫描 Game.exe 中的 1000"
        )

        self.assertEqual(status, "actionable")
        self.assertIsNotNone(intent_result)
        self.assertIsNone(clarification)
        self.assertIsNone(error)

        # 检查 FSM 状态已关闭
        sess = self.session_manager.get_session(self.session_id)
        fsm_dict = sess.clarification_fsm_state
        self.assertIsNotNone(fsm_dict)
        self.assertEqual(fsm_dict["state"], "ACTIONABLE")

        # 检查事件发送
        self.assertTrue(any(e[1] == "progress" for e in self.events))
        self.assertTrue(any(e[1] == "intent_result" for e in self.events))

    def test_message_with_ambiguity(self):
        """歧义消息 -> CLARIFYING，自动生成 UI Schema。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(
                status="clarifying",
                clarification={
                    "ambiguities": [
                        {"type": "ambiguous_process", "candidates": ["Game.exe:1234", "Game.exe:5678"]}
                    ]
                },
            ),
        ))

        status, intent_result, clarification, error, trace = self.service.process_message(
            self.session_id, "扫描 Game.exe"
        )

        self.assertEqual(status, "needs_clarification")
        self.assertIsNotNone(clarification)
        self.assertIsNone(error)

        # 检查 UI Schema 已生成
        clar_dict = clarification.to_dict()
        self.assertIn("ui_schema", clar_dict)
        self.assertEqual(clar_dict["ui_schema"]["message_style"], "info")
        self.assertEqual(clar_dict["ui_schema"]["components"][1]["type"], "single_select")

        # 检查会话状态
        sess = self.session_manager.get_session(self.session_id)
        self.assertEqual(sess.state, "clarifying")
        self.assertEqual(sess.pending_clarification, clarification.clarification_id)

        # 检查 FSM 状态
        fsm_dict = sess.clarification_fsm_state
        self.assertEqual(fsm_dict["state"], "CLARIFYING")
        self.assertEqual(fsm_dict["clarification_count"], 1)

        # 检查事件
        self.assertTrue(any(e[1] == "clarification" for e in self.events))

    def test_clarification_resubmit(self):
        """提交澄清 -> 重新解析 -> ACTIONABLE。"""
        # 第一轮：歧义
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(
                status="clarifying",
                clarification={
                    "ambiguities": [
                        {"type": "ambiguous_process", "candidates": ["Game.exe:1234", "Game.exe:5678"]}
                    ]
                },
            ),
        ))
        status1, _, clar1, _, _ = self.service.process_message(self.session_id, "扫描 Game.exe")
        self.assertEqual(status1, "needs_clarification")
        self.assertIsNotNone(clar1)

        # 第二轮：提交澄清
        pcr_out2 = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out2,
            execution_result=ExecutionResult(status="success"),
        ))
        status2, intent_result2, clar2, error2 = self.service.submit_clarification(
            self.session_id,
            clarification_id=clar1.clarification_id,
            selected_option=0,
        )

        self.assertEqual(status2, "actionable")
        self.assertIsNotNone(intent_result2)
        self.assertIsNone(clar2)
        self.assertIsNone(error2)

        # 检查 FSM 状态已关闭
        sess = self.session_manager.get_session(self.session_id)
        fsm_dict = sess.clarification_fsm_state
        self.assertEqual(fsm_dict["state"], "ACTIONABLE")

    def test_clarification_id_mismatch(self):
        """提交错误的 clarification_id -> 错误。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(
                status="clarifying",
                clarification={
                    "ambiguities": [
                        {"type": "ambiguous_process", "candidates": ["A", "B"]}
                    ]
                },
            ),
        ))
        status1, _, clar1, _, _ = self.service.process_message(self.session_id, "扫描")
        self.assertEqual(status1, "needs_clarification")

        # 提交错误的 ID
        status2, _, _, error2 = self.service.submit_clarification(
            self.session_id,
            clarification_id="wrong_id",
            selected_option=0,
        )
        self.assertEqual(status2, "error")
        self.assertIsNotNone(error2)
        self.assertEqual(error2.code, "CLARIFICATION_MISMATCH")

    def test_not_clarifying_state(self):
        """会话不在澄清状态却提交澄清 -> 错误。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))
        self.service.process_message(self.session_id, "扫描 Game.exe")

        # 此时 FSM 已关闭，不在 CLARIFYING
        status, _, _, error = self.service.submit_clarification(
            self.session_id,
            clarification_id="cid123",
            selected_option=0,
        )
        self.assertEqual(status, "error")
        self.assertEqual(error.code, "NOT_CLARIFYING")

    def test_different_ambiguity_types(self):
        """验证不同歧义类型生成正确的 UI。"""
        ambiguity_types = [
            ("ambiguous_process", {"candidates": ["A", "B"]}, "single_select"),
            ("ambiguous_address", {"candidates": ["0x1000", "0x2000"]}, "multi_select"),
            ("missing_value", {"field": "扫描值", "expected_type": "number"}, "number_input"),
            ("destructive_action", {"description": "写入内存"}, "confirm_dangerous"),
            ("unknown_intent", {"hint": "请选择", "suggestions": ["扫描", "读取"]}, "single_select"),
        ]

        for amb_type, amb_data, expected_comp_type in ambiguity_types:
            with self.subTest(amb_type=amb_type):
                self.events.clear()
                self.session = self.service.create_session()
                sid = self.session.session_id

                pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
                amb_data_copy = amb_data.copy()
                amb_data_copy["type"] = amb_type
                self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
                    pcr_output=pcr_out,
                    execution_result=ExecutionResult(
                        status="clarifying",
                        clarification={"ambiguities": [amb_data_copy]},
                    ),
                ))

                status, _, clar, _, _ = self.service.process_message(sid, "test")
                self.assertEqual(status, "needs_clarification")
                self.assertIsNotNone(clar)

                ui_schema = clar.to_dict()["ui_schema"]
                # 第 0 个组件是信息展示，第 1 个是交互组件
                comp = ui_schema["components"][1]
                self.assertEqual(comp["type"], expected_comp_type)

    def test_fsm_status_in_session_status(self):
        """会话状态查询包含 FSM 状态。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))
        self.service.process_message(self.session_id, "扫描")

        status = self.service.get_status(self.session_id)
        self.assertIsNotNone(status)
        self.assertIn("fsm", status)
        self.assertEqual(status["fsm"]["state"], "ACTIONABLE")
        self.assertEqual(status["fsm"]["clarification_count"], 0)
        self.assertTrue(status["fsm"]["can_clarify_more"])

    def test_event_callback_standard_format(self):
        """验证事件回调发送标准格式。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))
        self.service.process_message(self.session_id, "扫描")

        # 检查事件类型
        event_types = [e[1] for e in self.events]
        self.assertIn("progress", event_types)
        self.assertIn("intent_result", event_types)

        # 检查 intent_result 事件包含关键字段
        intent_events = [e for e in self.events if e[1] == "intent_result"]
        self.assertEqual(len(intent_events), 1)
        payload = intent_events[0][2]
        self.assertIn("status", payload)
        self.assertIn("latency_ms", payload)

    def test_clarification_max_rounds(self):
        """验证多轮澄清后达到最大次数限制。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")
        # 连续 2 轮完整循环 (process + submit)，每轮增加 2 次 count
        for i in range(2):
            self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
                pcr_output=pcr_out,
                execution_result=ExecutionResult(
                    status="clarifying",
                    clarification={
                        "ambiguities": [
                            {"type": "ambiguous_process", "candidates": ["A", "B"]}
                        ]
                    },
                ),
            ))
            status, _, clar, _, _ = self.service.process_message(
                self.session_id, f"歧义消息 {i}"
            )
            self.assertEqual(status, "needs_clarification")
            self.assertIsNotNone(clar)
            # 模拟澄清提交
            self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
                pcr_output=pcr_out,
                execution_result=ExecutionResult(
                    status="clarifying",
                    clarification={
                        "ambiguities": [
                            {"type": "ambiguous_process", "candidates": ["A", "B"]}
                        ]
                    },
                ),
            ))
            self.service.submit_clarification(
                self.session_id,
                clarification_id=clar.clarification_id,
                selected_option=0,
            )

        # 第 3 轮 process_message (count=5，达到上限)
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(
                status="clarifying",
                clarification={
                    "ambiguities": [
                        {"type": "ambiguous_process", "candidates": ["A", "B"]}
                    ]
                },
            ),
        ))
        status, _, clar, _, _ = self.service.process_message(
            self.session_id, "歧义消息 2"
        )
        self.assertEqual(status, "needs_clarification")
        self.assertIsNotNone(clar)

        # 检查 FSM 状态: count=5, max=5, can_clarify_more=False
        sess = self.session_manager.get_session(self.session_id)
        fsm_dict = sess.clarification_fsm_state
        self.assertEqual(fsm_dict["clarification_count"], 5)
        self.assertEqual(fsm_dict["max_clarifications"], 5)

    def test_session_state_transitions(self):
        """验证会话状态随 FSM 转换。"""
        pcr_out = PCROutput_v1(expectation="TOOL_SCAN")

        # 1. 初始 -> active
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))
        self.service.process_message(self.session_id, "扫描")
        sess = self.session_manager.get_session(self.session_id)
        self.assertEqual(sess.state, "active")
        self.assertIsNone(sess.pending_clarification)

        # 2. 歧义 -> clarifying
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(
                status="clarifying",
                clarification={
                    "ambiguities": [
                        {"type": "ambiguous_process", "candidates": ["A", "B"]}
                    ]
                },
            ),
        ))
        status, _, clar, _, _ = self.service.process_message(self.session_id, "歧义")
        self.assertEqual(status, "needs_clarification")
        sess = self.session_manager.get_session(self.session_id)
        self.assertEqual(sess.state, "clarifying")
        self.assertIsNotNone(sess.pending_clarification)

        # 3. 澄清后 -> active
        self.mock_orch.set_next_result(GateResult(track="track_0", blueprint_id="test",
            pcr_output=pcr_out,
            execution_result=ExecutionResult(status="success"),
        ))
        self.service.submit_clarification(
            self.session_id,
            clarification_id=clar.clarification_id,
            selected_option=0,
        )
        sess = self.session_manager.get_session(self.session_id)
        self.assertEqual(sess.state, "active")
        self.assertIsNone(sess.pending_clarification)


class TestWebSocketEventSerialization(unittest.TestCase):
    """验证 WebSocket 事件序列化。"""

    def test_intent_result_event(self):
        event = EventBuilder.intent_result(
            session_id="s1",
            message_id="msg1",
            status="actionable",
            intent_result={"expectation": "TOOL"},
            latency_ms=25.0,
        )
        raw = EventSerializer.serialize(event)
        event2 = EventSerializer.deserialize(raw)
        self.assertEqual(event2.event_type, "intent_result")
        self.assertEqual(event2.payload["status"], "actionable")
        self.assertEqual(event2.payload["latency_ms"], 25.0)

    def test_clarification_event(self):
        event = EventBuilder.clarification(
            session_id="s1",
            clarification_id="cid123",
            message="请选择",
            ui_schema={"message_style": "info"},
        )
        raw = EventSerializer.serialize(event)
        event2 = EventSerializer.deserialize(raw)
        self.assertEqual(event2.payload["clarification_id"], "cid123")
        self.assertEqual(event2.payload["ui_schema"]["message_style"], "info")
        self.assertIn("deadline", event2.payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
