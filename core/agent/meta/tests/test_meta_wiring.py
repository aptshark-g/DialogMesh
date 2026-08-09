# -*- coding: utf-8 -*-
"""
元认知 M5/M8/M9 批次测试（2026-08-05）。

覆盖:
  M5-M1  FeedbackBridge post_decision 写回（MetaSubscriber → 冷→热三层反馈）
  M5-M2  MetaSubscriber 显式 subscribe 接线（修复"实例存在从未订阅"）
  M5-M3  engine _init_meta_runtime / _run_meta_consume + 每 5 轮钩子
  M4     handle_meta retrospect 真实意图参数
  M8     三套归一: v4 MetaCognition.consume_trace（MetaConsumer 组件化）+ v3 归档
  M9     MetaReviewer/cognitive_loop 归档 + TriggerEngine 保留为组件资产
"""

import os
import tempfile
import types
import unittest


class FakeBus:
    """EventBus v2 同步桥最小替身（记录订阅与发布）。"""

    def __init__(self):
        self.subscribed = []
        self.published = []

    def subscribe_sync(self, kind, cb=None, **kwargs):
        self.subscribed.append(kind)

    def publish_sync(self, kind, payload=None, **kwargs):
        self.published.append((kind, payload))


class TestM5M1_FeedbackBridgeWriteBack(unittest.TestCase):
    """M5-M1: post_decision 零调用方 → MetaSubscriber 写回 FeedbackBridge。"""

    def test_profile_drift_posts_urgent_correction(self):
        from core.agent.meta.feedback_bridge import FeedbackBridge
        from core.agent.meta.meta_subscriber import MetaSubscriber
        fb = FeedbackBridge()
        ms = MetaSubscriber(feedback_bridge=fb)
        ms._state.profile_drift = 0.5
        ms._turn_count = 6
        ms._review_and_publish()
        self.assertTrue(fb.has_pending())
        correction = fb.consume()
        self.assertEqual(correction["type"], "profile_drift")
        self.assertEqual(correction["action"], "recalibrate_profile")
        self.assertFalse(fb.has_pending())  # consume 后取走

    def test_behavior_count_posts_belief_update(self):
        from core.agent.meta.feedback_bridge import FeedbackBridge
        from core.agent.meta.meta_subscriber import MetaSubscriber
        fb = FeedbackBridge()
        ms = MetaSubscriber(feedback_bridge=fb)
        ms._state.behavior_count = 5
        ms._state.profile_drift = 0.0
        ms._turn_count = 5
        ms._review_and_publish()
        belief = fb.consume_belief()
        self.assertEqual(belief["type"], "behavior_pattern")

    def test_no_bridge_is_safe(self):
        from core.agent.meta.meta_subscriber import MetaSubscriber
        ms = MetaSubscriber()  # bridge=None
        ms._turn_count = 5
        ms._review_and_publish()  # 不抛
        self.assertEqual(ms._turn_count, 5)


class TestM5M2_SubscribeWiring(unittest.TestCase):
    """M5-M2: 显式 subscribe（cli/engine 延迟接线后重订阅）。"""

    def test_subscribe_after_delayed_wiring(self):
        from core.agent.meta.meta_subscriber import SUBSCRIBED_KINDS, MetaSubscriber
        bus = FakeBus()
        ms = MetaSubscriber()  # 初始 bus=None → 不订阅
        self.assertFalse(ms.subscribe())
        ms._bus = bus
        self.assertTrue(ms.subscribe())
        self.assertEqual(len(bus.subscribed), len(SUBSCRIBED_KINDS))
        for kind in SUBSCRIBED_KINDS:
            self.assertIn(kind, bus.subscribed)

    def test_init_with_bus_subscribes(self):
        from core.agent.meta.meta_subscriber import SUBSCRIBED_KINDS, MetaSubscriber
        bus = FakeBus()
        MetaSubscriber(bus=bus)
        self.assertEqual(len(bus.subscribed), len(SUBSCRIBED_KINDS))

    def test_subscriber_receives_event(self):
        """订阅后事件驱动 _on_event（kind → _on_msg 解析）。"""
        from core.agent.meta.meta_subscriber import MetaSubscriber
        bus = FakeBus()
        ms = MetaSubscriber(bus=bus)
        ms._on_msg(types.SimpleNamespace(subject="behavior_recorded", data={"x": 1}))
        self.assertEqual(ms._state.behavior_count, 1)


class TestM5M3_EngineMetaRuntime(unittest.TestCase):
    """M5-M3: _meta_consumer/_trace_v3 初始化 + 每 5 轮 consume 闭环。"""

    def setUp(self):
        from core.agent.runtime.engine import CognitiveRuntimeEngine
        self.engine = CognitiveRuntimeEngine()

    def test_init_meta_runtime_creates_components(self):
        self.assertIsNone(self.engine._trace_v3)
        self.assertIsNone(self.engine._meta_consumer)
        self.engine._init_meta_runtime()
        self.assertIsNotNone(self.engine._trace_v3)
        self.assertIsNotNone(self.engine._meta_consumer)

    def test_run_meta_consume_submits_review(self):
        """MetaConsumer 检出 REJECT 模式 → adjust → 审核队列入队（M8 归一）。"""
        from core.agent.v4.cognitive.metacognition import MetaCognition
        self.engine._init_meta_runtime()

        class _FakeTrace:
            def meta_analyze(self):
                return {
                    "empty": False,
                    "reason_distribution": {"reject": 2, "observe": 1, "infer": 1},
                    "avg_confidence": 0.9,
                }

        tmp = tempfile.mkdtemp()
        self.engine._meta_cognition = MetaCognition(persist_dir=tmp)
        self.engine._trace_v3 = _FakeTrace()
        advice = self.engine._run_meta_consume()
        self.assertTrue(advice.get("adjust"))
        self.assertGreaterEqual(len(self.engine._meta_cognition._queue), 1)
        queued = self.engine._meta_cognition._queue[0]
        self.assertEqual(queued.source, "self")
        self.assertEqual(queued.target, "learning_loop")

    def test_five_turn_hook_fires(self):
        """on_event_sm 每 5 轮触发 meta runtime（此前恒 None → 闭环从未执行）。"""
        self.engine._state_machine = types.SimpleNamespace(
            run_pipeline=lambda phase, ctx: {"phases": [], "results": {}}
        )

        def _event(text):
            return types.SimpleNamespace(payload={"text": text, "session_id": "s"}, session_id="s")

        for i in range(1, 5):
            self.engine.on_event_sm(_event(f"turn{i}"))
            self.assertIsNone(self.engine._trace_v3)  # 第 1-4 轮不初始化

        self.engine.on_event_sm(_event("turn5"))
        self.assertIsNotNone(self.engine._trace_v3)   # 第 5 轮初始化 + consume
        self.assertIsNotNone(self.engine._meta_consumer)
        self.assertIsInstance(self.engine._meta_consumer._last_advice, dict)


class TestM4_HandleMetaIntentParam(unittest.TestCase):
    """M4: handle_meta retrospect 用真实意图（不再恒 general）。"""

    def _make_handler(self):
        from core.agent.event.handlers import register_all_handlers
        engine = types.SimpleNamespace(_meta_cognition=None, _state_machine=None)
        register_all_handlers(engine, tracer=None)  # 内部自建 StateMachine 并挂到 engine
        return engine, engine._state_machine

    def test_meta_handler_runs_with_intent_ctx(self):
        """meta 阶段 handler 在 intent 上下文中可执行（不抛、reviewed=True）。"""
        from core.agent.event.statemachine import PipelinePhase
        from core.agent.v4.cognitive.metacognition import MetaCognition
        tmp = tempfile.mkdtemp()
        mc = MetaCognition(persist_dir=tmp)
        engine, sm = self._make_handler()
        engine._meta_cognition = mc
        # 直接执行 META handler（通过 run_pipeline 触发，需传枚举）
        result = sm.run_pipeline(PipelinePhase.META, {
            "text": "hello",
            "intent": {"category": "ADVISOR"},
            "pcr": {"intent": "QUERY"},
        })
        results = result.get("results", {})
        meta = results.get("meta") or {}
        self.assertTrue(meta.get("reviewed"))


class TestM8_ThreeWayNormalization(unittest.TestCase):
    """M8: v4 唯一内核 + MetaConsumer 组件化 + v3 归档。"""

    def test_consume_trace_queues_review_items(self):
        from core.agent.v4.cognitive.metacognition import MetaCognition
        from core.agent.v4.cognitive.meta_consumer import MetaConsumer
        tmp = tempfile.mkdtemp()
        mc = MetaCognition(persist_dir=tmp, meta_consumer=MetaConsumer())

        class _FakeTrace:
            def meta_analyze(self):
                return {
                    "empty": False,
                    "reason_distribution": {"reject": 2, "observe": 0, "infer": 0},
                    "avg_confidence": 0.5,
                }

        advice = mc.consume_trace(_FakeTrace(), 6)
        self.assertTrue(advice.get("adjust"))
        self.assertGreaterEqual(len(mc._queue), 1)
        self.assertEqual(mc._queue[0].source, "self")
        self.assertIn("REJECT", mc._queue[0].data["warning"].upper())

    def test_consume_trace_lazy_consumer(self):
        """meta_consumer 未注入时懒创建（归一入口自洽）。"""
        from core.agent.v4.cognitive.metacognition import MetaCognition
        tmp = tempfile.mkdtemp()
        mc = MetaCognition(persist_dir=tmp)
        class _EmptyTrace:
            def meta_analyze(self):
                return {"empty": True}
        advice = mc.consume_trace(_EmptyTrace(), 1)
        self.assertFalse(advice.get("adjust", False))
        self.assertIsNotNone(mc._meta_consumer)

    def test_v3_adapter_archived(self):
        """v3 根 metacognition.py 已归档 v4/un_use，主路径不引用。"""
        root_meta = os.path.join("core", "agent", "metacognition.py")
        archive = os.path.join("core", "agent", "v4", "un_use", "metacognition_v3.py")
        self.assertFalse(os.path.exists(root_meta))
        self.assertTrue(os.path.exists(archive))

    def test_registry_points_to_v4(self):
        """subsystem_registrations 的 meta_cognition 注册串 → v4 内核。"""
        from core.agent.cli.subsystem_registrations import _registry
        self.assertEqual(
            _registry._defs["meta_cognition"].path,
            "core.agent.v4.cognitive.metacognition:MetaCognition",
        )


class TestM9_OrphanDisposition(unittest.TestCase):
    """M9: MetaReviewer/cognitive_loop 归档；TriggerEngine 保留为组件资产。"""

    def test_cognitive_loop_archived(self):
        """event/cognitive_loop.py（MetaReviewer 孤儿）已归档。"""
        src = os.path.join("core", "agent", "event", "cognitive_loop.py")
        archive = os.path.join("core", "agent", "v4", "un_use", "cognitive_loop_v1.py")
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(archive))

    def test_trigger_engine_kept_as_component(self):
        """MetacognitiveTriggerEngine 保留为组件资产（设计 §6 触发价值）。"""
        from core.agent.observability.metacognitive_trigger import MetacognitiveTriggerEngine
        self.assertTrue(callable(MetacognitiveTriggerEngine))


if __name__ == "__main__":
    unittest.main()
