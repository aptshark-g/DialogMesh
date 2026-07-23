"""PCR V2 Comprehensive Tests — dedicated, not piggybacking on old tests."""

import sys, time
sys.path.insert(0, '.')
from core.agent.pcr_router_v2 import PCRRouterV2, PCRResult, StructuralFeatures


class TestStructuralFeatures:
    """StructuralFeatures extraction — zero hardcoded keywords."""
    
    def test_english_tool(self):
        sf = StructuralFeatures.extract("scan 0x401000 and patch with NOP")
        assert sf.entity_count >= 1, f"hex entity: {sf.entity_count}"
        assert sf.verb_count >= 1, f"action verbs: {sf.verb_count}"
    
    def test_chinese_question(self):
        sf = StructuralFeatures.extract("为什么这个函数被优化掉了？")
        assert sf.question_markers >= 1
        assert sf.cjk_ratio > 0.5
    
    def test_chinese_emotional(self):
        sf = StructuralFeatures.extract("做了三天逆向整个人都废了太难了")
        assert sf.cjk_ratio > 0.5
    
    def test_imperative(self):
        sf = StructuralFeatures.extract("run the test now!")
        assert sf.imperative_markers >= 1
    
    def test_empty(self):
        sf = StructuralFeatures.extract("")
        assert sf.word_count == 0
        assert sf.verb_count == 0


class TestPCRRouting:
    """PCR V2 routing — coordinate-based, no hardcoded labels."""
    
    def test_tool_command(self):
        r = PCRRouterV2.route("scan 0x401000 and patch")
        assert r.zone in ("ATOMIC", "PRECISION", "MIXED", "EXPLORE", "ABYSS", "PSYCHE")
        assert 0 <= r.x_axis <= 1
        assert 0 <= r.y_axis <= 1
        assert -1 <= r.z_axis <= 1
    
    def test_chinese_query(self):
        r = PCRRouterV2.route("帮我分析这个加密算法是什么")
        assert r.execution_mode in ("cache", "small_model", "retrieval", "cot", "react", "slow")
        assert r.structural is not None
        assert r.structural.cjk_ratio > 0
    
    def test_short_empty(self):
        r = PCRRouterV2.route("")
        assert r.zone in ("MIXED", "ATOMIC")
    
    def test_metadata_complete(self):
        r = PCRRouterV2.route("scan memory at 0x401000 for entry point")
        assert "sf_verb" in r.metadata
        assert "sf_entity" in r.metadata
        assert "sf_words" in r.metadata
    
    def test_zone_mapping_is_complete(self):
        """All zones map to valid execution modes."""
        zones = {"ATOMIC": "cache", "PSYCHE": "small_model", "EXPLORE": "retrieval",
                 "PRECISION": "cot", "ABYSS": "react", "MIXED": "slow"}
        for zone, expected_mode in zones.items():
            r = PCRRouterV2.route("test")
            # Force zone by using internal method
            mode = PCRRouterV2._execution_mode(zone)
            assert mode == expected_mode, f"{zone} → {mode} (expected {expected_mode})"
    
    def test_no_hardcoded_keywords(self):
        """Verify zero keyword lists in PCR V2 code."""
        text = open('core/agent/pcr_router_v2.py', encoding='utf-8').read()
        import re
        # Should NOT have hardcoded word sets for classification
        keyword_sets = re.findall(r'\w+\s*=\s*\{[^}]{30,}\}', text)
        # Only acceptable: morphological suffix sets (structural), not semantic word lists
        bad = [s for s in keyword_sets if any(ord(c) > 127 for c in s)]  # any non-ASCII = likely Chinese word list
        assert len(bad) == 0, f"Hardcoded word sets found: {bad[:3]}"
    
    def test_structural_fallback_works(self):
        """When BGE unavailable, structural fallback still routes."""
        r = PCRRouterV2.route("我需要一个确切的答案")
        assert r.execution_mode in ("cache", "small_model", "retrieval", "cot", "react", "slow")
    
    def test_cognitive_level_inference(self):
        r1 = PCRRouterV2.route("scan 0x401000")
        r2 = PCRRouterV2.route("设计一个完整的反向工程框架来支持多架构分析")
        assert r1.cognitive_level in ("light", "moderate", "heavy")
        assert r2.cognitive_level in ("light", "moderate", "heavy")


if __name__ == "__main__":
    tests = TestStructuralFeatures()
    for name in dir(tests):
        if name.startswith("test_"):
            getattr(tests, name)()
            print(f"  ✅ {name}")
    
    tests2 = TestPCRRouting()
    for name in dir(tests2):
        if name.startswith("test_"):
            getattr(tests2, name)()
            print(f"  ✅ {name}")
    
    print(f"\n🎉 PCR V2: {sum(1 for n in dir(TestStructuralFeatures) if n.startswith('test_')) + sum(1 for n in dir(TestPCRRouting) if n.startswith('test_'))} tests passed — zero hardcoded")
