# -*- coding: utf-8 -*-
"""
core/agent/tests/test_integration_bridge.py
──────────────────────────────────────────
AgentPipeline 集成测试：验证五层新模块 + 现有 PCR 链的桥接。

运行：python -m unittest core.agent.tests.test_integration_bridge -v
"""

import unittest
from unittest.mock import MagicMock, patch

from core.agent.integration_bridge import AgentPipeline


class TestAgentPipelineInit(unittest.TestCase):
    """测试 Pipeline 初始化。"""

    def test_default_init(self):
        p = AgentPipeline(session_id="test-1")
        self.assertEqual(p._session_id, "test-1")
        self.assertEqual(p._turn_index, 0)
        self.assertTrue(p._active_modules["persistence"])
        self.assertTrue(p._active_modules["compiler"])
        self.assertTrue(p._active_modules["topic_tree"])
        self.assertTrue(p._active_modules["window"])
        self.assertTrue(p._active_modules["observability"])

    def test_disabled_modules(self):
        p = AgentPipeline(
            session_id="test-2",
            use_persistence=False,
            use_compiler=False,
            use_topic_tree=False,
            use_window=False,
            use_observability=False,
        )
        self.assertIsNone(p._persistence)
        self.assertIsNone(p._compiler)
        self.assertIsNone(p._topic_tree)
        self.assertIsNone(p._window)
        self.assertIsNone(p._logger)
        self.assertIsNone(p._metrics)
        self.assertIsNone(p._alerts)


class TestAgentPipelineProcess(unittest.TestCase):
    """测试 Pipeline 处理流程（Mock 依赖）。"""

    def setUp(self):
        self.pipeline = AgentPipeline(
            session_id="test-session",
            use_persistence=False,
            use_observability=False,
        )

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_process_with_compiler(self, mock_run):
        """编译器启用时，使用编译后的 query 调用 PCR。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.92,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        result = self.pipeline.process("扫描 0x401000 的数值")

        # 验证 run_intent_trace 被调用
        self.assertTrue(mock_run.called)
        args, kwargs = mock_run.call_args
        # 编译后的 query 应该包含代词消解结果
        self.assertIn("0x401000", kwargs["query"])

        # 验证 bridge 元信息注入
        self.assertIn("bridge", result)
        self.assertEqual(result["bridge"]["turn_index"], 1)
        self.assertEqual(result["bridge"]["session_id"], "test-session")

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_process_without_compiler(self, mock_run):
        """编译器禁用时，使用原始 query 调用 PCR。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.85,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        pipeline = AgentPipeline(
            session_id="test-2",
            use_compiler=False,
            use_topic_tree=False,
            use_window=False,
            use_persistence=False,
            use_observability=False,
        )
        result = pipeline.process("扫描 0x401000")

        args, kwargs = mock_run.call_args
        self.assertEqual(kwargs["query"], "扫描 0x401000")

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_history_accumulation(self, mock_run):
        """测试历史累积。"""
        mock_run.return_value = {
            "summary": {
                "category": "DIRECT_REPLY",
                "confidence": 0.95,
                "execution_status": "direct_reply",
                "has_ambiguity": False,
                "expectation": "",
                "message": "完成",
            }
        }

        self.pipeline.process("第一问")
        self.pipeline.process("第二问")

        # 历史应该累积：每轮 user + assistant(direct_reply) = 4 条
        self.assertEqual(len(self.pipeline._session_history), 4)
        self.assertEqual(self.pipeline._session_history[0]["content"], "第一问")
        self.assertEqual(self.pipeline._session_history[1]["content"], "完成")
        self.assertEqual(self.pipeline._session_history[2]["content"], "第二问")
        self.assertEqual(self.pipeline._session_history[3]["content"], "完成")

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_turn_index_increment(self, mock_run):
        """测试轮次索引递增。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.9,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        self.pipeline.process("问1")
        self.assertEqual(self.pipeline._turn_index, 1)
        self.pipeline.process("问2")
        self.assertEqual(self.pipeline._turn_index, 2)


class TestAgentPipelineTopicRouting(unittest.TestCase):
    """测试话题路由对窗口过滤的影响。"""

    def setUp(self):
        self.pipeline = AgentPipeline(
            session_id="test-topic",
            use_persistence=False,
            use_observability=False,
        )

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_new_topic_clears_history(self, mock_run):
        """新话题应清空历史过滤。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.9,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        # 先模拟一个 continue 决策
        with patch.object(
            self.pipeline._topic_tree, "route",
            return_value=MagicMock(action="continue", target_node_id="n1")
        ):
            self.pipeline.process("第一问")
            _, kwargs1 = mock_run.call_args
            self.assertEqual(len(kwargs1["history"]), 0)  # 第一轮历史为空

        # 第二轮 continue，历史应该有第一问
        with patch.object(
            self.pipeline._topic_tree, "route",
            return_value=MagicMock(action="continue", target_node_id="n1")
        ):
            self.pipeline.process("第二问")
            _, kwargs2 = mock_run.call_args
            # 历史应该包含第一轮
            self.assertTrue(len(kwargs2["history"]) > 0)

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_fork_topic_clears_history(self, mock_run):
        """fork 话题应清空历史。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.9,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        # 先处理一轮
        with patch.object(
            self.pipeline._topic_tree, "route",
            return_value=MagicMock(action="continue", target_node_id="n1")
        ):
            self.pipeline.process("第一问")

        # 然后 fork
        with patch.object(
            self.pipeline._topic_tree, "route",
            return_value=MagicMock(action="fork", target_node_id="n2")
        ):
            self.pipeline.process("新话题")
            _, kwargs = mock_run.call_args
            # fork 应该清空历史
            self.assertEqual(len(kwargs["history"]), 0)


class TestAgentPipelineSessionSummary(unittest.TestCase):
    """测试会话摘要。"""

    def test_summary_structure(self):
        p = AgentPipeline(
            session_id="test-summary",
            use_persistence=False,
            use_observability=False,
        )
        summary = p.get_session_summary()
        self.assertEqual(summary["session_id"], "test-summary")
        self.assertEqual(summary["turn_index"], 0)
        self.assertIn("modules", summary)


class TestAgentPipelineBackwardCompat(unittest.TestCase):
    """测试向后兼容性：禁用所有新模块时，行为等价于原有 run_intent_trace。"""

    @patch("core.agent.integration_bridge.run_intent_trace")
    def test_fully_disabled_pipeline(self, mock_run):
        """所有模块禁用，直接透传 query 和历史。"""
        mock_run.return_value = {
            "summary": {
                "category": "TOOL",
                "confidence": 0.9,
                "execution_status": "completed",
                "has_ambiguity": False,
                "expectation": "",
                "message": "",
            }
        }

        p = AgentPipeline(
            session_id="compat",
            use_persistence=False,
            use_compiler=False,
            use_topic_tree=False,
            use_window=False,
            use_observability=False,
        )
        result = p.process("直接查询", verbose=False)

        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["query"], "直接查询")
        self.assertEqual(kwargs["history"], [])
        self.assertEqual(kwargs["session_id"], "compat")

        # 结果中仍有 bridge 元信息（pipeline 层注入）
        self.assertIn("bridge", result)


if __name__ == "__main__":
    unittest.main()
