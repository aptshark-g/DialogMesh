import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.summary.l1.models import ContentCategory, L1SummaryEntry, L1MetaInfo
from core.agent.summary.l1.content_classifier import ContentClassifier
from core.agent.summary.l1.meta_extractor import MetaInfoExtractor
from core.agent.summary.l1.summary_generator import SummaryGenerator

class TestCategory:
    def test_values(self):
        assert ContentCategory.DETERMINISTIC.value == "deterministic"
class TestClassifier:
    def test_deterministic_type(self):
        c = ContentClassifier()
        cat = c.classify({"type":"tool_output"})
        assert cat == ContentCategory.DETERMINISTIC
    def test_llm_default(self):
        c = ContentClassifier()
        cat = c.classify({"raw_text":"hello world"})
        assert cat == ContentCategory.LLM
class TestGenerator:
    def test_deterministic(self):
        import types; m = types.SimpleNamespace(current_action="run")
        g = SummaryGenerator()
        r = g.generate(ContentCategory.DETERMINISTIC, {"result":"ok"}, m)
        assert "run" in r
class TestExtractor:
    def test_defaults(self):
        e = MetaInfoExtractor()
        info = e.extract({}, "")
        assert info.user_satisfaction == "neutral"
class TestEntry:
    def test_create(self):
        e = L1SummaryEntry("t1", "det", "text")
        assert e.turn_id == "t1"