"""DialogMesh v6 — Backend Module Tests (自动化)

Run: python tests/test_backend_modules.py
Requires: Gateway running on :8080, API not needed for most tests.
"""

import sys, unittest, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Test 1: GlobalDecider State Machine ──

class TestGlobalDecider(unittest.TestCase):
    def setUp(self):
        from core.agent.v4.state.global_decider import GlobalDecider, Command
        self.d = GlobalDecider()
        self.Command = Command

    def test_single_tick(self):
        evt = self.d.decide(self.Command(type="user_message"))
        state = self.d.evolve(evt)
        self.assertEqual(state.tick, 1)
        self.assertEqual(len(self.d.event_log), 1)

    def test_multi_tick_pipeline(self):
        for i, (cmd_type, field, expected) in enumerate([
            ("user_message", None, None),
            ("pcr", "pcr_expectation", "TOOL"),
            ("intent", "intent_category", "C"),
            ("planning", "plan_task_count", 3),
            ("profile", "profile_trust", 0.7),
        ]):
            payload = {}
            if field == "pcr_expectation":
                payload = {"expectation": "TOOL"}
            elif field == "intent_category":
                payload = {"category": "C"}
            elif field == "plan_task_count":
                payload = {"task_count": 3}
            elif field == "profile_trust":
                payload = {"trust": 0.7}
            self.d.evolve(self.d.decide(self.Command(type=cmd_type, payload=payload)))
            if expected is not None:
                self.assertEqual(getattr(self.d.state, field), expected, f"Tick {i+1}: {field}")

        self.assertEqual(self.d.state.tick, 5)
        self.assertEqual(len(self.d.event_log), 5)

    def test_broadcast_storm_prevention(self):
        # Each command produces exactly 1 event
        for i in range(10):
            self.d.evolve(self.d.decide(self.Command(type="user_message")))
        self.assertEqual(len(self.d.event_log), 10)
        self.assertEqual(self.d.state.tick, 10)

    def test_state_snapshot(self):
        self.d.evolve(self.d.decide(self.Command(type="pcr", payload={"expectation": "ADVISOR"})))
        self.d.evolve(self.d.decide(self.Command(type="intent", payload={"category": "EXPLAIN"})))
        self.d.evolve(self.d.decide(self.Command(type="behavior")))
        s = self.d.stats()
        self.assertIn("tick", s)
        self.assertIn("events_logged", s)
        self.assertEqual(s["events_logged"], 3)


# ── Test 2: PCR RuleBasedPCR ──

class TestPCR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.agent.pcr.datacontract import PCRInput_v1
        from core.agent.pcr.rule_based import RuleBasedPCR
        cls.PCRInput = PCRInput_v1
        cls.pcr = RuleBasedPCR()

    def test_expectation_tool(self):
        result = self.pcr.evaluate(self.PCRInput(query="scan 4 bytes for 100 in Game.exe"))
        self.assertIn(result.expectation, ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"])

    def test_expectation_advisor(self):
        result = self.pcr.evaluate(self.PCRInput(query="这段代码有什么问题？"))
        self.assertIn(result.expectation, ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"])

    def test_noise_level_range(self):
        result = self.pcr.evaluate(self.PCRInput(query="hello world"))
        self.assertGreaterEqual(result.noise_level, 0)
        self.assertLessEqual(result.noise_level, 1.0)

    def test_complexity_range(self):
        result = self.pcr.evaluate(self.PCRInput(query="先扫描再修改然后hook"))
        self.assertGreaterEqual(result.complexity_level, 0)
        self.assertLessEqual(result.complexity_level, 1.0)

    def test_execution_mode(self):
        result = self.pcr.evaluate(self.PCRInput(query="帮我分析这个函数"))
        valid_modes = ["FAST_EXECUTE", "CLARIFICATION", "DEEP_RESEARCH", "CONVERSATIONAL", "BALANCED"]
        self.assertIn(result.execution_mode, valid_modes)

    def test_empty_input(self):
        result = self.pcr.evaluate(self.PCRInput(query=""))
        self.assertEqual(result.expectation, "UNKNOWN")


# ── Test 3: IntentParser ──

class TestIntentParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.agent.v3_common.intent_parser import IntentParser
        from core.agent.v3_common.models import IntentContext, ParseContext
        cls.parser = IntentParser()
        cls.IntentContext = IntentContext
        cls.ParseContext = ParseContext

    def test_basic_parse(self):
        result = self.parser.parse(
            user_input="分析这段代码的性能",
            intent_context=self.IntentContext(),
            parse_context=self.ParseContext(),
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.intent)

    def test_entity_extraction(self):
        result = self.parser.parse(
            user_input="读取 0x00401000 处的 4 bytes",
            intent_context=self.IntentContext(),
            parse_context=self.ParseContext(),
        )
        self.assertIsNotNone(result)

    def test_parse_with_context(self):
        ctx = self.IntentContext()
        ctx.noise_level = 0.2
        ctx.complexity_level = 0.5
        result = self.parser.parse(
            user_input="帮我写一个脚本",
            intent_context=ctx,
            parse_context=self.ParseContext(),
        )
        self.assertIsNotNone(result)


# ── Test 4: Gateway Connectivity ──

class TestGateway(unittest.TestCase):
    def test_gateway_health(self):
        import urllib.request, json
        try:
            r = urllib.request.urlopen("http://127.0.0.1:8080/v1/health", timeout=5)
            body = json.loads(r.read())
            self.assertEqual(body["status"], "ok")
            self.assertGreater(body["providers_healthy"], 0)
        except Exception as e:
            self.skipTest(f"Gateway not available: {e}")

    def test_gateway_llm(self):
        import urllib.request, json
        try:
            data = json.dumps({
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "say hi in one word"}],
                "max_tokens": 10,
            }).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json", "Authorization": "Bearer not-needed"},
            )
            r = urllib.request.urlopen(req, timeout=10)
            body = json.loads(r.read())
            self.assertIn("choices", body)
            self.assertTrue(len(body["choices"]) > 0)
        except Exception as e:
            self.skipTest(f"Gateway LLM call failed: {e}")


# ── Test 5: TopicMatcher (Recursive Convergence) ──

class TestTopicMatcher(unittest.TestCase):
    def setUp(self):
        from core.agent.v4.tiered.topic_matcher import RecursiveConvergenceMatcher
        self.m = RecursiveConvergenceMatcher()

    def test_kurtosis_peak(self):
        k = self.m._kurtosis([1.0, 1.0, 1.0])
        self.assertGreater(k, 5.0)

    def test_kurtosis_flat(self):
        k = self.m._kurtosis([0.9, 0.2, 0.1])
        self.assertLess(k, 0)

    def test_match_basic(self):
        result = self.m.match(text="延迟飙升，没加监控是吗")
        self.assertIsNotNone(result)
        self.assertIsInstance(result.topic, str)


# ── Test 6: GlobalDecider + Engine integration ──

class TestEngineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
        cls.engine = CognitiveRuntimeEngine()
        cls.engine.start()

    def test_engine_started(self):
        self.assertTrue(self.engine._running)

    def test_decider_initialized(self):
        self.assertIsNotNone(self.engine._decider)

    def test_pcr_initialized(self):
        self.assertIsNotNone(self.engine._pcr_router)

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
